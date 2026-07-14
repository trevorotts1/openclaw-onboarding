# test_cc_rail_contract.py — FIX-XC-05c: Skill-6 delivery-rail contract parity test.
#
# The presentations rail proves its board + gate wiring with `test_cc_contract.py`
# (mc_board) and a nonce-locked canonical entry. This test gives the Skill-6 GHL
# delivery rail the SAME provable spine, in two halves:
#
#   1. BOARD CONTRACT (cc_board.py) — a producer moves a card to `review` and can
#      NEVER post `done`; review->done belongs solely to the Command Center QC gate
#      (runQCOnReview, PASS >= 8.5). The status enum stays in parity with the CC
#      TaskStatus values, a disabled board is a clean no-op, and ingest routing is
#      deterministic. Transport (`_post_json`) is monkeypatched to a recorder so the
#      EXACT method/URL/payload the helper would put on the wire is asserted — never
#      a live board.
#
#   2. FRONT-DOOR / NONCE ENTRY DISCIPLINE (ghl_gate.py) — the building->verified
#      transition is gated on `ghl_gate.require_pass`, the UN-FAKEABLE verdict reader.
#      A hand-written or wrong-writer summary (no valid ghl_verify.verify_all
#      writer/run_nonce) can NEVER pass the front door; a MOCK verdict is rejected;
#      missing evidence fails closed; only a real writer+nonce+consistent PASS gets 0.
#
# Stdlib + pytest only, zero network.
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402
import ghl_gate  # noqa: E402
import ghl_verify  # noqa: E402

BASE = "https://demo.zerohumanworkforce.com"
ENV = {"MISSION_CONTROL_URL": BASE, "MC_API_TOKEN": "t"}

# The CC TaskStatus values this producer must stay in parity with. If the server
# enum changes, this tuple is the single place the contract test is updated.
CC_STATUS_ENUM = (
    "backlog", "inbox", "planning", "pending_dispatch",
    "assigned", "in_progress", "review", "testing",
    "blocked", "done",
)


