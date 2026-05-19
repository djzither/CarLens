"""Fixture-backed Auto.dev listing provider (no live API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.auto_dev_client import parse_auto_dev_listings
from src.listings.listing_source_adapter import AUTO_DEV_SOURCE
from src.listings.providers.base import ListingProvider
from src.listings.providers.search_support import search_raw_listings
from src.listings.providers.types import SearchFilters, SearchResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)


class AutoDevProvider(ListingProvider):
    """Auto.dev provider skeleton using offline fixture JSON."""

    name = AUTO_DEV_SOURCE

    def __init__(self, fixture_path: Path | str | None = None) -> None:
        self._fixture_path = (
            Path(fixture_path) if fixture_path is not None else DEFAULT_FIXTURE_PATH
        )
        self._payload: dict[str, Any] | None = None

    @property
    def fixture_path(self) -> Path:
        return self._fixture_path

    def load_fixture_payload(self) -> dict[str, Any]:
        if self._payload is None:
            with self._fixture_path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError(f"{self._fixture_path.name} must contain a JSON object")
            self._payload = data
        return self._payload

    def fetch_raw_listings(self) -> list[dict[str, Any]]:
        """Parse fixture payload into CarLens raw listings (no HTTP)."""
        return parse_auto_dev_listings(self.load_fixture_payload())

    def search(self, filters: SearchFilters) -> SearchResult:
        raw_listings = self.fetch_raw_listings()
        return search_raw_listings(
            provider_name=self.name,
            raw_listings=raw_listings,
            filters=filters,
            validate_listing=self.validate_listing,
            total_available=len(raw_listings),
        )

    def get_by_id(self, listing_id: str) -> dict | None:
        for record in self.search(SearchFilters()).listings:
            if record.get("id") == listing_id or record.get("provider_listing_id") == listing_id:
                return record
        return None
