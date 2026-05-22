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
    format_title_certainty_display,
)
from src.listings.auto_dev_client import AUTODEV_API_KEY_ENV, AutoDevClient
from src.listings.listing_confidence import assess_listing_confidence
from src.listings.listing_quality_summary import (
    ListingQualityWarningsContext,
    build_listing_quality_summary,
)
from src.listings.listing_ranker import _listing_sort_key
from src.listings.providers import AutoDevProvider, ListingSearchService
from src.listings.recommendation_inventory import (
    FALLBACK_MIN_LISTINGS,
    cap_top_model_count,
    format_diagnostics_report,
    format_post_retrieval_diagnostics,
    format_pre_retrieval_diagnostics,
    resolve_selected_recommendation,
    retrieve_inventory_for_buyer,
    retrieve_inventory_for_selected_model,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

DEFAULT_BUYER_PROFILE_ID = "student"
DEFAULT_TOP_N = 10
DEFAULT_LIVE_TOP_MODEL_COUNT = 4
DEFAULT_SHOW_RECOMMENDATIONS_COUNT = 5
AUTO_DEV_PROVIDER_NAME = "auto.dev"
MAX_REASON_LINES = 3


def _find_buyer(profiles: list[dict[str, Any]], buyer_profile_id: str) -> dict[str, Any]:
    for profile in profiles:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def _format_reason_line(reason: dict[str, Any]) -> str:
    return str(reason.get("message", reason))


def _format_year_range_lines(selected: dict[str, Any] | None) -> list[str]:
    if not selected:
        return []
    lines = [
        f"Year range: {selected['start_year']}\u2013{selected['end_year']}",
    ]
    known_bad_years = selected.get("known_bad_years")
    if known_bad_years:
        years = ", ".join(str(year) for year in sorted(known_bad_years))
        lines.append(f"Watch out for years: {years}")
    return lines


def format_recommendation_entry(rank: int, item: dict[str, Any]) -> str:
    """Format one ranked vehicle recommendation for CLI display."""
    lines = [
        f"{rank}. {item['make']} {item['model']}",
        f"   Make: {item['make']}",
        f"   Model: {item['model']}",
        f"   Recommendation score: {item['normalized_score']:.3f}",
    ]
    for year_line in _format_year_range_lines(item.get("selected_year_range")):
        lines.append(f"   {year_line}")
    reasons = item.get("reasons") or []
    if reasons:
        lines.append("   Reasons:")
        for reason in reasons[:MAX_REASON_LINES]:
            lines.append(f"     - {_format_reason_line(reason)}")
    return "\n".join(lines)


def run_show_recommendations(
    *,
    buyer_profile_id: str,
    top_models: int,
) -> int:
    """List top recommended models without querying live inventory."""
    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)
    recommendation_result = recommend(buyer_profile_id, buyer=buyer)
    recommendations = recommendation_result["recommendations"]
    if not recommendations:
        print("Error: no vehicle recommendations available for this profile.", file=sys.stderr)
        return 1

    effective_top, was_capped = cap_top_model_count(top_models)
    display_list = recommendations[:effective_top]

    print(f"Buyer profile: {buyer_profile_id}")
    print(f"Top {len(display_list)} recommended models (no inventory search)")
    if was_capped:
        print(f"(showing max {effective_top} models)")
    print("=" * 60)
    for rank, item in enumerate(display_list, start=1):
        print()
        print(format_recommendation_entry(rank, item))
    print()
    print("=" * 60)
    print("Next: query inventory for one model, e.g.")
    first = display_list[0]
    print(
        f'  python Scripts/demo_live_inventory.py {buyer_profile_id} '
        f'--selected-index 1 --top {DEFAULT_TOP_N}'
    )
    print(
        f'  python Scripts/demo_live_inventory.py {buyer_profile_id} '
        f'--selected-model "{first["make"]} {first["model"]}" --top {DEFAULT_TOP_N}'
    )
    return 0


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


def _title_certainty_label(title_certainty: str, *, source: str | None = None) -> str:
    return format_title_certainty_display(title_certainty, source=source)


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
        "provider_name": listing.get("source", AUTO_DEV_PROVIDER_NAME),
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
        f"  Title:    {_title_certainty_label(str(quality.get('title_certainty', 'unknown')), source=str(listing.get('source', '')))}",
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


