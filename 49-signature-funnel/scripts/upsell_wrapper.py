#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""upsell_wrapper.py - S49-08 bridge between S49 dispatch and Skill 80.

Skill 80's verified entrypoint (80-signature-upsell/components/adapters/
produce.py --instance upsell_1|upsell_2) consumes a SUPERSET of the S49
page-request 1.0: all 19 S49 fields (with copy_profile pinned to the
consumer const "signature-upsell-eight-section") PLUS 11 more blocks
(approval_hash, instance, offer, disclosure, eligibility, entry_context,
routes, payment_capability, source_landing_copy_ref,
factual_scarcity_evidence, action_binding), plus two staged files S49
dispatch does not emit (the 8-section copy document and the verified
journey state). Its output bundle {result, page_plan, native_binding}
wraps a result carrying all 17 S49 page-result fields PLUS 10 more,
which collect_launch_receipts rejects (page-result 1.0 is
additionalProperties: false).

This wrapper is the adapter command dispatch runs for the upsell_1 and
upsell_2 roles (SEPARATE invocations; --slot names the role). It:

  1. ENRICH  builds the superset request from the S49 page-request, the
     launch record, the compiled route graph (hash-verified against the
     request), the staged copy document and the verified journey state.
     The incoming request must be exactly page-request 1.0-shaped: any
     key outside the packet schema's fields fails closed by name here
     rather than being forwarded, because Skill 80's runtime validator
     does not enforce its schema's additionalProperties: false.
     Every block is sourced from a named input (see BUILD-REPORT.md for
     the block-by-block table). A block with NO honest source fails the
     run closed with a named error BEFORE produce.py is invoked: the
     wrapper never fabricates disclosure terms, eligibility evidence,
     routes, capability claims or scarcity facts.
  2. INVOKE  runs produce.py with the matching --instance.
  3. EXTRACT takes bundle["result"] out of the bundle.
  4. PROJECT reduces it to exactly the 17 page-result 1.0 fields and
     verifies the echo against the S49 request (a result that does not
     echo is refused, never repaired).
  5. Writes the projected result at the {result} path dispatch expects.

Operator-staged run inputs (sidecar): an optional enrichment JSON file
may supply ONLY the keys this wrapper cannot source in-band:
  source_landing_copy_ref            (string)
  disclosure.recurring_terms        (object; required for non-one_time)
  eligibility.already_owned_action  ("suppress_offer" |
                                     "route_to_final_thank_you")
  payment_capability                (object; only with real S06 evidence)
Any other sidecar key fails closed. source_landing_copy_ref may also be
sourced from a sibling result-landing.json in the work dir (the landing
role's own result artifact path), which is where a real run records it.

Deterministic, stdlib only. Exit 0 ok, 2 fail-closed / consumer failure,
3 usage.

Errata (2026-10-17, coordinator prose-correction pass): the page-request
1.0 field count in this docstring was corrected from 20 to 19 per the
packet page-request 1.0 schema (exactly 19 properties). Prose only;
no behavior affected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

EXIT_OK = 0
EXIT_FAILCLOSED = 2
EXIT_USAGE = 3

INSTANCES = ("upsell_1", "upsell_2")
UPSELL_COPY_PROFILE = "signature-upsell-eight-section"
ADAPTER_VERIFICATION_SOURCES = frozenset(
    {"native_purchase_ledger", "provider_event_readback", "s44_event_adapter"})
PENDING_BEHAVIOR = "retain_current_purchase_state_until_resolved_or_explicit_decline"
ON_PENDING_OR_FAILED = "remain_on_page_recoverable"
PENDING_GUARDS = {"verified_main_payment", "verified_u1_payment",
                  "verified_d1_payment", "verified_u2_payment"}

# The 17 page-result 1.0 fields, in collect_launch_receipts order.
RESULT_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                 "revision", "request_id", "input_hash", "page_id", "status",
                 "artifacts", "author_session", "reviewer_session",
                 "independent_review", "proof_class", "blockers",
                 "native_bindings_ref", "test_only")
