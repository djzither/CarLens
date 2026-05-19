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
WATCHOUT_MISSING_MILEAGE = "Mileage not listed — cannot verify wear/usage"
DIRTY_TITLE_BANNER = (
    "Dirty or branded title reported — verify title status before purchase."
)
SELLER_TITLE_CONFLICT_WARNING = (
    "Seller's title/description conflict — verify title status independently "
    "before purchase."
)

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
        "seller_title_conflict",
        (
            "title/description conflict",
            "verify title status independently",
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
    "When fit is similar, higher trust (High, then Medium, then Low) ranks higher.",
    "Further tie-breakers: fewer warnings, lower price, then lower mileage.",
    "Price and mileage matter most as tie-breakers — not as the main reason a listing leads.",
)

_CONFIDENCE_FIELD_LABELS: dict[str, str] = {
    "confidence_level": "Trust level",
    "inferred_fields": "Fields inferred from listing text",
    "missing_fields": "Missing core details",
    "ambiguity_detected": "Unclear mileage in listing text",
    "mileage_conflict_detected": "Mileage mismatch between text and fields",
    "conflicting_signals": "Mixed positive and negative signals",
}


def _find_vehicle_profile(make: str, model: str) -> dict[str, Any] | None:
    from src.vehicles.vehicle_profile_loader import load_vehicle_profiles

    make_key = make.strip().casefold()
    model_key = model.strip().casefold()
    for vehicle in load_vehicle_profiles()["vehicles"]:
        if (
            vehicle["make"].strip().casefold() == make_key
            and vehicle["model"].strip().casefold() == model_key
        ):
            return vehicle
    return None


def _year_range_notes(
    vehicle: dict[str, Any],
    selected_year_range: dict[str, Any] | None,
) -> str | None:
    year_ranges = vehicle.get("year_ranges") or []
    if not year_ranges:
        return None
    if selected_year_range:
        for year_range in year_ranges:
            if (
                year_range.get("start_year") == selected_year_range.get("start_year")
                and year_range.get("end_year") == selected_year_range.get("end_year")
            ):
                notes = year_range.get("notes")
                if notes:
                    return str(notes).strip()
    notes = year_ranges[0].get("notes")
    return str(notes).strip() if notes else None


def _trait_summary(recommendation: dict[str, Any]) -> str | None:
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
    return None


def format_recommended_because(recommendation: dict[str, Any]) -> str:
    """Short summary for why a vehicle model was recommended (no circular fallback)."""
    notes = recommendation.get("notes")
    if notes and str(notes).strip():
        return str(notes).strip()

    trait_summary = _trait_summary(recommendation)
    if trait_summary:
        return trait_summary

    vehicle = _find_vehicle_profile(
        recommendation["make"],
        recommendation["model"],
    )
    if vehicle:
        profile_notes = _year_range_notes(
            vehicle,
            recommendation.get("selected_year_range"),
        )
        if profile_notes:
            return profile_notes

    return (
        f"Strong match for {recommendation['make']} {recommendation['model']} "
        f"based on your priorities."
    )


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
    """Compact facts row; missing price/mileage and dirty title are surfaced elsewhere."""
    parts: list[str] = []
    price = listing.get("price")
    if price is not None:
        parts.append(f"${int(price):,}")
    mileage = listing.get("mileage")
    if mileage is not None:
        parts.append(format_mileage(mileage))
    clean = listing.get("clean_title")
    if clean is True:
        parts.append("Clean title")
    elif clean is None:
        parts.append("Title undisclosed")
    return " · ".join(parts) if parts else "Details incomplete — see watchouts below"


def listing_has_missing_price(listing: dict[str, Any]) -> bool:
    return listing.get("price") is None


def listing_has_missing_mileage(listing: dict[str, Any]) -> bool:
    return listing.get("mileage") is None


def _looks_like_internal_listing_id(name: str) -> bool:
    lowered = name.casefold()
    return lowered.startswith(("adv_", "messy_", "good_", "sparse_", "budget_"))


def resolve_listing_display_name(
    entry: dict[str, Any],
    raw_listing: dict[str, Any] | None = None,
) -> str:
    """Buyer-facing listing label; never prefer internal demo IDs."""
    display_name = entry.get("display_name")
    if display_name and str(display_name).strip():
        return str(display_name).strip()

    listing = entry.get("listing") or {}
    for source in (listing, raw_listing or {}):
        for key in ("raw_title", "title"):
            value = source.get(key)
            if value and str(value).strip():
                return str(value).strip()

    parts = [
        str(listing["year"]),
        listing["make"],
        listing["model"],
    ]
    trim = listing.get("trim")
    if trim:
        parts.append(str(trim))
    ymmt = " ".join(parts)

    listing_name = str(entry.get("listing_name", "")).strip()
    if listing_name and not _looks_like_internal_listing_id(listing_name):
        return listing_name
    return ymmt


def detect_seller_title_conflict(
    raw_listing: dict[str, Any] | None,
    listing: dict[str, Any],
) -> bool:
    """True when title and description disagree on clean vs branded title."""
    if raw_listing is None:
        return False

    from src.listings.listing_normalizer import _resolved_title, detect_clean_title

    title = _resolved_title(raw_listing)
    description = raw_listing.get("description")
    description_text = (
        str(description).strip()
        if description is not None and str(description).strip()
        else None
    )
    if not title or not description_text:
        return False

    title_status = detect_clean_title(title, None)
    description_status = detect_clean_title(None, description_text)
    if title_status is None or description_status is None:
        return False
    return title_status != description_status


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


def build_watchouts(
    fit: dict[str, Any],
    listing: dict[str, Any],
    *,
    raw_listing: dict[str, Any] | None = None,
) -> list[str]:
    """Unified buyer-facing watchouts: warnings, negatives, and missing-field gaps."""
    candidates: list[str] = []

    if detect_seller_title_conflict(raw_listing, listing):
        candidates.append(SELLER_TITLE_CONFLICT_WARNING)

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


def format_confidence_breakdown(confidence: dict[str, Any]) -> list[tuple[str, str]]:
    """Buyer-friendly confidence lines for the scoring breakdown expander."""
    lines: list[tuple[str, str]] = []
    for key, value in confidence.items():
        label = _CONFIDENCE_FIELD_LABELS.get(key, key.replace("_", " ").title())
        if isinstance(value, bool):
            text = "Yes" if value else "No"
        elif isinstance(value, list):
            text = ", ".join(str(item) for item in value) if value else "None"
        else:
            text = str(value)
        lines.append((label, text))
    return lines


def build_ranking_explanation_lines() -> list[str]:
    return list(RANKING_ORDER_LINES)
