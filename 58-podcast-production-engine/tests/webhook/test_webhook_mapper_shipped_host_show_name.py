"""Regression test for the SHIPPED mapper (scripts/webhook/mapper.py + aliases.json),
independent of the spec_reference oracle used by conftest.py's `sut` fixture.

P3-02 (c)2: the real Convert and Flow WF-1 intake payload carries the interview
host/show names under the customData keys `podcast_host_name` / `podcast_show_name`
(PODCAST-SNAPSHOT-BUILD-MANIFEST.md Section B rows 1-2; the WF-1 payload merges
`{{custom_values.podcast_host_name}}` / `{{custom_values.podcast_show_name}}`).
An earlier FB-workflow revision referenced a non-existent custom value
`podcast_survey_host_name` (manifest K.7 item 3, flagged for remap). The shipped
`aliases.json` field_aliases table never carried EITHER key for `host_name` /
`show_name` (only the bare `host_name`/`show_name`/`hostName`/`showName` spellings),
so a real interview submission mapped through the SHIPPED mapper is wrongly held as
`needs_input` with `show_name`/`host_name` reported missing even though both were
supplied. This test drives the shipped module directly (no oracle) against a
captured Convert and Flow customData payload (byte-identical to
tests/webhook/fixtures/convertflow_interview_provocative.json) and proves the
mapping succeeds end to end.

Pre-fix this test fails 2/2 (host_name, show_name both come back None and both are
reported in `missing`, status stays "needs_input"). Post-fix it passes 2/2.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_WEBHOOK_SCRIPTS_DIR = os.path.abspath(
    os.path.join(_HERE, "..", "..", "scripts", "webhook")
)
_FIXTURE_PATH = os.path.join(_HERE, "fixtures", "convertflow_interview_provocative.json")

_TENANT_LOCATION_ID = "Loc0Abc123Xyz789"  # matches the fixture's locationId verbatim


def _load_shipped_mapper():
    """Import scripts/webhook/mapper.py by file path (the SHIPPED module, never the
    spec_reference oracle), so this test exercises production code directly."""
    module_path = os.path.join(_WEBHOOK_SCRIPTS_DIR, "mapper.py")
    spec = importlib.util.spec_from_file_location("podcast_shipped_mapper", module_path)
    module = importlib.util.module_from_spec(spec)
    # aliases.json is loaded relative to __file__ inside mapper.py (default_tables_path),
    # so it must resolve to the real sibling file regardless of sys.path state.
    sys.modules["podcast_shipped_mapper"] = module
    spec.loader.exec_module(module)
    return module


def _load_captured_payload():
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_shipped_mapper_resolves_host_name_from_podcast_host_name():
    mapper = _load_shipped_mapper()
    tables = mapper.load_tables()
    payload = _load_captured_payload()

    result = mapper.map_payload(payload, tables, expected_location_id=_TENANT_LOCATION_ID)

    assert result["canonical"].get("host_name") == "Dana Whitfield", (
        "host_name did not resolve from the captured customData.podcast_host_name key; "
        "got %r, missing=%r" % (result["canonical"].get("host_name"), result["missing"])
    )
    assert "host_name" not in result["missing"]


def test_shipped_mapper_resolves_show_name_from_podcast_show_name():
    mapper = _load_shipped_mapper()
    tables = mapper.load_tables()
    payload = _load_captured_payload()

    result = mapper.map_payload(payload, tables, expected_location_id=_TENANT_LOCATION_ID)

    assert result["canonical"].get("show_name") == "The Unfiltered Founder", (
        "show_name did not resolve from the captured customData.podcast_show_name key; "
        "got %r, missing=%r" % (result["canonical"].get("show_name"), result["missing"])
    )
    assert "show_name" not in result["missing"]


def test_shipped_mapper_full_interview_submission_is_mapped_not_needs_input():
    """End-to-end: the whole captured payload maps to status "mapped" with zero
    missing required fields -- proves the fix closes the gap for a real submission,
    not just the two individual field lookups."""
    mapper = _load_shipped_mapper()
    tables = mapper.load_tables()
    payload = _load_captured_payload()

    result = mapper.map_payload(payload, tables, expected_location_id=_TENANT_LOCATION_ID)

    assert result["status"] == "mapped", (
        "expected status 'mapped', got %r with missing=%r"
        % (result["status"], result["missing"])
    )
    assert result["missing"] == []


def test_shipped_mapper_still_accepts_legacy_bare_host_name_alias():
    """Back-compat: a sender that already posts the bare `host_name` / `show_name`
    keys (pre-existing alias entries) must keep working -- the fix only ADDS
    aliases, it never removes or reorders the existing ones."""
    mapper = _load_shipped_mapper()
    tables = mapper.load_tables()
    payload = copy.deepcopy(_load_captured_payload())
    payload["customData"]["host_name"] = payload["customData"].pop("podcast_host_name")
    payload["customData"]["show_name"] = payload["customData"].pop("podcast_show_name")

    result = mapper.map_payload(payload, tables, expected_location_id=_TENANT_LOCATION_ID)

    assert result["canonical"].get("host_name") == "Dana Whitfield"
    assert result["canonical"].get("show_name") == "The Unfiltered Founder"
    assert result["status"] == "mapped"


def test_shipped_mapper_accepts_legacy_podcast_survey_host_name_alias():
    """Back-compat for the OLD (documented-stale) merge tag name
    `podcast_survey_host_name` (PODCAST-SNAPSHOT-BUILD-MANIFEST.md K.7 item 3):
    any sender still emitting the pre-remap key must not be quarantined as
    needs_input while any live GHL workflow still carries the old merge tag."""
    mapper = _load_shipped_mapper()
    tables = mapper.load_tables()
    payload = copy.deepcopy(_load_captured_payload())
    payload["customData"]["podcast_survey_host_name"] = payload["customData"].pop("podcast_host_name")

    result = mapper.map_payload(payload, tables, expected_location_id=_TENANT_LOCATION_ID)

    assert result["canonical"].get("host_name") == "Dana Whitfield"
    assert "host_name" not in result["missing"]
