#!/usr/bin/env python3
import argparse
import os, sys, time, sqlite3, hashlib
from pathlib import Path

# v10.10.0 P0-003: graceful OpenAI fallback when GOOGLE_API_KEY absent.
# Per N18, Gemini Embeddings v2 is the canonical embedder. When the client
# doesn't have a Google API key, we fall back to OpenAI text-embedding-3-small.
# When neither is present, we exit with a clear error rather than silently
# producing nonsense embeddings.
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
    print("CRITICAL ERROR: numpy missing. Run: pip3 install numpy --break-system-packages")
    sys.exit(1)

try:
    import openai as openai_pkg
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai_pkg = None

# Workspace Root Configuration (Mac default → VPS fallback). Legacy ~/clawd
# was removed in v10.12.0 per memory: "OpenClaw is the system."
WORKSPACE_ROOT = os.environ.get("WORKSPACE_ROOT", os.path.expanduser("~/.openclaw/workspace"))
if not os.path.isdir(WORKSPACE_ROOT):
    VPS_WORKSPACE = "/data/.openclaw/workspace"
    if os.path.isdir(VPS_WORKSPACE):
        WORKSPACE_ROOT = VPS_WORKSPACE

DB_PATH = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/gemini-index.sqlite")
PERSONAS_DIR = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/personas")
if not os.path.exists(PERSONAS_DIR):
    PERSONAS_DIR = os.path.expanduser("~/Downloads/openclaw-master-files/coaching-personas/personas")

