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
import argparse, json, os, sqlite3, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_db import resolve_cc_db, is_db_found  # noqa: E402
from service_env import read_env  # noqa: E402


# The app folders update-skills.sh's cc_resolve_existing_dir accepts, in its own
# order. CC_APP_DIR, when set, pins the answer to that one folder (never falls
# through to another checkout), exactly as the updater's resolver does.
APP_DIR_CANDIDATES = (
    "~/projects/command-center",
    "/data/projects/command-center",
    "~/projects/blackceo-command-center",
    "/data/projects/blackceo-command-center",
    "~/projects/mission-control",
    "~/blackceo-command-center",
    "{oc_root}/command-center",
    "/opt/mission-control",
    "/app",
)


def app_env(app):
    """The Command Center's effective dotenv: <app>/.env under <app>/.env.local (Next.js precedence); a missing file is skipped."""
    return {**read_env(app / ".env"), **read_env(app / ".env.local")}


def app_dir_candidates(oc_root):
    """The updater's candidate folders, expanded, in the updater's order."""
    if os.environ.get("CC_APP_DIR"):
        return [Path(os.path.expanduser(os.environ["CC_APP_DIR"]))]
    root = Path(oc_root) if oc_root else Path.home() / ".openclaw"
    return [Path(os.path.expanduser(c.format(oc_root=root))) for c in APP_DIR_CANDIDATES]


def is_valid_checkout(folder):
    """Port of update-skills.sh cc_is_valid_checkout: a git repo carrying a package.json whose origin is the Command Center."""
    folder = Path(folder)
    if not (folder / ".git").is_dir() or not (folder / "package.json").is_file():
        return False
    try:
        r = subprocess.run(["git", "-C", str(folder), "remote", "get-url", "origin"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and b"blackceo-command-center" in r.stdout


def find_app_dir(oc_root):
    """The first folder the updater would accept, in the updater's order, else None."""
    for cand in app_dir_candidates(oc_root):
        if is_valid_checkout(cand):
            return cand
    return None


def cc_db_path(app=None, db=None, oc_root=None):
    """--db, else the app's own DATABASE_PATH (its .env / .env.local, else <app>/mission-control.db), else the first app folder the updater accepts, else the shared resolver."""
    if db:
        return Path(db)
    if not app:
        app = find_app_dir(oc_root)
    if app:
        app = Path(app)
        p = Path(os.path.expanduser(app_env(app).get("DATABASE_PATH") or "mission-control.db"))
        return p if p.is_absolute() else app / p
    return resolve_cc_db()


def run(state, app=None, db=None, check_only=False, oc_root=None):
    try:
        done = json.loads(Path(state).read_text()).get("interviewComplete") is True
    except (OSError, ValueError, AttributeError):
        return 4, "no readable build-state at %s" % state
    if not done:
        return 0, "build-state interviewComplete is not true; nothing to mirror"
    path = cc_db_path(app, db, oc_root)
    if not is_db_found(path):
        return 4, "no Command Center database found (looked in %d app folders and the shared resolver)" % len(app_dir_candidates(oc_root))
    folder = " (database folder: %s)" % path.parent.name
    con = sqlite3.connect(path.resolve().as_uri() + ("?mode=ro" if check_only else "?mode=rw"), uri=True, timeout=10)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(clients)")}
        if not {"is_self", "interview_complete"} <= cols:
            return 4, "no clients.interview_complete column (legacy Command Center database)" + folder
        row = con.execute("SELECT interview_complete FROM clients WHERE is_self = 1 LIMIT 1").fetchone()
        if row is None:
            return 4, "no is_self=1 client row" + folder
        if row[0] == 1:
            return 0, "already set (build-state and Command Center agree)"
        if check_only:
            return 3, "MISMATCH: build-state interviewComplete=true but clients.interview_complete=%s" % row[0] + folder
        with con:
            con.execute("UPDATE clients SET interview_complete = 1, updated_at = datetime('now') "
                        "WHERE is_self = 1 AND interview_complete IS NOT 1")
        row = con.execute("SELECT interview_complete FROM clients WHERE is_self = 1 LIMIT 1").fetchone()
        if row is None or row[0] != 1:
            return 3, "wrote but verification FAILED" + folder
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
        rc, msg = run(state, Path(a.app) if a.app else None, a.db, a.check, oc)
    except Exception as e:  # never raise into an update or an interview completion
        rc, msg = 3, "error: %s" % type(e).__name__
    print("cc-interview-flag: " + msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
