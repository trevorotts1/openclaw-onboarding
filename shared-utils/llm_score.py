"""
llm_score.py — LLM-backed scoring helper for OpenClaw.

Used by Skill 23's persona-selector to evaluate Layers 1-4 (mission /
owner_values / company_kpis / dept_kpis) against persona blueprints.
Returns a single float in [0.0, 1.0] with a short reasoning string.

Per company policy (memory: feedback-no-anthropic-for-subagents) no
Anthropic models are used in this pipeline. The model chain is:

    1. Ollama Cloud  — DeepSeek V4 Pro (primary, cheap + 1M context)
       Env: OLLAMA_CLOUD_API_KEY, OLLAMA_CLOUD_URL
            (default: https://ollama.com/api)

    2. OpenRouter    — DeepSeek V4 Pro (same model, paid fallback)
       Env: OPENROUTER_API_KEY

    3. OpenRouter    — Gemini 3.1 Flash Lite (cheapest last-resort)
       Env: OPENROUTER_API_KEY

Every one of those names is resolved by _env(), which since F25 reads the
box's SECRETS STORES as well as the process environment — see the
"Credential resolution (F25)" block below for the precedence contract and
for why a scheduler-spawned pass used to resolve nothing at all. `python3
shared-utils/llm_score.py --env-report` prints which of them resolve, from
where, with presence and LENGTH only and no value.

A simple SQLite cache keyed by SHA-256(persona_id + layer + context) keeps
repeat scoring of the same persona for the same company free. TTL = 30 days.

Usage:
    from llm_score import score_layer
    result = score_layer(
        persona_id="alex-hormozi",
        layer="mission",
        persona_blueprint_summary="Hormozi values...",
        context="BlackCEO's mission is...",
    )
    # result == {"score": 0.82, "reasoning": "...", "model": "...", "cached": False}

This module never raises on LLM failure — it falls through the chain and
returns a NEUTRAL_FALLBACK score with reasoning="all models failed: <error>"
so the caller can keep working (degraded mode).
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_TTL_SECONDS = 30 * 24 * 60 * 60   # 30 days
HTTP_TIMEOUT_SECONDS = 30
NEUTRAL_FALLBACK_SCORE = 0.6


# ───────────────────────────────────────────────────────────────────────
# Credential resolution  (F25)
#
# THE DEFECT THIS FIXES. Until F25 this module read os.environ and the
# openclaw.json env block and NOTHING ELSE -- unlike every sibling reader in
# shared-utils (key_resolver.py, api_key_utils.py) and unlike the
# presentation department's readers (presentation_job/env_store.py,
# model_router.py, research_web.py, kie_generate.py), all of which fall back
# to the box's SECRETS STORES. It is the residual half of the env-loading
# class that left PRESENTATION_NOTIFY_CMD unreachable and refused every
# dispatch with AF-NOTIFY-UNCONFIGURED: a script started by launchd or by the
# openclaw cron gets essentially NO environment, so a persona-scoring pass
# spawned under a scheduler resolved no key and logged
# "all models failed: OPENROUTER_API_KE..." while the key sat, present and
# non-blank, in ~/.openclaw/secrets/.env.
#
# MEASURED ON THE OPERATOR MAC, 2026-09-06 (values never printed, only
# presence and length):
#     presentation_job.env_store --report
#         watched  OPENROUTER_API_KEY: PRESENT (len 73, source env-store)
#     llm_score._env("OPENROUTER_API_KEY")  ->  resolved=False len=0
# Same box, same instant, two readers, opposite answers. That gap is F25.
#
# PRECEDENCE -- the same contract presentation_job/env_store.py documents:
#
#   1. the EXACT name in the process environment, non-blank        (wins)
#   2. any ALIAS of that name in the process environment, non-blank
#   3. the box's secrets stores, first store that answers          (F25)
#   4. the openclaw.json env block (legacy last resort)
#   5. the caller's default
#
# A BLANK process value does NOT shadow the store. Blank is the ABSENCE this
# whole fix is about, not an override -- that is precisely how the poller
# ended up refusing 5,948 consecutive dispatches. An operator override
# (`OPENROUTER_API_KEY=... python3 persona-selector-v2.py`) still wins,
# because it is non-blank.
#
# ONE CLIENT INSTALLATION, NEVER TWO. Which stores step 3 reads is decided by
# _openclaw_roots(): an explicit OPENCLAW_ROOT / OC_ROOT / OC_CONFIG pin (the
# same names presentation_job.oc_paths.root() honours) names THE installation
# this process belongs to and becomes the only root searched -- a credential
# search must never spill into another client's box. Unpinned, the default
# order is /data/.openclaw then ~/.openclaw then ~/.env, rebuilt from the
# LIVE environment on every call so a HOME-redirected child reads its own.
# The same roots decide which openclaw.json step 4 reads, so the two layers
# can never point at different installations.
#
# NAME CANON, NOT A RESTATED ALIAS TABLE. The alias family comes from
# shared-utils/secret_helper.py (FIX 67: secret_names.json), so a key written
# as OPENROUTER_KEY or OR_API_KEY resolves here exactly as it does in every
# other reader. If secret_helper cannot be imported the resolver degrades to
# the exact name only -- a broken canon never takes credential resolution
# down.
#
# PLACEHOLDER REJECTION IS DELIBERATELY *NOT* APPLIED. secret_helper offers
# looks_like_real_key(); this module does not call it. A false rejection
# would silently drop a real credential, while a bad value costs exactly one
# failed HTTPS attempt before the chain falls through -- and this module's
# contract is "never raise, always degrade". Readers that must fail closed
# before dispatch (kie_generate.py) keep using the strict gate; a scorer
# whose documented worst case is NEUTRAL_FALLBACK_SCORE must not.
#
# NO SECRET VALUE IS EVER PRINTED. env_report() is the only reporting
# surface and it carries presence and LENGTH only -- never a value, never a
# prefix of one. Same posture as env_store.redacted_report().
# ───────────────────────────────────────────────────────────────────────

#: Store filenames under an OpenClaw root, in the order every sibling reader
#: tries them. Mirrors shared-utils/secret_helper.ENV_FILE_CANDIDATES, which
#: is deliberately NOT imported and used directly: that list is a
#: module-level constant whose ~ was expanded once, at import, against
#: whatever HOME the process had then. The list here is rebuilt from the LIVE
#: environment on every call, which is what lets a HOME-redirected child (and
#: a hermetic test) resolve its OWN store instead of borrowing another
#: installation's. A test holds the two lists in lockstep -- see
#: _secret_store_files().
_STORE_RELATIVE_PATHS = ("secrets/.env", "secrets/secrets.env", ".env")

#: A legal POSIX environment variable name. Anything else in a store file is
#: skipped rather than trusted.
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SECRET_HELPER = None
_SECRET_HELPER_TRIED = False


def _secret_helper():
    """Import shared-utils/secret_helper.py (the FIX 67 secret-name canon).

    Returns the module, or None when it cannot be imported. Fails OPEN by
    design: a missing or broken canon degrades resolution to the exact name,
    it never raises and never takes scoring down.
    """
    global _SECRET_HELPER, _SECRET_HELPER_TRIED
    if _SECRET_HELPER_TRIED:
        return _SECRET_HELPER
    _SECRET_HELPER_TRIED = True
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import secret_helper  # noqa: F401  (sibling module, same directory)
        _SECRET_HELPER = secret_helper
    except Exception:
        _SECRET_HELPER = None
    return _SECRET_HELPER


def _alias_family(name: str) -> list:
    """Every accepted name for `name`, canon-ordered, `name` always included.

    An unknown name is its own family, so non-secret settings (e.g.
    OLLAMA_CLOUD_URL) never pick up an unrelated alias.
    """
    family = [name]
    helper = _secret_helper()
    if helper is not None:
        try:
            for alias in helper.alias_list(helper.canonical_for(name)):
                if alias and alias not in family:
                    family.append(alias)
        except Exception:
            pass
    return family


#: Explicit client-root pins, in the order presentation_job.oc_paths.root()
#: reads them. When one is set it names THE installation this process belongs
#: to, so it becomes the only root searched.
_ROOT_PIN_NAMES = ("OPENCLAW_ROOT", "OC_ROOT", "OC_CONFIG")


def _root_pin(view) -> str:
    """The explicit client-root pin for this invocation, or "".

    Only an absolute, non-"/" path counts; a relative or empty pin is treated
    as no pin at all rather than silently redirecting the search somewhere
    unintended.
    """
    for name in _ROOT_PIN_NAMES:
        pinned = str(view.get(name) or "").strip()
        if pinned and os.path.isabs(pinned) and pinned.rstrip(os.sep):
            return pinned
    return ""


def _openclaw_roots(environ=None) -> list:
    """Ordered OpenClaw roots for THIS invocation.

    A pinned root is the ONLY root returned: a pin means "this installation",
    and a credential search must never spill into another one -- the same
    boundary presentation_job.oc_paths enforces. Unpinned, the order is the
    container root first (/data/.openclaw -- VPS) then this user's HOME root
    (~/.openclaw -- Mac), matching shared-utils/secret_helper's candidate
    order. NOTE: that VPS-first order is also applied to openclaw.json, where
    this module previously looked under HOME first. The two can only disagree
    on a box that has BOTH roots, which oc_paths.root() already treats as a
    configuration error requiring OPENCLAW_ROOT; on every single-root box the
    resolved file is identical.
    """
    view = os.environ if environ is None else environ
    pinned = _root_pin(view)
    if pinned:
        return [pinned]
    home = str(view.get("HOME") or "").strip() or os.path.expanduser("~")
    return ["/data/.openclaw", os.path.join(home, ".openclaw")]


def _secret_store_files(environ=None) -> list:
    """Ordered secrets-store candidates for THIS invocation.

    Order: an explicit OPENCLAW_SECRETS pin first (the same override
    presentation_job.oc_paths honours), then every root _openclaw_roots()
    selects, then ~/.env -- the last only when no root is pinned, since a
    pinned root means "this installation" and ~/.env belongs to the HOME one.
    Rebuilt from the live environment on every call so a process running with
    a redirected HOME or a pinned root reads its OWN store.
    """
    view = os.environ if environ is None else environ
    files = []
    pin = str(view.get("OPENCLAW_SECRETS") or "").strip()
    if pin:
        files.append(pin)
    for root in _openclaw_roots(view):
        for relative in _STORE_RELATIVE_PATHS:
            files.append(os.path.join(root, relative))
    if not _root_pin(view):
        home = str(view.get("HOME") or "").strip() or os.path.expanduser("~")
        files.append(os.path.join(home, ".env"))
    # DELIBERATELY NOT unioned with secret_helper.env_file_candidates().
    # That module's list is a module-level constant whose ~ was expanded ONCE,
    # at import, against whatever HOME the process had then. Unioning it in
    # would let a HOME-redirected child read the store of a DIFFERENT
    # installation -- the exact borrowing presentation_job.oc_paths refuses --
    # and it would also make any "do the two lists agree?" test vacuous, since
    # the shared list would be a subset of this one by construction. The two
    # lists are held together by a real comparison instead:
    # test_f25_llm_score_secrets.py::test_candidate_stores_cover_every_shared_candidate
    # computes both in one fresh interpreter under one HOME and fails if this
    # list has drifted behind the shared one.
    ordered, seen = [], set()
    for path in files:
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _parse_store(path: str) -> dict:
    """NAME -> VALUE for ONE store file; {} for one that cannot be read.

    An unreadable store is a store that answers nothing, never an exception
    that kills a scoring pass. Line semantics are the ones every reader in
    this repo already uses (secret_helper._parse_env_file,
    presentation_job.env_store.parse_store): strip, skip blanks and
    #-comments, accept an optional `export ` prefix, split on the FIRST "=",
    strip one matching pair of surrounding quotes. The file is PARSED, never
    sourced, so it cannot execute anything.
    """
    values = {}
    try:
        if not os.path.isfile(path):
            return values
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                name, _, value = line.partition("=")
                name, value = name.strip(), value.strip()
                if not _ENV_NAME_RE.match(name):
                    continue
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                values.setdefault(name, value)
    except OSError:
        return values
    return values


def _store_lookup(key: str, environ=None) -> str:
    """First non-blank value for `key` (or any alias) across the stores.

    Store order is the outer loop -- the FIRST store that answers wins, and
    later stores only fill gaps, matching env_store.resolve(). A blank
    assignment in a store is skipped exactly as a blank in the process
    environment is: an empty `OPENROUTER_API_KEY=` line in the first store
    must not block the real value a later store carries.
    """
    family = _alias_family(key)
    for path in _secret_store_files(environ):
        parsed = _parse_store(path)
        if not parsed:
            continue
        for alias in family:
            value = str(parsed.get(alias) or "").strip()
            if value:
                return value
    return ""


def _openclaw_env(environ=None) -> dict:
    """Read .env-style values from the openclaw.json env block into a dict.

    Roots come from _openclaw_roots(), so a pinned root confines this lookup
    to the same installation the store lookup uses -- one root authority for
    both, instead of two lists that can disagree.

    BOTH env shapes are accepted. The live shape on every box measured
    2026-09-06 is ``{"env": {"vars": {NAME: VALUE}}}`` -- reading only the
    top level of ``env`` (what this function did before F25) resolved
    nothing at all there, which is why the documented
    "OPENROUTER_API_KEY (already in ~/.openclaw/openclaw.json)" fallback had
    never once fired. Flat ``{"env": {NAME: VALUE}}`` is still honoured so
    nothing that resolved before stops resolving.
    """
    paths = [os.path.join(root, "openclaw.json")
             for root in _openclaw_roots(environ)]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    data = json.load(f)
                env = data.get("env", {}) or {}
                if not isinstance(env, dict):
                    return {}
                merged = {k: v for k, v in env.items() if isinstance(v, str)}
                nested = env.get("vars")
                if isinstance(nested, dict):
                    for k, v in nested.items():
                        if isinstance(v, str):
                            merged.setdefault(k, v)
                return merged
            except Exception:
                pass
    return {}


def _env(key: str, default: str = "") -> str:
    """Resolve a name through the F25 precedence chain (see the block above).

    process env (exact, then alias) -> secrets stores -> openclaw.json env
    block -> `default`. Every step ignores BLANK values, at every layer: a
    blank is the absence this fix is about, never an override.
    """
    view = os.environ
    exact = str(view.get(key) or "").strip()
    if exact:
        return exact
    family = _alias_family(key)
    for alias in family:
        value = str(view.get(alias) or "").strip()
        if value:
            return value
    value = _store_lookup(key, view)
    if value:
        return value
    block = _openclaw_env(view)
    for alias in family:
        value = str(block.get(alias) or "").strip()
        if value:
            return value
    return default


def env_report(names=None) -> str:
    """REDACTED resolution report: presence, LENGTH and source per name.

    This is the ONLY surface in this module that says anything about a
    credential, and length is the only fact about a value it will ever
    state -- never the value, never a prefix of it. Safe to send straight to
    a log.
    """
    watched = list(names) if names else [
        "OLLAMA_CLOUD_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_CLOUD_URL",
    ]
    lines = []
    for name in watched:
        exact = str(os.environ.get(name) or "").strip()
        if exact:
            source, value = "process-env", exact
        else:
            alias_hit = ""
            for alias in _alias_family(name):
                alias_hit = str(os.environ.get(alias) or "").strip()
                if alias_hit:
                    break
            if alias_hit:
                source, value = "process-env-alias", alias_hit
            else:
                value = _store_lookup(name)
                if value:
                    source = "secrets-store"
                else:
                    block = _openclaw_env()
                    for alias in _alias_family(name):
                        value = str(block.get(alias) or "").strip()
                        if value:
                            break
                    source = "openclaw.json" if value else "UNRESOLVED"
        if value:
            lines.append(f"{name}: PRESENT (len {len(value)}, source {source})")
        else:
            # WORDED CAREFULLY. Some of these names carry a documented
            # in-code default (OLLAMA_CLOUD_URL), so "unresolved" is not the
            # same as "this call is dead" -- say what was measured, and let
            # the caller's default speak for itself.
            lines.append(
                f"{name}: NOT RESOLVED from the process env, any secrets "
                f"store, or the openclaw.json env block -- a caller with no "
                f"in-code default treats it as absent"
            )
    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────
# Cache
# ───────────────────────────────────────────────────────────────────────

def _cache_path() -> Path:
    """Cache lives under workspace/data/, falling back to /tmp."""
    candidates = [
        Path.home() / "clawd" / "data" / "llm-score-cache.sqlite",
        Path.home() / ".openclaw" / "workspace" / "data" / "llm-score-cache.sqlite",
        Path("/tmp") / "openclaw-llm-score-cache.sqlite",
    ]
    for c in candidates:
        try:
            c.parent.mkdir(parents=True, exist_ok=True)
            return c
        except OSError:
            continue
    return candidates[-1]


def _cache_key(persona_id: str, layer: str, persona_summary: str, context: str) -> str:
    h = hashlib.sha256()
    h.update(persona_id.encode("utf-8"))
    h.update(b"|")
    h.update(layer.encode("utf-8"))
    h.update(b"|")
    h.update(persona_summary.encode("utf-8"))
    h.update(b"|")
    h.update(context.encode("utf-8"))
    return h.hexdigest()


def _cache_get(key: str):
    try:
        path = _cache_path()
        conn = sqlite3.connect(str(path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_cache (
                key TEXT PRIMARY KEY,
                score REAL NOT NULL,
                reasoning TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        cur = conn.execute(
            "SELECT score, reasoning, model, created_at FROM score_cache WHERE key = ?",
            (key,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        score, reasoning, model, created_at = row
        if time.time() - created_at > CACHE_TTL_SECONDS:
            return None
        return {"score": float(score), "reasoning": reasoning, "model": model, "cached": True}
    except sqlite3.Error:
        return None


def _cache_put(key: str, score: float, reasoning: str, model: str):
    try:
        path = _cache_path()
        conn = sqlite3.connect(str(path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_cache (
                key TEXT PRIMARY KEY,
                score REAL NOT NULL,
                reasoning TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO score_cache (key, score, reasoning, model, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (key, score, reasoning, model, int(time.time())),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


# ───────────────────────────────────────────────────────────────────────
# Prompt
# ───────────────────────────────────────────────────────────────────────

LAYER_PROMPTS = {
    "mission": (
        "How well does this persona's philosophy align with the company's "
        "mission?"
    ),
    "owner_values": (
        "How well does this persona's methodology match the company owner's "
        "behavioral identity and stated values?"
    ),
    "company_kpis": (
        "How well does this persona's expertise advance the company-level "
        "KPIs?"
    ),
    "dept_kpis": (
        "How well does this persona's methodology fit this specific "
        "department's KPIs and operational goals?"
    ),
}

SCORING_INSTRUCTIONS = """You are a persona-fit evaluator for a zero-human company.
Score on a 0.0–1.0 continuous scale where:
  0.0–0.3 = poor fit (philosophy clashes, wrong domain, or actively counterproductive)
  0.4–0.6 = neutral / generic fit (could work, no strong signal either way)
  0.7–0.85 = good fit (clear alignment, persona advances this dimension)
  0.86–1.0 = excellent fit (this persona is a top-tier match for this dimension)

