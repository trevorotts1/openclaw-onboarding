"""A single-company board belonging to ANOTHER company must CANNOT-VOUCH, not drift.

resolve_company_slug() returns None for a board with <=1 distinct company_id
(nothing to disambiguate), so the join ran unfiltered. When that one company_id
belonged to a different tenant the gate reported THIS company's board as drift
(CHOSEN_NOT_DISPLAYED + DISPLAYED_NOT_CHOSEN) and phase 7z failed the install,
instead of the CANNOT-VOUCH the multi-company path already returns.

Controls pinned here: an own-company clean board still JOIN-OKs; a company_id
derived from the company NAME (not one of the config spellings) still JOIN-OKs
via content overlap; genuine drift on this company's own board still drifts.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JOIN = REPO / "23-ai-workforce-blueprint" / "scripts" / "prove-board-join.py"


class ForeignSingleCompanyBoard(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.home = Path(td.name)
        self.company = self.home / ".openclaw/workspace/zero-human-company/acme"
        self.company.mkdir(parents=True)
        (self.company / "company-config.json").write_text(
            json.dumps({"slug": "acme", "name": "Acme"}))
        (self.company / "departments.json").write_text(
            json.dumps([{"slug": "sales"}, {"slug": "marketing"}]))
        for d in ("sales", "marketing"):
            (self.company / "departments" / d).mkdir(parents=True)

    def _join(self, rows, extra_trees=()):
        for d in extra_trees:
            (self.company / "departments" / d).mkdir(parents=True, exist_ok=True)
        db = self.home / "mission-control.db"
        if db.exists():
            db.unlink()
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE workspaces (slug TEXT, name TEXT, company_id TEXT)")
        c.executemany("INSERT INTO workspaces VALUES (?, ?, ?)",
                      [(s, s, cid) for s, cid in rows])
        c.commit()
        c.close()
        env = {k: v for k, v in os.environ.items()
               if k not in ("DATABASE_PATH", "DASHBOARD_DB_PATH")}
        env["HOME"] = str(self.home)
        p = subprocess.run([sys.executable, str(JOIN), "--company-dir",
                            str(self.company), "--db", str(db), "--json"],
                           capture_output=True, text=True, env=env, timeout=120)
        verdict = (json.loads(p.stdout[p.stdout.index("\n{") + 1:])
                   if "\n{" in p.stdout else {})
        return p.returncode, verdict, p.stdout + p.stderr

    def test_foreign_single_company_id_cannot_vouch(self):
        rc, _v, out = self._join([("operations", "other-co"), ("finance", "other-co")])
        self.assertEqual(rc, 3, out)
        self.assertIn("CANNOT VOUCH", out)
        self.assertNotIn("CHOSEN_NOT_DISPLAYED", out)
        self.assertNotIn("DISPLAYED_NOT_CHOSEN", out)

    def test_own_single_company_clean_board_join_ok(self):
        rc, v, out = self._join([("sales", "acme"), ("marketing", "acme")])
        self.assertEqual(rc, 0, out)
        self.assertEqual(v.get("status"), "JOIN-OK")

    def test_name_derived_company_id_with_content_overlap_join_ok(self):
        # company_id not reproducible from company-config, but the rows ARE ours.
        rc, v, out = self._join([("sales", "acme-llc"), ("marketing", "acme-llc")])
        self.assertEqual(rc, 0, out)
        self.assertEqual(v.get("status"), "JOIN-OK")

    def test_genuine_drift_on_own_board_still_drifts(self):
        rc, v, out = self._join([("sales", "acme")], extra_trees=("legacy-ops",))
        self.assertEqual(rc, 2, out)
        self.assertEqual(v.get("status"), "AF-BOARD-JOIN-DRIFT")
        self.assertIn("CHOSEN_NOT_DISPLAYED", v.get("drift_classes") or [])


if __name__ == "__main__":
    unittest.main()
