"""Tests for FAULT-16 / FAULT-09 (2026-08-20, orchestrator-verified from the
live event log) -- the phase/work-order race and the resume spin, both in
presentation_job/phases.py's Engine._run_agent_phase().

THE DEFECT THIS FILE PROVES FIXED:

FAULT-16 -- Engine._run_agent_phase()'s poll loop trusted bare glob-match
presence (_artifacts_present()) as "the work is done." For P4-PROMPT
(produces_artifact = "working/prompts/slide-*.txt" -- 25 independently-graded
files for a 25-slide deck), that check is true the instant ONE stale file
from an earlier, blocked attempt is still on disk -- which it always is on
re-entry. That let the loop return EXIT_OK on its FIRST check (before any
sleep, in the SAME SECOND the work order was written), sending the phase
straight into run_phase()'s substance verifier against admittedly partial
output. A real deck sat blocked 9.5 hours with 14 of 25 slide prompts never
written because of exactly this.

FAULT-09 -- `--resume` re-entering that phase hit the identical bug against
the EXISTING failed artifact (re-verify + re-block in ~2 seconds -- 181
state.json.resume_history entries with zero forward progress between any of
them), and _run_agent_phase unconditionally overwrote the work order file
even when a dispatcher process still held a live claim on the same phase.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_engine_client_report.py, test_gates.py,
etc.).
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
from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
    """Same resolution order as test_engine_client_report.py's
    _canonical_manifest() / test_client_step_count.py's _manifest_phases()."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found")


def _manifest() -> Manifest:
    return Manifest(_canonical_manifest())


def _engine(tmp_path, dry_run=False) -> Engine:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_type": "webinar", "creation_mode": "from_scratch"}))
    manifest = _manifest()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=dry_run)


class FakeClock:
    """Deterministic, instant stand-in for time.time()/time.sleep() so the
    poll loop's real budget (minutes) can be exhausted -- or watched for a
    growth event -- without the test actually waiting real wall-clock time.
    `on_sleep(clock)` runs on every simulated sleep, letting a test inject a
    "the dispatcher just wrote something" event partway through the wait."""

    def __init__(self, start: float = 1_000_000.0, on_sleep=None):
        self.now = start
        self.sleep_calls = 0
        self.on_sleep = on_sleep

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls += 1
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(self)


def _install_clock(monkeypatch, **kw) -> FakeClock:
    clock = FakeClock(**kw)
    monkeypatch.setattr("time.time", clock.time)
    monkeypatch.setattr("time.sleep", clock.sleep)
    return clock


def _prompt_phase(eng: Engine):
    return eng.manifest.phase("P4-PROMPT")


def _slide_path(rd: Path, n: int) -> Path:
    return rd / "working" / "prompts" / f"slide-{n:02d}.txt"


def _write_slide(rd: Path, n: int, mtime: float) -> None:
    p = _slide_path(rd, n)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x" * 9500)  # clears the (unrelated) length-only degraded floor if ever consulted
    import os
    os.utime(p, (mtime, mtime))


# ---------------------------------------------------------------------------
# 1. FAULT-16 core: stale partial glob content must never satisfy the wait
#    loop by itself -- the substance verifier must never even be reached
#    without genuine forward progress.
# ---------------------------------------------------------------------------
def test_stale_partial_output_never_reaches_verifier_without_growth(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=False)
    phase = _prompt_phase(eng)
    rd = Path(eng.run_dir)
    clock = _install_clock(monkeypatch, on_sleep=None)  # nothing new ever appears
    _write_slide(rd, 1, clock.now - 10_000)  # stale: predates this dispatch entirely

    verify_calls = []
    monkeypatch.setattr(phase_verifiers, "verify",
                         lambda *a, **k: verify_calls.append(a) or (False, ["should never run"]))

    rc = eng.run_phase(phase)

    assert rc == EXIT_GATE_BLOCKED, f"expected an honest budget-timeout block, got {rc}"
    assert not verify_calls, (
        "the substance verifier ran against a stale, non-progressing glob match -- "
        "FAULT-16's same-breath judgement is back")
    assert clock.sleep_calls > 0, "the loop must genuinely wait, not exit on its first check"
    blocked = eng.state.get("blocked") or {}
    assert "produced nothing" in (blocked.get("reason") or ""), (
        "a no-progress timeout must use the honest generic budget-timeout reason, "
        f"got: {blocked.get('reason')!r}")


