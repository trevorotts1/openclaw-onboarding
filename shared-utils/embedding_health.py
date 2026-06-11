#!/usr/bin/env python3
"""
embedding_health.py — PRD Addendum B item B.6 (P1)
=====================================================
Per-box embedding-provider health check, covering ALL THREE embedding consumers:

  Index 1 — OpenClaw memory search
             (agents.defaults.memorySearch; ~/.openclaw/memory/*.sqlite meta stamp)
  Index 2 — Persona gemini-index
             (gemini-embedding-2 @3072; ~/.openclaw/gemini-index/ stamp)
  Index 3 — CC SOP embeddings
             (mission-control.db; sqlite stamp in the Command Center DB)

For EACH index three legs are checked:
  (a) Embedding-CAPABLE provider configured + key present + one cheap smoke embed.
      Ollama Cloud is NEVER embedding-capable (hard rule — no exceptions).
  (b) The index's stamped provider/model/dim matches the currently configured
      provider.  Mismatch -> FLAG RE-INDEX (not a pass).
  (c) The configured generative provider is NEVER assumed to embed.

Failures are LOUD and name both the index and the specific failed leg.

Also verifies that the memorySearch fallback config (PRD item 2.6) is present
(agents.defaults.memorySearch.fallback exists and is non-empty).

This module is designed to run:
  - Inline, called from fleet_refresh_runner.py (step_embedding_health)
  - Standalone:  python3 embedding_health.py [--json] [--openclaw-root <path>]

Output (JSON) schema:
  {
    "overall": "pass" | "fail" | "warn",
    "indexes": {
      "memory_search":   <IndexResult>,
      "persona_gemini":  <IndexResult>,
      "cc_sop":          <IndexResult>
    },
    "memory_fallback_ok":  bool,
    "memory_fallback_val": str | null,
    "errors":  [str, ...],
    "warnings":[str, ...],
    "notes":   [str, ...]
  }

  IndexResult:
  {
    "name":                           str,
    "leg_a_provider_capable":         bool,
    "leg_a_smoke":                    bool | null,   # null = provider not capable (smoke not attempted)
    "leg_b_stamp_match":              bool | null,   # null = no stamp on disk (not yet indexed)
    "leg_b_detail":                   str,
    "leg_c_generative_not_embedding": bool,
    "pass":                           bool,
    "needs_reindex":                  bool,
    "errors":                         [str],
    "warnings":                       [str]
  }

PRD Addendum B.6 — ships in v11.16.0
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
GREEN  = "\033[0;32m"
CYAN   = "\033[0;36m"
NC     = "\033[0m"


def _err(msg: str)  -> None: print(f"{RED}[embedding-health] FAIL  {msg}{NC}", file=sys.stderr)
def _warn(msg: str) -> None: print(f"{YELLOW}[embedding-health] WARN  {msg}{NC}", file=sys.stderr)
def _info(msg: str) -> None: print(f"{CYAN}[embedding-health] INFO  {msg}{NC}", file=sys.stderr)
def _ok(msg: str)   -> None: print(f"{GREEN}[embedding-health] PASS  {msg}{NC}", file=sys.stderr)


# ── Hard rule: providers that are NEVER embedding-capable ──────────────────────
# Ollama Cloud serves ONLY generative models.  Any box configured to use Ollama
# Cloud as its embedding provider is BROKEN.  This list is authoritative and is
# checked in leg (a) and leg (c) for every index.
NEVER_EMBEDDING_PROVIDERS = frozenset([
    "ollama",         # when baseUrl == https://ollama.com (cloud mode)
    "ollama:cloud",
    "ollama_cloud",
])

# Providers that CAN embed (canonical set known at release time)
EMBEDDING_CAPABLE_PROVIDERS = frozenset([
    "google",
    "gemini",
    "openai",
    "openrouter",   # only for text-embedding-3-small via OpenRouter
    "azure",
    "cohere",
    "voyageai",
    "voyage",
])

# Canonical embedding model for the persona gemini-index (PRD 1.8)
GEMINI_EMBED_MODEL = "gemini-embedding-2"
GEMINI_EMBED_DIMS  = 3072

# OpenAI / OpenRouter fallback for memory search
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_EMBED_DIMS  = 1536


# ─────────────────────────────────────────────────────────────────────────────
# Provider resolution helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_ollama_cloud(openclaw_json: dict) -> bool:
    """Return True if the Ollama provider baseUrl points to ollama.com (Cloud)."""
    try:
        base_url = (
            openclaw_json
            .get("models", {})
            .get("providers", {})
            .get("ollama", {})
            .get("baseUrl", "")
            or ""
        )
        return "ollama.com" in base_url.lower()
    except Exception:
        return False


def _resolve_memory_search_provider(openclaw_json: dict) -> Optional[str]:
    """Return agents.defaults.memorySearch.provider from openclaw.json."""
    try:
        return (
            openclaw_json
            .get("agents", {})
            .get("defaults", {})
            .get("memorySearch", {})
            .get("provider")
        )
    except Exception:
        return None


def _resolve_memory_search_fallback(openclaw_json: dict) -> Optional[str]:
    """Return agents.defaults.memorySearch.fallback (PRD 2.6)."""
    try:
        return (
            openclaw_json
            .get("agents", {})
            .get("defaults", {})
            .get("memorySearch", {})
            .get("fallback")
        )
    except Exception:
        return None


def _openclaw_env_vars(openclaw_json: Optional[dict]) -> dict:
    """
    Return the box's OWN openclaw.json env.vars map (env.vars).

    Bug-fix (v11.18.1): on gateway boxes the embedding key is wired into
    openclaw.json `env.vars` (and may not be exported into this Python process's
    OS env). NO CO-MINGLING: this reads env.vars ONLY from the openclaw_json
    already parsed for THIS box — it never borrows another box's key or hits
    another gateway.
    """
    if not isinstance(openclaw_json, dict):
        return {}
    env = openclaw_json.get("env", {})
    if not isinstance(env, dict):
        return {}
    vars_ = env.get("vars", {})
    return vars_ if isinstance(vars_, dict) else {}


def _load_gateway_env_file() -> dict:
    """
    Load the Mac OpenClaw launchd gateway env snapshot file.

    On Mac clients the gateway is managed by launchd and its env vars are
    loaded from a static snapshot file that is NOT inherited by subprocess
    environments (per the openclaw-mac-gateway-env-and-slack memory pattern):

        ~/.openclaw/service-env/ai.openclaw.gateway.env

    Returns an empty dict if the file is absent or unparseable.
    This is checked as a third source in _get_api_key (after os.environ and
    openclaw_json["env"]["vars"]) so Mac clients find their embedding keys
    without any co-mingling.
    """
    candidates = [
        Path.home() / ".openclaw" / "service-env" / "ai.openclaw.gateway.env",
        Path("/data/.openclaw/service-env/ai.openclaw.gateway.env"),
    ]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        result: dict = {}
        try:
            for line in candidate.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        result[k] = v
        except Exception:
            continue
        return result
    return {}


# Module-level lazy cache for gateway env file (loaded once per process)
_GATEWAY_ENV_CACHE: Optional[dict] = None


def _get_gateway_env_file() -> dict:
    """Return cached gateway env file contents (loaded once per process)."""
    global _GATEWAY_ENV_CACHE
    if _GATEWAY_ENV_CACHE is None:
        _GATEWAY_ENV_CACHE = _load_gateway_env_file()
    return _GATEWAY_ENV_CACHE


def _get_api_key(env_key: str, openclaw_json: Optional[dict] = None) -> Optional[str]:
    """Resolve an API key from multiple sources.  Returns None if absent/empty.

    Search order (first non-empty value wins):
      1. os.environ — VPS Docker / CI / shell-injected envs.
      2. openclaw_json["env"]["vars"] — keys wired via `openclaw config set env.vars.X`
         (present in the parsed openclaw.json; not always in OS env on gateway boxes).
      3. Mac gateway env file (~/.openclaw/service-env/ai.openclaw.gateway.env) —
         the launchd static snapshot; never inherited by subprocess envs on Mac
         (per openclaw-mac-gateway-env-and-slack pattern).

    NO CO-MINGLING: sources 2 and 3 are box-local only; they are never read
    from another box's files.
    """
    val = os.environ.get(env_key, "").strip()
    if val:
        return val
    env_vars = _openclaw_env_vars(openclaw_json)
    raw = env_vars.get(env_key, "")
    val = str(raw).strip() if raw is not None else ""
    if val:
        return val
    # Mac launchd gateway env file (third source)
    gw_env = _get_gateway_env_file()
    val = gw_env.get(env_key, "").strip()
    return val if val else None


def _provider_is_ollama_cloud(provider: str, openclaw_json: dict) -> bool:
    """Return True if this provider string resolves to Ollama Cloud."""
    if not provider:
        return False
    p = provider.lower().strip()
    if p in NEVER_EMBEDDING_PROVIDERS:
        return True
    if p == "ollama" and _is_ollama_cloud(openclaw_json):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Smoke embed helpers — one cheap call per provider
# ─────────────────────────────────────────────────────────────────────────────

def _smoke_embed_google(api_key: str) -> tuple[bool, str]:
    """Smoke embed via Google Generative AI (gemini-embedding-2 @3072)."""
    try:
        import urllib.request
        import urllib.error
        payload = json.dumps({
            "model": f"models/{GEMINI_EMBED_MODEL}",
            "content": {"parts": [{"text": "embedding health smoke test"}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": GEMINI_EMBED_DIMS,
        }).encode()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_EMBED_MODEL}:embedContent?key={api_key}"
        )
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())
            vals = body.get("embedding", {}).get("values", [])
            if len(vals) == GEMINI_EMBED_DIMS:
                return True, f"gemini-embedding-2 smoke OK: {len(vals)}-dim vector"
            return False, f"gemini-embedding-2 smoke: unexpected dim count {len(vals)}"
    except Exception as exc:
        return False, f"gemini-embedding-2 smoke FAILED: {exc.__class__.__name__}: {exc}"


def _smoke_embed_openai(api_key: str) -> tuple[bool, str]:
    """Smoke embed via OpenAI text-embedding-3-small."""
    try:
        import urllib.request
        payload = json.dumps({
            "model": OPENAI_EMBED_MODEL,
            "input": "embedding health smoke test",
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())
            vals = body.get("data", [{}])[0].get("embedding", [])
            if len(vals) == OPENAI_EMBED_DIMS:
                return True, f"text-embedding-3-small smoke OK: {len(vals)}-dim vector"
            return False, f"text-embedding-3-small smoke: unexpected dim count {len(vals)}"
    except Exception as exc:
        return False, f"text-embedding-3-small smoke FAILED: {exc.__class__.__name__}: {exc}"


def _smoke_embed_openrouter(api_key: str) -> tuple[bool, str]:
    """Smoke embed via OpenRouter (text-embedding-3-small @1536)."""
    try:
        import urllib.request
        payload = json.dumps({
            "model": "openai/text-embedding-3-small",
            "input": "embedding health smoke test",
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/embeddings",
            data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read())
            vals = body.get("data", [{}])[0].get("embedding", [])
            if len(vals) == OPENAI_EMBED_DIMS:
                return True, f"openrouter/text-embedding-3-small smoke OK: {len(vals)}-dim vector"
            return False, f"openrouter/text-embedding-3-small smoke: unexpected dim count {len(vals)}"
    except Exception as exc:
        return False, f"openrouter/text-embedding-3-small smoke FAILED: {exc.__class__.__name__}: {exc}"


def _attempt_smoke_embed(provider: str, openclaw_json: dict) -> tuple[bool, str]:
    """Dispatch a smoke embed call to the given provider."""
    p = (provider or "").lower().strip()

    # Hard rule: never attempt smoke on Ollama Cloud
    if _provider_is_ollama_cloud(p, openclaw_json):
        return False, "Ollama Cloud CANNOT embed — hard rule B.6 (no exceptions)"

    if p in ("google", "gemini"):
        key = _get_api_key("GOOGLE_API_KEY", openclaw_json) or _get_api_key("GEMINI_API_KEY", openclaw_json)
        if not key:
            return False, "GOOGLE_API_KEY / GEMINI_API_KEY not set"
        return _smoke_embed_google(key)

    if p == "openai":
        key = _get_api_key("OPENAI_API_KEY", openclaw_json)
        if not key:
            return False, "OPENAI_API_KEY not set"
        return _smoke_embed_openai(key)

    if p == "openrouter":
        key = _get_api_key("OPENROUTER_API_KEY", openclaw_json)
        if not key:
            return False, "OPENROUTER_API_KEY not set"
        return _smoke_embed_openrouter(key)

    return False, f"Provider '{provider}' not supported for smoke embed in this check"


# ─────────────────────────────────────────────────────────────────────────────
# Index stamp readers
# ─────────────────────────────────────────────────────────────────────────────

def _read_memory_stamp(openclaw_root: Path) -> Optional[dict]:
    """
    Read the embedded-provider meta stamp from the OpenClaw memory SQLite index.
    Checks <openclaw_root>/memory/*.sqlite for a meta/embedding_meta/settings table.
    Returns {provider, model, dim} or None if no stamp exists.
    """
    memory_dir = openclaw_root / "memory"
    if not memory_dir.is_dir():
        return None

    for sqlite_file in sorted(memory_dir.glob("*.sqlite")):
        try:
            con = sqlite3.connect(str(sqlite_file), timeout=5)
            cur = con.cursor()

            # Attempt 1: canonical meta table key/value
            try:
                cur.execute(
                    "SELECT key, value FROM meta "
                    "WHERE key IN ('provider','model','dim')"
                )
                rows = cur.fetchall()
                if rows:
                    stamp = {k: v for k, v in rows}
                    if "provider" in stamp or "model" in stamp:
                        con.close()
                        return stamp
            except sqlite3.OperationalError:
                pass

            # Attempt 2: embedding_meta (provider/model/dim columns)
            try:
                cur.execute(
                    "SELECT provider, model, dim FROM embedding_meta LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    con.close()
                    return {"provider": row[0], "model": row[1], "dim": str(row[2])}
            except sqlite3.OperationalError:
                pass

            # Attempt 3: settings table with embedding_* keys
            try:
                cur.execute(
                    "SELECT key, value FROM settings "
                    "WHERE key IN ('embedding_provider','embedding_model','embedding_dim')"
                )
                rows = cur.fetchall()
                if rows:
                    mapping = {k.replace("embedding_", ""): v for k, v in rows}
                    con.close()
                    return mapping
            except sqlite3.OperationalError:
                pass

            con.close()
        except Exception:
            continue

    return None


def _read_gemini_index_stamp(openclaw_root: Path) -> Optional[dict]:
    """
    Read the gemini-index stamp from the persona embedding index.
    Searches multiple candidate directories for meta.json / stamp.json.
    Returns {provider, model, dim} or None.
    """
    search_dirs = [
        openclaw_root / "gemini-index",
        openclaw_root / "workspace" / "gemini-index",
        openclaw_root.parent / "clawd" / "gemini-index",
        openclaw_root.parent.parent / "clawd" / "gemini-index",
    ]
    stamp_filenames = [
        "meta.json",
        "stamp.json",
        "index-meta.json",
        "embedding-meta.json",
    ]

    for d in search_dirs:
        for fname in stamp_filenames:
            p = d / fname
            if p.is_file():
                try:
                    data = json.loads(p.read_text())
                    if isinstance(data, dict) and ("provider" in data or "model" in data):
                        return data
                except Exception:
                    continue

    return None


def _read_cc_sop_stamp(
    cc_dir: Path,
    db_path_override: Optional[str] = None,
    openclaw_json: Optional[dict] = None,
) -> Optional[dict]:
    """
    Read the embedding stamp from the Command Center SOP database (mission-control.db).
    Returns {provider, model, dim} or None.

    Bug-fix (v11.18.1): DATABASE_PATH may be wired into the box's own
    openclaw.json env.vars rather than this process's OS env, so we consult
    env.vars as a fallback (OS env still wins). NO CO-MINGLING: env.vars are
    read only from the openclaw_json already passed in for THIS box.
    """
    candidates: list[Path] = []
    env_db = os.environ.get("DATABASE_PATH", "").strip()
    if not env_db:
        env_db = str(_openclaw_env_vars(openclaw_json).get("DATABASE_PATH", "") or "").strip()
    if env_db:
        candidates.insert(0, Path(env_db))
    if db_path_override:
        candidates.append(Path(db_path_override))
    if cc_dir and cc_dir.exists():
        candidates += [
            cc_dir / "mission-control.db",
            cc_dir / "data" / "mission-control.db",
            cc_dir / "db" / "mission-control.db",
            cc_dir / "prisma" / "dev.db",
        ]

    for db_file in candidates:
        if not db_file.is_file():
            continue
        try:
            con = sqlite3.connect(str(db_file), timeout=5)
            cur = con.cursor()

            # Attempt 1: embedding_meta table
            try:
                cur.execute(
                    "SELECT provider, model, dim FROM embedding_meta LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    con.close()
                    return {"provider": row[0], "model": row[1], "dim": str(row[2])}
            except sqlite3.OperationalError:
                pass

            # Attempt 2: meta key/value
            try:
                cur.execute(
                    "SELECT key, value FROM meta "
                    "WHERE key IN ('embedding_provider','embedding_model','embedding_dim')"
                )
                rows = cur.fetchall()
                if rows:
                    mapping = {k.replace("embedding_", ""): v for k, v in rows}
                    con.close()
                    return mapping
            except sqlite3.OperationalError:
                pass

            # Attempt 3: settings / system_settings / config
            for tbl in ("system_settings", "settings", "config"):
                try:
                    cur.execute(
                        f"SELECT key, value FROM {tbl} "
                        f"WHERE key LIKE 'embedding_%' LIMIT 10"
                    )
                    rows = cur.fetchall()
                    if rows:
                        mapping = {k.replace("embedding_", ""): v for k, v in rows}
                        con.close()
                        return mapping
                except sqlite3.OperationalError:
                    continue

            con.close()
        except Exception:
            continue

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Per-index health check functions
# ─────────────────────────────────────────────────────────────────────────────

def _make_index_result(name: str) -> dict:
    return {
        "name":                           name,
        "leg_a_provider_capable":         False,
        "leg_a_smoke":                    None,
        "leg_b_stamp_match":              None,
        "leg_b_detail":                   "no stamp on disk (index not yet built)",
        "leg_c_generative_not_embedding": True,
        "pass":                           False,
        "needs_reindex":                  False,
        "errors":                         [],
        "warnings":                       [],
    }


def check_memory_search_index(
    openclaw_root: Path,
    openclaw_json: dict,
    generative_provider: Optional[str],
) -> dict:
    """Check Index 1: OpenClaw memory search (agents.defaults.memorySearch)."""
    res = _make_index_result("memory_search (agents.defaults.memorySearch)")
    LBL = "Index 1 (memory_search)"

    mem_provider = _resolve_memory_search_provider(openclaw_json)

    # ── Leg (a) ────────────────────────────────────────────────────────────────
    if not mem_provider:
        msg = f"{LBL} leg-a FAIL: no memorySearch.provider configured in openclaw.json"
        res["errors"].append(msg)
        _err(msg)
    elif _provider_is_ollama_cloud(mem_provider, openclaw_json):
        msg = (
            f"{LBL} leg-a FAIL: memorySearch.provider='{mem_provider}' is Ollama Cloud — "
            f"NEVER embedding-capable (hard rule B.6). "
            f"Set a real embedding provider (google / openai / openrouter)."
        )
        res["errors"].append(msg)
        _err(msg)
    elif mem_provider.lower() not in EMBEDDING_CAPABLE_PROVIDERS:
        msg = (
            f"{LBL} leg-a WARN: memorySearch.provider='{mem_provider}' is not in the "
            f"known-capable set. Smoke embed may fail."
        )
        res["warnings"].append(msg)
        _warn(msg)
    else:
        res["leg_a_provider_capable"] = True
        _ok(f"{LBL} leg-a provider: '{mem_provider}' is embedding-capable")

    if res["leg_a_provider_capable"]:
        smoke_ok, smoke_detail = _attempt_smoke_embed(mem_provider, openclaw_json)
        res["leg_a_smoke"] = smoke_ok
        if smoke_ok:
            _ok(f"{LBL} leg-a smoke: {smoke_detail}")
        else:
            msg = f"{LBL} leg-a FAIL smoke: {smoke_detail}"
            res["errors"].append(msg)
            _err(msg)

    # ── Leg (b) ────────────────────────────────────────────────────────────────
    stamp = _read_memory_stamp(openclaw_root)
    if stamp is None:
        res["leg_b_stamp_match"] = None
        res["leg_b_detail"] = "no memory stamp on disk (index not yet built — OK on fresh box)"
        _info(f"{LBL} leg-b: no stamp (not yet indexed)")
    else:
        stamped_provider = (stamp.get("provider") or "").lower().strip()
        current_provider = (mem_provider or "").lower().strip()
        match = bool(stamped_provider and current_provider and stamped_provider == current_provider)
        res["leg_b_stamp_match"] = match
        res["leg_b_detail"] = (
            f"stamped provider='{stamped_provider}' model='{stamp.get('model')}' "
            f"dim='{stamp.get('dim')}' | configured='{current_provider}'"
        )
        if match:
            _ok(f"{LBL} leg-b stamp: {res['leg_b_detail']}")
        else:
            res["needs_reindex"] = True
            msg = (
                f"{LBL} leg-b FLAG RE-INDEX: stamped provider '{stamped_provider}' "
                f"!= configured '{current_provider}'. "
                f"Re-index memory with the current provider."
            )
            res["errors"].append(msg)
            _err(msg)

    # ── Leg (c) ────────────────────────────────────────────────────────────────
    if generative_provider and _provider_is_ollama_cloud(generative_provider, openclaw_json):
        if mem_provider == generative_provider:
            msg = (
                f"{LBL} leg-c FAIL: generative provider '{generative_provider}' is "
                f"Ollama Cloud and is configured as the embedding provider — HARD VIOLATION."
            )
            res["errors"].append(msg)
            res["leg_c_generative_not_embedding"] = False
            _err(msg)
        else:
            _ok(f"{LBL} leg-c: generative ({generative_provider}) != embedding ({mem_provider}) — correct")
    else:
        _ok(f"{LBL} leg-c: generative provider not used as embedding provider")

    # ── Overall ────────────────────────────────────────────────────────────────
    res["pass"] = (
        res["leg_a_provider_capable"]
        and res["leg_a_smoke"] is True
        and res["leg_b_stamp_match"] is not False
        and res["leg_c_generative_not_embedding"]
        and not res["needs_reindex"]
    )
    return res


def check_persona_gemini_index(
    openclaw_root: Path,
    openclaw_json: dict,
    generative_provider: Optional[str],
) -> dict:
    """Check Index 2: Persona gemini-index (gemini-embedding-2 @3072)."""
    res = _make_index_result(f"persona_gemini ({GEMINI_EMBED_MODEL} @{GEMINI_EMBED_DIMS})")
    LBL = "Index 2 (persona_gemini)"

    google_key = _get_api_key("GOOGLE_API_KEY", openclaw_json) or _get_api_key("GEMINI_API_KEY", openclaw_json)

    # ── Leg (a) ────────────────────────────────────────────────────────────────
    if not google_key:
        msg = (
            f"{LBL} leg-a FAIL: GOOGLE_API_KEY / GEMINI_API_KEY not set. "
            f"The persona gemini-index requires Google embedding "
            f"({GEMINI_EMBED_MODEL} @{GEMINI_EMBED_DIMS})."
        )
        res["errors"].append(msg)
        _err(msg)
    else:
        res["leg_a_provider_capable"] = True
        _ok(f"{LBL} leg-a: GOOGLE_API_KEY present, provider=google")
        smoke_ok, smoke_detail = _smoke_embed_google(google_key)
        res["leg_a_smoke"] = smoke_ok
        if smoke_ok:
            _ok(f"{LBL} leg-a smoke: {smoke_detail}")
        else:
            msg = f"{LBL} leg-a FAIL smoke: {smoke_detail}"
            res["errors"].append(msg)
            _err(msg)

    # ── Leg (b) ────────────────────────────────────────────────────────────────
    stamp = _read_gemini_index_stamp(openclaw_root)
    if stamp is None:
        res["leg_b_stamp_match"] = None
        res["leg_b_detail"] = "no gemini-index stamp on disk (index not yet built)"
        _info(f"{LBL} leg-b: no stamp (not yet indexed)")
    else:
        stamped_model    = (stamp.get("model") or "").lower().strip()
        stamped_dim      = str(stamp.get("dim", "") or "").strip()
        stamped_provider = (stamp.get("provider") or "").lower().strip()

        provider_mismatch = stamped_provider not in ("", "google", "gemini")
        model_ok = GEMINI_EMBED_MODEL.lower() in stamped_model if stamped_model else False
        dim_ok   = stamped_dim == str(GEMINI_EMBED_DIMS) if stamped_dim else True

        if provider_mismatch:
            res["needs_reindex"] = True
            res["leg_b_stamp_match"] = False
            msg = (
                f"{LBL} leg-b FLAG RE-INDEX: index is stamped with provider "
                f"'{stamped_provider}' but must use google/{GEMINI_EMBED_MODEL}. "
                f"Re-index with GOOGLE_API_KEY set."
            )
            res["errors"].append(msg)
            res["leg_b_detail"] = (
                f"stamped={stamped_provider}/{stamped_model}/{stamped_dim} "
                f"expected=google/{GEMINI_EMBED_MODEL}/{GEMINI_EMBED_DIMS}"
            )
            _err(msg)
        elif not model_ok or not dim_ok:
            res["needs_reindex"] = True
            res["leg_b_stamp_match"] = False
            msg = (
                f"{LBL} leg-b FLAG RE-INDEX: model or dim mismatch. "
                f"stamped model='{stamped_model}' dim='{stamped_dim}' "
                f"expected='{GEMINI_EMBED_MODEL}' dim='{GEMINI_EMBED_DIMS}'."
            )
            res["errors"].append(msg)
            res["leg_b_detail"] = (
                f"model_ok={model_ok} dim_ok={dim_ok} "
                f"stamped={stamped_model}/{stamped_dim}"
            )
            _err(msg)
        else:
            res["leg_b_stamp_match"] = True
            res["leg_b_detail"] = (
                f"stamped model='{stamped_model}' dim='{stamped_dim}' "
                f"matches {GEMINI_EMBED_MODEL}@{GEMINI_EMBED_DIMS}"
            )
            _ok(f"{LBL} leg-b stamp: {res['leg_b_detail']}")

    # ── Leg (c) ────────────────────────────────────────────────────────────────
    if generative_provider and _provider_is_ollama_cloud(generative_provider, openclaw_json):
        _info(
            f"{LBL} leg-c: generative=Ollama Cloud. "
            f"Confirming persona index uses a separate Google embedding call."
        )
        if stamp and (stamp.get("provider") or "").lower() in NEVER_EMBEDDING_PROVIDERS:
            res["leg_c_generative_not_embedding"] = False
            msg = (
                f"{LBL} leg-c FAIL: index stamped with Ollama provider — "
                f"Ollama Cloud CANNOT embed. Re-index with Google."
            )
            res["errors"].append(msg)
            _err(msg)
        else:
            _ok(f"{LBL} leg-c: no Ollama stamp on gemini-index — correct")
    else:
        _ok(f"{LBL} leg-c: generative provider not confused with embedding provider")

    # ── Overall ────────────────────────────────────────────────────────────────
    res["pass"] = (
        res["leg_a_provider_capable"]
        and res["leg_a_smoke"] is True
        and res["leg_b_stamp_match"] is not False
        and res["leg_c_generative_not_embedding"]
        and not res["needs_reindex"]
    )
    return res


def check_cc_sop_index(
    cc_dir: Path,
    openclaw_json: dict,
    generative_provider: Optional[str],
) -> dict:
    """Check Index 3: CC SOP embeddings (mission-control.db)."""
    res = _make_index_result("cc_sop (mission-control.db)")
    LBL = "Index 3 (cc_sop)"

    google_key    = _get_api_key("GOOGLE_API_KEY", openclaw_json) or _get_api_key("GEMINI_API_KEY", openclaw_json)
    openai_key    = _get_api_key("OPENAI_API_KEY", openclaw_json)
    openrouter_key = _get_api_key("OPENROUTER_API_KEY", openclaw_json)

    capable_provider: Optional[str] = None
    if google_key:
        capable_provider = "google"
    elif openai_key:
        capable_provider = "openai"
    elif openrouter_key:
        capable_provider = "openrouter"

    # ── Leg (a) ────────────────────────────────────────────────────────────────
    if not capable_provider:
        msg = (
            f"{LBL} leg-a FAIL: no embedding-capable key present. "
            f"Need GOOGLE_API_KEY/GEMINI_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY. "
            f"CC SOP embeddings will not work."
        )
        res["errors"].append(msg)
        _err(msg)
    else:
        res["leg_a_provider_capable"] = True
        _ok(f"{LBL} leg-a: capable provider='{capable_provider}' (key present)")
        smoke_ok, smoke_detail = _attempt_smoke_embed(capable_provider, openclaw_json)
        res["leg_a_smoke"] = smoke_ok
        if smoke_ok:
            _ok(f"{LBL} leg-a smoke: {smoke_detail}")
        else:
            msg = f"{LBL} leg-a FAIL smoke: {smoke_detail}"
            res["errors"].append(msg)
            _err(msg)

    # ── Leg (b) ────────────────────────────────────────────────────────────────
    stamp = _read_cc_sop_stamp(cc_dir, openclaw_json=openclaw_json)
    if stamp is None:
        res["leg_b_stamp_match"] = None
        res["leg_b_detail"] = "no CC SOP stamp on disk (DB not found or index not yet built)"
        _info(f"{LBL} leg-b: no stamp")
    else:
        stamped_provider = (stamp.get("provider") or "").lower().strip()
        stamped_model    = (stamp.get("model") or "").lower().strip()

        if stamped_provider in NEVER_EMBEDDING_PROVIDERS or (
            stamped_provider == "ollama" and _is_ollama_cloud(openclaw_json)
        ):
            res["needs_reindex"] = True
            res["leg_b_stamp_match"] = False
            msg = (
                f"{LBL} leg-b FLAG RE-INDEX: CC SOP index stamped with "
                f"'{stamped_provider}' — Ollama Cloud CANNOT embed. "
                f"Re-index with Google / OpenAI."
            )
            res["errors"].append(msg)
            res["leg_b_detail"] = f"stamped={stamped_provider}/{stamped_model}"
            _err(msg)
        elif capable_provider and stamped_provider and stamped_provider != capable_provider:
            res["needs_reindex"] = True
            res["leg_b_stamp_match"] = False
            msg = (
                f"{LBL} leg-b FLAG RE-INDEX: stamped provider='{stamped_provider}' "
                f"!= current capable provider='{capable_provider}'. "
                f"Re-index required."
            )
            res["errors"].append(msg)
            res["leg_b_detail"] = (
                f"stamped={stamped_provider}/{stamped_model} "
                f"vs current capable={capable_provider}"
            )
            _err(msg)
        else:
            res["leg_b_stamp_match"] = True
            res["leg_b_detail"] = (
                f"stamped={stamped_provider}/{stamped_model} (consistent with current capable provider)"
            )
            _ok(f"{LBL} leg-b stamp: {res['leg_b_detail']}")

    # ── Leg (c) ────────────────────────────────────────────────────────────────
    if generative_provider and _provider_is_ollama_cloud(generative_provider, openclaw_json):
        if stamp and (stamp.get("provider") or "").lower() in NEVER_EMBEDDING_PROVIDERS:
            res["leg_c_generative_not_embedding"] = False
            msg = (
                f"{LBL} leg-c FAIL: CC SOP index is stamped with Ollama provider — "
                f"Ollama Cloud CANNOT embed. Re-index with Google / OpenAI."
            )
            res["errors"].append(msg)
            _err(msg)
        else:
            _ok(f"{LBL} leg-c: no Ollama stamp found on CC SOP index")
    else:
        _ok(f"{LBL} leg-c: generative provider not confused with embedding provider")

    # ── Overall ────────────────────────────────────────────────────────────────
    res["pass"] = (
        res["leg_a_provider_capable"]
        and res["leg_a_smoke"] is True
        and res["leg_b_stamp_match"] is not False
        and res["leg_c_generative_not_embedding"]
        and not res["needs_reindex"]
    )
    return res


# ─────────────────────────────────────────────────────────────────────────────
# Top-level orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_embedding_health(
    openclaw_root: Path,
    openclaw_json: dict,
    cc_dir: Optional[Path],
) -> dict:
    """
    Run the full B.6 embedding-health check for all three indexes.
    Called by fleet_refresh_runner.step_embedding_health() and standalone CLI.
    Returns the canonical result dict.
    """
    _info("=" * 60)
    _info("B.6 Embedding-Health Check — all three indexes, three legs each")
    _info("=" * 60)

    # Resolve the generative provider for leg-c checks
    generative_raw = (
        openclaw_json
        .get("agents", {})
        .get("defaults", {})
        .get("model", {})
    )
    if isinstance(generative_raw, dict):
        generative_provider: Optional[str] = generative_raw.get("primary", "")
    else:
        generative_provider = str(generative_raw) if generative_raw else ""

    if isinstance(generative_provider, str) and "/" in generative_provider:
        generative_provider = generative_provider.split("/")[0]

    if _is_ollama_cloud(openclaw_json):
        _warn(
            "OLLAMA CLOUD BOX DETECTED: this box's Ollama baseUrl is https://ollama.com. "
            "Ollama Cloud serves generative models ONLY — it CANNOT embed. "
            "All three indexes require a separate embedding key (Google / OpenAI / OpenRouter)."
        )

    # ── Index 1: memory search ─────────────────────────────────────────────────
    _info("--- Index 1: OpenClaw memory search ---")
    mem_result = check_memory_search_index(openclaw_root, openclaw_json, generative_provider)

    # ── Index 2: persona gemini-index ─────────────────────────────────────────
    _info("--- Index 2: Persona gemini-index ---")
    gemini_result = check_persona_gemini_index(openclaw_root, openclaw_json, generative_provider)

    # ── Index 3: CC SOP embeddings ─────────────────────────────────────────────
    _info("--- Index 3: CC SOP embeddings ---")
    cc_sop_result = check_cc_sop_index(
        cc_dir if cc_dir is not None else Path("/nonexistent"),
        openclaw_json,
        generative_provider,
    )

    # ── PRD 2.6: memorySearch fallback ────────────────────────────────────────
    _info("--- PRD 2.6 memorySearch fallback check ---")
    fallback_val = _resolve_memory_search_fallback(openclaw_json)
    fallback_ok  = bool(fallback_val and str(fallback_val).strip())
    if fallback_ok:
        _ok(f"memorySearch fallback present: '{fallback_val}'")
    else:
        _warn(
            "memorySearch fallback (PRD 2.6) is missing or empty. "
            "Set agents.defaults.memorySearch.fallback in openclaw.json "
            "(e.g. 'openai' or 'google')."
        )

    # ── Aggregate ──────────────────────────────────────────────────────────────
    all_errors   = mem_result["errors"] + gemini_result["errors"] + cc_sop_result["errors"]
    all_warnings = mem_result["warnings"] + gemini_result["warnings"] + cc_sop_result["warnings"]

    if not fallback_ok:
        all_warnings.append(
            "memorySearch fallback (PRD 2.6) missing or empty — "
            "set agents.defaults.memorySearch.fallback in openclaw.json"
        )

    needs_reindex_any = (
        mem_result["needs_reindex"]
        or gemini_result["needs_reindex"]
        or cc_sop_result["needs_reindex"]
    )
    all_pass = mem_result["pass"] and gemini_result["pass"] and cc_sop_result["pass"]

    if all_pass and fallback_ok and not needs_reindex_any:
        overall = "pass"
        _ok("B.6 overall: PASS — all three indexes healthy, fallback configured")
    elif all_errors:
        overall = "fail"
        _err(f"B.6 overall: FAIL — {len(all_errors)} error(s) across {sum(1 for r in [mem_result, gemini_result, cc_sop_result] if r['errors'])} index(es)")
        for e in all_errors:
            _err(f"  {e}")
    else:
        overall = "warn"
        _warn(f"B.6 overall: WARN — {len(all_warnings)} warning(s), no hard failures")

    return {
        "overall":             overall,
        "indexes": {
            "memory_search":   mem_result,
            "persona_gemini":  gemini_result,
            "cc_sop":          cc_sop_result,
        },
        "memory_fallback_ok":  fallback_ok,
        "memory_fallback_val": fallback_val,
        "errors":              all_errors,
        "warnings":            all_warnings,
        "notes": [
            "Ollama Cloud (ollama.com) NEVER serves embeddings — hard rule B.6.",
            "leg_b_stamp_match=null means the index has not been built yet "
            "(acceptable on a fresh box — build the index to get a stamp).",
            "needs_reindex=true means the index was built with a different provider; "
            "the existing vectors are stale and MUST be rebuilt.",
            "PRD 2.6: agents.defaults.memorySearch.fallback must be set to a "
            "non-empty string (e.g. 'openai' or 'google').",
            "N32: a model-provider change is NOT complete until embedding-health passes on this box.",
        ],
    }


def load_openclaw_json(openclaw_root: Path) -> dict:
    """Load openclaw.json from the openclaw root. Returns {} on failure."""
    for candidate in [
        openclaw_root / "openclaw.json",
        openclaw_root.parent / "openclaw.json",
    ]:
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text())
            except Exception:
                pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point — standalone use and fixture tests
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "embedding_health.py — PRD B.6 per-box embedding health check.\n"
            "Checks all three embedding indexes (memory, persona, CC SOP) "
            "across three legs each (provider capable + smoke + stamp match)."
        )
    )
    parser.add_argument(
        "--openclaw-root", default="",
        help="Path to .openclaw root dir (auto-detected from /data/.openclaw or ~/.openclaw if omitted)",
    )
    parser.add_argument(
        "--cc-dir", default="",
        help="Path to Command Center install dir (auto-detected if omitted)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print result JSON to stdout in addition to diagnostic logs on stderr",
    )
    args = parser.parse_args()

    # Resolve openclaw root
    if args.openclaw_root:
        openclaw_root = Path(args.openclaw_root).resolve()
    else:
        candidates = [Path("/data/.openclaw"), Path.home() / ".openclaw"]
        openclaw_root = next((c for c in candidates if c.is_dir()), candidates[-1])

    openclaw_json = load_openclaw_json(openclaw_root)

    # Resolve CC dir
    cc_dir: Optional[Path] = Path(args.cc_dir).resolve() if args.cc_dir else None
    if cc_dir is None:
        for cand in [
            Path("/data/projects/command-center"),
            Path.home() / "projects" / "command-center",
        ]:
            if cand.is_dir():
                cc_dir = cand
                break

    result = run_embedding_health(openclaw_root, openclaw_json, cc_dir)

    if args.json:
        print(json.dumps(result, indent=2))

    sys.exit(0 if result["overall"] != "fail" else 1)


if __name__ == "__main__":
    main()
