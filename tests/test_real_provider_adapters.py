"""Fixture-backed real provider skeletons normalize to a shared SearchResult shape."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.listings.listing_fit import score_listing_fit
from src.listings.listing_normalizer import normalize_listing
from src.listings.listing_source_adapter import adapt_auto_dev_listing, adapt_marketcheck_listing
from src.listings.providers import (
    PROVIDER_LISTING_RECORD_KEYS,
    AutoDevProvider,
    MarketcheckProvider,
    SearchFilters,
    provider_clean_title_is_unknown,
    validate_provider_listing_record,
)
from src.listings.provider_clean_title import apply_explicit_clean_title

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTO_DEV_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)
MARKETCHECK_FIXTURE = (
    PROJECT_ROOT
    / "data"
    / "sample_listings"
    / "provider_payloads"
    / "marketcheck_sample.json"
)

AUTO_DEV_ROW = {
    "vin": "5YFBURHE5GP123456",
    "vehicle": {
        "year": 2016,
        "make": "Toyota",
        "model": "Corolla",
        "trim": "LE",
    },
    "retailListing": {"price": 10500, "miles": 92000},
}

MARKETCHECK_ROW = {
    "id": "mc-listing-123",
    "heading": "2016 Honda Civic LX",
    "price": 10950,
    "miles": 88000,
    "build": {"year": 2016, "make": "Honda", "model": "Civic"},
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


@pytest.fixture
def auto_dev() -> AutoDevProvider:
    return AutoDevProvider(AUTO_DEV_FIXTURE)


@pytest.fixture
def marketcheck() -> MarketcheckProvider:
    return MarketcheckProvider(MARKETCHECK_FIXTURE)


def _record_keys(record: dict) -> set[str]:
    return set(record.keys())


def test_auto_dev_provider_returns_search_result(auto_dev: AutoDevProvider) -> None:
    result = auto_dev.search(SearchFilters(make="Toyota", model="Corolla"))
    assert result.provider_name == "auto.dev"
    assert result.listings
    assert all(validate_provider_listing_record(item)[0] for item in result.listings)


def test_marketcheck_provider_returns_search_result(
    marketcheck: MarketcheckProvider,
) -> None:
    result = marketcheck.search(SearchFilters(make="Honda", model="Civic"))
    assert result.provider_name == "marketcheck"
    assert result.listings
    assert all(validate_provider_listing_record(item)[0] for item in result.listings)


def test_both_providers_share_listing_record_shape(
    auto_dev: AutoDevProvider,
    marketcheck: MarketcheckProvider,
) -> None:
    auto_record = auto_dev.search(SearchFilters()).listings[0]
    mc_record = marketcheck.search(SearchFilters()).listings[0]

    for record in (auto_record, mc_record):
        assert PROVIDER_LISTING_RECORD_KEYS <= _record_keys(record)
        assert record["provider_name"] in {"auto.dev", "marketcheck"}
        assert isinstance(record["listing"], dict)
        assert isinstance(record["provider_raw_fields"], list)
        assert record["provider_listing_id"]

    assert auto_record["provider_name"] == "auto.dev"
    assert mc_record["provider_name"] == "marketcheck"


def test_adapted_auto_dev_missing_clean_title_is_unknown() -> None:
    raw = adapt_auto_dev_listing(AUTO_DEV_ROW)
    assert provider_clean_title_is_unknown(raw)
    normalized = normalize_listing(raw)
    assert normalized.get("clean_title") is not False


def test_adapted_marketcheck_without_carfax_field_is_unknown() -> None:
    row = dict(MARKETCHECK_ROW)
    raw = adapt_marketcheck_listing(row)
    assert provider_clean_title_is_unknown(raw)


def test_apply_explicit_clean_title_only_sets_known_values() -> None:
    raw: dict = {}
    apply_explicit_clean_title(raw, None)
    assert "clean_title" not in raw
    apply_explicit_clean_title(raw, True)
    assert raw["clean_title"] is True
    raw.clear()
    apply_explicit_clean_title(raw, False)
    assert raw["clean_title"] is False


def test_adapted_dirty_title_caps_fit_label_to_weak() -> None:
    row = {
        **MARKETCHECK_ROW,
        "carfax_clean_title": False,
        "heading": "2016 Toyota Corolla LE",
        "build": {"year": 2016, "make": "Toyota", "model": "Corolla", "trim": "LE"},
    }
    raw = adapt_marketcheck_listing(row)
    assert raw["clean_title"] is False
    fit = score_listing_fit(normalize_listing(raw), RECOMMENDATION, BUYER)
    assert fit["fit_label"] == "Weak fit"
