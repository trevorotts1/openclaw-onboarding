#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_launch.py — turn an APPROVED launch plan into specialist page
requests (spec 06 S49-07; contracts doc 02 §7, schemas page-request 1.0).

Q12 REVISION (schema 1.1, S49): when the launch record names a
prompt_policy_id (brand-group field, plan-approved content bound by the
plan document hash), build_requests stamps it into emitted requests
and marks those requests schema_version "1.1" (page-request.v1.1 schema,
1.0 preserved). When the record names none, the emitted requests are
byte-identical 1.0 requests. No policy values are minted here: the id is
copied from the record verbatim, never invented per run, and never
supplied by a CLI flag, a run-dir config key, or a function parameter
(copy_profile's parameter path is the anti-pattern: it is not plan-bound).
validate_request applies the same rule in reverse: a "1.1" request must
carry the field, and a "1.0" request must not.

PP-T2 REVISION (per-role adoption switch, S49; adoption map section 2.1):
the Q12 stamp above is no longer global. build_requests emits the 1.1
shape for a role ONLY when the record names a prompt_policy_id AND that
role's state in the adoption file (49-signature-funnel/
prompt-policy-adoption.json, repo state owned by S49) is "ready"; every
other role receives exactly the 1.0 request, with no prompt_policy_id
key. A role missing from the file, a state outside the vocabulary, or an
unreadable adoption file all mean NOT ready (fail toward 1.0, never
toward 1.1). The adoption file controls emission SHAPE only: it never
supplies, alters, or defaults the policy id, which still comes only
from the approved launch record exactly as the Q12 revision built it,
and readiness is never taken from a CLI flag, a run-dir config key, or
a function parameter; it changes only by editing the adoption file in
the repo, through the flip procedure. After the Question 1 ruling the
id is a citation of the one governing policy (the KIE rule-12 band),
not a selector; the switch exists as consumer-contract protection,
because a 1.1-shaped request breaks consumer schemas that are still
closed (additionalProperties: false), and for no other reason. The
dispatch manifest records a prompt_policy_adoption block (per role: the
state read, the emitted schema_version, the evidence_ref behind
"ready") so receipts prove after the fact which roles ran 1.1 and on
what evidence. validate_request is unchanged: it already dual-accepts.

FAIL-CLOSED, in this order:
  1. The launch record must validate (validate_launch_plan) and its status
     must be approved/building.
  2. The plan-approval gate must pass for the CURRENT record
     (assert_plan_build_approved): hash binding, client identity, no worker
     self-approval, not revoked/expired.
  3. The route graph is RE-COMPILED from the record and must hash to the
     record's route_graph_hash — dispatch never trusts a stored graph.
  4. Write target discipline: local_only needs nothing more;
     approved_test_location needs a test_location_use approval;
     approved_live_publication needs test_location_use + page_publication
     approvals. Every scoped approval passes the SAME gate discipline as
     the plan approval (assert_scoped_approval): separate type, scope
     containing the type, plan-hash binding, client identity, no worker
     self-approval, provenance reference, revocation, expiry. Approvals
     are never inferred from the plan approval.

One idempotent page request per launch revision + page role. The dispatch
key is tenant + launch + revision + role + request hash: rebuilding the
same approved plan yields byte-identical requests, so a re-dispatch is a
no-op the consumer can dedupe, never a duplicate build.

EMISSION IS NOT EXECUTION. With no executor adapter configured this tool
writes the requests plus a dispatch manifest marked emitted_not_executed
and stops. A consumer adapter (S49-08, built with the owning skills' real
entrypoints) executes a request and returns a page-result (schema 1.0);
collect_launch_receipts.py aggregates those results into checkpoints.
The --simulate-executor flag exists for tests only and stamps every
result test_only with proof class L0.

Deterministic, stdlib only. Exit 0 ok, 2 violation, 3 usage/fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_launch_route as clr  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

ROLE_SKILL = {"landing": 71, "product_selection": 78, "checkout": 79,
              "upsell_1": 80, "downsell_1": 81, "upsell_2": 80, "thank_you": 82}
