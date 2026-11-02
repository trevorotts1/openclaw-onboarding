#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture tests for translate_thank_you_result.py (S49-08, CR-S49-004
Path B). Each case stages the three inputs in a temp dir, runs the
translator as a subprocess exactly as a dispatch adapter would, and
checks exit codes, refusal messages and the emitted page-result.

The happy-path page-result is validated three ways: exact 17-field set,
real JSON Schema validation against the packet page-result 1.0 schema,
and collect_launch_receipts' own validate_result + collect rollup.

Cases 10 onward cover prompt-policy adoption (adoption map section
1.6): the 1.1 echo source under the pair rule, translation against a
real companion run manifest built by Skill 82's own emitter, the
pair-rule refusal set, and the receipts-acceptance closure of a Q11
prompt item citing the governing policy against the registry of
record.

Cases 18 onward cover the design-only launch mode (DTY-01) and the
recomputed-trust rules (DTY-02): a forged result + manifest pair is
refused, validation is recomputed from the snapshot whose sha the
manifest binds, and a recorded review needs its record file (sha bound)
and a dispatch-registered reviewer. Refusals print to stderr.

Exit 0 when every case passes (also collected by pytest as one test).
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANE = HERE
FIXTURES = LANE / "fixtures"
TRANSLATOR = LANE / "translate_thank_you_result.py"
WAVE1_SCRIPTS = LANE
PACKET_SCHEMAS = LANE / "vendor"
AUTHOR = "s49-dispatch-fixture-session"

sys.path.insert(0, str(WAVE1_SCRIPTS))
import collect_launch_receipts as receipts  # noqa: E402

RESULT_FIELDS = {"schema_version", "tenant_id", "location_id", "launch_id",
                 "revision", "request_id", "input_hash", "page_id",
                 "status", "artifacts", "author_session", "reviewer_session",
                 "independent_review", "proof_class", "blockers",
                 "native_bindings_ref", "test_only"}

ok = True


def say(good: bool, msg: str) -> None:
    global ok
    ok = ok and good
    print(f"TEST {'ok' if good else 'FAIL'}: {msg}")


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def resolve_repo_root(start: Path) -> Path:
    """Nearest ancestor that looks like a checkout, for both layouts.

    The onboarding repository puts skills at the repo root; a deployed
    999 package puts them under ``.claude/skills``, so ``HERE.parents[1]``
    is NOT the repository root there. Both layouts carry shared-utils at
    the root (the same marker the Launcher's constants.py uses).
    """
    for candidate in (start, *start.parents):
        if (candidate / "shared-utils").is_dir() and (
                (candidate / ".claude").is_dir()
                or (candidate / "CONTROL").is_dir()):
            return candidate
    return start.parents[1]


def resolve_s82_root(repo_root: Path) -> Path:
    """Skill 82's tree under either naming convention.

    The onboarding repository uses ``82-signature-thank-you`` at the
    repository root; a 999 package uses the bare slug under
    ``.claude/skills``. Nothing here spells a numbered directory as the
    only option, so the same test runs in both layouts.
    """
    for candidate in (
            repo_root / "82-signature-thank-you",
            repo_root / "signature-thank-you",
            repo_root / ".claude" / "skills" / "signature-thank-you",
            repo_root / ".claude" / "skills" / "82-signature-thank-you"):
        if (candidate / "scripts" / "run_manifest.py").is_file():
            return candidate
    raise FileNotFoundError(
        "skill 82 tree not found under either naming convention: "
        f"looked for 82-signature-thank-you / signature-thank-you under "
        f"{repo_root} and {repo_root / '.claude' / 'skills'}")


