from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.listings.listing_confidence import assess_listing_confidence, detect_inferred_fields
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_fit import score_listing_fit
from src.listings.listing_ranker import rank_listings_for_recommendations
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADVERSARIAL_PATH = (
    PROJECT_ROOT / "data" / "sample_listings" / "adversarial_marketplace_demo.json"
)

ATTACK_CATEGORIES = frozenset(
    {
        "parser_attacks",
        "confidence_attacks",
        "title_status_attacks",
        "mileage_ambiguity",
        "awd_failures",
        "duplicate_listings",
        "sparse_listings",
        "misleading_text",
        "contradictory_signals",
    }
)


def _load_adversarial_data() -> dict[str, Any]:
    with ADVERSARIAL_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _load_adversarial_entries() -> list[dict[str, Any]]:
    return _load_adversarial_data()["listings"]


def _buyer(profile_id: str) -> dict[str, Any]:
    return next(
        profile
        for profile in load_buyer_profiles()["profiles"]
        if profile["id"] == profile_id
    )


def _recommendation_for(
    make: str,
    model: str,
    buyer_profile_id: str,
) -> dict[str, Any]:
    for item in recommend(buyer_profile_id)["recommendations"]:
        if item["make"] == make and item["model"] == model:
            return item
    return {
        "make": make,
        "model": model,
        "selected_year_range": {"start_year": 2014, "end_year": 2018},
    }


def _assess_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = _load_adversarial_data()
    buyer_profile_id = entry.get("buyer_profile_id", data["buyer_profile_id"])
    buyer = _buyer(buyer_profile_id)
    raw = entry["listing"]
    normalized = normalize_listing(raw)
    recommendation = _recommendation_for(
        normalized["make"],
        normalized["model"],
        buyer_profile_id,
    )
    fit = score_listing_fit(raw, recommendation, buyer)
    confidence = assess_listing_confidence(raw, normalized, fit=fit)
    return normalized, fit, confidence


@pytest.fixture(scope="module")
def adversarial_data() -> dict[str, Any]:
    return _load_adversarial_data()


def test_adversarial_marketplace_demo_file_exists():
    assert ADVERSARIAL_PATH.is_file()


def test_adversarial_attack_catalog_covers_required_categories(adversarial_data: dict):
    catalog = adversarial_data["attack_catalog"]
    assert ATTACK_CATEGORIES <= set(catalog.keys())


def test_adversarial_listing_entries_have_attack_category(adversarial_data: dict):
    for entry in adversarial_data["listings"]:
        assert entry["attack_category"] in ATTACK_CATEGORIES
        assert "expect" in entry


def test_adversarial_marketplace_demo_has_rich_listing_count():
    assert 25 <= len(_load_adversarial_entries()) <= 40


def test_adversarial_pipeline_dedupes_duplicates():
    data = _load_adversarial_data()
    buyer = _buyer(data["buyer_profile_id"])
    listings = [(entry["id"], entry["listing"]) for entry in data["listings"]]
    recommendations = recommend(data["buyer_profile_id"])["recommendations"]
    ranked = rank_listings_for_recommendations(listings, recommendations, buyer)

    assert ranked["pipeline"]["raw_count"] == len(listings)
    assert ranked["pipeline"]["deduped_count"] < ranked["pipeline"]["raw_count"]


@pytest.mark.parametrize("entry", _load_adversarial_entries(), ids=lambda item: item["id"])
def test_adversarial_listing_expectations(entry: dict[str, Any]):
    expect = entry["expect"]
    raw = entry["listing"]

    if expect.get("normalizes") is False:
        with pytest.raises(ValueError):
            normalize_listing(raw)
        return

    normalized, fit, confidence = _assess_entry(entry)

    if "year" in expect:
        assert normalized["year"] == expect["year"]
    if "price" in expect:
        assert normalized.get("price") == expect["price"]
    if "mileage" in expect:
        assert normalized.get("mileage") == expect["mileage"]
    if "clean_title" in expect:
        assert normalized.get("clean_title") is expect["clean_title"]

    if "confidence_level" in expect:
        assert confidence["confidence_level"] == expect["confidence_level"]
    if "confidence_in" in expect:
        assert confidence["confidence_level"] in expect["confidence_in"]
    if "ambiguity_detected" in expect:
        assert confidence["ambiguity_detected"] is expect["ambiguity_detected"]
    if "mileage_conflict_detected" in expect:
        assert (
            confidence["mileage_conflict_detected"]
            is expect["mileage_conflict_detected"]
        )
    if "fit_label" in expect:
        assert fit["fit_label"] == expect["fit_label"]
    if "warning_contains" in expect:
        needle = expect["warning_contains"]
        assert any(needle in warning for warning in fit.get("warnings", []))
    if "negative_contains" in expect:
        needle = expect["negative_contains"]
        assert any(needle in reason for reason in fit.get("negative_reasons", []))
    if "missing_fields_include" in expect:
        assert expect["missing_fields_include"] in confidence["missing_fields"]
    if "min_inferred_fields" in expect:
        inferred = detect_inferred_fields(raw, normalized)
        assert len(inferred) >= expect["min_inferred_fields"]


@pytest.mark.parametrize(
    "category",
    sorted(ATTACK_CATEGORIES),
)
def test_each_attack_category_has_listings(category: str, adversarial_data: dict):
    ids = [
        entry["id"]
        for entry in adversarial_data["listings"]
        if entry["attack_category"] == category
    ]
    assert ids, f"no listings for attack category {category!r}"
