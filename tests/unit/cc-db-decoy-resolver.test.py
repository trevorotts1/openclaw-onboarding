#!/usr/bin/env python3
"""Class B: the shared mission-control.db resolver must never pick a decoy.

shared-utils/resolve_db.py find_dashboard_db() is what backfill-per-dept-healer.sh,
materialize-dept-agents.sh, qc-system-integrity.sh, the persona probe, the
runtime-parity guard and the embedding probe all route through. It used to
return the FIRST EXISTING candidate, so a 0-byte `mission-control.db` (a stray
touch, a failed open) earlier in the list shadowed the live board, and an env
value of "" or "~/..." was taken literally. Every case below fails on main.

Hermetic: each case runs the resolver in a subprocess with HOME = a temp dir
and the DB env vars cleared.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESOLVER = REPO / "shared-utils" / "resolve_db.py"


def board(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE workspaces(id TEXT)")
    return path


class DecoyResolver(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.env = {k: v for k, v in os.environ.items()
                    if k not in ("DASHBOARD_DB_PATH", "DATABASE_PATH")}
        self.env["HOME"] = str(self.home)
        self.live = board(self.home / "projects" / "command-center" / "mission-control.db")

    def tearDown(self):
        self._tmp.cleanup()

    def resolve(self, **env):
        code = ("import sys; sys.path.insert(0, sys.argv[1]);"
                "from resolve_db import find_dashboard_db, is_db_found;"
                "p = find_dashboard_db(); print(p if is_db_found(p) else '')")
        r = subprocess.run([sys.executable, "-c", code, str(RESOLVER.parent)], capture_output=True,
                           text=True, env=dict(self.env, **env), timeout=30)
        return r.stdout.strip()

    def test_zero_byte_decoy_earlier_in_list_is_skipped(self):
        decoy = self.home / "data" / "mission-control.db"  # probed before ~/projects
        decoy.parent.mkdir(parents=True)
        decoy.touch()
        self.assertEqual(self.resolve(), str(self.live))

    def test_layout_candidate_without_workspaces_table_is_skipped(self):
        stray = self.home / "data" / "mission-control.db"
        stray.parent.mkdir(parents=True)
        with sqlite3.connect(stray) as db:
            db.execute("CREATE TABLE unrelated(x)")
        self.assertEqual(self.resolve(), str(self.live))

    def test_zero_byte_env_path_is_skipped(self):
        empty = self.home / "empty.db"
        empty.touch()
        self.assertEqual(self.resolve(DATABASE_PATH=str(empty)), str(self.live))

    def test_blank_env_var_is_ignored(self):
        self.assertEqual(self.resolve(DASHBOARD_DB_PATH=""), str(self.live))

    def test_env_tilde_is_expanded(self):
        other = board(self.home / "elsewhere" / "cc.db")
        self.assertEqual(self.resolve(DATABASE_PATH="~/elsewhere/cc.db"), str(other))

    def test_env_local_database_path_is_honored(self):
        other = board(self.home / "state" / "live.db")
        (self.live.parent / ".env.local").write_text("export DATABASE_PATH='~/state/live.db'\n")
        self.assertEqual(self.resolve(), str(other))

    def test_cli_path_contract_for_shell_callers(self):
        # backfill-per-dept-healer.sh / materialize-dept-agents.sh /
        # qc-system-integrity.sh call `resolve_db.py --path`.
        r = subprocess.run([sys.executable, str(RESOLVER), "--path"], capture_output=True,
                           text=True, env=self.env, timeout=30)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, str(self.live)))

    def test_nothing_usable_resolves_to_nothing(self):
        self.live.unlink()
        self.live.touch()  # only a 0-byte file left
        r = subprocess.run([sys.executable, str(RESOLVER), "--path"], capture_output=True,
                           text=True, env=self.env, timeout=30)
        self.assertEqual((r.returncode, r.stdout.strip()), (1, ""))


if __name__ == "__main__":
    unittest.main()
