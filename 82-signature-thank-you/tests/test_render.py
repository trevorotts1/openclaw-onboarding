"""Skill 82 renderer tests (S82-04 layout/copy profiles, S82-06 states).

Covers the renderer in scripts/render_thank_you.py against views built
by the authoritative resolver from TEST ONLY packet fixtures:

- the five terminal purchase sets render exactly the purchased
  names/amounts and no unpurchased names;
- a pending set never says "You are all set" and keeps base access;
- a failed extra keeps base access and is labeled Failed;
- the reconciling state shows retry + support and no buy CTA;
- outage cached views carry the "Unresolved items" label;
- all three error states show a support fallback and no receipt data
  (never a fake sample receipt);
- malicious untrusted text is HTML-escaped;
- an unknown or missing confirmation status fails closed instead of
  falling back to the word "Confirmed" (F-01);
- every rendered CTA carries an allowed data-cta-class, and none is a
  new-charge class.

Stdlib unittest only. All data is TEST ONLY.
"""

import copy
import json
import os
import re
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from thank_you_resolver import resolve_order_view  # noqa: E402
from validate_thank_you import ALLOWED_CTA_CLASSIFICATIONS  # noqa: E402
from render_thank_you import (  # noqa: E402
    ERROR_KINDS,
    format_amount,
    render_error,
    render_state_fragment,
    render_thank_you,
)

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
OFFERS = {o["offer_id"]: o for o in LAUNCH["offers"]}
IDENTITY = {
    "tenant_id": LAUNCH["tenant_id"],
    "location_id": LAUNCH["location_id"],
    "launch_id": LAUNCH["launch_id"],
}

BRAND = {
    "brand_name": "TEST ONLY BRAND",
    "colors": {"primary": "#123456", "accent": "#057a55",
               "background": "#ffffff", "text": "#111111"},
    "support": {"label": "Contact TEST ONLY support",
                "email": "support@example.test"},
    "manage_purchase_url": "https://example.test/manage",
}

CTA_CLASS_RE = re.compile(r'data-cta-class="([^"]+)"')
NEW_CHARGE_CLASSES = {"buy", "buy_now", "purchase", "checkout", "upsell",
                      "new_charge", "add_to_order", "one_click_buy"}


def make_snapshot(offer_ids, statuses=None):
    """Same verified-snapshot builder as tests/test_thank_you.py."""
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


def make_fulfillment(snapshot):
    fulfillment = {}
    for line in snapshot["line_items"]:
        for ent in line["entitlement_ids"]:
            if line["payment_status"] == "succeeded":
                fulfillment[ent] = {
                    "state": "granted",
                    "delivery_url": f"https://example.test/access/{ent}",
                    "next_action": "access",
                }
            else:
                fulfillment[ent] = {"state": "pending",
                                    "delivery_url": None,
                                    "next_action": None}
    return fulfillment


def resolve(offer_ids, statuses=None):
    snapshot = make_snapshot(offer_ids, statuses)
    return resolve_order_view(snapshot, make_fulfillment(snapshot),
                              expected_identity=IDENTITY)


def assert_ctas_allowed(testcase, html_out):
    classes = CTA_CLASS_RE.findall(html_out)
    testcase.assertTrue(classes, "expected at least one CTA in the output")
    for cls in classes:
        testcase.assertIn(cls, ALLOWED_CTA_CLASSIFICATIONS)
        testcase.assertNotIn(cls, NEW_CHARGE_CLASSES)
    testcase.assertNotIn("initiates_new_charge", html_out)


