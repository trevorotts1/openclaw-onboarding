"""Skill 06 batch-integration fault tests (Master Plan v3.0 C3).

Run sequentially, one heavy job at a time:
  python3 -m pytest scripts/tests/test_batch_state.py -q
Covers: one active batch latch (S05-style), tick coalescing (S04),
immutable candidate freeze with tests+QC on exact heads (S06, S07),
MERGED_VERIFIED gate (S08, S10, S11), MERGE_STATUS_UNKNOWN stays active.
"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts' / 'lib'))
import batch_state as bs

SHA_A = 'a' * 40
SHA_B = 'b' * 40
SHA_C = 'c' * 40


def unit(name, head_sha, source_sha=None, qc_verdict='pass', test_verdict='pass'):
    return {'name': name,
            'source_sha': source_sha or (name.encode().hex()[:40].ljust(40, '0')),
            'files': [f'{name}.py'],
            'tests': [{'suite': f'test_{name}', 'head_sha': head_sha,
                       'verdict': test_verdict}],
            'qc': {'reviewer': 'glm-5.3', 'head_sha': head_sha,
                   'verdict': qc_verdict}}


class LatchTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.latch = bs.BatchLatch(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_one_active_batch_across_ci_waits(self):
        self.latch.start_batch('b1')
        with self.assertRaises(bs.LatchRefused):
            self.latch.start_batch('b2')     # first refusal
        with self.assertRaises(bs.LatchRefused):
            self.latch.start_batch('b2')     # still active across CI waits
        self.assertEqual(self.latch.status()['active_batch_id'], 'b1')

    def test_s05_two_supervisors_cannot_both_start_batches(self):
        barrier = threading.Barrier(2)
        results = []

        def race(name):
            barrier.wait()
            try:
                self.latch.start_batch(name)
                results.append(('started', name))
            except bs.LatchRefused:
                results.append(('refused', name))

        threads = [threading.Thread(target=race, args=(f'b{i}',))
                   for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        started = [n for outcome, n in results if outcome == 'started']
        self.assertEqual(len(started), 1, results)   # exactly one batch

    def test_timer_ticks_coalesce_to_one_request(self):
        self.latch.start_batch('b1')
        for _ in range(5):
            self.latch.tick()
        status = self.latch.status()
        self.assertTrue(status['next_batch_requested'])   # single flag
        self.assertEqual(status['tick_count'], 5)         # ticks counted
        self.assertTrue(self.latch.finish_batch('b1'))    # drained once
        self.assertFalse(self.latch.status()['next_batch_requested'])

    def test_tick_without_active_batch_is_noop(self):
        self.assertFalse(self.latch.tick())
        self.assertFalse(self.latch.status()['next_batch_requested'])


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def test_ladder_forward_only_with_annotations(self):
        rec = bs.BatchRecord(self.dir.name, 'b1')
        rec.transition('FROZEN')
        rec.transition('FROZEN', 'annotation')     # real receipts annotate
        rec.transition('ASSEMBLING')
        self.assertEqual(rec.state, 'ASSEMBLING')
        with self.assertRaises(bs.StateViolation):
            rec.transition('COLLECTING')           # never backward

    def test_merge_status_unknown_stays_active(self):
        rec = bs.BatchRecord(self.dir.name, 'b2')
        for s in ('FROZEN', 'PUSHED'):
            rec.transition(s)
        rec.transition(bs.MERGE_STATUS_UNKNOWN, 'merge timeout')
        self.assertTrue(rec.is_active())           # latch stays set
        rec.transition('MERGE_VERIFICATION', 'reconciled')
        self.assertTrue(rec.is_active())
        rec.transition('CLEANUP')
        rec.transition('CLOSED')
        self.assertFalse(rec.is_active())

    def test_failed_preserved_needs_recovery_and_evidence(self):
        rec = bs.BatchRecord(self.dir.name, 'b3')
        rec.transition('FROZEN')
        with self.assertRaises(bs.StateViolation):
            rec.fail('boom', recovery_ref='', evidence_paths=['e.txt'])
        with self.assertRaises(bs.StateViolation):
            rec.fail('boom', recovery_ref='refs/recovery/b3', evidence_paths=[])
        self.assertEqual(rec.fail('boom', 'refs/recovery/b3', ['e.txt']),
                         bs.FAILED_PRESERVED)
        self.assertFalse(rec.is_active())
        with self.assertRaises(bs.StateViolation):
            rec.transition('CLOSED')               # terminal

    def test_unknown_state_rejected(self):
        rec = bs.BatchRecord(self.dir.name, 'b4')
        with self.assertRaises(bs.StateViolation):
            rec.transition('AWAITING_CANDIDATE_REVISION')  # not in the law


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cand = bs.CandidateFreeze(self.dir.name, 'b1')

    def tearDown(self):
        self.dir.cleanup()

    def test_freeze_requires_tests_qc_on_exact_heads(self):
        with self.assertRaises(bs.StateViolation):
            self.cand.freeze(SHA_A, SHA_A,
                             [unit('u1', head_sha=SHA_B)])   # QC at old head
        with self.assertRaises(bs.StateViolation):
            self.cand.freeze(SHA_A, SHA_A,
                             [unit('u1', SHA_A, qc_verdict='fail')])
        self.cand.freeze(SHA_A, SHA_A, [unit('u1', SHA_A)])
        ok, problems = self.cand.verify()
        self.assertTrue(ok, problems)
        self.assertEqual(self.cand.candidate_sha, SHA_A)

    def test_s06_post_freeze_commit_goes_to_next_batch(self):
        self.cand.freeze(SHA_A, SHA_A, [unit('u1', SHA_A)])
        with self.assertRaises(bs.StaleCandidate):
            self.cand.freeze(SHA_A, SHA_A, [unit('u1', SHA_A),
                                            unit('u2', SHA_A)])
        self.cand.stage_after_freeze(unit('u2', SHA_A))
        self.assertEqual([u['name'] for u in self.cand.next_batch_units],
                         ['u2'])
        self.assertEqual([u['name'] for u in self.cand._read()['units']],
                         ['u1'])                    # frozen set untouched

    def test_s07_checks_on_old_sha_never_accepted(self):
        self.cand.freeze(SHA_A, SHA_A, [unit('u1', SHA_A)])
        self.cand.record_check(SHA_A, 'ci', 'pass')
        self.assertTrue(self.cand.checks_green())
        self.cand.revise(SHA_B, [unit('u1', SHA_B)])   # repair -> new head
        self.assertFalse(self.cand.checks_green())     # old-SHA green ignored
        self.cand.record_check(SHA_A, 'ci', 'fail')    # stale fail ignored too
        self.assertFalse(self.cand.checks_green())
        self.assertEqual(self.cand.accepted_checks(), [])
        self.cand.record_check(SHA_B, 'ci', 'pass')
        self.assertTrue(self.cand.checks_green())
        # old revision kept as the recovery mapping (plan 8.4)
        self.assertEqual(self.cand._read()['revisions'][0]['candidate_sha'],
                         SHA_A)


class MergeGateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.mt = bs.MergeTransaction(self.dir.name, 'b1')

    def tearDown(self):
        self.dir.cleanup()

    def _landed(self):
        self.mt.record_candidate(SHA_A, pr_number=2415)
        self.mt.request_merge()
        return self.mt.reconcile({'merged': True, 'closed': True,
                                  'merge_commit': SHA_C, 'method': 'merge'})

    def test_merged_verified_needs_all_three_gates(self):
        self.assertEqual(self._landed(), 'MERGED')
        ok, reasons = self.mt.merged_verified()
        self.assertFalse(ok, reasons)                # no fetch, no smoke
        self.mt.record_target_fetch(SHA_C, ancestry_ok=True,
                                    content_matches=True)
        ok, _ = self.mt.merged_verified()
        self.assertFalse(ok)                         # still no smoke
        self.mt.record_post_merge_smoke('fail')
        ok, _ = self.mt.merged_verified()
        self.assertFalse(ok)                         # smoke must pass
        self.mt.record_post_merge_smoke('pass')
        ok, _ = self.mt.merged_verified()
        self.assertTrue(ok)
        self.assertEqual(self.mt.mark_merged_verified(), 'MERGED_VERIFIED')

    def test_s08_timeout_reconciled_never_blind_repeated(self):
        self.mt.record_candidate(SHA_A)
        self.mt.request_merge()
        with self.assertRaises(bs.MergeBlocked):
            self.mt.request_merge()                  # already open
        self.mt.merge_timeout()
        with self.assertRaises(bs.MergeBlocked):
            self.mt.request_merge()                  # S08: reconcile first
        self.assertEqual(self.mt.reconcile({'merged': True, 'closed': True,
                                            'merge_commit': SHA_C,
                                            'method': 'squash'}), 'MERGED')
        self.mt.request_merge()                      # resolved -> allowed

    def test_s10_closed_unmerged_is_not_landed(self):
        self.mt.record_candidate(SHA_A)
        self.mt.request_merge()
        self.assertEqual(self.mt.reconcile({'merged': False, 'closed': True,
                                            'merge_commit': None}),
                         'CLOSED_UNMERGED')
        ok, reasons = self.mt.merged_verified()
        self.assertFalse(ok, reasons)
        with self.assertRaises(bs.MergeBlocked):
            self.mt.mark_merged_verified()

    def test_s11_ancestry_gap_preserves_recovery_ref(self):
        self.mt.record_candidate(SHA_A)
        self.mt.request_merge()
        self.mt.reconcile({'merged': True, 'closed': True,
                           'merge_commit': SHA_C, 'method': 'squash'})
        with self.assertRaises(bs.MergeBlocked):
            # squash/rebase: ancestry gap without a recovery ref
            self.mt.record_target_fetch(SHA_C, ancestry_ok=False,
                                        content_matches=True)
        ref = 'refs/skill06/recovery/b1'
        self.mt.record_target_fetch(SHA_C, ancestry_ok=False,
                                    content_matches=True, recovery_ref=ref)
        self.mt.record_post_merge_smoke('pass')
        ok, reasons = self.mt.merged_verified()
        self.assertTrue(ok, reasons)
        self.assertEqual(self.mt._read()['target_fetch']['recovery_ref'], ref)


if __name__ == '__main__':
    unittest.main()
