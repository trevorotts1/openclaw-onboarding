#!/usr/bin/env python3
"""Board lanes land under the client's ONE company.

  * seed-dashboard-content.py: a company name with punctuation ("Acme Rocket!")
    no longer creates a second company row; the canonical companyId wins and is
    updated in place.
  * seed-workspaces.py: a CC system queue under 'default' that cannot be adopted
    no longer aborts the whole seed -- the client's custom lanes are seeded.
  * repair-board-company.py: dry run changes nothing; --apply merges the
    duplicate company, moves the client's 'default' lanes, seeds missing lanes,
    writes a row-level backup first (--restore undoes it), and is idempotent; a
    shared (multi-company) board refuses the lane move; --chosen-only moves only
    the chosen departments' 'default' lanes, even with another company row.
  * seed-workspaces.py find_company_info(): an explicit COMPANY_SLUG wins over a
    slug derived from COMPANY_NAME.

Run: python3 tests/unit/test_board_company_repair.py
"""
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
S32 = ROOT / "32-command-center-setup" / "scripts"
UUID = "0f0e0d0c-0b0a-4908-8706-050403020100"


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, str(S32 / file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Board(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name)
        self.db = self.root / "mission-control.db"
        self.company = self.root / "company"
        self.company.mkdir()
        (self.company / "departments.json").write_text(json.dumps([
            {"id": "marketing", "name": "Marketing"},
            {"id": "client-experience-booking", "name": "Client Experience Booking"},
            {"id": "launch-operations", "name": "Launch Operations"},
            {"id": "podcast", "name": "Podcast"}]))
        (self.company / "company-config.json").write_text(json.dumps(
            {"name": "Acme Rocket", "slug": "acme-rocket", "companyId": UUID}))
        with sqlite3.connect(self.db) as db:
            db.executescript(f"""
                CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
                                        industry TEXT, config TEXT DEFAULT '{{}}');
                CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
                                         description TEXT, icon TEXT, company_id TEXT DEFAULT 'default');
                CREATE TABLE agents (id TEXT PRIMARY KEY, name TEXT, workspace_id TEXT, company_id TEXT);
                CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, workspace_id TEXT, company_id TEXT);
                CREATE TABLE engine_workspace_bootstrap (workspace_id TEXT PRIMARY KEY,
                    original_workspace_json TEXT, adopted_company_id TEXT,
                    adoption_backup_json TEXT, adopted_at TEXT);
                INSERT INTO companies (id, name, slug) VALUES ('default', 'Default', 'default');
                INSERT INTO companies (id, name, slug) VALUES ('{UUID}', 'Acme Rocket', 'acme-rocket');
                INSERT INTO companies (id, name, slug) VALUES ('dup0001', 'Acme Rocket!', 'acme rocket!');
                INSERT INTO agents VALUES ('dept-head-x', 'Head', 'marketing', 'dup0001');
                INSERT INTO workspaces (id, name, slug, company_id) VALUES ('marketing', 'Marketing', 'marketing', '{UUID}');
                INSERT INTO workspaces (id, name, slug, company_id) VALUES ('podcast', 'Podcast', 'podcast', 'default');
                INSERT INTO engine_workspace_bootstrap (workspace_id, original_workspace_json)
                    VALUES ('podcast', '{{}}');
                INSERT INTO tasks VALUES ('ep-1', 'Episode 1', 'podcast', 'default');
            """)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.root), "ZERO_HUMAN_COMPANY_DIR": str(self.company),
                                                "MC_COMPANY_ID": UUID, "COMPANY_SLUG": "acme-rocket"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self._t.cleanup()

    def q(self, sql, *args):
        with sqlite3.connect(self.db) as db:
            return db.execute(sql, args).fetchall()


class TestSeedDashboardCompanyRow(_Board):
    def test_punctuated_name_never_creates_a_second_company(self):
        sd = _load("sd_company_test", "seed-dashboard-content.py")
        self.q("DELETE FROM companies WHERE id='dup0001'")
        for env in ({"MC_COMPANY_ID": UUID}, {"MC_COMPANY_ID": ""}):  # by companyId, then by slug
            with mock.patch.dict(os.environ, {"COMPANY_NAME": "Acme Rocket!", **env}):
                info = sd.find_company_config()
                with sqlite3.connect(self.db) as db:
                    self.assertEqual(sd.insert_company(db, info), UUID)
                    db.commit()
            self.assertEqual(self.q("SELECT id FROM companies WHERE id != 'default'"), [(UUID,)])

    def test_slug_rule_strips_punctuation(self):
        src = (S32 / "seed-dashboard-content.py").read_text()
        self.assertNotIn('.lower().replace(" ", "-").replace(",", "")', src)


class TestSeedWorkspacesDoesNotAbort(_Board):
    def test_default_owned_queue_left_alone_custom_lanes_seeded(self):
        sw = _load("sw_seed_test", "seed-workspaces.py")
        deps, _ = sw.find_departments_config()
        sw.seed(self.db, deps, {"companyId": UUID, "name": "Acme Rocket", "slug": "acme-rocket", "industry": "",
                                "brand_primary": "#1", "brand_accent": "#2", "brand_text": "#3"})
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='podcast'"), [("default",)])
        owned = {r[0] for r in self.q("SELECT id FROM workspaces WHERE company_id=?", UUID)}
        self.assertTrue({"client-experience-booking", "launch-operations"} <= owned, owned)


