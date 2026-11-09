#!/usr/bin/env python3
"""tests/unit/shared-readiness-projection.test.py — T-40 acceptance suite.

Clause (verbatim, live-ledgers/build.json T-40 `acceptance`):
  "Affected rebind/disconnect/upgrade proof invalidation, installed/running/live distinct."

Rows proven here (see lanes/PBB-561-lane/BUILD.md for the decomposition):
  1-3  installed / running / live are three distinct states (slots, disjoint
       vocabularies, all 8 combinations distinguishable)
  4    rebind invalidates the prior proof   (issue -> invalidate -> re-check)
  5    disconnect invalidates the prior proof
  6    upgrade invalidates the prior proof
  7    only AFFECTED proofs invalidate — another surface's proof stays valid
  8    inverse control: no event -> the prior proof STILL validates
  9    reachability lock: production call site exists (non-test file)
  10   CI lock: a workflow runs THIS suite by explicit file path

Run: python3 tests/unit/shared-readiness-projection.test.py   (rc 0 = all pass)
"""
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'shared-utils'))
import shared_readiness  # noqa: E402

SURFACE = 'command-center.startability'


def issue(binding='host-a', version='build-1', live=True, prior=None):
    return shared_readiness.project(
        SURFACE, binding, version,
        installed=True, running=True, live=live, prior=prior)


class DistinctStates(unittest.TestCase):
    def test_row1_2_3_three_slots_disjoint_vocabularies(self):
        p = issue()
        self.assertEqual(set(p['states']), {'installed', 'running', 'live'})
        vocabs = [set(v) for v in shared_readiness._STATE_VOCAB.values()]
        for i in range(3):
            for j in range(i + 1, 3):
                self.assertFalse(vocabs[i] & vocabs[j],
                                 'state vocabularies overlap: collapse possible')

    def test_row1_2_3_all_eight_combinations_distinct(self):
        seen = set()
        for inst in (True, False):
            for run in (True, False):
                for lv in (True, False):
                    p = shared_readiness.project(
                        SURFACE, 'host-a', 'build-1',
                        installed=inst, running=run, live=lv)
                    seen.add(json.dumps(p['states'], sort_keys=True))
        self.assertEqual(len(seen), 8, 'two of the three states collapsed')

    def test_row1_2_3_no_boolean_ready_no_single_string(self):
        p = issue()
        self.assertNotIn('ready', p['states'])
        self.assertNotIsInstance(p['states'], str)
        for slot, token in p['states'].items():
            self.assertIn(token, shared_readiness._STATE_VOCAB[slot])


class ProofInvalidation(unittest.TestCase):
    def _roundtrip(self, mutate):
        proof = issue()
        self.assertTrue(shared_readiness.proof_valid(proof, issue(prior=proof)),
                        'control: unchanged surface must stay valid')
        fresh = mutate(proof)
        self.assertFalse(shared_readiness.proof_valid(proof, fresh),
                         'stale proof still reads valid after the event')
        self.assertTrue(shared_readiness.proof_valid(fresh, fresh),
                        'the NEW proof must validate against itself')

    def test_row4_rebind_invalidates(self):
        def rebind(proof):
            p = issue(binding='host-b', prior=proof)
            self.assertIn('rebind', p['events'])
            return p
        self._roundtrip(rebind)

    def test_row5_disconnect_invalidates(self):
        def disconnect(proof):
            p = issue(live=False, prior=proof)
            self.assertIn('disconnect', p['events'])
            return p
        self._roundtrip(disconnect)

    def test_row6_upgrade_invalidates(self):
        def upgrade(proof):
            p = issue(version='build-2', prior=proof)
            self.assertIn('upgrade', p['events'])
            return p
        self._roundtrip(upgrade)

    def test_row7_only_affected_surface_invalidates(self):
        other = shared_readiness.project('other.surface', 'host-x', 'build-9',
                                         True, True, True)
        self.assertTrue(shared_readiness.proof_valid(other, other))
        affected = issue()
        affected_now = issue(binding='host-b', prior=affected)  # event on SURFACE only
        self.assertFalse(shared_readiness.proof_valid(affected, affected_now),
                         'the AFFECTED surface proof must be invalidated')
        other_now = shared_readiness.project('other.surface', 'host-x', 'build-9',
                                             True, True, True, prior=other)
        self.assertTrue(shared_readiness.proof_valid(other, other_now),
                        'unrelated surface proof must be unaffected')

    def test_row8_inverse_control_no_event_stays_valid(self):
        proof = issue()
        again = issue(prior=proof)
        self.assertEqual(again['events'], [])
        self.assertTrue(shared_readiness.proof_valid(proof, again))


class WiringLocks(unittest.TestCase):
    def test_row9_production_call_site_present(self):
        src = (REPO / '32-command-center-setup/scripts/verify-tenant-readiness.py').read_text()
        self.assertIn('import shared_readiness', src)
        self.assertIn('shared_readiness.project(', src)
        self.assertIn('shared_readiness.proof_valid(', src)

    def test_row10_ci_workflow_runs_this_suite_by_path(self):
        suite_path = 'tests/unit/shared-readiness-projection.test.py'
        hits = []
        for wf in (REPO / '.github/workflows').glob('*.yml'):
            if suite_path in wf.read_text():
                hits.append(wf.name)
        self.assertTrue(hits, 'no workflow names this suite by explicit path')
        self.assertIn('shared-readiness-projection-guard.yml', hits)


if __name__ == '__main__':
    unittest.main(verbosity=2)
