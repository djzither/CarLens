from __future__ import annotations

from app.listing_display import (
    DIRTY_TITLE_BANNER,
    SELLER_TITLE_CONFLICT_WARNING,
    SUMMARY_BADGE_BUDGET,
    SUMMARY_BADGE_CAUTION,
    SUMMARY_BADGE_TOP_PICK,
    STRONG_FIT_LOW_CONFIDENCE_CAPTION,
    STRONG_FIT_LOW_CONFIDENCE_HEADLINE,
    AUTO_DEV_TITLE_UNKNOWN_DETAIL,
    TITLE_DIRTY_HEADLINE,
    TITLE_UNKNOWN_HEADLINE,
    CAUTION_PREFIX,
    WATCHOUT_MISSING_MILEAGE,
    WATCHOUT_MISSING_PRICE,
    WATCHOUT_VERIFY_TITLE,
    format_caution_warning,
    banner_alerts,
    build_listing_card_alerts,
    build_watchouts,
    budget_option_listing_names,
    detect_seller_title_conflict,
    UNMATCHED_SECTION_INTRO,
    format_card_fit_summary,
    format_card_scoring_reasons,
    format_compact_listing_header,
    format_listing_card_tagline,
    format_listing_data_details_lines,
    format_listing_facts,
    format_listing_quality_metrics,
    format_provider_attribution_html,
    format_listing_source_markdown,
    format_title_status_block,
    format_trust_with_explanation,
    filter_watchouts_for_card,
    format_additional_notes_label,
    resolve_listing_quality_summary,
    title_status_alert,
    format_mileage,
    format_positive_reason_display,
    format_positive_reasons_for_display,
    format_recommended_because,
    format_summary_badge_line,
    has_major_warnings,
    listing_source_url,
    qualifies_as_top_pick,
    resolve_listing_display_name,
    resolve_listing_summary_badge,
    shows_strong_fit_low_confidence_warning,
    top_pick_banner_text,
    warning_is_major,
)
from src.listings.listing_reasons import STRONG_MODEL_MATCH
from src.listings.listing_fit import (
    DIRTY_TITLE_WARNING,
    MISSING_MILEAGE_WARNING,
    MISSING_PRICE_WARNING,
)


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


def test_format_listing_facts_omits_dirty_title_from_facts_row():
    listing = _strong_entry(clean_title=False)["listing"]
    facts = format_listing_facts(listing)
    assert "Dirty title" not in facts
    assert "$9,500" in facts


def test_format_listing_facts_omits_missing_price_and_mileage():
    listing = {
        "year": 2016,
        "make": "Toyota",
        "model": "Corolla",
        "clean_title": True,
    }
    facts = format_listing_facts(listing)
    assert "Price not listed" not in facts
    assert "Mileage not listed" not in facts


def test_format_recommended_because_uses_traits():
    recommendation = {
        "make": "Toyota",
        "model": "Corolla",
        "reasons": [
            {"trait": "reliable", "contribution": 0.2},
            {"type": "missing_trait", "trait": "awd", "message": "Limited"},
        ],
    }
    assert format_recommended_because(recommendation) == "reliable"


def test_format_recommended_because_never_uses_circular_fallback():
    recommendation = {
        "make": "Toyota",
        "model": "Corolla",
        "reasons": [],
        "selected_year_range": {"start_year": 2014, "end_year": 2019},
    }
    text = format_recommended_because(recommendation)
    assert "matches your buyer profile" not in text.casefold()
    assert len(text) > 10


def test_format_recommended_because_prefers_recommendation_notes():
    recommendation = {
        "make": "Toyota",
        "model": "Corolla",
        "notes": "Budget-friendly commuter with low ownership costs.",
        "reasons": [{"trait": "reliable", "contribution": 0.2}],
    }
    assert (
        format_recommended_because(recommendation)
        == "Budget-friendly commuter with low ownership costs."
    )


