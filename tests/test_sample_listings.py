import importlib.util
from pathlib import Path
from typing import Any

import pytest

from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
DEMO_SCRIPT = PROJECT_ROOT / "Scripts" / "demo_listing_fit.py"

EXPECTED_LISTING_IDS = [
    "good_corolla",
    "budget_boundary_corolla",
    "over_budget_corolla",
    "dirty_title_corolla",
    "out_of_range_year_corolla",
    "high_mileage_corolla",
    "stacked_risk_corolla",
    "wrong_model_bmw",
]


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("carlens_demo_listing_fit", DEMO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_student_sample_listings_file_exists():
    assert SAMPLE_LISTINGS_PATH.is_file()


def test_student_sample_listings_has_expected_scenarios():
    demo = _load_demo_module()
    buyer_profile_id, scenarios = demo.load_sample_listings(SAMPLE_LISTINGS_PATH)

    assert buyer_profile_id == "student"
    assert [name for name, _ in scenarios] == EXPECTED_LISTING_IDS
    assert scenarios[0][1]["make"] == "Toyota"
    assert scenarios[0][1]["model"] == "Corolla"


def _ranked_student_listings() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    demo = _load_demo_module()
    buyer_profile_id, scenarios = demo.load_sample_listings(SAMPLE_LISTINGS_PATH)
    buyer_data = load_buyer_profiles()
    buyer = demo._find_buyer(buyer_data["profiles"], buyer_profile_id)
    top_recommendation = recommend(buyer_profile_id)["recommendations"][0]
    return demo.score_and_rank_listings(scenarios, top_recommendation, buyer)


def _scenario_ids(
    ranked: list[tuple[str, dict[str, Any], dict[str, Any]]],
) -> list[str]:
    return [scenario_id for scenario_id, _, _ in ranked]


def _fit_by_id(
    ranked: list[tuple[str, dict[str, Any], dict[str, Any]]],
    scenario_id: str,
) -> dict[str, Any]:
    for name, _, fit in ranked:
        if name == scenario_id:
            return fit
    raise AssertionError(f"scenario not ranked: {scenario_id}")


def _rank_position(
    ranked: list[tuple[str, dict[str, Any], dict[str, Any]]],
    scenario_id: str,
) -> int:
    return _scenario_ids(ranked).index(scenario_id) + 1


@pytest.fixture
def ranked_student_listings() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    return _ranked_student_listings()


def test_good_corolla_ranks_above_over_budget_corolla(ranked_student_listings):
    assert _rank_position(ranked_student_listings, "good_corolla") < _rank_position(
        ranked_student_listings, "over_budget_corolla"
    )


def test_dirty_title_corolla_not_strong_fit_in_ranking(ranked_student_listings):
    fit = _fit_by_id(ranked_student_listings, "dirty_title_corolla")

    assert fit["fit_label"] != "Strong fit"
    assert any("clean title" in warning.lower() for warning in fit["warnings"])


def test_wrong_model_bmw_is_weak_fit_near_bottom(ranked_student_listings):
    fit = _fit_by_id(ranked_student_listings, "wrong_model_bmw")
    ids = _scenario_ids(ranked_student_listings)

    assert fit["fit_label"] == "Weak fit"
    assert any("not the recommended" in warning for warning in fit["warnings"])
    assert ids.index("wrong_model_bmw") >= len(ids) - 2


def test_stacked_risk_corolla_ranks_below_clean_in_budget_corollas(
    ranked_student_listings,
):
    stacked_rank = _rank_position(ranked_student_listings, "stacked_risk_corolla")
    for scenario_id in ("good_corolla", "budget_boundary_corolla"):
        assert stacked_rank > _rank_position(ranked_student_listings, scenario_id)


def test_budget_boundary_corolla_within_budget(ranked_student_listings):
    fit = _fit_by_id(ranked_student_listings, "budget_boundary_corolla")
    reasons_text = " ".join(fit["reasons"]).lower()
    warnings_text = " ".join(fit["warnings"]).lower()

    assert fit["fit_label"] == "Strong fit"
    assert "budget" in reasons_text
    assert "within" in reasons_text
    assert "exceeds" not in warnings_text


def test_format_ranked_summary_lists_scenarios_in_rank_order(ranked_student_listings):
    demo = _load_demo_module()
    summary = demo.format_ranked_summary(ranked_student_listings)

    assert "Ranked listings:" in summary
    ranked_ids = _scenario_ids(ranked_student_listings)
    summary_lines = [line for line in summary.splitlines() if line.strip().startswith("1.")]
    assert summary_lines
    assert ranked_ids[0] in summary_lines[0]
    for rank, scenario_id in enumerate(ranked_ids[:3], start=1):
        assert f"{rank}. {scenario_id}" in summary
