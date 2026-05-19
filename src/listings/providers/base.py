"""Listing provider abstraction for external inventory APIs."""

from __future__ import annotations

from typing import Any, Protocol, TypedDict, runtime_checkable


class ListingSearchQuery(TypedDict, total=False):
    """Optional filters passed to :meth:`ListingProvider.search_listings`."""

    make: str
    model: str
    min_year: int
    max_year: int
    max_price: float
    max_mileage: int


@runtime_checkable
class ListingProvider(Protocol):
    """Search vehicle listings from an external or mocked inventory source."""

    def search_listings(
        self,
        query: ListingSearchQuery | None = None,
    ) -> list[dict[str, Any]]:
        """Return listing records matching optional filters.

        Each record is a dict. Mock/sample providers use the CarLens sample shape:
        ``id``, ``listing`` (raw vehicle fields), and optional ``display_name``.
        """
        ...
