"""Unit tests for listing_normalizer.py."""
from __future__ import annotations

from datetime import date

import pytest

from src.listings.listing_normalizer import (
    _mileage_from_text,
    detect_clean_title,
    extract_trim,
    extract_year_make_model,
    normalize_listing,
    parse_mileage,
    parse_price,
    sanitize_image_url,
)
from src.listings.listing_schema import CANONICAL_LISTING_FIELDS


# ---------------------------------------------------------------------------
# parse_price
# ---------------------------------------------------------------------------

def test_parse_price_integer_passthrough():
    assert parse_price(10500) == 10500

def test_parse_price_dollar_format():
    assert parse_price("$10,500") == 10500

def test_parse_price_plain_integer_string():
    assert parse_price("10500") == 10500

def test_parse_price_decimal_zero_cents():
    assert parse_price("$10,500.00") == 10500

def test_parse_price_decimal_plain_zero_cents():
    assert parse_price("10500.00") == 10500

def test_parse_price_nonzero_cents_returns_none():
    assert parse_price("$10,500.50") is None
    assert parse_price("10500.50") is None

def test_parse_price_negative_returns_none():
    assert parse_price(-100) is None

def test_parse_price_none_returns_none():
    assert parse_price(None) is None

def test_parse_price_bool_returns_none():
    assert parse_price(True) is None

def test_parse_price_empty_string_returns_none():
    assert parse_price("") is None

def test_parse_price_non_numeric_returns_none():
    assert parse_price("ask") is None

def test_parse_price_float_whole_number():
    assert parse_price(10500.0) == 10500


# ---------------------------------------------------------------------------
# parse_mileage
# ---------------------------------------------------------------------------

def test_parse_mileage_integer_passthrough():
    assert parse_mileage(92000) == 92000

def test_parse_mileage_k_suffix():
    assert parse_mileage("92k") == 92000

def test_parse_mileage_k_miles_suffix():
    assert parse_mileage("92k miles") == 92000

def test_parse_mileage_with_commas():
    assert parse_mileage("92,000 mi") == 92000

def test_parse_mileage_plain_integer_string():
    assert parse_mileage("92000") == 92000

def test_parse_mileage_none_returns_none():
    assert parse_mileage(None) is None

def test_parse_mileage_bool_returns_none():
    assert parse_mileage(False) is None

def test_parse_mileage_empty_string_returns_none():
    assert parse_mileage("") is None


# ---------------------------------------------------------------------------
# detect_clean_title
# ---------------------------------------------------------------------------

def test_detect_clean_title_clean_title_phrase():
    assert detect_clean_title("2016 Toyota Corolla clean title", None) is True

def test_detect_clean_title_clean_carfax_phrase():
    assert detect_clean_title(None, "clean carfax, one owner") is True

def test_detect_clean_title_clear_title_phrase():
    assert detect_clean_title("clear title, great car", None) is True

def test_detect_clean_title_salvage_title_is_dirty():
    assert detect_clean_title("2015 Honda Civic salvage title", None) is False

def test_detect_clean_title_rebuilt_title_is_dirty():
    assert detect_clean_title("rebuilt title", None) is False

def test_detect_clean_title_flood_damage_is_dirty():
    assert detect_clean_title("flood damage disclosed", None) is False

def test_detect_clean_title_lemon_law_is_dirty():
    assert detect_clean_title("lemon law buyback", None) is False

def test_detect_clean_title_branded_title_is_dirty():
    assert detect_clean_title("branded title vehicle", None) is False

# False-positive guards

def test_detect_clean_title_flood_lights_not_dirty():
    assert detect_clean_title("Has flood lights great car", None) is None

def test_detect_clean_title_lemon_yellow_not_dirty():
    assert detect_clean_title("Lemon yellow exterior", None) is None

def test_detect_clean_title_rebuilt_engine_with_clean_title():
    assert detect_clean_title("Rebuilt engine but clean title", None) is True

def test_detect_clean_title_no_salvage_history_not_dirty():
    assert detect_clean_title("No salvage history on this car", None) is None

def test_detect_clean_title_not_clean_title_is_dirty():
    assert detect_clean_title("not clean title", None) is False

def test_detect_clean_title_clean_title_no_is_dirty():
    assert detect_clean_title("clean title: no", None) is False

