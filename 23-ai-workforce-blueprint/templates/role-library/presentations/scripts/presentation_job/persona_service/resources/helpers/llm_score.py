"""
llm_score.py — LLM-backed scoring helper for OpenClaw.

Used by Skill 23's persona-selector to evaluate Layers 1-4 (mission /
owner_values / company_kpis / dept_kpis) against persona blueprints.
Returns a single float in [0.0, 1.0] with a short reasoning string.

Per company policy (memory: feedback-no-anthropic-for-subagents) no
Anthropic models are used in this pipeline. THE CHAIN IS DATA —
default_scoring_chain() is the one ordered table and scoring_chain() is what
score_layer walks. Every step speaks the same OpenAI-compatible
/chat/completions shape, a step whose key does not resolve is SKIPPED
SILENTLY without opening a socket, and the first HTTP 200 carrying a
parseable {score, reasoning} wins:

    1. ollama-cloud     minimax-m3                    measured 3.1s 2026-09-21
    2. openrouter       minimax/minimax-m3            $0.30/M in, $1.20/M out
    3. agnes            agnes-3.0-flash               falls back once to
                                                      agnes-2.5-flash on a
                                                      400/404 (not served)
    4. deepseek-direct  deepseek-flash                = DeepSeek-V4.1-Flash
    5. ollama-cloud     ollama_cloud_model()          backstop, measured 1.5s
    6. openrouter       google/gemini-3.1-flash-lite  backstop, cheapest

Step 5 is the one id a box can move on its own: it resolves through
ollama_cloud_model() / OLLAMA_CLOUD_SCORING_MODEL, the same value
decompose-task.py and verify-persona-adherence.py use, so a provider
retiring a tag stays a config change. openrouter_model() /
OPENROUTER_SCORING_MODEL still serves those two callers; this chain routes
its OpenRouter budget through MiniMax and Gemini Lite instead.

Endpoints and credentials, one line each:

    ollama-cloud     <OLLAMA_CLOUD_URL>/chat/completions, default base
                     https://ollama.com/v1 — NOT /api, which 404s.
                     Key: OLLAMA_CLOUD_API_KEY first; if that is unset or the
                     call comes back 401, the gateway's OWN provider key from
                     openclaw.json is tried once as a last resort — see
                     ollama_cloud_api_keys().
    openrouter       https://openrouter.ai/api/v1/chat/completions.
                     Key: OPENROUTER_API_KEY.
    agnes            https://apihub.agnes-ai.com/v1/chat/completions.
                     Key: AGNES_API_KEY (the canon makes AGNES_AI_API_KEY and
                     AGNES_KEY the same family), then the gateway's own
                     provider key — see agnes_api_keys().
    deepseek-direct  https://api.deepseek.com/chat/completions.
                     Key: DEEPSEEK_API_KEY.

LLM_SCORE_CHAIN replaces the whole table: a comma list of "provider:model"
split on the FIRST colon so a tagged Ollama id keeps its own, e.g.
"ollama-cloud:minimax-m3,openrouter:google/gemini-3.1-flash-lite". An entry
naming an unknown provider is skipped with one warning to stderr.

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

#: Ollama Cloud's OpenAI-compatible chat surface lives under /v1, never /api.
#: The default here used to be https://ollama.com/api, so step 1 of the chain
#: POSTed to /api/chat/completions -- measured on a live client box 2026-09-21,
#: that path answers HTTP 404 `path "/api/chat/completions" not found`, while
#: the identical request to /v1/chat/completions answers 200 in 0.7s. Step 1 of
#: this chain had therefore NEVER once succeeded: every scoring call fell
#: through to paid OpenRouter at ~4s. OLLAMA_CLOUD_URL is still honoured, but a
#: box still pinned to the old https://ollama.com/api default is normalised to
#: /v1 rather than left broken -- see ollama_cloud_chat_url().
OLLAMA_CLOUD_DEFAULT_URL = "https://ollama.com/v1"

#: DEFAULTS, not hard-codes. A provider renaming or retiring a tag must be a
#: config change on the box, never a code change and a fleet roll -- the cloud
#: tag deepseek-v4-pro:cloud was deleted out from under this chain on
#: 2026-08-17 and every scoring call failed silently until someone read a
#: 404. GET https://ollama.com/api/tags on 2026-09-21 lists exactly
#: deepseek-v4.1-flash, deepseek-v4-flash:0731 and deepseek-v4-pro:0813;
#: openrouter.ai/api/v1/models lists deepseek/deepseek-v4.1-flash at 1048576
#: context, $0.15/M prompt and $0.60/M completion. Flash is the scoring
#: chain's model on both steps: these calls are 200-token judgements, not
#: generation.
OLLAMA_CLOUD_MODEL_DEFAULT = "deepseek-v4.1-flash"
OPENROUTER_MODEL_DEFAULT = "deepseek/deepseek-v4.1-flash"


def ollama_cloud_model() -> str:
    """Step-1 model tag; OLLAMA_CLOUD_SCORING_MODEL overrides the default."""
    return _env("OLLAMA_CLOUD_SCORING_MODEL", OLLAMA_CLOUD_MODEL_DEFAULT)


def ollama_cloud_model_id() -> str:
    """The provider-qualified id this module REPORTS for a step-1 answer."""
    return "ollama/" + ollama_cloud_model()


def openrouter_model() -> str:
    """The OpenRouter DeepSeek id; OPENROUTER_SCORING_MODEL overrides it.

    NOT a step of the chain below — the chain spends its OpenRouter budget on
    MiniMax and Gemini Lite. This is the id decompose-task.py and
    verify-persona-adherence.py use for their own single bounded calls, kept
    overridable for the same reason ollama_cloud_model() is.
    """
    return _env("OPENROUTER_SCORING_MODEL", OPENROUTER_MODEL_DEFAULT)


#: The other three transports. All four are OpenAI-compatible
#: /chat/completions surfaces, which is why ONE attempt function
#: (_attempt_chat) serves every step and the chain can stay a data table.
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
DEEPSEEK_DIRECT_CHAT_URL = "https://api.deepseek.com/chat/completions"

#: The chain's own model ids. Measured on a live client box 2026-09-21 with a
#: scoring-shaped request, max_tokens 200: deepseek-v4.1-flash 1.5s,
#: minimax-m3 3.1s, glm-5.3-flash 3.3s, OpenRouter DeepSeek ~4s.
OLLAMA_CLOUD_CHAIN_MODEL = "minimax-m3"
OPENROUTER_CHAIN_MODEL = "minimax/minimax-m3"
OPENROUTER_BACKSTOP_MODEL = "google/gemini-3.1-flash-lite"

#: agnes-3.0-flash is listed on an authenticated GET
#: https://apihub.agnes-ai.com/v1/models (2026-09-21), but a given box's Agnes
#: provider may not carry it. A 400/404 on this id retries once with the 2.5
#: tag every account has — see _attempt_chat's model_fallback.
AGNES_MODEL = "agnes-3.0-flash"
AGNES_FALLBACK_MODEL = "agnes-2.5-flash"

#: DeepSeek's own API. `deepseek-flash` is DeepSeek-V4.1-Flash
#: (api-docs.deepseek.com/quick_start/pricing, read 2026-09-21).
DEEPSEEK_DIRECT_MODEL = "deepseek-flash"

CACHE_TTL_SECONDS = 30 * 24 * 60 * 60   # 30 days

#: PER-STEP HTTP budget. A scoring call that has not answered in 20s is worth
#: less than the next step in the chain: every model above was measured at
#: 1.5-4s, and the selector that calls this runs ~22 of these inside the
#: Command Center's spawn budget. 30s bought nothing and cost a whole step.
HTTP_TIMEOUT_SECONDS = 20
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

    THREAD SAFETY. score_layer() now runs concurrently (persona-selector-v2
    scores its finalists on a thread pool), so _SECRET_HELPER_TRIED is set only
    AFTER _SECRET_HELPER has its final value. Setting it first left a window in
    which a second thread saw TRIED=True with the module still None and
    silently degraded to exact-name-only resolution -- a key stored under an
    ALIAS would not have resolved for that one call. A racing thread now simply
    redoes the import, which sys.modules makes free and idempotent.
    """
    global _SECRET_HELPER, _SECRET_HELPER_TRIED
    if _SECRET_HELPER_TRIED:
        return _SECRET_HELPER
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import secret_helper  # noqa: F401  (sibling module, same directory)
        _SECRET_HELPER = secret_helper
    except Exception:
        _SECRET_HELPER = None
    _SECRET_HELPER_TRIED = True
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
        "OLLAMA_CLOUD_API_KEY", "OPENROUTER_API_KEY", "AGNES_API_KEY",
        "DEEPSEEK_API_KEY", "OLLAMA_CLOUD_URL", "LLM_SCORE_CHAIN",
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

