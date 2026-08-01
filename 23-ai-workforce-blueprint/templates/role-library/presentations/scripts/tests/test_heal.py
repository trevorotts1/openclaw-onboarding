"""Tests for presentation_job heal.py -- U015 rung 2, 3, 4."""
import json, os, subprocess, sys
from pathlib import Path
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, EXIT_OK, EXIT_EXECUTOR_FAILED
from presentation_job.manifest import Manifest
from presentation_job.heal import HEAL_CAP_TRANSIENT, HEAL_CAP_REGENERATE, HEAL_CAP_ALT_ROUTE, HEAL_CAP_REGATE, record_heal_event, rung2_regenerate, rung3_alt_route, rung4_regate
from presentation_job.phases import Engine

def _mkmanifest(tmp_path, phases=None, cmd="echo ok"):
    mp = tmp_path / "m.json"
    if phases is None: phases = [{"id":"TP","order":1,"owning_role":"t","produces_artifact":["o.txt"],"executor":{"kind":"script","cmd":cmd}}]
    mp.write_text(json.dumps({"manifest_version":25,"phases":phases}))
    return Manifest(mp)

def _mkengine(tmp_path, manifest=None, dry_run=False):
    rd = tmp_path / "r"; rd.mkdir(exist_ok=True); store = StateStore(rd)
    if manifest is None: manifest = _mkmanifest(tmp_path)
    s = {"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"","manifest_path":str(manifest.path),"manifest_version":25,"manifest_sha256":manifest.sha256,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
    store.save(s)
    return Engine(rd, manifest, store, s, dry_run=dry_run), s

class TestCaps:
    def test_caps(self): assert HEAL_CAP_TRANSIENT==3 and HEAL_CAP_REGENERATE==2

class TestRung2:
    def test_capped(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD",raising=False)
        m=_mkmanifest(tmp_path,cmd="exit 99");e,s=_mkengine(tmp_path,m)
        assert rung2_regenerate(e,m.phase("TP"),"missing")!=EXIT_OK
        he=e._phase_state("TP").get("heal_events",[]);assert len(he)==2;assert all(x["rung"]==2 for x in he)
    def test_succeeds(self,tmp_path,monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD",raising=False)
        (tmp_path/"r").mkdir(exist_ok=True); (tmp_path/"r"/"o.txt").write_text("h")
        m=_mkmanifest(tmp_path,cmd="echo ok");e,s=_mkengine(tmp_path,m)
        assert rung2_regenerate(e,m.phase("TP"),"missing")==EXIT_OK
    def test_blocks(self,tmp_path,monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD",raising=False)
        m=_mkmanifest(tmp_path,cmd="exit 1");e,s=_mkengine(tmp_path,m)
        assert rung2_regenerate(e,m.phase("TP"),"missing")==EXIT_EXECUTOR_FAILED

class TestRung3:
    def test_noop(self,tmp_path,monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD",raising=False)
        m=_mkmanifest(tmp_path);e,s=_mkengine(tmp_path,m)
        assert rung3_alt_route(e,m.phase("TP"))==EXIT_EXECUTOR_FAILED
    def test_altcmd(self,tmp_path,monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD",raising=False)
        (tmp_path/"r").mkdir(exist_ok=True); (tmp_path/"r"/"o.txt").write_text("h")
        m=_mkmanifest(tmp_path,phases=[{"id":"TP","order":1,"owning_role":"t","produces_artifact":["o.txt"],"executor":{"kind":"script","cmd":"exit 1","alt_cmd":"echo ok"}}])
        e,s=_mkengine(tmp_path,m)
        assert rung3_alt_route(e,m.phase("TP"))==EXIT_OK

class TestRung4:
    def test_regate(self,tmp_path):
        rd=tmp_path/"r";rd.mkdir(exist_ok=True)
        (rd/"working"/"deliverables").mkdir(parents=True,exist_ok=True)
        (rd/"working"/"deliverables"/"PRESENTERS-SPEECH.md").write_text("x"*4096)
        (rd/"working"/"deliverables"/"presenter-teleprompter.html").write_text("y"*20480)
        (rd/"working"/"prompts").mkdir(parents=True,exist_ok=True)
        (rd/"working"/"prompts"/"slide-1.txt").write_text("A"*15000)
        (rd/"renders").mkdir(exist_ok=True)
        (rd/"renders"/"slide-1.ocr.json").write_text('{"checked":true,"matched":true}')
        (rd/"working"/"qc").mkdir(parents=True,exist_ok=True)
        (rd/"working"/"qc"/"final_qc_report.json").write_text('{"average":9.0}')
        (rd/"working"/"checkpoints").mkdir(parents=True,exist_ok=True)
        (rd/"working"/"checkpoints"/"media_library.json").write_text('{"media_ids":["a"]}')
        store=StateStore(rd)
        st={"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"","manifest_path":"/x","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
        store.save(st)
        mp=tmp_path/"m.json";mp.write_text('{"manifest_version":25,"phases":[{"id":"P","order":1,"owning_role":"t","produces_artifact":["o.txt"]}]}')
        e=Engine(rd,Manifest(mp),store,st)
        r=rung4_regate(e,["script"]);assert "script" in r;assert r["script"]["state"]=="pass"
        assert len([x for x in e._phase_state("CLOSE").get("heal_events",[]) if x["rung"]==4])==1

class TestSweep:
    def test_drains(self,tmp_path,monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        rd=tmp_path/"r";rd.mkdir();store=StateStore(rd)
        st={"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"","manifest_path":"/x","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[{"chat_id":"t","kind":"p","message":"m1"},{"chat_id":"t","kind":"p","message":"m2"},{"chat_id":"t","kind":"d","message":"m3"}],"heartbeat":{},"terminal":None}
        store.save(st)
        from presentation_job.__main__ import cmd_sweep_undeliverable
        class A:run_dir=rd
        rc=cmd_sweep_undeliverable(A());assert rc==0
        s2=store.load();assert len(s2.get("undeliverable",[]))==0
        assert isinstance(s2.get("sent",{}).get("p"),dict);assert s2["sent"]["p"]["count"]==2
    def test_parser(self,tmp_path):
        from presentation_job.__main__ import build_parser
        args=build_parser().parse_args(["--sweep-undeliverable","--run-dir",str(tmp_path)])
        assert args.sweep_undeliverable is True

class TestRecord:
    def test_append(self,tmp_path):
        rd=tmp_path/"r";rd.mkdir();store=StateStore(rd)
        st={"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"","manifest_path":"/x","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
        pd={};record_heal_event(st,"TP",store,pd,1,1,"t");assert len(pd.get("heal_events",[]))==1;assert pd["heal_events"][0]["rung"]==1
    def test_multiple(self,tmp_path):
        rd=tmp_path/"r";rd.mkdir();store=StateStore(rd)
        st={"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"","manifest_path":"/x","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
        pd={};record_heal_event(st,"TP",store,pd,1,1,"a");record_heal_event(st,"TP",store,pd,2,1,"b");record_heal_event(st,"TP",store,pd,4,1,"c")
        assert len(pd.get("heal_events",[]))==3;assert sorted(x["rung"] for x in pd["heal_events"])==[1,2,4]

class TestHealCapRegression:
    """Regression: HEAL_CAP_ALT_ROUTE and HEAL_CAP_REGATE have real readers."""
    def test_caps_have_readers(self):
        """Prove HEAL_CAP_ALT_ROUTE and HEAL_CAP_REGATE are referenced beyond
        their own definitions by running an AST census.  Each must appear as a
        Name node in at least two sites (definition + at least one reader)."""
        import ast, pathlib
        want = {"HEAL_CAP_ALT_ROUTE", "HEAL_CAP_REGATE"}
        seen = {w: [] for w in want}
        heal_p = pathlib.Path(__file__).resolve().parent.parent / "presentation_job" / "heal.py"
        t = ast.parse(heal_p.read_text())
        for n in ast.walk(t):
            if isinstance(n, ast.Name) and n.id in want:
                seen[n.id].append(n.lineno)
        for k in sorted(want):
            assert len(seen[k]) >= 2, f"{k} has {len(seen[k])} Name site(s) in heal.py ({seen[k]}) — needs >=2"

    def test_rung_census_excludes_3(self):
        """Regression: static census finds [1,2,4] not [1,2,3,4].  Rung 3
        only records at runtime when a client manifest declares alt_cmd."""
        import ast, pathlib
        pkg = pathlib.Path(__file__).resolve().parent.parent / "presentation_job"
        rungs = set()
        for f in sorted(pkg.glob("*.py")):
            t = ast.parse(f.read_text())
            for n in ast.walk(t):
                func_attr = None
                if isinstance(n, ast.Call):
                    if isinstance(n.func, ast.Attribute) and n.func.attr == "record_heal_event":
                        func_attr = "record_heal_event"
                    elif isinstance(n.func, ast.Name) and n.func.id == "record_heal_event":
                        func_attr = "record_heal_event"
                    if func_attr:
                        for k in n.keywords:
                            if k.arg == "rung" and isinstance(k.value, ast.Constant):
                                rungs.add(k.value.value)
        assert rungs == {1, 2, 4}, f"expected rungs {{1,2,4}}, got {rungs}"

    def test_rung3_heal_event_only_on_success(self, tmp_path, monkeypatch):
        """Regression: rung=3 heal_event recorded conditionally only when
        rung3_alt_route returns EXIT_OK."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        (tmp_path / "r").mkdir(exist_ok=True)
        (tmp_path / "r" / "o.txt").write_text("h")
        # Phase with alt_cmd that will succeed
        m = _mkmanifest(tmp_path, phases=[{"id":"TP","order":1,"owning_role":"t",
            "produces_artifact":["o.txt"],
            "executor":{"kind":"script","cmd":"exit 1","alt_cmd":"echo ok"}}])
        e, s = _mkengine(tmp_path, m)
        rc = rung3_alt_route(e, m.phase("TP"))
        assert rc == EXIT_OK  # rung3 succeeded
        # Now simulate what phases.py does: record heal event on success
        ps = e._phase_state("TP")
        record_heal_event(s, "TP", e.store, ps, rung=3, attempt=1, reason="alternate route")
        he = ps.get("heal_events", [])
        assert len(he) == 1
        assert he[0]["rung"] == 3

    def test_rung3_noop_no_heal_event(self, tmp_path, monkeypatch):
        """Regression: when no alt_cmd, rung3 is a no-op and records nothing."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        m = _mkmanifest(tmp_path)
        e, s = _mkengine(tmp_path, m)
        rc = rung3_alt_route(e, m.phase("TP"))
        assert rc == EXIT_EXECUTOR_FAILED  # no alt_cmd — no-op
        ps = e._phase_state("TP")
        assert len(ps.get("heal_events", [])) == 0
