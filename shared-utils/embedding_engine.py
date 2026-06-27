#!/usr/bin/env python3
"""
PRD 1.8 + onb-gemini — Single embedding engine for the coaching-personas index.

This module is the ONE implementation of the indexer and search logic.
All other copies (scripts/, skill 22, skill 23) are 3-line wrappers that
import from here. projects/gemini-migration/ was a finished migration artifact
and has been deleted.

Key invariants enforced here (PRD 1.8 + onb-gemini GA migration):
  - GEMINI_MODEL is the single pinned constant (now: "gemini-embedding-2", GA).
    A model change here auto-triggers --rebuild (old DB rows carry a different
    model name and the indexer refuses to serve mixed-model results).
  - STALE_GEMINI_MODELS lists all retired/preview slugs. Any DB whose stored
    model is in this set is STALE: the indexer refuses to extend it (requires
    --rebuild) and the search path falls back to keyword mode with a loud
    "stale preview model detected" warning. This is the model-drift detection
    path that fires at the Wave-5 deploy when client boxes hold -preview vectors.
  - output_dimensionality=3072 is set EXPLICITLY on every Gemini embed call
    so the dimension contract is enforced at the API level (not inferred).
  - The embeddings table has provider TEXT, model TEXT, dim INTEGER columns.
    The migration path adds them if absent and backfills from vector blob length
    (1536=openai, 3072=gemini, anything else flagged for re-index).
  - At QUERY TIME: the search function reads the index provider and uses THE
    SAME provider for the query embedding. If the matching key is unavailable,
    search falls back to KEYWORD mode with a loud WARNING — it NEVER computes
    cross-model cosine similarity (cross-provider OR cross-GA/preview).

Usage:
    from embedding_engine import (
        GEMINI_MODEL, STALE_GEMINI_MODELS, OPENAI_EMBED_MODEL,
        get_embedder, get_embedding, init_db, chunk_text,
        keyword_fallback_search, search, cmd_index, cmd_status,
        get_db_index_provider,
    )
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional SDK imports — graceful fallback per N18
# ---------------------------------------------------------------------------
try:
    from google import genai
    from google.genai import types as _genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    _genai_types = None

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

try:
    import openai as openai_pkg
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai_pkg = None

# ---------------------------------------------------------------------------
# PRD 1.8 + onb-gemini: SINGLE pinned model constants.
# Changing GEMINI_MODEL here will cause cmd_index() to detect a model mismatch
# against the DB and require --rebuild.
#
# GA migration (onb-gemini): "gemini-embedding-2-preview" → "gemini-embedding-2"
#   The preview slug is retired. Vectors produced by -preview and -2 are
#   INCOMPATIBLE even at the same dimensionality — they are different models.
#   Mixing them produces garbage cosine scores. STALE_GEMINI_MODELS captures
#   all known preview/retired slugs so the drift-detection path can identify
#   stale DBs at runtime and refuse to serve them without --rebuild.
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-embedding-2"           # GA model — pinned here
GEMINI_OUTPUT_DIM = 3072                      # explicit dimensionality contract
OPENAI_EMBED_MODEL = "text-embedding-3-small"  # 1536-dim

# All retired / preview Gemini embedding slugs whose vectors are INCOMPATIBLE
# with GEMINI_MODEL. Any DB row carrying one of these model names is stale and
# must be re-embedded before it can be queried or extended.
STALE_GEMINI_MODELS = frozenset({
    "gemini-embedding-2-preview",
    "gemini-embedding-exp-03-07",   # earlier experimental slug (safety net)
})

# Expected dimensions for known models (used for backfill migration)
_DIM_BY_MODEL = {
    GEMINI_MODEL: GEMINI_OUTPUT_DIM,
    OPENAI_EMBED_MODEL: 1536,
}
# Backfill heuristic: when a pre-1.8 DB has no provider/model metadata, infer
# from vector blob length. 3072-dim blobs may be -preview OR GA; both are
# tagged with GEMINI_MODEL here and will be detected as stale when -preview
# rows surface, triggering the re-embed path via STALE_GEMINI_MODELS.
_DIM_TO_PROVIDER = {
    1536: ("openai", OPENAI_EMBED_MODEL),
    3072: ("gemini", GEMINI_MODEL),
}

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
_QUOTA_RETRIES = 2

# ---------------------------------------------------------------------------
# PRD 1.9: path resolution via the single shared authority
# ---------------------------------------------------------------------------
_SHARED_UTILS = os.path.dirname(__file__)
sys.path.insert(0, os.path.realpath(_SHARED_UTILS))
try:
    from detect_platform import get_openclaw_paths as _get_paths
    _paths = _get_paths()
    WORKSPACE_ROOT = str(_paths["workspace"])
except (Exception, SystemExit):
    # Graceful fallback — should not happen on a properly installed box.
    WORKSPACE_ROOT = os.environ.get("WORKSPACE_ROOT",
                                    os.path.expanduser("~/.openclaw/workspace"))
    if not os.path.isdir(WORKSPACE_ROOT):
        _vps_ws = "/data/.openclaw/workspace"
        if os.path.isdir(_vps_ws):
            WORKSPACE_ROOT = _vps_ws

DB_PATH = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/gemini-index.sqlite")
PERSONAS_DIR = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/personas")
if not os.path.exists(PERSONAS_DIR):
    try:
        PERSONAS_DIR = os.path.join(str(_paths["master_files"]),
                                    "coaching-personas", "personas")
    except NameError:
        PERSONAS_DIR = os.path.expanduser(
            "~/.openclaw/workspace/data/coaching-personas/personas")


# ---------------------------------------------------------------------------
# Secret resolution
# ---------------------------------------------------------------------------

def _read_secret(name: str) -> str:
    """Read API key from secrets/.env, env var, then openclaw.json env block.

    a71f6bbd fix: probe ALL canonical secret stores, not just
    WORKSPACE_ROOT/secrets/.env. On a Mac install the real key lives at
    ~/.openclaw/secrets/.env while WORKSPACE_ROOT is ~/.openclaw/workspace
    (so WORKSPACE_ROOT/secrets/.env is absent) — the auto-embed Phase-5
    subprocess would otherwise never find the Gemini key.
    """
    _env_candidates = [
        os.path.join(WORKSPACE_ROOT, "secrets/.env"),
        os.path.expanduser("~/.openclaw/secrets/.env"),
        "/data/.openclaw/secrets/.env",
    ]
    _seen = set()
    for env_path in _env_candidates:
        rp = os.path.realpath(env_path)
        if rp in _seen:
            continue
        _seen.add(rp)
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("export "):
                        s = s[len("export "):]
                    if s.startswith(f"{name}="):
                        return s.split("=", 1)[1].strip().strip('"\'')
    v = os.environ.get(name)
    if v:
        return v
    for ocj in (os.path.expanduser("~/.openclaw/openclaw.json"),
                "/data/.openclaw/openclaw.json"):
        if os.path.exists(ocj):
            try:
                with open(ocj) as f:
                    env = json.load(f).get("env", {})
                if env.get(name):
                    return env[name]
            except Exception:
                pass
    return ""


# ---------------------------------------------------------------------------
# Embedder resolution
# ---------------------------------------------------------------------------

def get_embedder(provider_hint: str = None):
    """
    Resolve the embedder. Returns (provider, client, model_id) or raises
    SystemExit(1) if neither provider is available.

    provider_hint: if set to "gemini" or "openai", only try that provider.
    This is used by the search path to enforce same-provider queries.

    Resolution order (when no hint):
      1. Gemini (preferred per N18) — needs GOOGLE_API_KEY + google-genai pkg.
      2. OpenAI (fallback per N18)  — needs OPENAI_API_KEY + openai pkg.
      3. SystemExit(1) with clear error.
    """
    if provider_hint not in (None, "gemini", "openai"):
        raise ValueError(f"provider_hint must be 'gemini', 'openai', or None, got: {provider_hint!r}")

    want_gemini = provider_hint in (None, "gemini")
    want_openai = provider_hint in (None, "openai")

    if want_gemini:
        google_key = _read_secret("GOOGLE_API_KEY") or _read_secret("GEMINI_API_KEY")
        if google_key and GENAI_AVAILABLE:
            _http_opts = _genai_types.HttpOptions(timeout=30000)
            return ("gemini",
                    genai.Client(api_key=google_key, http_options=_http_opts),
                    GEMINI_MODEL)

    if want_openai:
        openai_key = _read_secret("OPENAI_API_KEY")
        if openai_key and OPENAI_AVAILABLE:
            client = openai_pkg.OpenAI(api_key=openai_key)
            if provider_hint is None:
                print(
                    f"[embedding-engine] WARN: GOOGLE_API_KEY absent — falling back to "
                    f"OpenAI {OPENAI_EMBED_MODEL}. Per N18 this is the documented "
                    "fallback when Gemini is unavailable.",
                    file=sys.stderr,
                )
            return ("openai", client, OPENAI_EMBED_MODEL)

    # Failure modes — loud, explicit
    if provider_hint is not None:
        print(
            f"WARNING [embedding-engine]: Index was built with provider={provider_hint!r} "
            f"but the matching API key / SDK is unavailable.\n"
            f"  Falling back to KEYWORD search — no cosine similarity will be computed.\n"
            f"  To restore semantic search: set the {provider_hint.upper()}_API_KEY "
            f"(for gemini: GOOGLE_API_KEY) and re-run.",
            file=sys.stderr,
        )
        return None  # Caller must fall back to keyword mode

    # No hint and no provider available — fatal for the indexer
    print("ERROR [embedding-engine]: No embedding provider available.", file=sys.stderr)
    if not GENAI_AVAILABLE:
        print("  google-genai not installed. "
              "Run: pip3 install google-genai --break-system-packages", file=sys.stderr)
    else:
        print("  GOOGLE_API_KEY / GEMINI_API_KEY not set in secrets/.env", file=sys.stderr)
    if not OPENAI_AVAILABLE:
        print("  openai not installed. "
              "Run: pip3 install openai --break-system-packages", file=sys.stderr)
    else:
        print("  OPENAI_API_KEY not set in secrets/.env", file=sys.stderr)
    sys.exit(1)


# Legacy alias — old callers still call get_client()
def get_client():
    provider, client, _ = get_embedder()
    return client


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _is_quota_or_timeout(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("429" in msg or "quota" in msg or "rate" in msg
            or "resource_exhausted" in msg or "timed out" in msg
            or "timeout" in msg)


def get_embedding(embedder, text, retries=5):
    """
    Embed text using the provided (provider, client, model_id) tuple.

    On 429 / RESOURCE_EXHAUSTED / timeout: retries up to _QUOTA_RETRIES times
    with exponential backoff, then exits non-zero so the caller falls back to
    keyword mode. The indexer can never hang indefinitely.
    """
    if isinstance(embedder, tuple):
        provider, client, model_id = embedder
    else:
        # Legacy: bare client object (Gemini)
        provider, client, model_id = "gemini", embedder, GEMINI_MODEL

    if not NUMPY_AVAILABLE:
        raise RuntimeError("numpy not installed — cannot compute embedding vectors. "
                           "Run: pip3 install numpy --break-system-packages")

    delay = 2
    quota_attempts = 0
    for attempt in range(retries):
        try:
            if provider == "gemini":
                response = client.models.embed_content(
                    model=model_id,
                    contents=text,
                    config=_genai_types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=GEMINI_OUTPUT_DIM),
                )
                return np.array(response.embeddings[0].values, dtype=np.float32)
            elif provider == "openai":
                response = client.embeddings.create(model=model_id, input=text)
                return np.array(response.data[0].embedding, dtype=np.float32)
            else:
                raise ValueError(f"unknown provider: {provider!r}")
        except Exception as e:
            if _is_quota_or_timeout(e):
                quota_attempts += 1
                if quota_attempts > _QUOTA_RETRIES:
                    print(
                        "ERROR [embedding-engine]: embedding quota exhausted / "
                        "request timed out — semantic index not built, "
                        "keyword fallback in effect",
                        file=sys.stderr,
                    )
                    sys.exit(2)
                print(
                    f"[embedding-engine] WARN: quota/timeout "
                    f"(attempt {quota_attempts}/{_QUOTA_RETRIES}), "
                    f"retrying in {delay}s ...",
                    file=sys.stderr,
                )
                time.sleep(delay)
                delay *= 2
            else:
                if attempt == retries - 1:
                    raise
                time.sleep(delay)
    return None


def embed_query(embedder, query):
    """
    Embed a query string using RETRIEVAL_QUERY task type (Gemini) or default (OpenAI).
    Returns np.ndarray or raises RuntimeError.
    """
    if not NUMPY_AVAILABLE:
        raise RuntimeError("numpy not installed — cannot compute embedding vectors")
    provider, client, model_id = embedder
    for attempt in range(3):
        try:
            if provider == "gemini":
                response = client.models.embed_content(
                    model=model_id,
                    contents=query,
                    config=_genai_types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY",
                        output_dimensionality=GEMINI_OUTPUT_DIM),
                )
                return np.array(response.embeddings[0].values, dtype=np.float32)
            elif provider == "openai":
                response = client.embeddings.create(model=model_id, input=query)
                return np.array(response.data[0].embedding, dtype=np.float32)
            else:
                raise ValueError(f"unknown provider: {provider!r}")
        except Exception as e:
            if _is_quota_or_timeout(e):
                time.sleep(2)
            else:
                raise
    raise RuntimeError("Query embedding failed after retries.")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path: str = None) -> sqlite3.Connection:
    """
    Open (or create) the embeddings SQLite DB.

    PRD 1.8 + onb-gemini: ensures provider TEXT, model TEXT, dim INTEGER columns
    exist. If the DB was created before this migration, adds the columns and
    backfills them from vector blob length:
        1536 * 4 = 6144 bytes  -> openai / text-embedding-3-small / 1536
        3072 * 4 = 12288 bytes -> gemini / gemini-embedding-2 / 3072
                                  (note: -preview blobs are the same size;
                                   they will be detected as stale via
                                   STALE_GEMINI_MODELS at search/index time)
        anything else -> flagged with provider='unknown', model='unknown'
    """
    if db_path is None:
        db_path = DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()

    # Create with all columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id           TEXT PRIMARY KEY,
            file_path    TEXT,
            chunk_index  INTEGER,
            content      TEXT,
            vector       BLOB,
            last_updated REAL,
            provider     TEXT,
            model        TEXT,
            dim          INTEGER
        )
    """)
    conn.commit()

    # Migration: add columns to existing tables that pre-date PRD 1.8
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(embeddings)")}
    migrated = False
    for col, coltype in [("provider", "TEXT"), ("model", "TEXT"), ("dim", "INTEGER")]:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE embeddings ADD COLUMN {col} {coltype}")
            migrated = True
    if migrated:
        conn.commit()
        print(
            "[embedding-engine] INFO: Added provider/model/dim columns to embeddings table "
            "(PRD 1.8 migration). Running backfill from vector blob length...",
            file=sys.stderr,
        )
        _backfill_provider_columns(conn)

    return conn


