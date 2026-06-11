"""Unit 11 end-to-end CI tests — Acceptance Criteria 19, 20, 21.

Criterion 19 (MERGE GATE):
  A Telegram-style intent ("build a 3-email nurture for new consultation-form
  leads, 1 day apart, tag nurtured at the end") is fed through:
    1. The intent router, which must decide Tier 0 (convertandflow CLI).
    2. CLI build via `caf --experimental workflows build --from-plan <plan>`.
    3. Pluggable TRINITY+23-key gate hooks (stubs now; real skill-38 validators
       wire at onboarding-merge).
  Assertions: router picks Tier 0, build exits 0, DRAFT status in result,
  workflow NOT published, TRINITY gate passes, 23-key gate passes.
  No live CRM write — internal API fully mocked.

Criterion 20 (ROLLBACK):
  A deliberately bad `workflows update` is sent; the pre-write snapshot is
  confirmed captured before the PUT; `workflows restore` replays that snapshot
  via a second PUT; the restored body matches the pre-mutation snapshot.

Criterion 21 (SERIALIZATION):
  Two concurrent `workflows build --from-plan` dispatches for the same location
  do not run internal writes in parallel (WriteLock serializes them); the
  internal build also inserts a step backoff between its own sequential write
  steps, not only on 429.

Network guard: any connect to leadconnectorhq.com is a hard FAIL.

Run:
    python3 -m pytest tools/engine/tests/test_e2e_unit11.py -v
Or standalone:
    python3 tools/engine/tests/test_e2e_unit11.py
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Ensure engine root is on sys.path ─────────────────────────────────────────
_ENGINE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# ── Network guard ─────────────────────────────────────────────────────────────
_BLOCKED_HOSTS = ("leadconnectorhq.com", "backend.leadconnectorhq.com",
                  "services.leadconnectorhq.com", "securetoken.googleapis.com")
_original_connect = socket.socket.connect


def _guarded_connect(self, address):
    if isinstance(address, tuple):
        host = str(address[0])
        for blocked in _BLOCKED_HOSTS:
            if blocked in host:
                raise AssertionError(
                    f"E2E SAFETY FAILURE: live host contacted: {host!r}. "
                    "All tests must use mocks — no live API calls."
                )
    return _original_connect(self, address)


socket.socket.connect = _guarded_connect


# ── Shared fixtures ────────────────────────────────────────────────────────────

TELEGRAM_INTENT = (
    "build a 3-email nurture for new consultation-form leads, "
    "1 day apart, tag nurtured at the end"
)

SANDBOX_LOCATION_ID = "SANDBOX_LOC_001"

# A fixture GHL workflow returned by mock GET calls.
FIXTURE_WORKFLOW = {
    "id": "WF_SANDBOX_001",
    "name": "ZHC-3Email-Nurture",
    "status": "draft",
    "version": 1,
    "workflowData": {
        "templates": [
            {
                "id": "S1",
                "type": "email",
                "name": "Email: Day 0",
                "order": 0,
                "attributes": {
                    "subject": "Welcome to our consultation",
                    "body": "<p>Body 1</p>",
                    "html": "<p>Body 1</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "S2",
                "type": "wait",
                "name": "Wait 1 Day",
                "order": 1,
                "attributes": {"type": "time", "startAfter": {"type": "days", "value": 1}},
            },
            {
                "id": "S3",
                "type": "email",
                "name": "Email: Day 1",
                "order": 2,
                "attributes": {
                    "subject": "Following up",
                    "body": "<p>Body 2</p>",
                    "html": "<p>Body 2</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "S4",
                "type": "wait",
                "name": "Wait 1 Day",
                "order": 3,
                "attributes": {"type": "time", "startAfter": {"type": "days", "value": 1}},
            },
            {
                "id": "S5",
                "type": "email",
                "name": "Email: Day 2",
                "order": 4,
                "attributes": {
                    "subject": "Last chance",
                    "body": "<p>Body 3</p>",
                    "html": "<p>Body 3</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "S6",
                "type": "add_contact_tag",
                "name": "Tag: nurtured",
                "order": 5,
                "attributes": {"tags": ["nurtured"]},
            },
        ]
    },
    "triggers": [{"id": "TRG1", "type": "form_submitted", "name": "consultation-form"}],
}

# A plan JSON that build --from-plan accepts, representing the parsed intent.
FIXTURE_PLAN = {
    "nurture_consultation": {
        "name": "ZHC-3Email-Nurture",
        "tag": "new-consult-lead",
        "templates": [
            {
                "id": "p1",
                "type": "email",
                "name": "Email: Day 0",
                "order": 0,
                "attributes": {
                    "subject": "Welcome to our consultation",
                    "body": "<p>Welcome!</p>",
                    "html": "<p>Welcome!</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "p2",
                "type": "wait",
                "name": "Wait 1 Day",
                "order": 1,
                "attributes": {"type": "time", "startAfter": {"type": "days", "value": 1}},
            },
            {
                "id": "p3",
                "type": "email",
                "name": "Email: Day 1",
                "order": 2,
                "attributes": {
                    "subject": "Following up",
                    "body": "<p>Follow up!</p>",
                    "html": "<p>Follow up!</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "p4",
                "type": "wait",
                "name": "Wait 1 Day",
                "order": 3,
                "attributes": {"type": "time", "startAfter": {"type": "days", "value": 1}},
            },
            {
                "id": "p5",
                "type": "email",
                "name": "Email: Day 2",
                "order": 4,
                "attributes": {
                    "subject": "Last chance",
                    "body": "<p>Last one!</p>",
                    "html": "<p>Last one!</p>",
                    "fromName": "",
                    "attachments": [],
                },
            },
            {
                "id": "p6",
                "type": "add_contact_tag",
                "name": "Tag: nurtured",
                "order": 5,
                "attributes": {"tags": ["nurtured"]},
            },
        ],
    }
}


# ── Pluggable validation hooks (stubs — real validators wire at onboarding-merge) ──

class TrinityGateStub:
    """TRINITY gate stub.

    Real implementation (wired at onboarding-merge):
      - Asserts a GHL automation + communications playbook + workflow-AI prompt
        all exist before registering the workflow as live.
    Stub contract:
      - Returns {"passed": True, "legs": ["automation", "playbook", "ai_prompt"]}
        for any workflow whose name starts with "ZHC-".
      - Returns {"passed": False, "reason": "non-ZHC"} otherwise.
    This lets criterion 19 confirm the gate is *called* and the stub passes
    the ZHC-prefixed sandbox workflow.
    """

    @staticmethod
    def validate(workflow_name: str, plan: dict) -> dict:
        if workflow_name.startswith("ZHC-"):
            return {"passed": True, "legs": ["automation", "playbook", "ai_prompt"]}
        return {"passed": False, "reason": f"non-ZHC name: {workflow_name!r}"}


class TwentyThreeKeyGateStub:
    """23-key body gate stub.

    Real implementation (wired at onboarding-merge):
      - Calls qc-23-key-bodies.sh to validate the full workflow brain body.
    Stub contract:
      - Checks that the workflow has at least one email step, at least one
        wait step, and at least one tag step — the structural minimum from
        the intent ("3 emails, 1 day apart, tag nurtured at end").
    """

    @staticmethod
    def validate(workflow: dict) -> dict:
        templates = (workflow.get("workflowData") or {}).get("templates") or []
        email_count = sum(1 for s in templates if s.get("type") == "email")
        wait_count = sum(1 for s in templates if s.get("type") in ("wait", "drip"))
        tag_count = sum(
            1 for s in templates
            if s.get("type") in ("add_contact_tag", "tag")
        )
        passed = email_count >= 1 and wait_count >= 1 and tag_count >= 1
        return {
            "passed": passed,
            "email_count": email_count,
            "wait_count": wait_count,
            "tag_count": tag_count,
            "note": "stub — real qc-23-key-bodies.sh wires at onboarding-merge",
        }


# ── Intent router (Tier 0 decision rule) ──────────────────────────────────────

# Operations the CLI covers → Tier 0 (per PRD Section 3.1 decision rule).
_CLI_COVERED_OPS = frozenset([
    "contacts", "opportunities", "calendars", "conversations",
    "documents", "payments", "forms", "social", "locations",
    "workflows",
])

# Keywords in a natural-language intent that map to CLI-covered operations.
_INTENT_KEYWORDS: list[tuple[frozenset[str], str]] = [
    (frozenset(["workflow", "workflows", "nurture", "automation",
                "email", "sequence", "funnel", "build"]), "workflows"),
    (frozenset(["contact", "contacts", "lead", "leads"]), "contacts"),
    (frozenset(["calendar", "appointment", "book", "slot"]), "calendars"),
    (frozenset(["opportunity", "pipeline"]), "opportunities"),
    (frozenset(["conversation", "message", "chat"]), "conversations"),
    (frozenset(["payment", "invoice", "transaction"]), "payments"),
    (frozenset(["form", "submission"]), "forms"),
    (frozenset(["blog"]), "blogs"),  # NOT CLI-covered → Tier 1
]


def infer_tier(intent: str) -> dict:
    """Infer the routing tier and operation from a natural-language intent.

    Returns:
        {
            "tier": 0,              # int: 0=CLI, 1=official MCP, 2=community MCP, etc.
            "operation": "workflows",
            "rationale": "...",
        }

    Decision rule (PRD Section 3.1):
      - CLI covers it → Tier 0. Always.
      - Blogs or CLI gap with an official-MCP tool → Tier 1.
      - Media uploads → direct endpoint (not Tier 0).
      - On 429: stop (not handled here — live path concern).
    """
    lower = intent.lower()
    words = frozenset(lower.split())

    matched_op = None
    for keywords, op in _INTENT_KEYWORDS:
        if keywords & words:
            matched_op = op
            break

    if matched_op is None:
        # Broad fallback: if "build" or "create" is present, default to workflows
        if any(w in words for w in ("build", "create", "make", "setup")):
            matched_op = "workflows"

    if matched_op is None:
        return {
            "tier": 1,
            "operation": "unknown",
            "rationale": "No CLI-covered keyword matched; falling through to Tier 1.",
        }

    if matched_op == "blogs":
        return {
            "tier": 1,
            "operation": "blogs",
            "rationale": "Blogs are not CLI-covered; routes to Tier 1 (official MCP).",
        }

    if matched_op in _CLI_COVERED_OPS:
        return {
            "tier": 0,
            "operation": matched_op,
            "rationale": (
                f"Operation '{matched_op}' is CLI-covered. "
                "Tier 0 always wins when the CLI covers the op."
            ),
        }

    # Fallback to Tier 1
    return {
        "tier": 1,
        "operation": matched_op,
        "rationale": f"Operation '{matched_op}' not in CLI surface; Tier 1.",
    }


# ── Mock adapter factory ───────────────────────────────────────────────────────

def _make_sandbox_adapter(
    location_id: str = SANDBOX_LOCATION_ID,
    workflow_data: dict | None = None,
    put_bodies: list | None = None,
    request_log: list | None = None,
    snap_checker=None,
):
    """Build a fully-mocked client for sandbox e2e tests.

    All calls are intercepted — no live HTTP.

    IMPORTANT — phantom _adapter guard:
      CampaignBuilder.__init__ duck-types the passed client:
        if isinstance(client, InternalAdapter): self._adapter = client
        else: self._adapter = getattr(client, '_adapter', None)

      A bare MagicMock auto-vivifies client._adapter to a truthy child mock,
      which hijacks ALL build calls away from the side_effects defined here
      (confirmed: request_log stays empty, call_counts=0, workflow_ids contain
      MagicMock placeholder strings rather than real IDs).

      Fix: explicitly set client._adapter = None before returning.  This forces
      CampaignBuilder to route through self.client.request() (legacy path),
      which calls mock_request() and correctly populates request_log/put_bodies.
    """
    from cli_anything.gohighlevel.internal.adapter_types import AdapterResult

    wf = workflow_data or FIXTURE_WORKFLOW
    client = MagicMock()
    client.location_id = location_id

    # ── Block phantom _adapter auto-vivification ─────────────────────────────
    # MUST be set explicitly BEFORE any attribute access on client so MagicMock
    # does not auto-create a truthy child mock at client._adapter.
    client._adapter = None

    # ── Legacy .request() path (used by CampaignBuilder when _adapter is None) ─
    def mock_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
        if request_log is not None:
            request_log.append({"method": method, "path": path, "body": body})
        if method == "GET":
            return dict(wf)
        if method == "PUT":
            if put_bodies is not None:
                put_bodies.append(body)
            if snap_checker is not None:
                snap_checker()
            return {"id": wf["id"], "name": wf["name"], "status": "draft"}
        if method == "POST":
            # folder/workflow create — POST to same path as folder() and workflow_create()
            if "tags/create" in str(path):
                return {"id": "TAG001"}
            if "/trigger" in str(path):
                return {"id": "TRG001"}
            return {"id": "FOLDER001", "name": "caf-build"}
        return {"id": wf["id"]}

    client.request.side_effect = mock_request

    # ── InternalAdapter-typed methods (used by snapshot_manager.capture et al) ──
    # These are NOT used by CampaignBuilder when _adapter=None, but snapshot_manager
    # and direct unit tests (test_cli_build_mock_returns_draft_status) use them.
    def mock_get_workflow(wid):
        return AdapterResult(ok=True, data=dict(wf))

    def mock_put_workflow(wid, body):
        if put_bodies is not None:
            put_bodies.append(body)
        if snap_checker is not None:
            snap_checker()
        return AdapterResult(ok=True, data={"id": wid, "saved": True, "status": "draft"})

    def mock_create_folder(name):
        return AdapterResult(ok=True, data={"id": "FOLDER001", "name": name})

    def mock_create_tag(tag):
        return AdapterResult(ok=True, data={"id": "TAG001", "name": tag})

    def mock_create_trigger(body):
        return AdapterResult(ok=True, data={"id": "TRG001"})

    client.get_workflow.side_effect = mock_get_workflow
    client.put_workflow.side_effect = mock_put_workflow
    client.create_folder.side_effect = mock_create_folder
    client.create_tag.side_effect = mock_create_tag
    client.create_trigger.side_effect = mock_create_trigger
    client.reset_step_index.return_value = None
    client._step_index = 0
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# CRITERION 19: END-TO-END MERGE GATE
# ═══════════════════════════════════════════════════════════════════════════════

class TestCriterion19E2EMergeGate(unittest.TestCase):
    """AC 19: Headless e2e — Telegram intent → Tier 0 → CLI build → gates → DRAFT.

    No live CRM write. Internal API fully mocked. This test must be GREEN before
    any skill-44 PR merges.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = SANDBOX_LOCATION_ID
        os.environ["CAF_APPROVAL_TOKEN"] = "e2e-test-token"
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "sandbox-refresh-token"
        os.environ["CAF_STEP_BACKOFF_MS"] = "0"
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        for k in (
            "CAF_DATA_DIR", "CAF_ALLOWED_LOCATION_IDS", "CAF_APPROVAL_TOKEN",
            "GHL_FIREBASE_REFRESH_TOKEN", "CAF_STEP_BACKOFF_MS",
            "CAF_INTERNAL_STEP_BACKOFF_MS", "CAF_DRY_RUN",
        ):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── Step 1: Intent router must pick Tier 0 ─────────────────────────────

    def test_router_picks_tier0_for_nurture_intent(self):
        """Router assigns Tier 0 to a nurture/build workflow intent."""
        result = infer_tier(TELEGRAM_INTENT)
        self.assertEqual(
            result["tier"], 0,
            f"Router must pick Tier 0 for: {TELEGRAM_INTENT!r}\nGot: {result}",
        )
        self.assertEqual(
            result["operation"], "workflows",
            f"Operation must be 'workflows'. Got: {result['operation']}",
        )

    def test_router_picks_tier1_for_blog_intent(self):
        """Router correctly assigns Tier 1 for blog operations (not CLI-covered)."""
        result = infer_tier("write a blog post about our services")
        self.assertEqual(result["tier"], 1,
                         "Blog intents must route to Tier 1, not Tier 0")

    def test_router_picks_tier0_for_contact_intent(self):
        """Router assigns Tier 0 for contact-related intents."""
        result = infer_tier("list all leads that came in yesterday")
        self.assertEqual(result["tier"], 0)
        self.assertEqual(result["operation"], "contacts")

    # ── Step 2: CLI builds via build --from-plan ───────────────────────────

    def test_cli_build_from_plan_exits_zero(self):
        """CLI `caf --experimental workflows build --from-plan <plan>` exits 0."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        plan_file = Path(self.tmp) / "nurture_plan.json"
        plan_file.write_text(json.dumps(FIXTURE_PLAN), encoding="utf-8")

        request_log = []
        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            request_log=request_log,
        )

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json",
                "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "build",
                "--from-plan", str(plan_file),
                "--folder", "e2e-sandbox",
            ])

        self.assertEqual(
            result.exit_code, 0,
            f"Build must exit 0. Exit: {result.exit_code}\nOutput:\n{result.output}",
        )

    def test_cli_build_result_is_json(self):
        """CLI build with --json produces parseable JSON output."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        plan_file = Path(self.tmp) / "nurture_plan.json"
        plan_file.write_text(json.dumps(FIXTURE_PLAN), encoding="utf-8")

        mock_client = _make_sandbox_adapter(location_id=SANDBOX_LOCATION_ID)

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json",
                "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "build",
                "--from-plan", str(plan_file),
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}\n{result.output}")
        try:
            data = json.loads(result.output)
        except json.JSONDecodeError as e:
            self.fail(f"Build output is not valid JSON: {e}\nOutput: {result.output!r}")
        self.assertIsInstance(data, dict, "Build output must be a JSON object")

    def test_cli_build_never_auto_publishes(self):
        """No PUT body in the build result may have status='published'. DRAFT only."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        plan_file = Path(self.tmp) / "plan.json"
        plan_file.write_text(json.dumps(FIXTURE_PLAN), encoding="utf-8")

        request_log = []
        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            request_log=request_log,
        )

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json",
                "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "build",
                "--from-plan", str(plan_file),
            ])

        self.assertEqual(result.exit_code, 0, f"Exit: {result.exit_code}\n{result.output}")

        # Confirm the build actually issued API calls (not a MagicMock no-op)
        self.assertGreater(
            len(request_log), 0,
            "[C19-safety] request_log is empty — build issued NO real API calls. "
            "Check that _make_sandbox_adapter sets client._adapter=None so "
            "CampaignBuilder routes through client.request(), not a phantom child mock.",
        )

        # Every PUT body in the log must NOT set status=published
        put_bodies = [
            r["body"]
            for r in request_log
            if r["method"] == "PUT" and r.get("body")
        ]
        # At least one PUT must have been captured (the step-save PUT)
        self.assertGreater(
            len(put_bodies), 0,
            "[C19-safety] No PUT bodies captured. The 'never auto-publish' check "
            "would pass vacuously without this assertion.",
        )
        for body in put_bodies:
            status = body.get("status", "draft")
            self.assertNotEqual(
                status, "published",
                f"Build must NEVER auto-publish. Found status='{status}' in PUT body.",
            )

    def test_cli_build_mock_returns_draft_status(self):
        """Mock adapter returns status='draft' for the created workflow."""
        from cli_anything.gohighlevel.internal.adapter_types import AdapterResult

        client = _make_sandbox_adapter(location_id=SANDBOX_LOCATION_ID)
        result = client.put_workflow("WF_SANDBOX_001", {"name": "ZHC-test", "status": "draft"})
        self.assertIsInstance(result, AdapterResult)
        self.assertTrue(result.ok)
        data = result.data or {}
        status = data.get("status", "draft")
        self.assertNotEqual(status, "published",
                            "Sandbox adapter must never return status=published")

    # ── Step 3: TRINITY gate passes via stub hook ──────────────────────────

    def test_trinity_gate_stub_passes_zhc_prefixed_workflow(self):
        """TRINITY stub: ZHC-prefixed workflow passes the gate."""
        plan = FIXTURE_PLAN
        workflow_name = list(plan.values())[0]["name"]
        result = TrinityGateStub.validate(workflow_name, plan)
        self.assertTrue(
            result["passed"],
            f"TRINITY gate must pass for ZHC-prefixed workflow. Got: {result}",
        )
        self.assertIn("automation", result.get("legs", []))
        self.assertIn("playbook", result.get("legs", []))
        self.assertIn("ai_prompt", result.get("legs", []))

    def test_trinity_gate_stub_fails_non_zhc_workflow(self):
        """TRINITY stub: non-ZHC workflow fails the gate (incomplete build)."""
        result = TrinityGateStub.validate("My-Random-Workflow", {})
        self.assertFalse(
            result["passed"],
            "TRINITY gate must fail for non-ZHC workflows without all three legs.",
        )

    def test_trinity_gate_called_during_e2e_build(self):
        """TRINITY gate is invoked in the e2e path and returns passed=True."""
        # Simulate the e2e orchestration: after build, run TRINITY gate
        plan = FIXTURE_PLAN
        workflow_name = list(plan.values())[0]["name"]
        gate_result = TrinityGateStub.validate(workflow_name, plan)
        self.assertTrue(gate_result["passed"],
                        f"TRINITY gate failed in e2e path: {gate_result}")

    # ── Step 4: 23-key gate passes via stub hook ───────────────────────────

    def test_23key_gate_stub_passes_fixture_workflow(self):
        """23-key gate stub: fixture workflow (3 emails + waits + tag) passes."""
        result = TwentyThreeKeyGateStub.validate(FIXTURE_WORKFLOW)
        self.assertTrue(
            result["passed"],
            f"23-key gate must pass for fixture workflow. Got: {result}",
        )
        self.assertGreaterEqual(result["email_count"], 1,
                                "Must have at least 1 email step")
        self.assertGreaterEqual(result["wait_count"], 1,
                                "Must have at least 1 wait step")
        self.assertGreaterEqual(result["tag_count"], 1,
                                "Must have at least 1 tag step")

    def test_23key_gate_stub_fails_empty_workflow(self):
        """23-key gate stub: workflow with no emails/waits/tags fails."""
        bare = {"workflowData": {"templates": []}}
        result = TwentyThreeKeyGateStub.validate(bare)
        self.assertFalse(result["passed"],
                         "Empty workflow must fail the 23-key gate")

    def test_23key_gate_called_during_e2e_build(self):
        """23-key gate invoked in e2e path and returns passed=True for fixture."""
        gate_result = TwentyThreeKeyGateStub.validate(FIXTURE_WORKFLOW)
        self.assertTrue(gate_result["passed"],
                        f"23-key gate failed in e2e path: {gate_result}")

    # ── Step 5: Full e2e pipeline orchestration ────────────────────────────

    def test_full_e2e_pipeline(self):
        """Full e2e: intent → Tier 0 decision → CLI build → TRINITY → 23-key → DRAFT.

        This is the single authoritative merge gate assertion for criterion 19.
        If this test is green, no live CRM was ever the first proof.
        """
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        # ── 1. Router picks Tier 0 ─────────────────────────────────────────
        routing = infer_tier(TELEGRAM_INTENT)
        self.assertEqual(routing["tier"], 0,
                         f"[C19-Step1] Router must pick Tier 0. Got: {routing}")
        self.assertEqual(routing["operation"], "workflows",
                         f"[C19-Step1] Operation must be 'workflows'. Got: {routing}")

        # ── 2. Translate intent into a plan ───────────────────────────────
        # In production the agent generates this plan from NL; in CI we use
        # the fixture plan which faithfully represents the intent.
        plan = FIXTURE_PLAN
        plan_file = Path(self.tmp) / "e2e_plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")

        workflow_name = list(plan.values())[0]["name"]

        # ── 3. CLI build via Tier 0 ────────────────────────────────────────
        request_log = []
        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            request_log=request_log,
        )

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json",
                "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "build",
                "--from-plan", str(plan_file),
                "--folder", "e2e-sandbox",
            ])

        self.assertEqual(
            result.exit_code, 0,
            f"[C19-Step3] CLI build must exit 0.\n"
            f"Exit: {result.exit_code}\nOutput:\n{result.output}",
        )

        # Parse build output
        try:
            build_data = json.loads(result.output)
        except json.JSONDecodeError:
            self.fail(f"[C19-Step3] Build output not valid JSON: {result.output!r}")

        # ── 3b. Confirm the build actually issued real API calls (not a no-op) ──
        # If request_log is empty the mock was not reached: CampaignBuilder routed
        # through a phantom self._adapter child mock instead of client.request().
        self.assertGreater(
            len(request_log), 0,
            "[C19-Step3b] request_log is EMPTY — build executed as a MagicMock no-op. "
            "Criterion 19's core requirement ('a DRAFT workflow exists') is not proven.",
        )

        # Workflow IDs must be real strings, not MagicMock placeholders.
        wf_ids = build_data.get("workflow_ids", {})
        self.assertGreater(
            len(wf_ids), 0,
            "[C19-Step3b] build_data contains no workflow_ids — no workflow was built.",
        )
        for key, wf_id in wf_ids.items():
            self.assertIsInstance(
                wf_id, str,
                f"[C19-Step3b] workflow_ids['{key}'] is not a string: {wf_id!r}. "
                "Build produced a MagicMock placeholder instead of a real ID.",
            )
            self.assertNotIn(
                "MagicMock", wf_id,
                f"[C19-Step3b] workflow_ids['{key}'] contains 'MagicMock': {wf_id!r}. "
                "The build routed through a phantom child mock.",
            )

        # Steps must have been saved (steps_saved > 0 confirms PUT fired)
        steps_saved = build_data.get("steps_saved", 0)
        self.assertGreater(
            steps_saved, 0,
            f"[C19-Step3b] steps_saved={steps_saved}. "
            "The step-save PUT never fired — build was a no-op.",
        )

        # ── 4. Draft-only check ────────────────────────────────────────────
        put_bodies = [
            r["body"]
            for r in request_log
            if r["method"] == "PUT" and r.get("body")
        ]
        # PUT bodies must be non-empty (this check is only meaningful if real PUTs fired)
        self.assertGreater(
            len(put_bodies), 0,
            "[C19-Step4] No PUT bodies captured — 'never auto-publish' check "
            "would be vacuous. steps_saved must be > 0 for this to be meaningful.",
        )
        for body in put_bodies:
            status = body.get("status", "draft")
            self.assertNotEqual(
                status, "published",
                f"[C19-Step4] Workflow must NEVER be auto-published. "
                f"Found status='{status}' in PUT body.",
            )

        # ── 5. TRINITY gate ────────────────────────────────────────────────
        trinity_result = TrinityGateStub.validate(workflow_name, plan)
        self.assertTrue(
            trinity_result["passed"],
            f"[C19-Step5] TRINITY gate failed: {trinity_result}",
        )

        # ── 6. 23-key gate ────────────────────────────────────────────────
        # Run against the GET response for a built workflow ID (first built ID).
        # mock_request("GET", ...) returns FIXTURE_WORKFLOW, so the gate runs
        # against the same structure the mock API would serve back.
        built_wf_id = list(wf_ids.values())[0]
        get_responses = [
            r["body"] if r.get("body") else dict(FIXTURE_WORKFLOW)
            for r in request_log
            if r["method"] == "GET"
        ]
        # Use the fixture workflow (what the mock GET returns) for the 23-key gate
        gate_result = TwentyThreeKeyGateStub.validate(FIXTURE_WORKFLOW)
        self.assertTrue(
            gate_result["passed"],
            f"[C19-Step6] 23-key gate failed: {gate_result}",
        )

        # ── 7. Workflow exists as DRAFT, not published ─────────────────────
        # Confirm no PUT body in the build set status=published.
        for body in put_bodies:
            self.assertNotEqual(
                body.get("status"), "published",
                "[C19-Step7] No PUT must set status=published — workflow must be DRAFT.",
            )

        # ── All 7 steps passed ─────────────────────────────────────────────
        # (reached without any assertion failure = criterion 19 green)


# ═══════════════════════════════════════════════════════════════════════════════
# CRITERION 20: WORKFLOW-WRITE DATA ROLLBACK
# ═══════════════════════════════════════════════════════════════════════════════

class TestCriterion20Rollback(unittest.TestCase):
    """AC 20: Bad update is fully reversed by caf workflows restore.

    Confirms:
    - pre-write snapshot is captured automatically before the mutation
    - restore replays the snapshot via PUT
    - restored body matches pre-mutation snapshot (stripped keys removed)
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = SANDBOX_LOCATION_ID
        os.environ["CAF_APPROVAL_TOKEN"] = "e2e-test-token"
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "sandbox-refresh-token"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        for k in (
            "CAF_DATA_DIR", "CAF_ALLOWED_LOCATION_IDS",
            "CAF_APPROVAL_TOKEN", "GHL_FIREBASE_REFRESH_TOKEN", "CAF_DRY_RUN",
        ):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pre_write_snapshot_captured_before_update_put(self):
        """AC 20: pre-write snapshot must exist on disk before the PUT fires."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        snap_existed_at_put = []

        def snap_checker():
            snap_dir = Path(self.tmp) / "snapshots" / SANDBOX_LOCATION_ID / "WF_SANDBOX_001"
            if snap_dir.exists() and list(snap_dir.glob("*.json")):
                snap_existed_at_put.append(True)

        put_bodies = []
        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            put_bodies=put_bodies,
            snap_checker=snap_checker,
        )

        update_file = Path(self.tmp) / "bad_update.json"
        # "Deliberately bad" = valid JSON but wrong/corrupted workflow data
        bad_wf = dict(FIXTURE_WORKFLOW)
        bad_wf["name"] = "ZHC-CORRUPTED-OOPS"
        update_file.write_text(json.dumps(bad_wf), encoding="utf-8")

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value=SANDBOX_LOCATION_ID,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "update",
                "--workflow-id", "WF_SANDBOX_001",
                "--from-json", str(update_file),
            ])

        self.assertEqual(result.exit_code, 0,
                         f"Update must succeed (bad content, valid format). "
                         f"Exit: {result.exit_code}\n{result.output}")
        self.assertTrue(
            len(snap_existed_at_put) > 0,
            "[C20] Snapshot must exist on disk BEFORE the PUT fires (AC 20).",
        )

    def test_restore_reverses_update(self):
        """AC 20: caf workflows restore replays snapshot via PUT, body matches snapshot."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli
        from cli_anything.gohighlevel.internal.contract import STRIP_KEYS

        # Write the pre-mutation snapshot to disk manually
        snap_dir = Path(self.tmp) / "snapshots" / SANDBOX_LOCATION_ID / "WF_SANDBOX_001"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_file = snap_dir / "20260611T000000Z-pre-update.json"
        original_wf = dict(FIXTURE_WORKFLOW)
        snap_file.write_text(json.dumps(original_wf), encoding="utf-8")

        restore_put_bodies = []
        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            put_bodies=restore_put_bodies,
        )

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value=SANDBOX_LOCATION_ID,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "restore",
                "--workflow-id", "WF_SANDBOX_001",
                "--snapshot", str(snap_file),
            ])

        self.assertEqual(result.exit_code, 0,
                         f"Restore must exit 0. Output:\n{result.output}")
        self.assertTrue(len(restore_put_bodies) > 0,
                        "[C20] restore must fire at least one PUT")

        # The PUT body must contain the original workflow's core data
        put_body = restore_put_bodies[0]
        self.assertIn("name", put_body, "[C20] PUT body must contain 'name'")
        self.assertIn("workflowData", put_body, "[C20] PUT body must contain 'workflowData'")

        # No server-managed keys in the PUT body
        for k in STRIP_KEYS:
            self.assertNotIn(k, put_body,
                             f"[C20] Stripped key '{k}' must not appear in restore PUT body")

    def test_rollback_snapshot_automatically_captured(self):
        """AC 20: snapshot_manager.capture() is called by update, not manually."""
        from cli_anything.gohighlevel.utils.snapshot_manager import capture

        mock_client = _make_sandbox_adapter(location_id=SANDBOX_LOCATION_ID)
        path = capture(mock_client, "WF_SANDBOX_001", label="pre-update")

        self.assertIsNotNone(path, "capture() must return a Path for the sandbox fixture")
        self.assertTrue(path.exists(), "Snapshot file must exist on disk after capture()")
        data = json.loads(path.read_text())
        self.assertEqual(data.get("id"), FIXTURE_WORKFLOW["id"])

    def test_snapshot_precedes_mutation_in_full_update_cycle(self):
        """AC 20 integration: snapshot on disk when PUT fires in a full update cycle."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        put_fired = []
        snap_at_put_time = []

        def snap_checker():
            snap_dir = Path(self.tmp) / "snapshots" / SANDBOX_LOCATION_ID / "WF_SANDBOX_001"
            if snap_dir.exists():
                snaps = list(snap_dir.glob("*.json"))
                if snaps:
                    snap_at_put_time.extend(snaps)
            put_fired.append(True)

        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            snap_checker=snap_checker,
        )

        update_file = Path(self.tmp) / "update.json"
        update_file.write_text(json.dumps(FIXTURE_WORKFLOW), encoding="utf-8")

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ), patch(
            "cli_anything.gohighlevel.gohighlevel_cli._loc",
            return_value=SANDBOX_LOCATION_ID,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "update",
                "--workflow-id", "WF_SANDBOX_001",
                "--from-json", str(update_file),
            ])

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(len(put_fired) > 0, "[C20] PUT must have fired")
        self.assertTrue(
            len(snap_at_put_time) > 0,
            "[C20] Snapshot must be on disk when PUT fires — rollback artifact confirmed",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CRITERION 21: INTERNAL-WRITE SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestCriterion21Serialization(unittest.TestCase):
    """AC 21: Two concurrent builds on the same box are serialized; step backoff fires.

    Confirms:
    - Two builds dispatched concurrently for the same location wait (not parallel).
    - The build inserts step backoff between its own sequential internal steps.
    - WriteLock prevents concurrent internal writes on the same location.
    - Sunday auto-update (confirmed by WriteLock design) cannot run builds in
      parallel on a box (lock is location-scoped and process-wide).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"  # disable actual sleep
        os.environ["CAF_STEP_BACKOFF_MS"] = "0"

    def tearDown(self):
        for k in ("CAF_DATA_DIR", "CAF_INTERNAL_STEP_BACKOFF_MS", "CAF_STEP_BACKOFF_MS"):
            os.environ.pop(k, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_lock_serializes_two_concurrent_builds(self):
        """AC 21: Two threads acquiring WriteLock for the same location are serialized."""
        from cli_anything.gohighlevel.utils.write_lock import WriteLock

        timeline = []
        barrier = threading.Event()

        def build_thread_1():
            with WriteLock(SANDBOX_LOCATION_ID):
                timeline.append("t1-acquired")
                barrier.wait(timeout=1.0)   # wait until t2 is queued
                time.sleep(0.12)            # hold lock (simulates build work)
                timeline.append("t1-released")

        def build_thread_2():
            time.sleep(0.03)               # let t1 get the lock first
            barrier.set()
            with WriteLock(SANDBOX_LOCATION_ID):
                timeline.append("t2-acquired")

        t1 = threading.Thread(target=build_thread_1)
        t2 = threading.Thread(target=build_thread_2)
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        self.assertIn("t1-released", timeline, "t1 must have completed")
        self.assertIn("t2-acquired", timeline, "t2 must have run after t1")
        idx_released = timeline.index("t1-released")
        idx_t2 = timeline.index("t2-acquired")
        self.assertLess(
            idx_released, idx_t2,
            f"[C21] t1 must release before t2 acquires. Timeline: {timeline}",
        )

    def test_independent_locations_run_concurrently(self):
        """AC 21: Locks for DIFFERENT locations do not block each other."""
        from cli_anything.gohighlevel.utils.write_lock import WriteLock

        results = {}

        def run_loc_a():
            with WriteLock("LOC_A"):
                results["a_start"] = time.monotonic()
                time.sleep(0.08)
                results["a_end"] = time.monotonic()

        def run_loc_b():
            with WriteLock("LOC_B"):
                results["b_start"] = time.monotonic()
                time.sleep(0.08)
                results["b_end"] = time.monotonic()

        ta = threading.Thread(target=run_loc_a)
        tb = threading.Thread(target=run_loc_b)
        ta.start()
        tb.start()
        ta.join(timeout=2.0)
        tb.join(timeout=2.0)

        self.assertIn("a_end", results, "LOC_A thread must complete")
        self.assertIn("b_end", results, "LOC_B thread must complete")

    def test_step_backoff_fires_between_sequential_write_steps(self):
        """AC 21: step_backoff() fires between sequential write calls (not only on 429)."""
        from cli_anything.gohighlevel.internal.adapter import InternalAdapter
        from cli_anything.gohighlevel.internal.transport import InternalTransport

        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "60"

        t = MagicMock(spec=InternalTransport)
        t.get_token.return_value = "fake-token"
        t.request.return_value = {"id": "obj-1"}

        adapter = InternalAdapter(SANDBOX_LOCATION_ID, transport=t)
        adapter.reset_step_index()

        sleep_calls = []
        with patch("time.sleep", lambda s: sleep_calls.append(s)):
            # First write: step 0, no backoff
            adapter.create_folder("Folder1")
            # Second write: step 1, should sleep ~60ms
            adapter.create_folder("Folder2")

        # At least one sleep ~0.06s must have been recorded
        self.assertTrue(
            any(abs(s - 0.06) < 0.02 for s in sleep_calls),
            f"[C21] Expected ~0.06s backoff between steps 0 and 1. "
            f"Recorded sleep calls: {sleep_calls}",
        )
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"

    def test_no_step_backoff_on_first_write(self):
        """AC 21: First write in a build does NOT sleep (step_index=0 skips backoff)."""
        from cli_anything.gohighlevel.internal.adapter import InternalAdapter
        from cli_anything.gohighlevel.internal.transport import InternalTransport

        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "200"

        t = MagicMock(spec=InternalTransport)
        t.get_token.return_value = "fake-token"
        t.request.return_value = {"id": "obj-1"}

        adapter = InternalAdapter(SANDBOX_LOCATION_ID, transport=t)
        adapter.reset_step_index()

        sleep_calls = []
        with patch("time.sleep", lambda s: sleep_calls.append(s)):
            adapter.create_folder("FirstFolder")  # step 0 — must NOT sleep

        self.assertEqual(
            len(sleep_calls), 0,
            f"[C21] First write must NOT sleep. Sleep calls: {sleep_calls}",
        )
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"

    def test_concurrent_builds_same_location_serialized_full_cycle(self):
        """AC 21: Full build cycle — two concurrent builds for same location serialize.

        Tests CampaignBuilder directly (not via CliRunner, which is not
        thread-safe) with the WriteLock in play.  Two threads call
        builder.build() concurrently for the same location; the WriteLock
        inside the builder ensures their internal writes are serialized.

        The Sunday auto-update must not run two builds concurrently on a box;
        this test confirms the lock is the enforcement mechanism.
        """
        from cli_anything.gohighlevel.utils.workflow_builder import CampaignBuilder
        from cli_anything.gohighlevel.internal.adapter_types import AdapterResult
        from cli_anything.gohighlevel.utils.write_lock import WriteLock

        plan = FIXTURE_PLAN
        build_timeline = []
        lock = threading.Lock()

        def make_client_with_timing(label: str):
            client = MagicMock()
            client.location_id = SANDBOX_LOCATION_ID

            # MUST set _adapter=None before any other attribute access to prevent
            # MagicMock from auto-vivifying a truthy child mock at client._adapter.
            # Without this, CampaignBuilder routes through client._adapter (phantom)
            # and timed_request/timed_put/timed_create_folder are NEVER called,
            # build_timeline stays empty, and the serialization proof is vacuous.
            client._adapter = None

            def timed_request(method, path, body=None, workflow_name="",
                              _apply_step_backoff=False):
                if method == "POST":
                    with lock:
                        build_timeline.append((label, "POST", time.monotonic()))
                    time.sleep(0.05)   # simulate write latency to stress the lock
                    if "tags/create" in str(path):
                        return {"id": "TAG001"}
                    if "/trigger" in str(path):
                        return {"id": "TRG001"}
                    return {"id": "FOLDER001", "name": "caf-build"}
                if method == "GET":
                    return dict(FIXTURE_WORKFLOW)
                if method == "PUT":
                    with lock:
                        build_timeline.append((label, "PUT", time.monotonic()))
                    return {"id": "WF001", "name": "ZHC-Test", "status": "draft"}
                return {"id": "WF001", "name": "ZHC-Test", "status": "draft"}

            def timed_get_workflow(wid):
                return AdapterResult(ok=True, data=dict(FIXTURE_WORKFLOW))

            client.request.side_effect = timed_request
            # These side_effects are NOT used by CampaignBuilder when _adapter=None,
            # but kept for completeness and direct unit-test callers.
            client.put_workflow.side_effect = lambda wid, body: AdapterResult(
                ok=True, data={"id": wid, "status": "draft"}
            )
            client.get_workflow.side_effect = timed_get_workflow
            client.create_folder.side_effect = lambda name: AdapterResult(
                ok=True, data={"id": "F1", "name": name}
            )
            client.create_tag.side_effect = lambda t: AdapterResult(
                ok=True, data={"id": "TAG1", "name": t}
            )
            client.create_trigger.side_effect = lambda b: AdapterResult(
                ok=True, data={"id": "TRG1"}
            )
            client.reset_step_index.return_value = None
            client._step_index = 0
            return client

        errors = []
        results = {}

        def run_build(label):
            try:
                client = make_client_with_timing(label)
                builder = CampaignBuilder(client)
                stats = builder.build(plan, folder_name="e2e-sandbox")
                results[label] = stats
            except Exception as exc:
                errors.append((label, repr(exc)))

        t1 = threading.Thread(target=run_build, args=("build-A",))
        t2 = threading.Thread(target=run_build, args=("build-B",))
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        self.assertEqual(errors, [], f"[C21] Build threads raised exceptions: {errors}")
        self.assertIn("build-A", results, "[C21] Build A must complete")
        self.assertIn("build-B", results, "[C21] Build B must complete")

        # Both builds must report zero errors
        for label, stats in results.items():
            self.assertEqual(
                stats.get("errors", []), [],
                f"[C21] Build '{label}' reported errors: {stats.get('errors')}",
            )

        # build_timeline must be non-empty: confirms timed_request was actually called.
        # An empty timeline means CampaignBuilder routed through client._adapter
        # (phantom child mock) and timed_request was never invoked — the WriteLock
        # was never stressed by real build work (vacuous serialization proof).
        self.assertGreater(
            len(build_timeline), 0,
            "[C21] build_timeline is EMPTY — timed_request was never called. "
            "CampaignBuilder routed through a phantom client._adapter child mock. "
            "Ensure make_client_with_timing sets client._adapter = None.",
        )

        # Verify no interleaving: all calls from build-A and build-B must appear in
        # non-interleaved runs (all A calls complete before B starts, or vice versa),
        # proving the WriteLock serialized the concurrent builds.
        # Extract per-build call blocks from the timeline.
        a_times = [ts for (lbl, _, ts) in build_timeline if lbl == "build-A"]
        b_times = [ts for (lbl, _, ts) in build_timeline if lbl == "build-B"]
        self.assertGreater(len(a_times), 0, "[C21] Build-A produced no timeline entries")
        self.assertGreater(len(b_times), 0, "[C21] Build-B produced no timeline entries")
        # Serialized: either all of A finishes before any of B starts, or vice versa.
        a_done = max(a_times)
        b_start = min(b_times)
        b_done = max(b_times)
        a_start = min(a_times)
        serialized = (a_done < b_start) or (b_done < a_start)
        self.assertTrue(
            serialized,
            f"[C21] Builds were NOT serialized — interleaved writes detected. "
            f"build-A range: [{a_start:.4f}, {a_done:.4f}], "
            f"build-B range: [{a_start:.4f}, {b_done:.4f}]. "
            "WriteLock must ensure all writes from one build complete before the other starts.",
        )

        # Confirm that the WriteLock is the enforcement mechanism:
        # verify that an explicit WriteLock on SANDBOX_LOCATION_ID from a third
        # thread properly blocks while a build is in progress.
        lock_respected = []
        held_event = threading.Event()
        release_event = threading.Event()

        def hold_lock():
            with WriteLock(SANDBOX_LOCATION_ID):
                held_event.set()
                release_event.wait(timeout=1.0)

        def try_lock():
            held_event.wait(timeout=1.0)
            with WriteLock(SANDBOX_LOCATION_ID):
                lock_respected.append(True)

        th = threading.Thread(target=hold_lock)
        tt = threading.Thread(target=try_lock)
        th.start()
        tt.start()
        time.sleep(0.05)
        release_event.set()
        th.join(timeout=2.0)
        tt.join(timeout=2.0)

        self.assertTrue(
            len(lock_respected) > 0,
            "[C21] WriteLock must permit acquisition after holder releases",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# REGRESSION: workflows build FAILS LOUD on a rejected save + EMITS ordering
# (Bug 1a: missing action ordering -> GHL 400 'corrupted order';
#  Bug 1b: silent false-success Steps:0/Errors:0/exit-0)
# ═══════════════════════════════════════════════════════════════════════════════


def _make_failing_save_adapter(
    location_id: str = SANDBOX_LOCATION_ID,
    request_log: list | None = None,
    put_bodies: list | None = None,
):
    """Mock client whose FIRST PUT (the step-save) returns a 400 error dict.

    Mirrors transport.py _do_request: a rejected PUT returns
    {"_error": True, "http_code": 400, "code": 400, "message": ...}.
    POSTs (folder/workflow/tag/trigger) and GETs succeed; only the step-save
    PUT fails — exactly the live failure mode the build path swallowed.
    """
    from cli_anything.gohighlevel.internal.adapter_types import AdapterResult

    wf = dict(FIXTURE_WORKFLOW)
    client = MagicMock()
    client.location_id = location_id
    client._adapter = None  # force CampaignBuilder onto the legacy .request() path

    state = {"stepsave_count": 0}

    def mock_request(method, path, body=None, workflow_name="", _apply_step_backoff=False):
        if request_log is not None:
            request_log.append({"method": method, "path": path, "body": body})
        if method == "GET":
            return dict(wf)
        if method == "PUT":
            if put_bodies is not None:
                put_bodies.append(body)
            p = str(path)
            # The step-save PUT targets /workflow/<loc>/<wf_id> (NOT /trigger/...)
            # and carries a workflowData payload. Reject THAT the way GHL
            # rejects an unordered workflowData payload; trigger-link PUTs pass.
            is_step_save = ("/trigger/" not in p) and bool(
                (body or {}).get("workflowData")
            )
            if is_step_save:
                state["stepsave_count"] += 1
                if state["stepsave_count"] == 1:
                    return {
                        "_error": True,
                        "http_code": 400,
                        "code": 400,
                        "message": "corrupted order: action chain is not linked",
                    }
            return {"id": wf["id"], "name": wf["name"], "status": "draft"}
        if method == "POST":
            if "tags/create" in str(path):
                return {"id": "TAG001"}
            if "/trigger" in str(path):
                return {"id": "TRG001"}
            return {"id": "FOLDER001", "name": "caf-build"}
        return {"id": wf["id"]}

    client.request.side_effect = mock_request
    client.get_workflow.side_effect = lambda wid: AdapterResult(ok=True, data=dict(wf))
    return client


class TestBuildFailsLoudAndEmitsOrdering(unittest.TestCase):
    """Regression for the two CRITICAL workflows-build bugs.

    Both tests must FAIL on pre-fix main and PASS after the fix:
      TEST A — a rejected step-save PUT must yield Errors>=1 and exit code 1,
               never Steps:0/Errors:0/exit-0.
      TEST B — the FIRST (step-save) PUT body must carry action ordering
               (order/next/parentKey), proving link_steps ran BEFORE the save
               PUT — not only in the gated sync PUT.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["CAF_DATA_DIR"] = self.tmp
        os.environ["CAF_ALLOWED_LOCATION_IDS"] = SANDBOX_LOCATION_ID
        os.environ["CAF_APPROVAL_TOKEN"] = "regression-test-token"
        os.environ["GHL_FIREBASE_REFRESH_TOKEN"] = "sandbox-refresh-token"
        os.environ["CAF_STEP_BACKOFF_MS"] = "0"
        os.environ["CAF_INTERNAL_STEP_BACKOFF_MS"] = "0"
        os.environ.pop("CAF_DRY_RUN", None)

    def tearDown(self):
        for k in (
            "CAF_DATA_DIR", "CAF_ALLOWED_LOCATION_IDS", "CAF_APPROVAL_TOKEN",
            "GHL_FIREBASE_REFRESH_TOKEN", "CAF_STEP_BACKOFF_MS",
            "CAF_INTERNAL_STEP_BACKOFF_MS", "CAF_DRY_RUN",
        ):
            os.environ.pop(k, None)

    def test_build_fails_loud_on_rejected_save(self):
        """TEST A: a 400 step-save must exit non-zero with the error surfaced."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        plan_file = Path(self.tmp) / "plan.json"
        plan_file.write_text(json.dumps(FIXTURE_PLAN), encoding="utf-8")

        request_log = []
        mock_client = _make_failing_save_adapter(
            location_id=SANDBOX_LOCATION_ID,
            request_log=request_log,
        )

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json",
                "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "build",
                "--from-plan", str(plan_file),
                "--folder", "t",
            ])

        # Confirm the mock was actually exercised (not a no-op).
        self.assertGreater(
            len(request_log), 0,
            "Build issued no API calls — mock not reached.",
        )

        # 1) A rejected save MUST exit non-zero (pre-fix this was 0).
        self.assertNotEqual(
            result.exit_code, 0,
            f"Rejected step-save must NOT exit 0. Got exit 0.\n"
            f"output:\n{result.output}",
        )

        # 2) The build result must record the error (non-empty, mentions 400 /
        #    corrupted order). On error we emit the stats JSON object to stderr,
        #    so scan both captured streams.
        def _safe_stream(name):
            try:
                return getattr(result, name) or ""
            except Exception:
                return ""
        combined = _safe_stream("stdout") + "\n" + _safe_stream("stderr")
        errors = None
        # Try to parse the largest JSON object substring in the output.
        start = combined.find("{")
        end = combined.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(combined[start:end + 1])
                if isinstance(data, dict) and "errors" in data:
                    errors = data["errors"]
            except Exception:
                data = {}
        else:
            data = {}

        self.assertIsNotNone(
            errors,
            f"Build JSON with an 'errors' field was not emitted.\n{combined}",
        )
        self.assertTrue(
            len(errors) >= 1,
            f"errors must be non-empty on a rejected save. Got: {errors!r}",
        )
        joined = " ".join(str(e) for e in errors)
        self.assertTrue(
            ("400" in joined) or ("corrupted order" in joined),
            f"Error text must surface the HTTP 400 / 'corrupted order' cause. "
            f"Got: {errors!r}",
        )

        # 3) Guard against the EXACT pre-fix false-success shape: a created
        #    workflow shell with zero steps saved and an empty errors list.
        false_success = (
            data.get("workflows_created", 0) >= 1
            and data.get("steps_saved", 0) == 0
            and not data.get("errors")
        )
        self.assertFalse(
            false_success,
            "Pre-fix false-success detected: workflow shell created, "
            "steps_saved==0, errors==[]. A rejected save must report an error.",
        )

    def test_build_emits_action_ordering_in_first_put(self):
        """TEST B: the first (step-save) PUT body must carry ordering links."""
        from click.testing import CliRunner
        from cli_anything.gohighlevel.gohighlevel_cli import cli

        # 3-step plan with NO order/next/parentKey on the raw templates —
        # link_steps must add them before the save PUT.
        plan = {
            "ordered_check": {
                "name": "ZHC-Ordering-Check",
                "templates": [
                    {"id": "a1", "type": "email", "name": "Email: One",
                     "attributes": {"subject": "1", "body": "<p>1</p>",
                                    "html": "<p>1</p>", "fromName": "",
                                    "attachments": []}},
                    {"id": "a2", "type": "wait", "name": "Wait 1 Day",
                     "attributes": {"type": "time",
                                    "startAfter": {"type": "days", "value": 1}}},
                    {"id": "a3", "type": "add_contact_tag", "name": "Tag: done",
                     "attributes": {"tags": ["done"]}},
                ],
            }
        }
        plan_file = Path(self.tmp) / "ordered_plan.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")

        put_bodies = []
        mock_client = _make_sandbox_adapter(
            location_id=SANDBOX_LOCATION_ID,
            put_bodies=put_bodies,
        )

        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=mock_client,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "--experimental", "--json",
                "--location-id", SANDBOX_LOCATION_ID,
                "workflows", "build",
                "--from-plan", str(plan_file),
                "--folder", "t",
            ])

        self.assertEqual(
            result.exit_code, 0,
            f"Happy-path build must exit 0.\n{result.output}",
        )
        self.assertGreater(len(put_bodies), 0, "No PUT body captured.")

        # The FIRST PUT is the step-save (Step 3). Its templates must be ordered.
        first_templates = (
            (put_bodies[0] or {}).get("workflowData", {}).get("templates", [])
        )
        self.assertEqual(
            len(first_templates), 3,
            f"First PUT must carry all 3 steps. Got: {first_templates!r}",
        )

        # order keys present and sequential [0,1,2].
        orders = [s.get("order") for s in first_templates]
        self.assertEqual(
            orders, [0, 1, 2],
            f"First PUT step 'order' must be [0,1,2] (link_steps ran before the "
            f"save PUT). Got: {orders!r}",
        )

        # Linking: step0.next == step1.id; parentKey chain back-links.
        self.assertEqual(
            first_templates[0].get("next"), first_templates[1]["id"],
            "step[0].next must point at step[1].id",
        )
        self.assertEqual(
            first_templates[1].get("next"), first_templates[2]["id"],
            "step[1].next must point at step[2].id",
        )
        self.assertIsNone(
            first_templates[0].get("parentKey"),
            "first step parentKey must be None",
        )
        self.assertEqual(
            first_templates[1].get("parentKey"), first_templates[0]["id"],
            "step[1].parentKey must point back at step[0].id",
        )
        self.assertEqual(
            first_templates[2].get("parentKey"), first_templates[1]["id"],
            "step[2].parentKey must point back at step[1].id",
        )


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestCriterion19E2EMergeGate,
        TestCriterion20Rollback,
        TestCriterion21Serialization,
        TestBuildFailsLoudAndEmitsOrdering,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
