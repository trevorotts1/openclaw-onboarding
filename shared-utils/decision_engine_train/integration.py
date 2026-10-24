"""T-43 onboarding cohort integration receipts.

Composes the accepted train core (``decision_engine_train.train``) and the
accepted D34 release-cohort validator into the compatibility decisions a
single shared target owner must make before a cohort lands: shared-file
ownership, schema/reader-writer compatibility, dependency contracts,
cross-repository publication order, red-subset isolation, exact independent
gates, and named-repair remote content proof.

Standard library only. No git, no subprocess, no network, no filesystem
mutation, no wall-clock reads inside decisions (callers pass ``now``).
Delivery (fetching, merging, pushing) is deliberately outside this module:
this module decides and records, it never mutates a remote.

Unknown input is always rendered as ``UNKNOWN`` with a reason string. There
is no code path that turns an unobserved fact into ``PROVEN``.
"""

from __future__ import annotations

import copy

from .train import INDEPENDENT_ROUTE, _load_cohort, isolate_failure, validate_qc_receipt

# The ledger artifact this module produces (T-43 output).
ARTIFACT = "onboarding-remote-merge-receipts"

PROVEN = "PROVEN"
CONTRADICTED = "CONTRADICTED"
UNKNOWN = "UNKNOWN"

ADMITTED = "ADMITTED"
HELD = "HELD"

HOUR_SECONDS = 3600
BUSY_RECHECK_SECONDS = 600

# Onboarding main's required check contexts (ruleset 20330619, E-PREP-MERGE
# 1.2). G1 is deliberately absent: it is push-to-main only, concludes
# "skipped" on a PR, and is non-blocking there. These are exact strings; a
# receipt that omits one is UNKNOWN, not PASS.
ONBOARDING_PR_REQUIRED_CHECKS = (
    "ghl-mcp-pin-gate",
    "GHL MCP supervision + install regression guard",
    "QC static invariants",
    "G1b — every release on main must keep a truthful annotated tag",
    "G2 — every v11+ annotated tag must have a CHANGELOG entry",
    "G3 — skill content change requires skill-version.txt bump",
    "Verify all version markers agree (scripts/bump-version.sh --check)",
)

# config/batch-compatibility.json rule ids (BC-01..BC-08).
RULE_SEPARATE_FILES = "BC-01"
RULE_SHARED_FILE = "BC-02"
RULE_DEPENDENCY = "BC-03"
RULE_ADDITIVE_SCHEMA = "BC-04"
RULE_BREAKING_WRITER = "BC-05"
RULE_CROSS_REPO = "BC-06"
RULE_RED_SUBSET = "BC-07"
RULE_NAMED_REPAIR = "BC-08"

__all__ = [
    "ADMITTED",
    "ARTIFACT",
    "BUSY_RECHECK_SECONDS",
    "CONTRADICTED",
    "HELD",
    "HOUR_SECONDS",
    "ONBOARDING_PR_REQUIRED_CHECKS",
    "PROVEN",
    "RULE_ADDITIVE_SCHEMA",
    "RULE_BREAKING_WRITER",
    "RULE_CROSS_REPO",
    "RULE_DEPENDENCY",
    "RULE_NAMED_REPAIR",
    "RULE_RED_SUBSET",
    "RULE_SEPARATE_FILES",
    "RULE_SHARED_FILE",
    "UNKNOWN",
    "build_receipt",
    "cleanup_disposition",
    "evaluate_cohort",
    "exact_independent_gate",
    "merge_due",
    "prove_named_repair",
    "target_owner",
    "verify_receipt",
]


def _reason(unit_id, rule_id, reason):
    return {"unit_id": str(unit_id), "rule_id": rule_id, "reason": reason}


