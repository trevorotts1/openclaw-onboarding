"""JEV 1.1 selection profiles (spec 1.1, sections 6-7)."""

from .profiles import (  # noqa: F401
    PROFILE_VERSION,
    NEEDS_MULTIPLE_DEPARTMENTS,
    NONE_SUITABLE,
    CapabilityFitInput,
    WorkerLoad,
    accept_role,
    build_department_candidate,
    build_role_profile,
    capability_score,
    canonical_json,
    content_hash,
    eligible_department_candidates,
    eligible_workers,
    exclusion_for,
    profile_hash,
    rank_roles,
    resolve_department_selection,
)
