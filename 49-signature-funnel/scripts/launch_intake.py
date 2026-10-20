#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""launch_intake.py — guided launch interview + plan assembly for Skill 49's
`signature_launch` mode (spec 06 S49-03; experience law doc 03).

RELATIONSHIP TO SKILL 6 (doc 03 §2 — reuse, do not duplicate): this machine
deliberately reuses the interaction machinery of Skill 6's
`tools/intake_interview.py`, read in full before this was written: the Question
shape (qid, plain text, hint, pre-existing-answer keys, options), inference
precedence (an answer already known is never asked again), option
normalisation, the required-answer re-ask, and the "you decide / think for me"
trigger that maps to doc 03's recommendation modes. What Skill 6's interview
cannot carry — and why this is a launch profile built on the same machinery
rather than a fork of it — is everything the launch domain adds: a DURABLE
session (pause/resume with recap, every answer saved immediately), a per-field
PROVENANCE ledger (provided / verified_existing / recommended_unapproved /
approved_recommendation / unknown / not_applicable), deterministic
recommendation RULES (no model improvisation on commercial facts), plan
assembly bound to a compiled route graph, and an approval gate.

STATE MACHINE (doc 03 §3):
  collecting -> recommendation_ready -> awaiting_plan_approval -> approved
             -> building
  side states: paused, awaiting_missing_fact, revision_requested, cancelled.

One focused question per turn; at most three short choices including the
client's own answer. A volunteered answer may fill several fields at once and
is echoed, not re-asked. An enabled chargeable slot may never carry an
unknown product, price, or fulfillment promise: plan assembly stops at
awaiting_missing_fact and names what is missing. Unknown price is recorded
`unknown` — never zero. Recommendations are proposals until the plan is
approved; choosing recommendation mode never approves anything.

Approval (doc 03 §9): `approve()` runs validate_launch_plan's
assert_plan_build_approved — the record must be type launch_plan_build, bind
the exact current plan hash, come from the launch's client identity (never
the worker operating the run), carry the platform reference of the client's
own response message, and not be revoked or expired.

Deterministic, stdlib only, no network, no model. Exit 0/2/3 as usual.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_launch_route as clr  # noqa: E402
import launch_plan as lpl  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "intake" / "launch-questions.json"

FIELD_STATES = ("provided", "verified_existing", "recommended_unapproved",
                "approved_recommendation", "unknown", "not_applicable")
MODES = ("know", "help", "choose_for_me")
STATES = ("collecting", "recommendation_ready", "awaiting_plan_approval",
          "approved", "building", "paused", "awaiting_missing_fact",
          "revision_requested", "cancelled")
_MODE_FROM_CHOICE = {"i know what i want": "know", "help me choose": "help",
                     "choose a setup for me to review": "choose_for_me"}
_THINK_FOR_ME = ("you decide", "think for me", "up to you", "whatever you think",
                 "you choose", "your call", "i don't know", "not sure", "unsure")


class IntakeError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(text: Any) -> str:
    return " ".join(str(text or "").casefold().split())


