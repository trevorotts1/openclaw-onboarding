"""
select_model.py — Smart model selector for OpenClaw skills.

Used by Skill 22 (Book-to-Persona), Skill 15 (Team Management), Skill 23 (AI
Workforce Blueprint), and any other skill that needs a model that
auto-adapts to whatever the client has installed.

MODEL RESOLUTION (client-choice doctrine, D3). The client SELECTS their
model; this module never prescribes one by name. Resolution order:

  1. An explicit client choice for this call (the explicit_model argument /
     --model CLI flag, or a SOP model pin in select_task_model()).
  2. The client's configured default model (agents.defaults.model in their
     own openclaw.json) when it satisfies the tier's capability
     requirements.
  3. The best-ranked model among the models the CLIENT configured, ranked
     by the tier's capability requirements. Ranking criteria, in order:
     provider-route tier (see the cascade note below), preferred-capability
     fit, highest version number, lowest cost band, then model id. The
     ranking only ever chooses among the client's own configured models;
     it never imports a model the client did not configure.
  4. Nothing qualifies: the selector returns Tier 5 (owner-input-required)
     with a plain-English prompt asking the client which model to use. A
     box is never left silently model-less, and no named model is ever
     substituted silently.

PURPOSE TIERS are capability requirements, not family preferences. Any
client-configured model that satisfies them is eligible:

  --purpose-tier heavy   (Heavy reasoning / heavy thinking — default)
    Requires text. Prefers reasoning, long context, tool use.
    Large/huge context needs also REQUIRE long context.
  --purpose-tier mid     (Mid-tier reasoning — fast but capable)
    Requires text. Prefers reasoning and tool use.
  --purpose-tier fast    (Fast / cheap — bulk operations)
    Requires text.

CASCADE NOTE. The provider-route preference (Ollama Cloud first, then
OpenRouter open-source routes, then free routes) survives ONLY as a ranking
tie-break inside step 3, among models the client already configured. It is
not a resolution order and never substitutes for the client's choice or
configured default. A bare "free" default (the openrouter/free literal or
a *-free slug as an unconfigured default) is never a valid resolution; the
sovereignty gate rejects it.

CLASSIFICATION DATA. The slot patterns and CHAINS tables below classify
known model families by capability class and route tier (which models
support which work). They are retained for tier_of_model(),
capabilities_for_model() and existing callers. The selectors do NOT walk
CHAINS as a family preference order.

In every selection path: NEVER select Anthropic models. Hardcoded filter.

OLLAMA CLOUD ID SHAPES (ISSUE-08). The classification patterns match the
three shapes the fleet actually runs, not just the bare `:cloud` tag:

  ollama/deepseek-v4.1-flash:cloud          plain cloud tag
  ollama/deepseek-v4.1-flash:0813-cloud     DATE-tagged cloud build
  ollama/qwen3-vl:235b-cloud            size-tagged cloud build
  ollama-cloud/kimi-k2.6:cloud          ollama-cloud/ provider prefix

The `_OLLAMA` and `_CLOUD_TAG` anchors below carry that contract, which is the
same one tier_of_model already applied. A family suffix still does NOT match its
base family: `ollama/kimi-k2.7-code:cloud` is a code model, not the Kimi chat
slot, and stays unmatched by the Kimi pattern.

Example:
    >>> from select_model import select_model_for_skill
    >>> r = select_model_for_skill("book-to-persona", purpose_tier="heavy")
    >>> r["model_id"]   # the client's configured default, when it qualifies
    'ollama/kimi-k2.6:cloud'
    >>> r["chain_position"]
    0
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

# ─── Intelligent Model Selector ───────────────────────────────────────────────
# ROUTE-TIER CLASSIFICATION (PLAN.md §2), single source of truth for the
# route tier of a model id. tier_of_model() classifies; the ranking inside
# the selectors uses this ONLY as a tie-break among models the CLIENT
# configured, after the client's explicit choice and configured default
# (see MODEL RESOLUTION in the module docstring). It is not a preference
# cascade and never substitutes a model the client did not configure.
#
#   TIER 1 — Ollama Cloud   : ollama/*:cloud (baseUrl https://ollama.com/v1)
#   TIER 2 — OpenRouter OSS  : openrouter/<oss-vendor>/* (open-weight only)
#   TIER 3, Free            : *:free / pricingModel == 'free' (ranked last
#                              among configured models; a bare "free" default
#                              is never a valid resolution, see FREE_SENTINELS)
#
# A proprietary OpenRouter route (openrouter/openai/*, openrouter/google/*-pro,
# openrouter/anthropic/*) is NOT a Tier-2 open-source model. Anthropic is
# forbidden outright (FORBIDDEN_PREFIXES); other proprietary routes are not
# silently selected by the ranking.
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
    openrouter/deepseek/deepseek-v4.1-flash -> deepseek-v4.1-flash
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
    """Classify a model id into its provider-route tier (1/2/3).

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
    # `ollama/qwen3-vl:235b-cloud` or simple `ollama/deepseek-v4.1-flash:cloud`.
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


