#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_launch_plan.py — checklist L1: Skill 49's launch plan includes pages +
emails + texts + automations + the AI choice, and every plan it emits validates
against the shared launch-plan contract.

Run as a script (`python3 49-signature-funnel/scripts/test_launch_plan.py`, exit 0 = all checks pass, 1 = at
least one failed) or under pytest / unittest, where every check is a real assertion: a failing check raises
AssertionError, so the run fails (issue 70).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import launch_intake  # noqa: E402
import launch_plan  # noqa: E402

CONTRACT = ROOT / "shared-utils" / "signature_launch_contract"
REGISTRY = ROOT / "50-email-engine" / "profiles" / "launch-email-families.json"


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
    if not good:
        raise AssertionError(msg)


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


def must(good: bool, msg: str) -> None:
    """say() plus a hard assert, so the check also fails under pytest (say() only records)."""
    say(good, msg)
    assert good, msg


def _registry_counts():
    """kind -> email_count straight from Skill 50's registry file, read independently of the planner."""
    families = json.loads(REGISTRY.read_text(encoding="utf-8"))["families"]
    return {f["kind"]: f["email_count"] for f in families}


def test_email_counts_come_from_skill_50() -> None:
    """Issue 58 (D-A): every planned sequence carries the count Skill 50's registry fixes,
    with no Black Friday special case, so Skill 50's adapter never refuses the plan."""
    expected = _registry_counts()
    must(launch_plan.email_counts() == {k: expected[k] for k in launch_plan.email_counts()}
        and set(launch_plan.PLANNED_EMAIL_KINDS) <= set(expected),
        "email_counts() is the registry's own kind -> email_count table")
    bf = dict(ANSWERS, **{
        "launch.launch_at": "2026-11-27T00:00:00-05:00",
        "launch.doors_open_at": "2026-11-27T00:00:00-05:00",
        "launch.doors_close_at": "2026-12-01T00:00:00-05:00",
        "launch.black_friday.teaser_at": "2026-11-20T09:00:00-05:00",
        "launch.black_friday.countdown_at": "2026-11-24T09:00:00-05:00",
        "launch.black_friday.cyber_monday_at": "2026-11-30T00:00:00-05:00",
        "launch.black_friday.last_call_at": "2026-11-30T20:00:00-05:00"})
    for label, answers in (("plain launch", ANSWERS), ("Black Friday launch", bf)):
        plan = launch_plan.build_launch_plan(_launch(), answers)["plan"]
        wrong = [(e["id"], e["email_count"], expected[e["kind"]]) for e in plan["email_sequences"]
                 if e["email_count"] != expected[e["kind"]]]
        must(not wrong, f"{label}: each sequence's email_count equals Skill 50's registry row"
            + ("" if not wrong else f" - disagree: {wrong}"))
    plain = launch_plan.build_launch_plan(_launch(), ANSWERS)["plan"]
    kinds = {e["kind"] for e in plain["email_sequences"]}
    must(kinds == set(launch_plan.PLANNED_EMAIL_KINDS),
        "the plan plans exactly the seven registry families (no kind without a registry row)")


def test_missing_or_broken_registry_refuses() -> None:
    """Issue 58: no registry, no default. Every defect is the named refusal, never a number."""
    families = json.loads(REGISTRY.read_text(encoding="utf-8"))["families"]
    broken = {
        "absent file": None,
        "not JSON": "{nope",
        "no families array": json.dumps({"families": "x"}),
        "a planned kind has no row": json.dumps(
            {"families": [f for f in families if f["kind"] != "upsell_followup"]}),
        "boolean count": json.dumps(
            {"families": [dict(f, email_count=True) if f["kind"] == "pre_launch" else f
                          for f in families]}),
        "zero count": json.dumps(
            {"families": [dict(f, email_count=0) if f["kind"] == "pre_launch" else f
                          for f in families]}),
        "duplicate kind": json.dumps({"families": families + [families[0]]}),
    }
    with tempfile.TemporaryDirectory() as tmp:
        for label, body in broken.items():
            path = Path(tmp) / "registry.json"
            path.unlink(missing_ok=True)
            if body is not None:
                path.write_text(body, encoding="utf-8")
            try:
                launch_plan.email_counts(path)
                must(False, f"a registry with {label} is refused")
            except launch_plan.LaunchPlanError as exc:
                must(launch_plan.EMAIL_REGISTRY_CODE in str(exc),
                    f"a registry with {label} is refused as {launch_plan.EMAIL_REGISTRY_CODE}")
        # the planner itself stops, it does not fall back to a number of its own
        saved = launch_plan.EMAIL_REGISTRY
        launch_plan.EMAIL_REGISTRY = Path(tmp) / "gone.json"
        try:
            launch_plan.build_launch_plan(_launch(), ANSWERS)
            must(False, "build_launch_plan with no registry is refused")
        except launch_plan.LaunchPlanError as exc:
            must(launch_plan.EMAIL_REGISTRY_CODE in str(exc),
                "build_launch_plan with no registry is refused, not defaulted")
        finally:
            launch_plan.EMAIL_REGISTRY = saved


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
        "launch.launch_at": "2026-11-27T00:00:00-05:00",
        "launch.doors_open_at": "2026-11-27T00:00:00-05:00",
        "launch.doors_close_at": "2026-12-01T00:00:00-05:00",
        "launch.black_friday.teaser_at": "2026-11-20T09:00:00-05:00",
        "launch.black_friday.countdown_at": "2026-11-24T09:00:00-05:00",
        "launch.black_friday.cyber_monday_at": "2026-11-30T00:00:00-05:00",
        "launch.black_friday.last_call_at": "2026-11-30T20:00:00-05:00"})
    plan = launch_plan.build_launch_plan(_launch(), bf)["plan"]
    check_contract(plan)
    say("black_friday" in plan["launch_calendar"],
        "Black Friday timing is carried when the calendar supplies it (Skill 83's calendar)")