def load_question_bank(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    data = json.loads((path or QUESTIONS_PATH).read_text(encoding="utf-8"))
    return data["questions"]


# ---------------------------------------------------------------------------
# Session.
# ---------------------------------------------------------------------------
def new_session(*, tenant_id: str, location_id: str, launch_id: str,
                client_identity_ref: str, brand_ref: str = "",
                brand_hash: str = "", known: Optional[Dict[str, Any]] = None,
                materials: Optional[List[Dict[str, Any]]] = None,
                available_providers: Optional[List[str]] = None,
                test_only: bool = False) -> Dict[str, Any]:
    """Create a session. `known` pre-fills fields from supplied/verified
    material (S6 task-key style) — those fields are NEVER asked again.
    `materials` is the client's existing verified catalog, the only source a
    recommendation may draw products from."""
    s: Dict[str, Any] = {
        "schema": "signature-launch-intake/v1",
        "session_id": uuid.uuid4().hex[:12],
        "tenant_id": tenant_id, "location_id": location_id,
        "launch_id": launch_id, "client_identity_ref": client_identity_ref,
        "brand_ref": brand_ref, "brand_hash": brand_hash,
        "state": "collecting", "phase": "A", "mode": None,
        "answers": {}, "materials": materials or [],
        "available_providers": available_providers or [],
        "plan_revision": 1, "plan": None, "plan_hash": None,
        "approval": None, "history": [{"at": _now(), "event": "created"}],
        "test_only": test_only,
    }
    for field_key, entry in (known or {}).items():
        if isinstance(entry, dict) and "value" in entry:
            s["answers"][field_key] = {
                "value": entry["value"],
                "state": entry.get("state", "verified_existing"),
                "source_ref": entry.get("source_ref", "supplied-material"),
                "question_id": None}
        else:
            s["answers"][field_key] = {
                "value": entry, "state": "verified_existing",
                "source_ref": "supplied-material", "question_id": None}
    return s


def _client_intake():
    """shared-utils/client_intake/engine.py: the repo checkout first, then the installed skills tree."""
    here = Path(__file__).resolve()
    for d in [p / "shared-utils" / "client_intake" for p in here.parents] + [
            Path.home() / ".openclaw" / "skills" / "shared-utils" / "client_intake",
            Path("/data/.openclaw/skills/shared-utils/client_intake")]:
        if (d / "engine.py").is_file():
            sys.path.insert(0, str(d))
            import engine  # noqa: E402
            return engine
    raise IntakeError("shared-utils/client_intake not found; install or update the onboarding skills")


def ingest_answers(session: Dict[str, Any], answers: Dict[str, Any],
                   brand_file: Optional[Path] = None) -> Dict[str, Any]:
    """Fill the session from the one client answers file (client-intake-answers/v1), so the same answers
    given in any harness never get asked again. A default or suggestion enters as recommended_unapproved,
    never as approved. brand_ref and brand_hash come from the brand file the answers produced (Skill 71
    brand_colors.py record-answers); without that file the brand question stays open."""
    for field_key, entry in _client_intake().to_launch_known(answers).items():
        session["answers"][field_key] = {"value": entry["value"], "state": entry["state"],
                                         "source_ref": entry["source_ref"], "question_id": None}
    mode = (session["answers"].get("interview.mode") or {}).get("value")
    if mode in MODES:
        session["mode"] = mode
    if brand_file is not None:
        bf = Path(brand_file)
        session["brand_ref"] = str(bf)
        session["brand_hash"] = hashlib.sha256(bf.read_bytes()).hexdigest()
        _set(session, "brand_ref", session["brand_ref"], "verified_existing", "d1_brand", "answers-file")
    session["history"].append({"at": _now(), "event": "answers_file_ingested"})
    _persist(session)
    return session


def save_session(session: Dict[str, Any], path: Path) -> None:
    session["_path"] = str(path)
    tmp = {k: v for k, v in session.items()}
    path.write_text(json.dumps(tmp, indent=2) + "\n", encoding="utf-8")


def load_session(path: Path) -> Dict[str, Any]:
    s = json.loads(path.read_text(encoding="utf-8"))
    s["_path"] = str(path)
    return s


def _persist(session: Dict[str, Any]) -> None:
    if session.get("_path"):
        save_session(session, Path(session["_path"]))


def _set(session: Dict[str, Any], field_key: str, value: Any, state: str,
         question_id: Optional[str], source_ref: str = "") -> None:
    if state not in FIELD_STATES:
        raise IntakeError(f"unknown field state {state!r}")
    session["answers"][field_key] = {"value": value, "state": state,
                                     "source_ref": source_ref,
                                     "question_id": question_id}


def _get(session: Dict[str, Any], field_key: str) -> Optional[Dict[str, Any]]:
    return session["answers"].get(field_key)


def _answered(session: Dict[str, Any], field_key: str) -> bool:
    e = _get(session, field_key)
    return e is not None and e["state"] != "unknown"


# ---------------------------------------------------------------------------
# Question flow — one question per turn, conditions evaluated on the ledger.
# ---------------------------------------------------------------------------
def _condition_met(session: Dict[str, Any], q: Dict[str, Any]) -> bool:
    cond = q.get("condition", "always")
    if cond == "always":
        return True
    if cond == "extras.upsell_1 == true":
        ex = _get(session, "extras")
        return bool(ex and ex["value"].get("upsell_1"))
    if cond == "after:b2_price":
        # Asked once the price question has been TOUCHED, even when the
        # price itself is still unknown (billing shape is a separate fact).
        return _get(session, "offers.main.price") is not None
    if cond == "plan_ready":
        return session.get("plan") is not None
    return True


def _question_targets_done(session: Dict[str, Any], q: Dict[str, Any]) -> bool:
    targets = q.get("targets", [])
    return bool(targets) and all(_answered(session, t) for t in targets)


def next_question(session: Dict[str, Any],
                  bank: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """The ONE next question, or None when the interview has all it needs.
    Never returns a question whose targets are already answered (supplied
    facts are not asked twice) or whose condition fails (disabled slots are
    skipped)."""
    if session["state"] in ("cancelled", "approved", "building"):
        return None
    bank = bank if bank is not None else load_question_bank()
    asked_ids = set(session.get("asked_ids", []))
    for q in bank:
        if q["id"] == "e1_plan_review":
            continue  # asked only via present_plan()
        if q["id"] in asked_ids:
            continue  # one turn per question; gaps surface at plan assembly
        if not _condition_met(session, q):
            continue
        if _question_targets_done(session, q):
            continue
        return {"id": q["id"], "phase": q["phase"], "prompt": q["prompt"],
                "choices": q.get("choices", []), "reason": q.get("reason", "")}
    return None


def _match_choice(raw: str, choices: List[str]) -> Optional[str]:
    n = _norm(raw)
    for c in choices:
        if _norm(c) == n:
            return c
    for c in choices:
        if n.startswith(_norm(c)) or _norm(c) in n:
            return c
    return None


def answer(session: Dict[str, Any], question_id: str, raw: str,
           value: Optional[Dict[str, Any]] = None,
           source_message_ref: str = "") -> Dict[str, Any]:
    """Record one answer. `value` carries structured payloads (amounts,
    packages, offer details) — a single volunteered answer may fill several
    fields at once. Every answer is saved immediately."""
    if session["state"] == "cancelled":
        raise IntakeError("this intake was cancelled; answers are no longer accepted")
    bank = {q["id"]: q for q in load_question_bank()}
    q = bank.get(question_id)
    if q is None:
        raise IntakeError(f"unknown question {question_id!r}")
    value = value or {}
    # A volunteered multi-field payload fills its fields first (echoed, not
    # re-asked) — states default to provided.
    for field_key, fv in (value.get("fields") or {}).items():
        if isinstance(fv, dict) and "value" in fv:
            _set(session, field_key, fv["value"], fv.get("state", "provided"),
                 question_id, source_message_ref)
        else:
            _set(session, field_key, fv, "provided", question_id, source_message_ref)

    session.setdefault("asked_ids", []).append(question_id)
    handler = _HANDLERS.get(question_id)
    if handler is not None:
        handler(session, q, raw, value, source_message_ref)
    elif not any(t in session["answers"] for t in q.get("targets", [])):
        for t in q.get("targets", []):
            _set(session, t, raw, "provided", question_id, source_message_ref)

    # Think-for-me phrasing anywhere selects recommendation help (doc 03 §1:
    # the client does not repeat the request at every step).
    if any(p in _norm(raw) for p in _THINK_FOR_ME) and session.get("mode") == "know":
        session["mode"] = "help"
    session["phase"] = q["phase"]
    session["history"].append({"at": _now(), "event": "answer",
                               "question_id": question_id})
    if session["state"] == "revision_requested":
        session["state"] = "collecting"
    _persist(session)
    return session


# --- per-question handlers -------------------------------------------------
def _h_mode(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"]) or raw
    s["mode"] = _MODE_FROM_CHOICE.get(_norm(choice), "help")
    _set(s, "interview.mode", s["mode"], "provided", q["id"], ref)


def _h_free_text(s, q, raw, value, ref):
    for t in q["targets"]:
        if t not in s["answers"]:
            _set(s, t, value.get(t, raw), "provided", q["id"], ref)


def _h_proof(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"])
    if choice and _norm(choice) == "none yet":
        _set(s, "proof", None, "not_applicable", q["id"], ref)
    else:
        _set(s, "proof", value.get("proof", raw), "provided", q["id"], ref)


def _recommend_journey(s) -> str:
    text = _norm((_get(s, "offers.main.description") or {}).get("value", "")) + " " + \
        _norm(" ".join(map(str, (_get(s, "offers.main.deliverables") or {})
                           .get("value", []) or [])))
    for token in ("package", "tier", "level", "vip", "premium", "pass"):
        if token in text:
            return "multiple_options"
    return "single_simple"


def _h_journey(s, q, raw, value, ref):
    if "packages" in value:
        # The packages themselves (names, contents, prices) — a
        # multiple_options plan is built from these, never invented.
        _set(s, "offers.main.packages", value["packages"], "provided",
             q["id"], ref)
    if _answered(s, "journey_mode"):
        return
    choice = _match_choice(raw, q["choices"])
    if "journey_mode" in value:
        _set(s, "journey_mode", value["journey_mode"], "provided", q["id"], ref)
    elif choice and _norm(choice) == "one offer":
        _set(s, "journey_mode", "single_simple", "provided", q["id"], ref)
    elif choice and _norm(choice) == "a few packages":
        _set(s, "journey_mode", "multiple_options", "provided", q["id"], ref)
    else:  # help me decide / think-for-me
        _set(s, "journey_mode", _recommend_journey(s), "recommended_unapproved",
             q["id"], ref)


def _h_price(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"])
    if "amount_minor" in value:
        _set(s, "offers.main.price",
             {"amount_minor": value["amount_minor"],
              "currency": value.get("currency", "USD")}, "provided", q["id"], ref)
    elif choice and _norm(choice) == "it is free":
        _set(s, "offers.main.price", {"amount_minor": 0, "currency": "USD"},
             "provided", q["id"], ref)
    elif choice and _norm(choice).startswith("suggest"):
        # A suggestion is a proposal with a stated rationale, never a fact.
        if "suggested_amount_minor" in value:
            _set(s, "offers.main.price",
                 {"amount_minor": value["suggested_amount_minor"],
                  "currency": value.get("currency", "USD"),
                  "rationale": value.get("rationale", "")},
                 "recommended_unapproved", q["id"], ref)
        else:
            _set(s, "offers.main.price", None, "unknown", q["id"], ref)
    else:
        _set(s, "offers.main.price", None, "unknown", q["id"], ref)


def _h_billing(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"]) or raw
    mapping = {"all at once": "one_time", "monthly": "recurring",
               "in parts / trial first": "installment"}
    bt = value.get("billing_type") or mapping.get(_norm(choice), "one_time")
    _set(s, "offers.main.billing_type", bt, "provided", q["id"], ref)
    _set(s, "offers.main.schedule", value.get("schedule", []), "provided",
         q["id"], ref)


def _unused_candidate(s, used_names: set) -> Optional[Dict[str, Any]]:
    for m in s.get("materials", []):
        if isinstance(m, dict) and m.get("name") and m["name"] not in used_names:
            return m
    return None


def _make_extra_handler(slot: str, extras_key: Optional[str]):
    def handler(s, q, raw, value, ref):
        field = f"offers.{slot}"
        choice = _match_choice(raw, q["choices"]) or ""
        n = _norm(choice)
        offer_payload = value.get(slot) or value.get("offer")
        if offer_payload:
            _set(s, field, offer_payload, "provided", q["id"], ref)
            enabled = True
        elif n.startswith("no") or "no add-on" in n or "no upgrade" in n \
                or "no downsell" in n or "no second upsell" in n:
            _set(s, field, None, "not_applicable", q["id"], ref)
            enabled = False
        elif "recommend" in n:
            used = set()
            main = _get(s, "offers.main.description")
            if main:
                used.add(_norm(main["value"]))
            for other in ("bump", "upsell_1", "downsell_1", "upsell_2"):
                e = _get(s, f"offers.{other}")
                if e and isinstance(e["value"], dict):
                    used.add(_norm(e["value"].get("display_name", "")))
            cand = _unused_candidate(s, used)
            if cand is not None:
                _set(s, field,
                     {"display_name": cand["name"],
                      "deliverables": cand.get("deliverables", []),
                      "price": cand.get("price"),
                      "assumption": "drawn from your existing catalog; "
                                    "confirm it is deliverable as offered"},
                     "recommended_unapproved", q["id"], ref)
                enabled = True
            else:
                # No suitable product in supplied facts: recommend none
                # rather than inventing one (doc 03 §6).
                _set(s, field, None, "not_applicable", q["id"], ref)
                enabled = False
        else:
            _set(s, field, {"description": raw}, "provided", q["id"], ref)
            enabled = True
        if extras_key:
            ex = dict((_get(s, "extras") or {}).get("value") or
                      {"upsell_1": False, "downsell_1": False, "upsell_2": False})
            ex[extras_key] = enabled
            _set(s, "extras", ex, "provided", q["id"], ref)
        if slot == "bump":
            _set(s, "bump_enabled", enabled, "provided", q["id"], ref)
    return handler


def _h_brand(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"]) or ""
    if "brand_ref" in value:
        s["brand_ref"] = value["brand_ref"]
        s["brand_hash"] = value.get("brand_hash", s.get("brand_hash", ""))
        _set(s, "brand_ref", value["brand_ref"], "verified_existing", q["id"], ref)
    elif _norm(choice) in ("some are missing", "help me check"):
        # never assume the brand is saved: unknown until the colors, logo and photos are answered
        # (shared-utils/client_intake asks them, with help) and a brand file exists
        _set(s, "brand_ref", None, "unknown", q["id"], ref)
    else:
        _set(s, "brand_ref", s.get("brand_ref") or "existing-brand",
             "verified_existing", q["id"], ref)


def _h_copy_profile(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"]) or ""
    n = _norm(choice)
    if n == "standard":
        _set(s, "copy_profile", "standard", "provided", q["id"], ref)
    elif n == "long-form":
        _set(s, "copy_profile", "long_form", "provided", q["id"], ref)
    else:
        deliverables = (_get(s, "offers.main.deliverables") or {}).get("value") or []
        rec = "long_form" if len(deliverables) >= 6 else "standard"
        _set(s, "copy_profile", rec, "recommended_unapproved", q["id"], ref)


def _h_location(s, q, raw, value, ref):
    _set(s, "location_binding",
         {"choice": raw, "location_id": s["location_id"],
          "note": "IDs come from verified access (S06), not recitation"},
         "provided", q["id"], ref)


def _h_image_provider(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"]) or ""
    providers = s.get("available_providers", [])
    if "image_provider" in value:
        _set(s, "image_provider", value["image_provider"], "provided", q["id"], ref)
    elif _norm(choice) == "no images needed":
        _set(s, "image_provider", "other_explicit", "provided", q["id"], ref)
    elif _norm(choice) == "my connected service" and providers:
        _set(s, "image_provider", providers[0], "verified_existing", q["id"], ref)
    elif providers:
        _set(s, "image_provider", providers[0], "recommended_unapproved",
             q["id"], ref)
    else:
        _set(s, "image_provider", None, "unknown", q["id"], ref)


def _h_budget(s, q, raw, value, ref):
    choice = _match_choice(raw, q["choices"]) or ""
    if _norm(choice) == "no paid pieces":
        _set(s, "paid_asset_budget", None, "not_applicable", q["id"], ref)
    elif "cap_minor" in value:
        _set(s, "paid_asset_budget",
             {"cap_minor": value["cap_minor"], "currency": value.get("currency", "USD"),
              "approval": "separate paid_asset_budget approval required"},
             "provided", q["id"], ref)
    else:
        _set(s, "paid_asset_budget", None, "unknown", q["id"], ref)


_HANDLERS = {
    "m0_mode": _h_mode, "a1_offer": _h_free_text, "a2_transformation": _h_free_text,
    "a3_pains": _h_free_text, "a4_deliverables": _h_free_text, "a5_proof": _h_proof,
    "b1_journey": _h_journey, "b2_price": _h_price, "b3_billing": _h_billing,
    "c1_bump": _make_extra_handler("bump", None),
    "c2_u1": _make_extra_handler("upsell_1", "upsell_1"),
    "c3_d1": _make_extra_handler("downsell_1", "downsell_1"),
    "c4_u2": _make_extra_handler("upsell_2", "upsell_2"),
    "d1_brand": _h_brand, "d2_copy_profile": _h_copy_profile,
    "d3_location": _h_location, "d4_image_provider": _h_image_provider,
    "d5_budget": _h_budget,
}


# ---------------------------------------------------------------------------
# Plan assembly.
# ---------------------------------------------------------------------------
def _money_display(amount_minor: Optional[int], currency: str) -> str:
    if amount_minor is None:
        return "price not set yet"
    if amount_minor == 0:
        return "free"
    return f"{currency} {amount_minor / 100:,.2f}"


def _offer_from_answers(session: Dict[str, Any], slot: str, field: str,
                        offer_id: str) -> Optional[Dict[str, Any]]:
    e = _get(session, field)
    if e is None or e["state"] == "not_applicable" or e["value"] is None:
        return None
    v = e["value"]
    if slot == "main":
        price_e = _get(session, "offers.main.price")
        price = price_e["value"] if price_e else None
        billing = (_get(session, "offers.main.billing_type") or {}).get("value",
                                                                       "one_time")
        schedule = (_get(session, "offers.main.schedule") or {}).get("value", [])
        display = value_name = None
        if isinstance(v, dict):
            display = v.get("display_name") or v.get("description")
            deliverables = v.get("deliverables", [])
        else:
            display = str(v)
            deliverables = (_get(session, "offers.main.deliverables") or {}) \
                .get("value", []) or []
        amount = price.get("amount_minor") if isinstance(price, dict) else None
        status = "approved" if e["state"] == "approved_recommendation" else (
            "recommended_unapproved" if price_e and
            price_e["state"] == "recommended_unapproved" else
            "unknown" if amount is None else "provided")
        return {"offer_id": offer_id, "slot": "main",
                "display_name": display or offer_id,
                "deliverables": list(deliverables), "exclusions": [],
                "entitlement_ids": [offer_id.lower()], "requires": [],
                "excludes": [], "native_product_id": None,
                "prices": [{"price_choice_id": f"{offer_id}-USD",
                            "currency": (price or {}).get("currency", "USD"),
                            "amount_minor": amount, "billing_type": billing,
                            "native_price_id": None, "schedule": list(schedule),
                            "terms_source": None, "approval_status": status}],
                "source_kind": "test_fixture" if session.get("test_only") else "owner",
                "source_ref": f"intake:{session['session_id']}",
                "test_only": bool(session.get("test_only"))}
    if not isinstance(v, dict) or not v.get("display_name"):
        return {"offer_id": offer_id, "slot": slot, "_incomplete": True}
    price = v.get("price") or {}
    amount = price.get("amount_minor") if isinstance(price, dict) else None
    return {"offer_id": offer_id, "slot": slot,
            "display_name": v["display_name"],
            "deliverables": list(v.get("deliverables", [])), "exclusions": [],
            "entitlement_ids": [offer_id.lower()], "requires": [],
            "excludes": [], "native_product_id": None,
            "prices": [{"price_choice_id": f"{offer_id}-USD",
                        "currency": price.get("currency", "USD")
                        if isinstance(price, dict) else "USD",
                        "amount_minor": amount, "billing_type": "one_time",
                        "native_price_id": None, "schedule": [],
                        "terms_source": None,
                        "approval_status": "recommended_unapproved"
                        if e["state"] == "recommended_unapproved" else
                        "unknown" if amount is None else "provided"}],
            "source_kind": "test_fixture" if session.get("test_only") else
            ("recommendation" if e["state"] == "recommended_unapproved" else "owner"),
            "source_ref": f"intake:{session['session_id']}",
            "test_only": bool(session.get("test_only"))}


def _package_offers(session: Dict[str, Any],
                    missing: List[str]) -> List[Dict[str, Any]]:
    """The main offers of a multiple_options plan, built ONLY from packages
    the client actually supplied (review D2: assembly previously emitted
    exactly one main offer, so a multiple_options approval could be spent
    on a plan dispatch would always refuse). Fewer than two named, priced
    packages is a missing fact, not an improvisation prompt."""
    e = _get(session, "offers.main.packages")
    pkgs = e["value"] if e else None
    if not isinstance(pkgs, list) or len(pkgs) < 2:
        missing.append("the packages for the selection page — a few-packages "
                       "launch needs at least two packages, each with a name "
                       "and a price")
        return []
    out: List[Dict[str, Any]] = []
    for i, pkg in enumerate(pkgs):
        oid = f"MAIN-{chr(65 + i)}"
        if not isinstance(pkg, dict) or not (pkg.get("display_name")
                                             or pkg.get("name")):
            missing.append(f"package {i + 1} has no name")
            continue
        name = pkg.get("display_name") or pkg.get("name")
        price = pkg.get("price") if isinstance(pkg.get("price"), dict) else {}
        amount = price.get("amount_minor", pkg.get("amount_minor"))
        if amount is None:
            missing.append(f"price for package {name} (unknown is not a price)")
        status = pkg.get("price_status") or (
            "recommended_unapproved" if e["state"] == "recommended_unapproved"
            else "unknown" if amount is None else "provided")
        out.append({
            "offer_id": oid, "slot": "main", "display_name": name,
            "deliverables": list(pkg.get("deliverables", [])), "exclusions": [],
            "entitlement_ids": [oid.lower()], "requires": [], "excludes": [],
            "native_product_id": None,
            "prices": [{"price_choice_id": f"{oid}-USD",
                        "currency": price.get("currency", "USD"),
                        "amount_minor": amount, "billing_type": "one_time",
                        "native_price_id": None, "schedule": [],
                        "terms_source": None, "approval_status": status}],
            "source_kind": "test_fixture" if session.get("test_only") else "owner",
            "source_ref": f"intake:{session['session_id']}",
            "test_only": bool(session.get("test_only"))})
    return out


def assemble_plan(session: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the launch record + compiled route graph from the ledger.
    Stops at awaiting_missing_fact when an enabled chargeable slot lacks a
    product, a known price, or fulfillment — never fills them in. The
    assembled record must ALSO pass the domain validator before it can be
    presented: an invalid plan never consumes a client approval (D2)."""
    missing: List[str] = []
    journey = (_get(session, "journey_mode") or {}).get("value")
    if not journey:
        missing.append("journey_mode (one offer or a few packages)")
        journey = "single_simple"
    extras = dict((_get(session, "extras") or {}).get("value") or
                  {"upsell_1": False, "downsell_1": False, "upsell_2": False})

    offers: List[Dict[str, Any]] = []
    if journey in ("multiple_options", "folded_levels"):  # levels are named, priced mains too; no invented ones
        offers.extend(_package_offers(session, missing))
    else:
        main = _offer_from_answers(session, "main", "offers.main.description",
                                   "MAIN")
        if main is None:
            missing.append("main offer (what is being sold)")
        else:
            p = main["prices"][0]
            if p["amount_minor"] is None:
                missing.append("main offer price (unknown is not a price)")
            offers.append(main)
    slot_ids = {"bump": "BUMP", "upsell_1": "U1", "downsell_1": "D1",
                "upsell_2": "U2"}
    for slot, oid in slot_ids.items():
        enabled = (_get(session, "bump_enabled") or {}).get("value") \
            if slot == "bump" else extras.get(slot)
        e = _get(session, f"offers.{slot}")
        if not enabled:
            continue
        o = _offer_from_answers(session, slot, f"offers.{slot}", oid)
        if o is None or o.pop("_incomplete", False):
            missing.append(f"{slot} is enabled but its product is not defined")
            continue
        if o["prices"][0]["amount_minor"] is None:
            missing.append(f"{slot} price (an enabled slot may not charge an "
                           "unknown amount)")
        offers.append(o)
    # Declared mutual exclusion between U1 and D1 (validator law).
    ids = {o["slot"]: o["offer_id"] for o in offers}
    for o in offers:
        if o["slot"] == "upsell_1" and "downsell_1" in ids:
            o["excludes"] = [ids["downsell_1"]]
        if o["slot"] == "downsell_1" and "upsell_1" in ids:
            o["excludes"] = [ids["upsell_1"]]
    brand_e = _get(session, "brand_ref")
    if brand_e is not None and brand_e["state"] == "unknown":
        missing.append("brand assets (logo / colors / founder photo)")

    launch: Dict[str, Any] = {
        "schema_version": "1.0", "tenant_id": session["tenant_id"],
        "location_id": session["location_id"], "launch_id": session["launch_id"],
        "revision": session["plan_revision"], "journey_mode": journey,
        "status": "collecting",
        "brand_ref": session.get("brand_ref") or "pending",
        "brand_hash": session.get("brand_hash") or "pending",
        "route_graph_ref": "", "route_graph_hash": "",
        "plan_approval_ref": None, "offers": offers, "extras": extras,
        "bump_enabled": bool((_get(session, "bump_enabled") or {}).get("value")),
        "image_provider": (_get(session, "image_provider") or {})
        .get("value") or "other_explicit",
        "source_refs": [f"intake-session:{session['session_id']}"],
        "test_only": bool(session.get("test_only")),
    }
    if missing:
        session["state"] = "awaiting_missing_fact"
        session["missing_facts"] = missing
        session["plan"] = None
        _persist(session)
        return {"state": "awaiting_missing_fact", "missing": missing}
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = f"route-graph:{launch['launch_id']}:rev{launch['revision']}"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    launch["status"] = "awaiting_plan_approval"
    # Domain validation is the last gate before presentation (D2 backstop):
    # any violation is a fact the plan still lacks, never an approval spent
    # on an unbuildable plan.
    violations = vlp.validate_launch(launch)
    if violations:
        missing.extend(f"plan validation: {v}" for v in violations)
        session["state"] = "awaiting_missing_fact"
        session["missing_facts"] = missing
        session["plan"] = None
        _persist(session)
        return {"state": "awaiting_missing_fact", "missing": missing}
    session["plan"] = launch
    session["route_graph"] = graph
    session["plan_hash"] = plan_hash(launch)
    # The FULL launch plan (pages + emails + texts + automations + AI choice) is
    # planned beside the launch record, in the shared launch-plan contract. A
    # missing calendar/AI fact never blocks the page plan; it is named, and the
    # page-level launch still proceeds to its own approval.
    try:
        full = lpl.build_from_session(session)
        session["launch_plan"] = full.get("plan")
        session["launch_plan_missing"] = full.get("missing", [])
    except (lpl.LaunchPlanError, ValueError) as exc:
        # PageSetError / RouteError are ValueErrors; a full-plan defect is named,
        # never allowed to block the page plan that was already validated above.
        session["launch_plan"] = None
        session["launch_plan_missing"] = [f"full launch plan: {exc}"]
    # Doc 03 §3 state machine (D4): a plan built on recommendations passes
    # through recommendation_ready; a plan of only supplied facts goes
    # straight to awaiting_plan_approval.
    used_recommendations = any(
        entry["state"] == "recommended_unapproved"
        for entry in session["answers"].values())
    session["state"] = ("recommendation_ready" if used_recommendations
                        else "awaiting_plan_approval")
    session.pop("missing_facts", None)
    session["history"].append({"at": _now(), "event": "plan_assembled",
                               "plan_hash": session["plan_hash"],
                               "state": session["state"]})
    _persist(session)
    return {"state": session["state"], "plan": launch,
            "plan_hash": session["plan_hash"],
            "launch_plan": session.get("launch_plan"),
            "launch_plan_missing": session.get("launch_plan_missing", [])}


def plan_hash(launch: Dict[str, Any]) -> str:
    """The hash an approval binds to — the plan's CONTENT (offers, prices,
    route, revision, mode). Lifecycle fields (status, plan_approval_ref) are
    excluded by the canonical implementation in validate_launch_plan: status
    flips to approved BECAUSE the gate passed, so binding it would make the
    gate invalidate its own approval."""
    return vlp.plan_document_hash(launch)


def render_summary(session: Dict[str, Any]) -> str:
    """The plain-language plan (doc 03 §8) with REAL names and prices — no
    bracketed placeholders. Only callable once a plan exists."""
    plan = session.get("plan")
    if not plan:
        raise IntakeError("no plan has been assembled yet")
    by_slot = {o["slot"]: o for o in plan["offers"]}

    def price_of(o):
        p = o["prices"][0]
        return _money_display(p["amount_minor"], p["currency"])

    lines = ["Here is the launch I recommend."]
    lines.append("1. Your first page introduces the result. It does not show a price.")
    lines.append("2. Interested visitors leave their first name, last name, email and phone.")
    main = by_slot.get("main")
    if plan["journey_mode"] == "multiple_options":
        mains = [o for o in plan["offers"] if o["slot"] == "main"]
        named = ", ".join(f"{o['display_name']} ({price_of(o)})" for o in mains)
        lines.append(f"3. They compare your packages — {named} — then check out.")
    else:
        lines.append(f"3. They go straight to checkout for "
                     f"{main['display_name']} ({price_of(main)}).")
    bump = by_slot.get("bump")
    if bump:
        lines.append(f"4. At checkout they can add {bump['display_name']} "
                     f"({price_of(bump)}), or leave it out.")
    else:
        lines.append("4. At checkout there is no add-on.")
    u1, d1, u2 = by_slot.get("upsell_1"), by_slot.get("downsell_1"), by_slot.get("upsell_2")
    if u1 and d1:
        lines.append(f"5. After buying, they see {u1['display_name']} "
                     f"({price_of(u1)}). If they pass, they see "
                     f"{d1['display_name']} ({price_of(d1)}).")
    elif u1:
        lines.append(f"5. After buying, they see {u1['display_name']} "
                     f"({price_of(u1)}).")
    else:
        lines.append("5. After buying, there are no extra offers.")
    if u2:
        lines.append(f"6. Buyers who accept either can see {u2['display_name']} "
                     f"({price_of(u2)}).")
    lines.append("7. The final page confirms only what they actually bought "
                 "and gives access.")
    lines.extend(_launch_plan_lines(session))
    lines.append("I will prepare the approved emails and follow-up automations as drafts.")
    lines.append("Do you approve this plan for building, or would you like a change?")
    return "\n".join(lines)


def _launch_plan_lines(session: Dict[str, Any]) -> List[str]:
    """The rest of the launch in plain language: emails, texts, automations and
    the Conversation AI choice. Anything still missing is named so the client can
    answer it; nothing is filled in here."""
    plan = session.get("launch_plan")
    missing = session.get("launch_plan_missing") or []
    if not plan:
        if missing:
            return ["The full launch plan still needs: " + "; ".join(missing) + "."]
        return []
    emails = len(plan.get("email_sequences") or [])
    texts = len(plan.get("text_sets") or [])
    automations = len(plan.get("automations") or [])
    lines = [f"The same launch plans {emails} email sequences (drafts), "
             f"{texts} text sets (drafts) and {automations} automations (drafts)."]
    ai = plan.get("conversation_ai") or {}
    if ai.get("requested"):
        lines.append(f"Conversation AI is on ({ai.get('mode')}): when a contact replies, "
                     "the bot answers, books or sends the checkout link, as you chose.")
    else:
        lines.append("Conversation AI: not requested, so no bot is built.")
    if texts and not plan.get("a2p_ready"):
        lines.append("Texts stay drafts: A2P 10DLC registration is not approved yet, "
                     "so they cannot send until it is.")
    if (plan.get("launch_calendar") or {}).get("black_friday"):
        lines.append("Black Friday timing is included: teaser, countdown, doors open, "
                     "Cyber Monday and last call.")
    return lines


def present_plan(session: Dict[str, Any]) -> str:
    """Present the plan summary. From collecting, awaiting_missing_fact, or
    revision_requested it (re)assembles first — supplying the missing fact
    and asking for the plan again is the normal recovery path, never a dead
    end (review D3)."""
    if session["state"] in ("collecting", "awaiting_missing_fact",
                            "revision_requested"):
        result = assemble_plan(session)
        if result["state"] not in ("awaiting_plan_approval",
                                   "recommendation_ready"):
            raise IntakeError("plan is not ready: missing " +
                              "; ".join(result.get("missing", [])))
    if session["state"] == "recommendation_ready":
        session["state"] = "awaiting_plan_approval"
        session["history"].append({"at": _now(), "event": "plan_presented"})
        _persist(session)
    if session["state"] != "awaiting_plan_approval":
        raise IntakeError(f"no plan to present from state {session['state']!r}")
    return render_summary(session)


# ---------------------------------------------------------------------------
# Approval + lifecycle.
# ---------------------------------------------------------------------------
def approve(session: Dict[str, Any], approval: Dict[str, Any],
            *, worker_identity_ref: str) -> Dict[str, Any]:
    """Bind the client's approval to the exact plan. Runs the gate; on
    success the launch record flips to approved, recommended fields the plan
    used become approved_recommendation, and the session may build."""
    if session["state"] == "recommendation_ready" and session.get("plan"):
        # The approval act itself is the presentation acknowledgment: the
        # client is approving THIS hashed plan, recommendations included.
        session["state"] = "awaiting_plan_approval"
        session["history"].append({"at": _now(),
                                   "event": "plan_presented_via_approve"})
    if session["state"] != "awaiting_plan_approval" or not session.get("plan"):
        raise IntakeError("no plan is awaiting approval in this session")
    violations = vlp.validate_launch(session["plan"])
    if violations:
        raise IntakeError("plan no longer validates; refusing to spend an "
                          "approval on it: " + "; ".join(violations))
    assertion = vlp.assert_plan_build_approved(
        session["plan"], approval,
        client_identity_ref=session["client_identity_ref"],
        worker_identity_ref=worker_identity_ref)
    session["plan"]["status"] = "approved"
    session["plan"]["plan_approval_ref"] = approval["approval_id"]
    session["approval"] = approval
    session["state"] = "approved"
    for entry in session["answers"].values():
        if entry["state"] == "recommended_unapproved":
            entry["state"] = "approved_recommendation"
    session["history"].append({"at": _now(), "event": "approved",
                               "approval_id": approval["approval_id"],
                               "verification_class": assertion["verification_class"]})
    _persist(session)
    return assertion


def begin_build(session: Dict[str, Any]) -> Dict[str, Any]:
    """The doc 03 §3 transition approved -> building. Only an approved
    session may enter building; the launch record's status follows."""
    if session["state"] != "approved" or not session.get("plan"):
        raise IntakeError("only an approved plan may enter building")
    session["plan"]["status"] = "building"
    session["state"] = "building"
    session["history"].append({"at": _now(), "event": "building"})
    _persist(session)
    return session


def request_revision(session: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    if session["state"] not in ("awaiting_plan_approval", "recommendation_ready",
                                "approved"):
        raise IntakeError("no plan to revise")
    session["plan_revision"] += 1
    session["plan"] = None
    session["plan_hash"] = None
    session["approval"] = None
    session["asked_ids"] = []  # a revised plan may need answers revisited
    session["state"] = "revision_requested"
    session["history"].append({"at": _now(), "event": "revision_requested",
                               "note": note, "revision": session["plan_revision"]})
    _persist(session)
    return session


def pause(session: Dict[str, Any]) -> Dict[str, Any]:
    if session["state"] not in ("cancelled", "approved", "building"):
        session["_state_before_pause"] = session["state"]
        session["state"] = "paused"
        _persist(session)
    return session


def resume(session: Dict[str, Any]) -> str:
    """Resume with a short recap, not a restart (doc 03 §1)."""
    if session["state"] == "paused":
        session["state"] = session.pop("_state_before_pause", "collecting")
        _persist(session)
    known = [f for f, e in session["answers"].items()
             if e["state"] in ("provided", "verified_existing",
                               "approved_recommendation")]
    lines = [f"Welcome back. We are setting up launch {session['launch_id']} "
             f"(step: {session['state']}).",
             f"We already have: {', '.join(sorted(known)) if known else 'nothing yet'}."]
    q = next_question(session)
    if session["state"] == "awaiting_plan_approval":
        lines.append("Your plan is ready for your review.")
    elif q:
        lines.append(f"Next: {q['prompt']}")
    return "\n".join(lines)


def cancel(session: Dict[str, Any]) -> Dict[str, Any]:
    session["state"] = "cancelled"
    session["history"].append({"at": _now(), "event": "cancelled"})
    _persist(session)
    return session


# ---------------------------------------------------------------------------
# Self-test — fixture conversations from doc 03 §11.
# ---------------------------------------------------------------------------
def _self_test() -> int:
    ok = True

    def say(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    def mk(**kw):
        base = dict(tenant_id="T", location_id="L", launch_id="X",
                    client_identity_ref="client-1", test_only=True)
        base.update(kw)
        return new_session(**base)

    def approval_for(session, **over):
        a = {"schema_version": "1.0", "approval_id": "APPR-1",
             "subject_type": "launch_plan_build",
             "subject_hash": session["plan_hash"],
             "owner_identity_ref": "client-1",
             "source_message_ref": "msg-123", "recorded_at": _now(),
             "scope": ["launch_plan_build"], "revoked": False,
             "verification_class": "recorded_consent_not_cryptographically_sealed"}
        a.update(over)
        return a

    # --- expert client: everything supplied via prefill, almost no questions
    s = mk(known={"offers.main.description": "Sunrise Coaching",
                  "offers.main.deliverables": ["6 sessions"],
                  "offers.main.price": {"amount_minor": 49700, "currency": "USD"},
                  "journey_mode": "single_simple",
                  "extras": {"upsell_1": False, "downsell_1": False,
                             "upsell_2": False},
                  "image_provider": "agnes"},
           brand_ref="brand-1", brand_hash="bh-1")
    asked = []
    while True:
        q = next_question(s)
        if q is None:
            break
        asked.append(q["id"])
        if q["id"] == "m0_mode":
            answer(s, "m0_mode", "I know what I want")
        elif q["id"] == "c1_bump":
            answer(s, "c1_bump", "No add-on")
        elif q["id"] == "c2_u1":
            answer(s, "c2_u1", "No upgrade")
        elif q["id"] == "d1_brand":
            answer(s, "d1_brand", "All saved already")
        elif q["id"] == "d2_copy_profile":
            answer(s, "d2_copy_profile", "Standard")
        elif q["id"] == "d3_location":
            answer(s, "d3_location", "Yes, my existing account")
        else:
            answer(s, q["id"], "n/a")
    say("b2_price" not in asked and "b1_journey" not in asked and
        "d4_image_provider" not in asked,
        f"expert: supplied facts are never re-asked (asked={asked})")
    r = assemble_plan(s)
    say(r["state"] == "awaiting_plan_approval", "expert: plan assembles")
    summary = render_summary(s)
    say("Sunrise Coaching" in summary and "497" in summary,
        "expert: summary names the real product and price")
    a = approve(s, approval_for(s), worker_identity_ref="worker-9")
    say(s["state"] == "approved" and a["verification_class"].startswith("recorded"),
        "expert: approval binds and is honestly classed as recorded consent")
    begin_build(s)
    say(s["state"] == "building" and s["plan"]["status"] == "building",
        "approved session enters building (doc 03 §3, D4)")

    # --- approval negatives
    s2 = mk()
    answer(s2, "m0_mode", "Choose a setup for me to review")
    say(s2["mode"] == "choose_for_me" and s2["state"] == "collecting",
        "'choose for me' selects recommendation mode and does NOT approve")
    answer(s2, "a1_offer", "A weekend workshop for new managers")
    answer(s2, "a4_deliverables", "x", value={"fields": {
        "offers.main.deliverables": {"value": ["2 days live"], "state": "provided"}}})
    answer(s2, "b1_journey", "Help me decide")
    say(_get(s2, "journey_mode")["state"] == "recommended_unapproved",
        "journey recommendation is labeled recommended_unapproved")
    answer(s2, "b2_price", "I have a price",
           value={"amount_minor": 29700, "currency": "USD"})
    answer(s2, "b3_billing", "All at once")
    answer(s2, "c1_bump", "No add-on")
    answer(s2, "c2_u1", "No upgrade")
    answer(s2, "d1_brand", "All saved already")
    answer(s2, "d2_copy_profile", "Recommend one")
    answer(s2, "d3_location", "Yes, my existing account")
    answer(s2, "d4_image_provider", "Recommend one")
    s2["available_providers"] = []
    r2 = assemble_plan(s2)
    say(r2["state"] == "recommendation_ready",
        "overwhelmed: a plan built on recommendations passes through "
        "recommendation_ready (doc 03 §3, D4)")
    present_plan(s2)
    say(s2["state"] == "awaiting_plan_approval",
        "presenting the plan moves recommendation_ready -> "
        "awaiting_plan_approval (D4)")
    try:
        approve(s2, approval_for(s2, owner_identity_ref="someone-else"),
                worker_identity_ref="worker-9")
        say(False, "unrelated client identity must not approve")
    except vlp.ApprovalError:
        say(True, "unrelated client identity cannot approve another launch")
    try:
        approve(s2, approval_for(s2, owner_identity_ref="worker-9"),
                worker_identity_ref="worker-9")
        say(False, "worker self-approval must fail")
    except vlp.ApprovalError:
        say(True, "worker cannot self-approve (identity == worker refused)")
    try:
        approve(s2, approval_for(s2, subject_hash="0" * 64),
                worker_identity_ref="worker-9")
        say(False, "stale hash approval must fail")
    except vlp.ApprovalError:
        say(True, "approval for a changed plan hash is rejected")
    approve(s2, approval_for(s2), worker_identity_ref="worker-9")
    say(_get(s2, "journey_mode")["state"] == "approved_recommendation",
        "after approval, used recommendations become approved_recommendation")

    # --- unknown price never becomes zero; missing fact blocks the plan
    s3 = mk()
    answer(s3, "a1_offer", "A course")
    answer(s3, "b1_journey", "One offer")
    answer(s3, "b2_price", "Suggest one for me to review")
    say(_get(s3, "offers.main.price")["state"] == "unknown",
        "suggest-without-rationale records price unknown, not zero")
    answer(s3, "c1_bump", "No add-on")
    answer(s3, "c2_u1", "No upgrade")
    r3 = assemble_plan(s3)
    say(r3["state"] == "awaiting_missing_fact" and
        any("price" in m for m in r3["missing"]),
        "unknown main price blocks plan at awaiting_missing_fact")
    # Review probe C (D3): supplying the missing fact then asking for the
    # plan recovers through present_plan — awaiting_missing_fact is not a
    # dead end.
    answer(s3, "b2_price", "I have a price",
           value={"amount_minor": 19900, "currency": "USD"})
    try:
        text3 = present_plan(s3)
        say(s3["state"] == "awaiting_plan_approval" and "199" in text3,
            "present_plan recovers after the missing price is supplied (D3)")
    except IntakeError as exc:
        say(False, f"present_plan recovers after the missing price is "
                   f"supplied (D3) — raised {exc}")

    # --- review probe B (D2): multiple_options needs real packages
    s7 = mk()
    answer(s7, "a1_offer", "A conference with levels")
    answer(s7, "b1_journey", "A few packages")
    answer(s7, "c1_bump", "No add-on")
    answer(s7, "c2_u1", "No upgrade")
    r7 = assemble_plan(s7)
    say(r7["state"] == "awaiting_missing_fact" and
        any("packages" in m for m in r7["missing"]),
        "multiple_options without packages stops at awaiting_missing_fact "
        "instead of spending an approval on an unbuildable plan (D2)")
    answer(s7, "b1_journey", "A few packages", value={"packages": [
        {"display_name": "Discovery Pass", "deliverables": ["day 1"],
         "price": {"amount_minor": 4900, "currency": "USD"}},
        {"display_name": "Elevation Elite", "deliverables": ["all days"],
         "price": {"amount_minor": 49700, "currency": "USD"}}]})
    r7 = assemble_plan(s7)
    mains7 = [o for o in (r7.get("plan") or {}).get("offers", [])
              if o["slot"] == "main"]
    say(r7["state"] == "awaiting_plan_approval" and len(mains7) == 2 and
        vlp.validate_launch(r7["plan"]) == [],
        "multiple_options with two named, priced packages assembles a valid "
        "plan (D2)")
    say("Discovery Pass" in render_summary(s7) and
        "Elevation Elite" in render_summary(s7),
        "selection-page summary names every package with its price (D2)")

    # --- free registration: free is a known price of 0
    s4 = mk(known={"journey_mode": "free_entry"})
    answer(s4, "a1_offer", "Free community registration")
    answer(s4, "b2_price", "It is free")
    answer(s4, "c1_bump", "No add-on")
    answer(s4, "c2_u1", "No upgrade")
    r4 = assemble_plan(s4)
    say(r4["state"] == "awaiting_plan_approval" and
        r4["plan"]["offers"][0]["prices"][0]["amount_minor"] == 0,
        "free entry: amount 0 is a KNOWN free price and the plan assembles")
    say("free" in render_summary(s4), "free entry: summary says free, not $0.00")

    # --- pause/resume with recap; cancel is terminal
    s5 = mk()
    answer(s5, "a1_offer", "A membership")
    pause(s5)
    recap = resume(s5)
    say("offers.main.description" in recap and s5["state"] == "collecting",
        "resume returns a recap naming what is already known")
    cancel(s5)
    try:
        answer(s5, "a2_transformation", "x")
        say(False, "cancelled intake must refuse answers")
    except IntakeError:
        say(True, "cancelled intake refuses further answers")

    # --- revision after approval request: hash changes, revision bumps
    s6 = mk()
    answer(s6, "a1_offer", "A retreat")
    answer(s6, "b1_journey", "One offer")
    answer(s6, "b2_price", "I have a price", value={"amount_minor": 10000})
    answer(s6, "c1_bump", "No add-on")
    answer(s6, "c2_u1", "No upgrade")
    assemble_plan(s6)
    old_hash = s6["plan_hash"]
    request_revision(s6, "price changed")
    answer(s6, "b2_price", "I have a price", value={"amount_minor": 12000})
    assemble_plan(s6)
    say(s6["plan_revision"] == 2 and s6["plan_hash"] != old_hash,
        "changed price after approval -> new revision, new plan hash")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Guided Signature Launch intake.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--new", action="store_true")
    ap.add_argument("--session", help="session JSON path")
    ap.add_argument("--tenant"); ap.add_argument("--location")
    ap.add_argument("--launch"); ap.add_argument("--client")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--answer", help="question id to answer")
    ap.add_argument("--text", default="")
    ap.add_argument("--value", help="JSON payload for structured answers")
    ap.add_argument("--source-ref", default="")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--launch-plan", action="store_true",
                    help="print the FULL launch plan (pages + emails + texts + automations + AI)")
    ap.add_argument("--out", help="with --launch-plan: write the plan JSON here")
    ap.add_argument("--recap", action="store_true")
    ap.add_argument("--cancel", action="store_true")
    ap.add_argument("--answers-file", help="client-intake-answers/v1 file to fill the session from")
    ap.add_argument("--brand-file", help="brand file written from that answers file (brand_ref and hash)")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.new:
        if not (args.session and args.tenant and args.launch and args.client):
            print("USAGE ERROR: --new needs --session --tenant --launch --client")
            return EXIT_FAILCLOSED
        s = new_session(tenant_id=args.tenant, location_id=args.location or "",
                        launch_id=args.launch, client_identity_ref=args.client)
        save_session(s, Path(args.session))
        print(f"session {s['session_id']} created at {args.session}")
        return EXIT_OK
    if not args.session:
        print("USAGE ERROR: pass --session (or --self-test).")
        return EXIT_FAILCLOSED
    s = load_session(Path(args.session))
    try:
        if args.answer:
            answer(s, args.answer, args.text,
                   value=json.loads(args.value) if args.value else None,
                   source_message_ref=args.source_ref)
            print("recorded.")
        elif args.answers_file:
            ingest_answers(s, json.loads(Path(args.answers_file).read_text(encoding="utf-8")),
                           Path(args.brand_file) if args.brand_file else None)
            print("answers file ingested.")
        elif args.next:
            q = next_question(s)
            print(json.dumps(q, indent=2) if q else "no further questions")
        elif args.plan:
            print(present_plan(s))
        elif args.launch_plan:
            if not s.get("plan"):
                raise IntakeError("no plan has been assembled yet; assemble it first")
            result = lpl.build_from_session(s)
            if result["state"] != "ready":
                print("FAIL: the launch plan is missing facts: " +
                      "; ".join(result["missing"]))
                return EXIT_VIOLATION
            text = json.dumps(result["plan"], indent=2) + "\n"
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
                print(f"launch plan written to {args.out}")
            else:
                print(text, end="")
        elif args.recap:
            print(resume(s))
        elif args.cancel:
            cancel(s)
            print("cancelled.")
        else:
            print("USAGE ERROR: pass --next, --answer, --answers-file, --plan, --recap or --cancel.")
            return EXIT_FAILCLOSED
    except (IntakeError, vlp.ApprovalError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_VIOLATION
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
