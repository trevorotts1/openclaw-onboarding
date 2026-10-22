"""Skill 06 process-identity fault tests (Master Plan v3.0 S19).

Run sequentially, one heavy job at a time:
  python3 -m pytest scripts/tests/test_process_identity.py -q
Covers: PID + start-time + boot identity, a reused PID is provably NOT the
recorded owner (neither alive nor identity-matchable), a live owner's lease
cannot be stolen, a duplicate supervisor cannot start the same batch, and a
dead owner's recovery is fenced by a generation bump.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import swarm_controls as sc

FAKE_START = 'Mon Jan  1 00:00:00 2001'


class IdentityTests(unittest.TestCase):
    def test_self_identity_alive_and_matching(self):
        rec = sc.capture_identity()
        self.assertTrue(sc.identity_alive(rec))
        self.assertTrue(sc.identity_matches(rec, sc.capture_identity()))

    def test_s19_reused_pid_is_not_the_recorded_owner(self):
        rec = sc.capture_identity()
        reused = dict(rec, start_time=FAKE_START)   # same PID, new process
        self.assertFalse(sc.identity_alive(reused),
                         'a reused PID must not read as the live owner')
        self.assertFalse(sc.identity_matches(rec, reused),
                         'a reused PID must never match the recorded owner')
        self.assertFalse(sc.identity_alive(rec['pid']))  # bare PID is not a record

    def test_dead_and_rebooted_records_not_alive(self):
        dead = {'pid': 99999999, 'start_time': FAKE_START,
                'boot_id': sc.boot_identity()}
        self.assertFalse(sc.identity_alive(dead))
        rebooted = dict(sc.capture_identity(),
                        boot_id='boot-999999999')   # another boot
        self.assertFalse(sc.identity_alive(rebooted))


class MergeLockIdentityTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.dir.name) / 'merge-batch-state.json'

    def tearDown(self):
        self.dir.cleanup()

    def _seed_active(self, identity, owner='sup-a', batch='b1', gen=2):
        self.state_path.write_text(json.dumps({
            'owner': owner, 'batch_id': batch, 'generation': gen,
            'status': 'active', 'identity': identity}))

    def test_live_owner_lease_not_stolen(self):
        self._seed_active(sc.capture_identity())
        with self.assertRaises(sc.OwnerAlive):
            sc.MergeLock(self.dir.name).try_acquire('sup-b', 'b1')

    def test_duplicate_supervisor_cannot_start_same_batch(self):
        me = sc.capture_identity()
        self._seed_active(me)
        other = dict(me, pid=me['pid'] + 1)         # a different live process
        with self.assertRaises(sc.OwnerAlive):
            sc.MergeLock(self.dir.name).try_acquire('sup-a', 'b1',
                                                    identity=other)

    def test_s19_stale_owner_recovery_bumps_generation_and_fences(self):
        me = sc.capture_identity()
        stale = dict(me, start_time=FAKE_START)     # PID reused: owner gone
        self._seed_active(stale, gen=2)
        lock = sc.MergeLock(self.dir.name)
        ok, gen = lock.try_acquire('sup-b', 'b1', identity=other_identity())
        self.assertTrue(ok)
        self.assertEqual(gen, 3)                    # new fenced generation
        lock.complete(3)
        with self.assertRaises(sc.StaleGeneration):
            # the old owner (or its PID reuser) can no longer write
            sc.MergeLock(self.dir.name).complete(2)

    def test_restart_same_owner_batch_resumes_same_generation(self):
        self._seed_active(dict(sc.capture_identity(), start_time=FAKE_START),
                          gen=2)
        ok, gen = sc.MergeLock(self.dir.name).try_acquire('sup-a', 'b1')
        self.assertTrue(ok)
        self.assertEqual(gen, 2)                    # resumes, never duplicates


def other_identity():
    return {'pid': 424242, 'start_time': FAKE_START,
            'boot_id': sc.boot_identity()}


if __name__ == '__main__':
    unittest.main()
