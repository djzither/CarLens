from __future__ import annotations

from typing import Any

# Drive-type requirements that exclude unsuitable vehicles (e.g. snow use).
# fwd/rwd-style requirements are soft preferences, not hard filters.
_CAPABILITY_DRIVE_TYPES = frozenset({"awd", "4wd"})


def _budget_max(buyer: dict[str, Any]) -> int:
    return int(buyer["budget_type"]["max_amount"])


def _required_drive_type(buyer: dict[str, Any]) -> str | None:
    for requirement in buyer.get("hard_requirements", []):
        if not isinstance(requirement, str) or not requirement.startswith("drive_type:"):
            continue
        drive_type = requirement.split(":", 1)[1]
        if drive_type in _CAPABILITY_DRIVE_TYPES:
            return drive_type
    return None


def apply_hard_filters(vehicle: dict[str, Any], buyer: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (passes, exclusion_reasons). Empty reasons when the vehicle passes."""
    reasons: list[str] = []

    price_min = vehicle["typical_price_range"]["min"]
    budget_max = _budget_max(buyer)
    if price_min > budget_max:
        reasons.append(
            f"typical_price_range.min ({price_min}) exceeds budget max ({budget_max})"
        )

    required_drive = _required_drive_type(buyer)
    if required_drive is not None and vehicle.get("drive_type") != required_drive:
        reasons.append(
            f"drive_type '{vehicle.get('drive_type')}' does not match required '{required_drive}'"
        )

    excluded = buyer.get("excluded_body_types")
    if excluded:
        body_type = vehicle.get("body_type")
        if body_type in excluded:
            reasons.append(f"body_type '{body_type}' is in excluded_body_types")

    return (len(reasons) == 0, reasons)
