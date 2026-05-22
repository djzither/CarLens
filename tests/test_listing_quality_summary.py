"""Tests for listing quality summary (fit vs data quality separated)."""

from __future__ import annotations

from src.listings.listing_fit import DIRTY_TITLE_WARNING
from src.listings.listing_quality_summary import (
    AUTO_DEV_TITLE_UNAVAILABLE_WARNING,
    CLEAN_TITLE_BADGE,
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


def test_strong_fit_with_medium_data_quality() -> None:
    listing = _complete_listing()
    del listing["clean_title"]
    record = _provider_record(listing=listing)
    fit = {"fit_label": "Strong fit", "fit_score": 0.9}

    summary = build_listing_quality_summary(record, fit=fit)

    assert summary["fit_quality"] == "strong"
    assert summary["data_quality_level"] == "medium"
    assert summary["title_certainty"] == "unknown"


def test_weak_fit_with_high_data_quality() -> None:
    record = _provider_record(listing=_complete_listing())
    fit = {"fit_label": "Weak fit", "fit_score": 0.2}

    summary = build_listing_quality_summary(record, fit=fit)

    assert summary["fit_quality"] == "weak"
    assert summary["data_quality_level"] == "high"
    assert summary["data_completeness"] == 1.0
    assert summary["title_certainty"] == "clean"
    assert summary["badges"] == [CLEAN_TITLE_BADGE]


def test_dirty_title_vs_unknown_title_warnings() -> None:
    dirty_record = _provider_record(listing=_complete_listing(clean_title=False))
    unknown_listing = _complete_listing()
    del unknown_listing["clean_title"]
    unknown_record = _provider_record(listing=unknown_listing)

    dirty_summary = build_listing_quality_summary(dirty_record)
    unknown_summary = build_listing_quality_summary(unknown_record)

    assert dirty_summary["title_certainty"] == "dirty"
    assert unknown_summary["title_certainty"] == "unknown"
    assert dirty_summary["warnings"] == [DIRTY_TITLE_WARNING]
    assert unknown_summary["warnings"] == [TITLE_UNAVAILABLE_WARNING]
    assert "dirty title" not in unknown_summary["warnings"][0].casefold()


def test_auto_dev_unknown_title_uses_provider_specific_wording() -> None:
    listing = _complete_listing()
    del listing["clean_title"]
    listing["title_status"] = "unknown"
    listing["source"] = "auto.dev"
    record = _provider_record(listing=listing, provider_name="auto.dev")

    summary = build_listing_quality_summary(record)

    assert summary["title_certainty"] == "unknown"
    assert summary["warnings"] == [AUTO_DEV_TITLE_UNAVAILABLE_WARNING]


def test_provider_raw_fields_drive_provided_and_unavailable() -> None:
    listing = _complete_listing()
    record = _provider_record(
        listing=listing,
        provider_raw_fields=["make", "model", "year", "price", "clean_title"],
    )

    summary = build_listing_quality_summary(record)

    assert summary["provided_fields"] == ["make", "model", "price", "year"]
    assert summary["unavailable_fields"] == ["mileage"]
    assert summary["data_completeness"] == 0.8


def test_high_data_quality_with_complete_provenance() -> None:
    record = _provider_record(listing=_complete_listing())
    summary = build_listing_quality_summary(
        record,
        fit={"fit_label": "Moderate fit"},
    )

    assert summary["source"] == "mock"
    assert summary["fit_quality"] == "moderate"
    assert summary["data_quality_level"] == "high"
    assert summary["provided_fields"] == [
        "make",
        "mileage",
        "model",
        "price",
        "year",
    ]
    assert summary["unavailable_fields"] == []
    assert summary["warnings"] == []


def test_low_data_quality_from_multiple_provider_warnings() -> None:
    record = _provider_record(listing=_complete_listing())
    ctx = ListingQualityWarningsContext(
        provider_warnings=[
            "mock: missing optional mileage",
            "mock: skipped — missing listing id",
        ],
    )
    summary = build_listing_quality_summary(
        record,
        fit={"fit_label": "Strong fit"},
        warnings_context=ctx,
    )

    assert summary["fit_quality"] == "strong"
    assert summary["data_quality_level"] == "low"
