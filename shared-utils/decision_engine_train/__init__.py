"""Two 15-minute batch-merge trains (JEV unit D33).

Portable standard-library core for spec sections 14 and 18, acceptance
A49-A53. One module, no third-party imports, no subprocess, no network.
Git and scheduling live outside this module; tests prove it with local
temporary git fixtures only.
"""

from .train import (
    INDEPENDENT_ROUTE,
    MANIFEST_SCHEMA,
    OUTCOMES,
    TRAIN_ROUTE,
    WINDOW_SECONDS,
    acquire_lease,
    amend,
    attach_integration_qc,
    collect_all,
    compose_batch,
    enqueue,
    freeze,
    isolate_failure,
    load_state,
    new_state,
    promote,
    quarter_window,
    record_tests,
    release_flight,
    save_state,
    select_eligible,
    tick,
    validate_qc_receipt,
    verify_manifest,
    window_start_utc,
)

__all__ = [
    "INDEPENDENT_ROUTE",
    "MANIFEST_SCHEMA",
    "OUTCOMES",
    "TRAIN_ROUTE",
    "WINDOW_SECONDS",
    "acquire_lease",
    "amend",
    "attach_integration_qc",
    "collect_all",
    "compose_batch",
    "freeze",
    "isolate_failure",
    "load_state",
    "new_state",
    "promote",
    "quarter_window",
    "record_tests",
    "release_flight",
    "save_state",
    "select_eligible",
    "tick",
    "validate_qc_receipt",
    "verify_manifest",
    "window_start_utc",
]
