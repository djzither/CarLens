"""CarLens Streamlit MVP — buyer profile to ranked listings."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.listings.listing_confidence import assess_listing_confidence
from src.listings.listing_ranker import rank_listings_for_recommendations
from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LISTINGS_DIR = PROJECT_ROOT / "data" / "sample_listings"

_CONFIDENCE_COLORS = {
    "High": "#1b7f3a",
    "Medium": "#b8860b",
    "Low": "#b3261e",
}


def _find_buyer(profiles: list[dict[str, Any]], buyer_profile_id: str) -> dict[str, Any]:
    for profile in profiles:
        if profile["id"] == buyer_profile_id:
            return profile
    raise ValueError(f"buyer profile not found: {buyer_profile_id}")


def load_sample_listings(
    buyer_profile_id: str,
) -> list[tuple[str, dict[str, Any]]]:
    path = SAMPLE_LISTINGS_DIR / f"{buyer_profile_id}_listings.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return [(entry["id"], entry["listing"]) for entry in data["listings"]]


def apply_buyer_overrides(
    buyer: dict[str, Any],
    *,
    budget_max: int,
    max_mileage: int,
    require_awd: bool,
) -> dict[str, Any]:
    updated = copy.deepcopy(buyer)
    updated["budget_type"] = {
        **updated["budget_type"],
        "max_amount": budget_max,
    }
    updated["max_mileage"] = max_mileage
    requirements = [
        item
        for item in updated.get("hard_requirements", [])
        if item != "drive_type:awd"
    ]
    if require_awd:
        requirements.append("drive_type:awd")
    updated["hard_requirements"] = requirements
    return updated


def run_pipeline(
    buyer_profile_id: str,
    buyer: dict[str, Any],
    listings: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    result = recommend(buyer_profile_id, buyer=buyer)
    ranked = rank_listings_for_recommendations(
        listings,
        result["recommendations"],
        buyer,
    )
    return {"recommendation_result": result, "ranked": ranked}


def _enrich_entry(
    entry: dict[str, Any],
    raw_listings: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    listing_name = entry["listing_name"]
    raw = raw_listings.get(listing_name, entry["listing"])
    normalized = entry["listing"]
    confidence = assess_listing_confidence(raw, normalized, fit=entry["fit"])
    return {**entry, "raw_listing": raw, "confidence": confidence}


def _fit_badge_color(fit_label: str) -> str:
    if fit_label == "Strong fit":
        return "#1b7f3a"
    if fit_label == "Moderate fit":
        return "#b8860b"
    return "#b3261e"


def render_listing_card(
    entry: dict[str, Any],
    *,
    compare_key: str,
) -> None:
    listing = entry["listing"]
    fit = entry["fit"]
    confidence = entry["confidence"]
    level = confidence["confidence_level"]

    header_cols = st.columns([5, 1])
    with header_cols[0]:
        st.markdown(
            f"**{entry['listing_name']}** · "
            f"<span style='color:{_fit_badge_color(fit['fit_label'])}'>"
            f"{fit['fit_label']}</span> · "
            f"Score **{fit['fit_score']:.3f}** · "
            f"<span style='color:{_CONFIDENCE_COLORS[level]}'>"
            f"Confidence: {level}</span>",
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        st.checkbox("Compare", key=compare_key)

    if fit.get("warnings"):
        warning_html = " ".join(
            f"<span style='background:#fff3cd;color:#664d03;padding:2px 8px;"
            f"border-radius:4px;margin-right:4px'>{warning}</span>"
            for warning in fit["warnings"]
        )
        st.markdown(warning_html, unsafe_allow_html=True)

    reason_cols = st.columns(2)
    with reason_cols[0]:
        st.markdown("**Positive reasons**")
        for reason in fit.get("positive_reasons") or ["(none)"]:
            st.markdown(f"- {reason}")
    with reason_cols[1]:
        st.markdown("**Negative reasons**")
        negatives = fit.get("negative_reasons") or []
        if negatives:
            for reason in negatives:
                st.markdown(f"- {reason}")
        else:
            st.markdown("- (none)")

    url = listing.get("listing_url")
    if url:
        st.markdown(f"[View listing source]({url})")
    elif listing.get("source"):
        st.caption(f"Source: {listing['source']}")


def render_vehicle_section(
    group: dict[str, Any],
    raw_listings: dict[str, dict[str, Any]],
) -> None:
    make = group["make"]
    model = group["model"]
    st.subheader(f"{make} {model}")
    rec_score = group.get("recommendation_score")
    if rec_score is not None:
        st.caption(f"Model recommendation score: {rec_score:.3f}")

    listings = group.get("listings") or []
    if not listings:
        st.info(group.get("coverage_message", "No matching listings found"))
        return

    enriched = [_enrich_entry(entry, raw_listings) for entry in listings]
    for entry in enriched:
        compare_key = f"compare_{group['make']}_{group['model']}_{entry['listing_name']}"
        with st.container(border=True):
            render_listing_card(entry, compare_key=compare_key)


def render_compare_tray() -> None:
    selected: list[str] = []
    for key, value in st.session_state.items():
        if key.startswith("compare_") and value:
            selected.append(key.removeprefix("compare_"))
    if not selected:
        return
    st.divider()
    st.markdown(f"**Compare selected** ({len(selected)})")
    for name in selected:
        st.markdown(f"- `{name}`")


def main() -> None:
    st.set_page_config(page_title="CarLens", page_icon="🚗", layout="wide")
    st.title("CarLens")
    st.caption("Personalized car decisions — ranked listings with explanations")

    buyer_data = load_buyer_profiles()
    profiles = buyer_data["profiles"]
    profile_labels = {profile["id"]: profile["label"] for profile in profiles}
    profile_ids = list(profile_labels.keys())

    with st.sidebar:
        st.header("Buyer preferences")
        selected_id = st.selectbox(
            "Buyer profile",
            profile_ids,
            format_func=lambda profile_id: profile_labels[profile_id],
        )
        base_buyer = _find_buyer(profiles, selected_id)
        default_budget = int(base_buyer["budget_type"]["max_amount"])
        default_mileage = int(base_buyer["max_mileage"])
        default_awd = "drive_type:awd" in base_buyer.get("hard_requirements", [])

        budget_max = st.slider(
            "Budget (max purchase)",
            min_value=5_000,
            max_value=max(default_budget * 2, 30_000),
            value=default_budget,
            step=500,
        )
        max_mileage = st.slider(
            "Mileage preference (max)",
            min_value=50_000,
            max_value=max(default_mileage + 50_000, 200_000),
            value=default_mileage,
            step=5_000,
        )
        require_awd = st.checkbox("Require AWD / 4WD", value=default_awd)

        st.divider()
        pipeline_clicked = st.button("Refresh recommendations", type="primary")

    buyer = apply_buyer_overrides(
        base_buyer,
        budget_max=budget_max,
        max_mileage=max_mileage,
        require_awd=require_awd,
    )

    try:
        listings = load_sample_listings(selected_id)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        st.error(f"Could not load sample listings: {exc}")
        return

    raw_lookup = {name: raw for name, raw in listings}

    prefs_key = (selected_id, budget_max, max_mileage, require_awd)
    needs_refresh = (
        pipeline_clicked
        or st.session_state.get("prefs_key") != prefs_key
        or "ranked_payload" not in st.session_state
    )
    if needs_refresh:
        with st.spinner("Running recommendation pipeline…"):
            payload = run_pipeline(selected_id, buyer, listings)
        st.session_state["ranked_payload"] = payload
        st.session_state["prefs_key"] = prefs_key

    payload = st.session_state["ranked_payload"]

    ranked = payload["ranked"]
    pipeline = ranked["pipeline"]
    st.markdown(
        f"Pipeline: **{pipeline['raw_count']}** raw → "
        f"**{pipeline['normalized_count']}** normalized → "
        f"**{pipeline['deduped_count']}** deduped"
    )

    for group in ranked["groups"]:
        render_vehicle_section(group, raw_lookup)

    unmatched = ranked.get("unmatched_listings") or []
    if unmatched:
        st.divider()
        st.subheader("Unmatched listings")
        pseudo_group = {
            "make": "Other",
            "model": "models",
            "listings": unmatched,
        }
        render_vehicle_section(pseudo_group, raw_lookup)

    invalid = ranked.get("invalid_listings") or []
    if invalid:
        with st.expander("Invalid listings"):
            for entry in invalid:
                st.markdown(f"**{entry['listing_name']}**")
                for warning in entry.get("warnings", []):
                    st.markdown(f"- {warning}")

    render_compare_tray()


main()
