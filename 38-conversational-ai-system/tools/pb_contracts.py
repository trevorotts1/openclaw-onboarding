#!/usr/bin/env python3
"""Shared Purple Billboard contract validator.

Enforces the typed contract layer only: collection state, strict outbound
envelopes, the revisioned approval manifest, shared readiness evidence and the
control-action lifecycle. It never talks to a provider and never sends anything.

Source of truth for the rules: Purple-Billboard-Client-System-Build/
DATA-CONTRACTS.md sections 1, 2, 3, 9 and 10 (DEC-02, DEC-08).

Commands
  validate    --kind KIND --file F [--manifest M]
  transition  --kind collection|action|lifecycle --before B --after A
  dispatch    --action F --gate G --ledger L [--manifest M] [--now T]
              [--max-gate-age-seconds N]
  receipt     --ledger L --key K --status S [--provider-object-id X]
              [--evidence-id E] [--now T]
  fulfill     --outbox F --fulfillment-ledger F --journal F --item F --basis F
              [--worker-id ID]
  fulfill-basis   --fulfillment-ledger F --basis F
  fulfill-access  --fulfillment-ledger F --item F --evidence E --accessible|--inaccessible
  fulfill-resume  (same paths) [--retry]
  fulfill-proof   (same paths) --proof F
  fulfill-continue (same paths)

The fulfill-* commands drive the T-13 direct original fulfillment module
(tools/direct_fulfillment.py) over the caller's append-only journal. They hand
it files and print its outcome, so this CLI still calls no provider itself.

Exit codes: 0 = accepted/dispatched/collapsed, 1 = contract violation or
refusal, 2 = usage/IO error. Every command prints one JSON object.

Dependency policy: stdlib only. The repo's qc-static CI runner installs nothing,
so a jsonschema import here would make the gate unrunnable in the place it
matters. When jsonschema IS importable the self-check cross-validates against
it, so the subset engine cannot drift silently.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Direct-script execution (python3 -I pb_contracts.py) does not put this
# directory on sys.path; the sibling module must still resolve.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import compat_guard  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = SKILL_ROOT / "schemas"

SCHEMA_FILES = {
    "collection": "collection-state.schema.json",
    "outbound": "outbound-action.schema.json",
    "approval": "approval-manifest.schema.json",
    "readiness": "readiness-evidence.schema.json",
    "action": "action-lifecycle.schema.json",
    "lifecycle": "engineering-loop.schema.json",
    "compatibility": "compatibility-record.schema.json",
    "reconciliation": "contact-reconciliation.schema.json",
}

# DATA-CONTRACTS section 3: the return must carry binding, policy and fence.
GATE_COMMON_CHECKS = [
    ("policy_revision", "policy_version", "POLICY_CHANGED"),
    ("content_revision", "content_revision", "CONTENT_CHANGED"),
    ("asset_version_id", "asset_version_id", "ASSET_CHANGED"),
]
# Section 3 public branch: exact approved placement/account/channel/schedule/CTA/
# keyword/assets/spares. The approved manifest is the authority, so any divergence
# on these fields blocks dispatch and names the field.
PLACEMENT_BOUND_FIELDS = [
    "channel",
    "scheduled_at",
    "timezone",
    "content_revision",
    "cta_text",
    "keyword",
    "promised_item_version",
    "bonus_asset_versions",
    "conversation_policy_version",
    "allowed_spare_ids",
]
LIFECYCLE_LADDER = ["NOT_INSTALLED", "ADOPTING", "RUNNING", "PAUSED_RESUMABLE", "CLOSING", "CLOSED"]
LIFECYCLE_EDGES = {
    "NOT_INSTALLED": {"ADOPTING"},
    "ADOPTING": {"RUNNING", "CANCELED"},
    "RUNNING": {"PAUSED_RESUMABLE", "CLOSING", "CANCELED"},
    "PAUSED_RESUMABLE": {"RUNNING", "CLOSING", "CANCELED"},
    "CLOSING": {"CLOSED", "CANCELED"},
    "CLOSED": set(),
    "CANCELED": set(),
}
NEVER_ROLLED_BACK = [
    "sent_effects",
    "contact_facts",
    "consent_suppression",
    "counters",
    "unknown_send_reconciliation",
]
DM_CHANNELS = {"FB_DM", "IG_DM"}

READINESS_KEYS = ["installed", "configured", "running", "replied", "fulfilled"]
TERMINAL_COLLECTION = {
    "stopped_complete",
    "stopped_declined",
    "stopped_final",
    "stopped_ineligible",
}
ACTION_LADDER = ["not_requested", "queued", "dispatched", "acknowledged", "completed"]
ACTION_TERMINAL = {"completed", "canceled"}
ACTION_SIDEWAYS = {"unknown", "failed", "canceled"}
COLLAPSE_STATUSES = {"queued", "dispatching", "accepted", "sent", "delivered"}
RETRYABLE_STATUSES = {"failed_not_sent", "suppressed", "quarantined", "expired"}
RECEIPT_STATUSES = [
    "accepted",
    "sent",
    "delivered",
    "failed_not_sent",
    "failed_after_acceptance",
    "unknown",
    "suppressed",
]


class UsageError(Exception):
    pass


# --------------------------------------------------------------------------
# JSON Schema subset engine (draft 2020-12 subset actually used by schemas/)
# --------------------------------------------------------------------------

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}
_JSON_TYPE_NAMES = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
    type(None): "null",
    dict: "object",
    list: "array",
}


def _kind(value):
    return _JSON_TYPE_NAMES.get(type(value), type(value).__name__)


def _type_ok(value, expected):
    if isinstance(expected, list):
        return any(_type_ok(value, one) for one in expected)
    check = _TYPE_CHECKS.get(expected)
    if check is None:
        raise UsageError("unsupported schema type %r" % (expected,))
    return check(value)


def validate_schema(schema, value, path="$"):
    """Return a list of 'path: message' strings. Empty list means valid."""
    errs = []

    if "type" in schema and not _type_ok(value, schema["type"]):
        return ["%s: expected type %s, got %s" % (path, schema["type"], _kind(value))]

    if "const" in schema and value != schema["const"]:
        errs.append("%s: expected const %r, got %r" % (path, schema["const"], value))

    if "enum" in schema and value not in schema["enum"]:
        errs.append("%s: %r is not one of %s" % (path, value, schema["enum"]))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append("%s: shorter than minLength %d" % (path, schema["minLength"]))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append("%s: below minimum %r" % (path, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errs.append("%s: above maximum %r" % (path, schema["maximum"]))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append("%s: fewer than minItems %d" % (path, schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append("%s: more than maxItems %d" % (path, schema["maxItems"]))
        if schema.get("uniqueItems"):
            seen = []
            for item in value:
                canon = json.dumps(item, sort_keys=True)
                if canon in seen:
                    errs.append("%s: duplicate item %r" % (path, item))
                    break
                seen.append(canon)
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                errs.extend(validate_schema(schema["items"], item, "%s[%d]" % (path, index)))

    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errs.append("%s: missing required property %r" % (path, name))
        properties = schema.get("properties", {})
        for name, subschema in properties.items():
            if name in value:
                errs.extend(validate_schema(subschema, value[name], "%s.%s" % (path, name)))
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errs.append("%s: unexpected property %r" % (path, name))

    for subschema in schema.get("allOf", []):
        errs.extend(validate_schema(subschema, value, path))

    if "oneOf" in schema:
        matches = 0
        branch_errors = []
        for index, branch in enumerate(schema["oneOf"]):
            branch_errs = validate_schema(branch, value, path)
            if not branch_errs:
                matches += 1
            elif matches == 0:
                branch_errors.append("oneOf[%d] %s" % (index, branch_errs[0]))
        if matches != 1:
            errs.append("%s: must match exactly one oneOf branch, matched %d" % (path, matches))
            if matches == 0:
                errs.extend(branch_errors)

    if "if" in schema:
        if not validate_schema(schema["if"], value, path):
            if "then" in schema:
                errs.extend(validate_schema(schema["then"], value, path))
        elif "else" in schema:
            errs.extend(validate_schema(schema["else"], value, path))

    return errs


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError("file not found: %s" % path)
    except json.JSONDecodeError as exc:
        raise UsageError("invalid JSON in %s: %s" % (path, exc))


def load_schema(kind):
    if kind not in SCHEMA_FILES:
        raise UsageError("unknown kind %r (expected one of %s)" % (kind, sorted(SCHEMA_FILES)))
    return load_json(SCHEMA_DIR / SCHEMA_FILES[kind])


def branch_gate_schema(scope):
    """Return the dispatch-gate schema for one outbound branch."""
    schema = load_schema("outbound")
    for branch in schema["oneOf"]:
        if branch["properties"]["scope"].get("const") == scope:
            gate = copy.deepcopy(branch["properties"]["dispatch_gate"])
            gate["type"] = "object"
            return gate
    raise UsageError("no outbound branch for scope %r" % scope)


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------


def parse_ts(value, label="timestamp"):
    if not isinstance(value, str) or not value:
        raise UsageError("%s must be a non-empty ISO-8601 string, got %r" % (label, value))
    raw = value.replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        raise UsageError("%s is not ISO-8601: %r" % (label, value))
    if stamp.tzinfo is None:
        raise UsageError("%s must carry an explicit timezone: %r" % (label, value))
    return stamp


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# Semantic checks (rules JSON Schema cannot express)
# --------------------------------------------------------------------------


def semantic_collection(doc):
    errs = []
    request_ids = []
    for index, item in enumerate(doc["requested_items"]):
        path = "$.requested_items[%d]" % index
        request_ids.append(item["request_id"])
        if item["status"] != "pending" and not item["evidence_id"]:
            errs.append("%s: status %r requires an evidence_id" % (path, item["status"]))
        if item["status"] == "fulfilled" and not item["fulfilled_at"]:
            errs.append("%s: fulfilled item requires fulfilled_at" % path)
        if item["status"] != "fulfilled" and item["fulfilled_at"]:
            errs.append("%s: only a fulfilled item may carry fulfilled_at" % path)
        try:
            parse_ts(item["requested_at"], "%s.requested_at" % path)
            if item["fulfilled_at"] is not None:
                parse_ts(item["fulfilled_at"], "%s.fulfilled_at" % path)
        except UsageError as exc:
            errs.append(str(exc))
    if len(set(request_ids)) != len(request_ids):
        errs.append("$.requested_items: duplicate request_id")
    stray = [rid for rid in doc["pending_request_ids"] if rid not in request_ids]
    if stray:
        errs.append("$.pending_request_ids: unknown request ids %s" % stray)
    if len(set(doc["pending_request_ids"])) != len(doc["pending_request_ids"]):
        errs.append("$.pending_request_ids: duplicate request id")

    # Section 1: FB, IG and SMS references share one lock, so the reference set is
    # 1..n and the origin must be one of its members.
    references = doc["channel_references"]
    pairs = [(ref["channel"], ref["conversation_id"]) for ref in references]
    if len(set(pairs)) != len(pairs):
        errs.append("$.channel_references: duplicate channel reference")
    if (doc["originating_channel"], doc["originating_conversation_id"]) not in pairs:
        errs.append(
            "$.channel_references: must contain the originating %s reference %r"
            % (doc["originating_channel"], doc["originating_conversation_id"])
        )

    budget = doc["capture_budget"]
    if budget["reminders_used"] > budget["max_reminders"]:
        errs.append("$.capture_budget: reminders_used exceeds the capture budget")
    if budget["sms_email_asks_used"] > budget["max_sms_email_asks"]:
        errs.append("$.capture_budget: sms_email_asks_used exceeds the capture budget")
    if budget["reminders_used"] < doc["reminders_accepted"]:
        errs.append("$.capture_budget: reminders_used cannot be below reminders_accepted")

    # Section 8: three distinct slots, in order.
    slots = doc["reminder_slots"]
    numbers = [slot["slot"] for slot in slots]
    if len(set(numbers)) != len(numbers):
        errs.append("$.reminder_slots: duplicate slot number %s" % sorted(numbers))
    if numbers != sorted(numbers):
        errs.append("$.reminder_slots: slot numbers must be listed in order")
    dues = []
    for index, slot in enumerate(slots):
        path = "$.reminder_slots[%d]" % index
        try:
            dues.append((parse_ts(slot["due_at"], "%s.due_at" % path), index))
        except UsageError as exc:
            errs.append(str(exc))
    if len(dues) == len(slots):
        for earlier, later in zip(dues, dues[1:]):
            if later[0] <= earlier[0]:
                errs.append("$.reminder_slots: due_at must increase across slots")

    if doc["t0"] is not None:
        try:
            parse_ts(doc["t0"], "t0")
        except UsageError as exc:
            errs.append(str(exc))
    return errs


def semantic_outbound(doc):
    errs = []
    not_before = parse_ts(doc["not_before"], "not_before")
    if doc["expires_at"] is not None:
        expires = parse_ts(doc["expires_at"], "expires_at")
        if expires <= not_before:
            errs.append("$.expires_at: must be later than not_before")
    if doc["status"] in {"accepted", "sent", "delivered"}:
        if not doc["attempts"]:
            errs.append("$.attempts: an accepted or later status requires at least one attempt")
        if not doc["receipt"]["evidence_id"]:
            errs.append("$.receipt.evidence_id: an accepted or later status requires a receipt")
    if doc["status"] == "failed_after_acceptance" and not doc["attempts"]:
        errs.append("$.attempts: failed_after_acceptance requires the attempt that was accepted")
    if doc["scope"] == "public_placement":
        gate = doc["dispatch_gate"]
        if gate is not None:
            parse_ts(gate["checked_at"], "dispatch_gate.checked_at")
    else:
        gate = doc["dispatch_gate"]
        if gate is not None:
            parse_ts(gate["checked_at"], "dispatch_gate.checked_at")
    return errs


def semantic_approval(doc):
    errs = []
    starts = parse_ts(doc["campaign_window"]["starts_on"] + "T00:00:00Z", "campaign_window.starts_on")
    ends = parse_ts(doc["campaign_window"]["ends_on"] + "T00:00:00Z", "campaign_window.ends_on")
    span_days = (ends - starts).days + 1
    if span_days != 30:
        errs.append("$.campaign_window: joined campaign must span 30 days, got %d" % span_days)
    placement_ids = [p["placement_id"] for p in doc["placements"]]
    if len(set(placement_ids)) != len(placement_ids):
        errs.append("$.placements: duplicate placement_id")
    if doc["status"] in {"APPROVED", "PARTIAL_INVALIDATED"} and not doc["placements"]:
        errs.append("$.placements: an approved manifest binds at least one placement")
    for earlier, later in zip(doc["placements"], doc["placements"][1:]):
        if later["scheduled_at"] < earlier["scheduled_at"]:
            errs.append("$.placements: placement slots must be listed in schedule order")
        if later["placement_id"] == earlier["placement_id"]:
            errs.append("$.placements: duplicate placement slot %r" % later["placement_id"])
    for placement in doc["placements"]:
        try:
            parse_ts(placement["scheduled_at"], "placements[%s].scheduled_at" % placement["placement_id"])
        except UsageError as exc:
            errs.append(str(exc))
    invalid = [p for p in doc["placements"] if p["approval_status"] == "INVALIDATED"]
    if doc["status"] == "APPROVED" and invalid:
        errs.append("$.placements: an APPROVED manifest cannot contain invalidated placements")
    if doc["status"] == "PARTIAL_INVALIDATED" and not invalid:
        errs.append("$.status: PARTIAL_INVALIDATED requires at least one invalidated placement")
    if doc["status"] in {"APPROVED", "PARTIAL_INVALIDATED"}:
        if not doc["approved_by"]:
            errs.append("$.approved_by: an approved manifest requires an approver")
        if not doc["approved_at"]:
            errs.append("$.approved_at: an approved manifest requires an approval time")
    return errs


def semantic_readiness(doc):
    errs = []
    previous = None
    for key in READINESS_KEYS:
        claim = doc["claims"][key]
        if claim["status"] == "READY":
            if not claim["evidence_timestamp"]:
                errs.append("$.claims.%s: READY requires an evidence_timestamp" % key)
            if not claim["evidence_ids"]:
                errs.append("$.claims.%s: READY requires at least one evidence_id" % key)
        if claim["status"] == "INVALIDATED":
            if claim["evidence_timestamp"] is not None:
                errs.append("$.claims.%s: an INVALIDATED claim keeps no evidence time" % key)
            if claim["evidence_ids"]:
                errs.append("$.claims.%s: an INVALIDATED claim keeps no evidence ids" % key)
        if claim["evidence_timestamp"] is not None:
            stamp = parse_ts(claim["evidence_timestamp"], "claims.%s.evidence_timestamp" % key)
            if previous is not None and stamp < previous:
                errs.append(
                    "$.claims.%s: evidence time predates the earlier stage (%s)" % (key, previous.isoformat())
                )
            previous = stamp

    invalidated = doc["invalidated"]
    if invalidated is None:
        for key in READINESS_KEYS:
            if doc["claims"][key]["status"] == "INVALIDATED":
                errs.append("$.claims.%s: INVALIDATED claim requires a matching invalidation record" % key)
    else:
        parse_ts(invalidated["at"], "invalidated.at")
        for key in invalidated["keys"]:
            if doc["claims"][key]["status"] != "INVALIDATED":
                errs.append(
                    "$.claims.%s: named in invalidated.keys but status is %r"
                    % (key, doc["claims"][key]["status"])
                )
        for key in READINESS_KEYS:
            if doc["claims"][key]["status"] == "INVALIDATED" and key not in invalidated["keys"]:
                errs.append("$.invalidated.keys: missing %r" % key)
    return errs


def semantic_action(doc):
    errs = []
    state = doc["state"]
    dispatch = doc["dispatch_receipt"]
    ack = doc["ack_receipt"]
    completion = doc["completion_receipt"]

    if state in {"not_requested", "queued"} and dispatch is not None:
        errs.append("$.dispatch_receipt: %r state cannot carry a dispatch receipt" % state)
    if state in {"dispatched", "acknowledged", "completed"} and dispatch is None:
        errs.append("$.dispatch_receipt: %r state requires a dispatch receipt" % state)
    if state in {"not_requested", "queued", "dispatched"} and ack is not None:
        errs.append("$.ack_receipt: %r state cannot carry an acknowledgement" % state)
    if state in {"acknowledged", "completed"} and ack is None:
        errs.append("$.ack_receipt: %r state requires an acknowledgement" % state)
    if state == "acknowledged" and completion is not None:
        errs.append("$.completion_receipt: an acknowledged action is not completed")
    if state == "completed":
        if completion is None:
            errs.append("$.completion_receipt: completed requires a completion receipt")
        else:
            if dispatch is None or ack is None:
                errs.append("$.state: completed requires dispatch, acknowledgement and completion")
            else:
                if completion["evidence_id"] == ack["evidence_id"]:
                    errs.append("$.completion_receipt: completion must not reuse the ACK evidence")
                completed = parse_ts(completion["completed_at"], "completion_receipt.completed_at")
                acknowledged = parse_ts(ack["acknowledged_at"], "ack_receipt.acknowledged_at")
                if completed <= acknowledged:
                    errs.append("$.completion_receipt: completion must be later than the ACK")
                if doc["stop_requested"] and completion["kind"] != "STOP_COMPLETED_FINALIZER":
                    errs.append(
                        "$.completion_receipt.kind: a stop must close on the finalizer receipt, got %r"
                        % completion["kind"]
                    )
    if state not in {"acknowledged", "completed"} and completion is not None:
        errs.append("$.completion_receipt: only a completed action carries a completion receipt")
    return errs


def semantic_lifecycle(doc):
    """Section 9: CLOSED is carried at one applied event revision by one controller."""
    errs = []
    state = doc["state"]
    try:
        parse_ts(doc["updated_at"], "updated_at")
    except UsageError as exc:
        errs.append(str(exc))

    if state == "CLOSING" and not doc["stop_action_id"]:
        errs.append("$.stop_action_id: a CLOSING loop keeps the stop action")
    if state == "CLOSED":
        if not doc["stop_action_id"]:
            errs.append("$.stop_action_id: CLOSED requires the stop action")
        if not doc["finalizer_evidence_id"]:
            errs.append("$.finalizer_evidence_id: CLOSED requires the finalizer terminal receipt")
        if doc["closed_event_revision"] is None:
            errs.append("$.closed_event_revision: CLOSED must name the applied event revision")
        elif doc["closed_event_revision"] != doc["applied_event_revision"]:
            errs.append(
                "$.closed_event_revision: the CLOSED update is carried at one applied event "
                "revision (%r != %r)" % (doc["closed_event_revision"], doc["applied_event_revision"])
            )
    else:
        if doc["closed_event_revision"] is not None:
            errs.append("$.closed_event_revision: only CLOSED carries a closed event revision")
        if doc["finalizer_evidence_id"] is not None:
            errs.append("$.finalizer_evidence_id: only CLOSED carries the finalizer receipt")
    return errs


def semantic_compat(doc):
    """Section 10: rollback compares the revision the upgrade wrote."""
    errs = []
    try:
        parse_ts(doc["updated_at"], "updated_at")
    except UsageError as exc:
        errs.append(str(exc))

    missing = [name for name in NEVER_ROLLED_BACK if name not in doc["never_rolled_back"]]
    if missing:
        errs.append("$.never_rolled_back: missing %s" % missing)

    rollback = doc["rollback"]
    target = rollback["target_revision"]
    if rollback["mode"] == "ROLLBACK":
        if target is None:
            errs.append("$.rollback.target_revision: a rollback names the revision it returns to")
        elif target > doc["upgrade_wrote_revision"]:
            errs.append(
                "$.rollback.target_revision: %d is a newer client revision than the %d the "
                "upgrade wrote; that conflict is repaired forward, never rolled back"
                % (target, doc["upgrade_wrote_revision"])
            )
        if doc["client_revision"] > doc["upgrade_wrote_revision"]:
            errs.append(
                "$.rollback.mode: client revision %d is newer than the revision the upgrade "
                "wrote (%d), so this is a forward repair, not a rollback"
                % (doc["client_revision"], doc["upgrade_wrote_revision"])
            )
    elif rollback["mode"] == "NONE" and target is not None:
        errs.append("$.rollback.target_revision: mode NONE names no target revision")
    return errs


def semantic_reconciliation(doc):
    """Section 1: verified identifiers, supported merges, never by name or across tenants."""
    errs = []
    try:
        parse_ts(doc["updated_at"], "updated_at")
    except UsageError as exc:
        errs.append(str(exc))
    for index, ident in enumerate(doc["verified_identifiers"]):
        path = "$.verified_identifiers[%d]" % index
        try:
            parse_ts(ident["verified_at"], "%s.verified_at" % path)
        except UsageError as exc:
            errs.append(str(exc))
        if ident["tenant_id"] != doc["tenant_id"]:
            errs.append("%s: an identifier from tenant %r is not this tenant's to reconcile" % (path, ident["tenant_id"]))

    merge = doc["merge"]
    if merge["basis"] == "DISPLAY_NAME":
        errs.append("$.merge.basis: never merge by display name")
    if merge["basis"] == "CROSS_TENANT":
        errs.append("$.merge.basis: never merge across tenants")
    if merge["mode"] == "MERGE":
        if merge["basis"] != "VERIFIED_IDENTIFIER":
            errs.append("$.merge.basis: a merge requires a verified identifier")
        if not merge["target_canonical_contact_id"]:
            errs.append("$.merge.target_canonical_contact_id: a merge names its target")
        if merge["target_canonical_contact_id"] in merge["source_canonical_contact_ids"]:
            errs.append("$.merge.source_canonical_contact_ids: a contact is not its own source")
    if doc["preserved"]["suppression_kept"] != "STRICTER":
        errs.append("$.preserved.suppression_kept: preserve the stricter suppression")
    return errs


SEMANTIC = {
    "collection": semantic_collection,
    "outbound": semantic_outbound,
    "approval": semantic_approval,
    "readiness": semantic_readiness,
    "action": semantic_action,
    "lifecycle": semantic_lifecycle,
    "compatibility": semantic_compat,
    "reconciliation": semantic_reconciliation,
}


def check_document(kind, doc):
    errs = validate_schema(load_schema(kind), doc)
    if not errs:
        errs.extend(SEMANTIC[kind](doc))
    return errs


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


LEDGER_VERSION = 2

# What makes two public placements the SAME placement. A new approved cycle, a
# new account binding or a new content revision is a DIFFERENT placement and must
# stay dispatchable; the same one retried must collapse. ``approval_revision`` is
# deliberately absent: re-approving unchanged content is freshness (enforced by
# the gate), not a new placement, so it must not mint a second post.
PLACEMENT_IDENTITY_FIELDS = (
    "campaign_cycle_id",
    "placement_id",
    "account_id",
    "account_binding_revision",
    "content_revision",
)


def _legacy_idempotency_key(doc):
    return "%s::%s" % (doc["tenant_id"], doc["logical_intent_key"])


def idempotency_key(doc):
    """Identity of the logical intent. Two dispatches sharing it are one action.

    A public placement is identified by its placement identity, not by a free-text
    key the caller happens to reuse: two placements in different cycles, or bound
    to a different account or content revision, never share an identity. The
    caller's ``logical_intent_key`` is still part of the key, so two different
    intents on ONE placement (a scheduled post and its reveal) stay distinct.
    """
    if doc.get("scope") != "public_placement":
        return _legacy_idempotency_key(doc)
    parts = [doc["tenant_id"]]
    parts.extend(doc[field] for field in PLACEMENT_IDENTITY_FIELDS)
    parts.append(doc["logical_intent_key"])
    return "::".join(parts)


def _migrate_v1(ledger):
    """One migration: version 1 keys were tenant::logical_intent_key.

    A version 1 entry never recorded which placement it belonged to, so its key
    cannot be recomputed without guessing. Rewriting it would silently un-collapse
    an in-flight action and could send it twice. The entries move to
    ``legacy_actions`` untouched and are still consulted by dispatch, so a retry
    against a version 1 ledger keeps deduping.
    """
    return {
        "version": LEDGER_VERSION,
        "actions": {},
        "legacy_actions": ledger["actions"],
    }


def load_ledger(path):
    if not os.path.exists(path):
        return {"version": LEDGER_VERSION, "actions": {}, "legacy_actions": {}}
    ledger = load_json(path)
    version = ledger.get("version")
    if not isinstance(ledger.get("actions"), dict):
        raise UsageError("ledger %s has no actions map" % path)
    # T-39 compat_guard: a ledger written by a newer build is refused by name
    # (no silent downgrade), the same gate every versioned on-disk record gets.
    try:
        compat_guard.assert_compatible(ledger, known_version=LEDGER_VERSION)
    except compat_guard.CompatError as exc:
        raise UsageError(
            "ledger %s is version %r; this build reads version 1 or %d"
            % (path, version, LEDGER_VERSION)) from exc
    if version == 1:
        return _migrate_v1(ledger)
    if version != LEDGER_VERSION:
        raise UsageError(
            "ledger %s is version %r; this build reads version 1 or %d"
            % (path, version, LEDGER_VERSION))
    ledger.setdefault("legacy_actions", {})
    return ledger


def save_ledger(path, ledger):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=directory, prefix=".pb-ledger-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(ledger, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def emit(payload):
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload.get("ok") else 1


def cmd_validate(args):
    doc = load_json(args.file)
    errs = check_document(args.kind, doc)
    result = {"ok": not errs, "command": "validate", "kind": args.kind, "file": args.file, "errors": errs}

    if not errs and args.kind == "outbound" and args.manifest:
        manifest = load_json(args.manifest)
        manifest_errs = check_document("approval", manifest)
        if manifest_errs:
            result["ok"] = False
            result["errors"] = ["approval manifest: " + err for err in manifest_errs]
        else:
            revision = doc.get("approval_revision")
            if revision is not None and revision != manifest["revision"]:
                result["ok"] = False
                result["errors"] = [
                    "$.approval_revision: %r does not match manifest revision %r"
                    % (revision, manifest["revision"])
                ]
    return emit(result)


def cmd_transition(args):
    before = load_json(args.before)
    after = load_json(args.after)
    errs = check_document(args.kind, before)
    errs += ["after " + err for err in check_document(args.kind, after)]

    if not errs and args.kind == "collection":
        errs.extend(collection_transition_errors(before, after))
    elif not errs and args.kind == "action":
        errs.extend(action_transition_errors(before, after))
    elif not errs and args.kind == "lifecycle":
        errs.extend(lifecycle_transition_errors(before, after))
    elif not errs:
        raise UsageError("transition supports kind collection, action or lifecycle, got %r" % args.kind)

    return emit(
        {
            "ok": not errs,
            "command": "transition",
            "kind": args.kind,
            "before": args.before,
            "after": args.after,
            "errors": errs,
        }
    )


def collection_transition_errors(before, after):
    errs = []
    for field in ("tenant_id", "canonical_contact_id", "collection_sequence_id"):
        if before[field] != after[field]:
            errs.append("$.%s: collection identity cannot change (%r -> %r)" % (field, before[field], after[field]))
    if after["state_version"] <= before["state_version"]:
        errs.append("$.state_version: must increase (%d -> %d)" % (before["state_version"], after["state_version"]))
    if after["ownership_fence"] < before["ownership_fence"]:
        errs.append("$.ownership_fence: must not decrease (%d -> %d)" % (before["ownership_fence"], after["ownership_fence"]))

    before_ids = {item["request_id"] for item in before["requested_items"]}
    after_ids = {item["request_id"] for item in after["requested_items"]}
    lost = sorted(before_ids - after_ids)
    if lost:
        errs.append("$.requested_items: partial capture records cannot be dropped %s" % lost)

    new_ids = sorted(after_ids - before_ids)
    if new_ids and (before["state"] in TERMINAL_COLLECTION or after["state"] in TERMINAL_COLLECTION):
        errs.append("$.requested_items: new request %s cannot restart final or declined capture" % new_ids)
    if before["state"] in TERMINAL_COLLECTION and after["state"] not in TERMINAL_COLLECTION:
        errs.append("$.state: terminal collection %r cannot be restarted as %r" % (before["state"], after["state"]))

    if before["final_action_id"] and before["final_action_id"] != after["final_action_id"]:
        errs.append("$.final_action_id: the reserved final action cannot be replaced")

    before_ask = before["sms_email_ask"]["logical_action_id"]
    after_ask = after["sms_email_ask"]["logical_action_id"]
    if before_ask and after_ask and before_ask != after_ask:
        errs.append("$.sms_email_ask.logical_action_id: a corrected number is not a new ask")
    return errs


def action_transition_errors(before, after):
    errs = []
    if before["action_id"] != after["action_id"]:
        errs.append("$.action_id: identity cannot change")
    if after["revision"] <= before["revision"]:
        errs.append("$.revision: must increase (%d -> %d)" % (before["revision"], after["revision"]))
    old, new = before["state"], after["state"]
    if old == new:
        return errs
    if old in ACTION_TERMINAL:
        errs.append("$.state: %r is terminal and cannot move to %r" % (old, new))
        return errs
    if new in ACTION_SIDEWAYS:
        return errs
    if old == "unknown":
        if new not in {"dispatched", "acknowledged", "completed", "failed", "canceled"}:
            errs.append("$.state: an unknown action reconciles to %r" % new)
        return errs
    if old in ACTION_LADDER and new in ACTION_LADDER:
        if ACTION_LADDER.index(new) < ACTION_LADDER.index(old):
            errs.append("$.state: cannot move backwards %r -> %r" % (old, new))
        return errs
    errs.append("$.state: unsupported transition %r -> %r" % (old, new))
    return errs


def lifecycle_transition_errors(before, after):
    """Section 9: the loop ladder, one controller, one applied event revision."""
    errs = []
    for field in ("tenant_id", "loop_id", "controller_id"):
        if before[field] != after[field]:
            errs.append(
                "$.%s: identity cannot change (%r -> %r); a crashed controller is never recreated"
                % (field, before[field], after[field])
            )
    if after["controller_generation"] < before["controller_generation"]:
        errs.append("$.controller_generation: must not decrease")
    if after["applied_event_revision"] <= before["applied_event_revision"]:
        errs.append(
            "$.applied_event_revision: must increase (%d -> %d)"
            % (before["applied_event_revision"], after["applied_event_revision"])
        )

    old, new = before["state"], after["state"]
    if old == new:
        return errs
    if new not in LIFECYCLE_EDGES[old]:
        errs.append("$.state: unsupported transition %r -> %r" % (old, new))
        return errs
    if new == "CLOSED":
        if after["closed_event_revision"] != after["applied_event_revision"]:
            errs.append(
                "$.closed_event_revision: the CLOSED update is carried at one applied event revision"
            )
        elif after["closed_event_revision"] <= before["applied_event_revision"]:
            errs.append(
                "$.closed_event_revision: the CLOSED update must be a new applied event revision"
            )
    return errs


def _is_blank_mark(character):
    """True for a character an id can carry while carrying no id.

    ``character.isspace()`` is exactly the set ``str.strip()`` removes (verified
    over the whole code space, 29 characters on both sides), so the whitespace
    half of the rule is unchanged. Category Cf is what the previous fix missed:
    zero width space (U+200B), the byte order mark (U+FEFF) and the other 168
    format marks are not whitespace, are invisible, and must not make a blank id
    look attached.
    """
    return character.isspace() or unicodedata.category(character) == "Cf"


def normalise_evidence_id(value):
    """Trim an evidence id and treat a blank one as absent.

    None and a blank id both mean "no evidence is attached", so the gate refuses
    on either. Blank covers whitespace-only and format-mark-only values: a single
    U+200B or U+FEFF carries no information and was still reaching the allow
    path. Only the two ends are trimmed, exactly as ``str.strip()`` always did for
    whitespace: the normaliser removes decoration from an id, it never rewrites
    the id itself, so a real id dispatches, a padded real id dispatches, and a
    format mark buried inside an id stays part of that literal id.
    ponytail: end-trim only; a format mark inside an id is left in place rather
    than silently retargeting the reference. Add a byte-exact check where the id
    is resolved against the evidence store if internal marks must refuse.
    Non-strings are handed back untouched: the schema layer names those
    INVALID_GATE and this presence check must not swallow them into a refusal.
    """
    if isinstance(value, str):
        start, end = 0, len(value)
        while start < end and _is_blank_mark(value[start]):
            start += 1
        while end > start and _is_blank_mark(value[end - 1]):
            end -= 1
        return value[start:end] or None
    return value

def cmd_dispatch(args):
    action = load_json(args.action)
    errs = check_document("outbound", action)
    if errs:
        return emit({"ok": False, "command": "dispatch", "decision": "INVALID", "errors": errs})

    gate = load_json(args.gate)
    gate_errs = validate_schema(branch_gate_schema(action["scope"]), gate, "$gate")
    if gate_errs:
        return emit(
            {"ok": False, "command": "dispatch", "decision": "INVALID_GATE", "errors": gate_errs}
        )

    now = parse_ts(args.now, "now") if args.now else parse_ts(now_utc(), "now")
    gate_checked = parse_ts(gate["checked_at"], "gate.checked_at")
    key = idempotency_key(action)
    ledger = load_ledger(args.ledger)
    # A version 1 entry predates placement identity. It is still the same action,
    # so a retry must find it and collapse; it is written back where it lives.
    bucket = ledger["actions"]
    existing = bucket.get(key)
    # Every scope, not only public placements: for a person_directed action the
    # old key is still the live key, so a fallback guarded on scope would look up
    # nothing and release a second send of an action already recorded as sent.
    if existing is None:
        legacy = ledger.get("legacy_actions") or {}
        legacy_key = _legacy_idempotency_key(action)
        if legacy_key in legacy:
            bucket, key, existing = legacy, legacy_key, legacy[legacy_key]

    def refuse(decision, reason, ok=False):
        return emit(
            {
                "ok": ok,
                "command": "dispatch",
                "decision": decision,
                "reason": reason,
                "action_id": action["action_id"],
                "idempotency_key": key,
                "attempts": len(existing["attempts"]) if existing else 0,
                "errors": [],
            }
        )

    # Idempotency first: a duplicate intent is collapsed before any gate work,
    # because nothing will be sent.
    if existing and existing["status"] in COLLAPSE_STATUSES:
        payload = {
            "ok": True,
            "command": "dispatch",
            "decision": "COLLAPSED",
            "reason": "DUPLICATE_LOGICAL_INTENT",
            "action_id": existing["action_id"],
            "idempotency_key": key,
            "attempts": len(existing["attempts"]),
            "errors": [],
        }
        return emit(payload)
    if existing and existing["status"] == "unknown":
        return refuse("RECONCILE_UNKNOWN", "UNKNOWN_EFFECT_MAY_NOT_BE_REPLAYED")
    if existing and existing["status"] == "canceled":
        return refuse("CANCELED", "ACTION_WAS_CANCELED")
    if existing and existing["status"] not in RETRYABLE_STATUSES | {"dispatching"}:
        return refuse("INVALID", "ACTION_STATUS_%s_NOT_DISPATCHABLE" % existing["status"].upper())

    # Section 1: a contact is reconciled and dispatched inside one tenant. The same
    # canonical_contact_id under another tenant is a different person's record.
    contact = action.get("canonical_contact_id")
    if contact:
        holders = sorted(
            {
                other["tenant_id"]
                for other in ledger["actions"].values()
                if other.get("canonical_contact_id") == contact
            }
            - {action["tenant_id"]}
        )
        if holders:
            return refuse(
                "QUARANTINED",
                "CONTACT_%s_ALREADY_BOUND_TO_TENANT_%s" % (contact.upper(), ",".join(holders).upper()),
            )

    if gate["decision"] != "ALLOW":
        return refuse(gate["decision"], "GATE_DECISION")
    if gate["binding_revision"] != action["account_binding_revision"]:
        return refuse("QUARANTINED", "BINDING_CHANGED")
    if gate["owner_fence"] != action["ownership_fence"]:
        return refuse("QUARANTINED", "FENCE_STALE")
    if gate_checked > now:
        return refuse("STALE_GATE", "GATE_DATED_IN_FUTURE")
    age_seconds = (now - gate_checked).total_seconds()
    if age_seconds > args.max_gate_age_seconds:
        return refuse("STALE_GATE", "GATE_EXPIRED_%ds" % int(age_seconds))

    if existing and existing["attempts"]:
        last = parse_ts(existing["attempts"][-1]["gate_checked_at"], "attempt.gate_checked_at")
        if gate_checked <= last:
            return refuse("STALE_GATE", "RETRY_GATE_NOT_FRESH")

    if action["scope"] == "public_placement" and gate["approval_revision"] != action["approval_revision"]:
        return refuse("STALE_APPROVAL", "GATE_CHECKED_OTHER_APPROVAL_REVISION")

    approval_errs = approval_errors(action, args.manifest)
    if approval_errs:
        named = sorted({err.split(":")[0][2:] for err in approval_errs if err.startswith("$.")})
        payload = {
            "ok": False,
            "command": "dispatch",
            "decision": "STALE_APPROVAL",
            "reason": "APPROVAL_NOT_CURRENT" + (":" + ",".join(named) if named else ""),
            "action_id": action["action_id"],
            "idempotency_key": key,
            "attempts": len(existing["attempts"]) if existing else 0,
            "errors": approval_errs,
        }
        return emit(payload)

    # Section 3 common checks: current authority and lifecycle, exact content and
    # asset, scheduling and quiet rules. The return carries binding, policy, fence.
    for gate_field, action_field, reason in GATE_COMMON_CHECKS:
        if gate[gate_field] != action[action_field]:
            return refuse("QUARANTINED", reason)
    if gate["lifecycle_state"] not in {"RUNNING", "PAUSED_RESUMABLE"}:
        return refuse("SUPPRESSED", "LIFECYCLE_%s" % gate["lifecycle_state"])
    if gate["quiet_rule_status"] != "CLEAR":
        return refuse("SUPPRESSED", "QUIET_RULE_%s" % gate["quiet_rule_status"])

    if action["scope"] == "public_placement":
        if gate["publication_paused"]:
            return refuse("SUPPRESSED", "PUBLICATION_PAUSED")
        if gate["platform_publishing_permission"] is not True:
            return refuse("SUPPRESSED", "NO_PLATFORM_PUBLISHING_PERMISSION")
        if action["purpose"] in {"REVEAL_COMMENT", "BONUS_COMMENT"}:
            if gate["parent_post_verified"] is not True:
                return refuse("PARENT_UNVERIFIED", "REVEAL_PARENT_NOT_VERIFIED")
            if gate["reveal_order_verified"] is not True:
                return refuse("SUPPRESSED", "REVEAL_ORDER_NOT_VERIFIED")
    else:
        if normalise_evidence_id(gate["trusted_contact_mapping_evidence_id"]) is None:
            return refuse("SUPPRESSED", "NO_TRUSTED_CONTACT_MAPPING")
        if action["purpose"] == "COMMENT_PRIVATE_OPENER" and gate["inbound_dm_window"]:
            return refuse("SUPPRESSED", "COMMENT_OPENER_IS_NOT_AN_INBOUND_DM_WINDOW")
        if action["channel"] in DM_CHANNELS and not gate["inbound_dm_window"]:
            return refuse("SUPPRESSED", "NO_INBOUND_DM_WINDOW")
        records = [r for r in gate["eligibility_evidence"] if r["purpose"] == action["purpose"]]
        stale_basis = {"OUTBOUND_MESSAGE", "CROSS_CHANNEL_MESSAGE"}
        # Outbound and cross-channel messages do not refresh FB/IG eligibility.
        usable = [r for r in records if r["evidence_id"] and r["basis"] not in stale_basis]
        if not usable and not gate["consent_evidence_id"]:
            if any(r["basis"] in stale_basis for r in records) and action["channel"] in DM_CHANNELS:
                return refuse("SUPPRESSED", "ELIGIBILITY_NOT_REFRESHED_BY_OUTBOUND")
            return refuse("SUPPRESSED", "NO_DELIVERY_BASIS")

    attempt_no = (len(existing["attempts"]) if existing else 0) + 1
    attempt = {
        "attempt_no": attempt_no,
        "attempt_id": "%s#%d" % (action["action_id"], attempt_no),
        "gate_checked_at": gate["checked_at"],
        "binding_revision": gate["binding_revision"],
        "owner_fence": gate["owner_fence"],
        "recorded_at": args.now or now_utc(),
        "decision": "ALLOW",
    }
    entry = existing or {
        "action_id": action["action_id"],
        "tenant_id": action["tenant_id"],
        "logical_intent_key": action["logical_intent_key"],
        "canonical_contact_id": action.get("canonical_contact_id"),
        "scope": action["scope"],
        "purpose": action["purpose"],
        "attempts": [],
        "receipts": [],
    }
    entry["canonical_contact_id"] = action.get("canonical_contact_id")
    entry["attempts"].append(attempt)
    entry["status"] = "dispatching"
    entry["updated_at"] = args.now or now_utc()
    bucket[key] = entry
    save_ledger(args.ledger, ledger)

    return emit(
        {
            "ok": True,
            "command": "dispatch",
            "decision": "DISPATCHED",
            "reason": "GATE_ALLOWED",
            "action_id": action["action_id"],
            "attempt": attempt_no,
            "attempt_id": attempt["attempt_id"],
            "idempotency_key": key,
            "attempts": len(entry["attempts"]),
            "errors": [],
        }
    )


def approval_errors(action, manifest_path):
    """Check the action against the current approval manifest."""
    if action["scope"] == "public_placement":
        manifest_id = action["approval_manifest_id"]
        revision = action["approval_revision"]
        placement_id = action["placement_id"]
        cycle_id = action["campaign_cycle_id"]
    else:
        precondition = action["precondition"]
        if not precondition["approval_manifest_id"]:
            return []
        manifest_id = precondition["approval_manifest_id"]
        revision = precondition["approval_revision"]
        placement_id = None
        cycle_id = None

    if not manifest_path:
        return ["approval manifest required for a placement-bound action"]
    manifest = load_json(manifest_path)
    errs = check_document("approval", manifest)
    if errs:
        return ["approval manifest: " + err for err in errs]

    problems = []
    if manifest["manifest_id"] != manifest_id:
        problems.append("$.approval_manifest_id: %r is not the loaded manifest %r" % (manifest_id, manifest["manifest_id"]))
    if manifest["tenant_id"] != action["tenant_id"]:
        problems.append("$.tenant_id: manifest belongs to %r" % manifest["tenant_id"])
    if cycle_id is not None and manifest["campaign_cycle_id"] != cycle_id:
        problems.append("$.campaign_cycle_id: manifest cycle is %r" % manifest["campaign_cycle_id"])
    if revision != manifest["revision"]:
        problems.append("$.approval_revision: %r is stale, manifest is at %r" % (revision, manifest["revision"]))
    if manifest["status"] not in {"APPROVED", "PARTIAL_INVALIDATED"}:
        problems.append("$.status: manifest is %r" % manifest["status"])

    if placement_id is not None:
        match = [p for p in manifest["placements"] if p["placement_id"] == placement_id]
        if not match:
            problems.append("$.placement_id: %r is not in the manifest" % placement_id)
        else:
            placement = match[0]
            if placement["approval_status"] != "APPROVED":
                problems.append("$.placement_id: placement approval is %r" % placement["approval_status"])
            if placement["account_id"] != action["account_id"]:
                problems.append("$.account_id: placement is bound to %r" % placement["account_id"])
            if placement["account_binding_revision"] != action["account_binding_revision"]:
                problems.append(
                    "$.account_binding_revision: placement is bound at %r"
                    % placement["account_binding_revision"]
                )
            if placement["content_revision"] != action["content_revision"]:
                problems.append("$.content_revision: placement approved %r" % placement["content_revision"])
            for field in PLACEMENT_BOUND_FIELDS:
                approved = placement[field]
                attempted = action[field]
                if isinstance(approved, list):
                    approved, attempted = sorted(approved), sorted(attempted or [])
                if approved != attempted:
                    problems.append(
                        "$.%s: diverges from the approved placement %r (approved %r)"
                        % (field, attempted, approved)
                    )
    return problems


def cmd_receipt(args):
    if args.status not in RECEIPT_STATUSES:
        raise UsageError("status must be one of %s" % RECEIPT_STATUSES)
    ledger = load_ledger(args.ledger)
    entry = ledger["actions"].get(args.key)
    if entry is None:
        entry = (ledger.get("legacy_actions") or {}).get(args.key)
    if entry is None:
        raise UsageError("no ledger entry for key %r" % args.key)
    stamp = args.now or now_utc()
    parse_ts(stamp, "now")
    receipt = {
        "status": args.status,
        "recorded_at": stamp,
        "provider_object_id": args.provider_object_id,
        "evidence_id": args.evidence_id,
    }
    entry.setdefault("receipts", []).append(receipt)
    entry["status"] = args.status
    entry["updated_at"] = stamp
    save_ledger(args.ledger, ledger)
    return emit(
        {
            "ok": True,
            "command": "receipt",
            "key": args.key,
            "status": args.status,
            "attempts": len(entry["attempts"]),
            "errors": [],
        }
    )


# --------------------------------------------------------------------------
# T-13 direct original fulfillment (R-10, R-12; C-13, C-F04, C-F07, C-F09)
# --------------------------------------------------------------------------
#
# The direct original gift is the same outbound-action lifecycle this file
# already fronts (dispatch -> attempt -> receipt) with one immutable promised
# item behind it. The module (tools/direct_fulfillment.py) owns every guarantee
# -- immutable identity, at-most-once, truthful receipt, crash resume -- so
# these commands only hand it the caller's files and print its outcome.

FULFILLMENT_OK = {"sent", "already_satisfied", "resumed", "nothing_to_do"}


def _fulfillment_module():
    """Load the T-13 module that sits beside this file.

    Imported at call time on purpose: a pb_contracts caller that never fulfills
    should not pay for the T-12 store package, and a checkout without the module
    refuses the command instead of failing the whole contract CLI.
    """
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import direct_fulfillment  # late import on purpose, see docstring
    return direct_fulfillment


def _outcome_record(outcome):
    return {
        "status": outcome.status,
        "reason": outcome.reason,
        "action_id": outcome.action_id,
        "state": outcome.state,
        "item_id": outcome.item_id,
        "version": outcome.version,
        "destination": outcome.destination,
        "transport_receipt": outcome.transport_receipt,
        "delivery_status": outcome.delivery_status,
        "continuation_allowed": outcome.continuation_allowed,
        "continuation_reason": outcome.continuation_reason,
    }


def _ghl_transport(df, tenant_id):
    """Build the real GHL Conversations sender for this tenant.

    The adapter is the frozen Skill 44 public adapter; nothing here invents an
    HTTP client. The PIT is read from the environment and never printed.
    """
    repo = Path(__file__).resolve().parents[2]
    for extra in (repo / "44-convert-and-flow-operator" / "tools" / "engine",
                  repo / "06-ghl-install-pages" / "tools"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    import ghl_public_client  # noqa: E402  (late: only for --transport ghl)
    from cli_anything.gohighlevel.public.auth import TenantBinding  # noqa: E402
    from cli_anything.gohighlevel.public.outbound_sender import make_sender  # noqa: E402

    env_name = "GHL_LOCATION_PIT"
    pit = os.environ.get(env_name, "")
    if not pit:
        raise df.FulfillmentError(
            f"transport_unavailable: {env_name} is not set (value never printed)")
    adapter, wire = ghl_public_client.make_adapter(str(tenant_id), pit)
    return make_sender(adapter, TenantBinding(location_id=str(tenant_id),
                                              source="pb_contracts"),
                       transport=wire, sent_index_path=None)


def _run_fulfillment(args, run):
    """Open the durable store, ledger and transport, run, close."""
    df = _fulfillment_module()
    store = df.DurableStore(args.outbox)
    ledger = df.FulfillmentLedger(args.fulfillment_ledger)
    try:
        item = df.PromisedItem(**load_json(args.item))
        basis = df.DeliveryBasis(**load_json(args.basis))
        if getattr(args, "transport", "journal") == "ghl":
            transport = _ghl_transport(df, basis.tenant_id)
        else:
            if not args.journal:
                raise df.FulfillmentError("bad_input: --journal is required"
                                          " with --transport journal")
            transport = df.JournalTransport(args.journal)
        outcome = run(df, store, ledger, transport, item, basis)
    except df.FulfillmentError as exc:
        return emit({"ok": False, "command": args.command, "reason": str(exc),
                     "errors": [str(exc)]})
    finally:
        ledger.close()
        store.close()
    payload = {"ok": outcome.status in FULFILLMENT_OK, "command": args.command}
    payload.update(_outcome_record(outcome))
    return emit(payload)


def cmd_fulfill(args):
    return _run_fulfillment(
        args,
        lambda df, store, ledger, transport, item, basis:
        df.fulfill(store, ledger, transport, item, basis, worker_id=args.worker_id),
    )


def cmd_fulfill_resume(args):
    return _run_fulfillment(
        args,
        lambda df, store, ledger, transport, item, basis:
        df.resume(store, ledger, transport, item, basis,
                  worker_id=args.worker_id, retry=args.retry),
    )


def cmd_fulfill_proof(args):
    return _run_fulfillment(
        args,
        lambda df, store, ledger, transport, item, basis:
        df.record_delivery_proof(store, item, basis, load_json(args.proof)),
    )


def cmd_fulfill_continue(args):
    return _run_fulfillment(
        args,
        lambda df, store, ledger, transport, item, basis:
        df.can_continue(store, ledger, item, basis),
    )


def cmd_fulfill_basis(args):
    """Record the durable delivery basis once; a repeat is a no-op."""
    df = _fulfillment_module()
    ledger = df.FulfillmentLedger(args.fulfillment_ledger)
    try:
        basis = df.DeliveryBasis(**load_json(args.basis))
        row = ledger.record_basis(basis)
    except df.FulfillmentError as exc:
        return emit({"ok": False, "command": args.command, "errors": [str(exc)]})
    finally:
        ledger.close()
    return emit({"ok": True, "command": "fulfill-basis", "basis": row})


def cmd_fulfill_access(args):
    """Record observed intended-reader accessibility; never inferred."""
    df = _fulfillment_module()
    ledger = df.FulfillmentLedger(args.fulfillment_ledger)
    try:
        item = df.PromisedItem(**load_json(args.item))
        basis = df.DeliveryBasis(**load_json(args.basis))
        row = ledger.record_reader_access(
            basis.tenant_id, item.item_id, item.version,
            accessible=args.accessible, evidence=args.evidence)
    except df.FulfillmentError as exc:
        return emit({"ok": False, "command": args.command, "errors": [str(exc)]})
    finally:
        ledger.close()
    return emit({"ok": True, "command": "fulfill-access", "reader_access": row})


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate one contract document")
    validate.add_argument("--kind", required=True, choices=sorted(SCHEMA_FILES))
    validate.add_argument("--file", required=True)
    validate.add_argument("--manifest", help="approval manifest for a placement-bound outbound action")
    validate.set_defaults(func=cmd_validate)

    transition = sub.add_parser("transition", help="validate a state transition")
    transition.add_argument("--kind", required=True, choices=["collection", "action", "lifecycle"])
    transition.add_argument("--before", required=True)
    transition.add_argument("--after", required=True)
    transition.set_defaults(func=cmd_transition)

    dispatch = sub.add_parser("dispatch", help="run the fresh dispatch gate and idempotency check")
    dispatch.add_argument("--action", required=True)
    dispatch.add_argument("--gate", required=True)
    dispatch.add_argument("--ledger", required=True)
    dispatch.add_argument("--manifest")
    dispatch.add_argument("--now")
    dispatch.add_argument("--max-gate-age-seconds", type=int, default=900)
    dispatch.set_defaults(func=cmd_dispatch)

    receipt = sub.add_parser("receipt", help="record a provider receipt against a ledger entry")
    receipt.add_argument("--ledger", required=True)
    receipt.add_argument("--key", required=True)
    receipt.add_argument("--status", required=True)
    receipt.add_argument("--provider-object-id", default=None)
    receipt.add_argument("--evidence-id", default=None)
    receipt.add_argument("--now")
    receipt.set_defaults(func=cmd_receipt)

    def fulfillment_paths(parser):
        parser.add_argument("--outbox", required=True, help="T-12 durable store (sqlite)")
        parser.add_argument("--fulfillment-ledger", required=True,
                            help="T-13 fulfillment ledger (sqlite)")
        parser.add_argument("--journal", default=None,
                            help="append-only transport journal (jsonl); required"
                                 " with --transport journal")
        parser.add_argument("--transport", choices=["journal", "ghl"],
                            default="journal",
                            help="journal (offline, default) or ghl (real"
                                 " Conversations sender)")
        parser.add_argument("--item", required=True, help="promised item JSON")
        parser.add_argument("--basis", required=True, help="delivery basis JSON")

    fulfill = sub.add_parser("fulfill", help="send the original promised item once")
    fulfillment_paths(fulfill)
    fulfill.add_argument("--worker-id", default="fulfillment-worker")
    fulfill.set_defaults(func=cmd_fulfill)

    fulfill_basis = sub.add_parser("fulfill-basis",
                                   help="record the durable delivery basis once")
    fulfill_basis.add_argument("--fulfillment-ledger", required=True,
                               help="T-13 fulfillment ledger (sqlite)")
    fulfill_basis.add_argument("--basis", required=True, help="delivery basis JSON")
    fulfill_basis.set_defaults(func=cmd_fulfill_basis)

    fulfill_access = sub.add_parser("fulfill-access",
                                    help="record observed intended-reader accessibility")
    fulfill_access.add_argument("--fulfillment-ledger", required=True,
                                help="T-13 fulfillment ledger (sqlite)")
    fulfill_access.add_argument("--item", required=True, help="promised item JSON")
    fulfill_access.add_argument("--basis", required=True, help="delivery basis JSON")
    fulfill_access.add_argument("--evidence", required=True,
                                help="who observed the reader reach the item, and how")
    access = fulfill_access.add_mutually_exclusive_group(required=True)
    access.add_argument("--accessible", dest="accessible", action="store_true")
    access.add_argument("--inaccessible", dest="accessible", action="store_false")
    fulfill_access.set_defaults(func=cmd_fulfill_access)

    fulfill_resume = sub.add_parser("fulfill-resume",
                                    help="reconcile a possibly-sent item without a second send")
    fulfillment_paths(fulfill_resume)
    fulfill_resume.add_argument("--worker-id", default="fulfillment-worker")
    fulfill_resume.add_argument("--retry", action="store_true",
                                help="retry under the same action identity after reconciliation "
                                     "proves the effect does not exist")
    fulfill_resume.set_defaults(func=cmd_fulfill_resume)

    fulfill_proof = sub.add_parser("fulfill-proof",
                                   help="promote accepted -> delivered from a real receipt")
    fulfillment_paths(fulfill_proof)
    fulfill_proof.add_argument("--proof", required=True, help="delivery proof JSON")
    fulfill_proof.set_defaults(func=cmd_fulfill_proof)

    fulfill_continue = sub.add_parser("fulfill-continue",
                                      help="may optional collection continue for this item?")
    fulfillment_paths(fulfill_continue)
    fulfill_continue.set_defaults(func=cmd_fulfill_continue)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UsageError as exc:
        print(json.dumps({"ok": False, "command": args.command, "errors": [str(exc)]}, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
