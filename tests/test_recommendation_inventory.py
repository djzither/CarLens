"""Tests for recommendation-driven inventory retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.listings.listing_ranker import rank_listings_for_recommendations
from src.listings.providers import (
    AutoDevProvider,
    ListingProvider,
    ListingSearchService,
    MockListingProvider,
    SearchFilters,
    SearchResult,
)
from src.listings.recommendation_inventory import (
    EARLY_STOP_LISTING_COUNT,
    FALLBACK_MIN_LISTINGS,
    MAX_TOP_MODEL_COUNT,
    RETRIEVAL_SOURCE_BUDGET_FALLBACK,
    RETRIEVAL_SOURCE_EXPANDED,
    RETRIEVAL_SOURCE_RECOMMENDATION,
    _RetrievalSession,
    cap_top_model_count,
    count_weak_fits,
    filters_for_recommendation,
    format_diagnostics_report,
    format_post_retrieval_diagnostics,
    format_pre_retrieval_diagnostics,
    format_provider_query_line,
    merge_search_results,
    provider_records_to_scenarios,
    recommended_model_keys,
    resolve_selected_recommendation,
    retrieve_inventory_for_buyer,
    retrieve_inventory_for_selected_model,
    tag_search_listings,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTO_DEV_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)
STUDENT_LISTINGS = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"


def _student_buyer() -> dict[str, Any]:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == "student":
            return profile
    raise AssertionError("student profile missing")


class _RecordingProvider(ListingProvider):
    name = "recording"

    def __init__(self, responses: dict[tuple[str | None, str | None], list[dict]] | None = None) -> None:
        self.calls: list[SearchFilters] = []
        self._responses = responses or {}

    def search(self, filters: SearchFilters) -> SearchResult:
        self.calls.append(filters)
        key = (filters.make, filters.model)
        listings = self._responses.get(key, [])
        return SearchResult(listings=listings, provider_name=self.name)

    def get_by_id(self, listing_id: str) -> dict | None:
        return None


def _provider_record(
    *,
    entry_id: str,
    make: str,
    model: str,
    provider_name: str = "recording",
) -> dict[str, Any]:
    listing = {
        "make": make,
        "model": model,
        "year": 2016,
        "mileage": 85000,
        "price": 10500,
        "clean_title": True,
        "source": provider_name,
        "listing_id": entry_id,
    }
    return {
        "id": entry_id,
        "provider_name": provider_name,
        "provider_listing_id": entry_id,
        "provider_raw_fields": list(listing.keys()),
        "listing": listing,
    }


def test_pre_retrieval_diagnostics_student_queries() -> None:
    buyer = _student_buyer()
    recommendations = recommend("student")["recommendations"]
    report = format_pre_retrieval_diagnostics(
        provider_name="auto.dev",
        buyer=buyer,
        recommendations=recommendations,
        top_model_count=3,
    )

    assert "Recommended models:" in report
    assert "  - Toyota Corolla" in report
    assert "  - Honda Civic" in report
    assert "  - Toyota Camry" in report
    assert (
        format_provider_query_line(
            "auto.dev",
            filters_for_recommendation(recommendations[0], buyer),
        )
        in report
    )
    assert "max_price=12000" in report
    assert "max_mileage=130000" in report
    assert "Listings returned per query:" in report
    assert "(pending)" in report
    assert "Fallback triggered: no" in report
    assert "early_stopped: no" in report
    assert "models_skipped_due_to_enough_results: 0" in report
    assert "Unmatched model count: 0" in report


def test_pre_retrieval_diagnostics_includes_mazda3_at_four_models() -> None:
    buyer = _student_buyer()
    recommendations = recommend("student")["recommendations"]
    report = format_pre_retrieval_diagnostics(
        provider_name="auto.dev",
        buyer=buyer,
        recommendations=recommendations,
        top_model_count=4,
    )

    assert "  - Mazda Mazda3" in report


def test_post_retrieval_diagnostics_reports_fallback_and_counts() -> None:
    sparse = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [_provider_record(entry_id="c1", make="Toyota", model="Corolla")],
            (None, None): [
                _provider_record(entry_id=f"b{i}", make="Honda", model="Civic")
                for i in range(FALLBACK_MIN_LISTINGS)
            ],
        }
    )
    service = ListingSearchService([sparse])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
    )
    diagnostics = result["diagnostics"]
    unmatched = len(result["ranked"].get("unmatched_listings") or [])
    report = format_post_retrieval_diagnostics(
        diagnostics,
        unmatched_model_count=unmatched,
    )

    assert "Listings returned per query:" in report
    assert "Fallback triggered: yes" in report
    assert "budget_fallback" in report
    assert f"Unmatched model count: {unmatched}" in report


def test_resolve_selected_recommendation_by_index_and_label() -> None:
    recommendations = recommend("student")["recommendations"]
    by_index = resolve_selected_recommendation(recommendations, selected_index=1)
    by_label = resolve_selected_recommendation(
        recommendations,
        selected_model=f"{by_index['make']} {by_index['model']}",
    )
    assert by_index == by_label


def test_selected_model_inventory_keeps_make_model_on_fallback() -> None:
    recommendations = recommend("student")["recommendations"]
    selected = resolve_selected_recommendation(recommendations, selected_index=2)
    make = selected["make"]
    model = selected["model"]

    class _NarrowThenWideProvider(ListingProvider):
        name = "recording"

        def __init__(self) -> None:
            self.calls: list[SearchFilters] = []

        def search(self, filters: SearchFilters) -> SearchResult:
            self.calls.append(filters)
            assert filters.make == make
            assert filters.model == model
            if len(self.calls) == 1:
                return SearchResult(listings=[], provider_name=self.name)
            return SearchResult(
                listings=[
                    _provider_record(
                        entry_id="wide-1",
                        make=make,
                        model=model,
                    )
                ],
                provider_name=self.name,
            )

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    provider = _NarrowThenWideProvider()
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_selected_model(
        "student",
        make,
        model,
        service,
        buyer=_student_buyer(),
        fallback_min_listings=1,
    )
    diagnostics = result["diagnostics"]

    assert diagnostics.fallback_triggered is False
    assert diagnostics.constrained_fallback_triggered is True
    assert diagnostics.expanded_fallback_triggered is True
    assert len(provider.calls) == 2
    assert all(call.make == make for call in provider.calls)
    assert all(call.model == model for call in provider.calls)
    assert not any(call.make is None and call.model is None for call in provider.calls)
    assert result["ranked"].get("single_model_mode") is True
    assert len(result["ranked"].get("unmatched_listings") or []) == 0


def test_selected_model_inventory_does_not_use_budget_fallback() -> None:
    recommendations = recommend("student")["recommendations"]
    selected = resolve_selected_recommendation(recommendations, selected_index=1)
    make = selected["make"]
    model = selected["model"]
    crosstrek = _provider_record(entry_id="sub-1", make="Subaru", model="XV")
    corolla = _provider_record(entry_id="cor-1", make="Toyota", model="Corolla")

    class _BudgetTrapProvider(ListingProvider):
        name = "recording"

        def __init__(self) -> None:
            self.calls: list[SearchFilters] = []

        def search(self, filters: SearchFilters) -> SearchResult:
            self.calls.append(filters)
            if filters.make and filters.model:
                return SearchResult(listings=[], provider_name=self.name)
            return SearchResult(listings=[crosstrek, corolla], provider_name=self.name)

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    provider = _BudgetTrapProvider()
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_selected_model(
        "student",
        make,
        model,
        service,
        buyer=_student_buyer(),
        fallback_min_listings=5,
    )

    diagnostics = result["diagnostics"]
    assert len(provider.calls) == 2
    assert not any(call.make is None and call.model is None for call in provider.calls)
    assert len(result["search_result"].listings) == 0
    assert diagnostics.constrained_fallback_triggered is True
    assert diagnostics.fallback_triggered is False


def test_student_profile_creates_corolla_and_civic_searches() -> None:
    provider = _RecordingProvider()
    service = ListingSearchService([provider])

    retrieve_inventory_for_buyer("student", service, buyer=_student_buyer())

    model_queries = {(call.make, call.model) for call in provider.calls}
    assert ("Toyota", "Corolla") in model_queries
    assert ("Honda", "Civic") in model_queries
    assert all(call.max_price == 12000 for call in provider.calls)
    assert all(call.max_mileage == 130000 for call in provider.calls)


def test_fallback_triggers_when_model_searches_return_few_listings() -> None:
    sparse = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [_provider_record(entry_id="c1", make="Toyota", model="Corolla")],
            ("Honda", "Civic"): [_provider_record(entry_id="c2", make="Honda", model="Civic")],
            ("Toyota", "Camry"): [_provider_record(entry_id="c3", make="Toyota", model="Camry")],
            (None, None): [
                _provider_record(entry_id=f"b{i}", make="Toyota", model="Corolla")
                for i in range(FALLBACK_MIN_LISTINGS)
            ],
        }
    )
    service = ListingSearchService([sparse])

    result = retrieve_inventory_for_buyer("student", service, buyer=_student_buyer())

    diagnostics = result["diagnostics"].as_dict()
    assert diagnostics["fallback_triggered"] is True
    assert diagnostics["fallback_search"] == {
        "make": None,
        "model": None,
        "min_year": None,
        "max_year": None,
        "max_price": 12000,
        "max_mileage": 130000,
        "clean_title_only": False,
    }
    assert any(call.make is None and call.model is None for call in sparse.calls)
    assert len(result["search_result"].listings) >= FALLBACK_MIN_LISTINGS


def test_aggregate_still_combines_multiple_providers() -> None:
    corolla = _provider_record(entry_id="ad-1", make="Toyota", model="Corolla", provider_name="auto.dev")
    civic = _provider_record(entry_id="mc-1", make="Honda", model="Civic", provider_name="marketcheck")

    class _FixedProvider(ListingProvider):
        def __init__(self, name: str, listings: list[dict]) -> None:
            self.name = name
            self._listings = listings

        def search(self, filters: SearchFilters) -> SearchResult:
            matched = [
                record
                for record in self._listings
                if (
                    filters.make is None
                    or record["listing"]["make"].casefold() == filters.make.casefold()
                )
                and (
                    filters.model is None
                    or record["listing"]["model"].casefold() == filters.model.casefold()
                )
            ]
            return SearchResult(listings=matched, provider_name=self.name)

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    service = ListingSearchService(
        [
            _FixedProvider("auto.dev", [corolla]),
            _FixedProvider("marketcheck", [civic]),
        ]
    )

    result = retrieve_inventory_for_buyer("student", service, buyer=_student_buyer())
    provider_names = {record["provider_name"] for record in result["search_result"].listings}

    assert provider_names >= {"auto.dev", "marketcheck"}


def test_ranking_improves_vs_unfiltered_inventory() -> None:
    buyer = _student_buyer()
    recommendations = recommend("student")["recommendations"]
    service = ListingSearchService([MockListingProvider(STUDENT_LISTINGS)])

    targeted = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=buyer,
        top_model_count=3,
        fallback_min_listings=1,
    )
    broad = rank_listings_for_recommendations(
        [
            (record["id"], record["listing"])
            for record in service.search(SearchFilters()).listings
        ],
        recommendations,
        buyer,
    )

    assert targeted["diagnostics"].weak_fit_count < count_weak_fits(broad)
    assert len(targeted["search_result"].listings) < len(
        service.search(SearchFilters()).listings
    )
    assert not targeted["diagnostics"].fallback_triggered
    assert len(targeted["ranked"].get("unmatched_listings") or []) == 0


def test_merge_search_results_dedupes_provider_provenance() -> None:
    record = _provider_record(entry_id="dup", make="Toyota", model="Corolla")
    copy = dict(record)
    copy["id"] = "dup-copy"
    first = SearchResult(listings=[record], provider_name="a")
    second = SearchResult(listings=[record, copy], provider_name="b")

    merged, removed = merge_search_results([first, second])

    assert len(merged.listings) == 1
    assert removed >= 1


def test_filters_for_recommendation_uses_year_range() -> None:
    buyer = _student_buyer()
    recommendation = recommend("student")["recommendations"][0]
    filters = filters_for_recommendation(recommendation, buyer)

    year_range = recommendation["selected_year_range"]
    assert filters.make == recommendation["make"]
    assert filters.model == recommendation["model"]
    assert filters.min_year == year_range["start_year"]
    assert filters.max_year == year_range["end_year"]
    assert filters.max_price == buyer["budget_type"]["max_amount"]


def test_top_model_count_capped_at_five() -> None:
    capped, was_capped = cap_top_model_count(10)
    assert capped == MAX_TOP_MODEL_COUNT
    assert was_capped is True

    provider = _RecordingProvider()
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=10,
        fallback_min_listings=1,
    )

    model_calls = [call for call in provider.calls if call.make is not None]
    assert len(model_calls) <= MAX_TOP_MODEL_COUNT
    assert result["diagnostics"].top_model_count_capped is True
    assert any("capped" in warning for warning in result["diagnostics"].warnings)


def test_early_stop_skips_remaining_model_queries() -> None:
    batch = [
        _provider_record(entry_id=f"fill-{index}", make="Toyota", model="Corolla")
        for index in range(EARLY_STOP_LISTING_COUNT + 1)
    ]

    class _HighVolumeProvider(ListingProvider):
        name = "high-volume"

        def __init__(self) -> None:
            self.calls: list[SearchFilters] = []

        def search(self, filters: SearchFilters) -> SearchResult:
            self.calls.append(filters)
            if filters.make and filters.model:
                return SearchResult(listings=list(batch), provider_name=self.name)
            return SearchResult(listings=[], provider_name=self.name)

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    provider = _HighVolumeProvider()
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=3,
        fallback_min_listings=1,
    )

    assert result["diagnostics"].early_stop_triggered is True
    assert result["diagnostics"].models_skipped_due_to_enough_results == 2
    assert len(provider.calls) == 1
    report = format_diagnostics_report(result["diagnostics"])
    assert "early_stopped: yes" in report
    assert "models_skipped_due_to_enough_results: 2" in report


def test_early_stop_reports_skipped_models_when_top_models_is_four() -> None:
    batch = [
        _provider_record(
            entry_id=f"fill-{index}",
            make="Toyota",
            model="Corolla",
        )
        for index in range(12)
    ]

    class _HighVolumeProvider(ListingProvider):
        name = "high-volume"

        def __init__(self) -> None:
            self.calls: list[SearchFilters] = []

        def search(self, filters: SearchFilters) -> SearchResult:
            self.calls.append(filters)
            if filters.make and filters.model:
                return SearchResult(listings=list(batch), provider_name=self.name)
            return SearchResult(listings=[], provider_name=self.name)

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    provider = _HighVolumeProvider()
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=4,
        fallback_min_listings=1,
    )
    diagnostics = result["diagnostics"]

    assert diagnostics.early_stop_triggered is True
    assert len(provider.calls) == 2
    assert len(diagnostics.recommended_models) == 4
    assert len(diagnostics.provider_searches) == 2
    assert diagnostics.models_skipped_due_to_enough_results == 2
    report = format_diagnostics_report(diagnostics)
    assert "Planned model queries: 4" in report
    assert "Provider queries executed: 2" in report
    assert "early_stopped: yes" in report
    assert "models_skipped_due_to_enough_results: 2" in report


def test_enough_inventory_skips_expand_models_without_early_stop() -> None:
    corolla = _provider_record(entry_id="c1", make="Toyota", model="Corolla")
    civic = _provider_record(entry_id="c2", make="Honda", model="Civic")
    camry = _provider_record(entry_id="c3", make="Toyota", model="Camry")
    sparse = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [corolla],
            ("Honda", "Civic"): [civic],
            ("Toyota", "Camry"): [camry],
            ("Mazda", "Mazda3"): [
                _provider_record(entry_id="c4", make="Mazda", model="Mazda3")
            ],
        }
    )
    service = ListingSearchService([sparse])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
        fallback_min_listings=3,
    )

    diagnostics = result["diagnostics"]
    assert diagnostics.early_stop_triggered is False
    assert diagnostics.expanded_fallback_triggered is True
    assert len(diagnostics.provider_searches) == 3
    assert diagnostics.models_skipped_due_to_enough_results == 2


def _budget_fallback_mix() -> list[dict[str, Any]]:
    return (
        [
            _provider_record(entry_id=f"sub-{index}", make="Subaru", model="XV")
            for index in range(8)
        ]
        + [
            _provider_record(entry_id=f"civ-{index}", make="Honda", model="Civic")
            for index in range(2)
        ]
        + [_provider_record(entry_id="cor-b", make="Toyota", model="Corolla")]
    )


def _retrieve_with_budget_fallback_mix(*, top_model_count: int = 1) -> dict[str, Any]:
    corolla = _provider_record(entry_id="c1", make="Toyota", model="Corolla")
    sparse = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [corolla],
            (None, None): _budget_fallback_mix(),
        }
    )
    service = ListingSearchService([sparse])
    return retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=top_model_count,
    )


def test_fallback_removes_non_recommended_models() -> None:
    result = _retrieve_with_budget_fallback_mix()
    diagnostics = result["diagnostics"]

    assert diagnostics.fallback_triggered is True
    pairs = {
        (record["listing"]["make"], record["listing"]["model"])
        for record in result["search_result"].listings
    }
    assert ("Subaru", "XV") not in pairs
    allowed = {
        (make, model)
        for make, model in recommended_model_keys(recommend("student")["recommendations"])
    }
    assert all(
        (str(make).casefold(), str(model).casefold()) in allowed
        for make, model in pairs
    )


def test_fallback_preserves_recommended_models() -> None:
    result = _retrieve_with_budget_fallback_mix()
    diagnostics = result["diagnostics"]

    pairs = {
        (record["listing"]["make"], record["listing"]["model"])
        for record in result["search_result"].listings
    }
    assert ("Honda", "Civic") in pairs
    assert ("Toyota", "Corolla") in pairs
    assert diagnostics.fallback_filtered_count == 3


def test_fallback_diagnostics_show_raw_vs_filtered_count() -> None:
    result = _retrieve_with_budget_fallback_mix()
    diagnostics = result["diagnostics"]
    diagnostics_dict = diagnostics.as_dict()

    assert diagnostics.fallback_raw_count == 11
    assert diagnostics.fallback_filtered_count == 3
    assert diagnostics_dict["fallback_raw_count"] == 11
    assert diagnostics_dict["fallback_filtered_count"] == 3
    fallback_row = next(
        row for row in diagnostics.listings_per_query if row.get("fallback")
    )
    assert fallback_row["fallback_raw_count"] == 11
    assert fallback_row["fallback_filtered_count"] == 3
    assert fallback_row["count"] == 3
    report = format_diagnostics_report(diagnostics)
    assert "Fallback listings: raw=11 filtered=3" in report


def test_top_results_exclude_unrelated_weak_fit_fallback() -> None:
    buyer = _student_buyer()
    recommendations = recommend("student")["recommendations"]
    corolla = _provider_record(entry_id="c1", make="Toyota", model="Corolla")
    budget_mix = _budget_fallback_mix()

    targeted = _retrieve_with_budget_fallback_mix()
    unfiltered_budget = tag_search_listings(
        SearchResult(listings=budget_mix, provider_name="recording"),
        RETRIEVAL_SOURCE_BUDGET_FALLBACK,
    )
    merged, _ = merge_search_results(
        [
            SearchResult(listings=[corolla], provider_name="recording"),
            unfiltered_budget,
        ]
    )
    unfiltered_ranked = rank_listings_for_recommendations(
        provider_records_to_scenarios(merged.listings),
        recommendations,
        buyer,
    )

    assert len(targeted["ranked"].get("unmatched_listings") or []) == 0
    assert targeted["diagnostics"].weak_fit_count < count_weak_fits(unfiltered_ranked)
    assert ("Subaru", "XV") not in {
        (entry["listing"]["make"], entry["listing"]["model"])
        for entry in targeted["ranked"].get("unmatched_listings") or []
    }


def test_fallback_tagging_on_listings() -> None:
    sparse = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [_provider_record(entry_id="c1", make="Toyota", model="Corolla")],
            (None, None): [
                _provider_record(entry_id=f"b{i}", make="Honda", model="Civic")
                for i in range(FALLBACK_MIN_LISTINGS)
            ],
        }
    )
    service = ListingSearchService([sparse])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
    )

    sources = {record.get("retrieval_source") for record in result["search_result"].listings}
    assert RETRIEVAL_SOURCE_RECOMMENDATION in sources
    assert RETRIEVAL_SOURCE_BUDGET_FALLBACK in sources
    assert result["diagnostics"].fallback_triggered is True


def test_expanded_fallback_tagging() -> None:
    sparse = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [_provider_record(entry_id="c1", make="Toyota", model="Corolla")],
            ("Honda", "Civic"): [_provider_record(entry_id="c2", make="Honda", model="Civic")],
            ("Toyota", "Camry"): [_provider_record(entry_id="c3", make="Toyota", model="Camry")],
            ("Mazda", "Mazda3"): [_provider_record(entry_id="c4", make="Mazda", model="Mazda3")],
        }
    )
    service = ListingSearchService([sparse])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
        fallback_min_listings=4,
    )

    sources = {record.get("retrieval_source") for record in result["search_result"].listings}
    assert RETRIEVAL_SOURCE_RECOMMENDATION in sources
    assert RETRIEVAL_SOURCE_EXPANDED in sources
    assert result["diagnostics"].expanded_fallback_triggered is True
    assert result["diagnostics"].fallback_triggered is False


def test_metrics_emitted() -> None:
    provider = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [_provider_record(entry_id="c1", make="Toyota", model="Corolla")],
        }
    )
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
        fallback_min_listings=1,
    )
    metrics = result["diagnostics"].metrics.as_dict()

    assert metrics["api_calls_per_provider"] == {"recording": 1}
    assert metrics["provider_query_count"] == 1
    assert metrics["raw_retrieved"] >= 1
    assert metrics["final_ranked"] >= 1
    assert 0.0 <= metrics["retrieval_efficiency"] <= 1.0
    assert metrics["cache_misses"] == 1
    assert metrics["cache_hits"] == 0
    assert "query_execution_ms" in metrics
    report = format_diagnostics_report(result["diagnostics"])
    assert "Retrieval efficiency:" in report
    assert "API calls:" in report
    assert "Fallback triggered:" in report
    assert "Listings returned per query:" in report


def test_query_cache_records_hits() -> None:
    provider = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [_provider_record(entry_id="c1", make="Toyota", model="Corolla")],
        }
    )
    service = ListingSearchService([provider])
    session = _RetrievalSession(service)
    filters = SearchFilters(make="Toyota", model="Corolla")

    session.search(filters, retrieval_source=RETRIEVAL_SOURCE_RECOMMENDATION)
    session.search(filters, retrieval_source=RETRIEVAL_SOURCE_RECOMMENDATION)

    assert session.metrics.cache_hits == 1
    assert session.metrics.cache_misses == 1
    assert len(provider.calls) == 1


def test_mock_student_inventory_with_real_fixtures() -> None:
    service = ListingSearchService(
        [
            MockListingProvider(STUDENT_LISTINGS),
            AutoDevProvider(AUTO_DEV_FIXTURE),
        ]
    )
    result = retrieve_inventory_for_buyer("student", service, buyer=_student_buyer())
    diagnostics = result["diagnostics"].as_dict()

    assert diagnostics["recommended_models"][0] == {"make": "Toyota", "model": "Corolla"}
    assert len(diagnostics["provider_searches"]) == 3
    assert diagnostics["listing_count"] >= 3
    assert result["ranked"]["groups"]
