from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from src.listings.listing_source_adapter import adapt_auto_dev_listing

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.auto.dev/listings"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1.0
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
AUTODEV_API_KEY_ENV = "AUTODEV_API_KEY"
LEGACY_API_KEY_ENV = "AUTO_DEV_API_KEY"


@dataclass(frozen=True)
class AutoDevSearchParams:
    """Server-side Auto.dev listing search parameters."""

    make: str | None = None
    model: str | None = None
    price_max: int | None = None
    mileage_max: int | None = None
    year_min: int | None = None
    year_max: int | None = None
    page: int | None = None
    page_size: int | None = None


@dataclass
class AutoDevClientResult:
    """Raw API payload plus any provider-level errors (never raises)."""

    payload: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def resolve_autodev_api_key(
    *,
    api_key: str | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    """Read AUTODEV_API_KEY from the environment (with legacy alias)."""
    if api_key:
        return api_key
    env = os.environ if environ is None else environ
    return env.get(AUTODEV_API_KEY_ENV) or env.get(LEGACY_API_KEY_ENV)


def build_search_query_params(params: AutoDevSearchParams) -> dict[str, str]:
    """Map CarLens search knobs to Auto.dev query parameters."""
    query: dict[str, str] = {}

    if params.make:
        query["vehicle.make"] = params.make.strip()
    if params.model:
        query["vehicle.model"] = params.model.strip()

    if params.year_min is not None or params.year_max is not None:
        low = str(params.year_min) if params.year_min is not None else "1900"
        high = str(params.year_max) if params.year_max is not None else "2099"
        query["vehicle.year"] = f"{low}-{high}"

    if params.price_max is not None:
        query["retailListing.price"] = f"1-{params.price_max}"

    if params.mileage_max is not None:
        query["retailListing.miles"] = f"0-{params.mileage_max}"

    if params.page is not None:
        query["page"] = str(params.page)
    if params.page_size is not None:
        query["limit"] = str(params.page_size)

    return query


def search_params_from_filters(
    *,
    make: str | None = None,
    model: str | None = None,
    price_max: int | None = None,
    mileage_max: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> AutoDevSearchParams:
    return AutoDevSearchParams(
        make=make,
        model=model,
        price_max=price_max,
        mileage_max=mileage_max,
        year_min=year_min,
        year_max=year_max,
        page=page,
        page_size=page_size,
    )


def _cache_key(path: str, params: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return path, tuple(sorted(params.items()))


class _ResponseCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, tuple[tuple[str, str], ...]], dict[str, Any]] = {}

    def get(self, path: str, params: dict[str, str]) -> dict[str, Any] | None:
        return self._entries.get(_cache_key(path, params))

    def set(self, path: str, params: dict[str, str], payload: dict[str, Any]) -> None:
        self._entries[_cache_key(path, params)] = payload

    def clear(self) -> None:
        self._entries.clear()


def _build_session() -> requests.Session:
    return requests.Session()


def _retry_delay(attempt: int) -> float:
    return RETRY_BACKOFF_FACTOR * (2**attempt)


class AutoDevClient:
    """Thin HTTP client for Auto.dev vehicle listings (raw payloads only)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        cache: _ResponseCache | None = None,
        use_cache: bool = True,
    ) -> None:
        self.api_key = resolve_autodev_api_key(api_key=api_key)
        self.base_url = base_url.rstrip("/")
        self._session = session or _build_session()
        self._cache = cache if cache is not None else _ResponseCache()
        self._use_cache = use_cache

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError(f"{AUTODEV_API_KEY_ENV} is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _fetch_json(self, path: str, params: dict[str, str]) -> AutoDevClientResult:
        if not self.api_key:
            return AutoDevClientResult(
                payload={},
                errors=[f"{AUTODEV_API_KEY_ENV} is not configured"],
            )

        if self._use_cache:
            cached = self._cache.get(path, params)
            if cached is not None:
                return AutoDevClientResult(payload=cached)

        url = f"{self.base_url}{path}"
        response: requests.Response | None = None
        last_error: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                logger.info("Auto.dev request made")
                response = self._session.get(
                    url,
                    headers=self._headers(),
                    params=params or None,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.Timeout as exc:
                last_error = f"Auto.dev request timed out: {exc}"
                if attempt < MAX_RETRIES:
                    time.sleep(_retry_delay(attempt))
                    continue
                return AutoDevClientResult(payload={}, errors=[last_error])
            except requests.RequestException as exc:
                last_error = f"Auto.dev request failed: {exc}"
                if attempt < MAX_RETRIES:
                    time.sleep(_retry_delay(attempt))
                    continue
                return AutoDevClientResult(payload={}, errors=[last_error])

            if (
                response is not None
                and response.status_code in TRANSIENT_STATUS_CODES
                and attempt < MAX_RETRIES
            ):
                time.sleep(_retry_delay(attempt))
                continue
            break

        if response is None:
            return AutoDevClientResult(
                payload={},
                errors=[last_error or "Auto.dev request failed"],
            )

        if response.status_code in TRANSIENT_STATUS_CODES:
            return AutoDevClientResult(
                payload={},
                errors=[
                    f"Auto.dev request failed after retries: HTTP {response.status_code}"
                ],
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return AutoDevClientResult(
                payload={},
                errors=[f"Auto.dev response was not valid JSON: {exc}"],
            )

        if not isinstance(payload, dict):
            return AutoDevClientResult(
                payload={},
                errors=["Auto.dev response must be a JSON object"],
            )

        if response.status_code >= 400:
            message = payload.get("error") or payload.get("message")
            detail = message or f"HTTP {response.status_code}"
            return AutoDevClientResult(
                payload={},
                errors=[f"Auto.dev request failed: {detail}"],
            )

        if self._use_cache:
            self._cache.set(path, params, payload)
        return AutoDevClientResult(payload=payload)

    def search_listings(
        self,
        params: AutoDevSearchParams | None = None,
        **kwargs: Any,
    ) -> AutoDevClientResult:
        """Search listings; returns the raw API envelope (never raises)."""
        search_params = params or search_params_from_filters(**kwargs)
        query = build_search_query_params(search_params)
        return self._fetch_json("", query)

    def search_listings_paginated(
        self,
        params: AutoDevSearchParams | None = None,
        *,
        max_pages: int = 10,
        **kwargs: Any,
    ) -> AutoDevClientResult:
        """Fetch and merge listing pages until `links.next` is absent (never raises)."""
        search_params = params or search_params_from_filters(**kwargs)
        start_page = search_params.page or 1
        page_payloads: list[dict[str, Any]] = []
        errors: list[str] = []

        for offset in range(max_pages):
            page = start_page + offset
            page_params = AutoDevSearchParams(
                make=search_params.make,
                model=search_params.model,
                price_max=search_params.price_max,
                mileage_max=search_params.mileage_max,
                year_min=search_params.year_min,
                year_max=search_params.year_max,
                page=page,
                page_size=search_params.page_size,
            )
            result = self.search_listings(page_params)
            if result.errors:
                return AutoDevClientResult(payload={}, errors=result.errors)
            if not result.payload:
                break

            page_payloads.append(result.payload)
            links = result.payload.get("links")
            has_next = isinstance(links, dict) and bool(links.get("next"))
            if not has_next:
                break

        if not page_payloads:
            return AutoDevClientResult(payload={}, errors=errors)
        return AutoDevClientResult(payload=merge_auto_dev_page_payloads(page_payloads))

    def get_listing_by_vin(self, vin: str) -> AutoDevClientResult:
        """Fetch one listing by VIN; returns the raw API envelope (never raises)."""
        cleaned = vin.strip()
        if not cleaned:
            return AutoDevClientResult(payload={}, errors=["VIN is required"])
        return self._fetch_json(f"/{cleaned}", {})


def merge_auto_dev_page_payloads(
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge paginated Auto.dev responses in page order."""
    merged_rows: list[dict[str, Any]] = []
    links: dict[str, Any] = {}
    for page_payload in pages:
        if not isinstance(page_payload, dict):
            continue
        merged_rows.extend(iter_auto_dev_provider_rows(page_payload))
        page_links = page_payload.get("links")
        if isinstance(page_links, dict):
            links = page_links
    return {"data": merged_rows, "links": links}


def resolve_fixture_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a single listings envelope from a fixture (supports `pages`)."""
    pages = payload.get("pages")
    if isinstance(pages, list) and pages:
        return merge_auto_dev_page_payloads(pages)
    return payload


def iter_auto_dev_provider_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract provider listing objects from an Auto.dev envelope."""
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def parse_auto_dev_listings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a listings API payload into CarLens raw listings (no HTTP)."""
    return [
        adapt_auto_dev_listing(item)
        for item in iter_auto_dev_provider_rows(payload)
    ]
