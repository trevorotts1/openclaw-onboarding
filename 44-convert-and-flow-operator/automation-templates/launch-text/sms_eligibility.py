#!/usr/bin/env python3
"""Pre-send eligibility gate for the launch-text SMS sets (stdlib only).

Call `evaluate_send()` IMMEDIATELY BEFORE a marketing send, with the
contact's current state. It is a send-time gate, not a build-time check:
consent, suppression, quiet hours, the launch deadline and the aggregate
contact-level marketing send count are read at the moment before the
provider call, so a STOP that landed after the workflow was built still
wins.

Classification is explicit: `doors_open`, `last_call` and
`abandoned_checkout` are marketing and consume the aggregate contact cap;
`opt_in_confirmation`, `keyword_opt_in`, `event_reminder` and
`access_link` are operational, never consume that cap, and are never
blocked by the launch deadline.

`verify_saved_conditions()` proves the rules are SAVED NATIVE
conditions in the workflow export. Prose in a purpose/copy/note field
does not satisfy a rule.

The AI nudge template (L10) uses this same cap/STOP contract.

    python3 test_sms_eligibility.py
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timedelta

MARKETING_KINDS = frozenset({"doors_open", "last_call", "abandoned_checkout"})
OPERATIONAL_KINDS = frozenset({
    "opt_in_confirmation", "keyword_opt_in", "event_reminder", "access_link",
})
# Aggregate marketing MESSAGES per contact per launch. The catalog's
# promotional sets total exactly 5 (1 + 2 + 2), so this is also the
# ceiling a fully-engaged contact can ever reach.
MARKETING_CAP = 5

QUIET_START = 8 * 60          # 08:00
QUIET_END = 21 * 60           # 21:00, exclusive
DEADLINE_SLOT = 20 * 60       # deadline steps move earlier to 20:00
EVENT_EARLY_SHIFT = 10        # minutes; event copy says "in 10 minutes"

SUPPRESSION_VALUES = frozenset({
    "stop", "sms-opted-out", "opted-out", "unsubscribe", "unsubscribed",
})
SHORTENER_HOSTS = frozenset({
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "buff.ly",
    "is.gd", "cutt.ly", "rebrand.ly", "shorturl.at",
})
LINK_RE = re.compile(r"https?://[^\s<>\"']+")
PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")
# STOP is required in every message by the shared contract.
REQUIRES_LINK = frozenset({
    "doors_open", "last_call", "abandoned_checkout", "access_link",
    "event_reminder",
})
GSM7_BASE = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXT = frozenset("^{}\\[~]|€")


def category(kind: str) -> str:
    """`marketing` or `operational`; unknown kinds are refused, never guessed."""
    if kind in MARKETING_KINDS:
        return "marketing"
    if kind in OPERATIONAL_KINDS:
        return "operational"
    raise ValueError("unknown text set kind: %r" % (kind,))


# ---------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------

def _local(value, tz_name=None) -> datetime:
    """Naive recipient-local wall time.

    Aware ISO values are converted when an IANA name is supplied;
    otherwise an aware value is treated as already expressed in the
    recipient's local offset. Naive values are local by definition.
    """
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is not None and tz_name:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            return dt.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
        except ZoneInfoNotFoundError:
            raise ValueError("unknown timezone: %r" % (tz_name,))
    return dt.replace(tzinfo=None)


def _minute_of_day(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _at(day, minute: int) -> datetime:
    if not isinstance(day, datetime):
        day = datetime.combine(day, datetime.min.time())
    return day.replace(hour=minute // 60, minute=minute % 60,
                       second=0, microsecond=0)


def _in_window(minute: int) -> bool:
    return QUIET_START <= minute < QUIET_END


def _earlier_slot(scheduled, deadline, kind, anchor, now):
    """Latest permitted instant before the deadline, or None.

    Deadline steps (doors_open / last_call / abandoned_checkout) move
    earlier to 20:00 per the catalog. Event reminders may shift earlier
    only by the copy's own 10-minute claim.
    """
    if deadline is None:
        return None
    if kind == "event_reminder":
        candidate = min(deadline - timedelta(minutes=1),
                        _at(deadline.date(), QUIET_END - 1))
        if scheduled - candidate > timedelta(minutes=EVENT_EARLY_SHIFT):
            return None
    else:
        candidate = _at(deadline.date(), DEADLINE_SLOT)
        if candidate >= deadline:
            candidate = _at(deadline.date() - timedelta(days=1), DEADLINE_SLOT)
        if candidate >= deadline:
            candidate = deadline - timedelta(minutes=1)
    if _minute_of_day(candidate) < QUIET_START:
        return None
    if candidate > deadline:
        return None
    if anchor is not None and candidate < anchor:
        return None  # the copy would be false if sent before its anchor
    if now is not None and candidate < now:
        return None
    return candidate


def resolve_send_time(scheduled: datetime, *, category_name: str, kind: str,
                      now=None, deadline=None, anchor=None):
    """Return (action, send_at, reason).

    action is `send`, `hold` or `skip`. A quiet-hours conflict is always
    resolved to a permitted earlier time or an explicit skip; it is
    never resolved to a later time that breaks the deadline.
    """
    if _in_window(_minute_of_day(scheduled)):
        if now is not None and scheduled < now:
            return "skip", None, "past_due"
        if anchor is not None and scheduled < anchor:
            return "skip", None, "before_anchor"
        return "send", scheduled, "inside_quiet_hours"

    if scheduled < _at(scheduled.date(), QUIET_START):
        candidate = _at(scheduled.date(), QUIET_START)
    else:
        candidate = _at(scheduled.date() + timedelta(days=1), QUIET_START)

    if deadline is not None and candidate > deadline:
        if category_name == "marketing" or kind == "event_reminder":
            earlier = _earlier_slot(scheduled, deadline, kind, anchor, now)
            if earlier is not None:
                return "hold", earlier, "quiet_hours_moved_earlier"
            return "skip", None, "quiet_hours_conflict_no_permitted_slot"
        return "skip", None, "past_launch_deadline"

    if now is not None and candidate < now:
        return "skip", None, "past_due"
    if anchor is not None and candidate < anchor:
        return "skip", None, "before_anchor"
    return "hold", candidate, "quiet_hours_held"


# ---------------------------------------------------------------------------
# content helpers
# ---------------------------------------------------------------------------

def render(template: str, variables: dict) -> str:
    """Merge placeholders; unknown tokens raise (never send raw braces)."""
    variables = dict(variables or {})
    variables.setdefault("first_name", "there")

    def replace(match):
        token = match.group(1)
        if token not in variables:
            raise ValueError("unknown placeholder {{%s}}" % token)
        return str(variables[token])

    return PLACEHOLDER_RE.sub(replace, template)


def _links(text: str) -> list[str]:
    return [link.rstrip(".,;:!?)") for link in LINK_RE.findall(text)]


def _host(link: str) -> str:
    rest = link.split("://", 1)[1]
    return rest.split("/", 1)[0].split(":", 1)[0].lower()


def _gsm7_units(text: str):
    units = 0
    for char in text:
        if char in GSM7_EXT:
            units += 2
        elif char in GSM7_BASE:
            units += 1
        else:
            return None
    return units


def count_segments(text: str):
    """Return (encoding, segments). Extension chars count as 2 septets."""
    units = _gsm7_units(text)
    if units is not None:
        return "gsm7", 1 if units <= 160 else int(math.ceil(units / 153.0))
    utf16_units = len(text.encode("utf-16-le")) // 2
    return "ucs2", 1 if utf16_units <= 70 else int(math.ceil(utf16_units / 67.0))


def validate_content(kind: str, text: str, *, allowlist=None, max_segments=2,
                     price_per_segment_usd=None):
    """Final merged text: encoding, links, STOP, segments and cost."""
    errors = []
    if not text or not text.strip():
        errors.append("text is empty")
    if PLACEHOLDER_RE.search(text):
        errors.append("unresolved placeholder in merged text")
    if "\n" in text or "\r" in text:
        errors.append("SMS must be a single line")
    if any(ord(char) < 32 for char in text):
        errors.append("control character in merged text")
    if unicodedata.normalize("NFC", text) != text:
        errors.append("text is not NFC-normalized")
    if "STOP" not in text:
        errors.append("STOP missing")
    if kind == "opt_in_confirmation" and "HELP" not in text:
        errors.append("HELP missing from opt-in confirmation")

    links = _links(text)
    for link in links:
        if not link.startswith("https://"):
            errors.append("link is not https: %s" % link)
            continue
        host = _host(link)
        if host in SHORTENER_HOSTS:
            errors.append("link shortener refused: %s" % host)
        if allowlist is not None and host not in allowlist:
            errors.append("link host not allowlisted: %s" % host)

    if kind in REQUIRES_LINK and not links:
        errors.append("message requires one link")

    encoding, segments = count_segments(text)
    if segments > max_segments:
        errors.append("%d segments exceeds the %d-segment ceiling"
                      % (segments, max_segments))
    cost = None
    if price_per_segment_usd is not None:
        cost = round(segments * float(price_per_segment_usd), 6)
    return {
        "ok": not errors,
        "errors": errors,
        "encoding": encoding,
        "segments": segments,
        "cost_usd": cost,
        "links": links,
    }


# ---------------------------------------------------------------------------
# send-time gate
# ---------------------------------------------------------------------------

def evaluate_send(send: dict) -> dict:
    """Evaluate ONE send immediately before the provider call (marketing:
    immediately before every marketing send, not once per workflow).

    send keys:
      kind, template, variables
      send_at            ISO string or datetime (recipient-local)
      timezone           IANA name, used only to convert an aware send_at
      now                ISO/datetime; when present, past-due sends skip
      deadline           launch deadline (doors_close_at)
      anchor             earliest truthful instant the copy depends on
      contact            consent, sms_subscribed, tags, suppression,
                         marketing_sends, operational_sends
      a2p_ready          bool
      price_per_segment_usd, max_segments, link_allowlist
    """
    checks = []

    def add(rule, ok, detail):
        checks.append({"rule": rule, "ok": bool(ok), "detail": detail})
        return ok

    def decision(action, reason, send_at=None, content=None):
        return {
            "kind": send.get("kind"),
            "category": cat,
            "action": action,
            "send_at": send_at.isoformat() if send_at else None,
            "reason": reason,
            "checks": checks,
            "text": content["text"] if content else None,
            "encoding": content["encoding"] if content else None,
            "segments": content["segments"] if content else None,
            "cost_usd": content["cost_usd"] if content else None,
        }

    try:
        cat = category(send.get("kind"))
    except ValueError as exc:
        return {
            "kind": send.get("kind"), "category": None, "action": "skip",
            "send_at": None, "reason": str(exc), "checks": [],
            "text": None, "encoding": None, "segments": None, "cost_usd": None,
        }

    contact = send.get("contact") or {}
    tz_name = send.get("timezone")

    if not send.get("send_at"):
        add("send_at", False, "a send time is required")
        return decision("skip", "failed: send_at", None, None)

    # 1. A2P readiness: drafts only until 10DLC approval.
    add("a2p_ready", send.get("a2p_ready") is True,
        "A2P 10DLC must be approved before any send")

    # 2. Suppression wins over everything, operational included.
    suppression = set()
    for value in list(contact.get("tags") or []) + \
            list(contact.get("suppression") or []):
        suppression.add(str(value).strip().lower())
    add("not_suppressed", not (suppression & SUPPRESSION_VALUES),
        "sms-opted-out / STOP wins over every set")

    # 3. Consent, classified by category.
    consent = contact.get("consent")
    subscribed = contact.get("sms_subscribed") is True
    if send.get("kind") in ("opt_in_confirmation", "keyword_opt_in"):
        add("consent", consent in ("pending", "confirmed"),
            "the opt-in handshake needs a pending or confirmed consent")
    else:
        add("consent", consent == "confirmed" and subscribed,
            "%s requires confirmed consent and sms-subscribed" % cat)

    # 4. Aggregate contact-level marketing count (operational is separate).
    try:
        marketing_sends = max(0, int(contact.get("marketing_sends") or 0))
        operational_sends = max(0, int(contact.get("operational_sends") or 0))
    except (TypeError, ValueError):
        add("aggregate_contact_cap", False, "send counts must be integers")
        return decision("skip", "failed: aggregate_contact_cap", None, None)
    if cat == "marketing":
        add("aggregate_contact_cap",
            marketing_sends + 1 <= MARKETING_CAP,
            "%d marketing sends already, cap %d" % (marketing_sends, MARKETING_CAP))
    else:
        add("aggregate_contact_cap", True,
            "operational; %d operational sends do not consume the cap"
            % operational_sends)

    # 5. Final merged text, link, encoding, segments and cost.
    try:
        text = render(send.get("template") or "", send.get("variables") or {})
        content = validate_content(
            send.get("kind"), text,
            allowlist=send.get("link_allowlist"),
            max_segments=send.get("max_segments", 2),
            price_per_segment_usd=send.get("price_per_segment_usd"),
        )
        content["text"] = text
        add("content", content["ok"], "; ".join(content["errors"]) or "clean")
    except ValueError as exc:
        content = None
        add("content", False, str(exc))

    # 6. Quiet hours, resolved before the deadline check.
    try:
        scheduled = _local(send["send_at"], tz_name)
        now = _local(send["now"], tz_name) if send.get("now") else None
        deadline = _local(send["deadline"], tz_name) if send.get("deadline") else None
        anchor = _local(send["anchor"], tz_name) if send.get("anchor") else None
    except ValueError as exc:
        # Unknown timezone or unparsable time: unknown timezone blocks.
        add("quiet_hours", False, str(exc))
        return decision("skip", "failed: quiet_hours", None, content)
    action, send_at, reason = resolve_send_time(
        scheduled, category_name=cat, kind=send["kind"], now=now,
        deadline=deadline if cat == "marketing" or
        send["kind"] == "event_reminder" else None,
        anchor=anchor,
    )
    add("quiet_hours", reason != "quiet_hours_conflict_no_permitted_slot"
        and not reason.startswith("past_"), reason)

    # 7. Launch deadline for marketing only; operational stays deliverable.
    if cat == "marketing" and deadline is not None and send_at is not None:
        add("launch_deadline", send_at <= deadline,
            "send %s must be <= %s" % (send_at.isoformat(), deadline.isoformat()))
    else:
        add("launch_deadline", True, "not a marketing deadline step")

    if action == "skip" or reason.startswith("past_"):
        return decision("skip", reason, None, content)
    if any(not check["ok"] for check in checks):
        failed = [check["rule"] for check in checks if not check["ok"]]
        return decision("skip", "failed: " + ", ".join(failed), None, content)
    if send_at is None:
        return decision("skip", "no permitted send time", None, content)
    if now is not None and send_at > now:
        return decision("hold", reason, send_at, content)
    return decision("send", "all pre-send checks passed", send_at, content)


# ---------------------------------------------------------------------------
# saved native conditions
# ---------------------------------------------------------------------------

EXPECTED_CONDITIONS = {
    "marketing": (
        ("consent", {"type": "tag_present", "value": "sms-subscribed"}),
        ("suppression", {"type": "tag_absent", "value": "sms-opted-out"}),
        ("aggregate_contact_cap", {"type": "field_lt",
                                   "field": "contact_marketing_sends",
                                   "value": MARKETING_CAP}),
        ("quiet_hours", {"type": "time_window", "start": "08:00",
                         "end": "21:00", "timezone": "recipient_local"}),
        ("launch_deadline", {"type": "deadline", "anchor": "doors_close_at"}),
    ),
    "operational": (
        ("suppression", {"type": "tag_absent", "value": "sms-opted-out"}),
        ("quiet_hours", {"type": "time_window", "start": "08:00",
                         "end": "21:00", "timezone": "recipient_local"}),
    ),
}

# Native step types that carry executable conditions. Anything else is
# prose or an action and can never satisfy a rule.
CONDITION_STEP_TYPES = frozenset({
    "if_else", "condition", "filter", "wait_until", "wait",
})
PROSE_FIELDS = ("name", "purpose", "copy", "message", "notes", "description")
PROSE_HINTS = {
    "consent": ("sms-subscribed", "consent"),
    "suppression": ("sms-opted-out", "STOP", "suppress"),
    "aggregate_contact_cap": ("contact_marketing_sends", "cap", "aggregate"),
    "quiet_hours": ("08:00", "21:00", "quiet hours"),
    "launch_deadline": ("doors_close_at", "deadline"),
}


def _matches(expected: dict, observed: dict) -> bool:
    if not isinstance(observed, dict) or observed.get("disabled") is True:
        return False
    kind = expected["type"]
    op = str(observed.get("operator") or "").lower()
    if kind == "tag_present":
        return expected["value"] == observed.get("value") and (
            observed.get("type") == "tag_present"
            or (observed.get("type") == "tag" and op in ("is", "present", "has")))
    if kind == "tag_absent":
        return expected["value"] == observed.get("value") and (
            observed.get("type") == "tag_absent"
            or (observed.get("type") == "tag"
                and op in ("is_not", "not_present", "absent", "does_not_have")))
    if kind == "field_lt":
        return (expected["field"] == observed.get("field")
                and observed.get("value") == expected["value"]
                and (observed.get("type") == "field_lt"
                     or (observed.get("type") == "field" and op == "lt")))
    if kind == "time_window":
        return (observed.get("type") == "time_window"
                and observed.get("start") == expected["start"]
                and observed.get("end") == expected["end"]
                and observed.get("timezone") == expected["timezone"])
    if kind == "deadline":
        return (observed.get("type") == "deadline"
                and observed.get("anchor") == expected["anchor"])
    return False


def verify_saved_conditions(snapshot: dict, category_name: str) -> dict:
    """Prove the rules are saved native conditions, not template prose."""
    steps = (snapshot or {}).get("steps")
    if not isinstance(steps, list):
        return {"ok": False, "missing": ["workflow.steps"], "prose_only": [],
                "found": {}}

    native = []
    prose = []
    for step in steps:
        if not isinstance(step, dict) or step.get("disabled") is True:
            continue
        for key in PROSE_FIELDS:
            if isinstance(step.get(key), str):
                prose.append(step[key])
        if step.get("type") in CONDITION_STEP_TYPES:
            for condition in step.get("conditions") or []:
                if isinstance(condition, dict):
                    native.append(condition)

    found, missing, prose_only = {}, [], []
    for rule, expected in EXPECTED_CONDITIONS[category_name]:
        ok = any(_matches(expected, condition) for condition in native)
        found[rule] = ok
        if not ok:
            missing.append(rule)
            haystack = " \n".join(prose).lower()
            if any(hint.lower() in haystack for hint in PROSE_HINTS[rule]):
                prose_only.append(rule)
    return {"ok": not missing, "missing": missing,
            "prose_only": prose_only, "found": found}