def _normalise_units(units):
    out = []
    for raw in units or ():
        unit = dict(raw)
        unit["unit_id"] = str(unit.get("unit_id") or "")
        unit["sha"] = str(unit.get("sha") or "")
        unit["files"] = tuple(str(f) for f in unit.get("files") or ())
        unit["depends_on"] = tuple(str(d) for d in unit.get("depends_on") or ())
        unit["state"] = str(unit.get("state") or "green")
        unit["schema"] = dict(unit.get("schema") or {})
        unit["repo"] = str(unit.get("repo") or "")
        out.append(unit)
    return out


def _schema_verdict(unit):
    """Return (rule_id, reason) for a schema clause, or None when the clause holds.

    BC-04: an additive field is admitted only when tolerant readers are
    PROVED — an "optional" annotation is not enough, because a strict old
    reader rejects unknown fields. BC-05: a new required field or breaking
    write format needs the protocol manifest + migration checkpoint and the
    writer switch stays disabled until reader proof exists.
    """
    schema = unit["schema"]
    kind = str(schema.get("kind") or "none")
    if kind in ("none", ""):
        return None
    if kind == "additive":
        if schema.get("tolerant_readers_proved") is not True:
            return (RULE_ADDITIVE_SCHEMA, "tolerant_readers_unproved")
        if not schema.get("reader_trace"):
            return (RULE_ADDITIVE_SCHEMA, "old_new_reader_trace_unobserved")
        return None
    if kind in ("required", "breaking"):
        if not schema.get("protocol_version"):
            return (RULE_BREAKING_WRITER, "protocol_manifest_missing")
        if not schema.get("migration_checkpoint"):
            return (RULE_BREAKING_WRITER, "migration_checkpoint_missing")
        if schema.get("writer_switch_enabled") is True:
            return (RULE_BREAKING_WRITER, "writer_switch_before_reader_proof")
        return None
    return (RULE_BREAKING_WRITER, "unknown_schema_kind:%s" % kind)


def _cross_repo_verdict(unit, by_id, repository, publication_order):
    """BC-06: a cross-repository unit lands after its producer's repository."""
    order = [str(r) for r in publication_order or ()]
    repo = unit["repo"] or repository
    producers = set()
    for dep_id in unit["depends_on"]:
        dep = by_id.get(dep_id)
        if dep is not None:
            dep_repo = dep["repo"] or repository
            if dep_repo != repo:
                producers.add(dep_repo)
    for dep_repo in unit.get("depends_on_repos") or ():
        dep_repo = str(dep_repo)
        if dep_repo != repo:
            producers.add(dep_repo)
    if not producers:
        return None
    if not order:
        return (RULE_CROSS_REPO, "publication_order_unobserved")
    if repo not in order:
        return (RULE_CROSS_REPO, "repository_absent_from_publication_order:%s" % repo)
    for dep_repo in sorted(producers):
        if dep_repo not in order:
            return (RULE_CROSS_REPO, "producer_absent_from_publication_order:%s" % dep_repo)
        if order.index(dep_repo) > order.index(repo):
            return (RULE_CROSS_REPO, "consumer_before_producer:%s" % dep_repo)
    return None


def _topological_order(admitted, by_id):
    """Deterministic Kahn order over admitted units. Returns (order, cyclic)."""
    admitted = set(admitted)
    deps = {uid: {d for d in by_id[uid]["depends_on"] if d in admitted}
            for uid in admitted}
    indegree = {uid: len(deps[uid]) for uid in admitted}
    ready = sorted(uid for uid, n in indegree.items() if n == 0)
    order = []
    while ready:
        uid = ready.pop(0)
        order.append(uid)
        for other in sorted(admitted):
            if uid in deps[other]:
                indegree[other] -= 1
                if indegree[other] == 0:
                    ready.append(other)
        ready.sort()
    cyclic = sorted(admitted - set(order))
    return order, cyclic


