from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .profile_validator import validate_vehicle_profiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_vehicle_profiles() -> dict[str, Any]:
    data = _load_json(DATA_DIR / "vehicle_profiles.json")
    return validate_vehicle_profiles(data)
