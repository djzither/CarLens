"""Tests for the live inventory demo script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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
