"""Shared types for listing provider search."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchFilters:
    """Server-style filters applied by a listing provider before scoring."""

    make: str | None = None
    model: str | None = None
    min_year: int | None = None
    max_year: int | None = None
    max_price: int | None = None
    max_mileage: int | None = None
    clean_title_only: bool = False


@dataclass
class SearchResult:
    """Outcome of a provider search call."""

    listings: list[dict] = field(default_factory=list)
    provider_name: str = ""
    errors: list[str] = field(default_factory=list)
    total_available: int | None = None
