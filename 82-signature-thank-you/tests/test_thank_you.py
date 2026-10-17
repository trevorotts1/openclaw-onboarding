"""Skill 82 tests (S82-03 / S82-09 offline coverage).

Covers:
(a) all 64 normal-path cases from the packet reference acceptance-cases.json
    — snapshot built from launch-example.json prices/entitlements, resolved,
    and checked for exact displayed offers, entitlements and totals;
(b) the five terminal purchase sets (none, U1, U1+U2, D1, D1+U2) x bump;
(c) negatives: query-string premium claim, unpurchased U1 on a D1 path,
    new upsell CTA, pending shown as confirmed, extra failed -> base access
    preserved, wrong tenant, duplicate event deduplication.

All data is TEST ONLY. Stdlib unittest only.
"""

import copy
import json
import os
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from thank_you_resolver import ResolverError, resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from validate_entitlements import validate_entitlements  # noqa: E402

def _packet_reference_dir():
    """Locate ``packet/reference`` independent of the checkout depth.

    CR-INT-S82-001: the fixed-depth ``SKILL_DIR.parents[3]`` walk this
    replaces resolved the packet only at the authored layout's depth
    and errored at import everywhere else. Resolution order: the
    ``S82_PACKET_REFERENCE`` env override, then a tolerant ancestor
    walk from the skill directory up to the first ancestor carrying
    ``packet/reference`` (the tolerant-walk shape INTEGRATION
    suggested in CR-INT-S82-001, mirroring S78's CR-INT-S78-001 fix).
    The suite asserts identically in every layout whose tree carries
    the packet at any ancestor depth.
    """
    override = os.environ.get("S82_PACKET_REFERENCE")
    if override:
        return Path(override)
    for ancestor in SKILL_DIR.parents:
        candidate = ancestor / "packet" / "reference"
        if (candidate / "launch-example.json").is_file() and \
                (candidate / "acceptance-cases.json").is_file():
            return candidate
    raise ImportError(
        "S82 tests: packet/reference (launch-example.json + "
        "acceptance-cases.json) not found in any ancestor of "
        f"{SKILL_DIR}; set S82_PACKET_REFERENCE to the packet "
        "reference directory"
    )


REF = _packet_reference_dir()
LAUNCH = json.loads((REF / "launch-example.json").read_text())
CASES = json.loads((REF / "acceptance-cases.json").read_text())["cases"]
OFFERS = {o["offer_id"]: o for o in LAUNCH["offers"]}
IDENTITY = {
    "tenant_id": LAUNCH["tenant_id"],
    "location_id": LAUNCH["location_id"],
    "launch_id": LAUNCH["launch_id"],
}


def make_snapshot(offer_ids, statuses=None, tenant_id=None):
    """Build a verified snapshot for the given purchased offer ids."""
    statuses = statuses or {}
    line_items = []
    event_ids = []
    for idx, offer_id in enumerate(offer_ids, start=1):
        offer = OFFERS[offer_id]
        price = offer["prices"][0]
        event_id = f"TEST-EVT-{idx:03d}"
        event_ids.append(event_id)
        line_items.append({
            "native_line_ref": f"TEST-LINE-{offer_id}",
            "event_id": event_id,
            "offer_id": offer_id,
            "slot": offer["slot"],
            "display_name": offer["display_name"],
            "currency": price["currency"],
            "amount_minor": price["amount_minor"],
            "entitlement_ids": list(offer["entitlement_ids"]),
            "payment_status": statuses.get(offer_id, "succeeded"),
            "billing": {
                "billing_type": price["billing_type"],
                "recurring_interval": None,
                "schedule": price["schedule"],
                "terms_source": price["terms_source"],
            },
        })
    return {
        "schema_version": "1.0",
        **IDENTITY,
        "tenant_id": tenant_id or IDENTITY["tenant_id"],
        "revision": LAUNCH["revision"],
        "source": "verified_normalized_purchase_snapshot",
        "verified": True,
        "provider": "TEST-ONLY",
        "native_order_ref": "TEST-ORDER-0001",
        "native_transaction_ref": "TEST-TXN-0001",
        "journey_id": "TEST-JOURNEY-0001",
        "event_ids": event_ids,
        "line_items": line_items,
        "evidence_ref": "TEST-ONLY fixture snapshot",
        "test_only": True,
    }


def make_fulfillment(snapshot, states=None):
    """Grant every entitlement of paid items unless overridden."""
    states = states or {}
    fulfillment = {}
    for line in snapshot["line_items"]:
        for ent in line["entitlement_ids"]:
            if ent in states:
                fulfillment[ent] = states[ent]
            elif line["payment_status"] == "succeeded":
                fulfillment[ent] = {
                    "state": "granted",
                    "delivery_url": f"https://example.test/access/{ent}",
                    "next_action": "access",
                }
            else:
                fulfillment[ent] = {"state": "pending", "delivery_url": None,
                                    "next_action": None}
    return fulfillment


