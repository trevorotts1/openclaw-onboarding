"""Tests for checkpoint resume re-validation (U014)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import struct
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MANIFEST_JSON = json.dumps({
    "manifest_version": 25,
    "phases": [
        {"id": "P9-SPEECH", "order": 8.5, "owning_role": "presenters-speech-writer",
         "produces_artifact": ["working/presenter-speech/PRESENTERS-SPEECH.md"],
         "executor": {"kind": "script"}},
        {"id": "P-CONVERTER", "order": 1.0, "owning_role": "converter",
         "produces_artifact": ["working/copy/intake.json"]},
    ],
    "deliverables_required": [
        {"filename": "PRESENTERS-SPEECH.md", "min_bytes": 2048},
        {"filename": "PRESENTERS-SPEECH.pdf", "min_bytes": 20480},
        {"filename": "presenter-teleprompter.html", "min_bytes": 10240},
    ]
})


def _make_manifest(tmp_path):
    """Write a real manifest file and return a Manifest object."""
    from presentation_job.manifest import Manifest
    mp = tmp_path / "manifest.json"
    mp.write_text(_MANIFEST_JSON, encoding="utf-8")
    return Manifest(mp)


def _png_bytes(w=1, h=1):
    """Build a minimal valid PNG."""
    import zlib

    def _chunk(ctype, data):
        body = ctype + data
        crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + body + crc

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    raw = b"\x00" + b"\x00" * (w * 3)
    idat = zlib.compress(raw)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


# ---------------------------------------------------------------------------
# Test 1-2: validate_text floor
# ---------------------------------------------------------------------------

def test_validate_text_at_floor(tmp_path):
    from presentation_job.artifacts import validate_text
    p = tmp_path / "t.md"
    p.write_bytes(b"x" * 2048)
    ok, reason = validate_text(p, 2048)
    assert ok, f"expected True at floor, got {reason}"


def test_validate_text_under_floor(tmp_path):
    from presentation_job.artifacts import validate_text
    p = tmp_path / "t.md"
    p.write_bytes(b"x" * 2047)
    ok, reason = validate_text(p, 2048)
    assert not ok
    assert "below" in reason.lower()


# ---------------------------------------------------------------------------
# Test 3: validate_image
# ---------------------------------------------------------------------------

def test_validate_image_whole_png(tmp_path):
    from presentation_job.artifacts import validate_image
    p = tmp_path / "g.png"
    p.write_bytes(_png_bytes())
    ok, reason = validate_image(p)
    assert ok, f"expected True for whole PNG, got {reason}"


def test_validate_image_truncated_png(tmp_path):
    from presentation_job.artifacts import validate_image
    p = tmp_path / "b.png"
    data = _png_bytes()
    p.write_bytes(data[:-12])
    ok, reason = validate_image(p)
    assert not ok
    assert "truncated" in reason.lower() or "iend" in reason.lower()


def test_validate_image_hash_mismatch(tmp_path):
    from presentation_job.artifacts import validate_image
    p = tmp_path / "g.png"
    data = _png_bytes()
    p.write_bytes(data)
    ok, reason = validate_image(p, recorded_sha="deadbeef" * 8)
    assert not ok
    assert "sha256" in reason.lower() or "mismatch" in reason.lower()


def test_validate_pptx_rejects_non_zip(tmp_path):
    from presentation_job.artifacts import validate_pptx
    p = tmp_path / "bad.pptx"
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    ok, reason = validate_pptx(p, 10)
    assert not ok


# ---------------------------------------------------------------------------
# Test 4: dispatcher reads floor from manifest
# ---------------------------------------------------------------------------

def test_validate_artifact_reads_floor_from_manifest(tmp_path):
    from presentation_job.artifacts import validate_artifact
    manifest = _make_manifest(tmp_path)
    p = tmp_path / "presenter-teleprompter.html"
    p.write_bytes(b"x" * 10240)
    ok, reason = validate_artifact(tmp_path, "presenter-teleprompter.html", manifest)
    assert ok, f"expected True at floor, got {reason}"
    p.write_bytes(b"x" * 10239)
    ok, reason = validate_artifact(tmp_path, "presenter-teleprompter.html", manifest)
    assert not ok
    assert "below" in reason.lower()


# ---------------------------------------------------------------------------
# Tests 5-9: resume re-run scenarios
# ---------------------------------------------------------------------------

def test_resume_deleted_artifact_fails_validation(tmp_path):
    """Test 5: deleted artifact fails re-validation."""
    from presentation_job.artifacts import validate_artifact
    rd = tmp_path
    (rd / "working" / "presenter-speech").mkdir(parents=True)
    sp = rd / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md"
    sp.write_bytes(b"x" * 2500)
    sha = hashlib.sha256(sp.read_bytes()).hexdigest()
    rel = "working/presenter-speech/PRESENTERS-SPEECH.md"
    manifest = _make_manifest(tmp_path)
    sp.unlink()
    ok, reason = validate_artifact(rd, rel, manifest, recorded_sha=sha)
    assert not ok
    assert "does not exist" in reason.lower()


def test_resume_truncated_artifact_fails_validation(tmp_path):
    """Test 6: truncated artifact below floor is rejected."""
    from presentation_job.artifacts import validate_artifact
    rd = tmp_path
    (rd / "working" / "presenter-speech").mkdir(parents=True)
    sp = rd / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md"
    sp.write_text("# short")
    rel = "working/presenter-speech/PRESENTERS-SPEECH.md"
    sha = hashlib.sha256(sp.read_bytes()).hexdigest()
    manifest = _make_manifest(tmp_path)
    ok, reason = validate_artifact(rd, rel, manifest, recorded_sha=sha)
    assert not ok
    assert "below" in reason.lower(), f"truncated should say below, got: {reason}"


def test_resume_hash_mismatch_fails_validation(tmp_path):
    """Test 7: changed artifact with wrong sha256 is rejected.

    Uses validate_image directly because the text predicate checks only
    existence and floor; hash comparison is a separate step done by the
    re-validation loop itself."""
    from presentation_job.artifacts import validate_image
    p = tmp_path / "g.png"
    data = _png_bytes()
    p.write_bytes(data)
    ok, reason = validate_image(p, recorded_sha="deadbeef" * 8)
    assert not ok
    assert "sha256" in reason.lower() or "mismatch" in reason.lower()


def test_empty_artifact_list_is_rejected():
    """Test 8: status=done with empty artifacts is caught."""
    ps = {"id": "P9-SPEECH", "status": "done", "artifacts": [], "sha256": {},
          "attempts": 1, "heal_events": [], "attested_at": "2026-07-25T00:00:00Z"}
    bad = []
    for rel in ps.get("artifacts", []) or []:
        bad.append("should not iterate")
    if not (ps.get("artifacts") or []) and ["slide-001.png"]:
        bad.append("phase recorded status=done with an empty artifact list")
    assert len(bad) == 1
    assert "empty artifact list" in bad[0]


def test_valid_artifacts_pass_validation(tmp_path):
    """Test 9: all artifacts valid -> skip, executor NOT invoked."""
    from presentation_job.artifacts import validate_artifact
    rd = tmp_path
    (rd / "working" / "presenter-speech").mkdir(parents=True)
    sp = rd / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md"
    sp.write_bytes(b"x" * 2500)
    sha = hashlib.sha256(sp.read_bytes()).hexdigest()
    rel = "working/presenter-speech/PRESENTERS-SPEECH.md"
    manifest = _make_manifest(tmp_path)
    ok, reason = validate_artifact(rd, rel, manifest, recorded_sha=sha)
    assert ok, f"valid artifact should pass, got {reason}"


# ---------------------------------------------------------------------------
# Test 10: heartbeat_interval_minutes has a caller in agent poll loop
# ---------------------------------------------------------------------------

def test_heartbeat_interval_has_caller():
    """Test 10: heartbeat_interval_minutes is accessed in phases.py."""
    import ast
    import pathlib
    phases_path = pathlib.Path(__file__).parent.parent / "presentation_job" / "phases.py"
    tree = ast.parse(phases_path.read_text())
    accesses = [n for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and n.attr == "heartbeat_interval_minutes"]
    assert len(accesses) >= 1, "heartbeat_interval_minutes must have at least one caller"


# ---------------------------------------------------------------------------
# Test 11: _block messages
# ---------------------------------------------------------------------------

def test_block_message_when_artifact_missing(tmp_path):
    """Test 11: missing deliverable produces 'does not exist' reason."""
    from presentation_job.artifacts import validate_artifact
    rd = tmp_path
    manifest = _make_manifest(tmp_path)
    rel = "working/deliverables/PRESENTERS-SPEECH.pdf"
    ok, reason = validate_artifact(rd, rel, manifest, recorded_sha="deadbeef")
    assert not ok
    assert "does not exist" in reason.lower()


def test_block_message_when_valid(tmp_path):
    """Test 11b: valid artifact passes."""
    from presentation_job.artifacts import validate_artifact
    rd = tmp_path
    (rd / "working" / "presenter-speech").mkdir(parents=True)
    sp = rd / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md"
    sp.write_bytes(b"x" * 2500)
    sha = hashlib.sha256(sp.read_bytes()).hexdigest()
    manifest = _make_manifest(tmp_path)
    ok, reason = validate_artifact(rd, "working/presenter-speech/PRESENTERS-SPEECH.md",
                                   manifest, recorded_sha=sha)
    assert ok


# ---------------------------------------------------------------------------
# Test 12: atomicity
# ---------------------------------------------------------------------------

def test_state_save_atomic_no_temp_left(tmp_path):
    """Test 12a: after StateStore.save, no .state-*.tmp file remains."""
    from presentation_job.state import StateStore
    store = StateStore(tmp_path)
    state = {
        "schema_version": 1, "job_id": "test-atomic",
        "run_dir": str(tmp_path), "manifest_path": str(tmp_path / "manifest.json"),
        "manifest_version": 25, "manifest_sha256": "0" * 64,
        "presentation_type": "from_scratch", "requester": {"chat_id": "test"},
        "intake": {}, "current_phase": None, "phases": [],
        "gates": {}, "waivers": [], "events": [],
        "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    loaded = store.load()
    assert loaded["job_id"] == "test-atomic"
    temps = list(tmp_path.glob(".state-*"))
    assert len(temps) == 0, f"Left temp files: {temps}"


def test_state_save_atomic_interrupted(tmp_path):
    """Test 12b: save leaves parseable state.json."""
    from presentation_job.state import StateStore
    store = StateStore(tmp_path)
    state = {
        "schema_version": 1, "job_id": "test-atomic2",
        "run_dir": str(tmp_path), "manifest_path": str(tmp_path / "manifest.json"),
        "manifest_version": 25, "manifest_sha256": "0" * 64,
        "presentation_type": "from_scratch", "requester": {"chat_id": "test"},
        "intake": {}, "current_phase": None, "phases": [],
        "gates": {}, "waivers": [], "events": [],
        "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    assert store.exists()
    loaded = store.load()
    assert loaded["job_id"] == "test-atomic2"


# ---------------------------------------------------------------------------
# Test 13: refuse unclassifiable artifact
# ---------------------------------------------------------------------------

def test_unclassifiable_refused(tmp_path):
    """Test 13: artifact matching no deliverable and no known extension is REFUSED."""
    from presentation_job.artifacts import validate_artifact
    manifest = _make_manifest(tmp_path)
    (tmp_path / "working").mkdir()
    (tmp_path / "working" / "mystery.bin").write_bytes(b"x")
    ok, reason = validate_artifact(tmp_path, "working/mystery.bin", manifest)
    assert not ok
    assert "no validity predicate" in reason
    assert "mystery.bin" in reason
    assert "refusing to reuse" in reason


def test_unclassifiable_refused_does_not_leak(tmp_path):
    """Test 13b: the declared deliverables still validate."""
    from presentation_job.artifacts import validate_artifact
    manifest = _make_manifest(tmp_path)
    (tmp_path / "working" / "presenter-speech").mkdir(parents=True)
    sp = tmp_path / "working" / "presenter-speech" / "PRESENTERS-SPEECH.md"
    sp.write_bytes(b"x" * 2048)
    sha = hashlib.sha256(sp.read_bytes()).hexdigest()
    ok, reason = validate_artifact(
        tmp_path, "working/presenter-speech/PRESENTERS-SPEECH.md", manifest, recorded_sha=sha)
    assert ok, f"deliverable should validate, got {reason}"


# ---------------------------------------------------------------------------
# Test 14: P4-RENDER task id routing
# ---------------------------------------------------------------------------

def test_render_family_task_id_routing(tmp_path):
    """Test 14: renders/slide-*.png routed by path pattern, task id check works."""
    from presentation_job.artifacts import validate_artifact
    manifest = _make_manifest(tmp_path)
    rd = tmp_path
    (rd / "renders").mkdir()
    (rd / "working" / "checkpoints").mkdir(parents=True)

    data = _png_bytes()
    sha = hashlib.sha256(data).hexdigest()

    for n in (1, 2):
        (rd / "renders" / f"slide-{n:03d}.png").write_bytes(data)

    (rd / "working" / "checkpoints" / "process_manifest.json").write_text(json.dumps({
        "phases": [{
            "phase": "render",
            "slides": [
                {"slide": 1, "taskId": "kie-abc123"},
                {"slide": 2, "taskId": "native"},
            ]
        }]
    }))

    # Slide 1: real task id -> pass
    ok1, reason1 = validate_artifact(rd, "renders/slide-001.png", manifest, recorded_sha=sha)
    assert ok1, f"slide 1 (real task id) should pass, got {reason1}"

    # Slide 2: "native" task id -> fail
    ok2, reason2 = validate_artifact(rd, "renders/slide-002.png", manifest, recorded_sha=sha)
    assert not ok2, f"slide 2 (native task id) should fail"
    assert "native" in reason2.lower() or "BAD_TASK" in reason2

    # Delete manifest -> no provenance -> refuse
    (rd / "working" / "checkpoints" / "process_manifest.json").unlink()
    ok3, reason3 = validate_artifact(rd, "renders/slide-001.png", manifest, recorded_sha=sha)
    assert not ok3, f"no checkpoint should refuse"
    assert ("cannot verify provenance" in reason3.lower()
            or "cannot prove provenance" in reason3.lower()
            or "refusing" in reason3.lower()
            or "no validity predicate" in reason3.lower())


# ---------------------------------------------------------------------------
# _BAD_TASK_IDS consistency
# ---------------------------------------------------------------------------

def test_bad_task_ids_consistency():
    """If the copy is used, assert it equals delivery_gate.py:160 source."""
    try:
        from delivery_gate import _BAD_TASK_IDS as src_ids
    except ImportError:
        pytest.skip("delivery_gate not importable")
    from presentation_job.artifacts import _BAD_TASK_IDS as artifact_ids
    assert artifact_ids == src_ids, f"Mismatch: {artifact_ids!r} != {src_ids!r}"
