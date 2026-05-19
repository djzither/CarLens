"""Multi-provider listing search aggregation."""

from __future__ import annotations

from src.listings.providers.base import ListingProvider
from src.listings.providers.schema import validate_provider_listing_record
from src.listings.providers.types import SearchFilters, SearchResult

AGGREGATED_PROVIDER_NAME = "aggregated"


class ListingSearchService:
    """Search across multiple listing providers and merge results."""

    def __init__(self, providers: list[ListingProvider]) -> None:
        self._providers = list(providers)

    @property
    def providers(self) -> list[ListingProvider]:
        return list(self._providers)

    def search(self, filters: SearchFilters) -> SearchResult:
        """Run provider searches and return a combined SearchResult."""
        combined_listings: list[dict] = []
        warnings: list[str] = []
        errors: list[str] = []
        total_available = 0
        seen_ids: set[tuple[str, str]] = set()

        for provider in self._providers:
            provider_name = provider.name or provider.__class__.__name__
            try:
                result = provider.search(filters)
            except Exception as exc:  # noqa: BLE001 — isolate provider failures
                errors.append(f"{provider_name}: {exc}")
                continue

            if result.errors:
                for message in result.errors:
                    errors.append(f"{provider_name}: {message}")

            for message in result.provider_warnings:
                warnings.append(f"{provider_name}: {message}")

            if result.total_available is not None:
                total_available += result.total_available

            for record in result.listings:
                valid, validation_errors = validate_provider_listing_record(record)
                if not valid:
                    entry_id = record.get("id", "unknown")
                    detail = ", ".join(validation_errors)
                    warnings.append(f"{provider_name}: {entry_id}: invalid record — {detail}")
                    continue

                provenance_key = (
                    str(record.get("provider_name", provider_name)),
                    str(record.get("provider_listing_id", "")),
                )
                if provenance_key in seen_ids:
                    continue
                seen_ids.add(provenance_key)

                combined_listings.append(record)

        return SearchResult(
            listings=combined_listings,
            provider_name=AGGREGATED_PROVIDER_NAME,
            provider_warnings=warnings,
            errors=errors,
            total_available=total_available or None,
        )
