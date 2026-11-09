"""WF29 promotion: promote exactly one version, verify it, roll back safely.

Acceptance: B13 (promotion half), IG-AI-06 (promotion and execution are
separate), section 26.4 (previous active version, verified rollback).
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
    ALLOWED_TOOLS,
    agent_document,
    approval_ref,
    fixture,
    ok,
    public_tenant,
    studio_adapter,
)

from _public_contract_fakes import FakeTransport  # noqa: E402

from cli_anything.gohighlevel.public.agent_studio import (  # noqa: E402
    OPERATION_IDS,
    READ_OPERATION,
)
from cli_anything.gohighlevel.public.agent_studio_graph import (  # noqa: E402
    merge_version,
    version_by_id,
)

STAGING_ID = "ver_synthetic_staging_0001"
PRODUCTION_ID = "ver_synthetic_production_0001"


def _current_version() -> dict:
    document = fixture("staging_agent.json")
    return dict(version_by_id(document, STAGING_ID))


def _document_with(version: dict) -> dict:
    return {
        "id": "agent_synthetic_0001",
        "locationId": public_tenant().location_id,
        "name": "Synthetic Flow Agent",
        "status": "active",
        "versions": [version],
    }


class UpdateVersionPreservesUnknownProperties(unittest.TestCase):
    def test_patch_sends_the_complete_version_with_unknown_fields_preserved(
        self,
    ) -> None:
        current = _current_version()
        intent = fixture("intent.json")
        merged, removed = merge_version(current, intent)
        self.assertEqual(removed, [])
        transport = FakeTransport(
            [ok(_document_with(current)), ok({"ok": True}),
             ok(_document_with(merged)), ok(_document_with(merged))]
        )
        adapter, _public = studio_adapter(transport)

        result = adapter.update_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            intent=intent,
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )

        self.assertEqual(result.status.value, "ok", result.error)
        self.assertTrue(result.evidence["agent_studio"]["readback_matched"])
        self.assertEqual(transport.requests[1]["method"], "PATCH")
        self.assertIn(STAGING_ID, transport.requests[1]["url"])
        sent = transport.requests[1]["body"]
        # approved change landed
        self.assertEqual(sent["nodes"][0]["tool"], "conversation.greet.warm")
        self.assertEqual(len(sent["variables"]), 2)
        # unmodified + UNKNOWN properties survived
        self.assertEqual(sent["entryNodeId"], "node_start")
        self.assertEqual(sent["configuration"]["futureTopLevel"], {"keep": "verbatim"})
        lookup = [node for node in sent["nodes"] if node["id"] == "node_lookup"][0]
        self.assertEqual(lookup["configuration"]["unknownFutureField"], {"keep": True})
        # an omitted node is preserved, never deleted by omission
        self.assertEqual([node["id"] for node in sent["nodes"]],
                         ["node_start", "node_lookup"])
        self.assertEqual(transport.call_count, 4)

    def test_an_explicit_removal_is_refused_without_allow_deletions(self) -> None:
        current = _current_version()
        transport = FakeTransport([ok(_document_with(current))])
        adapter, _public = studio_adapter(transport)

        result = adapter.update_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            intent={"configuration": {"locale": None}},
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )

        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error["rule"], "deletion_requires_approval")
        self.assertIn("configuration.locale", result.error["removed_paths"])
        self.assertEqual(transport.call_count, 1)

    def test_an_explicit_removal_proceeds_when_allowed(self) -> None:
        current = _current_version()
        merged, removed = merge_version(
            current, {"configuration": {"locale": None}}, allow_deletions=True
        )
        self.assertEqual(removed, ["configuration.locale"])
        transport = FakeTransport(
            [ok(_document_with(current)), ok({"ok": True}),
             ok(_document_with(merged)), ok(_document_with(merged))]
        )
        adapter, _public = studio_adapter(transport)
        result = adapter.update_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            intent={"configuration": {"locale": None}},
            approval=approval_ref(),
            allow_deletions=True,
            allowed_tools=ALLOWED_TOOLS,
        )
        self.assertEqual(result.status.value, "ok", result.error)
        self.assertNotIn("locale", transport.requests[1]["body"]["configuration"])

    def test_a_stale_expected_version_is_refused(self) -> None:
        current = _current_version()
        transport = FakeTransport([ok(_document_with(current))])
        adapter, _public = studio_adapter(transport)
        result = adapter.update_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            intent=fixture("intent.json"),
            approval=approval_ref(),
            expected_version={"id": STAGING_ID, "status": "staging", "nodes": []},
        )
        self.assertEqual(result.status.value, "conflict")
        self.assertEqual(result.error["rule"], "stale_version")
        self.assertEqual(transport.call_count, 1)

    def test_an_unknown_version_is_not_found(self) -> None:
        transport = FakeTransport([ok(_document_with(_current_version()))])
        adapter, _public = studio_adapter(transport)
        result = adapter.update_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id="ver_synthetic_absent_0001",
            intent=fixture("intent.json"),
            approval=approval_ref(),
        )
        self.assertEqual(result.status.value, "not_found")
        self.assertEqual(result.error["rule"], "version_not_present_in_readback")
        self.assertEqual(transport.call_count, 1)

    def test_a_patch_whose_readback_does_not_match_is_unknown(self) -> None:
        current = _current_version()
        transport = FakeTransport(
            [ok(_document_with(current)), ok({"ok": True}),
             ok(_document_with(current)), ok(_document_with(current))]
        )
        adapter, _public = studio_adapter(transport)
        result = adapter.update_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            intent={"variables": [{"name": "topic"}, {"name": "channel"}]},
            approval=approval_ref(),
            allowed_tools=ALLOWED_TOOLS,
        )
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "version_readback_mismatch")
        self.assertIn("variables", result.error["fields"])


class PromoteExactVersion(unittest.TestCase):
    def _promote(self, responses, **kwargs):
        transport = FakeTransport(responses)
        adapter, _public = studio_adapter(transport)
        result = adapter.promote_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=kwargs.pop("version_id", STAGING_ID),
            approval=approval_ref(),
            **kwargs,
        )
        return result, transport, adapter

    def test_promotion_names_the_previous_active_version_and_verifies_identity(
        self,
    ) -> None:
        document = fixture("staging_agent.json")
        promoted = fixture("promoted_agent.json")
        result, transport, _adapter = self._promote(
            [ok(document), ok({"ok": True}), ok(document), ok(promoted)]
        )

        self.assertEqual(result.status.value, "ok", result.error)
        studio = result.evidence["agent_studio"]
        self.assertEqual(studio["promoted_version_id"], STAGING_ID)
        self.assertEqual(studio["previous_active_version_id"], PRODUCTION_ID)
        self.assertTrue(studio["promoted_identity_verified"])
        self.assertEqual(transport.requests[1]["method"], "POST")
        self.assertTrue(transport.requests[1]["url"].endswith("/publish"))
        self.assertIn(STAGING_ID, transport.requests[1]["url"])

    def test_promotion_without_a_readable_active_version_is_refused(self) -> None:
        document = agent_document(production_id=None)
        result, transport, _adapter = self._promote([ok(document)])
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error["rule"], "previous_active_version_unknown")
        self.assertEqual(transport.call_count, 1)

    def test_promotion_whose_identity_does_not_change_is_unknown(self) -> None:
        document = fixture("staging_agent.json")
        result, _transport, _adapter = self._promote(
            [ok(document), ok({"ok": True}), ok(document), ok(document)]
        )
        self.assertEqual(result.status.value, "unknown_outcome")
        self.assertEqual(result.error["rule"], "promoted_identity_mismatch")

    def test_promoting_a_version_that_is_not_present_is_not_found(self) -> None:
        document = fixture("staging_agent.json")
        result, transport, _adapter = self._promote(
            [ok(document)], version_id="ver_synthetic_absent_0001"
        )
        self.assertEqual(result.status.value, "not_found")
        self.assertEqual(result.error["rule"], "promotion_target_not_present")
        self.assertEqual(transport.call_count, 1)

    def test_promoting_the_current_production_version_is_a_conflict(self) -> None:
        document = fixture("staging_agent.json")
        result, transport, _adapter = self._promote(
            [ok(document)], version_id=PRODUCTION_ID
        )
        self.assertEqual(result.status.value, "conflict")
        self.assertEqual(result.error["rule"], "version_already_production")
        self.assertEqual(transport.call_count, 1)

    def test_a_stale_expected_active_version_is_a_conflict(self) -> None:
        document = fixture("staging_agent.json")
        result, transport, _adapter = self._promote(
            [ok(document)], expected_active_version="ver_synthetic_other_0001"
        )
        self.assertEqual(result.status.value, "conflict")
        self.assertEqual(result.error["rule"], "stale_active_version")
        self.assertEqual(transport.call_count, 1)


class RollbackUsesThePromotionMechanism(unittest.TestCase):
    def test_rollback_without_a_recorded_previous_version_is_refused(self) -> None:
        transport = FakeTransport()
        adapter, _public = studio_adapter(transport)
        result = adapter.rollback(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            approval=approval_ref(),
        )
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(
            result.error["rule"], "rollback_without_recorded_previous_version"
        )
        self.assertEqual(transport.call_count, 0)

    def test_rollback_promotes_the_recorded_previous_version(self) -> None:
        document = fixture("staging_agent.json")
        promoted = fixture("promoted_agent.json")
        restored = agent_document(
            staging_id=STAGING_ID, production_id=PRODUCTION_ID
        )
        transport = FakeTransport(
            [
                # first: promote the staging version
                ok(document), ok({"ok": True}), ok(document), ok(promoted),
                # then: roll back to the recorded previous version
                ok(promoted), ok({"ok": True}), ok(promoted), ok(restored),
            ]
        )
        adapter, _public = studio_adapter(transport)
        first = adapter.promote_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            approval=approval_ref(),
        )
        self.assertEqual(first.status.value, "ok", first.error)

        second = adapter.rollback(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            approval=approval_ref(),
        )
        self.assertEqual(second.status.value, "ok", second.error)
        self.assertEqual(
            second.evidence["agent_studio"]["promoted_version_id"], PRODUCTION_ID
        )
        # a rollback is a promotion of a version, never a status mutation
        self.assertEqual(transport.requests[5]["method"], "POST")
        self.assertTrue(transport.requests[5]["url"].endswith("/publish"))

    def test_rollback_to_an_unrecorded_target_is_refused(self) -> None:
        document = fixture("staging_agent.json")
        promoted = fixture("promoted_agent.json")
        transport = FakeTransport(
            [ok(document), ok({"ok": True}), ok(document), ok(promoted)]
        )
        adapter, _public = studio_adapter(transport)
        adapter.promote_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            approval=approval_ref(),
        )
        result = adapter.rollback(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            approval=approval_ref(),
            to_version_id="ver_synthetic_never_promoted_0001",
        )
        self.assertEqual(result.status.value, "denied")
        self.assertEqual(result.error["rule"], "rollback_target_not_recorded")
        self.assertEqual(transport.call_count, 4)


class PromotionIsSeparatelyAuthorized(unittest.TestCase):
    def test_promotion_works_while_execution_stays_disabled(self) -> None:
        document = fixture("staging_agent.json")
        promoted = fixture("promoted_agent.json")
        transport = FakeTransport(
            [ok(document), ok({"ok": True}), ok(document), ok(promoted)]
        )
        adapter, _public = studio_adapter(
            transport,
            enabled=[READ_OPERATION, OPERATION_IDS["version.promote"]],
        )
        promoted_result = adapter.promote_version(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            version_id=STAGING_ID,
            approval=approval_ref(),
        )
        self.assertEqual(promoted_result.status.value, "ok", promoted_result.error)

        executed = adapter.execute(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            payload={"locationId": public_tenant().location_id},
            approval=approval_ref(),
            output_expect={"status": "completed"},
        )
        self.assertEqual(executed.status.value, "denied")
        self.assertEqual(executed.error["rule"], "capability_disabled")
        self.assertEqual(executed.evidence["operation_id"],
                         OPERATION_IDS["agent.execute"])


if __name__ == "__main__":
    unittest.main()
