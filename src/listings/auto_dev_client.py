from __future__ import annotations

import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.listings.listing_source_adapter import adapt_auto_dev_listing

DEFAULT_BASE_URL = "https://api.auto.dev/listings"


class AutoDevClient:
    """Thin client for Auto.dev vehicle listings."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.api_key = api_key or os.environ.get("AUTO_DEV_API_KEY")
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("AUTO_DEV_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}{path}{query}",
            headers=self._headers(),
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                import json

                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"Auto.dev request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Auto.dev response must be a JSON object")
        return payload

    def parse_listings_response(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert an Auto.dev listings envelope into CarLens raw listings."""
        data = payload.get("data")
        if data is None:
            return []
        if isinstance(data, dict):
            return [adapt_auto_dev_listing(data)]
        if not isinstance(data, list):
            raise ValueError("Auto.dev response data must be an object or array")
        return [adapt_auto_dev_listing(item) for item in data if isinstance(item, dict)]

    def search_listings(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request_json("", params)
        return self.parse_listings_response(payload)

    def get_listing_by_vin(self, vin: str) -> dict[str, Any]:
        payload = self._request_json(f"/{vin}")
        listings = self.parse_listings_response(payload)
        if not listings:
            raise RuntimeError(f"Auto.dev listing not found for VIN: {vin}")
        return listings[0]


def parse_auto_dev_listings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a listings API payload without performing a network call."""
    return AutoDevClient(api_key="offline").parse_listings_response(payload)
