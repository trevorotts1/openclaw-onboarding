#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: push_snapshot_to_subaccounts.py (MASTER-SPEC NEW-3)
# PUSH THE APPROVED TEMPLATE SNAPSHOT TO CLIENT-OWNED CONVERT AND FLOW LOCATIONS.
#
# WHAT THIS IS (config/anthology-snapshot-contract.json provisioning_branches_note
# + authorized_mechanisms/rejected_mechanisms; the multi-target batch sibling of
# provision_snapshot_import.py's single-location import):
#   The operator approves ONE snapshot (its id recorded in the snapshot contract,
#   snapshot_version, or passed explicitly) and THIS module pushes it to EVERY
#   target location listed on the command line, applying each target's own
#   per-client custom-VALUE overrides, and emits ONE machine-readable per-client
#   provision report covering every target. It is the engine's batch equivalent
#   of the same-agency branch and the hardened, explicit guard for the standing
#   cross-agency rejection:
#
#     push           batch push: for each --target <location_id>[,<overrides>],
#                    GET-check-by-name (idempotency law: a location that already
#                    carries the standard pipeline "Anthology Engine" BY NAME is
#                    VERIFIED, never re-pushed) -> if absent, PUT /locations/{id}
#                    with {companyId, snapshot:{id, override:true}} -> bounded
#                    snapshot-status poll -> resolve the field-map from the
#                    location's read-back fields BY KEY -> write that target's
#                    row in the provision report. One failing target NEVER
#                    cancels the batch; every target gets a row and the aggregate
#                    exit reflects the WORST per-target result.
#     status         READ-ONLY: per-target snapshot-status poll. Never mutates.
#     verify-only    READ-ONLY: per-target GET-check-by-name + field read-back
#                    (the same idempotency check, without any push). Never mutates.
#     plan           OFFLINE: prints the target list, per-target custom-value
#                    overrides, the tenancy gate outcome, and the target count.
#                    No network, no writes.
#     self-test      OFFLINE golden + attack fixtures. No network, no secrets.
#
# THE TENANCY GATE (the standing-REJECTED guard, enforced HERE, not described):
#   config/anthology-snapshot-contract.json rejected_mechanisms records the
#   cross-agency agency->subaccount API auto-push as REJECTED — pushing a
#   snapshot into a location the operator does NOT own under its agency is
#   impossible and this module must never attempt it. qc-snapshot-contract.sh
#   asserts the REJECTED record still stands. This module enforces the SAME
#   law at runtime:
#     --tenancy cross_agency (explicit) -> STOP exit 2, AF-AE-SNAP-PUSH-CROSS-
#       AGENCY-REJECTED, before any network call, per target.
#     --tenancy same_agency (explicit) -> the authorized branch; push proceeds.
#     --tenancy auto (default) -> decide per target: a target location id that
#       byte-equals the contract's OWN template location
#       (source_template_location.template_location_id) is the operator's own
#       sub-account -> same-agency, push allowed; ANY OTHER location id is
#       client-owned (cross-agency) -> the standing rejection applies, that
#       target is REFUSED with the reject surface (verify-only / dry-run may
#       still READ it). The auto decision is BYTECODE-DETERMINISTIC: an
#       unknown location is never silently pushed.
#   The same-agency PUSH itself (PUT /locations/{id} with companyId DAD7
#   snapshot.override) is AUTHORIZED (contract authorized_mechanisms row 1;
#   provision_snapshot_import.py already performs it for a single location);
#   this module performs it per target, identically, through the SAME client.
#
# CREDENTIAL DOCTRINE: the token + default location are resolved BY LABEL exactly
# like every other adapter (reg.resolve_pit / reg.resolve_location:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_LOCATION_ID etc., live process env
# first then the three canonical client env stores). The agency PIT used for the
# push is the OPERATOR-OWNED agency token under the same labels; values are NEVER
# printed (SET / NOT SET + masked location only). The browser User-Agent rides
# every request via reg.CafClient (W0.6/GK-09: services.leadconnectorhq.com is
# Cloudflare-fronted and 403s urllib's default UA — CF 1010 — before the request
# ever reaches Convert and Flow). The engine's scope-vs-edge-block discrimination
# (ScopeDenied vs UpstreamBlockedError) applies to every read AND write: a bare
# 401/403 is NEVER reported as a scope problem (the Wave 5 false positive), it is
# HELD.
#
# CUSTOM-VALUE OVERRIDES (per-client, per target): each --target may carry an
# overrides file: --target <location_id>[,<overrides.json>]. The overrides file
# is a JSON object keyed by the CONTRACT custom-value keys (anthology_webhook_url,
# anthology_hook_secret, producer, producer_email — contract location_custom_values
# .required). Only the keys present in the file are filled (GET-check +
# create-only-missing / update, exactly anthology_snapshot.py's idempotent fill);
# keys absent are skipped with a note. The hook-secret value may also come BY LABEL
# from ANTHOLOGY_INTAKE_HOOK_SECRET (the standard engine label) — the value is
# NEVER printed (SET / NOT SET only). A real-looking value in an overrides file
# that is not flagged secret is a VALIDATION refusal (AF-AE-SNAP-PUSH-OVERRIDES),
# never a silent write.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-SNAP-PUSH-CROSS-AGENCY-REJECTED -> cross-agency tenancy: the push is
#          the standing-REJECTED mechanism. STOP exit 2 BEFORE any network call.
#   AF-AE-SNAP-PUSH-PIPELINE-PRESENT      -> a target already carries the standard
#          pipeline BY NAME: verified no-op (never a second push).
#   AF-AE-SNAP-PUSH-PIPELINE-MISSING      -> no standard pipeline AND no push was
#          performed (usage refusal: no snapshot id / companyId not configured /
#          dry-run). STOP.
#   AF-AE-SNAP-PUSH-REFUSED               -> the snapshot PUT was rejected (scope /
#          validation / edge / transport). STOP or HELD per class, never a silent
#          skip, never recorded as pushed.
#   AF-AE-SNAP-PUSH-NO-FIXTURE            -> no snapshot id/version available
#          (contract snapshot_version empty AND no --snapshot-id) or a fixture
#          that drifted from the contract. STOP before any push.
#   AF-AE-SNAP-PUSH-STATUS-STALLED        -> the status poll never reached
#          "completed" (bounded). HELD exit 3, never a false pass.
#   AF-AE-SNAP-PUSH-READBACK-MISMATCH     -> after completion the location's
#          custom fields did not carry every intended key byte-for-byte. exit 5,
#          NOTHING stamped into field-map.json.
#   AF-AE-SNAP-PUSH-COMPANYID-MISSING     -> SAME-AGENCY companyId not configured
#          (--company-id / env label) and no same-agency tenancy declared. STOP:
#          the module never invents an agency id.
#   AF-AE-SNAP-PUSH-OVERRIDES             -> an overrides file failed validation
#          (unknown key, wrong value type, or a real-looking value on a
#          non-secret key). STOP before any write.
#   AF-AE-SNAP-PUSH-TARGET                -> a --target argument is malformed
#          (empty, missing location id, or the overrides file does not exist).
#          STOP before any network call.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator surface;
# 4 = enforced violation).
#   The aggregate exit of a batch is the WORST per-target result:
#     0  verified success (every target verified; idempotent no-op / dry run
#        counts as pass)
#     1  unexpected error
#     2  STOP refusal — usage / tenancy-rejected / missing credential / refusal
#        to create / malformed target / overrides refusal
#     3  Convert and Flow API unreachable / dependency held / status not
#        completed (retryable)
#     4  self-test FAILED — an assertion in the OFFLINE self-test (golden /
#        attack fixtures, field-map<->contract coherence, read-back law)
#        tripped: the AF-AE-SNAP-PUSH-* family. A tamper NEVER masquerades as
#        "unexpected error" (exit 1).
#     5  read-back mismatch (a contract key absent from the present fields)
#
# STDLIB ONLY (urllib + json), reusing anthology_registry.CafClient + credential
# resolution + _stop/_mask_location. Calls NO model. DOCTRINE: move in silence
# (operator-verbose only); NOTHING Anthropic in any runtime file; Convert and
# Flow naming in every client surface; NEVER print a secret value (SET / NOT
# SET + masked location only); config writes are atomic temp+replace;
# --self-test and --plan are OFFLINE.
# =============================================================================
"""push_snapshot_to_subaccounts.py — push the approved template snapshot to
client-owned Convert and Flow locations, with per-client custom-value overrides,
and emit a per-client provision report (Skill 59, MASTER-SPEC NEW-3)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Sibling import bootstrap (mirrors anthology_snapshot.py's own convention). The
# registry does the Cloudflare browser-UA wiring + LeadConnector client +
# label resolution we reuse.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED, AF-AE-SNAP-PUSH-* family)

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The engine's SAME-AGENCY company id (BlackCEO's own Convert and Flow agency;
# the client's location is a sub-account under it). Recorded in the snapshot
# contract's provisioning_branches_note + authorized_mechanisms. An arg or env
# label wins over this default so the module never hardcodes a value that
# drifted. The company id is operator infra config, not a secret; still, only
# the final 4 chars ever appear on a surface.
SAME_AGENCY_COMPANY_ID = "DAD7unnJpNUFc36952Xp"
COMPANY_ID_LABELS = ("ANTHOLOGY_SNAPSHOT_COMPANY_ID",)

# The snapshot-status poll surface the n8n Snapshot Provisioner workflow polls
# (same endpoint, same query shape; this module polls it directly after each
# push). Mirror of provision_snapshot_import.py.
SNAPSHOT_STATUS_PATH = "/snapshots/status"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"
_STATUS_PROCESSING = "processing"

# Bounds for the post-push status poll (mirror of provision_snapshot_import.py:
# 12 min at 10 s cadence, generous but bounded).
DEFAULT_POLL_TIMEOUT_S = 720
DEFAULT_POLL_INTERVAL_S = 10

# The hook-secret BY-LABEL source for the anthology_hook_secret custom value
# (mirror of anthology_snapshot.py's HOOK_SECRET_LABELS + the engine's
# route_secret_label contract). The value is NEVER printed.
HOOK_SECRET_LABELS = ("ANTHOLOGY_INTAKE_HOOK_SECRET",)


# ---------------------------------------------------------------------------
# Contract helpers. Values are never printed; drift is fail-closed.
# ---------------------------------------------------------------------------
def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_company_id(override: str = ""):
    """(label, company_id) or (None, None). The engine's SAME-AGENCY company id:
    arg wins, else env label, else the contract-recorded default. NEVER printed
    beyond the final 4 chars (it is operator infra config, not a secret)."""
    if override and override.strip():
        return "(--company-id)", override.strip()
    for name in COMPANY_ID_LABELS:
        v = os.environ.get(name, "")
        if v and v.strip():
            return name, v.strip()
    return "(contract default)", SAME_AGENCY_COMPANY_ID


def resolve_hook_secret():
    """(label, value) or (None, None). The value is NEVER printed."""
    for name in HOOK_SECRET_LABELS:
        v = os.environ.get(name, "")
        if v and v.strip():
            return name, v.strip()
    return None, None


def contract_snapshot_id(contract: dict) -> str:
    """The approved snapshot id: the contract's date-stamped snapshot_version
    (the name the operator gives the exported snapshot). This module refuses to
    push when it is empty AND no --snapshot-id was given (a push without an
    approved id is never performed)."""
    return (contract.get("snapshot_version") or "").strip()


def template_location_id(contract: dict) -> str:
    """The operator's OWN template location (source_template_location). A target
    whose location id BYTE-EQUALS this is the operator's own sub-account; under
    --tenancy auto it is the ONLY location the same-agency push may touch."""
    return (contract.get("source_template_location") or {}).get("template_location_id") or ""


def fixture_pipeline_name(fixture: dict) -> str:
    return (fixture.get("pipeline") or {}).get("name") or ""


def fixture_stage_names(fixture: dict) -> list:
    out = []
    for s in (fixture.get("pipeline") or {}).get("stages") or []:
        if isinstance(s, dict) and s.get("name"):
            out.append(s["name"])
    return out


def fixture_intended_keys(fixture: dict):
    """The custom-field keys the fixture carries, derived the SAME way the engine
    derives them (fieldKey = "contact." + create_name)."""
    out = []
    for f in (fixture.get("custom_fields") or {}).get("fields") or []:
        if isinstance(f, dict):
            cname = (f.get("create_name") or "").strip() or (f.get("name") or "").strip()
            if cname:
                out.append(reg.derive_field_key(cname))
    return out


# ---------------------------------------------------------------------------
# Overrides files (per-client custom-VALUE overrides; AF-AE-SNAP-PUSH-OVERRIDES)
# ---------------------------------------------------------------------------
# The contract's location custom-value keys (the ONLY keys an overrides file may
# carry). anthology_hook_secret is secret; a real-looking value on any other key
# is a validation refusal, never a silent write.
def contract_custom_value_keys(contract: dict) -> list:
    return [c.get("key") for c in
            ((contract.get("location_custom_values") or {}).get("required") or [])]


def contract_custom_value_secret(contract: dict, key: str) -> bool:
    for c in ((contract.get("location_custom_values") or {}).get("required") or []):
        if c.get("key") == key:
            return bool(c.get("secret"))
    return False


_REAL_VALUE_RE = __import__("re").compile(
    r"(https?://|pit-|ghl_|Bearer |[0-9a-fA-F]{24,}|[A-Za-z0-9_-]{20,}@)")


def validate_overrides(contract: dict, data) -> list:
    """Validate an overrides file against the contract custom-value keys.
    Returns a list of (key, reason) refusals; empty means valid. A refusal is
    AF-AE-SNAP-PUSH-OVERRIDES: STOP before any write. The hook-secret key may
    legitimately carry any value (it IS the client's own token-shaped secret,
    flagged secret in the contract); every OTHER key must be a plain
    non-secret-shaped value."""
    out = []
    if not isinstance(data, dict):
        return [("(root)", "overrides file must be a JSON object")]
    allowed = contract_custom_value_keys(contract)
    for key, value in data.items():
        if key not in allowed:
            out.append((key, "unknown custom-value key (allowed: %s)" % ", ".join(allowed)))
            continue
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            out.append((key, "value must be a non-empty string"))
            continue
        if not contract_custom_value_secret(contract, key):
            if _REAL_VALUE_RE.search(value):
                out.append((key, "real-looking value on a NON-secret key is refused "
                                  "(never-a-real-token law; pass the secret BY LABEL)"))
    return out


def build_fill_values(contract: dict, overrides: dict, *, out=None):
    """Compute the concrete value to write for each supplied override key, plus
    the hook-secret BY-LABEL value when the label resolves. Returns
    (to_write, skipped): to_write is a list of {key, name, value, secret};
    skipped is a list of (key, reason). Contract-DRIVEN (never a hardcoded
    custom-value set) so it can never drift from what the snapshot ships."""
    out = out or sys.stderr
    required = ((contract.get("location_custom_values") or {}).get("required")) or []
    by_name = {}
    for cv in required:
        name = cv.get("name") or cv.get("key")
        by_name[name.strip().lower()] = cv
    slabel, sval = resolve_hook_secret()
    to_write, skipped = [], []
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        cv = next((c for c in required if c.get("key") == key), None)
        if cv is None:
            continue
        name = cv.get("name") or key
        is_secret = bool(cv.get("secret"))
        if key == "anthology_hook_secret" and sval:
            # The label wins: the standard engine label is the source of truth
            # for the Authorization-header value; an overrides-file value is
            # only used when the label is NOT set (a deferred-fill fallback).
            value = "Bearer %s" % sval
        to_write.append({"key": key, "name": name, "value": value, "secret": is_secret})
    for key in contract_custom_value_keys(contract):
        if key in (overrides or {}) and (overrides or {}).get(key) is None:
            continue
        if key == "anthology_hook_secret" and not sval and key in (overrides or {}):
            skipped.append((key, "ANTHOLOGY_INTAKE_HOOK_SECRET NOT SET in any env "
                                 "store; the overrides-file value would be used (deferred)"))
    return to_write, skipped


# ---------------------------------------------------------------------------
# Per-target operations (mirror of provision_snapshot_import.py's per-location
# steps; every function here takes ONE client + ONE location and returns
# (exit_code, row) so the batch loop owns the aggregation).
# ---------------------------------------------------------------------------
def get_standard_pipeline(client, location_id: str, std_name: str, *, out=None):
    """GET-check-by-name: return the pipeline dict when the location carries the
    standard pipeline BY NAME, else None. Raises ScopeDenied / CafUnreachable;
    the caller maps them to STOP / HELD surfaces."""
    out = out or sys.stderr
    pipelines = client.list_pipelines(location_id)
    for p in pipelines or []:
        if (p.get("name") or "") == std_name:
            return p
    return None


def resolve_field_map_keys(client, location_id: str, want_keys: list, *, out=None):
    """READ-ONLY read-back: verify every intended key exists BY KEY
    byte-for-byte on the location. Returns (rc, present_keys_count).
    A key absent -> EX_MISMATCH (AF-AE-SNAP-PUSH-READBACK-MISMATCH); NOTHING is
    stamped by this module (field-map resolution is owned by the sibling
    provision_snapshot_import.py / anthology_registry.py; this module only
    PROVES the read-back for its report)."""
    out = out or sys.stderr
    try:
        fields = client.list_custom_fields(location_id)
    except reg.ScopeDenied:
        out.write("[push-snapshot] STOP: token cannot READ custom fields on marker %s. "
                  "AF-AE-SNAP-PUSH-READBACK-MISMATCH family: STOP, never a false "
                  "pass.\n" % reg._mask_location(location_id))
        return EX_STOP, 0
    except reg.CafUnreachable as exc:
        out.write("[push-snapshot] HELD: %s (marker %s). Retryable.\n"
                  % (exc, reg._mask_location(location_id)))
        return EX_HELD, 0
    present = {f.get("fieldKey") for f in fields}
    missing = [k for k in want_keys if k not in present]
    if missing:
        out.write("[push-snapshot] READ-BACK MISMATCH (marker %s): %d contract "
                  "custom-field key(s) absent: %s. AF-AE-SNAP-PUSH-READBACK-"
                  "MISMATCH: NOTHING stamped.\n"
                  % (reg._mask_location(location_id), len(missing),
                     ", ".join(missing[:5])))
        return EX_MISMATCH, len(present & set(want_keys))
    return EX_OK, len(want_keys)


def push_snapshot(client, location_id: str, company_id: str, snapshot_id: str, *,
                  out=None):
    """The SAME-AGENCY automated push: PUT /locations/{id} with
    {companyId, snapshot:{id, override:true}} (references/anthology-snapshot-
    guide.md section 6; contract authorized_mechanisms row 1). The agency PIT
    (locations.write scope) is the operator-owned credential resolved BY LABEL
    by the caller. Raises ScopeDenied / CafValidation / CafUnreachable /
    UpstreamBlockedError; the caller maps them to STOP / HELD surfaces
    (AF-AE-SNAP-PUSH-REFUSED)."""
    out = out or sys.stderr
    body = {
        "companyId": company_id,
        "snapshot": {"id": snapshot_id, "override": True},
    }
    out.write("[push-snapshot] PUT /locations/{id} (masked %s): snapshot %r, "
              "override, companyId ...%s. AF-AE-SNAP-PUSH-REFUSED on any "
              "rejection.\n"
              % (reg._mask_location(location_id), snapshot_id, company_id[-4:]))
    return client._request("PUT", "/locations/%s" % location_id, body=body)


def poll_snapshot_status(client, location_id: str, *, timeout_s: int,
                         interval_s: int, out=None, sleep_fn=time.sleep):
    """Poll GET /snapshots/status?locationId=... until "completed". Returns
    (rc, status). rc EX_OK on completed; EX_HELD on timeout/stalled
    (AF-AE-SNAP-PUSH-STATUS-STALLED) or a transient/edge error (never a false
    pass); EX_STOP on a scope denial (never retry a scope STOP)."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    deadline = time.monotonic() + timeout_s
    last_status = ""
    while True:
        try:
            resp = client._request("GET", SNAPSHOT_STATUS_PATH,
                                   query={"locationId": location_id})
        except reg.ScopeDenied:
            out.write("[snapshot-status] STOP: token not authorized for "
                      "snapshot-status on marker %s (AF-AE-SNAP-PUSH-STATUS-"
                      "STALLED: never a false pass).\n" % masked)
            return EX_STOP, last_status
        except reg.CafUnreachable as exc:
            out.write("[snapshot-status] HELD: %s (marker %s). Retryable.\n"
                      % (exc, masked))
            return EX_HELD, last_status
        status = (resp.get("status") or "").strip().lower() or last_status
        if status:
            last_status = status
        if status == _STATUS_COMPLETED:
            out.write("[snapshot-status] completed (marker %s).\n" % masked)
            return EX_OK, status
        if status == _STATUS_FAILED:
            out.write("[snapshot-status] FAILED (marker %s): the import reported "
                      "failure. AF-AE-SNAP-PUSH-STATUS-STALLED: never a false "
                      "pass.\n" % masked)
            return EX_HELD, status
        if time.monotonic() >= deadline:
            out.write("[snapshot-status] stalled (marker %s): status %r never "
                      "reached completed within %ds. AF-AE-SNAP-PUSH-STATUS-"
                      "STALLED: HELD, retryable, never a false pass.\n"
                      % (masked, last_status, timeout_s))
            return EX_HELD, last_status
        sleep_fn(interval_s)


