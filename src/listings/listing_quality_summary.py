"""Listing quality summary: fit quality separate from data quality."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.listings.listing_fit import DIRTY_TITLE_WARNING
from src.listings.provider_clean_title import provider_clean_title_is_unknown

FitQuality = Literal["strong", "moderate", "weak"]
DataQualityLevel = Literal["high", "medium", "low"]
TitleCertainty = Literal["clean", "dirty", "unknown"]

CLEAN_TITLE_BADGE = "Clean title verified"
TITLE_UNAVAILABLE_WARNING = "Title history unavailable"

# Provider-reported fields used for data completeness (not fit scoring).
TRACKED_DATA_FIELDS = frozenset({"make", "model", "year", "price", "mileage"})

_FIT_LABEL_TO_QUALITY: dict[str, FitQuality] = {
    "Strong fit": "strong",
    "Moderate fit": "moderate",
    "Weak fit": "weak",
}


@dataclass
class ListingQualityWarningsContext:
    """Provider- or search-level warnings that apply when summarizing one listing."""

    provider_warnings: list[str] = field(default_factory=list)


def _field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _resolve_title_certainty(listing: dict[str, Any]) -> TitleCertainty:
    clean_title = listing.get("clean_title")
    if clean_title is True:
        return "clean"
    if clean_title is False:
        return "dirty"
    if provider_clean_title_is_unknown(listing) or clean_title is None:
        return "unknown"
    return "unknown"


def _resolve_fit_quality(fit: dict[str, Any] | None) -> FitQuality:
    if not fit:
        return "moderate"
    label = fit.get("fit_label")
    if isinstance(label, str):
        mapped = _FIT_LABEL_TO_QUALITY.get(label.strip())
        if mapped:
            return mapped
    return "moderate"


def _partition_tracked_fields(
    listing: dict[str, Any],
    provider_raw_fields: list[str],
) -> tuple[list[str], list[str], float]:
    """Split tracked fields into provided vs unavailable; return completeness ratio."""
    reported = set(provider_raw_fields)
    provided: list[str] = []
    unavailable: list[str] = []
    for field_name in sorted(TRACKED_DATA_FIELDS):
        if field_name in reported and _field_present(listing.get(field_name)):
            provided.append(field_name)
        else:
            unavailable.append(field_name)
    total = len(TRACKED_DATA_FIELDS)
    completeness = len(provided) / total if total else 0.0
    return provided, unavailable, completeness


def _resolve_data_quality_level(
    *,
    title_certainty: TitleCertainty,
    data_completeness: float,
    provider_warning_count: int,
) -> DataQualityLevel:
    """Data quality only — ignores fit/recommendation signals."""
    if title_certainty == "dirty":
        return "low"
    if provider_warning_count >= 2 or data_completeness < 0.6:
        return "low"
    if (
        title_certainty == "unknown"
        or provider_warning_count >= 1
        or data_completeness < 1.0
    ):
        return "medium"
    return "high"


def _title_badges_and_warnings(title_certainty: TitleCertainty) -> tuple[list[str], list[str]]:
    badges: list[str] = []
    warnings: list[str] = []
    if title_certainty == "clean":
        badges.append(CLEAN_TITLE_BADGE)
    elif title_certainty == "dirty":
        warnings.append(DIRTY_TITLE_WARNING)
    elif title_certainty == "unknown":
        warnings.append(TITLE_UNAVAILABLE_WARNING)
    return badges, warnings


def build_listing_quality_summary(
    record: dict[str, Any],
    *,
    fit: dict[str, Any] | None = None,
    warnings_context: ListingQualityWarningsContext | None = None,
) -> dict[str, Any]:
    """
    Summarize listing quality for display (not scoring).

    ``record`` is a provider listing envelope with provenance.
    ``fit`` supplies ``fit_label`` for fit_quality only; it does not affect
    data_quality_level or data_completeness.
    """
    listing = record.get("listing")
    if not isinstance(listing, dict):
        listing = {}

    provider_name = str(record.get("provider_name") or listing.get("source") or "")
    raw_fields = record.get("provider_raw_fields")
    provider_raw_fields = list(raw_fields) if isinstance(raw_fields, list) else []

    ctx = warnings_context or ListingQualityWarningsContext()
    provider_warnings = list(ctx.provider_warnings)

    title_certainty = _resolve_title_certainty(listing)
    provided_fields, unavailable_fields, data_completeness = _partition_tracked_fields(
        listing, provider_raw_fields
    )
    data_quality_level = _resolve_data_quality_level(
        title_certainty=title_certainty,
        data_completeness=data_completeness,
        provider_warning_count=len(provider_warnings),
    )

    badges, warnings = _title_badges_and_warnings(title_certainty)

    return {
        "source": provider_name,
        "fit_quality": _resolve_fit_quality(fit),
        "data_quality_level": data_quality_level,
        "title_certainty": title_certainty,
        "data_completeness": round(data_completeness, 4),
        "provided_fields": provided_fields,
        "unavailable_fields": unavailable_fields,
        "badges": badges,
        "warnings": warnings,
    }
