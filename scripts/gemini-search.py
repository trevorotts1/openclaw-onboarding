#!/usr/bin/env python3
"""
Skill 22 / Book-to-Persona — semantic search against the coaching-personas
SQLite embedding index.

v10.13.0 changes:
  - Graceful google-genai + openai imports (no hard ImportError exit).
  - OpenAI text-embedding-3-small runtime fallback per N18.
  - Keyword-search fallback when BOTH providers unavailable (SQLite LIKE on
    `content` column) so the pipeline stays operational with zero embedding
    SDKs installed.
  - Removed ~/clawd legacy fallback (replaced with VPS workspace path).
"""
import sys
import os
import sqlite3
import argparse
import time

# Graceful google-genai import (P0-003 / P10.2 / P10.3 — v10.13.0)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None
    types = None

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

# PRD 1.9: resolve paths via the single shared authority.
_SHARED_UTILS = os.path.join(os.path.dirname(__file__), "..", "shared-utils")
sys.path.insert(0, os.path.realpath(_SHARED_UTILS))
try:
    from detect_platform import get_openclaw_paths as _get_paths
    _paths = _get_paths()
    WORKSPACE_ROOT = str(_paths["workspace"])
except (Exception, SystemExit):
    WORKSPACE_ROOT = os.environ.get("WORKSPACE_ROOT", os.path.expanduser("~/.openclaw/workspace"))
    if not os.path.isdir(WORKSPACE_ROOT):
        VPS_WORKSPACE = "/data/.openclaw/workspace"
        if os.path.isdir(VPS_WORKSPACE):
            WORKSPACE_ROOT = VPS_WORKSPACE

DB_PATH = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/gemini-index.sqlite")
GEMINI_MODEL = "gemini-embedding-2-preview"
OPENAI_EMBED_MODEL = "text-embedding-3-small"  # 1536-dim, cheaper than -large
TOP_K = 3


def _read_secret(name: str) -> str:
    """Read API key from secrets/.env, env var, then openclaw.json env block."""
    import json as _json
    env_path = os.path.join(WORKSPACE_ROOT, "secrets/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.strip().split("=", 1)[1].strip('"\'')
    v = os.environ.get(name)
    if v:
        return v
    for ocj in (os.path.expanduser("~/.openclaw/openclaw.json"),
                "/data/.openclaw/openclaw.json"):
        if os.path.exists(ocj):
            try:
                with open(ocj) as f:
                    env = _json.load(f).get("env", {})
                if env.get(name):
                    return env[name]
            except Exception:
                pass
    return ""


def get_embedder():
    """
    Returns (provider, client, model_id) or None if no embedder is available.

    Resolution order:
      1. Gemini (preferred per N18) — needs GOOGLE_API_KEY + google-genai pkg.
      2. OpenAI (fallback per N18)  — needs OPENAI_API_KEY + openai pkg.
      3. None — caller falls back to keyword search (SQLite LIKE).
    """
    google_key = _read_secret("GOOGLE_API_KEY") or _read_secret("GEMINI_API_KEY")
    if google_key and GENAI_AVAILABLE:
        return ("gemini", genai.Client(api_key=google_key), GEMINI_MODEL)
    openai_key = _read_secret("OPENAI_API_KEY")
    if openai_key and OPENAI_AVAILABLE:
        client = openai_pkg.OpenAI(api_key=openai_key)
        print(f"[gemini-search] WARN: GOOGLE_API_KEY absent or google-genai not "
              f"installed — falling back to OpenAI {OPENAI_EMBED_MODEL} per N18.",
              file=sys.stderr)
        return ("openai", client, OPENAI_EMBED_MODEL)
    return None


def embed_query(embedder, query):
    """Embed query via Gemini or OpenAI depending on provider tuple."""
    if not NUMPY_AVAILABLE:
        raise RuntimeError("numpy not installed — cannot compute embedding vectors")
    provider, client, model_id = embedder
    for attempt in range(3):
        try:
            if provider == "gemini":
                response = client.models.embed_content(
                    model=model_id,
                    contents=query,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
                )
                return np.array(response.embeddings[0].values, dtype=np.float32)
            elif provider == "openai":
                response = client.embeddings.create(model=model_id, input=query)
                return np.array(response.data[0].embedding, dtype=np.float32)
            else:
                raise ValueError(f"unknown provider: {provider}")
        except Exception as e:
            if "429" in str(e).lower() or "quota" in str(e).lower() or "rate" in str(e).lower():
                time.sleep(2)
            else:
                raise
    raise RuntimeError("Query embedding failed after retries.")