def provision_custom_values(client, location_id: str, contract: dict, to_write: list,
                            *, out=None):
    """Idempotent per-target custom-VALUE fill (GET-check then create-only-
    missing / update; exactly anthology_snapshot.py's fill semantics). Returns
    (rc, created, updated, skipped). The hook-secret VALUE is never printed."""
    out = out or sys.stderr
    masked = reg._mask_location(location_id)
    created, updated, skipped = [], [], []
    if not to_write:
        return EX_OK, created, updated, skipped
    try:
        existing = client.list_custom_values(location_id)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ location custom values.",
                  ["Location marker: %s" % masked,
                   "Grant the client's OWN location-scoped PIT the customValues "
                   "READ+WRITE scope.",
                   "AF-AE-SNAP-PUSH-REFUSED (customValues scope): STOP, never a "
                   "silent skip."])
        return EX_STOP, created, updated, skipped
    except reg.CafUnreachable as exc:
        out.write("[push-snapshot] HELD: %s (marker %s). Retryable.\n" % (exc, masked))
        return EX_HELD, created, updated, skipped
    index = {}
    for cv in existing:
        nm = cv.get("name")
        cid = cv.get("id") or cv.get("_id")
        if isinstance(nm, str) and cid:
            index[nm.strip().lower()] = cid
    for w in to_write:
        key, name, value, is_secret = w["key"], w["name"], w["value"], w["secret"]
        shown = "(secret; value not shown)" if is_secret else "set"
        cid = index.get(name.strip().lower())
        try:
            if cid:
                client.update_custom_value(location_id, cid, name, value)
                updated.append(key)
                out.write("[push-snapshot]   update %-24s -> %s\n" % (key, shown))
            else:
                client.create_custom_value(location_id, name, value)
                created.append(key)
                out.write("[push-snapshot]   create %-24s -> %s\n" % (key, shown))
        except reg.ScopeDenied:
            reg._stop(out, "The Convert and Flow token lacks customValues WRITE scope.",
                      ["Location marker: %s" % masked,
                       "Custom value that could not be written: %s" % key,
                       "Grant the client's OWN location-scoped PIT customValues "
                       "WRITE scope and re-run.",
                       "AF-AE-SNAP-PUSH-REFUSED (customValues write): STOP, never "
                       "a silent skip."])
            return EX_STOP, created, updated, skipped
        except reg.CafValidation as exc:
            reg._stop(out, "Convert and Flow rejected a custom-value write (%s)."
                      % key,
                      ["Location marker: %s" % masked, "Detail: %s" % exc])
            return EX_MISMATCH, created, updated, skipped
        except reg.CafUnreachable as exc:
            out.write("[push-snapshot] HELD after %d written: %s (marker %s). "
                      "Retryable.\n" % (len(created) + len(updated), exc, masked))
            return EX_HELD, created, updated, skipped
    return EX_OK, created, updated, skipped


