"""
select_model.py — Smart model selector for OpenClaw skills.

Used by Skill 22 (Book-to-Persona), Skill 15 (Team Management), Skill 23 (AI
Workforce Blueprint), and any other skill that needs a model recommendation
that auto-adapts to whatever the client has installed.

Three purpose-tier chains (v9.5.0):

  --purpose-tier heavy   (Heavy reasoning / heavy thinking — default)
    1. ollama/kimi-k*:cloud           (Ollama Cloud Kimi 2.6+, thinking=high)
    2. openrouter/moonshot/kimi-k*    (OpenRouter Kimi, thinking=high)
    3. ollama/deepseek-v*-pro:cloud   (Ollama Cloud DeepSeek V4-pro)
    4. openrouter/deepseek/deepseek-v*-pro  (OpenRouter DeepSeek V4-pro, thinking=high)
    5. codex/gpt-* OR openai-codex/gpt-*    (OAuth GPT — latest version)

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


# Purpose-tier chains. Each entry is a regex with a version capture group.
# Position 1 in a chain = most preferred.
CHAINS = {
    "heavy": [
        {"label": "Ollama Cloud Kimi (thinking=high)",
         "pattern": re.compile(r"^ollama/kimi-k(\d+(?:\.\d+)*)(?::cloud)?$")},
        {"label": "OpenRouter Kimi (thinking=high)",
         "pattern": re.compile(r"^openrouter/moonshot(?:ai)?/kimi-k(\d+(?:\.\d+)*)$")},
        {"label": "Ollama Cloud DeepSeek V*-pro",
         "pattern": re.compile(r"^ollama/deepseek-v(\d+(?:\.\d+)*)-pro(?::cloud)?$")},
        {"label": "OpenRouter DeepSeek V*-pro (thinking=high)",
         "pattern": re.compile(r"^(?:openrouter/)?deepseek/deepseek-v(\d+(?:\.\d+)*)-pro$")},
        {"label": "OAuth GPT (latest)",
         "pattern": re.compile(r"^(?:openai-)?codex/gpt-(\d+(?:\.\d+)*)(?:-[a-z]+)?$")},
    ],
    "mid": [
        {"label": "Ollama Cloud Minimax",
         "pattern": re.compile(r"^ollama/minimax-m(\d+(?:\.\d+)*)(?::cloud)?$")},
        {"label": "OpenRouter Mimo Pro (thinking=high)",
         "pattern": re.compile(r"^openrouter/xiaomi/mimo-v(\d+(?:\.\d+)*)-pro$")},
    ],
    "fast": [
        {"label": "Ollama Cloud DeepSeek V*-flash",
         "pattern": re.compile(r"^ollama/deepseek-v(\d+(?:\.\d+)*)-flash(?::cloud)?$")},
        {"label": "OpenRouter DeepSeek V*-flash",
         "pattern": re.compile(r"^(?:openrouter/)?deepseek/deepseek-v(\d+(?:\.\d+)*)-flash$")},
        {"label": "OpenRouter Gemini Flash Lite",
         "pattern": re.compile(r"^(?:openrouter/)?google/gemini-(\d+(?:\.\d+)*)-flash-lite(?:-preview)?$")},
    ],
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


def select_model_for_skill(
    skill_name: str = "",
    purpose_tier: str = "heavy",
    purpose: str = "",
    openclaw_json_path: Optional[str] = None,
) -> dict:
    """
    Select the best available model for a skill.

    Args:
      skill_name:     For logs / prompts
      purpose_tier:   "heavy" | "mid" | "fast"  (default: heavy)
      purpose:        Free-text description of what the model is for
      openclaw_json_path: Path override

    Returns dict with:
      model_id, chain_position, position_label, needs_owner_input,
      purpose_tier, available_models, prompt_to_owner, skill, purpose
    """
    if purpose_tier not in CHAINS:
        purpose_tier = "heavy"

    cfg = _load_openclaw_config(openclaw_json_path)
    available = _list_available_models(cfg)
    chain = CHAINS[purpose_tier]

    for idx, entry in enumerate(chain, start=1):
        match = _best_match_in_position(available, entry)
        if match:
            return {
                "model_id": match,
                "chain_position": idx,
                "position_label": entry["label"],
                "needs_owner_input": False,
                "purpose_tier": purpose_tier,
                "available_models": available,
                "prompt_to_owner": "",
                "skill": skill_name,
                "purpose": purpose,
            }

    # Nothing matched anywhere in this chain
    chain_summary = " → ".join(e["label"] for e in chain)
    prompt = (
        f"I cannot find a model for {skill_name or 'this skill'} "
        f"(tier: {purpose_tier}{', ' + purpose if purpose else ''}). "
        f"I looked for: {chain_summary}. "
        f"None are present in your openclaw.json. Anthropic models are excluded by policy (too expensive).\n\n"
        f"Available models in your config: "
        f"{', '.join(available) if available else '(none discoverable)'}\n\n"
        f"Which model should I use for {skill_name or 'this skill'}? "
        f"Reply with the exact model ID (e.g. ollama/kimi-k2.7:cloud). "
        f"The install will continue without this — I just need the answer before "
        f"wiring {skill_name or 'this skill'} for runtime use."
    )
    return {
        "model_id": None,
        "chain_position": 0,
        "position_label": "owner-input-required",
        "needs_owner_input": True,
        "purpose_tier": purpose_tier,
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