class TestRepairCommand(_Board):
    def repair(self, *args):
        return _load("repair_test", "repair-board-company.py").main(["--db", str(self.db), *args])

    def test_dry_run_changes_nothing(self):
        before = self.db.read_bytes()
        self.assertEqual(self.repair(), 0)
        self.assertEqual(before, self.db.read_bytes())

    def test_apply_merges_moves_seeds_and_is_idempotent(self):
        self.assertEqual(self.repair("--apply"), 0)
        self.assertEqual(self.q("SELECT id FROM companies ORDER BY id"), sorted([("default",), (UUID,)]))
        self.assertEqual(self.q("SELECT company_id FROM agents WHERE id='dept-head-x'"), [(UUID,)])
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='podcast'"), [(UUID,)])
        self.assertEqual(self.q("SELECT company_id FROM tasks WHERE id='ep-1'"), [(UUID,)])
        owned = {r[0] for r in self.q("SELECT id FROM workspaces WHERE company_id=?", UUID)}
        self.assertEqual(owned, {"marketing", "podcast", "client-experience-booking", "launch-operations"})
        self.assertTrue(list(self.root.glob("mission-control.db.repair-board-company-*.rows.json")))
        after = self.db.read_bytes()
        self.assertEqual(self.repair("--apply"), 0)
        self.assertEqual(after, self.db.read_bytes(), "second --apply must be a no-op")

    def test_shared_board_refuses_the_lane_move(self):
        self.q("INSERT INTO companies (id, name, slug) VALUES ('other-client', 'Other', 'other')")
        self.assertEqual(self.repair("--apply"), 0)
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='podcast'"), [("default",)])
        self.assertEqual(self.q("SELECT company_id FROM tasks WHERE id='ep-1'"), [("default",)])


class TestRepairCoversTheWholeCompany(_Board):
    """Field shape: departments.json lists only some departments, four more exist
    only on disk under the build's companyRoot and in the build state, the CEO
    lane lives under id master-orchestrator with slug ceo, podcast and anthology
    sit under 'default', and a duplicate punctuated company row exists."""

    ON_DISK_ONLY = ["client-experience-booking", "founding-member-concierge",
                    "launch-operations", "product-production"]

    def setUp(self):
        super().setUp()
        (self.company / "departments.json").write_text(json.dumps([
            {"id": "ceo", "name": "CEO"}, {"id": "marketing", "name": "Marketing"},
            {"id": "podcast", "name": "Podcast"}, {"id": "anthology", "name": "Anthology"}]))
        for slug in ["ceo", "marketing", "podcast", "anthology", *self.ON_DISK_ONLY]:
            (self.company / "departments" / slug).mkdir(parents=True)
        ws = self.root / ".openclaw" / "workspace"
        ws.mkdir(parents=True)
        (ws / ".workforce-build-state.json").write_text(json.dumps({
            "companyRoot": str(self.company), "companySlug": "acme-rocket",
            "departments": [{"slug": s} for s in ["ceo", "marketing", "founding-member-concierge"]]}))
        self.q(f"INSERT INTO workspaces (id, name, slug, company_id) VALUES "
               f"('master-orchestrator', 'CEO', 'ceo', '{UUID}')")
        self.q("INSERT INTO workspaces (id, name, slug, company_id) VALUES ('anthology', 'Anthology', 'anthology', 'default')")
        self.q("INSERT INTO engine_workspace_bootstrap (workspace_id, original_workspace_json) VALUES ('anthology', '{}')")

    def repair(self, *args):
        return _load("repair_cover_test", "repair-board-company.py").main(["--db", str(self.db), *args])

    def test_dry_run_reports_on_disk_lanes_and_not_the_ceo(self):
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.repair(), 0)
        plan = json.loads(out.getvalue().split("\nDRY RUN")[0])
        self.assertEqual(plan["missing_lanes"], sorted(self.ON_DISK_ONLY))
        self.assertEqual(plan["default_lanes"], ["anthology", "podcast"])
        self.assertEqual(plan["canonical_slug_module"], "shared-utils/canonical_slug.py")

    def test_apply_leaves_full_coverage_and_no_duplicate_lanes(self):
        self.assertEqual(self.repair("--apply"), 0)
        self.assertEqual(self.q("SELECT id FROM companies ORDER BY id"), sorted([("default",), (UUID,)]))
        rows = self.q("SELECT id, slug FROM workspaces WHERE company_id=?", UUID)
        slugs = [r[1] for r in rows]
        self.assertEqual(len(slugs), len(set(slugs)), rows)
        want = {"ceo", "marketing", "podcast", "anthology", *self.ON_DISK_ONLY}
        self.assertEqual(set(slugs), want)
        self.assertEqual(self.q("SELECT id FROM workspaces WHERE slug='ceo'"), [("master-orchestrator",)])
        self.assertEqual(self.q("SELECT count(*) FROM workspaces WHERE company_id='default'"), [(0,)])
        after = self.db.read_bytes()
        self.assertEqual(self.repair("--apply"), 0)
        self.assertEqual(after, self.db.read_bytes(), "second --apply must be a no-op")


