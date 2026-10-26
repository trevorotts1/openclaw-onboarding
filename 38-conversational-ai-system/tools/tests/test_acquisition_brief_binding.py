#!/usr/bin/env python3
"""Fifth T-06 acceptance clause: approval, capacity, claims and owner binding.

Before this clause the brief could be complete and still have nobody
accountable for it. The tests below prove the inverse as hard as the positive:
an unattributed brief, a doubly-attributed brief, an owner from another
tenant, and any binding signed by somebody other than the accountable owner
are all refused.

The synthetic client fixture in fixtures/synthetic_client.json drives the
end-to-end proof: known facts are reused, only missing facts are asked, the
four bindings are recorded, and the brief becomes plannable.

Run:
  python3 -m unittest discover -s tools/tests -p 'test_*.py'
"""

import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import acquisition_brief as ab  # noqa: E402

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_client.json"

FIXED_NOW = datetime.datetime(
    2026, 10, 24, 12, 0, 0, 0, tzinfo=datetime.timezone.utc
)

REQUIRED_FOR_ASSETS = sorted(ab.ASSET_REQUIRED_FOR_CAMPAIGN)


def fixed_clock():
    return FIXED_NOW


def load_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def new_brief(directory, *, tenant_id=None, name="brief.json"):
    return ab.AcquisitionBrief(
        os.path.join(directory, name), clock=fixed_clock, tenant_id=tenant_id
    )


def bind_everything(brief, owner_id="owner-1"):
    brief.bind_owner(owner_id, "Accountable Owner", email="owner@example.test")
    brief.bind_approval(owner_id, scope="30-day campaign")
    brief.bind_capacity(
        owner_id, monthly_new_customers=10, fulfilment_lead_days=14
    )
    brief.bind_claims(
        owner_id,
        [{"text": "Locally made", "substantiation": "studio photographs"}],
    )


class SyntheticClientFixtureTests(unittest.TestCase):
    """The acceptance text requires a synthetic client fixture."""

    def test_fixture_is_explicitly_synthetic(self):
        fixture = load_fixture()
        self.assertTrue(fixture["synthetic"])
        self.assertIn("example.test", fixture["owner"]["email"])
        self.assertIn("example.test", fixture["impostor_owner"]["email"])
        self.assertIn("fictional", fixture["note"].lower())

    def test_known_facts_are_reused_and_only_missing_facts_are_asked(self):
        fixture = load_fixture()
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory, tenant_id=fixture["tenant_id"])
            for fact_id, record in fixture["discovered_facts"].items():
                brief.record_fact(
                    fact_id,
                    record["value"],
                    provenance=record["provenance"],
                    source=record["source"],
                )

            asked = [question.fact_id for question in brief.next_questions()]
            self.assertEqual(
                asked, fixture["expected_questions_after_discovery"]
            )
            self.assertFalse(
                set(asked) & set(fixture["discovered_facts"]),
                "a reused fact was asked again",
            )
            self.assertEqual(set(asked), set(fixture["client_answers"]))

    def test_fixture_binds_owner_approval_capacity_and_claims(self):
        fixture = load_fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(
                path, clock=fixed_clock, tenant_id=fixture["tenant_id"]
            )
            for fact_id, record in fixture["discovered_facts"].items():
                brief.record_fact(
                    fact_id,
                    record["value"],
                    provenance=record["provenance"],
                    source=record["source"],
                )
            while True:
                question = brief.ask_next()
                if question is None:
                    break
                brief.answer(question.fact_id, fixture["client_answers"][question.fact_id])
            for kind in REQUIRED_FOR_ASSETS:
                brief.assess_asset(kind, ab.ASSET_PRESENT, detail="fixture/" + kind)

            self.assertTrue(brief.is_sufficient())
            self.assertTrue(brief.is_bound() is False)
            self.assertFalse(brief.is_campaign_ready())

            owner = fixture["owner"]
            brief.bind_owner(
                owner["owner_id"],
                owner["name"],
                email=owner["email"],
                role=owner["role"],
                tenant_id=owner["tenant_id"],
            )
            brief.bind_approval(
                owner["owner_id"], scope=fixture["approval"]["scope"]
            )
            capacity = fixture["capacity"]
            brief.bind_capacity(
                owner["owner_id"],
                monthly_new_customers=capacity["monthly_new_customers"],
                fulfilment_lead_days=capacity["fulfilment_lead_days"],
                notes=capacity["notes"],
            )
            brief.bind_claims(owner["owner_id"], fixture["claims"])

            self.assertTrue(brief.is_bound())
            self.assertTrue(brief.is_campaign_ready())
            self.assertEqual(brief.planning_blockers(), [])
            self.assertEqual(brief.next_binding_questions(), [])

            reloaded = ab.AcquisitionBrief(
                path, clock=fixed_clock, tenant_id=fixture["tenant_id"]
            )
            self.assertEqual(reloaded.require_owner().owner_id, owner["owner_id"])
            self.assertTrue(reloaded.is_campaign_ready())
            self.assertEqual(
                len(reloaded.snapshot()["binding"]["claims"]["claims"]),
                len(fixture["claims"]),
            )