# Ollama Cloud id SHAPE anchors (ISSUE-08). Real fleet ids carry a DATE-tagged or
# size-tagged cloud tag (`:0813-cloud`, `:235b-cloud`) and may use the
# `ollama-cloud/` provider prefix, both of which tier_of_model already accepts.
# The chain patterns anchored `^ollama/...(?::cloud)?$` and so matched NONE of
# them, which silently emptied every Ollama slot in every chain. These two
# anchors bring the chain regexes to the SAME contract as tier_of_model.
#   _OLLAMA    : ollama/ or ollama-cloud/ provider prefix
#   _CLOUD_TAG : no tag, `:cloud`, or a compound `:<variant>-cloud` tag
_OLLAMA = r"^ollama(?:-cloud)?/"
_CLOUD_TAG = r"(?::(?:[a-z0-9.]+-)?cloud)?$"   # :cloud | :0813-cloud | :235b-cloud

# Pattern definitions — each slot in the chain gets a version-capturing regex.
KIMI_OLLAMA      = {"label": "Ollama Cloud Kimi (thinking=high) — smartest, 262K ctx",
                    "family": "kimi",
                    "providers": ("ollama/", "ollama-cloud/"),
                    "pattern": re.compile(_OLLAMA + r"kimi-k(\d+(?:\.\d+)*)" + _CLOUD_TAG)}
KIMI_OPENROUTER  = {"label": "OpenRouter Kimi (thinking=high) — 262K ctx",
                    "family": "kimi",
                    "pattern": re.compile(r"^openrouter/moonshot(?:ai)?/kimi-k(\d+(?:\.\d+)*)$")}
OAUTH_GPT        = {"label": "OAuth GPT (latest, subscription)",
                    "pattern": re.compile(r"^(?:openai-)?codex/gpt-(\d+(?:\.\d+)*)(?:-[a-z]+)?$")}
MIMO_OPENROUTER  = {"label": "OpenRouter Mimo Pro (thinking=high)",
                    "family": "mimo-pro",
                    "pattern": re.compile(r"^openrouter/xiaomi/mimo-v(\d+(?:\.\d+)*)-pro$")}
# F31: GLM slugs carry provider variant suffixes (-flash, -pro, -air, -lite,
# -preview, -thinking) and an optional :cloud tag (openrouter/z-ai/glm-5.3-flash).
# The old pattern accepted ONLY the bare version slug and REJECTED every suffixed
# real-world slug. The regex stays the fallback classifier; provider-verified
# full slugs from model-capabilities.json are accepted first (see
# load_verified_slugs / _best_match_in_position below).
GLM_OPENROUTER   = {"label": "OpenRouter GLM (thinking=high)",
                    "family": "glm",
                    "pattern": re.compile(r"^openrouter/(?:z-ai|zhipu(?:ai)?)/glm-?(\d+(?:\.\d+)*)(?:-(?:flash|pro|air|lite|preview|thinking))?(?::cloud)?$")}
MINIMAX_OLLAMA   = {"label": "Ollama Cloud Minimax",
                    "family": "minimax",
                    "providers": ("ollama/", "ollama-cloud/"),
                    "pattern": re.compile(_OLLAMA + r"minimax-m(\d+(?:\.\d+)*)" + _CLOUD_TAG)}
