#!/usr/bin/env python3
import sys
import os
import sqlite3
import argparse
import time

# v10.12.0 P10.2: graceful google-genai import (matches indexer pattern). When
# the package is absent we fall through to OpenAI rather than crashing.
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
except ImportError:
    print("CRITICAL ERROR: numpy missing. Run: pip3 install numpy --break-system-packages", file=sys.stderr)
    sys.exit(1)

# Workspace Root Configuration (Mac → VPS fallback). Legacy ~/clawd removed in v10.12.0.
WORKSPACE_ROOT = os.environ.get("WORKSPACE_ROOT", os.path.expanduser("~/.openclaw/workspace"))
if not os.path.isdir(WORKSPACE_ROOT):
    VPS_WORKSPACE = "/data/.openclaw/workspace"
    if os.path.isdir(VPS_WORKSPACE):
        WORKSPACE_ROOT = VPS_WORKSPACE

DB_PATH = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/gemini-index.sqlite")
GEMINI_MODEL = "gemini-embedding-2-preview"
TOP_K = 3

OPENAI_EMBED_MODEL = "text-embedding-3-small"

try:
    import openai as openai_pkg
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai_pkg = None


def _read_secret(name):
    """Read API key from secrets/.env, env, or openclaw.json env block."""
    env_path = os.path.join(WORKSPACE_ROOT, "secrets/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.strip().split("=", 1)[1].strip('"\'')
    v = os.environ.get(name)
    if v:
        return v
    import json
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


def get_embedder():
    """
    Returns (provider, client, model_id). v10.10.0 P0-003 + v10.12.0 P10.2.
    Order: Gemini (preferred per N18) → OpenAI (fallback) → error.
    Both arms now check both the API key AND the package being importable.
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
    print("ERROR: No embedding provider available.", file=sys.stderr)
    print(f"  Set GOOGLE_API_KEY (preferred) or OPENAI_API_KEY in {WORKSPACE_ROOT}/secrets/.env",
          file=sys.stderr)
    if not GENAI_AVAILABLE:
        print("  Note: google-genai not installed. Run: pip3 install google-genai --break-system-packages",
              file=sys.stderr)
    if not OPENAI_AVAILABLE:
        print("  Note: openai not installed. Run: pip3 install openai --break-system-packages",
              file=sys.stderr)
    sys.exit(1)


# Legacy alias
def get_client():
    return get_embedder()[1]


def embed_query(client_or_pair, query):
    """Embed query with Gemini OR OpenAI depending on provider."""
    if isinstance(client_or_pair, tuple):
        provider, client, model_id = client_or_pair
    else:
        provider, client, model_id = "gemini", client_or_pair, GEMINI_MODEL

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
                raise e
    raise RuntimeError("Query embedding failed.")

def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0: return 0.0
    return dot_product / (norm_v1 * norm_v2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Search keyword")
    parser.add_argument("--limit", type=int, default=TOP_K)
    args = parser.parse_args()
    
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
        
    # v10.10.0 P0-003: get_embedder() returns (provider, client, model_id)
    embedder = get_embedder()
    print(f"[gemini-search] using embedder: {embedder[0]} ({embedder[2]})", file=sys.stderr)
    query_vector = embed_query(embedder, args.query)
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_path, content, vector FROM embeddings")
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
    top_results = results[:args.limit]
    
    for i, (sim, path, content) in enumerate(top_results, 1):
        print(f"[{i}] SCORE: {sim:.4f} | FILE: {os.path.basename(path)}")
        print("-" * 60)
        print(f"{content.strip()[:800]}...\\n")

if __name__ == "__main__":
    main()
