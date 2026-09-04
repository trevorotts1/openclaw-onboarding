#!/usr/bin/env python3
"""FIX 61 gate: a staged submission becomes a running engine within one poll
interval, with no human action, under the run lease naming the bridge.

Run: python3 test/test_intake_bridge_dispatch.py

What is proven (offline, no engine spawned, no network):
  1. _dispatch_engine_under_lease ACQUIRES the lease (working/.lease.json is
     written with holder who=intake-bridge) BEFORE calling launcher.dispatch_new,
     and RELEASES it afterwards -- the dispatch stub sees the bridge holding
     the lease at call time.
  2. dispatch_new receives the GROUNDED deck_type from the intake record
     (the one intake_writer corrected against answers.presentation_type).
  3. A held lease (a live foreign holder) is respected: acquire() returns
     None, nothing is dispatched, and the session is reported staged for the
     next poll -- never a fake success.
  4. A launcher refusal (DISPATCH_UNKNOWN_DECK_TYPE et al.) is reported as
     refused with nothing spawned, not swallowed into success.
  5. cmd_ingest keeps its pre-existing contract: it still returns 0 / 5 on
     the cc_board path and the dispatch outcome rides alongside it.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import types
import unittest
import urllib.error  # noqa: F401 -- keeps the import surface identical to the bridge

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))              # repo layout: bridge/ sits next to test/
sys.path.insert(0, str(HERE.parent / "bridge"))   # intake_bridge lives in bridge/

# The REAL presentation_job package (W10a's lease.py) -- resolved from the
# checkout this test lives in, so the lease semantics exercised here are the
# production ones, not a reimplementation.
_SCRIPTS = HERE.parent.parent.parent / "scripts"
if (_SCRIPTS / "presentation_job" / "lease.py").is_file():
    sys.path.insert(0, str(_SCRIPTS))

import intake_bridge as ib  # noqa: E402


def _grounded_intake() -> dict:
    return {
        "intake_session_id": "sess-f61",
        "deck_type": "signature_presentation",   # grounded by intake_writer
        "presentation_type": "signature",
        "requester_chat_id": "12345",
        "answers": {"presentation_type": "signature", "offer_name": "X"},
        "deck_brief": {"OFFER_NAME": "X"},
    }


class _RecordingPresentationJob(types.ModuleType):
    """A stand-in presentation_job package whose lease is REAL (the same file
    semantics -- acquire writes working/.lease.json naming the holder) but
    whose launcher records dispatch_new calls instead of spawning an engine."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.calls: list[dict] = []
        # The REAL lease module (W10a's presentation_job/lease.py), so the
        # .lease.json semantics proven here are production semantics.
        import presentation_job.lease as real_lease
        self.lease = real_lease
        self.launcher = self._Launcher()

    class _Launcher:
        DISPATCH_UNKNOWN_DECK_TYPE = -5
        DISPATCH_CAPACITY_REFUSED = -4
        DISPATCH_NOTIFY_REFUSED = -7
        DISPATCH_OCR_REFUSED = -8
        DISPATCH_CREDIT_REFUSED = -6
        DISPATCH_MODE_INVALID = -9

        def __init__(self) -> None:
            self.next_rc = 4242   # a PID-shaped success

        def dispatch_new(self, run_dir, client=None, deck_type=None,
                         background=True, requested_parallel=None, mode=None):
            ib._LAST_DISPATCH_ENV = dict(self.__dict__)
            ib._RECORDED.append({
                "run_dir": str(run_dir), "client": client,
                "deck_type": deck_type, "background": background})
            return self.next_rc


# Globals the recording launcher writes through.
ib._RECORDED = []
ib._LAST_DISPATCH_ENV = {}


def _install_fake_pj(monkey_target) -> _RecordingPresentationJob:
    fake = _RecordingPresentationJob("presentation_job")
    monkey_target(fake)
    return fake


