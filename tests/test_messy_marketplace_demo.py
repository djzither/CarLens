from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.listings.listing_ranker import rank_listings_for_recommendations
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MESSY_PATH = PROJECT_ROOT / "data" / "sample_listings" / "messy_marketplace_demo.json"


def _load_messy() -> tuple[str, list[tuple[str, dict]]]:
    with MESSY_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    listings = [(entry["id"], entry["listing"]) for entry in data["listings"]]
    return data["buyer_profile_id"], listings


def test_messy_marketplace_demo_file_exists():
    assert MESSY_PATH.is_file()


def test_messy_marketplace_demo_has_rich_listing_count():
    _, listings = _load_messy()
    assert 25 <= len(listings) <= 45


def test_messy_marketplace_demo_pipeline_runs():
    buyer_profile_id, listings = _load_messy()
    buyer = next(
        p for p in load_buyer_profiles()["profiles"] if p["id"] == buyer_profile_id
    )
    recommendations = recommend(buyer_profile_id)["recommendations"]
    ranked = rank_listings_for_recommendations(listings, recommendations, buyer)

    assert ranked["pipeline"]["raw_count"] == len(listings)
    assert ranked["pipeline"]["deduped_count"] < ranked["pipeline"]["raw_count"]
    assert ranked["groups"]
    assert ranked["unmatched_listings"]