SHARED_REFUSAL = "payment plans are not supported in this release"  # billing.py, the sentence Skill 83's intake says


def test_installment_and_trial_are_refused_at_plan_time() -> None:
    """D-D (issue 70): the client hears it when the plan is built, before approval, not at checkout."""
    for billing in ("installment", "trial"):
        launch = _launch()
        launch["offers"][0]["prices"][0].update(billing_type=billing, schedule=[{"amount_minor": 49700, "due": "today"}])
        result = launch_plan.build_launch_plan(launch, ANSWERS)
        say(result["state"] == "awaiting_missing_fact" and result["plan"] is None,
            f"a {billing} main price blocks the launch plan")
        say(any(SHARED_REFUSAL in m and repr(billing) in m for m in result["missing"]),
            f"the {billing} refusal carries the shared sentence ({SHARED_REFUSAL!r})")
    answered = launch_plan.build_launch_plan(_launch(), dict(ANSWERS, **{"offers.main.billing_type": "installment"}))
    say(answered["state"] == "awaiting_missing_fact" and any(SHARED_REFUSAL in m for m in answered["missing"]),
        "an installment billing ANSWER is refused at plan time too")
    for billing in ("one_time", "recurring"):
        launch = _launch()
        launch["offers"][0]["prices"][0]["billing_type"] = billing
        launch["offers"][0]["prices"][0]["schedule"] = [{"amount_minor": 49700, "due": "today"}]
        say(launch_plan.build_launch_plan(launch, ANSWERS)["state"] == "ready",
            f"a {billing} price is not refused at plan time")
    shared = sys.modules["signature_launch_billing"]
    say(shared.PAYMENT_PLANS_UNSUPPORTED == SHARED_REFUSAL and shared.plan_time_refusal("installment")
        and shared.plan_time_refusal("one_time") is None,
        "the plan-time refusal is the shared billing module's, not a local copy")


def test_without_the_shared_billing_file_the_plan_fails_closed() -> None:
    """No vocabulary installed means the plan's billing types cannot be judged: refused by name, never passed."""
    from unittest import mock
    with mock.patch.object(launch_plan, "_BILLING", HERE / "absent-billing.py"), mock.patch.dict(sys.modules):
        sys.modules.pop("signature_launch_billing", None)
        try:
            launch_plan.build_launch_plan(_launch(), ANSWERS)
        except launch_plan.LaunchPlanError as exc:
            say("not installed" in str(exc), "a missing billing.py is a named LaunchPlanError")
        else:
            say(False, "a missing billing.py must stop the plan")


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


CHECKS = (test_full_plan, test_email_counts_come_from_skill_50, test_missing_or_broken_registry_refuses,
          test_missing_facts, test_choices,
          test_installment_and_trial_are_refused_at_plan_time,
          test_without_the_shared_billing_file_the_plan_fails_closed, test_intake_integration)


class LaunchPlanTests(unittest.TestCase):
    """The same checks for unittest discovery (module-level test_* functions are what pytest collects)."""

    def test_every_check_holds(self):
        for check in CHECKS:
            with self.subTest(check=check.__name__):
                check()


def main() -> int:
    for check in CHECKS:
        try:
            check()
        except AssertionError:
            pass  # say() already printed the FAIL line and cleared _ok
    print("RESULT:", "PASS" if _ok else "FAIL")
    return 0 if _ok else 1


if __name__ == "__main__":
    sys.exit(main())