# ---------------------------------------------------------------------------
# 2. Re-entry (same scenario, called a SECOND time -- simulating --resume)
#    must ALSO wait rather than instantly re-verifying the unchanged artifact.
#    This is FAULT-09's "re-verifies the EXISTING failed artifact... in ~2
#    seconds" spin.
# ---------------------------------------------------------------------------
def test_resume_reentry_with_unchanged_artifact_waits_again_not_instant_reblock(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=False)
    phase = _prompt_phase(eng)
    rd = Path(eng.run_dir)
    clock = _install_clock(monkeypatch)
    _write_slide(rd, 1, clock.now - 10_000)

    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (False, ["never"]))

    rc1 = eng.run_phase(phase)
    assert rc1 == EXIT_GATE_BLOCKED
    sleeps_after_first_block = clock.sleep_calls
    assert sleeps_after_first_block > 0

    # Simulate --resume: clear the block the same way __main__.py does, and
    # re-enter with the artifact set EXACTLY as it was left (no growth at all
    # since the last attempt) -- the true "EXISTING failed artifact" case.
    eng.state.pop("blocked", None)
    eng.state["terminal"] = None
    ps = eng._phase_state(phase.id)
    ps["status"] = "pending"

    rc2 = eng.run_phase(phase)
    assert rc2 == EXIT_GATE_BLOCKED
    assert clock.sleep_calls > sleeps_after_first_block, (
        "resume must wait again (spend real budget) before re-blocking -- an "
        "instant re-block with zero additional sleeps is exactly FAULT-09's spin")


# ---------------------------------------------------------------------------
# 3. Once genuine forward progress appears mid-wait, the loop must hand off
#    to the REAL substance verifier -- and a genuinely bad artifact must
#    STILL fail. Proves the gate itself is untouched (fixing WHEN, not
#    WHETHER, it can fail).
# ---------------------------------------------------------------------------
def test_growth_reaches_verifier_and_bad_artifact_still_fails(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=False)
    phase = _prompt_phase(eng)
    rd = Path(eng.run_dir)

    state = {"progressed": False}

    def on_sleep(clock):
        # After a couple of real poll cycles, the dispatcher finally writes
        # a second slide -- genuine forward progress, later than baseline.
        if clock.sleep_calls == 2 and not state["progressed"]:
            _write_slide(rd, 2, clock.now)
            state["progressed"] = True

    clock = _install_clock(monkeypatch, on_sleep=on_sleep)
    _write_slide(rd, 1, clock.now - 10_000)  # stale baseline, predates this dispatch

    verify_calls = []

    def fake_verify(phase_id, run_dir):
        verify_calls.append(clock.sleep_calls)
        return False, ["AF-PROMPT-FLOOR: slide-25 missing"]

    monkeypatch.setattr(phase_verifiers, "verify", fake_verify)

    rc = eng.run_phase(phase)

    assert verify_calls, "the verifier must run once real progress is observed"
    assert verify_calls[0] >= 2, (
        "verification must not happen on the very first check -- it must "
        f"follow genuine waiting; observed sleep_calls={verify_calls[0]}")
    assert rc == EXIT_GATE_BLOCKED, "a genuinely bad artifact must still fail -- the gate is intact"
    blocked = eng.state.get("blocked") or {}
    assert "AF-PROMPT-FLOOR" in (blocked.get("reason") or ""), (
        "the REAL verifier's reason must reach the block, unmodified")


