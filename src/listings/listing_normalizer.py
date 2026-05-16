from __future__ import annotations

from typing import Any

from src.listings.listing_schema import validate_listing


def _coerce_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"{field} must be an integer")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise ValueError("listing.clean_title must be a boolean")


def normalize_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Coerce listing fields into a consistent shape for scoring."""
    if not isinstance(listing, dict):
        raise ValueError("listing must be a JSON object")

    normalized: dict[str, Any] = {
        "make": str(listing.get("make", "")).strip(),
        "model": str(listing.get("model", "")).strip(),
    }
    if not normalized["make"] or not normalized["model"]:
        raise ValueError("listing.make and listing.model are required")

    if "year" not in listing:
        raise ValueError("listing missing fields: ['year']")
    normalized["year"] = _coerce_int(listing["year"], "listing.year")

    if "price" in listing and listing["price"] is not None:
        normalized["price"] = _coerce_int(listing["price"], "listing.price")
    if "mileage" in listing and listing["mileage"] is not None:
        normalized["mileage"] = _coerce_int(listing["mileage"], "listing.mileage")
    if "clean_title" in listing and listing["clean_title"] is not None:
        normalized["clean_title"] = _coerce_bool(listing["clean_title"])
    if "location" in listing and listing["location"] is not None:
        location = str(listing["location"]).strip()
        if location:
            normalized["location"] = location
    if "trim" in listing and listing["trim"] is not None:
        trim = str(listing["trim"]).strip()
        if trim:
            normalized["trim"] = trim
    if "drive_type" in listing and listing["drive_type"] is not None:
        drive_type = str(listing["drive_type"]).strip()
        if drive_type:
            normalized["drive_type"] = drive_type.casefold()

    return validate_listing(normalized)
