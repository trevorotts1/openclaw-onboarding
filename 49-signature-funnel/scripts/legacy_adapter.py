#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""legacy_adapter.py — migrate a LEGACY locked brief into a launch-mode
DRAFT (spec 06 S49-10). Adapters, never silent edits: the legacy brief and
every historical run JSON stay byte-identical; this tool READS a legacy
brief and produces a NEW launch record plus a mapping report.

Three laws:
  1. A migrated brief is a draft for re-planning, status `collecting`.
     The legacy Q17 lock is NOT a launch plan approval — the report says
     so in plain words, plan_approval_ref is null, and the guided intake
     + approval gate must run before any build. Nothing here can mint an
     approved plan.
  2. Nothing is silently dropped. Legacy fields with no launch
     counterpart (above all q14_downsell2 — the launch profile has
     exactly one downsell) land in the report's `unmapped` list with the
     reason, for a human/scope decision.
  3. Facts keep their provenance: every adapted price/offer cites its
     legacy question as source_ref with source_kind owner (the client
     stated it in the legacy brief). A price that cannot be parsed is
     recorded unknown — never zero, never guessed.

Mapping: q1 main offer; q2 price (first $ amount); q5 deliverables;
q10/funnel_size -> extras (3: none, 5: U1+D1, 7: U1+D1+U2); q11/q12/q13
-> upsell_1/downsell_1/upsell_2 with prices parsed from their text;
offer_token_ledger supplies display names. Journey is single_simple —
a legacy brief describes one main offer; packages, if any existed, are a
re-plan question for the guided intake, never an inference here.

Deterministic, stdlib only. Exit 0 ok, 2 violation, 3 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_launch_route as clr  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

_PRICE_RE = re.compile(r"\$\s*([0-9][0-9,]*)(?:\.([0-9]{2}))?")


class AdapterError(ValueError):
    pass


def _parse_price_minor(text: Any) -> Optional[int]:
    if not isinstance(text, str):
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    dollars = int(m.group(1).replace(",", ""))
    cents = int(m.group(2)) if m.group(2) else 0
    return dollars * 100 + cents


def _split_list(text: Any) -> List[str]:
    if isinstance(text, list):
        return [str(x).strip() for x in text if str(x).strip()]
    if isinstance(text, str):
        return [p.strip() for p in text.split(",") if p.strip()]
    return []


def verify_legacy_brief(brief: Any) -> List[str]:
    fails = []
    if not isinstance(brief, dict):
        return ["legacy brief is not a JSON object"]
    if brief.get("locked") is not True:
        fails.append("legacy brief is not locked — an unlocked brief is "
                     "never adapted (finish or abandon the legacy intake)")
    if brief.get("funnel_size") not in (3, 5, 7):
        fails.append(f"funnel_size {brief.get('funnel_size')!r} is not 3, 5 or 7")
    if not isinstance(brief.get("answers"), dict):
        fails.append("legacy brief carries no answers object")
    return fails


def _offer(offer_id: str, slot: str, name: str, text: str, source_q: str,
           deliverables: Optional[List[str]] = None) -> Dict[str, Any]:
    amount = _parse_price_minor(text)
    return {"offer_id": offer_id, "slot": slot, "display_name": name,
            "deliverables": deliverables if deliverables is not None else [text],
            "exclusions": [], "entitlement_ids": [offer_id.lower()],
            "requires": [], "excludes": [], "native_product_id": None,
            "prices": [{"price_choice_id": f"{offer_id}-USD", "currency": "USD",
                        "amount_minor": amount, "billing_type": "one_time",
                        "native_price_id": None, "schedule": [],
                        "terms_source": None,
                        "approval_status": "provided" if amount is not None
                        else "unknown"}],
            "source_kind": "owner", "source_ref": f"legacy-brief:{source_q}",
            "test_only": False}


