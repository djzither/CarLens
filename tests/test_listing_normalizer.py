import pytest

from src.listings.listing_normalizer import (
    detect_clean_title,
    extract_trim,
    extract_year_make_model,
    normalize_listing,
    parse_mileage,
    parse_price,
)
from src.listings.listing_schema import CANONICAL_LISTING_FIELDS


def test_parse_price_dollar_format():
    assert parse_price("$10,500") == 10500


def test_parse_price_comma_format():
    assert parse_price("10,500") == 10500


def test_parse_price_plain_integer_string():
    assert parse_price("10500") == 10500


def test_parse_price_none_returns_none():
    assert parse_price(None) is None


def test_parse_mileage_k_abbreviation():
    assert parse_mileage("92k miles") == 92000


def test_parse_mileage_with_commas():
    assert parse_mileage("92,000 mi") == 92000


def test_parse_mileage_plain_integer():
    assert parse_mileage("92000") == 92000


def test_detect_clean_title_positive():
    assert detect_clean_title("2016 Toyota Corolla LE clean title 92k miles", None) is True


def test_detect_clean_title_salvage_title_is_dirty():
    assert detect_clean_title("2016 Corolla", "salvage title, runs great") is False


def test_detect_clean_title_rebuilt_title_is_dirty():
    assert detect_clean_title("rebuilt title", "one owner") is False


def test_detect_clean_title_flood_damage_is_dirty():
    assert detect_clean_title("flood damage disclosed", None) is False


def test_flood_lights_not_dirty():
    assert detect_clean_title("Has flood lights great car", None) is None


def test_lemon_color_not_dirty():
    assert detect_clean_title("Lemon yellow exterior", None) is None


def test_rebuilt_engine_with_clean_title_remains_clean():
    assert (
        detect_clean_title("Rebuilt engine, clean title", "Runs great")
        is True
    )


def test_no_salvage_history_not_dirty():
    assert detect_clean_title("No salvage history", "Well maintained") is None


def test_extract_trim_corolla_le():
    title = "2016 Toyota Corolla LE clean title 92k miles"
    assert extract_trim(title, "Toyota", "Corolla") == "LE"


def test_extract_year_make_model_from_title():
    extracted = extract_year_make_model("2016 Toyota Corolla LE clean title 92k miles")

    assert extracted == {"year": 2016, "make": "Toyota", "model": "Corolla"}


def test_missing_helper_inputs_return_none_without_crashing():
    assert parse_price("") is None
    assert parse_mileage("") is None
    assert extract_year_make_model("") == {"year": None, "make": None, "model": None}
    assert extract_trim("", "Toyota", "Corolla") is None
    assert detect_clean_title(None, None) is None


def test_normalize_listing_marketplace_style_output():
    raw = {
        "listing_id": "abc123",
        "title": "2016 Toyota Corolla LE clean title 92k miles",
        "price": "$10,500",
        "source": "craigslist",
        "listing_url": "https://example.com/listing/abc123",
    }

    result = normalize_listing(raw)

    assert result["make"] == "Toyota"
    assert result["model"] == "Corolla"
    assert result["year"] == 2016
    assert result["price"] == 10500
    assert result["mileage"] == 92000
    assert result["trim"] == "LE"
    assert result["clean_title"] is True
    assert result["listing_id"] == "abc123"
    assert result["source"] == "craigslist"
    assert result["listing_url"] == "https://example.com/listing/abc123"
    assert result["raw_title"] == raw["title"]

    expected_fields = {
        "listing_id",
        "make",
        "model",
        "year",
        "price",
        "mileage",
        "trim",
        "clean_title",
        "source",
        "listing_url",
        "raw_title",
    }
    assert expected_fields.issubset(result.keys())
    assert set(result.keys()).issubset(set(CANONICAL_LISTING_FIELDS) | {"location"})


def test_normalize_listing_structured_input_unchanged_for_scoring_fields():
    structured = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "trim": "LE",
    }

    result = normalize_listing(structured)

    assert result == structured


def test_normalize_listing_omits_unresolved_optionals():
    result = normalize_listing(
        {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
        }
    )

    assert "price" not in result
    assert "mileage" not in result
    assert "clean_title" not in result


def test_normalize_listing_requires_make_and_model():
    with pytest.raises(ValueError, match="make and listing.model"):
        normalize_listing({"title": "2016 sedan", "year": 2016})


def test_normalize_listing_requires_year():
    with pytest.raises(ValueError, match="missing fields"):
        normalize_listing({"make": "Toyota", "model": "Corolla"})
