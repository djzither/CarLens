"""Auto.dev listing adapter with field-level normalization and warnings."""

from __future__ import annotations

import re
from typing import Any

from src.listings.listing_normalizer import parse_mileage, parse_price

_AUTO_DEV_SOURCE = "auto.dev"

ADAPTER_WARNINGS_KEY = "_adapter_warnings"

_LOCATION_PLACEHOLDERS = frozenset(
    {
        "usa",
        "dealer online",
        "00000",
    }
)
_YEAR_PATTERN = re.compile(r"^\s*((?:19|20)\d{2})\s*")


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _raw_value_repr(value: Any) -> str:
    return repr(value)


def _invalid_price_warning(value: Any) -> str:
    return f"Invalid price value: {_raw_value_repr(value)}"


def _invalid_mileage_warning(value: Any) -> str:
    return f"Invalid mileage value: {_raw_value_repr(value)}"


def _invalid_year_warning(value: Any) -> str:
    return f"Invalid year value: {_raw_value_repr(value)}"


def _invalid_location_warning(value: Any) -> str:
    return f"Invalid location value: {_raw_value_repr(value)}"


def _optional_price(value: Any) -> tuple[int | None, list[str]]:
    if value is None:
        return None, []
    if isinstance(value, bool):
        return None, [_invalid_price_warning(value)]

    parsed = parse_price(value)
    if parsed is not None:
        return parsed, []

    if isinstance(value, (int, float)):
        number = float(value)
        if number >= 0 and number.is_integer():
            return int(number), []

    if isinstance(value, str) and value.strip():
        return None, [_invalid_price_warning(value)]

    return None, []


def _optional_mileage(value: Any) -> tuple[int | None, list[str]]:
    if value is None:
        return None, []
    if isinstance(value, bool):
        return None, [_invalid_mileage_warning(value)]

    parsed = parse_mileage(value)
    if parsed is not None:
        return parsed, []

    if isinstance(value, (int, float)):
        number = float(value)
        if number >= 0 and number.is_integer():
            return int(number), []

    if isinstance(value, str) and value.strip():
        return None, [_invalid_mileage_warning(value)]

    return None, []


def _parse_year_token(token: str) -> int | None:
    match = _YEAR_PATTERN.match(token)
    if not match:
        return None
    year = int(match.group(1))
    if 1900 <= year <= 2100:
        return year
    return None


def _optional_year(value: Any) -> tuple[int | None, list[str]]:
    if value is None:
        return None, []
    if isinstance(value, bool):
        return None, [_invalid_year_warning(value)]

    if isinstance(value, int):
        if 1900 <= value <= 2100:
            return value, []
        return None, [_invalid_year_warning(value)]

    if isinstance(value, float) and value.is_integer():
        year = int(value)
        if 1900 <= year <= 2100:
            return year, []
        return None, [_invalid_year_warning(value)]

    text = str(value).strip()
    if not text:
        return None, []

    if "-" in text:
        first_token = text.split("-", 1)[0].strip()
        parsed = _parse_year_token(first_token)
        if parsed is not None:
            return parsed, []
        return None, [_invalid_year_warning(value)]

    parsed = _parse_year_token(text)
    if parsed is not None:
        return parsed, []

    return None, [_invalid_year_warning(value)]


def _optional_location(value: Any) -> tuple[str | None, list[str]]:
    if value is None:
        return None, []
    text = _optional_str(value)
    if not text:
        return None, []
    if text.casefold() in _LOCATION_PLACEHOLDERS:
        return None, [_invalid_location_warning(value)]
    return text, []


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    target[key] = value


def _compose_title(*, year: Any, make: Any, model: Any, trim: Any = None) -> str | None:
    parts: list[str] = []
    year_value, _ = _optional_year(year)
    if year_value is not None:
        parts.append(str(year_value))
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


def _normalize_drive_type(value: Any) -> str | None:
    text = _optional_str(value)
    return text.casefold() if text else None


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

    year, year_warnings = _optional_year(vehicle.get("year"))
    warnings.extend(year_warnings)
    if year is not None:
        raw["year"] = year

    _set_if_present(raw, "trim", vehicle.get("trim"))
    _set_if_present(raw, "drive_type", _normalize_drive_type(vehicle.get("drivetrain")))

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
        year=vehicle.get("year"),
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

    if warnings:
        raw[ADAPTER_WARNINGS_KEY] = warnings
    return raw
