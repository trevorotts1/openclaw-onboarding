#!/usr/bin/env python3
"""Regression tests for playbook grammar, structural hashing, and content gates."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import playbook_engine as engine


BASE = """# Workflow: Example

persona: house-standard
model-tier: realtime-standard

declares
tools-used: update_tags
exits-used: done
fields-used: contact.email
tags-used: ZHC-discovery-booked (applies), webinar-registered (reads)

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
example: "Agent: What brings you here?"

Exit rules
exit-when-tag: done, action: end

## On success
Apply success tag.
Confirm completion.

## On escalation
Escalate to operator.
"""


COMPLETE = """# Workflow: Complete exemplar

persona: house-standard
model-tier: realtime-standard

declares
tools-used: update_tags, reference_documents
exits-used: done
fields-used: contact.email
tags-used: ZHC-discovery-booked (applies), webinar-registered (reads)

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
example: "Agent: What brings you here?"
Ask one question at a time.

Exit rules
exit-when-tag: done, action: end

## On success
Apply success tag.
Confirm completion.

## On escalation
Escalate to operator.

## Objection Library

| Objection | Approved response | Never say |
|---|---|---|
| Objection one | Acknowledge concern and ask a question. | Never dismiss concern. |
| Objection two | Clarify the expected outcome. | Never pressure customer. |
| Objection three | Explain the relevant benefit. | Never invent benefits. |
| Objection four | Answer with verified facts. | Never guess facts. |
| Objection five | Offer an appropriate next step. | Never force a decision. |

## Conversational KPIs

- Booking conversion rate: target at least 20%.
- Response quality: target at least 90% pass rate.

## Golden Transcript

Customer: I am interested but unsure.
Agent: What is your main concern?
Customer: I am worried about the cost.
Agent: I can explain the options and answer questions.
Customer: That would help.
Agent: Which option fits your needs best?
Customer: Tuesday works for me.
Agent: You're booked for Tuesday at 10. I'll send the confirmation now.

## Never say

- guaranteed results
"""


MINIMAL = """# Workflow: Minimal

### Phase 1 - Qualify
tools: update_tags
Ask about needs.

## On success
Finish.

## On escalation
Escalate to operator.

## Objection Library

## Conversational KPIs

## Golden Transcript

## Never say
"""


def objection_fixture(data_rows):
    rows = [
        "| Customer objection | Approved response | Never say |",
        "|---|---|---|",
    ]
    rows.extend(
        "| %s | Acknowledge and clarify. | Placeholder-free response. |" % objection
        for objection in data_rows
    )
    return """# Workflow: Objection table test

persona: house-standard
model-tier: realtime-standard

declares
tools-used: update_tags, reference_documents
exits-used: done
fields-used: contact.email
tags-used: ZHC-test (applies)

## What the agent does

### Phase 1 - Qualify
tools: update_tags, reference_documents
example: "Agent: What would help you decide?"
Ask one question at a time.

Exit rules
exit-when-tag: done, action: end

## On success
Apply success tag.
Confirm completion.

## On escalation
Escalate to operator.

## Objection Library

%s

## Conversational KPIs

- Booking conversion rate: target at least 20%%.

## Golden Transcript

Customer: I am interested but unsure.
Agent: What is your main concern?
Customer: I am worried about the cost.
Agent: I can explain the options and answer questions.
Customer: Tuesday works for me.
Agent: You're booked. I'll send the confirmation now.

## Never say

- guaranteed results
""" % "\n".join(rows)


class TestTagsUsed(unittest.TestCase):
    def test_tags_preserved_verbatim(self):
        parsed = engine.parse_playbook(BASE)
        self.assertEqual(
            parsed["declares"]["tags-used"],
            ["ZHC-discovery-booked (applies)", "webinar-registered (reads)"],
        )

    def test_parse_tag_entry(self):
        self.assertEqual(engine.parse_tag_entry("ZHC-x (applies)"), ("ZHC-x", "applies"))
        self.assertEqual(engine.parse_tag_entry("garbage"), (None, None))

    def test_malformed_tag_entry_is_defect(self):
        parsed = engine.parse_playbook(
            BASE.replace("webinar-registered (reads)", "garbage")
        )
        self.assertTrue(any(
            "tags-used entry" in defect
            for defect in engine.validate_playbook(parsed)
        ))


class TestStructureHash(unittest.TestCase):
    def test_escalation_changes_hash(self):
        first = BASE.replace(
            "Escalate to operator.", "Escalate to operator immediately."
        )
        second = BASE.replace(
            "Escalate to operator.", "Escalate to supervisor."
        )
        self.assertNotEqual(
            engine.structure_hash(engine.parse_playbook(first)),
            engine.structure_hash(engine.parse_playbook(second)),
        )

    def test_on_success_action_changes_hash(self):
        first = BASE
        second = BASE.replace("Confirm completion.", "Send completion summary.")
        self.assertNotEqual(
            engine.structure_hash(engine.parse_playbook(first)),
            engine.structure_hash(engine.parse_playbook(second)),
        )

    def test_identical_playbooks_have_identical_hash(self):
        self.assertEqual(
            engine.structure_hash(engine.parse_playbook(BASE)),
            engine.structure_hash(engine.parse_playbook(BASE)),
        )

    def test_fields_used_changes_hash(self):
        changed = BASE.replace(
            "fields-used: contact.email", "fields-used: contact.phone"
        )
        self.assertNotEqual(
            engine.structure_hash(engine.parse_playbook(BASE)),
            engine.structure_hash(engine.parse_playbook(changed)),
        )


class TestPhaseOrdering(unittest.TestCase):
    def test_duplicate_phase_numbers(self):
        fixture = """# Workflow

