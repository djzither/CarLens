"""CarLens Streamlit MVP — buyer profile to ranked listings."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from listing_display import (
    DIRTY_TITLE_BANNER,
    WATCHOUT_MISSING_MILEAGE,
    WATCHOUT_MISSING_PRICE,
    build_ranking_explanation_lines,
    build_watchouts,
    format_confidence_breakdown,
    format_listing_facts,
    format_listing_source_markdown,
    format_recommended_because,
    listing_has_missing_mileage,
    listing_has_missing_price,
    qualifies_as_top_pick,
    resolve_listing_display_name,
    top_pick_banner_text,
)
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
from app.provider_mock_demo import (
    PROVIDER_MOCK_BUYER_PROFILE_ID,
    PROVIDER_PIPELINE_STEPS,
    adapt_provider_payloads,
    display_name_lookup,
    listings_for_ranker as provider_listings_for_ranker,
    raw_listing_lookup as provider_raw_listing_lookup,
    run_provider_mock_pipeline,
)
from src.recommendation.recommendation_engine import recommend

SAMPLE_LISTINGS_DIR = PROJECT_ROOT / "data" / "sample_listings"

DEMO_LISTING_SETS: dict[str, dict[str, str]] = {
    "basic": {
        "label": "Basic Demo",
        "filename": "student_listings.json",
    },
    "messy": {
        "label": "Messy Marketplace Demo",
        "filename": "messy_marketplace_demo.json",
    },
    "adversarial": {
        "label": "Adversarial Demo",
        "filename": "adversarial_marketplace_demo.json",
    },
    "provider_mock": {
        "label": "Mock Provider Payload Demo",
        "filename": "",
    },
}

ADVERSARIAL_DATASET_KEY = "adversarial"
PROVIDER_MOCK_DATASET_KEY = "provider_mock"
ADVERSARIAL_DATASET_WARNING = (
    "Adversarial dataset: intentionally designed to stress-test trust and parsing"
)

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


def load_sample_listings(dataset_key: str) -> list[dict[str, Any]]:
    if dataset_key == PROVIDER_MOCK_DATASET_KEY:
        return adapt_provider_payloads()
    dataset = DEMO_LISTING_SETS[dataset_key]
    path = SAMPLE_LISTINGS_DIR / dataset["filename"]
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return [
        {
            "id": entry["id"],
            "listing": entry["listing"],
            "display_name": entry.get("display_name"),
        }
        for entry in data["listings"]
    ]


def _listings_for_ranker(
    loaded: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    return [(item["id"], item["listing"]) for item in loaded]


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
    *,
    display_names: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    listing_name = entry["listing_name"]
    raw = raw_listings.get(listing_name, entry["listing"])
    normalized = entry["listing"]
    confidence = entry["fit"].get("confidence")
    if confidence is None:
        confidence = assess_listing_confidence(raw, normalized, fit=entry["fit"])
    display_name = (display_names or {}).get(listing_name)
    return {
        **entry,
        "raw_listing": raw,
        "confidence": confidence,
        "display_name": display_name,
    }


def build_compare_catalog(
    ranked: dict[str, Any],
    raw_listings: dict[str, dict[str, Any]],
    *,
    display_names: dict[str, str | None] | None = None,
) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}

    for group in ranked.get("groups") or []:
        make = group["make"]
        model = group["model"]
        for entry in group.get("listings") or []:
            enriched = _enrich_entry(
                entry, raw_listings, display_names=display_names
            )
            compare_id = make_compare_id(make, model, entry["listing_name"])
            enriched["compare_id"] = compare_id
            catalog[compare_id] = enriched

    for entry in ranked.get("unmatched_listings") or []:
        enriched = _enrich_entry(
            entry, raw_listings, display_names=display_names
        )
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


def render_listing_summary(
    entry: dict[str, Any],
    *,
    rank: int,
    compare_id: str,
    selected_count: int,
) -> None:
    """Always-visible listing summary; scoring details live in an expander."""
    listing = entry["listing"]
    raw_listing = entry.get("raw_listing")
    fit = entry["fit"]
    confidence = entry["confidence"]
    level = confidence["confidence_level"]
    display_label = resolve_listing_display_name(entry, raw_listing)
    checkbox_key = compare_checkbox_key(compare_id)
    is_selected = bool(st.session_state.get(checkbox_key))
    at_limit = selected_count >= MAX_COMPARE_LISTINGS and not is_selected

    if listing.get("clean_title") is False:
        st.error(DIRTY_TITLE_BANNER)
    if listing_has_missing_price(listing):
        st.warning(WATCHOUT_MISSING_PRICE)
    if listing_has_missing_mileage(listing):
        st.warning(WATCHOUT_MISSING_MILEAGE)

    header_cols = st.columns([6, 1])
    with header_cols[0]:
        st.markdown(
            f"**{rank}. {display_label}** — "
            f"<span style='color:{_CONFIDENCE_COLORS[level]}'>"
            f"{level} trust</span>",
            unsafe_allow_html=True,
        )
        if listing.get("clean_title") is not False:
            st.markdown(
                f"<span style='color:{_fit_badge_color(fit['fit_label'])}'>"
                f"{fit['fit_label']}</span>",
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

    title_text = listing.get("raw_title") or (raw_listing or {}).get("title")
    if title_text and str(title_text).strip() and str(title_text).strip() != display_label:
        st.caption(str(title_text).strip())

    st.markdown(format_listing_facts(listing))

    # TODO: Fetch listing images from marketplace sources when image pipeline exists.
    image_url = listing.get("image_url")
    if image_url:
        st.image(str(image_url))

    # TODO: Add geocoding for distance_miles when location pipeline exists.
    distance_miles = listing.get("distance_miles")
    if distance_miles is not None:
        st.caption(f"{int(distance_miles):,} mi away")

    st.markdown(format_listing_source_markdown(listing))

    st.markdown("**Why it may fit**")
    positives = fit.get("positive_reasons") or []
    if positives:
        for reason in positives:
            st.markdown(f"- {reason}")
    else:
        st.markdown("- None")

    st.markdown("**Watchouts**")
    watchouts = build_watchouts(fit, listing, raw_listing=raw_listing)
    prominent = {WATCHOUT_MISSING_PRICE, WATCHOUT_MISSING_MILEAGE}
    remaining = [item for item in watchouts if item not in prominent]
    if remaining:
        for item in remaining:
            st.markdown(f"- {item}")
    elif not (
        listing_has_missing_price(listing) or listing_has_missing_mileage(listing)
    ):
        st.markdown("- None")

    with st.expander("Scoring breakdown"):
        st.markdown(f"- Fit label: {fit.get('fit_label', '—')}")
        st.markdown(f"- Fit score (internal): {fit.get('fit_score', 0.0):.3f}")

        st.markdown("**How this listing scored**")
        for reason in fit.get("reasons") or ["(none)"]:
            st.markdown(f"- {reason}")

        if fit.get("label_was_capped"):
            st.caption(
                "Fit label was adjusted down because of title, budget, or mileage risks."
            )

        st.markdown("**Trust assessment**")
        for label, text in format_confidence_breakdown(confidence):
            st.markdown(f"- {label}: {text}")

        if listing.get("source"):
            st.caption(f"Source: {listing['source']}")


def render_vehicle_section(
    group: dict[str, Any],
    raw_listings: dict[str, dict[str, Any]],
    *,
    display_names: dict[str, str | None] | None = None,
    selected_count: int,
) -> None:
    make = group["make"]
    model = group["model"]
    recommendation = group.get("recommendation") or {}

    st.markdown(f"## {make} {model}")
    st.markdown(
        f"**Recommended because:** {format_recommended_because(recommendation)}"
    )

    listings = group.get("listings") or []
    if not listings:
        st.info(group.get("coverage_message", "No matching listings found"))
        return

    enriched_listings = [
        _enrich_entry(entry, raw_listings, display_names=display_names)
        for entry in listings
    ]
    first_entry = enriched_listings[0]
    if qualifies_as_top_pick(first_entry):
        st.markdown(
            "<span style='background:#1b7f3a;color:white;padding:4px 10px;"
            "border-radius:6px;font-weight:600'>Top pick</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"*{top_pick_banner_text(first_entry)}*")

    st.markdown("**Why this ranking?**")
    for line in build_ranking_explanation_lines():
        st.markdown(f"- {line}")

    for rank, entry in enumerate(enriched_listings, start=1):
        compare_id = make_compare_id(make, model, entry["listing_name"])
        with st.container(border=True):
            render_listing_summary(
                entry,
                rank=rank,
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

    best_label = resolve_listing_display_name(
        best,
        best.get("raw_listing"),
    )
    st.success(
        f"**Best option:** {best_label} — "
        f"{best_row['fit_label']} ({best_row['confidence']} trust)"
    )

    header_cols = st.columns([1] + [1] * len(entries))
    header_cols[0].markdown("**Field**")
    for index, entry in enumerate(entries):
        label = resolve_listing_display_name(entry, entry.get("raw_listing"))
        header_cols[index + 1].markdown(f"**{label}**")

    compare_rows = [
        row for row in COMPARE_TABLE_ROWS if row[0] not in {"score"}
    ]
    for field_key, field_label in compare_rows:
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
        developer_mode = st.checkbox(
            "Developer mode",
            value=False,
            help="Show adversarial stress-test dataset and demo pipeline stats.",
        )
        dataset_keys = [
            key
            for key in DEMO_LISTING_SETS
            if developer_mode or key != ADVERSARIAL_DATASET_KEY
        ]
        listing_dataset = st.selectbox(
            "Listing dataset",
            dataset_keys,
            format_func=lambda key: DEMO_LISTING_SETS[key]["label"],
        )

        st.divider()
        pipeline_clicked = st.button("Refresh recommendations", type="primary")
        render_compare_sidebar_hint()

    buyer = apply_buyer_overrides(
        base_buyer,
        budget_max=budget_max,
        max_mileage=max_mileage,
        require_awd=require_awd,
    )

    is_provider_mock = listing_dataset == PROVIDER_MOCK_DATASET_KEY

    try:
        loaded_listings = load_sample_listings(listing_dataset)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        st.error(f"Could not load sample listings: {exc}")
        return

    if is_provider_mock:
        listings = provider_listings_for_ranker(loaded_listings)
        raw_lookup = provider_raw_listing_lookup(loaded_listings)
        display_names = display_name_lookup(loaded_listings)
        if selected_id != PROVIDER_MOCK_BUYER_PROFILE_ID:
            st.info(
                f"Mock provider demo uses the **{PROVIDER_MOCK_BUYER_PROFILE_ID}** "
                "buyer profile for recommendations."
            )
    else:
        listings = _listings_for_ranker(loaded_listings)
        raw_lookup = {item["id"]: item["listing"] for item in loaded_listings}
        display_names = {
            item["id"]: item.get("display_name") for item in loaded_listings
        }

    prefs_key = (
        selected_id,
        listing_dataset,
        budget_max,
        max_mileage,
        require_awd,
        developer_mode,
    )
    needs_refresh = (
        pipeline_clicked
        or st.session_state.get("prefs_key") != prefs_key
        or "ranked_payload" not in st.session_state
    )
    if needs_refresh:
        with st.spinner("Running recommendation pipeline…"):
            if is_provider_mock:
                payload = run_provider_mock_pipeline(
                    PROVIDER_MOCK_BUYER_PROFILE_ID,
                    buyer,
                    loaded=loaded_listings,
                )
            else:
                payload = run_pipeline(selected_id, buyer, listings)
        st.session_state["ranked_payload"] = payload
        st.session_state["prefs_key"] = prefs_key
        st.session_state["compare_catalog"] = build_compare_catalog(
            payload["ranked"],
            raw_lookup,
            display_names=display_names,
        )

    payload = st.session_state["ranked_payload"]
    catalog = st.session_state.get("compare_catalog") or build_compare_catalog(
        payload["ranked"],
        raw_lookup,
        display_names=display_names,
    )
    selected_count = count_selected_compare(st.session_state)

    ranked = payload["ranked"]
    pipeline = ranked["pipeline"]
    if listing_dataset == ADVERSARIAL_DATASET_KEY:
        st.warning(ADVERSARIAL_DATASET_WARNING)

    if is_provider_mock:
        st.info(
            "Mock provider payload demo — nested Auto.dev and MarketCheck JSON only; "
            "no live APIs or scraping."
        )
        with st.expander("Adapter pipeline (mock payloads)"):
            for step_number, step in enumerate(PROVIDER_PIPELINE_STEPS, start=1):
                st.markdown(f"{step_number}. {step}")

    for group in ranked["groups"]:
        render_vehicle_section(
            group,
            raw_lookup,
            display_names=display_names,
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
            display_names=display_names,
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

    with st.expander("About this demo dataset"):
        if is_provider_mock:
            st.markdown("- Source: mocked `auto_dev_sample.json` + `marketcheck_sample.json`")
        st.markdown(
            f"- Listings loaded: **{pipeline['raw_count']}**"
        )
        st.markdown(
            f"- After normalization: **{pipeline['normalized_count']}**"
        )
        st.markdown(
            f"- After duplicate removal: **{pipeline['deduped_count']}**"
        )
        if developer_mode:
            st.caption(
                "Developer mode is on — adversarial dataset and internal "
                "pipeline counts are visible."
            )


main()
