#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translate_thank_you_result.py - S49-side translator for the thank_you
role (S49-08 seam, CR-S49-004 Path B).

Skill 82 resolves the thank-you page at purchase time from purchase truth
and emits (a) a thank-you result document in its own contract shape and
(b) a companion run manifest (S82 v0.3.0 scope). Neither is a page-result
1.0: the result document omits page_id, independent_review and
native_bindings_ref, and S82 never sees the S49 page-request, so it
cannot mint the echo fields honestly. This translator holds both sides:
it takes the S49 page-request it already owns plus S82's two guaranteed
inputs and emits exactly one page-result 1.0 document.

The page-request echo source dual-accepts schema 1.0 and 1.1 under the
prompt-policy pair rule (adoption map section 1.6): a 1.1 request must
carry a non-empty prompt_policy_id citation, a 1.0 request must not
carry the field, and any other schema_version is refused by name. The
citation is accepted as a citation only: it is never echoed into the
emitted page-result (whose 1.0 field set is closed) and never read as
selecting anything. For this role the policy linkage is proven at
receipts acceptance (the Q11 prompt record the aggregator validates),
not at request acceptance.

FAIL-CLOSED discipline, in this order:
  1. All three inputs must parse and carry their contract's required
     structure. A missing block or field is refused BY NAME; nothing is
     defaulted and nothing is minted.
  2. Identity must agree across all three inputs on tenant_id,
     location_id, launch_id and test_only, and the result document's
     revision must agree with the request's revision. Any disagreement
     is refused BY NAME.
  3. Every artifact the S82 result claims must resolve to a real file
     whose SHA-256 equals the claimed hash. A claimed artifact that is
     absent or hashes differently is refused BY NAME.
  4. independent_review is derived ONLY from the manifest's
     independent_review block: status "recorded" with a named reviewer
     who is not the author session yields true and reviewer_session set
     to that reviewer; status "none" (with null fields, as S82's
     contract states) yields false and reviewer_session null. Any other
     shape is refused BY NAME. A review recorded by the author session
     itself is refused: an artifact's reviewer is never its author.
  5. status / proof_class never overclaim: S82 errors or a failed S82
     validation check yield "blocked" with the input facts named as
     blockers; a clean resolution is capped at locally_verified / L2,
     because the translator holds no install or live evidence of its
     own, whatever higher status the S82 document asserts.

Echo fields (request_id, input_hash, page_id, launch_id, revision,
tenant_id, location_id, test_only) come from the S49 page-request ONLY.
The S82 result document carries its own same-named fields for its own
internal request; per S82's reply to CR-S49-004 those are not S49
facts and are neither used nor cross-checked here. author_session is
the translator's own invocation context (the dispatch run), never a
value from S82's documents.

Deterministic, stdlib only. Exit 0 ok, 2 violation, 3 usage/fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
PROOF_CAP = "L2"
STATUS_CAP = "locally_verified"
S82_STATUSES = ("authored", "locally_verified", "installed_test_verified",
                "ready_for_activation", "live_verified", "blocked")

_REQUEST_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                   "revision", "request_id", "page_id", "page_role",
                   "assigned_skill", "approval_ref", "input_hash", "brand_ref",
                   "brand_hash", "route_graph_ref", "route_graph_hash",
                   "offer_refs", "copy_profile", "allowed_write_target",
                   "test_only")
_RESULT_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                  "revision", "request_id", "input_hash", "status",
                  "order_view", "validation", "errors", "blockers",
                  "artifacts", "author_session", "reviewer_session",
                  "proof_class", "test_only")
_MANIFEST_FIELDS = ("manifest_version", "tenant_id", "location_id",
                    "launch_id", "test_only", "result_ref",
                    "independent_review", "native_bindings_ref", "provenance")


class TranslationError(ValueError):
    """A named, fail-closed refusal: the message always names the field
    or fact that cannot be honestly supplied."""


