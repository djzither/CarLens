"""CarLens Streamlit MVP — buyer profile to ranked listings."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

# Streamlit runs this file as script module "app" (`streamlit run app/app.py`), not as
# package submodule app.app. Absolute `from app.*` then re-imports this file and recurses.
# Sibling imports plus app/ on sys.path work for Streamlit and for pytest (`from app.app`).
for directory in (APP_DIR, PROJECT_ROOT):
    path_str = str(directory)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import streamlit as st

from listing_display import (
    ListingCardAlert,
    UNMATCHED_SECTION_INTRO,
    banner_alerts,
    budget_option_listing_names,
    build_listing_card_alerts,
    build_ranking_explanation_lines,
    build_watchouts,
    format_additional_notes_label,
    format_card_fit_summary,
    format_card_scoring_reasons,
    format_compact_listing_header,
    format_confidence_breakdown,
    format_listing_card_tagline,
    format_listing_data_details_lines,
    format_listing_quality_metrics,
    format_provider_attribution_html,
    format_listing_source_markdown,
    format_positive_reasons_for_display,
    format_recommended_because,
    format_summary_badge_line,
    format_title_status_block,
    filter_watchouts_for_card,
    qualifies_as_top_pick,
    resolve_listing_display_name,
    resolve_listing_quality_summary,
    resolve_listing_summary_badge,
    title_status_alert,
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
    favorite_button_key,
    generate_beats_other_sentence,
    get_saved_listing_ids,
    is_listing_saved,
    make_compare_id,
    resolve_compare_entries,
    toggle_saved_listing,
    validate_compare_selection,
)
from src.listings.listing_confidence import assess_listing_confidence
from src.listings.listing_ranker import (
    pick_best_listing,
    rank_listings_for_recommendations,
)
from src.profiles.buyer_profile_loader import load_buyer_profiles
from provider_mock_demo import (
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


def available_listing_dataset_keys(
    developer_mode: bool,
    *,
    demo_sets: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Dataset keys shown in the sidebar; adversarial requires developer mode."""
    sets = demo_sets if demo_sets is not None else DEMO_LISTING_SETS
    return [
        key
        for key in sets
        if developer_mode or key != ADVERSARIAL_DATASET_KEY
    ]
DEFAULT_BUYER_PROFILE_ID = "student"
DEFAULT_LISTING_DATASET_KEY = "basic"
AUTO_LOAD_SPINNER_MESSAGE = "Finding best student car matches..."
AUTO_LOAD_STATUS_MESSAGE = (
    "Loading a student example: $12k budget, reliable daily driver"
)
INTRO_CARD_DISMISSED_KEY = "intro_card_dismissed"
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


def build_prefs_key(
    selected_id: str,
    listing_dataset: str,
    budget_max: int,
    max_mileage: int,
    require_awd: bool,
    developer_mode: bool,
) -> tuple[Any, ...]:
    return (
        selected_id,
        listing_dataset,
        budget_max,
        max_mileage,
        require_awd,
        developer_mode,
    )


def default_prefs_key(
    profiles: list[dict[str, Any]],
    *,
    developer_mode: bool = False,
) -> tuple[Any, ...]:
    buyer = _find_buyer(profiles, DEFAULT_BUYER_PROFILE_ID)
    return build_prefs_key(
        DEFAULT_BUYER_PROFILE_ID,
        DEFAULT_LISTING_DATASET_KEY,
        int(buyer["budget_type"]["max_amount"]),
        int(buyer["max_mileage"]),
        "drive_type:awd" in buyer.get("hard_requirements", []),
        developer_mode,
    )


