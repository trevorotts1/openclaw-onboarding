"""presentation_job/persona_context.py -- PRES-031: scoped persona context.

WHY THIS EXISTS: phases.py called persona.resolve_for_phase(run_dir,
phase.id) with NO client context -- the persona seam received generic phase
text instead of this client's audience, offer and presentation topic. Two
clients with different audiences could receive identically-governed voice,
and one client's cached bundle could leak into another run.

CONTRACT (SPEC PRES-031):
  1. Build a canonical scoped persona context from sealed intake:
     client/company/presentation IDs, audience, topic, offer, approved owner
     voice, relevant sales framework. Pass it explicitly to the shared
     persona seam (never generic phase text alone).
  2. Department execution persona and client-facing voice are SEPARATE
     explicit fields with scope and precedence. The owner-selected voice is
     preserved; the canonical dual-persona algorithm is not replaced with a
     hardcoded celebrity/default model.
  3. The complete versioned bundle caches by input/context hash (scoped by
     client+presentation -- never shared across them) and the relevant
     task-mode sections attach to every copy/prompt/speech/page/VSL/QC unit.
  4. Schema validation + model-aware section selection replace the
     arbitrary 8000-character slice. Required governance rules are never
     dropped silently.
  5. Sales doctrine and no-pitch teaching boundaries validate semantically
     against the selected frame/offer; rework narrows to violated units
     while whole-deck coherence review is retained.

SOURCES (precedence, never fabricated):
  working/copy/sp_intake.json -- sealed signature record (q3 audience, q4
      story/owner voice, q5 teaching topic, q7 offer ledger, signature_frame)
  working/copy/intake.json    -- client_name, requester_chat_id,
      deck_slug, presentation_type
  state.json intake            -- deck_slug fallback
  run_dir.name                 -- presentation/run identity fallback

The context hash covers every field that scopes the bundle; any client,
audience, topic, offer, voice or framework change is a different context
(a different cache key, a different bundle).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

CONTEXT_SCHEMA_VERSION = 1
BUNDLE_CACHE_VERSION = "persona-bundle-v1"

# Required governance rule markers: a selected section set missing any of
# these markers is INCOMPLETE (silent-drop refusal, never silent truncation).
# Markers are matched case-insensitively against the assembled governance
# text. The bundle fails closed (preflight error) when a required marker is
# absent after selection -- the caller must restructure context, never ship
# a bundle with dropped governance.
REQUIRED_GOVERNANCE_MARKERS = (
    "STYLE-INSPIRED, NEVER IMPERSONATION",
    "second person",
    "no-pitch",
)

# Phase -> sales framework relevant to its doctrine check (step 5). The
# framework name travels in the context so the seam and the teaching/pitch
# validators reason over the same declared doctrine.
PHASE_FRAMEWORK = {
    "P-SP-STRUCTURE": "signature-structure",
    "P4-COPY": "signature-story",
    "P-SP-P3-HYGIENE": "transformational-teaching",
    "P4-PROMPT": "purpose-pitch",
    "P-U-SALES-COPY": "offer-sales-page",
    "P-U-CHECKOUT-COPY": "offer-checkout",
    "P-U-VSL-COPY": "offer-vsl",
    "P-U-VSL-RESEARCH": "offer-vsl",
    "P9-SPEECH": "purpose-pitch",
    "P-SPEECH-QC": "purpose-pitch",
    "P7-TELEPROMPTER": "purpose-pitch",
}


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")


def build_persona_context(run_dir: Path, phase_id: str) -> Dict[str, Any]:
    """Canonical scoped persona context for one (run, phase).

    Reads sealed intake only; every field records its source. Missing
    intake fields are "" with source "absent" -- never fabricated. The
    context_hash covers all scoping fields (client, presentation, audience,
    topic, offer, owner voice, framework, phase).
    """
    sp = _read_json_dict(run_dir / "working" / "copy" / "sp_intake.json")
    intake = _read_json_dict(run_dir / "working" / "copy" / "intake.json")
    state = _read_json_dict(run_dir / "state.json")
    state_intake = state.get("intake") if isinstance(
        state.get("intake"), dict) else {}

    answers = sp.get("answers") if isinstance(sp.get("answers"), dict) else {}

    def _field(value: Any, source: str) -> Dict[str, Any]:
        text = str(value or "").strip()
        return {"value": text,
                "source": source if text else "absent"}

    audience = _field(answers.get("q3"), "sp_intake.answers.q3")
    topic = _field(answers.get("q5") or sp.get("teaching_topic"),
                   "sp_intake.answers.q5")
    offer_products = sp.get("q7_offer_products") or sp.get(
        "offer_token_ledger") or []
    if isinstance(offer_products, str):
        offer_products = [offer_products]
    offer = _field(answers.get("q7") or "; ".join(
        str(o) for o in offer_products if o), "sp_intake.answers.q7")
    owner_voice = _field(
        answers.get("q8") or answers.get("q4") or sp.get("owner_voice") or
        intake.get("owner_voice"), "sp_intake.answers.q8/q4")
    frame = _field(sp.get("signature_frame"), "sp_intake.signature_frame")

    client_name = str(intake.get("client_name") or state_intake.get("client")
                      or state_intake.get("client_name") or "")
    deck_slug = str(intake.get("deck_slug") or state_intake.get("deck_slug")
                    or run_dir.name or "")
    company_id = _slug(client_name) or "unscoped-client"
    presentation_id = _slug(deck_slug) or _slug(run_dir.name) or \
        "unscoped-presentation"
    run_id = run_dir.name

    # Department execution persona vs client-facing voice: separate fields,
    # separate scope, explicit precedence. The execution persona governs HOW
    # the department writes (role SOP voice); the client voice governs WHAT
    # the audience hears (owner-selected, audience-bound). Owner voice wins
    # on audience-facing surfaces; execution discipline wins on QC/repair
    # surfaces. Neither replaces the dual-persona blend -- both feed it.
    execution_persona = {
        "scope": "department",
        "role": "presentations-department-worker",
        "precedence": ("execution discipline governs structure, QC and "
                       "repair surfaces; client voice governs "
                       "audience-facing prose"),
    }
    client_voice = {
        "scope": "client-audience",
        "owner_voice": owner_voice["value"],
        "owner_voice_source": owner_voice["source"],
        "audience": audience["value"],
        "precedence": ("owner-selected voice is preserved verbatim into "
                       "the blend; never replaced with a hardcoded "
                       "celebrity/default model"),
    }

    framework = PHASE_FRAMEWORK.get(phase_id, "signature-general")

    context = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "client_id": company_id,
        "company_id": company_id,
        "presentation_id": presentation_id,
        "run_id": run_id,
        "phase_id": phase_id,
        "audience": audience,
        "topic": topic,
        "offer": {"value": offer["value"],
                  "products": [str(o) for o in offer_products if o],
                  "source": offer["source"]},
        "owner_voice": owner_voice,
        "signature_frame": frame,
        "framework": framework,
        "execution_persona": execution_persona,
        "client_voice": client_voice,
    }
    context["context_hash"] = hash_context(context)
    return context


def hash_context(context: Dict[str, Any]) -> str:
    """Content hash over every scoping field. Any client/audience/topic/
    offer/voice/framework/phase change is a different context."""
    scope = {
        "v": context.get("schema_version"),
        "client": context.get("client_id"),
        "presentation": context.get("presentation_id"),
        "run": context.get("run_id"),
        "phase": context.get("phase_id"),
        "audience": (context.get("audience") or {}).get("value"),
        "topic": (context.get("topic") or {}).get("value"),
        "offer": (context.get("offer") or {}).get("value"),
        "owner_voice": (context.get("owner_voice") or {}).get("value"),
        "frame": (context.get("signature_frame") or {}).get("value"),
        "framework": context.get("framework"),
    }
    return hashlib.sha256(
        json.dumps(scope, sort_keys=True,
                   ensure_ascii=False).encode("utf-8")).hexdigest()


def cache_key_for(context: Dict[str, Any]) -> str:
    """Versioned bundle-cache key. Scoped by client+presentation+context:
    no cross-run reuse, ever. Two clients with different audiences, and two
    presentations for one client, hash differently by construction."""
    return "|".join((BUNDLE_CACHE_VERSION,
                     str(context.get("client_id")),
                     str(context.get("presentation_id")),
                     str(context.get("context_hash"))))


# ---------------------------------------------------------------------------
# Bundle cache: complete versioned bundles by scoped key.
# ---------------------------------------------------------------------------

def _bundle_cache_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "persona_bundles.json"


def read_bundle_cache(run_dir: Path) -> Dict[str, Any]:
    path = _bundle_cache_path(run_dir)
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def lookup_bundle(run_dir: Path,
                  context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The cached COMPLETE bundle for this exact scoped context, or None.
    A hit reuses the full bundle (never a truncated slice); a context change
    is a different key (never a stale reuse)."""
    key = cache_key_for(context)
    entry = read_bundle_cache(run_dir).get(key)
    if not isinstance(entry, dict):
        return None
    if entry.get("context_hash") != context.get("context_hash"):
        return None
    bundle = entry.get("bundle")
    return bundle if isinstance(bundle, dict) else None


