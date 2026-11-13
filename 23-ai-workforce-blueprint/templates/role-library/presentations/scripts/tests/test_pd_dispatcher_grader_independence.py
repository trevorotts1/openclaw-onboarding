"""PD-068 (D-13) -- the grader is not told its grade and never grades its own
model's work.

Finding PD-068, decision D-13 (HOLD: built and staged, never merged until yes).

What is proven here (no paid call, no network, no manifest load):
  * the three QC report contracts describe their fields and say, in words, that
    a failing report is a correct output -- and no longer instruct `pass: true`;
  * a quality step whose stubbed report PARSES with `pass: false` returns
    `qc_failed` after EXACTLY ONE call, carrying the report's own reasons, and
    leaves that report on disk; a `pass: true` report in the same harness still
    goes through the verifier (the control that makes the first result mean
    something);
  * `qc_failed` is a failing status, so the phase still blocks/parks;
  * the pre-call family gate makes ZERO calls when the only eligible route is
    the author's own model family, and returns the plain reason
    "no independent model is available to grade this step";
  * with two families available it makes ONE call, pinned to the other family;
  * the family helper is the PD-204 rule (text after the last `/`, lower-case,
    up to the first non-letter).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402

QC_PHASE = "P1Q-COPY-QC"
QC_ROLE = "qc-specialist-copy"
REPORT_REL = "working/qc/copy_qc_report.json"


class QCPhase:
    id = QC_PHASE
    owning_role = QC_ROLE
    workers = 1
    budget_minutes = 5
    executor_kind = "agent"

    @staticmethod
    def resolve_artifact_patterns(_run_dir):
        return [REPORT_REL]


def _dept(tmp_path: Path) -> Path:
    dept = tmp_path / "dept"
    role = dept / "qc-specialist-copy"
    role.mkdir(parents=True)
    (role / "how-to.md").write_text(
        "Grade the copy against the rubric and report what you found.")
    return dept


def _run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "working/work-orders").mkdir(parents=True)
    (run / "working/qc").mkdir(parents=True)
    return run


def _report(pass_value: bool) -> str:
    return json.dumps({
        "gate": "Phase 1Q",
        "criteria": [{"name": "hook cadence", "score": 9.0},
                     {"name": "density", "score": 9.0}],
        "average": 9.0,
        "triggered_autofails": [],
        "pass": pass_value,
        "qc_independence": {"graded_by": "qc-specialist-presentations",
                            "independent": True, "self_graded": False},
    })


def _order(run: Path) -> dict:
    return {"phase": QC_PHASE, "owning_role": QC_ROLE,
            "produces_artifact": QCPhase.resolve_artifact_patterns(run)}


def _call(run, tmp_path):
    return D.dispatch_one(run, QC_PHASE, _order(run), dept_root=_dept(tmp_path),
                          phase_obj=QCPhase(), worker_id="test")


# --------------------------------------------------------------------------
# (1) the contracts say "report what you found; a failing report is a correct
# output", and stop ordering `pass: true`
# --------------------------------------------------------------------------
def test_the_three_report_contracts_allow_an_honest_failure():
    for phase_id in ("P1Q-COPY-QC", "P-PROMPT-QC", "P-TYPO-QC"):
        contract = D.ARTIFACT_CONTRACTS[phase_id]
        assert "Report what you found; a failing report is a correct output." in contract, phase_id
        assert "`pass`" in contract, (
            f"{phase_id} must still describe the pass field")
        assert "pass:true" not in contract, (
            f"{phase_id} still instructs pass:true unconditionally")


# --------------------------------------------------------------------------
# (2) pass:false -> qc_failed, ONE call, no retry; pass:true is the control
# --------------------------------------------------------------------------
def test_a_failing_report_is_one_call_and_qc_failed(tmp_path, monkeypatch):
    assert D.DISPATCH_RETRY_CAP > 1, "a retry must have been possible for this to mean anything"
    run = _run_dir(tmp_path)
    calls = {"n": 0}
    monkeypatch.setattr(D, "_verify", lambda *_a, **_k: (True, []))

    def _stub(*_args, **_kwargs):
        calls["n"] += 1
        return _report(False), {"request_id": "stub"}, {
            "provider": "stub-provider", "model": "stub-model"}

    monkeypatch.setattr(D, "dispatch_complete", _stub)

    result = _call(run, tmp_path)

    assert calls["n"] == 1, "a failing report must not be retried"
    assert result.status == "qc_failed", result.reasons
    assert result.attempts == 1
    # the report's own reasons, not a verifier paraphrase
    assert result.reasons == [f"{QC_PHASE} report says pass: false"], result.reasons
    # the honest report is the phase's correct output: it stays on disk
    on_disk = json.loads((run / REPORT_REL).read_text())
    assert on_disk["pass"] is False


def test_qc_failed_is_a_failing_status():
    assert "qc_failed" in D._FAILING_STATUSES


def test_a_passing_report_still_reaches_the_verifier(tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    calls = {"n": 0}
    verified = {"n": 0}

    def _verify(*_a, **_k):
        verified["n"] += 1
        return True, []

    def _stub(*_args, **_kwargs):
        calls["n"] += 1
        return _report(True), {"request_id": "stub"}, {
            "provider": "stub-provider", "model": "stub-model"}

    monkeypatch.setattr(D, "_verify", _verify)
    monkeypatch.setattr(D, "dispatch_complete", _stub)

    result = _call(run, tmp_path)

    assert calls["n"] == 1
    assert verified["n"] >= 2, "the pass:true control must reach the verifier"
    assert result.status == "ok", result.reasons


# --------------------------------------------------------------------------
# (3) the family gate: same family + one route -> zero calls, plain reason
# --------------------------------------------------------------------------
def test_same_family_with_one_route_makes_zero_calls(tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    monkeypatch.setattr(D, "_graded_author_model",
                        lambda _rd, _pid: "deepseek/deepseek-chat")
    monkeypatch.setattr(D, "_grader_route_decision", lambda _pid: {
        "route": {"provider": "deepseek-direct", "model": "deepseek-chat"},
        "candidates": [{"provider": "deepseek-direct", "model": "deepseek-chat",
                        "eligible": True, "reason": "wired on deepseek-direct"}],
    })
    calls = {"n": 0}

    def _stub(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("no model call may happen without an independent grader")

    monkeypatch.setattr(D, "dispatch_complete", _stub)

    result = _call(run, tmp_path)

    assert calls["n"] == 0
    assert result.status == "error"
    assert result.reasons == ["no independent model is available to grade this step"]
    assert not (run / REPORT_REL).exists()


def test_two_families_pin_the_other_family_and_call_once(tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    monkeypatch.setattr(D, "_graded_author_model",
                        lambda _rd, _pid: "deepseek/deepseek-chat")
    monkeypatch.setattr(D, "_grader_route_decision", lambda _pid: {
        "route": {"provider": "deepseek-direct", "model": "deepseek-chat"},
        "candidates": [
            {"provider": "deepseek-direct", "model": "deepseek-chat",
             "eligible": True},
            {"provider": "ollama-cloud", "model": "z-ai/glm-4.6",
             "eligible": True},
        ],
    })
    monkeypatch.setattr(D, "_verify", lambda *_a, **_k: (True, []))
    seen = {"n": 0, "override": "unset"}

    def _stub(*_args, **kwargs):
        seen["n"] += 1
        seen["override"] = kwargs.get("route_override")
        return _report(True), {"request_id": "stub"}, {
            "provider": "ollama-cloud", "model": "z-ai/glm-4.6"}

    monkeypatch.setattr(D, "dispatch_complete", _stub)

    result = _call(run, tmp_path)

    assert seen["n"] == 1
    assert seen["override"] == {"provider": "ollama-cloud", "model": "z-ai/glm-4.6"}, seen["override"]
    assert result.status == "ok", result.reasons


def test_an_unknown_author_never_invents_a_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_graded_author_model", lambda _rd, _pid: "")
    monkeypatch.setattr(D, "_grader_route_decision", lambda _pid: {
        "route": {"provider": "deepseek-direct", "model": "deepseek-chat"},
        "candidates": [{"provider": "deepseek-direct", "model": "deepseek-chat",
                        "eligible": True}],
    })
    refusal, override = D._independent_grader_decision(tmp_path, QC_PHASE, QC_ROLE)
    assert refusal == ""
    assert override is None


def test_a_non_qc_phase_is_never_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "_grader_route_decision",
                        lambda _pid: (_ for _ in ()).throw(AssertionError("must not route")))
    refusal, override = D._independent_grader_decision(
        tmp_path, "P4-COPY", "slide-copywriter")
    assert (refusal, override) == ("", None)


# --------------------------------------------------------------------------
# the family helper is PD-204's rule, verbatim
# --------------------------------------------------------------------------
def test_model_family_follows_the_pd204_rule():
    assert D._model_family("deepseek/deepseek-chat") == "deepseek"
    assert D._model_family("deepseek-reasoner") == "deepseek"
    assert D._model_family("claude-opus-4-1") == "claude"
    assert D._model_family("z-ai/glm-4.6v") == "glm"
    assert D._model_family("GLM-5.3-Flash") == "glm"
    assert D._model_family("") == ""
    assert D._model_family(None) == ""

# --------------------------------------------------------------------------
# (4) THE FAN-OUT SEAM. P-PROMPT-QC and P-IMAGE-QC declare
#     `fanout: {by: slide}` in the manifest, so their per-slide model calls
#     come from _dispatch_phase_fanout_units' unit worker -- NOT the serial
#     loop in dispatch_one. The gate has to stand in front of that seam too.
# --------------------------------------------------------------------------
import contextlib  # noqa: E402
import types  # noqa: E402

FANOUT_PHASE = "P-PROMPT-QC"
FANOUT_ROLE = "qc-specialist-prompt-presentations"
FANOUT_REPORT = "working/qc/prompt_qc_report.json"

class FanoutQCPhase:
    id = FANOUT_PHASE
    owning_role = FANOUT_ROLE
    workers = 1
    budget_minutes = 5
    executor_kind = "agent"
    fanout = {"by": "slide", "batch_width": 12}

def _fanout_call(run: Path, tmp_path: Path):
    dept = _dept(tmp_path)
    role = dept / FANOUT_ROLE
    role.mkdir(parents=True)
    (role / "how-to.md").write_text("Grade the per-slide prompts honestly.")
    return D._dispatch_phase_fanout_units(
        run,
        {"phase": FANOUT_PHASE, "owning_role": FANOUT_ROLE,
         "produces_artifact": [FANOUT_REPORT]},
        dept_root=dept, phase_obj=FanoutQCPhase(), worker_id="test",
        spec=types.SimpleNamespace(desired_count=None, batch_width=None),
        patterns=[FANOUT_REPORT], target=run / FANOUT_REPORT, prior_reasons=[])

def test_fanout_quality_step_refuses_before_any_preflight_or_unit_call(
        tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    monkeypatch.setattr(D, "_graded_author_model",
                        lambda _rd, _pid: "deepseek/deepseek-chat")
    monkeypatch.setattr(D, "_grader_route_decision", lambda _pid: {
        "route": {"provider": "deepseek-direct", "model": "deepseek-chat"},
        "candidates": [{"provider": "deepseek-direct", "model": "deepseek-chat",
                        "eligible": True}],
    })

    def _must_not_run(*_a, **_k):
        raise AssertionError("a refused fan-out quality step must make zero unit calls")

    monkeypatch.setattr(D, "_preflight_fanout_contract", _must_not_run)
    monkeypatch.setattr(D.fanout, "enumerate_fanout_items", _must_not_run)
    monkeypatch.setattr(D, "dispatch_complete", _must_not_run)

    result = _fanout_call(run, tmp_path)

    assert result.status == "error"
    assert result.attempts == 0
    assert result.reasons == ["no independent model is available to grade this step"]

class _StopAfterPin(Exception):
    pass

def test_fanout_quality_step_pins_the_other_family_into_every_unit(
        tmp_path, monkeypatch):
    run = _run_dir(tmp_path)
    monkeypatch.setattr(D, "_graded_author_model",
                        lambda _rd, _pid: "deepseek/deepseek-chat")
    monkeypatch.setattr(D, "_grader_route_decision", lambda _pid: {
        "route": {"provider": "deepseek-direct", "model": "deepseek-chat"},
        "candidates": [
            {"provider": "deepseek-direct", "model": "deepseek-chat",
             "eligible": True},
            {"provider": "ollama-cloud", "model": "z-ai/glm-4.6",
             "eligible": True},
        ],
    })
    monkeypatch.setattr(D, "_preflight_fanout_contract", lambda *_a, **_k: "")
    monkeypatch.setattr(D.fanout, "enumerate_fanout_items",
                        lambda *_a, **_k: [{"key": "slide-01"}])
    monkeypatch.setattr(D, "_unit_payload_enrichment",
                        lambda _rd, _pid, it, _n: {"key": it["key"],
                                                   "ordinal": 1,
                                                   "unit_inputs_now": {}})
    monkeypatch.setattr(D, "_preflight_section_payload_ranges",
                        lambda *_a, **_k: "")
    monkeypatch.setattr(D, "_read_units_ledger", lambda *_a, **_k: [])
    monkeypatch.setattr(D, "unit_store", None)
    monkeypatch.setattr(D, "paid_unit_scope",
                        lambda *_a, **_k: contextlib.nullcontext())
    seen = {"calls": 0, "override": "unset"}

    def _dispatch_stub(*_args, **kwargs):
        seen["calls"] += 1
        seen["override"] = kwargs.get("route_override")
        return _report(True), {"request_id": "stub"}, {
            "provider": "ollama-cloud", "model": "z-ai/glm-4.6"}

    monkeypatch.setattr(D, "dispatch_complete", _dispatch_stub)

    held = {}

    def _run_units_spy(units, worker_fn, **_kwargs):
        held["r"] = worker_fn(units[0])
        raise _StopAfterPin()

    monkeypatch.setattr(D.fanout, "run_units", _run_units_spy)

    with __import__("pytest").raises(_StopAfterPin):
        _fanout_call(run, tmp_path)

    assert seen["calls"] == 1, seen
    assert seen["override"] == {"provider": "ollama-cloud", "model": "z-ai/glm-4.6"}, seen
