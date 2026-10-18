"""Shared local production logic for the Skill 80 upsell adapters (S80-04/05).

Stdlib only. No network, no charges. S80-06 binding integration: every
bundle now carries the extra-offer binding record (see
build_native_binding) and CTAs bind the binding action ref
"extra-offer-binding:<offer_id>". The binding is INTERFACE-CONFORMANT
only, at fixture level, against the S79 extra_offer_interface.md DRAFT:
the native action itself is still provisioned by Skill 6 and confirmed
by S06, so native_action.action_id stays None and verified_by is
"s80_06_binding" (the binding integration exists; the L3 native install
does not). A pretty local button does not prove a charge route
(spec 10 section 7).

Contracts consumed (read-only, another worker's reviewed artifacts):
  * schemas/upsell-request.schema.json / upsell-result.schema.json
  * profiles/upsell-profile.json (profile id signature-upsell-eight-section)
Requests are validated here with lightweight stdlib checks that mirror the
request schema's load-bearing rules; the test suite additionally validates
requests and results against the actual JSON Schemas.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

ADAPTERS_DIR = Path(__file__).resolve().parent
WORK_DIR = ADAPTERS_DIR.parent
SKILL_DIR = WORK_DIR / "80-signature-upsell"
PROFILE_PATH = SKILL_DIR / "profiles" / "upsell-profile.json"
REQUEST_SCHEMA_PATH = SKILL_DIR / "schemas" / "upsell-request.schema.json"
RESULT_SCHEMA_PATH = SKILL_DIR / "schemas" / "upsell-result.schema.json"

AUTHOR_SESSION = "S80-adapters-builder (S80-04/S80-05/S80-07 build session)"
# Copy/request layer (schema- and validator-governed): the guarded native
# action ref form. The request schema patterns action_binding.
# expected_action_ref to this form and the copy validator's guarded-action
# form accepts only this form, so requests and copy fixtures keep
# declaring it unchanged.
ACTION_REF_PREFIX = "native-one-click:"
# Bundle/page layer (S80-06): the extra-offer binding's action ref. Every
# CTA in a produced bundle binds THIS ref; it wraps the native ref above
# for the same offer_id, and the correspondence is checked at build time
# (build_cta_map) and again by the page renderer.
BINDING_ACTION_REF_PREFIX = "extra-offer-binding:"

# S80-06 native_binding record constants (fixed integration contract).
# The interface is the S79/S06 shared DRAFT; binding_status states the
# conformance level honestly - nothing here claims a live native action.
BINDING_KIND = "extra_offer_binding"
BINDING_INTERFACE_REF = "S79 extra_offer_interface.md DRAFT (fixture level)"
BINDING_STATUS = "interface_conformant_pending_s06"
BINDING_OPEN_QUESTIONS = [
    "S06-Q1", "S06-Q2", "S06-Q3", "S06-Q4", "S06-Q5", "S06-Q6",
    "S44-Q7", "S44-Q8", "S49-Q9",
]
# TEST ONLY capability-evidence stand-in for fixtures (structured native:
# ref, per the S79 interface section 3 capability-evidence input). It is
# emitted only for test_only requests; a non-test request records None
# rather than borrowing fixture evidence.
TEST_CAPABILITY_EVIDENCE_REF = "native:TEST-CAPABILITY-EVIDENCE"


def native_action_ref(offer_id: str) -> str:
    """The copy/request-layer guarded native action ref for an offer."""
    return ACTION_REF_PREFIX + offer_id


def binding_action_ref(offer_id: str) -> str:
    """The S80-06 extra-offer binding action ref for an offer."""
    return BINDING_ACTION_REF_PREFIX + offer_id


def build_native_binding(request: Mapping) -> Dict[str, object]:
    """The bundle's S80-06 native_binding record (fixed contract shape).

    native_action_id is None: no native ID is invented; the real ID
    arrives only with S06's installed binding (open questions S06-Q1..Q6,
    S44-Q7/Q8, S49-Q9 stay open and are named in the record).
    """
    return {
        "kind": BINDING_KIND,
        "interface_ref": BINDING_INTERFACE_REF,
        "binding_status": BINDING_STATUS,
        "native_action_id": None,
        "capability_evidence_ref": (
            TEST_CAPABILITY_EVIDENCE_REF if request.get("test_only") else None
        ),
        "open_questions": list(BINDING_OPEN_QUESTIONS),
    }

# Only these adapter-side sources can verify a purchase (spec 10 section 3).
# A client-side parameter such as acceptedU1=true is NEVER proof.
ADAPTER_VERIFICATION_SOURCES = frozenset(
    {"native_purchase_ledger", "provider_event_readback", "s44_event_adapter"}
)

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
# Minor-unit exponents (doc 02 section 3: do not hardcode two decimals for
# every currency). Default is 2; well-known zero- and three-decimal
# currencies are listed explicitly.
MINOR_UNIT_EXPONENTS = {
    "JPY": 0, "KRW": 0, "VND": 0, "CLP": 0, "ISK": 0,
    "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3,
}

# Journey slot vocabulary (verified purchases recorded by trusted adapters).
JOURNEY_SLOT_BY_INSTANCE_SLOT = {"upsell_1": "upsell_1", "downsell_1": "downsell_1"}


class AdapterError(ValueError):
    """Raised when a request/copy/journey cannot produce a truthful page."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def format_amount_minor(amount_minor: int, currency: str) -> str:
    """Render integer minor units without float arithmetic (doc 02 s.3)."""
    if type(amount_minor) is not int or amount_minor < 0:
        raise AdapterError("amount_minor must be a non-negative integer.")
    if not CURRENCY_RE.match(currency or ""):
        raise AdapterError("currency must be a three-letter uppercase code.")
    exp = MINOR_UNIT_EXPONENTS.get(currency, 2)
    if exp == 0:
        return "%s %d" % (currency, amount_minor)
    whole, frac = divmod(amount_minor, 10 ** exp)
    return "%s %d.%0*d" % (currency, whole, exp, frac)


