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
# PRD 1.8: GEMINI_MODEL is the single pinned constant in embedding_engine.py.
# Import it here so a model change in one place propagates everywhere.
# EMBED-3: get_embedder/get_embedding are the ONLY sanctioned embed path —
# they read every canonical secret store (not just process env), pin
# output_dimensionality=3072 + task_type=RETRIEVAL_DOCUMENT, retry on quota,
# and HARD-FAIL on a wrong-dimension vector.
from embedding_engine import (  # type: ignore
    GEMINI_MODEL,
    GEMINI_OUTPUT_DIM,
    LEADERSHIP_SECTION_NUMBER,
    COACHING_SECTION_NUMBER,
    get_embedder,
    get_embedding,
    is_credential_error,
)
MIN_SECTION_WORDS = int(os.environ.get("OPENCLAW_MIN_SECTION_WORDS", "30"))

# EMBED-3: metadata stamped on rows written in the EXPLICIT fake mode
# (--allow-fake-embeddings, tests/plumbing only). The stamp is TRUTHFUL so no
# downstream consumer can mistake a fake vector for a real Gemini one —
# get_db_index_provider() will refuse to treat the DB as a clean gemini index
# and `--verify` fails it.
FAKE_PROVIDER = "fake"
FAKE_MODEL = "deterministic-hash-768"
FAKE_DIM = 768


# ---- Mode mapping (mirrors what's in INSTRUCTIONS.md / PRD v1.1 Ch 2) ----
# Single source of truth: embedding_engine.{LEADERSHIP,COACHING}_SECTION_NUMBER.
# Section 4: Agent Governance Framework (leadership). Section 3: Coaching Framework.
# Mirrors section-tag-migration.py (the live tagger) — cannot drift.
LEADERSHIP_SECTIONS = {LEADERSHIP_SECTION_NUMBER}
COACHING_SECTIONS = {COACHING_SECTION_NUMBER}


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


# ---- Embedding (EMBED-3 hard gate: real vectors or fail loud) ----
#
# HISTORY (the defect this replaces): the old generate_embedding() silently
# fell back to a hash-derived FAKE 768-dim vector whenever GOOGLE_API_KEY was
# missing from the process env (it never read secrets/.env) OR when ANY Gemini
# exception occurred — and then stamped the row provider='gemini',
# model=gemini-embedding-2, dim=3072 (lying metadata), so drift detection
# could never catch it. It also bypassed output_dimensionality=3072,
# task_type=RETRIEVAL_DOCUMENT, and the engine's retry/backoff.
#
# NOW: real embeds go through embedding_engine.get_embedding() (all secret
# stores, pinned dims, retries, dim assertion). No key / no SDK => the run
# FAILS LOUD (exit 4) unless the caller EXPLICITLY passed
# --allow-fake-embeddings, in which case fake vectors are written with
# TRUTHFUL metadata (provider='fake', model='deterministic-hash-768', dim=768)
# and only into an explicitly-chosen --db (never the default live index).

def resolve_real_embedder():
    """Resolve the Gemini embedder via the engine, or None if unavailable."""
    try:
        return get_embedder(provider_hint="gemini")
    except SystemExit:
        return None


