"""Tests for the mock listing provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.listings.providers.mock_provider import MockListingProvider

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDENT_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


@pytest.fixture
def provider() -> MockListingProvider:
    return MockListingProvider(STUDENT_LISTINGS_PATH)


def _listing(entry: dict) -> dict:
    return entry["listing"]


def test_returns_corolla_listings(provider: MockListingProvider) -> None:
    results = provider.search_listings({"make": "Toyota", "model": "Corolla"})
    assert results
    assert all(
        _normalize(_listing(entry).get("make")) == "toyota"
        and _normalize(_listing(entry).get("model")) == "corolla"
        for entry in results
    )


def test_filters_out_wrong_make_model(provider: MockListingProvider) -> None:
    corollas = provider.search_listings({"make": "Toyota", "model": "Corolla"})
    civics = provider.search_listings({"make": "Honda", "model": "Civic"})
    corolla_ids = {entry["id"] for entry in corollas}
    civic_ids = {entry["id"] for entry in civics}
    assert corolla_ids.isdisjoint(civic_ids)
    assert "good_corolla" in corolla_ids
    assert "good_civic" in civic_ids
    assert "good_corolla" not in civic_ids


def test_respects_max_price(provider: MockListingProvider) -> None:
    results = provider.search_listings(
        {"make": "Toyota", "model": "Corolla", "max_price": 12000}
    )
    ids = {entry["id"] for entry in results}
    assert "over_budget_corolla" not in ids
    assert "good_corolla" in ids
    for entry in results:
        price = _listing(entry).get("price")
        if price is not None:
            assert float(price) <= 12000


def test_missing_mileage_does_not_crash(provider: MockListingProvider) -> None:
    results = provider.search_listings(
        {"make": "Toyota", "model": "Corolla", "max_mileage": 200_000}
    )
    ids = {entry["id"] for entry in results}
    assert "missing_mileage_corolla" in ids


def _normalize(value: object) -> str:
    return str(value).strip().casefold()