def render_disclosure(disclosure: Mapping) -> str:
    """Render the adjacent-to-CTA disclosure from the commercial fields.

    The text is DERIVED from amount_minor / currency / billing_type /
    recurring_terms (integer minor units only), never trusted from a
    free-text field, so the amount a visitor sees always matches the
    approved offer mapping (spec 10 section 6).
    """
    amount = format_amount_minor(disclosure["amount_minor"], disclosure["currency"])
    billing = disclosure["billing_type"]
    terms = disclosure.get("recurring_terms")
    if billing == "one_time":
        if terms is not None:
            raise AdapterError("A one_time disclosure must not carry recurring terms.")
        return (
            "One-time charge of %s, charged to your original payment method "
            "when you accept. No further charges for this offer." % amount
        )
    if not isinstance(terms, Mapping):
        raise AdapterError(
            "Billing type %r requires recurring_terms (interval, cycles, "
            "trial) so the obligation can be disclosed." % (billing,)
        )
    interval = terms["interval"]
    count = terms["interval_count"]
    per = interval if count == 1 else "every %d %ss" % (count, interval)
    cycles = terms.get("cycles")
    parts: List[str] = ["%s today," % amount]
    if cycles is None:
        parts.append(
            "then %s per %s until cancelled, charged to your original "
            "payment method when you accept." % (amount, per)
        )
    elif cycles >= 2:
        parts.append(
            "then %s per %s for %d further payments (%d payments total), "
            "charged to your original payment method when you accept."
            % (amount, per, cycles - 1, cycles)
        )
    else:
        parts.append(
            "charged to your original payment method when you accept. "
            "No further charges for this offer."
        )
    body = " ".join(parts)
    trial_amount = terms.get("trial_amount_minor")
    trial_period = terms.get("trial_period")
    if trial_amount is not None and trial_period:
        return "Trial: %s for %s, then %s" % (
            format_amount_minor(trial_amount, disclosure["currency"]),
            trial_period,
            body,
        )
    return body


