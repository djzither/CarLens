"""Mock listing provider backed by local sample JSON (no paid API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.providers.raw_listing_provider import (
    RawListingProvider,
    build_provider_record_from_raw,
    raw_listing_matches_id,
)
from src.listings.providers.types import SearchFilters, SearchResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SAMPLE_PATH = (
    PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
)


def _listing_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    listing = entry.get("listing")
    if isinstance(listing, dict):
        return listing
    return entry


def _raw_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    raw = dict(_listing_from_entry(entry))
    entry_id = entry.get("id")
    if entry_id and not raw.get("listing_id"):
        raw["listing_id"] = str(entry_id)
    return raw


def _entry_matches_id(entry: dict[str, Any], lookup_id: str) -> bool:
    if str(entry.get("id", "")).strip() == lookup_id.strip():
        return True
    return raw_listing_matches_id(_listing_from_entry(entry), lookup_id)


class MockListingProvider(RawListingProvider):
    """Serve listings from a local sample JSON file with optional filters."""

    name = "mock"

    def __init__(self, data_path: Path | str | None = None) -> None:
        self._data_path = Path(data_path) if data_path is not None else DEFAULT_SAMPLE_PATH
        self._buyer_profile_id = ""
        self._entries: list[dict[str, Any]] = []
        self._load()

    @property
    def buyer_profile_id(self) -> str:
        return self._buyer_profile_id

    @property
    def data_path(self) -> Path:
        return self._data_path

    def _load(self) -> None:
        with self._data_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"{self._data_path.name} must contain a JSON object")
        self._buyer_profile_id = str(data.get("buyer_profile_id", ""))
        listings = data.get("listings")
        if not isinstance(listings, list):
            raise ValueError(f"{self._data_path.name} must contain a listings array")
        self._entries = [entry for entry in listings if isinstance(entry, dict)]

    def _find_entry(self, provider_listing_id: str) -> dict[str, Any] | None:
        for entry in self._entries:
            if _entry_matches_id(entry, provider_listing_id):
                return entry
        return None

    def count_raw_listings(self) -> int:
        return len(self._entries)

    def fetch_raw_listings(self, filters: SearchFilters) -> list[dict[str, Any]]:
        del filters
        return [_raw_from_entry(entry) for entry in self._entries]

    def fetch_raw_listing_by_id(self, provider_listing_id: str) -> dict[str, Any] | None:
        entry = self._find_entry(provider_listing_id)
        if entry is None:
            return None
        return _raw_from_entry(entry)

    def search(self, filters: SearchFilters) -> SearchResult:
        result = super().search(filters)
        display_by_id = {
            str(entry.get("id")): entry.get("display_name")
            for entry in self._entries
            if entry.get("id")
        }
        listings: list[dict[str, Any]] = []
        for record in result.listings:
            updated = dict(record)
            name = display_by_id.get(record["id"])
            if name and str(name).strip():
                updated["display_name"] = str(name).strip()
            listings.append(updated)
        return SearchResult(
            listings=listings,
            provider_name=result.provider_name,
            provider_warnings=result.provider_warnings,
            errors=result.errors,
            total_available=result.total_available,
        )

    def get_by_id(self, provider_listing_id: str) -> dict | None:
        entry = self._find_entry(provider_listing_id)
        if entry is None:
            return None
        display_name = entry.get("display_name")
        label = str(display_name).strip() if display_name else None
        return build_provider_record_from_raw(
            raw_listing=_raw_from_entry(entry),
            provider_name=self.name,
            validate_listing=self.validate_listing,
            entry_id=str(entry.get("id", provider_listing_id)),
            display_name=label,
        )
