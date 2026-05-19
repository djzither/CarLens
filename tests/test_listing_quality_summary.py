"""Tests for listing quality summary helper."""

from __future__ import annotations

from src.listings.listing_quality_summary import (
    CLEAN_TITLE_BADGE,
    TITLE_ISSUE_WARNING,
    TITLE_UNAVAILABLE_WARNING,
    ListingQualityWarningsContext,
    build_listing_quality_summary,
)


def _provider_record(
    *,
    listing: dict,
    provider_name: str = "mock",
    provider_raw_fields: list[str] | None = None,
) -> dict:
    fields = provider_raw_fields
    if fields is None:
        fields = sorted(
            key
            for key, value in listing.items()
            if value is not None and not (isinstance(value, str) and not value.strip())
        )
    return {
        "id": "demo-1",
        "listing": listing,
        "provider_name": provider_name,
        "provider_listing_id": "demo-1",
        "provider_raw_fields": fields,
    }


def _complete_listing(**overrides) -> dict:
    base = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 10_500,
        "mileage": 85_000,
        "clean_title": True,
        "source": "mock",
    }
    base.update(overrides)
    return base


def test_high_confidence_complete_listing_with_clean_title() -> None:
    record = _provider_record(listing=_complete_listing())
    summary = build_listing_quality_summary(record)

    assert summary["source"] == "mock"
    assert summary["confidence"] == "high"
    assert summary["badges"] == [CLEAN_TITLE_BADGE]
    assert summary["warnings"] == []


def test_medium_confidence_when_title_history_unavailable() -> None:
    listing = _complete_listing()
    del listing["clean_title"]
    record = _provider_record(listing=listing)
    summary = build_listing_quality_summary(record)

    assert summary["confidence"] == "medium"
    assert summary["badges"] == []
    assert summary["warnings"] == [TITLE_UNAVAILABLE_WARNING]


def test_medium_confidence_when_one_important_field_missing() -> None:
    listing = _complete_listing()
    record = _provider_record(
        listing=listing,
        provider_raw_fields=[
            "make",
            "model",
            "year",
            "price",
            "clean_title",
        ],
    )
    summary = build_listing_quality_summary(record)

    assert summary["confidence"] == "medium"
    assert CLEAN_TITLE_BADGE in summary["badges"]


def test_medium_confidence_with_single_provider_warning() -> None:
    record = _provider_record(listing=_complete_listing())
    ctx = ListingQualityWarningsContext(
        provider_warnings=["mock: missing optional image_url"],
    )
    summary = build_listing_quality_summary(record, warnings_context=ctx)

    assert summary["confidence"] == "medium"
    assert summary["badges"] == [CLEAN_TITLE_BADGE]


def test_low_confidence_when_title_issue_reported() -> None:
    record = _provider_record(listing=_complete_listing(clean_title=False))
    summary = build_listing_quality_summary(record)

    assert summary["confidence"] == "low"
    assert summary["badges"] == []
    assert summary["warnings"] == [TITLE_ISSUE_WARNING]


def test_low_confidence_when_multiple_important_fields_missing() -> None:
    listing = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "clean_title": True,
        "source": "mock",
    }
    record = _provider_record(
        listing=listing,
        provider_raw_fields=["make", "model", "year", "clean_title"],
    )
    summary = build_listing_quality_summary(record)

    assert summary["confidence"] == "low"
    assert CLEAN_TITLE_BADGE in summary["badges"]


def test_low_confidence_with_multiple_provider_warnings() -> None:
    record = _provider_record(listing=_complete_listing())
    ctx = ListingQualityWarningsContext(
        provider_warnings=[
            "mock: missing optional mileage",
            "mock: skipped — missing listing id",
        ],
    )
    summary = build_listing_quality_summary(record, warnings_context=ctx)

    assert summary["confidence"] == "low"
