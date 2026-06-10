#!/usr/bin/env python3
"""
OpenClaw Smart API Key Resolver

Unified API key resolution from openclaw.json env.vars, common .env files,
and live environment variables, with service aliases and fuzzy fallback.
"""

import json
import os
from typing import Dict, List, Optional

ENV_FILE_PATHS = [
    os.path.expanduser("~/clawd/secrets/.env"),
    os.path.expanduser("~/.openclaw/.env"),
    "/data/.openclaw/.env",
    os.path.expanduser("~/.env"),
    os.path.expanduser("~/.clawdbot/.env"),
]

OPENCLAW_JSON_PATHS = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    "/data/.openclaw/openclaw.json",
]

SERVICE_ALIASES: Dict[str, List[str]] = {
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY", "GOOGLE_GEMINI_API_KEY", "GCP_API_KEY", "GOOGLE_CLOUD_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY", "GOOGLE_AI_STUDIO_API_KEY"],
    "ghl": ["GOHIGHLEVEL_API_KEY", "GHL_API_KEY", "GOHIGHLEVEL_AGENCY_PIT"],
    "openrouter": ["OPENROUTER_API_KEY", "OPENROUTER_KEY", "OPEN_ROUTER_API_KEY"],
    "openai": ["OPENAI_API_KEY", "OPENAI_KEY"],
    "moonshot": ["MOONSHOT_API_KEY", "KIMI_API_KEY"],
    "kie": ["KIE_API_KEY", "KIE_KEY", "KIE_VIDEO_API_KEY", "KIE_API_KEY_IAFS"],
    "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
    "tavily": ["TAVILY_API_KEY", "TAVILY_KEY"],
    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "TG_BOT_TOKEN"],
    "perplexity": ["PERPLEXITY_API_KEY", "PERPLEXITY_KEY"],
    "n8n": ["N8N_API_KEY", "N8N_WEBHOOK_KEY", "N8N_KEY", "N8N_TOKEN"],
}

def _parse_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not os.path.isfile(path): return values
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"): continue
                if line.startswith("export "): line = line[7:].strip()
                if "=" not in line: continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values[key] = value
    except OSError: pass
    return values

def _load_openclaw_json_env_vars() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in OPENCLAW_JSON_PATHS:
        if not os.path.isfile(path): continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            env_vars = data.get("env", {}).get("vars", {})
            if isinstance(env_vars, dict):
                for key, value in env_vars.items():
                    if isinstance(value, str): values[key] = value
        except Exception: pass
    return values

def _build_env_map() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in ENV_FILE_PATHS: values.update(_parse_env_file(path))
    values.update(_load_openclaw_json_env_vars())
    values.update(dict(os.environ))
    return values

def resolve_key(service_or_key: str, *, exact: bool = False, default: Optional[str] = None) -> Optional[str]:
    env_map = _build_env_map()
    if exact: return env_map.get(service_or_key, default)
    normalized = service_or_key.lower().replace("-", "").replace("_", "")
    for candidate in SERVICE_ALIASES.get(normalized, []):
        value = env_map.get(candidate)
        if value: return value
    direct = env_map.get(service_or_key)
    if direct: return direct
    upper = service_or_key.upper()
    for suffix in ("_API_KEY", "_KEY", "_TOKEN", ""):
        candidate = f"{upper}{suffix}"
        value = env_map.get(candidate)
        if value: return value
    needle = service_or_key.lower()
    for key, value in env_map.items():
        if needle in key.lower() and value: return value
    return default
