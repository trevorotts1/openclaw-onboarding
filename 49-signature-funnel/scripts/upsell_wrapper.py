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
     The incoming request must be exactly page-request shaped: the
     1.0 fields, plus, on a request stamped schema_version "1.1", the
     one 1.1 field (prompt_policy_id, admitted under the pair rule by
     the flip-time seam, adoption map 1.4 item 4). Any other key fails
     closed by name here rather than being forwarded, because Skill
     80's runtime validator does not enforce its schema's
     additionalProperties: false.
     Every block is sourced from a named input (see BUILD-REPORT.md for
     the block-by-block table). A block with NO honest source fails the
     run closed with a named error BEFORE produce.py is invoked: the
     wrapper never fabricates disclosure terms, eligibility evidence,
     routes, capability claims or scarcity facts.
     Before any block is read, the launch record must match the request
     (tenant, location, launch, revision, approval, route graph hash and a
     recomputed input_hash); copy and journey must carry the request's
     test_only and the copy's offer_name must be the launch offer's
     display_name. Then Skill 80's validate_upsell_copy.py is run on the
     copy (--expected-action-ref native-one-click:<offer_id>, and for
     upsell_2 --compare the staged U1 copy: --u1-copy, default
     copy-upsell_1.json beside the request); any non-zero exit fails the run
     with no result, and the bundle's copy_validation records the real exit.
  2. INVOKE  runs produce.py with the matching --instance, on a journey whose
     product names and owned entitlement ids come from the launch record.
  3. EXTRACT takes bundle["result"] out of the bundle.
  4. PROJECT reduces it to exactly the 17 page-result 1.0 fields and
     verifies the echo against the S49 request (a result that does not
     echo is refused, never repaired).
  5. IMAGES  with --bridge-config (the landing bridge's own config: Skill 71 root plus
             brand owner, image cap and brand file) hands the page to Skill 71's
             page-type runner (scripts/run_page_type.py): desktop and mobile
             wireframes and mockups, one long review PDF per stage, overview boards,
             in <work_dir>/images-<slot>. The wrapper builds none of that itself. A
             failed image run fails the wrapper closed. A real (non test_only) run with
             neither flag exits 2 unless --skip-images-approval is recorded; a page
             whose disposition is not present_offer draws no images (and exits 2 on a
             real launch, after writing its blocked result).
  6. Writes the projected result at the {result} path dispatch expects.

STAGES (issue 72). --stage design (the default) is what dispatch runs: no purchase has happened, so the
eligibility block is evaluated over the design marker (DESIGN_JOURNEY_U1) and the result carries
U1-/U2-ELIGIBILITY-RUNTIME-ONLY; a journey that asserts verified purchases on a launch that is not
test_only is refused. --stage install keeps the strict path (adapter-verified journey records only).

Operator-staged run inputs (sidecar): the enrichment JSON file (REQUIRED: --enrichment)
may supply ONLY the keys this wrapper cannot source in-band:
  source_landing_copy_ref            (string)
  disclosure.recurring_terms        (object; required for non-one_time)
  eligibility.already_owned_action  ("suppress_offer" |
                                     "route_to_final_thank_you")
  payment_capability                (object; only with real S06 evidence)
Any other sidecar key fails closed. source_landing_copy_ref comes only from
the sidecar (UPS-18).

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import page_set  # noqa: E402  the shared image inputs and the page's full deliverables list

EXIT_OK = 0
EXIT_FAILCLOSED = 2
EXIT_USAGE = 3

INSTANCES = ("upsell_1", "upsell_2")
# Issue 72 / M8: the same stage vocabulary as downsell_wrapper.STAGES. At "design" no purchase has
# happened, so the eligibility block is evaluated over the design marker, never over purchase proof
# somebody typed in; at "install" the strict path stands (adapter-verified journey records only).
STAGES = ("design", "install")
DESIGN_JOURNEY_U1 = {"original_purchase": "design_marker"}
U1_ELIGIBILITY_BLOCKER = (
    "U1-ELIGIBILITY-RUNTIME-ONLY: the original purchase is a design marker, not purchase proof; no "
    "purchase was observed at design. Eligibility (a verified main purchase) is a runtime-stage gate "
    "enforced from the native purchase ledger and is not claimed here")
