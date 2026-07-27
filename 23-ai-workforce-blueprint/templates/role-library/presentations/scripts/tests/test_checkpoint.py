"""Tests for checkpoint resume + artifact validation (U014)."""
import hashlib, json, struct, sys, zlib
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
