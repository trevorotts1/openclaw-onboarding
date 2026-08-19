#!/usr/bin/env python3
"""test_upsell_intake_shape.py — Wave E (E2) regression pin for the upsell-flag
intake-shape defect found by the live Wave E run.

GROUND TRUTH THIS FILE PINS
----------------------------
There are TWO live intake paths and, before this fix, they wrote the upsell
flag to TWO DIFFERENT SHAPES:
  * intake_writer.py (the hosted interview-app bridge path) writes the
    documented NESTED shape: `pre_presentation_capture.WANT_SALES_CHECKOUT`.
  * deck-intake-driver.py (THE sanctioned chat intake conversation) writes the
    flag FLAT at intake.json's top level: `WANT_SALES_CHECKOUT` with NO
    `pre_presentation_capture` object at all (its cmd_complete():
    `intake[store_key] = val`, driven by upsell-questions.json's bare
    `storeOn` names).
Both builders' gates (sales_checkout_builder.resolve_sales_checkout_gate,
vsl_builder.resolve_vsl_gate) used to read ONLY the nested shape. A client who
answered "yes" through the chat path (the sanctioned path, and the DEFAULT
answer for sales_checkout) got a flat-shape intake.json, the gate found
nothing at `pre_presentation_capture.WANT_SALES_CHECKOUT`, and silently
DEFERRED -- the pages never built. This file pins the fix: BOTH shapes now
resolve correctly, NESTED preferred, FLAT as fallback, and every existing
defer/build/waived/fail_closed outcome is unchanged.

Unit-level (calls resolve_sales_checkout_gate()/resolve_vsl_gate() directly,
not the full builder) -- fast, deterministic, no filesystem, no network, no
kie.ai spend. Flat file inside tests/, manages its own import path -- matching
every sibling in this directory (test_upsell_verifiers.py, test_waivers.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

import sales_checkout_builder as scb  # noqa: E402
import vsl_builder as vb  # noqa: E402

# ---------------------------------------------------------------------------
# Real live-fixture values, read from the actual Wave E driver-produced
# intake.json (pres-wave-e-zhc-1787175621) -- read-only reference, not copied
# from the live box, just the same field/value shape it carries.
# ---------------------------------------------------------------------------
LIVE_FLAT_FIXTURE = {
    "WANT_SALES_CHECKOUT": "yes",
    "WANT_VSL_PAGE": "yes",
    "OFFER_NAME": "some offer",
    # deliberately no "pre_presentation_capture" key at all, matching the real
    # driver-produced live intake.json this fix targets.
}


# ---------------------------------------------------------------------------
# sales_checkout_builder.resolve_sales_checkout_gate
# ---------------------------------------------------------------------------
class TestSalesCheckoutGateNestedShape:
    """The documented app-bridge contract shape -- must keep working exactly
    as before this fix (regression guard, not new behaviour)."""

    def test_nested_yes_builds(self):
        g = scb.resolve_sales_checkout_gate(
            {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"}})
        assert g["decision"] == "build"

    def test_nested_absent_defers(self):
        g = scb.resolve_sales_checkout_gate({"pre_presentation_capture": {}})
        assert g["decision"] == "defer"

    def test_nested_no_with_reason_waives(self):
        g = scb.resolve_sales_checkout_gate({"pre_presentation_capture": {
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "We already have a checkout page.",
        }})
        assert g["decision"] == "waived"
        assert g["quote"] == "We already have a checkout page."

    def test_nested_no_without_reason_fails_closed(self):
        g = scb.resolve_sales_checkout_gate(
            {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "no"}})
        assert g["decision"] == "fail_closed"
        assert scb.AF_WAIVER_MISSING in g["detail"]


class TestSalesCheckoutGateFlatShape:
    """THE FIX -- deck-intake-driver.py's flat shape, no pre_presentation_capture
    wrapper at all. This is the exact shape that silently deferred before."""

    def test_flat_yes_builds(self):
        g = scb.resolve_sales_checkout_gate({"WANT_SALES_CHECKOUT": "yes"})
        assert g["decision"] == "build"

    def test_flat_and_nested_absent_defers(self):
        g = scb.resolve_sales_checkout_gate({})
        assert g["decision"] == "defer"

    def test_flat_no_with_reason_waives(self):
        g = scb.resolve_sales_checkout_gate({
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "We already have a checkout page.",
        })
        assert g["decision"] == "waived"
        assert g["quote"] == "We already have a checkout page."

    def test_flat_no_without_reason_fails_closed(self):
        g = scb.resolve_sales_checkout_gate({"WANT_SALES_CHECKOUT": "no"})
        assert g["decision"] == "fail_closed"
        assert scb.AF_WAIVER_MISSING in g["detail"]

    def test_flat_no_with_blank_reason_fails_closed(self):
        g = scb.resolve_sales_checkout_gate({
            "WANT_SALES_CHECKOUT": "no",
            "SALES_CHECKOUT_DECLINED_REASON": "   ",
        })
        assert g["decision"] == "fail_closed"

    def test_flat_unrecognized_value_fails_closed(self):
        g = scb.resolve_sales_checkout_gate({"WANT_SALES_CHECKOUT": "maybe"})
        assert g["decision"] == "fail_closed"
        assert scb.AF_VALUE_UNRECOGNIZED in g["detail"]

    def test_live_wave_e_fixture_shape_builds(self):
        """THE DECISIVE PROOF fixture: the real driver-produced live intake.json
        shape (flat 'yes', no pre_presentation_capture) must resolve to build."""
        g = scb.resolve_sales_checkout_gate(dict(LIVE_FLAT_FIXTURE))
        assert g["decision"] == "build"


class TestSalesCheckoutGateResolutionOrder:
    """NESTED preferred over FLAT; a blank nested value still falls through to
    a real FLAT value. Silence is still never consent in either shape."""

    def test_nested_wins_when_both_present(self):
        g = scb.resolve_sales_checkout_gate({
            "pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"},
            "WANT_SALES_CHECKOUT": "no",
        })
        assert g["decision"] == "build"

    def test_blank_nested_falls_through_to_flat(self):
        g = scb.resolve_sales_checkout_gate({
            "pre_presentation_capture": {"WANT_SALES_CHECKOUT": ""},
            "WANT_SALES_CHECKOUT": "yes",
        })
        assert g["decision"] == "build"

    def test_blank_in_both_shapes_still_defers(self):
        g = scb.resolve_sales_checkout_gate({
            "pre_presentation_capture": {"WANT_SALES_CHECKOUT": ""},
            "WANT_SALES_CHECKOUT": "",
        })
        assert g["decision"] == "defer"

    def test_reason_field_same_resolution_order(self):
        # nested reason wins over flat reason when both present.
        g = scb.resolve_sales_checkout_gate({
            "pre_presentation_capture": {
                "WANT_SALES_CHECKOUT": "no",
                "SALES_CHECKOUT_DECLINED_REASON": "Nested reason text here.",
            },
            "SALES_CHECKOUT_DECLINED_REASON": "Flat reason text here.",
        })
        assert g["decision"] == "waived"
        assert g["quote"] == "Nested reason text here."


# ---------------------------------------------------------------------------
# vsl_builder.resolve_vsl_gate
# ---------------------------------------------------------------------------
class TestVslGateNestedShape:
    def test_nested_yes_builds(self):
        g = vb.resolve_vsl_gate({"pre_presentation_capture": {"WANT_VSL_PAGE": "yes"}})
        assert g["decision"] == "build"

    def test_nested_absent_defers(self):
        g = vb.resolve_vsl_gate({"pre_presentation_capture": {}})
        assert g["decision"] == "defer"

    def test_nested_no_with_reason_waives(self):
        g = vb.resolve_vsl_gate({"pre_presentation_capture": {
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": "We don't have a video.",
        }})
        assert g["decision"] == "waived"
        assert g["quote"] == "We don't have a video."

    def test_nested_no_without_reason_fails_closed(self):
        g = vb.resolve_vsl_gate({"pre_presentation_capture": {"WANT_VSL_PAGE": "no"}})
        assert g["decision"] == "fail_closed"
        assert vb.AF_WAIVER_MISSING in g["detail"]


class TestVslGateFlatShape:
    """THE FIX -- deck-intake-driver.py's flat shape, no pre_presentation_capture
    wrapper at all. This is the exact shape that silently deferred before."""

    def test_flat_yes_builds(self):
        g = vb.resolve_vsl_gate({"WANT_VSL_PAGE": "yes"})
        assert g["decision"] == "build"

    def test_flat_and_nested_absent_defers(self):
        g = vb.resolve_vsl_gate({})
        assert g["decision"] == "defer"

    def test_flat_no_with_reason_waives(self):
        g = vb.resolve_vsl_gate({
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": "We don't have a video.",
        })
        assert g["decision"] == "waived"
        assert g["quote"] == "We don't have a video."

    def test_flat_no_without_reason_fails_closed(self):
        g = vb.resolve_vsl_gate({"WANT_VSL_PAGE": "no"})
        assert g["decision"] == "fail_closed"
        assert vb.AF_WAIVER_MISSING in g["detail"]

    def test_flat_no_with_blank_reason_fails_closed(self):
        g = vb.resolve_vsl_gate({
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": "   ",
        })
        assert g["decision"] == "fail_closed"

    def test_flat_unrecognized_value_fails_closed(self):
        g = vb.resolve_vsl_gate({"WANT_VSL_PAGE": "maybe"})
        assert g["decision"] == "fail_closed"
        assert vb.AF_VALUE_UNRECOGNIZED in g["detail"]

    def test_live_wave_e_fixture_shape_builds(self):
        """THE DECISIVE PROOF fixture: the real driver-produced live intake.json
        shape (flat 'yes', no pre_presentation_capture) must resolve to build."""
        g = vb.resolve_vsl_gate(dict(LIVE_FLAT_FIXTURE))
        assert g["decision"] == "build"


class TestVslGateResolutionOrder:
    def test_nested_wins_when_both_present(self):
        g = vb.resolve_vsl_gate({
            "pre_presentation_capture": {"WANT_VSL_PAGE": "yes"},
            "WANT_VSL_PAGE": "no",
        })
        assert g["decision"] == "build"

    def test_blank_nested_falls_through_to_flat(self):
        g = vb.resolve_vsl_gate({
            "pre_presentation_capture": {"WANT_VSL_PAGE": ""},
            "WANT_VSL_PAGE": "yes",
        })
        assert g["decision"] == "build"

    def test_blank_in_both_shapes_still_defers(self):
        g = vb.resolve_vsl_gate({
            "pre_presentation_capture": {"WANT_VSL_PAGE": ""},
            "WANT_VSL_PAGE": "",
        })
        assert g["decision"] == "defer"
