"""Tests for the RETURNED-OUTCOME LEDGER GAP (fix 2026-09-04).

THE FAULT (live-run proven, then reproduced at the seam here).

A 15-slide smoke deck on OpenClaw 2026.9.1 / skill 23 v24.1.2 stalled:
P-STYLE-SPEC emitted 37 identical `"status": "error"` records, one every
~10s from 20:11:04 to 20:18:23, still firing when the engine was killed.
In the SAME run P-SP-INTAKE and P0A-INTAKE each emitted 8 `"declined"`
records and then correctly self-parked with `blocked_retry_ceiling`.

The same split is on disk in an older real run, over a much longer window --
`.../runs/pres-wave-e-v3-1787240658/working/work-orders/`, the identical 542
sweep ticks between 2026-09-02T11:31:25 and 14:06:13:

  * P-SP-INTAKE  (a DECLINE_PHASES member, recorded via record_outcome)
      -> `.dispatch-state/P-SP-INTAKE.json` written, consecutive=542,
         blocked=True, plus a P-SP-INTAKE.dispatch-blocked.txt marker.
  * P4-PROMPT    (dispatch_one RETURNED DispatchResult(status="error"))
      -> 542 `"error"` rows in its 4.4MB sidecar log, one per tick, still
         firing on the last tick, NO ledger file at all, never parked.

542 vs 8, same run, same ticks, same failure class.

ROOT CAUSE -- a routing fault, not a per-call-site bug. record_outcome() had
exactly THREE call sites, and every one of them sat OUTSIDE dispatch_one's
normal return path:

  1. sweep_run_dir's DECLINE_PHASES short-circuit  (before the phase is claimed)
  2. sweep_run_dir's _phase_already_done short-circuit  (likewise)
  3. sweep_run_dir's `except` branch -- only when dispatch_one RAISES

Every value dispatch_one actually RETURNED -- "ok", "error", "exhausted",
"declined", "skipped_satisfied" -- was appended to `results` and dropped as far
as the ledger was concerned: no signature, no `consecutive`, no backoff window,
no ceiling, so should_dispatch() returned True on every tick forever. The
field shapes in the sidecar log show it directly:

    declined (via record_outcome): {worker, attempt, status, observation,
                                    consecutive, reason, at}
    error    (returned)          : {worker, attempt, status, reason, at}

The fanout zero-units refusal in _dispatch_phase_fanout_units is one instance
of that class; because sweep_run_dir is dispatch_one's only production caller,
folding the RETURNED outcome into the ledger at that one seam covers every
instance at once.

WHAT MUST NOT CHANGE. The zero-units refusal itself is CORRECT and stays
byte-for-byte: a fanout spec that enumerates no units must never invent a unit
and must never write an empty aggregate (S2). The bug was never the refusal --
it was that the refusal never stopped. And parking stays PARKED, NEVER DROPPED:
next_eligible_at_epoch = now + DISPATCH_BACKOFF_CAP_S, and any revision change
(a reissued work order, or this phase's own state.json status moving) un-parks
it on the very next tick, so a real upstream fix resumes the phase.

No test in this file makes a network call, spends a model token, touches a live
run directory, or starts a deck engine. The only stubbed seam is
dispatcher.dispatch_complete (the routed model entrypoint); the manifest, the
FanoutSpec, the enumerator, the sweep loop, the ledger, the backoff and the
ceiling are all the real code.
"""
from __future__ import annotations

import json
import sys
import time as _real_time
from collections import Counter
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import fanout as fo  # noqa: E402

PHASE = "P-STYLE-SPEC"
SPEC_ARTIFACT = "working/copy/style_preview_spec.json"

