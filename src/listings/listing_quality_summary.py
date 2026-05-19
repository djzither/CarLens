"""Listing quality summary from provider provenance and warning context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.listings.provider_clean_title import provider_clean_title_is_unknown

ConfidenceBand = Literal["high", "medium", "low"]

CLEAN_TITLE_BADGE = "Clean title verified"
TITLE_ISSUE_WARNING = "Title issue reported"
TITLE_UNAVAILABLE_WARNING = "Title history unavailable"

# Fields expected for trustworthy listing cards (provider-reported presence).
IMPORTANT_PROVIDER_FIELDS = frozenset({"make", "model", "year", "price", "mileage"})


@dataclass
class ListingQualityWarningsContext:
    """Provider- or search-level warnings that apply when summarizing one listing."""

    provider_warnings: list[str] = field(default_factory=list)


def _field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, bool):
        return True
    return True


def _missing_important_fields(
    listing: dict[str, Any],
    provider_raw_fields: list[str] | None,
) -> list[str]:
    """Important fields absent from the provider payload or listing values."""
    reported = set(provider_raw_fields or [])
    missing: list[str] = []
    for field_name in sorted(IMPORTANT_PROVIDER_FIELDS):
        if field_name not in reported:
            missing.append(field_name)
            continue
        if not _field_present(listing.get(field_name)):
            missing.append(field_name)
    return missing


def _title_badge_and_warning(listing: dict[str, Any]) -> tuple[str | None, str | None]:
    clean_title = listing.get("clean_title")
    if clean_title is True:
        return CLEAN_TITLE_BADGE, None
    if clean_title is False:
        return None, TITLE_ISSUE_WARNING
    if provider_clean_title_is_unknown(listing) or clean_title is None:
        return None, TITLE_UNAVAILABLE_WARNING
    return None, TITLE_UNAVAILABLE_WARNING


def _resolve_confidence(
    *,
    listing: dict[str, Any],
    missing_fields: list[str],
    provider_warning_count: int,
) -> ConfidenceBand:
    """Map data gaps and provider warnings to high / medium / low."""
    clean_title = listing.get("clean_title")
    missing_count = len(missing_fields)

    if clean_title is False:
        return "low"
    if provider_warning_count >= 2:
        return "low"
    if missing_count >= 2:
        return "low"
    if provider_warning_count >= 1 or missing_count >= 1:
        return "medium"
    if clean_title is not True:
        return "medium"
    return "high"


def build_listing_quality_summary(
    record: dict[str, Any],
    *,
    warnings_context: ListingQualityWarningsContext | None = None,
) -> dict[str, Any]:
    """
    Summarize listing data quality for display (not scoring).

    ``record`` is a provider listing envelope with provenance
    (``provider_name``, ``listing``, ``provider_raw_fields``, …).
    """
    listing = record.get("listing")
    if not isinstance(listing, dict):
        listing = {}

    provider_name = str(record.get("provider_name") or listing.get("source") or "")
    raw_fields = record.get("provider_raw_fields")
    provider_raw_fields = list(raw_fields) if isinstance(raw_fields, list) else []

    ctx = warnings_context or ListingQualityWarningsContext()
    provider_warnings = list(ctx.provider_warnings)

    badge, title_warning = _title_badge_and_warning(listing)
    badges: list[str] = []
    if badge:
        badges.append(badge)

    warnings: list[str] = []
    if title_warning:
        warnings.append(title_warning)

    missing_fields = _missing_important_fields(listing, provider_raw_fields)
    confidence = _resolve_confidence(
        listing=listing,
        missing_fields=missing_fields,
        provider_warning_count=len(provider_warnings),
    )

    return {
        "source": provider_name,
        "confidence": confidence,
        "badges": badges,
        "warnings": warnings,
    }