S82_ROOT = resolve_s82_root(resolve_repo_root(HERE))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(td: Path, req=None, res=None, man=None, with_artifact=True,
          trust=True, view=None):
    """Stage the three inputs. trust=True also stages what a genuine
    purchase-time run leaves behind: the purchase snapshot (sha bound in
    the manifest), a review record (sha bound) and the dispatch session
    registry. trust=False stages the documents exactly as given."""
    req = load("page-request.json") if req is None else req
    res = copy.deepcopy(load("thank-you-result.json") if res is None
                        else res)
    man = copy.deepcopy(load("thank-you-run-manifest.json") if man is None
                        else man)
    if trust:
        ident = {k: req[k] for k in ("tenant_id", "location_id",
                                     "launch_id", "revision", "test_only")}
        snap = json.loads((S82_ROOT / "fixtures" / "test-only-snapshot.json")
                          .read_text(encoding="utf-8"))
        snap.update(ident)
        if view is None:
            view = json.loads((S82_ROOT / "fixtures"
                               / "test-only-order-view.json")
                              .read_text(encoding="utf-8"))
            view.update(ident)
            # Skill 82's validators (DTY-18) take a link's expected URL and its
            # independent-authorization flag from the S44 fulfillment map, never
            # from the view. The translator hands them no map, so any block that
            # carries a delivery_url is refused (delivery_url_mismatch, then
            # missing_independent_authorization). A block with no delivery_url
            # renders no link and is not checked, so the fixture view stages its
            # access blocks link-free (entitlement and next_action kept).
            for block in view.get("access_blocks") or []:
                block.pop("delivery_url", None)
        res["order_view"] = view
        (td / "purchase-snapshot.json").write_text(
            json.dumps(snap, indent=2), encoding="utf-8")
        man["provenance"]["snapshot_ref"] = "purchase-snapshot.json"
        man["provenance"]["snapshot_sha256"] = _sha(
            td / "purchase-snapshot.json")
        rev = man["independent_review"]
        if rev["status"] == "recorded":
            (td / "review-record.md").write_text("verified\n",
                                                 encoding="utf-8")
            rev["record_ref"] = "review-record.md"
            rev["record_sha256"] = _sha(td / "review-record.md")
            (td / "dispatch-session-registry.json").write_text(
                json.dumps({"sessions": [rev["reviewer"]]}),
                encoding="utf-8")
    (td / "page-request.json").write_text(json.dumps(req, indent=2),
                                          encoding="utf-8")
    (td / "thank-you-result.json").write_text(json.dumps(res, indent=2),
                                              encoding="utf-8")
    (td / "thank-you-run-manifest.json").write_text(json.dumps(man, indent=2),
                                                    encoding="utf-8")
    if with_artifact:
        (td / "thank-you-render.html").write_bytes(
            (FIXTURES / "thank-you-render.html").read_bytes())
    return td / "page-result.json"


def run(td: Path, author: str = AUTHOR):
    return subprocess.run(
        [sys.executable, str(TRANSLATOR), str(td / "page-request.json"),
         str(td / "page-result.json"), str(td), "--author-session", author],
        capture_output=True, text=True)


def review_kw(out) -> dict:
    """ENF-10: a result claiming independent_review counts only through a review
    record whose reviewer session is in the dispatch ledger and which lists the
    sha256 of every artifact (two session strings are not a review). The
    collector's own inputs for that, built from the translated result."""
    if not out.get("independent_review"):
        return {}
    reviewer = out["reviewer_session"]
    return {"ledger": {"sessions": [{"session_id": reviewer,
                                     "model": "fixture-reviewer-model"}]},
            "review": {"schema": "signature-launch-review-record/v1",
                       "reviewer_session": reviewer,
                       "reviewer_model": "fixture-reviewer-model",
                       "request_id": out["request_id"],
                       "reviewed_artifacts": [
                           {"path": a["path"], "sha256": a["sha256"]}
                           for a in out["artifacts"]]}}


def collect_kw(out) -> dict:
    kw = review_kw(out)
    return ({"ledger": kw["ledger"],
             "review_records": {out["request_id"]: kw["review"]}}
            if kw else {})


def manifest_for(req):
    return {"launch_id": req["launch_id"],
            "revision": req["revision"],
            "plan_document_hash": "fixture-plan-hash",
            "route_graph_hash": req["route_graph_hash"],
            "execution": "executed",
            "requests": [{"request_id": req["request_id"],
                          "page_id": req["page_id"],
                          "page_role": "thank_you",
                          "assigned_skill": 82,
                          "input_hash": req["input_hash"]}]}


