#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selection_wrapper.py: S49-08 echo-correcting wrapper for Skill 78
(product_selection), built under CR-S49-002 Path B (S78's written choice,
handoffs/change-requests/S78-reply-CR-S49-002.md).

WHY THIS WRAPPER EXISTS. Skill 78's page-result emitter on main
(78-signature-product-selection/scripts/emit_page_result.py) breaks the
S49 receipt contract (page-result 1.0, collect_launch_receipts rules) in
four verified ways:
  1. It PRINTS the result to stdout and writes no file; dispatch expects a
     bare JSON result file at the configured {result} path.
  2. It hardcodes page_id "selection" instead of echoing the request's
     page_id.
  3. It sets input_hash to the SHA-256 of the selection PLAN, not the
     request's input_hash.
  4. Its result carries an `outcome` field, which page-result 1.0 rejects
     (additionalProperties: false).
Path A (fix the emitter natively) would edit files inside the Skill 78
v0.2.0 candidate under Trevor's byte-stable approval lock for PR #2158,
so S78 chose Path B: this wrapper, on the S49 side. RETIREMENT: when
S78's first candidate after PR #2158 lands with the native emitter fix,
this wrapper is retired and dispatch points at the native entrypoint.

WHAT THE WRAPPER DOES (dispatch adapter command for role
product_selection; invoked with {request}/{result}/{work_dir}
substitution by dispatch_launch.executor_from_config):
  1. Loads the S49 page-request (schema 1.0, or 1.1 when dispatch has
     stamped a prompt_policy_id under the prompt-policy adoption map)
     and the launch record the request references; cross-checks identity
     (tenant/location/launch/revision, test_only) and that the request's
     offer_refs are exactly the launch record's main-slot offer IDs.
     Any disagreement fails closed.
  2. ENRICHES checkout_targets (the Skill 78 selection-request profile
     additionally requires native product/price IDs per offer) from a
     configured mappings input: the native mapping rows the S44/S79 side
     delivers (e.g. rooms/S79/work/l3/native-product-mappings.json shape:
     {"mappings": [{offer_id, native_product_id, native_price_id, ...}]};
     a bare list, or {"checkout_targets": [...]}, is also accepted).
     One target per (offer, price choice). A mapping row without a
     price_choice_id can only satisfy a single-price offer. Any offer or
     price choice with no mapping row, or a row missing native IDs,
     FAILS CLOSED naming it. The wrapper never fabricates a native ID;
     the only derived value is target_ref when a row carries none, built
     as "mappings:<offer_id>:<native_product_id>:<native_price_id>", a
     reference into the mappings input, never a native ID itself.
  3. Builds the enriched Skill 78 selection-request (the request's
     fields with copy_profile set to the profile const
     "signature-product-selection", plus checkout_targets) and checks it
     against the profile requirements read from
     schema/selection-request.schema.json, including the profile's
     dual-accept pair rule: a 1.1 request's prompt_policy_id passes
     through into the enriched document verbatim (never dropped, never
     altered), a 1.0 request carries no such field. The enriched
     document is written to the work dir as evidence
     (selection-request.enriched.json). Nothing in Skill 78
     consumes this document at runtime today (see BUILD-REPORT flow map);
     it is the seam artifact S78's profile defines, produced and
     validated here so the enrichment is real, checked, and inspectable.
  4. Runs Skill 78's REAL plan builder (build_selection_plan.py) on the
     launch record, capturing its stdout plan into the work dir
     (selection-plan.json). A builder violation or error fails closed
     with the builder's stderr passed through.
  5. Runs Skill 78's REAL emitter (emit_page_result.py) on that plan,
     with --output naming a work-dir file for the emitted document and
     --request naming the dispatch request the wrapper holds, so the
     emitter echoes page_id and input_hash from the request itself;
     the wrapper reads the emitted file back. (The emitter's current
     CLI takes the result as an --output file and prints nothing on
     success; it is the CLI form the shipped native chain uses.)
  6. VERIFIES the emitter actually answered this request: request_id,
     tenant_id, location_id, launch_id, revision in the emitted document
     must equal the request's. A mismatch (a tampered or confused
     emitter) fails closed; the wrapper never papers over it.
  7. CORRECTS the echo from the request the wrapper holds (the
     authoritative source): page_id := request.page_id,
     input_hash := request.input_hash. PROJECTS the document to exactly
     the 17 page-result 1.0 fields (dropping outcome and any other
     extras), validates the projection (exact field set, status and
     proof_class enums, every receipt echo field equal to the request,
     test_only agreement, artifact entries exactly {path, sha256},
     independent_review never claimed without a distinct named
     reviewer), and writes it as bare JSON at the {result} path.

