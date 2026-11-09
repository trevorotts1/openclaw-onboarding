"""WF06 Courses public adapter contract tests.

Offline only.  Every request is replayed by ``_public_contract_fakes``; no
socket is opened and no live GoHighLevel call is made.  The operation rows used
here are an explicit synthetic fixture (WF00 owns the real registry rows), so a
row-shape change is a visible failure, never a silent drift.

Acceptance mapping:
  A08       -- DTO separation for course/category/lesson bodies
  A11       -- import lifecycle: processing is not completed creation
  IG-COURSE-01 -- every call routes through PublicGhlAdapter
  IG-COURSE-04 -- course ids never collide with commerce product ids/locations
  IG-COURSE-07 -- already-enrolled resolves idempotently; no payment claim
  IG-COURSE-08 -- revocation impact is computed before removal
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _public_contract_fakes import (  # noqa: E402
    SYNTHETIC_CONTACT,
    SYNTHETIC_TENANT,
    FakeTransport,
    approval,
    enabled_gate,
    fake_tenant,
    make_adapter,
    registry,
    resp,
    row,
)

from cli_anything.gohighlevel.public import courses as api  # noqa: E402
from cli_anything.gohighlevel.public.errors import ContractViolation  # noqa: E402
from cli_anything.gohighlevel.public.readback import ReadbackSpec  # noqa: E402
from cli_anything.gohighlevel.public.result import Status  # noqa: E402

# ---------------------------------------------------------------------------
# synthetic fixture rows (explicitly NOT the WF00 registry)
# ---------------------------------------------------------------------------

COURSE_ROWS = registry(
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
        api.OP_CATEGORY_CREATE,
        method="POST",
        path_template="/courses/products/{productId}/categories",
        tenant_binding="query.locationId",
        write=True,
    ),
    row(
        api.OP_LESSON_CREATE,
        method="POST",
        path_template="/courses/products/{productId}/lessons",
        tenant_binding="query.locationId",
        write=True,
    ),
    row(
        api.OP_IMPORT_SUBMIT,
        method="POST",
        path_template="/courses/courses-exporter/public/import",
        tenant_binding="body.locationId",
        write=True,
    ),
    row(
        api.OP_ENROLLMENT_CREATE,
        method="POST",
        path_template="/courses/enrollments",
        tenant_binding="body.locationId",
        write=True,
    ),
    row(
        api.OP_PRODUCT_ENROLLMENTS_LIST,
        method="GET",
        path_template="/courses/enrollments",
        tenant_binding="query.locationId",
    ),
    row(
        api.OP_OFFER_CREATE,
        method="POST",
        path_template="/courses/products/{productId}/offers",
        tenant_binding="query.locationId",
        write=True,
    ),
    row(
        api.OP_OFFER_REVOKE,
        method="DELETE",
        path_template="/courses/products/{productId}/offers/{offerId}",
        tenant_binding="query.locationId",
        write=True,
        approval_required=True,
    ),
    row(
        api.OP_QUIZ_CREATE,
        method="POST",
        path_template="/courses/products/{productId}/lessons/{lessonId}/quiz",
        tenant_binding="query.locationId",
        write=True,
    ),
    row(
        api.OP_QUIZ_QUESTIONS_UPSERT,
        method="PUT",
        path_template="/courses/products/{productId}/quizzes/{quizId}/questions",
        tenant_binding="query.locationId",
        write=True,
    ),
)

PRODUCT = "course_product_synthetic_0001"
CATEGORY = "course_category_synthetic_0001"
LESSON = "course_lesson_synthetic_0001"
QUIZ = "course_quiz_synthetic_0001"
OFFER = "course_offer_synthetic_0001"


def readback_for(product_id: str = PRODUCT) -> ReadbackSpec:
    return api.course_readback(product_id, expect={"id": product_id})


def make_course_adapter(responses: list) -> tuple[object, FakeTransport]:
    transport = FakeTransport(responses)
    adapter = make_adapter(
        transport,
        COURSE_ROWS,
        gate=enabled_gate(list(COURSE_ROWS.values())),
    )
    return adapter, transport


def created_response() -> object:
    return resp(201, b'{"id":"course_product_synthetic_0001"}', {})


def readback_response(product_id: str = PRODUCT) -> object:
    return resp(200, ('{"id":"' + product_id + '"}').encode("utf-8"), {})


# ---------------------------------------------------------------------------
# A08 -- DTO separation, no invented fields
# ---------------------------------------------------------------------------


class CourseDtoTest(unittest.TestCase):
    def test_create_course_body_has_only_documented_fields(self) -> None:
        body = api.create_course_body(
            title="Launch 101",
            description="Approved description",
            poster_image="https://approved.example/cover.png",
            customizations={"theme": "sand"},
        )
        self.assertEqual(
            set(body),
            {"title", "description", "posterImage", "customizations"},
        )
        for forbidden in (
            "locationId",
            "userId",
            "id",
            "originId",
            "source",
            "processing",
            "status",
        ):
            self.assertNotIn(forbidden, body)

    def test_create_course_requires_title_and_refuses_status(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            api.create_course_body(title="  ")
        self.assertEqual(caught.exception.rule, "course_field_invalid")

    def test_category_uses_lowercase_metadata_and_parent_category(self) -> None:
        body = api.create_category_body(
            title="Welcome",
            visibility="draft",
            parent_category_id=CATEGORY,
            metadata={"icon": "star"},
            sequence_no=1,
        )
        self.assertEqual(body["metadata"], {"icon": "star"})
        self.assertEqual(body["parentCategory"], CATEGORY)
        self.assertNotIn("metaData", body)
        self.assertNotIn("categoryId", body)

    def test_lesson_uses_capital_metadata_and_body_category_id(self) -> None:
        body = api.create_lesson_body(
            title="Introduction",
            category_id=CATEGORY,
            description="Approved introduction text",
            visibility="draft",
            sequence_no=1,
            meta_data={"duration": 600},
        )
        self.assertEqual(body["metaData"], {"duration": 600})
        self.assertEqual(body["categoryId"], CATEGORY)
        self.assertNotIn("metadata", body)
        self.assertNotIn("parentCategory", body)

    def test_content_type_requires_native_content_id_and_rejects_url(self) -> None:
        with self.assertRaises(ContractViolation) as caught:
            api.create_lesson_body(
                title="L", category_id=CATEGORY, content_type="video"
            )
        self.assertEqual(caught.exception.rule, "lesson_content_pair_incomplete")

        with self.assertRaises(ContractViolation) as caught:
            api.create_lesson_body(
                title="L",
                category_id=CATEGORY,
                content_type="video",
                content_id="https://cdn.example/video.mp4",
            )
        self.assertEqual(caught.exception.rule, "content_id_is_not_a_url")

        body = api.create_lesson_body(
            title="L",
            category_id=CATEGORY,
            content_type="video",
            content_id="native_content_0001",
        )
        self.assertEqual(body["contentId"], "native_content_0001")

    def test_lesson_serializer_exposes_no_invented_media_or_status_field(self) -> None:
        import inspect

        parameters = set(inspect.signature(api.create_lesson_body).parameters)
        self.assertEqual(
            parameters,
            {
                "title",
                "category_id",
                "description",
                "visibility",
                "sequence_no",
                "meta_data",
                "content_type",
                "content_id",
            },
        )
        for forbidden in ("videoUrl", "mediaUrl", "attachments", "status"):
            self.assertNotIn(forbidden, parameters)

    def test_import_uses_identity_envelope_and_verbatim_hierarchy(self) -> None:
        body = api.build_import_body(
            location_id=SYNTHETIC_TENANT,
            user_id="user_synthetic_0001",
            hierarchy={"courses": [{"title": "Launch 101"}]},
        )
        self.assertEqual(body["locationId"], SYNTHETIC_TENANT)
        self.assertEqual(body["userId"], "user_synthetic_0001")
        self.assertEqual(body["courses"], [{"title": "Launch 101"}])

        with self.assertRaises(ContractViolation) as caught:
            api.build_import_body(
                location_id=SYNTHETIC_TENANT, hierarchy={}
            )
        self.assertEqual(caught.exception.rule, "import_hierarchy_required")


# ---------------------------------------------------------------------------
# A08 + IG-COURSE-01 -- typed calls through the one adapter
# ---------------------------------------------------------------------------


class CourseCallTest(unittest.TestCase):
    def test_create_course_sends_body_without_location_and_query_with_it(self) -> None:
        adapter, transport = make_course_adapter(
            [created_response(), readback_response()]
        )
        result = api.create_course(
            adapter,
            tenant=fake_tenant(),
            title="Launch 101",
            description="Approved description",
            idempotency_key="gxo_courses-products-create-0123456789abcdef0123456789abcdef",
            readback=readback_for(),
        )
        self.assertIs(result.status, Status.ok)
        create_request = transport.requests[0]
        self.assertEqual(create_request["method"], "POST")
        self.assertEqual(create_request["url"], "/courses/products")
        self.assertEqual(
            create_request["body"],
            {"title": "Launch 101", "description": "Approved description"},
        )
        self.assertNotIn("locationId", create_request["body"])
        self.assertEqual(create_request["query"], {"locationId": SYNTHETIC_TENANT})

    def test_create_course_without_readback_is_refused_before_transport(self) -> None:
        adapter, transport = make_course_adapter([])
        with self.assertRaises(ContractViolation) as caught:
            api.create_course(
                adapter,
                tenant=fake_tenant(),
                title="Launch 101",
                idempotency_key="gxo_courses-products-create-0123456789abcdef0123456789abcdef",
            )
        self.assertEqual(caught.exception.rule, "readback_required")
        self.assertEqual(transport.call_count, 0)

    def test_category_and_lesson_bodies_keep_separate_vocabularies(self) -> None:
        adapter, transport = make_course_adapter(
            [resp(201, b'{"id":"cat"}'), readback_response(),
             resp(201, b'{"id":"les"}'), readback_response()]
        )
        api.create_category(
            adapter,
            tenant=fake_tenant(),
            product_id=PRODUCT,
            title="Welcome",
            visibility="category_visibility_literal",
            metadata={"icon": "star"},
            sequence_no=1,
            idempotency_key="gxo_courses-categories-create-0123456789abcdef0123456789abcdef",
            readback=readback_for(),
        )
        api.create_lesson(
            adapter,
            tenant=fake_tenant(),
            product_id=PRODUCT,
            title="Introduction",
            category_id=CATEGORY,
            visibility="lesson_visibility_literal",
            meta_data={"duration": 600},
            idempotency_key="gxo_courses-lessons-create-0123456789abcdef0123456789abcdef",
            readback=readback_for(),
        )
        category_request, lesson_request = transport.requests[0], transport.requests[2]
        self.assertEqual(
            category_request["url"], "/courses/products/" + PRODUCT + "/categories"
        )
        self.assertEqual(category_request["body"]["metadata"], {"icon": "star"})
        self.assertNotIn("metaData", category_request["body"])
        self.assertEqual(
            lesson_request["url"], "/courses/products/" + PRODUCT + "/lessons"
        )
        self.assertEqual(lesson_request["body"]["metaData"], {"duration": 600})
        self.assertEqual(
            lesson_request["body"]["visibility"], "lesson_visibility_literal"
        )

    def test_quiz_calls_use_documented_paths(self) -> None:
        adapter, transport = make_course_adapter(
            [resp(201, b'{"id":"quiz"}'), readback_response(),
             resp(200, b'{"id":"quiz"}'), readback_response()]
        )
        api.create_lesson_quiz(
            adapter,
            tenant=fake_tenant(),
            product_id=PRODUCT,
            lesson_id=LESSON,
            quiz_body={"title": "Check your learning"},
            idempotency_key="gxo_courses-quizzes-create-0123456789abcdef0123456789abcdef",
            readback=readback_for(),
        )
        api.upsert_quiz_questions(
            adapter,
            tenant=fake_tenant(),
            product_id=PRODUCT,
            quiz_id=QUIZ,
            questions_body={"questions": [{"text": "Q1"}]},
            idempotency_key="gxo_courses-quizzes-questions-upsert-0123456789abcdef0123456789abcdef",
            readback=readback_for(),
        )
        self.assertEqual(
            transport.requests[0]["url"],
            "/courses/products/" + PRODUCT + "/lessons/" + LESSON + "/quiz",
        )
        self.assertEqual(transport.requests[2]["method"], "PUT")
        self.assertEqual(
            transport.requests[2]["url"],
            "/courses/products/" + PRODUCT + "/quizzes/" + QUIZ + "/questions",
        )

    def test_unknown_registry_row_fails_loudly_not_silently(self) -> None:
        rows = {k: v for k, v in COURSE_ROWS.items() if k != api.OP_CATEGORY_CREATE}
        transport = FakeTransport([resp(201, b'{"id":"cat"}'), readback_response()])
        adapter = make_adapter(
            transport, rows, gate=enabled_gate(list(rows.values()))
        )
        with self.assertRaises(ContractViolation) as caught:
            api.create_category(
                adapter,
                tenant=fake_tenant(),
                product_id=PRODUCT,
                title="Welcome",
                idempotency_key="gxo_courses-categories-create-0123456789abcdef0123456789abcdef",
                readback=readback_for(),
            )
        self.assertEqual(caught.exception.rule, "unknown_operation_id")
        self.assertEqual(transport.call_count, 0)


# ---------------------------------------------------------------------------
# A11 -- import lifecycle
# ---------------------------------------------------------------------------


class CourseImportLifecycleTest(unittest.TestCase):
    def test_processing_is_not_content_verified(self) -> None:
        lifecycle = api.CourseImportLifecycle()
        lifecycle.submit("sha256:synthetic-submission")
        lifecycle.mark_processing("processing_synthetic_0001")
        self.assertFalse(lifecycle.is_content_verified)
        with self.assertRaises(ContractViolation) as caught:
            lifecycle.mark_content_verified()
        self.assertEqual(
            caught.exception.rule, "course_import_transition_invalid"
        )
        lifecycle.reconcile()
        lifecycle.mark_content_verified()
        self.assertTrue(lifecycle.is_content_verified)

    def test_repeat_submission_refused_before_reconciliation(self) -> None:
        lifecycle = api.CourseImportLifecycle()
        lifecycle.submit("sha256:synthetic-submission")
        self.assertFalse(lifecycle.can_submit)
        with self.assertRaises(ContractViolation) as caught:
            lifecycle.submit("sha256:another-submission")
        self.assertEqual(
            caught.exception.rule, "course_import_resubmission_refused"
        )

    def test_unknown_outcome_blocks_resubmission_until_reconciled(self) -> None:
        lifecycle = api.CourseImportLifecycle()
        lifecycle.submit("sha256:synthetic-submission")
        lifecycle.mark_unknown_outcome("response lost")
        with self.assertRaises(ContractViolation):
            lifecycle.submit("sha256:another-submission")
        lifecycle.reconcile()
        self.assertEqual(lifecycle.state, api.IMPORT_RECONCILED)


# ---------------------------------------------------------------------------
# IG-COURSE-04 -- no commerce/course identity confusion
# ---------------------------------------------------------------------------


class CourseIdentityTest(unittest.TestCase):
    def test_all_operation_ids_live_in_the_courses_family(self) -> None:
        for operation_id in api.COURSE_OPERATION_SPECS:
            self.assertTrue(
                operation_id.startswith("courses."),
                operation_id,
            )
            self.assertFalse(operation_id.startswith("products."), operation_id)

    def test_foreign_location_is_refused_before_transport(self) -> None:
        adapter, transport = make_course_adapter([])
        result = api.create_course(
            adapter,
            tenant=fake_tenant("loc_synthetic_other"),
            title="Launch 101",
            idempotency_key="gxo_courses-products-create-0123456789abcdef0123456789abcdef",
            readback=api.course_readback(PRODUCT, expect={"id": PRODUCT}),
        )
        self.assertIs(result.status, Status.denied)
        self.assertEqual((result.error or {}).get("rule"), "tenant_mismatch")
        self.assertEqual(transport.call_count, 0)


# ---------------------------------------------------------------------------
# IG-COURSE-07 -- enrollment idempotency, no payment claim
# ---------------------------------------------------------------------------


class EnrollmentTest(unittest.TestCase):
    def test_enrollment_body_uses_exported_assumption(self) -> None:
        body = api.create_enrollment_body(
            contact_id=SYNTHETIC_CONTACT, offer_id=OFFER
        )
        self.assertEqual(body, {"contactId": SYNTHETIC_CONTACT, "offerId": OFFER})

    def test_enrollment_outcomes_never_claim_payment(self) -> None:
        self.assertFalse(api.ENROLLMENT_IS_PAYMENT_PROOF)
        from cli_anything.gohighlevel.public.result import OperationResult

        def result_with(status: Status) -> OperationResult:
            return OperationResult(
                status=status,
                operation_id=api.OP_ENROLLMENT_CREATE,
                receipt_id="gxo_res_synthetic",
                request_fingerprint="0" * 64,
                http_status=None,
                response_fingerprint=None,
                tenant=SYNTHETIC_TENANT,
                attempt=1,
                version_header=None,
                readback=None,
                adapter_version="test",
                transport="http",
                doc_url=None,
                evidence={key: None for key in (
                    "operation_id", "request_fingerprint", "http_status",
                    "response_fingerprint", "tenant", "attempt", "readback",
                    "receipt_id", "version_header", "timeout_s",
                    "adapter_version", "transport", "auth_kind", "auth_source",
                    "doc_url", "doc_fetch_date", "request_bytes", "started_at",
                    "finished_at",
                )},
                error=None,
            )

        for status, expected in (
            (Status.ok, "enrollment_created"),
            (Status.conflict, "verify_existing_enrollment"),
            (Status.validation_error, "verify_existing_enrollment"),
            (Status.unknown_outcome, "unknown_outcome"),
        ):
            outcome = api.enrollment_outcome(result_with(status))
            self.assertEqual(outcome, expected)
            self.assertNotIn("paid", outcome)
            self.assertNotIn("payment", outcome)

    def test_enrollment_query_is_cursor_paginated(self) -> None:
        adapter, transport = make_course_adapter([resp(200, b'{"total":0}')])
        result = api.list_product_enrollments(
            adapter,
            tenant=fake_tenant(),
            limit=2,
            cursor="cursor_synthetic_0001",
        )
        self.assertIs(result.status, Status.ok)
        self.assertEqual(
            transport.last["query"],
            {
                "locationId": SYNTHETIC_TENANT,
                "limit": 2,
                "cursor": "cursor_synthetic_0001",
            },
        )
        self.assertEqual(
            api.advance_cursor({"limit": 2}, "cursor_synthetic_0002"),
            {"limit": 2, "cursor": "cursor_synthetic_0002"},
        )


# ---------------------------------------------------------------------------
# IG-COURSE-08 -- revocation impact before removal
# ---------------------------------------------------------------------------


class OfferRevocationTest(unittest.TestCase):
    def test_affected_product_set_is_computed_and_deduplicated(self) -> None:
        impact = api.revocation_impact(
            offer_id=OFFER, included_product_ids=["p2", "p1", "p2", " "]
        )
        self.assertEqual(impact["affected_product_ids"], ["p1", "p2"])
        self.assertEqual(impact["affected_count"], 2)
        self.assertTrue(impact["requires_confirmation"])

    def test_revoke_returns_impact_then_applies_approved_call(self) -> None:
        adapter, transport = make_course_adapter(
            [resp(200, b'{"revoked":true}'), readback_response()]
        )
        impact, result = api.revoke_offer(
            adapter,
            tenant=fake_tenant(),
            product_id=PRODUCT,
            offer_id=OFFER,
            included_product_ids=["p1", "p2"],
            idempotency_key="gxo_courses-offers-revoke-0123456789abcdef0123456789abcdef",
            approval=approval(),
            readback=readback_for(),
        )
        self.assertEqual(impact["affected_product_ids"], ["p1", "p2"])
        revoke_request = transport.requests[0]
        self.assertEqual(revoke_request["method"], "DELETE")
        self.assertTrue(
            revoke_request["url"].endswith("/offers/" + OFFER),
            revoke_request["url"],
        )
        self.assertIs(result.status, Status.ok)


# ---------------------------------------------------------------------------
# interface table -- unresolved stays unresolved
# ---------------------------------------------------------------------------


class CourseSpecTableTest(unittest.TestCase):
    def test_every_none_path_names_the_missing_evidence(self) -> None:
        for spec in api.COURSE_OPERATION_SPECS.values():
            if spec.path_template is None:
                self.assertEqual(spec.contract_state, api.UNRESOLVED)
                self.assertIn("path_template", spec.unresolved, spec.operation_id)

    def test_literal_paths_are_only_the_documented_ones(self) -> None:
        expected = {
            api.OP_COURSE_CREATE: "/courses/products",
            api.OP_IMPORT_SUBMIT: "/courses/courses-exporter/public/import",
            api.OP_ENROLLMENT_CREATE: "/courses/enrollments",
            api.OP_QUIZ_CREATE: (
                "/courses/products/{productId}/lessons/{lessonId}/quiz"
            ),
            api.OP_QUIZ_QUESTIONS_UPSERT: (
                "/courses/products/{productId}/quizzes/{quizId}/questions"
            ),
        }
        for operation_id, path in expected.items():
            self.assertEqual(
                api.COURSE_OPERATION_SPECS[operation_id].path_template, path
            )
        for operation_id, spec in api.COURSE_OPERATION_SPECS.items():
            if spec.path_template is not None:
                self.assertIn(operation_id, expected)
                self.assertTrue(spec.path_template.startswith("/courses/"))

    def test_unresolved_operations_are_exported_for_convergence(self) -> None:
        entries = dict(api.unresolved_operations())
        self.assertIn(api.OP_CATEGORY_CREATE, entries)
        self.assertIn("path_template", entries[api.OP_CATEGORY_CREATE])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