def evaluate_cohort(units, *, repository="onboarding", combined_owner=(),
                    publication_order=(), already_landed=()):
    """Freeze one compatible cohort and report admit/hold/unknown per BC-01..BC-08.

    ``units`` entries carry: ``unit_id``, exact ``sha``, ``files`` edited,
    ``depends_on`` (unit ids), ``state`` (``green``/``red``), optional
    ``schema`` (``kind``: ``none``/``additive``/``required``/``breaking``),
    optional ``repo`` and ``depends_on_repos``.

    ``combined_owner`` names the unit ids resolved as ONE combined candidate
    under a single owner (BC-02). ``publication_order`` is the explicit safe
    cross-repository order (BC-06). ``already_landed`` names accepted
    dependencies outside this cohort.

    A held unit holds its true dependents (BC-07 for red, BC-03 otherwise);
    unrelated green candidates stay admitted.
    """
    norm = _normalise_units(units)
    unknown, hold, valid = [], [], []
    seen = set()
    for unit in norm:
        uid = unit["unit_id"]
        if not uid:
            unknown.append(_reason("", RULE_SEPARATE_FILES, "unit_id_unobserved"))
            continue
        if uid in seen:
            unknown.append(_reason(uid, RULE_SEPARATE_FILES, "duplicate_unit_id"))
            continue
        seen.add(uid)
        if not unit["sha"]:
            unknown.append(_reason(uid, RULE_SEPARATE_FILES, "candidate_sha_unobserved"))
            continue
        if unit["state"] not in ("green", "red"):
            unknown.append(_reason(uid, RULE_RED_SUBSET,
                                   "unit_state_unobserved:%s" % unit["state"]))
            continue
        valid.append(unit)

    by_id = {unit["unit_id"]: unit for unit in valid}
    valid_ids = set(by_id)
    landed = {str(value) for value in already_landed or ()}

    # BC-07 red-subset isolation: the red unit and its TRUE dependents only.
    red_roots = sorted(uid for uid, unit in by_id.items() if unit["state"] == "red")
    entries = [{"unit_id": uid, "sha": by_id[uid]["sha"],
                "dependencies": list(by_id[uid]["depends_on"])}
               for uid in sorted(valid_ids)]
    parked = set()
    for root in red_roots:
        parked_units, _remaining = isolate_failure(entries, root)
        parked.update(entry["unit_id"] for entry in parked_units)
    for uid in sorted(parked):
        hold.append(_reason(uid, RULE_RED_SUBSET, "red_subset_isolation"))

    blocked = {entry["unit_id"] for entry in hold}
    blocked.update(entry["unit_id"] for entry in unknown)
    remaining = sorted(valid_ids - blocked)

    # BC-02 shared owned file: one combined candidate, never two independent races.
    file_owners = {}
    for uid in remaining:
        for path in by_id[uid]["files"]:
            file_owners.setdefault(path, []).append(uid)
    shared_groups = []
    for path in sorted(file_owners):
        owners = sorted(file_owners[path])
        if len(owners) > 1:
            shared_groups.append({"file": path, "unit_ids": owners})
    covered = {str(value) for value in combined_owner or ()}
    combined_candidates = []
    for group in shared_groups:
        group_ids = set(group["unit_ids"])
        if group_ids <= covered:
            combined_candidates.append({"files": [group["file"]],
                                        "unit_ids": sorted(group_ids)})
            continue
        for uid in group["unit_ids"]:
            if uid in remaining:
                hold.append(_reason(uid, RULE_SHARED_FILE,
                                    "shared_owned_file_needs_one_combined_owner:%s"
                                    % group["file"]))
                blocked.add(uid)
    remaining = [uid for uid in remaining if uid not in blocked]

    # BC-04 / BC-05 schema and reader/writer compatibility.
    for uid in list(remaining):
        verdict = _schema_verdict(by_id[uid])
        if verdict is not None:
            hold.append(_reason(uid, verdict[0], verdict[1]))
            blocked.add(uid)
    remaining = [uid for uid in remaining if uid not in blocked]

    # BC-06 cross-repository publication order.
    for uid in list(remaining):
        verdict = _cross_repo_verdict(by_id[uid], by_id, repository,
                                      publication_order)
        if verdict is not None:
            hold.append(_reason(uid, verdict[0], verdict[1]))
            blocked.add(uid)
    remaining = [uid for uid in remaining if uid not in blocked]

    # BC-03 dependency contract: land the dependency first or together.
    changed = True
    while changed:
        changed = False
        for uid in list(remaining):
            for dep in by_id[uid]["depends_on"]:
                if dep in landed:
                    continue
                if dep in blocked:
                    hold.append(_reason(uid, RULE_DEPENDENCY,
                                        "dependency_not_admitted:%s" % dep))
                    blocked.add(uid)
                    remaining.remove(uid)
                    changed = True
                    break
                if dep not in valid_ids:
                    hold.append(_reason(uid, RULE_DEPENDENCY,
                                        "dependency_contract_missing:%s" % dep))
                    blocked.add(uid)
                    remaining.remove(uid)
                    changed = True
                    break
    order, cyclic = _topological_order(remaining, by_id)
    for uid in cyclic:
        unknown.append(_reason(uid, RULE_DEPENDENCY, "dependency_cycle"))

    state = UNKNOWN if unknown else (HELD if hold else ADMITTED)
    return {
        "state": state,
        "repository": str(repository),
        "admit": order,
        "order": order,
        "candidates": [{"unit_id": uid, "sha": by_id[uid]["sha"]}
                       for uid in order],
        "hold": sorted(hold, key=lambda e: (e["unit_id"], e["rule_id"])),
        "unknown": sorted(unknown, key=lambda e: (e["unit_id"], e["rule_id"])),
        "red_subset": {"roots": red_roots, "held": sorted(parked)},
        "shared_files": shared_groups,
        "combined_candidates": combined_candidates,
        "cross_repo_order": [str(r) for r in publication_order or ()],
    }


