from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.recommendation_engine import recommend
from src.recommendation.year_range_selector import select_best_year_range
from src.vehicles import load_vehicle_profiles


def _vehicle_by_model(model: str) -> dict:
    for vehicle in load_vehicle_profiles()["vehicles"]:
        if vehicle["model"] == model:
            return vehicle
    raise AssertionError(f"vehicle not found: {model}")


def _buyer_by_id(profile_id: str) -> dict:
    for profile in load_buyer_profiles()["profiles"]:
        if profile["id"] == profile_id:
            return profile
    raise AssertionError(f"profile not found: {profile_id}")


def test_recommendation_includes_selected_year_range():
    result = recommend("student")
    for item in result["recommendations"]:
        assert "selected_year_range" in item
        assert item["selected_year_range"] is not None
        assert "start_year" in item["selected_year_range"]
        assert "end_year" in item["selected_year_range"]


def test_selects_highest_buy_confidence_range():
    buyer = _buyer_by_id("student")
    camry = _vehicle_by_model("Camry")
    selected = select_best_year_range(camry, buyer)
    assert selected is not None
    assert selected["start_year"] == 2012
    assert selected["end_year"] == 2017
    assert selected["buy_confidence"] == "high"


def test_prefers_mileage_fit_when_possible():
    buyer = {**_buyer_by_id("student"), "max_mileage": 100000}
    civic = _vehicle_by_model("Civic")
    selected = select_best_year_range(civic, buyer)
    assert selected is not None
    assert selected["start_year"] == 2016
    assert selected["end_year"] == 2021
    assert selected["buy_confidence"] == "medium"
    assert selected["known_bad_years"] == [2016]


def test_known_bad_years_included_when_present():
    buyer = {**_buyer_by_id("student"), "max_mileage": 100000}
    selected = select_best_year_range(_vehicle_by_model("Civic"), buyer)
    assert selected is not None
    assert "known_bad_years" in selected
    assert 2016 in selected["known_bad_years"]


def test_no_year_ranges_returns_none():
    vehicle = {"make": "Test", "model": "Empty", "year_ranges": []}
    buyer = _buyer_by_id("student")
    assert select_best_year_range(vehicle, buyer) is None

    vehicle_missing = {"make": "Test", "model": "Missing"}
    assert select_best_year_range(vehicle_missing, buyer) is None
