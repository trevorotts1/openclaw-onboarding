#!/usr/bin/env python3
"""WF-E (P9 / C10) — cross-skill + packaging contract regression, B12-B17 / B20-B22.

Owner: WF-E test lane (DeepSeek 1017, separately assigned tests). Scope is TEST
FIXTURES ONLY. This file never edits a repair module, the verifier seam, the
Skill 79 checkout contract, the Skill 81 wrapper, or any production path — it
asserts them.

What it proves (checklist C10, plan §14.2):

  B12  A folded-levels launch gets the APPROVED native contract and nothing
       invented: landing -> checkout with no product_selection node, every
       level kept distinct, and the unsupported checkout shape recorded as an
       explicit `contract_gap` rather than guessed into a Skill 79 mode.
  B13  Only a GENUINE decline routes to D1. payment_pending / payment_failed /
       requires_customer_action retain the stage; a clicked button is not
       payment; abandoned checkout is never a decline.
  B14  U2 eligibility follows the native contract (a verified paid U1 or D1 in
       the same journey). A bump-only order does not qualify, a pending U1 does
       not qualify, and one canonical U2 node exists (no duplicate U2).
  B15  A wrong / stale / cross-tenant / unverified order reference grants
       nothing: no disclosure, no access block, no query-string authority.
  B16  A stale, revoked, narrowed, future-dated, self-issued or MISSING
       approval blocks the action; nothing is synthesized in its place.
  B17  Repeating an approved operation reuses the native object: reconcile
       decides REUSE, the binding refuses a second charge, the purchase machine
       refuses a repeated submission.
  B20  The Skill 50 workflow handoff is DRAFT ONLY — every workflow status is
       `draft`, no step type is unverified, and building the plan opens no
       socket (no email/SMS send).
  B21  Skill 62's refusal is preserved while its gates are incomplete, and the
       media provider is never called to "prove" the gate.
  B22  Installed-vs-reviewed-repository drift is REPORTED (byte mismatch, not
       a git checkout, missing dependency trees, engine version drift), never
       claimed fixed from source alone.

Synthetic/offline only: no network, no real GHL, no client identifiers, no
secrets, no messages sent. Every "native" answer is an in-memory fixture.

Run:  python3 -m pytest tests/test_wf_e_p9_cross_skill.py -q
"""

from __future__ import annotations

import copy
import json
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Every module under test is loaded from its real home. Flat module names in
# this set are unique in the repository (checked by the sibling 83 parity test),
# so a single sys.path entry per tree resolves the intended module.
TOOLS_06 = ROOT / "06-ghl-install-pages" / "tools"
SF49 = ROOT / "49-signature-funnel" / "scripts"
EE50 = ROOT / "50-email-engine" / "tools"
CWFE62 = ROOT / "62-cinematic-web-funnel-engine" / "scripts"
OF79 = ROOT / "79-signature-order-form" / "scripts"
PACKET79 = ROOT / "79-signature-order-form" / "fixtures" / "packet"
UPS80_BINDING = ROOT / "80-signature-upsell" / "components" / "binding"
UPS80_ADAPTERS = ROOT / "80-signature-upsell" / "components" / "adapters"
TY82 = ROOT / "82-signature-thank-you" / "scripts"
LAUNCH83 = ROOT / "83-black-friday-launcher"
ROUTES83 = LAUNCH83 / "routes"

for _p in (TOOLS_06, SF49, EE50, CWFE62, OF79, PACKET79, UPS80_BINDING,
           UPS80_ADAPTERS, TY82, LAUNCH83, ROUTES83):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import browser_manager as bm  # noqa: E402
import emit_build_plan as ebp  # noqa: E402
import extra_offer_binding as binding  # noqa: E402
import ghl_github_reconcile as reconcile06  # noqa: E402
import ghl_recipe_objects as recipes  # noqa: E402
import launch_intake_adapter as intake50  # noqa: E402
import purchase_state  # noqa: E402
import reference_contracts  # noqa: E402
import render_thank_you  # noqa: E402
import route_law  # noqa: E402
import s49_launch_shape  # noqa: E402
import thank_you_resolver  # noqa: E402
from fixture_driver import FixtureDriver  # noqa: E402
from launcher_core import (  # noqa: E402
    checkout as checkout83,
    dependencies as dependencies83,
    intake as intake83,
    page_designs as page_designs83,
    route as route83,
)

SKILL62_VIDEOS = CWFE62 / "generate_videos.py"
THANK_YOU_SNAPSHOT = ROOT / "82-signature-thank-you" / "fixtures" / "test-only-snapshot.json"
GOLDEN_50 = ROOT / "50-email-engine" / "examples" / "golden-signature-launch-10"


# ---------------------------------------------------------------------------
# Fixtures — synthetic, offline, test_only everywhere
# ---------------------------------------------------------------------------

def launch_intake(mode: str, mains: int = 1, **overrides) -> dict:
    """A minimal launch intake that passes Skill 83's own validator."""
    offers = [{"offer_id": f"main-{i + 1}", "name": f"TEST ONLY Level {i + 1}",
               "role": "main",
               "price": {"amount_minor": 49700 + 50000 * i, "currency": "USD"}}
              for i in range(mains)]
    doc = {
        "schema_version": "1.0",
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "journey_mode": mode,
        "brand": {"ref": "brand-test", "hash": "a" * 64},
        "copy_profile": "signature_12_section",
        "approval": {"ref": "approval-test", "hash": "b" * 64},
        "entitlement_attestation": {"basis": "purchase", "evidence_ref": "ev-test",
                                    "attested_by": "operator-test",
                                    "purchase_reference": "order-test"},
        "offers": offers,
        "test_only": True,
    }
    doc.update(overrides)
    return doc


