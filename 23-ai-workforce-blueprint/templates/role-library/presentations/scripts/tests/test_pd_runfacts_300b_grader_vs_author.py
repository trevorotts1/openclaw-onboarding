#!/usr/bin/env python3
"""PD-300b — the grader is compared with the author, and the priority-shift
check names its items.

Two contracts, both proven in BOTH directions here (a pass row and a fail row
per rule), because a rule that only ever runs one way is a rule nobody has
tested:

  PART 1 — qc_aggregate's image check and verifier_registry's sealed verdict
           both compare `graded_by_model` (the grading route) with
           `author_model` (PD-300's field, stamped from the trusted execution
           stamps), fail when the author is absent, fail when the two are
           equal, fail when no ACTIVE author stamp covers the report at its
           current bytes, and fail when the grading model is not a vision
           model by PD-205b's registry lookup.

  PART 2 — runfacts.verify_priority_shift requires the ledger's item ids to be
           exactly PRIORITY_SHIFT_ITEM_IDS (PD-304's one list, imported not
           copied): a missing id, an extra id, a repeated id and an unnamed row
           each fail naming the id; the full set passes.

The rollback path is proven too: with PRESENTATION_EXECUTION_STAMPS=0 the
author/stamp rules must go quiet (no rows are minted under that rollback) while
the vision rule — which is not stamp-derived — still applies.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import qc_aggregate  # noqa: E402
import verifier_registry  # noqa: E402
from presentation_job import execution_stamp as _es  # noqa: E402
from presentation_job import runfacts  # noqa: E402
from presentation_job.priority_shift_items import (  # noqa: E402
    PRIORITY_SHIFT_ID_KEY,
    PRIORITY_SHIFT_ITEM_IDS,
)

AUTHOR = "deepseek-v4.1-flash"      # writes the deck
GRADER = "glm-ocr"                  # a real VISION model, different from the author
TEXT_MODEL = "deepseek-v4.1-flash"  # registry modality "text"


# --------------------------------------------------------------------------
# PART 1 — fixtures
# --------------------------------------------------------------------------
def _write(path: pathlib.Path, obj: dict) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return path


def _image_report(*, graded_model: str = GRADER,
                  author_model: str | None = AUTHOR,
                  request_id: str = "req-300b-1") -> dict:
    obj = {
        "gate": "AF-IMAGE-QC",
        "average": 9.2,
        "pass": True,
        "triggered_autofails": [],
        "qc_independence": {
            "graded_by": "qc-specialist-independent",
            "built_by": AUTHOR,
            "independent": True,
        },
        "graded_by_provider": "glm",
        "graded_by_model": graded_model,
        "request_id": request_id,
        "slides": [{"slide": n, "observed_text": f"slide {n:02d} read"}
                   for n in range(1, 5)],
    }
    if author_model is not None:
        obj["author_model"] = author_model
    return obj


def _run_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    rd = pathlib.Path(tmp_path) / "run"
    (rd / "working" / "qc").mkdir(parents=True, exist_ok=True)
    for n in range(1, 5):
        (rd / "renders").mkdir(parents=True, exist_ok=True)
        (rd / "renders" / f"slide-{n:02d}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x")
    return rd


def _stamp_author(rd: pathlib.Path, report: pathlib.Path, *,
                  model: str = AUTHOR, phase: str = "P-IMAGE-QC") -> None:
    _es.author_stamp(rd, phase, report, model=model, provider="fixture")


def _aggregate_reasons(rd: pathlib.Path, report: dict) -> list:
    _write(rd / "working" / "qc" / "image_qc_report.json", report)
    out = qc_aggregate.aggregate(rd)
    return list(out["domains"]["image"]["reasons"])


def _registry_reasons(rd: pathlib.Path, report: dict, *,
                      stamp: bool = True) -> list:
    report_path = _write(rd / "working" / "qc" / "image_qc_report.json", report)
    if stamp and _es.stamps_enabled():
        _stamp_author(rd, report_path)
    verifier_registry.reset_fix33_snapshots()
    spec = verifier_registry.qc_report_verifier("image")
    _ok, reasons = spec.run_verifier(rd)
    return list(reasons)


@pytest.mark.parametrize("which", ["aggregate", "registry"])
def test_a1_grader_equals_author_fails_naming_the_model(tmp_path, which,
                                                        monkeypatch):
    """A1: graded_by_model == author_model -> BOTH checks fail, naming it."""
    monkeypatch.delenv("PRESENTATION_EXECUTION_STAMPS", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_VISION_CONTRACT", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_REGISTRY_CONTRACT", raising=False)
    rd = _run_dir(tmp_path)
    report = _image_report(graded_model=AUTHOR, author_model=AUTHOR)
    reasons = (_aggregate_reasons if which == "aggregate"
               else _registry_reasons)(rd, report)
    joined = " | ".join(reasons)
    assert reasons, f"{which}: self-graded report must fail"
    assert "equals author_model" in joined or "equals the report's authoring" in joined, joined
    assert AUTHOR in joined, f"{which} must name the model: {joined}"


@pytest.mark.parametrize("which", ["aggregate", "registry"])
def test_a2_author_model_absent_fails(tmp_path, which, monkeypatch):
    """A2: no author_model -> BOTH checks fail."""
    monkeypatch.delenv("PRESENTATION_EXECUTION_STAMPS", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_VISION_CONTRACT", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_REGISTRY_CONTRACT", raising=False)
    rd = _run_dir(tmp_path)
    report = _image_report(author_model=None)
    reasons = (_aggregate_reasons if which == "aggregate"
               else _registry_reasons)(rd, report)
    joined = " | ".join(reasons)
    assert reasons, f"{which}: a report with no author_model must fail"
    assert "no author_model" in joined, joined


@pytest.mark.parametrize("which", ["aggregate", "registry"])
def test_a3_different_models_with_matching_stamp_rows_pass(tmp_path, which,
                                                           monkeypatch):
    """A3: grader != author, a vision grader, and an active author stamp for
    the report's CURRENT bytes -> BOTH checks pass on the author/stamp rules."""
    monkeypatch.delenv("PRESENTATION_EXECUTION_STAMPS", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_VISION_CONTRACT", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_REGISTRY_CONTRACT", raising=False)
    rd = _run_dir(tmp_path)
    report = _image_report()
    if which == "aggregate":
        report_path = _write(rd / "working" / "qc" / "image_qc_report.json", report)
        _stamp_author(rd, report_path)
        reasons = qc_aggregate.aggregate(rd)["domains"]["image"]["reasons"]
    else:
        reasons = _registry_reasons(rd, report)
    joined = " | ".join(reasons)
    for bad in ("no author_model", "equals author_model",
                "equals the report's authoring", "no ACTIVE author stamp",
                "not a vision model"):
        assert bad not in joined, f"{which}: honest control hit {bad!r}: {joined}"


