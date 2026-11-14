"""PD-111 — a QC report is not rejected for words in a reviewer's note.

Acceptance rows A1, A2, A3 (01-BUILD-SPEC.md, section PD-111).

THE DEFECT

`_qc_report_substance_problems` serialised the WHOLE report to JSON and matched
each entry of `QC_FOREIGN_SIGNATURES` against that blob. The signatures include
prose phrases ("overlay the headline", "applied in post", "word-count rubric"),
so any report whose reviewer note, reason, finding or fix DISCUSSED those words
was rejected as a foreign/generated artifact. A reviewer writing "do not overlay
the headline; re-prompt the copywriter instead" — a correct instruction — could
not pass a QC gate at all.

THE RULE

A signature may match only
  * a KEY NAME at any depth, or
  * the string value of the top-level `generator` field.
Free-text values (notes, reasons, findings, fixes) are never matched.

WHAT THESE TESTS PIN

A1 — a report whose note says "do not overlay the headline; re-prompt" passes.
A2 — a report with a key named `overlay_readiness` is still rejected.
A3 — a report with `"generator": "post-production overlay tool"` is still rejected.

A1 carries its own discriminator: it asserts the prose IS present in the
whole-blob JSON, so the old implementation provably rejected this report and a
regression back to blob matching fails here rather than passing quietly.

No network, no paid service: fixture JSON in a tmp dir only.
"""
from __future__ import annotations

import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402

GATE = "AF-PROMPT-QC"
SOP = "qc-specialist-presentations-sops.md"

# The exact note row A1 names. It contains the signature "overlay the headline".
REVIEWER_NOTE = "Do not overlay the headline; re-prompt the copywriter instead."

# A note carrying no signature, so the "still rejected" rows can prove the key /
# generator match alone rejected the report rather than tripping over prose.
CLEAN_NOTE = "Graded against the prompt SOP; two rewrite suggestions attached."


def _report(**over):
    obj = {
        "gate": GATE,
        "average": 9.1,
        "pass": True,
        "reviewer": "independent-qc-specialist",
        "criteria": [{"name": "hook", "score": 9.0}, {"name": "arc", "score": 9.2}],
        "notes": REVIEWER_NOTE,
    }
    obj.update(over)
    return obj


def _gate(tmp_path, obj):
    """Run the REAL gate the engine runs, not just the helper."""
    p = tmp_path / "prompt_qc_report.json"
    p.write_text(json.dumps(obj), encoding="utf-8")
    return bd._qc_report_gate(p, GATE, GATE, SOP)


def test_a1_reviewer_note_prose_is_not_a_foreign_signature(tmp_path):
    # The discriminator: the phrase really is in the blob, so the old
    # whole-blob match rejected this report. Prove that before asserting the fix.
    report = _report()
    assert "overlay the headline" in json.dumps(report).lower(), (
        "fixture drifted: A1 must exercise the exact signature the old blob match "
        "rejected")

    assert bd._qc_report_substance_problems(report) == []
    assert _gate(tmp_path, report) == ""


def test_a1_free_text_at_depth_is_also_ignored(tmp_path):
    # findings/reasons/fixes hang off nested blocks; none of them may be matched.
    report = _report(
        sections={
            "findings": [{"text": "the copy was applied in post, which is wrong"}],
            "fixes": [{"reason": "the typography_overlay_readiness criterion is a trap"}],
        })
    assert bd._qc_report_substance_problems(report) == []
    assert _gate(tmp_path, report) == ""


def test_a2_key_named_overlay_readiness_is_still_rejected(tmp_path):
    report = _report(notes=CLEAN_NOTE,
                     overlay_readiness="text baked into the image, not overlaid")
    problems = bd._qc_report_substance_problems(report)
    assert problems and "overlay_readiness" in problems[0]

    msg = _gate(tmp_path, report)
    assert msg.startswith(f"{GATE}:")
    assert "overlay_readiness" in msg


def test_a2b_nested_key_name_is_still_rejected(tmp_path):
    # Depth does not launder a key: a nested rubric field is still a key.
    report = _report(notes=CLEAN_NOTE,
                     meta={"rubric": {"typography_overlay_readiness": "checked"}})
    problems = bd._qc_report_substance_problems(report)
    assert problems and "typography_overlay_readiness" in problems[0]


def test_a3_generator_field_is_still_rejected(tmp_path):
    report = _report(notes=CLEAN_NOTE, generator="post-production overlay tool")
    problems = bd._qc_report_substance_problems(report)
    assert problems and "post-production overlay" in problems[0]

    msg = _gate(tmp_path, report)
    assert msg.startswith(f"{GATE}:")
    assert "foreign QC-generator signature" in msg


def test_a3b_generator_is_matched_case_insensitively(tmp_path):
    report = _report(notes=CLEAN_NOTE, generator="Post-Production Overlay Tool")
    assert bd._qc_report_substance_problems(report)
