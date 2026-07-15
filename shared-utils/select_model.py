"""
select_model.py — Smart model selector for OpenClaw skills.

Used by Skill 22 (Book-to-Persona), Skill 15 (Team Management), Skill 23 (AI
Workforce Blueprint), and any other skill that needs a model recommendation
that auto-adapts to whatever the client has installed.

Three purpose-tier chains (v10.2.0 priority — Ollama Cloud first, then
OpenRouter version of the same models, then OAuth GPT):

  --purpose-tier heavy   (Heavy reasoning / heavy thinking — default)
    1. ollama/deepseek-v*-pro:cloud   (Ollama Cloud DeepSeek V4-pro, 1M ctx)
    2. ollama/kimi-k*:cloud           (Ollama Cloud Kimi 2.6+, 262K ctx)
    3. openrouter/deepseek/deepseek-v*-pro  (OpenRouter DeepSeek V4-pro — same model, OR route)
    4. openrouter/moonshot/kimi-k*    (OpenRouter Kimi — same model, OR route)
    5. codex/gpt-* OR openai-codex/gpt-*    (OAuth GPT — last resort, latest version)

  --purpose-tier mid     (Mid-tier reasoning — fast but capable)
    1. ollama/minimax-m*:cloud        (Ollama Cloud Minimax 2.7+)
    2. openrouter/xiaomi/mimo-v*-pro  (OpenRouter Mimo 2.5+ pro, thinking=high)

  --purpose-tier fast    (Fast / cheap — bulk operations)
    1. ollama/deepseek-v*-flash:cloud (Ollama Cloud DeepSeek V4-flash)
    2. openrouter/deepseek/deepseek-v*-flash  (OpenRouter DeepSeek V4-flash)
    3. openrouter/google/gemini-3*flash-lite* (OpenRouter Gemini Flash Lite)

In every tier chain: NEVER select Anthropic models. Hardcoded filter.

For each tier, the selector picks the HIGHEST VERSION NUMBER it finds in the
client's openclaw.json. So when Kimi 2.7 or 3.0 ships and the client adds it,
the selector automatically picks the higher version without any code change.

If no chain entry matches anything in the client's config, the selector
returns Tier 5 (owner-input-required) with a plain-English prompt the install
agent can show the owner.

Example:
    >>> from select_model import select_model_for_skill
    >>> r = select_model_for_skill("book-to-persona", purpose_tier="heavy")
    >>> r["model_id"]
    'ollama/kimi-k2.6:cloud'
    >>> r["chain_position"]
    1
"""

import json
import os
import re
import sys
from typing import Optional


# Hardcoded filter — never recommend these. ROOT-anchored (MODEL-01), never
# per-generation, so renamed/future Claude families stay forbidden with no code
# change. Kept at BYTE parity with the Command Center TypeScript selector's
# FORBIDDEN_PREFIXES (blackceo-command-center src/lib/model-selector.ts):
#   anthropic/            canonical provider-prefixed route
#   anthropic.            Bedrock/Vertex dot-form (anthropic.claude-…, any gen)
#   openrouter/anthropic/ nested OpenRouter route
#   claude-               any Claude family/generation slug w/ no provider prefix
#                         (claude-5, claude-fable-5, claude-mythos-5, claude-instant)
# The old per-generation list (claude-3/-4/-opus/-sonnet/-haiku) silently ALLOWED
# the anthropic. dot route, claude-5/future gens, and named future models.
# Bare opus/sonnet/haiku (no vendor prefix, no `claude-` stem) are NOT routable
# model ids on any connector, so they are deliberately NOT matched — a substring
# match would false-positive on unrelated ids.
FORBIDDEN_PREFIXES = (
    "anthropic/",
    "anthropic.",
    "openrouter/anthropic/",
    "claude-",
)

# ─── Intelligent Model Selector (v12.15.0) ───────────────────────────────────
# The PREFERENCE CASCADE (PLAN.md §2) — single source of truth for tier order.
# Every layer (build-time dept default, task-time selector, repair sweep, gate)
# obeys this exact ordering.
#
#   TIER 1 — Ollama Cloud   : ollama/*:cloud (baseUrl https://ollama.com/v1)
#   TIER 2 — OpenRouter OSS  : openrouter/<oss-vendor>/* (open-weight only)
#   TIER 3 — Free            : *:free / pricingModel == 'free'  (LAST RESORT)
#
# A proprietary OpenRouter route (openrouter/openai/*, openrouter/google/*-pro,
# openrouter/anthropic/*) is NOT a Tier-2 open-source model. Anthropic is
# forbidden outright (FORBIDDEN_PREFIXES); other proprietary routes are not
# silently selected by the cascade.
TIER_OLLAMA_CLOUD = 1
TIER_OPENROUTER_OSS = 2
TIER_FREE = 3

# OpenRouter open-source (open-weight) vendor allow-list (PLAN.md §2 / §12).
OPENROUTER_OSS_VENDORS = (
    "deepseek",
    "moonshot", "moonshotai",
    "qwen", "alibaba",
    "z-ai", "zhipu", "zhipuai",
    "xiaomi",
    "meta", "meta-llama", "llama",
    "mistral", "mistralai",
    "google",   # only the open-weight gemma family is OSS-classified below
    "nvidia",
    "minimax",
)

# The "free" sentinel the Command Center bug used as a default. NEVER a valid
# resolution. Kept ONLY so the gate can explicitly reject it.
FREE_SENTINELS = ("openrouter/free", "free", "openrouter/auto:free")


