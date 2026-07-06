"""Unit tests for the Podcast Engine enrollment layer (PRD Step 17).

Every test is hermetic. No live CRM is ever contacted: caf is replaced by an
injected fake runner, and the one REST-fallback test monkeypatches requests.post.
A test that shells out to the real caf or reaches the network is a hard failure
by construction (the real runner is never passed in).

Run:
    python3 -m pytest test_enroll.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import enroll as en  # noqa: E402


GOOD_GATE = {"podbean_permalink": "https://pb/ep1", "field_writeback_verified": True}

STATE = {
    "location_id": "LOC",
    "workflows": {
        en.WF_04: {"id": "W04", "trigger": "field:podcast_survey_episode_url"},
        en.WF_06: {"id": "W06", "trigger": "direct_add"},
    },
}


class ScriptedRunner:
    """A fake caf runner driven by a table of contact states, recording calls."""

    def __init__(self, contact_reads: List[Dict[str, Any]],
                 enroll_ok: bool = True, tag_ok: bool = True,
                 workflows: List[Dict[str, Any]] | None = None) -> None:
        self.contact_reads = list(contact_reads)
        self.enroll_ok = enroll_ok
        self.tag_ok = tag_ok
        self.workflows = workflows or []
        self.calls: List[List[str]] = []

    def __call__(self, args: List[str]) -> en.CafResult:
        self.calls.append(list(args))
        key = " ".join(args[:2])
        if key == "contacts get":
            state = (self.contact_reads.pop(0) if len(self.contact_reads) > 1
                     else self.contact_reads[0])
            return en.CafResult(True, 0, data={"contact": state})
        if key == "workflows list":
            return en.CafResult(True, 0, data={"workflows": self.workflows})
        if key == "workflows enroll":
            return en.CafResult(self.enroll_ok, 0 if self.enroll_ok else 1,
                                data={"ok": self.enroll_ok},
                                stderr="" if self.enroll_ok else "rejected")
        if key == "contacts add-tag":
            return en.CafResult(self.tag_ok, 0 if self.tag_ok else 1)
        return en.CafResult(False, 1, stderr="unknown")

    def enroll_calls(self) -> List[List[str]]:
        return [c for c in self.calls if c[:2] == ["workflows", "enroll"]]


# --------------------------------------------------------------------------- #
# Mode guard
# --------------------------------------------------------------------------- #

def test_personal_mode_hard_refusal():
    runner = ScriptedRunner([{"tags": []}])
    with pytest.raises(en.ModeGuardError):
        en.enroll_episode(en.PERSONAL_MODE, "C1", STATE, runner=runner,
                          preconditions=GOOD_GATE)
    # Nothing was ever sent to caf.
    assert runner.calls == []


def test_non_interview_non_personal_is_skipped():
    runner = ScriptedRunner([{"tags": []}])
    res = en.enroll_episode("season_strategy", "C1", STATE, runner=runner,
                            preconditions=GOOD_GATE)
    assert res["skipped"] and not res["enrolled"] and res["verified"]
    assert runner.calls == []


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #

def test_gate_requires_permalink():
    with pytest.raises(en.GateError):
        en.enroll_episode(en.INTERVIEW_MODE, "C1", STATE,
                          runner=ScriptedRunner([{"tags": []}]),
                          preconditions={"field_writeback_verified": True})


def test_gate_requires_verified_writeback():
    with pytest.raises(en.GateError):
        en.enroll_episode(en.INTERVIEW_MODE, "C1", STATE,
                          runner=ScriptedRunner([{"tags": []}]),
                          preconditions={"podbean_permalink": "x"})


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

def test_resolve_workflow_from_state():
    wf = en.resolve_workflow(STATE, en.WF_04)
    assert wf["id"] == "W04" and wf["trigger"].startswith("field")


def test_resolve_workflow_from_live_discovery():
    runner = ScriptedRunner([{"tags": []}],
                            workflows=[{"id": "LIVE", "name": en.WF_06}])
    wf = en.resolve_workflow({"workflows": {}}, en.WF_06, runner=runner)
    assert wf["id"] == "LIVE"


def test_resolve_workflow_missing_raises_discovery():
    runner = ScriptedRunner([{"tags": []}], workflows=[])
    with pytest.raises(en.DiscoveryError):
        en.resolve_workflow({"workflows": {}}, en.WF_04, runner=runner)


# --------------------------------------------------------------------------- #
# Contact helpers
# --------------------------------------------------------------------------- #

def test_has_tag_case_insensitive():
    contact = {"tags": ["Podcast Completed Survey Style"]}
    assert en.has_tag(contact, "podcast completed survey style")


def test_url_field_is_set_list_shape():
    contact = {"customFields": [
        {"key": "contact.podcast_survey_episode_url", "value": "https://pb/x"}]}
    assert en.url_field_is_set(contact)


def test_url_field_is_set_false_when_empty():
    contact = {"customFields": [
        {"key": "contact.podcast_survey_episode_url", "value": ""}]}
    assert not en.url_field_is_set(contact)


# --------------------------------------------------------------------------- #
# Double-enrollment guard
# --------------------------------------------------------------------------- #

def test_double_enrollment_guard_skips_04_when_field_triggered():
    contact = {"id": "C1", "tags": ["Podcast Completed Survey Style",
                                    "podcast episode is ready"]}
    runner = ScriptedRunner([contact])
    res = en.enroll_episode(en.INTERVIEW_MODE, "C1", STATE, runner=runner,
                            preconditions=GOOD_GATE)
    assert res["workflows"][en.WF_04]["action"] == "none"
    # 04 was never explicitly enrolled.
    assert all("W04" not in c for c in
               [x for call in runner.enroll_calls() for x in call])
    assert res["verified"] is True


def test_04_explicitly_enrolled_when_field_trigger_absent():
    # First read: no 04 tag. Verify read: both tags present.
    runner = ScriptedRunner([
        {"id": "C2", "tags": []},
        {"id": "C2", "tags": ["Podcast Completed Survey Style",
                              "podcast episode is ready"]},
    ])
    res = en.enroll_episode(en.INTERVIEW_MODE, "C2", STATE, runner=runner,
                            preconditions=GOOD_GATE)
    assert res["workflows"][en.WF_04]["action"] == "enroll"
    assert any("W04" in call for call in runner.enroll_calls())
    assert res["verified"] is True


# --------------------------------------------------------------------------- #
# 06 tag-triggered path
# --------------------------------------------------------------------------- #

def test_06_tag_triggered_applies_tag_not_enroll():
    state = {
        "workflows": {
            en.WF_04: {"id": "W04", "trigger": "field:podcast_survey_episode_url"},
            en.WF_06: {"id": "W06", "trigger": "tag:podcast episode is ready"},
        },
    }
    contact = {"id": "C3", "tags": ["Podcast Completed Survey Style",
                                    "podcast episode is ready"]}
    runner = ScriptedRunner([contact])
    res = en.enroll_episode(en.INTERVIEW_MODE, "C3", state, runner=runner,
                            preconditions=GOOD_GATE)
    assert res["workflows"][en.WF_06]["action"] == "apply_tag"
    assert any(c[:2] == ["contacts", "add-tag"] for c in runner.calls)


# --------------------------------------------------------------------------- #
# Verification and failure
# --------------------------------------------------------------------------- #

def test_unverified_when_no_tag_and_enroll_rejected():
    state = {"workflows": {en.WF_04: {"id": "W04", "trigger": "direct_add"},
                           en.WF_06: {"id": "W06", "trigger": "direct_add"}}}
    runner = ScriptedRunner([{"id": "C4", "tags": []}], enroll_ok=False)
    with pytest.raises(en.EnrollmentError):
        en.enroll_episode(en.INTERVIEW_MODE, "C4", state, runner=runner,
                          preconditions=GOOD_GATE)


def test_direct_add_verified_by_api_ack_when_tag_absent():
    # Tags never appear, but enroll acks succeed -> verified by api_enroll_ack.
    state = {"workflows": {en.WF_04: {"id": "W04", "trigger": "direct_add"},
                           en.WF_06: {"id": "W06", "trigger": "direct_add"}}}
    runner = ScriptedRunner([{"id": "C5", "tags": []}], enroll_ok=True)
    res = en.enroll_episode(en.INTERVIEW_MODE, "C5", state, runner=runner,
                            preconditions=GOOD_GATE)
    assert res["verified"] is True
    assert res["workflows"][en.WF_04]["evidence"] == "api_enroll_ack"


def test_boundary_line_present_and_no_messaging_calls():
    contact = {"id": "C6", "tags": ["Podcast Completed Survey Style",
                                    "podcast episode is ready"]}
    runner = ScriptedRunner([contact])
    res = en.enroll_episode(en.INTERVIEW_MODE, "C6", STATE, runner=runner,
                            preconditions=GOOD_GATE)
    assert "STOP" in res["boundary"]
    # The engine never touches conversations/messages.
    joined = " ".join(x for call in runner.calls for x in call).lower()
    assert "conversation" not in joined and "message" not in joined


# --------------------------------------------------------------------------- #
# Rate limit
# --------------------------------------------------------------------------- #

def test_rate_limit_propagates_full_stop():
    def rate_runner(args: List[str]) -> en.CafResult:
        raise en.RateLimited("429", retry_after=15.0)

    with pytest.raises(en.RateLimited) as exc:
        en.enroll_episode(en.INTERVIEW_MODE, "C7", STATE, runner=rate_runner,
                          preconditions=GOOD_GATE)
    assert exc.value.retry_after == 15.0


# --------------------------------------------------------------------------- #
# Tier 3 REST fallback
# --------------------------------------------------------------------------- #

def test_rest_fallback_used_when_caf_enroll_fails(monkeypatch):
    calls = {"post": []}

    class _Resp:
        status_code = 200

    def fake_post(url, **kwargs):
        calls["post"].append({"url": url, **kwargs})
        return _Resp()

    import requests
    monkeypatch.setattr(requests, "post", fake_post)

    # caf enroll fails (rc!=0) but reads succeed; tags confirm on re-read.
    state = {"workflows": {en.WF_04: {"id": "W04", "trigger": "direct_add"},
                           en.WF_06: {"id": "W06", "trigger": "direct_add"}}}
    reads = [
        {"id": "C8", "tags": []},
        {"id": "C8", "tags": ["Podcast Completed Survey Style",
                              "podcast episode is ready"]},
    ]
    runner = ScriptedRunner(reads, enroll_ok=False)
    res = en.enroll_episode(en.INTERVIEW_MODE, "C8", state, runner=runner,
                            preconditions=GOOD_GATE,
                            rest_token="pit-token", location_id="LOC")
    assert res["verified"] is True
    assert calls["post"]  # REST fallback fired
    # The Authorization header carried the token but is never logged by us.
    assert calls["post"][0]["headers"]["Authorization"].startswith("Bearer ")


def test_rest_fallback_429_full_stop(monkeypatch):
    class _Resp:
        status_code = 429

    import requests
    monkeypatch.setattr(requests, "post", lambda url, **k: _Resp())
    with pytest.raises(en.RateLimited):
        en.enroll_via_rest("C9", "W1", "pit-token", "LOC")


def test_self_test_passes():
    assert en._self_test() is True
