"""Tests for provider warning summarization."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.listings.providers import (
    AutoDevProvider,
    ListingSearchService,
    MarketcheckProvider,
    MockListingProvider,
    SearchFilters,
    summarize_provider_warnings,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STUDENT_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
AUTO_DEV_FIXTURE = (
    PROJECT_ROOT / "data" / "sample_listings" / "provider_payloads" / "auto_dev_sample.json"
)
MARKETCHECK_FIXTURE = (
    PROJECT_ROOT
    / "data"
    / "sample_listings"
    / "provider_payloads"
    / "marketcheck_sample.json"
)


def test_groups_repeated_warning_types() -> None:
    warnings = [
        "a: missing optional mileage",
        "b: missing optional mileage",
        "c: missing optional mileage",
        "d: skipped — missing price",
        "e: skipped — missing price",
    ]
    summary = summarize_provider_warnings(warnings)

    assert summary.counts_by_category["optional:mileage"] == 3
    assert summary.counts_by_category["skipped:price"] == 2
    assert "3 listings missing optional mileage" in summary.summary_lines
    assert "2 listings skipped for missing price" in summary.summary_lines


def test_preserves_raw_warnings() -> None:
    warnings = ["good_corolla: missing optional clean_title"]
    summary = summarize_provider_warnings(warnings)

    assert summary.raw_warnings == warnings
    assert summary.raw_warnings is not warnings


def test_handles_no_warnings() -> None:
    summary = summarize_provider_warnings([])
    assert summary.summary_lines == []
    assert summary.counts_by_category == {}
    assert summary.raw_warnings == []

    empty = summarize_provider_warnings(None)
    assert empty.summary_lines == []
    assert empty.raw_warnings == []


def test_summarizes_aggregated_search_result() -> None:
    service = ListingSearchService(
        [
            MockListingProvider(STUDENT_LISTINGS_PATH),
            AutoDevProvider(AUTO_DEV_FIXTURE),
            MarketcheckProvider(MARKETCHECK_FIXTURE),
        ]
    )
    result = service.search(SearchFilters())
    summary = summarize_provider_warnings(result.provider_warnings)

    assert result.provider_warnings
    assert summary.raw_warnings == result.provider_warnings
    assert summary.summary_lines
    total_counted = sum(summary.counts_by_category.values())
    assert total_counted >= len(
        [w for w in result.provider_warnings if "missing optional" in w or "skipped" in w]
    )


def test_strips_provider_prefix_before_grouping() -> None:
    warnings = [
        "mock: a: missing optional mileage",
        "mock: b: missing optional mileage",
        "auto.dev: c: skipped — missing price",
    ]
    summary = summarize_provider_warnings(warnings)

    assert summary.counts_by_category["optional:mileage"] == 2
    assert summary.counts_by_category["skipped:price"] == 1
