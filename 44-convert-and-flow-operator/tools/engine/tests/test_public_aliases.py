"""Alias map -- GU-004 section 4.

Every alias the freeze names is either mapped to an operation id or listed in
``UNMAPPED`` with a reason.  No alias may silently return ``None`` without an
entry.  Credential and tenant aliases are proven against their frozen owner
(``public/auth.py``), which is present today; the operation-id alias table needs
``public/aliases.py`` and is reported as blocked until that module lands.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    FROZEN_OPERATIONS,
    REGISTRY_PRESENT,
    REGISTRY_REASON,
    SYNTHETIC_TENANT,
    SYNTHETIC_TOKEN,
)

from cli_anything.gohighlevel.public.auth import (  # noqa: E402
    AGENCY_PIT_ALIASES,
    FIREBASE_ALIASES,
    FIREBASE_FILE_ALIASES,
    LOCATION_ID_ALIASES,
    LOCATION_ID_FILE_ALIASES,
    LOCATION_PIT_ALIASES,
    LOCATION_PIT_FILE_ALIASES,
    AuthKind,
    resolve_auth,
    resolve_tenant_from_env,
)
from cli_anything.gohighlevel.public.errors import (  # noqa: E402
    ContractViolation,
    CredentialMissing,
)

try:  # the alias lane has not landed aliases.py yet
    from cli_anything.gohighlevel.public import aliases as _aliases  # noqa: E402

    _ALIASES_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - import failure path
    _aliases = None
    _ALIASES_ERROR = f"{type(exc).__name__}: {exc}"

_ALIASES_PRESENT = _aliases is not None
_ALIASES_REASON = (
    "BLOCKED: public/aliases.py not present at import time "
    f"({_ALIASES_ERROR}); assertions are frozen as written"
)

# Section 4.2 -- community MCP tool -> operation id.
COMMUNITY_MAPPED = {
    "ghl_list_products": "products.list",
    "ghl_get_product": "products.get",
    "ghl_create_product": "products.create",
    "ghl_update_product": "products.update",
    "ghl_delete_product": "products.delete",
    "ghl_create_price": "products.prices.create",
    "ghl_list_prices": "products.prices.list",
    "list_invoices": "invoices.list",
    "get_invoice": "invoices.get",
    "create_invoice": "invoices.create",
    "send_invoice": "invoices.send",
    "create_invoice_schedule": "invoices.schedules.create",
    "list_subscriptions": "subscriptions.list",
    "get_subscription_by_id": "subscriptions.get",
    "list_estimates": "estimates.list",
    "create_estimate": "estimates.create",
    "send_estimate": "estimates.send",
    "list_orders": "orders.list",
    "get_order_by_id": "orders.get",
    "list_transactions": "transactions.list",
    "get_transaction_by_id": "transactions.get",
    "record_order_payment": "orders.recordPayment",
    "list_coupons": "coupons.list",
    "get_coupon": "coupons.get",
    "create_coupon": "coupons.create",
    "update_coupon": "coupons.update",
    "delete_coupon": "coupons.delete",
    "ghl_list_workflows": "workflows.list",
    "ghl_get_workflow": "workflows.definition.read",
    "ghl_trigger_workflow": "workflows.enroll",
    "ghl_publish_workflow": "workflows.status.publish",
}

# Section 4.3 -- official MCP tool names.
OFFICIAL_MCP_MAPPED = {
    "list_locations": "mcp.list_locations",
    "search_operations": "mcp.search_operations",
    "describe_operation": "mcp.describe_operation",
    "execute_operation": "mcp.execute_operation",
}

# Section 4.2 / 4.3 -- explicitly unmapped, with a reason.
COMMUNITY_UNMAPPED = (
    "ghl_create_product_collection",
    "ghl_list_product_collections",
    "ghl_list_inventory",
    "ghl_bulk_edit_products",
    "update_invoice",
    "delete_invoice",
    "view_invoice",
    "generate_invoice_number",
    "list_invoice_schedules",
    "get_invoice_schedule",
    "update_invoice_schedule",
    "update_saas_subscription",
    "rebilling_update",
    "create_invoice_from_estimate",
    "generate_estimate_number",
    "list_gateways",
    "create_voice_ai_agent",
    "update_voice_ai_agent",
    "list_voice_ai_agents",
    "get_voice_ai_call_log",
    "ghl_buy_phone_number",
    "ghl_list_phone_numbers",
    "update_phone_number",
    "ghl_get_call_recording",
    "update_call_forwarding",
    "ghl_create_agent",
    "ghl_update_agent",
    "ghl_deploy_agent",
    "ghl_list_agents",
    "ghl_create_workflow",
    "ghl_update_workflow_actions",
)

OFFICIAL_MCP_UNMAPPED = ("search", "fetch")

# Section 4.4 -- collision names that are not operation ids.
COLLISION_NAMES = (
    "ghl-mcp",
    "leadconnector",
    "ghl-community-mcp",
    "caf",
    "convertandflow",
    "ghl",
)


def _rule_of(alias: str) -> str | None:
    """The refusal rule for an alias, or None when it resolves."""

    try:
        _aliases.resolve_alias(alias)
    except ContractViolation as exc:
        return exc.rule
    return None


def _unmapped_entry(alias: str):
    getter = getattr(_aliases.UNMAPPED, "get", None)
    assert callable(getter), "UNMAPPED must expose .get(alias) -> entry"
    return getter(alias)


@unittest.skipUnless(_ALIASES_PRESENT, _ALIASES_REASON)
class OperationAliasTableTest(unittest.TestCase):
    def test_every_mapped_community_alias_resolves_exactly(self) -> None:
        for alias, operation_id in COMMUNITY_MAPPED.items():
            with self.subTest(alias=alias):
                self.assertEqual(_aliases.resolve_operation_alias(alias), operation_id)
                self.assertEqual(_aliases.resolve_alias(alias).kind, "operation")

    def test_every_mapped_official_mcp_alias_resolves_exactly(self) -> None:
        for alias, operation_id in OFFICIAL_MCP_MAPPED.items():
            with self.subTest(alias=alias):
                self.assertEqual(_aliases.resolve_operation_alias(alias), operation_id)

    def test_every_unmapped_alias_is_listed_with_a_reason(self) -> None:
        for alias in COMMUNITY_UNMAPPED + OFFICIAL_MCP_UNMAPPED:
            with self.subTest(alias=alias):
                self.assertIn(alias, _aliases.UNMAPPED)
                entry = _unmapped_entry(alias)
                self.assertTrue(entry.reason.strip(), f"{alias} has an empty reason")
                self.assertTrue(entry.evidence.strip(), f"{alias} has no evidence")
                self.assertTrue(entry.category.strip(), f"{alias} has no category")
                self.assertEqual(_rule_of(alias), "alias_unmapped")

    def test_every_unmapped_alias_has_no_operation_target(self) -> None:
        for alias in COMMUNITY_UNMAPPED + OFFICIAL_MCP_UNMAPPED:
            with self.subTest(alias=alias):
                with self.assertRaises(ContractViolation) as caught:
                    _aliases.resolve_operation_alias(alias)
                self.assertEqual(caught.exception.rule, "alias_unmapped")

    def test_the_retired_community_service_is_explicit_and_never_a_route(self) -> None:
        resolution = _aliases.resolve_alias("ghl-community-mcp")
        self.assertEqual(resolution.kind, "service")
        self.assertEqual(resolution.target, "retired_community_service")
        with self.assertRaises(ContractViolation) as caught:
            _aliases.resolve_operation_alias("ghl-community-mcp")
        self.assertEqual(caught.exception.rule, "alias_not_an_operation")

    def test_the_ghl_mcp_collision_resolves_only_by_context(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            _aliases.resolve_alias("ghl-mcp")
        self.assertEqual(caught.exception.rule, "alias_collision_context_required")
        self.assertEqual(
            caught.exception.detail["contexts"], ["mcp.servers", "systemd"]
        )
        self.assertEqual(
            _aliases.resolve_service_alias("ghl-mcp", context="mcp.servers"),
            "official_mcp_connection",
        )
        self.assertEqual(
            _aliases.resolve_service_alias("ghl-mcp", context="systemd"),
            "retired_community_service",
        )
        with self.assertRaises(ContractViolation):
            _aliases.resolve_service_alias("ghl-mcp", context="not.a.context")
        self.assertNotEqual(
            _aliases.resolve_service_alias("ghl-mcp", context="mcp.servers"),
            _aliases.resolve_service_alias("ghl-mcp", context="systemd"),
        )

    def test_no_alias_silently_returns_none(self) -> None:
        sweep = (
            list(COMMUNITY_MAPPED)
            + list(OFFICIAL_MCP_MAPPED)
            + list(COMMUNITY_UNMAPPED)
            + list(OFFICIAL_MCP_UNMAPPED)
            + list(COLLISION_NAMES)
        )
        for alias in sweep:
            with self.subTest(alias=alias):
                rule = _rule_of(alias)
                self.assertNotEqual(
                    rule, "alias_unknown", f"{alias} is silently dropped"
                )
                if rule == "alias_unmapped":
                    self.assertIn(alias, _aliases.UNMAPPED)
                else:
                    resolution = _aliases.lookup_alias(alias)
                    self.assertIsNotNone(resolution)
                    self.assertEqual(resolution.alias, alias)
                    self.assertTrue(resolution.kind)
                    if resolution.kind != "collision":
                        self.assertIsNotNone(resolution.target)

    def test_ghl_loc_is_explicitly_unmapped(self) -> None:
        self.assertIn("GHL_LOC", _aliases.UNMAPPED)
        entry = _unmapped_entry("GHL_LOC")
        self.assertEqual(entry.category, "tenant")
        self.assertTrue(entry.reason.strip())
        self.assertEqual(_rule_of("GHL_LOC"), "alias_unmapped")

    def test_lookup_alias_is_explicit_about_unmapped_names(self) -> None:
        for alias in COMMUNITY_UNMAPPED + OFFICIAL_MCP_UNMAPPED:
            with self.subTest(alias=alias):
                self.assertIsNone(_aliases.lookup_alias(alias))
                self.assertIn(alias, _aliases.UNMAPPED)

    def test_mapped_and_unmapped_tables_do_not_overlap(self) -> None:
        for alias in list(COMMUNITY_MAPPED) + list(OFFICIAL_MCP_MAPPED):
            with self.subTest(alias=alias):
                self.assertNotIn(alias, _aliases.UNMAPPED)
                self.assertIsNotNone(_aliases.lookup_alias(alias))

    def test_credential_aliases_carry_their_auth_class(self) -> None:
        for alias in LOCATION_PIT_ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(
                    _aliases.resolve_credential_alias(alias), AuthKind.location_pit
                )
        for alias in FIREBASE_ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(
                    _aliases.resolve_credential_alias(alias), AuthKind.firebase_internal
                )

    def test_tenant_aliases_all_carry_the_location_target(self) -> None:
        for alias in LOCATION_ID_ALIASES:
            with self.subTest(alias=alias):
                self.assertEqual(_aliases.resolve_tenant_alias(alias), "location_id")

    @unittest.skipUnless(REGISTRY_PRESENT, REGISTRY_REASON)
    def test_every_mapped_target_exists_in_the_frozen_registry(self) -> None:
        targets = set(COMMUNITY_MAPPED.values()) | set(OFFICIAL_MCP_MAPPED.values())
        for operation_id in sorted(targets):
            with self.subTest(operation_id=operation_id):
                self.assertIn(operation_id, FROZEN_OPERATIONS)


class CredentialAliasTest(unittest.TestCase):
    def test_location_pit_alias_union_matches_the_freeze(self) -> None:
        frozen = (
            "GOHIGHLEVEL_API_KEY",
            "GHL_API_KEY",
            "GHL_PIT",
            "GHL_TOKEN",
            "GHL_PRIVATE_INTEGRATION_TOKEN",
            "PRIVATE_INTEGRATION_TOKEN",
            "GHL_PRIVATE_TOKEN",
            "PIT_TOKEN",
            "GHL_PIT_TOKEN",
            "GOHIGHLEVEL_LOCATION_PIT",
            "GHL_LOCATION_PIT",
            "GOHIGHLEVEL_PIT",
            "GOHIGHLEVEL_CF_PIT",
            "CONVERT_AND_FLOW_API_KEY",
            "CONVERT_AND_FLOW_PIT",
            "CONVERT_AND_FLOW_PRIVATE_INTEGRATION_TOKEN",
            "CONVERTANDFLOW_API_KEY",
            "CONVERTFLOW_API_KEY",
            "PODCAST_ENGINE_GHL_PIT",
        )
        self.assertEqual(LOCATION_PIT_ALIASES, frozen)

    def test_every_location_pit_alias_resolves(self) -> None:
        for alias in LOCATION_PIT_ALIASES:
            with self.subTest(alias=alias):
                auth = resolve_auth(
                    kind=AuthKind.location_pit,
                    env={alias: SYNTHETIC_TOKEN},
                    location_id=SYNTHETIC_TENANT,
                )
                self.assertEqual(auth.source, f"env:{alias}")
                self.assertEqual(auth.kind, AuthKind.location_pit)
                self.assertEqual(auth.location_id, SYNTHETIC_TENANT)
                self.assertNotIn(SYNTHETIC_TOKEN, auth.source)

    def test_placeholder_values_are_skipped(self) -> None:
        auth = resolve_auth(
            kind=AuthKind.location_pit,
            env={"GHL_API_KEY": "your-token-here", "GHL_PIT": SYNTHETIC_TOKEN},
            location_id=SYNTHETIC_TENANT,
        )
        self.assertEqual(auth.source, "env:GHL_PIT")

    def test_a_placeholder_only_environment_is_refused(self) -> None:
        with self.assertRaises(CredentialMissing):
            resolve_auth(
                kind=AuthKind.location_pit,
                env={"GHL_API_KEY": "changeme"},
                location_id=SYNTHETIC_TENANT,
            )

    def test_location_pit_file_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pit.txt"
            path.write_text(SYNTHETIC_TOKEN + "\n", encoding="utf-8")
            auth = resolve_auth(
                kind=AuthKind.location_pit,
                env={LOCATION_PIT_FILE_ALIASES[0]: str(path)},
                location_id=SYNTHETIC_TENANT,
            )
        self.assertEqual(auth.source, f"file:{LOCATION_PIT_FILE_ALIASES[0]}")

    def test_engine_tenant_precedence_is_opt_in(self) -> None:
        env = {
            "GOHIGHLEVEL_API_KEY": "synthetic-default",
            "PODCAST_ENGINE_GHL_PIT": "synthetic-engine",
        }
        default = resolve_auth(
            kind=AuthKind.location_pit, env=env, location_id=SYNTHETIC_TENANT
        )
        engine = resolve_auth(
            kind=AuthKind.location_pit,
            env=env,
            location_id=SYNTHETIC_TENANT,
            prefer_engine_tenant=True,
        )
        self.assertEqual(default.source, "env:GOHIGHLEVEL_API_KEY")
        self.assertEqual(engine.source, "env:PODCAST_ENGINE_GHL_PIT")

    def test_agency_aliases_are_unmapped_and_never_substitute(self) -> None:
        self.assertEqual(
            AGENCY_PIT_ALIASES,
            (
                "GOHIGHLEVEL_AGENCY_PIT",
                "GOHIGHLEVEL_AGENCY_API_KEY",
                "GOHIGHLEVEL_CONVERTANDFLOW_AGENCY_PIT",
                "GHL_AGENCY_PIT",
            ),
        )
        with self.assertRaises(ContractViolation) as caught:
            resolve_auth(
                kind=AuthKind.agency_pit,
                env={"GOHIGHLEVEL_AGENCY_PIT": SYNTHETIC_TOKEN},
                location_id=None,
            )
        self.assertEqual(caught.exception.rule, "agency_auth_unmapped")
        self.assertEqual(
            caught.exception.detail["aliases"], list(AGENCY_PIT_ALIASES)
        )

        for alias in AGENCY_PIT_ALIASES:
            with self.subTest(alias=alias):
                with self.assertRaises(CredentialMissing):
                    resolve_auth(
                        kind=AuthKind.location_pit,
                        env={alias: SYNTHETIC_TOKEN},
                        location_id=SYNTHETIC_TENANT,
                    )
                with self.assertRaises(CredentialMissing):
                    resolve_auth(
                        kind=AuthKind.firebase_internal,
                        env={alias: SYNTHETIC_TOKEN},
                        location_id=None,
                    )

    def test_firebase_aliases_resolve_for_the_private_class(self) -> None:
        for alias in FIREBASE_ALIASES:
            with self.subTest(alias=alias):
                auth = resolve_auth(
                    kind=AuthKind.firebase_internal,
                    env={alias: SYNTHETIC_TOKEN},
                    location_id=None,
                )
                self.assertEqual(auth.source, f"env:{alias}")
                self.assertIsNone(auth.location_id)

    def test_firebase_refresh_token_file_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "refresh.txt"
            path.write_text(SYNTHETIC_TOKEN, encoding="utf-8")
            auth = resolve_auth(
                kind=AuthKind.firebase_internal,
                env={FIREBASE_FILE_ALIASES[0]: str(path)},
                location_id=None,
            )
        self.assertEqual(auth.source, f"file:{FIREBASE_FILE_ALIASES[0]}")

    def test_oauth_requires_an_explicit_secret_name(self) -> None:
        with self.assertRaises(ContractViolation):
            resolve_auth(kind=AuthKind.oauth, env={}, location_id=SYNTHETIC_TENANT)
        auth = resolve_auth(
            kind=AuthKind.oauth,
            env={"SYNTHETIC_OAUTH_NAME": SYNTHETIC_TOKEN},
            location_id=SYNTHETIC_TENANT,
            secret_name="SYNTHETIC_OAUTH_NAME",
        )
        self.assertEqual(auth.source, "oauth:SYNTHETIC_OAUTH_NAME")


class TenantAliasTest(unittest.TestCase):
    def test_location_id_alias_union_matches_the_freeze(self) -> None:
        frozen = (
            "GHL_LOCATION_ID",
            "GOHIGHLEVEL_LOCATION_ID",
            "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
            "CONVERT_AND_FLOW_LOCATION_ID",
            "convert_and_flow_location",
            "CAF_LOCATION_ID",
            "CAF_ALLOWED_LOCATION_IDS",
            "HIGHLEVEL_LOCATION_ID",
            "PODCAST_ENGINE_GHL_LOCATION_ID",
        )
        self.assertEqual(LOCATION_ID_ALIASES, frozen)

    def test_every_location_id_alias_resolves(self) -> None:
        for alias in LOCATION_ID_ALIASES:
            with self.subTest(alias=alias):
                tenant = resolve_tenant_from_env({alias: SYNTHETIC_TENANT})
                self.assertEqual(tenant.location_id, SYNTHETIC_TENANT)
                self.assertEqual(tenant.source, f"env:{alias}")

    def test_allowed_lists_take_the_first_id(self) -> None:
        for alias in ("GOHIGHLEVEL_ALLOWED_LOCATION_IDS", "CAF_ALLOWED_LOCATION_IDS"):
            with self.subTest(alias=alias):
                tenant = resolve_tenant_from_env(
                    {alias: SYNTHETIC_TENANT + ",loc_synthetic_0002"}
                )
                self.assertEqual(tenant.location_id, SYNTHETIC_TENANT)

    def test_lowercase_alias_matches_case_insensitively(self) -> None:
        tenant = resolve_tenant_from_env(
            {"CONVERT_AND_FLOW_LOCATION": SYNTHETIC_TENANT}
        )
        self.assertEqual(tenant.location_id, SYNTHETIC_TENANT)

    def test_location_id_file_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "location.txt"
            path.write_text(SYNTHETIC_TENANT, encoding="utf-8")
            tenant = resolve_tenant_from_env({LOCATION_ID_FILE_ALIASES[0]: str(path)})
        self.assertEqual(tenant.location_id, SYNTHETIC_TENANT)
        self.assertEqual(tenant.source, f"file:{LOCATION_ID_FILE_ALIASES[0]}")

    def test_ghl_loc_is_never_inferred(self) -> None:
        # INSTALL.md names GHL_LOC as an install-time shell variable, not an
        # env alias; mapping it would invent a resolution path.
        with self.assertRaises(ContractViolation) as caught:
            resolve_tenant_from_env({"GHL_LOC": SYNTHETIC_TENANT})
        self.assertEqual(caught.exception.rule, "tenant_not_inferred")
        self.assertNotIn("GHL_LOC", caught.exception.detail["tried"])

    def test_the_tenant_is_never_inferred_by_the_adapter(self) -> None:
        from _public_contract_fakes import FakeTransport, make_adapter, resp

        operations = {}
        transport = FakeTransport([resp(200)])
        adapter = make_adapter(transport, operations)
        with self.assertRaises(ContractViolation):
            adapter.call(operation_id="contacts.get", tenant=None)  # type: ignore[arg-type]
        self.assertEqual(transport.call_count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
