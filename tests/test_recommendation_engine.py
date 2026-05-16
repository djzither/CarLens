import pytest

from src.recommendation.hard_filters import apply_hard_filters
from src.recommendation.recommendation_engine import recommend
from src.vehicles import load_vehicle_profiles


def _models(result: dict) -> list[str]:
    return [item["model"] for item in result["recommendations"]]


def _rank_index(models: list[str], model: str) -> int:
    return models.index(model)


def test_student_includes_outback_not_filtered_by_drive_or_body():
    result = recommend("student")
    models = _models(result)
    assert "Outback" in models
    outback_filtered = [
        item
        for item in result["filtered_out"]
        if item["model"] == "Outback"
    ]
    assert not outback_filtered
    for item in outback_filtered:
        reasons = " ".join(item["exclusion_reasons"]).lower()
        assert "drive_type" not in reasons
        assert "preferred_body_types" not in reasons


def test_student_economy_cars_rank_above_outback():
    result = recommend("student")
    models = _models(result)
    outback_rank = _rank_index(models, "Outback")
    for model in ("Corolla", "Civic", "Mazda3"):
        assert model in models
        assert _rank_index(models, model) < outback_rank


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


def test_excluded_body_types_still_hard_filters():
    buyer = {
        "budget_type": {"type": "max_purchase", "max_amount": 25000},
        "excluded_body_types": ["wagon"],
        "hard_requirements": [],
    }
    vehicle = {
        "make": "Subaru",
        "model": "Outback",
        "body_type": "wagon",
        "drive_type": "awd",
        "typical_price_range": {"min": 11000, "max": 24000},
    }
    passes, reasons = apply_hard_filters(vehicle, buyer)
    assert passes is False
    assert any("excluded_body_types" in reason for reason in reasons)


def test_preferred_body_types_do_not_hard_filter():
    buyer = {
        "budget_type": {"type": "max_purchase", "max_amount": 25000},
        "preferred_body_types": ["sedan", "hatchback"],
        "hard_requirements": [],
    }
    vehicle = {
        "make": "Subaru",
        "model": "Outback",
        "body_type": "wagon",
        "drive_type": "awd",
        "typical_price_range": {"min": 11000, "max": 24000},
    }
    passes, reasons = apply_hard_filters(vehicle, buyer)
    assert passes is True
    assert reasons == []


def test_recommendations_include_positive_reasons():
    result = recommend("student")
    assert result["recommendations"]
    for item in result["recommendations"]:
        assert item["reasons"]
        assert any(reason["contribution"] > 0 for reason in item["reasons"])


def test_unknown_buyer_raises():
    with pytest.raises(ValueError, match="buyer profile not found"):
        recommend("nonexistent_buyer")
