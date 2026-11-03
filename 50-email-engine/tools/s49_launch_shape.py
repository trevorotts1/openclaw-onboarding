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
  - The approval gate is the SAME one S49 uses (ENF-01): the record is
    checked by shared-utils/signature_launch_contract/approval_record.verify
    (Command Center record for a live plan; a local record only when the
    launch itself is test_only). Kind, scope, plan hash, client identity,
    revocation and expiry are the verifier's checks; this module adds only
    the worker self-approval refusal.

Deterministic, stdlib only. Nothing in this module approves anything: it
verifies records that already exist.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Vocabulary (S49 launch.schema.json + doc 03 field states)
# ---------------------------------------------------------------------------
# S49 validate_launch accepts 1.0, 1.1 (prompt_policy_id) and 1.2
# (delivery_bindings; what Skill 83 emits). The plan hash binds every field
# but the two lifecycle fields, so all three versions hash identically.
ACCEPTED_LAUNCH_SCHEMA_VERSIONS = ("1.0", "1.1", "1.2")
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
# Approval gate (the one verifier S49 uses: shared-utils approval_record.py)
# ---------------------------------------------------------------------------
_APPROVAL_RECORD = (Path(__file__).resolve().parents[2] / "shared-utils" /
                    "signature_launch_contract" / "approval_record.py")


def _approval_verifier():
    """Load approval_record.py by path. Missing = fail closed."""
    if not _APPROVAL_RECORD.is_file():
        raise ShapeError("approval not verified against platform record: the "
                         "approval verifier (approval_record.py) is not installed")
    spec = importlib.util.spec_from_file_location("approval_record_s50",
                                                  _APPROVAL_RECORD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_plan_build_approval(launch: Dict[str, Any], approval: Any, *,
                              client_identity_ref: str,
                              worker_identity_ref: str = "",
                              now: Optional[datetime] = None) -> Dict[str, Any]:
    """Verify the launch_plan_build approval for THIS launch record through
    approval_record.verify (same gate as S49 assert_plan_build_approved). A
    live launch needs the Command Center record (only approval_id is used);
    a test_only launch may use the local record. Raises ShapeError."""
    if not isinstance(approval, dict):
        raise ShapeError("approval record is not an object")
    if not isinstance(client_identity_ref, str) or not client_identity_ref.strip():
        raise ShapeError("approval names no client identity")
    if worker_identity_ref and client_identity_ref == worker_identity_ref:
        raise ShapeError(
            "the worker operating the run cannot approve its own work "
            "(self-approval is refused)")
    test_only = isinstance(launch, dict) and launch.get("test_only") is True
    expected_hash = plan_document_hash(launch)
    ver = _approval_verifier()
    try:
        out = ver.verify(approval.get("approval_id"), PLAN_BUILD_APPROVAL_TYPE,
                         expected_hash, [PLAN_BUILD_APPROVAL_TYPE],
                         client_identity=client_identity_ref, test_only=test_only,
                         record=approval if test_only else None, now=now)
    except (ver.ApprovalRefused, ver.ApprovalUnavailable) as exc:
        raise ShapeError(
            f"approval not verified against platform record: {exc}") from exc
    return {"ok": True, "approval_id": out["approval_id"],
            "subject_hash": expected_hash,
            "verification_class": "authenticated_platform_record"
            if out["authority"] == "command-center" else "local_test_record"}


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
