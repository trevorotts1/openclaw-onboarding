#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: n8n deployment drift detector tests
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: _fetch_all_workflows (the pagination loop)
# and main()'s exit-code contract are driven with mocked _call_n8n_api
# responses. Proves rem-3(b): a live instance with 295 workflows that page
# across multiple /workflows?limit=100&cursor=... responses is fully scanned,
# not silently truncated at the first 100.
#
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_verify_n8n_deploy.py
# =============================================================================
"""Deterministic tests for verify-n8n-deploy.py pagination + exit codes (rem-3)."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "verify-n8n-deploy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_n8n_deploy", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_n8n_deploy"] = mod
    spec.loader.exec_module(mod)
    return mod


VND = _load_module()


def _wf(name: str, *, webhook: str | None = None, nodes: int = 1,
        active: bool = True) -> dict:
    """A minimal live workflow dict with optional webhook node."""
    node_list = [{"id": f"n{i}", "type": "n8n-nodes-base.set"} for i in range(nodes)]
    if webhook:
        node_list.append({
            "id": "wh1",
            "type": "n8n-nodes-base.webhook",
            "parameters": {"path": webhook},
        })
    return {
        "name": name,
        "nodes": node_list,
        "connections": {},
        "active": active,
    }


class FetchAllWorkflowsTests(unittest.TestCase):
    """The pagination loop must accumulate every page until nextCursor is null."""

    def test_single_page_no_cursor(self):
        """One page with no nextCursor returns that page's data."""
        page = {"data": [_wf("alpha"), _wf("beta")], "nextCursor": None}
        with patch.object(VND, "_call_n8n_api", return_value=(0, page)):
            code, workflows = VND._fetch_all_workflows("http://x", "key")
        self.assertEqual(code, 0)
        self.assertEqual(len(workflows), 2)
        self.assertEqual(workflows[0]["name"], "alpha")

    def test_two_pages_both_scanned(self):
        """Two pages: page 1 has nextCursor, page 2 does not. Both must appear."""
        page1 = {"data": [_wf(f"wf-{i}") for i in range(100)],
                 "nextCursor": "cursor-page-2"}
        page2 = {"data": [_wf("publish-target", webhook="podbean-publish")],
                 "nextCursor": None}
        responses = [(0, page1), (0, page2)]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        with patch.object(VND, "_call_n8n_api", side_effect=fake_call) as mock_call:
            code, workflows = VND._fetch_all_workflows("http://x", "key")

        self.assertEqual(code, 0)
        # 100 from page 1 + 1 from page 2 = 101 total
        self.assertEqual(len(workflows), 101)
        # The publish-target workflow is on page 2 -- it must be present
        names = [w["name"] for w in workflows]
        self.assertIn("publish-target", names)
        # The first page's workflows are all present too
        self.assertIn("wf-0", names)
        self.assertIn("wf-99", names)
        # Two API calls were made (pagination loop ran twice)
        self.assertEqual(mock_call.call_count, 2)

    def test_three_pages_all_scanned(self):
        """Three pages (295 workflows across 100+100+95) are all accumulated."""
        page1 = {"data": [_wf(f"a-{i}") for i in range(100)],
                 "nextCursor": "c2"}
        page2 = {"data": [_wf(f"b-{i}") for i in range(100)],
                 "nextCursor": "c3"}
        page3 = {"data": [_wf(f"c-{i}") for i in range(95)],
                 "nextCursor": None}
        responses = [(0, page1), (0, page2), (0, page3)]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        with patch.object(VND, "_call_n8n_api", side_effect=fake_call) as mock_call:
            code, workflows = VND._fetch_all_workflows("http://x", "key")

        self.assertEqual(code, 0)
        self.assertEqual(len(workflows), 295)
        self.assertEqual(mock_call.call_count, 3)

    def test_first_page_error_returns_error_code(self):
        """If the first page fails, the error code propagates and no workflows return."""
        with patch.object(VND, "_call_n8n_api", return_value=(500, {"error": "boom"})):
            code, workflows = VND._fetch_all_workflows("http://x", "key")
        self.assertEqual(code, 500)
        self.assertEqual(workflows, [])

    def test_second_page_error_stops_and_returns_error(self):
        """If a later page fails, the loop stops and returns the error code."""
        page1 = {"data": [_wf("a")], "nextCursor": "c2"}
        responses = [(0, page1), (-1, {"error": "network dropped"})]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        with patch.object(VND, "_call_n8n_api", side_effect=fake_call):
            code, workflows = VND._fetch_all_workflows("http://x", "key")
        self.assertEqual(code, -1)
        self.assertEqual(workflows, [])

    def test_cursor_passed_as_query_param(self):
        """The cursor from page 1 must appear as a query param on the page 2 request."""
        page1 = {"data": [_wf("a")], "nextCursor": "opaque-cursor-xyz"}
        page2 = {"data": [_wf("b")], "nextCursor": None}
        responses = [(0, page1), (0, page2)]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        with patch.object(VND, "_call_n8n_api", side_effect=fake_call) as mock_call:
            VND._fetch_all_workflows("http://x", "key")

        # First call: no cursor param
        first_path = mock_call.call_args_list[0].args[2]
        self.assertIn("limit=100", first_path)
        self.assertNotIn("cursor=", first_path)
        # Second call: cursor param present and URL-encoded
        second_path = mock_call.call_args_list[1].args[2]
        self.assertIn("limit=100", second_path)
        self.assertIn("cursor=opaque-cursor-xyz", second_path)

    def test_cursor_url_encoded(self):
        """A cursor with special characters is URL-encoded in the query string."""
        page1 = {"data": [_wf("a")], "nextCursor": "cur sor/special"}
        page2 = {"data": [_wf("b")], "nextCursor": None}
        responses = [(0, page1), (0, page2)]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        with patch.object(VND, "_call_n8n_api", side_effect=fake_call) as mock_call:
            VND._fetch_all_workflows("http://x", "key")

        second_path = mock_call.call_args_list[1].args[2]
        # Space -> %20, slash -> %2F
        self.assertIn("cur%20sor%2Fspecial", second_path)


