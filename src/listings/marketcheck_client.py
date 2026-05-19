from __future__ import annotations

import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.listings.listing_source_adapter import adapt_marketcheck_listing

DEFAULT_BASE_URL = "https://api.marketcheck.com/v2/search/car/active"


class MarketcheckClient:
    """Thin client for MarketCheck inventory search."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.api_key = api_key or os.environ.get("MARKETCHECK_API_KEY")
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("MARKETCHECK_API_KEY is not configured")
        return {"Content-Type": "application/json"}

    def _request_json(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query_params = dict(params or {})
        query_params.setdefault("api_key", self.api_key)
        query = f"?{urlencode(query_params)}"
        request = Request(
            f"{self.base_url}{query}",
            headers=self._headers(),
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                import json

                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f"MarketCheck request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("MarketCheck response must be a JSON object")
        return payload

    def parse_listings_response(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert a MarketCheck search envelope into CarLens raw listings."""
        listings = payload.get("listings")
        if listings is None:
            return []
        if not isinstance(listings, list):
            raise ValueError("MarketCheck response listings must be an array")
        return [
            adapt_marketcheck_listing(item)
            for item in listings
            if isinstance(item, dict)
        ]

    def search_listings(self, **params: Any) -> list[dict[str, Any]]:
        payload = self._request_json(params)
        return self.parse_listings_response(payload)


def parse_marketcheck_listings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a search API payload without performing a network call."""
    return MarketcheckClient(api_key="offline").parse_listings_response(payload)
