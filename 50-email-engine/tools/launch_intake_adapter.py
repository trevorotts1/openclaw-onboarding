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

Launch mode (EM-B3): pass `--launch-plan PLAN` to read the U-CONTRACT
launch plan (shared-utils/signature_launch_contract/launch-plan.schema.json).
The plan's `email_sequences[]` units are the sequence selector: the adapter
emits one locked brief per planned Skill 50 sequence, each with its own
sequence_position and objective. The shared launch answers (the S49 intake
session answer ledger) are consumed exactly as above; the Skill 50
one-block questionnaire is never read or asked on this path.

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
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s49_launch_shape as s49  # noqa: E402
import launch_profiles  # noqa: E402

EXIT_OK = 0
EXIT_REFUSAL = 2
EXIT_USAGE = 3

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "intake" / "launch-intake-contract.json"

# ---- ONE profile registry (profiles/launch-email-families.json) --------------
# Every launch family's count, paired variants, purpose and timing is defined in
# that registry and read here, by the prover and by P4 emission. This adapter
# keeps NO second copy of the family table: a registry that cannot be read is a
# refusal, never a fallback to built-in sequence ids.
try:
    REGISTRY = launch_profiles.load_registry()
    REGISTRY_ERROR = None
except launch_profiles.RegistryError as exc:
    REGISTRY = {"families": [], "registry_version": None}
    REGISTRY_ERROR = str(exc)

FAMILIES = launch_profiles.families(REGISTRY) if not REGISTRY_ERROR else {}
PROFILE = (FAMILIES["main_launch"]["sequence_position"]
           if "main_launch" in FAMILIES else "signature-launch-landing-10")
PROFILE_RECORD_REF = (FAMILIES["main_launch"]["sequence_record"]
                      if "main_launch" in FAMILIES
                      else "email-library/sequences/sequence-signature-launch-landing-10.json")
OVERRIDE_CHANNELS = ("word_band_override", "expected_preview_count",
                     "subject_mode")
_OFFER_STATE_BY_KIND = {
    "owner": "provided",
    "existing_verified_catalog": "verified_existing",
    "recommendation": "approved_recommendation",
    "test_fixture": "provided",
}

# U-CONTRACT launch plan -> Skill 50 sequence profile (EM-B3). A launch plan
# unit kind resolves to the sequence library record that authors it; the
# objective follows the email's job, never invented from the plan. Both come
# from the ONE registry.
LAUNCH_PLAN_SCHEMA_VERSION = "1.0.0"
LAUNCH_SEQUENCE_PROFILES = {
    kind: (fam["sequence_position"], fam["objective"])
    for kind, fam in FAMILIES.items()
}
LAUNCH_SEQUENCE_PROVIDER = "skill50"

# The L01 session contract (shared intake/approval lane) — the agreed consumer
# surface for typed eligibility / lifecycle / sender metadata carried to L07.
SESSION_CONTRACT_REL = ("shared-utils", "signature_launch",
                        "session_contract.json")
SUPPORTED_SESSION_CONTRACT_MAJOR = "1"


def _registry() -> Dict[str, Any]:
    if REGISTRY_ERROR:
        raise Refusal("launch email profile registry is unreadable: %s — a "
                      "brief can never be locked against an unknown family"
                      % REGISTRY_ERROR)
    return REGISTRY


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
# Launch plan mode (EM-B3): the shared U-CONTRACT plan selects the sequences
# ---------------------------------------------------------------------------
def _profile_record_ref(family: Dict[str, Any]) -> str:
    """The sequence library record that defines this family (from the registry)."""
    return family["sequence_record"]