# The run pins the SAME canonical manifest load_manifest_for_run resolves --
# never a synthetic one (Manifest.load enforces MIN_MANIFEST_VERSION /
# MIN_MANIFEST_PHASES and a MANIFEST-SOURCE.txt sha, so a hand-rolled stub
# manifest could not load at all).
CLUSTER_MANIFEST = (
    _scripts_dir.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

# 200 ticks x 10s mirrors the real sweep cadence (the observed storm ran one
# record every ~10s). The backoff schedule after the fix is 0, 30, 60, 120,
# 240, 480, 900 -> the 8th and final dispatch lands at t=1840s and parks for
# DISPATCH_BACKOFF_CAP_S (900s), so the 2000s window ends with the phase still
# parked and no 9th dispatch. Before the fix the same window yields 200.
TICKS = 200
INTERVAL_S = 10.0


class _Clock:
    """A fake wall clock for should_dispatch/record_outcome. Everything except
    time() delegates to the real time module, so try_claim's clock_gettime /
    CLOCK_BOOTTIME liveness probe keeps working unchanged."""

    def __init__(self, t0: float) -> None:
        self._t = float(t0)

    def time(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt

    def __getattr__(self, name):  # pragma: no cover - pure delegation
        return getattr(_real_time, name)


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    c = _Clock(_real_time.time())
    monkeypatch.setattr(dj, "time", c)
    return c


def _seed_run(tmp_path: Path, *, slides: list | None = None) -> Path:
    """A run whose only work order is the fan-out phase.

    With slides=None the run carries NEITHER working/copy/slides.json NOR
    working/copy/arc_allocation.json -- the two sources fanout._slides_for_units
    reads -- so the REAL enumerator legitimately returns zero units. Nothing is
    monkeypatched to force that.
    """
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "state.json").write_text(json.dumps({
        "manifest_path": str(CLUSTER_MANIFEST),
        "phases": [{"id": PHASE, "status": "running"}],
    }), encoding="utf-8")
    (run_dir / "working" / "work-orders" / f"{PHASE}.json").write_text(json.dumps({
        "phase_id": PHASE, "owning_role": "brand-steward",
        "produces_artifact": SPEC_ARTIFACT,
    }), encoding="utf-8")
    if slides is not None:
        (run_dir / "working" / "copy" / "slides.json").write_text(
            json.dumps(slides), encoding="utf-8")
        (run_dir / "working" / "copy" / "intake.json").write_text(
            json.dumps({"business_name": "TestCo"}), encoding="utf-8")
    return run_dir


def _sidecar_rows(run_dir: Path) -> list:
    p = run_dir / "working" / "work-orders" / f"{PHASE}.dispatcher-log.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ledger(run_dir: Path) -> dict:
    return dj._read_ledger(run_dir, PHASE)


def _marker(run_dir: Path) -> Path:
    return run_dir / "working" / "work-orders" / f"{PHASE}.dispatch-blocked.txt"


def _sweep_n(run_dir: Path, clock: _Clock, n: int = TICKS) -> list:
    """Drive n real sweep ticks at the real cadence. Returns every
    DispatchResult the sweeps actually produced (one per real dispatch)."""
    out = []
    for _ in range(n):
        out.extend(dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=2))
        clock.advance(INTERVAL_S)
    return out


def _no_model(monkeypatch) -> list:
    """Fail loudly if the zero-units path ever reaches the model."""
    calls = []

    def _boom(*a, **kw):  # pragma: no cover - reaching this IS the failure
        calls.append(kw.get("phase_id"))
        raise AssertionError("zero-units refusal must never call the model")

    monkeypatch.setattr(dj, "dispatch_complete", _boom)
    return calls


# ---------------------------------------------------------------------------
# The enumerator genuinely returns zero here -- the premise of every test below
# is real, not stubbed.
# ---------------------------------------------------------------------------
def test_premise_real_enumerator_returns_zero_units(tmp_path):
    run_dir = _seed_run(tmp_path)
    spec = dj._phase_fanout_spec(PHASE, run_dir)
    assert spec is not None, "P-STYLE-SPEC must declare a manifest fanout field"
    assert spec.by == "slide"
    assert not (run_dir / "working" / "copy" / "slides.json").exists()
    assert not (run_dir / "working" / "copy" / "arc_allocation.json").exists()
    items = fo.enumerate_fanout_items(run_dir, spec, phase_id=PHASE,
                                      produces_artifact=[SPEC_ARTIFACT])
    assert items == [], f"expected zero units, got {items!r}"


# ---------------------------------------------------------------------------
# (a)/(b) The livelock: before the fix this ran forever; now it parks at 8.
# ---------------------------------------------------------------------------
def test_zero_units_refusal_parks_at_the_ceiling(tmp_path, clock, monkeypatch):
    _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)

    results = _sweep_n(run_dir, clock)

    # It STOPPED. Pre-fix this is TICKS (200); the ceiling is 8.
    assert len(results) == dj.DISPATCH_REPEAT_CEILING == 8, (
        f"expected exactly {dj.DISPATCH_REPEAT_CEILING} dispatches over "
        f"{TICKS} ticks / {TICKS * INTERVAL_S:.0f}s, got {len(results)}")
    assert {r.status for r in results} == {"error"}

    # It PARKED, and said so in all three non-silenceable places.
    led = _ledger(run_dir)
    assert led, "no ledger written for a returned outcome (the whole bug)"
    assert led["status"] == "error"
    assert led["consecutive"] == 8
    assert led["blocked"] is True
    assert "retry ceiling DISPATCH_REPEAT_CEILING=8" in led["blocked_reason"]
    assert "enumerated zero units" in led["blocked_reason"]
    assert _marker(run_dir).is_file()
    assert "DISPATCH BLOCKED" in _marker(run_dir).read_text(encoding="utf-8")

    rows = _sidecar_rows(run_dir)
    blocked = [r for r in rows if r["status"] == "blocked_retry_ceiling"]
    assert len(blocked) == 1, f"expected exactly one park record, got {len(blocked)}"
    assert blocked[0]["consecutive"] == 8

    # The park is a park, not a re-dispatch storm: it holds for the cap.
    may, why = dj.should_dispatch(run_dir, PHASE)
    assert may is False and "backoff" in why


