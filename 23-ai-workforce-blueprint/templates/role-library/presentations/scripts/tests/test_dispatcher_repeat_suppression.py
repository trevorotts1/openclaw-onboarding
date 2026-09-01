"""Tests for the dispatcher repeat-suppression ledger (FIX 2026-08-27).

THE FAULT (live-run proven, from the real sidecar logs of
~/webinar-decks/denise-calloway/trust-ledger/2026-08-27/working/work-orders/):

  (a) P-SP-INTAKE.dispatcher-log.jsonl: 494 byte-identical
      `"status": "declined"` records (382KB) -- sweep_run_dir() re-claimed and
      re-declined the same permanent DECLINE_PHASES verdict every ~10s for the
      life of the run.
  (b) P-0.5-RESEARCH.dispatcher-log.jsonl: 497 records, 495 of them
      `"status": "already_done_in_state"` with `"attempt": 0` -- a phase the
      Engine had already marked done was re-polled forever.

ONE CAUSE: sweep_run_dir() had no cross-tick memory. DISPATCH_RETRY_CAP (3)
bounds retries INSIDE one dispatch_one() call; each sweep tick called
dispatch_one() fresh, so nothing ever backed off, and no ceiling existed on
re-entry. (The `"attempt": 0` literal on those records was never a broken
counter -- it means "no model call was made on this tick". The per-call
counter increments correctly; the same live log's first line reads
`"attempt": 1, "status": "verified"`. What was missing was persistence
ACROSS calls, which the ledger now provides via `observations`/`consecutive`.)

THE ANTI-STARVATION CONTRACT these tests enforce (a prior fix on this box was
QC-rejected for over-suppressing): suppression is keyed on an outcome
SIGNATURE (status + reasons) AND a world revision (work-order file mtime+size,
plus this phase's own state.json status). ANY of

  * a different status,
  * a different reason text,
  * a reissued work-order file, or
  * a change in the phase's own state.json status

must reset the counter, emit a fresh sidecar record, and dispatch with ZERO
backoff delay. Only byte-identical repeats of an already-recorded outcome are
deduped/downgraded to ledger-only. A different outcome or a real state
transition can NEVER be swallowed.

No test in this file touches the live run directory, the network, or a real
DeepSeek call; record_outcome/should_dispatch are pure filesystem+json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import dispatcher as dj  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _mk_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "working" / "work-orders").mkdir(parents=True)
    (run / "state.json").write_text(json.dumps({
        "terminal": None,
        "phases": [{"id": "P-T", "status": "pending"}],
    }), encoding="utf-8")
    return run


def _sidecar(run: Path, phase_id: str) -> list:
    p = run / "working" / "work-orders" / f"{phase_id}.dispatcher-log.jsonl"
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _touch_order(run: Path, phase_id: str) -> None:
    """Simulate the Engine reissuing the work order (phases.py only rewrites a
    work order when it genuinely wants the phase dispatched again)."""
    of = run / "working" / "work-orders" / f"{phase_id}.json"
    of.write_text(json.dumps({"phase_id": phase_id, "reissued": time.time_ns()}),
                  encoding="utf-8")
    # guarantee an mtime_ns change even on coarse filesystems
    st = of.stat()
    import os
    os.utime(of, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def _set_phase_status(run: Path, phase_id: str, status: str) -> None:
    s = json.loads((run / "state.json").read_text(encoding="utf-8"))
    for ps in s["phases"]:
        if ps["id"] == phase_id:
            ps["status"] = status
    (run / "state.json").write_text(json.dumps(s), encoding="utf-8")


# ---------------------------------------------------------------------------
# Part 1: backoff engages on identical repeats
# ---------------------------------------------------------------------------
class TestBackoffEngages:
    def test_first_outcome_dispatches_with_zero_delay(self, tmp_path):
        run = _mk_run(tmp_path)
        assert dj.should_dispatch(run, "P-T") == (True, "")
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        led = dj._read_ledger(run, "P-T")
        assert led["consecutive"] == 1
        assert led["backoff_s"] == 0.0
        # repeat 0 => immediately eligible again
        assert dj.should_dispatch(run, "P-T")[0] is True

    def test_identical_repeat_is_deferred_inside_window(self, tmp_path):
        run = _mk_run(tmp_path)
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        # tick 2 within the (zero-delay first) window: allowed
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        led = dj._read_ledger(run, "P-T")
        assert led["consecutive"] == 2
        assert led["backoff_s"] == dj.DISPATCH_BACKOFF_BASE_S  # 30s
        may, why = dj.should_dispatch(run, "P-T")
        assert may is False
        assert "backoff" in why and "consecutive" in why

    def test_backoff_schedule_is_exponential_and_capped(self):
        assert dj._backoff_delay_s(0) == 0.0
        assert dj._backoff_delay_s(1) == dj.DISPATCH_BACKOFF_BASE_S
        assert dj._backoff_delay_s(2) == dj.DISPATCH_BACKOFF_BASE_S * 2
        assert dj._backoff_delay_s(3) == dj.DISPATCH_BACKOFF_BASE_S * 4
        # far past the cap
        assert dj._backoff_delay_s(50) == dj.DISPATCH_BACKOFF_CAP_S

    def test_window_expiry_re_eligible(self, tmp_path):
        run = _mk_run(tmp_path)
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        # travel past the 30s window
        future = time.time() + dj.DISPATCH_BACKOFF_BASE_S + 5
        may, _ = dj.should_dispatch(run, "P-T", now=future)
        assert may is True


# ---------------------------------------------------------------------------
# Part 2: ANTI-STARVATION -- a changed outcome ALWAYS emits and dispatches
# (the control a QC-rejected over-suppressing fix lacked)
# ---------------------------------------------------------------------------
class TestAntiStarvation:
    def test_different_reason_resets_and_emits(self, tmp_path):
        run = _mk_run(tmp_path)
        dj.record_outcome(run, "P-T", "declined", ["reason-A"], worker_id="w")
        dj.record_outcome(run, "P-T", "declined", ["reason-A"], worker_id="w")
        assert dj.should_dispatch(run, "P-T")[0] is False  # deferred
        # NEW outcome: different reason -> must dispatch immediately, zero delay
        may, _ = dj.should_dispatch(run, "P-T")  # ledger unchanged; still deferred
        d = dj.record_outcome(run, "P-T", "declined", ["reason-B"], worker_id="w")
        assert d["consecutive"] == 1  # reset
        assert d["observations"] == 3
        assert d["backoff_s"] == 0.0

    def test_different_status_resets_and_emits(self, tmp_path):
        run = _mk_run(tmp_path)
        dj.record_outcome(run, "P-T", "error", ["boom"], worker_id="w")
        d = dj.record_outcome(run, "P-T", "exhausted", ["boom"], worker_id="w")
        assert d["consecutive"] == 1
        assert d["backoff_s"] == 0.0
        # both outcomes are on the sidecar log
        statuses = [r["status"] for r in _sidecar(run, "P-T")]
        assert statuses == ["error", "exhausted"]

    def test_reissued_work_order_breaks_backoff(self, tmp_path):
        run = _mk_run(tmp_path)
        _touch_order(run, "P-T")  # the work order the ledger's revision was computed on
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        assert dj.should_dispatch(run, "P-T")[0] is False
        # Engine reissues the order -> deep backoff must be broken immediately
        _touch_order(run, "P-T")
        may, _ = dj.should_dispatch(run, "P-T")
        assert may is True, "a reissued work order MUST override any backoff window"

    def test_phase_state_change_breaks_backoff(self, tmp_path):
        run = _mk_run(tmp_path)
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        assert dj.should_dispatch(run, "P-T")[0] is False
        _set_phase_status(run, "P-T", "running")
        may, _ = dj.should_dispatch(run, "P-T")
        assert may is True, "a phase's own state transition MUST override any backoff"

    def test_other_phase_advancing_does_not_break_backoff(self, tmp_path):
        run = _mk_run(tmp_path)
        _touch_order(run, "P-T")
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        assert dj.should_dispatch(run, "P-T")[0] is False
        # an UNRELATED phase advances (whole-file mtime churn) -> window holds
        _set_phase_status(run, "P-OTHER", "done")
        may, _ = dj.should_dispatch(run, "P-T")
        assert may is False, "unrelated state churn must not reset this phase's backoff"


# ---------------------------------------------------------------------------
# Part 3: sidecar dedupe -- identical repeats are ledger-only
# ---------------------------------------------------------------------------
class TestSidecarDedupe:
    def test_identical_repeat_writes_no_new_sidecar_line(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(50):
            dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        lines = _sidecar(run, "P-T")
        # exactly TWO records: the first sighting, and the single loud
        # blocked_retry_ceiling park when the ceiling hit. Every one of the 48
        # byte-identical repeats between them wrote NOTHING.
        assert len(lines) == 2, "50 identical repeats must emit 1 record + 1 park"
        assert [r["status"] for r in lines] == ["declined", "blocked_retry_ceiling"]

    def test_the_one_record_carries_the_observation_count(self, tmp_path):
        run = _mk_run(tmp_path)
        for i in range(1, 51):
            led = dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        assert led["observations"] == 50
        assert led["consecutive"] == 50
        rec = _sidecar(run, "P-T")[0]
        assert rec["observation"] == 1  # first sighting's count, honestly reported
        assert rec["status"] == "declined"

    def test_new_outcome_after_repeats_emits_again(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(50):
            dj.record_outcome(run, "P-T", "declined", ["r1"], worker_id="w")
        dj.record_outcome(run, "P-T", "declined", ["r2"], worker_id="w")
        lines = _sidecar(run, "P-T")
        # declined r1 (1 record) + blocked park (1) + new outcome r2 (1)
        assert len(lines) == 3
        assert lines[-1]["consecutive"] == 1
        assert lines[-1]["reason"] == "r2"


# ---------------------------------------------------------------------------
# Part 4: hard retry ceiling -> BLOCKED with a VISIBLE reason, never silence
# ---------------------------------------------------------------------------
class TestRetryCeiling:
    def test_ceiling_parks_failing_phase_with_marker(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(dj.DISPATCH_REPEAT_CEILING):
            dj.record_outcome(run, "P-T", "error", ["always fails"], worker_id="w")
        led = dj._read_ledger(run, "P-T")
        assert led["blocked"] is True
        marker = dj._blocked_marker_path(run, "P-T")
        assert marker.is_file()
        text = marker.read_text(encoding="utf-8")
        assert "NEEDS ATTENTION" in text
        assert "P-T" in text and "always fails" in text

    def test_blocked_park_emits_sidecar_record_and_is_not_silent(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(dj.DISPATCH_REPEAT_CEILING):
            led = dj.record_outcome(run, "P-T", "exhausted", ["no good"], worker_id="w")
        statuses = [r["status"] for r in _sidecar(run, "P-T")]
        assert "blocked_retry_ceiling" in statuses, \
            "the park itself must be a visible, distinct sidecar record"

    def test_declined_parks_too_and_park_fires_exactly_once(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(dj.DISPATCH_REPEAT_CEILING + 10):
            dj.record_outcome(run, "P-T", "declined", ["driver_only"], worker_id="w")
        led = dj._read_ledger(run, "P-T")
        assert led["blocked"] is True
        statuses = [r["status"] for r in _sidecar(run, "P-T")]
        assert statuses.count("blocked_retry_ceiling") == 1, \
            "the park must fire once, not on every further repeat"

    def test_benign_repeat_never_parks(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(dj.DISPATCH_REPEAT_CEILING + 50):
            dj.record_outcome(run, "P-T", "already_done_in_state", worker_id="w")
        assert dj._read_ledger(run, "P-T")["blocked"] is False
        assert not dj._blocked_marker_path(run, "P-T").exists()

    def test_parked_phase_re_eligible_when_world_moves(self, tmp_path):
        run = _mk_run(tmp_path)
        for _ in range(dj.DISPATCH_REPEAT_CEILING):
            dj.record_outcome(run, "P-T", "error", ["boom"], worker_id="w")
        assert dj._read_ledger(run, "P-T")["blocked"] is True
        # parked window is long but finite; a reissued work order un-parks NOW
        _touch_order(run, "P-T")
        may, _ = dj.should_dispatch(run, "P-T")
        assert may is True, "a parked phase MUST resume on a real state transition"


# ---------------------------------------------------------------------------
# Part 5: terminal short-circuit in sweep_run_dir
# ---------------------------------------------------------------------------
class TestTerminalShortCircuit:
    def test_done_phase_recorded_without_dispatch_roundtrip(self, tmp_path, monkeypatch):
        run = _mk_run(tmp_path)
        _set_phase_status(run, "P-T", "done")
        order = {"phase_id": "P-T", "produces_artifact": ["x.txt"]}
        (run / "working" / "work-orders" / "P-T.json").write_text(json.dumps(order))

        called = {"dispatch_one": 0}
        monkeypatch.setattr(dj, "dispatch_one", lambda *a, **k: called.__setitem__("dispatch_one", called["dispatch_one"] + 1) or dj.DispatchResult("P-T", "ok", 1))

        monkeypatch.setattr(dj, "load_manifest_for_run", lambda run_dir: None)
        results = dj.sweep_run_dir(run, worker_id="w", max_workers=2)
        assert called["dispatch_one"] == 0, "a done phase must never reach dispatch_one"
        assert results == []
        led = dj._read_ledger(run, "P-T")
        assert led["status"] == "already_done_in_state"

    def test_decline_phase_recorded_without_dispatch_roundtrip(self, tmp_path, monkeypatch):
        run = _mk_run(tmp_path)
        phase = next(p for p in dj.DECLINE_PHASES)
        (run / "working" / "work-orders" / f"{phase}.json").write_text("{}")
        called = {"dispatch_one": 0}
        monkeypatch.setattr(dj, "dispatch_one", lambda *a, **k: called.__setitem__("dispatch_one", called["dispatch_one"] + 1) or dj.DispatchResult(phase, "declined", 0))

        monkeypatch.setattr(dj, "load_manifest_for_run", lambda run_dir: None)
        results = dj.sweep_run_dir(run, worker_id="w", max_workers=2)
        assert called["dispatch_one"] == 0
        assert results == []
        led = dj._read_ledger(run, phase)
        assert led["status"] == "declined"

    def test_decline_storm_suppressed_to_one_record_then_blocked(self, tmp_path, monkeypatch):
        """The live fault reproduced end-to-end: 494 identical declines become
        1 sidecar record, a parked marker, and a stopped round-trip."""
        run = _mk_run(tmp_path)
        phase = next(iter(dj.DECLINE_PHASES))
        (run / "working" / "work-orders" / f"{phase}.json").write_text("{}")
        monkeypatch.setattr(dj, "dispatch_one",
                            lambda *a, **k: dj.DispatchResult(phase, "declined", 0))
        monkeypatch.setattr(dj, "load_manifest_for_run", lambda run_dir: None)
        for _ in range(494):
            dj.sweep_run_dir(run, worker_id="w", max_workers=2)
        lines = (run / "working" / "work-orders" / f"{phase}.dispatcher-log.jsonl") \
            .read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) <= 2, (
            f"494 identical declines must collapse to <=2 sidecar records, got {len(lines)}")
        assert dj._blocked_marker_path(run, phase).exists()

    def test_undone_phase_still_dispatches_normally(self, tmp_path, monkeypatch):
        run = _mk_run(tmp_path)
        order = {"phase_id": "P-T"}
        (run / "working" / "work-orders" / "P-T.json").write_text(json.dumps(order))
        sent = {"n": 0}

        def fake_dispatch(run_dir, phase_id, order, **kw):
            sent["n"] += 1
            return dj.DispatchResult(phase_id, "ok", 1)

        monkeypatch.setattr(dj, "dispatch_one", fake_dispatch)
        monkeypatch.setattr(dj, "load_manifest_for_run", lambda run_dir: None)
        results = dj.sweep_run_dir(run, worker_id="w", max_workers=2)
        assert sent["n"] == 1
        assert results and results[0].status == "ok"