def main() -> int:
    req0 = load("page-request.json")

    # Case 1: happy path. Output must be a page-result 1.0 that passes
    # real schema validation and the receipt collector's own rules.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        out_path = stage(td)
        proc = run(td)
        print("happy-path stdout:", proc.stdout.strip())
        say(proc.returncode == 0, f"happy path exits 0 (got "
                                  f"{proc.returncode}: {proc.stderr.strip()})")
        out = json.loads(out_path.read_text(encoding="utf-8"))
        say(set(out.keys()) == RESULT_FIELDS,
            "happy path emits exactly the 17 page-result fields")
        try:
            import jsonschema
            schema = json.loads((PACKET_SCHEMAS /
                                 "page-result.schema.json")
                                .read_text(encoding="utf-8"))
            jsonschema.validate(out, schema)
            say(True, "happy path output validates against the packet "
                      "page-result 1.0 JSON Schema")
        except Exception as exc:  # noqa: BLE001
            say(False, f"happy path JSON Schema validation: {exc}")
        fails = receipts.validate_result(out, req0, **review_kw(out))
        say(fails == [], f"happy path passes collect_launch_receipts."
                         f"validate_result (fails={fails})")
        manifest = {"launch_id": req0["launch_id"],
                    "revision": req0["revision"],
                    "plan_document_hash": "fixture-plan-hash",
                    "route_graph_hash": req0["route_graph_hash"],
                    "execution": "executed",
                    "requests": [{"request_id": req0["request_id"],
                                  "page_id": req0["page_id"],
                                  "page_role": "thank_you",
                                  "assigned_skill": 82,
                                  "input_hash": req0["input_hash"]}]}
        cp = receipts.collect(manifest, [out],
                              {req0["request_id"]: req0}, **collect_kw(out))
        say(cp["roles_reported"] == ["thank_you"] and not cp["problems"],
            f"happy path is counted by collect() (problems={cp['problems']})")
        say(out["independent_review"] is True and
            out["reviewer_session"] == "SWARM",
            "happy path derives independent_review + reviewer_session "
            "from the manifest only")
        say(out["author_session"] == AUTHOR,
            "happy path author_session is the invocation context, not "
            "the S82 document's author_session")
        say(out["status"] == "locally_verified" and
            out["proof_class"] == "L2",
            "happy path status/proof carried honestly (locally_verified "
            "/ L2)")
        say(out["native_bindings_ref"] ==
            "rooms/S44/work/l4/l4-refund-results.json#map_after_refund",
            "happy path native_bindings_ref is the manifest envelope_ref")
        say(out["artifacts"] == load("thank-you-result.json")["artifacts"],
            "happy path artifacts carried with file-verified hashes")

    # Case 2: identity mismatch (result document location) fails closed.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        res = load("thank-you-result.json")
        res["location_id"] = "WRONG-LOCATION"
        stage(td, res=res)
        proc = run(td)
        print("identity-mismatch output:", proc.stderr.strip())
        say(proc.returncode == 2 and "location_id" in proc.stderr,
            "identity mismatch on location_id refused, naming the field")
        say(not (td / "page-result.json").exists(),
            "identity mismatch writes no page-result")

    # Case 3: manifest independent_review status none yields
    # independent_review false and reviewer_session null, still valid.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        man = load("thank-you-run-manifest.json")
        man["independent_review"] = {"status": "none", "reviewer": None,
                                     "verdict": None, "record_ref": None}
        out_path = stage(td, man=man)
        proc = run(td)
        say(proc.returncode == 0, "review-none manifest still translates")
        out = json.loads(out_path.read_text(encoding="utf-8"))
        say(out["independent_review"] is False and
            out["reviewer_session"] is None,
            "status none yields independent_review false, reviewer null")
        say(receipts.validate_result(out, req0, **review_kw(out)) == [],
            "review-none output still passes receipt validation")

    # Case 4: S82 errors non-empty yields status blocked with the
    # errors named as blockers.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        res = load("thank-you-result.json")
        res["errors"] = ["entitlement ev1 version unreadable at resolver"]
        res["status"] = "blocked"
        out_path = stage(td, res=res)
        proc = run(td)
        say(proc.returncode == 0, "errored S82 result still translates")
        out = json.loads(out_path.read_text(encoding="utf-8"))
        say(out["status"] == "blocked" and
            "entitlement ev1 version unreadable at resolver"
            in out["blockers"],
            "S82 errors produce status blocked with the error named")

    # Case 5: a missing manifest block fails closed naming the field.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        man = load("thank-you-run-manifest.json")
        del man["native_bindings_ref"]
        stage(td, man=man)
        proc = run(td)
        print("missing-block output:", proc.stderr.strip())
        say(proc.returncode == 2 and "native_bindings_ref" in proc.stderr,
            "missing native_bindings_ref block refused, naming the field")

    # Case 6: a claimed artifact absent on disk fails closed.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td, with_artifact=False)
        proc = run(td)
        print("missing-artifact output:", proc.stderr.strip())
        say(proc.returncode == 2 and "thank-you-render.html"
            in proc.stderr,
            "absent claimed artifact refused, naming the artifact")

    # Case 7: a review recorded by the author session itself is
    # refused (an artifact's reviewer is never its author).
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td)
        proc = run(td, author="SWARM")
        print("self-review output:", proc.stderr.strip())
        say(proc.returncode == 2 and "independent_review" in proc.stderr,
            "reviewer == author refused, naming independent_review")

    # Case 8: an S82 status claiming install-level proof is capped at
    # locally_verified / L2.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        res = load("thank-you-result.json")
        res["status"] = "live_verified"
        res["proof_class"] = "L5"
        out_path = stage(td, res=res)
        proc = run(td)
        out = json.loads(out_path.read_text(encoding="utf-8"))
        say(proc.returncode == 0 and out["status"] == "locally_verified"
            and out["proof_class"] == "L2",
            "install/live claims from the S82 document are capped at "
            "locally_verified / L2")

    # Case 9: a real S82 v0.3.0 no-envelope run manifest (delta D-1):
    # native_bindings_ref.envelope_ref is null, the emitter's normal
    # plain-run shape, which the manifest schema expressly permits.
    # The translation must succeed and carry the null through verbatim.
    # The manifest staged below is the shipped fixture manifest with
    # its review, bindings and provenance blocks set to the real
    # no-envelope run's values; it deep-equals the real emitter's
    # plain-run output (translator real-manifest verification,
    # instance B).
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        man = load("thank-you-run-manifest.json")
        man["independent_review"] = {"status": "none", "reviewer": None,
                                     "verdict": None, "record_ref": None}
        man["native_bindings_ref"] = {"envelope_ref": None,
                                      "entitlement_version": None}
        man["provenance"] = {"snapshot_ref": None, "map_ref": None}
        out_path = stage(td, man=man)  # stage binds the purchase snapshot
        proc = run(td)
        print("no-envelope stdout:", proc.stdout.strip())
        say(proc.returncode == 0,
            f"no-envelope real manifest (envelope_ref null) translates "
            f"(got {proc.returncode}: {proc.stderr.strip()})")
        out = json.loads(out_path.read_text(encoding="utf-8"))
        say(out["native_bindings_ref"] is None,
            "no-envelope output carries envelope_ref null verbatim as "
            "native_bindings_ref")
        say(receipts.validate_result(out, req0, **review_kw(out)) == [],
            "no-envelope output passes collect_launch_receipts."
            "validate_result with zero problems")

    # Case 10: prompt-policy adoption (map 1.6). A 1.1 echo source
    # carrying the kie-rule-12-band citation translates end to end,
    # and the emitted page-result is exactly the document the 1.0
    # source produces: the citation is pair-checked at read time and
    # never echoed (the page-result 1.0 field set is closed).
    req11 = load("page-request-policy.json")
    out11 = None
    with tempfile.TemporaryDirectory() as td1s, \
            tempfile.TemporaryDirectory() as td0s:
        td1, td0 = Path(td1s), Path(td0s)
        out_path11 = stage(td1, req=req11)
        proc = run(td1)
        print("1.1 happy-path stdout:", proc.stdout.strip())
        say(proc.returncode == 0,
            f"1.1 citation-carrying echo source translates (got "
            f"{proc.returncode}: {proc.stderr.strip()})")
        if out_path11.exists():
            out11 = json.loads(out_path11.read_text(encoding="utf-8"))
        out_path10 = stage(td0)
        proc0 = run(td0)
        say(proc0.returncode == 0, "1.0 control run inside case 10 "
                                   "translates")
        out10 = json.loads(out_path10.read_text(encoding="utf-8"))
    if out11 is not None:
        say(set(out11.keys()) == RESULT_FIELDS,
            "1.1 translation emits exactly the 17 page-result fields")
        say("prompt_policy_id" not in out11,
            "1.1 translation does not echo the citation into the "
            "page-result")
        say(out11 == out10,
            "1.1 translation output is identical to the 1.0 output "
            "(acceptance is the only effect of the 1.1 echo source)")
        say(receipts.validate_result(out11, req11, **review_kw(out11)) == [],
            "1.1 translation passes collect_launch_receipts."
            "validate_result against the 1.1 request with zero fails")
        cp = receipts.collect(manifest_for(req11), [out11],
                              {req11["request_id"]: req11},
                              **collect_kw(out11))
        say(cp["roles_reported"] == ["thank_you"] and not cp["problems"],
            f"collect() rollup over the translated 1.1 result reports "
            f"thank_you with zero problems (got problems "
            f"{cp['problems']})")

    # Case 11: the same 1.1 translation against a REAL S82 companion
    # run manifest, built at test time by Skill 82's own emitter
    # (82-signature-thank-you/scripts/run_manifest.py) from S82's
    # test-only order view carrying this fixture launch's identity,
    # and validated against S82's own run-manifest schema. This is
    # map 1.6's readiness evidence form: the translator proven
    # against the manifest S82 actually emits, not a hand-written
    # stand-in.
    repo_root = resolve_repo_root(HERE)
    s82_root = resolve_s82_root(repo_root)
    s82_scripts = s82_root / "scripts"
    sys.path.insert(0, str(s82_scripts))
    import run_manifest as s82_emitter  # noqa: E402
    view = json.loads((s82_root / "fixtures"
                       / "test-only-order-view.json").read_text(
                           encoding="utf-8"))
    for f in ("tenant_id", "location_id", "launch_id", "test_only"):
        view[f] = req11[f]
    man_real = s82_emitter.build_run_manifest(
        view,
        independent_review={
            "status": "recorded", "reviewer": "SWARM",
            "verdict": "verified",
            "record_ref": "rooms/S82/work/review-a13-l3-verification.md"},
        envelope_ref=("rooms/S44/work/l4/l4-refund-results.json"
                      "#map_after_refund"),
        snapshot_ref=("rooms/S06/work/l3/"
                      "native-order-read-6ad22df3baae1b6f9b2d5674.json"),
        map_ref=("rooms/S44/work/l4/l4-refund-results.json"
                 "#map_after_refund"),
        result_ref="thank-you-result.json")
    try:
        import jsonschema
        mschema = json.loads(
            (s82_root / "schemas"
             / "run-manifest.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(man_real, mschema)
        say(True, "emitter-built companion manifest validates against "
                  "S82's run-manifest schema")
    except Exception as exc:  # noqa: BLE001
        say(False, f"emitter-built companion manifest validates "
                   f"against S82's run-manifest schema ({exc})")
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        out_path = stage(td, req=req11, man=man_real)
        proc = run(td)
        print("1.1 vs real-manifest stdout:", proc.stdout.strip())
        say(proc.returncode == 0,
            f"1.1 translation succeeds against the emitter-built S82 "
            f"companion manifest (got {proc.returncode}: "
            f"{proc.stderr.strip()})")
        if out_path.exists():
            out_real = json.loads(out_path.read_text(encoding="utf-8"))
            say(out_real["independent_review"] is True
                and out_real["reviewer_session"] == "SWARM",
                "real-manifest translation carries the manifest's "
                "recorded independent review")
            say(receipts.validate_result(out_real, req11,
                                         **review_kw(out_real)) == [],
                "real-manifest translation passes validate_result "
                "with zero fails")
            cp = receipts.collect(manifest_for(req11), [out_real],
                                  {req11["request_id"]: req11},
                                  **collect_kw(out_real))
            say(not cp["problems"],
                f"collect() rollup over the real-manifest translation "
                f"has zero problems (got {cp['problems']})")

    # Case 12: a 1.1 echo source MISSING the citation is refused,
    # naming the defect, and nothing is written.
    req = load("page-request-policy.json")
    del req["prompt_policy_id"]
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        out_path = stage(td, req=req)
        proc = run(td)
        say(proc.returncode == 2 and "prompt_policy_id" in proc.stderr,
            f"1.1 source missing prompt_policy_id refused naming the "
            f"field (exit {proc.returncode}: {proc.stderr.strip()})")
        say(not out_path.exists(),
            "no page-result written for the missing-citation refusal")

    # Case 13: a 1.0 echo source CARRYING the field is refused (the
    # pair rule's other half; absence is the only 1.0 encoding).
    req = load("page-request.json")
    req["prompt_policy_id"] = "kie-rule-12-band"
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        out_path = stage(td, req=req)
        proc = run(td)
        say(proc.returncode == 2 and "prompt_policy_id" in proc.stderr
            and "1.1" in proc.stderr,
            f"1.0 source carrying prompt_policy_id refused naming the "
            f"pair rule (exit {proc.returncode}: {proc.stderr.strip()})")
        say(not out_path.exists(),
            "no page-result written for the 1.0-with-field refusal")

    # Case 14: malformed citations on a 1.1 source are each refused
    # naming the field: empty string, blank string, null, a number,
    # and an object (a selector shape is not a citation).
    for label, bad in (("empty string", ""), ("blank string", "   "),
                       ("null", None), ("number", 42),
                       ("object", {"policy_id": "kie-rule-12-band"})):
        req = load("page-request-policy.json")
        req["prompt_policy_id"] = bad
        with tempfile.TemporaryDirectory() as tds:
            td = Path(tds)
            out_path = stage(td, req=req)
            proc = run(td)
            say(proc.returncode == 2
                and "prompt_policy_id" in proc.stderr,
                f"1.1 source with {label} prompt_policy_id refused "
                f"naming the field (exit {proc.returncode}: "
                f"{proc.stderr.strip()})")
            say(not out_path.exists(),
                f"no page-result written for the {label} refusal")

    # Case 15: unknown schema_versions are refused naming the value:
    # a future version string, an intermediate string, and a number.
    for label, bad in (("string 2.0", "2.0"), ("string 1.2", "1.2"),
                       ("number 1.1", 1.1)):
        req = load("page-request.json")
        req["schema_version"] = bad
        with tempfile.TemporaryDirectory() as tds:
            td = Path(tds)
            out_path = stage(td, req=req)
            proc = run(td)
            say(proc.returncode == 2
                and "schema_version" in proc.stderr,
                f"echo source with schema_version {label} refused "
                f"naming the defect (exit {proc.returncode}: "
                f"{proc.stderr.strip()})")
            say(not out_path.exists(),
                f"no page-result written for the {label} refusal")

    # Case 16: registry-layer allocation, pinned. An UNREGISTERED
    # non-empty citation passes this translator: refusal of unknown
    # ids sits at dispatch and at the Q11 aggregator (map section
    # 4), never at the echo source.
    req = load("page-request-policy.json")
    req["prompt_policy_id"] = "unregistered-policy-xyz"
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        out_path = stage(td, req=req)
        proc = run(td)
        say(proc.returncode == 0 and out_path.exists(),
            f"translator accepts an unregistered non-empty citation "
            f"(registry refusal is not the echo source's layer; got "
            f"{proc.returncode}: {proc.stderr.strip()})")

    # Case 17: the policy linkage for this role is proven at
    # RECEIPTS acceptance (map 1.6 item 3): a Q11 prompt asset
    # receipt for the thank_you page, citing kie-rule-12-band and the
    # registry entry hash of record, closes the prompt item with
    # zero problems when the aggregator validates it against the
    # Q13 registry of record.
    if out11 is not None:
        registry = json.loads(
            (repo_root / "shared-utils" / "signature_launch" / "domain"
             / "prompt-policy-registry.json").read_text(
                 encoding="utf-8"))
        artifact_sha = load("thank-you-result.json")["artifacts"][0][
            "sha256"]
        active_hash = next(
            e["entry_hash"] for e in registry["entries"]
            if e["policy_id"] == "kie-rule-12-band"
            and e["entry_status"] == "active")
        receipt = {
            "schema_version": "1.0",
            "tenant_id": req11["tenant_id"],
            "launch_id": req11["launch_id"],
            "revision": req11["revision"],
            "page_id": req11["page_id"],
            "requested_provider": "KIE",
            "requested_model": "gpt-image-2-5",
            "actual_provider": "KIE",
            "actual_model": "gpt-image-2-5",
            "mode": "text-to-image",
            "request_metadata": {},
            "provider_receipt_ids": {"kie_task_id": "fixture-task-0001"},
            "result_hash": artifact_sha,
            "result_dimensions": {"width": 1024, "height": 1024},
            "budget_decision": {
                "decision": "OK",
                "prompt_policy_id": "kie-rule-12-band",
                "registry_entry_hash": active_hash},
            "output_path": "thank-you-render.html",
            "prompt_artifact_path": "thank-you-render.html",
            "prompt_hash": artifact_sha,
            "independent_visual_qc": {"status": "pass"},
        }
        cp = receipts.collect(manifest_for(req11), [out11],
                              {req11["request_id"]: req11},
                              asset_receipts=[receipt],
                              registry=registry, **collect_kw(out11))
        closed = cp["prompt_items"]["closed"]
        say(not cp["problems"] and len(closed) == 1
            and closed[0]["prompt_policy_id"] == "kie-rule-12-band",
            f"Q11 prompt item for thank_you closes against the "
            f"registry of record with zero problems (got problems "
            f"{cp['problems']}, closed {closed})")

    new_cases(req0)
    print("TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def _images_dir(td: Path) -> Path:
    """A thank-you Skill 71 run folder holding one design file."""
    d = td / "thank_you-run" / "desktop-wireframe"
    d.mkdir(parents=True)
    (d / "section-01.png").write_bytes(b"\x89PNG fixture")
    return td / "thank_you-run"


def new_cases(req0) -> None:
    # Case 18: design-only needs no S82 document and no snapshot.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        (td / "page-request.json").write_text(json.dumps(req0),
                                              encoding="utf-8")
        images = _images_dir(td)
        proc = subprocess.run(
            [sys.executable, str(TRANSLATOR), str(td / "page-request.json"),
             str(td / "page-result.json"), str(td), "--design-only",
             "--images-run-dir", str(images), "--author-session", AUTHOR],
            capture_output=True, text=True)
        say(proc.returncode == 0,
            f"design-only translates with no snapshot, result or manifest "
            f"(got {proc.returncode}: {proc.stderr.strip()})")
        out = json.loads((td / "page-result.json").read_text(
            encoding="utf-8"))
        say(out["status"] == "authored" and out["proof_class"] == "L0"
            and out["independent_review"] is False
            and out["reviewer_session"] is None
            and "THANK-YOU-RUNTIME-NOT-INSTALLED" in out["blockers"]
            and any(a["path"].endswith("section-01.png")
                    for a in out["artifacts"]),
            "design-only is authored/L0, no review, carries the standing "
            "blocker THANK-YOU-RUNTIME-NOT-INSTALLED and the design files")
        say(any("design deliverable only" in b for b in out["blockers"]),
            "design-only blockers say plainly the page is a design "
            "deliverable only (status stays 'authored': the page-result "
            "schema enum has no 'design_only')")
        say(json.loads(proc.stdout)["design_only"] is True,
            "design-only says so in its summary line")
        say(receipts.validate_result(out, req0) == [],
            "design-only output passes collect_launch_receipts."
            "validate_result")
        try:
            import jsonschema
            jsonschema.validate(out, json.loads(
                (PACKET_SCHEMAS / "page-result.schema.json")
                .read_text(encoding="utf-8")))
            say(True, "design-only output validates against the packet "
                      "page-result 1.0 JSON Schema")
        except Exception as exc:  # noqa: BLE001
            say(False, f"design-only JSON Schema validation: {exc}")

    # Case 19: design-only with no design files is refused to stderr.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        (td / "page-request.json").write_text(json.dumps(req0),
                                              encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(TRANSLATOR), str(td / "page-request.json"),
             str(td / "page-result.json"), str(td), "--design-only",
             "--author-session", AUTHOR], capture_output=True, text=True)
        say(proc.returncode == 2 and "no artifacts" in proc.stderr
            and proc.stdout.strip() == ""
            and not (td / "page-result.json").exists(),
            "design-only without design files refused 'no artifacts' on "
            "stderr, nothing on stdout, nothing written")

    # Case 20: the forged pair. Hand-written result (true booleans, no
    # artifacts) + manifest (made-up reviewer, no snapshot, unresolved
    # record) used to become locally_verified/L2 with independent_review.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        res = load("thank-you-result.json")
        res["artifacts"] = []
        stage(td, res=res, trust=False, with_artifact=False)
        proc = run(td)
        say(proc.returncode != 0 and not (td / "page-result.json").exists()
            and all(s in proc.stderr for s in (
                "validation recomputed", "record_ref unresolved",
                "no artifacts")) and proc.stdout.strip() == "",
            f"forged pair refused naming validation recomputed, record_ref "
            f"unresolved and no artifacts (exit {proc.returncode}: "
            f"{proc.stderr.strip()})")

    # Case 21: true validation booleans do not rescue a tampered view.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        view = json.loads((S82_ROOT / "fixtures" / "test-only-order-view.json")
                          .read_text(encoding="utf-8"))
        view.update({k: req0[k] for k in ("tenant_id", "location_id",
                                          "launch_id", "revision",
                                          "test_only")})
        view["order_ref"] = "SOMEONE-ELSES-ORDER"
        stage(td, view=view)
        proc = run(td)
        say(proc.returncode == 2 and "validation recomputed" in proc.stderr
            and "order_ref_mismatch" in proc.stderr,
            f"validators recomputed over order_view catch a wrong order "
            f"despite validation booleans true ({proc.stderr.strip()})")

    # Case 22: a snapshot whose sha is not the bound one is refused.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td)
        snap = json.loads((td / "purchase-snapshot.json").read_text(
            encoding="utf-8"))
        snap["note"] = "edited after the manifest bound it"
        (td / "purchase-snapshot.json").write_text(json.dumps(snap),
                                                   encoding="utf-8")
        proc = run(td)
        say(proc.returncode == 2 and "validation recomputed" in proc.stderr
            and "snapshot_sha256" in proc.stderr,
            "snapshot not matching manifest.provenance.snapshot_sha256 "
            "refused")

    # Case 23: review record edited, and a reviewer the dispatch never
    # recorded, are each refused.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td)
        (td / "review-record.md").write_text("edited\n", encoding="utf-8")
        proc = run(td)
        say(proc.returncode == 2 and "record_ref unresolved" in proc.stderr,
            "review record not matching record_sha256 refused")
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td)
        (td / "dispatch-session-registry.json").write_text(
            json.dumps({"sessions": ["some-other-session"]}),
            encoding="utf-8")
        proc = run(td)
        say(proc.returncode == 2 and "reviewer unregistered" in proc.stderr,
            "reviewer absent from the dispatch session registry refused")

    # Case 24: Skill 82's emitter carries the sha bindings and builds the
    # design-time manifest. The shipped schema's closed shape does not yet
    # list the two sha fields, so the schema is checked on the design-time
    # manifest and on the emitter's output without them.
    sys.path.insert(0, str(S82_ROOT / "scripts"))
    import run_manifest as s82_emitter  # noqa: E402
    dm = s82_emitter.build_design_manifest(
        req0["tenant_id"], req0["location_id"], req0["launch_id"],
        test_only=True)
    try:
        import jsonschema
        jsonschema.validate(dm, json.loads(
            (S82_ROOT / "schemas" / "run-manifest.schema.json")
            .read_text(encoding="utf-8")))
        say(dm["independent_review"]["status"] == "none"
            and dm["provenance"]["snapshot_ref"] is None,
            "design-time manifest is schema-valid with every purchase "
            "fact null")
    except Exception as exc:  # noqa: BLE001
        say(False, f"design-time manifest schema validation: {exc}")
    view = json.loads((S82_ROOT / "fixtures" / "test-only-order-view.json")
                      .read_text(encoding="utf-8"))
    mm = s82_emitter.build_run_manifest(
        view, snapshot_ref="s.json", snapshot_sha256="a" * 64,
        independent_review={"status": "recorded", "reviewer": "r",
                            "verdict": "v", "record_ref": "r.md",
                            "record_sha256": "b" * 64})
    say(mm["provenance"]["snapshot_sha256"] == "a" * 64
        and mm["independent_review"]["record_sha256"] == "b" * 64,
        "run manifest emitter binds snapshot_sha256 and record_sha256")


def test_thankyou_translator():
    """pytest entry: the whole case list is one test."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