def store_bundle(run_dir: Path, context: Dict[str, Any],
                 bundle: Dict[str, Any]) -> None:
    """Cache the COMPLETE bundle under the scoped key (atomic write)."""
    from presentation_job.checkpoint import atomic_write_text
    path = _bundle_cache_path(run_dir)
    try:
        cache = read_bundle_cache(run_dir)
        cache[cache_key_for(context)] = {
            "context_hash": context.get("context_hash"),
            "client_id": context.get("client_id"),
            "presentation_id": context.get("presentation_id"),
            "phase_id": context.get("phase_id"),
            "cached_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc).isoformat(
                    timespec="seconds"),
            "bundle": bundle,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            path, json.dumps(cache, indent=2, ensure_ascii=False))
    except OSError:
        pass  # cache loss costs a re-resolve, never correctness


# ---------------------------------------------------------------------------
# Schema validation + model-aware section selection (replaces the 8000-char
# slice). Required governance rules are never dropped silently.
# ---------------------------------------------------------------------------

BUNDLE_SCHEMA_REQUIRED = ("blend_directive", "voice", "resolved_audience",
                          "rationale")
BUNDLE_SCHEMA_OPTIONAL = ("task_personas", "persona_id", "persona_name",
                          "fallbacks", "catalog_version", "department",
                          "sop_slug", "job_text", "warnings", "selector")