GEMINI_MODEL = "gemini-embedding-2-preview"
OPENAI_EMBED_MODEL = "text-embedding-3-small"  # cheaper than -large; 1536-dim
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def _read_secret(name: str) -> str:
    """Read API key from secrets/.env, then env var, then openclaw.json env block."""
    env_path = os.path.join(WORKSPACE_ROOT, "secrets/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.strip().split("=", 1)[1].strip('"\'')
    v = os.environ.get(name)
    if v:
        return v
    # openclaw.json env block fallback (Mac + VPS)
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
    Resolve the embedder.

    Returns a tuple (provider, client_or_key, model_id).
        provider ∈ {"gemini", "openai"}

    Resolution order:
      1. Gemini (Embeddings v2) — preferred per N18. Requires GOOGLE_API_KEY +
         google-genai package.
      2. OpenAI (text-embedding-3-small) — fallback when Gemini unavailable.
         Requires OPENAI_API_KEY + openai package.
      3. Exit with clear error if neither available.
    """
    google_key = _read_secret("GOOGLE_API_KEY") or _read_secret("GEMINI_API_KEY")
    if google_key and GENAI_AVAILABLE:
        return ("gemini", genai.Client(api_key=google_key), GEMINI_MODEL)

    openai_key = _read_secret("OPENAI_API_KEY")
    if openai_key and OPENAI_AVAILABLE:
        client = openai_pkg.OpenAI(api_key=openai_key)
        print("[gemini-indexer] WARN: GOOGLE_API_KEY absent — falling back to "
              f"OpenAI {OPENAI_EMBED_MODEL}. Per N18 this is the documented "
              "fallback when Gemini is unavailable.", file=sys.stderr)
        return ("openai", client, OPENAI_EMBED_MODEL)

    print("ERROR: No embedding provider available.", file=sys.stderr)
    print("  Set GOOGLE_API_KEY (preferred) or OPENAI_API_KEY in "
          f"{WORKSPACE_ROOT}/secrets/.env", file=sys.stderr)
    if not GENAI_AVAILABLE:
        print("  Note: google-genai not installed. "
              "Run: pip3 install google-genai --break-system-packages", file=sys.stderr)
    if not OPENAI_AVAILABLE:
        print("  Note: openai not installed. "
              "Run: pip3 install openai --break-system-packages", file=sys.stderr)
    sys.exit(1)


# Legacy alias — old callers still call get_client()
def get_client():
    provider, client, _ = get_embedder()
    return client

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS embeddings (
        id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, content TEXT, vector BLOB, last_updated REAL)''')
    conn.commit()
    return conn

def chunk_text(text):
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            newline_pos = text.rfind("\n\n", start, end)
            if newline_pos > start + (CHUNK_SIZE // 2): end = newline_pos
            else:
                period_pos = text.rfind(". ", start, end)
                if period_pos > start + (CHUNK_SIZE // 2): end = period_pos + 1
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks

def get_embedding(client_or_pair, text, retries=5):
    """
    Embed `text`. Works with Gemini client (legacy) OR with the new
    (provider, client, model_id) tuple returned by get_embedder().
    """
    if isinstance(client_or_pair, tuple):
        provider, client, model_id = client_or_pair
    else:
        provider, client, model_id = "gemini", client_or_pair, GEMINI_MODEL

    delay = 2
    for attempt in range(retries):
        try:
            if provider == "gemini":
                response = client.models.embed_content(
                    model=model_id,
                    contents=text,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                )
                return np.array(response.embeddings[0].values, dtype=np.float32)
            elif provider == "openai":
                # OpenAI returns 1536-dim float vectors for text-embedding-3-small
                response = client.embeddings.create(
                    model=model_id,
                    input=text,
                )
                return np.array(response.data[0].embedding, dtype=np.float32)
            else:
                raise ValueError(f"unknown provider: {provider}")
        except Exception as e:
            if "429" in str(e).lower() or "quota" in str(e).lower() or "rate" in str(e).lower():
                time.sleep(delay)
                delay *= 2
            else:
                if attempt == retries - 1: raise
                time.sleep(delay)
    return None

def cmd_status():
    """Report DB stats + embedder readiness without running an index pass."""
    print(f"📁 Workspace root: {WORKSPACE_ROOT}")
    print(f"📁 Personas dir:   {PERSONAS_DIR}")
    print(f"📁 DB path:        {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("ℹ️  DB not initialized yet — run without --status to build it.")
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM embeddings")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT file_path) FROM embeddings")
        files_indexed = cur.fetchone()[0]
        cur.execute("SELECT MAX(last_updated) FROM embeddings")
        last_ts = cur.fetchone()[0]
        conn.close()
        print(f"📊 Chunks indexed:  {total}")
        print(f"📄 Files indexed:   {files_indexed}")
        if last_ts:
            print(f"🕐 Last updated:    {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_ts))}")
    if not os.path.exists(PERSONAS_DIR):
        print(f"⚠️  Personas dir missing: {PERSONAS_DIR}")
    else:
        files_on_disk = list(Path(PERSONAS_DIR).rglob("*.md"))
        print(f"📄 .md files on disk: {len(files_on_disk)}")
    # Resolution check (don't actually call the API)
    google_key = _read_secret("GOOGLE_API_KEY") or _read_secret("GEMINI_API_KEY")
    openai_key = _read_secret("OPENAI_API_KEY")
    if google_key and GENAI_AVAILABLE:
        print(f"🔑 Embedder ready:  gemini ({GEMINI_MODEL})")
    elif openai_key and OPENAI_AVAILABLE:
        print(f"🔑 Embedder ready:  openai ({OPENAI_EMBED_MODEL}) [N18 fallback]")
    else:
        print("⚠️  Embedder NOT ready — missing GOOGLE_API_KEY/OPENAI_API_KEY or python pkg.")
    return 0


def cmd_index(rebuild: bool = False):
    print(f"🚀 Starting Gemini Multimodal Indexer{' (REBUILD)' if rebuild else ''}")
    print(f"📁 Scanning: {PERSONAS_DIR}")
    if not os.path.exists(PERSONAS_DIR):
        print(f"ERROR: Directory not found -> {PERSONAS_DIR}")
        sys.exit(1)
    # get_embedder() returns (provider, client, model_id) tuple — supports
    # both Gemini (preferred per N18) and OpenAI (fallback).
    embedder = get_embedder()
    print(f"📐 Using embedder: {embedder[0]} ({embedder[2]})", file=sys.stderr)
    client = embedder  # passed straight to get_embedding() which unpacks the tuple
    conn = init_db()
    cursor = conn.cursor()

    if rebuild:
        print("🧹 --rebuild: dropping all existing embeddings")
        cursor.execute("DELETE FROM embeddings")
        conn.commit()

    files = list(Path(PERSONAS_DIR).rglob("*.md"))
    print(f"📄 Found {len(files)} markdown files to process.")

    total_chunks = 0
    skipped = 0
    errors = 0
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip():
                continue
            chunks = chunk_text(content)
            file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            cursor.execute("SELECT id FROM embeddings WHERE id LIKE ? LIMIT 1", (f"{file_hash}_%",))
            if cursor.fetchone() and not rebuild:
                skipped += 1
                continue
            print(f"  Indexing: {file_path.name} ({len(chunks)} chunks)")
            cursor.execute("DELETE FROM embeddings WHERE file_path = ?", (str(file_path),))
            for i, chunk in enumerate(chunks):
                vector = get_embedding(client, chunk)
                if vector is not None:
                    chunk_id = f"{file_hash}_{i}"
                    vector_bytes = vector.tobytes()
                    cursor.execute(
                        "INSERT INTO embeddings (id, file_path, chunk_index, content, vector, last_updated) VALUES (?, ?, ?, ?, ?, ?)",
                        (chunk_id, str(file_path), i, chunk, vector_bytes, time.time())
                    )
                    total_chunks += 1
                    time.sleep(0.5)
            conn.commit()
        except Exception as e:
            errors += 1
            print(f"  ❌ Error processing {file_path.name}: {e}")
    conn.close()
    print(f"✅ Indexing complete. Added {total_chunks} new chunks across {len(files) - skipped - errors} files "
          f"(skipped {skipped} unchanged, {errors} errors).")
    return 0 if errors == 0 else 2


def main():
    parser = argparse.ArgumentParser(
        prog="gemini-indexer",
        description="OpenClaw Gemini Engine indexer — builds the SQLite embeddings DB "
                    "for the coaching-personas collection. Gemini-first with OpenAI fallback (N18).",
    )
    parser.add_argument("--status", action="store_true",
                        help="Report DB stats and embedder readiness without indexing.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop all existing embeddings and re-index from scratch.")
    args = parser.parse_args()

    if args.status:
        sys.exit(cmd_status())
    sys.exit(cmd_index(rebuild=args.rebuild))


if __name__ == "__main__":
    main()
