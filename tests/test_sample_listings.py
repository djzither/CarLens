import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_LISTINGS_PATH = PROJECT_ROOT / "data" / "sample_listings" / "student_listings.json"
DEMO_SCRIPT = PROJECT_ROOT / "scripts" / "demo_listing_fit.py"

EXPECTED_LISTING_IDS = [
    "good_corolla",
    "over_budget_corolla",
    "dirty_title_corolla",
    "bad_year_corolla",
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