def launch_record(mode: str = "folded_levels") -> dict:
    """The route record the compiler consumes (Skill 83's own shape)."""
    return {
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "revision": 1,
        "journey_mode": mode,
        "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": True},
        "test_only": True,
    }


def snapshot() -> dict:
    return json.loads(THANK_YOU_SNAPSHOT.read_text(encoding="utf-8"))


def line_item(ref: str, slot: str, event_id: str, status: str = "succeeded") -> dict:
    return {
        "native_line_ref": ref,
        "event_id": event_id,
        "offer_id": slot.upper(),
        "slot": slot,
        "display_name": f"TEST ONLY {slot}",
        "currency": "USD",
        "amount_minor": 1000,
        "entitlement_ids": [f"{slot}-entitlement"],
        "payment_status": status,
        "billing": {"billing_type": "one_time", "recurring_interval": None,
                    "schedule": [], "terms_source": None},
    }


def with_lines(snap: dict, items: list) -> dict:
    out = copy.deepcopy(snap)
    out["line_items"] = copy.deepcopy(items)
    out["event_ids"] = sorted({item["event_id"] for item in items})
    return out


def binding_context() -> "binding.BindingContext":
    return binding.BindingContext(
        tenant_ref="tenant:TEST-TENANT",
        location_ref="location:TEST-LOCATION",
        launch_ref="launch:TEST-LAUNCH/r1",
        launch_revision="rev:TEST-LAUNCH-R1",
        parent_order_ref="native:TEST-PARENT-ORDER",
        parent_verification_source="native_purchase_ledger",
        offer_id="TEST-OFFER-U1",
        native_product_ref="native:TEST-PRODUCT",
        native_price_ref="native:TEST-PRICE",
        capability_evidence_ref="native:TEST-CAPABILITY-EVIDENCE",
        amount_minor=6700,
        currency="USD",
        success_route_ref="route:TEST-SUCCESS",
        decline_route_ref="route:TEST-DECLINE",
        error_route_ref="route:TEST-ERROR",
        disclosure_terms_ref="catalog:TEST-OFFER-U1-DISCLOSURE",
        copy_refs=(),
    )


# ---------------------------------------------------------------------------
# B12 — folded levels: approved graph, explicit unsupported-checkout gap
# ---------------------------------------------------------------------------

class TestB12FoldedLevels:
    def test_folded_levels_compiles_landing_to_checkout_with_no_selection_node(self):
        record = launch_record("folded_levels")
        graph = route_law.compile_route(record)["graph"]
        roles = [node["role"] for node in graph["nodes"]]
        assert roles[0] == "landing"
        assert "checkout" in roles
        assert "product_selection" not in roles
        events = {edge["event"] for edge in graph["edges"]}
        assert "selection_validated" not in events
        assert route_law.graph_violations(record, graph) == []

    def test_folded_levels_keeps_every_main_offer_distinct(self):
        doc = intake83.validate(launch_intake("folded_levels", mains=3))
        graph = route83.compile_route(doc)
        mapping = checkout83.order_form_mapping(doc, graph)
        assert [o["offer_id"] for o in mapping["main_offers"]] == ["main-1", "main-2", "main-3"]
        assert len({o["price"]["amount_minor"] for o in mapping["main_offers"]}) == 3
        # One main offer is never relabelled as the whole launch.
        assert mapping["supplied"].get("main_offer_id") is None
        assert mapping["supplied"].get("main_price") is None

    def test_the_unsupported_checkout_shape_is_an_explicit_gap_never_a_guessed_mode(self):
        doc = intake83.validate(launch_intake("folded_levels", mains=3))
        mapping = checkout83.order_form_mapping(doc, route83.compile_route(doc))
        assert mapping["checkout_mode"] is None
        assert mapping["checkout_mode_state"] == "contract_gap"
        # The gap names itself, and checkout_mode stays in the unknown set.
        assert "checkout_mode" in mapping["unknown"]
        assert any("contract" in note and "express neither" in note
                   for note in mapping["notes"]), mapping["notes"]
        # The contract has exactly two modes; neither is invented for this shape.
        assert set(mapping["contract_modes"]) == {"combined_single_offer", "post_selection"}
        assert checkout83.MODE_BY_JOURNEY["folded_levels"] is None
        assert checkout83.MODE_BY_JOURNEY["single_simple"] == "combined_single_offer"
        assert checkout83.MODE_BY_JOURNEY["multiple_options"] == "post_selection"

    def test_the_two_supported_shapes_still_resolve(self):
        for mode, expected in (("single_simple", "combined_single_offer"),
                               ("multiple_options", "post_selection")):
            doc = intake83.validate(launch_intake(mode, mains=1 if mode == "single_simple" else 2))
            mapping = checkout83.order_form_mapping(doc, route83.compile_route(doc))
            assert mapping["checkout_mode"] == expected, mode
            assert mapping["checkout_mode_state"] == "resolved", mode


