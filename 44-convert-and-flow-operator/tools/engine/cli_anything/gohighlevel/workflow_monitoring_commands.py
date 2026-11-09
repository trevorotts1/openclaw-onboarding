"""Workflow-monitoring click commands (WF25).

WF03 owns ``gohighlevel_cli.py`` and registers this module; WF25 never edits the
CLI entrypoint.  The exact registration patch is filed as a change request.

Every command is read-only and caller-driven: ``logs`` and ``stats`` read the
bounded windows the caller asks for and exit, and nothing here schedules,
sleeps or starts a service.  ``windows`` is offline and prints the validated
window plan so an operator can see the split before spending a call.

Failures exit non-zero: a contract refusal is printed with its machine rule and
never rendered as an empty successful result.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping

import click

from .public.errors import ContractViolation
from .public.workflow_monitoring import (
    DEFAULT_CONTRACT,
    MAX_PAGES_PER_SCAN,
    MonitoringContract,
    WorkflowMonitoring,
)

__all__ = ["build_group", "monitoring"]


def _pairs(values: tuple[str, ...], *, option: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise click.BadParameter(f"{option} expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        if not key.strip():
            raise click.BadParameter(f"{option} expects a non-empty key")
        parsed[key.strip()] = value
    return parsed


def _default_monitoring(ctx: click.Context) -> WorkflowMonitoring:
    """Build the real read path: public adapter over the frozen auth seam."""

    location_id = (ctx.obj or {}).get("location_id") or os.environ.get("GHL_LOCATION_ID")
    if not location_id:
        raise click.ClickException("--location-id or GHL_LOCATION_ID is required")
    from .public.adapter import PublicGhlAdapter
    from .public.auth import AuthKind, TenantBinding, resolve_auth

    auth = resolve_auth(kind=AuthKind.location_pit, location_id=location_id)
    public = PublicGhlAdapter(auth=auth)
    return WorkflowMonitoring(
        public=public,
        tenant=TenantBinding(location_id=location_id, source="request"),
    )


def _emit(ctx: click.Context, payload: Mapping[str, Any], label: str) -> None:
    if bool((ctx.obj or {}).get("json")):
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    click.echo(f"\n{label}")
    click.echo("-" * len(label))
    for key in ("workflow_id", "metric_kind", "label", "pages_read", "duplicates_dropped", "total_events"):
        if key in payload:
            click.echo(f"{key}: {payload[key]}")
    counts = payload.get("counts")
    if isinstance(counts, Mapping):
        for name in sorted(counts):
            click.echo(f"{name}: {counts[name]}")


def _fail(rule: str, detail: Mapping[str, Any] | None = None) -> None:
    suffix = ""
    if detail:
        suffix = " " + " ".join(f"{key}={detail[key]}" for key in sorted(detail))
    click.echo(f"Error: {rule}{suffix}", err=True)
    raise SystemExit(1)


def build_group(
    get_monitoring: Callable[[click.Context], WorkflowMonitoring] | None = None,
    *,
    contract: MonitoringContract | None = None,
) -> click.Group:
    """Build the ``monitoring`` group; tests inject a monitoring factory."""

    factory = get_monitoring or _default_monitoring
    window_contract = contract or DEFAULT_CONTRACT

    @click.group("monitoring", help="Workflow logs and statistics (read-only, bounded windows).")
    @click.pass_context
    def group(ctx: click.Context) -> None:
        ctx.ensure_object(dict)

    @group.command("logs")
    @click.option("--workflow-id", required=True, help="Workflow ID to read logs for")
    @click.option("--from", "start", required=True, help="RFC3339 window start (with offset)")
    @click.option("--to", "end", required=True, help="RFC3339 window end (with offset)")
    @click.option("--filter", "filters", multiple=True, metavar="KEY=VALUE", help="Non-date filters, forwarded unchanged")
    @click.option("--max-pages", default=10, type=int, show_default=True, help=f"Bounded page budget (max {MAX_PAGES_PER_SCAN})")
    @click.pass_context
    def logs_command(
        ctx: click.Context,
        workflow_id: str,
        start: str,
        end: str,
        filters: tuple[str, ...],
        max_pages: int,
    ) -> None:
        """Read one bounded, deduplicated log scan and print a redacted summary."""

        try:
            monitoring = factory(ctx)
            result = monitoring.logs(
                workflow_id=workflow_id,
                start=start,
                end=end,
                filters=_pairs(filters, option="--filter"),
                max_pages=max_pages,
            )
        except ContractViolation as exc:
            _fail(exc.rule, exc.detail)
        _emit(ctx, result.summary(), f"Workflow {workflow_id} log scan")

    @group.command("stats")
    @click.option("--workflow-id", required=True, help="Workflow ID to aggregate")
    @click.option("--from", "start", required=True, help="RFC3339 window start (with offset)")
    @click.option("--to", "end", required=True, help="RFC3339 window end (with offset)")
    @click.option("--group-by", "group_by", multiple=True, required=True, help="Grouping field name (informational)")
    @click.option("--group-query", "group_query", multiple=True, required=True, metavar="KEY=VALUE", help="Documented grouping query parameters from the WF00 operation row")
    @click.option("--limit", required=True, type=int, help="Aggregate group bound; never silently truncated")
    @click.option("--declared-limit", default=None, type=int, help="Caller-declared bound while the provider limit is unfrozen")
    @click.option("--filter", "filters", multiple=True, metavar="KEY=VALUE")
    @click.pass_context
    def stats_command(
        ctx: click.Context,
        workflow_id: str,
        start: str,
        end: str,
        group_by: tuple[str, ...],
        group_query: tuple[str, ...],
        limit: int,
        declared_limit: int | None,
        filters: tuple[str, ...],
    ) -> None:
        """Read per-window event counts; never labelled cohort conversion."""

        try:
            monitoring = factory(ctx)
            result = monitoring.aggregate(
                workflow_id=workflow_id,
                start=start,
                end=end,
                group_by=group_by,
                limit=limit,
                group_query=_pairs(group_query, option="--group-query"),
                declared_limit=declared_limit,
                filters=_pairs(filters, option="--filter"),
            )
        except ContractViolation as exc:
            _fail(exc.rule, exc.detail)
        _emit(ctx, result.summary(), f"Workflow {workflow_id} statistics")

    @group.command("windows")
    @click.option("--from", "start", required=True, help="RFC3339 period start (with offset)")
    @click.option("--to", "end", required=True, help="RFC3339 period end (with offset)")
    @click.pass_context
    def windows_command(ctx: click.Context, start: str, end: str) -> None:
        """Print the validated, non-overlapping query-window plan (offline)."""

        try:
            windows = window_contract.windows(start, end)
        except ContractViolation as exc:
            _fail(exc.rule, exc.detail)
        payload = {
            "contract_revision": window_contract.revision,
            "max_window_days": window_contract.max_window_days,
            "retention_days": window_contract.retention_days,
            "windows": [window.as_mapping() for window in windows],
        }
        _emit(ctx, payload, "Query window plan")

    return group


monitoring = build_group()
