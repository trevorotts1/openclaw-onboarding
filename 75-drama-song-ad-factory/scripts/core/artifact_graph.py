"""Artifact registry + dependency invalidation. Directive 21, 22, 24.4. Stdlib only.

Hashes files, pins dependency versions, invalidates only real dependents.
Rejects missing/truncated files and paths outside approved storage.
Sets STALE only on artifact records, never on stage state.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
_CHUNK = 65536


class GraphError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _norm(path, roots):
    """Normalized absolute path, or raise OUT_OF_STORAGE."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    parts = []
    for part in p.parts:
        if part in (".", ""):
            continue
        if part == "..":
            if parts and parts[-1] != "/":
                parts.pop()
            continue
        parts.append(part)
    norm = Path(*parts) if parts else Path("/")
    try:
        norm = norm.resolve()
    except OSError:
        pass
    for r in roots:
        rp = Path(r).resolve() if Path(r).exists() else Path(r).absolute()
        rp = rp.resolve() if hasattr(rp, "resolve") else rp
        try:
            norm.relative_to(rp)
            return str(norm)
        except ValueError:
            continue
    raise GraphError("OUT_OF_STORAGE", "%s outside approved roots" % path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


class Graph:
    def __init__(self, db_path, approved_roots):
        self.roots = [str(r) for r in approved_roots]
        self.con = sqlite3.connect(db_path)
        self.con.executescript(
            "CREATE TABLE IF NOT EXISTS artifacts(run_id TEXT, artifact_id TEXT,"
            " version INTEGER, kind TEXT, stage TEXT, path TEXT, sha256 TEXT,"
            " size INTEGER, stale INTEGER, supersedes TEXT, updated_at REAL,"
            " PRIMARY KEY(run_id, artifact_id));"
            "CREATE TABLE IF NOT EXISTS deps(run_id TEXT, artifact_id TEXT,"
            " depends_on TEXT, pinned_version INTEGER,"
            " PRIMARY KEY(run_id, artifact_id, depends_on));")
        self.con.commit()

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def register(self, run_id, artifact_id, kind, stage, path,
                 supersedes=None, expected_size=None):
        """Hash + store. Rejects missing, empty/truncated, out-of-storage."""
        norm = _norm(path, self.roots)
        if not Path(norm).exists():
            raise GraphError("MISSING_ARTIFACT", norm)
        size = Path(norm).stat().st_size
        if size == 0:
            raise GraphError("TRUNCATED_ARTIFACT", "%s empty" % norm)
        if expected_size is not None and size != expected_size:
            raise GraphError("TRUNCATED_ARTIFACT",
                             "size %d != %d" % (size, expected_size))
        digest = sha256_file(norm)
        row = self.con.execute(
            "SELECT version FROM artifacts WHERE run_id=? AND artifact_id=?",
            (run_id, artifact_id)).fetchone()
        version = (row[0] + 1) if row else 1
        self.con.execute(
            "INSERT OR REPLACE INTO artifacts(run_id, artifact_id, version,"
            " kind, stage, path, sha256, size, stale, supersedes, updated_at)"
            " VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (run_id, artifact_id, version, kind, stage, norm,
             digest, size, supersedes, time.time()))
        self.con.commit()
        return {"artifact_id": artifact_id, "version": version,
                "sha256": digest, "size": size}

    def get(self, run_id, artifact_id):
        r = self.con.execute(
            "SELECT version, kind, stage, path, sha256, size, stale, supersedes"
            " FROM artifacts WHERE run_id=? AND artifact_id=?",
            (run_id, artifact_id)).fetchone()
        if r is None:
            raise GraphError("NOT_FOUND", artifact_id)
        return {"artifact_id": artifact_id, "version": r[0], "kind": r[1],
                "stage": r[2], "path": r[3], "sha256": r[4], "size": r[5],
                "stale": bool(r[6]), "supersedes": r[7]}

    def verify(self, run_id, artifact_id):
        """Re-hash on disk; raise on missing/truncated/changed."""
        rec = self.get(run_id, artifact_id)
        p = Path(rec["path"])
        if not p.exists():
            raise GraphError("MISSING_ARTIFACT", rec["path"])
        if p.stat().st_size != rec["size"]:
            raise GraphError("TRUNCATED_ARTIFACT",
                             "%s size changed" % rec["path"])
        if sha256_file(rec["path"]) != rec["sha256"]:
            raise GraphError("HASH_MISMATCH", artifact_id)
        return rec

    def depend(self, run_id, artifact_id, depends_on):
        """Pin current version of depends_on. Rejects cycles."""
        for aid in (artifact_id, depends_on):
            if self.con.execute(
                    "SELECT 1 FROM artifacts WHERE run_id=? AND artifact_id=?",
                    (run_id, aid)).fetchone() is None:
                raise GraphError("NOT_FOUND", aid)
        if artifact_id == depends_on:
            raise GraphError("CYCLE", "self-dependency")
        # cycle check: depends_on must not already reach artifact_id
        seen, stack = set(), [depends_on]
        while stack:
            cur = stack.pop()
            if cur == artifact_id:
                raise GraphError("CYCLE", "%s -> %s" % (artifact_id,
                                                        depends_on))
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(r[0] for r in self.con.execute(
                "SELECT depends_on FROM deps WHERE run_id=? AND artifact_id=?",
                (run_id, cur)))
        pinned = self.get(run_id, depends_on)["version"]
        self.con.execute(
            "INSERT OR REPLACE INTO deps(run_id, artifact_id, depends_on,"
            " pinned_version) VALUES(?, ?, ?, ?)",
            (run_id, artifact_id, depends_on, pinned))
        self.con.commit()

    def dependencies(self, run_id, artifact_id):
        """Pinned deps with drift flags for pre-stage guards."""
        out = []
        for (dep, pin) in self.con.execute(
                "SELECT depends_on, pinned_version FROM deps"
                " WHERE run_id=? AND artifact_id=?", (run_id, artifact_id)):
            cur = self.get(run_id, dep)["version"]
            out.append({"depends_on": dep, "pinned_version": pin,
                        "current_version": cur, "drift": pin != cur})
        return out

    def invalidate_upstream_change(self, run_id, artifact_id, reason):
        """Mark artifact + all transitive dependents STALE, nothing else."""
        if not reason:
            raise GraphError("MISSING_REASON", "stale needs reason")
        self.get(run_id, artifact_id)  # NOT_FOUND if unknown
        affected, queue, seen = [], [artifact_id], set()
        while queue:
            cur = queue.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            rec = self.get(run_id, cur)
            if not rec["stale"] or cur == artifact_id:
                self.con.execute(
                    "UPDATE artifacts SET stale=1 WHERE run_id=? AND artifact_id=?",
                    (run_id, cur))
                affected.append(cur)
            queue.extend(r[0] for r in self.con.execute(
                "SELECT artifact_id FROM deps WHERE run_id=? AND depends_on=?",
                (run_id, cur)))
        self.con.commit()
        return affected

    invalidate = invalidate_upstream_change  # DTS-202 check.py compat

    def non_dependents(self, run_id, artifact_id):
        """IDs unaffected by invalidating artifact_id (for tests/guards)."""
        self.get(run_id, artifact_id)
        all_ids = [r[0] for r in self.con.execute(
            "SELECT artifact_id FROM artifacts WHERE run_id=?", (run_id,))]
        # walk dependents without writing
        dep_set, queue = set(), [artifact_id]
        while queue:
            cur = queue.pop(0)
            if cur in dep_set:
                continue
            dep_set.add(cur)
            queue.extend(r[0] for r in self.con.execute(
                "SELECT artifact_id FROM deps WHERE run_id=? AND depends_on=?",
                (run_id, cur)))
        return sorted(set(all_ids) - dep_set)
