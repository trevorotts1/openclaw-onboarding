"""S82-01 pair matrix: purchase-event schema acceptance in the adapter.

Fixture-driven. Every case comes from
fixtures/purchase-event-pair-matrix.json; this module contains no case
data of its own and no per-case branching beyond the case kind
(equivalence / snapshot / error).

What the matrix proves, and nothing more:

- equivalent 1.0, 1.1 and 1.2 streams produce the SAME snapshot mapping
  (including the 1.0-vs-1.1-vs-1.2 triple on one order);
- 1.1 events — still stamped by the 44 normalizer, normalizer.py:180 —
  build, with and without contact_ref;
- parent_order_ref absent / null / opaque string are equivalent — it is
  not an identity, not a grouping key and not an exported snapshot
  property;
- a parent_order_ref pointing at an earlier order never merges a later
  extra purchase into that order (grouping stays native_order_ref);
- refunds (full and partial) fold identically across the version axis;
- duplicate redelivery dedupes, conflicting redelivery raises;
- unsupported and missing versions fail closed, with the missing-version
  case still reporting the existing missing_field error;
- a parent_order_ref on a non-1.2 stamp — "1.0" or "1.1" — an empty
  string, or a non-string is refused.

TEST ONLY fixture data. Prior versions remain accepted: the 1.0 and 1.2
cases here are the pair halves, and the untouched suites
(tests/test_event_adapter.py, test_event_adapter_refunds.py,
test_ev1_dedupe.py, test_event_provenance.py) still run the baseline.

Run (S82_PACKET_REFERENCE is required by the shared test corpus), from
the skill directory:
    python3 -m unittest discover -s tests -t tests \
        -p 'test_event_adapter*.py' -v
Stdlib unittest only.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from purchase_event_adapter import (  # noqa: E402
    ACCEPTED_SCHEMA_VERSIONS,
    IDENTITY_KEYS,
    PARENT_ORDER_REF_VERSION,
    REFUND_IDENTITY_KEYS,
    AdapterError,
    build_snapshots,
)
from test_thank_you import LAUNCH, OFFERS  # noqa: E402

FIXTURE = SKILL_DIR / "fixtures" / "purchase-event-pair-matrix.json"


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


FIXTURE_DATA = load_fixture()
RAW_STREAMS = FIXTURE_DATA["streams"]
DERIVED_STREAMS = FIXTURE_DATA.get("derived_streams", {})
CASES = FIXTURE_DATA["cases"]
KINDS = {"equivalence", "snapshot", "error"}


def materialize(name):
    """Resolve one stream name to its events.

    A derived stream is its base's events with `set` applied to every
    event and `drop` keys removed — the 1.1 streams differ from their
    1.0 bases by the stamp alone, so they are recorded as a delta
    rather than copied out in full.
    """
    if name in RAW_STREAMS:
        return RAW_STREAMS[name]
    spec = DERIVED_STREAMS[name]
    events = copy.deepcopy(materialize(spec["derive_from"]))
    for event in events:
        event.update(spec.get("set", {}))
        for key in spec.get("drop", ()):
            event.pop(key, None)
    return events


STREAMS = {name: materialize(name)
           for name in list(RAW_STREAMS) + list(DERIVED_STREAMS)}


def build(stream_name):
    return build_snapshots(
        STREAMS[stream_name],
        journey_ids=FIXTURE_DATA["journeys"],
        offer_catalog=OFFERS,
        revision=LAUNCH["revision"],
    )


def iter_snapshots(snapshots):
    """Every snapshot plus every nested dict/list, for a field sweep."""
    stack = [snapshots]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            yield node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


class FixtureIntegrityTest(unittest.TestCase):
    def test_fixture_is_flagged_test_only(self):
        self.assertIs(FIXTURE_DATA["test_only"], True)

    def test_every_case_has_a_known_kind_and_an_existing_stream(self):
        self.assertTrue(CASES)
        for case in CASES:
            self.assertIn(case["kind"], KINDS, case["case_id"])
            refs = [case[k] for k in ("stream", "left", "middle", "right")
                    if k in case]
            self.assertTrue(refs, case["case_id"])
            for ref in refs:
                self.assertIn(ref, STREAMS, case["case_id"])

    def test_every_equivalence_pair_has_a_nonempty_reason(self):
        for case in CASES:
            if case["kind"] == "equivalence":
                self.assertTrue(case["why"].strip(), case["case_id"])

    def test_matrix_covers_the_required_axes(self):
        cases = {case["case_id"] for case in CASES}
        for required in (
            "eq-1.0-vs-1.2-main-bump",
            "eq-1.0-vs-1.1-vs-1.2-main-bump-triple",
            "eq-1.0-vs-1.1-same-order-followup-extras",
            "eq-parent-string-vs-null",
            "eq-parent-string-vs-absent",
            "eq-1.0-vs-1.2-separate-extra-order",
            "eq-1.0-vs-1.2-refund",
            "eq-1.0-vs-1.1-refund",
            "snapshot-1.1-contact-ref-accepted",
            "snapshot-duplicate-1.1-deduped",
            "snapshot-duplicate-redelivery-deduped",
            "error-1.1-conflicting-redelivery",
            "error-conflicting-redelivery",
            "error-unsupported-version",
            "error-missing-version",
            "error-parent-on-1.0-stamp",
            "error-parent-on-1.1-stamp",
        ):
            self.assertIn(required, cases)


class PairMatrixTest(unittest.TestCase):
    def test_accepted_versions_are_1_0_1_1_and_1_2(self):
        self.assertEqual(ACCEPTED_SCHEMA_VERSIONS, ("1.0", "1.1", "1.2"))

    def test_parent_order_ref_is_not_an_identity_or_refund_key(self):
        # The field is opaque linkage only. If it ever appears here it
        # has become an identity, and grouping/dedupe would depend on it.
        self.assertNotIn("parent_order_ref", IDENTITY_KEYS)
        self.assertNotIn("parent_order_ref", REFUND_IDENTITY_KEYS)

    def test_parent_order_ref_is_refused_on_every_non_1_2_version(self):
        # 1.1 is NOT a 1.2 field carrier: the v1.1 schema does not
        # declare parent_order_ref and sets additionalProperties false,
        # exactly as v1.0 does. So 1.1 is refused by the same rule as
        # 1.0, not by a looser one.
        self.assertEqual(PARENT_ORDER_REF_VERSION, "1.2")
        messages = {}
        for stream in ("parent_on_10", "parent_on_11"):
            with self.assertRaises(AdapterError) as ctx:
                build(stream)
            self.assertIn("invalid_parent_order_ref", str(ctx.exception))
            messages[stream] = str(ctx.exception)
        for stream, message in messages.items():
            self.assertIn("defined only by schema_version '1.2'", message,
                          stream)

    def test_equivalence_cases_produce_identical_snapshots(self):
        ran = 0
        for case in CASES:
            if case["kind"] != "equivalence":
                continue
            with self.subTest(case=case["case_id"]):
                names = [case[k] for k in ("left", "middle", "right")
                         if k in case]
                built = [build(name) for name in names]
                for other in built[1:]:
                    self.assertEqual(built[0], other, case["why"])
                ran += 1
        self.assertGreater(ran, 0)

    def test_snapshot_cases_match_their_expectations(self):
        ran = 0
        for case in CASES:
            if case["kind"] != "snapshot":
                continue
            with self.subTest(case=case["case_id"]):
                snapshots = build(case["stream"])
                expect = case["expect"]
                if "orders" in case:
                    self.assertEqual(sorted(snapshots), sorted(case["orders"]))
                if "line_count" in expect:
                    for order, count in expect["line_count"].items():
                        self.assertEqual(
                            len(snapshots[order]["line_items"]), count, order)
                if "line_payment_status" in expect:
                    for order, statuses in expect["line_payment_status"].items():
                        self.assertEqual(
                            [line["payment_status"]
                             for line in snapshots[order]["line_items"]],
                            statuses, order)
                if "line_event_id" in expect:
                    for order, ids in expect["line_event_id"].items():
                        self.assertEqual(
                            [line["event_id"]
                             for line in snapshots[order]["line_items"]],
                            ids, order)
                if "line_amount_minor" in expect:
                    for order, amounts in expect["line_amount_minor"].items():
                        self.assertEqual(
                            [line["amount_minor"]
                             for line in snapshots[order]["line_items"]],
                            amounts, order)
                ran += 1
        self.assertGreater(ran, 0)

    def test_error_cases_raise_the_named_error(self):
        ran = 0
        for case in CASES:
            if case["kind"] != "error":
                continue
            with self.subTest(case=case["case_id"]):
                with self.assertRaises(AdapterError) as ctx:
                    build(case["stream"])
                self.assertIn(case["error_contains"], str(ctx.exception))
                ran += 1
        self.assertGreater(ran, 0)

    def test_no_snapshot_exports_the_parent_or_contact_field(self):
        # Not a snapshot property, not a line property, nowhere nested.
        for case in CASES:
            if case["kind"] == "error":
                continue
            with self.subTest(case=case["case_id"]):
                stream = case["left"] if "left" in case else case["stream"]
                snapshots = build(stream)
                for node in iter_snapshots(snapshots):
                    self.assertNotIn("parent_order_ref", node)
                    self.assertNotIn("contact_ref", node)

    def test_snapshot_schema_version_stays_1_0_for_1_1_and_1_2_events(self):
        checked = 0
        for case in CASES:
            if case["kind"] == "error":
                continue
            stream = case["left"] if "left" in case else case["stream"]
            stamps = {event.get("schema_version") for event in STREAMS[stream]}
            if not stamps & {"1.1", "1.2"}:
                continue
            for snapshot in build(stream).values():
                self.assertEqual(snapshot["schema_version"], "1.0")
            checked += 1
        self.assertGreater(checked, 0)

    def test_parent_order_ref_never_regroups_orders(self):
        # The 1.2 parent deliberately points at TEST-ORDER-0001 from an
        # event whose own native_order_ref is TEST-ORDER-0002.
        snapshots = build("extra_separate_order_12_parent_string")
        self.assertEqual(sorted(snapshots),
                         ["TEST-ORDER-0001", "TEST-ORDER-0002"])
        self.assertEqual(
            [line["offer_id"] for line in snapshots["TEST-ORDER-0001"]["line_items"]],
            ["MAIN-A"])
        self.assertEqual(
            [line["offer_id"] for line in snapshots["TEST-ORDER-0002"]["line_items"]],
            ["U1"])


if __name__ == "__main__":
    unittest.main()
