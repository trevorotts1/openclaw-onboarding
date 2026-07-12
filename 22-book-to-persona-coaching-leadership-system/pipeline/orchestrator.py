#!/usr/bin/env python3
"""
BlackCEO Coaching Personas Matrix - Orchestration Engine
Manages the 3-phase book-to-persona pipeline across all 21 books.

Pipeline (v10.10.0 — PRD §5.4 'book-to-persona' chain):
  Phase 1 - Extraction (selector-resolved, see PRD §5.4):
              1. Ollama Cloud Kimi  →  2. OpenRouter Kimi  →
              3. Ollama Cloud DeepSeek V4 Pro  →
              4. OpenRouter DeepSeek V4 Pro  →
              5. OpenRouter Gemini 3.1 Flash Lite (cheapest fallback)
  Phase 2 - Analysis (same chain as Phase 1)
  Phase 3 - Synthesis (same chain — was GPT-5.3 Codex pre-v10.10.0;
              now uses the §5.4 chain so the cheapest fallback is
              Gemini Flash Lite, not GPT, matching N1 + cost policy)
  Phase 3b - Playbook Appendix (same chain as Phase 3): emits
              PLAYBOOK-APPENDIX.md next to persona-blueprint.md. The
              blueprint DISTILLS the book into governance + coaching; the
              appendix PRESERVES the book's reusable copy/funnel assets at
              full fidelity (headline/hook/subject formulas, page-by-page
              funnel recipes + sequences, sales/objection/follow-up/email
              scripts, frameworks/templates with steps, brand-voice language
              patterns, verbatim swipe file) so copy specialists write rich,
              brand-building copy. Quality floor enforced (see
              _validate_appendix + APPENDIX_* constants); fail-loud on the
              structure/honesty gate, one stricter retry on richness shortfall.

Anthropic models are FORBIDDEN by policy (N1). Filter applied at every tier.

Runs up to 4 books in parallel per phase. Manages queue automatically.

v6.6.0 additions:
  --single-book --slug SLUG  Run ONLY the named slug through phases 1-3;
                             reads its source.json to build a one-element BOOKS
                             entry (the #1 fix — without this, new sources added
                             via add-persona-from-source.sh never process).
  --source-json PATH         Alternate path for the source.json marker file.
  Path unification: BASE / BOOKS_DIR / PERSONAS_DIR and gemini-indexer.py
    PERSONAS_DIR all resolve to ONE canonical root so script-write = orchestrator-
    read = indexer-scan across VPS (/data/.openclaw/master-files/coaching-personas)
    and Mac (~/.openclaw/workspace/data/coaching-personas).
  Phase 6: after _append_persona_to_categories, invoke create_role_workspaces.py
    --refresh-personas-only so governing-personas.md auto-regenerates.
"""
from __future__ import annotations

import argparse
import os
import json
import re
import sys
import time
import asyncio
import subprocess
# aiohttp is only used by the live model-call code paths (Ollama Cloud /
# OpenRouter / Moonshot / Codex sessions). It is imported optionally so the
# pure-Python persona-registration and matcher-selectability code paths
# (e.g. _phase6_register_categories) stay importable and unit-testable in
# environments that do not install the heavy network dependency — such as the
# persona-blend-match-quality-guard CI job, whose end-to-end test imports this
# module only to exercise the write-side registration path. The
# `from __future__ import annotations` above keeps the aiohttp.* type hints in
# the async function signatures from being evaluated at import time, so the
# module imports cleanly without aiohttp; a live-call path that actually needs
# it still fails loudly (see _AiohttpUnavailable below).
try:
    import aiohttp
except ImportError:  # pragma: no cover - exercised only where aiohttp is absent
    class _AiohttpUnavailable:
        """Fails loudly only if a live model-call path is actually reached
        without aiohttp installed; import and offline code paths keep working."""

        def __getattr__(self, name):
            raise ImportError(
                "aiohttp is required for the book-to-persona live model-call "
                "pipeline (extraction/analysis/synthesis); install it with "
                "`pip install aiohttp`. It is intentionally optional so persona "
                "registration and matcher tests can import this module without it."
            )

    aiohttp = _AiohttpUnavailable()  # type: ignore
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# PRD 2.7: shared path resolver — persona-categories.json canonical path comes
# from get_openclaw_paths()["persona_categories"], not from a local candidate list.
_SHARED_UTILS = Path(__file__).resolve().parents[2] / "shared-utils"
if str(_SHARED_UTILS) not in sys.path:
    sys.path.insert(0, str(_SHARED_UTILS))
try:
    from detect_platform import get_openclaw_paths as _get_openclaw_paths  # type: ignore
    _OPENCLAW_PATHS_AVAILABLE = True
except ImportError:
    _OPENCLAW_PATHS_AVAILABLE = False

# §1.7: Import the shared persona-categories path resolver so orchestrator and
# generate-governing-personas.sh use the SAME resolution chain.
try:
    from resolve_persona_categories_path import get_persona_categories_path as _get_persona_categories_path  # type: ignore
    _PERSONA_RESOLVER_AVAILABLE = True
except ImportError:
    _PERSONA_RESOLVER_AVAILABLE = False

# D6 fix (ONB22-DUALITY-TAGS): the v1.3 additive audiences[]/topics[]/
# voice_style{}/usable_as[] duality-tag enrichment a newly-synthesized persona
# MAY carry (see _validate_duality_tags below) is gated through the SAME
# authoritative rulebook the Skill-23 voice-first AUDIENCE+TOPIC blend matcher
# enforces at read-time (persona_blend.validate_catalog_tags) — one rulebook,
# never two that can drift. Defensive/optional import: skill 22 must keep
# working standalone on a box where skill 23 isn't (yet) installed; duality-tag
# enrichment then degrades to a conservative structural-only check rather than
# blocking the pipeline (see _validate_duality_tags's fallback branch).
_SKILL23_SCRIPTS = Path(__file__).resolve().parents[2] / "23-ai-workforce-blueprint" / "scripts"
if str(_SKILL23_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL23_SCRIPTS))
try:
    import persona_blend as _persona_blend  # type: ignore
    _PERSONA_BLEND_AVAILABLE = True
except ImportError:
    _PERSONA_BLEND_AVAILABLE = False

# ─── PATHS ─────────────────────────────────────────────────────────────────────
# v6.6.0: Unified canonical root.
# VPS  → /data/.openclaw/master-files/coaching-personas
# Mac  → ~/.openclaw/workspace/data/coaching-personas
# The old ~/Downloads/openclaw-master-files path is kept as last-resort legacy.
def _resolve_canonical_base() -> Path:
    # G6 FIX (data-loss crash): mirror add-persona-from-source.sh:100-118 EXACTLY
    # so the shell's WRITE-root and the orchestrator's READ-root are the SAME
    # directory. Previously the shell wrote source.json under
    # <OC_ROOT>/master-files/coaching-personas whenever master-files/ existed,
    # while the orchestrator only honored that on the VPS root and otherwise fell
    # straight through to <OC_ROOT>/workspace/data/coaching-personas. On any Mac
    # box that had a ~/.openclaw/master-files dir, write-root != read-root →
    # source.json FileNotFoundError → the persona never built. Resolution per
    # OC_ROOT (VPS first, then Mac), identical ordering to the shell:
    #   1. <OC_ROOT>/master-files/coaching-personas    (when master-files/ exists)
    #   2. <OC_ROOT>/workspace/data/coaching-personas   (fallback)
    for oc_root in (Path("/data/.openclaw"), Path.home() / ".openclaw"):
        if (oc_root / "master-files").is_dir():
            return oc_root / "master-files" / "coaching-personas"
        if (oc_root / "workspace").is_dir():
            return oc_root / "workspace" / "data" / "coaching-personas"
    # Legacy path kept for backward compat on old setups
    return Path.home() / "Downloads" / "openclaw-master-files" / "coaching-personas"

BASE = _resolve_canonical_base()
BOOKS_DIR = BASE / "books"
PERSONAS_DIR = BASE / "personas"
PROJECT_DIR = BASE  # status + log live alongside the personas, not in ~/clawd
PROMPTS_DIR = Path(__file__).parent.parent / "agent-prompts"
STATUS_FILE = BASE / "pipeline-status.json"
LOG_FILE = BASE / "pipeline-log.txt"

