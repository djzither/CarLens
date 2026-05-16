from __future__ import annotations

from typing import Any

MISSING_TRAIT_WEIGHT_THRESHOLD = 0.20


def _score_label(score: float) -> str:
    if score >= 0.75:
        return "Strong"
    if score >= 0.50:
        return "Moderate"
    return "Weak"


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
                        "message": (
                            f"No rating available for {trait_name.replace('_', ' ')}"
                        ),
                    }
                )
            continue

        score = float(trait["score"])
        contribution = round(weight * score, 4)
        if contribution <= 0:
            continue

        label = _score_label(score)
        positive.append(
            {
                "trait": trait_name,
                "weight": weight,
                "vehicle_score": score,
                "contribution": contribution,
                "message": (
                    f"{label} {trait_name.replace('_', ' ')} "
                    f"(score {score:.2f}, weight {weight:.2f})"
                ),
            }
        )

    positive.sort(key=lambda item: item["contribution"], reverse=True)
    return positive + missing