# ---------------------------------------------------------------------------
# B13 — only a genuine decline routes to D1
# ---------------------------------------------------------------------------

class TestB13DeclineOnlyOnGenuineDecline:
    @pytest.mark.parametrize("event", ["payment_pending", "payment_failed",
                                       "requires_customer_action"])
    def test_a_pending_or_failed_payment_is_never_a_decline(self, event):
        graph = route_law.compile_route(launch_record())["graph"]
        result = route_law.navigate(graph, "upsell_1", event, ["MAIN"],
                                    payment_verified=False)
        assert result["kind"] == "stay_recoverable"
        assert result["to_stage"] == "upsell_1"
        assert result["purchased_after"] == ["MAIN"]

    def test_a_genuine_decline_is_the_only_route_into_d1(self):
        graph = route_law.compile_route(launch_record())["graph"]
        result = route_law.navigate(graph, "upsell_1", "explicit_decline", ["MAIN"],
                                    payment_verified=False)
        assert result["kind"] == "transition"
        assert result["to_stage"] == "downsell_1"
        assert result["guard"] == route_law.DECLINE_GUARD
        assert result["purchased_after"] == ["MAIN"]

    def test_a_clicked_button_is_not_payment(self):
        graph = route_law.compile_route(launch_record())["graph"]
        with pytest.raises(route_law.RouteInvariantError):
            route_law.navigate(graph, "upsell_1", "payment_succeeded", ["MAIN"],
                               payment_verified=False)

    def test_abandoned_checkout_is_not_a_decline(self):
        graph = route_law.compile_route(launch_record())["graph"]
        with pytest.raises(route_law.RouteInvariantError):
            route_law.navigate(graph, "checkout", "explicit_decline", ["MAIN"],
                               payment_verified=False)

    def test_an_unknown_event_never_infers_a_decline(self):
        graph = route_law.compile_route(launch_record())["graph"]
        with pytest.raises(route_law.RouteInvariantError):
            route_law.navigate(graph, "upsell_1", "user_closed_tab", ["MAIN"])

    def test_the_packet_reference_agrees_with_the_compiled_law(self):
        extras = reference_contracts.Extras()
        base = frozenset(["MAIN-A"])
        for event in ("payment_pending", "payment_failed", "requires_customer_action"):
            assert reference_contracts.resolve_after(
                "upsell_1", event, base, extras, False) == ("upsell_1", base)
        assert reference_contracts.resolve_after(
            "upsell_1", "explicit_decline", base, extras, False) == ("downsell_1", base)
        with pytest.raises(ValueError):
            reference_contracts.resolve_after("checkout", "explicit_decline", base, extras, False)


# ---------------------------------------------------------------------------
# B14 — U2 eligibility from verified native purchases; no duplicate U2
# ---------------------------------------------------------------------------

class TestB14U2Eligibility:
    def test_u2_follows_a_verified_paid_u1(self):
        graph = route_law.compile_route(launch_record())["graph"]
        result = route_law.navigate(graph, "upsell_1", "payment_succeeded", ["MAIN"],
                                    payment_verified=True)
        assert result["to_stage"] == "upsell_2"
        assert result["guard"] == route_law.PAID_GUARD["upsell_1"]
        assert result["purchased_after"] == ["MAIN", "U1"]

    def test_u2_follows_a_verified_paid_d1(self):
        graph = route_law.compile_route(launch_record())["graph"]
        result = route_law.navigate(graph, "downsell_1", "payment_succeeded", ["MAIN"],
                                    payment_verified=True)
        assert result["to_stage"] == "upsell_2"
        assert set(result["purchased_after"]) == {"MAIN", "D1"}

    def test_a_bump_only_order_does_not_qualify_u2(self):
        graph = route_law.compile_route(launch_record())["graph"]
        with pytest.raises(route_law.RouteInvariantError):
            route_law.navigate(graph, "upsell_2", "payment_succeeded", ["MAIN", "BUMP"],
                               payment_verified=True)

    def test_the_packet_reference_also_refuses_a_bump_only_u2(self):
        extras = reference_contracts.Extras()
        with pytest.raises(ValueError):
            reference_contracts.resolve_after("upsell_2", "payment_succeeded",
                                              frozenset(["MAIN-A", "BUMP"]), extras, True)

    def test_a_pending_u1_does_not_qualify_u2(self):
        base = [line_item("LINE-MAIN", "main", "EV-MAIN"),
                line_item("LINE-U1", "upsell_1", "EV-U1", status="pending"),
                line_item("LINE-U2", "upsell_2", "EV-U2")]
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(with_lines(snapshot(), base))
        assert "u2_without_qualification" in str(exc.value)
        assert "no PAID" in str(exc.value)

    def test_a_bump_only_order_never_resolves_a_u2_receipt(self):
        base = [line_item("LINE-MAIN", "main", "EV-MAIN"),
                line_item("LINE-BUMP", "bump", "EV-BUMP"),
                line_item("LINE-U2", "upsell_2", "EV-U2")]
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(with_lines(snapshot(), base))
        assert "u2_without_qualification" in str(exc.value)

    def test_a_verified_paid_u1_qualifies_u2(self):
        base = [line_item("LINE-MAIN", "main", "EV-MAIN"),
                line_item("LINE-U1", "upsell_1", "EV-U1"),
                line_item("LINE-U2", "upsell_2", "EV-U2")]
        view = thank_you_resolver.resolve_order_view(with_lines(snapshot(), base))
        assert [item["slot"] for item in view["items"]] == ["main", "upsell_1", "upsell_2"]

    def test_a_redelivered_u2_line_is_one_purchase_not_two(self):
        item = line_item("LINE-U2", "upsell_2", "EV-U2")
        base = [line_item("LINE-MAIN", "main", "EV-MAIN"),
                line_item("LINE-U1", "upsell_1", "EV-U1"), item, copy.deepcopy(item)]
        view = thank_you_resolver.resolve_order_view(with_lines(snapshot(), base))
        assert len([i for i in view["items"] if i["slot"] == "upsell_2"]) == 1

    def test_a_conflicting_redelivery_is_refused_not_merged(self):
        first = line_item("LINE-U2", "upsell_2", "EV-U2")
        second = copy.deepcopy(first)
        second["amount_minor"] = 9999
        base = [line_item("LINE-MAIN", "main", "EV-MAIN"),
                line_item("LINE-U1", "upsell_1", "EV-U1"), first, second]
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(with_lines(snapshot(), base))
        assert "duplicate_conflict" in str(exc.value)

    def test_the_graph_carries_exactly_one_canonical_u2_node(self):
        record = launch_record()
        graph = copy.deepcopy(route_law.compile_route(record)["graph"])
        assert [n["role"] for n in graph["nodes"]].count("upsell_2") == 1
        graph["nodes"].append({"page_id": "TEST-LAUNCH-UPSELL_2B", "role": "upsell_2"})
        violations = route_law.graph_violations(record, graph)
        assert violations, "a second upsell_2 node must violate the route law"

    def test_the_packet_graph_validator_refuses_a_duplicate_u2(self):
        graph = {
            "nodes": [{"page_id": "A", "role": "landing"},
                      {"page_id": "T", "role": "thank_you"},
                      {"page_id": "U2a", "role": "upsell_2"},
                      {"page_id": "U2b", "role": "upsell_2"}],
            "edges": [{"from": "A", "to": "T"}, {"from": "A", "to": "U2a"}],
        }
        with pytest.raises(ValueError) as exc:
            reference_contracts.validate_graph(graph)
        assert "duplicate U2" in str(exc.value)


