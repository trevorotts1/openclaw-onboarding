#!/usr/bin/env python3
"""Class F: heartbeat-embedding-probe.py must not call a box "dark" because its
SOP embeddings came from the shipped asset.

provision_sop_embeddings.py copies the asset's rows verbatim, so their
embedded_at is the ASSET BUILD date. On a box that imported the current release
(and whose Sunday update correctly SKIPs re-importing it) the newest row read
~65 days old, crossed the 30-day threshold and paged Rescue Rangers. Real
staleness must still show: a box's own delta rows that went stale, a box with
no marker, and a shipped asset older than the checkout's release.

Runs the real probe (--dry-run: no DB write, no alert) on fixture DBs.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / "32-command-center-setup" / "scripts" / "heartbeat-embedding-probe.py"
MANIFEST = REPO / "shared-utils" / "sop-embed-once" / "SOP-EMBEDDINGS-MANIFEST.json"


def iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def sql_ts(days_ago):  # datetime('now') spelling, as the marker writes it
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


class ShippedAssetFreshness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "mission-control.db"
        with sqlite3.connect(self.db) as c:
            c.executescript("""
              CREATE TABLE sops(id TEXT PRIMARY KEY, name TEXT, description TEXT, task_keywords TEXT);
              CREATE TABLE sop_embeddings(sop_id TEXT PRIMARY KEY, embedding BLOB,
                embedding_model TEXT, embedding_dims INTEGER, embedded_at TEXT);
              CREATE TABLE persona_index(id TEXT);
              INSERT INTO persona_index VALUES ('p1');
            """)
            for i in range(10):
                c.execute("INSERT INTO sops VALUES (?,?,?,?)", (f"s{i}", f"onboard {i}", "", ""))
                c.execute("INSERT INTO sop_embeddings VALUES (?,?,?,?,?)",
                          (f"s{i}", b"x", "gemini-embedding-2", 3072, iso(65)))  # asset build date

    def tearDown(self):
        self._tmp.cleanup()

    def mark_shipped(self, release, imported_days_ago):
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TABLE sop_embeddings_shipped_asset(id INTEGER PRIMARY KEY CHECK (id=1),"
                      " release_tag TEXT NOT NULL, sop_count INTEGER NOT NULL, sha256 TEXT NOT NULL,"
                      " imported_at TEXT NOT NULL)")
            c.execute("INSERT INTO sop_embeddings_shipped_asset VALUES (1,?,?,?,?)",
                      (release, 10, "0" * 64, sql_ts(imported_days_ago)))

    def probe(self):
        env = {k: v for k, v in os.environ.items() if k != "RESCUE_RANGERS_HELP_CHAT_ID"}
        r = subprocess.run([sys.executable, str(PROBE), "--db", str(self.db), "--dry-run",
                            "--box-id", "fixture"], capture_output=True, text=True, env=env, timeout=60)
        return r.returncode, r.stdout

    def current_release(self):
        return json.loads(MANIFEST.read_text())["release_tag"]

    def test_shipped_asset_only_is_not_dark(self):
        self.mark_shipped(self.current_release(), imported_days_ago=60)
        rc, out = self.probe()
        self.assertEqual(rc, 0, out)
        self.assertIn("status:               healthy", out)

    def test_stale_own_delta_rows_still_go_dark(self):
        self.mark_shipped(self.current_release(), imported_days_ago=60)
        with sqlite3.connect(self.db) as c:  # box's own row, embedded after import, now 40 days old
            c.execute("UPDATE sop_embeddings SET embedded_at=? WHERE sop_id='s0'", (iso(40),))
        rc, out = self.probe()
        self.assertEqual(rc, 2, out)
        self.assertIn("days old", out)

    def test_no_marker_is_aged_as_before(self):
        rc, out = self.probe()
        self.assertEqual(rc, 2, out)
        self.assertIn("embeddings are 65 days old", out)

    def test_older_shipped_release_is_degraded(self):
        self.mark_shipped("sop-embeddings-v0.0.1", imported_days_ago=60)
        rc, out = self.probe()
        self.assertEqual(rc, 1, out)
        self.assertIn("shipped SOP embeddings are release sop-embeddings-v0.0.1", out)


if __name__ == "__main__":
    unittest.main()
