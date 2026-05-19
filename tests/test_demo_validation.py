"""Demo-world validation: sample listings prove ranking behaves like a buyer assistant."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.listings.listing_fit import (
    MISSING_MILEAGE_WARNING,
    MISSING_PRICE_WARNING,
    NOT_AWD_WARNING,
    score_listing_fit,
)
from src.listings.listing_ranker import (
    COVERAGE_MESSAGE_NO_LISTINGS,
    rank_listings_by_recommendation,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDENT_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
OUTDOOR_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "outdoor_snow_listings.json"
DEMO_SCRIPT = PROJECT_ROOT / "Scripts" / "demo_listing_fit.py"

EXCLUDED_GOOD_MODEL_LISTINGS = frozenset({"good_camry", "good_mazda3", "good_outback"})


def _load_listings(path: Path) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    listings = [(entry["id"], entry["listing"]) for entry in data["listings"]]
    return data["buyer_profile_id"], listings


def _buyer(profile_id: str) -> dict[str, Any]:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise AssertionError(f"profile not found: {profile_id}")


def _rank(path: Path, *, exclude_ids: frozenset[str] = frozenset()) -> dict[str, Any]:
    buyer_profile_id, listings = _load_listings(path)
    if exclude_ids:
        listings = [(name, listing) for name, listing in listings if name not in exclude_ids]
    recommendations = recommend(buyer_profile_id)["recommendations"]
    return rank_listings_by_recommendation(
        listings, recommendations, _buyer(buyer_profile_id)
    )


def _group_by_model(ranked: dict[str, Any], model: str) -> dict[str, Any]:
    for group in ranked["groups"]:
        if group["model"] == model:
            return group
    raise AssertionError(f"group not found: {model}")


def _fit_in_group(ranked: dict[str, Any], model: str, listing_name: str) -> dict[str, Any]:
    group = _group_by_model(ranked, model)
    for entry in group["listings"]:
        if entry["listing_name"] == listing_name:
            return entry["fit"]
    raise AssertionError(f"{listing_name} not in {model} group")


def _rank_in_group(ranked: dict[str, Any], model: str, listing_name: str) -> int:
    group = _group_by_model(ranked, model)
    names = [entry["listing_name"] for entry in group["listings"]]
    return names.index(listing_name) + 1


@pytest.fixture
def ranked_student() -> dict[str, Any]:
    return _rank(STUDENT_LISTINGS_PATH)


@pytest.fixture
def ranked_student_sparse() -> dict[str, Any]:
    return _rank(STUDENT_LISTINGS_PATH, exclude_ids=EXCLUDED_GOOD_MODEL_LISTINGS)


@pytest.fixture
def ranked_outdoor() -> dict[str, Any]:
    return _rank(OUTDOOR_LISTINGS_PATH)


def test_missing_price_creates_warning_not_invalid_listing(ranked_student):
    fit = _fit_in_group(ranked_student, "Corolla", "missing_price_corolla")

    assert any(MISSING_PRICE_WARNING in warning for warning in fit["warnings"])
    assert "missing_price_corolla" not in {
        entry["listing_name"] for entry in ranked_student["invalid_listings"]
    }


def test_missing_mileage_creates_warning_not_invalid_listing(ranked_student):
    fit = _fit_in_group(ranked_student, "Corolla", "missing_mileage_corolla")

    assert any(MISSING_MILEAGE_WARNING in warning for warning in fit["warnings"])
    assert "missing_mileage_corolla" not in {
        entry["listing_name"] for entry in ranked_student["invalid_listings"]
    }


def test_dirty_title_cannot_be_strong_fit(ranked_student):
    for listing_name in ("dirty_title_corolla", "cheap_dirty_title_civic"):
        model = "Corolla" if "corolla" in listing_name else "Civic"
        fit = _fit_in_group(ranked_student, model, listing_name)
        assert fit["fit_label"] != "Strong fit"


def test_over_budget_cannot_outrank_clean_within_budget_corolla(ranked_student):
    assert _rank_in_group(ranked_student, "Corolla", "good_corolla") < _rank_in_group(
        ranked_student, "Corolla", "over_budget_corolla"
    )
    assert _rank_in_group(ranked_student, "Corolla", "good_corolla") < _rank_in_group(
        ranked_student, "Corolla", "low_mileage_overpriced_corolla"
    )


def test_high_mileage_ranks_below_normal_mileage_corolla(ranked_student):
    assert _rank_in_group(ranked_student, "Corolla", "good_corolla") < _rank_in_group(
        ranked_student, "Corolla", "high_mileage_corolla"
    )


def test_high_mileage_mazda3_ranks_below_good_mazda3(ranked_student):
    assert _rank_in_group(ranked_student, "Mazda3", "good_mazda3") < _rank_in_group(
        ranked_student, "Mazda3", "good_year_high_mileage_mazda3"
    )


def test_no_listing_recommendation_groups_still_display(ranked_student_sparse):
    group = _group_by_model(ranked_student_sparse, "Camry")

    assert group["listings"] == []
    assert group["coverage_message"] == COVERAGE_MESSAGE_NO_LISTINGS


def test_unmatched_listings_score_zero(ranked_student):
    bmw = next(
        entry
        for entry in ranked_student["unmatched_listings"]
        if entry["listing_name"] == "wrong_model_bmw"
    )
    assert bmw["fit"]["fit_score"] == 0.0


def test_wrong_trim_corolla_gets_trim_warning(ranked_student):
    fit = _fit_in_group(ranked_student, "Corolla", "wrong_trim_corolla")

    assert any("not a recognized trim" in warning for warning in fit["warnings"])


def test_missing_trim_corolla_does_not_get_trim_specified_warning(ranked_student):
    fit = _fit_in_group(ranked_student, "Corolla", "missing_trim_corolla")

    assert not any("Trim not specified" in warning for warning in fit["warnings"])


def test_good_listing_for_each_top_recommended_model(ranked_student):
    for model, listing_name in (
        ("Corolla", "good_corolla"),
        ("Civic", "good_civic"),
        ("Camry", "good_camry"),
        ("Mazda3", "good_mazda3"),
        ("Outback", "good_outback"),
    ):
        fit = _fit_in_group(ranked_student, model, listing_name)
        assert fit["fit_label"] == "Strong fit"


def test_fwd_outback_for_awd_buyer_warns_not_strong_fit(ranked_outdoor):
    fit = _fit_in_group(ranked_outdoor, "Outback", "fwd_outback_listing")

    assert any(NOT_AWD_WARNING in warning for warning in fit["warnings"])
    assert fit["fit_label"] != "Strong fit"


def test_good_awd_outback_for_awd_buyer_is_strong_fit(ranked_outdoor):
    fit = _fit_in_group(ranked_outdoor, "Outback", "good_awd_outback")

    assert fit["fit_label"] == "Strong fit"
    assert not any(NOT_AWD_WARNING in warning for warning in fit["warnings"])


def test_format_grouped_summary_handles_empty_and_populated_groups(ranked_student_sparse):
    demo = _load_demo_module()
    _, _, display_names = demo.load_sample_listings(STUDENT_LISTINGS_PATH)
    summary = demo.format_grouped_summary(
        ranked_student_sparse,
        display_names=display_names,
    )

    assert "Recommendation #3: Toyota Camry" in summary
    assert "  No matching listings found" in summary
    assert "2016 Toyota Corolla LE" in summary
    assert "good_corolla" not in summary


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("carlens_demo_listing_fit", DEMO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_missing_optional_fields_scoring_unit_warnings():
    recommendation = recommend("student")["recommendations"][0]
    buyer = _buyer("student")

    no_price = score_listing_fit(
        {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
            "mileage": 85000,
            "clean_title": True,
        },
        recommendation,
        buyer,
    )
    assert any(MISSING_PRICE_WARNING in warning for warning in no_price["warnings"])

    no_mileage = score_listing_fit(
        {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
            "price": 10500,
            "clean_title": True,
        },
        recommendation,
        buyer,
    )
    assert any(MISSING_MILEAGE_WARNING in warning for warning in no_mileage["warnings"])
