"""Listing provider interface for external inventory APIs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.listings.providers.types import SearchFilters, SearchResult

_REQUIRED_FIELDS = ("make", "model", "year", "price")
_ID_FIELDS = ("id", "listing_id")
_OPTIONAL_FIELDS = (
    "mileage",
    "clean_title",
    "title_status",
    "image_url",
    "source_url",
    "days_on_market",
    "accident_history",
)

_DIRTY_TITLE_STATUSES = frozenset({"dirty", "salvage", "rebuilt"})


def _field_present(raw: dict[str, Any], field: str) -> bool:
    value = raw.get(field)
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def skipped_listing_warning(entry_id: str, validation_errors: list[str]) -> str:
    """Warning for a listing skipped due to failed validation."""
    detail = ", ".join(validation_errors)
    return f"{entry_id}: skipped — {detail}"


def incomplete_listing_warnings(entry_id: str, raw: dict[str, Any]) -> list[str]:
    """Warnings for optional fields missing on an otherwise valid listing."""
    return [
        f"{entry_id}: missing optional {field}"
        for field in _OPTIONAL_FIELDS
        if not _field_present(raw, field)
    ]


def is_dirty_title(listing: dict[str, Any]) -> bool:
    """True when title is explicitly not clean (known-bad signals only)."""
    if listing.get("clean_title") is False:
        return True
    status = listing.get("title_status")
    if status is None:
        return False
    normalized = str(status).strip().casefold()
    return normalized in _DIRTY_TITLE_STATUSES


class ListingProvider(ABC):
    """Search vehicle listings from an external or mocked inventory source."""

    name: str = ""

    @abstractmethod
    def search(self, filters: SearchFilters) -> SearchResult:
        """Return listings matching filters plus any validation errors."""

    @abstractmethod
    def get_by_id(self, listing_id: str) -> dict | None:
        """Return a single listing record by id, or None if not found."""

    def validate_listing(self, raw: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate required listing fields before scoring.

        Required: id or listing_id, make, model, year, price.
        Optional: mileage, clean_title, title_status, image_url, source_url,
        days_on_market, accident_history.
        """
        errors: list[str] = []
        if not any(_field_present(raw, field) for field in _ID_FIELDS):
            errors.append("missing id or listing_id")
        for field in _REQUIRED_FIELDS:
            if not _field_present(raw, field):
                errors.append(f"missing {field}")
        return (not errors, errors)
