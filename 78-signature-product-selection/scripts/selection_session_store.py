"""Durable production session storage for Skill 78 (S78-05 production lane).

Implements the storage hooks of selection_session.SessionStore on SQLite
(Python stdlib only), so the resume / reconfirm / idempotent-confirm
semantics are inherited verbatim and only persistence changes:

- One database file per tenant under the configured base directory
  (<base>/<tenant>/selection-sessions.sqlite3, mode 0600). A ref index at
  <base>/index.sqlite3 maps an opaque ref to its tenant so a lookup never
  scans or opens another tenant's data; the index stores no selection
  content. Tenant isolation is therefore enforced twice: by file scoping
  and by the inherited _lookup tenant/launch check.
- Records carry the same fields as the in-memory core: selection JSON,
  tenant_id, launch_id, created_at, expires_at. Draft references persist
  alongside, so a double confirm across processes or restarts returns the
  same single draft reference.
- Fail closed: any storage read problem (missing file, corrupt database,
  malformed row) makes _get_record / _get_draft return None, which the
  inherited logic surfaces as the helpful 'expired' state, never a
  defaulted package. A write problem raises StorageError: a session that
  cannot be persisted must fail loudly at create time instead of silently
  falling back to memory and vanishing at restart.

No contact identity, card data, or price authority is stored; the stored
selection is the same validated selection.json intent the core accepts.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from selection_session import DEFAULT_TTL_SECONDS, SessionStore

V_SESSION_STORAGE = "S78-SESSION-STORAGE"


class StorageError(Exception):
    """A durable write could not be completed. Carries the house code."""

    def __init__(self, message: str):
        super().__init__(message)
        self.code = V_SESSION_STORAGE
        self.message = message


_SAFE_TENANT = re.compile(r"[^A-Za-z0-9._-]+")


def _tenant_dir_name(tenant_id: str) -> str:
    cleaned = _SAFE_TENANT.sub("_", str(tenant_id)).strip("._") or "tenant"
    if cleaned != str(tenant_id):
        digest = hashlib.sha256(str(tenant_id).encode()).hexdigest()[:12]
        return f"{cleaned}-{digest}"
    return cleaned


_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    ref TEXT PRIMARY KEY,
    selection_json TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    launch_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    ref TEXT PRIMARY KEY,
    draft_ref TEXT NOT NULL
);
"""

_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS ref_index (
    ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL
);
"""


class DurableSessionStore(SessionStore):
    def __init__(self, base_dir: Any, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        super().__init__(ttl_seconds=ttl_seconds)
        self.base = Path(base_dir)

    # -- path helpers ---------------------------------------------------
    def _tenant_db(self, tenant_id: str) -> Path:
        return self.base / _tenant_dir_name(tenant_id) / "selection-sessions.sqlite3"

    def _index_db(self) -> Path:
        return self.base / "index.sqlite3"

    def _connect(self, path: Path, *, create: bool) -> sqlite3.Connection:
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _tenant_for_ref(self, ref: str) -> Optional[str]:
        index = self._index_db()
        if not index.exists():
            return None
        try:
            conn = self._connect(index, create=False)
            try:
                row = conn.execute(
                    "SELECT tenant_id FROM ref_index WHERE ref = ?", (ref,)
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return None
        return row[0] if row else None

    # -- storage hooks --------------------------------------------------
    def _put_record(self, ref: str, rec: Dict[str, Any]) -> None:
        tenant_id = rec["tenant_id"]
        db = self._tenant_db(tenant_id)
        try:
            conn = self._connect(db, create=True)
            try:
                conn.executescript(_SCHEMA)
                conn.execute(
                    "INSERT OR REPLACE INTO records "
                    "(ref, selection_json, tenant_id, launch_id, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        ref,
                        json.dumps(rec["selection"], sort_keys=True),
                        rec["tenant_id"],
                        rec["launch_id"],
                        int(rec["created_at"]),
                        int(rec["expires_at"]),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            os.chmod(db, 0o600)
            conn = self._connect(self._index_db(), create=True)
            try:
                conn.executescript(_INDEX_SCHEMA)
                conn.execute(
                    "INSERT OR REPLACE INTO ref_index (ref, tenant_id) VALUES (?, ?)",
                    (ref, tenant_id),
                )
                conn.commit()
            finally:
                conn.close()
            os.chmod(self._index_db(), 0o600)
        except (sqlite3.Error, OSError) as e:
            raise StorageError(f"durable session record write failed: {e}") from e

    def _get_record(self, ref: str) -> Optional[Dict[str, Any]]:
        tenant_id = self._tenant_for_ref(ref)
        if tenant_id is None:
            return None
        db = self._tenant_db(tenant_id)
        if not db.exists():
            return None
        try:
            conn = self._connect(db, create=False)
            try:
                row = conn.execute(
                    "SELECT selection_json, tenant_id, launch_id, created_at, expires_at "
                    "FROM records WHERE ref = ?",
                    (ref,),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            selection = json.loads(row[0])
        except (ValueError, TypeError):
            return None
        if not isinstance(selection, dict):
            return None
        return {
            "selection": selection,
            "tenant_id": row[1],
            "launch_id": row[2],
            "created_at": row[3],
            "expires_at": row[4],
        }

    def _put_draft(self, ref: str, draft_ref: str) -> None:
        tenant_id = self._tenant_for_ref(ref)
        if tenant_id is None:
            raise StorageError("cannot persist a draft for an unknown session ref")
        db = self._tenant_db(tenant_id)
        try:
            conn = self._connect(db, create=True)
            try:
                conn.executescript(_SCHEMA)
                conn.execute(
                    "INSERT OR IGNORE INTO drafts (ref, draft_ref) VALUES (?, ?)",
                    (ref, draft_ref),
                )
                conn.commit()
            finally:
                conn.close()
        except (sqlite3.Error, OSError) as e:
            raise StorageError(f"durable draft write failed: {e}") from e

    def _get_draft(self, ref: str) -> Optional[str]:
        tenant_id = self._tenant_for_ref(ref)
        if tenant_id is None:
            return None
        db = self._tenant_db(tenant_id)
        if not db.exists():
            return None
        try:
            conn = self._connect(db, create=False)
            try:
                row = conn.execute(
                    "SELECT draft_ref FROM drafts WHERE ref = ?", (ref,)
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return None
        return row[0] if row else None
