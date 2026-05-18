from pathlib import Path
from typing import Any

import pytest

from src.listings.listing_fit import score_listing_fit
from src.listings.listing_ranker import (
    COVERAGE_MESSAGE_NO_LISTINGS,
    rank_listings_by_recommendation,
)
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


_SPARSE_LISTING_IDS = frozenset({"good_camry", "good_mazda3", "good_outback"})


@pytest.fixture
def ranked_student() -> dict[str, Any]:
    buyer_profile_id, listings = _load_sample_listings()
    recommendations = recommend(buyer_profile_id)["recommendations"]
    return rank_listings_by_recommendation(listings, recommendations, _buyer(buyer_profile_id))


@pytest.fixture
def ranked_student_sparse() -> dict[str, Any]:
    buyer_profile_id, listings = _load_sample_listings()
    listings = [
        (name, listing) for name, listing in listings if name not in _SPARSE_LISTING_IDS
    ]
    recommendations = recommend(buyer_profile_id)["recommendations"]
    return rank_listings_by_recommendation(listings, recommendations, _buyer(buyer_profile_id))


def _group_by_model(ranked: dict[str, Any], model: str) -> dict[str, Any] | None:
    for group in ranked["groups"]:
        if group["model"] == model:
            return group
    return None


def _listing_names(group: dict[str, Any]) -> list[str]:
    return [entry["listing_name"] for entry in group["listings"]]


def _fit_by_name(ranked: dict[str, Any], listing_name: str) -> dict[str, Any]:
    for group in ranked["groups"]:
        for entry in group["listings"]:
            if entry["listing_name"] == listing_name:
                return entry["fit"]
    for entry in ranked["unmatched_listings"]:
        if entry["listing_name"] == listing_name:
            return entry["fit"]
    raise AssertionError(f"listing not found: {listing_name}")


def _rank_in_group(group: dict[str, Any], listing_name: str) -> int:
    return _listing_names(group).index(listing_name) + 1


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


def test_civic_listing_scored_against_civic_recommendation(ranked_student):
    fit = _fit_by_name(ranked_student, "good_civic")
    reasons_text = " ".join(fit["reasons"])

    assert "Honda Civic" in reasons_text
    assert "Toyota Corolla" not in reasons_text
    assert not any("not the recommended" in warning for warning in fit["warnings"])


def test_bmw_goes_into_unmatched_listings(ranked_student):
    unmatched_names = [
        entry["listing_name"] for entry in ranked_student["unmatched_listings"]
    ]
    assert "wrong_model_bmw" in unmatched_names


def test_unmatched_bmw_has_zero_fit_score(ranked_student):
    bmw = next(
        entry
        for entry in ranked_student["unmatched_listings"]
        if entry["listing_name"] == "wrong_model_bmw"
    )
    assert bmw["fit"]["fit_score"] == 0.0


def test_unmatched_bmw_has_no_reasons(ranked_student):
    bmw = next(
        entry
        for entry in ranked_student["unmatched_listings"]
        if entry["listing_name"] == "wrong_model_bmw"
    )
    assert bmw["fit"]["reasons"] == []


def test_unmatched_bmw_warning_does_not_match_any_recommended_model(ranked_student):
    bmw = next(
        entry
        for entry in ranked_student["unmatched_listings"]
        if entry["listing_name"] == "wrong_model_bmw"
    )
    assert bmw["fit"]["fit_label"] == "Weak fit"
    assert any(
        "does not match any recommended model" in warning
        for warning in bmw["fit"]["warnings"]
    )
    assert any("BMW 328i" in warning for warning in bmw["fit"]["warnings"])


def test_listings_inside_group_sorted_by_fit_score_descending(ranked_student):
    group = _group_by_model(ranked_student, "Corolla")
    assert group is not None
    scores = [entry["fit"]["fit_score"] for entry in group["listings"]]
    assert scores == sorted(scores, reverse=True)


def test_stacked_risk_corolla_is_weak_fit_and_below_good_corolla(ranked_student):
    group = _group_by_model(ranked_student, "Corolla")
    assert group is not None
    stacked_fit = _fit_by_name(ranked_student, "stacked_risk_corolla")

    assert stacked_fit["fit_label"] == "Weak fit"
    assert _rank_in_group(group, "stacked_risk_corolla") > _rank_in_group(
        group, "good_corolla"
    )


def test_group_order_follows_recommendation_order(ranked_student):
    recommendations = recommend("student")["recommendations"]
    ranks = [group["recommendation_rank"] for group in ranked_student["groups"]]

    assert ranks == sorted(ranks)
    assert len(ranked_student["groups"]) == len(recommendations)
    for group in ranked_student["groups"]:
        recommendation = recommendations[group["recommendation_rank"] - 1]
        assert group["make"] == recommendation["make"]
        assert group["model"] == recommendation["model"]
        assert group["recommendation"] == recommendation


def test_recommended_vehicle_with_no_matching_listings_appears_in_groups(
    ranked_student_sparse,
):
    group = _group_by_model(ranked_student_sparse, "Camry")
    assert group is not None
    assert group["make"] == "Toyota"


