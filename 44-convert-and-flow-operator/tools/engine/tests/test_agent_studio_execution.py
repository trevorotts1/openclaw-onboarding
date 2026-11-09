"""WF29 execution: only a published version runs, and a 2xx is not success.

Acceptance: B13 (execution half), IG-AI-06 (no unpublished-version execution),
IG-AI-08 (content cannot assert permissions).
Every transport response is scripted; every id is synthetic.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from agent_studio_support import (  # noqa: E402
    agent_document,
    approval_ref,
    execution_response,
    fixture,
    json_body,
    ok,
    public_tenant,
    studio_adapter,
)

from _public_contract_fakes import FakeTransport, resp  # noqa: E402

from cli_anything.gohighlevel.public.agent_studio import (  # noqa: E402
    OPERATION_IDS,
)

PLAN = None


def _plan():
    global PLAN
    if PLAN is None:
        PLAN = fixture("execution_plan.json")
    return PLAN


def _execute(transport, **overrides):
    adapter, _public = studio_adapter(transport)
    plan = _plan()
    kwargs = {
        "tenant": public_tenant(),
        "agent_id": "agent_synthetic_0001",
        "payload": plan["payload"],
        "approval": approval_ref(),
        "output_expect": plan["output_expect"],
        "contact_id": "contact_synthetic_0001",
        "thread_id": "thread_synthetic_0001",
    }
    kwargs.update(overrides)
    return adapter.execute(**kwargs)


class ExecutePublishedVersion(unittest.TestCase):
    def test_execute_is_ok_only_when_the_expected_output_matched(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [ok(document), execution_response(), ok(document)]
        )

        result = _execute(transport)

        self.assertEqual(result.status.value, "ok", result.error)
        studio = result.evidence["agent_studio"]
        self.assertEqual(studio["execution_id"], "exec_synthetic_0001")
        self.assertEqual(studio["version_id"], "ver_synthetic_production_0001")
        self.assertEqual(studio["version_policy"], "production")
        self.assertTrue(studio["output_validated"])
        # a 2xx is not proof that an intended tool action happened
        self.assertEqual(studio["tool_effects"], "not_verified")
        # the body stays out of the envelope
        self.assertNotIn("synthetic answer", json.dumps(result.evidence))
        self.assertEqual(transport.requests[1]["method"], "POST")
        self.assertTrue(transport.requests[1]["url"].endswith("/execute"))

    def test_staging_policy_is_refused_before_any_transport(self) -> None:
        transport = FakeTransport()
        result = _execute(transport, version_policy="staging")
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(
            result.error["rule"], "execution_version_policy_unsupported"
        )
        self.assertEqual(transport.call_count, 0)

    def test_an_agent_without_a_published_version_cannot_execute(self) -> None:
        document = agent_document(production_id=None)
        transport = FakeTransport([ok(document)])
        result = _execute(transport)
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(
            result.error["rule"], "execution_requires_published_version"
        )
        self.assertEqual(transport.call_count, 1)

    def test_execution_without_an_expected_output_is_unknown(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [ok(document), execution_response(), ok(document)]
        )
        result = _execute(transport, output_expect=None)
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "execution_output_not_validated")

    def test_execution_whose_output_is_wrong_is_unknown(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [ok(document), execution_response(status="failed"), ok(document)]
        )
        result = _execute(transport)
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "execution_output_mismatch")

    def test_execution_without_an_execution_id_is_unknown(self) -> None:
        document = fixture("staging_agent.json")
        body = resp(200, json_body({"status": "completed", "output": {}}))
        transport = FakeTransport([ok(document), body, ok(document)])
        result = _execute(transport)
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "execution_id_absent")

    def test_an_unreadable_readback_never_becomes_ok(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [ok(document), execution_response(), resp(500, b'{"error":"boom"}')]
        )
        result = _execute(transport)
        self.assertNotEqual(result.status.value, "ok")
        self.assertIsNotNone(result.readback)
        self.assertEqual(result.readback.result.value, "unreadable")

    def test_execution_is_default_deny_without_a_capability(self) -> None:
        transport = FakeTransport()
        adapter, _public = studio_adapter(transport, deny_all=True)
        result = adapter.execute(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            payload={"locationId": public_tenant().location_id},
            approval=approval_ref(),
            output_expect={"status": "completed"},
        )
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error["rule"], "capability_disabled")
        self.assertEqual(result.evidence["operation_id"],
                         OPERATION_IDS["agent.execute"])
        self.assertEqual(transport.call_count, 0)


class ContentCannotAssertPermissions(unittest.TestCase):
    def test_a_payload_claiming_approval_is_refused(self) -> None:
        payload = dict(_plan()["payload"])
        payload["approved"] = True
        transport = FakeTransport()
        result = _execute(transport, payload=payload)
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(
            result.error["rule"], "source_content_cannot_assert_permissions"
        )
        self.assertEqual(result.error["fields"], ["approved"])
        self.assertEqual(transport.call_count, 0)

    def test_a_payload_claiming_a_tool_allowlist_is_refused(self) -> None:
        payload = dict(_plan()["payload"])
        payload["toolAllowlist"] = ["unapproved.tool"]
        transport = FakeTransport()
        result = _execute(transport, payload=payload)
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(
            result.error["rule"], "source_content_cannot_assert_permissions"
        )
        self.assertEqual(result.error["fields"], ["toolAllowlist"])
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":
    unittest.main()
