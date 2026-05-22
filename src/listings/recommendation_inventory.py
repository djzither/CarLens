"""Recommendation-driven inventory retrieval across listing providers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.listings.listing_ranker import rank_listings_for_recommendations
from src.listings.providers.schema import validate_provider_listing_record
from src.listings.providers.search_service import AGGREGATED_PROVIDER_NAME
from src.listings.providers.types import SearchFilters, SearchResult
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

DEFAULT_TOP_MODEL_COUNT = 3
FALLBACK_MIN_LISTINGS = 10
MAX_TOP_MODEL_COUNT = 5
MAX_PROVIDER_QUERIES_WARN = 10
EARLY_STOP_LISTING_COUNT = 20

RETRIEVAL_SOURCE_RECOMMENDATION = "recommendation"
RETRIEVAL_SOURCE_EXPANDED = "expanded"
RETRIEVAL_SOURCE_CONSTRAINED_FALLBACK = "constrained_fallback"
RETRIEVAL_SOURCE_BUDGET_FALLBACK = "budget_fallback"

CONSTRAINED_FALLBACK_YEAR_PADDING = 2
CONSTRAINED_FALLBACK_MILEAGE_FACTOR = 1.10
CONSTRAINED_FALLBACK_PRICE_FACTOR = 1.05


@dataclass
class RetrievalMetrics:
    """Efficiency metrics for a single inventory retrieval run."""

    api_calls_per_provider: dict[str, int] = field(default_factory=dict)
    query_execution_ms: list[float] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    raw_retrieved: int = 0
    final_ranked: int = 0
    provider_errors: int = 0
    provider_query_count: int = 0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total

    @property
    def retrieval_efficiency(self) -> float:
        if self.raw_retrieved == 0:
            return 0.0
        return self.final_ranked / self.raw_retrieved

    @property
    def provider_error_rate(self) -> float:
        total_calls = sum(self.api_calls_per_provider.values())
        if total_calls == 0:
            return 0.0
        return self.provider_errors / total_calls

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_calls_per_provider": dict(self.api_calls_per_provider),
            "query_execution_ms": list(self.query_execution_ms),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": self.cache_hit_rate,
            "raw_retrieved": self.raw_retrieved,
            "final_ranked": self.final_ranked,
            "retrieval_efficiency": self.retrieval_efficiency,
            "provider_errors": self.provider_errors,
            "provider_error_rate": self.provider_error_rate,
            "provider_query_count": self.provider_query_count,
        }


@dataclass
class InventorySearchDiagnostics:
    """
    Diagnostics for a recommendation-driven inventory pull.

    Fallback flags (``fallback_triggered``, ``constrained_fallback_triggered``,
    ``expanded_fallback_triggered``) mean a fallback query was **attempted**,
    not that it added listings. Use ``fallback_results_added`` for net new
    listings after a fallback attempt.
    """

    recommended_models: list[dict[str, str]] = field(default_factory=list)
    selected_model: str | None = None
    selected_make: str | None = None
    selected_model_name: str | None = None
    constrained_fallback_triggered: bool = False
    fallback_broadening_applied: dict[str, Any] | None = None
    initial_result_count: int = 0
    fallback_result_count: int = 0
    fallback_results_added: int | None = None
    final_result_count: int = 0
    provider_query_params: list[dict[str, Any]] = field(default_factory=list)
    provider_searches: list[dict[str, Any]] = field(default_factory=list)
    listings_per_query: list[dict[str, Any]] = field(default_factory=list)
    fallback_triggered: bool = False
    fallback_search: dict[str, Any] | None = None
    expanded_fallback_triggered: bool = False
    aggregator_duplicates_removed: int = 0
    duplicates_removed: int = 0
    weak_fit_count: int = 0
    listing_count: int = 0
    early_stop_triggered: bool = False
    models_skipped_due_to_enough_results: int = 0
    top_model_count_capped: bool = False
    fallback_raw_count: int | None = None
    fallback_filtered_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    metrics: RetrievalMetrics = field(default_factory=RetrievalMetrics)

    def is_single_model_retrieval(self) -> bool:
        """True when retrieval targeted one selected make/model (not multi-model batch)."""
        return self.selected_model is not None and len(self.recommended_models) == 1

    def as_dict(self) -> dict[str, Any]:
        provider_params = self.provider_query_params or self.provider_searches
        return {
            "recommended_models": self.recommended_models,
            "selected_model": self.selected_model,
            "selected_make": self.selected_make,
            "selected_model_name": self.selected_model_name,
            "constrained_fallback_triggered": self.constrained_fallback_triggered,
            "fallback_broadening_applied": self.fallback_broadening_applied,
            "initial_result_count": self.initial_result_count,
            "fallback_result_count": self.fallback_result_count,
            "fallback_results_added": self.fallback_results_added,
            "final_result_count": self.final_result_count,
            "provider_query_params": provider_params,
            "provider_searches": self.provider_searches,
            "provider_queries": provider_params,
            "listings_per_query": self.listings_per_query,
            "fallback_triggered": self.fallback_triggered,
            "fallback_raw_count": self.fallback_raw_count,
            "fallback_filtered_count": self.fallback_filtered_count,
            "fallback_search": self.fallback_search,
            "expanded_fallback_triggered": self.expanded_fallback_triggered,
            "aggregator_duplicates_removed": self.aggregator_duplicates_removed,
            "duplicates_removed": self.duplicates_removed,
            "weak_fit_count": self.weak_fit_count,
            "listing_count": self.listing_count,
            "early_stop_triggered": self.early_stop_triggered,
            "models_skipped_due_to_enough_results": (
                self.models_skipped_due_to_enough_results
            ),
            "top_model_count_capped": self.top_model_count_capped,
            "warnings": list(self.warnings),
            "metrics": self.metrics.as_dict(),
            "api_calls": dict(self.metrics.api_calls_per_provider),
            "cache_hits": self.metrics.cache_hits,
            "retrieval_efficiency": self.metrics.retrieval_efficiency,
        }


def format_recommended_models(
    recommendations: list[dict[str, Any]],
    *,
    top_model_count: int = DEFAULT_TOP_MODEL_COUNT,
) -> list[dict[str, str]]:
    """Top recommended make/model pairs for the initial retrieval batch."""
    effective_top, _ = cap_top_model_count(top_model_count)
    return [
        {"make": item["make"], "model": item["model"]}
        for item in recommendations[:effective_top]
    ]


def _query_label_from_summary(summary: dict[str, Any]) -> str:
    make = summary.get("make")
    model = summary.get("model")
    if make and model:
        return f"{make} {model}"
    if summary.get("retrieval_source") == RETRIEVAL_SOURCE_BUDGET_FALLBACK:
        return "budget_fallback"
    return "budget"


def format_listings_per_query_lines(
    listings_per_query: list[dict[str, Any]],
    *,
    pending: bool = False,
) -> list[str]:
    """Format per-query listing counts for CLI diagnostics."""
    lines = ["Listings returned per query:"]
    if pending:
        lines.append("  (pending)")
        return lines
    if not listings_per_query:
        lines.append("  (none)")
        return lines
    for row in listings_per_query:
        label = _query_label_from_summary(row)
        lines.append(f"  - {label}: {row.get('count', 0)}")
    return lines


def format_pre_retrieval_diagnostics(
    *,
    provider_name: str,
    buyer: dict[str, Any],
    recommendations: list[dict[str, Any]],
    top_model_count: int = DEFAULT_TOP_MODEL_COUNT,
    extra_queries: list[dict[str, Any]] | None = None,
) -> str:
    """Diagnostics printed before any live provider API calls."""
    lines = ["Recommended models:"]
    for model in format_recommended_models(
        recommendations,
        top_model_count=top_model_count,
    ):
        lines.append(f"  - {model['make']} {model['model']}")
    lines.append("Provider queries:")
    for query in planned_model_queries(
        buyer,
        recommendations,
        top_model_count=top_model_count,
    ):
        lines.append(f"  {format_provider_query_line(provider_name, query)}")
    for query in extra_queries or []:
        lines.append(f"  {format_provider_query_line(provider_name, query)}")
    lines.extend(format_listings_per_query_lines([], pending=True))
    lines.extend(
        [
            f"Planned model queries: {len(format_recommended_models(recommendations, top_model_count=top_model_count))}",
            "Provider queries executed: (pending)",
            "early_stopped: no",
            "models_skipped_due_to_enough_results: 0",
            "Fallback triggered: no",
            "Unmatched model count: 0",
        ]
    )
    return "\n".join(lines)


def format_post_retrieval_diagnostics(
    diagnostics: InventorySearchDiagnostics,
    *,
    unmatched_model_count: int,
) -> str:
    """Per-query counts and fallback/unmatched status after retrieval."""
    lines = format_listings_per_query_lines(diagnostics.listings_per_query)
    lines.append(
        f"Fallback triggered: {'yes' if diagnostics.fallback_triggered else 'no'}"
    )
    lines.append(f"Unmatched model count: {unmatched_model_count}")
    if diagnostics.selected_model:
        lines.append(f"selected_model: {diagnostics.selected_model}")
    lines.extend(format_retrieval_plan_lines(diagnostics))
    return "\n".join(lines)


def format_retrieval_plan_lines(diagnostics: InventorySearchDiagnostics) -> list[str]:
    """Planned vs executed model queries and early-stop summary."""
    planned = len(diagnostics.recommended_models)
    executed = len(diagnostics.provider_searches)
    return [
        f"Planned model queries: {planned}",
        f"Provider queries executed: {executed}",
        f"early_stopped: {'yes' if diagnostics.early_stop_triggered else 'no'}",
        (
            "models_skipped_due_to_enough_results: "
            f"{diagnostics.models_skipped_due_to_enough_results}"
        ),
    ]


def format_diagnostics_report(diagnostics: InventorySearchDiagnostics) -> str:
    """Human-readable diagnostics block for CLI or logs."""
    metrics = diagnostics.metrics
    api_calls = ", ".join(
        f"{name}={count}" for name, count in sorted(metrics.api_calls_per_provider.items())
    )
    if not api_calls:
        api_calls = "none"

    lines = [
        f"Recommended models: {diagnostics.recommended_models}",
        *format_retrieval_plan_lines(diagnostics),
        *format_listings_per_query_lines(diagnostics.listings_per_query),
        f"Fallback triggered: {'yes' if diagnostics.fallback_triggered else 'no'}",
    ]
    if diagnostics.fallback_triggered:
        lines.append(
            f"Fallback listings: raw={diagnostics.fallback_raw_count} "
            f"filtered={diagnostics.fallback_filtered_count}"
        )
    lines.extend([
        f"API calls: {api_calls}",
        f"Cache hits: {metrics.cache_hits} "
        f"(hit rate {metrics.cache_hit_rate:.0%})",
        f"Duplicates removed: {diagnostics.duplicates_removed}",
        f"Retrieval efficiency: {metrics.retrieval_efficiency:.2f}",
    ])
    if diagnostics.warnings:
        lines.append(f"Warnings: {'; '.join(diagnostics.warnings)}")
    return "\n".join(lines)


def cap_top_model_count(requested: int) -> tuple[int, bool]:
    """Return capped model count and whether the request was reduced."""
    capped = max(1, min(requested, MAX_TOP_MODEL_COUNT))
    return capped, capped < requested


def _find_buyer(profiles: list[dict[str, Any]], buyer_profile_id: str) -> dict[str, Any]:
    for profile in profiles:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def recommended_model_keys(
    recommendations: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """Case-insensitive make/model pairs for all recommended vehicles."""
    return {
        (str(item["make"]).casefold(), str(item["model"]).casefold())
        for item in recommendations
    }


def _listing_make_model_key(record: dict[str, Any]) -> tuple[str, str] | None:
    listing = record.get("listing")
    if not isinstance(listing, dict):
        return None
    make = listing.get("make")
    model = listing.get("model")
    if make is None or model is None:
        return None
    return str(make).casefold(), str(model).casefold()


def filter_fallback_to_recommended_models(
    fallback_result: SearchResult,
    recommended_models: set[tuple[str, str]],
) -> SearchResult:
    """Keep only budget-fallback listings that match a recommended make/model."""
    filtered_listings = [
        record
        for record in fallback_result.listings
        if (key := _listing_make_model_key(record)) is not None and key in recommended_models
    ]
    return SearchResult(
        listings=filtered_listings,
        provider_name=fallback_result.provider_name,
        provider_warnings=fallback_result.provider_warnings,
        errors=fallback_result.errors,
        total_available=fallback_result.total_available,
    )


def buyer_budget_filters(buyer: dict[str, Any]) -> SearchFilters:
    """Budget and mileage constraints without make/model narrowing."""
    budget = buyer.get("budget_type") or {}
    max_price = budget.get("max_amount")
    max_mileage = buyer.get("max_mileage")
    return SearchFilters(
        max_price=int(max_price) if max_price is not None else None,
        max_mileage=int(max_mileage) if max_mileage is not None else None,
    )


def filters_for_recommendation(
    recommendation: dict[str, Any],
    buyer: dict[str, Any],
) -> SearchFilters:
    """Build provider query filters for one recommended make/model."""
    budget = buyer.get("budget_type") or {}
    max_price = budget.get("max_amount")
    max_mileage = buyer.get("max_mileage")
    year_range = recommendation.get("selected_year_range") or {}

    return SearchFilters(
        make=recommendation["make"],
        model=recommendation["model"],
        min_year=year_range.get("start_year"),
        max_year=year_range.get("end_year"),
        max_price=int(max_price) if max_price is not None else None,
        max_mileage=int(max_mileage) if max_mileage is not None else None,
    )


def filters_for_recommendation_widened_year(
    recommendation: dict[str, Any],
    buyer: dict[str, Any],
) -> SearchFilters:
    """Same make/model and budget as recommendation search, without year narrowing."""
    budget = buyer.get("budget_type") or {}
    max_price = budget.get("max_amount")
    max_mileage = buyer.get("max_mileage")
    return SearchFilters(
        make=recommendation["make"],
        model=recommendation["model"],
        max_price=int(max_price) if max_price is not None else None,
        max_mileage=int(max_mileage) if max_mileage is not None else None,
    )


def find_recommendation_by_make_model(
    recommendations: list[dict[str, Any]],
    make: str,
    model: str,
) -> dict[str, Any]:
    """Return the recommendation entry matching make/model (case-insensitive)."""
    needle = (make.strip().casefold(), model.strip().casefold())
    for item in recommendations:
        key = (str(item["make"]).strip().casefold(), str(item["model"]).strip().casefold())
        if key == needle:
            return item
    available = format_available_model_labels(recommendations)
    raise ValueError(
        f"make/model {make!r} {model!r} not found in recommendations. "
        f"Valid options: {available}"
    )


def recommendation_stub_for_make_model(make: str, model: str) -> dict[str, Any]:
    """Minimal recommendation payload when only make/model are known."""
    return {"make": make, "model": model, "selected_year_range": {}}


def filters_for_constrained_fallback(
    primary_filters: SearchFilters,
) -> SearchFilters:
    """Broaden year, mileage, and price while preserving make/model constraints."""
    min_year = primary_filters.min_year
    max_year = primary_filters.max_year
    if min_year is not None:
        min_year = max(0, int(min_year) - CONSTRAINED_FALLBACK_YEAR_PADDING)
    if max_year is not None:
        max_year = int(max_year) + CONSTRAINED_FALLBACK_YEAR_PADDING

    max_mileage = primary_filters.max_mileage
    if max_mileage is not None:
        max_mileage = int(max_mileage * CONSTRAINED_FALLBACK_MILEAGE_FACTOR)

    max_price = primary_filters.max_price
    if max_price is not None:
        max_price = int(max_price * CONSTRAINED_FALLBACK_PRICE_FACTOR)

    return SearchFilters(
        make=primary_filters.make,
        model=primary_filters.model,
        min_year=min_year,
        max_year=max_year,
        max_price=max_price,
        max_mileage=max_mileage,
        clean_title_only=primary_filters.clean_title_only,
    )


def describe_fallback_broadening(
    primary_filters: SearchFilters,
    fallback_filters: SearchFilters,
) -> dict[str, Any]:
    """Summarize constrained fallback parameter changes for diagnostics."""
    return {
        "year": {
            "min_year": {
                "from": primary_filters.min_year,
                "to": fallback_filters.min_year,
            },
            "max_year": {
                "from": primary_filters.max_year,
                "to": fallback_filters.max_year,
            },
        },
        "max_mileage": {
            "from": primary_filters.max_mileage,
            "to": fallback_filters.max_mileage,
        },
        "max_price": {
            "from": primary_filters.max_price,
            "to": fallback_filters.max_price,
        },
    }


def filter_search_result_to_make_model(
    result: SearchResult,
    make: str,
    model: str,
) -> SearchResult:
    """Drop provider listings that do not match the selected make/model."""
    target = (make.strip().casefold(), model.strip().casefold())
    filtered = [
        record
        for record in result.listings
        if (key := _listing_make_model_key(record)) is not None and key == target
    ]
    return SearchResult(
        listings=filtered,
        provider_name=result.provider_name,
        provider_warnings=result.provider_warnings,
        errors=result.errors,
        total_available=result.total_available,
    )


def format_available_model_labels(
    recommendations: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> str:
    """Comma-separated Make Model labels for CLI error hints."""
    labels = [
        f"{item['make']} {item['model']}"
        for item in recommendations[: max(limit, 1)]
    ]
    return ", ".join(labels)


def recommendation_model_label(recommendation: dict[str, Any]) -> str:
    return f"{recommendation['make']} {recommendation['model']}"


def resolve_selected_recommendation(
    recommendations: list[dict[str, Any]],
    *,
    selected_model: str | None = None,
    selected_index: int | None = None,
) -> dict[str, Any]:
    """Resolve one recommendation by 1-based index or \"Make Model\" label."""
    available = format_available_model_labels(recommendations)

    if selected_index is not None:
        if selected_index < 1 or selected_index > len(recommendations):
            raise ValueError(
                f"selected_index {selected_index} out of range (1-{len(recommendations)}). "
                f"Valid options: {available}"
            )
        return recommendations[selected_index - 1]

    if selected_model:
        needle = selected_model.strip().casefold()
        for item in recommendations:
            label = f"{item['make']} {item['model']}".casefold()
            if label == needle:
                return item
        raise ValueError(
            f"selected model {selected_model!r} not found in recommendations. "
            f"Valid options: {available}"
        )

    raise ValueError("provide selected_model or selected_index")


