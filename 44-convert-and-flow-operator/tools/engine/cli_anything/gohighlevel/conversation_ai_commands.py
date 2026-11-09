"""CLI commands for native GHL Conversation AI - WF28.

This module is REGISTERED BY WF03 (``gohighlevel_cli.py`` is WF03's file).  It
adds one command group, ``conversation-ai``, and no other CLI surface:

    caf conversation-ai inventory
    caf conversation-ai get --agent-id <id>
    caf conversation-ai create --name <name> --channels sms,email \
        [--mode off] [--full-prompt <text>] [--logical-key <key>] \
        [--approval-ref <ref>]
    caf conversation-ai update --agent-id <id> --patch-file <json> \
        --logical-key <key> [--approval-ref <ref>]
    caf conversation-ai effective-prompt --agent-id <id>
    caf conversation-ai channels

The command never bypasses ``PublicGhlAdapter``: the capability gate, approval
seam, idempotency fingerprint and read-back all still run.  ``create`` only
accepts the non-sending mode ``off``; a mode change is a separate approved
``update``.  A primary-ownership field is refused by the adapter.

Exit: 0 the operation was accepted, 1 refused/denied, 2 usage or input error.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, Mapping, Optional, Sequence

from .public.auth import (
    AuthKind,
    resolve_auth,
    resolve_tenant_from_env,
)
from .public.conversation_ai import (
    CHANNEL_MAP,
    NATIVE_CHANNELS,
    NATIVE_MODES,
    UNSUPPORTED_CHANNELS,
    AgentSpec,
    ConversationAiAdapter,
    native_channel_for,
)
from .public.errors import ContractViolation, CredentialMissing
from .public.outbound_sender import CapturingTransport
from .public.transport import RequestsTransport

COMMAND = "conversation-ai"
_DESCRIPTION = "Native GHL Conversation AI agents (create off, read back, approve separately)"


def register(subparsers: Any) -> Any:
    """Attach the ``conversation-ai`` group to the CLI's subparser registry."""
    parser = subparsers.add_parser(COMMAND, help=_DESCRIPTION)
    commands = parser.add_subparsers(dest="conversation_ai_command", required=True)

    inventory = commands.add_parser("inventory", help="list native agents")
    inventory.set_defaults(conversation_ai_handler=_cmd_inventory)

    get = commands.add_parser("get", help="read one native agent")
    get.add_argument("--agent-id", required=True)
    get.set_defaults(conversation_ai_handler=_cmd_get)

    create = commands.add_parser("create", help="create a native agent in mode off")
    create.add_argument("--name", required=True)
    create.add_argument("--channels", required=True,
                        help="comma-separated Skill 38 channel names")
    create.add_argument("--mode", default="off", choices=list(NATIVE_MODES))
    create.add_argument("--full-prompt", default=None)
    create.add_argument("--personality", default=None)
    create.add_argument("--goal", default=None)
    create.add_argument("--instructions", default=None)
    create.add_argument("--logical-key", default=None)
    create.add_argument("--approval-ref", default=None)
    create.set_defaults(conversation_ai_handler=_cmd_create)

    update = commands.add_parser("update", help="patch one native agent")
    update.add_argument("--agent-id", required=True)
    update.add_argument("--patch-file", required=True)
    update.add_argument("--logical-key", required=True)
    update.add_argument("--approval-ref", default=None)
    update.set_defaults(conversation_ai_handler=_cmd_update)

    prompt = commands.add_parser("effective-prompt",
                                 help="show the prompt GHL actually generates from")
    prompt.add_argument("--agent-id", required=True)
    prompt.set_defaults(conversation_ai_handler=_cmd_effective_prompt)

    channels = commands.add_parser("channels", help="show the explicit channel map")
    channels.set_defaults(conversation_ai_handler=_cmd_channels)
    return parser


def default_client(_args: Any) -> ConversationAiAdapter:
    """Build the real adapter from the caller's env. Values are never printed."""
    tenant = resolve_tenant_from_env()
    auth = resolve_auth(
        kind=AuthKind.location_pit,
        location_id=tenant.location_id,
        prefer_engine_tenant=True,
    )
    from .public.adapter import PublicGhlAdapter

    transport = CapturingTransport(RequestsTransport())
    adapter = PublicGhlAdapter(auth=auth, transport=transport)
    return ConversationAiAdapter(adapter, tenant, transport=transport)


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _summary(result: Any) -> dict[str, Any]:
    status = getattr(result, "status", None)
    readback = getattr(result, "readback", None)
    return {
        "status": str(getattr(status, "value", status)),
        "operation_id": getattr(result, "operation_id", None),
        "receipt_id": getattr(result, "receipt_id", None),
        "error": dict(getattr(result, "error", None) or {}),
        "readback": str(getattr(getattr(readback, "result", None), "value",
                                getattr(readback, "result", None)))
        if readback is not None else None,
    }


