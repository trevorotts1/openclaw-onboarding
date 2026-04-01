#!/usr/bin/env python3
"""
Gemini Embedding 2 Indexer
Scans markdown files, generates embeddings via Gemini Embedding 2 Preview,
and stores them in a local SQLite database for semantic search.

Usage:
  python3 gemini-indexer.py              # Run indexing
  python3 gemini-indexer.py --status     # Check status (dirs, db, file count)
  python3 gemini-indexer.py --init       # Create required directories
  python3 gemini-indexer.py --dry-run    # Show what would be indexed (no API calls)
"""
import os, sys, time, sqlite3, hashlib, json
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_PATH = os.path.expanduser("~/clawd/data/coaching-personas/gemini-index.sqlite")
PERSONAS_DIR_PRIMARY = os.path.expanduser("~/clawd/data/coaching-personas/personas")
PERSONAS_DIR_FALLBACK = os.path.expanduser("~/Downloads/openclaw-master-files/coaching-personas/personas")

COLLECTIONS = {
    "coaching-personas": {
        "primary": PERSONAS_DIR_PRIMARY,
        "fallback": PERSONAS_DIR_FALLBACK,
        "glob": "**/*.md",
    },
    "master-files": {
        "primary": os.path.expanduser("~/clawd/data/master-files"),
        "fallback": os.path.expanduser("~/Downloads/openclaw-master-files"),
        "glob": "**/*.md",
    },
}

GEMINI_MODEL = "gemini-embedding-2-preview"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_api_key():
    # Priority 1: OpenClaw standard location
    openclaw_env = os.path.expanduser("~/.openclaw/.env")
    # Priority 2: OpenClaw secrets folder
    secrets_env = os.path.expanduser("~/.openclaw/secrets/.env")
    # Priority 3: Clawd secrets (Trevor's machine only)
    clawd_env = os.path.expanduser("~/clawd/secrets/.env")
    # Priority 4: User's workspace
    workspace_env = os.path.expanduser("~/.config/openclaw/.env")

    for env_path in [openclaw_env, secrets_env, clawd_env, workspace_env]:
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GOOGLE_API_KEY=") or line.startswith("GEMINI_API_KEY="):
                        return line.split("=", 1)[1].strip('"\'')

    # Priority 5: Environment variables
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

def resolve_dir(config):
    if os.path.isdir(config["primary"]):
        return config["primary"]
    if os.path.isdir(config["fallback"]):
        return config["fallback"]
    return None

def count_md_files(directory, glob_pattern="**/*.md"):
    return len(list(Path(directory).rglob(glob_pattern)))

# ---------------------------------------------------------------------------
# --status: check environment and report
# ---------------------------------------------------------------------------
def cmd_status():
    print("🔍 Gemini Engine Status Check")
    print("-" * 40)

    # API key
    api_key = get_api_key()
    if api_key:
        print(f"✅ API key: found ({api_key[:8]}...)")
    else:
        print("❌ API key: NOT FOUND (add GOOGLE_API_KEY to ~/clawd/secrets/.env)")

    # Python deps
    try:
        import google.genai  # noqa: F401
        print("✅ google-genai package: installed")
    except ImportError:
        print("❌ google-genai package: NOT INSTALLED (run: pip3 install google-genai --break-system-packages)")

    try:
        import numpy  # noqa: F401
        print("✅ numpy package: installed")
    except ImportError:
        print("❌ numpy package: NOT INSTALLED (run: pip3 install numpy --break-system-packages)")

    # Database
    db_dir = os.path.dirname(DB_PATH)
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM embeddings")
        count = cur.fetchone()[0]
        conn.close()
        print(f"✅ Database: {DB_PATH} ({count} embeddings)")
    else:
        print(f"⚠️  Database: not yet created ({DB_PATH})")
        if os.path.isdir(db_dir):
            print(f"   Directory exists: {db_dir}")
        else:
            print(f"   Directory missing: {db_dir}")

    # Collections
    for name, config in COLLECTIONS.items():
        resolved = resolve_dir(config)
        if resolved:
            count = count_md_files(resolved, config["glob"])
            print(f"✅ Collection '{name}': {resolved} ({count} .md files)")
        else:
            print(f"⚠️  Collection '{name}': directory not found")
            print(f"   Checked: {config['primary']}")
            print(f"   Checked: {config['fallback']}")

    # Summary
    all_ok = bool(api_key)
    try:
        import google.genai  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        all_ok = False

    print("-" * 40)
    if all_ok:
        print("✅ Gemini Engine is ready. Run without --status to start indexing.")
    else:
        print("⚠️  Gemini Engine is NOT ready. Fix the issues above first.")