def exact_independent_gate(unit, receipt, required_checks=("unit", "integration")):
    """Prove one unit with an exact-SHA independent PASS receipt and named checks.

    Reuses ``train.validate_qc_receipt`` for the exact-SHA/independent-route
    laws. A broad ``ALL_PASS`` aggregate is not exact evidence and is
    refused. Missing receipt or missing required-check results render
    ``UNKNOWN``; a failure renders ``CONTRADICTED``.
    """
    unit_id = str((unit or {}).get("unit_id") or "")
    if not isinstance(receipt, dict) or not receipt:
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "qc_receipt_unobserved", "checks": []}
    entry = {"sha": (unit or {}).get("sha"), "qc_receipt": receipt}
    ok, reason = validate_qc_receipt(entry)
    if not ok:
        return {"unit_id": unit_id, "state": CONTRADICTED,
                "reason": reason, "checks": []}

    raw_checks = receipt.get("checks")
    if isinstance(raw_checks, dict):
        observed = {str(k): str(v) for k, v in raw_checks.items()}
        check_list = [{"name": k, "status": v} for k, v in observed.items()]
    elif isinstance(raw_checks, list):
        observed = {str(c.get("name")): str(c.get("status"))
                    for c in raw_checks if isinstance(c, dict)}
        check_list = [{"name": str(c.get("name")), "status": str(c.get("status"))}
                      for c in raw_checks if isinstance(c, dict)]
    else:
        observed, check_list = {}, []
    for name in observed:
        if name.upper() in ("ALL_PASS", "ALL", "AGGREGATE"):
            return {"unit_id": unit_id, "state": CONTRADICTED,
                    "reason": "broad_all_pass_is_not_exact_evidence",
                    "checks": check_list}
    if not observed:
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "required_check_results_unobserved",
                "checks": check_list}
    for name in required_checks or ():
        if name not in observed:
            return {"unit_id": unit_id, "state": UNKNOWN,
                    "reason": "required_check_unobserved:%s" % name,
                    "checks": check_list}
        if observed[name] != "pass":
            return {"unit_id": unit_id, "state": CONTRADICTED,
                    "reason": "required_check_failed:%s" % name,
                    "checks": check_list}
    return {"unit_id": unit_id, "state": PROVEN, "reason": "",
            "checks": check_list}


