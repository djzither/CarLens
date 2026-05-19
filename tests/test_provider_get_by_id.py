"""get_by_id uses direct raw lookup, not full search()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.listings.providers import (
    AutoDevProvider,
    MarketcheckProvider,
    MockListingProvider,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDENT_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
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

AUTO_DEV_VIN = "5YFBURHE5GP123456"
MARKETCHECK_ID = "mc-demo-civic-2016"


@pytest.fixture
def mock_provider() -> MockListingProvider:
    return MockListingProvider(STUDENT_LISTINGS_PATH)


@pytest.fixture
def auto_dev() -> AutoDevProvider:
    return AutoDevProvider(AUTO_DEV_FIXTURE)


@pytest.fixture
def marketcheck() -> MarketcheckProvider:
    return MarketcheckProvider(MARKETCHECK_FIXTURE)


def test_mock_get_by_id_does_not_call_search(mock_provider: MockListingProvider) -> None:
    with patch.object(mock_provider, "search") as search_mock:
        record = mock_provider.get_by_id("good_corolla")
        search_mock.assert_not_called()
    assert record is not None


def test_auto_dev_get_by_id_does_not_call_search(auto_dev: AutoDevProvider) -> None:
    with patch.object(auto_dev, "search") as search_mock:
        record = auto_dev.get_by_id(AUTO_DEV_VIN)
        search_mock.assert_not_called()
    assert record is not None


def test_marketcheck_get_by_id_does_not_call_search(
    marketcheck: MarketcheckProvider,
) -> None:
    with patch.object(marketcheck, "search") as search_mock:
        record = marketcheck.get_by_id(MARKETCHECK_ID)
        search_mock.assert_not_called()
    assert record is not None


def test_get_by_id_returns_provenance(mock_provider: MockListingProvider) -> None:
    record = mock_provider.get_by_id("good_corolla")
    assert record is not None
    assert record["provider_name"] == "mock"
    assert record["provider_listing_id"] == "good_corolla"
    assert record["provider_raw_fields"]


def test_get_by_id_missing_id_returns_none(mock_provider: MockListingProvider) -> None:
    assert mock_provider.get_by_id("not_a_real_listing_id") is None


def test_get_by_id_invalid_listing_returns_none(
    mock_provider: MockListingProvider,
) -> None:
    assert mock_provider.get_by_id("missing_price_corolla") is None


def test_auto_dev_get_by_id_uses_listing_id(auto_dev: AutoDevProvider) -> None:
    record = auto_dev.get_by_id(AUTO_DEV_VIN)
    assert record is not None
    assert record["provider_listing_id"] == AUTO_DEV_VIN
    assert record["listing"]["source"] == "auto.dev"
