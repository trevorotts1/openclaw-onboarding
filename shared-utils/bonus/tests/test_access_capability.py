#!/usr/bin/env python3
"""Self-check for T-14 — bonus membership/access capability decision.

Pins every acceptance clause of the task record (R-13, C-14, C-F07) and the
refusal cases, so a future edit cannot quietly promote an unproved step to
"supported" or gate the original gift on the bonus lane.

  C-14  current official route/tenant requirements, mobile-only
        identity/token/recovery evidence or the EXACT capability block, and no
        fabricated API;
  C-F07 original gift proceeds while the bonus is unavailable.

Run: python3 -m unittest discover -s shared-utils/bonus/tests -v
     python3 -m unittest shared-utils.bonus.tests.test_access_capability -v
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_BONUS = _TESTS.parent
_SHARED = _BONUS.parent
_REPO = _SHARED.parent
for _p in (str(_SHARED), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bonus import access_capability as ac  # noqa: E402


class TestCapabilityBlock(unittest.TestCase):
    """C-14: the exact block, announced rather than an invented interface."""

    def test_every_step_is_declared_exactly_once_in_order(self):
        self.assertEqual(list(ac.STEP_ORDER), ["identity", "grant", "credential", "return", "recovery"])
        self.assertEqual([e.step for e in ac.EVIDENCE], list(ac.STEP_ORDER))

    def test_all_five_steps_are_blocked_today(self):
        self.assertEqual(ac.blocked_steps(), list(ac.STEP_ORDER))

    def test_every_step_names_the_exact_missing_evidence(self):
        for step, row in ac.capability_evidence().items():
            self.assertFalse(row["routable"], f"{step} was promoted to routable")
            self.assertTrue(row["missing"], f"{step} names no missing evidence")
            for clause in row["missing"]:
                self.assertTrue(str(clause).strip(), f"{step} carries a blank missing clause")
            self.assertTrue(row["authority"], f"{step} cites no authority")
            self.assertTrue(row["claim"].strip(), f"{step} carries no claim")

    def test_every_provenance_file_exists_in_this_tree(self):
        for step, row in ac.capability_evidence().items():
            self.assertTrue(row["provenance"], f"{step} cites no provenance")
            for rel in row["provenance"]:
                self.assertFalse(os.path.isabs(rel), f"{step} provenance must be repo-relative: {rel}")
                self.assertTrue(
                    (_REPO / rel).is_file(), f"{step} provenance does not exist: {rel}"
                )

    def test_no_step_is_proved_or_claims_a_tenant_observation(self):
        for step, row in ac.capability_evidence().items():
            self.assertNotEqual(row["state"], ac.PROVED, step)
            self.assertNotIn("verified on this box", row["claim"].lower(), step)


class TestNoFabricatedApi(unittest.TestCase):
    """C-14: no fabricated API anywhere in the route surface."""

    def test_supported_route_exposes_no_api(self):
        route = ac.supported_route()
        self.assertIsNone(route["api"])
        self.assertTrue(route["no_invented_api"])
        self.assertNotIn("endpoint", route["supported_path"].lower())

    def test_route_values_contain_no_url_or_verb_path(self):
        blob = json.dumps(ac.supported_route(), sort_keys=True)
        self.assertIsNone(re.search(r"https?://", blob))
        self.assertIsNone(re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", blob))

    def test_module_source_carries_no_url_or_verb_path(self):
        source = Path(ac.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?://", source), "module carries a URL")
        self.assertIsNone(
            re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9{]", source),
            "module carries a verb+path operation",
        )

    def test_membership_family_has_no_route_in_the_shared_inventory(self):
        # Reuse of the upstream inventory, not a second local table.
        self.assertEqual(ac.membership_inventory_routes(), [])

    def test_supported_route_reports_the_block_reason(self):
        route = ac.supported_route()
        self.assertFalse(route["available"])
        self.assertFalse(route["advertised_bonus_ready"])
        self.assertEqual(route["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(route["route"], "assisted_operator")


class TestRequestRefusal(unittest.TestCase):
    """C-14: an unattended grant is refused, never silently downgraded."""

    def test_unattended_request_is_refused_with_the_exact_block(self):
        result = ac.request_bonus_access(unattended=True)
        self.assertFalse(result["granted"])
        self.assertTrue(result["refused"])
        self.assertEqual(result["route"], "refused")
        self.assertEqual(result["reason_code"], ac.BLOCK_REASON)
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))
        self.assertTrue(result["no_silent_downgrade"])
        for step in ac.STEP_ORDER:
            self.assertIn(step, result["reason"])

    def test_refusal_offers_exactly_the_assisted_route(self):
        offer = ac.request_bonus_access(unattended=True)["offer"]
        self.assertEqual(offer["route"], "assisted_operator")
        self.assertEqual(offer["next"], "prepare_operator_instruction")

    def test_assisted_request_awaits_the_operator_and_has_no_receipt(self):
        result = ac.request_bonus_access(unattended=False)
        self.assertFalse(result["granted"])
        self.assertFalse(result["refused"])
        self.assertEqual(result["route"], "assisted_operator")
        self.assertEqual(result["status"], "awaiting-operator")
        self.assertIsNone(result["receipt"])
        self.assertFalse(result["system_claimed_grant"])
        self.assertEqual(result["blocked_steps"], list(ac.STEP_ORDER))

    def test_non_bool_unattended_is_refused(self):
        for value in ("yes", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.request_bonus_access(unattended=value)  # type: ignore[arg-type]


class TestOriginalGiftIndependence(unittest.TestCase):
    """C-F07: the original gift proceeds while the bonus is unavailable."""

    def test_original_is_ready_while_bonus_is_unavailable(self):
        plan = ac.plan_fulfillment(original_ready=True)
        self.assertTrue(plan["original"]["ready"])
        self.assertEqual(plan["original"]["route"], "direct_chat")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertFalse(plan["original"]["depends_on_bonus"])
        self.assertFalse(plan["bonus"]["available"])
        self.assertFalse(plan["advertised_bonus_ready"])
        self.assertEqual(plan["continuation"], "original_only")

    def test_a_not_ready_original_names_its_own_reason_never_the_bonus(self):
        plan = ac.plan_fulfillment(
            original_ready=False, original_reason="asset not yet approved for release"
        )
        self.assertFalse(plan["original"]["ready"])
        self.assertEqual(plan["original"]["reason"], "asset not yet approved for release")
        self.assertFalse(plan["original"]["blocked_by_bonus"])
        self.assertEqual(plan["continuation"], "original_repair")
        self.assertNotIn("bonus", plan["original"]["reason"].lower())

    def test_a_not_ready_original_must_name_its_reason(self):
        for reason in ("", "   "):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(original_ready=False, original_reason=reason)

    def test_original_lane_is_identical_when_the_bonus_lane_changes(self):
        # Prove no coupling: even a hypothetical proved bonus cannot move the
        # original lane. Same inputs must yield the same original dict.
        before = ac.plan_fulfillment(original_ready=True)["original"]
        proved = {
            "available": True,
            "route": "unattended",
            "blocked_steps": [],
            "missing_evidence": {},
            "api": None,
            "no_invented_api": True,
            "advertised_bonus_ready": True,
        }
        with _patched_route(proved):
            after_plan = ac.plan_fulfillment(original_ready=True)
        self.assertEqual(before, after_plan["original"])
        self.assertEqual(after_plan["continuation"], "original_and_bonus")

    def test_the_guard_rejects_a_hand_built_coupled_plan(self):
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["blocked_by_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        coupled = ac.plan_fulfillment(original_ready=True)
        coupled["original"]["depends_on_bonus"] = True
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus(coupled)
        with self.assertRaises(ac.BonusCouplingError):
            ac.assert_original_not_gated_by_bonus({"bonus": {}})

    def test_non_bool_plan_inputs_are_refused(self):
        for kwargs in (
            {"original_ready": "true"},
            {"original_ready": True, "bonus_requested": "no"},
        ):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.plan_fulfillment(**kwargs)  # type: ignore[arg-type]


class TestCredentialVersusResource(unittest.TestCase):
    """R-13: an expired credential is not expired guides."""

    def test_expired_credential_does_not_close_authorized_guides(self):
        state = ac.resolve_member_state(credential_state="expired", resource_authorized=True)
        self.assertFalse(state["credential_valid"])
        self.assertTrue(state["resource_available"])
        self.assertFalse(state["conflated"])
        self.assertIn("nothing about the guides", state["statement"])

    def test_valid_credential_does_not_authorize_guides(self):
        state = ac.resolve_member_state(credential_state="valid", resource_authorized=False)
        self.assertTrue(state["credential_valid"])
        self.assertFalse(state["resource_available"])

    def test_resource_availability_ignores_the_credential_on_every_state(self):
        for cred in ac.CREDENTIAL_STATES:
            self.assertTrue(
                ac.resolve_member_state(credential_state=cred, resource_authorized=True)[
                    "resource_available"
                ],
                cred,
            )
            self.assertFalse(
                ac.resolve_member_state(credential_state=cred, resource_authorized=False)[
                    "resource_available"
                ],
                cred,
            )

    def test_unknown_credential_state_is_refused(self):
        for value in ("good", "", None, "expir'd"):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state=value, resource_authorized=True)  # type: ignore[arg-type]

    def test_uppercase_and_padded_credential_state_is_normalised(self):
        state = ac.resolve_member_state(credential_state=" EXPIRED ", resource_authorized=True)
        self.assertEqual(state["credential_state"], "expired")

    def test_non_bool_authorization_is_refused(self):
        for value in ("true", 1, None):
            with self.assertRaises(ac.BonusCapabilityError):
                ac.resolve_member_state(credential_state="valid", resource_authorized=value)  # type: ignore[arg-type]


class TestDecisionDocument(unittest.TestCase):
    def test_document_is_serialisable_and_self_consistent(self):
        doc = ac.decision_document()
        blob = json.dumps(doc, sort_keys=True)
        round_trip = json.loads(blob)
        self.assertEqual(round_trip["verdict"], "BLOCKED")
        self.assertEqual(round_trip["blocked_steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["steps"], list(ac.STEP_ORDER))
        self.assertEqual(round_trip["check_ids"], ["C-14", "C-F07"])
        self.assertTrue(round_trip["original_gift_independent"])
        self.assertIsNone(round_trip["route"]["api"])
        self.assertEqual(set(round_trip["evidence"]), set(ac.STEP_ORDER))


class _patched_route:
    """Context manager: replace supported_route with a hypothetical proved one."""

    def __init__(self, value):
        self.value = value
        self._orig = None

    def __enter__(self):
        self._orig = ac.supported_route
        ac.supported_route = lambda: dict(self.value)
        return self

    def __exit__(self, *exc):
        ac.supported_route = self._orig
        return False


if __name__ == "__main__":
    unittest.main(verbosity=2)