def build_default_ranked_payload(
    profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Student profile + basic demo dataset — used for first-visit auto-load."""
    if profiles is None:
        profiles = load_buyer_profiles()["profiles"]
    buyer = _find_buyer(profiles, DEFAULT_BUYER_PROFILE_ID)
    buyer = apply_buyer_overrides(
        buyer,
        budget_max=int(buyer["budget_type"]["max_amount"]),
        max_mileage=int(buyer["max_mileage"]),
        require_awd="drive_type:awd" in buyer.get("hard_requirements", []),
    )
    loaded = load_sample_listings(DEFAULT_LISTING_DATASET_KEY)
    listings = _listings_for_ranker(loaded)
    return run_pipeline(DEFAULT_BUYER_PROFILE_ID, buyer, listings)


def ensure_initial_ranked_payload(
    session_state: dict[str, Any],
    *,
    payload: dict[str, Any],
    prefs_key: tuple[Any, ...],
    raw_lookup: dict[str, dict[str, Any]],
    display_names: dict[str, str | None] | None,
) -> bool:
    """Populate session state on first visit. Returns True when auto-load ran."""
    if "ranked_payload" in session_state:
        return False
    session_state["ranked_payload"] = payload
    session_state["auto_loaded"] = True
    session_state["prefs_key"] = prefs_key
    session_state["compare_catalog"] = build_compare_catalog(
        payload["ranked"],
        raw_lookup,
        display_names=display_names,
    )
    return True


def should_show_intro_card(session_state: dict[str, Any]) -> bool:
    return not session_state.get(INTRO_CARD_DISMISSED_KEY, False)


def dismiss_intro_card(session_state: dict[str, Any]) -> None:
    session_state[INTRO_CARD_DISMISSED_KEY] = True


def has_displayable_ranked_content(payload: dict[str, Any]) -> bool:
    ranked = payload.get("ranked") or {}
    for group in ranked.get("groups") or []:
        if group.get("listings"):
            return True
    if ranked.get("unmatched_listings"):
        return True
    return False


def is_blank_ui_state(session_state: dict[str, Any]) -> bool:
    payload = session_state.get("ranked_payload")
    if payload is None:
        return True
    return not has_displayable_ranked_content(payload)


def render_intro_card() -> None:
    if not should_show_intro_card(st.session_state):
        return
    with st.container(border=True):
        st.markdown("### CarLens helps you decide WHAT car to buy")
        st.markdown("1. Understands buyer preferences")
        st.markdown("2. Recommends vehicle models")
        st.markdown("3. Ranks actual listings by fit + trust")
        st.markdown("4. Explains why each car does or doesn’t work")
        st.markdown("*Try changing budget or buyer profile in the sidebar.*")
        if st.button("Dismiss", key="dismiss_intro_card"):
            dismiss_intro_card(st.session_state)
            st.rerun()


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


def _render_card_alert(alert: ListingCardAlert) -> None:
    if alert.detail:
        body = f"{alert.headline}\n\n{alert.detail}"
    else:
        body = alert.headline
    if alert.tier == "red":
        st.error(body)
    elif alert.tier == "yellow":
        st.warning(body)
    else:
        st.info(body)


def _render_title_status(alert: ListingCardAlert) -> None:
    certainty = alert.group.removeprefix("title_") if alert.group.startswith("title_") else ""
    block = format_title_status_block(certainty)
    if not block:
        block = (
            alert.headline
            if not alert.detail
            else f"{alert.headline}\n\n_{alert.detail}_"
        )
    if alert.tier == "red":
        st.error(block)
    elif alert.tier == "yellow":
        st.warning(block)
    else:
        st.success(block)


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
    is_budget_option: bool = False,
) -> None:
    """Always-visible listing summary; scoring details live in an expander."""
    listing = entry["listing"]
    raw_listing = entry.get("raw_listing")
    fit = entry["fit"]
    confidence = entry["confidence"]
    display_label = resolve_listing_display_name(entry, raw_listing)
    checkbox_key = compare_checkbox_key(compare_id)
    is_selected = bool(st.session_state.get(checkbox_key))
    at_limit = selected_count >= MAX_COMPARE_LISTINGS and not is_selected

    quality = resolve_listing_quality_summary(entry)
    alerts = build_listing_card_alerts(
        entry,
        quality_summary=quality,
        confidence=confidence,
        fit=fit,
        listing=listing,
        raw_listing=raw_listing,
    )

    for alert in banner_alerts(alerts):
        _render_card_alert(alert)

    badge = resolve_listing_summary_badge(
        entry,
        rank=rank,
        is_budget_option=is_budget_option,
        alerts=alerts,
    )
    badge_line = format_summary_badge_line(badge)
    if badge_line:
        st.markdown(badge_line)

    title_line, stats_line = format_compact_listing_header(
        entry,
        rank=rank,
        raw_listing=raw_listing,
    )
    header_cols = st.columns([5, 1, 1])
    with header_cols[0]:
        st.markdown(f"**{title_line}**")
        st.markdown(
            f"<span style='color:{_fit_badge_color(fit['fit_label'])}'>"
            f"{format_card_fit_summary(fit)}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(stats_line)
        st.caption(
            format_listing_card_tagline(
                entry,
                rank=rank,
                is_budget_option=is_budget_option,
            )
        )
        st.markdown(format_listing_quality_metrics(quality))
        provider_line = format_provider_attribution_html(entry)
        if provider_line:
            st.markdown(provider_line, unsafe_allow_html=True)
        title_alert = title_status_alert(alerts)
        if title_alert is not None:
            _render_title_status(title_alert)
        for alert in alerts:
            if alert.tier == "info" and not alert.group.startswith("title_"):
                _render_card_alert(alert)
        scoring_reasons = format_card_scoring_reasons(fit)
        if scoring_reasons:
            st.markdown("**Why this score**")
            for reason in scoring_reasons:
                st.markdown(f"- {reason}")
    with header_cols[1]:
        saved = is_listing_saved(st.session_state, compare_id)
        save_label = "Saved" if saved else "Save"
        if st.button(
            save_label,
            key=favorite_button_key(compare_id),
            help="Save to favorites for this session only.",
        ):
            toggle_saved_listing(st.session_state, compare_id)
            st.rerun()
    with header_cols[2]:
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
    display_positives = format_positive_reasons_for_display(
        positives,
        make=str(listing["make"]),
        model=str(listing["model"]),
        listing=listing,
        fit=fit,
    )
    if display_positives:
        for reason in display_positives:
            st.markdown(f"- {reason}")
    else:
        st.markdown("- None")

    st.markdown("**Watchouts**")
    watchouts = build_watchouts(fit, listing, raw_listing=raw_listing)
    visible, overflow = filter_watchouts_for_card(watchouts, alerts)
    if visible:
        for item in visible:
            st.markdown(f"- {item}")
    elif not overflow:
        st.markdown("- None")
    if overflow:
        with st.expander(format_additional_notes_label(len(overflow))):
            for item in overflow:
                st.markdown(f"- {item}")

    with st.expander("Listing data details"):
        for line in format_listing_data_details_lines(quality):
            st.markdown(f"- {line}")

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

    budget_names = budget_option_listing_names(enriched_listings)
    for rank, entry in enumerate(enriched_listings, start=1):
        compare_id = make_compare_id(make, model, entry["listing_name"])
        with st.container(border=True):
            render_listing_summary(
                entry,
                rank=rank,
                compare_id=compare_id,
                selected_count=selected_count,
                is_budget_option=entry["listing_name"] in budget_names,
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
        f"{best_row['fit_quality']} fit · {best_row['data_quality']} data quality"
    )

    st.markdown("**Why this beats the other option**")
    others = [entry for entry in entries if entry is not best]
    if len(entries) == 2 and len(others) == 1:
        st.markdown(generate_beats_other_sentence(best, others[0]))
    else:
        for other in others:
            other_label = resolve_listing_display_name(
                other,
                other.get("raw_listing"),
            )
            st.markdown(
                f"- vs **{other_label}:** "
                f"{generate_beats_other_sentence(best, other)}"
            )

    header_cols = st.columns([1] + [1] * len(entries))
    header_cols[0].markdown("**Field**")
    for index, entry in enumerate(entries):
        label = resolve_listing_display_name(entry, entry.get("raw_listing"))
        header_cols[index + 1].markdown(f"**{label}**")

    for field_key, field_label in COMPARE_TABLE_ROWS:
        cols = st.columns([1] + [1] * len(entries))
        cols[0].markdown(f"**{field_label}**")
        for index, row in enumerate(rows):
            with cols[index + 1]:
                _render_compare_cell(field_key, row[field_key])

    if st.button("Clear comparison selection"):
        clear_compare_selection()
        st.rerun()


def render_buyer_context_banner(
    profile_label: str,
    *,
    budget_max: int,
    max_mileage: int,
    require_awd: bool,
) -> None:
    awd_note = " · AWD required" if require_awd else ""
    st.markdown(
        f"**Buyer profile:** {profile_label} · "
        f"**Budget:** {budget_max:,} · **Max mileage:** {max_mileage:,}{awd_note}"
    )


def render_unmatched_listings(
    unmatched: list[dict[str, Any]],
    raw_listings: dict[str, dict[str, Any]],
    *,
    display_names: dict[str, str | None] | None = None,
    selected_count: int,
) -> None:
    st.divider()
    st.subheader("Other listings (no model match)")
    st.caption(UNMATCHED_SECTION_INTRO)
    enriched = [
        _enrich_entry(entry, raw_listings, display_names=display_names)
        for entry in unmatched
    ]
    for rank, entry in enumerate(enriched, start=1):
        compare_id = make_compare_id("Other", "Unmatched", entry["listing_name"])
        with st.container(border=True):
            render_listing_summary(
                entry,
                rank=rank,
                compare_id=compare_id,
                selected_count=selected_count,
            )


def render_compare_sidebar_hint() -> None:
    selected_count = count_selected_compare(st.session_state)
    saved_count = len(get_saved_listing_ids(st.session_state))
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
    st.markdown("**Saved listings**")
    st.caption(
        f"{saved_count} saved this session"
        if saved_count
        else "Use Save on a card to favorite listings"
    )


def main() -> None:
    st.set_page_config(page_title="CarLens", page_icon="🚗", layout="wide")
    st.title("CarLens")
    st.caption("Personalized car decisions — ranked listings with explanations")
    render_intro_card()

    buyer_data = load_buyer_profiles()
    profiles = buyer_data["profiles"]
    profile_labels = {profile["id"]: profile["label"] for profile in profiles}
    profile_ids = list(profile_labels.keys())
    default_profile_index = (
        profile_ids.index(DEFAULT_BUYER_PROFILE_ID)
        if DEFAULT_BUYER_PROFILE_ID in profile_ids
        else 0
    )

    with st.sidebar:
        st.subheader("Buyer Profile")
        selected_id = st.selectbox(
            "Profile",
            profile_ids,
            index=default_profile_index,
            format_func=lambda profile_id: profile_labels[profile_id],
            label_visibility="collapsed",
        )
        base_buyer = _find_buyer(profiles, selected_id)
        default_budget = int(base_buyer["budget_type"]["max_amount"])
        default_mileage = int(base_buyer["max_mileage"])
        default_awd = "drive_type:awd" in base_buyer.get("hard_requirements", [])

        st.subheader("Budget")
        budget_max = st.slider(
            "Max purchase price",
            min_value=5_000,
            max_value=max(default_budget * 2, 30_000),
            value=default_budget,
            step=500,
        )

        st.subheader("Preferences")
        max_mileage = st.slider(
            "Max mileage",
            min_value=50_000,
            max_value=max(default_mileage + 50_000, 200_000),
            value=default_mileage,
            step=5_000,
        )
        require_awd = st.checkbox("Require AWD / 4WD", value=default_awd)

        with st.expander("Technical details", expanded=False):
            developer_mode = st.checkbox(
                "Developer mode",
                value=False,
                help=(
                    "Show adversarial stress-test dataset and demo pipeline stats."
                ),
            )
            dataset_keys = available_listing_dataset_keys(developer_mode)
            default_dataset_index = (
                dataset_keys.index(DEFAULT_LISTING_DATASET_KEY)
                if DEFAULT_LISTING_DATASET_KEY in dataset_keys
                else 0
            )
            listing_dataset = st.selectbox(
                "Listing dataset",
                dataset_keys,
                index=default_dataset_index,
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

    prefs_key = build_prefs_key(
        selected_id,
        listing_dataset,
        budget_max,
        max_mileage,
        require_awd,
        developer_mode,
    )

    if "ranked_payload" not in st.session_state:
        st.info(AUTO_LOAD_STATUS_MESSAGE)
        default_loaded = load_sample_listings(DEFAULT_LISTING_DATASET_KEY)
        default_raw_lookup = {
            item["id"]: item["listing"] for item in default_loaded
        }
        default_display_names = {
            item["id"]: item.get("display_name") for item in default_loaded
        }
        with st.spinner(AUTO_LOAD_SPINNER_MESSAGE):
            payload = build_default_ranked_payload(profiles)
        ensure_initial_ranked_payload(
            st.session_state,
            payload=payload,
            prefs_key=prefs_key,
            raw_lookup=default_raw_lookup,
            display_names=default_display_names,
        )

    needs_refresh = pipeline_clicked or st.session_state.get("prefs_key") != prefs_key
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

    render_buyer_context_banner(
        profile_labels[selected_id],
        budget_max=budget_max,
        max_mileage=max_mileage,
        require_awd=require_awd,
    )
    recommendation_result = payload.get("recommendation_result") or {}
    recommended_models = recommendation_result.get("recommendations") or []
    if recommended_models:
        model_names = [
            f"{item['make']} {item['model']}" for item in recommended_models[:5]
        ]
        st.markdown(
            "**Recommended models:** "
            + ", ".join(model_names)
            + (" …" if len(recommended_models) > 5 else "")
        )

    for group in ranked["groups"]:
        render_vehicle_section(
            group,
            raw_lookup,
            display_names=display_names,
            selected_count=selected_count,
        )

    unmatched = ranked.get("unmatched_listings") or []
    if unmatched:
        render_unmatched_listings(
            unmatched,
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


if __name__ == "__main__":
    main()