class TestChosenOnly(_Board):
    """Field shape: podcast (chosen) and anthology (engine queue, not chosen) both
    sit under 'default', and a second company row exists on the board."""

    def setUp(self):
        super().setUp()
        (self.company / "departments.json").write_text(json.dumps([
            {"id": "marketing", "name": "Marketing"}, {"id": "podcast", "name": "Podcast"}]))
        self.q("INSERT INTO workspaces (id, name, slug, company_id) VALUES ('anthology', 'Anthology', 'anthology', 'default')")
        self.q("INSERT INTO engine_workspace_bootstrap (workspace_id, original_workspace_json) VALUES ('anthology', '{}')")
        self.q("INSERT INTO tasks VALUES ('book-1', 'Book 1', 'anthology', 'default')")
        self.q("INSERT INTO companies (id, name, slug) VALUES ('stray-co', 'Acme Rocket Ecosystem', 'acme-rocket-ecosystem')")

    def repair(self, *args):
        return _load("repair_chosen_test", "repair-board-company.py").main(["--db", str(self.db), *args])

    def test_only_the_chosen_lane_moves(self):
        self.assertEqual(self.repair("--chosen-only", "--apply"), 0)
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='podcast'"), [(UUID,)])
        self.assertEqual(self.q("SELECT company_id FROM tasks WHERE id='ep-1'"), [(UUID,)])
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='anthology'"), [("default",)])
        self.assertEqual(self.q("SELECT company_id FROM tasks WHERE id='book-1'"), [("default",)])
        # only chosen departments are seeded: no lanes for unchosen folders/state entries
        self.assertEqual({r[0] for r in self.q("SELECT id FROM workspaces WHERE company_id=?", UUID)},
                         {"marketing", "podcast"})

    def test_without_chosen_only_the_shared_board_still_refuses(self):
        self.assertEqual(self.repair("--apply"), 0)
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='podcast'"), [("default",)])

    def test_lane_another_company_works_in_is_left_alone(self):
        self.q("INSERT INTO tasks VALUES ('ep-x', 'Theirs', 'podcast', 'stray-co')")
        self.assertEqual(self.repair("--chosen-only", "--apply"), 0)
        self.assertEqual(self.q("SELECT company_id FROM workspaces WHERE id='podcast'"), [("default",)])

    def test_row_backup_restores_every_moved_row(self):
        before = self.q("SELECT 'c', id, name, slug FROM companies UNION ALL SELECT 'w', id, company_id, '' FROM workspaces "
                        "UNION ALL SELECT 't', id, company_id, '' FROM tasks UNION ALL SELECT 'a', id, company_id, '' FROM agents")
        self.q("DELETE FROM companies WHERE id='stray-co'")  # let A (dup merge) and B both run
        before = [r for r in before if r[1] != "stray-co"]
        self.assertEqual(self.repair("--chosen-only", "--apply"), 0)
        [backup] = self.root.glob("mission-control.db.repair-board-company-*.rows.json")
        self.assertLess(backup.stat().st_size, self.db.stat().st_size)
        self.assertEqual(self.repair("--restore", str(backup)), 0)
        self.q("DELETE FROM workspaces WHERE company_id=? AND id NOT IN ('marketing', 'podcast')", UUID)  # C is additive
        after = self.q("SELECT 'c', id, name, slug FROM companies UNION ALL SELECT 'w', id, company_id, '' FROM workspaces "
                       "UNION ALL SELECT 't', id, company_id, '' FROM tasks UNION ALL SELECT 'a', id, company_id, '' FROM agents")
        self.assertEqual(sorted(before), sorted(after))


class TestSeedSlug(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.home = self._t.name
        (Path(self.home) / ".openclaw").mkdir()   # a Mac-layout box, no company on disk
        self.addCleanup(self._t.cleanup)

    def test_explicit_company_slug_wins_over_the_name(self):
        sw = _load("sw_slug_test", "seed-workspaces.py")
        with mock.patch.dict(
                os.environ, {"HOME": self.home, "COMPANY_SLUG": "x", "COMPANY_NAME": "X Ecosystem",
                             "ZERO_HUMAN_COMPANY_DIR": ""}):
            info = sw.find_company_info(None)
        self.assertEqual((info["slug"], info["name"]), ("x", "X Ecosystem"))

    def test_name_still_derives_the_slug_when_none_is_given(self):
        sw = _load("sw_slug_test2", "seed-workspaces.py")
        with mock.patch.dict(
                os.environ, {"HOME": self.home, "COMPANY_SLUG": "", "COMPANY_NAME": "X Ecosystem",
                             "ZERO_HUMAN_COMPANY_DIR": ""}):
            self.assertEqual(sw.find_company_info(None)["slug"], "x-ecosystem")


if __name__ == "__main__":
    unittest.main(verbosity=2)
