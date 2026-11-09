#!/usr/bin/env python3
"""responder_policy.py - the single-responder policy for every channel (WF28).

WHY THIS EXISTS
---------------
A location can now have three things that answer a person: the existing
OpenClaw brain (Skill 38), GHL Workflow AI steps, and a native GHL Conversation
AI agent.  Nothing in the repo decided WHICH of them owns a channel, so two of
them could reply to one inbound message.  This module is that decision, and it
is the only one:

  * a per-location/channel routing record names exactly one primary responder
    and the native mode (off, suggestive, auto-pilot);
  * the internal Skill 38 channel names are mapped deliberately to the seven
    native enumerations (IG, FB, SMS, WebChat, WhatsApp, Live_Chat, Email);
    anything else is refused, never coerced;
  * two inbound events that arrive close together, a human takeover, an opt-out
    and a returning contact all resolve here;
  * a conversation-scoped lease, in the SAME SQLite file the rest of Skill 38
    uses for durable identity, makes "one responder" hold across local AND
    native dispatch and across process restarts.

The record never weakens the existing hard gates: opt-out, quiet hours and
client test mode must all stay enabled or the record is refused.  Unknown
properties are refused, so a customer-supplied payload can never add policy.

BOUNDARY WITH THE NATIVE ADAPTER
--------------------------------
This module decides who MAY answer.  It performs no network call and creates no
native agent.  The native adapter
(``cli_anything.gohighlevel.public.conversation_ai``) only runs after this
module returns a native verdict, and the adapter itself refuses a primary-agent
switch.

Run:
    python3 tools/responder_policy.py validate --record <path>
    python3 tools/responder_policy.py channel-map [<channel>]
    python3 tools/responder_policy.py resolve --record <path> --channel <c>
        [--event <json|path>] [--now <epoch>] [--lease <db>]
        [--tenant <id>] [--thread <ref>] [--event-id <id>] [--holder <id>]
    python3 tools/responder_policy.py claim --lease <db> --tenant <id>
        --thread <ref> --event-id <id> --holder <id> [--ttl <seconds>]
    python3 tools/responder_policy.py takeover --lease <db> --tenant <id>
        --thread <ref> --actor <who> --reason <why>
    python3 tools/responder_policy.py release --lease <db> --tenant <id>
        --thread <ref> --holder <id> [--reason <why>]
    python3 tools/responder_policy.py self-check

Exit: 0 accepted/valid, 1 refused/invalid, 2 usage or IO.

Acceptance: B11 (no double send; human takeover/opt-out/quiet hours work),
B12 (explicit channel map; no invented channel), IG-AI-04 (no duplicate
response), IG-AI-05 (handoff/opt-out/quiet hours/returning contact),
IG-AI-08 (content cannot change administrative policy).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

SCHEMA_VERSION = 1

#: The seven native GHL Conversation AI channel enumerations (Document 1 §25.5).
NATIVE_CHANNELS: Tuple[str, ...] = (
    "IG", "FB", "SMS", "WebChat", "WhatsApp", "Live_Chat", "Email",
)

#: The only native operational modes.  ``off`` is the creation default.
NATIVE_MODES: Tuple[str, ...] = ("off", "suggestive", "auto-pilot")
DEFAULT_NATIVE_MODE = "off"

#: Internal Skill 38 channel name -> exact native enumeration.  Deliberate:
#: WebChat and Live_Chat are different destinations and are never merged.
CHANNEL_MAP: Dict[str, str] = {
    "sms": "SMS",
    "text": "SMS",
    "phone": "SMS",
    "email": "Email",
    "fb": "FB",
    "facebook": "FB",
    "facebook_dm": "FB",
    "messenger": "FB",
    "ig": "IG",
    "instagram": "IG",
    "instagram_dm": "IG",
    "whatsapp": "WhatsApp",
    "webchat": "WebChat",
    "web_chat": "WebChat",
    "web_chat_widget": "WebChat",
    "live_chat": "Live_Chat",
    "livechat": "Live_Chat",
    "live-chat": "Live_Chat",
}

#: Channel labels a caller may know from the local skill but which have NO
#: native Conversation AI destination.  They are refused by name.
UNSUPPORTED_CHANNELS: Dict[str, str] = {
    "linkedin": "LinkedIn has no native Conversation AI channel enumeration",
    "fb_comment": "public Facebook comments are not a native conversation channel",
    "fb_comments": "public Facebook comments are not a native conversation channel",
    "facebook_comments": "public Facebook comments are not a native conversation channel",
    "instagram_comments": "public Instagram comments are not a native conversation channel",
    "all_in_one": "an all-in-one label is not a native channel; name the real destination",
    "all_in_one_chat": "an all-in-one label is not a native channel; name the real destination",
    "gmb": "Google Business Messages has no native Conversation AI channel",
    "tiktok": "TikTok has no native Conversation AI channel",
    "youtube": "YouTube has no native Conversation AI channel",
}

PRIMARY_LOCAL = "openclaw_inbound"
PRIMARY_NATIVE = "native_ghl"
PRIMARY_NONE = "none"
PRIMARY_KINDS: Tuple[str, ...] = (PRIMARY_LOCAL, PRIMARY_NATIVE, PRIMARY_NONE)

# Verdict codes.  A caller may assert on these; they never change meaning.
ALLOW_LOCAL = "ALLOW_LOCAL"
ALLOW_NATIVE_SUGGESTIVE = "ALLOW_NATIVE_SUGGESTIVE"
ALLOW_NATIVE_AUTOPILOT = "ALLOW_NATIVE_AUTOPILOT"
SUPPRESS_DUPLICATE_EVENT = "SUPPRESS_DUPLICATE_EVENT"
SUPPRESS_HUMAN_TAKEOVER = "SUPPRESS_HUMAN_TAKEOVER"
SUPPRESS_OPT_OUT = "SUPPRESS_OPT_OUT"
WAIT_QUIET_HOURS = "WAIT_QUIET_HOURS"
REFUSE_UNSUPPORTED_CHANNEL = "REFUSE_UNSUPPORTED_CHANNEL"
REFUSE_UNKNOWN_CHANNEL = "REFUSE_UNKNOWN_CHANNEL"
REFUSE_NO_RESPONDER = "REFUSE_NO_RESPONDER"
REFUSE_RESPONDER_CONFLICT = "REFUSE_RESPONDER_CONFLICT"
REFUSE_TWO_RESPONDERS = "REFUSE_TWO_RESPONDERS"
REFUSE_INVALID_RECORD = "REFUSE_INVALID_RECORD"
REFUSE_POLICY_WEAKENED = "REFUSE_POLICY_WEAKENED"
REFUSE_WORKFLOW_SEND_CONFLICT = "REFUSE_WORKFLOW_SEND_CONFLICT"
REFUSE_CHANNEL_MAP_MISMATCH = "REFUSE_CHANNEL_MAP_MISMATCH"
REFUSE_PRIMARY_SWITCH_UNAPPROVED = "REFUSE_PRIMARY_SWITCH_UNAPPROVED"

_KNOWN_TOP = {
    "schema_version", "record_id", "location_id", "channels",
    "production_primary", "quiet_hours", "native_prompt",
}
_KNOWN_CHANNEL = {
    "native_channel", "primary_responder", "native_mode", "handoff",
    "workflow_sends", "identity", "allowed_actions", "limits",
    "disabled_reason",
}
_KNOWN_HANDOFF = {"trigger", "pauses_automation", "resumes_on"}
_KNOWN_WORKFLOW = {"allowed", "deduplicates_with_primary", "reason"}
_KNOWN_IDENTITY = {"contact_identity", "thread_identity"}
_KNOWN_LIMITS = {"opt_out", "quiet_hours", "client_test_mode"}
_KNOWN_PRIMARY = {"agent_id", "snapshot_ref", "approved_switch_ref", "switched"}
_KNOWN_NATIVE_PROMPT = {
    "effective_prompt_field", "structured_fields_when_empty",
}
_KNOWN_QUIET = {"start", "end", "offset_minutes"}

IDENTITY_CONTACT = "canonical_contact_id"
THREAD_IDENTITIES = ("conversation_id", "thread_id")


class PolicyError(ValueError):
    """Malformed record, event or lease input.  Fail closed."""


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def native_channel_for(channel: Any) -> str:
    """Map one internal channel name to its exact native enumeration."""
    if not _nonempty(channel):
        raise PolicyError("REFUSE_UNKNOWN_CHANNEL: channel must be a nonempty string")
    key = str(channel).strip().lower()
    if key in UNSUPPORTED_CHANNELS:
        raise PolicyError(
            "REFUSE_UNSUPPORTED_CHANNEL: %s (%s)" % (key, UNSUPPORTED_CHANNELS[key]))
    kind = CHANNEL_MAP.get(key)
    if kind is None:
        if key == "chat":
            raise PolicyError(
                "REFUSE_UNKNOWN_CHANNEL: 'chat' is ambiguous; name webchat or"
                " live_chat explicitly")
        raise PolicyError(
            "REFUSE_UNKNOWN_CHANNEL: %r is not a Skill 38 channel; supported: %s"
            % (channel, sorted(CHANNEL_MAP)))
    return kind


def _err(code: str, message: str) -> str:
    return "%s: %s" % (code, message)


def _unknown_keys(doc: Mapping[str, Any], known: set, where: str) -> List[str]:
    return [
        _err(REFUSE_INVALID_RECORD,
             "%s carries unknown property %r; unknown policy is never accepted"
             % (where, key))
        for key in sorted(str(k) for k in doc if str(k) not in known)
    ]


def validate_record(doc: Any) -> List[str]:
    """Return ``CODE: message`` strings; empty means valid."""
    if not isinstance(doc, Mapping):
        return [_err(REFUSE_INVALID_RECORD, "the routing record must be an object")]
    errors = _unknown_keys(doc, _KNOWN_TOP, "the routing record")
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(_err(
            REFUSE_INVALID_RECORD,
            "schema_version must be %d" % SCHEMA_VERSION))
    if not _nonempty(doc.get("location_id")):
        errors.append(_err(REFUSE_INVALID_RECORD, "location_id must be a nonempty string"))
    channels = doc.get("channels")
    if not isinstance(channels, Mapping) or not channels:
        errors.append(_err(REFUSE_INVALID_RECORD, "channels must be a nonempty object"))
        return errors

    seen_native: Dict[str, str] = {}
    for name, entry in channels.items():
        where = "channel %r" % (name,)
        key = str(name).strip().lower()
        if key not in CHANNEL_MAP:
            if key in UNSUPPORTED_CHANNELS:
                errors.append(_err(
                    REFUSE_UNSUPPORTED_CHANNEL,
                    "%s is not a native destination: %s"
                    % (key, UNSUPPORTED_CHANNELS[key])))
            else:
                errors.append(_err(
                    REFUSE_UNKNOWN_CHANNEL,
                    "%r is not a Skill 38 channel; supported: %s"
                    % (name, sorted(CHANNEL_MAP))))
            continue
        if not isinstance(entry, Mapping):
            errors.append(_err(REFUSE_INVALID_RECORD, "%s must be an object" % where))
            continue
        errors.extend(_unknown_keys(entry, _KNOWN_CHANNEL, where))
        expected = CHANNEL_MAP[key]
        if entry.get("native_channel") != expected:
            errors.append(_err(
                REFUSE_CHANNEL_MAP_MISMATCH,
                "%s must declare native_channel %r (got %r)"
                % (where, expected, entry.get("native_channel"))))
        if expected in seen_native:
            errors.append(_err(
                REFUSE_TWO_RESPONDERS,
                "native channel %r is claimed by %r and %r; one destination has"
                " one responder" % (expected, seen_native[expected], key)))
        seen_native[expected] = key

        primary = entry.get("primary_responder")
        mode = entry.get("native_mode", DEFAULT_NATIVE_MODE)
        if primary not in PRIMARY_KINDS:
            errors.append(_err(
                REFUSE_INVALID_RECORD,
                "%s primary_responder must be one of %s" % (where, list(PRIMARY_KINDS))))
        if mode not in NATIVE_MODES:
            errors.append(_err(
                REFUSE_INVALID_RECORD,
                "%s native_mode must be one of %s" % (where, list(NATIVE_MODES))))
        if primary == PRIMARY_NONE:
            errors.append(_err(
                REFUSE_NO_RESPONDER,
                "%s names no responder; an inbound channel always needs exactly one"
                % where))
        if primary == PRIMARY_LOCAL and mode != "off":
            errors.append(_err(
                REFUSE_RESPONDER_CONFLICT,
                "%s has the local brain as primary but leaves native AI in %r;"
                " native AI may send only when it is the primary responder"
                % (where, mode)))
        if primary == PRIMARY_NATIVE and mode == "off":
            errors.append(_err(
                REFUSE_NO_RESPONDER,
                "%s makes native AI primary with mode 'off'; native AI cannot answer"
                % where))

        handoff = entry.get("handoff")
        if not isinstance(handoff, Mapping):
            errors.append(_err(REFUSE_INVALID_RECORD, "%s handoff must be an object" % where))
        else:
            errors.extend(_unknown_keys(handoff, _KNOWN_HANDOFF, where + " handoff"))
            if not _nonempty(handoff.get("trigger")):
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "%s handoff.trigger must name the human-handoff condition" % where))
            if handoff.get("pauses_automation") is not True:
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "%s handoff.pauses_automation must be true; a takeover pauses"
                    " automation" % where))

        workflow = entry.get("workflow_sends")
        if not isinstance(workflow, Mapping):
            errors.append(_err(
                REFUSE_INVALID_RECORD, "%s workflow_sends must be an object" % where))
        else:
            errors.extend(_unknown_keys(workflow, _KNOWN_WORKFLOW, where + " workflow_sends"))
            if not isinstance(workflow.get("allowed"), bool):
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "%s workflow_sends.allowed must be true or false" % where))
            if workflow.get("allowed") is True and workflow.get(
                    "deduplicates_with_primary") is not True:
                errors.append(_err(
                    REFUSE_WORKFLOW_SEND_CONFLICT,
                    "%s lets workflows send without deduplicating against the"
                    " primary responder" % where))

        identity = entry.get("identity")
        if not isinstance(identity, Mapping):
            errors.append(_err(REFUSE_INVALID_RECORD, "%s identity must be an object" % where))
        else:
            errors.extend(_unknown_keys(identity, _KNOWN_IDENTITY, where + " identity"))
            if identity.get("contact_identity") != IDENTITY_CONTACT:
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "%s identity.contact_identity must be %r"
                    % (where, IDENTITY_CONTACT)))
            if identity.get("thread_identity") not in THREAD_IDENTITIES:
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "%s identity.thread_identity must be one of %s"
                    % (where, list(THREAD_IDENTITIES))))

        actions = entry.get("allowed_actions")
        if (not isinstance(actions, list) or not actions
                or not all(_nonempty(item) for item in actions)):
            errors.append(_err(
                REFUSE_INVALID_RECORD,
                "%s allowed_actions must be a nonempty list of action names" % where))

        limits = entry.get("limits")
        if not isinstance(limits, Mapping):
            errors.append(_err(REFUSE_INVALID_RECORD, "%s limits must be an object" % where))
        else:
            errors.extend(_unknown_keys(limits, _KNOWN_LIMITS, where + " limits"))
            for name_limit in ("opt_out", "quiet_hours", "client_test_mode"):
                if limits.get(name_limit) is not True:
                    errors.append(_err(
                        REFUSE_POLICY_WEAKENED,
                        "%s limits.%s must stay true; the existing hard gate is"
                        " never disabled by a routing record" % (where, name_limit)))

    primary = doc.get("production_primary")
    if primary is not None:
        if not isinstance(primary, Mapping):
            errors.append(_err(
                REFUSE_INVALID_RECORD, "production_primary must be an object"))
        else:
            errors.extend(_unknown_keys(primary, _KNOWN_PRIMARY, "production_primary"))
            if not _nonempty(primary.get("agent_id")):
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "production_primary.agent_id must name the existing agent"))
            if primary.get("switched") is True and not _nonempty(
                    primary.get("approved_switch_ref")):
                errors.append(_err(
                    REFUSE_PRIMARY_SWITCH_UNAPPROVED,
                    "production_primary.switched requires approved_switch_ref;"
                    " an existing primary agent is never replaced silently"))
            if primary.get("switched") is True and not _nonempty(
                    primary.get("snapshot_ref")):
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "production_primary.switched requires snapshot_ref for rollback"))

    prompt = doc.get("native_prompt")
    if prompt is not None:
        if not isinstance(prompt, Mapping):
            errors.append(_err(
                REFUSE_INVALID_RECORD, "native_prompt must be an object"))
        else:
            errors.extend(_unknown_keys(prompt, _KNOWN_NATIVE_PROMPT, "native_prompt"))
            if prompt.get("effective_prompt_field") != "fullPrompt":
                errors.append(_err(
                    REFUSE_INVALID_RECORD,
                    "native_prompt.effective_prompt_field must be 'fullPrompt'; a"
                    " nonempty fullPrompt overrides the structured fields"))

    quiet = doc.get("quiet_hours")
    if quiet is not None:
        errors.extend(_quiet_errors(quiet))
    return errors


def _clock_minutes(text: Any) -> Optional[int]:
    if not isinstance(text, str) or len(text) != 5 or text[2] != ":":
        return None
    try:
        hour = int(text[:2])
        minute = int(text[3:])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def _quiet_errors(quiet: Any) -> List[str]:
    if not isinstance(quiet, Mapping):
        return [_err(REFUSE_INVALID_RECORD, "quiet_hours must be an object")]
    errors = _unknown_keys(quiet, _KNOWN_QUIET, "quiet_hours")
    start = _clock_minutes(quiet.get("start"))
    end = _clock_minutes(quiet.get("end"))
    if start is None:
        errors.append(_err(REFUSE_INVALID_RECORD, "quiet_hours.start must be HH:MM"))
    if end is None:
        errors.append(_err(REFUSE_INVALID_RECORD, "quiet_hours.end must be HH:MM"))
    offset = quiet.get("offset_minutes", 0)
    if not isinstance(offset, int) or isinstance(offset, bool):
        errors.append(_err(
            REFUSE_INVALID_RECORD, "quiet_hours.offset_minutes must be an integer"))
    return errors


def in_quiet_hours(quiet: Mapping[str, Any], now: float) -> bool:
    """True when ``now`` (epoch seconds) falls inside the recorded window."""
    start = _clock_minutes(quiet.get("start"))
    end = _clock_minutes(quiet.get("end"))
    offset = int(quiet.get("offset_minutes", 0) or 0)
    if start is None or end is None:
        return False
    minutes = (int(now) // 60 + offset) % (24 * 60)
    if start == end:
        return False
    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end


def _refused(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    verdict: Dict[str, Any] = {
        "status": "refused", "code": code, "responder": None, "reason": reason,
    }
    verdict.update(extra)
    return verdict


def _suppressed(code: str, reason: str, **extra: Any) -> Dict[str, Any]:
    verdict: Dict[str, Any] = {
        "status": "suppressed", "code": code, "responder": None, "reason": reason,
    }
    verdict.update(extra)
    return verdict


def effective_policy(doc: Mapping[str, Any], channel: Any) -> Dict[str, Any]:
    """The validated responder policy for one channel, or a refusal."""
    errors = validate_record(doc)
    if errors:
        return _refused(
            errors[0].split(":", 1)[0], errors[0].split(":", 1)[-1].strip(),
            errors=errors)
    try:
        key = str(channel).strip().lower()
    except Exception:  # pragma: no cover - defensive
        return _refused(REFUSE_UNKNOWN_CHANNEL, "channel is not text")
    native = CHANNEL_MAP.get(key)
    if native is None:
        try:
            native_channel_for(channel)
        except PolicyError as exc:
            code, _, reason = str(exc).partition(": ")
            return _refused(code, reason)
        return _refused(REFUSE_UNKNOWN_CHANNEL, "unsupported channel %r" % (channel,))
    entry = doc["channels"].get(key)
    if not isinstance(entry, Mapping):
        return _refused(
            REFUSE_NO_RESPONDER,
            "no routing record for channel %r; silence is never a policy" % key)
    return {
        "status": "accepted",
        "code": "POLICY",
        "channel": key,
        "native_channel": native,
        "policy": dict(entry),
    }


def resolve(doc: Mapping[str, Any], channel: Any, event: Any = None, *,
            now: Optional[float] = None,
            suppression_state: str = "none",
            lease: Optional["ResponderLease"] = None,
            tenant_id: Optional[str] = None,
            thread_ref: Optional[str] = None,
            holder: str = "responder") -> Dict[str, Any]:
    """Resolve one inbound event to its single responder, or a refusal.

    ``event`` is informational (``contact_id``, ``thread_id``, ``message_id``,
    ``kind``).  It can never change policy: only the operator record does.
    """
    ts = time.time() if now is None else float(now)
    policy = effective_policy(doc, channel)
    if policy["status"] != "accepted":
        return policy
    entry = policy["policy"]
    native = policy["native_channel"]
    kind = "inbound"
    if isinstance(event, Mapping):
        kind = str(event.get("kind") or "inbound")

    evidence: Dict[str, Any] = {
        "policy_location_id": doc.get("location_id"),
        "channel": policy["channel"],
        "native_channel": native,
        "primary_responder": entry.get("primary_responder"),
        "native_mode": entry.get("native_mode"),
        "event_kind": kind,
    }

    if kind == "opt_out" or suppression_state in ("global_stop", "channel_opt_out"):
        return _suppressed(
            SUPPRESS_OPT_OUT,
            "the person opted out; no responder speaks on this channel",
            evidence=dict(evidence, suppression_state=suppression_state))

    if kind == "human_takeover":
        return _suppressed(
            SUPPRESS_HUMAN_TAKEOVER,
            "a human owns this conversation", evidence=evidence)

    active = None
    if lease is not None:
        if not _nonempty(tenant_id) or not _nonempty(thread_ref):
            raise PolicyError("a lease decision requires tenant_id and thread_ref")
        active = lease.active(str(tenant_id), str(thread_ref), now=ts)
    if active is not None:
        if str(active["holder"]).startswith("human:"):
            return _suppressed(
                SUPPRESS_HUMAN_TAKEOVER,
                "human takeover is active until an authorised release",
                evidence=dict(evidence, holder=active["holder"]))
        if isinstance(event, Mapping) and _nonempty(event.get("message_id")):
            claimed = lease.claim(
                tenant_id=str(tenant_id), thread_ref=str(thread_ref),
                event_id=str(event["message_id"]), holder=holder, now=ts)
            if claimed["status"] == "duplicate":
                return _suppressed(
                    SUPPRESS_DUPLICATE_EVENT,
                    "this provider event already owns the reply lease",
                    evidence=dict(evidence, event_id=event["message_id"]))
            if claimed["status"] != "acquired":
                return _suppressed(
                    SUPPRESS_DUPLICATE_EVENT,
                    "another responder holds this conversation thread",
                    evidence=dict(evidence, holder=claimed.get("holder")))
        else:
            return _suppressed(
                SUPPRESS_DUPLICATE_EVENT,
                "another responder holds this conversation thread",
                evidence=dict(evidence, holder=active["holder"]))
    elif lease is not None and isinstance(event, Mapping) and _nonempty(
            event.get("message_id")):
        claimed = lease.claim(
            tenant_id=str(tenant_id), thread_ref=str(thread_ref),
            event_id=str(event["message_id"]), holder=holder, now=ts)
        if claimed["status"] not in ("acquired", "taken_over"):
            return _suppressed(
                SUPPRESS_DUPLICATE_EVENT,
                "another responder holds this conversation thread",
                evidence=dict(evidence, holder=claimed.get("holder")))

    quiet = doc.get("quiet_hours")
    if isinstance(quiet, Mapping) and in_quiet_hours(quiet, ts):
        return {
            "status": "wait",
            "code": WAIT_QUIET_HOURS,
            "responder": None,
            "reason": "the recorded quiet-hours window is open; queue, never send",
            "evidence": evidence,
        }

    primary = entry.get("primary_responder")
    mode = entry.get("native_mode")
    responder = {
        "kind": primary,
        "native_channel": native,
        "native_mode": mode,
        "contact_identity": (entry.get("identity") or {}).get("contact_identity"),
        "thread_identity": (entry.get("identity") or {}).get("thread_identity"),
        "allowed_actions": list(entry.get("allowed_actions") or []),
    }
    if primary == PRIMARY_LOCAL:
        return {
            "status": "accepted", "code": ALLOW_LOCAL, "responder": responder,
            "evidence": evidence,
        }
    if primary == PRIMARY_NATIVE and mode == "suggestive":
        return {
            "status": "accepted", "code": ALLOW_NATIVE_SUGGESTIVE,
            "responder": responder, "evidence": evidence,
        }
    if primary == PRIMARY_NATIVE and mode == "auto-pilot":
        return {
            "status": "accepted", "code": ALLOW_NATIVE_AUTOPILOT,
            "responder": responder, "evidence": evidence,
        }
    return _refused(
        REFUSE_NO_RESPONDER,
        "no responder is admissible for channel %r" % policy["channel"],
        evidence=evidence)


# ---------------------------------------------------------------------------
# The lease: one responder per conversation thread, durable across processes.
# ---------------------------------------------------------------------------

_LEASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS responder_leases (
    tenant_id   TEXT NOT NULL,
    thread_ref  TEXT NOT NULL,
    holder      TEXT NOT NULL,
    event_id    TEXT,
    acquired_at REAL NOT NULL,
    expires_at  REAL,
    released_at REAL,
    PRIMARY KEY (tenant_id, thread_ref)
);
CREATE TABLE IF NOT EXISTS responder_lease_events (
    tenant_id  TEXT NOT NULL,
    thread_ref TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    action     TEXT NOT NULL,
    holder     TEXT NOT NULL,
    event_id   TEXT,
    reason     TEXT NOT NULL DEFAULT '',
    at         REAL NOT NULL,
    PRIMARY KEY (tenant_id, thread_ref, seq)
);
"""

