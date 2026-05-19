#!/usr/bin/env python3
"""Command-line demo for CarLens listing fit scoring."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.listings.listing_ranker import rank_listings_by_recommendation
from src.listings.providers import MockListingProvider
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


def load_sample_listings(
    path: Path = SAMPLE_LISTINGS_PATH,
) -> tuple[str, list[tuple[str, dict[str, Any]]], dict[str, str]]:
    provider = MockListingProvider(path)
    entries = provider.search_listings()
    buyer_profile_id = provider.buyer_profile_id
    scenarios: list[tuple[str, dict[str, Any]]] = []
    display_names: dict[str, str] = {}
    for entry in entries:
        scenarios.append((entry["id"], entry["listing"]))
        name = entry.get("display_name")
        if name and str(name).strip():
            display_names[entry["id"]] = str(name).strip()
    return buyer_profile_id, scenarios, display_names


def scenario_display_label(
    scenario_id: str,
    listing: dict[str, Any],
    display_names: dict[str, str],
) -> str:
    if scenario_id in display_names:
        return display_names[scenario_id]
    title = listing.get("raw_title") or listing.get("title")
    if title and str(title).strip():
        return str(title).strip()
    return (
        f"{listing.get('year', '')} {listing.get('make', '')} "
        f"{listing.get('model', '')}".strip()
    )


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


def format_grouped_summary(
    ranked: dict[str, Any],
    *,
    display_names: dict[str, str] | None = None,
) -> str:
    labels = display_names or {}
    lines: list[str] = []

    for group in ranked["groups"]:
        lines.append(
            f"Recommendation #{group['recommendation_rank']}: "
            f"{group['make']} {group['model']}"
        )
        if not group["listings"]:
            lines.append(f"  {group.get('coverage_message', 'No matching listings found')}")
        else:
            for rank, entry in enumerate(group["listings"], start=1):
                fit = entry["fit"]
                label = scenario_display_label(
                    entry["listing_name"],
                    entry["listing"],
                    labels,
                )
                lines.append(
                    f"  {rank}. {label} — {fit['fit_label']} — "
                    f"{fit['fit_score']:.3f}"
                )
        lines.append("")

    if ranked["unmatched_listings"]:
        lines.append("Unmatched listings:")
        for entry in ranked["unmatched_listings"]:
            fit = entry["fit"]
            label = scenario_display_label(
                entry["listing_name"],
                entry["listing"],
                labels,
            )
            lines.append(
                f"  {label} — {fit['fit_label']} — {fit['fit_score']:.3f}"
            )
        lines.append("")

    if ranked.get("invalid_listings"):
        lines.append("Invalid listings:")
        for entry in ranked["invalid_listings"]:
            lines.append(f"  {entry['listing_name']}")
            for warning in entry["warnings"]:
                lines.append(f"    - {warning}")
        lines.append("")

    return "\n".join(lines).rstrip()


def format_grouped_details(
    ranked: dict[str, Any],
    *,
    display_names: dict[str, str] | None = None,
) -> str:
    labels = display_names or {}
    blocks: list[str] = []

    for group in ranked["groups"]:
        blocks.append(
            f"--- {group['make']} {group['model']} "
            f"(recommendation #{group['recommendation_rank']}) ---"
        )
        if not group["listings"]:
            blocks.append(group.get("coverage_message", "No matching listings found"))
        else:
            for entry in group["listings"]:
                label = scenario_display_label(
                    entry["listing_name"],
                    entry["listing"],
                    labels,
                )
                blocks.append(
                    format_scenario_output(label, entry["listing"], entry["fit"])
                )

    if ranked["unmatched_listings"]:
        blocks.append("--- Unmatched listings ---")
        for entry in ranked["unmatched_listings"]:
            label = scenario_display_label(
                entry["listing_name"],
                entry["listing"],
                labels,
            )
            blocks.append(
                format_scenario_output(label, entry["listing"], entry["fit"])
            )

    if ranked.get("invalid_listings"):
        blocks.append("--- Invalid listings ---")
        for entry in ranked["invalid_listings"]:
            blocks.append(f"=== {entry['listing_name']} ===")
            blocks.append(format_listing_section(entry["listing"]))
            blocks.append("")
            blocks.append("Warnings")
            for warning in entry["warnings"]:
                blocks.append(f"  - {warning}")

    return "\n".join(blocks)


def main() -> int:
    try:
        buyer_profile_id, scenarios, display_names = load_sample_listings()
    except (OSError, ValueError, KeyError) as exc:
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
    print(format_grouped_summary(ranked, display_names=display_names))
    print()
    print(format_grouped_details(ranked, display_names=display_names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
