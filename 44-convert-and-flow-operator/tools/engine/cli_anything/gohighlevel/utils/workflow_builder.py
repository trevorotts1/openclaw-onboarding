"""GHL workflow builder — step builders, linker, and campaign builder.

Adapted from ghl-superspeed-v3-main/lib/engine.py (2026-03-25).
Creates workflows as DRAFT (never auto-published).

EXPERIMENTAL: Gated behind --experimental flag in CLI.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

from cli_anything.gohighlevel.utils.ghl_internal_client import InternalGHLClient
from cli_anything.gohighlevel.utils.safety_gate import draft_only_active_flag
from cli_anything.gohighlevel.utils.write_lock import WriteLock
from cli_anything.gohighlevel.utils.workflow_timing import plan_timing

# ── Parallel-build worker cap ────────────────────────────────────────────────
# Lowered from the original hard-coded 10 to reduce burst pressure on the shared
# GHL rate bucket (matches the internal adapter's _DEFAULT_MAX_WORKERS=3).
# WriteLock serialises writes ACROSS builds but NOT within a single multi-workflow
# build, so this cap is what bounds one build's concurrent pipelines. Override
# with CAF_INTERNAL_MAX_WORKERS (the same env var the adapter honours).
_DEFAULT_BUILD_MAX_WORKERS = 3


def _build_max_workers() -> int:
    """Resolve the parallel-build worker count from CAF_INTERNAL_MAX_WORKERS.

    Falls back to _DEFAULT_BUILD_MAX_WORKERS when unset/invalid, and never
    returns < 1 (ThreadPoolExecutor requires max_workers >= 1).
    """
    raw = os.environ.get("CAF_INTERNAL_MAX_WORKERS", "").strip()
    try:
        n = int(raw)
    except (ValueError, TypeError):
        return _DEFAULT_BUILD_MAX_WORKERS
    return n if n >= 1 else _DEFAULT_BUILD_MAX_WORKERS


# ── Public V4 route selection (GU-013) ───────────────────────────────────────
#
# The public V4 adapter is PRIMARY only when that operation's capability row is
# enabled (freeze 3.2).  Otherwise the Skill 44 private rail keeps today's
# behaviour, unchanged and explicitly named.  The route is chosen BEFORE any
# transport call and is never switched afterwards: an ``unknown_outcome`` from a
# public write must be reconciled through the adapter, never retried through the
# private rail (freeze 2.4).

WORKFLOW_ROUTE_PUBLIC = "public_v4"
WORKFLOW_ROUTE_PRIVATE = "skill44_private_fallback"


@dataclass(frozen=True)
class WorkflowRoute:
    """One named route decision: public primary or the explicit private fallback."""

    operation: str
    operation_id: Optional[str]
    route: str
    reason: str
    blocked: Any = None

    @property
    def public(self) -> bool:
        return self.route == WORKFLOW_ROUTE_PUBLIC

    def as_evidence(self) -> dict:
        out = {
            "operation": self.operation,
            "operation_id": self.operation_id,
            "route": self.route,
            "reason": self.reason,
        }
        block = self.blocked
        if block is not None:
            out["activation_blocked"] = block.as_evidence()
        return out


def _v4_operation_map():
    from cli_anything.gohighlevel.public.workflow_v4 import OPERATION_MAP
    return OPERATION_MAP


def workflow_operation_id(operation: str) -> Optional[str]:
    """Frozen public operation id for a workflow surface, or None for a named gap."""
    return _v4_operation_map().get(str(operation))


def workflow_route(v4: Any, operation: str, *, tenant: Any = None) -> WorkflowRoute:
    """Choose public primary or the named private fallback for one surface.

    Never guesses: an absent adapter, an absent frozen row, a disabled
    capability, or an unbound probe all fall back, each says why (GHL-168 F2).
    """
    key = str(operation)
    if v4 is None:
        return WorkflowRoute(
            key, None, WORKFLOW_ROUTE_PRIVATE,
            "public V4 adapter unavailable; using the named Skill 44 private fallback",
        )
    try:
        operation_id = _v4_operation_map().get(key)
    except Exception as exc:  # noqa: BLE001 - an unimportable package is a named fallback
        return WorkflowRoute(
            key, None, WORKFLOW_ROUTE_PRIVATE,
            "public V4 package unavailable (%s); using the named Skill 44 private fallback"
            % type(exc).__name__,
        )
    if operation_id is None:
        return WorkflowRoute(
            key, None, WORKFLOW_ROUTE_PRIVATE,
            "no frozen public row for %r; using the named Skill 44 private fallback" % key,
        )
    capability = v4.capability(key, tenant=tenant)
    if capability.enabled:
        return WorkflowRoute(
            key, operation_id, WORKFLOW_ROUTE_PUBLIC,
            "capability row enabled for this operation",
        )
    return WorkflowRoute(
        key, operation_id, WORKFLOW_ROUTE_PRIVATE,
        "capability disabled; using the named Skill 44 private fallback",
        capability.activation_blocked,
    )


def load_public_v4(
    location_id: str,
    *,
    env: Optional[Mapping[str, str]] = None,
    transport: Any = None,
    capability: Any = None,
):
    """Build ``WorkflowV4Adapter`` over the frozen public adapter.

    Returns ``(adapter, reason)``.  ``adapter`` is None when the public
    credential class cannot be resolved; the caller then keeps the named
    private fallback.  The default capability gate is default-deny, so building
    the adapter can never send a request on its own.
    """
    try:
        from cli_anything.gohighlevel.public.adapter import PublicGhlAdapter
        from cli_anything.gohighlevel.public.auth import AuthKind, resolve_auth
        from cli_anything.gohighlevel.public.workflow_v4 import WorkflowV4Adapter
    except Exception as exc:  # noqa: BLE001
        return None, "public V4 package unavailable: %s" % type(exc).__name__
    try:
        auth = resolve_auth(
            kind=AuthKind.location_pit, location_id=location_id, env=env
        )
    except Exception as exc:  # noqa: BLE001
        return None, "public credential unavailable: %s" % type(exc).__name__
    public = PublicGhlAdapter(
        auth=auth, transport=transport, capability=capability
    )
    return WorkflowV4Adapter(public=public), "public adapter built; gate is default-deny"


def public_approval() -> Any:
    """Approval seam for a public V4 write: the existing gate token, never its value.

    Freeze 3.2 rule 4 requires an explicit approval token on every V4 write.
    A ``ZHC-`` name is standing approval for the private rail only; it is not a
    V4 approval token and is not substituted here.
    """
    try:
        from cli_anything.gohighlevel.public.adapter import ApprovalRef
    except Exception:  # noqa: BLE001
        return None
    if os.environ.get("CAF_APPROVAL_TOKEN", "").strip():
        return ApprovalRef(ref="CAF_APPROVAL_TOKEN", kind="gate_token")
    return None


def intent_from_definition(
    current: Mapping[str, Any], desired: Mapping[str, Any]
) -> Any:
    """Explicit ``Intent`` that turns ``current`` into ``desired``.

    Top-level fields present in ``desired`` are set; nodes are upserted by
    identity and identities missing from ``desired`` become explicit removals,
    so the update request can never delete a step by omission.  ``version`` is
    never set here -- it is system-owned and carried by the adapter.

    An id-less node in ``current`` is REFUSED (``current_node_identity_missing``):
    it has no identity to put in ``remove_*``, so excluding it from the present
    set would make removing it undetectable.  Refusing is the only answer that
    cannot silently drop a live node.

    ponytail: a top-level key that exists in ``current`` and is absent from
    ``desired`` cannot be removed through ``Intent`` (it has no remove_fields).
    Add one when a real plan needs top-level deletion.
    """
    from cli_anything.gohighlevel.public.errors import ContractViolation
    from cli_anything.gohighlevel.public.workflow_v4_intent import (
        COLLECTIONS,
        Intent,
        node_identity,
    )

    if not isinstance(current, Mapping) or not isinstance(desired, Mapping):
        raise ContractViolation("definition_invalid")
    plan: dict[str, Any] = {
        "set_fields": {
            str(key): value
            for key, value in desired.items()
            if str(key) not in COLLECTIONS and str(key) != "version"
        }
    }
    for kind in COLLECTIONS:
        current_nodes = _definition_nodes(current, kind)
        loose = [index for index, node in enumerate(current_nodes) if _identity(node) is None]
        if loose:
            raise ContractViolation(
                "current_node_identity_missing",
                detail={"kind": kind, "count": len(loose)},
            )
        wanted = _definition_nodes(desired, kind)
        present = {
            identity
            for identity in (_identity(node) for node in current_nodes)
            if identity is not None
        }
        seen: set = set()
        for node in wanted:
            identity = node_identity(node)
            if identity is None:
                raise ContractViolation(
                    "intent_node_identity_missing", detail={"kind": kind}
                )
            seen.add(identity)
        plan["upsert_" + kind] = tuple(wanted)
        plan["remove_" + kind] = tuple(sorted(present - seen))
    return Intent(**plan)


def _definition_nodes(definition: Mapping[str, Any], kind: str) -> tuple:
    nodes = definition.get(kind)
    if nodes is None:
        return ()
    if not isinstance(nodes, (list, tuple)):
        raise ValueError("definition collection %r is not a list" % kind)
    return tuple(nodes)


def _identity(node: Any) -> Optional[str]:
    from cli_anything.gohighlevel.public.workflow_v4_intent import node_identity
    return node_identity(node)


# ── Verified Action Types (56 confirmed via save API 2026-03-22) ──────────

VERIFIED_ACTIONS = frozenset([
    "add_contact_tag", "remove_contact_tag", "update_contact_field",
    "create_update_contact", "assign_user", "remove_assigned_user",
    "edit_conversation", "dnd_contact", "add_notes", "task-notification",
    "find_contact", "sms", "email", "call", "voicemail", "messenger", "gmb",
    "internal_notification", "instagram-dm", "ig_interactive_messenger",
    "fb_interactive_messenger", "respond_on_comment", "review_request",
    "wait", "if_else", "goto", "transition", "workflow_split", "workflow_goal",
    "add_to_workflow", "remove_from_workflow", "remove_from_all_workflows",
    "update_custom_value", "drip", "chatgpt", "conversation_ai",
    "create_opportunity", "find_opportunity", "remove_opportunity",
    "webhook", "custom_webhook", "google_sheets", "slack_message",
    "custom_code", "math_operation", "text_formatter", "number_formatter",
    "datetime_formatter", "array_functions", "ivr_gather", "ivr_connect_call",
    "facebook_conversion_api", "stripe_one_time_charge",
    "update_appointment_status", "membership_grant_offer",
    "membership_revoke_offer",
])


# ── Email Formatter ───────────────────────────────────────────────────────

def dm_email(text: str) -> str:
    """Convert plain text to Dan Martell style HTML email."""
    lines = text.strip().split("\n")
    html_parts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
        html_parts.append(
            f'<p style="margin:0 0 12px 0;line-height:1.75;'
            f'font-size:16px;font-family:arial,helvetica,sans-serif;'
            f'color:#000;">{line}</p>'
        )
    return "".join(html_parts)


# ── Step Builders ─────────────────────────────────────────────────────────

def _uid() -> str:
    return str(uuid.uuid4())


def _resolve_sms_from_number(explicit: str = "") -> str:
    """Resolve the SMS From-number.

    WF-12 gap fix: the SMS step previously carried NO ``fromNumber`` field at
    all, so the WF-12 mechanical assertion had nothing to read and a build
    could silently ship an SMS node with no From-number (silent send failure).

    We do NOT fabricate a server-side default we cannot prove. Resolution order:
      1. An explicit ``from_number=`` kwarg passed to ``sms_step``.
      2. ``CAF_SMS_FROM_NUMBER`` (the client's configured default From-number).
      3. ``GOHIGHLEVEL_SMS_FROM_NUMBER`` (alias).
      4. "" (empty) — left for GHL's location-default From-number resolution at
         SEND time. An empty value is intentionally allowed here so existing
         builds are unchanged; the WF-12 QC gate then surfaces the empty From
         on any LIVE/published workflow for human/client confirmation rather
         than blocking the build.

    The KEY is always emitted (even when empty) so WF-12 can assert presence.
    """
    if explicit and explicit.strip():
        return explicit.strip()
    for var in ("CAF_SMS_FROM_NUMBER", "GOHIGHLEVEL_SMS_FROM_NUMBER"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return ""


def sms_step(name: str, body: str, from_number: str = "", **kw: Any) -> dict:
    # WF-12: always emit a fromNumber key (resolved from kwarg/env, else empty
    # for GHL location-default send-time resolution) so the QC gate can assert
    # presence and surface an empty From on a published SMS node.
    return {
        "id": _uid(), "type": "sms", "name": f"SMS: {name}",
        "attributes": {
            "body": body, "attachments": [],
            "fromNumber": _resolve_sms_from_number(from_number),
        }, **kw,
    }


def email_step(name: str, subject: str, text: str, from_name: str = "", **kw: Any) -> dict:
    html = dm_email(text)
    return {
        "id": _uid(), "type": "email", "name": f"Email: {name}",
        "attributes": {
            "subject": subject, "body": html, "html": html,
            "fromName": from_name, "attachments": [], "conditions": [],
            "trackingOptions": {
                "hasTrackingLinks": False, "hasUtmTracking": False, "hasTags": False,
            },
        }, **kw,
    }


def wait_step(name: str, value: int, unit: str = "days", **kw: Any) -> dict:
    # GHL uses inconsistent unit strings: "minutes" (plural), "hour" (SINGULAR), "days" (plural)
    api_unit = {"minutes": "minutes", "hours": "hour", "hour": "hour", "days": "days"}.get(unit, unit)
    unit_label = {"minutes": "Minutes", "hour": "Hour", "hours": "Hours", "days": "Days"}.get(unit, unit.title())
    display = f"Wait {value} {unit_label}"
    return {
        "id": _uid(), "type": "wait", "name": display,
        "attributes": {
            "type": "time",
            "startAfter": {"type": api_unit, "value": value, "when": "after"},
            "name": display, "cat": "",
            "isHybridAction": True, "hybridActionType": "wait",
            "convertToMultipath": False, "transitions": [],
        }, "cat": "", **kw,
    }


def tag_step(name: str, tags: list[str], remove: bool = False, **kw: Any) -> dict:
    t = "remove_contact_tag" if remove else "add_contact_tag"
    return {"id": _uid(), "type": t, "name": name, "attributes": {"tags": tags}, **kw}


def webhook_step(name: str, url: str, method: str = "POST", data: list | None = None, **kw: Any) -> dict:
    return {
        "id": _uid(), "type": "webhook", "name": name,
        "attributes": {"method": method, "url": url, "customData": data or [], "headers": []},
        **kw,
    }


def ai_step(name: str, prompt: str, model: str = "gpt-4o", **kw: Any) -> dict:
    # NOTE (SK1-47): this is a GHL "ChatGPT" workflow ACTION node. The model runs on
    # GoHighLevel's OWN platform (GHL bills its Conversation-AI credits) — it is NOT
    # the client's sovereign OpenClaw model, so client model-sovereignty does not
    # govern this platform field. Reject an Anthropic/Claude id here anyway: GHL's
    # ChatGPT node cannot run one, so a claude/anthropic value is a mis-wiring, not a
    # valid GHL platform model.
    _m = str(model or "").lower()
    if "anthropic" in _m or "claude" in _m:
        raise ValueError(
            f"GHL ChatGPT action model {model!r} is invalid: the GHL platform ChatGPT "
            "node does not run Anthropic/Claude models. Use a GHL-supported ChatGPT "
            "model id (e.g. gpt-4o). This node is a GHL-platform field, not the "
            "client's sovereign OpenClaw model."
        )
    return {
        "id": _uid(), "type": "chatgpt", "name": name,
        "attributes": {
            "type": "chatgpt", "event": "simple-prompt", "model": model,
            "promptText": prompt, "actionType": "custom",
            "temperature": "0.2", "memoryKey": "action",
        }, **kw,
    }


# ── Action ID normalization (A16 layer-7 ruled fix, 2026-10-18) ─────────────
#
# The internal backend's step-save validation requires every action ("template")
# id to be a UUID ("Action validation failed: ... ID: Invalid uuid", observed
# live 2026-10-18 on a plan whose actions carried human-readable slug ids).
# Plan-supplied templates may therefore carry non-UUID author ids.  At build
# time the builder mints a deterministic UUID for each non-UUID action id:
# UUIDv5 over a FIXED namespace with the name "<location_id>:<original id>".
# Determinism is the idempotency contract: every re-run of the same plan at the
# same location derives the identical UUID set, so read-backs and re-builds
# agree byte-for-byte.  The namespace constant below is part of that contract —
# NEVER change it, or every previously derived id changes with it.
_ACTION_ID_NAMESPACE = uuid.UUID("e55e7d58-e496-48c8-afab-ba8f408598b0")


def _is_uuid(value: Any) -> bool:
    """True iff value is a string that parses as a UUID."""
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def normalize_action_ids(templates: list[dict], location_id: str) -> list[dict]:
    """Return templates with non-UUID action ids replaced by deterministic
    UUIDv5 mints (see the section note above).

    Every exact string occurrence of a replaced id anywhere in the template
    structures (the "id" field itself plus link references such as "next" and
    "parentKey", and any nested reference) is remapped to the same minted UUID,
    so the linked chain stays consistent.  Templates whose ids are already
    valid UUIDs pass through untouched.
    """
    mapping: dict[str, str] = {}
    for step in templates:
        original = step.get("id") if isinstance(step, dict) else None
        if isinstance(original, str) and original and not _is_uuid(original):
            mapping[original] = str(
                uuid.uuid5(_ACTION_ID_NAMESPACE, f"{location_id}:{original}")
            )
    if not mapping:
        return templates

    def _remap(node: Any) -> Any:
        if isinstance(node, str):
            return mapping.get(node, node)
        if isinstance(node, list):
            return [_remap(item) for item in node]
        if isinstance(node, dict):
            return {key: _remap(val) for key, val in node.items()}
        return node

    return [_remap(step) for step in templates]


# ── Step Linker ───────────────────────────────────────────────────────────

def link_steps(steps: list[dict]) -> list[dict]:
    """Auto-link steps with next/parentKey and set order."""
    linked = []
    for i, step in enumerate(steps):
        step = {**step}
        step["order"] = i
        step["parentKey"] = linked[i - 1]["id"] if i > 0 else None
        if i < len(steps) - 1:
            step["next"] = steps[i + 1]["id"]
        linked.append(step)
    return linked


# ── Validation ────────────────────────────────────────────────────────────

def validate_campaign(campaign: dict) -> list[str]:
    """Pre-flight validation. Returns list of errors (empty = valid)."""
    errors = []
    for key, wf in campaign.items():
        if not isinstance(wf, dict):
            errors.append(f"Workflow {key}: expected an object")
            continue
        if "timing" in wf:
            try:
                timing = wf["timing"]
                if not isinstance(timing, dict):
                    raise ValueError("timing must be an object")
                outline = plan_timing(timing.get("requirements"), timing.get("anchors", {}))
                if outline["requires_event_start"]:
                    raise ValueError(
                        "event timing requires Set event start time plus event-relative Waits; "
                        "this API adapter has no verified event-start payload. Execute the "
                        "timing outline through the managed browser per references/workflow-timing.md; "
                        "do not strip timing metadata or substitute duration waits")
                for node in outline["nodes"]:
                    matches = [s for s in wf.get("templates", [])
                               if isinstance(s, dict) and s.get("id") == node["step_id"]]
                    if len(matches) != 1:
                        raise ValueError(f"timing step {node['step_id']} must match exactly one template")
                    step = matches[0]
                    attrs = step.get("attributes", {})
                    start = attrs.get("startAfter", {})
                    unit = {"hour": "hours"}.get(start.get("type"), start.get("type"))
                    if (step.get("type") != "wait" or attrs.get("type") != "time"
                            or start.get("when") != "after" or unit != node["unit"]
                            or start.get("value") != node["offset"]):
                        raise ValueError(f"timing step {node['step_id']} does not match the requested delay")
            except (ValueError, TypeError, AttributeError) as exc:
                errors.append(f"Workflow {key}: {exc}")
        if "name" not in wf:
            errors.append(f"Workflow {key}: missing 'name'")
        if "templates" not in wf:
            errors.append(f"Workflow {key}: missing 'templates'")
            continue
        for i, step in enumerate(wf["templates"]):
            if "type" not in step:
                errors.append(f"Workflow {key}, step {i}: missing 'type'")
            elif step["type"] not in VERIFIED_ACTIONS:
                errors.append(f"Workflow {key}, step {i}: unverified type '{step['type']}'")
            if "id" not in step:
                errors.append(f"Workflow {key}, step {i}: missing 'id'")
            if "name" not in step:
                errors.append(f"Workflow {key}, step {i}: missing 'name'")
    return errors


# ── Existing-state indexing (idempotency) ──────────────────────────────────

def _index_existing(
    raw: Union[dict, list, None],
) -> Optional[tuple[dict[str, str], dict[str, str], dict[str, str]]]:
    """Parse a GET /workflow/{loc} listing into name->id maps for reuse checks.

    Returns (workflow_name_to_id, folder_name_to_id, workflow_name_to_parent_id)
    on success (empty dicts mean "confirmed nothing exists yet" — a valid,
    common result). Returns None when the response can't be read as a listing
    at all (missing, transport `_error`, or a shape with no recognizable item
    collection) — callers MUST treat None as "existing state unknown" and
    abort rather than build blind, since guessing wrong here is exactly the
    bug this function exists to prevent.

    VERIFIED response shape (captured against a live backend): a BARE LIST of
    item dicts. Each item carries `id` and `_id` (identical), `name`, `type`
    (observed value "workflow"), and `parentId` (the containing folder's id).
    The dict-wrapped branches below are retained as defensive tolerance for
    other deployments, but the bare list is what production returns.

    IMPORTANT LIMITATION — folders are NOT listed. The live response contains
    workflow items only; no item with type == "directory" is ever returned,
    even when folders demonstrably exist (their ids appear as the workflows'
    `parentId`). The public API (`GET /workflows/?locationId=`) is worse still
    — it omits `type` and `parentId` entirely. There is no folder-listing
    endpoint on either transport, so `folder_name_to_id` is populated only on
    deployments that do return directory items, and is empty in production.
    Folder de-duplication therefore CANNOT be done by name; the caller derives
    it from `workflow_name_to_parent_id` instead. Do not "fix" the empty folder
    map by assuming no folder exists — that is the duplicate-folder bug.

    Item classification: an item is a folder when item["type"] == "directory"
    — the exact value this module already POSTs when creating a folder — and
    a workflow otherwise. Items missing "name" or "id"/"_id" are skipped.
    """
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if raw.get("_error"):
            return None
        items = []
        found_key = False
        for key in ("workflows", "folders", "data", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                items.extend(val)
                found_key = True
        if not found_key:
            return None
    else:
        return None

    workflow_ids: dict[str, str] = {}
    folder_ids: dict[str, str] = {}
    workflow_parents: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        item_id = item.get("id") or item.get("_id")
        if not name or not item_id:
            continue
        if item.get("type") == "directory":
            folder_ids[name] = item_id
        else:
            workflow_ids[name] = item_id
            parent = item.get("parentId")
            if parent:
                workflow_parents[name] = parent
    return workflow_ids, folder_ids, workflow_parents


# ── Campaign Builder ──────────────────────────────────────────────────────

class CampaignBuilder:
    """Builds complete GHL campaigns via internal API.

    All workflows are created as DRAFT (never auto-published).
    Uses ThreadPoolExecutor for parallel workflow creation.
    """

    def __init__(self, client: InternalGHLClient, *, v4: Any = None):
        self.client = client
        self.loc = client.location_id
        # Public V4 adapter (GU-013).  None means "not wired": every workflow
        # surface then keeps the existing private rail, which is the named
        # fallback rather than an implicit default.
        self.public_v4 = v4
        self.stats: dict[str, Any] = {
            "workflows_created": 0,
            "steps_saved": 0,
            "triggers_created": 0,
            "errors": [],
            # Non-fatal caveats the operator must still see — chiefly the
            # folder-idempotency limitation (this API exposes no folder
            # listing, so a created folder cannot be proven unique). These are
            # NOT errors and must not fail the build, but they must never be
            # silent either: a build that quietly implies it de-duplicated
            # folders when it could not is the false-success failure mode this
            # module already got burned by once.
            "notes": [],
            "route": {},
            "start_time": 0.0,
            "end_time": 0.0,
        }

    def route_for(self, operation: str) -> WorkflowRoute:
        """Record and return the named route for one workflow surface."""
        route = workflow_route(self.public_v4, operation, tenant=self.loc)
        self.stats.setdefault("route", {})[operation] = route.as_evidence()
        return route

    def _v4_create_blocker(
        self,
        wf_def: dict,
        *,
        folder_name: Optional[str],
        requested_folder_id: Optional[str],
    ) -> Optional[str]:
        """Why this plan keeps the private create rail, or None when V4 fits.

        These are pre-flight mapping limits, not transport failures: the route
        is still decided before anything is sent.
        """
        if wf_def.get("tag"):
            return (
                "plan carries a contact_tag trigger; the V4 trigger node mapping "
                "is unverified, using the named Skill 44 private fallback"
            )
        if requested_folder_id:
            return (
                "explicit folder id has no documented V4 create field, using the "
                "named Skill 44 private fallback (pass --folder name for the "
                "public rail)"
            )
        if not folder_name:
            return (
                "no folder name to pass to the V4 create body, using the named "
                "Skill 44 private fallback"
            )
        return None

    def _create_workflow_public(
        self,
        key: str,
        wf_name: str,
        templates: list,
        folder_name: str,
    ) -> tuple:
        """Create one workflow through the public V4 adapter.

        Returns the same tuple shape as ``_create_workflow``.  A non-ok result
        is recorded and returned as a failure: there is NO fallback after a
        transport attempt, least of all after ``unknown_outcome`` (freeze 2.4).

        ponytail: the plan's ``templates`` are sent as the V4 ``actions`` array.
        The V4 action-node schema beyond id/type/name/attributes is unverified
        (B-V4-S); the capability gate cannot be enabled until an operator
        records production contract evidence, so this path is unreachable in
        production before that evidence exists.
        """
        from cli_anything.gohighlevel.public.auth import TenantBinding
        from cli_anything.gohighlevel.public.result import Status

        definition: dict[str, Any] = {"name": wf_name, "actions": list(templates)}
        if folder_name:
            definition["folderName"] = folder_name
            definition["createFolderIfMissing"] = True
        result = self.public_v4.create_workflow(
            tenant=TenantBinding(location_id=self.loc, source="request"),
            definition=definition,
            approval=public_approval(),
            attempt=1,
        )
        if result.status is Status.unknown_outcome:
            self.stats["errors"].append(
                f"{wf_name}: public V4 create returned unknown_outcome "
                f"(receipt {result.receipt_id}) — reconcile before any retry; "
                "the private fallback was NOT used."
            )
            return key, None, False, False, None
        if result.status is not Status.ok:
            self.stats["errors"].append(
                f"{wf_name}: public V4 create refused "
                f"({result.status.value}, receipt {result.receipt_id}) — "
                "the private fallback was NOT used."
            )
            return key, None, False, False, None
        workflow_v4 = dict(result.evidence.get("workflow_v4") or {})
        wf_id = workflow_v4.get("workflow_id")
        if not wf_id:
            self.stats["errors"].append(
                f"{wf_name}: public V4 create returned ok without a workflow id "
                f"(receipt {result.receipt_id}) — reconcile before any retry."
            )
            return key, None, False, False, None
        return key, str(wf_id), True, False, None

    def build(
        self,
        campaign: dict,
        folder_name: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> dict:
        """Build an entire campaign. Returns stats dict.

        Pass `folder_id` to drop the campaign into an existing folder; pass
        `folder_name` to create a new folder. Exactly one is required.

        Idempotent: a repeated call reuses an existing folder with the same
        name instead of creating a duplicate, and refuses (via stats["errors"])
        to touch a campaign workflow whose name already exists rather than
        silently duplicating or silently modifying it. See `_index_existing`.

        Serialization: the entire build is wrapped in a WriteLock for the
        location so that concurrent builds to the same location are
        serialized — second build waits for the first to complete before
        starting any internal-API writes (AC 21).
        """
        with WriteLock(self.loc):
            return self._build_locked(campaign, folder_name=folder_name, folder_id=folder_id)

    def _build_locked(
        self,
        campaign: dict,
        folder_name: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> dict:
        """Internal build implementation (called under WriteLock)."""
        self.stats["start_time"] = time.time()
        # Remember whether the caller pinned an explicit folder id: the V4
        # create contract has no folder-id field, so that request keeps the
        # named private fallback (a name-based folder can be passed instead).
        requested_folder_id = folder_id

        # Pre-flight validation
        errors = validate_campaign(campaign)
        if errors:
            self.stats["errors"].extend(errors)
            self.stats["end_time"] = time.time()
            return self.stats  # Invalid timing/steps must never reach GET/POST.

        # Idempotency pre-check — fetch the location's existing workflow/folder
        # listing ONCE per build() call (not once per workflow, to avoid N extra
        # API calls), before any create POST fires.  A repeated build with no
        # pre-existence check was unconditionally POSTing a new folder/workflow
        # every run; this is what let one morning's re-runs produce duplicate
        # workflows and 7 duplicate folders.  If we can't determine what
        # already exists, we FAIL LOUD and abort rather than risk creating
        # duplicates blind — the exact failure mode this fix targets.
        existing = _index_existing(self.client.request("GET", f"/workflow/{self.loc}"))
        if existing is None:
            self.stats["errors"].append(
                "Could not read the existing workflow/folder list before "
                "building (idempotency pre-check failed) — aborting instead "
                "of risking duplicate creation. Retry, or check GHL "
                "internal-API connectivity."
            )
            self.stats["end_time"] = time.time()
            return self.stats
        existing_workflow_ids, existing_folder_ids, existing_workflow_parents = existing

        # Resolve folder: reuse existing if folder_id given, else look up by
        # name and reuse it, else create.  Reuse is the safe default for a
        # folder — it's a pure organizational container, so silently reusing
        # one that already carries the target name can't corrupt anything a
        # human built (unlike reusing a workflow — see the collision check
        # below).
        #
        # When the public V4 create capability is enabled, the folder is passed
        # as ``folderName`` + ``createFolderIfMissing`` in the create body, so
        # no private folder POST fires.  A caller-pinned folder id cannot be
        # expressed that way, and a plan carrying a contact_tag trigger cannot
        # use the public route, so both keep the private folder + create rail.
        campaign_has_tag = any(
            isinstance(value, dict) and value.get("tag")
            for value in campaign.values()
        )
        folder_public_only = (
            self.route_for("create").public
            and not campaign_has_tag
            and bool(folder_name)
            and requested_folder_id is None
        )
        if not folder_id and folder_public_only:
            self.stats.setdefault("notes", []).append(
                f"Folder '{folder_name}' is created by the public V4 create body "
                "(folderName + createFolderIfMissing); no private folder POST."
            )
        elif not folder_id:
            if not folder_name:
                self.stats["errors"].append(
                    "CampaignBuilder.build requires folder_id or folder_name"
                )
                self.stats["end_time"] = time.time()
                return self.stats
            folder_id = existing_folder_ids.get(folder_name)
            if not folder_id:
                # Name lookup fails in production: the listing never returns
                # directory items (see _index_existing). Derive the folder
                # instead — if any workflow from THIS campaign already exists,
                # it is already sitting in the folder a previous run created,
                # so reuse its parentId. This is what actually stops the
                # re-run-creates-another-folder bug.
                for key in campaign:
                    wf_name = campaign[key].get("name") if isinstance(campaign[key], dict) else None
                    if wf_name and wf_name in existing_workflow_parents:
                        folder_id = existing_workflow_parents[wf_name]
                        self.stats.setdefault("notes", []).append(
                            f"Reused folder {folder_id} derived from existing "
                            f"workflow '{wf_name}' (folders are not listable "
                            f"by name on this API)."
                        )
                        break
            if not folder_id:
                # Genuinely could not determine whether a folder of this name
                # exists — no directory listing, and no campaign workflow
                # already present to derive from. Creating is the only option,
                # but say so plainly: this build canNOT claim it de-duplicated
                # folders, and a folder named `folder_name` may already exist.
                self.stats.setdefault("notes", []).append(
                    f"Created a new folder '{folder_name}' WITHOUT being able "
                    f"to confirm no folder of that name already exists — this "
                    f"API exposes no folder listing. If duplicates appear, "
                    f"remove them in the GHL UI and pass folder_id explicitly."
                )
                # Bug 2a — the folder-creation POST omitted workflow_name, so the
                # safety gate saw an empty name and the ZHC- standing-approval check
                # (safety_gate._is_approved) always failed for it: a ZHC- *folder*
                # name was forced to demand CAF_APPROVAL_TOKEN even though a ZHC-
                # *workflow* name in the very same build was standing-approved.
                # Pass folder_name as the gate's workflow_name so ZHC- folder names
                # carry standing approval exactly like ZHC- workflow names.  The
                # gate's behaviour is unchanged for non-ZHC names (still requires a
                # token).
                folder = self.client.request(
                    "POST", f"/workflow/{self.loc}",
                    {"name": folder_name, "type": "directory"},
                    workflow_name=folder_name,
                )
                folder_id = folder.get("id") if folder else None
                if not folder_id:
                    self.stats["errors"].append("Failed to create campaign folder")
                    self.stats["end_time"] = time.time()
                    return self.stats

        # Idempotency: a campaign workflow whose name already exists at this
        # location is surfaced as a build ERROR, not silently reused and not
        # silently skipped.  Unlike a folder, reusing an existing workflow's id
        # would run the tag/trigger/step-save/sync writes below against content
        # this build did not create and cannot prove is safe to overwrite — a
        # human may have hand-edited it since.  Filtered out here, before the
        # ThreadPoolExecutor starts, so no create POST ever fires for a
        # colliding name.
        to_build: dict[str, dict] = {}
        for key, wf_def in campaign.items():
            wf_name = wf_def.get("name") if isinstance(wf_def, dict) else None
            existing_wf_id = existing_workflow_ids.get(wf_name) if wf_name else None
            if existing_wf_id:
                self.stats["errors"].append(
                    f"{wf_name}: a workflow with this name already exists "
                    f"(id {existing_wf_id}) — skipped to avoid creating a "
                    "duplicate or silently modifying it. Rename it, delete "
                    "the existing one, or use 'workflows update'/'patch-*' "
                    "to change it directly."
                )
                continue
            to_build[key] = wf_def

        wf_ids: dict[str, str] = {}

        def _create_workflow(key: str, wf_def: dict) -> tuple:
            """Full pipeline: create → tag → trigger → save steps → sync."""
            wf_name = wf_def["name"]

            # Apply action ORDERING up front so the very first save PUT carries
            # order/next/parentKey on every step.  Without this the build path
            # PUT raw plan templates with no execution chain and GHL rejects the
            # save with a 400 'corrupted order' (Bug 1a).  link_steps is the
            # canonical linker already used by the legacy create-step path; we
            # run it inside the builder so all installed boxes get the fix
            # without re-authoring plan JSON.
            templates = link_steps(wf_def.get("templates", []))

            # A16 layer-7: the step-save backend validates action ids as
            # UUIDs; plan-supplied slug ids are rejected ("Invalid uuid").
            # Mint deterministic UUIDv5 ids for non-UUID action ids BEFORE
            # any consumer reads them (the trigger link below uses
            # templates[0]["id"] as its targetActionId), remapping link
            # references (next/parentKey) to the same mints.
            templates = normalize_action_ids(templates, self.loc)

            # GU-013 route decision — made BEFORE any transport call and never
            # switched after one.  Public V4 is used only when its capability
            # row is enabled AND the plan maps onto the documented V4 create
            # body (no contact_tag trigger, no explicit folder id).
            route = self.route_for("create")
            if route.public:
                blocker = self._v4_create_blocker(
                    wf_def, folder_name=folder_name,
                    requested_folder_id=requested_folder_id,
                )
                if blocker:
                    route = WorkflowRoute(
                        "create", route.operation_id, WORKFLOW_ROUTE_PRIVATE,
                        blocker, route.blocked,
                    )
                    self.stats.setdefault("route", {})["create"] = route.as_evidence()
                else:
                    return self._create_workflow_public(
                        key, wf_name, templates, folder_name
                    )

            # Named private fallback (unchanged behaviour): public capability is
            # disabled, or this plan cannot be expressed by the V4 contract.

            # Step 1: Create workflow
            result = self.client.request(
                "POST", f"/workflow/{self.loc}",
                {"name": wf_name, "parentId": folder_id},
                workflow_name=wf_name,
            )
            if not result or not result.get("id"):
                return key, None, False, False, None

            wf_id = result["id"]

            # Step 2: Create tag + trigger if specified
            tag = wf_def.get("tag")
            trigger_ok = False
            trigger_data = None
            if tag:
                self.client.create_location_tag(tag, workflow_name=wf_name)

                # Safety fix: active flag is driven by CAF_DRAFT_ONLY (default: False = inactive).
                # Shipping active:True on a status:draft workflow means the trigger fires on live
                # contacts while the workflow is labelled draft — the most dangerous inconsistency.
                trigger_active = draft_only_active_flag()

                trigger_body = {
                    "status": "draft",
                    "workflowId": wf_id,
                    "schedule_config": {},
                    "conditions": [{
                        "operator": "index-of-true",
                        "field": "tagsAdded",
                        "value": tag,
                        "title": "Tag Added",
                        "type": "select",
                        "id": "tag-added",
                    }],
                    "type": "contact_tag",
                    "masterType": "highlevel",
                    "name": tag.replace("-", " ").title(),
                    "actions": [{"workflow_id": wf_id, "type": "add_to_workflow"}],
                    "active": trigger_active,
                    "triggersChanged": True,
                    "location_id": self.loc,
                }
                tr = self.client.request(
                    "POST", f"/workflow/{self.loc}/trigger", trigger_body,
                    workflow_name=wf_name,
                )
                if tr and tr.get("id"):
                    trigger_ok = True
                    trigger_id = tr["id"]
                    trigger_data = {**trigger_body, "id": trigger_id}

                    # Link trigger to first step
                    first_step_id = templates[0]["id"] if templates else None
                    if first_step_id:
                        self.client.request(
                            "PUT", f"/workflow/{self.loc}/trigger/{trigger_id}",
                            {**trigger_body, "targetActionId": first_step_id,
                             "advanceCanvasMeta": {"position": {"x": 57.5, "y": -73}}},
                            workflow_name=wf_name,
                        )

            # Step 3: Save steps via PUT (linked templates carry order/next/parentKey)
            put_body = {
                "name": wf_name,
                "version": 1,
                "workflowData": {"templates": templates},
            }
            put_result = self.client.request(
                "PUT", f"/workflow/{self.loc}/{wf_id}", put_body,
                workflow_name=wf_name,
            )
            steps_ok = bool(put_result and not put_result.get("_error"))

            # Bug 1b — FAIL LOUD on a non-2xx save.  The transport returns
            # {"_error": True, "http_code": <code>, ...} on a rejected PUT; the
            # old code silently treated that as steps_ok=False and reported
            # Steps:0/Errors:0/exit-0.  Capture a real error string so the
            # caller can surface it and exit non-zero.
            step_err = None
            if not steps_ok:
                pr = put_result or {}
                http_code = pr.get("http_code") or pr.get("code")
                step_err = (
                    f"{wf_name}: step-save PUT failed "
                    f"(HTTP {http_code if http_code is not None else 'unknown'}): "
                    f"{pr.get('message', 'no response')}"
                )

            # Step 4: Sync triggers + canvas meta
            if steps_ok:
                current = self.client.request("GET", f"/workflow/{self.loc}/{wf_id}")
                if current and not current.get("_error"):
                    trigger_list = []
                    if trigger_data:
                        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
                        trigger_data.update({
                            "workflow_id": wf_id, "location_id": self.loc,
                            "belongs_to": "workflow", "deleted": False,
                            "date_added": now, "date_updated": now,
                            "advanceCanvasMeta": {"position": {"x": 57.5, "y": -73}},
                        })
                        for k in ("company_id", "company_age", "triggersChanged"):
                            trigger_data.pop(k, None)
                        trigger_list = [trigger_data]

                    steps_with_meta = []
                    for idx, step in enumerate(templates):
                        s = {**step}
                        s["advanceCanvasMeta"] = {"position": {"x": 400 + idx * 300, "y": 0}}
                        s.setdefault("cat", "")
                        s.setdefault("order", idx)
                        steps_with_meta.append(s)

                    meta = current.get("meta") or {}
                    meta["advanceCanvasMeta"] = {
                        "enabled": True,
                        "enabledAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                    }

                    self.client.request(
                        "PUT", f"/workflow/{self.loc}/{wf_id}",
                        {
                            "name": wf_name,
                            "version": current.get("version", 2),
                            "meta": meta,
                            "workflowData": {"templates": steps_with_meta},
                            "triggersChanged": bool(trigger_list),
                            "oldTriggers": trigger_list,
                            "newTriggers": trigger_list,
                        },
                        workflow_name=wf_name,
                    )

            return key, wf_id, steps_ok, trigger_ok, step_err

        # Run all (non-colliding) workflows in parallel (burst-capped;
        # CAF_INTERNAL_MAX_WORKERS). `to_build` excludes any name already
        # caught by the collision check above.
        with ThreadPoolExecutor(max_workers=_build_max_workers()) as pool:
            futures = [
                pool.submit(_create_workflow, key, wf_def)
                for key, wf_def in to_build.items()
            ]

            for future in as_completed(futures):
                key, wf_id, steps_ok, trigger_ok, step_err = future.result()
                # Surface a rejected step-save regardless of whether the shell
                # workflow was created — an empty workflow shell with a failed
                # save is a FAILURE, not a silent success (Bug 1b).
                if step_err:
                    self.stats["errors"].append(step_err)
                if wf_id:
                    wf_ids[key] = wf_id
                    self.stats["workflows_created"] += 1
                    if steps_ok:
                        self.stats["steps_saved"] += len(campaign[key]["templates"])
                    if trigger_ok:
                        self.stats["triggers_created"] += 1
                else:
                    self.stats["errors"].append(f"Failed: {campaign[key]['name']}")

        self.stats["end_time"] = time.time()
        self.stats["api_calls"] = self.client.call_count
        self.stats["workflow_ids"] = wf_ids
        self.stats["folder_id"] = folder_id

        return self.stats

    def format_summary(self) -> str:
        """Format build stats as a human-readable summary."""
        elapsed = self.stats["end_time"] - self.stats["start_time"]
        lines = [
            f"Done in {elapsed:.1f}s",
            f"  Workflows: {self.stats['workflows_created']}",
            f"  Steps:     {self.stats['steps_saved']}",
            f"  Triggers:  {self.stats['triggers_created']}",
            f"  API calls: {self.stats.get('api_calls', 0)}",
            f"  Errors:    {len(self.stats['errors'])}",
        ]
        for e in self.stats["errors"]:
            lines.append(f"    - {e}")

        notes = self.stats.get("notes") or []
        if notes:
            lines.append(f"  Notes:     {len(notes)}")
            for n in notes:
                lines.append(f"    - {n}")

        routes = self.stats.get("route") or {}
        if routes:
            lines.append("  Route:")
            for operation, info in sorted(routes.items()):
                lines.append(
                    f"    {operation}: {info.get('route')} ({info.get('reason')})"
                )

        wf_ids = self.stats.get("workflow_ids", {})
        if wf_ids:
            lines.append(f"\nGHL Links:")
            for key, wf_id in sorted(wf_ids.items()):
                lines.append(
                    f"  https://app.convertandflow.com/location/{self.loc}/workflow/{wf_id}"
                )

        return "\n".join(lines)
