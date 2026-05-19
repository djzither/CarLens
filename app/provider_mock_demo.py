"""Load mocked provider API payloads and run them through the listing adapter pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.listings.auto_dev_client import parse_auto_dev_listings
from src.listings.listing_deduper import dedupe_listings
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_ranker import rank_listings_for_recommendations
from src.listings.marketcheck_client import parse_marketcheck_listings
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
