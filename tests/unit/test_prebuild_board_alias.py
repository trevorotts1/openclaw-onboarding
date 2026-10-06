#!/usr/bin/env python3
"""Prebuild receipt verification against real SQLite runtime board projections."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'launch_board_alias', ROOT / '32-command-center-setup/scripts/interview-launch.py')
launch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch)


class PrebuildBoardAlias(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        self.company = self.root / 'company'
        self.soul = self.company / 'departments/master-orchestrator/agents/owner/SOUL.md'
        self.soul.parent.mkdir(parents=True)
        self.soul.write_text('Synthetic canonical CEO identity\n')
        (self.company / 'departments.json').write_text(json.dumps([
            {'slug': 'ceo', 'workspacePath': 'departments/master-orchestrator'}]))
        self.state = self.root / 'state.json'
        self.state.write_text(json.dumps({
            'companyId': 'company-a', 'tenantId': 'tenant-a',
            'installationId': 'installation-a', 'buildId': 'build-a',
            'companySlug': 'fixture-a', 'companyName': 'Fixture A',
            'companyRoot': str(self.company), 'buildType': 'standard-first',
            'interviewComplete': False,
            'operatorConsent': {'decision': 'prebuild'},
            'standardPrebuild': {'prebuiltDepartments': ['master-orchestrator']},
        }))
        self.dbpath = self.app / 'mission-control.db'
        with sqlite3.connect(self.dbpath) as db:
            db.execute('CREATE TABLE workspaces(id TEXT PRIMARY KEY, slug TEXT, company_id TEXT, archived_at TEXT)')
        (self.app / '.env.local').write_text(launch.encode_assignment('DATABASE_PATH', str(self.dbpath)) + '\n')

    def board(self, slug, company='company-a', archived=None, row_id='master-orchestrator'):
        with sqlite3.connect(self.dbpath) as db:
            db.execute('INSERT OR REPLACE INTO workspaces VALUES(?,?,?,?)',
                       (row_id, slug, company, archived))

    def verify(self):
        # Only the already-covered materializer is stubbed. Verification opens
        # actual SQLite and hashes actual files through the production wrapper.
        with patch.dict(os.environ, {}, clear=True), patch.object(launch.subprocess, 'run') as engine:
            launch.prebuild(self.state, self.app, ROOT)
        engine.assert_called_once()
        self.assertTrue(engine.call_args.kwargs['check'])
        return json.loads(self.state.read_text())['standardPrebuild']['foundationVerification']

    def test_runtime_aliases_verify_without_mutating_raw_artifact_paths_or_board(self):
        for slug in ('master-orchestrator', 'ceo', 'dept-ceo', 'central-operations'):
            with self.subTest(slug=slug):
                self.board(slug)
                receipt = self.verify()
                self.assertEqual(receipt['workspaceSlugs'], ['master-orchestrator'])
                self.assertEqual(receipt['companyId'], 'company-a')
                self.assertEqual(receipt['artifacts'][1]['path'], 'departments/master-orchestrator/agents/owner/SOUL.md')
                with sqlite3.connect(self.dbpath) as db:
                    self.assertEqual(db.execute('SELECT slug FROM workspaces').fetchone()[0], slug)

    def test_foreign_alias_cannot_supply_missing_owned_department(self):
        self.board('ceo', company='company-b')
        self.board('sales', row_id='own-sales')
        with self.assertRaisesRegex(ValueError, 'workspace ownership verification failed'):
            self.verify()
        self.assertNotIn('foundationVerification', json.loads(self.state.read_text())['standardPrebuild'])

    def test_archived_alias_cannot_supply_active_department(self):
        self.board('ceo', archived='2026-01-01')
        with self.assertRaisesRegex(ValueError, 'workspace ownership verification failed'):
            self.verify()

    def test_matching_row_id_does_not_override_unrelated_slug(self):
        self.board('sales')
        with self.assertRaisesRegex(ValueError, 'workspace ownership verification failed'):
            self.verify()

    def test_alias_does_not_bypass_canonical_identity_artifact_requirement(self):
        self.board('ceo')
        self.soul.unlink()
        with self.assertRaisesRegex(ValueError, 'canonical artifact missing'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
