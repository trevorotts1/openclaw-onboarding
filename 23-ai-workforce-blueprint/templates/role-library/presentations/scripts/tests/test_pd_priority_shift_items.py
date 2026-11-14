"""PD-304: the priority-shift contract matches the check that grades it.

The finding: P-SHIFT-QC had no entry in `dispatcher.ARTIFACT_CONTRACTS`, so the
grading model was handed the generic "write a substantive JSON file" contract
while `presentation_job.runfacts.verify_priority_shift` (reached through
`PHASE_VERIFIERS["P-SHIFT-QC"]`) grades the ledger against an exact schema, a
literal top-level `pass: true`, and item rows that each carry `pass: true`. A
model that is never told the shape cannot converge on it.

Two independent things are proved here, both against the real modules:

  * A4 (parity) -- `presentation_job.priority_shift_items.PRIORITY_SHIFT_ITEM_IDS`
    is exactly the id list, in order, that `build_deck._chk_priority_shift_ledger`
    writes into `working/qc/priority_shift_report.json`. Until PD-097 makes the
    writer import the tuple, this is what keeps the two copies equal; after it,
    the same assertion proves the import still matches the file the gate reads.
  * A1 / A3 (the contract is satisfiable and still has teeth) -- a report built in
    the shape `ARTIFACT_CONTRACTS["P-SHIFT-QC"]` states passes the step check, and
    the same report with ONE row marked `pass: false` fails naming that id.

Nothing here calls a model, the network, or any live service: the "stubbed model
answer" is the JSON this file writes into a temporary run dir.

Flat file inside tests/, manages its own import path -- matching every sibling in
this directory.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck  # noqa: E402
import phase_verifiers as pv  # noqa: E402
from presentation_job import dispatcher  # noqa: E402
from presentation_job import priority_shift_items as psi  # noqa: E402

REPORT_REL = ("working", "qc", "priority_shift_report.json")


def _spec() -> dict:
    """The minimum priority_shift_spec.json that makes the doctrine active."""
    return {
        "true_goal": "make the audience see the cost of standing still",
        "priority_stack": ["attention", "belief", "action"],
        "higher_priority_hook": "the quiet cost nobody invoices",
        "the_one_promise": "one deck that sells the shift",
        "the_one_wow": "the before/after snapshot",
        "the_one_demonstration": "the ninety-second walkthrough",
    }


def _run_dir(tmp_path: Path) -> Path:
    """A run dir the report writer can actually fire on: doctrine active (a valid
    spec), copy present, and one rendered slide so the gate is not pre-render."""
    run = tmp_path / "run"
    (run / "working" / "copy").mkdir(parents=True)
    (run / "renders").mkdir(parents=True)
    (run / "working" / "copy" / "priority_shift_spec.json").write_text(
        json.dumps(_spec()), encoding="utf-8")
    (run / "working" / "copy" / "slides_copy.md").write_text(
        "# SLIDE 1\n"
        "HEADLINE: attention is the product\n"
        "<!-- ARC: PRIORITY_STACK --><!-- ARC: PRESENT_COST -->"
        "<!-- ARC: HIGHER_PRIORITY --><!-- ARC: VALUE_ANCHOR -->\n",
        encoding="utf-8")
    (run / "renders" / "slide-01.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    return run


def _contract_report() -> dict:
    """A stubbed answer written exactly as ARTIFACT_CONTRACTS["P-SHIFT-QC"] says."""
    return {
        "schema": "priority_shift_report/v1",
        "pass": True,
        "items": [
            {
                psi.PRIORITY_SHIFT_ID_KEY: item_id,
                "pass": True,
                "evidence": f"quoted deck text for {item_id}",
            }
            for item_id in psi.PRIORITY_SHIFT_ITEM_IDS
        ],
    }


def _write_report(run: Path, report: dict) -> Path:
    path = run.joinpath(*REPORT_REL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# A4 -- parity between the shared tuple and the real writer.
# ---------------------------------------------------------------------------
def test_writer_writes_exactly_the_declared_ids_in_order(tmp_path):
    run = _run_dir(tmp_path)
    build_deck._chk_priority_shift_ledger(run)

    report = json.loads(run.joinpath(*REPORT_REL).read_text(encoding="utf-8"))
    written = [row[psi.PRIORITY_SHIFT_ID_KEY] for row in report["items"]]
    assert written == list(psi.PRIORITY_SHIFT_ITEM_IDS), (
        "priority_shift_items.PRIORITY_SHIFT_ITEM_IDS no longer equals the ids "
        "build_deck._chk_priority_shift_ledger writes -- the P-SHIFT-QC contract "
        "and the step check would grade different checklists")


def test_report_key_is_the_writers_own_row_key(tmp_path):
    """The contract's id key must be the key the writer emits, not a synonym."""
    run = _run_dir(tmp_path)
    build_deck._chk_priority_shift_ledger(run)

    report = json.loads(run.joinpath(*REPORT_REL).read_text(encoding="utf-8"))
    first = report["items"][0]
    assert psi.PRIORITY_SHIFT_ID_KEY in first
    assert first["pass"] is True
    assert isinstance(first.get("evidence"), str) and first["evidence"]


# ---------------------------------------------------------------------------
# A1 / A3 -- the stated contract is satisfiable, and a failing row still fails.
# ---------------------------------------------------------------------------
def test_contract_names_every_id_the_check_requires():
    text = dispatcher.ARTIFACT_CONTRACTS["P-SHIFT-QC"]
    assert "working/qc/priority_shift_report.json" in text
    assert "priority_shift_report/v1" in text
    assert psi.PRIORITY_SHIFT_ID_KEY in text
    for item_id in psi.PRIORITY_SHIFT_ITEM_IDS:
        assert item_id in text, f"the contract never states item id {item_id!r}"
    assert "correct output" in text, (
        "the contract must say a failing row is a correct output -- otherwise it "
        "only teaches the grader how to rubber-stamp")


def test_contract_shaped_report_passes_the_step_check(tmp_path):
    run = _run_dir(tmp_path)
    _write_report(run, _contract_report())

    ok, reasons = pv.PHASE_VERIFIERS["P-SHIFT-QC"](run)
    assert ok, reasons


def test_one_failing_row_fails_the_step_naming_that_id(tmp_path):
    run = _run_dir(tmp_path)
    report = _contract_report()
    failing_id = psi.PRIORITY_SHIFT_ITEM_IDS[4]
    report["items"][4]["pass"] = False
    # The top-level flag deliberately stays true: a ledger whose rows contradict
    # its own pass flag is exactly the rubber stamp the check exists to reject,
    # and it must be rejected by NAMING the failing item.
    _write_report(run, report)

    ok, reasons = pv.PHASE_VERIFIERS["P-SHIFT-QC"](run)
    assert not ok
    joined = " ".join(reasons)
    assert failing_id in joined, joined
