"""Explicit adapters — storage, credentials, scoring (PRES-053).

Every external capability the persona runtime touches is an injected
object behind a tiny protocol. The default hermetic implementations touch
only paths handed to them; the global operator stores (Command Center
SQLite, ~/.openclaw, /data/.openclaw) are unreachable by construction.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Storage — scoped per company. Never the global dashboard DB.
# ---------------------------------------------------------------------------
class StorageAdapter:
    """Protocol: persist scoped JSON + append scoped logs + per-company KV."""

    def read_json(self, scope: Dict[str, str], name: str) -> Optional[dict]:
        raise NotImplementedError

    def write_json(self, scope: Dict[str, str], name: str, payload: dict) -> Path:
        raise NotImplementedError

    def append_log(self, scope: Dict[str, str], name: str, line: str) -> bool:
        raise NotImplementedError

    def read_log_tail(self, scope: Dict[str, str], name: str,
                      tail: int = 2000) -> List[str]:
        raise NotImplementedError

    def db_path(self, scope: Dict[str, str]) -> Path:
        """Per-company sqlite path for sticky/variety state (may not exist)."""
        raise NotImplementedError


class FileStorage(StorageAdapter):
    """Rooted file storage. root/<company>/<presentation>/<run>/..."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _scope_dir(self, scope: Dict[str, str]) -> Path:
        d = self.root / _safe(scope.get("company_id", "unknown-company"))
        if scope.get("presentation_id"):
            d = d / _safe(scope["presentation_id"])
        if scope.get("run_id"):
            d = d / _safe(scope["run_id"])
        d.mkdir(parents=True, exist_ok=True)
        return d

    def read_json(self, scope, name):
        p = self._scope_dir(scope) / name
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def write_json(self, scope, name, payload):
        p = self._scope_dir(scope) / name
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, p)
        return p

    def append_log(self, scope, name, line):
        try:
            p = self._scope_dir(scope) / name
            with open(p, "a", encoding="utf-8") as f:
                f.write(line.rstrip("\n") + "\n")
            return True
        except OSError:
            return False

    def read_log_tail(self, scope, name, tail=2000):
        try:
            lines = (self._scope_dir(scope) / name).read_text(
                encoding="utf-8", errors="replace").splitlines()
            return lines[-tail:]
        except OSError:
            return []

    def db_path(self, scope):
        d = self.root / _safe(scope.get("company_id", "unknown-company"))
        d.mkdir(parents=True, exist_ok=True)
        return d / "persona-state.sqlite3"


class NullStorage(StorageAdapter):
    """No-persist adapter (dry-run / pure-memory tests)."""

    def read_json(self, scope, name):
        return None

    def write_json(self, scope, name, payload):
        return Path("/dev/null") / _safe(scope.get("company_id", "x")) / name

    def append_log(self, scope, name, line):
        return True

    def read_log_tail(self, scope, name, tail=2000):
        return []

    def db_path(self, scope):
        return Path("")


def _safe(segment: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in "-_.") else "-"
                      for c in str(segment or "").strip())
    return cleaned.strip("-_.") or "unnamed"


def read_recent_use_counts(db_path: Path, department_id: str,
                           task_category: str, window_hours: int) -> Dict[str, int]:
    """Scoped variety read — mirrors the selector query against OUR db only."""
    if not db_path or str(db_path) in ("", ".") or not Path(db_path).exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute(
            """
            SELECT persona_id, COUNT(*) AS uses
            FROM persona_selection_log
            WHERE department_id = ?
              AND COALESCE(layer_scores, '') LIKE ?
              AND COALESCE(layer_scores, '') LIKE ?
              AND selected_at >= datetime('now', ?)
            GROUP BY persona_id
            """,
            (department_id, "%task_category%",
             f"%{task_category}%", f"-{int(window_hours)} hours"),
        )
        rows = cur.fetchall()
        conn.close()
        return {pid: int(uses) for pid, uses in rows if pid}
    except sqlite3.Error:
        return {}


# ---------------------------------------------------------------------------
# Credentials — explicit named resolution. Never prints values.
# ---------------------------------------------------------------------------
class CredentialResolver:
    """Protocol: resolve a named credential or return '' (absent)."""

    def resolve(self, name: str) -> str:
        raise NotImplementedError

    def presence(self) -> Dict[str, bool]:
        """Presence-only report (lengths never values)."""
        raise NotImplementedError


class EnvCredentialResolver(CredentialResolver):
    """Explicit allow-list over provided mapping (default: process env)."""

    def __init__(self, names: List[str],
                 source: Optional[Dict[str, str]] = None) -> None:
        self._names = list(names)
        self._source = dict(source) if source is not None else dict(os.environ)

    def resolve(self, name: str) -> str:
        if name not in self._names:
            return ""
        return str(self._source.get(name, ""))

    def presence(self) -> Dict[str, bool]:
        return {n: bool(self._source.get(n)) for n in self._names}


class NullCredentialResolver(CredentialResolver):
    """Hermetic tests: no credentials exist, honestly reported."""

    def resolve(self, name: str) -> str:
        return ""

    def presence(self) -> Dict[str, bool]:
        return {}


# ---------------------------------------------------------------------------
# Scoring — explicit method tag. Never claims semantic without evidence.
# ---------------------------------------------------------------------------
HEURISTIC_METHOD = "heuristic-keyword"
SEMANTIC_METHOD = "semantic-embedding"
NEUTRAL_METHOD = "neutral-fallback"
MODULE_MISSING_METHOD = "module-missing"


class ScoringAdapter:
    """Protocol: score one persona against task text, honest method tag."""

    method: str = NEUTRAL_METHOD

    def score(self, persona_id: str, task_text: str,
              persona_summary: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    def rank_ids(self, task_text: str, top_k: int = 10) -> Optional[list]:
        """Optional Stage-C style retrieval. None = unavailable (honest)."""
        return None


class HeuristicScoring(ScoringAdapter):
    """Token-overlap scoring. Reports heuristic-keyword — never semantic."""

    method = HEURISTIC_METHOD

    def score(self, persona_id, task_text, persona_summary=""):
        q = _tokens(task_text)
        p = _tokens(f"{persona_id} {persona_summary}")
        if not q or not p:
            return {"score": 0.0, "method": self.method,
                    "detail": "empty token set"}
        overlap = len(q & p)
        score = round(min(1.0, overlap / max(1, min(len(q), 8)) * 0.9 + 0.1), 4)
        return {"score": score, "method": self.method,
                "detail": f"token overlap {overlap}/{len(q)}"}


class NeutralScoring(ScoringAdapter):
    """Last-resort 0.6 — explicit 'no signal', never masquerading."""

    method = NEUTRAL_METHOD

    def score(self, persona_id, task_text, persona_summary=""):
        return {"score": 0.6, "method": self.method,
                "detail": "no scoring signal available"}


_STOP = frozenset(
    "the a an and or of to in on for with is are was were be been by as at "
    "from that this it its into over under out our you your we they them he "
    "she his her their his her not no yes do does did will would can could "
    "should have has had all any each more most other some such than then "
    "there these those what when where which who whom how why write create "
    "make build slide deck presentation copy".split())


def _tokens(text: str) -> set:
    import re
    if not text:
        return set()
    return {t for t in re.split(r"[^a-z0-9]+", str(text).lower())
            if len(t) >= 3 and t not in _STOP}
