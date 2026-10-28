#!/usr/bin/env python3
"""ensure_cc_interview_flag.py -- mirror build-state interviewComplete into the Command Center database.

Command Center task ingest (isWorkforceProvisioned) reads clients.interview_complete on the is_self=1
row. Only the Command Center interview web page ever wrote it, so an interview finished through the
script / Telegram path left .workforce-build-state.json true and the database flag 0, and ingest then
parked every task in General Task. Called right after `update-interview-state.sh --complete` and on
every update/roll, so existing boxes heal on their next roll.

  ensure_cc_interview_flag.py [--state FILE] [--app DIR | --db FILE] [--oc-root DIR] [--check]

Rules: sets interview_complete=1 on the is_self=1 clients row ONLY when the build-state
interviewComplete is exactly true; never clears the flag; never touches another row or table; never
creates a database; idempotent. Never prints env values.

Exit: 0 already set / written / build-state not complete (nothing to mirror), 3 flag not set
(--check) or the write failed, 4 not applicable (no readable build-state, no Command Center
database, no self client row).
"""
import argparse, json, os, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_db import resolve_cc_db, is_db_found  # noqa: E402
from service_env import read_env  # noqa: E402


def cc_db_path(app=None, db=None):
    """--db, else the app's own DATABASE_PATH (its .env.local, else <app>/mission-control.db), else the shared resolver."""
    if db:
        return Path(db)
    if app:
        p = Path(os.path.expanduser(read_env(app / ".env.local").get("DATABASE_PATH") or "mission-control.db"))
        return p if p.is_absolute() else app / p
    return resolve_cc_db()


def run(state, app=None, db=None, check_only=False):
    try:
        done = json.loads(Path(state).read_text()).get("interviewComplete") is True
    except (OSError, ValueError, AttributeError):
        return 4, "no readable build-state at %s" % state
    if not done:
        return 0, "build-state interviewComplete is not true; nothing to mirror"
    path = cc_db_path(app, db)
    if not is_db_found(path):
        return 4, "no Command Center database found"
    con = sqlite3.connect(path.resolve().as_uri() + ("?mode=ro" if check_only else "?mode=rw"), uri=True, timeout=10)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(clients)")}
        if not {"is_self", "interview_complete"} <= cols:
            return 4, "no clients.interview_complete column (legacy Command Center database)"
        row = con.execute("SELECT interview_complete FROM clients WHERE is_self = 1 LIMIT 1").fetchone()
        if row is None:
            return 4, "no is_self=1 client row"
        if row[0] == 1:
            return 0, "already set (build-state and Command Center agree)"
        if check_only:
            return 3, "MISMATCH: build-state interviewComplete=true but clients.interview_complete=%s" % row[0]
        with con:
            con.execute("UPDATE clients SET interview_complete = 1, updated_at = datetime('now') "
                        "WHERE is_self = 1 AND interview_complete IS NOT 1")
        row = con.execute("SELECT interview_complete FROM clients WHERE is_self = 1 LIMIT 1").fetchone()
        if row is None or row[0] != 1:
            return 3, "wrote but verification FAILED"
        return 0, "set clients.interview_complete=1 for the is_self=1 row (build-state interviewComplete=true)"
    finally:
        con.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state")
    ap.add_argument("--app")
    ap.add_argument("--db")
    ap.add_argument("--oc-root")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    oc = Path(a.oc_root or os.environ.get("OPENCLAW_ROOT") or Path.home() / ".openclaw")
    state = a.state or os.environ.get("WORKFORCE_BUILD_STATE_PATH") or oc / "workspace/.workforce-build-state.json"
    try:
        rc, msg = run(state, Path(a.app) if a.app else None, a.db, a.check)
    except Exception as e:  # never raise into an update or an interview completion
        rc, msg = 3, "error: %s" % type(e).__name__
    print("cc-interview-flag: " + msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