def _print_inventory_results(
    *,
    retrieval: dict[str, Any],
    provider: AutoDevProvider,
    top_n: int,
    header: str,
) -> None:
    diagnostics = retrieval["diagnostics"]
    search_result = retrieval["search_result"]
    ranked = retrieval["ranked"]
    unmatched_model_count = len(ranked.get("unmatched_listings") or [])

    print(format_post_retrieval_diagnostics(
        diagnostics,
        unmatched_model_count=unmatched_model_count,
    ))
    print()

    provider_warnings = list(search_result.provider_warnings)
    provider_errors = list(search_result.errors)
    scenarios = [(record["id"], record["listing"]) for record in search_result.listings]
    raw_lookup = {entry_id: listing for entry_id, listing in scenarios}

    pipeline = ranked.get("pipeline") or {}
    duplicates = int(pipeline.get("raw_count", len(scenarios))) - int(
        pipeline.get("deduped_count", len(scenarios))
    )

    top_entries = _flatten_ranked_entries(ranked)[:top_n]
    print(header)
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
    print(format_diagnostics_report(diagnostics))
    print()
    print(f"Total raw listings:   {diagnostics.metrics.raw_retrieved}")
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
    if provider.last_fetch_errors:
        print()
        print("Auto.dev fetch notes:")
        for message in provider.last_fetch_errors:
            print(f"  - {message}")
    invalid_count = len(ranked.get("invalid_listings") or [])
    if invalid_count:
        print(f"Normalize failures:   {invalid_count}")
    print(f"Unmatched model count: {unmatched_model_count}")


def _require_api_key() -> AutoDevClient | None:
    client = AutoDevClient()
    if not client.has_api_key:
        print(
            f"Error: set {AUTODEV_API_KEY_ENV} to query live Auto.dev inventory.",
            file=sys.stderr,
        )
        return None
    return client


def run_selected_model_inventory(
    *,
    buyer_profile_id: str,
    top_n: int,
    selected_model: str | None,
    selected_index: int | None,
    max_pages: int,
    page_size: int,
    fallback_min_listings: int,
) -> int:
    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)
    recommendation_result = recommend(buyer_profile_id, buyer=buyer)
    recommendations = recommendation_result["recommendations"]
    if not recommendations:
        print("Error: no vehicle recommendations available for this profile.", file=sys.stderr)
        return 1

    selected = resolve_selected_recommendation(
        recommendations,
        selected_model=selected_model,
        selected_index=selected_index,
    )
    selected_label = f"{selected['make']} {selected['model']}"

    print(f"Buyer profile: {buyer_profile_id}")
    print(f"Selected model: {selected_label}")
    print("Retrieval: single recommended-model inventory search")
    print(
        f"(max_pages={max_pages}, page_size={page_size}, "
        f"fallback_min={fallback_min_listings})"
    )
    print()
    print(
        format_pre_retrieval_diagnostics(
            provider_name=AUTO_DEV_PROVIDER_NAME,
            buyer=buyer,
            recommendations=[selected],
            top_model_count=1,
        )
    )
    print()

    client = _require_api_key()
    if client is None:
        return 1
    provider = AutoDevProvider(
        client=client,
        use_live_api=True,
        max_pages=max_pages,
        page_size=page_size,
    )
    search_service = ListingSearchService([provider])

    retrieval = retrieve_inventory_for_selected_model(
        buyer_profile_id,
        selected["make"],
        selected["model"],
        search_service,
        buyer=buyer,
        recommendation=selected,
        fallback_min_listings=fallback_min_listings,
    )

    _print_inventory_results(
        retrieval=retrieval,
        provider=provider,
        top_n=top_n,
        header=f"Top listings for {selected_label} (live Auto.dev inventory)",
    )
    return 0


