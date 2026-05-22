from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

from src.listings.listing_schema import validate_listing
from src.vehicles.vehicle_profile_loader import load_vehicle_profiles

_CLEAN_TITLE_KEYWORDS = (
    "clean title",
    "clean carfax",
    "clear title",
)
_NEGATED_CLEAN_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:not|no)\s+clean\s+title\b", re.IGNORECASE),
    re.compile(r"\bclean\s+title\s*[:\-]?\s*(?:no|not)\b", re.IGNORECASE),
)

# Title-status phrases only; avoid false positives such as "flood lights" or "lemon yellow".
_DIRTY_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsalvage\s+title\b", re.IGNORECASE),
    re.compile(r"\btitle\s*:\s*salvage\b", re.IGNORECASE),
    re.compile(r"\bsalvaged\s+(?:title|vehicle|car)\b", re.IGNORECASE),
    re.compile(r"\brebuilt\s+title\b", re.IGNORECASE),
    re.compile(r"\brebuild\s+title\b", re.IGNORECASE),
    re.compile(r"\btitle\s*:\s*rebuilt\b", re.IGNORECASE),
    re.compile(r"\bflood\s+(?:damage|title|car|vehicle)\b", re.IGNORECASE),
    re.compile(r"\bflood[-\s]?damaged\b", re.IGNORECASE),
    re.compile(r"\bflooded\b", re.IGNORECASE),
    re.compile(r"\blemon\s+(?:law|title)\b", re.IGNORECASE),
    re.compile(r"\btitle\s*:\s*lemon\b", re.IGNORECASE),
    re.compile(r"\bbranded\s+title\b", re.IGNORECASE),
    re.compile(r"\bjunk\s+title\b", re.IGNORECASE),
)
_NEGATED_DIRTY_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bno\s+salvage\s+(?:title|history)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+salvage(?:\s+title)?\b", re.IGNORECASE),
    re.compile(r"\bno\s+flood\s+damage\b", re.IGNORECASE),
    re.compile(r"\bno\s+lemon\s+law\b", re.IGNORECASE),
    re.compile(r"\bno\s+branded\s+title\b", re.IGNORECASE),
)

_MODEL_TRIMS: dict[tuple[str, str], frozenset[str]] = {
    ("toyota", "corolla"): frozenset({"l", "le", "se", "xle", "s"}),
}

_MILEAGE_K_IN_TEXT_RE = re.compile(
    r"\b(\d{1,3}(?:,\d{3})*|\d+)\s*k\b(?:\s*(?:miles?|mi))?",
    re.IGNORECASE,
)
_MILEAGE_MILES_IN_TEXT_RE = re.compile(
    r"\b(\d{1,3}(?:,\d{3})+|\d{2,})\s*(?:miles?|mi)\b",
    re.IGNORECASE,
)

_MIN_LISTING_YEAR = 1980
_MIN_PLAUSIBLE_MILEAGE = 100
_MAX_PLAUSIBLE_MILEAGE = 500_000

_SERVICE_MILEAGE_TAIL_RE = re.compile(r"\s*ago\b", re.IGNORECASE)


def parse_price(value: Any) -> int | None:
    """Parse marketplace price strings into whole-dollar amounts."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None

    text = str(value).strip()
    if not text:
        return None

    cleaned = text.replace(",", "").replace("$", "").strip()
    if cleaned.isdigit():
        return int(cleaned)

    if "." in cleaned:
        dollars, cents = cleaned.split(".", 1)
        if not dollars.isdigit() or not cents.isdigit():
            return None
        if int(cents) != 0:
            return None
        return int(dollars)

    return None


def parse_mileage(value: Any) -> int | None:
    """Parse mileage strings such as '92k miles' or '92,000 mi'."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 0 else None

    text = str(value).strip().lower()
    if not text:
        return None

    k_match = re.fullmatch(
        r"(\d{1,3}(?:,\d{3})*|\d+)\s*k(?:\s*(?:miles?|mi))?",
        text,
    )
    if k_match:
        return int(k_match.group(1).replace(",", "")) * 1000

    miles_match = re.fullmatch(
        r"(\d{1,3}(?:,\d{3})*|\d+)\s*(?:miles?|mi)?",
        text,
    )
    if miles_match:
        return int(miles_match.group(1).replace(",", ""))

    if text.isdigit():
        return int(text)
    return None


