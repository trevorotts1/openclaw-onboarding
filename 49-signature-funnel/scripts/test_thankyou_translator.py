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

Exit 0 when every case passes.
"""

from __future__ import annotations

import copy
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


def stage(td: Path, req=None, res=None, man=None, with_artifact=True):
    req = load("page-request.json") if req is None else req
    res = load("thank-you-result.json") if res is None else res
    man = load("thank-you-run-manifest.json") if man is None else man
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
        fails = receipts.validate_result(out, req0)
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
                              {req0["request_id"]: req0})
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
        print("identity-mismatch output:", proc.stdout.strip())
        say(proc.returncode == 2 and "location_id" in proc.stdout,
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
        say(receipts.validate_result(out, req0) == [],
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
        print("missing-block output:", proc.stdout.strip())
        say(proc.returncode == 2 and "native_bindings_ref" in proc.stdout,
            "missing native_bindings_ref block refused, naming the field")

    # Case 6: a claimed artifact absent on disk fails closed.
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td, with_artifact=False)
        proc = run(td)
        print("missing-artifact output:", proc.stdout.strip())
        say(proc.returncode == 2 and "thank-you-render.html"
            in proc.stdout,
            "absent claimed artifact refused, naming the artifact")

    # Case 7: a review recorded by the author session itself is
    # refused (an artifact's reviewer is never its author).
    with tempfile.TemporaryDirectory() as tds:
        td = Path(tds)
        stage(td)
        proc = run(td, author="SWARM")
        print("self-review output:", proc.stdout.strip())
        say(proc.returncode == 2 and "independent_review" in proc.stdout,
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
        out_path = stage(td, man=man)
        proc = run(td)
        print("no-envelope stdout:", proc.stdout.strip())
        say(proc.returncode == 0,
            f"no-envelope real manifest (envelope_ref null) translates "
            f"(got {proc.returncode}: {proc.stdout.strip()})")
        out = json.loads(out_path.read_text(encoding="utf-8"))
        say(out["native_bindings_ref"] is None,
            "no-envelope output carries envelope_ref null verbatim as "
            "native_bindings_ref")
        say(receipts.validate_result(out, req0) == [],
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
            f"{proc.returncode}: {proc.stdout.strip()})")
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
        say(receipts.validate_result(out11, req11) == [],
            "1.1 translation passes collect_launch_receipts."
            "validate_result against the 1.1 request with zero fails")
        cp = receipts.collect(manifest_for(req11), [out11],
                              {req11["request_id"]: req11})
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
    repo_root = HERE.parents[1]
    s82_scripts = repo_root / "82-signature-thank-you" / "scripts"
    sys.path.insert(0, str(s82_scripts))
    import run_manifest as s82_emitter  # noqa: E402
    view = json.loads((repo_root / "82-signature-thank-you" / "fixtures"
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
            (repo_root / "82-signature-thank-you" / "schemas"
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
            f"{proc.stdout.strip()})")
        if out_path.exists():
            out_real = json.loads(out_path.read_text(encoding="utf-8"))
            say(out_real["independent_review"] is True
                and out_real["reviewer_session"] == "SWARM",
                "real-manifest translation carries the manifest's "
                "recorded independent review")
            say(receipts.validate_result(out_real, req11) == [],
                "real-manifest translation passes validate_result "
                "with zero fails")
            cp = receipts.collect(manifest_for(req11), [out_real],
                                  {req11["request_id"]: req11})
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
        say(proc.returncode == 2 and "prompt_policy_id" in proc.stdout,
            f"1.1 source missing prompt_policy_id refused naming the "
            f"field (exit {proc.returncode}: {proc.stdout.strip()})")
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
        say(proc.returncode == 2 and "prompt_policy_id" in proc.stdout
            and "1.1" in proc.stdout,
            f"1.0 source carrying prompt_policy_id refused naming the "
            f"pair rule (exit {proc.returncode}: {proc.stdout.strip()})")
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
                and "prompt_policy_id" in proc.stdout,
                f"1.1 source with {label} prompt_policy_id refused "
                f"naming the field (exit {proc.returncode}: "
                f"{proc.stdout.strip()})")
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
                and "schema_version" in proc.stdout,
                f"echo source with schema_version {label} refused "
                f"naming the defect (exit {proc.returncode}: "
                f"{proc.stdout.strip()})")
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
            f"{proc.returncode}: {proc.stdout.strip()})")

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
                "registry_entry_hash":
                    "b3584da0c21b197c900fc1f47f0e4dcf722c6d74cd4d612441"
                    "8f8500a3c7285b"},
            "output_path": "thank-you-render.html",
            "prompt_artifact_path": "thank-you-render.html",
            "prompt_hash": artifact_sha,
            "independent_visual_qc": {"status": "pass"},
        }
        cp = receipts.collect(manifest_for(req11), [out11],
                              {req11["request_id"]: req11},
                              asset_receipts=[receipt],
                              registry=registry)
        closed = cp["prompt_items"]["closed"]
        say(not cp["problems"] and len(closed) == 1
            and closed[0]["prompt_policy_id"] == "kie-rule-12-band",
            f"Q11 prompt item for thank_you closes against the "
            f"registry of record with zero problems (got problems "
            f"{cp['problems']}, closed {closed})")

    print("TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