U2_ELIGIBILITY_BLOCKER = (
    "U2-ELIGIBILITY-RUNTIME-ONLY: the original and qualifying purchases are design markers, not "
    "purchase proof; no purchase was observed at design. Eligibility (a verified main purchase plus a "
    "verified upsell_1 or downsell_1 purchase) is a runtime-stage gate enforced from the native "
    "purchase ledger and is not claimed here")
ELIGIBILITY_BLOCKERS = {"upsell_1": U1_ELIGIBILITY_BLOCKER, "upsell_2": U2_ELIGIBILITY_BLOCKER}
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
# false). enrich() fails closed on any other incoming key instead of
# forwarding it to Skill 80, whose runtime validator
# (adapter_common.validate_request) is a stdlib mirror that does NOT
# enforce the schema's additionalProperties: false. The test suite
# pins this tuple to the packet schema's properties, so the two
# cannot diverge silently.
REQUEST_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                  "revision", "request_id", "page_id", "page_role",
                  "assigned_skill", "approval_ref", "input_hash", "brand_ref",
                  "brand_hash", "route_graph_ref", "route_graph_hash",
                  "offer_refs", "copy_profile", "allowed_write_target",
                  "test_only")
# The one field the 1.1 shape adds, admitted by the flip-time seam
# (adoption map 1.4 item 4, executed under map 2.3 step 3(a)): on a
# request stamped schema_version "1.1" this key is admitted and
# carried into the enriched request unchanged; on any other version
# its presence fails closed, as does a "1.1" request without a
# non-empty string value (the pair rule, in the consumers' wording).
# It is deliberately NOT part of REQUEST_FIELDS, which stays pinned
# to the packet page-request 1.0 schema's properties.
POLICY_FIELD = "prompt_policy_id"
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


def _norm(text: Any) -> str:
    """Whitespace-collapsed, case-folded text for name comparison."""
    return " ".join(str(text or "").split()).casefold()


def launch_identity_problems(request: Mapping[str, Any],
                             launch: Mapping[str, Any]) -> List[str]:
    """UPS-29: the launch record must be the one the request was built from.

    Compares tenant, location, launch, revision, the approval ref and the
    route graph hash, and recomputes the request input_hash (dispatch's own
    derivation, which folds in plan_document_hash(launch)). A stale or
    foreign launch.json left in the work dir fails here, by field name only,
    before any block is read from it."""
    problems: List[str] = []
    for field in ("tenant_id", "location_id", "launch_id", "revision"):
        if launch.get(field) != request.get(field):
            problems.append(f"launch identity: {field} of the launch record "
                            "differs from the request (stale or foreign launch.json)")
    if launch.get("plan_approval_ref") != request.get("approval_ref"):
        problems.append("launch identity: plan_approval_ref of the launch record "
                        "differs from the request approval_ref")
    if launch.get("route_graph_hash") != request.get("route_graph_hash"):
        problems.append("launch identity: route_graph_hash of the launch record "
                        "differs from the request")
    try:
        import dispatch_launch  # the canonical input_hash derivation
        expected = dispatch_launch.request_input_hash(
            dict(launch), request.get("page_id"), request.get("page_role"))
    except (ImportError, KeyError, TypeError, ValueError) as exc:
        problems.append(f"launch identity: input_hash cannot be recomputed ({exc})")
    else:
        if expected != request.get("input_hash"):
            problems.append("launch identity: the request input_hash does not match "
                            "plan_document_hash of the launch record (the plan changed)")
    return problems


def derive_journey(journey: Mapping[str, Any], launch: Mapping[str, Any]) -> Dict[str, Any]:
    """UPS-13/UPS-33: the journey handed to Skill 80 with product names and
    owned entitlement ids sourced from the launch record.

    Each verified purchase takes its offer_display_name from the launch offer
    of the same slot (dropped when the record has no such offer), and every
    entitlement of a launch offer the journey shows as purchased is added to
    owned_entitlement_ids. Staged owned ids are kept: this only adds, so it
    can only block more, never present an owned offer."""
    by_slot = {o.get("slot"): o for o in launch.get("offers") or [] if isinstance(o, dict)}
    out = dict(journey)
    owned = list(journey.get("owned_entitlement_ids") or [])
    records = []
    for rec in journey.get("verified_purchases") or []:
        rec = dict(rec) if isinstance(rec, dict) else rec
        offer = by_slot.get(rec.get("slot")) if isinstance(rec, dict) else None
        if isinstance(rec, dict):
            if offer and offer.get("display_name"):
                rec["offer_display_name"] = offer["display_name"]
            else:
                rec.pop("offer_display_name", None)
        if offer:
            owned += [e for e in offer.get("entitlement_ids") or [] if e not in owned]
        records.append(rec)
    out["verified_purchases"] = records
    out["owned_entitlement_ids"] = owned
    return out


