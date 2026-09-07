"""F21 -- text and document truth: operator-facing strings must not assert
things the repository contradicts.

WHY THIS FILE EXISTS
--------------------
`gates.py._qc_gate` told every operator whose deck was missing
`working/qc/final_qc_report.json`:

    "... -- no phase in the current manifest produces this file ..."

That was true when it was written and has been FALSE since manifest_version 35
(see presentation_job/manifest.py's version log: "merging fix/qc-gate-fail-closed
adds P-QC-AGGREGATE"). At manifest_version 67 the phase `P-QC-AGGREGATE` is
scheduled at order 8.65, is owned by qc-specialist-presentations, declares
`produces_artifact = "working/qc/final_qc_report.json"`, and has a real script
executor (scripts/qc_aggregate.py). The stale sentence survived because nothing
tested it: an outside reviewer read it, believed it, and filed a P0 for a defect
that does not exist. Every hour spent on that P0 was spent because a string lied.

The class of bug is "a claim in prose that no test compares to the artifact it
describes". These tests close that loop for the specific claims F21 names:

  1. the qc-gate failure reason must NAME the phase that owes the file, and must
     not claim no producer exists;
  2. the constants gates.py renders that reason from must equal the manifest's
     own id / order / produces_artifact for that phase;
  3. 00-START-HERE.md's `manifest_version N, M phases` stamp must equal the
     manifest's real version and phase count (the drift test F21 asks for);
  4. the presentations role roster must not carry a manifest version stamp that
     the manifest has moved past.

Deliberately NOT asserted here: the wording of code COMMENTS. Comments may recount
history in the past tense ("when this was written there was no producer") -- that
is honest. What must never regress is what an OPERATOR reads.
"""
import json
import pathlib
import re
import sys
import tempfile

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import gates as gates_mod  # noqa: E402
from presentation_job.gates import Gates  # noqa: E402

# The false sentence this file exists to keep out of the operator's face. Matched
# whitespace-insensitively because the source builds it from adjacent string
# literals across two lines.
_FALSE_PRODUCER_CLAIM = re.compile(
    r"no\s+phase\s+in\s+the\s+current\s+manifest\s+produces\s+this\s+file",
    re.IGNORECASE,
)


