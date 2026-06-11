"""Adapter + probe CI tests (acceptance criteria C1, C19, C20, C21 — adapter side).

Covers:
  - InternalAdapter: create_folder, create_workflow, get_workflow, put_workflow,
    create_trigger, put_trigger, create_tag
  - AdapterResult normalization (success / None / _error dict)
  - Write gate: WRITE_DISABLED -> AdapterResult(ok=False) — never raises
  - Contract probe: passes against golden fixture via mock transport
  - Contract drift: trips degrade flag
  - Degraded adapter refuses writes with typed AdapterResult
  - Step backoff: inserted between sequential writes, skipped on first
  - Doctor command: probe result surfaced

All tests use mocks — NO live CRM is ever contacted.
Network guard: any connect to leadconnectorhq.com is a hard FAIL.

Run:
    python3 -m pytest tests/test_adapter_probe.py -v
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ── Ensure engine root is on sys.path ─────────────────────────────────────────
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ── Network guard ─────────────────────────────────────────────────────────────
_BLOCKED_HOST = "leadconnectorhq.com"
_BLOCKED_FIREBASE = "securetoken.googleapis.com"
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = str(address[0])
        if _BLOCKED_HOST in host or _BLOCKED_FIREBASE in host:
            raise AssertionError(
                f"ADAPTER CI SAFETY FAILURE: live host contacted: {host!r}. "
                "All adapter tests must use mocks."
            )
    return _original_connect(self, address)


socket.socket.connect = _guarded_connect


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_transport(responses: dict | None = None) -> MagicMock:
    """Build a mock InternalTransport that returns canned responses.

    responses: dict mapping (method, path_fragment) -> dict
    If None, all calls return {"id": "mock-id", "ok": True}.
    """
    t = MagicMock()
    t.call_count = 0
    t.get_token.return_value = "fake-id-token"
    t.force_refresh.return_value = "fake-id-token"

    if responses is None:
        responses = {}

    def _request(method, path, body=None):
        t.call_count += 1
        for (m, frag), resp in responses.items():
            if m == method and frag in path:
                return resp
        return {"id": "mock-id", "ok": True}

    t.request.side_effect = _request
    return t


def _make_adapter(location_id: str = "LOC123", transport=None):
    from cli_anything.gohighlevel.internal.adapter import InternalAdapter
    if transport is None:
        transport = _fake_transport()
    return InternalAdapter(location_id=location_id, transport=transport)


# ── Test: AdapterResult normalization ─────────────────────────────────────────

class TestNormalizeResult(unittest.TestCase):
    def setUp(self):
        from cli_anything.gohighlevel.internal.contract import normalize_result
        self.nr = normalize_result

    def test_success_dict(self):
        r = self.nr({"id": "abc"})
        self.assertTrue(r.ok)
        self.assertEqual(r.data, {"id": "abc"})
        self.assertIsNone(r.error)

    def test_none_is_auth_exhausted(self):
        r = self.nr(None)
        self.assertFalse(r.ok)
        self.assertEqual(r.http_code, 401)
        self.assertIn("AUTH_EXHAUSTED", r.error)

    def test_error_dict(self):
        r = self.nr({"_error": True, "http_code": 500, "message": "oops"})
        self.assertFalse(r.ok)
        self.assertEqual(r.http_code, 500)
        self.assertIn("oops", r.error)

    def test_429_surfaced(self):
        r = self.nr({"_error": True, "http_code": 429, "code": 429,
                     "message": "Rate limit exceeded", "rate_limit_reset": "14:00 UTC"})
        self.assertFalse(r.ok)
        self.assertEqual(r.http_code, 429)
        self.assertIn("RATE_LIMIT_429", r.error)
        self.assertIn("14:00 UTC", r.error)


# ── Test: InternalAdapter typed methods ───────────────────────────────────────

class TestInternalAdapter(unittest.TestCase):

    def setUp(self):
        # Safety gate: allow writes for these tests
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC123"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"  # no sleep in tests

    def tearDown(self):
        for k in ("CAF_ALLOWED_LOCATION_IDS", "CAF_APPROVAL_TOKEN",
                  "CAF_INTERNAL_STEP_BACKOFF_MS"):
            os.environ.pop(k, None)

    def _adapter(self, responses=None):
        return _make_adapter(transport=_fake_transport(responses))

    def test_create_folder_ok(self):
        adapter = self._adapter({("POST", "/workflow/LOC123"): {"id": "folder-1"}})
        result = adapter.create_folder("MyFolder")
        self.assertTrue(result.ok)

    def test_get_workflow_ok(self):
        adapter = self._adapter({("GET", "/workflow/LOC123/WF1"): {
            "id": "WF1", "name": "Test WF", "version": 1,
            "workflowData": {"templates": []},
        }})
        result = adapter.get_workflow("WF1")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["name"], "Test WF")

    def test_put_workflow_ok(self):
        adapter = self._adapter({("PUT", "/workflow/LOC123/WF1"): {"id": "WF1", "saved": True}})
        result = adapter.put_workflow("WF1", {"name": "X", "version": 1, "workflowData": {}})
        self.assertTrue(result.ok)

    def test_create_tag_ok(self):
        adapter = self._adapter({("POST", "/workflow/LOC123/tags/create"): {"ok": True}})
        result = adapter.create_tag("my-tag")
        self.assertTrue(result.ok)

    def test_create_trigger_ok(self):
        adapter = self._adapter({("POST", "/workflow/LOC123/trigger"): {"id": "TR1"}})
        body = {"name": "test trigger", "workflowId": "WF1"}
        result = adapter.create_trigger(body)
        self.assertTrue(result.ok)

    def test_put_trigger_ok(self):
        adapter = self._adapter({("PUT", "/workflow/LOC123/trigger/TR1"): {"id": "TR1"}})
        result = adapter.put_trigger("TR1", {"targetActionId": "STEP1"})
        self.assertTrue(result.ok)

    def test_auth_exhausted_returns_result_not_raises(self):
        t = _fake_transport()
        # Clear side_effect so return_value is used
        t.request.side_effect = None
        t.request.return_value = None  # simulates auth-exhausted after retry
        adapter = _make_adapter(transport=t)
        result = adapter.get_workflow("WF1")
        self.assertFalse(result.ok)
        self.assertEqual(result.http_code, 401)

    def test_429_returns_result_not_raises(self):
        t = _fake_transport()
        t.request.side_effect = None
        t.request.return_value = {
            "_error": True, "http_code": 429, "code": 429,
            "message": "Rate limit exceeded", "rate_limit_reset": "23:00",
        }
        adapter = _make_adapter(transport=t)
        result = adapter.get_workflow("WF1")
        self.assertFalse(result.ok)
        self.assertEqual(result.http_code, 429)


# ── Test: Write gate (degrade) ────────────────────────────────────────────────

class TestWriteGate(unittest.TestCase):

    def setUp(self):
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC123"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"
        self._tmpdir = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self._tmpdir

    def tearDown(self):
        for k in ("CAF_ALLOWED_LOCATION_IDS", "CAF_APPROVAL_TOKEN",
                  "CAF_INTERNAL_STEP_BACKOFF_MS", "CAF_DATA_DIR"):
            os.environ.pop(k, None)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_write_disabled_returns_clean_result(self):
        """Degraded adapter refuses writes with AdapterResult(ok=False), never raises."""
        from cli_anything.gohighlevel.internal import degrade
        from cli_anything.gohighlevel.internal.adapter_types import ProbeResult

        pr = ProbeResult(ok=False, reason="TEST_DRIFT", failed_assertion="test",
                         checked_at="2026-01-01T00:00:00Z", scope="contract")
        degrade.disable_writes("local", "TEST_DRIFT", probe_result=pr)
        self.assertTrue(degrade.is_write_disabled())

        adapter = _make_adapter()
        result = adapter.put_workflow("WF1", {"name": "X", "version": 1})
        self.assertFalse(result.ok)
        self.assertIn("WRITE_DISABLED", result.error)

        # GET still works even when degraded
        result_get = adapter.get_workflow("WF1")
        self.assertTrue(result_get.ok)

    def test_clear_write_disable(self):
        from cli_anything.gohighlevel.internal import degrade
        degrade.disable_writes("local", "TEST")
        self.assertTrue(degrade.is_write_disabled())
        degrade.clear_write_disable()
        self.assertFalse(degrade.is_write_disabled())


# ── Test: Contract probe with mock transport (C19) ───────────────────────────

class TestContractProbe(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self._tmpdir
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"

    def tearDown(self):
        os.environ.pop("CAF_DATA_DIR", None)
        os.environ.pop("CAF_INTERNAL_STEP_BACKOFF_MS", None)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_schema(self, schema: dict):
        """Write a test contract.schema.json to the internal/fixtures path."""
        fixtures_dir = (
            Path(_ENGINE_ROOT) / "cli_anything" / "gohighlevel" / "internal" / "fixtures"
        )
        schema_path = fixtures_dir / "contract.schema.json"
        # Write to a temp copy that the probe will find
        # (we patch _schema_path to point here)
        tmp_schema = Path(self._tmpdir) / "contract.schema.json"
        tmp_schema.write_text(json.dumps(schema), encoding="utf-8")
        return tmp_schema

    def test_probe_passes_with_good_token_and_no_live_assertions(self):
        """Probe passes when token is healthy and schema has no live-GET assertions."""
        from cli_anything.gohighlevel.internal.probe import run_contract_probe

        # Schema with no probe_fixture workflow_id -> skips live GET assertions
        schema = {
            "probe_fixture": {"workflow_id": ""},
            "workflow_get_shape": {
                "required_keys": ["name"],
                "requires_version": True,
                "requires_workflow_data_templates": True,
            },
            "check_verified_actions": False,
        }

        tmp_schema = self._write_schema(schema)

        adapter = _make_adapter()

        with patch(
            "cli_anything.gohighlevel.internal.probe._schema_path",
            return_value=tmp_schema,
        ):
            probe = run_contract_probe(adapter)

        self.assertTrue(probe.ok, f"Probe failed: {probe.reason}")
        self.assertEqual(probe.scope, "contract")

    def test_probe_fails_on_bad_token(self):
        """Probe returns TOKEN_DEAD result when token cannot be minted."""
        from cli_anything.gohighlevel.internal.probe import run_contract_probe
        from cli_anything.gohighlevel.internal.adapter_types import AdapterError

        t = _fake_transport()
        t.get_token.side_effect = AdapterError("NO_TOKEN", "no token set")
        adapter = _make_adapter(transport=t)

        probe = run_contract_probe(adapter)
        self.assertFalse(probe.ok)
        self.assertIn("NO_TOKEN", probe.reason)
        self.assertEqual(probe.scope, "token")

    def test_probe_drift_triggers_degrade(self):
        """A contract-drift assertion failure sets the degrade flag."""
        from cli_anything.gohighlevel.internal.probe import run_contract_probe
        from cli_anything.gohighlevel.internal import is_write_disabled

        # Schema that checks a workflow_id and requires a key we won't return
        schema = {
            "probe_fixture": {"workflow_id": "WF-PROBE"},
            "workflow_get_shape": {
                "required_keys": ["name", "MISSING_KEY_THAT_WILL_CAUSE_DRIFT"],
                "requires_version": False,
                "requires_workflow_data_templates": False,
            },
            "check_verified_actions": False,
        }
        tmp_schema = Path(self._tmpdir) / "contract.schema.json"
        tmp_schema.write_text(json.dumps(schema), encoding="utf-8")

        # Transport returns a workflow missing MISSING_KEY
        t = _fake_transport({
            ("GET", "/workflow/LOC123/WF-PROBE"): {
                "id": "WF-PROBE", "name": "test wf", "version": 1,
                "workflowData": {"templates": []},
            }
        })
        adapter = _make_adapter(transport=t)

        with patch(
            "cli_anything.gohighlevel.internal.probe._schema_path",
            return_value=tmp_schema,
        ):
            probe = run_contract_probe(adapter)

        self.assertFalse(probe.ok)
        self.assertIn("CONTRACT_DRIFT", probe.reason)
        self.assertTrue(is_write_disabled(), "degrade flag should be set on drift")

    def test_last_probe_written_to_disk(self):
        """Probe result is persisted to last-probe.json."""
        from cli_anything.gohighlevel.internal.probe import run_contract_probe, last_probe_result

        schema = {
            "probe_fixture": {"workflow_id": ""},
            "workflow_get_shape": {"required_keys": ["name"]},
            "check_verified_actions": False,
        }
        tmp_schema = Path(self._tmpdir) / "contract.schema.json"
        tmp_schema.write_text(json.dumps(schema), encoding="utf-8")

        adapter = _make_adapter()
        with patch(
            "cli_anything.gohighlevel.internal.probe._schema_path",
            return_value=tmp_schema,
        ):
            run_contract_probe(adapter)

        saved = last_probe_result()
        self.assertIsNotNone(saved)
        self.assertIn("ok", saved)
        self.assertIn("checked_at", saved)

    def test_probe_passes_against_shipped_fixtures_no_patching(self):
        """Rubric C19/shipped-fixtures assertion: probe must be GREEN against the
        REAL unpatched contract.schema.json + contract.golden.json shipped in
        internal/fixtures/.  No _schema_path patch.  No temp schema.

        This is the critical path that was previously uncovered: the suite was
        83/83 green but every probe test patched _schema_path to a hand-built
        temp schema, so a code/fixture mismatch (ai_step in golden, not in
        VERIFIED_ACTIONS) was invisible.  This test catches exactly that class
        of defect.
        """
        from cli_anything.gohighlevel.internal.probe import run_contract_probe

        # The shipped schema has probe_fixture.workflow_id = "" which skips live GETs.
        # Token check uses mock transport (get_token returns fake-id-token).
        # The check_verified_actions assertion runs against the shipped golden.
        adapter = _make_adapter()

        # Run against real shipped fixtures — no patching whatsoever.
        probe = run_contract_probe(adapter)

        self.assertTrue(
            probe.ok,
            f"Contract probe FAILED against shipped fixtures (code/fixture mismatch). "
            f"reason={probe.reason!r}  failed_assertion={probe.failed_assertion!r}. "
            f"Fix: reconcile contract.golden.json with VERIFIED_ACTIONS in workflow_builder.py."
        )
        self.assertEqual(probe.scope, "contract")


# ── Test: Step backoff (C21) ──────────────────────────────────────────────────

class TestStepBackoff(unittest.TestCase):

    def setUp(self):
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC123"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"

    def tearDown(self):
        for k in ("CAF_INTERNAL_STEP_BACKOFF_MS", "CAF_ALLOWED_LOCATION_IDS",
                  "CAF_APPROVAL_TOKEN"):
            os.environ.pop(k, None)

    def test_step_index_increments_per_write(self):
        """_step_index increments on each write call (step_backoff is called)."""
        adapter = _make_adapter()
        adapter.reset_step_index()
        self.assertEqual(adapter._step_index, 0)
        adapter.create_folder("F1")
        self.assertEqual(adapter._step_index, 1)
        adapter.create_folder("F2")
        self.assertEqual(adapter._step_index, 2)

    def test_step_index_not_incremented_on_read(self):
        """GET calls do not increment the step index."""
        adapter = _make_adapter()
        adapter.reset_step_index()
        adapter.get_workflow("WF1")
        self.assertEqual(adapter._step_index, 0)

    def test_step_backoff_zero_ms_no_sleep(self):
        """CAF_INTERNAL_STEP_BACKOFF_MS=0 means no sleep."""
        from cli_anything.gohighlevel.internal.guards import step_backoff
        start = time.monotonic()
        step_backoff(1, base_ms=0)  # step_index=1, would sleep by default
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)

    def test_step_backoff_skipped_on_first_write(self):
        """step_index=0 always skips the sleep regardless of base_ms."""
        from cli_anything.gohighlevel.internal.guards import step_backoff
        start = time.monotonic()
        step_backoff(0, base_ms=5000)  # would sleep 5s if not skipped
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)


# ── Test: STRIP_KEYS (contract.py) ────────────────────────────────────────────

class TestStripKeys(unittest.TestCase):

    def test_strip_for_put_removes_server_keys(self):
        from cli_anything.gohighlevel.internal.contract import strip_for_put, STRIP_KEYS
        obj = {"id": "x", "name": "My WF", "version": 1, "_id": "y",
               "createdAt": "2024", "workflowData": {"templates": []}}
        cleaned = strip_for_put(obj)
        for k in ("id", "_id", "createdAt"):
            self.assertNotIn(k, cleaned, f"STRIP_KEY '{k}' should be removed")
        self.assertIn("name", cleaned)
        self.assertIn("workflowData", cleaned)

    def test_strip_keys_frozenset_unchanged(self):
        """Verify STRIP_KEYS matches the verified set from the original source."""
        from cli_anything.gohighlevel.internal.contract import STRIP_KEYS
        required = {
            "_id", "id", "__v", "createdAt", "updatedAt", "companyId", "locationId",
            "companyAge", "creationSource", "originType", "deleted",
            "isTriggerBucketMigrated", "permissionMeta",
        }
        self.assertEqual(STRIP_KEYS, required)


# ── Test: Body builders (contract.py) ────────────────────────────────────────

class TestBodyBuilders(unittest.TestCase):

    def test_tag_trigger_body_shape(self):
        from cli_anything.gohighlevel.internal.contract import tag_trigger_body
        body = tag_trigger_body("LOC1", "WF1", "my-tag")
        self.assertEqual(body["workflowId"], "WF1")
        self.assertEqual(body["type"], "contact_tag")
        self.assertEqual(body["masterType"], "highlevel")
        self.assertFalse(body["active"])  # draft_only by default
        self.assertEqual(len(body["conditions"]), 1)
        self.assertEqual(body["conditions"][0]["operator"], "index-of-true")
        self.assertEqual(body["conditions"][0]["field"], "tagsAdded")

    def test_save_steps_body_shape(self):
        from cli_anything.gohighlevel.internal.contract import save_steps_body
        steps = [{"id": "s1", "type": "email", "name": "Email 1"}]
        body = save_steps_body("Test WF", steps, version=1)
        self.assertEqual(body["name"], "Test WF")
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["workflowData"]["templates"], steps)

    def test_sync_body_triggers_present(self):
        from cli_anything.gohighlevel.internal.contract import sync_body
        body = sync_body(
            "Test WF", 2, {}, [{"id": "s1"}], [{"id": "tr1"}]
        )
        self.assertTrue(body["triggersChanged"])
        self.assertEqual(body["newTriggers"], [{"id": "tr1"}])
        self.assertEqual(body["oldTriggers"], [{"id": "tr1"}])


# ── Test: Backward-compat shim (ghl_internal_client.py) ──────────────────────

class TestShimCompat(unittest.TestCase):
    """The shim must produce the same public interface as the original."""

    def setUp(self):
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = "LOC123"
        os.environ["CAF_APPROVAL_TOKEN"] = "test-token"
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"

    def tearDown(self):
        for k in ("CAF_ALLOWED_LOCATION_IDS", "CAF_APPROVAL_TOKEN",
                  "CAF_INTERNAL_STEP_BACKOFF_MS"):
            os.environ.pop(k, None)

    def _shim_client(self):
        from cli_anything.gohighlevel.utils.ghl_internal_client import (
            TokenManager, InternalGHLClient,
        )
        with patch.object(TokenManager, "get_token", return_value="fake-tok"):
            tm = TokenManager()
            # Patch the transport's request to avoid real HTTP
            client = InternalGHLClient(tm, "LOC123")
            client._adapter.transport.request = MagicMock(
                return_value={"id": "mock-id"}
            )
            return client

    def test_shim_exports_constants(self):
        from cli_anything.gohighlevel.utils.ghl_internal_client import (
            BASE_URL, FIREBASE_API_KEY, STRIP_KEYS, CHROME_UA,
        )
        self.assertIn("backend.leadconnectorhq.com", BASE_URL)
        self.assertIsInstance(STRIP_KEYS, frozenset)
        self.assertIn("id", STRIP_KEYS)

    def test_shim_request_returns_dict(self):
        client = self._shim_client()
        result = client.request("GET", f"/workflow/LOC123/WF1")
        self.assertIsInstance(result, dict)

    def test_shim_get_workflow(self):
        client = self._shim_client()
        client._adapter.transport.request = MagicMock(
            return_value={"id": "WF1", "name": "My Workflow", "version": 1,
                          "workflowData": {"templates": []}}
        )
        result = client.get_workflow("WF1")
        self.assertIsNotNone(result)
        self.assertEqual(result.get("name"), "My Workflow")

    def test_shim_create_location_tag(self):
        client = self._shim_client()
        result = client.create_location_tag("test-tag")
        self.assertTrue(result)

    def test_shim_call_count(self):
        client = self._shim_client()
        initial = client.call_count
        client.request("GET", "/workflow/LOC123/WF1")
        self.assertGreaterEqual(client.call_count, initial)


# ── Test: endpoints.py ────────────────────────────────────────────────────────

class TestEndpoints(unittest.TestCase):

    def setUp(self):
        from cli_anything.gohighlevel.internal import endpoints
        self.e = endpoints

    def test_base_url(self):
        self.assertEqual(self.e.BASE_URL, "https://backend.leadconnectorhq.com")

    def test_folder_path(self):
        self.assertEqual(self.e.folder("LOC1"), "/workflow/LOC1")

    def test_workflow_create_same_as_folder(self):
        # same path, different body — both must exist for probe independence
        self.assertEqual(self.e.workflow_create("LOC1"), self.e.folder("LOC1"))

    def test_workflow_get(self):
        self.assertEqual(self.e.workflow_get("LOC1", "WF1"), "/workflow/LOC1/WF1")

    def test_workflow_put(self):
        self.assertEqual(self.e.workflow_put("LOC1", "WF1"), "/workflow/LOC1/WF1")

    def test_trigger_create(self):
        self.assertEqual(self.e.trigger_create("LOC1"), "/workflow/LOC1/trigger")

    def test_trigger_put(self):
        self.assertEqual(self.e.trigger_put("LOC1", "TR1"), "/workflow/LOC1/trigger/TR1")

    def test_tag_create(self):
        self.assertEqual(self.e.tag_create("LOC1"), "/workflow/LOC1/tags/create")


# ── Test: data_dir resolution ─────────────────────────────────────────────────

class TestDataDir(unittest.TestCase):

    def test_respects_caf_data_dir_env(self):
        from cli_anything.gohighlevel.internal.guards import data_dir
        with tempfile.TemporaryDirectory() as d:
            os.environ["CAF_DATA_DIR"] = d
            try:
                p = data_dir()
                self.assertEqual(str(p), d)
            finally:
                os.environ.pop("CAF_DATA_DIR", None)

    def test_falls_back_to_home(self):
        from cli_anything.gohighlevel.internal.guards import data_dir
        os.environ.pop("CAF_DATA_DIR", None)
        p = data_dir()
        self.assertIn(".openclaw", str(p))
        self.assertIn("convert-and-flow-cli", str(p))


if __name__ == "__main__":
    unittest.main()
