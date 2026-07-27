"""Tests for U014 checkpoint re-validation (14 tests)."""
import hashlib, json, struct, time, zipfile, zlib
from pathlib import Path
from unittest.mock import patch
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from presentation_job.artifacts import (
    validate_text, validate_image, validate_pdf, validate_pptx,
    validate_artifact, render_manifest_for, _BAD_TASK_IDS,
)

def _png(w=1, h=1):
    def ch(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", ihdr)
            + ch(b"IDAT", zlib.compress(b"\x00" + b"\x00" * (w * 4 * h)))
            + ch(b"IEND", b""))

def _mk_manifest(dels=None):
    class M:
        def __init__(self, d): self.deliverables = d
    if dels is None:
        dels = [
            {"filename": "{deck_slug}-FINAL.pptx", "min_bytes": 1048576},
            {"filename": "{deck_slug}-FINAL.pdf", "min_bytes": 51200},
            {"filename": "PRESENTER-GUIDE.pdf", "min_bytes": 51200},
            {"filename": "PRESENTERS-SPEECH.md", "min_bytes": 2048},
            {"filename": "PRESENTERS-SPEECH.pdf", "min_bytes": 20480},
            {"filename": "PRESENTERS-SPEECH-FISH-TAGGED.md", "min_bytes": 2048},
            {"filename": "PRESENTER-AUDIO.mp3", "min_bytes": 512000},
            {"filename": "infographic.png", "min_bytes": 102400},
            {"filename": "presenter-teleprompter.html", "min_bytes": 10240},
        ]
    return M(dels)


# ===== 1. validate_text =====
class TestValidateText:
    def test_accepts_floor(self, tmp_path):
        f = tmp_path / "t.md"; f.write_bytes(b"x" * 2048)
        ok, _ = validate_text(f, 2048)
        assert ok is True

    def test_rejects_one_byte_under(self, tmp_path):
        f = tmp_path / "s.md"; f.write_bytes(b"x" * 2047)
        ok, reason = validate_text(f, 2048)
        assert ok is False
        assert "2047" in reason or "below floor" in reason.lower()

    def test_rejects_nonexistent(self, tmp_path):
        ok, _ = validate_text(tmp_path / "nope", 1)
        assert ok is False


# ===== 2. validate_image =====
class TestValidateImage:
    def test_accepts_whole_png(self, tmp_path):
        f = tmp_path / "g.png"; f.write_bytes(_png())
        ok, _ = validate_image(f)
        assert ok is True

    def test_rejects_truncated(self, tmp_path):
        f = tmp_path / "b.png"; f.write_bytes(_png()[:-12])
        ok, reason = validate_image(f)
        assert ok is False
        assert "iend" in reason.lower() or "truncated" in reason.lower()

    def test_rejects_sha_mismatch(self, tmp_path):
        f = tmp_path / "g.png"; f.write_bytes(_png())
        ok, reason = validate_image(f, recorded_sha="deadbeef")
        assert ok is False
        assert "sha256" in reason.lower()


# ===== 3. validate_pptx =====
class TestValidatePptx:
    def test_rejects_non_zip_pk(self, tmp_path):
        f = tmp_path / "bad.pptx"; f.write_bytes(b"PK\x03\x04" + b"x" * 200)
        ok, reason = validate_pptx(f, 30)
        assert ok is False
        assert "zip" in reason.lower() or "not a readable" in reason.lower()

    def test_accepts_valid_zip(self, tmp_path):
        f = tmp_path / "good.pptx"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("[Content_Types].xml", "<Types/>")
        ok, _ = validate_pptx(f, 30)
        assert ok is True


# ===== 4. validate_artifact dispatcher =====
class TestDispatcher:
    def test_floor_10240(self, tmp_path):
        m = _mk_manifest()
        f = tmp_path / "presenter-teleprompter.html"; f.write_bytes(b"x" * 10240)
        ok, _ = validate_artifact(tmp_path, "presenter-teleprompter.html", m)
        assert ok is True

    def test_floor_10240_under(self, tmp_path):
        m = _mk_manifest()
        f = tmp_path / "presenter-teleprompter.html"; f.write_bytes(b"x" * 10239)
        ok, _ = validate_artifact(tmp_path, "presenter-teleprompter.html", m)
        assert ok is False

    def test_floor_flip(self, tmp_path):
        sp = tmp_path / "PRESENTERS-SPEECH.md"; sp.write_bytes(b"x" * 2048)
        m1 = _mk_manifest()
        ok, _ = validate_artifact(tmp_path, "PRESENTERS-SPEECH.md", m1)
        assert ok is True
        m2 = _mk_manifest([{"filename": "PRESENTERS-SPEECH.md", "min_bytes": 4096}])
        ok, reason = validate_artifact(tmp_path, "PRESENTERS-SPEECH.md", m2)
        assert ok is False
        assert "4096" in reason