def _change_summary(change: Any) -> dict[str, Any]:
    payload = _summary(change.operation)
    payload.update({
        "agent_id": change.agent_id,
        "mode": change.mode,
        "native_channels": list(change.native_channels),
        "effective_prompt": dict(change.effective_prompt),
        "snapshot_digest": change.snapshot_digest,
        "readback_expect": dict(change.readback_expect),
    })
    return payload


def _client(args: Any, factory: Optional[Callable[[Any], Any]]) -> Any:
    return (factory or default_client)(args)


def _cmd_inventory(args: Any, factory: Optional[Callable[[Any], Any]] = None) -> int:
    result = _client(args, factory).inventory()
    _emit({"command": "inventory", **_summary(result)})
    return 0 if _summary(result)["status"] == "ok" else 1


def _cmd_get(args: Any, factory: Optional[Callable[[Any], Any]] = None) -> int:
    result = _client(args, factory).read(args.agent_id)
    _emit({"command": "get", **_summary(result)})
    return 0 if _summary(result)["status"] == "ok" else 1


def _cmd_create(args: Any, factory: Optional[Callable[[Any], Any]] = None) -> int:
    channels = [part.strip() for part in str(args.channels).split(",")
                if part.strip()]
    logical_key = args.logical_key or "conversation-ai:create:%s" % args.name
    spec = AgentSpec(
        name=args.name, channels=channels, mode=args.mode,
        full_prompt=args.full_prompt, personality=args.personality,
        goal=args.goal, instructions=args.instructions,
    )
    change = _client(args, factory).create(
        spec, logical_key=logical_key, approval=args.approval_ref)
    _emit({"command": "create", **_change_summary(change)})
    return 0 if change.ok else 1


def _cmd_update(args: Any, factory: Optional[Callable[[Any], Any]] = None) -> int:
    with open(args.patch_file, encoding="utf-8") as handle:
        patch = json.load(handle)
    if not isinstance(patch, Mapping):
        raise ContractViolation("conversation_patch_invalid",
                                detail={"reason": "patch file must be a JSON object"})
    change = _client(args, factory).update(
        args.agent_id, patch, logical_key=args.logical_key,
        approval=args.approval_ref)
    _emit({"command": "update", **_change_summary(change)})
    return 0 if change.ok else 1


def _cmd_effective_prompt(args: Any,
                          factory: Optional[Callable[[Any], Any]] = None) -> int:
    prompt = _client(args, factory).effective_prompt_of(args.agent_id)
    _emit({"command": "effective-prompt", "agent_id": args.agent_id,
           "effective_prompt": prompt})
    return 0 if prompt.get("source") != "unreadable" else 1


def _cmd_channels(_args: Any,
                  _factory: Optional[Callable[[Any], Any]] = None) -> int:
    _emit({
        "command": "channels",
        "native": list(NATIVE_CHANNELS),
        "map": dict(CHANNEL_MAP),
        "refused": dict(UNSUPPORTED_CHANNELS),
    })
    return 0


def run(args: Any, *, client_factory: Optional[Callable[[Any], Any]] = None) -> int:
    """Dispatch one parsed ``conversation-ai`` command. WF03 calls this."""
    handler = getattr(args, "conversation_ai_handler", None)
    if handler is None:
        sys.stderr.write("conversation-ai: a subcommand is required\n")
        return 2
    try:
        return int(handler(args, client_factory))
    except CredentialMissing as exc:
        sys.stderr.write("conversation-ai: credential unavailable: %s\n" % exc)
        return 2
    except ContractViolation as exc:
        _emit({"status": "refused", "rule": exc.rule,
               "operation_id": getattr(exc, "operation_id", None),
               "detail": dict(getattr(exc, "detail", {}) or {})})
        return 1
    except (OSError, UnicodeError, ValueError) as exc:
        sys.stderr.write("conversation-ai: %s\n" % exc)
        return 2


__all__ = ["COMMAND", "default_client", "register", "run"]