def test_detect_clean_title_no_flood_damage_not_dirty():
    assert detect_clean_title("no flood damage, clean carfax", None) is True

def test_detect_clean_title_empty_inputs_return_none():
    assert detect_clean_title(None, None) is None

def test_detect_clean_title_no_keywords_returns_none():
    assert detect_clean_title("2015 Toyota Corolla LE 92k miles", None) is None

def test_detect_clean_title_uses_description_when_title_absent():
    assert detect_clean_title(None, "clean title one owner") is True


# ---------------------------------------------------------------------------
# _mileage_from_text
# ---------------------------------------------------------------------------

def test_mileage_from_text_k_notation():
    assert _mileage_from_text("2015 Toyota Corolla 92k miles") == 92000

def test_mileage_from_text_miles_notation():
    assert _mileage_from_text("only 45,000 miles") == 45000

def test_mileage_from_text_miles_ago_returns_none():
    assert _mileage_from_text("brakes done 20000 miles ago") is None

def test_mileage_from_text_every_x_miles_returns_none():
    assert _mileage_from_text("oil change every 5000 miles") is None

def test_mileage_from_text_ambiguous_two_values_returns_none():
    assert _mileage_from_text("new engine at 100k, now at 45k") is None

def test_mileage_from_text_single_unambiguous_value():
    assert _mileage_from_text("low mileage 45k miles") == 45000

def test_mileage_from_text_no_mileage_returns_none():
    assert _mileage_from_text("2016 Toyota Corolla LE") is None


# ---------------------------------------------------------------------------
# normalize_listing — integration edge cases
# ---------------------------------------------------------------------------

def _base(**overrides) -> dict:
    base = {"make": "Toyota", "model": "Corolla", "year": 2016,
            "price": 10500, "mileage": 92000, "clean_title": True}
    base.update(overrides)
    return base


def test_normalize_year_as_mileage_is_rejected():
    assert "mileage" not in normalize_listing(_base(mileage=2016))

def test_normalize_mileage_below_minimum_is_rejected():
    assert "mileage" not in normalize_listing(_base(mileage=50))

def test_normalize_mileage_above_maximum_is_rejected():
    assert "mileage" not in normalize_listing(_base(mileage=600_000))

def test_normalize_plausible_mileage_stored():
    assert normalize_listing(_base(mileage=92000))["mileage"] == 92000

@pytest.mark.parametrize("mileage", [2016, "2016", "2016k", 600_000])
def test_normalize_drops_implausible_stored_mileage(mileage):
    assert "mileage" not in normalize_listing(_base(mileage=mileage))

@pytest.mark.parametrize(("mileage", "expected"), [(500, 500), (250_000, 250_000)])
def test_normalize_keeps_plausible_stored_mileage(mileage, expected):
    assert normalize_listing(_base(mileage=mileage))["mileage"] == expected

def test_normalize_year_out_of_range_raises():
    with pytest.raises(ValueError):
        normalize_listing(_base(year=1950))

def test_normalize_year_9999_raises():
    with pytest.raises(ValueError):
        normalize_listing(_base(year=9999))

def test_normalize_decimal_price_zero_cents_accepted():
    assert normalize_listing(_base(price="$10,500.00"))["price"] == 10500

def test_normalize_uppercase_make_canonicalized():
    assert normalize_listing(_base(make="TOYOTA"))["make"] == "Toyota"

def test_normalize_drive_type_lowercased():
    assert normalize_listing(_base(drive_type="AWD"))["drive_type"] == "awd"

def test_normalize_missing_make_raises():
    listing = _base(); del listing["make"]
    with pytest.raises((ValueError, KeyError)):
        normalize_listing(listing)

def test_normalize_missing_year_raises():
    with pytest.raises(ValueError):
        normalize_listing({"make": "Toyota", "model": "Corolla"})

def test_normalize_non_dict_raises():
    with pytest.raises(ValueError):
        normalize_listing("not a dict")

def test_normalize_allows_next_model_year():
    ny = date.today().year + 1
    assert normalize_listing(_base(year=ny))["year"] == ny

def test_normalize_rejects_year_before_1980():
    with pytest.raises(ValueError, match="listing.year must be between"):
        normalize_listing(_base(year=1979))