### Phase 2 - First
tools: update_tags

### Phase 2 - Second
tools: update_tags
"""
        defects = engine.validate_playbook(engine.parse_playbook(fixture))
        self.assertTrue(any("duplicate phase numbers" in d for d in defects))

    def test_phases_out_of_order(self):
        fixture = """# Workflow

### Phase 3 - Third
tools: update_tags

### Phase 2 - Second
tools: update_tags
"""
        defects = engine.validate_playbook(engine.parse_playbook(fixture))
        self.assertTrue(any("out of order" in d for d in defects))


class TestConversationLint(unittest.TestCase):
    def test_minimal_playbook_reports_objections_and_transcript(self):
        defects = engine.conversation_lint(engine.parse_playbook(MINIMAL))
        self.assertTrue(any("objection library has 0 objection(s)" in d for d in defects))
        self.assertTrue(any("no golden transcript" in d for d in defects))

    def test_complete_exemplar_is_clean(self):
        parsed = engine.parse_playbook(COMPLETE)
        self.assertEqual(engine.validate_playbook(parsed), [])
        self.assertEqual(engine.conversation_lint(parsed), [])

    def test_never_say_leakage(self):
        fixture = COMPLETE.replace(
            "Ask one question at a time.",
            "Never promise guaranteed results to customers.",
        )
        defects = engine.conversation_lint(engine.parse_playbook(fixture))
        self.assertTrue(any(
            "never-say phrase 'guaranteed results' also appears in the playbook copy" in d
            for d in defects
        ))

    def test_example_phrasing_parsed(self):
        self.assertEqual(
            engine.parse_playbook(BASE)["phases"][0]["examples"],
            ["Agent: What brings you here?"],
        )

    def test_on_success_actions_parsed(self):
        self.assertEqual(
            engine.parse_playbook(BASE)["on_success_actions"],
            ["Apply success tag.", "Confirm completion."],
        )

    def test_raw_text_retained(self):
        self.assertEqual(engine.parse_playbook(BASE)["_raw_text"], BASE)

    def test_objection_table_five_rows_counts_five(self):
        objections = [
            "Too expensive",
            "Need to think about it",
            "Talk to my spouse or partner",
            "I already have a coach",
            "Just looking right now",
        ]
        self.assertEqual(
            engine.conversation_lint(engine.parse_playbook(objection_fixture(objections))),
            [],
        )

    def test_objection_table_four_rows_is_defect(self):
        objections = [
            "Too expensive",
            "Need to think about it",
            "Talk to my spouse or partner",
            "I already have a coach",
        ]
        defects = engine.conversation_lint(
            engine.parse_playbook(objection_fixture(objections))
        )
        self.assertTrue(any(
            "objection library has 4 objection(s)" in defect
            for defect in defects
        ))

    def test_objection_bullets_do_not_count(self):
        fixture = objection_fixture([
            "Too expensive",
            "Need to think about it",
            "Talk to my spouse or partner",
            "I already have a coach",
            "Just looking right now",
        ])
        start = fixture.index("| Customer objection")
        end = fixture.index("\n## Conversational KPIs")
        bullet_section = "\n".join([
            "- Too expensive",
            "- Need to think about it",
            "- Talk to my spouse or partner",
            "- I already have a coach",
            "- Just looking right now",
        ])
        fixture = fixture[:start] + bullet_section + fixture[end:]
        defects = engine.conversation_lint(engine.parse_playbook(fixture))
        self.assertIn("objection library has 0 objection(s), minimum is 5", defects)
        self.assertFalse(any("no golden transcript" in defect for defect in defects))


if __name__ == "__main__":
    unittest.main(verbosity=2)