def _find_manifest():
    """Deployed layout first (scripts/../sops/PIPELINE-MANIFEST.json), then the
    repo layout by walking up for universal-sops/presentation-slide-craft/.
    Same strategy every other test in this directory uses."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for parent in [cur] + list(cur.parents):
        cand = (parent / "universal-sops" / "presentation-slide-craft"
                / "PIPELINE-MANIFEST.json")
        if cand.is_file():
            return cand
    return None


def _repo_root():
    """Ancestor holding universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json."""
    for parent in [SCRIPTS] + list(SCRIPTS.parents):
        if (parent / "universal-sops" / "presentation-slide-craft"
                / "PIPELINE-MANIFEST.json").is_file():
            return parent
    return None


MANIFEST = _find_manifest()
REPO = _repo_root()


def _qc_aggregate_phase():
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for phase in obj.get("phases", []):
        if phase.get("id") == "P-QC-AGGREGATE":
            return obj, phase
    return obj, None


# --------------------------------------------------------------------------
# 1. The operator-facing reason
# --------------------------------------------------------------------------
def _missing_report_reason():
    run_dir = pathlib.Path(tempfile.mkdtemp())
    result = Gates(run_dir, {})._qc_gate()
    assert result["state"] == "fail", (
        "a missing final_qc_report.json must FAIL the qc gate (D10 fail-closed); "
        f"got {result!r}")
    assert result.get("warn_only") is False, (
        "the qc gate is fail-closed on every branch; warn_only must be False")
    return result["reason"]


def test_qc_gate_reason_does_not_claim_the_producer_is_missing():
    """The exact string that sent a reviewer chasing a phantom P0."""
    reason = _missing_report_reason()
    assert not _FALSE_PRODUCER_CLAIM.search(reason), (
        "gates.py._qc_gate still tells operators no phase in the current manifest "
        "produces working/qc/final_qc_report.json. P-QC-AGGREGATE (order 8.65) "
        "does produce it and has since manifest_version 35. Reason rendered:\n"
        f"  {reason}")


def test_qc_gate_reason_names_the_phase_that_owes_the_file():
    """Naming the producer is the whole point: an operator must be able to go
    look at that phase instead of concluding the pipeline has a hole."""
    reason = _missing_report_reason()
    assert "P-QC-AGGREGATE" in reason, (
        "the qc-gate failure reason must name the phase that owes "
        "working/qc/final_qc_report.json (P-QC-AGGREGATE). Reason rendered:\n"
        f"  {reason}")
    assert "8.65" in reason, (
        "the qc-gate failure reason must carry the phase's manifest order so the "
        f"operator can find it in the manifest. Reason rendered:\n  {reason}")


def test_qc_gate_reason_points_at_evidence_the_phase_actually_leaves():
    """"see that phase's record in ..." is only actionable if it names a file this
    phase really writes.

    P-QC-AGGREGATE declares executor kind "script", so it runs through
    Engine._run_script_phase -> _run_script_phase_locked, which records via
    Engine._checkpoint into state.json's phases[] entry (and, on failure,
    _fail_unit adds quarantined_reason / quarantined_at). It does NOT go through
    dispatcher.dispatch_one, so working/work-orders/<phase>.dispatcher-log.jsonl
    is never written for it -- phases.py's _sidecar_pending docstring says that
    sidecar is appended by dispatcher._append_sidecar and "the engine never
    writes it". Naming the sidecar here would be the same class of lie F21 exists
    to remove, so this test forbids it explicitly."""
    reason = _missing_report_reason()
    assert "state.json" in reason, (
        "the reason must point the operator at the phase's own state.json record "
        "(phases[] entry id=P-QC-AGGREGATE), which is the evidence a script-kind "
        f"phase actually leaves behind. Reason rendered:\n  {reason}")
    assert "dispatcher-log.jsonl" not in reason, (
        "the reason points at working/work-orders/<phase>.dispatcher-log.jsonl, "
        "which dispatcher._append_sidecar writes for AGENT phases only. "
        "P-QC-AGGREGATE is executor kind 'script' and never produces that file, so "
        f"this sends a stuck operator to a path that does not exist. Reason:\n  {reason}")


# --------------------------------------------------------------------------
# 2. The constants the reason is rendered from must match the manifest
# --------------------------------------------------------------------------
@pytest.mark.skipif(MANIFEST is None, reason="PIPELINE-MANIFEST.json not found")
def test_gates_qc_aggregate_constants_match_the_manifest():
    """gates.py hardcodes the id/order/sidecar so close() never needs a
    resolvable manifest on disk. That is only safe if a test pins them to the
    manifest -- otherwise this file becomes the next stale string."""
    _, phase = _qc_aggregate_phase()
    assert phase is not None, (
        "P-QC-AGGREGATE is absent from PIPELINE-MANIFEST.json. If the phase was "
        "genuinely removed, gates.py's reason text must be rewritten in the same "
        "commit -- it currently tells operators that phase owes them the file.")

    phase_id = getattr(gates_mod, "QC_AGGREGATE_PHASE_ID", None)
    order = getattr(gates_mod, "QC_AGGREGATE_PHASE_ORDER", None)
    evidence = getattr(gates_mod, "QC_AGGREGATE_EVIDENCE_REL", None)

    assert phase_id is not None and order is not None and evidence is not None, (
        "gates.py must expose QC_AGGREGATE_PHASE_ID / QC_AGGREGATE_PHASE_ORDER / "
        "QC_AGGREGATE_EVIDENCE_REL so the operator-facing reason is rendered from "
        "named constants this test can pin to the manifest, not from a literal "
        "buried in an f-string where it went stale for 30+ manifest versions.")

    assert phase_id == phase["id"], (
        f"gates.QC_AGGREGATE_PHASE_ID={phase_id!r} != manifest id {phase['id']!r}")
    assert float(order) == float(phase["order"]), (
        f"gates.QC_AGGREGATE_PHASE_ORDER={order!r} != manifest order "
        f"{phase['order']!r} -- the reason quotes an order that no longer exists")
    assert phase.get("produces_artifact") == "working/qc/final_qc_report.json", (
        "P-QC-AGGREGATE no longer declares working/qc/final_qc_report.json as its "
        f"produces_artifact (got {phase.get('produces_artifact')!r}); the qc gate "
        "blames it for a file it does not owe")
    # The evidence path must match the executor kind the manifest declares. A
    # "script" phase records into state.json; only an agent phase gets a
    # dispatcher sidecar. If someone flips this phase to an agent executor, this
    # assertion fires and the reason text has to be revisited with it.
    kind = (phase.get("executor") or {}).get("kind")
    assert kind == "script", (
        f"P-QC-AGGREGATE executor kind is now {kind!r}, not 'script'. gates.py's "
        "reason points operators at state.json because a script phase records "
        "there via Engine._checkpoint; an agent phase would record in "
        "working/work-orders/<phase>.dispatcher-log.jsonl instead. Update "
        "QC_AGGREGATE_EVIDENCE_REL and the reason text together.")
    assert evidence == "state.json", (
        f"gates.QC_AGGREGATE_EVIDENCE_REL={evidence!r}; for a script-kind phase the "
        "run's state.json (state.STATE_FILENAME, written to run_dir/state.json) is "
        "the record Engine._checkpoint actually writes")


# --------------------------------------------------------------------------
# 3. The START-HERE drift test F21 asks for
# --------------------------------------------------------------------------
_VERSION_STAMP = re.compile(
    r"manifest_version\s+(\d+),\s*(?:(\d+)\s*phases|declared count\s*(\d+))",
    re.IGNORECASE)


@pytest.mark.skipif(MANIFEST is None or REPO is None,
                    reason="repo layout with PIPELINE-MANIFEST.json not found")
def test_start_here_manifest_version_matches_the_manifest():
    """00-START-HERE.md is what an agent reads to route work. Its
    'manifest_version N, M phases' stamp went to v55/55 against a v67/62 manifest
    once already; this pins it."""
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = obj["manifest_version"]
    count = len(obj["phases"])

    start_here = (REPO / "23-ai-workforce-blueprint" / "templates" / "role-library"
                  / "presentations" / "00-START-HERE.md")
    if not start_here.is_file():
        pytest.skip(f"00-START-HERE.md not present at {start_here}")

    text = start_here.read_text(encoding="utf-8")
    stamps = [(int(m.group(1)), int(m.group(2) or m.group(3)))
              for m in _VERSION_STAMP.finditer(text)]
    assert stamps, (
        "00-START-HERE.md carries no 'manifest_version N, M phases' stamp at all. "
        "It is the file an agent reads to learn which pipeline it is driving; the "
        "stamp is required so this drift test has something to compare.")
    for stamped_version, stamped_count in stamps:
        assert (stamped_version, stamped_count) == (version, count), (
            f"00-START-HERE.md claims manifest_version {stamped_version} with "
            f"{stamped_count} phases; PIPELINE-MANIFEST.json is version {version} "
            f"with {count} phases. Bump the doc in the same commit as the manifest.")


@pytest.mark.skipif(MANIFEST is None or REPO is None,
                    reason="repo layout with PIPELINE-MANIFEST.json not found")
def test_presentations_role_cards_manifest_stamps_match():
    """Same drift, same lock, for the role cards and DEPARTMENT-COUNTS-CANONICAL
    that F21 lists beside START-HERE. Scoped to files that already carry a stamp:
    this test pins the ones that make the claim, it does not demand new ones."""
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    truth = (obj["manifest_version"], len(obj["phases"]))

    dept = (REPO / "23-ai-workforce-blueprint" / "templates" / "role-library"
            / "presentations")
    if not dept.is_dir():
        pytest.skip(f"presentations role library not present at {dept}")

    stale = []
    checked = 0
    for path in sorted(dept.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for m in _VERSION_STAMP.finditer(text):
            checked += 1
            got = (int(m.group(1)), int(m.group(2) or m.group(3)))
            if got != truth:
                line = text[:m.start()].count("\n") + 1
                stale.append(f"{path.name}:{line} claims v{got[0]}/{got[1]}")

    # Control: if this loop found no stamps at all, the scan is broken, not clean.
    assert checked > 0, (
        f"no 'manifest_version N, M phases' stamp found in any *.md under {dept} -- "
        "the scanner matched nothing, which means this test is not checking "
        "anything rather than that everything is current")
    assert not stale, (
        f"manifest stamp drift against v{truth[0]}/{truth[1]}: " + "; ".join(stale))


# --------------------------------------------------------------------------
# 4. The roster's stale version stamp
# --------------------------------------------------------------------------
@pytest.mark.skipif(REPO is None, reason="repo layout not found")
def test_presentations_roster_has_no_superseded_manifest_stamp():
    """presentations-suggested-roles.md described the Slide Submitter as having
    'no owns_phase in manifest v51' -- a claim stamped to a manifest 16 versions
    behind, which then propagated verbatim into the generated
    how-to-use-this-department.md the client reads. The SUBSTANCE was still true
    (owns_phase is null at v67); the STAMP was not."""
    roster = (REPO / "23-ai-workforce-blueprint" / "suggested-roles"
              / "presentations-suggested-roles.md")
    generated = (REPO / "23-ai-workforce-blueprint" / "templates" / "role-library"
                 / "presentations" / "how-to-use-this-department.md")
    if not roster.is_file():
        pytest.skip(f"roster not present at {roster}")

    stale = re.compile(r"manifest\s+v(\d+)", re.IGNORECASE)
    current = None
    if MANIFEST is not None:
        current = json.loads(MANIFEST.read_text(encoding="utf-8"))["manifest_version"]

    seen = 0
    for path in (roster, generated):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for m in stale.finditer(text):
            seen += 1
            stamped = int(m.group(1))
            line = text[:m.start()].count("\n") + 1
            assert current is None or stamped >= current, (
                f"{path.name}:{line} stamps a claim to 'manifest v{stamped}' while "
                f"the pipeline manifest is at v{current}. Either re-verify the "
                "claim against the current manifest and restamp it, or drop the "
                "version reference -- a stamp 16 versions behind is how the "
                "final_qc_report.json producer lie survived.")

    # Control: the Slide Submitter entry is expected to carry exactly one current
    # stamp. Zero matches means the scanner broke, not that the roster is clean.
    assert seen > 0, (
        f"no 'manifest v<N>' stamp found in {roster.name} or {generated.name}; the "
        "scanner matched nothing, so a stale stamp reintroduced in a different "
        "wording would slip past this test unnoticed")


@pytest.mark.skipif(REPO is None, reason="repo layout not found")
def test_generated_department_guide_example_request_is_a_whole_sentence():
    """The guide's 'Example request' lines are what a non-technical owner copies
    and pastes. The Slide Submitter one used to end mid-clause ('... P4-RENDER."')
    because the source's first sentence overran the 90-char cap. A truncated
    example is an instruction the owner cannot follow."""
    generated = (REPO / "23-ai-workforce-blueprint" / "templates" / "role-library"
                 / "presentations" / "how-to-use-this-department.md")
    if not generated.is_file():
        pytest.skip(f"generated guide not present at {generated}")

    text = generated.read_text(encoding="utf-8")
    lines = [l for l in text.split("\n") if "*Example request:*" in l]
    assert lines, (
        "no '*Example request:*' lines found in how-to-use-this-department.md -- "
        "the scanner matched nothing, so this test proves nothing")

    broken = []
    for line in lines:
        if "Slide Submitter" not in line:
            continue
        # An unbalanced '(' means the cap cut the sentence inside a parenthetical.
        if line.count("(") != line.count(")"):
            broken.append(line.strip())
    assert not broken, (
        "the Slide Submitter example request is truncated mid-parenthetical; "
        "shorten the FIRST sentence of its entry in "
        "23-ai-workforce-blueprint/suggested-roles/presentations-suggested-roles.md "
        "(cap is 90 chars, see how_to_use_department._first_sentence) and "
        "regenerate with generate_how_to_use_docs.py presentations. Got:\n  "
        + "\n  ".join(broken))