def ollama_cloud_chat_url() -> str:
    """The Ollama Cloud chat-completions URL for THIS box.

    OLLAMA_CLOUD_URL is honoured verbatim except for one normalisation: a box
    still carrying this module's OLD default, https://ollama.com/api, is
    rewritten to /v1. That old base makes the request 404 (see
    OLLAMA_CLOUD_DEFAULT_URL), so honouring it literally would leave every
    already-provisioned box on the broken path this fix exists to close.
    """
    base = _env("OLLAMA_CLOUD_URL", OLLAMA_CLOUD_DEFAULT_URL).rstrip("/")
    if base.endswith("/api"):
        base = base[: -len("/api")] + "/v1"
    return base + "/chat/completions"


#: An apiKey field that NAMES an environment variable instead of carrying a
#: secret: "${OLLAMA_CLOUD_API_KEY}", "$OLLAMA_CLOUD_API_KEY", "env:NAME", or
#: the bare SHOUTING_NAME. Resolving one of those as a bearer token would send
#: the literal string to the provider and earn a 401.
_ENV_REF_RE = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$")
_SHOUTING_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _is_literal_key(value: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate:
        return False
    if _ENV_REF_RE.match(candidate):
        return False
    if candidate.lower().startswith(("env:", "secret:", "file:")):
        return False
    if _SHOUTING_NAME_RE.match(candidate):
        return False
    return True


def _openclaw_provider_key(host_fragment: str, environ=None) -> str:
    """The gateway's OWN apiKey for the provider whose baseUrl names `host_fragment`.

    Read from models.providers in the openclaw.json of the SAME installation
    _openclaw_roots() selects -- no new file discovery, and a pinned root still
    confines the search to one client. Both shapes the config takes are
    accepted: providers as a NAME -> config mapping, and providers as a list of
    configs. Only a LITERAL key counts (_is_literal_key); a field that merely
    names an env var is not a credential. Returns "" when there is nothing to
    return, and NEVER logs or raises -- the value goes straight into an
    Authorization header and nowhere else.
    """
    for root in _openclaw_roots(environ):
        path = os.path.join(root, "openclaw.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as handle:
                data = json.load(handle)
            providers = ((data.get("models") or {}).get("providers") or {})
            entries = providers.values() if isinstance(providers, dict) else providers
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                base = str(entry.get("baseUrl") or entry.get("base_url") or "")
                if host_fragment not in base:
                    continue
                key = str(entry.get("apiKey") or entry.get("api_key") or "").strip()
                if _is_literal_key(key):
                    return key
        except Exception:
            continue
    return ""


def ollama_cloud_api_keys() -> list:
    """Bearer tokens to try against Ollama Cloud, best first.

    1. OLLAMA_CLOUD_API_KEY through the F25 chain (process env, aliases, the
       box's secrets stores, the openclaw.json env block).
    2. LAST RESORT -- the key the OpenClaw gateway itself uses for its
       ollama.com provider, from models.providers in openclaw.json.

    Measured on a live client box 2026-09-21: the resolved OLLAMA_CLOUD_API_KEY
    answered 401 on ollama.com while the gateway's provider key answered 200
    for the identical request. The gateway key is the proven-working one, so it
    is tried when the first name resolves nothing AND when the first key is
    rejected -- see _attempt_ollama_cloud. This is RESOLUTION ONLY: nothing is
    written back to any env file or store.
    """
    keys = []
    env_key = _env("OLLAMA_CLOUD_API_KEY")
    if env_key:
        keys.append(env_key)
    provider_key = _openclaw_provider_key("ollama.com")
    if provider_key and provider_key not in keys:
        keys.append(provider_key)
    return keys


def openrouter_api_keys() -> list:
    """Bearer tokens for OpenRouter: the resolved OPENROUTER_API_KEY, or none.

    No gateway-provider fallback here, deliberately. OpenRouter is the step
    that has always resolved from its env name, and reaching into
    openclaw.json for it would be new credential behaviour this chain does not
    need. Ollama Cloud and Agnes get that fallback because their env name is
    the one measured absent or rejected on live boxes.
    """
    key = _env("OPENROUTER_API_KEY")
    return [key] if key else []


def agnes_api_keys() -> list:
    """Bearer tokens for Agnes AI, best first.

    1. AGNES_API_KEY through the F25 chain. The secret-name canon
       (secret_names.json) puts AGNES_AI_API_KEY and AGNES_KEY in the same
       family, so a box that wrote any of the three resolves here.
    2. LAST RESORT — the gateway's own key for the provider whose baseUrl
       names apihub.agnes-ai.com, through the SAME _openclaw_provider_key()
       the Ollama Cloud step uses. No new file discovery, a pinned root still
       confines the search to one installation, and only a LITERAL key counts.

    Resolution only: nothing is written back to any env file or store.
    """
    keys = []
    env_key = _env("AGNES_API_KEY")
    if env_key:
        keys.append(env_key)
    provider_key = _openclaw_provider_key("agnes-ai.com")
    if provider_key and provider_key not in keys:
        keys.append(provider_key)
    return keys


def deepseek_direct_api_keys() -> list:
    """Bearer tokens for DeepSeek's own API: the resolved DEEPSEEK_API_KEY.

    The canon also accepts DEEPSEEK_KEY and DEEP_SEEK_API_KEY. Most boxes
    carry no DeepSeek credential at all, and that step then costs nothing:
    a chain step with no key is skipped without touching the network.
    """
    key = _env("DEEPSEEK_API_KEY")
    return [key] if key else []


def _attempt_chat(provider: str, model: str, prompt: str, url: str, keys: list,
                  extra_headers: dict = None, extra_body: dict = None,
                  model_fallback: str = "") -> dict:
    """ONE chain step. -> {ok, score, reasoning, model} | {ok: False, error, model}

    `model` in the returned dict is always the STEP LABEL, "<provider>/<model>"
    — so the winning step's own name is what score_layer caches and what
    persona_selection_log records. The chain carries TWO Ollama Cloud steps and
    TWO OpenRouter steps, so a label naming only the family could not say which
    one served a score. ollama_cloud_model_id() is unchanged and still reports
    the "ollama/<tag>" form for the callers that are not chain steps.

    NO KEY IS A SKIP, NOT A FAILURE. An empty `keys` returns ok=False without
    opening a socket, and the caller simply advances. That is what lets the
    table carry a DeepSeek step on a fleet where almost no box has a DeepSeek
    credential.

    KEY ORDER. A 401 means THIS key is rejected, not that the provider is
    down, so the next candidate is tried. Any other HTTP status and any
    transport error ends the step — a 500 is the provider being down, and
    retrying would double every outage's cost.

    MODEL FALLBACK. With `model_fallback` set, an HTTP 400 or 404 retries once
    with that id, keeping the keys that already authenticated. Those two codes
    are how an OpenAI-compatible surface says "I do not serve that model".
    This is deliberately broader than matching the error BODY for "model not
    found": the wording is provider-specific and reading the body can itself
    fail, while the retry costs one call against a step that has already
    failed. The retry carries no fallback of its own, so it happens at most
    once.

    NO KEY VALUE IS EVER RETURNED OR LOGGED. A key goes into an Authorization
    header and nowhere else; urllib's HTTPError carries the status line, never
    the request headers.
    """
    label = f"{provider}/{model}"
    if not keys:
        return {"ok": False, "error": "no API key resolved", "model": label}

    headers_base = {"Content-Type": "application/json"}
    if extra_headers:
        headers_base.update(extra_headers)
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    if extra_body:
        body.update(extra_body)

    outcome = {"ok": False, "error": "no attempt made", "model": label}
    for index, api_key in enumerate(keys):
        headers = dict(headers_base)
        headers["Authorization"] = f"Bearer {api_key}"
        try:
            payload = _post_chat(url, headers, body)
        except urllib.error.HTTPError as e:
            # HTTPError before URLError: it is a SUBCLASS, and only it carries
            # .code.
            outcome = {"ok": False, "error": f"HTTPError: {e}", "model": label}
            if e.code == 401 and index + 1 < len(keys):
                continue
            if e.code in (400, 404) and model_fallback:
                return _attempt_chat(provider, model_fallback, prompt, url,
                                     keys[index:], extra_headers, extra_body)
            return outcome
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError,
                # OSError, NOT socket.timeout: on Python 3.9 `socket.timeout`
                # is an OSError but NOT a TimeoutError — they were unified only
                # in 3.10. A read timeout on a step therefore ESCAPED this
                # handler on 3.9, propagated out of pool.map in the selector's
                # score_personas, and killed the whole persona selection (rc 1)
                # instead of falling through to the next step in the chain.
                # OSError covers socket.timeout on EVERY version, plus the
                # connection-reset family. Do not narrow it back to
                # TimeoutError. urllib.error.HTTPError is caught above, so it
                # still takes its own 401/400/404 path.
                OSError,
                AttributeError, KeyError, TypeError) as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}",
                    "model": label}
        text = _extract_message(payload)
        parsed = _parse_score_json(text)
        if parsed["score"] is None:
            return {"ok": False, "error": f"unparseable: {parsed['reasoning']}",
                    "model": label}
        return {"ok": True, "score": parsed["score"],
                "reasoning": parsed["reasoning"], "model": label}
    return outcome


