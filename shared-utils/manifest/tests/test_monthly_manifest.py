#!/usr/bin/env python3
"""Self-check for the joined monthly approval manifest.

Pins every clause of the T-23 acceptance: exact placement / account / channel /
schedule / CTA / keyword / assets / spares approval, public dispatch binding it,
unrelated approved units continuing after one placement is invalidated, and the
approval revision advancing rather than repeating or rolling back.

The dispatch cases run the accepted T-08 guard in place (pb_contracts), so the
binding half of the proof is the shipped guard reading a manifest this module
produced, never a second copy of the comparison.

Run: python3 -I shared-utils/manifest/tests/test_monthly_manifest.py
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
MODULE_DIR = HERE.parents[1]
REPO_ROOT = HERE.parents[3]
CONTRACTS_TOOLS = REPO_ROOT / "38-conversational-ai-system" / "tools"
UPSTREAM_FIXTURES = CONTRACTS_TOOLS / "tests" / "fixtures" / "pb-contracts"

sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(CONTRACTS_TOOLS))

import monthly_manifest as mm  # noqa: E402
import pb_contracts as contracts  # noqa: E402

FIXTURES = MODULE_DIR / "fixtures"
AT = "2026-10-20T18:00:00Z"
NOW = "2026-10-24T10:01:00Z"
ZWSP = chr(0x200B)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def signed():
    """The two-placement fixture: one joined campaign, two approved placements."""
    return read_json(FIXTURES / "manifest-two-placement.json")


def draft():
    """The same campaign before the client signs it."""
    doc = signed()
    doc["status"] = "DRAFT"
    doc["revision"] = "rev-2"
    doc["approved_by"] = None
    doc["approved_at"] = None
    for placement in doc["placements"]:
        placement["approval_status"] = "DRAFT"
        placement["invalidated_at"] = None
        placement["invalidated_reason"] = None
    return doc


def approved():
    """The signed fixture put back through approve(), the module's own output."""
    doc, errs = mm.approve(draft(), "client-owner-1", AT, "rev-3", "rev-2")
    assert errs == [], errs
    return doc


def placement(doc, placement_id):
    return mm._placement(doc, placement_id)


def divergent(field):
    """A value that differs from the approved P-1 term, of the right shape."""
    if field in ("bonus_asset_versions", "allowed_spare_ids"):
        return ["divergent-1"]
    if field == "channel":
        return "IG_PUBLIC"
    if field == "scheduled_at":
        return "2026-11-02T15:00:00Z"
    if field == "content_revision":
        return "content-10"
    if field == "timezone":
        return "America/Chicago"
    if field == "account_id":
        return "acct-9"
    if field == "account_binding_revision":
        return "binding-9"
    return "divergent"