class _Recorder:
    """Stand-in for cc_board._post_json. Records every (method, url, payload) and
    returns a scripted (status_code, body). GETs are never issued by cc_board, so
    every recorded call is a write the helper chose to make."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, cfg, method="POST"):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": "TASK-1", "deduped": False, "status": "backlog"}
        return 200, {"ok": True}

    def statuses_written(self):
        return [c["payload"]["status"] for c in self.calls
                if isinstance(c["payload"], dict) and "status" in c["payload"]]


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    monkeypatch.setattr(cc_board, "_post_json", r)
    return r


# ─────────────────────────────────────────────────────────────────────────────
# 1) BOARD CONTRACT — cc_board.py
# ─────────────────────────────────────────────────────────────────────────────
class TestBoardContract:
    def test_status_enum_parity(self):
        assert tuple(cc_board._CC_STATUS_VALUES) == CC_STATUS_ENUM, (
            "cc_board._CC_STATUS_VALUES drifted from the CC TaskStatus enum")
        assert "review" in cc_board._CC_STATUS_VALUES
        assert "done" in cc_board._CC_STATUS_VALUES

    def test_dispatch_state_maps_verified_to_review_not_done(self):
        assert cc_board.DISPATCH_STATE_TO_CC["verified"] == "review", (
            "a verified build must land at 'review', never 'done'")
        assert "done" not in cc_board.DISPATCH_STATE_TO_CC.values(), (
            "no dispatcher state may map straight to 'done'")
        assert cc_board.DISPATCH_STATE_TO_CC["FAILED"] == "blocked"

    def test_move_task_done_is_hard_blocked(self, rec):
        assert cc_board.move_task("TASK-1", "done", env=ENV) is False, (
            "move_task('done') must be refused — the QC gate is the only promoter")
        assert rec.calls == [], "a blocked 'done' must issue NO wire call at all"

    def test_update_status_done_is_hard_blocked(self, rec):
        assert cc_board.update_status("TASK-1", "done", env=ENV) is False
        assert rec.calls == [], "update_status('done') must issue NO wire call"

    def test_move_task_review_posts_review(self, rec):
        assert cc_board.move_task("TASK-1", "review", note="ready", env=ENV) is True
        assert rec.statuses_written() == ["review"]
        (call,) = rec.calls
        assert call["url"] == f"{BASE}/api/tasks/TASK-1/status"
        assert call["payload"]["status"] == "review"

    def test_update_status_for_state_verified_posts_review(self, rec):
        assert cc_board.update_status_for_state("TASK-1", "verified", env=ENV) is True
        assert rec.statuses_written() == ["review"]

    def test_build_phase_driver_artifact_posts_review_never_done(self, rec):
        driver = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        driver.artifact("https://demo.zerohumanworkforce.com/funnel/live")
        written = rec.statuses_written()
        assert "review" in written, "the phase driver must terminate at 'review'"
        assert "done" not in written, (
            "PRODUCER POSTED 'done' — the QC review column was skipped (THE bug)")
        # the terminal producer status is 'review' (in_progress from auto-start, then review)
        assert written[-1] == "review"

    def test_disabled_board_is_clean_noop(self, rec):
        # No MISSION_CONTROL_URL => board disabled; nothing may touch the wire.
        assert cc_board.ingest_task("Job", env={}) is None
        assert cc_board.update_status("TASK-1", "review", env={}) is False
        assert cc_board.move_task("TASK-1", "review", env={}) is False
        assert rec.calls == [], "a disabled board must touch the network NEVER"

    def test_ingest_routes_funnel_and_website(self, rec):
        cc_board.ingest_task("Funnel job", job_type="funnel", env=ENV)
        cc_board.ingest_task("Site job", job_type="website", env=ENV)
        depts = [c["payload"]["department_slug"] for c in rec.calls
                 if c["url"].endswith("/api/tasks/ingest")]
        assert depts == ["funnels", "web-development"], depts

    def test_invalid_status_never_reaches_wire(self, rec):
        assert cc_board.move_task("TASK-1", "not-a-status", env=ENV) is False
        assert cc_board.update_status("TASK-1", "bogus", env=ENV) is False
        assert rec.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# 1b) B-U7 — INGEST PARITY: optional persona fields on ingest_task()
# ─────────────────────────────────────────────────────────────────────────────
class TestIngestPersonaParity:
    """closes the Path-B structural divergence: cc_board.ingest_task() can now
    hand the Command Center the producer's already-resolved persona bundle
    (voice/topic/task ids + bundle sha) so the CC pins it instead of
    re-matching. voice_persona_id gates the whole group — mirrors
    report_persona_used's (B-U6) voice-required gate."""

    def _ingest_payload(self, rec, **kwargs):
        rec.calls.clear()
        cc_board.ingest_task("Persona parity job", job_type="website", env=ENV, **kwargs)
        (call,) = [c for c in rec.calls if c["url"].endswith("/api/tasks/ingest")]
        return call["payload"]

    def test_legacy_call_omits_all_persona_keys(self, rec):
        # B-U7 acceptance (b): absent fields → byte-identical legacy payload.
        payload = self._ingest_payload(rec)
        for key in ("voice_persona_id", "topic_persona_id", "task_persona_ids", "bundle_sha"):
            assert key not in payload, f"legacy payload must OMIT {key!r}, got {payload[key]!r}"

    def test_full_persona_payload_carries_every_field_verbatim(self, rec):
        # B-U7 acceptance (a): the producer's ids land on the wire verbatim.
        payload = self._ingest_payload(
            rec,
            voice_persona_id="hormozi-100m-offers",
            topic_persona_id="miller-building-storybrand",
            task_persona_ids=["hormozi-100m-offers", "wiebe-copy-hackers"],
            bundle_sha="abc123def456",
        )
        assert payload["voice_persona_id"] == "hormozi-100m-offers"
        assert payload["topic_persona_id"] == "miller-building-storybrand"
        assert payload["task_persona_ids"] == ["hormozi-100m-offers", "wiebe-copy-hackers"]
        assert payload["bundle_sha"] == "abc123def456"

    def test_voice_persona_id_required_for_the_whole_group(self, rec):
        # topic/task/sha with NO voice_persona_id → nothing to pin, so the
        # entire persona-fields group is withheld (legacy payload).
        payload = self._ingest_payload(
            rec,
            topic_persona_id="miller-building-storybrand",
            task_persona_ids=["hormozi-100m-offers"],
            bundle_sha="abc123def456",
        )
        for key in ("voice_persona_id", "topic_persona_id", "task_persona_ids", "bundle_sha"):
            assert key not in payload, f"no-voice payload must OMIT {key!r}, got {payload[key]!r}"

    def test_task_persona_ids_cleaned_and_never_sent_empty(self, rec):
        payload = self._ingest_payload(
            rec,
            voice_persona_id="hormozi-100m-offers",
            task_persona_ids=["  wiebe-copy-hackers  ", "", "   ", "miller-building-storybrand"],
        )
        assert payload["task_persona_ids"] == ["wiebe-copy-hackers", "miller-building-storybrand"]

        payload_empty = self._ingest_payload(rec, voice_persona_id="hormozi-100m-offers", task_persona_ids=[])
        assert "task_persona_ids" not in payload_empty, (
            "an empty task_persona_ids list must be omitted, never sent as []")


