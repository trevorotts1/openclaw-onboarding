#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture-level tests for the S49 product_selection dispatch seam.

Cases:
  A  End-to-end happy path through the shipped config's product_selection
     entry, exactly as dispatch invokes an adapter: since the config
     retirement re-point the entry is Skill 78's native emitter chain
     (REAL plan builder + REAL emitter from the Skill 78 tree on main),
     driven with the S78 golden-three-option launch record. The emitted
     page-result must pass collect_launch_receipts' validate_result
     against the request (S49's own receipt path) and the packet
     page-result 1.0 JSON schema.
  A2 The same shipped entry accepted through
     dispatch_launch.executor_from_config, the real dispatch adapter seam.
  B  checkout_targets enrichment from S79's DELIVERED rows verbatim
     (SBX-PREMIUM / SBX-ESSENTIAL native IDs of record), unit level.
  C  Fail-closed: a mappings input missing one offer names that offer
     (MAIN-ELITE via CLI; SBX-ESSENTIAL via the enrichment unit).
  D  Fail-closed: a tampered emitter (tests/fixtures/tampered_emitter.py,
     a stub standing in for a misbehaving consumer) whose request_id is
     not the request's is refused and leaves no result file.

Requests are built with dispatch_launch's own request_input_hash and
dispatch_key so request_id/input_hash are genuine dispatch values.
Fixture level only: no network, no live launch (Skill 78 SKILL.md: do
not route live launches here yet).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE
S49_SCRIPTS = HERE
PACKET_SCHEMAS = HERE / "vendor"
S78_DIR = HERE.parents[1] / "78-signature-product-selection"
GOLDEN = S78_DIR / "fixtures" / "golden-three-option" / "launch.json"
GOLDEN_REC = S78_DIR / "fixtures" / "golden-three-option" / "recommendation.json"
SBX_LAUNCH = HERE / "fixtures" / "finalized-launch-record-signature-launch-l4.json"
SBX_MAPPINGS = HERE / "fixtures" / "mappings-sbx-verbatim.json"
WRAPPER = STAGE / "selection_wrapper.py"
CONFIG = HERE.parent / "launch-adapters.example.json"
LAUNCH_SLOT = "<per-launch: approved launch record JSON>"

sys.path.insert(0, str(S49_SCRIPTS))
sys.path.insert(0, str(STAGE))
import dispatch_launch as dl          # noqa: E402
import collect_launch_receipts as rc  # noqa: E402
import selection_wrapper as sw        # noqa: E402

RESULTS = []


def say(name, good, detail=""):
    RESULTS.append((name, good, detail))
    print(f"[{'PASS' if good else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def make_request(launch, offer_refs, page_id):
    ih = dl.request_input_hash(launch, page_id, "product_selection")
    return {
        "schema_version": "1.0",
        "tenant_id": launch["tenant_id"],
        "location_id": launch["location_id"],
        "launch_id": launch["launch_id"],
        "revision": launch["revision"],
        "request_id": dl.dispatch_key(launch, "product_selection", ih),
        "page_id": page_id,
        "page_role": "product_selection",
        "assigned_skill": 78,
        "approval_ref": launch["plan_approval_ref"],
        "input_hash": ih,
        "brand_ref": launch["brand_ref"],
        "brand_hash": launch["brand_hash"],
        "route_graph_ref": launch["route_graph_ref"],
        "route_graph_hash": launch["route_graph_hash"],
        "offer_refs": offer_refs,
        "copy_profile": "standard",
        "allowed_write_target": "local_only",
        "test_only": bool(launch["test_only"]),
    }


def run_cli(req_path, res_path, work_dir, launch, mappings, extra=()):
    argv = [sys.executable, str(WRAPPER),
            "--request", str(req_path), "--result", str(res_path),
            "--work-dir", str(work_dir), "--launch", str(launch),
            "--mappings", str(mappings), "--s78-dir", str(S78_DIR),
            "--author-session", "s49-08-test-author"] + list(extra)
    return subprocess.run(argv, capture_output=True, text=True, timeout=600)


def shipped_selection_entry(launch_path):
    """The shipped config's product_selection entry, with the example
    /path/to prefix and the per-launch launch-record slot substituted
    for this tree (the same substitutions deployment makes)."""
    config = json.loads(CONFIG.read_text())
    spec = config["adapters"]["product_selection"]
    root = str(HERE.parents[1])
    command = [part.replace("/path/to", root).replace(LAUNCH_SLOT, str(launch_path))
               for part in spec["command"]]
    return {"command": command, "timeout_s": spec.get("timeout_s", 600)}


def case_a(tmp):
    # Config retirement re-point (S49 config retirement candidate):
    # case A/A2 previously drove the S49 echo-correcting wrapper CLI.
    # Skill 78's native emitter fix landed in PR #2232, the wrapper
    # retired as the seam mechanism (S49 retirement record,
    # 2026-10-17), and the shipped config's product_selection entry now
    # names the native emitter chain, so case A/A2 drive that shipped
    # entry exactly as dispatch does. Cases B, C and D are unchanged:
    # the checkout_targets enrichment library and the wrapper CLI
    # remain shipped, and C/D still exercise them.
    launch = json.loads(GOLDEN.read_text())
    mains = [o["offer_id"] for o in launch["offers"] if o["slot"] == "main"]
    req = make_request(launch, mains, "TEST-LAUNCH-S78-GOLDEN-SELECTION")
    work = tmp / "a"; work.mkdir()
    req_p, res_p = work / "request-product_selection.json", work / "result-product_selection.json"
    req_p.write_text(json.dumps(req, indent=2) + "\n")
    entry = shipped_selection_entry(GOLDEN)
    argv = [part.replace("{request}", str(req_p)).replace("{result}", str(res_p))
            .replace("{work_dir}", str(work)) for part in entry["command"]]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    say("A native adapter command exits 0", proc.returncode == 0, proc.stderr.strip()[:300])
    if proc.returncode != 0:
        return
    res = json.loads(res_p.read_text())
    say("A result has exactly the 17 page-result fields",
        sorted(res.keys()) == sorted(sw.PAGE_RESULT_FIELDS),
        f"{len(res)} fields")
    say("A outcome field is not emitted", "outcome" not in res)
    say("A page_id echoed from the request", res["page_id"] == req["page_id"],
        f"native emitter echoes the request, result carries {res['page_id']!r}")
    say("A input_hash echoed from the request", res["input_hash"] == req["input_hash"])
    fails = rc.validate_result(res, req)
    say("A collect_launch_receipts.validate_result passes", fails == [], "; ".join(fails))
    try:
        import jsonschema
        schema = json.loads((PACKET_SCHEMAS / "page-result.schema.json").read_text())
        jsonschema.validate(res, schema)
        say("A packet page-result 1.0 JSON schema passes", True)
    except Exception as exc:  # jsonschema present in this env; report honestly
        say("A packet page-result 1.0 JSON schema passes", False, str(exc)[:200])
    plan = json.loads((work / "selection-plan.json").read_text())
    say("A real plan builder ran (plan outcome 'plan')", plan.get("outcome") == "plan")
    # The retired wrapper's enriched-selection-request artifact check
    # is gone with the wrapper's seam role: the native chain produces
    # no such artifact. checkout_targets enrichment correctness stays
    # covered by cases B and C against the shipped enrichment library.
    say("A proof is honest L1, no independent review claimed",
        res["proof_class"] == "L1" and res["independent_review"] is False
        and res["reviewer_session"] is None and res["status"] == "locally_verified")
    # Case A2: the real dispatch adapter seam accepts the shipped entry.
    cfg = {"adapters": {"product_selection": shipped_selection_entry(GOLDEN)}}
    executor = dl.executor_from_config(cfg, work)
    try:
        out = executor(req)
        say("A2 dispatch executor_from_config accepts the shipped entry result",
            out["request_id"] == req["request_id"])
    except Exception as exc:
        say("A2 dispatch executor_from_config accepts the shipped entry result", False, str(exc)[:300])


def case_b():
    launch = json.loads(SBX_LAUNCH.read_text())
    rows = sw.normalize_mapping_rows(json.loads(SBX_MAPPINGS.read_text()))
    targets = sw.enrich_checkout_targets(launch, ["SBX-PREMIUM", "SBX-ESSENTIAL"], rows)
    by_offer = {t["offer_id"]: t for t in targets}
    p, e = by_offer.get("SBX-PREMIUM", {}), by_offer.get("SBX-ESSENTIAL", {})
    say("B SBX-PREMIUM target carries S79's delivered native IDs",
        (p.get("native_product_id"), p.get("native_price_id"), p.get("price_choice_id"))
        == ("6ad22f138fd7561e0dc3f999", "6ad22f13094896d5b89e9881", "SBX-PREMIUM-USD"),
        f"{p.get('native_product_id')}/{p.get('native_price_id')}")
    say("B SBX-ESSENTIAL target carries S79's delivered native IDs",
        (e.get("native_product_id"), e.get("native_price_id"), e.get("price_choice_id"))
        == ("6ad22f13fcbbf97d90c8767c", "6ad22f13fcbbf97d90c87689", "SBX-ESSENTIAL-USD"),
        f"{e.get('native_product_id')}/{e.get('native_price_id')}")


def case_c(tmp):
    launch = json.loads(GOLDEN.read_text())
    mains = [o["offer_id"] for o in launch["offers"] if o["slot"] == "main"]
    req = make_request(launch, mains, "TEST-LAUNCH-S78-GOLDEN-SELECTION")
    work = tmp / "c"; work.mkdir()
    req_p, res_p = work / "request-product_selection.json", work / "result-product_selection.json"
    req_p.write_text(json.dumps(req, indent=2) + "\n")
    proc = run_cli(req_p, res_p, work, GOLDEN, HERE / "fixtures" / "mappings-golden-missing-elite.json")
    say("C wrapper fails closed on missing MAIN-ELITE mapping",
        proc.returncode == 3 and "MAIN-ELITE" in proc.stderr and not res_p.exists(),
        proc.stderr.strip()[:200])
    sbx = json.loads(SBX_LAUNCH.read_text())
    rows = sw.normalize_mapping_rows(json.loads(
        (HERE / "fixtures" / "mappings-sbx-missing-essential.json").read_text()))
    try:
        sw.enrich_checkout_targets(sbx, ["SBX-PREMIUM", "SBX-ESSENTIAL"], rows)
        say("C enrichment fails closed naming SBX-ESSENTIAL", False, "no error raised")
    except sw.WrapperError as exc:
        say("C enrichment fails closed naming SBX-ESSENTIAL",
            "SBX-ESSENTIAL" in str(exc), str(exc)[:200])


def case_d(tmp):
    launch = json.loads(GOLDEN.read_text())
    mains = [o["offer_id"] for o in launch["offers"] if o["slot"] == "main"]
    req = make_request(launch, mains, "TEST-LAUNCH-S78-GOLDEN-SELECTION")
    work = tmp / "d"; work.mkdir()
    req_p, res_p = work / "request-product_selection.json", work / "result-product_selection.json"
    req_p.write_text(json.dumps(req, indent=2) + "\n")
    proc = run_cli(req_p, res_p, work, GOLDEN, HERE / "fixtures" / "mappings-golden.json",
                   extra=("--emitter", str(HERE / "fixtures" / "tampered_emitter.py")))
    say("D tampered emitter request_id is refused, no result file",
        proc.returncode == 3 and "FORGED-REQUEST-ID" in proc.stderr and not res_p.exists(),
        proc.stderr.strip()[:200])


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        case_a(tmp)
        case_b()
        case_c(tmp)
        case_d(tmp)
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
