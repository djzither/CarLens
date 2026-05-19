"""get_by_id uses direct raw lookup, not full search()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.listings.providers import (
    AutoDevProvider,
    MarketcheckProvider,
    MockListingProvider,
    validate_provider_listing_record,
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


def test_auto_dev_get_by_id_found_listing(auto_dev: AutoDevProvider) -> None:
    record = auto_dev.get_by_id(AUTO_DEV_VIN)
    assert record is not None
    assert record["id"] == AUTO_DEV_VIN
    assert record["listing"]["make"] == "Toyota"
    assert record["listing"]["model"] == "Corolla"


def test_auto_dev_get_by_id_unknown_id_returns_none(auto_dev: AutoDevProvider) -> None:
    assert auto_dev.get_by_id("UNKNOWN_VIN_NOT_IN_FIXTURE") is None


def test_marketcheck_get_by_id_found_listing(
    marketcheck: MarketcheckProvider,
) -> None:
    record = marketcheck.get_by_id(MARKETCHECK_ID)
    assert record is not None
    assert record["id"] == MARKETCHECK_ID
    assert record["listing"]["make"] == "Honda"
    assert record["listing"]["model"] == "Civic"


def test_marketcheck_get_by_id_unknown_id_returns_none(
    marketcheck: MarketcheckProvider,
) -> None:
    assert marketcheck.get_by_id("mc-not-in-fixture") is None


@pytest.mark.parametrize(
    ("provider_fixture", "listing_id", "provider_name"),
    [
        ("auto_dev", AUTO_DEV_VIN, "auto.dev"),
        ("marketcheck", MARKETCHECK_ID, "marketcheck"),
    ],
)
def test_fixture_providers_get_by_id_attaches_provenance(
    provider_fixture: str,
    listing_id: str,
    provider_name: str,
    auto_dev: AutoDevProvider,
    marketcheck: MarketcheckProvider,
) -> None:
    provider = auto_dev if provider_fixture == "auto_dev" else marketcheck
    record = provider.get_by_id(listing_id)
    assert record is not None
    assert record["provider_name"] == provider_name
    assert record["provider_listing_id"] == listing_id
    assert isinstance(record["provider_raw_fields"], list)
    assert record["provider_raw_fields"]


@pytest.mark.parametrize(
    ("provider_fixture", "listing_id"),
    [
        ("auto_dev", AUTO_DEV_VIN),
        ("marketcheck", MARKETCHECK_ID),
    ],
)
def test_fixture_providers_get_by_id_passes_record_validation(
    provider_fixture: str,
    listing_id: str,
    auto_dev: AutoDevProvider,
    marketcheck: MarketcheckProvider,
) -> None:
    provider = auto_dev if provider_fixture == "auto_dev" else marketcheck
    record = provider.get_by_id(listing_id)
    assert record is not None
    ok, errors = validate_provider_listing_record(record)
    assert ok, errors
