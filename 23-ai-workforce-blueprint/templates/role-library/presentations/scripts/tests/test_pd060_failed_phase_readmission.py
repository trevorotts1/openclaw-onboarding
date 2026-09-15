"""PD-TEST-060 -- a FAILED/QUARANTINED phase is re-enterable on a resume.

The defect this pins: `_ready_queue_tick` admits PENDING phases only, so a
phase that ended `failed`/`quarantined` was never admitted again;
`_phase_terminal_bad` then withheld every descendant; and
`__main__._reset_parked_state` cleared terminal/blocked while resetting NO
phase status. The run therefore re-parked identically on every resume with 0
artifacts -- proven live on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4
(P3-ARC status=failed, attempts=1, heal_events=[], four dependents in
waiting_dependencies, terminal BLOCKED at CLOSE).

TWO DIRECTIONS, as the repair requires:
  * an ordinary (non-signature) run re-attempts a failed unit and ADVANCES;
  * the dispatcher's own durable park still binds -- a phase carrying the
    dispatcher's blocked marker (retry ceiling / paid budget) is NOT
    re-admitted, and an owner-decision BLOCKED phase is never touched.
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
from presentation_job.__main__ import _reset_parked_state  # noqa: E402
from presentation_job import dispatcher as dispatcher_mod  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: engine over a scratch manifest whose script phases are real
# python -c commands (same discipline as test_pres036_ready_queue.py -- the
# files appear for real, no attestation is ever simulated).
# ---------------------------------------------------------------------------
def _cmd_that_writes(target: str, delay: float = 0.0) -> str:
    d = json.dumps(target)
    body = (f"import time,pathlib;time.sleep({delay!r});"
            f"p=pathlib.Path({d});p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.write_text('done')")
    return f"python3 -c {json.dumps(body)}"


def _cmd_that_writes_only_after_sentinel(target: str, sentinel: str) -> str:
    """Fails (rc 7) on the first run; the sentinel makes it succeed later."""
    d = json.dumps(target)
    s = json.dumps(sentinel)
    body = (f"import pathlib,sys;"
            f"p=pathlib.Path({d});s=pathlib.Path({s});"
            f"p.parent.mkdir(parents=True,exist_ok=True);"
            f"(p.write_text('done') if s.exists() else sys.exit(7))")
    return f"python3 -c {json.dumps(body)}"


def _manifest(tmp_path: Path, phases: list) -> Path:
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{"id": pid, "order": order, "owning_role": "test",
                    "produces_artifact": [art],
                    **({"consumes": cons} if cons else {}),
                    "executor": {"kind": "script", "cmd": cmd}}
                    for (pid, order, art, cons, cmd) in phases],
    }), encoding="utf-8")
    return mp


def _engine(tmp_path: Path, phases: list) -> Engine:
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    mp = _manifest(tmp_path, phases)
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
def _stub_verifiers(monkeypatch):
    """Scratch phase ids have no registered verifier; every artifact here is a
    real file, so a pass-through substance check is the honest stand-in (same
    discipline test_pres036 / test_defect3 use). Gates and close() are stubbed
    so these tests pin SCHEDULING and only scheduling -- close() would refuse
    a scratch manifest on the real department gates."""
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
    yield


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PRESENTATION_READY_QUEUE", "1")
    monkeypatch.setenv("PRESENTATION_WAVE_EXECUTION", "1")
    monkeypatch.setenv("PRESENTATION_CAPACITY_OVERRIDE", "")
    yield


def _park_with_failed_arc(tmp_path: Path):
    """A -> C chain where A fails on the first run and would pass on a retry.
    Returns (engine, run_dir, sentinel)."""
    run = tmp_path / "run"
    sentinel = tmp_path / "go"
    phases = [
        ("A", 1, "working/a.txt", [],
         _cmd_that_writes_only_after_sentinel("working/a.txt", str(sentinel))),
        ("C", 2, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.02)),
    ]
    return _engine(tmp_path, phases), run, sentinel


# ---------------------------------------------------------------------------
# Unit level: the shared unpark helper is the re-admission seam.
# ---------------------------------------------------------------------------
def _state_for_reset(run_dir: Path, phases: list) -> dict:
    return {
        "run_dir": str(run_dir), "terminal": "BLOCKED",
        "blocked": {"phase": "A", "reason": "1 unit(s) failed", "at": "x"},
        "phases": phases,
    }


def test_failed_phase_is_readmitted_and_history_preserved(tmp_path):
    run = tmp_path / "run"
    (run / "working" / "work-orders").mkdir(parents=True)
    state = _state_for_reset(run, [
        {"id": "A", "status": "failed", "attempts": 1, "heal_events": [],
         "failed_rc": 3, "failed_reason": "phase exited rc=3 without parking"},
        {"id": "C", "status": "pending", "attempts": 0, "heal_events": []},
    ])
    prior = _reset_parked_state(state)
    assert prior and prior["phase"] == "A"
    a = state["phases"][0]
    assert a["status"] == "pending", a
    assert a["attempts"] == 1, "the failed attempt counter must be preserved"
    assert a["failed_rc"] == 3 and a["failed_reason"].startswith("phase exited")
    assert a["readmissions"][0]["prior_status"] == "failed"
    assert a["readmissions"][0]["prior_attempts"] == 1
    assert state["resume_readmissions"][0]["phase"] == "A"
    assert state["terminal"] is None
    assert "blocked" not in state
    assert state["resume_history"][0]["cleared_blocked"]["phase"] == "A"


def test_dispatcher_parked_phase_is_not_readmitted(tmp_path):
    """Direction 2: the dispatcher's durable park owns its generation."""
    run = tmp_path / "run"
    (run / "working" / "work-orders").mkdir(parents=True)
    marker = dispatcher_mod._blocked_marker_path(run, "A")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("DISPATCH BLOCKED -- retry ceiling", encoding="utf-8")
    state = _state_for_reset(run, [
        {"id": "A", "status": "failed", "attempts": 9, "heal_events": []},
    ])
    _reset_parked_state(state)
    a = state["phases"][0]
    assert a["status"] == "failed", "a dispatcher-parked phase must stay parked"
    assert not a.get("readmissions")
    assert state["last_resume_readmissions"] == []


