#!/usr/bin/env python3
"""test_item17_fleet_profiles.py -- FIX-PLAN Item 17: fleet shapes as
first-class profile values, the remembered system gauge, and the
model-choice record.

WHAT THIS FILE PINS, mechanically:

  1. PROFILE ROUND-TRIPS PER FLEET SHAPE. Each of the three exact labels
     (fleet-mac, fleet-hostinger, fleet-contabo) records into the profile,
     locks ask-once, and reads back byte-identical from a fresh load. A
     label that is not one of the three is REFUSED (the labels are
     Trevor's, exact, never renamed or folded).
  2. DETECTION HONESTY. A certain detection (fleet-mac) needs no question
     and is recorded by the gauge as detected; an ambiguous Linux
     container (hostinger or contabo, indistinguishable from inside)
     records NO shape, owes exactly one question, and the gauge carries
     the candidates instead of a guess.
  3. PER-SHAPE BUDGET DERIVATION. fleet-mac: native totals, no container
     budget, the owner reference profile as expectation. fleet-hostinger:
     the cgroup container budget is the box budget, no host ceiling.
     fleet-contabo: BOTH the container budget and the host ceiling it was
     sliced from. Unknown shape: defaults say unknown, nothing asserted.
  4. GAUGING PERSISTENCE + STALENESS. A recorded gauge starts a second
     load from measured truth (providers, budgets, measured_at); a gauge
     older than the persisted-measurement window, or cut under a
     different shape or different hardware, is NOT trusted
     (gauge_status / needs_regauge), and a re-gauge overwrites it without
     unsettling the locked shape answer.
  5. THE MODEL-CHOICE RECORD. Selection (client-selected or
     configured-default) and recommendations shown are separate fields
     with separate writers: a recommendation NEVER becomes the selection,
     accepting one does not write the selection, and "recommended" is
     refused as a selection source.

Unit-level: no network, no spend, no engine. Profiles live in tmp config
dirs; hardware/capacity readings are injected stubs in the shapes the
real modules produce.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import hardware_budget  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402

GB = 1024 ** 3

MAC_DETECTION = {
    "shape": "fleet-mac", "candidates": ["fleet-mac"], "certain": True,
    "platform": "darwin", "container": False,
    "container_budget_bytes": None, "host_ceiling_bytes": 24 * GB,
    "signals": {}, "evidence": ["platform is darwin"],
}
CONTAINER_DETECTION = {
    "shape": None, "candidates": ["fleet-hostinger", "fleet-contabo"],
    "certain": False, "platform": "linux", "container": True,
    "container_budget_bytes": 2 * GB, "host_ceiling_bytes": 62 * GB,
    "signals": {"cgroup_limit_bytes": 2 * GB, "host_ram_bytes": 62 * GB},
    "evidence": ["Linux container signals fired: dockerenv, cgroup_limited"],
}
MAC_SNAP = {
    "platform": "darwin", "status": "MEASURED",
    "ram_total_bytes": 24 * GB, "ram_available_bytes": 9 * GB,
    "cores": 10, "cgroup": "none (macOS host)",
    "budgets": {"text": {"budget": 400}, "image": {"budget": 9},
                "browser": {"budget": 9}, "render": {"budget": 9},
                "local_model": {"budget": 1}},
}
CONTAINER_SNAP = {
    "platform": "linux", "status": "MEASURED",
    "ram_total_bytes": 2 * GB, "ram_available_bytes": 1 * GB,
    "cores": 2, "cgroup": "cgroup",
    "budgets": {"text": {"budget": 50}, "image": {"budget": 1},
                "browser": {"budget": 1}, "render": {"budget": 1},
                "local_model": {"budget": 1}},
}
OLLAMA_100_READING = {
    "provider": "ollama-cloud", "plan": "$100/month", "status": "MEASURED",
    "available": 8,
    "account_factors": {"account_limit": 10, "reserve": 2,
                        "allocation": None, "account_ceiling": 8},
}


@pytest.fixture(autouse=True)
def _no_env_shape(monkeypatch):
    monkeypatch.delenv(rp.FLEET_SHAPE_ENV, raising=False)
    monkeypatch.delenv("PRESENTATION_RESOURCE_PROFILE", raising=False)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


# ---------------------------------------------------------------------------
# 1. Fleet shape round-trips
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("shape", ["fleet-mac", "fleet-hostinger",
                                   "fleet-contabo"])
def test_profile_round_trip_per_fleet_shape(tmp_path, shape):
    rp.record_fleet_shape(shape, config_dir=tmp_path)
    raw = json.loads((tmp_path / "resource_profile.json").read_text())
    assert raw["fleet"]["shape"] == shape  # the exact label, on disk
    assert raw["fleet"]["locked"] is True
    fresh = rp.load_profile(tmp_path)
    assert rp.fleet_shape(fresh) == shape
    assert rp.fleet_shape(config_dir=tmp_path) == shape
    # asked once: no question is owed any more, whatever detection says
    assert rp.fleet_shape_question(profile=fresh,
                                   detection=CONTAINER_DETECTION) is None


@pytest.mark.parametrize("bad", ["fleet-vps", "mac", "Fleet-Mac",
                                 "hostinger", "contabo", "", "fleet"])
def test_record_fleet_shape_refuses_any_other_label(tmp_path, bad):
    with pytest.raises(ValueError):
        rp.record_fleet_shape(bad, config_dir=tmp_path)
    assert rp.fleet_shape(config_dir=tmp_path) is None


def test_fleet_shape_first_answer_locks_and_rerecord_is_audited(tmp_path):
    rp.record_fleet_shape("fleet-hostinger", config_dir=tmp_path)
    rp.record_fleet_shape("fleet-contabo", config_dir=tmp_path)
    prof = rp.load_profile(tmp_path)
    assert rp.fleet_shape(prof) == "fleet-contabo"  # explicit re-record wins
    assert prof["fleet"]["locked"] is True         # the lock never unsettles
    log = prof["interview"]["fleet_shape"]
    assert [row["shape"] for row in log] == ["fleet-hostinger", "fleet-contabo"]


# ---------------------------------------------------------------------------
# 2. Detection honesty
# ---------------------------------------------------------------------------
def test_certain_detection_needs_no_question_and_gauge_records_it(tmp_path):
    question = rp.fleet_shape_question(profile=rp.new_profile(),
                                       detection=MAC_DETECTION)
    assert question is None
    gauge = rp.record_system_gauge(tmp_path, detection=MAC_DETECTION,
                                   snap=MAC_SNAP, capacity_readings=[])
    assert gauge["fleet_shape"] == "fleet-mac"
    assert gauge["shape_source"] == "detected"
    assert rp.fleet_shape(config_dir=tmp_path) == "fleet-mac"


def test_ambiguous_container_records_no_shape_and_owes_one_question(tmp_path):
    gauge = rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                                   snap=CONTAINER_SNAP, capacity_readings=[])
    assert gauge["fleet_shape"] is None            # never guessed
    assert gauge["shape_candidates"] == ["fleet-hostinger", "fleet-contabo"]
    assert rp.fleet_shape(config_dir=tmp_path) is None
    question = rp.fleet_shape_question(config_dir=tmp_path,
                                       detection=CONTAINER_DETECTION)
    assert question is not None
    assert question["id"] == "fleet_shape"
    assert question["candidates"] == ["fleet-hostinger", "fleet-contabo"]
    assert question["asked_once_then_locked"] is True


def test_env_declaration_records_shape_as_declared_and_locked(tmp_path,
                                                               monkeypatch):
    monkeypatch.setenv(rp.FLEET_SHAPE_ENV, "fleet-contabo")
    gauge = rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                                   snap=CONTAINER_SNAP, capacity_readings=[])
    assert gauge["fleet_shape"] == "fleet-contabo"
    assert gauge["shape_source"] == "declared"
    prof = rp.load_profile(tmp_path)
    assert prof["fleet"]["locked"] is True
    assert prof["fleet"]["source"] == "declared"


def test_invalid_env_shape_is_ignored_and_noted(tmp_path, monkeypatch):
    monkeypatch.setenv(rp.FLEET_SHAPE_ENV, "fleet-vps")
    gauge = rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                                   snap=CONTAINER_SNAP, capacity_readings=[])
    assert gauge["fleet_shape"] is None
    assert any(rp.FLEET_SHAPE_ENV in note for note in gauge["notes"])


def test_detect_fleet_shape_on_this_box_is_honest():
    det = hardware_budget.detect_fleet_shape()
    assert set(det) >= {"shape", "candidates", "certain", "evidence",
                        "container_budget_bytes", "host_ceiling_bytes"}
    assert det["shape"] in (None, "fleet-mac", "fleet-hostinger",
                            "fleet-contabo")
    assert set(det["candidates"]) <= set(rp.FLEET_SHAPES)
    if det["container"] and det["shape"] is None:
        # a container the code cannot place must name BOTH candidates
        assert det["candidates"] == ["fleet-hostinger", "fleet-contabo"]
    host, source = hardware_budget.host_ram_bytes()
    assert host is None or isinstance(host, int)
    assert isinstance(source, str) and source


# ---------------------------------------------------------------------------
# 3. Per-shape budget derivation
# ---------------------------------------------------------------------------
def test_gauge_mac_records_native_totals_and_reference_expectations(tmp_path):
    rp.record_fleet_shape("fleet-mac", config_dir=tmp_path)
    gauge = rp.record_system_gauge(tmp_path, detection=MAC_DETECTION,
                                   snap=MAC_SNAP, capacity_readings=[])
    hw = gauge["hardware"]
    assert hw["container_budget_bytes"] is None       # no container layer
    assert hw["host_ceiling_bytes"] == 24 * GB        # the box itself
    expectations = gauge["defaults_applied"]["workflow_expectations"]
    assert expectations["agents_per_workflow"] == 10  # owner reference profile
    assert expectations["concurrent_workflows"] == 50


def test_gauge_hostinger_records_container_budget_only(tmp_path):
    rp.record_fleet_shape("fleet-hostinger", config_dir=tmp_path)
    gauge = rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                                   snap=CONTAINER_SNAP, capacity_readings=[])
    hw = gauge["hardware"]
    assert hw["container_budget_bytes"] == 2 * GB  # cgroup limit = box budget
    assert hw["host_ceiling_bytes"] is None        # single-tenant: no ceiling
    assert gauge["defaults_applied"]["workflow_expectations"] is None


def test_gauge_contabo_records_container_budget_and_host_ceiling(tmp_path):
    rp.record_fleet_shape("fleet-contabo", config_dir=tmp_path)
    gauge = rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                                   snap=CONTAINER_SNAP, capacity_readings=[])
    hw = gauge["hardware"]
    assert hw["container_budget_bytes"] == 2 * GB   # the container's slice
    assert hw["host_ceiling_bytes"] == 62 * GB      # the shared host it came from
    assert gauge["defaults_applied"]["memory_model"] == \
        "container-under-shared-host"


def test_unknown_shape_defaults_assert_nothing():
    defaults = rp.fleet_shape_defaults(None)
    assert defaults["memory_model"] == "unknown"
    assert defaults["workflow_expectations"] is None
    assert rp.fleet_shape_defaults("fleet-nope")["memory_model"] == "unknown"


# ---------------------------------------------------------------------------
# 4. Gauging persistence and staleness
# ---------------------------------------------------------------------------
def _fresh_gauge(tmp_path, measured_at="2026-10-14T00:00:00+00:00"):
    rp.record_fleet_shape("fleet-hostinger", config_dir=tmp_path)
    return rp.record_system_gauge(
        tmp_path, detection=CONTAINER_DETECTION, snap=CONTAINER_SNAP,
        capacity_readings=[OLLAMA_100_READING], measured_at=measured_at)


def _stored_fingerprint(tmp_path):
    return rp.system_gauge(rp.load_profile(tmp_path))["fingerprint"]


def test_gauge_persists_measured_truth_for_the_second_run(tmp_path):
    gauge = _fresh_gauge(tmp_path)
    assert gauge["measured_at"] == "2026-10-14T00:00:00+00:00"
    assert gauge["budgets"]["text"] == 50
    row = gauge["providers"][0]
    assert row["provider"] == "ollama-cloud"
    assert row["available"] == 8          # cap table: raw 10 minus reserve 2
    assert row["account_limit"] == 10
    assert row["reserve"] == 2
    # a fresh load (the "second run") starts from the same measured truth
    prof = rp.load_profile(tmp_path)
    assert rp.system_gauge(prof)["measured_at"] == gauge["measured_at"]
    status = rp.gauge_status(prof, live_fingerprint=_stored_fingerprint(tmp_path),
                             now_s=_epoch("2026-10-14T01:00:00+00:00"))
    assert status["state"] == "fresh"
    assert rp.needs_regauge(prof,
                            live_fingerprint=_stored_fingerprint(tmp_path),
                            now_s=_epoch("2026-10-14T01:00:00+00:00")) is False


def test_unbounded_capacity_reading_is_recorded_as_unbounded(tmp_path):
    reading = {"provider": "openrouter", "plan": None, "status": "MEASURED",
               "available": capacity.UNBOUNDED, "account_factors": {}}
    gauge = rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                                   snap=CONTAINER_SNAP,
                                   capacity_readings=[reading])
    assert gauge["providers"][0]["available"] == "UNBOUNDED"
    json.dumps(rp.load_profile(tmp_path))  # the store stays valid JSON


def test_stale_gauge_is_not_trusted(tmp_path):
    _fresh_gauge(tmp_path, measured_at="2026-10-12T00:00:00+00:00")
    prof = rp.load_profile(tmp_path)
    status = rp.gauge_status(prof, live_fingerprint=_stored_fingerprint(tmp_path),
                             now_s=_epoch("2026-10-14T00:00:01+00:00"))
    assert status["state"] == "stale-age"   # 48h > the 24h window
    assert rp.needs_regauge(prof,
                            live_fingerprint=_stored_fingerprint(tmp_path),
                            now_s=_epoch("2026-10-14T00:00:01+00:00")) is True


def test_hardware_change_invalidates_the_gauge(tmp_path):
    _fresh_gauge(tmp_path)
    live = dict(_stored_fingerprint(tmp_path))
    live["host_ram_bytes"] = 124 * GB      # the box was replaced/resized
    status = rp.gauge_status(rp.load_profile(tmp_path), live_fingerprint=live,
                             now_s=_epoch("2026-10-14T01:00:00+00:00"))
    assert status["state"] == "hardware-changed"


def test_shape_change_invalidates_the_gauge(tmp_path):
    _fresh_gauge(tmp_path)
    rp.record_fleet_shape("fleet-contabo", config_dir=tmp_path)  # operator fix
    status = rp.gauge_status(rp.load_profile(tmp_path),
                             live_fingerprint=_stored_fingerprint(tmp_path),
                             now_s=_epoch("2026-10-14T01:00:00+00:00"))
    assert status["state"] == "shape-changed"


def test_regauge_overwrites_the_gauge_and_keeps_the_shape_lock(tmp_path):
    _fresh_gauge(tmp_path, measured_at="2026-10-12T00:00:00+00:00")
    gauge = rp.record_system_gauge(
        tmp_path, detection=CONTAINER_DETECTION, snap=CONTAINER_SNAP,
        capacity_readings=[OLLAMA_100_READING],
        measured_at="2026-10-14T00:00:00+00:00")
    assert gauge["measured_at"] == "2026-10-14T00:00:00+00:00"
    prof = rp.load_profile(tmp_path)
    assert prof["fleet"]["shape"] == "fleet-hostinger"  # answer untouched
    assert prof["fleet"]["locked"] is True
    status = rp.gauge_status(prof, live_fingerprint=_stored_fingerprint(tmp_path),
                             now_s=_epoch("2026-10-14T02:00:00+00:00"))
    assert status["state"] == "fresh"


def test_missing_gauge_reports_missing(tmp_path):
    status = rp.gauge_status(rp.load_profile(tmp_path))
    assert status["state"] == "missing"
    assert rp.needs_regauge(rp.load_profile(tmp_path)) is True


# ---------------------------------------------------------------------------
# 5. The model-choice record
# ---------------------------------------------------------------------------
def test_model_choice_selection_round_trips(tmp_path):
    rp.record_model_choice("openrouter", "acme/large-1", config_dir=tmp_path)
    prof = rp.load_profile(tmp_path)
    effective = rp.effective_model_choice("openrouter", profile=prof)
    assert effective["model"] == "acme/large-1"
    assert effective["source"] == "selected"


def test_model_choice_configured_default_is_distinct_from_selection(tmp_path):
    rp.record_model_choice("ollama-cloud", "client-default-model",
                           source="configured-default", config_dir=tmp_path)
    effective = rp.effective_model_choice("ollama-cloud",
                                          config_dir=tmp_path)
    assert effective["model"] == "client-default-model"
    assert effective["source"] == "configured-default"


def test_recommendation_shown_never_becomes_the_selection(tmp_path):
    rp.record_recommendation_shown(
        "openrouter", "acme/large-1", "no provider cap; the machine is "
        "the only limit", config_dir=tmp_path)
    prof = rp.load_profile(tmp_path)
    assert rp.effective_model_choice("openrouter", profile=prof) is None
    row = rp.model_choice_row("openrouter", profile=prof)
    assert row["selection"] is None
    shown = row["recommendations_shown"]
    assert len(shown) == 1
    assert shown[0]["model"] == "acme/large-1"
    assert shown[0]["response"] == "offered"
    assert "no provider cap" in shown[0]["reason"]


def test_selection_and_recommendation_stay_distinct(tmp_path):
    rp.record_recommendation_shown("deepseek-direct", "ds-pro",
                                   "faster for long decks",
                                   config_dir=tmp_path)
    rp.record_model_choice("deepseek-direct", "ds-flash", config_dir=tmp_path)
    row = rp.model_choice_row("deepseek-direct", config_dir=tmp_path)
    assert row["selection"]["model"] == "ds-flash"          # the client's pick
    assert row["recommendations_shown"][0]["model"] == "ds-pro"  # still guidance
    # accepting the recommendation does NOT rewrite the selection either
    updated = rp.record_recommendation_response(
        "deepseek-direct", "ds-pro", "accepted", config_dir=tmp_path)
    assert updated["response"] == "accepted"
    effective = rp.effective_model_choice("deepseek-direct",
                                          config_dir=tmp_path)
    assert effective["model"] == "ds-flash"


def test_record_model_choice_refuses_a_recommendation_source(tmp_path):
    with pytest.raises(ValueError):
        rp.record_model_choice("openrouter", "acme/large-1",
                               source="recommended", config_dir=tmp_path)
    assert rp.effective_model_choice("openrouter",
                                     config_dir=tmp_path) is None


def test_recommendation_response_for_never_shown_model_is_none(tmp_path):
    rp.record_model_choice("openrouter", "acme/large-1", config_dir=tmp_path)
    assert rp.record_recommendation_response(
        "openrouter", "acme/never-shown", "declined",
        config_dir=tmp_path) is None
    with pytest.raises(ValueError):
        rp.record_recommendation_response(
            "openrouter", "acme/large-1", "offered", config_dir=tmp_path)


def test_model_choices_survive_the_redaction_round_trip(tmp_path):
    rp.record_model_choice("OpenRouter", "acme/large-1", config_dir=tmp_path)
    rp.record_recommendation_shown("OpenRouter", "acme/large-2", "reason",
                                   config_dir=tmp_path)
    raw = json.loads((tmp_path / "resource_profile.json").read_text())
    assert isinstance(raw["model_choices"], list)  # rows are a list, not a dict
    prof = rp.load_profile(tmp_path)               # load re-applies redaction
    row = rp.model_choice_row("openrouter", profile=prof)
    assert row["selection"]["model"] == "acme/large-1"   # family folded once
    assert row["recommendations_shown"][0]["model"] == "acme/large-2"


# ---------------------------------------------------------------------------
# 6. The capacity probe surface
# ---------------------------------------------------------------------------
def test_capacity_probe_consumes_the_recorded_shape_and_gauge(tmp_path):
    rp.record_fleet_shape("fleet-contabo", config_dir=tmp_path)
    rp.record_system_gauge(tmp_path, detection=CONTAINER_DETECTION,
                           snap=CONTAINER_SNAP,
                           capacity_readings=[OLLAMA_100_READING])
    result = capacity.probe(tmp_path)
    surface = result["fleet_shape"]
    assert surface["recorded_shape"] == "fleet-contabo"
    assert surface["gauge"]["fleet_shape"] == "fleet-contabo"
    assert surface["gauge"]["hardware"]["container_budget_bytes"] == 2 * GB
    assert surface["gauge"]["hardware"]["host_ceiling_bytes"] == 62 * GB
    assert surface["gauge_state"] in ("fresh", "hardware-changed",
                                      "stale-age", "shape-changed")


def test_fleet_shape_surface_degrades_honestly_on_a_broken_profile(tmp_path):
    (tmp_path / "resource_profile.json").write_text("{not json")
    surface = capacity.fleet_shape_surface(tmp_path)
    assert surface["recorded_shape"] is None
    assert surface["gauge"] is None
    assert surface["gauge_state"] == "missing"
