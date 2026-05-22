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

    def __post_init__(self) -> None:
        make_set = self._field_populated(self.make)
        model_set = self._field_populated(self.model)
        if make_set != model_set:
            raise ValueError(
                "make and model must both be set or both be omitted; "
                f"got make={self.make!r}, model={self.model!r}"
            )

    @staticmethod
    def _field_populated(value: str | None) -> bool:
        return value is not None and str(value).strip() != ""


@dataclass
class SearchResult:
    """Outcome of a provider search call."""

    listings: list[dict] = field(default_factory=list)
    provider_name: str = ""
    provider_warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_available: int | None = None
