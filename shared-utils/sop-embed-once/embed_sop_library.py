#!/usr/bin/env python3
"""
shared-utils/sop-embed-once/embed_sop_library.py
─────────────────────────────────────────────────────────────────────────────
P4-03 step 1 — the "embed once, push to clients" pipeline for the CC SOP /
routing embedding system (System 2), mirroring the proven Corpus-1
(coaching-persona) pattern in shared-utils/embedding_engine.py +
shared-utils/prebuilt-index/build-and-publish.sh.

This module embeds the CANONICAL shared SOP library (sops.jsonl — the same
content 32-command-center-setup/scripts/ingest-sop-library.py loads into every
client's mission-control.db) ONCE with the operator's key, into a sqlite
export whose `sop_embeddings` table has the EXACT shape of Command Center
migration 057:

    sop_embeddings(
        sop_id          TEXT PRIMARY KEY,
        embedding       BLOB NOT NULL,
        embedding_model TEXT NOT NULL,
        embedding_dims  INTEGER NOT NULL,
        embedded_at     TEXT NOT NULL
    )

Plus one ADDITIVE column, `source_content_md5 TEXT`, used ONLY by this build
pipeline's HASH-SKIP guard (never read by the CC app — it never does
`SELECT *` against sop_embeddings, confirmed by grep across src/ + scripts/,
so an extra column is safe to ship in the asset and safe to import into a
live mission-control.db).

Embed text construction mirrors sop-embeddings.ts::buildSOPEmbedText() EXACTLY
(title + description + keywords + first 8 step names) so a shared-library SOP
embedded here and a client-authored SOP embedded live by backfill-sop-
embeddings.ts land in the SAME vector space (same model, same text-shaping
contract).

HASH-SKIP (the incremental / furnace-safe contract, mirroring
gemini-section-indexer.py's md5 guard): a SOP is re-embedded ONLY when its
embed text's md5 differs from the md5 already stored in source_content_md5.
Adding SOP #2,556 to sops.jsonl re-embeds ONE row, never the full library.

REAL-VECTOR HARD GATE (mirrors embedding_engine.py's _assert_vector_dim /
verify_index_integrity): every row must carry a real gemini/3072-dim vector
before the asset may be published — a wrong-dimension or fake vector is
refused, never persisted.

Usage:
    embed_sop_library.py --jsonl sops.jsonl --db sop-embeddings.sqlite \
        [--reindex-all] [--sop-slug <slug> ...] [--dry-run] [--force]
    embed_sop_library.py --db sop-embeddings.sqlite --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_SELF_DIR = Path(__file__).resolve().parent
_SHARED_UTILS = _SELF_DIR.parent
sys.path.insert(0, str(_SHARED_UTILS))

# embedding_engine.py is the ONE implementation of provider resolution +
# the real-vector hard gate (EMBED-3). Reused here rather than re-derived so
# the SOP pipeline and the persona pipeline can never drift on model/dims.
from embedding_engine import (  # noqa: E402
    GEMINI_MODEL,
    GEMINI_OUTPUT_DIM,
    get_embedder,
    get_embedding,
    _assert_vector_dim,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sop_embeddings (
    sop_id             TEXT PRIMARY KEY,
    embedding          BLOB NOT NULL,
    embedding_model    TEXT NOT NULL,
    embedding_dims     INTEGER NOT NULL,
    embedded_at        TEXT NOT NULL,
    source_content_md5 TEXT
);
CREATE INDEX IF NOT EXISTS idx_sop_embeddings_embedded_at ON sop_embeddings(embedded_at);
"""


