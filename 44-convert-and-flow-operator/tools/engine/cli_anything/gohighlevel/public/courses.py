"""Typed Courses API adapter (WF06 / GHL-006).

Contract sources: Document 1 section 8 (8.1-8.9) and 21.4-21.5, Document 2
WF06.  Every call travels through :class:`PublicGhlAdapter`, so this module
owns NO transport, NO auth, NO capability gate and NO operation registry of its
own.  ``public/operations.py`` remains the one dispatch authority; the rows for
the operations named here are owned by WF00 (change request WF06-CR-01).

DTO separation that this module enforces before transport:

* Create Course takes ``title`` (required); ``description``, ``posterImage``
  and ``customizations`` are optional.  ``locationId``/``userId``/``id``/
  ``originId``/``source``/``processing`` never enter the body; location is a
  query parameter injected by the operation row's tenant binding.
* Category settings use ``metadata`` (lower-case d) and ``parentCategory``.
* Lesson settings use ``metaData`` (capital D), ``categoryId`` in the body and
  ``contentType`` only together with a real native ``contentId``.  A CDN URL
  is not a content ID.
* No course ``status`` property is ever synthesised; release is explicit
  per-object visibility plus verification.
* Import has its own serializer and its own lifecycle; a processing response is
  never a completed course.

Fields whose exact current vendor schema Document 1 does not settle are
marked ``UNRESOLVED`` here and stay unresolved: no literal is guessed.  A
``None`` path template means the row cannot travel over HTTP until WF00 records
the verified path; the adapter then refuses loudly with
``unknown_operation_id`` instead of the module inventing a URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .adapter import ApprovalRef, PublicGhlAdapter
from .auth import TenantBinding
from .errors import ContractViolation
from .readback import ReadbackSpec
from .result import OperationResult, Status

# ---------------------------------------------------------------------------
# operation ids and frozen interface table (WF06-CP01)
# ---------------------------------------------------------------------------

OP_COURSE_CREATE = "courses.products.create"
OP_COURSE_GET = "courses.products.get"
OP_CATEGORY_CREATE = "courses.categories.create"
OP_LESSON_CREATE = "courses.lessons.create"
OP_IMPORT_SUBMIT = "courses.imports.submit"
OP_ENROLLMENT_CREATE = "courses.enrollments.create"
OP_PRODUCT_ENROLLMENTS_LIST = "courses.product_enrollments.list"
OP_OFFER_CREATE = "courses.offers.create"
OP_OFFER_REVOKE = "courses.offers.revoke"
OP_QUIZ_CREATE = "courses.quizzes.create"
OP_QUIZ_QUESTIONS_UPSERT = "courses.quizzes.questions.upsert"

DOCUMENTED = "documented"
UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CourseOperationSpec:
    """Frozen interface row for one course operation.

    ``path_template is None`` marks a path Document 1 does not settle.  The
    spec never dispatches; the adapter's registry row does.  ``unresolved``
    names exactly what is still owed so a consumer fails loudly rather than
    inheriting a guess.
    """

    operation_id: str
    method: str
    path_template: str | None
    path_params: tuple[str, ...]
    write: bool
    approval: bool
    readback_operation: str | None = None
    required_query: tuple[str, ...] = ()
    contract_state: str = DOCUMENTED
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.contract_state not in (DOCUMENTED, UNRESOLVED):
            raise ContractViolation(
                "course_spec_state_invalid", operation_id=self.operation_id
            )
        if self.contract_state == DOCUMENTED and self.path_template is None:
            raise ContractViolation(
                "course_spec_path_missing", operation_id=self.operation_id
            )
        if self.contract_state == UNRESOLVED and not self.unresolved:
            raise ContractViolation(
                "course_spec_unresolved_reason_missing",
                operation_id=self.operation_id,
            )
        if self.readback_operation is not None and not self.write:
            raise ContractViolation(
                "course_spec_readback_on_read", operation_id=self.operation_id
            )


_SPECS: tuple[CourseOperationSpec, ...] = (
    # Document 1 s8.3: "Create Course requires title"; request excludes
    # locationId, userId, id, originId, source, processing; locationId is a
    # query.  The literal path is named in s8.3.
    CourseOperationSpec(
        operation_id=OP_COURSE_CREATE,
        method="POST",
        path_template="/courses/products",
        path_params=(),
        write=True,
        approval=False,
        readback_operation=OP_COURSE_GET,
        unresolved=("version_literal",),
        contract_state=UNRESOLVED,
    ),
    # Read-back read for the course shell.  Document 1 names "the normal Course
    # CRUD endpoints" without publishing the GET path here; WF00 records it.
    CourseOperationSpec(
        operation_id=OP_COURSE_GET,
        method="GET",
        path_template=None,
        path_params=("productId",),
        write=False,
        approval=False,
        contract_state=UNRESOLVED,
        unresolved=("path_template", "version_literal"),
    ),
    # Document 1 s8.3 names Create Category and its DTO fields but not the
    # path.  No URL is invented here.
    CourseOperationSpec(
        operation_id=OP_CATEGORY_CREATE,
        method="POST",
        path_template=None,
        path_params=("productId",),
        write=True,
        approval=False,
        contract_state=UNRESOLVED,
        unresolved=("path_template", "version_literal"),
    ),
    # Document 1 s8.3 names Create Lesson (title + categoryId) and its DTO
    # fields but not the path.
    CourseOperationSpec(
        operation_id=OP_LESSON_CREATE,
        method="POST",
        path_template=None,
        path_params=("productId",),
        write=True,
        approval=False,
        contract_state=UNRESOLVED,
        unresolved=("path_template", "version_literal"),
    ),
    # Document 1 s8.6 names this exact path and its dedicated body contract.
    CourseOperationSpec(
        operation_id=OP_IMPORT_SUBMIT,
        method="POST",
        path_template="/courses/courses-exporter/public/import",
        path_params=(),
        write=True,
        approval=False,
        unresolved=("version_literal", "exact_hierarchy_keys"),
        contract_state=UNRESOLVED,
    ),
    # Document 1 s8.7 names POST /courses/enrollments (contact + offer).
    CourseOperationSpec(
        operation_id=OP_ENROLLMENT_CREATE,
        method="POST",
        path_template="/courses/enrollments",
        path_params=(),
        write=True,
        approval=False,
        unresolved=("version_literal", "exact_contact_offer_key_names"),
        contract_state=UNRESOLVED,
    ),
    # Document 1 s8.7 names the product-enrollments read with cursor
    # pagination but not its path or cursor parameter names.
    CourseOperationSpec(
        operation_id=OP_PRODUCT_ENROLLMENTS_LIST,
        method="GET",
        path_template=None,
        path_params=(),
        write=False,
        approval=False,
        contract_state=UNRESOLVED,
        unresolved=("path_template", "version_literal", "cursor_parameter_names"),
    ),
    # Document 1 s8.7 names the course-offer APIs but not their paths.
    CourseOperationSpec(
        operation_id=OP_OFFER_CREATE,
        method="POST",
        path_template=None,
        path_params=("productId",),
        write=True,
        approval=False,
        contract_state=UNRESOLVED,
        unresolved=("path_template", "version_literal", "offer_body_schema"),
    ),
    CourseOperationSpec(
        operation_id=OP_OFFER_REVOKE,
        method="DELETE",
        path_template=None,
        path_params=("productId", "offerId"),
        write=True,
        approval=True,
        contract_state=UNRESOLVED,
        unresolved=("path_template", "version_literal", "method_and_body"),
    ),
    # Document 1 s21.4 names the exact quiz-create path.
    CourseOperationSpec(
        operation_id=OP_QUIZ_CREATE,
        method="POST",
        path_template="/courses/products/{productId}/lessons/{lessonId}/quiz",
        path_params=("productId", "lessonId"),
        write=True,
        approval=False,
        unresolved=("version_literal", "quiz_body_schema"),
        contract_state=UNRESOLVED,
    ),
    # Document 1 s21.4 names the exact question-upsert path and method.
    CourseOperationSpec(
        operation_id=OP_QUIZ_QUESTIONS_UPSERT,
        method="PUT",
        path_template="/courses/products/{productId}/quizzes/{quizId}/questions",
        path_params=("productId", "quizId"),
        write=True,
        approval=False,
        unresolved=("version_literal", "questions_body_schema"),
        contract_state=UNRESOLVED,
    ),
)

COURSE_OPERATION_SPECS: Mapping[str, CourseOperationSpec] = {
    spec.operation_id: spec for spec in _SPECS
}


def spec_for(operation_id: str) -> CourseOperationSpec:
    spec = COURSE_OPERATION_SPECS.get(str(operation_id))
    if spec is None:
        raise ContractViolation(
            "course_operation_unknown", operation_id=str(operation_id)
        )
    return spec


def unresolved_operations() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Every operation still owing evidence, with exactly what is owed."""

    return tuple(
        (spec.operation_id, spec.unresolved)
        for spec in _SPECS
        if spec.contract_state == UNRESOLVED
    )


