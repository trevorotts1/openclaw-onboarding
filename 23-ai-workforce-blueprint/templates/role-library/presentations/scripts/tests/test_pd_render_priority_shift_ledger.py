"""PD-097 — the priority-shift ledger stops inventing per-slide verdicts and never
overwrites the step's own report.

Acceptance row A1 (01-BUILD-SPEC section PD-097) plus the binding amendment (d):
  * a doctrine-active scratch run with renders writes a report with 15 item rows
    (one per id in presentation_job/priority_shift_items.PRIORITY_SHIFT_ITEM_IDS)
    and NO slide rows, and the QC report-substance per-slide floor does not reject
    it for too few per-slide verdicts;
  * the file this function writes passes runfacts.verify_priority_shift when every
    item passes, and fails it (naming the item) when one item fails;
  * a report that already carries schema priority_shift_report/v1 is validated and
    never overwritten — the agent's report survives a retry/resume byte-for-byte,
    and a report that does not match the one shape is named, not clobbered.

No network, no paid service: fixture files in a tmp run dir only.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402
from presentation_job import runfacts as rf  # noqa: E402
from presentation_job.priority_shift_items import (  # noqa: E402
    PRIORITY_SHIFT_ID_KEY, PRIORITY_SHIFT_ITEM_IDS)
from presentation_job.runfacts import Verdict  # noqa: E402
from verifier_registry import write_fixture  # noqa: E402

REPORT_REL = "working/qc/priority_shift_report.json"
PER_SLIDE_NOTE = "not applicable — 14-item deck-level checklist"

CLEAN_SPEC = {
    "true_goal": "make the offer the audience's new #1 priority",
    "priority_stack": ["incumbent", "status quo"],
    "higher_priority_hook": "the cost of waiting outranks every line item",
    "the_one_promise": "double your qualified pipeline in eight weeks",
    "the_one_wow": "a stalled funnel rebuilt live on stage",
    "the_one_demonstration": "the three-move rebuild performed in real time",
}

CLEAN_COPY = (
    "# doctrine-clean pitch deck\n"
    "PRIORITY_STACK. what matters most to you — your current priority stack.\n"
    "PRESENT_COST. the cost of inaction is the cost of doing nothing.\n"
    "HIGHER_PRIORITY. one higher priority outranks the rest.\n"
    "VALUE_ANCHOR. the value anchor: worth far more than the price.\n"
    "URGENCY_SCARCITY. limited, with a hard deadline.\n"
    "ABILITY_UNBLOCK. a payment plan and a full guarantee make it easy to start.\n"
    "RERANK_DEMAND. make this your #1. Decide now — move this to the top.\n"
    "TRIGGER. act now — the deadline is by midnight tonight; enroll now.\n")

ARC = [{"slide": 1, "arc_section": "hook"},
       {"slide": 2, "arc_section": "apex", "beat": "promise-apex"},
       {"slide": 3, "arc_section": "recap"}]


def _png(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\xcc" * (bd.PLACEHOLDER_MIN_BYTES + 500))


def _flatfill_apex_vivid(path: pathlib.Path):
    """slide-02 (the apex) is the most vivid; every other slide is flat."""
    if "slide-02" in path.name:
        return (0.05, (100, 50, 200))
    return (0.50, (150, 100, 100))


@pytest.fixture()
def clean_run(tmp_path):
    rd = tmp_path / "run"
    write_fixture(rd, "working/copy/priority_shift_spec.json", CLEAN_SPEC)
    write_fixture(rd, "working/copy/intake.json",
                  {"pitch_included": True, "creation_mode": "from_scratch"})
    write_fixture(rd, "working/copy/slides_copy.md", CLEAN_COPY)
    write_fixture(rd, "working/copy/arc_allocation.json", ARC)
    for i in range(1, 4):
        _png(rd / "renders" / f"slide-{i:02d}.png")
    # A 34-slide deck: before PD-097 the per-slide floor was max(8, min(20, 34)) = 20,
    # so a 15-row deck-level checklist could never clear check_qc_phase_report_real.
    write_fixture(rd, "working/copy/slides.json",
                  [{"slide": i} for i in range(1, 35)])
    rf.reset_cache_for_tests()
    return rd


def test_a1_report_is_15_deck_level_rows_and_clears_the_substance_floor(
        clean_run, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        reason = bd._chk_priority_shift_ledger(clean_run)
    assert reason == "", reason

    report_path = clean_run / REPORT_REL
    obj = json.loads(report_path.read_text())
    assert obj["schema"] == "priority_shift_report/v1"
    assert obj["gate"] == "AF-PRIORITY-SHIFT"
    assert obj["pass"] is True
    # 15 rows, one per id from the ONE list, in its order — none missing, extra, twice.
    assert [r[PRIORITY_SHIFT_ID_KEY] for r in obj["items"]] == list(PRIORITY_SHIFT_ITEM_IDS)
    assert len(obj["items"]) == 15
    # No invented per-slide verdict rows; the note says so instead.
    assert "slides" not in obj
    assert obj["per_slide"] == PER_SLIDE_NOTE

    # The report-substance floor does not apply to this gate (0), so the 34-slide
    # deck's old floor of 20 no longer rejects the 15-row checklist.
    assert bd._qc_slide_floor(clean_run, report_obj=obj) == 0
    assert bd.check_qc_phase_report_real(clean_run, "P-SHIFT-QC") == ""


def test_a1_written_file_passes_verify_priority_shift(clean_run, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        assert bd._chk_priority_shift_ledger(clean_run) == ""
    rf.reset_cache_for_tests()
    verdict, detail = rf.verify_priority_shift(rf.get_or_seal(clean_run))
    assert verdict is Verdict.PASS, detail
    assert "15 item rows passing" in detail


def test_a1_one_failing_item_fails_verify_priority_shift(clean_run, monkeypatch):
    # Drop the higher_priority_hook: item 5 (ITEM[5]) has no anchor left to pass on.
    spec = dict(CLEAN_SPEC)
    spec.pop("higher_priority_hook")
    write_fixture(clean_run, "working/copy/priority_shift_spec.json", spec)
    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        reason = bd._chk_priority_shift_ledger(clean_run)
    assert "AF-PRIORITY-SHIFT" in reason

    obj = json.loads((clean_run / REPORT_REL).read_text())
    assert obj["pass"] is False
    row = {r[PRIORITY_SHIFT_ID_KEY]: r for r in obj["items"]}[PRIORITY_SHIFT_ITEM_IDS[5]]
    assert row["pass"] is False

    rf.reset_cache_for_tests()
    verdict, detail = rf.verify_priority_shift(rf.get_or_seal(clean_run))
    assert verdict is Verdict.FAIL, detail
    assert PRIORITY_SHIFT_ITEM_IDS[5] in detail


def test_a1_existing_agent_report_is_never_overwritten(clean_run, monkeypatch):
    agent_report = {
        "schema": "priority_shift_report/v1",
        "pass": True,
        "items": [{PRIORITY_SHIFT_ID_KEY: i, "pass": True,
                   "evidence": "agent note for " + i} for i in PRIORITY_SHIFT_ITEM_IDS],
        "notes": "written by the P-SHIFT-QC agent, not by build_deck",
    }
    write_fixture(clean_run, REPORT_REL, agent_report)
    before = (clean_run / REPORT_REL).read_bytes()

    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        reason = bd._chk_priority_shift_ledger(clean_run)
    assert reason == "", reason
    # Two writers, one file: the report that already carries the schema is untouched.
    assert (clean_run / REPORT_REL).read_bytes() == before


def test_a1_invalid_existing_report_is_named_not_overwritten(clean_run, monkeypatch):
    truncated = {
        "schema": "priority_shift_report/v1",
        "pass": True,
        "items": [{PRIORITY_SHIFT_ID_KEY: i, "pass": True}
                  for i in PRIORITY_SHIFT_ITEM_IDS[:-1]],
    }
    write_fixture(clean_run, REPORT_REL, truncated)
    before = (clean_run / REPORT_REL).read_bytes()

    with monkeypatch.context() as m:
        m.setattr(bd, "_png_flatfill_fraction", _flatfill_apex_vivid)
        reason = bd._chk_priority_shift_ledger(clean_run)
    assert "AF-PRIORITY-SHIFT" in reason
    assert "missing ids" in reason
    assert PRIORITY_SHIFT_ITEM_IDS[-1] in reason
    assert (clean_run / REPORT_REL).read_bytes() == before
