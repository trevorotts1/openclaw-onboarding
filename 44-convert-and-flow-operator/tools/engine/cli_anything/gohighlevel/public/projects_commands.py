"""Projects command module (WF32).  WF03 registers ``register()``.

The group is deliberately offline-safe: every operation resolves from a
Skills 36 discovery document.  Without one the command fails closed instead of
inventing a Projects endpoint.  A fixture document is refused unless
``--allow-fixture`` is passed, and every output is stamped ``fixture`` when it is.

Registration request (WF03 owns ``gohighlevel_cli.py``)::

    from cli_anything.gohighlevel.public.projects_commands import register
    register(cli)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

import click

from . import projects as pj
from .auth import AuthKind, TenantBinding, resolve_auth
from .capability import load_capability_record
from .errors import ContractViolation

_SERVICE_FACTORY: Callable[..., pj.ProjectsService] | None = None


def set_service_factory(factory: Callable[..., pj.ProjectsService] | None) -> None:
    """Test seam only: build the service without touching credentials."""

    global _SERVICE_FACTORY
    _SERVICE_FACTORY = factory


def register(root: click.Group) -> click.Group:
    root.add_command(projects)
    return root


def _refuse(exc: ContractViolation) -> None:
    payload = {"rule": exc.rule, "detail": dict(exc.detail)}
    if exc.operation_id:
        payload["operation_id"] = exc.operation_id
    click.echo(json.dumps(payload, indent=2, default=str), err=True)
    raise click.exceptions.Exit(3)


def _emit(payload: Mapping[str, Any]) -> None:
    click.echo(json.dumps(payload, indent=2, default=str))


def _load_catalog(path: str | None, *, allow_fixture: bool) -> pj.ProjectsCatalog:
    if not path:
        raise click.UsageError(
            "no Projects discovery document: pass --catalog <skill36-projects.json>; "
            "refusing to invent endpoints"
        )
    document = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    evidence = str(document.get("evidence", pj.EVIDENCE_DISCOVERY))
    if evidence == pj.EVIDENCE_FIXTURE and not allow_fixture:
        raise click.UsageError(
            "fixture catalog refused; pass --allow-fixture for an explicitly "
            "synthetic run"
        )
    return pj.ProjectsCatalog.from_document(document)


def _service(
    ctx: click.Context,
    *,
    catalog_path: str | None,
    allow_fixture: bool,
    base_url: str,
) -> pj.ProjectsService:
    if _SERVICE_FACTORY is not None:
        return _SERVICE_FACTORY(
            ctx=ctx,
            catalog_path=catalog_path,
            allow_fixture=allow_fixture,
            base_url=base_url,
        )
    catalog = _load_catalog(catalog_path, allow_fixture=allow_fixture)
    location_id = ctx.obj.get("projects_location_id")
    if not location_id:
        raise click.UsageError("pass --location-id or set GHL_LOCATION_ID")
    auth = resolve_auth(kind=AuthKind.location_pit, location_id=location_id)
    tenant = TenantBinding(location_id=location_id, source="cli:projects")
    return pj.ProjectsService.connect(
        auth=auth,
        tenant=tenant,
        catalog=catalog,
        gate=load_capability_record(tenant=location_id),
        allow_fixture=allow_fixture,
        base_url=base_url,
    )


def _object_payload(service: pj.ProjectsService, obj: pj.ProjectsObject) -> dict[str, Any]:
    return {
        "fixture": service.fixture,
        "kind": obj.kind,
        "id": obj.id,
        "verified": obj.verified,
        "verification": obj.verification,
        "result_status": obj.result.status.value if obj.result is not None else None,
    }


@click.group("projects")
@click.option("--catalog", "catalog_path", default=None, help="Skill 36 discovery JSON")
@click.option("--location-id", "location_id", default=None)
@click.option("--allow-fixture", is_flag=True, default=False)
@click.option("--base-url", default=pj.DEFAULT_BASE_URL, hidden=True)
@click.pass_context
def projects(ctx, catalog_path, location_id, allow_fixture, base_url):
    """GHL Projects: spaces, lists, statuses, tasks, subtasks, members."""

    ctx.ensure_object(dict)
    ctx.obj["projects_catalog_path"] = catalog_path
    ctx.obj["projects_allow_fixture"] = allow_fixture
    ctx.obj["projects_base_url"] = base_url
    ctx.obj["projects_location_id"] = location_id or os.environ.get("GHL_LOCATION_ID")


def _svc(ctx: click.Context) -> pj.ProjectsService:
    return _service(
        ctx,
        catalog_path=ctx.obj.get("projects_catalog_path"),
        allow_fixture=bool(ctx.obj.get("projects_allow_fixture")),
        base_url=str(ctx.obj.get("projects_base_url") or pj.DEFAULT_BASE_URL),
    )


@projects.command("availability")
@click.option("--ui-state", type=click.Choice([s.value for s in pj.AvailabilityState]),
              default="unknown", show_default=True)
@click.option("--ui-source", default="not_checked", show_default=True)
@click.option("--ui-reference", default="cli:ui", show_default=True)
@click.option("--api-state", type=click.Choice([s.value for s in pj.AvailabilityState]),
              default="unknown", show_default=True)
@click.option("--api-source", default="not_checked", show_default=True)
@click.option("--api-reference", default="cli:api", show_default=True)
@click.option("--checked-at", default="2026-11-08T00:00:00+00:00", show_default=True)
@click.option("--require", "required", multiple=True,
              type=click.Choice(["ui", "api"]), help="exit 3 unless available")
def projects_availability(
    ui_state, ui_source, ui_reference, api_state, api_source, api_reference,
    checked_at, required,
):
    """Report UI/Labs and API beta availability as independent facts."""

    try:
        availability = pj.ProjectsAvailability.from_records(
            ui_labs=pj.AvailabilityEvidence(
                dimension="ui_labs",
                state=ui_state,
                source=ui_source,
                reference=ui_reference,
                checked_at=checked_at,
            ),
            api_beta=pj.AvailabilityEvidence(
                dimension="api_beta",
                state=api_state,
                source=api_source,
                reference=api_reference,
                checked_at=checked_at,
            ),
        )
        for dimension in required:
            (availability.require_ui if dimension == "ui" else availability.require_api)()
    except ContractViolation as exc:
        _refuse(exc)
    _emit(availability.as_mapping())


@projects.command("space-create")
@click.option("--name", required=True)
@click.option("--description", default=None)
@click.option("--private", is_flag=True, default=False)
@click.pass_context
def projects_space_create(ctx, name, description, private):
    """Create a space, then discover its server-created default list."""

    try:
        service = _svc(ctx)
        space = service.create_space(name, description=description, private=private)
        default_list = service.discover_default_list(space.id)
    except ContractViolation as exc:
        _refuse(exc)
    payload = _object_payload(service, space)
    payload["default_list"] = (
        None
        if default_list is None
        else {"id": default_list.id, "verification": default_list.verification}
    )
    _emit(payload)


@projects.command("space-list")
@click.pass_context
def projects_space_list(ctx):
    try:
        service = _svc(ctx)
        page = service.list_spaces()
    except ContractViolation as exc:
        _refuse(exc)
    _emit({"fixture": service.fixture, "operation_id": page.operation_id,
           "pages": page.pages, "records": list(page.records)})


@projects.command("default-list")
@click.option("--space-id", required=True)
@click.pass_context
def projects_default_list(ctx, space_id):
    try:
        service = _svc(ctx)
        found = service.discover_default_list(space_id)
    except ContractViolation as exc:
        _refuse(exc)
    _emit({"fixture": service.fixture,
           "list": None if found is None else {"id": found.id, "data": dict(found.data)}})


@projects.command("list-create")
@click.option("--space-id", required=True)
@click.option("--name", required=True)
@click.option("--folder-id", default=None)
@click.pass_context
def projects_list_create(ctx, space_id, name, folder_id):
    try:
        service = _svc(ctx)
        created = service.create_list(space_id, name, folder_id=folder_id)
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, created))


@projects.command("statuses")
@click.option("--list-id", required=True)
@click.pass_context
def projects_statuses(ctx, list_id):
    try:
        service = _svc(ctx)
        page = service.list_statuses(list_id)
    except ContractViolation as exc:
        _refuse(exc)
    _emit({"fixture": service.fixture, "operation_id": page.operation_id,
           "records": list(page.records)})


@projects.command("task-create")
@click.option("--list-id", required=True)
@click.option("--title", required=True)
@click.option("--due-date", required=True)
@click.option("--status", default=None)
@click.option("--assignee-id", default=None)
@click.option("--description", default=None)
@click.pass_context
def projects_task_create(ctx, list_id, title, due_date, status, assignee_id, description):
    try:
        service = _svc(ctx)
        created = service.create_task(
            title,
            due_date,
            list_id=list_id,
            status=status,
            assignee_id=assignee_id,
            description=description,
        )
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, created))


@projects.command("subtask-create")
@click.option("--parent-task-id", required=True)
@click.option("--title", required=True)
@click.option("--due-date", required=True)
@click.option("--status", default=None)
@click.option("--assignee-id", default=None)
@click.pass_context
def projects_subtask_create(ctx, parent_task_id, title, due_date, status, assignee_id):
    try:
        service = _svc(ctx)
        created = service.create_subtask(
            parent_task_id,
            title,
            due_date,
            status=status,
            assignee_id=assignee_id,
        )
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, created))


@projects.command("task-list")
@click.option("--list-id", required=True)
@click.pass_context
def projects_task_list(ctx, list_id):
    try:
        service = _svc(ctx)
        page = service.list_tasks(list_id)
    except ContractViolation as exc:
        _refuse(exc)
    _emit({"fixture": service.fixture, "operation_id": page.operation_id,
           "pages": page.pages, "records": list(page.records)})


@projects.command("add-task-to-list")
@click.option("--task-id", required=True)
@click.option("--list-id", required=True)
@click.pass_context
def projects_add_task_to_list(ctx, task_id, list_id):
    try:
        service = _svc(ctx)
        obj = service.add_task_to_list(task_id, list_id)
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, obj))


@projects.command("comment-add")
@click.option("--task-id", required=True)
@click.option("--body", required=True)
@click.pass_context
def projects_comment_add(ctx, task_id, body):
    try:
        service = _svc(ctx)
        obj = service.add_comment(task_id, body)
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, obj))


@projects.command("recurrence-set")
@click.option("--task-id", required=True)
@click.option("--payload", "payload_json", required=True,
              help="structured recurrence JSON object (never an RRULE string)")
@click.pass_context
def projects_recurrence_set(ctx, task_id, payload_json):
    try:
        recurrence = json.loads(payload_json)
        service = _svc(ctx)
        obj = service.set_recurrence(task_id, recurrence)
    except json.JSONDecodeError as exc:
        raise click.BadParameter("payload must be a JSON object") from exc
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, obj))


@projects.command("members")
@click.option("--space-id", required=True)
@click.pass_context
def projects_members(ctx, space_id):
    try:
        service = _svc(ctx)
        page = service.list_members(space_id)
    except ContractViolation as exc:
        _refuse(exc)
    _emit({"fixture": service.fixture, "operation_id": page.operation_id,
           "records": list(page.records)})


@projects.command("member-remove")
@click.option("--space-id", required=True)
@click.option("--member-id", required=True)
@click.option("--approval-ref", required=True)
@click.pass_context
def projects_member_remove(ctx, space_id, member_id, approval_ref):
    from .adapter import ApprovalRef

    try:
        service = _svc(ctx)
        obj = service.remove_member(
            space_id, member_id, approval=ApprovalRef(ref=approval_ref)
        )
    except ContractViolation as exc:
        _refuse(exc)
    _emit(_object_payload(service, obj))


@projects.command("list-delete")
@click.option("--list-id", required=True)
@click.option("--space-id", required=True)
@click.option("--approval-ref", required=True)
@click.option("--impact-fingerprint", default=None)
@click.option("--approved-by", default="operator")
@click.pass_context
def projects_list_delete(ctx, list_id, space_id, approval_ref, impact_fingerprint, approved_by):
    """Delete a list only with an authorization bound to its impact report."""

    try:
        service = _svc(ctx)
        report = service.impact_report(list_id)
        authorization = (
            None
            if impact_fingerprint is None
            else pj.ImpactAuthorization(
                report_fingerprint=impact_fingerprint,
                approved_by=approved_by,
                reference=approval_ref,
            )
        )
        obj = service.delete_list(
            list_id, space_id=space_id, authorization=authorization
        )
    except ContractViolation as exc:
        _refuse(exc)
    payload = _object_payload(service, obj)
    payload["impact"] = {"child_count": report.child_count,
                         "fingerprint": report.fingerprint}
    _emit(payload)


@projects.command("space-delete")
@click.option("--space-id", required=True)
@click.option("--approval-ref", required=True)
@click.option("--impact-fingerprint", default=None)
@click.option("--approved-by", default="operator")
@click.pass_context
def projects_space_delete(ctx, space_id, approval_ref, impact_fingerprint, approved_by):
    try:
        service = _svc(ctx)
        report = service.impact_report_space(space_id)
        authorization = (
            None
            if impact_fingerprint is None
            else pj.ImpactAuthorization(
                report_fingerprint=impact_fingerprint,
                approved_by=approved_by,
                reference=approval_ref,
            )
        )
        obj = service.delete_space(space_id, authorization=authorization)
    except ContractViolation as exc:
        _refuse(exc)
    payload = _object_payload(service, obj)
    payload["impact"] = {"child_count": report.child_count,
                         "fingerprint": report.fingerprint}
    _emit(payload)


__all__ = ["projects", "register", "set_service_factory"]