def format_provider_query_line(
    provider_name: str,
    query: SearchFilters | dict[str, Any],
) -> str:
    """Format one provider query for CLI output."""
    summary = (
        search_filters_summary(query)
        if isinstance(query, SearchFilters)
        else query
    )
    make = summary.get("make")
    model = summary.get("model")
    if make and model:
        label = f"{make} {model}"
    else:
        label = "budget"
    parts = [f"- {provider_name}", label]
    if summary.get("max_price") is not None:
        parts.append(f"max_price={summary['max_price']}")
    if summary.get("max_mileage") is not None:
        parts.append(f"max_mileage={summary['max_mileage']}")
    return " ".join(parts)


def planned_model_queries(
    buyer: dict[str, Any],
    recommendations: list[dict[str, Any]],
    *,
    top_model_count: int = DEFAULT_TOP_MODEL_COUNT,
) -> list[dict[str, Any]]:
    """Return filter summaries for the initial recommended-model query batch."""
    effective_top, _ = cap_top_model_count(top_model_count)
    return [
        search_filters_summary(filters_for_recommendation(recommendation, buyer))
        for recommendation in recommendations[:effective_top]
    ]


def search_filters_summary(filters: SearchFilters) -> dict[str, Any]:
    """Serialize SearchFilters for diagnostics."""
    return {
        "make": filters.make,
        "model": filters.model,
        "min_year": filters.min_year,
        "max_year": filters.max_year,
        "max_price": filters.max_price,
        "max_mileage": filters.max_mileage,
        "clean_title_only": filters.clean_title_only,
    }


