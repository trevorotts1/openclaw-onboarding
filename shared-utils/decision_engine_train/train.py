"""Portable train core: per-repo QC-SHA queues, 900s windows, immutable manifests.

Standard library only. No git, subprocess, network, wall-clock reads inside
decisions (callers pass ``now``). Two repos collect concurrently; each repo
holds its own main-writer lease so batches never compete.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

WINDOW_SECONDS = 900
TRAIN_ROUTE = "haiku-chain"
INDEPENDENT_ROUTE = "sonnet-chain"
OUTCOMES = ("empty", "collected", "in_flight", "blocked", "promoted")

MANIFEST_SCHEMA = (
    "batch_id",
    "repository",
    "base_main_sha",
    "feature_shas",
    "unit_ids",
    "dependency_closure",
    "qc_receipts",
    "policy_version",
    "schema_version",
    "compat_version",
    "integration_sha",
    "test_results",
    "integration_qc",
    "promotion",
    "excluded",
)


def quarter_window(now):
    """Floor a UTC epoch timestamp to its 15-minute window start."""
    return int(now // WINDOW_SECONDS) * WINDOW_SECONDS


def window_start_utc(now):
    return quarter_window(now)


def new_state():
    """Empty persisted train state. All mutation goes through functions below."""
    return {"windows": {}, "leases": {}, "queue": {}, "batches": {}}


def save_state(state, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        "w", dir=str(path.parent), delete=False, encoding="utf-8"
    )
    try:
        json.dump(state, tmp, indent=2, sort_keys=True)
        tmp.close()
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
    return str(path)


def load_state(path):
    with open(path, encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict):
        raise ValueError("train state must be an object")
    for key in ("windows", "leases", "queue", "batches"):
        if key not in state or not isinstance(state[key], dict):
            raise ValueError("train state missing %r" % key)
    return state


def enqueue(state, repository, unit_id, sha, qc_receipt, dependencies=()):
    """Add one exact-SHA unit with its independent QC receipt to a repo queue."""
    repo = str(repository)
    queue = state["queue"].setdefault(repo, [])
    entry = {
        "unit_id": str(unit_id),
        "sha": str(sha),
        "qc_receipt": copy.deepcopy(dict(qc_receipt)),
        "dependencies": [str(d) for d in dependencies],
    }
    for i, old in enumerate(queue):
        if old["unit_id"] == entry["unit_id"]:
            queue[i] = entry
            return entry
    queue.append(entry)
    return entry


def validate_qc_receipt(entry):
    """An entry is eligible only with a matching independent PASS receipt.

    Changed SHA loses eligibility: receipt must name this exact SHA, carry
    verdict PASS, and come from the independent reviewer route. Anything
    else fails closed with a reason string.
    """
    receipt = entry.get("qc_receipt") or {}
    if receipt.get("verdict") != "PASS":
        return False, "qc verdict is not PASS"
    if receipt.get("reviewer_route") != INDEPENDENT_ROUTE:
        return False, "qc reviewer is not %s" % INDEPENDENT_ROUTE
    if not receipt.get("reviewer"):
        return False, "qc reviewer identity missing"
    if receipt.get("sha") != entry.get("sha"):
        return False, "changed SHA loses eligibility"
    return True, ""


def select_eligible(state, repository):
    """Split one repo queue into (eligible, excluded) without mutating state."""
    eligible, excluded = [], []
    for entry in state["queue"].get(str(repository), []):
        ok, reason = validate_qc_receipt(entry)
        if ok:
            eligible.append(copy.deepcopy(entry))
        else:
            excluded.append(
                {"unit_id": entry["unit_id"], "sha": entry["sha"], "reason": reason}
            )
    return eligible, excluded


def compose_batch(eligible, requested=(), policy_version="", schema_version="",
                  compat_version="", repository="", base_main_sha="", batch_id=""):
    """Close dependencies, order deterministically, freeze an immutable manifest.

    Units whose dependencies are missing or ineligible are excluded with an
    actionable reason; their exclusion never blocks independent units.
    """
    by_id = {e["unit_id"]: e for e in eligible}
    wanted = list(requested) if requested else sorted(by_id)
    included, excluded, visited, failed = [], [], set(), set()

    def visit(uid, stack):
        if uid in visited:
            return uid not in failed
        if uid in stack:
            failed.add(uid)
            excluded.append({"unit_id": uid, "sha": None,
                             "reason": "dependency cycle: %s" % "->".join(stack + (uid,))})
            visited.add(uid)
            return False
        entry = by_id.get(uid)
        if entry is None:
            if not stack:
                failed.add(uid)
                excluded.append({"unit_id": uid, "sha": None,
                                 "reason": "unit not in eligible queue"})
            visited.add(uid)
            return False
        ok = True
        for dep in entry.get("dependencies", ()):  # ponytail: DAG only; cycles park, no partial order attempted
            if not visit(dep, stack + (uid,)):
                ok = False
        visited.add(uid)
        if not ok:
            failed.add(uid)
            excluded.append({"unit_id": uid, "sha": entry["sha"],
                             "reason": "ineligible or missing dependency"})
            return False
        included.append(entry)
        return True

    for uid in wanted:
        visit(uid, ())

    included.sort(key=lambda e: e["unit_id"])
    manifest = {
        "batch_id": batch_id,
        "repository": repository,
        "base_main_sha": base_main_sha,
        "feature_shas": [e["sha"] for e in included],
        "unit_ids": [e["unit_id"] for e in included],
        "dependency_closure": {e["unit_id"]: list(e.get("dependencies", ())) for e in included},
        "qc_receipts": {e["unit_id"]: copy.deepcopy(e["qc_receipt"]) for e in included},
        "policy_version": policy_version,
        "schema_version": schema_version,
        "compat_version": compat_version,
        "integration_sha": None,
        "test_results": None,
        "integration_qc": None,
        "promotion": None,
        "excluded": excluded,
    }
    return manifest


def freeze(manifest):
    """Return a deep-frozen copy; callers must treat manifests as immutable."""
    return copy.deepcopy(manifest)


def verify_manifest(manifest):
    """Check section 14.5 shape and internal consistency. Returns (ok, reason)."""
    if not isinstance(manifest, dict):
        return False, "manifest must be an object"
    for key in MANIFEST_SCHEMA:
        if key not in manifest:
            return False, "manifest missing %r" % key
    n = len(manifest["unit_ids"])
    if not (len(manifest["feature_shas"]) == n == len(manifest["qc_receipts"])):
        return False, "unit/sha/receipt counts disagree"
    if sorted(manifest["unit_ids"]) != list(manifest["unit_ids"]):
        return False, "unit_ids not in deterministic order"
    for uid in manifest["unit_ids"]:
        receipt = manifest["qc_receipts"].get(uid) or {}
        if receipt.get("verdict") != "PASS":
            return False, "unit %s lacks PASS receipt" % uid
        if receipt.get("reviewer_route") != INDEPENDENT_ROUTE:
            return False, "unit %s lacks independent receipt" % uid
    for uid, sha in zip(manifest["unit_ids"], manifest["feature_shas"]):
        if manifest["qc_receipts"][uid].get("sha") != sha:
            return False, "unit %s receipt SHA mismatch" % uid
    return True, ""


def acquire_lease(state, repository, owner, now, ttl=WINDOW_SECONDS):
    """One main writer per repo. Returns (ok, reason); never shared across repos."""
    leases = state["leases"]
    repo = str(repository)
    current = leases.get(repo)
    if current is not None and now < current["expires"] and current["owner"] != owner:
        return False, "lease held by %s" % current["owner"]
    leases[repo] = {"owner": str(owner), "acquired": now, "expires": now + ttl}
    return True, ""


def release_flight(state, repository, owner):
    repo = str(repository)
    current = state["leases"].get(repo)
    if current is None or current["owner"] != owner:
        raise ValueError("no lease held by %s on %s" % (owner, repo))
    del state["leases"][repo]
    flight = state["windows"].get(repo, {}).get("in_flight")
    state["windows"].setdefault(repo, {})["in_flight"] = None
    return flight


def tick(state, repository, now, owner="train"):
    """Collect one repo tick: empty/collected/in_flight, persisted windows.

    Restart coalescing: a tick in the same quarter window with an unchanged
    eligible fingerprint reuses the last outcome instead of composing a
    duplicate batch.
    """
    repo = str(repository)
    window = quarter_window(now)
    eligible, excluded = select_eligible(state, repo)
    fingerprint = "|".join(
        "%s@%s" % (e["unit_id"], e["sha"]) for e in sorted(eligible, key=lambda e: e["unit_id"])
    )
    w = state["windows"].setdefault(repo, {})
    if w.get("in_flight") is not None:
        w["last_window"] = window
        return {"outcome": "in_flight", "window": window,
                "batch_id": w["in_flight"], "excluded": excluded}
    if (w.get("last_window") == window and w.get("last_fingerprint") == fingerprint
            and "last_outcome" in w):
        return {"outcome": w["last_outcome"], "window": window,
                "batch_id": w.get("last_batch_id"), "excluded": excluded,
                "coalesced": True}
    if not eligible:
        w.update({"last_window": window, "last_fingerprint": fingerprint,
                  "last_outcome": "empty", "last_batch_id": None})
        return {"outcome": "empty", "window": window, "batch_id": None, "excluded": excluded}
    ok, reason = acquire_lease(state, repo, owner, now)
    if not ok:
        w.update({"last_window": window, "last_fingerprint": fingerprint,
                  "last_outcome": "blocked", "last_batch_id": None})
        return {"outcome": "blocked", "window": window, "batch_id": None,
                "reason": reason, "excluded": excluded}
    batch_id = "%s-%d" % (repo, window)
    manifest = compose_batch(eligible, repository=repo, batch_id=batch_id)
    key = "%s/%s" % (repo, batch_id)
    state["batches"][key] = freeze(manifest)
    w.update({"last_window": window, "last_fingerprint": fingerprint,
              "last_outcome": "collected", "last_batch_id": batch_id,
              "in_flight": batch_id})
    return {"outcome": "collected", "window": window, "batch_id": batch_id,
            "manifest": manifest, "excluded": excluded}


def collect_all(state, repositories, now, owner="train"):
    """Tick every repo independently; one repo never blocks another's outcome."""
    return {repo: tick(state, repo, now, owner="%s:%s" % (owner, repo))
            for repo in repositories}


