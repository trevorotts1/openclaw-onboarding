#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""launch_plan.py — the FULL launch plan for a Skill 49 signature launch.

WHY
---
Skill 49 already plans every PAGE (page_set.py) and assembles the launch record
offers + route graph (launch_intake.py). Spec §4 makes the dispatcher the single
conductor of a whole launch, so the plan it dispatches must also list the email
sequences (Skill 50), the text sets, the automation families (Skill 44) and the
optional Conversation AI (Skill 38). This module turns the assembled launch
record + the intake answer ledger into ONE document in the shared contract
`shared-utils/signature_launch_contract/launch-plan.schema.json`, with a
`waits_for` edge per unit.

Contract: pages + email_sequences + text_sets + automations +
conversation_ai{requested,mode} + launch_calendar + a2p_ready.

LAW
---
* Plans only. Nothing here sends, builds, spends or switches anything live.
  every email, text and automation carries draft_only = true.
* Missing facts BLOCK the plan by name (state awaiting_missing_fact): a launch
  date, doors-open/close time, timezone or the Conversation AI mode is asked,
  never invented. A2P unknown is treated as not ready, the safe side: texts stay
  drafts and the package warns.
* `build_rail` is `skill44_engine` for every automation family — the answer
  recorded by U-GHL-PROBE (the official GHL API cannot author a workflow;
  `44-convert-and-flow-operator/automation-templates/launch-ghl-probe/
  GHL-CAPABILITY-NOTE.md`).
* Failed payment is planned only when the offer has payment plans; the AI reply
  workflow only when Conversation AI was requested; texts only when the client
  chose email + text. Promotional text sets stay within the spec cap of 5.
* Offers are preserved per package: offer id, price id, minor units, currency,
  billing type/schedule and provenance are copied verbatim, never collapsed to
  the lowest price. An unknown price is a missing fact, never zero; a zero price
  is accepted only on the supported free route (`journey_mode == "free_entry"`
  with a price whose approval status is not `unknown`). Founder identity is
  never inferred from anything.
* Event units are explicit: webinar, reminder, replay and no-show units are
  planned only from approved live-event facts. A self-paced product (and the
  absence of approved event facts) plans none. The event start is a separate
  fact from the sale opening; it is never read from, or substituted by,
  `launch.doors_open_at`.
* Access is resolved, not assumed: the welcome/access actions carry the approved
  access destination (or the approved thank-you page) plus every purchased
  entitlement and its prerequisites. Billing conversion itself belongs to the
  launch_bridge lane (L14); this planner only records the request.

Deterministic, stdlib only, no network, no model. Exit 0/2/3.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page_set as ps  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_FAILCLOSED = 3

SCHEMA_VERSION = "1.0.0"
SEND_WINDOW_DEFAULT = {"start": "08:00", "end": "21:00", "timezone": "recipient_local"}
PROMOTIONAL_CAP = 5

# Approved product/event facts (normalised: lower case, '-' and spaces become '_').
# A self-paced product may never carry a webinar, reminder, replay or no-show unit.
SELF_PACED_PRODUCT_TYPES = frozenset({
    "self_paced", "selfpaced", "evergreen", "on_demand", "recorded", "digital",
    "digital_product", "digital_course", "course_on_demand", "async",
})
LIVE_EVENT_TYPES = frozenset({
    "webinar", "live_webinar", "live_event", "live", "workshop", "challenge",
    "masterclass", "bootcamp", "live_stream", "live_streaming", "in_person_event",
})
EVENT_UNIT_IDS = ("auto_event_reminders", "text_event_reminder")
ACCESS_KEYS = ("launch.access_url", "launch.login_url", "launch.member_area_url")

# Page kind in the shared contract for each page_key in structure/page_types.json.
_CONTRACT_PAGE_KIND = {
    "landing": "landing", "sales": "sales", "product_selection": "order",
    "checkout": "checkout", "upsell_1": "upsell", "upsell_2": "upsell",
    "downsell_1": "downsell", "downsell_2": "downsell", "thank_you": "thank_you",
}

# U-GHL-PROBE: every family builds through Skill 44's engine (see module docstring).
BUILD_RAIL = "skill44_engine"

_MISSING = object()


class LaunchPlanError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Reading the intake answer ledger.
# ---------------------------------------------------------------------------
def _entry(answers: Dict[str, Any], key: str) -> Any:
    """The ledger entry for `key`, in launch_intake session form
    ({value, state}) or as a plain value. `_MISSING` when absent."""
    if key in answers:
        return answers[key]
    return _MISSING


def fact(answers: Dict[str, Any], *keys: str) -> Any:
    """The first supplied value among `keys`, or None.

    A fact whose state is `unknown` counts as NOT supplied: unknown is never a
    value (doc 03). `not_applicable` is a real answer of None (for example "no
    paid pieces"), so it is returned as None but does not count as missing."""
    for key in keys:
        entry = _entry(answers, key)
        if entry is _MISSING:
            continue
        if isinstance(entry, dict) and "value" in entry and (
                "state" in entry or "question_id" in entry):
            value, state = entry.get("value"), entry.get("state")
            if state == "unknown":
                return None
            return value
        return entry
    return None


