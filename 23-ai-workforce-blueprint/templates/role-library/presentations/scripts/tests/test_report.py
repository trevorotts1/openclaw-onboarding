"""Tests for presentation_job report.py -- U015 throttle, dispatch, events."""
import json, os, subprocess, sys
from pathlib import Path
from unittest import mock
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, utcnow
from presentation_job.report import Reporter, EVENTS_MAX

def _mkstate(tmp_path, chat_id="tc"):
    rd = tmp_path / "r"; rd.mkdir(); store = StateStore(rd)
    s = {"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"2026-01-01T00:00:00+00:00","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":chat_id},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
    return s, store

class TestDispatchFail:
    def test_dispatch_false(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        s,st=_mkstate(tmp_path); r=Reporter(s,st); r.to_requester("done","x")
        assert len(s.get("undeliverable",[]))==1; assert s.get("sent",{}).get("done") is None

class TestNonZero:
    def test_nonzero(self, tmp_path, monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\nexit 7\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s,st=_mkstate(tmp_path); r=Reporter(s,st); r.to_requester("done","x")
        assert len(s.get("undeliverable",[]))>=1
        sd=s.get("sent",{}).get("done"); assert sd is None or (isinstance(sd,dict) and sd.get("count",0)==0)

class TestSuccess:
    def test_success(self, tmp_path, monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s,st=_mkstate(tmp_path); r=Reporter(s,st); r.to_requester("progress","x")
        sd=s.get("sent",{}).get("progress"); assert isinstance(sd,dict); assert sd.get("count")==1

class TestTimeout:
    def test_timeout(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD","sleep 60")
        s,st=_mkstate(tmp_path); r=Reporter(s,st)
        with mock.patch.object(subprocess,"run",side_effect=subprocess.TimeoutExpired("c",30)):r.to_requester("done","x")
        assert len(s.get("undeliverable",[]))>=1

class TestDoneNever:
    def test_done(self,tmp_path,monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        s,st=_mkstate(tmp_path);r=Reporter(s,st)
        for i in range(500):r.to_requester("progress",f"n{i}")
        r.to_requester("done","deck ready");assert isinstance(s.get("sent",{}).get("done"),dict)

class TestBlocked:
    def test_dedupe(self,tmp_path,monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        s,st=_mkstate(tmp_path);r=Reporter(s,st)
        r.to_requester("blocked","x",phase_id="P",reason="e9");r.to_requester("blocked","x",phase_id="P",reason="e9");r.to_requester("blocked","x",phase_id="P",reason="e9")
        assert s.get("sent",{}).get("blocked",{}).get("count")==1;assert s.get("throttled",0)>=2
    def test_diff_reason(self,tmp_path,monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        s,st=_mkstate(tmp_path);r=Reporter(s,st)
        r.to_requester("blocked","x",phase_id="P",reason="e9");r.to_requester("blocked","x",phase_id="P",reason="ef")
        assert s.get("sent",{}).get("blocked",{}).get("count")==2

class TestEvents:
    def test_cap(self,tmp_path):
        s,st=_mkstate(tmp_path);r=Reporter(s,st)
        for i in range(EVENTS_MAX+500):r.event("t",f"m{i}")
        ev=s.get("events",[]);assert len(ev)<=EVENTS_MAX+2;assert ev[-1]["message"]==f"m{EVENTS_MAX+499}"

class TestUpgrade:
    def test_upgrade(self,tmp_path,monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        s,st=_mkstate(tmp_path);s["sent"]["ack"]="2026-01-01T00:00:00+00:00";st.save(s)
        r=Reporter(s,st);r.to_requester("ack","h")
        sd=s.get("sent",{}).get("ack");assert isinstance(sd,dict);assert sd["count"]==1;assert sd["first_at"]=="2026-01-01T00:00:00+00:00"

class TestProbe:
    def test_probe(self,tmp_path,monkeypatch):
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        s,st=_mkstate(tmp_path);s["throttle_probe"]=True;r=Reporter(s,st)
        for i in range(10):r.to_requester("progress",f"n{i}")
        assert s.get("sent",{}).get("progress") is None;assert s.get("throttled",0)==10
