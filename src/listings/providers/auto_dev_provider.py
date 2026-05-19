"""Fixture-backed Auto.dev listing provider (no live API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.auto_dev_client import parse_auto_dev_listings
from src.listings.listing_source_adapter import AUTO_DEV_SOURCE, adapt_auto_dev_listing
from src.listings.providers.raw_listing_provider import RawListingProvider, raw_listing_matches_id
from src.listings.providers.types import SearchFilters

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)


def _iter_auto_dev_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


class AutoDevProvider(RawListingProvider):
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

    def count_raw_listings(self) -> int:
        return len(_iter_auto_dev_rows(self.load_fixture_payload()))

    def fetch_raw_listings(self, filters: SearchFilters) -> list[dict[str, Any]]:
        """Parse fixture payload into CarLens raw listings (no HTTP)."""
        del filters  # filtering happens in search_raw_listings
        return parse_auto_dev_listings(self.load_fixture_payload())

    def fetch_raw_listing_by_id(self, provider_listing_id: str) -> dict[str, Any] | None:
        for row in _iter_auto_dev_rows(self.load_fixture_payload()):
            raw = adapt_auto_dev_listing(row)
            if raw_listing_matches_id(raw, provider_listing_id):
                return raw
        return None