def test_resolve_listing_display_name_uses_title_not_internal_id():
    entry = {
        "listing_name": "adv_parser_price_drop_corolla",
        "listing": {
            "year": 2016,
            "make": "Toyota",
            "model": "Corolla",
            "raw_title": "PRICE DROP 2022!!! 2016 Toyota Corolla LE",
        },
    }
    assert (
        resolve_listing_display_name(entry)
        == "PRICE DROP 2022!!! 2016 Toyota Corolla LE"
    )


def test_resolve_listing_display_name_prefers_display_name_field():
    entry = {
        "listing_name": "adv_test",
        "display_name": "2016 Toyota Corolla LE — demo card",
        "listing": {"year": 2016, "make": "Toyota", "model": "Corolla"},
    }
    assert resolve_listing_display_name(entry) == "2016 Toyota Corolla LE — demo card"


def test_detect_seller_title_conflict():
    raw = {
        "title": "2016 Toyota Corolla SE clean title",
        "description": "salvage title rebuilt — runs great",
    }
    assert detect_seller_title_conflict(raw, {"clean_title": False}) is True


def test_build_watchouts_includes_seller_conflict():
    entry = _strong_entry()
    raw = {
        "title": "2016 Toyota Corolla SE clean title",
        "description": "salvage title rebuilt",
    }
    watchouts = build_watchouts(entry["fit"], entry["listing"], raw_listing=raw)
    assert SELLER_TITLE_CONFLICT_WARNING in watchouts


def test_build_watchouts_includes_missing_price():
    entry = _strong_entry()
    entry["listing"].pop("price")
    entry["fit"]["warnings"] = [MISSING_PRICE_WARNING]

    watchouts = build_watchouts(entry["fit"], entry["listing"])

    assert watchouts == [WATCHOUT_MISSING_PRICE]


def test_build_watchouts_includes_missing_mileage():
    entry = _strong_entry()
    entry["listing"].pop("mileage")
    entry["fit"]["warnings"] = [MISSING_MILEAGE_WARNING]

    watchouts = build_watchouts(entry["fit"], entry["listing"])

    assert watchouts == [WATCHOUT_MISSING_MILEAGE]


def test_missing_mileage_watchout_uses_caution_prefix():
    assert WATCHOUT_MISSING_MILEAGE.startswith(CAUTION_PREFIX)
    assert "Mileage not listed" in WATCHOUT_MISSING_MILEAGE


def test_title_watchout_uses_caution_prefix():
    assert WATCHOUT_VERIFY_TITLE.startswith(CAUTION_PREFIX)
    assert WATCHOUT_VERIFY_TITLE.endswith("Verify title before purchase")
    assert format_summary_badge_line(SUMMARY_BADGE_CAUTION) == WATCHOUT_VERIFY_TITLE


def test_build_watchouts_dedupes_price_and_negative_reasons():
    entry = _strong_entry()
    entry["listing"].pop("price")
    entry["fit"]["warnings"] = [MISSING_PRICE_WARNING]
    entry["fit"]["negative_reasons"] = ["Over budget by $2,000"]

    watchouts = build_watchouts(entry["fit"], entry["listing"])

    assert watchouts[0] == WATCHOUT_MISSING_PRICE
    assert "Over budget" in watchouts[1]
    assert MISSING_PRICE_WARNING not in watchouts
    assert len(watchouts) == 2


def test_build_watchouts_combines_warnings_and_negatives_without_dupes():
    entry = _strong_entry()
    entry["fit"]["warnings"] = [DIRTY_TITLE_WARNING]
    entry["fit"]["negative_reasons"] = ["Dirty title"]

    watchouts = build_watchouts(entry["fit"], entry["listing"])

    assert len(watchouts) == 1
    assert watchouts[0].startswith(CAUTION_PREFIX)
    assert watchouts[0] == WATCHOUT_VERIFY_TITLE


def test_dirty_title_banner_matches_caution_title_warning():
    assert DIRTY_TITLE_BANNER == WATCHOUT_VERIFY_TITLE
    assert DIRTY_TITLE_BANNER.startswith(CAUTION_PREFIX)