def _filters_cache_key(filters: SearchFilters) -> tuple[Any, ...]:
    return (
        filters.make,
        filters.model,
        filters.min_year,
        filters.max_year,
        filters.max_price,
        filters.max_mileage,
        filters.clean_title_only,
    )


def tag_search_listings(result: SearchResult, retrieval_source: str) -> SearchResult:
    """Attach retrieval_source to each listing record in a search result."""
    tagged = []
    for record in result.listings:
        updated = dict(record)
        updated["retrieval_source"] = retrieval_source
        tagged.append(updated)
    return SearchResult(
        listings=tagged,
        provider_name=result.provider_name,
        provider_warnings=result.provider_warnings,
        errors=result.errors,
        total_available=result.total_available,
    )


class _RetrievalSession:
    """Instrumented, cached wrapper around ListingSearchService.search."""

    def __init__(self, search_service: Any) -> None:
        self._search_service = search_service
        self._cache: dict[tuple[Any, ...], SearchResult] = {}
        self.metrics = RetrievalMetrics()

    @property
    def providers(self) -> list[Any]:
        return list(self._search_service.providers)

    def search(self, filters: SearchFilters, *, retrieval_source: str) -> SearchResult:
        """Run a cached provider search and record efficiency metrics."""
        cache_key = _filters_cache_key(filters)
        started = time.perf_counter()

        if cache_key in self._cache:
            self.metrics.cache_hits += 1
            result = self._cache[cache_key]
        else:
            self.metrics.cache_misses += 1
            result = self._search_service.search(filters)
            self._cache[cache_key] = result

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.metrics.query_execution_ms.append(elapsed_ms)
        self.metrics.provider_query_count += 1
        self.metrics.raw_retrieved += len(result.listings)

        for provider in self.providers:
            provider_name = provider.name or provider.__class__.__name__
            self.metrics.api_calls_per_provider[provider_name] = (
                self.metrics.api_calls_per_provider.get(provider_name, 0) + 1
            )

        self.metrics.provider_errors += len(result.errors)

        return tag_search_listings(result, retrieval_source)


