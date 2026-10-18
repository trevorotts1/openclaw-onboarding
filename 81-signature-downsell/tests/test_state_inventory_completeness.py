"""State-inventory completeness meta-test (readiness lane 1820, item 5;
fixture-review gaps G13/G14/G15/G20 residual, local slice).

This is a META-test: it runs no validator and no route. It reads three
artifacts as text and asserts the inventory accounting between them:

1. Every native action state named in the States table of
   references/native-action-states.md is accounted for by at least one
   pin in the OTHER test files of this suite, where a pin is exactly
   one of:
   - BEHAVIOR-pinned: a packet reference-contract event exercising the
     state's behavior appears in a route test. The native state and
     the packet event are different vocabularies; the event mapping
     used here is the one lane review 7 itself recorded as pinned
     (lane-review-fixtures.md: failed, pending and
     requires_customer_action, explicit_decline are pinned locally;
     succeeded is pinned at the route layer):
         succeeded              <- event "payment_succeeded" (verified)
         failed                 <- event "payment_failed"
         pending                <- event "payment_pending"
         requires_customer_action <- event "requires_customer_action"
         explicit_decline       <- event "explicit_decline"
   - REFUSAL-pinned: the state name itself is asserted in
     tests/test_d1_route_law_pins.py to be rejected by the reference
     as an "Unknown event" at D1 (Fix Lane B's honest current-contract
     pin for states the shared interface does not model yet).
   - CR-labeled-skipped: a @unittest.skip in another test file names
     the state's change request (CR-S81-001 for processing,
     CR-S81-002 for unknown_outcome) and fails closed if reached.
2. Every schema UI term in the result-extension schema's
   ui_states_ref description is mapped in the vocabulary-mapping
   section of references/native-action-states.md (Fix Lane A table),
   and every native state appears in that mapping, either as a
   counterpart in the schema-term table or in the second table of
   native states with no schema term.

The expected vocabularies are asserted exactly, so a state or term
added to (or dropped from) either source without updating this
accounting fails here instead of falling silently between the two
lists (the G20 failure mode).

KNOWN HONEST STATE AT AUTHORING (2026-10-16): `idle` has NO pin of
any of the three kinds and no CR-labeled skip. Lane review 7 gap G15
records it verbatim: "idle. NOT PINNED... No local fixture renders or
models the idle state." Its fixture would be a UI-state preview check
at installed proof, not a route test, and no CR covers it. The pin
test below therefore FAILS on `idle` until a real pin exists; it is
not weakened to force a pass. `succeeded` is counted behavior-pinned
at the route layer only: its recording half (transaction/order
relation plus incremental entitlements, gap G16) is a shared
S49/S44 ledger contract and is not claimed here.
Run: python3 -m unittest discover -s tests -v
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATES_DOC = (ROOT / "references" / "native-action-states.md").read_text()
RESULT_SCHEMA = json.loads(
    (ROOT / "schemas" / "downsell-result-extension.schema.json").read_text()
)
TESTS_DIR = ROOT / "tests"
ROUTE_PINS = (TESTS_DIR / "test_d1_route_law_pins.py").read_text()

# Every OTHER test file in the suite, as one text corpus. This file is
# excluded so the meta-test can never pin a state by naming it itself.
OTHER_TESTS = "\n".join(
    p.read_text()
    for p in sorted(TESTS_DIR.glob("test_*.py"))
    if p.name != Path(__file__).name
)

EXPECTED_NATIVE_STATES = {
    "idle",
    "processing",
    "succeeded",
    "failed",
    "pending",
    "requires_customer_action",
    "unknown_outcome",
    "expired_or_unsupported_context",
    "explicit_decline",
    "abandoned",
}
EXPECTED_SCHEMA_TERMS = {
    "default",
    "focus",
    "selected",
    "loading",
    "error",
    "completed",
    "pending",
    "expired-context",
}

BEHAVIOR_EVENT_FOR_STATE = {
    "succeeded": "payment_succeeded",
    "failed": "payment_failed",
    "pending": "payment_pending",
    "requires_customer_action": "requires_customer_action",
    "explicit_decline": "explicit_decline",
}
REFUSAL_STATES = [
    "processing",
    "unknown_outcome",
    "expired_or_unsupported_context",
    "abandoned",
]
CR_SKIP_FOR_STATE = {
    "processing": "CR-S81-001",
    "unknown_outcome": "CR-S81-002",
    "idle": "CR-S81-010",
}


def backticked(cell):
    return re.findall(r"`([^`]+)`", cell)


def table_rows(section_text):
    rows = []
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] and "State" not in cells[0] \
                and "Schema term" not in cells[0] \
                and "Native state" not in cells[0]:
            rows.append(cells)
    return rows


def native_states():
    section = STATES_DOC.split("## States", 1)[1].split("\n## ", 1)[0]
    states = []
    for cells in table_rows(section):
        states.extend(backticked(cells[0]))
    return states


def schema_ui_terms():
    desc = RESULT_SCHEMA["properties"]["ui_states_ref"]["description"]
    listed = desc.split("(", 1)[1].split(")", 1)[0]
    return [t.strip() for t in listed.split(",")]


def mapping_tables():
    section = STATES_DOC.split("## Vocabulary mapping", 1)[1] \
        .split("\n## ", 1)[0]
    first, second = section.split(
        "Native action states with NO schema UI state term:", 1)
    schema_rows = {}
    for cells in table_rows(first):
        terms = backticked(cells[0])
        if terms:
            schema_rows[terms[0]] = backticked(cells[1])
    no_schema = set()
    for cells in table_rows(second):
        no_schema.update(backticked(cells[0]))
    return schema_rows, no_schema


def pin_categories(state):
    cats = set()
    event = BEHAVIOR_EVENT_FOR_STATE.get(state)
    if event and event in OTHER_TESTS:
        cats.add("behavior")
    if state in REFUSAL_STATES and state in ROUTE_PINS \
            and "Unknown event" in ROUTE_PINS:
        cats.add("refusal")
    cr = CR_SKIP_FOR_STATE.get(state)
    if cr and cr in OTHER_TESTS and "unittest.skip" in OTHER_TESTS:
        cats.add("cr-skip")
    return cats


class VocabularyShapeTests(unittest.TestCase):
    def test_native_state_inventory_is_exactly_the_expected_set(self):
        self.assertEqual(set(native_states()), EXPECTED_NATIVE_STATES)

    def test_schema_ui_terms_are_exactly_the_expected_set(self):
        self.assertEqual(set(schema_ui_terms()), EXPECTED_SCHEMA_TERMS)


class MappingCompletenessTests(unittest.TestCase):
    def test_every_schema_ui_term_is_mapped_in_the_reference(self):
        schema_rows, _ = mapping_tables()
        missing = set(schema_ui_terms()) - set(schema_rows)
        self.assertEqual(missing, set(),
                         f"schema UI terms with no mapping row: {missing}")

    def test_every_native_state_appears_in_the_mapping(self):
        schema_rows, no_schema = mapping_tables()
        counterparts = set()
        for tokens in schema_rows.values():
            counterparts.update(tokens)
        accounted = counterparts | no_schema
        missing = set(native_states()) - accounted
        self.assertEqual(
            missing, set(),
            f"native states absent from the vocabulary mapping: {missing}")
        extra = accounted - set(native_states())
        self.assertEqual(
            extra, set(),
            f"mapping names states not in the States table: {extra}")


class PinAccountingTests(unittest.TestCase):
    def test_behavior_pinned_states_have_their_event_in_route_tests(self):
        missing = [s for s, ev in BEHAVIOR_EVENT_FOR_STATE.items()
                   if ev not in OTHER_TESTS]
        self.assertEqual(missing, [],
                         f"behavior states whose event pin vanished: {missing}")

    def test_refusal_pinned_states_are_rejected_as_unknown_events(self):
        self.assertIn("Unknown event", ROUTE_PINS)
        missing = [s for s in REFUSAL_STATES if s not in ROUTE_PINS]
        self.assertEqual(missing, [],
                         f"refusal states no longer pinned: {missing}")

    def test_cr_labeled_skips_name_their_change_requests(self):
        for state, cr in CR_SKIP_FOR_STATE.items():
            self.assertIn(cr, OTHER_TESTS,
                          f"{state}: no CR-labeled skip naming {cr}")
            self.assertIn("unittest.skip", OTHER_TESTS)

    def test_every_native_state_is_pinned_or_cr_skipped(self):
        unpinned = [s for s in native_states() if not pin_categories(s)]
        self.assertEqual(
            unpinned, [],
            "native action states with NO behavior pin, NO refusal pin, "
            f"and NO CR-labeled skip: {unpinned}")


if __name__ == "__main__":
    unittest.main()
