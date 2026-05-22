"""Auto.dev listing adapter with field-level normalization and warnings."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.listings.listing_normalizer import parse_mileage, parse_price
from src.listings.auto_dev_title import apply_auto_dev_title_fields

logger = logging.getLogger(__name__)

_AUTO_DEV_SOURCE = "auto.dev"

ADAPTER_WARNINGS_KEY = "_adapter_warnings"

_LOCATION_PLACEHOLDERS = frozenset(
    {
        "usa",
        "na",
        "unknown",
        "dealer online",
        "00000",
    }
)
_ALLOWED_DRIVE_TYPES = frozenset({"awd", "fwd", "rwd", "4wd"})
_DRIVE_TYPE_ALIASES = {
    "all-wheel drive": "awd",
    "all wheel drive": "awd",
    "front-wheel drive": "fwd",
    "front wheel drive": "fwd",
    "rear-wheel drive": "rwd",
    "rear wheel drive": "rwd",
    "four-wheel drive": "4wd",
    "four wheel drive": "4wd",
}
_YEAR_PATTERN = re.compile(r"^\s*((?:19|20)\d{2})\s*")
_YEAR_IN_TEXT_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _raw_value_repr(value: Any) -> str:
    return repr(value)


def _emit_adapter_warning(message: str, warnings: list[str]) -> None:
    warnings.append(message)
    logger.warning(message)


def _invalid_price_warning(value: Any) -> str:
    return f"Invalid price value: {_raw_value_repr(value)}"


def _invalid_mileage_warning(value: Any) -> str:
    return f"Invalid mileage value: {_raw_value_repr(value)}"


def _invalid_year_warning(value: Any) -> str:
    return f"Invalid year value: {_raw_value_repr(value)}"


def _rejected_placeholder_location_warning(value: Any) -> str:
    return f"Rejected placeholder location: {_raw_value_repr(value)}"


def _unexpected_drive_type_warning(value: Any) -> str:
    return f"Unexpected drive_type: {_raw_value_repr(value)}"


def _is_placeholder_location(text: str) -> bool:
    return text.casefold() in _LOCATION_PLACEHOLDERS


def _optional_price(value: Any) -> tuple[int | None, list[str]]:
    warnings: list[str] = []
    if value is None:
        return None, warnings
    if isinstance(value, bool):
        _emit_adapter_warning(_invalid_price_warning(value), warnings)
        return None, warnings

    parsed = parse_price(value)
    if parsed is not None:
        return parsed, warnings

    if isinstance(value, (int, float)):
        number = float(value)
        if number >= 0 and number.is_integer():
            return int(number), warnings

    if isinstance(value, str) and value.strip():
        _emit_adapter_warning(_invalid_price_warning(value), warnings)

    return None, warnings


def _optional_mileage(value: Any) -> tuple[int | None, list[str]]:
    warnings: list[str] = []
    if value is None:
        return None, warnings
    if isinstance(value, bool):
        _emit_adapter_warning(_invalid_mileage_warning(value), warnings)
        return None, warnings

    parsed = parse_mileage(value)
    if parsed is not None:
        return parsed, warnings

    if isinstance(value, (int, float)):
        number = float(value)
        if number >= 0 and number.is_integer():
            return int(number), warnings

    if isinstance(value, str) and value.strip():
        _emit_adapter_warning(_invalid_mileage_warning(value), warnings)

    return None, warnings


def _parse_year_token(token: str) -> int | None:
    match = _YEAR_PATTERN.match(token)
    if not match:
        return None
    year = int(match.group(1))
    if 1900 <= year <= 2100:
        return year
    return None


def _extract_year_from_text(text: Any) -> int | None:
    cleaned = _optional_str(text)
    if not cleaned:
        return None
    matches = list(_YEAR_IN_TEXT_PATTERN.finditer(cleaned))
    if not matches:
        return None
    year = int(matches[0].group(1))
    if 1900 <= year <= 2100:
        return year
    return None


def _optional_year(value: Any) -> tuple[int | None, list[str]]:
    warnings: list[str] = []
    if value is None:
        return None, warnings
    if isinstance(value, bool):
        _emit_adapter_warning(_invalid_year_warning(value), warnings)
        return None, warnings

    if isinstance(value, int):
        if 1900 <= value <= 2100:
            return value, warnings
        _emit_adapter_warning(_invalid_year_warning(value), warnings)
        return None, warnings

    if isinstance(value, float) and value.is_integer():
        year = int(value)
        if 1900 <= year <= 2100:
            return year, warnings
        _emit_adapter_warning(_invalid_year_warning(value), warnings)
        return None, warnings

    text = str(value).strip()
    if not text:
        return None, warnings

    if "-" in text:
        first_token = text.split("-", 1)[0].strip()
        parsed = _parse_year_token(first_token)
        if parsed is not None:
            return parsed, warnings
        _emit_adapter_warning(_invalid_year_warning(value), warnings)
        return None, warnings

    parsed = _parse_year_token(text)
    if parsed is not None:
        return parsed, warnings

    _emit_adapter_warning(_invalid_year_warning(value), warnings)
    return None, warnings


def _optional_location(value: Any) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    text = _optional_str(value)
    if not text:
        return None, warnings
    if _is_placeholder_location(text):
        _emit_adapter_warning(_rejected_placeholder_location_warning(value), warnings)
        return None, warnings
    return text, warnings


def _optional_drive_type(value: Any) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    text = _optional_str(value)
    if not text:
        return None, warnings

    canonical = text.casefold()
    if canonical in _ALLOWED_DRIVE_TYPES:
        return canonical, warnings

    alias = _DRIVE_TYPE_ALIASES.get(canonical)
    if alias is not None:
        return alias, warnings

    upper = text.upper()
    if upper in {"AWD", "FWD", "RWD", "4WD"}:
        return upper.casefold(), warnings

    _emit_adapter_warning(_unexpected_drive_type_warning(value), warnings)
    return None, warnings


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    target[key] = value


def _compose_title(
    *,
    year: int | None = None,
    make: Any,
    model: Any,
    trim: Any = None,
) -> str | None:
    parts: list[str] = []
    if year is not None:
        parts.append(str(year))
    for value in (make, model, trim):
        text = _optional_str(value)
        if text:
            parts.append(text)
    if not parts:
        return None
    return " ".join(parts)


def _format_location(city: Any, state: Any, zip_code: Any = None) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    for part in (city, state, zip_code):
        if part is None:
            continue
        _, part_warnings = _optional_location(part)
        if part_warnings:
            return None, part_warnings

    city_text = _optional_str(city)
    state_text = _optional_str(state)
    zip_text = _optional_str(zip_code)
    if city_text and state_text:
        location = f"{city_text}, {state_text}"
    elif city_text:
        location = city_text
    elif state_text:
        location = state_text
    else:
        location = None
    if location and zip_text:
        location = f"{location} {zip_text}"

    if location is None:
        return None, warnings
    return _optional_location(location)


def _resolve_year(
    *,
    vehicle_year: Any,
    title_candidates: list[Any],
) -> tuple[int | None, list[str]]:
    year, warnings = _optional_year(vehicle_year)
    if year is not None:
        return year, warnings

    for candidate in title_candidates:
        extracted = _extract_year_from_text(candidate)
        if extracted is not None:
            logger.debug(
                "year extracted from title fallback: %r -> %s",
                candidate,
                extracted,
            )
            return extracted, warnings

    return None, warnings


def _optional_distance_miles(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        miles = float(value)
        if miles < 0:
            return None
        return int(round(miles))
    return None


def pop_adapter_warnings(raw: dict[str, Any]) -> list[str]:
    """Remove and return adapter warnings stored on a raw listing."""
    warnings = raw.pop(ADAPTER_WARNINGS_KEY, [])
    if not isinstance(warnings, list):
        return []
    return [str(message) for message in warnings if message]


def adapt_auto_dev_listing(provider_listing: dict[str, Any]) -> dict[str, Any]:
    """Map an Auto.dev listing object to the CarLens raw listing shape."""
    if not isinstance(provider_listing, dict):
        raise ValueError("provider_listing must be a JSON object")

    vehicle = _nested_dict(provider_listing.get("vehicle"))
    retail = _nested_dict(provider_listing.get("retailListing"))
    wholesale = _nested_dict(provider_listing.get("wholesaleListing"))
    warnings: list[str] = []
    raw: dict[str, Any] = {"source": _AUTO_DEV_SOURCE}

    listing_id = _optional_str(provider_listing.get("vin")) or _optional_str(
        vehicle.get("vin")
    )
    _set_if_present(raw, "listing_id", listing_id)

    _set_if_present(raw, "make", vehicle.get("make"))
    _set_if_present(raw, "model", vehicle.get("model"))

    title_candidates = [
        provider_listing.get("title"),
        retail.get("heading"),
    ]
    year, year_warnings = _resolve_year(
        vehicle_year=vehicle.get("year"),
        title_candidates=title_candidates,
    )
    warnings.extend(year_warnings)
    if year is not None:
        raw["year"] = year

    _set_if_present(raw, "trim", vehicle.get("trim"))

    drive_type, drive_warnings = _optional_drive_type(vehicle.get("drivetrain"))
    warnings.extend(drive_warnings)
    _set_if_present(raw, "drive_type", drive_type)

    if "price" in retail:
        price, price_warnings = _optional_price(retail.get("price"))
        warnings.extend(price_warnings)
        if price is not None:
            raw["price"] = price

    mileage_value = retail.get("miles")
    if mileage_value is None:
        mileage_value = wholesale.get("miles")
    if mileage_value is not None:
        mileage, mileage_warnings = _optional_mileage(mileage_value)
        warnings.extend(mileage_warnings)
        if mileage is not None:
            raw["mileage"] = mileage

    title = _compose_title(
        year=year,
        make=vehicle.get("make"),
        model=vehicle.get("model"),
        trim=vehicle.get("trim"),
    )
    _set_if_present(raw, "title", title)

    _set_if_present(raw, "listing_url", retail.get("vdp"))
    _set_if_present(raw, "image_url", retail.get("primaryImage"))

    distance = provider_listing.get("distance")
    if distance is None:
        distance = retail.get("distance")
    distance_miles = _optional_distance_miles(distance)
    if distance_miles is not None:
        raw["distance_miles"] = distance_miles

    location, location_warnings = _format_location(
        retail.get("city"),
        retail.get("state"),
        retail.get("zip"),
    )
    warnings.extend(location_warnings)
    _set_if_present(raw, "location", location)

    title_diagnostics = apply_auto_dev_title_fields(
        raw,
        provider_listing=provider_listing,
    )
    if title_diagnostics["title_certainty"] == "unknown":
        logger.debug(
            "title_status unknown (Auto.dev did not provide explicit clean/dirty title fields)"
        )
    else:
        logger.debug(
            "title_status mapped from provider fields: %s",
            title_diagnostics["normalized_title_status"],
        )

    if warnings:
        raw[ADAPTER_WARNINGS_KEY] = warnings
    return raw