def _repair_verdict(state, reason, **extra):
    payload = {"state": state, "reason": reason}
    payload.update(extra)
    return payload


def prove_named_repair(repair, observation):
    """BC-08: prove a named repair's ACTUAL content on the remote target.

    ``repair``: ``{"repair_id", "sha", "files": {path: blob_sha}}``.
    ``observation``: ``{"remote", "target_ref", "observed_head", "method":
    "ancestry"|"content_equivalence"|"squash", "contains_sha", "tree":
    {path: blob_sha}, "observed_at"}``.

    A prior baseline merge is never proof of a repair (the repair is a new
    owed incorporation). Every unobserved fact renders ``UNKNOWN`` with a
    reason; only an observed match renders ``PROVEN``.
    """
    repair = dict(repair or {})
    repair_id = str(repair.get("repair_id") or "")
    sha = str(repair.get("sha") or "")
    if not repair_id:
        return _repair_verdict(UNKNOWN, "repair_id_unobserved")
    if not _load_cohort().is_hex_sha(sha):
        return _repair_verdict(UNKNOWN, "repair_sha_not_exact_40_hex",
                               repair_id=repair_id)
    if not isinstance(observation, dict) or not observation:
        return _repair_verdict(UNKNOWN, "remote_content_unobserved",
                               repair_id=repair_id)
    if not observation.get("target_ref"):
        return _repair_verdict(UNKNOWN, "remote_target_unobserved",
                               repair_id=repair_id)
    if not observation.get("observed_head"):
        return _repair_verdict(UNKNOWN, "remote_head_unobserved",
                               repair_id=repair_id)
    method = str(observation.get("method") or "")
    if method == "baseline_only":
        return _repair_verdict(UNKNOWN,
                               "prior_baseline_merge_is_not_repair_proof",
                               repair_id=repair_id)
    if method == "ancestry":
        contains = observation.get("contains_sha")
        if contains is True:
            return _repair_verdict(PROVEN, "repair_in_target_ancestry",
                                   repair_id=repair_id)
        if contains is False:
            return _repair_verdict(CONTRADICTED,
                                   "repair_absent_from_target_ancestry",
                                   repair_id=repair_id)
        return _repair_verdict(UNKNOWN, "ancestry_unobserved",
                               repair_id=repair_id)
    if method in ("content_equivalence", "squash"):
        expected = {str(k): str(v) for k, v in (repair.get("files") or {}).items()}
        if not expected:
            return _repair_verdict(UNKNOWN, "repair_content_unobserved",
                                   repair_id=repair_id)
        tree = observation.get("tree")
        if not isinstance(tree, dict):
            return _repair_verdict(UNKNOWN, "remote_tree_unobserved",
                                   repair_id=repair_id)
        tree = {str(k): str(v) for k, v in tree.items()}
        for path in sorted(expected):
            if path not in tree:
                return _repair_verdict(UNKNOWN, "content_partially_observed:%s" % path,
                                       repair_id=repair_id)
            if tree[path] != expected[path]:
                return _repair_verdict(CONTRADICTED,
                                       "remote_content_differs:%s" % path,
                                       repair_id=repair_id)
        return _repair_verdict(PROVEN, "remote_content_equivalence",
                               repair_id=repair_id)
    return _repair_verdict(UNKNOWN, "proof_method_unobserved", repair_id=repair_id)


