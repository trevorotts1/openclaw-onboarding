#!/usr/bin/env python3
"""test_pd_phase_checks_human_review.py — PD-206a (finding PD-206/PD-306).

The two human verdicts on the minimum path (the prompt check's casting review
and the image check's grounding review) are read from THEIR OWN files:

    working/qc/human-review/representation_casting.json   -> P-PROMPT-QC
    working/qc/human-review/image_grounding.json          -> P-IMAGE-QC

each `{"pass": true|false, "reviewed_by": "<person or role>",
       "reviewed_at": "<time>", "note": "<free text>"}`.

A missing verdict is an OPERATOR HOLD (a reason starting `OPERATOR-REVIEW:`
that names the file), never a pass and never a block typed inside the graded
report — a report edit changes the report's hash and breaks its execution
stamp (PD-306). Nothing in this test calls a model or a live service: the
report the checks grade is built by the dispatcher's OWN merge function
(`presentation_job.dispatcher._reduce_qc_union`) from stub slide verdicts.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402
from presentation_job import dispatcher  # noqa: E402

GROUNDING_REL = "working/qc/human-review/image_grounding.json"
CASTING_REL = "working/qc/human-review/representation_casting.json"
OPERATOR = "OPERATOR-REVIEW:"


@pytest.fixture(autouse=True)
def _production_context(monkeypatch):
    """No degraded marker: the checks must fail closed in production."""
    for key in ("PRESENTATION_ALLOW_DEGRADED_VERIFIERS", "CI", "OPENCLAW_TEST"):
        monkeypatch.delenv(key, raising=False)


def _merged_report(phase_id: str, gate: str, slides: int = 3) -> str:
    """The merged QC report the dispatcher writes, from stub slide verdicts
    (its own reducer — no model call)."""
    ordered = []
    for n in range(1, slides + 1):
        payload = {"phase_id": phase_id, "slide_id": f"slide-{n:02d}",
                   "ordinal": n, "unit_count": slides,
                   "reviewer_role": "qc-specialist-presentations"}
        row = {"slide_id": f"slide-{n:02d}", "slide": n, "pass": True,
               "score": 9.1,
               "qc_independence": {"graded_by": "qc-specialist-presentations",
                                    "independent": True}}
        ordered.append((payload, json.dumps(row)))
    merged = dispatcher._reduce_qc_union(ordered)
    assert merged is not None, "the dispatcher merge refused well-formed stub rows"
    return merged


def _seed_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    qc = run / "working" / "qc"
    qc.mkdir(parents=True)
    (qc / "prompt_qc_report.json").write_text(_merged_report(
        "P-PROMPT-QC", "Phase Prompt-QC"))
    (qc / "image_qc_report.json").write_text(_merged_report(
        "P-IMAGE-QC", "Phase Image-QC"))
    return run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verdict(run: Path, rel: str, **fields) -> Path:
    path = run / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields))
    return path


def _reviewed(sub_verifier_name: str):
    """The registry's sub-verdict leg with the base report gate stubbed: the base
    gate is build_deck's own report-shape check (another unit's surface), and
    this unit is proven to change only the human-verdict leg."""
    sub = getattr(pv, sub_verifier_name)
    return pv._fix16_aggregate(lambda rd: (True, []), sub)


# ---------------------------------------------------------------------------
# A1 — no verdict file: both steps hold, naming the file
# ---------------------------------------------------------------------------
def test_a1_missing_verdicts_hold_and_name_their_file(tmp_path):
    run = _seed_run(tmp_path)

    ok_p, reasons_p = pv.verify("P-PROMPT-QC", run)
    assert ok_p is False
    assert any(r.startswith(OPERATOR) and CASTING_REL in r for r in reasons_p), reasons_p

    ok_i, reasons_i = pv.verify("P-IMAGE-QC", run)
    assert ok_i is False
    assert any(r.startswith(OPERATOR) and GROUNDING_REL in r for r in reasons_i), reasons_i


# ---------------------------------------------------------------------------
# A2 — pass:true and a non-builder reviewer: the step passes, report untouched
# ---------------------------------------------------------------------------
def test_a2_passing_verdict_passes_and_report_bytes_unchanged(tmp_path):
    run = _seed_run(tmp_path)
    report = run / "working" / "qc" / "prompt_qc_report.json"
    before = _sha(report)

    _verdict(run, CASTING_REL, **{"pass": True, "reviewed_by": "jill-bulluck",
                                  "reviewed_at": "2026-11-12 4:40 PM Eastern",
                                  "note": "reads as the client's own audience"})

    ok, reasons = _reviewed("_verify_representation_casting")(run)
    assert ok is True, reasons
    assert reasons == []
    assert _sha(report) == before, "recording a verdict must never edit the graded report"


def test_a2_passing_grounding_verdict_passes(tmp_path):
    run = _seed_run(tmp_path)
    report = run / "working" / "qc" / "image_qc_report.json"
    before = _sha(report)
    _verdict(run, GROUNDING_REL, **{"pass": True, "reviewed_by": "coach-kaz",
                                    "reviewed_at": "2026-11-12 4:41 PM Eastern",
                                    "note": ""})
    ok, reasons = _reviewed("_verify_image_grounding")(run)
    assert ok is True, reasons
    assert _sha(report) == before


# ---------------------------------------------------------------------------
# A3 — pass:false: the step fails with the reviewer's note
# ---------------------------------------------------------------------------
def test_a3_failing_verdict_fails_with_the_note(tmp_path):
    run = _seed_run(tmp_path)
    _verdict(run, CASTING_REL, **{"pass": False, "reviewed_by": "jill-bulluck",
                                  "note": "slide 4 shows a different audience"})
    ok, reasons = _reviewed("_verify_representation_casting")(run)
    assert ok is False
    assert any("slide 4 shows a different audience" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# A4 — the old block typed inside the report, no file: the step still holds
# ---------------------------------------------------------------------------
def test_a4_report_embedded_block_is_not_a_verdict(tmp_path):
    run = _seed_run(tmp_path)
    report = run / "working" / "qc" / "prompt_qc_report.json"
    doc = json.loads(report.read_text())
    doc["representation_casting"] = {"pass": True,
                                     "reviewed_by": "representation-casting-director"}
    report.write_text(json.dumps(doc))

    ok, reasons = pv.verify("P-PROMPT-QC", run)
    assert ok is False
    assert any(r.startswith(OPERATOR) and CASTING_REL in r for r in reasons), reasons

    image = run / "working" / "qc" / "image_qc_report.json"
    idoc = json.loads(image.read_text())
    idoc["image_grounding"] = {"pass": True, "reviewed_by": "image-grounding-steward"}
    image.write_text(json.dumps(idoc))
    ok_i, reasons_i = pv.verify("P-IMAGE-QC", run)
    assert ok_i is False
    assert any(r.startswith(OPERATOR) and GROUNDING_REL in r for r in reasons_i), reasons_i


# ---------------------------------------------------------------------------
# A5 — a builder name is refused
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("builder", ["builder", "self", "build_deck", "author"])
def test_a5_builder_byline_is_refused(tmp_path, builder):
    run = _seed_run(tmp_path)
    _verdict(run, GROUNDING_REL, **{"pass": True, "reviewed_by": builder})
    ok, reasons = _reviewed("_verify_image_grounding")(run)
    assert ok is False
    assert any(repr(builder) in r for r in reasons), reasons


def test_a5_builder_byline_is_refused_on_the_casting_verdict(tmp_path):
    run = _seed_run(tmp_path)
    _verdict(run, CASTING_REL, **{"pass": True, "reviewed_by": "Builder"})
    ok, reasons = _reviewed("_verify_representation_casting")(run)
    assert ok is False
    assert any("Builder" in r for r in reasons), reasons
