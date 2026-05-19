"""Tests for the mock listing provider (phase 1 API-ready abstraction)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.listings.providers import MockListingProvider, SearchFilters

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDENT_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


@pytest.fixture
def provider() -> MockListingProvider:
    return MockListingProvider(STUDENT_LISTINGS_PATH)


def _listing(entry: dict) -> dict:
    return entry["listing"]


def _ids(result_listings: list[dict]) -> set[str]:
    return {entry["id"] for entry in result_listings}


def test_returns_corolla_listings(provider: MockListingProvider) -> None:
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    assert result.listings
    assert result.provider_name == "mock"
    assert all(
        _normalize(_listing(entry).get("make")) == "toyota"
        and _normalize(_listing(entry).get("model")) == "corolla"
        for entry in result.listings
    )


def test_filters_out_wrong_make_model(provider: MockListingProvider) -> None:
    corollas = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    civics = provider.search(SearchFilters(make="Honda", model="Civic"))
    corolla_ids = _ids(corollas.listings)
    civic_ids = _ids(civics.listings)
    assert corolla_ids.isdisjoint(civic_ids)
    assert "good_corolla" in corolla_ids
    assert "good_civic" in civic_ids
    assert "good_corolla" not in civic_ids


def test_respects_max_price(provider: MockListingProvider) -> None:
    result = provider.search(
        SearchFilters(make="Toyota", model="Corolla", max_price=12000)
    )
    ids = _ids(result.listings)
    assert "over_budget_corolla" not in ids
    assert "good_corolla" in ids
    for entry in result.listings:
        price = _listing(entry).get("price")
        if price is not None:
            assert float(price) <= 12000


def test_respects_year_range(provider: MockListingProvider) -> None:
    result = provider.search(
        SearchFilters(make="Toyota", model="Corolla", min_year=2015, max_year=2016)
    )
    ids = _ids(result.listings)
    assert "out_of_range_year_corolla" not in ids
    assert "good_corolla" in ids
    for entry in result.listings:
        year = _listing(entry).get("year")
        assert year is not None
        assert 2015 <= int(year) <= 2016


def test_missing_mileage_does_not_crash(provider: MockListingProvider) -> None:
    result = provider.search(
        SearchFilters(make="Toyota", model="Corolla", max_mileage=200_000)
    )
    assert "missing_mileage_corolla" in _ids(result.listings)


def test_missing_clean_title_not_excluded_when_clean_title_only(
    provider: MockListingProvider,
) -> None:
    provider._entries.append(
        {
            "id": "unknown_clean_title_corolla",
            "listing": {
                "make": "Toyota",
                "model": "Corolla",
                "year": 2016,
                "price": 9999,
            },
        }
    )
    result = provider.search(
        SearchFilters(make="Toyota", model="Corolla", clean_title_only=True)
    )
    assert "unknown_clean_title_corolla" in _ids(result.listings)


def test_dirty_title_excluded_when_clean_title_only(
    provider: MockListingProvider,
) -> None:
    result = provider.search(
        SearchFilters(make="Toyota", model="Corolla", clean_title_only=True)
    )
    ids = _ids(result.listings)
    assert "dirty_title_corolla" not in ids
    assert "good_corolla" in ids


def test_salvage_title_status_excluded_when_clean_title_only(
    provider: MockListingProvider,
) -> None:
    provider._entries.append(
        {
            "id": "salvage_status_corolla",
            "listing": {
                "make": "Toyota",
                "model": "Corolla",
                "year": 2016,
                "price": 9500,
                "title_status": "salvage",
            },
        }
    )
    result = provider.search(
        SearchFilters(make="Toyota", model="Corolla", clean_title_only=True)
    )
    assert "salvage_status_corolla" not in _ids(result.listings)


def test_invalid_listing_skipped_and_records_warning(
    provider: MockListingProvider,
) -> None:
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    assert "missing_price_corolla" not in _ids(result.listings)
    assert any("missing_price_corolla" in w for w in result.provider_warnings)
    assert any("skipped" in w and "price" in w for w in result.provider_warnings)


def test_missing_required_fields_skipped(provider: MockListingProvider) -> None:
    provider._entries.append(
        {
            "id": "no_year_listing",
            "listing": {"make": "Toyota", "model": "Corolla", "price": 9000},
        }
    )
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    assert "no_year_listing" not in _ids(result.listings)
    assert any("no_year_listing" in w and "skipped" in w for w in result.provider_warnings)


def test_valid_listings_return_when_invalid_exist(provider: MockListingProvider) -> None:
    provider._entries.append(
        {
            "id": "broken_listing",
            "listing": {"make": "Toyota", "model": "Corolla"},
        }
    )
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    assert "good_corolla" in _ids(result.listings)
    assert len(result.listings) >= 10
    assert any("broken_listing" in w for w in result.provider_warnings)


def test_incomplete_valid_listing_emits_optional_warnings(
    provider: MockListingProvider,
) -> None:
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    assert "missing_mileage_corolla" in _ids(result.listings)
    assert any(
        "missing_mileage_corolla" in w and "mileage" in w
        for w in result.provider_warnings
    )


def test_provenance_on_valid_listings_when_invalid_exist(
    provider: MockListingProvider,
) -> None:
    provider._entries.append(
        {
            "id": "no_price_listing",
            "listing": {"make": "Toyota", "model": "Corolla", "year": 2016},
        }
    )
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    entry = next(e for e in result.listings if e["id"] == "good_corolla")
    assert entry["provider_name"] == "mock"
    assert entry["provider_listing_id"] == "good_corolla"
    assert entry["provider_raw_fields"]


def test_validate_listing_requires_id_and_core_fields(
    provider: MockListingProvider,
) -> None:
    ok, errors = provider.validate_listing(
        {
            "id": "x",
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
            "price": 10000,
        }
    )
    assert ok
    assert errors == []

    bad, errors = provider.validate_listing({"make": "Toyota", "model": "Corolla"})
    assert not bad
    assert any("id" in err for err in errors)
    assert any("year" in err for err in errors)
    assert any("price" in err for err in errors)


def test_get_by_id_returns_entry(provider: MockListingProvider) -> None:
    entry = provider.get_by_id("good_corolla")
    assert entry is not None
    assert entry["id"] == "good_corolla"
    assert provider.get_by_id("missing_price_corolla") is None


def test_search_attaches_provenance_metadata(provider: MockListingProvider) -> None:
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    entry = next(e for e in result.listings if e["id"] == "good_corolla")
    listing = _listing(entry)

    assert entry["provider_name"] == "mock"
    assert entry["provider_listing_id"] == "good_corolla"
    assert "provider_url" not in entry
    assert isinstance(entry["provider_raw_fields"], list)
    assert "make" in entry["provider_raw_fields"]
    assert "price" in entry["provider_raw_fields"]
    assert "mileage" in entry["provider_raw_fields"]
    assert all(listing.get(field) is not None for field in entry["provider_raw_fields"])


def test_provenance_includes_provider_url_when_present(
    provider: MockListingProvider,
) -> None:
    provider._entries.append(
        {
            "id": "url_corolla",
            "listing": {
                "make": "Toyota",
                "model": "Corolla",
                "year": 2016,
                "price": 10000,
                "listing_url": "https://example.com/listings/url-corolla",
            },
        }
    )
    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))
    entry = next(e for e in result.listings if e["id"] == "url_corolla")
    assert entry["provider_url"] == "https://example.com/listings/url-corolla"
    assert "listing_url" in entry["provider_raw_fields"]


def test_get_by_id_includes_provenance(provider: MockListingProvider) -> None:
    entry = provider.get_by_id("good_corolla")
    assert entry is not None
    assert entry["provider_name"] == "mock"
    assert entry["provider_listing_id"] == "good_corolla"
    assert entry["provider_raw_fields"]


def _normalize(value: object) -> str:
    return str(value).strip().casefold()
