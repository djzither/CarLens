"""Tests for AutoDevClient (mocked HTTP only — no live API calls)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.listings.auto_dev_client import (
    AUTODEV_API_KEY_ENV,
    MAX_RETRIES,
    AutoDevClient,
    AutoDevSearchParams,
    _ResponseCache,
    build_search_query_params,
    resolve_autodev_api_key,
)
from src.listings.providers import AutoDevProvider, ListingSearchService, SearchFilters

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTO_DEV_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)

SAMPLE_PAYLOAD = {
    "data": [
        {
            "vin": "5YFBURHE5GP123456",
            "vehicle": {
                "vin": "5YFBURHE5GP123456",
                "year": 2016,
                "make": "Toyota",
                "model": "Corolla",
            },
            "retailListing": {"price": 10500, "miles": 92000},
        }
    ]
}


def _mock_response(
    *,
    status_code: int = 200,
    payload: dict | None = None,
    json_error: bool = False,
) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    if json_error:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = payload if payload is not None else SAMPLE_PAYLOAD
    return response


@pytest.fixture
def session() -> MagicMock:
    return MagicMock(spec=requests.Session)


@pytest.fixture
def client(session: MagicMock) -> AutoDevClient:
    return AutoDevClient(
        api_key="test-key",
        session=session,
        cache=_ResponseCache(),
        use_cache=True,
    )


def test_resolve_api_key_prefers_autodev_env() -> None:
    assert (
        resolve_autodev_api_key(
            environ={AUTODEV_API_KEY_ENV: "primary", "AUTO_DEV_API_KEY": "legacy"}
        )
        == "primary"
    )


def test_missing_api_key_returns_error_without_http(session: MagicMock) -> None:
    client = AutoDevClient(api_key=None, session=session, use_cache=False)
    result = client.search_listings(
        AutoDevSearchParams(make="Toyota", model="Corolla"),
    )

    assert result.payload == {}
    assert any("not configured" in message for message in result.errors)
    session.get.assert_not_called()


def test_timeout_records_error_and_empty_payload(
    client: AutoDevClient, session: MagicMock
) -> None:
    session.get.side_effect = requests.Timeout("timed out")

    with patch("src.listings.auto_dev_client.time.sleep"):
        result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert result.payload == {}
    assert any("timed out" in message for message in result.errors)


def test_request_exception_records_error(
    client: AutoDevClient, session: MagicMock
) -> None:
    session.get.side_effect = requests.ConnectionError("connection reset")

    with patch("src.listings.auto_dev_client.time.sleep"):
        result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert result.payload == {}
    assert any("connection reset" in message for message in result.errors)


def test_retry_path_eventually_succeeds(session: MagicMock) -> None:
    session.get.side_effect = [
        _mock_response(status_code=503),
        _mock_response(status_code=502),
        _mock_response(status_code=200, payload=SAMPLE_PAYLOAD),
    ]
    client = AutoDevClient(api_key="test-key", session=session, use_cache=False)

    with patch("src.listings.auto_dev_client.time.sleep"):
        result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert session.get.call_count == 3
    assert result.errors == []
    assert result.payload["data"][0]["vin"] == "5YFBURHE5GP123456"


def test_transient_status_after_retries_records_error(
    client: AutoDevClient, session: MagicMock
) -> None:
    session.get.return_value = _mock_response(status_code=503)

    with patch("src.listings.auto_dev_client.time.sleep"):
        result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert session.get.call_count == MAX_RETRIES + 1
    assert result.payload == {}
    assert any("503" in message for message in result.errors)


def test_api_error_status_returns_empty_payload(
    client: AutoDevClient, session: MagicMock
) -> None:
    session.get.return_value = _mock_response(
        status_code=400,
        payload={"error": "Invalid parameter", "status": 400},
    )

    result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert result.payload == {}
    assert any("Invalid parameter" in message for message in result.errors)


def test_invalid_json_records_error(client: AutoDevClient, session: MagicMock) -> None:
    session.get.return_value = _mock_response(json_error=True)

    result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert result.payload == {}
    assert any("valid JSON" in message for message in result.errors)


def test_success_returns_raw_payload_only(
    client: AutoDevClient, session: MagicMock
) -> None:
    session.get.return_value = _mock_response(payload=SAMPLE_PAYLOAD)

    result = client.search_listings(AutoDevSearchParams(make="Toyota"))

    assert result.errors == []
    assert "data" in result.payload
    assert result.payload["data"][0]["vehicle"]["make"] == "Toyota"
    assert "listing_id" not in result.payload["data"][0]


def test_build_search_query_params_maps_filters() -> None:
    params = AutoDevSearchParams(
        make="Toyota",
        model="Corolla",
        price_max=30000,
        mileage_max=120000,
        year_min=2015,
        year_max=2020,
        page=2,
        page_size=25,
    )

    query = build_search_query_params(params)

    assert query == {
        "vehicle.make": "Toyota",
        "vehicle.model": "Corolla",
        "vehicle.year": "2015-2020",
        "retailListing.price": "1-30000",
        "retailListing.miles": "0-120000",
        "page": "2",
        "limit": "25",
    }


def test_search_passes_query_params_to_session(
    client: AutoDevClient, session: MagicMock
) -> None:
    session.get.return_value = _mock_response()

    client.search_listings(
        AutoDevSearchParams(make="Honda", model="Civic", page=1, page_size=10),
    )

    _, kwargs = session.get.call_args
    assert kwargs["params"]["vehicle.make"] == "Honda"
    assert kwargs["params"]["vehicle.model"] == "Civic"
    assert kwargs["params"]["page"] == "1"
    assert kwargs["params"]["limit"] == "10"
    assert kwargs["timeout"] == 10


def test_request_logging(client: AutoDevClient, session: MagicMock) -> None:
    session.get.return_value = _mock_response()

    with patch("src.listings.auto_dev_client.logger") as log_mock:
        client.search_listings(AutoDevSearchParams(make="Toyota"))

    log_mock.info.assert_called_once_with("Auto.dev request made")


def test_cache_avoids_duplicate_requests(client: AutoDevClient, session: MagicMock) -> None:
    session.get.return_value = _mock_response()

    first = client.search_listings(AutoDevSearchParams(make="Toyota", model="Corolla"))
    second = client.search_listings(AutoDevSearchParams(make="Toyota", model="Corolla"))

    assert first.payload == second.payload
    session.get.assert_called_once()


def test_fixture_fallback_on_api_failure() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.return_value = _mock_response(
        status_code=500,
        payload={"error": "upstream"},
    )
    provider = AutoDevProvider(
        AUTO_DEV_FIXTURE,
        client=AutoDevClient(api_key="test-key", session=session, use_cache=False),
    )

    result = provider.search(SearchFilters(make="Toyota", model="Corolla"))

    assert result.listings
    assert result.listings[0]["listing"]["make"] == "Toyota"
    assert any("Auto.dev" in message for message in result.errors)


def test_fixture_fallback_when_api_key_missing() -> None:
    session = MagicMock(spec=requests.Session)
    provider = AutoDevProvider(
        AUTO_DEV_FIXTURE,
        client=AutoDevClient(api_key=None, session=session, use_cache=False),
    )

    result = provider.search(SearchFilters())

    assert result.listings
    session.get.assert_not_called()


def test_aggregate_search_continues_with_fixture_fallback() -> None:
    session = MagicMock(spec=requests.Session)
    session.get.side_effect = requests.ConnectionError("offline")
    auto_provider = AutoDevProvider(
        AUTO_DEV_FIXTURE,
        client=AutoDevClient(api_key="test-key", session=session, use_cache=False),
    )
    service = ListingSearchService([auto_provider])

    result = service.search(SearchFilters(make="Toyota", model="Corolla"))

    assert result.listings
    assert any("Auto.dev" in err for err in result.errors)
