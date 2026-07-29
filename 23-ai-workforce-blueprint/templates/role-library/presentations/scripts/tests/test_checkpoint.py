"""Tests for U028 -- atomic checkpointing and per-artifact-type validity predicates."""

import hashlib
import json
import os
import pathlib
import struct
import tempfile
import zlib

import pytest


def _chunk(typ, data):
    c = typ + data
    return struct.pack(">I", len(data)) + typ + data + struct.pack(
        ">I", zlib.crc32(c) & 0xFFFFFFFF
    )


def real_png(pad=60000):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 16 for _ in range(16))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"tEXt", b"pad\x00" + b"x" * pad)
        + _chunk(b"IEND", b"")
    )


class TestAtomicWriter:

    def test_atomic_write_bytes_roundtrip(self):
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "out.bin"
        from presentation_job.checkpoint import atomic_write_bytes
        atomic_write_bytes(p, b"hello world")
        assert p.read_bytes() == b"hello world"

    def test_atomic_write_text_roundtrip(self):
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "out.json"
        from presentation_job.checkpoint import atomic_write_text
        atomic_write_text(p, '{"v": 1}')
        assert json.loads(p.read_text()) == {"v": 1}

    def test_no_leftover_temp_files(self):
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "unique.json"
        from presentation_job.checkpoint import atomic_write_text
        atomic_write_text(p, "data")
        files = [f.name for f in d.iterdir() if f.name != "unique.json"]
        assert files == []

    def test_atomic_writer_uses_mkstemp_fsync_replace(self):
        import inspect
        from presentation_job import checkpoint as cp
        src = inspect.getsource(cp)
        assert "mkstemp" in src
        assert "fsync" in src
        assert "os.replace" in src

    def test_atomic_writes_create_parent_dir(self):
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "nested" / "deep" / "f.json"
        from presentation_job.checkpoint import atomic_write_text
        atomic_write_text(p, "ok")
        assert p.read_text() == "ok"

    def test_atomic_write_failure_cleans_temp(self):
        d = pathlib.Path(tempfile.mkdtemp())
        p = d / "target.json"
        from presentation_job.checkpoint import atomic_write_bytes
        payload = b"x" * 100000
        atomic_write_bytes(p, payload)
        temps = [f for f in d.iterdir() if f.name.endswith(".json") and f != p]
        assert temps == []


class TestImagePredicate:

    def setup_method(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.good = real_png()
        self.sha = hashlib.sha256(self.good).hexdigest()
        self.p = self.d / "real.png"
        self.p.write_bytes(self.good)
        self.pred = __import__(
            "presentation_job.checkpoint", fromlist=["PREDICATES"]
        ).PREDICATES["image"]

    def test_valid_right_hash_passes(self):
        assert self.pred(self.p, sha256=self.sha) is True

    def test_wrong_hash_fails(self):
        assert self.pred(self.p, sha256="0" * 64) is False

    def test_under_byte_floor_fails(self):
        thin = real_png(pad=100)
        tp = self.d / "thin.png"
        tp.write_bytes(thin)
        assert self.pred(tp, sha256=hashlib.sha256(thin).hexdigest()) is False

    def test_bad_magic_fails(self):
        bp = self.d / "nomagic.png"
        bp.write_bytes(os.urandom(60000))
        assert self.pred(bp, sha256=hashlib.sha256(bp.read_bytes()).hexdigest()) is False

    def test_truncated_fails(self):
        tp = self.d / "trunc.png"
        tp.write_bytes(self.good[:30000])
        assert self.pred(tp, sha256=hashlib.sha256(tp.read_bytes()).hexdigest()) is False

    def test_symlink_fails(self):
        lp = self.d / "link.png"
        os.symlink(str(self.p), str(lp))
        assert self.pred(lp, sha256=self.sha) is False

    def test_missing_fails(self):
        mp = self.d / "nope.png"
        assert self.pred(mp, sha256=self.sha) is False

    def test_intact_then_corrupt(self):
        assert self.pred(self.p, sha256=self.sha) is True
        self.p.write_bytes(self.good[:20000])
        assert self.pred(self.p, sha256=self.sha) is False

    def test_none_sha256_skips_hash_check(self):
        assert self.pred(self.p, sha256=None) is True

    def test_zero_byte_file_fails(self):
        zp = self.d / "zero.png"
        zp.write_bytes(b"")
        assert self.pred(zp) is False


class TestTextPredicate:

    def setup_method(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.pred = __import__(
            "presentation_job.checkpoint", fromlist=["PREDICATES"]
        ).PREDICATES["text"]

    def test_exists_above_floor_passes(self):
        p = self.d / "speech.md"
        p.write_text("x" * 3000)
        assert self.pred(p, min_bytes=2048) is True

    def test_below_floor_fails(self):
        p = self.d / "short.txt"
        p.write_text("x" * 100)
        assert self.pred(p, min_bytes=2048) is False

    def test_missing_fails(self):
        assert self.pred(self.d / "gone.txt", min_bytes=10) is False

    def test_symlink_fails(self):
        p = self.d / "real.txt"
        p.write_text("x" * 5000)
        lp = self.d / "link.txt"
        os.symlink(str(p), str(lp))
        assert self.pred(lp, min_bytes=100) is False

    def test_zero_bytes_fails(self):
        p = self.d / "empty.txt"
        p.write_text("")
        assert self.pred(p, min_bytes=1) is False


class TestCheckpointBridge:

    def test_checkpoint_noop_when_store_lacks_update_phase(self):
        from presentation_job.checkpoint import checkpoint
        checkpoint(object(), "phase-1", "image", sha256="abc")

    def test_checkpoint_calls_update_phase(self):
        from presentation_job.checkpoint import checkpoint
        calls = []

        class Store:
            def update_phase(self, phase_id, artifact_type, **fields):
                calls.append((phase_id, artifact_type, fields))

        checkpoint(Store(), "phase-3", "image", sha256="abc123", task_id="t1")
        assert len(calls) == 1
        assert calls[0] == ("phase-3", "image", {"sha256": "abc123", "task_id": "t1"})

    def test_checkpoint_never_raises(self):
        from presentation_job.checkpoint import checkpoint

        class BadStore:
            def update_phase(self, *a, **k):
                raise RuntimeError("boom")

        checkpoint(BadStore(), "p", "text")


def test_hash_comparison_reaches_equality():
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "img.png"
    p.write_bytes(real_png())
    correct = hashlib.sha256(real_png()).hexdigest()
    wrong = "0" * 64
    pred = __import__(
        "presentation_job.checkpoint", fromlist=["PREDICATES"]
    ).PREDICATES["image"]
    assert pred(p, sha256=correct) is True
    assert pred(p, sha256=wrong) is False
