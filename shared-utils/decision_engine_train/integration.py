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


_HEX_DIGITS = "0123456789abcdef"
CONSUMER_STATES = ("active", "released")
UNIT_STATES = ("green", "red")


def _is_hex_sha(value):
    """Exact 40-char lowercase hex git SHA. Shape only, no lookup."""
    return (isinstance(value, str) and len(value) == 40
            and all(c in _HEX_DIGITS for c in value))


def _as_mapping(value):
    """A record mapping, or None when the shape was not observed."""
    return value if isinstance(value, dict) else None


def _as_records(value):
    """A sequence of records, or None when the shape was not observed.

    Strings and mappings are NOT record sequences: ``"nobody"`` iterating as
    characters is a malformed record, never an observed list of consumers.
    """
    if isinstance(value, (list, tuple)):
        return value
    return None

def _as_names(value):
    """A sequence of names, or None when the shape was not observed.

    Strings and mappings are NOT name sequences: ``"AB"`` iterating as
    characters is one malformed owner, never two observed owners. ``None``
    is the observed empty set (the caller passed nothing).
    """
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        return None
    names = []
    for raw in value:
        if not isinstance(raw, str) or not raw:
            return None
        names.append(raw)
    return tuple(names)

def _as_number(value):
    """A real count of seconds, or None when the shape was not observed.

    A string is never a timestamp and ``bool`` is never an interval: an
    unobserved clock is never read as an instant.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _as_hex_ref(value):
    """A git object id as observed: a hex prefix, or None when not observed.

    ``None``, an int, a bool and any non-hex string are NOT an object id.
    Length may be abbreviated, but every character must be a hex digit —
    ``"zz"`` is not a prefix of anything git wrote.
    """
    if not isinstance(value, str) or not value or len(value) > 40:
        return None
    for char in value:
        if char not in _HEX_DIGITS:
            return None
    return value


def _as_blob_map(value):
    """A ``{path: blob id}`` mapping of observed strings, or None.

    ``None`` is not a blob id and neither is an int: a content proof built
    from two unobserved values would be ``None == None``, which is not
    equivalence. Every path and every blob id must already be a non-empty
    string.
    """
    mapping = _as_mapping(value)
    if mapping is None:
        return None
    out = {}
    for path, blob in mapping.items():
        if not isinstance(path, str) or not path:
            return None
        if not isinstance(blob, str) or not blob:
            return None
        out[path] = blob
    return out


def _as_checks(raw):
    """Observed ``(name: status)`` results, or None when not observed.

    A check name is never ``None`` and a status is never ``5``: neither is
    str()-coerced into a named check, so a malformed collection can neither
    satisfy nor be mistaken for a named check result.
    """
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        pairs = []
        for entry in raw:
            record = _as_mapping(entry)
            if record is None:
                return None
            pairs.append((record.get("name"), record.get("status")))
    else:
        return None
    observed, check_list = {}, []
    for name, status in pairs:
        if not isinstance(name, str) or not name:
            return None
        if not isinstance(status, str) or not status:
            return None
        observed[name] = status
        check_list.append({"name": name, "status": status})
    return observed, check_list


def _normalise_units(units):
    """Normalise unit records. Returns ``(units, problems)``.

    A field that was not observed is a ``problems`` entry rendering
    ``UNKNOWN`` — never a silent default. In particular an absent ``files``
    list is NOT "touches nothing" (BC-02 never ran) and an absent ``state``
    is NOT "green" (BC-07 never isolated a red unit).
    """
    out, problems = [], []
    for index, raw in enumerate(units or ()):
        record = _as_mapping(raw)
        if record is None:
            problems.append(_reason("", RULE_SEPARATE_FILES,
                                    "unit_record_malformed:%d" % index))
            continue
        uid = record.get("unit_id")
        if not isinstance(uid, str) or not uid:
            problems.append(_reason("", RULE_SEPARATE_FILES,
                                    "unit_id_unobserved"))
            continue
        sha = record.get("sha")
        if not isinstance(sha, str) or not sha:
            problems.append(_reason(uid, RULE_SEPARATE_FILES,
                                    "candidate_sha_unobserved"))
            continue
        if not _is_hex_sha(sha):
            problems.append(_reason(uid, RULE_SEPARATE_FILES,
                                    "candidate_sha_not_exact_40_hex"))
            continue
        if record.get("files") is None:
            problems.append(_reason(uid, RULE_SHARED_FILE,
                                    "unit_files_unobserved"))
            continue
        files = _as_names(record.get("files"))
        if files is None:
            problems.append(_reason(uid, RULE_SHARED_FILE,
                                    "unit_files_malformed"))
            continue
        if record.get("depends_on") is None:
            deps = ()
        else:
            deps = _as_names(record.get("depends_on"))
            if deps is None:
                problems.append(_reason(uid, RULE_DEPENDENCY,
                                        "unit_depends_on_malformed"))
                continue
        if record.get("depends_on_repos") is None:
            dep_repos = ()
        else:
            dep_repos = _as_names(record.get("depends_on_repos"))
            if dep_repos is None:
                problems.append(_reason(uid, RULE_CROSS_REPO,
                                        "unit_depends_on_repos_malformed"))
                continue
        if record.get("schema") is None:
            schema = {}
        else:
            schema = _as_mapping(record.get("schema"))
            if schema is None:
                problems.append(_reason(uid, RULE_BREAKING_WRITER,
                                        "schema_record_malformed"))
                continue
        state = record.get("state")
        if state is None:
            problems.append(_reason(uid, RULE_RED_SUBSET,
                                    "unit_state_unobserved"))
            continue
        if not isinstance(state, str) or state not in UNIT_STATES:
            problems.append(_reason(uid, RULE_RED_SUBSET,
                                    "unit_state_malformed"))
            continue
        repo = record.get("repo")
        if repo is None:
            repo = ""
        elif not isinstance(repo, str) or not repo:
            problems.append(_reason(uid, RULE_CROSS_REPO,
                                    "unit_repo_malformed"))
            continue
        unit = dict(record)
        unit["unit_id"] = uid
        unit["sha"] = sha
        unit["files"] = tuple(files)
        unit["depends_on"] = tuple(deps)
        unit["depends_on_repos"] = tuple(dep_repos)
        unit["state"] = state
        unit["schema"] = dict(schema)
        unit["repo"] = repo
        out.append(unit)
    return out, problems


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
    order = list(_as_names(publication_order) or ())
    repo = unit["repo"] or repository
    producers = set()
    for dep_id in unit["depends_on"]:
        dep = by_id.get(dep_id)
        if dep is not None:
            dep_repo = dep["repo"] or repository
            if dep_repo != repo:
                producers.add(dep_repo)
    for dep_repo in _as_names(unit.get("depends_on_repos")) or ():
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
    unrelated green candidates stay admitted. A unit that does not declare
    ``files`` or ``state`` renders ``UNKNOWN`` — an unobserved field is
    never a silent default, so BC-02 and BC-07 always run. A cohort that was
    not observed at all renders ``UNKNOWN``, never ``ADMITTED``. The name
    collections follow the same law: a string is never a sequence of names,
    so ``combined_owner="AB"`` is one malformed owner, never two observed
    ones, and it renders ``UNKNOWN`` instead of collapsing a BC-02
    collision or satisfying a BC-03 contract.
    """
    raw_units = _as_records(units)
    problems = [] if raw_units is not None else [
        _reason("", RULE_SEPARATE_FILES, "cohort_unobserved")]
    norm, normalised_problems = _normalise_units(raw_units or ())
    unknown = problems + normalised_problems
    if not norm and not unknown:
        unknown.append(_reason("", RULE_SEPARATE_FILES, "cohort_empty"))
    combined_names = _as_names(combined_owner)
    if combined_names is None:
        unknown.append(_reason("", RULE_SHARED_FILE, "combined_owner_malformed"))
        combined_names = ()
    landed_names = _as_names(already_landed)
    if landed_names is None:
        unknown.append(_reason("", RULE_DEPENDENCY, "already_landed_malformed"))
        landed_names = ()
    order_names = _as_names(publication_order)
    if order_names is None:
        unknown.append(_reason("", RULE_CROSS_REPO, "publication_order_malformed"))
        order_names = ()
    hold, valid = [], []
    seen = set()
    for unit in norm:
        uid = unit["unit_id"]
        if uid in seen:
            unknown.append(_reason(uid, RULE_SEPARATE_FILES, "duplicate_unit_id"))
            continue
        seen.add(uid)
        valid.append(unit)

    by_id = {unit["unit_id"]: unit for unit in valid}
    valid_ids = set(by_id)
    landed = set(landed_names)

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
    covered = set(combined_names)
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
                                      order_names)
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
        "cross_repo_order": list(order_names),
    }