ROLE_OFFERS = {"landing": ("main",), "product_selection": ("main",),
               "checkout": ("main", "bump"), "upsell_1": ("upsell_1",),
               "downsell_1": ("downsell_1",), "upsell_2": ("upsell_2",),
               "thank_you": ("main", "bump", "upsell_1", "downsell_1", "upsell_2")}
WRITE_TARGETS = ("local_only", "approved_test_location", "approved_live_publication")

ADOPTION_SCHEMA = "signature-launch-prompt-policy-adoption/v1"
ADOPTION_STATES = ("not_ready", "ready", "never_by_design",
                   "blocked_no_consumer")
# The adoption file lives at the skill root, one level above this scripts
# directory (49-signature-funnel/prompt-policy-adoption.json). It is repo
# state, changed only by the flip procedure's commit (adoption map
# section 2.3); dispatch never takes readiness from a CLI flag, a run-dir
# config key, or a function parameter, and the file can never supply the
# policy id. Tests rebind ADOPTION_FILE to a fixture copy.
ADOPTION_FILE = (Path(__file__).resolve().parent.parent
                 / "prompt-policy-adoption.json")
_NOT_READY = {"state": "not_ready", "evidence_ref": None}


class DispatchError(ValueError):
    pass


def _read_adoption() -> Tuple[Dict[str, Dict[str, Any]], str]:
    """Read the per-role adoption file (adoption map section 2.1 rule 1).

    Returns (decisions, file_status): decisions maps every dispatch role
    to {"state", "evidence_ref"} holding the EFFECTIVE state for this
    run, and file_status is "loaded" or "unreadable". Fail toward 1.0 at
    every layer: a missing, unparseable, or wrongly shaped file makes
    every role not ready; a role missing from the file, an entry that is
    not an object, or a state value outside the vocabulary makes that
    role not ready. Nothing here raises, because 1.0 is always
    emittable and an adoption-file failure must never widen emission."""
    try:
        doc = json.loads(ADOPTION_FILE.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) \
                or doc.get("schema") != ADOPTION_SCHEMA \
                or not isinstance(doc.get("roles"), dict):
            raise ValueError("adoption file does not have the v1 shape")
        entries = doc["roles"]
    except (OSError, ValueError):
        return ({role: dict(_NOT_READY) for role in ROLE_SKILL},
                "unreadable")
    decisions: Dict[str, Dict[str, Any]] = {}
    for role in ROLE_SKILL:
        entry = entries.get(role)
        if isinstance(entry, dict) \
                and entry.get("state") in ADOPTION_STATES:
            ref = entry.get("evidence_ref")
            decisions[role] = {
                "state": entry["state"],
                "evidence_ref": ref if isinstance(ref, str) else None}
        else:
            decisions[role] = dict(_NOT_READY)
    return decisions, "loaded"


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def request_input_hash(launch: Dict[str, Any], page_id: str, role: str) -> str:
    return hashlib.sha256(_canonical({
        "plan_document_hash": vlp.plan_document_hash(launch),
        "route_graph_hash": launch["route_graph_hash"],
        "page_id": page_id, "page_role": role,
        "revision": launch["revision"]})).hexdigest()


def dispatch_key(launch: Dict[str, Any], role: str, input_hash: str) -> str:
    return (f"{launch['tenant_id']}:{launch['launch_id']}:"
            f"rev{launch['revision']}:{role}:{input_hash[:16]}")


