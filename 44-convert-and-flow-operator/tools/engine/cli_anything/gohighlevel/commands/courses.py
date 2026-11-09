"""``courses`` command group (WF06).

WF03 registers this module once::

    from .commands import courses as courses_commands
    courses_commands.register(cli, get_runtime=_public_runtime)

``get_runtime(ctx) -> (PublicGhlAdapter, TenantBinding)`` keeps auth, transport
and tenant selection in the CLI owner's hands; this module never reads secrets
or constructs a transport.  Every mutation goes through
``public/courses.py`` and therefore through the one public adapter.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

import click

from ..public.adapter import PublicGhlAdapter
from ..public.auth import TenantBinding
from ..public.errors import ContractViolation
from ..public.idempotency import IdempotencyKey
from ..public.readback import ReadbackSpec
from ..public import courses as course_api

Runtime = tuple[PublicGhlAdapter, TenantBinding]
RuntimeFactory = Callable[[click.Context], Runtime]


def _json_object(text: str | None, *, option: str) -> dict[str, Any]:
    if text is None:
        return {}
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise click.BadParameter(f"{option} must be valid JSON: {exc}") from exc
    if not isinstance(value, Mapping):
        raise click.BadParameter(f"{option} must be a JSON object")
    return dict(value)


def _key(operation_id: str, supplied: str | None) -> str:
    if supplied is not None and supplied.strip():
        return supplied.strip()
    return IdempotencyKey.issue(operation_id).value


def _readback(
    operation_id: str | None,
    path_params_json: str | None,
    expect_json: str | None,
) -> ReadbackSpec | None:
    if operation_id is None:
        return None
    expect = _json_object(expect_json, option="--readback-expect-json")
    if not expect:
        raise click.BadParameter(
            "--readback-expect-json is required with --readback-operation"
        )
    params = _json_object(path_params_json, option="--readback-path-params-json")
    return ReadbackSpec(
        operation_id=operation_id,
        target_params={str(k): str(v) for k, v in params.items()},
        expect=expect,
    )


def _emit(result: Any) -> None:
    click.echo(
        json.dumps(
            {
                "status": str(getattr(result, "status", "")),
                "operation_id": getattr(result, "operation_id", None),
                "receipt_id": getattr(result, "receipt_id", None),
                "http_status": getattr(result, "http_status", None),
                "readback": (
                    getattr(getattr(result, "readback", None), "result", None)
                    and str(result.readback.result)
                ),
                "error": getattr(result, "error", None),
            },
            sort_keys=True,
        )
    )


def build_group(get_runtime: RuntimeFactory) -> click.Group:
    def runtime(ctx: click.Context) -> Runtime:
        adapter, tenant = get_runtime(ctx)
        if not isinstance(adapter, PublicGhlAdapter):
            raise click.ClickException("runtime did not supply a PublicGhlAdapter")
        if not isinstance(tenant, TenantBinding):
            raise click.ClickException("runtime did not supply a TenantBinding")
        return adapter, tenant

    @click.group(name="courses")
    def group() -> None:
        """Course adapter commands (course/category/lesson/import/enrollment)."""

    @group.command("create")
    @click.option("--title", required=True)
    @click.option("--description", default=None)
    @click.option("--poster-image", default=None)
    @click.option("--customizations-json", default=None)
    @click.option("--idempotency-key", default=None)
    @click.option("--readback-operation", default=None)
    @click.option("--readback-path-params-json", default=None)
    @click.option("--readback-expect-json", default=None)
    @click.pass_context
    def create(
        ctx: click.Context,
        title: str,
        description: str | None,
        poster_image: str | None,
        customizations_json: str | None,
        idempotency_key: str | None,
        readback_operation: str | None,
        readback_path_params_json: str | None,
        readback_expect_json: str | None,
    ) -> None:
        """Create a course shell.  Location is a query, never a body field."""

        adapter, tenant = runtime(ctx)
        customizations = _json_object(
            customizations_json, option="--customizations-json"
        )
        try:
            result = course_api.create_course(
                adapter,
                tenant=tenant,
                title=title,
                description=description,
                poster_image=poster_image,
                customizations=customizations or None,
                idempotency_key=_key(course_api.OP_COURSE_CREATE, idempotency_key),
                readback=_readback(
                    readback_operation,
                    readback_path_params_json,
                    readback_expect_json,
                ),
            )
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(result)

    @group.command("category-create")
    @click.option("--product-id", required=True)
    @click.option("--title", required=True)
    @click.option("--visibility", default=None)
    @click.option("--parent-category-id", default=None)
    @click.option("--metadata-json", default=None)
    @click.option("--sequence-no", type=int, default=None)
    @click.option("--idempotency-key", default=None)
    @click.option("--readback-operation", default=None)
    @click.option("--readback-path-params-json", default=None)
    @click.option("--readback-expect-json", default=None)
    @click.pass_context
    def category_create(
        ctx: click.Context,
        product_id: str,
        title: str,
        visibility: str | None,
        parent_category_id: str | None,
        metadata_json: str | None,
        sequence_no: int | None,
        idempotency_key: str | None,
        readback_operation: str | None,
        readback_path_params_json: str | None,
        readback_expect_json: str | None,
    ) -> None:
        """Create a category (settings use lower-case ``metadata``)."""

        adapter, tenant = runtime(ctx)
        try:
            result = course_api.create_category(
                adapter,
                tenant=tenant,
                product_id=product_id,
                title=title,
                visibility=visibility,
                parent_category_id=parent_category_id,
                metadata=_json_object(metadata_json, option="--metadata-json") or None,
                sequence_no=sequence_no,
                idempotency_key=_key(
                    course_api.OP_CATEGORY_CREATE, idempotency_key
                ),
                readback=_readback(
                    readback_operation,
                    readback_path_params_json,
                    readback_expect_json,
                ),
            )
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(result)

    @group.command("lesson-create")
    @click.option("--product-id", required=True)
    @click.option("--title", required=True)
    @click.option("--category-id", required=True)
    @click.option("--description", default=None)
    @click.option("--visibility", default=None)
    @click.option("--sequence-no", type=int, default=None)
    @click.option("--meta-data-json", default=None)
    @click.option("--content-type", default=None)
    @click.option("--content-id", default=None)
    @click.option("--idempotency-key", default=None)
    @click.option("--readback-operation", default=None)
    @click.option("--readback-path-params-json", default=None)
    @click.option("--readback-expect-json", default=None)
    @click.pass_context
    def lesson_create(
        ctx: click.Context,
        product_id: str,
        title: str,
        category_id: str,
        description: str | None,
        visibility: str | None,
        sequence_no: int | None,
        meta_data_json: str | None,
        content_type: str | None,
        content_id: str | None,
        idempotency_key: str | None,
        readback_operation: str | None,
        readback_path_params_json: str | None,
        readback_expect_json: str | None,
    ) -> None:
        """Create a lesson (settings use capital-D ``metaData``)."""

        adapter, tenant = runtime(ctx)
        try:
            result = course_api.create_lesson(
                adapter,
                tenant=tenant,
                product_id=product_id,
                title=title,
                category_id=category_id,
                description=description,
                visibility=visibility,
                sequence_no=sequence_no,
                meta_data=_json_object(meta_data_json, option="--meta-data-json") or None,
                content_type=content_type,
                content_id=content_id,
                idempotency_key=_key(course_api.OP_LESSON_CREATE, idempotency_key),
                readback=_readback(
                    readback_operation,
                    readback_path_params_json,
                    readback_expect_json,
                ),
            )
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(result)

    @group.command("import")
    @click.option("--location-id", required=True)
    @click.option("--hierarchy-json", required=True)
    @click.option("--user-id", default=None)
    @click.option("--submission-fingerprint", required=True)
    @click.option("--idempotency-key", default=None)
    @click.option("--readback-operation", default=None)
    @click.option("--readback-path-params-json", default=None)
    @click.option("--readback-expect-json", default=None)
    @click.pass_context
    def import_course(
        ctx: click.Context,
        location_id: str,
        hierarchy_json: str,
        user_id: str | None,
        submission_fingerprint: str,
        idempotency_key: str | None,
        readback_operation: str | None,
        readback_path_params_json: str | None,
        readback_expect_json: str | None,
    ) -> None:
        """Submit one course import (state machine starts at planned)."""

        adapter, tenant = runtime(ctx)
        hierarchy = _json_object(hierarchy_json, option="--hierarchy-json")
        lifecycle = course_api.CourseImportLifecycle()
        try:
            result = course_api.submit_import(
                adapter,
                tenant=tenant,
                location_id=location_id,
                hierarchy=hierarchy,
                user_id=user_id,
                lifecycle=lifecycle,
                submission_fingerprint=submission_fingerprint,
                idempotency_key=_key(course_api.OP_IMPORT_SUBMIT, idempotency_key),
                readback=_readback(
                    readback_operation,
                    readback_path_params_json,
                    readback_expect_json,
                ),
            )
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(result)
        click.echo(json.dumps(lifecycle.as_receipt(), sort_keys=True))

    @group.command("enroll")
    @click.option("--contact-id", required=True)
    @click.option("--offer-id", required=True)
    @click.option("--idempotency-key", default=None)
    @click.option("--readback-operation", default=None)
    @click.option("--readback-path-params-json", default=None)
    @click.option("--readback-expect-json", default=None)
    @click.pass_context
    def enroll(
        ctx: click.Context,
        contact_id: str,
        offer_id: str,
        idempotency_key: str | None,
        readback_operation: str | None,
        readback_path_params_json: str | None,
        readback_expect_json: str | None,
    ) -> None:
        """Create an enrollment.  An enrollment is never payment proof."""

        adapter, tenant = runtime(ctx)
        try:
            result = course_api.create_enrollment(
                adapter,
                tenant=tenant,
                contact_id=contact_id,
                offer_id=offer_id,
                idempotency_key=_key(
                    course_api.OP_ENROLLMENT_CREATE, idempotency_key
                ),
                readback=_readback(
                    readback_operation,
                    readback_path_params_json,
                    readback_expect_json,
                ),
            )
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(result)
        click.echo(
            json.dumps(
                {
                    "enrollment_outcome": course_api.enrollment_outcome(result),
                    "payment_proof": course_api.ENROLLMENT_IS_PAYMENT_PROOF,
                },
                sort_keys=True,
            )
        )

    @group.command("revoke-preview")
    @click.option("--offer-id", required=True)
    @click.option("--included-product-ids", required=True)
    def revoke_preview(offer_id: str, included_product_ids: str) -> None:
        """Show the affected product set BEFORE an approved revoke."""

        products = [
            item.strip()
            for item in str(included_product_ids).split(",")
            if item.strip()
        ]
        click.echo(
            json.dumps(
                course_api.revocation_impact(
                    offer_id=offer_id, included_product_ids=products
                ),
                sort_keys=True,
            )
        )

    @group.command("enrollments")
    @click.option("--limit", type=int, default=None)
    @click.option("--cursor", default=None)
    @click.option("--query-json", default=None)
    @click.pass_context
    def enrollments(
        ctx: click.Context,
        limit: int | None,
        cursor: str | None,
        query_json: str | None,
    ) -> None:
        """Cursor-paginated product-enrollment read."""

        adapter, tenant = runtime(ctx)
        try:
            result = course_api.list_product_enrollments(
                adapter,
                tenant=tenant,
                query=_json_object(query_json, option="--query-json"),
                limit=limit,
                cursor=cursor,
            )
        except ContractViolation as exc:
            raise click.ClickException(str(exc)) from exc
        _emit(result)

    return group


def register(root: click.Group, *, get_runtime: RuntimeFactory) -> click.Group:
    """Attach the ``courses`` group to the CLI root and return it."""

    if not isinstance(root, click.Group):
        raise ContractViolation("cli_root_invalid")
    group = build_group(get_runtime)
    root.add_command(group)
    return group


__all__ = ["build_group", "register", "Runtime", "RuntimeFactory"]
