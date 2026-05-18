import pytest

from src.listings.listing_fit import (
    MISSING_MILEAGE_WARNING,
    MISSING_PRICE_WARNING,
    MISSING_TITLE_WARNING,
    score_listing_fit,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend


def _buyer(profile_id: str) -> dict:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise AssertionError(f"profile not found: {profile_id}")


def _corolla_recommendation() -> dict:
    result = recommend("student")
    return next(
        item for item in result["recommendations"] if item["model"] == "Corolla"
    )


def _civic_recommendation_with_bad_years() -> dict:
    result = recommend("student")
    civic = next(
        item for item in result["recommendations"] if item["model"] == "Civic"
    )
    return {
        **civic,
        "selected_year_range": {
            "start_year": 2016,
            "end_year": 2021,
            "known_bad_years": [2016],
        },
    }


def test_good_corolla_listing_for_student_is_strong_fit():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 95000,
        "price": 11000,
        "clean_title": True,
        "trim": "LE",
        "location": "Boston, MA",
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] == "Strong fit"
    assert result["fit_score"] >= 0.75
    assert result["reasons"]
    assert not result["warnings"]


def test_over_budget_listing_gets_penalty_and_warning():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 95000,
        "price": 15000,
        "clean_title": True,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert any("exceeds" in warning.lower() for warning in result["warnings"])
    assert result["fit_score"] < 1.0


def test_known_bad_year_gets_warning():
    listing = {
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
        "mileage": 80000,
        "price": 10000,
        "clean_title": True,
    }
    result = score_listing_fit(
        listing, _civic_recommendation_with_bad_years(), _buyer("student")
    )

    assert any("known weak year" in warning.lower() for warning in result["warnings"])


def test_wrong_model_gets_weak_fit():
    listing = {
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
        "mileage": 95000,
        "price": 11000,
        "clean_title": True,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] == "Weak fit"
    assert result["fit_score"] < 0.50
    assert any("not the recommended" in warning for warning in result["warnings"])


def _bmw_listing() -> dict:
    return {
        "make": "BMW",
        "model": "328i",
        "year": 2015,
        "mileage": 90000,
        "price": 11000,
        "clean_title": True,
    }


def test_wrong_model_bmw_has_weak_fit():
    result = score_listing_fit(
        _bmw_listing(), _corolla_recommendation(), _buyer("student")
    )

    assert result["fit_label"] == "Weak fit"
    assert any("not the recommended" in warning for warning in result["warnings"])


def test_wrong_model_bmw_suppresses_positive_reasons():
    result = score_listing_fit(
        _bmw_listing(), _corolla_recommendation(), _buyer("student")
    )

    reasons_text = " ".join(result["reasons"]).lower()
    assert "year" not in reasons_text
    assert "budget" not in reasons_text
    assert "mileage" not in reasons_text


def test_out_of_range_year_corolla_cannot_be_strong_fit():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2009,
        "mileage": 85000,
        "price": 8000,
        "clean_title": True,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] != "Strong fit"
    assert result["fit_label"] == "Moderate fit"
    assert any("outside the recommended" in warning for warning in result["warnings"])


def test_dirty_title_corolla_cannot_be_strong_fit():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 95000,
        "price": 11000,
        "clean_title": False,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] != "Strong fit"
    assert result["fit_label"] == "Moderate fit"


def test_dirty_title_gets_warning():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 95000,
        "price": 11000,
        "clean_title": False,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert any("clean title" in warning.lower() for warning in result["warnings"])
    assert any("salvage" in warning.lower() for warning in result["warnings"])


def test_missing_year_range_does_not_lower_fit_score():
    recommendation = {
        "make": "Toyota",
        "model": "Corolla",
        "selected_year_range": None,
    }
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 11000,
        "mileage": 85000,
        "clean_title": True,
    }
    result = score_listing_fit(listing, recommendation, _buyer("student"))

    assert result["fit_label"] == "Strong fit"
    assert result["fit_score"] >= 0.75
    assert not any("year" in warning.lower() for warning in result["warnings"])
    assert not any("year" in reason.lower() for reason in result["reasons"])


