from __future__ import annotations

import pytest

from src.listings.listing_compare import (
    MAX_COMPARE_LISTINGS,
    MIN_COMPARE_LISTINGS,
    build_compare_row,
    collect_selected_compare_ids,
    compare_checkbox_key,
    compare_id_from_checkbox_key,
    generate_beats_other_sentence,
    get_saved_listing_ids,
    is_listing_saved,
    make_compare_id,
    parse_compare_id,
    resolve_compare_entries,
    toggle_saved_listing,
    validate_compare_selection,
)
from src.listings.listing_ranker import pick_best_listing


def test_compare_id_round_trip():
    compare_id = make_compare_id("Toyota", "Corolla", "good_corolla")
    assert parse_compare_id(compare_id) == ("Toyota", "Corolla", "good_corolla")
    assert compare_id_from_checkbox_key(compare_checkbox_key(compare_id)) == compare_id


def test_validate_compare_selection():
    assert validate_compare_selection(0) is not None
    assert validate_compare_selection(1) is not None
    assert validate_compare_selection(MIN_COMPARE_LISTINGS) is None
    assert validate_compare_selection(MAX_COMPARE_LISTINGS) is None
    assert validate_compare_selection(MAX_COMPARE_LISTINGS + 1) is not None


def test_build_compare_row_formats_listing_fields():
    entry = {
        "listing_name": "good_corolla",
        "listing": {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
            "trim": "LE",
            "price": 10_500,
            "mileage": 85_000,
            "clean_title": True,
            "raw_title": "2016 Toyota Corolla LE",
            "listing_url": "https://example.com/corolla",
        },
        "provider_raw_fields": [
            "make",
            "model",
            "year",
            "price",
            "mileage",
            "clean_title",
        ],
        "fit": {
            "fit_label": "Strong fit",
            "fit_score": 0.91,
            "positive_reasons": ["Under budget"],
            "negative_reasons": [],
            "warnings": ["Minor note"],
        },
        "confidence": {"confidence_level": "High"},
    }

    row = build_compare_row(entry)

    assert row["fit_quality"] == "Strong"
    assert row["data_quality"] == "High"
    assert row["price"] == "$10,500"
    assert row["mileage"] == "85,000 mi"
    assert row["title_certainty"] == "Clean (verified)"
    assert "Under budget" in row["why_it_fits"]
    assert "Minor note" in row["watchouts"]
    assert row["title"] == "2016 Toyota Corolla LE"
    assert row["fit_label"] == "Strong fit"
    assert row["confidence"] == "High"


def test_collect_selected_compare_ids_from_session_state():
    compare_id = make_compare_id("Honda", "Civic", "good_civic")
    session = {
        compare_checkbox_key(compare_id): True,
        "compare_other": False,
        "unrelated": True,
    }

    assert collect_selected_compare_ids(session) == [compare_id]


def test_resolve_compare_entries_preserves_selection_order():
    first = make_compare_id("Toyota", "Corolla", "a")
    second = make_compare_id("Honda", "Civic", "b")
    catalog = {
        first: {"listing_name": "a"},
        second: {"listing_name": "b"},
    }

    resolved = resolve_compare_entries(catalog, [second, first])

    assert [entry["listing_name"] for entry in resolved] == ["b", "a"]


def test_pick_best_listing_uses_fit_score_ranking():
    entries = [
        {
            "listing_name": "weak",
            "listing": {"price": 9_000, "mileage": 90_000},
            "fit": {
                "fit_score": 0.4,
                "fit_label": "Weak fit",
                "warnings": ["a", "b"],
            },
        },
        {
            "listing_name": "strong",
            "listing": {"price": 10_000, "mileage": 80_000},
            "fit": {
                "fit_score": 0.9,
                "fit_label": "Strong fit",
                "warnings": [],
            },
        },
    ]

    best = pick_best_listing(entries)

    assert best["listing_name"] == "strong"


def test_pick_best_listing_requires_entries():
    with pytest.raises(ValueError, match="entries must not be empty"):
        pick_best_listing([])


def test_generate_beats_other_sentence_title_and_mileage():
    winner = {
        "listing_name": "good_corolla",
        "listing": {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2016,
            "mileage": 70_000,
            "price": 10_000,
            "clean_title": True,
        },
        "fit": {"fit_label": "Strong fit", "fit_score": 0.9},
        "confidence": {"confidence_level": "High"},
    }
    other = {
        "listing_name": "other_corolla",
        "listing": {
            "make": "Toyota",
            "model": "Corolla",
            "year": 2015,
            "mileage": 110_000,
            "price": 10_500,
            "clean_title": None,
        },
        "fit": {"fit_label": "Moderate fit", "fit_score": 0.6},
        "confidence": {"confidence_level": "Medium"},
    }

    sentence = generate_beats_other_sentence(winner, other)

    assert sentence.startswith("This Toyota Corolla ranks higher because")
    assert "verified title history" in sentence
    assert "lower mileage" in sentence


def test_favorites_toggle_session_only():
    compare_id = make_compare_id("Toyota", "Corolla", "a")
    session: dict = {}

    assert not is_listing_saved(session, compare_id)
    assert toggle_saved_listing(session, compare_id) is True
    assert is_listing_saved(session, compare_id)
    assert compare_id in get_saved_listing_ids(session)
    assert toggle_saved_listing(session, compare_id) is False
    assert not is_listing_saved(session, compare_id)