def merge_search_results(results: list[SearchResult]) -> tuple[SearchResult, int]:
    """Merge provider search results and dedupe by provider provenance."""
    combined_listings: list[dict] = []
    warnings: list[str] = []
    errors: list[str] = []
    total_available = 0
    seen_ids: set[tuple[str, str]] = set()
    duplicates_removed = 0

    for result in results:
        if result.errors:
            errors.extend(result.errors)
        warnings.extend(result.provider_warnings)
        if result.total_available is not None:
            total_available += result.total_available

        for record in result.listings:
            valid, validation_errors = validate_provider_listing_record(record)
            if not valid:
                entry_id = record.get("id", "unknown")
                detail = ", ".join(validation_errors)
                provider_name = str(record.get("provider_name", "unknown"))
                warnings.append(
                    f"{provider_name}: {entry_id}: invalid record — {detail}"
                )
                continue

            provenance_key = (
                str(record.get("provider_name", "")),
                str(record.get("provider_listing_id", "")),
            )
            if provenance_key in seen_ids:
                duplicates_removed += 1
                continue
            seen_ids.add(provenance_key)
            combined_listings.append(record)

    return (
        SearchResult(
            listings=combined_listings,
            provider_name=AGGREGATED_PROVIDER_NAME,
            provider_warnings=warnings,
            errors=errors,
            total_available=total_available or None,
        ),
        duplicates_removed,
    )


