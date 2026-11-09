# test_ghl_meeting_rooms.py — WF26 Skill 6 Meeting Rooms (Document 1 §23).
#
# Maps to acceptance B06 (create/reuse, host identity, save/reopen), B07 (calendar
# reusable vs appointment-unique, no implicit Zoom migration) and B08 (guest/session
# isolation, AV/recording/transcript/summary/breakout readiness kept separate), plus
# IG-MEET-01..09. The live path is exercised through a FAKE UI state machine: no
# browser, no network, no GoHighLevel write. A fake is never reported as live proof.
import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import ghl_meeting_rooms as mr  # noqa: E402

StopAndReport = mr.StopAndReport

BASE_TASK = {
    "location_id": "SYNTHETIC_LOCATION",
    "host_user_id": "SYNTHETIC_HOST_USER",
    "purpose": "office hours",
    "room_link_mode": "reusable",
}


class FakeCalendar:
    """Skill-44 calendar stand-in. Returns only what the scenario declares observed."""

    def __init__(self, links=("https://join/a", "https://join/b"), existing=None,
                 reschedule=True, cancel=True):
        self.links = list(links)
        self.existing = existing
        self.reschedule_observed = reschedule
        self.cancel_observed = cancel
        self.booking_link = "https://book.example/cal"
        self._n = 0

    def read_appointment(self, calendar_id=None, appointment_id=None):
        return self.existing or {}

    def create_test_appointment(self, calendar_id=None, sequence=1, plan=None):
        link = self.links[sequence - 1] if sequence - 1 < len(self.links) else ""
        self._n += 1
        return {"appointment_id": f"appt-{self._n}", "join_url": link}

    def reschedule(self, appointment_id=None, sequence=1):
        return {"appointment_id": appointment_id, "observed": self.reschedule_observed,
                "stale_links": []}

    def cancel(self, appointment_id=None, sequence=2):
        return {"appointment_id": appointment_id, "observed": self.cancel_observed,
                "stale_links": []}


class FakeBrowserManager:
    """Minimal shared-browser-manager stand-in. No process, no page, no network."""

    def __init__(self):
        self.session = "ghl-skill6-synthetic-location"

    def session_name(self, location_id):
        return self.session

    def headless_guard(self):
        return None

    def assert_agent_browser_version(self):
        return None

    def browser_session(self, location_id):
        session = self.session

        class _Ctx:
            def __enter__(self):
                return session

            def __exit__(self, *_exc):
                return False

        return _Ctx()


def _sub_results(**overrides):
    out = {k: mr.STATE_NOT_RUN for k in mr.SUB_RESULT_KEYS}
    out.update(overrides)
    return out


def _walk_selectors(node, path="meeting_room"):
    if isinstance(node, dict):
        if "status" in node and "anchor" in node:
            yield path, node
            return
        for key, value in node.items():
            if str(key).startswith("_"):
                continue
            yield from _walk_selectors(value, f"{path}.{key}")


# ---------------------------------------------------------------------------
# Plan + preflight (B06, IG-MEET-01)
# ---------------------------------------------------------------------------
def test_plan_requires_host_identity_and_never_defaults_to_operator():
    plan = mr.plan_room(dict(BASE_TASK))
    assert plan["host_user_id"] == "SYNTHETIC_HOST_USER"
    assert plan["room_link_mode"] == "reusable"
    with pytest.raises(StopAndReport) as exc:
        mr.plan_room({"location_id": "SYNTHETIC_LOCATION"})
    assert exc.value.step == "plan.host_user_id"
    assert "never defaulted" in exc.value.reason.lower()


def test_plan_accepts_only_secret_reference_not_a_literal_passcode():
    with pytest.raises(StopAndReport) as exc:
        mr.plan_room(dict(BASE_TASK, passcode="1234"))
    assert "passcode_secret_reference" in exc.value.reason

    plan = mr.plan_room(dict(BASE_TASK, passcode_secret_reference="vault://meet/passcode"))
    assert plan["passcode_secret_reference"] == "vault://meet/passcode"
    assert "passcode" not in plan
    assert "1234" not in json.dumps(plan)


