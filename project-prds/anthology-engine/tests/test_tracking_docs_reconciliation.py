#!/usr/bin/env python3
"""test_tracking_docs_reconciliation.py -- GK-18/U80 regression suite.

WHY THIS SUITE EXISTS: GK-18/U80 found `project-prds/anthology-engine/CHECKLIST.md`,
`SESSION-LOG.md`, and `CHANGE-LOG.md` silently stale against the shipped
`59-anthology-engine/` engine code for 62 commits (2026-07-07 through 2026-07-16) --
the exact class of drift these tests exist to catch the NEXT time it starts, not
just to describe the one time it already happened.

Two kinds of test live here, and they are NOT interchangeable:

1. STRUCTURAL INVARIANTS (must hold forever): every CHECKLIST.md checkbox row
   carries a recognized status annotation (no more bare, unannotated boxes);
   SESSION-LOG.md and CHANGE-LOG.md stay byte-for-byte append-only versus their
   pre-reconciliation content (their own binding contract); the GK-18/U80 tally
   line's arithmetic matches what is actually written in the file (this exact bug
   existed in this suite's own first draft and was caught by re-deriving the count,
   not by trusting the prose -- the fix-first-draft is the proof this test is not
   tautological).

2. NAMED-CLAIM SNAPSHOTS (must hold until a NAMED future unit changes them): a
   handful of tests pin the specific, dated facts this reconciliation pass found
   and wrote into CHECKLIST.md (the 56-shipped-.py-file count; `anthology_book.py`
   missing from ENGINE-MANIFEST.json's own inventory; 5 of the 6 named SOPs
   present). These are drift detectors, not celebrations of the gap: if one of
   them starts failing, it means the underlying reality moved and CHECKLIST.md's
   matching row is now the thing that is stale -- go re-run GK-18/U80's own method
   (read the file, run the shipped provers, update the row with a fresh RECONCILED
   annotation) rather than deleting the test. A snapshot test flipping from PASS
   to FAIL is this suite doing its job, not this suite being broken.

Hermetic except where explicitly noted: reads files and runs `git show` against
the local repo only; no network, no live credential, no live box, no secret value
ever printed (the one known hardcoded-secret finding is asserted by VARIABLE NAME
and LINE NUMBER only, never by reading or printing its value).

Run: python3 -m pytest project-prds/anthology-engine/tests/test_tracking_docs_reconciliation.py -q
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PRD_DIR = REPO_ROOT / "project-prds" / "anthology-engine"
ENGINE_DIR = REPO_ROOT / "59-anthology-engine"

CHECKLIST = PRD_DIR / "CHECKLIST.md"
SESSION_LOG = PRD_DIR / "SESSION-LOG.md"
CHANGE_LOG = PRD_DIR / "CHANGE-LOG.md"
MANIFEST = ENGINE_DIR / "ENGINE-MANIFEST.json"

# The merge-base this branch was cut from (skill6-v2/U80 off origin/main). Used as
# the append-only baseline: SESSION-LOG.md and CHANGE-LOG.md as they stood at this
# commit MUST remain an exact byte-prefix of the current file.
BASELINE_COMMIT = "85996770cb8301279b2bd499b96d2476becac70e"

# The recognized status tags every checkbox row must carry after GK-18/U80. A row
# missing all four means it fell back to the pre-reconciliation bare-box state this
# suite exists to prevent.
STATUS_TAGS = (
    "RECONCILED GK-18/U80",
    "RUNTIME ATTESTATION",
    "NOT BUILT — LIVE PROOF OWED",
    "NOT BUILT — GAP",
)

CHECKBOX_LINE = re.compile(r"^(?:-\s\[[ xX]\]|\d+\.\s\[[ xX]\])")


def _git_show(path_from_root: str, commit: str = BASELINE_COMMIT) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path_from_root}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _checklist_lines():
    return CHECKLIST.read_text().splitlines()


def _checkbox_lines():
    return [l for l in _checklist_lines() if CHECKBOX_LINE.match(l)]


# ---------------------------------------------------------------------------
# 1. STRUCTURAL INVARIANTS
# ---------------------------------------------------------------------------


def test_checklist_has_the_expected_53_checkbox_rows():
    """Fail-first proof this pattern is meaningful: 27 Part A + 26 Part C = 53,
    matching the file's own '(26 numbered items...)' / per-participant header
    counts. A count drifting away from 53 means a row was added or deleted
    without anyone re-running the reconciliation math below."""
    rows = _checkbox_lines()
    assert len(rows) == 53, (
        f"expected 53 checkbox rows (27 Part A + 26 Part C), found {len(rows)} -- "
        "a row was added or removed; re-run the GK-18/U80 tally before trusting "
        "CHECKLIST.md again"
    )


def test_every_checkbox_row_carries_a_recognized_status_tag():
    """The core structural invariant: no bare, unannotated checkbox rows. This is
    the exact defect GK-18/U80 fixed (53/53 rows previously carried nothing but
    the original PRD prose); a row missing every tag below is a regression back
    to that state."""
    unannotated = []
    for line in _checkbox_lines():
        if not any(tag in line for tag in STATUS_TAGS):
            unannotated.append(line[:90])
    assert not unannotated, (
        "checkbox row(s) missing a recognized GK-18/U80 status tag "
        f"{STATUS_TAGS}:\n" + "\n".join(unannotated)
    )


def test_session_log_is_append_only_since_the_u80_baseline():
    """SESSION-LOG.md's own contract: 'APPEND-ONLY. Never edit or delete a prior
    entry.' Structural proof, not a promise: the file as it stood at this
    branch's merge-base must remain an EXACT byte-prefix of the current file."""
    baseline = _git_show("project-prds/anthology-engine/SESSION-LOG.md")
    current = SESSION_LOG.read_text()
    assert current.startswith(baseline), (
        "SESSION-LOG.md is no longer a byte-for-byte superset of its "
        f"{BASELINE_COMMIT[:8]} baseline -- append-only was violated"
    )
    assert len(current) > len(baseline), (
        "SESSION-LOG.md is unchanged since the baseline -- GK-18/U80's own "
        "reconciliation entry did not get appended"
    )


