#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture tests for translate_thank_you_result.py (S49-08, CR-S49-004
Path B). Each case stages the three inputs in a temp dir, runs the
translator as a subprocess exactly as a dispatch adapter would, and
checks exit codes, refusal messages and the emitted page-result.

The happy-path page-result is validated three ways: exact 17-field set,
real JSON Schema validation against the packet page-result 1.0 schema,
and collect_launch_receipts' own validate_result + collect rollup.

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

    print("TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
