"""Tests for presentation_job heal.py -- U015 rung 2, 3, 4."""
import json, os, subprocess, sys
from pathlib import Path
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, EXIT_OK, EXIT_EXECUTOR_FAILED
from presentation_job.manifest import Manifest
from presentation_job.heal import HEAL_CAP_TRANSIENT, HEAL_CAP_REGENERATE, record_heal_event, rung2_regenerate, rung3_alt_route, rung4_regate
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

def _mkengine_at(tmp_path, run_dir, manifest, dry_run=False):
    """Like _mkengine, but the caller supplies the run_dir Path (which may be
    an adversarial name for shell-metacharacter injection tests)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(run_dir)
    s = {"schema_version":1,"job_id":"t","run_dir":str(run_dir),"created_at":"","manifest_path":str(manifest.path),"manifest_version":25,"manifest_sha256":manifest.sha256,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
    store.save(s)
    return Engine(run_dir, manifest, store, s, dry_run=dry_run), s

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

    def test_injection_blocked(self, tmp_path, monkeypatch):
        """U069 bypass #3: __main__.cmd_sweep_undeliverable held its own
        hand-rolled subprocess.run(cmd, shell=True, ...), independent of both
        report.dispatch() and Reporter._dispatch(). It now routes through
        report.dispatch() -- prove a $(touch ...) payload in
        PRESENTATION_NOTIFY_CMD never fires while the queued message still
        drains mechanically."""
        sentinel = tmp_path / "PWNED_SWEEP_UNDELIVERABLE"
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", f"echo hello $(touch {sentinel})")
        rd = tmp_path/"r"; rd.mkdir(); store = StateStore(rd)
        st = {"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"","manifest_path":"/x","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"t"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[{"chat_id":"t","kind":"p","message":"m1"}],"heartbeat":{},"terminal":None}
        store.save(st)
        from presentation_job.__main__ import cmd_sweep_undeliverable
        class A: run_dir = rd
        rc = cmd_sweep_undeliverable(A())
        assert rc == 0, "the message must still drain mechanically (echo succeeds)"
        assert not sentinel.exists(), (
            f"SECURITY FAILURE: cmd_sweep_undeliverable executed injected content, {sentinel} exists"
        )
        s2 = store.load()
        assert len(s2.get("undeliverable", [])) == 0

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


# ---------------------------------------------------------------------------
# U069 bypass closure: the merge gate found that heal.py's retry rungs
# (rung2_regenerate, rung3_alt_route) re-derived `cmd.replace("{run_dir}", ...)`
# and ran it with shell=True, completely independent of the tokenise-first
# fix landed in phases.py._run_script_phase. That meant a run_dir or manifest
# executor.cmd/alt_cmd crafted with shell metacharacters was STILL exploitable
# whenever a phase healed through rung 2 or rung 3 -- the fix only covered the
# happy path. The close: both rungs now call the engine's single
# `_build_executor_argv` (tokenise, then substitute into tokens) instead of
# rebuilding a raw command string of their own. These tests drive real
# injection payloads through rung2 and rung3 directly and prove nothing
# injected ever runs, then prove the identical run_dir payload is equally
# inert on the primary path -- one code path, one guarantee, not two.
# ---------------------------------------------------------------------------
class TestU069HealBypassClosed:
    def test_rung2_manifest_cmd_injection_blocked(self, tmp_path, monkeypatch):
        """U069 bypass: executor.cmd with a `;`-chained payload must not run
        the chained command when rung2_regenerate re-executes it."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        sentinel = tmp_path / "PWNED_RUNG2_CMD"
        m = _mkmanifest(tmp_path, cmd="echo hello; touch " + str(sentinel))
        e, s = _mkengine(tmp_path, m)
        rc = rung2_regenerate(e, m.phase("TP"), "missing artifact")
        assert rc == EXIT_OK, "echo itself must still succeed mechanically"
        assert not sentinel.exists(), (
            f"SECURITY FAILURE: rung2_regenerate executed injected content, {sentinel} exists"
        )

    def test_rung3_alt_cmd_injection_blocked(self, tmp_path, monkeypatch):
        """U069 bypass: alt_cmd with a `;`-chained payload must not run the
        chained command when rung3_alt_route executes it."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        sentinel = tmp_path / "PWNED_RUNG3_ALT"
        m = _mkmanifest(tmp_path, phases=[{
            "id": "TP", "order": 1, "owning_role": "t",
            "produces_artifact": ["o.txt"],
            "executor": {"kind": "script", "cmd": "exit 1",
                         "alt_cmd": "echo hello; touch " + str(sentinel)},
        }])
        e, s = _mkengine(tmp_path, m)
        rc = rung3_alt_route(e, m.phase("TP"))
        assert rc == EXIT_OK, "echo itself must still succeed mechanically"
        assert not sentinel.exists(), (
            f"SECURITY FAILURE: rung3_alt_route executed injected content, {sentinel} exists"
        )

    def test_rung2_run_dir_metachar_injection_blocked(self, tmp_path, monkeypatch):
        """U069 bypass, run_dir vector: a run_dir whose NAME contains a shell
        command-substitution payload must not fire when rung2_regenerate
        substitutes {run_dir} into the (re-tokenised) argv. Before the close,
        rung2 did `cmd.replace("{run_dir}", str(run_dir))` then shell=True'd
        the result, so this exact payload would execute."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        sentinel = tmp_path / "PWNED_RUNG2_RUNDIR"
        run_dir = tmp_path / ("evil_$(touch " + str(sentinel) + ")_dir")
        m = _mkmanifest(tmp_path, cmd="echo {run_dir}")
        e, s = _mkengine_at(tmp_path, run_dir, m)
        rc = rung2_regenerate(e, m.phase("TP"), "missing artifact")
        assert rc == EXIT_OK, "echo itself must still succeed mechanically"
        assert not sentinel.exists(), (
            f"SECURITY FAILURE: rung2_regenerate re-interpreted run_dir as shell syntax, "
            f"{sentinel} exists"
        )

    def test_same_run_dir_payload_inert_on_both_paths(self, tmp_path, monkeypatch):
        """Same adversarial run_dir, driven through the primary path
        (_run_script_phase) and the heal/retry path (rung2_regenerate) in the
        same test -- proves there is exactly one argv-building code path
        shared by both, not two with diverging safety."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        sentinel = tmp_path / "PWNED_SHARED_PATH"
        run_dir = tmp_path / ("evil_$(touch " + str(sentinel) + ")_dir")
        m = _mkmanifest(tmp_path, cmd="echo {run_dir}")
        e, s = _mkengine_at(tmp_path, run_dir, m)
        phase = m.phase("TP")

        rc1 = e._run_script_phase(phase)
        assert rc1 == EXIT_OK
        assert not sentinel.exists(), "primary path let the run_dir payload execute"

        rc2 = rung2_regenerate(e, phase, "missing artifact")
        assert rc2 == EXIT_OK
        assert not sentinel.exists(), "heal/retry path let the run_dir payload execute"