# ---------------------------------------------------------------------------
# B15 — wrong / stale / cross-tenant order grants nothing
# ---------------------------------------------------------------------------

class TestB15ThankYouTenantChecks:
    def test_a_cross_tenant_order_reference_is_refused(self):
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(
                snapshot(),
                expected_identity={"tenant_id": "OTHER-TENANT",
                                   "location_id": "TEST-LOCATION",
                                   "launch_id": "TEST-LAUNCH"})
        assert "identity_mismatch" in str(exc.value)
        assert "wrong_tenant" in str(exc.value)

    def test_a_wrong_launch_scope_is_refused(self):
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(
                snapshot(),
                expected_identity={"tenant_id": "TEST-TENANT",
                                   "location_id": "TEST-LOCATION",
                                   "launch_id": "OTHER-LAUNCH"})
        assert "wrong_scope" in str(exc.value)

    def test_an_unverified_or_foreign_snapshot_builds_nothing(self):
        unverified = snapshot()
        unverified["verified"] = False
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(unverified)
        assert "unverified_snapshot" in str(exc.value)

    @pytest.mark.parametrize("context", [
        {"query_params": {"vip": "1"}},
        {"query_params": {"entitlement": "extra-full"}},
        {"claimed_entitlement_ids": ["extra-full"]},
    ])
    def test_query_string_and_url_claims_are_never_authority(self, context):
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(snapshot(), request_context=context)
        assert "query_string_authority_rejected" in str(exc.value)

    def test_access_is_granted_only_for_a_paid_item_with_granted_fulfillment(self):
        granted = thank_you_resolver.resolve_order_view(
            snapshot(), fulfillment_map={"base-a": {"state": "granted",
                                                    "delivery_url": "https://test.invalid/a",
                                                    "next_action": "access"}})
        assert len(granted["access_blocks"]) == 1
        pending = thank_you_resolver.resolve_order_view(
            snapshot(), fulfillment_map={"base-a": {"state": "pending"}})
        assert pending["access_blocks"] == []
        missing = thank_you_resolver.resolve_order_view(snapshot())
        assert missing["access_blocks"] == []

    def test_an_unapproved_fulfillment_action_is_refused_not_passed_through(self):
        with pytest.raises(thank_you_resolver.ResolverError) as exc:
            thank_you_resolver.resolve_order_view(
                snapshot(),
                fulfillment_map={"base-a": {"state": "granted",
                                            "next_action": "buy_more"}})
        assert "invalid_next_action" in str(exc.value)

    def test_the_rendered_error_discloses_no_order_data(self):
        view = thank_you_resolver.resolve_order_view(
            snapshot(), fulfillment_map={"base-a": {"state": "granted"}})
        for kind in render_thank_you.ERROR_KINDS:
            fragment = render_thank_you.render_error(kind)
            assert "TEST-ORDER-0001" not in fragment
            assert "TEST ONLY" not in fragment
            assert "9700" not in fragment
            assert "$" not in fragment
        rendered = render_thank_you.render_order_view(view)
        assert "buy_more" not in rendered
        assert 'data-cta-class="buy_more"' not in rendered