VALIDATOR_VERDICTS = {0: "pass", 2: "violation", 3: "fail_closed"}


def run_copy_validation(produce: str, copy_path: str, expected_action_ref: str,
                        compare: Optional[str]) -> Dict[str, Any]:
    """UPS-01: run Skill 80's own validate_upsell_copy.py on the staged copy
    and return the copy_validation record built from its real exit code.
    Raises EnrichmentError (naming the violations) on any non-zero exit."""
    validator = Path(produce).resolve().parent.parent / "80-signature-upsell" \
        / "scripts" / "validate_upsell_copy.py"
    if not validator.is_file():
        raise EnrichmentError([f"copy validation: {validator.name} not found "
                               "beside the Skill 80 adapters; it is never skipped"])
    cmd = [sys.executable, str(validator), copy_path,
           "--expected-action-ref", expected_action_ref]
    if compare:
        cmd += ["--compare", compare]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).strip()
        raise EnrichmentError([f"copy validation: validate_upsell_copy.py exited "
                               f"{proc.returncode}: {detail[:1500]}"])
    return {"validator": "scripts/validate_upsell_copy.py",
            "profile_id": UPSELL_COPY_PROFILE,
            "exit_code": proc.returncode,
            "verdict": VALIDATOR_VERDICTS[proc.returncode],
            "copy_sha256": hashlib.sha256(Path(copy_path).read_bytes()).hexdigest()}


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


def _design_slot(launch: Mapping[str, Any], problems: List[str]) -> Optional[str]:
    """The U2 entry slot a design-stage request names: upsell_1 when the launch enables it, else
    downsell_1. The canonical U2 page serves both entry paths; the runtime guard checks the real one."""
    extras = launch.get("extras") if isinstance(launch.get("extras"), dict) else {}
    for slot in ("upsell_1", "downsell_1"):
        if extras.get(slot) is True:
            return slot
    problems.append("eligibility.qualifying_purchase: the launch record enables neither upsell_1 nor "
                    "downsell_1, so upsell_2 has no entry path to design for")
    return None


