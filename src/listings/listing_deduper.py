from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

_PRICE_TOLERANCE_DOLLARS = 500
_PRICE_TOLERANCE_RATIO = 0.02
_MILEAGE_TOLERANCE_MILES = 1_000
_MILEAGE_TOLERANCE_RATIO = 0.02
_TITLE_TOKEN_JACCARD_THRESHOLD = 0.75


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_key(value: Any) -> str | None:
    text = _norm_text(value)
    return text.casefold() if text else None


def _norm_url(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    parsed = urlsplit(text.strip())
    filtered_qs = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in {"fbclid", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
    ]
    normalized = urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/"),
            "&".join(f"{key}={val}" for key, val in filtered_qs),
            "",
        )
    )
    return normalized.casefold()


def _listing_title(listing: dict[str, Any]) -> str | None:
    return _norm_text(listing.get("raw_title")) or _norm_text(listing.get("title"))


def _canonicalize_title_text(text: str) -> str:
    lowered = text.casefold()

    def _replace_k_match(match: re.Match[str]) -> str:
        digits = match.group(1).replace(",", "")
        return str(int(digits) * 1000)

    lowered = re.sub(
        r"(\d{1,3}(?:,\d{3})*|\d+)\s*k\b",
        _replace_k_match,
        lowered,
    )
    lowered = lowered.replace(",", "")
    return re.sub(r"\s+", " ", lowered).strip()


def _normalize_title_tokens(text: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", _canonicalize_title_text(text)).strip()
    if not normalized:
        return set()
    return {token for token in normalized.split() if token}


def _titles_similar(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False

    left_norm = _canonicalize_title_text(left)
    right_norm = _canonicalize_title_text(right)
    if left_norm == right_norm:
        return True
    if left_norm in right_norm or right_norm in left_norm:
        return True

    left_tokens = _normalize_title_tokens(left)
    right_tokens = _normalize_title_tokens(right)
    if not left_tokens or not right_tokens:
        return False

    union = left_tokens | right_tokens
    if not union:
        return False
    return len(left_tokens & right_tokens) / len(union) >= _TITLE_TOKEN_JACCARD_THRESHOLD


def _values_within_tolerance(
    left: int,
    right: int,
    *,
    absolute: int,
    ratio: float,
) -> bool:
    difference = abs(left - right)
    average = (left + right) / 2
    return difference <= absolute or difference <= ratio * average


def _similar_price(left: int | None, right: int | None) -> bool:
    if left is None or right is None:
        return True
    return _values_within_tolerance(
        left,
        right,
        absolute=_PRICE_TOLERANCE_DOLLARS,
        ratio=_PRICE_TOLERANCE_RATIO,
    )


def _similar_mileage(left: int | None, right: int | None) -> bool:
    if left is None or right is None:
        return True
    return _values_within_tolerance(
        left,
        right,
        absolute=_MILEAGE_TOLERANCE_MILES,
        ratio=_MILEAGE_TOLERANCE_RATIO,
    )


_DISPLAY_PASSTHROUGH_FIELDS = ("image_url", "distance_miles")


def merge_display_fields(
    primary: dict[str, Any],
    secondary: dict[str, Any],
) -> dict[str, Any]:
    """Fill missing display fields on the primary listing from a duplicate."""
    merged = dict(primary)
    for key in _DISPLAY_PASSTHROUGH_FIELDS:
        if merged.get(key) is not None:
            continue
        value = secondary.get(key)
        if value is not None:
            merged[key] = value
    return merged


def _completeness_rank(listing: dict[str, Any]) -> tuple[int, int]:
    score = 0
    if listing.get("price") is not None:
        score += 1
    if listing.get("mileage") is not None:
        score += 1
    if listing.get("clean_title") is not None:
        score += 1
    if _norm_text(listing.get("listing_url")):
        score += 1
    if _norm_text(listing.get("image_url")):
        score += 1
    if listing.get("distance_miles") is not None:
        score += 1
    title = _listing_title(listing) or ""
    return score, len(title)


def pick_more_complete_listing(
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    """Return the listing with more usable fields for scoring and display."""
    if _completeness_rank(right) > _completeness_rank(left):
        return merge_display_fields(right, left)
    return merge_display_fields(left, right)


def _same_vehicle_identity(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for field in ("make", "model", "year"):
        if field not in left or field not in right:
            return False
        if field == "year":
            if left["year"] != right["year"]:
                return False
        else:
            if _norm_key(left[field]) != _norm_key(right[field]):
                return False
    return True


def _trims_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_trim = _norm_key(left.get("trim"))
    right_trim = _norm_key(right.get("trim"))
    return bool(left_trim and right_trim and left_trim != right_trim)


def _likely_same_listing(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not _same_vehicle_identity(left, right):
        return False
    if _trims_conflict(left, right):
        return False
    if not _similar_price(left.get("price"), right.get("price")):
        return False
    if not _similar_mileage(left.get("mileage"), right.get("mileage")):
        return False
    return _titles_similar(_listing_title(left), _listing_title(right))


def _duplicate_by_url(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_url = _norm_url(left.get("listing_url"))
    right_url = _norm_url(right.get("listing_url"))
    return bool(left_url and right_url and left_url == right_url)


def _duplicate_by_source_id(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_id = _norm_key(left.get("listing_id"))
    right_id = _norm_key(right.get("listing_id"))
    left_source = _norm_key(left.get("source"))
    right_source = _norm_key(right.get("source"))
    return bool(
        left_id
        and right_id
        and left_source
        and right_source
        and left_id == right_id
        and left_source == right_source
    )


def listings_are_duplicates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Return True when two listings should be treated as the same marketplace post."""
    if _duplicate_by_url(left, right):
        return True
    if _duplicate_by_source_id(left, right):
        return True
    return _likely_same_listing(left, right)


def dedupe_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate marketplace listings, keeping the most complete record."""
    kept: list[dict[str, Any]] = []

    for listing in listings:
        duplicate_index: int | None = None
        for index, existing in enumerate(kept):
            if listings_are_duplicates(existing, listing):
                duplicate_index = index
                break

        if duplicate_index is None:
            kept.append(listing)
        else:
            kept[duplicate_index] = pick_more_complete_listing(
                kept[duplicate_index],
                listing,
            )

    return kept
