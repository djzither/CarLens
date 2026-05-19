from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.listings.listing_fit import DIRTY_TITLE_WARNING, score_listing_fit
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_ranker import (
    COVERAGE_MESSAGE_NO_LISTINGS,
    rank_listings_by_recommendation,
    rank_listings_for_recommendations,
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


def test_listings_inside_group_sorted_by_fit_label_then_score(ranked_student):
    group = _group_by_model(ranked_student, "Corolla")
    assert group is not None
    label_rank = {"Strong fit": 0, "Moderate fit": 1, "Weak fit": 2}
    labels = [label_rank[entry["fit"]["fit_label"]] for entry in group["listings"]]
    assert labels == sorted(labels)


def test_strong_fit_never_ranks_below_moderate_fit():
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    strong_listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    moderate_listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 140000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    strong_fit = score_listing_fit(strong_listing, recommendation, buyer)
    moderate_fit = score_listing_fit(moderate_listing, recommendation, buyer)

    assert strong_fit["fit_label"] == "Strong fit"
    assert moderate_fit["fit_label"] == "Moderate fit"

    order = _rank_toyota_listings(
        [
            ("moderate_first", moderate_listing),
            ("strong_second", strong_listing),
        ]
    )
    assert order.index("strong_second") < order.index("moderate_first")


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


def test_missing_mileage_does_not_outrank_disclosed_over_limit():
    in_budget_over_limit = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 140000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    missing_mileage = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }

    order = _rank_toyota_listings(
        [
            ("missing_mileage", missing_mileage),
            ("over_limit", in_budget_over_limit),
        ]
    )
    assert order.index("over_limit") < order.index("missing_mileage")


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


def _rank_single_raw(
    raw_listing: dict[str, Any],
    *,
    listing_name: str = "raw_marketplace",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ranked = rank_listings_by_recommendation(
        [(listing_name, raw_listing)],
        [_corolla_recommendation()],
        _buyer("student"),
    )
    group = _group_by_model(ranked, "Corolla")
    assert group is not None
    assert len(group["listings"]) == 1
    entry = group["listings"][0]
    return ranked, entry["listing"], entry["fit"]


def test_raw_title_listing_ranks_under_corolla_group():
    raw = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
    }

    ranked, listing, fit = _rank_single_raw(raw, listing_name="raw_corolla_title")

    assert ranked["invalid_listings"] == []
    assert listing["make"] == "Toyota"
    assert listing["model"] == "Corolla"
    assert listing["year"] == 2016
    assert listing["trim"] == "LE"
    assert "Toyota Corolla" in " ".join(fit["reasons"])


def test_raw_price_string_scores_as_under_budget():
    raw = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
    }

    _, _, fit = _rank_single_raw(raw)

    assert "Under budget" in fit["positive_reasons"]
    assert any("within your" in reason.lower() for reason in fit["reasons"])


def test_raw_mileage_string_scores_as_mileage_ok():
    raw = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
    }

    _, listing, fit = _rank_single_raw(raw)

    assert listing["mileage"] == 92000
    assert "Mileage within preferred range" in fit["positive_reasons"]
    assert any("within your" in reason.lower() and "mile" in reason.lower() for reason in fit["reasons"])


def test_raw_dirty_title_listing_negative_reason_and_warning():
    raw = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "price": "$10,500",
        "description": "salvage title, runs and drives",
    }

    _, listing, fit = _rank_single_raw(raw, listing_name="raw_dirty_corolla")

    assert listing["clean_title"] is False
    assert "Dirty title" in fit["negative_reasons"]
    assert any(DIRTY_TITLE_WARNING in warning for warning in fit["warnings"])


def test_raw_listing_missing_optional_fields_does_not_crash_ranker():
    raw = {"title": "2016 Toyota Corolla LE"}

    ranked, listing, fit = _rank_single_raw(raw, listing_name="raw_minimal_corolla")

    assert ranked["invalid_listings"] == []
    assert listing["make"] == "Toyota"
    assert listing["model"] == "Corolla"
    assert listing["year"] == 2016
    assert "price" not in listing
    assert "mileage" not in listing
    assert any("price was not provided" in warning.lower() for warning in fit["warnings"])
    assert any("mileage not disclosed" in warning.lower() for warning in fit["warnings"])


def test_ranker_dedupes_duplicate_listing_urls():
    duplicate_url = "https://example.com/listing/abc123"
    sparse = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "listing_url": duplicate_url,
    }
    complete = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "listing_url": duplicate_url,
    }
    ranked = rank_listings_for_recommendations(
        [
            ("sparse_corolla", sparse),
            ("complete_corolla", complete),
        ],
        [_corolla_recommendation()],
        _buyer("student"),
    )

    group = _group_by_model(ranked, "Corolla")
    assert group is not None
    assert len(group["listings"]) == 1
    assert group["listings"][0]["listing_name"] == "complete_corolla"
    assert group["listings"][0]["listing"]["price"] == 10500