def record_tests(state, repository, batch_id, integration_sha, results):
    key = "%s/%s" % (repository, batch_id)
    manifest = state["batches"].get(key)
    if manifest is None:
        raise ValueError("unknown batch %s" % key)
    if manifest["integration_sha"] is not None:
        raise ValueError("integration candidate already recorded; conflicts need a new batch")
    manifest = copy.deepcopy(manifest)
    manifest["integration_sha"] = integration_sha
    manifest["test_results"] = copy.deepcopy(results)
    state["batches"][key] = manifest
    return manifest


def attach_integration_qc(state, repository, batch_id, reviewer, reviewer_route, verdict,
                          detail=""):
    """Independent Sonnet approval of the exact candidate. Train route cannot approve."""
    if reviewer_route != INDEPENDENT_ROUTE:
        raise ValueError("integration QC requires %s reviewer" % INDEPENDENT_ROUTE)
    key = "%s/%s" % (repository, batch_id)
    manifest = state["batches"].get(key)
    if manifest is None:
        raise ValueError("unknown batch %s" % key)
    manifest = copy.deepcopy(manifest)
    manifest["integration_qc"] = {"reviewer": reviewer, "reviewer_route": reviewer_route,
                                  "verdict": verdict, "detail": detail,
                                  "integration_sha": manifest["integration_sha"]}
    state["batches"][key] = manifest
    return manifest


