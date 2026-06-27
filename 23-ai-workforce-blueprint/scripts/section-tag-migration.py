#!/usr/bin/env python3
"""Backfill section_number + mode onto the chunk-level coaching-personas index.

NON-DESTRUCTIVE: vectors untouched, no re-embedding. Idempotent. Full-file backup
before any write. This is the canonical FLEET tagger — a fresh box runs it to bring
the gemini-index.sqlite up to mode/section_number parity with the live operator box.

Section -> mode mapping is imported from embedding_engine (the single source of
truth) so the tagger and gemini-section-indexer.py can never disagree:
  Section 4 = Agent Governance Framework -> leadership
  Section 3 = Coaching Framework         -> coaching
  (everything else)                      -> both
"""
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# Resolve shared-utils both in-repo (../../shared-utils) and on a deployed box
# (~/.openclaw/skills/shared-utils). First match wins.
_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / "shared-utils",
    Path.home() / ".openclaw" / "skills" / "shared-utils",
    Path("/data/.openclaw/skills/shared-utils"),
]
for _p in _CANDIDATES:
    if (_p / "embedding_engine.py").exists():
        sys.path.insert(0, str(_p))
        break

import embedding_engine as E  # type: ignore
from embedding_engine import (  # type: ignore
    LEADERSHIP_SECTION_NUMBER as LEADERSHIP_SECTION,
    COACHING_SECTION_NUMBER as COACHING_SECTION,
)

DB = E.DB_PATH
HDR = re.compile(r'(?m)^##\s+Section\s+(\d+)\b[^\n]*')


def main() -> int:
    if not os.path.exists(DB):
        print(f"ERROR: index not found at {DB} — build it first.", file=sys.stderr)
        return 1

    bak = f"{DB}.SECTIONTAG-BAK-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(DB, bak)                       # full-file backup before any write
    conn = sqlite3.connect(DB, timeout=60.0)
    cur = conn.cursor()

    # 1) add columns (idempotent). DEFAULT 'both' logically backfills existing rows.
    for col, ddl in (("section_number", "INTEGER"), ("mode", "TEXT DEFAULT 'both'")):
        try:
            cur.execute(f"ALTER TABLE embeddings ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mode ON embeddings(mode)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_section_number ON embeddings(section_number)")
    cur.execute("UPDATE embeddings SET mode='both' WHERE mode IS NULL")  # belt-and-suspenders
    conn.commit()

    # 2) tag blueprint chunks by reconstructed offset -> nearest preceding Section header.
    cur.execute("SELECT DISTINCT file_path FROM embeddings WHERE file_path LIKE '%persona-blueprint.md'")
    files = [r[0] for r in cur.fetchall()]
    tagged = mismatch = missing = 0
    for fp in files:
        if not os.path.exists(fp):
            missing += 1
            continue                                            # leave 'both'/NULL
        text = open(fp, encoding="utf-8", errors="replace").read()
        chunks = E.chunk_text(text)
        offs, start = [], 0
        for ch in chunks:
            offs.append(start)
            start = start + len(ch) - E.CHUNK_OVERLAP
        headers = [(m.start(), int(m.group(1))) for m in HDR.finditer(text)]
        cur.execute("SELECT id, chunk_index, content FROM embeddings WHERE file_path=?", (fp,))
        for cid, ci, content in cur.fetchall():
            if ci >= len(chunks) or chunks[ci] != content:      # fail-safe: file drifted
                mismatch += 1
                continue                                        # leave default 'both'
            sec = None
            for pos, num in headers:
                if pos <= offs[ci]:
                    sec = num
                else:
                    break
            mode = ("leadership" if sec == LEADERSHIP_SECTION else
                    "coaching" if sec == COACHING_SECTION else "both")
            cur.execute("UPDATE embeddings SET section_number=?, mode=? WHERE id=?", (sec, mode, cid))
            tagged += 1
    conn.commit()
    conn.close()
    print(f"tagged={tagged} mismatch_left_both={mismatch} missing_files={missing} backup={bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