def generate_fake_embedding(text: str, dim: int = FAKE_DIM) -> bytes:
    """Deterministic hash-driven pseudo-embedding (NOT semantic, valid shape).
    Only reachable via --allow-fake-embeddings; rows are stamped provider='fake'."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    floats = []
    for i in range(dim):
        b = h[i % len(h)]
        floats.append((b - 128) / 128.0)
    return struct.pack(f"{dim}f", *floats)


def embed_section(embedder, text: str) -> bytes:
    """
    Real Gemini embed via the canonical engine. Raises / exits on failure —
    NEVER silently degrades to a fake vector.
    """
    vec = get_embedding(embedder, text[:8000])
    if vec is None or vec.shape[0] != GEMINI_OUTPUT_DIM:
        raise RuntimeError(
            f"embedding returned {'None' if vec is None else vec.shape[0]} "
            f"instead of a {GEMINI_OUTPUT_DIM}-dim vector — refusing to write"
        )
    return vec.tobytes()


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
        # md5 of the WHOLE blueprint at index time. Lets index_blueprint() skip a
        # re-embed when the source content is byte-identical to what's already
        # stored (furnace guard — see the HASH-SKIP block). NULL on rows written
        # before this column existed; they re-index once, then populate it.
        ("content_hash", "TEXT"),
        # PRD 1.8 provider/model/dim metadata — must match embedding_engine.py's
        # schema so get_db_index_provider() can identify the index provider and
        # semantic search can enforce same-provider query embedding. Rows written
        # by older versions of this indexer (before this fix) may have NULL here;
        # _backfill_provider_columns() in embedding_engine.py auto-stamps them on
        # first init_db() call when the columns were previously absent, but does
        # NOT re-run when the columns already exist. This indexer now stamps
        # every new row explicitly so no delta persona arrives blank-provider.
        ("provider", "TEXT"),
        ("model", "TEXT"),
        ("dim", "INTEGER"),
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
def index_blueprint(conn, blueprint_path: Path, embedder=None,
                    allow_fake: bool = False,
                    dry_run: bool = False, force: bool = False) -> int:
    """Returns the number of sections indexed, or -1 if the blueprint was
    HASH-SKIPped (content byte-identical to what's already in the index).

    embedder: the (provider, client, model) tuple from resolve_real_embedder().
    allow_fake: EXPLICIT opt-in — write deterministic fake vectors with
    truthful provider='fake' metadata (tests/plumbing only)."""
    meta = parse_persona_metadata(blueprint_path)
    if not meta["persona_id"]:
        print(f"  SKIP {blueprint_path}: cannot parse persona_id from path")
        return 0

    content = blueprint_path.read_text(encoding="utf-8", errors="replace")
    cur = conn.cursor()

    # ---- md5 content-hash skip (FURNACE GUARD) ----
    # Mirrors embedding_engine.py:920-929: re-embedding every section on every run
    # is pure token/compute bloat, and this indexer can sit behind a recurring
    # trigger. If a section row for this persona already carries this exact md5,
    # the source is unchanged → do NOT re-embed. A genuine edit changes the md5
    # (no matching row → re-index); `--force` bypasses the skip entirely. The check
    # runs BEFORE the destructive chunk-row DELETE so a skip leaves the index intact.
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    if not force and not dry_run:
        cur.execute(
            "SELECT 1 FROM embeddings "
            "WHERE persona_id = ? AND unit_type = 'section' AND content_hash = ? LIMIT 1",
            (meta["persona_id"], content_hash),
        )
        if cur.fetchone():
            print(
                f"  HASH-SKIP {meta['persona_id']}: content unchanged "
                f"(md5={content_hash[:12]}…) — already indexed; not re-embedding. "
                f"Use --force to override."
            )
            return -1

    # First, delete any existing CHUNK rows for this persona (we're replacing
    # with section-level). NOTE: `unit_type IN ('chunk', NULL)` never matched
    # NULL (SQL semantics) — fixed to an explicit IS NULL clause.
    cur.execute(
        "DELETE FROM embeddings WHERE persona_id = ? "
        "AND (unit_type = 'chunk' OR unit_type IS NULL)",
        (meta["persona_id"],),
    )

    if allow_fake:
        prov, mdl, dim = FAKE_PROVIDER, FAKE_MODEL, FAKE_DIM
    else:
        prov, mdl, dim = "gemini", GEMINI_MODEL, GEMINI_OUTPUT_DIM

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

        if allow_fake:
            vector_bytes = generate_fake_embedding(full_text)
        else:
            # Real embed or raise — never a silent fake (EMBED-3 hard gate).
            vector_bytes = embed_section(embedder, full_text)
        cur.execute("""
            INSERT OR REPLACE INTO embeddings
              (id, file_path, chunk_index, content, vector, last_updated,
               persona_id, author, book_title, section_number, section_name,
               mode, source_type, source_depth, confidence, schema_version,
               unit_type, unit_metadata, content_hash,
               provider, model, dim)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2, 'section', ?, ?, ?, ?, ?)
        """, (
            chunk_id, str(blueprint_path), section_num, full_text, vector_bytes, time.time(),
            meta["persona_id"], meta["author"], meta["book_title"], section_num, section_name,
            mode, meta["source_type"], meta["source_depth"], meta["confidence"],
            json.dumps({"word_count": word_count}), content_hash,
            prov, mdl, dim,
        ))
        count += 1
        print(f"  indexed section {section_num:02d}: {section_name[:60]} ({word_count}w, {mode})")
    conn.commit()

    # EMBED-3 post-write verification: every row just written for this persona
    # must be self-consistent (blob length == stamped dim * 4 == the mode's
    # contract dim). A violation aborts the whole run non-zero — it can only
    # mean a fake/truncated vector nearly reached the index.
    if not dry_run and count > 0:
        bad = cur.execute(
            "SELECT id, dim, length(vector) FROM embeddings "
            "WHERE persona_id = ? AND unit_type = 'section' "
            "AND (dim != ? OR length(vector) != ? OR provider != ? OR model != ?)",
            (meta["persona_id"], dim, dim * 4, prov, mdl),
        ).fetchall()
        if bad:
            raise RuntimeError(
                f"post-write verification FAILED for {meta['persona_id']}: "
                f"{len(bad)} row(s) violate the {prov}/{mdl}@{dim} contract "
                f"(first: {bad[0]})"
            )
    return count


def main():
    parser = argparse.ArgumentParser(description="Section-level Gemini indexer for persona blueprints")
    parser.add_argument("--reindex-all", action="store_true", help="Re-index every persona at section level")
    parser.add_argument("--persona-id", help="Index only a specific persona by id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="Bypass the md5 content-hash skip and re-embed every section, "
                             "even if the source blueprint is unchanged")
    parser.add_argument("--db", default=None,
                        help="Explicit DB path (default: the canonical live "
                             "coaching-personas/gemini-index.sqlite). Used by "
                             "build-and-publish.sh staging and by tests.")
    parser.add_argument("--personas-root", default=None,
                        help="Explicit personas root to scan (default: the "
                             "canonical live coaching-personas/personas dir).")
    parser.add_argument("--allow-fake-embeddings", action="store_true",
                        help="EXPLICIT opt-in (tests/plumbing only): write "
                             "deterministic fake vectors stamped provider='fake' "
                             "dim=768. Requires --db or OPENCLAW_SANDBOX=1 — the "
                             "default live index can never receive fake vectors.")
    args = parser.parse_args()

    paths = get_openclaw_paths()
    if args.db:
        db_path = Path(args.db)
    else:
        # EMBED-1: paths["gemini_index"] is now the SAME file the search path
        # reads (workspace/data/coaching-personas/gemini-index.sqlite).
        db_path = Path(paths["gemini_index"])
        # EMBED-2 sandbox hard gate: a build targeting the DEFAULT live DB
        # must not silently land in a sandboxed HOME.
        try:
            from detect_platform import assert_live_workspace_for_write  # type: ignore
            assert_live_workspace_for_write("gemini-section-indexer", db_path)
        except ImportError:
            pass
        # Legacy-drift self-heal warning: pre-fix builds wrote to
        # workspace/data/gemini-index.sqlite (a DB the search path never
        # reads). If that orphan exists, say so loudly.
        legacy = paths.get("legacy_gemini_index")
        if legacy and Path(legacy).exists() and Path(legacy) != db_path:
            print(
                f"WARN: orphaned legacy index detected at {legacy} — rows "
                f"written there by pre-fix builds are INVISIBLE to search. "
                f"See docs/EMBEDDINGS.md ('Landing a delta') to converge, "
                f"then delete the orphan.",
                file=sys.stderr,
            )

    if args.allow_fake_embeddings and not args.db \
            and os.environ.get("OPENCLAW_SANDBOX", "").strip() != "1":
        print(
            "ERROR: --allow-fake-embeddings targets the DEFAULT live index. "
            "Fake vectors may only be written to an explicit --db target (or "
            "under OPENCLAW_SANDBOX=1). Refusing.",
            file=sys.stderr,
        )
        return 4

    db_path.parent.mkdir(parents=True, exist_ok=True)
    personas_root = Path(args.personas_root) if args.personas_root \
        else (Path(paths["coaching_personas"]) / "personas")

    if not personas_root.exists():
        print(f"No personas directory at {personas_root}. Run Skill 22 first.")
        return 1

    # EMBED-3: resolve the embedder UP FRONT — real vectors or fail loud.
    embedder = None
    if args.allow_fake_embeddings:
        print(
            "=" * 60 + "\n"
            "!! FAKE-EMBEDDING MODE (--allow-fake-embeddings) !!\n"
            "Vectors are deterministic hashes, NOT semantic. Rows are stamped\n"
            f"provider='{FAKE_PROVIDER}' model='{FAKE_MODEL}' dim={FAKE_DIM} so\n"
            "no consumer can mistake them for real Gemini vectors.\n" + "=" * 60
        )
    elif not args.dry_run:
        embedder = resolve_real_embedder()
        if embedder is None:
            print(
                "ERROR: no usable Gemini embedder (GOOGLE_API_KEY/GEMINI_API_KEY "
                "not found in any canonical secret store, or google-genai not "
                "installed). REFUSING to index — this tool never writes fake "
                "vectors implicitly. Fix the key/SDK, or pass "
                "--allow-fake-embeddings WITH --db for plumbing tests. "
                "(embedding-subsystem hard gate EMBED-3)",
                file=sys.stderr,
            )
            return 4

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
    print(f"Embedding model: "
          f"{FAKE_MODEL + ' (FAKE — explicit opt-in)' if args.allow_fake_embeddings else GEMINI_MODEL + ' (real Gemini via embedding_engine)'}")
    print()

    total = 0
    skipped = 0
    try:
        for bp in targets:
            print(f"=== {bp.parent.name} ===")
            n = index_blueprint(conn, bp, embedder=embedder,
                                allow_fake=args.allow_fake_embeddings,
                                dry_run=args.dry_run, force=args.force)
            if n < 0:
                skipped += 1
                print("  -> unchanged (hash-skip; no re-embed)")
            else:
                total += n
                print(f"  -> {n} sections indexed")
            print()
    except Exception as e:
        conn.close()
        # A-U8: a credential-shaped failure discovered MID-RUN (key present
        # but rejected by the API — revoked / wrong-project / malformed) is
        # classified the SAME way as the upfront "no key" preflight refusal
        # above (exit 4) — both are honest, expected, non-fatal states a
        # caller (orchestrator.py Phase 5) may defer rather than block on.
        # Any OTHER exception (corrupt content, a genuine bug) is NOT
        # deferral-eligible: exit 6 keeps it fail-loud, distinct from 4, so
        # a caller never silently treats a real defect as "just missing a
        # key".
        if is_credential_error(e):
            print(f"ERROR: indexing aborted — credential rejected: {e}", file=sys.stderr)
            return 4
        print(f"ERROR: indexing aborted — {e}", file=sys.stderr)
        return 6

    conn.close()

    print("=" * 60)
    print(f"Total sections indexed: {total}  (personas skipped unchanged: {skipped})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
