"""Tests for checkpoint resume + artifact validation (U014), and atomic
checkpointing + per-artifact-type validity predicates (U028).

This file is shared by two units. U014 landed first (commit c753fbb0) and
owns everything above the "U028" marker below: StateStore atomicity,
presentation_job.artifacts's validate_text/validate_image/validate_pdf/
validate_pptx/validate_json/validate_artifact/render_manifest_for, and the
Engine re-validation-on-resume behaviour. U028 (this unit) owns everything
from the "U028" marker down: presentation_job.checkpoint's atomic writer and
the image/text predicate registry used by build_deck.render_slide's
pre-call task-id checkpoint.

Do not remove or rewrite U014's tests to add U028's -- extend this file,
never replace it. A prior version of SPEC/units/U028.md's Touches: block
mislabelled this path NEW; it was already U014's file. See
QUALITY-CONTROL/tickets/U028.md, Round 8, CORRECTION 3, for the full history.
"""
import hashlib, json, os, pathlib, struct, sys, tempfile, zlib
from pathlib import Path
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, EXIT_OK
from presentation_job.artifacts import (validate_text, validate_image, validate_pdf,
    validate_pptx, validate_json, validate_artifact, render_manifest_for, _BAD_TASK_IDS)
from presentation_job.manifest import Manifest, Phase

def _png(w=1, h=1):
    def ch(t, d):
        c = zlib.crc32(t + d) & 0xFFFFFFFF
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", c)
    ih = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    r = b"\x00" + b"\x00" * (w * 4)
    return b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", ih) + ch(b"IDAT", zlib.compress(r)) + ch(b"IEND", b"")

def _manifest(dl=None):
    dl = dl or [{"key": "s", "filename": "S.md", "min_bytes": 2048, "label": "s"}]
    return type("M", (), {"deliverables": dl})()

# Test 1
def test_text_floor_accepts(tmp_path):
    p = tmp_path / "t.md"; p.write_bytes(b"x" * 2048)
    assert validate_text(p, 2048)[0]

def test_text_under_rejects(tmp_path):
    p = tmp_path / "t.md"; p.write_bytes(b"x" * 2047)
    assert not validate_text(p, 2048)[0]

def test_text_nonexistent(tmp_path):
    assert not validate_text(tmp_path / "n.md", 2048)[0]

# Test 2
def test_png_valid(tmp_path):
    p = tmp_path / "g.png"; p.write_bytes(_png())
    assert validate_image(p)[0]

def test_png_truncated(tmp_path):
    d = _png(); p = tmp_path / "b.png"; p.write_bytes(d[:-12])
    ok, r = validate_image(p); assert not ok

def test_png_hash_mismatch(tmp_path):
    d = _png(); p = tmp_path / "g.png"; p.write_bytes(d)
    ok, r = validate_image(p, recorded_sha=hashlib.sha256(b"x").hexdigest())
    assert not ok

def test_png_bad_task_id(tmp_path):
    d = _png()
    p = tmp_path / "r" / "s001.png"; p.parent.mkdir(); p.write_bytes(d)
    sha = hashlib.sha256(d).hexdigest()
    rm = {"r/s001.png": "native"}
    assert not validate_image(p, recorded_sha=sha, render_manifest=rm)[0]

def test_png_good_task_id(tmp_path):
    d = _png()
    p = tmp_path / "r" / "s001.png"; p.parent.mkdir(); p.write_bytes(d)
    sha = hashlib.sha256(d).hexdigest()
    rm = {"r/s001.png": "kie-abc"}
    assert validate_image(p, recorded_sha=sha, render_manifest=rm)[0]

# Test 3
def test_pptx_bad_zip(tmp_path):
    p = tmp_path / "b.pptx"; p.write_bytes(b"PK" + b"\x00" * 100)
    assert not validate_pptx(p, 2)[0]

# Test 4
def test_manifest_floor(tmp_path):
    d = tmp_path / "w" / "d"; d.mkdir(parents=True)
    (d / "t.html").write_bytes(b"x" * 10240)
    man = _manifest([{"key": "t", "filename": "t.html", "min_bytes": 10240}])
    assert validate_artifact(tmp_path, "w/d/t.html", man)[0]

def test_manifest_under(tmp_path):
    d = tmp_path / "w" / "d"; d.mkdir(parents=True)
    (d / "t.html").write_bytes(b"x" * 10239)
    man = _manifest([{"key": "t", "filename": "t.html", "min_bytes": 10240}])
    assert not validate_artifact(tmp_path, "w/d/t.html", man)[0]

