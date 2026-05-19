"""Mock listing provider backed by local sample JSON (no paid API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.providers.base import ListingSearchQuery

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


def _matches_query(entry: dict[str, Any], query: ListingSearchQuery) -> bool:
    listing = _listing_from_entry(entry)

    make = query.get("make")
    if make is not None and _normalize_str(listing.get("make")) != _normalize_str(make):
        return False

    model = query.get("model")
    if model is not None and _normalize_str(listing.get("model")) != _normalize_str(model):
        return False

    year = listing.get("year")
    if year is not None:
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            year_int = None
    else:
        year_int = None

    min_year = query.get("min_year")
    if min_year is not None:
        if year_int is None or year_int < int(min_year):
            return False

    max_year = query.get("max_year")
    if max_year is not None:
        if year_int is None or year_int > int(max_year):
            return False

    price = listing.get("price")
    max_price = query.get("max_price")
    if max_price is not None and price is not None:
        try:
            if float(price) > float(max_price):
                return False
        except (TypeError, ValueError):
            pass

    mileage = listing.get("mileage")
    max_mileage = query.get("max_mileage")
    if max_mileage is not None and mileage is not None:
        try:
            if int(mileage) > int(max_mileage):
                return False
        except (TypeError, ValueError):
            pass

    return True


class MockListingProvider:
    """Serve listings from a local sample JSON file with optional filters."""

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

    def search_listings(
        self,
        query: ListingSearchQuery | None = None,
    ) -> list[dict[str, Any]]:
        filters = query or {}
        if not filters:
            return list(self._entries)
        return [entry for entry in self._entries if _matches_query(entry, filters)]