def test_listing_source_url_requires_http_scheme():
    listing = {"listing_url": "https://demo.carlens.local/listing/1"}
    assert listing_source_url(listing) == "https://demo.carlens.local/listing/1"
    assert listing_source_url({"listing_url": "not-a-url"}) is None
    assert listing_source_url({}) is None


def test_format_listing_source_markdown_view_listing():
    listing = {"listing_url": "https://demo.carlens.local/listing/1"}
    assert format_listing_source_markdown(listing) == (
        "[View listing](https://demo.carlens.local/listing/1)"
    )


def test_format_listing_source_markdown_without_url():
    assert format_listing_source_markdown({}) == "No source link"


def test_strong_fit_low_confidence_triggers_warning():
    fit = {"fit_label": "Strong fit"}
    confidence = {"confidence_level": "Low"}
    assert shows_strong_fit_low_confidence_warning(fit, confidence) is True
    assert STRONG_FIT_LOW_CONFIDENCE_HEADLINE.startswith("⚠")


def test_strong_fit_high_confidence_does_not_trigger_warning():
    fit = {"fit_label": "Strong fit"}
    confidence = {"confidence_level": "High"}
    assert shows_strong_fit_low_confidence_warning(fit, confidence) is False


def test_moderate_fit_low_confidence_does_not_trigger_strong_fit_warning():
    fit = {"fit_label": "Moderate fit"}
    confidence = {"confidence_level": "Low"}
    assert shows_strong_fit_low_confidence_warning(fit, confidence) is False


def test_format_listing_source_markdown_shows_source_label():
    listing = {"source": "facebook_marketplace"}
    text = format_listing_source_markdown(listing)
    assert "Facebook Marketplace" in text
    assert "good_corolla" not in text


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


def test_format_positive_reason_display_humanizes_strong_model_match():
    listing = {"year": 2016, "make": "Toyota", "model": "Corolla", "price": 9_500}
    text = format_positive_reason_display(
        STRONG_MODEL_MATCH,
        make="Toyota",
        model="Corolla",
        listing=listing,
    )
    assert "Toyota Corolla" in text
    assert "strong match" in text.casefold()
    assert STRONG_MODEL_MATCH not in text


def test_format_positive_reasons_for_display_includes_rationale():
    entry = _strong_entry()
    listing = entry["listing"]
    lines = format_positive_reasons_for_display(
        ["Under budget", STRONG_MODEL_MATCH],
        make="Toyota",
        model="Corolla",
        listing=listing,
        fit=entry["fit"],
    )
    assert len(lines) >= 2
    assert any("budget" in line.casefold() for line in lines)
    assert not any(line == STRONG_MODEL_MATCH for line in lines)
    assert not any(line == "Under budget" for line in lines)


def test_resolve_summary_badge_top_pick_for_rank_one_strong_entry():
    entry = _strong_entry()
    badge = resolve_listing_summary_badge(entry, rank=1)
    assert badge == SUMMARY_BADGE_TOP_PICK
    assert "TOP PICK" in format_summary_badge_line(badge)


def test_resolve_summary_badge_caution_for_dirty_title():
    entry = _strong_entry(clean_title=False)
    entry["listing"]["clean_title"] = False
    entry["fit"]["warnings"] = []
    quality = resolve_listing_quality_summary(entry)
    alerts = build_listing_card_alerts(entry, quality_summary=quality)
    badge = resolve_listing_summary_badge(entry, rank=2, alerts=alerts)
    assert badge is None
    assert title_status_alert(alerts) is not None
    assert TITLE_DIRTY_HEADLINE in format_title_status_block("dirty")


def test_budget_option_listing_names_picks_lowest_strong_under_budget():
    low = _strong_entry()
    low["listing_name"] = "low"
    low["listing"]["price"] = 8_000
    high = _strong_entry()
    high["listing_name"] = "high"
    high["listing"]["price"] = 11_000
    names = budget_option_listing_names([low, high])
    assert names == {"low"}