def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)


def get_persona_name(file_path):
    """Extract the parent folder name from a file path (e.g., 'cialdini-influence')."""
    return os.path.basename(os.path.dirname(file_path))


def keyword_fallback_search(query: str, limit: int):
    """
    SQLite LIKE keyword-search fallback when no embedding provider is available.
    Last-resort path so the persona pipeline stays operational without google-genai
    or openai installed. Per N18 + Phase 10 audit recommendation.
    """
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cur = conn.cursor()
    # Split query into significant words; OR them in LIKE clauses.
    words = [w.strip() for w in query.lower().split() if len(w.strip()) >= 3]
    if not words:
        words = [query.lower()]
    placeholders = " OR ".join("LOWER(content) LIKE ?" for _ in words)
    params = [f"%{w}%" for w in words]
    cur.execute(
        f"SELECT file_path, content FROM embeddings "
        f"WHERE file_path LIKE '%coaching-personas/personas/%' AND ({placeholders})",
        params,
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No keyword matches found in the index.")
        return 0
    # Score by number of distinct keywords hit per row.
    def score_row(content: str) -> int:
        return sum(1 for w in words if w in content.lower())
    scored = [(score_row(content), path, content) for path, content in rows]
    scored.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for s, path, content in scored:
        persona = get_persona_name(path)
        if persona in seen:
            continue
        seen.add(persona)
        out.append((s, persona, content))
        if len(out) >= limit:
            break
    print(f"[gemini-search] keyword-fallback mode (no embedder available — "
          f"install google-genai or openai for semantic search)", file=sys.stderr)
    for i, (s, persona, content) in enumerate(out, 1):
        print(f"[{i}] KEYWORD-HITS: {s} | PERSONA: {persona}")
        print("-" * 60)
        print(f"{content.strip()[:800]}...\n")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Search keyword")
    parser.add_argument("--limit", type=int, default=TOP_K)
    args = parser.parse_args()

    if not args.query or not args.query.strip():
        print("ERROR: task description required")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    embedder = get_embedder()
    if embedder is None or not NUMPY_AVAILABLE:
        # Keyword fallback — no embedder OR no numpy.
        return keyword_fallback_search(args.query, args.limit)

    print(f"[gemini-search] using embedder: {embedder[0]} ({embedder[2]})", file=sys.stderr)
    try:
        query_vector = embed_query(embedder, args.query)
    except Exception as e:
        if "api key" in str(e).lower() or "permission" in str(e).lower() or "401" in str(e) or "403" in str(e):
            print(f"WARNING: embedder rejected credentials ({e}). Trying keyword fallback...", file=sys.stderr)
            return keyword_fallback_search(args.query, args.limit)
        raise

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_path, content, vector FROM embeddings WHERE file_path LIKE '%coaching-personas/personas/%'")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No documents found in the index.")
        sys.exit(0)

    results = []
    for row in rows:
        chunk_id, file_path, content, vector_bytes = row
        stored_vector = np.frombuffer(vector_bytes, dtype=np.float32)
        sim = cosine_similarity(query_vector, stored_vector)
        results.append((sim, file_path, content))

    results.sort(key=lambda x: x[0], reverse=True)

    # Deduplicate by parent folder, return top N distinct personas
    seen_folders = set()
    top_results = []
    for sim, path, content in results:
        persona_name = get_persona_name(path)
        if persona_name not in seen_folders:
            seen_folders.add(persona_name)
            top_results.append((sim, persona_name, content))
        if len(top_results) >= args.limit:
            break

    for i, (sim, persona, content) in enumerate(top_results, 1):
        print(f"[{i}] SCORE: {sim:.4f} | PERSONA: {persona}")
        print("-" * 60)
        print(f"{content.strip()[:800]}...\n")


if __name__ == "__main__":
    main()
