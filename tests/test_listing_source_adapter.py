"""Tests for provider listing adapters (mock payloads only)."""

from __future__ import annotations

import pytest

from src.listings.listing_deduper import dedupe_listings
from src.listings.listing_fit import score_listing_fit
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_ranker import rank_listings_for_recommendations
from src.listings.listing_source_adapter import (
    AUTO_DEV_SOURCE,
    MARKETCHECK_SOURCE,
    adapt_auto_dev_listing,
    adapt_marketcheck_listing,
)
from src.listings.auto_dev_client import parse_auto_dev_listings
from src.listings.marketcheck_client import parse_marketcheck_listings

AUTO_DEV_SAMPLE = {
    "vin": "5YFBURHE5GP123456",
    "distance": 12.4,
    "vehicle": {
        "vin": "5YFBURHE5GP123456",
        "year": 2016,
        "make": "Toyota",
        "model": "Corolla",
        "trim": "LE",
        "drivetrain": "FWD",
    },
    "retailListing": {
        "price": 10500,
        "miles": 92000,
        "vdp": "https://dealer.example/auto-dev-corolla",
        "primaryImage": "https://photos.example/auto-dev-corolla.jpg",
        "city": "Portland",
        "state": "OR",
        "zip": "97201",
    },
    "history": {"accidents": False},
}

MARKETCHECK_SAMPLE = {
    "id": "mc-listing-123",
    "vin": "5YFBURHE5GP123456",
    "heading": "2016 Toyota Corolla LE",
    "price": 10500,
    "miles": 92000,
    "vdp_url": "https://dealer.example/marketcheck-corolla",
    "dist": 8.2,
    "carfax_clean_title": True,
    "media": {
        "photo_links": ["https://photos.example/marketcheck-corolla.jpg"],
    },
    "build": {
        "year": 2016,
        "make": "Toyota",
        "model": "Corolla",
        "trim": "LE",
        "drivetrain": "FWD",
    },
    "dealer": {"city": "Portland", "state": "OR", "zip": "97201"},
}

BUYER = {
    "id": "student",
    "budget_type": {"max_amount": 12000},
    "max_mileage": 120000,
    "hard_requirements": [],
}

RECOMMENDATION = {
    "make": "Toyota",
    "model": "Corolla",
    "normalized_score": 0.9,
    "selected_year_range": {"start_year": 2014, "end_year": 2018},
}


def test_auto_dev_maps_to_carlens_raw_schema():
    raw = adapt_auto_dev_listing(AUTO_DEV_SAMPLE)

    assert raw["source"] == AUTO_DEV_SOURCE
    assert raw["listing_id"] == "5YFBURHE5GP123456"
    assert raw["make"] == "Toyota"
    assert raw["model"] == "Corolla"
    assert raw["year"] == 2016
    assert raw["price"] == 10500
    assert raw["mileage"] == 92000
    assert raw["listing_url"] == "https://dealer.example/auto-dev-corolla"
    assert raw["image_url"] == "https://photos.example/auto-dev-corolla.jpg"
    assert raw["distance_miles"] == 12
    assert "retailListing" not in raw
    assert "vehicle" not in raw


def test_marketcheck_maps_to_carlens_raw_schema():
    raw = adapt_marketcheck_listing(MARKETCHECK_SAMPLE)

    assert raw["source"] == MARKETCHECK_SOURCE
    assert raw["listing_id"] == "mc-listing-123"
    assert raw["make"] == "Toyota"
    assert raw["model"] == "Corolla"
    assert raw["year"] == 2016
    assert raw["price"] == 10500
    assert raw["mileage"] == 92000
    assert raw["title"] == "2016 Toyota Corolla LE"
    assert raw["listing_url"] == "https://dealer.example/marketcheck-corolla"
    assert raw["image_url"] == "https://photos.example/marketcheck-corolla.jpg"
    assert raw["distance_miles"] == 8
    assert "build" not in raw
    assert "media" not in raw


def test_missing_price_mileage_title_handled_safely():
    auto_raw = adapt_auto_dev_listing(
        {
            "vin": "VIN123",
            "vehicle": {"year": 2016, "make": "Toyota", "model": "Corolla"},
            "retailListing": {},
        }
    )
    assert "price" not in auto_raw
    assert "mileage" not in auto_raw
    auto_norm = normalize_listing(auto_raw)
    assert auto_norm["make"] == "Toyota"
    assert "price" not in auto_norm
    assert "mileage" not in auto_norm

    mc_raw = adapt_marketcheck_listing(
        {
            "id": "sparse-mc",
            "build": {"year": 2016, "make": "Toyota", "model": "Corolla"},
        }
    )
    assert mc_raw["title"] == "2016 Toyota Corolla"
    mc_norm = normalize_listing(mc_raw)
    assert "price" not in mc_norm
    assert "mileage" not in mc_norm


def test_urls_and_distance_preserved_through_pipeline():
    for adapter_fn, sample in (
        (adapt_auto_dev_listing, AUTO_DEV_SAMPLE),
        (adapt_marketcheck_listing, MARKETCHECK_SAMPLE),
    ):
        raw = adapter_fn(sample)
        normalized = normalize_listing(raw)
        assert normalized["listing_url"] == raw["listing_url"]
        assert normalized["image_url"] == raw["image_url"]
        assert normalized["distance_miles"] == raw["distance_miles"]


def test_adapted_listings_flow_through_ranking_pipeline():
    auto_sample = dict(AUTO_DEV_SAMPLE)
    auto_sample["retailListing"] = {
        **auto_sample["retailListing"],
        "price": 10500,
        "vdp": "https://dealer.example/auto-dev-only",
    }
    mc_sample = dict(MARKETCHECK_SAMPLE)
    mc_sample["price"] = 15000
    mc_sample["vdp_url"] = "https://dealer.example/marketcheck-only"

    scenarios = [
        ("auto_dev", adapt_auto_dev_listing(auto_sample)),
        ("marketcheck", adapt_marketcheck_listing(mc_sample)),
    ]
    deduped = dedupe_listings([normalize_listing(raw) for _, raw in scenarios])
    assert len(deduped) == 2

    fit = score_listing_fit(deduped[0], RECOMMENDATION, BUYER)
    assert fit["fit_score"] > 0

    ranked = rank_listings_for_recommendations(
        scenarios,
        [RECOMMENDATION],
        BUYER,
    )
    assert ranked["pipeline"]["raw_count"] == 2
    assert ranked["pipeline"]["deduped_count"] == 2


def test_client_parsers_use_adapter_without_network():
    auto = parse_auto_dev_listings({"data": [AUTO_DEV_SAMPLE]})
    assert len(auto) == 1
    assert auto[0]["source"] == AUTO_DEV_SOURCE

    mc = parse_marketcheck_listings({"listings": [MARKETCHECK_SAMPLE]})
    assert len(mc) == 1
    assert mc[0]["source"] == MARKETCHECK_SOURCE


def test_adapter_rejects_non_object():
    with pytest.raises(ValueError):
        adapt_auto_dev_listing("not-a-dict")