# ---------------------------------------------------------------------------
# B16 — stale / missing approval blocks the action
# ---------------------------------------------------------------------------

def plan_approval(launch: dict, **overrides) -> dict:
    record = {
        "schema_version": "1.0",
        "approval_id": "APPR-TEST",
        "subject_type": s49_launch_shape.PLAN_BUILD_APPROVAL_TYPE,
        "subject_hash": s49_launch_shape.plan_document_hash(launch),
        "owner_identity_ref": "client-test",
        "source_message_ref": "msg-test",
        "recorded_at": "2026-10-21T00:00:00Z",
        "scope": [s49_launch_shape.PLAN_BUILD_APPROVAL_TYPE],
        "revoked": False,
        "verification_class": sorted(s49_launch_shape.VERIFICATION_CLASSES)[0],
    }
    record.update(overrides)
    return record


NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)
PLAN_LAUNCH = {"tenant_id": "TEST-TENANT", "location_id": "TEST-LOCATION",
               "launch_id": "TEST-LAUNCH", "revision": 1}


class TestB16StaleApprovalBlocks:
    def test_a_current_approval_binds(self):
        result = s49_launch_shape.check_plan_build_approval(
            PLAN_LAUNCH, plan_approval(PLAN_LAUNCH),
            client_identity_ref="client-test", worker_identity_ref="worker-test", now=NOW)
        assert result["ok"] is True
        assert result["subject_hash"] == s49_launch_shape.plan_document_hash(PLAN_LAUNCH)

    @pytest.mark.parametrize("overrides,expected", [
        ({"subject_hash": "0" * 64}, "does not match the current plan"),
        ({"revoked": True}, "revoked"),
        ({"scope": []}, "authorizes nothing"),
        ({"scope": ["launch_plan_build_narrowed"]}, "authorizes nothing"),
        ({"subject_type": "design_board"}, "approval types are separate"),
        ({"recorded_at": "2099-01-01T00:00:00Z"}, "in the future"),
        ({"recorded_at": "not-a-timestamp"}, "not a valid timestamp"),
        ({"source_message_ref": ""}, "platform reference"),
        ({"verification_class": "self_asserted"}, "verification_class"),
    ])
    def test_a_stale_or_malformed_approval_blocks_the_action(self, overrides, expected):
        with pytest.raises(s49_launch_shape.ShapeError) as exc:
            s49_launch_shape.check_plan_build_approval(
                PLAN_LAUNCH, plan_approval(PLAN_LAUNCH, **overrides),
                client_identity_ref="client-test", worker_identity_ref="worker-test", now=NOW)
        assert expected in str(exc.value)

    def test_an_approval_for_another_plan_does_not_authorize_this_one(self):
        other = dict(PLAN_LAUNCH, launch_id="OTHER-LAUNCH")
        with pytest.raises(s49_launch_shape.ShapeError) as exc:
            s49_launch_shape.check_plan_build_approval(
                PLAN_LAUNCH, plan_approval(other),
                client_identity_ref="client-test", worker_identity_ref="worker-test", now=NOW)
        assert "another plan" in str(exc.value)

    def test_the_worker_cannot_approve_its_own_work(self):
        with pytest.raises(s49_launch_shape.ShapeError) as exc:
            s49_launch_shape.check_plan_build_approval(
                PLAN_LAUNCH, plan_approval(PLAN_LAUNCH, owner_identity_ref="worker-test"),
                client_identity_ref="worker-test", worker_identity_ref="worker-test", now=NOW)
        assert "self-approval" in str(exc.value)

    def test_an_empty_approval_record_authorizes_nothing(self):
        for empty in ({}, None, "approved"):
            with pytest.raises(s49_launch_shape.ShapeError):
                s49_launch_shape.check_plan_build_approval(
                    PLAN_LAUNCH, empty, client_identity_ref="client-test", now=NOW)

    def test_a_missing_intake_approval_fails_closed_by_name(self):
        doc = launch_intake("single_simple", approval={"ref": "", "hash": ""})
        with pytest.raises(intake83.IntakeError) as exc:
            intake83.validate(doc)
        assert "AF-LAUNCH-INTAKE-MISSING" in str(exc.value)
        assert "approval.ref" in str(exc.value)

    def test_design_approvals_are_never_synthesized(self):
        approvals = page_designs83.default_approvals()
        assert approvals
        for name, record in approvals.items():
            assert record["state"] == "awaiting_client_approval", name
            assert record["approval_ref"] is None, name


# ---------------------------------------------------------------------------
# B17 — a repeated operation reuses the native object
# ---------------------------------------------------------------------------

FUNNEL_ROWS = [{"id": "NATIVE-FUNNEL-1", "locationId": "TEST-LOCATION",
                "name": "TEST ONLY Launch Funnel", "type": "funnel"}]


