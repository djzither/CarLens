import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.recommendation.recommendation_engine import recommend

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_SCRIPT = PROJECT_ROOT / "scripts" / "demo_recommend.py"


def _load_demo_module():
    spec = importlib.util.spec_from_file_location("carlens_demo_recommend", DEMO_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


demo = _load_demo_module()


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.80, "Strong match"),
        (0.75, "Strong match"),
        (0.60, "Moderate match"),
        (0.50, "Moderate match"),
        (0.49, "Weak match"),
    ],
)
def test_match_label_thresholds(score, expected):
    assert demo.match_label(score) == expected


def test_format_human_output_for_student():
    result = recommend("student")
    text = demo.format_human_output(result)
    assert "Buyer profile: student" in text
    assert "Ranked recommendations:" in text
    assert "Corolla" in text
    assert "Strong match" in text or "Moderate match" in text
    assert "Filtered out:" not in text


def test_main_json_flag(capsys):
    assert demo.main(["student", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["buyer_profile_id"] == "student"


def test_main_unknown_profile_returns_error():
    assert demo.main(["missing_profile"]) == 1


def test_cli_student_runs():
    completed = subprocess.run(
        [sys.executable, str(DEMO_SCRIPT), "student"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "Buyer profile: student" in completed.stdout
    assert "Corolla" in completed.stdout


def test_cli_json_outputs_valid_recommend_payload():
    completed = subprocess.run(
        [sys.executable, str(DEMO_SCRIPT), "outdoor_snow", "--json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["buyer_profile_id"] == "outdoor_snow"
    assert payload["recommendations"][0]["model"] == "Outback"
