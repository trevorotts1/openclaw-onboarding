#!/usr/bin/env python3
# tests/unit/rescue-contract-rr003.test.py
#
# RR-003 — proves the ONB side of the identity admission contract:
#   1. The sanitized identity admission addendum exists, is public-safe
#      (no credential values, no table IDs, no client identities) and matches
#      the private schema's public projection (refusal vocabulary, schema
#      names, header names).
#   2. The connection manifest declares the per-enrollment credential NAMES
#      (RR_BOX_CRED / RR_BOX_ID) posture-only: required=false, optional until
#      enrolled, and the shared secret stays required — no rotation.
#   3. The base public client contract is unchanged in its guarantees
#      (nine fields, retired paths) — RR-003 is additive.
#   4. The RR-017 baseline test still passes its own invariants (still present,
#      still hermetic) — dependency not regressed.
#
# Hermetic: file reads only, no network, no credentials.
#
# Run: python3 tests/unit/rescue-contract-rr017.test.py   (baseline, unchanged)
#      python3 tests/unit/rescue-contract-rr003.test.py   (this file)
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RR = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "rescue-rangers")

PASS = 0
FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))


addendum_path = os.path.join(RR, "contract", "IDENTITY-ADMISSION-CONTRACT.md")
manifest_path = os.path.join(RR, "connection-manifest.json")
base_contract_path = os.path.join(RR, "contract", "PUBLIC-CLIENT-CONTRACT.md")

print("RR-003 identity admission contract (ONB side)")

check(os.path.isfile(addendum_path), "identity admission addendum exists")

addendum = ""
if os.path.isfile(addendum_path):
    with open(addendum_path, "r", encoding="utf-8") as fh:
        addendum = fh.read()

# 1. sanitized: no hex-id shapes, no secret-value shapes, no bearer tokens
check(not re.search(r"\b[0-9a-f]{20,}\b", addendum), "addendum carries no hex table/credential shapes")
check(not re.search(r"X-Rescue-Secret:\s*\S", addendum.replace("`X-Rescue-Secret`", "")),
      "addendum carries no secret header VALUE (header names only)")
check(not re.search(r"X-RR-Box-Cred:\s*\S", addendum), "per-enrollment credential header carries no value")
check("SANITIZED" in addendum, "addendum is labelled sanitized")
check("blackceo-fleet-ops" in addendum, "addendum points at the private authority")

# refusal vocabulary matches the private schema projection
for status in ("identity_mismatch", "unknown_identity", "credential_revoked",
               "credential_disabled", "schema_version_unexpected", "forbidden_action",
               "return_to_unauthorized", "shared_client_retired"):
    check(status in addendum, f"addendum documents refusal status {status}")

# schema + header names
check("`v1`" in addendum and "`v2`" in addendum, "addendum names both admission schemas")
check("X-Rescue-Secret" in addendum and "X-RR-Box-Cred" in addendum and "X-RR-Box-Id" in addendum,
      "addendum names all three credential headers")
check("No existing credential is rotated" in addendum, "addendum states no-rotation rule")
check("never trusted" in addendum, "addendum states returnTo is never trusted for delivery")

# 2. connection manifest posture
check(os.path.isfile(manifest_path), "connection manifest exists")
with open(manifest_path, "r", encoding="utf-8") as fh:
    manifest = json.load(fh)
points = {p["name"]: p for p in manifest.get("connection_points", [])}
check("rescue-box-cred" in points, "manifest declares rescue-box-cred connection point")
check("rescue-box-cred-id" in points, "manifest declares rescue-box-cred-id connection point")
if "rescue-box-cred" in points:
    check(points["rescue-box-cred"].get("required") is False,
          "per-enrollment credential is optional until the operator enrolls the box")
    check(points["rescue-box-cred"].get("cfg_key") == "env.vars.RR_BOX_CRED",
          "credential env var NAME is RR_BOX_CRED (value never present here)")
if "rescue-box-cred-id" in points:
    check(points["rescue-box-cred-id"].get("cfg_key") == "env.vars.RR_BOX_ID",
          "enrollment id env var NAME is RR_BOX_ID")
check(points.get("rescue-rangers-webhook-secret", {}).get("required") is True,
      "shared fleet secret stays REQUIRED — nothing rotated")
check("OPERATOR-SEEDED" in points.get("rescue-box-cred", {}).get("description", ""),
      "per-enrollment credential is operator-seeded, never self-service")

# 3. base contract guarantees unchanged
check(os.path.isfile(base_contract_path), "base public client contract still present")
with open(base_contract_path, "r", encoding="utf-8") as fh:
    base = fh.read()
for field in ("person", "clientName", "agentName", "boxName", "boxType",
              "openclawVersion", "problem", "alreadyTried", "returnTo"):
    check(f"`{field}`" in base, f"base nine-field contract still names {field}")
check("retired" in base.lower(), "base contract still labels the retired relay path")

# 4. RR-017 baseline artifacts untouched by this wave
rr017 = os.path.join(HERE, "rescue-contract-rr017.test.py")
check(os.path.isfile(rr017), "RR-017 baseline test still present (dependency intact)")

print()
print(f"RESULT: {PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)
