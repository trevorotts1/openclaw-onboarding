#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""collect_launch_receipts.py — aggregate specialist page-results into a
launch checkpoint (spec 06 S49-09; schema page-result 1.0).

A result only counts when it ECHOES its request: same request_id, input_hash,
page_id, launch and revision. A result authored and "reviewed" by the same
session never counts as independently reviewed — independent_review=true
requires a different, named reviewer session (an artifact's reviewer is
never its author). Proof classes are ordered L0 < L1 < ... < L5, and the
checkpoint reports the WEAKEST link per role honestly: a launch is only as
proven as its least-proven page.

Checkpoint rollups (per launch revision):
  roles_expected (from the dispatch manifest), roles_reported,
  missing_roles, blocked_roles, aggregate_status —
  one of: not_started, in_progress, authored, locally_verified,
  installed_test_verified, ready_for_activation, live_verified, blocked.
ready_for_activation additionally requires independent review on every
role. The checkpoint is evidence for the watchdog's progress sample; it
never declares a merge or an activation by itself.

Prompt items (PP-T3, Q11): a producing page may also emit provider-neutral
asset receipts (doc 02 section 10; schema prompt-asset-receipt 1.0), one
per prompt-produced asset. collect() accepts them via asset_receipts and
closes a prompt item only when the receipt echoes its page request's
identity (tenant, launch, revision, page), its prompt_hash agrees with
the prompt artifact recorded in the page's page-result, its provider
identifiers are honest (a KIE task ID recorded only where KIE issued
one; an absent identifier recorded as absent, never fabricated), and its
budget_decision CITES the one governing prompt policy as
{decision, prompt_policy_id, registry_entry_hash}. Since the Q1 ruling
(2026-10-17) that citation names the ONE governing policy (the KIE
rule-12 band); this module performs NO policy selection, NO policy
evaluation, and invokes NO prompt validator (S49's Q6 position is
unchanged). Decision values are registry verdict strings only: layer-
local exit codes, numeric or exit-code-shaped, are refused by name, as
is a citation missing either its policy id or its entry hash. When a
registry artifact is supplied, the cited entry is resolved in it and
the cited hash is verified (SHA-256 over canonical JSON, the entry_hash
field itself excluded).

Deterministic, stdlib only. Exit 0 ok, 2 violation, 3 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

STATUSES = ("authored", "locally_verified", "installed_test_verified",
            "ready_for_activation", "live_verified", "blocked")
LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
_RESULT_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                  "revision", "request_id", "input_hash", "page_id", "status",
                  "artifacts", "author_session", "reviewer_session",
                  "independent_review", "proof_class", "blockers",
                  "native_bindings_ref", "test_only")


class ReceiptError(ValueError):
    pass


def validate_result(res: Any, request: Optional[Dict[str, Any]]) -> List[str]:
    fails: List[str] = []
    if not isinstance(res, dict):
        return ["result is not an object"]
    for f in _RESULT_FIELDS:
        if f not in res:
            fails.append(f"result missing field {f!r}")
    if fails:
        return fails
    if res["schema_version"] != "1.0":
        fails.append("result schema_version is not 1.0")
    if res["status"] not in STATUSES:
        fails.append(f"unknown result status {res['status']!r}")
    if res["proof_class"] not in LEVELS:
        fails.append(f"unknown proof_class {res['proof_class']!r}")
    for a in res["artifacts"]:
        if not isinstance(a, dict) or "path" not in a or "sha256" not in a:
            fails.append("an artifact entry lacks path/sha256")
    if res["independent_review"]:
        if not res["reviewer_session"]:
            fails.append("independent_review claimed with no reviewer session")
        elif res["reviewer_session"] == res["author_session"]:
            fails.append("independent_review claimed but reviewer == author "
                         "(an artifact's reviewer is never its author)")
    if request is not None:
        for f in ("request_id", "input_hash", "page_id", "launch_id",
                  "revision", "tenant_id", "location_id"):
            if f in request and res[f] != request[f]:
                fails.append(f"result does not echo its request on {f}: "
                             f"{res[f]!r} != {request[f]!r}")
        if "test_only" in request and res["test_only"] != request["test_only"]:
            fails.append("result test_only disagrees with its request")
    return fails


# --- PP-T3 (Q11) prompt-item asset receipts -------------------------------
# A prompt item closes only through an asset receipt satisfying S49's
# filed Q11 acceptance rules (prompt-policy answers, section 1) and the
# registry citation rule: every budget decision cites the policy_id AND
# the entry_hash; a decision missing either is not acceptable here.