def has_fact(answers: Dict[str, Any], *keys: str) -> bool:
    """True when at least one of `keys` is present with a non-unknown state
    (a supplied `not_applicable` counts — it is a real answer)."""
    for key in keys:
        entry = _entry(answers, key)
        if entry is _MISSING:
            continue
        if isinstance(entry, dict) and "value" in entry and (
                "state" in entry or "question_id" in entry):
            if entry.get("state") == "unknown":
                continue
            if entry.get("state") == "not_applicable":
                return True
            if entry.get("value") is not None:
                return True
            continue
        if entry is not None:
            return True
    return False


# ---------------------------------------------------------------------------
# Offer facts.
# ---------------------------------------------------------------------------
def _norm(value: Any) -> str:
    """Normalise an approved fact for comparison: no case, '-' or spaces."""
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _offers(launch: Dict[str, Any]) -> List[Dict[str, Any]]:
    offers = [o for o in launch.get("offers", []) if isinstance(o, dict)]
    mains = [o for o in offers if o.get("slot") == "main"] or offers
    return mains


def _price_of(offer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for price in offer.get("prices") or []:
        if isinstance(price, dict):
            return price
    return None


def _package_record(offer: Dict[str, Any], index: int) -> Dict[str, Any]:
    """One package, verbatim: ids, minor units, currency, billing and provenance.

    Nothing is defaulted. An amount that is not a whole number of minor units is
    reported as unsupported (its raw value is kept for the reader) and a missing
    amount stays None — never zero. The offer id is never invented: an offer
    without one records None. Founder identity is not a field here and is never
    derived from an offer or a name.
    """
    price = _price_of(offer) or {}
    amount = price.get("amount_minor")
    known_amount = isinstance(amount, int) and not isinstance(amount, bool)
    currency = price.get("currency")
    schedule = price.get("schedule")
    return {
        "offer_id": offer.get("offer_id"),
        "slot": offer.get("slot"),
        "display_name": offer.get("display_name"),
        "price_id": price.get("price_choice_id") or price.get("price_id"),
        "amount_minor": amount if known_amount else None,
        "amount_raw": amount,
        "currency": currency if isinstance(currency, str) and currency else None,
        "billing_type": price.get("billing_type"),
        "billing_schedule": list(schedule) if isinstance(schedule, list) else [],
        "billing_schedule_raw": schedule,
        "terms_source": price.get("terms_source"),
        "native_product_id": offer.get("native_product_id"),
        "entitlements": list(offer.get("entitlement_ids") or []),
        "prerequisites": list(offer.get("requires") or []),
        "provenance": {
            "source": "launch.offers",
            "offer_index": index,
            "source_kind": offer.get("source_kind"),
            "source_ref": offer.get("source_ref"),
            "test_only": bool(offer.get("test_only")),
            "price_approval_status": price.get("approval_status"),
            "amount_state": "provided" if known_amount
            else ("unknown" if amount is None else "unsupported"),
        },
    }


def _free_route_supported(launch: Dict[str, Any], package: Dict[str, Any]) -> bool:
    """A zero amount is a real price only on the supported free route."""
    status = (package.get("provenance") or {}).get("price_approval_status")
    return _norm(launch.get("journey_mode")) == "free_entry" and status != "unknown"


def _payment_plans(launch: Dict[str, Any], answers: Dict[str, Any],
                   packages: Optional[Sequence[Dict[str, Any]]] = None) -> bool:
    explicit = fact(answers, "offers.main.payment_plans", "launch.payment_plans")
    if explicit is not None:
        return bool(explicit)
    for package in packages or []:
        if package.get("billing_type") in ("installment", "recurring", "trial") \
                or package.get("billing_schedule"):
            return True
    billing = fact(answers, "offers.main.billing_type")
    if billing in ("installment", "recurring", "trial"):
        return True
    return bool(fact(answers, "offers.main.schedule") or [])


def _offer_block(launch: Dict[str, Any], answers: Dict[str, Any],
                 missing: List[str]) -> Dict[str, Any]:
    """The offer block with one preserved record per package (no lowest-price collapse)."""
    offers = [o for o in launch.get("offers", []) if isinstance(o, dict)]
    packages = [_package_record(offer, index) for index, offer in enumerate(offers)]
    mains = [p for p in packages if p.get("slot") == "main"] or packages
    names = [p.get("display_name") for p in mains if p.get("display_name")]
    primary = mains[0] if mains else None

    for package in mains:
        label = package.get("display_name") or package.get("offer_id") or \
            "main package %d" % (int(package["provenance"]["offer_index"]) + 1)
        amount = package.get("amount_minor")
        if amount is None:
            raw = package.get("amount_raw")
            missing.append("the price of %s (unknown is not a price and is never zero%s)"
                           % (label, "" if raw is None else "; got %r" % (raw,)))
        elif amount == 0 and not _free_route_supported(launch, package):
            missing.append("a supported free route for %s (a zero amount is accepted only on "
                           "journey_mode free_entry with an approved price)" % label)
        if not package.get("currency"):
            missing.append("the currency of %s" % label)
        elif not (package["currency"].isupper() and len(package["currency"]) == 3):
            missing.append("the ISO-4217 currency code of %s (got %r)"
                           % (label, package["currency"]))
        raw_schedule = package.get("billing_schedule_raw")
        if raw_schedule is not None and not isinstance(raw_schedule, list):
            missing.append("a billing schedule for %s must be a list of due/amount rows "
                           "(got %r)" % (label, raw_schedule))
        if package.get("billing_type") in ("installment", "trial", "recurring") \
                and not package.get("billing_schedule") and not package.get("terms_source"):
            missing.append("the exact %s terms for %s (unsupported without a schedule or "
                           "terms source)" % (package["billing_type"], label))

    price_usd = None
    if primary is not None and primary.get("amount_minor") is not None:
        price_usd = round(primary["amount_minor"] / 100.0, 2)
    return {
        "name": " / ".join(names) if names else str(launch.get("launch_id", "launch")),
        # Primary (first main) package for the single scalar the contract requires;
        # every package's own exact price lives in `packages`. Never a minimum.
        "price_usd": price_usd if price_usd is not None else 0.0,
        "currency": (primary or {}).get("currency"),
        "payment_plans": _payment_plans(launch, answers, packages),
        "packages": packages,
        "landing_url": fact(answers, "launch.landing_url"),
        "sales_page_url": fact(answers, "launch.sales_page_url"),
        "checkout_url": fact(answers, "launch.checkout_url"),
        "thank_you_url": fact(answers, "launch.thank_you_url"),
        # Recorded for the launch_bridge lane (L14); this planner never converts.
        "billing_conversion": {
            "owner": "launch_bridge",
            "lane": "L14",
            "requested": True,
            "reason": "billing/route conversion belongs to the bridge; the planner keeps the "
                      "approved minor units, currency and schedule verbatim",
        },
    }


# ---------------------------------------------------------------------------
# Event eligibility and access delivery.
# ---------------------------------------------------------------------------
def _event_block(launch: Dict[str, Any], answers: Dict[str, Any],
                 calendar: Dict[str, Any], missing: List[str]) -> Dict[str, Any]:
    """Explicit event eligibility from approved facts, with the event start kept
    separate from the sale opening. No fact means no event units (fail closed)."""
    raw_event = launch.get("event") if isinstance(launch.get("event"), dict) else {}
    product_type = (_norm(fact(answers, "launch.product_type", "launch.offer_type",
                               "launch.delivery_mode"))
                    or _norm(raw_event.get("product_type"))
                    or _norm(launch.get("product_type")))
    event_type = (_norm(fact(answers, "launch.event.type", "launch.event_type"))
                  or _norm(raw_event.get("type")))
    starts_at = (fact(answers, "launch.event.starts_at", "launch.event_start_at")
                 or raw_event.get("starts_at"))

    eligible = False
    reason: Optional[str] = None
    if product_type in SELF_PACED_PRODUCT_TYPES or event_type in SELF_PACED_PRODUCT_TYPES:
        reason = ("self-paced product: no webinar, reminder, replay or no-show units "
                  "(product_type=%r, event_type=%r)"
                  % (product_type or None, event_type or None))
    elif event_type in LIVE_EVENT_TYPES or product_type in LIVE_EVENT_TYPES:
        eligible, reason = True, None
    elif not (product_type or event_type):
        reason = ("no approved event facts: webinar, reminder, replay and no-show units "
                  "are not planned")
    else:
        reason = ("approved facts do not describe a live event "
                  "(product_type=%r, event_type=%r)"
                  % (product_type or None, event_type or None))

    if eligible and not starts_at:
        missing.append("when the live event starts (launch.event.starts_at) — the event "
                       "start is separate from when the sale opens")

    return {
        "eligible": eligible,
        "type": (event_type or product_type) if eligible else None,
        "starts_at": starts_at if eligible else None,
        # Separate fields, both sourced from the calendar/event facts above.
        "sale_opens_at": calendar.get("doors_open_at"),
        "sale_closes_at": calendar.get("doors_close_at"),
        "reminders_planned": eligible,
        "facts": {"product_type": product_type or None,
                  "event_type": event_type or None},
        "reason": reason,
    }


def _access_block(launch: Dict[str, Any], answers: Dict[str, Any],
                  missing: List[str]) -> Dict[str, Any]:
    """Resolve the approved access destination and keep every purchased entitlement."""
    offers = [o for o in launch.get("offers", []) if isinstance(o, dict)]
    entitlements: List[str] = []
    prerequisites: List[str] = []
    for offer in offers:
        for entitlement in offer.get("entitlement_ids") or []:
            if isinstance(entitlement, str) and entitlement and entitlement not in entitlements:
                entitlements.append(entitlement)
        for requirement in offer.get("requires") or []:
            if isinstance(requirement, str) and requirement and requirement not in prerequisites:
                prerequisites.append(requirement)
    explicit = fact(answers, "launch.entitlements")
    if isinstance(explicit, list):
        for entitlement in explicit:
            if isinstance(entitlement, str) and entitlement and entitlement not in entitlements:
                entitlements.append(entitlement)

    destination: Optional[str] = None
    source: Optional[str] = None
    for key in ACCESS_KEYS:
        value = fact(answers, key)
        if isinstance(value, str) and value.strip():
            destination, source = value.strip(), key
            break
    if not destination:
        value = fact(answers, "launch.thank_you_url")
        if isinstance(value, str) and value.strip():
            destination = value.strip()
            source = "launch.thank_you_url"

    login = fact(answers, "launch.login_url")
    login_url = login.strip() if isinstance(login, str) and login.strip() else None

    if not destination:
        # Every welcome/access action needs a usable approved destination, even on
        # the free route; a purchase or a registration may never land nowhere.
        missing.append("the access destination members use after purchase or registration "
                       "(launch.access_url, launch.login_url or an approved thank-you page)")
    return {
        "resolved": bool(destination),
        "destination": destination,
        "destination_source": source,
        "login_url": login_url,
        "entitlements": entitlements,
        "prerequisites": prerequisites,
        "delivery": "access_link_email_and_text" if destination else "unresolved",
    }


# ---------------------------------------------------------------------------
# Units.
# ---------------------------------------------------------------------------
def _units(launch: Dict[str, Any], landing_pages: Optional[Iterable[str]],
           extra_pages: Sequence[str]) -> Dict[str, Any]:
    """The page list and its unit ids, in page order, with the route-chain waits."""
    page_set = ps.build_page_set(launch, landing_pages=landing_pages, extra_pages=extra_pages)
    pages: List[Dict[str, Any]] = []
    for entry in page_set["pages"]:
        page_key = entry["page_key"]
        uid = "page_" + page_key
        kind = _CONTRACT_PAGE_KIND.get(page_key, "other")
        # landing pages (opt-in and sales) are roots; every later page waits for
        # the page before it in the route, exactly as the contract fixtures read.
        waits = [] if page_key in ("landing", "sales") else ([pages[-1]["id"]] if pages else [])
        url_key = {"landing": "launch.landing_url", "sales": "launch.sales_page_url",
                   "checkout": "launch.checkout_url", "thank_you": "launch.thank_you_url"}.get(page_key)
        pages.append({"id": uid, "kind": kind, "url": None,
                      "waits_for": waits, "_url_key": url_key})
    return {"page_set": page_set, "pages": pages}


def _text_sets(*, text_channel: bool, has_landing: bool,
               has_sales: bool, has_checkout: bool, has_thank_you: bool,
               keyword: Optional[str], send_window: Dict[str, Any],
               event_eligible: bool = False) -> List[Dict[str, Any]]:
    """Spec §3.2. Every set is a draft, ends with a reply invitation and STOP.
    a2p_ready=False changes nothing in the plan — the sets stay drafts and the
    package carries the warning; the plan never claims texts can send."""
    if not text_channel:
        return []
    landing_wait = ["page_landing"] if has_landing else (["page_sales"] if has_sales else [])
    sets: List[Dict[str, Any]] = [{
        "id": "text_opt_in_confirmation", "kind": "opt_in_confirmation",
        "messages": 1, "promotional": False, "draft_only": True,
        "opt_out_keyword": "STOP", "includes_reply_invitation": True,
        "send_window": dict(send_window), "waits_for": list(landing_wait),
    }]
    if keyword:
        sets.append({
            "id": "text_keyword_opt_in", "kind": "keyword_opt_in",
            "messages": 1, "promotional": False, "draft_only": True,
            "opt_out_keyword": "STOP", "includes_reply_invitation": True,
            "send_window": dict(send_window), "waits_for": list(landing_wait),
        })
    if event_eligible:  # only from approved live-event facts; self-paced products get none
        sets.append({
            "id": "text_event_reminder", "kind": "event_reminder",
            "messages": 3, "promotional": False, "draft_only": True,
            "opt_out_keyword": "STOP", "includes_reply_invitation": True,
            "send_window": dict(send_window), "waits_for": [],
        })
    sets.append({
        "id": "text_doors_open", "kind": "doors_open",
        "messages": 1, "promotional": True, "draft_only": True,
        "opt_out_keyword": "STOP", "includes_reply_invitation": True,
        "send_window": dict(send_window),
        "waits_for": ["page_sales"] if has_sales else list(landing_wait),
    })
    sets.append({
        "id": "text_last_call", "kind": "last_call",
        "messages": 2, "promotional": True, "draft_only": True,
        "opt_out_keyword": "STOP", "includes_reply_invitation": True,
        "send_window": dict(send_window), "waits_for": ["email_doors_closing"],
    })
    if has_checkout:
        sets.append({
            "id": "text_abandoned_checkout", "kind": "abandoned_checkout",
            "messages": 2, "promotional": True, "draft_only": True,
            "opt_out_keyword": "STOP", "includes_reply_invitation": True,
            "send_window": dict(send_window), "waits_for": ["page_checkout"],
        })
    if has_thank_you:
        sets.append({
            "id": "text_access_link", "kind": "access_link",
            "messages": 1, "promotional": False, "draft_only": True,
            "opt_out_keyword": "STOP", "includes_reply_invitation": True,
            "send_window": dict(send_window), "waits_for": ["page_thank_you"],
        })
    promotional = [s for s in sets if s["promotional"]]
    if len(promotional) > PROMOTIONAL_CAP:  # constructed under the cap; kept as a guard
        raise LaunchPlanError("promotional text sets exceed the cap of %d" % PROMOTIONAL_CAP)
    return sets


def _automations(*, has_upsells: bool, has_checkout: bool, has_thank_you: bool,
                 has_sales: bool, has_landing: bool, payment_plans: bool,
                 ai_requested: bool, text_ids: Sequence[str],
                 email_ids: Sequence[str], black_friday: bool,
                 event_eligible: bool = False) -> List[Dict[str, Any]]:
    """Spec §3.3, one unit per family, template per the spec table. Every unit is
    draft_only and builds through the Skill 44 engine (U-GHL-PROBE)."""
    text = set(text_ids)

    def tset(*ids: str) -> List[str]:
        return [i for i in ids if i in text]

    def unit(uid: str, family: str, template: str, trigger_type: str, detail: str,
             waits: Sequence[str]) -> Dict[str, Any]:
        return {"id": uid, "family": family, "template": template,
                "build_rail": BUILD_RAIL, "draft_only": True,
                "trigger": {"type": trigger_type, "detail": detail},
                "waits_for": list(waits)}

    landing_wait = "page_landing" if has_landing else ("page_sales" if has_sales else "")
    out = [
        unit("auto_pre_launch", "pre_launch", "cart-open-cart-close-launch-sequence",
             "launch_calendar",
             "teaser, countdown, doors open and doors close switches drive tags and the "
             "email/text schedule" + (" (Black Friday: teaser, countdown, Cyber Monday, last call)"
                                      if black_friday else ""),
             ["email_pre_launch", "email_main_launch", "email_doors_closing"]
             + tset("text_doors_open")),
        unit("auto_opt_in", "opt_in", "post-optin-multichannel-stack", "form_submitted",
             "waitlist / registration opt-in tags the contact and starts nurture",
             tset("text_opt_in_confirmation", "text_keyword_opt_in") + ["email_pre_launch"]),
    ]
    if event_eligible:  # approved live-event facts only; never for a self-paced product
        out.append(unit("auto_event_reminders", "event_reminders",
                        "webinar-registration-reminder-replay-stack", "registration",
                        "confirm, 1 week / 3 days / 1 day / 1 hour / 15 minutes before, then "
                        "replay and no-show follow-up", ["email_pre_launch"]
                        + tset("text_event_reminder")))
    post_sale_waits = ["email_welcome_access"] + (["page_thank_you"] if has_thank_you else []) \
        + tset("text_access_link")
    out.append(unit("auto_post_sale", "post_sale", "new", "payment_succeeded",
                    "access + welcome, promotional sends stop, next follow-up starts",
                    post_sale_waits))
    if has_upsells:
        followups = [f"email_{k}" for k in ("upsell_1", "upsell_2", "downsell_1", "downsell_2")]
        out.append(unit("auto_upsell_branch", "upsell_downsell", "new", "upsell_decision",
                        "bought or declined routes to the matching follow-up",
                        [i for i in followups if i in set(email_ids)]))
    if has_checkout:
        out.append(unit("auto_abandoned_checkout", "abandoned_checkout",
                        "abandoned-cart-multichannel-recovery", "checkout_started_unpaid",
                        "recovery stops on purchase",
                        ["email_abandoned_checkout"] + tset("text_abandoned_checkout")))
    out.append(unit("auto_page_retargeting", "page_retargeting",
                    "behavioral-retargeting-page-visit-fire", "page_visit_no_checkout",
                    "sales page visit without checkout gets one nudge",
                    [landing_wait] if landing_wait else []))
    out.append(unit("auto_onboarding_review", "onboarding_review",
                    "membership-stick-retention", "purchase",
                    "first hour / day / week, then a review and referral ask",
                    ["auto_post_sale"]))
    out.append(unit("auto_win_back", "win_back", "re-engagement-winback-broadcast",
                    "launch_closed_no_purchase",
                    "re-engagement for the next offer",
                    ["auto_post_sale"] + tset("text_last_call")))
    if payment_plans:
        out.append(unit("auto_failed_payment", "failed_payment", "new", "payment_failed",
                        "payment-plan recovery only (the offer has payment plans)",
                        ["auto_post_sale"]))
    if ai_requested:
        out.append(unit("auto_ai_reply", "conversation_ai_reply", "new", "customer_replied",
                        "SMS and chat replies route to the Conversation AI action; keyword "
                        "wake-up re-enables the bot",
                        tset("text_opt_in_confirmation") + ["auto_post_sale"]))
    return out


# ---------------------------------------------------------------------------
# Assembly.
# ---------------------------------------------------------------------------
def build_launch_plan(launch: Dict[str, Any], answers: Dict[str, Any], *,
                      landing_pages: Optional[Iterable[str]] = None,
                      extra_pages: Sequence[str] = ()) -> Dict[str, Any]:
    """Build the contract-shaped launch plan from the assembled launch record and
    the intake answer ledger.

    Returns {"state": "ready"|"awaiting_missing_fact", "missing": [...],
             "plan": {...}|None}. A missing calendar fact or Conversation AI mode
    stops the plan by name; nothing is defaulted that a lane would write as a
    deadline or a job the bot cannot do."""
    if not isinstance(launch, dict) or not launch.get("offers"):
        raise LaunchPlanError("the launch record has no offers; assemble the plan first")
    if not isinstance(answers, dict):
        raise LaunchPlanError("the answer ledger is not a JSON object")

    missing: List[str] = []
    calendar = {
        "launch_at": fact(answers, "launch.launch_at"),
        "doors_open_at": fact(answers, "launch.doors_open_at"),
        "doors_close_at": fact(answers, "launch.doors_close_at"),
        "timezone": fact(answers, "launch.timezone"),
    }
    for key, label in (("launch_at", "the launch date and time"),
                       ("doors_open_at", "when the doors open"),
                       ("doors_close_at", "when the doors close"),
                       ("timezone", "the launch timezone")):
        if not calendar[key]:
            missing.append(f"{label} (launch.{key})")
    bf = {k: fact(answers, f"launch.black_friday.{k}")
          for k in ("teaser_at", "countdown_at", "cyber_monday_at", "last_call_at")}
    if all(bf.values()):
        calendar["black_friday"] = bf
    elif any(bf.values()):
        missing.append("all four Black Friday times (teaser, countdown, Cyber Monday, "
                       "last call) — a partial Black Friday calendar is never filled in")

    ai_requested = bool(fact(answers, "launch.conversation_ai") or False)
    ai_mode = fact(answers, "launch.conversation_ai_mode")
    ai_channels = fact(answers, "launch.conversation_ai_channels")
    if ai_requested and ai_mode not in ("faq", "booking", "checkout", "full"):
        missing.append("what the Conversation AI does when someone replies "
                       "(faq / booking / checkout / full)")

    # Offer, event and access facts are resolved together so their missing facts
    # are named in one pass (no partial plan, no invented price/deadline/route).
    event = _event_block(launch, answers, calendar, missing)
    offer = _offer_block(launch, answers, missing)
    access = _access_block(launch, answers, missing)

    if missing:
        return {"state": "awaiting_missing_fact", "missing": missing, "plan": None}

    conversation_ai: Dict[str, Any] = {
        "requested": ai_requested, "mode": ai_mode if ai_requested else "none"}
    if ai_requested and ai_channels:
        conversation_ai["channels"] = list(ai_channels)

    built = _units(launch, landing_pages, extra_pages)
    pages = built["pages"]
    page_ids = {p["id"] for p in pages}
    has_landing, has_sales = "page_landing" in page_ids, "page_sales" in page_ids
    has_checkout, has_thank_you = "page_checkout" in page_ids, "page_thank_you" in page_ids

    for page in pages:  # resolve the page URL from the offer block
        url_key = page.pop("_url_key")
        if url_key is not None and not page["url"]:
            page["url"] = offer.get(url_key.split(".", 1)[1])

    emails: List[Dict[str, Any]] = []

    def email(uid: str, kind: str, count: int, waits: Sequence[str]) -> None:
        emails.append({"id": uid, "kind": kind, "provider": "skill50",
                       "email_count": count, "draft_only": True,
                       "waits_for": [w for w in waits if w in page_ids or w in
                                     {e["id"] for e in emails}]})

    email("email_pre_launch", "pre_launch", 5 if "black_friday" in calendar else 4,
          ["page_landing"] if has_landing else (["page_sales"] if has_sales else []))
    email("email_main_launch", "main_launch", 10,
          ["page_sales"] if has_sales else (["page_landing"] if has_landing else []))
    email("email_doors_closing", "doors_closing", 3, ["email_main_launch"])
    for page in pages:
        if page["kind"] == "upsell":
            email(f"email_{page['id'].removeprefix('page_')}", "upsell_followup", 2, [page["id"]])
        elif page["kind"] == "downsell":
            email(f"email_{page['id'].removeprefix('page_')}", "downsell_followup", 2, [page["id"]])
    if has_checkout:
        email("email_abandoned_checkout", "abandoned_checkout", 3, ["page_checkout"])
    email("email_welcome_access", "welcome_access", 2,
          ["page_thank_you"] if has_thank_you else ["email_main_launch"])

    email_ids = {e["id"] for e in emails}
    channels = fact(answers, "launch.channels")
    if isinstance(channels, list):
        text_channel = any(str(c).lower() in ("text", "sms") for c in channels)
    elif isinstance(channels, str):
        text_channel = "text" in channels.lower() or "sms" in channels.lower()
    else:
        text_channel = bool(fact(answers, "launch.texts_enabled") or False)
    send_window = fact(answers, "launch.send_window") or dict(SEND_WINDOW_DEFAULT)
    texts = _text_sets(text_channel=text_channel, has_landing=has_landing,
                       has_sales=has_sales, has_checkout=has_checkout,
                       has_thank_you=has_thank_you,
                       keyword=fact(answers, "launch.text_keyword"),
                       send_window=send_window,
                       event_eligible=event["eligible"])
    text_ids = [t["id"] for t in texts]

    has_upsells = any(p["kind"] in ("upsell", "downsell") for p in pages)
    automations = _automations(
        has_upsells=has_upsells, has_checkout=has_checkout, has_thank_you=has_thank_you,
        has_sales=has_sales, has_landing=has_landing,
        payment_plans=offer["payment_plans"], ai_requested=ai_requested,
        text_ids=text_ids, email_ids=sorted(email_ids),
        black_friday="black_friday" in calendar,
        event_eligible=event["eligible"])

    # Every welcome/access action carries the resolved destination and the full
    # entitlement set, so a lane can never deliver a purchase to nowhere or drop
    # an entitlement the buyer paid for.
    for unit in emails + texts + automations:
        if unit["id"] in ("email_welcome_access", "text_access_link", "auto_post_sale"):
            unit["access_destination"] = access["destination"]
            unit["entitlements"] = list(access["entitlements"])
            unit["prerequisites"] = list(access["prerequisites"])

    a2p_ready = bool(fact(answers, "launch.a2p_ready") or False)
    warnings: List[str] = []
    if not access["resolved"]:
        warnings.append("no access destination resolved: welcome/access actions have no "
                        "usable approved destination")
    if texts and not a2p_ready:
        warnings.append("A2P 10DLC is not approved: texts stay drafts and cannot send")
    if not event["eligible"]:
        warnings.append("event units are not planned — " + str(event["reason"]))

    plan = {
        "schema_version": SCHEMA_VERSION,
        "launch_id": str(launch.get("launch_id", "launch")),
        "offer": offer,
        "launch_calendar": calendar,
        "event": event,
        "access": access,
        "warnings": warnings,
        "a2p_ready": a2p_ready,
        "conversation_ai": conversation_ai,
        "pages": pages,
        "email_sequences": emails,
        "text_sets": texts,
        "automations": automations,
    }
    _assert_waits_resolve(plan)
    return {"state": "ready", "missing": [], "plan": plan}


def _assert_waits_resolve(plan: Dict[str, Any]) -> None:
    """Every waits_for id resolves to a unit in this plan; ids are unique. A
    dangling edge would stall the swarm forever, so it is refused here too."""
    ids: List[str] = []
    for array in ("pages", "email_sequences", "text_sets", "automations"):
        ids += [u["id"] for u in plan.get(array, [])]
    known = set(ids)
    if len(known) != len(ids):
        raise LaunchPlanError("duplicate unit id in the launch plan")
    for array in ("pages", "email_sequences", "text_sets", "automations"):
        for unit in plan.get(array, []):
            for wait in unit.get("waits_for", []):
                if wait not in known:
                    raise LaunchPlanError(
                        f"{unit['id']}: waits_for unknown unit {wait!r}")
                if wait == unit["id"]:
                    raise LaunchPlanError(f"{unit['id']}: waits_for itself")


def build_from_session(session: Dict[str, Any], *,
                       landing_pages: Optional[Iterable[str]] = None,
                       extra_pages: Sequence[str] = ()) -> Dict[str, Any]:
    """The plan for one launch_intake session. `session["plan"]` is the assembled
    launch record; `session["answers"]` is the provenance ledger."""
    launch = session.get("plan")
    if not launch:
        raise LaunchPlanError("session has no assembled launch record")
    return build_launch_plan(launch, session.get("answers") or {},
                             landing_pages=landing_pages, extra_pages=extra_pages)


def check(plan: Dict[str, Any]) -> List[str]:
    """Light contract checks a lane can run without the shared validator."""
    try:
        _assert_waits_resolve(plan)
    except LaunchPlanError as exc:
        return [str(exc)]
    errors = []
    if not plan.get("pages"):
        errors.append("the plan has no pages")
    for unit in plan.get("email_sequences", []) + plan.get("text_sets", []) \
            + plan.get("automations", []):
        if unit.get("draft_only") is not True:
            errors.append(f"{unit.get('id')}: is not draft_only")
    ai = plan.get("conversation_ai") or {}
    if bool(ai.get("requested")) != (ai.get("mode") not in (None, "none")):
        errors.append("conversation_ai requested and mode disagree")
    event = plan.get("event") or {}
    if event.get("eligible") is False:
        present = {u.get("id") for array in ("text_sets", "automations")
                   for u in plan.get(array, [])}
        for unit_id in EVENT_UNIT_IDS:
            if unit_id in present:
                errors.append(f"{unit_id}: event unit planned for an ineligible event")
    access = plan.get("access") or {}
    if access and not access.get("resolved"):
        errors.append("access: welcome/access actions have no usable approved destination")
    for unit in plan.get("email_sequences", []) + plan.get("text_sets", []) \
            + plan.get("automations", []):
        if unit.get("id") in ("email_welcome_access", "text_access_link", "auto_post_sale") \
                and access and unit.get("access_destination") != access.get("destination"):
            errors.append(f"{unit.get('id')}: access destination disagrees with the plan")
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> int:
    ok = True

    def say(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    launch = {
        "launch_id": "demo-2026-11", "journey_mode": "single_simple",
        "extras": {"upsell_1": True, "downsell_1": False, "upsell_2": False},
        "offers": [
            {"offer_id": "MAIN-A", "slot": "main", "display_name": "Demo Offer",
             "entitlement_ids": ["base-a"],
             "prices": [{"price_choice_id": "MAIN-A-USD", "amount_minor": 49700,
                         "currency": "USD", "billing_type": "one_time",
                         "schedule": [], "approval_status": "provided"}]},
            {"offer_id": "U1", "slot": "upsell_1", "display_name": "Demo Upgrade",
             "entitlement_ids": ["upgrade-b"],
             "prices": [{"price_choice_id": "U1-USD", "amount_minor": 9900,
                         "currency": "USD", "billing_type": "one_time",
                         "schedule": [], "approval_status": "provided"}]},
        ],
    }
    answers = {
        "launch.launch_at": {"value": "2026-11-03T12:00:00-05:00", "state": "provided"},
        "launch.doors_open_at": {"value": "2026-11-03T09:00:00-05:00", "state": "provided"},
        "launch.doors_close_at": {"value": "2026-11-10T23:59:00-05:00", "state": "provided"},
        "launch.timezone": {"value": "America/New_York", "state": "provided"},
        "launch.channels": {"value": ["email", "text"], "state": "provided"},
        "launch.a2p_ready": {"value": False, "state": "provided"},
        "launch.conversation_ai": {"value": False, "state": "provided"},
        "launch.product_type": {"value": "self_paced", "state": "provided"},
        "launch.access_url": {"value": "https://example.test/access", "state": "provided"},
    }
    result = build_launch_plan(launch, answers)
    say(result["state"] == "ready", "a complete launch plan assembles")
    plan = result["plan"]
    for key in ("pages", "email_sequences", "text_sets", "automations",
                "conversation_ai", "launch_calendar", "a2p_ready"):
        say(key in plan, f"the plan carries {key} (checklist L1)")
    say(plan["conversation_ai"] == {"requested": False, "mode": "none"},
        "AI not requested is recorded, never built")
    say(not any(a["family"] == "conversation_ai_reply" for a in plan["automations"]),
        "no AI reply workflow when AI was not requested")
    say(all(t["draft_only"] for t in plan["text_sets"]) and plan["a2p_ready"] is False,
        "A2P not ready: texts stay drafts")
    say(not any(a["family"] == "failed_payment" for a in plan["automations"]),
        "no failed-payment automation without payment plans")
    say(any(e["id"].startswith("email_upsell_") for e in plan["email_sequences"]),
        "one upsell follow-up per upsell page")
    say(check(plan) == [], "waits_for edges all resolve")
    say([p["offer_id"] for p in plan["offer"]["packages"]] == ["MAIN-A", "U1"],
        "offer and price ids are copied per package, never invented")
    say([p["amount_minor"] for p in plan["offer"]["packages"] if p["slot"] == "main"] == [49700]
        and plan["offer"]["packages"][0]["price_id"] == "MAIN-A-USD",
        "each package keeps its own exact minor units (no lowest-price collapse)")
    say(plan["event"]["eligible"] is False and
        not any(u["id"] in ("text_event_reminder", "auto_event_reminders")
                for a in ("text_sets", "automations") for u in plan[a]),
        "a self-paced product plans no webinar, reminder, replay or no-show units")
    say(plan["access"]["resolved"] is True and
        plan["access"]["destination"] == "https://example.test/access" and
        "base-a" in plan["access"]["entitlements"] and
        "upgrade-b" in plan["access"]["entitlements"],
        "the welcome/access actions resolve the approved destination and every entitlement")

    no_calendar = {k: v for k, v in answers.items() if not k.startswith("launch.launch")}
    blocked = build_launch_plan(launch, no_calendar)
    say(blocked["state"] == "awaiting_missing_fact" and
        any("launch_at" in m for m in blocked["missing"]),
        "a missing launch date blocks the plan by name; no deadline is invented")

    email_only = dict(answers, **{"launch.channels": {"value": ["email"], "state": "provided"}})
    p2 = build_launch_plan(launch, email_only)["plan"]
    say(p2["text_sets"] == [], "email-only launch plans no texts")

    ai = dict(answers, **{
        "launch.conversation_ai": {"value": True, "state": "provided"},
        "launch.conversation_ai_mode": {"value": "checkout", "state": "provided"},
        "offers.main.payment_plans": {"value": True, "state": "provided"},
    })
    p3 = build_launch_plan(launch, ai)["plan"]
    say(p3["conversation_ai"]["requested"] is True and
        p3["conversation_ai"]["mode"] == "checkout", "requested AI keeps its mode")
    say(any(a["family"] == "conversation_ai_reply" for a in p3["automations"]),
        "requested AI adds the reply workflow")
    say(any(a["family"] == "failed_payment" for a in p3["automations"]),
        "payment plans add the failed-payment automation")
    say(check(p3) == [], "the AI + plans plan still has resolving waits")

    ai_no_mode = {k: v for k, v in ai.items() if k != "launch.conversation_ai_mode"}
    say(build_launch_plan(launch, ai_no_mode)["state"] == "awaiting_missing_fact",
        "requested AI without a mode blocks the plan")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Build the full launch plan (pages, emails, texts, automations, AI).")
    ap.add_argument("--launch", help="assembled launch record (launch.json)")
    ap.add_argument("--answers", help="intake answer ledger or plain answers JSON")
    ap.add_argument("--session", help="launch_intake session JSON (uses its plan + answers)")
    ap.add_argument("--landing-pages")
    ap.add_argument("--extra", action="append", default=[])
    ap.add_argument("--out", help="write the plan JSON here instead of stdout")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    try:
        if args.session:
            from launch_intake import load_session  # local import: no cycle at module load
            result = build_from_session(
                load_session(Path(args.session)),
                landing_pages=args.landing_pages.split(",") if args.landing_pages else None,
                extra_pages=args.extra)
        elif args.launch and args.answers:
            result = build_launch_plan(
                _load(args.launch), _load(args.answers),
                landing_pages=args.landing_pages.split(",") if args.landing_pages else None,
                extra_pages=args.extra)
        else:
            print("USAGE ERROR: pass --session, or --launch with --answers (or --self-test).")
            return EXIT_USAGE
    except (LaunchPlanError, ps.PageSetError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_FAILCLOSED
    if result["state"] != "ready":
        print("FAIL: the launch plan is missing facts: " + "; ".join(result["missing"]))
        return EXIT_FAILCLOSED
    text = json.dumps(result["plan"], indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"launch plan written to {args.out}")
    else:
        print(text, end="")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
