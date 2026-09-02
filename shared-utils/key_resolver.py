#!/usr/bin/env python3
"""
OpenClaw Smart API Key Resolver

Unified API key resolution from openclaw.json env.vars, common .env files,
and live environment variables, with service aliases and fuzzy fallback.

FIX 67 — One secret-name canon: this module no longer restates its own
alias table. SERVICE_ALIASES is built at import from the canon in
shared-utils/secret_names.json ({"CANONICAL": ["ALIAS", ...]}) via
secret_helper.load_secret_names(); every family's canonical name and all
of its aliases resolve, on both platforms. Placeholder rejection goes
through secret_helper.looks_like_real_key — a value like PASTE_REAL_TOKEN
never resolves. If the canon file is missing or unreadable the loader
fails OPEN to the fallback tables below so a broken JSON can never take
key resolution down; placeholder rejection stays hard either way.
"""

import json
import os
from typing import Dict, List, Optional

try:
    from secret_helper import (
        alias_list as _canon_alias_list,
        is_placeholder as _canon_is_placeholder,
        load_secret_names as _canon_load,
        looks_like_real_key as _canon_looks_like_real_key,
    )
    _CANON_AVAILABLE = True
except Exception:  # canon module unreadable: fail open to local tables
    _CANON_AVAILABLE = False

ENV_FILE_PATHS = [
    os.path.expanduser("~/clawd/secrets/.env"),
    os.path.expanduser("~/.openclaw/secrets/.env"),
    os.path.expanduser("~/.openclaw/.env"),
    "/data/.openclaw/secrets/.env",
    "/data/.openclaw/.env",
    os.path.expanduser("~/.env"),
    os.path.expanduser("~/.clawdbot/.env"),
]

OPENCLAW_JSON_PATHS = [
    os.path.expanduser("~/.openclaw/openclaw.json"),
    "/data/.openclaw/openclaw.json",
]

# FIX 67 fallback service->aliases tables. Used ONLY when the canon cannot be
# loaded; the canon in secret_names.json is the source of truth. Do not add
# new aliases here — add them to secret_names.json.
_FALLBACK_SERVICE_ALIASES: Dict[str, List[str]] = {
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
    "brave": ["BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"],
    "ollama": ["OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY", "OLLAMA_KEY", "OLLAMA_TOKEN"],
    "agnes": ["AGNES_API_KEY", "AGNES_AI_API_KEY", "AGNES_KEY"],
}

# Service shorthand -> canonical canon head. Service lookups ("google",
# "ghl", "ollama" ...) expand to the canon family of the head.
_SERVICE_TO_CANONICAL: Dict[str, str] = {
    "google": "GOOGLE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ghl": "GOHIGHLEVEL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "kie": "KIE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "telegram": "TELEGRAM_BOT_TOKEN",
    "perplexity": "PERPLEXITY_API_KEY",
    "n8n": "N8N_API_KEY",
    "brave": "BRAVE_SEARCH_API_KEY",
    "ollama": "OLLAMA_CLOUD_API_KEY",
    "agnes": "AGNES_API_KEY",
    "moonshotcloud": "MOONSHOT_API_KEY",
    "convertflow": "GOHIGHLEVEL_API_KEY",
    "convertandflow": "GOHIGHLEVEL_API_KEY",
}


def _build_service_aliases() -> Dict[str, List[str]]:
    """Build SERVICE_ALIASES from the canon.

    For every canonical family in secret_names.json the family's canonical
    name and every alias become lookup keys mapping to the full alias list,
    plus service shorthands (google, ghl, brave, ...). Unknown services fall
    through to the fuzzy suffix walk in resolve_key as before.
    """
    aliases: Dict[str, List[str]] = {}
    if _CANON_AVAILABLE:
        canon = _canon_load()
        for canonical, family in canon.items():
            for name in family:
                # resolve_key normalizes the query by stripping "-" and "_"
                # before this dict lookup, so register BOTH the raw lowercase
                # form (exact env-var names as service keys) and the
                # underscore-stripped normalized form ("ollama_cloud_api_key"
                # and "ollamacloudapikey" both hit the family).
                aliases[name.lower()] = list(family)
                aliases[name.lower().replace("-", "").replace("_", "")] = list(family)
            head = _SERVICE_TO_CANONICAL_INVERSE.get(canonical)
            if head:
                aliases.setdefault(head, list(family))
    # Service shorthands whose canon family could not be found keep the
    # fallback list so nothing that resolved before stops resolving.
    for service, fallback in _FALLBACK_SERVICE_ALIASES.items():
        aliases.setdefault(service, fallback)
        aliases.setdefault(
            service.replace("-", "").replace("_", ""), fallback)
    return aliases


