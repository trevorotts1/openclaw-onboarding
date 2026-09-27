"""Owner-direct execution-policy record (JEV spec 1.1, section 5).

Stdlib only. No network, no provider access, no state writes inside this
module: persistence helpers are pure functions over a caller-supplied store.

Companion to D02 (shared-utils/decision_engine/contracts/schema.py): the D02
envelope classifies intent; this module authorizes the 5.1 owner-direct mode
and carries it through the 5.3 lifecycle. Actual dispatch wiring is D12's
unit; this module stops at policy-level types plus round-trip rules.

D10 CC intake shape contract (read-only alias, CC repo never edited):
cc-d10 src/lib/intake/classify.ts Classification carries
``executionPreference: 'current_assistant'`` for "you do it" rows (spec 4.4).
``ClassificationLike`` mirrors that shape; ``is_owner_direct_preference``
maps it onto this module's decision input.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Mapping

POLICY_REVISION_INITIAL = 1

TRUSTED_SOURCE = "trusted_context"
UNTRUSTED_SOURCES = (
    "user_supplied_json",
    "magic_marker",
    "task_description",
    "quoted_text",
)

OWNER_DIRECT_MODE = "owner_direct"
CURRENT_ASSISTANT = "current_assistant"

# Spec 5.3 lifecycle, in order. auto/manual dispatch kept distinct.
LIFECYCLE_STAGES = (
    "ingest",
    "task_creation",
    "assignment",
    "queued_retries",
    "execution_reservation",
    "auto_dispatch",
    "manual_dispatch",
    "worker_context",
    "qc_correction",
    "resume",
    "completion",
)

CONTEXT_KEYS = (
    "execution_mode",
    "executor",
    "policy_revision",
    "config_revision",
    "source_message_id",
    "evidence_span",
    "company",
)


@dataclass(frozen=True)
class ExecutionPolicyRecord:
    """Durable execution-policy record, exact spec 5.2 fields plus two.

    Spec 5.2 requires: mode, requested executor, actual authorized executor,
    source message ID, evidence span/reference, authenticated requester,
    company, policy revision. ``requester_authenticated`` and
    ``authorization_source`` carry the 5.2 binding rule (trusted server-side
    context binds request to owner; user JSON / magic markers never do).
    ``config_revision`` lets D12 fence compare-and-swap on policy/config
    revision (spec 5.5 seam).
    """

    mode: str = OWNER_DIRECT_MODE
    requested_executor: str = CURRENT_ASSISTANT
    actual_executor: str = CURRENT_ASSISTANT
    source_message_id: str = ""
    evidence_span: str = ""
    authenticated_requester: str = ""
    requester_authenticated: bool = False
    authorization_source: str = "unknown"
    company: str = ""
    policy_revision: int = POLICY_REVISION_INITIAL
    config_revision: str = ""


class ClassificationLike(Mapping):
    """Read-only alias for the D10 CC classify() output shape.

    Structural mirror only (never imports the CC repo): ``intent``,
    ``executionPreference``, ``provenance``, ``controlProbe``,
    ``bypassAllowed``, ``messageHash``.
    """

    def __init__(self, payload: Mapping[str, Any]):
        self._payload = dict(payload)

    def __getitem__(self, key: str) -> Any:
        return self._payload[key]

    def __iter__(self):
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)


def is_owner_direct_preference(classification: Mapping[str, Any]) -> bool:
    """True when a D10 Classification asks for the current assistant."""
    try:
        return classification.get("executionPreference") == CURRENT_ASSISTANT
    except Exception:
        return False


def validate_record(record: Any) -> tuple[bool, str]:
    """Fail-closed validator. Returns ``(ok, reason)``; never raises."""
    try:
        if not isinstance(record, ExecutionPolicyRecord):
            return False, "not_a_record"
        if record.mode != OWNER_DIRECT_MODE:
            return False, "invalid_mode"
        if not isinstance(record.requested_executor, str) or not record.requested_executor.strip():
            return False, "missing_requested_executor"
        if not isinstance(record.actual_executor, str) or not record.actual_executor.strip():
            return False, "missing_actual_executor"
        if not isinstance(record.source_message_id, str) or not record.source_message_id.strip():
            return False, "missing_source_message_id"
        if not isinstance(record.evidence_span, str) or not record.evidence_span.strip():
            return False, "missing_evidence_span"
        if not record.requester_authenticated or not (
            isinstance(record.authenticated_requester, str) and record.authenticated_requester.strip()
        ):
            return False, "unauthenticated_requester"
        if record.authorization_source != TRUSTED_SOURCE:
            return False, "not_authorized_intent_only"
        if not isinstance(record.company, str) or not record.company.strip():
            return False, "missing_company"
        if not isinstance(record.policy_revision, int) or isinstance(record.policy_revision, bool) \
                or record.policy_revision < 1:
            return False, "invalid_policy_revision"
        return True, "ok"
    except Exception:
        return False, "validator_error"


def record_from_dict(data: Mapping[str, Any]) -> ExecutionPolicyRecord:
    """Rehydrate, tolerating unknown extension fields (dropped, never fail)."""
    known = {f for f in ExecutionPolicyRecord.__dataclass_fields__}
    return ExecutionPolicyRecord(**{k: v for k, v in dict(data).items() if k in known})


def record_key(record: ExecutionPolicyRecord) -> str:
    """Stable store key: company + source message + policy revision."""
    return f"{record.company}:{record.source_message_id}:{record.policy_revision}"


def save_record(store: dict, record: ExecutionPolicyRecord) -> str:
    """Persist into a caller-supplied store. Module owns no handles."""
    key = record_key(record)
    store[key] = asdict(record)
    return key


def load_record(store: Mapping[str, Any], key: str) -> dict | None:
    """Read raw record dict from a caller-supplied store; None when absent."""
    hit = store.get(key)
    return dict(hit) if isinstance(hit, dict) else None


def bump_policy_revision(record: ExecutionPolicyRecord) -> ExecutionPolicyRecord:
    """Return a copy with policy_revision + 1; original untouched."""
    current = record.policy_revision
    if not isinstance(current, int) or isinstance(current, bool) or current < 1:
        current = POLICY_REVISION_INITIAL
        return replace(record, policy_revision=current)
    return replace(record, policy_revision=current + 1)


def propagate_to_context(
    context: Mapping[str, Any],
    record: ExecutionPolicyRecord,
    stage: str,
) -> dict:
    """Encode mode + revision into a worker-context dict (spec 5.3).

    Raises ValueError on an unknown lifecycle stage (caller contract, not
    untrusted input). Never mutates the input context.
    """
    if stage not in LIFECYCLE_STAGES:
        raise ValueError(f"unknown lifecycle stage: {stage!r}")
    out = dict(context)
    out.update(
        execution_mode=record.mode,
        executor=record.actual_executor,
        policy_revision=record.policy_revision,
        config_revision=record.config_revision,
        source_message_id=record.source_message_id,
        evidence_span=record.evidence_span,
        company=record.company,
        lifecycle_stage=stage,
    )
    return out


def apply_qc_failure(context: Mapping[str, Any]) -> dict:
    """QC failure returns to the SAME authorized executor (spec 5.3).

    Policy-level rule only: executor and mode pass through untouched; stage
    advances to qc_correction. A retry must not revert to normal routing.
    """
    out = dict(context)
    out["lifecycle_stage"] = "qc_correction"
    return out


def decide_owner_direct(
    record: Any,
    trusted: Callable[[], bool] | bool,
    classification: Mapping[str, Any] | None = None,
) -> dict:
    """Owner-direct branch (spec 5.1/5.2).

    Returns ``{"mode": "owner_direct", "executor": "current_assistant",
    "evidence": record}`` only when the caller-supplied trusted-context
    predicate passes AND the record validates. Every other path returns a
    dict with ``mode`` absent, so the existing catch-all path behaves
    byte-identically. An optional D10 Classification further gates on the
    ``current_assistant`` execution preference.
    """
    is_trusted = trusted() if callable(trusted) else bool(trusted)
    if not is_trusted:
        return {}
    if classification is not None and not is_owner_direct_preference(classification):
        return {}
    ok, _ = validate_record(record)
    if not ok:
        return {}
    return {"mode": OWNER_DIRECT_MODE, "executor": CURRENT_ASSISTANT, "evidence": record}


__all__ = [
    "POLICY_REVISION_INITIAL",
    "TRUSTED_SOURCE",
    "UNTRUSTED_SOURCES",
    "OWNER_DIRECT_MODE",
    "CURRENT_ASSISTANT",
    "LIFECYCLE_STAGES",
    "CONTEXT_KEYS",
    "ExecutionPolicyRecord",
    "ClassificationLike",
    "is_owner_direct_preference",
    "validate_record",
    "record_from_dict",
    "record_key",
    "save_record",
    "load_record",
    "bump_policy_revision",
    "propagate_to_context",
    "apply_qc_failure",
    "decide_owner_direct",
]
