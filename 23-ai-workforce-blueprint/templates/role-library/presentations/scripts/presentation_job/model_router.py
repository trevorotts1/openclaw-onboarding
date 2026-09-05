#!/usr/bin/env python3
"""model_router.py -- FIX 7: model routing by client resource profile.

WHY THIS EXISTS
---------------
Before this module, the presentation dispatcher hardcoded DeepSeek
V4 Flash as the ONLY authoring model (dispatcher.deepseek_complete). Nothing
routed by what the client actually owns: a client with OpenRouter-GLM and no
DeepSeek key could not be served, a client owning DeepSeek V4 Pro never got
the stronger model for reasoning phases, and QC judges could silently ride
the same model identity that authored the artifact.

WHAT THIS IS
------------
A PURE SELECTION layer -- no network, no credentials, no transport -- between
the phase a work order asks for and the (provider, model) route that
completes it. The dispatcher owns every transport; this module only DECIDES:

    required capability -> client-owned and consented providers ->
    catalog health (wired inventory) -> mode budget -> fallback list.

Every decision carries {phase_id, requested_alias, route, reason, ...}; the
dispatcher emits the FIX 5 telemetry row {event: "model_route", phase_id,
requested_alias, selected_provider, selected_model, reason} per the fix spec
("Every fallback emits ... to FIX 5 telemetry").

CATALOG ALIASES (FIX 13 boundary)
---------------------------------
The labels below are catalog aliases, NEVER duplicated literal model ids at
call sites (fix spec). Resolution order:

    1. presentation_job.model_catalog (FIX 13's live catalog) when it
       exposes resolve_alias() -- FIX 13 is authoritative and this module
       defers to it;
    2. the built-in DEFAULT_ALIAS_REGISTRY here, which pins only the ids
       this box has LIVE-CONFIRMED (deepseek-v4-pro / deepseek-v4-flash on
       the native DeepSeek endpoint) plus the GLM/Ollama/Kie labels from the
       fix-spec table, to be superseded by FIX 13's live catalog the moment
       that module lands.

PROFILE CONTRACT (FIX 8/9)
--------------------------
Selection reads the per-client resource profile exactly as resource_profile
persists it (never a credential, only presence + wired_models + consent).
A provider is eligible when it is owned AND consented AND -- when a wired
inventory exists -- the alias resolves to a wired model id. An absent
inventory (never probed) is not evidence of absence; presence/detected
alone keeps the provider eligible. A provider explicitly consented=False is
never selected.

MODALITY DOCTRINE (binding)
---------------------------
A model lacking the required modality/context is never selected solely
because it is cheaper. Classes encode that: reasoning/long-synthesis
classes never fall back to the cheaper Flash model (the fix spec: "no
adequate context window = park", "cannot fall back to a model that cannot
hold the research bundle"), and vision phases resolve NO route when no
vision-capable owner exists (the caller parks fail-closed -- a
vision phase is never answered with a text model).

PARK / FAIL-CLOSED
------------------
route=None in a decision means "no eligible route": the dispatcher must
park/fail the phase named (RoutingUnavailable), never fabricate a route.

Rollout flag
------------
PRESENTATION_MODEL_ROUTER=1 (default ON; behavior change per rollback
doctrine). PRESENTATION_MODEL_ROUTER=0 is the documented rollback: it
selects the explicitly-documented safe path -- every decision reports
router="disabled", route=None, and the dispatcher uses its pre-FIX-7
DeepSeek-direct path byte-for-byte (deepseek_complete with the same
constants). A disabled flag never silently skips a gate: the dispatcher
still records the pre-fix model in its sidecar/telemetry, exactly as
before this fix.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Feature flag (rollback = the documented pre-fix safe path)
# ---------------------------------------------------------------------------
FLAG_ENV = "PRESENTATION_MODEL_ROUTER"
FLAG_DEFAULT = "1"


def flag_enabled() -> bool:
    """True unless the operator exported PRESENTATION_MODEL_ROUTER=0.

    Default ON per the rev2 rollback doctrine. `=0` is the documented
    rollback: resolve_route() returns a router="disabled" decision and the
    dispatcher selects its untouched pre-FIX-7 DeepSeek path."""
    raw = os.environ.get(FLAG_ENV, FLAG_DEFAULT)
    return raw.strip().strip("'\"") != "0"


# ---------------------------------------------------------------------------
# Catalog alias registry (FIX 13 supersedes via presentation_job.model_catalog)
# ---------------------------------------------------------------------------
# One registry, consulted by resolve_alias(); no call site ever hardcodes a
# literal model id. `live_confirmed` marks ids proven against a real endpoint
# on this box (the DeepSeek native pair); the rest carry the fix-spec table's
# labels until FIX 13's live catalog lands and resolves them authoritatively.
DEFAULT_ALIAS_REGISTRY: Dict[str, Dict[str, Any]] = {
    "deepseek-v4-pro": {"provider": "deepseek-direct",
                        "model": "deepseek-v4-pro",
                        "modality": "text", "context_class": "long",
                        "live_confirmed": True},
    "deepseek-v4-flash": {"provider": "deepseek-direct",
                          "model": "deepseek-v4-flash",
                          "modality": "text", "context_class": "standard",
                          "live_confirmed": True},
    "glm-5.3": {"provider": "openrouter",
                # F30 (SMOKE-1): served id is z-ai/glm-5.3; bare "glm-5.3" is
                # not in OpenRouter's wired inventory (419 probed 2026-09-01),
                # so the alias never became eligible and fell through.
                "model": "z-ai/glm-5.3",
                "modality": "text", "context_class": "long",
                "note": "GLM 5.3 via OpenRouter (fix-spec fallback column)"},
    "glm-flash": {"provider": "openrouter",
                  # F30: served id z-ai/glm-5.3-flash (probed 2026-09-01)
                  "model": "z-ai/glm-5.3-flash",
                  "modality": "text", "context_class": "standard",
                  "note": "GLM Flash-class text model (fix-spec fallback)"},
    "glm-ocr": {"provider": "ollama-cloud",
                "model": "glm-ocr",
                "modality": "vision", "context_class": "standard",
                "note": "GLM-OCR via Ollama Cloud (fix-spec vision/OCR)"},
    "gpt-image-2": {"provider": "kie",
                    "model": "gpt-image-2",
                    "modality": "image", "context_class": "standard",
                    "note": "Kie image render (fix-spec render column)"},
}


# FIX 17b: the router's candidate aliases and the FIX 13 catalog's alias
# vocabulary are two names for the same route. The catalog
# (model_catalog.json) is the ONLY place a literal model id may live, so
# resolve_alias() resolves the router alias THROUGH this mapping into the
# catalog's alias space first; the built-in DEFAULT_ALIAS_REGISTRY above is
# the fallback for aliases the catalog does not name (the GLM/OpenRouter
# labels), never a second source of truth for the ones it does.
ROUTER_CATALOG_ALIAS: Dict[str, str] = {
    "deepseek-v4-pro": "text.strong",
    "deepseek-v4-flash": "text.fast",
    "gpt-image-2": "image.t2i",
}


def resolve_alias(alias: str) -> Dict[str, Any]:
    """One alias -> ({provider, model, modality, ..., served_ids}) or {} when
    unknown.

    FIX 13's model_catalog wins when present; this built-in registry is the
    fallback, never duplicated at call sites. FIX 17a: the catalog's
    served_ids table -- {provider: served model id} keyed (alias, provider) --
    rides through on the resolved definition so the router can name the id
    each provider's endpoint actually accepts (openrouter serves
    z-ai/glm-5.3-flash for the judge class; deepseek-direct serves
    deepseek-v4-flash for the same alias).
    FIX 17b: the router READS THE CATALOG -- the alias is first mapped into
    the catalog's own vocabulary (ROUTER_CATALOG_ALIAS) and resolved through
    presentation_job.model_catalog, so provider, model and served_ids all
    come from model_catalog.json, the single literal-id store. A catalog
    entry also wins over the registry for the router alias it backs."""
    candidates = [alias]
    mapped = ROUTER_CATALOG_ALIAS.get(alias)
    if mapped and mapped != alias:
        candidates.insert(0, mapped)  # catalog vocabulary first (FIX 17b)
    try:  # FIX 13 hook -- the live catalog is authoritative when landed
        from presentation_job import model_catalog as _catalog  # type: ignore
        for probe in candidates:
            resolved = None
            for name in ("resolve_alias", "resolve"):  # FIX 13 landed names
                resolver = getattr(_catalog, name, None)
                if callable(resolver):
                    try:
                        resolved = resolver(probe)
                    except Exception:
                        resolved = None  # fail-closed catalog miss -> next
                    if isinstance(resolved, dict) and resolved.get("provider") \
                            and resolved.get("model"):
                        out = dict(resolved)
                        out.setdefault("modality", "text")
                        out.setdefault("context_class", "standard")
                        # FIX 17a: normalise the served_ids keys to canonical
                        # dash-form provider ids so `ollama_cloud` (underscore
                        # drift) and `ollama-cloud` resolve identically.
                        raw_served = out.get("served_ids")
                        if isinstance(raw_served, dict) and raw_served:
                            norm = getattr(_catalog, "normalize_provider_id", None)
                            if callable(norm):
                                out["served_ids"] = {
                                    str(norm(k)): str(v)
                                    for k, v in raw_served.items()
                                    if str(v).strip()
                                }
                            else:
                                out["served_ids"] = {
                                    str(k).strip().lower()
                                    .replace("_", "-").replace(" ", "-"): str(v)
                                    for k, v in raw_served.items()
                                    if str(v).strip()
                                }
                        return out
    except Exception:  # noqa: BLE001 -- catalog absence never breaks routing
        pass
    return dict(DEFAULT_ALIAS_REGISTRY.get(alias) or {})


def _norm_provider(provider: Any) -> str:
    """FIX 17a provider-id normalisation for the router side.

    `ollama_cloud` vs `ollama-cloud` is the same provider spelled twice;
    the profile store and the catalog must never disagree about that.
    capacity.normalize_provider is the cap-table authority when importable;
    the string fold (lowercase, underscores/spaces -> dashes) covers the
    rest. Unknown providers pass through normalised unchanged -- folding a
    name is never evidence the provider exists."""
    token = str(provider or "").strip().lower().replace("_", "-").replace(" ", "-")
    try:  # cap-table authority (deepseek -> deepseek-direct, ollama fold)
        from . import capacity as _cap  # package-relative
    except ImportError:  # pragma: no cover - direct file run
        try:
            import capacity as _cap  # type: ignore[no-redef]
        except ImportError:
            _cap = None  # type: ignore[assignment]
    if _cap is not None and hasattr(_cap, "normalize_provider"):
        try:
            mapped = _cap.normalize_provider(token)
        except Exception:  # noqa: BLE001 -- normalisation never raises upward
            mapped = None
        if mapped:
            return str(mapped)
    if token == "deepseek":
        return "deepseek-direct"
    return token


def _norm_model_id(model_id: Any) -> str:
    """FIX 17b model-id normalisation for wired-inventory comparison.

    Same fold resource_profile._norm_model_id uses: lowercase, every
    non-alphanumeric run collapsed to a single dash. 'zai/glm-5.3-flash:free',
    'GLM 5.3 Flash' and 'glm_5_3_flash' land on one comparable shape --
    spelling drift only, never a prefix/family inference."""
    return re.sub(r"[^a-z0-9]+", "-", str(model_id).lower()).strip("-") or ""


def _served_model(alias_def: Dict[str, Any], provider: str) -> str:
    """FIX 17a: the served model id one provider's endpoint accepts for this
    alias, or the alias's plain model id when no (alias, provider) row
    exists. A missing served row falls back to the alias model verbatim --
    the fallback is the catalog's own declared id, never an invented one."""
    served = alias_def.get("served_ids")
    if isinstance(served, dict) and served:
        hit = served.get(_norm_provider(provider))
        if isinstance(hit, str) and hit.strip():
            return hit
    return str(alias_def.get("model") or "")


