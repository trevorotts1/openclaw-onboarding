#!/usr/bin/env python3
"""move-task.py — the ONLY sanctioned way to change a Kanban task's status.

Enforces the Skill 32 Kanban Done-Gate (see CORE_UPDATES.md): a card cannot move
from **Review** to **Complete** unless the department's Devil's Advocate has
recorded a PASSING sign-off for that task. Until now the Done-Gate was PROSE in
AGENTS.md with no enforcement — agents hand-wrote SQL UPDATEs to tasks.status and
the Review→Complete gate was unenforceable in code. This tool makes it real.

Doctrine (CORE_UPDATES.md v9.6.5+):
  Backlog → Ready → In Progress → REVIEW → (Devil's Advocate validates) → Complete
  - A worker NEVER moves a card straight from In Progress to Complete.
  - A worker NEVER marks a card Complete on its own behalf — only a DA sign-off
    unlocks Complete.

Subcommands:
  move    --task <id> --to <status> [--by <agent_id>] [--note "..."]
            Transition tasks.status. Refuses → Complete unless the card is in
            Review AND a Devil's Advocate sign-off with verdict=pass exists.
  signoff --task <id> [--role devils-advocate] [--by <agent_id>]
          [--verdict pass|fail|indeterminate] [--note "..."]
            Record a sign-off for a task (idempotent upsert on task_id+role).
  status  --task <id>
            Print the task's current status + whether a passing DA sign-off exists.

DB resolution: shared-utils/resolve_db.find_dashboard_db() (Mac
~/projects/command-center first, then VPS /data/projects/command-center). Pass
--db to override. Schema-tolerant + idempotent: safe to re-run.

Exit codes:
  0  transition applied / sign-off recorded / status printed
  2  transition BLOCKED by the Done-Gate (Review→Complete without a DA sign-off,
     or an attempt to jump to Complete without passing through Review)
  1  error (task not found, DB missing, bad args)
"""
from __future__ import annotations

import argparse
import re
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# PRD 1.3: resolve the DB via the single shared resolver.
_SHARED_UTILS = Path(__file__).resolve().parent.parent.parent / "shared-utils"
sys.path.insert(0, str(_SHARED_UTILS))
try:
    from resolve_db import find_dashboard_db as _shared_find_dashboard_db, is_db_found  # type: ignore
    _HAS_SHARED_RESOLVER = True
except ImportError:
    _HAS_SHARED_RESOLVER = False

DA_ROLE = "devils-advocate"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_db(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).is_file() else None
    if _HAS_SHARED_RESOLVER:
        p = _shared_find_dashboard_db()
        if is_db_found(p):
            return str(p)
    for cand in (
        Path.home() / "projects/command-center/mission-control.db",
        Path.home() / "projects/mission-control/mission-control.db",
        Path("/opt/mission-control/mission-control.db"),
        Path("/app/mission-control.db"),
        Path("/data/projects/command-center/mission-control.db"),
    ):
        if cand.is_file():
            return str(cand)
    return None


def _canon(status: str) -> str:
    """Normalize a status token for GATE LOGIC only (board may store 'backlog',
    'in_progress', 'In Progress', etc.). The verbatim --to value is what gets
    written; this canonical form is used solely to decide the gate."""
    s = re.sub(r"[^a-z0-9]+", "", (status or "").lower())
    aliases = {
        "done": "complete",
        "completed": "complete",
        "finished": "complete",
        "inprogress": "inprogress",
        "doing": "inprogress",
        "wip": "inprogress",
        "reviewing": "review",
        "qa": "review",
    }
    return aliases.get(s, s)


def _ensure_tables(db: sqlite3.Connection) -> None:
    """Create the audit + sign-off tables this tool owns (idempotent)."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_signoffs (
          id          TEXT PRIMARY KEY,
          task_id     TEXT NOT NULL,
          role_type   TEXT NOT NULL,
          agent_id    TEXT,
          verdict     TEXT,
          note        TEXT,
          created_at  TEXT DEFAULT (datetime('now')),
          updated_at  TEXT,
          UNIQUE(task_id, role_type)
        );
        CREATE INDEX IF NOT EXISTS idx_task_signoffs_task ON task_signoffs(task_id);

        CREATE TABLE IF NOT EXISTS task_status_audit (
          id          TEXT PRIMARY KEY,
          task_id     TEXT NOT NULL,
          from_status TEXT,
          to_status   TEXT,
          actor       TEXT,
          gate        TEXT,
          note        TEXT,
          created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_task_status_audit_task ON task_status_audit(task_id);
        """
    )


def _task_cols(db: sqlite3.Connection) -> list:
    return [r[1] for r in db.execute("PRAGMA table_info(tasks)")]


def _get_task(db: sqlite3.Connection, task_id: str):
    cols = _task_cols(db)
    if "id" not in cols or "status" not in cols:
        return None, cols
    row = db.execute("SELECT id, status FROM tasks WHERE id = ? LIMIT 1", (task_id,)).fetchone()
    return row, cols


def _has_passing_da_signoff(db: sqlite3.Connection, task_id: str) -> bool:
    row = db.execute(
        "SELECT verdict FROM task_signoffs WHERE task_id = ? AND role_type = ? LIMIT 1",
        (task_id, DA_ROLE),
    ).fetchone()
    if not row:
        return False
    return _canon(row[0] or "") in ("pass", "passed", "approve", "approved", "ok")