def validate_bundle(bundle: Dict[str, Any]) -> List[str]:
    """Schema check for a persona bundle. Returns missing-required list
    (empty == valid). Unknown extra keys are tolerated (seam superset)."""
    if not isinstance(bundle, dict):
        return list(BUNDLE_SCHEMA_REQUIRED)
    return [k for k in BUNDLE_SCHEMA_REQUIRED
            if not bundle.get(k)]


def _char_budget(model_hint: Optional[str] = None) -> int:
    # Model-aware budgets: small-context providers get a tight budget with
    # explicit restructure; large-context providers carry the full bundle.
    # Floor: never below the size needed for required governance markers
    # (enforced by the marker check, not by budget arithmetic alone).
    hint = str(model_hint or "").lower()
    if any(m in hint for m in ("haiku", "flash", "mini", "small", "8b", "7b")):
        return 4000
    return 12000


def select_bundle_sections(bundle: Dict[str, Any], *,
                           phase_id: str = "",
                           model_hint: Optional[str] = None,
                           task_mode: str = "copy") -> Dict[str, Any]:
    """Assemble the governance text for one work unit from the COMPLETE
    cached bundle -- schema-validated, section-selected, never sliced.

    Selection order (all-or-nothing per tier):
      tier 1 (always): blend_directive + voice + resolved_audience summary
      tier 2 (task_mode in copy/prompt/speech/page/vsl/qc): rationale +
          task_personas relevant to the phase + guardrail restatement
      tier 3 (budget allows): fallbacks, catalog_version, selector notes

    Returns {text, sections, complete, missing_markers, budget}. When
    required governance markers would not fit / are absent, complete=False
    with the missing markers named -- the caller must preflight-fail with
    restructure guidance, never ship a silently-truncated bundle.
    """
    missing_schema = validate_bundle(bundle)
    budget = _char_budget(model_hint)
    if missing_schema:
        return {"text": "", "sections": [], "complete": False,
                "missing_markers": [],
                "missing_schema": missing_schema,
                "budget": budget,
                "why": "bundle fails schema: missing "
                       + ", ".join(missing_schema)}

    directive = str(bundle.get("blend_directive") or "")
    voice = bundle.get("voice")
    voice_text = json.dumps(voice, indent=2) if voice else ""
    audience = bundle.get("resolved_audience")
    audience_text = json.dumps(audience, indent=2) if audience else ""

    sections: List[Dict[str, str]] = []
    sections.append({"name": "blend_directive", "text": directive})
    sections.append({"name": "voice", "text": voice_text})
    sections.append({"name": "resolved_audience", "text": audience_text})

    if task_mode in ("copy", "prompt", "speech", "page", "vsl", "qc",
                     "render"):
        rationale = bundle.get("rationale")
        if rationale:
            sections.append(
                {"name": "rationale",
                 "text": json.dumps(rationale, indent=2)})
        task_personas = bundle.get("task_personas") or []
        if isinstance(task_personas, list) and task_personas:
            sections.append(
                {"name": "task_personas",
                 "text": json.dumps(task_personas, indent=2)})
        # Guardrail restatement: the no-impersonation + voice-preservation
        # rule rides every unit even if the directive is long.
        sections.append({
            "name": "governance_guardrails",
            "text": ("GOVERNANCE (applies to this unit): "
                     "STYLE-INSPIRED, NEVER IMPERSONATION -- adopt cadence "
                     "and register only, never impersonate. Write in second "
                     "person in the owner voice. Teaching units carry a "
                     "no-pitch boundary: no offer, price, CTA or scarcity "
                     "inside transformational teaching.")})

    text = "\n\n".join(
        f"### {s['name']}\n{s['text']}" for s in sections if s["text"])
    # Marker scope: the bundle's own directive must carry the
    # STYLE-INSPIRED guardrail (it is the seam's mandatory clause, not
    # something the appended governance_guardrails tier may supply on its
    # behalf -- a directive without it is a degraded bundle). The
    # audience-surface markers (second person, no-pitch) may be satisfied
    # by any selected section including the guardrails tier.
    directive_text = directive or ""
    missing_markers = []
    if REQUIRED_GOVERNANCE_MARKERS[0].lower() not in \
            directive_text.lower():
        missing_markers.append(REQUIRED_GOVERNANCE_MARKERS[0])
    for m in REQUIRED_GOVERNANCE_MARKERS[1:]:
        if m.lower() not in text.lower():
            missing_markers.append(m)
    if missing_markers:
        return {"text": text,
                "sections": [s["name"] for s in sections],
                "complete": False, "missing_markers": missing_markers,
                "missing_schema": [], "budget": budget,
                "why": "required governance markers absent after selection: "
                       + ", ".join(missing_markers)}
    if len(text) > budget:
        # Over budget WITH all markers present: keep tier-1 + guardrails
        # (the non-droppable core) and report the restructure need.
        core = "\n\n".join(
            f"### {s['name']}\n{s['text']}"
            for s in sections
            if s["name"] in ("blend_directive", "governance_guardrails"))
        core_missing = [m for m in REQUIRED_GOVERNANCE_MARKERS
                        if m.lower() not in core.lower()]
        return {"text": core,
                "sections": [s["name"] for s in sections
                             if s["name"] in ("blend_directive",
                                              "governance_guardrails")],
                "complete": not core_missing,
                "missing_markers": core_missing,
                "missing_schema": [], "budget": budget,
                "restructured": True,
                "why": ("bundle exceeds model budget "
                        f"({len(text)} > {budget}); core retained") if
                not core_missing else
                "bundle exceeds model budget AND core drops markers"}
    return {"text": text, "sections": [s["name"] for s in sections],
            "complete": True, "missing_markers": [],
            "missing_schema": [], "budget": budget}


