# test_cc_u9_tightenings.py — U9 §7 Command Center / Kanban tightenings.
#
# Proves the four U9 tightenings on the Skill-6 board producer, with the transport
# (_post_json) monkeypatched to a recorder so the EXACT wire calls are asserted and
# no network is touched:
#   §7.1 one card, phases as activities + MULTIPLE deliverables before review
#   §7.2 QC score emission INTO the card payload (post_qc_score)
#   §7.3 failure taxonomy prefix on blocked/backlog moves
#   §7.4 queue visibility → pending_dispatch naming the lock holder
#
# Stdlib + pytest only, zero network.
from __future__ import annotations

import os
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import cc_board  # noqa: E402

BASE = "https://demo.zerohumanworkforce.com"
ENV = {"MISSION_CONTROL_URL": BASE, "MC_API_TOKEN": "t"}


class _Recorder:
    """Records every (method, url, payload) and returns a scripted 2xx body."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, cfg, method="POST"):
        self.calls.append({"method": method, "url": url, "payload": payload})
        if url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": "TASK-1", "deduped": False, "status": "backlog"}
        return 200, {"ok": True}

    def statuses(self):
        return [c["payload"]["status"] for c in self.calls
                if isinstance(c["payload"], dict) and "status" in c["payload"]]

    def activities(self):
        return [c for c in self.calls if c["url"].endswith("/activities")]

    def deliverables(self):
        return [c for c in self.calls if c["url"].endswith("/deliverables")]


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    monkeypatch.setattr(cc_board, "_post_json", r)
    return r


# ─────────────────────────────────────────────────────────────────────────────
# §7.2 — QC score emission
# ─────────────────────────────────────────────────────────────────────────────
class TestQcEmission:
    def test_score_and_gate_in_payload(self, rec):
        assert cc_board.post_qc_score(
            "TASK-1", 8.5, "qc-built-form", scorecard_path="/e/sc.json", env=ENV
        ) is True
        (call,) = rec.activities()
        p = call["payload"]
        assert p["activity_type"] == "completed"
        assert "QC: 8.5/10 — qc-built-form" in p["message"]
        assert "[PASS]" in p["message"]
        md = p["metadata"]
        assert md["qc_score"] == 8.5
        assert md["qc_gate"] == "qc-built-form"
        assert md["qc_passed"] is True
        assert md["scorecard_path"] == "/e/sc.json"

    def test_sub_threshold_derives_fail(self, rec):
        cc_board.post_qc_score("TASK-1", 7.0, "qc-built-funnel", env=ENV)
        p = rec.activities()[0]["payload"]
        assert "[FAIL]" in p["message"]
        assert p["metadata"]["qc_passed"] is False

    def test_explicit_passed_overrides_threshold(self, rec):
        # A high score but an explicit fail verdict (e.g. a hard-miss gate) wins.
        cc_board.post_qc_score("TASK-1", 9.9, "qc-built-funnel", passed=False, env=ENV)
        p = rec.activities()[0]["payload"]
        assert "[FAIL]" in p["message"]
        assert p["metadata"]["qc_passed"] is False

    def test_scoreless_passed_only(self, rec):
        cc_board.post_qc_score("TASK-1", None, "render-gate", passed=True, env=ENV)
        p = rec.activities()[0]["payload"]
        assert p["message"].startswith("QC: render-gate [PASS]")
        assert "qc_score" not in p["metadata"]

    def test_clamp_and_coerce(self):
        assert cc_board._normalize_qc_score("9.2") == 9.2
        assert cc_board._normalize_qc_score(11) == 10.0
        assert cc_board._normalize_qc_score(-1) == 0.0
        assert cc_board._normalize_qc_score("") is None
        assert cc_board._normalize_qc_score(None) is None
        assert cc_board._normalize_qc_score("nope") is None

    def test_empty_task_id_noop(self, rec):
        assert cc_board.post_qc_score("", 9.0, "g", env=ENV) is False
        assert rec.calls == []

    def test_disabled_board_noop(self, rec):
        assert cc_board.post_qc_score("TASK-1", 9.0, "g", env={}) is False
        assert rec.calls == []


# ─────────────────────────────────────────────────────────────────────────────
# §7.3 — failure taxonomy
# ─────────────────────────────────────────────────────────────────────────────
class TestFailureTaxonomy:
    def test_taxonomy_set_is_exactly_the_spec(self):
        assert set(cc_board._CC_BLOCK_REASONS) == {
            "AUTH-STOP", "SELECTOR-MISS", "RATE-LIMIT",
            "TOKEN-CONTEXT", "PARKED", "VERIFY-FAIL",
        }

    def test_blocked_note_is_prefixed(self, rec):
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.fail(human_required=True, reason="verify-fail")  # case-insensitive
        blocked = [c for c in rec.calls if c["payload"].get("status") == "blocked"]
        assert blocked, "must move to blocked"
        assert blocked[0]["payload"]["note"].startswith("VERIFY-FAIL: ")
        act = [c for c in rec.activities()]
        assert act and act[0]["payload"]["metadata"]["block_reason"] == "VERIFY-FAIL"

    def test_invalid_reason_is_not_prefixed(self, rec):
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.fail(reason="made-up")  # not in taxonomy
        backlog = [c for c in rec.calls if c["payload"].get("status") == "backlog"]
        assert backlog
        first_token = str(backlog[0]["payload"]["note"]).split(":")[0]
        assert first_token not in cc_board._CC_BLOCK_REASONS

    def test_fail_without_reason_still_works(self, rec):
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        assert d.fail() is True or d.fail() is False  # fail-soft, never raises
        assert any(c["payload"].get("status") == "backlog" for c in rec.calls)


# ─────────────────────────────────────────────────────────────────────────────
# §7.4 — queue visibility
# ─────────────────────────────────────────────────────────────────────────────
class TestQueueVisibility:
    def test_pending_dispatch_names_holder(self, rec):
        assert cc_board.post_queue_wait("TASK-1", "ghl-skill6-LOC123", env=ENV) is True
        pend = [c for c in rec.calls if c["payload"].get("status") == "pending_dispatch"]
        assert pend, "must move to pending_dispatch"
        assert "ghl-skill6-LOC123" in pend[0]["payload"]["note"]
        act = rec.activities()[0]["payload"]
        assert act["metadata"]["holder_session"] == "ghl-skill6-LOC123"

    def test_empty_task_id_noop(self, rec):
        assert cc_board.post_queue_wait("", "holder", env=ENV) is False
        assert rec.calls == []

    def test_driver_queued_before_start(self, rec):
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.queued("ghl-skill6-LOC9")
        # queued() must not start the build (no in_progress yet).
        assert "in_progress" not in rec.statuses()
        assert "pending_dispatch" in rec.statuses()


# ─────────────────────────────────────────────────────────────────────────────
# §7.1 — multi-deliverable flow + never 'done'
# ─────────────────────────────────────────────────────────────────────────────
class TestMultiDeliverableFlow:
    def test_multiple_deliverables_then_review(self, rec):
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.start("build start")
        d.step(1, 2, "Step 1/2: scaffold")
        assert d.deliverable("https://x/preview", meta={"type": "preview_url"}) is True
        assert d.deliverable("https://x/embed", meta={"type": "embed_snippet"}) is True
        assert d._finished is False, "deliverable() must be non-terminal"
        assert len(rec.deliverables()) == 2
        assert d.review() is True
        assert d._finished is True
        # terminal status is review, never done.
        assert rec.statuses()[-1] == "review"
        assert "done" not in rec.statuses()

    def test_deliverable_after_review_is_noop(self, rec):
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.deliverable("https://x/a")
        d.review()
        assert d.deliverable("https://x/late") is False

    def test_artifact_one_shot_still_works(self, rec):
        # Backward-compat: the single-shot artifact() path is unchanged.
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.artifact("https://x/only", meta={"type": "survey_url"})
        assert rec.statuses()[-1] == "review"
        assert "done" not in rec.statuses()
        assert len(rec.deliverables()) == 1

    def test_qc_after_review_is_allowed(self, rec):
        # QC runs while the card sits at review — qc() must NOT be blocked by finish.
        d = cc_board.BuildPhaseDriver("TASK-1", env=ENV)
        d.artifact("https://x/only")
        assert d.qc(9.0, "qc-built-form", scorecard_path="/e/sc.json") is True
        completed = [c for c in rec.activities()
                     if c["payload"]["activity_type"] == "completed"
                     and "QC:" in c["payload"]["message"]]
        assert completed, "qc() must post a QC 'completed' activity even after review()"


def test_u9_selftest_exits_zero():
    assert cc_board._u9_selftest() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
