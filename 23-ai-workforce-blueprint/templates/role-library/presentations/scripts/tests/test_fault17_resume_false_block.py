"""Tests for FAULT-17 (2026-08-20, orchestrator-verified from the live
pres-wave-e-v3-1787240658 event log) -- the resume false-block in
presentation_job/phases.py's Engine._run_agent_phase().

THE DEFECT THIS FILE PROVES FIXED:

FAULT-17 -- FAULT-16's mtime-growth guard (baseline_progress captured at the
TOP of Engine._run_agent_phase(), "the marker must be NEWER than baseline
before bare presence is trusted") answers "is this file faking completion"
correctly for a FRESH dispatch. It answers the wrong question on a RESUME
where an EARLIER dispatch already finished the work: the completed artifact's
mtime is already baked into THIS call's own baseline (captured fresh, every
call, at line ~697), so growth can never be observed -- nothing is ever going
to rewrite a file the dispatcher already correctly considers
already_satisfied.

LIVE EVIDENCE (run pres-wave-e-v3-1787240658, phase PF-DESIGN):
  - work order issued 2026-08-20T17:30:46-04:00, budget_minutes 30
  - working/research/design-brief-generated.md written 2026-08-20T17:34:17,
    33,267 bytes real content, matching the phase's own glob
    "working/research/design-brief-*.md"
  - PF-DESIGN.dispatcher-log.jsonl: worker dispatcher-77615 recorded
    {"status": "verified", "verifier_ok": true} the SAME SECOND (17:34:17)
  - a second dispatcher worker (dispatcher-95703) then logged
    {"status": "already_satisfied"} every ~10s from 17:37:03 through
    18:10:18 -- it could see the work was done the entire time
  - the engine still blocked at 18:10:19: "agent-authored phase produced
    nothing within 30 minutes" -- over a complete, already-verified artifact,
    on work that had been finished for 36 minutes

THE FIX: when the mtime-growth guard says "no new progress" AND this call is
re-entering onto a work order it did not itself just issue (a live claim, or
a still-outstanding work order -- the same claim_live/wo_live signal FAULT-09b
already computes to avoid clobbering), consult the same substance verifier
run_phase() calls downstream (phase_verifiers.verify(), reused verbatim). A
PASS means the work is genuinely done -- accept it. A FAIL changes nothing:
falls through to the identical wait/announce/checkpoint cadence, so a stale
or genuinely bad pre-existing file still cannot pass (FAULT-16 intact).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_f16_agent_phase_wait_race.py,
test_engine_client_report.py, etc.).
"""
from __future__ import annotations

import json
import os
import sys
import time as real_time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers -- deliberately duplicated from test_f16_agent_phase_wait_race.py
# rather than imported, matching this directory's own established convention
# (see that file's module docstring: "matching every sibling in this
# directory").
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
    """Same resolution order as test_f16_agent_phase_wait_race.py's
    _canonical_manifest()."""
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
    """Deterministic, instant stand-in for time.time()/time.sleep() -- see
    test_f16_agent_phase_wait_race.py's identical helper for the full
    rationale."""

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
    p.write_text("x" * 9500)
    os.utime(p, (mtime, mtime))


def _seed_live_work_order(rd: Path, phase) -> Path:
    """Simulate a RESUME: a work order for this phase was issued by an
    EARLIER dispatch (not this call) and is still live (not stale) -- the
    claim_live/wo_live signal FAULT-09b already computes, and FAULT-17's
    fix gates its verifier fallback on. Mirrors the live incident's
    PF-DESIGN.json, whose issued_at (17:30:46) predates the block (18:10:19)
    by over half an hour yet is well inside the phase's own
    stale_after = max(120, budget_minutes*60*2) window.

    Uses real_time.time() (NOT the monkeypatched time.time) for the on-disk
    mtime -- the same real-clock/fake-clock split test_f16's
    test_live_claim_prevents_work_order_clobber uses, because
    Path.stat().st_mtime always reads the OS's real clock regardless of
    what time.time() is monkeypatched to."""
    wo_dir = rd / "working" / "work-orders"
    wo_dir.mkdir(parents=True, exist_ok=True)
    wo_path = wo_dir / f"{phase.id}.json"
    wo_path.write_text(json.dumps({
        "phase": phase.id, "owning_role": phase.owning_role,
        "produces_artifact": phase.produces_artifact, "verifier": phase.verifier,
        "budget_minutes": phase.budget_minutes, "issued_at": "EARLIER-DISPATCH-2026-08-20T17:30:46-04:00",
    }, indent=2), encoding="utf-8")
    now = real_time.time()
    os.utime(wo_path, (now, now))
    return wo_path