def exact_independent_gate(unit, receipt, required_checks=("unit", "integration")):
    """Prove one unit with an exact-SHA independent PASS receipt and named checks.

    Reuses ``train.validate_qc_receipt`` for the exact-SHA/independent-route
    laws. A broad ``ALL_PASS`` aggregate is not exact evidence and is
    refused. Missing receipt or missing required-check results render
    ``UNKNOWN``; a failure renders ``CONTRADICTED``. The named-check law is
    never a caller-optional knob: an empty or malformed ``required_checks``
    is an unobserved requirement and renders ``UNKNOWN``, so a gate can
    never prove on zero named checks.
    """
    record = _as_mapping(unit)
    if record is None:
        return {"unit_id": "", "state": UNKNOWN,
                "reason": "unit_record_malformed", "checks": []}
    unit_id = record.get("unit_id")
    if not isinstance(unit_id, str) or not unit_id:
        return {"unit_id": "", "state": UNKNOWN,
                "reason": "unit_id_unobserved", "checks": []}
    unit_sha = record.get("sha")
    if not isinstance(receipt, dict) or not receipt:
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "qc_receipt_unobserved", "checks": []}
    receipt_sha = receipt.get("sha")
    if unit_sha is None or not str(unit_sha):
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "candidate_sha_unobserved", "checks": []}
    if receipt_sha is None or not str(receipt_sha):
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "qc_sha_unobserved", "checks": []}
    if not _is_hex_sha(str(unit_sha)):
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "candidate_sha_not_exact_40_hex", "checks": []}
    if not _is_hex_sha(str(receipt_sha)):
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "qc_sha_not_exact_40_hex", "checks": []}
    entry = {"sha": unit_sha, "qc_receipt": receipt}
    ok, reason = validate_qc_receipt(entry)
    if not ok:
        return {"unit_id": unit_id, "state": CONTRADICTED,
                "reason": reason, "checks": []}

    parsed = _as_checks(receipt.get("checks"))
    if parsed is None:
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "required_check_results_malformed", "checks": []}
    observed, check_list = parsed
    for name in observed:
        if name.upper() in ("ALL_PASS", "ALL", "AGGREGATE"):
            return {"unit_id": unit_id, "state": CONTRADICTED,
                    "reason": "broad_all_pass_is_not_exact_evidence",
                    "checks": check_list}
    if not observed:
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "required_check_results_unobserved",
                "checks": check_list}
    required = _as_names(required_checks)
    if required is None or not required:
        return {"unit_id": unit_id, "state": UNKNOWN,
                "reason": "required_checks_unobserved", "checks": check_list}
    for name in required:
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
    record = _as_mapping(repair)
    if record is None:
        return _repair_verdict(UNKNOWN, "repair_record_malformed")
    repair = dict(record)
    repair_id = repair.get("repair_id")
    sha = repair.get("sha")
    if not isinstance(repair_id, str) or not repair_id:
        return _repair_verdict(UNKNOWN, "repair_id_unobserved")
    if not isinstance(sha, str) or not _load_cohort().is_hex_sha(sha):
        return _repair_verdict(UNKNOWN, "repair_sha_not_exact_40_hex",
                               repair_id=repair_id)
    if not isinstance(observation, dict) or not observation:
        return _repair_verdict(UNKNOWN, "remote_content_unobserved",
                               repair_id=repair_id)
    target_ref = observation.get("target_ref")
    if not isinstance(target_ref, str) or not target_ref:
        return _repair_verdict(UNKNOWN, "remote_target_unobserved",
                               repair_id=repair_id)
    if _as_hex_ref(observation.get("observed_head")) is None:
        return _repair_verdict(UNKNOWN, "remote_head_unobserved",
                               repair_id=repair_id)
    method = observation.get("method")
    if not isinstance(method, str) or not method:
        return _repair_verdict(UNKNOWN, "proof_method_unobserved",
                               repair_id=repair_id)
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
        if repair.get("files") is None:
            expected = {}
        else:
            expected = _as_blob_map(repair.get("files"))
            if expected is None:
                return _repair_verdict(UNKNOWN, "repair_content_malformed",
                                       repair_id=repair_id)
        if not expected:
            return _repair_verdict(UNKNOWN, "repair_content_unobserved",
                                   repair_id=repair_id)
        if observation.get("tree") is None:
            return _repair_verdict(UNKNOWN, "remote_tree_unobserved",
                                   repair_id=repair_id)
        tree = _as_blob_map(observation.get("tree"))
        if tree is None:
            return _repair_verdict(UNKNOWN, "remote_tree_malformed",
                                   repair_id=repair_id)
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

    An identity that was not observed is never str()-coerced into a lease:
    ``None`` is not an owner and not a key. A lease record is never read
    with silent defaults either — no ``expires`` is not "expired", and an
    unobserved holder is not "nobody" — so a live foreign lease can never
    be stolen and a malformed clock never raises.
    """
    if not isinstance(key, str) or not key:
        return {"state": UNKNOWN, "reason": "lease_key_unobserved",
                "owner": owner, "key": key}
    if not isinstance(owner, str) or not owner:
        return {"state": UNKNOWN, "reason": "lease_owner_unobserved",
                "owner": owner, "key": key}
    clock = _as_number(now)
    window = _as_number(ttl)
    if clock is None or window is None or window <= 0:
        return {"state": UNKNOWN, "reason": "lease_clock_unobserved",
                "owner": owner, "key": key}
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
        holder = current.get("owner")
        if not isinstance(holder, str) or not holder:
            return {"state": UNKNOWN, "reason": "lease_record_owner_unobserved",
                    "owner": owner, "key": key}
        if "expires" not in current:
            return {"state": UNKNOWN, "reason": "lease_expiry_unobserved",
                    "owner": owner, "key": key}
        expires = _as_number(current.get("expires"))
        if expires is None:
            return {"state": UNKNOWN, "reason": "lease_expiry_malformed",
                    "owner": owner, "key": key}
        if expires > clock and holder != owner:
            return {"state": HELD, "reason": "lease_held_by_other:%s"
                    % holder, "owner": owner, "key": key}
    value = {"owner": owner, "acquired": clock, "expires": clock + window}
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

    ``state`` is ``PROVEN`` when the schedule was determined from observed
    inputs and ``UNKNOWN`` when the caller's state store was unobserved or
    malformed — a malformed store renders ``UNKNOWN``, it never raises and
    never schedules. The clock, the busy window and the sweep interval are
    inputs of the same kind: a string is never an instant, so a malformed
    parameter renders ``UNKNOWN`` too instead of raising on a comparison.
    """
    repo = str(repository)
    unknown_result = {"repository": repo, "due": False, "immediate": False,
                      "next_check": None, "reason": "merge_state_unobserved",
                      "first_due": None, "state": UNKNOWN}
    clock = _as_number(now)
    window = _as_number(sweep_interval)
    busy = None if busy_until is None else _as_number(busy_until)
    if clock is None or window is None or window <= 0:
        return dict(unknown_result)
    if busy_until is not None and busy is None:
        return dict(unknown_result)
    store = _as_mapping(state)
    if store is None:
        return dict(unknown_result)
    root = store.get("merge_due")
    if root is None:
        root = {}
        store["merge_due"] = root
    root = _as_mapping(root)
    if root is None:
        return dict(unknown_result)
    record = root.get(repo)
    if record is None:
        record = {"first_due": None, "last_sweep": None, "last_reason": None}
        root[repo] = record
    record = _as_mapping(record)
    if record is None:
        return dict(unknown_result)
    stored_due = record.get("first_due")
    stored_sweep = record.get("last_sweep")
    if (stored_due is not None and _as_number(stored_due) is None) or (
            stored_sweep is not None and _as_number(stored_sweep) is None):
        return dict(unknown_result)
    if stored_due is None:
        stored_due = clock
        record["first_due"] = stored_due
    if busy is not None and busy > clock:
        next_check = min(busy, clock + BUSY_RECHECK_SECONDS)
        record["last_reason"] = "target_busy_remains_due"
        return {"repository": repo, "due": True, "immediate": False,
                "next_check": next_check, "reason": record["last_reason"],
                "first_due": record["first_due"], "state": PROVEN}
    if new_events:
        record["last_reason"] = "event_requests_owner"
        record["last_sweep"] = clock
        return {"repository": repo, "due": True, "immediate": True,
                "next_check": clock, "reason": record["last_reason"],
                "first_due": record["first_due"], "state": PROVEN}
    if stored_sweep is not None and clock - stored_sweep < window:
        record["last_reason"] = "hourly_sweep_not_due"
        return {"repository": repo, "due": False, "immediate": False,
                "next_check": stored_sweep + window,
                "reason": record["last_reason"],
                "first_due": record["first_due"], "state": PROVEN}
    record["last_sweep"] = clock
    record["last_reason"] = "backlog_sweep_due"
    return {"repository": repo, "due": True, "immediate": False,
            "next_check": clock, "reason": record["last_reason"],
            "first_due": record["first_due"], "state": PROVEN}


