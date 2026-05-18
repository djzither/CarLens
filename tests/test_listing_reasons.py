from src.listings.listing_fit import score_listing_fit
from src.listings.listing_reasons import build_listing_reasons
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend


def _buyer(profile_id: str) -> dict:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise AssertionError(f"profile not found: {profile_id}")


def _corolla_recommendation() -> dict:
    return next(
        item
        for item in recommend("student")["recommendations"]
        if item["model"] == "Corolla"
    )


def _civic_recommendation() -> dict:
    return next(
        item
        for item in recommend("student")["recommendations"]
        if item["model"] == "Civic"
    )


def _clean_corolla_listing(**overrides) -> dict:
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }
    listing.update(overrides)
    return listing


def test_strong_listing_positive_reasons_ordered():
    reasons = build_listing_reasons(
        _clean_corolla_listing(),
        _buyer("student"),
        _corolla_recommendation(),
    )

    assert reasons["positive_reasons"] == [
        "Strong model match",
        "Within recommended year range",
        "Under budget",
        "Mileage within preferred range",
    ]
    assert reasons["negative_reasons"] == []


def test_wrong_model_dominates_and_suppresses_positives():
    listing = {
        "make": "BMW",
        "model": "328i",
        "year": 2015,
        "mileage": 90000,
        "price": 11000,
        "clean_title": True,
    }
    recommendation = _corolla_recommendation()
    reasons = build_listing_reasons(listing, _buyer("student"), recommendation)

    assert reasons["positive_reasons"] == []
    assert reasons["negative_reasons"][0] == "Not the recommended Toyota Corolla"
    assert len(reasons["negative_reasons"]) == 1


def test_dirty_title_and_known_bad_year_near_top_of_negatives():
    listing = {
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
        "mileage": 80000,
        "price": 10000,
        "clean_title": False,
    }
    reasons = build_listing_reasons(
        listing, _buyer("student"), _civic_recommendation()
    )

    assert reasons["negative_reasons"][:2] == [
        "Dirty title",
        "Known problematic model year",
    ]
    assert "Strong model match" in reasons["positive_reasons"]
    assert "Within recommended year range" not in reasons["positive_reasons"]


def test_over_budget_negative_includes_amount():
    reasons = build_listing_reasons(
        _clean_corolla_listing(price=15000),
        _buyer("student"),
        _corolla_recommendation(),
    )

    assert "Over budget by $3,000" in reasons["negative_reasons"]
    assert "Under budget" not in reasons["positive_reasons"]


def test_over_mileage_negative_includes_amount():
    reasons = build_listing_reasons(
        _clean_corolla_listing(mileage=140000),
        _buyer("student"),
        _corolla_recommendation(),
    )

    assert "Mileage exceeds preferred max by 10,000" in reasons["negative_reasons"]
    assert "Mileage within preferred range" not in reasons["positive_reasons"]


def test_year_outside_range_suppresses_within_range_positive():
    reasons = build_listing_reasons(
        _clean_corolla_listing(year=2009, price=8000),
        _buyer("student"),
        _corolla_recommendation(),
    )

    assert "Year outside recommended range" in reasons["negative_reasons"]
    assert "Within recommended year range" not in reasons["positive_reasons"]


def test_score_listing_fit_includes_structured_reasons():
    result = score_listing_fit(
        _clean_corolla_listing(),
        _corolla_recommendation(),
        _buyer("student"),
    )

    assert "positive_reasons" in result
    assert "negative_reasons" in result
    assert result["positive_reasons"][0] == "Strong model match"


def test_awd_listing_includes_matches_requested_awd_positive():
    recommendation = next(
        item
        for item in recommend("outdoor_snow")["recommendations"]
        if item["model"] == "Outback"
    )
    listing = {
        "make": "Subaru",
        "model": "Outback",
        "year": 2016,
        "mileage": 90000,
        "price": 19000,
        "clean_title": True,
        "drive_type": "awd",
    }
    reasons = build_listing_reasons(
        listing, _buyer("outdoor_snow"), recommendation
    )

    assert "Matches requested AWD" in reasons["positive_reasons"]


def test_known_bad_year_from_vehicle_profile_when_selected_range_differs():
    recommendation = {
        **_civic_recommendation(),
        "selected_year_range": {
            "start_year": 2012,
            "end_year": 2015,
            "known_bad_years": [],
        },
    }
    listing = {
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
        "mileage": 80000,
        "price": 10000,
        "clean_title": True,
    }
    reasons = build_listing_reasons(listing, _buyer("student"), recommendation)

    assert "Known problematic model year" in reasons["negative_reasons"]
    assert "Year outside recommended range" in reasons["negative_reasons"]