def _eligibility_block(instance: str, offer: Mapping[str, Any],
                       journey: Mapping[str, Any], sidecar: Mapping[str, Any],
                       problems: List[str], design_slot: Optional[str] = None,
                       design: bool = False) -> Optional[Dict[str, Any]]:
    qualifying = None
    if design:
        # DESIGN_JOURNEY_U1: nothing was bought, so the purchases are markers (80's validate_request
        # accepts them only with stage == "design"). No journey record is read or asserted.
        original = {"status": DESIGN_JOURNEY_U1["original_purchase"]}
        if instance == "upsell_2":
            if design_slot is None:
                return None
            qualifying = {"slot": design_slot, "status": DESIGN_JOURNEY_U1["original_purchase"]}
    else:
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
                   problems: List[str], design_slot: Optional[str] = None,
                   design: bool = False) -> Optional[str]:
    if instance == "upsell_1":
        return None  # Contract: U1 follows checkout; it has no entry context.
    if design:
        return {"upsell_1": "from_upsell_1", "downsell_1": "from_downsell_1"}.get(design_slot)
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
    problems.append(
        "source_landing_copy_ref: the enrichment sidecar must name the landing "
        "copy this upsell derives from")
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
           instance: str, stage: str = "design") -> Dict[str, Any]:
    """Build the Skill 80 superset request, or raise EnrichmentError
    naming every block that has no honest source.

    stage "design" (the default): a journey that carries no verified purchase records is evaluated as
    the design marker (DESIGN_JOURNEY_U1) and the request carries stage "design"; a journey that DOES
    carry verified purchase records is refused on a launch that is not test_only (a design-time run
    observes no purchase, so the claim is asserted proof, exactly as downsell_wrapper refuses it) and
    keeps the staged-fixture path on a test_only launch. stage "install": only adapter-verified journey
    records are accepted, as before."""
    identity = launch_identity_problems(request, launch)
    if identity:
        raise EnrichmentError(identity)
    problems: List[str] = []
    if stage not in STAGES:
        problems.append(f"stage: {stage!r} is not one of {list(STAGES)}")
    # Input shape (DEFECT 1 cure): the request must be exactly
    # page-request shaped. Any key outside REQUEST_FIELDS fails closed
    # by name here, before the enriched request is built, instead of
    # being silently forwarded to a consumer whose runtime validator
    # does not enforce its schema's additionalProperties: false.
    # The one admission beyond the 1.0 fields is the flip-time seam
    # (adoption map 1.4 item 4): POLICY_FIELD is admitted on a request
    # stamped "1.1" and carried through unchanged (the enriched request
    # below starts as a copy of the request, so an admitted id rides
    # it verbatim). The pair rule is enforced with the consumers' own
    # wording: the field on any other version fails closed, and a
    # "1.1" request without a non-empty string id fails closed, so a
    # mislabeled request is refused here by name rather than
    # forwarded. Genuinely unknown keys fail exactly as before.
    for key in sorted(set(request) - set(REQUEST_FIELDS) - {POLICY_FIELD}):
        problems.append(
            f"request: field {key!r} is not part of page-request 1.0; "
            "this wrapper consumes 1.0-shaped requests only (refused, "
            "never forwarded)")
    version = request.get("schema_version")
    if POLICY_FIELD in request:
        if version != "1.1":
            problems.append(
                "request: prompt_policy_id requires request "
                "schema_version 1.1 (the 1.0 schema forbids the field)")
        elif not isinstance(request[POLICY_FIELD], str) \
                or not request[POLICY_FIELD]:
            problems.append(
                "request: a 1.1 request must carry a non-empty "
                "prompt_policy_id (the 1.1 label exists to carry "
                "the field)")
    elif version == "1.1":
        problems.append(
            "request: a 1.1 request must carry a non-empty "
            "prompt_policy_id (the 1.1 label exists to carry the field)")
    _check_sidecar(sidecar, problems)
    if request.get("page_role") != instance:
        problems.append(f"instance: request page_role "
                        f"{request.get('page_role')!r} does not match the "
                        f"invoked slot {instance!r}")
    if request.get("assigned_skill") != 80:
        problems.append(f"assigned_skill: request assigns skill "
                        f"{request.get('assigned_skill')!r}, not 80")
    offer = _select_offer(request, launch, instance, problems)
    # UPS-13: a launch accepts only copy and journey of its own kind (test
    # fixtures never feed a real launch and the reverse), and the copy must
    # be written for the offer the launch record names.
    test_only = bool(request.get("test_only", False))
    for label, doc in (("copy", copy_doc), ("journey", journey)):
        if bool(doc.get("test_only", False)) != test_only:
            problems.append(f"{label}: test_only {bool(doc.get('test_only', False))} "
                            f"differs from the request's test_only {test_only}; "
                            "test fixtures never feed a real launch")
    if offer and _norm(copy_doc.get("offer_name")) != _norm(offer.get("display_name")):
        problems.append("copy.offer_name: the copy names a different offer than the "
                        "launch record's display_name for this slot")
    carries_purchases = bool(journey.get("verified_purchases"))
    if stage == "design" and carries_purchases and not test_only:
        problems.append(
            "journey.verified_purchases: the staged journey carries verified purchase records while "
            "the launch is not test_only; a design-time run observes no purchase, so the claim is "
            "refused (eligibility is a runtime-stage gate; run --stage install on the read-back)")
    design = stage == "design" and not carries_purchases
    design_slot = _design_slot(launch, problems) if design and instance == "upsell_2" else None
    offer_block = _offer_block(offer, problems) if offer else None
    disclosure = _disclosure_block(offer, sidecar, problems) if offer else None
    eligibility = _eligibility_block(instance, offer, journey, sidecar, problems,
                                      design_slot=design_slot, design=design) if offer else None
    entry_context = _entry_context(instance, journey, problems, design_slot=design_slot, design=design)
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
    if design:
        enriched["stage"] = "design"  # 80 accepts the design marker only with this
    enriched["action_binding"] = {
        "expected_action_ref": "native-one-click:" + offer["offer_id"],
        "binding_kind": "native_one_click_guarded",
        "source_ref": "request:" + str(request.get("request_id")),
    }
    return enriched