def cleanup_disposition(resource):
    """Classify the four cleanup dispositions; never delete anything.

    The four cases in fixtures/cleanup.examples.json: disposable scratch,
    clean merged tree, dirty unique work, active shared consumer. Actual
    disposal belongs to T-46; this is the integration-side handoff record.
    An unobserved consumer/clean state is ``UNKNOWN``, never ``eligible``.
    """
    record = _as_mapping(resource)
    if record is None:
        return {"id": "", "disposition": UNKNOWN,
                "reason": "resource_record_malformed"}
    resource_id = record.get("id")
    if not isinstance(resource_id, str) or not resource_id:
        return {"id": "", "disposition": UNKNOWN,
                "reason": "resource_id_unobserved"}
    if record.get("consumers") is None:
        return {"id": resource_id, "disposition": UNKNOWN,
                "reason": "consumer_state_unobserved"}
    consumers = _as_records(record.get("consumers"))
    if consumers is None:
        return {"id": resource_id, "disposition": UNKNOWN,
                "reason": "consumer_state_unobserved"}
    active = []
    for raw in consumers:
        consumer = _as_mapping(raw)
        state = consumer.get("state") if consumer is not None else None
        if consumer is None or state not in CONSUMER_STATES:
            return {"id": resource_id, "disposition": UNKNOWN,
                    "reason": "consumer_state_unobserved"}
        if state == "active":
            consumer_id = consumer.get("id")
            if not isinstance(consumer_id, str) or not consumer_id:
                return {"id": resource_id, "disposition": UNKNOWN,
                        "reason": "consumer_state_unobserved"}
            active.append(consumer_id)
    if active:
        return {"id": resource_id, "disposition": "deferred",
                "reason": "consumer_active:%s" % ",".join(sorted(active))}
    unique = record.get("has_unique_unmerged_work")
    if unique is True:
        return {"id": resource_id, "disposition": "deferred",
                "reason": "unique_unmerged_work_preserved"}
    if unique is not False:
        return {"id": resource_id, "disposition": UNKNOWN,
                "reason": "unique_work_state_unobserved"}
    clean_state = record.get("clean_state")
    resource_type = record.get("resource_type")
    if not isinstance(resource_type, str) or not resource_type:
        return {"id": resource_id, "disposition": UNKNOWN,
                "reason": "resource_type_unobserved"}
    if resource_type == "disposable_scratch":
        return {"id": resource_id, "disposition": "eligible",
                "reason": "disposable_scratch"}
    if resource_type == "merged_worktree":
        if clean_state != "CLEAN":
            return {"id": resource_id, "disposition": UNKNOWN,
                    "reason": "clean_state_unobserved"}
        proof_ids = _as_names(record.get("remote_merge_proof_ids"))
        if proof_ids is None:
            return {"id": resource_id, "disposition": UNKNOWN,
                    "reason": "remote_merge_proof_malformed"}
        if not proof_ids:
            return {"id": resource_id, "disposition": UNKNOWN,
                    "reason": "remote_merge_proof_unobserved"}
        return {"id": resource_id, "disposition": "eligible",
                "reason": "clean_merged_tree"}
    return {"id": resource_id, "disposition": UNKNOWN,
            "reason": "resource_type_unobserved:%s" % resource_type}


