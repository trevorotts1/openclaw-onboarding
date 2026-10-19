"""Offline self-check for evidence/W11/gu022-403-scope-analysis.md.

Run from the repo root:
  python3 evidence/W11/check-gu022-scope-analysis.py

Asserts, without any network call and without printing a secret:
  1. the analysis and fact record exist and cite both documented scopes;
  2. the frozen registry has no locations.* row and marks contacts.list retired;
  3. the public adapter refuses the three probed operations before transport
     (default-deny capability gate);
  4. no credential value present in the operator's env stores appears in the
     evidence files.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE = os.path.join(ROOT, "44-convert-and-flow-operator", "tools", "engine", "cli_anything")
sys.path.insert(0, ENGINE)

from gohighlevel.public.adapter import PublicGhlAdapter  # noqa: E402
from gohighlevel.public.auth import AuthContext, AuthKind, TenantBinding  # noqa: E402
from gohighlevel.public.operations import OPERATIONS  # noqa: E402

EVIDENCE = os.path.join(ROOT, "evidence", "W11")
ANALYSIS = os.path.join(EVIDENCE, "gu022-403-scope-analysis.md")
FACTS = os.path.join(EVIDENCE, "ghl-111-scope-facts.json")
TENANT = "XCgFTEA1oDvsPnTqqgoB"

# GHL-150 (2026-10-19): real 200s were observed on this tenant for exactly
# these operations.  The checked-in record is bound to it, and the tenant this
# analysis probed stays unbound, which is still default-deny here.
VERIFIED_TENANT = "Mct54Bwi1KlNouGXQcDX"
VERIFIED_OPERATIONS = frozenset(
    {
        "locations.get",
        "contacts.list",
        "contacts.search",
        "custom_fields.list",
        "pipelines.list",
        "media.files.list",
    }
)


def check_registry() -> None:
    # GHL-140 registered the read the analysis said was missing. Registration is
    # not access: the row may exist while the tenant still refuses the token.
    loc = OPERATIONS["locations.get"]
    assert loc.method == "GET", loc.method
    assert loc.path_template == "/locations/{locationId}", loc.path_template
    assert loc.version == "2021-07-28", loc.version
    assert "locations.readonly" in loc.scopes_candidate, loc.scopes_candidate
    row = OPERATIONS["contacts.list"]
    assert row.route_class == "retired", row.route_class
    assert row.blocker == "B-DEPRECATED", row.blocker
    assert row.version == "2021-07-28", row.version
    assert OPERATIONS["contacts.search"].path_template == "/contacts/search"
    assert OPERATIONS["contacts.search"].version == "v3"


def check_documents() -> dict:
    with open(ANALYSIS, encoding="utf-8") as fh:
        text = fh.read()
    with open(FACTS, encoding="utf-8") as fh:
        facts = json.load(fh)
    for needle in (
        "locations.readonly",
        "contacts.readonly",
        "The token does not have access to this location.",
        "This location is not accessible from this token!",
        "GET /locations/{locationId}",
        "capability_disabled",
        "Mct54Bwi1KlNouGXQcDX",
    ):
        assert needle in text, f"analysis missing: {needle}"
    assert facts["credential_never_printed"] is True
    assert facts["conclusion"]["scope_failures"] == [
        "locations.readonly for GET /locations/{locationId}",
        "contacts.readonly for contact reads",
    ]
    assert len(facts["configured_location_ids"]) == 7
    return {"text": text, "facts_raw": json.dumps(facts)}


def check_gate() -> None:
    class ExplodingTransport:
        def request(self, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("transport reached: capability gate failed")

    auth = AuthContext(
        kind=AuthKind.location_pit,
        location_id=TENANT,
        resolve_secret=lambda name: "not-a-real-secret",
        source="env:TEST_ONLY",
    )
    adapter = PublicGhlAdapter(auth=auth, transport=ExplodingTransport())
    tenant = TenantBinding(location_id=TENANT, source="test")
    cases = [
        ("contacts.list", {"query": {"limit": 1}}),
        ("contacts.search", {"body": {"locationId": TENANT, "pageLimit": 1}}),
        ("custom_fields.list", {"path_params": {"locationId": TENANT}}),
    ]
    for op, kwargs in cases:
        result = adapter.call(operation_id=op, tenant=tenant, **kwargs)
        assert result.status.value == "denied", (op, result.status)
        assert result.http_status is None, (op, result.http_status)
        assert (result.error or {}).get("rule") == "capability_disabled", (op, result.error)


def check_capability_record() -> None:
    from gohighlevel.public.capability import load_capability_record

    gate = load_capability_record(tenant=VERIFIED_TENANT)
    assert len(gate) == len(VERIFIED_OPERATIONS), len(gate)
    for operation_id in sorted(VERIFIED_OPERATIONS):
        capability = gate.get(operation_id)
        assert capability.enabled, operation_id
        assert capability.read_verified, operation_id
        assert capability.activation == "VERIFIED", operation_id
        assert not capability.provisional, operation_id
    for operation_id in ("contacts.get", "media.upload", "pipelines.get"):
        assert not gate.get(operation_id).enabled, operation_id
    # The tenant this analysis probed is not the verified tenant, so the record
    # loads nothing for it: tenant mismatch still fails closed.
    assert len(load_capability_record(tenant=TENANT)) == 0


def check_no_secret_in_evidence(docs: dict) -> None:
    haystacks = [docs["text"], docs["facts_raw"]]
    homes = os.path.expanduser("~/.openclaw")
    paths = [
        os.path.join(homes, "secrets", ".env"),
        os.path.join(homes, ".env"),
        os.path.join(homes, "secrets", "secrets.env"),
        os.path.join(homes, "service-env", "ai.openclaw.gateway.env"),
    ]
    values: set[str] = set()
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip().removeprefix("export ").strip()
                    value = value.strip().strip('"').strip("'")
                    if len(value) >= 12 and (
                        "KEY" in key.upper()
                        or "TOKEN" in key.upper()
                        or "PIT" in key.upper()
                        or "SECRET" in key.upper()
                        or "PASSWORD" in key.upper()
                    ):
                        values.add(value)
        except OSError:
            continue
    leaks = [h for h in haystacks for v in values if v and v in h]
    assert not leaks, f"{len(leaks)} credential value(s) leaked into evidence"


if __name__ == "__main__":
    check_registry()
    docs = check_documents()
    check_gate()
    check_capability_record()
    check_no_secret_in_evidence(docs)
    print(
        "OK: registry, scopes, default-deny gate, capability record and "
        "no-secret checks passed"
    )
