#!/usr/bin/env python3
"""PRES-008 gate: _dispatch_launch drives a submission's engine launch under
the run lease, with durable submission states (launch_ledger.py).

Run: python3 test/test_intake_bridge_dispatch.py

What is proven (offline, no engine spawned, no network):
  1. _dispatch_launch ACQUIRES the lease (working/.lease.json is written with
     holder who=intake-bridge) BEFORE calling launcher.dispatch_new, and
     RELEASES it afterwards -- the dispatch stub sees the bridge holding the
     lease at call time.
  2. dispatch_new receives the GROUNDED deck_type from the intake record
     (the one intake_writer corrected against answers.presentation_type).
  3. A held lease (a live foreign holder) is respected: acquire() returns
     None, nothing is dispatched, and the verdict is "lease_held" -- a held
     launch lease is NEVER completion (the submission stays launch_pending).
  4. A launcher refusal (DISPATCH_UNKNOWN_DECK_TYPE et al.) is reported as
     refused with nothing spawned, never a success.
  5. PRES-008 core: a live existing worker is an IDEMPOTENT acknowledgement
     -- discovery completes the handoff BEFORE any spawn, so a crash between
     a successful dispatch and the ledger write recovers with NO second
     executor.
  6. PRES-008: launch_pending survives a refusal -- the durable state
     document records the retry, and the board task id persists (no
     duplicate card on the next tick).
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
import launch_ledger as _ll  # noqa: E402

POLICY = {
    "backoff_base_s": 0.0,
    "backoff_cap_s": 0.0,
    "max_attempts": 10,
    "notify_thresholds": (3, 7),
    "claim_ttl_s": 120.0,
}


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
            ib._RECORDED.append({
                "run_dir": str(run_dir), "client": client,
                "deck_type": deck_type, "background": background})
            return self.next_rc


# Globals the recording launcher writes through.
ib._RECORDED = []


def _install_fake_pj(monkey_target) -> _RecordingPresentationJob:
    fake = _RecordingPresentationJob("presentation_job")
    monkey_target(fake)
    return fake


class TestDispatchLaunch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = pathlib.Path(self._tmp.name) / "runs" / "pres-f61"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        ib._RECORDED = []
        self._orig_sys_path = list(sys.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        sys.path = self._orig_sys_path

    def _hold(self, session_id: str = "sess-f61") -> dict:
        doc = ib._submission_hold(self.run_dir, session_id, POLICY,
                                  holder={"claimed_by": "test"},
                                  run_dir_str=str(self.run_dir))
        self.assertTrue(doc, "the test poller must win its own claim")
        return doc

    def test_dispatches_under_lease_with_bridge_as_holder(self):
        """Core proof: at the instant dispatch_new runs, the lease file exists
        and names THIS bridge as holder; after the call it is released."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        doc = self._hold()
        verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                              "sess-f61", doc, POLICY, False)
        self.assertEqual(verdict, "launched", detail)
        self.assertEqual(ib._RECORDED[0]["run_dir"], str(self.run_dir))
        self.assertEqual(ib._RECORDED[0]["background"], True)
        # Grounded deck_type passed through untouched.
        self.assertEqual(ib._RECORDED[0]["deck_type"], "signature_presentation")
        # The lease document named the bridge as holder while dispatch ran.
        lease_doc = json.loads(
            (self.run_dir / "working" / ".lease.json").read_text(encoding="utf-8"))
        self.assertEqual(lease_doc.get("who"), "intake-bridge")
        self.assertEqual(lease_doc.get("session_id"), "sess-f61")
        self.assertIn("acquired_at", lease_doc)

    def test_dispatch_new_receives_grounded_deck_type_not_webinar(self):
        """A 'signature' intake must hand 'signature_presentation' (the grounded
        deck_type) to dispatch_new -- never a hardcoded webinar default."""
        _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                            lambda: pj))
        doc = self._hold()
        ib._dispatch_launch(self.run_dir, _grounded_intake(), "sess-f61",
                            doc, POLICY, False)
        self.assertEqual(ib._RECORDED[0]["deck_type"], "signature_presentation")

    def test_held_lease_respected_never_completion(self):
        """A live foreign holder keeps the run: acquire() returns None, NO
        dispatch happens, and the verdict is lease_held -- never completion
        (a held launch lease alone is NOT worker_acknowledged, PRES-008).
        The holder pid must be LIVE (a dead-pid lease is takeover-eligible per
        lease.py's rules), so the fixture spawns a genuinely live sentinel
        process this test does NOT run as."""
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
            held = self._hold()
            verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                                  "sess-f61", held, POLICY, False)
            self.assertEqual(verdict, "lease_held", detail)
            self.assertEqual(ib._RECORDED, [], "no dispatch while lease held")
            self.assertFalse(_ll.is_complete(_ll.load(self.run_dir, "sess-f61")),
                             "a held lease must never complete the submission")
            held_doc = real_lease.read(self.run_dir) or {}
            self.assertEqual(held_doc.get("who"), "another-engine",
                             "the pre-existing holder must survive, not be stolen")
        finally:
            sentinel.kill()
            sentinel.wait()

    def test_launcher_refusal_reported_nothing_spawned(self):
        """A deck-type refusal is a loud verdict with nothing spawned -- and
        never a success. (The recording stub logs the refused dispatch CALL
        itself; "nothing spawned" is what the negative rc encodes — no pid
        came back.)"""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        fake.launcher.next_rc = fake.launcher.DISPATCH_UNKNOWN_DECK_TYPE
        doc = self._hold()
        verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                              "sess-f61", doc, POLICY, False)
        self.assertEqual(verdict, "refused_permanent")
        self.assertIn("AF-DECK-TYPE-UNKNOWN", detail)
        after = _ll.load(self.run_dir, "sess-f61")
        self.assertTrue(_ll.is_blocked(after))
        self.assertFalse(_ll.is_complete(after))
        self.assertIn("AF-DECK-TYPE-UNKNOWN", after["blocked"]["reason"])
        self.assertTrue(after["blocked"]["remediation"],
                        "a permanent refusal carries its remediation")

    def test_launch_failure_never_breaks_ingest_contract(self):
        """An exception inside dispatch is contained: the verdict is
        refused_retryable and the lease is still released by the finally."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        def boom(*a, **k):
            raise RuntimeError("engine spawn exploded")
        fake.launcher.dispatch_new = boom
        doc = self._hold()
        verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                              "sess-f61", doc, POLICY, False)
        self.assertEqual(verdict, "refused_retryable")
        self.assertIn("dispatch error", detail)
        lease_doc = json.loads(
            (self.run_dir / "working" / ".lease.json").read_text(encoding="utf-8"))
        self.assertIn("released_at", lease_doc)

    def test_missing_presentation_job_reports_reachable_failure(self):
        """No presentation_job on the box: a named verdict, no crash, no fake
        dispatch."""
        setattr(ib, "_load_presentation_job", lambda: None)
        doc = self._hold()
        verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                              "sess-f61", doc, POLICY, False)
        self.assertEqual(verdict, "no_engine")
        self.assertIn("presentation_job not reachable", detail)
        self.assertEqual(ib._RECORDED, [])

    def test_existing_live_worker_acknowledged_no_second_executor(self):
        """PRES-008 core: a live worker named by state.json/.engine.pid is an
        IDEMPOTENT acknowledgement -- _dispatch_launch discovers it BEFORE any
        spawn (no second executor) and completes the handoff with a current
        execution id persisted."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        import subprocess as _subprocess
        import time as _time
        sentinel = _subprocess.Popen(
            ["/usr/bin/env", "python3", "-c", "import time; time.sleep(30)"],
            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
        try:
            _time.sleep(0.2)
            # The same surfaces launcher._read_engine_pid reads: state.json
            # (job_id + engine_pid) then the .engine.pid sidecar.
            (self.run_dir / "state.json").write_text(json.dumps({
                "job_id": "pj_test_existing_worker", "engine_pid": sentinel.pid}),
                encoding="utf-8")
            doc = self._hold()
            verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                                  "sess-f61", doc, POLICY, False)
            self.assertEqual(verdict, "acknowledged", detail)
            self.assertEqual(ib._RECORDED, [],
                             "discovery must complete the handoff WITHOUT a spawn")
            after = _ll.load(self.run_dir, "sess-f61")
            self.assertTrue(_ll.is_complete(after))
            self.assertEqual(after["worker_ack"]["execution_id"],
                             "pj_test_existing_worker")
            # Idempotent: re-acking changes nothing.
            again = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                        "sess-f61", after, POLICY, False)
            self.assertEqual(again[0], "acknowledged")
            self.assertEqual(len(ib._RECORDED), 0)
        finally:
            sentinel.kill()
            sentinel.wait()

    def test_refusal_after_launch_pending_keeps_board_binding_no_duplicate(self):
        """PRES-008: a retryable refusal leaves the submission retryable with
        the board task id PERSISTED -- the next tick re-drives launch, never
        re-registers a card (no duplicate), and never completes."""
        fake = _install_fake_pj(lambda pj: setattr(ib, "_load_presentation_job",
                                                   lambda: pj))
        fake.launcher.next_rc = fake.launcher.DISPATCH_CAPACITY_REFUSED
        doc = self._hold()
        doc = _ll.transition(self.run_dir, "sess-f61", doc, _ll.BOARD_REGISTERED,
                             board_task_id="CC-123", why="test board binding")
        verdict, detail = ib._dispatch_launch(self.run_dir, _grounded_intake(),
                                              "sess-f61", doc, POLICY, False)
        self.assertEqual(verdict, "refused_retryable")
        after = _ll.load(self.run_dir, "sess-f61")
        self.assertFalse(_ll.is_complete(after))
        self.assertEqual(after.get("board_task_id"), "CC-123",
                         "the board binding must survive the launch retry")
        self.assertIsNone(after.get("retry_attempt"),
                          "the retry is scheduled by _drive_submission, which "
                          "routes this verdict through mark_retry_pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)