# ---------------------------------------------------------------------------
# 1. THE FALSE BLOCK (mandatory -- must FAIL against pre-fix code): a
#    resume landing on a COMPLETE, verifier-PASSING artifact whose mtime
#    predates this call's own baseline must NOT block -- it must recognize
#    the work is done and return success, without burning the budget.
# ---------------------------------------------------------------------------
def test_resume_onto_finished_verifier_passing_work_does_not_false_block(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=False)
    phase = _prompt_phase(eng)
    rd = Path(eng.run_dir)

    _seed_live_work_order(rd, phase)

    clock = _install_clock(monkeypatch, on_sleep=None)  # nothing ever grows -- the
    # dispatcher already finished; there is nothing left for it to write.
    # The artifact predates this call's own baseline exactly like
    # design-brief-generated.md (17:34:17) predated the blocking call's
    # baseline capture in the live incident.
    _write_slide(rd, 1, clock.now - 10_000)

    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng.run_phase(phase)

    assert rc == EXIT_OK, (
        f"expected the resume to recognize already-finished, verifier-passing "
        f"work and succeed -- got {rc} (the false block: 'agent-authored phase "
        f"produced nothing' over a complete artifact, exactly the live "
        f"pres-wave-e-v3-1787240658 / PF-DESIGN incident)")
    assert clock.sleep_calls == 0, (
        "a verifier-confirmed-complete resume must be recognized on the FIRST "
        f"check, not after burning budget -- observed {clock.sleep_calls} sleep(s)")
    assert eng._phase_state(phase.id).get("status") == "done"


# ---------------------------------------------------------------------------
# 2. FAULT-16 MUST STILL BITE (guards against over-fixing): the exact same
#    resumed-onto-live-work setup, but the pre-existing artifact does NOT
#    pass its substance verifier and never grows -- must still keep
#    waiting / still block. Proves the FAULT-17 fallback is gated on a REAL
#    verifier PASS, not merely on "this call is a resume."
# ---------------------------------------------------------------------------
def test_resume_onto_live_work_with_failing_verifier_still_blocks(tmp_path, monkeypatch):
    eng = _engine(tmp_path, dry_run=False)
    phase = _prompt_phase(eng)
    rd = Path(eng.run_dir)

    _seed_live_work_order(rd, phase)

    clock = _install_clock(monkeypatch, on_sleep=None)
    _write_slide(rd, 1, clock.now - 10_000)  # stale AND genuinely incomplete
    # (only 1 of the 25 slides this phase's glob expects)

    verify_calls = []

    def fake_verify(phase_id, run_dir):
        verify_calls.append(phase_id)
        return False, ["AF-PROMPT-FLOOR: slide-25 missing"]

    monkeypatch.setattr(phase_verifiers, "verify", fake_verify)

    rc = eng.run_phase(phase)

    assert verify_calls, (
        "the FAULT-17 fallback must actually consult the real substance "
        "verifier on a resumed, non-growing artifact -- it must never assume "
        "a pass just because this call is a resume")
    assert rc == EXIT_GATE_BLOCKED, (
        f"a genuinely incomplete artifact must still block even on a resume -- "
        f"got {rc}. FAULT-16's protection must survive the FAULT-17 fix intact.")
    blocked = eng.state.get("blocked") or {}
    reason = blocked.get("reason") or ""
    assert "AF-PROMPT-FLOOR" in reason or "produced nothing" in reason, (
        f"expected an honest block reason (verifier reason or the generic "
        f"budget-timeout reason), got: {reason!r}")
