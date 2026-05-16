from __future__ import annotations

from typing import Any

from src.listings.listing_fit import score_listing_fit
from src.listings.listing_normalizer import normalize_listing

COVERAGE_MESSAGE_NO_LISTINGS = "No matching listings found"


def _model_key(make: str, model: str) -> tuple[str, str]:
    return make.strip().casefold(), model.strip().casefold()


def _listing_model_key(listing: dict[str, Any]) -> tuple[str, str]:
    normalized = normalize_listing(listing)
    return _model_key(normalized["make"], normalized["model"])


def _listing_display_name(listing: dict[str, Any]) -> tuple[str, str]:
    make = str(listing.get("make", "Unknown")).strip() or "Unknown"
    model = str(listing.get("model", "Unknown")).strip() or "Unknown"
    return make, model


def _unmatched_fit(listing: dict[str, Any]) -> dict[str, Any]:
    make, model = _listing_display_name(listing)
    return {
        "fit_score": 0.0,
        "fit_label": "Weak fit",
        "reasons": [],
        "warnings": [f"{make} {model} does not match any recommended model"],
    }


def _recommendation_lookup(
    recommendations: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for recommendation in recommendations:
        key = _model_key(recommendation["make"], recommendation["model"])
        lookup.setdefault(key, recommendation)
    return lookup


def _sort_scored_listings(
    entries: list[tuple[int, str, dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    entries.sort(key=lambda item: (-item[3]["fit_score"], item[0]))
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

    for index, (listing_name, listing) in enumerate(listings):
        try:
            key = _listing_model_key(listing)
        except ValueError as exc:
            invalid_listings.append(
                {
                    "listing_name": listing_name,
                    "listing": listing,
                    "warnings": [str(exc)],
                }
            )
            continue

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
