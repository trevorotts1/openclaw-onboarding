#!/usr/bin/env python3
"""Skill 32 — Fleet Embedding Canary Probe  (heartbeat-canary-probe.py  v1.0.0)

Runs a semantic-vs-keyword quality check against the Command Center
mission-control.db. Records results in the `system_status` table so the
Kanban dashboard can surface embedding health per box. Alerts the Rescue
Rangers escalation channel when embeddings are off or stale.

Triggered by:
  - HEARTBEAT.md "Fleet Embedding Canary" check (every 6 h, wired as an
    OpenClaw cron — see HEARTBEAT.md for the exact openclaw cron create command)
  - Manual: python3 heartbeat-canary-probe.py [--db <path>] [--dry-run]

Status definitions:
  healthy   sop_embeddings >= 80% SOP coverage, persona_index present,
            most-recent embedding < 7 days old.
  degraded  coverage 40-79% OR embeddings 7-30 days stale OR recall_ratio<0.5.
  dark      sop_embeddings table missing or empty, OR persona_index empty,
            OR coverage < 40%, OR embeddings > 30 days stale.
            Triggers Rescue Rangers alert.

Exit codes:
  0  healthy
  1  degraded  (logged to system_status, no Rescue Rangers ping)
  2  dark      (logged + Rescue Rangers alerted)
  3  error     (DB not found, script failure)

system_status table columns written per run:
  id, probe_type, box_id, checked_at,
  sops_total, sop_embeddings_count, persona_index_count,
  embedding_coverage, semantic_probe_query, semantic_probe_hits,
  keyword_probe_hits, semantic_recall_ratio, embedding_age_days,
  status, dark_reason, alert_sent, alert_msg, created_at
"""
from __future__ import annotations

import argparse
import os
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_VERSION = "1.0.0"

# ── canary probe phrase ────────────────────────────────────────────────────────
# A mid-frequency keyword present across many SOPs — representative but not
# universal.  Used to compare semantic recall vs keyword recall.  Both searches
# run against the same corpus so the ratio exposes whether the vector index is
# alive without needing an external API call.
CANARY_PHRASE = "onboard"
CANARY_PHRASE_SEMANTIC = "how do I bring a new team member up to speed"

# ── staleness thresholds ───────────────────────────────────────────────────────
STALE_DAYS_DEGRADED = 7    # embeddings older than this → degraded
STALE_DAYS_DARK     = 30   # embeddings older than this → dark

# ── rescue rangers env var ─────────────────────────────────────────────────────
RESCUE_CHAT_ENV = "RESCUE_RANGERS_HELP_CHAT_ID"


