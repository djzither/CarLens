"""Mock listing provider backed by local sample JSON (no paid API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.providers.base import ListingProvider, is_dirty_title
from src.listings.providers.provenance import attach_listing_provenance
from src.listings.providers.types import SearchFilters, SearchResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SAMPLE_PATH = (
    PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
)


def _normalize_str(value: Any) -> str:
    return str(value).strip().casefold()


def _listing_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    listing = entry.get("listing")
    if isinstance(listing, dict):
        return listing
    return entry


def _raw_for_validation(entry: dict[str, Any]) -> dict[str, Any]:
    listing = _listing_from_entry(entry)
    raw = dict(listing)
    entry_id = entry.get("id")
    if entry_id and not raw.get("id") and not raw.get("listing_id"):
        raw["id"] = entry_id
    return raw


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_price(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matches_filters(entry: dict[str, Any], filters: SearchFilters) -> bool:
    listing = _listing_from_entry(entry)

    if filters.make is not None:
        if _normalize_str(listing.get("make")) != _normalize_str(filters.make):
            return False

    if filters.model is not None:
        if _normalize_str(listing.get("model")) != _normalize_str(filters.model):
            return False

    year_int = _parse_int(listing.get("year"))

    if filters.min_year is not None:
        if year_int is None or year_int < filters.min_year:
            return False

    if filters.max_year is not None:
        if year_int is None or year_int > filters.max_year:
            return False

    if filters.max_price is not None:
        price = _parse_price(listing.get("price"))
        if price is not None and price > float(filters.max_price):
            return False

    if filters.max_mileage is not None:
        mileage = _parse_int(listing.get("mileage"))
        if mileage is not None and mileage > filters.max_mileage:
            return False

    if filters.clean_title_only and is_dirty_title(listing):
        return False

    return True


class MockListingProvider(ListingProvider):
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

    def search(self, filters: SearchFilters) -> SearchResult:
        matched: list[dict[str, Any]] = []
        errors: list[str] = []

        for entry in self._entries:
            entry_id = str(entry.get("id", "unknown"))
            raw = _raw_for_validation(entry)
            valid, validation_errors = self.validate_listing(raw)
            if not valid:
                errors.append(f"{entry_id}: {', '.join(validation_errors)}")
                continue
            if _matches_filters(entry, filters):
                matched.append(
                    attach_listing_provenance(entry, provider_name=self.name)
                )

        return SearchResult(
            listings=matched,
            provider_name=self.name,
            errors=errors,
            total_available=len(self._entries),
        )

    def get_by_id(self, listing_id: str) -> dict | None:
        for entry in self._entries:
            if entry.get("id") != listing_id:
                continue
            raw = _raw_for_validation(entry)
            valid, _ = self.validate_listing(raw)
            if valid:
                return attach_listing_provenance(entry, provider_name=self.name)
            return None
        return None