# ISSUE-08: GLM also ships on Ollama Cloud (ollama/glm-5.3:cloud). The chain had
# an OpenRouter GLM slot only, so a client whose GLM lives on Ollama Cloud had no
# GLM slot at all. Same suffix set as GLM_OPENROUTER; `providers` keeps this
# Tier-1 slot from claiming an OpenRouter GLM slug out of the verified inventory.
GLM_OLLAMA       = {"label": "Ollama Cloud GLM (thinking=high)",
                    "family": "glm",
                    "providers": ("ollama/", "ollama-cloud/"),
                    "pattern": re.compile(_OLLAMA + r"glm-?(\d+(?:\.\d+)*)"
                                          r"(?:-(?:flash|pro|air|lite|preview|thinking))?"
                                          + _CLOUD_TAG)}
DEEPSEEK_FLASH_OLLAMA     = {"label": "Ollama Cloud DeepSeek V*-flash",
                             "family": "deepseek-flash",
                             "providers": ("ollama/", "ollama-cloud/"),
                             "pattern": re.compile(_OLLAMA + r"deepseek-v(\d+(?:\.\d+)*)-flash" + _CLOUD_TAG)}
DEEPSEEK_FLASH_OPENROUTER = {"label": "OpenRouter DeepSeek V*-flash",
                             "family": "deepseek-flash",
                             "pattern": re.compile(r"^(?:openrouter/)?deepseek/deepseek-v(\d+(?:\.\d+)*)-flash$")}
# KEF001: DeepSeek V4 Pro no longer exists; its chain slots were removed. Flash (V4.1, 1M ctx)
# serves the large/huge-context chains.
GEMINI_FLASH_LITE         = {"label": "OpenRouter Gemini Flash Lite",
                             "family": "gemini-flash-lite",
                             "pattern": re.compile(r"^(?:openrouter/)?google/gemini-(\d+(?:\.\d+)*)-flash-lite(?:-preview)?$")}
# Gemini Pro pattern: classification entry for the Gemini Pro family
# (PRD §5.1 and §5.2 capability class).
GEMINI_PRO                = {"label": "OpenRouter Gemini Pro",
                             "family": "gemini-pro",
                             "pattern": re.compile(r"^(?:openrouter/)?google/gemini-(\d+(?:\.\d+)*)-pro(?:-preview)?$")}

# Purpose-tier classification tables. These tables classify known model
# families into capability classes per purpose tier and context need. They
# are CLASSIFICATION DATA, retained for tier_of_model(),
# capabilities_for_model(), _best_match_in_position() and existing callers.
# The selectors do NOT walk these lists as a family preference order:
# selection follows the client-choice resolution in the module docstring
# (explicit choice, then the client's configured default, then
# capability-ranked selection among the client's own configured models).
#
# Each table has 3 context-need variants:
#   normal, standard input window
#   large , input is 800K-3M chars; a long-context model is required
#   huge  , input is > 3M chars; the largest-context models only
CHAINS = {
    "heavy": {
        "normal": [
            KIMI_OLLAMA,
            KIMI_OPENROUTER,
            OAUTH_GPT,
            MIMO_OPENROUTER, GLM_OPENROUTER,
        ],
        # Large input (800K-3M chars): long context required
        "large": [
            DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER,
            OAUTH_GPT,
            KIMI_OLLAMA, KIMI_OPENROUTER,
        ],
        # Huge input (>3M chars): largest-context class only
        "huge": [
            DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER,
            OAUTH_GPT,
        ],
    },
    "mid": {
        "normal": [MINIMAX_OLLAMA, GLM_OLLAMA, MIMO_OPENROUTER, GLM_OPENROUTER],
        "large":  [MINIMAX_OLLAMA, GLM_OLLAMA, MIMO_OPENROUTER, GLM_OPENROUTER],
        "huge":   [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, OAUTH_GPT],
    },
    "fast": {
        "normal": [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_FLASH_LITE],
        "large":  [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_FLASH_LITE],
        "huge":   [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER],
    },

    # ─── Role-specific classification tables (PRD §5) ─────────────────────
    # These four tables map 1:1 to the audit's PRD §5 role specification.
    # Same status as the tier tables above: classification data only, not a
    # selection order. Role capability needs:
    #   orchestrator      , heavy reasoning (thinking=high)
    #   installer-subagent, long context for big skill files
    #   qc-subagent       , capable reasoning plus cheap bulk checks
    #   book-to-persona   , heavy reasoning over long inputs
    "orchestrator": {
        "normal": [
            KIMI_OLLAMA,
            KIMI_OPENROUTER,
            GEMINI_PRO,
            GEMINI_FLASH_LITE,
            OAUTH_GPT,
        ],
        "large": [KIMI_OLLAMA, KIMI_OPENROUTER, GEMINI_PRO, DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, OAUTH_GPT],
        "huge":  [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_PRO, OAUTH_GPT],
    },

    "installer-subagent": {
        "normal": [
            GEMINI_PRO,
            GEMINI_FLASH_LITE,
            OAUTH_GPT,
        ],
        "large": [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_PRO, OAUTH_GPT],
        "huge":  [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_PRO, OAUTH_GPT],
    },

    "qc-subagent": {
        "normal": [
            KIMI_OLLAMA,
            KIMI_OPENROUTER,
            GEMINI_FLASH_LITE,
        ],
        "large": [KIMI_OLLAMA, KIMI_OPENROUTER, DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER],
        "huge":  [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER],
    },

    "book-to-persona": {
        "normal": [
            KIMI_OLLAMA,
            KIMI_OPENROUTER,
            GEMINI_FLASH_LITE,
        ],
        "large": [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, KIMI_OLLAMA, KIMI_OPENROUTER, GEMINI_FLASH_LITE],
        "huge":  [DEEPSEEK_FLASH_OLLAMA, DEEPSEEK_FLASH_OPENROUTER, GEMINI_FLASH_LITE],
    },
}


