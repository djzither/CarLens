from __future__ import annotations

from typing import Any


def build_reasons(vehicle: dict[str, Any], buyer: dict[str, Any]) -> list[dict[str, Any]]:
    """Return trait contributions that positively affected the score, highest first."""
    trait_weights: dict[str, float] = buyer["trait_weights"]
    vehicle_traits = {trait["name"]: trait for trait in vehicle.get("traits", [])}

    contributions: list[dict[str, Any]] = []
    for trait_name, weight in trait_weights.items():
        trait = vehicle_traits.get(trait_name)
        if trait is None:
            continue
        score = float(trait["score"])
        contribution = round(weight * score, 4)
        if contribution <= 0:
            continue
        contributions.append(
            {
                "trait": trait_name,
                "weight": weight,
                "vehicle_score": score,
                "contribution": contribution,
                "message": (
                    f"Strong {trait_name.replace('_', ' ')} "
                    f"(score {score:.2f}, weight {weight:.2f})"
                ),
            }
        )

    contributions.sort(key=lambda item: item["contribution"], reverse=True)
    return contributions