# ---------------------------------------------------------------------------
# Embed-text construction — MUST mirror sop-embeddings.ts::buildSOPEmbedText()
# ---------------------------------------------------------------------------
def build_sop_embed_text(sop: dict) -> str:
    """Title + description + keywords + first 8 step names, '|'-joined.

    Mirrors src/lib/sop-embeddings.ts::buildSOPEmbedText() in the CC repo
    field-for-field so a shared-library SOP embedded here and a client SOP
    embedded live land in the same vector space for the same content shape.
    """
    parts = [sop.get("name", "") or ""]

    description = sop.get("description")
    if description:
        parts.append(description)

    keywords = sop.get("task_keywords")
    if keywords:
        parts.append(keywords)

    steps = sop.get("steps", [])
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except (json.JSONDecodeError, TypeError):
            steps = []
    if isinstance(steps, list):
        step_names = [s.get("name") for s in steps[:8] if isinstance(s, dict) and s.get("name")]
        if step_names:
            parts.append("; ".join(step_names))

    return " | ".join(p for p in parts if p)


def sop_id_from_slug(slug: str) -> str:
    """Mirror ingest-sop-library.py's id derivation: sop_<slug with dashes as underscores>[:60]."""
    return "sop_" + slug.replace("-", "_")[:60]


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def load_sops_jsonl(path: str) -> list[dict]:
    sops = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            sop = json.loads(line)
            if sop.get("slug"):
                sops.append(sop)
    return sops


# ---------------------------------------------------------------------------
# Incremental embed (HASH-SKIP)
# ---------------------------------------------------------------------------
def embed_delta(
    conn: sqlite3.Connection,
    sops: list[dict],
    embed_fn=None,
    force: bool = False,
    only_slugs: Optional[set[str]] = None,
    dry_run: bool = False,
) -> dict:
    """Embed only new/changed SOPs (md5 HASH-SKIP). Returns stats dict.

    embed_fn: callable(text: str) -> real vector with a `.shape[0]` attribute
    (numpy array). Defaults to the real Gemini embedder via embedding_engine.
    Tests inject a fake embed_fn so the hash-skip / dry-run / gate logic is
    provable WITHOUT a live API key (mirrors the existing repo pattern of
    testing gate logic, not live network calls, e.g.
    tests/unit/provision-idempotency.test.sh).
    """
    ensure_schema(conn)
    cur = conn.cursor()

    stats = {"embedded": 0, "skipped_unchanged": 0, "skipped_not_selected": 0, "errors": 0}

    real_embedder = None
    if embed_fn is None and not dry_run:
        provider, client, model_id = get_embedder(provider_hint="gemini")
        real_embedder = (provider, client, model_id)

    for sop in sops:
        slug = sop["slug"]
        if only_slugs is not None and slug not in only_slugs:
            stats["skipped_not_selected"] += 1
            continue

        sop_id = sop_id_from_slug(slug)
        text = build_sop_embed_text(sop)
        content_md5 = _md5(text)

        row = cur.execute(
            "SELECT source_content_md5 FROM sop_embeddings WHERE sop_id=?", (sop_id,)
        ).fetchone()
        already_current = row is not None and row[0] == content_md5

        if already_current and not force:
            stats["skipped_unchanged"] += 1
            continue

        if dry_run:
            stats["embedded"] += 1
            continue

        try:
            if embed_fn is not None:
                vec = embed_fn(text)
                dim = len(vec)
                blob = _vector_to_blob(vec)
                model_name = GEMINI_MODEL
            else:
                _provider, _client, model_id = real_embedder
                vec = get_embedding(real_embedder, text)
                _assert_vector_dim(vec, GEMINI_OUTPUT_DIM, _provider, model_id)
                dim = int(vec.shape[0])
                blob = vec.astype("float32").tobytes() if hasattr(vec, "astype") else _vector_to_blob(vec)
                model_name = model_id

            cur.execute(
                """INSERT INTO sop_embeddings
                       (sop_id, embedding, embedding_model, embedding_dims, embedded_at, source_content_md5)
                   VALUES (?, ?, ?, ?, datetime('now'), ?)
                   ON CONFLICT(sop_id) DO UPDATE SET
                       embedding=excluded.embedding,
                       embedding_model=excluded.embedding_model,
                       embedding_dims=excluded.embedding_dims,
                       embedded_at=excluded.embedded_at,
                       source_content_md5=excluded.source_content_md5""",
                (sop_id, blob, model_name, dim, content_md5),
            )
            stats["embedded"] += 1
        except Exception as exc:  # noqa: BLE001 — surfaced in stats, loud print below
            stats["errors"] += 1
            print(f"  [embed-sop-library] ERROR embedding slug={slug}: {exc}", file=sys.stderr)

    conn.commit()
    return stats