def test_plan_link_modes_are_internal_labels():
    for mode in mr.ROOM_LINK_MODES:
        task = dict(BASE_TASK, room_link_mode=mode)
        if mode == "existing_room":
            task["existing_room_reference"] = "Coaching Room"
        assert mr.plan_room(task)["room_link_mode"] == mode

    with pytest.raises(StopAndReport):
        mr.plan_room(dict(BASE_TASK, room_link_mode="zoom"))
    with pytest.raises(StopAndReport):
        mr.plan_room(dict(BASE_TASK, room_link_mode="existing_room"))


def test_preflight_blocks_transcription_without_approval_reference():
    plan = mr.plan_room(dict(BASE_TASK, transcription_policy="on"))
    blocked = mr.preflight(plan)
    assert blocked["pass"] is False
    assert "approval" in blocked["stop_reason"].lower()

    approved = mr.plan_room(dict(BASE_TASK, transcription_policy="on",
                                 approval_references=["APPROVED-1"]))
    assert mr.preflight(approved)["pass"] is True


def test_plan_schema_matches_frozen_checkpoint_file():
    schema = mr.plan_room_schema()
    sample = mr.plan_room(dict(BASE_TASK))
    assert set(schema["properties"]) == set(sample)
    assert schema["properties"]["room_link_mode"]["enum"] == list(mr.ROOM_LINK_MODES)

    frozen = json.loads((TOOLS_DIR / "meeting-room-plan.schema.json").read_text(encoding="utf-8"))
    assert frozen == schema, (
        "the frozen WF26-CP01 room-plan schema drifted from plan_room(); "
        "regenerate with ghl_meeting_rooms.write_plan_schema()")


# ---------------------------------------------------------------------------
# Dedicated selector map + D8 (B06)
# ---------------------------------------------------------------------------
def test_selector_map_is_dedicated_and_every_target_is_honest():
    sels = mr.load_selectors()
    legend = set(sels["_status_legend"])
    keys = set()
    for path, node in _walk_selectors(sels["meeting_room"]):
        keys.add(path)
        assert node["status"] in legend, path
        if node["status"] == "capture-pending":
            assert node.get("conf") == 0, path
            assert node.get("fallbacks"), f"{path} must carry a capture recipe"
        assert "community" not in path and "course" not in path, path
    assert keys, "the meeting selector map must not be empty"

    report = mr.selector_status_report()
    assert report["locked_count"] == 0, "this lane captured nothing live"
    assert report["capture_complete"] is False


def test_click_list_names_only_dedicated_selector_paths():
    plan = mr.plan_room(dict(BASE_TASK, cohost_user_ids=["coach-2"], allow_guests=True,
                             passcode_secret_reference="vault://meet/pw",
                             calendar_id="cal-1", room_link_mode="appointment_unique",
                             migration_authorization="MIG-1"))
    click = mr.emit_click_list(plan)
    sels = mr.load_selectors()
    targets = [s["target"] for s in click["steps"] if s["target"].startswith("meeting_room.")]
    assert targets, "the click list must name selector paths"
    for dotted in targets:
        assert mr._target_present(sels, dotted), dotted
        assert "community" not in dotted and "course" not in dotted
        assert "#" not in dotted and ">" not in dotted, "no raw CSS selectors"
    assert click["browser_policy"] == mr.BROWSER_POLICY


def test_d8_gate_stops_on_capture_pending_with_meeting_capture_guidance(tmp_path):
    plan = mr.plan_room(dict(BASE_TASK))
    sels = mr.load_selectors()
    with pytest.raises(StopAndReport) as exc:
        mr.anchor(sels, "meeting_room.my_room.create_room_button")
    assert "Meeting Rooms" in exc.value.reason
    assert "capture" in exc.value.reason.lower()
    # An OPTIONAL pending target is skipped, never guessed.
    assert mr.anchor(sels, "meeting_room.my_room.create_room_button", required=False) == ""


