#!/usr/bin/env python3
"""
Field-key to field-id resolution and cache (design Section 3.1).

The Convert and Flow contact API writes address custom fields by field ID while
this engine states its contract in field keys (contact.<key>). At first-run
smoke test the layer lists the account custom fields, builds the map, and
persists it in the per-client state file. The map is refreshed only when a write
fails with an unknown-field error or on operator command, never per episode.

Rules preserved verbatim from the design:
  - Every REQUIRED write key must exist, or the caller STOPS and routes the
    client to support (the fields are created via the snapshot, never silently).
  - The double underscore in contact.podcast_survey__additional_info is exact.
    The map never falls back to a single-underscore variant.
  - book_teaser may be absent (Interview mode only). Its absence is recorded and
    surfaced as a founder reminder, never created silently, never a hard fail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import constants
from .state import GhlState
from .transport import CafRestDataPlane


class MissingRequiredFieldError(Exception):
    """One or more REQUIRED write keys are absent from the account.

    The caller surfaces the support-path message and stops; it never creates the
    standardized fields. Carries the list of missing keys for the report."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__("Convert and Flow custom fields are missing")
        self.missing = missing


@dataclass
class FieldMapResult:
    field_map: dict[str, str] = field(default_factory=dict)
    book_teaser_present: bool = False
    additional_info_double_underscore_present: bool = False
    additional_info_single_underscore_seen: bool = False
    from_cache: bool = False

    def public_summary(self) -> dict[str, Any]:
        return {
            "resolved_keys": sorted(self.field_map.keys()),
            "book_teaser_present": self.book_teaser_present,
            "additional_info_double_underscore_present":
                self.additional_info_double_underscore_present,
            "additional_info_single_underscore_seen":
                self.additional_info_single_underscore_seen,
            "from_cache": self.from_cache,
        }


def _index_by_key(raw_fields: list[dict[str, Any]]) -> dict[str, str]:
    """Map fieldKey -> id. Accepts both `contact.<x>` and bare `<x>` fieldKeys
    that some API versions return, but never normalizes underscores."""
    index: dict[str, str] = {}
    for entry in raw_fields:
        if not isinstance(entry, dict):
            continue
        field_id = entry.get("id")
        field_key = entry.get("fieldKey") or entry.get("key")
        if not field_id or not field_key:
            continue
        index[field_key] = field_id
        # Also index a bare-key form so a `contact.` prefixed lookup still hits
        # when the API returns the key without the prefix. Underscores untouched.
        if field_key.startswith("contact."):
            index.setdefault(field_key[len("contact."):], field_id)
        else:
            index.setdefault(f"contact.{field_key}", field_id)
    return index


def _lookup(index: dict[str, str], key: str) -> str | None:
    """Exact lookup with a prefix-tolerant fallback. Never underscore-normalizes."""
    if key in index:
        return index[key]
    if key.startswith("contact."):
        bare = key[len("contact."):]
        return index.get(bare)
    return index.get(f"contact.{key}")


def build_field_map(dataplane: CafRestDataPlane) -> FieldMapResult:
    """List the account custom fields and build the field-key to field-id map."""
    raw = dataplane.list_custom_fields()
    index = _index_by_key(raw)
    result = FieldMapResult()

    # Required write keys must all resolve.
    missing: list[str] = []
    for key in constants.REQUIRED_WRITE_KEYS:
        field_id = _lookup(index, key)
        if field_id:
            result.field_map[key] = field_id
        else:
            missing.append(key)
    if missing:
        raise MissingRequiredFieldError(missing)

    # Optional and read keys: map when present, do not fail when absent.
    for key in (*constants.READ_KEYS, constants.FULL_TRANSCRIPT_KEY):
        field_id = _lookup(index, key)
        if field_id:
            result.field_map[key] = field_id

    # Double-underscore assertion: map the exact key only; never the single.
    double_key = constants.ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY
    single_key = double_key.replace("survey__additional", "survey_additional")
    result.additional_info_double_underscore_present = _lookup(index, double_key) is not None
    result.additional_info_single_underscore_seen = _lookup(index, single_key) is not None

    # book_teaser: Interview mode only, may not exist.
    book_id = _lookup(index, constants.BOOK_TEASER_KEY)
    if book_id:
        result.field_map[constants.BOOK_TEASER_KEY] = book_id
        result.book_teaser_present = True
    else:
        result.book_teaser_present = False

    return result


def get_or_build_field_map(dataplane: CafRestDataPlane, state: GhlState,
                           *, refresh: bool = False) -> FieldMapResult:
    """Cache-first field map. Uses the persisted map unless refresh is asked or
    a required key is missing from the cache; otherwise rebuilds and persists."""
    if not refresh:
        cached = state.get_field_map()
        if cached and all(k in cached for k in constants.REQUIRED_WRITE_KEYS):
            result = FieldMapResult(
                field_map=cached,
                book_teaser_present=state.book_teaser_present(),
                additional_info_double_underscore_present=(
                    constants.ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY in cached),
                from_cache=True,
            )
            return result

    result = build_field_map(dataplane)
    state.save_field_map(
        result.field_map, result.book_teaser_present, location_id=dataplane.location_id
    )
    return result