def build_requests(launch: Dict[str, Any], graph: Dict[str, Any], *,
                   copy_profile: str,
                   allowed_write_target: str) -> List[Dict[str, Any]]:
    if allowed_write_target not in WRITE_TARGETS:
        raise DispatchError(f"allowed_write_target {allowed_write_target!r} "
                            "is not a write target")
    if "prompt_policy_id" in launch:
        policy_id = launch["prompt_policy_id"]
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise DispatchError(
                "launch record prompt_policy_id, when the key is present, "
                "must be a non-empty string — null or blank is refused; "
                "omit the key entirely when no policy governs (absence is "
                "the only encoding of 'no policy': absent, null, and a "
                "value are three different plan hashes)")
    else:
        policy_id = None
    decisions, _adoption_status = _read_adoption()
    offer_ids = {}
    for o in launch["offers"]:
        offer_ids.setdefault(o["slot"], []).append(o["offer_id"])
    requests: List[Dict[str, Any]] = []
    for node in graph["nodes"]:
        role = node["role"]
        ih = request_input_hash(launch, node["page_id"], role)
        refs: List[str] = []
        for slot in ROLE_OFFERS[role]:
            refs.extend(offer_ids.get(slot, []))
        # PP-T2 emission rule (adoption map section 2.1 rule 2): the 1.1
        # shape is emitted for this role only when the record names a
        # policy id AND the role's adoption state is "ready". The switch
        # gates shape only; the id stamped is the record's, verbatim.
        decision = decisions.get(role) or _NOT_READY
        stamp = bool(policy_id) and decision["state"] == "ready"
        requests.append({
            "schema_version": "1.1" if stamp else "1.0",
            "tenant_id": launch["tenant_id"],
            "location_id": launch["location_id"],
            "launch_id": launch["launch_id"],
            "revision": launch["revision"],
            "request_id": dispatch_key(launch, role, ih),
            "page_id": node["page_id"],
            "page_role": role,
            "assigned_skill": ROLE_SKILL[role],
            "approval_ref": launch["plan_approval_ref"],
            "input_hash": ih,
            "brand_ref": launch["brand_ref"],
            "brand_hash": launch["brand_hash"],
            "route_graph_ref": launch["route_graph_ref"],
            "route_graph_hash": launch["route_graph_hash"],
            "offer_refs": refs,
            "copy_profile": copy_profile,
            **({"prompt_policy_id": policy_id} if stamp else {}),
            "allowed_write_target": allowed_write_target,
            "test_only": bool(launch["test_only"]),
        })
    return requests


_REQUEST_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                   "revision", "request_id", "page_id", "page_role",
                   "assigned_skill", "approval_ref", "input_hash", "brand_ref",
                   "brand_hash", "route_graph_ref", "route_graph_hash",
                   "offer_refs", "copy_profile", "allowed_write_target",
                   "test_only")


def validate_request(req: Dict[str, Any]) -> List[str]:
    fails = [f"request missing field {f!r}" for f in _REQUEST_FIELDS
             if f not in req]
    if fails:
        return fails
    if req["schema_version"] not in ("1.0", "1.1"):
        fails.append("request schema_version is not 1.0 or 1.1")
    elif req["schema_version"] == "1.1":
        pid = req.get("prompt_policy_id")
        if not isinstance(pid, str) or not pid.strip():
            fails.append("a 1.1 request must carry a non-empty "
                         "prompt_policy_id (the 1.1 label exists to carry "
                         "the field)")
    elif "prompt_policy_id" in req:
        fails.append("prompt_policy_id requires request schema_version "
                     "1.1 (the 1.0 schema forbids the field)")
    if req["page_role"] not in ROLE_SKILL:
        fails.append(f"unknown page_role {req['page_role']!r}")
    elif req["assigned_skill"] != ROLE_SKILL[req["page_role"]]:
        fails.append(f"page_role {req['page_role']} must be assigned to skill "
                     f"{ROLE_SKILL[req['page_role']]}, not {req['assigned_skill']}")
    if req["allowed_write_target"] not in WRITE_TARGETS:
        fails.append("allowed_write_target is not valid")
    return fails


def _check_scoped_approvals(launch: Dict[str, Any],
                              approvals: List[Dict[str, Any]],
                              target: str, *,
                              client_identity_ref: str,
                              worker_identity_ref: str) -> None:
    """Scoped side-effect approvals get the FULL gate discipline (doc 02 §9,
    doc 03 §9): separate type, scope containing the type, plan-hash binding,
    client identity, no worker self-approval, provenance reference,
    revocation, expiry — via validate_launch_plan.assert_scoped_approval,
    the same helper core the plan gate uses. A record the worker minted
    alone authorizes nothing."""
    needed = {"local_only": [],
              "approved_test_location": ["test_location_use"],
              "approved_live_publication": ["test_location_use",
                                            "page_publication"]}[target]
    for need in needed:
        candidates = [a for a in approvals
                      if isinstance(a, dict)
                      and a.get("subject_type") == need]
        if not candidates:
            raise DispatchError(
                f"write target {target} requires a {need} approval bound to "
                "this plan hash; none supplied (approvals are separate types "
                "and never inferred from the plan approval)")
        first_error: Optional[str] = None
        for cand in candidates:
            try:
                vlp.assert_scoped_approval(
                    launch, cand, need,
                    client_identity_ref=client_identity_ref,
                    worker_identity_ref=worker_identity_ref)
                break
            except vlp.ApprovalError as exc:
                if first_error is None:
                    first_error = str(exc)
        else:
            raise DispatchError(
                f"write target {target}: no {need} approval passed the gate "
                f"discipline — {first_error}")


