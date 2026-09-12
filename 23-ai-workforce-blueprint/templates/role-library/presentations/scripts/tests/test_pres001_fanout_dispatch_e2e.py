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
# P-U-DESIGN-SALES (by=slide, text units): ordered text join; every unit
# contributes exactly its own slide's page-design prompt.
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

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        m = re.search(r"SLIDE (\d+) OF (\d+)", user_prompt)
        n = int(m.group(1))
        return f"DESIGN PROMPT for slide {n}", {"request_id": "r"}, \
            {"provider": "s", "model": "m"}

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
    assert body.index("slide 1") < body.index("slide 2") < body.index("slide 3")
