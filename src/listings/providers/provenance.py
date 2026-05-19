"""Provider provenance metadata for listing search results."""

from __future__ import annotations

from typing import Any

_PROVIDER_URL_FIELDS = ("listing_url", "source_url", "vdp_url", "url")


def _field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def present_field_names(raw: dict[str, Any]) -> list[str]:
    """Sorted names of top-level listing fields that had a value."""
    return sorted(key for key, value in raw.items() if _field_present(value))


def resolve_provider_url(raw: dict[str, Any]) -> str | None:
    for field in _PROVIDER_URL_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_provider_listing_id(entry: dict[str, Any], raw: dict[str, Any]) -> str:
    for field in ("listing_id", "id"):
        value = raw.get(field)
        if _field_present(value):
            return str(value).strip()
    entry_id = entry.get("id")
    if _field_present(entry_id):
        return str(entry_id).strip()
    return ""


def attach_listing_provenance(
    entry: dict[str, Any],
    *,
    provider_name: str,
) -> dict[str, Any]:
    """Return a copy of a listing record with provider provenance metadata."""
    listing = entry.get("listing")
    raw = dict(listing) if isinstance(listing, dict) else dict(entry)

    enriched: dict[str, Any] = dict(entry)
    enriched["provider_name"] = provider_name
    enriched["provider_listing_id"] = resolve_provider_listing_id(entry, raw)
    provider_url = resolve_provider_url(raw)
    if provider_url is not None:
        enriched["provider_url"] = provider_url
    enriched["provider_raw_fields"] = present_field_names(raw)
    return enriched