def target_owner(store, key, owner, now, ttl=900):
    """Acquire the single shared target owner through a real shared store.

    A local file is NOT distributed exclusion (BATCH-MERGE.md), so a
    backend that is not declared ``distributed = True`` is refused as
    ``UNKNOWN``. The store must expose ``get(key)`` and
    ``compare_and_set(key, expected, value)``. Only a won, read-back
    compare-and-set proves ownership.
    """
    key = str(key)
    owner = str(owner)
    if store is None:
        return {"state": UNKNOWN, "reason": "no_shared_lease_backend",
                "owner": owner, "key": key}
    if getattr(store, "distributed", False) is not True:
        return {"state": UNKNOWN,
                "reason": "local_file_is_not_distributed_exclusion",
                "owner": owner, "key": key}
    if not (hasattr(store, "get") and hasattr(store, "compare_and_set")):
        return {"state": UNKNOWN, "reason": "shared_lease_backend_incomplete",
                "owner": owner, "key": key}
    try:
        current = store.get(key)
    except Exception as exc:  # noqa: BLE001 - backend failure is an unknown
        return {"state": UNKNOWN, "reason": "lease_backend_error:%s"
                % type(exc).__name__, "owner": owner, "key": key}
    if current is not None:
        if not isinstance(current, dict):
            return {"state": UNKNOWN, "reason": "lease_record_malformed",
                    "owner": owner, "key": key}
        if current.get("expires", 0) > now and current.get("owner") != owner:
            return {"state": HELD, "reason": "lease_held_by_other:%s"
                    % current.get("owner"), "owner": owner, "key": key}
    value = {"owner": owner, "acquired": now, "expires": now + ttl}
    try:
        won = store.compare_and_set(key, current, value)
    except Exception as exc:  # noqa: BLE001
        return {"state": UNKNOWN, "reason": "lease_backend_error:%s"
                % type(exc).__name__, "owner": owner, "key": key}
    if not won:
        return {"state": HELD, "reason": "lease_compare_and_set_lost",
                "owner": owner, "key": key}
    try:
        read_back = store.get(key)
    except Exception as exc:  # noqa: BLE001
        return {"state": UNKNOWN, "reason": "lease_backend_error:%s"
                % type(exc).__name__, "owner": owner, "key": key}
    if read_back != value:
        return {"state": UNKNOWN, "reason": "lease_read_back_mismatch",
                "owner": owner, "key": key}
    return {"state": PROVEN, "reason": "", "owner": owner, "key": key,
            "lease": value}


def merge_due(state, repository, now, *, new_events=False, busy_until=None,
              sweep_interval=HOUR_SECONDS):
    """C-F15 supervisor takeover / merge-due without losing age on restart.

    Events (accepted candidate, named repair, CI completion, lease release)
    immediately make the owner due. A busy target stays due and rechecks
    within ten minutes or on release. Otherwise the backlog sweep is at
    most hourly. ``first_due`` is persisted so restart preserves age.
    """
    repo = str(repository)
    record = state.setdefault("merge_due", {}).setdefault(
        repo, {"first_due": None, "last_sweep": None, "last_reason": None})
    if record.get("first_due") is None:
        record["first_due"] = now
    if busy_until is not None and busy_until > now:
        next_check = min(busy_until, now + BUSY_RECHECK_SECONDS)
        record["last_reason"] = "target_busy_remains_due"
        return {"repository": repo, "due": True, "immediate": False,
                "next_check": next_check, "reason": record["last_reason"],
                "first_due": record["first_due"]}
    if new_events:
        record["last_reason"] = "event_requests_owner"
        record["last_sweep"] = now
        return {"repository": repo, "due": True, "immediate": True,
                "next_check": now, "reason": record["last_reason"],
                "first_due": record["first_due"]}
    last_sweep = record.get("last_sweep")
    if last_sweep is not None and now - last_sweep < sweep_interval:
        record["last_reason"] = "hourly_sweep_not_due"
        return {"repository": repo, "due": False, "immediate": False,
                "next_check": last_sweep + sweep_interval,
                "reason": record["last_reason"],
                "first_due": record["first_due"]}
    record["last_sweep"] = now
    record["last_reason"] = "backlog_sweep_due"
    return {"repository": repo, "due": True, "immediate": False,
            "next_check": now, "reason": record["last_reason"],
            "first_due": record["first_due"]}