LEASE_TTL_S = 120.0
HUMAN_PREFIX = "human:"


def _required(value: Any, name: str) -> str:
    if not _nonempty(value):
        raise PolicyError("bad_input: %s must be a nonempty string" % name)
    return str(value).strip()


class ResponderLease:
    """The conversation-thread lease shared by local and native dispatch."""

    def __init__(self, path: str) -> None:
        self.path = _required(path, "path")
        self._db = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_LEASE_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def active(self, tenant_id: str, thread_ref: str, *,
               now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        tenant_id = _required(tenant_id, "tenant_id")
        thread_ref = _required(thread_ref, "thread_ref")
        ts = time.time() if now is None else float(now)
        row = self._db.execute(
            "SELECT * FROM responder_leases WHERE tenant_id=? AND thread_ref=?",
            (tenant_id, thread_ref)).fetchone()
        if row is None or row["released_at"] is not None:
            return None
        if row["expires_at"] is not None and float(row["expires_at"]) <= ts:
            return None
        return dict(row)

    def claim(self, *, tenant_id: str, thread_ref: str, event_id: str,
              holder: str = "responder", now: Optional[float] = None,
              ttl_s: float = LEASE_TTL_S) -> Dict[str, Any]:
        """Take the thread lease. Idempotent only for a fresh thread."""
        tenant_id = _required(tenant_id, "tenant_id")
        thread_ref = _required(thread_ref, "thread_ref")
        event_id = _required(event_id, "event_id")
        holder = _required(holder, "holder")
        if not isinstance(ttl_s, (int, float)) or float(ttl_s) <= 0:
            raise PolicyError("bad_input: ttl_s must be positive")
        ts = time.time() if now is None else float(now)
        expires = ts + float(ttl_s)
        with self._tx() as cur:
            row = cur.execute(
                "SELECT * FROM responder_leases WHERE tenant_id=? AND thread_ref=?",
                (tenant_id, thread_ref)).fetchone()
            if row is not None and row["released_at"] is None:
                if row["event_id"] == event_id:
                    return {"status": "duplicate", "holder": row["holder"],
                            "expires_at": row["expires_at"]}
                if row["expires_at"] is None or float(row["expires_at"]) > ts:
                    return {"status": "busy", "holder": row["holder"],
                            "expires_at": row["expires_at"]}
            if row is None:
                cur.execute(
                    "INSERT INTO responder_leases (tenant_id, thread_ref, holder,"
                    " event_id, acquired_at, expires_at, released_at)"
                    " VALUES (?,?,?,?,?,?,NULL)",
                    (tenant_id, thread_ref, holder, event_id, ts, expires))
            else:
                cur.execute(
                    "UPDATE responder_leases SET holder=?, event_id=?,"
                    " acquired_at=?, expires_at=?, released_at=NULL"
                    " WHERE tenant_id=? AND thread_ref=?",
                    (holder, event_id, ts, expires, tenant_id, thread_ref))
            self._event(cur, tenant_id, thread_ref, "claim", holder, event_id,
                        "", ts)
            return {"status": "acquired", "holder": holder, "expires_at": expires}

    def takeover(self, *, tenant_id: str, thread_ref: str, actor: str,
                 reason: str, now: Optional[float] = None) -> Dict[str, Any]:
        """A human takes the thread. No expiry: only release() lifts it."""
        tenant_id = _required(tenant_id, "tenant_id")
        thread_ref = _required(thread_ref, "thread_ref")
        actor = _required(actor, "actor")
        reason = _required(reason, "reason")
        ts = time.time() if now is None else float(now)
        holder = HUMAN_PREFIX + actor
        with self._tx() as cur:
            row = cur.execute(
                "SELECT holder FROM responder_leases WHERE tenant_id=? AND thread_ref=?",
                (tenant_id, thread_ref)).fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO responder_leases (tenant_id, thread_ref, holder,"
                    " event_id, acquired_at, expires_at, released_at)"
                    " VALUES (?,?,?,NULL,?,NULL,NULL)",
                    (tenant_id, thread_ref, holder, ts))
            else:
                cur.execute(
                    "UPDATE responder_leases SET holder=?, event_id=NULL,"
                    " acquired_at=?, expires_at=NULL, released_at=NULL"
                    " WHERE tenant_id=? AND thread_ref=?",
                    (holder, ts, tenant_id, thread_ref))
            self._event(cur, tenant_id, thread_ref, "takeover", holder, None,
                        reason, ts)
        return {"status": "taken_over", "holder": holder, "expires_at": None}

    def release(self, *, tenant_id: str, thread_ref: str, holder: str,
                reason: str = "", now: Optional[float] = None) -> Dict[str, Any]:
        """Release a lease this holder owns. A foreign holder is refused."""
        tenant_id = _required(tenant_id, "tenant_id")
        thread_ref = _required(thread_ref, "thread_ref")
        holder = _required(holder, "holder")
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = cur.execute(
                "SELECT holder, released_at FROM responder_leases"
                " WHERE tenant_id=? AND thread_ref=?",
                (tenant_id, thread_ref)).fetchone()
            if row is None:
                return {"status": "not_held", "holder": None}
            if row["released_at"] is not None:
                return {"status": "already_released", "holder": row["holder"]}
            if row["holder"] != holder:
                return {"status": "refused_foreign_holder", "holder": row["holder"]}
            cur.execute(
                "UPDATE responder_leases SET released_at=? WHERE tenant_id=?"
                " AND thread_ref=?", (ts, tenant_id, thread_ref))
            self._event(cur, tenant_id, thread_ref, "release", holder, None,
                        reason, ts)
        return {"status": "released", "holder": holder}

    def events(self, tenant_id: str, thread_ref: str) -> List[Dict[str, Any]]:
        tenant_id = _required(tenant_id, "tenant_id")
        thread_ref = _required(thread_ref, "thread_ref")
        return [dict(row) for row in self._db.execute(
            "SELECT * FROM responder_lease_events WHERE tenant_id=?"
            " AND thread_ref=? ORDER BY seq", (tenant_id, thread_ref)).fetchall()]

    class _Tx:
        def __init__(self, db: sqlite3.Connection) -> None:
            self.db = db
            self.cur: Optional[sqlite3.Cursor] = None

        def __enter__(self) -> sqlite3.Cursor:
            self.cur = self.db.cursor()
            self.cur.execute("BEGIN IMMEDIATE")
            return self.cur

        def __exit__(self, exc_type, exc, tb) -> bool:
            assert self.cur is not None
            if exc_type is None:
                self.db.commit()
            else:
                self.db.rollback()
            self.cur.close()
            return False

    def _tx(self) -> "ResponderLease._Tx":
        return ResponderLease._Tx(self._db)

    @staticmethod
    def _event(cur: sqlite3.Cursor, tenant_id: str, thread_ref: str,
               action: str, holder: str, event_id: Optional[str],
               reason: str, ts: float) -> None:
        seq = cur.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM responder_lease_events"
            " WHERE tenant_id=? AND thread_ref=?",
            (tenant_id, thread_ref)).fetchone()["n"]
        cur.execute(
            "INSERT INTO responder_lease_events (tenant_id, thread_ref, seq,"
            " action, holder, event_id, reason, at) VALUES (?,?,?,?,?,?,?,?)",
            (tenant_id, thread_ref, int(seq), action, holder, event_id,
             reason or "", ts))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_USAGE = (
    "usage: responder_policy.py validate --record <path>\n"
    "       responder_policy.py channel-map [<channel>]\n"
    "       responder_policy.py resolve --record <path> --channel <c>"
    " [--event <json|path>] [--now <epoch>] [--lease <db>] [--tenant <id>]"
    " [--thread <ref>] [--holder <id>] [--suppression <state>]\n"
    "       responder_policy.py claim --lease <db> --tenant <id> --thread <ref>"
    " --event-id <id> --holder <id> [--ttl <seconds>]\n"
    "       responder_policy.py takeover --lease <db> --tenant <id>"
    " --thread <ref> --actor <who> --reason <why>\n"
    "       responder_policy.py release --lease <db> --tenant <id>"
    " --thread <ref> --holder <id> [--reason <why>]\n"
    "       responder_policy.py self-check\n"
)

