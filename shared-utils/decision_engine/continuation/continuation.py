#!/usr/bin/env python3
"""D12 owner-direct/named-worker continuation policy (JEV spec 1.1, ss 5.3/5.5/10.3).

Given a task snapshot plus the D11 execution-policy record and the D23
single-writer primitives, produce the authorized continuation decision:

* ``preserve_executor`` — QC failure / retry keeps the authorized executor.
* ``hold_unavailable_executor`` — pinned executor gone, task killed/archived,
  live/unknown execution, policy drift, or QC cap: HOLD, never silent delegation.
* ``reroute_delegated`` — normal delegation (or unauthorized owner-direct):
  the department router decides, not this module.

Stdlib only. No network, no provider access, no state writes: the CAS commit
helper takes the caller-supplied store plus the caller-imported D23 module, so
this file never opens a handle and no transaction can span a call. Untrusted
text (``owner_direct`` booleans, magic markers, quoted commands) is never an
input: authorization comes only from a validated D11 record plus a
caller-supplied trusted-context predicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

PRESERVE_EXECUTOR = "preserve_executor"
HOLD_UNAVAILABLE = "hold_unavailable_executor"
REROUTE_DELEGATED = "reroute_delegated"

PREFERENCE_OWNER_DIRECT = "current_assistant"
PREFERENCE_NAMED_WORKER = "named_worker"
PREFERENCE_NORMAL = "normal_delegation"

# Mirrors the CC execution-attempt states this decision must never steal.
EXECUTION_ACTIVE = ("reserved", "sending", "accepted", "running", "unknown")
EXECUTION_TERMINAL = ("succeeded", "failed")
EXECUTION_NONE = "none"

_TRUSTED_SOURCE = "trusted_context"
_OWNER_DIRECT_MODE = "owner_direct"
_CURRENT_ASSISTANT = "current_assistant"


def _d11_validator():
    """D11 fail-closed record validator, live when importable.

    Consumes shared-utils/execution_policy (D11) instead of restating it.
    Falls back to a local fail-closed re-check only when the module is not
    importable, so a path misconfiguration can never silently authorize.
    """
    try:
        from execution_policy import (  # noqa: PLC0415 (runtime, path-set by caller)
            CURRENT_ASSISTANT,
            OWNER_DIRECT_MODE,
            TRUSTED_SOURCE,
            validate_record,
        )
        return validate_record, OWNER_DIRECT_MODE, CURRENT_ASSISTANT, TRUSTED_SOURCE
    except Exception:
        def _local(record: Any) -> tuple[bool, str]:
            try:
                if record is None or isinstance(record, bool):
                    return False, "not_a_record"
                mode = getattr(record, "mode", None)
                if mode != _OWNER_DIRECT_MODE:
                    return False, "invalid_mode"
                for attr, reason in (
                    ("requested_executor", "missing_requested_executor"),
                    ("actual_executor", "missing_actual_executor"),
                    ("source_message_id", "missing_source_message_id"),
                    ("evidence_span", "missing_evidence_span"),
                    ("company", "missing_company"),
                ):
                    if not isinstance(getattr(record, attr, None), str) \
                            or not getattr(record, attr).strip():
                        return False, reason
                if not getattr(record, "requester_authenticated", False) \
                        or not str(getattr(record, "authenticated_requester", "")).strip():
                    return False, "unauthenticated_requester"
                if getattr(record, "authorization_source", None) != _TRUSTED_SOURCE:
                    return False, "not_authorized_intent_only"
                rev = getattr(record, "policy_revision", 0)
                if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
                    return False, "invalid_policy_revision"
                return True, "ok"
            except Exception:
                return False, "validator_error"

        return _local, _OWNER_DIRECT_MODE, _CURRENT_ASSISTANT, _TRUSTED_SOURCE


@dataclass(frozen=True)
class TaskSnapshot:
    """Everything the continuation decision fences on, read BEFORE routing."""

    task_id: str = ""
    status: str = "backlog"
    assignment_version: int = 0
    input_hash: str | None = None
    policy_revision: int = 0
    config_revision: str = ""
    company_id: str = ""
    workspace_id: str = ""
    assigned_agent_id: str | None = None
    execution_state: str = EXECUTION_NONE
    qc_failures: int = 0
    qc_cap: int = 5
    killed: bool = False
    archived: bool = False


@dataclass(frozen=True)
class ExecutorAvailability:
    """Caller-resolved liveness of the pinned executor. Reason is evidence."""

    available: bool
    reason: str = "ok"


@dataclass(frozen=True)
class ContinuationDecision:
    """Authorized continuation, JSON-safe for the CC bridge."""

    action: str
    executor: str | None
    reason: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    task_id: str = ""
    assignment_version: int = 0
    policy_revision: int = 0


def _base_evidence(snapshot: TaskSnapshot) -> dict:
    return {
        "task_id": snapshot.task_id,
        "status": snapshot.status,
        "assignment_version": snapshot.assignment_version,
        "policy_revision": snapshot.policy_revision,
        "config_revision": snapshot.config_revision,
        "company_id": snapshot.company_id,
        "workspace_id": snapshot.workspace_id,
        "execution_state": snapshot.execution_state,
        "qc_failures": snapshot.qc_failures,
        "qc_cap": snapshot.qc_cap,
    }


def decide_continuation(
    record: Any,
    snapshot: TaskSnapshot,
    availability: ExecutorAvailability,
    trusted: Callable[[], bool] | bool,
    preference: str = PREFERENCE_NORMAL,
    requested_executor: str | None = None,
) -> ContinuationDecision:
    """Authorize preserve | hold | reroute. Never raises on untrusted input."""
    validate_record, owner_direct_mode, current_assistant, _ = _d11_validator()
    ev = _base_evidence(snapshot)
    hold = lambda reason, extra=None: ContinuationDecision(  # noqa: E731
        HOLD_UNAVAILABLE, None, reason,
        {**ev, **(extra or {})},
        snapshot.task_id, snapshot.assignment_version, snapshot.policy_revision)

    if snapshot.killed:
        return hold("task_killed")
    if snapshot.archived:
        return hold("task_archived")
    if snapshot.execution_state in EXECUTION_ACTIVE:
        # Never reopen or steal a live/unknown attempt; the old attempt must
        # reach terminal/reconciled first (reservation machinery owns that).
        return hold("execution_active",
                    {"active_state": snapshot.execution_state})

    is_trusted = trusted() if callable(trusted) else bool(trusted)
    if preference == PREFERENCE_NORMAL or not is_trusted:
        return ContinuationDecision(
            REROUTE_DELEGATED, None,
            "normal_delegation" if preference == PREFERENCE_NORMAL
            else "not_authorized_intent_only",
            {**ev, "preference": preference}, snapshot.task_id,
            snapshot.assignment_version, snapshot.policy_revision)

    ok, why = validate_record(record)
    if not ok:
        # Intent evidence (user JSON, magic markers, quoted text, bare
        # booleans) never authorizes: without a valid trusted record the
        # department router decides.
        return ContinuationDecision(
            REROUTE_DELEGATED, None, why,
            {**ev, "preference": preference}, snapshot.task_id,
            snapshot.assignment_version, snapshot.policy_revision)

    if getattr(record, "mode", None) != owner_direct_mode:
        return ContinuationDecision(
            REROUTE_DELEGATED, None, "invalid_mode",
            {**ev, "preference": preference}, snapshot.task_id,
            snapshot.assignment_version, snapshot.policy_revision)

    if preference == PREFERENCE_OWNER_DIRECT:
        if getattr(record, "actual_executor", None) != current_assistant:
            return ContinuationDecision(
                REROUTE_DELEGATED, None, "executor_mismatch",
                {**ev, "preference": preference}, snapshot.task_id,
                snapshot.assignment_version, snapshot.policy_revision)
        executor = current_assistant
    elif preference == PREFERENCE_NAMED_WORKER:
        if not requested_executor \
                or getattr(record, "actual_executor", None) != requested_executor:
            return ContinuationDecision(
                REROUTE_DELEGATED, None, "executor_mismatch",
                {**ev, "preference": preference}, snapshot.task_id,
                snapshot.assignment_version, snapshot.policy_revision)
        executor = requested_executor
    else:
        return ContinuationDecision(
            REROUTE_DELEGATED, None, "unknown_preference",
            {**ev, "preference": preference}, snapshot.task_id,
            snapshot.assignment_version, snapshot.policy_revision)

    if snapshot.policy_revision != getattr(record, "policy_revision", None):
        # Owner/policy edit landed while routing awaited: stale, do not commit.
        return hold("policy_changed",
                    {"record_revision": getattr(record, "policy_revision", None)})
    if snapshot.qc_failures >= snapshot.qc_cap:
        return hold("qc_cap_exhausted")
    if not availability.available:
        # Unavailable pinned executor creates a specific hold, never silent
        # delegation to another worker.
        return hold("executor_unavailable",
                    {"executor": executor, "detail": availability.reason})

    return ContinuationDecision(
        PRESERVE_EXECUTOR, executor, "owner_direct_preserved",
        {**ev, "preference": preference, "executor": executor,
         "record_revision": getattr(record, "policy_revision", None)},
        snapshot.task_id, snapshot.assignment_version, snapshot.policy_revision)


def apply_qc_failure_to_snapshot(snapshot: TaskSnapshot) -> TaskSnapshot:
    """QC failure accounts one retry on the SAME task (ID/provenance kept).

    The executor decision stays with decide_continuation: a retry must not
    revert to normal routing while the record still authorizes.
    """
    from dataclasses import replace  # noqa: PLC0415 (stdlib, deferred for import cost)

    return replace(snapshot, qc_failures=snapshot.qc_failures + 1)


def build_cas_payload(
    decision: ContinuationDecision,
    snapshot: TaskSnapshot,
    input_hash: str | None = None,
    fence_token: Mapping[str, Any] | None = None,
) -> tuple[dict, dict]:
    """Build the D23 decision + board mirrors for a preserve/hold commit."""
    if decision.action == REROUTE_DELEGATED:
        raise ValueError("reroute is decided by the department router, not committed here")
    resolved_hash = input_hash if input_hash is not None else snapshot.input_hash
    decision_dict = {
        "decisionId": "continuation-%s-%d" % (snapshot.task_id, snapshot.assignment_version),
        "inputHash": resolved_hash,
        "action": decision.action,
        "executor": decision.executor,
        "reason": decision.reason,
        "taskId": snapshot.task_id,
        "assignmentVersion": snapshot.assignment_version,
        "policyRevision": snapshot.policy_revision,
    }
    if fence_token is not None:
        decision_dict["fence_token"] = dict(fence_token)
    mirrors = {
        "task": snapshot.task_id,
        "executor": decision.executor,
        "reason": decision.reason,
        "action": decision.action,
    }
    return decision_dict, mirrors


def commit_continuation(
    store: dict,
    expected_revision: int,
    decision: ContinuationDecision,
    snapshot: TaskSnapshot,
    cas_module: Any,
    input_hash: str | None = None,
    fence_token: Mapping[str, Any] | None = None,
) -> int:
    """Single-writer commit of a preserve/hold via the caller-imported D23 module.

    ``cas_module`` is the real shared-utils/decision_engine/commit module
    (imported by the caller, e.g. by file path in tests). Loser/fencing
    failures propagate as D23 typed errors and write nothing.
    """
    payload, mirrors = build_cas_payload(decision, snapshot, input_hash, fence_token)
    return cas_module.cas_commit(store, expected_revision, payload, mirrors)


def to_bridge_dict(decision: ContinuationDecision) -> dict:
    """JSON-safe shape consumed by the CC decision-engine bridge (D09)."""
    return {
        "action": decision.action,
        "executor": decision.executor,
        "reason": decision.reason,
        "evidence": dict(decision.evidence),
        "task_id": decision.task_id,
        "assignment_version": decision.assignment_version,
        "policy_revision": decision.policy_revision,
    }
