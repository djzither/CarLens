from __future__ import annotations

from typing import Any

from src.listings.listing_fit import (
    _AWD_DRIVE_TYPES,
    _budget_max,
    _buyer_requires_awd,
    _known_bad_years_for_recommendation,
    _model_matches,
    _resolve_clean_title,
    _year_in_range,
)
from src.listings.listing_normalizer import normalize_listing

STRONG_MODEL_MATCH = "Strong model match"
UNDISCLOSED_TITLE_NEGATIVE = (
    "Title status not disclosed — verify before purchase"
)
AWD_NOT_MET_NEGATIVE = "Does not meet AWD requirement"
AWD_NOT_DISCLOSED_NEGATIVE = "Drive type not disclosed — AWD required"


def _wrong_model_reason(recommendation: dict[str, Any]) -> str:
    return (
        f"Not the recommended {recommendation['make']} {recommendation['model']}"
    )


def build_listing_reasons(
    listing: dict[str, Any],
    buyer: dict[str, Any],
    recommendation: dict[str, Any],
) -> dict[str, list[str]]:
    """Build ordered positive and negative reasons for a listing fit."""
    normalized = normalize_listing(listing)
    selected_year_range = recommendation.get("selected_year_range")
    budget_max = _budget_max(buyer)
    max_mileage = buyer.get("max_mileage")

    if not _model_matches(normalized, recommendation):
        return {
            "positive_reasons": [],
            "negative_reasons": [_wrong_model_reason(recommendation)],
        }

    year_in_range = _year_in_range(normalized["year"], selected_year_range)
    has_year_range = selected_year_range is not None
    known_bad_year = normalized["year"] in _known_bad_years_for_recommendation(
        recommendation
    )
    clean_title = _resolve_clean_title(normalized)

    negative_reasons: list[str] = []
    if clean_title is False:
        negative_reasons.append("Dirty title")
    elif clean_title is None:
        negative_reasons.append(UNDISCLOSED_TITLE_NEGATIVE)
    if known_bad_year:
        negative_reasons.append("Known problematic model year")
    if has_year_range and not year_in_range:
        negative_reasons.append("Year outside recommended range")
    if "price" in normalized and normalized["price"] > budget_max:
        over_amount = normalized["price"] - budget_max
        negative_reasons.append(f"Over budget by ${over_amount:,}")
    if (
        max_mileage is not None
        and "mileage" in normalized
        and normalized["mileage"] > max_mileage
    ):
        over_miles = normalized["mileage"] - max_mileage
        negative_reasons.append(
            f"Mileage exceeds preferred max by {over_miles:,}"
        )
    if _buyer_requires_awd(buyer):
        listing_drive = normalized.get("drive_type")
        if not listing_drive:
            negative_reasons.append(AWD_NOT_DISCLOSED_NEGATIVE)
        elif listing_drive not in _AWD_DRIVE_TYPES:
            negative_reasons.append(AWD_NOT_MET_NEGATIVE)

    positive_reasons: list[str] = []
    if len(negative_reasons) < 2:
        positive_reasons.append(STRONG_MODEL_MATCH)
    if year_in_range and not known_bad_year:
        positive_reasons.append("Within recommended year range")
    if "price" in normalized and normalized["price"] <= budget_max:
        positive_reasons.append("Under budget")
    if (
        max_mileage is not None
        and "mileage" in normalized
        and normalized["mileage"] <= max_mileage
    ):
        positive_reasons.append("Mileage within preferred range")
    if _buyer_requires_awd(buyer):
        listing_drive = normalized.get("drive_type")
        if listing_drive in _AWD_DRIVE_TYPES:
            positive_reasons.append("Matches requested AWD")

    return {
        "positive_reasons": positive_reasons,
        "negative_reasons": negative_reasons,
    }