def _launch_contract():
    """The shared launch plan validator and schema, from the repo checkout or
    the installed skills tree. Imported by path so a same-named module on
    sys.path can never shadow the contract this adapter is bound to."""
    here = Path(__file__).resolve()
    candidates = [p / "shared-utils" / "signature_launch_contract"
                  for p in here.parents]
    candidates += [
        Path.home() / ".openclaw" / "skills" / "shared-utils" / "signature_launch_contract",
        Path("/data/.openclaw/skills/shared-utils/signature_launch_contract"),
    ]
    for directory in candidates:
        schema_path = directory / "launch-plan.schema.json"
        validator_path = directory / "validate_launch_plan.py"
        if not (schema_path.is_file() and validator_path.is_file()):
            continue
        spec = importlib.util.spec_from_file_location(
            "_s50_launch_contract_validator", validator_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, schema_path
    raise Refusal(
        "shared launch contract not found (shared-utils/"
        "signature_launch_contract): launch mode cannot be proven against "
        "the contract it claims to read")


def _validate_launch_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Fail closed unless the plan validates against the shared launch contract."""
    if not isinstance(plan, dict):
        raise Refusal("launch plan is not a JSON object")
    if plan.get("schema_version") != LAUNCH_PLAN_SCHEMA_VERSION:
        raise Refusal(
            f"launch plan schema_version is {plan.get('schema_version')!r}, "
            f"expected {LAUNCH_PLAN_SCHEMA_VERSION!r}")
    module, schema_path = _launch_contract()
    try:
        schema = module.load_json(schema_path)
        errors = module.validate_plan(plan, schema)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refusal(f"launch plan contract could not be read: {exc}")
    if errors:
        raise Refusal(
            "launch plan violates the shared launch contract: "
            + "; ".join(errors[:8]))
    return plan


def _launch_sequences(plan: Dict[str, Any],
                      sequence_id: Optional[str] = None) -> list:
    """The planned Skill 50 email units, in plan order. A named unit must
    exist; with no name every planned Skill 50 unit is returned."""
    units = [u for u in plan.get("email_sequences") or []
             if isinstance(u, dict)]
    if sequence_id is not None:
        units = [u for u in units if u.get("id") == sequence_id]
        if not units:
            raise Refusal(
                f"launch plan has no email_sequences unit {sequence_id!r}")
    else:
        units = [u for u in units
                 if u.get("provider") == LAUNCH_SEQUENCE_PROVIDER]
    if not units:
        raise Refusal("launch plan plans no Skill 50 email sequence")
    for unit in units:
        uid = unit.get("id")
        if unit.get("provider") != LAUNCH_SEQUENCE_PROVIDER:
            raise Refusal(
                f"email sequence {uid!r} provider is "
                f"{unit.get('provider')!r}, expected "
                f"{LAUNCH_SEQUENCE_PROVIDER!r}")
        if unit.get("draft_only") is not True:
            raise Refusal(f"email sequence {uid!r} is not draft_only")
        if unit.get("kind") not in LAUNCH_SEQUENCE_PROFILES:
            raise Refusal(
                f"email sequence {uid!r} kind {unit.get('kind')!r} has no "
                "Skill 50 launch sequence profile")
        family = FAMILIES[unit["kind"]]
        declared = unit.get("email_count")
        if declared != family["email_count"]:
            raise Refusal(
                f"email sequence {uid!r} declares {declared!r} emails but the "
                f"{family['kind']} family ({family['profile']}) fixes exactly "
                f"{family['email_count']} — a count mismatch is never padded "
                "and never trimmed; fix the plan or extend the registry")
    return units


def adapt_launch_plan(session: Dict[str, Any], launch: Dict[str, Any],
                      approval: Dict[str, Any], brand_facts: Dict[str, Any],
                      landing_facts: Dict[str, Any], launch_plan: Dict[str, Any],
                      *, sequence_id: Optional[str] = None,
                      full_launch_plan: Optional[Dict[str, Any]] = None,
                      **adapt_kwargs: Any) -> list:
    """Launch mode: read the shared launch answers and the shared launch plan,
    and emit one locked brief per planned Skill 50 sequence.

    The Skill 50 one-block questionnaire is never read, asked, or attested:
    each brief carries intake_mode "signature_launch" and the same approved
    provenance the single-profile path emits. Returns
    [{"sequence_id", "kind", "brief"}, ...] in plan order.

    `full_launch_plan` is the L01 full launch plan beside the launch record
    (typed `launch_answers` + `launch_calendar`); the session's own
    `launch_plan` is the fallback, so the real producer output is consumed
    without the caller threading it twice.
    """
    _validate_launch_plan(launch_plan)
    plan_launch_id = launch_plan.get("launch_id")
    if not _nonempty_str(plan_launch_id) \
            or plan_launch_id != launch.get("launch_id"):
        raise Refusal(
            "launch plan launch_id does not match the launch record: the "
            "plan belongs to another launch")
    full = full_launch_plan
    if full is None and isinstance(session, dict):
        cand = session.get("launch_plan")
        if isinstance(cand, dict) and cand.get("launch_answers"):
            full = cand
    briefs = []
    for unit in _launch_sequences(launch_plan, sequence_id):
        profile, objective = LAUNCH_SEQUENCE_PROFILES[unit["kind"]]
        brief = adapt(session, launch, approval, brand_facts, landing_facts,
                      profile=profile, objective=objective,
                      full_launch_plan=full, **adapt_kwargs)
        briefs.append({"sequence_id": unit["id"], "kind": unit["kind"],
                       "brief": brief})
    return briefs


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
          landing_facts_ref: str = "landing-facts document",
          profile: str = PROFILE,
          objective: Optional[str] = None,
          full_launch_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate the five launch artifacts and emit the locked brief.

    `profile` selects which approved launch family the brief locks (launch mode
    passes one per planned email_sequences unit); it is resolved against the ONE
    profile registry, so an unknown profile is a refusal, never a guess. The
    default is the main landing-10 family, so the original single-brief CLI path
    is unchanged. `objective` defaults to the family's objective and may not
    contradict it. `full_launch_plan` is the L01 full launch plan beside the
    launch record (pages + emails + texts + automations, carrying the typed
    `launch_answers` block and `launch_calendar`); when present the session
    consumer reads its typed block, otherwise the session ledger.

    Raises Refusal on any defect. The emitted brief is the shape
    tools/prove-email.py consumes under intake_mode signature_launch.
    """
    if full_launch_plan is None and isinstance(session, dict):
        cand = session.get("launch_plan")
        if isinstance(cand, dict) and cand.get("launch_answers"):
            full_launch_plan = cand
    _load_contract()
    registry = _registry()
    family = launch_profiles.family_for(profile, registry)
    if family is None:
        raise Refusal(
            "profile %r is not a registered launch email family (%s): a brief "
            "cannot be locked against an unknown family"
            % (profile, ", ".join(sorted(FAMILIES)) or "registry empty"))
    if objective is None:
        objective = family["objective"]
    elif objective != family["objective"]:
        raise Refusal(
            "objective %r contradicts the %s family objective %r — the "
            "objective follows the email's job, never the caller's guess"
            % (objective, family["kind"], family["objective"]))
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
    # Real L01 new_session() keys the lifecycle as `state` (collecting -> ...
    # -> approved); the handcrafted adapter fixtures use `status`. Read the
    # real key first, fall back to the legacy alias — never the reverse.
    session_state = session.get("state", session.get("status"))
    if session_state not in s49.BUILDABLE_SESSION_STATES:
        raise Refusal(
            f"intake session state is {session_state!r}: only an "
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
    record_ref = _profile_record_ref(family)
    constant_prov = _prov("verified_existing", "existing_verified_catalog",
                          record_ref)
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
        "objective": objective,
        "buyer_type": "all",
        "offer": offer_answer,
        "brand_voice": brand_voice,
        "sequence_position": family["sequence_position"],
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
            "profile": family["profile"],
            "family_kind": family["kind"],
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
                "status": session.get("state", session.get("status")),
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
        "family": _family_block(family, registry),
        "session_contract": _consume_session_contract(
            session, family, full_launch_plan),
    }
    return brief


def _family_block(family: Dict[str, Any], registry: Dict[str, Any]) -> Dict[str, Any]:
    """The family the brief is locked for, as typed data. The prover checks it
    against the locked answers (wrong family fails), and P4 emission copies the
    eligibility / lifecycle / sender metadata from it so L07 consumes the same
    typed values the gate certified."""
    return {
        "kind": family["kind"],
        "profile": family["profile"],
        "sequence_position": family["sequence_position"],
        "sequence_id": family["sequence_id"],
        "source_record": family["sequence_record"],
        "purpose": family["purpose"],
        "destination": family["destination"],
        "email_count": family["email_count"],
        "preview_count": family["preview_count"],
        "subject_count": family["subject_count"],
        "paired_variants": {
            "pairs": ["A", "B"],
            "subjects": family["subject_count"],
            "previews": family["preview_count"],
        },
        "timing": family["timing"],
        "eligibility": _deep_copy(family["eligibility"]),
        "lifecycle": _deep_copy(family["lifecycle"]),
        "sender": _deep_copy(family["sender"]),
        "overrides": _deep_copy(family["overrides"]),
        "registry_version": registry.get("registry_version"),
    }


def _deep_copy(value: Any) -> Any:
    """Deep copy that keeps JSON types EXACTLY (a boolean stays a boolean; a
    timestamp stays the confirmed string it was — never coerced)."""
    return json.loads(json.dumps(value))


# ---------------------------------------------------------------------------
# L01 session contract consumer
# ---------------------------------------------------------------------------
def _session_contract_path() -> Optional[Path]:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent.joinpath(*SESSION_CONTRACT_REL)
        if candidate.is_file():
            return candidate
    return None


def _typed_value(name: str, value: Any, spec: Any) -> Any:
    """Validate one typed value declared by the session contract. Fail closed:
    a value whose type the contract declares and that does not match is a
    refusal, never a quiet coercion (the exact defect class: a string 'No'
    read as a boolean)."""
    expected = spec.get("type") if isinstance(spec, dict) else spec
    checks = {
        "boolean": lambda v: isinstance(v, bool),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "string": lambda v: isinstance(v, str),
        "timestamp": lambda v: isinstance(v, str) and bool(v.strip()),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    if expected in checks and not checks[expected](value):
        raise Refusal(
            "session contract field %r is declared %s but carries %r — a typed "
            "value is never coerced" % (name, expected, type(value).__name__))
    if isinstance(spec, dict) and spec.get("confirmed") is True \
            and not (isinstance(value, dict) and value.get("confirmed") is True):
        raise Refusal(
            "session contract field %r must carry a confirmed value "
            "(confirmed: true), never an assumed one" % name)
    return _deep_copy(value)


def _metadata_sources(session: Dict[str, Any], family: Dict[str, Any]) -> Dict[str, Any]:
    """Typed eligibility / lifecycle / sender metadata carried to L07.

    The approved launch family is the authority for each family's rules; the
    session answers may override a value ONLY when they carry a confirmed,
    typed entry. Nothing here is string-coerced and nothing is defaulted from a
    guess."""
    answers = s49.session_answers(session)
    out: Dict[str, Any] = {}
    for key in ("eligibility", "lifecycle", "sender"):
        from_session = answers.get(key)
        if isinstance(from_session, dict) and from_session.get("confirmed") is True:
            out[key] = _deep_copy(from_session)
            out.setdefault("provenance", {})[key] = {
                "state": "provided", "source_kind": "owner",
                "source_ref": "approved launch intake session answers.%s" % key,
            }
        else:
            out[key] = _deep_copy(family[key])
            out.setdefault("provenance", {})[key] = {
                "state": "verified_existing",
                "source_kind": "existing_verified_catalog",
                "source_ref": family["sequence_record"],
            }
    return out


def _consume_session_contract(session: Dict[str, Any],
                              family: Dict[str, Any],
                              full_launch_plan: Optional[Dict[str, Any]] = None,
                              ) -> Dict[str, Any]:
    """Consume the versioned L01 session contract when it is published.

    Absent contract: the brief says so explicitly and names the blocked
    acceptance, rather than inventing a version or silently skipping the
    consumer. Present contract, two shapes:
      * legacy (agreed-shape): `required_answers` + `typed_fields`;
      * real L01 (signature-launch-session-contract/v1, contract_version
        1.0.0): `launch_answers[]` descriptors (id + ledger_keys) with the
        required behavior under `consumer_requirements.L06_skill50`, and the
        fixture at `fixtures/session_contract.complete_plan.json`.
    Both shapes: the declared version is checked, every declared required
    answer must exist in the approved session ledger, and every declared
    typed field is validated (booleans stay booleans — the string "No" is
    never truthy). A present contract with missing required answers is a
    refusal, never an empty typed:{}.
    """
    path = _session_contract_path()
    metadata = _metadata_sources(session, family)
    rel = "/".join(SESSION_CONTRACT_REL)
    if path is None:
        return {
            "state": "absent",
            "ref": rel,
            "family": family["profile"],
            "typed_metadata": metadata,
            "blocked_acceptance": (
                "L01 has not published %s on this branch (no commits beyond "
                "origin/main), so the consumer is exercised against the agreed "
                "shape only; re-run this adapter once L01 lands to consume the "
                "real fixture" % rel),
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal("session contract at %s is unreadable: %s" % (path, exc))
    if not isinstance(doc, dict):
        raise Refusal("session contract at %s is not a JSON object" % path)
    if doc.get("contract") not in (None, "signature-launch-session"):
        raise Refusal("session contract at %s declares contract %r, not "
                      "'signature-launch-session'" % (path, doc.get("contract")))
    # Real L01 contract identifies as schema
    # signature-launch-session-contract/v1 with contract_version "1.0.0".
    version = doc.get("contract_version")
    if not (isinstance(version, str)
            and version.split(".")[0] == SUPPORTED_SESSION_CONTRACT_MAJOR):
        raise Refusal("session contract version %r is not supported (major %s)"
                      % (version, SUPPORTED_SESSION_CONTRACT_MAJOR))
    if "launch_answers" in doc:
        return _consume_l01_contract(doc, session, family, metadata,
                                     full_launch_plan)
    answers = s49.session_answers(session)
    missing = [name for name in (doc.get("required_answers") or [])
               if name not in answers]
    if missing:
        raise Refusal(
            "approved session carries no answer for session-contract "
            "requirement(s): %s" % ", ".join(sorted(missing)))
    typed = {}
    for name, spec in (doc.get("typed_fields") or {}).items():
        if name in answers:
            typed[name] = _typed_value(name, answers[name], spec)
    return {
        "state": "consumed",
        "ref": rel,
        "contract_version": version,
        "family": family["profile"],
        "typed": typed,
        "typed_metadata": metadata,
    }


# The eight launch answers, keyed by the session-ledger key the consumer
# reads and the Python type the contract demands. States gate separately:
# only `provided` (or verified_existing) counts as ready — a
# recommended_unapproved or unknown entry is carried, never approved.
_L01_LEDGER_TYPES = {
    "launch.launch_at": "timestamp",
    "launch.doors_open_at": "timestamp",
    "launch.doors_close_at": "timestamp",
    "launch.timezone": "string",
    "launch.channels": "array",
    "launch.conversation_ai": "boolean",
    "launch.access_delivery": "boolean",
    "launch.payment_plans": "boolean",
    "launch.sender_name": "string",
    "launch.reply_to_email": "string",
    "launch.a2p_ready": "boolean",
}
_L01_READY_STATES = ("provided", "verified_existing")
_L01_BOOLEAN_ANSWERS = ("launch.conversation_ai", "launch.access_delivery",
                        "launch.payment_plans", "launch.a2p_ready")


def _l01_ledger(session: Dict[str, Any],
                full_launch_plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The typed launch_answers block: the full plan's block wins (it is the
    assembled, digest-bound record), the session ledger is the fallback."""
    if isinstance(full_launch_plan, dict):
        block = full_launch_plan.get("launch_answers")
        if isinstance(block, dict) and block:
            return block
    answers = s49.session_answers(session)
    return answers if isinstance(answers, dict) else {}


def _consume_l01_contract(doc: Dict[str, Any], session: Dict[str, Any],
                          family: Dict[str, Any], metadata: Dict[str, Any],
                          full_launch_plan: Optional[Dict[str, Any]]
                          ) -> Dict[str, Any]:
    """Consume the real L01 session contract (contract_version 1.0.0).

    Required coverage comes from `launch_answers[].ledger_keys`: every key
    must exist in the session/full-plan ledger or the consumer refuses by
    name — never an empty typed:{}. Typed values are validated by the
    contract's own rules (booleans are real booleans; the string "No" is
    never truthy; recommended_unapproved/unknown is never ready); sender
    names and reply-to mailboxes must be present and non-empty; deadlines
    come from launch_calendar ISO timestamps with a real IANA zone.
    """
    req = doc.get("consumer_requirements") or {}
    l06_req = req.get("L06_skill50") or {}
    descriptors = doc.get("launch_answers") or []
    if not isinstance(descriptors, list) or not descriptors:
        raise Refusal("session contract declares no launch_answers: "
                      "required coverage cannot be proven")
    ledger = _l01_ledger(session, full_launch_plan)
    required_keys = sorted(
        {k for d in descriptors if isinstance(d, dict)
         for k in (d.get("ledger_keys") or [])})
    missing = [k for k in required_keys if k not in ledger]
    if missing:
        raise Refusal(
            "approved session carries no answer for L01 session-contract "
            "requirement(s): %s" % ", ".join(missing))
    typed: Dict[str, Any] = {}
    for key in required_keys:
        entry = ledger.get(key)
        if not isinstance(entry, dict) or "value" not in entry:
            raise Refusal(
                "session-contract answer %r is not a ledger entry "
                "(value is required)" % key)
        expected = _L01_LEDGER_TYPES.get(key)
        state = entry.get("state")
        value = entry.get("value")
        if expected is not None:
            typed[key] = _typed_value(key, value, expected)
        else:
            typed[key] = _deep_copy(value)
        ready = state in _L01_READY_STATES
        typed[key + ".state"] = state
        typed[key + ".ready"] = ready
        if key in _L01_BOOLEAN_ANSWERS and not isinstance(value, bool):
            raise Refusal(
                "session contract field %r is declared boolean but carries "
                "%r — a typed value is never coerced" % (key, type(value).__name__))
        if key in ("launch.sender_name", "launch.reply_to_email") \
                and not _nonempty_str(value):
            raise Refusal(
                "session contract field %r must be present and non-empty "
                "before any email is composed — a missing sender blocks by "
                "name, never a placeholder" % key)
    # Text work only when 'text' is present in the channels array — never
    # from a display string. a2p_ready/conversation_ai/access_delivery/
    # payment_plans that are non-boolean or not ready count as NOT ready.
    channels = typed.get("launch.channels")
    text_planned = isinstance(channels, list) and "text" in channels
    readiness = {}
    for key in _L01_BOOLEAN_ANSWERS:
        readiness[key] = typed.get(key + ".ready") is True \
            and isinstance(typed.get(key), bool) and typed[key] is True
    out: Dict[str, Any] = {
        "state": "consumed",
        "ref": "/".join(SESSION_CONTRACT_REL),
        "contract_version": doc.get("contract_version"),
        "family": family["profile"],
        "typed": typed,
        "typed_metadata": metadata,
        "channels": channels,
        "text_planned": text_planned,
        "readiness": readiness,
    }
    calendar = (full_launch_plan.get("launch_calendar")
                if isinstance(full_launch_plan, dict) else None)
    if isinstance(calendar, dict) and calendar:
        out["launch_calendar"] = _deep_copy(calendar)
    if isinstance(l06_req, dict) and l06_req.get("reads"):
        out["contract_reads"] = list(l06_req["reads"])
    digest_doc = doc.get("digest") or {}
    if isinstance(digest_doc, dict) and digest_doc.get("value_shape"):
        out["digest_rule"] = {
            "algorithm": digest_doc.get("algorithm"),
            "canonicalization": digest_doc.get("canonicalization"),
            "value_shape": digest_doc.get("value_shape"),
        }
    return out


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
            # The L01 session contract requires these ledger keys and the
            # access destination; no intake question produces them, so the
            # fixture states them the way an operator would supply them.
            **{
                key: {"value": value, "state": "provided",
                      "source_ref": "operator-supplied fixture fact %s" % key}
                for key, value in (
                    ("launch.a2p_ready", False),
                    ("launch.access_delivery", True),
                    ("launch.access_url", "https://momentum-method.example/access"),
                    ("launch.channels", ["email"]),
                    ("launch.conversation_ai", False),
                    ("launch.doors_close_at", "2026-11-10T23:59:00-05:00"),
                    ("launch.doors_open_at", "2026-11-03T09:00:00-05:00"),
                    ("launch.launch_at", "2026-11-03T12:00:00-05:00"),
                    ("launch.payment_plans", False),
                    ("launch.reply_to_email", "hello@momentum-method.example"),
                    ("launch.sender_name", "Jordan Marsh"),
                    ("launch.timezone", "America/New_York"),
                )
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


def build_launch_plan_fixture() -> Dict[str, Any]:
    """A U-CONTRACT launch plan for the fixture launch: every planned Skill 50
    sequence kind, so launch mode is exercised end to end. Fictional."""
    sequences = [
        ("email_pre_launch", "pre_launch"),
        ("email_main_launch", "main_launch"),
        ("email_doors_closing", "doors_closing"),
        ("email_upsell_1", "upsell_followup"),
        ("email_downsell_1", "downsell_followup"),
        ("email_abandoned_checkout", "abandoned_checkout"),
        ("email_welcome_access", "welcome_access"),
    ]
    return {
        "schema_version": "1.0.0",
        "launch_id": "launch-fixture-0001",
        "offer": {"name": "The Momentum Method", "price_usd": 497,
                  "currency": "USD", "payment_plans": False},
        "launch_calendar": {
            "launch_at": "2026-11-03T12:00:00-05:00",
            "doors_open_at": "2026-11-03T09:00:00-05:00",
            "doors_close_at": "2026-11-10T23:59:00-05:00",
            "timezone": "America/New_York",
        },
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "pages": [{"id": "page_landing", "kind": "landing",
                   "url": None, "waits_for": []}],
        "email_sequences": [
            {"id": uid, "kind": kind, "provider": "skill50",
             "email_count": FAMILIES[kind]["email_count"],
             "draft_only": True, "waits_for": []}
            for uid, kind in sequences
        ],
        "text_sets": [],
        "automations": [],
    }


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

    # --- EM-B3 launch mode: the shared launch plan selects the sequences -----
    lfx = build_fixtures()
    plan = build_launch_plan_fixture()
    try:
        adapted = adapt_launch_plan(
            lfx["session"], lfx["launch"], lfx["approval"],
            lfx["brand_facts"], lfx["landing_facts"], plan,
            worker_identity_ref=lfx["worker_identity_ref"])
        say(len(adapted) == len(plan["email_sequences"]),
            "launch mode emits one brief per planned Skill 50 sequence")
        say({a["sequence_id"] for a in adapted}
            == {u["id"] for u in plan["email_sequences"]},
            "every planned sequence id is covered")
        by_kind = {a["kind"]: a["brief"] for a in adapted}
        say(by_kind["abandoned_checkout"]["answers"]["objective"]
            == "abandoned-cart"
            and by_kind["upsell_followup"]["answers"]["objective"] == "upsell"
            and by_kind["downsell_followup"]["answers"]["objective"]
            == "downsell",
            "objective follows the planned sequence kind")
        say(by_kind["pre_launch"]["answers"]["sequence_position"]
            == "signature-launch-prelaunch"
            and by_kind["main_launch"]["answers"]["sequence_position"]
            == PROFILE,
            "sequence_position follows the planned profile")
        say(all("asked_all_at_once" not in a["brief"]
                and "question_block_msg_id" not in a["brief"]
                for a in adapted),
            "launch mode never emits the legacy questionnaire attestation")
        say(all(a["brief"]["intake_mode"] == "signature_launch"
                for a in adapted),
            "every launch brief carries intake_mode signature_launch")
        say(all(a["brief"].get("family", {}).get("kind") == a["kind"]
                and a["brief"]["family"]["profile"]
                == a["brief"]["launch_provenance"]["profile"]
                for a in adapted),
            "every launch brief carries the typed family block it locked")
        say(all(a["brief"].get("session_contract", {}).get("state")
                in ("absent", "consumed")
                and a["brief"]["session_contract"].get("typed_metadata")
                for a in adapted),
            "session contract state is explicit and typed metadata is carried")
        say({a["brief"]["family"]["kind"]: a["brief"]["family"]["email_count"]
             for a in adapted}
            == {k: FAMILIES[k]["email_count"] for k in FAMILIES},
            "each brief's family count equals the registry count")
        one = adapt_launch_plan(
            lfx["session"], lfx["launch"], lfx["approval"],
            lfx["brand_facts"], lfx["landing_facts"], plan,
            sequence_id="email_main_launch",
            worker_identity_ref=lfx["worker_identity_ref"])
        say(len(one) == 1
            and one[0]["brief"]["answers"]["sequence_position"] == PROFILE,
            "a named sequence adapts to exactly one brief")
    except Refusal as exc:
        say(False, f"launch mode adapts a valid plan (refused: {exc})")

    def plan_refuses(label: str, mutate) -> None:
        bad = json.loads(json.dumps(plan))
        mutate(bad)
        try:
            adapt_launch_plan(
                lfx["session"], lfx["launch"], lfx["approval"],
                lfx["brand_facts"], lfx["landing_facts"], bad,
                worker_identity_ref=lfx["worker_identity_ref"])
            say(False, label)
        except Refusal:
            say(True, label)

    plan_refuses("plan bound to another launch is refused",
                 lambda p: p.__setitem__("launch_id", "another-launch"))
    plan_refuses("plan violating the shared contract is refused",
                 lambda p: p["launch_calendar"].pop("timezone"))
    plan_refuses("plan with a non-draft email sequence is refused",
                 lambda p: p["email_sequences"][0].__setitem__(
                     "draft_only", False))
    plan_refuses("plan with an unknown sequence kind is refused",
                 lambda p: p["email_sequences"][0].__setitem__(
                     "kind", "follow_up"))
    plan_refuses("plan with the wrong count for the family is refused",
                 lambda p: p["email_sequences"][3].__setitem__(
                     "email_count", 2))
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
    ap.add_argument("--launch-plan",
                    help="U-CONTRACT launch plan JSON (launch mode): emit one "
                         "brief per planned Skill 50 email sequence")
    ap.add_argument("--sequence",
                    help="launch mode: the email_sequences unit id to adapt "
                         "(default: every planned Skill 50 sequence)")
    ap.add_argument("--out", help="write the locked brief here "
                                  "(default: stdout)")
    ap.add_argument("--out-dir",
                    help="launch mode: write each brief to "
                         "BRIEF-<sequence-id>.json in this directory")
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
    if args.launch_plan and (args.out and args.out_dir):
        print("USAGE ERROR: pass --out or --out-dir in launch mode, not both",
              file=sys.stderr)
        return EXIT_USAGE
    session, _, _ = _read_json_arg(args.session, "intake session")
    launch, _, _ = _read_json_arg(args.launch, "launch record")
    approval, _, _ = _read_json_arg(args.approval, "approval record")
    brand_facts, brand_sha, brand_name = _read_json_arg(
        args.brand_facts, "brand facts")
    landing_facts, landing_sha, landing_name = _read_json_arg(
        args.landing_facts, "landing facts")
    adapt_kwargs = {
        "worker_identity_ref": args.worker_identity or "",
        "brand_facts_sha256": brand_sha,
        "landing_facts_sha256": landing_sha,
        "brand_facts_ref": brand_name,
        "landing_facts_ref": landing_name,
    }
    try:
        if args.launch_plan:
            launch_plan, _, _ = _read_json_arg(args.launch_plan, "launch plan")
            adapted = adapt_launch_plan(
                session, launch, approval, brand_facts, landing_facts,
                launch_plan, sequence_id=args.sequence, **adapt_kwargs)
            if not args.out and not args.out_dir:
                sys.stdout.write(json.dumps(
                    {"launch_id": launch_plan.get("launch_id"),
                     "briefs": adapted}, indent=2) + "\n")
                return EXIT_OK
            if args.out:
                if len(adapted) != 1:
                    print("USAGE ERROR: --out needs exactly one brief; pass "
                          "--sequence or use --out-dir", file=sys.stderr)
                    return EXIT_USAGE
                brief = adapted[0]["brief"]
                try:
                    Path(args.out).write_text(
                        json.dumps(brief, indent=2) + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"USAGE/IO ERROR: cannot write brief to "
                          f"{args.out}: {exc}", file=sys.stderr)
                    return EXIT_USAGE
                prov = brief["launch_provenance"]
                print(f"ADAPTED: locked brief for {prov['profile']} written "
                      f"to {args.out} (launch {prov['launch_id']}, plan_hash "
                      f"{prov['plan_hash'][:12]}..., approval "
                      f"{prov['approval']['approval_id']})")
                return EXIT_OK
            out_dir = Path(args.out_dir)
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                for item in adapted:
                    target = out_dir / ("BRIEF-%s.json" % item["sequence_id"])
                    target.write_text(
                        json.dumps(item["brief"], indent=2) + "\n",
                        encoding="utf-8")
            except OSError as exc:
                print(f"USAGE/IO ERROR: cannot write briefs to "
                      f"{args.out_dir}: {exc}", file=sys.stderr)
                return EXIT_USAGE
            print(f"ADAPTED: {len(adapted)} locked launch briefs written to "
                  f"{args.out_dir} (launch "
                  f"{launch_plan.get('launch_id')})")
            return EXIT_OK
        brief = adapt(session, launch, approval, brand_facts, landing_facts,
                      **adapt_kwargs)
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
