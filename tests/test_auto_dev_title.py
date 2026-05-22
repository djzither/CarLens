"""Tests for Auto.dev explicit title mapping and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.listings.auto_dev_adapter import adapt_auto_dev_listing, pop_adapter_warnings
from src.listings.auto_dev_title import collect_raw_title_fields, pop_title_diagnostics
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_quality_summary import (
    AUTO_DEV_TITLE_UNAVAILABLE_WARNING,
    build_listing_quality_summary,
)
from src.listings.providers import AutoDevProvider, SearchFilters
from app.listing_display import (
    AUTO_DEV_TITLE_UNKNOWN_DETAIL,
    format_title_certainty_display,
    format_title_status_block,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)


def test_sample_fixture_exposes_history_without_clean_title_field() -> None:
    with SAMPLE_FIXTURE.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    row = payload["data"][0]

    fields = collect_raw_title_fields(row)
    assert "history.accidents" in fields
    assert "history.ownerCount" in fields
    assert not any("clean" in key.casefold() for key in fields)


def test_missing_title_information_maps_to_unknown() -> None:
    row = {
        "vin": "UNKNOWN01",
        "vehicle": {"year": 2016, "make": "Toyota", "model": "Corolla"},
        "retailListing": {"price": 10000, "miles": 80000},
        "history": {"accidents": False, "ownerCount": 1},
    }
    raw = adapt_auto_dev_listing(row)

    assert "clean_title" not in raw
    assert raw["title_status"] == "unknown"
    diagnostics = pop_title_diagnostics(raw)
    assert diagnostics is not None
    assert diagnostics["title_certainty"] == "unknown"
    assert diagnostics["normalized_title_status"] == "unknown"
    assert diagnostics["title_certainty"] == "unknown"


def test_explicit_clean_title_true_maps_to_clean() -> None:
    row = {
        "vin": "CLEAN01",
        "vehicle": {"year": 2018, "make": "Honda", "model": "Civic"},
        "retailListing": {"price": 12000, "miles": 70000, "cleanTitle": True},
    }
    raw = adapt_auto_dev_listing(row)

    assert raw["clean_title"] is True
    assert raw["title_status"] == "clean"
    diagnostics = pop_title_diagnostics(raw)
    assert diagnostics["title_certainty"] == "clean"
    assert diagnostics["raw_title_fields_found"]["retailListing.cleanTitle"] is True


@pytest.mark.parametrize(
    "status_field",
    ["titleStatus", "title_status", "titleBrand"],
)
def test_salvage_or_branded_provider_status_maps_to_dirty(status_field: str) -> None:
    row = {
        "vin": "DIRTY01",
        "vehicle": {"year": 2015, "make": "Subaru", "model": "XV"},
        "retailListing": {
            "price": 9000,
            "miles": 95000,
            status_field: "salvage",
        },
    }
    raw = adapt_auto_dev_listing(row)

    assert raw["clean_title"] is False
    assert raw["title_status"] == "dirty"
    diagnostics = pop_title_diagnostics(raw)
    assert diagnostics["title_certainty"] == "dirty"


def test_explicit_clean_title_false_maps_to_dirty() -> None:
    row = {
        "vin": "DIRTY02",
        "vehicle": {"year": 2014, "make": "Nissan", "model": "Altima"},
        "retailListing": {"price": 8000, "miles": 100000, "cleanTitle": False},
    }
    raw = adapt_auto_dev_listing(row)

    assert raw["clean_title"] is False
    assert raw["title_status"] == "dirty"


def test_heading_clean_carfax_does_not_infer_clean_title() -> None:
    row = {
        "vin": "HEADING01",
        "vehicle": {"year": 2016, "make": "Toyota", "model": "Corolla"},
        "retailListing": {
            "price": 10000,
            "miles": 80000,
            "heading": "2016 Toyota Corolla LE — clean Carfax, one owner",
        },
    }
    raw = adapt_auto_dev_listing(row)
    normalized = normalize_listing(raw)

    assert "clean_title" not in raw
    assert "clean_title" not in normalized
    assert normalized["title_status"] == "unknown"


def test_provider_search_emits_title_diagnostics_warning() -> None:
    provider = AutoDevProvider(SAMPLE_FIXTURE, use_live_api=False)
    result = provider.search(SearchFilters())

    assert any("title diagnostics" in warning for warning in result.provider_warnings)
    assert any("status=unknown" in warning for warning in result.provider_warnings)


def test_unknown_title_fallback_wording_auto_dev() -> None:
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 10_500,
        "mileage": 85_000,
        "title_status": "unknown",
        "source": "auto.dev",
    }
    record = {
        "id": "demo-1",
        "listing": listing,
        "provider_name": "auto.dev",
        "provider_listing_id": "demo-1",
        "provider_raw_fields": sorted(listing.keys()),
    }
    summary = build_listing_quality_summary(record)

    assert summary["title_certainty"] == "unknown"
    assert summary["warnings"] == [AUTO_DEV_TITLE_UNAVAILABLE_WARNING]
    assert format_title_certainty_display("unknown", source="auto.dev") == (
        AUTO_DEV_TITLE_UNKNOWN_DETAIL
    )
    block = format_title_status_block("unknown", source="auto.dev")
    assert AUTO_DEV_TITLE_UNKNOWN_DETAIL in block
    assert "Ask seller for title documentation" not in block