def entitlement_set(offer_ids):
    out = set()
    for offer_id in offer_ids:
        out.update(OFFERS[offer_id]["entitlement_ids"])
    return out


class AllFixtureCasesTest(unittest.TestCase):
    def test_all_64_cases(self):
        self.assertEqual(len(CASES), 64)
        for case in CASES:
            with self.subTest(case_id=case["case_id"]):
                expected_offers = case["expected_purchased_offers"]
                snapshot = make_snapshot(expected_offers)
                fulfillment = make_fulfillment(snapshot)
                view = resolve_order_view(snapshot, fulfillment,
                                          expected_identity=IDENTITY)

                displayed_offers = [i["offer_id"] for i in view["items"]]
                self.assertEqual(sorted(displayed_offers), sorted(expected_offers))
                # slot order: main first, bump second
                self.assertEqual(displayed_offers, expected_offers)

                displayed_entitlements = set()
                for item in view["items"]:
                    displayed_entitlements.update(item["entitlement_ids"])
                self.assertEqual(displayed_entitlements,
                                 entitlement_set(expected_offers))

                # no unpurchased entitlement appears anywhere
                all_entitlements = entitlement_set(OFFERS)
                self.assertEqual(
                    displayed_entitlements - entitlement_set(expected_offers),
                    set(),
                )
                self.assertTrue(displayed_entitlements <= all_entitlements)
                access_ents = {b["entitlement_id"] for b in view["access_blocks"]}
                self.assertEqual(access_ents, entitlement_set(expected_offers))

                self.assertEqual(view["totals"]["paid_total_minor"],
                                 case["expected_total_minor_test_usd"])
                self.assertEqual(view["totals"]["pending_total_minor"], 0)
                self.assertTrue(view["confirmation"]["all_set"])
                self.assertEqual(view["pending_items"], [])
                self.assertEqual(view["failed_items"], [])
                self.assertFalse({"U1", "D1"} <= set(displayed_offers))

                self.assertEqual(
                    validate_thank_you(view, snapshot, fulfillment), [])
                self.assertEqual(
                    validate_entitlements(view, snapshot, fulfillment), [])


class FiveTerminalPurchaseSetsTest(unittest.TestCase):
    SETS = [[], ["U1"], ["U1", "U2"], ["D1"], ["D1", "U2"]]

    def test_five_sets_times_bump(self):
        for extras in self.SETS:
            for bump in (False, True):
                offers = ["MAIN-A"] + (["BUMP"] if bump else []) + extras
                with self.subTest(extras=extras, bump=bump):
                    snapshot = make_snapshot(offers)
                    fulfillment = make_fulfillment(snapshot)
                    view = resolve_order_view(snapshot, fulfillment,
                                              expected_identity=IDENTITY)
                    self.assertEqual([i["offer_id"] for i in view["items"]],
                                     offers)
                    self.assertEqual(
                        {b["entitlement_id"] for b in view["access_blocks"]},
                        entitlement_set(offers))
                    self.assertEqual(
                        view["totals"]["paid_total_minor"],
                        sum(OFFERS[o]["prices"][0]["amount_minor"]
                            for o in offers))
                    self.assertEqual(
                        validate_thank_you(view, snapshot, fulfillment), [])