def test_empty_group_has_no_listings(ranked_student_sparse):
    group = _group_by_model(ranked_student_sparse, "Camry")
    assert group is not None
    assert group["listings"] == []


def test_empty_group_has_coverage_message(ranked_student_sparse):
    group = _group_by_model(ranked_student_sparse, "Camry")
    assert group is not None
    assert group["coverage_message"] == COVERAGE_MESSAGE_NO_LISTINGS


def test_malformed_listing_does_not_crash_ranker():
    buyer_profile_id, listings = _load_sample_listings()
    listings = [
        *listings,
        ("missing_fields", {"make": "Toyota", "model": "Corolla"}),
    ]
    recommendations = recommend(buyer_profile_id)["recommendations"]
    ranked = rank_listings_by_recommendation(
        listings, recommendations, _buyer(buyer_profile_id)
    )

    assert ranked["groups"]
    assert ranked["invalid_listings"]


def _corolla_recommendation() -> dict[str, Any]:
    return next(
        item
        for item in recommend("student")["recommendations"]
        if item["model"] == "Corolla"
    )


def _rank_toyota_listings(
    listings: list[tuple[str, dict[str, Any]]],
) -> list[str]:
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    ranked = rank_listings_by_recommendation(
        listings, [recommendation], buyer
    )
    group = _group_by_model(ranked, "Corolla")
    assert group is not None
    return _listing_names(group)


def test_equal_fit_score_fewer_warnings_ranks_higher():
    base = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    warning_heavy = {
        **base,
        "trim": "Unknown",
    }
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    clean_fit = score_listing_fit(base, recommendation, buyer)
    heavy_fit = score_listing_fit(warning_heavy, recommendation, buyer)

    assert clean_fit["fit_score"] == heavy_fit["fit_score"]
    assert len(heavy_fit["warnings"]) > len(clean_fit["warnings"])

    order = _rank_toyota_listings(
        [
            ("warning_heavy", warning_heavy),
            ("clean_listing", base),
        ]
    )
    assert order.index("clean_listing") < order.index("warning_heavy")


def test_equal_fit_score_lower_mileage_ranks_higher():
    listing_low = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 60000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    listing_high = {**listing_low, "mileage": 95000}
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    low_fit = score_listing_fit(listing_low, recommendation, buyer)
    high_fit = score_listing_fit(listing_high, recommendation, buyer)

    assert low_fit["fit_score"] == high_fit["fit_score"]

    order = _rank_toyota_listings(
        [
            ("high_mileage", listing_high),
            ("low_mileage", listing_low),
        ]
    )
    assert order.index("low_mileage") < order.index("high_mileage")


def test_equal_fit_score_lower_price_ranks_higher():
    listing_cheap = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 9000,
        "clean_title": True,
        "trim": "LE",
    }
    listing_dear = {**listing_cheap, "price": 11000}
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    cheap_fit = score_listing_fit(listing_cheap, recommendation, buyer)
    dear_fit = score_listing_fit(listing_dear, recommendation, buyer)

    assert cheap_fit["fit_score"] == dear_fit["fit_score"]
    assert cheap_fit["fit_label"] == dear_fit["fit_label"]
    assert len(cheap_fit["warnings"]) == len(dear_fit["warnings"])

    order = _rank_toyota_listings(
        [
            ("dear_listing", listing_dear),
            ("cheap_listing", listing_cheap),
        ]
    )
    assert order.index("cheap_listing") < order.index("dear_listing")


def test_missing_price_does_not_rank_above_clean_in_budget_listing():
    in_budget = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    missing_price = dict(in_budget)
    del missing_price["price"]

    order = _rank_toyota_listings(
        [
            ("missing_price", missing_price),
            ("in_budget", in_budget),
        ]
    )
    assert order.index("in_budget") < order.index("missing_price")


def test_ranking_order_is_deterministic_regardless_of_input_order():
    listings = [
        (
            "zebra",
            {
                "make": "Toyota",
                "model": "Corolla",
                "year": 2016,
                "mileage": 85000,
                "price": 10500,
                "clean_title": True,
                "trim": "LE",
            },
        ),
        (
            "alpha",
            {
                "make": "Toyota",
                "model": "Corolla",
                "year": 2016,
                "mileage": 85000,
                "price": 10500,
                "clean_title": True,
                "trim": "LE",
            },
        ),
    ]
    forward = _rank_toyota_listings(listings)
    reverse = _rank_toyota_listings(list(reversed(listings)))

    assert forward == reverse == ["alpha", "zebra"]


def test_malformed_listing_appears_in_invalid_listings():
    buyer_profile_id, listings = _load_sample_listings()
    listings = [("missing_year", {"make": "Toyota", "model": "Corolla", "price": 10000})]
    recommendations = recommend(buyer_profile_id)["recommendations"]
    ranked = rank_listings_by_recommendation(
        listings, recommendations, _buyer(buyer_profile_id)
    )

    assert len(ranked["invalid_listings"]) == 1
    invalid = ranked["invalid_listings"][0]
    assert invalid["listing_name"] == "missing_year"
    assert invalid["warnings"]