# ---------------------------------------------------------------------------
# Projection - bundle result -> the 17 page-result 1.0 fields below plus page_role, which the one
# canonical schema requires and the projection echoes from the request.
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
    # The one canonical page-result schema requires page_role (Harmony issue 85). Skill 80's result
    # may not carry it: copy it from the request, and refuse a result that names another role.
    role = result.get("page_role", request.get("page_role"))
    if role != request.get("page_role"):
        raise EnrichmentError([
            f"result does not echo its request on page_role: {role!r} != "
            f"{request.get('page_role')!r} (refused, never repaired)"])
    projected["page_role"] = role
    for f in ECHO_FIELDS:
        if projected[f] != request.get(f):
            raise EnrichmentError([
                f"result does not echo its request on {f}: "
                f"{projected[f]!r} != {request.get(f)!r} (refused, "
                "never repaired)"])
    return projected


# ---------------------------------------------------------------------------
# Images - wireframes and mockups through Skill 71's page-type runner.
# ---------------------------------------------------------------------------
def image_command(args: argparse.Namespace, request_path: Path, graph_path: Path,
                  bundle_path: Path, work_dir: Path) -> List[str]:
    """The Skill 71 runner command for this slot.

    Brand owner, image cap, brand file and design style come from the shared image inputs file when
    one is given, else from the landing bridge's config; none is invented here (the same discipline
    as landing_bridge.py). A value in the inputs file wins over the bridge config."""
    cfg = _load_json(Path(args.bridge_config), "bridge config") if args.bridge_config else {}
    landing = cfg.get("landing") or {}
    inputs = getattr(args, "inputs", None) or {}
    root = Path(args.skill71_root or (cfg.get("skill71") or {}).get("root") or "")

    def pick(key):
        value = inputs.get(key)
        return landing.get(key) if value in (None, "") else value

    missing = [k for k in ("brand_owner", "image_cap", "brand_file") if pick(k) in (None, "")]
    runner = root / "scripts" / "run_page_type.py"
    if missing or not runner.is_file():
        raise EnrichmentError([f"image inputs / bridge config: {missing} missing" if missing
                               else f"skill71 root has no {runner.name}"])
    # CARRIED 9: the page's own per-section image plan (Skill 80 upsell_image_plan.py), built from
    # the enriched request (which carries the offer record), reaches Skill 71 through --slots, so
    # U1 and U2 are not drawn from the heading-derived stock fallback.
    planner = Path(args.produce).parent / "upsell_image_plan.py"
    plan_path = work_dir / f"image-plan-{args.slot}.json"
    planned = subprocess.run(
        [sys.executable, str(planner), "--request", str(work_dir / f"upsell-request-{args.slot}.json"),
         "--out", str(plan_path)], capture_output=True, text=True)
    if planned.returncode != 0 or not plan_path.is_file():
        raise EnrichmentError([f"upsell_image_plan.py exited {planned.returncode}: "
                               f"{(planned.stdout + planned.stderr).strip()[:400]}"])
    # Dispatch stamps every request with one copy_profile; this page's is the consumer
    # constant, so Skill 71's intake records the upsell form. Nothing else is changed.
    images_request = work_dir / f"page-request-images-{args.slot}.json"
    images_request.write_text(json.dumps(
        dict(_load_json(request_path, "request"), copy_profile=UPSELL_COPY_PROFILE),
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cmd = [sys.executable, str(runner), "--copy-version", "upsell",
           "--copy-json", args.copy, "--bundle", str(bundle_path),
           "--request", str(images_request), "--launch-record", args.launch,
           "--route-graph", str(graph_path), "--brand-file", str(pick("brand_file")),
           "--brand-owner", str(pick("brand_owner")), "--image-cap", str(pick("image_cap")),
           "--run-dir", str(work_dir / f"images-{args.slot}"), "--provider", args.image_provider,
           "--slots", str(plan_path)]
    if pick("design_style"):
        cmd += ["--design-style", str(pick("design_style"))]
    if inputs.get("design_prose_ref"):
        cmd += ["--design-prose", str(inputs["design_prose_ref"])]
    if args.allow_paid:
        cmd.append("--allow-paid")
    return cmd


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
    ap.add_argument("--stage", choices=list(STAGES), default="design",
                    help="design (default): no purchase has happened, so a journey with no verified "
                         "purchase records is evaluated as the design marker and the result carries "
                         "U1/U2-ELIGIBILITY-RUNTIME-ONLY; a non-test launch whose journey asserts a "
                         "verified purchase is refused. install: adapter-verified journey records "
                         "only")
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
    ap.add_argument("--enrichment", required=True,
                    help="sidecar JSON for the documented keys only; REQUIRED: "
                         "source_landing_copy_ref comes only from it (UPS-18), so "
                         "a run without it can never pass")
    ap.add_argument("--produce", required=True, help="path to Skill 80 produce.py")
    ap.add_argument("--copy-artifact-path",
                    help="path string recorded in result.artifacts "
                         "(default: the --copy value)")
    ap.add_argument("--bridge-config",
                    help="landing bridge config JSON (Skill 71 root, brand owner, image "
                         "cap, brand file): produce the page's wireframes and mockups "
                         "through Skill 71. Without it none are made, and the wrapper says so")
    ap.add_argument("--image-inputs",
                    help="the shared image inputs file (design style, brand file, owner, image cap, "
                         "provider); makes the images run without --bridge-config when "
                         "--skill71-root is given")
    ap.add_argument("--skill71-root", help="the Skill 71 tree (default: the bridge config's)")
    ap.add_argument("--image-provider", choices=["stub", "kie"], default="stub",
                    help="image provider for --bridge-config (stub is free and draws "
                         "placeholders; kie spends money and needs --allow-paid)")
    ap.add_argument("--allow-paid", action="store_true",
                    help="confirms the spend cap is approved for --image-provider kie")
    ap.add_argument("--u1-copy",
                    help="the staged U1 copy JSON, compared for U2 distinctness "
                         "(default for upsell_2: copy-upsell_1.json beside the request)")
    ap.add_argument("--skip-images-approval",
                    help="recorded approval ref for a run with no wireframes or mockups; "
                         "without it a real (non test_only) run needs --bridge-config "
                         "or --image-inputs")
    ap.add_argument("--bundle-out",
                    help="where to keep the raw bundle (default: "
                         "bundle-<slot>.json beside the request)")
    args = ap.parse_args(argv)
    args.inputs = None
    if args.image_inputs:
        try:
            args.inputs = page_set.load_image_inputs(args.image_inputs)
        except page_set.PageSetError as exc:
            print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
            return EXIT_FAILCLOSED
        if args.image_provider == "stub" and args.inputs["image_provider"] == "kie":
            args.image_provider, args.allow_paid = "kie", args.inputs["allow_paid"]

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
                          journey, sidecar, work_dir, args.slot, args.stage)
    except EnrichmentError as exc:
        for p in exc.problems:
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return EXIT_FAILCLOSED
    except OSError as exc:
        print(f"FAIL-CLOSED: cannot read run input: {exc}", file=sys.stderr)
        return EXIT_FAILCLOSED

    test_only = bool(request.get("test_only", False))
    try:
        compare = None
        if args.slot == "upsell_2":
            compare = args.u1_copy or str(work_dir / "copy-upsell_1.json")
            if not Path(compare).is_file():
                raise EnrichmentError([
                    f"copy validation: upsell_2 needs the staged U1 copy to compare "
                    f"({compare} not found; pass --u1-copy)"])
        copy_validation = run_copy_validation(
            args.produce, args.copy, enriched["action_binding"]["expected_action_ref"],
            compare)
    except (EnrichmentError, OSError) as exc:
        for p in (exc.problems if isinstance(exc, EnrichmentError) else [str(exc)]):
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return EXIT_FAILCLOSED
    # UPS-22: the image step is mandatory for a real launch unless a skip
    # approval is recorded. ponytail: the ref is recorded, not verified here;
    # the approval primitive owns that check.
    if not (args.bridge_config or args.image_inputs or test_only
            or args.skip_images_approval):
        print("FAIL-CLOSED: images: neither --bridge-config nor --image-inputs was "
              "given and no --skip-images-approval is recorded; a real launch "
              "requires its wireframes and mockups", file=sys.stderr)
        return EXIT_FAILCLOSED

    enriched_path = work_dir / f"upsell-request-{args.slot}.json"
    journey_path = work_dir / f"journey-derived-{args.slot}.json"
    journey_path.write_text(json.dumps(derive_journey(_load_json(Path(args.journey), "journey state"),
                                                      launch), indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    enriched_path.write_text(json.dumps(enriched, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    bundle_path = Path(args.bundle_out) if args.bundle_out \
        else work_dir / f"bundle-{args.slot}.json"
    cmd = [sys.executable, args.produce, "--instance", args.slot,
           "--request", str(enriched_path), "--copy", args.copy,
           "--journey", str(journey_path), "--out", str(bundle_path), "--launch", args.launch]
    if args.copy_artifact_path:
        cmd += ["--copy-artifact-path", args.copy_artifact_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"FAIL-CLOSED: Skill 80 produce.py exited {proc.returncode}: "
              f"{proc.stderr.strip()[:800]}", file=sys.stderr)
        return EXIT_FAILCLOSED
    try:
        bundle = _load_json(bundle_path, "bundle")
        result = bundle.get("result") if isinstance(bundle, dict) else None
        if not isinstance(result, dict) or (result.get("hashes") or {}).get(
                "copy_sha256") != copy_validation["copy_sha256"]:
            raise EnrichmentError(["copy validation: the validated copy is not the "
                                   "copy Skill 80 built from (sha256 differs)"])
        # UPS-01: record what the validator really returned, and claim no test
        # outcome this run did not produce (Skill 80 hardcodes both).
        result["copy_validation"] = copy_validation
        result["test_outcomes"] = [
            {"test_id": "S80-copy-validator", "level": "L1", "outcome": "pass",
             "evidence_ref": "validate_upsell_copy.py exit 0 on copy_sha256 "
                             + copy_validation["copy_sha256"]}
        ] + [dict(o, outcome="not_run", evidence_ref=None)
             if o.get("outcome") == "pass" else o
             for o in result.get("test_outcomes") or []]
        bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
        projected = project_result(bundle, request)
        if enriched.get("stage") == "design":  # the design marker was used: say so in the result
            projected["blockers"] = list(projected["blockers"]) + [ELIGIBILITY_BLOCKERS[args.slot]]
    except EnrichmentError as exc:
        for p in exc.problems:
            print(f"FAIL-CLOSED: {p}", file=sys.stderr)
        return EXIT_FAILCLOSED
    # UPS-33: no paid image calls for a page that will not be presented.
    disposition = (bundle.get("page_plan") or {}).get("disposition") or {}
    blocked = disposition.get("action") != "present_offer"
    if blocked:
        print(f"NOTE images: disposition {disposition.get('action')!r} "
              f"({disposition.get('reason')!r}); the page is not presented, so no "
              f"wireframes or mockups were drawn for {args.slot}", file=sys.stderr)
    elif args.bridge_config or args.image_inputs:
        try:
            cmd = image_command(args, request_path, graph_path, bundle_path, work_dir)
        except EnrichmentError as exc:
            for p in exc.problems:
                print(f"FAIL-CLOSED: {p}", file=sys.stderr)
            return EXIT_FAILCLOSED
        if subprocess.run(cmd).returncode != 0:
            print("FAIL-CLOSED: Skill 71 page-type runner failed; no page-result written",
                  file=sys.stderr)
            return EXIT_FAILCLOSED
        # every design file the page made goes into its result, not only the copy
        images_dir = work_dir / f"images-{args.slot}"
        page_set.stage_visual_bible(getattr(args, "inputs", None), images_dir)
        found = {a["path"]: a for a in projected["artifacts"]}
        found.update({a["path"]: a for a in page_set.design_artifacts(args.slot, images_dir, with_provider=True)})
        projected["artifacts"] = [found[k] for k in sorted(found)]
    else:
        print(f"NOTE images: no --bridge-config, so no wireframes or mockups were made "
              f"for {args.slot}; this result is copy and a "
              f"{'TEST ONLY render' if test_only else 'recorded-skip render'} only",
              file=sys.stderr)
    Path(args.result).write_text(json.dumps(projected, indent=2) + "\n",
                                 encoding="utf-8")
    if blocked and not test_only:
        print(f"FAIL-CLOSED: {args.slot} is {disposition.get('action')!r} but the "
              "launch requires this page; the blocked result is written, the run "
              "does not pass", file=sys.stderr)
        return EXIT_FAILCLOSED
    print(f"wrote {args.result} (slot={args.slot} "
          f"status={projected['status']} proof_class={projected['proof_class']}; "
          f"enriched request {enriched_path}; bundle {bundle_path})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
