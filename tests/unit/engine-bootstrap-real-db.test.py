#!/usr/bin/env python3
"""Real CC migrations -> real Skill32 seed -> converge twice -> restart.
Run with CC_REPO pointing at the paired checkout with installed dependencies.
No provider, service, browser or client network calls.
"""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
CC = Path(os.environ['CC_REPO']).resolve()
spec = importlib.util.spec_from_file_location('seeder', ROOT / '32-command-center-setup/scripts/seed-workspaces.py')
seeder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seeder)

class EngineFoundation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='engine-bootstrap-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'foundation.test.db'
        self.company = self.root / 'company'
        self.company.mkdir()
        self.uuid = 'fdca238e-b11e-4c04-a356-1b8af5f5fa69'
        self.info = dict(companyId=self.uuid, name='Client Foundation', slug='client-foundation', industry='', brand_primary='#111111', brand_accent='#222222', brand_text='#ffffff')
        self.depts = [dict(id=d, slug=d, name=d.title(), emoji='X') for d in ('podcast','anthology','presentations','marketing')]
        self.env = {**os.environ, 'HOME':str(self.root), 'DATABASE_PATH':str(self.db), 'ZERO_HUMAN_COMPANY_DIR':str(self.company), 'DISABLE_QC_AUTO_SCORER':'true'}
        for key in ('MASTER_FILES_DIR','BLACKCEO_COMMAND_CENTER_ROOT','COMPANY_SLUG','COMPANY_NAME','MC_COMPANY_ID','MC_TENANT_ID','MC_INSTALLATION_ID'):
            self.env.pop(key, None)
        self.run_cc('init')

    def run_cc(self, mode):
        result = subprocess.run([str(CC/'node_modules/.bin/tsx'), str(CC/'tests/helpers/engine-foundation-fixture.ts'), mode], cwd=CC, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-4000:])

    def rows(self, table):
        with sqlite3.connect(self.db) as db:
            return db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()

    def seed(self):
        with patch.dict(os.environ, self.env, clear=True):
            seeder.seed(self.db, self.depts, self.info)

    def test_real_migrations_seed_converge_restart_preserve_bindings(self):
        before_agents = self.rows('agents')
        before_skills = self.rows('agent_skills')
        self.seed()
        self.seed()
        # Adoption itself preserves the original agent rows, not merely IDs.
        self.assertEqual(before_agents, self.rows('agents')[:len(before_agents)])
        self.assertEqual(before_skills, self.rows('agent_skills'))
        (self.company/'departments.json').write_text(json.dumps(self.depts))
        (self.company/'company-config.json').write_text(json.dumps({'id':self.uuid, 'companyId':self.uuid, 'name':self.info['name'], 'slug':self.info['slug']}))
        self.env.update(MC_COMPANY_ID=self.uuid, COMPANY_SLUG=self.info['slug'])
        self.run_cc('converge')
        self.run_cc('restart')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT id FROM workspaces WHERE company_id=? ORDER BY id', (self.uuid,)).fetchall(), [(d,) for d in sorted(x['id'] for x in self.depts)])
            receipts = db.execute('SELECT adopted_company_id, adoption_backup_json FROM engine_workspace_bootstrap').fetchall()
            self.assertEqual(len(receipts), 3)
            self.assertTrue(all(r[0]==self.uuid and json.loads(r[1])['workspace']['company_id']=='default' for r in receipts))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    # A CC system queue under the CC's own 'default' company that is NOT an
    # adoptable placeholder (real work, customized, unrecorded, runtime-bound) is
    # left EXACTLY as it is -- and the client's own departments are still seeded.
    # It used to roll back the whole seed, so a client's custom departments never
    # got a board. Reassigning such a queue is repair-board-company.py --apply only.
    def queue_rows(self, ws):
        with sqlite3.connect(self.db) as db:
            return (db.execute('SELECT * FROM workspaces WHERE id=?', (ws,)).fetchall(),
                    db.execute('SELECT * FROM agents WHERE workspace_id=? ORDER BY id', (ws,)).fetchall(),
                    db.execute('SELECT * FROM tasks WHERE workspace_id=? ORDER BY id', (ws,)).fetchall(),
                    db.execute('SELECT * FROM engine_workspace_bootstrap WHERE workspace_id=?', (ws,)).fetchall())

    def assert_left_alone_and_client_seeded(self, ws):
        before = self.queue_rows(ws)
        self.seed()
        self.seed()
        self.assertEqual(before, self.queue_rows(ws), ws + ' must be left exactly as it was')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT company_id FROM workspaces WHERE id=?", (ws,)).fetchone(), ('default',))
            owned = {r[0] for r in db.execute('SELECT id FROM workspaces WHERE company_id=?', (self.uuid,))}
        self.assertTrue({'presentations', 'marketing'} <= owned, owned)

    def test_active_default_queue_left_alone_rest_seeded(self):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO tasks (id,title,workspace_id) VALUES ('real-work','Existing work','anthology')")
        self.assert_left_alone_and_client_seeded('anthology')

    def test_custom_default_queue_left_alone_rest_seeded(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE workspaces SET name='Existing system queue' WHERE id='podcast'")
        self.assert_left_alone_and_client_seeded('podcast')

    def test_foreign_company_refuses_without_changes(self):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO companies(id,name,slug) VALUES ('other','Other','other')")
            db.execute("UPDATE workspaces SET company_id='other' WHERE id='podcast'")
        before = self.rows('workspaces')
        with self.assertRaises(ValueError): self.seed()
        self.assertEqual(before,self.rows('workspaces'))

    def test_customized_seeded_agent_left_alone_rest_seeded(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE agents SET name='Another team editor' WHERE id='podcast-editor'")
        self.assert_left_alone_and_client_seeded('podcast')

    def test_unrecorded_engine_left_alone_rest_seeded(self):
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM engine_workspace_bootstrap WHERE workspace_id='podcast'")
        self.assert_left_alone_and_client_seeded('podcast')

    def test_runtime_bound_agent_left_alone_rest_seeded(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE agents SET openclaw_agent_id='already-live' WHERE id='podcast-editor'")
        self.assert_left_alone_and_client_seeded('podcast')

if __name__ == '__main__': unittest.main()
