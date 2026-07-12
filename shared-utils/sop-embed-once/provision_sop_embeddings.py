#!/usr/bin/env python3
"""
shared-utils/sop-embed-once/provision_sop_embeddings.py
─────────────────────────────────────────────────────────────────────────────
P4-03 step 2 — wires the shipped SOP-embeddings asset into a client's
mission-control.db, mirroring shared-utils/provision-persona-index.sh's
idempotency gate for the persona index (System 1). Called from
32-command-center-setup/scripts/ingest-sop-library.sh AFTER the SOP content
ingester has run (so `sops` rows exist to join against).

CONTRACT (mirrors the persona pipeline):
  - sha256 is a HARD GATE — a corrupt asset is NEVER imported.
  - Idempotent: a box already at/above the manifest's sop_count for the exact
    release_tag skips the download entirely (SKIP, no network I/O).
  - Import is additive/scoped: only rows whose sop_id exists in the box's own
    `sops` table are inserted (never orphans a FK, never touches a client's
    OWN embedded rows for SOPs outside the shared library — e.g. custom SOPs
    from sop_proposals, which are backfill-sop-embeddings.ts's job per step 3).
  - Zero client-key embed calls — this is a straight sqlite ATTACH + INSERT,
    no embedding API call of any kind.
  - Marker table `sop_embeddings_shipped_asset` records what was imported so
    the CC app (backfill-sop-embeddings.ts) can detect "the shared library is
    already covered" and refuse a wasteful full re-embed (step 3).

PROVISION_DRY_RUN=1 (env) prints the gate decision and returns BEFORE any
network I/O — mirrors provision-persona-index.sh's PROVISION_DRY_RUN gate,
used by tests/unit/provision-sop-embeddings-idempotency.test.sh.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

MARKER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sop_embeddings_shipped_asset (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    release_tag  TEXT NOT NULL,
    sop_count    INTEGER NOT NULL,
    sha256       TEXT NOT NULL,
    imported_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_manifest(manifest_path: str) -> Optional[dict]:
    try:
        with open(manifest_path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _current_marker(db_path: str) -> Optional[dict]:
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute(MARKER_TABLE_SQL)
        row = conn.execute(
            "SELECT release_tag, sop_count, sha256, imported_at FROM sop_embeddings_shipped_asset WHERE id=1"
        ).fetchone()
        conn.commit()
        conn.close()
        if row is None:
            return None
        return {"release_tag": row[0], "sop_count": row[1], "sha256": row[2], "imported_at": row[3]}
    except sqlite3.Error:
        return None


def provision_sop_embeddings(manifest_path: str, db_path: str, dry_run: Optional[bool] = None) -> dict:
    """Idempotently import the shipped sop_embeddings asset into db_path.

    Returns a status dict: {"status": "SKIP"|"IMPORTED"|"DRY-RUN"|"WARN", "reason": str, ...}
    NEVER raises — every failure path degrades to a WARN status (additive,
    never blocks install/update), matching the persona pipeline's
    _pidx_skip_warn contract.
    """
    if dry_run is None:
        dry_run = os.environ.get("PROVISION_DRY_RUN", "0") == "1"

    manifest = _read_manifest(manifest_path)
    if manifest is None:
        return {"status": "WARN", "reason": f"manifest not found/unreadable: {manifest_path}"}

    if manifest.get("asset_rebuild_required") is True:
        return {
            "status": "WARN",
            "reason": "asset_rebuild_required:true — no SOP-embeddings asset has been published yet "
                      "(operator must run shared-utils/sop-embed-once/build-and-publish.sh); "
                      "skipping provisioning (additive, no-op)",
        }

    release_tag = manifest.get("release_tag")
    asset_url = manifest.get("asset_url")
    sha256_expected = manifest.get("sha256")
    sop_count = manifest.get("sop_count") or 0
    model = manifest.get("model")
    dims = manifest.get("dims")

    if not release_tag or not asset_url or not sha256_expected:
        return {"status": "WARN", "reason": "manifest missing release_tag/asset_url/sha256 — skipping (additive)"}
    if not sop_count or sop_count <= 0:
        return {"status": "WARN", "reason": "manifest sop_count missing/zero — skipping (additive; no trustworthy count)"}

    if not os.path.isfile(db_path):
        return {"status": "WARN", "reason": f"target DB not found: {db_path} — install/ingest the SOP library first"}

    # ── Idempotency gate ──────────────────────────────────────────────────────
    marker = _current_marker(db_path)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        installed_rows = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sop_embeddings'"
        ).fetchone()[0]
        installed_count = 0
        if installed_rows:
            installed_count = conn.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0]
        conn.close()
    except sqlite3.Error as exc:
        return {"status": "WARN", "reason": f"could not read target DB: {exc}"}

    if marker and marker["release_tag"] == release_tag and installed_count >= sop_count:
        return {
            "status": "SKIP",
            "reason": f"already canonical (release={release_tag}, {installed_count} rows >= manifest {sop_count})",
        }

    if dry_run:
        return {
            "status": "DRY-RUN",
            "reason": f"would import release={release_tag} (manifest sop_count={sop_count}) from {asset_url}",
        }

    # ── Download + verify + import ────────────────────────────────────────────
    tmp_dir = tempfile.mkdtemp(prefix="sop-embed-provision-")
    try:
        gz_path = os.path.join(tmp_dir, "sop-embeddings.sqlite.gz")
        try:
            urllib.request.urlretrieve(asset_url, gz_path)  # noqa: S310 — canonical GH release asset
        except Exception as exc:  # noqa: BLE001
            return {"status": "WARN", "reason": f"download failed ({asset_url}): {exc}"}

        actual_sha = _sha256_file(gz_path)
        if actual_sha != sha256_expected:
            return {
                "status": "WARN",
                "reason": f"sha256 MISMATCH (expected {sha256_expected}, got {actual_sha}) — "
                          "NOT importing a corrupt asset",
            }

        shipped_db = os.path.join(tmp_dir, "shipped.sqlite")
        with gzip.open(gz_path, "rb") as src, open(shipped_db, "wb") as dst:
            shutil.copyfileobj(src, dst)

        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute(MARKER_TABLE_SQL)
        conn.execute(f"ATTACH DATABASE '{shipped_db}' AS shipped")
        # Model/dims agreement guard — refuse to mix vector spaces (standing
        # guard, P4-03 step 8). Only import rows matching the manifest's
        # declared model/dims contract.
        cur = conn.execute(
            "SELECT COUNT(*) FROM shipped.sop_embeddings WHERE embedding_model != ? OR embedding_dims != ?",
            (model, dims),
        )
        mismatched = cur.fetchone()[0]
        if mismatched:
            conn.commit()  # close out the implicit read transaction before DETACH
            conn.execute("DETACH DATABASE shipped")
            conn.close()
            return {
                "status": "WARN",
                "reason": f"shipped asset has {mismatched} row(s) not matching manifest model/dims "
                          f"({model}/{dims}) — REFUSING import (never mix vector spaces)",
            }

        conn.execute(
            """INSERT OR REPLACE INTO main.sop_embeddings
                   (sop_id, embedding, embedding_model, embedding_dims, embedded_at)
               SELECT sop_id, embedding, embedding_model, embedding_dims, embedded_at
               FROM shipped.sop_embeddings
               WHERE sop_id IN (SELECT id FROM main.sops)"""
        )
        imported = conn.total_changes
        conn.commit()  # DETACH requires no pending transaction on the attached db
        conn.execute("DETACH DATABASE shipped")
        conn.execute("DELETE FROM sop_embeddings_shipped_asset WHERE id=1")
        conn.execute(
            "INSERT INTO sop_embeddings_shipped_asset (id, release_tag, sop_count, sha256, imported_at) "
            "VALUES (1, ?, ?, ?, datetime('now'))",
            (release_tag, sop_count, sha256_expected),
        )
        conn.commit()
        conn.close()

        return {
            "status": "IMPORTED",
            "reason": f"imported shared-library sop_embeddings (release={release_tag}, "
                      f"{sop_count} manifest rows, sha256 verified, 0 embedding API calls)",
            "imported_rows": imported,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="P4-03 step 2 — provision the shipped SOP-embeddings asset")
    parser.add_argument("manifest", help="Path to SOP-EMBEDDINGS-MANIFEST.json")
    parser.add_argument("db", help="Path to the target mission-control.db")
    args = parser.parse_args()

    result = provision_sop_embeddings(args.manifest, args.db)
    print(f"[provision-sop-embeddings] {result['status']}: {result['reason']}")
    return 0  # additive/never-block, matches _pidx_skip_warn contract


if __name__ == "__main__":
    sys.exit(_main())
