#!/usr/bin/env python3
"""auto_update_repair.py -- the repair agent's model chain for the Tue/Fri/Sun auto-update.

When an auto-update run fails its health gate, the runner (fleet_refresh_runner.heal_and_gate) asks this module
which of the runner's own, already-tested repair actions to run next. The model never gets a shell: it can only
pick from ALLOWED_ACTIONS, and everything else it says is dropped. That keeps a repair model's mistake from being
able to touch credentials, models, providers, departments or client files.

Model chain (the LATEST DeepSeek Flash), first one available on THIS box wins:
  1. Ollama Cloud    DeepSeek Flash
  2. OpenRouter      DeepSeek Flash
  3. DeepSeek Direct deepseek-v4-flash
"Available" means a credential for that provider already resolves from the box's own config / env / secrets
stores (shared-utils/llm_score.py resolvers). This module never adds, changes, writes or prints a key, and never
changes the client's primary model: it only reads the provider config and makes one chat call per attempt.
No provider available means NO_DEEPSEEK: the runner skips repair and rolls back if the box is unhealthy.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ALLOWED_ACTIONS = ("rerun:pull-onboarding", "rerun:pull-cc", "rebuild-cc", "rerun:restart-cc", "restart-gateway")
MAX_ACTIONS_PER_ATTEMPT = 3

# (provider, host fragment in a provider baseUrl, default model id used only when the box config lists none)
CHAIN_SPEC = (
    ("ollama-cloud", "ollama.com", "deepseek-v4.1-flash:cloud"),
    ("openrouter", "openrouter.ai", "deepseek/deepseek-v4.1-flash"),
    ("deepseek-direct", "deepseek.com", "deepseek-v4-flash"),
)

_SECRETISH = (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{25,}\b"), re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
              re.compile(r"\b[A-Za-z0-9_-]{40,}\b"))


def scrub(text: str) -> str:
    for rx in _SECRETISH:
        text = rx.sub("<redacted>", text)
    return text


def _version_key(model_id: str) -> tuple:
    m = re.search(r"v?(\d+(?:\.\d+)*)", model_id.lower().split("deepseek", 1)[-1])
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def configured_flash_model(root: Path, host_fragment: str) -> str:
    """Highest-version DeepSeek Flash id the box's own provider block lists for this host, else ''."""
    try:
        cfg = json.loads((Path(root) / "openclaw.json").read_text())
    except (OSError, ValueError):
        return ""
    providers = ((cfg.get("models") or {}).get("providers") or {})
    entries = providers.values() if isinstance(providers, dict) else providers
    best = ""
    for entry in entries:
        if not isinstance(entry, dict) or host_fragment not in str(entry.get("baseUrl") or entry.get("base_url") or ""):
            continue
        for m in entry.get("models") or []:
            mid = str(m.get("id") if isinstance(m, dict) else m or "")
            low = mid.lower()
            if "deepseek" in low and "flash" in low and (not best or _version_key(mid) > _version_key(best)):
                best = mid
    return best


def _keys_and_url(provider: str):
    import llm_score  # type: ignore  (same directory; resolvers read the box's own stores)
    if provider == "ollama-cloud":
        return llm_score.ollama_cloud_api_keys(), llm_score.ollama_cloud_chat_url(), {}
    if provider == "openrouter":
        return llm_score.openrouter_api_keys(), llm_score.OPENROUTER_CHAT_URL, {"reasoning": {"exclude": True}}
    return llm_score.deepseek_direct_api_keys(), llm_score.DEEPSEEK_DIRECT_CHAT_URL, {}


def provider_chain(root: Path, resolver=_keys_and_url) -> list[dict]:
    """Available steps in order. A step is available only when a key already resolves for its provider.
    Key values stay in memory in the step dict and are never logged or written."""
    out = []
    for provider, host, default in CHAIN_SPEC:
        try:
            keys, url, extra = resolver(provider)
        except Exception:               # an unreadable provider is simply unavailable
            continue
        if not keys:
            continue
        model = configured_flash_model(root, host) or default
        out.append({"provider": provider, "model": model, "label": f"{provider}/{model}", "url": url,
                    "keys": list(keys), "extra": extra})
    return out


def _prompt(failing: dict, tried: list) -> str:
    return (
        "An OpenClaw box update just failed its health gate. Choose which repair actions to run next. "
        "You cannot run commands; you can only pick from this exact list: "
        + json.dumps(list(ALLOWED_ACTIONS)) + ".\n"
        "Rules: never restart the gateway unless a gateway check is failing; rebuild-cc only for a Command Center "
        "failure; rerun:pull-onboarding only for a content integrity failure. Pick at most "
        f"{MAX_ACTIONS_PER_ATTEMPT}, in the order to run them.\n"
        f"Failing checks (name: detail): {scrub(json.dumps(failing, sort_keys=True))[:1500]}\n"
        f"Attempts already made: {scrub(json.dumps(tried))[:1200]}\n"
        'Reply with ONLY a JSON object like {"actions": ["restart-gateway"]}.')


def parse_actions(text: str) -> list[str]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return []
    try:
        raw = (json.loads(m.group(0)) or {}).get("actions") or []
    except ValueError:
        return []
    seen, out = set(), []
    for a in raw if isinstance(raw, list) else []:
        if isinstance(a, str) and a in ALLOWED_ACTIONS and a not in seen:
            seen.add(a)
            out.append(a)
    return out[:MAX_ACTIONS_PER_ATTEMPT]


def _call(step: dict, prompt: str) -> str:
    import llm_score  # type: ignore
    body = {"model": step["model"], "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1, "max_tokens": 300}
    body.update(step.get("extra") or {})
    last = None
    for key in step["keys"]:
        try:
            payload = llm_score._post_chat(step["url"], {"Content-Type": "application/json",
                                                         "Authorization": f"Bearer {key}"}, body, timeout=60)
            return llm_score._extract_message(payload)
        except Exception as e:           # next key, then next provider; the error never carries a key
            last = e
    raise RuntimeError(type(last).__name__ if last else "no key")


def plan_actions(failing: dict, tried: list, chain: list[dict], call=_call) -> dict:
    """{"model": label|None, "actions": [...], "error": str|None}. Walks the chain; the first provider that
    answers with parseable actions wins. A provider that errors or answers nonsense falls through to the next."""
    errors = []
    for step in chain:
        try:
            text = call(step, _prompt(failing, tried))
        except Exception as e:
            errors.append(f"{step['label']}: {type(e).__name__}")
            continue
        actions = parse_actions(text)
        if actions:
            return {"model": step["label"], "actions": actions, "error": None}
        errors.append(f"{step['label']}: no usable actions")
    return {"model": None, "actions": [], "error": "; ".join(errors) or "no provider available"}
