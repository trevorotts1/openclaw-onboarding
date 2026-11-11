"""Issues 77 and 78 across the 78 to 79 seam, driven through the real modules on both sides.

77. 78's session clock is epoch seconds; whatever leaves the session store toward Skill 79 is an aware
    ISO-8601 string, which 79 parses as an instant (CHK-07). An integer handed over anyway is refused by name.
78. The selection intent's schedule rows are `{sequence, due, amount_minor}`, the checkout schema's row shape,
    and they arrive in Skill 79's Selection with the billing type.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL = HERE.parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(HERE.parents[2] / "79-signature-order-form" / "scripts"))

import jsonschema  # noqa: E402  (activated through the PYDEPS block in the scripts above when needed)

from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402
from selection_core import build_selection, validate_binding  # noqa: E402
from selection_flow import (  # noqa: E402
    SelectionBillingError, SelectionTimeError, billing_summary, resolve_selection, selection_from_intent,
)
from selection_session import SessionStore, to_iso  # noqa: E402
from selection_session_store import DurableSessionStore  # noqa: E402

SELECTION_SCHEMA = json.loads((SKILL / "schema" / "selection.schema.json").read_text())
CHECKOUT_SCHEMA = json.loads((HERE.parents[2] / "79-signature-order-form" / "references" / "checkout.schema.json").read_text())
INSTALLMENT_PRICE = {
    "price_choice_id": "MAIN-A-USD-INST", "currency": "USD", "amount_minor": 9700, "billing_type": "installment",
    "native_price_id": "TEST-PRICE-A2", "terms_source": None, "approval_status": "approved",
    "schedule": [{"amount_minor": 4850, "due": "today"}, {"amount_minor": 4850, "due": "in 30 days"}]}


def installment_launch():
    launch = copy.deepcopy(SELF_TEST_LAUNCH)
    launch["offers"][0]["prices"].append(copy.deepcopy(INSTALLMENT_PRICE))
    return launch


def installment_intent(launch):
    return build_selection(launch, offer_id="MAIN-A", price_choice_id="MAIN-A-USD-INST",
                           selected_at="2026-10-15T20:00:00Z", source_page_id="SEL", session_ref="opaque")


def resolve_for(selection, launch, now):
    return resolve_selection(
        selection, current_launch_revision=launch["revision"], current_offer_revision=launch["revision"],
        current_native_price_id="TEST-PRICE-A2", current_amount_minor=9700, current_currency="USD", now=now,
        expected_tenant_id=launch["tenant_id"], expected_location_id=launch["location_id"],
        expected_launch_id=launch["launch_id"])


class ScheduleRowShape(unittest.TestCase):
    def test_the_selection_intent_carries_checkout_shaped_rows_and_validates(self):
        intent = installment_intent(installment_launch())
        self.assertEqual(intent["schedule"], [{"sequence": 1, "due": "today", "amount_minor": 4850},
                                              {"sequence": 2, "due": "in 30 days", "amount_minor": 4850}])
        jsonschema.validate(intent, SELECTION_SCHEMA)

    def test_the_old_two_key_row_is_no_longer_a_valid_intent(self):
        intent = installment_intent(installment_launch())
        intent["schedule"] = [{"amount_minor": 4850, "due": "today"}]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(intent, SELECTION_SCHEMA)

    def test_one_time_intents_still_carry_an_empty_schedule(self):
        intent = build_selection(SELF_TEST_LAUNCH, offer_id="MAIN-A", price_choice_id="MAIN-A-USD",
                                 selected_at="2026-10-15T20:00:00Z", source_page_id="SEL", session_ref="opaque")
        self.assertEqual(intent["schedule"], [])
        jsonschema.validate(intent, SELECTION_SCHEMA)

    def test_78_and_79_agree_on_the_schedule_row_shape(self):
        mine = SELECTION_SCHEMA["properties"]["schedule"]["items"]
        theirs = CHECKOUT_SCHEMA["$defs"]["price_choice"]["properties"]["schedule"]["items"]
        self.assertEqual(sorted(mine["required"]), sorted(theirs["required"]))
        self.assertEqual(mine["properties"], theirs["properties"])
        self.assertIs(mine["additionalProperties"], False)
        self.assertIs(theirs["additionalProperties"], False)

    def test_the_binding_check_accepts_the_new_row_shape(self):
        launch = installment_launch()
        validate_binding(installment_intent(launch), launch, expected_revision=1)


class SessionToCheckoutRoundTrip(unittest.TestCase):
    def selection_from_store(self, store, launch, intent, resume_now=1100):
        ref = store.create(intent, now=1000)
        resumed = store.resume(ref, tenant_id=launch["tenant_id"], launch_id=launch["launch_id"],
                               launch=launch, now=resume_now)
        self.assertEqual(resumed["state"], "resumed", resumed)
        return resumed

    def test_to_iso_is_an_aware_utc_instant(self):
        self.assertEqual(to_iso(0), "1970-01-01T00:00:00Z")
        self.assertEqual(to_iso(2800), "1970-01-01T00:46:40Z")

    def test_resume_hands_79_an_iso_expiry_and_79_compares_it_as_an_instant(self):
        launch = installment_launch()
        resumed = self.selection_from_store(SessionStore(ttl_seconds=1800), launch, installment_intent(launch))
        self.assertEqual(resumed["expires_at"], "1970-01-01T00:46:40Z")  # created at 1000 s + 1800 s TTL
        sel = selection_from_intent(resumed["selection"], expires_at=resumed["expires_at"])
        self.assertEqual(resolve_for(sel, launch, "1970-01-01T00:20:00Z").action, "proceed")
        self.assertEqual(resolve_for(sel, launch, "1970-01-01T00:50:00Z").action, "recovery_choice")
        self.assertEqual(resolve_for(sel, launch, "1970-01-01T01:30:00+01:00").action, "proceed")  # 00:30Z

    def test_the_durable_store_hands_over_the_same_iso_expiry(self):
        launch = installment_launch()
        with tempfile.TemporaryDirectory() as td:
            resumed = self.selection_from_store(DurableSessionStore(td, ttl_seconds=1800), launch,
                                                installment_intent(launch))
        self.assertEqual(resumed["expires_at"], "1970-01-01T00:46:40Z")

    def test_the_raw_epoch_is_refused_by_name_at_the_79_adapter(self):
        launch = installment_launch()
        intent = installment_intent(launch)
        store = SessionStore(ttl_seconds=1800)
        ref = store.create(intent, now=1000)
        epoch = store._get_record(ref)["expires_at"]
        self.assertIsInstance(epoch, int)
        with self.assertRaises(SelectionTimeError):
            selection_from_intent(intent, expires_at=epoch)

    def test_billing_type_and_schedule_arrive_in_the_selection_and_are_summarised(self):
        launch = installment_launch()
        resumed = self.selection_from_store(SessionStore(), launch, installment_intent(launch))
        sel = selection_from_intent(resumed["selection"], expires_at=resumed["expires_at"])
        self.assertEqual((sel.billing_type, sel.schedule), ("installment", ((1, "today", 4850), (2, "in 30 days", 4850))))
        summary = billing_summary(sel, currency_exponent=2)
        self.assertEqual([r["amount"] for r in summary["rows"]], ["USD 48.50", "USD 48.50"])

    def test_an_intent_in_the_old_row_shape_stops_at_the_adapter(self):
        launch = installment_launch()
        intent = installment_intent(launch)
        intent["schedule"] = [{"amount_minor": 4850, "due": "today"}, {"amount_minor": 4850, "due": "in 30 days"}]
        with self.assertRaises(SelectionBillingError):
            selection_from_intent(intent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
