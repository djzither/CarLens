import pytest

from src.profiles.buyer_profile_loader import load_buyer_profiles
from src.recommendation.explainability import build_reasons
from src.recommendation.hard_filters import apply_hard_filters
from src.recommendation.recommendation_engine import recommend
from src.recommendation.score_calculator import calculate_score
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


def _positive_reasons(reasons: list[dict]) -> list[dict]:
    return [reason for reason in reasons if "contribution" in reason]


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


def test_weak_trait_uses_product_wording_not_raw_scores():
    buyer = {"trait_weights": {"reliable": 0.35}}
    vehicle = {
        "traits": [{"name": "reliable", "score": 0.4, "confidence": "medium"}]
    }
    reasons = build_reasons(vehicle, buyer)
    assert len(_positive_reasons(reasons)) == 1
    message = reasons[0]["message"]
    assert message == "Limited Reliability"
    assert "score" not in message.lower()
    assert "weight" not in message.lower()
    assert reasons[0]["vehicle_score"] == 0.4
    assert reasons[0]["weight"] == 0.35


def test_missing_high_weight_trait_appears_in_reasons():
    reasons = build_reasons(_vehicle_by_model("Outback"), _buyer_by_id("student"))
    missing = [r for r in reasons if r.get("type") == "missing_trait"]
    missing_traits = {r["trait"] for r in missing}
    assert "low_cost" in missing_traits
    assert "fuel_efficient" in missing_traits
    assert all(r["weight"] >= 0.20 for r in missing)
    messages = {r["trait"]: r["message"] for r in missing}
    assert messages["low_cost"] == "Limited ownership cost data"
    assert messages["fuel_efficient"] == "Limited fuel efficiency data"


def test_positive_reasons_include_contribution_values():
    reasons = build_reasons(_vehicle_by_model("Corolla"), _buyer_by_id("student"))
    positive = _positive_reasons(reasons)
    assert positive
    assert all("contribution" in reason and reason["contribution"] > 0 for reason in positive)
    contributions = [reason["contribution"] for reason in positive]
    assert contributions == sorted(contributions, reverse=True)
    assert positive[0]["message"] == "Excellent Reliability"
    assert "score" not in positive[0]["message"].lower()


def test_recommendations_include_reasons_for_each_vehicle():
    result = recommend("student")
    assert result["recommendations"]
    for item in result["recommendations"]:
        assert item["reasons"]
        positive = _positive_reasons(item["reasons"])
        assert positive
        assert any(reason["contribution"] > 0 for reason in positive)


def test_score_math_matches_weighted_trait_sum():
    buyer = _buyer_by_id("student")
    vehicle = _vehicle_by_model("Corolla")
    weights = buyer["trait_weights"]
    traits = {t["name"]: t["score"] for t in vehicle["traits"]}

    expected_score = sum(
        weights[name] * traits[name] for name in weights if name in traits
    )
    expected_max = sum(weights.values())

    result = calculate_score(vehicle, buyer)
    assert result["score"] == round(expected_score, 4)
    assert result["max_possible_score"] == round(expected_max, 4)
    assert result["normalized_score"] == round(expected_score / expected_max, 3)


def test_normalized_score_between_zero_and_one():
    result = recommend("student")
    for item in result["recommendations"]:
        assert 0.0 <= item["normalized_score"] <= 1.0
        assert item["max_possible_score"] > 0


def test_recommendations_sorted_by_normalized_score_descending():
    result = recommend("student")
    normalized_scores = [item["normalized_score"] for item in result["recommendations"]]
    assert normalized_scores == sorted(normalized_scores, reverse=True)


def test_zero_trait_weights_does_not_crash():
    buyer = {"trait_weights": {}}
    vehicle = {"traits": [{"name": "reliable", "score": 0.9, "confidence": "high"}]}
    result = calculate_score(vehicle, buyer)
    assert result["score"] == 0.0
    assert result["max_possible_score"] == 0.0
    assert result["normalized_score"] == 0.0
    assert result["matched_weight"] == 0.0
    assert result["missing_weight"] == 0.0


def test_missing_high_weight_traits_report_missing_weight():
    result = calculate_score(_vehicle_by_model("Outback"), _buyer_by_id("student"))
    assert result["missing_weight"] > 0.30
    assert result["matched_weight"] == 0.35
    assert result["missing_weight"] == round(1.0 - 0.35, 4)


def test_no_missing_traits_has_zero_missing_weight():
    result = calculate_score(_vehicle_by_model("Corolla"), _buyer_by_id("student"))
    assert result["missing_weight"] == 0.0
    assert result["matched_weight"] == result["max_possible_score"]


def test_recommendations_include_weight_coverage_fields():
    result = recommend("student")
    for item in result["recommendations"]:
        assert "matched_weight" in item
        assert "missing_weight" in item
        assert round(item["matched_weight"] + item["missing_weight"], 4) == round(
            item["max_possible_score"], 4
        )


def test_unknown_buyer_raises():
    with pytest.raises(ValueError, match="buyer profile not found"):
        recommend("nonexistent_buyer")