# ─── Client-choice resolution (D3) ────────────────────────────────────────────
# Capability requirements per purpose tier. `required` capabilities are a hard
# gate for steps 2-3 of the resolution (module docstring); `preferred`
# capabilities only rank candidates. Requirements are expressed WITHOUT family
# names: any client-configured model that satisfies them is eligible.
TIER_REQUIREMENTS = {
    "heavy": {
        "normal": {"required": ("text",),
                   "preferred": ("reasoning", "long_context", "tool_use")},
        "large":  {"required": ("text", "long_context"),
                   "preferred": ("reasoning", "tool_use")},
        "huge":   {"required": ("text", "long_context"),
                   "preferred": ("reasoning",)},
    },
    "mid": {
        "normal": {"required": ("text",),
                   "preferred": ("reasoning", "tool_use")},
        "large":  {"required": ("text", "long_context"),
                   "preferred": ("reasoning", "tool_use")},
        "huge":   {"required": ("text", "long_context"),
                   "preferred": ("reasoning",)},
    },
    "fast": {
        "normal": {"required": ("text",), "preferred": ()},
        "large":  {"required": ("text", "long_context"), "preferred": ()},
        "huge":   {"required": ("text", "long_context"), "preferred": ()},
    },
}

# Role tiers resolve with the requirements of their capability class.
_ROLE_TIER_CLASS = {
    "orchestrator": "heavy",
    "installer-subagent": "heavy",
    "book-to-persona": "heavy",
    "qc-subagent": "mid",
}


def _requirements_for(purpose_tier: str, context_need: str) -> dict:
    """Capability requirements for a purpose tier + context need."""
    tier_class = _ROLE_TIER_CLASS.get(purpose_tier, purpose_tier)
    tiers = TIER_REQUIREMENTS.get(tier_class, TIER_REQUIREMENTS["mid"])
    return tiers.get(context_need, tiers["normal"])


def _meets_requirements(model_id: str, req: dict) -> bool:
    """True iff the model's capabilities cover the tier's REQUIRED set."""
    caps = set(capabilities_for_model(model_id))
    return all(c in caps for c in req.get("required", ()))


def _preferred_count(model_id: str, req: dict) -> int:
    caps = set(capabilities_for_model(model_id))
    return sum(1 for c in req.get("preferred", ()) if c in caps)


def _version_key(model_id: str) -> tuple:
    """First dotted version number in the provider-stripped slug, as a tuple."""
    bare = _strip_provider(model_id) or model_id
    m = re.search(r"(\d+(?:\.\d+)*)", bare)
    return _parse_version(m.group(1)) if m else (0,)


