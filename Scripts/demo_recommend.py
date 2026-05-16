#!/usr/bin/env python3
"""Command-line demo for CarLens model recommendations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.recommendation.recommendation_engine import recommend

LIMITED_DATA_MESSAGE = "Limited data available for this vehicle profile"
MISSING_WEIGHT_NOTICE_THRESHOLD = 0.30


def match_label(normalized_score: float) -> str:
    if normalized_score >= 0.75:
        return "Strong match"
    if normalized_score >= 0.50:
        return "Moderate match"
    return "Weak match"


def format_reason(reason: dict) -> str:
    return str(reason.get("message", reason))


def format_year_range_lines(selected: dict | None) -> list[str]:
    if not selected:
        return []
    lines = [
        f"Recommended years: {selected['start_year']}\u2013{selected['end_year']}"
    ]
    known_bad_years = selected.get("known_bad_years")
    if known_bad_years:
        years = ", ".join(str(year) for year in sorted(known_bad_years))
        lines.append(f"Watch out for: {years}")
    return lines


def format_human_output(result: dict, *, debug: bool = False) -> str:
    lines = [f"Buyer profile: {result['buyer_profile_id']}", "", "Ranked recommendations:"]

    for rank, item in enumerate(result["recommendations"], start=1):
        lines.append("")
        lines.append(f"  {rank}. {item['make']} {item['model']}")
        label = match_label(item["normalized_score"])
        lines.append(f"     {label} ({item['normalized_score']:.3f})")
        if debug:
            lines.append(
                f"     score={item['score']} / max={item['max_possible_score']}"
            )
        if item.get("missing_weight", 0) > MISSING_WEIGHT_NOTICE_THRESHOLD:
            lines.append(f"     {LIMITED_DATA_MESSAGE}")
        for year_line in format_year_range_lines(item.get("selected_year_range")):
            lines.append(f"     {year_line}")
        for reason in item.get("reasons", [])[:3]:
            lines.append(f"     - {format_reason(reason)}")

    filtered_out = result.get("filtered_out", [])
    if filtered_out:
        lines.extend(["", "Filtered out:"])
        for item in filtered_out:
            lines.append(f"  - {item['make']} {item['model']}")
            for reason in item.get("exclusion_reasons", []):
                lines.append(f"      {reason}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CarLens recommendation demo")
    parser.add_argument(
        "buyer_profile_id",
        help="Buyer profile id (e.g. student, outdoor_snow)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw recommend() JSON output",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include raw score fields in human-readable output",
    )
    args = parser.parse_args(argv)

    try:
        result = recommend(args.buyer_profile_id)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_human_output(result, debug=args.debug))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
