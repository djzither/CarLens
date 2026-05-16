import importlib.util
from pathlib import Path
from typing import Any

import pytest

from src.listings.listing_ranker import rank_listings_by_recommendation
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
DEMO_SCRIPT = PROJECT_ROOT / "Scripts" / "demo_listing_fit.py"

EXPECTED_LISTING_IDS = [
    "good_corolla",
    "budget_boundary_corolla",
    "over_budget_corolla",
    "dirty_title_corolla",
    "out_of_range_year_corolla",
    "high_mileage_corolla",
    "stacked_risk_corolla",
    "good_civic",
    "wrong_model_bmw",
]


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("carlens_demo_listing_fit", DEMO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_student_sample_listings_file_exists():
    assert SAMPLE_LISTINGS_PATH.is_file()


def test_student_sample_listings_has_expected_scenarios():
    demo = _load_demo_module()
    buyer_profile_id, scenarios = demo.load_sample_listings(SAMPLE_LISTINGS_PATH)

    assert buyer_profile_id == "student"
    assert [name for name, _ in scenarios] == EXPECTED_LISTING_IDS
    assert scenarios[0][1]["make"] == "Toyota"
    assert scenarios[0][1]["model"] == "Corolla"


def _ranked_student_listings() -> dict[str, Any]:
    demo = _load_demo_module()
    buyer_profile_id, scenarios = demo.load_sample_listings(SAMPLE_LISTINGS_PATH)
    buyer_data = load_buyer_profiles()
    buyer = demo._find_buyer(buyer_data["profiles"], buyer_profile_id)
    recommendations = recommend(buyer_profile_id)["recommendations"]
    return rank_listings_by_recommendation(scenarios, recommendations, buyer)


def _corolla_group(ranked: dict[str, Any]) -> dict[str, Any]:
    for group in ranked["groups"]:
        if group["model"] == "Corolla":
            return group
    raise AssertionError("Corolla group not found")


def _corolla_listing_names(ranked: dict[str, Any]) -> list[str]:
    return [entry["listing_name"] for entry in _corolla_group(ranked)["listings"]]


def _corolla_fit(ranked: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    for entry in _corolla_group(ranked)["listings"]:
        if entry["listing_name"] == scenario_id:
            return entry["fit"]
    raise AssertionError(f"scenario not in Corolla group: {scenario_id}")


def _civic_group(ranked: dict[str, Any]) -> dict[str, Any]:
    for group in ranked["groups"]:
        if group["model"] == "Civic":
            return group
    raise AssertionError("Civic group not found")


def _civic_fit(ranked: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    for entry in _civic_group(ranked)["listings"]:
        if entry["listing_name"] == scenario_id:
            return entry["fit"]
    raise AssertionError(f"scenario not in Civic group: {scenario_id}")


def _corolla_rank(ranked: dict[str, Any], scenario_id: str) -> int:
    return _corolla_listing_names(ranked).index(scenario_id) + 1


@pytest.fixture
def ranked_student_listings() -> dict[str, Any]:
    return _ranked_student_listings()


def test_good_corolla_ranks_above_over_budget_corolla(ranked_student_listings):
    assert _corolla_rank(ranked_student_listings, "good_corolla") < _corolla_rank(
        ranked_student_listings, "over_budget_corolla"
    )


def test_dirty_title_corolla_not_strong_fit_in_ranking(ranked_student_listings):
    fit = _corolla_fit(ranked_student_listings, "dirty_title_corolla")

    assert fit["fit_label"] != "Strong fit"
    assert any("clean title" in warning.lower() for warning in fit["warnings"])


def test_wrong_model_bmw_is_weak_fit_unmatched(ranked_student_listings):
    bmw = next(
        entry
        for entry in ranked_student_listings["unmatched_listings"]
        if entry["listing_name"] == "wrong_model_bmw"
    )

    assert bmw["fit"]["fit_label"] == "Weak fit"
    assert bmw["fit"]["fit_score"] == 0.0
    assert bmw["fit"]["reasons"] == []
    assert any(
        "does not match any recommended model" in warning
        for warning in bmw["fit"]["warnings"]
    )


def test_stacked_risk_corolla_ranks_below_clean_in_budget_corollas(ranked_student_listings):
    stacked_rank = _corolla_rank(ranked_student_listings, "stacked_risk_corolla")
    for scenario_id in ("good_corolla", "budget_boundary_corolla"):
        assert stacked_rank > _corolla_rank(ranked_student_listings, scenario_id)


def test_out_of_range_year_corolla_not_strong_fit_in_ranking(ranked_student_listings):
    fit = _corolla_fit(ranked_student_listings, "out_of_range_year_corolla")

    assert fit["fit_label"] != "Strong fit"
    assert fit["fit_label"] == "Moderate fit"
    assert any("outside the recommended" in warning for warning in fit["warnings"])


def test_good_civic_has_no_year_range_warning(ranked_student_listings):
    fit = _civic_fit(ranked_student_listings, "good_civic")

    assert not any("outside the recommended" in warning for warning in fit["warnings"])


def test_good_civic_remains_in_civic_group(ranked_student_listings):
    civic_names = [entry["listing_name"] for entry in _civic_group(ranked_student_listings)["listings"]]
    assert "good_civic" in civic_names


def test_budget_boundary_corolla_within_budget(ranked_student_listings):
    fit = _corolla_fit(ranked_student_listings, "budget_boundary_corolla")
    reasons_text = " ".join(fit["reasons"]).lower()
    warnings_text = " ".join(fit["warnings"]).lower()

    assert fit["fit_label"] == "Strong fit"
    assert "budget" in reasons_text
    assert "within" in reasons_text
    assert "exceeds" not in warnings_text


def test_format_grouped_summary_lists_groups_and_unmatched(ranked_student_listings):
    demo = _load_demo_module()
    summary = demo.format_grouped_summary(ranked_student_listings)

    assert "Recommendation #1:" in summary
    assert "Toyota Corolla" in summary
    assert "good_corolla" in summary
    assert "Unmatched listings:" in summary
    assert "wrong_model_bmw" in summary