def dispatch(launch: Dict[str, Any], approval: Dict[str, Any], *,
             client_identity_ref: str, worker_identity_ref: str,
             copy_profile: str = "standard",
             allowed_write_target: str = "local_only",
             scoped_approvals: Optional[List[Dict[str, Any]]] = None,
             out_dir: Optional[Path] = None,
             executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
             ) -> Dict[str, Any]:
    """Full dispatch. Returns the manifest dict; writes requests (+ results
    when an executor ran) under out_dir when given."""
    fails = vlp.validate_launch(launch)
    if fails:
        raise DispatchError("launch record fails validation: " + "; ".join(fails))
    if launch["status"] not in ("approved", "building"):
        raise DispatchError(f"launch status is {launch['status']!r} — dispatch "
                            "requires an approved plan")
    vlp.assert_plan_build_approved(launch, approval,
                                   client_identity_ref=client_identity_ref,
                                   worker_identity_ref=worker_identity_ref)
    graph = clr.compile_route(launch)
    if clr.graph_hash(graph) != launch["route_graph_hash"]:
        raise DispatchError("re-compiled route graph hash does not match the "
                            "record's route_graph_hash — the approved plan and "
                            "its route disagree; re-plan, never dispatch")
    _check_scoped_approvals(launch, scoped_approvals or [], allowed_write_target,
                            client_identity_ref=client_identity_ref,
                            worker_identity_ref=worker_identity_ref)
    requests = build_requests(launch, graph, copy_profile=copy_profile,
                              allowed_write_target=allowed_write_target)
    for r in requests:
        rf = validate_request(r)
        if rf:
            raise DispatchError("built request failed schema discipline: " +
                                "; ".join(rf))
    # PP-T2 manifest block (adoption map section 2.1 rule 5): per role,
    # the state read, the schema_version actually emitted (taken from the
    # request itself, never inferred from the decision), and the
    # evidence_ref behind the state.
    adoption, adoption_status = _read_adoption()
    adoption_block: Dict[str, Any] = {"file_status": adoption_status,
                                      "roles": {}}
    for r in requests:
        d = adoption[r["page_role"]]
        adoption_block["roles"][r["page_role"]] = {
            "state": d["state"],
            "emitted_schema_version": r["schema_version"],
            "evidence_ref": d["evidence_ref"]}
    manifest: Dict[str, Any] = {
        "schema": "signature-launch-dispatch/v1",
        "launch_id": launch["launch_id"], "revision": launch["revision"],
        "plan_document_hash": vlp.plan_document_hash(launch),
        "route_graph_hash": launch["route_graph_hash"],
        "allowed_write_target": allowed_write_target,
        "prompt_policy_adoption": adoption_block,
        "execution": "executed" if executor else "emitted_not_executed",
        "requests": [{"request_id": r["request_id"], "page_id": r["page_id"],
                      "page_role": r["page_role"],
                      "assigned_skill": r["assigned_skill"],
                      "input_hash": r["input_hash"]} for r in requests],
        "results": [],
    }
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "route-graph.json").write_bytes(clr.serialize_graph(graph))
        for r in requests:
            (out_dir / f"request-{r['page_role']}.json").write_text(
                json.dumps(r, indent=2) + "\n", encoding="utf-8")
    if executor:
        for r in requests:
            result = executor(r)
            manifest["results"].append(result)
            if out_dir:
                (out_dir / f"result-{r['page_role']}.json").write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if out_dir:
        (out_dir / "dispatch-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def executor_from_config(config: Dict[str, Any], work_dir: Path):
    """Build an executor from a consumer-adapter config (S49-08 seam).

    Config shape: {"adapters": {"<page_role>": {"command": ["prog", "{request}",
    "{result}"], "timeout_s": 600}}}. For each request the adapter command
    runs with the request JSON path and the expected result JSON path; the
    result is accepted ONLY when it parses and passes the receipt
    validation (schema shape + exact request echo) from
    collect_launch_receipts. A role with no configured adapter, a failing
    command, or an invalid result is a DispatchError — dispatch never
    papers over a consumer that did not really answer."""
    import subprocess
    import collect_launch_receipts as receipts

    adapters = config.get("adapters") or {}

    def run(req: Dict[str, Any]) -> Dict[str, Any]:
        role = req["page_role"]
        spec = adapters.get(role)
        if not spec or not spec.get("command"):
            raise DispatchError(f"no consumer adapter configured for role "
                                f"{role} — dispatch cannot execute it")
        req_path = work_dir / f"request-{role}.json"
        res_path = work_dir / f"result-{role}.json"
        cmd = [part.replace("{request}", str(req_path))
                    .replace("{result}", str(res_path))
                    .replace("{work_dir}", str(work_dir))
               for part in spec["command"]]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=float(spec.get("timeout_s", 600)))
        if proc.returncode != 0:
            raise DispatchError(f"consumer adapter for {role} exited "
                                f"{proc.returncode}: {proc.stderr.strip()[:400]}")
        if not res_path.is_file():
            raise DispatchError(f"consumer adapter for {role} produced no "
                                f"result file at {res_path}")
        result = json.loads(res_path.read_text(encoding="utf-8"))
        fails = receipts.validate_result(result, req)
        if fails:
            raise DispatchError(f"consumer result for {role} failed receipt "
                                "validation: " + "; ".join(fails))
        return result

    return run


