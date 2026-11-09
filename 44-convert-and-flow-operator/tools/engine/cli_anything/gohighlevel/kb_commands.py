"""Knowledge Base CLI commands (WF30).

WF03 owns ``gohighlevel_cli.py`` and command registration.  This module is the
registration-ready surface::

    from cli_anything.gohighlevel.kb_commands import build_kb_group
    cli.add_command(build_kb_group(adapter_factory=..., tenant_factory=...))

The module-level ``kb`` group exists so a registration line is a one-liner,
but it refuses with a clear message until a factory is wired: no command ever
guesses a credential, a tenant or an adapter.  Every command prints JSON and
exits non-zero on a non-ok operation, a refusal or a named gap.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import click

from .public import knowledge_bases as kb_api
from .public.auth import TenantBinding
from .public.errors import ContractViolation
from .public.result import OperationResult, Status


def _result_payload(result: OperationResult, body: Any = None) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "operation_id": result.operation_id,
        "receipt_id": result.receipt_id,
        "tenant": result.tenant,
        "http_status": result.http_status,
        "readback": None if result.readback is None else result.readback.result.value,
        "error": result.error,
        "body": body,
    }


def _fail(ctx: click.Context, payload: dict[str, Any], code: int) -> None:
    click.echo(json.dumps(payload, indent=2, default=str), err=True)
    ctx.exit(code)


def _emit(ctx: click.Context, result: OperationResult, body: Any = None) -> None:
    payload = _result_payload(result, body)
    if result.status is not Status.ok:
        _fail(ctx, payload, 1)
        return
    click.echo(json.dumps(payload, indent=2, default=str))


def _guard(ctx: click.Context, action: Callable[[], Any]) -> Any:
    try:
        return action()
    except (kb_api.KnowledgeBaseGap, kb_api.KnowledgeBaseRefusal, ContractViolation) as caught:
        _fail(
            ctx,
            {
                "refused": True,
                "rule": getattr(caught, "rule", "contract_violation"),
                "detail": getattr(caught, "detail", {}),
            },
            2,
        )
        return None


def build_kb_group(
    *,
    adapter_factory: Callable[[], kb_api.KnowledgeBaseClient] | None = None,
    tenant_factory: Callable[[], TenantBinding] | None = None,
) -> click.Group:
    """Build the ``kb`` command group around injected factories."""

    def _client() -> kb_api.KnowledgeBaseClient:
        if adapter_factory is None:
            raise click.UsageError(
                "KB commands are not wired: WF03 must register build_kb_group("
                "adapter_factory=..., tenant_factory=...)"
            )
        return adapter_factory()

    def _tenant() -> TenantBinding:
        if tenant_factory is None:
            raise click.UsageError(
                "KB commands are not wired: WF03 must register build_kb_group("
                "adapter_factory=..., tenant_factory=...)"
            )
        return tenant_factory()

    @click.group("kb")
    def group() -> None:
        """Knowledge Base lifecycle (native GHL knowledge, sources, agent)."""

    @group.command("inventory")
    @click.option("--query", default=None, help="Filter by name")
    @click.option("--limit", type=int, default=None, help="Page size")
    @click.option("--last-id", default=None, help="Pagination cursor")
    @click.pass_context
    def inventory(ctx, query, limit, last_id):
        """List knowledge bases and the per-location limit state."""
        client = _client()
        call = _guard(ctx, lambda: client.inventory(
            _tenant(), query=query, limit=limit, last_id=last_id,
        ))
        if call is None:
            return
        body = call.body
        if call.result.status is Status.ok and body is not None:
            try:
                parsed = kb_api.parse_inventory(body)
            except ContractViolation as caught:
                _fail(ctx, {"refused": True, "rule": caught.rule, "detail": caught.detail}, 2)
                return
            if parsed.active_count >= kb_api.KB_PER_LOCATION_LIMIT:
                click.echo(json.dumps({
                    "limit_state": "at_or_over_limit",
                    "active_count": parsed.active_count,
                    "limit": kb_api.KB_PER_LOCATION_LIMIT,
                    "delete_permitted": False,
                    "hint": "reuse an existing knowledge base; deletion to free capacity is refused",
                }, indent=2), err=True)
        _emit(ctx, call.result, body)

    @group.command("create")
    @click.option("--name", required=True, help="Knowledge base name")
    @click.option("--description", default=None, help="Description")
    @click.pass_context
    def create(ctx, name, description):
        """Create a knowledge base (the caller inventories first; no deletion)."""
        client = _client()
        call = _guard(ctx, lambda: client.create(_tenant(), name=name, description=description))
        if call is None:
            return
        _emit(ctx, call.result, call.body)

    @group.command("discover")
    @click.option("--kb-id", required=True, help="Knowledge base id")
    @click.option("--url", required=True, help="Approved https URL")
    @click.option("--option", type=click.Choice(kb_api.CRAWLER_OPTIONS), default="Exact")
    @click.pass_context
    def discover(ctx, kb_id, url, option):
        """Start crawler discovery.  Preview/discovery is NOT ingestion."""
        client = _client()
        call = _guard(ctx, lambda: client.discover_urls(
            _tenant(), knowledge_base_id=kb_id, url=url, option=option,
        ))
        if call is None:
            return
        _emit(ctx, call.result, call.body)

    @group.command("status")
    @click.option("--kb-id", required=True, help="Knowledge base id")
    @click.option("--operation-id", required=True, help="Resumable crawler job id")
    @click.pass_context
    def status(ctx, kb_id, operation_id):
        """Read one bounded crawler/training status observation."""
        client = _client()
        call = _guard(ctx, lambda: client.crawl_status(
            _tenant(), knowledge_base_id=kb_id, operation_id=operation_id,
        ))
        if call is None:
            return
        _emit(ctx, call.result, call.body)

    @group.command("train")
    @click.option("--kb-id", required=True, help="Knowledge base id")
    @click.option("--operation-id", required=True, help="Crawler job id")
    @click.option("--url-id", "url_ids", multiple=True, required=True, help="Discovered url id")
    @click.pass_context
    def train(ctx, kb_id, operation_id, url_ids):
        """Train/discovered-page ingestion.  Training is a separate checkpoint."""
        client = _client()
        call = _guard(ctx, lambda: client.train_urls(
            _tenant(), knowledge_base_id=kb_id, operation_id=operation_id,
            url_ids=list(url_ids),
        ))
        if call is None:
            return
        _emit(ctx, call.result, call.body)

    @group.command("upload")
    @click.option("--kb-id", required=True, help="Knowledge base id")
    @click.option("--file", "file_path", required=True, type=click.Path(exists=True, dir_okay=False))
    @click.pass_context
    def upload(ctx, kb_id, file_path):
        """Upload one approved PDF/DOC/DOCX (multipart seam owned by WF01)."""
        client = _client()
        acceptance = _guard(ctx, lambda: client.upload_source_file(
            _tenant(), knowledge_base_id=kb_id, path=file_path,
        ))
        if acceptance is None:
            return
        click.echo(json.dumps({
            "accepted": acceptance.accepted,
            "upload_state": acceptance.upload_state,
            "ingestion_state": acceptance.ingestion_state,
            "training_state": acceptance.training_state,
            "attachment_state": acceptance.attachment_state,
            "content_sha256": acceptance.content_sha256,
            "byte_size": acceptance.byte_size,
            "http_status": acceptance.http_status,
            "provider_file_id": acceptance.provider_file_id,
        }, indent=2))
        if not acceptance.accepted:
            ctx.exit(1)

    @group.command("attach")
    @click.option("--agent-id", required=True, help="Native Conversation AI agent id")
    @click.option("--kb-id", required=True, help="Knowledge base id")
    @click.pass_context
    def attach(ctx, agent_id, kb_id):
        """Attach a knowledge base to the named native agent (union semantics)."""
        client = _client()
        outcome = _guard(ctx, lambda: client.attach_knowledge_base(
            _tenant(), agent_id=agent_id, knowledge_base_id=kb_id,
        ))
        if outcome is None:
            return
        click.echo(json.dumps({
            "state": outcome.state,
            "verified": outcome.verified,
            "previous_ids": list(outcome.previous_ids),
            "requested_ids": list(outcome.requested_ids),
        }, indent=2))
        if outcome.state != "attached":
            ctx.exit(1)

    @group.command("detach")
    @click.option("--agent-id", required=True, help="Native Conversation AI agent id")
    @click.option("--kb-id", required=True, help="Knowledge base id")
    @click.pass_context
    def detach(ctx, agent_id, kb_id):
        """Detach a knowledge base from one named agent only."""
        client = _client()
        outcome = _guard(ctx, lambda: client.detach_knowledge_base(
            _tenant(), agent_id=agent_id, knowledge_base_id=kb_id,
        ))
        if outcome is None:
            return
        click.echo(json.dumps({
            "state": outcome.state,
            "verified": outcome.verified,
            "previous_ids": list(outcome.previous_ids),
            "requested_ids": list(outcome.requested_ids),
        }, indent=2))
        if outcome.state != "detached":
            ctx.exit(1)

    @group.command("evaluate")
    @click.option("--cases", "cases_path", required=True, type=click.Path(exists=True, dir_okay=False),
                  help="JSON file containing retrieval cases")
    @click.option("--kb-id", required=True)
    @click.option("--agent-id", default=None)
    @click.pass_context
    def evaluate(ctx, cases_path, kb_id, agent_id):
        """Evaluate the five retrieval cases.  No interrogator is NOT RUN."""
        with open(cases_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        cases = [
            kb_api.RetrievalCase(
                case_id=str(item["case_id"]),
                kind=str(item["kind"]),
                question=str(item["question"]),
                expected_source_id=item.get("expected_source_id"),
                expected_answer_fragment=item.get("expected_answer_fragment"),
                conflict_source_id=item.get("conflict_source_id"),
                updated_source_id=item.get("updated_source_id"),
                stale_source_id=item.get("stale_source_id"),
                other_client_id=item.get("other_client_id"),
            )
            for item in payload
        ]
        report = _guard(ctx, lambda: kb_api.evaluate_retrieval(
            cases, knowledge_base_id=kb_id, agent_id=agent_id,
        ))
        if report is None:
            return
        click.echo(json.dumps({
            "state": report.state,
            "interrogator_used": report.interrogator_used,
            "reason": report.reason,
            "results": [
                {"case_id": item.case_id, "kind": item.kind, "state": item.state, "reason": item.reason}
                for item in report.results
            ],
        }, indent=2))
        if report.state != "verified":
            ctx.exit(1)

    return group


kb = build_kb_group()

__all__ = ["build_kb_group", "kb"]
