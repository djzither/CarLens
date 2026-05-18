from __future__ import annotations

from app.listing_display import (
    build_watchouts,
    format_listing_facts,
    format_mileage,
    format_recommended_because,
    has_major_warnings,
    qualifies_as_top_pick,
    top_pick_banner_text,
    warning_is_major,
)
from src.listings.listing_fit import DIRTY_TITLE_WARNING


def _strong_entry(*, warnings: list[str] | None = None, clean_title: bool = True) -> dict:
    return {
        "listing_name": "2016 Toyota Corolla LE",
        "listing": {
            "year": 2016,
            "make": "Toyota",
            "model": "Corolla",
            "price": 9_500,
            "mileage": 92_000,
            "clean_title": clean_title,
        },
        "fit": {
            "fit_label": "Strong fit",
            "fit_score": 0.91,
            "warnings": warnings or [],
            "positive_reasons": ["Under budget"],
            "negative_reasons": [],
        },
        "confidence": {"confidence_level": "High"},
    }


def test_format_mileage_uses_k_suffix():
    assert format_mileage(92_000) == "92k miles"
    assert format_mileage(None) == "Mileage not listed"


def test_format_listing_facts_joins_price_mileage_title():
    facts = format_listing_facts(_strong_entry()["listing"])
    assert "$9,500" in facts
    assert "92k miles" in facts
    assert "Clean title" in facts


def test_format_recommended_because_uses_traits():
    recommendation = {
        "reasons": [
            {"trait": "reliable", "contribution": 0.2},
            {"type": "missing_trait", "trait": "awd", "message": "Limited"},
        ]
    }
    assert format_recommended_because(recommendation) == "reliable"


def test_build_watchouts_uses_negative_reasons():
    entry = _strong_entry()
    entry["fit"]["negative_reasons"] = ["Mileage exceeds preferred max by 5,000"]
    assert build_watchouts(entry["fit"]) == ["Mileage exceeds preferred max by 5,000"]


def test_warning_is_major_detects_dirty_title():
    assert warning_is_major(DIRTY_TITLE_WARNING)


def test_qualifies_as_top_pick_requires_strong_fit_and_clean_title():
    assert qualifies_as_top_pick(_strong_entry()) is True
    dirty = _strong_entry(clean_title=False)
    dirty["listing"]["clean_title"] = False
    dirty["fit"]["warnings"] = [DIRTY_TITLE_WARNING]
    assert qualifies_as_top_pick(dirty) is False


def test_top_pick_banner_when_not_qualified():
    entry = _strong_entry()
    entry["fit"]["fit_label"] = "Moderate fit"
    assert top_pick_banner_text(entry) == "No clear top pick — review warnings."


def test_has_major_warnings_for_budget_exceed():
    fit = {"warnings": ["Price $20,000 exceeds your $10,000 budget"]}
    assert has_major_warnings(fit) is True
