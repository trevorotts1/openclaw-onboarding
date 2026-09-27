#!/usr/bin/env python3
"""Offline checks: python3 tests/unit/test_workflow_slots.py. No model calls."""
from contextlib import closing
import json
import multiprocessing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared-utils'))
from workflow_slots import execute


def reservation(workflow, agent):
    return dict(action='reserve', coordinator='coordinator', workflow_id=workflow, reservation_id=agent,
                role='builder', route='opus-chain', parent='coordinator', unit='D32', lease_seconds=3600)


def contender(database, command, barrier, queue):
    barrier.wait(timeout=20)
    try:
        execute(database, {'coordinator': 'coordinator', **command})
        queue.put('accepted')
    except ValueError as exc:
        queue.put(str(exc))
    except Exception as exc:
        queue.put('unexpected:' + repr(exc))


class SlotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / 'slots.sqlite')
        execute(self.database, dict(action='init', coordinator='coordinator'))

    def call(self, action, **kwargs):
        return execute(self.database, dict(action=action, coordinator='coordinator', **kwargs))

    def race(self, commands):
        ctx = multiprocessing.get_context('spawn')
        barrier, queue = ctx.Barrier(len(commands)), ctx.Queue()
        workers = [ctx.Process(target=contender, args=(self.database, c, barrier, queue)) for c in commands]
        for worker in workers:
            worker.start()
        try:
            results = [queue.get(timeout=30) for _ in workers]
            for worker in workers:
                worker.join(timeout=10)
                self.assertEqual(worker.exitcode, 0)
            self.assertFalse(any(r.startswith('unexpected:') for r in results), results)
            return results
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join()
            queue.close()
            queue.join_thread()

    def test_simultaneous_tenth_eleventh_workflow(self):
        for i in range(9):
            self.call('open', workflow_id=f'w{i}')
        results = self.race([dict(action='open', workflow_id=f'last{i}') for i in range(4)])
        self.assertEqual(results.count('accepted'), 1)
        self.assertEqual(results.count('workflow limit'), 3)
        self.assertEqual(self.call('snapshot')['active_workflows'], 10)

    def test_simultaneous_tenth_eleventh_slot(self):
        self.call('open', workflow_id='w')
        for i in range(9):
            execute(self.database, reservation('w', f'a{i}'))
        results = self.race([reservation('w', f'last{i}') for i in range(4)])
        self.assertEqual(results.count('accepted'), 1)
        self.assertEqual(results.count('workflow agent limit'), 3)
        self.assertEqual(self.call('snapshot')['reserved_or_live'], 10)

    def test_simultaneous_hundredth_hundred_first_slot(self):
        for w in range(10):
            self.call('open', workflow_id=f'w{w}')
            for a in range(10 if w < 9 else 9):
                execute(self.database, reservation(f'w{w}', f'a{w}-{a}'))
        results = self.race([reservation('w9', f'last{i}') for i in range(4)])
        self.assertEqual(results.count('accepted'), 1)
        self.assertEqual(results.count('global agent limit'), 3)
        self.assertEqual(self.call('snapshot')['reserved_or_live'], 100)

    def test_release_fence_restart_expiry_and_reuse(self):
        self.call('open', workflow_id='w')
        row = execute(self.database, reservation('w', 'a'))
        key = dict(reservation_id='a', fence=row['fence'])
        with self.assertRaisesRegex(ValueError, 'still has'):
            self.call('close', workflow_id='w')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.call('start', reservation_id='a', fence='wrong', session_ref='session', agent_id='actual-agent')
        self.call('start', **key, session_ref='session', agent_id='actual-agent')
        with self.assertRaisesRegex(ValueError, 'already started'):
            self.call('start', **key, session_ref='session', agent_id='actual-agent')
        with closing(sqlite3.connect(self.database, isolation_level=None)) as db:
            db.execute('UPDATE slots SET expires=0 WHERE reservation_id=?', ('a',))
        # New connection simulates restart: no automatic expiry reclamation.
        with self.assertRaisesRegex(ValueError, 'lease expired'):
            self.call('check', **key)
        self.assertEqual(self.call('snapshot')['reserved_or_live'], 1)
        for evidence in ({}, dict(verified=True, kind='session_terminal', reference='receipt', session_ref='other', status='completed')):
            with self.assertRaises(ValueError):
                self.call('release', **key, evidence=evidence)
        released = self.call('release', **key, evidence=dict(verified=True, kind='session_terminal', reference='receipt', session_ref='session', status='completed'))
        self.assertNotEqual(released['fence'], row['fence'])
        self.assertEqual(self.call('snapshot')['reserved_or_live'], 0)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.call('check', **key)
        with self.assertRaisesRegex(ValueError, 'already reserved'):
            execute(self.database, reservation('w', 'a'))
        self.call('close', workflow_id='w')
        with self.assertRaisesRegex(ValueError, 'retired'):
            self.call('open', workflow_id='w')
        self.call('open', workflow_id='replacement')

    def test_route_validation_and_duplicate_race(self):
        self.call('open', workflow_id='w')
        for role, route in [('builder', 'Opus-chain'), ('reviewer', 'opus-chain'), ('merge_operator', 'claude-haiku'), ('unknown', 'opus-chain')]:
            with self.assertRaisesRegex(ValueError, 'role/route mismatch'):
                execute(self.database, {**reservation('w', 'a'), 'role': role, 'route': route})
        for seconds in [True, 0, -1, float('nan'), float('inf'), '3600']:
            with self.assertRaisesRegex(ValueError, 'lease_seconds'):
                execute(self.database, {**reservation('w', 'a'), 'lease_seconds': seconds})
        results = self.race([reservation('w', 'a')] * 4)
        self.assertEqual(results.count('accepted'), 1)
        self.assertEqual(self.call('snapshot')['reserved_or_live'], 1)
        row = self.call('snapshot')['slots'][0]
        self.call('release', reservation_id='a', fence=row['fence'], evidence=dict(verified=True, kind='launch_cancelled', reference='not submitted'))
        for role, route in [('reviewer', 'sonnet-chain'), ('merge_operator', 'haiku-chain')]:
            execute(self.database, {**reservation('w', role), 'role': role, 'route': route})

    def test_coordinator_binding_and_renewal(self):
        self.call('open', workflow_id='w')
        with self.assertRaisesRegex(ValueError, 'trusted coordinator'):
            execute(self.database, dict(action='open', coordinator='worker', workflow_id='other'))
        with self.assertRaisesRegex(ValueError, 'nested'):
            execute(self.database, {**reservation('w', 'r'), 'parent': 'worker'})
        row = execute(self.database, reservation('w', 'r'))
        self.assertIsNone(row['agent_id'])
        key = dict(reservation_id='r', fence=row['fence'])
        bound = self.call('start', **key, agent_id='harness-generated', session_ref='session')
        self.assertEqual(bound['agent_id'], 'harness-generated')
        renewed = self.call('renew', **key, lease_seconds=7200)
        self.assertGreater(renewed['expires'], row['expires'])
        self.assertEqual(renewed['fence'], row['fence'])
        with closing(sqlite3.connect(self.database, isolation_level=None)) as db:
            db.execute('UPDATE slots SET expires=0')
        with self.assertRaisesRegex(ValueError, 'lease expired'):
            self.call('renew', **key, lease_seconds=7200)
        self.assertEqual(self.call('snapshot')['reserved_or_live'], 1)

    def test_json_cli(self):
        argv = [sys.executable, str(ROOT / 'shared-utils/workflow_slots.py'), self.database]
        for payload, code in [('[]', 2), ('not json', 2), ('{"action":"snapshot","extra":true}', 2), ('{"action":"snapshot","coordinator":"coordinator"}', 0)]:
            out = subprocess.run(argv, input=payload, text=True, capture_output=True, timeout=10)
            self.assertEqual(out.returncode, code, out.stderr)
            self.assertEqual(json.loads(out.stdout)['ok'], code == 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
