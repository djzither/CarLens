"""Smoke tests for mocked provider payload → UI-ready ranked listings."""

from __future__ import annotations

from app.provider_mock_demo import (
    PROVIDER_MOCK_BUYER_PROFILE_ID,
    adapt_provider_payloads,
    first_ui_ready_listing,
    normalized_listings_from_provider_mock,
    run_provider_mock_pipeline,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles


def _student_buyer() -> dict:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == PROVIDER_MOCK_BUYER_PROFILE_ID:
            return profile
    raise AssertionError("student buyer profile not found")


def test_mocked_provider_payload_produces_ranked_listing():
    buyer = _student_buyer()
    payload = run_provider_mock_pipeline(PROVIDER_MOCK_BUYER_PROFILE_ID, buyer)
    ranked = payload["ranked"]

    assert ranked["pipeline"]["raw_count"] >= 2
    assert ranked["pipeline"]["deduped_count"] >= 1

    total_ranked = sum(
        len(group.get("listings") or []) for group in ranked.get("groups") or []
    )
    assert total_ranked >= 1


def test_listing_url_image_url_distance_survive_to_ui_ready_object():
    buyer = _student_buyer()
    payload = run_provider_mock_pipeline(PROVIDER_MOCK_BUYER_PROFILE_ID, buyer)
    listing = first_ui_ready_listing(payload)

    assert listing is not None
    assert listing.get("listing_url", "").startswith("https://")
    assert listing.get("image_url", "").startswith("https://")
    assert listing.get("distance_miles") is not None

    normalized = normalized_listings_from_provider_mock()
    assert any(
        item.get("listing_url") and item.get("image_url") and item.get("distance_miles")
        for item in normalized
    )


def test_adapted_payloads_are_flat_carlens_raw_shape():
    loaded = adapt_provider_payloads()
    assert len(loaded) >= 2
    for item in loaded:
        raw = item["listing"]
        assert "vehicle" not in raw
        assert "retailListing" not in raw
        assert "build" not in raw
        assert raw.get("source") in {"auto.dev", "marketcheck"}