def run_live_demo(
    *,
    buyer_profile_id: str,
    top_n: int,
    top_model_count: int,
    max_pages: int,
    page_size: int,
    fallback_min_listings: int,
) -> int:
    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)

    recommendation_result = recommend(buyer_profile_id, buyer=buyer)
    recommendations = recommendation_result["recommendations"]
    if not recommendations:
        print("Error: no vehicle recommendations available for this profile.", file=sys.stderr)
        return 1

    print(f"Buyer profile: {buyer_profile_id}")
    print(
        "Retrieval: recommendation-driven per-model queries "
        f"(top_models={top_model_count}, max_pages={max_pages}, page_size={page_size})"
    )
    print()
    print(
        format_pre_retrieval_diagnostics(
            provider_name=AUTO_DEV_PROVIDER_NAME,
            buyer=buyer,
            recommendations=recommendations,
            top_model_count=top_model_count,
        )
    )
    print()

    client = _require_api_key()
    if client is None:
        return 1
    provider = AutoDevProvider(
        client=client,
        use_live_api=True,
        max_pages=max_pages,
        page_size=page_size,
    )
    search_service = ListingSearchService([provider])

    retrieval = retrieve_inventory_for_buyer(
        buyer_profile_id,
        search_service,
        buyer=buyer,
        top_model_count=top_model_count,
        fallback_min_listings=fallback_min_listings,
    )

    _print_inventory_results(
        retrieval=retrieval,
        provider=provider,
        top_n=top_n,
        header=f"Top {top_n} listings (live Auto.dev inventory)",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CarLens live inventory: browse recommendations or search one model.",
    )
    parser.add_argument(
        "buyer_profile_id",
        nargs="?",
        default=DEFAULT_BUYER_PROFILE_ID,
        help=f"Buyer profile id (default: {DEFAULT_BUYER_PROFILE_ID})",
    )
    parser.add_argument(
        "--show-recommendations",
        action="store_true",
        help="List top recommended models only (no live inventory API calls)",
    )
    parser.add_argument(
        "--selected-model",
        metavar="MAKE MODEL",
        help='Search inventory for one model, e.g. "Honda Civic"',
    )
    parser.add_argument(
        "--selected-index",
        type=int,
        metavar="N",
        help="Search inventory for recommendation rank N (1-based)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=DEFAULT_TOP_N,
        help=f"Number of listings to print (default: {DEFAULT_TOP_N})",
    )
    parser.add_argument(
        "--top-models",
        type=int,
        default=None,
        help=(
            "With --show-recommendations: how many models to list. "
            f"Otherwise: per-model queries to run (default: {DEFAULT_LIVE_TOP_MODEL_COUNT})"
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Maximum Auto.dev pages to fetch per model query (default: 2)",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=20,
        help="Auto.dev page size per query (default: 20)",
    )
    parser.add_argument(
        "--fallback-min",
        type=int,
        default=FALLBACK_MIN_LISTINGS,
        help=(
            "Minimum listings before expanded/budget fallback "
            f"(default: {FALLBACK_MIN_LISTINGS}; selected-model uses widened year only)"
        ),
    )
    args = parser.parse_args(argv)

    if args.show_recommendations and (
        args.selected_model is not None or args.selected_index is not None
    ):
        print(
            "Error: use either --show-recommendations or a selection flag, not both.",
            file=sys.stderr,
        )
        return 1

    if args.selected_model is not None and args.selected_index is not None:
        print(
            "Error: use either --selected-model or --selected-index, not both.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.show_recommendations:
            top_models = (
                args.top_models
                if args.top_models is not None
                else DEFAULT_SHOW_RECOMMENDATIONS_COUNT
            )
            return run_show_recommendations(
                buyer_profile_id=args.buyer_profile_id,
                top_models=max(top_models, 1),
            )

        if args.selected_model is not None or args.selected_index is not None:
            return run_selected_model_inventory(
                buyer_profile_id=args.buyer_profile_id,
                top_n=max(args.top, 1),
                selected_model=args.selected_model,
                selected_index=args.selected_index,
                max_pages=max(args.max_pages, 1),
                page_size=max(args.page_size, 1),
                fallback_min_listings=max(args.fallback_min, 0),
            )

        top_model_count = (
            args.top_models
            if args.top_models is not None
            else DEFAULT_LIVE_TOP_MODEL_COUNT
        )
        return run_live_demo(
            buyer_profile_id=args.buyer_profile_id,
            top_n=max(args.top, 1),
            top_model_count=max(top_model_count, 1),
            max_pages=max(args.max_pages, 1),
            page_size=max(args.page_size, 1),
            fallback_min_listings=max(args.fallback_min, 0),
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