Fail-closed discipline: exit 0 only when a validated result file exists
at {result}; any failure prints FAIL-CLOSED to stderr, exits 3, and
removes any file at {result} so a stale result can never be mistaken
for this run's answer. Exit 2 is reserved for usage errors.

Stdlib only. No network. No live routing: Skill 78's SKILL.md says do
not route live launches to it yet; this wrapper is for the dispatch
seam and fixture-level execution until S78's install status changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

ROLE = "product_selection"
SKILL = 78
SELECTION_COPY_PROFILE = "signature-product-selection"

PAGE_RESULT_FIELDS = (
    "schema_version", "tenant_id", "location_id", "launch_id", "revision",
    "request_id", "input_hash", "page_id", "status", "artifacts",
    "author_session", "reviewer_session", "independent_review",
    "proof_class", "blockers", "native_bindings_ref", "test_only")
STATUSES = ("authored", "locally_verified", "installed_test_verified",
            "ready_for_activation", "live_verified", "blocked")
LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
LOCAL_STATUSES = ("authored", "locally_verified", "blocked")

# The Skill 78 selection-request profile requirements, mirrored from
# schema/selection-request.schema.json as read in full from main:
# required field list, consts, and minimum lengths at the pre-adoption
# profile (blob 4ab5d62f78), extended by the dual-accept pair rule of
# the landed revised profile (blob c84b04d765): schema_version accepts
# "1.0" or "1.1"; a "1.1" document must carry prompt_policy_id as a
# non-empty string; a "1.0" document must not carry the field.
PROFILE_REQUIRED = (
    "schema_version", "tenant_id", "location_id", "launch_id", "revision",
    "request_id", "page_id", "page_role", "assigned_skill", "approval_ref",
    "input_hash", "brand_ref", "brand_hash", "route_graph_ref",
    "route_graph_hash", "offer_refs", "copy_profile", "checkout_targets",
    "allowed_write_target", "test_only")
TARGET_FIELDS = ("offer_id", "price_choice_id", "native_product_id",
                 "native_price_id", "target_ref")


class WrapperError(ValueError):
    pass