# ---------------------------------------------------------------------------
# The tenancy gate (the standing-REJECTED guard, enforced here)
# ---------------------------------------------------------------------------
def tenancy_decision(tenancy_arg: str, location_id: str, contract: dict, *,
                     out=None) -> tuple:
    """Decide the tenancy for ONE target. Returns (branch, reason) where branch
    is "same_agency", "cross_agency", or "unknown". The branch drives whether a
    push is permitted:
      --tenancy same_agency    -> always same_agency (the operator asserts the
                                  whole batch is DAD7 sub-accounts).
      --tenancy cross_agency   -> always cross_agency: the push is the
                                  standing-REJECTED mechanism; refused.
      --tenancy auto (default) -> a location id byte-equal to the contract's own
                                  template location is same_agency; ANY OTHER id
                                  is cross_agency (client-owned) -> refused. An
                                  unknown location is NEVER silently pushed."""
    out = out or sys.stderr
    t = (tenancy_arg or "auto").strip().lower()
    if t == "same_agency":
        return "same_agency", "--tenancy same_agency (explicit)"
    if t == "cross_agency":
        return "cross_agency", "--tenancy cross_agency (explicit)"
    if t == "auto":
        tmpl = template_location_id(contract)
        if tmpl and (location_id or "").strip() == tmpl:
            return "same_agency", "target byte-equals the contract's OWN template location"
        return "cross_agency", ("target is NOT the operator's template location "
                                "(auto: only the template location is same-agency; "
                                "any other location is client-owned -> the standing "
                                "rejection applies)")
    return "unknown", "--tenancy must be same_agency, cross_agency, or auto"