# ---------------------------------------------------------------------------
# Reuse decision (B06, IG-MEET-01)
# ---------------------------------------------------------------------------
def test_reuse_prefers_an_owned_room_and_ignores_other_hosts_rooms():
    plan = mr.plan_room(dict(BASE_TASK))
    owned = mr.reuse_decision(plan, [
        {"name": "Office Hours", "owner_user_id": "SYNTHETIC_HOST_USER",
         "join_url": "https://join/owned"}])
    assert owned["action"] == "reuse"
    assert "owned" in owned["reason"].lower() or "approved" in owned["reason"].lower()

    others = mr.reuse_decision(plan, [
        {"name": "Office Hours", "owner_user_id": "someone-else",
         "join_url": "https://join/other"}])
    assert others["action"] == "create"
    assert others["room"] is None
    assert "other users" in others["note"]


def test_existing_room_mode_blocks_when_the_reference_is_not_owned():
    plan = mr.plan_room(dict(BASE_TASK, room_link_mode="existing_room",
                             existing_room_reference="Coaching"))
    decision = mr.reuse_decision(plan, [
        {"name": "Coaching", "owner_user_id": "someone-else"}])
    assert decision["action"] == "blocked"
    assert "owned by host" in decision["reason"]


# ---------------------------------------------------------------------------
# Save/reopen + host identity (B06, IG-MEET-02)
# ---------------------------------------------------------------------------
def test_save_reopen_requires_name_and_owner_on_the_reopened_surface(monkeypatch):
    plan = mr.plan_room(dict(BASE_TASK))

    monkeypatch.setattr(mr, "_snapshot", lambda session, timeout=20: "Office Hours")
    sub = _sub_results()
    warnings = []
    mr._verify_saved_and_reopened("s", plan, sub, warnings)
    assert sub["configuration_saved_and_reopened"] == mr.STATE_VERIFIED
    assert sub["host_identity_verified"] == mr.STATE_NOT_RUN
    assert any("host identity" in w or "host ownership" in w for w in warnings)

    monkeypatch.setattr(mr, "_snapshot",
                        lambda session, timeout=20: "Office Hours — SYNTHETIC_HOST_USER")
    sub2 = _sub_results()
    mr._verify_saved_and_reopened("s", plan, sub2, [])
    assert sub2["host_identity_verified"] == mr.STATE_VERIFIED


def test_secret_value_never_reaches_evidence(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps({"room": "Office Hours"}), encoding="utf-8")
    assert mr.assert_no_secret_leak(str(tmp_path), ["SUPER-SECRET-9"]) == []

    (tmp_path / "leak.json").write_text(json.dumps({"passcode": "SUPER-SECRET-9"}),
                                        encoding="utf-8")
    leaks = mr.assert_no_secret_leak(str(tmp_path), ["SUPER-SECRET-9"])
    assert len(leaks) == 1 and leaks[0].endswith("leak.json")


def test_cleanup_deletes_only_a_created_room_under_explicit_authorization(monkeypatch):
    plan = mr.plan_room(dict(BASE_TASK))
    warnings = []

    existing = mr._cleanup("s", mr.load_selectors(), plan, created=False, warnings=warnings)
    assert existing["attempted"] is False and existing["deleted"] is False
    assert "nothing created" in existing["note"]

    unauth = mr._cleanup("s", mr.load_selectors(), plan, created=True, warnings=warnings)
    assert unauth["attempted"] is False and unauth["deleted"] is False
    assert any("authorization" in w for w in warnings)

    monkeypatch.setattr(mr, "anchor", lambda sels, dotted, required=True: "fake-anchor")
    monkeypatch.setattr(mr._cb, "_ex_click",
                        lambda *a, **k: {"ok": True, "path": "fake"})
    authorised = mr._cleanup("s", mr.load_selectors(),
                             dict(plan, cleanup_authorization="CLEAN-1"),
                             created=True, warnings=[])
    assert authorised["deleted"] is True
    assert authorised["authorization"] == "CLEAN-1"


