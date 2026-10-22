"""capability_control — S75-W04-U2 capability-aware configuration and account
failure control. Import as ``capability_control`` from this skill's
``scripts/core`` directory; stdlib only.

One resolved capability manifest from the installed runtime schema and the
authoritative provider catalog; staged/validated/atomic configuration changes;
honest reasoning-effort representation; hard-cap failure classification with a
shared account breaker. Finding D30 (spec sections 7.5, 15.3).
"""
from .effort import EffortPlan, ModelCaps, plan_request, thinking_log_proof
from .failures import AccountBreaker, BoundedPolicy, Failure, classify
from .manifest import CapabilityManifest, DispatchReceipt, Finding, effort_claims_findings, resolve_manifest
from .config_stage import ApplyResult, ConfigStage, StageResult, canonical_digest
from .runtime_schema import OwnedMerge, RuntimeSchema, SchemaError, assert_writable_target

__all__ = [
    "AccountBreaker", "ApplyResult", "BoundedPolicy", "CapabilityManifest", "ConfigStage",
    "DispatchReceipt", "EffortPlan", "Failure", "Finding", "ModelCaps", "OwnedMerge",
    "RuntimeSchema", "SchemaError", "StageResult", "assert_writable_target",
    "canonical_digest", "effort_claims_findings", "plan_request", "resolve_manifest",
    "thinking_log_proof", "classify",
]
