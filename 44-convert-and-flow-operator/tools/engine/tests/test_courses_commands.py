"""WF06 ``courses`` command group tests (offline).

WF03 registers the group; these tests prove the module is registrable and that
each command reaches ``public/courses.py`` -> ``PublicGhlAdapter`` with the
documented DTO separation.  No socket is opened.
"""

from __future__ import annotations

import json
import os
import sys
import unittest

import click
from click.testing import CliRunner

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_TENANT,
    FakeTransport,
    enabled_gate,
    fake_tenant,
    make_adapter,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.commands import courses as commands  # noqa: E402
from cli_anything.gohighlevel.public import courses as api  # noqa: E402

ROWS = registry(
    row(
        api.OP_COURSE_CREATE,
        method="POST",
        path_template="/courses/products",
        tenant_binding="query.locationId",
        write=True,
    ),
    row(
        api.OP_COURSE_GET,
        method="GET",
        path_template="/courses/products/{productId}",
        tenant_binding="query.locationId",
    ),
    row(
        api.OP_ENROLLMENT_CREATE,
        method="POST",
        path_template="/courses/enrollments",
        tenant_binding="body.locationId",
        write=True,
    ),
)


def build_runtime(responses: list):
    transport = FakeTransport(responses)
    adapter = make_adapter(
        transport, ROWS, gate=enabled_gate(list(ROWS.values()))
    )
    tenant = fake_tenant()

    def get_runtime(_ctx: click.Context):
        return adapter, tenant

    return get_runtime, transport


class CourseCommandsTest(unittest.TestCase):
    def test_register_adds_courses_group(self) -> None:
        root = click.Group("root")
        get_runtime, _ = build_runtime([])
        group = commands.register(root, get_runtime=get_runtime)
        self.assertIn("courses", root.commands)
        self.assertEqual(
            set(group.commands),
            {
                "create",
                "category-create",
                "lesson-create",
                "import",
                "enroll",
                "revoke-preview",
                "enrollments",
            },
        )

    def test_create_sends_title_only_body_and_location_query(self) -> None:
        get_runtime, transport = build_runtime(
            [
                resp(201, b'{"id":"course_product_synthetic_0001"}'),
                resp(200, b'{"id":"course_product_synthetic_0001"}'),
            ]
        )
        group = commands.build_group(get_runtime)
        result = CliRunner().invoke(
            group,
            [
                "create",
                "--title",
                "Launch 101",
                "--readback-operation",
                api.OP_COURSE_GET,
                "--readback-path-params-json",
                '{"productId":"course_product_synthetic_0001"}',
                "--readback-expect-json",
                '{"id":"course_product_synthetic_0001"}',
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output.strip().splitlines()[0])
        self.assertEqual(payload["status"], "Status.ok")
        self.assertEqual(transport.requests[0]["body"], {"title": "Launch 101"})
        self.assertEqual(
            transport.requests[0]["query"], {"locationId": SYNTHETIC_TENANT}
        )

    def test_enroll_without_readback_refuses_loudly(self) -> None:
        get_runtime, transport = build_runtime([])
        group = commands.build_group(get_runtime)
        result = CliRunner().invoke(
            group,
            ["enroll", "--contact-id", "contact_1", "--offer-id", "offer_1"],
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("readback_required", result.output)
        self.assertEqual(transport.call_count, 0)

    def test_revoke_preview_reports_affected_set(self) -> None:
        get_runtime, _ = build_runtime([])
        group = commands.build_group(get_runtime)
        result = CliRunner().invoke(
            group,
            [
                "revoke-preview",
                "--offer-id",
                "offer_1",
                "--included-product-ids",
                "p2,p1,p2",
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        payload = json.loads(result.output.strip())
        self.assertEqual(payload["affected_product_ids"], ["p1", "p2"])
        self.assertEqual(payload["affected_count"], 2)
        self.assertTrue(payload["requires_confirmation"])

    def test_enrollments_command_passes_cursor_query(self) -> None:
        rows = registry(
            *[
                item
                for item in ROWS.values()
            ],
            # extend the fixture with the read row the command needs
            row(
                api.OP_PRODUCT_ENROLLMENTS_LIST,
                method="GET",
                path_template="/courses/enrollments",
                tenant_binding="query.locationId",
            ),
        )
        transport = FakeTransport([resp(200, b'{"total":0}')])
        adapter = make_adapter(
            transport, rows, gate=enabled_gate(list(rows.values()))
        )
        tenant = fake_tenant()
        group = commands.build_group(lambda _ctx: (adapter, tenant))
        result = CliRunner().invoke(
            group, ["enrollments", "--limit", "2", "--cursor", "c1"]
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(
            transport.last["query"],
            {"locationId": SYNTHETIC_TENANT, "limit": 2, "cursor": "c1"},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
