"""Shared search pipeline for fixture and future live API providers."""

from __future__ import annotations

from typing import Any, Callable

from src.listings.providers.base import incomplete_listing_warnings, skipped_listing_warning
from src.listings.providers.provenance import attach_listing_provenance
from src.listings.providers.schema import make_provider_listing_record
from src.listings.providers.types import SearchFilters, SearchResult


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


def matches_filters(entry: dict[str, Any], filters: SearchFilters) -> bool:
    from src.listings.providers.base import is_dirty_title

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


def resolve_entry_id(raw_listing: dict[str, Any], *, fallback_index: int) -> str:
    for field in ("listing_id", "id", "vin"):
        value = raw_listing.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return f"listing-{fallback_index}"


def resolve_display_name(raw_listing: dict[str, Any]) -> str | None:
    for field in ("title", "raw_title"):
        value = raw_listing.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    parts = [raw_listing.get("year"), raw_listing.get("make"), raw_listing.get("model")]
    text = " ".join(str(part) for part in parts if part is not None).strip()
    return text or None


def search_raw_listings(
    *,
    provider_name: str,
    raw_listings: list[dict[str, Any]],
    filters: SearchFilters,
    validate_listing: Callable[[dict[str, Any]], tuple[bool, list[str]]],
    total_available: int | None = None,
) -> SearchResult:
    """Validate, filter, and attach provenance to adapted raw listings."""
    matched: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, raw_listing in enumerate(raw_listings):
        entry_id = resolve_entry_id(raw_listing, fallback_index=index)
        entry = make_provider_listing_record(
            entry_id=entry_id,
            raw_listing=raw_listing,
            provider_name=provider_name,
            display_name=resolve_display_name(raw_listing),
        )
        validation_raw = _raw_for_validation(entry)
        valid, validation_errors = validate_listing(validation_raw)
        if not valid:
            warnings.append(skipped_listing_warning(entry_id, validation_errors))
            continue
        if matches_filters(entry, filters):
            warnings.extend(incomplete_listing_warnings(entry_id, validation_raw))
            matched.append(attach_listing_provenance(entry, provider_name=provider_name))

    return SearchResult(
        listings=matched,
        provider_name=provider_name,
        provider_warnings=warnings,
        total_available=total_available if total_available is not None else len(raw_listings),
    )