def adapt_legacy_brief(brief: Dict[str, Any], *, tenant_id: str,
                       location_id: str, launch_id: str,
                       test_only: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    fails = verify_legacy_brief(brief)
    if fails:
        raise AdapterError("; ".join(fails))
    a = brief["answers"]
    tokens = brief.get("offer_token_ledger") or []
    size = brief["funnel_size"]
    mapped: List[str] = []
    unmapped: List[Dict[str, str]] = []
    warnings: List[str] = []

    def token(i: int, fallback: str) -> str:
        return tokens[i] if len(tokens) > i else fallback

    offers: List[Dict[str, Any]] = []
    main_text = str(a.get("q1_offer", ""))
    main = _offer("MAIN", "main", token(0, "Main offer"), main_text, "q1_offer",
                  deliverables=_split_list(a.get("q5_goods")) or [main_text])
    price2 = _parse_price_minor(a.get("q2_price_promise"))
    if price2 is not None:
        main["prices"][0]["amount_minor"] = price2
        main["prices"][0]["approval_status"] = "provided"
        main["source_ref"] = "legacy-brief:q1_offer+q2_price_promise"
    elif main["prices"][0]["amount_minor"] is None:
        warnings.append("main price could not be parsed from q1/q2 — "
                        "recorded unknown, to be settled in guided intake")
    offers.append(main)
    mapped += ["q1_offer->offers.main", "q2_price_promise->offers.main.price",
               "q5_goods->offers.main.deliverables"]

    extras = {"upsell_1": size >= 5, "downsell_1": size >= 5,
              "upsell_2": size >= 7}
    slot_map = [("q11_oto1", "upsell_1", "U1", 1), ("q12_downsell1", "downsell_1", "D1", 2),
                ("q13_oto2", "upsell_2", "U2", 3)]
    for q, slot, oid, ti in slot_map:
        if not extras[slot]:
            continue
        text = str(a.get(q, ""))
        if not text:
            warnings.append(f"{q} empty but funnel_size {size} implies {slot} — "
                            "slot disabled in the draft; confirm in intake")
            extras[slot] = False
            continue
        offers.append(_offer(oid, slot, token(ti, oid), text, q))
        mapped.append(f"{q}->offers.{slot}")
    for o in offers:
        if o["slot"] == "upsell_1":
            o["excludes"] = ["D1"] if extras["downsell_1"] else []
        if o["slot"] == "downsell_1":
            o["excludes"] = ["U1"] if extras["upsell_1"] else []
    if a.get("q14_downsell2"):
        unmapped.append({"field": "q14_downsell2",
                         "reason": "the launch profile has exactly ONE downsell; "
                                   "a second downsell needs a scope decision — "
                                   "it is not folded into D1 and not dropped "
                                   "silently; the 7-step Signature Funnel "
                                   "(downsell-2) gets its wireframes and "
                                   "mockups from legacy_downsell_images.py"})
    for q in ("q3_pains", "q4_people", "q6_founder_story", "q7_brand_colors",
              "q8_representation", "q9_voice", "q15_reference_images",
              "q16_truth_gate"):
        if a.get(q):
            mapped.append(f"{q}->brand/copy context (carried in source_refs; "
                          "structured by the guided intake)")

    launch: Dict[str, Any] = {
        "schema_version": "1.0", "tenant_id": tenant_id,
        "location_id": location_id, "launch_id": launch_id, "revision": 1,
        "journey_mode": "single_simple", "status": "collecting",
        "brand_ref": "legacy-brief-brand",
        "brand_hash": hashlib.sha256(json.dumps(
            a, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "route_graph_ref": "", "route_graph_hash": "",
        "plan_approval_ref": None, "offers": offers, "extras": extras,
        "bump_enabled": False, "image_provider": "other_explicit",
        "source_refs": ["legacy-brief:adapted-by-legacy_adapter.py"],
        "test_only": test_only,
    }
    for o in launch["offers"]:
        o["test_only"] = test_only
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = f"route-graph:{launch_id}:rev1"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    report = {
        "adapter": "legacy_adapter.py/v1",
        "source": "legacy locked brief (signature_funnel)",
        "mapped": mapped, "unmapped": unmapped, "warnings": warnings,
        "plan_approval": "NONE — the legacy Q17 lock is not a launch plan "
                         "approval. This draft is status collecting: run the "
                         "guided intake and the approval gate before any build.",
        "journey_note": "single_simple assumed (one main offer in the legacy "
                        "brief); packages are a re-plan question, not an "
                        "inference.",
    }
    return launch, report


GOLDEN_BRIEF = {
    "funnel_type": "signature_funnel", "one_question_per_turn": True,
    "locked": True, "funnel_size": 7,
    "answers": {
        "q1_offer": "The Daybreak Method — a 30-day morning-discipline course",
        "q2_price_promise": "$149; calm, owned mornings and a first deep-work block within 30 days",
        "q3_pains": "waking already behind; a privately broken promise to rise; kids learning the snooze",
        "q4_people": "founders, parents, creators, and leaders who want calm and output",
        "q5_goods": "30 daily audio rituals, 4 live calls, a tracker, a private community, a founder text",
        "q6_founder_story": "burned out and always behind; decided one gray dawn; built it for tired builders",
        "q7_brand_colors": "deep indigo and warm sunrise amber",
        "q8_representation": "60% Black women, 20% Black men, 15% mixed, 5% other",
        "q9_voice": "bold, warm, plainspoken, street-smart",
        "q10_funnel_length": "7-step",
        "q11_oto1": "The Fast Track Sprint, done-with-you accelerated onboarding, $197, 40 seats",
        "q12_downsell1": "The Daybreak Field Notes, recordings-only tier, $47",
        "q13_oto2": "The Founders Table Retreat, categorically different in-person weekend, $997, 20 seats",
        "q14_downsell2": "The Single Day Pass, one retreat day, $297",
        "q15_reference_images": "signature only",
        "q16_truth_gate": {"community_url": "https://community.example.com/daybreak",
                           "bonus": "the five-minute morning reset audio",
                           "founder_text_confirmed": True},
        "q17_confirmation": "approved"},
    "offer_token_ledger": ["The Daybreak Method", "The Fast Track Sprint",
                           "The Daybreak Field Notes", "The Founders Table Retreat",
                           "The Single Day Pass"]}


def _self_test() -> int:
    ok = True

    def say(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    launch, report = adapt_legacy_brief(GOLDEN_BRIEF, tenant_id="T",
                                        location_id="L", launch_id="DB",
                                        test_only=True)
    say(launch["status"] == "collecting" and launch["plan_approval_ref"] is None,
        "adapted brief is a collecting draft with NO plan approval")
    prices = {o["offer_id"]: o["prices"][0]["amount_minor"]
              for o in launch["offers"]}
    say(prices == {"MAIN": 14900, "U1": 19700, "D1": 4700, "U2": 99700},
        f"legacy prices parsed to minor units exactly ({prices})")
    say(launch["extras"] == {"upsell_1": True, "downsell_1": True,
                             "upsell_2": True},
        "7-step brief maps to U1+D1+U2 enabled")
    say(any(u["field"] == "q14_downsell2" for u in report["unmapped"]),
        "D2 is reported unmapped with its reason — never silently dropped")
    say(vlp.validate_launch(launch) == [],
        "adapted draft passes the plan validator at collecting status")
    say(all(o["source_kind"] == "owner" for o in launch["offers"]),
        "adapted facts keep owner provenance with legacy-question source refs")
    try:
        adapt_legacy_brief(dict(GOLDEN_BRIEF, locked=False), tenant_id="T",
                           location_id="L", launch_id="DB")
        say(False, "unlocked brief must be refused")
    except AdapterError:
        say(True, "unlocked legacy brief is refused, never adapted")
    small = json.loads(json.dumps(GOLDEN_BRIEF))
    small["funnel_size"] = 3
    l3, _ = adapt_legacy_brief(small, tenant_id="T", location_id="L",
                               launch_id="DB3", test_only=True)
    say(l3["extras"] == {"upsell_1": False, "downsell_1": False,
                         "upsell_2": False} and len(l3["offers"]) == 1,
        "3-step brief maps to a main-only draft")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Adapt a legacy locked brief "
                                             "into a launch-mode draft.")
    ap.add_argument("--brief"); ap.add_argument("--tenant")
    ap.add_argument("--location"); ap.add_argument("--launch")
    ap.add_argument("--out"); ap.add_argument("--report-out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not (args.brief and args.tenant and args.launch and args.out):
        print("USAGE ERROR: --brief --tenant --launch --out are required.")
        return EXIT_FAILCLOSED
    try:
        brief = json.loads(Path(args.brief).read_text(encoding="utf-8"))
        launch, report = adapt_legacy_brief(
            brief, tenant_id=args.tenant, location_id=args.location or "",
            launch_id=args.launch)
    except (AdapterError, OSError, ValueError, clr.RouteError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_VIOLATION
    Path(args.out).write_text(json.dumps(launch, indent=2) + "\n",
                              encoding="utf-8")
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    print(json.dumps({"draft": args.out, "status": launch["status"],
                      "unmapped": [u["field"] for u in report["unmapped"]]},
                     indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
