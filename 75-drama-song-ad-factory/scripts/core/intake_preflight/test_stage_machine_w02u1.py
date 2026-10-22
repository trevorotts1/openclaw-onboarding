#!/usr/bin/env python3
"""Regression suite for S75-W02-U1 (SPEC 8.1/8.2/8.6; D02, D03, D04, D33).

Run: python3 test_stage_machine_w02u1.py   (plain asserts, no framework)

Covers the acceptance rows:
  1. all-parked / all-failed / empty runs never report delivered
  2. mixed terminal states keep their reasons
  3. approval and provider events auto-continue the correct run
  4. an expired lease resumes via fenced reclaim with the old owner unable to write
  5. the complete 12-stage registry traverses with controlled fixtures through
     final delivery, including crashes and user revisions
  6. valid QC-record lists are read by the real reader without manual rewrites
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import factory as F  # noqa: E402
import state_store as ss  # noqa: E402

PASS = []


def ok(name):
    PASS.append(name)
    print("PASS  %s" % name)


# ── 1. false-completion selector: parked / failed / empty never delivered ────
def test_false_completion_never_delivered():
    # empty run
    got = {}
    d = F.select_next_action(got)
    delivered, report = F._decide_completion({
        "required": F.CANONICAL_STAGES, "optional": [], "stage_states": {},
        "approvals_current": True, "final_qc_independent_pass": True,
        "artifacts_present": True, "delivery_receipts_ok": True})
    assert d["all_complete"] is False, d
    assert delivered is False, report
    assert any("complete" in r for r in report["reasons"]), report

    # all-parked
    got = {s: "PARKED" for s in F.CANONICAL_STAGES}
    d = F.select_next_action(got)
    assert d["all_complete"] is False and d["verdict"] == "exhausted", d
    ev = {"required": list(F.CANONICAL_STAGES), "optional": [],
          "stage_states": d["stage_states"], "approvals_current": True,
          "final_qc_independent_pass": True, "artifacts_present": True,
          "delivery_receipts_ok": True}
    delivered, report = F._decide_completion(ev)
    assert delivered is False, report
    ok("all-parked never delivered")

    # all-failed
    got = {s: "FAILED_BLOCKED" for s in F.CANONICAL_STAGES}
    d = F.select_next_action(got)
    assert d["all_complete"] is False, d
    ev["stage_states"] = d["stage_states"]
    delivered, report = F._decide_completion(ev)
    assert delivered is False, report
    ok("all-failed never delivered")

    # empty (zero required) never delivered
    delivered, report = F._decide_completion({"required": [], "optional": [],
                                              "stage_states": {}})
    assert delivered is False and any("empty" in r for r in report["reasons"])
    ok("empty run never delivered")


# ── 2. mixed terminal states keep their reasons ─────────────────────────────
def test_mixed_terminal_keeps_reasons():
    got = {s: "COMPLETE" for s in F.CANONICAL_STAGES}
    got["video-generation"] = "PARKED"
    got["delivery"] = "FAILED_BLOCKED"
    d = F.select_next_action(got)
    assert d["verdict"] == "exhausted" and d["all_complete"] is False, d
    reasons = {n["stage"]: n["reason"] for n in d["not_runnable"]}
    assert "video-generation" in reasons and "delivery" in reasons, reasons
    assert "parked" in reasons["video-generation"], reasons
    assert "block" in reasons["delivery"] or "external" in reasons["delivery"], reasons
    ev = {"required": list(F.CANONICAL_STAGES), "optional": [],
          "stage_states": d["stage_states"], "approvals_current": True,
          "final_qc_independent_pass": True, "artifacts_present": True,
          "delivery_receipts_ok": True}
    delivered, report = F._decide_completion(ev)
    assert delivered is False
    assert any("video-generation" in r for r in report["reasons"]), report
    assert any("delivery" in r for r in report["reasons"]), report
    ok("mixed terminal states keep reasons")


# ── strict completion also requires approvals / final QC / artifacts / receipts
def test_strict_completion_requires_all_gates():
    base = {"required": list(F.CANONICAL_STAGES), "optional": [],
            "stage_states": {s: "complete" for s in F.CANONICAL_STAGES}}
    good = dict(base, approvals_current=True, final_qc_independent_pass=True,
                artifacts_present=True, delivery_receipts_ok=True)
    delivered, report = F._decide_completion(good)
    assert delivered is True, report
    for gate in ("approvals_current", "final_qc_independent_pass",
                 "artifacts_present", "delivery_receipts_ok"):
        bad = dict(good)
        bad[gate] = False
        delivered, report = F._decide_completion(bad)
        assert delivered is False, (gate, report)
    ok("strict completion requires approvals+finalQC+artifacts+receipts")


# ── 3. approval and provider events auto-continue the correct run ───────────
def test_events_auto_continue():
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run-A"
        (run / "control").mkdir(parents=True)
        db = run / "control" / "state.sqlite3"
        st = ss.Store(db)
        st.init_run("run-A", F.CANONICAL_STAGES)
        # research complete, creative-strategy ready -> next should be creative
        st.transition("run-A", "research", "READY", "w1")
        st.claim("run-A", "research", "w1", 60)
        st.transition("run-A", "research", "COMPLETE", "w1")
        st.close()

        a1 = F.continuation_enqueue(run, "approval", run_id="run-A")
        assert a1["verdict"] == "runnable" and a1["next_stage"] == "creative-strategy", a1
        assert a1["entrypoint"], a1
        q = F.drain_continuation(run)
        assert q and q[-1]["next_stage"] == "creative-strategy", q

        # a provider-completion event on music advances to continuity-bible
        st = ss.Store(db)
        for s in ("creative-strategy", "script-lyrics"):
            st.transition("run-A", s, "READY", "w1")
            st.claim("run-A", s, "w1", 60)
            st.transition("run-A", s, "COMPLETE", "w1")
        st.transition("run-A", "music", "READY", "w1")
        st.claim("run-A", "music", "w1", 60)
        st.transition("run-A", "music", "COMPLETE", "w1")
        st.close()
        a2 = F.continuation_enqueue(run, "provider-completion", run_id="run-A")
        assert a2["verdict"] == "runnable" and a2["next_stage"] == "continuity-bible", a2
        ok("approval + provider events auto-continue the correct run")


# ── 4. expired lease resumes via fenced reclaim; old owner cannot write ─────
def test_expired_lease_fenced_reclaim():
    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run-B"
        (run / "control").mkdir(parents=True)
        db = run / "control" / "state.sqlite3"
        st = ss.Store(db)
        st.init_run("run-B", [F.MUSIC])
        st.transition("run-B", F.MUSIC, "READY", "old", expected_version=None)
        row = st.claim("run-B", F.MUSIC, "old", lease_s=1, expected_version=None)
        old_version = row["version"]
        time.sleep(1.2)  # let the old lease expire

        # resume via the fenced claim path (music_stage action=resume -> RUNNING)
        res = F.music_stage(str(run), "new", "resume", run_id="run-B", lease_s=60)
        assert res["outcome"] == "ok" and res["reason_code"] == "music-resumed", res
        assert res["row"]["owner"] == "new", res["row"]

        # old owner can no longer write (fenced)
        try:
            st.heartbeat("run-B", F.MUSIC, "old", lease_s=10)
            raise AssertionError("old owner heartbeat must be fenced")
        except ss.StoreError as e:
            assert e.code in ("NOT_OWNER", "STALE_LEASE"), e.code
        try:
            st.transition("run-B", F.MUSIC, "QC", "old",
                          expected_version=old_version)
            raise AssertionError("old owner transition must be fenced")
        except ss.StoreError as e:
            assert e.code in ("VERSION_MISMATCH", "NOT_OWNER",
                              "ILLEGAL_TRANSITION"), e.code
        st.close()
        ok("expired lease fenced reclaim; old owner unable to write")


# ── 5. full registry traversal through final delivery (crash + revision) ────
def _make_full_run(run, stages=F.CANONICAL_STAGES):
    """Controlled fixture: complete every stage with the artifacts the
    strict-completion gate needs. Includes an independent final-QC record,
    current approvals, and delivery receipts."""
    (run / "control").mkdir(parents=True, exist_ok=True)
    reg = F.STAGE_REGISTRY
    plan = {"revision": "r7"}
    (run / "control" / "plan-revision.json").write_text(json.dumps(plan))
    approvals = {}
    for s in stages:
        entry = reg[s]
        for rel in entry["required_artifacts"]:
            p = run / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("artifact %s" % rel)
        if entry["approval_policy"] != "none":
            approvals[s] = {"state": "approved", "plan_revision": "r7"}
        (run / entry["required_artifacts"][0]).write_text("artifact")
    (run / "control" / "approvals.json").write_text(json.dumps(approvals))
    fq = run / "final-qc" / "record.json"
    fq.parent.mkdir(parents=True, exist_ok=True)
    fq.write_text(json.dumps({"gate": "PASS",
                              "producer": reg["final-qc"]["qc_producer"]}))
    rec = run / "delivery" / "receipts.json"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps([{"dest": "chat", "status": "delivered"}]))


def test_registry_traversal_and_completion():
    assert F.validate_registry() == [], F.validate_registry()
    ok("12-stage registry valid (all fields present)")

    with tempfile.TemporaryDirectory() as td:
        run = Path(td) / "run-C"
        _make_full_run(run)
        got = {s: "COMPLETE" for s in F.CANONICAL_STAGES}
        d = F.select_next_action(got)
        assert d["all_complete"] is True, d
        delivered, report = F.evaluate_completion(run, got)
        assert delivered is True, report
        ok("complete registry traverses through final delivery -> delivered")

        # user revision: a script-lyrics approval invalidated (plan bump) -> not delivered
        (run / "control" / "plan-revision.json").write_text(json.dumps({"revision": "r8"}))
        delivered, report = F.evaluate_completion(run, got)
        assert delivered is False and any("approvals" in r for r in report["reasons"]), report
        ok("user revision (stale approval) blocks delivery")

        # crash recovery: a mid-run crash leaves video-generation running ->
        # next is waiting/runnable, never a false delivered
        got2 = dict(got)
        got2["video-generation"] = "RUNNING"
        d2 = F.select_next_action(got2)
        assert d2["all_complete"] is False and d2["next_stage"] == "video-generation", d2
        delivered2, _ = F.evaluate_completion(run, got2)
        assert delivered2 is False
        ok("crash mid-run never reads as delivered")


# ── 6. valid QC-record lists read by the real reader ────────────────────────
def test_qc_records_list_reader():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "qc-records.json"
        recs = [{"check_id": "song-gate", "result": "pass"},
                {"check_id": "audio-present", "result": "pass"}]
        p.write_text(json.dumps(recs))
        got = F._read_json_list(p, required=True)
        assert got == recs, got

        # the dict-only reader must NOT swallow a list (D33): it returns default
        assert F._read_json(p, None) is None, "dict-only reader must not read a list"

        # a valid list with an unknown extra field is still readable
        recs2 = [{"check_id": "x", "result": "pass", "unknown_field": 1}]
        p.write_text(json.dumps(recs2))
        assert F._read_json_list(p) == recs2

        # wrong shape -> loud ShapeError, never a quiet empty
        p.write_text(json.dumps({"not": "a list"}))
        try:
            F._read_json_list(p, required=True)
            raise AssertionError("dict must raise ShapeError for a list reader")
        except F.ShapeError:
            pass
        # missing + required -> ShapeError; missing + not required -> []
        os.remove(p)
        try:
            F._read_json_list(p, required=True)
            raise AssertionError("missing required list must raise")
        except F.ShapeError:
            pass
        assert F._read_json_list(p, required=False) == []

        # independent required-checks: non-empty, and empty declaration refused
        assert F._required_checks("music"), "required checks must be non-empty"
        assert F._required_checks("no-such-stage") is None
        ok("QC-record lists read by the real reader; dict-only never coerces")


def main():
    test_false_completion_never_delivered()
    test_mixed_terminal_keeps_reasons()
    test_strict_completion_requires_all_gates()
    test_events_auto_continue()
    test_expired_lease_fenced_reclaim()
    test_registry_traversal_and_completion()
    test_qc_records_list_reader()
    print("\nALL %d CHECKS PASSED" % len(PASS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
