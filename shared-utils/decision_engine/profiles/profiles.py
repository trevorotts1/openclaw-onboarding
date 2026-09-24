#!/usr/bin/env python3
"""JEV 1.1 selection profiles (spec 1.1, sections 6.1-6.4, 7.1-7.4).

Stdlib only. No network, no provider access, no state writes.

Builders CONSUME caller-supplied authoritative roster/config data. This module
holds no department roster and no role library of its own: any company,
including companies with fully custom departments, flows through the same
code path. Builders raise ValueError on unresolvable input (fail fast at
build time); exclusion/selection helpers return data, never raise on
well-formed input.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import NamedTuple

PROFILE_VERSION = "1.0"
PROFILE_VERSION_MAJOR = "1"

# Spec 6.3: distinct routing outcomes. A split score between two departments
# never implies multi-department work; that judgment arrives explicitly.
NONE_SUITABLE = "none_suitable"
NEEDS_MULTIPLE_DEPARTMENTS = "needs_multiple_departments"

# Spec 7.3 exclusion reasons (data, not branches at call sites).
REASON_FOREIGN_COMPANY = "foreign_company"
REASON_WORKER_OFFLINE = "worker_offline"
REASON_RUNTIME_UNAUTHORIZED = "runtime_unauthorized"
REASON_QC_ONLY_PRODUCTION = "qc_only_production"

# Spec 6.2 canonical department-candidate description fields.
DEPT_CANDIDATE_FIELDS = (
    "department_id",
    "display_name",
    "purpose",
    "owned_outcomes",
    "exclusions",
    "capabilities",
    "neighbors",
    "profile_version",
    "sources",
)

# Spec 7.2 compact versioned role-selection profile fields.
ROLE_PROFILE_FIELDS = (
    "role_id",
    "role_slug",
    "company_id",
    "department_id",
    "responsibilities",
    "owned_outcomes",
    "deliverable_types",
    "capabilities",
    "exclusions",
    "sources",
    "availability",
    "profile_version",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def content_hash(text: str) -> str:
    """Stable sha256 hex of source text; changes when content changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(node) -> str:
    """Deterministic JSON for hashing (sorted keys, compact separators)."""
    return json.dumps(node, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def profile_hash(profile: dict) -> str:
    """Content hash of a built profile (proves derivation from sources)."""
    return content_hash(canonical_json(profile))


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _as_str_list(value, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ValueError(f"{name}: required string or list of strings, got {value!r}")


def _source_entries(role_or_dept: dict) -> list[dict]:
    """Source file/section ids + content hashes (spec 7.2, 6.2-from-config).

    Caller supplies ``sources`` as [{file, section, content}] and/or a
    ``source_text`` blob; every entry is hashed so a profile pins the exact
    material it was derived from.
    """
    entries: list[dict] = []
    for src in role_or_dept.get("sources") or []:
        if not isinstance(src, dict):
            raise ValueError(f"source entry must be an object, got {src!r}")
        for key in ("file", "section", "content"):
            if not isinstance(src.get(key), str) or not src[key].strip():
                raise ValueError(f"source entry: required non-empty {key!r}")
        entries.append({
            "file": src["file"],
            "section": src["section"],
            "content_hash": content_hash(src["content"]),
        })
    if role_or_dept.get("source_text") is not None:
        text = role_or_dept["source_text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("source_text: required non-empty string")
        entries.append({
            "file": role_or_dept.get("source_file", "inline"),
            "section": role_or_dept.get("source_section", "full"),
            "content_hash": content_hash(text),
        })
    if not entries:
        raise ValueError("at least one source (sources[] entry or source_text) required")
    return entries


# ---------------------------------------------------------------------------
# Departments (spec 6.1-6.4)
# ---------------------------------------------------------------------------

def build_department_candidate(dept: dict, *, company_id: str) -> dict:
    """Versioned candidate profile derived from caller-supplied dept config.

    Required: department_id, display_name. Everything descriptive (purpose,
    owned outcomes, exclusions, capabilities, neighbors) comes from the
    passed config, never from a roster inside this module.
    """
    if not isinstance(dept, dict):
        raise ValueError(f"dept: required object, got {type(dept).__name__}")
    dept_id = dept.get("department_id")
    if not isinstance(dept_id, str) or not dept_id.strip():
        raise ValueError("dept: 'department_id' must resolve to a non-empty string")
    name = dept.get("display_name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"dept {dept_id!r}: 'display_name' required non-empty string")
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError("company_id: required non-empty string")
    return {
        "department_id": dept_id,
        "display_name": name,
        "purpose": dept.get("purpose", ""),
        "owned_outcomes": _as_str_list(dept.get("owned_outcomes"), "owned_outcomes"),
        "exclusions": _as_str_list(dept.get("exclusions"), "exclusions"),
        "capabilities": _as_str_list(dept.get("capabilities"), "capabilities"),
        "neighbors": _as_str_list(dept.get("neighbors"), "neighbors"),
        "profile_version": PROFILE_VERSION,
        "sources": _source_entries(dept),
    }


def eligible_department_candidates(
    roster: list[dict],
    *,
    company_id: str,
    active_ids: list[str] | None = None,
) -> list[dict]:
    """Deterministic eligibility over the caller-supplied roster.

    Custom departments pass through untouched; output sorted by
    department_id. ``active_ids`` optionally narrows to the actual active
    roster. No roster-size assumptions anywhere on this path.
    """
    if not isinstance(roster, list):
        raise ValueError(f"roster: required list, got {type(roster).__name__}")
    wanted = set(active_ids) if active_ids is not None else None
    out = []
    for dept in roster:
        candidate = build_department_candidate(dept, company_id=company_id)
        if wanted is None or candidate["department_id"] in wanted:
            out.append(candidate)
    out.sort(key=lambda c: c["department_id"])
    return out


def resolve_department_selection(
    suitability: dict[str, float],
    *,
    threshold: float,
    multi_department: bool = False,
    owner_preferred: str | None = None,
) -> str:
    """Ranking is not acceptance (spec 6.4).

    Returns a department_id, NONE_SUITABLE, or NEEDS_MULTIPLE_DEPARTMENTS.
    ``multi_department`` is an explicit caller judgment; split scores alone
    never produce it. An explicit owner preference outranks semantic ranking
    when it meets the absolute threshold; an unresolvable explicit request
    raises instead of being quietly replaced.
    """
    if owner_preferred is not None and owner_preferred not in suitability:
        raise ValueError(
            f"owner-preferred department {owner_preferred!r} does not resolve "
            "in this company; refusing quiet substitution"
        )
    if multi_department:
        return NEEDS_MULTIPLE_DEPARTMENTS
    if owner_preferred is not None and suitability[owner_preferred] >= threshold:
        return owner_preferred
    qualified = {k: v for k, v in suitability.items() if v >= threshold}
    if not qualified:
        return NONE_SUITABLE
    return sorted(qualified, key=lambda k: (-qualified[k], k))[0]


# ---------------------------------------------------------------------------
# Roles (spec 7.1-7.4)
# ---------------------------------------------------------------------------

class CapabilityFitInput(NamedTuple):
    """Task-aware matching input (spec 7.1). Capability only — no load.

    Load/availability travels in WorkerLoad, never here, so an idle
    unqualified worker cannot outrank a qualified busy one on fit.
    """
    outcome: str
    artifact_type: str = ""
    constraints: tuple = ()
    department_id: str = ""
    sop_context: tuple = ()
    worker_responsibilities: tuple = ()


class WorkerLoad(NamedTuple):
    """Measured load, kept separate from capability fit (spec 7.3)."""
    worker_id: str
    available: bool = True
    queue_depth: int = 0


def build_role_profile(role: dict, *, runtime: dict) -> dict:
    """Compact versioned selection profile from caller-supplied role material.

    ``role`` carries library/how-to content; ``runtime`` carries
    authoritative facts (company_id, availability, eligible worker IDs).
    """
    if not isinstance(role, dict):
        raise ValueError(f"role: required object, got {type(role).__name__}")
    if not isinstance(runtime, dict):
        raise ValueError(f"runtime: required object, got {type(runtime).__name__}")
    role_id = role.get("role_id")
    if not isinstance(role_id, str) or not role_id.strip():
        raise ValueError("role: 'role_id' must resolve to a non-empty string")
    slug = role.get("role_slug", role_id)
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError(f"role {role_id!r}: 'role_slug' required non-empty string")
    company_id = runtime.get("company_id")
    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError(f"role {role_id!r}: runtime 'company_id' required (authoritative fact)")
    availability = runtime.get("availability", {})
    if not isinstance(availability, dict):
        raise ValueError(f"role {role_id!r}: runtime 'availability' must be an object")
    worker_ids = availability.get("eligible_worker_ids", [])
    if not isinstance(worker_ids, list) or not all(isinstance(w, str) for w in worker_ids):
        raise ValueError(f"role {role_id!r}: 'eligible_worker_ids' must be a list of strings")
    return {
        "role_id": role_id,
        "role_slug": slug,
        "company_id": company_id,
        "department_id": role.get("department_id", ""),
        "responsibilities": _as_str_list(role.get("responsibilities"), "responsibilities"),
        "owned_outcomes": _as_str_list(role.get("owned_outcomes"), "owned_outcomes"),
        "deliverable_types": _as_str_list(role.get("deliverable_types"), "deliverable_types"),
        "capabilities": _as_str_list(
            role.get("capabilities", role.get("procedures_skills")), "capabilities"),
        "exclusions": _as_str_list(role.get("exclusions"), "exclusions"),
        "sources": _source_entries(role),
        "availability": {
            "status": availability.get("status", "unknown"),
            "eligible_worker_ids": list(worker_ids),
        },
        "profile_version": PROFILE_VERSION,
    }


def capability_score(fit: CapabilityFitInput, profile: dict) -> float:
    """Deterministic lexical coverage of task tokens by role text (0..1)."""
    task_text = " ".join([
        fit.outcome, fit.artifact_type, fit.department_id,
        " ".join(fit.constraints), " ".join(fit.sop_context),
        " ".join(fit.worker_responsibilities),
    ])
    task_tokens = _tokens(task_text)
    if not task_tokens:
        return 0.0
    role_text = " ".join(
        profile.get("responsibilities", [])
        + profile.get("owned_outcomes", [])
        + profile.get("deliverable_types", [])
        + profile.get("capabilities", [])
    )
    hit = task_tokens & _tokens(role_text)
    return len(hit) / len(task_tokens)


def rank_roles(fit: CapabilityFitInput, profiles: list[dict]) -> list[tuple[str, float]]:
    """Capability ranking only; acceptance is a separate threshold step."""
    ranked = [(p["role_id"], capability_score(fit, p)) for p in profiles]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked


def accept_role(ranked: list[tuple[str, float]], *, threshold: float) -> str:
    """Absolute suitability gate: ranking winner below threshold is refused."""
    if not ranked:
        return NONE_SUITABLE
    best_id, best_score = ranked[0]
    if best_score < threshold:
        return NONE_SUITABLE
    return best_id


# ---------------------------------------------------------------------------
# Exclusions (spec 7.3) — data-driven predicates + owner-direct exception
# ---------------------------------------------------------------------------

def exclusion_for(worker: dict, *, company_id: str, allowed_runtimes: list[str]) -> str | None:
    """Reason a worker is excluded from production candidates, else None.

    Busy is NOT an exclusion: fully qualified busy workers stay eligible
    and load policy decides queueing elsewhere.
    """
    if worker.get("company_id") != company_id:
        return REASON_FOREIGN_COMPANY
    if worker.get("status") in ("offline", "retired"):
        return REASON_WORKER_OFFLINE
    if worker.get("runtime") not in allowed_runtimes:
        return REASON_RUNTIME_UNAUTHORIZED
    if worker.get("qc_only") is True:
        return REASON_QC_ONLY_PRODUCTION
    return None


def eligible_workers(
    workers: list[dict],
    *,
    company_id: str,
    allowed_runtimes: list[str],
    owner_direct: bool = False,
) -> dict:
    """Split workers into eligible vs excluded-with-reason, sorted by id.

    ``owner_direct=True`` is its own explicit path (spec 7.3 owner-direct
    exception): every worker passes and the flag is recorded, never silent.
    """
    eligible: list[str] = []
    excluded: list[dict] = []
    for worker in sorted(workers, key=lambda w: w.get("worker_id", "")):
        wid = worker.get("worker_id")
        if not isinstance(wid, str) or not wid.strip():
            raise ValueError("worker: 'worker_id' must resolve to a non-empty string")
        if owner_direct:
            eligible.append(wid)
            continue
        reason = exclusion_for(worker, company_id=company_id,
                               allowed_runtimes=allowed_runtimes)
        if reason is None:
            eligible.append(wid)
        else:
            excluded.append({"worker_id": wid, "reason": reason})
    return {
        "eligible": eligible,
        "excluded": excluded,
        "owner_direct_exception": owner_direct,
    }