@lru_cache(maxsize=1)
def _known_vehicles() -> tuple[tuple[str, str], ...]:
    vehicles = load_vehicle_profiles()["vehicles"]
    ordered = sorted(
        ((vehicle["make"], vehicle["model"]) for vehicle in vehicles),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    return tuple(ordered)


@lru_cache(maxsize=1)
def _canonical_make_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for make, _model in _known_vehicles():
        names.setdefault(make.casefold(), make)
    return names


def _normalize_make(make: str) -> str:
    stripped = make.strip()
    if not stripped:
        return stripped
    return _canonical_make_names().get(stripped.casefold(), stripped)


def _max_allowed_year() -> int:
    return date.today().year + 1


def _validate_year(year: int) -> int:
    max_year = _max_allowed_year()
    if year < _MIN_LISTING_YEAR or year > max_year:
        raise ValueError(
            f"listing.year must be between {_MIN_LISTING_YEAR} and {max_year}"
        )
    return year


def _looks_like_vehicle_year(value: int) -> bool:
    return _MIN_LISTING_YEAR <= value <= _max_allowed_year()


def _mileage_for_normalized_listing(parsed: int | None) -> int | None:
    if parsed is None:
        return None
    if parsed < _MIN_PLAUSIBLE_MILEAGE or parsed > _MAX_PLAUSIBLE_MILEAGE:
        return None
    if _looks_like_vehicle_year(parsed):
        return None
    return parsed


def _is_service_history_mileage_match(text: str, match: re.Match[str]) -> bool:
    start, end = match.span()
    tail = text[end : end + 16]
    before = text[max(0, start - 40) : start].casefold()

    if _SERVICE_MILEAGE_TAIL_RE.match(tail):
        return True
    if re.search(r"\bevery\s*$", before.rstrip()) or before.rstrip().endswith("every"):
        return True
    return False


def _mileage_candidates_from_text(text: str) -> list[int]:
    candidates: list[int] = []
    for pattern in (_MILEAGE_K_IN_TEXT_RE, _MILEAGE_MILES_IN_TEXT_RE):
        for match in pattern.finditer(text):
            if _is_service_history_mileage_match(text, match):
                continue
            parsed = parse_mileage(match.group(0))
            if parsed is not None:
                candidates.append(parsed)
    return candidates


def extract_year_make_model(title: str) -> dict[str, int | str | None]:
    """Extract year, make, and model from a listing title when present."""
    if not title or not str(title).strip():
        return {"year": None, "make": None, "model": None}

    text = str(title).strip()
    title_lower = text.casefold()
    best_make: str | None = None
    best_model: str | None = None
    best_model_len = 0
    make_pos = -1

    for make, model in _known_vehicles():
        make_lower = make.casefold()
        model_lower = model.casefold()
        found_make_pos = title_lower.find(make_lower)
        model_pos = title_lower.find(model_lower)
        if found_make_pos == -1 or model_pos == -1 or model_pos <= found_make_pos:
            continue
        if len(model_lower) > best_model_len:
            best_make = make
            best_model = model
            best_model_len = len(model_lower)
            make_pos = found_make_pos

    year: int | None = None
    if make_pos >= 0:
        prefix = text[:make_pos]
        year_matches = list(re.finditer(r"\b((?:19|20)\d{2})\b", prefix))
        if year_matches:
            year = int(year_matches[-1].group(1))

    if year is None:
        leading_year = re.match(r"^\s*((?:19|20)\d{2})\b", text)
        if leading_year:
            year = int(leading_year.group(1))
        else:
            embedded_year = re.search(r"\b((?:19|20)\d{2})\b", text)
            if embedded_year:
                year = int(embedded_year.group(1))

    return {"year": year, "make": best_make, "model": best_model}


def extract_trim(title: str, make: str, model: str) -> str | None:
    """Extract a known trim token from a listing title."""
    if not title or not make or not model:
        return None

    known_trims = _MODEL_TRIMS.get((make.strip().casefold(), model.strip().casefold()))
    if not known_trims:
        return None

    title_lower = str(title).casefold()
    model_lower = model.strip().casefold()
    model_pos = title_lower.find(model_lower)
    if model_pos == -1:
        return None

    remainder = title_lower[model_pos + len(model_lower) :]
    for trim in sorted(known_trims, key=len, reverse=True):
        pattern = rf"\b{re.escape(trim)}\b"
        match = re.search(pattern, remainder)
        if match:
            return trim.upper()
    return None


def _has_dirty_title_signal(text: str) -> bool:
    if any(pattern.search(text) for pattern in _NEGATED_DIRTY_TITLE_PATTERNS):
        return False
    return any(pattern.search(text) for pattern in _DIRTY_TITLE_PATTERNS)


def detect_clean_title(title: str | None, description: str | None) -> bool | None:
    """Infer title status from title and description text."""
    combined = " ".join(
        part.strip()
        for part in (title, description)
        if part and str(part).strip()
    )
    if not combined:
        return None

    if _has_dirty_title_signal(combined):
        return False

    if any(pattern.search(combined) for pattern in _NEGATED_CLEAN_TITLE_PATTERNS):
        return False

    combined_lower = combined.casefold()
    for keyword in _CLEAN_TITLE_KEYWORDS:
        if keyword in combined_lower:
            return True

    return None


def _coerce_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"{field} must be an integer")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    raise ValueError("listing.clean_title must be a boolean")


