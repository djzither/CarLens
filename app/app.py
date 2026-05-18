"""CarLens Streamlit MVP — buyer profile to ranked listings."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.listings.listing_compare import (
    COMPARE_TABLE_ROWS,
    MAX_COMPARE_LISTINGS,
    MIN_COMPARE_LISTINGS,
    build_compare_row,
    collect_selected_compare_ids,
    compare_checkbox_key,
    compare_id_from_checkbox_key,
    count_selected_compare,
    make_compare_id,
    resolve_compare_entries,
    validate_compare_selection,
)
from src.listings.listing_confidence import assess_listing_confidence
from src.listings.listing_ranker import (
    pick_best_listing,
    rank_listings_for_recommendations,
)
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


def build_compare_catalog(
    ranked: dict[str, Any],
    raw_listings: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}

    for group in ranked.get("groups") or []:
        make = group["make"]
        model = group["model"]
        for entry in group.get("listings") or []:
            enriched = _enrich_entry(entry, raw_listings)
            compare_id = make_compare_id(make, model, entry["listing_name"])
            enriched["compare_id"] = compare_id
            catalog[compare_id] = enriched

    for entry in ranked.get("unmatched_listings") or []:
        enriched = _enrich_entry(entry, raw_listings)
        compare_id = make_compare_id("Other", "Unmatched", entry["listing_name"])
        enriched["compare_id"] = compare_id
        catalog[compare_id] = enriched

    return catalog


def _fit_badge_color(fit_label: str) -> str:
    if fit_label == "Strong fit":
        return "#1b7f3a"
    if fit_label == "Moderate fit":
        return "#b8860b"
    return "#b3261e"


def render_listing_card(
    entry: dict[str, Any],
    *,
    compare_id: str,
    selected_count: int,
) -> None:
    listing = entry["listing"]
    fit = entry["fit"]
    confidence = entry["confidence"]
    level = confidence["confidence_level"]
    checkbox_key = compare_checkbox_key(compare_id)
    is_selected = bool(st.session_state.get(checkbox_key))
    at_limit = selected_count >= MAX_COMPARE_LISTINGS and not is_selected

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
        st.checkbox(
            "Compare",
            key=checkbox_key,
            disabled=at_limit,
            help=(
                f"Select up to {MAX_COMPARE_LISTINGS} listings to compare."
                if at_limit
                else None
            ),
        )

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
    *,
    selected_count: int,
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

    for entry in listings:
        compare_id = make_compare_id(make, model, entry["listing_name"])
        enriched = _enrich_entry(entry, raw_listings)
        with st.container(border=True):
            render_listing_card(
                enriched,
                compare_id=compare_id,
                selected_count=selected_count,
            )


def _render_compare_cell(field_key: str, value: str) -> None:
    if field_key == "source_link" and value.startswith("http"):
        st.markdown(f"[Open listing]({value})")
    else:
        st.markdown(value.replace("\n", "  \n"))


def clear_compare_selection() -> None:
    for key in list(st.session_state.keys()):
        if compare_id_from_checkbox_key(str(key)) is not None:
            st.session_state[key] = False


def render_compare_mode(catalog: dict[str, dict[str, Any]]) -> None:
    selected_ids = collect_selected_compare_ids(st.session_state)
    if not selected_ids:
        return

    st.divider()
    st.subheader("Compare mode")
    st.caption(
        f"Select {MIN_COMPARE_LISTINGS}–{MAX_COMPARE_LISTINGS} listings using the "
        "Compare checkboxes above."
    )

    validation_error = validate_compare_selection(len(selected_ids))
    if validation_error:
        st.info(validation_error)
        if st.button("Clear comparison selection"):
            clear_compare_selection()
            st.rerun()
        return

    entries = resolve_compare_entries(catalog, selected_ids)
    rows = [build_compare_row(entry) for entry in entries]
    best = pick_best_listing(entries)
    best_row = build_compare_row(best)

    st.success(
        f"**Best option:** {best['listing_name']} — "
        f"{best_row['fit_label']} (score {best_row['score']}, "
        f"confidence {best_row['confidence']})"
    )

    header_cols = st.columns([1] + [1] * len(entries))
    header_cols[0].markdown("**Field**")
    for index, entry in enumerate(entries):
        header_cols[index + 1].markdown(f"**{entry['listing_name']}**")

    for field_key, field_label in COMPARE_TABLE_ROWS:
        cols = st.columns([1] + [1] * len(entries))
        cols[0].markdown(f"**{field_label}**")
        for index, row in enumerate(rows):
            with cols[index + 1]:
                _render_compare_cell(field_key, row[field_key])

    if st.button("Clear comparison selection"):
        clear_compare_selection()
        st.rerun()


def render_compare_sidebar_hint() -> None:
    selected_count = count_selected_compare(st.session_state)
    st.divider()
    st.markdown("**Compare mode**")
    st.caption(
        f"{selected_count} selected · choose {MIN_COMPARE_LISTINGS}–"
        f"{MAX_COMPARE_LISTINGS} listings"
    )
    if selected_count > MAX_COMPARE_LISTINGS:
        st.warning(
            f"Too many listings selected. Compare at most {MAX_COMPARE_LISTINGS}."
        )


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
        render_compare_sidebar_hint()

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
        st.session_state["compare_catalog"] = build_compare_catalog(
            payload["ranked"],
            raw_lookup,
        )

    payload = st.session_state["ranked_payload"]
    catalog = st.session_state.get("compare_catalog") or build_compare_catalog(
        payload["ranked"],
        raw_lookup,
    )
    selected_count = count_selected_compare(st.session_state)

    ranked = payload["ranked"]
    pipeline = ranked["pipeline"]
    st.markdown(
        f"Pipeline: **{pipeline['raw_count']}** raw → "
        f"**{pipeline['normalized_count']}** normalized → "
        f"**{pipeline['deduped_count']}** deduped"
    )

    for group in ranked["groups"]:
        render_vehicle_section(
            group,
            raw_lookup,
            selected_count=selected_count,
        )

    unmatched = ranked.get("unmatched_listings") or []
    if unmatched:
        st.divider()
        st.subheader("Unmatched listings")
        pseudo_group = {
            "make": "Other",
            "model": "Unmatched",
            "listings": unmatched,
        }
        render_vehicle_section(
            pseudo_group,
            raw_lookup,
            selected_count=selected_count,
        )

    invalid = ranked.get("invalid_listings") or []
    if invalid:
        with st.expander("Invalid listings"):
            for entry in invalid:
                st.markdown(f"**{entry['listing_name']}**")
                for warning in entry.get("warnings", []):
                    st.markdown(f"- {warning}")

    render_compare_mode(catalog)


main()