class NegativeTest(unittest.TestCase):
    def test_query_string_premium_claim_rejected(self):
        # No verified snapshot at all: a vip=true claim builds nothing.
        with self.assertRaises(ResolverError):
            resolve_order_view(None, {}, expected_identity=IDENTITY,
                               request_context={"query_params": {"vip": "true"}})
        # Even with a valid snapshot, an entitlement claim via query is rejected.
        snapshot = make_snapshot(["MAIN-A"])
        with self.assertRaises(ResolverError):
            resolve_order_view(
                snapshot, make_fulfillment(snapshot),
                expected_identity=IDENTITY,
                request_context={"query_params": {"vip": "true",
                                                  "offer": "U1"}})
        # A hand-built view carrying a query-string claim fails validation.
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["query_params"] = {"vip": "true"}
        errors = validate_thank_you(tampered, snapshot)
        self.assertTrue(any("query_string_authority" in e for e in errors),
                        errors)

    def test_unpurchased_u1_on_d1_path_rejected(self):
        snapshot = make_snapshot(["MAIN-A", "D1"])
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        # Sanity: the honest D1 view contains no U1 entitlement.
        self.assertNotIn("extra-full",
                         {b["entitlement_id"] for b in view["access_blocks"]})
        # Tamper: display U1 as if purchased.
        tampered = copy.deepcopy(view)
        u1 = OFFERS["U1"]
        tampered["items"].append({
            "offer_id": "U1", "slot": "upsell_1",
            "display_name": u1["display_name"],
            "amount_minor": u1["prices"][0]["amount_minor"],
            "currency": "USD", "display_status": "paid",
            "entitlement_ids": ["extra-full"],
            "native_line_ref": "TEST-LINE-U1", "event_id": "TEST-EVT-FAKE",
            "billing": {"billing_type": "one_time"},
        })
        tampered["access_blocks"].append({
            "entitlement_id": "extra-full", "offer_id": "U1",
            "slot": "upsell_1", "next_action": "access",
            "delivery_url": "https://example.test/access/extra-full",
            "fulfillment_state": "granted",
        })
        ty_errors = validate_thank_you(tampered, snapshot, fulfillment)
        ent_errors = validate_entitlements(tampered, snapshot, fulfillment)
        self.assertTrue(any("unprovenanced_item" in e or
                            "access_without_paid_purchase" in e
                            for e in ty_errors), ty_errors)
        self.assertTrue(any("unpurchased_entitlement_displayed" in e
                            for e in ent_errors), ent_errors)

    def test_new_upsell_cta_rejected(self):
        snapshot = make_snapshot(["MAIN-A"])
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["ctas"].append({
            "classification": "upsell",
            "label": "Add TEST ONLY U1 now",
            "offer_id": "U1",
            "entitlement_id": None,
            "initiates_new_charge": True,
        })
        errors = validate_thank_you(tampered, snapshot)
        self.assertTrue(any("unclassified_cta" in e for e in errors), errors)
        self.assertTrue(any("new_charge_cta" in e for e in errors), errors)
        self.assertTrue(any("unpurchased_cta_target" in e for e in errors),
                        errors)
        # A recommendation block is a pitch too.
        tampered2 = copy.deepcopy(view)
        tampered2["recommendations"] = [{"offer_id": "U2"}]
        errors2 = validate_thank_you(tampered2, snapshot)
        self.assertTrue(any("new_offer_pitch" in e for e in errors2), errors2)

    def test_pending_charge_never_shown_confirmed(self):
        snapshot = make_snapshot(["MAIN-A", "U1"],
                                 statuses={"U1": "pending"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertFalse(view["confirmation"]["all_set"])
        self.assertNotIn("all set",
                         view["confirmation"]["headline"].lower())
        self.assertEqual(view["pending_items"], ["U1"])
        # Base is still confirmed and accessible; the pending extra has
        # no access block and is excluded from the paid total.
        self.assertIn("base-a",
                      {b["entitlement_id"] for b in view["access_blocks"]})
        self.assertNotIn("extra-full",
                         {b["entitlement_id"] for b in view["access_blocks"]})
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)
        self.assertEqual(view["totals"]["pending_total_minor"], 6700)
        # Tamper: relabel the pending view as fully confirmed -> rejected.
        tampered = copy.deepcopy(view)
        tampered["confirmation"] = {
            "status": "confirmed", "all_set": True,
            "headline": "You are all set. Your purchase is confirmed.",
        }
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(any("false_confirmation" in e for e in errors), errors)

    def test_extra_failed_base_access_preserved(self):
        # A20: no valid base access may be lost when an extra fails; and
        # the resolver output for a failed U2 keeps base (and U1) access.
        snapshot = make_snapshot(["MAIN-A", "U1", "U2"],
                                 statuses={"U2": "failed"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        access = {b["entitlement_id"] for b in view["access_blocks"]}
        self.assertIn("base-a", access)
        self.assertIn("extra-full", access)
        self.assertNotIn("implementation", access)
        self.assertEqual(view["failed_items"], ["U2"])
        self.assertFalse(view["confirmation"]["all_set"])
        self.assertEqual(view["totals"]["paid_total_minor"], 9700 + 6700)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])

    def test_wrong_tenant_rejected(self):
        snapshot = make_snapshot(["MAIN-A"], tenant_id="TEST-OTHER-TENANT")
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, {}, expected_identity=IDENTITY)
        self.assertIn("wrong_tenant", str(ctx.exception))

    def test_duplicate_event_deduped(self):
        snapshot = make_snapshot(["MAIN-A", "BUMP"])
        # The same event/line delivered twice (duplicate webhook delivery).
        snapshot["line_items"].append(copy.deepcopy(snapshot["line_items"][1]))
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual([i["offer_id"] for i in view["items"]],
                         ["MAIN-A", "BUMP"])
        self.assertEqual(view["totals"]["paid_total_minor"], 9700 + 2700)
        # A conflicting redelivery of the same native line is an error,
        # never a silent merge.
        conflict = make_snapshot(["MAIN-A", "BUMP"])
        dup = copy.deepcopy(conflict["line_items"][1])
        dup["amount_minor"] = 9999
        conflict["line_items"].append(dup)
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(conflict, {})
        self.assertIn("duplicate_conflict", str(ctx.exception))

    def test_unverified_and_query_only_inputs_rejected(self):
        snapshot = make_snapshot(["MAIN-A"])
        unverified = copy.deepcopy(snapshot)
        unverified["verified"] = False
        with self.assertRaises(ResolverError):
            resolve_order_view(unverified, {})
        # A snapshot carrying raw card data is rejected outright.
        poisoned = copy.deepcopy(snapshot)
        poisoned["line_items"][0]["card_number"] = "TEST-ONLY-NOT-A-REAL-CARD"
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(poisoned, {})
        self.assertIn("forbidden_field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
