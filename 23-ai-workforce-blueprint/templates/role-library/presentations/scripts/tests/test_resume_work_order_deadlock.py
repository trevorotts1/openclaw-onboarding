"""Two resume-time deadlocks that make a deck build look hung, both observed on
the live run archived as the P-SP-INTAKE collision evidence (2026-09-04/05).

DEADLOCK 1 -- work-order reuse never re-checked the artifact.
  Engine._run_agent_phase() decided "a work order is live" purely from FILE
  MTIME (phases.py, the stale_after/claim_live/wo_live block) and never asked
  whether the artifact that order exists to produce was already there.
  Observed:
      23:19:18  work order written for P-SP-INTAKE
      23:22:54  dispatcher parks the order at its retry ceiling
                (sidecar row status="blocked_retry_ceiling")
      23:42:59  the real, driver-signed sp_intake.json is written
      00:02:29  --resume logs "a work order is already outstanding ... waiting
                on it instead of reissuing" -- and waits, silently, on an
                artifact that had been valid for twenty minutes.
  Two independent causes, both fixed and both proved separately here:
    (a) the reuse branch had no satisfaction test at all; and
    (b) _sidecar_pending() did not count `blocked_retry_ceiling` as settled, so
        the poll loop forced ok=False on every tick. That closed the circle:
        the Engine waited for the dispatcher, while the dispatcher's own park
        marker says it resumes only "if the Engine reissues the work order"
        (dispatcher.py:4374-4376).

DEADLOCK 2 -- terminal="BLOCKED" stopped dispatch but not the Engine.
  _block() stamps a run-level terminal MID-PLAN (phases.py:2446). From that
  instant every dispatcher exits on its next tick (dispatcher.py:4679/:4738),
  but the Engine kept walking the plan and queueing work orders -- 00:55:20
  wrote orders for P-STYLE-SPEC and P-3.5-RESEARCH-MAP for a run nothing would
  ever dispatch, and P3-ARC burned its full 30-minute budget between 00:25:20
  and 00:55:20 before failing "produced nothing". To an operator that is
  indistinguishable from slow progress. This is FIX 22's bug
  (__main__.py:866-876) recurring mid-run instead of at entry.

Flat file inside tests/, manages its own import path, and builds its own
one-phase manifest -- it never reads PIPELINE-MANIFEST.json, so it cannot
drift with manifest edits.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED  # noqa: E402
import phase_verifiers  # noqa: E402


PHASE_ID = "P-SP-INTAKE"
ARTIFACT = "working/copy/sp_intake.json"
SENTINEL = "SENTINEL-DO-NOT-OVERWRITE"


# ---------------------------------------------------------------------------
# Harness (same shape as tests/test_f16_agent_phase_wait_race.py)
# ---------------------------------------------------------------------------
class FakeClock:
    """Deterministic stand-in for time.time()/time.sleep() so a real phase
    budget can be exhausted without waiting real wall-clock time."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start
        self.sleep_calls = 0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls += 1
        self.now += seconds


