#!/usr/bin/env python3
"""S75-T02 invariant tests: wrong/missing job UUID refuses affected writes
with no fallback, and a prebuilder receipt proves the ACTUAL recurring jobID.

Run: python3 -I tests/unit/job-uuid-gate.test.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'scripts', 'lib'))

import job_uuid_gate as g  # noqa: E402

JOB = 'a8a8ad74'
JOBS = [{'id': JOB, 'recurring': True, 'schedule': '*/1 * * * *'}]


class GateTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='s75t02-'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def target(self):
        return self.dir / 'nested' / 'state.json'

    # --- writes allowed only on an exact, recurring, unambiguous proof -----
    def test_proven_write_lands(self):
        out = g.guarded_write(self.target(), '{"k":1}', expected_job_id=JOB,
                              observed_jobs=JOBS)
        self.assertEqual(out['actual_recurring_job_id'], JOB)
        self.assertEqual(self.target().read_text(), '{"k":1}')

    # --- no silent fallback on wrong / missing / unknown ------------------
    def test_wrong_uuid_refuses_and_writes_nothing(self):
        with self.assertRaises(g.WriteRefused) as ctx:
            g.guarded_write(self.target(), 'x', expected_job_id='deadbeef',
                            observed_jobs=JOBS)
        self.assertEqual(ctx.exception.reason, g.JOB_UUID_MISMATCH)
        self.assertFalse(self.target().exists())
        self.assertFalse(self.target().parent.exists())

    def test_missing_expected_uuid_refuses(self):
        for bad in ('', None):
            with self.assertRaises(g.WriteRefused) as ctx:
                g.guarded_write(self.target(), 'x', expected_job_id=bad,
                                observed_jobs=JOBS)
            self.assertEqual(ctx.exception.reason, g.JOB_UUID_MISSING)
            self.assertFalse(self.target().exists())

    def test_empty_observation_refuses(self):
        with self.assertRaises(g.WriteRefused) as ctx:
            g.guarded_write(self.target(), 'x', expected_job_id=JOB,
                            observed_jobs=[])
        self.assertEqual(ctx.exception.reason, g.JOB_UUID_MISMATCH)
        self.assertFalse(self.target().exists())

    def test_unknown_recurrence_refuses(self):
        for job in ({'id': JOB}, {'id': JOB, 'recurring': False},
                    {'id': JOB, 'schedule': '  '}):
            with self.assertRaises(g.WriteRefused) as ctx:
                g.guarded_write(self.target(), 'x', expected_job_id=JOB,
                                observed_jobs=[job])
            self.assertEqual(ctx.exception.reason, g.JOB_NOT_RECURRING)
            self.assertFalse(self.target().exists())

    def test_explicit_false_beats_nonempty_schedule(self):
        # Exact shape the verifier named: the record DENIES recurrence while
        # still carrying a live-looking cron string. Must refuse, not land.
        job = {'id': JOB, 'recurring': False, 'schedule': '*/5 * * * *'}
        self.assertFalse(g._recurring(job))
        with self.assertRaises(g.WriteRefused) as ctx:
            g.guarded_write(self.target(), 'x', expected_job_id=JOB,
                            observed_jobs=[job])
        self.assertEqual(ctx.exception.reason, g.JOB_NOT_RECURRING)
        self.assertFalse(self.target().exists())
        receipt = self.dir / 'receipt.json'
        with self.assertRaises(g.WriteRefused):
            g.write_prebuilder_receipt(receipt, expected_job_id=JOB,
                                       observed_jobs=[job])
        self.assertFalse(receipt.exists())

    def test_ambiguous_observation_refuses(self):
        with self.assertRaises(g.WriteRefused) as ctx:
            g.guarded_write(self.target(), 'x', expected_job_id=JOB,
                            observed_jobs=[JOBS[0], dict(JOBS[0])])
        self.assertEqual(ctx.exception.reason, g.JOB_UUID_AMBIGUOUS)
        self.assertFalse(self.target().exists())

    def test_no_case_or_whitespace_normalisation(self):
        for near in (JOB.upper(), JOB + ' ', ' ' + JOB, JOB[:-1]):
            with self.assertRaises(g.WriteRefused):
                g.guarded_write(self.target(), 'x', expected_job_id=near,
                                observed_jobs=JOBS)
            self.assertFalse(self.target().exists())

    def test_refusal_preserves_existing_bytes(self):
        self.target().parent.mkdir(parents=True)
        self.target().write_text('OLD')
        with self.assertRaises(g.WriteRefused):
            g.guarded_write(self.target(), 'NEW', expected_job_id='nope',
                            observed_jobs=JOBS)
        self.assertEqual(self.target().read_text(), 'OLD')

    # --- prebuilder receipt proves the ACTUAL recurring jobID -------------
    def test_receipt_records_actual_job_id_and_prompt_digest(self):
        body = b'prebuilder loop prompt body'
        receipt = g.write_prebuilder_receipt(
            self.dir / 'receipt.json', expected_job_id=JOB,
            observed_jobs=JOBS, prompt_body=body)
        on_disk = json.loads((self.dir / 'receipt.json').read_text())
        self.assertEqual(on_disk, receipt)
        self.assertTrue(receipt['job_uuid_proven'])
        self.assertEqual(receipt['actual_recurring_job_id'], JOB)
        self.assertEqual(receipt['prompt_body_bytes'], len(body))
        self.assertEqual(receipt['observation_count'], 1)
        self.assertIsNone(receipt['refusal'])

    def test_receipt_refuses_unproven_uuid_and_writes_no_file(self):
        for expected, jobs in (('deadbeef', JOBS), ('', JOBS), (JOB, [])):
            path = self.dir / 'receipt.json'
            with self.assertRaises(g.WriteRefused):
                g.write_prebuilder_receipt(path, expected_job_id=expected,
                                           observed_jobs=jobs)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