def _backfill_provider_columns(conn: sqlite3.Connection):
    """
    Backfill provider/model/dim for rows that pre-date the PRD 1.8 migration.
    Resolution:
        blob length == 1536*4 (6144)  -> openai / text-embedding-3-small / 1536
        blob length == 3072*4 (12288) -> gemini / gemini-embedding-2 / 3072
                                         (GA model name; stale -preview rows
                                          carry the same blob size and will be
                                          upgraded during the Wave-5 --rebuild)
        other -> unknown / unknown / 0 (flagged for re-index)
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, vector FROM embeddings WHERE provider IS NULL OR provider = ''"
    )
    rows = cursor.fetchall()
    updated = 0
    flagged = 0
    for row_id, vector_bytes in rows:
        if vector_bytes is None:
            continue
        byte_len = len(vector_bytes)
        dim = byte_len // 4  # float32 = 4 bytes
        if dim in _DIM_TO_PROVIDER:
            prov, mdl = _DIM_TO_PROVIDER[dim]
        else:
            prov, mdl, dim = "unknown", "unknown", 0
            flagged += 1
        cursor.execute(
            "UPDATE embeddings SET provider=?, model=?, dim=? WHERE id=?",
            (prov, mdl, dim, row_id),
        )
        updated += 1
    conn.commit()
    if flagged:
        print(
            f"WARNING [embedding-engine]: {flagged} row(s) could not be classified "
            f"by blob length and were marked provider='unknown'. "
            f"Run with --rebuild to re-index them.",
            file=sys.stderr,
        )
    print(
        f"[embedding-engine] INFO: Backfilled {updated} rows with provider/model/dim.",
        file=sys.stderr,
    )


def get_db_index_provider(db_path: str = None) -> tuple:
    """
    Read the distinct (provider, model) from the embeddings table.

    Returns:
        (provider, model) string tuple if all rows agree on one provider/model.
        None if the DB is empty, does not have the columns yet, or has mixed providers.

    PRD 1.8 contract: a model change (GEMINI_MODEL constant updated) will cause
    this to return a different model than the current constant, which the indexer
    uses to detect that --rebuild is needed.
    """
    if db_path is None:
        db_path = DB_PATH
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        cur = conn.cursor()
        # Check if provider column exists
        cols = {row[1] for row in cur.execute("PRAGMA table_info(embeddings)")}
        if "provider" not in cols:
            conn.close()
            return None
        cur.execute(
            "SELECT DISTINCT provider, model FROM embeddings "
            "WHERE provider IS NOT NULL AND provider != '' AND provider != 'unknown'"
        )
        rows = cur.fetchall()
        conn.close()
        if len(rows) == 1:
            return rows[0]  # (provider, model)
        return None  # empty, mixed, or unknown
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str) -> list:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            newline_pos = text.rfind("\n\n", start, end)
            if newline_pos > start + (CHUNK_SIZE // 2):
                end = newline_pos
            else:
                period_pos = text.rfind(". ", start, end)
                if period_pos > start + (CHUNK_SIZE // 2):
                    end = period_pos + 1
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def cosine_similarity(v1, v2) -> float:
    dot = np.dot(v1, v2)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(dot / (n1 * n2))


# ---------------------------------------------------------------------------
# Keyword fallback search
# ---------------------------------------------------------------------------

def get_persona_name(file_path: str) -> str:
    """Extract parent folder name from a file path (e.g. 'cialdini-influence')."""
    return os.path.basename(os.path.dirname(file_path))


# ---------------------------------------------------------------------------
# Mode-aware retrieval (coaching vs. leadership / Task-Mode).
#
# A persona blueprint is dual-purpose: the COACHING half (conversation) and the
# LEADERSHIP / Task-Mode half (Section 4 "Agent Governance Framework" — Execution
# Standard, Definition of Done, Failure Patterns). The section-level indexer
# (gemini-section-indexer.py) tags each row with `mode` ('coaching'|'leadership'|
# 'both') and `section_number`. A leadership query must be able to surface the
# GOVERNANCE chunk distinctly rather than coaching chunks. These helpers add an
# OPTIONAL mode filter that is applied ONLY when the index actually carries those
# columns — so the chunk-only index (no mode/section_number) is unaffected and the
# call stays fully backward-compatible.
# ---------------------------------------------------------------------------

# Section 4 is the Agent Governance Framework (the leadership / Task-Mode half).
LEADERSHIP_SECTION_NUMBER = 4


def _table_columns(cur, table: str = "embeddings") -> set:
    try:
        cur.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cur.fetchall()}
    except Exception:
        return set()


def _mode_filter_sql(cur, mode):
    """Return (sql_fragment, params) restricting rows to the requested mode.

    ``mode`` is 'leadership' | 'coaching' | None. Returns ('', []) when no mode
    is requested OR when the index lacks the mode/section_number columns (so a
    legacy chunk-only index is never broken by this filter).
    """
    if not mode:
        return "", []
    cols = _table_columns(cur)
    if "mode" not in cols and "section_number" not in cols:
        return "", []  # legacy index: no leadership/coaching distinction to filter on
    mode = mode.lower()
    clauses, params = [], []
    if "mode" in cols:
        clauses.append("LOWER(mode) = ?")
        params.append(mode)
        clauses.append("LOWER(mode) = 'both'")  # 'both' sections serve either mode
    if mode == "leadership" and "section_number" in cols:
        clauses.append("section_number = ?")
        params.append(LEADERSHIP_SECTION_NUMBER)
    if not clauses:
        return "", []
    return " AND (" + " OR ".join(clauses) + ") ", params


def keyword_fallback_search(query: str, limit: int, db_path: str = None,
                            mode: str = None) -> int:
    """
    SQLite LIKE keyword-search fallback.

    Called when no embedding provider is available OR when the index was built
    with a different provider than what is currently available (PRD 1.8:
    never cross-provider cosine).

    ``mode`` ('leadership'|'coaching'|None) optionally restricts results to the
    Task-Mode (Section 4) / coaching half when the index carries section metadata.

    Returns 0 on success, 1 on error.
    """
    if db_path is None:
        db_path = DB_PATH
    if not os.path.exists(db_path):
        print(f"ERROR [embedding-engine]: DB not found at {db_path}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db_path, timeout=30.0)
    cur = conn.cursor()
    mode_sql, mode_params = _mode_filter_sql(cur, mode)
    words = [w.strip() for w in query.lower().split() if len(w.strip()) >= 3]
    if not words:
        words = [query.lower()]
    placeholders = " OR ".join("LOWER(content) LIKE ?" for _ in words)
    params = [f"%{w}%" for w in words] + mode_params
    cur.execute(
        f"SELECT file_path, content FROM embeddings "
        f"WHERE file_path LIKE '%coaching-personas/personas/%' "
        f"AND ({placeholders}) {mode_sql}",
        params,
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No keyword matches found in the index.")
        return 0

    def score_row(content: str) -> int:
        return sum(1 for w in words if w in content.lower())

    scored = [(score_row(c), p, c) for p, c in rows]
    scored.sort(key=lambda x: -x[0])
    seen: set = set()
    out = []
    for s, path, content in scored:
        persona = get_persona_name(path)
        if persona in seen:
            continue
        seen.add(persona)
        out.append((s, persona, content))
        if len(out) >= limit:
            break

    print(
        "[embedding-engine] WARNING: keyword-fallback mode active — "
        "install google-genai or openai (or make the matching key available) "
        "for semantic search. No cosine similarity was computed.",
        file=sys.stderr,
    )
    for i, (s, persona, content) in enumerate(out, 1):
        print(f"[{i}] KEYWORD-HITS: {s} | PERSONA: {persona}")
        print("-" * 60)
        print(f"{content.strip()[:800]}...\n")
    return 0


# ---------------------------------------------------------------------------
# search() — the main query-time function
# PRD 1.8 contract: reads index provider, enforces same-provider query embedding.
# ---------------------------------------------------------------------------

def search(query: str, limit: int = 3, db_path: str = None, mode: str = None) -> int:
    """
    Semantic search over the coaching-personas embedding index.

    PRD 1.8 contract:
      1. Read the index provider from the DB (get_db_index_provider).
      2. Attempt to load THE SAME provider for the query embedding.
      3. If the matching key is unavailable: fall back to KEYWORD mode with a
         loud WARNING — NEVER compute cross-provider cosine similarity.
      4. If the DB has no provider metadata (old index): fall back to keyword
         mode and warn the user to run --rebuild.

    Returns 0 on success.
    """
    if db_path is None:
        db_path = DB_PATH

    if not os.path.exists(db_path):
        print(f"ERROR [embedding-engine]: DB not found at {db_path}", file=sys.stderr)
        return 1

    if not query or not query.strip():
        print("ERROR [embedding-engine]: query string is empty", file=sys.stderr)
        return 1

    # Step 1: determine what provider the index was built with
    index_info = get_db_index_provider(db_path)
    if index_info is None:
        print(
            "WARNING [embedding-engine]: Cannot determine index provider "
            "(DB empty, columns missing, or mixed providers). "
            "Falling back to KEYWORD search. Run `gemini-indexer --rebuild` "
            "to re-index with a single provider.",
            file=sys.stderr,
        )
        return keyword_fallback_search(query, limit, db_path, mode)

    index_provider, index_model = index_info

    # Step 2: check if index model is stale (retired preview slug) or differs
    # from the current GEMINI_MODEL constant (any model drift).
    # STALE_GEMINI_MODELS is the authoritative list of incompatible old slugs.
    # Cross-model cosine is NEVER computed — keyword fallback instead.
    if index_provider == "gemini" and (
            index_model in STALE_GEMINI_MODELS or index_model != GEMINI_MODEL):
        if index_model in STALE_GEMINI_MODELS:
            stale_reason = (
                f"STALE PREVIEW MODEL DETECTED — Index was built with "
                f"model={index_model!r} which is a retired/preview slug. "
                f"Vectors from {index_model!r} are INCOMPATIBLE with the current "
                f"GA model {GEMINI_MODEL!r} even at the same dimensionality. "
                f"Run `gemini-indexer --rebuild` to re-embed with {GEMINI_MODEL!r}. "
                f"Falling back to KEYWORD search until re-embed completes."
            )
        else:
            stale_reason = (
                f"Index was built with model={index_model!r} "
                f"but GEMINI_MODEL constant is now {GEMINI_MODEL!r}. "
                f"Run `gemini-indexer --rebuild` to re-index with the current model. "
                f"Falling back to KEYWORD search."
            )
        print(
            f"WARNING [embedding-engine]: {stale_reason}",
            file=sys.stderr,
        )
        return keyword_fallback_search(query, limit, db_path, mode)

    # Step 3: load THE SAME provider for query embedding
    embedder = get_embedder(provider_hint=index_provider)
    if embedder is None:
        # get_embedder already printed the loud WARNING about missing key
        return keyword_fallback_search(query, limit, db_path, mode)

    if not NUMPY_AVAILABLE:
        print(
            "WARNING [embedding-engine]: numpy not installed — falling back to "
            "KEYWORD search.",
            file=sys.stderr,
        )
        return keyword_fallback_search(query, limit, db_path, mode)

    print(
        f"[embedding-engine] using embedder: {embedder[0]} ({embedder[2]}) "
        f"(matches index provider={index_provider!r}, model={index_model!r})",
        file=sys.stderr,
    )

    try:
        query_vector = embed_query(embedder, query)
    except Exception as e:
        if ("api key" in str(e).lower() or "permission" in str(e).lower()
                or "401" in str(e) or "403" in str(e)):
            print(
                f"WARNING [embedding-engine]: embedder rejected credentials ({e}). "
                f"Falling back to KEYWORD search.",
                file=sys.stderr,
            )
            return keyword_fallback_search(query, limit, db_path, mode)
        raise

    # Step 4: cosine similarity — only against rows with matching provider
    conn = sqlite3.connect(db_path, timeout=30.0)
    cursor = conn.cursor()
    # Optional leadership/coaching mode filter (applied only when the index
    # carries section metadata — see _mode_filter_sql).
    mode_sql, mode_params = _mode_filter_sql(cursor, mode)
    # Filter to matching provider rows to be safe (extra guard against mixed index)
    cursor.execute(
        "SELECT id, file_path, content, vector FROM embeddings "
        "WHERE file_path LIKE '%coaching-personas/personas/%' "
        "AND (provider = ? OR provider IS NULL OR provider = '') " + mode_sql,
        (index_provider, *mode_params),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No documents found in the index.")
        return 0

    results = []
    for chunk_id, file_path, content, vector_bytes in rows:
        stored_vector = np.frombuffer(vector_bytes, dtype=np.float32)
        # Dimension guard: skip if dimensions mismatch (should not happen after migration)
        if stored_vector.shape[0] != query_vector.shape[0]:
            print(
                f"WARNING [embedding-engine]: dim mismatch for {file_path} "
                f"(stored={stored_vector.shape[0]}, query={query_vector.shape[0]}). "
                f"Skipping — run --rebuild to fix.",
                file=sys.stderr,
            )
            continue
        sim = cosine_similarity(query_vector, stored_vector)
        results.append((sim, file_path, content))

    results.sort(key=lambda x: x[0], reverse=True)

    seen_folders: set = set()
    top_results = []
    for sim, path, content in results:
        persona_name = get_persona_name(path)
        if persona_name not in seen_folders:
            seen_folders.add(persona_name)
            top_results.append((sim, persona_name, content))
        if len(top_results) >= limit:
            break

    for i, (sim, persona, content) in enumerate(top_results, 1):
        print(f"[{i}] SCORE: {sim:.4f} | PERSONA: {persona}")
        print("-" * 60)
        print(f"{content.strip()[:800]}...\n")
    return 0


# ---------------------------------------------------------------------------
# cmd_status — report without indexing
# ---------------------------------------------------------------------------

def cmd_status(db_path: str = None) -> int:
    if db_path is None:
        db_path = DB_PATH
    print(f"Workspace root: {WORKSPACE_ROOT}")
    print(f"Personas dir:   {PERSONAS_DIR}")
    print(f"DB path:        {db_path}")
    if not os.path.exists(db_path):
        print("INFO: DB not initialized yet — run without --status to build it.")
    else:
        conn = sqlite3.connect(db_path, timeout=30.0)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM embeddings")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT file_path) FROM embeddings")
        files_indexed = cur.fetchone()[0]
        cur.execute("SELECT MAX(last_updated) FROM embeddings")
        last_ts = cur.fetchone()[0]
        # PRD 1.8: report provider/model in status
        index_info = get_db_index_provider(db_path)
        conn.close()
        print(f"Chunks indexed:  {total}")
        print(f"Files indexed:   {files_indexed}")
        if last_ts:
            print(f"Last updated:    "
                  f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_ts))}")
        if index_info:
            iprov, imodel = index_info
            print(f"Index provider:  {iprov}")
            print(f"Index model:     {imodel}")
            if iprov == "gemini" and imodel != GEMINI_MODEL:
                if imodel in STALE_GEMINI_MODELS:
                    print(
                        f"WARNING: STALE PREVIEW MODEL — Index model {imodel!r} is "
                        f"a retired/preview slug; vectors are INCOMPATIBLE with current "
                        f"GA model {GEMINI_MODEL!r}. Run --rebuild to re-embed.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"WARNING: Index model {imodel!r} != current constant "
                        f"{GEMINI_MODEL!r}. Run --rebuild.",
                        file=sys.stderr,
                    )
        else:
            print("Index provider:  (unknown — run --rebuild to set)")
    if not os.path.exists(PERSONAS_DIR):
        print(f"WARNING: Personas dir missing: {PERSONAS_DIR}")
    else:
        files_on_disk = list(Path(PERSONAS_DIR).rglob("*.md"))
        print(f".md files on disk: {len(files_on_disk)}")
    # Embedder availability check
    google_key = _read_secret("GOOGLE_API_KEY") or _read_secret("GEMINI_API_KEY")
    openai_key = _read_secret("OPENAI_API_KEY")
    if google_key and GENAI_AVAILABLE:
        print(f"Embedder ready:  gemini ({GEMINI_MODEL})")
    elif openai_key and OPENAI_AVAILABLE:
        print(f"Embedder ready:  openai ({OPENAI_EMBED_MODEL}) [N18 fallback]")
    else:
        print("WARNING: Embedder NOT ready — missing API key or python pkg.")
    return 0


# ---------------------------------------------------------------------------
# cmd_index — the main indexer
# ---------------------------------------------------------------------------

def cmd_index(rebuild: bool = False, db_path: str = None,
              personas_dir: str = None) -> int:
    """
    Build or update the coaching-personas embedding index.

    PRD 1.8: writes provider/model/dim to every new row. Detects model drift
    (GEMINI_MODEL constant changed) and requires --rebuild in that case.
    """
    if db_path is None:
        db_path = DB_PATH
    if personas_dir is None:
        personas_dir = PERSONAS_DIR

    print(f"[embedding-engine] Starting indexer{' (REBUILD)' if rebuild else ''}")
    print(f"[embedding-engine] Scanning: {personas_dir}")
    if not os.path.exists(personas_dir):
        print(f"ERROR [embedding-engine]: Directory not found -> {personas_dir}",
              file=sys.stderr)
        return 1

    # Check for model drift before doing any work.
    # Stale preview models (STALE_GEMINI_MODELS) get a specific "stale" message;
    # any other Gemini mismatch gets the generic drift message. Both block the
    # incremental indexer and require --rebuild to protect vector integrity.
    index_info = get_db_index_provider(db_path)
    if index_info is not None and not rebuild:
        existing_provider, existing_model = index_info
        if existing_provider == "gemini" and existing_model != GEMINI_MODEL:
            if existing_model in STALE_GEMINI_MODELS:
                print(
                    f"ERROR [embedding-engine]: STALE PREVIEW MODEL — Index contains "
                    f"vectors from retired/preview model {existing_model!r}. "
                    f"These vectors are INCOMPATIBLE with the current GA model "
                    f"{GEMINI_MODEL!r}. Run with --rebuild to re-embed all documents "
                    f"with {GEMINI_MODEL!r}. (Wave-5 per-box re-embed will do this.)",
                    file=sys.stderr,
                )
            else:
                print(
                    f"ERROR [embedding-engine]: GEMINI_MODEL constant is now "
                    f"{GEMINI_MODEL!r} but the index was built with {existing_model!r}. "
                    f"Run with --rebuild to re-index with the current model.",
                    file=sys.stderr,
                )
            return 1

    embedder = get_embedder()
    prov, _, mdl = embedder
    dim = _DIM_BY_MODEL.get(mdl, 0)
    print(f"[embedding-engine] Using embedder: {prov} ({mdl}, dim={dim})",
          file=sys.stderr)

    conn = init_db(db_path)
    cursor = conn.cursor()

    if rebuild:
        print("[embedding-engine] --rebuild: dropping all existing embeddings")
        cursor.execute("DELETE FROM embeddings")
        conn.commit()

    files = list(Path(personas_dir).rglob("*.md"))
    print(f"[embedding-engine] Found {len(files)} markdown files.")

    total_chunks = 0
    skipped = 0
    errors = 0
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            chunks = chunk_text(content)
            file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
            cursor.execute(
                "SELECT id FROM embeddings WHERE id LIKE ? LIMIT 1",
                (f"{file_hash}_%",),
            )
            if cursor.fetchone() and not rebuild:
                skipped += 1
                continue
            print(f"  Indexing: {file_path.name} ({len(chunks)} chunks)")
            cursor.execute(
                "DELETE FROM embeddings WHERE file_path = ?", (str(file_path),))
            for i, chunk in enumerate(chunks):
                vector = get_embedding(embedder, chunk)
                if vector is not None:
                    chunk_id = f"{file_hash}_{i}"
                    vector_bytes = vector.tobytes()
                    cursor.execute(
                        "INSERT INTO embeddings "
                        "(id, file_path, chunk_index, content, vector, "
                        " last_updated, provider, model, dim) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (chunk_id, str(file_path), i, chunk,
                         vector_bytes, time.time(), prov, mdl, dim),
                    )
                    total_chunks += 1
                    time.sleep(0.5)
            conn.commit()
        except Exception as e:
            errors += 1
            print(f"  ERROR processing {file_path.name}: {e}", file=sys.stderr)
    conn.close()
    print(
        f"[embedding-engine] Indexing complete. "
        f"Added {total_chunks} new chunks across "
        f"{len(files) - skipped - errors} files "
        f"(skipped {skipped} unchanged, {errors} errors)."
    )
    return 0 if errors == 0 else 2


# ---------------------------------------------------------------------------
# CLI entrypoints (for direct invocation of the module)
# ---------------------------------------------------------------------------

def _indexer_main():
    parser = argparse.ArgumentParser(
        prog="embedding-engine (indexer)",
        description="OpenClaw embedding engine indexer (PRD 1.8 canonical).",
    )
    parser.add_argument("--status", action="store_true",
                        help="Report DB stats and embedder readiness.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop all embeddings and re-index from scratch.")
    args = parser.parse_args()
    if args.status:
        sys.exit(cmd_status())
    sys.exit(cmd_index(rebuild=args.rebuild))


def _search_main():
    parser = argparse.ArgumentParser(
        prog="embedding-engine (search)",
        description="OpenClaw semantic search (PRD 1.8 canonical).",
    )
    parser.add_argument("query", type=str, help="Search query text")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--mode", choices=["leadership", "coaching"], default=None,
        help="Restrict results to the persona's Task-Mode/leadership half "
             "(Section 4 Agent Governance Framework) or the coaching half. "
             "Applied only when the index carries section metadata; a legacy "
             "chunk-only index ignores it and searches everything.")
    args = parser.parse_args()
    sys.exit(search(args.query, limit=args.limit, mode=args.mode))


if __name__ == "__main__":
    # When invoked directly, default to search mode if a positional arg is given.
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        _search_main()
    else:
        _indexer_main()
