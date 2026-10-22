#!/usr/bin/env python3
"""Integration: resolve the capability manifest from live captured fixtures and
bind the REAL host-dispatch receipt (evidence/host-dispatch-*.json).

Writes evidence/manifest-reconciliation.json — the acceptance artifact for
"the manifest reconciles catalog, allowlist, provider entries and cache
versions with actual host dispatch proving the chosen model".
"""
import json
import os
import re
import sys

UNIT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, UNIT_ROOT)

from capability_control.manifest import (  # noqa: E402
    DispatchReceipt, effort_claims_findings, resolve_manifest,
)

BUILDER = "openrouter/xiaomi/mimo-v2.6-pro"
QC = "openrouter/z-ai/glm-5.3"


def load(name):
    with open(os.path.join(UNIT_ROOT, "fixtures", name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def main():
    auth_raw = load("provider-catalog.openrouter.json")["models"]
    host_raw = load("host-catalog.9router.json")["models"]
    router = load("router-surfaces.db.json")
    cache_meta = load("session-cache.model-catalog.json")["cache_meta"]

    authoritative = {"openrouter/" + row["id"]: row for row in auth_raw.values()}
    host = {row["id"]: row for row in host_raw}

    surfaces = {
        "selectable": [BUILDER, QC],
        "allowlist": {
            "enabled": [BUILDER, QC],
            "disabled": router["kv"]["disabledModels"],
            "aliases": {"mimo-pro": BUILDER},
        },
        "provider_entries": [
            {"entry_id": "providerThinking:openrouter", "provider": "openrouter", "thinking_mode": "high"},
        ],
        "role_bindings": [
            {"role": "builder", "model_id": BUILDER, "requested_effort": "none"},
            {"role": "qc", "model_id": QC, "requested_effort": "high"},
        ],
        "scheduler_jobs": [{"job_id": "keepalive-15min", "schedule": "*/15 * * * *", "model_id": BUILDER}],
        "caches": [{
            "cache_id": "model-catalog.json",
            "source_revision": str(cache_meta.get("etag")),
            "fetched_at": str(cache_meta.get("syncedAt")),
            "refresh_path": "python3 -I tools/capture_fixtures.py --out fixtures/",
            "version": cache_meta.get("v"),
        }],
        "authoritative_revision": "openrouter-live-2026-10-22",
    }

    manifest = resolve_manifest("s75-w04-u2/capability-config/v1", authoritative, host, surfaces)

    # fabricated effort claims from the live router combos ("model(max)" annotations)
    claimed = {}
    for combo in router["combos"]:
        for entry in combo["models"]:
            match = re.match(r"^(.+)\((\w+)\)$", entry.strip())
            if match:
                claimed.setdefault(match.group(1), match.group(2))
    manifest.findings.extend(effort_claims_findings(manifest, claimed))

    # bind the REAL host-dispatch receipt for the builder role
    probe_path = os.path.join(UNIT_ROOT, "evidence", "host-dispatch-openrouter_xiaomi_mimo-v2.6-pro.json")
    with open(probe_path, "r", encoding="utf-8") as fh:
        probe = json.load(fh)
    result = manifest.verify_dispatch(DispatchReceipt(
        role="builder",
        requested_model=probe["requested_model"],
        resolved_model=probe["requested_model"],
        response_model=probe.get("response_model"),
        router_request_id=probe.get("router_receipt_id"),
        timestamp=probe.get("received_at"),
    ))

    out = {
        "unit": "S75-W04-U2",
        "built_from": {
            "authoritative_catalog": "fixtures/provider-catalog.openrouter.json",
            "host_catalog": "fixtures/host-catalog.9router.json",
            "router_surfaces": "fixtures/router-surfaces.db.json",
            "session_cache": "fixtures/session-cache.model-catalog.json",
            "runtime_schema": "fixtures/runtime-schema.snapshot.json",
        },
        "host_dispatch_proof": {
            "receipt_file": os.path.relpath(probe_path, UNIT_ROOT),
            "requested_model": probe["requested_model"],
            "response_model": probe.get("response_model"),
            "gateway_request_id": probe.get("router_receipt_id"),
            "thinking_block_seen": probe.get("thinking_block_seen"),
            "effort_parameter_sent": False,
            "verdict": result.as_dict(),
        },
        "unverified_roles_after_proof": manifest.unverified_roles(),
        "manifest": manifest.as_dict(),
        "note": "qc role left unverified: no qc dispatch probe was made in this unit; "
                "W00-U1 route-receipts.json carries the GLM high-effort end-to-end proof.",
    }
    out_path = os.path.join(UNIT_ROOT, "evidence", "manifest-reconciliation.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print("manifest findings:", [f.code for f in manifest.findings])
    print("builder dispatch:", result.code, "| unverified roles:", manifest.unverified_roles())
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
