"""Normalized provider listing record and raw listing expectations."""

from __future__ import annotations

from typing import Any

from src.listings.listing_source_adapter import RAW_LISTING_KEYS

# Envelope returned in SearchResult.listings (see providers/README.md).
PROVIDER_LISTING_RECORD_KEYS = frozenset(
    {
        "id",
        "listing",
        "provider_name",
        "provider_listing_id",
        "provider_raw_fields",
    }
)
PROVIDER_LISTING_OPTIONAL_KEYS = frozenset({"display_name", "provider_url"})

# Minimum raw listing keys expected after Auto.dev / MarketCheck adaptation.
NORMALIZED_RAW_LISTING_REQUIRED = frozenset(
    {"make", "model", "year", "price", "source"}
)
NORMALIZED_RAW_LISTING_RECOMMENDED = frozenset(
    {
        "listing_id",
        "mileage",
        "title",
        "listing_url",
        "image_url",
        "location",
        "distance_miles",
    }
)


def validate_provider_listing_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a SearchResult listing envelope."""
    errors: list[str] = []
    missing = PROVIDER_LISTING_RECORD_KEYS - record.keys()
    if missing:
        errors.append(f"missing record keys: {', '.join(sorted(missing))}")
    listing = record.get("listing")
    if not isinstance(listing, dict):
        errors.append("listing must be a dict")
    else:
        raw_missing = NORMALIZED_RAW_LISTING_REQUIRED - listing.keys()
        if raw_missing:
            errors.append(
                f"listing missing required raw keys: {', '.join(sorted(raw_missing))}"
            )
        unknown = set(listing.keys()) - RAW_LISTING_KEYS - {"id", "raw_title"}
        if unknown:
            errors.append(f"unexpected raw listing keys: {', '.join(sorted(unknown))}")
    return (not errors, errors)


def make_provider_listing_record(
    *,
    entry_id: str,
    raw_listing: dict[str, Any],
    provider_name: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Build a listing record before provenance attachment."""
    record: dict[str, Any] = {"id": entry_id, "listing": raw_listing}
    if display_name:
        record["display_name"] = display_name
    return record
