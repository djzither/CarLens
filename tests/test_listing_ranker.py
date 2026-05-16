from pathlib import Path
from typing import Any

import pytest

from src.listings.listing_ranker import rank_listings_by_recommendation
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


def _load_sample_listings() -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    import json

    with SAMPLE_LISTINGS_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    listings = [(entry["id"], entry["listing"]) for entry in data["listings"]]
    return data["buyer_profile_id"], listings


def _buyer(profile_id: str) -> dict[str, Any]:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise AssertionError(f"profile not found: {profile_id}")


@pytest.fixture
def ranked_student() -> dict[str, Any]:
    buyer_profile_id, listings = _load_sample_listings()
    recommendations = recommend(buyer_profile_id)["recommendations"]
    return rank_listings_by_recommendation(listings, recommendations, _buyer(buyer_profile_id))


def _group_by_model(ranked: dict[str, Any], model: str) -> dict[str, Any] | None:
    for group in ranked["groups"]:
        if group["model"] == model:
            return group
    return None


def _listing_names(group: dict[str, Any]) -> list[str]:
    return [entry["listing_name"] for entry in group["listings"]]


def test_corolla_listing_goes_into_corolla_group(ranked_student):
    group = _group_by_model(ranked_student, "Corolla")
    assert group is not None
    assert group["make"] == "Toyota"
    assert "good_corolla" in _listing_names(group)


def test_civic_listing_goes_into_civic_group(ranked_student):
    group = _group_by_model(ranked_student, "Civic")
    assert group is not None
    assert group["make"] == "Honda"
    assert "good_civic" in _listing_names(group)


def test_bmw_goes_into_unmatched_listings(ranked_student):
    unmatched_names = [
        entry["listing_name"] for entry in ranked_student["unmatched_listings"]
    ]
    assert "wrong_model_bmw" in unmatched_names


def test_listings_inside_group_sorted_by_fit_score_descending(ranked_student):
    group = _group_by_model(ranked_student, "Corolla")
    assert group is not None
    scores = [entry["fit"]["fit_score"] for entry in group["listings"]]
    assert scores == sorted(scores, reverse=True)


def test_group_order_follows_recommendation_order(ranked_student):
    recommendations = recommend("student")["recommendations"]
    ranks = [group["recommendation_rank"] for group in ranked_student["groups"]]

    assert ranks == sorted(ranks)
    for group in ranked_student["groups"]:
        recommendation = recommendations[group["recommendation_rank"] - 1]
        assert group["make"] == recommendation["make"]
        assert group["model"] == recommendation["model"]


def test_unmatched_bmw_is_weak_fit(ranked_student):
    bmw = next(
        entry
        for entry in ranked_student["unmatched_listings"]
        if entry["listing_name"] == "wrong_model_bmw"
    )
    assert bmw["fit"]["fit_label"] == "Weak fit"
    assert any("not the recommended" in warning for warning in bmw["fit"]["warnings"])
