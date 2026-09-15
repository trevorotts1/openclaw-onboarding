"""PD-TEST-098 (verifier half) -- the SUBSTANCE VERIFIER must enforce the shared
prompt band, because THREE authorities consult it
(tests/test_pd098_design_verifier_band.py).

THE DEFECT THIS CLOSES. Fixing `artifacts.validate_artifact` alone was NOT
enough, and the independent review refuted that claim by driving the whole
chain. The `artifacts.py` arm does fire -- `phase.banked_invalid` is emitted and
the phase is checkpointed PENDING -- but TWO other authorities then re-blessed
the same over-ceiling artifact, so the net effect was 0 model calls and an
unchanged artifact:

  Authority 1 -- `Engine._phase_artifact_satisfied` (phases.py:2670) is
    `_artifacts_present` AND `phase_verifiers.verify`. `wo_satisfied`
    (phases.py:2813) uses it to complete a phase WITHOUT dispatching, so the
    engine re-attested the phase `done`, artifact byte-unchanged.
  Authority 2 -- the dispatcher's idempotent pre-check
    (dispatcher.py:5140-5157) consults the same verifier and returned
    `skipped_satisfied`.
  Authority 3 -- `_phase_already_done` (dispatcher.py:3226, called at :5090) is
    a STATUS-STRING-ONLY guard: no verifier, no artifact. It is why the engine's
    PENDING reset is load-bearing.

The old arm was `_make_pu_verifier` -> `_pu_check_text`, which accepted these
files on ">= 40 chars" alone, so `verify('P-U-DESIGN-SALES', run)` returned
`(True, [])` on the live 58,482-char prompt.

THE FIX. `_pu_check_design_prompt` enforces the shared band, read from
`prompt_gate`. One seam closes Authorities 1 and 2; the `artifacts.py` reset
closes Authority 3. BOTH are required -- neither alone heals the run.

MEASURED END TO END (real dispatcher, real manifest, model STUBBED, no paid
call), phase status `pending` vs `done`:

    status=pending -> dispatch_one returns `ok`, 3 model calls,
                      artifact 58,482 -> 17,858 chars, prompt_gate -> []
    status=done    -> dispatch_one returns `skipped_satisfied`, 0 calls

WHAT THESE TESTS PIN
  1. `phase_verifiers.verify` returns `(False, [reason naming AF-P2 and the
     measured length])` for all three live over-ceiling prompts
     (Authorities 1 + 2).
  2. `Engine._phase_artifact_satisfied` is therefore False.
  3. Driven through the REAL `Engine.run_phase`, the phase is NOT re-attested
     `done` and no `phase.work_order_satisfied` event fires.
  4. At `pending`, `dispatch_one` does NOT return `skipped_satisfied`; with a
     compliant stubbed model it RE-AUTHORS an artifact that clears the real
     gate (Authority 3 + the producer half together).
  5. BLAST RADIUS: non-design `P-U-*` text artifacts are unaffected.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # cross-test fixture import

import phase_verifiers as PV  # noqa: E402
import prompt_gate as PG  # noqa: E402
from presentation_job import dispatcher as D  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


def _find_shipped_manifest():
    """Walk UP from this file -- never a fixed `parents[N]` index, which raised
    `IndexError: 4` at COLLECTION time in a shallower tree."""
    for base in SCRIPTS.parents:
        cand = base / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
    return None


_SHIPPED = _find_shipped_manifest()

# (phase, artifact, live stripped length) -- measured read-only on the live run.
DESIGN = (
    ("P-U-DESIGN-SALES", "prompts/sales.design.txt", 58482),
    ("P-U-DESIGN-CHECKOUT", "prompts/checkout.design.txt", 49525),
    ("P-U-DESIGN-VSL", "prompts/vsl.design.txt", 51333),
)


def _manifest_file(tmp_path: Path, *, with_fanout: bool = True) -> Path:
    """A manifest carrying the REAL contract fields for the three design
    phases. The shipped v69 manifest is used when this tree has it, so the
    test drives the real contract; the inline copy is a fallback."""
    if _SHIPPED is not None:
        return _SHIPPED
    phases = []
    for i, (pid, rel, _n) in enumerate(DESIGN):
        entry = {"id": pid, "order": 4.2 + i, "owning_role": "slide-image-creator",
                 "produces_artifact": [rel], "client_report": {},
                 "executor": {"kind": "agent"}}
        if with_fanout:
            entry["fanout"] = {"by": "slide", "desired_count": 3, "batch_width": 3}
        phases.append(entry)
    mf = tmp_path / "mf.json"
    mf.write_text(json.dumps({"manifest_version": 69, "phases": phases,
                              "deliverables_required": []}))
    return mf


def _run_with_live_artifacts(tmp_path: Path, *, status: str = "done",
                             sizes=None, manifest_path: Path | None = None):
    """A run dir holding the three live over-ceiling design prompts, with real
    banked sha256 recorded, plus whatever run context the verifier reads."""
    rd = tmp_path / "run"
    (rd / "prompts").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps(
        {"slots": [{"ordinal": n, "arc": "A"} for n in range(1, 9)]}))
    (rd / "working" / "copy" / "slides.json").write_text(json.dumps(
        {"slides": [{"ordinal": n} for n in range(1, 9)]}))
    # The three design phases each `defers_unless` an intake flag; without the
    # flags the verifier correctly reports the phase DEFERRED (satisfied), which
    # would make the band assertions below vacuous.
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"client": "t", "want_sales_checkout": "yes", "want_vsl_page": "yes"}))
    mf = manifest_path or _manifest_file(tmp_path)
    phases = []
    for pid, rel, n in DESIGN:
        size = (sizes or {}).get(pid, n)
        p = rd / rel
        p.write_text("d" * size + "\n", encoding="utf-8")
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        phases.append({"id": pid, "status": status, "artifacts": [rel],
                       "sha256": {rel: sha}, "attempts": 1, "heal_events": [],
                       "attested_at": "x"})
    store = StateStore(rd)
    store.save({"job_id": "pj", "schema_version": 1, "run_dir": str(rd),
                "manifest_path": str(mf), "phases": phases, "events": [],
                "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}})
    return rd, mf


# ---------------------------------------------------------------------------
# 1 -- Authorities 1 and 2: the verifier itself.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_verify_rejects_the_live_over_ceiling_design_prompt(tmp_path, pid, rel, n):
    """THE ACCEPTANCE TARGET, half 1. Pre-fix this returned `(True, [])` -- the
    re-blessing that made the artifacts.py predicate a no-op in practice."""
    rd, _mf = _run_with_live_artifacts(tmp_path)
    ok, reasons = PV.verify(pid, rd)
    assert ok is False, (
        "the substance verifier must NOT accept an over-ceiling design prompt")
    joined = " ".join(reasons)
    assert "AF-P2" in joined, joined
    assert str(n) in joined, joined


def test_verify_accepts_an_in_band_design_prompt(tmp_path):
    """NEGATIVE CONTROL: without this, the test above would pass even if the
    verifier failed every design prompt, and no resume could ever reuse work."""
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: PG.PROMPT_CHAR_CEILING for pid, _r, _n in DESIGN})
    for pid, _rel, _n in DESIGN:
        ok, reasons = PV.verify(pid, rd)
        assert ok is True, f"{pid}: an in-band design prompt must verify: {reasons}"


def test_verify_band_is_read_from_prompt_gate(tmp_path, monkeypatch):
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: 30000 for pid, _r, _n in DESIGN})
    assert PV.verify(DESIGN[0][0], rd)[0] is False
    monkeypatch.setattr(PG, "PROMPT_CHAR_CEILING", 60000)
    monkeypatch.setattr(PG, "PROMPT_CHAR_FLOOR", 20000)
    ok, reasons = PV.verify(DESIGN[0][0], rd)
    assert ok is True, (
        "the verifier must follow prompt_gate's constants, not a second copy: "
        f"{reasons}")


def test_verify_under_floor_design_prompt_is_refused(tmp_path):
    rd, _mf = _run_with_live_artifacts(
        tmp_path, sizes={pid: 500 for pid, _r, _n in DESIGN})
    ok, reasons = PV.verify(DESIGN[0][0], rd)
    assert ok is False and "AF-P1" in " ".join(reasons), reasons


# ---------------------------------------------------------------------------
# 2/3 -- Authority 1 and the engine half, end to end.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_phase_artifact_satisfied_is_false(tmp_path, pid, rel, n):
    from presentation_job.phases import Engine
    rd, mf = _run_with_live_artifacts(tmp_path)
    eng = Engine(rd, Manifest(mf), StateStore(rd), StateStore(rd).load(), dry_run=True)
    assert eng._phase_artifact_satisfied(eng.manifest.phase(pid)) is False, (
        "Authority 1: a satisfied check that passes here re-attests the phase "
        "done without dispatching")


@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_engine_run_phase_does_not_reattest_done(tmp_path, pid, rel, n):
    """THE ACCEPTANCE TARGET, half 2 -- the half the review found unproven.
    Pre-fix: `phase.work_order_satisfied` fired and the phase went back to
    `done` with an unchanged artifact."""
    from presentation_job.phases import Engine
    rd, mf = _run_with_live_artifacts(tmp_path, status="done")
    before = (rd / rel).read_bytes()
    eng = Engine(rd, Manifest(mf), StateStore(rd), StateStore(rd).load(), dry_run=True)
    try:
        eng.run_phase(eng.manifest.phase(pid))
    except Exception:  # noqa: BLE001 -- the observable is the state, not the rc
        pass
    ps = eng._phase_state(pid)
    kinds = [e.get("kind") for e in eng.state.get("events", [])]
    satisfied = [e for e in eng.state.get("events", [])
                 if e.get("kind") == "phase.work_order_satisfied"
                 and pid in str(e.get("message", ""))]
    assert "phase.banked_invalid" in kinds, (
        "the artifacts.py half must announce the banked artifact invalid")
    assert ps.get("status") != "done", (
        "the phase was re-attested done on an over-ceiling artifact")
    assert not satisfied, "a satisfied work order must not complete this phase"
    assert (rd / rel).read_bytes() == before, "the artifact was not re-authored"


# ---------------------------------------------------------------------------
# 4 -- Authority 3 + the full self-heal, model STUBBED (no paid call).
# ---------------------------------------------------------------------------
def _stub_dispatch(monkeypatch, parts_for):
    calls: list = []

    def fake(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        calls.append(user_prompt)
        parts = parts_for()
        return (parts[min(len(calls), len(parts)) - 1],
                {"request_id": "req-stub"}, {"provider": "stub", "model": "stub"})

    monkeypatch.setattr(D, "dispatch_complete", fake)
    return calls


@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_pending_phase_is_not_skipped_and_is_reauthoried(tmp_path, monkeypatch, pid, rel, n):
    """THE STRONGEST EVIDENCE AVAILABLE WITHOUT A PAID CALL (review's ask).

    Authority 3 short-circuits on the STATUS STRING alone, so only a real
    dispatch proves the re-blessing is gone. At `pending` (the state the
    artifacts.py arm produces) `dispatch_one` must NOT return
    `skipped_satisfied`, must actually call the model, and the artifact it
    writes must clear the REAL shared gate."""
    from test_pd098_design_prompt_band import _compliant_parts
    rd, mf = _run_with_live_artifacts(tmp_path, status="pending")
    calls = _stub_dispatch(monkeypatch, lambda: _compliant_parts(3))
    man = Manifest(mf)
    res = D.dispatch_one(
        rd, pid, {"phase": pid, "owning_role": "slide-image-creator",
                  "produces_artifact": [rel]},
        dept_root=SCRIPTS.parent, phase_obj=man.phase(pid), worker_id="test")
    assert res.status != "skipped_satisfied", (
        "the dispatcher's idempotent pre-check re-blessed the artifact")
    assert len(calls) == 3, f"expected a real 3-unit re-author, got {len(calls)}"
    text = (rd / rel).read_text(encoding="utf-8").strip()
    assert PG.PROMPT_CHAR_FLOOR <= len(text) <= PG.PROMPT_CHAR_CEILING, (
        f"re-authored artifact is {len(text)} chars, outside the band")
    assert PG.prompt_problems(text, "One Request. One Package.") == []


@pytest.mark.parametrize("pid,rel,n", DESIGN)
def test_done_phase_is_still_skipped_by_the_status_guard(tmp_path, monkeypatch, pid, rel, n):
    """Authority 3, stated as a test so the dependency is explicit: while
    state.json says `done` the dispatcher skips on the status string and never
    reaches the verifier. This is exactly why the engine's PENDING reset is
    load-bearing and why the predicate alone changes nothing."""
    rd, mf = _run_with_live_artifacts(tmp_path, status="done")
    calls = _stub_dispatch(monkeypatch, lambda: ["x"])
    man = Manifest(mf)
    res = D.dispatch_one(
        rd, pid, {"phase": pid, "owning_role": "slide-image-creator",
                  "produces_artifact": [rel]},
        dept_root=SCRIPTS.parent, phase_obj=man.phase(pid), worker_id="test")
    assert res.status == "skipped_satisfied"
    assert calls == []


# ---------------------------------------------------------------------------
# 5 -- BLAST RADIUS on the verifier: non-design P-U-* text artifacts.
# ---------------------------------------------------------------------------
def test_non_design_pu_text_artifacts_are_unaffected(tmp_path):
    """Every other `_pu_check_text` consumer must keep the old ">= 40 chars"
    contract -- the new arm matches only `prompts/*.design.txt`."""
    rd = tmp_path / "run"
    body = "# fragment\n" + "real authored copy for the upsell page. " * 12
    for rel in ("working/upsell/copy/sales.fragment.md",
                "working/upsell/copy/copy_ledger.json",
                "working/upsell/copy/checkout.fragment.md",
                "working/upsell/vsl-research.md"):
        p = rd / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"ledger": body}) if rel.endswith(".json") else body,
                     encoding="utf-8")
    for pid in ("P-U-SALES-COPY", "P-U-CHECKOUT-COPY", "P-U-VSL-RESEARCH"):
        ok, reasons = PV.verify(pid, rd)
        assert ok is True, f"{pid}: non-design text artifact must still pass: {reasons}"
    # ...and the near-miss paths never enter the design arm
    for near in ("working/prompts/sales.design.txt", "prompts/sales.design.md",
                 "prompts/sales.txt"):
        assert not PV._DESIGN_PROMPT_REL_RE.match(near), near


def test_shipped_manifest_lookup_never_raises():
    """(D) nit: the old `SCRIPTS.parents[4]` raised IndexError at COLLECTION
    time outside the canonical tree depth."""
    import test_pd098_banked_design_revalidation as other
    # total: returns a Path or None, never raises, at ANY tree depth
    assert other._find_shipped_manifest() is not None
    assert _find_shipped_manifest() == other._find_shipped_manifest()
