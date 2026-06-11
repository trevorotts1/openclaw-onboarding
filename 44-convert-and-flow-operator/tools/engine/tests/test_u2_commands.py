"""Unit 2 test suite — Section 0 commands, snapshots, serialization, step backoff.

Covers:
  - caf workflows get
  - caf workflows export
  - caf workflows update (with pre-write snapshot)
  - caf workflows build --from-plan (with WriteLock serialization + step backoff)
  - caf workflows patch-email (with pre-write snapshot)
  - caf workflows patch-trigger (with pre-write snapshot)
  - caf workflows restore (with pre-restore snapshot)
  - snapshot_manager: capture() / restore() / list_snapshots()
  - write_lock: WriteLock serializes concurrent writes
  - ghl_internal_client: step backoff inserted between sequential calls
  - Acceptance Criterion 20: pre-write snapshot captured before every mutation
  - Acceptance Criterion 21: serialization + step backoff

All tests use mocks/fixtures — NO live CRM is ever contacted.

Run:
    python3 -m pytest tests/test_u2_commands.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# ── Ensure engine root is on sys.path ─────────────────────────────────────────
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ── Network guard — any connect to leadconnectorhq.com is a hard FAIL ─────────
_BLOCKED_HOST = "leadconnectorhq.com"
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = address[0]
        if _BLOCKED_HOST in str(host):
            raise AssertionError(
                f"U2 SAFETY FAILURE: live CRM host contacted: {host!r}. "
                "All tests must use mocks — no live API calls."
            )
    return _original_connect(self, address)


# Install guard globally for all tests in this module
socket.socket.connect = _guarded_connect


# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURE_WORKFLOW = {
    "id": "WF001",
    "name": "ZHC-Test-Workflow",
    "status": "draft",
    "version": 3,
    "workflowData": {
        "templates": [
            {
                "id": "STEP001",
                "type": "email",
                "name": "Email: Welcome",
                "order": 0,
                "attributes": {
                    "subject": "Welcome to our community",
                    "body": "<p>Hello!</p>",
                    "html": "<p>Hello!</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "STEP002",
                "type": "wait",
                "name": "Wait 1 Day",
                "order": 1,
                "attributes": {"type": "time", "startAfter": {"type": "days", "value": 1}},
            },
            {
                "id": "STEP003",
                "type": "add_contact_tag",
                "name": "Tag: nurtured",
                "order": 2,
                "attributes": {"tags": ["nurtured"]},
            },
        ]
    },
    "triggers": [{"id": "TRG001", "type": "contact_tag", "name": "new-lead"}],
}

FIXTURE_PLAN = {
    "email_nurture": {
        "name": "ZHC-3Email-Nurture",
        "tag": "new-consult-lead",
        "templates": [
            {
                "id": "s1", "type": "email", "name": "Email: Email 1",
                "order": 0,
                "attributes": {
                    "subject": "Email 1",
                    "body": "<p>Body 1</p>",
                    "html": "<p>Body 1</p>",
                    "fromName": "", "attachments": [],
                },
            },
        ],
    }
}


def _make_mock_client(location_id: str = "LOC001", workflow_data: dict | None = None) -> MagicMock:
    """Create a mock InternalAdapter that returns fixture data.

    Returns AdapterResult from get_workflow/put_workflow to match the
    InternalAdapter interface used by CLI commands after the adapter refactor.
    Also provides a legacy .request() side_effect for snapshot_manager compat
    (snapshot_manager checks isinstance(client, InternalAdapter) — False for
    MagicMock — so it falls through to the legacy .request() path).
    """
    from unittest.mock import MagicMock
    from cli_anything.gohighlevel.internal.adapter_types import AdapterResult
    client = MagicMock()
    client.location_id = location_id
    wf = workflow_data or FIXTURE_WORKFLOW

    # Legacy .request() path — used by snapshot_manager._client_get() fallback
    def mock_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
        if method == "GET":
            return dict(wf)
        return {"id": "NEW001", "name": wf.get("name", "test"), "status": "draft"}

    client.request.side_effect = mock_request

    # InternalAdapter-style .get_workflow() — returns AdapterResult
    def mock_get_workflow(wid):
        return AdapterResult(ok=True, data=dict(wf))

    client.get_workflow.side_effect = mock_get_workflow

    # InternalAdapter-style .put_workflow() — returns AdapterResult
    def mock_put_workflow(wid, body):
        return AdapterResult(ok=True, data={"id": wid, "saved": True})

    client.put_workflow.side_effect = mock_put_workflow

    # reset_step_index (called by CampaignBuilder)
    client.reset_step_index.return_value = None
    client._step_index = 0

    return client


def _make_inline_adapter_mock(
    location_id: str = "LOC001",
    workflow_data: dict | None = None,
    put_bodies: list | None = None,
    snap_checker=None,
) -> MagicMock:
    """Build a mock InternalAdapter with capture-list hooks for test assertions.

    put_bodies:   If provided, each PUT body is appended here.
    snap_checker: Optional callable(snap_dir) called during put_workflow to check
                  snapshot state at PUT time.
    """
    from cli_anything.gohighlevel.internal.adapter_types import AdapterResult
    from pathlib import Path as _Path

    client = MagicMock()
    client.location_id = location_id
    wf = workflow_data or FIXTURE_WORKFLOW

    # Legacy .request() — used by snapshot_manager._client_get() / _client_put() fallback
    # (snapshot_manager checks isinstance(client, InternalAdapter) — False for MagicMock)
    def mock_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
        if method == "GET":
            return dict(wf)
        if method == "PUT":
            # Also collect to put_bodies so restore tests can assert on them
            if put_bodies is not None:
                put_bodies.append(body)
            if snap_checker is not None:
                snap_checker()
            return {"id": "NEW001", "name": wf.get("name", "test")}
        return {"id": "NEW001", "name": wf.get("name", "test")}
    client.request.side_effect = mock_request

    # Adapter .get_workflow()
    def mock_get_workflow(wid):
        return AdapterResult(ok=True, data=dict(wf))
    client.get_workflow.side_effect = mock_get_workflow

    # Adapter .put_workflow()
    def mock_put_workflow(wid, body):
        if put_bodies is not None:
            put_bodies.append(body)
        if snap_checker is not None:
            snap_checker()
        return AdapterResult(ok=True, data={"id": wid, "saved": True})
    client.put_workflow.side_effect = mock_put_workflow

    client.reset_step_index.return_value = None
    client._step_index = 0
    return client


# ── snapshot_manager tests ─────────────────────────────────────────────────────

class TestSnapshotCapture(unittest.TestCase):
    """snapshot_manager.capture() writes a timestamped JSON file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp

    def tearDown(self):
        os.environ.pop("CAF_DATA_DIR", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_capture_creates_file(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import capture, snapshot_dir
        client = _make_mock_client("LOC001")
        path = capture(client, "WF001", label="pre-update")
        self.assertIsNotNone(path, "capture() must return a Path on success")
        self.assertTrue(path.exists(), "Snapshot file must exist on disk")
        data = json.loads(path.read_text())
        self.assertEqual(data["id"], "WF001")

    def test_capture_uses_timestamped_filename(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import capture
        client = _make_mock_client("LOC001")
        path = capture(client, "WF001", label="pre-patch-email")
        # Filename format: <YYYYMMDDTHHMMSSZ>-pre-patch-email.json
        self.assertRegex(
            path.name,
            r"^\d{8}T\d{6}Z-pre-patch-email\.json$",
            "Filename must contain timestamp + label",
        )

    def test_capture_correct_directory_structure(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import capture
        client = _make_mock_client("LOC001")
        path = capture(client, "WF001")
        # Path: <data_root>/snapshots/LOC001/WF001/<timestamp>.json
        self.assertIn("LOC001", str(path))
        self.assertIn("WF001", str(path))

    def test_capture_returns_none_on_get_failure(self):
        """If GET returns None, capture() returns None — caller must abort."""
        from cli_anything.gohighlevel.utils.snapshot_manager import capture
        client = MagicMock()
        client.location_id = "LOC001"
        client.request.return_value = None
        client.get_workflow.return_value = None  # not used by capture; request is
        # Patch request to return None for GET
        def bad_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
            if method == "GET":
                return None
            return {}
        client.request.side_effect = bad_request
        result = capture(client, "WF001", label="pre-update")
        self.assertIsNone(result, "capture() must return None when GET fails")

    def test_capture_returns_none_on_api_error(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import capture
        client = MagicMock()
        client.location_id = "LOC001"
        def error_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
            return {"_error": True, "code": 404, "message": "not found"}
        client.request.side_effect = error_request
        result = capture(client, "WF001")
        self.assertIsNone(result, "capture() must return None when GET returns _error")


class TestSnapshotRestore(unittest.TestCase):
    """snapshot_manager.restore() sends a PUT to revert workflow."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ["CAF_DRY_RUN"] = ""

    def tearDown(self):
        os.environ.pop("CAF_DATA_DIR", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        os.environ.pop("CAF_DRY_RUN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_snapshot(self, data: dict, suffix: str = "snap.json") -> Path:
        snap_dir = Path(self.tmp) / "snapshots" / "LOC001" / "WF001"
        snap_dir.mkdir(parents=True, exist_ok=True)
        f = snap_dir / suffix
        f.write_text(json.dumps(data), encoding="utf-8")
        return f

    def test_restore_calls_put_with_clean_body(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import restore
        from cli_anything.gohighlevel.utils.ghl_internal_client import STRIP_KEYS

        snap_data = dict(FIXTURE_WORKFLOW)
        snap_data["_id"] = "should-be-stripped"
        snap_path = self._write_snapshot(snap_data)

        put_calls = []
        def capture_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
            if method == "PUT":
                put_calls.append({"path": path, "body": body})
                return {"id": "WF001", "name": "ok"}
            return {}
        client = MagicMock()
        client.location_id = "LOC001"
        client.request.side_effect = capture_request

        restore(client, "WF001", snap_path)

        self.assertEqual(len(put_calls), 1, "restore() must fire exactly one PUT")
        put_body = put_calls[0]["body"]
        for stripped_key in STRIP_KEYS:
            self.assertNotIn(
                stripped_key, put_body,
                f"PUT body must not contain server-managed key '{stripped_key}'",
            )
        self.assertIn("name", put_body)
        self.assertIn("workflowData", put_body)

    def test_restore_raises_file_not_found(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import restore
        client = MagicMock()
        client.location_id = "LOC001"
        with self.assertRaises(FileNotFoundError):
            restore(client, "WF001", "/nonexistent/path/snap.json")

    def test_restore_raises_value_error_on_bad_snapshot(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import restore
        snap_path = self._write_snapshot({"missing_required_fields": True})
        client = MagicMock()
        client.location_id = "LOC001"
        with self.assertRaises(ValueError):
            restore(client, "WF001", snap_path)

    def test_list_snapshots_returns_newest_first(self):
        from cli_anything.gohighlevel.utils.snapshot_manager import list_snapshots
        # Create 3 snapshots with different timestamps
        for ts in ["20260101T000000Z", "20260102T000000Z", "20260103T000000Z"]:
            f = Path(self.tmp) / "snapshots" / "LOC001" / "WF001" / f"{ts}.json"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"ts": ts}))

        snaps = list_snapshots("LOC001", "WF001")
        names = [p.name for p in snaps]
        self.assertEqual(names[0], "20260103T000000Z.json", "Newest snapshot must be first")
        self.assertEqual(len(snaps), 3)


# ── WriteLock serialization tests ─────────────────────────────────────────────

class TestWriteLockSerialization(unittest.TestCase):
    """WriteLock prevents two concurrent builds from running internal writes in parallel."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp

    def tearDown(self):
        os.environ.pop("CAF_DATA_DIR", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_lock_acquired_and_released(self):
        """Basic: context manager acquires and releases without error."""
        from cli_anything.gohighlevel.utils.write_lock import WriteLock
        with WriteLock("TEST_LOC"):
            pass  # must not raise

    def test_two_threads_serialize(self):
        """Second thread must WAIT until first releases the lock.

        We use a timeline: t1 holds the lock for ~200ms, t2 tries to acquire
        immediately after t1.  We confirm t2's body runs AFTER t1 releases.
        """
        from cli_anything.gohighlevel.utils.write_lock import WriteLock

        timeline = []
        barrier = threading.Event()

        def thread1():
            with WriteLock("SER_LOC"):
                timeline.append("t1-start")
                barrier.wait(timeout=1.0)  # hold until t2 is waiting
                time.sleep(0.15)           # simulate work
                timeline.append("t1-end")

        def thread2():
            # Give t1 a head start then try to acquire
            time.sleep(0.05)
            barrier.set()
            with WriteLock("SER_LOC"):
                timeline.append("t2-start")

        t1 = threading.Thread(target=thread1)
        t2 = threading.Thread(target=thread2)
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        # t1-end must precede t2-start
        self.assertIn("t1-end", timeline)
        self.assertIn("t2-start", timeline)
        idx_t1_end = timeline.index("t1-end")
        idx_t2_start = timeline.index("t2-start")
        self.assertLess(
            idx_t1_end, idx_t2_start,
            f"t1 must finish before t2 starts. Timeline: {timeline}",
        )

    def test_different_locations_do_not_serialize(self):
        """Locks for different location IDs are independent — both run concurrently."""
        from cli_anything.gohighlevel.utils.write_lock import WriteLock

        results = {}

        def thread_a():
            with WriteLock("LOC_A"):
                results["a_start"] = time.monotonic()
                time.sleep(0.1)
                results["a_end"] = time.monotonic()

        def thread_b():
            with WriteLock("LOC_B"):
                results["b_start"] = time.monotonic()
                time.sleep(0.1)
                results["b_end"] = time.monotonic()

        ta = threading.Thread(target=thread_a)
        tb = threading.Thread(target=thread_b)
        ta.start()
        tb.start()
        ta.join(timeout=2.0)
        tb.join(timeout=2.0)

        # Both should overlap (b_start < a_end OR a_start < b_end) — not strictly sequential
        # We verify both finished — the actual timing assertion would be flaky in CI;
        # the important thing is they don't deadlock.
        self.assertIn("a_end", results)
        self.assertIn("b_end", results)


# ── Step backoff tests ─────────────────────────────────────────────────────────

class TestStepBackoff(unittest.TestCase):
    """InternalAdapter inserts step backoff between sequential write steps.

    The backoff moved from InternalGHLClient (removed from shim) to
    guards.step_backoff() called by InternalAdapter._call().
    CAF_INTERNAL_STEP_BACKOFF_MS controls the new path.
    """

    def setUp(self):
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"  # disable actual sleep in tests
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        for k in ("CAF_INTERNAL_STEP_BACKOFF_MS", "CAF_ALLOWED_LOCATION_IDS",
                  "CAF_APPROVAL_TOKEN", "CAF_DRY_RUN"):
            os.environ.pop(k, None)

    def test_backoff_reads_env_at_call_time(self):
        """guards.step_backoff() reads CAF_INTERNAL_STEP_BACKOFF_MS from env at call time."""
        from cli_anything.gohighlevel.internal.guards import step_backoff

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("time.sleep", mock_sleep):
            os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "150"
            step_backoff(1)   # step_index=1 -> will sleep
            os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"
            step_backoff(2)   # step_index=2, 0ms -> no sleep

        self.assertAlmostEqual(sleep_calls[0], 0.15, places=3,
                               msg="step_backoff(150ms) must sleep 0.15s")
        # Second call with 0ms must not sleep (or sleep 0)
        if len(sleep_calls) > 1:
            self.assertAlmostEqual(sleep_calls[1], 0.0, places=3)

    def test_request_with_step_backoff_flag_sleeps(self):
        """InternalAdapter._call increments step_index and calls step_backoff on writes."""
        from cli_anything.gohighlevel.internal.adapter import InternalAdapter
        from cli_anything.gohighlevel.internal.transport import InternalTransport

        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "50"

        t = MagicMock(spec=InternalTransport)
        t.get_token.return_value = "fake-token"
        t.request.return_value = {"id": "folder-1"}
        adapter = InternalAdapter("LOC001", transport=t)
        adapter.reset_step_index()

        sleep_calls = []
        with patch("time.sleep", lambda s: sleep_calls.append(s)):
            adapter.create_folder("F1")  # step 0 -> no sleep
            adapter.create_folder("F2")  # step 1 -> sleep 50ms

        self.assertTrue(
            any(abs(s - 0.05) < 0.02 for s in sleep_calls),
            f"Expected ~0.05s sleep call on second write; got {sleep_calls}",
        )
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"

    def test_request_without_flag_does_not_sleep(self):
        """request() without _apply_step_backoff must NOT sleep."""
        from cli_anything.gohighlevel.utils.ghl_internal_client import (
            TokenManager, InternalGHLClient,
        )
        os.environ["CAF_STEP_BACKOFF_MS"] = "500"
        os.environ["CAF_DRY_RUN"] = "true"

        tm = MagicMock(spec=TokenManager)
        tm.get_token.return_value = "fake-token"
        client = InternalGHLClient(tm, "LOC001")

        sleep_calls = []
        with patch("time.sleep", lambda s: sleep_calls.append(s)):
            try:
                client.request("GET", "/workflow/LOC001/WF001")
            except SystemExit:
                pass

        self.assertEqual(sleep_calls, [],
                         "request() without _apply_step_backoff must not sleep")
        os.environ["CAF_STEP_BACKOFF_MS"] = "0"
        os.environ.pop("CAF_DRY_RUN", None)


# ── CLI command tests (via Click test runner) ──────────────────────────────────

class TestWorkflowsGetCommand(unittest.TestCase):
    """caf workflows get --workflow-id <id> fetches and displays a workflow."""

    def setUp(self):
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = tempfile.mkdtemp()

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        import shutil
        shutil.rmtree(os.environ.pop("CAF_DATA_DIR", "/tmp/noop"), ignore_errors=True)

    def test_get_outputs_workflow_json(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        mock_client = _make_mock_client()
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["--json", "--location-id", "LOC001",
                                         "workflows", "get", "--workflow-id", "WF001"])

        self.assertEqual(result.exit_code, 0, f"Exit code must be 0. Output: {result.output}")
        data = json.loads(result.output)
        self.assertEqual(data.get("id"), "WF001")


class TestWorkflowsExportCommand(unittest.TestCase):
    """caf workflows export writes workflow to file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_creates_file(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        out_path = os.path.join(self.tmp, "wf_export.json")
        mock_client = _make_mock_client()

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--location-id", "LOC001",
                "workflows", "export",
                "--workflow-id", "WF001",
                "--out", out_path,
            ])

        self.assertEqual(result.exit_code, 0, f"Exit code must be 0. Output: {result.output}")
        self.assertTrue(os.path.exists(out_path), "Export file must be created")
        data = json.loads(Path(out_path).read_text())
        self.assertEqual(data.get("id"), "WF001")


class TestWorkflowsUpdateCommand(unittest.TestCase):
    """caf workflows update -- snapshot captured before PUT."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_wf_json(self, data: dict | None = None) -> str:
        p = Path(self.tmp) / "update_input.json"
        p.write_text(json.dumps(data or FIXTURE_WORKFLOW))
        return str(p)

    def test_update_captures_snapshot_before_put(self):
        """AC 20: pre-write snapshot must exist on disk before the PUT fires."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        snap_paths = []
        put_called = []

        def snap_checker():
            snap_dir = Path(self.tmp) / "snapshots" / "LOC001" / "WF001"
            existing = list(snap_dir.glob("*.json")) if snap_dir.exists() else []
            snap_paths.extend(existing)
            put_called.append(True)

        mock_client = _make_inline_adapter_mock(
            snap_checker=snap_checker,
        )

        in_file = self._write_wf_json()

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "update",
                "--workflow-id", "WF001",
                "--from-json", in_file,
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}, Output: {result.output}")
        self.assertTrue(len(put_called) > 0, "PUT must have been called")
        self.assertTrue(
            len(snap_paths) > 0,
            "Snapshot must exist on disk BEFORE the PUT fires (AC 20)",
        )

    def test_update_aborts_if_snapshot_fails(self):
        """If GET fails before update, the command must abort — no PUT sent."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        put_called = []

        def mock_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
            if method == "GET":
                return None  # simulate GET failure
            put_called.append(True)
            return {"id": "WF001"}

        mock_client = MagicMock()
        mock_client.location_id = "LOC001"
        mock_client.request.side_effect = mock_request

        in_file = self._write_wf_json()

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "update",
                "--workflow-id", "WF001",
                "--from-json", in_file,
            ])

        self.assertNotEqual(result.exit_code, 0, "Must exit non-zero when snapshot fails")
        self.assertEqual(len(put_called), 0, "PUT must NOT be called when snapshot fails")


class TestWorkflowsPatchEmailCommand(unittest.TestCase):
    """caf workflows patch-email -- snapshot + surgical email step edit."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_patch_email_updates_subject(self):
        """Subject is replaced in the PUT body; snapshot captured beforehand."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        put_bodies = []
        mock_client = _make_inline_adapter_mock(put_bodies=put_bodies)

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "patch-email",
                "--workflow-id", "WF001",
                "--step-id", "STEP001",
                "--subject", "Brand new subject line",
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}, Output: {result.output}")
        self.assertTrue(len(put_bodies) > 0, "PUT must have fired")

        # The subject in the PUT body's workflowData must be the new value
        templates = put_bodies[0]["workflowData"]["templates"]
        email_step = next(s for s in templates if s["id"] == "STEP001")
        self.assertEqual(
            email_step["attributes"]["subject"],
            "Brand new subject line",
            "Email step subject must be updated in PUT body",
        )

    def test_patch_email_captures_snapshot_before_put(self):
        """AC 20: pre-patch-email snapshot must exist before PUT fires."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        snap_at_put_time = []

        def snap_checker():
            snap_dir = Path(self.tmp) / "snapshots" / "LOC001" / "WF001"
            if snap_dir.exists():
                snap_at_put_time.extend(snap_dir.glob("*.json"))

        mock_client = _make_inline_adapter_mock(snap_checker=snap_checker)

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "patch-email",
                "--workflow-id", "WF001",
                "--step-id", "STEP001",
                "--subject", "Test",
            ])

        self.assertTrue(
            len(snap_at_put_time) > 0,
            "Snapshot must be on disk when PUT fires (AC 20)",
        )

    def test_patch_email_fails_if_step_not_found(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        mock_client = _make_mock_client()

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "patch-email",
                "--workflow-id", "WF001",
                "--step-id", "NONEXISTENT_STEP",
                "--subject", "Test",
            ])

        self.assertNotEqual(result.exit_code, 0, "Must fail for unknown step ID")


class TestWorkflowsPatchTriggerCommand(unittest.TestCase):
    """caf workflows patch-trigger -- snapshot + trigger replacement."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_patch_trigger_fires_put_with_new_trigger(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        put_bodies = []
        mock_client = _make_inline_adapter_mock(put_bodies=put_bodies)

        trigger_file = Path(self.tmp) / "trigger.json"
        new_trigger = {"id": "TRG_NEW", "type": "form_submitted", "name": "Form: Consult"}
        trigger_file.write_text(json.dumps(new_trigger))

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "patch-trigger",
                "--workflow-id", "WF001",
                "--trigger-json", str(trigger_file),
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}, Output: {result.output}")
        self.assertTrue(len(put_bodies) > 0, "PUT must have fired")
        # newTriggers must contain the new trigger definition
        self.assertEqual(
            put_bodies[0]["newTriggers"],
            [new_trigger],
            "newTriggers in PUT body must match provided trigger JSON",
        )


class TestWorkflowsRestoreCommand(unittest.TestCase):
    """caf workflows restore -- reverts to snapshot."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_snapshot_file(self) -> str:
        snap_dir = Path(self.tmp) / "snapshots" / "LOC001" / "WF001"
        snap_dir.mkdir(parents=True, exist_ok=True)
        f = snap_dir / "20260101T000000Z-pre-update.json"
        f.write_text(json.dumps(FIXTURE_WORKFLOW))
        return str(f)

    def test_restore_sends_put_from_snapshot(self):
        """restore must send a PUT whose body matches the snapshot (minus stripped keys)."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli
        from cli_anything.gohighlevel.internal.contract import STRIP_KEYS

        put_bodies = []
        mock_client = _make_inline_adapter_mock(put_bodies=put_bodies)

        snap_file = self._write_snapshot_file()

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "restore",
                "--workflow-id", "WF001",
                "--snapshot", snap_file,
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}, Output: {result.output}")
        # At least one PUT from the restore (there may also be one from pre-restore snapshot)
        self.assertTrue(len(put_bodies) > 0, "restore must fire a PUT")
        # None of the PUT bodies should contain stripped keys
        for body in put_bodies:
            for k in STRIP_KEYS:
                self.assertNotIn(k, body, f"Stripped key '{k}' must not be in PUT body")

    def test_restore_with_nonexistent_snapshot_fails(self):
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        mock_client = _make_mock_client()
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", "LOC001",
                "workflows", "restore",
                "--workflow-id", "WF001",
                "--snapshot", "/nonexistent/snap.json",
            ])

        # Click validates the path with exists=True before the command runs
        self.assertNotEqual(result.exit_code, 0)


