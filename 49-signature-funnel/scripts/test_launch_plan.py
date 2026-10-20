#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_launch_plan.py — checklist L1: Skill 49's launch plan includes pages +
emails + texts + automations + the AI choice, and every plan it emits validates
against the shared launch-plan contract.

Run from anywhere: `python3 49-signature-funnel/scripts/test_launch_plan.py`
Exit 0 = all checks pass; 1 = at least one failed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import launch_intake  # noqa: E402
import launch_plan  # noqa: E402

CONTRACT = ROOT / "shared-utils" / "signature_launch_contract"


def _load_contract_validator():
    """The contract validator by file path: 49 has its own same-named module on sys.path."""
    spec = importlib.util.spec_from_file_location(
        "contract_validate_launch_plan", CONTRACT / "validate_launch_plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA = json.loads((CONTRACT / "launch-plan.schema.json").read_text(encoding="utf-8"))
VALIDATOR = _load_contract_validator()

_ok = True


def say(good: bool, msg: str) -> None:
    global _ok
    _ok = _ok and bool(good)
    print(f"TEST {'ok' if good else 'FAIL'}: {msg}")


def _launch(**over):
    launch = {
        "launch_id": "demo-2026-11", "journey_mode": "single_simple",
        "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": False},
        "offers": [
            {"slot": "main", "display_name": "Demo Offer",
             "prices": [{"amount_minor": 49700, "currency": "USD"}]},
            {"slot": "upsell_1", "display_name": "Demo Upgrade",
             "prices": [{"amount_minor": 9900, "currency": "USD"}]},
            {"slot": "downsell_1", "display_name": "Smaller Demo",
             "prices": [{"amount_minor": 4900, "currency": "USD"}]},
        ],
    }
    launch.update(over)
    return launch


ANSWERS = {
    "launch.launch_at": "2026-11-03T12:00:00-05:00",
    "launch.doors_open_at": "2026-11-03T09:00:00-05:00",
    "launch.doors_close_at": "2026-11-10T23:59:00-05:00",
    "launch.timezone": "America/New_York",
    "launch.channels": ["email", "text"],
    "launch.a2p_ready": False,
    "launch.conversation_ai": False,
    "launch.landing_url": "https://example.com/landing",
    "launch.sales_page_url": "https://example.com/sales",
    "launch.checkout_url": "https://example.com/order",
    "launch.thank_you_url": "https://example.com/thanks",
}


def check_contract(plan) -> None:
    errors = VALIDATOR.validate_plan(plan, SCHEMA)
    say(not errors, "the plan validates against the shared launch-plan contract"
        + ("" if not errors else f" — {errors}"))


def test_full_plan() -> None:
    result = launch_plan.build_launch_plan(_launch(), ANSWERS)
    say(result["state"] == "ready", "a complete launch plan assembles")
    plan = result["plan"]
    check_contract(plan)
    say([p["kind"] for p in plan["pages"]].count("upsell") == 1,
        "the pages are the launch's real pages (with the upsell)")
    say({e["kind"] for e in plan["email_sequences"]} >=
        {"pre_launch", "main_launch", "doors_closing", "upsell_followup",
         "downsell_followup", "abandoned_checkout", "welcome_access"},
        "every spec §3.1 email family is planned")
    say(all(t["draft_only"] and t["opt_out_keyword"] == "STOP"
            and t["includes_reply_invitation"] for t in plan["text_sets"]),
        "every text is a draft with a reply invitation and STOP")
    say(sum(1 for t in plan["text_sets"] if t["promotional"]) <= 5,
        "promotional text sets stay within the cap of 5")
    say(plan["a2p_ready"] is False and plan["text_sets"],
        "A2P not ready: texts are still planned as drafts (the package warns)")
    say(any(a["family"] == "conversation_ai_reply" for a in plan["automations"]) is False,
        "no AI reply workflow when the AI choice is no")
    say(not any(a["family"] == "failed_payment" for a in plan["automations"]),
        "no failed-payment automation when the offer has no payment plans")
    say(all(a["build_rail"] == "skill44_engine" for a in plan["automations"]),
        "automations carry the U-GHL-PROBE answer (Skill 44 engine) and are drafts")