_RECEIPT_FIELDS = ("schema_version", "tenant_id", "launch_id", "revision",
                   "page_id", "requested_provider", "requested_model",
                   "actual_provider", "actual_model", "mode",
                   "request_metadata", "provider_receipt_ids", "result_hash",
                   "result_dimensions", "budget_decision", "output_path",
                   "prompt_artifact_path", "prompt_hash",
                   "independent_visual_qc")
_BUDGET_DECISION_FIELDS = ("decision", "prompt_policy_id",
                           "registry_entry_hash")
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_EXIT_CODE_SHAPE = re.compile(r"^-?\d+$")


def compute_entry_hash(entry: Dict[str, Any]) -> str:
    """Q13 entry hash: SHA-256 of the entry serialized as canonical JSON
    (keys sorted, comma and colon separators, UTF-8), with the entry_hash
    field itself excluded. Every other field, including provenance, is
    inside the hash."""
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def find_registry_entry(registry: Optional[Dict[str, Any]],
                        policy_id: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(registry, dict):
        return None
    for entry in registry.get("entries", []):
        if isinstance(entry, dict) and entry.get("policy_id") == policy_id:
            return entry
    return None


def validate_budget_decision(bd: Any,
                             registry: Optional[Dict[str, Any]] = None
                             ) -> List[str]:
    """A budget decision is a CITATION of the one governing policy, never
    a selection and never an evaluation: it names the governing
    prompt_policy_id and cites that registry entry's hash. Decision
    values are registry verdict strings only; layer-local exit codes
    (numeric values, or strings shaped like exit codes) are refused by
    name, as is a citation missing either of its halves. When a registry
    artifact is supplied, the entry is resolved in it and the cited hash
    and verdict are verified against it."""
    if bd is None:
        return ["budget_decision is absent: a prompt item cannot close "
                "without a budget_decision naming prompt_policy_id and "
                "registry_entry_hash"]
    if not isinstance(bd, dict):
        return ["budget_decision is not an object"]
    fails: List[str] = []
    for f in bd:
        if f not in _BUDGET_DECISION_FIELDS:
            fails.append(f"budget_decision carries unknown field {f!r}")
    if "decision" not in bd:
        fails.append("budget_decision missing decision")
    else:
        decision = bd["decision"]
        if not isinstance(decision, str):
            fails.append(f"budget_decision decision {decision!r} is not a "
                         "registry verdict string: layer-local exit codes "
                         "are refused as decision values")
        elif not decision.strip():
            fails.append("budget_decision decision is blank: no verdict "
                         "is cited")
        elif _EXIT_CODE_SHAPE.match(decision.strip()):
            fails.append(f"budget_decision decision {decision!r} is an "
                         "exit-code-shaped value: layer-local exit codes "
                         "are refused as decision values")
    if "prompt_policy_id" not in bd:
        fails.append("budget_decision missing prompt_policy_id: a "
                     "citation must name the governing policy")
    elif not isinstance(bd["prompt_policy_id"], str) or \
            not bd["prompt_policy_id"].strip():
        fails.append("budget_decision prompt_policy_id is not a "
                     "non-empty string")
    if "registry_entry_hash" not in bd:
        fails.append("budget_decision missing registry_entry_hash: a "
                     "citation must cite the registry entry hash "
                     "alongside the policy id")
    elif not isinstance(bd["registry_entry_hash"], str) or \
            not _HEX64.match(bd["registry_entry_hash"]):
        fails.append("budget_decision registry_entry_hash is not a "
                     "64-character lowercase hex SHA-256")
    if fails:
        return fails
    if registry is not None:
        policy_id = bd["prompt_policy_id"]
        entry = find_registry_entry(registry, policy_id)
        if entry is None:
            fails.append(f"budget_decision names prompt_policy_id "
                         f"{policy_id!r}, which no entry in the supplied "
                         "registry carries")
            return fails
        if entry.get("entry_status") != "active":
            fails.append(f"budget_decision cites registry entry "
                         f"{policy_id!r} whose entry_status is "
                         f"{entry.get('entry_status')!r}: only active "
                         "entries may be resolved by a new run")
        if entry.get("entry_hash") != compute_entry_hash(entry):
            fails.append(f"registry entry {policy_id!r} fails its own "
                         "entry_hash check against the supplied registry")
        if bd["registry_entry_hash"] != entry.get("entry_hash"):
            fails.append(f"budget_decision registry_entry_hash does not "
                         f"match the hash of registry entry {policy_id!r}")
        values = (entry.get("budget_decision") or {}).get("decision_values")
        if isinstance(values, list) and bd["decision"] not in values:
            fails.append(f"budget_decision decision {bd['decision']!r} is "
                         f"not one of registry entry {policy_id!r}'s "
                         "decision_values (unknown verdict string)")
    return fails


def validate_asset_receipt(receipt: Any, request: Optional[Dict[str, Any]],
                           result: Optional[Dict[str, Any]],
                           registry: Optional[Dict[str, Any]] = None
                           ) -> List[str]:
    """Q11 acceptance rules for one prompt item's asset receipt (doc 02
    section 10 fields): identity echo against its page request, prompt
    hash agreement with the prompt artifact named in the page-result,
    provider identifier honesty, and a budget_decision that cites the
    governing policy (see validate_budget_decision)."""
    fails: List[str] = []
    if not isinstance(receipt, dict):
        return ["asset receipt is not an object"]
    for f in _RECEIPT_FIELDS:
        if f not in receipt:
            fails.append(f"asset receipt missing field {f!r}")
    if fails:
        return fails
    if receipt["schema_version"] != "1.0":
        fails.append("asset receipt schema_version is not 1.0")
    if request is not None:
        for f in ("tenant_id", "launch_id", "revision", "page_id"):
            if f in request and receipt[f] != request[f]:
                fails.append(f"asset receipt does not echo its request "
                             f"on {f}: {receipt[f]!r} != {request[f]!r}")
    # Provider identifier honesty (doc 02 section 10; the A23 rule): a
    # KIE task ID is recorded only where KIE actually issued one; an
    # absent identifier is recorded as absent (null), never fabricated.
    ids = receipt["provider_receipt_ids"]
    if not isinstance(ids, dict):
        fails.append("provider_receipt_ids is not an object")
    else:
        task_id = ids.get("kie_task_id")
        if task_id is not None:
            if not isinstance(task_id, str) or not task_id.strip():
                fails.append("provider_receipt_ids kie_task_id is claimed "
                             "but is not a non-empty string")
            elif "kie" not in str(receipt["actual_provider"]).lower():
                fails.append(f"provider_receipt_ids claims a KIE task ID "
                             f"but actual_provider is "
                             f"{receipt['actual_provider']!r}: a task ID "
                             "recorded where the provider issued none is "
                             "fabricated")
    # Prompt hash agreement: the receipt's prompt_hash must equal the
    # sha256 of the prompt artifact it names in the page-result.
    if result is not None:
        artifacts = {a.get("path"): a.get("sha256")
                     for a in result.get("artifacts", [])
                     if isinstance(a, dict)}
        named = receipt["prompt_artifact_path"]
        if named not in artifacts:
            fails.append(f"prompt artifact {named!r} is not among the "
                         "page-result's artifacts")
        elif artifacts[named] != receipt["prompt_hash"]:
            fails.append("prompt_hash does not agree with the prompt "
                         f"artifact {named!r} in the page-result")
    fails.extend(validate_budget_decision(receipt["budget_decision"],
                                           registry))
    return fails


def _manifest_requests(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Echo anchors carried by the dispatch manifest itself (request_id,
    input_hash, page_id per request, plus the manifest's launch/revision).
    Echo validation ALWAYS runs against at least these — the guarantee in
    this module's docstring never depends on the caller volunteering the
    full requests map (review D6b)."""
    return {r["request_id"]: {"request_id": r["request_id"],
                              "input_hash": r["input_hash"],
                              "page_id": r["page_id"],
                              "launch_id": manifest["launch_id"],
                              "revision": manifest["revision"]}
            for r in manifest["requests"]}


def collect(manifest: Dict[str, Any], results: List[Dict[str, Any]],
            requests: Optional[Dict[str, Dict[str, Any]]] = None,
            asset_receipts: Optional[List[Dict[str, Any]]] = None,
            registry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """manifest: the dispatch manifest. results: page-result dicts.
    requests: optional request_id -> request map for FULL echo validation
    (adds tenant/location/test_only); when omitted, echo validation still
    runs against the manifest's own request anchors.
    asset_receipts: optional PP-T3 prompt-item asset receipts; when
    supplied, each is validated under the Q11 acceptance rules against
    its page's counted result and the checkpoint gains a prompt_items
    block listing the closed items. When omitted, the checkpoint is
    exactly the shipped page-result aggregation, unchanged.
    registry: optional prompt-policy registry document; when supplied,
    budget-decision citations are verified against it."""
    expected = {r["page_role"]: r for r in manifest["requests"]}
    by_role: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    seen_ids = set()
    for res in results:
        rid = res.get("request_id")
        if rid in seen_ids:
            problems.append(f"duplicate result for request {rid}")
            continue
        seen_ids.add(rid)
        role = next((ro for ro, rq in expected.items()
                     if rq["request_id"] == rid), None)
        if role is None:
            problems.append(f"result for unknown request {rid} — not part of "
                            "this dispatch")
            continue
        req = (requests or _manifest_requests(manifest)).get(rid)
        fails = validate_result(res, req)
        if fails:
            problems.extend(f"{role}: {f}" for f in fails)
            continue
        by_role[role] = res
    prompt_block = None
    if asset_receipts is not None:
        closed: List[Dict[str, Any]] = []
        anchors = requests or _manifest_requests(manifest)
        for receipt in asset_receipts:
            page_id = receipt.get("page_id") \
                if isinstance(receipt, dict) else None
            role = next((ro for ro, r in by_role.items()
                         if r["page_id"] == page_id), None)
            if role is None:
                problems.append(f"prompt item for page {page_id!r}: no "
                                "counted page-result carries that page, "
                                "so the item cannot close")
                continue
            result = by_role[role]
            req = anchors.get(result["request_id"])
            fails = validate_asset_receipt(receipt, req, result, registry)
            if fails:
                problems.extend(f"prompt item {role}: {f}" for f in fails)
                continue
            bd = receipt["budget_decision"]
            closed.append({"page_id": page_id, "page_role": role,
                           "decision": bd["decision"],
                           "prompt_policy_id": bd["prompt_policy_id"],
                           "registry_entry_hash":
                               bd["registry_entry_hash"]})
        prompt_block = {"closed": sorted(closed,
                                         key=lambda c: c["page_id"])}
    missing = [ro for ro in expected if ro not in by_role]
    blocked = [ro for ro, r in by_role.items() if r["status"] == "blocked"]
    present = [by_role[ro] for ro in expected if ro in by_role]

    def all_at_least(status: str) -> bool:
        order = {s: i for i, s in enumerate(STATUSES)}
        return bool(present) and not missing and all(
            order[r["status"]] >= order[status] for r in present)

    if problems and not present:
        aggregate = "blocked"
    elif blocked:
        aggregate = "blocked"
    elif not present:
        aggregate = "not_started"
    elif missing:
        aggregate = "in_progress"
    elif all_at_least("live_verified"):
        aggregate = "live_verified"
    elif all_at_least("ready_for_activation") and \
            all(r["independent_review"] for r in present):
        aggregate = "ready_for_activation"
    elif all_at_least("installed_test_verified"):
        aggregate = "installed_test_verified"
    elif all_at_least("locally_verified"):
        aggregate = "locally_verified"
    else:
        aggregate = "authored"
    weakest = min((r["proof_class"] for r in present),
                  key=LEVELS.index) if present else None
    return {
        "schema": "signature-launch-checkpoint/v1",
        "launch_id": manifest["launch_id"], "revision": manifest["revision"],
        "plan_document_hash": manifest["plan_document_hash"],
        "route_graph_hash": manifest["route_graph_hash"],
        "execution": manifest["execution"],
        "roles_expected": sorted(expected),
        "roles_reported": sorted(by_role),
        "missing_roles": sorted(missing),
        "blocked_roles": sorted(blocked),
        "problems": problems,
        **({"prompt_items": prompt_block} if prompt_block is not None
           else {}),
        "per_role": {ro: {"status": by_role[ro]["status"],
                          "proof_class": by_role[ro]["proof_class"],
                          "independent_review": by_role[ro]["independent_review"],
                          "blockers": by_role[ro]["blockers"]}
                     for ro in sorted(by_role)},
        "weakest_proof_class": weakest,
        "aggregate_status": aggregate,
    }


def _load(p: str) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _self_test() -> int:
    ok = True

    def say(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    manifest = {"launch_id": "X", "revision": 1, "plan_document_hash": "ph",
                "route_graph_hash": "gh", "execution": "executed",
                "requests": [{"request_id": f"rq-{r}", "page_id": f"P-{r}",
                              "page_role": r, "assigned_skill": 71,
                              "input_hash": f"ih-{r}"}
                             for r in ("landing", "checkout", "thank_you")]}
    requests = {rq["request_id"]: {"request_id": rq["request_id"],
                                   "input_hash": rq["input_hash"],
                                   "page_id": rq["page_id"], "launch_id": "X",
                                   "revision": 1, "tenant_id": "T",
                                   "location_id": "L", "test_only": True}
                for rq in manifest["requests"]}

    def res(role, status="locally_verified", author="a1", reviewer="r1",
            proof="L2"):
        rq = requests[f"rq-{role}"]
        return {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
                "launch_id": "X", "revision": 1, "request_id": rq["request_id"],
                "input_hash": rq["input_hash"], "page_id": rq["page_id"],
                "status": status, "artifacts": [], "author_session": author,
                "reviewer_session": reviewer,
                "independent_review": reviewer is not None,
                "proof_class": proof, "blockers": [],
                "native_bindings_ref": None, "test_only": True}

    cp = collect(manifest, [res("landing"), res("checkout"), res("thank_you")])
    say(cp["aggregate_status"] == "locally_verified" and
        cp["weakest_proof_class"] == "L2",
        "full L2 locally_verified set rolls up honestly")
    cp = collect(manifest, [res("landing")])
    say(cp["aggregate_status"] == "in_progress" and
        cp["missing_roles"] == ["checkout", "thank_you"],
        "partial results report in_progress with named missing roles")
    bad = res("landing"); bad["reviewer_session"] = "a1"
    cp = collect(manifest, [bad, res("checkout"), res("thank_you")])
    say(any("reviewer == author" in p for p in cp["problems"]),
        "self-reviewed result is rejected as a problem, never counted")
    cp = collect(manifest, [res("landing", "ready_for_activation"),
                            res("checkout", "ready_for_activation"),
                            res("thank_you", "ready_for_activation")])
    say(cp["aggregate_status"] == "ready_for_activation",
        "all roles ready + independent review -> ready_for_activation")
    cp = collect(manifest, [res("landing", "ready_for_activation", reviewer=None),
                            res("checkout", "ready_for_activation"),
                            res("thank_you", "ready_for_activation")])
    say(cp["aggregate_status"] != "ready_for_activation",
        "ready_for_activation is withheld when a role lacks independent review")
    stray = res("landing"); stray["request_id"] = "rq-nope"
    cp = collect(manifest, [stray])
    say(cp["aggregate_status"] == "blocked" and cp["problems"],
        "a result that echoes no request in this dispatch is a problem")
    # Review probe E (D6b): with NO requests map supplied, a result whose
    # input_hash does not echo the manifest's anchor must not count — the
    # echo guarantee comes from the manifest itself.
    forged = res("landing", "live_verified", proof="L5")
    forged["input_hash"] = "GARBAGE-NOT-THE-REAL-HASH"
    cp = collect(manifest, [forged, res("checkout", "live_verified", proof="L5"),
                            res("thank_you", "live_verified", proof="L5")])
    say(cp["aggregate_status"] != "live_verified" and
        any("input_hash" in p for p in cp["problems"]) and
        "landing" in cp["missing_roles"],
        "a non-echoing result is refused even without a requests map (D6b)")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Aggregate launch page-results.")
    ap.add_argument("--manifest", help="dispatch-manifest.json")
    ap.add_argument("--results-dir", help="directory of result-*.json files")
    ap.add_argument("--requests-dir", help="directory of request-*.json files")
    ap.add_argument("--asset-receipts-dir",
                    help="directory of asset-receipt-*.json files (PP-T3 "
                         "prompt items); without it, behavior is exactly "
                         "the shipped page-result aggregation")
    ap.add_argument("--registry",
                    help="prompt-policy registry JSON; when supplied, "
                         "budget-decision citations are verified against it")
    ap.add_argument("--out", help="write the checkpoint JSON here")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not (args.manifest and args.results_dir):
        print("USAGE ERROR: --manifest and --results-dir are required.")
        return EXIT_FAILCLOSED
    try:
        manifest = _load(args.manifest)
        results = [_load(str(p)) for p in
                   sorted(Path(args.results_dir).glob("result-*.json"))]
        requests = None
        if args.requests_dir:
            requests = {}
            for p in sorted(Path(args.requests_dir).glob("request-*.json")):
                r = _load(str(p))
                requests[r["request_id"]] = r
        asset_receipts = None
        if args.asset_receipts_dir:
            asset_receipts = [_load(str(p)) for p in
                              sorted(Path(args.asset_receipts_dir)
                                     .glob("asset-receipt-*.json"))]
        registry = _load(args.registry) if args.registry else None
        cp = collect(manifest, results, requests, asset_receipts, registry)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_VIOLATION
    text = json.dumps(cp, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