# ---------------------------------------------------------------------------
# Request validation (stdlib mirror of the load-bearing schema rules)
# ---------------------------------------------------------------------------


def validate_request(request: Mapping, instance: str) -> None:
    if not isinstance(request, Mapping):
        raise AdapterError("Request must be a JSON object.")
    # Prompt-policy pair rule (adoption map 1.4 item 2): the runtime
    # mirror enforces the same pair rule as the request schema, so a
    # mislabeled request cannot pass silently. schema_version must be
    # "1.0" or "1.1"; a 1.1 request must carry a non-empty string
    # prompt_policy_id; a 1.0 request must not carry the field at all.
    # The id is a citation, never a selection: this mirror checks the
    # pair rule and the field's shape only. Resolving the id against
    # the registry of record happens where the citation is stamped
    # (dispatch) and where budget decisions are accepted (the Q11
    # aggregator), per the map's section 4 citation rule.
    version = request.get("schema_version")
    if version not in ("1.0", "1.1"):
        raise AdapterError(
            "Request schema_version %r is not a shape this consumer "
            "accepts; expected \"1.0\" or \"1.1\"." % (version,)
        )
    if version == "1.1":
        policy_id = request.get("prompt_policy_id")
        if not isinstance(policy_id, str) or not policy_id:
            raise AdapterError(
                "a 1.1 request must carry a non-empty prompt_policy_id "
                "(the 1.1 label exists to carry the field)"
            )
    elif "prompt_policy_id" in request:
        raise AdapterError(
            "prompt_policy_id requires request schema_version 1.1 "
            "(the 1.0 schema forbids the field)"
        )
    if request.get("assigned_skill") != 80:
        raise AdapterError("Request is not assigned to Skill 80.")
    if request.get("instance") != instance or request.get("page_role") != instance:
        raise AdapterError(
            "Request instance/page_role must both be %r." % (instance,)
        )
    offer = request.get("offer") or {}
    if offer.get("slot") != instance:
        raise AdapterError("Offer slot must match the instance %r." % (instance,))
    if not offer.get("offer_id") or not offer.get("display_name"):
        raise AdapterError("Offer must carry an offer_id and display_name.")
    if not request.get("page_id") or not request.get("request_id"):
        raise AdapterError("Request must carry page_id and request_id.")
    disclosure = request.get("disclosure") or {}
    amount = disclosure.get("amount_minor")
    if type(amount) is not int or amount < 0:
        raise AdapterError(
            "Missing or non-integer price: an unknown price is a blocked "
            "request, never silently zero (doc 02 section 2)."
        )
    if disclosure.get("adjacent_to_cta") is not True:
        raise AdapterError("Disclosure must be adjacent to the CTA.")
    # Renders or raises: guarantees the disclosure text can be derived.
    render_disclosure(disclosure)
    routes = request.get("routes") or {}
    if routes.get("on_payment_pending_or_failed") != "remain_on_page_recoverable":
        raise AdapterError(
            "Pending/failed payments must remain on the page in a "
            "recoverable state (doc 02 section 4)."
        )
    elig = request.get("eligibility") or {}
    if elig.get("bump_only_qualifies") is not False:
        raise AdapterError("bump_only_qualifies must be false in this profile.")
    if elig.get("client_side_claims_accepted_as_proof") is not False:
        raise AdapterError(
            "Client-side claims must never be accepted as purchase proof."
        )
    # D-03 action binding: when the request declares the guarded native
    # action (the repaired request schema's action_binding block), it must
    # be the native guarded kind and must name THIS offer's action ref -
    # the same ref every CTA binds. A declared binding that points at a
    # different action is a fail-closed error, not a detail.
    binding = request.get("action_binding")
    if binding is not None:
        if not isinstance(binding, Mapping):
            raise AdapterError("action_binding must be a JSON object.")
        if binding.get("binding_kind") != "native_one_click_guarded":
            raise AdapterError(
                "action_binding.binding_kind must be 'native_one_click_guarded'."
            )
        expected_ref = ACTION_REF_PREFIX + offer.get("offer_id", "")
        if binding.get("expected_action_ref") != expected_ref:
            raise AdapterError(
                "action_binding.expected_action_ref %r does not match the "
                "request offer action ref %r."
                % (binding.get("expected_action_ref"), expected_ref)
            )


