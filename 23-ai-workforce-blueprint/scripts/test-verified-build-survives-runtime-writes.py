"""A verified build stays verified when the workforce writes its own memory.

Runtime writes (memory files, a reconcile timestamp, a late interview progress
stamp) must not un-verify a finished build; a role file or an owner decision
must. Run with: python3 test-verified-build-survives-runtime-writes.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workforce_completion import finalize, REQUIRED_CHECKS
from workforce_state import atomic_write, read, update


class VerifiedBuildSurvivesRuntimeWrites(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / 'state.json'
        self.art = self.root / 'company' / 'departments'
        self.dept = self.art / 'marketing'
        (self.dept / 'roles' / 'head').mkdir(parents=True)
        (self.dept / 'roles' / 'head' / 'how-to.md').write_text('head how-to\n')
        (self.dept / 'MEMORY.md').write_text('day 1\n')
        (self.dept / 'AGENTS.md').write_text('agents\n')
        atomic_write(self.state, {
            'companyId': 'fixture', 'companySlug': 'fixture', 'buildId': 'build-1',
            'interviewComplete': True, 'interviewQc': {'status': 'pass'},
            'interviewCompletedAt': '2026-11-12T00:00:00+00:00',
            'roleLibraryStatus': 'done', 'sopLibraryStatus': 'done',
            'commsAutomationStatus': 'not-applicable',
            'departments': [{'slug': 'marketing', 'status': 'done'}],
            'canonicalReconciliation': {
                'reconciledAt': '2026-11-12T00:00:00+00:00',
                'decisions': {'marketing': {'decision': 'yes', 'decidedBy': 'owner'}},
                'chosenDepartments': {'slugs': ['marketing']},
                'mergeDecisions': {},
            },
        })

    def tearDown(self):
        self.temp.cleanup()

    def finalize_with_checks(self):
        return finalize(self.state, {name: 0 for name in REQUIRED_CHECKS}, self.art)

    def verified(self):
        return read(self.state)['completionVerification']['status'] == 'verified'

    def unmet(self):
        return read(self.state)['completionVerification']['unmetRequirements']

    def test_verified_build_survives_runtime_writes(self):
        self.assertTrue(self.finalize_with_checks())
        self.assertTrue(self.verified())

        with (self.dept / 'MEMORY.md').open('a') as handle:
            handle.write('second line written by the workforce\n')
        (self.dept / 'AGENTS.md').write_text('agents, rewritten by the workforce\n')
        update(self.state, lambda s: s['canonicalReconciliation'].update(
            reconciledAt='2026-11-12T06:30:00+00:00'))
        update(self.state, lambda s: s.update(
            interviewProgress={'lastQuestionAt': '2026-11-12T06:31:00+00:00',
                               'lastQuestionNumber': 31}))

        self.assertTrue(finalize(self.state), self.unmet())
        self.assertTrue(self.verified())

    def test_changed_role_file_unverifies(self):
        self.assertTrue(self.finalize_with_checks())
        (self.dept / 'roles' / 'head' / 'how-to.md').write_text('head how-to, edited later\n')
        self.assertFalse(finalize(self.state))
        self.assertIn('changed-or-missing-artifacts', self.unmet())

    def test_changed_decision_unverifies(self):
        self.assertTrue(self.finalize_with_checks())
        (self.dept / 'roles' / 'head' / 'how-to.md').write_text('head how-to, edited later\n')
        self.assertTrue(self.finalize_with_checks())
        update(self.state, lambda s: s['canonicalReconciliation']['decisions']['marketing'].update(
            decision='no'))
        self.assertFalse(finalize(self.state))
        self.assertIn('changed-inputs', self.unmet())


if __name__ == '__main__':
    unittest.main()
