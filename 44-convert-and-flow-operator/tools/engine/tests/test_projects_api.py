"""Projects (WF32) focused tests -- offline, fixture-catalog only.

Covers acceptance B18, B19 and IG-PROJECT-01, 02, 03, 04, 05, 06, 08.

Every wire name comes from the explicit fixture catalog in
``cli_anything.gohighlevel.public.projects``; the module refuses a fixture
catalog unless ``allow_fixture=True``, which is set only here.  No live host is
contacted: ``FakeTransport`` replays scripted bodies.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    fake_auth,
    fake_tenant,
    resp,
)

from cli_anything.gohighlevel.public import projects as pj  # noqa: E402
from cli_anything.gohighlevel.public.adapter import ApprovalRef  # noqa: E402
from cli_anything.gohighlevel.public.auth import AuthKind, TenantBinding  # noqa: E402
from cli_anything.gohighlevel.public.capability import (  # noqa: E402
    Capability,
    CapabilityGate,
)
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402

FIXED_NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
DUE = "2026-12-01"


def body(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


def ok(payload: dict):
    return resp(200, body=body(payload))


def project_gate(catalog: pj.ProjectsCatalog, tenant: str = SYNTHETIC_TENANT) -> CapabilityGate:
    gate = CapabilityGate(tenant=tenant)
    for operation_id in catalog.operation_ids:
        row = catalog.row(operation_id)
        capability = Capability(
            operation_id=operation_id,
            contract_verified=True,
            adapter_built=True,
            offline_tests_passed=True,
            read_verified=True,
            canary_verified=True,
        )
        gate.enable(capability, write=row.write)
    return gate


def service(responses, *, catalog=None, gate=None, auth=None, tenant=None):
    catalog = catalog or pj.ProjectsCatalog.fixture()
    fake = FakeTransport(responses)
    svc = pj.ProjectsService.connect(
        auth=auth or fake_auth(),
        tenant=tenant or fake_tenant(),
        catalog=catalog,
        transport=fake,
        gate=gate if gate is not None else project_gate(catalog),
        allow_fixture=True,
        clock=lambda: FIXED_NOW,
    )
    return svc, fake


def paths(fake) -> list[str]:
    return [request["url"] for request in fake.requests]


class AvailabilityTests(unittest.TestCase):
    def test_ui_and_api_are_independent(self):
        """IG-PROJECT-01: UI available does not imply API beta."""
        ui = pj.AvailabilityEvidence(
            dimension="ui_labs",
            state=pj.AvailabilityState.available,
            source="labs_capture",
            reference="fixture:ui",
            checked_at="2026-11-08T00:00:00+00:00",
        )
        api = pj.AvailabilityEvidence.unknown("api_beta")
        availability = pj.ProjectsAvailability.from_records(ui_labs=ui, api_beta=api)
        availability.require_ui()
        with self.assertRaises(ContractViolation) as caught:
            availability.require_api()
        self.assertEqual(caught.exception.rule, "projects_feature_unavailable")
        self.assertEqual(caught.exception.detail["dimension"], "api_beta")
        self.assertTrue(availability.as_mapping()["independent"])

    def test_api_evidence_cannot_come_from_ui(self):
        with self.assertRaises(ContractViolation) as caught:
            pj.AvailabilityEvidence(
                dimension="api_beta",
                state=pj.AvailabilityState.available,
                source="ui_labs_capture",
                reference="fixture:api",
                checked_at="2026-11-08T00:00:00+00:00",
            )
        self.assertEqual(
            caught.exception.rule, "projects_api_availability_inferred_from_ui"
        )

    def test_denial_classification_needs_explicit_beta_marker(self):
        class Result:
            status = pj.Status.denied
            error = {"code": "SOME_BETA_DENIED"}

        self.assertIs(
            pj.classify_denial(Result(), beta_error_code="OTHER"),
            pj.AvailabilityState.forbidden,
        )
        self.assertIs(
            pj.classify_denial(Result(), beta_error_code="SOME_BETA_DENIED"),
            pj.AvailabilityState.not_available,
        )


class CredentialAndCatalogTests(unittest.TestCase):
    def test_credential_must_match_tenant_before_transport(self):
        fake = FakeTransport([])
        with self.assertRaises(ContractViolation) as caught:
            pj.ProjectsService.connect(
                auth=fake_auth(location_id="loc_other_0002"),
                tenant=fake_tenant(),
                catalog=pj.ProjectsCatalog.fixture(),
                transport=fake,
                gate=project_gate(pj.ProjectsCatalog.fixture()),
                allow_fixture=True,
            )
        self.assertEqual(caught.exception.rule, "projects_tenant_not_bound")
        self.assertEqual(fake.call_count, 0)

    def test_fixture_catalog_refused_without_explicit_opt_in(self):
        with self.assertRaises(ContractViolation) as caught:
            pj.ProjectsService.connect(
                auth=fake_auth(),
                tenant=fake_tenant(),
                catalog=pj.ProjectsCatalog.fixture(),
                transport=FakeTransport([]),
                allow_fixture=False,
            )
        self.assertEqual(caught.exception.rule, "projects_fixture_catalog_refused")

    def test_discovery_document_missing_fields_fails_loudly(self):
        with self.assertRaises(ContractViolation) as caught:
            pj.ProjectsCatalog.from_document(
                {"evidence": "discovery", "operations": {"projects.tasks.create": {"method": "POST"}}}
            )
        self.assertEqual(caught.exception.rule, "projects_discovery_incomplete")
        self.assertIn("path_template", caught.exception.detail["missing"])

    def test_location_id_is_never_sent_for_token_binding(self):
        with self.assertRaises(ContractViolation) as caught:
            pj._forbid_location_id({}, {}, {"locationId": "loc_x"}, "projects.tasks.create")
        self.assertEqual(caught.exception.rule, "projects_location_id_not_allowed")

    def test_default_deny_gate_blocks_before_transport(self):
        fake = FakeTransport([ok({"id": "space_1"})])
        svc = pj.ProjectsService.connect(
            auth=fake_auth(),
            tenant=fake_tenant(),
            catalog=pj.ProjectsCatalog.fixture(),
            transport=fake,
            allow_fixture=True,
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.create_space("Delivery")
        self.assertEqual(caught.exception.rule, "projects_call_not_ok")
        self.assertEqual(caught.exception.detail["rule"], "capability_disabled")
        self.assertEqual(fake.call_count, 0)


class SpaceAndListTests(unittest.TestCase):
    def test_space_create_discovers_default_list_without_duplicate(self):
        """IG-PROJECT-03 / B18."""
        svc, fake = service(
            [
                ok({"id": "space_1", "name": "Delivery"}),
                ok({"name": "Delivery", "spaces": []}),
                ok({"id": "space_1", "name": "Delivery"}),
                ok({"lists": [{"id": "list_1", "isDefault": True}]}),
            ]
        )
        space = svc.create_space("Delivery")
        self.assertEqual(space.id, "space_1")
        self.assertTrue(space.verified)
        default = svc.discover_default_list(space.id)
        self.assertIsNotNone(default)
        self.assertEqual(default.id, "list_1")
        creates = [
            request
            for request in fake.requests
            if request["method"] == "POST" and request["url"].endswith("/lists")
        ]
        self.assertEqual(creates, [])
        self.assertEqual(fake.call_count, 4)

    def test_ambiguous_default_lists_are_refused(self):
        svc, fake = service(
            [
                ok(
                    {
                        "lists": [
                            {"id": "list_1", "isDefault": True},
                            {"id": "list_2", "isDefault": True},
                        ]
                    }
                )
            ]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.discover_default_list("space_1")
        self.assertEqual(caught.exception.rule, "projects_default_list_ambiguous")
        self.assertEqual(fake.call_count, 1)

    def test_no_default_list_returns_none(self):
        svc, _ = service([ok({"lists": []})])
        self.assertIsNone(svc.discover_default_list("space_1"))


class PaginationTests(unittest.TestCase):
    def test_cursor_pagination_no_duplicates_or_missing(self):
        """IG-PROJECT-06 / B18."""
        svc, fake = service(
            [
                ok({"tasks": [{"id": "t1"}, {"id": "t2"}], "meta": {"nextCursor": "c2"}}),
                ok({"tasks": [{"id": "t3"}], "meta": {}}),
            ]
        )
        page = svc.list_tasks("list_1")
        self.assertEqual([record["id"] for record in page.records], ["t1", "t2", "t3"])
        self.assertEqual(page.pages, 2)
        self.assertEqual(page.tokens, ("c2",))
        self.assertEqual(fake.requests[1]["query"]["cursor"], "c2")

    def test_search_after_pagination_uses_last_record_token(self):
        svc, fake = service(
            [
                ok(
                    {
                        "members": [
                            {"id": "m1", "searchAfter": "s1"},
                            {"id": "m2", "searchAfter": "s2"},
                        ]
                    }
                ),
                ok({"members": [{"id": "m3"}]}),
            ]
        )
        page = svc.list_members("space_1")
        self.assertEqual([record["id"] for record in page.records], ["m1", "m2", "m3"])
        self.assertEqual(fake.requests[1]["query"]["searchAfter"], "s2")

    def test_skip_limit_pagination_honours_total(self):
        svc, fake = service(
            [
                ok({"spaces": [{"id": "s1"}, {"id": "s2"}], "total": 3}),
                ok({"spaces": [{"id": "s3"}], "total": 3}),
            ]
        )
        page = svc.list_spaces()
        self.assertEqual([record["id"] for record in page.records], ["s1", "s2", "s3"])
        self.assertEqual(fake.requests[1]["query"]["skip"], 2)

    def test_duplicate_record_across_pages_is_refused(self):
        svc, _ = service(
            [
                ok({"tasks": [{"id": "t1"}], "meta": {"nextCursor": "c2"}}),
                ok({"tasks": [{"id": "t1"}], "meta": {}}),
            ]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.list_tasks("list_1")
        self.assertEqual(caught.exception.rule, "projects_pagination_duplicate")

    def test_repeated_token_is_refused(self):
        svc, _ = service(
            [
                ok({"tasks": [{"id": "t1"}], "meta": {"nextCursor": "c2"}}),
                ok({"tasks": [{"id": "t2"}], "meta": {"nextCursor": "c2"}}),
            ]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.list_tasks("list_1")
        self.assertEqual(caught.exception.rule, "projects_pagination_token_repeated")

    def test_short_page_against_reported_total_is_refused(self):
        svc, _ = service([ok({"spaces": [{"id": "s1"}], "total": 5})])
        with self.assertRaises(ContractViolation) as caught:
            svc.list_spaces()
        self.assertEqual(caught.exception.rule, "projects_pagination_incomplete")


class TaskTests(unittest.TestCase):
    def test_task_needs_title_before_transport(self):
        svc, fake = service([])
        with self.assertRaises(ContractViolation) as caught:
            svc.create_task("  ", DUE, list_id="list_1")
        self.assertEqual(caught.exception.rule, "projects_title_required")
        self.assertEqual(fake.call_count, 0)

    def test_task_needs_due_date_before_transport(self):
        svc, fake = service([])
        with self.assertRaises(ContractViolation) as caught:
            svc.create_task("Write", None, list_id="list_1")
        self.assertEqual(caught.exception.rule, "projects_due_date_required")
        self.assertEqual(fake.call_count, 0)

    def test_naive_datetime_refused(self):
        with self.assertRaises(ContractViolation) as caught:
            pj.normalize_due_date("2026-12-01T17:30:00", today=FIXED_NOW.date())
        self.assertEqual(caught.exception.rule, "projects_due_date_timezone_required")

    def test_past_due_date_refused(self):
        with self.assertRaises(ContractViolation) as caught:
            pj.normalize_due_date("2023-01-01", today=FIXED_NOW.date())
        self.assertEqual(caught.exception.rule, "projects_due_date_in_past")

    def test_offset_is_preserved(self):
        self.assertEqual(
            pj.normalize_due_date(
                "2026-12-01T17:30:00-05:00", today=FIXED_NOW.date()
            ),
            "2026-12-01T17:30:00-05:00",
        )

    def test_status_resolved_from_list_statuses_and_no_status_group(self):
        """B19 / IG-PROJECT-04."""
        svc, fake = service(
            [
                ok({"statuses": [{"id": "st1", "name": "Done"}], "total": 1}),
                ok({"id": "task_1", "title": "Write"}),
                ok({"listId": "list_1", "tasks": []}),
                ok({"id": "task_1", "listId": "list_1"}),
            ]
        )
        created = svc.create_task(
            "Write", DUE, list_id="list_1", status="Done", assignee_id="user_1"
        )
        self.assertEqual(created.id, "task_1")
        self.assertTrue(created.verified)
        task_request = fake.requests[1]
        self.assertEqual(task_request["body"]["status"], "st1")
        self.assertEqual(task_request["body"]["assigneeId"], "user_1")
        self.assertEqual(task_request["body"]["dueDate"], DUE)
        self.assertNotIn("statusGroup", task_request["body"])
        self.assertNotIn("locationId", task_request["body"])

    def test_unknown_status_refused_before_task_write(self):
        svc, fake = service([ok({"statuses": [{"id": "st1", "name": "Done"}], "total": 1})])
        with self.assertRaises(ContractViolation) as caught:
            svc.create_task("Write", DUE, list_id="list_1", status="Blocked")
        self.assertEqual(caught.exception.rule, "projects_status_not_in_list")
        self.assertEqual(fake.call_count, 1)

    def test_multiple_assignees_refused_before_transport(self):
        svc, fake = service([])
        with self.assertRaises(ContractViolation) as caught:
            svc.create_task(
                "Write", DUE, list_id="list_1", assignee_ids=("user_1", "user_2")
            )
        self.assertEqual(caught.exception.rule, "projects_multiple_assignees")
        self.assertEqual(fake.call_count, 0)

    def test_subtask_uses_parent_task_id_and_home_list(self):
        svc, fake = service(
            [
                ok({"id": "parent_1", "listId": "home_list"}),
                ok({"statuses": [{"id": "st1", "name": "Done"}], "total": 1}),
                ok({"id": "sub_1", "title": "Step"}),
                ok({"listId": "home_list", "tasks": []}),
                ok({"id": "sub_1", "listId": "home_list"}),
            ]
        )
        created = svc.create_subtask(
            "parent_1", "Step", DUE, status="st1", assignee_id="user_1"
        )
        self.assertEqual(created.id, "sub_1")
        task_request = fake.requests[2]
        self.assertIn("/lists/home_list/tasks", task_request["url"])
        self.assertEqual(task_request["body"]["parentTaskId"], "parent_1")
        self.assertEqual(task_request["body"]["status"], "st1")

    def test_add_to_list_preserves_home_list_identity(self):
        svc, fake = service(
            [
                ok({"id": "task_1", "listId": "home_a"}),
                ok({"ok": True}),
                ok({"id": "task_1", "listId": "home_a"}),
                ok({"id": "task_1", "listId": "home_a"}),
            ]
        )
        result = svc.add_task_to_list("task_1", "list_b")
        self.assertEqual(result.verification, "home_list_preserved")
        methods = [(request["method"], request["url"]) for request in fake.requests]
        self.assertNotIn(("POST", "/projects/_fixture/lists/list_b/tasks"), methods)
        self.assertIn(
            ("POST", "/projects/_fixture/tasks/task_1/lists"), methods
        )
        self.assertEqual(fake.requests[1]["body"], {"listId": "list_b"})

    def test_comment_and_recurrence_are_their_own_operations(self):
        svc, fake = service(
            [
                ok({"id": "comment_1"}),
                ok({"taskId": "task_1", "comments": []}),
                ok({"id": "task_1"}),
                ok({"id": "task_1"}),
            ]
        )
        svc.add_comment("task_1", "Looks good")
        svc.set_recurrence("task_1", {"frequency": "weekly", "interval": 1})
        urls = [request["url"] for request in fake.requests]
        self.assertTrue(any(url.endswith("/comments") for url in urls))
        self.assertTrue(any(url.endswith("/recurrence") for url in urls))
        with self.assertRaises(ContractViolation) as caught:
            svc.set_recurrence("task_1", "RRULE:FREQ=WEEKLY")
        self.assertEqual(caught.exception.rule, "projects_rrule_forbidden")


class MembershipTests(unittest.TestCase):
    def test_additive_update_never_removes_members(self):
        """IG-PROJECT-05."""
        svc, fake = service(
            [
                ok({"ok": True}),
                ok({"spaceId": "space_1", "members": []}),
                ok({"spaceId": "space_1", "members": [{"id": "m2"}]}),
            ]
        )
        svc.add_members("space_1", ["m2"])
        self.assertNotIn("DELETE", [request["method"] for request in fake.requests])
        self.assertEqual(fake.requests[0]["body"], {"memberIds": ["m2"]})
        svc.list_members("space_1")

    def test_removal_uses_documented_operation_and_proves_absence(self):
        svc, fake = service(
            [
                ok({"ok": True}),
                ok({"spaceId": "space_1", "members": []}),
                ok({"spaceId": "space_1", "members": [{"id": "m1"}]}),
            ]
        )
        result = svc.remove_member(
            "space_1", "m2", approval=ApprovalRef(ref="approval_synthetic_0001")
        )
        self.assertEqual(result.verification, "absence_proved")
        self.assertEqual(fake.requests[0]["method"], "DELETE")
        self.assertTrue(fake.requests[0]["url"].endswith("/members/m2"))

    def test_removal_reported_still_present_is_refused(self):
        svc, _ = service(
            [
                ok({"ok": True}),
                ok({"spaceId": "space_1", "members": []}),
                ok({"spaceId": "space_1", "members": [{"id": "m2"}]}),
            ]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.remove_member(
                "space_1", "m2", approval=ApprovalRef(ref="approval_synthetic_0001")
            )
        self.assertEqual(caught.exception.rule, "projects_member_still_present")


class ParentDeletionTests(unittest.TestCase):
    def test_delete_requires_impact_authorization(self):
        """IG-PROJECT-08."""
        svc, fake = service(
            [ok({"tasks": [{"id": "t1"}, {"id": "t2"}], "meta": {}})]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.delete_list("list_1", space_id="space_1")
        self.assertEqual(
            caught.exception.rule, "projects_impact_authorization_required"
        )
        self.assertEqual(caught.exception.detail["child_count"], 2)
        self.assertEqual(fake.call_count, 1)
        self.assertNotIn("DELETE", [request["method"] for request in fake.requests])

    def test_delete_with_bound_impact_authorization(self):
        svc, _ = service(
            [ok({"tasks": [{"id": "t1"}, {"id": "t2"}], "meta": {}})]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.delete_list("list_1", space_id="space_1")
        fingerprint = caught.exception.detail["report_fingerprint"]

        svc2, fake2 = service(
            [
                ok({"tasks": [{"id": "t1"}, {"id": "t2"}], "meta": {}}),
                ok({"ok": True}),
                ok({"spaceId": "space_1", "lists": []}),
            ]
        )
        obj = svc2.delete_list(
            "list_1",
            space_id="space_1",
            authorization=pj.ImpactAuthorization(
                report_fingerprint=fingerprint,
                approved_by="operator",
                reference="approval_synthetic_0001",
            ),
        )
        self.assertEqual(obj.kind, "deleted")
        self.assertEqual(fake2.requests[-2]["method"], "DELETE")

    def test_wrong_impact_fingerprint_refused(self):
        svc, _ = service([ok({"tasks": [{"id": "t1"}], "meta": {}})])
        with self.assertRaises(ContractViolation) as caught:
            svc.delete_list(
                "list_1",
                space_id="space_1",
                authorization=pj.ImpactAuthorization(
                    report_fingerprint="0" * 64,
                    approved_by="operator",
                    reference="approval_synthetic_0001",
                ),
            )
        self.assertEqual(
            caught.exception.rule, "projects_impact_authorization_required"
        )


class VerificationTests(unittest.TestCase):
    def test_create_is_verified_by_a_read_of_the_created_id(self):
        svc, _ = service(
            [
                ok({"id": "space_1", "name": "Delivery"}),
                ok({"name": "Delivery", "spaces": []}),
                ok({"id": "space_1"}),
            ]
        )
        obj = svc.create_space("Delivery")
        self.assertTrue(obj.verified)
        self.assertEqual(obj.verification, "read_by_id")

    def test_create_readback_mismatch_is_refused(self):
        svc, _ = service(
            [
                ok({"id": "space_1", "name": "Delivery"}),
                ok({"name": "Delivery", "spaces": []}),
                ok({"id": "space_other"}),
            ]
        )
        with self.assertRaises(ContractViolation) as caught:
            svc.create_space("Delivery")
        self.assertEqual(caught.exception.rule, "projects_verification_mismatch")

    def test_interface_and_fixture_export(self):
        interface = pj.projects_interface()
        self.assertEqual(interface["interface_version"], 1)
        self.assertEqual(len(interface["operations"]), len(pj.REQUIRED_OPERATION_IDS))
        fixtures = pj.synthetic_fixtures()
        self.assertEqual(fixtures["availability"]["ui_labs"]["state"], "available")
        self.assertEqual(fixtures["availability"]["api_beta"]["state"], "unknown")
        self.assertEqual(len(fixtures["permissions"]["private_space_members"]), 2)


if __name__ == "__main__":
    unittest.main()