Return ONLY a JSON object — no markdown, no preamble:
{"score": <float 0.0-1.0>, "reasoning": "<one sentence why>"}

Do NOT default to 0.7 when uncertain. If signal is genuinely weak in both
directions, return 0.5 with reasoning="insufficient signal".
"""


def _build_prompt(layer: str, persona_id: str, persona_summary: str, context: str) -> str:
    question = LAYER_PROMPTS.get(layer, "How well does this persona fit?")
    return (
        f"{SCORING_INSTRUCTIONS}\n\n"
        f"Question: {question}\n\n"
        f"Persona: {persona_id}\n"
        f"Persona summary:\n{persona_summary[:2000]}\n\n"
        f"Context (company / owner / KPIs / dept):\n{context[:2000]}\n"
    )


# ───────────────────────────────────────────────────────────────────────
# HTTP — OpenAI-completions-compatible
# ───────────────────────────────────────────────────────────────────────

def _post_chat(url: str, headers: dict, body: dict, timeout: int = HTTP_TIMEOUT_SECONDS) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _extract_message(payload: dict) -> str:
    """Extract text from an OpenAI-compatible chat-completion payload.

    DeepSeek V4 Pro (and other thinking/reasoning models) may return
    ``content: null`` and put the actual text in ``reasoning_details`` or
    ``reasoning``.  Crash-guard order:
      1. content  — non-null, non-empty string → use it
      2. reasoning_details (list of {text}|{thinking} blocks) → concat text
      3. reasoning (str) — DeepSeek legacy field → use it
      4. "" — all fields missing / null → caller treats as unparseable
    """
    try:
        msg = payload["choices"][0]["message"]
        # Primary: standard content field
        content = msg.get("content")
        if content is not None and str(content).strip():
            return str(content).strip()
        # Fallback 1: reasoning_details (array of typed blocks)
        rd = msg.get("reasoning_details")
        if rd and isinstance(rd, list):
            parts = []
            for block in rd:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("thinking") or ""
                    if text:
                        parts.append(str(text))
            if parts:
                return " ".join(parts).strip()
        # Fallback 2: reasoning (plain string, DeepSeek legacy)
        reasoning = msg.get("reasoning")
        if reasoning and str(reasoning).strip():
            return str(reasoning).strip()
        return ""
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _parse_score_json(text: str) -> dict:
    """Pull {score, reasoning} out of a model response. Resilient to fluff."""
    if not text:
        return {"score": None, "reasoning": "empty response"}
    # Try direct parse
    try:
        obj = json.loads(text)
        score = float(obj.get("score", -1))
        if 0.0 <= score <= 1.0:
            return {"score": score, "reasoning": str(obj.get("reasoning", ""))[:500]}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # Try to find a JSON object inside the text
    match = re.search(r'\{[^{}]*"score"\s*:\s*([0-9.]+)[^{}]*\}', text)
    if match:
        try:
            score = float(match.group(1))
            if 0.0 <= score <= 1.0:
                reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text)
                return {
                    "score": score,
                    "reasoning": reasoning_match.group(1)[:500] if reasoning_match else "parsed from non-JSON",
                }
        except (TypeError, ValueError):
            pass
    return {"score": None, "reasoning": f"parse failed: {text[:160]}"}


# ───────────────────────────────────────────────────────────────────────
# Provider attempts
# ───────────────────────────────────────────────────────────────────────

def _attempt_ollama_cloud(prompt: str) -> dict:
    api_key = _env("OLLAMA_CLOUD_API_KEY")
    if not api_key:
        return {"ok": False, "error": "OLLAMA_CLOUD_API_KEY not set", "model": "ollama/deepseek-v4-pro:cloud"}
    base_url = _env("OLLAMA_CLOUD_URL", "https://ollama.com/api")
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "deepseek-v4-pro:cloud",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    try:
        payload = _post_chat(url, headers, body)
        text = _extract_message(payload)
        parsed = _parse_score_json(text)
        if parsed["score"] is None:
            return {"ok": False, "error": f"unparseable: {parsed['reasoning']}", "model": "ollama/deepseek-v4-pro:cloud"}
        return {"ok": True, "score": parsed["score"], "reasoning": parsed["reasoning"],
                "model": "ollama/deepseek-v4-pro:cloud"}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "model": "ollama/deepseek-v4-pro:cloud"}


def _attempt_openrouter(prompt: str, model_id: str) -> dict:
    api_key = _env("OPENROUTER_API_KEY")
    if not api_key:
        return {"ok": False, "error": "OPENROUTER_API_KEY not set", "model": model_id}
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/trevorotts1/openclaw-onboarding",
        "X-Title": "OpenClaw persona-selector",
    }
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
        # Ask OpenRouter thinking models to suppress reasoning tokens so content
        # is always a plain string — avoids the content=null crash.
        # Non-thinking models silently ignore this field.
        "reasoning": {"exclude": True},
    }
    try:
        payload = _post_chat(url, headers, body)
        text = _extract_message(payload)
        parsed = _parse_score_json(text)
        if parsed["score"] is None:
            return {"ok": False, "error": f"unparseable: {parsed['reasoning']}", "model": model_id}
        return {"ok": True, "score": parsed["score"], "reasoning": parsed["reasoning"],
                "model": model_id}
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, AttributeError, KeyError, TypeError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "model": model_id}


# ───────────────────────────────────────────────────────────────────────
# Public API
# ───────────────────────────────────────────────────────────────────────

def score_layer(
    persona_id: str,
    layer: str,
    persona_blueprint_summary: str,
    context: str,
    use_cache: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Score a single persona-layer fit using the configured LLM chain.

    Returns:
        {
          "score":     float in [0.0, 1.0],
          "reasoning": str,
          "model":     str   — which model returned the score
          "cached":    bool  — True if served from cache
          "fallback":  bool  — True if all models failed and we returned NEUTRAL_FALLBACK_SCORE
        }
    """
    key = _cache_key(persona_id, layer, persona_blueprint_summary, context)

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return {**cached, "fallback": False}

    prompt = _build_prompt(layer, persona_id, persona_blueprint_summary, context)

    chain = [
        ("ollama-cloud-deepseek-pro", lambda: _attempt_ollama_cloud(prompt)),
        ("openrouter-deepseek-pro",   lambda: _attempt_openrouter(prompt, "deepseek/deepseek-v4-pro")),
        ("openrouter-gemini-lite",    lambda: _attempt_openrouter(prompt, "google/gemini-3.1-flash-lite")),
    ]

    last_error = ""
    for name, attempt in chain:
        result = attempt()
        if result.get("ok"):
            if verbose:
                print(f"[llm_score] {layer}/{persona_id} via {result['model']} → {result['score']:.2f}",
                      file=sys.stderr)
            _cache_put(key, result["score"], result["reasoning"], result["model"])
            return {
                "score": result["score"],
                "reasoning": result["reasoning"],
                "model": result["model"],
                "cached": False,
                "fallback": False,
            }
        last_error = f"{name}: {result.get('error', 'unknown')}"
        if verbose:
            print(f"[llm_score] {name} failed: {result.get('error')}", file=sys.stderr)

    return {
        "score": NEUTRAL_FALLBACK_SCORE,
        "reasoning": f"all models failed: {last_error[:200]}",
        "model": "fallback",
        "cached": False,
        "fallback": True,
    }


