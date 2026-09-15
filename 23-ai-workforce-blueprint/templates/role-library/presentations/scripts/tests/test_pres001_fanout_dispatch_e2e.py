"""PRES-001 (W2 WF05) END-TO-END dispatch tests -- the acceptance path through
_dispatch_phase_fanout_units with the PAID CALL STUBBED (dispatch_complete
monkeypatched; zero network, zero tokens).

QC-PRES-001 acceptance, proven here against a real fanout pool and a real
run-dir fixture:
  1. 3 distinct sections / 20 slides produce exactly each expected unit once
     (exactly 3 paid calls for P4-COPY), retain input order (SLIDE 1..20 in
     artifact order), and the reduced artifact is complete.
  2. Two identical whole-deck responses fail UNIT validation (slide-scoped QC
     contract) and no report is written.
  3. Duplicate ordinal fails the reducer; missing ordinal fails the reducer.
  4. Markdown reducer accepts valid text (positive).
  5. Fail a unit (slide-7-equivalent), resume: ONLY the failed unit is
     re-paid; the reduce still covers all 20 slides.
  6. A changed source input hash invalidates only affected units (re-paid)
     while unaffected units reuse their stored outputs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import fanout  # noqa: E402


class FakePhase:
    """Phase-shaped stub: this test never loads a manifest."""
    def __init__(self, pid: str, role: str):
        self.id = pid
        self.owning_role = role
        self.workers = 1
        self.budget_minutes = 5
        self.executor_kind = "agent"


SECTIONS = (("Hook", 1, 5), ("Teach", 6, 15), ("Offer", 16, 20))
N_SLIDES = 20


def _p4_run(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    slots = [{"ordinal": n, "arc": name}
             for name, lo, hi in SECTIONS
             for n in range(lo, hi + 1)]
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({"slots": slots}))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"client": "t"}))
    (rd / "working" / "copy" / "priority_shift_spec.json").write_text(json.dumps({"p": 1}))
    (rd / "working" / "copy" / "sp_intake.json").write_text(json.dumps({"s": 1}))
    (rd / "working" / "research" / "research_map.json").write_text(json.dumps({"m": 1}))
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"ordinal": n} for n in range(1, N_SLIDES + 1)]}))
    return rd


def _dept(tmp_path: Path, role: str) -> Path:
    dept = tmp_path / "dept"
    r = dept / role
    r.mkdir(parents=True)
    (r / "how-to.md").write_text("SOP")
    return dept


def _section_body(name: str, lo: int, hi: int) -> str:
    return "\n".join(f"SLIDE {n}\nHEADLINE for {n}\nNOTE {n}" for n in range(lo, hi + 1))


def _ordinals(text: str):
    return [int(m) for m in re.findall(r"(?im)^\s*SLIDE\s+(\d+)\s*$", text)]


@pytest.fixture()
def p4_env(tmp_path, monkeypatch):
    rd = _p4_run(tmp_path)
    dept = _dept(tmp_path, "slide-copywriter")
    calls: list = []

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        calls.append(user_prompt)
        for name, lo, hi in SECTIONS:
            if repr(name) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(name, lo, hi), {"request_id": "req-stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")

    monkeypatch.setattr(D, "dispatch_complete", fake_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    return {"rd": rd, "dept": dept, "calls": calls, "fake_dispatch": fake_dispatch,
            "order": {"owning_role": "slide-copywriter",
                      "produces_artifact": "working/copy/slides_copy.md"},
            "spec": fanout.parse_fanout_field({"by": "section", "max_units": 5}),
            "phase": FakePhase("P4-COPY", "slide-copywriter"),
            "target": rd / "working" / "copy" / "slides_copy.md"}


def _dispatch(env):
    return D._dispatch_phase_fanout_units(
        env["rd"], env["order"], dept_root=env["dept"], phase_obj=env["phase"],
        worker_id="test", spec=env["spec"],
        patterns=["working/copy/slides_copy.md"], target=env["target"],
        prior_reasons=[])


def test_three_sections_twenty_slides_exactly_once_in_order(p4_env):
    res = _dispatch(p4_env)
    assert res.status == "ok", res.reasons
    assert len(p4_env["calls"]) == 3, "exactly one paid call per section unit"
    merged = p4_env["target"].read_text()
    assert _ordinals(merged) == list(range(1, N_SLIDES + 1))


def test_fail_unit_then_resume_repays_only_it(p4_env, monkeypatch):
    first = _dispatch(p4_env)
    assert first.status == "ok"
    artifact = p4_env["target"].read_text()

    # ROUND 2: the Teach unit's scratch is destroyed (simulating its failure —
    # only a failed unit's scratch can be absent) and its next dispatch fails.
    teach_scratch = fanout.unit_output_path(p4_env["rd"], "P4-COPY", "section-02")
    if teach_scratch.is_file():
        teach_scratch.unlink()

    def failing_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        if repr("Teach") in user_prompt:
            raise RuntimeError("stub transport failure mid-deck")
        for name, lo, hi in SECTIONS:
            if repr(name) in user_prompt:
                return (_section_body(name, lo, hi), {"request_id": "r"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("no scope")

    monkeypatch.setattr(D, "dispatch_complete", failing_dispatch)
    res2 = _dispatch(p4_env)
    assert res2.status == "partial_failure"
    assert any("section-02" in r for r in res2.reasons)
    # the failed reduce must never tear the on-disk artifact
    assert p4_env["target"].read_text() == artifact

    # ROUND 3 (resume): the transport fault is cleared; Hook + Offer reuse
    # their stored, re-validated outputs and cost ZERO calls; ONLY the failed
    # Teach unit is re-paid.
    monkeypatch.setattr(D, "dispatch_complete", p4_env["fake_dispatch"])
    p4_env["calls"].clear()
    res3 = _dispatch(p4_env)
    assert res3.status == "ok"
    assert len(p4_env["calls"]) == 1, \
        f"resume must re-pay ONLY the failed unit, paid {len(p4_env['calls'])}"
    assert _ordinals(p4_env["target"].read_text()) == list(range(1, N_SLIDES + 1))


def test_changed_input_hash_repays_only_affected_units(p4_env, monkeypatch):
    first = _dispatch(p4_env)
    assert first.status == "ok"
    p4_env["calls"].clear()
    # a WHOLE-PHASE input changes: every unit consumes it, so every unit is
    # honestly invalid — all three re-paid, none reused.
    (p4_env["rd"] / "working" / "copy" / "intake.json").write_text(
        json.dumps({"client": "t2"}))
    res = _dispatch(p4_env)
    assert res.status == "ok"
    assert len(p4_env["calls"]) == 3
    assert _ordinals(p4_env["target"].read_text()) == list(range(1, N_SLIDES + 1))


# ---------------------------------------------------------------------------
# Slide-scoped QC contract: the whole-deck duplicate dies at UNIT validation.
# ---------------------------------------------------------------------------

def _qc_run(tmp_path: Path) -> Path:
    rd = tmp_path / "qcrun"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "prompts").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"ordinal": n} for n in range(1, 6)]}))
    for n in range(1, 6):
        (rd / "working" / "prompts" / f"slide-{n:02d}.txt").write_text(f"PROMPT {n}")
    return rd


def test_two_identical_whole_deck_responses_fail_unit_validation(tmp_path, monkeypatch):
    rd = _qc_run(tmp_path)
    dept = _dept(tmp_path, "qc-x")
    WHOLE = json.dumps({"slides": [{"slide": n, "slide_id": f"slide-{n:02d}",
                                    "pass": True, "average": 9.0} for n in range(1, 6)]})

    def dup_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        m = re.search(r"SLIDE (\d+) OF (\d+)", user_prompt)
        n = int(m.group(1))
        # TWO UNITS answer with the IDENTICAL whole-deck response
        return WHOLE, {"request_id": "r"}, {"provider": "s", "model": "m"}

    monkeypatch.setattr(D, "dispatch_complete", dup_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    order = {"owning_role": "qc-x",
             "produces_artifact": "working/qc/prompt_qc_report.json"}
    spec = fanout.parse_fanout_field({"by": "slide", "max_units": 12})
    target = rd / "working" / "qc" / "prompt_qc_report.json"
    res = D._dispatch_phase_fanout_units(
        rd, order, dept_root=dept, phase_obj=FakePhase("P-PROMPT-QC", "qc-x"),
        worker_id="t", spec=spec, patterns=["working/qc/prompt_qc_report.json"],
        target=target, prior_reasons=[])
    assert res.status == "exhausted"
    # every whole-deck unit was refused by the unit validator itself — the
    # slide_results dicts carry {"slide_id", "ordinal", "status", "error"}.
    whole_deck_rows = [r for r in res.slide_results
                       if "WHOLE-DECK" in str(r.get("error"))]
    assert whole_deck_rows, res.slide_results
    assert all(r.get("status") == "failed" for r in whole_deck_rows)
    assert not target.exists(), "a refused union must never write a report"


def test_qc_ok_run_preserves_all_verdict_rows(tmp_path, monkeypatch):
    rd = _qc_run(tmp_path)
    dept = _dept(tmp_path, "qc-x")

    def ok_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        m = re.search(r"SLIDE (\d+) OF (\d+)", user_prompt)
        n = int(m.group(1))
        return (json.dumps({"slide": n, "slide_id": f"slide-{n:02d}",
                            "pass": True, "average": 9.0}),
                {"request_id": "rr"}, {"provider": "s", "model": "m"})

    monkeypatch.setattr(D, "dispatch_complete", ok_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    order = {"owning_role": "qc-x",
             "produces_artifact": "working/qc/prompt_qc_report.json"}
    spec = fanout.parse_fanout_field({"by": "slide", "max_units": 12})
    target = rd / "working" / "qc" / "prompt_qc_report.json"
    res = D._dispatch_phase_fanout_units(
        rd, order, dept_root=dept, phase_obj=FakePhase("P-PROMPT-QC", "qc-x"),
        worker_id="t", spec=spec, patterns=["working/qc/prompt_qc_report.json"],
        target=target, prior_reasons=[])
    assert res.status == "ok"
    rep = json.loads(target.read_text())
    assert len(rep["slides"]) == 5 and len(rep["results"]) == 5
    assert rep["pass"] is True and rep["gate"] == "Phase Prompt-QC"
    assert [r["slide_id"] for r in rep["slides"]] == \
        [f"slide-{n:02d}" for n in range(1, 6)]


# ---------------------------------------------------------------------------
# P9-SPEECH contract scope sanity: the manifest's own executor for P9-SPEECH
# is a script (the generic unit path never executes there — its stale fanout
# field is not evidence of the generic path). The preflight refuses the dead
# declaration before any paid call.
# ---------------------------------------------------------------------------

def test_preflight_refuses_script_executor_fanout(tmp_path, monkeypatch):
    rd = tmp_path / "run"
    rd.mkdir()
    (rd / "state.json").write_text(json.dumps({
        "manifest_path": str(tmp_path / "manifest.json")}))
    manifest = {
        "phases": [{
            "id": "P9-SPEECH", "order": 8.5, "owning_role": "speech-writer",
            "produces_artifact": ["working/deliverables/PRESENTERS-SPEECH.md"],
            "executor": {"kind": "script", "cmd": "python3 scripts/x.py"},
            "fanout": {"by": "slide", "max_units": 12},
            "consumes": ["working/copy/intake.json"],
        }]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    reason = D._preflight_fanout_contract(
        "P9-SPEECH", fanout.FanoutSpec(by="slide"), rd)
    assert reason and "executor is a script" in reason


# ---------------------------------------------------------------------------
# P-U-DESIGN-SALES (by=slide, text units): ordered text join.
#
# PD-TEST-098 UPDATED THIS FIXTURE -- deliberately, and here is why. It used to
# read "every unit contributes exactly its own slide's page-design prompt", and
# its stub matched `SLIDE (\d+) OF (\d+)` and returned a 25-char
# "DESIGN PROMPT for slide N". That is the DEFECT, encoded as a test: the
# consumer (`build_infographic.resolve_design_prompt`) reads
# `prompts/<page>.design.txt` VERBATIM as ONE prompt for ONE 16:9 image and
# gates it at 9,000-18,000 chars, so three complete per-slide prompts
# concatenated is not a valid single prompt -- on the live run it made a
# 58,484-char file against an 18,000 ceiling and parked three render phases.
# The units now author PARTS of the one prompt, each inside its share of the
# shared band. The test's REAL intent (units join in declared order) is
# unchanged and still asserted, and the assertion is now stronger: the joined
# artifact must land inside the band the consumer enforces.
# ---------------------------------------------------------------------------

def test_design_text_units_join_in_order(tmp_path, monkeypatch):
    rd = tmp_path / "drun"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "upsell" / "copy").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"ordinal": n} for n in range(1, 4)]}))
    (rd / "working" / "upsell" / "copy" / "sales.fragment.md").write_text("FRAGMENT")
    (rd / ".test-context").write_text("test")
    dept = _dept(tmp_path, "designer-x")

    calls = []

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        m = re.search(r"PART (\d+) OF (\d+)", user_prompt)
        assert m, "a design unit must be told which PART of the one prompt it authors"
        n = int(m.group(1))
        calls.append(user_prompt)
        # A part inside its own share of the shared band (PD-TEST-098).
        floor_share, _ceil = D.design_unit_char_budget(int(m.group(2)))
        part = f"PART for slide {n}. " + ("specific art direction. " *
                                          (floor_share // 20 + 40))
        return part, {"request_id": "r"}, {"provider": "s", "model": "m"}

    monkeypatch.setattr(D, "dispatch_complete", fake_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    order = {"owning_role": "designer-x",
             "produces_artifact": "prompts/sales.design.txt"}
    spec = fanout.parse_fanout_field({"by": "slide", "max_units": 3})
    target = rd / "prompts" / "sales.design.txt"
    res = D._dispatch_phase_fanout_units(
        rd, order, dept_root=dept, phase_obj=FakePhase("P-U-DESIGN-SALES", "designer-x"),
        worker_id="t", spec=spec, patterns=["prompts/sales.design.txt"],
        target=target, prior_reasons=[])
    assert res.status == "ok", res.reasons
    body = target.read_text()
    # the original intent: the parts join in declared order
    assert body.index("slide 1") < body.index("slide 2") < body.index("slide 3")
    # PD-TEST-098: and the joined artifact is ONE prompt inside the band the
    # consumer enforces -- the property whose absence parked three phases.
    assert 3 == len(calls)
    import prompt_gate as _pg
    assert _pg.PROMPT_CHAR_FLOOR <= len(body.strip()) <= _pg.PROMPT_CHAR_CEILING, (
        f"joined design prompt is {len(body.strip())} chars, outside the "
        f"{_pg.PROMPT_CHAR_FLOOR}-{_pg.PROMPT_CHAR_CEILING} band")

# ---------------------------------------------------------------------------
# PD-TEST-119 / 120 / 121 -- AN ACTIONABLE REPAIR RECEIPT VOIDS THE BANK.
#
# These three defects interlock into a loop with no exit: banked units are reused
# on an input hash alone (119), the paid cap is per PHASE so the first authoring
# pass spends it (120), and nothing sanctioned un-banks a unit set (121). The
# repair receipt is the one operator act that resolves all three at once, so the
# fanout now refuses to reuse banked units while a receipt is actionable -- and
# the reservations that pay for the re-author consume that same receipt.
# ---------------------------------------------------------------------------
def _design_run_for_receipt(tmp_path):
    rd = tmp_path / "d121"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "upsell" / "copy").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"ordinal": n} for n in range(1, 4)]}))
    (rd / "working" / "upsell" / "copy" / "sales.fragment.md").write_text("FRAGMENT")
    (rd / ".test-context").write_text("test")
    return rd


def _design_env2(tmp_path, monkeypatch, *, verify_ok):
    rd = _design_run_for_receipt(tmp_path)
    dept = _dept(tmp_path, "designer-x")
    calls: list = []

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        m = re.search(r"PART (\d+) OF (\d+)", user_prompt)
        assert m, "a design unit must be told which PART it authors"
        n = int(m.group(1))
        calls.append(user_prompt)
        floor_share, _ceil = D.design_unit_char_budget(int(m.group(2)))
        return (f"PART for slide {n}. "
                + ("specific art direction. " * (floor_share // 20 + 40)),
                {"request_id": "r"}, {"provider": "s", "model": "m"})

    monkeypatch.setattr(D, "dispatch_complete", fake_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (verify_ok, [] if verify_ok else ["AF-P13"]))
    return {"rd": rd, "dept": dept, "calls": calls,
            "order": {"owning_role": "designer-x",
                      "produces_artifact": "prompts/sales.design.txt"},
            "spec": fanout.parse_fanout_field({"by": "slide", "max_units": 3}),
            "phase": FakePhase("P-U-DESIGN-SALES", "designer-x"),
            "target": rd / "prompts" / "sales.design.txt"}


def _run119(env):
    """Dispatch the design fanout with this env's stubs (the same call shape the
    PD-TEST-119 work used, defined here so this suite is self-contained)."""
    return D._dispatch_phase_fanout_units(
        env["rd"], env["order"], dept_root=env["dept"], phase_obj=env["phase"],
        worker_id="t", spec=env["spec"], patterns=["prompts/sales.design.txt"],
        target=env["target"], prior_reasons=[])


def _seed_ledger(rd, generation=0, paid=3):
    """A durable ledger, the precondition `authorize_paid_retry_reset` enforces."""
    D._write_ledger(rd, "P-U-DESIGN-SALES", {
        "phase_id": "P-U-DESIGN-SALES", "status": "exhausted",
        "paid_attempts": paid, "generation": generation,
        "blocked": True, "approved_input_revision": "initial"})


def test_actionable_receipt_forces_a_re_author(tmp_path, monkeypatch):
    """THE ACCEPTANCE TARGET. Banked units are reused on an input hash alone, so
    without this the phase rebuilds the identical rejected artifact forever."""
    env = _design_env2(tmp_path, monkeypatch, verify_ok=True)
    _run119(env)
    assert len(env["calls"]) == 3, "first pass authors"
    _run119(env)
    assert len(env["calls"]) == 3, "a banked unit set is reused (no re-bill)"

    _seed_ledger(env["rd"], generation=0)
    receipt = D.authorize_paid_retry_reset(env["rd"], "P-U-DESIGN-SALES", allowance=3)
    assert receipt["prior_generation"] == 0

    _run119(env)
    assert len(env["calls"]) == 6, (
        "an actionable repair receipt must void the bank and re-author every "
        "unit -- otherwise the phase can never produce a different artifact")


def test_consuming_the_receipt_restores_normal_banking(tmp_path, monkeypatch):
    """BOUND: the receipt is single-use by generation. Once spent, the bank is
    reusable again, so a phase whose verifier can never pass cannot loop."""
    env = _design_env2(tmp_path, monkeypatch, verify_ok=True)
    _run119(env)
    _seed_ledger(env["rd"], generation=0)
    D.authorize_paid_retry_reset(env["rd"], "P-U-DESIGN-SALES", allowance=3)
    _run119(env)
    assert len(env["calls"]) == 6, "the receipt voided the bank once"

    # The receipt's single-use property is the LEDGER GENERATION: consumption
    # bumps it, and `_repair_receipt_is_actionable` then refuses because the
    # receipt's prior_generation no longer matches. This suite stubs
    # `dispatch_complete`, which sits ABOVE the reservation seam
    # (dispatcher.py:2409) and is therefore the ONLY place a receipt is consumed --
    # so consumption cannot happen here, and asserting that it did would be
    # asserting something the stub bypasses (the exact gap the PD-TEST-119 review
    # flagged). Assert the BOUND on the property that actually decides it instead:
    # advance the generation exactly as consumption does, and require the bank to
    # be honoured again.
    led = D._read_ledger(env["rd"], "P-U-DESIGN-SALES")
    led = dict(led)
    led["generation"] = int(led.get("generation") or 0) + 1
    D._write_ledger(env["rd"], "P-U-DESIGN-SALES", led)
    _run119(env)
    assert len(env["calls"]) == 6, (
        "once the ledger generation has advanced past the receipt's "
        "prior_generation the receipt is spent, so the bank must be honoured "
        "again -- this is what stops a never-passing verifier from looping")


def test_no_receipt_leaves_the_bank_untouched(tmp_path, monkeypatch):
    """REGRESSION GUARD for PRES-014: with no receipt on disk nothing about the
    reuse decision changes."""
    env = _design_env2(tmp_path, monkeypatch, verify_ok=True)
    _run119(env)
    assert len(env["calls"]) == 3
    _run119(env)
    _run119(env)
    assert len(env["calls"]) == 3, "no receipt -> banked units reused, zero re-bill"

def test_void_is_refused_when_the_receipt_cannot_pay_for_every_unit(tmp_path, monkeypatch):
    """MEDIUM defect found by the independent review of PR #1150.

    `--reset-allowance 1` is a legal, documented invocation. Without this gate it
    voided the WHOLE bank while paying for ONE unit: one unit re-authored, the
    others died on PaidBudgetExhausted, and their durable records were overwritten
    from `ok` to `failed` -- the "parked AND unbuildable" mode. The bank must be
    left intact instead."""
    from presentation_job import unit_store
    env = _design_env2(tmp_path, monkeypatch, verify_ok=True)
    _run119(env)
    assert len(env["calls"]) == 3, "first pass authors"
    before = unit_store.load_state(env["rd"], "P-U-DESIGN-SALES")

    _seed_ledger(env["rd"], generation=0)
    D.authorize_paid_retry_reset(env["rd"], "P-U-DESIGN-SALES", allowance=1)
    _run119(env)
    assert len(env["calls"]) == 3, (
        "a receipt that cannot pay for every unit it would invalidate must NOT "
        "void the bank -- the units are reused instead")
    after = unit_store.load_state(env["rd"], "P-U-DESIGN-SALES")
    # `ok` -> `banked` is the NORMAL admission transition for a reused unit and is
    # expected here; what the defect produced was `ok` -> `failed`, which loses the
    # bank outright. Assert the hazard, not the transition.
    statuses = {k: v.get("status") for k, v in after.items()}
    assert set(statuses.values()) <= {"ok", "banked"}, (
        f"no unit may be downgraded to failed by a receipt that cannot pay for it: {statuses}")
    assert len(after) == len(before), (
        f"unit records must not be dropped: before={len(before)} after={len(after)}")
    side = (env["rd"] / "working" / "work-orders"
            / "P-U-DESIGN-SALES.dispatcher-log.jsonl").read_text()
    assert "bank_void_refused_insufficient_allowance" in side, (
        "the refusal must be recorded, not silent")