# ---------------------------------------------------------------------------
# 4. Once genuine forward progress appears AND the (real) verifier passes,
#    the phase must complete normally -- proves this is a timing fix, not a
#    new permanent-wait deadlock.
# ---------------------------------------------------------------------------
def test_growth_then_good_artifact_passes(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=False)
    phase = _prompt_phase(eng)
    rd = Path(eng.run_dir)

    def on_sleep(clock):
        if clock.sleep_calls == 1:
            _write_slide(rd, 2, clock.now)

    clock = _install_clock(monkeypatch, on_sleep=on_sleep)
    _write_slide(rd, 1, clock.now - 10_000)

    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng.run_phase(phase)

    assert rc == EXIT_OK
    assert eng._phase_state(phase.id).get("status") == "done"


# ---------------------------------------------------------------------------
# 5. FAULT-09b: a live dispatcher claim (or a still-outstanding work order)
#    must be reused, never clobbered with a freshly (re)issued one.
# ---------------------------------------------------------------------------
def test_live_claim_prevents_work_order_clobber(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=True)  # dry_run short-circuits AFTER the
    phase = _prompt_phase(eng)             # work-order decision -- exactly what we're testing
    rd = Path(eng.run_dir)
    wo_dir = rd / "working" / "work-orders"
    wo_dir.mkdir(parents=True, exist_ok=True)
    wo_path = wo_dir / f"{phase.id}.json"
    claim_path = wo_dir / f"{phase.id}.claim"

    sentinel = {"phase": phase.id, "owning_role": "someone-else", "produces_artifact": [],
                "verifier": "x", "budget_minutes": 1, "issued_at": "SENTINEL-DO-NOT-OVERWRITE"}
    wo_path.write_text(json.dumps(sentinel), encoding="utf-8")
    claim_path.write_text(json.dumps({"worker": "dispatcher-1", "claimed_at": "now"}),
                           encoding="utf-8")
    import os, time as real_time
    now = real_time.time()
    os.utime(claim_path, (now, now))

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_OK
    on_disk = json.loads(wo_path.read_text(encoding="utf-8"))
    assert on_disk["issued_at"] == "SENTINEL-DO-NOT-OVERWRITE", (
        "a live dispatcher claim must stop the engine from reissuing the work order")
    kinds = [e.get("kind") for e in eng.state.get("events", [])]
    assert "phase.work_order_reused" in kinds
    assert "phase.work_order" not in kinds, "must not ALSO log a fresh-issue event"


# ---------------------------------------------------------------------------
# 6. Regression guard: an exact/single-file produces_artifact is completely
#    unaffected -- presence still exits immediately, zero sleeps, matching
#    tests/test_checkpoint.py::test_heartbeat_interval's existing contract.
# ---------------------------------------------------------------------------
def test_exact_path_artifact_still_exits_immediately(tmp_path, monkeypatch):
    from presentation_job.manifest import Manifest as _M
    rd = tmp_path / "run"
    (rd / "working").mkdir(parents=True, exist_ok=True)
    (rd / "w").mkdir(parents=True, exist_ok=True)
    (rd / "w" / "o.txt").write_text("ok")
    mf = tmp_path / "mf.json"
    mf.write_text(json.dumps({"manifest_version": 25, "phases": [
        {"id": "PT", "order": 1.0, "owning_role": "r", "produces_artifact": "w/o.txt",
         "heartbeat_minutes": 1, "client_report": {}}], "deliverables_required": []}))
    manifest = _M(mf)
    store = StateStore(rd)
    state = {"job_id": "pj", "schema_version": 1, "run_dir": str(rd), "phases": [],
             "events": [], "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}}
    store.save(state)
    state = store.load()
    eng = Engine(rd, manifest, store, state)
    clock = _install_clock(monkeypatch)
    ph = manifest.phase("PT")

    rc = eng._run_agent_phase(ph)

    assert rc == EXIT_OK
    assert clock.sleep_calls == 0, "an exact-path artifact must still exit on the first check"