def _merge_component_states(components, reasons):
    """Fold component states: any contradiction wins, then any unknown, else proven.

    A component whose state is absent or unrecognised folds to ``UNKNOWN``
    **with a reason**: an unobserved component state is never a proof, and an
    ``UNKNOWN`` with no reason is a receipt ``verify_receipt`` itself rejects.
    """
    states = []
    for component in components:
        record = _as_mapping(component)
        if record is None or not isinstance(record.get("state"), str):
            states.append(None)
            continue
        states.append(record["state"])
    if any(state == CONTRADICTED for state in states):
        return CONTRADICTED
    if any(state not in (PROVEN, ADMITTED) for state in states):
        reasons.append("component_state_unobserved")
        return UNKNOWN
    return PROVEN


def _records_or_reason(value, label, reasons):
    """Records from ``value``; anything else renders ``UNKNOWN``.

    A missing collection is an observed empty set; a non-sequence or a
    non-record entry is a malformation and always carries a reason, so the
    fold can never turn it into success.
    """
    records = _as_records(value) if value is not None else ()
    if records is None:
        reasons.append("%s_unobserved" % label)
        return []
    out, malformed = [], False
    for raw in records:
        record = _as_mapping(raw)
        if record is None:
            malformed = True
            continue
        out.append(dict(record))
    if malformed:
        reasons.append("%s_record_malformed" % label)
    return out


