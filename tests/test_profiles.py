import pytest

from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.vehicles import load_vehicle_profiles, validate_vehicle_profiles


def _vehicle_by_model(vehicles: list[dict], model: str) -> dict:
    for vehicle in vehicles:
        if vehicle["model"] == model:
            return vehicle
    raise AssertionError(f"vehicle not found: {model}")


def _trait_names(vehicle: dict) -> set[str]:
    return {trait["name"] for trait in vehicle["traits"]}


def _profile_by_id(profiles: list[dict], profile_id: str) -> dict:
    for profile in profiles:
        if profile["id"] == profile_id:
            return profile
    raise AssertionError(f"profile not found: {profile_id}")


def test_vehicle_profiles_load_and_validate():
    data = load_vehicle_profiles()
    assert data["schema_version"] == "1.0"
    vehicles = data["vehicles"]
    assert len(vehicles) == 5
    models = {vehicle["model"] for vehicle in vehicles}
    assert models == {"Camry", "Corolla", "Civic", "Mazda3", "Outback"}


def test_buyer_profiles_load_and_validate():
    data = load_buyer_profiles()
    assert data["schema_version"] == "1.0"
    profiles = data["profiles"]
    assert len(profiles) == 2
    assert {profile["id"] for profile in profiles} == {"student", "outdoor_snow"}


def test_validation_rejects_bad_vehicle():
    bad = {
        "schema_version": "1.0",
        "vehicles": [
            {
                "make": "Toyota",
                "model": "Camry",
                "body_type": "sedan",
                "drive_type": "fwd",
                "seats": 5,
                "typical_price_range": {"min": 9000, "max": 18000},
                "traits": [{"name": "reliable", "score": 0.9, "confidence": "high"}],
                "year_ranges": [
                    {
                        "start_year": 2020,
                        "end_year": 2018,
                        "buy_confidence": "high",
                        "known_bad_years": [],
                        "mileage_min": 100000,
                        "mileage_max": 50000,
                        "notes": "bad range",
                        "risk_flags": [],
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="start_year"):
        validate_vehicle_profiles(bad)


def test_student_profile_budget_and_priorities():
    profiles = load_buyer_profiles()["profiles"]
    student = _profile_by_id(profiles, "student")
    assert student["budget_type"]["max_amount"] <= 15000
    assert student["trait_weights"]["reliable"] > student["trait_weights"]["common_parts"]
    assert "sedan" in student["preferred_body_types"]
    assert student["primary_use"] == "daily_commute"


def test_outdoor_snow_profile_priorities():
    profiles = load_buyer_profiles()["profiles"]
    outdoor = _profile_by_id(profiles, "outdoor_snow")
    assert outdoor["trait_weights"]["awd"] >= outdoor["trait_weights"]["reliable"]
    assert "winter_capable" in outdoor["trait_weights"]
    assert "cargo_space" in outdoor["trait_weights"]
    assert outdoor["primary_use"] == "snow_and_outdoor"


def test_outback_has_awd_trait():
    vehicles = load_vehicle_profiles()["vehicles"]
    outback = _vehicle_by_model(vehicles, "Outback")
    assert "awd" in _trait_names(outback)
    assert outback["drive_type"] == "awd"


def test_corolla_typical_cost_below_outback():
    vehicles = load_vehicle_profiles()["vehicles"]
    corolla = _vehicle_by_model(vehicles, "Corolla")
    outback = _vehicle_by_model(vehicles, "Outback")
    assert "low_cost" in _trait_names(corolla)
    assert corolla["typical_price_range"]["max"] < outback["typical_price_range"]["max"]


def test_student_budget_lower_than_outdoor_snow():
    profiles = load_buyer_profiles()["profiles"]
    student = _profile_by_id(profiles, "student")
    outdoor = _profile_by_id(profiles, "outdoor_snow")
    assert student["budget_type"]["max_amount"] < outdoor["budget_type"]["max_amount"]


def test_outdoor_snow_prefers_awd_student_avoids_it():
    profiles = load_buyer_profiles()["profiles"]
    student = _profile_by_id(profiles, "student")
    outdoor = _profile_by_id(profiles, "outdoor_snow")
    assert "drive_type:awd" in outdoor["hard_requirements"]
    assert "drive_type:fwd" in student["hard_requirements"]
