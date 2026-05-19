"""Tests for first-visit auto-load and onboarding intro card."""

from __future__ import annotations

from app.app import (
    ADVERSARIAL_DATASET_KEY,
    AUTO_LOAD_SPINNER_MESSAGE,
    AUTO_LOAD_STATUS_MESSAGE,
    INTRO_CARD_DISMISSED_KEY,
    available_listing_dataset_keys,
    build_default_ranked_payload,
    dismiss_intro_card,
    ensure_initial_ranked_payload,
    has_displayable_ranked_content,
    is_blank_ui_state,
    load_sample_listings,
    should_show_intro_card,
    _listings_for_ranker,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles


def _default_catalog_inputs():
    loaded = load_sample_listings("basic")
    raw_lookup = {item["id"]: item["listing"] for item in loaded}
    display_names = {item["id"]: item.get("display_name") for item in loaded}
    return raw_lookup, display_names


def test_auto_load_initializes_ranked_payload():
    profiles = load_buyer_profiles()["profiles"]
    payload = build_default_ranked_payload(profiles)
    raw_lookup, display_names = _default_catalog_inputs()
    session_state: dict = {}

    loaded = ensure_initial_ranked_payload(
        session_state,
        payload=payload,
        prefs_key=("student", "basic", 12_000, 130_000, False, False),
        raw_lookup=raw_lookup,
        display_names=display_names,
    )

    assert loaded is True
    assert "ranked_payload" in session_state
    assert session_state["auto_loaded"] is True
    assert session_state["compare_catalog"]


def test_ensure_initial_ranked_payload_is_idempotent():
    profiles = load_buyer_profiles()["profiles"]
    payload = build_default_ranked_payload(profiles)
    raw_lookup, display_names = _default_catalog_inputs()
    session_state: dict = {}

    assert ensure_initial_ranked_payload(
        session_state,
        payload=payload,
        prefs_key=("student", "basic", 12_000, 130_000, False, False),
        raw_lookup=raw_lookup,
        display_names=display_names,
    )
    assert not ensure_initial_ranked_payload(
        session_state,
        payload=payload,
        prefs_key=("student", "basic", 12_000, 130_000, False, False),
        raw_lookup=raw_lookup,
        display_names=display_names,
    )


def test_first_render_not_blank_after_auto_load():
    profiles = load_buyer_profiles()["profiles"]
    payload = build_default_ranked_payload(profiles)
    raw_lookup, display_names = _default_catalog_inputs()
    session_state: dict = {}

    ensure_initial_ranked_payload(
        session_state,
        payload=payload,
        prefs_key=("student", "basic", 12_000, 130_000, False, False),
        raw_lookup=raw_lookup,
        display_names=display_names,
    )

    assert not is_blank_ui_state(session_state)
    assert has_displayable_ranked_content(session_state["ranked_payload"])


def test_build_default_ranked_payload_has_listings():
    payload = build_default_ranked_payload()
    loaded = load_sample_listings("basic")
    listings = _listings_for_ranker(loaded)
    assert len(listings) >= 1
    assert has_displayable_ranked_content(payload)
    ranked = payload["ranked"]
    assert ranked["pipeline"]["raw_count"] >= 1


def test_intro_card_can_be_dismissed():
    session_state: dict = {}
    assert should_show_intro_card(session_state)
    dismiss_intro_card(session_state)
    assert not should_show_intro_card(session_state)
    assert session_state[INTRO_CARD_DISMISSED_KEY] is True


def test_auto_load_messages_are_recruiter_friendly():
    assert "student" in AUTO_LOAD_SPINNER_MESSAGE.lower()
    assert "$12k" in AUTO_LOAD_STATUS_MESSAGE or "12k" in AUTO_LOAD_STATUS_MESSAGE.lower()


def test_adversarial_dataset_hidden_without_developer_mode():
    keys = available_listing_dataset_keys(False)
    assert ADVERSARIAL_DATASET_KEY not in keys
    assert "basic" in keys


def test_adversarial_dataset_available_in_developer_mode():
    keys = available_listing_dataset_keys(True)
    assert ADVERSARIAL_DATASET_KEY in keys