def test_missing_optional_fields_does_not_crash():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 11000,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert "fit_score" in result
    assert "fit_label" in result
    assert isinstance(result["reasons"], list)
    assert isinstance(result["warnings"], list)


def test_missing_mileage_emits_warning():
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 11000,
        "clean_title": True,
    }
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert MISSING_MILEAGE_WARNING in result["warnings"]


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


def test_missing_mileage_scores_below_disclosed_good_mileage():
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    disclosed = score_listing_fit(_clean_corolla_listing(), recommendation, buyer)
    missing_listing = _clean_corolla_listing()
    del missing_listing["mileage"]
    missing = score_listing_fit(missing_listing, recommendation, buyer)

    assert MISSING_MILEAGE_WARNING in missing["warnings"]
    assert missing["fit_score"] < disclosed["fit_score"]
    assert any("mileage" in reason.lower() for reason in disclosed["reasons"])
    assert not any("mileage" in reason.lower() for reason in missing["reasons"])


def test_missing_mileage_produces_warning():
    listing = _clean_corolla_listing()
    del listing["mileage"]
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert MISSING_MILEAGE_WARNING in result["warnings"]


def test_missing_title_emits_warning():
    listing = _clean_corolla_listing()
    del listing["clean_title"]
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert MISSING_TITLE_WARNING in result["warnings"]
    assert result["fit_label"] != "Strong fit"


def test_missing_title_does_not_score_higher_than_dirty_title():
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    confirmed_clean = score_listing_fit(
        _clean_corolla_listing(),
        recommendation,
        buyer,
    )
    undisclosed_listing = _clean_corolla_listing()
    del undisclosed_listing["clean_title"]
    undisclosed = score_listing_fit(undisclosed_listing, recommendation, buyer)
    dirty = score_listing_fit(
        _clean_corolla_listing(clean_title=False),
        recommendation,
        buyer,
    )

    assert undisclosed["fit_score"] < confirmed_clean["fit_score"]
    assert undisclosed["fit_score"] <= dirty["fit_score"]


def test_severely_over_budget_is_weak_fit():
    listing = _clean_corolla_listing(price=25000)
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] == "Weak fit"
    assert any("exceeds" in warning.lower() for warning in result["warnings"])


def test_out_of_range_year_is_not_strong_fit():
    listing = _clean_corolla_listing(year=2009, price=8000)
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] != "Strong fit"
    assert any("outside the recommended" in warning for warning in result["warnings"])


def test_slight_mileage_overrun_is_not_strong_fit():
    listing = _clean_corolla_listing(mileage=131000)
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] != "Strong fit"
    assert any("exceeds" in warning.lower() for warning in result["warnings"])


def test_moderate_mileage_overrun_is_not_strong_fit():
    listing = _clean_corolla_listing(mileage=140000)
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] != "Strong fit"
    assert any("exceeds" in warning.lower() for warning in result["warnings"])


def test_severely_over_mileage_is_not_strong_fit():
    listing = _clean_corolla_listing(mileage=200000)
    result = score_listing_fit(listing, _corolla_recommendation(), _buyer("student"))

    assert result["fit_label"] != "Strong fit"
    assert any("exceeds" in warning.lower() for warning in result["warnings"])


def test_missing_price_scores_below_in_budget_listing():
    recommendation = _corolla_recommendation()
    buyer = _buyer("student")
    in_budget = score_listing_fit(_clean_corolla_listing(), recommendation, buyer)
    missing_listing = _clean_corolla_listing()
    del missing_listing["price"]
    missing = score_listing_fit(missing_listing, recommendation, buyer)

    assert MISSING_PRICE_WARNING in missing["warnings"]
    assert missing["fit_score"] < in_budget["fit_score"]
    assert any("price" in reason.lower() for reason in in_budget["reasons"])
    assert not any("price" in reason.lower() for reason in missing["reasons"])


def test_missing_price_is_not_strong_fit():
    missing_listing = _clean_corolla_listing()
    del missing_listing["price"]
    result = score_listing_fit(
        missing_listing, _corolla_recommendation(), _buyer("student")
    )

    assert result["fit_label"] != "Strong fit"
    assert any(
        "price was not provided" in warning.lower() for warning in result["warnings"]
    )