def _mileage_from_text(text: str) -> int | None:
    candidates = _mileage_candidates_from_text(text)
    if not candidates:
        return None
    distinct = set(candidates)
    if len(distinct) > 1:
        return None
    return candidates[0]


def _resolved_title(raw: dict[str, Any]) -> str | None:
    for key in ("title", "raw_title"):
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    target[key] = value


_ALLOWED_IMAGE_URL_SCHEMES = frozenset({"http", "https"})


def sanitize_image_url(value: Any) -> str | None:
    """Return image_url only for safe http(s) URLs."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    scheme = urlsplit(text).scheme.casefold()
    if scheme not in _ALLOWED_IMAGE_URL_SCHEMES:
        return None
    return text


def normalize_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Coerce raw marketplace listings into the canonical listing schema."""
    if not isinstance(listing, dict):
        raise ValueError("listing must be a JSON object")

    raw = dict(listing)
    title = _resolved_title(raw)
    description = raw.get("description")
    description_text = (
        str(description).strip()
        if description is not None and str(description).strip()
        else None
    )

    extracted = extract_year_make_model(title) if title else {"year": None, "make": None, "model": None}

    make = str(raw["make"]).strip() if raw.get("make") else extracted.get("make")
    model = str(raw["model"]).strip() if raw.get("model") else extracted.get("model")
    if not make or not model:
        raise ValueError("listing.make and listing.model are required")

    make = _normalize_make(make)

    if "year" in raw and raw["year"] is not None:
        year = _validate_year(_coerce_int(raw["year"], "listing.year"))
    elif extracted.get("year") is not None:
        year = _validate_year(int(extracted["year"]))
    else:
        raise ValueError("listing missing fields: ['year']")

    normalized: dict[str, Any] = {
        "make": make,
        "model": model,
        "year": year,
    }

    listing_id = raw.get("listing_id", raw.get("id"))
    _set_if_present(normalized, "listing_id", listing_id)
    _set_if_present(normalized, "source", raw.get("source"))
    _set_if_present(normalized, "listing_url", raw.get("listing_url"))
    if title:
        normalized["raw_title"] = title

    if "price" in raw and raw["price"] is not None:
        parsed_price = parse_price(raw["price"])
        if parsed_price is not None:
            normalized["price"] = parsed_price
    if "mileage" in raw and raw["mileage"] is not None:
        stored_mileage = _mileage_for_normalized_listing(parse_mileage(raw["mileage"]))
        if stored_mileage is not None:
            normalized["mileage"] = stored_mileage
    elif title:
        stored_mileage = _mileage_for_normalized_listing(_mileage_from_text(title))
        if stored_mileage is not None:
            normalized["mileage"] = stored_mileage

    if "trim" in raw and raw["trim"] is not None:
        trim = str(raw["trim"]).strip()
        if trim:
            normalized["trim"] = trim
    elif title:
        trim = extract_trim(title, make, model)
        if trim:
            normalized["trim"] = trim

    title_status = raw.get("title_status")
    if title_status is not None and str(title_status).strip():
        normalized["title_status"] = str(title_status).strip().casefold()

    source = str(raw.get("source", "")).strip().casefold()
    if "clean_title" in raw and raw["clean_title"] is not None:
        normalized["clean_title"] = _coerce_bool(raw["clean_title"])
    elif source != "auto.dev":
        inferred_title = detect_clean_title(title, description_text)
        if inferred_title is not None:
            normalized["clean_title"] = inferred_title

    if "location" in raw and raw["location"] is not None:
        location = str(raw["location"]).strip()
        if location:
            normalized["location"] = location
    if "drive_type" in raw and raw["drive_type"] is not None:
        drive_type = str(raw["drive_type"]).strip()
        if drive_type:
            normalized["drive_type"] = drive_type.casefold()

    image_url = sanitize_image_url(raw.get("image_url"))
    if image_url is not None:
        normalized["image_url"] = image_url
    if raw.get("distance_miles") is not None and not isinstance(
        raw.get("distance_miles"), bool
    ):
        distance = raw["distance_miles"]
        if isinstance(distance, int):
            normalized["distance_miles"] = distance
        elif isinstance(distance, float) and distance >= 0:
            normalized["distance_miles"] = int(round(distance))

    return validate_listing(normalized)