# The page-request 1.0 fields: exactly the properties of the packet
# page-request schema (19 fields; the schema is additionalProperties:
# false). This wrapper consumes 1.0-shaped requests ONLY: enrich()
# fails closed on any other incoming key instead of forwarding it to
# Skill 80, whose runtime validator (adapter_common.validate_request)
# is a stdlib mirror that does NOT enforce the schema's
# additionalProperties: false. The test suite pins this tuple to the
# packet schema's properties, so the two cannot diverge silently.
REQUEST_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                  "revision", "request_id", "page_id", "page_role",
                  "assigned_skill", "approval_ref", "input_hash", "brand_ref",
                  "brand_hash", "route_graph_ref", "route_graph_hash",
                  "offer_refs", "copy_profile", "allowed_write_target",
                  "test_only")
ECHO_FIELDS = ("request_id", "input_hash", "page_id", "launch_id",
               "revision", "tenant_id", "location_id", "test_only")

MINOR_UNIT_EXPONENTS = {
    "JPY": 0, "KRW": 0, "VND": 0, "CLP": 0, "ISK": 0,
    "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3,
}
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
SIDECAR_TOP_KEYS = {"source_landing_copy_ref", "disclosure", "eligibility",
                    "payment_capability"}
SIDECAR_DISCLOSURE_KEYS = {"recurring_terms"}
SIDECAR_ELIGIBILITY_KEYS = {"already_owned_action"}


