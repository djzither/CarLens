"""Focused tests for recommendation-guided CLI retrieval (mocked providers only)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.listings.providers import ListingProvider, ListingSearchService, SearchFilters, SearchResult
from src.listings.recommendation_inventory import (
    FALLBACK_MIN_LISTINGS,
    filter_fallback_to_recommended_models,
    filters_for_recommendation,
    format_available_model_labels,
    format_post_retrieval_diagnostics,
    recommended_model_keys,
    resolve_selected_recommendation,
    retrieve_inventory_for_buyer,
    retrieve_inventory_for_selected_model,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_PATH = PROJECT_ROOT / "Scripts" / "demo_live_inventory.py"


def _student_buyer() -> dict[str, Any]:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == "student":
            return profile
    raise AssertionError("student profile missing")


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


class _RecordingProvider(ListingProvider):
    name = "recording"

    def __init__(self, responses: dict[tuple[str | None, str | None], list[dict]] | None = None) -> None:
        self.calls: list[SearchFilters] = []
        self._responses = responses or {}

    def search(self, filters: SearchFilters) -> SearchResult:
        self.calls.append(filters)
        key = (filters.make, filters.model)
        return SearchResult(
            listings=list(self._responses.get(key, [])),
            provider_name=self.name,
        )

    def get_by_id(self, listing_id: str) -> dict | None:
        return None


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("demo_live_inventory", DEMO_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_live_inventory"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def student_recommendations() -> list[dict[str, Any]]:
    return recommend("student")["recommendations"]


# --- 1. Recommendation-only mode ---


def test_recommendation_only_mode_returns_top_n_vehicles(
    student_recommendations: list[dict[str, Any]],
) -> None:
    demo = _load_demo_module()
    lines: list[str] = []
    for rank, item in enumerate(student_recommendations[:3], start=1):
        lines.append(demo.format_recommendation_entry(rank, item))

    output = "\n".join(lines)
    for item in student_recommendations[:3]:
        assert item["make"] in output
        assert item["model"] in output
        assert f"{item['normalized_score']:.3f}" in output


def test_recommendation_only_mode_does_not_invoke_providers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = _load_demo_module()
    provider_init = MagicMock(side_effect=AssertionError("provider must not be constructed"))
    search_init = MagicMock(side_effect=AssertionError("search service must not be constructed"))
    monkeypatch.setattr(demo, "AutoDevProvider", provider_init)
    monkeypatch.setattr(demo, "ListingSearchService", search_init)
    monkeypatch.delenv("AUTODEV_API_KEY", raising=False)
    monkeypatch.delenv("AUTO_DEV_API_KEY", raising=False)

    exit_code = demo.run_show_recommendations(
        buyer_profile_id="student",
        top_models=5,
    )

    assert exit_code == 0
    provider_init.assert_not_called()
    search_init.assert_not_called()
    assert "no inventory search" in capsys.readouterr().out


# --- 2. Selected-model retrieval ---


def test_selected_model_builds_search_filters_with_make_and_model(
    student_recommendations: list[dict[str, Any]],
) -> None:
    buyer = _student_buyer()
    civic = resolve_selected_recommendation(
        student_recommendations,
        selected_model="Honda Civic",
    )
    filters = filters_for_recommendation(civic, buyer)

    assert filters.make == "Honda"
    assert filters.model == "Civic"
    assert filters.max_price == buyer["budget_type"]["max_amount"]
    assert filters.max_mileage == buyer["max_mileage"]


def test_honda_civic_selection_only_queries_civic_inventory() -> None:
    buyer = _student_buyer()
    civic_listing = _provider_record(entry_id="civic-1", make="Honda", model="Civic")
    crosstrek = _provider_record(entry_id="sub-1", make="Subaru", model="XV")

    provider = _RecordingProvider(
        {
            ("Honda", "Civic"): [civic_listing],
            ("Subaru", "XV"): [crosstrek],
        }
    )
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_selected_model(
        "student",
        "Honda",
        "Civic",
        service,
        buyer=buyer,
        fallback_min_listings=1,
    )

    assert len(provider.calls) == 1
    assert provider.calls[0].make == "Honda"
    assert provider.calls[0].model == "Civic"
    assert ("Subaru", "XV") not in {(c.make, c.model) for c in provider.calls}
    assert len(result["search_result"].listings) == 1
    assert result["search_result"].listings[0]["listing"]["model"] == "Civic"


def test_selected_model_ranked_results_exclude_unrelated_models() -> None:
    buyer = _student_buyer()
    civic_listing = _provider_record(entry_id="civic-1", make="Honda", model="Civic")
    provider = _RecordingProvider({("Honda", "Civic"): [civic_listing]})
    service = ListingSearchService([provider])

    result = retrieve_inventory_for_selected_model(
        "student",
        "Honda",
        "Civic",
        service,
        buyer=buyer,
        fallback_min_listings=1,
    )

    for record in result["search_result"].listings:
        assert record["listing"]["make"] == "Honda"
        assert record["listing"]["model"] == "Civic"
    assert len(result["ranked"].get("unmatched_listings") or []) == 0
    assert result["ranked"].get("single_model_mode") is True


# --- 3. Invalid selection handling ---


def test_invalid_selected_model_raises_with_valid_options(
    student_recommendations: list[dict[str, Any]],
) -> None:
    with pytest.raises(ValueError, match="not found in recommendations"):
        resolve_selected_recommendation(
            student_recommendations,
            selected_model="Honda Fit",
        )

    available = format_available_model_labels(student_recommendations)
    with pytest.raises(ValueError, match=available):
        resolve_selected_recommendation(
            student_recommendations,
            selected_model="Not A Real Car",
        )


def test_cli_invalid_selected_model_prints_error_and_valid_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    student_recommendations: list[dict[str, Any]],
) -> None:
    monkeypatch.delenv("AUTODEV_API_KEY", raising=False)
    monkeypatch.delenv("AUTO_DEV_API_KEY", raising=False)
    demo = _load_demo_module()

    exit_code = demo.main(
        ["student", "--selected-model", "Honda Fit", "--top", "5"],
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error:" in captured.err
    assert "not found" in captured.err
    assert "Valid options:" in captured.err
    assert student_recommendations[0]["make"] in captured.err


# --- 4. Fallback behavior ---


def test_budget_fallback_filter_removes_unrelated_makes_and_models() -> None:
    recommendations = recommend("student")["recommendations"]
    allowed = recommended_model_keys(recommendations)
    corolla = _provider_record(entry_id="cor-1", make="Toyota", model="Corolla")
    crosstrek = _provider_record(entry_id="sub-1", make="Subaru", model="XV")

    raw = SearchResult(
        listings=[corolla, crosstrek, crosstrek],
        provider_name="recording",
    )
    filtered = filter_fallback_to_recommended_models(raw, allowed)

    assert len(filtered.listings) == 1
    assert filtered.listings[0]["listing"]["make"] == "Toyota"
    assert filtered.provider_warnings == raw.provider_warnings
    assert filtered.errors == raw.errors
    assert filtered.provider_name == raw.provider_name


def test_retrieve_inventory_budget_fallback_excludes_unrelated_models() -> None:
    corolla = _provider_record(entry_id="c1", make="Toyota", model="Corolla")
    crosstrek = _provider_record(entry_id="sub-1", make="Subaru", model="XV")
    civic = _provider_record(entry_id="c2", make="Honda", model="Civic")

    class _EmptyModelsThenBudget(ListingProvider):
        name = "recording"

        def __init__(self) -> None:
            self.calls: list[SearchFilters] = []

        def search(self, filters: SearchFilters) -> SearchResult:
            self.calls.append(filters)
            if filters.make is not None and filters.model is not None:
                return SearchResult(listings=[], provider_name=self.name)
            return SearchResult(
                listings=[crosstrek, civic, corolla],
                provider_name=self.name,
            )

        def get_by_id(self, listing_id: str) -> dict | None:
            return None

    provider = _EmptyModelsThenBudget()
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
        fallback_min_listings=2,
    )

    pairs = {
        (record["listing"]["make"], record["listing"]["model"])
        for record in result["search_result"].listings
    }
    assert ("Subaru", "XV") not in pairs
    diagnostics = result["diagnostics"]
    assert diagnostics.fallback_triggered is True
    assert diagnostics.fallback_raw_count == 3
    assert diagnostics.fallback_filtered_count == 2
    assert any(
        search.get("retrieval_source") == "budget_fallback"
        for search in diagnostics.provider_searches
    )


def test_budget_fallback_preserves_recommended_model_pairs() -> None:
    corolla = _provider_record(entry_id="cor-1", make="Toyota", model="Corolla")
    civic = _provider_record(entry_id="civ-1", make="Honda", model="Civic")

    provider = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [],
            (None, None): [corolla, civic],
        }
    )
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
        fallback_min_listings=2,
    )

    pairs = {
        (record["listing"]["make"], record["listing"]["model"])
        for record in result["search_result"].listings
    }
    assert ("Toyota", "Corolla") in pairs
    assert ("Honda", "Civic") in pairs


# --- 5. Retrieval diagnostics ---


def test_selected_model_retrieval_diagnostics() -> None:
    buyer = _student_buyer()
    civic_listing = _provider_record(entry_id="civic-1", make="Honda", model="Civic")
    provider = _RecordingProvider({("Honda", "Civic"): [civic_listing]})
    service = ListingSearchService([provider])

    result = retrieve_inventory_for_selected_model(
        "student",
        "Honda",
        "Civic",
        service,
        buyer=buyer,
        fallback_min_listings=1,
    )
    diagnostics = result["diagnostics"]
    diagnostics_dict = diagnostics.as_dict()
    unmatched = len(result["ranked"].get("unmatched_listings") or [])

    assert diagnostics.selected_model == "Honda Civic"
    assert diagnostics_dict["selected_model"] == "Honda Civic"
    assert len(diagnostics.provider_searches) >= 1
    assert diagnostics_dict["provider_queries"] == diagnostics.provider_searches
    assert diagnostics.provider_searches[0]["make"] == "Honda"
    assert diagnostics.provider_searches[0]["model"] == "Civic"
    assert all(search.get("make") == "Honda" for search in diagnostics.provider_searches)
    assert all(search.get("model") == "Civic" for search in diagnostics.provider_searches)
    assert diagnostics.fallback_triggered is False
    assert diagnostics.constrained_fallback_triggered is False
    assert diagnostics.is_single_model_retrieval() is True
    assert result["ranked"].get("single_model_mode") is True

    report = format_post_retrieval_diagnostics(
        diagnostics,
        unmatched_model_count=unmatched,
    )
    assert "selected_model: Honda Civic" in report
    assert "Provider queries executed:" in report
    assert "Fallback triggered: no" in report
    assert f"Unmatched model count: {unmatched}" in report
    assert unmatched == 0


def test_multi_model_retrieval_diagnostics_include_fallback_and_queries() -> None:
    corolla = _provider_record(entry_id="c1", make="Toyota", model="Corolla")
    provider = _RecordingProvider(
        {
            ("Toyota", "Corolla"): [corolla],
            (None, None): [
                _provider_record(entry_id=f"b{i}", make="Toyota", model="Corolla")
                for i in range(FALLBACK_MIN_LISTINGS)
            ],
        }
    )
    service = ListingSearchService([provider])
    result = retrieve_inventory_for_buyer(
        "student",
        service,
        buyer=_student_buyer(),
        top_model_count=1,
        fallback_min_listings=FALLBACK_MIN_LISTINGS,
    )
    diagnostics = result["diagnostics"]
    unmatched = len(result["ranked"].get("unmatched_listings") or [])

    assert diagnostics.selected_model is None
    assert len(diagnostics.provider_searches) >= 2
    assert diagnostics.fallback_triggered is True
    assert any(
        search.get("retrieval_source") == "budget_fallback"
        for search in diagnostics.provider_searches
    )
    report = format_post_retrieval_diagnostics(
        diagnostics,
        unmatched_model_count=unmatched,
    )
    assert "selected_model" not in report
    assert "Fallback triggered: yes" in report
    assert "Provider queries executed:" in report
    assert f"Unmatched model count: {unmatched}" in report
