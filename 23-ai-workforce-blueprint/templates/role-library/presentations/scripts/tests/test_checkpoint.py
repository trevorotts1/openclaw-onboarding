"""Tests for U014: checkpoint before every phase, re-validate banked artifacts on resume."""
from __future__ import annotations

import hashlib, json, os, struct, sys, tempfile, zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.artifacts import (
    _exists_is_file, _check_floor, _sha_check,
    validate_text, validate_json, validate_image,
    validate_pdf, validate_pptx,
    validate_artifact, render_manifest_for,
    _BAD_TASK_IDS,
)


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _make_png() -> bytes:
    """Return a valid PNG > 50 bytes."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", 0x0BF0C2F3 & 0xFFFFFFFF)
    idat_payload = b"\x00" * 50
    idat_crc = struct.pack(">I", 0xDEADBEEF & 0xFFFFFFFF)
    iend_crc = struct.pack(">I", 0xAE426082)
    chunks = sig + struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc
    chunks += struct.pack(">I", 50) + b"IDAT" + idat_payload + idat_crc
    chunks += struct.pack(">I", 0) + b"IEND" + iend_crc
    return chunks


def _make_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _make_pptx() -> bytes:
    fd, name = tempfile.mkstemp(suffix=".pptx")
    os.close(fd)
    p = Path(name)
    try:
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types></Types>")
        data = p.read_bytes()
    finally:
        p.unlink(missing_ok=True)
    return data


def _make_run_dir(files: Dict[str, bytes]) -> Path:
    d = Path(tempfile.mkdtemp())
    for rel, data in files.items():
        fpath = d / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_bytes(data)
    return d


class _FakeManifest:
    deliverables = [
        {"filename": "output.pptx", "min_bytes": 100},
        {"filename": "output.pdf", "min_bytes": 10},
        {"filename": "infographic.png", "min_bytes": 50},
        {"filename": "notes.md", "min_bytes": 1},
        {"filename": "speech.html", "min_bytes": 1},
        {"filename": "audio.mp3", "min_bytes": 1},
        {"filename": "waivers.json", "min_bytes": 2},
        {"filename": "state.json", "min_bytes": 2},
        {"filename": "summary.txt", "min_bytes": 9000},
    ]


# -- basic predicates --
class TestValidateText:
    def test_floor_pass(self, tmp_path):
        p = _write(tmp_path / "t.txt", b"hello world")
        ok, _ = validate_text(p, 5)
        assert ok

    def test_floor_fail(self, tmp_path):
        p = _write(tmp_path / "t.txt", b"hi")
        ok, reason = validate_text(p, 100)
        assert not ok
        assert "below floor" in reason

    def test_missing_file(self, tmp_path):
        p = tmp_path / "ghost.txt"
        ok, reason = validate_text(p, 1)
        assert not ok
        assert "does not exist" in reason


class TestValidateImage:
    def test_valid_png(self, tmp_path):
        p = _write(tmp_path / "s.png", _make_png())
        ok, _ = validate_image(p)
        assert ok

    def test_truncated_no_iend(self, tmp_path):
        data = _make_png()
        p = _write(tmp_path / "s.png", data[:-20])
        ok, reason = validate_image(p)
        assert not ok
        assert "IEND" in reason

    def test_hash_mismatch(self, tmp_path):
        p = _write(tmp_path / "s.png", _make_png())
        ok, reason = validate_image(p, recorded_sha="0" * 64)
        assert not ok
        assert "!=" in reason

    def test_hash_match(self, tmp_path):
        data = _make_png()
        p = _write(tmp_path / "s.png", data)
        sha = hashlib.sha256(data).hexdigest()
        ok, _ = validate_image(p, recorded_sha=sha)
        assert ok

    def test_too_short(self, tmp_path):
        p = _write(tmp_path / "s.png", b"x")
        ok, reason = validate_image(p)
        assert not ok
        assert "too short" in reason


class TestValidatePptx:
    def test_valid_pptx(self, tmp_path):
        p = _write(tmp_path / "o.pptx", _make_pptx())
        ok, _ = validate_pptx(p, 100)
        assert ok

    def test_not_a_zip(self, tmp_path):
        p = _write(tmp_path / "o.pptx", b"not a zip")
        ok, reason = validate_pptx(p, 1)
        assert not ok
        assert "ZIP/PK" in reason


class TestValidatePdf:
    def test_valid_pdf(self, tmp_path):
        p = _write(tmp_path / "o.pdf", _make_pdf())
        ok, _ = validate_pdf(p, 10)
        assert ok

    def test_missing_eof(self, tmp_path):
        p = _write(tmp_path / "o.pdf", b"%PDF-1.4\nno eof")
        ok, reason = validate_pdf(p, 5)
        assert not ok
        assert "EOF" in reason


# -- dispatcher --
class TestValidateArtifact:
    def test_pptx_via_manifest(self, tmp_path):
        run = _make_run_dir({"output.pptx": _make_pptx()})
        ok, _ = validate_artifact(run, "output.pptx", _FakeManifest())
        assert ok

    def test_pdf_via_manifest(self, tmp_path):
        run = _make_run_dir({"output.pdf": _make_pdf()})
        ok, _ = validate_artifact(run, "output.pdf", _FakeManifest())
        assert ok

    def test_unknown_artifact_refused(self, tmp_path):
        run = _make_run_dir({"weird.xyz": b"data"})
        ok, reason = validate_artifact(run, "weird.xyz", _FakeManifest())
        assert not ok
        assert "no validity predicate" in reason

    def test_nine_deliverables_still_validate(self, tmp_path):
        run = _make_run_dir({
            "output.pptx": _make_pptx(),
            "output.pdf": _make_pdf(),
            "infographic.png": _make_png(),
            "notes.md": b"# Notes\n\nSome content here.",
            "speech.html": b"<html><body>Speech</body></html>",
            "audio.mp3": b"fake mp3 data with enough bytes .................",
            "waivers.json": b'{"waived": true}',
            "state.json": b'{"ok": true}',
            "summary.txt": b"x" * 10000,
        })
        ok_count = 0
        for fname in ["output.pptx", "output.pdf", "infographic.png", "notes.md",
                       "speech.html", "audio.mp3", "waivers.json", "state.json", "summary.txt"]:
            ok, reason = validate_artifact(run, fname, _FakeManifest())
            assert ok or "no validity predicate" not in reason, f"{fname}: {reason}"
            if ok:
                ok_count += 1
        assert ok_count == 9, f"Only {ok_count}/9 validated"

    def test_floor_rejects_tiny_file(self, tmp_path):
        run = _make_run_dir({"output.pptx": b"PK\x03\x04" + b"\x00" * 20})
        ok, reason = validate_artifact(run, "output.pptx", _FakeManifest())
        assert not ok
        assert "below floor" in reason


# -- resume re-validation --
class TestResumeRevalidation:
    def test_valid_banked_ok(self, tmp_path):
        data = _make_pptx()
        run = _make_run_dir({"output.pptx": data})
        sha = hashlib.sha256(data).hexdigest()
        ok, _ = validate_artifact(run, "output.pptx", _FakeManifest(), recorded_sha=sha)
        assert ok

    def test_deleted_banked_fails(self, tmp_path):
        data = _make_pptx()
        sha = hashlib.sha256(data).hexdigest()
        run = _make_run_dir({"output.pptx": data})
        (run / "output.pptx").unlink()
        ok, reason = validate_artifact(run, "output.pptx", _FakeManifest(), recorded_sha=sha)
        assert not ok
        assert "does not exist" in reason

    def test_truncated_banked_fails(self, tmp_path):
        data = _make_png()
        sha = hashlib.sha256(data).hexdigest()
        run = _make_run_dir({"infographic.png": data[:50]})
        ok, reason = validate_artifact(run, "infographic.png", _FakeManifest(), recorded_sha=sha)
        assert not ok

    def test_hash_mismatch_sha_check(self, tmp_path):
        run = _make_run_dir({"notes.md": b"some notes content for testing"})
        ok, reason = validate_artifact(run, "notes.md", _FakeManifest(),
                                        recorded_sha="0" * 64)
        assert not ok
        assert "!=" in reason

    def test_empty_artifact_fails(self, tmp_path):
        run = _make_run_dir({"notes.md": b""})
        ok, reason = validate_artifact(run, "notes.md", _FakeManifest())
        assert not ok
        assert "below floor" in reason


# -- P4-RENDER --
class TestRenderRouting:
    def test_no_checkpoint_refused(self, tmp_path):
        run = _make_run_dir({"renders/slide-001.png": _make_png()})
        ok, reason = validate_artifact(run, "renders/slide-001.png", _FakeManifest())
        assert not ok
        assert "process_manifest.json" in reason

    def test_bad_task_id_rejected(self, tmp_path):
        run = _make_run_dir({"renders/slide-001.png": _make_png()})
        ck = run / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        (ck / "process_manifest.json").write_text(json.dumps({
            "phases": [{"phase": "render", "slides": [{"slide": 1, "taskId": "placeholder"}]}]
        }))
        ok, reason = validate_artifact(run, "renders/slide-001.png", _FakeManifest())
        assert not ok
        assert "not a real kie task id" in reason

    def test_real_task_id_accepted(self, tmp_path):
        run = _make_run_dir({"renders/slide-001.png": _make_png()})
        ck = run / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        (ck / "process_manifest.json").write_text(json.dumps({
            "phases": [{"phase": "render", "slides": [{"slide": 1, "taskId": "tk_a1b2c3d4e5f6g7h8"}]}]
        }))
        ok, _ = validate_artifact(run, "renders/slide-001.png", _FakeManifest())
        assert ok


# -- BAD_TASK_IDS --
class TestBadTaskIds:
    def test_none_is_bad(self):
        assert None in _BAD_TASK_IDS

    def test_placeholder_is_bad(self):
        assert "placeholder" in _BAD_TASK_IDS

    def test_all_bad_values_are_hashable(self):
        for bad in _BAD_TASK_IDS:
            h = hash(bad)
            assert isinstance(h, int)


# -- atomicity --
class TestAtomicity:
    def test_no_temp_files_in_output(self, tmp_path):
        p = _write(tmp_path / "o.pptx", _make_pptx())
        before = set(tmp_path.iterdir())
        validate_pptx(p, 10)
        after = set(tmp_path.iterdir())
        assert before == after

    def test_json_parsable(self, tmp_path):
        p = _write(tmp_path / "s.json", b'{"key": "value", "num": 42}')
        ok, _ = validate_json(p)
        assert ok

    def test_json_not_parsable(self, tmp_path):
        p = _write(tmp_path / "s.json", b"not json at all")
        ok, reason = validate_json(p)
        assert not ok
        assert "not valid JSON" in reason


# -- render_manifest_for --
class TestRenderManifestFor:
    def test_returns_empty_when_no_checkpoint(self, tmp_path):
        assert render_manifest_for(tmp_path, "renders/slide-001.png") == {}

    def test_extracts_slide_task_mapping(self, tmp_path):
        ck = tmp_path / "working" / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        (ck / "process_manifest.json").write_text(json.dumps({
            "phases": [{"phase": "render",
                         "slides": [{"slide": 1, "taskId": "tk_aaa"},
                                    {"slide": 2, "taskId": "tk_bbb"}]}]
        }))
        result = render_manifest_for(tmp_path, "renders/slide-002.png")
        assert result.get("renders/slide-001.png") == "tk_aaa"
        assert result.get("renders/slide-002.png") == "tk_bbb"


# -- _block messages --
class TestBlockMessages:
    def test_missing_artifact_detected(self, tmp_path):
        run = _make_run_dir({})
        ok, reason = validate_artifact(run, "output.pptx", _FakeManifest())
        assert not ok
        assert "does not exist" in reason

    def test_present_artifact_validated(self, tmp_path):
        run = _make_run_dir({"output.pptx": _make_pptx()})
        ok, _ = validate_artifact(run, "output.pptx", _FakeManifest())
        assert ok
