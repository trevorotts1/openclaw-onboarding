#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_launch_plan_offer_event.py — synthetic-local regression for lane L02.

Covers audit units UL-005 / UL-013 / UL-031 (planner part):
  * every package keeps offer id, price id, minor units, currency, billing
    type/schedule and provenance — no lowest-price collapse;
  * an unknown price is a missing fact and is never zero; a zero price is real
    only on the supported free route (journey_mode free_entry, approved price);
  * installments/trials keep exact terms or are rejected as unsupported;
  * event eligibility is explicit from approved facts — a self-paced product
    plans no webinar/reminder/replay/no-show units, and the event start is a
    separate fact from the sale opening;
  * the welcome/access actions resolve an approved destination plus every
    purchased entitlement and its prerequisites;
  * founder identity is never inferred.

Synthetic fixtures only: no network, no provider, no live send, no purchase.
Run from anywhere: `python3 49-signature-funnel/scripts/test_launch_plan_offer_event.py`
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

import launch_plan  # noqa: E402

CONTRACT = ROOT / "shared-utils" / "signature_launch_contract"


def _validator():
    spec = importlib.util.spec_from_file_location(
        "contract_validate_launch_plan_l02", CONTRACT / "validate_launch_plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA = json.loads((CONTRACT / "launch-plan.schema.json").read_text(encoding="utf-8"))
VALIDATOR = _validator()

_ok = True


def say(good: bool, msg: str) -> None:
    global _ok
    _ok = _ok and bool(good)
    print(f"TEST {'ok' if good else 'FAIL'}: {msg}")


def _price(price_id: str, amount, currency="USD", billing="one_time",
           schedule=None, status="provided") -> dict:
    return {"price_choice_id": price_id, "currency": currency,
            "amount_minor": amount, "billing_type": billing,
            "native_price_id": None, "schedule": list(schedule or []),
            "terms_source": None, "approval_status": status}


def _offer(offer_id, slot, name, price, entitlements=(), requires=()) -> dict:
    return {"offer_id": offer_id, "slot": slot, "display_name": name,
            "deliverables": [], "exclusions": [],
            "entitlement_ids": list(entitlements), "requires": list(requires),
            "excludes": [], "native_product_id": None, "prices": [price],
            "source_kind": "test_fixture", "source_ref": "synthetic-l02",
            "test_only": True}


ANSWERS = {
    "launch.launch_at": "2026-11-03T12:00:00-05:00",
    "launch.doors_open_at": "2026-11-03T09:00:00-05:00",
    "launch.doors_close_at": "2026-11-10T23:59:00-05:00",
    "launch.timezone": "America/New_York",
    "launch.channels": ["email", "text"],
    "launch.a2p_ready": False,
    "launch.conversation_ai": False,
    "launch.landing_url": "https://example.test/landing",
    "launch.sales_page_url": "https://example.test/sales",
    "launch.checkout_url": "https://example.test/order",
    "launch.thank_you_url": "https://example.test/thanks",
    "launch.access_url": "https://example.test/access",
}

EXTRAS = {"upsell_1": True, "downsell_1": False, "upsell_2": False}


def _launch(**over) -> dict:
    base = {
        "launch_id": "l02-synthetic",
        "journey_mode": "single_simple",
        "extras": dict(EXTRAS),
        "offers": [
            _offer("MAIN-A", "main", "Package A", _price("MAIN-A-USD", 49700),
                   entitlements=["base-a"]),
            _offer("U1", "upsell_1", "Upgrade", _price("U1-USD", 9900),
                   entitlements=["upgrade-b"]),
        ],
    }
    base.update(over)
    return base


def _contract(plan: dict, label: str) -> None:
    errors = VALIDATOR.validate_plan(plan, SCHEMA)
    say(not errors, f"{label}: the plan validates against the launch-plan contract"
        + ("" if not errors else f" — {errors}"))


def _answers(**over) -> dict:
    merged = dict(ANSWERS)
    merged.update(over)
    return merged


# ---------------------------------------------------------------------------
# Offers: preservation, no collapse, unknown never zero, free route.
# ---------------------------------------------------------------------------
def test_packages_preserved() -> None:
    launch = _launch(
        journey_mode="multiple_options",
        extras={"upsell_1": False, "downsell_1": False, "upsell_2": False},
        offers=[
            _offer("MAIN-A", "main", "Starter", _price("MAIN-A-USD", 19700)),
            _offer("MAIN-B", "main", "Core", _price("MAIN-B-USD", 49700)),
            _offer("MAIN-C", "main", "Elite", _price("MAIN-C-EUR", 79700, "EUR")),
        ])
    result = launch_plan.build_launch_plan(launch, _answers())
    say(result["state"] == "ready", "multi-package launch assembles")
    plan = result["plan"]
    _contract(plan, "multi-package")
    packages = plan["offer"]["packages"]
    say([p["offer_id"] for p in packages] == ["MAIN-A", "MAIN-B", "MAIN-C"],
        "every package keeps its own offer id in order")
    say([p["price_id"] for p in packages] == ["MAIN-A-USD", "MAIN-B-USD", "MAIN-C-EUR"],
        "every package keeps its own price id")
    say([p["amount_minor"] for p in packages] == [19700, 49700, 79700],
        "every package keeps exact minor units (no lowest-price collapse)")
    say([p["currency"] for p in packages] == ["USD", "USD", "EUR"],
        "every package keeps its own currency")
    say(plan["offer"]["name"] == "Starter / Core / Elite",
        "main names are joined, not reduced to one")
    say(plan["offer"]["price_usd"] == 197.0,
        "the scalar entry price is the first package, never a minimum")
    say(all(p["provenance"]["source_kind"] == "test_fixture"
            and p["provenance"]["source_ref"] == "synthetic-l02"
            and p["provenance"]["amount_state"] == "provided"
            for p in packages),
        "provenance is carried per package")
    say(plan["offer"]["billing_conversion"]["owner"] == "launch_bridge"
        and plan["offer"]["billing_conversion"]["lane"] == "L14",
        "billing conversion is requested from the launch_bridge lane, never done here")


def test_unknown_price_never_zero() -> None:
    launch = _launch(offers=[
        _offer("MAIN-A", "main", "Package A", _price("MAIN-A-USD", None))])
    result = launch_plan.build_launch_plan(launch, _answers())
    say(result["state"] == "awaiting_missing_fact" and result["plan"] is None,
        "an unknown price blocks the plan instead of becoming zero")
    say(any("price" in m and "unknown" in m for m in result["missing"]),
        "the unknown price is named as a missing fact")

    launch = _launch(offers=[
        _offer("MAIN-A", "main", "Package A", _price("MAIN-A-USD", 12.5))])
    result = launch_plan.build_launch_plan(launch, _answers())
    say(result["state"] == "awaiting_missing_fact",
        "a non-integer amount is unsupported, never rounded into a price")

    launch = _launch(offers=[
        _offer("MAIN-A", "main", "Package A", _price("MAIN-A-USD", 49700, currency=""))])
    result = launch_plan.build_launch_plan(launch, _answers())
    say(result["state"] == "awaiting_missing_fact"
        and any("currency" in m for m in result["missing"]),
        "a missing currency is a missing fact, never defaulted to USD")


def test_free_route() -> None:
    free = _launch(
        journey_mode="free_entry",
        extras={"upsell_1": False, "downsell_1": False, "upsell_2": False},
        offers=[_offer("MAIN-A", "main", "Free Seat",
                       _price("MAIN-A-USD", 0, status="provided"))])
    result = launch_plan.build_launch_plan(free, _answers())
    say(result["state"] == "ready", "a verified free price assembles on the free route")
    say(result["plan"]["offer"]["packages"][0]["amount_minor"] == 0,
        "a verified free package keeps its real zero")
    _contract(result["plan"], "verified free")

    unsafe = _launch(
        extras={"upsell_1": False, "downsell_1": False, "upsell_2": False},
        offers=[_offer("MAIN-A", "main", "Free Seat",
                       _price("MAIN-A-USD", 0, status="provided"))])
    result = launch_plan.build_launch_plan(unsafe, _answers())
    say(result["state"] == "awaiting_missing_fact"
        and any("free route" in m for m in result["missing"]),
        "a zero price off the free route is rejected as unsupported")

    unverified = _launch(
        journey_mode="free_entry",
        extras={"upsell_1": False, "downsell_1": False, "upsell_2": False},
        offers=[_offer("MAIN-A", "main", "Free Seat",
                       _price("MAIN-A-USD", 0, status="unknown"))])
    result = launch_plan.build_launch_plan(unverified, _answers())
    say(result["state"] == "awaiting_missing_fact",
        "an unverified zero is not accepted as free")


def test_installment_terms() -> None:
    bare = _launch(offers=[
        _offer("MAIN-A", "main", "Package A",
               _price("MAIN-A-USD", 49700, billing="installment", schedule=[]))])
    result = launch_plan.build_launch_plan(bare, _answers())
    say(result["state"] == "awaiting_missing_fact"
        and any("installment terms" in m for m in result["missing"]),
        "an installment without exact terms is explicitly rejected as unsupported")

    schedule = [{"amount_minor": 16600, "due": "2026-11-03"},
                {"amount_minor": 16600, "due": "2026-12-03"},
                {"amount_minor": 16500, "due": "2027-01-03"}]
    terms = _launch(offers=[
        _offer("MAIN-A", "main", "Package A",
               _price("MAIN-A-USD", 49700, billing="installment", schedule=schedule))])
    result = launch_plan.build_launch_plan(terms, _answers())
    say(result["state"] == "ready", "an installment with exact terms assembles")
    plan = result["plan"]
    _contract(plan, "installment")
    say(plan["offer"]["packages"][0]["billing_schedule"] == schedule,
        "installment terms are retained verbatim")
    say(plan["offer"]["payment_plans"] is True
        and any(a["family"] == "failed_payment" for a in plan["automations"]),
        "installment terms open the failed-payment family")

    trial = _launch(offers=[
        _offer("MAIN-A", "main", "Package A",
               _price("MAIN-A-USD", 49700, billing="trial", schedule=[]))])
    result = launch_plan.build_launch_plan(trial, _answers())
    say(result["state"] == "awaiting_missing_fact"
        and any("trial terms" in m for m in result["missing"]),
        "a trial without exact terms is explicitly rejected as unsupported")


# ---------------------------------------------------------------------------
# Event eligibility: explicit, self-paced excludes event units, start separate.
# ---------------------------------------------------------------------------
def _unit_ids(plan: dict) -> set:
    return {u["id"] for array in ("text_sets", "automations")
            for u in plan.get(array, [])}


def test_self_paced_no_event_units() -> None:
    for fact_key, value in (("launch.product_type", "self_paced"),
                            ("launch.delivery_mode", "self-paced"),
                            ("launch.event.type", "evergreen")):
        result = launch_plan.build_launch_plan(_launch(), _answers(**{fact_key: value}))
        say(result["state"] == "ready", f"{fact_key}={value!r}: the plan assembles")
        plan = result["plan"]
        _contract(plan, f"self-paced {fact_key}")
        ids = _unit_ids(plan)
        say("text_event_reminder" not in ids and "auto_event_reminders" not in ids,
            f"{fact_key}={value!r}: no webinar, reminder, replay or no-show units")
        say(plan["event"]["eligible"] is False
            and "self-paced" in plan["event"]["reason"],
            f"{fact_key}={value!r}: event eligibility is explicit and recorded")


def test_no_event_facts_plans_no_event_units() -> None:
    result = launch_plan.build_launch_plan(_launch(), _answers())
    plan = result["plan"]
    say(plan["event"]["eligible"] is False
        and "no approved event facts" in plan["event"]["reason"],
        "absent event facts plan no event units (fail closed, nothing invented)")
    _contract(plan, "no event facts")


def test_live_event_start_separate_from_sale_opening() -> None:
    facts = {"launch.product_type": "live_webinar",
             "launch.event.starts_at": "2026-11-05T19:00:00-05:00"}
    result = launch_plan.build_launch_plan(_launch(), _answers(**facts))
    say(result["state"] == "ready", "an approved live event assembles")
    plan = result["plan"]
    _contract(plan, "live event")
    ids = _unit_ids(plan)
    say("text_event_reminder" in ids and "auto_event_reminders" in ids,
        "an approved live event plans its reminder/replay family")
    say(plan["event"]["starts_at"] == "2026-11-05T19:00:00-05:00"
        and plan["event"]["sale_opens_at"] == "2026-11-03T09:00:00-05:00",
        "the event start and the sale opening are separate facts")
    say(plan["event"]["starts_at"] != plan["event"]["sale_opens_at"],
        "the sale opening is never reused as the event start")

    missing_start = launch_plan.build_launch_plan(
        _launch(), _answers(**{"launch.product_type": "live_webinar"}))
    say(missing_start["state"] == "awaiting_missing_fact"
        and any("launch.event.starts_at" in m for m in missing_start["missing"]),
        "a live event without its own start blocks by name")

    # A sale opening alone must never be taken as the event start.
    doors_only = launch_plan.build_launch_plan(
        _launch(), _answers(**{"launch.event.type": "webinar"}))
    say(doors_only["state"] == "awaiting_missing_fact",
        "launch.doors_open_at is never substituted for launch.event.starts_at")


# ---------------------------------------------------------------------------
# Access destination + entitlements.
# ---------------------------------------------------------------------------
def test_access_resolution() -> None:
    result = launch_plan.build_launch_plan(_launch(), _answers())
    plan = result["plan"]
    _contract(plan, "access explicit")
    say(plan["access"]["resolved"] is True
        and plan["access"]["destination"] == "https://example.test/access"
        and plan["access"]["destination_source"] == "launch.access_url",
        "the approved access destination is resolved and its source recorded")
    say(plan["access"]["entitlements"] == ["base-a", "upgrade-b"],
        "every purchased entitlement is kept (main + upsell)")
    say(plan["access"]["base_entitlements"] == ["base-a"]
        and plan["access"]["upsell_entitlements"] == {"upsell_1": ["upgrade-b"]},
        "entitlements stay tied to the offer that grants them (base vs upsell)")
    for unit_id in ("email_welcome_access", "text_access_link", "auto_post_sale"):
        units = [u for u in plan["email_sequences"] + plan["text_sets"]
                 + plan["automations"] if u["id"] == unit_id]
        say(units and units[0]["access_destination"] == "https://example.test/access"
            and units[0]["entitlements"] == ["base-a"],
            f"{unit_id}: carries the usable destination and the base entitlements only")
    upsells = [u for u in plan["email_sequences"] if u["id"] == "email_upsell_1"]
    say(upsells and upsells[0].get("entitlements") == ["upgrade-b"],
        "email_upsell_1: carries its own upsell entitlement, not every buyer's welcome")

    fallback = dict(ANSWERS)
    fallback.pop("launch.access_url")
    plan = launch_plan.build_launch_plan(_launch(), fallback)["plan"]
    _contract(plan, "access thank-you fallback")
    say(plan["access"]["resolved"] is True
        and plan["access"]["destination"] == "https://example.test/thanks"
        and plan["access"]["destination_source"] == "launch.thank_you_url",
        "an approved thank-you page resolves the access destination")

    no_destination = dict(ANSWERS)
    for key in ("launch.access_url", "launch.login_url", "launch.member_area_url",
                "launch.thank_you_url"):
        no_destination.pop(key, None)
    result = launch_plan.build_launch_plan(_launch(), no_destination)
    say(result["state"] == "awaiting_missing_fact"
        and any("access destination" in m for m in result["missing"]),
        "a paid launch with nowhere to deliver access blocks by name")

    prerequisites = _launch(offers=[
        _offer("MAIN-A", "main", "Package A", _price("MAIN-A-USD", 49700),
               entitlements=["base-a"], requires=["community-access"]),
        _offer("U1", "upsell_1", "Upgrade", _price("U1-USD", 9900),
               entitlements=["upgrade-b"])])
    plan = launch_plan.build_launch_plan(prerequisites, _answers())["plan"]
    say(plan["access"]["prerequisites"] == ["community-access"],
        "entitlement prerequisites are resolved, not assumed")

    no_delivery = _answers(**{"launch.access_delivery": "No, nothing to deliver"})
    plan = launch_plan.build_launch_plan(_launch(), no_delivery)["plan"]
    say(plan["access"]["deliver_access"] is False,
        "the access-delivery choice is respected (no delivery)")
    welcome = [u for u in plan["email_sequences"] if u["id"] == "email_welcome_access"]
    say(welcome and welcome[0]["access_destination"] is None
        and welcome[0]["entitlements"] == [],
        "no-delivery choice: welcome units carry no destination or entitlements")

    yes_delivery = _answers(
        **{"launch.access_delivery": "Yes, send access after purchase"})
    plan = launch_plan.build_launch_plan(_launch(), yes_delivery)["plan"]
    welcome = [u for u in plan["email_sequences"] if u["id"] == "email_welcome_access"]
    say(plan["access"]["deliver_access"] is True
        and welcome and welcome[0]["entitlements"] == ["base-a"],
        "yes-delivery choice: welcome units carry the base entitlements")


# ---------------------------------------------------------------------------
# Founder identity is never inferred; offer ids are never invented.
# ---------------------------------------------------------------------------
def test_no_founder_inference() -> None:
    launch = _launch(offers=[
        {"slot": "main", "display_name": "Unnamed Package",
         "prices": [_price("P-1", 49700)]}])
    result = launch_plan.build_launch_plan(launch, _answers())
    plan = result["plan"]
    text = json.dumps(plan).lower()
    say("founder" not in text and "owner_name" not in text,
        "the plan never infers or emits a founder identity")
    package = plan["offer"]["packages"][0]
    say(package["offer_id"] is None and package["price_id"] == "P-1",
        "a missing offer id stays None; nothing is invented to fill it")


def main() -> int:
    test_packages_preserved()
    test_unknown_price_never_zero()
    test_free_route()
    test_installment_terms()
    test_self_paced_no_event_units()
    test_no_event_facts_plans_no_event_units()
    test_live_event_start_separate_from_sale_opening()
    test_access_resolution()
    test_no_founder_inference()
    print("RESULT:", "PASS" if _ok else "FAIL")
    return 0 if _ok else 1


if __name__ == "__main__":
    sys.exit(main())