def _step_ollama_cloud(prompt: str, model: str) -> dict:
    return _attempt_chat("ollama-cloud", model, prompt,
                         ollama_cloud_chat_url(), ollama_cloud_api_keys())


def _step_openrouter(prompt: str, model: str) -> dict:
    return _attempt_chat(
        "openrouter", model, prompt, OPENROUTER_CHAT_URL, openrouter_api_keys(),
        extra_headers={
            "HTTP-Referer": "https://github.com/trevorotts1/openclaw-onboarding",
            "X-Title": "OpenClaw persona-selector",
        },
        # Ask OpenRouter thinking models to suppress reasoning tokens so
        # content is always a plain string — avoids the content=null crash.
        # Non-thinking models silently ignore it. It is OpenRouter's OWN
        # extension, so it is not sent to the other three surfaces, where an
        # unknown body field is a 400 waiting to happen.
        extra_body={"reasoning": {"exclude": True}},
    )


def _step_agnes(prompt: str, model: str) -> dict:
    return _attempt_chat(
        "agnes", model, prompt,
        AGNES_BASE_URL.rstrip("/") + "/chat/completions", agnes_api_keys(),
        model_fallback=AGNES_FALLBACK_MODEL if model == AGNES_MODEL else "",
    )


def _step_deepseek_direct(prompt: str, model: str) -> dict:
    return _attempt_chat("deepseek-direct", model, prompt,
                         DEEPSEEK_DIRECT_CHAT_URL, deepseek_direct_api_keys())


