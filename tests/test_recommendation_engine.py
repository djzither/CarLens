import pytest

from src.recommendation.hard_filters import apply_hard_filters
from src.recommendation.recommendation_engine import recommend
from src.vehicles import load_vehicle_profiles


def _models(result: dict) -> list[str]:
    return [item["model"] for item in result["recommendations"]]


def test_student_favors_corolla_civic_mazda3_over_outback():
    result = recommend("student")
    models = _models(result)
    assert "Outback" not in models
    for model in ("Corolla", "Civic", "Mazda3"):
        assert model in models
    economy_rank = [models.index(m) for m in ("Corolla", "Civic", "Mazda3")]
    assert economy_rank == sorted(economy_rank)


def test_outdoor_snow_favors_outback_over_corolla():
    result = recommend("outdoor_snow")
    models = _models(result)
    assert models[0] == "Outback"
    assert "Corolla" not in models
    assert "Civic" not in models


def test_over_budget_vehicle_filtered_before_scoring():
    buyer = {
        "budget_type": {"type": "max_purchase", "max_amount": 5000},
        "preferred_body_types": ["sedan"],
        "hard_requirements": [],
    }
    vehicle = {
        "make": "Toyota",
        "model": "Corolla",
        "body_type": "sedan",
        "drive_type": "fwd",
        "typical_price_range": {"min": 6000, "max": 14000},
    }
    passes, reasons = apply_hard_filters(vehicle, buyer)
    assert passes is False
    assert any("budget" in reason.lower() for reason in reasons)

    vehicles_by_model = {
        v["model"]: v for v in load_vehicle_profiles()["vehicles"]
    }
    result = recommend("student")
    for item in result["recommendations"]:
        price_min = vehicles_by_model[item["model"]]["typical_price_range"]["min"]
        assert price_min <= 12000


def test_recommendations_include_positive_reasons():
    result = recommend("student")
    assert result["recommendations"]
    for item in result["recommendations"]:
        assert item["reasons"]
        assert any(reason["contribution"] > 0 for reason in item["reasons"])


def test_unknown_buyer_raises():
    with pytest.raises(ValueError, match="buyer profile not found"):
        recommend("nonexistent_buyer")