class TestB17RepeatReusesNativeObject:
    def test_a_recorded_native_id_reuses_the_object(self):
        result = recipes.reconcile(FUNNEL_ROWS, kind="funnel",
                                   location_id="TEST-LOCATION",
                                   native_id="NATIVE-FUNNEL-1")
        assert result.action == recipes.REUSE
        assert result.ok is True
        assert result.identity is not None
        assert result.identity.native_id == "NATIVE-FUNNEL-1"

    def test_a_second_run_after_create_reuses_rather_than_duplicates(self):
        first = recipes.reconcile([], kind="funnel", location_id="TEST-LOCATION",
                                  name="TEST ONLY Launch Funnel")
        assert first.action == recipes.CREATE
        created_row = {"id": "NATIVE-FUNNEL-NEW", "locationId": "TEST-LOCATION",
                       "name": "TEST ONLY Launch Funnel", "type": "funnel"}
        second = recipes.reconcile([created_row], kind="funnel",
                                   location_id="TEST-LOCATION",
                                   name="TEST ONLY Launch Funnel")
        assert second.action == recipes.REUSE
        assert second.identity.native_id == "NATIVE-FUNNEL-NEW"
        # And by the recorded id, which is the strongest evidence there is.
        third = recipes.reconcile([created_row], kind="funnel",
                                  location_id="TEST-LOCATION",
                                  native_id="NATIVE-FUNNEL-NEW")
        assert third.action == recipes.REUSE
        assert len([created_row]) == 1

    def test_a_name_collision_elsewhere_is_neither_adopted_nor_overwritten(self):
        result = recipes.reconcile(FUNNEL_ROWS, kind="funnel",
                                   location_id="OTHER-LOCATION",
                                   name="TEST ONLY Launch Funnel")
        assert result.action == recipes.REFUSE_COLLISION
        assert result.refused is True
        assert "neither adopted nor overwritten" in result.reason

    def test_an_unproven_read_can_never_license_a_create(self):
        result = recipes.reconcile([], kind="funnel", location_id="TEST-LOCATION",
                                   name="TEST ONLY New Funnel", read_complete=False)
        assert result.action == recipes.REFUSE_UNPROVEN_READ
        assert result.refused is True

    def test_a_repeat_accept_never_issues_a_second_charge(self):
        offer = binding.ExtraOfferBinding(binding_context())
        offer.presentation_decision(True)
        driver = FixtureDriver("paid_with_readback")
        first = offer.accept(driver)
        assert first.state == binding.PAID
        assert len(driver.invoke_calls) == 1
        with pytest.raises(binding.BindingError) as exc:
            offer.accept(driver)
        assert "no duplicate charge" in str(exc.value)
        assert len(driver.invoke_calls) == 1

    def test_a_pending_outcome_blocks_the_retry_instead_of_charging_twice(self):
        offer = binding.ExtraOfferBinding(binding_context())
        offer.presentation_decision(True)
        driver = FixtureDriver("pending_then_paid")
        first = offer.accept(driver)
        assert first.state == binding.PENDING_CONFIRMATION
        assert offer.unresolved is True
        with pytest.raises(binding.BindingError):
            offer.accept(driver)
        assert len(driver.invoke_calls) == 1
        resolved = offer.reconcile(driver)
        assert resolved.state == binding.PAID

    def test_a_repeated_submission_is_rejected_by_the_purchase_machine(self):
        attempt = purchase_state.PurchaseAttempt()
        attempt.apply("begin_validation")
        attempt.apply("submit")
        with pytest.raises(purchase_state.StateError) as exc:
            attempt.apply("submit")
        assert "repeated submission" in str(exc.value)

    def test_paid_is_terminal_and_an_unknown_outcome_must_be_reconciled_first(self):
        paid = purchase_state.PurchaseAttempt()
        paid.apply("begin_validation")
        paid.apply("submit")
        paid.apply("native_paid_verified")
        assert paid.can_traverse_paid_edge() is True
        with pytest.raises(purchase_state.StateError):
            paid.apply("native_failed")

        unknown = purchase_state.PurchaseAttempt()
        unknown.apply("begin_validation")
        unknown.apply("submit")
        unknown.apply("timeout_unknown_outcome")
        assert unknown.can_traverse_paid_edge() is False
        with pytest.raises(purchase_state.StateError) as exc:
            unknown.apply("retry_after_reconciliation")
        assert "reconciled against native records" in str(exc.value)
        assert unknown.record_reconciliation(False) == "failed"
        assert unknown.apply("retry_after_reconciliation") == "ready"


# ---------------------------------------------------------------------------
# B20 — Skill 50 handoff is draft only, and sends nothing
# ---------------------------------------------------------------------------

