"""Auto.dev title-status mapping and diagnostics (explicit provider fields only)."""

from __future__ import annotations

from typing import Any

from src.listings.provider_clean_title import apply_explicit_clean_title

TITLE_DIAGNOSTICS_KEY = "_auto_dev_title_diagnostics"

TitleStatus = str  # clean | dirty | unknown
TitleCertainty = str  # clean | dirty | unknown

_TITLE_KEY_MARKERS = (
    "title",
    "clean",
    "salvage",
    "brand",
    "rebuilt",
    "carfax",
    "autocheck",
    "history",
    "accident",
    "owner",
    "condition",
    "status",
)

_DIRTY_STATUS_VALUES = frozenset({
    "dirty",
    "salvage",
    "rebuilt",
    "branded",
    "junk",
    "flood",
    "lemon",
    "total loss",
    "totalloss",
})

_EXPLICIT_CLEAN_KEYS = (
    "cleanTitle",
    "clean_title",
    "carfaxCleanTitle",
    "carfax_clean_title",
    "autocheckCleanTitle",
    "autocheck_clean_title",
)

_EXPLICIT_STATUS_KEYS = (
    "titleStatus",
    "title_status",
    "titleBrand",
    "title_brand",
    "brandedTitle",
    "branded_title",
    "registrationStatus",
    "registration_status",
)


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_title_related_key(key: str) -> bool:
    lowered = key.casefold()
    return any(marker in lowered for marker in _TITLE_KEY_MARKERS)


def _walk_title_fields(
    value: Any,
    *,
    prefix: str,
    found: dict[str, Any],
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(child, dict):
                _walk_title_fields(child, prefix=path, found=found)
            elif _is_title_related_key(key) and child is not None and child != "":
                found[path] = child
    elif isinstance(value, list) and prefix:
        if value:
            found[prefix] = value


def collect_raw_title_fields(provider_listing: dict[str, Any]) -> dict[str, Any]:
    """Collect non-empty title-related fields from an Auto.dev listing payload."""
    found: dict[str, Any] = {}
    _walk_title_fields(provider_listing, prefix="", found=found)
    return dict(sorted(found.items()))


def _first_present(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def _coerce_optional_bool(value: Any) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1", "clean"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _status_value_is_dirty(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    text = str(value).strip().casefold()
    if not text:
        return False
    if text in _DIRTY_STATUS_VALUES:
        return True
    return any(token in text for token in _DIRTY_STATUS_VALUES)


def _explicit_clean_title_value(provider_listing: dict[str, Any]) -> bool | None:
    retail = _nested_dict(provider_listing.get("retailListing"))
    wholesale = _nested_dict(provider_listing.get("wholesaleListing"))
    history = _nested_dict(provider_listing.get("history"))

    for block in (retail, wholesale, history, provider_listing):
        raw_value = _first_present(block, _EXPLICIT_CLEAN_KEYS)
        coerced = _coerce_optional_bool(raw_value)
        if coerced is not None:
            return coerced
    return None


def _explicit_dirty_status_value(provider_listing: dict[str, Any]) -> bool:
    retail = _nested_dict(provider_listing.get("retailListing"))
    wholesale = _nested_dict(provider_listing.get("wholesaleListing"))
    history = _nested_dict(provider_listing.get("history"))
    vehicle = _nested_dict(provider_listing.get("vehicle"))

    for block in (retail, wholesale, history, vehicle, provider_listing):
        for key in _EXPLICIT_STATUS_KEYS:
            if key in block and _status_value_is_dirty(block.get(key)):
                return True
    return False


def title_certainty_from_status(title_status: str) -> TitleCertainty:
    if title_status == "clean":
        return "clean"
    if title_status == "dirty":
        return "dirty"
    return "unknown"


def build_title_diagnostics(
    *,
    provider_listing: dict[str, Any],
    title_status: str,
) -> dict[str, Any]:
    certainty = title_certainty_from_status(title_status)
    return {
        "raw_title_fields_found": collect_raw_title_fields(provider_listing),
        "normalized_title_status": title_status,
        "title_certainty": certainty,
    }


def apply_auto_dev_title_fields(
    raw: dict[str, Any],
    *,
    provider_listing: dict[str, Any],
) -> dict[str, Any]:
    """
    Map explicit Auto.dev title signals onto the raw listing.

    Does not infer clean title from marketing text or composed headings.
    """
    clean_explicit = _explicit_clean_title_value(provider_listing)
    dirty_explicit = _explicit_dirty_status_value(provider_listing)

    if clean_explicit is True and not dirty_explicit:
        apply_explicit_clean_title(raw, True)
        title_status = "clean"
    elif clean_explicit is False or dirty_explicit:
        apply_explicit_clean_title(raw, False)
        title_status = "dirty"
    else:
        title_status = "unknown"

    raw["title_status"] = title_status
    diagnostics = build_title_diagnostics(
        provider_listing=provider_listing,
        title_status=title_status,
    )
    raw[TITLE_DIAGNOSTICS_KEY] = diagnostics
    return diagnostics


def pop_title_diagnostics(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Remove and return title diagnostics stored during adaptation."""
    value = raw.pop(TITLE_DIAGNOSTICS_KEY, None)
    return value if isinstance(value, dict) else None


def peek_title_diagnostics(raw: dict[str, Any]) -> dict[str, Any] | None:
    value = raw.get(TITLE_DIAGNOSTICS_KEY)
    return value if isinstance(value, dict) else None


def format_title_diagnostics_provider_note(
    entry_id: str,
    diagnostics: dict[str, Any],
) -> str:
    """Single provider warning summarizing title field coverage."""
    fields = diagnostics.get("raw_title_fields_found") or {}
    field_names = ", ".join(sorted(fields.keys())) if fields else "none"
    return (
        f"{entry_id}: title diagnostics "
        f"(status={diagnostics.get('normalized_title_status')}, "
        f"certainty={diagnostics.get('title_certainty')}, "
        f"provider_fields={field_names})"
    )
