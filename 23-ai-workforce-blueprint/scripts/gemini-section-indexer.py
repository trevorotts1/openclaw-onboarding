#!/usr/bin/env python3
"""
Section-level Gemini indexer.

Drop-in alternative to chunk-based gemini-indexer.py. Indexes each persona
blueprint at the SECTION level (## headings) instead of character chunks.

Why: chunk-based RAG fragments persona frameworks. A query for "coaching
questions" returns a 1000-char snippet that lacks methodology context. Section-
level retrieval returns the WHOLE Section 6 (Coaching Framework) as the unit.

Schema requirements: the embeddings table must already have these v2.1 columns
(added by gemini-indexer.py migration block):
    persona_id, author, book_title, section_number, section_name,
    mode, source_type, source_depth, confidence, schema_version

Plus the v2.1 wave 3 additions:
    unit_type ('section' | 'chunk'),
    unit_metadata (JSON, e.g. {"word_count": 1234, "has_examples": true})

If those columns don't exist yet, this script adds them via migration before
indexing.

Usage:
    python3 23-ai-workforce-blueprint/scripts/gemini-section-indexer.py \
        --reindex-all
    python3 23-ai-workforce-blueprint/scripts/gemini-section-indexer.py \
        --persona-id hormozi-100m-offers
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared-utils"))
from detect_platform import get_openclaw_paths  # type: ignore


# Reuse env-driven config as gemini-indexer.py does
GEMINI_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview")
MIN_SECTION_WORDS = int(os.environ.get("OPENCLAW_MIN_SECTION_WORDS", "30"))


# ---- Mode mapping (mirrors what's in INSTRUCTIONS.md / PRD v1.1 Ch 2) ----
LEADERSHIP_SECTIONS = {4}        # Section 4: Agent Governance Framework
COACHING_SECTIONS = {6}          # Section 6: Coaching Framework


def get_section_mode(section_number: int, section_name: str) -> str:
    """Returns 'coaching' | 'leadership' | 'both'."""
    if section_number in LEADERSHIP_SECTIONS:
        return "leadership"
    if section_number in COACHING_SECTIONS:
        return "coaching"
    name_lower = (section_name or "").lower()
    if any(kw in name_lower for kw in ["governance", "execution", "qc protocol", "failure pattern", "task activation"]):
        return "leadership"
    if any(kw in name_lower for kw in ["coaching", "assessment", "challenge", "support", "question library"]):
        return "coaching"
    return "both"


def parse_persona_metadata(file_path: Path) -> dict:
    """Extract persona metadata from path. Expected pattern:
       .../coaching-personas/personas/<author-slug>-<book-slug>/persona-blueprint.md
    """
    parts = file_path.parts
    meta = {
        "persona_id": None, "author": None, "book_title": None,
        "source_type": "book", "source_depth": "deep", "confidence": 1.0,
    }
    for i, part in enumerate(parts):
        if part == "personas" and i + 1 < len(parts):
            pid = parts[i + 1]
            meta["persona_id"] = pid
            dash = pid.find("-")
            if dash > 0:
                meta["author"] = pid[:dash]
                meta["book_title"] = pid[dash + 1:].replace("-", " ").title()
            break
    return meta


# ---- Section parsing ----
SECTION_PATTERN = re.compile(
    r"^##\s+(.+?)$\n(.*?)(?=^##\s+|\Z)",
    re.MULTILINE | re.DOTALL,
)


def parse_sections(content: str):
    """Yields (section_number, section_name, body_text)."""
    for match in SECTION_PATTERN.finditer(content):
        heading = match.group(1).strip()
        body = match.group(2)

        # Extract section number
        num_match = re.match(r"(?:Section\s+)?(\d+)[A-Za-z]?\s*[:\-]?\s*(.+)?", heading)
        if num_match:
            try:
                section_num = int(num_match.group(1))
                section_name = (num_match.group(2) or "").strip()
            except (TypeError, ValueError):
                section_num = 0
                section_name = heading
        else:
            section_num = 0
            section_name = heading

        # Skip near-empty sections
        word_count = len(body.split())
        if word_count < MIN_SECTION_WORDS:
            continue
        yield section_num, section_name, body.strip()


# ---- Embedding (deterministic fallback when no API key) ----
def generate_embedding(text: str, dim: int = 768) -> bytes:
    """
    If GOOGLE_API_KEY is set and google-genai is installed, use real Gemini
    embeddings. Else use a deterministic hash-based fallback that produces a
    structurally valid vector — good for testing index plumbing.
    """
    if os.environ.get("GOOGLE_API_KEY"):
        try:
            from google import genai  # type: ignore
            client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
            resp = client.models.embed_content(
                model=GEMINI_MODEL,
                contents=text[:8000],
            )
            embedding = resp.embeddings[0].values
            return struct.pack(f"{len(embedding)}f", *embedding)
        except Exception as e:
            print(f"  WARN: Gemini embed failed ({e}), using deterministic fallback")

    # Deterministic fallback: hash-driven pseudo-embedding (NOT semantic, but valid shape)
    h = hashlib.sha256(text.encode("utf-8")).digest()
    floats = []
    for i in range(dim):
        b = h[i % len(h)]
        floats.append((b - 128) / 128.0)
    return struct.pack(f"{dim}f", *floats)


# ---- Schema migration (idempotent) ----
def ensure_v2_1_schema(conn):
    cur = conn.cursor()
    # Make sure base table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            vector BLOB NOT NULL,
            last_updated REAL NOT NULL
        )
    """)
    # Add v2.1 columns if missing
    new_cols = [
        ("persona_id", "TEXT"),
        ("author", "TEXT"),
        ("book_title", "TEXT"),
        ("section_number", "INTEGER"),
        ("section_name", "TEXT"),
        ("mode", "TEXT DEFAULT 'both'"),
        ("domain_tags", "TEXT"),
        ("source_type", "TEXT DEFAULT 'unknown'"),
        ("source_depth", "TEXT DEFAULT 'unknown'"),
        ("confidence", "REAL DEFAULT 1.0"),
        ("schema_version", "INTEGER DEFAULT 2"),
        ("persona_version", "INTEGER DEFAULT 1"),
        ("unit_type", "TEXT DEFAULT 'chunk'"),
        ("unit_metadata", "TEXT"),
    ]
    for col, col_type in new_cols:
        try:
            cur.execute(f"ALTER TABLE embeddings ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists
    # Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mode ON embeddings(mode)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_persona_id ON embeddings(persona_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unit_type ON embeddings(unit_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_section_number ON embeddings(section_number)")
    conn.commit()


# ---- Main indexing ----
def index_blueprint(conn, blueprint_path: Path, dry_run: bool = False) -> int:
    meta = parse_persona_metadata(blueprint_path)
    if not meta["persona_id"]:
        print(f"  SKIP {blueprint_path}: cannot parse persona_id from path")
        return 0

    content = blueprint_path.read_text(encoding="utf-8", errors="replace")
    cur = conn.cursor()

    # First, delete any existing CHUNK rows for this persona (we're replacing with section-level)
    cur.execute(
        "DELETE FROM embeddings WHERE persona_id = ? AND unit_type IN ('chunk', NULL)",
        (meta["persona_id"],),
    )

    count = 0
    for section_num, section_name, body in parse_sections(content):
        full_text = f"## {section_name}\n{body}"
        word_count = len(full_text.split())
        mode = get_section_mode(section_num, section_name)

        chunk_id = f"{meta['persona_id']}__section_{section_num:02d}"
        if dry_run:
            print(f"  [DRY-RUN] would index {chunk_id} ({word_count} words, mode={mode})")
            count += 1
            continue

        vector_bytes = generate_embedding(full_text)
        cur.execute("""
            INSERT OR REPLACE INTO embeddings
              (id, file_path, chunk_index, content, vector, last_updated,
               persona_id, author, book_title, section_number, section_name,
               mode, source_type, source_depth, confidence, schema_version,
               unit_type, unit_metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2, 'section', ?)
        """, (
            chunk_id, str(blueprint_path), section_num, full_text, vector_bytes, time.time(),
            meta["persona_id"], meta["author"], meta["book_title"], section_num, section_name,
            mode, meta["source_type"], meta["source_depth"], meta["confidence"],
            json.dumps({"word_count": word_count}),
        ))
        count += 1
        print(f"  indexed section {section_num:02d}: {section_name[:60]} ({word_count}w, {mode})")
    conn.commit()
    return count


def main():
    parser = argparse.ArgumentParser(description="Section-level Gemini indexer for persona blueprints")
    parser.add_argument("--reindex-all", action="store_true", help="Re-index every persona at section level")
    parser.add_argument("--persona-id", help="Index only a specific persona by id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = get_openclaw_paths()
    db_path = paths["gemini_index"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    personas_root = paths["coaching_personas"] / "personas"

    if not personas_root.exists():
        print(f"No personas directory at {personas_root}. Run Skill 22 first.")
        return 1

    conn = sqlite3.connect(str(db_path))
    ensure_v2_1_schema(conn)

    targets = []
    if args.persona_id:
        bp = personas_root / args.persona_id / "persona-blueprint.md"
        if bp.exists():
            targets.append(bp)
        else:
            print(f"ERROR: persona-blueprint.md not found at {bp}")
            return 1
    else:
        for persona_dir in personas_root.iterdir():
            if not persona_dir.is_dir():
                continue
            bp = persona_dir / "persona-blueprint.md"
            if bp.exists():
                targets.append(bp)

    print(f"Indexing {len(targets)} persona blueprint(s) at section level")
    print(f"DB: {db_path}")
    print(f"Embedding model: {GEMINI_MODEL}{' (real Gemini)' if os.environ.get('GOOGLE_API_KEY') else ' (deterministic fallback — set GOOGLE_API_KEY for real embeddings)'}")
    print()

    total = 0
    for bp in targets:
        print(f"=== {bp.parent.name} ===")
        n = index_blueprint(conn, bp, dry_run=args.dry_run)
        total += n
        print(f"  -> {n} sections indexed")
        print()

    conn.close()

    print("=" * 60)
    print(f"Total sections indexed: {total}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
