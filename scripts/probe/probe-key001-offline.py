#!/usr/bin/env python3
"""KEY-001 / A01 key-name half: OFFLINE proof of direct-key alias resolution.

Unit KEY-001 scope: direct-route KEY-NAME resolution only. Never a real key,
never a real outbound call, never a secrets file read. Both provider
transports are the stub named ``RecordingStubTransport`` (module-level
function pairs below), which records the endpoint chosen and counts calls;
the real ladder, real D04 post_decisions, real D05 send_decisions and real
D06 credential_resolver run around them.

Cases:
  (i)   both keys present (direct primary + OpenRouter)      -> direct chosen,
        OpenRouter transport calls == 0
  (i-b) both keys present, direct stored under the OPERATOR
        store name JEV_TYPESAFE_API_KEY (box as configured)  -> direct chosen,
        OpenRouter transport calls == 0
  (ii)  only a direct alias present (JEV_API_KEY, no
        TYPESAFE_API_KEY, no operator name)                  -> direct chosen
  (iii) neither direct alias present (only OpenRouter)       -> resolver
        honestly reports absent; direct transport calls == 0; OpenRouter
        transport registers exactly 1 (the honest fallback, and the control
        that proves the zero-call instrument discriminates).

All key values here are literals invented for this probe. No credential
material is read from any file or the environment.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# Repo root is derived from this file's own location
# (<root>/scripts/probe/probe-key001-offline.py) so the probe runs from a
# clean checkout, never from a lane-absolute path.
ROOT = Path(__file__).resolve().parent.parent.parent
DE = ROOT / "shared-utils" / "decision_engine"

sys.path.insert(0, str(ROOT / "shared-utils"))

_spec = importlib.util.spec_from_file_location(
    "key001_ladder", DE / "ladder" / "ladder.py")
ladder = importlib.util.module_from_spec(_spec)
sys.modules["key001_ladder"] = ladder
_spec.loader.exec_module(ladder)
TS, ORO, CR = ladder._load_providers()

# Literal fakes, invented here. Never a real credential, never from disk.
FAKE_DIRECT_PRIMARY = "probeDirectKeyAA1b2c3d4e5f6g7h8i9j0"
FAKE_DIRECT_ALIAS = "probeAliasKeyBB9x8y7z6w5v4u3t2s1r0"
FAKE_DIRECT_OPERATOR = "probeOperatorKeyCC4d5e6f7g8h9i0j1k2l3"
FAKE_OPENROUTER = "probeRouterKeyDD7q8w9e0r1t2y3u4i5o6"

# ── stubbed transports: the instrument ──────────────────────────────────
DIRECT_CALLS: list = []      # records url (endpoint chosen)
OR_CALLS: list = []          # records endpoint


def RecordingStubTransport_direct(url, body, headers, timeout_s):
    """Direct-leg stub transport: records the endpoint, no network."""
    DIRECT_CALLS.append({"endpoint": url})
    return 200, {"model": TS.TYPESAFE_MODEL, "judgments": []}


def RecordingStubTransport_openrouter(endpoint, headers, payload):
    """OpenRouter-leg stub transport: records the endpoint, no network."""
    OR_CALLS.append({"endpoint": endpoint})
    return 200, {"model": ORO.REQUESTED_MODEL, "judgments": []}


def _allow(provider, purpose="decide"):
    return {"spend_ok": True, "transmit_ok": True, "reason": "offline-probe"}


def _run(values: dict) -> dict:
    DIRECT_CALLS.clear()
    OR_CALLS.clear()
    store = {"source_category": "probe_store",
             "company_id": "KEY001Probe",
             "values": dict(values)}
    creds = CR.resolve_company_credentials("KEY001Probe", [store], {})
    order: list = []
    lad = ladder.DirectFirstLadder(
        policy_fn=_allow,
        direct_call=ladder._default_direct_call,        # real D04, stub http
        openrouter_call=ladder._default_openrouter_call,  # real D05, stub tr
    )
    verdict = lad.run(
        company_id="KEY001Probe", stores=[store], context={},
        state={}, questions=[{"id": "q_key001", "type": "noul"}],
        keys=dict(values), order_log=order,
        direct_http=RecordingStubTransport_direct,
        openrouter_transport=RecordingStubTransport_openrouter)
    return {
        "resolver": {
            r: {"state": s.state, "key_name": s.key_name,
                "configured": s.configured}
            for r, s in creds.items()},
        "decision_source": verdict.get("decision_source"),
        "ok": verdict.get("ok"),
        "stage_outcomes": [
            {"stage": s.get("stage"), "outcome": s.get("outcome"),
             "skip_reason": s.get("skip_reason")}
            for s in verdict.get("stages", [])],
        "order_log": order,
        "direct_transport_calls": len(DIRECT_CALLS),
        "direct_endpoints": [c["endpoint"] for c in DIRECT_CALLS],
        "openrouter_transport_calls": len(OR_CALLS),
        "openrouter_endpoints": [c["endpoint"] for c in OR_CALLS],
    }


CASES = {
    "i_both_present_primary": {
        "TYPESAFE_API_KEY": FAKE_DIRECT_PRIMARY,
        "OPENROUTER_API_KEY": FAKE_OPENROUTER},
    "i_b_both_present_operator_store_name": {
        "JEV_TYPESAFE_API_KEY": FAKE_DIRECT_OPERATOR,
        "OPENROUTER_API_KEY": FAKE_OPENROUTER},
    "ii_alias_only_jev_api_key": {
        "JEV_API_KEY": FAKE_DIRECT_ALIAS,
        "OPENROUTER_API_KEY": FAKE_OPENROUTER},
    "iii_neither_direct_alias_present": {
        "OPENROUTER_API_KEY": FAKE_OPENROUTER},
}

results = {name: _run(values) for name, values in CASES.items()}

checks = {
    "i_direct_chosen_or_zero": (
        results["i_both_present_primary"]["decision_source"]
        == "typesafe_direct"
        and results["i_both_present_primary"]["openrouter_transport_calls"]
        == 0
        and results["i_both_present_primary"]["direct_transport_calls"] == 1),
    "i_b_operator_name_direct_chosen_or_zero": (
        results["i_b_both_present_operator_store_name"]["decision_source"]
        == "typesafe_direct"
        and results["i_b_both_present_operator_store_name"][
            "openrouter_transport_calls"] == 0),
    "ii_alias_only_direct_chosen": (
        results["ii_alias_only_jev_api_key"]["decision_source"]
        == "typesafe_direct"
        and results["ii_alias_only_jev_api_key"][
            "openrouter_transport_calls"] == 0),
    "iii_absent_honest_no_fallthrough": (
        results["iii_neither_direct_alias_present"]["resolver"]["direct"][
            "state"] == "absent"
        and results["iii_neither_direct_alias_present"][
            "direct_transport_calls"] == 0
        and "skip:typesafe_direct:no_credential"
        in results["iii_neither_direct_alias_present"]["order_log"]
        and results["iii_neither_direct_alias_present"][
            "openrouter_transport_calls"] == 1),
}

# Alias list as implemented: measure file:line of every direct-name lookup.
import re
LOOKUPS = []
for path, names in (
    (DE / "providers" / "typesafe_direct.py",
     ("DIRECT_KEY_PRIMARY", "DIRECT_KEY_ALIAS", "DIRECT_KEY_OPERATOR",
      "DIRECT_KEY_NAMES", "for name in DIRECT_KEY_NAMES")),
    (DE / "providers" / "credential_resolver.py",
     ("DIRECT_KEYS: Tuple", "for key in ROUTE_KEYS[route]")),
):
    src_lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(src_lines, 1):
        if any(n in line for n in names):
            LOOKUPS.append({
                "file": str(path),
                "line": i,
                "text": line.strip()[:100],
            })

out = {
    "unit": "KEY-001",
    "criterion": "A01: Both keys present: direct JEV is used; OpenRouter "
                 "receives zero selection calls for that successful stage "
                 "(key-name half).",
    "instrument": "RecordingStubTransport (direct + openrouter) - records "
                  "endpoint chosen, counts calls; no network",
    "fake_values_only": True,
    "real_keys_used": 0,
    "real_network_calls": 0,
    "secrets_files_read": 0,
    "alias_list_as_implemented": LOOKUPS,
    "direct_key_names_order": list(TS.DIRECT_KEY_NAMES),
    "direct_keys_resolver_order": list(CR.DIRECT_KEYS),
    "cases": results,
    "checks": checks,
    "all_pass": all(checks.values()),
}

(ROOT / "scripts" / "probe" / "probe-key001-offline-out.json").write_text(
    json.dumps(out, indent=2) + "\n")
print(json.dumps({"checks": checks, "all_pass": all(checks.values()),
                  "direct_key_names": list(TS.DIRECT_KEY_NAMES),
                  "resolver_direct_keys": list(CR.DIRECT_KEYS)}, indent=2))
sys.exit(0 if all(checks.values()) else 1)
