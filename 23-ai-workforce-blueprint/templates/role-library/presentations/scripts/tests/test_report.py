import json, os, subprocess, sys
from pathlib import Path
from unittest import mock
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, utcnow
from presentation_job.report import Reporter, EVENTS_MAX, PROGRESS_MIN_INTERVAL_MINUTES

def _mkstate(tmp_path, chat_id="test_chat"):
    run_dir = tmp_path / "run"; run_dir.mkdir()
    store = StateStore(run_dir)
    state = {"schema_version":1,"job_id":"test","run_dir":str(run_dir),"created_at":"2026-01-01T00:00:00+00:00","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":chat_id},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
    return store, state

class TestDispatchFailsWithoutCmd:
    def test_dispatch_false(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        from presentation_job.report import _dispatch
        assert _dispatch("c","done","hi") is False
    def test_to_requester_undeliverable(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        r.to_requester("done","test")
        assert len(state.get("undeliverable",[])) == 1
        assert state.get("sent",{}).get("done") is None

class TestDispatchNonZero:
    def test_nonzero_undeliverable(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\nexit 7\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        r.to_requester("done","x")
        assert len(state.get("undeliverable",[])) >= 1
        sd = state.get("sent",{}).get("done"); assert sd is None or (isinstance(sd,dict) and sd.get("count",0)==0)

class TestDispatchSuccess:
    def test_success_stamps(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        r.to_requester("progress","started")
        sd = state.get("sent",{}).get("progress"); assert isinstance(sd,dict); assert sd.get("count")==1

class TestDispatchTimeout:
    def test_timeout_undeliverable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD","sleep 60")
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        with mock.patch.object(subprocess,"run",side_effect=subprocess.TimeoutExpired("c",30)): r.to_requester("done","x")
        assert len(state.get("undeliverable",[])) >= 1

class TestDoneNeverThrottled:
    def test_done_always_delivers(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        for i in range(500): r.to_requester("progress",f"n{i}")
        r.to_requester("done","deck ready")
        assert isinstance(state.get("sent",{}).get("done"),dict)

class TestBlockedDedupe:
    def test_blocked_deduped(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        r.to_requester("blocked","x",phase_id="PX",reason="exit 9")
        r.to_requester("blocked","x",phase_id="PX",reason="exit 9")
        r.to_requester("blocked","x",phase_id="PX",reason="exit 9")
        sd = state.get("sent",{}).get("blocked"); assert isinstance(sd,dict); assert sd.get("count")==1
        assert state.get("throttled",0) >= 2
    def test_blocked_different_reason_not_deduped(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        r.to_requester("blocked","x",phase_id="PX",reason="exit 9")
        r.to_requester("blocked","x",phase_id="PX",reason="executor failed")
        assert state.get("sent",{}).get("blocked",{}).get("count")==2

class TestEventsCap:
    def test_events_capped(self, tmp_path):
        store, state = _mkstate(tmp_path); r = Reporter(state, store)
        for i in range(EVENTS_MAX+500): r.event("test",f"msg {i}")
        events = state.get("events",[]); assert len(events) <= EVENTS_MAX+2
        assert events[-1]["message"] == f"msg {EVENTS_MAX+499}"

class TestSentUpgrade:
    def test_bare_timestamp_upgraded(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); state["sent"]["ack"]="2026-01-01T00:00:00+00:00"; store.save(state)
        r = Reporter(state, store); r.to_requester("ack","hello")
        sd = state.get("sent",{}).get("ack"); assert isinstance(sd,dict); assert sd["count"]==1; assert sd["first_at"]=="2026-01-01T00:00:00+00:00"

class TestThrottleProbe:
    def test_probe_suppresses_progress(self, tmp_path, monkeypatch):
        ndir = tmp_path / "notify"; ndir.mkdir(); ns = ndir / "n.sh"; ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        store, state = _mkstate(tmp_path); state["throttle_probe"]=True; r = Reporter(state, store)
        for i in range(10): r.to_requester("progress",f"n{i}")
        assert state.get("sent",{}).get("progress") is None; assert state.get("throttled",0)==10