# Test 5-9: re-validation
def _make_engine(tmp_path, rel, content, manifest_dl=None, state_override=None):
    from presentation_job.phases import Engine
    rd = tmp_path / "run"; rd.mkdir(parents=True, exist_ok=True)
    ap = rd / rel; ap.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        ap.write_text(content)
    shasum = hashlib.sha256(ap.read_bytes()).hexdigest() if (content is not None and ap.is_file()) else "deadbeef" * 8
    mf = tmp_path / "mf.json"
    dl = manifest_dl or [{"key": "s", "filename": Path(rel).name, "min_bytes": 2048, "label": "s"}]
    mf.write_text(json.dumps({"manifest_version": 25, "phases": [
        {"id": "P9", "order": 8.5, "owning_role": "r", "produces_artifact": rel, "client_report": {}}],
        "deliverables_required": dl}))
    manifest = Manifest(mf)
    store = StateStore(rd)
    state = {"job_id": "pj", "schema_version": 1, "run_dir": str(rd),
             "phases": [{"id": "P9", "status": "done", "artifacts": [rel],
                         "sha256": {rel: shasum}, "attempts": 1,
                         "heal_events": [], "attested_at": "x"}],
             "events": [], "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}}
    if state_override:
        state.update(state_override)
    store.save(state)
    state = store.load()
    return Engine(rd, manifest, store, state, dry_run=True), manifest

def test_deleted_reruns(tmp_path):
    eng, man = _make_engine(tmp_path, "w/s/S.md", "# s\n" + "z" * 2500)
    (tmp_path / "run" / "w" / "s" / "S.md").unlink()
    eng.run_phase(man.phase("P9"))
    # Detection should fire
    evs = [e for e in eng.state.get("events", []) if e.get("kind") == "phase.banked_invalid"]
    assert evs, "Expected banked_invalid event for deleted artifact"

def test_truncated_reruns(tmp_path):
    eng, man = _make_engine(tmp_path, "w/s/S.md", "# s\n" + "z" * 2500)
    (tmp_path / "run" / "w" / "s" / "S.md").write_text("# short")
    eng.run_phase(man.phase("P9"))
    evs = [e for e in eng.state.get("events", []) if e.get("kind") == "phase.banked_invalid"]
    assert evs, "Expected banked_invalid for truncated artifact"

def test_sha_mismatch_reruns(tmp_path):
    eng, man = _make_engine(tmp_path, "w/s/S.md", "# s\n" + "z" * 2500)
    ps = eng._phase_state("P9")
    ps["sha256"]["w/s/S.md"] = "deadbeef" * 8
    eng.store.save(eng.state)
    eng.state = eng.store.load()
    eng.run_phase(man.phase("P9"))
    ps2 = eng._phase_state("P9")
    assert ps2.get("banked_invalid"), f"banked_invalid not set after detection: {ps2}"

def test_empty_artifacts_reruns(tmp_path):
    eng, man = _make_engine(tmp_path, "w/s/S.md", None,
                            state_override={"phases": [
                                {"id": "P9", "status": "done", "artifacts": [], "sha256": {},
                                 "attempts": 1, "heal_events": [], "attested_at": "x"}]})
    eng.run_phase(man.phase("P9"))
    evs = [e for e in eng.state.get("events", []) if e.get("kind") == "phase.banked_invalid"]
    assert evs, "Expected banked_invalid for empty artifacts"

def test_valid_skipped(tmp_path):
    eng, man = _make_engine(tmp_path, "w/s/S.md", "# s\n" + "z" * 2500)
    rc = eng.run_phase(man.phase("P9"))
    assert rc == EXIT_OK, f"Expected SKIP (EXIT_OK=0), got {rc}"
    assert eng._phase_state("P9").get("status") == "done"

# Test 10
def test_heartbeat_interval(tmp_path):
    from presentation_job.phases import Engine
    rd = tmp_path / "run"; rd.mkdir(parents=True, exist_ok=True)
    (rd / "working").mkdir(parents=True, exist_ok=True)
    (rd / "w").mkdir(parents=True, exist_ok=True)
    (rd / "w/o.txt").write_text("ok")
    mf = tmp_path / "mf.json"
    mf.write_text(json.dumps({"manifest_version": 25, "phases": [
        {"id": "PT", "order": 1.0, "owning_role": "r", "produces_artifact": "w/o.txt",
         "heartbeat_minutes": 1, "client_report": {}}], "deliverables_required": []}))
    manifest = Manifest(mf)
    store = StateStore(rd)
    state = {"job_id": "pj", "schema_version": 1, "run_dir": str(rd), "phases": [],
             "events": [], "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}}
    store.save(state); state = store.load()
    eng = Engine(rd, manifest, store, state)
    ph = manifest.phase("PT")
    assert ph.heartbeat_interval_minutes >= 1
    assert eng._run_agent_phase(ph) == EXIT_OK

# Test 11
def test_block_rebuilt_message(tmp_path):
    from presentation_job.phases import Engine
    rd = tmp_path / "run"; rd.mkdir(parents=True, exist_ok=True)
    (rd / "working" / "deliverables").mkdir(parents=True, exist_ok=True)
    mf = tmp_path / "mf.json"
    rel = "working/deliverables/P.pdf"
    mf.write_text(json.dumps({"manifest_version": 25, "phases": [
        {"id": "P9", "order": 8.5, "owning_role": "r", "produces_artifact": rel, "client_report": {}}],
        "deliverables_required": [{"key": "sp", "filename": "P.pdf", "min_bytes": 20480, "label": "sp"}]}))
    manifest = Manifest(mf)
    store = StateStore(rd)
    state = {"job_id": "pj", "schema_version": 1, "run_dir": str(rd),
             "phases": [{"id": "P9", "status": "done", "artifacts": [rel],
                         "sha256": {rel: "deadbeef" * 8}, "attempts": 1,
                         "heal_events": [], "attested_at": "x"}],
             "events": [], "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}}
    store.save(state); state = store.load()
    eng = Engine(rd, manifest, store, state)
    eng._block(manifest.phase("P9"), "test")
    evs = [e for e in state.get("events", []) if e.get("kind") == "report.blocked"]
    assert evs
    msg = evs[-1]["message"]
    assert "will be rebuilt" in msg, f"Expected 'will be rebuilt' in: {msg[:150]}"

# Test 12
def test_atomic_no_temp(tmp_path):
    store = StateStore(tmp_path)
    store.save({"job_id": "pj", "schema_version": 1, "phases": [], "events": [],
                "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}})
    assert len(list(tmp_path.glob(".state-*.tmp"))) == 0

def test_atomic_parses(tmp_path):
    store = StateStore(tmp_path)
    store.save({"job_id": "pj", "schema_version": 1, "phases": [], "events": [],
                "sent": {}, "requester": {"chat_id": "t"}, "heartbeat": {}})
    assert store.load()["job_id"] == "pj"
    assert json.loads((tmp_path / "state.json").read_text())["job_id"] == "pj"

# Test 13
def test_mystery_bin_refused(tmp_path):
    (tmp_path / "working").mkdir()
    (tmp_path / "working" / "mystery.bin").write_bytes(b"x")
    ok, r = validate_artifact(tmp_path, "working/mystery.bin", _manifest())
    assert not ok
    assert "no validity predicate" in r and "mystery.bin" in r

def test_nine_deliverables_pass(tmp_path):
    import zipfile as zf
    d = tmp_path / "w" / "d"; d.mkdir(parents=True)
    s = tmp_path / "w" / "sp"; s.mkdir(parents=True)
    with zf.ZipFile(str(d / "x.pptx"), "w") as z: z.writestr("a.txt", "x" * 100)
    for fn, sz in [("x.pdf", 51200), ("G.pdf", 51200), ("S.pdf", 20480)]:
        (d / fn).write_bytes(b"%PDF-1.4\n" + b"x" * sz + b"\n%%EOF\n")
    (s / "S.md").write_bytes(b"x" * 2048); (s / "F.md").write_bytes(b"x" * 2048)
    (d / "A.mp3").write_bytes(b"x" * 512000)
    (d / "i.png").write_bytes(_png(100, 100))
    (d / "t.html").write_bytes(b"x" * 10240)
    dl = [{"key": k, "filename": fn, "min_bytes": mb} for k, fn, mb in [
        ("pptx", "x.pptx", 1), ("pdf1", "x.pdf", 51200), ("pdf2", "G.pdf", 51200),
        ("md1", "S.md", 2048), ("pdf3", "S.pdf", 20480), ("md2", "F.md", 2048),
        ("mp3", "A.mp3", 512000), ("png", "i.png", 102400), ("html", "t.html", 10240)]]
    man = _manifest(dl)
    tests = ["w/d/x.pptx", "w/d/x.pdf", "w/d/G.pdf", "w/sp/S.md",
             "w/d/S.pdf", "w/sp/F.md", "w/d/A.mp3", "w/d/i.png", "w/d/t.html"]
    passed = sum(1 for t in tests if validate_artifact(tmp_path, t, man)[0])
    assert passed == 9, f"Expected 9, got {passed}"

# Test 14
def test_render_real_task_id(tmp_path):
    r = tmp_path / "renders"; r.mkdir()
    d = _png(); sha = hashlib.sha256(d).hexdigest()
    (r / "slide-001.png").write_bytes(d)
    (r / "slide-002.png").write_bytes(d)
    ck = tmp_path / "working" / "checkpoints"; ck.mkdir(parents=True)
    ck.joinpath("process_manifest.json").write_text(json.dumps({
        "phases": [{"phase": "render", "slides": [
            {"slide": 1, "taskId": "kie-abc"}, {"slide": 2, "taskId": "native"}]}]}))
    man = _manifest()
    assert validate_artifact(tmp_path, "renders/slide-001.png", man, recorded_sha=sha)[0]
    assert not validate_artifact(tmp_path, "renders/slide-002.png", man, recorded_sha=sha)[0]

def test_render_no_checkpoint(tmp_path):
    r = tmp_path / "renders"; r.mkdir()
    d = _png(); sha = hashlib.sha256(d).hexdigest()
    (r / "slide-001.png").write_bytes(d)
    ok, why = validate_artifact(tmp_path, "renders/slide-001.png", _manifest(), recorded_sha=sha)
    assert not ok, f"No checkpoint should refuse: {why}"


# ============================================================================
# U028 -- atomic checkpointing and per-artifact-type validity predicates,
# for presentation_job/checkpoint.py (the pre-paid-call task-id checkpoint
# used by build_deck.render_slide). Everything below this marker is U028's;
# everything above is U014's, unmodified. No identifier below collides with
# any identifier above (verified by AST walk over both original files before
# merging -- zero overlapping top-level names).
# ============================================================================

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