# ---------------------------------------------------------------------------
# Guest isolation (B08, IG-MEET-03)
# ---------------------------------------------------------------------------
def test_guest_check_refuses_a_shared_host_session():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results()
    warnings = []
    out = mr._guest_check(plan, {"guest_context": lambda url, plan=None: {
        "isolated": False, "joined": True}}, "https://join/x", sub, warnings)
    assert out["isolated"] is False
    assert sub["guest_join_flow_verified"] == mr.STATE_FAILED
    assert warnings


def test_guest_check_without_an_isolated_context_stays_pending():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results()
    warnings = []
    mr._guest_check(plan, {}, "https://join/x", sub, warnings)
    assert sub["guest_join_flow_verified"] == mr.STATE_PENDING
    assert any("host session" in w for w in warnings)


def test_guest_check_verifies_only_an_isolated_join():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results()
    mr._guest_check(plan, {"guest_context": lambda url, plan=None: {
        "isolated": True, "joined": True, "waiting_room": True}},
        "https://join/x", sub, [])
    assert sub["guest_join_flow_verified"] == mr.STATE_VERIFIED


# ---------------------------------------------------------------------------
# Rehearsal + AV honesty (B08, IG-MEET-06)
# ---------------------------------------------------------------------------
def test_rehearsal_never_claims_live_av_from_devices_alone():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results()
    warnings = []
    mr._rehearsal(plan, {"media_devices": lambda: {"audio": True, "video": True}},
                  sub, warnings)
    assert sub["live_audio_video_verified"] == mr.STATE_PENDING
    assert any("no rehearsal was observed" in w for w in warnings)


def test_rehearsal_without_devices_is_pending_not_failed():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results()
    warnings = []
    mr._rehearsal(plan, {"media_devices": lambda: {"audio": False, "video": False}},
                  sub, warnings)
    assert sub["live_audio_video_verified"] == mr.STATE_PENDING
    assert any("no usable microphone" in w for w in warnings)


def test_rehearsal_verifies_only_an_observed_media_result():
    plan = mr.plan_room(dict(BASE_TASK, requested_outputs=["screen_sharing_verified"]))
    sub = _sub_results()
    mr._rehearsal(plan, {"media_devices": lambda: {"audio": True, "video": True},
                         "rehearsal_observation": lambda: {
                             "audio": True, "video": True, "screen": True}},
                  sub, [])
    assert sub["live_audio_video_verified"] == mr.STATE_VERIFIED
    assert sub["screen_sharing_verified"] == mr.STATE_VERIFIED


# ---------------------------------------------------------------------------
# Calendar / integration (B07, IG-MEET-04, IG-MEET-05, IG-MEET-09)
# ---------------------------------------------------------------------------
def test_reusable_mode_records_only_an_observed_link():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results()
    out = mr._calendar_branch(plan, {"calendar": FakeCalendar(existing={
        "meeting_location": "Meeting Room", "join_url": "https://join/reuse"})}, sub, [])
    assert sub["calendar_link_generation_verified"] == mr.STATE_VERIFIED
    assert out["reusable_link"] == "https://join/reuse"

    sub2 = _sub_results()
    warnings = []
    mr._calendar_branch(plan, {"calendar": FakeCalendar(existing={})}, sub2, warnings)
    assert sub2["calendar_link_generation_verified"] == mr.STATE_PENDING
    assert any("not observed" in w or "never fabricated" in w for w in warnings)


