#!/usr/bin/env python3
import sys
import os
import sqlite3
import argparse
import time

try:
    from google import genai
    from google.genai import types
    import numpy as np
except ImportError:
    print("CRITICAL ERROR: Missing dependencies.")
    sys.exit(1)

DB_PATH = os.path.expanduser("~/clawd/data/coaching-personas/gemini-index.sqlite")
GEMINI_MODEL = "gemini-embedding-2-preview"
TOP_K = 3

def get_client():
    env_path = os.path.expanduser("~/clawd/secrets/.env")
    api_key = None
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.strip().split("=", 1)[1].strip('"\'')
                    break
    if not api_key: api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("WARNING: GOOGLE_API_KEY not set. Using keyword fallback.")
        sys.exit(2)
    return genai.Client(api_key=api_key)

def embed_query(client, query):
    for attempt in range(3):
        try:
            response = client.models.embed_content(
                model=GEMINI_MODEL,
                contents=query,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
            )
            return np.array(response.embeddings[0].values, dtype=np.float32)
        except Exception as e:
            if "429" in str(e).lower() or "quota" in str(e).lower():
                time.sleep(2)
            else: raise e
    raise RuntimeError("Query embedding failed.")

def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0: return 0.0
    return dot_product / (norm_v1 * norm_v2)

def get_persona_name(file_path):
    """Extract the parent folder name from a file path (e.g., 'cialdini-influence')."""
    return os.path.basename(os.path.dirname(file_path))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Search keyword")
    parser.add_argument("--limit", type=int, default=TOP_K)
    args = parser.parse_args()

    # BUG 3 FIX: validate empty input
    if not args.query or not args.query.strip():
        print("ERROR: task description required")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    client = get_client()
    try:
        query_vector = embed_query(client, args.query)
    except Exception as e:
        if "api key" in str(e).lower() or "permission" in str(e).lower() or "401" in str(e) or "403" in str(e):
            print("WARNING: GOOGLE_API_KEY not set. Using keyword fallback.")
            sys.exit(2)
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

    # BUG 1 + 2 FIX: deduplicate by parent folder, return top 3 distinct personas
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
