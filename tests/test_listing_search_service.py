"""Tests for multi-provider ListingSearchService aggregation."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.listings.providers import (
    AutoDevProvider,
    ListingProvider,
    ListingSearchService,
    MarketcheckProvider,
    SearchFilters,
    SearchResult,
    validate_provider_listing_record,
)
from src.listings.providers.search_service import AGGREGATED_PROVIDER_NAME

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTO_DEV_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)
MARKETCHECK_FIXTURE = (
    PROJECT_ROOT
    / "data"
    / "sample_listings"
    / "provider_payloads"
    / "marketcheck_sample.json"
)


class _BrokenProvider(ListingProvider):
    name = "broken"

    def search(self, filters: SearchFilters) -> SearchResult:
        raise RuntimeError("provider offline")

    def get_by_id(self, listing_id: str) -> dict | None:
        return None


class _WarningProvider(ListingProvider):
    name = "warn-only"

    def search(self, filters: SearchFilters) -> SearchResult:
        return SearchResult(
            listings=[],
            provider_name=self.name,
            provider_warnings=["sample warning"],
        )

    def get_by_id(self, listing_id: str) -> dict | None:
        return None


@pytest.fixture
def multi_service() -> ListingSearchService:
    return ListingSearchService(
        [
            AutoDevProvider(AUTO_DEV_FIXTURE),
            MarketcheckProvider(MARKETCHECK_FIXTURE),
        ]
    )


def test_combines_auto_dev_and_marketcheck(multi_service: ListingSearchService) -> None:
    result = multi_service.search(SearchFilters())
    provider_names = {record["provider_name"] for record in result.listings}

    assert result.provider_name == AGGREGATED_PROVIDER_NAME
    assert len(result.listings) >= 2
    assert provider_names >= {"auto.dev", "marketcheck"}


def test_preserves_provider_name_on_every_listing(
    multi_service: ListingSearchService,
) -> None:
    result = multi_service.search(SearchFilters())
    for record in result.listings:
        assert record["provider_name"] in {"auto.dev", "marketcheck"}
        assert record["provider_name"] == record["listing"].get("source")


def test_aggregates_provider_warnings(multi_service: ListingSearchService) -> None:
    service = ListingSearchService(
        [_WarningProvider(), AutoDevProvider(AUTO_DEV_FIXTURE)]
    )
    result = service.search(SearchFilters())
    assert any("warn-only" in w and "sample warning" in w for w in result.provider_warnings)
    assert result.listings


def test_provider_exception_does_not_crash_search(
    multi_service: ListingSearchService,
) -> None:
    service = ListingSearchService(
        [_BrokenProvider(), AutoDevProvider(AUTO_DEV_FIXTURE)]
    )
    result = service.search(SearchFilters(make="Toyota", model="Corolla"))

    assert any("broken" in err and "provider offline" in err for err in result.errors)
    assert result.listings
    assert all(record["provider_name"] == "auto.dev" for record in result.listings)


def test_returned_listings_match_shared_schema(
    multi_service: ListingSearchService,
) -> None:
    result = multi_service.search(SearchFilters())
    assert result.listings
    for record in result.listings:
        ok, errors = validate_provider_listing_record(record)
        assert ok, errors


def test_dedupes_same_provider_listing_id(multi_service: ListingSearchService) -> None:
    class _DupProvider(ListingProvider):
        name = "dup"

        def search(self, filters: SearchFilters) -> SearchResult:
            record = AutoDevProvider(AUTO_DEV_FIXTURE).search(SearchFilters()).listings[0]
            copy = dict(record)
            copy["id"] = "dup_copy"
            return SearchResult(listings=[record, copy], provider_name=self.name)

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    service = ListingSearchService([_DupProvider()])
    result = service.search(SearchFilters())
    ids = [
        (r["provider_name"], r["provider_listing_id"])
        for r in result.listings
    ]
    assert len(ids) == len(set(ids))


def test_search_filters_rejects_make_without_model() -> None:
    with pytest.raises(ValueError, match="make and model must both"):
        SearchFilters(make="Toyota")


def test_search_filters_rejects_model_without_make() -> None:
    with pytest.raises(ValueError, match="make and model must both"):
        SearchFilters(model="Corolla")


def test_search_filters_accepts_both_omitted_or_both_set() -> None:
    SearchFilters()
    SearchFilters(make="Toyota", model="Corolla")
