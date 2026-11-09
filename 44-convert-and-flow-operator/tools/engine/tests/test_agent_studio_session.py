"""WF29 execution-session isolation.

Acceptance: IG-AI-07 (an execution session cannot cross locations, agents or
unrelated contacts), section 26.3.
Every transport response is scripted; every id is synthetic.
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from agent_studio_support import (  # noqa: E402
    OTHER_TENANT,
    approval_ref,
    execution_response,
    fixture,
    ok,
    public_tenant,
    studio_adapter,
)

from _public_contract_fakes import FakeTransport  # noqa: E402

from cli_anything.gohighlevel.public.agent_studio import (  # noqa: E402
    ExecutionSession,
    session_mismatch,
)

PRODUCTION_ID = "ver_synthetic_production_0001"
CONTACT = "contact_synthetic_0001"
THREAD = "thread_synthetic_0001"


def _execute(transport, **overrides):
    adapter, _public = studio_adapter(transport)
    kwargs = {
        "tenant": public_tenant(),
        "agent_id": "agent_synthetic_0001",
        "payload": {"locationId": public_tenant().location_id,
                    "message": {"text": "synthetic input"}},
        "approval": approval_ref(),
        "output_expect": {"status": "completed"},
        "contact_id": CONTACT,
        "thread_id": THREAD,
    }
    kwargs.update(overrides)
    return adapter.execute(**kwargs), adapter


class BoundSession(unittest.TestCase):
    def test_a_successful_execution_binds_every_identity_field(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [ok(document), execution_response(), ok(document)]
        )

        result, adapter = _execute(transport)
        self.assertEqual(result.status.value, "ok", result.error)
        session = adapter.session("exec_synthetic_0001")
        self.assertIsNotNone(session)
        self.assertEqual(session.location_id, public_tenant().location_id)
        self.assertEqual(session.agent_id, "agent_synthetic_0001")
        self.assertEqual(session.version_id, PRODUCTION_ID)
        self.assertEqual(session.version_policy, "production")
        self.assertEqual(session.contact_id, CONTACT)
        self.assertEqual(session.thread_id, THREAD)

    def test_the_same_binding_may_continue_the_same_session(self) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport(
            [
                ok(document), execution_response(), ok(document),
                ok(document), execution_response(), ok(document),
            ]
        )
        first, adapter = _execute(transport)
        self.assertEqual(first.status.value, "ok", first.error)
        session = adapter.session("exec_synthetic_0001")

        second = adapter.execute(
            tenant=public_tenant(),
            agent_id="agent_synthetic_0001",
            payload={"locationId": public_tenant().location_id},
            approval=approval_ref(),
            output_expect={"status": "completed"},
            contact_id=CONTACT,
            thread_id=THREAD,
            session=session,
        )
        self.assertEqual(second.status.value, "ok", second.error)


class CrossBoundaries(unittest.TestCase):
    def _session(self, **overrides):
        values = {
            "execution_id": "exec_synthetic_0001",
            "location_id": public_tenant().location_id,
            "agent_id": "agent_synthetic_0001",
            "version_id": PRODUCTION_ID,
            "version_policy": "production",
            "contact_id": CONTACT,
            "thread_id": THREAD,
        }
        values.update(overrides)
        return ExecutionSession(**values)

    def _refused(self, crossed: str, **overrides) -> None:
        document = fixture("staging_agent.json")
        transport = FakeTransport([ok(document)])
        result, _adapter = _execute(
            transport, session=self._session(**overrides)
        )
        self.assertEqual(result.status.value, "denied", result.error)
        self.assertEqual(result.error["rule"], "execution_session_cross_bound")
        self.assertEqual(result.error["crossed"], crossed)
        # the session check happens after the precondition read, never after a write
        self.assertEqual(transport.call_count, 1)

    def test_a_session_cannot_cross_locations(self) -> None:
        self._refused("location_id", location_id=OTHER_TENANT)

    def test_a_session_cannot_cross_agents(self) -> None:
        self._refused("agent_id", agent_id="agent_synthetic_0002")

    def test_a_session_cannot_cross_contacts(self) -> None:
        self._refused("contact_id", contact_id="contact_synthetic_0002")

    def test_a_session_cannot_cross_threads(self) -> None:
        self._refused("thread_id", thread_id="thread_synthetic_0002")

    def test_a_session_cannot_cross_version_policies(self) -> None:
        self._refused("version_policy", version_policy="staging")

    def test_a_session_cannot_cross_promoted_versions(self) -> None:
        self._refused("version_id", version_id="ver_synthetic_other_0001")


class SessionMismatchUnit(unittest.TestCase):
    def _session(self, **overrides):
        values = {
            "execution_id": "exec_synthetic_0001",
            "location_id": "loc_synthetic_0001",
            "agent_id": "agent_synthetic_0001",
            "version_id": "ver_synthetic_production_0001",
            "version_policy": "production",
            "contact_id": CONTACT,
            "thread_id": THREAD,
        }
        values.update(overrides)
        return ExecutionSession(**values)

    def _check(self, session, **overrides):
        kwargs = {
            "tenant": public_tenant(),
            "agent_id": "agent_synthetic_0001",
            "version_policy": "production",
            "version_id": "ver_synthetic_production_0001",
            "contact_id": CONTACT,
            "thread_id": THREAD,
        }
        kwargs.update(overrides)
        return session_mismatch(session, **kwargs)

    def test_a_matching_session_has_no_mismatch(self) -> None:
        self.assertIsNone(self._check(self._session()))

    def test_a_none_contact_matches_a_session_with_no_contact(self) -> None:
        self.assertIsNone(
            self._check(self._session(contact_id=None), contact_id=None)
        )

    def test_an_unresolved_version_is_not_compared(self) -> None:
        self.assertIsNone(self._check(self._session(), version_id=None))

    def test_a_non_session_object_is_named(self) -> None:
        self.assertEqual(self._check({"execution_id": "x"}), "session_invalid")


if __name__ == "__main__":
    unittest.main()
