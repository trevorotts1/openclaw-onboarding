"""GHL workflow builder — step builders, linker, and campaign builder.

Adapted from ghl-superspeed-v3-main/lib/engine.py (2026-03-25).
Creates workflows as DRAFT (never auto-published).

EXPERIMENTAL: Gated behind --experimental flag in CLI.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
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


# ── Launch-build compiler (L07 / UL-010) ─────────────────────────────────
#
# The launch-c plan reader emits one automation-build document carrying the
# launch plan's calendar, schedule nodes, eligibility/lifecycle/sender metadata
# and stable unit keys.  This layer compiles that document into the
# provider-native shape the private rail already sends: trigger conditions,
# per-email guard conditions and workflow settings.  It never calls a provider
# and never activates anything — every workflow it produces is a draft.
#
# Purchase suppression is scoped to this campaign only: a verified purchase
# stops the remaining PROMOTIONAL emails, never the entitled access email.
# Unsubscribe suppresses every remaining send.  Close-time and past-time nodes
# arrive already suppressed by the plan reader; a suppressed node is never
# compiled into a sendable step.

class WorkflowCompileError(ValueError):
    """A launch build cannot be compiled without guessing. Fail closed."""

    def __init__(self, code: str, message: str, detail: Optional[dict] = None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.detail = detail or {}


GUARD_UNSUBSCRIBED = "guard-unsubscribed"
GUARD_PURCHASE = "guard-purchase-suppression"
GUARD_CLOSE = "guard-close-time"
REQUIRED_OUTPUTS = ("workflow_id", "steps_saved", "trigger_created", "readback_verified")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _graph_projection(templates: list) -> list:
    """Identity-bearing projection of a step graph (layout/meta excluded)."""
    projection = []
    for step in templates or []:
        if not isinstance(step, dict):
            projection.append(step)
            continue
        projection.append({
            "id": step.get("id"),
            "type": step.get("type"),
            "name": step.get("name"),
            "order": step.get("order"),
            "parentKey": step.get("parentKey"),
            "next": step.get("next"),
            "attributes": step.get("attributes"),
        })
    return projection


def graph_hash(templates: list) -> str:
    """Deterministic hash of the saved execution graph."""
    return _sha256(_graph_projection(templates))


def _rule_names(lifecycle: Mapping[str, Any], key: str) -> set:
    rules = lifecycle.get(key) if isinstance(lifecycle, Mapping) else None
    return {rule.get("rule") for rule in rules or [] if isinstance(rule, Mapping)}


def _missing_guards(lifecycle: Mapping[str, Any], *, promotional: bool) -> list:
    if not promotional:
        return []
    stops = _rule_names(lifecycle, "stop_rules")
    suppressions = _rule_names(lifecycle, "suppression_rules")
    missing = []
    if "stop_on_unsubscribe" not in stops:
        missing.append("stop_on_unsubscribe")
    if "stop_on_verified_purchase" not in stops:
        missing.append("stop_on_verified_purchase")
    if "suppress_promotion_after_verified_purchase" not in suppressions:
        missing.append("suppress_promotion_after_verified_purchase")
    if "recheck_eligibility_immediately_before_send" not in suppressions:
        missing.append("recheck_eligibility_immediately_before_send")
    return missing


def compile_guard_conditions(*, promotional: bool, close_at: Optional[str] = None) -> list[dict]:
    """Provider-native conditions placed on every email step.

    ID-unsubscribed: legal suppression, every email.
    contact.verified_purchase: promotional emails only, this campaign only.
    schedule_window: keeps a promotional CTA strictly before doors close.
    """
    conditions = [{
        "id": GUARD_UNSUBSCRIBED,
        "type": "contact_field",
        "field": "contact.unsubscribed",
        "operator": "is",
        "value": False,
        "title": "Not unsubscribed",
        "action": "continue",
    }]
    if promotional:
        conditions.append({
            "id": GUARD_PURCHASE,
            "type": "contact_field",
            "field": "contact.verified_purchase",
            "operator": "is",
            "value": False,
            "title": "No verified purchase in this campaign",
            "scope": "this_campaign_only",
            "action": "continue",
        })
        if close_at:
            conditions.append({
                "id": GUARD_CLOSE,
                "type": "schedule_window",
                "field": "send_at",
                "operator": "before",
                "value": close_at,
                "title": "Before doors close",
                "action": "continue",
            })
    return conditions


def compile_settings(*, sender: Mapping[str, Any], lifecycle: Mapping[str, Any],
                     phase: Optional[str], close_at: Optional[str],
                     promotional: bool) -> dict:
    settings: dict[str, Any] = {
        "phase": phase,
        "marketing": not promotional,
        "suppression": {
            "stopOnUnsubscribe": True,
            "stopOnVerifiedPurchase": bool(promotional),
            "scope": "this_campaign_only",
            "recheckBeforeEachSend": list(
                _rule_names(lifecycle, "suppression_rules")),
        },
    }
    sender_profile = sender.get("sender_profile_ref")
    reply_to = sender.get("reply_to_ref")
    if isinstance(sender_profile, str) and sender_profile:
        settings["senderProfileRef"] = sender_profile
    if isinstance(reply_to, str) and reply_to:
        settings["replyToRef"] = reply_to
    if close_at:
        settings["closeAt"] = close_at
    return settings


def compile_trigger_conditions(tag: Optional[str], eligibility: list) -> list[dict]:
    conditions = []
    if tag:
        conditions.append({
            "operator": "index-of-true",
            "field": "tagsAdded",
            "value": tag,
            "title": "Tag Added",
            "type": "select",
            "id": "tag-added",
        })
    for rule in eligibility or []:
        if not isinstance(rule, Mapping):
            continue
        rule_id = str(rule.get("rule") or "").strip()
        if not rule_id:
            continue
        condition = {
            "operator": "is-true",
            "field": rule_id,
            "title": rule_id.replace("_", " ").title(),
            "type": "eligibility",
            "id": "elig-" + re.sub(r"[^a-z0-9]+", "-", rule_id.lower()).strip("-"),
        }
        for key in ("source_ref", "policy_ref", "check", "timing"):
            if rule.get(key):
                condition[key] = rule[key]
        conditions.append(condition)
    return conditions


def _guarded_templates(templates: list, *, promotional: bool,
                       close_at: Optional[str]) -> list:
    guarded = []
    for step in templates or []:
        step = {**step}
        if step.get("type") == "email":
            attrs = dict(step.get("attributes") or {})
            conditions = list(attrs.get("conditions") or [])
            known = {item.get("id") for item in conditions if isinstance(item, dict)}
            for condition in compile_guard_conditions(
                    promotional=promotional, close_at=close_at):
                if condition["id"] not in known:
                    conditions.append(condition)
            attrs["conditions"] = conditions
            attrs["marketing"] = promotional
            step["attributes"] = attrs
        guarded.append(step)
    return guarded


def compile_automation_build(build: Mapping[str, Any], *, external_deps: Optional[list] = None,
                             depends_on: Optional[list] = None) -> dict:
    """Compile ONE launch-c build entry into one or more provider workflow defs."""
    if not isinstance(build, Mapping):
        raise WorkflowCompileError("BUILD-SHAPE", "build entry is not an object")
    if build.get("draft_only") is not True:
        raise WorkflowCompileError("BUILD-NOT-DRAFT",
                                   "only a draft_only build may be compiled")
    if build.get("state") != "ready" or build.get("blocked_by"):
        raise WorkflowCompileError(
            "BUILD-BLOCKED",
            "build %r is blocked: %s" % (build.get("id"), build.get("blocked_by")),
            detail={"unit_key": build.get("unit_key"),
                    "blocked_by": build.get("blocked_by")})

    workflows = build.get("workflows") or []
    if not workflows:
        raise WorkflowCompileError("BUILD-NO-WORKFLOWS",
                                   "build %r carries no workflows" % build.get("id"))
    schedule = build.get("schedule") or {}
    sequences = schedule.get("sequences") or {}
    lifecycle = build.get("lifecycle") or {}
    eligibility = build.get("eligibility") or []
    sender = build.get("sender") or {}
    unit_key = build.get("unit_key") or str(build.get("id"))
    phase = build.get("phase") or build.get("family")

    compiled = {}
    previous_keys = []
    for workflow in workflows:
        email_steps = [step for step in (workflow.get("steps") or [])
                       if isinstance(step, Mapping) and step.get("type") == "email"]
        if not email_steps:
            raise WorkflowCompileError(
                "BUILD-NO-EMAIL",
                "workflow %r in build %r has no email step"
                % (workflow.get("key"), build.get("id")))
        seq_id = None
        for candidate, seq_schedule in sequences.items():
            if seq_schedule.get("workflow_key") == workflow.get("key"):
                seq_id = candidate
                break
            if workflow.get("key") in {
                    node.get("workflow_key") for node in seq_schedule.get("nodes", [])}:
                seq_id = candidate
                break
        seq_schedule = sequences.get(seq_id or "", {})
        close_at = seq_schedule.get("close_at")
        promotional = seq_schedule.get("promotional")
        if promotional is None:
            promotional = (seq_id or phase) != "welcome_access"
        missing = _missing_guards(lifecycle, promotional=promotional)
        if missing:
            raise WorkflowCompileError(
                "MISSING-GUARDS",
                "build %r promotional workflow %r has no suppression guards: %s"
                % (build.get("id"), workflow.get("key"), ", ".join(missing)),
                detail={"unit_key": unit_key, "missing": missing})

        templates = _guarded_templates(workflow.get("steps") or [],
                                       promotional=promotional, close_at=close_at)
        wf_key = "%s__%s" % (build.get("id"), workflow.get("key"))
        required = ["workflow_id", "steps_saved", "readback_verified"]
        if workflow.get("tag"):
            required.append("trigger_created")
        compiled[wf_key] = {
            "name": workflow.get("name"),
            "tag": workflow.get("tag"),
            "status": "draft",
            "templates": templates,
            "unit_key": "%s/%s" % (unit_key, workflow.get("key")),
            "source_unit": build.get("id"),
            "phase": seq_id or phase,
            "promotional": promotional,
            "close_at": close_at,
            "eligibility": list(eligibility),
            "lifecycle": dict(lifecycle),
            "sender": dict(sender),
            "settings": compile_settings(
                sender=sender, lifecycle=lifecycle, phase=seq_id or phase,
                close_at=close_at, promotional=promotional),
            "trigger_conditions": compile_trigger_conditions(
                workflow.get("tag"), list(eligibility)),
            "expected_source_hash": build.get("expected_graph_hash"),
            "depends_on": list(depends_on or []) + list(previous_keys),
            "external_depends_on": list(external_deps or []),
            "requires": required,
        }
        previous_keys.append(wf_key)
    return compiled


def compile_launch_builds(document: Mapping[str, Any], *, require_ready: bool = True) -> dict:
    """Compile a whole launch-c automation-build document into a campaign dict.

    Refuses (WorkflowCompileError) on a blocked/invalid build, a missing
    required output, or a missing suppression guard. Never sends and never
    publishes.
    """
    if not isinstance(document, Mapping):
        raise WorkflowCompileError("DOCUMENT-SHAPE", "automation-build document is not an object")
    if document.get("draft_only") is not True:
        raise WorkflowCompileError("DOCUMENT-NOT-DRAFT",
                                   "automation-build document must be draft_only")
    builds = document.get("builds")
    if not isinstance(builds, list):
        raise WorkflowCompileError("DOCUMENT-SHAPE", "builds must be a list")

    campaign: dict[str, Any] = {}
    for build in builds:
        if not isinstance(build, Mapping):
            raise WorkflowCompileError("BUILD-SHAPE", "build entry is not an object")
        if require_ready and (build.get("state") != "ready" or build.get("blocked_by")):
            raise WorkflowCompileError(
                "BUILD-BLOCKED",
                "build %r is blocked: %s" % (build.get("id"), build.get("blocked_by")),
                detail={"unit_key": build.get("unit_key"),
                        "blocked_by": build.get("blocked_by")})
        required_outputs = build.get("required_outputs") or []
        for output in required_outputs:
            if output == "workflows" and not build.get("workflows"):
                raise WorkflowCompileError("REQUIRED-OUTPUT-MISSING",
                                           "build %r has no workflows" % build.get("id"))
            if output == "schedule" and not (build.get("schedule") or {}).get("nodes"):
                raise WorkflowCompileError("REQUIRED-OUTPUT-MISSING",
                                           "build %r has no schedule nodes" % build.get("id"))
            if output == "guards" and build.get("lifecycle") is None:
                raise WorkflowCompileError("REQUIRED-OUTPUT-MISSING",
                                           "build %r has no lifecycle guards" % build.get("id"))

        # Provider-visible dependencies: the workflows bound to dependency
        # email sequences. External unit dependencies were enforced by the
        # plan reader (a missing page URL / text set / count blocks the build).
        dependency_keys = []
        for dep in build.get("depends_on") or []:
            for candidate_key, wf_def in campaign.items():
                if wf_def.get("source_unit") == dep:
                    dependency_keys.append(candidate_key)
        external = [dep for dep in (build.get("depends_on") or [])
                    if not any(wf.get("source_unit") == dep for wf in campaign.values())]
        compiled = compile_automation_build(
            build, external_deps=external, depends_on=dependency_keys)
        for key, wf_def in compiled.items():
            if key in campaign:
                raise WorkflowCompileError("DUPLICATE-WORKFLOW-KEY", key)
            campaign[key] = wf_def
    return campaign


# ── Build journal (stable unit keys, remote ids, phases, hashes, readback) ──

class BuildJournal:
    """Append-only JSONL receipt journal for a compiled launch build.

    Entries carry NO credentials and no message bodies: unit key, workflow
    name, phase, remote id, expected hash, readback hash and status only.
    """

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._lock = threading.Lock()

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError as exc:
                raise ValueError("build journal %s is corrupt: %s" % (self.path, exc))
        return out

    def latest(self, unit_key: str) -> Optional[dict]:
        found = None
        for entry in self.entries():
            if entry.get("unit_key") == unit_key:
                found = entry
        return found

    def latest_phase(self, unit_key: str, phase: str) -> Optional[dict]:
        found = None
        for entry in self.entries():
            if entry.get("unit_key") == unit_key and entry.get("phase") == phase:
                found = entry
        return found

    def append(self, **entry: Any) -> dict:
        record = dict(entry)
        record.setdefault("recorded_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        line = _canonical(record) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        return record


def _journal_for(journal: Any) -> Optional[BuildJournal]:
    if journal is None:
        env_path = os.environ.get("CAF_BUILD_JOURNAL", "").strip()
        return BuildJournal(env_path) if env_path else None
    if isinstance(journal, BuildJournal):
        return journal
    return BuildJournal(journal)


def _readback_templates(client: Any, location_id: str,
                        workflow_id: str) -> Optional[list]:
    """Read the saved workflow graph back, or None when it cannot be read."""
    try:
        data = client.request("GET", "/workflow/%s/%s" % (location_id, workflow_id))
    except Exception:  # noqa: BLE001 - an unreadable readback is an explicit unknown
        return None
    if not isinstance(data, dict) or data.get("_error"):
        return None
    workflow_data = data.get("workflowData")
    if isinstance(workflow_data, dict) and isinstance(workflow_data.get("templates"), list):
        return workflow_data["templates"]
    if isinstance(data.get("templates"), list):
        return data["templates"]
    return None


def verify_saved_graph(client: Any, location_id: str, workflow_id: str,
                       expected_hash: str) -> tuple:
    """Return ``(ok, observed_hash, templates)``; unknown readback is not ok."""
    templates = _readback_templates(client, location_id, workflow_id)
    if templates is None:
        return False, None, None
    observed = graph_hash(templates)
    return observed == expected_hash, observed, templates


def reconcile_journal(client: Any, journal: BuildJournal, location_id: str) -> dict:
    """Reconcile uncertain prior attempts BEFORE any retry.

    Never retries a create. For each unresolved entry: read the remote graph;
    adopt it when it matches the journalled expected hash, flag a human edit
    when it differs, and keep it unknown when the read fails.
    """
    report = {"adopted": [], "human_edit": [], "unknown": [], "clean": []}
    for entry in journal.entries():
        unit_key = entry.get("unit_key")
        remote_id = entry.get("remote_id")
        if not unit_key or not remote_id:
            continue
        if entry.get("phase") != "create" or entry.get("status") != "unknown_outcome":
            continue
        ok, observed, templates = verify_saved_graph(
            client, location_id, remote_id, entry.get("expected_hash") or "")
        if templates is None:
            report["unknown"].append({"unit_key": unit_key, "remote_id": remote_id})
        elif ok:
            journal.append(unit_key=unit_key, remote_id=remote_id, phase="reconcile",
                           status="adopted", expected_hash=entry.get("expected_hash"),
                           readback_hash=observed)
            report["adopted"].append({"unit_key": unit_key, "remote_id": remote_id})
        else:
            journal.append(unit_key=unit_key, remote_id=remote_id, phase="reconcile",
                           status="human_edit", expected_hash=entry.get("expected_hash"),
                           readback_hash=observed)
            report["human_edit"].append({"unit_key": unit_key, "remote_id": remote_id})
    return report


def _journal_trigger_ok(journal: Optional[BuildJournal], unit_key: Optional[str],
                        wf_def: Mapping[str, Any]) -> bool:
    """Adoption proves outputs only from the journal's own prior receipts."""
    if not wf_def.get("tag"):
        return True
    if not journal or not unit_key:
        return False
    entry = journal.latest_phase(unit_key, "trigger")
    return bool(entry and entry.get("status") == "ok")


