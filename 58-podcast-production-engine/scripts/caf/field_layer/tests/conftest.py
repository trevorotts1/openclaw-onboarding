#!/usr/bin/env python3
"""
Test fixtures for the Convert and Flow field layer. Fully offline: no network,
no subprocess, no caf binary. A FakeDataPlane stands in for the transport with
the same method surface used by field_map and writer.
"""
from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# Make `import field_layer` resolve when pytest runs from anywhere. The package
# lives at scripts/caf/field_layer; its parent (scripts/caf) goes on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_CAF = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _SCRIPTS_CAF not in sys.path:
    sys.path.insert(0, _SCRIPTS_CAF)

from field_layer import constants  # noqa: E402


def make_custom_fields() -> list[dict[str, Any]]:
    """A field list covering every required write key plus a couple of reads and
    the double-underscore additional-info key. book_teaser is intentionally
    absent so the absence path is the default; a test adds it explicitly."""
    keys = [
        constants.EPISODE_URL_KEY,
        "contact.podcast_survey_episode_title",
        "contact.podcast_survey_episode_description",
        "contact.finish_podcast_google_doc_link",
        "contact.podcast_transcript_link",
        constants.FULL_TRANSCRIPT_KEY,
        constants.ADDITIONAL_INFO_DOUBLE_UNDERSCORE_KEY,
        "contact.my_preferred_pronoun",
    ]
    fields = []
    for index, key in enumerate(keys):
        fields.append({"id": f"fid_{index}", "fieldKey": key, "dataType": "TEXT"})
    return fields


class FakeDataPlane:
    """In-memory stand-in for CafRestDataPlane."""

    def __init__(self, custom_fields: list[dict[str, Any]], location_id: str = "loc-abc") -> None:
        self.location_id = location_id
        self._fields = custom_fields
        self._store: dict[str, dict[str, str]] = {}
        self.write_calls: list[list[str]] = []   # ordered list of id-lists written
        self.drop_once: set[str] = set()          # field ids dropped on first write
        self.drop_always: set[str] = set()        # field ids never stored
        self._dropped_once: set[str] = set()
        self.rate_limit_on: set[str] = set()      # field ids that raise RateLimited
        self.list_count = 0                        # times list_custom_fields ran

    def list_custom_fields(self) -> list[dict[str, Any]]:
        self.list_count += 1
        return self._fields

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        store = self._store.get(contact_id, {})
        return {"id": contact_id,
                "customFields": [{"id": fid, "value": val} for fid, val in store.items()]}

    def write_custom_fields(self, contact_id: str,
                            fields: list[dict[str, str]]) -> tuple[Any, str]:
        from field_layer.transport import RateLimited

        ids = [f["id"] for f in fields]
        self.write_calls.append(ids)
        store = self._store.setdefault(contact_id, {})
        for entry in fields:
            fid = entry["id"]
            if fid in self.rate_limit_on:
                raise RateLimited(1.0)
            if fid in self.drop_always:
                continue
            if fid in self.drop_once and fid not in self._dropped_once:
                self._dropped_once.add(fid)
                continue
            store[fid] = entry["value"]
        return ({"ok": True}, "tier3")


@pytest.fixture
def custom_fields() -> list[dict[str, Any]]:
    return make_custom_fields()


@pytest.fixture
def fake_dataplane_cls():
    return FakeDataPlane


@pytest.fixture
def dataplane(custom_fields):
    return FakeDataPlane(custom_fields)


@pytest.fixture
def valid_values() -> dict[str, str]:
    return {
        "contact.podcast_survey_episode_title": "Why Quiet Founders Win",
        "contact.podcast_survey_episode_description": "A ten minute episode on restraint.",
        "contact.finish_podcast_google_doc_link": "https://docs.example.com/package",
        "contact.podcast_transcript_link": "https://docs.example.com/script",
        constants.EPISODE_URL_KEY: "https://client.podbean.com/e/episode-123",
    }