# ─── MODEL IDs (v10.10.0: PRD §5.4 'book-to-persona' chain) ──────────────────
# Model selection is dynamic via shared-utils/select_model.py with the
# 'book-to-persona' purpose_tier chain (5 positions):
#   1. ollama/kimi-k*:cloud
#   2. openrouter/moonshot/kimi-k*
#   3. ollama/deepseek-v*-pro:cloud
#   4. openrouter/deepseek/deepseek-v*-pro
#   5. openrouter/google/gemini-*-flash-lite       ← cheapest fallback
#
# Phase 3 (synthesis) used to default to GPT-5.3 Codex when nothing else was
# available. As of v10.10.0 we no longer fall through to GPT — Gemini Flash
# Lite is the cheapest non-Anthropic non-GPT path, matching the audit's
# Phase 14.4 requirement (PRD §5.4) and the no-Anthropic-models policy (N1).
# Anthropic models are FORBIDDEN. Filter applied at every tier.
# The fallback strings below are last-resort defaults only used if
# select_model.py itself is unreachable.
def _resolve_model(skill: str, purpose: str, purpose_tier: str,
                   fallback: str, input_chars: int = None) -> str:
    """Call shared-utils/select_model.py with purpose-tier + optional input_chars.

    Passing input_chars makes the selector auto-pick DeepSeek V4-pro (1M ctx) for
    inputs that won't fit in Kimi's 262K window. Default behavior with no
    input_chars uses Kimi-first (smartest thinker).
    """
    selector = Path(__file__).resolve().parents[2] / "shared-utils" / "select_model.py"
    if not selector.exists():
        selector = Path("/data/.openclaw/skills/shared-utils/select_model.py")
    if not selector.exists():
        selector = Path.home() / ".openclaw" / "skills" / "shared-utils" / "select_model.py"
    if not selector.exists():
        selector = Path.home() / "Downloads" / "openclaw-master-files" / "shared-utils" / "select_model.py"
    if not selector.exists():
        return fallback
    cmd = ["python3", str(selector),
           "--skill", skill,
           "--purpose-tier", purpose_tier,
           "--purpose", purpose,
           "--format", "id"]
    if input_chars is not None:
        cmd.extend(["--input-chars", str(input_chars)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        model_id = result.stdout.strip()
        if model_id and "anthropic/" not in model_id.lower() and "claude-" not in model_id.lower():
            return model_id
    except Exception:
        pass
    return fallback


def _route_for(model_id: str) -> str:
    """Resolve the API route based on the model's prefix."""
    if model_id.startswith("ollama/"):
        return "ollama"
    if "codex" in model_id:
        return "openai-responses"
    return "openrouter"


# task-64 defect (b): the Ollama→OpenRouter FALLBACK used to build
#   model.replace("ollama/", "openrouter/").replace(":cloud", "")
# which produced e.g. 'openrouter/deepseek-v4-pro' and passed it to
# call_openrouter WITHOUT stripping the route prefix -> OpenRouter 400
# "not a valid model ID" (the DIRECT openrouter route strips the prefix; the
# fallback did not). It also never inserted the vendor segment OpenRouter
# requires (deepseek-v4-pro -> deepseek/deepseek-v4-pro). This helper is now
# the ONLY sanctioned conversion for every call_openrouter model argument.
# Vendor pairs mirror shared-utils/select_model.py's chain patterns
# (DEEPSEEK_PRO_OPENROUTER / DEEPSEEK_FLASH_OPENROUTER / KIMI_OPENROUTER).
_OLLAMA_OR_VENDOR_RULES = [
    (re.compile(r"^deepseek-v[\d.]+-(?:pro|flash)$"), "deepseek"),
    (re.compile(r"^kimi-k[\d.]+$"), "moonshotai"),
    (re.compile(r"^minimax-m[\d.]+$"), "minimax"),
]


def _openrouter_fallback_model(model_id: str) -> str:
    """
    Convert any chain model id into the OpenRouter API model id.

        openrouter/deepseek/deepseek-v4-pro -> deepseek/deepseek-v4-pro
        ollama/deepseek-v4-pro:cloud        -> deepseek/deepseek-v4-pro
        ollama/kimi-k2.6:cloud              -> moonshotai/kimi-k2.6
        deepseek/deepseek-v4-pro            -> deepseek/deepseek-v4-pro (pass-through)
    """
    m = (model_id or "").strip()
    if m.startswith("openrouter/"):
        return m[len("openrouter/"):]
    if m.startswith("ollama/"):
        bare = m[len("ollama/"):].split(":", 1)[0]  # drop ':cloud' / any tag
        for _pat, _vendor in _OLLAMA_OR_VENDOR_RULES:
            if _pat.match(bare):
                return f"{_vendor}/{bare}"
        # Unknown family: return the bare name (never a malformed
        # 'openrouter/...' route prefix). OpenRouter will reject it loudly
        # with the actual name in the error instead of a prefix artifact.
        return bare
    return m


def resolve_phase_model(phase: str, input_chars: int = None) -> tuple:
    """
    Resolve (model_id, route) for a given pipeline phase.
    Pass input_chars when the actual input size is known so the selector
    can context-switch to DeepSeek V4-pro for large/huge books.

    v10.10.0 — all three phases use the PRD §5.4 'book-to-persona' chain:
      normal context: Ollama Kimi → OpenRouter Kimi → Ollama DeepSeek Pro →
                      OpenRouter DeepSeek Pro → Gemini Flash Lite
      large context (800K-3M chars): same chain, large-input variant where
                      DeepSeek Pro (1M ctx) leads
      huge context  (> 3M chars):    DeepSeek Pro only

    No GPT in the chain. No Anthropic. Gemini Flash Lite is the cheapest
    fallback per PRD §5.4 and the audit's Phase 14.4 requirement.
    """
    purpose_map = {
        "phase1": "Phase 1 extraction",
        "phase2": "Phase 2 analysis",
        "phase3": "Phase 3 synthesis",
    }
    purpose = purpose_map.get(phase, phase)
    # v10.10.0: the LAST-RESORT fallback (used only when select_model.py is
    # itself unreachable) is now Gemini Flash Lite, not GPT/Kimi. This
    # matches PRD §5.4 (the 'book-to-persona' chain ends at Flash Lite) and
    # closes audit Phase 14.4 finding ("Phase 3 = GPT-5.3 Codex").
    # Trevor 2026-06-01: book-to-persona runs on the fleet-standard DeepSeek V4 Pro
    # chain (the latest). Primary = Ollama Cloud deepseek-v4-pro:cloud; the selector
    # falls to OpenRouter deepseek/deepseek-v4-pro if Ollama isn't on the box. No kimi.
    fallback = "ollama/deepseek-v4-pro:cloud"
    # Tier-5 (no Ollama, no OpenRouter, no models matching) falls to
    # Gemini Flash Lite per PRD §5.4 position 5 — this is the LAST RESORT.
    last_resort = "openrouter/google/gemini-3.1-flash-lite-preview"

    model_id = _resolve_model("book-to-persona", purpose, "book-to-persona", fallback, input_chars=input_chars)
    # If _resolve_model couldn't find anything, it falls back to the
    # `fallback` string above. If even that's not in the client's config,
    # final defense: Gemini Flash Lite. This makes the comment "no GPT in
    # the chain" structurally true.
    if not model_id:
        model_id = last_resort
    return model_id, _route_for(model_id)


# Default models for module import (resolved without book size — caller should re-resolve per book):
MODEL_EXTRACTION, MODEL_EXTRACTION_ROUTE = resolve_phase_model("phase1")
MODEL_ANALYSIS,   MODEL_ANALYSIS_ROUTE   = resolve_phase_model("phase2")
MODEL_SYNTHESIS,  MODEL_SYNTHESIS_ROUTE  = resolve_phase_model("phase3")

# ─── LIMITS ───────────────────────────────────────────────────────────────────
PARALLEL_LIMIT   = 40        # Max books processed simultaneously per phase
OPENROUTER_FALLBACK_FOLDERS = {"samit-disrupt-yourself", "attwood-passion-test"}  # Books that hit Kimi content filter
CHUNK_THRESHOLD  = 80000    # Characters - books above this get chunked for Phase 2
MAX_CHUNK_SIZE   = 70000    # Characters per chunk for Phase 2
MAX_RETRIES      = 3        # Retry failed API calls this many times
RETRY_DELAY      = 10       # Seconds between retries

# ─── PLAYBOOK APPENDIX FLOORS (Phase 3b) ──────────────────────────────────────
# The appendix (PLAYBOOK-APPENDIX.md) preserves the book's reusable copy/funnel
# assets at full fidelity. The HARD gate enforces STRUCTURE + HONESTY (file
# present, substantive, all 8 sections, Coverage Map) and FAILS LOUD if missed —
# but it deliberately does NOT hard-fail on asset COUNT, because a memoir or
# non-commercial book legitimately has few formulas/scripts and must mark them
# ABSENT rather than fabricate. Count/length shortfalls are WARN-level so the
# operator + QC see a thin appendix without the pipeline forcing invented assets.
APPENDIX_HARD_MIN_CHARS    = 6000   # any book — below this is a hard fail
APPENDIX_SOFT_MIN_CHARS    = 12000  # asset-rich books should clear this (warn below)
APPENDIX_MIN_PATTERN_BLOCKS = 12    # target count of "Pattern:" capture fields (warn below)
APPENDIX_MIN_EXAMPLE_BLOCKS = 12    # target count of "Worked example:" capture fields (warn below)
APPENDIX_REQUIRED_SECTIONS = ["## A", "## B", "## C", "## D", "## E", "## F", "## G", "## H"]
APPENDIX_MAX_RETRIES        = 1     # one stricter retry if the floor/targets are missed

# ─── API KEYS ─────────────────────────────────────────────────────────────────
def get_keys():
    """Read provider keys from the canonical secret stores.

    task-64 defect (a): values stored as KEY="..." (surrounding quotes) were
    passed through verbatim, producing a malformed Authorization: Bearer
    header -> OpenRouter 401 "Missing Authentication header". Values are now
    defensively DEQUOTED (one pair of matching surrounding single/double
    quotes stripped) and an optional leading `export ` is tolerated — the
    same normalization shared-utils/embedding_engine._read_secret applies.
    Also probes ALL canonical stores (legacy ~/clawd first for back-compat,
    then Mac + VPS), first-found-wins per key.
    """
    env_paths = [
        Path.home() / "clawd/secrets/.env",
        Path.home() / ".openclaw/secrets/.env",
        Path("/data/.openclaw/secrets/.env"),
    ]
    keys = {}
    for env_path in env_paths:
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            s = line.strip()
            if s.startswith("export "):
                s = s[len("export "):]
            if "=" not in s or s.startswith("#"):
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
            # Defensive dequote: strip ONE pair of matching surrounding quotes.
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            if k and k not in keys:
                keys[k] = v
    return keys

_KEYS = get_keys()
# v10.3.0: Ollama Cloud is now the primary route for heavy reasoning. The
# selector picks ollama/* first; we only need OpenRouter/OAuth as fallback
# routes if the client doesn't have Ollama Cloud configured.
OLLAMA_API_KEY      = _KEYS.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_API_KEY", "")
OPENROUTER_API_KEY  = _KEYS.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_API_KEY      = _KEYS.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
MOONSHOT_API_KEY    = _KEYS.get("MOONSHOT_API_KEY") or os.environ.get("MOONSHOT_API_KEY", "")  # deprecated, kept for back-compat only

# task-64 bug 3 (Ollama auth routing): the Ollama route now defaults to the
# LOCAL daemon (http://localhost:11434/api). The daemon is authenticated via
# `ollama signin` (~/.ollama/id_ed25519) and transparently proxies `*:cloud`
# models to Ollama Cloud — this WORKS on the operator box while the box's
# 21-char OLLAMA_API_KEY is a DEAD placeholder that returns bare 401 on
# ollama.com/api/chat. (Trap: ollama.com/api/tags is PUBLIC and returns 200
# for ANY key, so a dead key masquerades as valid — never validate an Ollama
# key against /api/tags.) An explicit OLLAMA_BASE_URL in secrets/.env or the
# env overrides the default; only a NON-local base sends (and requires) the
# bearer key.
_OLLAMA_LOCAL_BASE = "http://localhost:11434/api"
_ollama_base_cfg = (_KEYS.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_BASE_URL") or "").strip().rstrip("/")
if _ollama_base_cfg:
    OLLAMA_BASE_URL = _ollama_base_cfg if _ollama_base_cfg.endswith("/api") else _ollama_base_cfg + "/api"
else:
    OLLAMA_BASE_URL = _OLLAMA_LOCAL_BASE
OLLAMA_IS_LOCAL = ("localhost" in OLLAMA_BASE_URL) or ("127.0.0.1" in OLLAMA_BASE_URL)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL     = "https://api.openai.com/v1"


def _local_ollama_reachable(timeout: float = 1.0) -> bool:
    """Cheap TCP probe of the local Ollama daemon (no API call, no tokens)."""
    if not OLLAMA_IS_LOCAL:
        return False
    try:
        import socket
        from urllib.parse import urlparse
        u = urlparse(OLLAMA_BASE_URL)
        with socket.create_connection((u.hostname or "localhost", u.port or 11434),
                                      timeout=timeout):
            return True
    except OSError:
        return False


# No hard requirement on any single key — at least ONE provider ROUTE must be
# usable, but the selector decides which one to use. A signed-in LOCAL Ollama
# daemon counts as a route (bug 3): it needs NO API key at all.
#
# This precondition is enforced at the START of main() (i.e. a live run), NOT at
# module import time. Like the optional aiohttp import above, the pure-Python
# persona-registration / matcher-selectability code paths (e.g.
# _phase6_register_categories) MUST stay importable and unit-testable on a bare
# runner that has no provider route configured — such as the
# persona-blend-match-quality-guard CI job, whose end-to-end and duality-tag
# tests import this module only to exercise the write side (no live model call is
# ever made). A real CLI invocation still fails fast — before any orphan-guard or
# network work — because main() calls _assert_provider_route() first, so the
# fail-closed behavior a live run relies on is unchanged.
def _assert_provider_route():
    if not (OLLAMA_API_KEY or OPENROUTER_API_KEY or OPENAI_API_KEY or _local_ollama_reachable()):
        raise ValueError(
            "No usable model provider route found. Either run `ollama signin` so the "
            "local daemon (http://localhost:11434) can proxy *:cloud models, or set "
            "at least one of: OPENROUTER_API_KEY (fallback), OLLAMA_API_KEY (direct "
            "ollama.com — only needed with a non-local OLLAMA_BASE_URL), or "
            "OPENAI_API_KEY (last resort) in secrets/.env or as a container env var."
        )

# task-64 bug 4 (max_tokens ceiling): Ollama Cloud hard-caps each model's
# OUTPUT tokens; requesting more is a deterministic 400 ("max_tokens exceeds
# model's maximum") even when authenticated. deepseek-v4-pro's confirmed
# ceiling is 65536 — the pipeline asked for 120000 on Phase-3/single-book
# synthesis. Requests are clamped to the model's known ceiling (default 65536
# for unknown models, which is above every non-synthesis call here).
_MODEL_MAX_OUTPUT_TOKENS = {
    "deepseek-v4-pro": 65536,   # confirmed: Ollama Cloud 400s above this
}
_DEFAULT_MAX_OUTPUT_TOKENS = 65536


def _clamp_max_tokens(model: str, requested: int) -> int:
    base = (model or "").split(":", 1)[0]    # drop ':cloud' / tags
    base = base.rsplit("/", 1)[-1]           # drop vendor/route prefixes
    cap = _DEFAULT_MAX_OUTPUT_TOKENS
    for fam, c in _MODEL_MAX_OUTPUT_TOKENS.items():
        if base.startswith(fam):
            cap = c
            break
    if requested > cap:
        log(f"  max_tokens {requested} exceeds {model} output ceiling {cap} — clamping")
        return cap
    return requested


# ═════════════════════════════════════════════════════════════════════════════
# STRUCTURAL STORM GUARDS — "I can't have a storm like this" (operator directive)
# ─────────────────────────────────────────────────────────────────────────────
# A provider retry-storm (observed: ~1300 all-4xx requests in one day, zero
# tokens produced, ~10/15 books failed) is made STRUCTURALLY IMPOSSIBLE here —
# not merely less likely. Five guardrails, any one of which alone caps the blast
# radius:
#
#   G1 FAIL-FAST     retry ONLY 429 (rate-limit) and 5xx (server). EVERY other
#                    status — all 4xx incl. 400/401/402/403/404/408/422 — is
#                    non-transient and fails fast to the fallback. Hard cap of
#                    PROVIDER_MAX_RETRIES retries (429/5xx only).
#   G2 PREFLIGHT     before the build loop, ONE tiny probe per provider it will
#                    use; a deterministic auth/credit/param failure ABORTS the
#                    whole build before any phase runs (see preflight_providers).
#   G3 CIRCUIT-BRK   if a provider's FIRST CIRCUIT_BREAKER_TRIP real calls all
#                    fail with the SAME error class, the whole build aborts (no
#                    churn through the remaining books/phases).
#   G4 REQ BUDGET    a per-build HARD ceiling on total provider requests
#                    (REQUEST_BUDGET_MULTIPLIER x expected). The counter is
#                    module-global and shared by every concurrent book task, so
#                    total requests can never exceed budget + in-flight
#                    concurrency — a hard, finite bound regardless of how the
#                    errors are distributed.
#   G5 TOKEN CLAMP   _clamp_max_tokens (above) caps max_tokens to the model's
#                    real output ceiling so an over-ask can never 400.
#
# G1: 402 is included (credits/quota exhausted — must fail fast, never retry).
PROVIDER_MAX_RETRIES = 2                 # retry ONLY 429/5xx, at most twice
CIRCUIT_BREAKER_TRIP = 3
REQUEST_BUDGET_MULTIPLIER = 3
# Generous per-book expected-call estimate (phases 1-3 + chunk analyses +
# appendix + a couple of legit retries) so the GLOBAL budget is a true backstop
# ceiling, not a hair-trigger — the circuit breaker (G3) is the FAST stop. Env
# override lets an operator widen it for an unusually chunk-heavy batch.
PER_BOOK_EXPECTED_CALLS = int(os.environ.get("OPENCLAW_BOOK_EXPECTED_CALLS", "12"))


def _is_retryable_status(status: int) -> bool:
    """G1: retry ONLY 429 (rate-limit) and 5xx (server). EVERY other status is
    non-transient and MUST fail fast — a 4xx cannot be fixed by retrying, and a
    402 (no credits) / 401 (bad key) retried across every fallback tier is
    exactly what produced the storm."""
    return status == 429 or 500 <= status <= 599


# Retained for reference/back-compat; the live decision uses _is_retryable_status
# (retry-allowlist) which is the structural inverse — everything not explicitly
# retryable fails fast.
_NO_RETRY_STATUSES = frozenset({400, 401, 402, 403, 404, 408, 422})


class _DeterministicHTTPError(RuntimeError):
    """A non-transient HTTP status that will never succeed on retry — fail fast
    to the caller's provider fallback."""


class _BuildAbort(BaseException):
    """Abort the ENTIRE build immediately (budget / circuit-breaker / preflight).
    Subclasses BaseException ON PURPOSE so the per-phase `except Exception`
    handlers in run_extraction/analysis/synthesis cannot swallow it — it
    propagates straight up to main(), which logs it and exits non-zero."""


class _StormGuard:
    """Per-build global request budget (G4) + per-provider circuit breaker (G3).

    A single instance is created at build start (init_storm_guard) and consulted
    by EVERY provider call. Because the counter is shared across all concurrent
    book tasks, the total number of provider requests in a build can never exceed
    ``budget + in-flight concurrency`` — a hard structural bound that makes a
    storm impossible even if every call errors.
    """

    def __init__(self, budget: int):
        self.budget = max(1, int(budget))
        self.count = 0
        self.aborted_reason = None
        self._early = {}   # provider -> list[str] of the first few outcomes

    def charge(self, provider: str) -> None:
        self.count += 1
        if self.count > self.budget:
            self.aborted_reason = (
                f"GLOBAL REQUEST BUDGET EXCEEDED: {self.count} > {self.budget} "
                f"provider requests — aborting the build to prevent a request storm."
            )
            raise _BuildAbort(self.aborted_reason)

    def record(self, provider: str, ok: bool, error_class: str = None) -> None:
        e = self._early.setdefault(provider, [])
        if len(e) >= CIRCUIT_BREAKER_TRIP:
            return
        e.append("ok" if ok else f"err:{error_class}")
        if (not ok and len(e) == CIRCUIT_BREAKER_TRIP
                and all(o == f"err:{error_class}" for o in e)):
            self.aborted_reason = (
                f"CIRCUIT BREAKER tripped for provider {provider!r}: the first "
                f"{CIRCUIT_BREAKER_TRIP} calls ALL failed with {error_class!r} — "
                f"aborting the build (no churn through the remaining books/phases)."
            )
            raise _BuildAbort(self.aborted_reason)


_STORM = None  # set by init_storm_guard() at build start; None => guards inert


def init_storm_guard(expected_requests: int):
    """Create the per-build storm guard. Called once at build start."""
    global _STORM
    budget = REQUEST_BUDGET_MULTIPLIER * max(1, int(expected_requests))
    _STORM = _StormGuard(budget)
    log(f"  [storm-guard] global request budget = {budget} "
        f"({REQUEST_BUDGET_MULTIPLIER}x expected {expected_requests}); "
        f"circuit-breaker trips after {CIRCUIT_BREAKER_TRIP} same-class failures; "
        f"retries only on 429/5xx (max {PROVIDER_MAX_RETRIES}).")
    return _STORM


def _storm_charge(provider: str) -> None:
    if _STORM is not None:
        _STORM.charge(provider)


def _storm_record(provider: str, ok: bool, error_class: str = None) -> None:
    if _STORM is not None:
        _STORM.record(provider, ok, error_class)

# ─── BOOK REGISTRY ────────────────────────────────────────────────────────────
BOOKS = [
    # Priority 1 - Build First
    {"title": "Atomic Habits",                  "author": "James Clear",       "file": "Atomic Habits - James Clear.pdf",                      "folder": "clear-atomic-habits"},
    {"title": "SPIN Selling",                   "author": "Neil Rackham",      "file": "SPIN Selling - Neil Rackham.pdf",                      "folder": "rackham-spin-selling"},
    {"title": "Never Split the Difference",     "author": "Chris Voss",        "file": "Never Split the Difference - Chris Voss.pdf",          "folder": "voss-never-split-difference"},
    {"title": "Influence",                      "author": "Robert Cialdini",   "file": "Influence - Robert Cialdini.pdf",                      "folder": "cialdini-influence"},
    {"title": "Building a StoryBrand",           "author": "Donald Miller",     "file": "Building a StoryBrand - Donald Miller.pdf",            "folder": "miller-building-storybrand"},
    # Priority 2
    {"title": "To Sell Is Human",               "author": "Daniel Pink",       "file": "To Sell Is Human - Daniel Pink.pdf",                   "folder": "pink-to-sell-is-human"},
    {"title": "Exactly What to Say",            "author": "Phil Jones",        "file": "Exactly What to Say - Phil Jones.pdf",                 "folder": "jones-exactly-what-to-say"},
    {"title": "Start with Why",                 "author": "Simon Sinek",       "file": "Start with Why - Simon Sinek.pdf",                     "folder": "sinek-start-with-why"},
    {"title": "The Power of Habit",             "author": "Charles Duhigg",    "file": "The Power of Habit - Charles Duhigg.pdf",              "folder": "duhigg-power-of-habit"},
    {"title": "Good to Great",                  "author": "Jim Collins",       "file": "Good to Great - Jim Collins.pdf",                      "folder": "collins-good-to-great"},
    # Priority 3
    {"title": "The 5 Second Rule",              "author": "Mel Robbins",       "file": "The 5 Second Rule - Mel Robbins.pdf",                  "folder": "robbins-five-second-rule"},
    {"title": "Drive",                          "author": "Daniel Pink",       "file": "Drive - Daniel Pink.pdf",                              "folder": "pink-drive"},
    {"title": "Find Your Why",                  "author": "Simon Sinek",       "file": "Find Your Why - Simon Sinek.pdf",                      "folder": "sinek-find-your-why"},
    {"title": "Cant Hurt Me",                   "author": "David Goggins",     "file": "Cant Hurt Me - David Goggins.pdf",                     "folder": "goggins-cant-hurt-me"},
    {"title": "Instinct",                       "author": "TD Jakes",          "file": "Instinct - TD Jakes.pdf",                              "folder": "jakes-instinct"},
    # Priority 4
    {"title": "Set Boundaries Find Peace",      "author": "Nedra Tawwab",      "file": "Set Boundaries Find Peace - Nedra Tawwab.pdf",         "folder": "tawwab-set-boundaries-find-peace"},
    {"title": "Atlas of the Heart",             "author": "Brene Brown",       "file": "Atlas of the Heart - Brene Brown.pdf",                 "folder": "brown-atlas-of-heart"},
    {"title": "Becoming",                       "author": "Michelle Obama",    "file": "Becoming - Michelle Obama.pdf",                        "folder": "obama-becoming"},
    {"title": "The Light We Carry",             "author": "Michelle Obama",    "file": "The Light We Carry - Michelle Obama.pdf",              "folder": "obama-light-we-carry"},
    {"title": "Hook Point",                     "author": "Brendan Kane",      "file": "Hook_Point",                                           "folder": "kane-hook-point"},
    {"title": "When",                           "author": "Daniel Pink",        "file": "When - Dan Pink.pdf",                                       "folder": "pink-when"},
    {"title": "Building a Second Brain",         "author": "Tiago Forte",        "file": "Building a Second Brain - Tiago Forte.pdf",                 "folder": "forte-building-second-brain"},
    {"title": "Crucial Conversations",           "author": "Grenny Patterson",   "file": "Crucial Conversations - Grenny Patterson.pdf",              "folder": "grenny-crucial-conversations"},
    {"title": "Profit First",                    "author": "Mike Michalowicz",   "file": "Profit First - Mike Michalowicz.pdf",                       "folder": "michalowicz-profit-first"},
    {"title": "The Let Them Theory",             "author": "Mel Robbins",        "file": "The Let Them Theory - Mel Robbins.pdf",                     "folder": "robbins-let-them-theory"},
    {"title": "The 5 AM Club",                   "author": "Robin Sharma",       "file": "The 5 AM Club - Robin Sharma.pdf",                          "folder": "sharma-5am-club"},
    {"title": "Copy Hackers Value Proposition",  "author": "Joanna Wiebe",      "file": "Copy Hackers Value Proposition - Joanna Wiebe.pdf",        "folder": "wiebe-copy-hackers"},
    {"title": "The Copywriters Handbook",         "author": "Robert Bly",         "file": "The Copywriters Handbook - Robert Bly.pdf",                "folder": "bly-copywriters-handbook"},
    {"title": "Relentless",                       "author": "Tim Grover",         "file": "Relentless - Tim Grover.pdf",                              "folder": "grover-relentless"},
    {"title": "Code of the Extraordinary Mind",   "author": "Vishen Lakhiani",    "file": "Code of the Extraordinary Mind - Vishen Lakhiani.pdf",     "folder": "lakhiani-extraordinary-mind"},
    {"title": "Oversubscribed",                   "author": "Daniel Priestley",   "file": "Oversubscribed - Daniel Priestley.mobi",                   "folder": "priestley-oversubscribed"},
    {"title": "Disrupt Yourself",                 "author": "Jay Samit",          "file": "Disrupt Yourself - Jay Samit.pdf",                         "folder": "samit-disrupt-yourself"},
    {"title": "Words that Change Minds",          "author": "Shelle Rose Charvet","file": "Words that Change Minds - Shelle Rose Charvet.pdf",        "folder": "charvet-words-change-minds"},
    {"title": "The PARA Method",                  "author": "Tiago Forte",        "file": "The PARA Method - Tiago Forte.pdf",                        "folder": "forte-para-method"},
    {"title": "The Passion Test",                 "author": "Janet Attwood",      "file": "The Passion Test - Attwood.pdf",                           "folder": "attwood-passion-test"},
    {"title": "This Is Marketing",                "author": "Seth Godin",         "file": "This Is Marketing - Seth Godin.azw3",                      "folder": "godin-this-is-marketing"},
    {"title": "The 12 Week Year",                 "author": "Brian Moran",        "file": "The 12 Week Year - Moran Lennington.pdf",                  "folder": "moran-12-week-year"},
    {"title": "100M Offers",                      "author": "Alex Hormozi",       "file": "100M Offers - Alex Hormozi.pdf",                           "folder": "hormozi-100m-offers"},
    {"title": "Good to Great Summary",          "author": "Jim Collins",       "file": "Good to Great Summary - Jim Collins.pdf",              "folder": "collins-good-to-great-summary"},
]

# ─── PERSONA CATEGORIES UPDATER (PRD 2.7) ────────────────────────────────────
def _persona_categories_path() -> Path:
    """Locate persona-categories.json via the shared path resolver (§1.7 / PRD 2.7).

    Resolution order (§3.1):
    1. get_openclaw_paths()["persona_categories"] from detect_platform.py (canonical)
    2. shared resolve_persona_categories_path.get_persona_categories_path() (§1.7 reconciliation)
    3. BASE / persona-categories.json (local fallback)

    Both this function and generate-governing-personas.sh now call the SAME
    resolve_persona_categories_path resolver, eliminating the workspace/data/coaching-personas/
    vs workspace/coaching-personas/ path drift (§1.7).
    """
    if _OPENCLAW_PATHS_AVAILABLE:
        try:
            return _get_openclaw_paths()["persona_categories"]
        except Exception as e:
            print(f"[orchestrator] WARNING: get_openclaw_paths() failed ({e}); trying shared resolver.")

    # §1.7: Try the shared resolver (same chain as generate-governing-personas.sh)
    if _PERSONA_RESOLVER_AVAILABLE:
        try:
            resolved = _get_persona_categories_path(fail_loud=False)
            if resolved and resolved.is_file():
                return resolved
        except Exception as e:
            print(f"[orchestrator] WARNING: resolve_persona_categories_path failed ({e}); using BASE fallback.")

    # Final fallback — should not occur on a properly installed box.
    return BASE / "persona-categories.json"


def _ledger_append_phase6b_skip(folder: str, detail: str) -> None:
    """§1.7.3: Append a Phase-6b skip/fail record to the add-ledger so converge
    knows to retry governing-personas.md refresh. Best-effort — never raises."""
    import fcntl
    from datetime import datetime, timezone

    oc_root_candidates = [Path("/data/.openclaw"), Path.home() / ".openclaw"]
    oc_root = next((c for c in oc_root_candidates if c.is_dir()), None)
    if not oc_root:
        return

    ledger_dir = oc_root / "extension-sync"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "add-ledger.jsonl"
    record = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "persona",
        "slug": folder,
        "status": "phase6b-skip",
        "detail": detail,
        "by": "orchestrator",
    }, separators=(",", ":")) + "\n"
    try:
        with open(ledger_path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(record)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass  # Best-effort


def _auto_classify_persona_tags(folder: str, book: dict,
                                domain_vocab: list, perspective_vocab: list):
    """G6 FIX (routing-invisibility): deterministically classify a new persona's
    domain[] + perspective[] from its own synthesized text against the controlled
    vocab, so the dept-scope filter can route to it WITHOUT a manual tagging step.

    No model call (no token furnace, fully offline + idempotent). Returns
    (domain_tags, perspective_tags). domain[] is GUARANTEED non-empty — the
    dept-scope filter excludes any persona with no matching domain, so an empty
    domain is exactly the "invisible to routing" failure this fixes; we fall back
    to the universal 'coaching' domain (every book in this skill is a
    coaching/leadership work) when nothing more specific matches.
    """
    import re

    # Densest synthesized source first, then the analysis, then raw extraction.
    text_parts = [str(book.get("title", "")), str(book.get("author", ""))]
    for fname in ("persona-blueprint.md", "analysis-notes.md", "extraction-notes.md"):
        p = PERSONAS_DIR / folder / fname
        if p.exists():
            try:
                text_parts.append(p.read_text(errors="ignore"))
            except Exception:
                pass
            break  # one source is enough; blueprint is the synthesized superset
    text = " ".join(text_parts).lower()

    def _count(term: str) -> int:
        # Word-boundary match so short tokens (e.g. 'men') don't match inside
        # 'management'/'women'. Phrases match as whole phrases.
        return len(re.findall(r"\b" + re.escape(term) + r"\b", text))

    # ── domain[] : direct vocab match (tag, de-hyphenated, joined) ──────────
    domain_scores = {}
    for tag in (domain_vocab or []):
        variants = {tag, tag.replace("-", " "), tag.replace("-", "")}
        score = sum(_count(v) for v in variants)
        if score >= 2:  # threshold trims one-off noise mentions
            domain_scores[tag] = score
    domain_tags = [t for t, _ in sorted(domain_scores.items(),
                                        key=lambda kv: kv[1], reverse=True)][:6]
    if not domain_tags:
        if "coaching" in (domain_vocab or []):
            domain_tags = ["coaching"]
        elif domain_vocab:
            domain_tags = [domain_vocab[0]]
        else:
            domain_tags = ["coaching"]

    # ── perspective[] : keyword map, restricted to the controlled vocab ─────
    _PERSPECTIVE_KEYWORDS = {
        "african-american-experience": ["african american", "black community",
                                        "black men", "black women", "systemic racism"],
        "womens-challenges": ["women", "woman", "female", "motherhood"],
        "mens-challenges": ["men", "man", "masculinity", "fatherhood", "brotherhood"],
        "family-relationships": ["family", "parenting", "marriage", "household"],
        "faith-spirituality": ["faith", "spiritual", "prayer", "scripture", "biblical"],
        "love-romantic-relationships": ["romantic", "dating", "intimacy", "courtship"],
    }
    perspective_scores = {}
    for tag in (perspective_vocab or []):
        kws = _PERSPECTIVE_KEYWORDS.get(tag)
        if not kws:
            continue
        score = sum(_count(k) for k in kws)
        if score >= 2:
            perspective_scores[tag] = score
    perspective_tags = [t for t, _ in sorted(perspective_scores.items(),
                                             key=lambda kv: kv[1], reverse=True)][:3]

    return domain_tags, perspective_tags


# ─── P13-2: persona-categories.json schema-lint gate (FINAL-REVIEW-2026-07-01) ──
# PERSONA-ROUTER.md / persona-categories.README.md DOCUMENT the rule that every
# personas[*].domain / .perspective value must come from the top-level
# domainTags[]/perspectiveTags[] controlled vocab (or extend it with a
# well-formed new tag) — nothing MACHINE-ENFORCED it before this gate. A
# malformed append (wrong type, empty string, stray whitespace, a value that
# neither matches the vocab nor is a well-formed new tag) would silently write
# into persona-categories.json and orphan that persona from persona-selector-v2.py
# Stage-B category filtering (build_candidate_pool's dept-scope filter matches
# literal tag membership). This gate runs immediately before every write in
# _append_persona_to_categories and HARD FAILS — raising
# PersonaCategoriesSchemaError naming the offending key — rather than writing
# a malformed entry. The caller (process_book, Phase 6) already wraps this
# call in try/except and logs the failure per the pipeline's existing
# non-fatal-to-the-book convention (mirrors Phase 6b's handling below it) —
# the persona-categories.json FILE itself is simply never written when this
# gate fires, so a malformed entry can never land on disk.
_TAG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class PersonaCategoriesSchemaError(ValueError):
    """Raised when a persona-categories.json append does not conform to the
    documented schema (well-formed domainTags[]/perspectiveTags[] membership
    or well-formed extension). The message always names the offending key."""


# ─── F1.4 (DEP-12): Phase-6 categories-write FAIL-LOUD + auto-repair contract ──
# BEFORE this fix, process_book's Phase-6 wrapper caught EVERY exception from
# _append_persona_to_categories and logged a WARNING — the run still "succeeded"
# (exit 0). A blueprint that failed the schema-lint gate (or any categories
# write) was left on disk with NO key under personas-categories.json.personas,
# and since persona-selector-v2.py:list_available_personas() reads exactly that
# dict's KEYS as the persona universe, the persona was INVISIBLE to the selector
# on that box — an unselectable orphan, the mirror of F1.2's "registered but not
# embedded" silent-success (mirrors FDN-5's fail-loud exit pattern).
#
# The contract now has TWO independent guarantees:
#   (1) NEVER-TO-ZERO on registration itself — the persona is ALWAYS given a
#       categories key. When the normal (auto-classified) append fails, an
#       AUTO-REPAIR path re-registers the entry with a SAFE-DEFAULT tag set
#       (domain=PHASE6_SAFE_DEFAULT_DOMAIN, empty perspective) plus a
#       needs_retag:true marker, rather than skipping the entry. domain[] is a
#       controlled-vocab tag ('leadership' — every book in this skill is a
#       coaching/leadership work), so the safe-default entry passes both the
#       schema-lint gate and persona_fleet.py sync-categories validation, i.e. it
#       is publishable and immediately routable.
#   (2) FAIL-LOUD — a Phase-6 categories write that needed the auto-repair path
#       (or failed even that) is recorded so main() exits with a DISTINCT
#       non-zero code (PHASE6_CATEGORIES_EXIT_CODE=9), never a silent success.
#       The caller (add-persona-from-source.sh / the inbox watcher) can then tell
#       "needs operator re-tag" apart from a clean build and route to retry /
#       quarantine instead of moving the source to processed/.
PHASE6_CATEGORIES_EXIT_CODE = 9  # distinct from F1.2's EMBED_FAILED (8)

# never-to-zero applied to registration itself: the safe-default domain used by
# the auto-repair path so a persona is ALWAYS registered (never invisible to the
# selector universe). 'leadership' is a controlled-vocab domainTags member.
PHASE6_SAFE_DEFAULT_DOMAIN = ["leadership"]

# Folders whose Phase-6 categories write took the fail-loud/auto-repair path this
# run. Checked at the end of main() to emit PHASE6_CATEGORIES_EXIT_CODE. Module
# level (not per-book) so the async batch gather aggregates across books.
_CATEGORIES_WRITE_FAILURES: list = []


def pipeline_had_categories_failures() -> bool:
    """True iff any Phase-6 categories write needed auto-repair / failed this run
    (F1.4). Consulted by main() to decide the fail-loud non-zero exit."""
    return bool(_CATEGORIES_WRITE_FAILURES)


def _lint_tag_list(entry_key: str, tags, vocab: list) -> list:
    """Validate `tags` (a persona entry's domain[] or perspective[] list)
    against `vocab` (the top-level domainTags[]/perspectiveTags[] controlled
    vocab). Every tag must be a well-formed lowercase kebab-case string, and
    must EITHER already exist in `vocab` OR be appended to it here (a
    well-formed extension — the documented, allowed way to introduce a new
    tag). Anything else (wrong type, empty, malformed characters) is a hard
    fail naming the offending key ('<entry_key>[<index>]') so the caller can
    never write a malformed entry.

    Returns the (possibly-extended) vocab list; does not mutate the input.
    """
    if tags is None:
        return list(vocab)
    if not isinstance(tags, list):
        raise PersonaCategoriesSchemaError(
            f"persona-categories.json schema-lint: '{entry_key}' must be a "
            f"list, got {type(tags).__name__}"
        )
    new_vocab = list(vocab)
    for i, tag in enumerate(tags):
        offending_key = f"{entry_key}[{i}]"
        if not isinstance(tag, str) or not tag.strip():
            raise PersonaCategoriesSchemaError(
                f"persona-categories.json schema-lint: malformed tag at "
                f"'{offending_key}' (must be a non-empty string, got {tag!r})"
            )
        if not _TAG_RE.match(tag):
            raise PersonaCategoriesSchemaError(
                f"persona-categories.json schema-lint: malformed tag at "
                f"'{offending_key}' = {tag!r} (must be lowercase kebab-case, "
                f"e.g. 'sales-persuasion' — does not match {_TAG_RE.pattern!r})"
            )
        if tag not in new_vocab:
            # Well-formed NEW tag — the documented-allowed way to extend the
            # controlled vocab.
            new_vocab.append(tag)
    return new_vocab


def _lint_persona_categories_write(data: dict, folder: str) -> None:
    """Hard-fail schema-lint gate for a persona-categories.json write.

    Validates the about-to-be-written entry at data["personas"][folder]
    against domainTags[]/perspectiveTags[], extending those controlled-vocab
    arrays IN PLACE (on `data`) when a new tag is well-formed, and raising
    PersonaCategoriesSchemaError (naming the offending key) on anything
    malformed. Call immediately before every json.dump in
    _append_persona_to_categories — never after.
    """
    entry = data.get("personas", {}).get(folder)
    if not isinstance(entry, dict):
        raise PersonaCategoriesSchemaError(
            f"persona-categories.json schema-lint: 'personas.{folder}' must "
            f"be an object, got {type(entry).__name__}"
        )
    data["domainTags"] = _lint_tag_list(
        f"personas.{folder}.domain", entry.get("domain"),
        data.get("domainTags", []) or [],
    )
    data["perspectiveTags"] = _lint_tag_list(
        f"personas.{folder}.perspective", entry.get("perspective"),
        data.get("perspectiveTags", []) or [],
    )


# ─── D6 fix (ONB22-DUALITY-TAGS): v1.3 duality-tag enrichment parse + gate ─────
# BEFORE this fix, NOTHING in the pipeline ever wrote audiences[]/topics[]/
# voice_style{}/usable_as[] for a newly-synthesized persona — only the one-time
# 2026-07-09 backfill (v6.17.0, see CHANGELOG.md) carries them, so the Skill-23
# blend matcher's candidate universe was frozen at those 99 personas forever
# (persona_blend.match_audience_persona / match_topic_persona can only pick a
# persona that carries these tags). The Phase-3 synthesis model MAY now emit an
# OPTIONAL '## Duality Tags' block (agent-prompts/synthesis-agent-prompt.md,
# whose system prompt is dynamically extended with the LIVE audienceTags[]/
# topicTags[] vocab by _synthesis_system() below — vocab-first, so a proposed
# tag is chosen FROM the existing controlled vocabulary rather than invented).
#
# This layer is strictly ADDITIVE and NEVER-TO-ZERO-safe for core registration:
#   • absent block  -> NO-OP (matches persona_blend.py's own pre-enrichment
#                      semantics; an entry with only domain/perspective/custom
#                      stays perfectly valid).
#   • malformed/rejected block -> reported LOUD (printed diagnostic + recorded
#                      in _DUALITY_TAG_WRITE_FAILURES for introspection/tests)
#                      and OMITTED — never written half-valid, and never blocks
#                      the domain/perspective registration F1.4 guarantees.
_DUALITY_BLOCK_RE = re.compile(
    r"##\s*Duality\s+Tags.*?```json\s*(\{.*?\})\s*```",
    re.IGNORECASE | re.DOTALL,
)

# Folders whose '## Duality Tags' block was present but rejected (malformed
# JSON or failed the persona_blend.validate_catalog_tags gate) this run.
# Informational only — deliberately does NOT feed PHASE6_CATEGORIES_EXIT_CODE;
# enrichment failing must never orphan a persona from core domain/perspective
# routing. Module level so the async batch gather aggregates across books
# (mirrors _CATEGORIES_WRITE_FAILURES).
_DUALITY_TAG_WRITE_FAILURES: list = []


def pipeline_had_duality_tag_failures() -> bool:
    """True iff any persona's '## Duality Tags' block was present but rejected
    this run. Informational/test hook only — never changes the process exit
    code (see module comment above _DUALITY_BLOCK_RE)."""
    return bool(_DUALITY_TAG_WRITE_FAILURES)


def _parse_duality_tags_block(blueprint_text: str):
    """Extract the OPTIONAL v1.3 duality-tag block from a synthesized
    persona-blueprint.md. Returns (parsed_dict_or_None, error_or_None):

      (None, None)    — no '## Duality Tags' heading found (pre-enrichment /
                         older prompt version) — NOT a failure.
      (None, "<msg>") — heading present but the ```json {...}``` block is
                         missing or not valid JSON — a real authoring defect,
                         reported LOUD by the caller.
      (dict, None)    — parsed; shape + vocab membership are validated
                         separately by _validate_duality_tags.
    """
    if not blueprint_text or not re.search(r"##\s*Duality\s+Tags", blueprint_text, re.IGNORECASE):
        return None, None
    m = _DUALITY_BLOCK_RE.search(blueprint_text)
    if not m:
        return None, ("'## Duality Tags' heading present but no parseable "
                      "```json { ... } ``` block follows it")
    try:
        parsed = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return None, f"'## Duality Tags' json block is not valid JSON: {e}"
    if not isinstance(parsed, dict):
        return None, "'## Duality Tags' json block must be a JSON object"
    return parsed, None


def _validate_duality_tags(folder: str, entry_with_duality: dict, data: dict) -> list:
    """Gate a candidate duality-enriched entry through the SAME authoritative
    validator the Skill-23 blend matcher's own catalog gate uses
    (persona_blend.validate_catalog_tags) — one rulebook, reused, so the
    write-time gate here can never drift from the read-time contract. Returns
    a list of error strings (empty list = ok).

    Falls back to a minimal structural check (list types + USABLE_AS_ENUM +
    voice_style.summary required) when skill 23 isn't importable on this box
    (defensive — skill 22 must still run standalone) — never silently accepts
    a malformed block either way.
    """
    if _PERSONA_BLEND_AVAILABLE:
        mini_catalog = {
            "schemaVersion": "1.3",
            "audienceTags": data.get("audienceTags", []) or [],
            "topicTags": data.get("topicTags", []) or [],
            "personas": {folder: entry_with_duality},
        }
        result = _persona_blend.validate_catalog_tags(mini_catalog)
        return list(result.get("errors") or [])
    # Fallback structural check (persona_blend not importable on this box).
    errs = []
    ua = entry_with_duality.get("usable_as")
    if ua is not None:
        if not isinstance(ua, list) or any(x not in ("audience", "topic", "task") for x in ua):
            errs.append(f"{folder}: usable_as must be a list subset of "
                        f"[audience, topic, task]")
    for field in ("audiences", "topics"):
        v = entry_with_duality.get(field)
        if v is not None and not isinstance(v, list):
            errs.append(f"{folder}: '{field}' must be a list")
    vs = entry_with_duality.get("voice_style")
    if vs is not None and (not isinstance(vs, dict) or not str(vs.get("summary", "")).strip()):
        errs.append(f"{folder}: voice_style.summary is required and missing")
    return errs


def _register_duality_tags(folder: str, data: dict) -> None:
    """Parse + gate the OPTIONAL '## Duality Tags' block out of folder's
    persona-blueprint.md and, when well-formed, merge audiences[]/topics[]/
    voice_style{}/usable_as[] into data["personas"][folder] IN PLACE. Call
    AFTER the base entry (domain/perspective/custom/…) has been assigned and
    BEFORE _lint_persona_categories_write / json.dump. Never raises — see the
    module comment above _DUALITY_BLOCK_RE for the additive/never-to-zero
    contract.
    """
    blueprint_path = PERSONAS_DIR / folder / "persona-blueprint.md"
    blueprint_text = blueprint_path.read_text(errors="ignore") if blueprint_path.exists() else ""
    parsed, err = _parse_duality_tags_block(blueprint_text)
    if err:
        print(f"[orchestrator] [PHASE 6 DUALITY-TAGS SKIPPED] {folder}: {err} "
              f"— entry registered WITHOUT audience/topic enrichment (core "
              f"domain/perspective routing unaffected).")
        if folder not in _DUALITY_TAG_WRITE_FAILURES:
            _DUALITY_TAG_WRITE_FAILURES.append(folder)
        return
    if not parsed:
        return  # no block present — pre-enrichment NO-OP, not a failure.

    candidate = dict(data["personas"][folder])
    for f in ("audiences", "topics", "voice_style", "usable_as"):
        if f in parsed:
            candidate[f] = parsed[f]
    gate_errors = _validate_duality_tags(folder, candidate, data)
    if gate_errors:
        print(f"[orchestrator] [PHASE 6 DUALITY-TAGS SKIPPED] {folder}: "
              f"persona_blend.validate_catalog_tags rejected the block:")
        for e in gate_errors:
            print(f"    ✗ {e}")
        print(f"[orchestrator] {folder} registered WITHOUT audience/topic "
              f"enrichment (core domain/perspective routing unaffected).")
        if folder not in _DUALITY_TAG_WRITE_FAILURES:
            _DUALITY_TAG_WRITE_FAILURES.append(folder)
        return

    for f in ("audiences", "topics", "voice_style", "usable_as"):
        if f in parsed:
            data["personas"][folder][f] = parsed[f]
    print(f"[orchestrator] {folder} enriched with duality tags "
          f"(audiences={len(parsed.get('audiences') or [])}, "
          f"topics={len(parsed.get('topics') or [])}, "
          f"usable_as={parsed.get('usable_as')}).")


def _append_persona_to_categories(book: dict, folder: str,
                                  appendix_status: str = None,
                                  domain_override: list = None,
                                  needs_retag: bool = False) -> None:
    """Append a new persona entry to persona-categories.json (idempotent).

    PRD 2.7: always writes to the canonical path returned by _persona_categories_path()
    (workspace/data/coaching-personas/persona-categories.json). The skill-folder copy
    is the shipped seed — if the canonical file is absent and the seed exists, the seed
    is COPIED to the canonical location rather than discarded.

    Schema 1.0: personas live under data["personas"][slug] with author, book,
    domain[], perspective[], custom[] fields. We write an empty-tags stub so
    that (a) the persona becomes visible to v2 selector's list_available_personas
    (b) the operator gets a clear "no tags yet" signal to fill in domain +
    perspective tags before the dept-scope filter will include this persona.

    P13-1 (FINAL-REVIEW-2026-07-01 Point 13 fix 1): also stamps
    `appendixStatus` (COMPLETE / COMPLETE_WITH_WARNINGS / FAILED / MISSING) so
    persona-selector-v2.py's appendix_completeness_bonus() can prefer a
    persona with a full-fidelity PLAYBOOK-APPENDIX.md for asset-heavy tasks.
    `appendix_status` should be the caller's pipeline-status.json
    `status[folder]["phase3b"]` value (process_book, Phase 6, already has
    `status` in scope) — falls back to a disk check when not supplied (e.g. a
    legacy/manual call path) so the field is never silently omitted.

    P13-2: before writing, every domain[]/perspective[] value on the new
    entry is run through the schema-lint gate (_lint_persona_categories_write)
    — a malformed append (wrong type, empty, not kebab-case) HARD FAILS,
    raising PersonaCategoriesSchemaError, and the file is never written.

    F1.4 (DEP-12): the AUTO-REPAIR path passes `domain_override` (e.g.
    PHASE6_SAFE_DEFAULT_DOMAIN) to BYPASS the auto-classifier and register the
    persona with a known-good controlled-vocab domain, and `needs_retag=True` to
    stamp an additive `needs_retag` marker on the entry so operator tooling can
    later re-classify it. This is never-to-zero applied to registration itself —
    a persona always gets a categories key (visible to the selector universe)
    even when auto-classification / the normal write path fails.
    """
    import shutil
    cat_path = _persona_categories_path()
    if not cat_path.exists():
        cat_path.parent.mkdir(parents=True, exist_ok=True)
        # Prefer to seed from the skill-folder copy so existing tags are preserved.
        skill_seed = Path(__file__).resolve().parents[1] / "persona-categories.json"
        if skill_seed.exists():
            shutil.copy2(skill_seed, cat_path)
            print(f"[orchestrator] Seeded {cat_path} from shipped skill-folder copy.")
        else:
            # No seed available — create a minimal v1.0 shell.
            data = {
                "schemaVersion": "1.0",
                "created": datetime.datetime.utcnow().strftime("%Y-%m-%d"),
                "domainTags": [],
                "perspectiveTags": [],
                "personas": {},
            }
            with open(cat_path, "w") as f:
                json.dump(data, f, indent=2)
        data = json.loads(cat_path.read_text())
        if "personas" not in data or not isinstance(data.get("personas"), dict):
            data["personas"] = {}
    else:
        with open(cat_path) as f:
            data = json.load(f)
        if "personas" not in data or not isinstance(data.get("personas"), dict):
            data["personas"] = {}

    if folder in data["personas"]:
        return  # Already present — idempotent no-op.

    if domain_override is not None:
        # F1.4 AUTO-REPAIR: skip the auto-classifier and register with a
        # known-good controlled-vocab domain. Guaranteed non-empty (the caller
        # passes PHASE6_SAFE_DEFAULT_DOMAIN); perspective is left empty (the
        # safe default makes no perspective claim).
        domain_tags, perspective_tags = list(domain_override), []
    else:
        # G6 FIX: auto-classify domain[]/perspective[] against the controlled vocab
        # so the persona is immediately routable. domain[] is guaranteed non-empty —
        # an empty domain is precisely what made prior auto-added personas invisible
        # to the dept-scope filter. autoTagged flags it for optional operator refining.
        domain_tags, perspective_tags = _auto_classify_persona_tags(
            folder, book,
            data.get("domainTags", []),
            data.get("perspectiveTags", []),
        )

    # P13-1: resolve the appendix-completeness field. Prefer the caller's
    # pipeline-status.json phase3b state (authoritative — the on-disk file's
    # own header never carries the real COMPLETE/COMPLETE_WITH_WARNINGS/FAILED
    # verdict, only a static "QC_PENDING" placeholder). Fall back to a plain
    # file-existence check for a caller that has no status dict in scope.
    appendix_path = PERSONAS_DIR / folder / "PLAYBOOK-APPENDIX.md"
    if appendix_status:
        resolved_appendix_status = appendix_status
    elif appendix_path.exists():
        resolved_appendix_status = "COMPLETE"
    else:
        resolved_appendix_status = "MISSING"

    data["personas"][folder] = {
        "author": book.get("author", "unknown"),
        "book": book.get("title", folder),
        "domain": domain_tags,
        "perspective": perspective_tags,
        "custom": [],
        "autoTagged": True,    # set by orchestrator auto-classifier; operator may refine
        "appendixStatus": resolved_appendix_status,  # P13-1: COMPLETE / COMPLETE_WITH_WARNINGS / FAILED / MISSING
        "added": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if needs_retag:
        # F1.4 additive marker: this entry got the SAFE-DEFAULT domain because
        # auto-classification / the normal write failed. It is registered (never
        # invisible) but its tags are a placeholder — operator/tooling must
        # re-classify. A workspace-only field (persona_fleet.py sync-categories
        # ships only the canonical seed fields, so it never leaks to the repo seed).
        data["personas"][folder]["needs_retag"] = True

    # D6 fix (ONB22-DUALITY-TAGS): OPTIONAL v1.3 audiences[]/topics[]/
    # voice_style{}/usable_as[] enrichment, parsed from the synthesis model's
    # '## Duality Tags' block and gated through persona_blend.validate_catalog_tags.
    # Additive + never-to-zero: absence or rejection never blocks the
    # domain/perspective registration above (see _register_duality_tags docstring).
    _register_duality_tags(folder, data)

    # P13-2: hard-fail schema-lint gate — raises PersonaCategoriesSchemaError
    # (naming the offending key) BEFORE any write if domain[]/perspective[]
    # is malformed. The file on disk is left untouched when this raises.
    _lint_persona_categories_write(data, folder)

    with open(cat_path, "w") as f:
        json.dump(data, f, indent=2)
    _kind = "safe-default (needs_retag)" if needs_retag else "auto-tagged"
    print(f"[orchestrator] Appended {folder} to {cat_path} "
          f"({_kind} domain={domain_tags} perspective={perspective_tags}; "
          f"appendixStatus={resolved_appendix_status}; operator may refine).")


def _phase6_register_categories(book: dict, folder: str,
                                appendix_status: str = None) -> str:
    """F1.4 (DEP-12) Phase-6 categories registration with FAIL-LOUD + AUTO-REPAIR.

    Attempts the normal (auto-classified) persona-categories.json append. On ANY
    failure it does NOT swallow the error into a warning (the pre-fix silent
    success that stranded a blueprint with no categories key — invisible to
    persona-selector-v2.py's list_available_personas() universe). Instead:

      1. AUTO-REPAIR (never-to-zero on registration): re-register the entry with
         the SAFE-DEFAULT tag set (PHASE6_SAFE_DEFAULT_DOMAIN) + needs_retag:true
         so the persona ALWAYS gets a categories key and stays selectable.
      2. FAIL-LOUD: record the folder in _CATEGORIES_WRITE_FAILURES so main()
         exits PHASE6_CATEGORIES_EXIT_CODE (never a silent success), whether or
         not the auto-repair itself succeeded.

    Idempotent: _append_persona_to_categories no-ops when the slug is already a
    key, so a repaired-then-rerun build is safe. Returns one of:
      "ok"       — normal auto-classified registration succeeded.
      "repaired" — normal path failed; safe-default entry written (needs_retag).
      "failed"   — normal path AND the safe-default auto-repair both failed;
                   the persona has no categories key on this box.
    """
    try:
        _append_persona_to_categories(book, folder, appendix_status=appendix_status)
        return "ok"
    except Exception as e:
        log(f"  [PHASE 6 FAILED] persona-categories.json write for {folder}: {e}")
        outcome = "failed"
        try:
            # never-to-zero: register with safe defaults rather than skip the
            # entry, so the persona is never invisible to the selector universe.
            _append_persona_to_categories(
                book, folder,
                appendix_status=appendix_status,
                domain_override=list(PHASE6_SAFE_DEFAULT_DOMAIN),
                needs_retag=True,
            )
            log(f"  [PHASE 6 AUTO-REPAIR] {folder} registered with safe-default "
                f"domain={PHASE6_SAFE_DEFAULT_DOMAIN} + needs_retag:true "
                f"(persona is selectable; operator must re-tag).")
            outcome = "repaired"
        except Exception as e2:
            log(f"  [PHASE 6 AUTO-REPAIR FAILED] {folder}: {e2} — persona has NO "
                f"categories key on this box; failing loud "
                f"(exit {PHASE6_CATEGORIES_EXIT_CODE}).")
        # FAIL-LOUD regardless of auto-repair outcome — a Phase-6 categories
        # write that needed repair is never reported as a clean success.
        if folder not in _CATEGORIES_WRITE_FAILURES:
            _CATEGORIES_WRITE_FAILURES.append(folder)
        return outcome


# ─── LOGGING ──────────────────────────────────────────────────────────────────
def log(msg):
    timestamp = datetime.datetime.now().strftime("%B %-d at %-I:%M %p")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ─── STATUS TRACKING ──────────────────────────────────────────────────────────
def load_status():
    status = {}
    if STATUS_FILE.exists():
        try:
            status = json.loads(STATUS_FILE.read_text())
        except Exception:
            status = {}

    for book in BOOKS:
        if book["folder"] not in status:
            status[book["folder"]] = {
                "title": book["title"],
                "author": book["author"],
                "phase1": "PENDING",
                "phase2": "PENDING",
                "phase3": "PENDING",
                "started": None,
                "completed": None,
                "errors": []
            }
    # Write only if the status dir exists (don't create dirs at module import time)
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2))
    return status

def save_status(status):
    STATUS_FILE.write_text(json.dumps(status, indent=2))

def mark_phase(status, folder, phase, state, error=None):
    status[folder][f"phase{phase}"] = state
    if error:
        status[folder]["errors"].append({"phase": phase, "error": error, "time": str(datetime.datetime.now())})
    save_status(status)

# ─── MULTI-FORMAT TEXT EXTRACTION ────────────────────────────────────────────
SUPPORTED_FORMATS = {
    ".pdf":  "PDF",
    ".epub": "EPUB",
    ".mobi": "MOBI",
    ".azw":  "Kindle AZW",
    ".azw3": "Kindle AZW3",
    ".kfx":  "Kindle KFX",
}

def extract_book_text(book_path: Path) -> str:
    """
    Unified text extraction for PDF, EPUB, MOBI, AZW, AZW3, KFX.

    Routes to the appropriate extractor based on file extension:
    - PDF: pdfplumber (fastest, most accurate for PDFs)
    - EPUB: ebooklib (pure Python, lightweight)
    - MOBI/AZW/AZW3/KFX: Calibre ebook-convert (converts to txt then reads)

    All paths return plain text string ready for LLM input.
    """
    ext = book_path.suffix.lower()
    fmt = SUPPORTED_FORMATS.get(ext)

    if not fmt:
        raise ValueError(
            f"Unsupported format: {ext}\n"
            f"Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        )

    if ext == ".pdf":
        return _extract_pdf(book_path)
    elif ext == ".epub":
        return _extract_epub(book_path)
    elif ext == ".mobi":
        # MOBI: try fast Python library first, fall back to Calibre+DeDRM
        return _extract_mobi_python(book_path)
    else:
        # AZW, AZW3, KFX - Calibre + DeDRM plugin handles all of these
        return _extract_via_calibre(book_path)


def _extract_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber (primary) or pypdf (fallback)."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text
        log("  Warning: pdfplumber returned empty text - trying pypdf fallback")
    except ImportError:
        log("  pdfplumber not installed, trying pypdf")
    except Exception as e:
        log(f"  pdfplumber error: {e} - trying pypdf fallback")

    try:
        import pypdf
        text = ""
        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text
    except ImportError:
        raise RuntimeError("Neither pdfplumber nor pypdf installed. Run: pip3 install pdfplumber")


def _extract_epub(epub_path: Path) -> str:
    """Extract text from EPUB using ebooklib."""
    try:
        from ebooklib import epub
        import html
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style'):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ('script', 'style'):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    self.text_parts.append(data)

        book = epub.read_epub(str(epub_path))
        text_parts = []

        for item in book.get_items():
            if item.get_type() == 9:  # ITEM_DOCUMENT
                parser = _TextExtractor()
                parser.feed(item.get_content().decode("utf-8", errors="ignore"))
                chunk = " ".join(parser.text_parts)
                if chunk.strip():
                    text_parts.append(chunk)

        return "\n\n".join(text_parts)

    except ImportError:
        log("  ebooklib not installed, falling back to Calibre for EPUB")
        return _extract_via_calibre(epub_path)


def _find_calibre() -> str:
    """Locate ebook-convert binary across common install paths. Auto-installs (Homebrew on Mac, apt-get on Linux) if missing. N26."""
    import subprocess
    import platform
    calibre_paths = [
        # Mac
        "/opt/homebrew/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        # Linux (VPS)
        "/usr/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/snap/bin/ebook-convert",
        "/opt/calibre/ebook-convert",
    ]
    for p in calibre_paths:
        if Path(p).exists():
            return p
    result = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    is_linux = platform.system() == "Linux"

    if is_linux:
        # Linux/VPS path: try apt-get first, then upstream installer fallback
        log("Calibre not found. Auto-installing on Linux via apt-get (this may take a few minutes)...")
        apt_get = None
        for p in ["/usr/bin/apt-get", "/usr/local/bin/apt-get"]:
            if Path(p).exists():
                apt_get = p
                break
        if apt_get:
            sudo_bin = "/usr/bin/sudo" if Path("/usr/bin/sudo").exists() else None
            update_cmd = ([sudo_bin] if sudo_bin else []) + [apt_get, "update", "-y"]
            install_cmd = ([sudo_bin] if sudo_bin else []) + [apt_get, "install", "-y", "calibre"]
            subprocess.run(update_cmd, capture_output=False)
            install_result = subprocess.run(install_cmd, capture_output=False)
            if install_result.returncode == 0:
                log("Calibre installed via apt-get. Continuing...")
                for p in calibre_paths:
                    if Path(p).exists():
                        return p
                result_post = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
                if result_post.returncode == 0 and result_post.stdout.strip():
                    return result_post.stdout.strip()

        # apt-get failed or unavailable — try upstream Calibre installer
        log("apt-get install failed or unavailable. Falling back to upstream Calibre installer...")
        installer_cmd = (
            'wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh '
            '| sh /dev/stdin install_dir=/opt isolated=y'
        )
        install_result2 = subprocess.run(installer_cmd, shell=True, capture_output=False)
        if install_result2.returncode == 0:
            log("Calibre installed via upstream installer. Continuing...")
            for p in calibre_paths:
                if Path(p).exists():
                    return p
            result_post2 = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
            if result_post2.returncode == 0 and result_post2.stdout.strip():
                return result_post2.stdout.strip()
        raise RuntimeError(
            "Calibre auto-install failed on Linux. Please install manually:\n"
            "  sudo apt-get install -y calibre\n"
            "  OR: wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sudo sh /dev/stdin"
        )

    # Mac path: auto-install via Homebrew
    log("Calibre not found. Auto-installing via Homebrew (this may take a few minutes)...")
    brew_paths = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
    brew_bin = None
    for bp in brew_paths:
        if Path(bp).exists():
            brew_bin = bp
            break
    if brew_bin is None:
        result2 = subprocess.run(["which", "brew"], capture_output=True, text=True)
        if result2.returncode == 0 and result2.stdout.strip():
            brew_bin = result2.stdout.strip()

    if brew_bin:
        install_result = subprocess.run(
            [brew_bin, "install", "--cask", "calibre"],
            capture_output=False,
        )
        if install_result.returncode == 0:
            log("Calibre installed successfully. Continuing...")
            for p in calibre_paths:
                if Path(p).exists():
                    return p
            result3 = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
            if result3.returncode == 0 and result3.stdout.strip():
                return result3.stdout.strip()
        else:
            raise RuntimeError("Calibre auto-install failed. Please install manually: brew install --cask calibre")
    else:
        raise RuntimeError(
            "Homebrew not found and Calibre is not installed.\n"
            "Install Homebrew first: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"\n"
            "Then run: brew install --cask calibre"
        )
    raise RuntimeError("Calibre install completed but ebook-convert binary still not found. Please restart Terminal and try again.")


def _extract_mobi_python(book_path: Path) -> str:
    """
    Extract MOBI text using the `mobi` Python library (fast, no Calibre needed).
    Works on DRM-free MOBI files. Falls back to Calibre if it fails.

    The mobi library extracts to an HTML file then we parse it to plain text.
    """
    try:
        import mobi
        import tempfile
        from html.parser import HTMLParser
        from bs4 import BeautifulSoup

        with tempfile.TemporaryDirectory() as tmpdir:
            # mobi.extract() returns (temp_dir, epub_path)
            extract_dir, epub_path = mobi.extract(str(book_path))
            # If it gave us an epub, read it via ebooklib
            if epub_path and Path(epub_path).exists():
                log("  MOBI extracted to EPUB via mobi library, parsing...")
                return _extract_epub(Path(epub_path))
            else:
                # Try to find any HTML files in the extract dir
                html_files = list(Path(extract_dir).rglob("*.html")) + list(Path(extract_dir).rglob("*.htm"))
                if html_files:
                    parts = []
                    for hf in sorted(html_files):
                        soup = BeautifulSoup(hf.read_text(errors="ignore"), "html.parser")
                        parts.append(soup.get_text(separator="\n"))
                    text = "\n\n".join(parts)
                    if text.strip():
                        log(f"  MOBI extracted via HTML parsing: {len(text):,} chars")
                        return text
    except Exception as e:
        log(f"  mobi Python library failed ({e}), falling back to Calibre")

    return _extract_via_calibre(book_path)


def _extract_via_calibre(book_path: Path) -> str:
    """
    Convert MOBI, AZW, AZW3, KFX (and EPUB fallback) to plain text using Calibre.

    With DeDRM plugin installed (v10.0.9), Calibre handles DRM-protected books
    from Amazon Kindle, Adobe Adept, Barnes & Noble, and Mobipocket.

    DRM removal is for personal use only (books you legally purchased and own).
    Calibre + DeDRM plugin installed at: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/drm-tools/

    Conversion chain: source format -> TXT via ebook-convert
    """
    import subprocess
    import tempfile

    calibre_bin = _find_calibre()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "output.txt"

        # ebook-convert with DRM plugin active handles protected files automatically
        # The DeDRM plugin intercepts during import - no extra flags needed
        cmd = [
            calibre_bin,
            str(book_path),
            str(out_path),
            "--txt-output-formatting=plain",  # plain is cleaner than markdown for LLM input
            "--keep-ligatures",               # preserve special chars
        ]

        log(f"  Converting {book_path.suffix.upper()} via Calibre + DeDRM...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # DRM removal can take longer
        )

        if result.returncode != 0:
            stderr = result.stderr[:500]
            # Check for common DRM error messages
            if "drm" in stderr.lower() or "decryption" in stderr.lower() or "protection" in stderr.lower():
                raise RuntimeError(
                    f"DRM removal failed for {book_path.name}.\n"
                    f"This book may use a DRM type not supported by DeDRM v10.0.9.\n"
                    f"For Kindle books: ensure the book was downloaded via Kindle for Mac.\n"
                    f"Calibre stderr: {stderr}"
                )
            raise RuntimeError(
                f"Calibre conversion failed (exit {result.returncode}):\n"
                f"stderr: {stderr}"
            )

        if not out_path.exists():
            raise RuntimeError(f"Calibre ran but output file not found: {out_path}")

        text = out_path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            raise RuntimeError(
                f"Calibre conversion produced empty output for {book_path.name}. "
                f"File may be DRM-protected and decryption failed silently."
            )

        log(f"  Calibre conversion complete: {len(text):,} characters extracted")
        return text


# ─── LEGACY ALIAS (keeps backward compat if anything calls extract_pdf_text) ──
def extract_pdf_text(pdf_path: Path) -> str:
    """Alias for backward compatibility. Use extract_book_text() for new code."""
    return _extract_pdf(pdf_path)


# ─── (OLD PDF-ONLY FALLBACK - kept for reference, replaced by _extract_pdf) ──
def _legacy_pypdf_fallback(pdf_path):
    try:
        import pypdf
        text = ""
        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except ImportError:
        pass
    raise RuntimeError("Neither pdfplumber nor pypdf is installed. Run: pip3 install pdfplumber")

# ─── CHUNKING LOGIC ───────────────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = MAX_CHUNK_SIZE, overlap: int = 2000) -> list:
    """
    Split large book text into overlapping chunks for Phase 2 analysis.
    Used for books exceeding CHUNK_THRESHOLD characters.
    Overlap ensures no methodology context is lost at chunk boundaries.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    total = len(text)

    while start < total:
        end = min(start + chunk_size, total)

        # Try to break at a paragraph boundary rather than mid-sentence
        if end < total:
            boundary = text.rfind("\n\n", start, end)
            if boundary > start + (chunk_size // 2):
                end = boundary

        chunk = text[start:end]
        chunks.append(chunk)
        log(f"    Chunk {len(chunks)}: chars {start:,} - {end:,} ({len(chunk):,} chars)")

        # Move forward with overlap so context carries between chunks
        start = end - overlap

    log(f"  Book chunked into {len(chunks)} segments")
    return chunks

# ─── API CALLS ────────────────────────────────────────────────────────────────

async def call_ollama_cloud(session: aiohttp.ClientSession, model: str, system: str, user: str, max_tokens: int = 16000) -> str:
    """
    Call the Ollama route for any ollama/* model.

    task-64 bug 3: the DEFAULT base is the LOCAL daemon
    (http://localhost:11434/api), authenticated by `ollama signin` — NO bearer
    key is sent or required; the daemon proxies `*:cloud` models to Ollama
    Cloud itself. A bearer key is only used (and then REQUIRED) when
    OLLAMA_BASE_URL points at a non-local base such as https://ollama.com/api.

    `model` arg must be an Ollama model id WITHOUT the "ollama/" prefix
    (e.g. "deepseek-v4-pro:cloud" not "ollama/deepseek-v4-pro:cloud").
    max_tokens is clamped to the model's real output ceiling (bug 4) — a
    request above it is a deterministic 400 on Ollama Cloud.
    """
    headers = {"Content-Type": "application/json"}
    if not OLLAMA_IS_LOCAL:
        if not OLLAMA_API_KEY:
            raise RuntimeError(
                "Non-local OLLAMA_BASE_URL configured but OLLAMA_API_KEY is not "
                "set — either unset OLLAMA_BASE_URL to use the signed-in local "
                "daemon, or set a REAL key (never validate it via /api/tags; "
                "that endpoint is public and returns 200 for any key)."
            )
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    max_tokens = _clamp_max_tokens(model, max_tokens)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": True,  # Trevor 2026-06-01: thinking ON (high) for DeepSeek V4 Pro reasoning
        "options": {
            "temperature": 1.0,
            "num_predict": max_tokens,
        },
    }

    _attempts = min(MAX_RETRIES, PROVIDER_MAX_RETRIES + 1)  # G1: hard retry cap
    for attempt in range(1, _attempts + 1):
        try:
            _storm_charge("ollama")  # G4: counts toward the global request budget
            async with session.post(
                f"{OLLAMA_BASE_URL}/chat",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=1800),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Ollama chat response shape: {"message": {"content": "..."}}
                    msg = data.get("message", {}) if isinstance(data, dict) else {}
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if content:
                        _storm_record("ollama", True)  # G3: healthy call
                        return content
                    log(f"  Ollama returned empty content (attempt {attempt}/{_attempts}); body preview: {json.dumps(data)[:200]}")
                else:
                    error_text = await response.text()
                    log(f"  Ollama error {response.status}: {error_text[:200]}")
                    if not _is_retryable_status(response.status):
                        # G1: non-transient (any 4xx incl. 401/402/403) — fail
                        # fast so the caller's OpenRouter fallback runs at once.
                        _storm_record("ollama", False, f"http_{response.status}")
                        raise _DeterministicHTTPError(
                            f"Ollama {response.status} (non-transient — not retrying): {error_text[:300]}")
                    _storm_record("ollama", False, f"http_{response.status}")
                if attempt < _attempts:
                    log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{_attempts})")
                    import asyncio as _asyncio
                    await _asyncio.sleep(RETRY_DELAY * attempt)
        except (_DeterministicHTTPError, _BuildAbort):
            raise
        except Exception as e:
            log(f"  Exception on attempt {attempt}: {e}")
            _storm_record("ollama", False, type(e).__name__)
            if attempt < _attempts:
                import asyncio as _asyncio
                await _asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"All {_attempts} attempts failed for {model} via Ollama ({OLLAMA_BASE_URL})")


async def call_moonshot(session: aiohttp.ClientSession, system: str, user: str) -> str:
    """
    DEPRECATED in v10.3.0. Kept for backward compatibility but no longer
    referenced by the routing chain. The selector chain now goes:
    Ollama Cloud → OpenRouter (same models) → OAuth GPT. Moonshot direct
    API is not in the chain.

    Calls Kimi K2.5 via Moonshot direct API (legacy path).
    """
    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "kimi-k2.6",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 1.0,
        "max_tokens": 16000
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.post(
                "https://api.moonshot.ai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=1800)  # v9.5.2: 30 min for heavy reasoning
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    log(f"  Moonshot error {response.status}: {error_text[:200]}")
                    if attempt < MAX_RETRIES:
                        log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
        except Exception as e:
            log(f"  Exception on attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
                import asyncio
                await asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError("All attempts failed for moonshot direct API")

async def call_openrouter(session: aiohttp.ClientSession, model: str, system: str, user: str, max_tokens: int = 16000) -> str:
    """Call Kimi K2.5 or DeepSeek V3.2-Speciale via OpenRouter."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://blackceo.com",
        "X-Title": "BlackCEO Coaching Personas Matrix"
    }
    # bug 4: clamp to the model's real output ceiling here too — the primary
    # OpenRouter fallback (deepseek/deepseek-v4-pro) shares the 65536 cap, and
    # no model in this pipeline's chain accepts the 120000 the synthesis phases
    # request (so an over-ask is a deterministic 400 on every route).
    max_tokens = _clamp_max_tokens(model, max_tokens)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "reasoning": {"effort": "high"}  # Trevor 2026-06-01: thinking HIGH (OpenRouter reasoning effort)
    }

    _attempts = min(MAX_RETRIES, PROVIDER_MAX_RETRIES + 1)  # G1: hard retry cap
    for attempt in range(1, _attempts + 1):
        try:
            _storm_charge("openrouter")  # G4: counts toward the global budget
            async with session.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=1800)  # v9.5.2: 30 min for heavy reasoning
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    if content is None:
                        # Some models return null content with reasoning_content
                        reasoning = data["choices"][0]["message"].get("reasoning_content", "")
                        if reasoning:
                            log(f"  Warning: content was null, using reasoning_content ({len(reasoning):,} chars)")
                            _storm_record("openrouter", True)
                            return reasoning
                        log(f"  Warning: content was null and no reasoning_content - retrying...")
                        if attempt < _attempts:
                            await asyncio.sleep(RETRY_DELAY * attempt)
                            continue
                        raise RuntimeError(f"API returned null content after {_attempts} attempts")
                    _storm_record("openrouter", True)  # G3: healthy call
                    return content
                else:
                    error_text = await response.text()
                    log(f"  OpenRouter error {response.status}: {error_text[:200]}")
                    if not _is_retryable_status(response.status):
                        # G1: non-transient (bad model id / auth / no credits /
                        # params) — retrying cannot succeed. Fail fast.
                        _storm_record("openrouter", False, f"http_{response.status}")
                        raise _DeterministicHTTPError(
                            f"OpenRouter {response.status} (non-transient — not retrying): {error_text[:300]}")
                    _storm_record("openrouter", False, f"http_{response.status}")
                    if attempt < _attempts:
                        log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{_attempts})")
                        await asyncio.sleep(RETRY_DELAY * attempt)
        except (_DeterministicHTTPError, _BuildAbort):
            raise
        except Exception as e:
            log(f"  Exception on attempt {attempt}: {e}")
            _storm_record("openrouter", False, type(e).__name__)
            if attempt < _attempts:
                await asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"All {_attempts} attempts failed for {model} via OpenRouter")


async def call_codex(session: aiohttp.ClientSession, user: str, max_tokens: int = 120000) -> str:
    """
    Call GPT-5.3 Codex via OpenAI Responses API (Trevor's OAuth subscription).
    Uses the direct OpenAI API key - NOT OpenRouter.
    Model: gpt-5.3-codex
    API: /v1/responses (required - Codex does not use /v1/chat/completions)
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_SYNTHESIS,       # gpt-5.3-codex
        "input": user,
        "max_output_tokens": max_tokens,
        "temperature": 1.0
    }

    max_tokens = _clamp_max_tokens(MODEL_SYNTHESIS, max_tokens)  # G5
    payload["max_output_tokens"] = max_tokens
    _attempts = min(MAX_RETRIES, PROVIDER_MAX_RETRIES + 1)  # G1: hard retry cap
    for attempt in range(1, _attempts + 1):
        try:
            _storm_charge("openai")  # G4: counts toward the global budget
            async with session.post(
                f"{OPENAI_BASE_URL}/responses",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=3600)  # v9.5.2: 60 min — heavy synthesis can run long on large books
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # OpenAI Responses API format
                    for item in data.get("output", []):
                        if item.get("type") == "message":
                            for content in item.get("content", []):
                                if content.get("type") == "output_text":
                                    _storm_record("openai", True)  # G3: healthy call
                                    return content["text"]
                    raise RuntimeError(f"Unexpected response format: {json.dumps(data)[:300]}")
                else:
                    error_text = await response.text()
                    log(f"  OpenAI Codex error {response.status}: {error_text[:200]}")
                    if not _is_retryable_status(response.status):
                        # G1: non-transient — fail fast (no fallback beyond Codex).
                        _storm_record("openai", False, f"http_{response.status}")
                        raise _DeterministicHTTPError(
                            f"OpenAI Codex {response.status} (non-transient — not retrying): {error_text[:300]}")
                    _storm_record("openai", False, f"http_{response.status}")
                    if attempt < _attempts:
                        log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{_attempts})")
                        await asyncio.sleep(RETRY_DELAY * attempt)
        except (_DeterministicHTTPError, _BuildAbort):
            raise
        except Exception as e:
            log(f"  Codex exception on attempt {attempt}: {e}")
            _storm_record("openai", False, type(e).__name__)
            if attempt < _attempts:
                await asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"All {_attempts} attempts failed for GPT-5.3 Codex")


# ─── G2: PREFLIGHT AUTH/CREDIT PROBE ──────────────────────────────────────────
async def _preflight_probe_one(session, provider: str, model: str):
    """ONE tiny probe call to a provider. Returns None on OK / transient blip,
    or a reason string on a DETERMINISTIC auth/credit/param failure (4xx) that
    would doom the whole build. Runs BEFORE the storm guard is armed, so it
    never charges the budget."""
    try:
        if provider == "ollama":
            await call_ollama_cloud(session, model, "ping", "ping", max_tokens=1)
        elif provider == "openrouter":
            await call_openrouter(session, model, "ping", "ping", max_tokens=1)
        elif provider == "openai":
            await call_codex(session, "ping", max_tokens=16)
        return None
    except _DeterministicHTTPError as e:
        # Auth (401/403) / credits (402) / bad params (400/422) — the build
        # cannot succeed. This is the abort trigger.
        return f"{provider}/{model}: {e}"
    except _BuildAbort:
        raise
    except Exception:
        # Transient (429/5xx/network) or a probe-shape quirk — do NOT block the
        # build on a blip; the real loop's guards still bound any storm.
        return None


async def preflight_providers(session, phase_models) -> None:
    """G2: before the build loop runs, probe each DISTINCT (provider, model) the
    build will use with ONE tiny call. A deterministic auth/credit/param failure
    ABORTS the entire build (raise _BuildAbort) before any phase/chunk loop is
    ever entered — so a dead key / no-credits box never enters the storm zone."""
    seen = set()
    problems = []
    for model_id in phase_models:
        if not model_id:
            continue
        route = _route_for(model_id)
        provider = {"ollama": "ollama",
                    "openrouter": "openrouter",
                    "openai-responses": "openai"}.get(route, "openrouter")
        if provider == "ollama":
            probe_model = model_id.replace("ollama/", "", 1)
        elif provider == "openrouter":
            probe_model = _openrouter_fallback_model(model_id)
        else:
            probe_model = model_id
        key = (provider, probe_model)
        if key in seen:
            continue
        seen.add(key)
        log(f"  [preflight] probing {provider} / {probe_model} …")
        reason = await _preflight_probe_one(session, provider, probe_model)
        if reason:
            problems.append(reason)
    if problems:
        raise _BuildAbort(
            "PREFLIGHT FAILED — aborting build before any phase runs "
            "(fix auth/credits/params, then re-run):\n  - " + "\n  - ".join(problems))
    log("  [preflight] all providers reachable — proceeding")


# ─── LOAD PROMPTS ─────────────────────────────────────────────────────────────
def load_prompt(filename: str) -> str:
    """Load a prompt file. Searches PROMPTS_DIR and fallback locations."""
    candidates = [PROMPTS_DIR / filename]
    # Additional search paths: skill folder agent-prompts/, legacy location
    skill_dir = Path(__file__).parent.parent
    candidates.append(skill_dir / "agent-prompts" / filename)
    for path in candidates:
        if path.exists():
            return path.read_text()
    raise FileNotFoundError(
        f"Prompt file not found: {filename}\n"
        f"Searched: {[str(c) for c in candidates]}"
    )

# Lazy-loaded — evaluated when first used, not at import time.
# This allows `--single-book` to run even if the agent-prompts dir is temporarily
# unavailable (the orchestrator errors with a clear message at the right callsite).
_PROMPT_CACHE: dict = {}

def _get_prompt(filename: str) -> str:
    if filename not in _PROMPT_CACHE:
        _PROMPT_CACHE[filename] = load_prompt(filename)
    return _PROMPT_CACHE[filename]

def _extraction_system() -> str:  return _get_prompt("extraction-agent-prompt.md")
def _analysis_system()   -> str:  return _get_prompt("analysis-agent-prompt.md")
def _appendix_system()   -> str:  return _get_prompt("playbook-appendix-prompt.md")  # Phase 3b


def _synthesis_system() -> str:
    """Phase-3 synthesis system prompt, dynamically extended (D6 fix,
    ONB22-DUALITY-TAGS) with the LIVE controlled audienceTags[]/topicTags[]
    vocabulary read fresh from the canonical persona-categories.json.

    WHY dynamic (not baked into the static template): persona_blend's
    validate_catalog_tags rejects an audiences[]/topics[] tag that is not
    already a member of the vocab when that vocab is non-empty — unlike
    domain[]/perspective[], there is no auto-extend allowance (by design; see
    persona_fleet.py _validate_entry). So the model can only land clean
    'vocab-first' duality tags (per agent-prompts/synthesis-agent-prompt.md) if
    it actually SEES the real vocab at synthesis time. Deliberately NOT cached
    in _PROMPT_CACHE (that cache is keyed by static filename) — the vocab can
    grow between books in a batch run; each call re-reads the small JSON file.

    Absent file / empty vocab (a pre-enrichment 1.2 catalog, or first-ever run)
    omits the vocab block entirely — the template's own instructions then tell
    the model to leave audiences[]/topics[] empty rather than invent tags with
    nothing to ground them, so schema-1.2 boxes behave exactly as before this
    fix (matches persona_blend.py's own pre-enrichment NO-OP semantics).
    """
    template = _get_prompt("synthesis-agent-prompt.md")
    try:
        cat_path = _persona_categories_path()
        if cat_path.exists():
            cat = json.loads(cat_path.read_text())
            aud = sorted(set(cat.get("audienceTags") or []))
            top = sorted(set(cat.get("topicTags") or []))
            if aud or top:
                template = template + (
                    "\n\n## Duality Tags — Current Controlled Vocabulary (LIVE, read-only)\n\n"
                    "Choose `audiences[]` and `topics[]` for the Duality Tags block ONLY "
                    "from the tags below (vocab-first — persona_blend.validate_catalog_tags "
                    "rejects anything else; leave a list EMPTY rather than inventing a new "
                    "tag not shown here):\n\n"
                    f"audienceTags ({len(aud)}): {', '.join(aud)}\n\n"
                    f"topicTags ({len(top)}): {', '.join(top)}\n"
                )
    except Exception:
        # Best-effort — a vocab-injection failure must never block Phase 3 itself.
        pass
    return template

# ─── PHASE 1 - EXTRACTION ─────────────────────────────────────────────────────
async def run_extraction(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    output_path = PERSONAS_DIR / folder / "extraction-notes.md"
    (PERSONAS_DIR / folder).mkdir(parents=True, exist_ok=True)

    log(f"[PHASE 1] Starting extraction: {book['title']}")
    mark_phase(status, folder, 1, "IN_PROGRESS")

    try:
        # v6.6.0: Check for pre-extracted text FIRST (YouTube/video/text sources
        # write their transcript to a text file via add-persona-from-source.sh
        # before calling the orchestrator; we must consume it here, not re-invoke
        # whisper).  Two possible locations:
        #   a) book["_text_file"] — stashed by _build_book_from_source_json()
        #   b) BASE/text/<slug>.txt — the canonical location written by the script
        text = ""
        _pre_text_path = None
        if book.get("_text_file") and Path(book["_text_file"]).exists():
            _pre_text_path = Path(book["_text_file"])
        else:
            for _candidate in [
                BASE / "text" / f"{folder}.txt",
                PERSONAS_DIR / folder / "text" / f"{folder}.txt",
            ]:
                if _candidate.exists() and _candidate.stat().st_size > 0:
                    _pre_text_path = _candidate
                    break

        if _pre_text_path:
            text = _pre_text_path.read_text(encoding="utf-8", errors="ignore")
            log(f"  Using pre-extracted text ({_pre_text_path}): {len(text):,} chars")
        else:
            # Standard book extraction path: resolve file → extract text
            book_file = book["file"]
            book_path = BOOKS_DIR / book_file
            if not book_path.exists():
                # Try finding the book in any supported format
                stem = Path(book_file).stem
                found = None
                for ext in SUPPORTED_FORMATS.keys():
                    candidate = BOOKS_DIR / (stem + ext)
                    if candidate.exists():
                        found = candidate
                        break
                if found:
                    book_path = found
                    log(f"  Note: Using {found.name} (original file not found)")
                else:
                    log(f"  [PHASE 1 FAILED] {book['title']}: Book file not found: {book_path}")
                    mark_phase(status, folder, 1, "FAILED", f"File not found: {book_file}")
                    return False

            fmt = SUPPORTED_FORMATS.get(book_path.suffix.lower(), "UNKNOWN")
            text = extract_book_text(book_path)
            log(f"  {fmt} extracted: {len(text):,} characters")

        if not text.strip():
            log(f"  [PHASE 1 FAILED] {book['title']}: text extraction produced empty result")
            mark_phase(status, folder, 1, "FAILED", "Empty text after extraction")
            return False

        # v9.5.1: re-resolve model PER BOOK based on its actual char count.
        # Books > 800K chars switch from Kimi (262K ctx) to DeepSeek V4-pro (1M ctx).
        # Books > 3M chars get DeepSeek-only.
        per_book_model, per_book_route = resolve_phase_model("phase1", input_chars=len(text))
        log(f"  Model for this book (Phase 1, {len(text):,} chars): {per_book_model} via {per_book_route}")

        # If the resolved model is DeepSeek-pro (1M ctx) we can pass the full text.
        # Otherwise truncate to leave room for the system prompt (Kimi: 262K tokens ≈ 900K chars cap).
        max_chars = 3_500_000 if "deepseek-v" in per_book_model and "pro" in per_book_model else 900_000

        user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Here is the complete book text. Extract all 20 items as specified in your instructions.

---

{text[:max_chars]}"""

        # v10.3.0: Route the call based on the resolved model. Priority is
        # Ollama Cloud first (cheap subscription), OpenRouter same-model
        # fallback second, OAuth GPT third. Moonshot direct API is no longer
        # in the routing chain (Kimi 2.6 + DeepSeek V4-pro both available
        # via Ollama Cloud and OpenRouter — no need for the direct route).
        _ext_sys = _extraction_system()
        if folder in OPENROUTER_FALLBACK_FOLDERS:
            log(f"  Using OpenRouter fallback for {book['title']} (content filter)")
            or_model = _openrouter_fallback_model(per_book_model)
            result = await call_openrouter(session, or_model, _ext_sys, user_prompt, max_tokens=16000)
        elif per_book_route == "ollama":
            # PRIMARY route — strip the "ollama/" prefix and call Ollama Cloud
            ollama_model = per_book_model.replace("ollama/", "", 1)
            try:
                result = await call_ollama_cloud(session, ollama_model, _ext_sys, user_prompt, max_tokens=16000)
            except Exception as e:
                # Ollama Cloud failed — fall back to OpenRouter same model
                log(f"  Ollama Cloud call failed ({e}); falling back to OpenRouter same model")
                fallback_model = _openrouter_fallback_model(per_book_model)
                result = await call_openrouter(session, fallback_model, _ext_sys, user_prompt, max_tokens=16000)
        elif per_book_route == "openrouter":
            or_model = per_book_model.replace("openrouter/", "", 1)
            result = await call_openrouter(session, or_model, _ext_sys, user_prompt, max_tokens=16000)
        elif per_book_route == "openai-responses":
            # OAuth GPT — uses existing OpenAI client path
            if "call_openai_responses" in globals():
                result = await call_openai_responses(session, per_book_model, _ext_sys, user_prompt, max_tokens=16000)
            else:
                result = await call_codex(session, user_prompt, max_tokens=16000)
        else:
            # Unknown route — try OpenRouter as a safe default
            log(f"  WARN: unknown route '{per_book_route}' for model {per_book_model}; trying OpenRouter")
            or_model = _openrouter_fallback_model(per_book_model)
            result = await call_openrouter(session, or_model, _ext_sys, user_prompt, max_tokens=16000)

        header = f"# EXTRACTION NOTES - {book['title']}\n**Author:** {book['author']}\n**Extracted:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}\n**Model:** {MODEL_EXTRACTION}\n\n---\n\n"
        output_path.write_text(header + result)

        log(f"  [PHASE 1 COMPLETE] {book['title']} - {len(result):,} chars saved")
        mark_phase(status, folder, 1, "COMPLETE")
        return True

    except Exception as e:
        log(f"  [PHASE 1 FAILED] {book['title']}: {e}")
        mark_phase(status, folder, 1, "FAILED", str(e))
        return False

# ─── PHASE 2 - ANALYSIS ───────────────────────────────────────────────────────
async def run_analysis(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    extraction_path = PERSONAS_DIR / folder / "extraction-notes.md"
    output_path = PERSONAS_DIR / folder / "analysis-notes.md"

    log(f"[PHASE 2] Starting analysis: {book['title']}")
    mark_phase(status, folder, 2, "IN_PROGRESS")

    try:
        extraction_text = extraction_path.read_text()
        log(f"  Extraction notes: {len(extraction_text):,} chars")

        # CHUNKING LOGIC - DeepSeek V3.2-Speciale has 163K context
        # Extraction notes for large books may exceed safe limit
        DEEPSEEK_SAFE_LIMIT = 120000  # Leave room for system prompt + output

        if len(extraction_text) > DEEPSEEK_SAFE_LIMIT:
            log(f"  Large extraction ({len(extraction_text):,} chars) - chunking for analysis")
            chunks = chunk_text(extraction_text, chunk_size=DEEPSEEK_SAFE_LIMIT, overlap=3000)

            # Run analysis on each chunk, then synthesize chunk analyses
            chunk_analyses = []
            for i, chunk in enumerate(chunks, 1):
                log(f"  Analyzing chunk {i}/{len(chunks)}...")
                user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}
CHUNK: {i} of {len(chunks)}

Analyze this portion of the extraction notes across all 12 analytical dimensions.
Note this is chunk {i} of {len(chunks)} - focus on the material present in this chunk.
A final synthesis pass will combine all chunk analyses.

---

{chunk}"""
                # v9.6.2: resolve model per chunk based on chunk size, route accordingly
                # G6 FIX (HIGH, data loss): the model-call + append BELOW were
                # dedented OUTSIDE this for-loop, so for any book whose extraction
                # notes exceeded the chunk limit only the LAST chunk was ever
                # analyzed and every earlier chunk was silently dropped. Re-indented
                # back INSIDE the loop so EVERY chunk is analyzed and concatenated.
                per_chunk_model, per_chunk_route = resolve_phase_model("phase2", input_chars=len(chunk))
                log(f"    Model for chunk {i}: {per_chunk_model} via {per_chunk_route}")
                _ana_sys = _analysis_system()
                if per_chunk_route == "openai-responses":
                    if "call_openai_responses" in globals():
                        chunk_result = await call_openai_responses(session, per_chunk_model, _ana_sys, user_prompt, max_tokens=16000)
                    else:
                        chunk_result = await call_codex(session, user_prompt, max_tokens=16000)
                elif per_chunk_route == "ollama":
                    # v10.3.0: Ollama Cloud is now a real route
                    ollama_model = per_chunk_model.replace("ollama/", "", 1)
                    try:
                        chunk_result = await call_ollama_cloud(session, ollama_model, _ana_sys, user_prompt, max_tokens=16000)
                    except Exception as e:
                        log(f"    Ollama Cloud chunk call failed ({e}); falling back to OpenRouter")
                        fallback_model = _openrouter_fallback_model(per_chunk_model)
                        chunk_result = await call_openrouter(session, fallback_model, _ana_sys, user_prompt, max_tokens=16000)
                else:
                    or_model = per_chunk_model.replace("openrouter/", "", 1)
                    chunk_result = await call_openrouter(session, or_model, _ana_sys, user_prompt, max_tokens=16000)
                chunk_analyses.append(f"## CHUNK {i} ANALYSIS\n\n{chunk_result}")
                await asyncio.sleep(2)  # Brief pause between chunks

            # Final synthesis of all chunk analyses
            log(f"  Synthesizing {len(chunks)} chunk analyses into unified analysis...")
            synthesis_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Below are analyses from {len(chunks)} chunks of this book's extraction notes.
Synthesize them into one complete, unified analysis across all 12 analytical dimensions.
Resolve any inconsistencies. Fill gaps by inferring from context.
Produce the final structured analysis document.

---

{''.join(chunk_analyses)}"""

            # v9.6.2: resolve model for the synthesis pass — uses combined size of all chunk analyses
            combined_size = sum(len(ca) for ca in chunk_analyses)
            synth_model, synth_route = resolve_phase_model("phase2", input_chars=combined_size)
            log(f"  Synthesis model: {synth_model} via {synth_route}")
            _ana_sys2 = _analysis_system()
            if synth_route == "openai-responses":
                if "call_openai_responses" in globals():
                    result = await call_openai_responses(session, synth_model, _ana_sys2, synthesis_prompt, max_tokens=16000)
                else:
                    result = await call_codex(session, synthesis_prompt, max_tokens=16000)
            elif synth_route == "ollama":
                # v10.3.0: Ollama Cloud is now a real route
                ollama_model = synth_model.replace("ollama/", "", 1)
                try:
                    result = await call_ollama_cloud(session, ollama_model, _ana_sys2, synthesis_prompt, max_tokens=16000)
                except Exception as e:
                    log(f"  Ollama Cloud synthesis call failed ({e}); falling back to OpenRouter")
                    fallback_model = _openrouter_fallback_model(synth_model)
                    result = await call_openrouter(session, fallback_model, _ana_sys2, synthesis_prompt, max_tokens=16000)
            else:
                or_model = synth_model.replace("openrouter/", "", 1)
                result = await call_openrouter(session, or_model, _ana_sys2, synthesis_prompt, max_tokens=16000)

        else:
            user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Here are the complete extraction notes from Phase 1.
Analyze across all 12 analytical dimensions as specified.

---

{extraction_text}"""

            # v9.6.2: resolve model per book size
            single_model, single_route = resolve_phase_model("phase2", input_chars=len(extraction_text))
            log(f"  Single-pass model: {single_model} via {single_route}")
            _ana_sys3 = _analysis_system()
            if single_route == "openai-responses":
                if "call_openai_responses" in globals():
                    result = await call_openai_responses(session, single_model, _ana_sys3, user_prompt, max_tokens=16000)
                else:
                    result = await call_codex(session, user_prompt, max_tokens=16000)
            elif single_route == "ollama":
                # v10.3.0: Ollama Cloud is now a real route
                ollama_model = single_model.replace("ollama/", "", 1)
                try:
                    result = await call_ollama_cloud(session, ollama_model, _ana_sys3, user_prompt, max_tokens=16000)
                except Exception as e:
                    log(f"  Ollama Cloud single-pass call failed ({e}); falling back to OpenRouter")
                    fallback_model = _openrouter_fallback_model(single_model)
                    result = await call_openrouter(session, fallback_model, _ana_sys3, user_prompt, max_tokens=16000)
            else:
                or_model = single_model.replace("openrouter/", "", 1)
                result = await call_openrouter(session, or_model, _ana_sys3, user_prompt, max_tokens=16000)

        header = f"# ANALYSIS NOTES - {book['title']}\n**Author:** {book['author']}\n**Analyzed:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}\n**Model:** {MODEL_ANALYSIS}\n\n---\n\n"
        output_path.write_text(header + result)

        log(f"  [PHASE 2 COMPLETE] {book['title']} - {len(result):,} chars saved")
        mark_phase(status, folder, 2, "COMPLETE")
        return True

    except Exception as e:
        log(f"  [PHASE 2 FAILED] {book['title']}: {e}")
        mark_phase(status, folder, 2, "FAILED", str(e))
        return False

# ─── PHASE 3b - PLAYBOOK APPENDIX ─────────────────────────────────────────────
def _validate_appendix(text: str):
    """Validate a PLAYBOOK-APPENDIX.md draft against the quality floor.

    Returns (ok, hard_reasons, soft_warnings).
      - ok=False (hard_reasons non-empty): STRUCTURE/HONESTY gate failed →
        Phase 3b is marked FAILED (fail-loud; no false success).
      - soft_warnings: richness/length below target. Logged, not fatal — a
        genuinely thin (non-commercial) book legitimately has fewer assets and
        marks them ABSENT in the Coverage Map rather than fabricating.
    """
    if not text or not text.strip():
        return False, ["empty output"], []
    n = len(text)
    reasons, warnings = [], []

    missing = [s for s in APPENDIX_REQUIRED_SECTIONS if s not in text]
    if missing:
        reasons.append(f"missing section headers {missing}")
    if "Coverage Map" not in text and "Source Richness" not in text:
        reasons.append("missing Asset Coverage Map (Section H) — required honesty ledger")
    if n < APPENDIX_HARD_MIN_CHARS:
        reasons.append(f"too short: {n:,} < {APPENDIX_HARD_MIN_CHARS:,} hard min chars")

    low = text.lower()
    pat = low.count("pattern:")
    ex = low.count("worked example:")
    if pat < APPENDIX_MIN_PATTERN_BLOCKS:
        warnings.append(f"only {pat} Pattern: blocks (target >= {APPENDIX_MIN_PATTERN_BLOCKS})")
    if ex < APPENDIX_MIN_EXAMPLE_BLOCKS:
        warnings.append(f"only {ex} 'Worked example:' blocks (target >= {APPENDIX_MIN_EXAMPLE_BLOCKS})")
    if n < APPENDIX_SOFT_MIN_CHARS:
        warnings.append(f"length {n:,} < {APPENDIX_SOFT_MIN_CHARS:,} soft target "
                        f"(acceptable ONLY if the Coverage Map marks the source THIN/ABSENT)")

    return (len(reasons) == 0), reasons, warnings


async def _appendix_model_call(session: aiohttp.ClientSession, system_prompt: str, user_prompt: str) -> str:
    """Route a Phase 3b appendix call through the same selector chain as Phase 3
    synthesis (Ollama-Cloud-first, OpenRouter same-model fallback, OAuth GPT)."""
    input_size = len(system_prompt) + len(user_prompt)
    model, route = resolve_phase_model("phase3", input_chars=input_size)
    log(f"  Phase 3b appendix model: {model} via {route} (input ~{input_size:,} chars)")
    if route == "openai-responses":
        full_input = f"{system_prompt}\n\n---\n\n{user_prompt}"
        return await call_codex(session, full_input, max_tokens=120000)
    elif route == "ollama":
        ollama_model = model.replace("ollama/", "", 1)
        try:
            return await call_ollama_cloud(session, ollama_model, system_prompt, user_prompt, max_tokens=120000)
        except Exception as e:
            log(f"  Ollama Cloud appendix call failed ({e}); falling back to OpenRouter same model")
            fallback_model = _openrouter_fallback_model(model)
            return await call_openrouter(session, fallback_model, system_prompt, user_prompt, max_tokens=120000)
    else:
        or_model = model.replace("openrouter/", "", 1)
        return await call_openrouter(session, or_model, system_prompt, user_prompt, max_tokens=120000)


async def run_playbook_appendix(session: aiohttp.ClientSession, book: dict, status: dict,
                                extraction_text: str, analysis_text: str) -> bool:
    """Phase 3b: emit PLAYBOOK-APPENDIX.md alongside persona-blueprint.md.

    Preserves the book's reusable copy/funnel assets at full fidelity (headline/
    hook/subject formulas, page-by-page funnel recipes + sequences, sales/
    objection/follow-up/email scripts, frameworks/templates with steps, brand-
    voice language patterns, verbatim swipe file). Enforces the quality floor;
    one stricter retry if the floor/targets are missed; fail-loud on the hard gate.
    """
    folder = book["folder"]
    appendix_path = PERSONAS_DIR / folder / "PLAYBOOK-APPENDIX.md"
    (PERSONAS_DIR / folder).mkdir(parents=True, exist_ok=True)

    log(f"[PHASE 3b] Building playbook appendix: {book['title']}")
    mark_phase(status, folder, "3b", "IN_PROGRESS")

    try:
        appendix_sys = _appendix_system()
        base_user = f"""BOOK: {book['title']}
AUTHOR: {book['author']}
PERSONA FOLDER: {folder}

Build the complete PLAYBOOK-APPENDIX.md (sections A-H) from the inputs below.
Preserve every reusable asset at FULL fidelity using the Pattern / Worked example /
Source capture convention. Never fabricate — mark a category ABSENT IN SOURCE (and
record it in the Coverage Map) where the book is genuinely thin.

---

## PHASE 1 EXTRACTION NOTES (focus: items 21-30, the Playbook Asset Lens)
{extraction_text[:90000]}

---

## PHASE 2 ANALYSIS NOTES (focus: Dimension 13, Patternized Asset Catalog)
{analysis_text[:60000]}
"""

        best = ""
        last_reasons, last_warnings = [], []
        for attempt in range(APPENDIX_MAX_RETRIES + 1):
            user_prompt = base_user
            if attempt > 0:
                shortfalls = "; ".join((last_reasons or []) + (last_warnings or [])) or "below richness target"
                user_prompt = base_user + f"""

---

RETRY: your previous draft fell short of the quality floor ({shortfalls}).
WITHOUT fabricating anything, expand it: pull MORE of the book's real formulas,
scripts, page recipes, and swipe examples out of the extraction notes; ensure ALL
sections A-H are present with the Coverage Map; and give every asset BOTH a
'Pattern:' and a 'Worked example:' field. If a category truly has no source
material, keep it ABSENT IN SOURCE rather than inventing.
"""
            result = await _appendix_model_call(session, appendix_sys, user_prompt)
            if result and len(result) > len(best):
                best = result
            ok, last_reasons, last_warnings = _validate_appendix(best)
            if ok and not last_warnings:
                break  # clean pass — no retry needed
            if attempt >= APPENDIX_MAX_RETRIES:
                break  # out of retries — keep best draft, report below

        header = f"""# PLAYBOOK APPENDIX - {book['title']}
**Source Book:** {book['title']} by {book['author']}
**Companion To:** persona-blueprint.md
**Version:** 1.0.0
**Built:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}
**Purpose:** Full-fidelity reusable copy/funnel asset library (depth preservation — swipe-ready)
**QC Status:** QC_PENDING

---

"""
        appendix_path.write_text(header + best)

        ok, reasons, warnings = _validate_appendix(best)
        for w in warnings:
            log(f"  [PHASE 3b WARN] {book['title']}: {w}")
        if ok:
            state = "COMPLETE" if not warnings else "COMPLETE_WITH_WARNINGS"
            mark_phase(status, folder, "3b", state)
            log(f"  [PHASE 3b {state}] {book['title']} - {len(best):,} chars; appendix saved")
            return True
        else:
            # FAIL LOUD — do not pretend the appendix is good. The blueprint is
            # still valid; the appendix is marked FAILED for converge/QC to retry.
            log(f"  [PHASE 3b FAILED] {book['title']}: hard floor not met: {reasons}")
            mark_phase(status, folder, "3b", "FAILED", "; ".join(reasons))
            return False

    except Exception as e:
        log(f"  [PHASE 3b FAILED] {book['title']}: {e}")
        mark_phase(status, folder, "3b", "FAILED", str(e))
        return False


# ─── PHASE 3 - SYNTHESIS ──────────────────────────────────────────────────────
async def run_synthesis(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    extraction_path = PERSONAS_DIR / folder / "extraction-notes.md"
    analysis_path = PERSONAS_DIR / folder / "analysis-notes.md"
    blueprint_path = PERSONAS_DIR / folder / "persona-blueprint.md"

    # F1.2 (FDN-5): re-entrancy for an idempotent retry. If the blueprint was
    # already synthesized on a prior run (phase3 COMPLETE) but a LATER phase
    # (notably Phase 5 embedding) FAILED, a retry must NOT re-run the costly LLM
    # synthesis — it must RE-EMBED ONLY. Detect that here and skip straight to
    # the Phase 3b / Phase 5 / Phase 6 tail with the on-disk blueprint intact.
    _phase3_already = (
        status.get(folder, {}).get("phase3") == "COMPLETE"
        and blueprint_path.exists()
    )
    if _phase3_already:
        log(f"[PHASE 3] Blueprint already COMPLETE for {folder} — skipping "
            f"synthesis; re-entering to re-embed (Phase 5) only.")
    else:
        log(f"[PHASE 3] Starting synthesis: {book['title']}")
        mark_phase(status, folder, 3, "IN_PROGRESS")

    try:
        extraction_text = extraction_path.read_text()
        analysis_text = analysis_path.read_text()

        if not _phase3_already:
            # Read the SKILL.md spec to include in synthesis prompt
            # v6.6.0: look in the skill folder, not PROJECT_DIR (which is now BASE)
            skill_path_candidates = [
                Path(__file__).parent.parent / "SKILL.md",
                BASE / "SKILL.md",
            ]
            skill_spec = ""
            for sp in skill_path_candidates:
                if sp.exists():
                    skill_spec = sp.read_text()
                    break

            user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}
PERSONA FOLDER: {folder}

You have the extraction notes (Phase 1) and deep analysis (Phase 2) below.
Build the complete 14-section dual-purpose persona blueprint as specified.

The output file must be saved to:
{PERSONAS_DIR}/{folder}/persona-blueprint.md

---

## PHASE 1 EXTRACTION NOTES
{extraction_text[:60000]}

---

## PHASE 2 ANALYSIS NOTES
{analysis_text[:60000]}

---

## SKILL.md BLUEPRINT SPECIFICATION
{skill_spec[:30000]}

---

Now write the complete persona blueprint. All 14 sections. Zero placeholders.
Both Coaching Framework (Section 3) and Agent Governance Framework (Section 4) fully built.
At the end, rate your output on the 6 dimensions specified in your instructions."""

            # v9.6.2: Phase 3 model resolved per book via heavy-tier selector.
            # Synthesis input combines all extraction + analysis notes — can be large.
            phase3_input_size = len(user_prompt)
            phase3_model, phase3_route = resolve_phase_model("phase3", input_chars=phase3_input_size)
            log(f"  Phase 3 synthesis model: {phase3_model} via {phase3_route} (input ~{phase3_input_size:,} chars)")

            _syn_sys = _synthesis_system()
            full_input = f"{_syn_sys}\n\n---\n\n{user_prompt}"
            if phase3_route == "openai-responses":
                # OAuth GPT route — preferred for Phase 3 synthesis (no per-call cost)
                result = await call_codex(session, full_input, max_tokens=120000)
            elif phase3_route == "ollama":
                # v10.3.0: Ollama Cloud is now a real route — call it directly
                ollama_model = phase3_model.replace("ollama/", "", 1)
                try:
                    result = await call_ollama_cloud(session, ollama_model, _syn_sys, user_prompt, max_tokens=120000)
                except Exception as e:
                    log(f"  Ollama Cloud call failed ({e}); falling back to OpenRouter same model")
                    fallback_model = _openrouter_fallback_model(phase3_model)
                    result = await call_openrouter(session, fallback_model, _syn_sys, user_prompt, max_tokens=120000)
            else:
                # OpenRouter route (e.g. OpenRouter Kimi / OpenRouter DeepSeek-pro)
                or_model = phase3_model.replace("openrouter/", "", 1)
                result = await call_openrouter(session, or_model, _syn_sys, user_prompt, max_tokens=120000)

            header = f"""# PERSONA BLUEPRINT - {book['title']}
**Source Book:** {book['title']} by {book['author']}
**Version:** 1.0.0
**Built:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}
**Gemini Index:** {folder}
**Index Location:** ./qmd-index/
**Coaching Mode:** BUILT
**Task Mode:** BUILT
**QC Status:** QC_PENDING

---

"""
            blueprint_path.write_text(header + result)

            log(f"  [PHASE 3 COMPLETE] {book['title']} - {len(result):,} chars saved")
            mark_phase(status, folder, 3, "COMPLETE")
            status[folder]["completed"] = datetime.datetime.now().strftime('%B %-d at %-I:%M %p')
            save_status(status)

        # Phase 3b: emit PLAYBOOK-APPENDIX.md alongside the blueprint. This is the
        # depth-preservation half of the pipeline — it keeps the book's actual
        # reusable copy/funnel assets (formulas, scripts, page recipes, swipe file,
        # brand-voice patterns) at full fidelity so copy specialists write rich,
        # brand-building copy instead of the over-concise output the distilled
        # blueprint alone produced. Reuses the extraction + analysis text already
        # loaded above. Runs BEFORE Phase 5 so the appendix is present when the
        # Gemini indexer scans the persona folder. Non-fatal to Phase 3: a missed
        # appendix floor is marked FAILED (fail-loud) but the blueprint still ships.
        _p3b = status.get(folder, {}).get("phase3b")
        if _phase3_already and _p3b in ("COMPLETE", "COMPLETE_WITH_WARNINGS", "DONE"):
            log(f"  Phase 3b already {_p3b} for {folder} — skipping appendix "
                f"regen on re-embed-only re-entry.")
        else:
            try:
                await run_playbook_appendix(session, book, status, extraction_text, analysis_text)
            except Exception as e:
                log(f"  Warning: Phase 3b (playbook appendix) failed for {folder}: {e}")
                mark_phase(status, folder, "3b", "FAILED", str(e))

        # Phase 5: Auto re-index persona in Gemini Engine.
        # Pre-v10.14.27 hardcoded the legacy ~/clawd/scripts/gemini-indexer.py
        # path, which doesn't exist on Mac-new (~/.openclaw/...) or VPS
        # (/data/.openclaw/...) — so the indexer was silently skipped on
        # every modern install, leaving the new persona's blueprint
        # un-embedded and invisible to Layer 5 (semantic_task_fit).
        #
        # a71f6bbd fix: the canonical INSTALLED wrapper lives at
        # ~/.openclaw/scripts/gemini-indexer.py (and /data/.openclaw/scripts/...
        # on VPS). Put those at the FRONT and DEPRIORITIZE the ~/clawd legacy
        # wrapper. ALSO: this phase used to print "Re-indexing complete" even
        # when the indexer exited non-zero (the sys.path ModuleNotFoundError
        # was swallowed) — that silent-success lie is the bug being fixed.
        # Now FAIL-LOUD: on non-zero exit we log stderr, mark Phase 5 FAILED in
        # pipeline-status.json, and DO NOT print "Re-indexing complete".
        # EMBED-5: prefer the SECTION-level indexer (gemini-section-indexer.py,
        # Skill 23) run per-persona. The canonical index is section-converged
        # (one row per '## Section N', mode/section_number tagged — what the
        # --mode leadership/coaching retrieval filters need); the chunk indexer
        # would embed the new persona as untagged unit_type='chunk' rows. The
        # chunk wrapper stays as FALLBACK when the section indexer isn't
        # installed. Both fail LOUD on non-zero exit (the fake-768 silent
        # fallback was removed from the section indexer — a missing
        # GOOGLE_API_KEY now exits 4 and Phase 5 reports FAILED).
        _sec_name = "gemini-section-indexer.py"
        section_candidates = [
            Path(__file__).resolve().parents[2] / "23-ai-workforce-blueprint" / "scripts" / _sec_name,
            Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "scripts" / _sec_name,
            Path("/data/.openclaw/skills/23-ai-workforce-blueprint/scripts") / _sec_name,
        ]
        indexer_candidates = [
            Path.home() / ".openclaw" / "scripts" / "gemini-indexer.py",
            Path("/data/.openclaw/scripts/gemini-indexer.py"),
            Path.home() / ".openclaw" / "workspace" / "scripts" / "gemini-indexer.py",
            Path("/data/.openclaw/workspace/scripts/gemini-indexer.py"),
            Path.home() / "clawd" / "scripts" / "gemini-indexer.py",  # legacy (deprioritized)
        ]
        section_path = next((p for p in section_candidates if p.exists()), None)
        indexer_path = section_path or next((p for p in indexer_candidates if p.exists()), None)
        if indexer_path is not None:
            if section_path is not None:
                indexer_cmd = [sys.executable, str(section_path), "--persona-id", folder]
            else:
                indexer_cmd = [sys.executable, str(indexer_path)]
            log(f"Phase 5: Re-indexing persona in Gemini Engine ({' '.join(indexer_cmd[1:])})...")
            result_proc = subprocess.run(
                indexer_cmd,
                capture_output=True,
                text=True,
                check=False
            )
            if result_proc.returncode != 0:
                _err = (result_proc.stderr or "").strip()
                log(f"  [PHASE 5 FAILED] gemini-indexer.py ({indexer_path}) exited "
                    f"with code {result_proc.returncode}: {_err[:1000]}")
                mark_phase(status, folder, 5, "FAILED",
                           f"indexer exit {result_proc.returncode}: {_err[:500]}")
                # NOTE: deliberately NOT printing "Re-indexing complete" — the
                # embed did not happen; the persona blueprint is NOT searchable.
            else:
                if (result_proc.stdout or "").strip():
                    log(f"  [PHASE 5] {result_proc.stdout.strip()[:500]}")
                mark_phase(status, folder, 5, "DONE")
                log("Phase 5: Re-indexing complete.")
        else:
            _all_probed = [str(c) for c in section_candidates + indexer_candidates]
            log(f"  [PHASE 5 FAILED] no indexer found in any of "
                f"{_all_probed} — persona NOT embedded")
            mark_phase(status, folder, 5, "FAILED",
                       f"indexer wrapper not found: {_all_probed}")

        # Phase 6: Append new persona to persona-categories.json so the
        # selector's list_available_personas() can see it on the next run.
        # Pre-v10.14.27 only the add-persona-from-source.sh wrapper did
        # this — direct orchestrator calls (e.g. orchestrator.py --single-book)
        # left the persona invisible to the v2 selector.
        # F1.4 (DEP-12): FAIL-LOUD + AUTO-REPAIR. The pre-fix code caught every
        # exception here and logged a WARNING — a categories-write failure was a
        # silent success that stranded the blueprint with no categories key
        # (invisible to the selector universe). _phase6_register_categories now
        # (a) auto-repairs with a safe-default entry so the persona is ALWAYS
        # registered (never-to-zero), and (b) records the failure so main() exits
        # PHASE6_CATEGORIES_EXIT_CODE instead of reporting a clean build.
        # P13-1: pass the Phase 3b appendix verdict (COMPLETE /
        # COMPLETE_WITH_WARNINGS / FAILED) already recorded in `status` above.
        _phase6_outcome = _phase6_register_categories(
            book, folder,
            appendix_status=status.get(folder, {}).get("phase3b"))
        if _phase6_outcome != "ok":
            mark_phase(status, folder, 6, "FAILED" if _phase6_outcome == "failed"
                       else "REPAIRED",
                       f"categories write {_phase6_outcome} "
                       f"(needs_retag; fail-loud exit {PHASE6_CATEGORIES_EXIT_CODE})")

        # Phase 6b: v6.6.0 — auto-regenerate governing-personas.md for every
        # department so the command-center dashboard picks up the new persona
        # without a manual `create_role_workspaces.py` run.
        # Uses the --refresh-personas-only flag added in this same PR.
        # Non-fatal: the new persona is still fully usable even if this step fails.
        try:
            crw_candidates = [
                Path(__file__).resolve().parents[2] / "23-ai-workforce-blueprint" / "scripts" / "create_role_workspaces.py",
                Path("/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/create_role_workspaces.py"),
                Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "scripts" / "create_role_workspaces.py",
            ]
            crw_path = next((p for p in crw_candidates if p.exists()), None)
            if crw_path:
                log(f"Phase 6b: Refreshing governing-personas.md for all departments ({crw_path})...")
                crw_proc = subprocess.run(
                    [sys.executable, str(crw_path), "--refresh-personas-only"],
                    capture_output=True, text=True, check=False, timeout=60,
                )
                if crw_proc.returncode == 0:
                    log("Phase 6b: governing-personas.md refresh complete.")
                    # §1.7.3: structured success line for converge/QC
                    print(f"[PERSONA-REFRESH] DONE: governing-personas.md refreshed for all depts")
                else:
                    reason = crw_proc.stderr[:200].strip() or f"rc={crw_proc.returncode}"
                    log(f"  Warning: --refresh-personas-only exited {crw_proc.returncode}: {reason}")
                    # §1.7.3: structured failure line the agent can surface
                    print(f"[PERSONA-REFRESH] FAILED: {reason}")
                    # Append to add-ledger for converge retry
                    _ledger_append_phase6b_skip(folder, f"FAILED: {reason}")
            else:
                msg = "Skill 23 not installed (create_role_workspaces.py not found)"
                log(f"  Phase 6b: {msg} — governing-personas.md NOT refreshed (non-fatal).")
                # §1.7.3: structured SKIPPED line
                print(f"[PERSONA-REFRESH] SKIPPED: {msg}")
                _ledger_append_phase6b_skip(folder, f"SKIPPED: {msg}")
        except Exception as e:
            log(f"  Warning: Phase 6b refresh failed: {e}")
            print(f"[PERSONA-REFRESH] FAILED: {e}")
            _ledger_append_phase6b_skip(folder, f"FAILED: {e}")

        return True

    except Exception as e:
        log(f"  [PHASE 3 FAILED] {book['title']}: {e}")
        mark_phase(status, folder, 3, "FAILED", str(e))
        return False

# ─── PROCESS ONE BOOK ─────────────────────────────────────────────────────────
async def process_book(session: aiohttp.ClientSession, book: dict, status: dict):
    folder = book["folder"]
    s = status[folder]

    timestamp = datetime.datetime.now().strftime('%B %-d at %-I:%M %p')
    log(f"\n{'='*60}")
    log(f"STARTING: {book['title']} by {book['author']}")
    log(f"{'='*60}")

    if s["started"] is None:
        status[folder]["started"] = timestamp
        save_status(status)

    # Phase 1
    if s["phase1"] not in ("COMPLETE",):
        ok = await run_extraction(session, book, status)
        if not ok:
            log(f"  Skipping {book['title']} - extraction failed")
            return

    # Phase 2
    if s["phase2"] not in ("COMPLETE",):
        ok = await run_analysis(session, book, status)
        if not ok:
            log(f"  Skipping synthesis for {book['title']} - analysis failed")
            return

    # Phase 3
    if s["phase3"] not in ("COMPLETE",):
        await run_synthesis(session, book, status)

# ─── PARSE ARGS ───────────────────────────────────────────────────────────────
def _parse_args():
    """
    v6.6.0: argparse so callers can run a single slug instead of the full list.

    --single-book / --slug SLUG
        Build a ONE-element BOOKS entry from the slug's source.json marker
        (written by add-persona-from-source.sh) and run ONLY that folder
        through phases 1-3. This is the #1 fix: without it, every source
        added via add-persona-from-source.sh silently never runs through
        the pipeline because the slug isn't in the hardcoded BOOKS list.

    --source-json PATH
        Explicit path to source.json (overrides the default search).
    """
    parser = argparse.ArgumentParser(
        prog="orchestrator.py",
        description="BlackCEO Coaching Personas Matrix — 3-phase book-to-persona pipeline.",
    )
    parser.add_argument(
        "--single-book", action="store_true",
        help="Run only the single slug specified by --slug (used by add-persona-from-source.sh).",
    )
    parser.add_argument(
        "--slug", metavar="SLUG",
        help="Slug to process when --single-book is given.",
    )
    parser.add_argument(
        "--source-json", metavar="PATH",
        help="Explicit path to source.json for --single-book mode.",
    )
    return parser.parse_args()


def _build_book_from_source_json(slug: str, source_json_path: str = None) -> dict:
    """
    Build a BOOKS-compatible dict from a slug's source.json marker file.
    Searches the canonical personas/<slug>/source.json location when no
    explicit path is given.

    source.json schema (written by add-persona-from-source.sh):
      {
        "slug":        "hormozi-100m-offers",
        "title":       "100M Offers",
        "author":      "Alex Hormozi",
        "source_type": "book",          # book / youtube / video / text
        "source_path": "/path/to/file",
        "text_file":   "/path/to/text/hormozi-100m-offers.txt",
        "added":       "2026-06-01T12:00:00Z",
        "pipeline_status": "PENDING"
      }
    """
    if source_json_path:
        sj_path = Path(source_json_path)
    else:
        sj_path = PERSONAS_DIR / slug / "source.json"

    if not sj_path.exists():
        raise FileNotFoundError(
            f"source.json not found for slug '{slug}'.\n"
            f"Expected: {sj_path}\n"
            "Run add-persona-from-source.sh to register the source first."
        )

    with open(sj_path) as f:
        data = json.load(f)

    source_type = data.get("source_type", "text")
    # For book types, the file field should point to the book file.
    # For video/youtube/text, the pipeline will use the pre-extracted text_file.
    book_file = data.get("source_path", "")
    if source_type != "book":
        # Non-book: the text file is the canonical input; use a dummy "file"
        # that the extraction phase will skip in favour of the pre-extracted text.
        book_file = data.get("text_file", "")

    return {
        "title":  data.get("title", slug),
        "author": data.get("author", "unknown"),
        "file":   str(Path(book_file).name) if book_file else f"{slug}.txt",
        "folder": slug,
        # Stash the full text_file path so run_extraction can pick it up.
        "_text_file": data.get("text_file", ""),
        "_source_type": source_type,
    }


def _ensure_status_entry(status: dict, book: dict) -> dict:
    """
    Guarantee a status entry exists for this book's folder.
    Used by --single-book mode where load_status() only iterates BOOKS.
    """
    folder = book["folder"]
    if folder not in status:
        status[folder] = {
            "title":   book["title"],
            "author":  book["author"],
            "phase1":  "PENDING",
            "phase2":  "PENDING",
            "phase3":  "PENDING",
            "started":   None,
            "completed": None,
            "errors":    [],
        }
        save_status(status)
    return status


# ─── MAIN ORCHESTRATOR ────────────────────────────────────────────────────────
async def main(args=None):
    if args is None:
        args = _parse_args()

    # Fail fast (before any orphan-guard / network work) if no model provider
    # route is usable. Deferred here from module-import time so this file stays
    # importable for the pure-Python write/matcher code paths the CI guards
    # exercise; a live run's fail-closed behavior is unchanged.
    _assert_provider_route()

    # ── ORPHAN-PROCESS PREVENTION (fleet-wide) ────────────────────────────────
    # Arm the shared self-defense so an interrupted/detached run can never leave
    # this Python child making :cloud calls forever (see orphan_guard.py). Runs
    # for BOTH modes; best-effort — a missing orphan_guard.py just warns.
    _og = None
    _og_run_dir = str(BASE / ".pipeline-runs")
    try:
        import orphan_guard as _og
        # Honour OPENCLAW_RUN_DIR (set by run-orchestrator.sh) so the orchestrator,
        # the launcher's trap, and reap-orchestrators.sh all agree on WHERE the
        # per-run pidfile lives; fall back to the workspace-local dir otherwise.
        _og_run_dir = _og.run_dir_path(_og_run_dir)
        _og.arm(log_fn=log, run_dir=_og_run_dir)
    except Exception as _og_e:
        log(f"  [orphan-guard] WARN: not armed ({_og_e}) — running without "
            f"orphan self-defense; use run-orchestrator.sh for the reapable path")

    # ── Single-book mode (--single-book --slug SLUG) ──────────────────────────
    if args.single_book:
        if not args.slug:
            print("ERROR: --single-book requires --slug SLUG", file=sys.stderr)
            sys.exit(1)

        # SINGLE-RUN LOCK per slug — refuse a duplicate/overlapping orchestrator
        # for the same persona (fix 4). The flock is held for the process
        # lifetime and released automatically on exit.
        if _og is not None:
            _slug_lock = _og.acquire_slug_lock(_og_run_dir, args.slug)
            if _slug_lock is None:
                log(f"ERROR: another orchestrator run for slug '{args.slug}' is "
                    f"already active (single-run lock held) — refusing to start "
                    f"a duplicate. If that run is dead, remove its lock in "
                    f"{_og_run_dir} or run reap-orchestrators.sh --sweep.")
                sys.exit(4)

        log("\n" + "="*60)
        log(f"Skill 22 Pipeline — Single-book mode: {args.slug}")
        log("="*60 + "\n")

        try:
            book = _build_book_from_source_json(args.slug, args.source_json)
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            sys.exit(1)

        # Load status, ensure entry for this slug
        status = {}
        if STATUS_FILE.exists():
            try:
                status = json.loads(STATUS_FILE.read_text())
            except Exception:
                status = {}
        _ensure_status_entry(status, book)

        log(f"  Title:  {book['title']}")
        log(f"  Author: {book['author']}")
        log(f"  Folder: {book['folder']}")
        log(f"  Source type: {book.get('_source_type', 'book')}")
        s = status[book["folder"]]
        log(f"  Status: P1={s['phase1']} P2={s['phase2']} P3={s['phase3']}")

        if s["phase3"] == "COMPLETE" and s.get("phase5") == "DONE":
            log("  Persona already COMPLETE (blueprint + embed). Use --force to "
                "re-run (not yet implemented).")
            log("  Blueprint at: " + str(PERSONAS_DIR / book["folder"] / "persona-blueprint.md"))
            return
        if s["phase3"] == "COMPLETE" and s.get("phase5") != "DONE":
            # F1.2 (FDN-5): the blueprint was synthesized but Phase 5 embedding
            # has not succeeded. Do NOT early-return — fall through to
            # process_book so run_synthesis re-enters in RE-EMBED-ONLY mode
            # (idempotent: no LLM synthesis, just re-index + re-register).
            log(f"  Blueprint COMPLETE but Phase-5 embed not DONE "
                f"(phase5={s.get('phase5', 'PENDING')}) — re-entering to re-embed only.")

        connector = aiohttp.TCPConnector(limit=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                # G2 preflight then G3/G4 storm guard (1 book) — see the
                # STRUCTURAL STORM GUARDS block. A dead key / no-credits box
                # aborts here BEFORE the phase loop.
                await preflight_providers(
                    session, [MODEL_EXTRACTION, MODEL_ANALYSIS, MODEL_SYNTHESIS])
                init_storm_guard(PER_BOOK_EXPECTED_CALLS)
                await process_book(session, book, status)
            except _BuildAbort as e:
                log("\n" + "="*60)
                log(f"[BUILD ABORTED — STORM GUARD] {e}")
                log(f"  Provider requests made before abort: "
                    f"{_STORM.count if _STORM else 0}")
                log("="*60)
                sys.exit(2)

        final = status[book["folder"]]
        log("\n" + "="*60)
        log(f"Single-book pipeline complete: {args.slug}")
        log(f"  P1={final['phase1']}  P2={final['phase2']}  P3={final['phase3']}"
            f"  P5={final.get('phase5', 'PENDING')}")
        log("="*60)

        # F1.2 (FDN-5): Phase-5 (embedding) failure is FATAL end-to-end. A
        # persona whose blueprint exists but whose vectors are missing is
        # "registered but not embedded" — matchable by keyword only, invisible
        # to Layer-5 semantic retrieval (exactly the failure class N38 guards
        # against, but on the workspace side where N38 does not run). Propagate a
        # DISTINCT exit code (8 = EMBED_FAILED) so the caller
        # (add-persona-from-source.sh -> persona-inbox-watcher.sh) fails LOUD and
        # quarantines/retries instead of logging a false success. The blueprint
        # is deliberately LEFT ON DISK so an idempotent retry re-embeds only
        # (see run_synthesis `_phase3_already` re-entry above).
        if final.get("phase5") == "FAILED":
            log(f"[PIPELINE FAILED — EMBED_FAILED (8)] {args.slug}: Phase 5 "
                f"embedding FAILED — persona is registered but NOT searchable "
                f"(vector-less). Blueprint left on disk; re-run re-embeds only.")
            sys.exit(8)
        # F1.4 (DEP-12): Phase-6 categories fail-loud gate (exit 9). Runs after
        # the Phase-5 embed gate so a persona that is both un-embedded AND needs
        # re-tag still surfaces the earlier (embed) failure first.
        _exit_if_categories_failed()
        return

    # ── Full-batch mode (default: process all pending books in BOOKS list) ────
    log("\n" + "="*60)
    log("BlackCEO Coaching Personas Matrix - Pipeline Starting")
    log(f"Books to process: {len(BOOKS)}")
    log(f"Parallel limit: {PARALLEL_LIMIT} books at a time")
    log(f"Extraction model: {MODEL_EXTRACTION}")
    log(f"Analysis model:   {MODEL_ANALYSIS}")
    log(f"Synthesis model:  {MODEL_SYNTHESIS}")
    log("="*60 + "\n")

    # Check pdfplumber is available
    try:
        import pdfplumber
        log("PDF library: pdfplumber OK")
    except ImportError:
        try:
            import pypdf
            log("PDF library: pypdf OK (pdfplumber preferred - run: pip3 install pdfplumber)")
        except ImportError:
            log("ERROR: No PDF library found. Run: pip3 install pdfplumber")
            return

    status = load_status()

    # Filter to only books that aren't fully complete
    pending = [b for b in BOOKS if status[b["folder"]]["phase3"] != "COMPLETE"]
    complete = [b for b in BOOKS if status[b["folder"]]["phase3"] == "COMPLETE"]

    log(f"Already complete: {len(complete)}")
    log(f"Pending: {len(pending)}\n")

    if not pending:
        log("All books already processed. Pipeline complete.")
        return

    # Process in batches of PARALLEL_LIMIT
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            # G2 preflight (abort before any phase if a provider the build needs
            # fails auth/credits/params) then arm the G3/G4 storm guard. The
            # global request budget scales with the pending-book count, so no
            # batch — however large — can produce an unbounded request storm.
            await preflight_providers(
                session, [MODEL_EXTRACTION, MODEL_ANALYSIS, MODEL_SYNTHESIS])
            init_storm_guard(len(pending) * PER_BOOK_EXPECTED_CALLS)

            for i in range(0, len(pending), PARALLEL_LIMIT):
                batch = pending[i:i + PARALLEL_LIMIT]
                batch_num = (i // PARALLEL_LIMIT) + 1
                total_batches = (len(pending) + PARALLEL_LIMIT - 1) // PARALLEL_LIMIT

                log(f"\n--- BATCH {batch_num}/{total_batches} ---")
                log(f"Books: {', '.join(b['title'] for b in batch)}\n")

                tasks = [process_book(session, book, status) for book in batch]
                await asyncio.gather(*tasks)

                # Progress report after each batch
                done = sum(1 for b in BOOKS if status[b["folder"]]["phase3"] == "COMPLETE")
                log(f"\n--- Batch {batch_num} complete. Total done: {done}/{len(BOOKS)} ---\n")
        except _BuildAbort as e:
            log("\n" + "="*60)
            log(f"[BUILD ABORTED — STORM GUARD] {e}")
            log(f"  Provider requests made before abort: "
                f"{_STORM.count if _STORM else 0} "
                f"(budget was {_STORM.budget if _STORM else 'n/a'})")
            log("  No request storm occurred — the build stopped structurally.")
            log("="*60)
            sys.exit(2)

    # Final report
    log("\n" + "="*60)
    log("PIPELINE COMPLETE")
    log("="*60)
    final_status = load_status()
    for book in BOOKS:
        s = final_status[book["folder"]]
        phases = f"P1:{s['phase1'][0]} P2:{s['phase2'][0]} P3:{s['phase3'][0]}"
        log(f"  {book['title']}: {phases}")

    complete_count = sum(1 for b in BOOKS if final_status[b["folder"]]["phase3"] == "COMPLETE")
    failed_count = sum(1 for b in BOOKS if "FAILED" in [final_status[b["folder"]][f"phase{p}"] for p in [1,2,3]])
    # F1.2 (FDN-5): a synthesized-but-un-embedded persona is a silent-failure
    # class too, so surface Phase-5 failures in the batch report as well.
    embed_failed = [b["folder"] for b in BOOKS
                    if final_status[b["folder"]].get("phase5") == "FAILED"]
    log(f"\nCompleted: {complete_count}/{len(BOOKS)}")
    log(f"Failed: {failed_count}")
    if embed_failed:
        log(f"EMBED_FAILED (Phase 5, registered but NOT searchable): "
            f"{len(embed_failed)} -> {', '.join(embed_failed)}")
    log(f"\nPersona blueprints saved to: {PERSONAS_DIR}")
    log(f"Status file: {STATUS_FILE}")
    log(f"Full log: {LOG_FILE}")
    # F1.2 (FDN-5): propagate an embedding failure as a distinct non-zero exit
    # (8 = EMBED_FAILED) end-to-end, even in full-batch mode, so no wrapper can
    # log a false success over a vector-less persona. Blueprints stay on disk;
    # an idempotent re-run re-embeds only. Runs BEFORE the Phase-6 categories
    # gate so an embed failure surfaces first (mirrors the single-book tail).
    if embed_failed:
        sys.exit(8)
    # F1.4 (DEP-12): Phase-6 categories fail-loud gate (exit 9), after the embed gate.
    _exit_if_categories_failed()


def _exit_if_categories_failed() -> None:
    """F1.4 (DEP-12) fail-loud gate. If any Phase-6 persona-categories.json write
    needed the auto-repair path (or failed even that) this run, exit with the
    distinct PHASE6_CATEGORIES_EXIT_CODE so the caller never treats a
    needs_retag build as a clean success (mirrors F1.2 / FDN-5). The affected
    personas are still REGISTERED (never-to-zero) — the non-zero exit signals
    "operator must re-tag", not "persona lost"."""
    if not pipeline_had_categories_failures():
        return
    log("\n" + "="*60)
    log(f"[PHASE 6 FAIL-LOUD] {len(_CATEGORIES_WRITE_FAILURES)} persona(s) needed "
        f"a Phase-6 categories auto-repair (safe-default domain + needs_retag) "
        f"this run: {_CATEGORIES_WRITE_FAILURES}")
    log(f"  These personas ARE registered and selectable, but their tags are "
        f"placeholders — re-classify them, then re-run.")
    log(f"  Exiting {PHASE6_CATEGORIES_EXIT_CODE} (not a silent success).")
    log("="*60)
    sys.exit(PHASE6_CATEGORIES_EXIT_CODE)


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())

# Fallback list — books that hit Kimi direct content filter, route via OpenRouter
# NOTE: This duplicate definition (also at line ~153) is kept here to avoid
# breaking any callers that access it via module inspection. The set at line ~153
# is the canonical one used at runtime; this one is a no-op (already defined).
# OPENROUTER_FALLBACK_FOLDERS = {"samit-disrupt-yourself", "attwood-passion-test"}