#: provider name -> step runner. The ONLY place a provider name is legal,
#: in default_scoring_chain() and in an LLM_SCORE_CHAIN override alike.
_STEP_RUNNERS = {
    "ollama-cloud": _step_ollama_cloud,
    "openrouter": _step_openrouter,
    "agnes": _step_agnes,
    "deepseek-direct": _step_deepseek_direct,
}


def default_scoring_chain() -> list:
    """THE CHAIN, AS DATA — (provider, model) in the operator's order.

    A function and not a module constant for one reason: step 5's tag is box
    CONFIGURATION (ollama_cloud_model(), OLLAMA_CLOUD_SCORING_MODEL), and a
    constant would freeze whatever the environment looked like at import —
    which under launchd and the openclaw cron is nothing at all. Every other
    id here is a literal.

    The order is deliberate and is not a price ranking: the two fastest models
    measured on a live box sit at 1 and 5, with a paid mirror of each in
    between, so no single provider outage empties the chain. A step whose key
    does not resolve is skipped silently, so a box holding only an OpenRouter
    credential simply runs steps 2 and 6 and pays for nothing else.
    """
    return [
        ("ollama-cloud",    OLLAMA_CLOUD_CHAIN_MODEL),
        ("openrouter",      OPENROUTER_CHAIN_MODEL),
        ("agnes",           AGNES_MODEL),
        ("deepseek-direct", DEEPSEEK_DIRECT_MODEL),
        ("ollama-cloud",    ollama_cloud_model()),
        ("openrouter",      OPENROUTER_BACKSTOP_MODEL),
    ]


