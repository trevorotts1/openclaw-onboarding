import json, os, subprocess, sys, time
from pathlib import Path
from unittest import mock
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, utcnow, EXIT_OK, EXIT_GATE_BLOCKED, EXIT_EXECUTOR_FAILED, EXIT_LOCK_HELD
from presentation_job.manifest import Manifest, Phase
from presentation_job.heal import HEAL_CAP_TRANSIENT, HEAL_CAP_REGENERATE, HEAL_CAP_ALT_ROUTE, HEAL_CAP_REGATE, record_heal_event, rung2_regenerate, rung3_alt_route, rung4_regate
from presentation_job.report import Reporter
from presentation_job.phases import Engine

def _mkmanifest(tmp_path, phases=None, executor_cmd="echo ok"):
    manifest_path = tmp_path / "m.json"
    if phases is None: phases = [{"id":"TP","order":1,"owning_role":"t","produces_artifact":["o.txt"],"executor":{"kind":"script","cmd":executor_cmd}}]
    manifest_json = {"manifest_version":25,"phases":phases}
    manifest_path.write_text(json.dumps(manifest_json))
    return Manifest(manifest_path)

def _mkengine(tmp_path, manifest=None, dry_run=False):
    run_dir = tmp_path / "run"; run_dir.mkdir(); store = StateStore(run_dir)
    if manifest is None: manifest = _mkmanifest(tmp_path)
    state = {"schema_version":1,"job_id":"t","run_dir":str(run_dir),"created_at":"2026-01-01T00:00:00+00:00","manifest_path":str(manifest.path),"manifest_version":25,"manifest_sha256":manifest.sha256,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
    store.save(state)
    engine = Engine(run_dir, manifest, store, state, dry_run=dry_run)
    return engine, state

def _mkst(tmp_path, chat_id="t"):
    run_dir = tmp_path / "run"; run_dir.mkdir(); store = StateStore(run_dir)
    state = {"schema_version":1,"job_id":"t","run_dir":str(run_dir),"created_at":"2026-01-01T00:00:00+00:00","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":chat_id},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
    return store, state

class TestHealCaps:
    def test_caps_positive(self):
        assert HEAL_CAP_TRANSIENT == 3
        assert HEAL_CAP_REGENERATE == 2
        assert HEAL_CAP_ALT_ROUTE == 1
        assert HEAL_CAP_REGATE == 1

class TestRung2:
    def test_rung2_capped(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        manifest = _mkmanifest(tmp_path, executor_cmd="exit 99")
        engine, state = _mkengine(tmp_path, manifest)
        phase = manifest.phase("TP")
        rc = rung2_regenerate(engine, phase, "missing o.txt")
        assert rc != EXIT_OK
        he = engine._phase_state("TP").get("heal_events",[]); assert len(he) == HEAL_CAP_REGENERATE
        for e in he: assert e["rung"] == 2

    def test_rung2_succeeds(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        run_dir = tmp_path / "run"; run_dir.mkdir(); (run_dir / "o.txt").write_text("h")
        manifest = _mkmanifest(tmp_path, executor_cmd="echo ok")
        engine, state = _mkengine(tmp_path, manifest)
        assert rung2_regenerate(engine, manifest.phase("TP"), "missing o.txt") == EXIT_OK

    def test_rung2_blocks_after_cap(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        manifest = _mkmanifest(tmp_path, executor_cmd="exit 1")
        engine, state = _mkengine(tmp_path, manifest)
        assert rung2_regenerate(engine, manifest.phase("TP"), "missing o.txt") == EXIT_EXECUTOR_FAILED

class TestRung3:
    def test_rung3_noop(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        manifest = _mkmanifest(tmp_path)
        engine, state = _mkengine(tmp_path, manifest)
        assert rung3_alt_route(engine, manifest.phase("TP")) == EXIT_EXECUTOR_FAILED

    def test_rung3_executes_alt_cmd(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        run_dir = tmp_path / "run"; run_dir.mkdir(); (run_dir / "o.txt").write_text("h")
        manifest = _mkmanifest(tmp_path, phases=[{"id":"TP","order":1,"owning_role":"t","produces_artifact":["o.txt"],"executor":{"kind":"script","cmd":"exit 1","alt_cmd":"echo ok"}}])
        engine, state = _mkengine(tmp_path, manifest)
        assert rung3_alt_route(engine, manifest.phase("TP")) == EXIT_OK

class TestRung4:
    def test_rung4_reevaluates(self, tmp_path):
        run_dir = tmp_path / "run"; run_dir.mkdir()
        (run_dir / "working" / "deliverables").mkdir(parents=True)
        (run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md").write_text("x"*4096)
        (run_dir / "working" / "deliverables" / "presenter-teleprompter.html").write_text("y"*20480)
        (run_dir / "working" / "prompts").mkdir(parents=True)
        (run_dir / "working" / "prompts" / "slide-1.txt").write_text("A"*15000)
        (run_dir / "renders").mkdir(parents=True)
        (run_dir / "renders" / "slide-1.ocr.json").write_text('{"checked":true,"matched":true}')
        (run_dir / "working" / "qc").mkdir(parents=True)
        (run_dir / "working" / "qc" / "final_qc_report.json").write_text('{"average":9.0}')
        (run_dir / "working" / "checkpoints").mkdir(parents=True)
        (run_dir / "working" / "checkpoints" / "media_library.json").write_text('{"media_ids":["abc"]}')
        store = StateStore(run_dir)
        state = {"schema_version":1,"job_id":"t","run_dir":str(run_dir),"created_at":"","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
        store.save(state)
        mp = tmp_path / "m.json"; mp.write_text('{"manifest_version":25,"phases":[{"id":"P0A-INTAKE","order":1,"owning_role":"t","produces_artifact":["o.txt"]}]}')
        engine = Engine(run_dir, Manifest(mp), store, state, dry_run=False)
        result = rung4_regate(engine, ["script"])
        assert "script" in result; assert result["script"]["state"] == "pass"
        assert len([e for e in engine._phase_state("CLOSE").get("heal_events",[]) if e["rung"]==4]) == 1

class TestSweep:
    def test_sweep_drains(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        run_dir = tmp_path / "run"; run_dir.mkdir(); store = StateStore(run_dir)
        state = {"schema_version":1,"job_id":"t","run_dir":str(run_dir),"created_at":"","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[{"chat_id":"t","kind":"progress","message":"m1"},{"chat_id":"t","kind":"progress","message":"m2"},{"chat_id":"t","kind":"done","message":"m3"}],"heartbeat":{},"terminal":None}
        store.save(state)
        from presentation_job.__main__ import cmd_sweep_undeliverable
        class A: run_dir = run_dir
        rc = cmd_sweep_undeliverable(A()); assert rc == 0
        st = store.load(); assert len(st.get("undeliverable",[])) == 0
        assert isinstance(st.get("sent",{}).get("progress"),dict)
        assert st["sent"]["progress"]["count"]==2

    def test_sweep_parser(self, tmp_path):
        from presentation_job.__main__ import build_parser
        args = build_parser().parse_args(["--sweep-undeliverable","--run-dir",str(tmp_path)])
        assert args.sweep_undeliverable is True

class TestRecordHeal:
    def test_record_appends(self, tmp_path):
        store, state = _mkst(tmp_path)
        pd = {"id":"TP"}; record_heal_event(state,"TP",store,pd,rung=1,attempt=1,reason="t")
        assert len(pd.get("heal_events",[])) == 1; assert pd["heal_events"][0]["rung"]==1

    def test_multiple_rungs(self, tmp_path):
        store, state = _mkst(tmp_path)
        pd = {"id":"TP"}
        record_heal_event(state,"TP",store,pd,rung=1,attempt=1,reason="a")
        record_heal_event(state,"TP",store,pd,rung=2,attempt=1,reason="b")
        record_heal_event(state,"TP",store,pd,rung=4,attempt=1,reason="c")
        assert len(pd.get("heal_events",[]))==3
        assert sorted(e["rung"] for e in pd["heal_events"]) == [1,2,4]