def test_appointment_unique_requires_two_different_observed_links():
    plan = mr.plan_room(dict(BASE_TASK, room_link_mode="appointment_unique"))
    sub = _sub_results()
    out = mr._calendar_branch(plan, {"calendar": FakeCalendar()}, sub, [])
    assert out["links"] == ["https://join/a", "https://join/b"]
    assert sub["calendar_link_generation_verified"] == mr.STATE_VERIFIED
    assert sub["reschedule_and_cancellation_verified"] == mr.STATE_VERIFIED

    sub_dup = _sub_results()
    warnings = []
    mr._calendar_branch(plan, {"calendar": FakeCalendar(
        links=("https://join/same", "https://join/same"))}, sub_dup, warnings)
    assert sub_dup["calendar_link_generation_verified"] == mr.STATE_NOT_RUN
    assert any("SAME link" in w for w in warnings)


def test_reschedule_and_cancel_are_not_presumed():
    plan = mr.plan_room(dict(BASE_TASK, room_link_mode="appointment_unique"))
    sub = _sub_results()
    warnings = []
    mr._calendar_branch(plan, {"calendar": FakeCalendar(reschedule=False, cancel=False)},
                        sub, warnings)
    assert sub["reschedule_and_cancellation_verified"] == mr.STATE_PENDING
    assert any("NOT observed" in w for w in warnings)


def test_existing_zoom_link_is_preserved_without_migration_authorization():
    plan = mr.plan_room(dict(BASE_TASK, calendar_id="cal-1"))
    sub = _sub_results()
    warnings = []
    out = mr._calendar_branch(plan, {"calendar": FakeCalendar(existing={
        "meeting_location": "Zoom", "join_url": "https://zoom.example/x"})}, sub, warnings)
    assert sub["calendar_link_generation_verified"] == mr.STATE_PENDING
    assert any("migration_authorization" in w for w in warnings)
    assert out["existing"]["meeting_location"] == "Zoom"

    allowed = mr.plan_room(dict(BASE_TASK, calendar_id="cal-1",
                                migration_authorization="MIG-APPROVED-1"))
    sub2 = _sub_results()
    out2 = mr._calendar_branch(allowed, {"calendar": FakeCalendar(
        existing={"meeting_location": "Zoom", "join_url": "https://zoom.example/x"})},
        sub2, [])
    assert out2["reusable_link"] == "https://zoom.example/x"


def test_no_calendar_adapter_records_pending_instead_of_guessing():
    plan = mr.plan_room(dict(BASE_TASK, room_link_mode="appointment_unique"))
    sub = _sub_results()
    warnings = []
    mr._calendar_branch(plan, {}, sub, warnings)
    assert sub["calendar_link_generation_verified"] == mr.STATE_PENDING
    assert sub["reschedule_and_cancellation_verified"] == mr.STATE_PENDING
    assert any("calendar adapter" in w for w in warnings)


# ---------------------------------------------------------------------------
# Outputs (B08, IG-MEET-07) and breakout (IG-MEET-08)
# ---------------------------------------------------------------------------
def test_recording_transcript_summary_and_followup_are_separate_results():
    plan = mr.plan_room(dict(BASE_TASK, recording_policy="on",
                             transcription_policy="off_unless_approved",
                             approval_references=["APPROVED-REC-1"],
                             requested_outputs=["recording_verified",
                                                "transcript_verified",
                                                "follow_up_task_creation_verified"]))
    sub = _sub_results(recording_verified=mr.STATE_NOT_RUN,
                       transcript_verified=mr.STATE_NOT_RUN,
                       follow_up_task_creation_verified=mr.STATE_NOT_RUN)
    warnings = []
    mr._recording_branch(plan, {}, sub, warnings)

    assert sub["recording_verified"] == mr.STATE_PENDING
    assert sub["transcript_verified"] == mr.STATE_NOT_REQUESTED
    assert sub["follow_up_task_creation_verified"] == mr.STATE_PENDING
    assert any("recording alone" in w for w in warnings)
    assert any("follow-up" in w for w in warnings)