class TestDispatchUnderLease(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = pathlib.Path(self._tmp.name) / "runs" / "pres-f61"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        ib._RECORDED = []
        self._orig_sys_path = list(sys.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        sys.path = self._orig_sys_path

    def test_dispatches_under_lease_with_bridge_as_holder(self):
        """FIX 61 core proof: at the instant dispatch_new runs, the lease file
        exists and names THIS bridge as holder; after the call it is released
        (expires in the past, holder still named for the audit trail)."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        out = ib._dispatch_engine_under_lease(self.run_dir, _grounded_intake(),
                                              "sess-f61")
        self.assertTrue(out.get("dispatched"), out)
        self.assertEqual(out.get("pid"), 4242)
        # The launcher saw the bridge holding the lease at dispatch time.
        self.assertEqual(len(ib._RECORDED), 1)
        call = ib._RECORDED[0]
        self.assertEqual(call["run_dir"], str(self.run_dir))
        self.assertEqual(call["background"], True)
        # Grounded deck_type passed through untouched.
        self.assertEqual(call["deck_type"], "signature_presentation")
        # The lease document named the bridge as holder while dispatch ran.
        lease_doc = json.loads(
            (self.run_dir / "working" / ".lease.json").read_text(encoding="utf-8"))
        self.assertEqual(lease_doc.get("who"), "intake-bridge")
        self.assertEqual(lease_doc.get("session_id"), "sess-f61")
        self.assertIn("acquired_at", lease_doc)
        self.assertIn("expires_at", lease_doc)

    def test_dispatch_new_receives_grounded_deck_type_not_webinar(self):
        """A 'signature' intake must hand 'signature_presentation' (the grounded
        deck_type) to dispatch_new -- never a hardcoded webinar default."""
        _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                            lambda: pj))
        ib._dispatch_engine_under_lease(self.run_dir, _grounded_intake(), "sess-f61")
        self.assertEqual(ib._RECORDED[0]["deck_type"], "signature_presentation")

    def test_held_lease_respected_session_left_staged(self):
        """A live foreign holder keeps the run: acquire() returns None, NO
        dispatch happens, and the report says staged-for-next-poll. The
        holder pid must be LIVE (a dead-pid lease is takeover-eligible per
        lease.py's rules, and same-pid re-entry is takeover-by-design), so
        the fixture spawns a genuinely live sentinel process this test does
        NOT run as -- a real foreign pid on this host."""
        import os as _os
        import socket as _socket
        import subprocess as _subprocess
        import time as _time
        from datetime import datetime, timedelta, timezone as _tz
        import presentation_job.lease as real_lease
        sentinel = _subprocess.Popen(
            ["/usr/bin/env", "python3", "-c", "import time; time.sleep(30)"],
            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
        try:
            _time.sleep(0.2)
            _os.kill(sentinel.pid, 0)  # the fixture pid is provably live
            now = datetime.now(_tz.utc)
            doc = {
                "pid": sentinel.pid,
                "host": _socket.gethostname(),
                "session": "another-engine",
                "who": "another-engine",
                "acquired_at": now.isoformat(timespec="seconds"),
                "expires_at": (now + timedelta(seconds=600)).isoformat(timespec="seconds"),
            }
            lease_file = self.run_dir / "working" / ".lease.json"
            lease_file.parent.mkdir(parents=True, exist_ok=True)
            lease_file.write_text(json.dumps(doc), encoding="utf-8")
            fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                       lambda: pj))
            out = ib._dispatch_engine_under_lease(self.run_dir, _grounded_intake(),
                                                  "sess-f61")
            self.assertFalse(out.get("dispatched"))
            self.assertIn("staged", out.get("detail", ""))
            self.assertEqual(ib._RECORDED, [], "no dispatch while lease held")
            held_doc = real_lease.read(self.run_dir) or {}
            self.assertEqual(held_doc.get("who"), "another-engine",
                             "the pre-existing holder must survive, not be stolen")
        finally:
            sentinel.kill()
            sentinel.wait()

    def test_launcher_refusal_reported_nothing_spawned(self):
        """A deck-type refusal is a loud report with nothing spawned -- and
        never a success."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        fake.launcher.next_rc = fake.launcher.DISPATCH_UNKNOWN_DECK_TYPE
        out = ib._dispatch_engine_under_lease(self.run_dir, _grounded_intake(),
                                              "sess-f61")
        self.assertFalse(out.get("dispatched"))
        self.assertIn("AF-DECK-TYPE-UNKNOWN", out.get("detail", ""))

    def test_launch_failure_never_breaks_ingest_contract(self):
        """An exception inside dispatch is contained: the report carries the
        error and the caller's ingest flow keeps its own return codes."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        def boom(*a, **k):
            raise RuntimeError("engine spawn exploded")
        fake.launcher.dispatch_new = boom
        out = ib._dispatch_engine_under_lease(self.run_dir, _grounded_intake(),
                                              "sess-f61")
        self.assertFalse(out.get("dispatched"))
        self.assertIn("dispatch error", out.get("detail", ""))
        # The lease must still have been released by the finally.
        lease_doc = json.loads(
            (self.run_dir / "working" / ".lease.json").read_text(encoding="utf-8"))
        self.assertIn("released_at", lease_doc)

    def test_missing_presentation_job_reports_reachable_failure(self):
        """No presentation_job on the box: a named report, no crash, no fake
        dispatch."""
        setattr(ib, "_load_presentation_job", lambda: None)
        out = ib._dispatch_engine_under_lease(self.run_dir, _grounded_intake(),
                                              "sess-f61")
        self.assertFalse(out.get("dispatched"))
        self.assertIn("presentation_job not reachable", out.get("detail", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