def _audit(db, task_id, frm, to, actor, gate, note):
    db.execute(
        "INSERT INTO task_status_audit (id, task_id, from_status, to_status, actor, gate, note, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (secrets.token_hex(8), task_id, frm, to, actor or "", gate, note or "", _now_iso()),
    )


def cmd_move(db, args) -> int:
    _ensure_tables(db)
    row, cols = _get_task(db, args.task)
    if row is None:
        print(f"[move-task] ERROR: task id {args.task!r} not found (or tasks table missing id/status)", file=sys.stderr)
        return 1
    cur = row[1] or ""
    cur_c = _canon(cur)
    to_c = _canon(args.to)

    # Idempotent: already at the target status — no-op, never re-checks the gate.
    if cur_c == to_c:
        print(f"[move-task] no-op: task {args.task} already at status {cur!r}")
        return 0

    # ---- Done-Gate enforcement: any transition INTO Complete ----
    if to_c == "complete":
        if cur_c != "review":
            print(
                f"[move-task] BLOCKED (Done-Gate): task {args.task} is {cur!r}; a card must pass "
                f"through Review before Complete. Move it to Review first.",
                file=sys.stderr,
            )
            _audit(db, args.task, cur, args.to, args.by, "blocked-not-review", args.note)
            db.commit()
            return 2
        if not _has_passing_da_signoff(db, args.task):
            print(
                f"[move-task] BLOCKED (Done-Gate): Review→Complete on task {args.task} requires a "
                f"Devil's Advocate sign-off (verdict=pass). None found. The dept DA must run:\n"
                f"  python3 move-task.py signoff --task {args.task} --verdict pass --by <da-agent-id>",
                file=sys.stderr,
            )
            _audit(db, args.task, cur, args.to, args.by, "blocked-no-da-signoff", args.note)
            db.commit()
            return 2

    # ---- Apply the transition (schema-tolerant) ----
    if "updated_at" in cols:
        db.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (args.to, _now_iso(), args.task))
    else:
        db.execute("UPDATE tasks SET status = ? WHERE id = ?", (args.to, args.task))
    gate = "review-to-complete-passed" if to_c == "complete" else "transition"
    _audit(db, args.task, cur, args.to, args.by, gate, args.note)
    db.commit()
    print(f"[move-task] OK: task {args.task} {cur!r} -> {args.to!r}")
    return 0


def cmd_signoff(db, args) -> int:
    _ensure_tables(db)
    row, _ = _get_task(db, args.task)
    if row is None:
        print(f"[move-task] ERROR: task id {args.task!r} not found", file=sys.stderr)
        return 1
    role = args.role or DA_ROLE
    now = _now_iso()
    # Idempotent upsert on (task_id, role_type) without requiring SQLite 3.24 UPSERT.
    db.execute(
        "INSERT OR IGNORE INTO task_signoffs (id, task_id, role_type, agent_id, verdict, note, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (secrets.token_hex(8), args.task, role, args.by or "", args.verdict, args.note or "", now, now),
    )
    db.execute(
        "UPDATE task_signoffs SET agent_id = ?, verdict = ?, note = ?, updated_at = ? "
        "WHERE task_id = ? AND role_type = ?",
        (args.by or "", args.verdict, args.note or "", now, args.task, role),
    )
    db.commit()
    print(f"[move-task] sign-off recorded: task {args.task} role={role} verdict={args.verdict!r}")
    return 0


def cmd_status(db, args) -> int:
    _ensure_tables(db)
    row, _ = _get_task(db, args.task)
    if row is None:
        print(f"[move-task] ERROR: task id {args.task!r} not found", file=sys.stderr)
        return 1
    has = _has_passing_da_signoff(db, args.task)
    print(f"task:    {args.task}")
    print(f"status:  {row[1]!r}")
    print(f"da_pass: {has}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Sanctioned Kanban task-status transitions with Done-Gate enforcement.")
    ap.add_argument("--db", default=None, help="Path to mission-control.db (auto-discovered if omitted)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("move", help="transition a task's status (enforces the Done-Gate)")
    m.add_argument("--task", required=True)
    m.add_argument("--to", required=True, help="target status (e.g. 'review', 'complete', 'in_progress')")
    m.add_argument("--by", default="", help="acting agent id (audit)")
    m.add_argument("--note", default="")

    s = sub.add_parser("signoff", help="record a Devil's Advocate (or other) sign-off")
    s.add_argument("--task", required=True)
    s.add_argument("--role", default=DA_ROLE, help=f"role_type (default {DA_ROLE})")
    s.add_argument("--by", default="", help="signing agent id")
    s.add_argument("--verdict", default="pass", choices=["pass", "fail", "indeterminate"])
    s.add_argument("--note", default="")

    st = sub.add_parser("status", help="show a task's status + DA sign-off state")
    st.add_argument("--task", required=True)

    a = ap.parse_args(argv)

    db_path = _find_db(a.db)
    if not db_path:
        print("[move-task] ERROR: mission-control.db not found. Is Skill 32 (Command Center) installed?", file=sys.stderr)
        return 1

    db = sqlite3.connect(db_path)
    try:
        if a.cmd == "move":
            return cmd_move(db, a)
        if a.cmd == "signoff":
            return cmd_signoff(db, a)
        if a.cmd == "status":
            return cmd_status(db, a)
    finally:
        db.close()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