def test_normalize_rejects_far_future_year():
    with pytest.raises(ValueError, match="listing.year must be between"):
        normalize_listing(_base(year=date.today().year + 2))

def test_normalize_clean_title_true_stored():
    assert normalize_listing(_base(clean_title=True))["clean_title"] is True

def test_normalize_clean_title_false_stored():
    assert normalize_listing(_base(clean_title=False))["clean_title"] is False

def test_normalize_clean_title_inferred_from_title():
    listing = _base(); del listing["clean_title"]
    listing["title"] = "2016 Toyota Corolla clean title"
    assert normalize_listing(listing).get("clean_title") is True

def test_normalize_dirty_title_inferred_from_title():
    listing = _base(); del listing["clean_title"]
    listing["title"] = "2015 Toyota Corolla salvage title"
    assert normalize_listing(listing).get("clean_title") is False

def test_normalize_flood_lights_in_title_does_not_set_dirty():
    listing = _base(); del listing["clean_title"]
    listing["title"] = "2015 Toyota Corolla has flood lights"
    assert normalize_listing(listing).get("clean_title") is not False

@pytest.mark.parametrize("title", [
    "brakes done 20000 miles ago",
    "50k miles ago oil was changed",
    "oil change every 5000 miles",
])
def test_normalize_ignores_service_history_mileage_in_title(title):
    assert "mileage" not in normalize_listing(
        {"make": "Toyota", "model": "Corolla", "year": 2016, "title": title}
    )

@pytest.mark.parametrize("title", [
    "new engine at 100k, now at 45k",
    "Engine has 50k, car has 85,000 miles",
])
def test_normalize_ignores_ambiguous_mileage_in_title(title):
    assert "mileage" not in normalize_listing(
        {"make": "Toyota", "model": "Corolla", "year": 2016, "title": title}
    )

def test_normalize_extracts_single_mileage_from_title():
    result = normalize_listing(
        {"make": "Toyota", "model": "Corolla", "year": 2016,
         "title": "Toyota Corolla 85k miles"}
    )
    assert result["mileage"] == 85_000

@pytest.mark.parametrize("title", [
    "Price cut 2022! 2016 Toyota Corolla",
    "Updated 2023: 2016 Toyota Corolla",
    "2016 Toyota Corolla LE",
])
def test_extract_year_make_model_prefers_vehicle_year_near_make(title):
    e = extract_year_make_model(title)
    assert e["year"] == 2016
    assert e["make"] == "Toyota"
    assert e["model"] == "Corolla"

def test_normalize_marketplace_style_title_extraction():
    raw = {"listing_id": "abc123", "title": "2016 Toyota Corolla LE clean title 92k miles",
           "price": "$10,500", "source": "craigslist"}
    r = normalize_listing(raw)
    assert r["make"] == "Toyota"
    assert r["year"] == 2016
    assert r["price"] == 10500
    assert r["mileage"] == 92000
    assert r["clean_title"] is True

def test_extract_trim_corolla_le():
    assert extract_trim("2016 Toyota Corolla LE clean title", "Toyota", "Corolla") == "LE"

@pytest.mark.parametrize(
    ("image_url", "expected"),
    [
        ("https://photos.example/car.jpg", "https://photos.example/car.jpg"),
        ("http://photos.example/car.jpg", "http://photos.example/car.jpg"),
        ("javascript:alert(1)", None),
        ("data:image/png;base64,abc", None),
        ("file:///etc/passwd", None),
    ],
)
def test_sanitize_image_url_scheme(image_url, expected):
    assert sanitize_image_url(image_url) == expected


def test_normalize_drops_unsafe_image_url():
    listing = _base(image_url="javascript:alert(1)")
    assert "image_url" not in normalize_listing(listing)


def test_normalize_keeps_https_image_url():
    listing = _base(image_url="https://photos.example/car.jpg")
    assert normalize_listing(listing)["image_url"] == "https://photos.example/car.jpg"


def test_missing_helper_inputs_do_not_crash():
    assert parse_price("") is None
    assert parse_mileage("") is None
    assert extract_year_make_model("") == {"year": None, "make": None, "model": None}
    assert extract_trim("", "Toyota", "Corolla") is None
    assert detect_clean_title(None, None) is None
