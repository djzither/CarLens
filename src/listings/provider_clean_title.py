"""Provider clean-title mapping: unknown unless explicitly stated."""

from __future__ import annotations

from typing import Any


def apply_explicit_clean_title(raw: dict[str, Any], provider_value: Any) -> None:
    """Set raw clean_title only when the provider explicitly reports true/false."""
    if provider_value is True:
        raw["clean_title"] = True
    elif provider_value is False:
        raw["clean_title"] = False


def provider_clean_title_is_unknown(raw: dict[str, Any]) -> bool:
    """True when the adapted raw listing has no explicit clean_title signal."""
    return "clean_title" not in raw
