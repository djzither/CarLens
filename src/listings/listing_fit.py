from __future__ import annotations

from typing import Any

from src.listings.listing_normalizer import normalize_listing

MODEL_MATCH_POINTS = 40
YEAR_IN_RANGE_POINTS = 25
PRICE_UNDER_BUDGET_POINTS = 20
MILEAGE_OK_POINTS = 15

WRONG_MODEL_PENALTY = 45
OVER_BUDGET_PENALTY = 20
BAD_YEAR_PENALTY = 25
DIRTY_TITLE_PENALTY = 20

DIRTY_TITLE_WARNING = (
    "Listing does not have a clean title — this can indicate salvage, flood "
    "damage, major accident history, or theft recovery."
)


def fit_label(fit_score: float) -> str:
    if fit_score >= 0.75:
        return "Strong fit"
    if fit_score >= 0.50:
        return "Moderate fit"
    return "Weak fit"


def _cap_fit_label(label: str, *, clean_title: bool | None, model_matches: bool) -> str:
    if not model_matches:
        return "Weak fit"
    if clean_title is False and label == "Strong fit":
        return "Moderate fit"
    return label


def _norm_name(value: str) -> str:
    return value.strip().casefold()


def _budget_max(buyer: dict[str, Any]) -> int:
    return int(buyer["budget_type"]["max_amount"])


def _model_matches(listing: dict[str, Any], recommendation: dict[str, Any]) -> bool:
    return _norm_name(listing["make"]) == _norm_name(
        recommendation["make"]
    ) and _norm_name(listing["model"]) == _norm_name(recommendation["model"])


def _year_in_range(year: int, selected_year_range: dict[str, Any] | None) -> bool:
    if not selected_year_range:
        return False
    return selected_year_range["start_year"] <= year <= selected_year_range["end_year"]


def _known_bad_years(selected_year_range: dict[str, Any] | None) -> set[int]:
    if not selected_year_range:
        return set()
    return set(selected_year_range.get("known_bad_years") or [])


def score_listing_fit(
    listing: dict[str, Any],
    recommendation: dict[str, Any],
    buyer: dict[str, Any],
) -> dict[str, Any]:
    """Score how well a listing matches a recommendation and buyer constraints."""
    normalized = normalize_listing(listing)
    selected_year_range = recommendation.get("selected_year_range")

    score = 0.0
    max_possible = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    model_matches = _model_matches(normalized, recommendation)

    if model_matches:
        score += MODEL_MATCH_POINTS
        reasons.append(
            f"Matches recommended {recommendation['make']} {recommendation['model']}"
        )
    else:
        warnings.append(
            f"Listing is {normalized['make']} {normalized['model']}, not the "
            f"recommended {recommendation['make']} {recommendation['model']}"
        )
        score -= WRONG_MODEL_PENALTY
    max_possible += MODEL_MATCH_POINTS

    if _year_in_range(normalized["year"], selected_year_range):
        score += YEAR_IN_RANGE_POINTS
        if model_matches:
            reasons.append(
                f"Model year {normalized['year']} is within the recommended range"
            )
    elif selected_year_range:
        warnings.append(
            f"Model year {normalized['year']} is outside the recommended "
            f"{selected_year_range['start_year']}\u2013{selected_year_range['end_year']} range"
        )
    if selected_year_range:
        max_possible += YEAR_IN_RANGE_POINTS

    budget_max = _budget_max(buyer)
    if normalized["price"] <= budget_max:
        score += PRICE_UNDER_BUDGET_POINTS
        if model_matches:
            reasons.append(
                f"Price ${normalized['price']:,} is within your ${budget_max:,} budget"
            )
    else:
        score -= OVER_BUDGET_PENALTY
        warnings.append(
            f"Price ${normalized['price']:,} exceeds your ${budget_max:,} budget"
        )
    max_possible += PRICE_UNDER_BUDGET_POINTS

    max_mileage = buyer.get("max_mileage")
    if max_mileage is not None and "mileage" in normalized:
        max_possible += MILEAGE_OK_POINTS
        if normalized["mileage"] <= max_mileage:
            score += MILEAGE_OK_POINTS
            if model_matches:
                reasons.append(
                    f"Mileage {normalized['mileage']:,} is within your "
                    f"{max_mileage:,} mile limit"
                )
        else:
            warnings.append(
                f"Mileage {normalized['mileage']:,} exceeds your {max_mileage:,} mile limit"
            )

    if normalized["year"] in _known_bad_years(selected_year_range):
        score -= BAD_YEAR_PENALTY
        warnings.append(f"{normalized['year']} is a known weak year for this model")

    clean_title = normalized.get("clean_title")
    if clean_title is False:
        score -= DIRTY_TITLE_PENALTY
        warnings.append(DIRTY_TITLE_WARNING)

    if max_possible <= 0:
        normalized_score = 0.0
    else:
        normalized_score = max(0.0, min(1.0, score / max_possible))

    label = _cap_fit_label(
        fit_label(normalized_score),
        clean_title=clean_title,
        model_matches=model_matches,
    )

    return {
        "fit_score": round(normalized_score, 3),
        "fit_label": label,
        "reasons": reasons,
        "warnings": warnings,
    }