# ---------------------------------------------------------------------------
# DTO serializers -- exact fields, nothing invented
# ---------------------------------------------------------------------------

_COURSE_BODY_FIELDS = ("title", "description", "posterImage", "customizations")
_COURSE_FORBIDDEN_KEYS = (
    "locationId",
    "userId",
    "id",
    "originId",
    "source",
    "processing",
    "status",
)
_CATEGORY_BODY_FIELDS = (
    "title",
    "visibility",
    "parentCategory",
    "metadata",
    "sequenceNo",
)
_LESSON_BODY_FIELDS = (
    "title",
    "categoryId",
    "description",
    "visibility",
    "sequenceNo",
    "metaData",
    "contentType",
    "contentId",
)
_LESSON_FORBIDDEN_KEYS = ("videoUrl", "mediaUrl", "attachments", "status")

#: Assumed key names that Document 1 describes in prose only.  They are
#: exported so the assertion is auditable and a contract change is a visible
#: test failure, never a silent drift.
ASSUMED_DTO_FIELDS: Mapping[str, str] = {
    "enrollment.contact": "contactId",
    "enrollment.offer": "offerId",
    "pagination.limit": "limit",
    "pagination.cursor": "cursor",
}


def _text(value: Any, *, field_name: str, operation_id: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractViolation(
            "course_field_invalid",
            operation_id=operation_id,
            detail={"field": field_name},
        )
    return value.strip()


def _refuse_keys(
    body: Mapping[str, Any],
    *,
    allowed: Sequence[str],
    operation_id: str,
) -> None:
    extra = sorted(str(key) for key in body if str(key) not in allowed)
    if extra:
        raise ContractViolation(
            "course_dto_unknown_field",
            operation_id=operation_id,
            detail={"fields": extra},
        )


def _refuse_identity_keys(
    body: Mapping[str, Any], *, operation_id: str, forbidden: Sequence[str]
) -> None:
    present = sorted(str(key) for key in body if str(key) in forbidden)
    if present:
        raise ContractViolation(
            "course_dto_forbidden_field",
            operation_id=operation_id,
            detail={"fields": present},
        )


def create_course_body(
    *,
    title: str,
    description: str | None = None,
    poster_image: str | None = None,
    customizations: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create Course DTO (Document 1 s8.3).  No course status is invented."""

    body: dict[str, Any] = {
        "title": _text(title, field_name="title", operation_id=OP_COURSE_CREATE)
    }
    if description is not None:
        body["description"] = _text(
            description, field_name="description", operation_id=OP_COURSE_CREATE
        )
    if poster_image is not None:
        body["posterImage"] = _text(
            poster_image, field_name="posterImage", operation_id=OP_COURSE_CREATE
        )
    if customizations is not None:
        if not isinstance(customizations, Mapping):
            raise ContractViolation(
                "course_field_invalid",
                operation_id=OP_COURSE_CREATE,
                detail={"field": "customizations"},
            )
        body["customizations"] = dict(customizations)
    _refuse_keys(
        body, allowed=_COURSE_BODY_FIELDS, operation_id=OP_COURSE_CREATE
    )
    _refuse_identity_keys(
        body,
        operation_id=OP_COURSE_CREATE,
        forbidden=_COURSE_FORBIDDEN_KEYS,
    )
    return {key: value for key, value in body.items() if value is not None}


def create_category_body(
    *,
    title: str,
    visibility: str | None = None,
    parent_category_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    sequence_no: int | None = None,
) -> dict[str, Any]:
    """Create Category DTO.  Category settings are ``metadata`` (lower-case d).

    The category visibility vocabulary differs from the lesson vocabulary; the
    exact sets are documented by WF00's row evidence.  This serializer accepts
    any non-empty string and never translates one vocabulary into the other.
    """

    body: dict[str, Any] = {
        "title": _text(title, field_name="title", operation_id=OP_CATEGORY_CREATE)
    }
    if visibility is not None:
        body["visibility"] = _text(
            visibility, field_name="visibility", operation_id=OP_CATEGORY_CREATE
        )
    if parent_category_id is not None:
        body["parentCategory"] = _text(
            parent_category_id,
            field_name="parentCategory",
            operation_id=OP_CATEGORY_CREATE,
        )
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise ContractViolation(
                "course_field_invalid",
                operation_id=OP_CATEGORY_CREATE,
                detail={"field": "metadata"},
            )
        body["metadata"] = dict(metadata)
    if sequence_no is not None:
        if not isinstance(sequence_no, int) or isinstance(sequence_no, bool):
            raise ContractViolation(
                "course_field_invalid",
                operation_id=OP_CATEGORY_CREATE,
                detail={"field": "sequenceNo"},
            )
        body["sequenceNo"] = sequence_no
    if "metaData" in body:  # defensive: the key can only arrive via metadata
        raise ContractViolation(
            "category_metadata_field_lowercase_required",
            operation_id=OP_CATEGORY_CREATE,
        )
    _refuse_keys(
        body, allowed=_CATEGORY_BODY_FIELDS, operation_id=OP_CATEGORY_CREATE
    )
    _refuse_identity_keys(
        body,
        operation_id=OP_CATEGORY_CREATE,
        forbidden=("locationId", "userId", "productId", "originId", "source", "id"),
    )
    return body


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") or "://" in value


def create_lesson_body(
    *,
    title: str,
    category_id: str,
    description: str | None = None,
    visibility: str | None = None,
    sequence_no: int | None = None,
    meta_data: Mapping[str, Any] | None = None,
    content_type: str | None = None,
    content_id: str | None = None,
) -> dict[str, Any]:
    """Create Lesson DTO.  Lesson settings are ``metaData`` (capital D).

    ``contentType`` travels only with a real native ``contentId`` of the same
    location; a CDN URL is never accepted as a content ID.
    """

    body: dict[str, Any] = {
        "title": _text(title, field_name="title", operation_id=OP_LESSON_CREATE),
        "categoryId": _text(
            category_id, field_name="categoryId", operation_id=OP_LESSON_CREATE
        ),
    }
    if description is not None:
        body["description"] = _text(
            description, field_name="description", operation_id=OP_LESSON_CREATE
        )
    if visibility is not None:
        body["visibility"] = _text(
            visibility, field_name="visibility", operation_id=OP_LESSON_CREATE
        )
    if sequence_no is not None:
        if not isinstance(sequence_no, int) or isinstance(sequence_no, bool):
            raise ContractViolation(
                "course_field_invalid",
                operation_id=OP_LESSON_CREATE,
                detail={"field": "sequenceNo"},
            )
        body["sequenceNo"] = sequence_no
    if meta_data is not None:
        if not isinstance(meta_data, Mapping):
            raise ContractViolation(
                "course_field_invalid",
                operation_id=OP_LESSON_CREATE,
                detail={"field": "metaData"},
            )
        body["metaData"] = dict(meta_data)
    if (content_type is None) != (content_id is None):
        raise ContractViolation(
            "lesson_content_pair_incomplete",
            operation_id=OP_LESSON_CREATE,
            detail={"contentType": content_type is not None, "contentId": content_id is not None},
        )
    if content_id is not None:
        text_id = _text(
            content_id, field_name="contentId", operation_id=OP_LESSON_CREATE
        )
        if _is_url(text_id):
            raise ContractViolation(
                "content_id_is_not_a_url",
                operation_id=OP_LESSON_CREATE,
                detail={"hint": "a CDN URL is not a native content ID"},
            )
        body["contentType"] = _text(
            content_type or "", field_name="contentType", operation_id=OP_LESSON_CREATE
        )
        body["contentId"] = text_id
    _refuse_keys(
        body, allowed=_LESSON_BODY_FIELDS, operation_id=OP_LESSON_CREATE
    )
    _refuse_identity_keys(
        body,
        operation_id=OP_LESSON_CREATE,
        forbidden=_LESSON_FORBIDDEN_KEYS,
    )
    if "metadata" in body:  # defensive
        raise ContractViolation(
            "lesson_metadata_field_capital_d_required",
            operation_id=OP_LESSON_CREATE,
        )
    return body


def build_import_body(
    *,
    location_id: str,
    hierarchy: Mapping[str, Any],
    user_id: str | None = None,
) -> dict[str, Any]:
    """Dedicated import serializer (Document 1 s8.6).

    Import has a different body contract from ordinary CRUD and may carry
    location/user/course hierarchy fields the create DTO refuses.  The exact
    hierarchy key shape is not settled by Document 1, so the caller supplies
    the approved hierarchy verbatim; this function only fixes the identity
    envelope and never invents hierarchy keys.
    """

    body: dict[str, Any] = {
        "locationId": _text(
            location_id, field_name="locationId", operation_id=OP_IMPORT_SUBMIT
        )
    }
    if user_id is not None:
        body["userId"] = _text(
            user_id, field_name="userId", operation_id=OP_IMPORT_SUBMIT
        )
    if not isinstance(hierarchy, Mapping) or not hierarchy:
        raise ContractViolation(
            "import_hierarchy_required", operation_id=OP_IMPORT_SUBMIT
        )
    overlap = sorted(set(body) & set(hierarchy))
    if overlap:
        raise ContractViolation(
            "import_hierarchy_conflict",
            operation_id=OP_IMPORT_SUBMIT,
            detail={"fields": overlap},
        )
    body.update(dict(hierarchy))
    return body


# ---------------------------------------------------------------------------
# import lifecycle -- processing is not completion (A11)
# ---------------------------------------------------------------------------

IMPORT_PLANNED = "planned"
IMPORT_SUBMITTED = "submitted"
IMPORT_PROCESSING = "processing"
IMPORT_RECONCILED = "reconciled"
IMPORT_CONTENT_VERIFIED = "content_verified"
IMPORT_FAILED = "failed"
IMPORT_UNKNOWN_OUTCOME = "unknown_outcome"

IMPORT_STATES: tuple[str, ...] = (
    IMPORT_PLANNED,
    IMPORT_SUBMITTED,
    IMPORT_PROCESSING,
    IMPORT_RECONCILED,
    IMPORT_CONTENT_VERIFIED,
    IMPORT_FAILED,
    IMPORT_UNKNOWN_OUTCOME,
)

_IMPORT_TRANSITIONS: Mapping[str, frozenset[str]] = {
    IMPORT_PLANNED: frozenset({IMPORT_SUBMITTED}),
    IMPORT_SUBMITTED: frozenset(
        {IMPORT_PROCESSING, IMPORT_FAILED, IMPORT_UNKNOWN_OUTCOME}
    ),
    IMPORT_PROCESSING: frozenset(
        {IMPORT_RECONCILED, IMPORT_FAILED, IMPORT_UNKNOWN_OUTCOME}
    ),
    IMPORT_RECONCILED: frozenset({IMPORT_CONTENT_VERIFIED, IMPORT_FAILED}),
    IMPORT_CONTENT_VERIFIED: frozenset(),
    IMPORT_FAILED: frozenset(),
    IMPORT_UNKNOWN_OUTCOME: frozenset({IMPORT_RECONCILED, IMPORT_FAILED}),
}


@dataclass
class CourseImportLifecycle:
    """Local import state machine.

    ``planned -> submitted -> processing -> reconciled -> content_verified``
    with ``failed`` / ``unknown_outcome`` branches.  A repeat submission is
    refused until the prior submission has been reconciled; an
    ``unknown_outcome`` is never retried blindly.
    """

    submission_fingerprint: str | None = None
    state: str = IMPORT_PLANNED
    processing_ids: list[str] = field(default_factory=list)
    intended_hierarchy: Mapping[str, Any] | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.state not in IMPORT_STATES:
            raise ContractViolation(
                "course_import_state_invalid", detail={"state": str(self.state)}
            )
        if self.state != IMPORT_PLANNED and not self.submission_fingerprint:
            raise ContractViolation(
                "course_import_fingerprint_missing", detail={"state": self.state}
            )

    @property
    def can_submit(self) -> bool:
        return self.state == IMPORT_PLANNED and not self.submission_fingerprint

    @property
    def is_content_verified(self) -> bool:
        return self.state == IMPORT_CONTENT_VERIFIED

    def submit(self, fingerprint: str) -> "CourseImportLifecycle":
        if not self.can_submit:
            raise ContractViolation(
                "course_import_resubmission_refused",
                operation_id=OP_IMPORT_SUBMIT,
                detail={
                    "state": self.state,
                    "hint": "reconcile the prior submission before any repeat",
                },
            )
        text = _text(
            fingerprint, field_name="submissionFingerprint", operation_id=OP_IMPORT_SUBMIT
        )
        self._move(IMPORT_SUBMITTED)
        self.submission_fingerprint = text
        return self

    def mark_processing(self, processing_id: str) -> "CourseImportLifecycle":
        text = _text(
            processing_id, field_name="processingId", operation_id=OP_IMPORT_SUBMIT
        )
        self._move(IMPORT_PROCESSING)
        if text not in self.processing_ids:
            self.processing_ids.append(text)
        return self

    def reconcile(self) -> "CourseImportLifecycle":
        self._move(IMPORT_RECONCILED)
        return self

    def mark_content_verified(self) -> "CourseImportLifecycle":
        """The only completion state.  A processing 200 cannot reach it."""

        self._move(IMPORT_CONTENT_VERIFIED)
        return self

    def mark_failed(self, reason: str) -> "CourseImportLifecycle":
        text = _text(
            reason, field_name="failureReason", operation_id=OP_IMPORT_SUBMIT
        )
        self._move(IMPORT_FAILED)
        self.failure_reason = text
        return self

    def mark_unknown_outcome(self, reason: str) -> "CourseImportLifecycle":
        text = _text(
            reason, field_name="unknownReason", operation_id=OP_IMPORT_SUBMIT
        )
        self._move(IMPORT_UNKNOWN_OUTCOME)
        self.failure_reason = text
        return self

    def _move(self, target: str) -> None:
        allowed = _IMPORT_TRANSITIONS.get(self.state, frozenset())
        if target not in allowed:
            raise ContractViolation(
                "course_import_transition_invalid",
                operation_id=OP_IMPORT_SUBMIT,
                detail={"from": self.state, "to": target},
            )
        self.state = target

    def as_receipt(self) -> dict[str, Any]:
        return {
            "operation_id": OP_IMPORT_SUBMIT,
            "state": self.state,
            "submission_fingerprint": self.submission_fingerprint,
            "processing_ids": list(self.processing_ids),
            "content_verified": self.is_content_verified,
            "failure_reason": self.failure_reason,
        }


# ---------------------------------------------------------------------------
# typed calls -- the adapter remains the only dispatch authority
# ---------------------------------------------------------------------------


def _call(
    adapter: PublicGhlAdapter,
    spec: CourseOperationSpec,
    *,
    tenant: TenantBinding,
    path_params: Mapping[str, str] | None = None,
    query: Mapping[str, object] | None = None,
    body: Mapping[str, object] | None = None,
    idempotency_key: str | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    readback: ReadbackSpec | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    if not isinstance(adapter, PublicGhlAdapter):
        raise ContractViolation("adapter_required", operation_id=spec.operation_id)
    provided = dict(path_params or {})
    expected = set(spec.path_params)
    if set(provided) != expected:
        raise ContractViolation(
            "course_path_params_mismatch",
            operation_id=spec.operation_id,
            detail={
                "missing": sorted(expected - set(provided)),
                "extra": sorted(set(provided) - expected),
            },
        )
    return adapter.call(
        operation_id=spec.operation_id,
        tenant=tenant,
        path_params=provided,
        query=dict(query or {}),
        body=dict(body) if body is not None else None,
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def course_readback(
    product_id: str, *, expect: Mapping[str, Any]
) -> ReadbackSpec:
    """Read-back plan for a course write; an empty expectation is refused."""

    text = _text(product_id, field_name="productId", operation_id=OP_COURSE_GET)
    if not isinstance(expect, Mapping) or not expect:
        raise ContractViolation("readback_vacuous", operation_id=OP_COURSE_GET)
    return ReadbackSpec(
        operation_id=OP_COURSE_GET,
        target_params={"productId": text},
        expect=dict(expect),
    )


def create_course(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    title: str,
    description: str | None = None,
    poster_image: str | None = None,
    customizations: Mapping[str, Any] | None = None,
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    return _call(
        adapter,
        spec_for(OP_COURSE_CREATE),
        tenant=tenant,
        body=create_course_body(
            title=title,
            description=description,
            poster_image=poster_image,
            customizations=customizations,
        ),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def create_category(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    product_id: str,
    title: str,
    visibility: str | None = None,
    parent_category_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    sequence_no: int | None = None,
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    return _call(
        adapter,
        spec_for(OP_CATEGORY_CREATE),
        tenant=tenant,
        path_params={
            "productId": _text(
                product_id, field_name="productId", operation_id=OP_CATEGORY_CREATE
            )
        },
        body=create_category_body(
            title=title,
            visibility=visibility,
            parent_category_id=parent_category_id,
            metadata=metadata,
            sequence_no=sequence_no,
        ),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def create_lesson(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    product_id: str,
    title: str,
    category_id: str,
    description: str | None = None,
    visibility: str | None = None,
    sequence_no: int | None = None,
    meta_data: Mapping[str, Any] | None = None,
    content_type: str | None = None,
    content_id: str | None = None,
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    return _call(
        adapter,
        spec_for(OP_LESSON_CREATE),
        tenant=tenant,
        path_params={
            "productId": _text(
                product_id, field_name="productId", operation_id=OP_LESSON_CREATE
            )
        },
        body=create_lesson_body(
            title=title,
            category_id=category_id,
            description=description,
            visibility=visibility,
            sequence_no=sequence_no,
            meta_data=meta_data,
            content_type=content_type,
            content_id=content_id,
        ),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def submit_import(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    location_id: str,
    hierarchy: Mapping[str, Any],
    user_id: str | None = None,
    lifecycle: CourseImportLifecycle,
    submission_fingerprint: str,
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    """Submit one import.  Refused unless the lifecycle is still ``planned``."""

    if tenant.location_id != location_id:
        raise ContractViolation(
            "tenant_mismatch",
            operation_id=OP_IMPORT_SUBMIT,
            detail={"hint": "import locationId must equal the call tenant"},
        )
    lifecycle.submit(submission_fingerprint)
    body = build_import_body(
        location_id=location_id, hierarchy=hierarchy, user_id=user_id
    )
    lifecycle.intended_hierarchy = dict(hierarchy)
    return _call(
        adapter,
        spec_for(OP_IMPORT_SUBMIT),
        tenant=tenant,
        body=body,
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def create_enrollment_body(*, contact_id: str, offer_id: str) -> dict[str, Any]:
    return {
        ASSUMED_DTO_FIELDS["enrollment.contact"]: _text(
            contact_id, field_name="contactId", operation_id=OP_ENROLLMENT_CREATE
        ),
        ASSUMED_DTO_FIELDS["enrollment.offer"]: _text(
            offer_id, field_name="offerId", operation_id=OP_ENROLLMENT_CREATE
        ),
    }


def create_enrollment(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    contact_id: str,
    offer_id: str,
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    return _call(
        adapter,
        spec_for(OP_ENROLLMENT_CREATE),
        tenant=tenant,
        body=create_enrollment_body(contact_id=contact_id, offer_id=offer_id),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


#: An enrollment is an access grant, never payment proof (Document 1 s8.7).
ENROLLMENT_IS_PAYMENT_PROOF = False

_ENROLLMENT_OUTCOME: Mapping[Status, str] = {
    Status.ok: "enrollment_created",
    Status.conflict: "verify_existing_enrollment",
    Status.validation_error: "verify_existing_enrollment",
    Status.unknown_outcome: "unknown_outcome",
    Status.denied: "denied",
    Status.not_found: "offer_or_contact_not_found",
    Status.rate_limited: "rate_limited",
    Status.unavailable: "unavailable",
}


def enrollment_outcome(result: OperationResult) -> str:
    """Resolve an enrollment attempt without ever claiming payment.

    ``ok`` means the entitlement was created.  ``conflict`` /
    ``validation_error`` can mean the contact was already enrolled for that
    offer: that resolves idempotently only after a read confirms the intended
    entitlement, so the answer is ``verify_existing_enrollment``, not success.
    """

    return _ENROLLMENT_OUTCOME.get(Status(result.status), "unknown_outcome")


def list_product_enrollments(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    query: Mapping[str, object] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    limit_param: str = "limit",
    cursor_param: str = "cursor",
    timeout_s: float | None = None,
) -> OperationResult:
    """Cursor-paginated product-enrollment read.

    The response cursor is not returned in :class:`OperationResult` (the
    adapter deliberately carries no payload), so the caller advances with
    :func:`advance_cursor` using the decoded page it read.  Parameter names are
    the exported assumption ``ASSUMED_DTO_FIELDS`` until WF00 records them.
    """

    page = dict(query or {})
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ContractViolation(
                "course_page_limit_invalid", operation_id=OP_PRODUCT_ENROLLMENTS_LIST
            )
        page[str(limit_param)] = limit
    if cursor is not None:
        page[str(cursor_param)] = _text(
            cursor,
            field_name="cursor",
            operation_id=OP_PRODUCT_ENROLLMENTS_LIST,
        )
    return _call(
        adapter,
        spec_for(OP_PRODUCT_ENROLLMENTS_LIST),
        tenant=tenant,
        query=page,
        timeout_s=timeout_s,
    )


def advance_cursor(
    query: Mapping[str, object],
    next_cursor: str,
    *,
    cursor_param: str = "cursor",
) -> dict[str, object]:
    page = dict(query)
    page[str(cursor_param)] = _text(
        next_cursor, field_name="cursor", operation_id=OP_PRODUCT_ENROLLMENTS_LIST
    )
    return page


def create_course_offer(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    product_id: str,
    offer_body: Mapping[str, Any],
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    """Create a course offer.  The offer body schema is not settled here."""

    if not isinstance(offer_body, Mapping) or not offer_body:
        raise ContractViolation("course_offer_body_required", operation_id=OP_OFFER_CREATE)
    return _call(
        adapter,
        spec_for(OP_OFFER_CREATE),
        tenant=tenant,
        path_params={
            "productId": _text(
                product_id, field_name="productId", operation_id=OP_OFFER_CREATE
            )
        },
        body=dict(offer_body),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def revocation_impact(
    *, offer_id: str, included_product_ids: Sequence[str]
) -> dict[str, Any]:
    """Compute the affected product set BEFORE an approved revoke.

    The caller supplies the offer snapshot's included product identifiers;
    this module does not guess the vendor's offer-response field name.
    """

    offer = _text(offer_id, field_name="offerId", operation_id=OP_OFFER_REVOKE)
    affected = sorted({str(item) for item in included_product_ids if str(item).strip()})
    return {
        "offer_id": offer,
        "affected_product_ids": affected,
        "affected_count": len(affected),
        "requires_confirmation": True,
    }


def revoke_offer(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    product_id: str,
    offer_id: str,
    included_product_ids: Sequence[str],
    idempotency_key: str,
    approval: ApprovalRef | Mapping[str, Any] | str,
    readback: ReadbackSpec | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> tuple[dict[str, Any], OperationResult]:
    """Show the affected set first, then apply the approved revoke."""

    impact = revocation_impact(
        offer_id=offer_id, included_product_ids=included_product_ids
    )
    result = _call(
        adapter,
        spec_for(OP_OFFER_REVOKE),
        tenant=tenant,
        path_params={
            "productId": _text(
                product_id, field_name="productId", operation_id=OP_OFFER_REVOKE
            ),
            "offerId": _text(
                offer_id, field_name="offerId", operation_id=OP_OFFER_REVOKE
            ),
        },
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )
    return impact, result


def create_lesson_quiz(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    product_id: str,
    lesson_id: str,
    quiz_body: Mapping[str, Any],
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    """Lesson-quiz create.  Body schema stays caller-supplied until resolved."""

    if not isinstance(quiz_body, Mapping) or not quiz_body:
        raise ContractViolation("course_quiz_body_required", operation_id=OP_QUIZ_CREATE)
    return _call(
        adapter,
        spec_for(OP_QUIZ_CREATE),
        tenant=tenant,
        path_params={
            "productId": _text(
                product_id, field_name="productId", operation_id=OP_QUIZ_CREATE
            ),
            "lessonId": _text(
                lesson_id, field_name="lessonId", operation_id=OP_QUIZ_CREATE
            ),
        },
        body=dict(quiz_body),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


def upsert_quiz_questions(
    adapter: PublicGhlAdapter,
    *,
    tenant: TenantBinding,
    product_id: str,
    quiz_id: str,
    questions_body: Mapping[str, Any],
    idempotency_key: str,
    readback: ReadbackSpec | None = None,
    approval: ApprovalRef | Mapping[str, Any] | str | None = None,
    timeout_s: float | None = None,
    attempt: int = 1,
) -> OperationResult:
    """Question upsert.  The payload is the resolved current schema, verbatim."""

    if not isinstance(questions_body, Mapping) or not questions_body:
        raise ContractViolation(
            "course_quiz_questions_required", operation_id=OP_QUIZ_QUESTIONS_UPSERT
        )
    return _call(
        adapter,
        spec_for(OP_QUIZ_QUESTIONS_UPSERT),
        tenant=tenant,
        path_params={
            "productId": _text(
                product_id,
                field_name="productId",
                operation_id=OP_QUIZ_QUESTIONS_UPSERT,
            ),
            "quizId": _text(
                quiz_id, field_name="quizId", operation_id=OP_QUIZ_QUESTIONS_UPSERT
            ),
        },
        body=dict(questions_body),
        idempotency_key=idempotency_key,
        approval=approval,
        readback=readback,
        timeout_s=timeout_s,
        attempt=attempt,
    )


__all__ = [
    "OP_COURSE_CREATE",
    "OP_COURSE_GET",
    "OP_CATEGORY_CREATE",
    "OP_LESSON_CREATE",
    "OP_IMPORT_SUBMIT",
    "OP_ENROLLMENT_CREATE",
    "OP_PRODUCT_ENROLLMENTS_LIST",
    "OP_OFFER_CREATE",
    "OP_OFFER_REVOKE",
    "OP_QUIZ_CREATE",
    "OP_QUIZ_QUESTIONS_UPSERT",
    "CourseOperationSpec",
    "COURSE_OPERATION_SPECS",
    "ASSUMED_DTO_FIELDS",
    "spec_for",
    "unresolved_operations",
    "create_course_body",
    "create_category_body",
    "create_lesson_body",
    "build_import_body",
    "CourseImportLifecycle",
    "IMPORT_STATES",
    "course_readback",
    "create_course",
    "create_category",
    "create_lesson",
    "submit_import",
    "create_enrollment_body",
    "create_enrollment",
    "enrollment_outcome",
    "ENROLLMENT_IS_PAYMENT_PROOF",
    "list_product_enrollments",
    "advance_cursor",
    "create_course_offer",
    "revocation_impact",
    "revoke_offer",
    "create_lesson_quiz",
    "upsert_quiz_questions",
]
