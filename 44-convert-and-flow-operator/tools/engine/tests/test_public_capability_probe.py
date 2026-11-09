"""WF01 read-only beta probe and the capability command module.

Covers: A02 (beta reason recorded), IG-ROUTE-10 (useful refusal, zero writes),
and the "read-only probe" half of Document 1 section 4.3.

Every test is offline: a recording fake transport stands in for the network.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    SYNTHETIC_TOKEN,
    FakeTransport,
    fake_auth,
    resp,
)

from cli_anything.gohighlevel.public.auth import AuthKind  # noqa: E402
from cli_anything.gohighlevel.public.capability_command import (  # noqa: E402
    WORKFLOW_STEP_TYPES_PATH,
    probe_family,
    probe_workflow_family,
    register,
)

FIXED = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


class WorkflowProbeTests(unittest.TestCase):
    def _probe(self, transport: FakeTransport, auth=None):
        return probe_workflow_family(
            tenant=SYNTHETIC_TENANT,
            auth=auth or fake_auth(),
            transport=transport,
            clock=lambda: FIXED,
        )

    def test_probe_is_the_documented_read_only_get(self) -> None:
        transport = FakeTransport([resp(200, b'{"stepTypes":[]}')])
        result = self._probe(transport)
        self.assertEqual(transport.call_count, 1)
        call = transport.last
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], WORKFLOW_STEP_TYPES_PATH)
        # The probe carries its own operation page Version, not a global default.
        self.assertEqual(call["version"], "v3")
        self.assertEqual(call["query"], {"limit": 1, "locationId": SYNTHETIC_TENANT})
        self.assertIsNone(call["body"])
        self.assertEqual(result.classification, "ok")
        self.assertEqual(result.public_beta_state, "enabled")
        self.assertEqual(result.available_route, "public_rest")
        self.assertFalse(result.refused)

    def test_beta_denial_is_recorded_with_the_private_fallback(self) -> None:
        transport = FakeTransport(
            [
                resp(
                    403,
                    b'{"code":"WORKFLOW_API_NOT_ENABLED_FOR_LOCATION",'
                    b'"message":"Workflow API is not enabled for location"}',
                )
            ]
        )
        result = self._probe(transport)
        self.assertEqual(result.classification, "beta_not_enabled")
        self.assertEqual(result.public_beta_state, "beta_not_enabled")
        self.assertEqual(result.available_route, "private_fallback")
        self.assertEqual(result.provider_code, "WORKFLOW_API_NOT_ENABLED_FOR_LOCATION")
        self.assertTrue(result.refused)

    def test_a_401_is_never_called_a_beta_flag(self) -> None:
        transport = FakeTransport([resp(401, b'{"message":"token expired"}')])
        result = self._probe(transport)
        self.assertEqual(result.classification, "unauthorized")
        self.assertEqual(result.public_beta_state, "unknown")
        self.assertEqual(result.available_route, "none")

    def test_missing_credential_refuses_without_a_network_call(self) -> None:
        from cli_anything.gohighlevel.public.errors import CredentialMissing

        def explode(name: str) -> str:
            raise CredentialMissing(detail={"name": name})

        transport = FakeTransport()
        auth = fake_auth()
        object.__setattr__(auth, "resolve_secret", explode)
        result = self._probe(transport, auth)
        self.assertEqual(result.refusal_reason, "credential_missing")
        self.assertTrue(result.refused)
        self.assertEqual(transport.call_count, 0)

    def test_probe_result_never_carries_the_token(self) -> None:
        transport = FakeTransport([resp(200)])
        result = self._probe(transport)
        blob = json.dumps(result.as_document())
        self.assertNotIn(SYNTHETIC_TOKEN, blob)
        self.assertIn("credential_fingerprint", result.as_document())
        self.assertNotIn("Bearer", blob)

    def test_unimplemented_family_refuses_with_zero_writes(self) -> None:
        transport = FakeTransport()
        result = probe_family(
            family="contacts",
            tenant=SYNTHETIC_TENANT,
            auth=fake_auth(),
            transport=transport,
            clock=lambda: FIXED,
        )
        self.assertTrue(result.refused)
        self.assertEqual(result.refusal_reason, "probe_family_unimplemented")
        self.assertEqual(result.available_route, "none")
        self.assertEqual(transport.call_count, 0)

    def test_firebase_credential_is_not_substituted_for_the_probe(self) -> None:
        # A Firebase token is a different credential class; the probe sends the
        # token-id header it resolves, never a Bearer value it does not own.
        transport = FakeTransport([resp(401, b"{}")])
        auth = fake_auth(kind=AuthKind.firebase_internal, name="GHL_FIREBASE_REFRESH_TOKEN")
        result = probe_workflow_family(
            tenant=SYNTHETIC_TENANT, auth=auth, transport=transport, clock=lambda: FIXED
        )
        self.assertEqual(result.credential_ref, "env:GHL_FIREBASE_REFRESH_TOKEN")
        self.assertEqual(transport.last["headers"], {"token-id": SYNTHETIC_TOKEN})


class RegistrationTests(unittest.TestCase):
    def test_register_attaches_the_capabilities_group(self) -> None:
        import click
        from click.testing import CliRunner

        @click.group()
        def cli() -> None:
            """test root"""

        register(cli)
        runner = CliRunner()
        listed = runner.invoke(cli, ["capabilities", "--help"])
        self.assertEqual(listed.exit_code, 0, listed.output)
        probe_help = runner.invoke(cli, ["capabilities", "probe", "--help"])
        self.assertEqual(probe_help.exit_code, 0, probe_help.output)
        self.assertIn("--family", probe_help.output)

    def test_write_probe_is_refused(self) -> None:
        import click
        from click.testing import CliRunner

        @click.group()
        def cli() -> None:
            """test root"""

        register(cli)
        result = CliRunner().invoke(
            cli, ["capabilities", "probe", "--no-read-only"], obj={"json": True}
        )
        self.assertEqual(result.exit_code, 2)
        self.assertIn("write_probe_not_implemented", result.output + str(result.exception or ""))


if __name__ == "__main__":
    unittest.main()