def _rank_candidates(models: list, req: dict) -> list:
    """Deterministically rank the CLIENT's own configured models.

    Criteria, primary first: route tier (tier_of_model, unclassified last),
    preferred-capability fit (desc), highest version (desc), lowest cost
    band, then model id. This ranking is a tie-break among models the client
    configured; it never imports a model the client did not configure.
    Implemented as successive stable sorts, last sort is primary.
    """
    ranked = sorted(models)                                        # id asc
    ranked.sort(key=lambda m: _cost_band(m))                       # cost asc
    ranked.sort(key=_version_key, reverse=True)                    # version desc
    ranked.sort(key=lambda m: -_preferred_count(m, req))           # fit desc
    ranked.sort(key=lambda m: tier_of_model(m) or 99)              # tier asc
    return ranked


def _configured_default_model(cfg: dict) -> Optional[str]:
    """The client's OWN configured default model id (agents.defaults.model).

    Accepts the canonical object form ({"primary": ...}) and a bare string.
    Returns None when no default is configured, or when the configured
    default is forbidden (the Anthropic filter applies to defaults too: a
    forbidden default is treated as unconfigured so the caller surfaces
    owner input rather than dispatching it).
    """
    if not isinstance(cfg, dict):
        return None
    defaults = (cfg.get("agents") or {}).get("defaults") or {}
    field = defaults.get("model")
    primary = None
    if isinstance(field, str):
        primary = field
    elif isinstance(field, dict):
        primary = field.get("primary") or field.get("model")
    if isinstance(primary, str) and primary.strip() and not _is_forbidden(primary):
        return primary.strip()
    return None


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

    # Both roster shapes: agents.entries (OpenClaw 2026.9.x) and agents.list[].
    _entries = agents.get("entries")
    _roster = list(_entries.values()) if isinstance(_entries, dict) else []
    _roster += agents.get("list", []) if isinstance(agents.get("list"), list) else []
    for entry in _roster:
        if isinstance(entry, dict):
            _take(entry.get("model"))
            _take((entry.get("subagents") or {}).get("model"))

    return [m for m in found if not _is_forbidden(m)]


_VERIFIED_SLUGS_CACHE = None


def load_verified_slugs() -> dict:
    """Load the provider-verified full-slug inventory (F31).

    Returns the `verified_slugs` object from model-capabilities.json:
      { "<provider>/<vendor/model-slug>": {"family": "...", "capabilities": [...]} }
    The inventory is DATA — adding a new model slug (e.g. glm-5.3-flash) needs
    only a JSON edit, never a selector-code change. The version-capturing regex
    per chain entry stays as the fallback classifier for slugs NOT in the
    verified inventory.
    """
    global _VERIFIED_SLUGS_CACHE
    if _VERIFIED_SLUGS_CACHE is None:
        cap_map = load_capability_map()
        _VERIFIED_SLUGS_CACHE = cap_map.get("verified_slugs", {})
    return _VERIFIED_SLUGS_CACHE


def slug_is_verified(model_id: str) -> bool:
    """True iff the full model id appears in the provider-verified slug inventory."""
    if not model_id:
        return False
    return model_id.strip().lower() in load_verified_slugs()


def _family_of(model_id: str) -> str:
    """Family for a verified slug from the inventory (or '' when unverified)."""
    entry = load_verified_slugs().get(model_id.strip().lower(), {})
    return entry.get("family", "")