class TestB20Skill50DraftOnly:
    @staticmethod
    def _plan() -> dict:
        brief = json.loads((GOLDEN_50 / "brief.json").read_text(encoding="utf-8"))
        emails = json.loads((GOLDEN_50 / "emails.json").read_text(encoding="utf-8"))
        return ebp.build_plan(brief, emails)

    def test_every_emitted_workflow_is_a_draft(self):
        plan = self._plan()
        workflows = [k for k in plan if k not in ("folder", "_meta")]
        assert workflows
        for key in workflows:
            assert plan[key]["status"] == "draft", key
        assert plan["_meta"]["draft_only"] is True
        assert plan["_meta"]["deploy_mode"] == "draft-only"
        assert ebp.validate_plan(plan) == []

    def test_no_step_type_is_unverified(self):
        plan = self._plan()
        for key in [k for k in plan if k not in ("folder", "_meta")]:
            for step in plan[key]["templates"]:
                assert step["type"] in ebp.VERIFIED_STEP_TYPES, step["type"]

    def test_building_the_handoff_opens_no_socket(self, monkeypatch):
        """A send would need the network. Building the plan must not touch it."""
        def _refuse(*args, **kwargs):
            raise AssertionError("the draft handoff must not open a socket")

        monkeypatch.setattr(socket, "socket", _refuse)
        monkeypatch.setattr(socket, "create_connection", _refuse)
        plan = self._plan()
        assert plan["_meta"]["draft_only"] is True

    @pytest.mark.parametrize("unit,expected", [
        ({"id": "s1", "provider": "skill50", "draft_only": False,
          "kind": "main_launch", "email_count": 10}, "not draft_only"),
        ({"id": "s1", "provider": "skill50", "draft_only": True,
          "kind": "main_launch", "email_count": 7}, "declares 7 emails"),
        ({"id": "s1", "provider": "other_engine", "draft_only": True,
          "kind": "main_launch", "email_count": 10}, "plans no Skill 50 email sequence"),
    ])
    def test_a_non_draft_or_miscounted_handoff_is_refused(self, unit, expected):
        with pytest.raises(intake50.Refusal) as exc:
            intake50._launch_sequences({"email_sequences": [unit]})
        assert expected in str(exc.value)

    def test_an_empty_handoff_is_refused(self):
        with pytest.raises(intake50.Refusal):
            intake50._launch_sequences({"email_sequences": []})


# ---------------------------------------------------------------------------
# B21 — Skill 62 refusal is preserved while its gates are incomplete
# ---------------------------------------------------------------------------

class _RecordingProvider:
    """A media provider that records any call and never answers."""

    def __init__(self) -> None:
        self.calls: list = []

    def __getattr__(self, name):
        def _call(*args, **kwargs):
            self.calls.append(name)
            return (False, "TEST ONLY: the provider must not be reached")
        return _call


