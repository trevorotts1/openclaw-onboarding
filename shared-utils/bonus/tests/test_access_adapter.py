#!/usr/bin/env python3
"""Proofs for the T-15 bonus access adapter: R-13 / R-27, check C-15.

Acceptance, verbatim: "Separate identity/grant/credential/SMS/resource
authorization; return access and email-later same member."

Every clause is pinned, including the refusals:
  the five dimensions are separate (a sweep of one never moves another),
  a denial never cascades and a pass never mints a sibling pass,
  credential is not resource and SMS permission is not identity,
  one member owns both channel handles and a handle cannot move,
  a failed step is recorded against the member the channel resolved to,
  email-later defers the SAME member,
  and a resume lands on that member over the channel it arrived on.

Run: python3 -I shared-utils/bonus/tests/test_access_adapter.py
No network, no provider, no model.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
sys.path.insert(0, str(MODULE))

import access_adapter as a  # noqa: E402


def _states(**overrides):
    base = {d: a.UNVERIFIED for d in a.DIMENSIONS}
    base.update(overrides)
    return base


class TestTheDimensionsAreSeparate(unittest.TestCase):
    def test_the_five_dimensions_are_declared_once_in_fixed_order(self):
        self.assertEqual(
            a.DIMENSIONS, ("identity", "grant", "credential", "sms", "resource")
        )
        self.assertEqual(len(set(a.DIMENSIONS)), len(a.DIMENSIONS))
        self.assertEqual(sorted(a._STATES), sorted(["authorized", "denied", "unverified"]))

    def test_all_five_authorized_authorizes_the_member(self):
        auth = a.authorize(
            member_id="m-1", states={d: a.AUTHORIZED for d in a.DIMENSIONS}
        )
        self.assertTrue(auth.authorized)
        self.assertEqual(auth.blocked_dimensions, [])
        self.assertEqual(auth.next_action(), "operator_issue_credential")

    def test_one_denied_dimension_leaves_the_other_four_verdicts_identical(self):
        baseline = a.authorize(member_id="m-1", states=_states())
        denied = a.authorize(member_id="m-1", states=_states(credential=a.DENIED))
        baseline_others = [v.as_dict() for v in baseline.verdicts if v.dimension != "credential"]
        denied_others = [v.as_dict() for v in denied.verdicts if v.dimension != "credential"]
        self.assertEqual(baseline_others, denied_others)
        self.assertEqual(denied.verdict("credential").state, a.DENIED)

    def test_sweeping_every_dimension_never_moves_another_verdict(self):
        for dimension in a.DIMENSIONS:
            for state in a._STATES:
                auth = a.authorize(member_id="m-1", states=_states(**{dimension: state}))
                for verdict in auth.verdicts:
                    if verdict.dimension == dimension:
                        self.assertEqual(verdict.state, state)
                    else:
                        self.assertEqual(
                            verdict.state,
                            a.UNVERIFIED,
                            f"{dimension}={state} moved {verdict.dimension}",
                        )

    def test_overall_authorized_requires_every_dimension_on_its_own_evidence(self):
        for dimension in a.DIMENSIONS:
            for state in (a.DENIED, a.UNVERIFIED):
                auth = a.authorize(
                    member_id="m-1",
                    states={d: a.AUTHORIZED for d in a.DIMENSIONS} | {dimension: state},
                )
                self.assertFalse(auth.authorized, f"{dimension}={state} still authorized")
                self.assertEqual(auth.blocked_dimensions, [dimension])
                self.assertEqual(auth.next_action(), "operator_grant_required")

    def test_a_denial_does_not_cascade_into_a_sibling_denial(self):
        auth = a.authorize(
            member_id="m-1",
            states={d: a.AUTHORIZED for d in a.DIMENSIONS} | {"grant": a.DENIED},
        )
        self.assertEqual(auth.blocked_dimensions, ["grant"])
        for dimension in a.DIMENSIONS:
            if dimension != "grant":
                self.assertEqual(auth.verdict(dimension).state, a.AUTHORIZED)

    def test_an_authorized_dimension_does_not_authorize_a_sibling(self):
        auth = a.authorize(member_id="m-1", states=_states(identity=a.AUTHORIZED))
        self.assertEqual(auth.blocked_dimensions, ["grant", "credential", "sms", "resource"])
        self.assertFalse(auth.authorized)

    def test_an_expired_credential_is_not_an_expired_resource(self):
        auth = a.authorize(
            member_id="m-1",
            states=_states(credential=a.DENIED, resource=a.AUTHORIZED),
            reasons={"credential": "login credential expired"},
        )
        self.assertFalse(auth.verdict("credential").authorized)
        self.assertTrue(auth.verdict("resource").authorized)
        self.assertNotEqual(
            auth.verdict("credential").reason, auth.verdict("resource").reason
        )

    def test_sms_permission_says_nothing_about_identity(self):
        no_sms = a.authorize(member_id="m-1", states=_states(identity=a.AUTHORIZED))
        with_sms = a.authorize(
            member_id="m-1", states=_states(identity=a.AUTHORIZED, sms=a.AUTHORIZED)
        )
        self.assertFalse(no_sms.verdict("sms").authorized)
        self.assertTrue(with_sms.verdict("sms").authorized)
        self.assertEqual(
            no_sms.verdict("identity").as_dict(), with_sms.verdict("identity").as_dict()
        )


class TestInputsAreRefusedNotDefaulted(unittest.TestCase):
    def test_a_missing_dimension_is_refused(self):
        states = _states()
        del states["sms"]
        with self.assertRaises(a.AccessAdapterError) as caught:
            a.authorize(member_id="m-1", states=states)
        self.assertIn("missing", str(caught.exception))

    def test_an_unknown_dimension_is_refused(self):
        with self.assertRaises(a.AccessAdapterError) as caught:
            a.authorize(member_id="m-1", states=_states(entitlement=a.AUTHORIZED))
        self.assertIn("unknown", str(caught.exception))

    def test_an_unknown_state_is_refused(self):
        with self.assertRaises(a.AccessAdapterError):
            a.authorize(member_id="m-1", states=_states(grant="maybe"))

    def test_a_non_string_state_is_refused(self):
        with self.assertRaises(a.AccessAdapterError):
            a.authorize(member_id="m-1", states=_states(grant=True))

    def test_a_blank_or_non_string_member_id_is_refused(self):
        for bad in ("", "   ", None, 7):
            with self.assertRaises(a.AccessAdapterError):
                a.authorize(member_id=bad, states=_states())

    def test_non_mapping_states_is_refused(self):
        with self.assertRaises(a.AccessAdapterError):
            a.authorize(member_id="m-1", states=[("identity", a.AUTHORIZED)])

    def test_a_reason_is_never_borrowed_across_dimensions(self):
        auth = a.authorize(
            member_id="m-1", states=_states(), reasons={"identity": "no mobile identity"}
        )
        self.assertEqual(auth.verdict("identity").reason, "no mobile identity")
        for dimension in a.DIMENSIONS:
            if dimension != "identity":
                self.assertEqual(auth.verdict(dimension).reason, "")

    def test_state_spelling_is_normalised_but_meaning_is_not_invented(self):
        auth = a.authorize(member_id="  m-1  ", states=_states(grant=" AUTHORIZED "))
        self.assertEqual(auth.member_id, "m-1")
        self.assertEqual(auth.verdict("grant").state, a.AUTHORIZED)
        self.assertFalse(auth.authorized)


class TestOneMemberAcrossBothChannels(unittest.TestCase):
    def test_the_sms_and_email_handles_bind_to_one_member(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        ledger.bind(member_id="m-1", channel="email", handle="email-1")
        self.assertEqual(ledger.member_for(channel="sms", handle="sms-1"), "m-1")
        self.assertEqual(ledger.member_for(channel="email", handle="email-1"), "m-1")

    def test_a_handle_cannot_move_to_a_different_member(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        with self.assertRaises(a.MemberContinuityError):
            ledger.bind(member_id="m-2", channel="sms", handle="sms-1")
        self.assertEqual(ledger.member_for(channel="sms", handle="sms-1"), "m-1")

    def test_rebinding_the_same_member_is_idempotent_and_reported(self):
        ledger = a.AccessLedger()
        self.assertFalse(ledger.bind(member_id="m-1", channel="sms", handle="sms-1")["already_bound"])
        self.assertTrue(ledger.bind(member_id="m-1", channel="sms", handle="sms-1")["already_bound"])

    def test_an_unknown_channel_is_refused(self):
        ledger = a.AccessLedger()
        for bad in ("whatsapp", "", None):
            with self.assertRaises(a.AccessAdapterError):
                ledger.bind(member_id="m-1", channel=bad, handle="h-1")

    def test_an_unbound_handle_resolves_to_no_member(self):
        self.assertIsNone(a.AccessLedger().member_for(channel="sms", handle="sms-1"))

    def test_a_failed_step_cannot_be_attributed_to_an_unbound_handle(self):
        ledger = a.AccessLedger()
        with self.assertRaises(a.AccessAdapterError):
            ledger.record_failed_step(
                member_id="m-1", dimension="identity", reason="r",
                channel="sms", handle="sms-1",
            )

    def test_a_failed_step_cannot_be_attributed_to_another_members_handle(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        with self.assertRaises(a.MemberContinuityError):
            ledger.record_failed_step(
                member_id="m-2", dimension="identity", reason="r",
                channel="sms", handle="sms-1",
            )

    def test_a_failed_step_names_a_real_dimension(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        with self.assertRaises(a.AccessAdapterError):
            ledger.record_failed_step(
                member_id="m-1", dimension="entitlement", reason="r",
                channel="sms", handle="sms-1",
            )


class TestEmailLaterIsTheSameMember(unittest.TestCase):
    def test_email_later_records_the_same_member(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        record = ledger.defer_to_email(member_id="m-1", handle="email-1")
        self.assertTrue(record["deferred"])
        self.assertEqual(record["member_id"], "m-1")
        self.assertEqual(ledger.member_for(channel="email", handle="email-1"), "m-1")

    def test_email_later_refuses_an_address_owned_by_a_different_member(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        ledger.bind(member_id="m-2", channel="email", handle="email-2")
        with self.assertRaises(a.MemberContinuityError):
            ledger.defer_to_email(member_id="m-1", handle="email-2")
        self.assertEqual(ledger.member_for(channel="email", handle="email-2"), "m-2")

    def test_the_deferral_names_the_pending_dimensions(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        for dimension in ("credential", "grant"):
            ledger.record_failed_step(
                member_id="m-1", dimension=dimension, reason="r",
                channel="sms", handle="sms-1",
            )
        record = ledger.defer_to_email(member_id="m-1", handle="email-1")
        self.assertEqual(record["pending_dimensions"], ["credential", "grant"])

    def test_no_deferral_reads_as_none_not_as_an_empty_member(self):
        self.assertIsNone(a.AccessLedger().deferral(member_id="m-1"))


class TestResumeLandsOnTheSameMember(unittest.TestCase):
    def _ledger_with_failure(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        ledger.record_failed_step(
            member_id="m-1", dimension="credential", reason="credential not issued",
            channel="sms", handle="sms-1",
        )
        return ledger

    def test_resume_returns_the_exact_failed_dimension(self):
        result = self._ledger_with_failure().resume(
            channel="sms", handle="sms-1", via="sms_return"
        )
        self.assertEqual(result["status"], "resumed")
        self.assertEqual(result["resumed_dimensions"], ["credential"])
        self.assertEqual(result["member_id"], "m-1")
        self.assertTrue(result["same_member"])

    def test_a_return_over_the_wrong_channel_is_refused(self):
        ledger = self._ledger_with_failure()
        with self.assertRaises(a.MemberContinuityError):
            ledger.resume(channel="sms", handle="sms-1", via="email")
        with self.assertRaises(a.MemberContinuityError):
            ledger.resume(channel="email", handle="sms-1", via="sms_return")

    def test_an_unbound_return_handle_resolves_to_no_member_and_is_refused(self):
        with self.assertRaises(a.AccessAdapterError):
            a.AccessLedger().resume(channel="sms", handle="sms-9", via="sms_return")

    def test_nothing_pending_is_reported_as_nothing_not_as_success(self):
        ledger = a.AccessLedger()
        ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
        result = ledger.resume(channel="sms", handle="sms-1", via="sms_return")
        self.assertEqual(result["status"], "nothing_to_resume")
        self.assertEqual(result["resumed_dimensions"], [])

    def test_an_unknown_return_path_is_refused(self):
        for bad in ("carrier_pigeon", "", None):
            with self.assertRaises(a.AccessAdapterError):
                self._ledger_with_failure().resume(
                    channel="sms", handle="sms-1", via=bad
                )

    def test_access_return_and_email_later_resolve_to_one_member(self):
        """The clause end to end: one member, two channels, two return paths."""
        ledger = self._ledger_with_failure()
        ledger.defer_to_email(member_id="m-1", handle="email-1")

        over_sms = ledger.resume(channel="sms", handle="sms-1", via="sms_return")
        over_email = ledger.resume(channel="email", handle="email-1", via="email")

        self.assertEqual(over_sms["member_id"], "m-1")
        self.assertEqual(over_email["member_id"], "m-1")
        self.assertEqual(over_sms["member_id"], over_email["member_id"])
        self.assertEqual(over_sms["resumed_dimensions"], ["credential"])
        self.assertEqual(over_email["resumed_dimensions"], ["credential"])
        self.assertEqual(ledger.deferral(member_id="m-1")["member_id"], "m-1")

    def test_two_members_never_share_a_resume(self):
        ledger = self._ledger_with_failure()
        ledger.bind(member_id="m-2", channel="sms", handle="sms-2")
        second = ledger.resume(channel="sms", handle="sms-2", via="sms_return")
        self.assertEqual(second["member_id"], "m-2")
        self.assertEqual(second["status"], "nothing_to_resume")


class TestNoProviderAndNoOriginalCoupling(unittest.TestCase):
    def test_the_module_imports_no_network_library(self):
        source = (MODULE / "access_adapter.py").read_text(encoding="utf-8")
        for forbidden in (
            "import urllib", "import requests", "import socket",
            "import http", "from http", "import ssl", "import ftplib",
        ):
            self.assertNotIn(forbidden, source)

    def test_no_result_ever_claims_automation_or_a_grant(self):
        for states in (
            {d: a.AUTHORIZED for d in a.DIMENSIONS},
            _states(),
            _states(identity=a.DENIED),
        ):
            payload = a.authorize(member_id="m-1", states=states).as_dict()
            self.assertFalse(payload["automated"])
            self.assertFalse(payload["system_claimed_grant"])
            self.assertIn(
                payload["next_action"],
                ("operator_grant_required", "operator_issue_credential"),
            )
            self.assertEqual(len(payload["verdicts"]), len(a.DIMENSIONS))

    def test_a_blocked_lane_offers_no_original_lane_field(self):
        payload = a.authorize(member_id="m-1", states=_states()).as_dict()
        for key in payload:
            self.assertNotIn("original", key.lower())
        source = (MODULE / "access_adapter.py").read_text(encoding="utf-8")
        for coupling in ("import direct_fulfillment", "from direct_fulfillment"):
            self.assertNotIn(coupling, source)
        self.assertEqual(payload["reason_code"], a.BLOCK_REASON)


if __name__ == "__main__":
    unittest.main(verbosity=2)
