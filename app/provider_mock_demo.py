"""Load mocked provider API payloads and run them through the listing adapter pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.listings.auto_dev_client import parse_auto_dev_listings
from src.listings.listing_deduper import dedupe_listings
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_ranker import rank_listings_for_recommendations
from src.listings.marketcheck_client import parse_marketcheck_listings
from src.listings.providers import MockListingProvider, SearchFilters
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
PROVIDER_PAYLOADS_DIR = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads"
)
AUTO_DEV_PAYLOAD_PATH = PROVIDER_PAYLOADS_DIR / "auto_dev_sample.json"
MARKETCHECK_PAYLOAD_PATH = PROVIDER_PAYLOADS_DIR / "marketcheck_sample.json"
PROVIDER_MOCK_BUYER_PROFILE_ID = "student"

PROVIDER_PIPELINE_STEPS: tuple[str, ...] = (
    "Mock provider JSON (nested Auto.dev / MarketCheck shapes)",
    "parse_auto_dev_listings() / parse_marketcheck_listings()",
    "listing_source_adapter → CarLens raw listing",
    "normalize_listing()",
    "dedupe_listings() (via rank_listings_for_recommendations)",
    "score_listing_fit() + rank → listing cards",
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return data


def search_sample_listings(
    filters: SearchFilters | None = None,
    *,
    data_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Search student sample listings via :class:`MockListingProvider`."""
    provider = MockListingProvider(data_path or SAMPLE_LISTINGS_PATH)
    result = provider.search(filters or SearchFilters())
    return result.listings


def adapt_provider_payloads() -> list[dict[str, Any]]:
    """Parse mocked provider envelopes into flat CarLens raw listings."""
    auto_payload = _load_json(AUTO_DEV_PAYLOAD_PATH)
    marketcheck_payload = _load_json(MARKETCHECK_PAYLOAD_PATH)

    adapted: list[dict[str, Any]] = []
    for index, raw in enumerate(parse_auto_dev_listings(auto_payload)):
        listing_id = raw.get("listing_id") or f"auto-dev-{index}"
        adapted.append(
            {
                "id": f"auto_dev_{listing_id}",
                "listing": raw,
                "display_name": raw.get("title"),
                "provider": "auto.dev",
            }
        )

    for index, raw in enumerate(parse_marketcheck_listings(marketcheck_payload)):
        listing_id = raw.get("listing_id") or f"marketcheck-{index}"
        adapted.append(
            {
                "id": f"marketcheck_{listing_id}",
                "listing": raw,
                "display_name": raw.get("title"),
                "provider": "marketcheck",
            }
        )
    return adapted


def listings_for_ranker(
    loaded: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    return [(item["id"], item["listing"]) for item in loaded]


def raw_listing_lookup(loaded: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item["listing"] for item in loaded}


def display_name_lookup(loaded: list[dict[str, Any]]) -> dict[str, str | None]:
    return {item["id"]: item.get("display_name") for item in loaded}


def run_provider_mock_pipeline(
    buyer_profile_id: str,
    buyer: dict[str, Any],
    loaded: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run recommend + rank on adapter output from mocked provider payloads."""
    items = loaded if loaded is not None else adapt_provider_payloads()
    listings = listings_for_ranker(items)
    result = recommend(buyer_profile_id, buyer=buyer)
    ranked = rank_listings_for_recommendations(
        listings,
        result["recommendations"],
        buyer,
    )
    return {"recommendation_result": result, "ranked": ranked, "loaded": items}


def first_ui_ready_listing(ranked_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first normalized listing dict attached to a ranked entry."""
    ranked = ranked_payload["ranked"]
    for group in ranked.get("groups") or []:
        for entry in group.get("listings") or []:
            return entry["listing"]
    for entry in ranked.get("unmatched_listings") or []:
        return entry["listing"]
    return None


def normalized_listings_from_provider_mock(
    loaded: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Normalize and dedupe adapter output (for smoke tests and diagnostics)."""
    items = loaded if loaded is not None else adapt_provider_payloads()
    normalized = [normalize_listing(item["listing"]) for item in items]
    return dedupe_listings(normalized)


def _find_buyer(buyer_profile_id: str) -> dict[str, Any]:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def main(argv: list[str] | None = None) -> int:
    """CLI demo: mock provider search + optional nested-payload pipeline."""
    import argparse

    parser = argparse.ArgumentParser(description="CarLens mock provider demo")
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Also run Auto.dev / MarketCheck adapter pipeline smoke output",
    )
    parser.add_argument(
        "--make",
        default="Toyota",
        help="Search filter make (default: Toyota)",
    )
    parser.add_argument(
        "--model",
        default="Corolla",
        help="Search filter model (default: Corolla)",
    )
    parser.add_argument(
        "--max-price",
        type=int,
        default=None,
        help="Optional max_price filter",
    )
    parser.add_argument(
        "--clean-title-only",
        action="store_true",
        help="Exclude explicitly dirty/salvage/rebuilt titles",
    )
    args = parser.parse_args(argv)

    filters = SearchFilters(
        make=args.make,
        model=args.model,
        max_price=args.max_price,
        clean_title_only=args.clean_title_only,
    )
    provider = MockListingProvider(SAMPLE_LISTINGS_PATH)
    search_result = provider.search(filters)

    print(f"Provider: {search_result.provider_name}")
    print(f"Buyer profile (sample file): {provider.buyer_profile_id}")
    print(f"Matched listings: {len(search_result.listings)}")
    if search_result.total_available is not None:
        print(f"Total in sample file: {search_result.total_available}")
    if search_result.provider_warnings:
        print(f"Provider warnings: {len(search_result.provider_warnings)}")
        for warning in search_result.provider_warnings[:5]:
            print(f"  - {warning}")
        if len(search_result.provider_warnings) > 5:
            print(f"  ... and {len(search_result.provider_warnings) - 5} more")
    if search_result.errors:
        print(f"Provider errors: {len(search_result.errors)}")
        for err in search_result.errors[:5]:
            print(f"  - {err}")

    for entry in search_result.listings[:8]:
        listing = entry["listing"]
        label = entry.get("display_name") or entry["id"]
        price = listing.get("price", "n/a")
        year = listing.get("year", "n/a")
        print(f"  - {label} ({year}, ${price})")
    if len(search_result.listings) > 8:
        print(f"  ... and {len(search_result.listings) - 8} more")

    if args.pipeline:
        print()
        print("Nested provider payload pipeline:")
        buyer = _find_buyer(PROVIDER_MOCK_BUYER_PROFILE_ID)
        payload = run_provider_mock_pipeline(PROVIDER_MOCK_BUYER_PROFILE_ID, buyer)
        pipeline = payload["ranked"]["pipeline"]
        print(f"  raw={pipeline['raw_count']} normalized={pipeline['normalized_count']} "
              f"deduped={pipeline['deduped_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
