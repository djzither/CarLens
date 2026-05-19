#!/usr/bin/env python3
"""Inspect live Auto.dev inventory through the CarLens provider + ranking pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.listing_display import (
    build_watchouts,
    format_mileage,
    format_positive_reasons_for_display,
    format_price,
)
from src.listings.auto_dev_client import (
    AUTODEV_API_KEY_ENV,
    AutoDevClient,
    AutoDevSearchParams,
    iter_auto_dev_provider_rows,
)
from src.listings.listing_confidence import assess_listing_confidence
from src.listings.listing_quality_summary import (
    ListingQualityWarningsContext,
    build_listing_quality_summary,
)
from src.listings.listing_ranker import _listing_sort_key, rank_listings_for_recommendations
from src.listings.providers import SearchFilters
from src.listings.providers.auto_dev_provider import (
    AutoDevProvider,
    _expand_adapter_warnings,
    _filters_to_search_params,
)
from src.listings.providers.search_support import search_raw_listings
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

DEFAULT_BUYER_PROFILE_ID = "student"
DEFAULT_TOP_N = 10


def _find_buyer(profiles: list[dict[str, Any]], buyer_profile_id: str) -> dict[str, Any]:
    for profile in profiles:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def _buyer_search_filters(buyer: dict[str, Any]) -> SearchFilters:
    budget = buyer.get("budget_type") or {}
    max_price = budget.get("max_amount")
    max_mileage = buyer.get("max_mileage")
    return SearchFilters(
        max_price=int(max_price) if max_price is not None else None,
        max_mileage=int(max_mileage) if max_mileage is not None else None,
    )


def _search_params_with_pagination(
    filters: SearchFilters,
    *,
    page_size: int,
) -> AutoDevSearchParams:
    base = _filters_to_search_params(filters)
    return AutoDevSearchParams(
        make=base.make,
        model=base.model,
        price_max=base.price_max,
        mileage_max=base.mileage_max,
        year_min=base.year_min,
        year_max=base.year_max,
        page=1,
        page_size=page_size,
    )


def _provider_search_from_payload(
    provider: AutoDevProvider,
    *,
    payload: dict[str, Any],
    filters: SearchFilters,
) -> Any:
    """Run the same normalization + validation path as AutoDevProvider.search."""
    raw_listings, adapter_warnings = _expand_adapter_warnings(
        provider._adapt_provider_rows(payload)
    )
    total = len(iter_auto_dev_provider_rows(payload))
    result = search_raw_listings(
        provider_name=provider.name,
        raw_listings=raw_listings,
        filters=filters,
        validate_listing=provider.validate_listing,
        total_available=total,
    )
    return result, adapter_warnings


def _flatten_ranked_entries(ranked: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for group in ranked.get("groups") or []:
        recommendation = group.get("recommendation") or {}
        for entry in group.get("listings") or []:
            entries.append({**entry, "recommendation": recommendation})
    for entry in ranked.get("unmatched_listings") or []:
        entries.append({**entry, "recommendation": None})
    entries.sort(
        key=lambda item: _listing_sort_key(
            item["listing_name"],
            item["listing"],
            item["fit"],
        )
    )
    return entries


def _warnings_for_listing(listing_key: str, provider_warnings: list[str]) -> list[str]:
    prefix = f"{listing_key}:"
    return [
        message[len(prefix) :].strip()
        for message in provider_warnings
        if message.startswith(prefix)
    ]


def _skipped_count(provider_warnings: list[str]) -> int:
    return sum(1 for message in provider_warnings if "skipped" in message.casefold())


def _title_certainty_label(title_certainty: str) -> str:
    return {
        "clean": "Clean",
        "dirty": "Dirty / branded",
        "unknown": "Unknown",
    }.get(title_certainty, title_certainty)


def _fit_quality_label(fit: dict[str, Any], quality: dict[str, Any]) -> str:
    label = fit.get("fit_label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    mapped = quality.get("fit_quality")
    if mapped == "strong":
        return "Strong fit"
    if mapped == "moderate":
        return "Moderate fit"
    if mapped == "weak":
        return "Weak fit"
    return "—"


def _format_listing_result(
    *,
    rank: int,
    entry: dict[str, Any],
    raw_listing: dict[str, Any],
    provider_warnings: list[str],
) -> str:
    listing = entry["listing"]
    fit = entry["fit"]
    listing_id = str(listing.get("listing_id") or entry["listing_name"])
    recommendation = entry.get("recommendation")

    confidence = fit.get("confidence")
    if confidence is None:
        confidence = assess_listing_confidence(raw_listing, listing, fit=fit)

    record = {
        "id": entry["listing_name"],
        "listing": listing,
        "provider_name": listing.get("source", "auto.dev"),
        "provider_listing_id": listing_id,
        "provider_raw_fields": list(listing.keys()),
    }
    listing_notes = sorted(
        set(
            _warnings_for_listing(listing_id, provider_warnings)
            + _warnings_for_listing(entry["listing_name"], provider_warnings)
        )
    )
    quality = build_listing_quality_summary(
        record,
        fit=fit,
        warnings_context=ListingQualityWarningsContext(provider_warnings=listing_notes),
    )

    make = str(listing.get("make", "—"))
    model = str(listing.get("model", "—"))
    year = listing.get("year", "—")

    if recommendation:
        why_lines = format_positive_reasons_for_display(
            fit.get("positive_reasons") or fit.get("reasons") or [],
            make=make,
            model=model,
            listing=listing,
            fit=fit,
        )
    else:
        why_lines = [str(item) for item in (fit.get("reasons") or [])[:3]] or [
            "Does not match a top recommended model — shown for inventory inspection."
        ]

    watchouts = build_watchouts(fit, listing, raw_listing=raw_listing)
    watchout_lines = [f"  - {item}" for item in watchouts[:6]] if watchouts else ["  (none)"]
    if len(watchouts) > 6:
        watchout_lines.append(f"  - … +{len(watchouts) - 6} more")

    lines = [
        f"#{rank}",
        f"  {make} {model} {year}",
        f"  Price:    {format_price(listing.get('price'))}",
        f"  Mileage:  {format_mileage(listing.get('mileage'))}",
        f"  Fit:      {_fit_quality_label(fit, quality)} ({fit.get('fit_score', 0.0):.0%})",
        f"  Data:     {str(quality.get('data_quality_level', '—')).title()}",
        f"  Title:    {_title_certainty_label(str(quality.get('title_certainty', 'unknown')))}",
        f"  Trust:    {confidence.get('confidence_level', '—')}",
        f"  Provider: {record['provider_name']}",
        "  Why it fits:",
    ]
    lines.extend(f"    - {line}" for line in why_lines[:4])
    lines.append("  Watchouts:")
    lines.extend(watchout_lines)
    if listing_notes:
        lines.append("  Provider notes:")
        lines.extend(f"    - {note}" for note in listing_notes[:4])
    return "\n".join(lines)


def run_live_demo(
    *,
    buyer_profile_id: str,
    top_n: int,
    max_pages: int,
    page_size: int,
) -> int:
    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)
    filters = _buyer_search_filters(buyer)

    client = AutoDevClient()
    if not client.has_api_key:
        print(
            f"Error: set {AUTODEV_API_KEY_ENV} to query live Auto.dev inventory.",
            file=sys.stderr,
        )
        return 1

    params = _search_params_with_pagination(filters, page_size=page_size)

    print(f"Buyer profile: {buyer_profile_id}")
    print(
        "Auto.dev filters: "
        f"max_price={filters.max_price}, max_mileage={filters.max_mileage}, "
        f"max_pages={max_pages}, page_size={page_size}"
    )
    print()

    fetch = client.search_listings_paginated(params, max_pages=max_pages)
    total_raw = len(iter_auto_dev_provider_rows(fetch.payload))
    if fetch.errors and not fetch.payload:
        print("Auto.dev fetch failed:", file=sys.stderr)
        for message in fetch.errors:
            print(f"  - {message}", file=sys.stderr)
        return 1

    provider = AutoDevProvider(client=client, use_live_api=False)
    search_result, adapter_warnings = _provider_search_from_payload(
        provider,
        payload=fetch.payload,
        filters=filters,
    )
    provider_warnings = [*adapter_warnings, *search_result.provider_warnings]
    provider_errors = list(fetch.errors)

    recommendation_result = recommend(buyer_profile_id, buyer=buyer)
    recommendations = recommendation_result["recommendations"]
    if not recommendations:
        print("Error: no vehicle recommendations available for this profile.", file=sys.stderr)
        return 1

    scenarios = [(record["id"], record["listing"]) for record in search_result.listings]
    raw_lookup = {entry_id: listing for entry_id, listing in scenarios}

    ranked = rank_listings_for_recommendations(scenarios, recommendations, buyer)
    pipeline = ranked.get("pipeline") or {}
    duplicates = int(pipeline.get("raw_count", len(scenarios))) - int(
        pipeline.get("deduped_count", len(scenarios))
    )

    top_entries = _flatten_ranked_entries(ranked)[:top_n]
    print(f"Top {len(top_entries)} listings (live Auto.dev inventory)")
    print("=" * 60)
    for rank, entry in enumerate(top_entries, start=1):
        raw_listing = raw_lookup.get(entry["listing_name"], entry["listing"])
        print()
        print(_format_listing_result(
            rank=rank,
            entry=entry,
            raw_listing=raw_listing,
            provider_warnings=provider_warnings,
        ))

    print()
    print("=" * 60)
    print("Inventory summary")
    print("=" * 60)
    print(f"Total raw listings:   {total_raw}")
    print(f"Total valid listings: {len(search_result.listings)}")
    print(f"Skipped listings:     {_skipped_count(provider_warnings)}")
    print(f"Warnings count:       {len(provider_warnings)}")
    print(f"Duplicates removed:   {max(duplicates, 0)}")
    if ranked.get("invalid_listings"):
        print(f"Invalid (normalize):  {len(ranked['invalid_listings'])}")
    if provider_errors:
        print()
        print("Provider errors:")
        for message in provider_errors:
            print(f"  - {message}")
    invalid_count = len(ranked.get("invalid_listings") or [])
    if invalid_count:
        print(f"Normalize failures:   {invalid_count}")
    unmatched = len(ranked.get("unmatched_listings") or [])
    if unmatched:
        print(f"Unmatched models:     {unmatched}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull live Auto.dev listings and rank them for a buyer profile.",
    )
    parser.add_argument(
        "buyer_profile_id",
        nargs="?",
        default=DEFAULT_BUYER_PROFILE_ID,
        help=f"Buyer profile id (default: {DEFAULT_BUYER_PROFILE_ID})",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of listings to print (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Maximum Auto.dev pages to fetch (default: 2)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
        help="Auto.dev page size (default: 20)",
    )
    args = parser.parse_args(argv)

    try:
        return run_live_demo(
            buyer_profile_id=args.buyer_profile_id,
            top_n=max(args.top, 1),
            max_pages=max(args.max_pages, 1),
            page_size=max(args.page_size, 1),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
