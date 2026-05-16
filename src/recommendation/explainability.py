from __future__ import annotations

from typing import Any

MISSING_TRAIT_WEIGHT_THRESHOLD = 0.20

TRAIT_DISPLAY_NAMES: dict[str, str] = {
    "reliable": "Reliability",
    "fuel_efficient": "Fuel Efficiency",
    "low_cost": "Low Ownership Cost",
    "common_parts": "Common Parts Availability",
    "cargo_space": "Cargo Space",
    "winter_capable": "Winter Capability",
    "awd": "All-Wheel Drive",
}

MISSING_TRAIT_MESSAGES: dict[str, str] = {
    "reliable": "Limited reliability data",
    "fuel_efficient": "Limited fuel efficiency data",
    "low_cost": "Limited ownership cost data",
    "common_parts": "Limited parts availability data",
    "cargo_space": "Limited cargo space data",
    "winter_capable": "Limited winter capability data",
    "awd": "Limited all-wheel drive data",
}


def trait_display_name(trait_name: str) -> str:
    return TRAIT_DISPLAY_NAMES.get(
        trait_name, trait_name.replace("_", " ").title()
    )


def _positive_message(trait_name: str, score: float) -> str:
    name = trait_display_name(trait_name)
    if score >= 0.85:
        return f"Excellent {name}"
    if score >= 0.75:
        return f"Strong {name}"
    if score >= 0.50:
        return f"Moderate {name}"
    return f"Limited {name}"


def _missing_message(trait_name: str) -> str:
    return MISSING_TRAIT_MESSAGES.get(
        trait_name, f"Limited {trait_display_name(trait_name).lower()} data"
    )


def build_reasons(vehicle: dict[str, Any], buyer: dict[str, Any]) -> list[dict[str, Any]]:
    """Positive trait contributions first (by impact), then missing high-weight traits."""
    trait_weights: dict[str, float] = buyer["trait_weights"]
    vehicle_traits = {trait["name"]: trait for trait in vehicle.get("traits", [])}

    positive: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for trait_name, weight in trait_weights.items():
        trait = vehicle_traits.get(trait_name)
        if trait is None:
            if weight >= MISSING_TRAIT_WEIGHT_THRESHOLD:
                missing.append(
                    {
                        "type": "missing_trait",
                        "trait": trait_name,
                        "weight": weight,
                        "message": _missing_message(trait_name),
                    }
                )
            continue

        score = float(trait["score"])
        contribution = round(weight * score, 4)
        if contribution <= 0:
            continue

        positive.append(
            {
                "trait": trait_name,
                "weight": weight,
                "vehicle_score": score,
                "contribution": contribution,
                "message": _positive_message(trait_name, score),
            }
        )

    positive.sort(key=lambda item: item["contribution"], reverse=True)
    return positive + missing