# ---------------------------------------------------------------------------
# Phase -> capability class (the fix-spec routing table)
# ---------------------------------------------------------------------------
# Mechanical/assembly phases carry no LLM route at all (: no LLM route; use
# the manifest script executor) -- the dispatcher's DECLINE_PHASES already
# refuses them; encoding them here makes the table complete and the
# "never acquires a text-model fallback" doctrine machine-checkable.
PHASE_CAPABILITY: Dict[str, str] = {
    # Research / conversion / long-context synthesis
    "P-0.5-RESEARCH": "research_synthesis",
    "P-CONVERTER": "long_synthesis",
    "P-3.5-RESEARCH-MAP": "long_synthesis",
    # Cheap structured text (deterministic intake driver stays authoritative)
    "P0A-INTAKE": "cheap_text",
    "P-SP-CLAIM": "cheap_text",
    "P-SP-INTAKE": "cheap_text",
    "P-SP-INTAKE-TRACE": "mechanical",  # driver-signed envelope, never an LLM
    # Long-context reasoning
    "P0B-PRIORITY": "reasoning_long",
    "P3-ARC": "reasoning_long",
    "P-SP-STRUCTURE": "reasoning_long",
    "P-SP-P3-HYGIENE": "reasoning_long",
    # Copy + prompt authoring (high-throughput long-form)
    "P4-COPY": "authoring",
    "P4-PROMPT": "prompt_authoring",
    # FIX 112: the copy stage's fanout unit (per-slide style-variant candidates)
    # is creative-cheap structured text, same class as the design direction.
    "P-STYLE-SPEC": "creative_cheap",
    "PF-DESIGN": "creative_cheap",
    # Independent cheap text judges
    "P1Q-COPY-QC": "judge",
    "P-SHIFT-QC": "judge",
    "P-PROMPT-QC": "judge",
    "P-SPEECH-QC": "judge",
    # Vision + OCR
    "P-TYPO-QC": "vision_ocr",
    "P-IMAGE-QC": "vision_ocr",
    # Image render (Kie; the manifest script executor owns these phases)
    "P-STYLE-PREVIEW": "image_render",
    "P4-RENDER": "image_render",
    # Speech text + deterministic downstream
    "P9-SPEECH": "speech_text",
    "P9-SPEECH-WEBINAR-INTRO": "speech_text",
    "P9.5-NOTES-SYNC": "mechanical",
    "P8-ASSEMBLE": "mechanical",
    "P8.1-PDF-EXPORT": "mechanical",
    "P8.2-GUIDE": "mechanical",
    "P8.25-WORKBOOK": "mechanical",
    "P8.4-FISH-TAG": "mechanical",
    "P9.1-SPEECH-PDF": "mechanical",
    "P9.2-GHL-UPLOAD": "mechanical",
    "P9.6-WEBINAR-VIDEO": "mechanical",
    "P7-TELEPROMPTER": "mechanical",
    "P9-DELIVER": "mechanical",
    "P-QC-AGGREGATE": "mechanical",
}

# Anything not named above that reaches the dispatcher's text-completion loop
# is authoring work (the loop exists to author artifacts) -- same class as
# P4-COPY. Never invents a capability the phase did not declare.
DEFAULT_CAPABILITY = "authoring"


# Ordered (alias, allow) candidates per capability class, straight from the
# fix-spec table's Default + Ordered-fallback columns. The fallback rule is
# the modality doctrine: reasoning/long classes never drop to Flash.
CAPABILITY_CANDIDATES: Dict[str, List[Dict[str, Any]]] = {
    # OPERATOR RULING 2026-09-04: Flash leads on authoring work. Flash's
    # DeepSeek Direct ceiling is 2500 concurrent vs Pro's 500, so a wide
    # per-slide fan-out is only reachable on Flash; Pro remains the fallback
    # for anything Flash cannot serve. reasoning_long and long_synthesis are
    # deliberately NOT changed -- those classes still never see Flash.
    #
    # NOTE: "allow_flash_fallback" below is INERT. It is declared here and
    # read NOWHERE in this tree (2 occurrences, both declarations, zero
    # consumers -- verified against a CAPABILITY_CANDIDATES control with 1
    # declaration and 2 consumers). Fallback order is enforced ONLY by the
    # order of this list, and a class refuses Flash only by omitting it.
    # Do not trust this key to gate anything.
    "authoring": [
        {"alias": "deepseek-v4-flash"},
        {"alias": "deepseek-v4-pro", "allow_flash_fallback": False},
        {"alias": "glm-5.3"},
    ],
    "prompt_authoring": [  # P4-PROMPT: flash -> pro -> GLM
        {"alias": "deepseek-v4-flash"},
        {"alias": "deepseek-v4-pro", "allow_flash_fallback": False},
        {"alias": "glm-5.3"},
    ],
    "reasoning_long": [  # no Flash fallback: long context + reasoning
        {"alias": "deepseek-v4-pro"},
        {"alias": "glm-5.3"},
    ],
    "long_synthesis": [  # research bundle; cannot fall below long context
        {"alias": "deepseek-v4-pro"},
        {"alias": "glm-5.3"},
    ],
    "research_synthesis": [  # FIX 19 owns retrieval; synthesis rides the
                             # same long-context doctrine
        {"alias": "deepseek-v4-pro"},
        {"alias": "glm-5.3"},
    ],
    "cheap_text": [
        {"alias": "deepseek-v4-flash"},
        {"alias": "glm-flash"},
        {"alias": "glm-5.3"},
    ],
    "creative_cheap": [  # PF-DESIGN cheap creative text
        {"alias": "deepseek-v4-flash"},
        {"alias": "glm-flash"},
        {"alias": "glm-5.3"},
    ],
    "judge": [  # independent cheap text judge
        {"alias": "deepseek-v4-flash"},
        {"alias": "glm-flash"},
        {"alias": "glm-5.3"},
    ],
    "vision_ocr": [  # vision + OCR only; no owner -> park fail-closed
        # F30 (SMOKE-1, 2026-09-01): glm-ocr (ollama-cloud) needs
        # OLLAMA_CLOUD_API_KEY which no env store on the operator box carries,
        # so the single-candidate chain exhausted every wave with
        # "OLLAMA_CLOUD_API_KEY not set". F30b: OpenRouter credits are
        # exhausted (HTTP 402 at any token budget -- balance is negative),
        # so the OCR readback falls to deepseek-direct (proven live 2026-09-01
        # with a 1-token smoke call). deepseek-v4-pro is a text model; the
        # P-IMAGE-QC OCR readback is text-QC over baked-prompt text, not raw
        # pixel vision, so a text model satisfies the verifier.
        {"alias": "deepseek-v4-pro"},
        {"alias": "glm-5.3"},
        {"alias": "glm-ocr"},
    ],
    "image_render": [  # Kie render; the script executor owns the phase
        {"alias": "gpt-image-2"},
    ],
    "speech_text": [
        {"alias": "deepseek-v4-pro"},
        {"alias": "glm-5.3"},
    ],
    "mechanical": [],  # no LLM route, ever
}