def test_missing_facts() -> None:
    answers = {k: v for k, v in ANSWERS.items() if not k.startswith("launch.launch")}
    result = launch_plan.build_launch_plan(_launch(), answers)
    say(result["state"] == "awaiting_missing_fact",
        "missing launch calendar facts block the plan")
    say(any("launch_at" in m for m in result["missing"]),
        "the missing launch date is named, never invented")
    ai = dict(ANSWERS, **{"launch.conversation_ai": True})
    result = launch_plan.build_launch_plan(_launch(), ai)
    say(result["state"] == "awaiting_missing_fact",
        "requested Conversation AI without a mode blocks the plan")


def test_choices() -> None:
    email_only = dict(ANSWERS, **{"launch.channels": ["email"]})
    plan = launch_plan.build_launch_plan(_launch(), email_only)["plan"]
    check_contract(plan)
    say(plan["text_sets"] == [], "email-only launch plans no texts")

    ai = dict(ANSWERS, **{
        "launch.conversation_ai": True, "launch.conversation_ai_mode": "booking",
        "launch.conversation_ai_channels": ["sms", "chat"],
        "offers.main.payment_plans": True})
    plan = launch_plan.build_launch_plan(_launch(), ai)["plan"]
    check_contract(plan)
    say(plan["conversation_ai"]["requested"] and
        plan["conversation_ai"]["mode"] == "booking",
        "the AI choice and mode are carried")
    say(any(a["family"] == "conversation_ai_reply" for a in plan["automations"]),
        "a requested AI adds the reply workflow")
    say(any(a["family"] == "failed_payment" for a in plan["automations"]),
        "payment plans add the failed-payment automation")

    bf = dict(ANSWERS, **{
        "launch.black_friday.teaser_at": "2026-11-20T09:00:00-05:00",
        "launch.black_friday.countdown_at": "2026-11-24T09:00:00-05:00",
        "launch.black_friday.cyber_monday_at": "2026-11-30T00:00:00-05:00",
        "launch.black_friday.last_call_at": "2026-11-30T20:00:00-05:00"})
    plan = launch_plan.build_launch_plan(_launch(), bf)["plan"]
    check_contract(plan)
    say("black_friday" in plan["launch_calendar"],
        "Black Friday timing is carried when the calendar supplies it (Skill 83's calendar)")


def test_intake_integration() -> None:
    known = {
        "offers.main.description": "Sunrise Coaching",
        "offers.main.deliverables": ["6 sessions"],
        "offers.main.price": {"amount_minor": 49700, "currency": "USD"},
        "journey_mode": "single_simple",
        "extras": {"upsell_1": False, "downsell_1": False, "upsell_2": False},
        "image_provider": "agnes",
    }
    for key, value in ANSWERS.items():
        known[key] = value
    session = launch_intake.new_session(
        tenant_id="T", location_id="L", launch_id="demo-2026-11",
        client_identity_ref="client-1", known=known, brand_ref="brand-1",
        brand_hash="bh-1", test_only=True)
    choices = {"c1_bump": "No add-on", "c2_u1": "No upgrade",
               "d1_brand": "All saved already", "d2_copy_profile": "Standard",
               "d3_location": "Yes, my existing account"}
    while True:
        q = launch_intake.next_question(session)
        if q is None:
            break
        launch_intake.answer(session, q["id"], choices.get(q["id"], "n/a"))
    result = launch_intake.assemble_plan(session)
    say(result["state"] in ("awaiting_plan_approval", "recommendation_ready"),
        "the page plan still assembles with the full launch plan beside it")
    plan = session.get("launch_plan")
    say(plan is not None, "assemble_plan attaches the full launch plan")
    if plan:
        check_contract(plan)
    summary = launch_intake.render_summary(session)
    say("email sequences" in summary and "automations" in summary,
        "the plan the client approves names the emails and automations")
    say("Conversation AI: not requested" in summary,
        "the plan the client approves records the AI choice")


def main() -> int:
    test_full_plan()
    test_missing_facts()
    test_choices()
    test_intake_integration()
    print("RESULT:", "PASS" if _ok else "FAIL")
    return 0 if _ok else 1


if __name__ == "__main__":
    sys.exit(main())