def validate_routes_for_instance(request: Mapping, instance: str) -> None:
    """Validate this skill's own route edges on the request (spec 10 s.3)."""
    routes = request["routes"]
    ok_success = {"upsell_1": {"upsell_2", "thank_you"}, "upsell_2": {"thank_you"}}
    ok_decline = {"upsell_1": {"downsell_1", "thank_you"}, "upsell_2": {"thank_you"}}
    s_target = (routes.get("on_payment_succeeded") or {}).get("target_role")
    d_target = (routes.get("on_explicit_decline") or {}).get("target_role")
    if s_target not in ok_success[instance]:
        raise AdapterError(
            "%s payment success must route to %s, not %r."
            % (instance, sorted(ok_success[instance]), s_target)
        )
    if d_target not in ok_decline[instance]:
        raise AdapterError(
            "%s explicit decline must route to %s, not %r."
            % (instance, sorted(ok_decline[instance]), d_target)
        )


# ---------------------------------------------------------------------------
# Copy binding
# ---------------------------------------------------------------------------


def build_cta_map(copy_doc: Mapping, request: Mapping) -> List[Dict[str, object]]:
    """Build the 8-entry CTA map; every CTA binds the SAME guarded action.

    Two ref layers, one offer: the copy document declares the guarded
    native action in the copy/request-layer form
    "native-one-click:<offer_id>" (the only form the request schema and
    the copy validator accept), and the copy is checked against THAT ref.
    The bundle's CTA map binds the S80-06 extra-offer binding ref
    "extra-offer-binding:<offer_id>" for the same offer_id. No native
    action ID is invented here.
    """
    offer_id = request["offer"]["offer_id"]
    expected_ref = ACTION_REF_PREFIX + offer_id
    emitted_ref = binding_action_ref(offer_id)
    if copy_doc.get("instance") != request["instance"]:
        raise AdapterError("Copy instance does not match the request instance.")
    # D-03: the copy's own action_binding block (added by the schema
    # repair) must agree with the same expected ref; the copy declaring
    # a different expected action is a binding mismatch, fail closed.
    copy_binding = copy_doc.get("action_binding")
    if copy_binding is not None and copy_binding.get("expected_action_ref") != expected_ref:
        raise AdapterError(
            "Copy action_binding.expected_action_ref %r does not match "
            "the request offer action ref %r."
            % (copy_binding.get("expected_action_ref"), expected_ref)
        )
    if copy_doc.get("accept_action_ref") != expected_ref:
        raise AdapterError(
            "Copy accept_action_ref %r does not match the request offer "
            "action ref %r." % (copy_doc.get("accept_action_ref"), expected_ref)
        )
    sections = copy_doc.get("sections") or []
    if len(sections) != 8:
        raise AdapterError("Upsell copy must have exactly eight sections.")
    cta_map: List[Dict[str, object]] = []
    for expected_number, section in enumerate(sections, start=1):
        if section.get("number") != expected_number:
            raise AdapterError("Copy sections must be numbered 1..8 in order.")
        cta = section.get("cta") or {}
        if not cta.get("text"):
            raise AdapterError(
                "Section %d has no CTA; every upsell section requires one."
                % expected_number
            )
        if cta.get("action_ref") != expected_ref:
            raise AdapterError(
                "Section %d CTA binds %r, not the single guarded action %r."
                % (expected_number, cta.get("action_ref"), expected_ref)
            )
        cta_map.append(
            {
                "section_number": expected_number,
                "cta_text": cta["text"],
                "action_ref": emitted_ref,
            }
        )
    return cta_map


