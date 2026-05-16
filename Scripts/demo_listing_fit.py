#!/usr/bin/env python3
"""Command-line demo for CarLens listing fit scoring."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.listings.listing_fit import score_listing_fit
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

BUYER_PROFILE_ID = "student"

LISTING_SCENARIOS = {
    "good_corolla": {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
    },
    "over_budget_corolla": {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 15000,
        "clean_title": True,
    },
    "dirty_title_corolla": {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": False,
    },
    "bad_year_corolla": {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2009,
        "mileage": 85000,
        "price": 8000,
        "clean_title": True,
    },
    "wrong_model_bmw": {
        "make": "BMW",
        "model": "328i",
        "year": 2015,
        "mileage": 90000,
        "price": 11000,
        "clean_title": True,
    },
}


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


def main() -> int:
    buyer_data = load_buyer_profiles()
    buyer = _find_buyer(buyer_data["profiles"], BUYER_PROFILE_ID)

    result = recommend(BUYER_PROFILE_ID)
    if not result["recommendations"]:
        print("Error: no recommendations available", file=sys.stderr)
        return 1

    top_recommendation = result["recommendations"][0]
    print(f"Buyer profile: {BUYER_PROFILE_ID}")
    print(
        f"Recommendation: {top_recommendation['make']} {top_recommendation['model']}"
    )
    print()

    blocks: list[str] = []
    for scenario_name, listing in LISTING_SCENARIOS.items():
        fit = score_listing_fit(listing, top_recommendation, buyer)
        blocks.append(format_scenario_output(scenario_name, listing, fit))

    print("\n".join(blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
