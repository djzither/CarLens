from __future__ import annotations

from typing import Any, Literal

from src.listings.listing_normalizer import (
    _mileage_candidates_from_text,
    _resolved_title,
    detect_clean_title,
    extract_trim,
    extract_year_make_model,
)

ConfidenceLevel = Literal["High", "Medium", "Low"]

_CORE_FIELDS = ("price", "mileage", "clean_title")


def _listing_title(raw: dict[str, Any]) -> str | None:
    return _resolved_title(raw)


def title_has_ambiguous_mileage(title: str | None) -> bool:
    """True when title text contains multiple distinct mileage readings."""
    if not title or not title.strip():
        return False
    candidates = _mileage_candidates_from_text(title)
    return len(set(candidates)) > 1


def detect_inferred_fields(
    raw_listing: dict[str, Any],
    normalized: dict[str, Any],
) -> list[str]:
    """Field names populated during normalization but not explicitly provided."""
    inferred: list[str] = []
    title = _listing_title(raw_listing)

    if title and raw_listing.get("make") is None:
        extracted = extract_year_make_model(title)
        if extracted.get("make"):
            inferred.append("make")
    if title and raw_listing.get("model") is None:
        extracted = extract_year_make_model(title)
        if extracted.get("model"):
            inferred.append("model")
    if raw_listing.get("year") is None and title:
        extracted = extract_year_make_model(title)
        if extracted.get("year") is not None:
            inferred.append("year")

    if raw_listing.get("mileage") is None and "mileage" in normalized:
        inferred.append("mileage")

    if raw_listing.get("trim") is None and "trim" in normalized:
        make = normalized["make"]
        model = normalized["model"]
        if title and extract_trim(title, make, model):
            inferred.append("trim")

    if raw_listing.get("clean_title") is None and "clean_title" in normalized:
        description = raw_listing.get("description")
        description_text = (
            str(description).strip()
            if description is not None and str(description).strip()
            else None
        )
        if detect_clean_title(title, description_text) is not None:
            inferred.append("clean_title")

    return inferred


def _missing_core_fields(normalized: dict[str, Any]) -> list[str]:
    return [field for field in _CORE_FIELDS if field not in normalized]


def _has_conflicting_signals(fit: dict[str, Any] | None) -> bool:
    if not fit:
        return False
    if fit.get("label_was_capped"):
        return True
    positives = fit.get("positive_reasons") or []
    negatives = fit.get("negative_reasons") or []
    if positives and negatives and "Strong model match" in positives:
        for negative in negatives:
            if negative.startswith("Not the recommended"):
                return True
    return False


def assess_listing_confidence(
    raw_listing: dict[str, Any],
    normalized: dict[str, Any],
    *,
    fit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score how trustworthy listing data is for display and decisions."""
    inferred_fields = detect_inferred_fields(raw_listing, normalized)
    missing_fields = _missing_core_fields(normalized)
    title = _listing_title(raw_listing)
    ambiguity_detected = title_has_ambiguous_mileage(title)
    conflicting_signals = _has_conflicting_signals(fit)
    warning_count = len(fit.get("warnings", [])) if fit else 0
    core_present = len(_CORE_FIELDS) - len(missing_fields)

    low = (
        ambiguity_detected
        or len(inferred_fields) >= 2
        or core_present < 2
        or conflicting_signals
        or warning_count >= 3
    )
    if low:
        level: ConfidenceLevel = "Low"
    elif (
        len(inferred_fields) == 1
        or len(missing_fields) == 1
        or warning_count >= 1
    ):
        level = "Medium"
    else:
        level = "High"

    return {
        "confidence_level": level,
        "inferred_fields": inferred_fields,
        "missing_fields": missing_fields,
        "ambiguity_detected": ambiguity_detected,
        "conflicting_signals": conflicting_signals,
    }
