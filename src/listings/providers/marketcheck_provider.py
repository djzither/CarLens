"""Fixture-backed MarketCheck listing provider (no live API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.listing_source_adapter import MARKETCHECK_SOURCE, adapt_marketcheck_listing
from src.listings.marketcheck_client import parse_marketcheck_listings
from src.listings.providers.raw_listing_provider import RawListingProvider, raw_listing_matches_id
from src.listings.providers.types import SearchFilters

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "sample_listings"
    / "provider_payloads"
    / "marketcheck_sample.json"
)


def _iter_marketcheck_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    listings = payload.get("listings")
    if not isinstance(listings, list):
        return []
    return [row for row in listings if isinstance(row, dict)]


class MarketcheckProvider(RawListingProvider):
    """MarketCheck provider skeleton using offline fixture JSON."""

    name = MARKETCHECK_SOURCE

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

    def count_raw_listings(self) -> int:
        return len(_iter_marketcheck_rows(self.load_fixture_payload()))

    def fetch_raw_listings(self, filters: SearchFilters) -> list[dict[str, Any]]:
        """Parse fixture payload into CarLens raw listings (no HTTP)."""
        del filters
        return parse_marketcheck_listings(self.load_fixture_payload())

    def fetch_raw_listing_by_id(self, provider_listing_id: str) -> dict[str, Any] | None:
        for row in _iter_marketcheck_rows(self.load_fixture_payload()):
            raw = adapt_marketcheck_listing(row)
            if raw_listing_matches_id(raw, provider_listing_id):
                return raw
        return None
