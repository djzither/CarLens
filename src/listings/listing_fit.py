from __future__ import annotations

from typing import Any

from src.listings.listing_normalizer import normalize_listing

MODEL_MATCH_POINTS = 40
YEAR_IN_RANGE_POINTS = 25
PRICE_UNDER_BUDGET_POINTS = 20
MILEAGE_OK_POINTS = 15

WRONG_MODEL_PENALTY = 45
OVER_BUDGET_PENALTY = 20
EXTREME_OVER_BUDGET_MULTIPLIER = 2
BAD_YEAR_PENALTY = 25
DIRTY_TITLE_PENALTY = 20
UNDISCLOSED_TITLE_PENALTY = 20
SEVERE_OVER_MILEAGE_MULTIPLIER = 1.5

DIRTY_TITLE_WARNING = (
    "Listing does not have a clean title — this can indicate salvage, flood "
    "damage, major accident history, or theft recovery."
)
MISSING_PRICE_WARNING = (
    "Listing price was not provided — cannot verify budget fit."
)
MISSING_MILEAGE_WARNING = (
    "Mileage not disclosed — odometer reading unavailable"
)
MISSING_TITLE_WARNING = (
    "Title status not disclosed — verify clean title before purchase"
)
MISSING_DRIVE_TYPE_WARNING = (
    "Drive type was not provided — cannot confirm all-wheel drive requirement."
)
NOT_AWD_WARNING = (
    "Listing is not all-wheel drive; your profile requires AWD or 4WD."
)
_AWD_DRIVE_TYPES = frozenset({"awd", "4wd"})

_MODEL_TRIMS: dict[tuple[str, str], frozenset[str]] = {
    ("toyota", "corolla"): frozenset({"l", "le", "se", "xle", "s"}),
}


def fit_label(fit_score: float) -> str:
    if fit_score >= 0.75:
        return "Strong fit"
    if fit_score >= 0.50:
        return "Moderate fit"
    return "Weak fit"


def _cap_fit_label(
    label: str,
    *,
    clean_title: bool | None,
    model_matches: bool,
    year_in_range: bool,
    has_year_range: bool,
    awd_requirement_met: bool = True,
    extreme_over_budget: bool = False,
    over_mileage_limit: bool = False,
    severe_over_mileage: bool = False,
) -> str:
    if not model_matches:
        return "Weak fit"
    if extreme_over_budget:
        return "Weak fit"
    if label == "Strong fit":
        if clean_title is not True:
            return "Moderate fit"
        if has_year_range and not year_in_range:
            return "Moderate fit"
        if not awd_requirement_met:
            return "Moderate fit"
        if over_mileage_limit:
            return "Moderate fit"
        if severe_over_mileage:
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


def _buyer_requires_awd(buyer: dict[str, Any]) -> bool:
    return "drive_type:awd" in buyer.get("hard_requirements", [])


def _resolve_clean_title(normalized: dict[str, Any]) -> bool | None:
    """Return True only when title is confirmed clean; False if dirty; else undisclosed."""
    if "clean_title" not in normalized:
        return None
    return normalized["clean_title"]


def _append_trim_warnings(
    normalized: dict[str, Any],
    recommendation: dict[str, Any],
    warnings: list[str],
) -> None:
    key = (_norm_name(recommendation["make"]), _norm_name(recommendation["model"]))
    known_trims = _MODEL_TRIMS.get(key)
    if not known_trims:
        return

    trim = normalized.get("trim")
    if not trim:
        warnings.append(
            f"Trim not specified for {recommendation['make']} {recommendation['model']}"
        )
        return

    if trim.strip().casefold() not in known_trims:
        warnings.append(
            f"Trim '{trim}' is not a recognized trim for this model"
        )


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

    year_in_range = _year_in_range(normalized["year"], selected_year_range)
    has_year_range = selected_year_range is not None
    if year_in_range:
        score += YEAR_IN_RANGE_POINTS
        if model_matches:
            reasons.append(
                f"Model year {normalized['year']} is within the recommended range"
            )
    elif has_year_range:
        warnings.append(
            f"Model year {normalized['year']} is outside the recommended "
            f"{selected_year_range['start_year']}\u2013{selected_year_range['end_year']} range"
        )
    if has_year_range:
        max_possible += YEAR_IN_RANGE_POINTS

    budget_max = _budget_max(buyer)
    extreme_over_budget = False
    if "price" in normalized:
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
            if normalized["price"] >= budget_max * EXTREME_OVER_BUDGET_MULTIPLIER:
                extreme_over_budget = True
        max_possible += PRICE_UNDER_BUDGET_POINTS
    else:
        warnings.append(MISSING_PRICE_WARNING)

    max_mileage = buyer.get("max_mileage")
    over_mileage_limit = False
    severe_over_mileage = False
    if max_mileage is not None:
        max_possible += MILEAGE_OK_POINTS
        if "mileage" in normalized:
            if normalized["mileage"] <= max_mileage:
                score += MILEAGE_OK_POINTS
                if model_matches:
                    reasons.append(
                        f"Mileage {normalized['mileage']:,} is within your "
                        f"{max_mileage:,} mile limit"
                    )
            else:
                over_mileage_limit = True
                warnings.append(
                    f"Mileage {normalized['mileage']:,} exceeds your "
                    f"{max_mileage:,} mile limit"
                )
                if (
                    normalized["mileage"]
                    > max_mileage * SEVERE_OVER_MILEAGE_MULTIPLIER
                ):
                    severe_over_mileage = True
        else:
            warnings.append(MISSING_MILEAGE_WARNING)

    _append_trim_warnings(normalized, recommendation, warnings)

    awd_requirement_met = True
    if _buyer_requires_awd(buyer) and model_matches:
        listing_drive = normalized.get("drive_type")
        if not listing_drive:
            warnings.append(MISSING_DRIVE_TYPE_WARNING)
            awd_requirement_met = False
        elif listing_drive not in _AWD_DRIVE_TYPES:
            warnings.append(NOT_AWD_WARNING)
            awd_requirement_met = False

    if normalized["year"] in _known_bad_years(selected_year_range):
        score -= BAD_YEAR_PENALTY
        warnings.append(f"{normalized['year']} is a known weak year for this model")

    clean_title = _resolve_clean_title(normalized)
    if clean_title is True:
        pass
    elif clean_title is False:
        score -= DIRTY_TITLE_PENALTY
        warnings.append(DIRTY_TITLE_WARNING)
    else:
        score -= UNDISCLOSED_TITLE_PENALTY
        warnings.append(MISSING_TITLE_WARNING)

    if max_possible <= 0:
        normalized_score = 0.0
    else:
        normalized_score = max(0.0, min(1.0, score / max_possible))

    label = _cap_fit_label(
        fit_label(normalized_score),
        clean_title=clean_title,
        model_matches=model_matches,
        year_in_range=year_in_range,
        has_year_range=has_year_range,
        awd_requirement_met=awd_requirement_met,
        extreme_over_budget=extreme_over_budget,
        over_mileage_limit=over_mileage_limit,
        severe_over_mileage=severe_over_mileage,
    )

    return {
        "fit_score": round(normalized_score, 3),
        "fit_label": label,
        "reasons": reasons,
        "warnings": warnings,
    }