def _load(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WrapperError(f"cannot load {what} at {path}: {exc}")


def _fail(result_path: Path, message: str) -> int:
    try:
        if result_path.is_file():
            result_path.unlink()
    except OSError:
        pass
    print(f"FAIL-CLOSED: {message}", file=sys.stderr)
    return EXIT_FAILCLOSED


def normalize_mapping_rows(mappings: Any) -> List[Dict[str, Any]]:
    """Accept the delivered native-mapping shapes: an object with a
    'mappings' list (the S79 delivered read-back format), an object with
    a 'checkout_targets' list, or a bare list of rows."""
    if isinstance(mappings, list):
        return mappings
    if isinstance(mappings, dict):
        for key in ("mappings", "checkout_targets", "targets"):
            if isinstance(mappings.get(key), list):
                return mappings[key]
    raise WrapperError("mappings input is neither a list nor an object "
                       "with a 'mappings'/'checkout_targets' list")


def enrich_checkout_targets(launch: Dict[str, Any],
                            offer_refs: List[str],
                            rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One checkout target per (offer, price choice) for every offer the
    request names, sourced ONLY from mapping rows. Fails closed naming
    the first offer or price choice with no usable row."""
    offers = {o.get("offer_id"): o for o in launch.get("offers", [])}
    targets: List[Dict[str, Any]] = []
    for offer_id in offer_refs:
        offer = offers.get(offer_id)
        if offer is None:
            raise WrapperError(
                f"request names offer {offer_id!r} which is not in the "
                "launch record; cannot enrich checkout_targets")
        offer_rows = [r for r in rows if r.get("offer_id") == offer_id]
        for price in offer.get("prices", []):
            pcid = price.get("price_choice_id")
            row = next((r for r in offer_rows
                        if r.get("price_choice_id") == pcid), None)
            if row is None:
                unkeyed = [r for r in offer_rows
                           if not r.get("price_choice_id")]
                if len(unkeyed) == 1 and len(offer.get("prices", [])) == 1:
                    row = unkeyed[0]
            if row is None:
                raise WrapperError(
                    f"no native mapping row for offer {offer_id!r} price "
                    f"choice {pcid!r}; checkout_targets cannot be enriched "
                    "for this offer (native IDs are never fabricated)")
            npid, nprid = row.get("native_product_id"), row.get("native_price_id")
            if not npid or not nprid:
                raise WrapperError(
                    f"mapping row for offer {offer_id!r} price choice "
                    f"{pcid!r} lacks native_product_id/native_price_id; "
                    "checkout_targets cannot be enriched for this offer")
            target_ref = (row.get("target_ref")
                          or row.get("checkout_target_ref")
                          or f"mappings:{offer_id}:{npid}:{nprid}")
            targets.append({"offer_id": offer_id, "price_choice_id": pcid,
                            "native_product_id": npid,
                            "native_price_id": nprid,
                            "target_ref": target_ref})
    if not targets:
        raise WrapperError("enrichment produced no checkout_targets")
    return targets


def build_selection_request(request: Dict[str, Any],
                            targets: List[Dict[str, Any]],
                            recommendation: Optional[Dict[str, Any]] = None
                            ) -> Dict[str, Any]:
    sel = dict(request)
    sel["copy_profile"] = SELECTION_COPY_PROFILE
    sel["checkout_targets"] = targets
    if recommendation is not None:
        sel["recommendation"] = recommendation
    return sel


def validate_selection_request(sel: Dict[str, Any]) -> List[str]:
    """Check the enriched document against the Skill 78 profile
    requirements (schema/selection-request.schema.json)."""
    fails = [f"selection request missing field {f!r}"
             for f in PROFILE_REQUIRED if f not in sel]
    if fails:
        return fails
    version = sel["schema_version"]
    if version not in ("1.0", "1.1"):
        fails.append(f"selection request schema_version {version!r} is "
                     "not \"1.0\" or \"1.1\"")
    elif version == "1.1":
        pid = sel.get("prompt_policy_id")
        if not isinstance(pid, str) or len(pid) < 1:
            fails.append("selection request schema_version is 1.1 but "
                         "prompt_policy_id is missing or is not a "
                         "non-empty string")
    elif "prompt_policy_id" in sel:
        fails.append("selection request schema_version is 1.0 but "
                     "carries prompt_policy_id, which the profile "
                     "forbids for 1.0")
    if sel["page_role"] != ROLE:
        fails.append(f"selection request page_role is not {ROLE}")
    if sel["assigned_skill"] != SKILL:
        fails.append("selection request assigned_skill is not 78")
    if sel["copy_profile"] != SELECTION_COPY_PROFILE:
        fails.append("selection request copy_profile is not "
                     "signature-product-selection")
    if len(sel.get("offer_refs") or []) < 2:
        fails.append("selection profile requires at least two offer_refs")
    targets = sel.get("checkout_targets") or []
    if len(targets) < 1:
        fails.append("selection profile requires at least one checkout target")
    for t in targets:
        for f in TARGET_FIELDS:
            if not isinstance(t.get(f), str) or not t.get(f):
                fails.append(f"checkout target lacks a non-empty {f}: {t!r}")
    return fails


def project_result(raw: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    """Verify the emitter answered THIS request, correct the echo from
    the request, and project to exactly the 17 page-result 1.0 fields."""
    for f in ("request_id", "tenant_id", "location_id", "launch_id", "revision"):
        if raw.get(f) != request.get(f):
            raise WrapperError(
                f"emitter result does not answer this request on {f}: "
                f"{raw.get(f)!r} != {request.get(f)!r}; refusing to correct "
                "an identity the wrapper cannot vouch for")
    fixed = dict(raw)
    fixed["page_id"] = request["page_id"]
    fixed["input_hash"] = request["input_hash"]
    missing = [f for f in PAGE_RESULT_FIELDS if f not in fixed]
    if missing:
        raise WrapperError(f"emitter result lacks page-result fields "
                           f"{missing}; cannot project")
    return {f: fixed[f] for f in PAGE_RESULT_FIELDS}


def validate_projection(res: Dict[str, Any], request: Dict[str, Any]) -> List[str]:
    """The receipt discipline of collect_launch_receipts.validate_result,
    applied to the projection before it is written (the dispatch
    executor re-runs the real thing on the file)."""
    fails: List[str] = []
    if set(res.keys()) != set(PAGE_RESULT_FIELDS):
        fails.append("projection is not exactly the 17 page-result fields")
    if res["schema_version"] != "1.0":
        fails.append("result schema_version is not 1.0")
    if res["status"] not in STATUSES:
        fails.append(f"unknown result status {res['status']!r}")
    if res["proof_class"] not in LEVELS:
        fails.append(f"unknown proof_class {res['proof_class']!r}")
    for a in res["artifacts"]:
        if not isinstance(a, dict) or set(a.keys()) != {"path", "sha256"}:
            fails.append("an artifact entry is not exactly {path, sha256}")
        elif len(a["sha256"]) != 64 or any(
                c not in "0123456789abcdef" for c in a["sha256"]):
            fails.append("an artifact sha256 is not 64 lowercase hex chars")
    if res["independent_review"]:
        if not res["reviewer_session"]:
            fails.append("independent_review claimed with no reviewer session")
        elif res["reviewer_session"] == res["author_session"]:
            fails.append("independent_review claimed but reviewer == author")
    for f in ("request_id", "input_hash", "page_id", "launch_id", "revision",
              "tenant_id", "location_id", "test_only"):
        if res[f] != request[f]:
            fails.append(f"result does not echo its request on {f}")
    return fails


def _run(argv: List[str], what: str) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=1200)
    if proc.returncode != 0:
        raise WrapperError(f"{what} exited {proc.returncode}: "
                           f"{proc.stderr.strip()[:600]}")
    return proc.stdout


def run_wrapper(args: argparse.Namespace) -> int:
    result_path = Path(args.result)
    try:
        request = _load(Path(args.request), "page-request")
        if not isinstance(request, dict):
            raise WrapperError("page-request is not a JSON object")
        if request.get("page_role") != ROLE or request.get("assigned_skill") != SKILL:
            raise WrapperError(
                f"request is for role {request.get('page_role')!r} / skill "
                f"{request.get('assigned_skill')!r}; this wrapper serves "
                f"only {ROLE} / {SKILL}")
        launch = _load(Path(args.launch), "launch record")
        for f in ("tenant_id", "location_id", "launch_id", "revision", "test_only"):
            if launch.get(f) != request.get(f):
                raise WrapperError(
                    f"launch record disagrees with the request on {f}: "
                    f"{launch.get(f)!r} != {request.get(f)!r}")
        mains = [o["offer_id"] for o in launch.get("offers", [])
                 if o.get("slot") == "main"]
        if sorted(mains) != sorted(request.get("offer_refs") or []):
            raise WrapperError(
                f"request offer_refs {request.get('offer_refs')} do not "
                f"match the launch record's main offers {mains}")
        rows = normalize_mapping_rows(_load(Path(args.mappings),
                                            "native mappings"))
        targets = enrich_checkout_targets(launch, request["offer_refs"], rows)
        recommendation = None
        if args.recommendation:
            recommendation = _load(Path(args.recommendation), "recommendation")
        sel_req = build_selection_request(request, targets, recommendation)
        fails = validate_selection_request(sel_req)
        if fails:
            raise WrapperError("enriched selection request fails the Skill "
                               "78 profile: " + "; ".join(fails))
        work_dir = Path(args.work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "selection-request.enriched.json").write_text(
            json.dumps(sel_req, indent=2) + "\n", encoding="utf-8")

        s78_scripts = Path(args.s78_dir) / "scripts"
        plan_builder = args.plan_builder or str(s78_scripts / "build_selection_plan.py")
        emitter = args.emitter or str(s78_scripts / "emit_page_result.py")
        plan_argv = [sys.executable, plan_builder, str(Path(args.launch))]
        if args.recommendation:
            plan_argv += ["--recommendation", str(Path(args.recommendation))]
        plan_text = _run(plan_argv, "Skill 78 plan builder")
        try:
            plan = json.loads(plan_text)
        except ValueError as exc:
            raise WrapperError(f"plan builder stdout is not JSON: {exc}")
        plan_path = work_dir / "selection-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

        emitted_path = work_dir / "selection-result.emitted.json"
        emit_argv = [sys.executable, emitter, str(plan_path),
                     "--output", str(emitted_path),
                     "--author-session", args.author_session,
                     "--request", str(Path(args.request)),
                     "--status", args.status,
                     "--artifact", str(plan_path)]
        _run(emit_argv, "Skill 78 emitter")
        if not emitted_path.is_file():
            raise WrapperError("Skill 78 emitter exited 0 but wrote no "
                               f"result file at {emitted_path}")
        raw = _load(emitted_path, "emitter result")
        if not isinstance(raw, dict):
            raise WrapperError("emitter result is not a JSON object")
        projected = project_result(raw, request)
        fails = validate_projection(projected, request)
        if fails:
            raise WrapperError("projected result fails receipt discipline: "
                               + "; ".join(fails))
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(projected, indent=2) + "\n",
                               encoding="utf-8")
    except WrapperError as exc:
        return _fail(result_path, str(exc))
    return EXIT_OK


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="S49-08 echo-correcting wrapper for Skill 78 "
                    "product_selection (CR-S49-002 Path B).")
    ap.add_argument("--request", required=True,
                    help="S49 page-request JSON path ({request})")
    ap.add_argument("--result", required=True,
                    help="page-result JSON path to write ({result})")
    ap.add_argument("--work-dir", required=True,
                    help="dispatch work directory ({work_dir})")
    ap.add_argument("--launch", required=True,
                    help="launch record JSON the request references")
    ap.add_argument("--mappings", required=True,
                    help="native mapping rows (S44/S79 delivered format) "
                         "used to enrich checkout_targets")
    ap.add_argument("--s78-dir", required=True,
                    help="Skill 78 tree root holding scripts/ (main checkout "
                         "or the vendored reference copy)")
    ap.add_argument("--author-session", required=True,
                    help="author session id passed to the Skill 78 emitter")
    ap.add_argument("--recommendation",
                    help="optional approved recommendation JSON for the "
                         "plan builder")
    ap.add_argument("--status", default="locally_verified",
                    choices=list(LOCAL_STATUSES),
                    help="status the local emitter may claim (default "
                         "locally_verified; installed/live statuses are "
                         "never emittable here)")
    ap.add_argument("--plan-builder",
                    help="override plan builder path (tests only)")
    ap.add_argument("--emitter",
                    help="override emitter path (tests only; a tampered "
                         "emitter must be refused, never corrected)")
    args = ap.parse_args(argv)
    return run_wrapper(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