def _load(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TranslationError(f"{what}: cannot read {path}: {exc}")
    except ValueError as exc:
        raise TranslationError(f"{what}: {path} is not valid JSON: {exc}")


def _require_fields(doc: Any, fields: Any, what: str) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        raise TranslationError(f"{what} is not a JSON object")
    for f in fields:
        if f not in doc:
            raise TranslationError(f"{what} missing field {f!r}")
    return doc


def _check_request(req: Any) -> Dict[str, Any]:
    req = _require_fields(req, _REQUEST_FIELDS, "page-request")
    # Prompt-policy adoption (map section 1.6): the pair rule below is
    # the one the landed dispatch switch enforces in
    # dispatch_launch.validate_request, in the same words: a "1.1"
    # request must carry a non-empty prompt_policy_id, and a "1.0"
    # request must not carry the field at all (the Q12 encoding:
    # absence is the only encoding of "no policy", never null). The
    # citation is pair-checked here and nowhere else in this module;
    # refusing an id no registry entry carries is a registry-layer act
    # at dispatch and at the Q11 aggregator (map section 4), not an
    # echo-source act, so no registry read happens here.
    version = req["schema_version"]
    if version not in ("1.0", "1.1"):
        raise TranslationError(
            f"page-request schema_version is {version!r}; this "
            "translator dual-accepts 1.0 and 1.1 echo sources only")
    if version == "1.1":
        pid = req.get("prompt_policy_id")
        if not isinstance(pid, str) or not pid.strip():
            raise TranslationError(
                "a 1.1 page-request must carry a non-empty "
                "prompt_policy_id (the 1.1 label exists to carry the "
                "field)")
    elif "prompt_policy_id" in req:
        raise TranslationError(
            "prompt_policy_id requires page-request schema_version "
            "1.1 (the 1.0 schema forbids the field)")
    if req["page_role"] != "thank_you":
        raise TranslationError(
            f"page-request page_role is {req['page_role']!r}; this "
            "translator serves the thank_you role only")
    if req["assigned_skill"] != 82:
        raise TranslationError(
            f"page-request assigned_skill is {req['assigned_skill']!r}; "
            "the thank_you role belongs to skill 82")
    return req


def _check_s82_result(res: Any) -> Dict[str, Any]:
    res = _require_fields(res, _RESULT_FIELDS, "thank-you result document")
    if res["schema_version"] != "1.0":
        raise TranslationError(
            "thank-you result document schema_version is not 1.0")
    if res["status"] not in S82_STATUSES:
        raise TranslationError(
            f"thank-you result document has unknown status "
            f"{res['status']!r}")
    if res["proof_class"] not in LEVELS:
        raise TranslationError(
            f"thank-you result document has unknown proof_class "
            f"{res['proof_class']!r}")
    val = res["validation"]
    if not isinstance(val, dict):
        raise TranslationError("thank-you result document field "
                               "'validation' is not an object")
    for f in ("no_pitch_pass", "entitlements_match"):
        if f not in val or not isinstance(val[f], bool):
            raise TranslationError(
                f"thank-you result document field 'validation.{f}' is "
                "missing or not a boolean")
    for f in ("errors", "blockers"):
        if not isinstance(res[f], list) or \
                not all(isinstance(x, str) and x for x in res[f]):
            raise TranslationError(
                f"thank-you result document field {f!r} is not a list "
                "of non-empty strings")
    if not isinstance(res["artifacts"], list):
        raise TranslationError("thank-you result document field "
                               "'artifacts' is not a list")
    for a in res["artifacts"]:
        if not isinstance(a, dict) or "path" not in a or "sha256" not in a:
            raise TranslationError("thank-you result document has an "
                                   "artifact entry lacking path/sha256")
    return res


def _check_manifest(man: Any) -> Dict[str, Any]:
    man = _require_fields(man, _MANIFEST_FIELDS, "run manifest")
    if man["manifest_version"] != "1.0":
        raise TranslationError(
            f"run manifest manifest_version is "
            f"{man['manifest_version']!r}, not '1.0'")
    rev = man["independent_review"]
    if not isinstance(rev, dict):
        raise TranslationError("run manifest field 'independent_review' "
                               "is not an object")
    for f in ("status", "reviewer", "verdict", "record_ref"):
        if f not in rev:
            raise TranslationError(
                f"run manifest field 'independent_review.{f}' is missing")
    nb = man["native_bindings_ref"]
    if not isinstance(nb, dict):
        raise TranslationError("run manifest field 'native_bindings_ref' "
                               "is not an object")
    for f in ("envelope_ref", "entitlement_version"):
        if f not in nb:
            raise TranslationError(
                f"run manifest field 'native_bindings_ref.{f}' is "
                "missing")
    if nb["envelope_ref"] is not None and \
            (not isinstance(nb["envelope_ref"], str) or
             not nb["envelope_ref"]):
        raise TranslationError("run manifest field "
                               "'native_bindings_ref.envelope_ref' is "
                               "neither null nor a non-empty string")
    prov = man["provenance"]
    if not isinstance(prov, dict):
        raise TranslationError("run manifest field 'provenance' is not "
                               "an object")
    for f in ("snapshot_ref", "map_ref"):
        if f not in prov:
            raise TranslationError(
                f"run manifest field 'provenance.{f}' is missing")
    return man


def _cross_check_identity(req: Dict[str, Any], res: Dict[str, Any],
                          man: Dict[str, Any]) -> None:
    for f in ("tenant_id", "location_id", "launch_id", "test_only"):
        if res[f] != req[f]:
            raise TranslationError(
                f"identity mismatch on {f}: thank-you result document "
                f"has {res[f]!r}, page-request has {req[f]!r}")
        if man[f] != req[f]:
            raise TranslationError(
                f"identity mismatch on {f}: run manifest has "
                f"{man[f]!r}, page-request has {req[f]!r}")
    if res["revision"] != req["revision"]:
        raise TranslationError(
            f"identity mismatch on revision: thank-you result document "
            f"has {res['revision']!r}, page-request has "
            f"{req['revision']!r}")


def _check_manifest_binds_result(man: Dict[str, Any],
                                 res_path: Path) -> None:
    ref = man["result_ref"]
    if not isinstance(ref, str) or not ref:
        raise TranslationError("run manifest field 'result_ref' is not "
                               "a non-empty string")
    if Path(ref).name != res_path.name:
        raise TranslationError(
            f"run manifest result_ref {ref!r} does not name the result "
            f"document supplied ({res_path.name!r})")


def _derive_review(man: Dict[str, Any], author_session: str):
    rev = man["independent_review"]
    status = rev["status"]
    if status == "none":
        for f in ("reviewer", "verdict", "record_ref"):
            if rev[f] is not None:
                raise TranslationError(
                    f"run manifest independent_review.status is 'none' "
                    f"but independent_review.{f} is {rev[f]!r}, not "
                    "null; S82's contract states null fields until a "
                    "review exists")
        return False, None
    if status == "recorded":
        reviewer = rev["reviewer"]
        if not isinstance(reviewer, str) or not reviewer:
            raise TranslationError(
                "run manifest independent_review.status is 'recorded' "
                "but independent_review.reviewer is missing or empty")
        if not isinstance(rev["verdict"], str) or not rev["verdict"]:
            raise TranslationError(
                "run manifest independent_review.status is 'recorded' "
                "but independent_review.verdict is missing or empty")
        if not isinstance(rev["record_ref"], str) or not rev["record_ref"]:
            raise TranslationError(
                "run manifest independent_review.status is 'recorded' "
                "but independent_review.record_ref is missing or empty")
        if reviewer == author_session:
            raise TranslationError(
                "run manifest independent_review.reviewer equals the "
                "author session; an artifact's reviewer is never its "
                "author, so this review cannot be claimed")
        return True, reviewer
    raise TranslationError(
        f"run manifest independent_review.status {status!r} is not a "
        "status this translator can honestly translate (expected "
        "'recorded' or 'none')")


def _verify_artifacts(res: Dict[str, Any], res_dir: Path,
                      work_dir: Optional[Path]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for a in res["artifacts"]:
        claimed = a["sha256"]
        p = Path(a["path"])
        candidates = [p] if p.is_absolute() else \
            [res_dir / p, Path.cwd() / p] + \
            ([work_dir / p] if work_dir else [])
        found = next((c for c in candidates if c.is_file()), None)
        if found is None:
            raise TranslationError(
                f"artifact {a['path']!r} claimed by the thank-you "
                "result document does not resolve to a real file; "
                "refusing to carry an unverified artifact claim")
        actual = hashlib.sha256(found.read_bytes()).hexdigest()
        if actual != claimed:
            raise TranslationError(
                f"artifact {a['path']!r} hashes to {actual}, not the "
                f"claimed {claimed}; refusing a result whose artifact "
                "hashes do not verify")
        out.append({"path": a["path"], "sha256": claimed})
    return out


def _derive_status(res: Dict[str, Any]):
    blockers: List[str] = []

    def add(text: str) -> None:
        if text not in blockers:
            blockers.append(text)

    for e in res["errors"]:
        add(e)
    val = res["validation"]
    for f in ("no_pitch_pass", "entitlements_match"):
        if val[f] is not True:
            add(f"S82 validation check failed: validation.{f} is false")
    for b in res["blockers"]:
        add(b)
    if res["errors"] or val["no_pitch_pass"] is not True or \
            val["entitlements_match"] is not True:
        return "blocked", blockers
    if res["status"] == "blocked":
        if not blockers:
            add("S82 thank-you result reports status 'blocked' with no "
                "named errors or blockers")
        return "blocked", blockers
    status = res["status"]
    if status not in ("authored", STATUS_CAP):
        status = STATUS_CAP
    return status, blockers


def _cap_proof(proof_class: str) -> str:
    return LEVELS[min(LEVELS.index(proof_class), LEVELS.index(PROOF_CAP))]


def translate(req: Dict[str, Any], res: Dict[str, Any],
              man: Dict[str, Any], *, author_session: str,
              res_path: Path,
              work_dir: Optional[Path]) -> Dict[str, Any]:
    _cross_check_identity(req, res, man)
    _check_manifest_binds_result(man, res_path)
    independent_review, reviewer_session = _derive_review(
        man, author_session)
    artifacts = _verify_artifacts(res, res_path.resolve().parent,
                                  work_dir)
    status, blockers = _derive_status(res)
    return {
        "schema_version": "1.0",
        "tenant_id": req["tenant_id"],
        "location_id": req["location_id"],
        "launch_id": req["launch_id"],
        "revision": req["revision"],
        "request_id": req["request_id"],
        "input_hash": req["input_hash"],
        "page_id": req["page_id"],
        "status": status,
        "artifacts": artifacts,
        "author_session": author_session,
        "reviewer_session": reviewer_session,
        "independent_review": independent_review,
        "proof_class": _cap_proof(res["proof_class"]),
        "blockers": blockers,
        "native_bindings_ref": man["native_bindings_ref"]["envelope_ref"],
        "test_only": req["test_only"],
    }


def _author_session_from_context(args) -> Optional[str]:
    if args.author_session:
        return args.author_session
    for env in ("SIGNATURE_LAUNCH_AUTHOR_SESSION", "OPENCLAW_SESSION_ID",
                "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID"):
        if os.environ.get(env):
            return os.environ[env]
    return None


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Translate an S82 thank-you result + run manifest "
                    "into a page-result 1.0 for the S49 thank_you role.")
    ap.add_argument("request", help="S49 page-request JSON (thank_you)")
    ap.add_argument("result", help="page-result 1.0 path to write")
    ap.add_argument("work_dir", nargs="?", default=None,
                    help="dispatch work dir (locates S82 inputs by "
                         "default and resolves relative artifact paths)")
    ap.add_argument("--s82-result", default=None,
                    help="S82 thank-you result document (default: "
                         "<work_dir>/thank-you-result.json, else beside "
                         "the request)")
    ap.add_argument("--manifest", default=None,
                    help="S82 companion run manifest (default: "
                         "<work_dir>/thank-you-run-manifest.json, else "
                         "beside the request)")
    ap.add_argument("--author-session", default=None,
                    help="the dispatch run's session identity (the "
                         "page-result author); falls back to "
                         "SIGNATURE_LAUNCH_AUTHOR_SESSION / "
                         "OPENCLAW_SESSION_ID environment")
    args = ap.parse_args(argv)

    author_session = _author_session_from_context(args)
    if not author_session:
        print("USAGE ERROR: no author session: pass --author-session or "
              "set SIGNATURE_LAUNCH_AUTHOR_SESSION. The page-result "
              "author is the dispatch run and is never taken from S82's "
              "documents.")
        return EXIT_FAILCLOSED
    req_path = Path(args.request)
    work_dir = Path(args.work_dir) if args.work_dir else None
    base = work_dir if work_dir else req_path.resolve().parent
    res_path = Path(args.s82_result) if args.s82_result else \
        base / "thank-you-result.json"
    man_path = Path(args.manifest) if args.manifest else \
        base / "thank-you-run-manifest.json"
    try:
        req = _check_request(_load(req_path, "page-request"))
        res = _check_s82_result(_load(res_path, "thank-you result "
                                             "document"))
        man = _check_manifest(_load(man_path, "run manifest"))
        out = translate(req, res, man, author_session=author_session,
                        res_path=res_path, work_dir=work_dir)
    except TranslationError as exc:
        print(f"TRANSLATION REFUSED: {exc}")
        return EXIT_VIOLATION
    Path(args.result).write_text(json.dumps(out, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps({"translated": True, "status": out["status"],
                      "proof_class": out["proof_class"],
                      "independent_review": out["independent_review"]}))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