def test_resolve_summary_badge_budget_option_when_flagged():
    entry = _strong_entry()
    entry["listing_name"] = "budget"
    badge = resolve_listing_summary_badge(
        entry,
        rank=2,
        is_budget_option=True,
    )
    assert badge == SUMMARY_BADGE_BUDGET


def test_format_compact_listing_header_matches_expected_shape():
    entry = _strong_entry()
    title_line, stats_line = format_compact_listing_header(entry, rank=1)
    assert title_line.startswith("#1 ")
    assert "Toyota" in title_line
    assert "High trust (all core fields provided)" in stats_line
    assert "$" in stats_line
    assert "% fit" not in stats_line


def test_format_trust_with_explanation_medium_title_unavailable():
    confidence = {
        "confidence_level": "Medium",
        "missing_fields": ["clean_title"],
        "inferred_fields": [],
    }
    assert format_trust_with_explanation(confidence) == "Medium trust (title unavailable)"


def test_format_trust_with_explanation_medium_mileage_inferred():
    confidence = {
        "confidence_level": "Medium",
        "missing_fields": [],
        "inferred_fields": ["mileage"],
    }
    assert format_trust_with_explanation(confidence) == "Medium trust (mileage inferred)"


def test_format_trust_with_explanation_low_multiple_missing():
    confidence = {
        "confidence_level": "Low",
        "missing_fields": ["price", "mileage"],
        "inferred_fields": [],
    }
    assert format_trust_with_explanation(confidence) == "Low trust (multiple missing fields)"


def test_format_card_fit_summary_includes_label_and_score():
    entry = _strong_entry()
    summary = format_card_fit_summary(entry["fit"])
    assert "Strong fit" in summary
    assert "91%" in summary
    assert "score" in summary.casefold()


def test_format_card_scoring_reasons_returns_scoring_rationale():
    entry = _strong_entry()
    entry["fit"]["reasons"] = ["Strong model match", "Within budget tolerance"]
    reasons = format_card_scoring_reasons(entry["fit"])
    assert len(reasons) == 2
    assert "Strong model match" in reasons[0]


def test_unmatched_section_intro_is_clear():
    assert "did not match" in UNMATCHED_SECTION_INTRO.casefold()


def test_format_listing_card_tagline_for_top_pick():
    entry = _strong_entry()
    tagline = format_listing_card_tagline(entry, rank=1)
    assert "top overall" in tagline.casefold()
    assert len(tagline) > 20


def test_format_listing_quality_metrics_separates_fit_and_data() -> None:
    entry = _strong_entry()
    entry["listing"]["source"] = "mock"
    entry["provider_name"] = "mock"
    entry["provider_raw_fields"] = [
        "make",
        "model",
        "year",
        "price",
        "mileage",
        "clean_title",
    ]
    summary = resolve_listing_quality_summary(entry)
    metrics = format_listing_quality_metrics(summary)

    assert "**Fit:** Strong" in metrics
    assert "**Data quality:** High" in metrics
    assert "**Source:**" not in metrics
    assert "**Title:**" not in metrics

    entry["provider_name"] = "marketcheck"
    html = format_provider_attribution_html(entry)
    assert html is not None
    assert "via MarketCheck" in html


def test_strong_fit_medium_data_quality_on_card_entry() -> None:
    entry = _strong_entry()
    entry["listing"].pop("clean_title", None)
    entry["provider_raw_fields"] = [
        "make",
        "model",
        "year",
        "price",
        "mileage",
    ]
    summary = resolve_listing_quality_summary(entry)

    assert summary["fit_quality"] == "strong"
    assert summary["data_quality_level"] == "medium"
    assert summary["title_certainty"] == "unknown"