def run(*argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = contracts.main([str(arg) for arg in argv])
    return code, json.loads(buffer.getvalue())


class ManifestCase(unittest.TestCase):
    def assertRefused(self, doc, errs, needle):
        self.assertTrue(errs, "the change was accepted without a reason")
        self.assertTrue(
            any(needle in err for err in errs),
            "%r missing from %s" % (needle, errs),
        )


class RefusalTests(ManifestCase):
    def test_a_refusal_never_half_writes_the_document(self):
        # Every refusal returns a copy equal to its input: a caller that persists
        # the returned document after an error cannot damage the approved state.
        cases = [
            (draft(), lambda doc: mm.approve(doc, ZWSP, AT, "rev-3", "rev-2")),
            (signed(), lambda doc: mm.amend(doc, "P-1", {"keyword": "   "}, "", AT, "rev-3")),
            (signed(), lambda doc: mm.amend(doc, "P-1", {"keyword": "VAULT"}, "r", AT, "rev-2")),
            (signed(), lambda doc: mm.next_cycle(doc, "cycle-2026-11", "2026-12-01", "2026-12-30", "rev-4", "rev-3")),
            (invalidated(), lambda doc: mm.reapprove(doc, "P-1", ZWSP, "not-a-time", "rev-3")),
        ]
        for index, (before, call) in enumerate(cases):
            with self.subTest(index):
                returned, errs = call(copy.deepcopy(before))
                self.assertTrue(errs, "the case was accepted, so it cannot prove refusal")
                self.assertEqual(before, returned)


class JoinedApprovalTests(ManifestCase):
    """R1: one coordinated approval joins every placement of the 30-day campaign."""

    def test_one_approval_joins_every_placement_at_one_revision(self):
        before = draft()
        doc, errs = mm.approve(before, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertEqual([], errs)
        self.assertEqual([], mm.validate(doc))
        self.assertEqual("APPROVED", doc["status"])
        self.assertEqual("rev-3", doc["revision"])
        self.assertEqual("client-owner-1", doc["approved_by"])
        self.assertEqual(AT, doc["approved_at"])
        for approved_placement in doc["placements"]:
            self.assertEqual("APPROVED", approved_placement["approval_status"])
            self.assertIsNone(approved_placement["invalidated_at"])
        self.assertEqual(["P-1", "P-2"], [p["placement_id"] for p in doc["placements"]])

    def test_control_the_signed_fixture_is_a_valid_contract_document(self):
        self.assertEqual([], mm.validate(signed()))

    def test_a_manifest_with_no_placement_is_not_a_joined_approval(self):
        doc = draft()
        doc["placements"] = []
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertRefused(doc, errs, "binds at least one placement")

    def test_a_duplicate_placement_id_is_refused(self):
        doc = draft()
        doc["placements"].append(copy.deepcopy(doc["placements"][0]))
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertRefused(doc, errs, "duplicate placement_id")

    def test_a_campaign_window_that_is_not_thirty_days_is_refused(self):
        doc = draft()
        doc["campaign_window"]["ends_on"] = "2026-11-29"
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertRefused(doc, errs, "must span 30 days")

    def test_every_missing_term_blocks_the_join_and_names_itself(self):
        for field in mm.APPROVAL_TERMS:
            with self.subTest(field):
                doc = draft()
                target = placement(doc, "P-2")
                target[field] = ["  "] if isinstance(target[field], list) else "   "
                _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
                self.assertRefused(doc, errs, field)

    def test_an_invisible_only_term_is_absent(self):
        doc = draft()
        placement(doc, "P-1")["cta_text"] = ZWSP
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertRefused(doc, errs, "cta_text")

    def test_a_blank_entry_inside_an_approved_list_is_absent(self):
        for field in ("bonus_asset_versions", "allowed_spare_ids"):
            with self.subTest(field):
                doc = draft()
                placement(doc, "P-1")[field] = ["  "]
                _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
                self.assertRefused(doc, errs, field)

    def test_a_placement_scheduled_outside_the_joined_window_is_refused(self):
        doc = draft()
        placement(doc, "P-2")["scheduled_at"] = "2026-12-05T15:00:00Z"
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertRefused(doc, errs, "outside the joined campaign window")

    def test_an_invalidated_placement_is_not_silently_re_approved(self):
        doc = draft()
        target = placement(doc, "P-1")
        target["approval_status"] = "INVALIDATED"
        target["invalidated_at"] = AT
        target["invalidated_reason"] = "client changed the CTA"
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
        self.assertRefused(doc, errs, "re-approve that placement on its own")

    def test_only_a_draft_is_joined(self):
        _, errs = mm.approve(signed(), "client-owner-1", AT, "rev-4", "rev-3")
        self.assertTrue(any("only a DRAFT" in err for err in errs), errs)

    def test_an_approval_names_its_approver_and_a_real_time(self):
        doc = draft()
        _, errs = mm.approve(doc, ZWSP, "not-a-timestamp", "rev-3", "rev-2")
        self.assertRefused(doc, errs, "approved_by")
        self.assertTrue(any("approved_at" in err for err in errs), errs)


class VersionEnforcementTests(ManifestCase):
    """R2: a new approval advances its revision; nothing writes on a stale read."""

    def test_the_same_revision_cannot_approve_twice(self):
        _, errs = mm.approve(draft(), "client-owner-1", AT, "rev-2", "rev-2")
        self.assertTrue(any("already the current revision" in err for err in errs), errs)

    def test_a_backward_revision_is_refused(self):
        doc = signed()
        _, errs = mm.amend(doc, "P-1", {"cta_text": "new"}, "reason", AT, "rev-2")
        self.assertTrue(any("is at 'rev-3'" in err for err in errs), errs)
        self.assertEqual(
            ["$.revision: 'rev-2' rolls back 'rev-3'"], mm.check_revision("rev-3", "rev-2")
        )

    def test_an_opaque_revision_may_advance_but_not_repeat_a_counter(self):
        self.assertEqual([], mm.check_revision("rev-3", "2026-11-20-approval"))
        self.assertEqual([], mm.check_revision("rev-3", "rev-4"))
        self.assertTrue(mm.check_revision("rev-3", "rev-3"))
        self.assertTrue(mm.check_revision("rev-3", "v3"))
        self.assertTrue(mm.check_revision("rev-3", "   "))

    def test_every_write_requires_the_revision_it_read(self):
        cases = [
            ("approve", lambda: mm.approve(draft(), "client-owner-1", AT, "rev-3", "rev-1")),
            ("amend", lambda: mm.amend(signed(), "P-1", {"cta_text": "new"}, "r", AT, "rev-1")),
            ("reapprove", lambda: mm.reapprove(invalidated(), "P-1", "client-owner-1", AT, "rev-1")),
            ("next_cycle", lambda: mm.next_cycle(
                signed(), "cycle-2026-12", "2026-12-01", "2026-12-30", "rev-4", "rev-1")),
        ]
        for label, call in cases:
            with self.subTest(label):
                _, errs = call()
                self.assertTrue(any("expected 'rev-1'" in err for err in errs), errs)


class AmendmentTests(ManifestCase):
    """R3: a mutation invalidates that placement only; the campaign revision holds."""

    def test_amending_one_placement_invalidates_only_that_placement(self):
        doc, errs = mm.amend(
            signed(), "P-1", {"cta_text": "Comment VAULT and I will send it."}, "client edit", AT, "rev-3"
        )
        self.assertEqual([], errs)
        self.assertEqual([], mm.validate(doc))
        self.assertEqual("PARTIAL_INVALIDATED", doc["status"])
        self.assertEqual("rev-3", doc["revision"], "the campaign approval revision must not move")
        target = placement(doc, "P-1")
        self.assertEqual("INVALIDATED", target["approval_status"])
        self.assertEqual(AT, target["invalidated_at"])
        self.assertEqual("client edit", target["invalidated_reason"])
        self.assertEqual("Comment VAULT and I will send it.", target["cta_text"])
        other = placement(doc, "P-2")
        self.assertEqual("APPROVED", other["approval_status"])
        self.assertIsNone(other["invalidated_at"])
        self.assertEqual(placement(signed(), "P-2"), other)

    def test_each_approved_term_can_be_amended_without_touching_the_other_unit(self):
        for field in mm.APPROVAL_TERMS:
            with self.subTest(field):
                doc, errs = mm.amend(signed(), "P-2", {field: divergent(field)}, "client edit", AT, "rev-3")
                self.assertEqual([], errs)
                self.assertEqual("APPROVED", placement(doc, "P-1")["approval_status"])
                self.assertEqual(divergent(field), placement(doc, "P-2")[field])

    def test_a_term_outside_the_approval_is_not_amendable(self):
        _, errs = mm.amend(signed(), "P-1", {"asset_version_id": "asset-9"}, "r", AT, "rev-3")
        self.assertTrue(any("is not an approved term" in err for err in errs), errs)

    def test_an_amendment_that_changes_nothing_keeps_the_placement_approved(self):
        _, errs = mm.amend(signed(), "P-1", {"keyword": "GUIDE"}, "r", AT, "rev-3")
        self.assertTrue(any("changes nothing" in err for err in errs), errs)

    def test_an_amendment_names_its_reason_and_a_real_time(self):
        _, errs = mm.amend(signed(), "P-1", {"keyword": "VAULT"}, ZWSP, "yesterday", "rev-3")
        self.assertTrue(any("invalidated_reason" in err for err in errs), errs)
        self.assertTrue(any("invalidated_at" in err for err in errs), errs)

    def test_an_unknown_placement_is_refused(self):
        _, errs = mm.amend(signed(), "P-9", {"keyword": "VAULT"}, "r", AT, "rev-3")
        self.assertTrue(any("'P-9' is not in the manifest" in err for err in errs), errs)

    def test_a_draft_has_no_approved_terms_to_amend(self):
        _, errs = mm.amend(draft(), "P-1", {"keyword": "VAULT"}, "r", AT, "rev-2")
        self.assertTrue(any("only an approved manifest" in err for err in errs), errs)

    def test_an_amended_schedule_must_stay_inside_the_joined_window(self):
        _, errs = mm.amend(signed(), "P-1", {"scheduled_at": "2026-12-05T15:00:00Z"}, "r", AT, "rev-3")
        self.assertTrue(any("outside the joined campaign window" in err for err in errs), errs)

    def test_a_second_amendment_does_not_re_invalidate_the_first(self):
        first, errs = mm.amend(signed(), "P-1", {"keyword": "VAULT"}, "edit one", AT, "rev-3")
        self.assertEqual([], errs)
        second, errs = mm.amend(first, "P-2", {"keyword": "ACCESS"}, "edit two", AT, "rev-3")
        self.assertEqual([], errs)
        self.assertEqual("INVALIDATED", placement(second, "P-1")["approval_status"])
        self.assertEqual("VAULT", placement(second, "P-1")["keyword"])
        self.assertEqual("INVALIDATED", placement(second, "P-2")["approval_status"])
        self.assertEqual("rev-3", second["revision"])


def invalidated():
    doc, errs = mm.amend(signed(), "P-1", {"cta_text": "Comment VAULT."}, "client edit", AT, "rev-3")
    assert errs == [], errs
    return doc


class ReapprovalTests(ManifestCase):
    """R4: a re-approved placement returns to the campaign without a new campaign."""

    def test_reapproval_restores_one_placement_and_keeps_the_revision(self):
        doc, errs = mm.reapprove(invalidated(), "P-1", "client-owner-1", AT, "rev-3")
        self.assertEqual([], errs)
        self.assertEqual([], mm.validate(doc))
        self.assertEqual("APPROVED", doc["status"])
        self.assertEqual("rev-3", doc["revision"])
        self.assertEqual("APPROVED", placement(doc, "P-1")["approval_status"])
        self.assertIsNone(placement(doc, "P-1")["invalidated_at"])
        self.assertEqual("Comment VAULT.", placement(doc, "P-1")["cta_text"])
        self.assertEqual(placement(signed(), "P-2"), placement(doc, "P-2"))

    def test_reapproval_requires_a_partially_invalidated_manifest(self):
        _, errs = mm.reapprove(signed(), "P-1", "client-owner-1", AT, "rev-3")
        self.assertTrue(any("only a partially invalidated manifest" in err for err in errs), errs)

    def test_an_approved_placement_is_not_reapproved(self):
        doc = invalidated()
        doc["placements"][1]["approval_status"] = "APPROVED"
        _, errs = mm.reapprove(doc, "P-2", "client-owner-1", AT, "rev-3")
        self.assertTrue(any("not an invalidated placement" in err for err in errs), errs)

    def test_a_blank_term_cannot_be_reapproved(self):
        doc = invalidated()
        placement(doc, "P-1")["keyword"] = "   "
        _, errs = mm.reapprove(doc, "P-1", "client-owner-1", AT, "rev-3")
        self.assertTrue(any("keyword" in err for err in errs), errs)

    def test_a_slot_outside_the_window_cannot_be_reapproved(self):
        doc = invalidated()
        placement(doc, "P-1")["scheduled_at"] = "2027-01-01T15:00:00Z"
        _, errs = mm.reapprove(doc, "P-1", "client-owner-1", AT, "rev-3")
        self.assertTrue(any("outside the joined campaign window" in err for err in errs), errs)

    def test_reapproval_names_its_approver(self):
        _, errs = mm.reapprove(invalidated(), "P-1", "  ", AT, "rev-3")
        self.assertTrue(any("approved_by" in err for err in errs), errs)


class NextCycleTests(ManifestCase):
    """R2/R4: the previous cycle's approval is over; a new one starts unapproved."""

    def test_the_next_cycle_is_a_fresh_draft_at_a_new_revision(self):
        doc, errs = mm.next_cycle(signed(), "cycle-2026-12", "2026-12-01", "2026-12-30", "rev-4", "rev-3")
        self.assertEqual([], errs)
        self.assertEqual([], mm.validate(doc))
        self.assertEqual("DRAFT", doc["status"])
        self.assertEqual("cycle-2026-12", doc["campaign_cycle_id"])
        self.assertEqual("rev-4", doc["revision"])
        self.assertEqual({"starts_on": "2026-12-01", "ends_on": "2026-12-30"}, doc["campaign_window"])
        self.assertIsNone(doc["approved_by"])
        self.assertIsNone(doc["approved_at"])
        for carried in doc["placements"]:
            self.assertEqual("DRAFT", carried["approval_status"])
            self.assertIsNone(carried["invalidated_at"])

    def test_the_same_cycle_id_is_refused(self):
        _, errs = mm.next_cycle(signed(), "cycle-2026-11", "2026-12-01", "2026-12-30", "rev-4", "rev-3")
        self.assertTrue(any("is the current cycle" in err for err in errs), errs)

    def test_a_cycle_must_span_thirty_days_and_not_overlap_the_last_day(self):
        _, errs = mm.next_cycle(signed(), "cycle-2026-12", "2026-12-01", "2026-12-29", "rev-4", "rev-3")
        self.assertTrue(any("spans 30 days" in err for err in errs), errs)
        _, errs = mm.next_cycle(signed(), "cycle-2026-12", "2026-11-29", "2026-12-28", "rev-4", "rev-3")
        self.assertTrue(any("previous cycle's last day" in err for err in errs), errs)

    def test_the_new_cycle_cannot_reuse_the_old_revision(self):
        _, errs = mm.next_cycle(signed(), "cycle-2026-12", "2026-12-01", "2026-12-30", "rev-3", "rev-3")
        self.assertTrue(any("already the current revision" in err for err in errs), errs)

    def test_the_carried_schedule_must_be_reset_before_the_new_cycle_is_approved(self):
        # The November slot is outside the December window, so the approval the
        # new cycle asks for is refused until the schedule is re-set. This is the
        # schedule half of "exact schedule approval", not a new rule.
        doc, errs = mm.next_cycle(signed(), "cycle-2026-12", "2026-12-01", "2026-12-30", "rev-4", "rev-3")
        self.assertEqual([], errs)
        _, errs = mm.approve(doc, "client-owner-1", AT, "rev-5", "rev-4")
        self.assertTrue(any("outside the joined campaign window" in err for err in errs), errs)


class DispatchBindingTests(unittest.TestCase):
    """R5: public dispatch binds the approved manifest; unrelated units continue.

    The dispatch itself is the accepted T-08 guard (pb_contracts dispatch) run in
    place. These cases prove a manifest this module produced binds it, and that
    invalidating one placement leaves the other unit dispatching.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pb-manifest-"))
        self.manifest = self.tmp / "manifest.json"
        self.gate = str(UPSTREAM_FIXTURES / "gates" / "public-allow.json")
        self.write_manifest(signed())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_manifest(self, doc):
        self.current = doc
        self.manifest.write_text(json.dumps(doc), encoding="utf-8")

    def action(self, placement_id):
        """A queued public placement action for one approved placement."""
        doc = read_json(UPSTREAM_FIXTURES / "outbound" / "public-placement.json")
        approved_placement = placement(self.current, placement_id)
        doc["action_id"] = "act-%s" % placement_id
        doc["logical_intent_key"] = "%s/%s/SCHEDULED_POST" % (self.current["campaign_cycle_id"], placement_id)
        doc["placement_id"] = placement_id
        for field in mm.APPROVAL_TERMS:
            doc[field] = copy.deepcopy(approved_placement[field])
        return doc

    def dispatch(self, action, name=None, manifest=None):
        action_path = self.tmp / ("%s.json" % (name or action["action_id"]))
        action_path.write_text(json.dumps(action), encoding="utf-8")
        return run(
            "dispatch",
            "--action", action_path,
            "--gate", self.gate,
            "--manifest", manifest or self.manifest,
            "--ledger", self.tmp / ("ledger-%s.json" % (name or action["action_id"])),
            "--now", NOW,
        )

    def test_both_approved_placements_dispatch(self):
        for placement_id in ("P-1", "P-2"):
            with self.subTest(placement_id):
                code, payload = self.dispatch(self.action(placement_id))
                self.assertEqual(0, code, payload)
                self.assertEqual("DISPATCHED", payload["decision"], payload)

    def test_public_dispatch_binds_every_approved_placement_term(self):
        for field in contracts.PLACEMENT_BOUND_FIELDS:
            with self.subTest(field):
                action = self.action("P-1")
                action[field] = divergent(field)
                code, payload = self.dispatch(action, name="mut-%s" % field)
                self.assertEqual(1, code, payload)
                self.assertEqual("STALE_APPROVAL", payload["decision"], payload)
                self.assertIn(field, payload["reason"])
                self.assertTrue(
                    any(err.startswith("$.%s:" % field) for err in payload["errors"]),
                    payload["errors"],
                )

    def test_public_dispatch_binds_the_approved_account(self):
        for field, needle in (
            ("account_id", "account_id"),
            ("account_binding_revision", "account_binding_revision"),
        ):
            with self.subTest(field):
                doc = signed()
                placement(doc, "P-1")[field] = divergent(field)
                path = self.tmp / ("manifest-%s.json" % field)
                path.write_text(json.dumps(doc), encoding="utf-8")
                code, payload = self.dispatch(self.action("P-1"), "acct-%s" % field, str(path))
                self.assertEqual(1, code, payload)
                self.assertEqual("STALE_APPROVAL", payload["decision"], payload)
                self.assertIn(needle, payload["reason"])
                self.assertTrue(
                    any(err.startswith("$.%s:" % needle) for err in payload["errors"]),
                    payload["errors"],
                )

    def test_an_amended_placement_is_refused_while_the_other_unit_continues(self):
        doc, errs = mm.amend(signed(), "P-1", {"cta_text": "Comment VAULT and I will send it."}, "edit", AT, "rev-3")
        self.assertEqual([], errs)
        self.write_manifest(doc)
        self.assertEqual("rev-3", doc["revision"], "the campaign revision must not move")

        code, refused = self.dispatch(self.action("P-1"))
        self.assertEqual(1, code, refused)
        self.assertEqual("STALE_APPROVAL", refused["decision"], refused)
        self.assertTrue(
            any("placement approval is 'INVALIDATED'" in err for err in refused["errors"]),
            refused["errors"],
        )

        code, allowed = self.dispatch(self.action("P-2"), name="P-2-unrelated")
        self.assertEqual(0, code, allowed)
        self.assertEqual("DISPATCHED", allowed["decision"], allowed)

    def test_a_reapproved_placement_dispatches_again_beside_the_other_unit(self):
        amended, errs = mm.amend(signed(), "P-1", {"keyword": "VAULT"}, "edit", AT, "rev-3")
        self.assertEqual([], errs)
        doc, errs = mm.reapprove(amended, "P-1", "client-owner-1", AT, "rev-3")
        self.assertEqual([], errs)
        self.write_manifest(doc)

        for placement_id, name in (("P-1", "P-1-reapproved"), ("P-2", "P-2-beside")):
            with self.subTest(placement_id):
                code, payload = self.dispatch(self.action(placement_id), name=name)
                self.assertEqual(0, code, payload)
                self.assertEqual("DISPATCHED", payload["decision"], payload)

    def test_a_new_cycle_refuses_the_previous_cycles_action(self):
        doc, errs = mm.next_cycle(signed(), "cycle-2026-12", "2026-12-01", "2026-12-30", "rev-4", "rev-3")
        self.assertEqual([], errs)
        self.write_manifest(doc)
        code, payload = self.dispatch(self.action("P-1"))
        self.assertEqual(1, code, payload)
        self.assertEqual("STALE_APPROVAL", payload["decision"], payload)
        self.assertIn("campaign_cycle_id", payload["reason"])
        self.assertIn("approval_revision", payload["reason"])


class RevisionOrderingTests(ManifestCase):
    """Version enforcement: no rollback, and no revision scheme is unapprovable.

    The 1.0.0 module read a counter out of the trailing digits only, so any
    revision without a trailing digit was opaque and a differing value advanced.
    That admitted the rollback ``rev-3`` -> ``rev-2-final`` and refused the
    forward ``2026-11-01`` -> ``2026-12-01``. Both directions are pinned here.
    """

    def test_a_rollback_is_refused_even_when_a_word_trails_the_counter(self):
        for revision in ("rev-2-final", "rev-2-approval", "rev-2"):
            with self.subTest(revision):
                self.assertEqual(
                    ["$.revision: %r rolls back 'rev-3'" % (revision,)],
                    mm.check_revision("rev-3", revision),
                )
        # The inverse: the same tagged scheme moving forward still approves.
        self.assertEqual([], mm.check_revision("rev-2-final", "rev-3"))
        self.assertEqual([], mm.check_revision("rev-3", "rev-4-final"))

    def test_a_date_or_semver_revision_can_advance(self):
        self.assertEqual([], mm.check_revision("2026-11-01", "2026-12-01"))
        self.assertEqual([], mm.check_revision("2026-12-01", "2027-01-01"))
        self.assertEqual([], mm.check_revision("v1.0", "v2.0"))
        self.assertEqual([], mm.check_revision("v1.9.0", "v1.10.0"))
        # The inverse: the same schemes walking backwards are still refused.
        self.assertEqual(
            ["$.revision: '2026-11-01' rolls back '2026-12-01'"],
            mm.check_revision("2026-12-01", "2026-11-01"),
        )
        self.assertEqual(
            ["$.revision: 'v1.0' rolls back 'v2.0'"],
            mm.check_revision("v2.0", "v1.0"),
        )

    def test_the_whole_number_run_is_ordered_numerically(self):
        # v1.10 is after v1.9: the numbers decide, not their spelling.
        self.assertEqual([], mm.check_revision("v1.9.0", "v1.10.0"))
        self.assertTrue(mm.check_revision("v1.10.0", "v1.9.0"))

    def test_a_revision_that_cannot_be_ordered_is_refused_not_guessed(self):
        # The module promises a revision never rolls back, so an order it cannot
        # prove is not an advance. Neither of these is a blanket refusal: both
        # schemes approve freely against their own kind (cases above).
        for previous, revision in (("rev-3", "final"), ("final", "rev-3")):
            with self.subTest(revision):
                errs = mm.check_revision(previous, revision)
                self.assertTrue(errs, "an unordered revision pair was accepted")
                self.assertTrue(any("cannot be ordered" in err for err in errs), errs)

    def test_the_revision_decision_table_is_pinned(self):
        advancing = [
            ("rev-3", "rev-4"),
            ("rev-3", "2026-11-20-approval"),
            ("rev-2-final", "rev-3"),
            ("2026-11-01", "2026-12-01"),
            ("v1.0", "v2.0"),
            ("alpha", "beta"),
        ]
        refusing = [
            ("rev-3", "rev-3"),
            ("rev-3", "rev-2"),
            ("rev-3", "rev-2-final"),
            ("rev-3", "rev-2-approval"),
            ("rev-3", "v3"),
            ("2026-12-01", "2026-11-01"),
            ("v2.0", "v1.0"),
            ("alpha", "alpha"),
            ("rev-3", "final"),
            ("rev-3", "   "),
        ]
        for previous, revision in advancing:
            with self.subTest(decision="advance", previous=previous, revision=revision):
                self.assertEqual([], mm.check_revision(previous, revision))
        for previous, revision in refusing:
            with self.subTest(decision="refuse", previous=previous, revision=revision):
                self.assertTrue(mm.check_revision(previous, revision))


class MalformedDocumentTests(ManifestCase):
    """The return contract holds at the JSON trust boundary: a wrong-shaped
    manifest or field is refused with the field named, never raised at a caller
    that is loading a file. Each refusal is paired with the same call on a valid
    document succeeding, so a blanket refusal cannot pass here."""

    def assertRefusedShape(self, returned, errs, before, needle):
        self.assertTrue(errs, "the malformed shape was accepted without a reason")
        self.assertTrue(any(needle in err for err in errs), "%r missing from %s" % (needle, errs))
        self.assertEqual(before, returned)

    def test_a_malformed_placements_shape_is_refused_not_raised(self):
        for value in ("P-1", {"P-1": 1}, ["P-1"], [None], 5):
            with self.subTest(value):
                doc = draft()
                doc["placements"] = value
                before = copy.deepcopy(doc)
                returned, errs = mm.approve(doc, "client-owner-1", AT, "rev-3", "rev-2")
                self.assertRefusedShape(returned, errs, before, "$.placements")
        # The inverse: the same call on a real placement list still approves.
        doc, errs = mm.approve(draft(), "client-owner-1", AT, "rev-3", "rev-2")
        self.assertEqual([], errs)
        self.assertEqual([], mm.validate(doc))

    def test_a_malformed_amendment_is_refused_not_raised(self):
        for changes, needle in (
            (None, "an amendment"),
            (["keyword"], "an amendment"),
            ("keyword", "an amendment"),
            (5, "an amendment"),
            # a well-shaped map with a null value is the term check's to name
            ({"keyword": None}, "an approved term must be present"),
        ):
            with self.subTest(changes):
                doc = signed()
                before = copy.deepcopy(doc)
                returned, errs = mm.amend(doc, "P-1", changes, "client edit", AT, "rev-3")
                self.assertRefusedShape(returned, errs, before, needle)
        # The inverse: a real amendment still invalidates exactly one placement.
        doc, errs = mm.amend(signed(), "P-1", {"keyword": "VAULT"}, "client edit", AT, "rev-3")
        self.assertEqual([], errs)
        self.assertEqual("INVALIDATED", placement(doc, "P-1")["approval_status"])
        self.assertEqual("APPROVED", placement(doc, "P-2")["approval_status"])

    def test_a_malformed_window_names_the_field_not_the_interpreter(self):
        doc = signed()
        before = copy.deepcopy(doc)
        returned, errs = mm.next_cycle(doc, "cycle-2026-12", "2026-12-01", None, "rev-4", "rev-3")
        self.assertRefusedShape(returned, errs, before, "campaign_window")
        self.assertFalse(
            any("unsupported operand" in err for err in errs),
            "the raw interpreter message leaked instead of naming the field: %s" % (errs,),
        )
        # The inverse: the same call with real dates still opens the cycle.
        doc, errs = mm.next_cycle(
            signed(), "cycle-2026-12", "2026-12-01", "2026-12-30", "rev-4", "rev-3"
        )
        self.assertEqual([], errs)
        self.assertEqual("DRAFT", doc["status"])

    def test_a_document_that_is_not_an_object_is_refused_not_raised(self):
        for doc in (["P-1"], "manifest", 5, None):
            with self.subTest(doc):
                before = copy.deepcopy(doc)
                for call in (
                    lambda d: mm.approve(d, "client-owner-1", AT, "rev-3", "rev-2"),
                    lambda d: mm.amend(d, "P-1", {"keyword": "VAULT"}, "r", AT, "rev-3"),
                    lambda d: mm.reapprove(d, "P-1", "client-owner-1", AT, "rev-3"),
                    lambda d: mm.next_cycle(d, "c-2", "2026-12-01", "2026-12-30", "rev-4", "rev-3"),
                ):
                    returned, errs = call(copy.deepcopy(doc))
                    self.assertTrue(errs, "a non-object document was accepted")
                    self.assertEqual(before, returned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