def test_breakout_created_is_never_reported_as_participants_inside():
    plan = mr.plan_room(dict(BASE_TASK, breakout_requested=True))
    assert plan["sub_results"]["breakout_opened_verified"] == mr.STATE_NOT_RUN

    sub = _sub_results(breakout_opened_verified=mr.STATE_NOT_RUN)
    warnings = []
    out = mr._rehearsal(plan, {"media_devices": lambda: {"audio": False, "video": False}},
                        sub, warnings)
    assert out["breakout"]["opened"] is None
    assert out["breakout"]["participants_inside"] is None
    assert sub["breakout_opened_verified"] != mr.STATE_VERIFIED
    assert any("assignment is not an active session" in w for w in warnings)


# ---------------------------------------------------------------------------
# Honest status assembly (B06-B08)
# ---------------------------------------------------------------------------
def test_finalize_blocks_a_failed_requested_sub_result():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results(configuration_saved_and_reopened=mr.STATE_VERIFIED,
                       host_identity_verified=mr.STATE_VERIFIED,
                       guest_join_flow_verified=mr.STATE_FAILED)
    result = mr.finalize_result(plan, sub)
    assert result["status"] == mr.STATUS_BLOCKED
    assert "guest_join_flow_verified" in result["unmet_sub_results"]
    assert any("FAILED" in w for w in result["warnings"])


def test_finalize_reports_setup_verified_with_live_av_pending():
    plan = mr.plan_room(dict(BASE_TASK))
    sub = _sub_results(configuration_saved_and_reopened=mr.STATE_VERIFIED,
                       host_identity_verified=mr.STATE_VERIFIED)
    result = mr.finalize_result(plan, sub)
    assert result["status"] == mr.STATUS_SETUP_VERIFIED
    assert result["live_av_status"] == mr.LIVE_AV_PENDING


# ---------------------------------------------------------------------------
# Dry run + the fake-UI live walk (B06, B08)
# ---------------------------------------------------------------------------
def test_dry_run_writes_the_plan_artifacts_and_never_claims_verification(tmp_path):
    result = mr.build_meeting_room(dict(BASE_TASK), str(tmp_path), dry_run=True)
    assert result["ok"] is True
    assert result["status"] == mr.STATUS_PLANNED
    assert result["setup_verified"] is False
    assert result["live_av_status"] == mr.LIVE_AV_PENDING
    assert result["dry_run"] is True
    routing = tmp_path / "routing"
    for name in ("meeting-room-plan.json", "meeting-room-click-list.json",
                 "meeting-room-preflight.json", "meeting-room-subresults.json"):
        assert (routing / name).is_file(), name
    assert result["selector_status"]["capture_complete"] is False
    plan = json.loads((routing / "meeting-room-plan.json").read_text(encoding="utf-8"))
    assert plan["host_user_id"] == "SYNTHETIC_HOST_USER"


def _fake_ui_deps(**overrides):
    deps = {
        "seed_and_land": lambda session, location_id, root: {"landed": True},
        "close": lambda location_id: None,
        "room_inventory": lambda session, sels: [{
            "name": "Office Hours", "owner_user_id": "SYNTHETIC_HOST_USER",
            "join_url": "https://join/reuse"}],
        "guest_context": lambda url, plan=None: {"isolated": True, "joined": True,
                                                 "waiting_room": True},
        "media_devices": lambda: {"audio": True, "video": True},
        "rehearsal_observation": None,
        "calendar": FakeCalendar(existing={"meeting_location": "Meeting Room",
                                          "join_url": "https://join/reuse"}),
        "follow_up_tasks": None,
        "resolve_secret": None,
        "secret_values": [],
    }
    deps.update(overrides)
    return deps