def _simulated_executor(author: str):
    def run(req: Dict[str, Any]) -> Dict[str, Any]:
        return {"schema_version": "1.0", "tenant_id": req["tenant_id"],
                "location_id": req["location_id"], "launch_id": req["launch_id"],
                "revision": req["revision"], "request_id": req["request_id"],
                "input_hash": req["input_hash"], "page_id": req["page_id"],
                "status": "authored", "artifacts": [],
                "author_session": author, "reviewer_session": None,
                "independent_review": False, "proof_class": "L0",
                "blockers": [], "native_bindings_ref": None,
                "test_only": True}
    return run


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> int:
    ok = True

    def say(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def offer(oid, slot, amt, excludes=()):
        return {"offer_id": oid, "slot": slot, "display_name": oid,
                "deliverables": ["x"], "exclusions": [],
                "entitlement_ids": [oid.lower()], "requires": [],
                "excludes": list(excludes), "native_product_id": None,
                "prices": [{"price_choice_id": f"{oid}-USD", "currency": "USD",
                            "amount_minor": amt, "billing_type": "one_time",
                            "native_price_id": None, "schedule": [],
                            "terms_source": None, "approval_status": "approved"}],
                "source_kind": "test_fixture", "source_ref": "self-test",
                "test_only": True}

    launch = {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
              "launch_id": "X", "revision": 1, "journey_mode": "multiple_options",
              "status": "awaiting_plan_approval", "brand_ref": "B",
              "brand_hash": "H", "route_graph_ref": "", "route_graph_hash": "",
              "plan_approval_ref": None,
              "offers": [offer("M1", "main", 1000), offer("M2", "main", 2000),
                         offer("BP", "bump", 500),
                         offer("U1", "upsell_1", 3000, ["D1"]),
                         offer("D1", "downsell_1", 1500, ["U1"]),
                         offer("U2", "upsell_2", 4000)],
              "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": True},
              "bump_enabled": True, "image_provider": "agnes",
              "source_refs": [], "test_only": True}
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = "route-graph:X:rev1"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    approval = {"schema_version": "1.0", "approval_id": "APPR-1",
                "subject_type": "launch_plan_build",
                "subject_hash": vlp.plan_document_hash(launch),
                "owner_identity_ref": "client-1", "source_message_ref": "m-1",
                "recorded_at": now, "scope": ["launch_plan_build"],
                "revoked": False,
                "verification_class": "recorded_consent_not_cryptographically_sealed"}
    launch["status"] = "approved"
    launch["plan_approval_ref"] = "APPR-1"

    m = dispatch(launch, approval, client_identity_ref="client-1",
                 worker_identity_ref="worker-9")
    say(len(m["requests"]) == 7 and m["execution"] == "emitted_not_executed",
        "approved full plan emits 7 role requests and honestly marks them "
        "not executed")
    roles = {r["page_role"]: r for r in m["requests"]}
    say(roles["upsell_1"]["assigned_skill"] == 80 and
        roles["upsell_2"]["assigned_skill"] == 80 and
        roles["upsell_1"]["request_id"] != roles["upsell_2"]["request_id"],
        "U1 and U2 are separate S80 invocations with distinct dispatch keys")
    say(roles["checkout"]["page_role"] == "checkout" and
        len([r for r in m["requests"] if r["page_role"] == "bump"]) == 0,
        "the bump is never dispatched as a page")
    m2 = dispatch(launch, approval, client_identity_ref="client-1",
                  worker_identity_ref="worker-9")
    say([r["request_id"] for r in m["requests"]] ==
        [r["request_id"] for r in m2["requests"]],
        "dispatch is idempotent: same approved plan, same dispatch keys")
    try:
        dispatch(launch, dict(approval, subject_hash="0" * 64),
                 client_identity_ref="client-1", worker_identity_ref="worker-9")
        say(False, "dispatch under a stale approval must fail")
    except vlp.ApprovalError:
        say(True, "dispatch refuses when the plan approval does not bind")
    try:
        dispatch(launch, approval, client_identity_ref="client-1",
                 worker_identity_ref="worker-9",
                 allowed_write_target="approved_test_location")
        say(False, "test-location dispatch without its approval must fail")
    except DispatchError:
        say(True, "test-location write target requires its own scoped approval")
    scoped = [dict(approval, approval_id="APPR-T",
                   subject_type="test_location_use",
                   scope=["test_location_use"])]
    m3 = dispatch(launch, approval, client_identity_ref="client-1",
                  worker_identity_ref="worker-9",
                  allowed_write_target="approved_test_location",
                  scoped_approvals=scoped, executor=_simulated_executor("test"))
    say(len(m3["results"]) == 7 and m3["execution"] == "executed",
        "with the scoped approval + executor, dispatch executes and returns results")
    # Review probe D (D6): fabricated scoped approvals — worker as owner,
    # no provenance reference, recorded in 2020, class "none" — must NOT
    # authorize a live publication target.
    fabricated = [
        dict(approval, approval_id="F-T", subject_type="test_location_use",
             scope=["test_location_use"], owner_identity_ref="worker-9",
             source_message_ref="", recorded_at="2020-01-01T00:00:00Z",
             verification_class="none"),
        dict(approval, approval_id="F-P", subject_type="page_publication",
             scope=["page_publication"], owner_identity_ref="worker-9",
             source_message_ref="", recorded_at="2020-01-01T00:00:00Z",
             verification_class="none")]
    try:
        dispatch(launch, approval, client_identity_ref="client-1",
                 worker_identity_ref="worker-9",
                 allowed_write_target="approved_live_publication",
                 scoped_approvals=fabricated)
        say(False, "fabricated scoped approvals must not authorize live "
                   "publication (D6)")
    except DispatchError:
        say(True, "fabricated scoped approvals are refused for live "
                  "publication (D6: identity, provenance, expiry, class all "
                  "checked)")

    # Consumer-adapter seam (S49-08): a real subprocess consumer whose
    # result echoes the request is accepted; one that echoes wrongly is not.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        consumer = tdp / "consumer.py"
        consumer.write_text(
            "import json,sys\n"
            "req=json.load(open(sys.argv[1]))\n"
            "res={'schema_version':'1.0','tenant_id':req['tenant_id'],"
            "'location_id':req['location_id'],'launch_id':req['launch_id'],"
            "'revision':req['revision'],'request_id':req['request_id'],"
            "'input_hash':req['input_hash'],'page_id':req['page_id'],"
            "'status':'authored','artifacts':[],"
            "'author_session':'consumer-test','reviewer_session':None,"
            "'independent_review':False,'proof_class':'L0','blockers':[],"
            "'native_bindings_ref':None,'test_only':req['test_only']}\n"
            "json.dump(res,open(sys.argv[2],'w'))\n", encoding="utf-8")
        cfg = {"adapters": {role: {"command": [sys.executable, str(consumer),
                                              "{request}", "{result}"]}
                            for role in ROLE_SKILL}}
        out = tdp / "dispatch"
        m4 = dispatch(launch, approval, client_identity_ref="client-1",
                      worker_identity_ref="worker-9", out_dir=out,
                      executor=executor_from_config(cfg, out))
        say(len(m4["results"]) == 7,
            "adapter-config executor runs real consumers and validates echoes")
        bad = tdp / "bad_consumer.py"
        bad.write_text("import json,sys\n"
                       "json.dump({'bogus': True}, open(sys.argv[2],'w'))\n",
                       encoding="utf-8")
        cfg_bad = {"adapters": {role: {"command": [sys.executable, str(bad),
                                                   "{request}", "{result}"]}
                                for role in ROLE_SKILL}}
        try:
            dispatch(launch, approval, client_identity_ref="client-1",
                     worker_identity_ref="worker-9", out_dir=out,
                     executor=executor_from_config(cfg_bad, out))
            say(False, "an invalid consumer result must be refused")
        except DispatchError:
            say(True, "a consumer result that fails receipt validation is refused")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Dispatch an approved launch plan.")
    ap.add_argument("--launch"); ap.add_argument("--approval")
    ap.add_argument("--run-dir",
                    help="launch run dir holding launch.json, approval.json and "
                         "launch-request.json (mode signature_launch); outputs "
                         "go to <run-dir>/dispatch")
    ap.add_argument("--client"); ap.add_argument("--worker")
    ap.add_argument("--copy-profile", default="standard")
    ap.add_argument("--write-target", default="local_only")
    ap.add_argument("--scoped-approvals", help="JSON array of extra approvals")
    ap.add_argument("--out", help="directory for requests + manifest")
    ap.add_argument("--adapters",
                    help="consumer adapter config JSON (executes requests "
                         "through the owning skills' entrypoints)")
    ap.add_argument("--simulate-executor", action="store_true",
                    help="TEST ONLY: fabricate L0 authored results")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    cfg: Dict[str, Any] = {}
    if args.run_dir:
        rd = Path(args.run_dir)
        args.launch = args.launch or str(rd / "launch.json")
        args.approval = args.approval or str(rd / "approval.json")
        cfg_path = rd / "launch-request.json"
        if cfg_path.is_file():
            cfg = _load(str(cfg_path))
        if cfg.get("mode") not in (None, "signature_launch"):
            print("FAIL: launch-request.json mode is not signature_launch")
            return EXIT_VIOLATION
        args.client = args.client or cfg.get("client_identity_ref")
        args.worker = args.worker or cfg.get("worker_identity_ref")
        args.copy_profile = cfg.get("copy_profile", args.copy_profile)
        args.write_target = cfg.get("allowed_write_target", args.write_target)
        args.out = args.out or str(rd / "dispatch")
    if not (args.launch and args.approval and args.client and args.worker):
        print("USAGE ERROR: --launch --approval --client --worker are required.")
        return EXIT_FAILCLOSED
    try:
        launch = _load(args.launch)
        approval = _load(args.approval)
        scoped = _load(args.scoped_approvals) if args.scoped_approvals \
            else cfg.get("scoped_approvals", [])
        executor = None
        if args.adapters:
            if not args.out:
                print("FAIL: --adapters requires --out (or --run-dir) as the "
                      "work dir for request/result files")
                return EXIT_FAILCLOSED
            executor = executor_from_config(_load(args.adapters),
                                            Path(args.out))
        elif args.simulate_executor:
            executor = _simulated_executor("dispatch-cli-simulated")
        m = dispatch(launch, approval, client_identity_ref=args.client,
                     worker_identity_ref=args.worker,
                     copy_profile=args.copy_profile,
                     allowed_write_target=args.write_target,
                     scoped_approvals=scoped,
                     out_dir=Path(args.out) if args.out else None,
                     executor=executor)
    except (DispatchError, vlp.ApprovalError, clr.RouteError, OSError,
            ValueError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_VIOLATION
    print(json.dumps({"execution": m["execution"],
                      "requests": len(m["requests"]),
                      "results": len(m["results"])}, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
