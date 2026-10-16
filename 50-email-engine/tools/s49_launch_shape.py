#!/usr/bin/env python3
"""s49_launch_shape.py: the S49 Signature Launch shape, as consumed by Skill 50.

SINGLE ADJUSTMENT POINT. Every assumption the Email Engine makes about the
shape S49 publishes for a Signature Launch (the launch record, the intake
session answer ledger, the approval record, and the plan document hash
canonicalization) lives in THIS module and nowhere else. The launch intake
adapter (tools/launch_intake_adapter.py) imports the shape semantics from
here: it traverses the launch record's own top-level keys directly, but
every S49-specific meaning (which fields bind, how the plan hash
canonicalizes, what the approval gate requires, the ledger keys and the
field-state vocabulary) is defined here and nowhere else. When S49 changes
its published shape, this file is the one place that changes with it.

Sources of the shape (read in full during the S50-04 build, 2026-10-16):
  - S49 candidate a2bd2c5a95cf4a168ffab4818e67807de1d2aa3e (draft PR #2137),
    preserved on disk under rooms/S49/wave1/ in the Signature Launch
    workspace: 49-signature-funnel/schema/launch.schema.json (byte-identical
    to shared-utils/signature_launch/domain/launch.schema.json),
    49-signature-funnel/intake/launch-questions.json,
    49-signature-funnel/scripts/launch_intake.py, and
    49-signature-funnel/scripts/validate_launch_plan.py.
  - The approval discipline replicates doc 03 section 9 as S49 implemented
    it in validate_launch_plan.py (_check_approval_record), with ONE
    deliberate difference: no default 72 hour expiry. The adapter is a
    downstream consumer verifying the approval binding (hash, identity,
    scope, revocation); freshness at build time is the S49 gate's own check,
    made when the approval was recorded. Future-dated records are refused.

Deterministic, stdlib only. Nothing in this module approves anything: it
verifies records that already exist.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Vocabulary (S49 launch.schema.json + doc 03 field states)
# ---------------------------------------------------------------------------
LAUNCH_SCHEMA_VERSION = "1.0"
SESSION_SCHEMA = "signature-launch-intake/v1"
APPROVAL_SCHEMA_VERSION = "1.0"
PLAN_BUILD_APPROVAL_TYPE = "launch_plan_build"
VERIFICATION_CLASSES = (
    "authenticated_platform_record",
    "recorded_consent_not_cryptographically_sealed",
)
SOURCE_KINDS = ("owner", "existing_verified_catalog", "recommendation",
                "test_fixture")
OFFER_SLOTS = ("main", "bump", "upsell_1", "downsell_1", "upsell_2")
BUILDABLE_SESSION_STATES = ("approved", "building")
BUILDABLE_LAUNCH_STATUSES = ("approved", "building")

# Doc 03 field states. The adapter consumes only CONSUMED_STATES:
# a recommendation the client has not approved is not a locked fact, and
# unknown is never a value. not_applicable is valid only where a field's own
# contract allows it (testimonial evidence).
FIELD_STATES = ("provided", "verified_existing", "recommended_unapproved",
                "approved_recommendation", "unknown", "not_applicable")
CONSUMED_STATES = ("provided", "verified_existing", "approved_recommendation")

# Intake ledger keys the email profile consumes (launch-questions.json).
LEDGER_PAINS = "offers.main.pains"           # question a3: the three pains
LEDGER_TRANSFORMATION = "offers.main.transformation"  # question a2
LEDGER_PROOF = "proof"                       # question a5
LEDGER_OVERRIDES = "locked_overrides"        # session-level, adapter-defined

# Launch record fields the plan hash excludes (S49: the hash binds CONTENT,
# never lifecycle fields, so one approval stays verifiable across the status
# flip the approval itself causes).
HASH_EXCLUDED_FIELDS = ("status", "plan_approval_ref")


class ShapeError(ValueError):
    """An S49-shaped record failed verification. Fail-closed: callers turn
    this into a refusal, never a fallback."""


# ---------------------------------------------------------------------------
# Plan document hash (byte-for-byte the S49 canonicalization)
# ---------------------------------------------------------------------------
def plan_document_hash(launch: Dict[str, Any]) -> str:
    bindable = {k: v for k, v in launch.items()
                if k not in HASH_EXCLUDED_FIELDS}
    return hashlib.sha256(
        json.dumps(bindable, sort_keys=True,
                   separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Approval gate (replicates S49 _check_approval_record for the plan gate)
# ---------------------------------------------------------------------------
def check_plan_build_approval(launch: Dict[str, Any], approval: Any, *,
                              client_identity_ref: str,
                              worker_identity_ref: str = "",
                              now: Optional[datetime] = None) -> Dict[str, Any]:
    """Verify the launch_plan_build approval binding for THIS launch record.

    Checks, in order: record shape; schema version; type is
    launch_plan_build; the scope list actually contains launch_plan_build
    (a narrowed or emptied scope authorizes nothing); not revoked;
    verification class recognized; subject_hash equals the recomputed plan
    document hash; the approver is the launch's client identity; the
    approver is not the worker operating the run; the record carries the
    platform reference of the client's own response; recorded_at parses and
    is not in the future. Raises ShapeError on any failure.
    """
    if not isinstance(approval, dict):
        raise ShapeError("approval record is not an object")
    for f in ("schema_version", "approval_id", "subject_type", "subject_hash",
              "owner_identity_ref", "source_message_ref", "recorded_at",
              "scope", "revoked", "verification_class"):
        if f not in approval:
            raise ShapeError(f"approval record is missing field {f!r}")
    if approval["schema_version"] != APPROVAL_SCHEMA_VERSION:
        raise ShapeError("approval schema_version is not 1.0")
    if approval["subject_type"] != PLAN_BUILD_APPROVAL_TYPE:
        raise ShapeError(
            f"approval type {approval['subject_type']!r} does not authorize "
            f"{PLAN_BUILD_APPROVAL_TYPE!r} (approval types are separate)")
    scope = approval["scope"]
    if not isinstance(scope, list) or not scope \
            or not all(isinstance(s, str) and s.strip() for s in scope) \
            or PLAN_BUILD_APPROVAL_TYPE not in scope:
        raise ShapeError(
            f"approval scope {scope!r} does not cover "
            f"{PLAN_BUILD_APPROVAL_TYPE!r}: a narrowed, emptied, or foreign "
            "scope authorizes nothing")
    if approval["revoked"] is not False:
        raise ShapeError("approval has been revoked")
    if approval["verification_class"] not in VERIFICATION_CLASSES:
        raise ShapeError("approval verification_class is not recognized")
    expected_hash = plan_document_hash(launch)
    if approval["subject_hash"] != expected_hash:
        raise ShapeError(
            "approval subject_hash does not match the current plan: the "
            "plan changed after approval (or this approval belongs to "
            "another plan)")
    owner = approval["owner_identity_ref"]
    if not isinstance(owner, str) or not owner.strip():
        raise ShapeError("approval names no owner identity")
    if owner != client_identity_ref:
        raise ShapeError(
            "the approver is not this launch's client identity: an "
            "unrelated identity cannot approve another launch")
    if worker_identity_ref and owner == worker_identity_ref:
        raise ShapeError(
            "the worker operating the run cannot approve its own work "
            "(self-approval is refused)")
    if not isinstance(approval["source_message_ref"], str) \
            or not approval["source_message_ref"].strip():
        raise ShapeError(
            "approval carries no platform reference to the client's own "
            "response: recorded consent requires the owner's actual message")
    try:
        recorded = datetime.fromisoformat(
            str(approval["recorded_at"]).replace("Z", "+00:00"))
    except ValueError:
        raise ShapeError("approval recorded_at is not a valid timestamp")
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if recorded > now:
        raise ShapeError("approval recorded_at is in the future")
    return {"ok": True, "approval_id": approval["approval_id"],
            "subject_hash": expected_hash,
            "verification_class": approval["verification_class"]}


# ---------------------------------------------------------------------------
# Intake session accessors (launch_intake.py session document)
# ---------------------------------------------------------------------------
def session_answers(session: Any) -> Dict[str, Any]:
    if not isinstance(session, dict):
        raise ShapeError("intake session is not an object")
    answers = session.get("answers")
    if not isinstance(answers, dict):
        raise ShapeError("intake session carries no answers ledger object")
    return answers


def ledger_entry(session: Any, key: str) -> Optional[Dict[str, Any]]:
    """One answer-ledger entry: {value, state, source_ref, question_id}.
    Returns None when the session never recorded the key. Note the S49
    intake can leave source_ref empty on handler-set fields, so an empty
    source_ref is a shape fact to handle, never a parse failure here."""
    entry = session_answers(session).get(key)
    if entry is None:
        return None
    if not isinstance(entry, dict) or "value" not in entry \
            or "state" not in entry:
        raise ShapeError(
            f"ledger entry {key!r} is not a ledger entry object "
            "(value and state are required)")
    return entry


def consumed_state_ok(entry: Dict[str, Any], field_label: str) -> None:
    """Refuse a ledger entry whose state the email profile may not consume."""
    state = entry.get("state")
    if state not in FIELD_STATES:
        raise ShapeError(
            f"{field_label}: ledger state {state!r} is not a doc 03 field "
            "state")
    if state not in CONSUMED_STATES:
        raise ShapeError(
            f"{field_label}: ledger state is {state!r}: the email profile "
            "consumes only provided, verified_existing, or "
            "approved_recommendation facts (an unapproved recommendation or "
            "an unknown is not a locked fact)")


def main_offers(launch: Any) -> list:
    if not isinstance(launch, dict):
        raise ShapeError("launch record is not an object")
    offers = launch.get("offers")
    if not isinstance(offers, list):
        raise ShapeError("launch record carries no offers array")
    mains = [o for o in offers if isinstance(o, dict)
             and o.get("slot") == "main"]
    return mains