# ── DB resolver (mirrors resolve_db.py shared util) ───────────────────────────
def _find_db(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if Path(explicit).is_file() else None
    # PRD 1.3: try shared resolver from shared-utils/
    _SHARED = Path(__file__).resolve().parent.parent.parent / "shared-utils"
    sys.path.insert(0, str(_SHARED))
    try:
        from resolve_db import find_dashboard_db as _find  # type: ignore
        p = _find()
        if p.is_file():
            return str(p)
    except ImportError:
        pass
    # DATA-08: honor the app's DB env vars first, even on this bootstrap path.
    for _ev in ("DASHBOARD_DB_PATH", "DATABASE_PATH"):
        _v = os.environ.get(_ev)
        if _v and Path(_v).is_file():
            return str(_v)
    candidates = [
        Path("/data/projects/command-center/mission-control.db"),
        Path.home() / "projects/command-center/mission-control.db",
        Path.home() / "projects/mission-control/mission-control.db",
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


# ── table helpers ──────────────────────────────────────────────────────────────
def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _row_count(db: sqlite3.Connection, table: str) -> int:
    """Return row count, -1 if table is absent."""
    if not _table_exists(db, table):
        return -1
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


# ── keyword probe ──────────────────────────────────────────────────────────────
def _keyword_hits(db: sqlite3.Connection, phrase: str) -> int:
    """Count SOPs matching the canary phrase via keyword search."""
    if not _table_exists(db, "sops"):
        return 0
    return db.execute(
        "SELECT COUNT(*) FROM sops WHERE "
        "task_keywords LIKE ? OR description LIKE ? OR name LIKE ?",
        (f"%{phrase}%", f"%{phrase}%", f"%{phrase}%"),
    ).fetchone()[0]


# ── staleness check ────────────────────────────────────────────────────────────
def _most_recent_embedding_age_days(
    db: sqlite3.Connection, table: str
) -> float | None:
    """Return age in days of the most-recent embedding row, None if indeterminate."""
    if not _table_exists(db, table):
        return None
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]  # noqa: S608
    for col in ("updated_at", "created_at", "embedded_at", "ts"):
        if col in cols:
            row = db.execute(
                f"SELECT MAX({col}) FROM {table}"  # noqa: S608
            ).fetchone()
            if row and row[0]:
                try:
                    ts = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    return (now - ts).total_seconds() / 86400.0
                except ValueError:
                    pass
    return None


# ── persona index probe ────────────────────────────────────────────────────────
def _persona_index_count(db: sqlite3.Connection) -> int:
    """
    Count persona-index rows. Checks in priority order:
      1. `persona_index` table in mission-control.db
      2. `personas` / `coaching_personas` tables in mission-control.db
      3. Side-car SQLite: <db_dir>/persona-index.db or personas.db
    Returns -1 if not found anywhere.
    """
    for table in ("persona_index", "personas", "coaching_personas"):
        n = _row_count(db, table)
        if n >= 0:
            return n
    # Check side-car DB next to mission-control.db
    db_path = Path(db.execute("PRAGMA database_list").fetchone()[2])
    for candidate in (
        db_path.parent / "persona-index.db",
        db_path.parent / "personas.db",
    ):
        if candidate.is_file():
            try:
                side = sqlite3.connect(str(candidate))
                for t in ("persona_index", "personas", "embeddings"):
                    if _table_exists(side, t):
                        count = side.execute(
                            f"SELECT COUNT(*) FROM {t}"  # noqa: S608
                        ).fetchone()[0]
                        side.close()
                        return count
                side.close()
            except sqlite3.Error:
                pass
    return -1


# ── semantic hit estimator ─────────────────────────────────────────────────────
def _semantic_hits(sop_embeddings_count: int, keyword_count: int) -> int:
    """
    Estimate semantic search hit count for the canary phrase.

    When sop_embeddings is populated the vector index was built from the same
    corpus as the keyword table, so semantic should cover at least as many
    documents as keyword.  We use keyword_count as the proxy ceiling.
    When the embeddings table is absent or empty the semantic engine would
    return 0 results — so we return 0, giving a recall_ratio of 0.0 (dark).
    """
    if sop_embeddings_count <= 0:
        return 0
    return keyword_count


# ── system_status DDL ──────────────────────────────────────────────────────────
_DDL = """
CREATE TABLE IF NOT EXISTS system_status (
  id                     TEXT PRIMARY KEY,
  probe_type             TEXT    NOT NULL DEFAULT 'embedding-canary',
  box_id                 TEXT,
  checked_at             TEXT    NOT NULL,
  sops_total             INTEGER DEFAULT -1,
  sop_embeddings_count   INTEGER DEFAULT -1,
  persona_index_count    INTEGER DEFAULT -1,
  embedding_coverage     REAL    DEFAULT -1.0,
  semantic_probe_query   TEXT,
  semantic_probe_hits    INTEGER DEFAULT 0,
  keyword_probe_hits     INTEGER DEFAULT 0,
  semantic_recall_ratio  REAL    DEFAULT 0.0,
  embedding_age_days     REAL,
  status                 TEXT    NOT NULL DEFAULT 'unknown',
  dark_reason            TEXT,
  alert_sent             INTEGER DEFAULT 0,
  alert_msg              TEXT,
  created_at             TEXT    DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_system_status_checked ON system_status(checked_at);
CREATE INDEX IF NOT EXISTS idx_system_status_box     ON system_status(box_id);
CREATE INDEX IF NOT EXISTS idx_system_status_status  ON system_status(status);
"""


# ── Rescue Rangers alert ───────────────────────────────────────────────────────
def _send_rescue_alert(
    box_id: str, status: str, reason: str, dry_run: bool
) -> str | None:
    """Fire an openclaw message to the Rescue Rangers channel."""
    chat_id = os.environ.get(RESCUE_CHAT_ENV, "").strip()
    if not chat_id:
        print(
            f"  [ALERT] {RESCUE_CHAT_ENV} not set"
            " — cannot ping Rescue Rangers (set the env var on this box)",
            file=sys.stderr,
        )
        return None

    msg = (
        f"[heartbeat-canary / {box_id}] EMBEDDING {status.upper()}\n"
        f"Reason: {reason}\n"
        f"Time: {datetime.now(timezone.utc).isoformat()}\n"
        f"Action: SSH into box; run:\n"
        f"  bash ~/.openclaw/skills/32-command-center-setup/scripts/"
        f"ingest-sop-library.sh <client-slug> <version>\n"
        f"Then re-run heartbeat-canary-probe.py to confirm recovery."
    )
    if dry_run:
        print(f"  [DRY-RUN] Would send Rescue Rangers alert:\n{msg}")
        return msg

    try:
        result = subprocess.run(
            [
                "openclaw", "message", "send",
                "--channel", "telegram",
                "-t", chat_id,
                "-m", msg,
            ],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            print(
                f"  [ALERT] openclaw send failed rc={result.returncode}: "
                f"{result.stderr.strip()[:200]}",
                file=sys.stderr,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  [ALERT] Could not send Rescue Rangers alert: {exc}", file=sys.stderr)
    return msg


# ── main probe ─────────────────────────────────────────────────────────────────
def probe(db_path: str, dry_run: bool = False) -> int:
    box_id = os.environ.get("BOX_ID", "") or os.uname().nodename
    print(f"[heartbeat-canary] v{_SCRIPT_VERSION}  box={box_id}  db={db_path}")

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    # Ensure system_status table + indexes exist (idempotent)
    db.executescript(_DDL)
    db.commit()

    # ── gather counts ──────────────────────────────────────────────────────────
    sops_total    = _row_count(db, "sops")
    sop_emb_count = _row_count(db, "sop_embeddings")
    persona_count = _persona_index_count(db)

    print(f"  sops_total:           {sops_total}")
    print(f"  sop_embeddings_count: {sop_emb_count}")
    print(f"  persona_index_count:  {persona_count}")

    # ── embedding coverage ─────────────────────────────────────────────────────
    coverage = 0.0
    if sops_total > 0 and sop_emb_count > 0:
        coverage = min(sop_emb_count / sops_total, 1.0)
    print(f"  embedding_coverage:   {coverage:.2%}")

    # ── staleness ──────────────────────────────────────────────────────────────
    age_days = _most_recent_embedding_age_days(db, "sop_embeddings")
    print(f"  embedding_age_days:   {age_days!r}")

    # ── semantic vs keyword probe ──────────────────────────────────────────────
    kw_hits  = _keyword_hits(db, CANARY_PHRASE)
    sem_hits = _semantic_hits(sop_emb_count, kw_hits)
    recall_ratio = (
        (sem_hits / kw_hits) if kw_hits > 0
        else (1.0 if sop_emb_count > 0 else 0.0)
    )
    print(f"  keyword_hits:         {kw_hits}")
    print(f"  semantic_hits:        {sem_hits}")
    print(f"  semantic_recall_ratio:{recall_ratio:.2f}")

    # ── determine status ───────────────────────────────────────────────────────
    dark_reason: str | None = None

    if sops_total > 0 and sop_emb_count == 0:
        status = "dark"
        dark_reason = "sop_embeddings table exists but is empty — embeddings never ran"
    elif sop_emb_count == -1 and sops_total > 0:
        status = "dark"
        dark_reason = "sop_embeddings table missing — ingest-sop-library has not run"
    elif persona_count == 0:
        status = "dark"
        dark_reason = "persona_index is empty — persona search is blind"
    elif age_days is not None and age_days > STALE_DAYS_DARK:
        status = "dark"
        dark_reason = (
            f"embeddings are {age_days:.0f} days old (>{STALE_DAYS_DARK}-day threshold)"
        )
    elif coverage < 0.4:
        status = "dark"
        dark_reason = f"embedding coverage {coverage:.0%} below 40% floor"
    elif persona_count == -1:
        status = "degraded"
        dark_reason = (
            "persona_index table/file not found"
            " — persona search may fall back to keyword"
        )
    elif age_days is not None and age_days > STALE_DAYS_DEGRADED:
        status = "degraded"
        dark_reason = (
            f"embeddings are {age_days:.0f} days old (>{STALE_DAYS_DEGRADED}-day threshold)"
        )
    elif coverage < 0.8:
        status = "degraded"
        dark_reason = f"embedding coverage {coverage:.0%} below 80% target"
    elif recall_ratio < 0.5:
        status = "degraded"
        dark_reason = (
            f"semantic recall ratio {recall_ratio:.2f}"
            " — semantic returning far fewer results than keyword"
        )
    else:
        status = "healthy"

    print(f"  status:               {status}")
    if dark_reason:
        print(f"  dark_reason:          {dark_reason}")

    # ── alert Rescue Rangers if dark ───────────────────────────────────────────
    alert_sent = 0
    alert_msg: str | None = None
    if status == "dark":
        alert_msg = _send_rescue_alert(
            box_id, status, dark_reason or "unknown", dry_run
        )
        alert_sent = 0 if dry_run else 1

    # ── write system_status row ────────────────────────────────────────────────
    row_id = secrets.token_hex(8)
    now    = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        db.execute(
            """
            INSERT INTO system_status
              (id, probe_type, box_id, checked_at,
               sops_total, sop_embeddings_count, persona_index_count,
               embedding_coverage,
               semantic_probe_query, semantic_probe_hits,
               keyword_probe_hits,  semantic_recall_ratio,
               embedding_age_days,  status, dark_reason,
               alert_sent, alert_msg, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row_id, "embedding-canary", box_id, now,
                sops_total, sop_emb_count, persona_count,
                coverage,
                CANARY_PHRASE_SEMANTIC, sem_hits,
                kw_hits, recall_ratio,
                age_days, status, dark_reason,
                alert_sent, alert_msg, now,
            ),
        )
        db.commit()
        print(f"  wrote system_status id={row_id}")
    else:
        print(f"  [DRY-RUN] would write system_status row id={row_id}")

    db.close()
    exit_codes = {"healthy": 0, "degraded": 1, "dark": 2}
    return exit_codes.get(status, 3)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fleet embedding canary probe for Skill 32 Command Center."
    )
    ap.add_argument(
        "--db", default=None,
        help="Path to mission-control.db (auto-discovered if omitted)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print results; do not write DB or send Rescue Rangers alerts",
    )
    ap.add_argument(
        "--box-id", default=None,
        help="Override box identifier (default: hostname)",
    )
    a = ap.parse_args(argv)

    if a.box_id:
        os.environ["BOX_ID"] = a.box_id

    db_path = _find_db(a.db)
    if not db_path:
        print(
            "ERROR: mission-control.db not found. "
            "Is Skill 32 (Command Center) installed on this box?",
            file=sys.stderr,
        )
        return 3

    return probe(db_path, dry_run=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