# ===== 5-8. Resume revalidation (engine) =====
class TestResumeRevalidation:
    def _eng(self, run_dir, phases, dry=True):
        from presentation_job.manifest import Manifest
        from presentation_job.state import StateStore, utcnow
        from presentation_job.phases import Engine

        mfp = run_dir / "_m.json"
        mfp.write_text(json.dumps({
            "manifest_version": 25,
            "phases": [{"id": "P9-SPEECH", "order": 8.5,
                        "owning_role": "test",
                        "produces_artifact": ["working/presenter-speech/PRESENTERS-SPEECH.md"],
                        "client_report": {}, "executor": {"kind": "script", "cmd": "echo ok"}}],
            "deliverables_required": [{"filename": "PRESENTERS-SPEECH.md", "min_bytes": 2048}],
            "autofails": [],
        }))
        manifest = Manifest(mfp)
        store = StateStore(run_dir)
        state = {"schema_version": 1, "job_id": "pj", "run_dir": str(run_dir),
                 "created_at": utcnow(), "manifest_path": str(mfp),
                 "manifest_version": 25, "manifest_sha256": manifest.sha256,
                 "presentation_type": "from_scratch", "requester": {"chat_id": "t"},
                 "intake": {}, "current_phase": None, "phases": phases,
                 "gates": {}, "waivers": [], "events": [], "sent": {},
                 "undeliverable": [], "heartbeat": {}, "terminal": None}
        store.save(state)
        return Engine(run_dir, manifest, store, store.load(), dry_run=dry)

    def _ps(self, pid="P9-SPEECH", status="done", arts=None, sha=None):
        return {"id": pid, "status": status, "artifacts": arts or [],
                "sha256": sha or {}, "attempts": 1, "heal_events": [],
                "attested_at": "2026-07-25T00:00:00Z"}

    def _run_phase_capture(self, eng, pid):
        from io import StringIO
        import sys
        old = sys.stdout
        buf = StringIO()
        try:
            sys.stdout = buf
            rc = eng.run_phase(eng.manifest.phase(pid))
        finally:
            sys.stdout = old
        return rc, buf.getvalue()

    def test_skip_valid(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        sp = rd / "working" / "presenter-speech"; sp.mkdir(parents=True)
        sf = sp / "PRESENTERS-SPEECH.md"; sf.write_text("# s\n" + "z" * 2500)
        sha = hashlib.sha256(sf.read_bytes()).hexdigest()
        eng = self._eng(rd, [self._ps(arts=["working/presenter-speech/PRESENTERS-SPEECH.md"],
                                       sha={"working/presenter-speech/PRESENTERS-SPEECH.md": sha})])
        rc, out = self._run_phase_capture(eng, "P9-SPEECH")
        assert rc == 0
        assert "SKIP" in out

    def test_rerun_deleted(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        eng = self._eng(rd, [self._ps(arts=["working/presenter-speech/PRESENTERS-SPEECH.md"],
                                       sha={"working/presenter-speech/PRESENTERS-SPEECH.md": "deadbeef"})])
        rc, out = self._run_phase_capture(eng, "P9-SPEECH")
        assert rc == 0
        assert "DRY-RUN" in out

    def test_rerun_truncated(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        sp = rd / "working" / "presenter-speech"; sp.mkdir(parents=True)
        sf = sp / "PRESENTERS-SPEECH.md"; sf.write_text("# short")
        sha = hashlib.sha256(sf.read_bytes()).hexdigest()
        eng = self._eng(rd, [self._ps(arts=["working/presenter-speech/PRESENTERS-SPEECH.md"],
                                       sha={"working/presenter-speech/PRESENTERS-SPEECH.md": sha})])
        rc, out = self._run_phase_capture(eng, "P9-SPEECH")
        assert rc == 0
        assert "DRY-RUN" in out

    def test_rerun_hash(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        sp = rd / "working" / "presenter-speech"; sp.mkdir(parents=True)
        sf = sp / "PRESENTERS-SPEECH.md"; sf.write_text("# s\n" + "q" * 2500)
        eng = self._eng(rd, [self._ps(arts=["working/presenter-speech/PRESENTERS-SPEECH.md"],
                                       sha={"working/presenter-speech/PRESENTERS-SPEECH.md": "deadbeef"})])
        rc, out = self._run_phase_capture(eng, "P9-SPEECH")
        assert rc == 0
        assert "DRY-RUN" in out

    def test_rerun_empty_artifacts(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        eng = self._eng(rd, [self._ps(arts=[], sha={})])
        rc, out = self._run_phase_capture(eng, "P9-SPEECH")
        assert rc == 0
        assert "DRY-RUN" in out


# ===== 9. Agent poll heartbeat =====
class TestAgentHeartbeat:
    def test_checkpoint_during_poll(self, tmp_path):
        from presentation_job.manifest import Phase, PHASE_BUDGET_MINUTES
        from presentation_job.state import StateStore, utcnow
        from presentation_job.phases import Engine

        rd = tmp_path / "run"; rd.mkdir()
        store = StateStore(rd)
        state = {"schema_version": 1, "job_id": "pj", "run_dir": str(rd),
                 "created_at": utcnow(), "manifest_path": "/d", "manifest_version": 25,
                 "manifest_sha256": "a", "presentation_type": "from_scratch",
                 "requester": {"chat_id": "t"}, "intake": {}, "current_phase": None,
                 "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
                 "undeliverable": [], "heartbeat": {}, "terminal": None}
        store.save(state)
        m = _mk_manifest()
        phase = Phase(id="TA", order=1.0, owning_role="t", produces_artifact=["t.out"],
                      executor_kind="agent", executor_cmd=None, verifier=None,
                      client_report={}, heartbeat_minutes=10, long_running=False)
        PHASE_BUDGET_MINUTES["TA"] = 1
        eng = Engine(rd, m, store, store.load(), dry_run=False)
        (rd / "t.out").write_text("done")
        rc = eng._run_agent_phase(phase)
        assert rc == 0
        del PHASE_BUDGET_MINUTES["TA"]


# ===== 10-11. _block messages =====
class TestBlockMessages:
    def _eng(self, rd, phases):
        from presentation_job.manifest import Manifest, Phase, PHASE_BUDGET_MINUTES
        from presentation_job.state import StateStore, utcnow
        from presentation_job.phases import Engine

        mfp = rd / "_m.json"
        mfp.write_text(json.dumps({"manifest_version": 25, "phases": [],
                                    "deliverables_required": [{"filename": "PRESENTERS-SPEECH.pdf", "min_bytes": 20480}],
                                    "autofails": []}))
        manifest = _mk_manifest()
        store = StateStore(rd)
        state = {"schema_version": 1, "job_id": "pj", "run_dir": str(rd),
                 "created_at": utcnow(), "manifest_path": str(mfp),
                 "manifest_version": 25, "manifest_sha256": manifest.sha256,
                 "presentation_type": "from_scratch", "requester": {"chat_id": "t"},
                 "intake": {}, "current_phase": None, "phases": phases,
                 "gates": {}, "waivers": [], "events": [], "sent": {},
                 "undeliverable": [], "heartbeat": {}, "terminal": None}
        store.save(state)
        return Engine(rd, manifest, store, store.load(), dry_run=True)

    def test_missing_says_rebuilt(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        ps = {"id": "P9-SPEECH", "status": "done",
              "artifacts": ["working/deliverables/PRESENTERS-SPEECH.pdf"],
              "sha256": {"working/deliverables/PRESENTERS-SPEECH.pdf": "deadbeef"},
              "attempts": 1, "heal_events": [], "attested_at": "2026-07-25T00:00:00Z"}
        eng = self._eng(rd, [ps])
        from presentation_job.manifest import Phase, PHASE_BUDGET_MINUTES
        PHASE_BUDGET_MINUTES["TBM"] = 1
        phase = Phase(id="TBM", order=99, owning_role="t", produces_artifact=["t.out"],
                      executor_kind="agent", executor_cmd=None, verifier=None, client_report={})
        eng._block(phase, "test missing")
        st = eng.store.load()
        msgs = [e for e in st.get("events", []) if e.get("kind") == "message_to_requester"]
        last = msgs[-1]["body"] if msgs else ""
        assert "will be rebuilt" in last
        del PHASE_BUDGET_MINUTES["TBM"]

    def test_present_says_nothing_lost(self, tmp_path):
        rd = tmp_path / "run"; rd.mkdir()
        dl = rd / "working" / "deliverables"; dl.mkdir(parents=True)
        pdf = dl / "PRESENTERS-SPEECH.pdf"
        pdf.write_bytes(b"%PDF-\n" + b"x" * 20500 + b"\n%%EOF")
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        ps = {"id": "P9-SPEECH", "status": "done",
              "artifacts": ["working/deliverables/PRESENTERS-SPEECH.pdf"],
              "sha256": {"working/deliverables/PRESENTERS-SPEECH.pdf": sha},
              "attempts": 1, "heal_events": [], "attested_at": "2026-07-25T00:00:00Z"}
        eng = self._eng(rd, [ps])
        from presentation_job.manifest import Phase, PHASE_BUDGET_MINUTES
        PHASE_BUDGET_MINUTES["TBP"] = 1
        phase = Phase(id="TBP", order=99, owning_role="t", produces_artifact=["t.out"],
                      executor_kind="agent", executor_cmd=None, verifier=None, client_report={})
        eng._block(phase, "test ok")
        st = eng.store.load()
        msgs = [e for e in st.get("events", []) if e.get("kind") == "message_to_requester"]
        last = msgs[-1]["body"] if msgs else ""
        assert "nothing is lost" in last
        del PHASE_BUDGET_MINUTES["TBP"]


# ===== 12. Atomicity =====
class TestAtomicity:
    def test_no_temp_left(self, tmp_path):
        from presentation_job.state import StateStore, utcnow
        s = StateStore(tmp_path)
        s.save({"schema_version": 1, "job_id": "pj", "run_dir": str(tmp_path),
                "created_at": utcnow(), "manifest_path": "/d", "manifest_version": 25,
                "manifest_sha256": "a", "presentation_type": "from_scratch",
                "requester": {"chat_id": "t"}, "intake": {}, "current_phase": None,
                "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
                "undeliverable": [], "heartbeat": {}, "terminal": None})
        assert len(list(tmp_path.glob(".state-*.tmp"))) == 0

    def test_state_parses(self, tmp_path):
        from presentation_job.state import StateStore, utcnow
        s = StateStore(tmp_path)
        s.save({"schema_version": 1, "job_id": "pj", "run_dir": str(tmp_path),
                "created_at": utcnow(), "manifest_path": "/d", "manifest_version": 25,
                "manifest_sha256": "a", "presentation_type": "from_scratch",
                "requester": {"chat_id": "t"}, "intake": {}, "current_phase": None,
                "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
                "undeliverable": [], "heartbeat": {}, "terminal": None})
        assert s.load()["job_id"] == "pj"

    def test_interrupted_save(self, tmp_path):
        from presentation_job.state import StateStore, utcnow
        s = StateStore(tmp_path)
        v1 = {"schema_version": 1, "job_id": "pj_orig", "run_dir": str(tmp_path),
              "created_at": utcnow(), "manifest_path": "/d", "manifest_version": 25,
              "manifest_sha256": "a", "presentation_type": "from_scratch",
              "requester": {"chat_id": "t"}, "intake": {}, "current_phase": None,
              "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
              "undeliverable": [], "heartbeat": {}, "terminal": None}
        s.save(v1)
        assert s.load()["job_id"] == "pj_orig"
        v2 = dict(v1); v2["job_id"] = "pj_bad"; v2["bad"] = object()
        try: s.save(v2)
        except (TypeError, Exception): pass
        assert s.load()["job_id"] == "pj_orig"
        assert len(list(tmp_path.glob(".state-*.tmp"))) == 0


# ===== 13. Unknown refusal =====
class TestRefusal:
    def test_unknown_refused(self, tmp_path):
        (tmp_path / "working").mkdir()
        (tmp_path / "working" / "mystery.bin").write_bytes(b"x")
        m = _mk_manifest()
        ok, reason = validate_artifact(tmp_path, "working/mystery.bin", m)
        assert ok is False
        assert "no validity predicate for working/mystery.bin" in reason

    def test_nine_deliverables(self, tmp_path):
        m = _mk_manifest()
        cases = [
            ("{deck_slug}-FINAL.pptx", 1048576, "pptx"),
            ("{deck_slug}-FINAL.pdf", 51200, "pdf"),
            ("PRESENTER-GUIDE.pdf", 51200, "pdf"),
            ("PRESENTERS-SPEECH.md", 2048, "md"),
            ("PRESENTERS-SPEECH.pdf", 20480, "pdf"),
            ("PRESENTERS-SPEECH-FISH-TAGGED.md", 2048, "md"),
            ("PRESENTER-AUDIO.mp3", 512000, "mp3"),
            ("infographic.png", 102400, "png"),
            ("presenter-teleprompter.html", 10240, "html"),
        ]
        for fn, fl, kd in cases:
            p = tmp_path / fn
            if kd == "pptx":
                with zipfile.ZipFile(p, "w") as zf:
                    zf.writestr("[Content_Types].xml", "<Types/>")
                cur = p.stat().st_size
                if cur < fl: p.write_bytes(p.read_bytes() + b"\x00" * (fl - cur))
            elif kd == "pdf":
                p.write_bytes(b"%PDF-\n" + b"x" * max(0, fl - 15) + b"\n%%EOF")
            elif kd == "png":
                p.write_bytes(_png(10, 10))
                cur = p.stat().st_size
                if cur < fl: p.write_bytes(p.read_bytes() + b"\x00" * (fl - cur))
            else:
                p.write_bytes(b"x" * fl)
            ok, reason = validate_artifact(tmp_path, fn, m)
            assert ok, f"{fn}: {reason}"


# ===== 14. P4-RENDER routing =====
class TestRenderFamily:
    def test_real_task_id(self, tmp_path):
        r = tmp_path / "renders"; r.mkdir()
        data = _png()
        (r / "slide-001.png").write_bytes(data)
        ck = tmp_path / "working" / "checkpoints"; ck.mkdir(parents=True)
        (ck / "process_manifest.json").write_text(json.dumps({"phases": [
            {"phase": "render", "slides": [{"slide": 1, "taskId": "kie-abc123"}, {"slide": 2, "taskId": "native"}]}]}))
        sha = hashlib.sha256(data).hexdigest()
        m = _mk_manifest()
        ok, reason = validate_artifact(tmp_path, "renders/slide-001.png", m, recorded_sha=sha)
        assert ok is True, f"slide 1 should pass: {reason}"

    def test_bad_task_id(self, tmp_path):
        r = tmp_path / "renders"; r.mkdir()
        data = _png()
        (r / "slide-002.png").write_bytes(data)
        ck = tmp_path / "working" / "checkpoints"; ck.mkdir(parents=True)
        (ck / "process_manifest.json").write_text(json.dumps({"phases": [
            {"phase": "render", "slides": [{"slide": 1, "taskId": "kie-abc123"}, {"slide": 2, "taskId": "native"}]}]}))
        sha = hashlib.sha256(data).hexdigest()
        m = _mk_manifest()
        ok, reason = validate_artifact(tmp_path, "renders/slide-002.png", m, recorded_sha=sha)
        assert ok is False
        assert "task id" in reason.lower() or "native" in reason

    def test_no_checkpoint(self, tmp_path):
        r = tmp_path / "renders"; r.mkdir()
        data = _png()
        (r / "slide-001.png").write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        m = _mk_manifest()
        ok, reason = validate_artifact(tmp_path, "renders/slide-001.png", m, recorded_sha=sha)
        assert ok is False, f"no checkpoint should refuse: {ok!r} {reason!r}"

    def test_bad_task_ids_equal(self):
        try:
            from delivery_gate import _BAD_TASK_IDS as up
        except ImportError:
            up = frozenset({None, "", "native", "placeholder", "none", "null", "n/a"})
        assert _BAD_TASK_IDS == up

    def test_dispatcher_routes_render(self, tmp_path):
        r = tmp_path / "renders"; r.mkdir()
        data = _png()
        (r / "slide-001.png").write_bytes(data)
        ck = tmp_path / "working" / "checkpoints"; ck.mkdir(parents=True)
        (ck / "process_manifest.json").write_text(json.dumps({"phases": [
            {"phase": "render", "slides": [{"slide": 1, "taskId": "kie-abc123"}]}]}))
        sha = hashlib.sha256(data).hexdigest()
        m = _mk_manifest()
        ok, reason = validate_artifact(tmp_path, "renders/slide-001.png", m, recorded_sha=sha)
        assert ok is True, f"render branch should route via validate_image: {reason}"
