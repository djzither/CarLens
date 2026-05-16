from __future__ import annotations

from typing import Any

from src.listings.listing_fit import score_listing_fit
from src.listings.listing_normalizer import normalize_listing


def _model_key(make: str, model: str) -> tuple[str, str]:
    return make.strip().casefold(), model.strip().casefold()


def _listing_model_key(listing: dict[str, Any]) -> tuple[str, str]:
    normalized = normalize_listing(listing)
    return _model_key(normalized["make"], normalized["model"])


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

    for index, (listing_name, listing) in enumerate(listings):
        key = _listing_model_key(listing)
        if key in lookup:
            buckets.setdefault(key, []).append((index, listing_name, listing))
        else:
            unmatched_entries.append((index, listing_name, listing))

    groups: list[dict[str, Any]] = []
    for recommendation_rank, recommendation in enumerate(recommendations, start=1):
        key = _model_key(recommendation["make"], recommendation["model"])
        bucket = buckets.get(key)
        if not bucket:
            continue

        scored: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
        for index, listing_name, listing in bucket:
            fit = score_listing_fit(listing, recommendation, buyer)
            scored.append((index, listing_name, listing, fit))

        groups.append(
            {
                "recommendation_rank": recommendation_rank,
                "make": recommendation["make"],
                "model": recommendation["model"],
                "recommendation_score": recommendation["normalized_score"],
                "listings": _sort_scored_listings(scored),
            }
        )

    unmatched_listings: list[dict[str, Any]] = []
    if unmatched_entries and recommendations:
        fallback = recommendations[0]
        scored_unmatched: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
        for index, listing_name, listing in unmatched_entries:
            fit = score_listing_fit(listing, fallback, buyer)
            scored_unmatched.append((index, listing_name, listing, fit))
        unmatched_listings = _sort_scored_listings(scored_unmatched)
    elif unmatched_entries:
        for index, listing_name, listing in unmatched_entries:
            unmatched_listings.append(
                {
                    "listing_name": listing_name,
                    "listing": listing,
                    "fit": {
                        "fit_score": 0.0,
                        "fit_label": "Weak fit",
                        "reasons": [],
                        "warnings": ["No matching recommendation"],
                    },
                }
            )

    return {
        "groups": groups,
        "unmatched_listings": unmatched_listings,
    }
