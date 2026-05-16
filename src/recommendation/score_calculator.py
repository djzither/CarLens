from __future__ import annotations

from typing import Any


def _trait_scores_by_name(vehicle: dict[str, Any]) -> dict[str, float]:
    return {trait["name"]: float(trait["score"]) for trait in vehicle.get("traits", [])}


def calculate_score(vehicle: dict[str, Any], buyer: dict[str, Any]) -> float:
    """Weighted sum of buyer trait_weights times matching vehicle trait scores."""
    trait_weights: dict[str, float] = buyer["trait_weights"]
    vehicle_traits = _trait_scores_by_name(vehicle)

    total = 0.0
    for trait_name, weight in trait_weights.items():
        if trait_name in vehicle_traits:
            total += weight * vehicle_traits[trait_name]
    return round(total, 4)
