#!/usr/bin/env python3
"""Shared Purple Billboard contract validator.

Enforces the typed contract layer only: collection state, strict outbound
envelopes, the revisioned approval manifest, shared readiness evidence and the
control-action lifecycle. It never talks to a provider and never sends anything.

Source of truth for the rules: Purple-Billboard-Client-System-Build/
DATA-CONTRACTS.md sections 1, 2, 3, 9 and 10 (DEC-02, DEC-08).

Commands
  validate    --kind KIND --file F [--manifest M]
  transition  --kind collection|action --before B --after A
  dispatch    --action F --gate G --ledger L [--manifest M] [--now T]
              [--max-gate-age-seconds N]
  receipt     --ledger L --key K --status S [--provider-object-id X]
              [--evidence-id E] [--now T]

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
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = SKILL_ROOT / "schemas"

SCHEMA_FILES = {
    "collection": "collection-state.schema.json",
    "outbound": "outbound-action.schema.json",
    "approval": "approval-manifest.schema.json",
    "readiness": "readiness-evidence.schema.json",
    "action": "action-lifecycle.schema.json",
}

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
    if len(set(request_ids)) != len(request_ids):
        errs.append("$.requested_items: duplicate request_id")
    stray = [rid for rid in doc["pending_request_ids"] if rid not in request_ids]
    if stray:
        errs.append("$.pending_request_ids: unknown request ids %s" % stray)
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


SEMANTIC = {
    "collection": semantic_collection,
    "outbound": semantic_outbound,
    "approval": semantic_approval,
    "readiness": semantic_readiness,
    "action": semantic_action,
}


def check_document(kind, doc):
    errs = validate_schema(load_schema(kind), doc)
    if not errs:
        errs.extend(SEMANTIC[kind](doc))
    return errs


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


def idempotency_key(doc):
    return "%s::%s" % (doc["tenant_id"], doc["logical_intent_key"])


def load_ledger(path):
    if not os.path.exists(path):
        return {"version": 1, "actions": {}}
    ledger = load_json(path)
    if ledger.get("version") != 1 or not isinstance(ledger.get("actions"), dict):
        raise UsageError("ledger %s is not version 1 with an actions map" % path)
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
    elif not errs:
        raise UsageError("transition supports kind collection or action, got %r" % args.kind)

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
    existing = ledger["actions"].get(key)

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
        payload = {
            "ok": False,
            "command": "dispatch",
            "decision": "STALE_APPROVAL",
            "reason": "APPROVAL_NOT_CURRENT",
            "action_id": action["action_id"],
            "idempotency_key": key,
            "attempts": len(existing["attempts"]) if existing else 0,
            "errors": approval_errs,
        }
        return emit(payload)

    if action["scope"] == "public_placement":
        if gate["publication_paused"]:
            return refuse("SUPPRESSED", "PUBLICATION_PAUSED")
        if action["purpose"] in {"REVEAL_COMMENT", "BONUS_COMMENT"}:
            if gate["parent_post_verified"] is not True:
                return refuse("PARENT_UNVERIFIED", "REVEAL_PARENT_NOT_VERIFIED")
    else:
        if not gate["eligibility_evidence_id"] and not gate["consent_evidence_id"]:
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
        "scope": action["scope"],
        "purpose": action["purpose"],
        "attempts": [],
        "receipts": [],
    }
    entry["attempts"].append(attempt)
    entry["status"] = "dispatching"
    entry["updated_at"] = args.now or now_utc()
    ledger["actions"][key] = entry
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
    return problems


def cmd_receipt(args):
    if args.status not in RECEIPT_STATUSES:
        raise UsageError("status must be one of %s" % RECEIPT_STATUSES)
    ledger = load_ledger(args.ledger)
    entry = ledger["actions"].get(args.key)
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
    transition.add_argument("--kind", required=True, choices=["collection", "action"])
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
