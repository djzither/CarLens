from __future__ import annotations

from typing import Any

from src.listings.listing_quality_summary import (
    ListingQualityWarningsContext,
    build_listing_quality_summary,
)

MIN_COMPARE_LISTINGS = 2
MAX_COMPARE_LISTINGS = 3

_COMPARE_ID_SEP = "\x1f"
_COMPARE_KEY_PREFIX = "compare_"
_FAVORITE_KEY_PREFIX = "favorite_"

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
    "clean": "Clean (verified)",
    "dirty": "Issue reported",
    "unknown": "Unknown",
}

_FIT_QUALITY_RANK = {"strong": 0, "moderate": 1, "weak": 2}
_DATA_QUALITY_RANK = {"high": 0, "medium": 1, "low": 2}
_TITLE_CERTAINTY_RANK = {"clean": 0, "unknown": 1, "dirty": 2}
_CONFIDENCE_RANK = {"High": 0, "Medium": 1, "Low": 2}


def make_compare_id(make: str, model: str, listing_name: str) -> str:
    return f"{make}{_COMPARE_ID_SEP}{model}{_COMPARE_ID_SEP}{listing_name}"


def parse_compare_id(compare_id: str) -> tuple[str, str, str]:
    parts = compare_id.split(_COMPARE_ID_SEP, 2)
    if len(parts) != 3:
        raise ValueError(f"invalid compare id: {compare_id!r}")
    return parts[0], parts[1], parts[2]


def compare_checkbox_key(compare_id: str) -> str:
    return f"{_COMPARE_KEY_PREFIX}{compare_id}"


def compare_id_from_checkbox_key(key: str) -> str | None:
    if not key.startswith(_COMPARE_KEY_PREFIX):
        return None
    return key[len(_COMPARE_KEY_PREFIX) :]


def favorite_button_key(compare_id: str) -> str:
    return f"{_FAVORITE_KEY_PREFIX}{compare_id}"


def compare_id_from_favorite_key(key: str) -> str | None:
    if not key.startswith(_FAVORITE_KEY_PREFIX):
        return None
    return key[len(_FAVORITE_KEY_PREFIX) :]


def validate_compare_selection(count: int) -> str | None:
    if count < MIN_COMPARE_LISTINGS:
        return f"Select at least {MIN_COMPARE_LISTINGS} listings to compare."
    if count > MAX_COMPARE_LISTINGS:
        return f"Select at most {MAX_COMPARE_LISTINGS} listings to compare."
    return None


def _format_price(listing: dict[str, Any]) -> str:
    price = listing.get("price")
    if price is None:
        return "Not listed"
    return f"${int(price):,}"


def _format_mileage(listing: dict[str, Any]) -> str:
    mileage = listing.get("mileage")
    if mileage is None:
        return "Not listed"
    return f"{int(mileage):,} mi"


def _format_list(items: list[str]) -> str:
    if not items:
        return "—"
    return "\n".join(f"• {item}" for item in items)


def _provider_record_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
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