# ---------------------------------------------------------------------------
# Doctrine checks (step 5): covert pitch in teaching, invented proof on
# sales pages / VSL. Pure functions over unit text + context, so QC and the
# engine share one implementation.
# ---------------------------------------------------------------------------

_PITCH_MARKERS = (
    "buy now", "order now", "enroll now", "join now", "sign up now",
    "limited time", "act now", "special offer", "discount", "% off",
    "price", "$", "payment", "checkout", "cta", "call to action",
    "guarantee", "bonus", "scarcity", "doors close", "cart",
)


def check_no_covert_pitch(unit_text: str, phase_id: str,
                          context: Dict[str, Any]) -> Dict[str, Any]:
    """Teaching phases (transformational-teaching framework) must not carry
    pitch markers. Sales/page/VSL phases are EXEMPT (their doctrine REQUIRES
    the offer) but their claims must come from the approved offer ledger
    (see check_offer_claims)."""
    framework = str(context.get("framework") or "")
    teaching = "teaching" in framework or phase_id == "P-SP-P3-HYGIENE"
    low = (unit_text or "").lower()
    hits = sorted({m for m in _PITCH_MARKERS if m in low})
    if teaching and hits:
        return {"ok": False, "phase_id": phase_id,
                "why": "covert pitch markers inside teaching unit: "
                       + ", ".join(hits)}
    return {"ok": True, "phase_id": phase_id, "markers": hits,
            "teaching_surface": teaching}


def check_offer_claims(unit_text: str,
                       context: Dict[str, Any]) -> Dict[str, Any]:
    """Sales/page/VSL units may only assert offer claims from the approved
    ledger (q7 products). Proof language (testimonials, revenue figures,
    guarantees) with no ledger anchor is invented proof -> fail."""
    offer = context.get("offer") or {}
    products = [str(p) for p in (offer.get("products") or []) if p]
    low = (unit_text or "").lower()
    proof_words = ("testimonial", "proof", "results", "revenue", "income",
                   "guarantee", "case study", "clients earned", "made $")
    proof_hit = any(w in low for w in proof_words)
    offer_anchored = any(p.lower()[:24] in low for p in products) \
        if products else False
    if proof_hit and products and not offer_anchored:
        return {"ok": False,
                "why": "proof language without approved-offer anchor; "
                       "assert only ledger claims: " + "; ".join(products)}
    return {"ok": True, "offer_anchored": offer_anchored,
            "proof_language": proof_hit}