def test_owner_blocked_and_done_phases_are_never_readmitted(tmp_path):
    run = tmp_path / "run"
    (run / "working" / "work-orders").mkdir(parents=True)
    state = _state_for_reset(run, [
        {"id": "OWNER", "status": "blocked", "attempts": 1, "heal_events": []},
        {"id": "DONE", "status": "done", "attempts": 1, "artifacts": ["x"]},
        {"id": "QUAR", "status": "quarantined", "attempts": 2,
         "quarantined_reason": "artifact never appeared"},
    ])
    _reset_parked_state(state)
    by_id = {p["id"]: p for p in state["phases"]}
    assert by_id["OWNER"]["status"] == "blocked", "owner decision is not ours"
    assert by_id["DONE"]["status"] == "done"
    assert by_id["QUAR"]["status"] == "pending", "_fail_unit promises re-entry"
    assert [r["phase"] for r in state["last_resume_readmissions"]] == ["QUAR"]


# ---------------------------------------------------------------------------
# Engine level: the run actually ADVANCES after the resume.
# ---------------------------------------------------------------------------
def test_resume_readmits_failed_unit_and_run_advances(tmp_path):
    eng, run, sentinel = _park_with_failed_arc(tmp_path)
    rc1 = eng.run()
    assert rc1 != EXIT_OK
    a = eng._phase_state("A")
    assert a["status"] == "failed" and a["attempts"] == 1, a
    assert eng.state.get("terminal") == "BLOCKED"
    assert not (run / "working" / "c.txt").exists(), "C ran behind a failed A"

    # A supported resume: the shared unpark helper, then the engine again.
    sentinel.write_text("go", encoding="utf-8")
    prior = _reset_parked_state(eng.state)
    assert prior is not None and prior["phase"] == "A"
    eng.store.save(eng.state)
    rc2 = eng.run()
    assert rc2 == EXIT_OK, eng.state.get("blocked")
    a = eng._phase_state("A")
    assert a["status"] == "done", a
    assert a["attempts"] == 2, "the retry is a real second attempt"
    assert eng._phase_state("C")["status"] == "done"
    assert (run / "working" / "c.txt").exists()
    assert eng.state["terminal"] == "DONE"


def test_resume_does_not_readmit_a_dispatcher_parked_unit(tmp_path):
    eng, run, sentinel = _park_with_failed_arc(tmp_path)
    rc1 = eng.run()
    assert rc1 != EXIT_OK
    marker = dispatcher_mod._blocked_marker_path(run, "A")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("DISPATCH BLOCKED -- retry ceiling", encoding="utf-8")

    sentinel.write_text("go", encoding="utf-8")
    _reset_parked_state(eng.state)
    eng.store.save(eng.state)
    rc2 = eng.run()
    assert rc2 != EXIT_OK, "a parked unit must not be re-dispatched by a resume"
    a = eng._phase_state("A")
    assert a["status"] == "failed"
    assert a["attempts"] == 1, "no attempt may be bought by a resume"
    assert not (run / "working" / "c.txt").exists()