def test_live_walk_reuses_a_room_and_returns_setup_verified(monkeypatch, tmp_path):
    monkeypatch.setenv("GHL_LOCATION_ID", "SYNTHETIC_LOCATION")
    monkeypatch.setattr(mr._ffb, "browser_manager", FakeBrowserManager())
    monkeypatch.setattr(mr, "anchor", lambda sels, dotted, required=True: "fake-anchor")
    monkeypatch.setattr(mr._cb, "_ex_click", lambda *a, **k: {"ok": True, "path": "fake"})
    monkeypatch.setattr(mr._cb, "_ex_fill", lambda *a, **k: {"ok": True, "path": "fake"})
    monkeypatch.setattr(mr, "_snapshot",
                        lambda session, timeout=20: "Office Hours — SYNTHETIC_HOST_USER")

    result = mr.build_meeting_room(dict(BASE_TASK), str(tmp_path), dry_run=False,
                                   deps=_fake_ui_deps())

    assert result["status"] == mr.STATUS_SETUP_VERIFIED, result.get("warnings")
    assert result["live_av_status"] == mr.LIVE_AV_PENDING
    assert result["reuse"]["action"] == "reuse"
    assert result["sub_results"]["host_identity_verified"] == mr.STATE_VERIFIED
    assert result["sub_results"]["guest_join_flow_verified"] == mr.STATE_VERIFIED
    assert result["sub_results"]["calendar_link_generation_verified"] == mr.STATE_VERIFIED
    assert result["sub_results"]["live_audio_video_verified"] == mr.STATE_PENDING
    assert result["delivery"]["guest_join_link"] == "https://join/reuse"
    assert result["cleanup"]["deleted"] is False
    routing = tmp_path / "routing"
    for name in ("meeting-room-reopen.json", "meeting-room-integration.json",
                 "meeting-room-guest.json", "meeting-room-rehearsal.json",
                 "meeting-room-delivery.json", "meeting-room-cleanup.json"):
        assert (routing / name).is_file(), name


def test_live_walk_creates_then_cleans_up_only_with_authorization(monkeypatch, tmp_path):
    monkeypatch.setenv("GHL_LOCATION_ID", "SYNTHETIC_LOCATION")
    monkeypatch.setattr(mr._ffb, "browser_manager", FakeBrowserManager())
    monkeypatch.setattr(mr, "anchor", lambda sels, dotted, required=True: "fake-anchor")
    monkeypatch.setattr(mr._cb, "_ex_click", lambda *a, **k: {"ok": True, "path": "fake"})
    monkeypatch.setattr(mr._cb, "_ex_fill", lambda *a, **k: {"ok": True, "path": "fake"})
    monkeypatch.setattr(mr, "_snapshot",
                        lambda session, timeout=20: "Scratch Rehearsal — SYNTHETIC_HOST_USER")

    task = dict(BASE_TASK, purpose="Scratch Rehearsal", cleanup_authorization="CLEAN-42")
    result = mr.build_meeting_room(task, str(tmp_path), dry_run=False,
                                   deps=_fake_ui_deps(room_inventory=lambda s, sel: []))

    assert result["status"] == mr.STATUS_SETUP_VERIFIED, result.get("warnings")
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["deleted"] is True
    assert result["cleanup"]["authorization"] == "CLEAN-42"


def test_live_walk_stops_on_capture_pending_selector(monkeypatch, tmp_path):
    """D8: with the REAL executor gate and an uncaptured map, the walk must STOP and
    report BLOCKED — never fabricate a click or a success."""
    monkeypatch.setenv("GHL_LOCATION_ID", "SYNTHETIC_LOCATION")
    monkeypatch.setattr(mr._ffb, "browser_manager", FakeBrowserManager())

    result = mr.build_meeting_room(dict(BASE_TASK), str(tmp_path), dry_run=False,
                                   deps=_fake_ui_deps())

    assert result["ok"] is False
    assert result["status"] == mr.STATUS_BLOCKED
    reason = (result.get("stop_reason") or "").lower()
    assert "not been captured live" in reason or "capture" in reason
    assert "meeting room" in reason