# Service shorthand -> canonical head (inverted once for the builder).
_SERVICE_TO_CANONICAL_INVERSE: Dict[str, str] = dict(_SERVICE_TO_CANONICAL)

SERVICE_ALIASES: Dict[str, List[str]] = _build_service_aliases()


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


def _is_placeholder(value: str, canonical: Optional[str] = None) -> bool:
    """Placeholder rejection. Canon-backed when secret_helper is importable,
    local twin otherwise — a PASTE_REAL_TOKEN-style value never passes."""
    if _CANON_AVAILABLE:
        if not _canon_is_placeholder(value):
            if canonical and not _canon_looks_like_real_key(value, canonical):
                return True
            return False
        return True
    # Local twin (canon module unavailable): same stages, no provider regexes.
    if value is None:
        return True
    value = str(value).strip()
    if len(value) < 10:
        return True
    low = value.lower()
    if low in ("true", "false", "yes", "no", "null", "none", "undefined", "n/a", "na"):
        return True
    for sub in (
        "xxxxx", "your_key", "your-key", "your_api", "your-api", "yourkey",
        "your_token", "replace_me", "replace-me", "replaceme", "changeme",
        "change_me", "change-me", "placeholder", "example", "sample", "dummy",
        "demo", "test_key", "fake_key", "sk-test", "sk-xxx", "sk-example",
        "sk-replace", "todo", "tbd", "fill_in", "fillin", "paste-your",
        "paste_your", "paste-real", "paste_real", "pastereal", "insert_your",
        "enter_your", "set_your", "no_key", "nokey", "none_yet", "not_set",
        "unset", "missing",
    ):
        if sub in low:
            return True
    if value.startswith("<") and value.endswith(">"):
        return True
    if value.startswith("[") and value.endswith("]"):
        return True
    if "{{" in value and "}}" in value:
        return True
    return False


def _canonical_family_blocked(env_map: Dict[str, str], name: str) -> bool:
    """True when `name` (canonical or alias) sits in a canon family whose
    CANONICAL head is present but placeholder-rejected. FIX 67: a placeholder
    under the canonical name poisons the whole family — the fuzzy fallback
    must not resurrect the query with some other KIE_*-flavored variable."""
    canonical = _canonical_for_candidate(name)
    if not canonical:
        return False
    canonical_value = env_map.get(canonical)
    if canonical_value and _is_placeholder(canonical_value, canonical):
        return True
    return False


def resolve_key(service_or_key: str, *, exact: bool = False, default: Optional[str] = None) -> Optional[str]:
    env_map = _build_env_map()
    if exact: return env_map.get(service_or_key, default)
    normalized = service_or_key.lower().replace("-", "").replace("_", "")
    for candidate in SERVICE_ALIASES.get(normalized, []):
        value = env_map.get(candidate)
        if value and not _is_placeholder(value, _canonical_for_candidate(candidate)):
            return value
    direct = env_map.get(service_or_key)
    if direct and not _is_placeholder(direct, _canonical_for_candidate(service_or_key)):
        return direct
    upper = service_or_key.upper()
    for suffix in ("_API_KEY", "_KEY", "_TOKEN", ""):
        candidate = f"{upper}{suffix}"
        value = env_map.get(candidate)
        if value and not _is_placeholder(value, _canonical_for_candidate(candidate)):
            return value
    # FIX 67: when the canonical head of this query's family is present but
    # placeholder-rejected, every further fallback is poisoned — return default.
    for probe in (service_or_key, upper, f"{upper}_API_KEY"):
        if _canonical_family_blocked(env_map, probe):
            return default
    needle = service_or_key.lower()
    for key, value in env_map.items():
        if needle in key.lower() and value and not _is_placeholder(value, _canonical_for_candidate(key)):
            # Never satisfy a key query with a config-style value
            # (KIE_BASE_URL etc.) — the candidate name itself must carry a
            # key-ish marker or be a known canon alias for this service.
            if "KEY" in key.upper() or "TOKEN" in key.upper() or "SECRET" in key.upper() or "API" in key.upper() or _canonical_for_candidate(key):
                if not _canonical_family_blocked(env_map, key):
                    return value
    return default


def _canonical_for_candidate(candidate: str) -> Optional[str]:
    """Canonical head for a candidate env-var name, or None when unknown."""
    if _CANON_AVAILABLE:
        for canonical, family in _canon_load().items():
            if candidate in family:
                return canonical
    return None
