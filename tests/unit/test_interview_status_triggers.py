"""Item 09 guard: interview STATUS questions have triggers, a read order, and a
prohibition on port-probe inference.

WHAT THIS GUARD IS NOT. It asserts that the words and structure exist in the
skill docs — nothing more. It cannot and does not prove that any agent actually
read INSTRUCTIONS.md before answering a client, and it proves nothing about a
live box. It only stops the next edit from silently deleting the trigger list,
the read-order rule or the prohibition, which is how this failure shipped: the
skill's triggers covered building and scaffolding but not "can she start".
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / '23-ai-workforce-blueprint/SKILL.md'
INSTRUCTIONS = ROOT / '23-ai-workforce-blueprint/INSTRUCTIONS.md'
SKILL32 = ROOT / '32-command-center-setup/SKILL.md'
# The guide lives in the separate fleet-onboarding repo, so its Step 4.4 and
# sign-off lines are verified by that repo's own PR, not from here.

STATUS_TRIGGERS = [
    'can she start the interview',
    'can <client> start the interview',
    'where is the interview link',
    'what is the link',
    'is the link working',
    'my interview link expired',
    'resume my interview',
    'can the interview start',
]


class InterviewStatusTriggerGuard(unittest.TestCase):
    def test_status_triggers_are_present(self):
        text = SKILL.read_text()
        for trigger in STATUS_TRIGGERS:
            with self.subTest(trigger=trigger):
                self.assertIn(f'- "{trigger}"', text)

    def test_build_triggers_were_not_removed(self):
        # A trigger list that only covers status questions would break builds.
        text = SKILL.read_text()
        for trigger in ('build my AI workforce', 'set up my departments', 'hire my AI team'):
            self.assertIn(f'- "{trigger}"', text)

    def test_read_order_is_stated_in_both_documents(self):
        skill = SKILL.read_text()
        self.assertIn('Interview STATUS questions use a shorter authoritative read order', skill)
        self.assertIn('SKILL.md then the authoritative INSTRUCTIONS.md', skill)
        # An actual build still requires the full six reads.
        self.assertIn('all six reads', skill)
        instructions = INSTRUCTIONS.read_text()
        self.assertIn('Authoritative Read Order and Prohibited Inference', instructions)
        self.assertIn('read SKILL.md first', instructions)

    def test_port_probe_inference_is_forbidden(self):
        for path in (SKILL, INSTRUCTIONS):
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertRegex(text, r'[Nn]ever derive .*port probe|Never derive "no interview link"')

    def test_three_facts_and_four_facts_are_named_separately(self):
        for path in (SKILL, INSTRUCTIONS):
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertIn('Stable public bookmark', text.replace('stable public bookmark', 'Stable public bookmark'))
                self.assertIn('privately minted', text.lower())
                self.assertIn('verified delivery', text.lower())
                self.assertIn('four', text)

    def test_down_application_is_classified_as_a_deployment_fault(self):
        for path in (SKILL, INSTRUCTIONS):
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertIn('Command Center deployment fault', text)
                self.assertIn('9Router', text)
                # and it must say what a start-time refusal actually is
                self.assertIn('exit 78', text)

    def test_skill32_references_the_startability_gate(self):
        text = SKILL32.read_text()
        self.assertIn('--startability --no-send', text)
        self.assertIn('ledger key `4.4`', text)
        self.assertIn('historic ledger flag is never accepted as proof', text)

    def test_guard_never_claims_it_proves_a_read(self):
        # The guard's own honesty clause: a text check is not proof an agent read.
        doc = Path(__file__).read_text()
        self.assertIn('cannot and does not prove', doc)


if __name__ == '__main__':
    unittest.main()