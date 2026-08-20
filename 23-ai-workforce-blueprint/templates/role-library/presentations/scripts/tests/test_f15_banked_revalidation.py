"""Tests for Unit F15: banked-artifact re-validation false-positive fix.

ROOT CAUSE (proved against the live run's own state.json, run
pres-wave-e-zhc-1787175621): validate_artifact() in presentation_job/artifacts.py
had no validity predicate for the class of INTERMEDIATE working-set artifacts
that most phases produce (research briefs, intake transcripts, arc/structure
specs, priority-shift specs, ...) -- these are not slide renders, not
registered client deliverables, not slide prompt .txt files, and not
working/qc|copy/intake.json. Every one of them fell through to the catch-all

    return False, f"no validity predicate for {rel_path} -- refusing to reuse it"

UNCONDITIONALLY -- regardless of whether the file was present, untouched, and
byte-identical to what was banked when the phase completed. That is why every
resume printed "N will be rebuilt" and re-spent DeepSeek money re-doing work
that was already paid for: e.g. P-0.5-RESEARCH's
working/research/brief-generated.md was flagged banked_invalid in the live
run's state.json with exactly this reason, even though its on-disk sha256
(f52f25f55a1fca2704694c5a29e110359c4c477d5342ff5b141fb1828f7bc877) matched the
recorded sha256 in state.json exactly.

The fix extends validate_artifact()'s fallback: when a recorded_sha IS
supplied (which phases.py always does for every banked artifact -- sha256 is
populated alongside artifacts at bank time, see phases.py:440-488), the
fallback now verifies the file exists, is non-empty, and its actual sha256
matches the recorded one -- real re-verification, not blind trust. Only when
NO recorded_sha is supplied does it still refuse outright (preserving
tests/test_checkpoint.py::test_mystery_bin_refused, which calls
validate_artifact() with no recorded_sha at all).

These tests FAIL against the pre-fix artifacts.py (proved by reverting to a
scratch copy of the original catch-all and re-running -- see
NON-VACUOUS-PROOF note in the unit's final report).
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.artifacts import validate_artifact
from presentation_job.state import StateStore, EXIT_OK
from presentation_job.manifest import Manifest


def _manifest(dl=None):
    dl = dl or []
    return type("M", (), {"deliverables": dl})()


# ---------------------------------------------------------------------------
# Layer 1: the predicate itself (presentation_job.artifacts.validate_artifact)
# ---------------------------------------------------------------------------

def test_intermediate_artifact_present_and_valid_revalidates_ok(tmp_path):
    """A banked intermediate artifact (not a render, not a deliverable, not a
    slide prompt, not qc/intake.json) that is genuinely present and
    byte-identical to what was recorded must re-validate as VALID.

    This is the exact shape of the live failure: P-0.5-RESEARCH's
    working/research/brief-generated.md.
    """
    rel = "working/research/brief-generated.md"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    content = b"# Research Brief\n" + b"z" * 3000
    p.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()

    ok, why = validate_artifact(tmp_path, rel, _manifest(), recorded_sha=sha)
    assert ok, f"Expected genuinely-present, hash-matching artifact to validate OK, got: {why}"


def test_intermediate_artifact_family_all_revalidate_ok(tmp_path):
    """Every rel_path actually observed failing in the live run's state.json
    (banked_invalid) must now revalidate OK when present + hash-matching."""
    rels = [
        "working/research/brief-generated.md",
        "working/copy/sp_intake.json",
        "working/interview/intake_transcript.json",
        "working/copy/priority_shift_spec.json",
        "working/copy/arc_allocation.json",
        "working/research/research_map.json",
        "working/copy/slides_copy.md",
        "working/copy/sp_structure.json",
        "working/research/design-brief-generated.md",
    ]
    man = _manifest()
    for rel in rels:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        content = (rel + "\n").encode() * 50
        p.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        ok, why = validate_artifact(tmp_path, rel, man, recorded_sha=sha)
        assert ok, f"{rel}: expected OK, got: {why}"


def test_intermediate_artifact_missing_still_fails(tmp_path):
    """A banked intermediate artifact that is genuinely MISSING must still
    fail re-validation -- the gate keeps its teeth."""
    rel = "working/research/brief-generated.md"
    sha = hashlib.sha256(b"whatever was there before").hexdigest()
    # Never written -- file does not exist.
    ok, why = validate_artifact(tmp_path, rel, _manifest(), recorded_sha=sha)
    assert not ok, f"Expected missing artifact to fail re-validation, got OK: {why}"


def test_intermediate_artifact_corrupted_still_fails(tmp_path):
    """A banked intermediate artifact whose content changed (sha256 no
    longer matches what was recorded) must still fail re-validation."""
    rel = "working/copy/arc_allocation.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps({"arc": "original"}).encode()
    recorded_sha = hashlib.sha256(original).hexdigest()
    # File on disk now differs from what was banked (truncated/overwritten).
    p.write_bytes(json.dumps({"arc": "CORRUPTED"}).encode())

    ok, why = validate_artifact(tmp_path, rel, _manifest(), recorded_sha=recorded_sha)
    assert not ok, f"Expected sha256-mismatched artifact to fail re-validation, got OK: {why}"
    assert "sha256 mismatch" in why


def test_intermediate_artifact_empty_file_still_fails(tmp_path):
    """A banked intermediate artifact truncated to zero bytes must still
    fail, even in the pathological case where the recorded hash also
    happens to be the empty-string hash (banking should never produce this,
    but the predicate must not treat 0 bytes as valid)."""
    rel = "working/copy/sp_structure.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    empty_sha = hashlib.sha256(b"").hexdigest()

    ok, why = validate_artifact(tmp_path, rel, _manifest(), recorded_sha=empty_sha)
    assert not ok, f"Expected empty file to fail re-validation regardless of hash, got OK: {why}"


def test_unknown_artifact_with_no_recorded_sha_still_refused(tmp_path):
    """Companion to tests/test_checkpoint.py::test_mystery_bin_refused --
    the fix's new branch only activates when a recorded_sha IS supplied.
    An artifact with genuinely no recorded hash must still refuse outright,
    exactly as before this fix. This proves the fix does not turn into a
    blanket 'trust anything present' rule."""
    (tmp_path / "working").mkdir()
    (tmp_path / "working" / "mystery.bin").write_bytes(b"x")
    ok, why = validate_artifact(tmp_path, "working/mystery.bin", _manifest())
    assert not ok
    assert "no validity predicate" in why and "mystery.bin" in why


# ---------------------------------------------------------------------------
# Layer 2: engine-level resume behaviour (presentation_job.phases.Engine),
# proving the fix reaches the actual "SKIP: already done" resume path and
# stops needless re-spend, not just the raw predicate function.
# ---------------------------------------------------------------------------

def _make_engine_for_intermediate_artifact(tmp_path, rel, content):
    from presentation_job.phases import Engine
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    ap = rd / rel
    ap.parent.mkdir(parents=True, exist_ok=True)
    ap.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()

    mf = tmp_path / "mf.json"
    mf.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{
            "id": "P-0.5-RESEARCH", "order": 0.5, "owning_role": "r",
            "produces_artifact": rel, "client_report": {},
        }],
        "deliverables_required": [],
    }))
    manifest = Manifest(mf)
    store = StateStore(rd)
    state = {
        "job_id": "pj", "schema_version": 1, "run_dir": str(rd),
        "phases": [{
            "id": "P-0.5-RESEARCH", "status": "done", "artifacts": [rel],
            "sha256": {rel: sha}, "attempts": 1, "heal_events": [],
            "attested_at": "x",
        }],
        "events": [], "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {},
    }
    store.save(state)
    state = store.load()
    return Engine(rd, manifest, store, state, dry_run=True), manifest


def test_engine_resume_skips_valid_banked_intermediate_artifact(tmp_path):
    """On resume, a genuinely present + hash-matching intermediate artifact
    must be SKIPPED (banked work reused), not silently re-run and
    re-charged. This is the actual behaviour Trevor is paying DeepSeek for
    on every resume."""
    content = b"# Research Brief\n" + b"z" * 3000
    eng, man = _make_engine_for_intermediate_artifact(
        tmp_path, "working/research/brief-generated.md", content)

    rc = eng.run_phase(man.phase("P-0.5-RESEARCH"))

    assert rc == EXIT_OK
    ps = eng._phase_state("P-0.5-RESEARCH")
    assert ps.get("status") == "done", f"Expected phase to stay done (reused), got: {ps}"
    assert not ps.get("banked_invalid"), (
        f"Expected NO banked_invalid for a genuinely valid artifact, got: {ps.get('banked_invalid')}")
    evs = [e for e in eng.state.get("events", []) if e.get("kind") == "phase.banked_invalid"]
    assert not evs, f"Expected no banked_invalid event, got: {evs}"


def test_engine_resume_still_reruns_missing_intermediate_artifact(tmp_path):
    """On resume, a banked intermediate artifact that is genuinely gone from
    disk must still be detected and the phase re-run -- the gate keeps its
    teeth even after the fix."""
    content = b"# Research Brief\n" + b"z" * 3000
    eng, man = _make_engine_for_intermediate_artifact(
        tmp_path, "working/research/brief-generated.md", content)
    (tmp_path / "run" / "working" / "research" / "brief-generated.md").unlink()

    eng.run_phase(man.phase("P-0.5-RESEARCH"))

    evs = [e for e in eng.state.get("events", []) if e.get("kind") == "phase.banked_invalid"]
    assert evs, "Expected banked_invalid event for genuinely deleted intermediate artifact"


def test_engine_resume_still_reruns_corrupted_intermediate_artifact(tmp_path):
    """On resume, a banked intermediate artifact whose bytes changed
    (sha256 mismatch) must still be detected and the phase re-run."""
    content = b"# Research Brief\n" + b"z" * 3000
    eng, man = _make_engine_for_intermediate_artifact(
        tmp_path, "working/research/brief-generated.md", content)
    (tmp_path / "run" / "working" / "research" / "brief-generated.md").write_text("CORRUPTED SHORT")

    eng.run_phase(man.phase("P-0.5-RESEARCH"))

    ps = eng._phase_state("P-0.5-RESEARCH")
    assert ps.get("banked_invalid"), f"banked_invalid not set after corruption detection: {ps}"
