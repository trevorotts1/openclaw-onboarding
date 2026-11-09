"""WF05 / A25: typed agency create-location + product-price one-conversion proofs.

Offline only: fake transport, synthetic tenants, no credentials, no network and
no live sub-account.  Run from the engine root:

    PYTHONPATH="$PWD" python3 -m pytest -q tests/test_agency_locations.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import click

from cli_anything.gohighlevel.public import agency
from cli_anything.gohighlevel.public import auth as public_auth
from cli_anything.gohighlevel.public.agency_commands import register
from cli_anything.gohighlevel.public.capability import Capability
from cli_anything.gohighlevel.public.errors import ContractViolation, CredentialMissing
from cli_anything.gohighlevel.public.transport import TransportResponse

AGENCY = "aglAgency0001"
OTHER_AGENCY = "aglAgency0002"
TOKEN_VALUE = "agency-secret-value"
KEY = "gxo_locations-create-" + "a" * 32


class FakeTransport:
    """Scripted responses; records every call.  No network in any test."""

    def __init__(self, script=()):
        self.script = list(script)
        self.calls = []

    def request(self, *, method, url, version, headers, query, body, timeout_s):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "version": version,
                "headers": dict(headers),
                "query": query,
                "body": body,
                "timeout_s": timeout_s,
            }
        )
        action = self.script.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def resp(status=200, payload=None, error_kind="none"):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return TransportResponse(status, {"content-type": "application/json"}, body, error_kind, 0.01)


def agency_auth():
    return agency.AgencyAuthContext(
        kind=public_auth.AuthKind.agency_pit,
        resolve_secret=lambda _name: TOKEN_VALUE,
        source="env:GHL_AGENCY_PIT",
    )


def capability(tenant=AGENCY, enabled=True, canary=True):
    return Capability(
        operation_id=agency.OPERATION_ID,
        contract_verified=True,
        adapter_built=True,
        offline_tests_passed=True,
        read_verified=True,
        canary_verified=canary,
        enabled=enabled,
        tenant=tenant,
    )


def spec(name="Launch Sub-Account", company=AGENCY):
    return agency.AgencyLocationSpec(name=name, agency_company_id=company)


def approved(spec_obj, action=agency.APPROVAL_ACTION, expiry=4102444800):
    return {
        "kind": agency.APPROVAL_KIND,
        "action": action,
        "object_key": agency.approval_object_key(spec_obj),
        "plan_sha256": "ab" * 32,
        "approver": "client",
        "expiry": expiry,
    }


def adapter(transport, *, company=AGENCY, plan_pro=True, cap=None):
    facts = agency.PlanFacts(
        {company: agency.PlanFact(company, plan_pro, "owner_supplied")}
    )
    return agency.AgencyAdapter(
        auth=agency_auth(),
        transport=transport,
        capability=capability() if cap is None else cap,
        plan_facts=facts,
    )


ACCEPT = lambda _record: True  # noqa: E731


def test_agency_token_resolver_is_separate_from_the_location_resolver():
    with pytest.raises(CredentialMissing) as exc:
        agency.resolve_agency_auth(env={"GHL_API_KEY": "location-pit"})
    assert public_auth.LOCATION_PIT_ALIASES[0] not in exc.value.detail["tried"]
    assert set(exc.value.detail["tried"]) == set(public_auth.AGENCY_PIT_ALIASES)

    resolved = agency.resolve_agency_auth(env={"GHL_AGENCY_PIT": TOKEN_VALUE})
    assert resolved.kind is public_auth.AuthKind.agency_pit
    assert agency.agency_headers(resolved) == {"Authorization": "Bearer " + TOKEN_VALUE}

    # The frozen location resolver still refuses agency auth (never substituted).
    with pytest.raises(ContractViolation) as refused:
        public_auth.resolve_auth(
            kind=public_auth.AuthKind.agency_pit,
            env={"GHL_AGENCY_PIT": TOKEN_VALUE},
            location_id=None,
        )
    assert refused.value.rule == "agency_auth_unmapped"

    # A location credential object can never drive the agency adapter.
    location_auth = public_auth.AuthContext(
        kind=public_auth.AuthKind.location_pit,
        location_id="loc_1",
        resolve_secret=lambda _n: "location-pit",
        source="env:GHL_API_KEY",
    )
    with pytest.raises(ContractViolation) as mixed:
        agency.AgencyAdapter(auth=location_auth, transport=FakeTransport())
    assert mixed.value.rule == "agency_write_requires_agency_token"


def test_typed_operation_uses_agency_token_version_and_company_id():
    created = {"location": {"id": "loc_new", "name": spec().name}}
    transport = FakeTransport([resp(201, created), resp(200, created)])
    result = adapter(transport).create_location(
        spec(), approval=approved(spec()), approval_verifier=ACCEPT, idempotency_key=KEY
    )
    assert result.status.value == "ok"
    assert result.readback is not None and result.readback.result.value == "verified"
    create = transport.calls[0]
    assert (create["method"], create["url"], create["version"]) == (
        "POST",
        "/locations",
        "2021-07-28",
    )
    assert create["headers"] == {"Authorization": "Bearer " + TOKEN_VALUE}
    assert create["body"] == {"name": spec().name, "companyId": AGENCY}
    assert "locationId" not in create["body"] and create["query"] is None
    assert transport.calls[1]["url"] == "/locations/loc_new"
    assert agency.OPERATION_SCOPES == ("locations.write",)


def test_company_id_rejects_relation_number_and_command_center_uuid():
    for bad in ("12345", "550e8400-e29b-41d4-a716-446655440000", "", "your-company"):
        with pytest.raises(ContractViolation):
            agency.guard_agency_company_id(bad)
    assert agency.guard_agency_company_id(AGENCY) == AGENCY


def test_plan_eligibility_is_per_tenant_and_never_a_global_default():
    # Owner-supplied Agency Pro for AGENCY is eligible for AGENCY only.
    ok_transport = FakeTransport([resp(201, {"location": {"id": "loc_a", "name": spec().name}}),
                                  resp(200, {"location": {"id": "loc_a", "name": spec().name}})])
    assert adapter(ok_transport).create_location(
        spec(), approval=approved(spec()), approval_verifier=ACCEPT, idempotency_key=KEY
    ).status.value == "ok"

    other = spec(company=OTHER_AGENCY)
    refused_transport = FakeTransport()
    result = adapter(refused_transport).create_location(
        other,
        approval=approved(other),
        approval_verifier=ACCEPT,
        idempotency_key=KEY,
    )
    assert result.status.value == "denied"
    assert result.error["rule"] == "agency_plan_not_eligible_for_tenant"
    assert refused_transport.calls == []

    unknown_transport = FakeTransport()
    unknown = agency.AgencyAdapter(
        auth=agency_auth(),
        transport=unknown_transport,
        capability=capability(tenant=AGENCY),
        plan_facts=agency.PlanFacts(),  # no fact recorded: unknown, not eligible
    )
    result = unknown.create_location(
        spec(company=AGENCY), approval=approved(spec()), approval_verifier=ACCEPT,
        idempotency_key=KEY,
    )
    assert result.status.value == "denied"
    assert result.evidence["plan_fact"] == {
        "agency_pro": None,
        "source": "unknown",
        "eligible": False,
    }
    assert unknown_transport.calls == []


def test_capability_is_default_deny_and_tenant_bound():
    transport = FakeTransport()
    no_cap = agency.AgencyAdapter(auth=agency_auth(), transport=transport,
                                  capability=None, plan_facts=agency.PlanFacts(
                                      {AGENCY: agency.PlanFact(AGENCY, True, "owner_supplied")}))
    result = no_cap.create_location(spec(), approval=approved(spec()),
                                    approval_verifier=ACCEPT, idempotency_key=KEY)
    assert result.status.value == "denied" and result.error["rule"] == "capability_disabled"

    wrong_tenant = adapter(FakeTransport(), cap=capability(tenant=OTHER_AGENCY))
    result = wrong_tenant.create_location(spec(), approval=approved(spec()),
                                          approval_verifier=ACCEPT, idempotency_key=KEY)
    assert result.error["rule"] == "capability_tenant_mismatch"

    no_canary = adapter(FakeTransport(), cap=capability(canary=False))
    result = no_canary.create_location(spec(), approval=approved(spec()),
                                       approval_verifier=ACCEPT, idempotency_key=KEY)
    assert result.error["rule"] == "capability_disabled"
    assert transport.calls == []


@pytest.mark.parametrize(
    "mutation,rule",
    [
        (lambda record: record.clear(), "approval_required"),
        (lambda record: record.update(expiry=1), "approval_expired"),
        (lambda record: record.update(action="products.create"), "approval_mismatch"),
        (lambda record: record.update(object_key="agency:elsewhere:x"), "approval_mismatch"),
        (lambda record: record.update(approver=""), "approval_required"),
    ],
)
def test_approval_must_be_verified_bound_and_unexpired(mutation, rule):
    transport = FakeTransport()
    record = approved(spec())
    mutation(record)
    with pytest.raises(ContractViolation) as refused:
        adapter(transport).create_location(
            spec(), approval=record, approval_verifier=ACCEPT, idempotency_key=KEY
        )
    assert refused.value.rule == rule
    assert transport.calls == []

    with pytest.raises(ContractViolation) as unverified:
        adapter(FakeTransport()).create_location(
            spec(), approval=approved(spec()), approval_verifier=lambda _r: False,
            idempotency_key=KEY,
        )
    assert unverified.value.rule == "approval_unverified"


def test_dry_run_compiles_without_any_network_call():
    transport = FakeTransport()
    result = adapter(transport).create_location(
        spec(), approval=approved(spec()), approval_verifier=ACCEPT,
        idempotency_key=KEY, dry_run=True,
    )
    assert result.status.value == "ok"
    assert result.evidence["dry_run"] is True
    assert result.evidence["mutation_performed"] is False
    assert result.evidence["compiled_body_keys"] == ["companyId", "name"]
    assert transport.calls == []


def test_readback_mismatch_is_unknown_outcome_and_reconciles():
    good = {"location": {"id": "loc_new", "name": spec().name}}
    drift = {"location": {"id": "loc_new", "name": "somebody else"}}
    transport = FakeTransport([resp(201, good), resp(200, drift), resp(200, good)])
    instance = adapter(transport)
    result = instance.create_location(
        spec(), approval=approved(spec()), approval_verifier=ACCEPT, idempotency_key=KEY
    )
    assert result.status.value == "unknown_outcome"
    assert result.error["rule"] == "readback_mismatch"
    assert result.evidence["mutation_performed"] is True

    reconciled = instance.reconcile(result)
    assert reconciled.status.value == "ok"
    assert reconciled.readback.result.value == "verified"
    assert [c["method"] for c in transport.calls] == ["POST", "GET", "GET"]


def test_create_without_native_id_is_uncertain_and_never_guessed():
    transport = FakeTransport([resp(200, {"location": {}})])
    instance = adapter(transport)
    result = instance.create_location(
        spec(), approval=approved(spec()), approval_verifier=ACCEPT, idempotency_key=KEY
    )
    assert result.status.value == "unknown_outcome"
    assert result.error["rule"] == "create_response_missing_id"
    assert len(transport.calls) == 1
    with pytest.raises(ContractViolation) as refused:
        instance.reconcile(result)
    assert refused.value.rule == "reconcile_requires_native_location_id"
    assert len(transport.calls) == 1


def test_idempotency_key_reuse_with_a_different_intent_is_refused():
    good = {"location": {"id": "loc_new", "name": spec().name}}
    transport = FakeTransport([resp(201, good), resp(200, good)])
    instance = adapter(transport)
    first = instance.create_location(
        spec(), approval=approved(spec()), approval_verifier=ACCEPT, idempotency_key=KEY
    )
    assert first.status.value == "ok"
    second = instance.create_location(
        spec(name="Different Name"), approval=approved(spec(name="Different Name")),
        approval_verifier=ACCEPT, idempotency_key=KEY,
    )
    assert second.status.value == "conflict"
    assert second.error["rule"] == "idempotency_key_reuse"
    assert len(transport.calls) == 2  # one POST + one readback; no second write


def _shared_products_prices():
    root = Path(__file__).resolve().parents[4]
    path = root / "shared-utils" / "ghl" / "products_prices.py"
    spec_obj = importlib.util.spec_from_file_location("_wf05_products_prices", path)
    module = importlib.util.module_from_spec(spec_obj)
    import sys

    sys.modules["_wf05_products_prices"] = module
    spec_obj.loader.exec_module(module)
    return module


def test_a25_products_prices_conversion_is_applied_exactly_once():
    pp = _shared_products_prices()
    body = pp.price_request_body(
        pp.PriceSpec("Workshop Seat", "loc_1", "one_time", "USD", 4900)
    )
    assert body["amount"] == 49.0 and body["currency"] == "USD"
    assert pp.api_amount_to_minor(body["amount"], 2) == 4900
    with pytest.raises(pp.SpecError):
        pp.PriceSpec("Seat", "loc_1", "one_time", "USD", 49.0)


def test_command_module_registers_refuses_then_runs_through_injection():
    def verify(approval_id, plan_sha256, action):
        assert (approval_id, plan_sha256, action) == ("apr_1", "ab" * 32, agency.APPROVAL_ACTION)
        return {"ok": True, "expires_at": "2099-01-01T00:00:00Z", "client_identity": "client"}

    transport = FakeTransport(
        [resp(201, {"location": {"id": "loc_cmd", "name": "Cmd Sub"}}),
         resp(200, {"location": {"id": "loc_cmd", "name": "Cmd Sub"}})]
    )
    root = click.Group()
    register(
        root,
        verify_approval=verify,
        capability_loader=lambda _company: capability(),
        transport_factory=lambda: transport,
    )
    runner = CliRunner()

    refused = runner.invoke(
        root,
        ["agency", "create-location", "--name", "Cmd Sub", "--agency-company-id", AGENCY, "--agency-pro"],
        env={"GOHIGHLEVEL_AGENCY_PIT": TOKEN_VALUE},
    )
    assert refused.exit_code == 1
    assert "REFUSED before any network call" in refused.output
    assert "PRIVATE FALLBACK (labelled" in refused.output
    assert transport.calls == []

    ok = runner.invoke(
        root,
        ["agency", "create-location", "--name", "Cmd Sub", "--agency-company-id", AGENCY,
         "--agency-pro", "--approval-id", "apr_1", "--plan-sha256", "ab" * 32],
        env={"GOHIGHLEVEL_AGENCY_PIT": TOKEN_VALUE},
    )
    assert ok.exit_code == 0, ok.output
    summary = json.loads(ok.output)
    assert summary["status"] == "ok" and summary["rail"] == "public_agency"
    assert transport.calls[0]["body"] == {"name": "Cmd Sub", "companyId": AGENCY}
    assert "agency-secret-value" not in ok.output


def test_command_without_agency_token_falls_back_labelled():
    root = click.Group()
    register(
        root,
        verify_approval=lambda *_a: {"ok": True, "expires_at": "2099-01-01T00:00:00Z",
                                     "client_identity": "client"},
        capability_loader=lambda _c: capability(),
        transport_factory=FakeTransport,
    )
    result = CliRunner().invoke(
        root,
        ["agency", "create-location", "--name", "Cmd Sub", "--agency-company-id", AGENCY,
         "--agency-pro", "--approval-id", "apr_1", "--plan-sha256", "ab" * 32],
        env={"GHL_API_KEY": "location-pit-only"},
    )
    assert result.exit_code == 1
    assert "agency_token_missing" in result.output
    assert "PRIVATE FALLBACK (labelled" in result.output


def test_route_decision_prefers_public_and_labels_private_fallback():
    public = agency.route_decision(
        spec=spec(),
        agency_credential_present=True,
        plan_fact=agency.PlanFact(AGENCY, True, "owner_supplied"),
        approval=approved(spec()),
        capability=capability(),
    )
    assert public.public is True and public.rail == agency.PUBLIC_RAIL
    assert public.request == {"name": spec().name, "companyId": AGENCY}

    fallback = agency.route_decision(
        spec=spec(),
        agency_credential_present=False,
        plan_fact=agency.PlanFact(AGENCY, True, "owner_supplied"),
        approval=approved(spec()),
        capability=capability(),
    )
    assert fallback.rail == agency.PRIVATE_FALLBACK_RAIL
    assert fallback.reason == "agency_token_missing"
    assert fallback.request is None