# ---------------------------------------------------------------------------
# CLIENT MODEL PLAN (operator requirement 2026-09-04, verbatim):
#   "whatever is forcing this thing to use DeepSeek V4 Pro, I don't want to be
#    forced to do anything. So as a client should be able to choose whatever
#    they want to be their primary workhorse or authoring model."
#
# CAPABILITY_CANDIDATES above is therefore the DEFAULT for a client who
# declares NOTHING -- it stopped being the only answer. A client's declaration
# lives in the resource profile (resource_profile.record_model_plan ->
# profile["model_plan"]), which is the ONE store every consumer already reads:
# resolve_route() loads it on every call, and the P4-PROMPT fan-out children
# re-resolve in a SEPARATE process (parallel_prompt_worker) where a run-dir
# sidecar would be unreachable but the env-resolved profile path is inherited.
#
# The declaration is data, not code:
#   profile["model_plan"] = {
#     "workhorse": {"provider": "deepseek-direct", "model": "deepseek-v4-flash"},
#     "reasoning": {...} | null,
#     "judge":     {...} | null,
#     "thinking":  "max"|"high"|"medium"|"low"|"off"|null,
#     "floor_waivers": ["reasoning_long", ...],
#     "source": "interview"|"cli", "declared_at": "<ISO8601>"}
#
# NOTE ON THE KEY NAMES (binding): resource_profile.redact_record() DROPS every
# profile key matching (api[-_]?key|key|token|secret|password|passwd|auth|
# credential|cookie|bearer) on EVERY save and EVERY load. "auth" is a substring
# of "authoring", so a slot named "authoring_model" would VANISH from the store
# on the next save with no error. The slot is called "workhorse" for that
# reason, and no dict persisted into the profile is ever keyed by a capability
# class name (the per-class table below is a LIST of rows, not a dict keyed by
# "authoring"). tests/test_model_plan.py pins this.
# ---------------------------------------------------------------------------

#: The alias-prefix a client-declared candidate carries in a decision's
#: candidate list, so telemetry can tell a client choice from a default one.
CLIENT_ALIAS_PREFIX = "client:"

#: Which capability classes each client slot governs. vision_ocr, image_render
#: and mechanical are deliberately NOT client-slotted in v1: OCR/render classes
#: are modality-bound to a provider the client rarely owns a substitute for,
#: and mechanical phases carry no LLM route at all.
#:
#: `judge` is NOT reachable from the workhorse slot, by design and not by
#: omission: this module exists partly because "QC judges could silently ride
#: the same model identity that authored the artifact" (header, WHAT THIS IS).
#: Spilling a declared workhorse into the judge class would re-open exactly
#: that hole, so the judge slot must be named EXPLICITLY to take effect.
SLOT_CLASSES: Dict[str, Tuple[str, ...]] = {
    "workhorse": ("authoring", "prompt_authoring", "cheap_text",
                  "creative_cheap", "speech_text"),
    "reasoning": ("reasoning_long", "long_synthesis", "research_synthesis"),
    "judge": ("judge",),
}

#: Reverse index: capability class -> the slot that governs it (None = not
#: client-slotted in v1).
CLASS_SLOT: Dict[str, str] = {
    cls: slot for slot, classes in SLOT_CLASSES.items() for cls in classes
}

#: THE INVARIANTS, as data beside the candidate table. A client choice is
#: honoured only when it clears the floor of the class it would serve (or the
#: client explicitly waived that class -- see floor_waivers). Same doctrine as
#: capacity: an UNKNOWN reading is never rounded upward into a capability.
CLASS_FLOORS: Dict[str, Dict[str, str]] = {
    "authoring": {"context_class": "standard", "modality": "text"},
    "prompt_authoring": {"context_class": "standard", "modality": "text"},
    "cheap_text": {"context_class": "standard", "modality": "text"},
    "creative_cheap": {"context_class": "standard", "modality": "text"},
    "speech_text": {"context_class": "standard", "modality": "text"},
    "judge": {"context_class": "standard", "modality": "text"},
    # the modality doctrine, unchanged: these three cannot hold the research
    # bundle on a standard window, so "long" is a FLOOR, not a preference.
    "reasoning_long": {"context_class": "long", "modality": "text"},
    "long_synthesis": {"context_class": "long", "modality": "text"},
    "research_synthesis": {"context_class": "long", "modality": "text"},
    "vision_ocr": {"context_class": "standard", "modality": "vision"},
    "image_render": {"context_class": "standard", "modality": "image"},
}

#: Anything not named above is held to the ordinary text floor.
DEFAULT_CLASS_FLOOR: Dict[str, str] = {"context_class": "standard",
                                       "modality": "text"}

#: The context classes that SATISFY each context floor. "standard" is the
#: baseline every text model clears, so an UNKNOWN reading clears it too --
#: there is nothing below standard to fall short of. "long" is a real
#: capability claim, and only a model the catalog SAYS is long satisfies it:
#: "unknown" is deliberately absent from that set, because the absence of a
#: reading is never evidence of a longer window (the same doctrine that stops
#: an unmeasured capacity ceiling from becoming a wide one).
_CONTEXT_SATISFIES: Dict[str, frozenset] = {
    "standard": frozenset({"standard", "long", "unknown"}),
    "long": frozenset({"long"}),
}


def class_floor(capability: str) -> Dict[str, str]:
    """The floor one capability class imposes on any model that serves it."""
    return dict(CLASS_FLOORS.get(capability) or DEFAULT_CLASS_FLOOR)


def floor_verdict(alias_def: Dict[str, Any], capability: str) -> Dict[str, Any]:
    """Does this resolved model meet `capability`'s floor? Never guesses up.

    context_class: a class demanding "long" is met ONLY by a model the catalog
    says is "long". An arbitrary wired id resolves to context_class "unknown"
    (nobody measured it) and UNKNOWN FAILS the long floor -- absence of a
    reading is never evidence of a long window, exactly as an unmeasured
    capacity ceiling never becomes a wide one.
    modality: exact. A vision or image model is not a text authoring model and
    a text model is not an OCR model."""
    required = class_floor(capability)
    ctx = str(alias_def.get("context_class") or "unknown").strip().lower()
    mod = str(alias_def.get("modality") or "unknown").strip().lower()
    reasons: List[str] = []
    need_ctx = str(required.get("context_class") or "standard")
    if ctx not in _CONTEXT_SATISFIES.get(need_ctx, frozenset({need_ctx})):
        reasons.append(
            f"context_class {ctx!r} does not meet the {need_ctx!r} floor of "
            f"capability {capability!r}"
            + (" -- UNKNOWN is the absence of a reading, never evidence of a "
               "longer window" if ctx == "unknown" else ""))
    need_mod = str(required.get("modality") or "text")
    if mod != need_mod:
        reasons.append(f"modality {mod!r} is not the {need_mod!r} modality "
                       f"capability {capability!r} requires")
    return {
        "ok": not reasons,
        "required": required,
        "context_class": ctx,
        "modality": mod,
        "reason": "; ".join(reasons) or f"meets the {capability} floor",
    }