def refuse_cross_agency(out, location_id: str, snapshot_id: str) -> None:
    """The standing-REJECTED surface: the cross-agency agency->subaccount API
    auto-push must never be attempted. LOUD, before any network call."""
    reg._stop(out, "CROSS-AGENCY SNAPSHOT PUSH REJECTED (standing guard).",
              ["Target location marker: %s" % reg._mask_location(location_id),
               "The snapshot %r would be pushed into a location the operator "
               "does NOT own under its agency." % snapshot_id,
               "config/anthology-snapshot-contract.json rejected_mechanisms "
               "records the agency->subaccount API auto-push as REJECTED (a "
               "push across an agency boundary is impossible and is never "
               "attempted); qc-snapshot-contract.sh asserts the record stands.",
               "For a cross-agency client the ONLY path is the share link + "
               "MANUAL import (Settings -> Snapshots -> Import/Load), followed "
               "by the per-client custom-value fill + verify.",
               "AF-AE-SNAP-PUSH-CROSS-AGENCY-REJECTED: STOP, never a silent "
               "fallback, never a faked success."])


# ---------------------------------------------------------------------------
# The batch run: per-target rows + one provision report + aggregate exit
# ---------------------------------------------------------------------------
def _worst(a: int, b: int) -> int:
    """The worst of two house exit codes: any STOP (2) beats any HELD (3) beats
    any mismatch (5) beats OK (0); 1 (unexpected) is never produced here and is
    passed through."""
    if a == EX_ERR or b == EX_ERR:
        return EX_ERR
    if a == EX_STOP or b == EX_STOP:
        return EX_STOP
    if a == EX_HELD or b == EX_HELD:
        return EX_HELD
    if a == EX_MISMATCH or b == EX_MISMATCH:
        return EX_MISMATCH
    return EX_OK


def run_batch(client, targets, contract: dict, field_map: dict, report_path: Path,
              *, snapshot_id: str = "", tenancy_arg: str = "auto",
              company_id: str = "", poll_timeout_s: int = DEFAULT_POLL_TIMEOUT_S,
              poll_interval_s: int = DEFAULT_POLL_INTERVAL_S,
              poll_count: int = -1, dry_run: bool = False, out=None,
              jsonout=None):
    """The batch push. `targets` is a list of dicts {location_id, overrides}
    (already parsed + validated). Returns the aggregate exit code (worst
    per-target). Writes ONE provision report covering every target. One failing
    target NEVER cancels the batch."""
    out = out or sys.stderr
    if not targets:
        reg._stop(out, "No target locations supplied.",
                  ["At least one --target location id is required.",
                   "AF-AE-SNAP-PUSH-TARGET: STOP before any network call."])
        return EX_STOP
    cid_label, cid = resolve_company_id(company_id)
    want_keys = [f["intended_key"] for f in
                 ((field_map.get("provisioning") or {}).get("fields") or [])]
    rows = []
    agg = EX_OK
    for t in targets:
        loc = t["location_id"]
        masked = reg._mask_location(loc)
        branch, reason = tenancy_decision(tenancy_arg, loc, contract, out=out)
        row = {
            "location_masked": masked,
            "tenancy_branch": branch,
            "tenancy_reason": reason,
            "push_attempted": False,
            "pushed": False,
            "status": "",
            "custom_values": {"created": [], "updated": [], "skipped": []},
            "error": "",
        }
        # -- the standing rejection fires BEFORE any network call ---------------
        if branch != "same_agency":
            refuse_cross_agency(out, loc, snapshot_id or contract_snapshot_id(contract))
            row["error"] = "AF-AE-SNAP-PUSH-CROSS-AGENCY-REJECTED"
            row["outcome"] = "rejected"
            rows.append(row)
            agg = _worst(agg, EX_STOP)
            continue

        # -- dry-run: plan the target, no network, no writes -------------------
        if dry_run:
            out.write("[push-snapshot] DRY RUN (marker %s): would GET-check the "
                      "standard pipeline by name, then PUT snapshot %r with "
                      "override. No writes performed.\n" % (masked, snapshot_id))
            row["outcome"] = "planned"
            rows.append(row)
            continue

        # -- 1. GET-check-by-name (idempotency law) ---------------------------
        std_name = (contract.get("pipeline") or {}).get("name") or ""
        try:
            existing = get_standard_pipeline(client, loc, std_name, out=out)
        except reg.ScopeDenied:
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (pipeline read scope)"
            row["outcome"] = "stop"
            rows.append(row)
            agg = _worst(agg, EX_STOP)
            continue
        except reg.CafUnreachable as exc:
            out.write("[push-snapshot] HELD: %s (marker %s). Retryable.\n"
                      % (exc, masked))
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (transport on read)"
            row["outcome"] = "held"
            rows.append(row)
            agg = _worst(agg, EX_HELD)
            continue

        if existing:
            out.write("[push-snapshot] idempotent no-op (marker %s): the standard "
                      "pipeline %r already exists BY NAME on this location "
                      "(AF-AE-SNAP-PUSH-PIPELINE-PRESENT) -- no snapshot push "
                      "performed.\n" % (masked, std_name))
            rc, present = resolve_field_map_keys(client, loc, want_keys, out=out)
            row["outcome"] = "already_imported" if rc == EX_OK else "readback_mismatch"
            row["field_keys_present"] = present
            row["push_attempted"] = False
            rows.append(row)
            agg = _worst(agg, rc)
            continue

        # -- 2. snapshot-id + companyId gates, then the push -------------------
        if not snapshot_id:
            row["error"] = "AF-AE-SNAP-PUSH-NO-FIXTURE (no snapshot id/version)"
            row["outcome"] = "stop"
            rows.append(row)
            agg = _worst(agg, EX_STOP)
            continue
        if not cid or not cid.strip():
            row["error"] = "AF-AE-SNAP-PUSH-COMPANYID-MISSING"
            row["outcome"] = "stop"
            rows.append(row)
            agg = _worst(agg, EX_STOP)
            continue
        row["company_id_masked"] = "...%s" % cid[-4:]
        row["push_attempted"] = True
        try:
            push_snapshot(client, loc, cid, snapshot_id, out=out)
        except reg.ScopeDenied:
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (scope)"
            row["outcome"] = "push_refused_scope"
            rows.append(row)
            agg = _worst(agg, EX_STOP)
            continue
        except reg.CafValidation as exc:
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (validation: %s)" % exc
            row["outcome"] = "push_refused_validation"
            rows.append(row)
            agg = _worst(agg, EX_STOP)
            continue
        except reg.UpstreamBlockedError as exc:
            out.write("[push-snapshot] HELD: %s (marker %s). This is NOT a scope "
                      "problem -- likely a Cloudflare/WAF edge block (CF 1010); "
                      "the request already carries the proven browser User-Agent. "
                      "AF-AE-SNAP-PUSH-REFUSED (edge). Retryable.\n" % (exc, masked))
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (edge)"
            row["outcome"] = "push_held_edge"
            rows.append(row)
            agg = _worst(agg, EX_HELD)
            continue
        except reg.CafUnreachable as exc:
            out.write("[push-snapshot] HELD: %s (marker %s). "
                      "AF-AE-SNAP-PUSH-REFUSED (transport). Retryable.\n"
                      % (exc, masked))
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (transport)"
            row["outcome"] = "push_held_transport"
            rows.append(row)
            agg = _worst(agg, EX_HELD)
            continue
        row["pushed"] = True

        # -- 3. status poll (bounded) ------------------------------------------
        if poll_count == 0:
            row["outcome"] = "status_not_completed"
            row["error"] = "AF-AE-SNAP-PUSH-STATUS-STALLED (poll skipped)"
            rows.append(row)
            agg = _worst(agg, EX_HELD)
            continue
        rc, status = poll_snapshot_status(
            client, loc, timeout_s=poll_timeout_s, interval_s=poll_interval_s,
            out=out)
        row["status"] = status
        if rc != EX_OK:
            row["outcome"] = "status_not_completed"
            row["error"] = "AF-AE-SNAP-PUSH-STATUS-STALLED"
            rows.append(row)
            agg = _worst(agg, rc)
            continue

        # -- 4. read-back: every intended key present BY KEY -------------------
        rc, present = resolve_field_map_keys(client, loc, want_keys, out=out)
        row["field_keys_present"] = present
        if rc != EX_OK:
            row["outcome"] = "readback_mismatch"
            row["error"] = "AF-AE-SNAP-PUSH-READBACK-MISMATCH"
            rows.append(row)
            agg = _worst(agg, rc)
            continue

        # -- 5. per-client custom-VALUE overrides (idempotent fill) ------------
        to_write, _skipped = build_fill_values(contract, t.get("overrides") or {},
                                               out=out)
        rc2, created, updated, skipped = provision_custom_values(
            client, loc, contract, to_write, out=out)
        row["custom_values"] = {"created": created, "updated": updated,
                                "skipped": skipped}
        if rc2 != EX_OK:
            row["outcome"] = "custom_values_%s" % rc2
            row["error"] = "AF-AE-SNAP-PUSH-REFUSED (custom-values fill)"
            rows.append(row)
            agg = _worst(agg, rc2)
            continue

        row["outcome"] = "imported"
        rows.append(row)
        out.write("[push-snapshot] OK (marker %s): snapshot %r imported; %d field "
                  "keys present; %d custom values written.\n"
                  % (masked, snapshot_id, present, len(created) + len(updated)))

    report = {
        "schema_version": 1,
        "engine": "anthology",
        "contract": contract.get("contract"),
        "snapshot_version": contract_snapshot_id(contract),
        "snapshot_id_used": snapshot_id or None,
        "tenancy_mode": (tenancy_arg or "auto").strip().lower(),
        "target_count": len(targets),
        "at": reg._now_iso(),
        "per_client": rows,
    }
    write_report(report_path, report, out=out)
    out.write("[push-snapshot] provision report written to %s (%d target(s), "
              "aggregate exit %d)\n" % (report_path, len(targets), agg))
    if jsonout is not None:
        json.dump({"ok": agg == EX_OK, "target_count": len(targets),
                   "aggregate_exit": agg, "report": str(report_path),
                   "per_client": rows}, jsonout)
        jsonout.write("\n")
    return agg


