"""Compact summaries of provider warning messages."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_OPTIONAL_MISSING_RE = re.compile(
    r":\s*missing optional\s+(?P<field>[a-z_]+)\s*$",
    re.IGNORECASE,
)
_SKIPPED_RE = re.compile(
    r":\s*skipped\s*[—\-]\s*(?P<detail>.+?)\s*$",
    re.IGNORECASE,
)
_INVALID_RECORD_RE = re.compile(r":\s*invalid record\s*[—\-]", re.IGNORECASE)

_KNOWN_PROVIDER_PREFIXES = frozenset(
    {
        "mock",
        "auto.dev",
        "marketcheck",
        "aggregated",
        "broken",
        "warn-only",
        "dup",
    }
)

_SKIPPED_FIELD_PATTERNS: tuple[tuple[str, str], ...] = (
    ("missing id or listing_id", "listing id"),
    ("missing listing_id", "listing id"),
    ("missing id", "listing id"),
    ("missing price", "price"),
    ("missing year", "year"),
    ("missing make", "make"),
    ("missing model", "model"),
)


@dataclass
class ProviderWarningSummary:
    """Grouped provider warning counts with raw messages preserved."""

    summary_lines: list[str] = field(default_factory=list)
    counts_by_category: dict[str, int] = field(default_factory=dict)
    raw_warnings: list[str] = field(default_factory=list)


def _strip_provider_prefix(message: str) -> str:
    """Remove a leading ``provider_name:`` prefix from aggregated warnings."""
    body = message.strip()
    while ": " in body:
        prefix, rest = body.split(": ", 1)
        if prefix not in _KNOWN_PROVIDER_PREFIXES and "." not in prefix:
            break
        body = rest.strip()
    return body


def _classify_warning(message: str) -> list[str]:
    """Return summary category keys triggered by one warning line."""
    body = _strip_provider_prefix(message)
    categories: list[str] = []

    optional_match = _OPTIONAL_MISSING_RE.search(body)
    if optional_match:
        field_name = optional_match.group("field").lower()
        categories.append(f"optional:{field_name}")
        return categories

    skipped_match = _SKIPPED_RE.search(body)
    if skipped_match:
        detail = skipped_match.group("detail").casefold()
        matched = False
        for pattern, label in _SKIPPED_FIELD_PATTERNS:
            if pattern in detail:
                categories.append(f"skipped:{label}")
                matched = True
        if not matched:
            categories.append("skipped:validation")
        return categories

    if _INVALID_RECORD_RE.search(body):
        categories.append("invalid_record")
        return categories

    categories.append("other")
    return categories


def _format_summary_line(category: str, count: int) -> str:
    noun = "listing" if count == 1 else "listings"
    if category.startswith("optional:"):
        field_name = category.split(":", 1)[1].replace("_", " ")
        return f"{count} {noun} missing optional {field_name}"
    if category.startswith("skipped:"):
        reason = category.split(":", 1)[1]
        if reason == "listing id":
            return f"{count} {noun} skipped for missing listing id"
        return f"{count} {noun} skipped for missing {reason}"
    if category == "invalid_record":
        return f"{count} {noun} with invalid record shape"
    return f"{count} {noun} with other provider warnings"


def _category_sort_key(category: str) -> tuple[int, str]:
    if category.startswith("skipped:"):
        return (0, category)
    if category.startswith("optional:"):
        return (1, category)
    if category == "invalid_record":
        return (2, category)
    return (3, category)


def summarize_provider_warnings(
    warnings: list[str] | None,
) -> ProviderWarningSummary:
    """Group repeated provider warnings into compact summary lines."""
    raw = list(warnings or [])
    if not raw:
        return ProviderWarningSummary(raw_warnings=[])

    counter: Counter[str] = Counter()
    for message in raw:
        categories = _classify_warning(message)
        for category in categories:
            counter[category] += 1

    ordered = sorted(counter.items(), key=lambda item: _category_sort_key(item[0]))
    summary_lines = [_format_summary_line(category, count) for category, count in ordered]
    counts_by_category = dict(ordered)

    return ProviderWarningSummary(
        summary_lines=summary_lines,
        counts_by_category=counts_by_category,
        raw_warnings=raw,
    )