def _best_match_in_position(models: list, chain_entry: dict) -> Optional[str]:
    """Highest-version model matching the chain entry — provider-verified slugs FIRST.

    F31 contract: "recognize provider-verified full slugs instead of selecting by
    version number alone." Pass 1 accepts any FULL slug that (a) is in the
    verified inventory with this entry's family and (b) carries one of the
    entry's `providers` prefixes when the entry declares them. Pass 2 is the
    legacy version-capturing regex for slugs not yet in the inventory.

    ISSUE-08: `providers` is the optional prefix guard. Two chain slots can share
    one family across different providers (the Ollama Cloud GLM slot and the
    OpenRouter GLM slot are both family `glm`), and a family-only pass 1 would let
    the Tier-1 slot claim the Tier-2 slug and mislabel it. An entry with no
    `providers` key behaves exactly as before.
    """
    family = chain_entry.get("family", "")
    providers = chain_entry.get("providers") or ()
    candidates = []
    verified_slugs = load_verified_slugs()
    for m in models:
        low = m.strip().lower()
        # Pass 1: provider-verified full slug of the entry's family (and, when the
        # entry declares them, one of its provider prefixes).
        if (family and low in verified_slugs
                and verified_slugs[low].get("family") == family
                and (not providers or low.startswith(tuple(providers)))):
            candidates.append((_parse_version(_strip_provider(m) or m), m))
            continue
        # Pass 2 — legacy version-capturing regex (fallback classifier).
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
    explicit_model: Optional[str] = None,
) -> dict:
    """
    Select the model for a skill, following the client-choice resolution
    (module docstring): explicit client choice, then the client's
    configured default model, then capability-ranked selection among the
    client's own configured models, then owner-input-required.

    Args:
      skill_name:     For logs / prompts
      purpose_tier:   "heavy" | "mid" | "fast"  (default: heavy)
      context_need:   "normal" | "large" | "huge"  (auto-derived from input_chars if given)
      input_chars:    Optional input size; if provided, overrides context_need
      purpose:        Free-text description
      openclaw_json_path: Path override
      explicit_model: A model id the client explicitly chose for this call

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
    req = _requirements_for(purpose_tier, context_need)

    def _ok(model_id, position, label):
        return {
            "model_id": model_id,
            "chain_position": position,
            "position_label": label,
            "needs_owner_input": False,
            "purpose_tier": purpose_tier,
            "context_need": context_need,
            "available_models": available,
            "prompt_to_owner": "",
            "skill": skill_name,
            "purpose": purpose,
        }

    def _needs_input(prompt):
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

    # Step 1, explicit client choice for this call. Honored when it is not
    # forbidden, not a bare free sentinel, and present in the client's
    # configuration (or when no configuration was discoverable to check
    # against). An unusable explicit choice surfaces as owner input, the
    # same way an invalid SOP pin does in select_task_model().
    if explicit_model:
        pick = explicit_model.strip()
        if (not _is_forbidden(pick)
                and pick.lower() not in FREE_SENTINELS
                and (not available or pick in available)):
            return _ok(pick, 0, "client explicit choice")
        return _needs_input(
            f"The model you chose for {skill_name or 'this skill'} "
            f"('{pick}') cannot be used: it is forbidden by policy, a bare "
            f"free default, or not present in your openclaw.json.\n\n"
            f"Available models in your config: "
            f"{', '.join(available) if available else '(none discoverable)'}\n\n"
            f"Which model should I use for {skill_name or 'this skill'}? "
            f"Reply with the exact model ID from your config."
        )

    # Step 2, the client's configured default model, when it satisfies
    # this tier's capability requirements.
    default_model = _configured_default_model(cfg)
    if (default_model and default_model in available
            and _meets_requirements(default_model, req)):
        return _ok(default_model, 0, "client configured default model")

    # Step 3, capability-ranked selection among the client's own
    # configured models. The configured default, when present but not
    # requirement-satisfying, is not eligible here either: eligibility is
    # the tier's required capability set.
    eligible = [m for m in available if _meets_requirements(m, req)]
    ranked = _rank_candidates(eligible, req)
    if ranked:
        return _ok(ranked[0], 1, "capability match")

    # Step 4, nothing qualifies: ask the client. Never substitute a named
    # model silently, and never leave the box silently model-less.
    required_text = ", ".join(req.get("required", ("text",)))
    prompt = (
        f"I cannot find a usable model for {skill_name or 'this skill'} "
        f"(tier: {purpose_tier} / context: {context_need}"
        f"{', ' + purpose if purpose else ''}). "
        f"This tier needs a model with these capabilities: {required_text}. "
        f"None of the models in your openclaw.json qualifies, and no "
        f"configured default model is set. Anthropic models are excluded by policy.\n\n"
        f"Available models in your config: "
        f"{', '.join(available) if available else '(none discoverable)'}\n\n"
        f"Which model should I use for {skill_name or 'this skill'}? "
        f"Reply with the exact model ID from your config, or set a default "
        f"model in agents.defaults.model and re-run. "
        f"The install will continue without this — I just need the answer before "
        f"wiring {skill_name or 'this skill'} for runtime use."
    )
    return _needs_input(prompt)


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
      1. SOP pin (the client's own pinned choice, validated, still gated;
         PLAN.md §5)
      2. The client's configured default model, when the config was loaded
         here and the default is modality-appropriate and meets the tier's
         capability requirements
      3. Capability-ranked selection over modality-filtered candidates
         from the client's own configured inventory (this function)
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
    cfg = None
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

    # Step C, resolve over modality-filtered, available candidates (D3).
    # Modality is a HARD pre-filter applied BEFORE ranking (PLAN.md §4.3).
    modality_ok = [m for m in inv_ids if model_has_modality(m, required_modality)]
    considered = list(modality_ok)

    # Inside this step: (1) the client's configured default model, when the
    # config was loaded here (an explicitly passed inventory carries no
    # default preference) and the default is in the pool and meets the
    # tier's capability requirements; (2) the best-ranked remaining
    # candidate. The route tier is the ranking's outer loop (Tier 1 beats
    # Tier 2 beats Tier 3) purely as a tie-break among the client's own
    # configured models; no family preference order is consulted.
    req = _requirements_for(tier_purpose, "normal")
    cfg_default = _configured_default_model(cfg) if cfg is not None else None
    for cascade_tier in (TIER_OLLAMA_CLOUD, TIER_OPENROUTER_OSS, TIER_FREE):
        tier_pool = [m for m in modality_ok if tier_of_model(m) == cascade_tier]
        if not tier_pool:
            continue
        if (cfg_default and cfg_default in tier_pool
                and _meets_requirements(cfg_default, req)):
            return {
                "model_id": cfg_default,
                "tier": cascade_tier,
                "modelSource": "task_selector",
                "required_modality": required_modality,
                "difficulty": difficulty,
                "chain_position": 0,
                "position_label": "client configured default model",
                "candidates_considered": considered,
                "needs_owner_input": False,
                "prompt_to_owner": "",
            }
        # Eligibility is the tier's required capability set; when no pool
        # member meets it, the whole modality-correct pool stays eligible
        # (modality was already hard-filtered above).
        eligible = [m for m in tier_pool if _meets_requirements(m, req)] or tier_pool
        best = _rank_candidates(eligible, req)[0]
        return {
            "model_id": best,
            "tier": cascade_tier,
            "modelSource": "task_selector",
            "required_modality": required_modality,
            "difficulty": difficulty,
            "chain_position": 1,
            "position_label": "capability match",
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
            f"Ask the client which model to use, add a {required_modality}-capable "
            f"model to the configuration, or set one as the configured default "
            f"model, and re-run."
        ),
    }


def resolve_dept_default_model(
    dept_canonical: str,
    inventory: Optional[list] = None,
    openclaw_json_path: Optional[str] = None,
) -> dict:
    """Build-time Layer-1 dept default (PLAN.md §3.2).

    Looks up the department's suitability (tier + baseline modality) and resolves
    a concrete model from the client inventory via the client-choice resolution
    (configured default first, then capability ranking). Never returns the
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
                        help="Capability tier: heavy=reasoning/planning/QC (default); "
                             "mid=general work (reasoning + tool use preferred); "
                             "fast=bulk lookups and classification (text only)")
    parser.add_argument("--context-need", choices=("normal", "large", "huge"),
                        default="normal",
                        help="normal=standard window (default); "
                             "large=>800K chars, long context required; "
                             "huge=>3M chars, long context required")
    parser.add_argument("--model", default=None,
                        help="[skill mode] explicit model id chosen by the client "
                             "for this call (resolution step 1)")
    parser.add_argument("--input-chars", type=int, default=None,
                        help="Optional input size in chars; overrides --context-need "
                             "(< 800K = normal, 800K-3M = large, > 3M = huge)")
    parser.add_argument("--purpose", default="", help="Free-text description")
    parser.add_argument("--config", default=None, help="Path to openclaw.json")
    # ── Intelligent Model Selector modes (v12.15.0) ──
    parser.add_argument("--mode", choices=("skill", "task", "dept-default"),
                        default="skill",
                        help="skill=purpose-tier capability resolution (default); "
                             "task=task-time selector (modality+difficulty+ranking); "
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
            explicit_model=args.model,
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