# ─────────────────────────────────────────────────────────────────────────────
# 2) FRONT-DOOR / NONCE ENTRY DISCIPLINE — ghl_gate.py
# ─────────────────────────────────────────────────────────────────────────────
def _write_evidence(root: Path, *, summary_over: dict | None = None,
                    raw=None, bind_raw_sha=False) -> Path:
    """Write a minimal machine-written evidence tree ghl_gate reads. Returns root.

    Defaults produce a well-formed, canonical-writer, LIVE, overall_pass=True tree
    with matching counts so the (mocked) consistency guard is satisfied."""
    raw = raw if raw is not None else [{"page_id": "P1", "pass": True}]
    (root / "scorecard").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    raw_path = root / ghl_verify.RAW_REL
    raw_path.write_text(json.dumps(raw), encoding="utf-8")
    summary = {
        "writer": ghl_verify._WRITER_ID,
        "run_nonce": "11111111-2222-3333-4444-555555555555",
        "trust": "LIVE",
        "overall_pass": True,
        "passed": 1, "total": 1, "failed": 0,
    }
    if bind_raw_sha:
        summary["raw_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if summary_over:
        summary.update(summary_over)
    (root / ghl_verify.SUMMARY_REL).write_text(json.dumps(summary), encoding="utf-8")
    return root


class TestFrontDoorNonceDiscipline:
    def test_missing_evidence_fails_closed(self, tmp_path):
        # Empty tree => required file missing => rc 4 (never a silent pass).
        assert ghl_gate.require_pass(str(tmp_path)) == 4

    def test_handwritten_summary_wrong_writer_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ghl_verify, "assert_consistent", lambda *a, **k: None)
        root = _write_evidence(tmp_path, summary_over={"writer": "hand-written-by-agent"})
        # rc 5 = writer/run_nonce invalid — a fabricated summary can't enter.
        assert ghl_gate.require_pass(str(root)) == 5

    def test_missing_run_nonce_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ghl_verify, "assert_consistent", lambda *a, **k: None)
        root = _write_evidence(tmp_path, summary_over={"run_nonce": ""})
        assert ghl_gate.require_pass(str(root)) == 5

    def test_mock_trust_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ghl_verify, "assert_consistent", lambda *a, **k: None)
        root = _write_evidence(tmp_path, summary_over={"trust": "MOCK"})
        assert ghl_gate.require_pass(str(root)) == 2

    def test_valid_front_door_pass(self, tmp_path, monkeypatch):
        # Real writer + nonce + LIVE trust + (mocked) consistent + overall_pass.
        monkeypatch.setattr(ghl_verify, "assert_consistent", lambda *a, **k: None)
        root = _write_evidence(tmp_path)
        assert ghl_gate.require_pass(str(root)) == 0

    def test_real_failure_reports_one_not_masked(self, tmp_path, monkeypatch):
        # A well-formed but failing build returns rc 1 — a real failure, distinct
        # from the fabrication/mock/missing codes (5/2/4).
        monkeypatch.setattr(ghl_verify, "assert_consistent", lambda *a, **k: None)
        root = _write_evidence(tmp_path, summary_over={"overall_pass": False})
        assert ghl_gate.require_pass(str(root)) == 1

    def test_expected_writer_is_the_canonical_verifier(self):
        # The front door is bound to ghl_verify.verify_all's identity — proving the
        # nonce discipline can't be re-pointed at some other writer.
        assert ghl_gate._EXPECTED_WRITER == ghl_verify._WRITER_ID == "ghl_verify.verify_all"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