def promote(state, repository, batch_id, final_main_sha, force_push=False):
    """Promote only with PASS tests on the exact candidate plus independent approval.

    Never force-push: force_push=True is rejected outright.
    """
    if force_push:
        raise ValueError("force-push is never permitted")
    key = "%s/%s" % (repository, batch_id)
    manifest = state["batches"].get(key)
    if manifest is None:
        raise ValueError("unknown batch %s" % key)
    ok, reason = verify_manifest(manifest)
    if not ok:
        raise ValueError("unpromotable batch: %s" % reason)
    qc = manifest.get("integration_qc") or {}
    if qc.get("verdict") != "PASS" or qc.get("reviewer_route") != INDEPENDENT_ROUTE:
        raise ValueError("promotion requires independent %s approval" % INDEPENDENT_ROUTE)
    if qc.get("integration_sha") != manifest.get("integration_sha"):
        raise ValueError("integration QC approval is for a different candidate tree")
    results = manifest.get("test_results") or {}
    if not results or any(r.get("status") != "pass" for r in results.get("checks", [])):
        raise ValueError("promotion requires passing tests on the exact candidate")
    manifest = copy.deepcopy(manifest)
    manifest["promotion"] = {"final_main_sha": final_main_sha, "forced": False}
    state["batches"][key] = manifest
    w = state["windows"].setdefault(str(repository), {})
    w.update({"last_outcome": "promoted", "last_batch_id": batch_id, "in_flight": None})
    return manifest


def isolate_failure(eligible, failed_unit_id):
    """Park only the failed unit plus its dependents; keep independent work eligible."""
    by_id = {e["unit_id"]: e for e in eligible}
    if failed_unit_id not in by_id:
        raise ValueError("unknown unit %s" % failed_unit_id)
    parked = {failed_unit_id}
    changed = True
    while changed:  # ponytail: queues are small; BFS with deque on growth
        changed = False
        for e in eligible:
            if e["unit_id"] not in parked and any(
                    d in parked for d in e.get("dependencies", ())):
                parked.add(e["unit_id"])
                changed = True
    remaining = [e for e in eligible if e["unit_id"] not in parked]
    parked_entries = [by_id[u] for u in sorted(parked)]
    return parked_entries, remaining


def amend(state, repository, unit_id, new_sha):
    """A changed feature SHA loses eligibility until re-reviewed (receipt still old)."""
    for entry in state["queue"].get(str(repository), []):
        if entry["unit_id"] == str(unit_id):
            entry["sha"] = str(new_sha)
            return entry
    raise ValueError("unknown unit %s" % unit_id)