class FiveTerminalPurchaseSetsRenderTest(unittest.TestCase):
    SETS = [[], ["U1"], ["U1", "U2"], ["D1"], ["D1", "U2"]]

    def test_five_sets_render_exactly_purchased(self):
        all_names = {o["display_name"] for o in OFFERS.values()}
        for extras in self.SETS:
            for bump in (False, True):
                offers = ["MAIN-A"] + (["BUMP"] if bump else []) + extras
                with self.subTest(extras=extras, bump=bump):
                    html_out = render_thank_you(resolve(offers), BRAND)
                    purchased_names = {OFFERS[o]["display_name"]
                                       for o in offers}
                    for offer_id in offers:
                        offer = OFFERS[offer_id]
                        self.assertIn(offer["display_name"], html_out)
                        self.assertIn(
                            format_amount(
                                offer["prices"][0]["amount_minor"], "USD"),
                            html_out)
                    for name in all_names - purchased_names:
                        self.assertNotIn(name, html_out)
                    total = sum(OFFERS[o]["prices"][0]["amount_minor"]
                                for o in offers)
                    self.assertIn(format_amount(total, "USD"), html_out)
                    self.assertIn("TEST-ORDER-0001", html_out)
                    self.assertIn("You are all set", html_out)
                    for offer_id in offers:
                        for ent in OFFERS[offer_id]["entitlement_ids"]:
                            self.assertIn(
                                f"https://example.test/access/{ent}",
                                html_out)

    def test_summary_is_text_table_not_image(self):
        html_out = render_thank_you(resolve(["MAIN-A", "U1"]), BRAND)
        self.assertIn("<table", html_out)
        self.assertIn("<caption>", html_out)
        self.assertNotIn("<img", html_out)


class PendingAndFailedRenderTest(unittest.TestCase):
    def test_pending_set_never_all_set_and_base_access_kept(self):
        view = resolve(["MAIN-A", "U1"], statuses={"U1": "pending"})
        html_out = render_thank_you(view, BRAND)
        self.assertNotIn("You are all set", html_out)
        self.assertIn("Pending", html_out)
        self.assertIn("TEST ONLY U1", html_out)
        # Base access is rendered; the pending extra has no access link.
        self.assertIn("https://example.test/access/base-a", html_out)
        self.assertNotIn("https://example.test/access/extra-full",
                         html_out)
        # Pending money is separated from the paid total.
        self.assertIn("Pending (not yet confirmed)", html_out)
        self.assertIn(format_amount(6700, "USD"), html_out)

    def test_failed_extra_keeps_base_access(self):
        view = resolve(["MAIN-A", "U1", "U2"], statuses={"U2": "failed"})
        html_out = render_thank_you(view, BRAND)
        self.assertIn("https://example.test/access/base-a", html_out)
        self.assertIn("https://example.test/access/extra-full", html_out)
        self.assertNotIn("https://example.test/access/implementation",
                         html_out)
        self.assertIn("Failed", html_out)
        self.assertNotIn("You are all set", html_out)


class ReconcilingRenderTest(unittest.TestCase):
    def test_reconciling_fragment_has_retry_support_no_buy(self):
        html_out = render_state_fragment(
            "reconciling", BRAND,
            {"retry": {"attempt": 2, "max_attempts": 5,
                       "next_retry_seconds": 15}})
        self.assertIn("Check again now", html_out)
        self.assertIn("check 2 of 5", html_out)
        self.assertIn('data-cta-class="support"', html_out)
        self.assertIn("never starts another purchase", html_out)
        self.assertNotIn("Buy now", html_out)
        assert_ctas_allowed(self, html_out)

    def test_reconciling_banner_over_partial_view(self):
        view = resolve(["MAIN-A", "U1"], statuses={"U1": "pending"})
        html_out = render_thank_you(
            view, BRAND,
            {"mode": "reconciling",
             "retry": {"attempt": 1, "max_attempts": 5,
                       "next_retry_seconds": 5}})
        self.assertIn("Confirming your purchase", html_out)
        self.assertIn("https://example.test/access/base-a", html_out)
        self.assertNotIn("You are all set", html_out)
        assert_ctas_allowed(self, html_out)


class OutageRenderTest(unittest.TestCase):
    def test_outage_cached_labels_unresolved_items(self):
        view = resolve(["MAIN-A", "U1"], statuses={"U1": "pending"})
        html_out = render_thank_you(view, BRAND, {"mode": "outage_cached"})
        self.assertIn("Unresolved items", html_out)
        self.assertIn("last confirmed copy", html_out)
        self.assertIn("TEST ONLY U1", html_out)
        self.assertIn("https://example.test/access/base-a", html_out)
        assert_ctas_allowed(self, html_out)