def provider_records_to_scenarios(
    records: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """Convert provider listing records into ranker scenarios."""
    return [(str(record["id"]), record["listing"]) for record in records]


def count_weak_fits(ranked: dict[str, Any]) -> int:
    """Count listings labeled Weak fit across ranked groups and unmatched."""
    weak = 0
    for group in ranked.get("groups") or []:
        for entry in group.get("listings") or []:
            if entry.get("fit", {}).get("fit_label") == "Weak fit":
                weak += 1
    for entry in ranked.get("unmatched_listings") or []:
        if entry.get("fit", {}).get("fit_label") == "Weak fit":
            weak += 1
    return weak


def count_ranked_listings(ranked: dict[str, Any]) -> int:
    """Count listings present in ranked groups and unmatched buckets."""
    total = 0
    for group in ranked.get("groups") or []:
        total += len(group.get("listings") or [])
    total += len(ranked.get("unmatched_listings") or [])
    return total


def _run_model_query(
    session: _RetrievalSession,
    diagnostics: InventorySearchDiagnostics,
    *,
    recommendation: dict[str, Any],
    buyer: dict[str, Any],
    retrieval_source: str,
    per_query_results: list[SearchResult],
    filters: SearchFilters | None = None,
) -> SearchResult:
    if filters is None:
        filters = filters_for_recommendation(recommendation, buyer)
    query_summary = {
        **search_filters_summary(filters),
        "retrieval_source": retrieval_source,
    }
    diagnostics.provider_searches.append(query_summary)
    result = session.search(filters, retrieval_source=retrieval_source)
    per_query_results.append(result)
    diagnostics.listings_per_query.append(
        {**query_summary, "count": len(result.listings)},
    )
    return result


def retrieve_inventory_for_buyer(
    buyer_profile_id: str,
    search_service: Any,
    *,
    buyer: dict[str, Any] | None = None,
    top_model_count: int = DEFAULT_TOP_MODEL_COUNT,
    fallback_min_listings: int = FALLBACK_MIN_LISTINGS,
) -> dict[str, Any]:
    """
    Pull inventory using top recommended models, then rank with existing pipeline.

    Applies guardrails (model cap, early stop, progressive fallback) and records
    retrieval efficiency metrics without changing provider or ranking logic.

    Raises:
        ValueError: Unknown ``buyer_profile_id`` (when ``buyer`` is omitted), or no
            recommendations for the profile.

    Provider errors:
        Provider failures are collected on ``search_result.errors``; they do not
        raise from this function. Callers should surface ``errors`` and
        ``provider_warnings`` to the user when present.

    Caller behavior:
        Use ``diagnostics`` for query/fallback status. ``fallback_triggered`` means
        a budget fallback was attempted, not that listings were added; check
        ``fallback_results_added`` when set.
    """
    if buyer is None:
        buyer_data = load_buyer_profiles()
        buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)

    recommendation_result = recommend(buyer_profile_id, buyer=buyer)
    recommendations = recommendation_result["recommendations"]
    if not recommendations:
        raise ValueError(
            f"no vehicle recommendations available for profile {buyer_profile_id!r}"
        )

    effective_top, was_capped = cap_top_model_count(top_model_count)
    session = _RetrievalSession(search_service)
    diagnostics = InventorySearchDiagnostics(
        metrics=session.metrics,
        top_model_count_capped=was_capped,
    )
    if was_capped:
        diagnostics.warnings.append(
            f"top_model_count capped at {MAX_TOP_MODEL_COUNT} (requested {top_model_count})"
        )

    initial_recommendations = recommendations[:effective_top]
    diagnostics.recommended_models = [
        {"make": item["make"], "model": item["model"]}
        for item in initial_recommendations
    ]

    per_query_results: list[SearchResult] = []
    collected_count = 0
    models_queried = 0

    for recommendation in initial_recommendations:
        if collected_count >= EARLY_STOP_LISTING_COUNT:
            diagnostics.early_stop_triggered = True
            diagnostics.models_skipped_due_to_enough_results += (
                len(initial_recommendations) - models_queried
            )
            break
        _run_model_query(
            session,
            diagnostics,
            recommendation=recommendation,
            buyer=buyer,
            retrieval_source=RETRIEVAL_SOURCE_RECOMMENDATION,
            per_query_results=per_query_results,
        )
        models_queried += 1
        collected_count = sum(len(result.listings) for result in per_query_results)

    merged, aggregator_dupes = merge_search_results(per_query_results)
    diagnostics.aggregator_duplicates_removed = aggregator_dupes
    collected_count = len(merged.listings)

    if (
        collected_count < fallback_min_listings
        and collected_count < EARLY_STOP_LISTING_COUNT
    ):
        expand_start = effective_top
        expand_end = min(len(recommendations), MAX_TOP_MODEL_COUNT)
        expand_candidates = recommendations[expand_start:expand_end]
        if expand_candidates:
            diagnostics.expanded_fallback_triggered = True
            expand_models_queried = 0
            for recommendation in expand_candidates:
                if collected_count >= fallback_min_listings:
                    diagnostics.models_skipped_due_to_enough_results += (
                        len(expand_candidates) - expand_models_queried
                    )
                    break
                if collected_count >= EARLY_STOP_LISTING_COUNT:
                    diagnostics.early_stop_triggered = True
                    diagnostics.models_skipped_due_to_enough_results += (
                        len(expand_candidates) - expand_models_queried
                    )
                    break
                _run_model_query(
                    session,
                    diagnostics,
                    recommendation=recommendation,
                    buyer=buyer,
                    retrieval_source=RETRIEVAL_SOURCE_EXPANDED,
                    per_query_results=per_query_results,
                )
                expand_models_queried += 1
                merged, aggregator_dupes = merge_search_results(per_query_results)
                diagnostics.aggregator_duplicates_removed = aggregator_dupes
                collected_count = len(merged.listings)

    if collected_count < fallback_min_listings:
        before_fallback_count = collected_count
        fallback_filters = buyer_budget_filters(buyer)
        all_recommended_models = recommended_model_keys(recommendations)
        diagnostics.fallback_triggered = True
        diagnostics.fallback_search = search_filters_summary(fallback_filters)
        query_summary = {
            **diagnostics.fallback_search,
            "retrieval_source": RETRIEVAL_SOURCE_BUDGET_FALLBACK,
        }
        diagnostics.provider_searches.append(query_summary)
        fallback_result = session.search(
            fallback_filters,
            retrieval_source=RETRIEVAL_SOURCE_BUDGET_FALLBACK,
        )
        diagnostics.fallback_raw_count = len(fallback_result.listings)
        fallback_result = filter_fallback_to_recommended_models(
            fallback_result,
            all_recommended_models,
        )
        diagnostics.fallback_filtered_count = len(fallback_result.listings)
        per_query_results.append(fallback_result)
        diagnostics.listings_per_query.append(
            {
                **query_summary,
                "count": diagnostics.fallback_filtered_count,
                "fallback": True,
                "fallback_raw_count": diagnostics.fallback_raw_count,
                "fallback_filtered_count": diagnostics.fallback_filtered_count,
            }
        )
        merged, aggregator_dupes = merge_search_results(per_query_results)
        diagnostics.aggregator_duplicates_removed = aggregator_dupes
        collected_count = len(merged.listings)
        diagnostics.fallback_results_added = max(
            0,
            collected_count - before_fallback_count,
        )

    if diagnostics.metrics.provider_query_count > MAX_PROVIDER_QUERIES_WARN:
        diagnostics.warnings.append(
            f"provider query count {diagnostics.metrics.provider_query_count} "
            f"exceeds recommended maximum of {MAX_PROVIDER_QUERIES_WARN}"
        )

    scenarios = provider_records_to_scenarios(merged.listings)
    ranked = rank_listings_for_recommendations(
        scenarios,
        recommendations,
        buyer,
    )
    pipeline = ranked.get("pipeline") or {}
    diagnostics.duplicates_removed = max(
        0,
        int(pipeline.get("raw_count", len(scenarios)))
        - int(pipeline.get("deduped_count", len(scenarios))),
    )
    diagnostics.weak_fit_count = count_weak_fits(ranked)
    diagnostics.listing_count = len(merged.listings)
    diagnostics.metrics.final_ranked = count_ranked_listings(ranked)

    return {
        "buyer_profile_id": buyer_profile_id,
        "buyer": buyer,
        "recommendation_result": recommendation_result,
        "search_result": merged,
        "ranked": ranked,
        "diagnostics": diagnostics,
    }