class MainExitCodeTests(unittest.TestCase):
    """The exit-code contract (0/1/2) must hold under mocked pagination."""

    def _make_config_dir(self, workflows: dict) -> str:
        """Write workflow JSON files into a temp config dir; return its path."""
        tmp = tempfile.mkdtemp(prefix="vnd_test_")
        for fname, content in workflows.items():
            Path(tmp, fname).write_text(json.dumps(content), encoding="utf-8")
        return tmp

    def test_exit_2_when_env_missing(self):
        """No N8N_API_URL / N8N_API_KEY -> exit 2 (unreachable)."""
        env = {"N8N_API_URL": "", "N8N_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            # Even if these were set in the outer env, force them empty
            with patch.dict(os.environ, {"N8N_API_URL": "", "N8N_API_KEY": ""}):
                rc = VND.main(["--config-dir", "/tmp/nonexistent-xyz"])
        self.assertEqual(rc, 2)

    def test_exit_2_when_api_unreachable(self):
        """API returns an error code -> exit 2 (unreachable)."""
        config = self._make_config_dir({
            "test.workflow.json": {
                "meta": {"version": "1.0.0"},
                "name": "test",
                "nodes": [{"id": "n1", "type": "n8n-nodes-base.start"}],
                "connections": {},
            },
        })
        env = {"N8N_API_URL": "http://fake", "N8N_API_KEY": "fakekey"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(VND, "_call_n8n_api", return_value=(-1, {"error": "nope"})):
                rc = VND.main(["--config-dir", config])
        self.assertEqual(rc, 2)

    def test_exit_1_on_drift_when_workflow_not_found(self):
        """Exported workflow absent from live (even on page 2) -> DRIFT, exit 1."""
        config = self._make_config_dir({
            "test.workflow.json": {
                "meta": {"version": "1.0.0"},
                "name": "my-publish-workflow",
                "nodes": [{
                    "id": "wh1", "type": "n8n-nodes-base.webhook",
                    "parameters": {"path": "podbean-publish"},
                }],
                "connections": {},
                "active": True,
            },
        })
        # Two pages: the matching workflow is on NEITHER page
        page1 = {"data": [_wf(f"other-{i}") for i in range(100)],
                 "nextCursor": "c2"}
        page2 = {"data": [_wf("unrelated")], "nextCursor": None}
        responses = [(0, page1), (0, page2)]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        env = {"N8N_API_URL": "http://fake", "N8N_API_KEY": "fakekey"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(VND, "_call_n8n_api", side_effect=fake_call) as mock_call:
                rc = VND.main(["--config-dir", config])
        self.assertEqual(rc, 1)
        # Both pages were scanned (not just the first 100)
        self.assertEqual(mock_call.call_count, 2)

    def test_exit_0_match_found_on_second_page(self):
        """The publish workflow is on page 2 -- finding it proves both pages scanned."""
        config = self._make_config_dir({
            "test.workflow.json": {
                "meta": {"version": "1.0.0"},
                "name": "create podcast episode from openclaw",
                "nodes": [{
                    "id": "wh1", "type": "n8n-nodes-base.webhook",
                    "parameters": {"path": "podbean-publish"},
                }],
                "connections": {},
                "active": True,
            },
        })
        # Page 1: 100 unrelated workflows. Page 2: the matching one.
        # The live match must have the SAME node count, connection count,
        # active state, and webhook paths as the export so the comparison is
        # a MATCH, not a DRIFT. _wf(webhook=...) adds 1 webhook node on top
        # of the `nodes` count, so nodes=0 yields exactly 1 node (the webhook).
        page1 = {"data": [_wf(f"other-{i}") for i in range(100)],
                 "nextCursor": "c2"}
        page2 = {"data": [_wf("create podcast episode from openclaw",
                              webhook="podbean-publish", nodes=0, active=True)],
                 "nextCursor": None}
        responses = [(0, page1), (0, page2)]

        def fake_call(api_url, api_key, path, *, timeout=15):
            return responses.pop(0)

        env = {"N8N_API_URL": "http://fake", "N8N_API_KEY": "fakekey"}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(VND, "_call_n8n_api", side_effect=fake_call) as mock_call:
                rc = VND.main(["--config-dir", config])
        self.assertEqual(rc, 0)
        self.assertEqual(mock_call.call_count, 2)


class FindLiveWorkflowActivePreferenceTests(unittest.TestCase):
    """When several live workflows share a webhook path (deploy cutover leaves
    superseded twins INACTIVE), matching must prefer the ACTIVE one so the repo
    export is reconciled against the deployed workflow, not a stale rollback."""

    def _wf_with_path(self, name, active, path="podbean-publish"):
        return {
            "name": name,
            "active": active,
            "nodes": [{"type": "n8n-nodes-base.webhook",
                       "parameters": {"path": path}}],
            "connections": {},
        }

    def test_active_preferred_when_multiple_share_path(self):
        export = {
            "name": "create podcast episode from openclaw",
            "active": True,
            "nodes": [{"type": "n8n-nodes-base.webhook",
                       "parameters": {"path": "podbean-publish"}}],
            "connections": {},
        }
        live = [
            self._wf_with_path("old 59-node superseded", False),
            self._wf_with_path("old 70-node readback-bug", False),
            self._wf_with_path("new 70-node fixed", True),
        ]
        got = VND._find_live_workflow(live, export)
        self.assertIsNotNone(got)
        self.assertTrue(got["active"])
        self.assertEqual(got["name"], "new 70-node fixed")

    def test_inactive_fallback_when_no_active_twin(self):
        export = {
            "name": "create podcast episode from openclaw",
            "active": True,
            "nodes": [{"type": "n8n-nodes-base.webhook",
                       "parameters": {"path": "podbean-publish"}}],
            "connections": {},
        }
        live = [
            self._wf_with_path("only-twin-inactive", False),
        ]
        got = VND._find_live_workflow(live, export)
        self.assertIsNotNone(got)
        self.assertEqual(got["name"], "only-twin-inactive")

if __name__ == "__main__":
    unittest.main()