# ---------------------------------------------------------------------------
# Verified journey state (adapter-side view of trusted purchase evidence)
# ---------------------------------------------------------------------------


def journey_records(journey: Optional[Mapping]) -> List[Mapping]:
    if not journey:
        return []
    return list(journey.get("verified_purchases") or [])


def journey_record_for(journey: Optional[Mapping], slot: str) -> Optional[Mapping]:
    for rec in journey_records(journey):
        if rec.get("slot") == slot:
            return rec
    return None


def original_purchase_check(request: Mapping, journey: Optional[Mapping]) -> Dict:
    """Cross-check the request's original-purchase claim against journey
    evidence recorded by a trusted adapter. Both must agree, and the
    verification source must be an adapter source - never client-side."""
    orig = (request.get("eligibility") or {}).get("original_purchase") or {}
    problems: List[str] = []
    if orig.get("status") != "verified_succeeded":
        problems.append("original purchase is not verified_succeeded")
    if orig.get("verification_source") not in ADAPTER_VERIFICATION_SOURCES:
        problems.append(
            "verification_source %r is not an adapter source; client-side "
            "claims are not purchase proof" % (orig.get("verification_source"),)
        )
    rec = journey_record_for(journey, "main")
    if rec is None:
        problems.append("journey state carries no verified main purchase record")
    else:
        if rec.get("evidence_ref") != orig.get("evidence_ref"):
            problems.append(
                "journey main-purchase evidence_ref does not match the request"
            )
        if rec.get("verification_source") not in ADAPTER_VERIFICATION_SOURCES:
            problems.append(
                "journey main-purchase record carries no adapter "
                "verification_source; an unsourced record is not verified "
                "journey evidence"
            )
    return {"verified": not problems, "problems": problems, "record": rec}


# ---------------------------------------------------------------------------
# Presentation decision: already-owned / incompatible suppression
# ---------------------------------------------------------------------------


def decide_presentation(
    request: Mapping,
    journey: Optional[Mapping],
    *,
    eligibility_ok: bool,
) -> Dict[str, object]:
    """Decide whether the offer may be presented, suppressed, or must
    route safely to the final thank-you. Never emits a duplicate charge:
    when the decision is not present_offer, charge_action_emitted is
    False (spec 10 sections 5 and 6)."""
    elig = request.get("eligibility") or {}
    offer = request.get("offer") or {}
    owned = set((journey or {}).get("owned_entitlement_ids") or [])
    conflicting = set((journey or {}).get("conflicting_entitlement_ids_for_instance") or [])
    already_owned = bool(elig.get("already_owned_instance")) or bool(
        owned & set(offer.get("entitlement_ids") or [])
    )
    incompatible = bool(conflicting & set(offer.get("entitlement_ids") or [])) or bool(
        (journey or {}).get("incompatible_with_instance")
    )
    fallback_action = elig.get("already_owned_action") or "suppress_offer"
    if not eligibility_ok:
        return {
            "action": "block_unverified",
            "reason": "eligibility_not_verified",
            "charge_action_emitted": False,
            "safe_route": None,
        }
    if already_owned:
        action = (
            "route_to_final_thank_you"
            if fallback_action == "route_to_final_thank_you"
            else "suppress_offer"
        )
        return {
            "action": action,
            "reason": "already_owned",
            "charge_action_emitted": False,
            "safe_route": "thank_you" if action == "route_to_final_thank_you" else None,
        }
    if incompatible:
        return {
            "action": "route_to_final_thank_you",
            "reason": "incompatible_entitlement",
            "charge_action_emitted": False,
            "safe_route": "thank_you",
        }
    return {"action": "present_offer", "reason": "eligible", "charge_action_emitted": True}


# ---------------------------------------------------------------------------
# Result assembly (spec 10 section 7 upsell-result.json)
# ---------------------------------------------------------------------------