def summarize_persona_blueprint(persona_id: str, max_chars: int = 2000) -> str:
    """
    Read the persona blueprint (if it exists) and return a short summary
    suitable for prompts. Looks under workspace/coaching-personas/personas/<id>/blueprint.md
    falling back to persona-id only if not found.
    """
    candidates = [
        Path.home() / "clawd" / "coaching-personas" / "personas" / persona_id / "blueprint.md",
        Path.home() / ".openclaw" / "workspace" / "coaching-personas" / "personas" / persona_id / "blueprint.md",
        Path("/data/.openclaw/workspace/coaching-personas/personas") / persona_id / "blueprint.md",
    ]
    for c in candidates:
        try:
            if c.exists():
                text = c.read_text(encoding="utf-8", errors="replace")
                return text[:max_chars]
        except OSError:
            continue
    return f"(no blueprint found for {persona_id})"


if __name__ == "__main__":
    # Quick smoke test
    import argparse
    parser = argparse.ArgumentParser(description="LLM-scored persona-layer fit")
    parser.add_argument("--persona")
    parser.add_argument("--layer", choices=list(LAYER_PROMPTS.keys()))
    parser.add_argument("--context")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--env-report", action="store_true",
        help="print the REDACTED credential-resolution report (presence, "
             "LENGTH and source per name; never a value) and exit. Use this "
             "to tell an env-loading failure apart from a provider failure.")
    args = parser.parse_args()

    if args.env_report:
        print(env_report())
        raise SystemExit(0)

    missing = [n for n in ("persona", "layer", "context")
               if not getattr(args, n)]
    if missing:
        parser.error("the following arguments are required: "
                     + ", ".join("--" + n for n in missing))

    summary = summarize_persona_blueprint(args.persona)
    result = score_layer(args.persona, args.layer, summary, args.context, verbose=args.verbose)
    print(json.dumps(result, indent=2))
