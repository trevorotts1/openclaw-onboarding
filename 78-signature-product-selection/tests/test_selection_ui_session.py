import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from selection_core import build_selection  # noqa: E402
from selection_session import SessionStore  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH, build_plan  # noqa: E402
from render_selection_preview import render  # noqa: E402
from emit_binding_plan import SELF_TEST_TARGETS, emit_plan  # noqa: E402
import copy as _copy


def make_selection():
    return build_selection(
        SELF_TEST_LAUNCH, offer_id="MAIN-B", price_choice_id="MAIN-B-USD",
        selected_at="2026-10-15T20:00:00Z", source_page_id="TEST-SELECTION",
        session_ref="opaque",
    )


class RadioGroupModelTests(unittest.TestCase):
    """S78-08 keyboard/functional contract, tested against the shipped
    renderer (the first checkpoint tested a model defined inside the test
    itself, which proved nothing about shipped code; S78-09 finding).
    The renderer ships native radio inputs, so keyboard behavior is the
    platform's own; the assertions pin the shipped markup and the shipped
    progressive-enhancement script instead."""

    def test_shipped_markup_uses_native_radios_no_key_hijack(self):
        plan = build_plan(SELF_TEST_LAUNCH, {"offer_id": "MAIN-B", "reason": "Recommended for founders who need individual feedback", "approved": True})
        doc = render(plan)
        self.assertEqual(doc.count('<input type="radio"'), 2)
        self.assertIn("<fieldset", doc)
        self.assertIn("<legend>Packages</legend>", doc)
        for oid in ("MAIN-A", "MAIN-B"):
            self.assertIn(f'value="{oid}"', doc)
        self.assertNotIn("onkeydown", doc)
        self.assertNotIn('addEventListener("keydown"', doc)
        self.assertIn("sl78SyncSelected", doc)
        self.assertIn("sl78SyncDetails", doc)

    def test_default_state_checks_nothing(self):
        plan = build_plan(SELF_TEST_LAUNCH, {"offer_id": "MAIN-B", "reason": "Recommended for founders who need individual feedback", "approved": True})
        doc = render(plan)
        self.assertEqual(doc.count(" checked"), 0)
        self.assertEqual(doc.count('sl78-offer" data-selected="true"'), 0)

    def test_selected_state_checks_exactly_one_and_marks_same_card(self):
        plan = build_plan(SELF_TEST_LAUNCH, {"offer_id": "MAIN-B", "reason": "Recommended for founders who need individual feedback", "approved": True})
        doc = render(plan, state="selected")
        self.assertEqual(doc.count(" checked"), 1)
        self.assertEqual(doc.count('sl78-offer" data-selected="true"'), 1)
        checked_line = next(line for line in doc.splitlines() if " checked" in line)
        self.assertIn('value="MAIN-B"', checked_line)

    def test_error_state_blocks_continuation(self):
        plan = build_plan(SELF_TEST_LAUNCH)
        doc = render(plan, state="error")
        self.assertIn("Choose a package to continue.", doc)
        self.assertIn('aria-describedby="sl78-error"', doc)
        self.assertEqual(doc.count(" checked"), 0)
        self.assertEqual(doc.count('sl78-offer" data-selected="true"'), 0)