class OwnerBindingTests(unittest.TestCase):
    def test_owner_is_bound_with_provenance_timestamp_and_tenant(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory, tenant_id="tenant-a")
            owner = brief.bind_owner(
                "owner-1",
                "Accountable Owner",
                email="owner@example.test",
                tenant_id="tenant-a",
            )
            self.assertEqual(owner.owner_id, "owner-1")
            self.assertEqual(owner.tenant_id, "tenant-a")
            self.assertEqual(
                owner.recorded_at, FIXED_NOW.isoformat(timespec="microseconds")
            )
            self.assertEqual(brief.single_owner(), owner)
            self.assertEqual(brief.require_owner(), owner)

    def test_unattributed_brief_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            with self.assertRaises(ab.OwnerConflictError):
                brief.require_owner()
            self.assertFalse(brief.is_bound())
            self.assertIn(
                {
                    "kind": "binding_owner_unattributed",
                    "fact_id": "binding.owner",
                    "reason": "no accountable owner named",
                },
                brief.binding_blockers(),
            )
            self.assertFalse(brief.is_campaign_ready())
            self.assertEqual(
                [q.fact_id for q in brief.next_binding_questions()],
                ["binding.owner"],
            )

    def test_second_distinct_owner_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "First Owner")
            with self.assertRaises(ab.OwnerConflictError):
                brief.bind_owner("owner-2", "Second Owner")
            self.assertEqual(len(brief.owners()), 1)
            self.assertEqual(brief.require_owner().owner_id, "owner-1")

    def test_hand_edited_two_owner_brief_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            brief.bind_owner("owner-1", "First Owner")
            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            document["binding"]["owners"]["owner-2"] = {
                "owner_id": "owner-2",
                "name": "Second Owner",
                "email": None,
                "role": "owner",
                "tenant_id": None,
                "recorded_at": FIXED_NOW.isoformat(timespec="microseconds"),
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            reloaded = ab.AcquisitionBrief(path, clock=fixed_clock)
            with self.assertRaises(ab.OwnerConflictError):
                reloaded.require_owner()
            self.assertIn(
                "binding_owner_multiple",
                [blocker["kind"] for blocker in reloaded.binding_blockers()],
            )
            snapshot = reloaded.snapshot()
            self.assertIsNone(snapshot["binding"]["owner"])
            self.assertTrue(snapshot["binding"]["owner_ambiguous"])
            self.assertFalse(reloaded.is_campaign_ready())

    def test_owner_from_another_tenant_is_refused(self):
        fixture = load_fixture()
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory, tenant_id=fixture["tenant_id"])
            impostor = fixture["impostor_owner"]
            with self.assertRaises(ab.BindingError):
                brief.bind_owner(
                    impostor["owner_id"],
                    impostor["name"],
                    email=impostor["email"],
                    tenant_id=impostor["tenant_id"],
                )
            self.assertEqual(brief.owners(), [])

    def test_owner_without_tenant_on_a_tenant_scoped_brief_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory, tenant_id="tenant-a")
            with self.assertRaises(ab.BindingError):
                brief.bind_owner("owner-1", "Accountable Owner")
            self.assertEqual(brief.owners(), [])

    def test_absent_empty_and_wrong_type_owner_values_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            attacks = (
                (None, "Name"),
                ("", "Name"),
                ("   ", "Name"),
                (42, "Name"),
                ("owner-1", None),
                ("owner-1", ""),
                ("owner-1", "   "),
                ("owner-1", ["Owner"]),
            )
            for owner_id, name in attacks:
                with self.assertRaises(ab.BindingError):
                    brief.bind_owner(owner_id, name)
            with self.assertRaises(ab.BindingError):
                brief.bind_owner("owner-1", "Owner", email="not-an-email")
            with self.assertRaises(ab.BindingError):
                brief.bind_owner("owner-1", "Owner", role="   ")
            self.assertEqual(brief.owners(), [])
            self.assertFalse(os.path.exists(brief.path))

    def test_rebinding_the_same_owner_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            events = len(brief._state["interview"]["events"])
            brief.bind_owner("owner-1", "Owner")
            self.assertEqual(len(brief._state["interview"]["events"]), events)
            self.assertEqual(len(brief.owners()), 1)


