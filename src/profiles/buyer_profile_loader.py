from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

SCHEMA_VERSION = "1.0"
BUDGET_TYPES = frozenset({"max_purchase"})

ROOT_REQUIRED = frozenset({"schema_version", "profiles"})
PROFILE_REQUIRED = frozenset(
    {
        "id",
        "label",
        "budget_type",
        "preferred_body_types",
        "max_mileage",
        "primary_use",
        "trait_weights",
        "hard_requirements",
    }
)
BUDGET_TYPE_REQUIRED = frozenset({"type", "max_amount"})


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


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


def validate_budget_type(budget_type: Any, context: str) -> None:
    if not isinstance(budget_type, dict):
        raise ValueError(f"{context} must be an object")

    missing = BUDGET_TYPE_REQUIRED - budget_type.keys()
    if missing:
        raise ValueError(f"{context} missing fields: {sorted(missing)}")

    budget_kind = _require_str(budget_type["type"], f"{context}.type")
    if budget_kind not in BUDGET_TYPES:
        raise ValueError(f"{context}.type must be one of {sorted(BUDGET_TYPES)}")

    max_amount = _require_int(budget_type["max_amount"], f"{context}.max_amount")
    if max_amount < 0:
        raise ValueError(f"{context}.max_amount must be >= 0")


def validate_trait_weights(trait_weights: Any, context: str) -> None:
    if not isinstance(trait_weights, dict):
        raise ValueError(f"{context} must be an object")
    if not trait_weights:
        raise ValueError(f"{context} must not be empty")

    for trait_name, weight in trait_weights.items():
        if not isinstance(trait_name, str) or not trait_name.strip():
            raise ValueError(f"{context} keys must be non-empty strings")
        value = _require_float(weight, f"{context}.{trait_name}")
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{context}.{trait_name} must be between 0.0 and 1.0")


def validate_buyer_profiles(data: Any) -> dict[str, Any]:
    root = _require_dict(data, "buyer profiles")

    missing_root = ROOT_REQUIRED - root.keys()
    if missing_root:
        raise ValueError(f"buyer profiles missing fields: {sorted(missing_root)}")

    schema_version = _require_str(root["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    profiles = _require_list(root.get("profiles"), "profiles")
    if not profiles:
        raise ValueError("profiles must not be empty")

    seen_ids: set[str] = set()
    for index, profile in enumerate(profiles):
        context = f"profiles[{index}]"
        if not isinstance(profile, dict):
            raise ValueError(f"{context} must be an object")

        missing = PROFILE_REQUIRED - profile.keys()
        if missing:
            raise ValueError(f"{context} missing fields: {sorted(missing)}")

        profile_id = _require_str(profile["id"], f"{context}.id")
        if profile_id in seen_ids:
            raise ValueError(f"duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)

        _require_str(profile["label"], f"{context}.label")
        validate_budget_type(profile["budget_type"], f"{context}.budget_type")

        preferred_body_types = _require_list(profile["preferred_body_types"], f"{context}.preferred_body_types")
        if not preferred_body_types or not all(isinstance(item, str) for item in preferred_body_types):
            raise ValueError(f"{context}.preferred_body_types must be a non-empty list of strings")

        max_mileage = _require_int(profile["max_mileage"], f"{context}.max_mileage")
        if max_mileage < 0:
            raise ValueError(f"{context}.max_mileage must be >= 0")

        _require_str(profile["primary_use"], f"{context}.primary_use")
        validate_trait_weights(profile["trait_weights"], f"{context}.trait_weights")

        hard_requirements = _require_list(profile["hard_requirements"], f"{context}.hard_requirements")
        if not all(isinstance(item, str) for item in hard_requirements):
            raise ValueError(f"{context}.hard_requirements must contain strings")

    return root


def load_buyer_profiles() -> dict[str, Any]:
    data = _load_json(DATA_DIR / "buyer_profiles.json")
    return validate_buyer_profiles(data)