def build_result(
    *,
    request: Mapping,
    copy_sha256: str,
    copy_artifact_path: str,
    cta_map: List[Dict[str, object]],
    eligibility_check: Mapping,
    disposition: Mapping,
    test_outcomes: Sequence[Mapping],
    extra_blockers: Sequence[str] = (),
) -> Dict[str, object]:
    disclosure = request["disclosure"]
    offer = request["offer"]
    blocked = disposition["action"] != "present_offer"
    blockers: List[str] = [
        "S80-06 extra-offer binding is integrated at interface-conformance "
        "level only (S79 draft interface, fixture level): the native "
        "action ID is null pending S06 confirmation (open questions "
        "S06-Q1..Q6, S44-Q7/Q8, S49-Q9) - result is authored/local only, "
        "NOT installed or live proof."
    ]
    blockers.extend(extra_blockers)
    if disposition["action"] == "block_unverified":
        blockers.append(
            "blocked_unverified: eligibility could not be verified from "
            "trusted adapter evidence; the paid action is blocked."
        )
    elif disposition["action"] in ("suppress_offer", "route_to_final_thank_you"):
        blockers.append(
            "%s: %s - offer not presented for purchase; no charge action "
            "emitted, no duplicate charge."
            % (disposition["action"], disposition["reason"])
        )
    disclosure_text = render_disclosure(disclosure)
    return {
        "schema_version": "1.0",
        "tenant_id": request["tenant_id"],
        "location_id": request["location_id"],
        "launch_id": request["launch_id"],
        "revision": request["revision"],
        "request_id": request["request_id"],
        "input_hash": request["input_hash"],
        "page_id": request["page_id"],
        "status": "blocked" if blocked else "authored",
        "artifacts": [{"path": copy_artifact_path, "sha256": copy_sha256}],
        "author_session": AUTHOR_SESSION,
        "reviewer_session": None,
        "independent_review": False,
        "proof_class": "L1",
        "blockers": blockers,
        "native_bindings_ref": None,
        "test_only": bool(request.get("test_only", False)),
        "instance": request["instance"],
        "source_hash": copy_sha256,
        "approved_offer_mapping": {
            "offer_id": offer["offer_id"],
            "slot": offer["slot"],
            "native_product_id": offer.get("native_product_id"),
            "native_price_id": disclosure.get("native_price_id"),
            "amount_minor": disclosure["amount_minor"],
            "currency": disclosure["currency"],
            "billing_type": disclosure["billing_type"],
        },
        "native_action": {
            "action_id": None,
            "settings_ref": None,
            "binding_screenshot_ref": None,
            "verified_by": "s80_06_binding",
        },
        "cta_map": cta_map,
        "disclosure_audit": {
            "amount_matches_native": None,
            "currency_present": True,
            "recurring_terms_disclosed": (
                True if disclosure["billing_type"] != "one_time" else None
            ),
            "adjacent_to_cta": True,
            "verdict": "pending_native_binding",
            "notes": [
                "Local disclosure rendered from integer amount_minor, "
                "currency and billing terms: %s" % disclosure_text,
                "Amount-versus-native match completes only after the "
                "native read-back that follows S06's installed binding "
                "confirmation (S80-06 binding is interface-conformant "
                "only until then).",
            ],
        },
        "eligibility_check": dict(eligibility_check),
        "copy_validation": {
            "validator": "scripts/validate_upsell_copy.py",
            "profile_id": "signature-upsell-eight-section",
            "exit_code": 0,
            "verdict": "pass",
            "copy_sha256": copy_sha256,
        },
        "hashes": {
            "copy_sha256": copy_sha256,
            "ui_sha256": None,
            "asset_sha256": [],
        },
        "test_outcomes": [dict(t) for t in test_outcomes],
    }