def _vector_to_blob(vec) -> bytes:
    """float32 little-endian blob — matches float32ToBuffer() in sop-embeddings.ts
    (Buffer.from(Float32Array.buffer), which is little-endian on every fleet
    platform: x86_64 and Apple Silicon are both LE)."""
    import struct

    return struct.pack("<%df" % len(vec), *[float(x) for x in vec])


# ---------------------------------------------------------------------------
# REAL-VECTOR HARD GATE (publish-side assertion)
# ---------------------------------------------------------------------------
def verify_real_vectors(conn: sqlite3.Connection, expected_model: str, expected_dim: int) -> tuple[bool, int, str]:
    """Refuse to publish unless EVERY row is expected_model / expected_dim
    with a blob whose byte length matches (dim * 4 bytes, float32).
    Returns (ok, bad_row_count, detail)."""
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT sop_id, embedding_model, embedding_dims, length(embedding) FROM sop_embeddings"
    ).fetchall()
    bad = []
    for sop_id, model, dims, blob_len in rows:
        expected_bytes = expected_dim * 4
        if model != expected_model or dims != expected_dim or blob_len != expected_bytes:
            bad.append((sop_id, model, dims, blob_len))
    if bad:
        detail = "; ".join(
            f"{sid}: model={m!r} dims={d} blob_bytes={bl} (want {expected_model!r}/{expected_dim}/{expected_dim*4})"
            for sid, m, d, bl in bad[:5]
        )
        return False, len(bad), detail
    return True, 0, f"all {len(rows)} row(s) verified {expected_model}/{expected_dim}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main() -> int:
    parser = argparse.ArgumentParser(description="P4-03 SOP embed-once builder")
    parser.add_argument("--jsonl", help="Path to canonical sops.jsonl")
    parser.add_argument("--db", required=True, help="Target sqlite DB (staged build dir)")
    parser.add_argument("--reindex-all", action="store_true", help="Consider every SOP (still HASH-SKIP unchanged)")
    parser.add_argument("--sop-slug", action="append", default=[], help="Limit to this slug (repeatable)")
    parser.add_argument("--force", action="store_true", help="Re-embed even if content md5 unchanged")
    parser.add_argument("--dry-run", action="store_true", help="Compute what would embed; no API calls, no writes beyond counting")
    parser.add_argument("--verify", action="store_true", help="Verify every row is a real gemini/3072 vector; exit 0 pass, 4 fail")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    ensure_schema(conn)

    if args.verify:
        ok, bad_count, detail = verify_real_vectors(conn, GEMINI_MODEL, GEMINI_OUTPUT_DIM)
        print(f"[embed-sop-library] verify: {detail}")
        conn.close()
        return 0 if ok else 4

    if not args.jsonl:
        print("ERROR: --jsonl is required unless --verify", file=sys.stderr)
        return 2

    sops = load_sops_jsonl(args.jsonl)
    only = set(args.sop_slug) if args.sop_slug else None
    stats = embed_delta(conn, sops, force=args.force, only_slugs=only, dry_run=args.dry_run)
    print(
        f"[embed-sop-library] embedded={stats['embedded']} "
        f"skipped_unchanged={stats['skipped_unchanged']} "
        f"skipped_not_selected={stats['skipped_not_selected']} "
        f"errors={stats['errors']}"
    )
    conn.close()
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(_main())