def test_returned_error_now_carries_the_cross_tick_counter(tmp_path, clock, monkeypatch):
    """The field-shape defect: a returned `error` used to be logged with only
    {worker, attempt, status, reason, at} -- no `observation`, no
    `consecutive` -- because it never went through record_outcome."""
    _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)
    _sweep_n(run_dir, clock)

    rows = _sidecar_rows(run_dir)
    counted = [r for r in rows if "consecutive" in r and "observation" in r]
    assert counted, "no sidecar row carries the cross-tick counter"
    assert any(r["status"] == "error" for r in counted)


def test_repeat_storm_is_deduped_not_amplified(tmp_path, clock, monkeypatch):
    """The 542-row / 4.4MB log was the other half of the fault. record_outcome
    emits a counter row only when the outcome signature is NEW, so eight
    dispatches cannot produce eight counter rows."""
    _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)
    _sweep_n(run_dir, clock)

    rows = _sidecar_rows(run_dir)
    counts = Counter(r["status"] for r in rows)
    # 8 refusal records from the fanout path + exactly 1 ledger counter row
    # for the (single) distinct outcome + 1 park record.
    assert counts["blocked_retry_ceiling"] == 1
    assert sum(1 for r in rows if "consecutive" in r and r["status"] == "error") == 1
    assert len(rows) < 2 * TICKS  # nowhere near one row per tick


# ---------------------------------------------------------------------------
# (c) The refusal is PRESERVED. A fix that invents a unit is worse than the bug.
# ---------------------------------------------------------------------------
def test_refusal_preserved_never_invents_a_unit_or_an_empty_aggregate(
        tmp_path, clock, monkeypatch):
    calls = _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)

    results = _sweep_n(run_dir, clock)

    # No model was ever called: no unit was fabricated to have something to run.
    assert calls == []
    # No artifact on disk -- not a real one, not an empty one.
    assert not (run_dir / SPEC_ARTIFACT).exists()
    # No per-unit scratch output was invented either.
    unit_dir = fo.unit_output_dir(run_dir, PHASE)
    assert not unit_dir.exists() or not any(unit_dir.iterdir())
    # Every outcome is still the honest refusal, with its reason intact.
    assert results and all(r.status == "error" for r in results)
    assert all("no unit is ever invented" in " ".join(r.reasons) for r in results)
    # And the phase was NOT marked done/satisfied to make the symptom go away.
    assert all(r.status != "ok" for r in results)


# ---------------------------------------------------------------------------
# (d) Parked, never dropped: a real upstream fix un-parks the phase.
# ---------------------------------------------------------------------------
def test_revision_change_unparks_the_blocked_phase(tmp_path, clock, monkeypatch):
    _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)
    _sweep_n(run_dir, clock)
    assert _ledger(run_dir)["blocked"] is True
    assert dj.should_dispatch(run_dir, PHASE)[0] is False

    # The Engine reissues the work order (what a real upstream fix looks like).
    of = run_dir / "working" / "work-orders" / f"{PHASE}.json"
    of.write_text(of.read_text(encoding="utf-8") + " ", encoding="utf-8")

    may, why = dj.should_dispatch(run_dir, PHASE)
    assert may is True, f"a parked phase must un-park on a revision change ({why})"


def test_phase_state_change_also_unparks(tmp_path, clock, monkeypatch):
    _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)
    _sweep_n(run_dir, clock)
    assert dj.should_dispatch(run_dir, PHASE)[0] is False

    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["phases"] = [{"id": PHASE, "status": "retrying"}]
    state_path.write_text(json.dumps(state), encoding="utf-8")

    assert dj.should_dispatch(run_dir, PHASE)[0] is True