@pytest.mark.parametrize("which", ["aggregate", "registry"])
def test_report_changed_after_stamp_fails(tmp_path, which, monkeypatch):
    """The stamp-row rule: stamping the report then MUTATING it orphans the
    row, so who wrote the current bytes is unproven -> fails."""
    monkeypatch.delenv("PRESENTATION_EXECUTION_STAMPS", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_VISION_CONTRACT", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_REGISTRY_CONTRACT", raising=False)
    rd = _run_dir(tmp_path)
    report = _image_report()
    report_path = _write(rd / "working" / "qc" / "image_qc_report.json", report)
    _stamp_author(rd, report_path)
    # A repair: same shape, different bytes, no new stamp.
    mutated = dict(report)
    mutated["average"] = 9.3
    _write(report_path, mutated)
    if which == "aggregate":
        reasons = qc_aggregate.aggregate(rd)["domains"]["image"]["reasons"]
    else:
        # The row was minted for the ORIGINAL bytes; do not re-stamp here.
        reasons = _registry_reasons(rd, mutated, stamp=False)
    joined = " | ".join(reasons)
    assert "no ACTIVE author stamp" in joined, joined


@pytest.mark.parametrize("which", ["aggregate", "registry"])
def test_non_vision_grader_fails(tmp_path, which, monkeypatch):
    """The vision rule: a TEXT model grading the image range fails, naming it.
    Not stamp-derived, so it holds under the stamps rollback too."""
    monkeypatch.setenv("PRESENTATION_EXECUTION_STAMPS", "0")
    monkeypatch.delenv("PRESENTATION_FIX33_VISION_CONTRACT", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_REGISTRY_CONTRACT", raising=False)
    rd = _run_dir(tmp_path)
    report = _image_report(graded_model=TEXT_MODEL, author_model="some-other-model")
    reasons = (_aggregate_reasons if which == "aggregate"
               else _registry_reasons)(rd, report)
    joined = " | ".join(reasons)
    # Under the rollback the report carries no stamp at all, so the aggregate
    # judges the vision rule only where the report DID claim a vision unit.
    assert "not a vision model" in joined, joined
    assert TEXT_MODEL in joined, joined


@pytest.mark.parametrize("which", ["aggregate", "registry"])
def test_stamps_rollback_silences_author_rules(tmp_path, which, monkeypatch):
    """PRESENTATION_EXECUTION_STAMPS=0 mints no rows; the author/stamp rules
    must not fire, so a documented rollback is not turned into a hard fail."""
    monkeypatch.setenv("PRESENTATION_EXECUTION_STAMPS", "0")
    monkeypatch.delenv("PRESENTATION_FIX33_VISION_CONTRACT", raising=False)
    monkeypatch.delenv("PRESENTATION_FIX33_REGISTRY_CONTRACT", raising=False)
    rd = _run_dir(tmp_path)
    report = _image_report(author_model=None)
    reasons = (_aggregate_reasons if which == "aggregate"
               else _registry_reasons)(rd, report)
    joined = " | ".join(reasons)
    assert "no author_model" not in joined, joined
    assert "no ACTIVE author stamp" not in joined, joined


# --------------------------------------------------------------------------
# PART 2 — priority shift ids
# --------------------------------------------------------------------------
def _ps_report(ids, *, passes=True) -> dict:
    return {
        "schema": "priority_shift_report/v1",
        "gate": "AF-PRIORITY-SHIFT",
        "pass": True,
        "items": [{"item": i, "pass": passes, "evidence": "ok"} for i in ids],
    }


def _ps_verdict(tmp_path: pathlib.Path, report: dict):
    rd = pathlib.Path(tmp_path) / "ps"
    (rd / "working" / "qc").mkdir(parents=True, exist_ok=True)
    _write(rd / "working" / "qc" / "priority_shift_report.json", report)
    facts = runfacts.seal(rd, nonce_bound=False, force=True)
    return runfacts.verify_priority_shift(facts)


def test_a4_missing_id_fails_naming_it(tmp_path):
    """A4: a ledger missing one id fails, and the reason NAMES that id."""
    ids = list(PRIORITY_SHIFT_ITEM_IDS)
    dropped = ids.pop(7)
    verdict, detail = _ps_verdict(tmp_path, _ps_report(ids))
    assert verdict is runfacts.Verdict.FAIL
    assert dropped in detail, detail
    assert "missing ship-gate item ids" in detail, detail


def test_a5_extra_id_and_repeated_id_fail_naming_it(tmp_path):
    """A5: one extra id fails naming it; one id twice fails naming it."""
    ids = list(PRIORITY_SHIFT_ITEM_IDS)
    verdict, detail = _ps_verdict(
        tmp_path, _ps_report(ids + ["99_not_a_ship_gate_item"]))
    assert verdict is runfacts.Verdict.FAIL
    assert "99_not_a_ship_gate_item" in detail, detail
    assert "does not define" in detail, detail

    other = pathlib.Path(tmp_path) / "dup"
    other.mkdir()
    verdict2, detail2 = _ps_verdict(other, _ps_report(ids + [ids[3]]))
    assert verdict2 is runfacts.Verdict.FAIL
    assert ids[3] in detail2, detail2
    assert "repeats ship-gate item ids" in detail2, detail2


def test_unnamed_row_fails(tmp_path):
    """A row with no id at all cannot be attributed to a ship-gate item."""
    ids = list(PRIORITY_SHIFT_ITEM_IDS)
    report = _ps_report(ids)
    report["items"][0].pop(PRIORITY_SHIFT_ID_KEY)
    verdict, detail = _ps_verdict(tmp_path, report)
    assert verdict is runfacts.Verdict.FAIL
    assert "carry no" in detail and PRIORITY_SHIFT_ID_KEY in detail, detail


def test_a6_full_set_all_passing_passes(tmp_path):
    """A6: exactly the ship gate's id set, each once, all pass:true -> PASS."""
    verdict, detail = _ps_verdict(tmp_path, _ps_report(list(PRIORITY_SHIFT_ITEM_IDS)))
    assert verdict is runfacts.Verdict.PASS, detail
    assert len(PRIORITY_SHIFT_ITEM_IDS) == 15, "ship gate is fifteen items"


def test_id_rule_runs_before_the_pass_rule(tmp_path):
    """A row that is BOTH failing and unnamed: the id problem is named too, so
    an incomplete ledger is never reported as merely a failing row."""
    ids = list(PRIORITY_SHIFT_ITEM_IDS)[1:]
    report = _ps_report(ids, passes=False)
    verdict, detail = _ps_verdict(tmp_path, report)
    assert verdict is runfacts.Verdict.FAIL
    assert "missing ship-gate item ids" in detail, detail
    assert "ledger items failing" in detail, detail
