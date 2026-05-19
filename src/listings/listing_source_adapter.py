from __future__ import annotations

from typing import Any

AUTO_DEV_SOURCE = "auto.dev"
MARKETCHECK_SOURCE = "marketcheck"

# Internal raw listing keys consumed by normalize_listing() and the scoring pipeline.
RAW_LISTING_CORE_KEYS = frozenset(
    {
        "make",
        "model",
        "year",
        "price",
        "mileage",
        "title",
        "raw_title",
        "trim",
        "clean_title",
        "location",
        "drive_type",
        "description",
        "listing_id",
        "source",
        "listing_url",
    }
)
RAW_LISTING_PASSTHROUGH_KEYS = frozenset({"image_url", "distance_miles"})
RAW_LISTING_KEYS = RAW_LISTING_CORE_KEYS | RAW_LISTING_PASSTHROUGH_KEYS


def _nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _optional_distance_miles(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        miles = float(value)
        if miles < 0:
            return None
        return int(round(miles))
    return None


def _set_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    target[key] = value


def _compose_title(*, year: Any, make: Any, model: Any, trim: Any = None) -> str | None:
    parts: list[str] = []
    year_text = _optional_int(year)
    if year_text is not None:
        parts.append(str(year_text))
    for value in (make, model, trim):
        text = _optional_str(value)
        if text:
            parts.append(text)
    if not parts:
        return None
    return " ".join(parts)


def _format_location(city: Any, state: Any, zip_code: Any = None) -> str | None:
    city_text = _optional_str(city)
    state_text = _optional_str(state)
    zip_text = _optional_str(zip_code)
    if city_text and state_text:
        location = f"{city_text}, {state_text}"
    elif city_text:
        location = city_text
    elif state_text:
        location = state_text
    else:
        location = None
    if location and zip_text:
        return f"{location} {zip_text}"
    return location


def _normalize_drive_type(value: Any) -> str | None:
    text = _optional_str(value)
    return text.casefold() if text else None


def _first_photo_url(media: dict[str, Any]) -> str | None:
    for key in ("photo_links_cached", "photo_links"):
        links = media.get(key)
        if not isinstance(links, list):
            continue
        for link in links:
            url = _optional_str(link)
            if url:
                return url
    return None


def adapt_auto_dev_listing(provider_listing: dict[str, Any]) -> dict[str, Any]:
    """Map an Auto.dev listing object to the CarLens raw listing shape."""
    if not isinstance(provider_listing, dict):
        raise ValueError("provider_listing must be a JSON object")

    vehicle = _nested_dict(provider_listing.get("vehicle"))
    retail = _nested_dict(provider_listing.get("retailListing"))
    wholesale = _nested_dict(provider_listing.get("wholesaleListing"))
    raw: dict[str, Any] = {"source": AUTO_DEV_SOURCE}

    listing_id = _optional_str(provider_listing.get("vin")) or _optional_str(
        vehicle.get("vin")
    )
    _set_if_present(raw, "listing_id", listing_id)

    _set_if_present(raw, "make", vehicle.get("make"))
    _set_if_present(raw, "model", vehicle.get("model"))
    year = _optional_int(vehicle.get("year"))
    if year is not None:
        raw["year"] = year

    _set_if_present(raw, "trim", vehicle.get("trim"))
    _set_if_present(raw, "drive_type", _normalize_drive_type(vehicle.get("drivetrain")))

    price = retail.get("price")
    if price is not None:
        raw["price"] = price

    mileage = retail.get("miles")
    if mileage is None:
        mileage = wholesale.get("miles")
    if mileage is not None:
        raw["mileage"] = mileage

    title = _compose_title(
        year=vehicle.get("year"),
        make=vehicle.get("make"),
        model=vehicle.get("model"),
        trim=vehicle.get("trim"),
    )
    _set_if_present(raw, "title", title)

    _set_if_present(raw, "listing_url", retail.get("vdp"))
    _set_if_present(raw, "image_url", retail.get("primaryImage"))

    distance = provider_listing.get("distance")
    if distance is None:
        distance = retail.get("distance")
    distance_miles = _optional_distance_miles(distance)
    if distance_miles is not None:
        raw["distance_miles"] = distance_miles

    location = _format_location(
        retail.get("city"),
        retail.get("state"),
        retail.get("zip"),
    )
    _set_if_present(raw, "location", location)

    return raw


def adapt_marketcheck_listing(provider_listing: dict[str, Any]) -> dict[str, Any]:
    """Map a MarketCheck listing object to the CarLens raw listing shape."""
    if not isinstance(provider_listing, dict):
        raise ValueError("provider_listing must be a JSON object")

    build = _nested_dict(provider_listing.get("build"))
    dealer = _nested_dict(provider_listing.get("dealer"))
    media = _nested_dict(provider_listing.get("media"))

    raw: dict[str, Any] = {"source": MARKETCHECK_SOURCE}

    _set_if_present(
        raw,
        "listing_id",
        provider_listing.get("id") or provider_listing.get("vin"),
    )

    year = _optional_int(build.get("year") or provider_listing.get("year"))
    if year is not None:
        raw["year"] = year
    _set_if_present(raw, "make", build.get("make") or provider_listing.get("make"))
    _set_if_present(raw, "model", build.get("model") or provider_listing.get("model"))
    _set_if_present(raw, "trim", build.get("trim") or provider_listing.get("trim"))
    _set_if_present(
        raw,
        "drive_type",
        _normalize_drive_type(build.get("drivetrain")),
    )

    if provider_listing.get("price") is not None:
        raw["price"] = provider_listing["price"]
    if provider_listing.get("miles") is not None:
        raw["mileage"] = provider_listing["miles"]

    title = _optional_str(provider_listing.get("heading"))
    if title is None:
        title = _compose_title(
            year=year,
            make=raw.get("make"),
            model=raw.get("model"),
            trim=raw.get("trim"),
        )
    _set_if_present(raw, "title", title)

    _set_if_present(raw, "listing_url", provider_listing.get("vdp_url"))
    _set_if_present(raw, "image_url", _first_photo_url(media))

    distance_miles = _optional_distance_miles(provider_listing.get("dist"))
    if distance_miles is not None:
        raw["distance_miles"] = distance_miles

    location = _format_location(dealer.get("city"), dealer.get("state"), dealer.get("zip"))
    _set_if_present(raw, "location", location)

    clean_title = provider_listing.get("carfax_clean_title")
    if isinstance(clean_title, bool):
        raw["clean_title"] = clean_title

    return raw


def adapt_provider_listings(
    provider: str,
    listings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adapt a batch of provider listings."""
    if provider == AUTO_DEV_SOURCE:
        return [adapt_auto_dev_listing(item) for item in listings]
    if provider == MARKETCHECK_SOURCE:
        return [adapt_marketcheck_listing(item) for item in listings]
    raise ValueError(f"unsupported listing provider: {provider}")