def _contract_errors(campaign: Mapping[str, Any]) -> list[str]:
    """Validate declared dependencies and required outputs for compiled plans.

    Plans without compiled markers keep the legacy behaviour unchanged.
    """
    errors: list[str] = []
    graph: dict[str, list] = {}
    for key, wf_def in campaign.items():
        if not isinstance(wf_def, Mapping):
            continue
        compiled = any(field in wf_def for field in (
            "unit_key", "expected_source_hash", "lifecycle", "depends_on", "requires"))
        if not compiled:
            continue
        templates = wf_def.get("templates")
        if not isinstance(templates, list) or not templates:
            errors.append(f"{key}: compiled workflow has no templates")
            continue
        ids = [step.get("id") for step in templates if isinstance(step, Mapping)]
        if len(ids) != len(set(ids)):
            errors.append(f"{key}: compiled workflow has duplicate step ids")
        if not all(isinstance(step_id, str) and step_id for step_id in ids):
            errors.append(f"{key}: compiled step is missing an id")
        lifecycle = wf_def.get("lifecycle")
        promotional = bool(wf_def.get("promotional"))
        if promotional:
            if not isinstance(lifecycle, Mapping):
                errors.append(f"{key}: promotional workflow has no lifecycle guards")
            else:
                missing = _missing_guards(lifecycle, promotional=True)
                if missing:
                    errors.append(
                        f"{key}: missing suppression guard(s): {', '.join(missing)}")
        requires = wf_def.get("requires") or []
        if not isinstance(requires, list):
            errors.append(f"{key}: requires must be a list")
            requires = []
        for output in requires:
            if output not in REQUIRED_OUTPUTS:
                errors.append(f"{key}: unknown required output {output!r}")
        depends_on = wf_def.get("depends_on") or []
        if not isinstance(depends_on, list):
            errors.append(f"{key}: depends_on must be a list")
            depends_on = []
        for dep in depends_on:
            if dep == key:
                errors.append(f"{key}: depends on itself")
            elif dep not in campaign:
                errors.append(f"{key}: depends on unknown workflow {dep!r}")
        graph[key] = [dep for dep in depends_on if dep in campaign]

    # Cycle check over declared provider dependencies.
    state: dict[str, str] = {}

    def visit(node: str, trail: list) -> None:
        if state.get(node) == "done":
            return
        if state.get(node) == "open":
            errors.append("workflow dependency cycle: %s" % " -> ".join(trail + [node]))
            return
        state[node] = "open"
        for dep in graph.get(node, []):
            visit(dep, trail + [node])
        state[node] = "done"

    for node in sorted(graph):
        visit(node, [])
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
        *,
        journal: Any = None,
    ) -> dict:
        """Build an entire campaign. Returns stats dict.

        Pass `folder_id` to drop the campaign into an existing folder; pass
        `folder_name` to create a new folder. Exactly one is required.

        `journal` (path or ``BuildJournal``) opts a compiled launch build into
        the receipt journal + readback verification; plans without a compiled
        unit key keep the unchanged private-rail behaviour.

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
            return self._build_locked(
                campaign, folder_name=folder_name, folder_id=folder_id,
                journal=_journal_for(journal),
            )

    def _build_locked(
        self,
        campaign: dict,
        folder_name: Optional[str] = None,
        folder_id: Optional[str] = None,
        *,
        journal: Optional[BuildJournal] = None,
    ) -> dict:
        """Internal build implementation (called under WriteLock)."""
        self.stats["start_time"] = time.time()
        self.stats.setdefault("journal_entries", [])
        self.stats.setdefault("readback", {})
        self.stats.setdefault("adopted", [])
        self.stats.setdefault("needs_reconcile", [])
        if journal is not None:
            self.stats["journal_path"] = str(journal.path)
        # Remember whether the caller pinned an explicit folder id: the V4
        # create contract has no folder-id field, so that request keeps the
        # named private fallback (a name-based folder can be passed instead).
        requested_folder_id = folder_id

        # Pre-flight validation
        errors = validate_campaign(campaign)
        contract_errors = _contract_errors(campaign)
        if contract_errors:
            errors = list(errors) + contract_errors
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
        adopted_ids: dict[str, str] = {}
        adopted_trigger: dict[str, bool] = {}
        for key, wf_def in campaign.items():
            wf_name = wf_def.get("name") if isinstance(wf_def, dict) else None
            existing_wf_id = existing_workflow_ids.get(wf_name) if wf_name else None
            unit_key = wf_def.get("unit_key") if isinstance(wf_def, dict) else None
            prior = journal.latest(unit_key) if (journal and unit_key) else None

            # Journal-first reconciliation: a prior attempt that may have
            # created this workflow is verified by READBACK before anything
            # else. Never create a second copy and never overwrite a human edit.
            if journal and unit_key and prior and prior.get("remote_id"):
                remote_id = str(prior["remote_id"])
                expected = prior.get("expected_hash") or ""
                ok, observed, templates = verify_saved_graph(
                    self.client, self.loc, remote_id, expected)
                if templates is None:
                    self.stats["needs_reconcile"].append(unit_key)
                    self.stats["errors"].append(
                        f"{wf_name}: prior attempt {remote_id} exists but the "
                        "saved graph cannot be read — reconcile before retry; "
                        "NO create or overwrite was attempted."
                    )
                    continue
                if ok:
                    adopted_ids[key] = remote_id
                    adopted_trigger[key] = _journal_trigger_ok(journal, unit_key, wf_def)
                    self.stats["adopted"].append(wf_name)
                    self.stats.setdefault("notes", []).append(
                        f"{wf_name}: adopted existing workflow {remote_id} from "
                        "the build journal; saved graph matches the expected "
                        "hash and was NOT overwritten."
                    )
                    continue
                self.stats["errors"].append(
                    f"{wf_name}: existing workflow {remote_id} differs from the "
                    "journalled graph (expected %s, observed %s) — a human edit "
                    "is preserved; NO overwrite was attempted."
                    % (expected[:12], (observed or "unreadable")[:12])
                )
                journal.append(unit_key=unit_key, remote_id=remote_id,
                               phase="reconcile", status="human_edit",
                               expected_hash=expected, readback_hash=observed)
                continue

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

        wf_ids: dict[str, str] = dict(adopted_ids)

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

            unit_key = wf_def.get("unit_key")
            expected_hash = graph_hash(templates)
            declared_hash = wf_def.get("expected_hash")
            if declared_hash and declared_hash != expected_hash:
                return (key, None, False, False, None,
                        f"{wf_name}: compiled graph hash {expected_hash} does not "
                        f"match the declared expected hash {declared_hash} — "
                        "refusing to build a plan that drifted after compile.")

            # Reconcile-before-retry: a journalled remote id is authoritative.
            # Read it back; adopt only when it matches, never retry a create.
            prior = journal.latest(unit_key) if (journal and unit_key) else None
            if prior and prior.get("remote_id"):
                remote_id = str(prior["remote_id"])
                ok, observed, prior_templates = verify_saved_graph(
                    self.client, self.loc, remote_id, prior.get("expected_hash") or expected_hash)
                if prior_templates is None:
                    self.stats["needs_reconcile"].append(unit_key)
                    return (key, None, False, False, None,
                            f"{wf_name}: prior attempt {remote_id} cannot be read "
                            "back — reconcile before any retry; no create fired.")
                if not ok:
                    journal.append(unit_key=unit_key, remote_id=remote_id,
                                   phase="reconcile", status="human_edit",
                                   expected_hash=prior.get("expected_hash"),
                                   readback_hash=observed)
                    return (key, None, False, False, None,
                            f"{wf_name}: existing workflow {remote_id} differs from "
                            "the journalled graph — human edit preserved; no "
                            "overwrite fired.")
                journal.append(unit_key=unit_key, remote_id=remote_id,
                               phase="reconcile", status="adopted",
                               expected_hash=prior.get("expected_hash"),
                               readback_hash=observed)
                self.stats["adopted"].append(wf_name)
                return (key, remote_id, True,
                        _journal_trigger_ok(journal, unit_key, wf_def), None, True)

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
                    public_result = self._create_workflow_public(
                        key, wf_name, templates, folder_name
                    )
                    return tuple(public_result) + (None,)

            # Named private fallback (unchanged behaviour): public capability is
            # disabled, or this plan cannot be expressed by the V4 contract.

            # Step 1: Create workflow
            create_body: dict[str, Any] = {"name": wf_name, "parentId": folder_id}
            if wf_def.get("settings"):
                create_body["settings"] = wf_def["settings"]
            result = self.client.request(
                "POST", f"/workflow/{self.loc}",
                create_body,
                workflow_name=wf_name,
            )
            if not result or not result.get("id"):
                # An absent/unknown create response is UNCERTAIN, not a failure:
                # the workflow may exist. Journal it so the next run reconciles
                # instead of POSTing a duplicate.
                if journal and unit_key:
                    journal.append(unit_key=unit_key, name=wf_name, phase="create",
                                   status="unknown_outcome", remote_id=None,
                                   expected_hash=expected_hash)
                self.stats["needs_reconcile"].append(unit_key or wf_name)
                return (key, None, False, False, None,
                        f"{wf_name}: create returned no id — outcome uncertain; "
                        "reconcile before retry; no duplicate create was attempted.")

            wf_id = result["id"]
            if journal and unit_key:
                journal.append(unit_key=unit_key, name=wf_name, remote_id=str(wf_id),
                               phase="create", status="ok",
                               expected_hash=expected_hash)

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
                    "conditions": list(wf_def.get("trigger_conditions") or [{
                        "operator": "index-of-true",
                        "field": "tagsAdded",
                        "value": tag,
                        "title": "Tag Added",
                        "type": "select",
                        "id": "tag-added",
                    }]),
                    "type": "contact_tag",
                    "masterType": "highlevel",
                    "name": tag.replace("-", " ").title(),
                    "actions": [{"workflow_id": wf_id, "type": "add_to_workflow"}],
                    "active": trigger_active,
                    "triggersChanged": True,
                    "location_id": self.loc,
                }
                if wf_def.get("settings"):
                    trigger_body["settings"] = wf_def["settings"]
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
                if journal and unit_key:
                    journal.append(unit_key=unit_key, name=wf_name,
                                   remote_id=str(wf_id), phase="trigger",
                                   status="ok" if trigger_ok else "failed",
                                   expected_hash=expected_hash)

            # Step 3: Save steps via PUT (linked templates carry order/next/parentKey)
            put_body = {
                "name": wf_name,
                "version": 1,
                "workflowData": {"templates": templates},
            }
            if wf_def.get("settings"):
                put_body["settings"] = wf_def["settings"]
            put_result = self.client.request(
                "PUT", f"/workflow/{self.loc}/{wf_id}", put_body,
                workflow_name=wf_name,
            )
            steps_ok = bool(put_result and not put_result.get("_error"))
            if journal and unit_key:
                journal.append(unit_key=unit_key, name=wf_name, remote_id=str(wf_id),
                               phase="save", status="ok" if steps_ok else "failed",
                               expected_hash=expected_hash)

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

            # Step 5: Read the saved graph back. A compiled launch build is not
            # "saved" until the provider returns the graph we expected.
            readback_ok = None
            requires = wf_def.get("requires") or []
            if steps_ok and (wf_def.get("unit_key") or "readback_verified" in requires):
                ok, observed, read_templates = verify_saved_graph(
                    self.client, self.loc, str(wf_id), expected_hash)
                readback_ok = bool(ok)
                self.stats["readback"][key] = {
                    "workflow_id": str(wf_id),
                    "expected_hash": expected_hash,
                    "readback_hash": observed,
                    "ok": readback_ok,
                    "readable": read_templates is not None,
                }
                if read_templates is None:
                    step_err = (f"{wf_name}: saved graph readback failed — "
                                "outcome uncertain; reconcile before retry.")
                    if unit_key:
                        self.stats["needs_reconcile"].append(unit_key)
                    if journal and unit_key:
                        journal.append(unit_key=unit_key, name=wf_name,
                                       remote_id=str(wf_id), phase="readback",
                                       status="unreadable",
                                       expected_hash=expected_hash,
                                       readback_hash=None)
                elif not ok:
                    step_err = (f"{wf_name}: saved graph readback mismatch "
                                f"(expected {expected_hash[:12]}, observed "
                                f"{(observed or '')[:12]}) — workflow was saved "
                                "but does not match the compiled graph.")
                    if journal and unit_key:
                        journal.append(unit_key=unit_key, name=wf_name,
                                       remote_id=str(wf_id), phase="readback",
                                       status="mismatch",
                                       expected_hash=expected_hash,
                                       readback_hash=observed)
                elif journal and unit_key:
                    journal.append(unit_key=unit_key, name=wf_name,
                                   remote_id=str(wf_id), phase="readback",
                                   status="ok", expected_hash=expected_hash,
                                   readback_hash=observed)

            return key, wf_id, steps_ok, trigger_ok, step_err, readback_ok

        # Run all (non-colliding) workflows in parallel (burst-capped;
        # CAF_INTERNAL_MAX_WORKERS). `to_build` excludes any name already
        # caught by the collision check above.
        results: dict[str, tuple] = {
            key: (remote_id, True, adopted_trigger.get(key, False), None, True)
            for key, remote_id in adopted_ids.items()
        }
        with ThreadPoolExecutor(max_workers=_build_max_workers()) as pool:
            futures = [
                pool.submit(_create_workflow, key, wf_def)
                for key, wf_def in to_build.items()
            ]

            for future in as_completed(futures):
                key, wf_id, steps_ok, trigger_ok, step_err, readback_ok = future.result()
                results[key] = (wf_id, steps_ok, trigger_ok, step_err, readback_ok)
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

        # Every declared dependency and required output is enforced after the
        # build: a workflow that was skipped/blocked cannot satisfy a dependent.
        for key, wf_def in campaign.items():
            if not isinstance(wf_def, Mapping):
                continue
            for dep in wf_def.get("depends_on") or []:
                if dep in campaign and dep not in wf_ids:
                    self.stats["errors"].append(
                        f"{wf_def.get('name') or key}: declared dependency "
                        f"{dep!r} was not built — refusing to report success.")
            requires = wf_def.get("requires") or []
            if not requires:
                continue
            built = results.get(key)
            wf_id, steps_ok, trigger_ok, _step_err, readback_ok = built or (
                wf_ids.get(key), True, True, None, None)
            if "workflow_id" in requires and not wf_id:
                self.stats["errors"].append(
                    f"{wf_def.get('name') or key}: required output 'workflow_id' missing")
            if "steps_saved" in requires and not steps_ok:
                self.stats["errors"].append(
                    f"{wf_def.get('name') or key}: required output 'steps_saved' missing")
            if "trigger_created" in requires and not trigger_ok:
                self.stats["errors"].append(
                    f"{wf_def.get('name') or key}: required output 'trigger_created' missing")
            if "readback_verified" in requires and readback_ok is not True:
                self.stats["errors"].append(
                    f"{wf_def.get('name') or key}: required output "
                    "'readback_verified' missing")

        self.stats["workflows_reused"] = len(adopted_ids)
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
