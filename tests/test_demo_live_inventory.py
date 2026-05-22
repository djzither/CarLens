"""Tests for the live inventory demo script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_PATH = PROJECT_ROOT / "Scripts" / "demo_live_inventory.py"


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("demo_live_inventory", DEMO_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_live_inventory"] = module
    spec.loader.exec_module(module)
    return module


def test_run_live_demo_prints_pre_api_diagnostics_before_key_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("AUTODEV_API_KEY", raising=False)
    monkeypatch.delenv("AUTO_DEV_API_KEY", raising=False)
    demo = _load_demo_module()

    exit_code = demo.run_live_demo(
        buyer_profile_id="student",
        top_n=3,
        top_model_count=3,
        max_pages=1,
        page_size=10,
        fallback_min_listings=10,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Recommended models:" in captured.out
    assert "Provider queries:" in captured.out
    assert "Toyota Corolla" in captured.out
    assert "max_price=12000" in captured.out
    assert "Fallback triggered: no" in captured.out
    assert "AUTODEV_API_KEY" in captured.err


def test_show_recommendations_lists_models_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("AUTODEV_API_KEY", raising=False)
    monkeypatch.delenv("AUTO_DEV_API_KEY", raising=False)
    demo = _load_demo_module()

    exit_code = demo.run_show_recommendations(
        buyer_profile_id="student",
        top_models=3,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "no inventory search" in captured.out
    assert "1." in captured.out
    assert "Recommendation score:" in captured.out
    assert "Reasons:" in captured.out
    assert "AUTODEV_API_KEY" not in captured.err

    recommendations = recommend("student")["recommendations"][:3]
    for item in recommendations:
        assert item["make"] in captured.out
        assert item["model"] in captured.out


def test_selected_model_inventory_prints_selection_before_key_check(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("AUTODEV_API_KEY", raising=False)
    monkeypatch.delenv("AUTO_DEV_API_KEY", raising=False)
    demo = _load_demo_module()
    recommendations = recommend("student")["recommendations"]
    selected = recommendations[1]

    exit_code = demo.run_selected_model_inventory(
        buyer_profile_id="student",
        top_n=5,
        selected_model=None,
        selected_index=2,
        max_pages=1,
        page_size=10,
        fallback_min_listings=10,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"Selected model: {selected['make']} {selected['model']}" in captured.out
    assert "single recommended-model" in captured.out
    assert selected["make"] in captured.out
    assert "AUTODEV_API_KEY" in captured.err