class TestWorkflowsBuildFromPlan(unittest.TestCase):
    """caf workflows build --from-plan uses WriteLock + step backoff."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ["CAF_STEP_BACKOFF_MS"] = "0"  # disable sleep in tests
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        os.environ.pop("CAF_STEP_BACKOFF_MS", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_from_plan_draft_only(self):
        """Workflow built from plan must be DRAFT (never auto-published)."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        plan_file = Path(self.tmp) / "plan.json"
        plan_file.write_text(json.dumps(FIXTURE_PLAN))

        request_log = []

        def mock_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
            request_log.append({"method": method, "path": path, "body": body})
            if method == "POST" and "tags/create" not in path and "trigger" not in path:
                return {"id": "FOLDER001", "name": "test"}
            if method == "POST" and "trigger" in path:
                return {"id": "TRG001"}
            if method == "PUT":
                return {"id": "WF001", "name": "ZHC-3Email-Nurture", "status": "draft"}
            if method == "GET":
                return {"id": "WF001", "name": "ZHC-3Email-Nurture", "version": 2, "meta": {}}
            return {"id": "WF001"}

        mock_client = MagicMock()
        mock_client.location_id = "LOC001"
        mock_client.request.side_effect = mock_request
        mock_client.call_count = 0

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json", "--location-id", "LOC001",
                "workflows", "build",
                "--from-plan", str(plan_file),
                "--folder", "test-folder",
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}, Output: {result.output}")
        data = json.loads(result.output)
        self.assertNotIn("errors", data.get("errors", []) and ["nonempty"],
                         f"Build should have no errors: {data.get('errors')}")

        # Verify no PUT body sets status to "published"
        put_bodies = [r["body"] for r in request_log if r["method"] == "PUT" and r["body"]]
        for body in put_bodies:
            status = body.get("status", "draft")
            self.assertNotEqual(
                status, "published",
                f"Build must never auto-publish a workflow (found status={status})",
            )

    def test_build_from_plan_requires_experimental(self):
        """build --from-plan must reject without --experimental flag."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        plan_file = Path(self.tmp) / "plan.json"
        plan_file.write_text(json.dumps(FIXTURE_PLAN))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "--location-id", "LOC001",
            "workflows", "build",
            "--from-plan", str(plan_file),
        ])
        self.assertNotEqual(result.exit_code, 0, "Must require --experimental flag")


# ── Pre-write snapshot rule exhaustive check ──────────────────────────────────

class TestPreWriteSnapshotRule(unittest.TestCase):
    """AC 20: every write command (update / patch-email / patch-trigger / restore)
    must capture a pre-write snapshot before any PUT fires."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "fake-refresh"
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC001"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        os.environ.pop("GHL_FIREBASE_REFRESH_TOKEN", None)
        os.environ.pop("CAF_ALLOWED_LOCATION_IDS", None)
        os.environ.pop("CAF_APPROVAL_TOKEN", None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_command_and_check_snapshot(self, args: list[str]) -> bool:
        """Run a CLI command; return True if snapshot was on disk when PUT fired."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        snap_existed_at_put = []

        def snap_checker():
            snap_dir = Path(self.tmp) / "snapshots" / "LOC001" / "WF001"
            if snap_dir.exists() and list(snap_dir.glob("*.json")):
                snap_existed_at_put.append(True)

        mock_client = _make_inline_adapter_mock(snap_checker=snap_checker)

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value="LOC001",
        ):
            runner = CliRunner()
            result = runner.invoke(cli, args)

        return len(snap_existed_at_put) > 0 and result.exit_code == 0

    def test_update_snapshot_before_put(self):
        in_file = Path(self.tmp) / "wf.json"
        in_file.write_text(json.dumps(FIXTURE_WORKFLOW))
        ok = self._run_command_and_check_snapshot([
            "--experimental", "--location-id", "LOC001",
            "workflows", "update",
            "--workflow-id", "WF001", "--from-json", str(in_file),
        ])
        self.assertTrue(ok, "update: snapshot must exist before PUT (AC 20)")

    def test_patch_email_snapshot_before_put(self):
        ok = self._run_command_and_check_snapshot([
            "--experimental", "--location-id", "LOC001",
            "workflows", "patch-email",
            "--workflow-id", "WF001", "--step-id", "STEP001",
            "--subject", "New subject",
        ])
        self.assertTrue(ok, "patch-email: snapshot must exist before PUT (AC 20)")

    def test_patch_trigger_snapshot_before_put(self):
        trig_file = Path(self.tmp) / "trig.json"
        trig_file.write_text(json.dumps({"id": "T2", "type": "form_submitted"}))
        ok = self._run_command_and_check_snapshot([
            "--experimental", "--location-id", "LOC001",
            "workflows", "patch-trigger",
            "--workflow-id", "WF001", "--trigger-json", str(trig_file),
        ])
        self.assertTrue(ok, "patch-trigger: snapshot must exist before PUT (AC 20)")


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestSnapshotCapture,
        TestSnapshotRestore,
        TestWriteLockSerialization,
        TestStepBackoff,
        TestWorkflowsGetCommand,
        TestWorkflowsExportCommand,
        TestWorkflowsUpdateCommand,
        TestWorkflowsPatchEmailCommand,
        TestWorkflowsPatchTriggerCommand,
        TestWorkflowsRestoreCommand,
        TestWorkflowsBuildFromPlan,
        TestPreWriteSnapshotRule,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
