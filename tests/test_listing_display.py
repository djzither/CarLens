from __future__ import annotations

from app.listing_display import (
    DIRTY_TITLE_BANNER,
    SELLER_TITLE_CONFLICT_WARNING,
    WATCHOUT_MISSING_MILEAGE,
    WATCHOUT_MISSING_PRICE,
    build_watchouts,
    detect_seller_title_conflict,
    format_listing_facts,
    format_listing_source_markdown,
    format_mileage,
    format_recommended_because,
    has_major_warnings,
    listing_source_url,
    qualifies_as_top_pick,
    resolve_listing_display_name,
    top_pick_banner_text,
    warning_is_major,
)
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
    assert "Dirty title" in watchouts[0] or "clean title" in watchouts[0].casefold()


def test_dirty_title_banner_constant_is_prominent_copy():
    assert "verify title status" in DIRTY_TITLE_BANNER.casefold()


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
