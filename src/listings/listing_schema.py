from __future__ import annotations

from typing import Any

LISTING_REQUIRED = frozenset({"make", "model", "year"})
LISTING_OPTIONAL = frozenset(
    {
        "price",
        "mileage",
        "clean_title",
        "title_status",
        "location",
        "trim",
        "drive_type",
        "listing_id",
        "source",
        "listing_url",
        "raw_title",
        "image_url",
        "distance_miles",
    }
)
CANONICAL_LISTING_FIELDS = (
    "listing_id",
    "make",
    "model",
    "year",
    "price",
    "mileage",
    "trim",
    "clean_title",
    "drive_type",
    "source",
    "listing_url",
    "raw_title",
)


def _require_dict(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _optional_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field)


def _optional_bool(value: Any, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def validate_listing(listing: Any) -> dict[str, Any]:
    """Validate required listing fields; optional fields are checked when present."""
    data = _require_dict(listing, "listing")

    missing = LISTING_REQUIRED - data.keys()
    if missing:
        raise ValueError(f"listing missing fields: {sorted(missing)}")

    validated: dict[str, Any] = {
        "make": _require_str(data["make"], "listing.make"),
        "model": _require_str(data["model"], "listing.model"),
        "year": _require_int(data["year"], "listing.year"),
    }

    if "price" in data:
        validated["price"] = _optional_int(data["price"], "listing.price")
    if "mileage" in data:
        validated["mileage"] = _optional_int(data["mileage"], "listing.mileage")
    if "clean_title" in data:
        validated["clean_title"] = _optional_bool(data["clean_title"], "listing.clean_title")
    if "title_status" in data:
        validated["title_status"] = _require_str(data["title_status"], "listing.title_status")
    if "location" in data:
        validated["location"] = _require_str(data["location"], "listing.location")
    if "trim" in data:
        validated["trim"] = _require_str(data["trim"], "listing.trim")
    if "drive_type" in data:
        validated["drive_type"] = _require_str(data["drive_type"], "listing.drive_type")
    if "listing_id" in data:
        validated["listing_id"] = _require_str(data["listing_id"], "listing.listing_id")
    if "source" in data:
        validated["source"] = _require_str(data["source"], "listing.source")
    if "listing_url" in data:
        validated["listing_url"] = _require_str(data["listing_url"], "listing.listing_url")
    if "raw_title" in data:
        validated["raw_title"] = _require_str(data["raw_title"], "listing.raw_title")
    if "image_url" in data:
        validated["image_url"] = _require_str(data["image_url"], "listing.image_url")
    if "distance_miles" in data:
        validated["distance_miles"] = _optional_int(
            data["distance_miles"], "listing.distance_miles"
        )

    return validated
