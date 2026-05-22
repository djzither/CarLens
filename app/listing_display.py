"""Pure helpers for Streamlit listing summary and ranking copy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.listings.listing_fit import (
    DIRTY_TITLE_WARNING,
    MISSING_DRIVE_TYPE_WARNING,
    MISSING_MILEAGE_WARNING,
    MISSING_PRICE_WARNING,
    MISSING_TITLE_WARNING,
    NOT_AWD_WARNING,
)
from src.listings.listing_reasons import STRONG_MODEL_MATCH

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

CAUTION_PREFIX = "⚠️ CAUTION:"


def format_caution_warning(detail: str) -> str:
    """Buyer-facing caution line with a consistent prefix."""
    text = str(detail).strip()
    if text.startswith(CAUTION_PREFIX):
        return text
    if text.startswith("⚠️ CAUTION"):
        text = text.split(":", 1)[-1].strip()
    return f"{CAUTION_PREFIX} {text}"


WATCHOUT_MISSING_PRICE = format_caution_warning(
    "Price not listed — cannot verify budget fit"
)
WATCHOUT_MISSING_MILEAGE = format_caution_warning(
    "Mileage not listed — cannot verify wear/usage"
)
WATCHOUT_VERIFY_TITLE = format_caution_warning("Verify title before purchase")
STRONG_FIT_LOW_CONFIDENCE_HEADLINE = "⚠ Strong fit but low data confidence"
STRONG_FIT_LOW_CONFIDENCE_CAPTION = (
    "Good overall match but missing important information. "
    "Verify details before purchase."
)
DIRTY_TITLE_BANNER = WATCHOUT_VERIFY_TITLE
SELLER_TITLE_CONFLICT_WARNING = format_caution_warning(
    "Seller title/description conflict — verify title before purchase"
)

TITLE_DIRTY_HEADLINE = "🚨 Branded/dirty title reported"
TITLE_DIRTY_DETAIL = "May significantly affect resale and financing"
TITLE_UNKNOWN_HEADLINE = "⚠️ Title history unavailable"
TITLE_UNKNOWN_DETAIL = "Ask seller for title documentation"
AUTO_DEV_TITLE_UNKNOWN_DETAIL = (
    "Title status not provided by Auto.dev — verify before purchase"
)
TITLE_CLEAN_HEADLINE = "✅ Clean title verified"

AlertTier = Literal["red", "yellow", "info"]
MAX_WATCHOUTS_VISIBLE = 4

_INFO_MILEAGE_INFERRED = "ℹ️ Mileage inferred from listing text"
_INFO_PROVIDER_LIMITED = "ℹ️ Limited provider data — verify key fields independently"


@dataclass(frozen=True)
class ListingCardAlert:
    """One deduplicated buyer-facing alert on a listing card."""

    tier: AlertTier
    group: str
    headline: str
    detail: str | None = None

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

SUMMARY_BADGE_TOP_PICK: tuple[str, str] = (
    "🏆 TOP PICK",
    "Best overall value and reliability",
)
SUMMARY_BADGE_CAUTION: tuple[str, str] = (
    "⚠️ CAUTION",
    "Verify title before purchase",
)  # subtitle only; use format_summary_badge_line for full caution text
SUMMARY_BADGE_BUDGET: tuple[str, str] = (
    "💰 BUDGET OPTION",
    "Lowest-cost strong match",
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

    make = recommendation.get("make")
    model = recommendation.get("model")
    if not make or not model:
        return "See listing fit and trust details below."

    vehicle = _find_vehicle_profile(
        make,
        model,
    )
    if vehicle:
        profile_notes = _year_range_notes(
            vehicle,
            recommendation.get("selected_year_range"),
        )
        if profile_notes:
            return profile_notes

    return (
        f"Strong match for {make} {model} "
        f"based on your priorities."
    )


def _top_trait_phrase(make: str, model: str) -> str:
    vehicle = _find_vehicle_profile(make, model)
    if not vehicle:
        return "solid value"
    trait_names: list[str] = []
    for trait in vehicle.get("traits") or []:
        name = str(trait.get("name", "")).replace("_", " ").strip()
        if name:
            trait_names.append(name)
        if len(trait_names) >= 2:
            break
    if not trait_names:
        return "solid value"
    if len(trait_names) == 1:
        return trait_names[0]
    return f"{trait_names[0]} and {trait_names[1]}"


def format_positive_reason_display(
    reason: str,
    *,
    make: str,
    model: str,
    listing: dict[str, Any],
) -> str:
    """Human-readable positive reason; upstream signal strings stay unchanged."""
    if reason == STRONG_MODEL_MATCH:
        traits = _top_trait_phrase(make, model)
        return (
            f"{make} {model} is a strong match because it is known for "
            f"{traits} and typically fits this budget range."
        )
    if reason == "Within recommended year range":
        year = listing.get("year")
        if year is not None:
            return (
                f"Model year {year} falls within the recommended years for "
                f"this {make} {model}."
            )
        return (
            f"Model year is within the recommended range for this "
            f"{make} {model}."
        )
    if reason == "Under budget":
        price = listing.get("price")
        if price is not None:
            return (
                f"Listed at {format_price(price)}, which comfortably fits "
                f"your budget."
            )
        return "Price comfortably fits your budget."
    if reason == "Mileage within preferred range":
        mileage = listing.get("mileage")
        if mileage is not None and listing.get("price") is not None:
            return (
                "This listing is especially attractive because mileage is low "
                f"({format_compact_mileage(mileage)}) and price "
                f"({format_compact_price(listing['price'])}) comfortably "
                f"fit your budget."
            )
        return (
            "This listing is especially attractive because mileage is low "
            "and price comfortably fits your budget."
        )
    if reason == "Matches requested AWD":
        return "Meets your all-wheel drive requirement."
    return reason


def format_positive_reasons_for_display(
    positives: list[str],
    *,
    make: str,
    model: str,
    listing: dict[str, Any],
    fit: dict[str, Any] | None = None,
) -> list[str]:
    lines = [
        format_positive_reason_display(
            reason,
            make=make,
            model=model,
            listing=listing,
        )
        for reason in positives
    ]
    if (
        listing.get("clean_title") is True
        and fit is not None
        and not has_major_warnings(fit)
        and not any("title" in line.casefold() for line in lines)
    ):
        lines.append("Clean title with no major risks detected.")
    return lines


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


def format_compact_price(price: int | float | None) -> str:
    if price is None:
        return "Price N/A"
    amount = int(price)
    if amount >= 1_000:
        thousands = amount / 1_000
        if amount % 1_000 == 0:
            return f"${int(thousands)}k"
        return f"${thousands:.1f}k"
    return f"${amount:,}"


def format_compact_mileage(mileage: int | float | None) -> str:
    if mileage is None:
        return "mi N/A"
    miles = int(mileage)
    if miles >= 1_000:
        thousands = miles / 1_000
        if miles % 1_000 == 0:
            return f"{int(thousands)}k mi"
        return f"{thousands:.1f}k mi"
    return f"{miles:,} mi"


def format_fit_percent(fit: dict[str, Any]) -> str:
    score = float(fit.get("fit_score", 0.0))
    return f"{int(round(score * 100))}% fit"


def format_fit_score_display(fit: dict[str, Any]) -> str:
    """Buyer-facing fit score (0–100); label is shown separately."""
    score = float(fit.get("fit_score", 0.0))
    return f"{int(round(score * 100))}%"


UNMATCHED_SECTION_INTRO = (
    "These listings did not match any recommended vehicle model. "
    "They are shown separately and are not ranked against your top picks."
)


def format_card_fit_summary(fit: dict[str, Any]) -> str:
    """Single-line fit label + score for listing cards."""
    label = str(fit.get("fit_label", "—"))
    return f"{label} · {format_fit_score_display(fit)} score"


def format_card_scoring_reasons(fit: dict[str, Any], *, limit: int = 3) -> list[str]:
    """Short scoring rationale bullets for the card surface (full list stays in expander)."""
    reasons = [str(item).strip() for item in (fit.get("reasons") or []) if str(item).strip()]
    return reasons[:limit]


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


_DEMO_ID_PREFIXES = (
    "adv_",
    "messy_",
    "sparse_",
    "good_",
    "budget_",
    "over_",
    "dirty_",
    "out_of_",
    "high_",
    "stacked_",
    "low_",
    "missing_",
    "wrong_",
    "cheap_",
)


def _looks_like_internal_listing_id(name: str) -> bool:
    lowered = name.casefold()
    return lowered.startswith(_DEMO_ID_PREFIXES)


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


def _normalize_watchout_message(text: str) -> str:
    """Map scoring warnings and field gaps to consistent caution-prefixed copy."""
    group = _watchout_dedupe_group(text)
    if group == "mileage_missing":
        return WATCHOUT_MISSING_MILEAGE
    if group == "price_missing":
        return WATCHOUT_MISSING_PRICE
    if group in ("title_dirty", "title_undisclosed"):
        return WATCHOUT_VERIFY_TITLE
    if group == "seller_title_conflict":
        return SELLER_TITLE_CONFLICT_WARNING
    if str(text).strip().startswith(CAUTION_PREFIX):
        return str(text).strip()
    return str(text).strip()


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

    for warning in fit.get("warnings") or []:
        candidates.append(_normalize_watchout_message(warning))
    for reason in fit.get("negative_reasons") or []:
        candidates.append(_normalize_watchout_message(reason))

    return _dedupe_watchouts(candidates)


def _resolve_trust_explanation(confidence: dict[str, Any]) -> str:
    """Short parenthetical reason for the trust level (data quality only)."""
    level = confidence.get("confidence_level")
    missing = list(confidence.get("missing_fields") or [])
    inferred = list(confidence.get("inferred_fields") or [])

    if level == "High" and not missing and not inferred:
        return "all core fields provided"
    if level == "Low" and len(missing) >= 2:
        return "multiple missing fields"
    if "clean_title" in missing:
        return "title unavailable"
    if "mileage" in inferred:
        return "mileage inferred"
    if "price" in inferred:
        return "price inferred"
    if confidence.get("ambiguity_detected"):
        return "unclear mileage in listing text"
    if confidence.get("mileage_conflict_detected"):
        return "mileage mismatch"
    if confidence.get("conflicting_signals"):
        return "mixed positive and negative signals"
    if missing:
        return f"{str(missing[0]).replace('_', ' ')} unavailable"
    if inferred:
        return f"{str(inferred[0]).replace('_', ' ')} inferred"
    if level == "Medium":
        return "some listing details missing or inferred"
    if level == "Low":
        return "multiple listing gaps"
    return "review listing details"


def format_trust_with_explanation(confidence: dict[str, Any]) -> str:
    level = str(confidence.get("confidence_level", "Low"))
    return f"{level} trust ({_resolve_trust_explanation(confidence)})"


def format_title_status_block(
    title_certainty: str,
    *,
    source: str | None = None,
) -> str | None:
    """Dedicated title-state copy (shown once on the card)."""
    if title_certainty == "clean":
        return f"**{TITLE_CLEAN_HEADLINE}**"
    if title_certainty == "dirty":
        return f"**{TITLE_DIRTY_HEADLINE}**\n\n_{TITLE_DIRTY_DETAIL}_"
    if title_certainty == "unknown":
        detail = TITLE_UNKNOWN_DETAIL
        if source and str(source).casefold() == "auto.dev":
            detail = AUTO_DEV_TITLE_UNKNOWN_DETAIL
        return f"**{TITLE_UNKNOWN_HEADLINE}**\n\n_{detail}_"
    return None


def format_title_certainty_display(
    title_certainty: str,
    *,
    source: str | None = None,
) -> str:
    """Short title line for CLI summaries."""
    if title_certainty == "clean":
        return "Clean"
    if title_certainty == "dirty":
        return "Dirty / branded"
    if title_certainty == "unknown" and source and str(source).casefold() == "auto.dev":
        return AUTO_DEV_TITLE_UNKNOWN_DETAIL
    if title_certainty == "unknown":
        return "Unknown"
    return title_certainty


def title_certainty_from_listing(listing: dict[str, Any]) -> str:
    clean = listing.get("clean_title")
    if clean is True:
        return "clean"
    if clean is False:
        return "dirty"
    return "unknown"


def _alert_from_watchout_text(text: str) -> ListingCardAlert | None:
    group = _watchout_dedupe_group(text)
    if group == "title_dirty":
        return ListingCardAlert("red", group, TITLE_DIRTY_HEADLINE, TITLE_DIRTY_DETAIL)
    if group == "title_undisclosed":
        return ListingCardAlert(
            "yellow",
            "title_unknown",
            TITLE_UNKNOWN_HEADLINE,
            TITLE_UNKNOWN_DETAIL,
        )
    if group == "price_missing":
        return ListingCardAlert("yellow", group, WATCHOUT_MISSING_PRICE, None)
    if group == "mileage_missing":
        return ListingCardAlert("yellow", group, WATCHOUT_MISSING_MILEAGE, None)
    if group == "seller_title_conflict":
        return ListingCardAlert("yellow", group, SELLER_TITLE_CONFLICT_WARNING, None)
    if warning_is_major(text):
        return ListingCardAlert("red", group or "major_risk", str(text).strip(), None)
    if group in ("awd_requirement",):
        return ListingCardAlert("yellow", group, str(text).strip(), None)
    if group:
        return ListingCardAlert("yellow", group, str(text).strip(), None)
    return None


def build_listing_card_alerts(
    entry: dict[str, Any],
    *,
    quality_summary: dict[str, Any],
    confidence: dict[str, Any] | None = None,
    fit: dict[str, Any] | None = None,
    listing: dict[str, Any] | None = None,
    raw_listing: dict[str, Any] | None = None,
) -> list[ListingCardAlert]:
    """Collect deduplicated card alerts (title, gaps, major risks, info notes)."""
    listing = listing or entry.get("listing") or {}
    fit = fit or entry.get("fit") or {}
    confidence = confidence or entry.get("confidence") or fit.get("confidence") or {}
    raw_listing = raw_listing if raw_listing is not None else entry.get("raw_listing")

    alerts: list[ListingCardAlert] = []
    seen_groups: set[str] = set()

    def add(alert: ListingCardAlert) -> None:
        if alert.group in seen_groups:
            return
        seen_groups.add(alert.group)
        alerts.append(alert)

    title_certainty = str(quality_summary.get("title_certainty", ""))
    if title_certainty == "dirty":
        add(
            ListingCardAlert(
                "red",
                "title_dirty",
                TITLE_DIRTY_HEADLINE,
                TITLE_DIRTY_DETAIL,
            )
        )
    elif title_certainty == "unknown":
        source = str(listing.get("source") or quality_summary.get("source") or "")
        unknown_detail = TITLE_UNKNOWN_DETAIL
        if source.casefold() == "auto.dev":
            unknown_detail = AUTO_DEV_TITLE_UNKNOWN_DETAIL
        add(
            ListingCardAlert(
                "yellow",
                "title_unknown",
                TITLE_UNKNOWN_HEADLINE,
                unknown_detail,
            )
        )
    elif title_certainty == "clean":
        add(ListingCardAlert("info", "title_clean", TITLE_CLEAN_HEADLINE, None))

    if listing.get("price") is None:
        add(ListingCardAlert("yellow", "price_missing", WATCHOUT_MISSING_PRICE, None))
    if listing.get("mileage") is None:
        add(ListingCardAlert("yellow", "mileage_missing", WATCHOUT_MISSING_MILEAGE, None))

    if detect_seller_title_conflict(raw_listing, listing):
        add(
            ListingCardAlert(
                "yellow",
                "seller_title_conflict",
                SELLER_TITLE_CONFLICT_WARNING,
                None,
            )
        )

    if shows_strong_fit_low_confidence_warning(fit, confidence):
        add(
            ListingCardAlert(
                "yellow",
                "strong_fit_low_trust",
                STRONG_FIT_LOW_CONFIDENCE_HEADLINE,
                STRONG_FIT_LOW_CONFIDENCE_CAPTION,
            )
        )

    inferred = confidence.get("inferred_fields") or []
    if "mileage" in inferred and "mileage_inferred" not in seen_groups:
        add(ListingCardAlert("info", "mileage_inferred", _INFO_MILEAGE_INFERRED, None))

    provider_warnings = entry.get("provider_warnings")
    if isinstance(provider_warnings, list) and provider_warnings:
        add(ListingCardAlert("info", "provider_limited", _INFO_PROVIDER_LIMITED, None))

    for warning in fit.get("warnings") or []:
        mapped = _alert_from_watchout_text(str(warning))
        if mapped:
            add(mapped)
    for reason in fit.get("negative_reasons") or []:
        mapped = _alert_from_watchout_text(str(reason))
        if mapped:
            add(mapped)

    return alerts


def banner_alerts(alerts: list[ListingCardAlert]) -> list[ListingCardAlert]:
    """Top-of-card banners (exclude title blocks shown separately)."""
    return [alert for alert in alerts if not alert.group.startswith("title_")]


def title_status_alert(alerts: list[ListingCardAlert]) -> ListingCardAlert | None:
    for alert in alerts:
        if alert.group.startswith("title_"):
            return alert
    return None


def suppressed_watchout_groups(alerts: list[ListingCardAlert]) -> set[str]:
    """Watchout topics already surfaced elsewhere on the card."""
    groups = {alert.group for alert in alerts}
    if "title_dirty" in groups or "title_unknown" in groups or "title_clean" in groups:
        groups |= {"title_dirty", "title_undisclosed", "title_clean"}
    return groups


def filter_watchouts_for_card(
    watchouts: list[str],
    alerts: list[ListingCardAlert],
    *,
    max_visible: int = MAX_WATCHOUTS_VISIBLE,
) -> tuple[list[str], list[str]]:
    """Drop watchouts already shown; cap visible count."""
    suppressed = suppressed_watchout_groups(alerts)
    filtered: list[str] = []
    for item in watchouts:
        group = _watchout_dedupe_group(item)
        if group is not None and group in suppressed:
            continue
        filtered.append(item)
    filtered = _dedupe_watchouts(filtered)
    visible = filtered[:max_visible]
    overflow = filtered[max_visible:]
    return visible, overflow


def format_additional_notes_label(count: int) -> str:
    return f"Additional notes ({count})"


def listing_source_url(listing: dict[str, Any]) -> str | None:
    """Return a safe listing URL when explicitly provided."""
    url = listing.get("listing_url")
    if url is None:
        return None
    text = str(url).strip()
    if text.startswith(("http://", "https://")):
        return text
    return None


_SOURCE_LABELS: dict[str, str] = {
    "facebook_marketplace": "Facebook Marketplace",
    "craigslist": "Craigslist",
    "autotrader": "AutoTrader",
    "cars.com": "Cars.com",
    "auto.dev": "Auto.dev",
    "marketcheck": "MarketCheck",
}


def format_listing_source_markdown(listing: dict[str, Any]) -> str:
    """Markdown for the listing source line on a card."""
    url = listing_source_url(listing)
    source = listing.get("source")
    source_label = _SOURCE_LABELS.get(str(source), str(source)) if source else None
    if url and source_label:
        return f"**Source:** {source_label} · [View listing]({url})"
    if url:
        return f"[View listing]({url})"
    if source_label:
        return f"**Source:** {source_label}"
    return "No source link"


def has_dirty_title(listing: dict[str, Any]) -> bool:
    return listing.get("clean_title") is False


def confidence_level_from_entry(
    fit: dict[str, Any],
    confidence: dict[str, Any] | None = None,
) -> str:
    conf = confidence or fit.get("confidence") or {}
    return str(conf.get("confidence_level", fit.get("confidence_level", "Low")))


def shows_strong_fit_low_confidence_warning(
    fit: dict[str, Any],
    confidence: dict[str, Any] | None = None,
) -> bool:
    """True when fit is strong but trust/data confidence is low."""
    return (
        fit.get("fit_label") == "Strong fit"
        and confidence_level_from_entry(fit, confidence) == "Low"
    )


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


def listing_needs_caution_badge(
    entry: dict[str, Any],
    *,
    watchouts: list[str] | None = None,
) -> bool:
    listing = entry["listing"]
    fit = entry["fit"]
    if listing.get("clean_title") is False:
        return True
    if has_major_warnings(fit):
        return True
    if watchouts is None:
        watchouts = build_watchouts(
            fit,
            listing,
            raw_listing=entry.get("raw_listing"),
        )
    for item in watchouts:
        lowered = item.casefold()
        if "title" in lowered or "verify" in lowered:
            return True
    return False


def resolve_listing_summary_badge(
    entry: dict[str, Any],
    *,
    rank: int = 1,
    is_budget_option: bool = False,
    alerts: list[ListingCardAlert] | None = None,
) -> tuple[str, str] | None:
    if rank == 1 and qualifies_as_top_pick(entry):
        return SUMMARY_BADGE_TOP_PICK
    title_handled = alerts and any(
        alert.group in ("title_dirty", "title_unknown") for alert in alerts
    )
    if not title_handled and listing_needs_caution_badge(entry):
        return SUMMARY_BADGE_CAUTION
    if is_budget_option:
        return SUMMARY_BADGE_BUDGET
    return None


def format_summary_badge_line(badge: tuple[str, str] | None) -> str | None:
    if badge is None:
        return None
    label, subtitle = badge
    if label == "⚠️ CAUTION":
        return format_caution_warning(subtitle)
    return f"**{label}:** {subtitle}"


def budget_option_listing_names(entries: list[dict[str, Any]]) -> set[str]:
    """Listing names tied for lowest price among strong, under-budget listings."""
    candidates: list[tuple[int, str]] = []
    for entry in entries:
        fit = entry["fit"]
        listing = entry["listing"]
        if fit.get("fit_label") != "Strong fit":
            continue
        price = listing.get("price")
        if price is None:
            continue
        positives = fit.get("positive_reasons") or []
        if "Under budget" not in positives:
            continue
        candidates.append((int(price), entry["listing_name"]))
    if not candidates:
        return set()
    min_price = min(price for price, _ in candidates)
    return {name for price, name in candidates if price == min_price}


def format_compact_listing_header(
    entry: dict[str, Any],
    *,
    rank: int,
    raw_listing: dict[str, Any] | None = None,
) -> tuple[str, str]:
    listing = entry["listing"]
    fit = entry["fit"]
    confidence = entry.get("confidence") or fit.get("confidence") or {}
    display_label = resolve_listing_display_name(entry, raw_listing)
    short_label = f"{listing['make']} {listing['model']}"
    if short_label.casefold() not in display_label.casefold():
        title_line = f"#{rank} {display_label}"
    else:
        title_line = f"#{rank} {short_label}"
    stats = " | ".join(
        [
            format_trust_with_explanation(confidence),
            format_compact_price(listing.get("price")),
            format_compact_mileage(listing.get("mileage")),
        ]
    )
    return title_line, stats


def format_listing_card_tagline(
    entry: dict[str, Any],
    *,
    rank: int = 1,
    is_budget_option: bool = False,
) -> str:
    listing = entry["listing"]
    fit = entry["fit"]
    make = str(listing["make"])
    model = str(listing["model"])

    if rank == 1 and qualifies_as_top_pick(entry):
        trait = _top_trait_phrase(make, model)
        return (
            f"Top overall choice with strong {trait} and no red flags."
        )
    if listing_needs_caution_badge(entry):
        return "Review title and listing details carefully before committing."
    if is_budget_option:
        return (
            "Strong match at the lowest price among comparable listings "
            "in this group."
        )
    if fit.get("fit_label") == "Strong fit":
        return (
            f"Solid {make} {model} option that aligns with your priorities."
        )
    if fit.get("fit_label") == "Moderate fit":
        return "Acceptable match — weigh watchouts against price and mileage."
    return "Weaker match for this recommendation — compare alternatives first."


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


_FIT_QUALITY_LABELS: dict[str, str] = {
    "strong": "Strong",
    "moderate": "Moderate",
    "weak": "Weak",
}

_DATA_QUALITY_LABELS: dict[str, str] = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

_TITLE_CERTAINTY_LABELS: dict[str, str] = {
    "clean": "Clean",
    "dirty": "Issue reported",
    "unknown": "Unknown",
}


def build_provider_record_for_quality(entry: dict[str, Any]) -> dict[str, Any]:
    """Build a provider-style record for :func:`build_listing_quality_summary`."""
    from src.listings.providers.provenance import present_field_names

    listing = entry.get("listing") or {}
    raw = entry.get("raw_listing") or listing
    provider_name = (
        entry.get("provider_name")
        or entry.get("provider")
        or listing.get("source")
        or "unknown"
    )
    raw_fields = entry.get("provider_raw_fields")
    if not isinstance(raw_fields, list):
        raw_fields = present_field_names(raw if isinstance(raw, dict) else listing)
    return {
        "id": entry.get("listing_name", ""),
        "listing": listing,
        "provider_name": str(provider_name),
        "provider_listing_id": str(
            entry.get("provider_listing_id") or entry.get("listing_name", "")
        ),
        "provider_raw_fields": list(raw_fields),
    }


def resolve_listing_quality_summary(entry: dict[str, Any]) -> dict[str, Any]:
    """Compute fit vs data quality summary for a ranked listing card."""
    from src.listings.listing_quality_summary import (
        ListingQualityWarningsContext,
        build_listing_quality_summary,
    )

    record = build_provider_record_for_quality(entry)
    provider_warnings = entry.get("provider_warnings")
    ctx = ListingQualityWarningsContext(
        provider_warnings=list(provider_warnings)
        if isinstance(provider_warnings, list)
        else []
    )
    return build_listing_quality_summary(
        record,
        fit=entry.get("fit"),
        warnings_context=ctx,
    )


def format_provider_name_label(provider_name: str) -> str:
    key = str(provider_name).strip()
    if not key or key == "unknown":
        return "Unknown"
    return _SOURCE_LABELS.get(key, key.replace("_", " ").title())


def format_listing_quality_metrics(summary: dict[str, Any]) -> str:
    """Single compact line: fit and data quality (provider shown separately)."""
    fit = _FIT_QUALITY_LABELS.get(str(summary.get("fit_quality", "")), "—")
    data = _DATA_QUALITY_LABELS.get(str(summary.get("data_quality_level", "")), "—")
    return f"**Fit:** {fit} · **Data quality:** {data}"


_PROVIDER_MARKS: dict[str, str] = {
    "auto.dev": "◆",
    "marketcheck": "◆",
    "facebook_marketplace": "◇",
    "craigslist": "◇",
}


def format_provider_attribution_html(entry: dict[str, Any]) -> str | None:
    """Subtle provider source line for listing cards (no external assets)."""
    listing = entry.get("listing") or {}
    source = (
        entry.get("provider_name")
        or entry.get("provider")
        or listing.get("source")
    )
    if not source or str(source).strip().casefold() in ("", "unknown"):
        return None
    key = str(source).strip()
    label = format_provider_name_label(key)
    mark = _PROVIDER_MARKS.get(key, "")
    prefix = f"{mark} " if mark else ""
    return (
        f"<p style='margin:0.15rem 0 0;color:#6b7280;font-size:0.78rem;"
        f"letter-spacing:0.02em'>{prefix}via {label}</p>"
    )


def format_listing_data_details_lines(summary: dict[str, Any]) -> list[str]:
    """Expander copy: completeness and field coverage (not raw provenance)."""
    completeness = float(summary.get("data_completeness", 0.0))
    pct = int(round(completeness * 100))
    title = _TITLE_CERTAINTY_LABELS.get(str(summary.get("title_certainty", "")), "—")
    lines = [
        f"Data completeness: {pct}%",
        f"Title certainty: {title}",
    ]
    provided = summary.get("provided_fields") or []
    unavailable = summary.get("unavailable_fields") or []
    if provided:
        lines.append(f"Provided: {', '.join(str(f) for f in provided)}")
    if unavailable:
        lines.append(f"Unavailable: {', '.join(str(f) for f in unavailable)}")
    data_level = _DATA_QUALITY_LABELS.get(
        str(summary.get("data_quality_level", "")),
        "—",
    )
    lines.append(f"Data quality level: {data_level}")
    return lines