def _install_clock(monkeypatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr("time.time", clock.time)
    monkeypatch.setattr("time.sleep", clock.sleep)
    return clock


def _engine(tmp_path) -> Engine:
    """One EXACT-path agent phase -- the shape P-SP-INTAKE actually has."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    mf = tmp_path / "mf.json"
    mf.write_text(json.dumps({"manifest_version": 25, "phases": [
        {"id": PHASE_ID, "order": 1.0,
         "owning_role": "signature-presentation-architect",
         "produces_artifact": ARTIFACT, "heartbeat_minutes": 15,
         "client_report": {}}], "deliverables_required": []}))
    manifest = Manifest(mf)
    store = StateStore(rd)
    store.save({"job_id": "dl", "schema_version": 1, "run_dir": str(rd),
                "phases": [], "events": [], "sent": {}, "gates": {}, "waivers": [],
                "requester": {"chat_id": "t"}, "heartbeat": {},
                "undeliverable": [], "terminal": None})
    return Engine(rd, manifest, store, store.load())


def _wo_dir(eng: Engine) -> Path:
    d = Path(eng.run_dir) / "working" / "work-orders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _work_order(eng: Engine, clock: FakeClock, age_s: float = 60.0) -> Path:
    """An outstanding work order whose mtime is `age_s` old on the fake clock."""
    wo = _wo_dir(eng) / f"{PHASE_ID}.json"
    wo.write_text(json.dumps({"phase": PHASE_ID, "issued_at": SENTINEL}),
                  encoding="utf-8")
    os.utime(wo, (clock.now - age_s, clock.now - age_s))
    return wo


def _live_claim(eng: Engine, clock: FakeClock) -> Path:
    """dispatcher.py's own claim-file convention, freshly touched."""
    c = _wo_dir(eng) / f"{PHASE_ID}.claim"
    c.write_text(json.dumps({"worker": "dispatcher-15132-511d9d80"}), encoding="utf-8")
    os.utime(c, (clock.now - 5.0, clock.now - 5.0))
    return c


def _sidecar(eng: Engine, status: str) -> Path:
    """The dispatcher's own sidecar log -- one row with `status`. Verbatim row
    shape from the archived run's P-SP-INTAKE.dispatcher-log.jsonl."""
    s = _wo_dir(eng) / f"{PHASE_ID}.dispatcher-log.jsonl"
    s.write_text(json.dumps({"worker": "dispatcher-15132-511d9d80", "attempt": 0,
                             "status": status, "observation": 8,
                             "consecutive": 8}) + "\n", encoding="utf-8")
    return s


def _artifact(eng: Engine) -> Path:
    """The real, driver-signed record's shape: answers + turn_ledger_provenance."""
    p = Path(eng.run_dir) / ARTIFACT
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "answers": {f"q{i}": f"answer {i}" for i in range(1, 9)},
        "turn_ledger_provenance": {"key_id": "k1", "signature": "deadbeef",
                                   "signed_at": "2026-09-04T23:42:59-04:00",
                                   "turns": 8}}), encoding="utf-8")
    return p


def _kinds(eng: Engine):
    return [e.get("kind") for e in eng.state.get("events", [])]


def _stale_after(eng: Engine) -> float:
    phase = eng.manifest.phase(PHASE_ID)
    return max(120.0, phase.budget_minutes * 60 * 2)


# ---------------------------------------------------------------------------
# DEADLOCK 1 (a): an outstanding work order for an ALREADY-SATISFIED artifact
#                 is not a reason to wait.
# ---------------------------------------------------------------------------
def test_satisfied_artifact_is_not_waited_on_behind_an_outstanding_work_order(
        tmp_path, monkeypatch):
    """THE 00:02:29 RESUME. A work order is outstanding and nowhere near stale,
    the dispatcher has parked it at its retry ceiling, and the real artifact is
    already on disk and passes its substance verifier. The phase must COMPLETE,
    not wait. Before the fix this burned the entire phase budget."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    wo = _work_order(eng, clock)
    _sidecar(eng, "blocked_retry_ceiling")
    _artifact(eng)
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_OK, f"a satisfied artifact must complete the phase, got rc={rc}"
    assert clock.sleep_calls == 0, (
        "the engine must not wait one tick on an order for work that is done "
        f"(slept {clock.sleep_calls} times)")
    kinds = _kinds(eng)
    assert "phase.work_order_satisfied" in kinds, kinds
    assert "phase.work_order_reused" not in kinds, (
        "waiting on an outstanding order for a satisfied artifact IS the deadlock")
    assert json.loads(wo.read_text(encoding="utf-8"))["issued_at"] == SENTINEL, (
        "the short-circuit must not clobber the outstanding order either")


def test_present_but_unverified_artifact_is_never_treated_as_satisfied(
        tmp_path, monkeypatch):
    """GATE INTEGRITY / known-good negative control for the test above. Bare
    file presence must never trigger the new short-circuit -- _artifacts_present()
    gates on literal existence only (the hazard dispatcher.py:3541-3544
    documents), so satisfaction requires the substance verifier to PASS. With a
    dispatcher genuinely mid-flight the engine still waits the order out, byte
    for byte the pre-fix behaviour."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    _work_order(eng, clock)
    _sidecar(eng, "call_failed")         # a dispatcher genuinely still in flight
    _artifact(eng)                       # present...
    monkeypatch.setattr(phase_verifiers, "verify",
                        lambda *a, **k: (False, ["AF-SP-PROVENANCE: not confirmed"]))

    rc = eng._run_agent_phase(phase)

    kinds = _kinds(eng)
    assert "phase.work_order_satisfied" not in kinds, (
        "a file that fails its verifier is NOT a satisfied artifact")
    assert "phase.work_order_reused" in kinds, kinds
    assert rc == EXIT_GATE_BLOCKED
    assert clock.sleep_calls > 0, "an unverified artifact must still be waited on"


