"""MOCK-only unit tests — v2_dispatcher (the bounded Funnels-dept dispatcher).

These tests are MOCK-ONLY. The ``builder`` is an injected fake (NO seed/activate,
NO REST autosave, NO live GHL, NO browser, NO network). The canonical verifier is
driven through ghl_verify with an injected fetcher elsewhere; here we inject a
fake verifier OR pass pages that the real ghl_verify reduces with a stubbed
fetcher. The assertions cover the SOP §1 bounded-dispatcher CONTRACT:

  * the state machine backlog -> dispatched -> building -> verified | FAILED,
  * HARD max_inflight=1 (a task is left in backlog, never a 2nd concurrent build),
  * the wall-clock cap converts a HANG / over-long build into a FAILED (the
    HTTP-000-hang fix) — never an indefinite stall,
  * a crashed builder -> FAILED with the partial evidence + reason recorded,
  * the sub-account location gate failure blocks `verified` (NO-COMINGLING),
  * the telemetry-scrub gate blocks `verified` while a leak remains,
  * a clean build reaches `verified` and records the verdict honestly (a FAIL
    overall_pass is reported, never massaged to pass).

No real client/operator names, ids, emails, or location-ids appear.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import v2_dispatcher as disp
import ghl_verify as gv


FAKE_TASK = {"id": "taskFAKE", "brand": "Fictional Soap Co",
             "location_id": "LOCATIONfake0000", "brief": "build a funnel"}


def _fake_verifier(overall: bool, passed: int = 1, total: int = 1):
    """Injected verifier mirroring ghl_verify.verify_all's return contract."""
    def _v(evidence_root, pages, **kw):
        summary = {"overall_pass": overall, "passed": passed, "total": total,
                   "failed": total - passed}
        # Write the two canonical files so the evidence tree looks real.
        os.makedirs(os.path.join(evidence_root, "scorecard"), exist_ok=True)
        with open(os.path.join(evidence_root, "scorecard", "verify-summary.json"), "w") as f:
            json.dump(summary, f)
        return {"raw": [], "summary": summary, "raw_path": "", "summary_path": ""}
    return _v


def _builder_ok(pages=None, gate_ok=True, duration=10.0):
    pages = pages if pages is not None else [{"step": "optin", "preview_url": "u", "marker": "m"}]
    def _b(task, evidence_root):
        # A real builder writes ledgers as it goes; the fake writes a stub ledger.
        os.makedirs(os.path.join(evidence_root, "funnel"), exist_ok=True)
        with open(os.path.join(evidence_root, "funnel", "ledger.json"), "w") as f:
            json.dump({"built": True}, f)
        return {"pages": pages, "location_gate_ok": gate_ok, "duration_s": duration}
    return _b


# ── max_inflight = 1 (never a second concurrent build over the fixture) ───────

class TestMaxInflight:
    def test_left_in_backlog_when_inflight_full(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True), inflight_now=1, max_inflight=1)
        assert res.state == disp.STATE_BACKLOG
        assert "max_inflight" in res.reason
        # task-record.json reflects the backlog hold.
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["state"] == "backlog"


# ── wall-clock cap converts a hang / over-long build into FAILED ──────────────

class TestWallClockCap:
    def test_over_cap_is_failed_not_stall(self, tmp_path):
        # Builder "ran" 5000s — over the 1800s cap -> FAILED (the HTTP-000 fix).
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(duration=5000.0),
            verifier=_fake_verifier(True), wallclock_cap_s=1800)
        assert res.state == disp.STATE_FAILED
        assert "timeout" in res.reason
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["state"] == "FAILED"
        assert rec["build_duration_s"] == 5000.0

    def test_under_cap_proceeds(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(duration=10.0),
            verifier=_fake_verifier(True), wallclock_cap_s=1800)
        assert res.state == disp.STATE_VERIFIED


# ── a crashed builder -> FAILED with the reason recorded (evidence kept) ──────

