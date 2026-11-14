#!/usr/bin/env python3
"""Tests for ensure_cc_interview_flag.py -- the interview-finished mirror.

Every case runs the helper as a subprocess against a throwaway HOME on a
temporary folder: no real Command Center, no real database and no real
build-state is read or written. The app-folder fixture is a throwaway git
repository whose origin is the Command Center, so it passes the same validity
test the updater's cc_is_valid_checkout applies.

Covered (U-23):
  1. --state only, build-state complete, flag 0 -> exit 0 and the flag is 1
     (before the fix: exit 4, the folder was never resolved);
  2. the same fixture with --check -> exit 3 and the flag is STILL 0;
  3. interviewComplete false -> exit 0 and the flag is untouched;
  4. no database anywhere under the temporary home -> exit 4 and the printed
     line says how many app folders were looked in.
"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent / "ensure_cc_interview_flag.py"
CLEARED = ("DASHBOARD_DB_PATH", "DATABASE_PATH", "WORKFORCE_BUILD_STATE_PATH",
           "OPENCLAW_ROOT", "CC_APP_DIR", "OC_WORKSPACE_DEFAULT", "OC_CONFIG")


def run_helper(home, *args):
    """Run the helper with a clean, throwaway HOME; return the CompletedProcess."""
    env = {k: v for k, v in os.environ.items() if k not in CLEARED}
    env["HOME"] = str(home)
    return subprocess.run([sys.executable, str(HELPER), *args],
                          env=env, capture_output=True, text=True)


def make_app(home):
    """A Command Center checkout at <home>/projects/blackceo-command-center with the is_self row at 0."""
    app = home / "projects" / "blackceo-command-center"
    app.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(app)], check=True)
    subprocess.run(["git", "-C", str(app), "remote", "add", "origin",
                    "https://github.com/trevorotts1/blackceo-command-center.git"], check=True)
    (app / "package.json").write_text("{}\n", encoding="utf-8")
    db = app / "mission-control.db"
    con = sqlite3.connect(db)
    try:
        con.executescript(
            "CREATE TABLE clients (id INTEGER PRIMARY KEY, is_self INTEGER, "
            "interview_complete INTEGER, updated_at TEXT);"
            "INSERT INTO clients (is_self, interview_complete) VALUES (1, 0);")
        con.commit()
    finally:
        con.close()
    return app, db


def make_state(home, complete):
    path = home / "workspace" / ".workforce-build-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"interviewComplete": complete}), encoding="utf-8")
    return path


def read_flag(db):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT interview_complete FROM clients WHERE is_self = 1 LIMIT 1").fetchone()[0]
    finally:
        con.close()


def test_state_only_resolves_the_app_folder_and_sets_the_flag(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _app, db = make_app(home)
    state = make_state(home, True)

    proc = run_helper(home, "--state", str(state))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert read_flag(db) == 1
    assert "set clients.interview_complete=1" in proc.stdout


def test_check_reports_the_mismatch_and_leaves_the_flag_alone(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _app, db = make_app(home)
    state = make_state(home, True)

    proc = run_helper(home, "--check", "--state", str(state))

    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert read_flag(db) == 0
    assert "MISMATCH" in proc.stdout


def test_incomplete_interview_is_a_no_op(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _app, db = make_app(home)
    state = make_state(home, False)

    proc = run_helper(home, "--state", str(state))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert read_flag(db) == 0
    assert "nothing to mirror" in proc.stdout


def test_no_database_anywhere_says_how_many_folders_were_looked_in(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    state = make_state(home, True)

    proc = run_helper(home, "--state", str(state))

    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "no Command Center database found" in proc.stdout
    assert "looked in 9 app folders and the shared resolver" in proc.stdout
