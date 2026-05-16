from __future__ import annotations

from typing import Any

BUY_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def _confidence_rank(year_range: dict[str, Any]) -> int:
    return BUY_CONFIDENCE_RANK.get(year_range.get("buy_confidence", ""), 0)


def select_best_year_range(
    vehicle: dict[str, Any], buyer: dict[str, Any]
) -> dict[str, Any] | None:
    """Pick the best year range for this buyer (confidence first, mileage when possible)."""
    year_ranges = vehicle.get("year_ranges")
    if not year_ranges:
        return None

    candidates = list(year_ranges)
    max_mileage = buyer.get("max_mileage")
    if max_mileage is not None:
        mileage_fit = [
            year_range
            for year_range in year_ranges
            if year_range["mileage_max"] <= max_mileage
        ]
        if mileage_fit:
            candidates = mileage_fit

    best = max(
        candidates,
        key=lambda year_range: (_confidence_rank(year_range), year_range["start_year"]),
    )

    selected: dict[str, Any] = {
        "start_year": best["start_year"],
        "end_year": best["end_year"],
        "buy_confidence": best["buy_confidence"],
        "mileage_min": best["mileage_min"],
        "mileage_max": best["mileage_max"],
    }
    known_bad_years = best.get("known_bad_years") or []
    if known_bad_years:
        selected["known_bad_years"] = list(known_bad_years)
    return selected