class ApprovalBindingTests(unittest.TestCase):
    def test_approval_binds_the_owner_and_its_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            record = brief.bind_approval("owner-1", scope="30-day campaign")
            self.assertEqual(record["bound_by"], "owner-1")
            self.assertEqual(record["scope"], "30-day campaign")
            self.assertEqual(record["provenance"], ab.PROVENANCE_CLIENT_STATED)

    def test_approval_before_an_owner_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            with self.assertRaises(ab.OwnerConflictError):
                brief.bind_approval("owner-1", scope="30-day campaign")

    def test_approval_from_a_non_owner_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            with self.assertRaises(ab.BindingError):
                brief.bind_approval("owner-2", scope="30-day campaign")
            self.assertIsNone(brief.snapshot()["binding"]["approval"])

    def test_empty_scope_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            for scope in (None, "", "   ", 30):
                with self.assertRaises(ab.BindingError):
                    brief.bind_approval("owner-1", scope=scope)

    def test_approval_is_reused_and_never_re_asked(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            brief.bind_approval("owner-1", scope="30-day campaign")
            self.assertNotIn(
                "binding.approval",
                [q.fact_id for q in brief.next_binding_questions()],
            )
            brief.bind_approval("owner-1", scope="30-day campaign")
            self.assertEqual(
                brief.snapshot()["binding"]["approval"]["scope"], "30-day campaign"
            )


class CapacityBindingTests(unittest.TestCase):
    def test_capacity_records_the_owner_commitment(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            record = brief.bind_capacity(
                "owner-1", monthly_new_customers=10, fulfilment_lead_days=14
            )
            self.assertEqual(record["bound_by"], "owner-1")
            self.assertEqual(record["monthly_new_customers"], 10)
            self.assertEqual(record["fulfilment_lead_days"], 14)

    def test_wrong_type_negative_and_bool_capacity_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            attacks = ("ten", 10.5, True, -1, None)
            for value in attacks:
                with self.assertRaises(ab.BindingError):
                    brief.bind_capacity(
                        "owner-1",
                        monthly_new_customers=value,
                        fulfilment_lead_days=14,
                    )
                with self.assertRaises(ab.BindingError):
                    brief.bind_capacity(
                        "owner-1",
                        monthly_new_customers=10,
                        fulfilment_lead_days=value,
                    )
            self.assertIsNone(brief.snapshot()["binding"]["capacity"])

    def test_capacity_declared_by_a_non_owner_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            with self.assertRaises(ab.BindingError):
                brief.bind_capacity(
                    "owner-2", monthly_new_customers=10, fulfilment_lead_days=14
                )

    def test_zero_capacity_binds_but_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            brief.bind_capacity(
                "owner-1", monthly_new_customers=0, fulfilment_lead_days=14
            )
            self.assertIn(
                "binding_capacity_zero",
                [blocker["kind"] for blocker in brief.binding_blockers()],
            )
            self.assertFalse(brief.is_bound())


class ClaimsBindingTests(unittest.TestCase):
    def test_claims_bind_with_substantiation(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            record = brief.bind_claims(
                "owner-1",
                [
                    {"text": "Locally made", "substantiation": "studio photos"},
                    {"text": "Food safe", "substantiation": "supplier cert"},
                ],
            )
            self.assertEqual(record["bound_by"], "owner-1")
            self.assertEqual(len(record["claims"]), 2)

    def test_claim_without_substantiation_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            attacks = (
                [{"text": "Locally made"}],
                [{"text": "Locally made", "substantiation": ""}],
                [{"text": "Locally made", "substantiation": "   "}],
                [{"text": "", "substantiation": "studio photos"}],
                [{"substantiation": "studio photos"}],
                [{}],
            )
            for claims in attacks:
                with self.assertRaises(ab.BindingError):
                    brief.bind_claims("owner-1", claims)
            self.assertIsNone(brief.snapshot()["binding"]["claims"])

    def test_wrong_shape_claims_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            for claims in ("Locally made", {"text": "x"}, [["x"]], [None], 42):
                with self.assertRaises(ab.BindingError):
                    brief.bind_claims("owner-1", claims)

    def test_claims_approved_by_a_non_owner_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            with self.assertRaises(ab.BindingError):
                brief.bind_claims(
                    "owner-2",
                    [{"text": "Locally made", "substantiation": "photos"}],
                )

    def test_explicit_empty_claim_list_is_an_answer_not_a_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            record = brief.bind_claims("owner-1", [])
            self.assertEqual(record["claims"], [])
            self.assertNotIn(
                "binding.claims",
                [q.fact_id for q in brief.next_binding_questions()],
            )


class BindingQuestionAndBlockerTests(unittest.TestCase):
    def test_binding_questions_are_ordered_owner_first_and_disappear_when_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            self.assertEqual(
                [q.fact_id for q in brief.next_binding_questions()],
                ["binding.owner"],
            )
            brief.bind_owner("owner-1", "Owner")
            self.assertEqual(
                [q.fact_id for q in brief.next_binding_questions()],
                ["binding.approval", "binding.capacity", "binding.claims"],
            )
            bind_everything(brief, owner_id="owner-1")
            self.assertEqual(brief.next_binding_questions(), [])

    def test_missing_each_binding_is_named_as_its_own_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            brief.bind_owner("owner-1", "Owner")
            kinds = [blocker["kind"] for blocker in brief.binding_blockers()]
            self.assertEqual(kinds, ["binding_missing"] * 3)
            self.assertEqual(
                [blocker["fact_id"] for blocker in brief.binding_blockers()],
                ["binding.approval", "binding.capacity", "binding.claims"],
            )
            self.assertFalse(brief.is_bound())
            self.assertFalse(brief.is_campaign_ready())

    def test_binding_signed_by_a_different_owner_is_refused_on_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            brief.bind_owner("owner-1", "First Owner")
            brief.bind_approval("owner-1", scope="30-day campaign")
            with open(path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            document["binding"]["owners"] = {
                "owner-2": {
                    "owner_id": "owner-2",
                    "name": "Replacement Owner",
                    "email": None,
                    "role": "owner",
                    "tenant_id": None,
                    "recorded_at": FIXED_NOW.isoformat(timespec="microseconds"),
                }
            }
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(document, handle)

            reloaded = ab.AcquisitionBrief(path, clock=fixed_clock)
            self.assertEqual(reloaded.require_owner().owner_id, "owner-2")
            self.assertIn(
                "binding_owner_mismatch",
                [blocker["kind"] for blocker in reloaded.binding_blockers()],
            )
            self.assertFalse(reloaded.is_bound())

    def test_completed_bindings_are_persisted_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            brief = new_brief(directory)
            bind_everything(brief)
            self.assertEqual(
                [name for name in os.listdir(directory) if name.endswith(".tmp")],
                [],
            )
            with open(brief.path, "r", encoding="utf-8") as handle:
                document = json.load(handle)
            self.assertEqual(set(document["binding"]["owners"]), {"owner-1"})
            for key in ("approval", "capacity", "claims"):
                self.assertIsNotNone(document["binding"][key])
            events = [
                event["event"] for event in document["interview"]["events"]
            ]
            for event in (
                "owner_bound",
                "approval_bound",
                "capacity_bound",
                "claims_bound",
            ):
                self.assertIn(event, events)


class LegacyAndCorruptBindingTests(unittest.TestCase):
    def test_brief_without_a_binding_section_loads_unattributed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema": ab.SCHEMA,
                        "facts": {},
                        "unresolved": {},
                        "interview": {},
                        "assets": {},
                    },
                    handle,
                )
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            with self.assertRaises(ab.OwnerConflictError):
                brief.require_owner()
            self.assertFalse(brief.is_bound())
            self.assertIsNone(brief.snapshot()["binding"]["owner"])

    def test_non_object_binding_section_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema": ab.SCHEMA,
                        "facts": {},
                        "unresolved": {},
                        "interview": {},
                        "assets": {},
                        "binding": [],
                    },
                    handle,
                )
            with self.assertRaises(ab.BriefCorruptError):
                ab.AcquisitionBrief(path, clock=fixed_clock)

    def test_malformed_owner_record_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema": ab.SCHEMA,
                        "facts": {},
                        "unresolved": {},
                        "interview": {},
                        "assets": {},
                        "binding": {"owners": {"owner-1": "not-an-object"}},
                    },
                    handle,
                )
            with self.assertRaises(ab.BriefCorruptError):
                ab.AcquisitionBrief(path, clock=fixed_clock)


