"""Reality-hardening tests for Auto.dev fixtures (no live API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.listings.auto_dev_client import (
    iter_auto_dev_provider_rows,
    merge_auto_dev_page_payloads,
    parse_auto_dev_listings,
    resolve_fixture_payload,
)
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_source_adapter import adapt_auto_dev_listing
from src.listings.providers import AutoDevProvider, ListingSearchService, SearchFilters

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UGLY_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_ugly.json"
)

# VINs referenced in auto_dev_ugly.json
VIN_NO_YEAR = "UGLY01NOYEAR00001"
VIN_NO_PRICE = "UGLY02NOPRICE0002"
VIN_NO_MILES = "UGLY03NOMILES00003"
VIN_STR_PRICE = "UGLY04STRPRICE004"
VIN_STR_MILES = "UGLY05STRMILES005"
VIN_DUPLICATE = "DUPLICATEVIN123456"
VIN_BAD_TITLE = "UGLY07BADTITLE07"
VIN_NULL_NESTED = "UGLY08NULLNEST08"
VIN_GOOD = "UGLY09GOODLIST009"
VIN_PAGE_TWO = "UGLY10PAGE2LIST10"
VIN_DEAD_URL = "UGLY11DEADURL11"


@pytest.fixture
def ugly_payload() -> dict:
    with UGLY_FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def ugly_provider() -> AutoDevProvider:
    return AutoDevProvider(UGLY_FIXTURE, use_live_api=False)


def test_merge_combines_page_two_results(ugly_payload: dict) -> None:
    merged = resolve_fixture_payload(ugly_payload)
    vins = {row.get("vin") for row in iter_auto_dev_provider_rows(merged)}

    assert VIN_GOOD in vins
    assert VIN_PAGE_TWO in vins
    assert len(iter_auto_dev_provider_rows(merged)) == 18


def test_empty_page_merges_to_zero_rows(ugly_payload: dict) -> None:
    empty = ugly_payload["empty_page"]
    merged = merge_auto_dev_page_payloads([empty])

    assert merged["data"] == []


def test_malformed_values_do_not_crash_pipeline(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    assert isinstance(result.listings, list)
    assert isinstance(result.provider_warnings, list)


@pytest.mark.parametrize(
    ("vin", "expected_price", "expected_mileage"),
    [
        (VIN_STR_PRICE, 11500, 76000),
        (VIN_STR_MILES, 8900, 84000),
        (VIN_GOOD, 13900, 61000),
        (VIN_PAGE_TWO, 15200, 54000),
        (VIN_DEAD_URL, 5200, 145000),
    ],
)
def test_normalization_survives_ugly_strings(
    ugly_payload: dict,
    vin: str,
    expected_price: int,
    expected_mileage: int,
) -> None:
    merged = resolve_fixture_payload(ugly_payload)
    row = next(r for r in iter_auto_dev_provider_rows(merged) if r.get("vin") == vin)
    raw = adapt_auto_dev_listing(row)
    normalized = normalize_listing(raw)

    assert normalized["price"] == expected_price
    assert normalized["mileage"] == expected_mileage


def test_missing_year_row_skipped_with_validation_warning(
    ugly_provider: AutoDevProvider,
) -> None:
    result = ugly_provider.search(SearchFilters())
    returned_vins = {record["listing"].get("listing_id") for record in result.listings}

    assert VIN_NO_YEAR not in returned_vins
    assert any(VIN_NO_YEAR in warning and "skipped" in warning for warning in result.provider_warnings)


def test_missing_price_row_skipped(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    returned_vins = {record["listing"].get("listing_id") for record in result.listings}

    assert VIN_NO_PRICE not in returned_vins
    assert any(VIN_NO_PRICE in warning for warning in result.provider_warnings)


def test_missing_mileage_emits_optional_warning(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    record = next(r for r in result.listings if r["listing"].get("listing_id") == VIN_NO_MILES)

    assert record["listing"]["make"] == "Toyota"
    assert any(
        VIN_NO_MILES in warning and "missing optional mileage" in warning
        for warning in result.provider_warnings
    )


def test_null_nested_fields_do_not_crash(ugly_provider: AutoDevProvider) -> None:
    result = ugly_provider.search(SearchFilters())
    returned_vins = {record["listing"].get("listing_id") for record in result.listings}

    assert VIN_NULL_NESTED not in returned_vins
    assert any(VIN_NULL_NESTED in warning for warning in result.provider_warnings)


def test_malformed_title_row_still_normalizes(ugly_payload: dict) -> None:
    merged = resolve_fixture_payload(ugly_payload)
    row = next(r for r in iter_auto_dev_provider_rows(merged) if r.get("vin") == VIN_BAD_TITLE)
    normalized = normalize_listing(adapt_auto_dev_listing(row))

    assert normalized["year"] == 2011
    assert normalized["trim"] == "!!!UNKNOWN!!!"


def test_duplicate_vin_behavior_documented(ugly_provider: AutoDevProvider) -> None:
    """Provider search keeps duplicate VIN rows; aggregate search dedupes by provider id."""
    provider_result = ugly_provider.search(SearchFilters())
    duplicate_records = [
        record
        for record in provider_result.listings
        if record["provider_listing_id"] == VIN_DUPLICATE
    ]
    assert len(duplicate_records) == 2

    aggregate = ListingSearchService([ugly_provider]).search(SearchFilters())
    aggregate_duplicates = [
        record
        for record in aggregate.listings
        if record["provider_listing_id"] == VIN_DUPLICATE
    ]
    assert len(aggregate_duplicates) == 1


def test_aggregate_search_continues_when_sibling_provider_fails(
    ugly_provider: AutoDevProvider,
) -> None:
    class _BrokenProvider(AutoDevProvider):
        name = "broken"

        def search(self, filters: SearchFilters):
            raise RuntimeError("offline")

    service = ListingSearchService([_BrokenProvider(UGLY_FIXTURE), ugly_provider])
    result = service.search(SearchFilters())

    assert any("broken" in err for err in result.errors)
    assert any(record["listing"].get("listing_id") == VIN_GOOD for record in result.listings)


def test_parse_auto_dev_listings_never_raises_on_empty_page(ugly_payload: dict) -> None:
    rows = parse_auto_dev_listings(ugly_payload["empty_page"])
    assert rows == []