def test_change_log_is_append_only_since_the_u80_baseline():
    """Same append-only proof as above, for CHANGE-LOG.md's 'Rows are NEVER
    edited or deleted; corrections are new rows' contract."""
    baseline = _git_show("project-prds/anthology-engine/CHANGE-LOG.md")
    current = CHANGE_LOG.read_text()
    assert current.startswith(baseline), (
        "CHANGE-LOG.md is no longer a byte-for-byte superset of its "
        f"{BASELINE_COMMIT[:8]} baseline -- append-only was violated"
    )
    assert len(current) > len(baseline), (
        "CHANGE-LOG.md is unchanged since the baseline -- GK-18/U80's own "
        "Section 3 rows did not get appended"
    )


def test_checklist_tally_arithmetic_matches_the_actual_row_tags():
    """Fail-first proof (this exact bug existed in this suite's own first
    reconciliation draft, caught by this re-derivation, not by re-reading the
    prose): re-count the Part C rows by tag independently of the closing tally
    paragraph's own arithmetic, and assert they agree with each other AND sum to
    26."""
    lines = _checklist_lines()
    part_c_start = next(
        i for i, l in enumerate(lines) if l.startswith("## PART C:")
    )
    part_c_end = next(
        i for i, l in enumerate(lines) if l.startswith("END OF CHECKLIST.")
    )
    part_c_rows = [
        l for l in lines[part_c_start:part_c_end] if re.match(r"^\d+\.\s\[[ xX]\]", l)
    ]
    assert len(part_c_rows) == 26

    reconciled = sum(1 for l in part_c_rows if "RECONCILED GK-18/U80" in l)
    live_owed = sum(1 for l in part_c_rows if "NOT BUILT — LIVE PROOF OWED" in l)
    gap = sum(1 for l in part_c_rows if "NOT BUILT — GAP" in l)

    assert reconciled + live_owed + gap == 26, (
        f"tagged rows ({reconciled} + {live_owed} + {gap} = "
        f"{reconciled + live_owed + gap}) do not sum to the 26 Part C items -- "
        "a row is tagged with more than one status, or fewer than one"
    )

    tally_line = next(l for l in lines if l.startswith("**GK-18/U80 tally"))
    numbers = re.findall(r"(\d+) of 26", tally_line)
    assert numbers == [str(reconciled), str(live_owed), str(gap)], (
        f"the tally paragraph claims {numbers} but the rows themselves tag "
        f"{[reconciled, live_owed, gap]} -- the prose and the data disagree"
    )

    ticked = sum(1 for l in part_c_rows if re.match(r"^\d+\.\s\[[xX]\]", l))
    assert ticked == reconciled, (
        f"{ticked} row(s) show a literal [x] but {reconciled} carry the "
        "RECONCILED tag -- a box was ticked without the matching evidence tag, "
        "or vice versa"
    )


# ---------------------------------------------------------------------------
# 2. NAMED-CLAIM SNAPSHOTS -- see the module docstring before touching these
# ---------------------------------------------------------------------------


def test_shipped_python_file_count_matches_the_documented_57():
    """CHECKLIST.md's reconciliation note states 57 shipped Python files in
    59-anthology-engine/. If this count moves, the note is now stale -- update
    CHECKLIST.md's reconciliation note (and this literal) together, in the same
    commit, the way GK-18/U80 itself would.

    Moved 56 -> 57 in the merge-train commit that landed GK-17/U79 immediately
    before this unit: U79 added tests/test_a7_selfheal_reconcile.py, a new .py
    file under 59-anthology-engine/. Updated here + in CHECKLIST.md together,
    in the same commit, per this docstring's own instruction."""
    py_files = [p for p in ENGINE_DIR.rglob("*.py") if "__pycache__" not in p.parts]
    assert len(py_files) == 57, (
        f"59-anthology-engine/ now ships {len(py_files)} .py files, not the 57 "
        "CHECKLIST.md's reconciliation note documents -- update the note"
    )
    assert "57 shipped Python files" in CHECKLIST.read_text()