def cleanup_disposition(resource):
    """Classify the four cleanup dispositions; never delete anything.

    The four cases in fixtures/cleanup.examples.json: disposable scratch,
    clean merged tree, dirty unique work, active shared consumer. Actual
    disposal belongs to T-46; this is the integration-side handoff record.
    An unobserved consumer/clean state is ``UNKNOWN``, never ``eligible``.
    """
    resource = dict(resource or {})
    resource_id = str(resource.get("id") or "")
    if not resource_id:
        return {"id": "", "disposition": UNKNOWN,
                "reason": "resource_id_unobserved"}
    consumers = resource.get("consumers")
    if consumers is None:
        return {"id": resource_id, "disposition": UNKNOWN,
                "reason": "consumer_state_unobserved"}
    active = sorted(str(c.get("id")) for c in consumers
                    if isinstance(c, dict) and c.get("state") == "active")
    if active:
        return {"id": resource_id, "disposition": "deferred",
                "reason": "consumer_active:%s" % ",".join(active)}
    unique = resource.get("has_unique_unmerged_work")
    if unique is True:
        return {"id": resource_id, "disposition": "deferred",
                "reason": "unique_unmerged_work_preserved"}
    if unique is not False:
        return {"id": resource_id, "disposition": UNKNOWN,
                "reason": "unique_work_state_unobserved"}
    clean_state = resource.get("clean_state")
    resource_type = str(resource.get("resource_type") or "")
    if resource_type == "disposable_scratch":
        return {"id": resource_id, "disposition": "eligible",
                "reason": "disposable_scratch"}
    if resource_type == "merged_worktree":
        if clean_state != "CLEAN":
            return {"id": resource_id, "disposition": UNKNOWN,
                    "reason": "clean_state_unobserved"}
        if not resource.get("remote_merge_proof_ids"):
            return {"id": resource_id, "disposition": UNKNOWN,
                    "reason": "remote_merge_proof_unobserved"}
        return {"id": resource_id, "disposition": "eligible",
                "reason": "clean_merged_tree"}
    return {"id": resource_id, "disposition": UNKNOWN,
            "reason": "resource_type_unobserved:%s" % resource_type}


def _merge_component_states(components):
    """Fold component states: any contradiction wins, then any unknown, else proven."""
    states = [str(c.get("state")) for c in components if c]
    if any(state == CONTRADICTED for state in states):
        return CONTRADICTED
    if any(state == UNKNOWN or state == HELD for state in states):
        return UNKNOWN
    return PROVEN


def build_receipt(*, repository="onboarding", owner, target, cohort, gates,
                  named_repairs=(), cleanup=(), proof=None):
    """Assemble one ``onboarding-remote-merge-receipts`` record.

    ``PROVEN`` requires every clause proven: the shared owner, the frozen
    compatible cohort, the exact independent gates, the remote target
    proof, every named repair, and every cleanup handoff. Anything
    unobserved is ``UNKNOWN`` with reasons; a contradiction is
    ``CONTRADICTED``. No aggregate ``ALL_PASS`` is ever emitted.
    """
    owner = dict(owner or {})
    target = dict(target or {})
    cohort = dict(cohort or {})
    gates = [dict(gate) for gate in gates or ()]
    named_repairs = [dict(repair) for repair in named_repairs or ()]
    cleanup = [dict(item) for item in cleanup or ()]
    proof = dict(proof or {})

    reasons = []
    if not target.get("remote"):
        reasons.append("remote_target_unobserved")
    if not target.get("before"):
        reasons.append("target_before_unobserved")
    if not target.get("after"):
        reasons.append("target_after_unobserved")
    if not cohort.get("admit"):
        reasons.append("cohort_membership_empty")
    for entry in cohort.get("unknown") or ():
        reasons.append("cohort_unknown:%s:%s"
                       % (entry.get("unit_id"), entry.get("reason")))
    for entry in cohort.get("hold") or ():
        reasons.append("cohort_held:%s:%s"
                       % (entry.get("unit_id"), entry.get("reason")))
    for gate in gates:
        if gate.get("state") != PROVEN:
            reasons.append("gate:%s:%s"
                           % (gate.get("unit_id"), gate.get("reason")))
    for repair in named_repairs:
        if repair.get("state") != PROVEN:
            reasons.append("named_repair:%s:%s"
                           % (repair.get("repair_id"), repair.get("reason")))
    for item in cleanup:
        if item.get("disposition") == UNKNOWN:
            reasons.append("cleanup:%s:%s" % (item.get("id"), item.get("reason")))
    if proof.get("state") != PROVEN:
        reasons.append("remote_proof:%s" % (proof.get("reason")
                                           or "proof_unobserved"))

    components = [owner, cohort, proof] + gates + named_repairs
    components += [{"state": UNKNOWN} if item.get("disposition") == UNKNOWN
                   else {"state": PROVEN} for item in cleanup]
    cohort_state = (UNKNOWN if cohort.get("unknown") else
                    UNKNOWN if cohort.get("hold") else
                    ADMITTED if cohort.get("admit") else UNKNOWN)
    components.append({"state": cohort_state})
    state = _merge_component_states(components)
    if reasons and state == PROVEN:
        state = UNKNOWN

    receipt = {
        "schema_version": 1,
        "artifact": ARTIFACT,
        "repository": str(repository),
        "owner": copy.deepcopy(owner),
        "target": copy.deepcopy(target),
        "candidates": [{"unit_id": uid, "sha": _sha_for(cohort, uid)}
                       for uid in cohort.get("order") or ()],
        "cohort": copy.deepcopy(cohort),
        "gates": copy.deepcopy(gates),
        "named_repairs": copy.deepcopy(named_repairs),
        "cleanup": copy.deepcopy(cleanup),
        "proof": copy.deepcopy(proof),
        "state": state,
        "reasons": reasons,
    }
    return receipt


