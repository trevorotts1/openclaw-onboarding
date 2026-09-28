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

# Release-cohort manifest instance (spec 14.8/17.4): ties the tested ONB + CC
# SHAs/versions for one release. Root-relative so the path is repo-agnostic.
COHORT_MANIFEST_RELPATH = "release-cohort.json"

# Which candidate SHA of the manifest describes each train repository. The
# manifest carries one onb_sha and one cc_sha; a promotion in a given repo must
# be the SHA the manifest names for THAT repo, or the manifest does not describe
# the candidate (A53).
COHORT_CANDIDATE_SHA_KEY = {"onb": "onb_sha", "cc": "cc_sha"}

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


def _load_cohort():
    """Return the REAL D34 cohort module (decision_engine/modes/cohort.py).

    Package import first; file-location fallback when train.py is loaded
    standalone (offline test convention). Never a copy: the cross-repo
    pairing authority stays in D34 (14.8/A53); this module only obeys it.
    """
    try:
        from decision_engine.modes import cohort as _cohort
        return _cohort
    except ImportError:
        pass
    import importlib.util
    import sys
    existing = sys.modules.get("d33_decision_cohort")
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        "d33_decision_cohort",
        Path(__file__).resolve().parent.parent / "decision_engine"
        / "modes" / "cohort.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["d33_decision_cohort"] = module
    spec.loader.exec_module(module)
    return module

def _load_cohort_manifest(repo_root=None):
    """Read + validate the release-cohort manifest INSTANCE (14.8/17.4).

    The committed instance lives at ``<repo_root>/release-cohort.json``
    (COHORT_MANIFEST_RELPATH). ``repo_root`` defaults to this file's
    repo root, the same convention
    ``shared-utils/cc_compat.py::load_cc_compat`` uses for cc-compat.json.

    Returns the manifest dict, already accepted by the REAL D34
    validator, or None when no instance is committed. Raises ValueError
    when one exists but the validator rejects it: a malformed cross-repo
    pairing fails closed, it is never silently ignored.
    """
    root = Path(repo_root) if repo_root is not None else (
        Path(__file__).resolve().parents[2])
    path = root / COHORT_MANIFEST_RELPATH
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("cohort manifest unreadable at %s: %s"
                         % (path, exc))
    ok, errors = _load_cohort().validate_cohort(manifest)
    if not ok:
        raise ValueError("cohort manifest invalid at %s: %s"
                         % (path, "; ".join(errors)))
    return manifest

def check_release_cohort(repo_root=None, pairing=None, handshake_ok=False,
                         repository=None, candidate_sha=None):
    """Load the committed instance and fail closed unless it proves the pair.

    Returns the manifest dict for ``promote(cohort=...)``. Raises when an
    instance is committed but does not validate, when its exact tested
    pair is not the pair being released, or when ``candidate_sha`` is not
    the SHA the instance names for ``repository`` — a release can never
    ride on an untested, half-promoted, or different-revision pairing
    (14.8/A53). Returns None when no instance is committed, so the
    caller's absence recording is unchanged.

    ``handshake_ok`` is the caller's observed result of the live
    capability/version handshake (bridge ``--capability`` against the CC
    probe); it is deliberately NOT a manifest field, and it defaults to
    False so an unproven handshake fails closed rather than activating.

    ``repository``/``candidate_sha`` bind the check to the exact candidate
    being released. The instance describes ONE candidate per repository;
    when the caller names the candidate it is about to activate, that
    candidate must be the one the instance describes (exact equality, per
    this module's no-fuzzy-match rule). Omitting both keeps the historical
    instance-only scope; naming one without the other raises.
    """
    cm = _load_cohort()
    cohort = _load_cohort_manifest(repo_root)
    if cohort is None:
        return None
    ok, errors = cm.validate_cohort(cohort)
    if not ok:
        raise ValueError("cohort manifest invalid: %s" % "; ".join(errors))
    if pairing is None:
        pairing = cm.PAIR_NEW_NEW
    tested = cohort.get("tested_pairs") or [
        (cohort["onb_sha"], cohort["cc_sha"])]
    verdict = cm.evaluate_pairing(
        pairing=pairing, onb_sha=cohort["onb_sha"], cc_sha=cohort["cc_sha"],
        tested_pairs=tested, handshake_ok=bool(handshake_ok))
    if verdict["behavior"] != cm.BEHAVIOR_FULL_CONTRACT:
        raise ValueError(
            "half-promoted pair must not activate: %s (pairing=%s, onb=%s, "
            "cc=%s)" % (verdict["reason"], pairing, cohort["onb_sha"],
                        cohort["cc_sha"]))
    _require_exact_candidate(cohort, repository, candidate_sha)
    return cohort