class ErrorRenderTest(unittest.TestCase):
    def test_each_error_kind_has_support_and_no_receipt(self):
        for kind in ERROR_KINDS:
            with self.subTest(kind=kind):
                html_out = render_error(kind, BRAND)
                self.assertIn('data-cta-class="support"', html_out)
                self.assertIn("support@example.test", html_out)
                # No fake sample receipt: no purchased names, amounts,
                # order reference, or summary table anywhere.
                for offer in OFFERS.values():
                    self.assertNotIn(offer["display_name"], html_out)
                self.assertNotIn("TEST-ORDER-0001", html_out)
                self.assertNotIn("<table", html_out)
                self.assertNotIn("$97.00", html_out)
                assert_ctas_allowed(self, html_out)

    def test_error_via_render_thank_you_state(self):
        html_out = render_thank_you(
            None, BRAND, {"mode": "error",
                          "error_kind": "stale_session"})
        self.assertIn("Your session has expired", html_out)
        self.assertIn('data-cta-class="support"', html_out)

    def test_no_view_without_state_is_an_error_not_a_receipt(self):
        with self.assertRaises(ValueError):
            render_thank_you(None, BRAND)


class EscapingRenderTest(unittest.TestCase):
    def test_malicious_display_name_is_escaped(self):
        snapshot = make_snapshot(["MAIN-A"])
        snapshot["line_items"][0]["display_name"] = \
            '<script>alert("x")</script>'
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        html_out = render_thank_you(view, BRAND)
        self.assertNotIn('<script>alert("x")</script>', html_out)
        self.assertIn("&lt;script&gt;", html_out)

    def test_malicious_brand_and_url_are_neutralized(self):
        brand = copy.deepcopy(BRAND)
        brand["brand_name"] = '<img src=x onerror=alert(1)>'
        brand["support"] = {"label": "Support",
                            "url": "javascript:alert(1)"}
        html_out = render_thank_you(resolve(["MAIN-A"]), brand)
        self.assertNotIn("<img src=x", html_out)
        self.assertIn("&lt;img", html_out)
        self.assertNotIn("javascript:alert(1)", html_out)


class CtaClassificationRenderTest(unittest.TestCase):
    def test_all_rendered_ctas_use_allowed_classes(self):
        outputs = [
            render_thank_you(resolve(["MAIN-A"]), BRAND),
            render_thank_you(resolve(["MAIN-A", "BUMP", "U1", "U2"]),
                             BRAND),
            render_thank_you(resolve(["MAIN-A", "D1"],
                                     statuses={"D1": "pending"}), BRAND),
            render_thank_you(resolve(["MAIN-A", "U1"],
                                     statuses={"U1": "failed"}), BRAND),
        ]
        for html_out in outputs:
            assert_ctas_allowed(self, html_out)
            # Structural no-pitch backstop: nothing rendered from a
            # recommendations list, and no offer section exists.
            self.assertNotIn("ty82-offers", html_out)
            self.assertNotIn("Recommended for you", html_out)


class UnknownConfirmationStatusRenderTest(unittest.TestCase):
    """F-01 regression: an unknown confirmation status must fail
    closed, never fall back to the word "Confirmed" next to a pending
    pill. The order-view schema constrains confirmation.status to the
    CONFIRMATION_LABELS enum, so anything else is invalid input and
    the renderer raises, mirroring unknown error/state kinds."""

    def test_unknown_confirmation_status_raises(self):
        view = resolve(["MAIN-A"])
        view["confirmation"]["status"] = "weird_status"
        with self.assertRaises(ValueError):
            render_thank_you(view, BRAND)

    def test_missing_confirmation_status_raises(self):
        view = resolve(["MAIN-A"])
        del view["confirmation"]["status"]
        with self.assertRaises(ValueError):
            render_thank_you(view, BRAND)

    def test_known_statuses_still_render(self):
        html_out = render_thank_you(resolve(["MAIN-A"]), BRAND)
        self.assertIn("Confirmed", html_out)


if __name__ == "__main__":
    unittest.main()