# ---------------------------------------------------------------------------
# DEADLOCK 1 (b): a retry-ceiling park is the dispatcher DONE with the order,
#                 not a dispatcher still mid-flight.
# ---------------------------------------------------------------------------
def test_retry_ceiling_park_settles_the_dispatcher_sidecar(tmp_path):
    """_sidecar_pending() must read `blocked_retry_ceiling` as settled. The
    dispatcher's own park marker says re-dispatch resumes only if the Engine
    reissues the order (dispatcher.py:4374-4376), so no later attempt can land
    while the Engine waits -- reading it as 'mid-flight' is the circular wait.
    Carries its own known-good control: a genuinely in-flight row still pends."""
    eng = _engine(tmp_path)

    _sidecar(eng, "blocked_retry_ceiling")
    assert eng._sidecar_pending(PHASE_ID) is False, (
        "a phase parked at the dispatcher's retry ceiling has no attempt coming")

    # CONTROL (must be non-empty / True, or this check proves nothing):
    _sidecar(eng, "call_failed")
    assert eng._sidecar_pending(PHASE_ID) is True, (
        "CONTROL FAILED -- a genuinely mid-flight dispatcher row must still pend; "
        "if this is False the test is broken, not the code")
    _sidecar(eng, "verified")
    assert eng._sidecar_pending(PHASE_ID) is False


def test_ceiling_park_does_not_deadlock_the_poll_loop(tmp_path, monkeypatch):
    """The same defect reached through the OTHER door: no outstanding order, so
    the engine issues a fresh one and enters the poll loop. The dispatcher has
    already parked at its ceiling and the artifact is present and verifying.
    Before the fix _sidecar_pending() forced ok=False on every single tick and
    the loop burned the whole budget on a complete phase."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    _sidecar(eng, "blocked_retry_ceiling")
    _artifact(eng)
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_OK
    assert clock.sleep_calls == 0
    assert "phase.work_order" in _kinds(eng), "a fresh order is still issued"


# ---------------------------------------------------------------------------
# FAULT-09 PRESERVED: the guard that must not break.
# ---------------------------------------------------------------------------
def test_live_claim_still_forces_a_wait_even_when_the_artifact_is_satisfied(
        tmp_path, monkeypatch):
    """FAULT-09: two components must never act on one phase simultaneously. A
    dispatcher process actually HOLDING this phase wins unconditionally --
    satisfied artifact or not, because the claim holder may be mid-rewrite of
    the very file we just measured. The engine must wait and must not reissue."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    wo = _work_order(eng, clock)
    _live_claim(eng, clock)
    _artifact(eng)
    _sidecar(eng, "call_failed")          # the claim holder is genuinely in flight
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng._run_agent_phase(phase)

    kinds = _kinds(eng)
    assert "phase.work_order_reused" in kinds, kinds
    assert "phase.work_order_satisfied" not in kinds, (
        "a satisfied artifact must NEVER override a live dispatcher claim")
    assert "phase.work_order" not in kinds, "must not ALSO log a fresh issue"
    assert json.loads(wo.read_text(encoding="utf-8"))["issued_at"] == SENTINEL, (
        "a live dispatcher claim must stop the engine reissuing the work order")
    assert clock.sleep_calls > 0, "a live claim must still make the engine WAIT"
    assert rc == EXIT_GATE_BLOCKED


def test_live_claim_wins_even_with_no_sidecar_at_all(tmp_path, monkeypatch):
    """Companion: the claim alone is enough -- the new satisfied short-circuit
    is never reached while a claim is live, regardless of sidecar state."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    wo = _work_order(eng, clock)
    _live_claim(eng, clock)
    _artifact(eng)
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    eng._run_agent_phase(phase)

    kinds = _kinds(eng)
    assert "phase.work_order_reused" in kinds
    assert "phase.work_order_satisfied" not in kinds
    assert json.loads(wo.read_text(encoding="utf-8"))["issued_at"] == SENTINEL


# ---------------------------------------------------------------------------
# STALE-VS-LIVE BOUNDARY: unchanged for the UNSATISFIED case.
# ---------------------------------------------------------------------------
def test_fresh_work_order_with_no_artifact_still_waits(tmp_path, monkeypatch):
    """The FAULT-09b patience contract is untouched: a still-outstanding order
    with NOTHING produced is reused and waited on, exactly as before."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    wo = _work_order(eng, clock)
    calls = []
    monkeypatch.setattr(phase_verifiers, "verify",
                        lambda *a, **k: calls.append(a) or (True, []))

    rc = eng._run_agent_phase(phase)

    kinds = _kinds(eng)
    assert "phase.work_order_reused" in kinds, kinds
    assert "phase.work_order_satisfied" not in kinds
    assert rc == EXIT_GATE_BLOCKED
    assert clock.sleep_calls > 0
    assert json.loads(wo.read_text(encoding="utf-8"))["issued_at"] == SENTINEL
    assert not calls, (
        "no artifact on disk -> the substance verifier must never be consulted")


