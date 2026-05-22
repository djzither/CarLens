"""Auto.dev listing provider with optional live API and fixture fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.auto_dev_client import (
    AutoDevClient,
    AutoDevSearchParams,
    iter_auto_dev_provider_rows,
    parse_auto_dev_listings,
    resolve_fixture_payload,
)
from src.listings.auto_dev_adapter import adapt_auto_dev_listing, pop_adapter_warnings
from src.listings.listing_source_adapter import AUTO_DEV_SOURCE
from src.listings.providers.raw_listing_provider import RawListingProvider, raw_listing_matches_id
from src.listings.providers.search_support import resolve_entry_id, search_raw_listings
from src.listings.providers.types import SearchFilters, SearchResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)


def _iter_auto_dev_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return iter_auto_dev_provider_rows(payload)


def _expand_adapter_warnings(raw_listings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    cleaned: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_listings):
        listing = dict(raw)
        adapter_messages = pop_adapter_warnings(listing)
        if adapter_messages:
            entry_id = resolve_entry_id(listing, fallback_index=index)
            warnings.extend(f"{entry_id}: {message}" for message in adapter_messages)
        cleaned.append(listing)
    return cleaned, warnings


def _filters_to_search_params(filters: SearchFilters) -> AutoDevSearchParams:
    return AutoDevSearchParams(
        make=filters.make,
        model=filters.model,
        price_max=filters.max_price,
        mileage_max=filters.max_mileage,
        year_min=filters.min_year,
        year_max=filters.max_year,
    )


class AutoDevProvider(RawListingProvider):
    """Auto.dev provider: live API when configured, fixtures on failure or offline."""

    name = AUTO_DEV_SOURCE

    def __init__(
        self,
        fixture_path: Path | str | None = None,
        *,
        client: AutoDevClient | None = None,
        use_live_api: bool = True,
        max_pages: int = 10,
        page_size: int | None = None,
    ) -> None:
        self._fixture_path = (
            Path(fixture_path) if fixture_path is not None else DEFAULT_FIXTURE_PATH
        )
        self._payload: dict[str, Any] | None = None
        self._client = client if client is not None else AutoDevClient()
        self._use_live_api = use_live_api
        self._max_pages = max(1, max_pages)
        self._page_size = page_size
        self._last_fetch_errors: list[str] = []

    @property
    def fixture_path(self) -> Path:
        return self._fixture_path

    @property
    def last_fetch_errors(self) -> list[str]:
        return list(self._last_fetch_errors)

    def load_fixture_payload(self) -> dict[str, Any]:
        if self._payload is None:
            with self._fixture_path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError(f"{self._fixture_path.name} must contain a JSON object")
            self._payload = data
        return self._payload

    def _resolved_fixture_payload(self) -> dict[str, Any]:
        return resolve_fixture_payload(self.load_fixture_payload())

    def count_raw_listings(self) -> int:
        return len(_iter_auto_dev_rows(self._resolved_fixture_payload()))

    def _adapt_provider_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            adapt_auto_dev_listing(row)
            for row in iter_auto_dev_provider_rows(payload)
        ]

    def _fixture_raw_listings(self) -> list[dict[str, Any]]:
        return parse_auto_dev_listings(self._resolved_fixture_payload())

    def _try_live_fetch(self, filters: SearchFilters) -> tuple[list[dict[str, Any]], list[str]]:
        if not self._use_live_api or not self._client.has_api_key:
            return [], []

        base = _filters_to_search_params(filters)
        params = AutoDevSearchParams(
            make=base.make,
            model=base.model,
            price_max=base.price_max,
            mileage_max=base.mileage_max,
            year_min=base.year_min,
            year_max=base.year_max,
            page=1,
            page_size=self._page_size,
        )
        result = self._client.search_listings_paginated(
            params,
            max_pages=self._max_pages,
        )
        if result.errors:
            return [], result.errors
        if not result.payload:
            return [], []

        listings = self._adapt_provider_rows(result.payload)
        if listings:
            return listings, []
        return [], []

    def fetch_raw_listings(self, filters: SearchFilters) -> list[dict[str, Any]]:
        self._last_fetch_errors = []
        live_listings, errors = self._try_live_fetch(filters)
        if errors:
            self._last_fetch_errors.extend(errors)
        if live_listings:
            return live_listings
        return self._fixture_raw_listings()

    def fetch_raw_listing_by_id(self, provider_listing_id: str) -> dict[str, Any] | None:
        if self._use_live_api and self._client.has_api_key:
            result = self._client.get_listing_by_vin(provider_listing_id)
            if not result.errors and result.payload:
                rows = self._adapt_provider_rows(result.payload)
                if rows:
                    return rows[0]

        for row in _iter_auto_dev_rows(self._resolved_fixture_payload()):
            raw = adapt_auto_dev_listing(row)
            if raw_listing_matches_id(raw, provider_listing_id):
                return raw
        return None

    def search(self, filters: SearchFilters) -> SearchResult:
        raw_listings, adapter_warnings = _expand_adapter_warnings(
            self.fetch_raw_listings(filters)
        )
        total = self.count_raw_listings()
        result = search_raw_listings(
            provider_name=self.name,
            raw_listings=raw_listings,
            filters=filters,
            validate_listing=self.validate_listing,
            total_available=total if total is not None else len(raw_listings),
        )
        merged_warnings = [*adapter_warnings, *result.provider_warnings]
        if not self._last_fetch_errors:
            return SearchResult(
                listings=result.listings,
                provider_name=result.provider_name,
                provider_warnings=merged_warnings,
                errors=result.errors,
                total_available=result.total_available,
            )
        return SearchResult(
            listings=result.listings,
            provider_name=result.provider_name,
            provider_warnings=merged_warnings,
            errors=[*result.errors, *self._last_fetch_errors],
            total_available=result.total_available,
        )
