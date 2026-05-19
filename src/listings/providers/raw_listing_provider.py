"""Base provider with separate raw fetch paths for search and get_by_id."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Callable

from src.listings.providers.base import ListingProvider
from src.listings.providers.provenance import attach_listing_provenance
from src.listings.providers.schema import make_provider_listing_record
from src.listings.providers.search_support import (
    _raw_for_validation,
    resolve_display_name,
    resolve_entry_id,
    search_raw_listings,
)
from src.listings.providers.types import SearchFilters, SearchResult


def raw_listing_matches_id(raw: dict[str, Any], lookup_id: str) -> bool:
    """True when a raw listing's id fields match the lookup value."""
    needle = lookup_id.strip()
    if not needle:
        return False
    for field in ("listing_id", "id", "vin"):
        value = raw.get(field)
        if value is not None and str(value).strip() == needle:
            return True
    return False


def build_provider_record_from_raw(
    *,
    raw_listing: dict[str, Any] | None,
    provider_name: str,
    validate_listing: Callable[[dict[str, Any]], tuple[bool, list[str]]],
    entry_id: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any] | None:
    """Validate, wrap, and attach provenance to one raw listing."""
    if raw_listing is None:
        return None

    record_id = entry_id or resolve_entry_id(raw_listing, fallback_index=0)
    label = display_name or resolve_display_name(raw_listing)
    entry = make_provider_listing_record(
        entry_id=record_id,
        raw_listing=raw_listing,
        provider_name=provider_name,
        display_name=label,
    )
    validation_raw = _raw_for_validation(entry)
    valid, _ = validate_listing(validation_raw)
    if not valid:
        return None
    return attach_listing_provenance(entry, provider_name=provider_name)


class RawListingProvider(ListingProvider):
    """Provider that adapts raw listings via fetch_raw_listings / fetch_raw_listing_by_id."""

    @abstractmethod
    def fetch_raw_listings(self, filters: SearchFilters) -> list[dict[str, Any]]:
        """Load or query all candidate raw listings (filtering may happen in search)."""

    @abstractmethod
    def fetch_raw_listing_by_id(
        self, provider_listing_id: str
    ) -> dict[str, Any] | None:
        """Fetch one raw listing by provider id without running a full search."""

    def count_raw_listings(self) -> int | None:
        """Optional total inventory count for SearchResult.total_available."""
        return None

    def search(self, filters: SearchFilters) -> SearchResult:
        raw_listings = self.fetch_raw_listings(filters)
        total = self.count_raw_listings()
        return search_raw_listings(
            provider_name=self.name,
            raw_listings=raw_listings,
            filters=filters,
            validate_listing=self.validate_listing,
            total_available=total if total is not None else len(raw_listings),
        )

    def get_by_id(self, provider_listing_id: str) -> dict | None:
        raw = self.fetch_raw_listing_by_id(provider_listing_id)
        return build_provider_record_from_raw(
            raw_listing=raw,
            provider_name=self.name,
            validate_listing=self.validate_listing,
            entry_id=provider_listing_id,
        )
