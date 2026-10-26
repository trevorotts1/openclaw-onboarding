"""control — S75-T34 supervisor policy adapter.

Enforceable checks for the loop-control recovery protocol (LOOP-CONTROL.md
"Exact owned stop and replacement", "Activation proof", "Safe restart and
takeover"), expressed as pure decisions over caller-supplied observations.
No process is started, signalled or inspected here: the host's supported
observe/fence/stop/terminate/verify operations are injected. Stdlib only.

Import as ``control`` from this skill's ``scripts/core`` directory.
"""
from .supervisor_policy_adapter import (
    ACTIVE,
    ISOLATED_UNKNOWN_OWNER,
    MISSED_READY,
    NOT_ACTIVE,
    OWNED_VIOLATION,
    REQUIRED_ACTIVATION_FACETS,
    REQUIRED_OPERATIONS,
    STOPPED_VERIFIED,
    STOP_UNVERIFIED,
    ControlRefused,
    ReplacementRefused,
    RestartRefused,
    StopRefused,
    activation_status,
    assess,
    detect_missed_ready,
    detect_owned_violation,
    isolate_unknown_owner,
    plan_replacement,
    preserve_checkpoint,
    read_evidence,
    reconcile_restart,
    stop_verified_offender,
    transfer_control,
    verify_checkpoint,
    write_evidence,
)

__all__ = [
    "ACTIVE", "ISOLATED_UNKNOWN_OWNER", "MISSED_READY", "NOT_ACTIVE",
    "OWNED_VIOLATION", "REQUIRED_ACTIVATION_FACETS", "REQUIRED_OPERATIONS",
    "STOPPED_VERIFIED", "STOP_UNVERIFIED", "ControlRefused",
    "ReplacementRefused", "RestartRefused", "StopRefused", "activation_status",
    "assess", "detect_missed_ready", "detect_owned_violation",
    "isolate_unknown_owner", "plan_replacement", "preserve_checkpoint",
    "read_evidence", "reconcile_restart", "stop_verified_offender",
    "transfer_control", "verify_checkpoint", "write_evidence",
]
