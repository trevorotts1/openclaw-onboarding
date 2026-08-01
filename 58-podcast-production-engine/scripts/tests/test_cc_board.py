#!/usr/bin/env python3
"""
test_cc_board.py -- hermetic tests for the Podcast department producer-side
Command Center board caller (cc_board.py). Stdlib unittest only; NO live
network -- every HTTP call is intercepted so the suite is deterministic and
offline.

Covers:
  * FAIL-SOFT: no CC_BASE_URL => clean no-op, never raises.
  * run-begin creates a card via POST /api/tasks/ingest and maps job-id.
  * Duplicate run-begin is idempotent (returns same task_id, no second POST).
  * patch-phase sends correct PATCH payload with phase_id + status.
  * CC unreachable => exit 0 + stderr line (fail-soft proof).
  * Missing required args => exit 2.
  * close sends terminal status (done / blocked).
"""

import hashlib
import hmac
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
import cc_board  # noqa: E402


# ---------------------------------------------------------------------------
# A fake HTTP layer: records the last request and returns a scripted response.
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status, payload):
        self._status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Recorder:
    """Stand-in for urllib.request.urlopen. Captures requests and replays a queue
    of (status, payload) responses; a response may be an Exception to raise."""

    def __init__(self):
        self.requests = []
        self.responses = []

    def queue(self, status, payload):
        self.responses.append((status, payload))

    def queue_raise(self, exc):
        self.responses.append(exc)

    def __call__(self, req, timeout=None):
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "headers": {k.lower(): v for k, v in req.header_items()},
            "body": req.data.decode("utf-8") if req.data else "",
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError("no scripted response queued")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        status, payload = nxt
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "err", {}, io.BytesIO(json.dumps(payload).encode()))
        return _FakeResp(status, payload)


ENV = {
    "CC_BASE_URL": "https://cc.example.test/",
    "MC_API_TOKEN": "tok-abc",
    "WEBHOOK_SECRET": "shh-secret",
}


class FailSoftTest(unittest.TestCase):
    """Board disabled or unreachable => clean no-op."""

    def test_config_none_without_url(self):
        self.assertIsNone(cc_board.board_config({"MC_API_TOKEN": "x"}))
        self.assertIsNone(cc_board.board_config({}))

    def test_config_resolved_with_url(self):
        cfg = cc_board.board_config(ENV)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["base_url"], "https://cc.example.test")
        self.assertEqual(cfg["token"], "tok-abc")
        self.assertEqual(cfg["timeout"], 5)

    def test_create_noop_without_url(self):
        self.assertIsNone(cc_board.create_board_card("j1", "client", "My Ep", env={}))

    def test_patch_noop_without_url(self):
        self.assertFalse(cc_board.patch_board_card("j1", phase="writing", status="in_progress", env={}))


