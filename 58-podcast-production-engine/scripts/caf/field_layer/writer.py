#!/usr/bin/env python3
"""
Link-back writer and read-back verifier (design Sections 3.3 and 3.4).

Write ordering, binding:
  1. one batch call carrying title, description, Episode Package link, Speech
     Script link (and book_teaser when the field exists, and the optional full
     transcript when supplied).
  2. a second, separate call writing contact.podcast_survey_episode_url ALONE.

The URL is last and alone because the client account workflow
"04-Podcast is Completed" is triggered by that field changing. Writing the URL
is therefore a live customer-facing trigger and must land only after every
other field is already in place, so the workflow reads a complete record.

Read-back verification, binding: after the writes, the contact is fetched and
every written value is compared byte-for-byte. Only a passing read-back counts
as a Convert and Flow save confirmation. A mismatch retries the write once, then
enters failure handling.

Value hygiene, binding: links are bare URLs (no markdown, no surrounding
quotes); title and description have no code fences and no em dash characters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import constants
from .field_map import FieldMapResult
from .transport import CafRestDataPlane


class ValueHygieneError(Exception):
    """A value violates the bare-URL or no-em-dash / no-fence rules."""


class ReadBackMismatch(Exception):
    """One or more written values did not read back byte-for-byte after retry."""

    def __init__(self, mismatched_keys: list[str]) -> None:
        super().__init__("Convert and Flow read-back mismatch")
        self.mismatched_keys = mismatched_keys


@dataclass
class LinkBackResult:
    batch_keys_written: list[str] = field(default_factory=list)
    url_written: bool = False
    batch_tier: str | None = None
    url_tier: str | None = None
    read_back_pass: bool = False
    retried: bool = False
    book_teaser_note: str | None = None

    def public_summary(self) -> dict[str, Any]:
        return {
            "batch_keys_written": self.batch_keys_written,
            "url_written": self.url_written,
            "batch_tier": self.batch_tier,
            "url_tier": self.url_tier,
            "read_back_pass": self.read_back_pass,
            "retried": self.retried,
            "book_teaser_note": self.book_teaser_note,
            "save_confirmed": self.read_back_pass,
        }


# ---------------------------------------------------------------------------
# Value hygiene
# ---------------------------------------------------------------------------

def _assert_no_forbidden_chars(key: str, value: str) -> None:
    for dash in constants.EM_DASH_CHARS:
        if dash in value:
            raise ValueHygieneError(f"{key} contains a forbidden em dash character")
    if constants.TRIPLE_BACKTICK in value:
        raise ValueHygieneError(f"{key} contains a forbidden triple-backtick fence")


def _hygiene_url(key: str, value: str) -> str:
    cleaned = value.strip().strip("\"'`<>").strip()
    if constants.TRIPLE_BACKTICK in value:
        raise ValueHygieneError(f"{key} URL contains a forbidden triple-backtick fence")
    if "](" in cleaned or cleaned.startswith("["):
        raise ValueHygieneError(f"{key} must be a bare URL, not markdown")
    if any(ch.isspace() for ch in cleaned):
        raise ValueHygieneError(f"{key} must be a single bare URL with no whitespace")
    if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        raise ValueHygieneError(f"{key} must be a bare http(s) URL")
    return cleaned


def _hygiene(key: str, value: str) -> str:
    if not isinstance(value, str):
        raise ValueHygieneError(f"{key} value must be a string")
    if key in constants.URL_WRITE_KEYS:
        return _hygiene_url(key, value)
    cleaned = value
    _assert_no_forbidden_chars(key, cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Read-back extraction
# ---------------------------------------------------------------------------

def _extract_values_by_id(contact: dict[str, Any]) -> dict[str, str]:
    raw = contact.get("customFields")
    if not isinstance(raw, list):
        raw = contact.get("customField")
    values: dict[str, str] = {}
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            field_id = entry.get("id")
            if not field_id:
                continue
            value = entry.get("value")
            if value is None:
                value = entry.get("field_value")
            if value is not None:
                values[field_id] = str(value)
    return values


def verify_read_back(dataplane: CafRestDataPlane, contact_id: str,
                     field_map: dict[str, str], expected: dict[str, str]) -> tuple[bool, list[str]]:
    """Fetch the contact and compare each expected key byte-for-byte.
    Returns (all_match, mismatched_keys)."""
    contact = dataplane.get_contact(contact_id)
    by_id = _extract_values_by_id(contact)
    mismatched: list[str] = []
    for key, expected_value in expected.items():
        field_id = field_map.get(key)
        if not field_id:
            mismatched.append(key)
            continue
        if by_id.get(field_id) != expected_value:
            mismatched.append(key)
    return (not mismatched, mismatched)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _fields_for_keys(keys: list[str], values: dict[str, str],
                     field_map: dict[str, str]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for key in keys:
        field_id = field_map.get(key)
        if not field_id:
            raise ValueHygieneError(f"no field id cached for {key}; rebuild the field map")
        payload.append({"id": field_id, "value": values[key]})
    return payload


def write_link_back(dataplane: CafRestDataPlane, contact_id: str,
                    values: dict[str, str], field_result: FieldMapResult) -> LinkBackResult:
    """Perform the batch-then-URL-last write with byte-for-byte read-back."""
    field_map = field_result.field_map
    result = LinkBackResult()

    # Required values must all be supplied.
    missing_values = [k for k in constants.REQUIRED_WRITE_KEYS if k not in values]
    if missing_values:
        raise ValueHygieneError(f"missing required link-back values: {missing_values}")

    # Hygiene every supplied value up front so nothing partial is written.
    clean: dict[str, str] = {}
    for key, value in values.items():
        if key == constants.BOOK_TEASER_KEY and not field_result.book_teaser_present:
            continue  # skip; handled as a note below
        if key not in field_map and key != constants.BOOK_TEASER_KEY:
            continue  # unknown key with no id; ignore rather than guess
        clean[key] = _hygiene(key, value)

    # Determine the batch key order: required batch keys, then optional ones.
    batch_keys: list[str] = [k for k in constants.BATCH_REQUIRED_WRITE_KEYS if k in clean]
    if constants.FULL_TRANSCRIPT_KEY in clean:
        batch_keys.append(constants.FULL_TRANSCRIPT_KEY)

    # book_teaser handling (Interview mode only; may be absent).
    if constants.BOOK_TEASER_KEY in values:
        if field_result.book_teaser_present and constants.BOOK_TEASER_KEY in clean:
            batch_keys.append(constants.BOOK_TEASER_KEY)
        else:
            result.book_teaser_note = (
                "book_teaser field absent in the account; reminder to create a "
                "custom field named book_teaser. Not written, episode not failed.")

    # 1. Batch call (everything except the URL).
    if batch_keys:
        _, result.batch_tier = dataplane.write_custom_fields(
            contact_id, _fields_for_keys(batch_keys, clean, field_map))
        result.batch_keys_written = list(batch_keys)

    # 2. URL call, ALONE and LAST.
    url_key = constants.EPISODE_URL_KEY
    _, result.url_tier = dataplane.write_custom_fields(
        contact_id, _fields_for_keys([url_key], clean, field_map))
    result.url_written = True

    # 3. Read-back verify every written value byte-for-byte.
    expected = {k: clean[k] for k in (*batch_keys, url_key)}
    ok, mismatched = verify_read_back(dataplane, contact_id, field_map, expected)

    # 4. One retry, preserving ordering (batch subset first, URL alone last).
    if not ok:
        result.retried = True
        retry_batch = [k for k in mismatched if k != url_key]
        if retry_batch:
            dataplane.write_custom_fields(
                contact_id, _fields_for_keys(retry_batch, clean, field_map))
        if url_key in mismatched:
            dataplane.write_custom_fields(
                contact_id, _fields_for_keys([url_key], clean, field_map))
        ok, mismatched = verify_read_back(dataplane, contact_id, field_map, expected)

    result.read_back_pass = ok
    if not ok:
        raise ReadBackMismatch(mismatched)
    return result
