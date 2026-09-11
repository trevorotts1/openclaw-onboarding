#!/usr/bin/env python3
"""test_f6_fanout_width.py -- F6: fan-out phases run at the measured width, not at 1.

THE FAULT (PRESENTATION-DEPT-FABLE-REVIEW section 3.8 / fix list F6).

`dispatcher._dispatch_phase_fanout_units` -- the generic runner for EVERY
manifest phase that declares a `fanout` field -- resolved its pool width like
this:

    effective_workers = resolve_effective_workers(
        phase_obj.workers if phase_obj is not None else 1, unit_count=len(items))

`Phase.workers` defaults to 1 when the manifest omits the key
(`manifest.py`: `workers: int = 1`), and EIGHT of the nine fan-out phases in
the shipped manifest omit it:

    P4-COPY, P-U-DESIGN-SALES, P-U-DESIGN-CHECKOUT, P-U-DESIGN-VSL,
    P-PROMPT-QC, P-STYLE-SPEC, P-IMAGE-QC, P9-SPEECH

(only P4-PROMPT declares `workers: 12`, and P4-PROMPT never reaches this
function -- it has its own pool path). `min()`'s first term was therefore the
constant 1, and `capacity_available` was never passed at all: a cap installed
as a floor of one. Every declared fan-out phase ran its units strictly
serially -- 20-25 sequential language-model calls per QC phase, twice per
deck, plus copy by section -- while the run's measured capacity said 8, 100 or
2,500.

THE FIX. The width now comes from the SAME authority P4-PROMPT's wave uses:
`_routing_stamp` (renamed from `_prompt_routing_stamp`, which was never
P4-specific) -> client resource profile -> route -> capacity probe -> mode
ceiling -> `measured_capacity`; then `min()`'d against the unit count and the
per-phase env override. `phase.workers` is not a cap on this path: the
manifest's `fanout` field is the opt-in flag, and this function is only
reached when `_phase_fanout_spec()` returned one.

WHAT THESE TESTS PROVE, AND HOW THEY FAIL ON PRISTINE main:

  1. width == min(routed_capacity, units), recorded by the real pool in
     `working/fanout/<phase>-progress.json` -- pristine records 1.
  2. with more units than capacity, width == the routed capacity (8), not the
     unit count and not 1 -- pristine records 1.
  3. the per-phase env override has a SHELL-LEGAL name
     (`PRESENTATION_PHASE_WORKERS_P_STYLE_SPEC`, not the un-assignable
     `...P-STYLE-SPEC` the fix brief's f-string would produce) and is honoured
     on this path -- pristine has no `fanout.phase_worker_env_var` at all.
  4. two units are ACTUALLY in flight at the same instant (a threading.Barrier
     that only trips when a second thread arrives) -- pristine deadlocks the
     barrier at width 1 and the phase comes back "exhausted".
  5. the `_prompt_routing_stamp` -> `_routing_stamp` rename is a rename, not a
     break: the old name still resolves to the same object -- pristine has no
     `_routing_stamp`.

NO NETWORK, NO MODEL SPEND, NO LIVE RUN DIRECTORY. The only stubbed seams are
`dispatcher.dispatch_complete` (the routed model entrypoint) and
`dispatcher._model_router` set to None -- the documented router-absent
rollback, which makes the routing stamp's number deterministic
(DEFAULT_MAX_WORKERS) on any box without reading a client profile or firing a
capacity probe. The manifest, the FanoutSpec, the enumerator, the real
`fanout.run_units` ThreadPoolExecutor, the aggregator, the atomic write and
the phase verifier are all the real code.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

PHASE = "P-STYLE-SPEC"          # manifest: fanout by slide, NO `workers` key
OWNING_ROLE = "brand-steward"


# ---------------------------------------------------------------------------
# Harness (same shape as tests/test_fix112_missing_producers.py, which proves
# this exact phase end to end through the same seams).
# ---------------------------------------------------------------------------
def _seed_run(tmp_path: Path, n_slides: int) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    slides = [
        {"ordinal": i, "slide": i, "slide_id": f"s{i}", "archetype": "cover",
         "copy": [f"Line {i}"], "design_tokens": {"palette": "#223"},
         "research_anchors": [], "negative_requirements": []}
        for i in range(1, n_slides + 1)
    ]
    (run_dir / "working" / "copy" / "slides.json").write_text(json.dumps(slides))
    (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"business_name": "TestCo", "hook": "Grow without guesswork"}))
    (run_dir / "state.json").write_text(json.dumps(
        {"manifest_path": str(CLUSTER_MANIFEST)}))
    return run_dir


def _phase_obj(run_dir: Path, pid: str = PHASE):
    from presentation_job.dispatcher import load_manifest_for_run
    m = load_manifest_for_run(run_dir)
    assert m is not None, "state.json did not resolve the deployed manifest"
    po = m.phase_or_none(pid)
    assert po is not None, f"{pid} missing from the deployed manifest"
    return po


def _router_absent(monkeypatch):
    """The documented router-absent rollback. `_routing_stamp` then returns its
    base stamp -- measured_capacity = DEFAULT_MAX_WORKERS -- without resolving
    a client profile or firing a capacity probe, so the expected width is the
    same integer on every box and in CI."""
    import presentation_job.dispatcher as d
    monkeypatch.setattr(d, "_model_router", None)
    return d.DEFAULT_MAX_WORKERS


def _stub_units(monkeypatch, body):
    """Stub the routed model entrypoint. `body(n)` returns the unit's text."""
    import presentation_job.dispatcher as d
    calls: list = []
    lock = threading.Lock()

    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        with lock:
            calls.append(phase_id)
            n = len(calls)
        return body(n), {"request_id": f"stub-{n}"}, {"provider": "stub", "model": "stub-1"}

    monkeypatch.setattr(d, "dispatch_complete", _fake)
    return calls