def retrieve_inventory_for_selected_model(
    buyer_profile_id: str,
    make: str,
    model: str,
    search_service: Any,
    *,
    buyer: dict[str, Any] | None = None,
    fallback_strategy: str = "constrained",
    fallback_min_listings: int = FALLBACK_MIN_LISTINGS,
    recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Primary single-model guided retrieval: one make/model, constrained fallback only.

    Initial query preserves make/model, budget, mileage, and recommendation year range.
    When results are insufficient, optionally broadens year, mileage, and price ceiling
    for the same make/model — never other models or budget-only retrieval.

    Raises:
        ValueError: Unsupported ``fallback_strategy`` (only ``'constrained'``).
        ValueError: Unknown ``buyer_profile_id`` when ``buyer`` is omitted.
        ValueError: No recommendations for the profile.

    Provider errors:
        Provider failures are collected on ``search_result.errors``; they do not
        raise from this function. Inspect ``search_result.errors`` and
        ``search_result.provider_warnings`` before presenting listings.

    Caller behavior:
        Read ``ranked`` with ``single_model_mode`` set. ``unmatched_listings`` is
        always empty in that mode. Use ``diagnostics.is_single_model_retrieval()``
        and ``diagnostics.fallback_results_added`` (after constrained fallback) to
        explain whether a fallback attempt added inventory.
        ``constrained_fallback_triggered`` means the broader same-model query ran,
        not that results improved.
    """
    if fallback_strategy != "constrained":
        raise ValueError(
            f"unsupported fallback_strategy {fallback_strategy!r}; use 'constrained'"
        )

    if buyer is None:
        buyer_data = load_buyer_profiles()
        buyer = _find_buyer(buyer_data["profiles"], buyer_profile_id)

    recommendation_result = recommend(buyer_profile_id, buyer=buyer)
    all_recommendations = recommendation_result["recommendations"]
    if not all_recommendations:
        raise ValueError(
            f"no vehicle recommendations available for profile {buyer_profile_id!r}"
        )

    if recommendation is None:
        try:
            recommendation = find_recommendation_by_make_model(
                all_recommendations,
                make,
                model,
            )
        except ValueError:
            recommendation = recommendation_stub_for_make_model(make, model)

    session = _RetrievalSession(search_service)
    diagnostics = InventorySearchDiagnostics(metrics=session.metrics)
    diagnostics.selected_make = make
    diagnostics.selected_model_name = model
    diagnostics.selected_model = recommendation_model_label(recommendation)
    diagnostics.recommended_models = [{"make": make, "model": model}]

    per_query_results: list[SearchResult] = []
    primary_filters = filters_for_recommendation(recommendation, buyer)
    _run_model_query(
        session,
        diagnostics,
        recommendation=recommendation,
        buyer=buyer,
        retrieval_source=RETRIEVAL_SOURCE_RECOMMENDATION,
        per_query_results=per_query_results,
        filters=primary_filters,
    )

    merged, aggregator_dupes = merge_search_results(per_query_results)
    merged = filter_search_result_to_make_model(merged, make, model)
    diagnostics.aggregator_duplicates_removed = aggregator_dupes
    diagnostics.initial_result_count = len(merged.listings)
    collected_count = diagnostics.initial_result_count

    if collected_count < fallback_min_listings:
        diagnostics.constrained_fallback_triggered = True
        diagnostics.expanded_fallback_triggered = True
        fallback_filters = filters_for_constrained_fallback(primary_filters)
        diagnostics.fallback_broadening_applied = describe_fallback_broadening(
            primary_filters,
            fallback_filters,
        )
        query_summary = {
            **search_filters_summary(fallback_filters),
            "retrieval_source": RETRIEVAL_SOURCE_CONSTRAINED_FALLBACK,
        }
        diagnostics.provider_searches.append(query_summary)
        diagnostics.provider_query_params.append(query_summary)
        fallback_result = session.search(
            fallback_filters,
            retrieval_source=RETRIEVAL_SOURCE_CONSTRAINED_FALLBACK,
        )
        fallback_result = filter_search_result_to_make_model(fallback_result, make, model)
        per_query_results.append(fallback_result)
        diagnostics.fallback_result_count = len(fallback_result.listings)
        diagnostics.listings_per_query.append(
            {**query_summary, "count": diagnostics.fallback_result_count},
        )
        merged, aggregator_dupes = merge_search_results(per_query_results)
        merged = filter_search_result_to_make_model(merged, make, model)
        diagnostics.aggregator_duplicates_removed = aggregator_dupes
        collected_count = len(merged.listings)
        diagnostics.fallback_results_added = max(
            0,
            collected_count - diagnostics.initial_result_count,
        )

    diagnostics.provider_query_params = list(diagnostics.provider_searches)
    diagnostics.final_result_count = collected_count
    diagnostics.listing_count = collected_count

    scenarios = provider_records_to_scenarios(merged.listings)
    ranked = rank_listings_for_recommendations(
        scenarios,
        [recommendation],
        buyer,
    )
    pipeline = ranked.get("pipeline") or {}
    diagnostics.duplicates_removed = max(
        0,
        int(pipeline.get("raw_count", len(scenarios)))
        - int(pipeline.get("deduped_count", len(scenarios))),
    )
    diagnostics.weak_fit_count = count_weak_fits(ranked)
    diagnostics.metrics.final_ranked = count_ranked_listings(ranked)

    return {
        "buyer_profile_id": buyer_profile_id,
        "buyer": buyer,
        "recommendation_result": recommendation_result,
        "selected_make": make,
        "selected_model": model,
        "selected_recommendation": recommendation,
        "search_result": merged,
        "ranked": ranked,
        "diagnostics": diagnostics,
    }