def _sha_for(cohort, unit_id):
    """Look up the exact SHA the cohort froze for a unit, else UNKNOWN."""
    for candidate in cohort.get("candidates") or ():
        if candidate.get("unit_id") == unit_id:
            return candidate.get("sha")
    return None


def verify_receipt(receipt):
    """Re-check a receipt: shape, known state, and no false PROVEN.

    Returns ``(ok, reason)``. A ``PROVEN`` receipt must carry the artifact
    name, an owner, a target with before/after, at least one candidate and
    gate, and no reasons. An ``UNKNOWN`` receipt must name a reason.
    """
    if not isinstance(receipt, dict):
        return False, "receipt must be an object"
    if receipt.get("artifact") != ARTIFACT:
        return False, "artifact must be %r" % ARTIFACT
    state = receipt.get("state")
    if state not in (PROVEN, CONTRADICTED, UNKNOWN):
        return False, "unknown receipt state: %r" % state
    if state == PROVEN:
        if receipt.get("reasons"):
            return False, "proven receipt carries reasons"
        owner = receipt.get("owner") or {}
        if owner.get("state") != PROVEN:
            return False, "proven receipt lacks a proven owner"
        target = receipt.get("target") or {}
        if not (target.get("remote") and target.get("before")
                and target.get("after")):
            return False, "proven receipt lacks target before/after"
        if not receipt.get("candidates"):
            return False, "proven receipt has no candidates"
        if not receipt.get("gates"):
            return False, "proven receipt has no gates"
        cohort = receipt.get("cohort") or {}
        if (cohort.get("hold") or cohort.get("unknown")
                or not cohort.get("admit")):
            return False, "proven receipt carries a non-admitted cohort"
        for gate in receipt.get("gates") or ():
            if gate.get("state") != PROVEN:
                return False, "proven receipt carries a non-proven gate"
        for item in receipt.get("cleanup") or ():
            if item.get("disposition") == UNKNOWN:
                return False, "proven receipt carries an unknown cleanup"
        for repair in receipt.get("named_repairs") or ():
            if repair.get("state") != PROVEN:
                return False, "proven receipt carries a non-proven repair"
        if (receipt.get("proof") or {}).get("state") != PROVEN:
            return False, "proven receipt lacks remote proof"
    if state in (UNKNOWN, CONTRADICTED) and not receipt.get("reasons"):
        return False, "%s receipt must name a reason" % state
    return True, ""