def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _load_json_sibling(name: str) -> dict:
    """Load a JSON data file that ships next to this module (or its symlinks)."""
    candidates = [
        os.path.join(_module_dir(), name),
        os.path.join(os.path.expanduser("~"), "Downloads", "openclaw-master-files",
                     "shared-utils", name),
        os.path.join(os.path.expanduser("~"), ".openclaw", "skills",
                     "shared-utils", name),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except (OSError, ValueError):
                continue
    return {}


_CAP_MAP_CACHE = None
_SUIT_MAP_CACHE = None


def load_capability_map() -> dict:
    global _CAP_MAP_CACHE
    if _CAP_MAP_CACHE is None:
        _CAP_MAP_CACHE = _load_json_sibling("model-capabilities.json")
    return _CAP_MAP_CACHE


def load_suitability_map() -> dict:
    global _SUIT_MAP_CACHE
    if _SUIT_MAP_CACHE is None:
        _SUIT_MAP_CACHE = _load_json_sibling("dept-model-suitability.json")
    return _SUIT_MAP_CACHE


def _strip_provider(model_id: str) -> str:
    """Reduce a fully-qualified model id to its bare family slug for matching.

    ollama/qwen3-vl:235b-cloud      -> qwen3-vl
    openrouter/deepseek/deepseek-v4-pro -> deepseek-v4-pro
    """
    if not model_id:
        return ""
    mid = model_id.strip().lower()
    # drop any :cloud / :free / :235b style suffix
    mid = mid.split(":", 1)[0]
    # take the last path segment (vendor/model -> model)
    mid = mid.split("/")[-1]
    return mid


# Generation-hint substrings. An UNKNOWN model id (matching no capability
# family) whose bare slug contains one of these is almost certainly a media
# generation / transcription model, NOT a text LLM. Such ids MUST NOT fall
# through to the ["text"] default — otherwise the cascade could pick an image /
# video / TTS model for a text LLM role.
#
# Adversarial case (the reason this gate exists): a client installs a new model
# like `replicate/flux-pro-1.1` or `fal/sora-2-hd` or `somevendor/img-gen-xl`.
# None match a known family, so the old behavior returned ["text"] and the model
# became eligible for a HEAVY-REASONING / WRITING role — producing an LLM agent
# backed by an image generator. The hints below classify these as their output
# modality so model_has_modality(...,"text") returns False for them.
_GENERATION_HINT_PATTERNS = re.compile(
    r"(?:^|[-_./])(?:"
    r"image|img|flux|sora|dalle|diffusion|"   # image generation
    r"video|veo|kling|"                        # video generation
    r"tts|whisper|"                            # speech-to-text / text-to-speech
    r"audio[-_]?gen|"                           # audio generation (audio-gen, audiogen, audio_gen)
    r"gpt-image"                                # explicit OpenAI image route
    r")",
    re.IGNORECASE,
)


def _generation_hint_modality(bare: str) -> Optional[str]:
    """Classify an UNKNOWN slug by its generation hint, or None if no hint."""
    low = bare.lower()
    if re.search(r"(?:^|[-_./])(?:image|img|flux|dalle|diffusion|gpt-image)", low):
        return "image_generation"
    if re.search(r"(?:^|[-_./])(?:video|veo|kling|sora)", low):
        return "video_generation"
    if re.search(r"(?:^|[-_./])whisper", low):
        return "audio_transcription"
    if re.search(r"(?:^|[-_./])(?:tts|audio[-_]?gen)", low):
        return "audio_generation"
    return None


def capabilities_for_model(model_id: str) -> list:
    """Resolve a model's capability set from the shipped capability map.

    Family is matched by the FIRST family whose `match` regex matches the
    provider-stripped slug. More-specific families (e.g. qwen-vl, glm-vision)
    are listed before their broader siblings in the JSON so they win.

    HARDENED (MSF): a slug that matches NO capability family but whose name
    carries a generation hint (image|img|flux|sora|dalle|diffusion|video|veo|
    tts|whisper|audio-gen|gpt-image) is classified by its OUTPUT modality and
    NEVER returned as ["text"]. This guarantees text_ok=False for such ids so
    they can never be selected for an LLM role (adversarial case above the
    pattern definition). Recognized text models are unaffected — known families
    match first and return their declared capabilities verbatim.
    """
    cap_map = load_capability_map()
    families = cap_map.get("families", [])
    bare = _strip_provider(model_id)
    if not bare:
        return list(cap_map.get("default_capabilities", ["text"]))
    for fam in families:
        pat = fam.get("match")
        if not pat:
            continue
        try:
            if re.fullmatch(pat, bare) or re.match(pat + r"$", bare) or re.match(pat, bare):
                return list(fam.get("capabilities", []))
        except re.error:
            continue
    # Unknown family: if the bare slug looks like a generation/transcription
    # model, report ONLY its generation modality (text_ok=False). Never let a
    # generation model masquerade as a text LLM via the default.
    if _GENERATION_HINT_PATTERNS.search(bare):
        gen_modality = _generation_hint_modality(bare) or "image_generation"
        return [gen_modality]
    return list(cap_map.get("default_capabilities", ["text"]))


def model_has_modality(model_id: str, required_modality) -> bool:
    """True iff the model's capabilities ⊇ required_modality (HARD constraint)."""
    if not required_modality:
        return True
    if isinstance(required_modality, str):
        required_modality = [required_modality]
    caps = set(capabilities_for_model(model_id))
    # Behavior tokens (reasoning/tool_use/etc.) are soft preferences, not hard
    # eligibility — only true OUTPUT/INPUT modalities are inviolable.
    hard_modalities = {
        "vision", "image_generation", "video_generation",
        "audio_generation", "audio_transcription", "audio_input", "embeddings",
    }
    for req in required_modality:
        if req in hard_modalities and req not in caps:
            return False
        # `text` is satisfied by any non-pure-generation model
        if req == "text" and not (caps & {"text"}) and not (caps - {"image_generation", "video_generation", "audio_generation", "audio_transcription"}):
            return False
    return True


def tier_of_model(model_id: str) -> int:
    """Classify a model id into the PREFERENCE CASCADE tier (1/2/3).

    Returns 0 for a model that does not belong to any valid tier (e.g. a
    proprietary OpenRouter route or the free sentinel — which the gate rejects).
    """
    if not model_id:
        return 0
    mid = model_id.strip().lower()
    if mid in FREE_SENTINELS:
        return TIER_FREE
    # Tier 3: any *:free slug (free pricing tier)
    if mid.endswith(":free") or mid.endswith("/free"):
        return TIER_FREE
    # Tier 1: Ollama Cloud. The cloud marker is the trailing `cloud` token of
    # the tag (after the last ':'), which may be compound, e.g.
    # `ollama/qwen3-vl:235b-cloud` or simple `ollama/deepseek-v4-pro:cloud`.
    if mid.startswith("ollama/"):
        tag = mid.split(":", 1)[1] if ":" in mid else ""
        if tag == "cloud" or tag.endswith("-cloud"):
            return TIER_OLLAMA_CLOUD
    if mid.startswith("ollama-cloud/"):
        return TIER_OLLAMA_CLOUD
    # Tier 2: OpenRouter open-source vendors
    if mid.startswith("openrouter/"):
        parts = mid.split("/")
        if len(parts) >= 3:
            vendor = parts[1]
            model_slug = parts[2]
            # google is only OSS for the gemma family; gemini-*-pro is proprietary
            if vendor == "google" and not model_slug.startswith("gemma"):
                return 0
            if vendor in OPENROUTER_OSS_VENDORS:
                return TIER_OPENROUTER_OSS
        return 0
    return 0


# Pattern definitions — each slot in the chain gets a version-capturing regex.
KIMI_OLLAMA      = {"label": "Ollama Cloud Kimi (thinking=high) — smartest, 262K ctx",
                    "pattern": re.compile(r"^ollama/kimi-k(\d+(?:\.\d+)*)(?::cloud)?$")}
KIMI_OPENROUTER  = {"label": "OpenRouter Kimi (thinking=high) — 262K ctx",
                    "pattern": re.compile(r"^openrouter/moonshot(?:ai)?/kimi-k(\d+(?:\.\d+)*)$")}
DEEPSEEK_PRO_OLLAMA     = {"label": "Ollama Cloud DeepSeek V*-pro (thinking=high) — 1M ctx",
                           "pattern": re.compile(r"^ollama/deepseek-v(\d+(?:\.\d+)*)-pro(?::cloud)?$")}
DEEPSEEK_PRO_OPENROUTER = {"label": "OpenRouter DeepSeek V*-pro (thinking=high) — 1M ctx",
                           "pattern": re.compile(r"^(?:openrouter/)?deepseek/deepseek-v(\d+(?:\.\d+)*)-pro$")}
OAUTH_GPT        = {"label": "OAuth GPT (latest, subscription)",
                    "pattern": re.compile(r"^(?:openai-)?codex/gpt-(\d+(?:\.\d+)*)(?:-[a-z]+)?$")}
MIMO_OPENROUTER  = {"label": "OpenRouter Mimo Pro (thinking=high)",
                    "pattern": re.compile(r"^openrouter/xiaomi/mimo-v(\d+(?:\.\d+)*)-pro$")}
GLM_OPENROUTER   = {"label": "OpenRouter GLM (thinking=high)",
                    "pattern": re.compile(r"^openrouter/(?:z-ai|zhipu(?:ai)?)/glm-?(\d+(?:\.\d+)*)$")}
MINIMAX_OLLAMA   = {"label": "Ollama Cloud Minimax",
                    "pattern": re.compile(r"^ollama/minimax-m(\d+(?:\.\d+)*)(?::cloud)?$")}
DEEPSEEK_FLASH_OLLAMA     = {"label": "Ollama Cloud DeepSeek V*-flash",
                             "pattern": re.compile(r"^ollama/deepseek-v(\d+(?:\.\d+)*)-flash(?::cloud)?$")}
DEEPSEEK_FLASH_OPENROUTER = {"label": "OpenRouter DeepSeek V*-flash",
                             "pattern": re.compile(r"^(?:openrouter/)?deepseek/deepseek-v(\d+(?:\.\d+)*)-flash$")}
GEMINI_FLASH_LITE         = {"label": "OpenRouter Gemini Flash Lite",
                             "pattern": re.compile(r"^(?:openrouter/)?google/gemini-(\d+(?:\.\d+)*)-flash-lite(?:-preview)?$")}
# v10.10.0 P0-002: Gemini 3.1 Pro pattern. Final fallback for the
# orchestrator and installer-subagent chains per PRD §5.1 and §5.2.
GEMINI_PRO                = {"label": "OpenRouter Gemini Pro",
                             "pattern": re.compile(r"^(?:openrouter/)?google/gemini-(\d+(?:\.\d+)*)-pro(?:-preview)?$")}

# Purpose-tier chains. v10.2.0 priority (per owner directive):
#   For heavy reasoning + book extraction, prefer Ollama Cloud DeepSeek V4-pro
#   or Ollama Cloud Kimi 2.6 (or latest version of each). If the client has
#   neither on Ollama Cloud, fall back to the SAME model via OpenRouter
#   (openrouter/deepseek/deepseek-v4-pro or openrouter/moonshot/kimi-k2.6).
#   OAuth GPT only when neither Ollama nor OpenRouter has those models.
#
# Each chain has 3 context-need variants:
#   normal — input fits in Kimi's 262K window
#   large  — input is 800K-3M chars; DeepSeek V4-pro's 1M ctx required
#   huge   — input is > 3M chars; DeepSeek V4-pro only
CHAINS = {
    "heavy": {
        # Default heavy reasoning — Ollama DeepSeek V4-pro and Kimi 2.6 first,
        # then OpenRouter versions of the same models, then OAuth GPT.
        "normal": [
            DEEPSEEK_PRO_OLLAMA, KIMI_OLLAMA,           # Ollama Cloud preferred (same models)
            DEEPSEEK_PRO_OPENROUTER, KIMI_OPENROUTER,   # Same models via OpenRouter as fallback
            OAUTH_GPT,                                  # Last resort
            MIMO_OPENROUTER, GLM_OPENROUTER,            # Mid-cost OR alternates only if Kimi/DeepSeek missing
        ],
        # Large input (800K-3M chars): DeepSeek V4-pro's 1M context required
        "large": [
            DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER,
            OAUTH_GPT,
            KIMI_OLLAMA, KIMI_OPENROUTER,  # last resort; 262K may fail on big input
        ],
        # Huge input (>3M chars): DeepSeek V4-pro is the only model with enough context
        "huge": [
            DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER,
            OAUTH_GPT,
        ],
    },
    "mid": {
        "normal": [MINIMAX_OLLAMA, MIMO_OPENROUTER, GLM_OPENROUTER],
        "large":  [MINIMAX_OLLAMA, MIMO_OPENROUTER, GLM_OPENROUTER],
        "huge":   [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, OAUTH_GPT],
    },
    "fast": {
        "normal": [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_FLASH_LITE],
        "large":  [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_FLASH_LITE],
        "huge":   [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER],
    },

    # ─── v10.9.0 P1-C: PRD §5 role-specific chains ────────────────────────
    # These four chains map 1:1 to the audit's PRD §5 specification so
    # Phase 8 (Model Selection) can verify role-specific dispatch.
    #
    # §5.1 Master Orchestrator (thinking=high):
    #   1. ollama/kimi-k*:cloud  → 2. openrouter/moonshot/kimi-k*  → 3. Gemini 3.1 Pro
    # v10.10.0 P0-002: Gemini Pro is now in position 3, the explicit PRD §5.1
    # fallback. Flash Lite drops to position 4 (cheaper last resort).
    "orchestrator": {
        "normal": [
            KIMI_OLLAMA,                # 1. Ollama Cloud Kimi (latest)
            KIMI_OPENROUTER,            # 2. OpenRouter Kimi (same model, OR route)
            GEMINI_PRO,                 # 3. Gemini 3.1 Pro — PRD §5.1 explicit fallback
            GEMINI_FLASH_LITE,          # 4. Gemini Flash Lite — cheaper last resort
            OAUTH_GPT,
        ],
        "large": [KIMI_OLLAMA, KIMI_OPENROUTER, GEMINI_PRO, DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, OAUTH_GPT],
        "huge":  [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, GEMINI_PRO, OAUTH_GPT],
    },

    # §5.2 Installer sub-agent — needs DeepSeek V4 Pro's 1M context for big
    #   skill files
    #   1. ollama/deepseek-v*-pro:cloud  →  2. openrouter/deepseek/...  →  3. Gemini 3.1 Pro
    "installer-subagent": {
        "normal": [
            DEEPSEEK_PRO_OLLAMA,        # 1. Ollama Cloud DeepSeek V4 Pro
            DEEPSEEK_PRO_OPENROUTER,    # 2. OpenRouter DeepSeek V4 Pro
            GEMINI_PRO,                 # 3. Gemini 3.1 Pro — PRD §5.2 explicit fallback
            GEMINI_FLASH_LITE,          # 4. Cheaper last resort
            OAUTH_GPT,
        ],
        "large": [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, GEMINI_PRO, OAUTH_GPT],
        "huge":  [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, GEMINI_PRO, OAUTH_GPT],
    },

    # §5.3 QC sub-agent — cheap+capable; Kimi for reasoning, Flash Lite for
    #   bulk yes/no checks
    #   1. ollama/kimi-k*:cloud  →  2. openrouter/moonshot/kimi  →  3. Gemini Flash Lite
    "qc-subagent": {
        "normal": [
            KIMI_OLLAMA,                # 1. Ollama Cloud Kimi
            KIMI_OPENROUTER,            # 2. OpenRouter Kimi
            GEMINI_FLASH_LITE,          # 3. OpenRouter Gemini Flash Lite (cheap last resort)
        ],
        "large": [KIMI_OLLAMA, KIMI_OPENROUTER, DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER],
        "huge":  [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER],
    },

    # §5.4 Book-to-Persona pipeline — Trevor 2026-06-01: DeepSeek V4 Pro FIRST
    #   (the latest; Ollama Cloud preferred -> OpenRouter DeepSeek fallback). Kimi
    #   demoted to tertiary; cheapest fallback at the end.
    #   1. DeepSeek cloud -> 2. DeepSeek OR -> 3. Kimi cloud -> 4. Kimi OR -> 5. Gemini Flash Lite
    "book-to-persona": {
        "normal": [
            DEEPSEEK_PRO_OLLAMA,        # 1. Ollama Cloud DeepSeek V4 Pro (latest, preferred)
            DEEPSEEK_PRO_OPENROUTER,    # 2. OpenRouter DeepSeek V4 Pro (fallback)
            KIMI_OLLAMA,                # 3. Ollama Cloud Kimi
            KIMI_OPENROUTER,            # 4. OpenRouter Kimi
            GEMINI_FLASH_LITE,          # 5. Cheapest fallback
        ],
        "large": [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, KIMI_OLLAMA, KIMI_OPENROUTER, GEMINI_FLASH_LITE],
        "huge":  [DEEPSEEK_PRO_OLLAMA, DEEPSEEK_PRO_OPENROUTER, GEMINI_FLASH_LITE],
    },
}


def _parse_version(s: str) -> tuple:
    """Parse a dotted version like '2.6' into (2, 6) for comparison."""
    try:
        return tuple(int(p) for p in s.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _is_forbidden(model_id: str) -> bool:
    # Substring match against the ROOT anchors (MODEL-01). Semantics kept identical
    # to the TS twin's isForbidden (`mid.includes(p)`): `p in mid` already subsumes
    # `startswith`, so both engines forbid the SAME set. See parity check.
    mid = model_id.lower()
    return any(mid.startswith(p) or p in mid for p in FORBIDDEN_PREFIXES)


def _load_openclaw_config(path: Optional[str] = None) -> dict:
    candidates = [
        path,
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "/data/.openclaw/openclaw.json",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    return {}


def _list_available_models(cfg: dict) -> list:
    """Extract every model identifier the client has configured."""
    found = set()

    def _take(value):
        if isinstance(value, str) and value:
            found.add(value)
        elif isinstance(value, list):
            for v in value:
                _take(v)
        elif isinstance(value, dict):
            for k in ("primary", "model", "fallbacks", "id"):
                if k in value:
                    _take(value[k])

    models_list = cfg.get("models", {}).get("list", [])
    for entry in models_list:
        if isinstance(entry, dict):
            _take(entry.get("id"))
            _take(entry.get("model"))
        elif isinstance(entry, str):
            _take(entry)

    agents = cfg.get("agents", {})
    defaults = agents.get("defaults", {})
    _take(defaults.get("model"))
    _take(defaults.get("subagents", {}).get("model"))

    for entry in agents.get("list", []):
        if isinstance(entry, dict):
            _take(entry.get("model"))
            _take(entry.get("subagents", {}).get("model"))

    return [m for m in found if not _is_forbidden(m)]


def _best_match_in_position(models: list, chain_entry: dict) -> Optional[str]:
    """Highest-version model matching the chain entry's pattern."""
    candidates = []
    for m in models:
        match = chain_entry["pattern"].match(m)
        if match:
            version = _parse_version(match.group(1))
            candidates.append((version, m))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _classify_context_need(input_chars: Optional[int]) -> str:
    """Map an input character count to a context-need bucket."""
    if input_chars is None:
        return "normal"
    if input_chars > 3_000_000:
        return "huge"
    if input_chars > 800_000:
        return "large"
    return "normal"


def select_model_for_skill(
    skill_name: str = "",
    purpose_tier: str = "heavy",
    context_need: str = "normal",
    input_chars: Optional[int] = None,
    purpose: str = "",
    openclaw_json_path: Optional[str] = None,
) -> dict:
    """
    Select the best available model for a skill.

    Args:
      skill_name:     For logs / prompts
      purpose_tier:   "heavy" | "mid" | "fast"  (default: heavy)
      context_need:   "normal" | "large" | "huge"  (auto-derived from input_chars if given)
      input_chars:    Optional input size; if provided, overrides context_need
      purpose:        Free-text description
      openclaw_json_path: Path override

    Returns dict with:
      model_id, chain_position, position_label, needs_owner_input,
      purpose_tier, context_need, available_models, prompt_to_owner,
      skill, purpose
    """
    if purpose_tier not in CHAINS:
        purpose_tier = "heavy"

    # Auto-derive context_need from input_chars if caller passed it
    if input_chars is not None:
        context_need = _classify_context_need(input_chars)

    if context_need not in ("normal", "large", "huge"):
        context_need = "normal"

    cfg = _load_openclaw_config(openclaw_json_path)
    available = _list_available_models(cfg)
    chain = CHAINS[purpose_tier][context_need]

    for idx, entry in enumerate(chain, start=1):
        match = _best_match_in_position(available, entry)
        if match:
            return {
                "model_id": match,
                "chain_position": idx,
                "position_label": entry["label"],
                "needs_owner_input": False,
                "purpose_tier": purpose_tier,
                "context_need": context_need,
                "available_models": available,
                "prompt_to_owner": "",
                "skill": skill_name,
                "purpose": purpose,
            }

    # Nothing matched anywhere in this chain
    chain_summary = " → ".join(e["label"] for e in chain)
    prompt = (
        f"I cannot find a model for {skill_name or 'this skill'} "
        f"(tier: {purpose_tier} / context: {context_need}"
        f"{', ' + purpose if purpose else ''}). "
        f"I looked for: {chain_summary}. "
        f"None are present in your openclaw.json. Anthropic models are excluded by policy.\n\n"
        f"Available models in your config: "
        f"{', '.join(available) if available else '(none discoverable)'}\n\n"
        f"Which model should I use for {skill_name or 'this skill'}? "
        f"Reply with the exact model ID (e.g. ollama/kimi-k2.7:cloud or ollama/deepseek-v4-pro:cloud). "
        f"The install will continue without this — I just need the answer before "
        f"wiring {skill_name or 'this skill'} for runtime use."
    )
    return {
        "model_id": None,
        "chain_position": 0,
        "position_label": "owner-input-required",
        "needs_owner_input": True,
        "purpose_tier": purpose_tier,
        "context_need": context_need,
        "available_models": available,
        "prompt_to_owner": prompt,
        "skill": skill_name,
        "purpose": purpose,
    }


# ─── Task-time selector (PLAN.md §4) ─────────────────────────────────────────

# Difficulty classifier (PLAN.md §4.2). difficulty -> purpose tier.
_HARD_SIGNALS = (
    "strategy", "architect", "architecture", "multi-step", "roadmap",
    "legal", "financial", "compliance", "analyze", "analysis", "design",
    "qc ", "quality control", "audit", "synthesize", "reasoning", "plan",
    "evaluate", "diagnose", "investigate", "restructure",
)
_SIMPLE_SIGNALS = (
    "classify", "tag", "yes/no", "yes or no", "format", "rename", "lookup",
    "canned", "acknowledge", "confirm receipt", "label", "categorize",
    "extract field", "short reply",
)

# Modality inference (PLAN.md §4.3).
_VISION_SIGNALS = (
    "image", "screenshot", "slide", "photo", "look at", "visual qc",
    "ocr", "diagram", "thumbnail", "logo", "mockup", "review the design",
    "see the", "picture",
)
_IMAGE_GEN_SIGNALS = (
    "generate an image", "create an image", "make an image", "design a graphic",
    "produce a logo", "render an image", "generate artwork", "create a thumbnail",
    "image generation",
)
_VIDEO_SIGNALS = ("generate a video", "produce a video", "edit the video", "render video", "video generation")
_AUDIO_GEN_SIGNALS = ("voiceover", "text-to-speech", "tts", "narration", "generate audio", "produce audio")
_AUDIO_TX_SIGNALS = ("transcribe", "transcription", "caption the audio", "speech-to-text")


def classify_difficulty(text: str, input_chars: Optional[int] = None) -> str:
    """Classify task difficulty -> 'hard' | 'medium' | 'simple' (PLAN.md §4.2)."""
    t = (text or "").lower()
    if input_chars is not None and input_chars > 50_000:
        return "hard"
    if any(sig in t for sig in _HARD_SIGNALS):
        return "hard"
    if any(sig in t for sig in _SIMPLE_SIGNALS):
        return "simple"
    return "medium"


def difficulty_to_tier(difficulty: str) -> str:
    return {"hard": "heavy", "medium": "mid", "simple": "fast"}.get(difficulty, "mid")


def infer_modality(text: str) -> str:
    """Determine the REQUIRED modality of a task (PLAN.md §4.3). HARD constraint."""
    t = (text or "").lower()
    if any(sig in t for sig in _IMAGE_GEN_SIGNALS):
        return "image_generation"
    if any(sig in t for sig in _VIDEO_SIGNALS):
        return "video_generation"
    if any(sig in t for sig in _AUDIO_GEN_SIGNALS):
        return "audio_generation"
    if any(sig in t for sig in _AUDIO_TX_SIGNALS):
        return "audio_transcription"
    if any(sig in t for sig in _VISION_SIGNALS):
        return "vision"
    return "text"


def _cost_band(model: dict) -> int:
    """Rank a model's cost for the cheapest-of-equal tie-break. Lower = cheaper.

    `model` may be a dict carrying input/output cost-per-million, or just an id.
    Falls back to a neutral band when no cost data is present.
    """
    if not isinstance(model, dict):
        return 2
    cost = model.get("input_cost_per_million")
    if cost is None:
        cost = model.get("cost")
    if cost is None:
        return 2  # neutral / unknown
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return 2
    if cost <= 0:
        return 0       # free
    if cost < 1.0:
        return 1       # low
    if cost < 5.0:
        return 2       # mid
    return 3           # high


def select_task_model(
    task_text: str = "",
    department: str = "",
    required_modality: Optional[str] = None,
    difficulty: Optional[str] = None,
    sop_model_pin: Optional[str] = None,
    input_chars: Optional[int] = None,
    inventory: Optional[list] = None,
    openclaw_json_path: Optional[str] = None,
) -> dict:
    """Task-time selector (PLAN.md §4 + §5 precedence).

    Resolution order (highest wins):
      1. SOP pin (validated — still gated; PLAN.md §5)
      2. Task-time cascade over modality-filtered candidates (this function)
      (role override + dept default are handled by the CC resolver / build side)

    Returns a dict including model_id, tier (1/2/3), modelSource, required_modality,
    difficulty, chain_position, candidates_considered, needs_owner_input.
    """
    # Step A — classify difficulty + modality
    if difficulty is None:
        difficulty = classify_difficulty(task_text, input_chars)
    if required_modality is None:
        required_modality = infer_modality(task_text)
    tier_purpose = difficulty_to_tier(difficulty)

    # Build available inventory
    if inventory is None:
        cfg = _load_openclaw_config(openclaw_json_path)
        inventory = _list_available_models(cfg)
    # Normalize inventory to a list of model ids (accept dicts too)
    inv_ids = []
    for m in inventory or []:
        if isinstance(m, str):
            inv_ids.append(m)
        elif isinstance(m, dict) and m.get("id"):
            inv_ids.append(m["id"])
    inv_ids = [m for m in inv_ids if not _is_forbidden(m)]
    # The bare free sentinel (openrouter/free, "free") is NEVER a real,
    # resolvable model — it is the exact bug this selector exists to kill. Drop
    # it from the candidate pool so it can never be chosen (a genuine `*:free`
    # slug like `vendor/model:free` is still allowed as a Tier-3 last resort).
    inv_ids = [m for m in inv_ids if m.strip().lower() not in FREE_SENTINELS]

    # Step 1 — SOP pin WINS (still validated by the gate; here we just honor it
    # if it is present, non-forbidden, in inventory, and modality-appropriate).
    if sop_model_pin:
        pin = sop_model_pin.strip()
        pin_ok = (
            pin.lower() not in FREE_SENTINELS
            and not _is_forbidden(pin)
            and (not inv_ids or pin in inv_ids)
            and model_has_modality(pin, required_modality)
        )
        if pin_ok:
            return {
                "model_id": pin,
                "tier": tier_of_model(pin),
                "modelSource": "sop_pin",
                "required_modality": required_modality,
                "difficulty": difficulty,
                "chain_position": 0,
                "candidates_considered": [pin],
                "needs_owner_input": False,
                "prompt_to_owner": "",
            }
        # An invalid pin does NOT silently fall through to free — it surfaces.
        return {
            "model_id": None,
            "tier": 0,
            "modelSource": "sop_pin_invalid",
            "required_modality": required_modality,
            "difficulty": difficulty,
            "chain_position": 0,
            "candidates_considered": [pin],
            "needs_owner_input": True,
            "prompt_to_owner": (
                f"SOP pin '{pin}' is invalid (forbidden, missing from inventory, "
                f"or wrong modality for required '{required_modality}'). "
                f"Pick a model present in your inventory with the right modality."
            ),
        }

    # Step C — walk the cascade over modality-filtered, available candidates.
    # Modality is a HARD pre-filter applied BEFORE the cascade (PLAN.md §4.3).
    modality_ok = [m for m in inv_ids if model_has_modality(m, required_modality)]
    considered = list(modality_ok)

    # Within the difficulty-selected purpose chain, prefer the existing
    # version-aware chain ordering, but enforce the tier cascade as the outer
    # loop so Tier 1 always beats Tier 2 beats Tier 3.
    chain = CHAINS.get(tier_purpose, CHAINS["mid"]).get("normal", [])
    for cascade_tier in (TIER_OLLAMA_CLOUD, TIER_OPENROUTER_OSS, TIER_FREE):
        tier_pool = [m for m in modality_ok if tier_of_model(m) == cascade_tier]
        if not tier_pool:
            continue
        # (a) prefer a model that matches a known chain slot (highest version)
        for idx, entry in enumerate(chain, start=1):
            match = _best_match_in_position(tier_pool, entry)
            if match:
                return {
                    "model_id": match,
                    "tier": cascade_tier,
                    "modelSource": "task_selector",
                    "required_modality": required_modality,
                    "difficulty": difficulty,
                    "chain_position": idx,
                    "position_label": entry["label"],
                    "candidates_considered": considered,
                    "needs_owner_input": False,
                    "prompt_to_owner": "",
                }
        # (b) no chain slot matched, but the tier has modality-correct models:
        #     pick deterministically (sorted) — effectiveness already satisfied
        #     by modality + tier; ties broken by lowest cost band then name.
        best = sorted(tier_pool, key=lambda m: (_cost_band(m), m))[0]
        return {
            "model_id": best,
            "tier": cascade_tier,
            "modelSource": "task_selector",
            "required_modality": required_modality,
            "difficulty": difficulty,
            "chain_position": 0,
            "position_label": "tier-modality-match",
            "candidates_considered": considered,
            "needs_owner_input": False,
            "prompt_to_owner": "",
        }

    # Specialized-modality terminal pool: image/video/audio-generation and
    # transcription models frequently live on providers that are NOT chat-cascade
    # tiers (e.g. a dedicated Ollama Cloud image model, Fal, Replicate). If the
    # task needs such a modality and a modality-correct model exists that simply
    # didn't classify into T1/T2/T3, select it rather than blocking — it is still
    # a real, modality-appropriate, non-forbidden, in-inventory model. (Tier 1
    # Ollama Cloud generation models already win above; this only catches the
    # non-cascade providers.) Text tasks NEVER reach here — they always have a
    # cascade tier — so this never silently downgrades a chat task.
    SPECIALIZED = {"image_generation", "video_generation",
                   "audio_generation", "audio_transcription"}
    if required_modality in SPECIALIZED and modality_ok:
        best = sorted(modality_ok, key=lambda m: (_cost_band(m), m))[0]
        return {
            "model_id": best,
            "tier": tier_of_model(best),
            "modelSource": "task_selector",
            "required_modality": required_modality,
            "difficulty": difficulty,
            "chain_position": 0,
            "position_label": "specialized-modality-match",
            "candidates_considered": considered,
            "needs_owner_input": False,
            "prompt_to_owner": "",
        }

    # Nothing modality-appropriate in any tier — NEVER return a free literal.
    return {
        "model_id": None,
        "tier": 0,
        "modelSource": "needs_owner_input",
        "required_modality": required_modality,
        "difficulty": difficulty,
        "chain_position": 0,
        "candidates_considered": considered,
        "needs_owner_input": True,
        "prompt_to_owner": (
            f"No model in your inventory satisfies required modality "
            f"'{required_modality}' for this {difficulty} task "
            f"(department: {department or 'unknown'}). "
            f"A {required_modality} task MUST run on a {required_modality}-capable "
            f"model — a text-only model is never eligible. "
            f"Add a {required_modality}-capable model (Ollama Cloud preferred, "
            f"then OpenRouter open-source) and re-run."
        ),
    }


def resolve_dept_default_model(
    dept_canonical: str,
    inventory: Optional[list] = None,
    openclaw_json_path: Optional[str] = None,
) -> dict:
    """Build-time Layer-1 dept default (PLAN.md §3.2).

    Looks up the department's suitability (tier + baseline modality) and resolves
    a concrete model from the client inventory via the cascade. Never returns the
    free sentinel; returns needs_owner_input if no suitable model exists.
    """
    suit_map = load_suitability_map()
    depts = suit_map.get("departments", {})
    suit = depts.get(dept_canonical) or suit_map.get("default", {"tier": "mid", "modality": ["text"]})
    tier = suit.get("tier", "mid")
    modality_list = suit.get("modality", ["text"])
    # Pick the strongest HARD modality the dept needs as the pre-filter key.
    hard = {"vision", "image_generation", "video_generation",
            "audio_generation", "audio_transcription", "audio_input"}
    required = next((m for m in modality_list if m in hard), "text")
    # Reuse the task selector machinery (no SOP pin, dept difficulty == tier).
    diff = {"heavy": "hard", "mid": "medium", "fast": "simple"}.get(tier, "medium")
    result = select_task_model(
        task_text="",
        department=dept_canonical,
        required_modality=required,
        difficulty=diff,
        inventory=inventory,
        openclaw_json_path=openclaw_json_path,
    )
    result["dept"] = dept_canonical
    result["suitability_tier"] = tier
    result["suitability_modality"] = modality_list
    return result


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Select the best available model for an OpenClaw skill."
    )
    parser.add_argument("--skill", default="", help="Skill name (for logs/prompts)")
    parser.add_argument("--purpose-tier", choices=("heavy", "mid", "fast"),
                        default="heavy",
                        help="heavy=Kimi-first reasoning chain (default); "
                             "mid=Minimax/Mimo chain; fast=DeepSeek-flash/Gemini-lite chain")
    parser.add_argument("--context-need", choices=("normal", "large", "huge"),
                        default="normal",
                        help="normal=fits Kimi 262K ctx (default, Kimi preferred); "
                             "large=>800K chars, DeepSeek-pro 1M ctx preferred; "
                             "huge=>3M chars, DeepSeek-pro only")
    parser.add_argument("--input-chars", type=int, default=None,
                        help="Optional input size in chars; overrides --context-need "
                             "(< 800K = normal, 800K-3M = large, > 3M = huge)")
    parser.add_argument("--purpose", default="", help="Free-text description")
    parser.add_argument("--config", default=None, help="Path to openclaw.json")
    # ── Intelligent Model Selector modes (v12.15.0) ──
    parser.add_argument("--mode", choices=("skill", "task", "dept-default"),
                        default="skill",
                        help="skill=legacy purpose-tier chain (default); "
                             "task=task-time selector (modality+difficulty+cascade); "
                             "dept-default=Layer-1 build-time dept default model")
    parser.add_argument("--task-text", default="",
                        help="[task mode] task title+description for classification")
    parser.add_argument("--department", default="",
                        help="[task/dept-default mode] canonical department slug")
    parser.add_argument("--required-modality", default=None,
                        help="[task mode] override inferred modality "
                             "(text|vision|image_generation|video_generation|"
                             "audio_generation|audio_transcription)")
    parser.add_argument("--difficulty", default=None,
                        choices=("hard", "medium", "simple"),
                        help="[task mode] override inferred difficulty")
    parser.add_argument("--sop-model-pin", default=None,
                        help="[task mode] SOP-pinned model id (wins if valid)")
    parser.add_argument(
        "--format",
        choices=("json", "id", "prompt"),
        default="json",
    )
    args = parser.parse_args()

    if args.mode == "task":
        result = select_task_model(
            task_text=args.task_text or args.purpose,
            department=args.department,
            required_modality=args.required_modality,
            difficulty=args.difficulty,
            sop_model_pin=args.sop_model_pin,
            input_chars=args.input_chars,
            openclaw_json_path=args.config,
        )
    elif args.mode == "dept-default":
        result = resolve_dept_default_model(
            dept_canonical=args.department,
            openclaw_json_path=args.config,
        )
    else:
        result = select_model_for_skill(
            skill_name=args.skill,
            purpose_tier=args.purpose_tier,
            context_need=args.context_need,
            input_chars=args.input_chars,
            purpose=args.purpose,
            openclaw_json_path=args.config,
        )

    if args.format == "id":
        print(result["model_id"] or "")
        sys.exit(0 if result["model_id"] else 2)
    elif args.format == "prompt":
        print(result["prompt_to_owner"])
        sys.exit(0 if not result["needs_owner_input"] else 2)
    else:
        print(json.dumps(result, indent=2))
        sys.exit(0 if not result["needs_owner_input"] else 2)


if __name__ == "__main__":
    main()