def test_genuinely_stale_work_order_is_still_reissued(tmp_path, monkeypatch):
    """The other side of the same boundary: no sign of life for more than 2x
    this phase's own budget is still presumed abandoned and safe to reissue."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    wo = _work_order(eng, clock, age_s=_stale_after(eng) + 100.0)

    eng._run_agent_phase(phase)

    kinds = _kinds(eng)
    assert "phase.work_order" in kinds, kinds
    assert "phase.work_order_reused" not in kinds
    assert json.loads(wo.read_text(encoding="utf-8"))["issued_at"] != SENTINEL, (
        "an abandoned order must still be reissued")


# ---------------------------------------------------------------------------
# DEADLOCK 2: a parked run must not silently accumulate work orders.
# ---------------------------------------------------------------------------
def test_parked_run_does_not_silently_accumulate_work_orders(
        tmp_path, monkeypatch, capsys):
    """THE 00:55:20 EVENTS. state.terminal is set (exactly what _block() stamps
    mid-plan at phases.py:2446), so every dispatcher has already exited on it
    (dispatcher.py:4679/:4738). The engine must NOT queue an order nothing can
    service, must not burn the phase budget waiting for it, and must say so
    loudly."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    eng.state["terminal"] = "BLOCKED"

    rc = eng._run_agent_phase(phase)
    err = capsys.readouterr().err

    assert rc == EXIT_GATE_BLOCKED, f"a parked run must not report progress, got rc={rc}"
    assert not (_wo_dir(eng) / f"{PHASE_ID}.json").exists(), (
        "a parked run must not queue work nothing will dispatch")
    assert clock.sleep_calls == 0, (
        "and must not burn the phase budget waiting on an order it never wrote")
    kinds = _kinds(eng)
    assert "phase.no_dispatch_run_parked" in kinds, kinds
    assert "phase.work_order" not in kinds
    assert "NO DISPATCH" in err and "state.terminal=BLOCKED" in err, err


def test_unparked_run_still_queues_normally(tmp_path, monkeypatch):
    """CONTROL for the test above -- same engine, same phase, terminal clear.
    If this did not queue, the guard would be firing on everything and the
    check above would prove nothing."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    _install_clock(monkeypatch)
    assert eng.state.get("terminal") is None

    eng._run_agent_phase(phase)

    assert (_wo_dir(eng) / f"{PHASE_ID}.json").is_file(), (
        "CONTROL FAILED -- an unparked run must still queue its work order")
    assert "phase.work_order" in _kinds(eng)


def test_parked_run_still_completes_an_already_satisfied_phase(tmp_path, monkeypatch):
    """A park must never strand a phase that is already done: completing it
    queues nothing and needs no dispatcher, so the guard must not block it."""
    eng = _engine(tmp_path)
    phase = eng.manifest.phase(PHASE_ID)
    clock = _install_clock(monkeypatch)
    eng.state["terminal"] = "BLOCKED"
    _work_order(eng, clock)
    _artifact(eng)
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_OK
    assert "phase.work_order_satisfied" in _kinds(eng)
    assert "phase.no_dispatch_run_parked" not in _kinds(eng)


def test_dispatcher_still_honours_a_set_terminal(tmp_path):
    """FIX-9 RECONCILIATION, code side. terminal="BLOCKED" was never retired:
    phases.py writes it in 8 places and five other modules read it. So
    _run_terminal() honouring it is CORRECT and is deliberately unchanged --
    only the comment claiming Fix 9 'drops terminal=BLOCKED entirely' was
    wrong. Deadlock 2 is fixed on the Engine side, where the queueing happens,
    never by loosening this safety."""
    from presentation_job import dispatcher
    rd = tmp_path / "run"
    rd.mkdir()

    (rd / "state.json").write_text(json.dumps({"terminal": "BLOCKED"}), encoding="utf-8")
    assert dispatcher._run_terminal(rd) == "BLOCKED"

    # CONTROL: the same reader on a live run must come back None, or a
    # "terminal is honoured" claim would be unfalsifiable.
    (rd / "state.json").write_text(json.dumps({"terminal": None}), encoding="utf-8")
    assert dispatcher._run_terminal(rd) is None