class SessionTests(unittest.TestCase):
    def test_resume_round_trip(self):
        store = SessionStore(ttl_seconds=600)
        ref = store.create(make_selection(), now=1000)
        out = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                           launch=SELF_TEST_LAUNCH, now=1100)
        self.assertEqual(out["state"], "resumed")
        self.assertEqual(out["selection"]["offer_id"], "MAIN-B")

    def test_expiry_never_defaults_a_package(self):
        store = SessionStore(ttl_seconds=600)
        ref = store.create(make_selection(), now=1000)
        out = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                           launch=SELF_TEST_LAUNCH, now=1700)
        self.assertEqual(out["state"], "expired")
        self.assertNotIn("selection", out)
        self.assertIn("nothing was chosen for you", out["message"])

    def test_cross_tenant_ref_resolves_to_nothing(self):
        store = SessionStore()
        ref = store.create(make_selection(), now=1000)
        out = store.resume(ref, tenant_id="OTHER", launch_id="TEST-LAUNCH",
                           launch=SELF_TEST_LAUNCH, now=1001)
        self.assertEqual(out["state"], "expired")

    def test_changed_price_requires_reconfirm_not_silent_switch(self):
        store = SessionStore()
        ref = store.create(make_selection(), now=1000)
        changed = _copy.deepcopy(SELF_TEST_LAUNCH)
        changed["offers"][1]["prices"][0]["amount_minor"] = 21700
        out = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH",
                           launch=changed, now=1001)
        self.assertEqual(out["state"], "reconfirm_required")
        self.assertEqual(out["previous_amount_minor"], 19700)
        self.assertEqual(out["selected_offer_id"], "MAIN-B")

    def test_double_confirm_is_idempotent(self):
        store = SessionStore()
        ref = store.create(make_selection(), now=1000)
        first = store.confirm(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=SELF_TEST_LAUNCH, now=1001)
        second = store.confirm(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=SELF_TEST_LAUNCH, now=1002)
        self.assertEqual(first["state"], "confirmed")
        self.assertEqual(first["draft_ref"], second["draft_ref"])
        self.assertTrue(second["duplicate"])

    def test_confirm_revalidates_and_refuses_stale_terms(self):
        store = SessionStore()
        ref = store.create(make_selection(), now=1000)
        changed = _copy.deepcopy(SELF_TEST_LAUNCH)
        changed["offers"][1]["prices"][0]["amount_minor"] = 21700
        out = store.confirm(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=changed, now=1001)
        self.assertEqual(out["state"], "reconfirm_required")
        self.assertNotIn("draft_ref", out)

    def test_resume_and_confirm_agree_on_revoked_approval(self):
        store = SessionStore()
        ref = store.create(make_selection(), now=1000)
        revoked = _copy.deepcopy(SELF_TEST_LAUNCH)
        revoked["offers"][1]["prices"][0]["approval_status"] = "recommended_unapproved"
        resumed = store.resume(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=revoked, now=1001)
        confirmed = store.confirm(ref, tenant_id="TEST-TENANT", launch_id="TEST-LAUNCH", launch=revoked, now=1001)
        self.assertEqual(resumed["state"], "reconfirm_required")
        self.assertEqual(confirmed["state"], "reconfirm_required")

    def test_selection_cta_never_marks_payment(self):
        sel = make_selection()
        self.assertEqual(sel["kind"], "selection_intent_not_payment_evidence")
        self.assertNotIn("card", str(sel).lower())


class BindingPlanTests(unittest.TestCase):
    def test_plan_covers_every_selectable_offer(self):
        plan = emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="per_offer_targets")
        self.assertEqual({m["offer_id"] for m in plan["mappings"]}, {"MAIN-A", "MAIN-B"})
        self.assertEqual(plan["consumers"], ["S79", "S06"])

    def test_plan_keys_targets_per_price_choice(self):
        launch = _copy.deepcopy(SELF_TEST_LAUNCH)
        launch["offers"][0]["prices"].append(
            {"price_choice_id": "MAIN-A-USD-INST", "currency": "USD", "amount_minor": 9700,
             "billing_type": "installment", "native_price_id": "TEST-PRICE-A2",
             "schedule": [{"amount_minor": 4850, "due": "today"}, {"amount_minor": 4850, "due": "in 30 days"}],
             "terms_source": None, "approval_status": "approved"})
        targets = SELF_TEST_TARGETS + [
            {"offer_id": "MAIN-A", "price_choice_id": "MAIN-A-USD-INST", "native_product_id": "TEST-PROD-A",
             "native_price_id": "TEST-PRICE-A2", "target_ref": "TEST-CHECKOUT-A2"}]
        plan = emit_plan(launch, targets, route="per_offer_targets")
        self.assertEqual(len(plan["mappings"]), 3)
        with self.assertRaises(Exception):
            emit_plan(launch, SELF_TEST_TARGETS, route="per_offer_targets")


if __name__ == "__main__":
    unittest.main()