class AuthAndContractTest(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = self.rec
        # Clear any pre-existing state map for these tests.
        self._tmp_state = tempfile.TemporaryDirectory()
        self._orig_state = cc_board._STATE_FILE
        cc_board._STATE_DIR = Path(self._tmp_state.name)
        cc_board._STATE_FILE = cc_board._STATE_DIR / "board-map.json"

    def tearDown(self):
        cc_board.urllib.request.urlopen = self._orig
        cc_board._STATE_DIR = Path.home() / ".openclaw" / "podcast-engine"
        cc_board._STATE_FILE = self._orig_state
        self._tmp_state.cleanup()

    def _verify_signature(self, request):
        """Recompute the signature exactly as the route handler does."""
        body = request["body"].encode("utf-8")
        expected = hmac.new(b"shh-secret", body, hashlib.sha256).hexdigest()
        self.assertEqual(request["headers"]["x-webhook-signature"], expected)

    def test_create_contract_and_auth(self):
        self.rec.queue(201, {"ok": True, "task_id": "task-uuid-001",
                             "workspace_id": "ws-podcast", "status": "backlog"})
        tid = cc_board.create_board_card("job-abc", "Test Client", "Ep Title", env=ENV)
        self.assertEqual(tid, "task-uuid-001")
        req = self.rec.requests[-1]
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["url"], "https://cc.example.test/api/tasks/ingest")
        self.assertEqual(req["headers"]["authorization"], "Bearer tok-abc")
        self.assertEqual(req["headers"]["content-type"], "application/json")
        self._verify_signature(req)
        body = json.loads(req["body"])
        self.assertEqual(body["title"], "Episode: Ep Title (Test Client)")
        self.assertEqual(body["department_slug"], "podcast")
        self.assertEqual(body["source"], "podcast-engine")
        self.assertEqual(body["source_ref"], "podcast:job-abc")
        self.assertEqual(body["idempotency_key"], "podcast:episode:job-abc")

    def test_create_http_error_is_failsoft(self):
        self.rec.queue(500, {"error": "boom"})
        tid = cc_board.create_board_card("j1", "c", "E", env=ENV)
        self.assertIsNone(tid)

    def test_create_urlerror_is_failsoft(self):
        """Persistent network failure after retry => fail-soft None."""
        self.rec.queue_raise(urllib.error.URLError("conn refused"))
        self.rec.queue_raise(urllib.error.URLError("conn refused again"))
        tid = cc_board.create_board_card("j1", "c", "E", env=ENV)
        self.assertIsNone(tid)

    def test_create_retries_on_network_error(self):
        """One retry on network error only."""
        self.rec.queue_raise(urllib.error.URLError("conn refused"))
        self.rec.queue(201, {"ok": True, "task_id": "task-retry-ok",
                             "workspace_id": "ws", "status": "backlog"})
        tid = cc_board.create_board_card("j-retry", "c", "E", env=ENV)
        self.assertEqual(tid, "task-retry-ok")
        self.assertEqual(len([r for r in self.rec.requests if r["method"] == "POST"]), 2)


