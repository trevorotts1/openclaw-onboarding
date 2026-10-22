"""Skill 06 swarm-control fault tests (Master Plan v3.0 C2).

Run sequentially, one heavy job at a time:
  python3 -m pytest scripts/tests/test_swarm_controls.py -q
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import swarm_controls as sc

MODULE = ROOT / 'scripts' / 'lib' / 'swarm_controls.py'


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.ledger = sc.AdmissionLedger(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_agent_cap_4_start_6_max(self):
        ids = [self.ledger.acquire('agent', f'a{i}') for i in range(4)]
        self.assertEqual(len(set(ids)), 4)
        with self.assertRaises(sc.SlotRefused):
            self.ledger.acquire('agent', 'a5')  # 5th refused at start cap
        self.assertEqual(self.ledger.expand_agent_cap(), 6)
        self.ledger.acquire('agent', 'a5')
        self.ledger.acquire('agent', 'a6')
        with self.assertRaises(sc.SlotRefused):
            self.ledger.acquire('agent', 'a7')  # hard max 6
        self.assertEqual(self.ledger.expand_agent_cap(), 6)  # clamped

    def test_one_heavy_job_host_wide(self):
        tok = self.ledger.acquire('heavy', 'job-1')
        with self.assertRaises(sc.SlotRefused):
            self.ledger.acquire('heavy', 'job-2')
        self.ledger.release(tok)
        self.ledger.acquire('heavy', 'job-2')  # after release a new job may start

    def test_single_browser_lease(self):
        self.ledger.acquire('browser', 'lane-x')
        with self.assertRaises(sc.SlotRefused):
            self.ledger.acquire('browser', 'lane-y')

    def test_restart_resumes_not_duplicates(self):
        tok1 = self.ledger.acquire('agent', 'supervisor')
        # restart: fresh object, same persisted state, same owner
        ledger2 = sc.AdmissionLedger(self.dir.name)
        tok2 = ledger2.acquire('agent', 'supervisor')
        self.assertEqual(tok1, tok2)
        self.assertEqual(ledger2.counts()['agent'], 1)

    def test_sweep_stale_frees_slots(self):
        clock = {'t': 1000.0}
        ledger = sc.AdmissionLedger(self.dir.name, now=lambda: clock['t'])
        ledger.acquire('agent', 'dead-worker')
        clock['t'] += 300
        stale = ledger.sweep_stale(max_age_s=120)
        self.assertEqual(len(stale), 1)
        self.assertEqual(ledger.counts()['agent'], 0)


class ChildEnvTests(unittest.TestCase):
    def test_routes_only_children_parent_untouched(self):
        base = {'PATH': '/usr/bin', 'HOME': '/Users/x'}
        before = dict(base)
        env = sc.child_env(base, '/external/run')
        self.assertEqual(base, before)  # parent env never mutated
        self.assertEqual(env['TMPDIR'], '/external/run/tmp')
        self.assertEqual(env['npm_config_cache'], '/external/run/cache/npm')
        self.assertEqual(env['PIP_CACHE_DIR'], '/external/run/cache/pip')
        self.assertEqual(env['PATH'], '/usr/bin')


class HealthCheckTests(unittest.TestCase):
    def test_verdict_shape(self):
        out = sc.health_check('/', tempfile.gettempdir())
        self.assertIn(out['overall'], ('start', 'hold', 'critical'))
        self.assertIn(out['internal_verdict'], ('start', 'hold', 'critical'))
        self.assertIn(out['external_verdict'], ('start', 'hold', 'critical'))
        self.assertEqual(len(out['loadavg']), 3)


class MergeLockTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def _claim(self, owner, batch='batch-1', hold=0.0, barrier=None):
        cmd = [sys.executable, str(MODULE), 'claim-merge',
               '--state-dir', self.dir.name, '--owner', owner,
               '--batch', batch, '--hold', str(hold)]
        if barrier:
            cmd += ['--barrier', barrier]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    def test_two_supervisors_cannot_both_own_lock(self):
        barrier = str(Path(self.dir.name) / 'go')
        procs = [subprocess.Popen(
            [sys.executable, str(MODULE), 'claim-merge',
             '--state-dir', self.dir.name, '--owner', f'sup-{i}',
             '--batch', 'batch-1', '--hold', '2', '--barrier', barrier],
            stdout=subprocess.PIPE, text=True) for i in range(2)]
        Path(barrier).write_text('go')  # both race from the same instant
        outs = [p.communicate(timeout=30)[0].strip() for p in procs]
        owned = [o for o in outs if o.startswith('OWNED')]
        refused = [o for o in outs if o == 'REFUSED']
        self.assertEqual(len(owned), 1, outs)   # exactly one owner
        self.assertEqual(len(refused), 1, outs)

    def test_restart_resumes_batch_no_duplicate(self):
        # first supervisor crashes (exits without complete/release):
        # flock is freed by the kernel, state stays active
        r1 = self._claim('sup', 'batch-1')
        self.assertTrue(r1.stdout.startswith('OWNED'), r1.stdout)
        gen1 = int(r1.stdout.strip().split('=')[1])
        # restart: same owner+batch resumes at the same generation
        r2 = self._claim('sup', 'batch-1')
        self.assertTrue(r2.stdout.startswith('OWNED'), r2.stdout)
        self.assertEqual(int(r2.stdout.strip().split('=')[1]), gen1)

    def test_takeover_fences_stale_writer(self):
        lock = sc.MergeLock(self.dir.name)
        ok_a, gen_a = lock.try_acquire('sup-a', 'batch-1')
        self.assertTrue(ok_a)
        lock.release()
        lock2 = sc.MergeLock(self.dir.name)
        ok, gen_b = lock2.try_acquire('sup-b', 'batch-1')  # takeover
        self.assertTrue(ok)
        self.assertGreater(gen_b, gen_a)
        lock2.complete(gen_b)  # current owner finishes, releases flock
        with self.assertRaises(sc.StaleGeneration):
            sc.MergeLock(self.dir.name).complete(gen_a)  # stale fenced


if __name__ == '__main__':
    unittest.main()