class ReadPathOwnerValidationTests(unittest.TestCase):
    """The owner guarantee must survive a reload, not only the write call.

    A brief is a persistent JSON document. Anything that can edit that file
    reaches ``AcquisitionBrief(...)`` without ever calling ``bind_owner``, so
    every refusal proved here happens at the constructor, on real bytes on
    disk: build through the sanctioned API, hand-edit one field, reload.
    """

    def _document(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, path, document):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle)

    def test_hand_edited_owner_fields_are_refused_on_reload(self):
        mutations = (
            ("name", "   "),
            ("name", ""),
            ("name", None),
            ("name", 42),
            ("role", ""),
            ("role", "   "),
            ("role", None),
            ("email", ""),
            ("email", "not-an-email"),
            ("owner_id", ""),
            ("owner_id", None),
        )
        for field, bad_value in mutations:
            with self.subTest(field=field, value=bad_value):
                with tempfile.TemporaryDirectory() as directory:
                    path = os.path.join(directory, "brief.json")
                    brief = ab.AcquisitionBrief(path, clock=fixed_clock)
                    bind_everything(brief)
                    self.assertTrue(brief.is_bound())

                    document = self._document(path)
                    document["binding"]["owners"]["owner-1"][field] = bad_value
                    self._write(path, document)
                    before = self._document(path)

                    # Refusal at the point of use: a real reload of real bytes.
                    with self.assertRaises(ab.BriefCorruptError):
                        ab.AcquisitionBrief(path, clock=fixed_clock)
                    # Refusal is not a silent repair of the file.
                    self.assertEqual(self._document(path), before)

    def test_hand_edited_owner_missing_a_required_field_is_refused(self):
        for field in ("owner_id", "name", "role"):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    path = os.path.join(directory, "brief.json")
                    brief = ab.AcquisitionBrief(path, clock=fixed_clock)
                    bind_everything(brief)
                    document = self._document(path)
                    del document["binding"]["owners"]["owner-1"][field]
                    self._write(path, document)
                    with self.assertRaises(ab.BriefCorruptError):
                        ab.AcquisitionBrief(path, clock=fixed_clock)

    def test_hand_edited_foreign_tenant_owner_is_refused_on_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock, tenant_id="tenant-a")
            brief.bind_owner(
                "owner-1", "Accountable Owner", email="owner@example.test",
                tenant_id="tenant-a",
            )
            document = self._document(path)
            document["binding"]["owners"]["owner-1"]["tenant_id"] = "tenant-b"
            self._write(path, document)
            with self.assertRaises(ab.BriefCorruptError):
                ab.AcquisitionBrief(path, clock=fixed_clock, tenant_id="tenant-a")

    def test_tenant_scoped_brief_refuses_a_reloaded_owner_with_no_tenant(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock, tenant_id="tenant-a")
            brief.bind_owner(
                "owner-1", "Accountable Owner", email="owner@example.test",
                tenant_id="tenant-a",
            )
            document = self._document(path)
            document["binding"]["owners"]["owner-1"]["tenant_id"] = None
            self._write(path, document)
            with self.assertRaises(ab.BriefCorruptError):
                ab.AcquisitionBrief(path, clock=fixed_clock, tenant_id="tenant-a")

    def test_load_method_refuses_a_tampered_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            bind_everything(brief)
            self.assertTrue(brief.is_bound())
            document = self._document(path)
            document["binding"]["owners"]["owner-1"]["name"] = " "
            self._write(path, document)
            with self.assertRaises(ab.BriefCorruptError):
                brief.load()

    def test_a_legal_hand_edit_still_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "brief.json")
            brief = ab.AcquisitionBrief(path, clock=fixed_clock)
            bind_everything(brief)
            document = self._document(path)
            document["binding"]["owners"]["owner-1"]["name"] = "Renamed Owner"
            self._write(path, document)

            reloaded = ab.AcquisitionBrief(path, clock=fixed_clock)
            self.assertEqual(reloaded.require_owner().name, "Renamed Owner")
            self.assertTrue(reloaded.is_bound())

    def test_bare_document_with_an_invalid_owner_is_corrupt(self):
        # No API call ever ran here: exactly the reported hand-edited file.
        for field, bad_value in (
            ("name", "   "),
            ("role", ""),
            ("email", "nope"),
        ):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as directory:
                    path = os.path.join(directory, "brief.json")
                    owner = {
                        "owner_id": "owner-1",
                        "name": "Accountable Owner",
                        "email": "owner@example.test",
                        "role": "owner",
                        "tenant_id": None,
                        "recorded_at": FIXED_NOW.isoformat(timespec="microseconds"),
                    }
                    owner[field] = bad_value
                    document = {
                        "schema": ab.SCHEMA,
                        "facts": {},
                        "unresolved": {},
                        "interview": {},
                        "assets": {},
                        "binding": {
                            "owners": {"owner-1": owner},
                            "approval": {
                                "bound_by": "owner-1",
                                "scope": "30-day campaign",
                                "approved_at": FIXED_NOW.isoformat(
                                    timespec="microseconds"
                                ),
                                "provenance": ab.PROVENANCE_CLIENT_STATED,
                                "recorded_at": FIXED_NOW.isoformat(
                                    timespec="microseconds"
                                ),
                            },
                            "capacity": {
                                "bound_by": "owner-1",
                                "monthly_new_customers": 10,
                                "fulfilment_lead_days": 14,
                                "recorded_at": FIXED_NOW.isoformat(
                                    timespec="microseconds"
                                ),
                            },
                            "claims": {
                                "bound_by": "owner-1",
                                "claims": [],
                                "recorded_at": FIXED_NOW.isoformat(
                                    timespec="microseconds"
                                ),
                            },
                        },
                    }
                    self._write(path, document)
                    with self.assertRaises(ab.BriefCorruptError):
                        ab.AcquisitionBrief(path, clock=fixed_clock)


if __name__ == "__main__":
    unittest.main(verbosity=2)