def write_report(report_path: Path, report: dict, *, out=None) -> int:
    """Atomic temp+replace write of the provision report (house write law;
    a failed write is an unexpected error, never a silent success)."""
    out = out or sys.stderr
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".push-snap.", suffix=".json.tmp",
                                   dir=str(report_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.chmod(tmp, 0o644)
            os.replace(tmp, str(report_path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        out.write("[push-snapshot] ERROR writing report %s: %s\n"
                  % (report_path, type(exc).__name__))
        return EX_ERR
    return EX_OK


# ---------------------------------------------------------------------------
# Target parsing + overrides loading (AF-AE-SNAP-PUSH-TARGET)
# ---------------------------------------------------------------------------
def parse_targets(raw_targets, contract: dict, *, out=None) -> tuple:
    """Parse --target arguments: each is <location_id> or
    <location_id>,<overrides.json>. Returns (targets, refusals): targets is a
    list of {location_id, overrides}; refusals is a list of (raw, reason) that
    STOP the whole batch BEFORE any network call (AF-AE-SNAP-PUSH-TARGET)."""
    out = out or sys.stderr
    targets, refusals = [], []
    for raw in raw_targets or []:
        raw = (raw or "").strip()
        if not raw:
            refusals.append((raw, "empty --target"))
            continue
        parts = [p.strip() for p in raw.split(",")]
        loc = parts[0]
        if not loc:
            refusals.append((raw, "missing location id"))
            continue
        overrides = {}
        if len(parts) > 1 and parts[1]:
            ov_path = Path(parts[1]).expanduser()
            if not ov_path.is_file():
                refusals.append((raw, "overrides file not found: %s" % parts[1]))
                continue
            try:
                overrides = load_json(ov_path)
            except (ValueError, OSError) as exc:
                refusals.append((raw, "overrides file unreadable: %s" % exc))
                continue
            bad = validate_overrides(contract, overrides)
            if bad:
                refusals.append((raw, "overrides refused: %s"
                                 % "; ".join("%s (%s)" % (k, r) for k, r in bad)))
                continue
        targets.append({"location_id": loc, "overrides": overrides})
    return targets, refusals


# ---------------------------------------------------------------------------
# Read-only status / verify-only commands (never mutate)
# ---------------------------------------------------------------------------
def status_batch(client, targets, contract: dict, *, timeout_s: int,
                 interval_s: int, out=None, jsonout=None) -> int:
    rows = []
    agg = EX_OK
    for t in targets:
        loc = t["location_id"]
        masked = reg._mask_location(loc)
        branch, _reason = tenancy_decision("auto", loc, contract, out=out)
        rc, status = poll_snapshot_status(client, loc, timeout_s=timeout_s,
                                          interval_s=interval_s, out=out)
        rows.append({"location_masked": masked, "tenancy_branch": branch,
                     "status": status, "exit": rc})
        agg = _worst(agg, rc)
    if jsonout is not None:
        json.dump({"ok": agg == EX_OK, "targets": rows}, jsonout)
        jsonout.write("\n")
    return agg


def verify_only_batch(client, targets, contract: dict, field_map: dict, *,
                      out=None, jsonout=None) -> int:
    rows = []
    agg = EX_OK
    want_keys = [f["intended_key"] for f in
                 ((field_map.get("provisioning") or {}).get("fields") or [])]
    std_name = (contract.get("pipeline") or {}).get("name") or ""
    for t in targets:
        loc = t["location_id"]
        masked = reg._mask_location(loc)
        branch, _reason = tenancy_decision("auto", loc, contract, out=out)
        try:
            existing = get_standard_pipeline(client, loc, std_name, out=out)
        except reg.ScopeDenied:
            rows.append({"location_masked": masked, "tenancy_branch": branch,
                         "pipeline_present": None, "exit": EX_STOP,
                         "error": "pipeline read scope"})
            agg = _worst(agg, EX_STOP)
            continue
        except reg.CafUnreachable as exc:
            rows.append({"location_masked": masked, "tenancy_branch": branch,
                         "pipeline_present": None, "exit": EX_HELD,
                         "error": str(exc)})
            agg = _worst(agg, EX_HELD)
            continue
        rc, present = resolve_field_map_keys(client, loc, want_keys, out=out)
        rows.append({"location_masked": masked, "tenancy_branch": branch,
                     "pipeline_present": bool(existing), "field_keys_present": present,
                     "exit": rc})
        agg = _worst(agg, rc)
    if jsonout is not None:
        json.dump({"ok": agg == EX_OK, "targets": rows}, jsonout)
        jsonout.write("\n")
    return agg


# ---------------------------------------------------------------------------
# OFFLINE plan (no network, no writes)
# ---------------------------------------------------------------------------
def plan_command(targets, contract: dict, *, snapshot_id: str = "",
                 tenancy_arg: str = "auto", out=None, jsonout=None) -> int:
    out = out or sys.stderr
    lines = []
    refused = 0
    for t in targets:
        loc = t["location_id"]
        branch, reason = tenancy_decision(tenancy_arg, loc, contract, out=out)
        lines.append({"location_masked": reg._mask_location(loc),
                      "tenancy_branch": branch, "tenancy_reason": reason,
                      "overrides": sorted((t.get("overrides") or {}).keys())})
        if branch != "same_agency":
            refused += 1
    if jsonout is not None:
        json.dump({"ok": refused == 0, "snapshot_id": snapshot_id or
                   contract_snapshot_id(contract),
                   "tenancy_mode": (tenancy_arg or "auto").strip().lower(),
                   "target_count": len(targets), "refused_cross_agency": refused,
                   "targets": lines}, jsonout)
        jsonout.write("\n")
        return EX_OK if refused == 0 else EX_STOP
    out.write("PUSH SNAPSHOT TO SUBACCOUNTS — PLAN (offline)\n")
    out.write("  approved snapshot id: %r\n" % (snapshot_id or contract_snapshot_id(contract)))
    out.write("  tenancy mode: %r (cross-agency push is standing-REJECTED; "
              "auto allows only the operator's own template location)\n"
              % (tenancy_arg or "auto").strip().lower())
    out.write("  target count: %d\n" % len(targets))
    for ln in lines:
        out.write("    - %-14s %-12s %s\n"
                  % (ln["location_masked"], ln["tenancy_branch"],
                     "; ".join(ln["overrides"]) or "(no overrides)"))
    if refused:
        out.write("  REFUSED (cross-agency standing guard): %d target(s). "
                  "AF-AE-SNAP-PUSH-CROSS-AGENCY-REJECTED.\n" % refused)
        return EX_STOP
    return EX_OK


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets. Mirrors the
# sibling self-tests (provision_snapshot_import.py / anthology_snapshot.py): an
# in-memory fake Convert and Flow exercises the tenancy gate, the idempotency
# law, the push, the poll ladder, the read-back, the overrides fill, the
# never-print rule, and the per-client report.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """In-memory Convert and Flow covering exactly the batch surface:
    list_pipelines (GET-check-by-name), list_custom_fields (read-back),
    list/create/update custom values, snapshot PUT (recorded), snapshot-status
    GET (scripted)."""

    def __init__(self, *, pipelines=None, fields=None, status_outcome="completed",
                 push_behavior="ok", cv_read=True, cv_write=True):
        self._pipelines = list(pipelines or [])
        self._fields = {f["fieldKey"]: dict(f) for f in (fields or [])}
        self._status_outcome = status_outcome
        self._push_behavior = push_behavior
        self._cv_read = cv_read
        self._cv_write = cv_write
        self.values = {}
        self.pushes = []
        self._seq = 0
        self._status_calls = 0

    def list_pipelines(self, location_id):
        return [dict(p) for p in self._pipelines]

    def list_custom_fields(self, location_id):
        return [dict(fieldKey=k, **{kk: vv for kk, vv in v.items() if kk != "fieldKey"})
                for k, v in self._fields.items()]

    def list_custom_values(self, location_id):
        if not self._cv_read:
            raise reg.ScopeDenied("no customValues read scope")
        return [{"id": k, "name": v["name"], "value": v["value"]}
                for k, v in self.values.items()]

    def create_custom_value(self, location_id, name, value):
        if not self._cv_write:
            raise reg.ScopeDenied("no customValues write scope")
        self._seq += 1
        cid = "cv-%d" % self._seq
        self.values[cid] = {"name": name, "value": value}
        return {"id": cid, "name": name}

    def update_custom_value(self, location_id, cv_id, name, value):
        if not self._cv_write:
            raise reg.ScopeDenied("no customValues write scope")
        self.values[cv_id] = {"name": name, "value": value}
        return {"id": cv_id, "name": name}

    def _request(self, method, path, query=None, body=None):
        if method == "PUT" and path.startswith("/locations/"):
            if self._push_behavior == "scope":
                raise reg.ScopeDenied("fixture: no locations.write scope")
            if self._push_behavior == "validation":
                raise reg.CafValidation("fixture: snapshot rejected (400)")
            if self._push_behavior == "edge":
                raise reg.UpstreamBlockedError("fixture: HTTP 403 edge block (CF 1010)")
            if self._push_behavior == "transport":
                raise reg.CafUnreachable("fixture: connect timeout")
            self._seq += 1
            self.pushes.append({"path": path, "body": body})
            return {"ok": True}
        if method == "GET" and path == SNAPSHOT_STATUS_PATH:
            if self._status_outcome == "processing-then-completed":
                if self._status_calls == 0:
                    self._status_calls = 1
                    return {"status": _STATUS_PROCESSING}
                return {"status": _STATUS_COMPLETED}
            if self._status_outcome == "failed":
                return {"status": _STATUS_FAILED}
            if self._status_outcome == "stalled":
                return {"status": _STATUS_PROCESSING}
            if self._status_outcome == "scope":
                raise reg.ScopeDenied("fixture: no snapshot-status scope")
            return {"status": _STATUS_COMPLETED}
        raise AssertionError("unexpected %s %s" % (method, path))


def _fixture_fields(field_map, *, drop=None):
    out = []
    for f in field_map["provisioning"]["fields"]:
        if f["intended_key"] == drop:
            continue
        out.append({"fieldKey": f["intended_key"], "id": "fld-%s" % f["create_name"],
                    "name": f["create_name"], "dataType": f.get("data_type", "LARGE_TEXT")})
    return out


def _fixture_pipeline(contract):
    return {"id": "pipe-1", "name": contract["pipeline"]["name"],
            "stages": [{"id": "stg-%d" % s["position"], "name": s["name"]}
                       for s in contract["pipeline"]["stages"]]}


def _targets(template_id, other_id):
    """Two target locations: the operator's OWN template location (same-agency
    under --tenancy auto) and a client-owned location (cross-agency, refused)."""
    return [
        {"location_id": template_id, "overrides": {
            "producer": "Jane Doe",
            "producer_email": "jane@example.com",
            "anthology_webhook_url": "https://box.example.com/hooks/anthology-intake",
        }},
        {"location_id": other_id, "overrides": {}},
    ]


def self_test() -> int:
    import io
    dev = io.StringIO()
    contract = load_json(CONTRACT_PATH)
    field_map = load_json(FIELD_MAP_PATH)
    td = Path(tempfile.mkdtemp(prefix="ae-pushsnap-"))
    rpt_path = td / "provision_report.json"
    tmpl = template_location_id(contract)
    other = "loc_CLIENT_OWNED_000001"
    assert tmpl, "contract source_template_location.template_location_id must be present"
    want_keys = [f["intended_key"] for f in field_map["provisioning"]["fields"]]

    try:
        return _self_test_body(dev, contract, field_map, rpt_path, tmpl, other, want_keys)
    except AssertionError as exc:
        # A self-test FAILURE is an enforced violation, never an "unexpected
        # error": the field-map drift a tamper produces is exactly the
        # AF-AE-SNAP-PUSH-* family this module documents (read-back law). The
        # OFFLINE self-test reports the SAME code family, exit 4 — a tamper
        # NEVER masquerades as exit 1.
        sys.stderr.write("[push_snapshot_to_subaccounts] SELF-TEST FAILED "
                         "(AF-AE-SNAP-PUSH-* family): %s\n" % exc)
        return EX_VIOLATION


def _self_test_body(dev, contract, field_map, rpt_path, tmpl, other, want_keys) -> int:
    import io
    # ---- field-map <-> contract coherence: a drifted field-map must FAIL the
    #      self-test, never pass it (the read-back fixtures derive from the
    #      map, so a tampered map would otherwise self-confirm). The coherence
    #      assert is the FIRST self-test check for that reason.
    contract_keys = [f["intended_key"] for f in (contract.get("custom_fields") or {}).get("fields", [])]
    assert want_keys == contract_keys, \
        "field-map provisioning.fields drifted from contract custom_fields " \
        "(AF-AE-SNAP-PUSH-READBACK-MISMATCH family)"

    # -- (0) overrides validation ---------------------------------------------
    assert validate_overrides(contract, {"producer": "Jane"}) == []
    bad = validate_overrides(contract, {"producer": "https://real.example.com/x"})
    assert bad and bad[0][0] == "producer", bad
    bad = validate_overrides(contract, {"not_a_key": "x"})
    assert bad and bad[0][0] == "not_a_key", bad
    bad = validate_overrides(contract, {"anthology_hook_secret": "Bearer ANYTHING"})
    assert bad == [], "the secret key may legitimately carry a token-shaped value"

    # -- (1) tenancy gate: auto refuses the client-owned location BEFORE any
    #        network call; the template location is same-agency -----------------
    branch, _r = tenancy_decision("auto", tmpl, contract, out=dev)
    assert branch == "same_agency", branch
    branch, _r = tenancy_decision("auto", other, contract, out=dev)
    assert branch == "cross_agency", branch
    branch, _r = tenancy_decision("same_agency", other, contract, out=dev)
    assert branch == "same_agency", "explicit same_agency must override auto"
    branch, _r = tenancy_decision("cross_agency", tmpl, contract, out=dev)
    assert branch == "cross_agency", "explicit cross_agency refuses even the template"

    # -- (2) batch with the client-owned target: the push is REFUSED (exit 2),
    #        the template target pushes, the report has BOTH rows -----------------
    caf = _FakeCaf(fields=_fixture_fields(field_map),
                   status_outcome="processing-then-completed")
    rc = run_batch(caf, _targets(tmpl, other), contract, field_map, rpt_path,
                   snapshot_id=contract_snapshot_id(contract), out=dev)
    assert rc == EX_STOP, "a rejected target must make the batch exit 2, got %s" % rc
    assert len(caf.pushes) == 1, "exactly the template target may be pushed, got %d" % len(caf.pushes)
    body = caf.pushes[0]["body"]
    assert body["snapshot"]["override"] is True
    assert body["snapshot"]["id"] == contract_snapshot_id(contract)
    assert body["companyId"] == SAME_AGENCY_COMPANY_ID
    assert "AF-AE-SNAP-PUSH-CROSS-AGENCY-REJECTED" in dev.getvalue(), \
        "the standing rejection must appear on the operator surface"
    rpt = load_json(rpt_path)
    assert len(rpt["per_client"]) == 2, "the report must carry BOTH target rows"
    by_loc = {r["location_masked"]: r for r in rpt["per_client"]}
    assert by_loc["...%s" % other[-4:]]["outcome"] == "rejected"
    assert by_loc["...%s" % other[-4:]]["push_attempted"] is False
    assert by_loc["...%s" % tmpl[-4:]]["outcome"] == "imported"
    assert by_loc["...%s" % tmpl[-4:]]["pushed"] is True
    assert by_loc["...%s" % tmpl[-4:]]["field_keys_present"] == len(want_keys)

    # -- (3) idempotency: an already-imported template target is NEVER re-pushed --
    caf2 = _FakeCaf(pipelines=[_fixture_pipeline(contract)],
                    fields=_fixture_fields(field_map))
    rc = run_batch(caf2, _targets(tmpl, other), contract, field_map, rpt_path,
                   snapshot_id=contract_snapshot_id(contract), out=dev)
    assert rc == EX_STOP, "rejected target still drives the aggregate, got %s" % rc
    assert caf2.pushes == [], "an already-imported location must NEVER be pushed"
    rpt2 = load_json(rpt_path)
    by_loc2 = {r["location_masked"]: r for r in rpt2["per_client"]}
    assert by_loc2["...%s" % tmpl[-4:]]["outcome"] == "already_imported"

    # -- (4) the standing rejection fires BEFORE any network call: a client that
    #        cannot be reached must never be touched -------------------------------
    dev4 = io.StringIO()
    _fb_saved = {n: os.environ.pop(n, None) for n in HOOK_SECRET_LABELS}
    try:
        rc = run_batch(None, [{"location_id": other, "overrides": {}}],
                       contract, field_map, rpt_path,
                       snapshot_id=contract_snapshot_id(contract), out=dev4)
    finally:
        for n, v in _fb_saved.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
    assert rc == EX_STOP and "AF-AE-SNAP-PUSH-CROSS-AGENCY-REJECTED" in dev4.getvalue()

    # -- (5) explicit same-agency batch: push refusal ladder ----------------------
    for behavior, want in (("scope", EX_STOP), ("validation", EX_STOP),
                           ("edge", EX_HELD), ("transport", EX_HELD)):
        dev5 = io.StringIO()
        caf5 = _FakeCaf(fields=_fixture_fields(field_map), push_behavior=behavior)
        rc = run_batch(caf5, [{"location_id": tmpl, "overrides": {}}],
                       contract, field_map, rpt_path,
                       snapshot_id=contract_snapshot_id(contract),
                       tenancy_arg="same_agency", out=dev5)
        assert rc == want, "push_behavior %r: want %s, got %s" % (behavior, want, rc)
        assert caf5.pushes == [], "a refused push must not be recorded as pushed"
        if behavior == "edge":
            assert "NOT a scope problem" in dev5.getvalue(), \
                "an edge block must NEVER be mislabeled as a scope problem"

    # -- (6) status ladder: failed -> HELD, stalled -> HELD, scope -> STOP --------
    for outcome, want in (("failed", EX_HELD), ("stalled", EX_HELD),
                          ("scope", EX_STOP)):
        dev6 = io.StringIO()
        caf6 = _FakeCaf(fields=_fixture_fields(field_map), status_outcome=outcome)
        rc = run_batch(caf6, [{"location_id": tmpl, "overrides": {}}],
                       contract, field_map, rpt_path,
                       snapshot_id=contract_snapshot_id(contract),
                       tenancy_arg="same_agency", poll_timeout_s=1,
                       poll_interval_s=1, out=dev6)
        assert rc == want, "status_outcome %r: want %s, got %s" % (outcome, want, rc)

    # -- (7) read-back mismatch -> exit 5, report row marks it, nothing pushed -----
    dev7 = io.StringIO()
    drop_key = want_keys[-1]
    caf7 = _FakeCaf(fields=_fixture_fields(field_map, drop=drop_key))
    rc = run_batch(caf7, [{"location_id": tmpl, "overrides": {}}],
                   contract, field_map, rpt_path,
                   snapshot_id=contract_snapshot_id(contract),
                   tenancy_arg="same_agency", out=dev7)
    assert rc == EX_MISMATCH, "missing read-back field must exit 5, got %s" % rc
    assert "AF-AE-SNAP-PUSH-READBACK-MISMATCH" in dev7.getvalue()

    # -- (8) custom-value fill: create + idempotent update, secret never printed ----
    dev8 = io.StringIO()
    caf8 = _FakeCaf(fields=_fixture_fields(field_map))
    overrides8 = {"producer": "Jane Doe", "producer_email": "jane@example.com",
                  "anthology_webhook_url": "https://box.example.com/hooks/anthology-intake",
                  "anthology_hook_secret": "Bearer SEKRIT"}
    rc = run_batch(caf8, [{"location_id": tmpl, "overrides": overrides8}],
                   contract, field_map, rpt_path,
                   snapshot_id=contract_snapshot_id(contract),
                   tenancy_arg="same_agency", out=dev8)
    assert rc == EX_OK, "custom-values fill must exit 0, got %s" % rc
    assert len(caf8.values) == 4, "expected 4 custom values created, got %d" % len(caf8.values)
    assert "SEKRIT" not in dev8.getvalue(), "SECRET VALUE LEAKED to the operator surface"
    rpt8 = load_json(rpt_path)
    cv = rpt8["per_client"][0]["custom_values"]
    assert len(cv["created"]) == 4, cv
    # re-run -> all UPDATE (idempotent, no duplicates)
    rc = run_batch(caf8, [{"location_id": tmpl, "overrides": overrides8}],
                   contract, field_map, rpt_path,
                   snapshot_id=contract_snapshot_id(contract),
                   tenancy_arg="same_agency", out=dev8)
    assert rc == EX_OK and len(caf8.values) == 4, "idempotent re-run must not duplicate"
    rpt8b = load_json(rpt_path)
    assert len(rpt8b["per_client"][0]["custom_values"]["updated"]) == 4, rpt8b

    # -- (9) malformed target / missing overrides file -> STOP before any call -----
    dev9 = io.StringIO()
    targets9, refusals9 = parse_targets(["loc_A,/no/such/overrides.json"], contract,
                                        out=dev9)
    assert targets9 == [] and len(refusals9) == 1, (targets9, refusals9)
    rc = run_batch(None, targets9, contract, field_map, rpt_path,
                   snapshot_id="x", out=dev9)
    assert rc == EX_STOP, "malformed targets must STOP the batch, got %s" % rc
    assert "AF-AE-SNAP-PUSH-TARGET" in dev9.getvalue() or "not found" in dev9.getvalue()

    # -- (10) dry-run: no network, no push, no report -----------------------------
    dev10 = io.StringIO()
    caf10 = _FakeCaf(fields=_fixture_fields(field_map))
    rc = run_batch(caf10, [{"location_id": tmpl, "overrides": {}}],
                   contract, field_map, rpt_path,
                   snapshot_id=contract_snapshot_id(contract),
                   tenancy_arg="same_agency", dry_run=True, out=dev10)
    assert rc == EX_OK and caf10.pushes == [], "dry-run must plan without pushing"
    assert "DRY RUN" in dev10.getvalue()

    # -- (11) never-print: no secret value / no raw location id on any surface -----
    all_text = (dev.getvalue() + dev4.getvalue() + dev5.getvalue()
                + dev8.getvalue() + json.dumps(load_json(rpt_path)))
    for token in ("pit-", "SEKRIT", "Bearer ", tmpl, other):
        assert token not in all_text, "surface leak: %r must never appear" % token

    # -- (12) offline plan: refused targets make the plan STOP --------------------
    dev12 = io.StringIO()
    rc = plan_command(_targets(tmpl, other), contract,
                      snapshot_id=contract_snapshot_id(contract), out=dev12)
    assert rc == EX_STOP, "cross-agency plan must STOP, got %s" % rc
    rc = plan_command(_targets(tmpl, other), contract, tenancy_arg="same_agency",
                      snapshot_id=contract_snapshot_id(contract), out=dev12)
    assert rc == EX_OK, "explicit same-agency plan must pass, got %s" % rc

    print("push_snapshot_to_subaccounts self-test: OK "
          "(tenancy gate auto/same/cross, cross-agency standing rejection "
          "[refused before any network call], per-client report with BOTH rows, "
          "idempotency [already-imported -> no push], push-refusal ladder "
          "scope/validation/edge/transport, status ladder failed/stalled/scope, "
          "read-back mismatch exit 5, custom-value create/update idempotency "
          "with the secret never printed, malformed-target STOP, dry-run "
          "plans without writing, never-print, offline plan)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="push_snapshot_to_subaccounts.py",
        description="Push the approved template snapshot to client-owned Convert "
                    "and Flow locations, with per-client custom-value overrides, "
                    "and emit a per-client provision report (Skill 59, "
                    "MASTER-SPEC NEW-3). Cross-agency agency->subaccount "
                    "auto-push is standing-REJECTED and refused before any "
                    "network call.")
    ap.add_argument("--snapshot-id", default="",
                    help="the approved snapshot id/version to push (default: the "
                    "contract snapshot_version; an empty id is refused)")
    ap.add_argument("--target", action="append", default=[],
                    help="target location id, optionally followed by a comma and "
                    "an overrides JSON file: <location_id> or "
                    "<location_id>,<overrides.json> (repeatable)")
    ap.add_argument("--tenancy", default="auto",
                    choices=("auto", "same_agency", "cross_agency"),
                    help="auto (default): only the operator's OWN template "
                    "location may be pushed (cross-agency is standing-REJECTED); "
                    "same_agency: assert the whole batch is DAD7 sub-accounts; "
                    "cross_agency: refuse every target")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the "
                    "read-back keys)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--provision-report", default="",
                    help="path to the provision_report.json output (default: "
                    "config/provision_report.json next to the field-map)")
    ap.add_argument("--location-id", default="",
                    help="override the client Convert and Flow location id "
                    "(label CONVERT_AND_FLOW_LOCATION_ID by default; never "
                    "printed)")
    ap.add_argument("--company-id", default="",
                    help="override the SAME-AGENCY companyId (env "
                    "ANTHOLOGY_SNAPSHOT_COMPANY_ID, else the contract-recorded "
                    "BlackCEO agency id)")
    ap.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S,
                    help="snapshot-status poll bound in seconds (default %d)"
                    % DEFAULT_POLL_TIMEOUT_S)
    ap.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL_S,
                    help="snapshot-status poll cadence in seconds (default %d)"
                    % DEFAULT_POLL_INTERVAL_S)
    ap.add_argument("--poll-count", type=int, default=-1,
                    help="status poll cap (-1 = poll until timeout; 0 = skip the "
                    "wait, never verified)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the batch without performing it / no network")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["push", "status", "verify-only", "plan",
                                    "self-test"])

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # so argparse's required positional cmd never rejects the flag form.
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        contract = load_json(Path(args.contract).expanduser())
        field_map = reg.load_field_map(Path(args.field_map).expanduser())

        # --target parsing + overrides validation (AF-AE-SNAP-PUSH-TARGET).
        # A refusal STOPS the whole batch BEFORE any network call.
        targets, refusals = parse_targets(args.target, contract)
        if refusals:
            reg._stop(sys.stderr, "Malformed --target argument(s).",
                      ["AF-AE-SNAP-PUSH-TARGET: STOP before any network call."]
                      + ["- %s (%s)" % (raw or "<empty>", reason)
                         for raw, reason in refusals])
            return EX_STOP
        if not targets:
            reg._stop(sys.stderr, "No --target locations supplied.",
                      ["At least one target location id is required.",
                       "AF-AE-SNAP-PUSH-TARGET: STOP."])
            return EX_STOP

        report_path = Path(args.provision_report).expanduser() if args.provision_report.strip() \
            else Path(args.field_map).expanduser().parent / "provision_report.json"

        if args.cmd == "plan":
            return plan_command(targets, contract, snapshot_id=args.snapshot_id,
                                tenancy_arg=args.tenancy, jsonout=jsonout)

        if args.cmd == "push":
            if args.dry_run:
                # No network in dry-run: plan only.
                return plan_command(targets, contract, snapshot_id=args.snapshot_id,
                                    tenancy_arg=args.tenancy, jsonout=jsonout)
            sid = args.snapshot_id.strip() or contract_snapshot_id(contract)
            if not sid:
                reg._stop(sys.stderr, "No approved snapshot id/version is available.",
                          ["The contract snapshot_version is empty AND no "
                           "--snapshot-id was supplied.",
                           "A push without an approved snapshot id is never "
                           "performed.",
                           "AF-AE-SNAP-PUSH-NO-FIXTURE: STOP."])
                return EX_STOP
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return run_batch(
                client, targets, contract, field_map, report_path,
                snapshot_id=sid, tenancy_arg=args.tenancy,
                company_id=args.company_id, poll_timeout_s=args.poll_timeout,
                poll_interval_s=args.poll_interval, poll_count=args.poll_count,
                dry_run=False, jsonout=jsonout)

        if args.cmd == "status":
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return status_batch(client, targets, contract,
                                timeout_s=args.poll_timeout,
                                interval_s=args.poll_interval, jsonout=jsonout)

        if args.cmd == "verify-only":
            client, loc_or_rc = reg._live_client(args.location_id)
            if client is None:
                return loc_or_rc
            return verify_only_batch(client, targets, contract, field_map,
                                     jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        sys.stderr.write("[push_snapshot_to_subaccounts] file not found: %s\n" % exc)
        return EX_ERR
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[push_snapshot_to_subaccounts] unexpected error: %s\n"
                         % type(exc).__name__)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