def build_receipt(*, repository="onboarding", owner, target, cohort, gates,
                  named_repairs=(), cleanup=(), proof=None):
    """Assemble one ``onboarding-remote-merge-receipts`` record.

    ``PROVEN`` requires every clause proven: the shared owner, the frozen
    compatible cohort, the exact independent gates, the remote target
    proof, every named repair, and every cleanup handoff already
    ``eligible``. A ``deferred`` cleanup handoff is unresolved and blocks
    ``PROVEN`` exactly like ``UNKNOWN``. Every candidate carries the exact
    40-hex SHA the cohort froze. Anything unobserved or malformed is
    ``UNKNOWN`` with reasons; a contradiction is ``CONTRADICTED``. No
    aggregate ``ALL_PASS`` is ever emitted.
    """
    reasons = []
    owner = _as_mapping(owner)
    target = _as_mapping(target)
    cohort = _as_mapping(cohort)
    proof = _as_mapping(proof)
    if owner is None:
        reasons.append("owner_unobserved")
        owner = {}
    if target is None:
        reasons.append("target_unobserved")
        target = {}
    if cohort is None:
        reasons.append("cohort_unobserved")
        cohort = {}
    if proof is None:
        reasons.append("remote_proof:proof_unobserved")
        proof = {"state": UNKNOWN, "reason": "proof_unobserved"}

    gates = _records_or_reason(gates, "gate", reasons)
    named_repairs = _records_or_reason(named_repairs, "named_repair", reasons)
    cleanup = _records_or_reason(cleanup, "cleanup", reasons)

    if owner.get("state") != PROVEN:
        reasons.append("owner:%s" % (owner.get("reason") or "owner_unobserved"))
    if not isinstance(target.get("remote"), str) or not target.get("remote"):
        reasons.append("remote_target_unobserved")
    if _as_hex_ref(target.get("before")) is None:
        reasons.append("target_before_unobserved")
    if _as_hex_ref(target.get("after")) is None:
        reasons.append("target_after_unobserved")
    admit_names = _as_names(cohort.get("admit"))
    if admit_names is None:
        reasons.append("cohort_membership_malformed")
    elif not admit_names:
        reasons.append("cohort_membership_empty")
    for entry in _records_or_reason(cohort.get("unknown"), "cohort_unknown",
                                    reasons):
        reasons.append("cohort_unknown:%s:%s"
                       % (entry.get("unit_id"), entry.get("reason")))
    for entry in _records_or_reason(cohort.get("hold"), "cohort_hold", reasons):
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
        if item.get("disposition") != "eligible":
            reasons.append("cleanup:%s:%s" % (item.get("id"), item.get("reason")))
    if proof.get("state") != PROVEN:
        reasons.append("remote_proof:%s" % (proof.get("reason")
                                           or "proof_unobserved"))

    candidates = []
    order = _as_names(cohort.get("order"))
    if order is None or not order:
        reasons.append("candidate_unobserved")
        order = ()
    for uid in order:
        sha = _sha_for(cohort, uid)
        candidates.append({"unit_id": uid, "sha": sha})
        if not _is_hex_sha(sha):
            reasons.append("candidate_sha_unobserved:%s" % uid)

    components = [owner, proof] + gates + named_repairs
    components += [{"state": PROVEN if item.get("disposition") == "eligible"
                    else UNKNOWN} for item in cleanup]
    cohort_state = (UNKNOWN if cohort.get("unknown") else
                    UNKNOWN if cohort.get("hold") else
                    ADMITTED if admit_names else UNKNOWN)
    components.append({"state": cohort_state})
    state = _merge_component_states(components, reasons)
    if reasons and state == PROVEN:
        state = UNKNOWN

    receipt = {
        "schema_version": 1,
        "artifact": ARTIFACT,
        "repository": str(repository),
        "owner": copy.deepcopy(owner),
        "target": copy.deepcopy(target),
        "candidates": candidates,
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
    """Look up the exact SHA the cohort froze for a unit, else None."""
    if not isinstance(unit_id, str) or not unit_id:
        return None
    for candidate in _as_records(cohort.get("candidates")) or ():
        record = _as_mapping(candidate)
        if record is not None and record.get("unit_id") == unit_id:
            sha = record.get("sha")
            return sha if isinstance(sha, str) else None
    return None


def verify_receipt(receipt):
    """Re-check a receipt: shape, known state, and no false PROVEN.

    Returns ``(ok, reason)``. A ``PROVEN`` receipt must carry the artifact
    name, an owner, a target with before/after, at least one candidate
    carrying an exact 40-hex SHA, and at least one gate, and no reasons.
    Every cleanup handoff must already be ``eligible`` — ``deferred`` and
    ``UNKNOWN`` are both unresolved. An ``UNKNOWN`` receipt must name a
    reason. A malformed collection is a shape failure reported as
    ``(False, reason)`` — this re-check never raises, whatever the receipt
    carries.
    """
    if not isinstance(receipt, dict):
        return False, "receipt must be an object"
    if receipt.get("artifact") != ARTIFACT:
        return False, "artifact must be %r" % ARTIFACT
    state = receipt.get("state")
    if state not in (PROVEN, CONTRADICTED, UNKNOWN):
        return False, "unknown receipt state: %r" % state
    for field in ("candidates", "gates", "named_repairs", "cleanup"):
        raw = receipt.get(field)
        records = _as_records(raw)
        if raw is not None and records is None:
            return False, "receipt %s must be a list of records" % field
        for entry in records or ():
            if _as_mapping(entry) is None:
                return False, "receipt %s must be a list of records" % field
    proof = receipt.get("proof")
    if proof is not None and _as_mapping(proof) is None:
        return False, "receipt proof must be an object"
    if state == PROVEN:
        if receipt.get("reasons"):
            return False, "proven receipt carries reasons"
        owner = _as_mapping(receipt.get("owner")) or {}
        if owner.get("state") != PROVEN:
            return False, "proven receipt lacks a proven owner"
        target = _as_mapping(receipt.get("target")) or {}
        if not isinstance(target.get("remote"), str) or not target.get("remote"):
            return False, "proven receipt lacks target before/after"
        if (_as_hex_ref(target.get("before")) is None
                or _as_hex_ref(target.get("after")) is None):
            return False, "proven receipt lacks target before/after"
        candidates = _as_records(receipt.get("candidates"))
        if not candidates:
            return False, "proven receipt has no candidates"
        for candidate in candidates:
            record = _as_mapping(candidate) or {}
            if not isinstance(record.get("unit_id"), str) or not record["unit_id"]:
                return False, "proven receipt carries a candidate without a unit id"
            if not _is_hex_sha(record.get("sha")):
                return False, "proven receipt carries a candidate without an exact sha"
        if not receipt.get("gates"):
            return False, "proven receipt has no gates"
        cohort = _as_mapping(receipt.get("cohort")) or {}
        admit = _as_names(cohort.get("admit"))
        if (cohort.get("hold") or cohort.get("unknown")
                or admit is None or not admit):
            return False, "proven receipt carries a non-admitted cohort"
        for gate in receipt.get("gates") or ():
            if gate.get("state") != PROVEN:
                return False, "proven receipt carries a non-proven gate"
        for item in receipt.get("cleanup") or ():
            if item.get("disposition") == UNKNOWN:
                return False, "proven receipt carries an unknown cleanup"
            if item.get("disposition") != "eligible":
                return False, "proven receipt carries a deferred cleanup"
        for repair in receipt.get("named_repairs") or ():
            if repair.get("state") != PROVEN:
                return False, "proven receipt carries a non-proven repair"
        if (receipt.get("proof") or {}).get("state") != PROVEN:
            return False, "proven receipt lacks remote proof"
    if state in (UNKNOWN, CONTRADICTED) and not receipt.get("reasons"):
        return False, "%s receipt must name a reason" % state
    return True, ""
