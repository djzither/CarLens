from __future__ import annotations

from typing import Any

from src.listings.listing_deduper import dedupe_listings
from src.listings.listing_fit import score_listing_fit
from src.listings.listing_normalizer import normalize_listing

COVERAGE_MESSAGE_NO_LISTINGS = "No matching listings found"

_FIT_LABEL_STRENGTH = {
    "Strong fit": 0,
    "Moderate fit": 1,
    "Weak fit": 2,
}

_MISSING_NUMERIC_TIE_BREAK = 2**31 - 1


def _model_key(make: str, model: str) -> tuple[str, str]:
    return make.strip().casefold(), model.strip().casefold()


def _prepare_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw or canonical listing once for grouping and scoring."""
    return normalize_listing(listing)


def _dedupe_prepared_entries(
    entries: list[tuple[int, str, dict[str, Any]]],
) -> list[tuple[int, str, dict[str, Any]]]:
    """Drop duplicate normalized listings while keeping the most complete record."""
    survivors = dedupe_listings([listing for _, _, listing in entries])
    survivor_ids = {id(listing) for listing in survivors}
    return [entry for entry in entries if id(entry[2]) in survivor_ids]


def _listing_model_key(listing: dict[str, Any]) -> tuple[str, str]:
    return _model_key(listing["make"], listing["model"])


def _unmatched_fit(listing: dict[str, Any]) -> dict[str, Any]:
    unmatched_warning = (
        f"{listing['make']} {listing['model']} does not match any recommended model"
    )
    return {
        "fit_score": 0.0,
        "fit_label": "Weak fit",
        "label_was_capped": False,
        "reasons": [],
        "warnings": [unmatched_warning],
        "positive_reasons": [],
        "negative_reasons": [unmatched_warning],
    }


def _recommendation_lookup(
    recommendations: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for recommendation in recommendations:
        key = _model_key(recommendation["make"], recommendation["model"])
        lookup.setdefault(key, recommendation)
    return lookup


def _tie_break_price(listing: dict[str, Any]) -> int:
    price = listing.get("price")
    if price is None:
        return _MISSING_NUMERIC_TIE_BREAK
    return int(price)


def _tie_break_mileage(listing: dict[str, Any]) -> int:
    mileage = listing.get("mileage")
    if mileage is None:
        return _MISSING_NUMERIC_TIE_BREAK
    return int(mileage)


def _listing_sort_key(
    listing_name: str,
    listing: dict[str, Any],
    fit: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        -fit["fit_score"],
        _FIT_LABEL_STRENGTH.get(fit["fit_label"], len(_FIT_LABEL_STRENGTH)),
        len(fit["warnings"]),
        _tie_break_price(listing),
        _tie_break_mileage(listing),
        listing_name.casefold(),
    )


def _sort_scored_listings(
    entries: list[tuple[int, str, dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    entries.sort(
        key=lambda item: _listing_sort_key(item[1], item[2], item[3]),
    )
    return [
        {
            "listing_name": listing_name,
            "listing": listing,
            "fit": fit,
        }
        for _, listing_name, listing, fit in entries
    ]


def rank_listings_by_recommendation(
    listings: list[tuple[str, dict[str, Any]]],
    recommendations: list[dict[str, Any]],
    buyer: dict[str, Any],
) -> dict[str, Any]:
    """Group listings by matching recommendation and rank fit within each group."""
    lookup = _recommendation_lookup(recommendations)
    buckets: dict[tuple[str, str], list[tuple[int, str, dict[str, Any]]]] = {}
    unmatched_entries: list[tuple[int, str, dict[str, Any]]] = []
    invalid_listings: list[dict[str, Any]] = []

    prepared_entries: list[tuple[int, str, dict[str, Any]]] = []
    for index, (listing_name, raw_listing) in enumerate(listings):
        try:
            listing = _prepare_listing(raw_listing)
        except ValueError as exc:
            invalid_listings.append(
                {
                    "listing_name": listing_name,
                    "listing": raw_listing,
                    "warnings": [str(exc)],
                }
            )
            continue
        prepared_entries.append((index, listing_name, listing))

    for index, listing_name, listing in _dedupe_prepared_entries(prepared_entries):
        key = _listing_model_key(listing)
        if key in lookup:
            buckets.setdefault(key, []).append((index, listing_name, listing))
        else:
            unmatched_entries.append((index, listing_name, listing))

    groups: list[dict[str, Any]] = []
    for recommendation_rank, recommendation in enumerate(recommendations, start=1):
        key = _model_key(recommendation["make"], recommendation["model"])
        bucket = buckets.get(key, [])

        scored: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
        for index, listing_name, listing in bucket:
            fit = score_listing_fit(listing, recommendation, buyer)
            scored.append((index, listing_name, listing, fit))

        group: dict[str, Any] = {
            "recommendation_rank": recommendation_rank,
            "make": recommendation["make"],
            "model": recommendation["model"],
            "recommendation": recommendation,
            "recommendation_score": recommendation["normalized_score"],
            "listings": _sort_scored_listings(scored),
        }
        if not group["listings"]:
            group["coverage_message"] = COVERAGE_MESSAGE_NO_LISTINGS
        groups.append(group)

    unmatched_listings = [
        {
            "listing_name": listing_name,
            "listing": listing,
            "fit": _unmatched_fit(listing),
        }
        for _, listing_name, listing in sorted(unmatched_entries, key=lambda item: item[0])
    ]

    return {
        "groups": groups,
        "unmatched_listings": unmatched_listings,
        "invalid_listings": invalid_listings,
    }
