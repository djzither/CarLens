from __future__ import annotations

from typing import Any

MIN_COMPARE_LISTINGS = 2
MAX_COMPARE_LISTINGS = 4

_COMPARE_ID_SEP = "\x1f"
_COMPARE_KEY_PREFIX = "compare_"


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


def validate_compare_selection(count: int) -> str | None:
    if count < MIN_COMPARE_LISTINGS:
        return f"Select at least {MIN_COMPARE_LISTINGS} listings to compare."
    if count > MAX_COMPARE_LISTINGS:
        return f"Select at most {MAX_COMPARE_LISTINGS} listings to compare."
    return None


def _format_price(listing: dict[str, Any]) -> str:
    price = listing.get("price")
    if price is None:
        return "—"
    return f"${int(price):,}"


def _format_mileage(listing: dict[str, Any]) -> str:
    mileage = listing.get("mileage")
    if mileage is None:
        return "—"
    return f"{int(mileage):,}"


def _format_ymmt(listing: dict[str, Any]) -> str:
    parts = [str(listing["year"]), listing["make"], listing["model"]]
    trim = listing.get("trim")
    if trim:
        parts.append(str(trim))
    return " ".join(parts)


def _format_list(items: list[str]) -> str:
    if not items:
        return "—"
    return "\n".join(f"• {item}" for item in items)


def build_compare_row(entry: dict[str, Any]) -> dict[str, str]:
    """Build display values for a side-by-side listing comparison."""
    listing = entry["listing"]
    fit = entry["fit"]
    confidence = entry["confidence"]
    title = listing.get("raw_title") or entry.get("listing_name", "—")
    source = listing.get("listing_url") or listing.get("source") or "—"

    return {
        "listing_name": entry.get("listing_name", "—"),
        "title": str(title),
        "price": _format_price(listing),
        "year_make_model_trim": _format_ymmt(listing),
        "mileage": _format_mileage(listing),
        "fit_label": fit.get("fit_label", "—"),
        "score": f"{fit.get('fit_score', 0.0):.3f}",
        "confidence": confidence.get("confidence_level", "—"),
        "positive_reasons": _format_list(fit.get("positive_reasons") or []),
        "negative_reasons": _format_list(fit.get("negative_reasons") or []),
        "warnings": _format_list(fit.get("warnings") or []),
        "source_link": str(source),
    }


COMPARE_TABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("title", "Title"),
    ("price", "Price"),
    ("year_make_model_trim", "Year / make / model / trim"),
    ("mileage", "Mileage"),
    ("fit_label", "Fit label"),
    ("score", "Score"),
    ("confidence", "Confidence"),
    ("positive_reasons", "Positive reasons"),
    ("negative_reasons", "Negative reasons"),
    ("warnings", "Warnings"),
    ("source_link", "Source link"),
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