def test_weak_fit_high_data_quality_on_card_entry() -> None:
    entry = _strong_entry()
    entry["fit"]["fit_label"] = "Weak fit"
    entry["provider_raw_fields"] = [
        "make",
        "model",
        "year",
        "price",
        "mileage",
        "clean_title",
    ]
    summary = resolve_listing_quality_summary(entry)

    assert summary["fit_quality"] == "weak"
    assert summary["data_quality_level"] == "high"


def test_title_status_blocks_dirty_vs_unknown() -> None:
    dirty_block = format_title_status_block("dirty")
    unknown_block = format_title_status_block("unknown")
    auto_dev_unknown = format_title_status_block("unknown", source="auto.dev")

    assert TITLE_DIRTY_HEADLINE in dirty_block
    assert TITLE_UNKNOWN_HEADLINE in unknown_block
    assert "dirty title" not in unknown_block.casefold()
    assert len(dirty_block) > len(unknown_block)
    assert AUTO_DEV_TITLE_UNKNOWN_DETAIL in auto_dev_unknown
    assert "Ask seller for title documentation" not in auto_dev_unknown


def test_strong_fit_with_medium_data_on_card_alerts() -> None:
    entry = _strong_entry()
    entry["listing"].pop("clean_title", None)
    entry["provider_raw_fields"] = ["make", "model", "year", "price", "mileage"]
    quality = resolve_listing_quality_summary(entry)
    alerts = build_listing_card_alerts(entry, quality_summary=quality)

    assert quality["fit_quality"] == "strong"
    assert quality["data_quality_level"] == "medium"
    assert any(alert.group == "title_unknown" for alert in alerts)
    assert not any(alert.group == "title_dirty" for alert in alerts)


def test_weak_fit_high_data_card_alerts() -> None:
    entry = _strong_entry()
    entry["fit"]["fit_label"] = "Weak fit"
    entry["provider_raw_fields"] = [
        "make",
        "model",
        "year",
        "price",
        "mileage",
        "clean_title",
    ]
    quality = resolve_listing_quality_summary(entry)
    alerts = build_listing_card_alerts(entry, quality_summary=quality)

    assert quality["fit_quality"] == "weak"
    assert quality["data_quality_level"] == "high"
    assert any(alert.group == "title_clean" for alert in alerts)


def test_banner_alerts_exclude_title_blocks() -> None:
    entry = _strong_entry(clean_title=False)
    entry["listing"]["clean_title"] = False
    quality = resolve_listing_quality_summary(entry)
    alerts = build_listing_card_alerts(entry, quality_summary=quality)

    assert title_status_alert(alerts) is not None
    assert not any(alert.group.startswith("title_") for alert in banner_alerts(alerts))


def test_filter_watchouts_caps_at_four_with_overflow() -> None:
    entry = _strong_entry()
    entry["fit"]["warnings"] = [
        "Known weak year for this model",
        "Year outside recommended range",
        "Not the recommended Honda Civic",
    ]
    entry["fit"]["negative_reasons"] = [
        "Over budget by $2,000",
        "Mileage exceeds preferred max",
        "Does not match any recommended model",
    ]
    watchouts = build_watchouts(entry["fit"], entry["listing"])
    quality = resolve_listing_quality_summary(entry)
    alerts = build_listing_card_alerts(entry, quality_summary=quality)
    visible, overflow = filter_watchouts_for_card(watchouts, alerts, max_visible=4)

    assert len(visible) == 4
    assert len(overflow) == 2
    assert format_additional_notes_label(2) == "Additional notes (2)"


def test_listing_data_details_omits_raw_provenance() -> None:
    entry = _strong_entry()
    entry["provider_raw_fields"] = ["make", "model", "year", "price", "mileage"]
    entry["provider_warnings"] = ["mock: skipped — missing listing id"]
    lines = format_listing_data_details_lines(resolve_listing_quality_summary(entry))
    joined = "\n".join(lines)

    assert "provider_raw_fields" not in joined
    assert "skipped" not in joined
    assert "Provided:" in joined
    assert "Data completeness:" in joined
