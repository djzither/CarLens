from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
BUY_CONFIDENCE = frozenset({"high", "medium", "low"})
DRIVE_TYPES = frozenset({"fwd", "rwd", "awd", "4wd"})

ROOT_REQUIRED = frozenset({"schema_version", "vehicles"})
VEHICLE_REQUIRED = frozenset(
    {
        "make",
        "model",
        "body_type",
        "drive_type",
        "seats",
        "typical_price_range",
        "traits",
        "year_ranges",
    }
)
TRAIT_REQUIRED = frozenset({"name", "score", "confidence"})
PRICE_RANGE_REQUIRED = frozenset({"min", "max"})
YEAR_RANGE_REQUIRED = frozenset(
    {
        "start_year",
        "end_year",
        "buy_confidence",
        "known_bad_years",
        "mileage_min",
        "mileage_max",
        "notes",
        "risk_flags",
    }
)


def _require_dict(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_int(value: Any, field: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _require_float(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _validate_confidence(value: Any, field: str) -> str:
    confidence = _require_str(value, field)
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"{field} must be one of {sorted(CONFIDENCE_LEVELS)}")
    return confidence


def validate_trait(trait: Any, context: str) -> None:
    if not isinstance(trait, dict):
        raise ValueError(f"{context} must be an object")

    missing = TRAIT_REQUIRED - trait.keys()
    if missing:
        raise ValueError(f"{context} missing fields: {sorted(missing)}")

    _require_str(trait["name"], f"{context}.name")
    score = _require_float(trait["score"], f"{context}.score")
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"{context}.score must be between 0.0 and 1.0")
    _validate_confidence(trait["confidence"], f"{context}.confidence")


def validate_price_range(price_range: Any, context: str) -> None:
    if not isinstance(price_range, dict):
        raise ValueError(f"{context} must be an object")

    missing = PRICE_RANGE_REQUIRED - price_range.keys()
    if missing:
        raise ValueError(f"{context} missing fields: {sorted(missing)}")

    price_min = _require_int(price_range["min"], f"{context}.min")
    price_max = _require_int(price_range["max"], f"{context}.max")
    if price_min > price_max:
        raise ValueError(f"{context}.min must be <= max")


def validate_year_range(year_range: Any, context: str) -> None:
    if not isinstance(year_range, dict):
        raise ValueError(f"{context} year range must be an object")

    missing = YEAR_RANGE_REQUIRED - year_range.keys()
    if missing:
        raise ValueError(f"{context} year range missing fields: {sorted(missing)}")

    start_year = _require_int(year_range["start_year"], f"{context}.start_year")
    end_year = _require_int(year_range["end_year"], f"{context}.end_year")
    if start_year > end_year:
        raise ValueError(f"{context} start_year must be <= end_year")

    buy_confidence = _require_str(year_range["buy_confidence"], f"{context}.buy_confidence")
    if buy_confidence not in BUY_CONFIDENCE:
        raise ValueError(f"{context}.buy_confidence must be one of {sorted(BUY_CONFIDENCE)}")

    known_bad_years = _require_list(year_range["known_bad_years"], f"{context}.known_bad_years")
    if not all(isinstance(year, int) for year in known_bad_years):
        raise ValueError(f"{context}.known_bad_years must contain integers")

    mileage_min = _require_int(year_range["mileage_min"], f"{context}.mileage_min")
    mileage_max = _require_int(year_range["mileage_max"], f"{context}.mileage_max")
    if mileage_min > mileage_max:
        raise ValueError(f"{context} mileage_min must be <= mileage_max")

    _require_str(year_range["notes"], f"{context}.notes")
    risk_flags = _require_list(year_range["risk_flags"], f"{context}.risk_flags")
    if not all(isinstance(flag, str) for flag in risk_flags):
        raise ValueError(f"{context}.risk_flags must contain strings")


def validate_vehicle_profiles(data: Any) -> dict[str, Any]:
    root = _require_dict(data, "vehicle profiles")

    missing_root = ROOT_REQUIRED - root.keys()
    if missing_root:
        raise ValueError(f"vehicle profiles missing fields: {sorted(missing_root)}")

    schema_version = _require_str(root["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    vehicles = _require_list(root.get("vehicles"), "vehicles")
    if not vehicles:
        raise ValueError("vehicles must not be empty")

    seen_models: set[tuple[str, str]] = set()
    for index, vehicle in enumerate(vehicles):
        context = f"vehicles[{index}]"
        if not isinstance(vehicle, dict):
            raise ValueError(f"{context} must be an object")

        missing = VEHICLE_REQUIRED - vehicle.keys()
        if missing:
            raise ValueError(f"{context} missing fields: {sorted(missing)}")

        make = _require_str(vehicle["make"], f"{context}.make")
        model = _require_str(vehicle["model"], f"{context}.model")
        key = (make.lower(), model.lower())
        if key in seen_models:
            raise ValueError(f"duplicate vehicle: {make} {model}")
        seen_models.add(key)

        _require_str(vehicle["body_type"], f"{context}.body_type")
        drive_type = _require_str(vehicle["drive_type"], f"{context}.drive_type")
        if drive_type not in DRIVE_TYPES:
            raise ValueError(f"{context}.drive_type must be one of {sorted(DRIVE_TYPES)}")

        seats = _require_int(vehicle["seats"], f"{context}.seats")
        if seats < 1:
            raise ValueError(f"{context}.seats must be >= 1")

        validate_price_range(vehicle["typical_price_range"], f"{context}.typical_price_range")

        traits = _require_list(vehicle["traits"], f"{context}.traits")
        if not traits:
            raise ValueError(f"{context}.traits must not be empty")
        for trait_index, trait in enumerate(traits):
            validate_trait(trait, f"{context}.traits[{trait_index}]")

        year_ranges = _require_list(vehicle["year_ranges"], f"{context}.year_ranges")
        if not year_ranges:
            raise ValueError(f"{context}.year_ranges must not be empty")

        for yr_index, year_range in enumerate(year_ranges):
            validate_year_range(year_range, f"{context}.year_ranges[{yr_index}]")

    return root
