#!/usr/bin/env python3
import os, sys, time, sqlite3, hashlib
from pathlib import Path

try:
    from google import genai
    from google.genai import types
    import numpy as np
except ImportError:
    print("CRITICAL ERROR: Missing dependencies.")
    print("Run: pip3 install google-genai numpy --break-system-packages")
    sys.exit(1)

# Workspace Root Configuration
WORKSPACE_ROOT = os.environ.get("WORKSPACE_ROOT", os.path.expanduser("~/.openclaw/workspace"))
CLAWD_ROOT = os.path.expanduser("~/clawd")  # Legacy fallback
if not os.path.isdir(WORKSPACE_ROOT):
    WORKSPACE_ROOT = CLAWD_ROOT

DB_PATH = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/gemini-index.sqlite")
PERSONAS_DIR = os.path.join(WORKSPACE_ROOT, "data/coaching-personas/personas")
if not os.path.exists(PERSONAS_DIR):
    PERSONAS_DIR = os.path.expanduser("~/Downloads/openclaw-master-files/coaching-personas/personas")

GEMINI_MODEL = "gemini-embedding-2-preview"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

def get_client():
    env_path = os.path.join(WORKSPACE_ROOT, "secrets/.env")
    api_key = None
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.strip().split("=", 1)[1].strip('"\'')
                    break
    if not api_key: api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print(f"ERROR: GOOGLE_API_KEY not found in {WORKSPACE_ROOT}/secrets/.env")
        sys.exit(1)
    return genai.Client(api_key=api_key)

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

def get_embedding(client, text, retries=5):
    delay = 2
    for attempt in range(retries):
        try:
            response = client.models.embed_content(
                model=GEMINI_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            return np.array(response.embeddings[0].values, dtype=np.float32)
        except Exception as e:
            if "429" in str(e).lower() or "quota" in str(e).lower():
                time.sleep(delay)
                delay *= 2
            else:
                if attempt == retries - 1: raise
                time.sleep(delay)
    return None

def main():
    print(f"🚀 Starting Gemini Multimodal Indexer")
    print(f"📁 Scanning: {PERSONAS_DIR}")
    if not os.path.exists(PERSONAS_DIR):
        print(f"ERROR: Directory not found -> {PERSONAS_DIR}")
        sys.exit(1)
    client = get_client()
    conn = init_db()
    cursor = conn.cursor()
    files = list(Path(PERSONAS_DIR).rglob("*.md"))
    print(f"📄 Found {len(files)} markdown files to process.")
    
    total_chunks = 0
    # Process just the first 2 files for the test
    for file_path in files[:2]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip(): continue
            chunks = chunk_text(content)
            file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            cursor.execute("SELECT id FROM embeddings WHERE id LIKE ? LIMIT 1", (f"{file_hash}_%",))
            if cursor.fetchone():
                print(f"  Skipping (already indexed): {file_path.name}")
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
            print(f"  ❌ Error processing {file_path.name}: {e}")
    conn.close()
    print(f"✅ Indexing test complete. Added {total_chunks} new chunks.")

if __name__ == "__main__":
    main()
