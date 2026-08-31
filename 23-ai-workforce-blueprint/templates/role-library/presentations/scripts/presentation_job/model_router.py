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
import os
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
                "model": "glm-5.3",
                "modality": "text", "context_class": "long",
                "note": "GLM 5.3 via OpenRouter (fix-spec fallback column)"},
    "glm-flash": {"provider": "openrouter",
                  "model": "glm-flash",
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


def resolve_alias(alias: str) -> Dict[str, Any]:
    """One alias -> ({provider, model, modality, ...}) or {} when unknown.

    FIX 13's model_catalog wins when present; this built-in registry is the
    fallback, never duplicated at call sites."""
    try:  # FIX 13 hook -- the live catalog is authoritative when landed
        from presentation_job import model_catalog as _catalog  # type: ignore
        resolved = None
        for name in ("resolve_alias", "resolve"):  # FIX 13 landed names
            resolver = getattr(_catalog, name, None)
            if callable(resolver):
                try:
                    resolved = resolver(alias)
                except Exception:
                    resolved = None  # fail-closed catalog miss -> registry
                if isinstance(resolved, dict) and resolved.get("provider") \
                        and resolved.get("model"):
                    out = dict(resolved)
                    out.setdefault("modality", "text")
                    out.setdefault("context_class", "standard")
                    return out
    except Exception:  # noqa: BLE001 -- catalog absence never breaks routing
        pass
    return dict(DEFAULT_ALIAS_REGISTRY.get(alias) or {})


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
    "authoring": [
        {"alias": "deepseek-v4-pro", "allow_flash_fallback": False},
        {"alias": "deepseek-v4-flash"},
        {"alias": "glm-5.3"},
    ],
    "prompt_authoring": [  # P4-PROMPT: pro -> flash when context fits -> GLM
        {"alias": "deepseek-v4-pro", "allow_flash_fallback": False},
        {"alias": "deepseek-v4-flash"},
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
    provider = str(alias_def.get("provider") or "")
    model = str(alias_def.get("model") or "")
    if not provider:
        return False, "alias resolves to no provider"
    entry = providers.get(provider)
    if not isinstance(entry, dict):
        return False, f"provider {provider} not owned by the client profile"
    if entry.get("consented") is False:
        return False, f"provider {provider} is not consented"
    wired = entry.get("wired_models")
    if isinstance(wired, list) and wired:
        # Catalog health: the alias must resolve to a wired model id. Exact
        # id match, per-model, or family pattern; a profile may also wire a
        # sibling class member (e.g. the client wired v4-flash: the v4 pair
        # is one live-confirmed endpoint class, so v4-pro rides the same
        # ownership + consent + endpoint evidence).
        def _model_matches(m: str) -> bool:
            if not m:
                return False
            return any(
                m == w or fnmatch.fnmatch(m, str(w))
                or fnmatch.fnmatch(str(w), m + "-*")
                or (m.split("-r", 1)[0] == str(w).split("-r", 1)[0]
                    and m.rsplit("-", 1)[-1] == str(w).rsplit("-", 1)[-1])
                or _same_class(m, str(w))
                for w in wired
            )

        def _same_class(a: str, b: str) -> bool:
            def klass(m: str) -> str:
                parts = m.replace("_", "-").split("-")
                head = parts[0]
                tail = parts[-1] if len(parts) > 1 and len(parts[-1]) <= 8 else ""
                return f"{head}:{tail}"
            ka, kb = klass(a), klass(b)
            if ka == kb and klass(a) not in ("", ":"):
                return True
            # family prefix: deepseek-v4-* is one endpoint class
            pref = a.rsplit("-", 1)[0]
            return bool(pref) and (b == pref or b.startswith(pref + "-"))

        if _model_matches(model):
            return True, f"wired on {provider}"
        # family/class fallback: same endpoint class, sibling member wired
        try:
            family = model.rsplit("-", 1)[0]
        except Exception:
            family = model
        if any(str(w) == family or str(w).startswith(family) for w in wired):
            return True, (f"{provider} carries the {family} model family "
                          f"(wired: {', '.join(map(str, wired[:3]))})")
        return False, (f"model {model} not in {provider}'s wired "
                       f"inventory ({len(wired)} wired)")
    # No wired inventory yet (never probed): presence/detected alone keeps
    # the provider eligible -- absence of a reading is never evidence of
    # absence (resource_profile keeps the last good inventory for the same
    # reason).
    if entry.get("presence") or entry.get("detected"):
        return True, f"{provider} present (no wired inventory yet)"
    return False, f"provider {provider} has no presence or inventory evidence"


# ---------------------------------------------------------------------------
# THE decision
# ---------------------------------------------------------------------------
def resolve_route(phase_id: str, *,
                  profile: Optional[Dict[str, Any]] = None,
                  config_dir: Optional[Any] = None,
                  mode: str = "standard") -> Dict[str, Any]:
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

    candidates: List[Dict[str, Any]] = []
    route: Optional[Dict[str, str]] = None
    reason = ""
    for cand in CAPABILITY_CANDIDATES.get(capability, []):
        alias = str(cand.get("alias") or "")
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
            route = {"provider": alias_def["provider"],
                     "model": alias_def["model"]}
            reason = ("primary" if len(candidates) == 1 or ok == candidates[0].get("eligible")
                      else f"fallback: {why}")
    if route is not None:
        first_eligible_idx = next(
            (i for i, c in enumerate(candidates) if c.get("eligible")), 0)
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