def quality_summary_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Fit vs data quality summary for compare rows (display only)."""
    record = _provider_record_for_entry(entry)
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


def _watchouts_for_compare(entry: dict[str, Any]) -> list[str]:
    fit = entry.get("fit") or {}
    listing = entry.get("listing") or {}
    items: list[str] = []
    if listing.get("price") is None:
        items.append("Price not listed")
    if listing.get("mileage") is None:
        items.append("Mileage not listed")
    for warning in fit.get("warnings") or []:
        text = str(warning).strip()
        if text:
            items.append(text)
    for reason in fit.get("negative_reasons") or []:
        text = str(reason).strip()
        if text:
            items.append(text)
    return items[:5]


def _short_listing_label(entry: dict[str, Any]) -> str:
    listing = entry.get("listing") or {}
    make = str(listing.get("make", "")).strip()
    model = str(listing.get("model", "")).strip()
    if make and model:
        return f"{make} {model}"
    return str(entry.get("listing_name", "This listing"))


def _join_beat_reasons(reasons: list[str]) -> str:
    if not reasons:
        return ""
    if len(reasons) == 1:
        return reasons[0]
    if len(reasons) == 2:
        return f"{reasons[0]} and {reasons[1]}"
    return ", ".join(reasons[:-1]) + f", and {reasons[-1]}"


def collect_beat_reasons(winner: dict[str, Any], other: dict[str, Any]) -> list[str]:
    """Human-readable reasons the winner outranks another listing (demo copy)."""
    w_listing = winner.get("listing") or {}
    o_listing = other.get("listing") or {}
    w_summary = quality_summary_for_entry(winner)
    o_summary = quality_summary_for_entry(other)
    reasons: list[str] = []

    w_title = str(w_summary.get("title_certainty", "unknown"))
    o_title = str(o_summary.get("title_certainty", "unknown"))
    if w_title == "clean" and o_title != "clean":
        reasons.append("verified title history")
    elif w_title == "unknown" and o_title == "dirty":
        reasons.append("no reported title issues")

    w_mileage = w_listing.get("mileage")
    o_mileage = o_listing.get("mileage")
    if (
        w_mileage is not None
        and o_mileage is not None
        and int(w_mileage) < int(o_mileage)
    ):
        reasons.append("lower mileage")

    w_fit = str(w_summary.get("fit_quality", "moderate"))
    o_fit = str(o_summary.get("fit_quality", "moderate"))
    if _FIT_QUALITY_RANK.get(w_fit, 1) < _FIT_QUALITY_RANK.get(o_fit, 1):
        reasons.append("stronger overall fit for your priorities")

    w_data = str(w_summary.get("data_quality_level", "medium"))
    o_data = str(o_summary.get("data_quality_level", "medium"))
    if _DATA_QUALITY_RANK.get(w_data, 1) < _DATA_QUALITY_RANK.get(o_data, 1):
        reasons.append("more complete and reliable listing data")

    w_conf = (winner.get("confidence") or {}).get("confidence_level")
    o_conf = (other.get("confidence") or {}).get("confidence_level")
    if (
        isinstance(w_conf, str)
        and isinstance(o_conf, str)
        and _CONFIDENCE_RANK.get(w_conf, 2) < _CONFIDENCE_RANK.get(o_conf, 2)
    ):
        reasons.append("higher data trust")

    w_price = w_listing.get("price")
    o_price = o_listing.get("price")
    if (
        w_fit == o_fit == "strong"
        and w_price is not None
        and o_price is not None
        and int(w_price) < int(o_price)
    ):
        reasons.append("a lower price at similar fit")

    return reasons[:2]


def generate_beats_other_sentence(winner: dict[str, Any], other: dict[str, Any]) -> str:
    """One-sentence comparison: why the winner beats another option."""
    label = _short_listing_label(winner)
    reasons = collect_beat_reasons(winner, other)
    if not reasons:
        return (
            f"This {label} ranks higher based on overall fit and listing quality."
        )
    joined = _join_beat_reasons(reasons)
    return f"This {label} ranks higher because it has {joined}."


def build_compare_row(entry: dict[str, Any]) -> dict[str, str]:
    """Build display values for a side-by-side listing comparison."""
    listing = entry["listing"]
    fit = entry["fit"]
    summary = quality_summary_for_entry(entry)
    provider_source = str(summary.get("source") or listing.get("source") or "—")
    if provider_source == "unknown":
        provider_source = "—"

    return {
        "fit_quality": _FIT_QUALITY_LABELS.get(
            str(summary.get("fit_quality", "")), "—"
        ),
        "data_quality": _DATA_QUALITY_LABELS.get(
            str(summary.get("data_quality_level", "")), "—"
        ),
        "price": _format_price(listing),
        "mileage": _format_mileage(listing),
        "title_certainty": _TITLE_CERTAINTY_LABELS.get(
            str(summary.get("title_certainty", "")), "—"
        ),
        "why_it_fits": _format_list(fit.get("positive_reasons") or []),
        "watchouts": _format_list(_watchouts_for_compare(entry)),
        "provider_source": provider_source,
        # Legacy keys kept for tests that assert formatting helpers
        "listing_name": entry.get("listing_name", "—"),
        "title": str(listing.get("raw_title") or entry.get("listing_name", "—")),
        "fit_label": str(fit.get("fit_label", "—")),
        "score": f"{fit.get('fit_score', 0.0):.3f}",
        "confidence": str(
            (entry.get("confidence") or {}).get("confidence_level", "—")
        ),
        "year_make_model_trim": " ".join(
            part
            for part in [
                str(listing.get("year", "")),
                str(listing.get("make", "")),
                str(listing.get("model", "")),
                str(listing.get("trim") or ""),
            ]
            if part
        ),
        "positive_reasons": _format_list(fit.get("positive_reasons") or []),
        "negative_reasons": _format_list(fit.get("negative_reasons") or []),
        "warnings": _format_list(fit.get("warnings") or []),
        "source_link": str(
            listing.get("listing_url") or listing.get("source") or "—"
        ),
    }


COMPARE_TABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("fit_quality", "Fit quality"),
    ("data_quality", "Data quality"),
    ("price", "Price"),
    ("mileage", "Mileage"),
    ("title_certainty", "Title certainty"),
    ("why_it_fits", "Why it fits"),
    ("watchouts", "Watchouts"),
    ("provider_source", "Provider"),
)


def collect_selected_compare_ids(session_state: dict[str, Any]) -> list[str]:
    selected: list[str] = []
    for key, value in session_state.items():
        if not value:
            continue
        compare_id = compare_id_from_checkbox_key(str(key))
        if compare_id is not None:
            selected.append(compare_id)
    return selected


def resolve_compare_entries(
    catalog: dict[str, dict[str, Any]],
    compare_ids: list[str],
) -> list[dict[str, Any]]:
    """Return catalog entries in the order the user selected them."""
    entries: list[dict[str, Any]] = []
    for compare_id in compare_ids:
        entry = catalog.get(compare_id)
        if entry is not None:
            entries.append(entry)
    return entries


def count_selected_compare(session_state: dict[str, Any]) -> int:
    return len(collect_selected_compare_ids(session_state))


FAVORITES_SESSION_KEY = "saved_listing_ids"


def get_saved_listing_ids(session_state: dict[str, Any]) -> set[str]:
    raw = session_state.get(FAVORITES_SESSION_KEY, [])
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw}


def is_listing_saved(session_state: dict[str, Any], compare_id: str) -> bool:
    return compare_id in get_saved_listing_ids(session_state)


def toggle_saved_listing(session_state: dict[str, Any], compare_id: str) -> bool:
    """Toggle favorite state; returns True when saved after toggle."""
    saved = get_saved_listing_ids(session_state)
    if compare_id in saved:
        saved.remove(compare_id)
        session_state[FAVORITES_SESSION_KEY] = sorted(saved)
        return False
    saved.add(compare_id)
    session_state[FAVORITES_SESSION_KEY] = sorted(saved)
    return True