class TestBuilderCrash:
    def test_builder_exception_is_failed(self, tmp_path):
        def _boom(task, root):
            raise RuntimeError("seed/activate failed")
        res = disp.dispatch_one(FAKE_TASK, str(tmp_path), builder=_boom,
                                verifier=_fake_verifier(True))
        assert res.state == disp.STATE_FAILED
        assert "builder raised" in res.reason
        assert "seed/activate failed" in res.reason


# ── sub-account location gate failure blocks `verified` (NO-COMINGLING) ───────

class TestLocationGate:
    def test_gate_not_ok_blocks_verified(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(gate_ok=False),
            verifier=_fake_verifier(True))
        assert res.state == disp.STATE_FAILED
        assert "location gate" in res.reason.lower()


# ── telemetry-scrub gate blocks `verified` while a leak remains ───────────────

class TestTelemetryGate:
    def test_leaked_telemetry_is_scrubbed_then_passes(self, tmp_path):
        # A dirty telemetry file is scrubbed by the gate; after scrub it is clean,
        # so the build proceeds to verified.
        tdir = tmp_path / "logs"
        tdir.mkdir()
        tfile = tdir / "agent-turn-3.out.json"
        tfile.write_text(json.dumps({"tools": ["redacted-client__messages_send"]}))
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True), telemetry_glob=[str(tfile)])
        assert res.state == disp.STATE_VERIFIED
        # The file on disk is now scrubbed clean.
        import scrub_turn_telemetry as scrub
        assert scrub.is_clean(tfile.read_text())


# ── clean build reaches verified; the verdict is recorded HONESTLY ────────────

class TestVerifiedHonestVerdict:
    def test_overall_pass_true_is_truthy_result(self, tmp_path):
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(True, passed=2, total=2))
        assert res.state == disp.STATE_VERIFIED
        assert bool(res) is True
        assert res.verify["overall_pass"] is True

    def test_overall_fail_recorded_not_massaged(self, tmp_path):
        # The build ran and verified, but the canonical verifier says FAIL (e.g.
        # markers didn't land). The dispatcher records verified-state WITH a False
        # overall_pass — it does NOT massage it to pass.
        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(),
            verifier=_fake_verifier(False, passed=1, total=6))
        assert res.state == disp.STATE_VERIFIED
        assert bool(res) is False              # truthiness requires overall_pass
        assert res.verify["overall_pass"] is False
        rec = json.load(open(os.path.join(tmp_path, "routing", "task-record.json")))
        assert rec["verify_overall_pass"] is False
        assert rec["verify_passed"] == 1 and rec["verify_total"] == 6


# ── integration with the REAL ghl_verify (injected fetcher, no network) ───────

class TestWithRealVerifier:
    def test_real_verifier_consistent_files(self, tmp_path):
        # Use the REAL ghl_verify.verify_all but inject a fake fetcher so no
        # network happens — proves the dispatcher + canonical verifier compose.
        pages = [{"step": "optin", "page_id": "P1", "preview_url": "u1", "marker": "m"},
                 {"step": "home", "page_id": "P2", "preview_url": "u2", "marker": "m"}]
        results = {"u1": {"ok": True, "http": 200, "marker_found": True, "url": "u1"},
                   "u2": {"ok": False, "http": 200, "marker_found": False, "url": "u2"}}

        def _fetch(url, marker):
            return results.get(url, {"ok": False, "http": None, "marker_found": False, "url": url})

        def _real_verifier(evidence_root, pgs, **kw):
            return gv.verify_all(evidence_root, pgs, fetcher=_fetch, **kw)

        res = disp.dispatch_one(
            FAKE_TASK, str(tmp_path), builder=_builder_ok(pages=pages),
            verifier=_real_verifier)
        assert res.state == disp.STATE_VERIFIED
        # 1/2 truth -> overall FAIL, reported honestly.
        assert res.verify["passed"] == 1 and res.verify["total"] == 2
        assert res.verify["overall_pass"] is False
        # The two canonical files exist and agree.
        raw = json.load(open(os.path.join(tmp_path, "logs", "final-preview-verify.json")))
        summary = json.load(open(os.path.join(tmp_path, "scorecard", "verify-summary.json")))
        gv.assert_consistent(summary, raw)