class EnrichmentError(ValueError):
    """Fail-closed: one or more superset blocks have no honest source.

    `blocks` names the unsourceable blocks so the operator sees exactly
    what run input is missing; the wrapper never guesses them."""

    def __init__(self, problems: List[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


# ---------------------------------------------------------------------------
# Small deterministic helpers (mirrors of the S49/S80 canonical logic).
# ---------------------------------------------------------------------------
def plan_document_hash(launch: Mapping[str, Any]) -> str:
    """SHA-256 of the launch record's bindable content. Byte-identical
    rule to validate_launch_plan.plan_document_hash (the plan-approval
    gate binds approvals to this value): canonical JSON of the record
    minus its lifecycle fields status and plan_approval_ref."""
    bindable = {k: v for k, v in launch.items()
                if k not in ("status", "plan_approval_ref")}
    return hashlib.sha256(json.dumps(
        bindable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def format_amount_minor(amount_minor: int, currency: str) -> str:
    """Integer minor units rendered without floats (doc 02 section 3);
    the same rule adapter_common.render_disclosure applies."""
    exp = MINOR_UNIT_EXPONENTS.get(currency, 2)
    if exp == 0:
        return "%s %d" % (currency, amount_minor)
    whole, frac = divmod(amount_minor, 10 ** exp)
    return "%s %d.%0*d" % (currency, whole, exp, frac)


def render_disclosure_text(amount_minor: int, currency: str, billing_type: str,
                           recurring_terms: Optional[Mapping[str, Any]]) -> str:
    """The adjacent-to-CTA disclosure text, DERIVED from the record's own
    approved amount/currency/terms (never copied from free text). Mirrors
    adapter_common.render_disclosure, which re-derives the same text for
    the page plan; the two must agree because both derive from the same
    structured fields."""
    amount = format_amount_minor(amount_minor, currency)
    if billing_type == "one_time":
        return ("One-time charge of %s, charged to your original payment "
                "method when you accept. No further charges for this "
                "offer." % amount)
    terms = recurring_terms or {}
    interval = terms["interval"]
    count = terms["interval_count"]
    per = interval if count == 1 else "every %d %ss" % (count, interval)
    cycles = terms.get("cycles")
    parts = ["%s today," % amount]
    if cycles is None:
        parts.append("then %s per %s until cancelled, charged to your "
                     "original payment method when you accept."
                     % (amount, per))
    elif cycles >= 2:
        parts.append("then %s per %s for %d further payments (%d payments "
                     "total), charged to your original payment method "
                     "when you accept." % (amount, per, cycles - 1, cycles))
    else:
        parts.append("charged to your original payment method when you "
                     "accept. No further charges for this offer.")
    body = " ".join(parts)
    trial_amount = terms.get("trial_amount_minor")
    trial_period = terms.get("trial_period")
    if trial_amount is not None and trial_period:
        return "Trial: %s for %s, then %s" % (
            format_amount_minor(trial_amount, currency), trial_period, body)
    return body


def _load_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EnrichmentError([f"{what}: cannot load {path}: {exc}"])


# ---------------------------------------------------------------------------
# Enrichment - one builder per superset block. Each returns (value, source)
# or records a named problem; enrich() fails closed if any problem exists.
# ---------------------------------------------------------------------------
def _select_offer(request: Mapping[str, Any], launch: Mapping[str, Any],
                  instance: str, problems: List[str]) -> Optional[Dict[str, Any]]:
    candidates = [o for o in launch.get("offers") or []
                  if isinstance(o, dict) and o.get("slot") == instance]
    if len(candidates) != 1:
        problems.append(
            f"offer: launch record carries {len(candidates)} offer(s) for "
            f"slot {instance}; exactly one is required")
        return None
    offer = candidates[0]
    if offer.get("offer_id") not in (request.get("offer_refs") or []):
        problems.append(
            f"offer: record offer {offer.get('offer_id')!r} for slot "
            f"{instance} is not bound by the request's offer_refs "
            f"{request.get('offer_refs')!r}")
        return None
    return offer


def _offer_block(offer: Mapping[str, Any], problems: List[str]) -> Optional[Dict[str, Any]]:
    out: Dict[str, Any] = {}
    for field in ("offer_id", "slot", "display_name", "deliverables",
                  "exclusions", "entitlement_ids", "native_product_id"):
        if field not in offer:
            problems.append(f"offer.{field}: missing on the launch record offer")
            return None
        out[field] = offer[field]
    if not out["deliverables"]:
        problems.append("offer.deliverables: the record offer names no "
                        "deliverables; the wrapper does not invent them")
        return None
    return out


def _select_price(offer: Mapping[str, Any],
                  problems: List[str]) -> Optional[Dict[str, Any]]:
    prices = [p for p in offer.get("prices") or [] if isinstance(p, dict)]
    approved = [p for p in prices
                if p.get("approval_status") in ("approved", "provided")]
    if len(approved) == 1:
        return approved[0]
    if len(prices) == 1:
        return prices[0]
    problems.append(
        f"disclosure: offer {offer.get('offer_id')!r} carries "
        f"{len(prices)} price choices ({len(approved)} approved); the "
        "wrapper never guesses which price a page discloses")
    return None


def _disclosure_block(offer: Mapping[str, Any], sidecar: Mapping[str, Any],
                      problems: List[str]) -> Optional[Dict[str, Any]]:
    price = _select_price(offer, problems)
    if price is None:
        return None
    amount = price.get("amount_minor")
    if type(amount) is not int or amount < 0:
        problems.append(
            "disclosure.amount_minor: the record price has no integer "
            "amount (unknown price); an unknown price is a blocked "
            "request, never silently zero")
        return None
    currency = price.get("currency")
    if not isinstance(currency, str) or not CURRENCY_RE.match(currency):
        problems.append(f"disclosure.currency: record price currency "
                        f"{currency!r} is not a three-letter code")
        return None
    billing = price.get("billing_type")
    side_terms = (sidecar.get("disclosure") or {}).get("recurring_terms")
    if billing == "one_time":
        if side_terms is not None:
            problems.append(
                "disclosure.recurring_terms: sidecar supplies terms for a "
                "one_time price; the contradiction fails closed")
            return None
        terms = None
    else:
        if not isinstance(side_terms, dict) or \
                "interval" not in side_terms or "interval_count" not in side_terms:
            problems.append(
                f"disclosure.recurring_terms: price billing_type is "
                f"{billing!r} but no recurring terms are sourced (the "
                "launch record's schedule rows carry amounts and free-text "
                "dues only, from which no interval may be invented); "
                "supply disclosure.recurring_terms in the enrichment "
                "sidecar from the approved terms of record")
            return None
        terms = side_terms
    return {
        "amount_minor": amount,
        "currency": currency,
        "billing_type": billing,
        "recurring_terms": terms,
        "disclosure_text": render_disclosure_text(amount, currency, billing, terms),
        "adjacent_to_cta": True,
        "native_price_id": price.get("native_price_id"),
    }


def _journey_record(journey: Mapping[str, Any], slot: str) -> Optional[Mapping[str, Any]]:
    for rec in journey.get("verified_purchases") or []:
        if isinstance(rec, dict) and rec.get("slot") == slot:
            return rec
    return None


def _purchase_block(rec: Mapping[str, Any], label: str,
                    problems: List[str]) -> Optional[Dict[str, Any]]:
    source = rec.get("verification_source")
    evidence = rec.get("evidence_ref")
    if source not in ADAPTER_VERIFICATION_SOURCES or not evidence:
        problems.append(
            f"{label}: journey record for this purchase carries no "
            "adapter verification_source / evidence_ref; an unsourced "
            "record is not purchase proof")
        return None
    out: Dict[str, Any] = {"status": "verified_succeeded",
                           "verification_source": source,
                           "evidence_ref": evidence}
    if rec.get("provider_event_ref") is not None:
        out["provider_event_ref"] = rec["provider_event_ref"]
    return out


def _eligibility_block(instance: str, offer: Mapping[str, Any],
                       journey: Mapping[str, Any], sidecar: Mapping[str, Any],
                       problems: List[str]) -> Optional[Dict[str, Any]]:
    main_rec = _journey_record(journey, "main")
    if main_rec is None:
        problems.append(
            "eligibility.original_purchase: the journey state carries no "
            "verified main purchase record; purchase proof cannot be "
            "sourced from the request or the launch record")
        return None
    original = _purchase_block(main_rec, "eligibility.original_purchase", problems)
    if original is None:
        return None
    qualifying = None
    if instance == "upsell_2":
        qualifying = _qualifying_block(journey, problems)
        if qualifying is None:
            return None
    owned = set(journey.get("owned_entitlement_ids") or [])
    already_owned = bool(owned & set(offer.get("entitlement_ids") or []))
    out: Dict[str, Any] = {
        "original_purchase": original,
        "qualifying_purchase": qualifying,
        "bump_only_qualifies": False,
        "client_side_claims_accepted_as_proof": False,
        "already_owned_instance": already_owned,
    }
    action = (sidecar.get("eligibility") or {}).get("already_owned_action")
    if action is not None:
        if action not in ("suppress_offer", "route_to_final_thank_you"):
            problems.append(f"eligibility.already_owned_action: sidecar "
                            f"value {action!r} is not a lawful action")
            return None
        out["already_owned_action"] = action
    return out


def _qualifying_block(journey: Mapping[str, Any],
                      problems: List[str]) -> Optional[Dict[str, Any]]:
    for slot in ("upsell_1", "downsell_1"):
        rec = _journey_record(journey, slot)
        if rec is not None:
            block = _purchase_block(rec, "eligibility.qualifying_purchase",
                                    problems)
            if block is None:
                return None
            block = dict(block)
            block["slot"] = slot
            # Reorder to the sibling fixtures' key order (cosmetic only).
            return {"slot": block["slot"], "status": block["status"],
                    "verification_source": block["verification_source"],
                    "evidence_ref": block["evidence_ref"],
                    **({"provider_event_ref": block["provider_event_ref"]}
                       if "provider_event_ref" in block else {})}
    problems.append(
        "eligibility.qualifying_purchase: the journey state carries no "
        "verified upsell_1 or downsell_1 purchase record; a bump alone "
        "never qualifies and no qualifying purchase may be asserted "
        "without journey evidence")
    return None


def _entry_context(instance: str, journey: Mapping[str, Any],
                   problems: List[str]) -> Optional[str]:
    if instance == "upsell_1":
        return None  # Contract: U1 follows checkout; it has no entry context.
    for slot, ctx in (("upsell_1", "from_upsell_1"),
                      ("downsell_1", "from_downsell_1")):
        if _journey_record(journey, slot) is not None:
            return ctx
    problems.append(
        "entry_context: no verified upsell_1/downsell_1 journey record "
        "exists to source the U2 entry context from")
    return None


def _routes_block(request: Mapping[str, Any], graph: Mapping[str, Any],
                  graph_bytes: bytes, instance: str,
                  problems: List[str]) -> Optional[Dict[str, Any]]:
    digest = hashlib.sha256(graph_bytes).hexdigest()
    if digest != request.get("route_graph_hash"):
        problems.append(
            f"routes: route graph file hash {digest} does not match the "
            f"request's route_graph_hash {request.get('route_graph_hash')!r}; "
            "routes are never sourced from an unverified graph")
        return None
    if graph.get("pending_failed_payment_behavior") != PENDING_BEHAVIOR:
        problems.append(
            "routes.on_payment_pending_or_failed: graph behavior "
            f"{graph.get('pending_failed_payment_behavior')!r} is not the "
            "recoverable-retention law")
        return None
    page_id = request.get("page_id")
    role_of = {n.get("page_id"): n.get("role") for n in graph.get("nodes") or []}
    targets: Dict[str, Dict[str, str]] = {}
    for edge in graph.get("edges") or []:
        if edge.get("from") != page_id:
            continue
        if edge.get("event") == "payment_succeeded":
            if edge.get("guard") not in PENDING_GUARDS:
                problems.append(
                    f"routes.on_payment_succeeded: paid edge guard "
                    f"{edge.get('guard')!r} is not a verified-payment guard")
                return None
            targets["on_payment_succeeded"] = {
                "target_role": role_of.get(edge.get("to")),
                "target_page_id": edge.get("to")}
        elif edge.get("event") == "explicit_decline":
            targets["on_explicit_decline"] = {
                "target_role": role_of.get(edge.get("to")),
                "target_page_id": edge.get("to")}
    for key in ("on_payment_succeeded", "on_explicit_decline"):
        if key not in targets or not targets[key]["target_role"]:
            problems.append(f"routes.{key}: the verified route graph has "
                            f"no such edge from page {page_id!r}")
            return None
    return {**targets, "on_payment_pending_or_failed": ON_PENDING_OR_FAILED}


def _payment_capability_block(offer: Mapping[str, Any],
                              sidecar: Mapping[str, Any],
                              problems: List[str]) -> Optional[Dict[str, Any]]:
    supplied = sidecar.get("payment_capability")
    if supplied is not None:
        if not isinstance(supplied, dict) or \
                set(supplied) != {"one_click_native_action_verified",
                                  "evidence_ref",
                                  "fallback_when_one_click_unavailable"}:
            problems.append(
                "payment_capability: sidecar block must carry exactly "
                "one_click_native_action_verified, evidence_ref and "
                "fallback_when_one_click_unavailable")
            return None
        if supplied["one_click_native_action_verified"] and \
                not supplied.get("evidence_ref"):
            problems.append(
                "payment_capability: a verified one-click capability "
                "claimed without an evidence_ref is a claim, not proof")
            return None
        return dict(supplied)
    # No S06/S80-06 capability evidence is in hand: declare the capability
    # UNVERIFIED and the paid action blocked-safe. That is a statement of
    # absence sourced from the record (the offer carries no installed
    # native binding evidence), never an invented capability.
    return {"one_click_native_action_verified": False,
            "evidence_ref": None,
            "fallback_when_one_click_unavailable":
                "block_paid_action_safe_continuation"}


def _source_landing_copy_ref(sidecar: Mapping[str, Any], work_dir: Path,
                             problems: List[str]) -> Optional[str]:
    ref = sidecar.get("source_landing_copy_ref")
    if isinstance(ref, str) and ref:
        return ref
    landing_result = work_dir / "result-landing.json"
    if landing_result.is_file():
        try:
            res = json.loads(landing_result.read_text(encoding="utf-8"))
            artifacts = res.get("artifacts") or []
            if artifacts and artifacts[0].get("path"):
                return artifacts[0]["path"]
        except ValueError:
            pass
    problems.append(
        "source_landing_copy_ref: no source names the landing copy this "
        "upsell derives from (supply it in the enrichment sidecar, or run "
        "after the landing role has written result-landing.json into the "
        "work dir)")
    return None


def _check_sidecar(sidecar: Mapping[str, Any], problems: List[str]) -> None:
    extra = set(sidecar) - SIDECAR_TOP_KEYS
    if extra:
        problems.append(f"enrichment sidecar: unknown key(s) {sorted(extra)}; "
                        "the sidecar may only supply the documented keys")
    disc = sidecar.get("disclosure") or {}
    if set(disc) - SIDECAR_DISCLOSURE_KEYS:
        problems.append("enrichment sidecar: disclosure may only supply "
                        "recurring_terms")
    elig = sidecar.get("eligibility") or {}
    if set(elig) - SIDECAR_ELIGIBILITY_KEYS:
        problems.append("enrichment sidecar: eligibility may only supply "
                        "already_owned_action")


def enrich(request: Mapping[str, Any], launch: Mapping[str, Any],
           graph: Mapping[str, Any], graph_bytes: bytes,
           copy_doc: Mapping[str, Any], journey: Mapping[str, Any],
           sidecar: Mapping[str, Any], work_dir: Path,
           instance: str) -> Dict[str, Any]:
    """Build the Skill 80 superset request, or raise EnrichmentError
    naming every block that has no honest source."""
    problems: List[str] = []
    # Input shape (DEFECT 1 cure): the request must be exactly
    # page-request 1.0-shaped. Any key outside REQUEST_FIELDS (for
    # example the schema 1.1 prompt_policy_id) fails closed by name
    # here, before the enriched request is built, instead of being
    # silently forwarded to a consumer whose runtime validator does
    # not enforce its schema's additionalProperties: false.
    for key in sorted(set(request) - set(REQUEST_FIELDS)):
        problems.append(
            f"request: field {key!r} is not part of page-request 1.0; "
            "this wrapper consumes 1.0-shaped requests only (refused, "
            "never forwarded)")
    _check_sidecar(sidecar, problems)
    if request.get("page_role") != instance:
        problems.append(f"instance: request page_role "
                        f"{request.get('page_role')!r} does not match the "
                        f"invoked slot {instance!r}")
    if request.get("assigned_skill") != 80:
        problems.append(f"assigned_skill: request assigns skill "
                        f"{request.get('assigned_skill')!r}, not 80")
    offer = _select_offer(request, launch, instance, problems)
    offer_block = _offer_block(offer, problems) if offer else None
    disclosure = _disclosure_block(offer, sidecar, problems) if offer else None
    eligibility = _eligibility_block(instance, offer, journey, sidecar,
                                      problems) if offer else None
    entry_context = _entry_context(instance, journey, problems)
    routes = _routes_block(request, graph, graph_bytes, instance, problems)
    capability = _payment_capability_block(offer, sidecar, problems) if offer else None
    landing_ref = _source_landing_copy_ref(sidecar, work_dir, problems)
    scarcity = copy_doc.get("verified_scarcity_evidence")
    if scarcity is None:
        scarcity = []
    if not isinstance(scarcity, list):
        problems.append("factual_scarcity_evidence: the copy document's "
                        "verified_scarcity_evidence is not an array")
    if problems:
        raise EnrichmentError(problems)

    enriched = dict(request)
    enriched["copy_profile"] = UPSELL_COPY_PROFILE
    enriched["approval_hash"] = plan_document_hash(launch)
    enriched["instance"] = instance
    enriched["source_landing_copy_ref"] = landing_ref
    enriched["offer"] = offer_block
    enriched["disclosure"] = disclosure
    enriched["eligibility"] = eligibility
    enriched["entry_context"] = entry_context
    enriched["routes"] = routes
    enriched["payment_capability"] = capability
    enriched["factual_scarcity_evidence"] = scarcity
    enriched["action_binding"] = {
        "expected_action_ref": "native-one-click:" + offer["offer_id"],
        "binding_kind": "native_one_click_guarded",
        "source_ref": "request:" + str(request.get("request_id")),
    }
    return enriched


# ---------------------------------------------------------------------------
# Projection - bundle result -> exactly the 17 page-result 1.0 fields.
# ---------------------------------------------------------------------------
def project_result(bundle: Mapping[str, Any],
                   request: Mapping[str, Any]) -> Dict[str, Any]:
    result = bundle.get("result")
    if not isinstance(result, dict):
        raise EnrichmentError(["bundle carries no 'result' object to project"])
    missing = [f for f in RESULT_FIELDS if f not in result]
    if missing:
        raise EnrichmentError([f"bundle result is missing page-result "
                                f"field(s) {missing}"])
    projected = {f: result[f] for f in RESULT_FIELDS}
    for f in ECHO_FIELDS:
        if projected[f] != request.get(f):
            raise EnrichmentError([
                f"result does not echo its request on {f}: "
                f"{projected[f]!r} != {request.get(f)!r} (refused, "
                "never repaired)"])
    return projected


# ---------------------------------------------------------------------------
# CLI - the dispatch adapter command shape.
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="S49-08 wrapper: S49 page-request -> Skill 80 produce.py "
                    "-> page-result 1.0, for one upsell instance.")
    ap.add_argument("--slot", required=True, choices=INSTANCES,
                    help="the dispatch role (upsell_1|upsell_2); separate "
                         "invocation per role")
    ap.add_argument("--request", required=True, help="S49 page-request JSON")
    ap.add_argument("--result", required=True, help="page-result JSON to write")
    ap.add_argument("--launch", required=True, help="launch record JSON")
    ap.add_argument("--route-graph",
                    help="compiled route graph JSON (default: route-graph.json "
                         "beside the request, as dispatch writes it)")
    ap.add_argument("--copy", required=True,
                    help="staged 8-section copy document JSON for this instance")
    ap.add_argument("--journey", required=True,
                    help="verified journey state JSON (trusted-adapter records)")
    ap.add_argument("--enrichment",
                    help="optional sidecar JSON for the documented keys only")
    ap.add_argument("--produce", required=True, help="path to Skill 80 produce.py")
    ap.add_argument("--copy-artifact-path",
                    help="path string recorded in result.artifacts "
                         "(default: the --copy value)")
    ap.add_argument("--bundle-out",
                    help="where to keep the raw bundle (default: "
                         "bundle-<slot>.json beside the request)")
    args = ap.parse_args(argv)

    request_path = Path(args.request)
    work_dir = request_path.resolve().parent
    try:
        request = _load_json(request_path, "request")
        launch = _load_json(Path(args.launch), "launch record")
        graph_path = Path(args.route_graph) if args.route_graph \
            else work_dir / "route-graph.json"
        graph_bytes = graph_path.read_bytes()
        graph = json.loads(graph_bytes)
        copy_doc = _load_json(Path(args.copy), "copy document")
        journey = _load_json(Path(args.journey), "journey state")
        sidecar = _load_json(Path(args.enrichment), "enrichment sidecar") \
            if args.enrichment else {}
        enriched = enrich(request, launch, graph, graph_bytes, copy_doc,
                          journey, sidecar, work_dir, args.slot)
    except EnrichmentError as exc:
        for p in exc.problems:
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return EXIT_FAILCLOSED
    except OSError as exc:
        print(f"FAIL-CLOSED: cannot read run input: {exc}", file=sys.stderr)
        return EXIT_FAILCLOSED

    enriched_path = work_dir / f"upsell-request-{args.slot}.json"
    enriched_path.write_text(json.dumps(enriched, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    bundle_path = Path(args.bundle_out) if args.bundle_out \
        else work_dir / f"bundle-{args.slot}.json"
    cmd = [sys.executable, args.produce, "--instance", args.slot,
           "--request", str(enriched_path), "--copy", args.copy,
           "--journey", args.journey, "--out", str(bundle_path)]
    if args.copy_artifact_path:
        cmd += ["--copy-artifact-path", args.copy_artifact_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"FAIL-CLOSED: Skill 80 produce.py exited {proc.returncode}: "
              f"{proc.stderr.strip()[:800]}", file=sys.stderr)
        return EXIT_FAILCLOSED
    try:
        bundle = _load_json(bundle_path, "bundle")
        projected = project_result(bundle, request)
    except EnrichmentError as exc:
        for p in exc.problems:
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return EXIT_FAILCLOSED
    Path(args.result).write_text(json.dumps(projected, indent=2) + "\n",
                                 encoding="utf-8")
    print(f"wrote {args.result} (slot={args.slot} "
          f"status={projected['status']} proof_class={projected['proof_class']}; "
          f"enriched request {enriched_path}; bundle {bundle_path})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