class TestB21Skill62RefusalPreserved:
    @staticmethod
    def _videos():
        import importlib.util
        spec = importlib.util.spec_from_file_location("wf_e_p9_skill62_videos", SKILL62_VIDEOS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_draft_clips_refuse_before_the_anchor_approval_exists(self):
        videos = self._videos()
        provider = _RecordingProvider()
        with tempfile.TemporaryDirectory() as tmp:
            passed, detail = videos.generate_draft_clips(Path(tmp), provider=provider)
        assert passed is False
        assert "anchor-approval.json does not exist yet" in detail
        assert "P6-ANCHOR must run first" in detail
        assert provider.calls == [], "a refusal must never reach the paid provider"

    def test_final_clips_refuse_before_a_draft_receipt_exists(self):
        videos = self._videos()
        provider = _RecordingProvider()
        with tempfile.TemporaryDirectory() as tmp:
            passed, detail = videos.generate_final_scene_clips(Path(tmp), provider=provider)
        assert passed is False
        assert "draft-media-receipt.json does not exist yet" in detail
        assert provider.calls == []

    def test_final_media_approval_refuses_before_the_asset_ledger_exists(self):
        videos = self._videos()
        with tempfile.TemporaryDirectory() as tmp:
            passed, detail = videos.approve_final_media(Path(tmp), approved_by="operator-test")
        assert passed is False
        assert "video-asset-ledger.json does not exist yet" in detail

    def test_an_empty_approver_is_refused_rather_than_defaulted(self):
        videos = self._videos()
        with tempfile.TemporaryDirectory() as tmp:
            for approver in ("", "   "):
                passed, detail = videos.approve_draft_clips(Path(tmp), approved_by=approver)
                assert passed is False
                assert "approved_by" in detail

    def test_the_refusal_is_a_gate_not_a_crash(self):
        """Refusal is a returned verdict with a named reason, never an exception
        the caller could mistake for a transient error and retry blindly."""
        videos = self._videos()
        with tempfile.TemporaryDirectory() as tmp:
            passed, detail = videos.generate_draft_clips(Path(tmp),
                                                         provider=_RecordingProvider())
        assert (passed, isinstance(detail, str)) == (False, True)
        assert detail.strip() != ""


# ---------------------------------------------------------------------------
# B22 — installed vs reviewed repository drift is reported, never claimed fixed
# ---------------------------------------------------------------------------

class TestB22InstalledRepoDrift:
    def test_a_directory_that_is_not_a_git_checkout_is_not_treated_as_the_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            source = Path(tmp) / "source"
            repo.mkdir()
            source.mkdir()
            (repo / "index.html").write_text("TEST", encoding="utf-8")
            (source / "index.html").write_text("TEST", encoding="utf-8")
            result = reconcile06.verify_repo_byte_match(str(repo), str(source))
        assert result["match"] is False
        assert "not a git repository" in result["reason"]

    def test_a_byte_mismatch_is_reported_as_drift_not_as_a_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            source = Path(tmp) / "source"
            (repo / ".git").mkdir(parents=True)
            source.mkdir()
            (repo / "index.html").write_text("REVIEWED", encoding="utf-8")
            (source / "index.html").write_text("INSTALLED", encoding="utf-8")
            result = reconcile06.verify_repo_byte_match(str(repo), str(source))
        assert result["match"] is False
        assert "byte mismatch" in result["reason"]
        # The report names both sides; nothing claims the installed copy changed.
        assert result["repo_path"] and result["source_path"]

    def test_a_byte_identical_pair_reports_a_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            source = Path(tmp) / "source"
            (repo / ".git").mkdir(parents=True)
            source.mkdir()
            (repo / "index.html").write_text("SAME", encoding="utf-8")
            (source / "index.html").write_text("SAME", encoding="utf-8")
            result = reconcile06.verify_repo_byte_match(str(repo), str(source))
        assert result["match"] is True

    def test_a_missing_file_on_either_side_is_a_reported_non_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            source = Path(tmp) / "source"
            (repo / ".git").mkdir(parents=True)
            source.mkdir()
            result = reconcile06.verify_repo_byte_match(str(repo), str(source))
        assert result["match"] is False
        assert "not found" in result["reason"]

    def test_a_dependency_report_names_what_is_missing_and_enables_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "83-black-friday-launcher").mkdir()
            (root / "83-black-friday-launcher" / "SKILL.md").write_text(
                "---\nname: black-friday-launcher\n---\n", encoding="utf-8")
            (root / "49-signature-funnel").mkdir()
            before = sorted(p.name for p in root.rglob("*"))
            report = dependencies83.check(root=root)
            after = sorted(p.name for p in root.rglob("*"))
        assert before == after, "a dependency check must not write into the tree it inspects"
        assert report["would_enable"] is False
        assert report["enabled_in_999"] is False
        assert report["blockers"], "missing required trees must be reported as blockers"
        assert "tree-78-signature-product-selection" in report["missing"]
        assert "tree-49-signature-funnel" in report["present"]
        # Every entry carries the evidence that produced its verdict.
        assert all(entry["evidence"] for entry in report["entries"])

    def test_the_reviewed_repository_reports_its_own_state_honestly(self):
        """B22: a repository checkout is not a deployed runtime.

        Every verdict is carried with its evidence; a required thing this
        interpreter cannot see (a runtime package under an isolated
        interpreter) is reported as a BLOCKER, never folded into "present",
        and `enabled_in_999` follows the blockers instead of the source tree.
        """
        report = dependencies83.check()
        seen_from = Path(report["seen_from"])
        assert (seen_from / "83-black-friday-launcher").is_dir(), report["seen_from"]
        by_id = {entry["id"]: entry for entry in report["entries"]}
        assert all(entry["evidence"] for entry in report["entries"])
        # The three verdict buckets partition the entries exactly.
        assert set(report["present"]) | set(report["missing"]) | set(
            report["unverifiable"]) == set(by_id)
        assert not (set(report["present"]) & set(report["missing"]))
        # The repository's own skill trees are present in the reviewed checkout.
        assert all(by_id[name]["status"] == "present"
                   for name in ("tree-49-signature-funnel", "tree-79-signature-order-form",
                                "tree-80-signature-upsell", "tree-81-signature-downsell",
                                "tree-82-signature-thank-you"))
        # A blocker is always named in `missing` and always disables enablement.
        for blocker in report["blockers"]:
            assert blocker in report["missing"], blocker
            assert by_id[blocker]["required"] is True, blocker
        assert report["enabled_in_999"] is False or report["blockers"] == []
        assert report["would_enable"] is (report["blockers"] == [])
        # A runtime probe is an interpreter fact, so it is reported as one:
        # under `python3 -I` the same source tree can lose a runtime package.
        for entry in report["entries"]:
            if entry["kind"] == "runtime_package":
                assert "isolated_interpreter=" in entry["evidence"], entry["evidence"]
                assert "find_spec" in entry["evidence"], entry["evidence"]

    def test_a_duplicate_native_name_in_scope_is_refused_not_guessed(self):
        rows = [dict(FUNNEL_ROWS[0]), {"id": "NATIVE-FUNNEL-2",
                                       "locationId": "TEST-LOCATION",
                                       "name": "TEST ONLY Launch Funnel",
                                       "type": "funnel"}]
        result = recipes.reconcile(rows, kind="funnel", location_id="TEST-LOCATION",
                                   name="TEST ONLY Launch Funnel")
        assert result.action == recipes.REFUSE_AMBIGUOUS
        assert result.refused is True

    def test_an_engine_version_drift_is_refused_not_silently_accepted(self, monkeypatch):
        monkeypatch.setattr(bm, "_read_live_agent_browser_version", lambda: "9.9.9")
        with pytest.raises(RuntimeError) as exc:
            bm.assert_agent_browser_version({"GHL_AB_PINNED_VERSION": "0.27.0"})
        assert "version-pin guard" in str(exc.value)
        assert "0.27.0" in str(exc.value)

    def test_the_drift_override_is_an_explicit_acknowledged_warning(self, monkeypatch, capsys):
        monkeypatch.setattr(bm, "_read_live_agent_browser_version", lambda: "9.9.9")
        bm.assert_agent_browser_version({"GHL_AB_PINNED_VERSION": "0.27.0",
                                         "GHL_AB_ALLOW_VERSION_DRIFT": "1"})
        captured = capsys.readouterr()
        assert "WARN" in captured.err
        assert "risk acknowledged" in captured.err

    def test_an_unreadable_engine_version_is_refused_by_default(self, monkeypatch):
        monkeypatch.setattr(bm, "_read_live_agent_browser_version", lambda: None)
        with pytest.raises(RuntimeError) as exc:
            bm.assert_agent_browser_version({"GHL_AB_PINNED_VERSION": "0.27.0"})
        assert "could not determine agent-browser version" in str(exc.value)
