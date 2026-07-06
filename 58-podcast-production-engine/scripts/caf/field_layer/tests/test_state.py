#!/usr/bin/env python3
"""State tests: sibling-section preservation, no secret material, round-trip."""
from __future__ import annotations

import json
import os

from field_layer import constants
from field_layer.state import GhlState


def test_save_field_map_preserves_sibling_sections(tmp_path):
    # A sibling slice already wrote folders, workflows, rate, and a fingerprint.
    path = os.path.join(str(tmp_path), constants.STATE_FILE_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "client": "acme",
            "location_id": "loc-xyz",
            "pit_fingerprint": "abc123def456",
            "folders": {"podcast": "f1"},
            "workflows": {"06-Podcast_Episode_Is_Ready": {"id": "w6"}},
            "rate": {"last_daily_remaining": 199000},
        }, handle)

    state = GhlState(str(tmp_path))
    state.save_field_map({"contact.podcast_survey_episode_url": "fid_0"}, True)

    data = state.load()
    # Field-layer sections written.
    assert data["field_map"]["contact.podcast_survey_episode_url"] == "fid_0"
    assert data["book_teaser_field_present"] is True
    # Sibling sections intact.
    assert data["folders"] == {"podcast": "f1"}
    assert data["workflows"]["06-Podcast_Episode_Is_Ready"]["id"] == "w6"
    assert data["rate"]["last_daily_remaining"] == 199000
    assert data["pit_fingerprint"] == "abc123def456"


def test_no_secret_material_written(tmp_path):
    state = GhlState(str(tmp_path))
    state.save_field_map({"contact.podcast_survey_episode_url": "fid_0"}, False,
                         location_id="loc-xyz")
    raw = open(state.path, "r", encoding="utf-8").read()
    assert "pit-" not in raw  # never a token value
    assert "Bearer" not in raw


def test_location_id_not_overwritten_when_present(tmp_path):
    path = os.path.join(str(tmp_path), constants.STATE_FILE_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"location_id": "loc-original"}, handle)
    state = GhlState(str(tmp_path))
    state.save_field_map({"contact.podcast_survey_episode_url": "fid_0"}, False,
                         location_id="loc-other")
    assert state.get_location_id() == "loc-original"


def test_field_map_round_trip_empty_start(tmp_path):
    state = GhlState(str(tmp_path))
    assert state.get_field_map() == {}
    state.save_field_map({"contact.podcast_survey_episode_title": "fid_1"}, False)
    assert state.get_field_map() == {"contact.podcast_survey_episode_title": "fid_1"}
