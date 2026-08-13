"""Tests for presentation_job report.py -- U015 throttle, dispatch, events."""
import json, os, subprocess, sys
from pathlib import Path
from unittest import mock
import pytest
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))
from presentation_job.state import StateStore, utcnow
from presentation_job.report import Reporter, EVENTS_MAX, dispatch3
from presentation_job.result import CheckResult

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

class Test8MessageBound:
    """Test 8: throttle assertion — sends many progress messages with time
    advancing 1 minute per call, verifying total sent is 6-20.

    When PROGRESS_MIN_INTERVAL_MINUTES is set to 0 (mutation), the throttle
    never suppresses, so all 66 messages go through (>20), and this test FAILS.
    That proves the suite detects the broken throttle."""
    def test_message_bound(self,tmp_path,monkeypatch):
        import presentation_job.report as rpt
        n=tmp_path/"n";n.mkdir();ns=n/"s.sh";ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n");ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",str(ns))
        rd=tmp_path/"r";rd.mkdir();store=StateStore(rd)
        s={"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"2026-01-01T00:00:00+00:00","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"tc"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[],"heartbeat":{},"terminal":None}
        store.save(s)
        # Fake clock: 1 minute per call, so with PROGRESS_MIN_INTERVAL_MINUTES=10,
        # every 11th progress message passes (diff >= 10).  64 progress / 11 ≈ 6 sent.
        # Total: 1 ack + ~6 progress + 1 done ≈ 8 (in the 6-20 band).
        _tick=[0]
        monkeypatch.setattr(rpt,'_parse_minutes',lambda ts: (_tick.__setitem__(0,_tick[0]+1) or _tick[0]) if True else 0)
        r=Reporter(s,store)
        r.to_requester("ack","Starting build.")
        for i in range(32):
            r.to_requester("progress",f"Starting phase {i}",phase_id=f"P{i}",reason="start")
            r.to_requester("progress",f"Phase {i} complete",phase_id=f"P{i}",reason="done")
        r.to_requester("done","All done.")
        sc=s.get("sent",{})
        total=sum(v.get("count",0) for v in sc.values() if isinstance(v,dict))
        throttled=s.get("throttled",0)
        assert isinstance(sc.get("ack"),dict) and sc["ack"]["count"]==1
        assert isinstance(sc.get("done"),dict) and sc["done"]["count"]==1
        assert throttled>0,(f"throttled={throttled} — throttle inactive (PROGRESS_MIN_INTERVAL_MINUTES=0?)")
        assert 6<=total<=20,f"expected 6-20 messages, got {total} (throttled={throttled})"

