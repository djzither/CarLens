#!/usr/bin/env python3
"""Command-line demo for the marketplace listing pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.listings.listing_ranker import rank_listings_for_recommendations
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


def load_sample_listings(
    path: Path = SAMPLE_LISTINGS_PATH,
) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

    buyer_profile_id = data["buyer_profile_id"]
    scenarios: list[tuple[str, dict[str, Any]]] = []
    for entry in data["listings"]:
        scenarios.append((entry["id"], entry["listing"]))
    return buyer_profile_id, scenarios


def _find_buyer(profiles: list[dict], buyer_profile_id: str) -> dict:
    for profile in profiles:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def _with_pipeline_duplicates(
    scenarios: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    """Add a duplicate marketplace post so pipeline counts are visible in the demo."""
    for listing_name, listing in scenarios:
        if listing_name != "good_corolla":
            continue
        duplicate_url = "https://example.com/demo/good-corolla-dup"
        sparse = {
            "title": "2016 Toyota Corolla LE 92k miles",
            "listing_url": duplicate_url,
            "source": "demo",
            "listing_id": "good-corolla-dup",
        }
        complete = {
            **listing,
            "listing_url": duplicate_url,
            "source": "demo",
            "listing_id": "good-corolla-dup",
            "raw_title": "2016 Toyota Corolla LE clean title 92k miles",
        }
        return [
            *scenarios,
            ("good_corolla_sparse_dup", sparse),
            ("good_corolla_complete_dup", complete),
        ]
    return scenarios


def _format_reason_lines(label: str, items: list[str]) -> list[str]:
    lines = [label]
    if items:
        for item in items:
            lines.append(f"  - {item}")
    else:
        lines.append("  (none)")
    return lines


def format_ranked_entry(entry: dict[str, Any]) -> str:
    listing = entry["listing"]
    fit = entry["fit"]
    lines = [
        f"{entry['listing_name']} — {fit['fit_label']} — {fit['fit_score']:.3f}",
    ]
    for key in ("source", "listing_id", "listing_url", "raw_title"):
        if key in listing:
            lines.append(f"  {key}: {listing[key]}")
    lines.extend(_format_reason_lines("Warnings", fit["warnings"]))
    lines.extend(_format_reason_lines("Positive reasons", fit["positive_reasons"]))
    lines.extend(_format_reason_lines("Negative reasons", fit["negative_reasons"]))
    return "\n".join(lines)


def main() -> int:
    try:
        buyer_profile_id, scenarios = load_sample_listings()
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Error loading sample listings: {exc}", file=sys.stderr)
        return 1

    scenarios = _with_pipeline_duplicates(scenarios)
    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)

    result = recommend(buyer_profile_id)
    recommendations = result["recommendations"]
    if not recommendations:
        print("Error: no recommendations available", file=sys.stderr)
        return 1

    ranked = rank_listings_for_recommendations(scenarios, recommendations, buyer)
    pipeline = ranked["pipeline"]

    print(f"Buyer profile: {buyer_profile_id}")
    print(f"Raw listings: {pipeline['raw_count']}")
    print(f"After normalization: {pipeline['normalized_count']}")
    print(f"After dedupe: {pipeline['deduped_count']}")
    print()

    for group in ranked["groups"]:
        print(
            f"Recommendation #{group['recommendation_rank']}: "
            f"{group['make']} {group['model']}"
        )
        if not group["listings"]:
            print(f"  {group.get('coverage_message', 'No matching listings found')}")
            continue
        for entry in group["listings"]:
            print(format_ranked_entry(entry))
            print()

    if ranked["unmatched_listings"]:
        print("Unmatched listings:")
        for entry in ranked["unmatched_listings"]:
            print(format_ranked_entry(entry))
            print()

    if ranked["invalid_listings"]:
        print("Invalid listings:")
        for entry in ranked["invalid_listings"]:
            print(f"  {entry['listing_name']}")
            for warning in entry["warnings"]:
                print(f"    - {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
