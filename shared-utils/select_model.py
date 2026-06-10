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


# Hardcoded filter — never recommend these
FORBIDDEN_PREFIXES = (
    "anthropic/",
    "claude-opus",
    "claude-sonnet",
    "claude-haiku",
    "claude-3",
    "claude-4",
)


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
    mid = model_id.lower()
    return any(mid.startswith(p) or p in mid for p in FORBIDDEN_PREFIXES)


def _load_openclaw_config(path: Optional[str] = None) -> dict:
    candidates = [
        path,
        str(Path.home() / ".openclaw/openclaw.json"),
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
    parser.add_argument(
        "--format",
        choices=("json", "id", "prompt"),
        default="json",
    )
    args = parser.parse_args()

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