_FLAGS = {
    "--record", "--channel", "--event", "--now", "--lease", "--tenant",
    "--thread", "--holder", "--event-id", "--ttl", "--actor", "--reason",
    "--suppression",
}


def _usage(message: Optional[str] = None) -> int:
    if message:
        sys.stderr.write(message + "\n")
    sys.stderr.write(_USAGE)
    return 2


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _parse_event(value: Optional[str]) -> Any:
    if value is None:
        return None
    if os.path.isfile(value):
        return _load_json(value)
    try:
        return json.loads(value)
    except ValueError as exc:
        raise PolicyError("invalid JSON event: %s" % exc)


def _emit(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _cmd_validate(args: Dict[str, str]) -> int:
    doc = _load_json(args["record"])
    errors = validate_record(doc)
    _emit({"status": "refused" if errors else "accepted", "errors": errors})
    return 0 if not errors else 1


def _cmd_channel_map(args: Dict[str, str]) -> int:
    requested = args.get("channel")
    if requested is None:
        _emit({"channels": CHANNEL_MAP, "native": list(NATIVE_CHANNELS),
               "unsupported": UNSUPPORTED_CHANNELS})
        return 0
    try:
        _emit({"channel": requested, "native_channel": native_channel_for(requested)})
        return 0
    except PolicyError as exc:
        code, _, reason = str(exc).partition(": ")
        _emit({"status": "refused", "code": code, "reason": reason})
        return 1


def _cmd_resolve(args: Dict[str, str]) -> int:
    doc = _load_json(args["record"])
    event = _parse_event(args.get("event"))
    now = float(args["now"]) if args.get("now") else None
    lease = None
    try:
        if args.get("lease"):
            lease = ResponderLease(args["lease"])
        verdict = resolve(
            doc, args.get("channel"), event, now=now,
            suppression_state=args.get("suppression") or "none",
            lease=lease, tenant_id=args.get("tenant"),
            thread_ref=args.get("thread"), holder=args.get("holder") or "responder")
    finally:
        if lease is not None:
            lease.close()
    _emit(verdict)
    return 0 if verdict["status"] in ("accepted", "suppressed", "wait") else 1


def _cmd_claim(args: Dict[str, str]) -> int:
    lease = ResponderLease(args["lease"])
    try:
        ttl = float(args.get("ttl") or LEASE_TTL_S)
        result = lease.claim(
            tenant_id=args["tenant"], thread_ref=args["thread"],
            event_id=args["event_id"], holder=args.get("holder") or "responder",
            ttl_s=ttl)
    finally:
        lease.close()
    _emit(result)
    return 0 if result["status"] == "acquired" else 1


def _cmd_takeover(args: Dict[str, str]) -> int:
    lease = ResponderLease(args["lease"])
    try:
        result = lease.takeover(
            tenant_id=args["tenant"], thread_ref=args["thread"],
            actor=args["actor"], reason=args["reason"])
    finally:
        lease.close()
    _emit(result)
    return 0


def _cmd_release(args: Dict[str, str]) -> int:
    lease = ResponderLease(args["lease"])
    try:
        result = lease.release(
            tenant_id=args["tenant"], thread_ref=args["thread"],
            holder=args["holder"], reason=args.get("reason") or "")
    finally:
        lease.close()
    _emit(result)
    return 0 if result["status"] in ("released", "already_released") else 1


def _self_check() -> int:
    """Assert-based self-check over the lease and a minimal record."""
    import tempfile

    root = tempfile.mkdtemp(prefix="responder-policy-selfcheck-")
    db = os.path.join(root, "lease.sqlite")
    lease = ResponderLease(db)
    passed = 0

    def ok(condition: bool, label: str) -> None:
        nonlocal passed
        if not condition:
            raise AssertionError("FAIL: " + label)
        passed += 1

    record = {
        "schema_version": 1,
        "record_id": "responders/synthetic",
        "location_id": "loc_synthetic",
        "channels": {
            "sms": {
                "native_channel": "SMS",
                "primary_responder": PRIMARY_LOCAL,
                "native_mode": "off",
                "handoff": {"trigger": "human_request", "pauses_automation": True,
                            "resumes_on": "operator_release"},
                "workflow_sends": {"allowed": False, "deduplicates_with_primary": True,
                                   "reason": "primary owns sends"},
                "identity": {"contact_identity": IDENTITY_CONTACT,
                             "thread_identity": "conversation_id"},
                "allowed_actions": ["reply"],
                "limits": {"opt_out": True, "quiet_hours": True,
                           "client_test_mode": True},
            }
        },
        "native_prompt": {"effective_prompt_field": "fullPrompt"},
    }
    ok(validate_record(record) == [], "a minimal local-only record validates")
    first = resolve(record, "sms", {"kind": "inbound", "message_id": "m1"},
                    lease=lease, tenant_id="t", thread_ref="th")
    ok(first["code"] == ALLOW_LOCAL, "local brain owns an off-mode channel")
    second = resolve(record, "sms", {"kind": "inbound", "message_id": "m2"},
                     lease=lease, tenant_id="t", thread_ref="th")
    ok(second["code"] == SUPPRESS_DUPLICATE_EVENT,
       "a second contemporaneous message is suppressed")
    lease.release(tenant_id="t", thread_ref="th", holder="responder")
    returning = resolve(record, "sms", {"kind": "returning_contact",
                                        "message_id": "m3"},
                        lease=lease, tenant_id="t", thread_ref="th")
    ok(returning["code"] == ALLOW_LOCAL, "a returning contact is allowed once the lease frees")
    lease.takeover(tenant_id="t", thread_ref="th", actor="operator",
                   reason="customer asked for a person")
    human = resolve(record, "sms", {"kind": "inbound", "message_id": "m4"},
                    lease=lease, tenant_id="t", thread_ref="th")
    ok(human["code"] == SUPPRESS_HUMAN_TAKEOVER, "a human takeover suppresses the bot")
    lease.close()
    print("OK %d PASS" % passed)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        return _usage("a command is required")
    command = args_list.pop(0)
    if command not in ("validate", "channel-map", "resolve", "claim", "takeover",
                       "release", "self-check"):
        return _usage("unknown command %r" % (command,))
    args: Dict[str, str] = {}
    while args_list:
        flag = args_list.pop(0)
        if flag not in _FLAGS:
            return _usage("unknown argument %r" % (flag,))
        if not args_list:
            return _usage("%s needs a value" % flag)
        args[flag.lstrip("-").replace("-", "_")] = args_list.pop(0)

    required: Dict[str, Tuple[str, ...]] = {
        "validate": ("record",),
        "resolve": ("record", "channel"),
        "claim": ("lease", "tenant", "thread", "event_id"),
        "takeover": ("lease", "tenant", "thread", "actor", "reason"),
        "release": ("lease", "tenant", "thread", "holder"),
    }
    for name in required.get(command, ()):
        if not args.get(name):
            return _usage("--%s is required for %s" % (name.replace("_", "-"), command))
    try:
        if command == "validate":
            return _cmd_validate(args)
        if command == "channel-map":
            return _cmd_channel_map(args)
        if command == "resolve":
            return _cmd_resolve(args)
        if command == "claim":
            return _cmd_claim(args)
        if command == "takeover":
            return _cmd_takeover(args)
        if command == "release":
            return _cmd_release(args)
        return _self_check()
    except PolicyError as exc:
        return _usage(str(exc))
    except (OSError, UnicodeError, ValueError) as exc:
        return _usage("cannot read or check the input: %s" % (exc,))


if __name__ == "__main__":
    sys.exit(main())