def _variant(n: int) -> str:
    """One P-STYLE-SPEC unit's output: {id, style_directive, representative_slide}."""
    vid = "ABC"[(n - 1) % 3]
    return json.dumps({"id": vid,
                       "style_directive": f"variant {vid} warm editorial direction",
                       "representative_slide": ((n - 1) % 3) + 1})


def _pool_width(run_dir: Path, phase_id: str = PHASE) -> int:
    """The width the REAL pool ran at, as `fanout.run_units` itself recorded it
    (`progress["workers"] = workers`, set from the ThreadPoolExecutor's own
    max_workers). Read through fanout's own path helper -- never a guessed
    filename."""
    from presentation_job import fanout as _f
    path = _f._progress_path(run_dir, phase_id)
    assert path.is_file(), (
        f"the fan-out pool wrote no progress artifact at {path} -- "
        f"the phase never reached fanout.run_units")
    return int(json.loads(path.read_text())["workers"])


def _dispatch(d, run_dir: Path):
    return d.dispatch_one(
        run_dir, PHASE, {"phase_id": PHASE, "owning_role": OWNING_ROLE},
        dept_root=SCRIPTS.parent, phase_obj=_phase_obj(run_dir),
        worker_id="test-f6")


# ---------------------------------------------------------------------------
# 1. The width is the routed capacity min'd with the unit count -- never 1.
# ---------------------------------------------------------------------------
def test_fanout_phase_runs_at_the_routed_width_not_at_one(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    routed = _router_absent(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=3)
    calls = _stub_units(monkeypatch, _variant)

    # The manifest genuinely declares NO `workers` for this phase: the pre-F6
    # code path had literally nothing but the default 1 to work with.
    assert _phase_obj(run_dir).workers == 1, (
        "harness assumption broken: P-STYLE-SPEC now declares `workers` in the "
        "manifest, so this test no longer exercises the absent-workers default")

    result = _dispatch(d, run_dir)
    assert result.status == "ok", f"fanout dispatch failed: {result.reasons}"
    assert len(calls) == 3, calls

    width = _pool_width(run_dir)
    assert width == min(routed, 3), (
        f"fan-out ran at width {width}; expected min(routed={routed}, units=3). "
        f"width==1 is the F6 defect: phase.workers (absent => 1) used as the cap")
    assert width > 1, "F6: the phase ran SERIALLY"


# ---------------------------------------------------------------------------
# 2. More units than capacity: the width is the ROUTED number, not the unit
#    count and not 1.
# ---------------------------------------------------------------------------
def test_width_is_the_routed_capacity_when_units_exceed_it(tmp_path, monkeypatch):
    """PRES-014 UPDATE (W2 WF05): the manifest now migrates the style spec's
    max_units to {desired_count: 3, batch_width: 3}, so a 12-slide deck
    admits EXACTLY 3 units (the phase's desired work count) in ONE bounded
    batch of width 3. The pre-PRES-014 expectation (12 units admitted, one
    pool at the routed width 8) is superseded: the whole point of the fix is
    that a 100-slide style deck makes 3 variant calls, not 12 and not 100.
    The routed-width claim this test kept alive for F6 is now proven by the
    per-slide QC phases (batch_width 12, desired_count absent -> all units
    admitted, each batch bounded by the routed width)."""
    import presentation_job.dispatcher as d
    routed = _router_absent(monkeypatch)
    assert routed == 8, (
        f"DEFAULT_MAX_WORKERS moved to {routed}; update this test's expectation")
    run_dir = _seed_run(tmp_path, n_slides=12)
    calls = _stub_units(monkeypatch, _variant)

    result = _dispatch(d, run_dir)
    assert result.status == "ok", f"fanout dispatch failed: {result.reasons}"

    # desired_count=3: exactly 3 model calls over a 12-slide deck.
    assert len(calls) == 3, calls
    width = _pool_width(run_dir)
    assert width == 3, (
        f"fan-out ran at width {width}; expected the migrated batch_width 3 "
        f"(the style spec's bounded batch). 1 = the F6 defect")

    # The width and the migration are on the audit trail too.
    rows = _sidecar_rows(run_dir)
    plan = [r for r in rows if r.get("status") == "fanout_plan"]
    assert plan, f"no fanout_plan sidecar row: {rows}"
    assert plan[0].get("units_desired") == 3, plan[0]
    assert plan[0].get("units_enumerated") == 12, plan[0]
    final = [r for r in rows if r.get("status") in ("verified", "failed")]
    assert final, f"no terminal sidecar row for {PHASE}: {rows}"
    assert final[-1].get("routed_width") == routed, final[-1]


def _sidecar_rows(run_dir: Path) -> list:
    import presentation_job.dispatcher as d
    path = d._sidecar_path(run_dir, PHASE) if hasattr(d, "_sidecar_path") else None
    if path is None:
        # locate the sidecar the writer actually used, without guessing a name
        cands = sorted((run_dir / "working" / "work-orders").rglob(f"*{PHASE}*"))
        cands = [c for c in cands if c.is_file() and c.suffix in (".jsonl", ".log", ".json")]
        assert cands, f"no sidecar file found for {PHASE} under working/work-orders"
        path = cands[0]
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# ---------------------------------------------------------------------------
# 3. The per-phase env override -- with a name a shell can actually assign.
# ---------------------------------------------------------------------------
def test_phase_worker_env_var_is_shell_legal_and_is_honoured(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    from presentation_job import fanout as _f

    # A raw f"PRESENTATION_PHASE_WORKERS_{phase_id}" is NOT assignable in any
    # shell for a real phase id -- every fan-out phase in the manifest has a
    # hyphen, one has a dot. The builder collapses them.
    name = _f.phase_worker_env_var(PHASE)
    assert name == "PRESENTATION_PHASE_WORKERS_P_STYLE_SPEC", name
    assert name.replace("_", "").isalnum(), (
        f"{name} is not a legal shell variable name")
    assert _f.phase_worker_env_var("P8.3-INFOGRAPHIC") == \
        "PRESENTATION_PHASE_WORKERS_P8_3_INFOGRAPHIC"

    _router_absent(monkeypatch)
    monkeypatch.setenv(name, "2")
    run_dir = _seed_run(tmp_path, n_slides=12)
    _stub_units(monkeypatch, _variant)

    result = _dispatch(d, run_dir)
    assert result.status == "ok", f"fanout dispatch failed: {result.reasons}"
    width = _pool_width(run_dir)
    assert width == 2, (
        f"the env override named {name} was not honoured on the manifest "
        f"fan-out path: ran at {width}, expected 2")


# ---------------------------------------------------------------------------
# 4. Two units are ACTUALLY in flight at the same instant.
#    This is the behavioural proof, not a recorded number: at width 1 the
#    barrier can never trip and the phase comes back exhausted.
# ---------------------------------------------------------------------------
def test_units_run_concurrently_not_one_after_another(tmp_path, monkeypatch):
    """PRES-014 UPDATE (W2 WF05): the style spec's migrated batch_width is 3,
    so 4 enumerated slides admit one bounded batch of 3 units in flight
    TOGETHER (desired_count=3 caps the calls, not the overlap). The barrier
    needs a partner count that matches the batch: 3 units in one pool at
    width min(routed=8, batch=3)=3 -- all three wait on a Barrier(3), which
    can only trip when the pool is genuinely concurrent. At width 1 (the F6
    defect) it deadlocks and the phase comes back failed."""
    import presentation_job.dispatcher as d
    _router_absent(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=4)

    barrier = threading.Barrier(3, timeout=20)
    tripped = {"n": 0}
    lock = threading.Lock()
    seq = {"n": 0}

    def _fake(system_prompt, user_prompt, *, phase_id, run_dir=None, **kw):
        with lock:
            seq["n"] += 1
            n = seq["n"]
        # Only returns once a THIRD thread reaches this line. At width 1 it
        # raises BrokenBarrierError after the timeout -- exactly the serial
        # behaviour F6 removes (and PRES-014 keeps removed).
        barrier.wait()
        with lock:
            tripped["n"] += 1
        return _variant(n), {"request_id": f"stub-{n}"}, \
            {"provider": "stub", "model": "stub-1"}

    monkeypatch.setattr(d, "dispatch_complete", _fake)

    result = _dispatch(d, run_dir)
    assert result.status == "ok", (
        f"units did not overlap -- the pool ran them one at a time and the "
        f"concurrency barrier timed out: {result.reasons}")
    assert tripped["n"] == 3, tripped


# ---------------------------------------------------------------------------
# 5. The rename is a rename, not a break.
# ---------------------------------------------------------------------------
def test_routing_stamp_is_not_p4_specific_and_keeps_its_old_name(tmp_path, monkeypatch):
    import presentation_job.dispatcher as d
    assert hasattr(d, "_routing_stamp"), (
        "F6 renames _prompt_routing_stamp -> _routing_stamp: the width authority "
        "is not P4-PROMPT-specific")
    assert d._prompt_routing_stamp is d._routing_stamp, (
        "the old name must keep resolving to the same object -- "
        "test_defect5_routing_stamp_provider_identity.py and "
        "test_fix11_mode_axis.py both call it")

    routed = _router_absent(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=1)
    for pid in (PHASE, "P-PROMPT-QC", "P4-PROMPT"):
        stamp = d._routing_stamp(run_dir=run_dir, phase_id=pid)
        assert int(stamp["measured_capacity"]) == routed, (pid, stamp)
    # default arg preserves the pre-rename call shape
    assert d._routing_stamp(run_dir=run_dir) == d._routing_stamp(
        run_dir=run_dir, phase_id="P4-PROMPT")


# ---------------------------------------------------------------------------
# 6. phase.workers is no longer a cap on this path.
# ---------------------------------------------------------------------------
def test_phase_workers_is_not_a_cap_on_the_manifest_fanout_path(tmp_path, monkeypatch):
    """A `workers: 1` phase object -- what the manifest hands every fan-out
    phase except P4-PROMPT -- must not clamp the pool. The `fanout` field is
    the opt-in flag; `workers` is not the ceiling here."""
    import dataclasses
    import presentation_job.dispatcher as d
    routed = _router_absent(monkeypatch)
    run_dir = _seed_run(tmp_path, n_slides=3)
    _stub_units(monkeypatch, _variant)

    po = _phase_obj(run_dir)
    assert po.workers == 1
    forced = dataclasses.replace(po, workers=1)

    result = d.dispatch_one(
        run_dir, PHASE, {"phase_id": PHASE, "owning_role": OWNING_ROLE},
        dept_root=SCRIPTS.parent, phase_obj=forced, worker_id="test-f6")
    assert result.status == "ok", result.reasons
    assert _pool_width(run_dir) == min(routed, 3)
