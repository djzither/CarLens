from __future__ import annotations

from typing import Any


def _trait_scores_by_name(vehicle: dict[str, Any]) -> dict[str, float]:
    return {trait["name"]: float(trait["score"]) for trait in vehicle.get("traits", [])}


def calculate_score(vehicle: dict[str, Any], buyer: dict[str, Any]) -> dict[str, float]:
    """Weighted trait match with raw and normalized scores."""
    trait_weights: dict[str, float] = buyer["trait_weights"]
    vehicle_traits = _trait_scores_by_name(vehicle)

    score = 0.0
    matched_weight = 0.0
    missing_weight = 0.0
    for trait_name, weight in trait_weights.items():
        if trait_name in vehicle_traits:
            score += weight * vehicle_traits[trait_name]
            matched_weight += weight
        else:
            missing_weight += weight

    max_possible_score = sum(trait_weights.values())
    if max_possible_score == 0:
        normalized_score = 0.0
    else:
        normalized_score = round(score / max_possible_score, 3)

    return {
        "score": round(score, 4),
        "max_possible_score": round(max_possible_score, 4),
        "normalized_score": normalized_score,
        "matched_weight": round(matched_weight, 4),
        "missing_weight": round(missing_weight, 4),
    }