def test_unparked_phase_really_dispatches_again(tmp_path, clock, monkeypatch):
    """should_dispatch saying True is not enough -- prove the sweep acts on it
    and the counter restarts, so the phase is genuinely alive again."""
    _no_model(monkeypatch)
    run_dir = _seed_run(tmp_path)
    _sweep_n(run_dir, clock)
    assert _ledger(run_dir)["consecutive"] == 8

    of = run_dir / "working" / "work-orders" / f"{PHASE}.json"
    of.write_text(of.read_text(encoding="utf-8") + " ", encoding="utf-8")

    again = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=2)
    assert len(again) == 1, "un-parked phase did not re-dispatch"
    led = _ledger(run_dir)
    assert led["consecutive"] == 1, "the counter must restart on a new revision"
    assert led["blocked"] is False


# ---------------------------------------------------------------------------
# (e) No regression on the normal path: a fan-out phase WITH units still runs.
# ---------------------------------------------------------------------------
def _three_slides() -> list:
    return [{"ordinal": n, "slide": n, "slide_id": f"s{n}", "archetype": "cover",
             "copy": [f"Headline {n}"], "design_tokens": {"palette": "#223"},
             "research_anchors": [], "negative_requirements": []}
            for n in (1, 2, 3)]


def test_fanout_phase_with_units_still_dispatches_and_aggregates(
        tmp_path, clock, monkeypatch):
    seen = []

    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        seen.append(phase_id)
        n = len(seen)
        return (json.dumps({"id": "ABC"[n - 1],
                            "style_directive": f"variant {'ABC'[n - 1]} editorial",
                            "representative_slide": n}),
                {"request_id": f"stub-{n}"}, {"provider": "stub", "model": "stub-1"})

    monkeypatch.setattr(dj, "dispatch_complete", _fake)
    run_dir = _seed_run(tmp_path, slides=_three_slides())

    results = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=3)

    assert len(results) == 1 and results[0].status == "ok", \
        f"normal fan-out path regressed: {results and results[0].reasons}"
    assert len(seen) == 3, "one model call per fan-out unit"

    spec = json.loads((run_dir / SPEC_ARTIFACT).read_text(encoding="utf-8"))
    assert len(spec["variants"]) == 3
    assert {v["id"] for v in spec["variants"]} == {"A", "B", "C"}
    assert len(spec["representative_slides"]) == 3

    # The success is recorded too -- and a success can never park.
    led = _ledger(run_dir)
    assert led["status"] == "ok"
    assert led["blocked"] is False
    assert led["next_eligible_at_epoch"] <= clock.time(), \
        "a first-sighting outcome must carry zero backoff delay"


def test_successful_phase_is_not_parked_by_repetition(tmp_path, clock, monkeypatch):
    """`ok` is not in _FAILING_STATUSES, so even an unchanging repeat backs off
    but never reaches the ceiling."""
    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        return (json.dumps({"id": "A", "style_directive": "d", "representative_slide": 1}),
                {"request_id": "s"}, {"provider": "stub", "model": "stub-1"})

    monkeypatch.setattr(dj, "dispatch_complete", _fake)
    run_dir = _seed_run(tmp_path, slides=_three_slides())
    _sweep_n(run_dir, clock, n=40)

    led = _ledger(run_dir)
    assert led["blocked"] is False, "a non-failing status must never park"
    assert not _marker(run_dir).exists()


# ---------------------------------------------------------------------------
# The seam itself: the regression guard for the actual defect.
# ---------------------------------------------------------------------------
def test_every_returned_status_reaches_the_ledger(tmp_path, clock, monkeypatch):
    """dispatch_one's RETURN value -- not just a raised exception -- must be
    folded into the ledger. This is the one-line routing fault the whole fix
    turns on, asserted directly for each status dispatch_one can return."""
    run_dir = _seed_run(tmp_path)

    for status in ("ok", "error", "exhausted", "declined", "skipped_satisfied"):
        led_path = dj._ledger_path(run_dir, PHASE)
        if led_path.exists():
            led_path.unlink()
        monkeypatch.setattr(
            dj, "dispatch_one",
            lambda *a, _s=status, **k: dj.DispatchResult(PHASE, _s, 0, [f"r-{_s}"]))

        out = dj.sweep_run_dir(run_dir, worker_id="test-sweeper", max_workers=1)

        assert len(out) == 1 and out[0].status == status
        led = _ledger(run_dir)
        assert led, f"returned status {status!r} wrote no ledger entry"
        assert led["status"] == status
        assert led["consecutive"] == 1
        assert led["reasons"] == [f"r-{status}"]
        clock.advance(INTERVAL_S)
