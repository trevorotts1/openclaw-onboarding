#!/usr/bin/env python3
"""BU-35 acceptance test: the link sender uses the Command Center's rule.

Drives shared-utils/interview_completion.py prompt_status with the fixture table
tests/fixtures/state-identity-cases.json, the same table the Command Center runs
against its classifyStateIdentity, so the two copies of the rule cannot agree by
accident.

Three cases, one rule:
  matched    — all three stamps present and equal;
  legacy     — NONE of the three present (a state written before the stamps);
  mismatched — a present stamp differs, or only some are present.
matched and legacy continue to the completion check; only mismatched answers
UNKNOWN, which the link sender reports as exit 8.
"""
from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'state-identity-cases.json'

sys.path.insert(0, str(ROOT / 'shared-utils'))

from interview_completion import prompt_status  # noqa: E402

DECLARATION_TABLE = '''CREATE TABLE interview_prior_completion_declarations (
    tenant_id TEXT, company_id TEXT, installation_id TEXT, declared_by TEXT,
    declared_at TEXT, source TEXT, PRIMARY KEY(tenant_id, company_id, installation_id))'''


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


class IdentityRule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.database = self.root / 'mission-control.db'
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(DECLARATION_TABLE)
        self.document = load_fixture()
        self.context = dict(self.document['context'])

    def tearDown(self):
        self.tmp.cleanup()

    def declare(self):
        with contextlib.closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute('INSERT INTO interview_prior_completion_declarations VALUES(?,?,?,?,?,?)',
                               (self.context['tenantId'], self.context['companyId'],
                                self.context['installationId'], 'owner', '2026-09-24',
                                'owner-self-attestation'))

    def env(self, database=None):
        database = str(self.database if database is None else database)
        return {'DATABASE_PATH': database, 'DASHBOARD_DB_PATH': database,
                'MC_TENANT_ID': self.context['tenantId'],
                'MC_COMPANY_ID': self.context['companyId'],
                'MC_INSTALLATION_ID': self.context['installationId']}

    def status(self, stamps, env=None, complete=False):
        """prompt_status plus the one stderr line it must print."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = prompt_status(dict(stamps, interviewComplete=complete),
                                   self.env() if env is None else env)
        return result, stderr.getvalue()

    def test_the_fixture_covers_the_three_classes(self):
        cases = self.document['cases']
        self.assertEqual(len(cases), 5)
        self.assertEqual({case['class'] for case in cases},
                         {'matched', 'legacy', 'mismatched'})
        self.assertEqual({case['word'] for case in cases},
                         {'INCOMPLETE', 'UNKNOWN', 'COMPLETE'})

    def test_every_fixture_case_answers_its_word_and_names_its_class(self):
        for case in self.document['cases']:
            with self.subTest(case=case['name']):
                if case['declared']:
                    self.declare()
                result, stderr = self.status(
                    case['stamps'], complete=case.get('interviewComplete', False))
                self.assertEqual(result, case['word'])
                # COMPLETE returns before the identity rule runs, so it is the one
                # word that does not print the identity line (BU-35).
                if case['word'] != 'COMPLETE':
                    self.assertEqual(len(stderr.strip().splitlines()), 1, stderr)
                    self.assertIn(f'identity {case["class"]}:', stderr)

    def test_matched_with_a_declaration_is_declared(self):
        self.declare()
        matched = next(case for case in self.document['cases'] if case['class'] == 'matched')
        result, stderr = self.status(matched['stamps'])
        self.assertEqual(result, 'DECLARED')
        self.assertIn('identity matched:', stderr)

    def test_a_missing_database_continues_instead_of_answering_unknown(self):
        missing = self.root / 'missing.db'
        result, stderr = self.status({}, self.env(database=missing))
        self.assertEqual(result, 'INCOMPLETE')
        self.assertIn('identity legacy:', stderr)
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