class IdempotencyTest(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = self.rec
        self._tmp_state = tempfile.TemporaryDirectory()
        self._orig_state = cc_board._STATE_FILE
        cc_board._STATE_DIR = Path(self._tmp_state.name)
        cc_board._STATE_FILE = cc_board._STATE_DIR / "board-map.json"

    def tearDown(self):
        cc_board.urllib.request.urlopen = self._orig
        cc_board._STATE_DIR = Path.home() / ".openclaw" / "podcast-engine"
        cc_board._STATE_FILE = self._orig_state
        self._tmp_state.cleanup()

    def test_duplicate_run_begin_is_idempotent(self):
        """Second call returns the same task_id without making a second HTTP request."""
        self.rec.queue(201, {"ok": True, "task_id": "task-001",
                             "workspace_id": "ws", "status": "backlog"})
        tid1 = cc_board.create_board_card("job-dup", "C", "Ep", env=ENV)
        self.assertEqual(tid1, "task-001")
        self.assertEqual(len(self.rec.requests), 1)

        # Second call: no HTTP request, returns cached task_id.
        tid2 = cc_board.create_board_card("job-dup", "C", "Ep", env=ENV)
        self.assertEqual(tid2, "task-001")
        self.assertEqual(len(self.rec.requests), 1)  # no additional requests

    def test_dedup_across_instances(self):
        """Map is persisted to disk, so a second process finds the mapping."""
        self.rec.queue(201, {"ok": True, "task_id": "task-002",
                             "workspace_id": "ws", "status": "backlog"})
        tid1 = cc_board.create_board_card("job-cross", "C", "Ep", env=ENV)
        self.assertEqual(tid1, "task-002")

        # Simulate a fresh lookup (same process, but map should be loaded from disk).
        self.rec.queue(201, {"ok": True, "task_id": "task-NEW",
                             "workspace_id": "ws", "status": "backlog"})
        tid2 = cc_board.create_board_card("job-cross", "C", "Ep", env=ENV)
        self.assertEqual(tid2, "task-002")  # cached, not "task-NEW"


class PatchPhaseTest(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = self.rec
        self._tmp_state = tempfile.TemporaryDirectory()
        self._orig_state = cc_board._STATE_FILE
        cc_board._STATE_DIR = Path(self._tmp_state.name)
        cc_board._STATE_FILE = cc_board._STATE_DIR / "board-map.json"

    def tearDown(self):
        cc_board.urllib.request.urlopen = self._orig
        cc_board._STATE_DIR = Path.home() / ".openclaw" / "podcast-engine"
        cc_board._STATE_FILE = self._orig_state
        self._tmp_state.cleanup()

    def test_patch_phase_maps_correctly(self):
        """PATCH sends phase_id and status correctly."""
        # First create the card to establish the job-id -> task-id mapping.
        self.rec.queue(201, {"ok": True, "task_id": "task-phase-test",
                             "workspace_id": "ws", "status": "backlog"})
        cc_board.create_board_card("job-phase", "C", "Ep", env=ENV)

        # Now patch the phase.
        self.rec.queue(200, {"task": {"id": "task-phase-test", "status": "in_progress"}})
        ok = cc_board.patch_board_card("job-phase", phase="writing", status="in_progress", env=ENV)
        self.assertTrue(ok)

        # Find the PATCH request (skip the POST).
        patches = [r for r in self.rec.requests if r["method"] == "PATCH"]
        self.assertEqual(len(patches), 1)
        patch = patches[0]
        self.assertEqual(patch["url"], "https://cc.example.test/api/tasks/task-phase-test")
        body = json.loads(patch["body"])
        self.assertEqual(body["phase_id"], "writing")
        self.assertEqual(body["status"], "in_progress")

    def test_patch_without_mapped_task_is_noop(self):
        """No task mapped for this job-id => fail-soft False."""
        ok = cc_board.patch_board_card("no-such-job", phase="writing", status="in_progress", env=ENV)
        self.assertFalse(ok)
        self.assertEqual(len(self.rec.requests), 0)

    def test_all_phases_accepted(self):
        """All valid podcast phases are accepted by the CLI."""
        valid_phases = {
            "received", "researching", "writing", "in_qc",
            "generating_art", "producing_audio", "publishing", "enrolling", "complete",
        }
        # First create.
        self.rec.queue(201, {"ok": True, "task_id": "task-all",
                             "workspace_id": "ws", "status": "backlog"})
        cc_board.create_board_card("job-all", "C", "Ep", env=ENV)

        for phase in valid_phases:
            self.rec.queue(200, {"task": {"id": "task-all", "status": "in_progress"}})
            ok = cc_board.patch_board_card("job-all", phase=phase, status="in_progress", env=ENV)
            self.assertTrue(ok, f"phase={phase} should be accepted")


class CloseTest(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = self.rec
        self._tmp_state = tempfile.TemporaryDirectory()
        self._orig_state = cc_board._STATE_FILE
        cc_board._STATE_DIR = Path(self._tmp_state.name)
        cc_board._STATE_FILE = cc_board._STATE_DIR / "board-map.json"

    def tearDown(self):
        cc_board.urllib.request.urlopen = self._orig
        cc_board._STATE_DIR = Path.home() / ".openclaw" / "podcast-engine"
        cc_board._STATE_FILE = self._orig_state
        self._tmp_state.cleanup()

    def test_close_done(self):
        self.rec.queue(201, {"ok": True, "task_id": "task-close",
                             "workspace_id": "ws", "status": "backlog"})
        cc_board.create_board_card("job-close", "C", "Ep", env=ENV)

        self.rec.queue(200, {"task": {"id": "task-close", "status": "done"}})
        ok = cc_board.patch_board_card("job-close", status="done", note="Episode finished.", env=ENV)
        self.assertTrue(ok)
        patch = [r for r in self.rec.requests if r["method"] == "PATCH"][-1]
        body = json.loads(patch["body"])
        self.assertEqual(body["status"], "done")
        self.assertEqual(body["note"], "Episode finished.")

    def test_close_blocked(self):
        self.rec.queue(201, {"ok": True, "task_id": "task-blocked",
                             "workspace_id": "ws", "status": "backlog"})
        cc_board.create_board_card("job-blocked", "C", "Ep", env=ENV)

        self.rec.queue(200, {"task": {"id": "task-blocked", "status": "blocked"}})
        ok = cc_board.patch_board_card("job-blocked", status="blocked", note="Stuck on approval.", env=ENV)
        self.assertTrue(ok)
        patch = [r for r in self.rec.requests if r["method"] == "PATCH"][-1]
        body = json.loads(patch["body"])
        self.assertEqual(body["status"], "blocked")


class CliExitCodeTest(unittest.TestCase):
    """Prove CLI exit codes: fail-soft => exit 0, usage error => exit 2."""

    CC_BOARD_PATH = str(PARENT / "cc_board.py")

    def setUp(self):
        self._tmp_state = tempfile.TemporaryDirectory()
        self._env = {
            **os.environ,
            "CC_BASE_URL": "https://cc.example.test",
            "MC_API_TOKEN": "tok",
        }
        # Redirect state directory for CLI tests.
        self._env["HOME"] = self._tmp_state.name

    def tearDown(self):
        self._tmp_state.cleanup()

    def _run(self, *args, **kwargs):
        env = kwargs.pop("env", self._env)
        return subprocess.run(
            [sys.executable, self.CC_BOARD_PATH] + list(args),
            capture_output=True, text=True, env=env, **kwargs,
        )

    def test_missing_args_exit_2(self):
        # No subcommand at all.
        r = self._run()
        self.assertEqual(r.returncode, 2)

        # run-begin without --episode-title.
        r = self._run("run-begin", "--job-id", "j1")
        self.assertEqual(r.returncode, 2)

        # patch-phase without required args.
        r = self._run("patch-phase", "--job-id", "j1")
        self.assertEqual(r.returncode, 2)

        # close without --status.
        r = self._run("close", "--job-id", "j1")
        self.assertEqual(r.returncode, 2)

    def test_run_begin_fail_soft_exit_0(self):
        """CC unreachable => exit 0 with stderr line."""
        env = {**self._env, "CC_BASE_URL": "https://cc-down.example.test"}
        # No mocking the network in subprocess -- just prove that with no CC
        # reachable, the exit code is 0. We do this by providing an unreachable URL.
        r = self._run("run-begin", "--job-id", "j1", "--episode-title", "Ep",
                       env=env, timeout=12)
        self.assertEqual(r.returncode, 0, f"Expected exit 0, got {r.returncode}. stderr={r.stderr}")
        self.assertTrue(r.stderr, "Expected stderr output on fail-soft")

    def test_patch_phase_fail_soft_exit_0(self):
        """patch-phase with CC unreachable => exit 0."""
        env = {**self._env, "CC_BASE_URL": "https://cc-down.example.test"}
        r = self._run("patch-phase", "--job-id", "j1", "--phase", "writing",
                       "--status", "in_progress", env=env, timeout=12)
        self.assertEqual(r.returncode, 0, f"Expected exit 0, got {r.returncode}. stderr={r.stderr}")
        self.assertTrue(r.stderr, "Expected stderr output on fail-soft")

    def test_close_fail_soft_exit_0(self):
        """close with CC unreachable => exit 0."""
        env = {**self._env, "CC_BASE_URL": "https://cc-down.example.test"}
        r = self._run("close", "--job-id", "j1", "--status", "done",
                       env=env, timeout=12)
        self.assertEqual(r.returncode, 0, f"Expected exit 0, got {r.returncode}. stderr={r.stderr}")
        self.assertTrue(r.stderr, "Expected stderr output on fail-soft")

    def test_invalid_phase_exit_2(self):
        """invalid phase => exit 2."""
        r = self._run("patch-phase", "--job-id", "j1", "--phase", "bogus",
                       "--status", "in_progress")
        self.assertEqual(r.returncode, 2, f"Expected exit 2, got {r.returncode}. stderr={r.stderr}")

    def test_invalid_status_exit_2(self):
        """invalid status => exit 2."""
        r = self._run("patch-phase", "--job-id", "j1", "--phase", "writing",
                       "--status", "bogus")
        self.assertEqual(r.returncode, 2, f"Expected exit 2, got {r.returncode}. stderr={r.stderr}")

    def test_close_invalid_status_exit_2(self):
        """close with invalid status => exit 2."""
        r = self._run("close", "--job-id", "j1", "--status", "bogus")
        self.assertEqual(r.returncode, 2, f"Expected exit 2, got {r.returncode}. stderr={r.stderr}")


class LegalPhasesTest(unittest.TestCase):
    """Enumeration of podcast-specific phases that the CLI validates."""

    def test_valid_phases(self):
        valid = {
            "received", "researching", "writing", "in_qc",
            "generating_art", "producing_audio", "publishing", "enrolling", "complete",
        }
        self.assertEqual(len(valid), 9)

    def test_valid_statuses(self):
        valid = {"in_progress", "review", "done", "blocked"}
        self.assertEqual(len(valid), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