class TestUndeliverableChatId:
    """Regression: undeliverable records store 'chat_id', not 'chat_id_present'."""
    def test_chat_id_key_present(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        s, st = _mkstate(tmp_path, chat_id="test-chat-42")
        r = Reporter(s, st)
        r.to_requester("done", "x")
        undel = s.get("undeliverable", [])
        assert len(undel) == 1
        assert "chat_id" in undel[0], f"expected 'chat_id' key, got keys={list(undel[0].keys())}"
        assert undel[0]["chat_id"] == "test-chat-42", f"expected chat_id='test-chat-42', got {undel[0].get('chat_id')}"
        assert "chat_id_present" not in undel[0], \
            f"'chat_id_present' key found — sweeper key mismatch defect; got keys={list(undel[0].keys())}"
    def test_chat_id_falsy_skips_dispatch(self, tmp_path, monkeypatch):
        """Empty chat_id returns early and does NOT create undeliverable record."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        s, st = _mkstate(tmp_path, chat_id="")
        r = Reporter(s, st)
        r.to_requester("blocked", "msg")
        undel = s.get("undeliverable", [])
        assert len(undel) == 0  # early return, no dispatch attempted

class TestSweeperDispatch:
    """Regression: sweeper can actually dispatch when transport recovers."""
    def test_sweeper_drains_with_chat_id_key(self, tmp_path, monkeypatch):
        n = tmp_path / "n"; n.mkdir(); ns = n / "s.sh"
        ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        rd = tmp_path / "r"; rd.mkdir(); store = StateStore(rd)
        s = {"schema_version":1,"job_id":"t","run_dir":str(rd),"created_at":"2026-01-01T00:00:00+00:00","manifest_path":"/x.json","manifest_version":25,"manifest_sha256":"0"*64,"presentation_type":"from_scratch","requester":{"chat_id":"tc"},"phases":[],"gates":{},"waivers":[],"events":[],"sent":{},"undeliverable":[{"chat_id":"tc","kind":"progress","message":"m1","attempts":1}],"heartbeat":{},"terminal":None}
        store.save(s)
        from presentation_job.__main__ import cmd_sweep_undeliverable
        class A: run_dir = rd
        rc = cmd_sweep_undeliverable(A())
        assert rc == 0
        s2 = store.load()
        assert len(s2.get("undeliverable",[])) == 0
        assert isinstance(s2.get("sent",{}).get("progress"), dict)
        assert s2["sent"]["progress"]["count"] == 1


class TestDispatch3ThreeValued:
    """B6-1 acceptance: dispatch3() itself distinguishes GOOD / BAD / UNKNOWABLE
    instead of collapsing all three into one boolean."""

    def test_good_confirmed_delivery_is_pass(self, tmp_path, monkeypatch):
        n = tmp_path / "n"; n.mkdir(); ns = n / "s.sh"
        ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        assert dispatch3("chat", "kind", "msg") is CheckResult.PASS

    def test_bad_no_transport_configured_is_fail(self, monkeypatch):
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        assert dispatch3("chat", "kind", "msg") is CheckResult.FAIL

    def test_unknowable_nonzero_exit_is_undetermined_not_pass(self, tmp_path, monkeypatch):
        n = tmp_path / "n"; n.mkdir(); ns = n / "s.sh"
        ns.write_text("#!/bin/sh\nexit 7\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        result = dispatch3("chat", "kind", "msg")
        assert result is CheckResult.UNDETERMINED
        assert result is not CheckResult.PASS

    def test_unknowable_timeout_is_undetermined_not_pass(self, monkeypatch):
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", "sleep 60")
        with mock.patch.object(subprocess, "run",
                                side_effect=subprocess.TimeoutExpired("c", 30)):
            result = dispatch3("chat", "kind", "msg")
        assert result is CheckResult.UNDETERMINED
        assert result is not CheckResult.PASS

    def test_checkresult_has_no_truthiness(self):
        """Guards against the exact regression this type exists to prevent:
        `if result:` must never compile a silent decision about UNDETERMINED."""
        with pytest.raises(TypeError):
            bool(CheckResult.UNDETERMINED)
        with pytest.raises(TypeError):
            bool(CheckResult.PASS)


class TestBlockedDedupeNeverSuppressesAnUnconfirmedSend:
    """B6-1 acceptance, the actual production bug: a blocked alert that FAILS or
    is UNDETERMINED on its first attempt must not have its retry silently
    swallowed by the dedupe timer -- the timer must only ever be armed by a
    CONFIRMED delivery. This is the exact heal.py retry-loop shape (same
    phase_id, same reason, called again seconds later)."""

    def test_good_confirmed_send_then_dedupes_the_next_identical_call(self, tmp_path, monkeypatch):
        """Control / GOOD: unaffected by the fix -- a message that DID get
        through still dedupes its own immediate repeat (no double-notify)."""
        n = tmp_path / "n"; n.mkdir(); ns = n / "s.sh"
        ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s, st = _mkstate(tmp_path); r = Reporter(s, st)
        r.to_requester("blocked", "x", phase_id="P", reason="e9")
        r.to_requester("blocked", "x", phase_id="P", reason="e9")
        assert s.get("sent", {}).get("blocked", {}).get("count") == 1
        assert s.get("throttled", 0) == 1
        assert len(s.get("undeliverable", [])) == 0

    def test_bad_unconfigured_transport_retries_instead_of_throttling(self, tmp_path, monkeypatch):
        """BAD: transport never configured (FAIL every time). The second
        identical blocked call must still ATTEMPT delivery (and queue again),
        never get silently throttled with nothing queued."""
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        s, st = _mkstate(tmp_path); r = Reporter(s, st)
        r.to_requester("blocked", "x", phase_id="P", reason="e9")
        r.to_requester("blocked", "x", phase_id="P", reason="e9")
        assert s.get("sent", {}).get("blocked") is None
        assert s.get("throttled", 0) == 0, "must not be throttled -- neither send was ever confirmed"
        assert len(s.get("undeliverable", [])) == 2, "both unconfirmed attempts must be queued, never dropped"

    def test_unknowable_failed_first_attempt_does_not_suppress_the_retry(self, tmp_path, monkeypatch):
        """THE regression proof. First blocked call's transport is broken
        (non-zero exit == UNDETERMINED). Before the fix: _throttle_decision
        stamped the dedupe timer on the FIRST call regardless of outcome, so
        this SECOND identical call (same phase_id/reason, well within
        BLOCKED_DEDUPE_MINUTES, exactly heal.py's retry-loop shape) would have
        been silently throttled -- never dispatched, never queued -- an alert
        about a real failure just swallowed. After the fix: since the first
        attempt was never CONFIRMED delivered, the dedupe timer was never
        armed, so the second call tries again."""
        n = tmp_path / "n"; n.mkdir(); ns = n / "s.sh"
        ns.write_text("#!/bin/sh\nexit 7\n"); ns.chmod(0o755)
        monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", str(ns))
        s, st = _mkstate(tmp_path); r = Reporter(s, st)

        r.to_requester("blocked", "attempt 1", phase_id="P4-RENDER", reason="exit 1")
        assert s.get("throttled", 0) == 0, "the first attempt is never throttled"
        assert len(s.get("undeliverable", [])) == 1, "the first failed attempt must be queued"

        r.to_requester("blocked", "attempt 2", phase_id="P4-RENDER", reason="exit 1")
        # This is the load-bearing assertion: NOT throttled, and a second
        # queued record exists -- the retry was actually attempted, not
        # silently eaten by a dedupe timer that should never have been armed.
        assert s.get("throttled", 0) == 0, (
            "an unconfirmed send must never arm the dedupe timer -- the retry "
            "was silently swallowed if this is nonzero"
        )
        assert len(s.get("undeliverable", [])) == 2, (
            "the retry must have been attempted and queued again, not discarded"
        )
        assert s.get("sent", {}).get("blocked") is None, "never actually delivered in this scenario"
        # Now let the transport recover and confirm the SAME (phase_id, reason)
        # blocked event finally gets through and, only now, dedupe activates.
        ns.write_text("#!/bin/sh\ncat>/dev/null\nexit 0\n"); ns.chmod(0o755)
        r.to_requester("blocked", "attempt 3", phase_id="P4-RENDER", reason="exit 1")
        assert s.get("sent", {}).get("blocked", {}).get("count") == 1
        r.to_requester("blocked", "attempt 4", phase_id="P4-RENDER", reason="exit 1")
        assert s.get("sent", {}).get("blocked", {}).get("count") == 1, "now dedupes, since attempt 3 was confirmed"
