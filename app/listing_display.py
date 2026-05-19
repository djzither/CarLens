"""Pure helpers for Streamlit listing summary and ranking copy."""

from __future__ import annotations

from typing import Any

from src.listings.listing_fit import (
    DIRTY_TITLE_WARNING,
    MISSING_DRIVE_TYPE_WARNING,
    MISSING_MILEAGE_WARNING,
    MISSING_PRICE_WARNING,
    MISSING_TITLE_WARNING,
    NOT_AWD_WARNING,
)

_MAJOR_WARNING_MARKERS = (
    "does not have a clean title",
    "title status not disclosed",
    "price was not provided",
    "mileage not disclosed",
    "drive type was not provided",
    "not all-wheel drive",
    "exceeds your",
    "known weak year",
    "outside the recommended",
    "does not match any recommended model",
    DIRTY_TITLE_WARNING,
    MISSING_TITLE_WARNING,
    MISSING_PRICE_WARNING,
    MISSING_MILEAGE_WARNING,
    MISSING_DRIVE_TYPE_WARNING,
    NOT_AWD_WARNING,
)

WATCHOUT_MISSING_PRICE = "Price not listed — cannot verify budget fit"
WATCHOUT_MISSING_MILEAGE = "Mileage not listed — cannot verify usage/risk"

_WATCHOUT_DEDUPE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "price_missing",
        (
            "price not listed",
            "price was not provided",
            "cannot verify budget fit",
        ),
    ),
    (
        "mileage_missing",
        (
            "mileage not listed",
            "mileage not disclosed",
            "odometer reading unavailable",
            "cannot verify usage",
        ),
    ),
    (
        "title_dirty",
        (
            "dirty title",
            "does not have a clean title",
            "salvage",
            "rebuilt title",
            "flood damage",
            "flood title",
        ),
    ),
    (
        "title_undisclosed",
        (
            "title status not disclosed",
            "verify clean title before purchase",
            "verify before purchase",
        ),
    ),
    (
        "awd_requirement",
        (
            "does not meet awd",
            "awd required",
            "all-wheel drive",
            "4wd",
            "drive type not disclosed",
            "drive type was not provided",
        ),
    ),
)

RANKING_ORDER_LINES: tuple[str, ...] = (
    "Listings are ordered by fit label (Strong fit, then Moderate, then Weak).",
    "When fit is similar, higher confidence (High, then Medium, then Low) ranks higher.",
    "Further tie-breakers: higher fit score, fewer warnings, lower price, then lower mileage.",
    "Price and mileage matter most as tie-breakers — not as the main reason a listing leads.",
)


def format_recommended_because(recommendation: dict[str, Any]) -> str:
    """Short trait-led summary for why a vehicle model was recommended."""
    reasons = recommendation.get("reasons") or []
    traits: list[str] = []
    for item in reasons:
        if item.get("type") == "missing_trait":
            continue
        trait = item.get("trait")
        if trait:
            traits.append(str(trait).replace("_", " "))
    if traits:
        return ", ".join(traits)
    return "matches your buyer profile"


def format_price(price: int | float | None) -> str:
    if price is None:
        return "Price not listed"
    return f"${int(price):,}"


def format_mileage(mileage: int | float | None) -> str:
    if mileage is None:
        return "Mileage not listed"
    miles = int(mileage)
    if miles >= 1_000:
        thousands = miles / 1_000
        if miles % 1_000 == 0:
            return f"{int(thousands)}k miles"
        return f"{thousands:.1f}k miles"
    return f"{miles:,} miles"


def format_title_status(listing: dict[str, Any]) -> str:
    clean = listing.get("clean_title")
    if clean is True:
        return "Clean title"
    if clean is False:
        return "Dirty title"
    return "Title undisclosed"


def format_listing_facts(listing: dict[str, Any]) -> str:
    return " · ".join(
        (
            format_price(listing.get("price")),
            format_mileage(listing.get("mileage")),
            format_title_status(listing),
        )
    )


def _normalize_watchout_key(text: str) -> str:
    return " ".join(str(text).casefold().split())


def _watchout_dedupe_group(text: str) -> str | None:
    lowered = str(text).casefold()
    for group_name, markers in _WATCHOUT_DEDUPE_GROUPS:
        if any(marker in lowered for marker in markers):
            if group_name == "price_missing" and (
                "exceed" in lowered or "over budget" in lowered
            ):
                continue
            if group_name == "mileage_missing" and (
                "exceed" in lowered or "exceeds preferred" in lowered
            ):
                continue
            return group_name
    return None


def _dedupe_watchouts(items: list[str]) -> list[str]:
    """Drop exact and topical duplicates while preserving first-seen order."""
    deduped: list[str] = []
    seen_exact: set[str] = set()
    seen_groups: set[str] = set()

    for item in items:
        text = str(item).strip()
        if not text:
            continue
        exact_key = _normalize_watchout_key(text)
        if exact_key in seen_exact:
            continue
        group = _watchout_dedupe_group(text)
        if group is not None and group in seen_groups:
            continue
        seen_exact.add(exact_key)
        if group is not None:
            seen_groups.add(group)
        deduped.append(text)

    return deduped


def build_watchouts(fit: dict[str, Any], listing: dict[str, Any]) -> list[str]:
    """Unified buyer-facing watchouts: warnings, negatives, and missing-field gaps."""
    candidates: list[str] = []

    if listing.get("price") is None:
        candidates.append(WATCHOUT_MISSING_PRICE)
    if listing.get("mileage") is None:
        candidates.append(WATCHOUT_MISSING_MILEAGE)

    candidates.extend(fit.get("warnings") or [])
    candidates.extend(fit.get("negative_reasons") or [])

    return _dedupe_watchouts(candidates)


def listing_source_url(listing: dict[str, Any]) -> str | None:
    """Return a safe listing URL when explicitly provided."""
    url = listing.get("listing_url")
    if url is None:
        return None
    text = str(url).strip()
    if text.startswith(("http://", "https://")):
        return text
    return None


def format_listing_source_markdown(listing: dict[str, Any]) -> str:
    """Markdown for the listing source line on a card."""
    url = listing_source_url(listing)
    if url:
        return f"[View listing]({url})"
    return "No source link"


def has_dirty_title(listing: dict[str, Any]) -> bool:
    return listing.get("clean_title") is False


def warning_is_major(warning: str) -> bool:
    lowered = warning.casefold()
    return any(marker.casefold() in lowered for marker in _MAJOR_WARNING_MARKERS)


def has_major_warnings(fit: dict[str, Any]) -> bool:
    return any(warning_is_major(warning) for warning in fit.get("warnings") or [])


def qualifies_as_top_pick(entry: dict[str, Any]) -> bool:
    """True when the first listing in a group is a clear stand-out choice."""
    fit = entry["fit"]
    listing = entry["listing"]
    confidence = entry.get("confidence") or fit.get("confidence") or {}
    level = confidence.get("confidence_level", fit.get("confidence_level", "Low"))

    if fit.get("fit_label") != "Strong fit":
        return False
    if level not in ("High", "Medium"):
        return False
    if has_dirty_title(listing):
        return False
    if has_major_warnings(fit):
        return False
    return True


def top_pick_banner_text(entry: dict[str, Any] | None) -> str:
    if entry is not None and qualifies_as_top_pick(entry):
        return "Top pick"
    return "No clear top pick — review warnings."


def format_score_caption(fit: dict[str, Any]) -> str:
    return f"Fit score {fit.get('fit_score', 0.0):.3f} (secondary signal)"


def build_ranking_explanation_lines() -> list[str]:
    return list(RANKING_ORDER_LINES)