def scoring_chain() -> list:
    """The ordered [(provider, model)] this box will walk.

    default_scoring_chain() unless LLM_SCORE_CHAIN resolves, in which case the
    override wins OUTRIGHT: an operator naming a chain is naming the whole
    chain, and silently merging the default back in would make the setting
    unreadable. The override is a comma list of "provider:model" split on the
    FIRST colon, so a tagged Ollama id keeps its own
    ("ollama-cloud:deepseek-v4-pro:0813").

    An entry naming an unknown provider is skipped with ONE warning per
    offending name, to stderr. This module degrades; it does not raise, and it
    does not take a scoring pass down over a typo in a setting.
    """
    raw = _env("LLM_SCORE_CHAIN")
    if not raw:
        return default_scoring_chain()
    steps, warned = [], set()
    for item in raw.split(","):
        provider, _, model = item.strip().partition(":")
        provider, model = provider.strip(), model.strip()
        if not provider or not model:
            continue
        if provider not in _STEP_RUNNERS:
            if provider not in warned:
                warned.add(provider)
                print(f"[llm_score] LLM_SCORE_CHAIN: unknown provider "
                      f"{provider!r} — step skipped (known: "
                      f"{', '.join(sorted(_STEP_RUNNERS))})", file=sys.stderr)
            continue
        steps.append((provider, model))
    return steps


# ── Back-compat entry points ───────────────────────────────────────────
# verify-persona-adherence.py imports BOTH of these by name at module level,
# and an ImportError there switches that script's whole LLM path off. They are
# the same two steps the chain runs, under the names that call site uses.

def _attempt_ollama_cloud(prompt: str, model: str = "") -> dict:
    return _step_ollama_cloud(prompt, model or ollama_cloud_model())


def _attempt_openrouter(prompt: str, model_id: str) -> dict:
    return _step_openrouter(prompt, model_id)


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

    # scoring_chain() only ever yields providers _STEP_RUNNERS knows, so the
    # lookup below cannot miss -- an unknown name was already dropped, with a
    # warning, where the override was parsed.
    last_error = "no step ran: the scoring chain resolved to zero steps"
    for provider, model in scoring_chain():
        result = _STEP_RUNNERS[provider](prompt, model)
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
        last_error = f"{result['model']}: {result.get('error', 'unknown')}"
        if verbose:
            print(f"[llm_score] {result['model']} failed: {result.get('error')}",
                  file=sys.stderr)

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
