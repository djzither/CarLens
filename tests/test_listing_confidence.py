from __future__ import annotations

import pytest

from src.listings.listing_confidence import (
    assess_listing_confidence,
    detect_inferred_fields,
    title_has_ambiguous_mileage,
)
from src.listings.listing_fit import score_listing_fit
from src.listings.listing_normalizer import normalize_listing


def _complete_corolla_raw() -> dict:
    return {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85_000,
        "price": 10_500,
        "clean_title": True,
        "listing_url": "https://example.com/corolla",
    }


def test_high_confidence_for_complete_explicit_listing():
    raw = _complete_corolla_raw()
    normalized = normalize_listing(raw)

    result = assess_listing_confidence(raw, normalized)

    assert result["confidence_level"] == "High"
    assert result["inferred_fields"] == []
    assert result["missing_fields"] == []
    assert result["ambiguity_detected"] is False
    assert result["conflicting_signals"] is False


def test_medium_confidence_when_price_missing():
    raw = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85_000,
        "clean_title": True,
    }
    normalized = normalize_listing(raw)

    result = assess_listing_confidence(raw, normalized)

    assert result["confidence_level"] == "Medium"
    assert result["missing_fields"] == ["price"]


def test_low_confidence_for_sparse_title_only_listing():
    raw = {
        "title": "2016 Toyota Corolla LE 92k miles",
        "listing_url": "https://example.com/sparse",
    }
    normalized = normalize_listing(raw)
    inferred = detect_inferred_fields(raw, normalized)

    assert len(inferred) >= 2
    result = assess_listing_confidence(raw, normalized)

    assert result["confidence_level"] == "Low"


def test_low_confidence_when_title_mileage_is_ambiguous():
    assert title_has_ambiguous_mileage(
        "new engine at 100k, now at 45k miles on 2016 Toyota Corolla"
    )

    raw = {
        "title": "new engine at 100k, now at 45k miles on 2016 Toyota Corolla",
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 9_000,
        "clean_title": True,
    }
    normalized = normalize_listing(raw)

    result = assess_listing_confidence(raw, normalized)

    assert result["ambiguity_detected"] is True
    assert result["confidence_level"] == "Low"


def test_medium_confidence_when_mileage_inferred_from_title():
    raw = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "price": 10_500,
        "clean_title": True,
        "trim": "LE",
        "title": "2016 Toyota Corolla 85k miles",
    }
    normalized = normalize_listing(raw)

    assert "mileage" in detect_inferred_fields(raw, normalized)

    result = assess_listing_confidence(raw, normalized)

    assert result["confidence_level"] == "Medium"
    assert result["inferred_fields"] == ["mileage"]


def test_low_confidence_when_fit_label_was_capped(
    student_buyer: dict,
    student_corolla_recommendation: dict,
):
    raw = {
        "make": "Toyota",
        "model": "Corolla",
        "year": 2016,
        "mileage": 85_000,
        "price": 10_500,
        "clean_title": False,
    }
    normalized = normalize_listing(raw)
    fit = score_listing_fit(raw, student_corolla_recommendation, student_buyer)

    assert fit["label_was_capped"] is True

    result = assess_listing_confidence(raw, normalized, fit=fit)

    assert result["conflicting_signals"] is True
    assert result["confidence_level"] == "Low"


@pytest.fixture
def student_buyer() -> dict:
    return {
        "id": "student",
        "budget_type": {"type": "max_purchase", "max_amount": 12_000},
        "max_mileage": 130_000,
        "hard_requirements": ["price_under_budget"],
    }


@pytest.fixture
def student_corolla_recommendation() -> dict:
    return {
        "make": "Toyota",
        "model": "Corolla",
        "selected_year_range": {"start_year": 2014, "end_year": 2018},
    }
