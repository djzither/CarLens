from __future__ import annotations

from typing import Any

from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.explainability import build_reasons
from src.recommendation.hard_filters import apply_hard_filters
from src.recommendation.score_calculator import calculate_score
from src.recommendation.year_range_selector import select_best_year_range
from src.vehicles.vehicle_profile_loader import load_vehicle_profiles


def _find_buyer(profiles: list[dict[str, Any]], buyer_profile_id: str) -> dict[str, Any]:
    for profile in profiles:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def recommend(buyer_profile_id: str) -> dict[str, Any]:
    buyer_data = load_buyer_profiles()
    vehicle_data = load_vehicle_profiles()

    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)
    vehicles = vehicle_data["vehicles"]

    recommendations: list[dict[str, Any]] = []
    filtered_out: list[dict[str, Any]] = []

    for vehicle in vehicles:
        passes, exclusion_reasons = apply_hard_filters(vehicle, buyer)
        entry = {
            "make": vehicle["make"],
            "model": vehicle["model"],
        }
        if not passes:
            filtered_out.append({**entry, "exclusion_reasons": exclusion_reasons})
            continue

        scores = calculate_score(vehicle, buyer)
        reasons = build_reasons(vehicle, buyer)
        recommendations.append(
            {
                **entry,
                "score": scores["score"],
                "max_possible_score": scores["max_possible_score"],
                "normalized_score": scores["normalized_score"],
                "selected_year_range": select_best_year_range(vehicle, buyer),
                "reasons": reasons,
            }
        )

    recommendations.sort(
        key=lambda item: (-item["normalized_score"], item["make"], item["model"])
    )

    return {
        "buyer_profile_id": buyer_profile_id,
        "recommendations": recommendations,
        "filtered_out": filtered_out,
        "summary": {
            "total_vehicles": len(vehicles),
            "recommended_count": len(recommendations),
            "filtered_count": len(filtered_out),
        },
    }