def _require_exact_candidate(cohort, repository, candidate_sha):
    """Refuse a candidate the release-cohort instance does not describe.

    Exact string equality against the SHA the instance names for
    ``repository``; a different revision of the same release is still a
    different candidate (A53). Both arguments must be given together, and
    ``repository`` must map to one of the pair — an unknown repository
    cannot be governed by the instance, so it fails closed rather than
    being waved through.
    """
    if repository is None and candidate_sha is None:
        return
    if repository is None or candidate_sha is None:
        raise ValueError(
            "cohort candidate binding requires both repository and "
            "candidate_sha (got repository=%r, candidate_sha=%r)"
            % (repository, candidate_sha))
    key = COHORT_CANDIDATE_SHA_KEY.get(str(repository))
    if key is None:
        raise ValueError(
            "repository %r is not part of the release-cohort pair (expected "
            "one of %r)" % (repository, sorted(COHORT_CANDIDATE_SHA_KEY)))
    described = cohort[key]
    if str(candidate_sha) != described:
        raise ValueError(
            "candidate %s is not the pair the release-cohort instance "
            "describes: instance %s=%s, candidate=%s"
            % (candidate_sha, key, described, candidate_sha))

def promote(state, repository, batch_id, final_main_sha, force_push=False,
            cohort=None, pairing=None, handshake_ok=False):
    """Promote only with PASS tests on the exact candidate plus independent approval.

    Never force-push: force_push=True is rejected outright.

    ``cohort`` (14.8/A53) — optional release-cohort manifest dict
    (``onb_sha``/``cc_sha`` exact 40-hex, ``onb_version``/``cc_version``/
    ``contract`` non-empty, optional ``tested_pairs`` list of exact
    ``(onb_sha, cc_sha)`` tuples). When supplied, the REAL D34 cohort
    validator decides activation: a new+new pair is refused unless its
    exact tested pair exists and the capability/version handshake passed —
    a half-promoted pair must never activate an incompatible feature. A
    new+old or old+new pair promotes on the compatible-fallback behaviour
    with the truthful capability state recorded. When omitted, the
    manifest records ``cohort.checked = False`` so the absence of
    cross-repo evidence is visible rather than silent.

    This function does NOT call :func:`check_release_cohort`: ``cohort``
    arrives already loaded from the caller, and ``repository`` (below) is
    this repo's train lane, not a release-cohort repository key. So the
    candidate-pair binding that function now offers governs only where a
    caller consults it — it does not govern activation here (A53). The
    committed release-cohort manifest INSTANCE
    (``<repo root>/release-cohort.json``) is validated by
    :func:`check_release_cohort`, which binds a release to the exact tested
    ONB+CC pair the instance names (14.8/17.4).
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

    cohort_record = {"checked": False, "reason": "no_cohort_manifest"}
    if cohort is not None:
        cm = _load_cohort()
        ok, errors = cm.validate_cohort(cohort)
        if not ok:
            raise ValueError("cohort manifest invalid: %s" % "; ".join(errors))
        tested = cohort.get("tested_pairs")
        if not tested:
            tested = [(cohort["onb_sha"], cohort["cc_sha"])]
        verdict = cm.evaluate_pairing(
            pairing=pairing, onb_sha=cohort["onb_sha"],
            cc_sha=cohort["cc_sha"], tested_pairs=tested,
            handshake_ok=bool(handshake_ok))
        if verdict["behavior"] != cm.BEHAVIOR_FULL_CONTRACT and pairing == cm.PAIR_NEW_NEW:
            raise ValueError(
                "half-promoted pair must not activate: %s (pairing=%s, "
                "onb=%s, cc=%s)"
                % (verdict["reason"], pairing, cohort["onb_sha"],
                   cohort["cc_sha"]))
        cohort_record = {
            "checked": True,
            "pairing": pairing,
            "behavior": verdict["behavior"],
            "capability": verdict["capability"],
            "reason": verdict["reason"],
            "exact_match": verdict["exact_match"],
            "onb_sha": cohort["onb_sha"],
            "cc_sha": cohort["cc_sha"],
        }

    manifest = copy.deepcopy(manifest)
    manifest["promotion"] = {"final_main_sha": final_main_sha, "forced": False,
                             "cohort": cohort_record}
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