def test_duplicate_raw_listings_appear_once_in_ranked_output():
    duplicate_url = "https://example.com/listing/dup-once"
    first = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "listing_url": duplicate_url,
        "source": "craigslist",
        "listing_id": "dup-1",
    }
    second = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "listing_url": duplicate_url,
        "source": "craigslist",
        "listing_id": "dup-1",
    }
    ranked = rank_listings_for_recommendations(
        [("first", first), ("second", second)],
        [_corolla_recommendation()],
        _buyer("student"),
    )

    group = _group_by_model(ranked, "Corolla")
    assert group is not None
    assert len(group["listings"]) == 1
    assert ranked["pipeline"]["raw_count"] == 2
    assert ranked["pipeline"]["deduped_count"] == 1


def test_duplicate_keeps_most_complete_version_in_ranked_output():
    duplicate_url = "https://example.com/listing/complete-wins"
    sparse = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "listing_url": duplicate_url,
    }
    complete = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "clean_title": True,
        "listing_url": duplicate_url,
    }
    ranked = rank_listings_for_recommendations(
        [("sparse", sparse), ("complete", complete)],
        [_corolla_recommendation()],
        _buyer("student"),
    )

    listing = _group_by_model(ranked, "Corolla")["listings"][0]["listing"]
    assert listing["price"] == 10500
    assert listing["clean_title"] is True
    assert listing["mileage"] == 92000


@patch("src.listings.listing_ranker.score_listing_fit", wraps=score_listing_fit)
def test_dedupe_happens_before_ranking(mock_score_listing_fit):
    duplicate_url = "https://example.com/listing/score-once"
    sparse = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "listing_url": duplicate_url,
    }
    complete = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "listing_url": duplicate_url,
    }
    rank_listings_for_recommendations(
        [("sparse", sparse), ("complete", complete)],
        [_corolla_recommendation()],
        _buyer("student"),
    )

    assert mock_score_listing_fit.call_count == 1


def test_structured_reasons_after_normalization_and_dedupe():
    duplicate_url = "https://example.com/listing/reasons"
    sparse = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "listing_url": duplicate_url,
    }
    complete = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "listing_url": duplicate_url,
    }
    ranked = rank_listings_for_recommendations(
        [("sparse", sparse), ("complete", complete)],
        [_corolla_recommendation()],
        _buyer("student"),
    )

    fit = _group_by_model(ranked, "Corolla")["listings"][0]["fit"]
    assert "Strong model match" in fit["positive_reasons"]
    assert "Under budget" in fit["positive_reasons"]
    assert fit["negative_reasons"] == []
    assert any("Toyota Corolla" in reason for reason in fit["reasons"])


def test_marketplace_metadata_preserved_in_ranked_output():
    raw = {
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "source": "craigslist",
        "listing_id": "cl-12345",
        "listing_url": "https://example.com/listing/cl-12345",
    }

    _, listing, _ = _rank_single_raw(raw, listing_name="marketplace_corolla")

    assert listing["source"] == "craigslist"
    assert listing["listing_id"] == "cl-12345"
    assert listing["listing_url"] == "https://example.com/listing/cl-12345"
    assert listing["raw_title"] == raw["title"]


def test_canonical_listing_preserved_in_ranked_output():
    structured = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    expected = normalize_listing(structured)

    _, listing, _ = _rank_single_raw(structured, listing_name="canonical_corolla")

    assert listing == expected


def test_title_only_listing_low_confidence_through_ranker():
    """Ranker must pass original raw listing into confidence assessment."""
    buyer_profile_id, _ = _load_sample_listings()
    buyer = _buyer(buyer_profile_id)
    recommendations = recommend(buyer_profile_id)["recommendations"]
    corolla_rec = next(
        rec
        for rec in recommendations
        if rec["make"] == "Toyota" and rec["model"] == "Corolla"
    )

    ranked = rank_listings_for_recommendations(
        [
            (
                "title_only_corolla",
                {
                    "title": "2016 Toyota Corolla LE 92k miles",
                    "listing_url": "https://example.com/sparse",
                },
            )
        ],
        [corolla_rec],
        buyer,
    )

    corolla_group = next(
        group
        for group in ranked["groups"]
        if group["make"] == "Toyota" and group["model"] == "Corolla"
    )
    assert corolla_group["listings"]
    assert corolla_group["listings"][0]["fit"]["confidence_level"] == "Low"
