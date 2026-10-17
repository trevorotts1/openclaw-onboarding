#!/usr/bin/env python3
"""launch_intake_adapter.py: the shared-launch intake adapter (S50-04).

Imports an APPROVED S49 Signature Launch intake into the Email Engine as the
locked brief for profile signature_launch_landing_10, with per-field
provenance. This is a SEPARATE intake path from the legacy one-block
questionnaire (intake/email-intake-questions.json): the adapter never reads
that contract, never re-asks its questions, and never emits its attestation
flags (asked_all_at_once and friends would be fabricated statements about a
launch intake). The legacy contract and its authority test are untouched.

Inputs (all five are required, all produced and approved upstream):
  --session        S49 intake session (signature-launch-intake/v1)
  --launch         S49 launch record (launch.schema.json v1.0)
  --approval       S49 approval record of type launch_plan_build
  --brand-facts    brand facts document (founder name, brand voice)
  --landing-facts  landing facts document (sections 5, 6, 8, 9, 10 facts,
                   round timing, testimonial evidence or explicit null)

Every S49-shape assumption lives in tools/s49_launch_shape.py, the single
translation module; this file speaks only in engine terms. The contract is
intake/launch-intake-contract.json (human doc: intake/LAUNCH-INTAKE.md).

Fail-closed: any provenance gap, hash mismatch, or approval defect is a
REFUSAL (exit 2) naming the reason. A bare "approved": true flag is never
read as evidence anywhere in this file.

EXIT CODES: 0 adapted, 2 refusal, 3 usage / IO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s49_launch_shape as s49  # noqa: E402

EXIT_OK = 0
EXIT_REFUSAL = 2
EXIT_USAGE = 3

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "intake" / "launch-intake-contract.json"
PROFILE = "signature-launch-landing-10"
PROFILE_RECORD_REF = "email-library/sequences/sequence-signature-launch-landing-10.json"
OVERRIDE_CHANNELS = ("word_band_override", "expected_preview_count",
                     "subject_mode")
_OFFER_STATE_BY_KIND = {
    "owner": "provided",
    "existing_verified_catalog": "verified_existing",
    "recommendation": "approved_recommendation",
    "test_fixture": "provided",
}


class Refusal(Exception):
    """The launch brief cannot be honestly produced from these inputs."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _canonical_hash(doc: Any) -> str:
    return hashlib.sha256(json.dumps(
        doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _prov(state: str, source_kind: str, source_ref: str,
          question_id: Optional[str] = None, artifact: Optional[str] = None,
          artifact_hash: Optional[str] = None) -> Dict[str, Any]:
    return {"state": state, "source_kind": source_kind,
            "source_ref": source_ref, "question_id": question_id,
            "artifact": artifact, "artifact_hash": artifact_hash}


def _load_contract() -> Dict[str, Any]:
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal(f"launch intake contract is unreadable: {exc}")
    if contract.get("profile") != PROFILE \
            or contract.get("intake_mode") != "signature_launch" \
            or set(contract.get("consumed_states") or []) \
            != set(s49.CONSUMED_STATES):
        raise Refusal(
            "launch intake contract does not match the adapter constants "
            "(profile, intake_mode, consumed_states): refusing rather than "
            "adapting against a drifted contract")
    return contract


def _artifact_provenance(doc: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Validate a facts document's provenance block; return it normalized."""
    prov = doc.get("provenance")
    if not isinstance(prov, dict):
        raise Refusal(f"{label} carries no provenance block: facts without "
                      "provenance are refused")
    state = prov.get("state")
    if state not in s49.FIELD_STATES:
        raise Refusal(f"{label} provenance state {state!r} is not a doc 03 "
                      "field state")
    if state not in s49.CONSUMED_STATES:
        raise Refusal(
            f"{label} provenance state is {state!r}: only provided, "
            "verified_existing, or approved_recommendation facts can be "
            "locked into a brief")
    if prov.get("source_kind") not in s49.SOURCE_KINDS:
        raise Refusal(f"{label} provenance source_kind "
                      f"{prov.get('source_kind')!r} is not a provenance kind")
    if not _nonempty_str(prov.get("source_ref")):
        raise Refusal(f"{label} provenance carries no source_ref")
    return prov


def _ledger(session: Dict[str, Any], key: str,
            label: str) -> Dict[str, Any]:
    try:
        entry = s49.ledger_entry(session, key)
    except s49.ShapeError as exc:
        raise Refusal(str(exc))
    if entry is None:
        raise Refusal(
            f"the approved intake session carries no answer for {label} "
            f"({key}): a missing answer is not an approved fact")
    return entry


def _entry_ref(session: Dict[str, Any], entry: Dict[str, Any],
               key: str) -> str:
    """The provenance reference for a ledger entry. The S49 intake can leave
    source_ref empty on handler-set fields, so fall back to the session
    reference: a traceable reference is always recorded, never an empty one
    and never an invented approval."""
    ref = entry.get("source_ref")
    if _nonempty_str(ref):
        return ref
    return f"s49-intake-session:{session.get('session_id', '')}#{key}"


def _consumed(entry: Dict[str, Any], label: str) -> None:
    try:
        s49.consumed_state_ok(entry, label)
    except s49.ShapeError as exc:
        raise Refusal(str(exc))


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------
def adapt(session: Dict[str, Any], launch: Dict[str, Any],
          approval: Dict[str, Any], brand_facts: Dict[str, Any],
          landing_facts: Dict[str, Any], *,
          worker_identity_ref: str = "",
          brand_facts_sha256: Optional[str] = None,
          landing_facts_sha256: Optional[str] = None,
          brand_facts_ref: str = "brand-facts document",
          landing_facts_ref: str = "landing-facts document") -> Dict[str, Any]:
    """Validate the five launch artifacts and emit the locked brief.

    Raises Refusal on any defect. The emitted brief is the shape
    tools/prove-email.py consumes under intake_mode signature_launch.
    """
    _load_contract()
    for label, doc in (("intake session", session), ("launch record", launch),
                       ("approval record", approval),
                       ("brand facts", brand_facts),
                       ("landing facts", landing_facts)):
        if not isinstance(doc, dict):
            raise Refusal(f"{label} is not a JSON object")
    brand_hash = brand_facts_sha256 or _canonical_hash(brand_facts)
    landing_hash = landing_facts_sha256 or _canonical_hash(landing_facts)

    # --- session -----------------------------------------------------------
    if session.get("schema") != s49.SESSION_SCHEMA:
        raise Refusal(
            f"intake session schema is {session.get('schema')!r}, expected "
            f"{s49.SESSION_SCHEMA!r}: this adapter consumes only the S49 "
            "launch intake session shape")
    if session.get("status") not in s49.BUILDABLE_SESSION_STATES:
        raise Refusal(
            f"intake session status is {session.get('status')!r}: only an "
            "approved or building session can produce a locked brief")
    client_ref = session.get("client_identity_ref")
    if not _nonempty_str(client_ref):
        raise Refusal("intake session names no client identity reference")
    if not _nonempty_str(launch.get("launch_id")) \
            or session.get("launch_id") != launch.get("launch_id"):
        raise Refusal(
            "intake session launch_id does not match the launch record: "
            "the session belongs to another launch")
    plan_hash = s49.plan_document_hash(launch)
    if not _nonempty_str(session.get("plan_hash")):
        raise Refusal("intake session holds no plan hash: nothing was "
                      "approved to adapt")
    if session.get("plan_hash") != plan_hash:
        raise Refusal(
            "session plan_hash does not match the recomputed launch plan "
            "hash: the plan changed after the intake was approved")

    # --- launch record -----------------------------------------------------
    if launch.get("schema_version") != s49.LAUNCH_SCHEMA_VERSION:
        raise Refusal(
            f"launch record schema_version is "
            f"{launch.get('schema_version')!r}, expected '1.0'")
    if launch.get("status") not in s49.BUILDABLE_LAUNCH_STATUSES:
        raise Refusal(
            f"launch record status is {launch.get('status')!r}: only an "
            "approved or building plan can produce a locked brief")
    try:
        mains = s49.main_offers(launch)
    except s49.ShapeError as exc:
        raise Refusal(str(exc))
    if not mains:
        raise Refusal("launch record defines no main offer")
    if launch.get("journey_mode") == "single_simple" and len(mains) != 1:
        raise Refusal(
            f"journey_mode single_simple requires exactly one main offer, "
            f"found {len(mains)}")
    for offer in launch.get("offers") or []:
        if not isinstance(offer, dict):
            raise Refusal("launch record carries a non-object offer entry")
        oid = offer.get("offer_id")
        if offer.get("source_kind") not in s49.SOURCE_KINDS:
            raise Refusal(
                f"offer {oid!r} source_kind {offer.get('source_kind')!r} "
                "is not a provenance kind")
        if not _nonempty_str(offer.get("source_ref")):
            raise Refusal(
                f"offer {oid!r} carries no source_ref: provenance is "
                "required for every offered fact")
        for price in offer.get("prices") or []:
            if isinstance(price, dict) \
                    and (price.get("approval_status") == "unknown"
                         or price.get("amount_minor") is None):
                raise Refusal(
                    f"offer {oid!r} carries an unknown price while the "
                    "plan is approved: approval cannot cover an unknowable "
                    "price (unknown is never zero)")
    for offer in mains:
        if not _nonempty_str(offer.get("display_name")):
            raise Refusal(
                f"main offer {offer.get('offer_id')!r} has no display_name")

    # --- approval gate (S49 discipline, replicated in the shape module) ----
    try:
        s49.check_plan_build_approval(
            launch, approval, client_identity_ref=client_ref,
            worker_identity_ref=worker_identity_ref or "")
    except s49.ShapeError as exc:
        raise Refusal(str(exc))
    if launch.get("plan_approval_ref") != approval.get("approval_id"):
        raise Refusal(
            "launch record plan_approval_ref does not name the approval "
            "record's approval_id: the record and its approval disagree")

    # --- consumed ledger answers -------------------------------------------
    pains_entry = _ledger(session, s49.LEDGER_PAINS, "the section 6 pains")
    _consumed(pains_entry, "the section 6 pains")
    pains_value = pains_entry.get("value")
    if not isinstance(pains_value, list) or not pains_value \
            or not all(_nonempty_str(p) for p in pains_value):
        raise Refusal(
            "the intake pains answer is not a list of non-empty pain "
            "statements")
    transformation_entry = _ledger(session, s49.LEDGER_TRANSFORMATION,
                                   "the transformation (section 5 why)")
    _consumed(transformation_entry, "the transformation")
    if not _nonempty_str(transformation_entry.get("value")):
        raise Refusal("the intake transformation answer is empty")
    proof_entry = _ledger(session, s49.LEDGER_PROOF, "the proof answer")
    proof_state = proof_entry.get("state")
    if proof_state not in s49.FIELD_STATES:
        raise Refusal(f"the proof answer state {proof_state!r} is not a "
                      "doc 03 field state")
    if proof_state not in s49.CONSUMED_STATES \
            and proof_state != "not_applicable":
        raise Refusal(
            f"the proof answer state is {proof_state!r}: testimonial "
            "evidence can only be locked from an approved fact or an "
            "explicit not_applicable")

    # Client-exact overrides: only provenanced ledger entries, only the
    # locked overrides channel the prover honors.
    overrides: Dict[str, Any] = {}
    raw_overrides = s49.session_answers(session).get(s49.LEDGER_OVERRIDES)
    if raw_overrides is not None:
        if not isinstance(raw_overrides, dict):
            raise Refusal("session locked_overrides is not an object of "
                          "per-channel ledger entries")
        for channel, entry in raw_overrides.items():
            if channel not in OVERRIDE_CHANNELS:
                raise Refusal(
                    f"override channel {channel!r} is not in the locked "
                    "overrides channel (word_band_override, "
                    "expected_preview_count, subject_mode)")
            if not isinstance(entry, dict) or "value" not in entry \
                    or "state" not in entry:
                raise Refusal(
                    f"override {channel!r} is not a ledger entry: an "
                    "override without provenance is refused")
            _consumed(entry, f"override {channel!r}")
            value = entry.get("value")
            if channel == "expected_preview_count" \
                    and not (isinstance(value, int)
                             and not isinstance(value, bool)):
                raise Refusal("override expected_preview_count is not an "
                              "integer")
            if channel == "subject_mode" and not _nonempty_str(value):
                raise Refusal("override subject_mode is not a non-empty "
                              "string")
            if channel == "word_band_override" \
                    and not isinstance(value, dict):
                raise Refusal("override word_band_override is not an object")
            overrides[channel] = value

    # --- brand facts ---------------------------------------------------------
    brand_prov = _artifact_provenance(brand_facts, "brand facts")
    if brand_facts.get("brand_ref") != launch.get("brand_ref"):
        raise Refusal(
            "brand facts brand_ref does not match the launch record "
            "brand_ref: these brand facts belong to another brand")
    if "brand_hash" in brand_facts \
            and brand_facts.get("brand_hash") != launch.get("brand_hash"):
        raise Refusal(
            "brand facts declare a brand_hash that differs from the launch "
            "record brand_hash: the brand facts are not the approved brand")
    founder_name = brand_facts.get("founder_name")
    if not _nonempty_str(founder_name):
        raise Refusal(
            "brand facts carry no founder_name: the founder's actual name "
            "is required, never a placeholder")
    brand_voice = brand_facts.get("brand_voice")
    if not _nonempty_str(brand_voice):
        raise Refusal("brand facts carry no brand_voice")

    # --- landing facts -------------------------------------------------------
    landing_prov = _artifact_provenance(landing_facts, "landing facts")
    if "launch_id" in landing_facts \
            and landing_facts.get("launch_id") != launch.get("launch_id"):
        raise Refusal(
            "landing facts are bound to a different launch_id: facts from "
            "another launch cannot brief this one")
    offer_names = [o["display_name"] for o in mains]
    if "offer" in landing_facts \
            and landing_facts.get("offer") not in offer_names:
        raise Refusal(
            "landing facts name an offer that is not a main offer of this "
            "launch: the facts describe another offer")
    landing = landing_facts.get("landing")
    if not isinstance(landing, dict):
        raise Refusal("landing facts carry no landing object")
    if not _nonempty_str(landing.get("section_5_why")):
        raise Refusal("landing facts carry no section 5 why")
    who = landing.get("section_6_who")
    if not isinstance(who, dict):
        raise Refusal("landing facts carry no section 6 who object")
    fact_pains = who.get("pains")
    if not isinstance(fact_pains, list) or len(fact_pains) != 3:
        raise Refusal(
            "landing facts section 6 must carry exactly three pains (the "
            "profile's three PASTOR pain slots)")
    pain_refs = []
    for pain in fact_pains:
        if not isinstance(pain, dict) or not _nonempty_str(pain.get("ref")) \
                or not _nonempty_str(pain.get("pain")):
            raise Refusal(
                "each landing section 6 pain must carry a ref and a pain "
                "statement")
        pain_refs.append(pain["ref"])
    if len(set(pain_refs)) != 3:
        raise Refusal("landing section 6 pain refs are not distinct")
    for key in ("section_8_what_is_inside", "section_9_how_it_works",
                "section_10_support"):
        items = landing.get(key)
        if not isinstance(items, list) or not items \
                or not all(_nonempty_str(i) for i in items):
            raise Refusal(f"landing facts {key} is missing or empty")
    round_timing = landing.get("round_timing")
    if not isinstance(round_timing, dict) \
            or not _nonempty_str(round_timing.get("ref")) \
            or not _nonempty_str(round_timing.get("fact")):
        raise Refusal(
            "landing facts round_timing must carry a ref and the timing "
            "fact: round timing without provenance is refused")
    if "testimonial_evidence" not in landing:
        raise Refusal(
            "landing facts do not state testimonial_evidence: absence is "
            "not an explicit null (state the evidence or state null)")
    evidence = landing.get("testimonial_evidence")
    if evidence is not None:
        if not isinstance(evidence, list) or not evidence or not all(
                isinstance(e, dict) and _nonempty_str(e.get("quote"))
                and _nonempty_str(e.get("attribution")) for e in evidence):
            raise Refusal(
                "testimonial_evidence must be null or a list of entries "
                "each carrying a quote and an attribution")
        if proof_state == "not_applicable":
            raise Refusal(
                "the intake recorded proof as not_applicable but the "
                "landing facts carry testimonial evidence: the two "
                "artifacts contradict each other")
    deadline = landing.get("deadline")
    if deadline is not None:
        if not isinstance(deadline, dict) \
                or deadline.get("when_provenance") != "brief" \
                or landing_prov.get("approval_ref") \
                != approval.get("approval_id"):
            raise Refusal(
                "the landing facts declare a deadline whose provenance is "
                "not the approved launch plan: a deadline fact without "
                "brief provenance is refused")

    # --- assemble the locked brief ------------------------------------------
    offer_answer = " + ".join(offer_names)
    first_main = mains[0]
    constant_prov = _prov("verified_existing", "existing_verified_catalog",
                          PROFILE_RECORD_REF)
    brand_field = _prov(brand_prov["state"], brand_prov["source_kind"],
                        brand_prov["source_ref"], artifact=brand_facts_ref,
                        artifact_hash=brand_hash)
    landing_field = _prov(landing_prov["state"], landing_prov["source_kind"],
                          landing_prov["source_ref"],
                          artifact=landing_facts_ref,
                          artifact_hash=landing_hash)
    if evidence is None and proof_state == "not_applicable":
        testimonial_field = _prov(
            "not_applicable", landing_prov["source_kind"],
            _entry_ref(session, proof_entry, s49.LEDGER_PROOF),
            question_id=proof_entry.get("question_id"),
            artifact=landing_facts_ref, artifact_hash=landing_hash)
    else:
        testimonial_field = dict(landing_field)
    fields = {
        "sequence_position": dict(constant_prov),
        "objective": dict(constant_prov),
        "buyer_type": dict(constant_prov),
        "offer": _prov(_OFFER_STATE_BY_KIND[first_main["source_kind"]],
                       first_main["source_kind"], first_main["source_ref"],
                       artifact="launch record",
                       artifact_hash=plan_hash),
        "founder_name": dict(brand_field),
        "brand_voice": dict(brand_field),
        "why_section_5": dict(landing_field),
        "pains_section_6": dict(landing_field),
        "sections_8_9_10": dict(landing_field),
        "round_timing": dict(landing_field),
        "testimonial_evidence": testimonial_field,
    }
    intake_answers = {}
    for key, entry in ((s49.LEDGER_PAINS, pains_entry),
                       (s49.LEDGER_TRANSFORMATION, transformation_entry),
                       (s49.LEDGER_PROOF, proof_entry)):
        intake_answers[key] = {
            "state": entry.get("state"),
            "source_ref": _entry_ref(session, entry, key),
            "question_id": entry.get("question_id"),
        }
    answers: Dict[str, Any] = {
        "objective": "promotional",
        "buyer_type": "all",
        "offer": offer_answer,
        "brand_voice": brand_voice,
        "sequence_position": PROFILE,
        "founder_name": founder_name,
        "high_ticket": "no",
        "offer_token_ledger": offer_names,
        "client_overrode_word_band": "word_band_override" in overrides,
    }
    if overrides:
        answers["locked_overrides"] = overrides
    brief = {
        "kind": "brief",
        "skill": "email-engine",
        "intake_mode": "signature_launch",
        "launch_provenance": {
            "profile": PROFILE,
            "launch_id": launch.get("launch_id"),
            "launch_revision": launch.get("revision"),
            "tenant_id": launch.get("tenant_id"),
            "location_id": launch.get("location_id"),
            "plan_hash": plan_hash,
            "offer": {
                "offer_id": first_main.get("offer_id"),
                "offer_ids": [o.get("offer_id") for o in mains],
                "display_name": offer_answer,
                "source_kind": first_main["source_kind"],
                "source_ref": first_main["source_ref"],
            },
            "approval": {
                "approval_id": approval.get("approval_id"),
                "subject_type": approval.get("subject_type"),
                "subject_hash": approval.get("subject_hash"),
                "owner_identity_ref": approval.get("owner_identity_ref"),
                "source_message_ref": approval.get("source_message_ref"),
                "recorded_at": approval.get("recorded_at"),
                "scope": approval.get("scope"),
                "revoked": approval.get("revoked"),
                "verification_class": approval.get("verification_class"),
            },
            "session": {
                "session_id": session.get("session_id"),
                "status": session.get("status"),
                "client_identity_ref": client_ref,
            },
            "fields": fields,
            "intake_answers": intake_answers,
            "artifacts": {
                "brand_facts": {"ref": brand_facts_ref,
                                "sha256": brand_hash},
                "landing_facts": {"ref": landing_facts_ref,
                                  "sha256": landing_hash},
            },
        },
        "answers": answers,
    }
    return brief


# ---------------------------------------------------------------------------
# Fixtures (fictional, aligned with examples/golden-signature-launch-10).
# Shared by --self-test and test_launch_intake_adapter.py so the two can
# never drift apart.
# ---------------------------------------------------------------------------
def build_fixtures() -> Dict[str, Any]:
    brand_hash = hashlib.sha256(
        b"signature-launch-fixture-brand").hexdigest()
    pains = [
        "Effort without return: working harder than ever, doing everything "
        "right, and still watching results stay flat month after month.",
        "No system: every week starts from zero, every win is a scramble, "
        "and nothing learned ever compounds into predictable results.",
        "Building alone: no room, no peers, and no one to check your "
        "thinking, so isolation quietly convinces you the wall is "
        "permanent.",
    ]
    launch = {
        "schema_version": "1.0",
        "tenant_id": "tenant-fixture",
        "location_id": "location-fixture",
        "launch_id": "launch-fixture-0001",
        "revision": 1,
        "journey_mode": "single_simple",
        "status": "approved",
        "brand_ref": "brand:momentum-method",
        "brand_hash": brand_hash,
        "route_graph_ref": "route-graph-fixture",
        "route_graph_hash": hashlib.sha256(
            b"route-graph-fixture").hexdigest(),
        "plan_approval_ref": "approval-fixture-0001",
        "offers": [{
            "offer_id": "offer-main-momentum",
            "slot": "main",
            "display_name": "The Momentum Method",
            "deliverables": [
                "The weekly system map: the one thing to work on each week",
                "Plug-and-play launch templates: skip the blank page",
                "The results tracker: momentum you can see building",
            ],
            "exclusions": [],
            "entitlement_ids": ["momentum-method-core"],
            "requires": [],
            "excludes": [],
            "native_product_id": None,
            "prices": [{
                "price_choice_id": "momentum-usd", "currency": "USD",
                "amount_minor": 49700, "billing_type": "one_time",
                "native_price_id": None, "schedule": [],
                "terms_source": None, "approval_status": "provided",
            }],
            "source_kind": "owner",
            "source_ref": "client intake answers a1 and a4, approved in "
                          "the launch plan",
            "test_only": True,
        }],
        "extras": {"upsell_1": False, "downsell_1": False,
                   "upsell_2": False},
        "bump_enabled": False,
        "image_provider": "other_explicit",
        "source_refs": ["intake session session-fixture-0001"],
        "test_only": True,
    }
    plan_hash = s49.plan_document_hash(launch)
    approval = {
        "schema_version": "1.0",
        "approval_id": "approval-fixture-0001",
        "subject_type": "launch_plan_build",
        "subject_hash": plan_hash,
        "owner_identity_ref": "client:jordan-marsh",
        "source_message_ref": "msg-fixture-0001",
        "recorded_at": "2026-10-15T14:30:00+00:00",
        "scope": ["launch_plan_build"],
        "revoked": False,
        "verification_class":
            "recorded_consent_not_cryptographically_sealed",
    }
    session = {
        "session_id": "session-fixture-0001",
        "schema": s49.SESSION_SCHEMA,
        "mode": "signature_launch",
        "status": "approved",
        "client_identity_ref": "client:jordan-marsh",
        "location_ref": "location-fixture",
        "launch_id": "launch-fixture-0001",
        "launch_ref": "launch-fixture-0001",
        "answers": {
            s49.LEDGER_TRANSFORMATION: {
                "value": "Results that finally match the effort: a weekly "
                         "system that compounds instead of resetting.",
                "state": "provided",
                "source_ref": "intake answer a2 in session "
                              "session-fixture-0001",
                "question_id": "a2",
            },
            s49.LEDGER_PAINS: {
                "value": pains,
                "state": "provided",
                "source_ref": "intake answer a3 in session "
                              "session-fixture-0001",
                "question_id": "a3",
            },
            s49.LEDGER_PROOF: {
                "value": None,
                "state": "not_applicable",
                "source_ref": "intake answer a5 in session "
                              "session-fixture-0001",
                "question_id": "a5",
            },
        },
        "plan_hash": plan_hash,
        "approval_id": "approval-fixture-0001",
    }
    brand_facts = {
        "brand_ref": "brand:momentum-method",
        "brand_hash": brand_hash,
        "founder_name": "Jordan Marsh",
        "brand_voice": "Warm, direct, builder to builder. Short "
                       "sentences. No hype, no income claims, no guru "
                       "voice.",
        "provenance": {
            "state": "provided", "source_kind": "owner",
            "source_ref": "brand facts supplied by the client during the "
                          "launch intake",
            "approval_ref": "approval-fixture-0001",
        },
    }
    landing_facts = {
        "launch_id": "launch-fixture-0001",
        "offer": "The Momentum Method",
        "founder_name": "Jordan Marsh",
        "landing": {
            "section_5_why": "The people who work the hardest should never "
                             "be the ones rewarded the least. Effort was "
                             "never the problem; the missing architecture "
                             "was.",
            "section_6_who": {
                "audience": "Founders and builders with a real offer and "
                            "real effort, whose results do not match the "
                            "work they put in.",
                "pains": [
                    {"ref": "landing.section6.pain.1", "pain": pains[0]},
                    {"ref": "landing.section6.pain.2", "pain": pains[1]},
                    {"ref": "landing.section6.pain.3", "pain": pains[2]},
                ],
            },
            "section_8_what_is_inside": [
                "The weekly system map: the one thing to work on each week",
                "Plug-and-play launch templates: skip the blank page",
                "The results tracker: momentum you can see building",
            ],
            "section_9_how_it_works": [
                "A guided thirty-day path, one step at a time",
                "Live monthly strategy calls with people ahead of you",
                "A private builder community for fast answers",
            ],
            "section_10_support": [
                "Your first personalized system map the same day you join",
                "Direct feedback on your plan inside the calls",
            ],
            "round_timing": {
                "ref": "landing.offer.round_timing",
                "fact": "The Momentum Method runs in rolling thirty-day "
                        "rounds. The next round begins on a Monday, and "
                        "enrollment for that round closes the Thursday "
                        "before it begins.",
            },
            "testimonial_evidence": None,
        },
        "provenance": {
            "state": "provided", "source_kind": "owner",
            "source_ref": "landing facts approved with the launch plan",
            "approval_ref": "approval-fixture-0001",
        },
    }
    return {"session": session, "launch": launch, "approval": approval,
            "brand_facts": brand_facts, "landing_facts": landing_facts,
            "client_identity_ref": "client:jordan-marsh",
            "worker_identity_ref": "worker:s50-adapter"}


def _self_test() -> int:
    import copy
    ok = True

    def say(good: bool, msg: str) -> None:
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    def refuses(label: str, mutate) -> None:
        fx = copy.deepcopy(build_fixtures())
        mutate(fx)
        try:
            adapt(fx["session"], fx["launch"], fx["approval"],
                  fx["brand_facts"], fx["landing_facts"],
                  worker_identity_ref=fx["worker_identity_ref"])
            say(False, label)
        except Refusal:
            say(True, label)

    fx = build_fixtures()
    try:
        brief = adapt(fx["session"], fx["launch"], fx["approval"],
                      fx["brand_facts"], fx["landing_facts"],
                      worker_identity_ref=fx["worker_identity_ref"])
        say(True, "valid fixture set adapts to a locked brief")
        say(brief["intake_mode"] == "signature_launch"
            and brief["launch_provenance"]["plan_hash"]
            == s49.plan_document_hash(fx["launch"]),
            "emitted brief carries the recomputed plan hash")
        say("asked_all_at_once" not in brief
            and "question_block_msg_id" not in brief
            and "conversation_ledger" not in brief,
            "no legacy attestation flags are emitted (nothing fabricated)")
        say(brief["answers"]["founder_name"] == "Jordan Marsh"
            and brief["answers"]["offer"] == "The Momentum Method"
            and brief["answers"]["sequence_position"] == PROFILE,
            "brief answers carry the founder's actual name and the offer")
        say(brief["launch_provenance"]["fields"]["testimonial_evidence"]
            ["state"] == "not_applicable",
            "testimonial evidence is an explicit not_applicable, not an "
            "omission")
    except Refusal as exc:
        say(False, f"valid fixture set adapts (refused: {exc})")

    refuses("tampered plan (offer renamed after approval) is refused",
            lambda f: f["launch"]["offers"][0].__setitem__(
                "display_name", "The Renamed Method"))
    refuses("revoked approval is refused",
            lambda f: f["approval"].__setitem__("revoked", True))
    refuses("scope without launch_plan_build is refused",
            lambda f: f["approval"].__setitem__(
                "scope", ["paid_asset_budget"]))
    refuses("approval by a foreign identity is refused",
            lambda f: f["approval"].__setitem__(
                "owner_identity_ref", "client:someone-else"))
    refuses("deadline without brief provenance is refused",
            lambda f: f["landing_facts"]["landing"].__setitem__(
                "deadline", {"statement": "Enrollment closes Thursday.",
                             "when_provenance": "none"}))
    refuses("pains in state unknown are refused",
            lambda f: f["session"]["answers"][s49.LEDGER_PAINS]
            .__setitem__("state", "unknown"))
    refuses("pains as an unapproved recommendation are refused",
            lambda f: f["session"]["answers"][s49.LEDGER_PAINS]
            .__setitem__("state", "recommended_unapproved"))
    refuses("brand hash mismatch is refused",
            lambda f: f["brand_facts"].__setitem__("brand_hash", "0" * 64))
    refuses("testimonial evidence absent (not explicit null) is refused",
            lambda f: f["landing_facts"]["landing"].pop(
                "testimonial_evidence"))
    refuses("evidence contradicting a not_applicable proof answer refused",
            lambda f: f["landing_facts"]["landing"].__setitem__(
                "testimonial_evidence",
                [{"quote": "It worked.", "attribution": "A member"}]))
    refuses("session still collecting is refused",
            lambda f: f["session"].__setitem__("status", "collecting"))
    # Worker self-approval: the approver IS the client (passes the identity
    # check) but the run is operated by that same identity.
    fx2 = build_fixtures()
    try:
        adapt(fx2["session"], fx2["launch"], fx2["approval"],
              fx2["brand_facts"], fx2["landing_facts"],
              worker_identity_ref=fx2["client_identity_ref"])
        say(False, "worker self-approval is refused")
    except Refusal:
        say(True, "worker self-approval is refused")
    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return EXIT_OK if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _read_json_arg(path: str, label: str):
    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as exc:
        print(f"USAGE/IO ERROR: cannot read {label} at {path}: {exc}",
              file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"USAGE/IO ERROR: {label} at {path} is not valid JSON: {exc}",
              file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
    return doc, hashlib.sha256(raw).hexdigest(), p.name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Adapt an approved S49 launch intake into the locked "
                    "Email Engine brief for signature_launch_landing_10. "
                    "Exit 0 adapted, 2 refusal, 3 usage.")
    ap.add_argument("--session", help="S49 intake session JSON")
    ap.add_argument("--launch", help="S49 launch record JSON")
    ap.add_argument("--approval", help="S49 approval record JSON")
    ap.add_argument("--brand-facts", help="brand facts JSON")
    ap.add_argument("--landing-facts", help="landing facts JSON")
    ap.add_argument("--worker-identity",
                    help="identity ref of the worker operating this run "
                         "(self-approval check)")
    ap.add_argument("--out", help="write the locked brief here "
                                  "(default: stdout)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    missing = [name for name in ("session", "launch", "approval",
                                 "brand_facts", "landing_facts")
               if not getattr(args, name)]
    if missing:
        print("USAGE ERROR: missing required arguments: "
              + ", ".join("--" + m.replace("_", "-") for m in missing),
              file=sys.stderr)
        return EXIT_USAGE
    session, _, _ = _read_json_arg(args.session, "intake session")
    launch, _, _ = _read_json_arg(args.launch, "launch record")
    approval, _, _ = _read_json_arg(args.approval, "approval record")
    brand_facts, brand_sha, brand_name = _read_json_arg(
        args.brand_facts, "brand facts")
    landing_facts, landing_sha, landing_name = _read_json_arg(
        args.landing_facts, "landing facts")
    try:
        brief = adapt(session, launch, approval, brand_facts, landing_facts,
                      worker_identity_ref=args.worker_identity or "",
                      brand_facts_sha256=brand_sha,
                      landing_facts_sha256=landing_sha,
                      brand_facts_ref=brand_name,
                      landing_facts_ref=landing_name)
    except Refusal as exc:
        print(f"REFUSAL: {exc}")
        return EXIT_REFUSAL
    text = json.dumps(brief, indent=2) + "\n"
    if args.out:
        try:
            Path(args.out).write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"USAGE/IO ERROR: cannot write brief to {args.out}: "
                  f"{exc}", file=sys.stderr)
            return EXIT_USAGE
        prov = brief["launch_provenance"]
        print(f"ADAPTED: locked brief for {PROFILE} written to {args.out} "
              f"(launch {prov['launch_id']} revision "
              f"{prov['launch_revision']}, plan_hash "
              f"{prov['plan_hash'][:12]}..., approval "
              f"{prov['approval']['approval_id']})")
    else:
        sys.stdout.write(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
