"""Tests for Auto.dev adapter field normalization helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.listings.auto_dev_adapter import (
    _optional_location,
    _optional_mileage,
    _optional_price,
    _optional_year,
    adapt_auto_dev_listing,
    pop_adapter_warnings,
)
from src.listings.auto_dev_client import iter_auto_dev_provider_rows, resolve_fixture_payload
from src.listings.listing_normalizer import normalize_listing
from src.listings.providers import AutoDevProvider, ListingSearchService, SearchFilters

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UGLY_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_ugly.json"
)

VIN_BAD_PRICE = "ADPT01BADPRICE1"
VIN_YEAR_RANGE = "ADPT02YEARRANGE2"
VIN_WHOLESALE = "ADPT03WHOLESALE3"
VIN_BAD_MILES = "ADPT04BADMILES4"
VIN_EMPTY_RETAIL = "ADPT05EMPTYRETAIL5"
VIN_BAD_LOCATION = "ADPT06BADLOCAT6"
VIN_GOOD = "UGLY09GOODLIST009"


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        (11500, 11500, False),
        ("11,500", 11500, False),
        ("$11,500", 11500, False),
        ("11,500 USD", None, True),
    ],
)
def test_optional_price(value, expected, expect_warning) -> None:
    parsed, warnings = _optional_price(value)

    assert parsed == expected
    if expect_warning:
        assert len(warnings) == 1
        assert warnings[0] == f"Invalid price value: {value!r}"
    else:
        assert warnings == []


@pytest.mark.parametrize(
    ("value", "expected", "expect_warning"),
    [
        ("84,000 mi", 84000, False),
        ("84000", 84000, False),
        ("unknown miles", None, True),
    ],
)
def test_optional_mileage(value, expected, expect_warning) -> None:
    parsed, warnings = _optional_mileage(value)

    assert parsed == expected
    if expect_warning:
        assert warnings[0] == f"Invalid mileage value: {value!r}"
    else:
        assert warnings == []


def test_optional_year_accepts_range_first_year() -> None:
    parsed, warnings = _optional_year("2015-2016")

    assert parsed == 2015
    assert warnings == []


def test_optional_year_invalid_emits_warning() -> None:
    parsed, warnings = _optional_year("not-a-year")

    assert parsed is None
    assert warnings == ["Invalid year value: 'not-a-year'"]


@pytest.mark.parametrize(
    "value",
    ["USA", "Dealer Online", "00000"],
)
def test_optional_location_rejects_placeholders(value: str) -> None:
    parsed, warnings = _optional_location(value)

    assert parsed is None
    assert warnings == [f"Invalid location value: {value!r}"]


def test_adapt_coerces_year_range_and_wholesale_mileage() -> None:
    with UGLY_FIXTURE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    merged = resolve_fixture_payload(payload)
    year_row = next(r for r in iter_auto_dev_provider_rows(merged) if r.get("vin") == VIN_YEAR_RANGE)
    wholesale_row = next(
        r for r in iter_auto_dev_provider_rows(merged) if r.get("vin") == VIN_WHOLESALE
    )

    year_raw = adapt_auto_dev_listing(year_row)
    wholesale_raw = adapt_auto_dev_listing(wholesale_row)

    assert year_raw["year"] == 2015
    assert wholesale_raw["mileage"] == 55000
    assert pop_adapter_warnings(year_raw) == []
    assert pop_adapter_warnings(wholesale_raw) == []


def test_malformed_values_create_adapter_warnings(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    joined = "\n".join(result.provider_warnings)

    assert f"{VIN_BAD_PRICE}: Invalid price value: '11,500 USD'" in joined
    assert f"{VIN_BAD_MILES}: Invalid mileage value: 'unknown miles'" in joined
    assert "Invalid location value: 'Dealer Online'" in joined


def test_invalid_price_not_silently_dropped(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    returned = {record["listing"].get("listing_id") for record in result.listings}

    assert VIN_BAD_PRICE not in returned
    assert any(VIN_BAD_PRICE in warning and "Invalid price value" in warning for warning in result.provider_warnings)
    assert any(VIN_BAD_PRICE in warning and "skipped" in warning for warning in result.provider_warnings)


def test_year_range_listing_survives_normalization(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    record = next(r for r in result.listings if r["listing"].get("listing_id") == VIN_YEAR_RANGE)

    normalized = normalize_listing(record["listing"])
    assert normalized["year"] == 2015
    assert normalized["price"] == 14000


def test_aggregate_search_returns_results_with_adapter_warnings() -> None:
    provider = AutoDevProvider(UGLY_FIXTURE, use_live_api=False)
    result = ListingSearchService([provider]).search(SearchFilters())

    assert any(record["listing"].get("listing_id") == VIN_GOOD for record in result.listings)
    assert any("Invalid price value" in warning for warning in result.provider_warnings)


def test_every_non_result_row_has_warning(ugly_provider: AutoDevProvider) -> None:
    with UGLY_FIXTURE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    all_vins = {row.get("vin") for row in iter_auto_dev_provider_rows(resolve_fixture_payload(payload))}

    result = ugly_provider.search(SearchFilters())
    returned = {record["listing"].get("listing_id") for record in result.listings}
    missing = all_vins - returned

    warned_vins = {
        vin
        for vin in missing
        if any(vin in warning for warning in result.provider_warnings)
    }
    assert warned_vins == missing


@pytest.fixture
def ugly_provider() -> AutoDevProvider:
    return AutoDevProvider(UGLY_FIXTURE, use_live_api=False)