def test_anthology_book_py_gap_is_still_accurately_documented():
    """Named claim (CHECKLIST.md item 19): scripts/anthology_book.py ships on
    disk but is absent from ENGINE-MANIFEST.json's own script_inventory. This
    test locks in that GAP as GK-18/U80 found and documented it. If it starts
    failing because the file now appears in the manifest: good, someone closed
    the gap -- go flip CHECKLIST.md item 19 to a RECONCILED tick in the same
    commit that changes this test's expectation. If it fails because the
    manifest lost MORE entries: that's a new, undocumented gap -- do not touch
    this test, go re-run the reconciliation."""
    script_path = ENGINE_DIR / "scripts" / "anthology_book.py"
    assert script_path.is_file(), "anthology_book.py no longer ships -- re-check item 19"

    manifest = json.loads(MANIFEST.read_text())
    haystack = json.dumps(manifest["script_inventory"])
    assert "anthology_book.py" not in haystack, (
        "anthology_book.py now appears in ENGINE-MANIFEST.json's script_inventory -- "
        "the item-19 gap this test documents has been closed; update CHECKLIST.md "
        "item 19 to RECONCILED and update/remove this test in the same commit"
    )


def test_sop_set_is_still_five_of_six():
    """Named claim (CHECKLIST.md item 21): 5 of the 6 SOP-ANTHOLOGY-* documents
    exist; 'Revocation and Churn' does not, anywhere in the repo. Same
    drift-detector contract as the test above."""
    sop_dir = REPO_ROOT / "universal-sops" / "anthology-craft"
    sops = sorted(p.name for p in sop_dir.glob("SOP-ANTHOLOGY-*.md"))
    assert sops == [
        "SOP-ANTHOLOGY-01-ENGINE-RUNBOOK.md",
        "SOP-ANTHOLOGY-02-CLIENT-ONBOARDING.md",
        "SOP-ANTHOLOGY-03-APPROVALS-AND-GATES.md",
        "SOP-ANTHOLOGY-04-ASSEMBLY.md",
        "SOP-ANTHOLOGY-05-CREDIT-HEALTH-AND-QUEUE.md",
    ], (
        f"the anthology-craft SOP set changed to {sops} -- if a Revocation-and-"
        "Churn SOP (or fleet-revocation-runbook appendix) was added, update "
        "CHECKLIST.md item 21 to RECONCILED in the same commit that changes "
        "this test's expectation"
    )


def test_hardcoded_secret_finding_is_named_by_location_only_never_by_value():
    """Named claim (CHECKLIST.md item 2): a hardcoded literal secret value sits
    at scripts/anthology_registry.py, in the FIREBASE_API_KEY assignment. This
    test asserts the location by NAME and LINE only -- it never reads, compares,
    or prints the value itself, matching this repo's own credential doctrine and
    this suite's own hard instruction. If this stops matching, item 2 needs a
    fresh reconciliation pass either way (fixed, or moved)."""
    path = ENGINE_DIR / "scripts" / "anthology_registry.py"
    lines = path.read_text().splitlines()
    assert len(lines) >= 393, "anthology_registry.py is shorter than expected"
    flagged_line = lines[392]  # 1-indexed line 393
    assert "FIREBASE_API_KEY" in flagged_line and "=" in flagged_line, (
        "anthology_registry.py:393 no longer assigns FIREBASE_API_KEY -- if the "
        "hardcoded value was removed (env/label resolution instead), update "
        "CHECKLIST.md item 2 in the same commit that changes this test's "
        "expectation; do not print or copy the line's value anywhere"
    )


def test_wiring_verifier_currently_fails_on_the_named_floor_count_drift():
    """Named claim (CHECKLIST.md item 20): the department's own enforcement
    script, verify-anthology-engine-wiring.py, currently exits non-zero on a
    floor-count mismatch (department-floor.py reports 26, wiring.json declares
    28). Runs the real script; no mocking. If this starts passing, the drift was
    fixed -- flip CHECKLIST.md item 20 to RECONCILED in the same commit."""
    script = (
        REPO_ROOT
        / "23-ai-workforce-blueprint"
        / "department-wiring"
        / "anthology-engine"
        / "verify-anthology-engine-wiring.py"
    )
    result = subprocess.run(
        ["python3", str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, (
        "verify-anthology-engine-wiring.py now exits 0 -- the floor-count drift "
        "CHECKLIST.md item 20 documents appears fixed; update item 20 to "
        "RECONCILED in the same commit that changes this test's expectation"
    )
    assert "floor" in (result.stdout + result.stderr).lower()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