def build_page_plan(
    *,
    request: Mapping,
    disclosure_text: str,
    disposition: Mapping,
    acknowledgement_blocks: Sequence[Mapping] = (),
) -> Dict[str, object]:
    """Interaction/commercial declarations around the result (spec 10 s.6).

    Declares the S80-06 extra-offer binding the CTAs invoke (with the
    copy/request-layer native ref it wraps, for audit), the adjacent
    disclosure, processing/decline/failure states and the fallback. The
    binding is interface-conformant at fixture level; the native install
    is S06's and remains pending S06 confirmation - this plan never
    claims a live native action exists.
    """
    offer = request["offer"]
    capability = request.get("payment_capability") or {}
    routes = request["routes"]
    plan = {
        "test_only": bool(request.get("test_only", False)),
        "instance": request["instance"],
        "page_id": request["page_id"],
        "action_binding": {
            "kind": BINDING_KIND,
            "status": BINDING_STATUS,
            "action_ref": binding_action_ref(offer["offer_id"]),
            "native_action_ref": native_action_ref(offer["offer_id"]),
            "action_id": None,
            "guard": "single_flight_payment_attempt_guard",
            "purchase_trigger": "cta_click",
            "triggers_that_never_purchase": [
                "page_load",
                "scroll",
                "timer_expiry",
                "close_icon_click",
            ],
            "all_ctas_bind_this_action": True,
        },
        "disclosure": {
            "adjacent_to_cta": True,
            "text": disclosure_text,
            "amount_minor": request["disclosure"]["amount_minor"],
            "currency": request["disclosure"]["currency"],
            "billing_type": request["disclosure"]["billing_type"],
            "recurring_terms": request["disclosure"].get("recurring_terms"),
        },
        "states": {
            "processing": {
                "on_cta_click": "show_processing_and_disable_repeat_triggering",
                "repeat_click_while_pending": "ignored_by_single_flight_guard",
            },
            "decline": {
                "visible": True,
                "charges": False,
                "target_role": routes["on_explicit_decline"]["target_role"],
                "target_page_id": routes["on_explicit_decline"]["target_page_id"],
            },
            "payment_pending_or_failed": {
                "behaviour": "remain_on_page_recoverable",
                "is_acceptance": False,
                "is_decline": False,
                "grants_entitlement": False,
                "continue_without_extra": (
                    "deliberate action recorded separately as an explicit "
                    "decline (doc 02 section 4)"
                ),
            },
            "requires_customer_action": {
                "behaviour": "remain_on_page_recoverable",
                "is_acceptance": False,
                "is_decline": False,
            },
            "expired_or_lost_payment_context": {
                "behaviour": "block_paid_action_safe_continuation",
                "fabricate_payment_token": False,
            },
            "one_click_unavailable": {
                "fallback": capability.get(
                    "fallback_when_one_click_unavailable",
                    "block_paid_action_safe_continuation",
                ),
                "one_click_native_action_verified": bool(
                    capability.get("one_click_native_action_verified", False)
                ),
            },
            "already_owned_or_incompatible": {
                "behaviour": "suppress_or_safe_final_thank_you",
                "duplicate_charge": False,
            },
        },
        "success_route": {
            "target_role": routes["on_payment_succeeded"]["target_role"],
            "target_page_id": routes["on_payment_succeeded"]["target_page_id"],
            "requires": "verified_payment_from_trusted_adapter",
        },
        "disposition": dict(disposition),
        "acknowledgement_blocks": [dict(b) for b in acknowledgement_blocks],
    }
    # Prompt-policy pass-through (adoption map 1.4 item 2): the page
    # plan is the bundle provenance record S80 designates for the
    # governing prompt policy id. The id rides here, present only on a
    # 1.1 request (absent entirely at 1.0, never null - the Q12
    # encoding), so a prompt receipt or the flip-time wrapper seam can
    # read the governing id from the produced bundle. No result-profile
    # change: the Q11 prompt receipt can carry the id without one.
    policy_id = request.get("prompt_policy_id")
    if policy_id:
        plan["prompt_policy_id"] = policy_id
    return plan
