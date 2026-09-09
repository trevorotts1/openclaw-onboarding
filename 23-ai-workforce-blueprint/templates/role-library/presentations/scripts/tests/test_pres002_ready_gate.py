"""PRES-002 -- the runtime predecessor-success gate + persisted edge graph
(2026-09-09, W2 WF06).

TODO.md PRES-002 acceptance, proven here on real python -c script executors
(wall-clock controllable, artifact-writing, honest files -- no simulated
attestation is ever minted; the same discipline test_pres036_ready_queue uses):

  1. A -> C plus independent B: force A to fail; B completes, C is called ZERO
     times, and the exact blocking edge is visible (state phases[C]
     .waiting_dependency naming A, plus the event log row).
  2. Repair A; only A and C run -- B stays DONE (banked, skipped), A re-runs,
     C runs for the first time. C's pred_input_hashes stamp carries A's fresh
     banked sha256.
  3. A quick -> C and B slow: C is ADMITTED while B is still RUNNING (the
     admission tick sees B in the running list) -- prerequisite-pass
     admission, no barrier behind unrelated slow peers.
  4. A stale prior A artifact after a NEW A failure cannot unlock C: A fails
     while a stale artifact from an earlier life still sits on disk; C never
     runs even though C's input file path exists -- the predicate re-validates
     A's banked hashes at admission time and the stale file does not match
     what A banked (A quarantined with nothing banked).
  5. An explicit client-declined OPTIONAL branch defers only its documented
     descendants: a defers_unless producer is deferred, and its consumer --
     itself defers_unless-gated on the same answer -- is deferred too (never
     run, never blocked-with-reason); an UNRELATED phase still completes.

Rollback: PRESENTATION_DAG_ADMISSION=0 selects the pre-fix run_phase
byte-for-byte (the gate returns None before any check).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_OK  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: real python -c script executors over a scratch manifest (same
# discipline as tests/test_pres036_ready_queue.py -- honest artifacts, no
# simulated attestations, wall-clock controllable).
# ---------------------------------------------------------------------------
def _cmd_that_writes(target: str, delay: float = 0.0) -> str:
    d = json.dumps(target)
    body = (f"import time,pathlib;time.sleep({delay!r});"
            f"p=pathlib.Path({d});p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.write_text('done')")
    return f"python3 -c {json.dumps(body)}"


def _engine(tmp_path: Path, phases: list) -> Engine:
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{"id": pid, "order": order, "owning_role": "test",
                    "produces_artifact": [art],
                    **({"consumes": cons} if cons else {}),
                    **({"defers_unless": du[0]} if du and du[0] else {}),
                    "executor": {"kind": "script", "cmd": cmd}}
                    for (pid, order, art, cons, cmd, *du) in phases],
    }), encoding="utf-8")
    manifest = Manifest(mp)
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(mp), "manifest_version": 25,
        "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    return Engine(rd, manifest, store, state, dry_run=False)


@pytest.fixture(autouse=True)
def _stub_boundaries(monkeypatch):
    """Scratch phase ids have no registered verifier; the engine fails closed
    on that. These tests prove SCHEDULING and every artifact is a real file
    the executor wrote, so a pass-through substance check is the honest
    stand-in. close() would refuse a scratch manifest on the department's real
    gates and MUST NOT mint a fake certificate: it is stubbed to its success
    terminal -- the scheduling subject never touches gate logic."""
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))
    import presentation_job.phases as phases_mod
    monkeypatch.setattr(
        phases_mod.Gates, "evaluate_all",
        lambda self: {k: {"state": "pass", "reason": "test stub"} for k in
                      phases_mod.ALL_GATE_KEYS})

    def _stub_close(self):
        with self._state_lock:
            self.state["terminal"] = "DONE"
            self.store.save(self.state)
        return EXIT_OK
    monkeypatch.setattr(phases_mod.Engine, "close", _stub_close)
    monkeypatch.setenv("PRESENTATION_DAG_ADMISSION", "1")
    monkeypatch.setenv("PRESENTATION_WAVE_EXECUTION", "1")
    yield


FAIL_CMD = "python3 -c \"import sys; sys.exit(7)\""


# ---------------------------------------------------------------------------
# 1. A fails -> C never runs (zero calls), B completes, blocking edge named.
# ---------------------------------------------------------------------------
def test_failed_ancestor_blocks_descendant_with_edge_named(tmp_path, monkeypatch):
    phases = [
        ("A", 1, "working/a.txt", [], FAIL_CMD),
        ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.02)),
        ("C", 3, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.05)),
    ]
    eng = _engine(tmp_path, phases)
    calls: list = []
    real_gate = eng._check_predecessor_success

    def spy(phase):
        calls.append(phase.id)
        return real_gate(phase)

    monkeypatch.setattr(eng, "_check_predecessor_success", spy)
    rc = eng.run()
    assert rc != EXIT_OK, "A failed; the run must park once at the end"
    # A and B were both admitted (independent siblings keep running)...
    assert "A" in calls and "B" in calls
    # ...B completed...
    assert eng._phase_state("B").get("status") == "done"
    # ...A ended quarantined (FIX 9a unit failure)...
    assert eng._phase_state("A").get("status") == "quarantined"
    # ...and C was NEVER admitted -- zero executor calls, still pending.
    assert eng._phase_state("C").get("status") == "pending", \
        "C must never have run against a failed ancestor"
    assert not (tmp_path / "run" / "working" / "c.txt").exists(), \
        "C's executor never ran -- no artifact, no transport call"
    # THE EXACT BLOCKING EDGE, visible in two places: the phase record's
    # waiting_dependency names A as the blocker, and at least one admission
    # attempt recorded the terminal-bad quarantine status (earlier attempts
    # legitimately saw A still running -- those rows are the withhold trail).
    ps_c = eng._phase_state("C")
    wd = ps_c.get("waiting_dependency") or []
    assert any(w.get("blocked_by") == "A" and w.get("phase") == "C"
               for w in wd), f"blocking edge A->C not named: {wd}"
    evs = [e for e in eng.state.get("events", [])
           if e.get("kind") == "phase.waiting_dependency"
           and "C waits on A" in (e.get("message") or "")]
    assert evs, "the waiting_dependency event row is missing from the event log"
    assert any("quarantined" in (e.get("message") or "") for e in evs), \
        "at least one withhold row must name A's terminal-bad quarantine: " \
        + "; ".join(e.get("message", "") for e in evs[-5:])


# ---------------------------------------------------------------------------
# 2. Repair A; only A and C run -- B stays banked-DONE.
# ---------------------------------------------------------------------------
def test_repairing_ancestor_runs_exactly_a_and_c(tmp_path):
    def _build():
        return _engine(tmp_path, [
            ("A", 1, "working/a.txt", [], FAIL_CMD),
            ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.02)),
            ("C", 3, "working/c.txt", ["working/a.txt"],
             _cmd_that_writes("working/c.txt", 0.05)),
        ])
    eng1 = _build()
    eng1.run()
    assert eng1._phase_state("C").get("status") == "pending"
    # REPAIR: A now succeeds. Re-enter the SAME run dir through a fresh engine
    # over the persisted state (the resume path). _engine() writes a blank
    # state, so capture-and-restore the persisted one first.
    rd = tmp_path / "run"
    import presentation_job.state as st
    persisted = st.StateStore(rd).load()
    good = _cmd_that_writes("working/a.txt", 0.02)
    eng2 = _engine(tmp_path, [
        ("A", 1, "working/a.txt", [], good),
        ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.02)),
        ("C", 3, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.05)),
    ])
    eng2.state = persisted
    eng2.store = st.StateStore(rd)
    b_mtime_before = (rd / "working" / "b.txt").stat().st_mtime
    ran: list = []
    real_gate = eng2._check_predecessor_success

    def spy(phase):
        # Record an ADMISSION only when the gate cleared AND the phase is not
        # already banked-DONE (a DONE phase passes the gate but then SKIPs
        # without ever reaching its executor -- that is banked reuse, not a
        # run). The run/no-run discriminator is run_phase's own done-skip.
        rc = real_gate(phase)
        ps = eng2._phase_state(phase.id)
        if rc is None and ps.get("status") != "done":
            ran.append(phase.id)
        return rc

    eng2._check_predecessor_success = spy
    # Reset the parked terminal (the engine's --resume does this via
    # _reset_parked_state; the run here is the post-repair pass).
    eng2.state["terminal"] = None
    eng2.state.pop("blocked", None)
    eng2.store.save(eng2.state)
    rc = eng2.run()
    assert rc == EXIT_OK, eng2.state.get("blocked")
    assert set(ran) == {"A", "C"}, (
        f"after the repair exactly A and C run; B is banked-DONE. ran={ran}")
    assert eng2._phase_state("B").get("status") == "done"
    assert eng2._phase_state("A").get("status") == "done"
    assert eng2._phase_state("C").get("status") == "done"
    # B's artifact was NOT rewritten on the repair pass (banked reuse).
    assert (rd / "working" / "b.txt").stat().st_mtime == b_mtime_before, \
        "B re-ran its executor on the repair pass -- banked DONE was ignored"
    # PRES-002: C's DONE record stamps the predecessor input-version hashes.
    stamp = eng2._phase_state("C").get("pred_input_hashes") or {}
    assert stamp.get("A"), "C must stamp A's banked input-version hashes at done"
    assert stamp["A"].get("working/a.txt"), \
        "the stamp carries the per-artifact sha256 map"
    import hashlib
    a_bytes = (rd / "working" / "a.txt").read_bytes()
    assert stamp["A"]["working/a.txt"] == hashlib.sha256(a_bytes).hexdigest(), \
        "the stamped hash is the CURRENT banked bytes of A, not a stale one"


# ---------------------------------------------------------------------------
# 3. quick A -> C admitted while slow B still RUNNING (no barrier behind peers).
# ---------------------------------------------------------------------------
def test_quick_ancestor_admits_descendant_before_slow_peer_finishes(tmp_path):
    phases = [
        ("A", 1, "working/a.txt", [], _cmd_that_writes("working/a.txt", 0.05)),
        ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 1.2)),
        ("C", 3, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.05)),
    ]
    eng = _engine(tmp_path, phases)
    admission_log: list = []
    running_seen: list = []
    real_tick_state = {}

    # Spy at the ENGINE level: after C's gate passes, B must still be running.
    real_gate = eng._check_predecessor_success

    def spy(phase):
        rc = real_gate(phase)
        if rc is None and phase.id == "C":
            admission_log.append("C")
            ps_b = eng._phase_state("B")
            running_seen.append(ps_b.get("status"))
        return rc

    eng._check_predecessor_success = spy
    rc = eng.run()
    assert rc == EXIT_OK
    assert admission_log, "C was never admitted"
    assert "running" in running_seen, (
        "C was admitted only after B finished -- a full-wave barrier, not "
        f"prerequisite-pass admission (running_seen={running_seen})")
    # The artifact ordering proves the same thing at wall-clock level:
    c_mtime = (tmp_path / "run" / "working" / "c.txt").stat().st_mtime
    b_mtime = (tmp_path / "run" / "working" / "b.txt").stat().st_mtime
    assert c_mtime < b_mtime, "C completed only after slow B"


# ---------------------------------------------------------------------------
# 4. A stale prior A artifact cannot unlock C after a NEW A failure.
# ---------------------------------------------------------------------------
def test_stale_ancestor_artifact_cannot_unlock_descendant(tmp_path):
    rd = tmp_path / "run"
    (rd / "working").mkdir(parents=True)
    # A STALE artifact from an earlier life sits on disk BEFORE the run.
    stale = rd / "working" / "a.txt"
    stale.write_text("stale-bits-from-a-prior-life")
    phases = [
        ("A", 1, "working/a.txt", [], FAIL_CMD),
        ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.02)),
        ("C", 3, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.05)),
    ]
    eng = _engine(tmp_path, phases)
    # Force the wave loop to re-enter A a SECOND time after its first failure
    # (the resume shape): a prior DONE record for A with a hash that no longer
    # matches the (failed) re-run world. C's predicate must re-validate A's
    # CURRENT banked hashes at admission time and refuse.
    sha_stale = __import__("hashlib").sha256(stale.read_bytes()).hexdigest()
    eng.state.setdefault("phases", []).append({
        "id": "A", "status": "done", "artifacts": ["working/a.txt"],
        "sha256": {"working/a.txt": sha_stale}, "attempts": 1,
        "heal_events": [], "attested_at": "2026-01-01T00:00:00+00:00",
        "verifier_ok": True,
    })
    eng.state["phases"].append({
        "id": "C", "status": "pending", "artifacts": [], "sha256": {},
        "attempts": 0, "heal_events": [], "attested_at": None,
    })
    eng.store.save(eng.state)
    # Now corrupt the stale file so even the BANKED hash no longer matches:
    stale.write_text("rewritten-by-someone-else")
    rc = eng.run()
    assert rc != EXIT_OK
    assert eng._phase_state("A").get("status") == "quarantined"
    assert eng._phase_state("C").get("status") == "pending", \
        "a stale prior artifact must never unlock C"
    assert not (rd / "working" / "c.txt").exists()
    wd = eng._phase_state("C").get("waiting_dependency") or []
    assert any(w.get("blocked_by") == "A" for w in wd)


# ---------------------------------------------------------------------------
# 5. Declined optional branch defers only its documented descendants.
# ---------------------------------------------------------------------------
def test_declined_optional_branch_defers_documented_descendants(tmp_path):
    # OPT (defers_unless false -> deferred) produces opt.txt; DESC consumes it
    # AND carries the same defers_unless (the documented descendant -- the
    # optional-edge rule: consumer belongs to the declinable branch); INDY
    # consumes nothing and must still complete.
    declined = "intake.want == \"yes\""
    phases = [
        ("INDY", 1, "working/i.txt", [], _cmd_that_writes("working/i.txt", 0.02)),
        ("OPT", 2, "working/opt.txt", [], _cmd_that_writes("working/opt.txt", 0.02),
         declined),
        ("DESC", 3, "working/d.txt", ["working/opt.txt"],
         _cmd_that_writes("working/d.txt", 0.02), declined),
    ]
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"want": "no"}))
    eng = _engine(tmp_path, phases)
    # Point the engine's intake loader at the run dir's record.
    rc = eng.run()
    assert rc == EXIT_OK, eng.state.get("blocked")
    assert eng._phase_state("INDY").get("status") == "done", \
        "an unrelated sibling must complete regardless of the declined branch"
    # OPT's gate evaluated false -> DEFERRED by Engine.run's defers filter.
    assert eng._phase_state("OPT").get("status") == "deferred"
    # DESC (the documented descendant) is deferred on the same answer -- never
    # run, never parked on a missing artifact.
    ps_desc = eng._phase_state("DESC")
    assert ps_desc.get("status") == "deferred", \
        f"the declined branch's descendant must defer, got {ps_desc.get('status')}"
    assert not (rd / "working" / "opt.txt").exists()
    assert not (rd / "working" / "d.txt").exists()


# ---------------------------------------------------------------------------
# 6. The persisted edge graph + rollback flag.
# ---------------------------------------------------------------------------
def test_edge_graph_persisted_with_manifest_sha(tmp_path):
    phases = [
        ("A", 1, "working/a.txt", [], _cmd_that_writes("working/a.txt", 0.02)),
        ("C", 2, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.02)),
    ]
    eng = _engine(tmp_path, phases)
    rc = eng.run()
    assert rc == EXIT_OK
    gpath = tmp_path / "run" / "working" / "checkpoints" / "dependency-edges.json"
    assert gpath.is_file(), "the edge graph was not persisted for this run"
    obj = json.loads(gpath.read_text())
    assert obj["manifest_sha256"] == eng.manifest.sha256
    edge = next(e for e in obj["edges"]
                if e["producer"] == "A" and e["consumer"] == "C")
    assert edge["via"] == ["working/a.txt"]
    assert edge["optional"] is False
    # state carries the summary:
    de = eng.state.get("dependency_edges") or {}
    assert de.get("edge_count") == 1
    assert de.get("manifest_sha256") == eng.manifest.sha256


def test_rollback_flag_disables_the_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_DAG_ADMISSION", "0")
    phases = [
        ("A", 1, "working/a.txt", [], FAIL_CMD),
        ("C", 2, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.02)),
    ]
    eng = _engine(tmp_path, phases)
    calls: list = []
    real_gate = eng._check_predecessor_success

    def spy(phase):
        calls.append(phase.id)
        return real_gate(phase)

    eng._check_predecessor_success = spy
    rc = eng.run()
    # The gate itself runs (the flag makes it return None early) but C DID run
    # despite the failed A -- the pre-fix behavior, on record.
    assert "C" in calls
    assert eng._phase_state("C").get("status") == "done"
    assert (tmp_path / "run" / "working" / "c.txt").is_file()
    assert rc != EXIT_OK  # A still fails and the run parks once at the end


def test_deferred_producer_cannot_satisfy_required_edge(tmp_path):
    # OPT is deferred by its gate; REQ consumes opt.txt WITHOUT any
    # defers_unless of its own -- a required edge. The deferred producer may
    # never satisfy it: REQ waits (and Engine.run defers REQ itself through
    # the same intake? No -- REQ has no gate, so it stays waiting_dependency).
    declined = "intake.want == \"yes\""
    phases = [
        ("OPT", 1, "working/opt.txt", [], _cmd_that_writes("working/opt.txt", 0.02),
         declined),
        ("REQ", 2, "working/req.txt", ["working/opt.txt"],
         _cmd_that_writes("working/req.txt", 0.02), None),
    ]
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"want": "no"}))
    eng = _engine(tmp_path, phases)
    rc = eng.run()
    assert eng._phase_state("OPT").get("status") == "deferred"
    ps_req = eng._phase_state("REQ")
    wd = ps_req.get("waiting_dependency") or []
    assert any(w.get("blocked_by") == "OPT" and "non-optional" in
               (w.get("reason") or "") for w in wd), \
        f"a deferred producer must not satisfy a required edge: {wd}"
    assert ps_req.get("status") == "pending"
    assert not (rd / "working" / "req.txt").exists()