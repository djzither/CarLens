#!/usr/bin/env python3
"""Command-line demo for CarLens listing fit scoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.listings.listing_ranker import rank_listings_by_recommendation
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


def load_sample_listings(path: Path = SAMPLE_LISTINGS_PATH) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
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


def format_listing_section(listing: dict) -> str:
    lines = ["LISTING", ""]
    for key in ("make", "model", "year", "mileage", "price", "clean_title", "location"):
        if key in listing:
            lines.append(f"  {key}: {listing[key]}")
    return "\n".join(lines)


def format_fit_result(fit: dict) -> str:
    lines = [
        "",
        "FIT RESULT",
        "",
        f"Score: {fit['fit_score']:.3f}",
        f"Label: {fit['fit_label']}",
        "",
        "Reasons",
    ]
    if fit["reasons"]:
        for reason in fit["reasons"]:
            lines.append(f"  - {reason}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("Warnings")
    if fit["warnings"]:
        for warning in fit["warnings"]:
            lines.append(f"  - {warning}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def format_scenario_output(scenario_name: str, listing: dict, fit: dict) -> str:
    lines = [
        f"=== {scenario_name} ===",
        format_listing_section(listing),
        format_fit_result(fit),
    ]
    return "\n".join(lines)


def format_grouped_summary(ranked: dict[str, Any]) -> str:
    lines: list[str] = []

    for group in ranked["groups"]:
        lines.append(
            f"Recommendation #{group['recommendation_rank']}: "
            f"{group['make']} {group['model']}"
        )
        for rank, entry in enumerate(group["listings"], start=1):
            fit = entry["fit"]
            lines.append(
                f"  {rank}. {entry['listing_name']} — {fit['fit_label']} — "
                f"{fit['fit_score']:.3f}"
            )
        lines.append("")

    if ranked["unmatched_listings"]:
        lines.append("Unmatched listings:")
        for entry in ranked["unmatched_listings"]:
            fit = entry["fit"]
            lines.append(
                f"  {entry['listing_name']} — {fit['fit_label']} — {fit['fit_score']:.3f}"
            )
        lines.append("")

    return "\n".join(lines).rstrip()


def format_grouped_details(ranked: dict[str, Any]) -> str:
    blocks: list[str] = []

    for group in ranked["groups"]:
        blocks.append(
            f"--- {group['make']} {group['model']} "
            f"(recommendation #{group['recommendation_rank']}) ---"
        )
        for entry in group["listings"]:
            blocks.append(
                format_scenario_output(
                    entry["listing_name"], entry["listing"], entry["fit"]
                )
            )

    if ranked["unmatched_listings"]:
        blocks.append("--- Unmatched listings ---")
        for entry in ranked["unmatched_listings"]:
            blocks.append(
                format_scenario_output(
                    entry["listing_name"], entry["listing"], entry["fit"]
                )
            )

    return "\n".join(blocks)


def main() -> int:
    try:
        buyer_profile_id, scenarios = load_sample_listings()
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"Error loading sample listings: {exc}", file=sys.stderr)
        return 1

    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)

    result = recommend(buyer_profile_id)
    recommendations = result["recommendations"]
    if not recommendations:
        print("Error: no recommendations available", file=sys.stderr)
        return 1

    print(f"Buyer profile: {buyer_profile_id}")
    print(f"Recommendations loaded: {len(recommendations)}")
    print()

    ranked = rank_listings_by_recommendation(scenarios, recommendations, buyer)
    print(format_grouped_summary(ranked))
    print()
    print(format_grouped_details(ranked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