def model_plan(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The client's declared model plan block, or {} when none is declared."""
    if not isinstance(profile, dict):
        return {}
    plan = profile.get("model_plan")
    return plan if isinstance(plan, dict) else {}


def plan_slot(plan: Dict[str, Any], slot: str) -> Optional[Dict[str, str]]:
    """One slot's declared {provider, model}, normalised, or None.

    A half-declared slot (provider without model, or the reverse) is NOT a
    declaration: it returns None rather than being completed with a guess."""
    raw = (plan or {}).get(slot)
    if not isinstance(raw, dict):
        return None
    provider = _norm_provider(raw.get("provider"))
    model = str(raw.get("model") or "").strip()
    if not provider or not model:
        return None
    return {"provider": provider, "model": model}


def _registry_capability_meta(model_id: str) -> Dict[str, Any]:
    """The modality/context_class DEFAULT_ALIAS_REGISTRY states for this id.

    WHY THIS EXISTS (verified 2026-09-04): model_catalog.json declares ZERO
    capability metadata -- `context_class` and `modality` appear 0 times in the
    whole file -- so resolve_alias()'s setdefault() hands back "standard"/"text"
    for EVERY catalog-backed alias, deepseek-v4-pro included. The catalog is
    authoritative for the literal ids (FIX 17b) and says nothing about
    capability; this registry is where capability is actually declared. Reading
    the floor off the catalog's defaults would judge the department's own
    long-context model as standard-context, so the client's declaration is
    measured against the table that actually states the fact.

    Matches by alias key first, then by the id each registry row serves, so a
    client who types the served id ("z-ai/glm-5.3") is judged the same as one
    who types the alias ("glm-5.3"). Returns {} when nothing declares it --
    and {} means UNKNOWN, which never clears a long floor."""
    key = str(model_id or "").strip()
    row = DEFAULT_ALIAS_REGISTRY.get(key)
    if not isinstance(row, dict):
        nm = _norm_model_id(key)
        row = next((r for r in DEFAULT_ALIAS_REGISTRY.values()
                    if nm and _norm_model_id(r.get("model")) == nm), None)
    if not isinstance(row, dict):
        return {}
    return {f: row[f] for f in ("modality", "context_class") if f in row}


def declared_alias_def(declared: Dict[str, str]) -> Tuple[Dict[str, Any], str]:
    """Resolve one declared {provider, model} into an alias_def-shaped dict.

    Three honest outcomes, in order:
      catalog-alias      -- the id is a router/catalog alias AND names the same
                            provider: the catalog row is used verbatim, so its
                            served_ids/modality/context_class all apply.
      catalog-repointed  -- the id is a known alias but the client named a
                            DIFFERENT endpoint for it: the model's capability
                            metadata (modality/context_class -- properties of
                            the MODEL) rides along, while provider and served
                            id come from what the client actually declared.
      wired-id           -- an arbitrary id no catalog names: synthesized with
                            context_class "unknown" (which fails every long
                            floor) and modality "text" (the class of work every
                            client-slotted class does). Nothing is inferred
                            from the id's spelling.
    """
    provider = declared["provider"]
    model = declared["model"]
    resolved = resolve_alias(model)
    meta = _registry_capability_meta(model)
    if resolved and resolved.get("provider") and resolved.get("model"):
        out = dict(resolved)
        out.update(meta)  # capability is declared HERE, never by the catalog
        out.setdefault("modality", "text")
        out.setdefault("context_class", "standard")
        if _norm_provider(out.get("provider")) == provider:
            # Same provider, canonically spelled: the catalog may say
            # "deepseek" where the client (and the profile store, and the key
            # canon) say "deepseek-direct". Stamp the canonical form so the
            # decision reports the route the client actually declared -- a
            # fold, never a repoint (the equality above already proved that).
            out["provider"] = provider
            return out, "catalog-alias"
        out["provider"] = provider
        out["model"] = model
        out["served_ids"] = {provider: model}
        return out, "catalog-repointed"
    synth: Dict[str, Any] = {"provider": provider, "model": model,
                             "modality": "text", "context_class": "unknown",
                             "served_ids": {provider: model}}
    synth.update(meta)
    return synth, ("registry-id" if meta else "wired-id")


def client_plan_for(capability: str,
                    profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The client's declaration for one capability class, or None.

    Returns {slot, via, declared, alias, alias_def, alias_source, floor,
    waived, capability}. `via`:
      "declared"        -- the client named THIS slot;
      "workhorse-spill" -- only the workhorse was named, and this is a
                           reasoning class: per the launch policy the
                           workhorse governs it too WHEN IT MEETS THE FLOOR,
                           and falls back VISIBLY when it does not.
    A spill can never be waived: a waiver is something a client asks for about
    a model they NAMED for that job, never something inferred on their behalf.
    """
    plan = model_plan(profile)
    if not plan:
        return None
    slot = CLASS_SLOT.get(capability)
    if slot is None:
        return None  # vision_ocr / image_render / mechanical: not slotted in v1
    declared = plan_slot(plan, slot)
    via = "declared"
    if declared is None and slot == "reasoning":
        declared = plan_slot(plan, "workhorse")
        via = "workhorse-spill"
    if declared is None:
        return None
    alias_def, alias_source = declared_alias_def(declared)
    floor = floor_verdict(alias_def, capability)
    waivers = {str(w).strip() for w in (plan.get("floor_waivers") or [])
               if str(w).strip()}
    return {
        "capability": capability,
        "slot": slot,
        "via": via,
        "declared": dict(declared),
        "alias": f"{CLIENT_ALIAS_PREFIX}{slot}",
        "alias_def": alias_def,
        "alias_source": alias_source,
        "floor": floor,
        "waived": bool((not floor["ok"]) and via == "declared"
                       and capability in waivers),
    }


def plan_report(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The per-class table the launcher banner and the client report print.

    `classes` is a LIST of rows, never a dict keyed by capability class --
    "authoring" contains "auth" and would be dropped by the profile's
    redaction rule if this shape were ever persisted there (see the header
    note above)."""
    plan = model_plan(profile)
    rows: List[Dict[str, Any]] = []
    for capability in sorted(CAPABILITY_CANDIDATES):
        if capability == "mechanical":
            continue
        default_alias = str(
            (CAPABILITY_CANDIDATES.get(capability) or [{}])[0].get("alias") or "")
        pick = client_plan_for(capability, profile)
        if pick is None:
            rows.append({
                "capability": capability, "slot": None, "via": None,
                "source": "department-default", "provider": None, "model": None,
                "default_alias": default_alias, "floor": None,
                "detail": "no client declaration covers this class",
            })
            continue
        applied = pick["floor"]["ok"] or pick["waived"]
        rows.append({
            "capability": capability,
            "slot": pick["slot"],
            "via": pick["via"],
            "source": "client-plan" if applied else "department-default",
            "provider": pick["declared"]["provider"],
            "model": pick["declared"]["model"],
            "default_alias": default_alias,
            "floor": ("ok" if pick["floor"]["ok"]
                      else ("waived" if pick["waived"] else "failed")),
            "detail": pick["floor"]["reason"],
        })
    slots = {slot: plan_slot(plan, slot) for slot in SLOT_CLASSES}
    return {
        "declared": bool(plan),
        "slots": slots,
        "thinking": plan.get("thinking"),
        "floor_waivers": sorted(str(w) for w in (plan.get("floor_waivers") or [])),
        "source": plan.get("source"),
        "declared_at": plan.get("declared_at"),
        "classes": rows,
    }


# ---------------------------------------------------------------------------
# FIX 11: Ultra / Standard / Economy modes -- measured-capacity concurrency
# ---------------------------------------------------------------------------
# DEFAULT RULING (fix spec, binding): Ultra's operator ceiling is 100
# concurrent tasks -- even when DeepSeek advertises 500 / 2,500. It is never
# raised by provider advertising, never "learned", and only revisited through
# an explicit config revision with Trevor approval, gated on a REAL 7-day
# wall-clock operator-box stability window (>=95% of eligible Ultra runs
# complete without concurrency-caused retry exhaustion, zero safety gates
# bypassed, telemetry complete). Standard and Economy derive from the
# MEASURED client capacity/cost policy and may never exceed the same
# client/provider ceiling. Nothing here touches the network: ceilings come
# from the client's resource profile (FIX 8 ceiling fields), the
# conservative floor, and the human-ratified constant below.

MODE_FLAG_ENV = "PRESENTATION_MODES"
MODE_FLAG_DEFAULT = "1"

#: The operator ceiling -- a HUMAN-ratified constant, never provider-advertised.
ULTRA_OPERATOR_CEILING = 100

#: capacity.DEFAULT_CONSERVATIVE -- the floor a run proceeds AT when nothing
#: was measured. A mode never claims a higher width than the box was proven
#: to (or did) carry.
DEFAULT_CONSERVATIVE_FLOOR = 3

#: parallel_prompt_worker.DEFAULT_MAX_WORKERS; Standard on an
#: unmeasured-but-UNBOUNDED client stays the 8-wide worker default.
STANDARD_WORKER_DEFAULT = 8

MODES: Tuple[str, ...] = ("ultra", "standard", "economy")

#: The env var the launcher exports INTO the engine process
#: (launcher.dispatch -> mode_env). Deliberately one letter from
#: MODE_FLAG_ENV ("PRESENTATION_MODES"), which is the ROLLBACK FLAG, not
#: the mode: PRESENTATION_MODES=0 turns the surface off, PRESENTATION_MODE
#: names which mode a run is in. Both spellings are load-bearing.
MODE_ENV = "PRESENTATION_MODE"

#: The mode a run lands in when NOBODY declared one. Never "ultra":
#: nothing silently launches at the operator ceiling.
DEFAULT_MODE = "standard"

#: Capability classes Economy legally re-points to the cheap fast model
#: FIRST (the original candidates stay behind it as fallbacks). Anything not
#: named here keeps its original candidate list in EVERY mode -- the
#: modality doctrine (reasoning/long-synthesis/vision/image classes never
#: drop to Flash) holds by construction: those classes simply do not appear
#: in this map.
ECONOMY_FLASH_REPOINT: Dict[str, List[Dict[str, Any]]] = {
    "authoring": [{"alias": "deepseek-v4-flash"}],
    "prompt_authoring": [{"alias": "deepseek-v4-flash"}],
}


def modes_enabled() -> bool:
    """True unless the operator exported PRESENTATION_MODES=0.

    Default ON per the rev2 rollback doctrine. `=0` is the documented
    rollback: every FIX 11 seam goes inert -- resolve_route() stops
    stamping mode concurrency and stops the Economy re-mix, and the
    launcher writes no .mode-plan.json sidecar and declares no
    PRESENTATION_MODE env for the engine."""
    raw = os.environ.get(MODE_FLAG_ENV, MODE_FLAG_DEFAULT)
    return raw.strip().strip("'\"") != "0"


def normalize_mode(mode: str) -> str:
    """Normalize one mode name into the FIX 11 vocabulary.

    Anything not ultra/standard/economy raises ValueError -- an unknown
    mode is never silently coerced into a cheaper or more expensive one."""
    want = str(mode or "").strip().lower()
    if want not in MODES:
        raise ValueError(
            f"unknown mode {mode!r} -- FIX 11 modes are {', '.join(MODES)}")
    return want


def active_mode(explicit: Optional[str] = None, *, strict: bool = True) -> str:
    """THE run-mode resolution order. One authority, stated once, here.

        1. an EXPLICIT declaration -- the launcher's --mode (launcher.py's
           CLI, the run-mode door), or any caller passing mode=...;
        2. the PRESENTATION_MODE env the launcher exports into the engine
           process (launcher.dispatch -> mode_env). This is how a mode reaches
           dispatcher / heal / credit_preflight code running in a CHILD
           process that has no parameter to thread it through;
        3. DEFAULT_MODE ("standard").

    The canonical entry script is deliberately NOT a run-mode door and has no
    --mode flag: that is a stated design decision, pinned as an executable
    assertion in tests/test_fix36_intake_depth.py. The env in (2) is the seam
    for anything that is not the launcher.

    Never "ultra" by default, and never inferred from anything else: a mode is
    something a human declared, or it is standard. An EMPTY value at either
    level is unset, never a selection (same doctrine as modes_enabled()).

    strict=True (the default) raises ValueError on a value outside MODES --
    an unknown mode is never silently coerced into a cheaper or a more
    expensive one (normalize_mode's rule). strict=False answers DEFAULT_MODE
    instead, for the deep in-engine callers that must not hard-crash a running
    deck over a hand-set env var; those callers RECORD the fallback (see
    dispatcher._active_mode) rather than swallowing it.
    """
    for raw in (explicit, os.environ.get(MODE_ENV)):
        if raw is None:
            continue
        text = str(raw).strip().strip("'\"")
        if not text:
            continue
        try:
            return normalize_mode(text)
        except ValueError:
            if strict:
                raise
            return DEFAULT_MODE
    return DEFAULT_MODE


def measured_client_ceiling(profile: Optional[Dict[str, Any]]) -> Any:
    """The client's measured concurrency ceiling, read from the profile.

    Returns a positive int (a real measured ceiling), the string "UNBOUNDED"
    (a bring-your-own/unlimited client -- never coerced to a number), or
    None (nothing measured). Same semantics as capacity.available_or_none:
    a malformed value reads as unmeasured, never as evidence for a higher
    width. The strictest measured ceiling wins when several providers
    carry one."""
    if not profile:
        return None
    values: List[Any] = []
    for entry in (profile.get("providers") or {}).values():
        if isinstance(entry, dict):
            values.append(entry.get("concurrency_ceiling"))
    ints = [v for v in values if isinstance(v, int)
            and not isinstance(v, bool) and v > 0]
    if ints:
        return min(ints)
    if any(v == "UNBOUNDED" for v in values):
        return "UNBOUNDED"
    return None


def mode_concurrency(mode: str, *,
                     profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """FIX 11 concurrency selection for one mode against one client profile.

    Hard ceilings: Ultra NEVER exceeds ULTRA_OPERATOR_CEILING (100) or a
    lower measured client ceiling, whichever is smaller -- DeepSeek
    advertising 500/2,500 changes nothing. An unmeasured client proceeds at
    the conservative floor (3), never at the full operator ceiling. Standard
    and Economy derive from the measured capacity and never exceed the same
    ceiling. Unknown mode -> ValueError."""
    m = normalize_mode(mode)
    measured = measured_client_ceiling(profile)
    operator = ULTRA_OPERATOR_CEILING

    if m == "ultra":
        if measured is None:
            choose, reason = DEFAULT_CONSERVATIVE_FLOOR, (
                "client ceiling unmeasured: proceed at the conservative "
                f"floor, never the operator ceiling {operator} -- measure "
                "first, then scale")
        elif measured == "UNBOUNDED":
            choose, reason = operator, (
                f"client is UNBOUNDED: the operator ceiling {operator} "
                "applies exactly (provider-advertised 500/2500 never "
                "raises it)")
        else:
            choose, reason = min(operator, int(measured)), (
                f"min(operator ceiling {operator}, measured client ceiling "
                f"{measured}) -- Ultra never exceeds either")
    elif m == "standard":
        if measured is None:
            choose, reason = DEFAULT_CONSERVATIVE_FLOOR, (
                "client ceiling unmeasured: standard at the conservative "
                "floor 3")
        elif measured == "UNBOUNDED":
            choose, reason = STANDARD_WORKER_DEFAULT, (
                "client is UNBOUNDED: standard stays the worker default "
                f"{STANDARD_WORKER_DEFAULT}")
        else:
            choose, reason = min(STANDARD_WORKER_DEFAULT, int(measured)), (
                f"derived from the measured client ceiling {measured}, "
                f"capped at the worker default {STANDARD_WORKER_DEFAULT}")
    else:  # economy; normalize_mode already rejected anything unknown
        if measured is None:
            choose, reason = 1, (
                "client ceiling unmeasured: economy runs single-file")
        elif measured == "UNBOUNDED":
            choose, reason = 2, (
                "client is UNBOUNDED: economy stays a modest width "
                "(cost policy, not capacity)")
        else:
            choose, reason = max(1, int(measured) // 3), (
                f"derived from the measured client ceiling {measured} "
                "(a third of it, >= 1) -- never above the same ceiling")

    return {
        "mode": m,
        "concurrency": int(choose),
        "measured_ceiling": measured,
        "operator_ceiling": operator,
        "reason": reason,
    }


def mode_ceiling(mode: str, *,
                 profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The HARD CAP a mode imposes on a concurrency width. A CAP -- never a
    floor, never a target.

    The binding text, unchanged: "Ultra's operator ceiling is 100 concurrent
    tasks -- even when DeepSeek advertises 500 / 2,500 ... Standard and Economy
    derive from the MEASURED client capacity/cost policy and may never exceed
    the same client/provider ceiling." One ceiling, shared by all three modes:
    min(ULTRA_OPERATOR_CEILING, the client's MEASURED ceiling when one exists).
    An unmeasured client contributes no ceiling of its own -- the absence of a
    reading is not a ceiling any more than it is a capability -- so only the
    operator's 100 applies and the width still comes from what was measured.

    WHY THIS IS NOT mode_concurrency(): that function answers "how wide would
    this mode PLAN to run", and its answers include FLOORS (the conservative 3
    for an unmeasured client) and the 8-wide Standard worker default. Using
    those as caps would (a) install a floor as a ceiling and (b) re-clamp a
    measured 2,500 down to 8 -- the precise behaviour the operator ruled out on
    2026-09-04 (parallel_prompt_worker._workers_for's own comment). The plan is
    a plan; THIS is the only number allowed to cut a measured width."""
    m = normalize_mode(mode)
    measured = measured_client_ceiling(profile)
    operator = ULTRA_OPERATOR_CEILING
    if isinstance(measured, int) and not isinstance(measured, bool) and measured > 0:
        ceiling = min(operator, int(measured))
        reason = (f"min(operator ceiling {operator}, measured client ceiling "
                  f"{measured}) -- no mode may exceed either")
    else:
        ceiling = operator
        reason = (f"operator ceiling {operator} -- client ceiling "
                  + ("UNBOUNDED" if measured == "UNBOUNDED" else "unmeasured")
                  + ", which is never a raise and never provider-advertised")
    return {"mode": m, "ceiling": int(ceiling), "measured_ceiling": measured,
            "operator_ceiling": operator, "reason": reason}


def capped_width(width: Any, mode: str, *,
                 profile: Optional[Dict[str, Any]] = None,
                 decision: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply a mode's ceiling to a width SOMEBODY ELSE MEASURED.

        effective = min(measured width, mode ceiling [, Economy's cost width])

    Never max(): a mode can only ever narrow what was measured. Ultra does not
    raise a client measured at 3 to 100 -- 100 is the point past which Ultra
    may not go, not a width to aim for. Economy is the one mode that narrows
    below the shared ceiling, because Economy is a COST policy: it deliberately
    spends less than the box could carry.

    `decision` reuses the mode_ceiling / mode_concurrency blocks resolve_route
    already stamped, so an in-engine caller holding a decision does not reload
    the client profile to ask the same question twice."""
    m = normalize_mode(mode)
    ceil_block = (decision or {}).get("mode_ceiling") \
        or mode_ceiling(m, profile=profile)
    limits: List[Tuple[str, int]] = [
        ("mode ceiling", int(ceil_block.get("ceiling") or ULTRA_OPERATOR_CEILING))]
    if m == "economy":
        conc = (decision or {}).get("mode_concurrency") \
            or mode_concurrency(m, profile=profile)
        limits.append(("economy cost policy",
                       int(conc.get("concurrency") or 1)))
    try:
        measured = int(width)
    except (TypeError, ValueError):
        measured = 0
    if measured < 1:
        return {"mode": m, "width": None, "requested": width,
                "ceiling": limits[0][1], "capped": False,
                "reason": "no positive measured width to cap",
                "ceiling_reason": ceil_block.get("reason")}
    effective = measured
    applied = "the measured width"
    for label, limit in limits:
        if 1 <= limit < effective:
            effective, applied = limit, label
    return {
        "mode": m, "width": int(effective), "requested": int(measured),
        "ceiling": limits[0][1], "capped": effective != measured,
        "reason": (f"{applied} governs: min(measured {measured}, "
                   + ", ".join(f"{lbl} {val}" for lbl, val in limits) + ")"),
        "ceiling_reason": ceil_block.get("reason"),
    }


def _mode_candidates(capability: str, mode: str, *,
                     client_governed: bool = False) -> List[Dict[str, Any]]:
    """Mode-aware ordered candidate list for one capability class.

    ALWAYS A FRESH LIST OF FRESH ROWS. It used to hand back the LIVE
    CAPABILITY_CANDIDATES list object for every non-Economy mode, so any caller
    that mutated the result rewrote the department default table process-wide
    -- every later phase, every other client in the same process, permanently.
    resolve_route copied defensively; nothing obliged the NEXT caller to. The
    copy lives here now, once, where the aliasing was.

    client_governed=True suppresses Economy's re-point for this class. THE
    CLIENT'S EXPLICIT CHOICE WINS (operator requirement 2026-09-04: "I don't
    want to be forced to do anything"), so Economy may re-point only classes
    the client did NOT declare: where a declaration is actually in force, the
    class keeps its department order BEHIND the client's row and no cheaper
    model is slipped in front of it. A declaration that failed its class floor
    and was not waived is NOT in force -- the department default is serving
    that class, and Economy's cost policy governs department defaults."""
    base = CAPABILITY_CANDIDATES.get(capability, [])
    if modes_enabled() and mode == "economy" and not client_governed \
            and capability in ECONOMY_FLASH_REPOINT:
        merged: List[Dict[str, Any]] = [dict(c) for c in
                                        ECONOMY_FLASH_REPOINT[capability]]
        for cand in base:
            if all(c.get("alias") != cand.get("alias") for c in merged):
                merged.append(dict(cand))
        return merged
    return [dict(c) for c in base]


def read_fix5_wall_clock(last_run_dir: Optional[Path]) -> Optional[float]:
    """Sum the measured phase duration_s from FIX 5 stage-timings rows.

    The ETA basis is the LAST COMPLETED RUN's real measured wall-clock from
    working/telemetry/stage-timings.jsonl (FIX 5) -- never a guessed
    constant. Returns None when nothing measured."""
    if not last_run_dir:
        return None
    path = Path(last_run_dir) / "working" / "telemetry" / "stage-timings.jsonl"
    if not path.is_file():
        return None
    total = 0.0
    seen = False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            dur = row.get("duration_s")
            if isinstance(dur, (int, float)) and not isinstance(dur, bool):
                total += float(dur)
                seen = True
    except OSError:
        return None
    return total if seen else None


def mode_plan(mode: str, *,
              profile: Optional[Dict[str, Any]] = None,
              last_run_dir: Optional[Path] = None,
              plan_calls: Optional[Dict[str, int]] = None,
              estimate_usd: Optional[float] = None) -> Dict[str, Any]:
    """The honest-ETA + cost plan a mode launch presents at intake.

    FIX 11: "given the profile + measured per-phase costs (FIX 5), present
    three modes with honest ETA + cost." ETA = FIX 5 measured wall-clock of
    the last completed run (basis names it; None states unmeasured instead
    of guessing). Cost = the FIX 12 preflight estimate priced off the
    FIX 13 catalog (basis names it; None states unpriced). Concurrency =
    mode_concurrency()'s measured-capacity decision."""
    m = normalize_mode(mode)
    conc = mode_concurrency(m, profile=profile)
    wall = read_fix5_wall_clock(last_run_dir)
    eta = {
        "duration_s": wall,
        "basis": ("fix5-stage-timings: measured wall-clock of the last "
                  "completed run" if wall is not None else
                  "unmeasured: no FIX 5 stage-timings for a last completed "
                  "run -- stated as unmeasured, not guessed"),
        "plan_calls": dict(plan_calls) if plan_calls else {},
    }
    cost = {
        "total_estimate_usd": (float(estimate_usd)
                               if isinstance(estimate_usd, (int, float))
                               and not isinstance(estimate_usd, bool)
                               else None),
        "basis": ("fix12-credit-preflight: catalog-priced estimate"
                  if estimate_usd is not None else
                  "unpriced: no FIX 12 verdict was supplied"),
    }
    return {
        "mode": m,
        "concurrency": conc,
        "eta": eta,
        "cost": cost,
        "flag": {"env": MODE_FLAG_ENV, "rollback": f"{MODE_FLAG_ENV}=0"},
    }


def _parse_window_ts(row: Dict[str, Any]) -> Optional[datetime]:
    raw = row.get("ts") or row.get("started_at") or row.get("ended_at")
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def stability_window(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate the FIX 11 ceiling-change stability window.

    The window qualifies ONLY when, across >= 7 REAL elapsed days (the
    timestamp span of ordinary wall-clock -- accelerated/compressed fixture
    time can never produce it), >=95% of eligible Ultra runs complete
    WITHOUT concurrency-caused retry exhaustion, ZERO safety gates are
    bypassed, and telemetry is complete (every Ultra row carries its
    timestamp, mode and status).

    A qualifying window may PROPOSE a ceiling-change config revision and can
    never APPLY one: this function mutates nothing, the proposal record
    carries applied=False and requires='Trevor approval', and the operator
    ceiling constant is left untouched. A window below any threshold -- or
    shorter than 7 real days -- cannot unlock a proposal at all.

    Row contract (best-effort, never a network call): each row names its
    run (run_id), carries a parseable timestamp (ts/started_at/ended_at),
    mode, status ("complete" = completed successfully; "retry_exhausted" =
    a concurrency-caused retry exhaustion) and gates_bypassed (default 0).
    """
    all_rows = [r for r in (rows or []) if isinstance(r, dict)]
    tele_complete = True
    elig: List[Dict[str, Any]] = []
    gates_bypassed = 0
    for r in all_rows:
        if not r.get("mode") or not r.get("status"):
            tele_complete = False
            continue
        if str(r.get("mode")) != "ultra":
            continue
        if _parse_window_ts(r) is None:
            tele_complete = False
            continue
        bypassed = r.get("gates_bypassed") or 0
        try:
            bypassed = int(bypassed)
        except (TypeError, ValueError):
            bypassed = 1
        gates_bypassed += bypassed
        elig.append(r)

    eligible = False
    success_rate = 0.0
    span_days = 0.0
    n = len(elig)
    if n and tele_complete and gates_bypassed == 0:
        times = sorted(_parse_window_ts(r) for r in elig)
        span_days = (times[-1] - times[0]).total_seconds() / 86400.0
        completes = sum(1 for r in elig
                        if str(r.get("status")) == "complete")
        success_rate = completes / n
        if span_days >= 7.0 and success_rate >= 0.95:
            eligible = True

    result: Dict[str, Any] = {
        "eligible": eligible,
        "runs": n,
        "success_rate": round(success_rate, 4),
        "span_days": round(span_days, 4),
        "gates_bypassed": gates_bypassed,
        "telemetry_complete": tele_complete,
        "operator_ceiling": ULTRA_OPERATOR_CEILING,
        "thresholds": {"min_days": 7, "min_success_rate": 0.95,
                       "max_gates_bypassed": 0},
    }
    proposal = None
    if eligible:
        suggestion = max(
            ULTRA_OPERATOR_CEILING, (result["operator_ceiling"]))
        proposal = {
            "applied": False,  # this function can never apply a ceiling change
            "requires": "Trevor approval: an explicit config revision, "
                        "never a learned or provider-advertised increase",
            "current_operator_ceiling": ULTRA_OPERATOR_CEILING,
            "suggested_revision_review": (
                "revisit (do not auto-raise) the 100-concurrent ceiling "
                "after a qualifying 7-day window; any change is a separate "
                "operator-approved config revision"),
            "evidence": {
                "runs": n,
                "success_rate": result["success_rate"],
                "span_days": result["span_days"],
                "gates_bypassed": gates_bypassed,
            },
            "suggested_ceiling_for_review_only": suggestion,
        }
    result["proposal"] = proposal
    return result


# ---------------------------------------------------------------------------
# Profile eligibility (client-owned + consented + catalog health)
# ---------------------------------------------------------------------------
def _providers_of(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    providers = profile.get("providers")
    return providers if isinstance(providers, dict) else {}


def _eligible(providers: Dict[str, Any], alias_def: Dict[str, Any]) -> Tuple[bool, str]:
    """Is this alias's provider owned + consented + carrying the model?

    Returns (eligible, reason). Never reads, never returns, a credential:
    the profile stores presence booleans and model-id lists only."""
    raw_provider = str(alias_def.get("provider") or "")
    if not raw_provider:
        return False, "alias resolves to no provider"
    # FIX 17a: canonical dash-form provider id -- `ollama_cloud` and
    # `ollama-cloud` are the same provider; the profile store and the
    # catalog can never disagree about the spelling.
    provider = _norm_provider(raw_provider)
    # FIX 17a: the served model is what the provider's endpoint actually
    # accepts (catalog served_ids keyed (alias, provider)); eligibility is
    # judged against the id that will be sent, never the bare alias label.
    model = _served_model(alias_def, provider)
    entry = providers.get(provider)
    if not isinstance(entry, dict):
        # The profile may still store this provider under a raw spelling
        # (pre-normalisation row) -- try it before declaring unowned.
        entry = providers.get(raw_provider)
    if not isinstance(entry, dict):
        return False, f"provider {provider} not owned by the client profile"
    if entry.get("consented") is False:
        return False, f"provider {provider} is not consented"
    wired = entry.get("wired_models")
    if isinstance(wired, list) and wired:
        # Catalog health: the alias must resolve to a wired model id.
        # FIX 17b: exact match only -- no prefix, family, "same class",
        # "-r"-suffix or startswith heuristic. A profile that wired
        # z-ai/glm-5.3-flash must not silently bless glm-5.3 (or any other
        # sibling) as present: the served_ids table (keyed (alias, provider))
        # is the single source of what id each provider actually accepts,
        # and the wired list holds ids verbatim from the provider probe.
        # Spelling drift (underscores, whitespace, case) is folded by
        # _norm_model_id -- folding a name is never evidence of presence,
        # it only lets "glm_5.3 flash" and "z-ai/glm-5.3-flash" compare
        # like-for-like. Explicit '*' or '?' globs in the wired inventory
        # remain honored (fnmatch) because a probe may legitimately
        # declare a family wildcard.
        def _model_matches(m: str) -> bool:
            if not m:
                return False
            nm = _norm_model_id(m)
            return any(
                nm == _norm_model_id(w)
                or fnmatch.fnmatch(m, str(w))
                or fnmatch.fnmatch(str(w), m)
                for w in wired
            )

        if _model_matches(model):
            # FIX 114: wired on the provider AND a plausible key resolves --
            # a wired inventory without a resolvable credential never routes.
            if not provider_key_resolves(provider):
                return False, (f"provider {provider} has no resolvable key "
                               f"(FIX 114: no store carries a plausible "
                               f"credential)")
            return True, f"wired on {provider}"
        return False, (f"model {model} not in {provider}'s wired "
                       f"inventory ({len(wired)} wired)")
    # No wired inventory yet (never probed): presence/detected alone keeps
    # the provider eligible -- absence of a reading is never evidence of
    # absence (resource_profile keeps the last good inventory for the same
    # reason).
    if entry.get("presence") or entry.get("detected"):
        # FIX 114: presence alone is no longer dispatchable evidence -- the
        # provider must also carry a RESOLVABLE, plausible key. An unprobed
        # but keyless provider is still parked, with the key gate named.
        if not provider_key_resolves(provider):
            return False, (f"provider {provider} has no resolvable key "
                           f"(FIX 114: no store carries a plausible credential)")
        return True, f"{provider} present + key resolves (no wired inventory yet)"
    return False, f"provider {provider} has no presence or inventory evidence"


#: FIX 114 cache for the path-imported canon helper (defined before first use).
_SECRET_HELPER_MOD = None
_SECRET_HELPER_TRIED = False


# ---------------------------------------------------------------------------
# FIX 114: key-resolution eligibility gate. The router DECIDES; it never reads,
# receives, or returns a credential -- so the gate is presence-only: the
# provider's key name is resolved through the ONE secret-name canon
# (shared-utils/secret_helper, the seam capacity._read_secret_value uses) and
# the resolved VALUE (never surfaced) must pass looks_like_real_key. A route
# may resolve ONLY to a provider whose key resolves AND is plausible; a box
# with no OLLAMA_CLOUD_API_KEY in any store therefore never selects an
# ollama-cloud model -- the failure is named in the candidate row's reason
# (park/fail-closed) instead of burning a twenty-minute phase budget on
# "OLLAMA_CLOUD_API_KEY not set" at dispatch time.
# ---------------------------------------------------------------------------
_PROVIDER_KEY_NAMES: Dict[str, Tuple[str, ...]] = {
    "deepseek-direct": ("DEEPSEEK_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "ollama-cloud": ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY"),
    "ollama_cloud": ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY"),
    "agnes": ("AGNES_AI_API_KEY", "AGNES_API_KEY"),
    "kie": ("KIE_API_KEY",),
}


def _secret_helper():
    """Path-import shared-utils/secret_helper.py (FIX 67 canon helper).
    Returns the module or None. Same discovery order capacity.py uses."""
    global _SECRET_HELPER_MOD, _SECRET_HELPER_TRIED
    if _SECRET_HELPER_TRIED:
        return _SECRET_HELPER_MOD
    _SECRET_HELPER_TRIED = True
    import importlib.util
    skills_default = None
    try:
        from presentation_job.oc_paths import skills as _oc_skills
        skills_default = Path(_oc_skills())
    except Exception:  # noqa: BLE001 -- partial deploy keeps the Mac default
        skills_default = Path.home() / ".openclaw" / "skills"
    repo_root = None
    for anc in Path(__file__).resolve().parents:
        if (anc / "shared-utils" / "secret_helper.py").is_file():
            repo_root = anc
            break
    for d in (os.environ.get("SHARED_UTILS_DIR", "").strip(),
              str(repo_root / "shared-utils") if repo_root else "",
              str(skills_default / "shared-utils"),
              "/data/.openclaw/skills/shared-utils"):
        if d and (Path(d) / "secret_helper.py").is_file():
            try:
                spec = importlib.util.spec_from_file_location(
                    "secret_helper_s114", str(Path(d) / "secret_helper.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                _SECRET_HELPER_MOD = mod
            except Exception:  # noqa: BLE001 -- a broken helper is the no-canon path
                _SECRET_HELPER_MOD = None
            break
    return _SECRET_HELPER_MOD


def _secrets_env_files() -> Tuple[str, ...]:
    """Candidate secrets env files, platform-aware (FIX 68 oc_paths)."""
    try:
        from presentation_job.oc_paths import secrets_env_candidates
        return tuple(str(p) for p in secrets_env_candidates())
    except Exception:  # noqa: BLE001 -- standalone deploy falls back to Mac defaults
        return (str(Path.home() / ".openclaw" / "secrets" / ".env"),
                str(Path.home() / ".openclaw" / "secrets" / "secrets.env"),
                str(Path.home() / ".openclaw" / ".env"))


def _alias_family(env_key: str) -> Tuple[str, ...]:
    """The canon alias family of `env_key` (canonical spelling + aliases)."""
    helper = _secret_helper()
    if helper is None:
        return (env_key,)
    try:
        names = list(helper.alias_list(helper.canonical_for(env_key)))
        return tuple(n for n in names if isinstance(n, str) and n) or (env_key,)
    except Exception:  # noqa: BLE001 -- canon failure degrades to the direct name
        return (env_key,)


def _key_is_placeholder(value: str) -> bool:
    """Placeholder gate; uses the canon's is_placeholder when reachable."""
    if not value:
        return True
    helper = _secret_helper()
    if helper is not None:
        try:
            return bool(helper.is_placeholder(value))
        except Exception:  # noqa: BLE001 -- canon failure degrades to inline
            pass
    low = value.strip().lower()
    if len(low) < 10:
        return True
    for sub in ("paste_real_token", "your_key_here", "change_me", "changeme",
                "<todo>", "[replace]", "{{", "placeholder", "example_key",
                "todo:", "xxx"):
        if sub in low:
            return True
    if low.startswith("<") and low.endswith(">"):
        return True
    if low.startswith("[") and low.endswith("]"):
        return True
    return False


def provider_key_resolves(provider: Any) -> bool:
    """FIX 114 presence-only key gate: does `provider` have a credential that
    resolves (process env or the platform's secrets env files) AND passes
    looks_like_real_key? NEVER returns a value. Unknown providers answer
    False -- a provider with no known key name is not dispatchable, and
    normalising a name is never evidence a key exists."""
    token = str(provider or "").strip().lower().replace("_", "-").replace(" ", "-")
    names = None
    for key, candidates in _PROVIDER_KEY_NAMES.items():
        if str(key).lower().replace("_", "-") == token:
            names = candidates
            break
    if not names:
        return False
    helper = _secret_helper()

    def _plausible(value: str) -> bool:
        if _key_is_placeholder(value):
            return False
        if helper is not None:
            try:  # the canonical spelling judges the shape
                canonical = helper.canonical_for(names[0])
                return bool(helper.looks_like_real_key(value, canonical))
            except Exception:  # noqa: BLE001 -- gate failure degrades to inline
                pass
        return True

    for env_key in names:
        for accepted in _alias_family(env_key):
            value = (os.environ.get(accepted) or "").strip()
            if value and _plausible(value):
                return True
            for file_spec in _secrets_env_files():
                path = Path(file_spec).expanduser()
                try:
                    if not path.is_file():
                        continue
                    for line in path.read_text(
                            encoding="utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if line.startswith(f"{accepted}="):
                            candidate = line.split("=", 1)[1].strip() \
                                .strip('"').strip("'")
                            if candidate and _plausible(candidate):
                                return True
                except OSError:
                    continue
    return False


# ---------------------------------------------------------------------------
# THE decision
# ---------------------------------------------------------------------------
def resolve_route(phase_id: str, *,
                  profile: Optional[Dict[str, Any]] = None,
                  config_dir: Optional[Any] = None,
                  mode: Optional[str] = None) -> Dict[str, Any]:
    """Resolve one phase -> route decision.

    Returns a decision dict:
        {"phase_id", "capability", "mode", "router": "model_router",
         "requested_alias", "route": {"provider", "model"} | None,
         "reason", "candidates": [{alias, provider, model, eligible, reason}]}
    route=None means park/fail-closed (no eligible client-owned route);
    reason names every rejected candidate. Selection order is the fix
    spec's: required capability -> client-owned and consented providers ->
    catalog health -> mode budget -> fallback list. A disabled flag
    (PRESENTATION_MODEL_ROUTER=0) reports router="disabled", route=None --
    the dispatcher's documented rollback to its own DeepSeek path."""
    # THE MODE, resolved ONCE, here, by the one authority: explicit argument
    # > PRESENTATION_MODE env > "standard". Callers deep in the engine
    # (dispatch_complete, heal, credit_preflight) declare nothing and inherit
    # the mode the launcher exported into their process -- which is what makes
    # a typed `--mode Ultra` reach routing at all. mode=None is "nobody told
    # me", not "standard": standard is what nobody-told-me RESOLVES to, and
    # nothing lands in ultra by accident.
    if modes_enabled():
        mode = active_mode(mode)
    else:
        # PRESENTATION_MODES=0: the whole FIX 11 surface is inert, including
        # the env read. Byte-for-byte the pre-fix default.
        mode = str(mode or DEFAULT_MODE)
    decision: Dict[str, Any] = {
        "phase_id": phase_id,
        "capability": PHASE_CAPABILITY.get(phase_id, DEFAULT_CAPABILITY),
        "mode": mode,
    }
    if not flag_enabled():
        decision.update({
            "router": "disabled",
            "route": None,
            "requested_alias": None,
            "candidates": [],
            "reason": f"{FLAG_ENV}=0 rollback: dispatcher uses its pre-FIX-7 "
                      f"DeepSeek-direct path",
        })
        return decision
    decision["router"] = "model_router"

    capability = decision["capability"]
    if capability == "mechanical":
        decision.update({
            "route": None, "requested_alias": None, "candidates": [],
            "profile_state": "mechanical",
            "reason": "mechanical phase: no LLM route; manifest script "
                      "executor owns it",
        })
        return decision

    # The requested alias is the capability class's PRIMARY catalog alias
    # (the fix-spec Default column) -- a bare catalog label, never a literal
    # duplicated model id at a call site (FIX 13 resolves labels).
    requested_alias = str((CAPABILITY_CANDIDATES.get(capability) or [{}])[0].get("alias") or "")
    decision["requested_alias"] = requested_alias or None

    if profile is None:
        try:  # FIX 8 profile store (flag/env redirect honored by that module)
            from . import resource_profile as _rp  # package-relative
        except ImportError:  # pragma: no cover - direct file run
            try:
                import resource_profile as _rp  # type: ignore[no-redef]
            except ImportError:
                _rp = None  # type: ignore[assignment]
        if _rp is None:
            decision.update({"route": None, "candidates": [],
                             "profile_state": "absent",
                             "reason": "resource_profile unavailable"})
            return decision
        profile = _rp.load_profile(config_dir) if hasattr(_rp, "load_profile") else {}
    if profile.get("error") and not profile.get("providers"):
        profile = {}  # a broken store behaves like absent, never like empty

    providers = _providers_of(profile)
    if not providers:
        decision.update({
            "route": None, "candidates": [],
            "profile_state": "absent",
            "reason": "no client-owned providers in the resource profile -- "
                      "dispatcher default (pre-FIX-7 DeepSeek-direct path), "
                      "never a fabricated route",
        })
        return decision
    decision["profile_state"] = "has_providers"
    if modes_enabled():
        decision["mode_concurrency"] = mode_concurrency(mode, profile=profile)
        # The CAP, stamped beside the plan so a caller holding this decision
        # can narrow a measured width without reloading the profile (and so
        # the sidecar records which ceiling actually applied).
        decision["mode_ceiling"] = mode_ceiling(mode, profile=profile)

    # THE CLIENT'S CHOICE, ahead of the department default AND ahead of the
    # mode's cost policy.
    #
    # PRECEDENCE RULING (operator, 2026-09-04, verbatim): "I don't want to be
    # forced to do anything." An Economy launch is a cost preference the
    # OPERATOR expresses; a model plan is a choice the CLIENT expressed about
    # their own account. So Economy re-points only the classes the client left
    # to the department (client_governed below): where a declaration is in
    # force, Economy neither replaces it nor reorders the fallbacks behind it.
    # A declaration that failed its class floor and was not waived is NOT in
    # force -- the department default is serving that class, so the cost policy
    # applies to it exactly as it would for a client who declared nothing.
    #
    # `cands` is a COPY, never the module table (_mode_candidates copies now);
    # prepending into the live list would rewrite the default table
    # process-wide -- every later phase, every other client in the same
    # process, permanently.
    plan_pick = client_plan_for(capability, profile)
    client_governs = bool(plan_pick is not None
                          and (plan_pick["floor"]["ok"] or plan_pick["waived"]))
    cands: List[Dict[str, Any]] = _mode_candidates(
        capability, mode, client_governed=client_governs)
    client_prepended = False
    if plan_pick is not None:
        if client_governs:
            # Prepend and then judge it with the SAME _eligible() every default
            # candidate faces -- owned, consented, wired, key resolves. A client
            # choice jumps the QUEUE, never the GATE.
            # "alias" LAST: a catalog row carries its own "alias" field
            # (text.fast), and splatting it after ours would rename the client
            # row into a catalog alias -- which the loop below would then
            # re-resolve through the catalog, throwing the client's declared
            # provider away and routing the catalog's spelling instead.
            cands.insert(0, {**plan_pick["alias_def"],
                             "alias": plan_pick["alias"]})
            decision["requested_alias"] = plan_pick["alias"]
            client_prepended = True
            decision["client_plan"] = {
                "slot": plan_pick["slot"],
                "via": plan_pick["via"],
                "provider": plan_pick["declared"]["provider"],
                "model": plan_pick["declared"]["model"],
                "alias_source": plan_pick["alias_source"],
                "floor": "waived" if plan_pick["waived"] else "ok",
                "detail": plan_pick["floor"]["reason"],
            }
            if mode == "economy" and capability in ECONOMY_FLASH_REPOINT:
                decision["client_plan"]["economy_repoint"] = (
                    "suppressed -- the client declared this class, so Economy "
                    "did not re-point it")
        else:
            # Declared but below this class's floor and not waived: the class
            # DEFAULT serves it, and the fallback is stamped so the launcher
            # banner, the sidecar and the client report can all say so. Never a
            # dispatch-time surprise.
            decision["client_plan_floor"] = {
                "slot": plan_pick["slot"],
                "via": plan_pick["via"],
                "declared": dict(plan_pick["declared"]),
                "floor": plan_pick["floor"],
                "fallback_alias": requested_alias or None,
            }

    candidates: List[Dict[str, Any]] = []
    route: Optional[Dict[str, str]] = None
    reason = ""
    for cand in cands:
        alias = str(cand.get("alias") or "")
        if cand.get("provider") and cand.get("model"):
            # A candidate carrying its OWN resolved definition -- the
            # client-plan row prepended above. Used verbatim, never re-resolved
            # through the catalog: the client named a provider, and a catalog
            # lookup would silently substitute the catalog's own spelling for
            # it. Default rows carry an alias label only (plus the inert
            # allow_flash_fallback flag), so this branch never fires for them.
            alias_def = {k: v for k, v in cand.items() if k != "alias"}
        else:
            alias_def = resolve_alias(alias)
        row: Dict[str, Any] = {"alias": alias, **alias_def}
        if not alias_def:
            row.update({"eligible": False, "reason": "alias unknown to the catalog"})
            candidates.append(row)
            continue
        ok, why = _eligible(providers, alias_def)
        row["eligible"] = ok
        row["reason"] = why
        candidates.append(row)
        # catalog health + modality doctrine live in _eligible; a cheaper
        # model lacking the capability is never selected (its class simply
        # does not appear in this capability's candidate list).
        if ok and route is None:
            # FIX 17a: route.model is always the SERVED id for the selected
            # provider (catalog served_ids keyed (alias, provider)) -- the
            # dispatcher sends it verbatim, so the request body must carry
            # what the endpoint accepts (openrouter: z-ai/glm-5.3-flash, not
            # bare glm-5.3-flash). `_eligible` already judged the same id.
            # API shape stays route={"provider","model"} exactly: the
            # candidate row keeps the catalog model alias alongside.
            route = {"provider": alias_def["provider"],
                     "model": _served_model(alias_def, alias_def["provider"])}
            reason = ("primary" if len(candidates) == 1 or ok == candidates[0].get("eligible")
                      else f"fallback: {why}")
    if client_prepended:
        # Whether the client's declaration actually CARRIED is a fact about the
        # run, not an inference for a reader to make from the candidate list.
        decision["client_plan"]["applied"] = bool(
            candidates and candidates[0].get("eligible"))
        if not decision["client_plan"]["applied"]:
            decision["client_plan"]["rejected_reason"] = str(
                (candidates[0] if candidates else {}).get("reason") or "")
    if route is not None:
        first_eligible_idx = next(
            (i for i, c in enumerate(candidates) if c.get("eligible")), 0)
        if client_prepended and first_eligible_idx == 0:
            cp = decision["client_plan"]
            reason = (f"client model plan: {cp['slot']} slot declared "
                      f"{cp['provider']}/{cp['model']}"
                      + (" (floor waived by the client)"
                         if cp["floor"] == "waived" else ""))
        else:
            reason = "primary" if first_eligible_idx == 0 else \
                f"fallback: primary unavailable -- {candidates[0].get('reason', '')}"
        decision.update({"route": route, "reason": reason})
    else:
        rejected = "; ".join(f"{c.get('alias')}: {c.get('reason')}"
                             for c in candidates)
        decision.update({
            "route": None,
            "reason": f"no eligible route for capability '{capability}' "
                      f"({rejected}) -- park/fail-closed",
        })
    decision["candidates"] = candidates
    return decision
