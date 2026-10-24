"""Versioned, idempotent recovery classification for historical Skill 75 runs.

Classifies existing projects as RESUMABLE, RECOVERABLE or BLOCKED from evidence
already on disk. Read-only with respect to source evidence; the only file it
writes is the caller-supplied idempotency journal. No receipts are created, no
approval is inferred, no paid output is regenerated, nothing is rolled back.
"""
from .classifier import (  # noqa: F401
    BLOCKED,
    CLASSIFIER_VERSION,
    INPUT_SCHEMA,
    JOURNAL_SCHEMA,
    OUTPUT_SCHEMA,
    RECOVERABLE,
    REGENERATION_POLICY,
    RESUMABLE,
    ROLLBACK_POLICY,
    STATES,
    Journal,
    RecoveryError,
    UnsupportedSchemaError,
    check_approvals,
    classify,
    digest_of,
    load_project,
    validate_project,
    verify_evidence,
)

__all__ = [
    "BLOCKED",
    "CLASSIFIER_VERSION",
    "INPUT_SCHEMA",
    "JOURNAL_SCHEMA",
    "OUTPUT_SCHEMA",
    "RECOVERABLE",
    "REGENERATION_POLICY",
    "RESUMABLE",
    "ROLLBACK_POLICY",
    "STATES",
    "Journal",
    "RecoveryError",
    "UnsupportedSchemaError",
    "check_approvals",
    "classify",
    "digest_of",
    "load_project",
    "validate_project",
    "verify_evidence",
]