# ---------------------------------------------------------------------------
# --init: create required directories
# ---------------------------------------------------------------------------
def cmd_init():
    print("📁 Creating required directories...")
    dirs = [
        os.path.dirname(DB_PATH),
        PERSONAS_DIR_PRIMARY,
        PERSONAS_DIR_FALLBACK,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  ✅ {d}")
    print("Done. Directories created.")

# ---------------------------------------------------------------------------
# --dry-run: show what would be indexed
# ---------------------------------------------------------------------------
def cmd_dry_run():
    print("🔍 Dry run — scanning collections (no API calls)")
    for name, config in COLLECTIONS.items():
        resolved = resolve_dir(config)
        if resolved:
            files = list(Path(resolved).rglob(config["glob"]))
            print(f"  📁 '{name}': {resolved} — {len(files)} files")
            for f in files[:5]:
                print(f"     {f.name}")
            if len(files) > 5:
                print(f"     ... and {len(files) - 5} more")
        else:
            print(f"  ⚠️  '{name}': directory not found (skipping)")
    print("Done.")

# ---------------------------------------------------------------------------
# Main indexing
# ---------------------------------------------------------------------------
def main():
    from google import genai
    from google.genai import types
    import numpy as np

    def get_client():
        api_key = get_api_key()
        if not api_key:
            print("ERROR: GOOGLE_API_KEY not found in ~/clawd/secrets/.env")
            sys.exit(1)
        return genai.Client(api_key=api_key)

    def init_db():
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER,
            content TEXT, vector BLOB, last_updated REAL)''')
        conn.commit()
        return conn

    def chunk_text(text):
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

    def get_embedding(client, text, retries=5):
        delay = 2
        for attempt in range(retries):
            try:
                response = client.models.embed_content(
                    model=GEMINI_MODEL,
                    contents=text,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
                )
                return np.array(response.embeddings[0].values, dtype=np.float32)
            except Exception as e:
                if "429" in str(e).lower() or "quota" in str(e).lower():
                    time.sleep(delay)
                    delay *= 2
                else:
                    if attempt == retries - 1:
                        raise
                    time.sleep(delay)
        return None

    print("🚀 Starting Gemini Multimodal Indexer")
    client = get_client()
    conn = init_db()
    cursor = conn.cursor()

    total_chunks = 0
    for name, config in COLLECTIONS.items():
        resolved = resolve_dir(config)
        if not resolved:
            print(f"⚠️  Skipping '{name}': directory not found")
            continue
        print(f"\n📁 Scanning: {resolved} ({name})")
        files = list(Path(resolved).rglob(config["glob"]))
        print(f"📄 Found {len(files)} markdown files.")

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
                if cursor.fetchone():
                    print(f"  ⏭️  Skipping (already indexed): {file_path.name}")
                    continue
                print(f"  📝 Indexing: {file_path.name} ({len(chunks)} chunks)")
                cursor.execute(
                    "DELETE FROM embeddings WHERE file_path = ?", (str(file_path),)
                )
                for i, chunk in enumerate(chunks):
                    vector = get_embedding(client, chunk)
                    if vector is not None:
                        chunk_id = f"{file_hash}_{i}"
                        vector_bytes = vector.tobytes()
                        cursor.execute(
                            "INSERT OR REPLACE INTO embeddings "
                            "(id, file_path, chunk_index, content, vector, last_updated) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (chunk_id, str(file_path), i, chunk, vector_bytes, time.time()),
                        )
                        total_chunks += 1
                        time.sleep(0.5)
                conn.commit()
            except Exception as e:
                print(f"  ❌ Error processing {file_path.name}: {e}")

    conn.close()
    print(f"\n✅ Indexing complete. Added {total_chunks} new chunks.")


if __name__ == "__main__":
    if "--status" in sys.argv:
        cmd_status()
    elif "--init" in sys.argv:
        cmd_init()
    elif "--dry-run" in sys.argv:
        cmd_dry_run()
    else:
        main()
