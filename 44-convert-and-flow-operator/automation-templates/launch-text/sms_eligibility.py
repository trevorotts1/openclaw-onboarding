#!/usr/bin/env python3
"""Pre-send eligibility gate for the launch-text SMS sets (stdlib only).

Call `evaluate_send()` IMMEDIATELY BEFORE a marketing send, with the
contact's current state. It is a send-time gate, not a build-time check:
consent, suppression, quiet hours, the launch deadline and the aggregate
contact-level marketing send count are read at the moment before the
provider call, so a STOP that landed after the workflow was built still
wins.

Classification is explicit: `doors_open`, `last_call`,
`abandoned_checkout` and `buyer_followup_offer` are marketing and consume
the aggregate contact cap;
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

MARKETING_KINDS = frozenset({"doors_open", "last_call", "abandoned_checkout",
                             "buyer_followup_offer"})
# A buyer follow-up offer is a promotional text sent to someone who already
# bought, after the launch has closed (a challenge or membership invitation).
# It is marketing in every respect (consent, STOP, cap, quiet hours, one link)
# but its deadline is the OFFER'S OWN deadline, never the launch's doors_close_at:
# the caller must pass that per-offer deadline as `deadline`, and a send without
# one is refused (fail closed, never defaulted to the launch deadline).
OFFER_DEADLINE_KINDS = frozenset({"buyer_followup_offer"})
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
    "event_reminder", "buyer_followup_offer",
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

    # 6b. A buyer follow-up offer carries its OWN deadline; none given = refused.
    if send["kind"] in OFFER_DEADLINE_KINDS and deadline is None:
        add("launch_deadline", False,
            "%s needs its own per-offer deadline (not the launch's doors_close_at)"
            % send["kind"])
    # 7. Launch deadline for marketing only; operational stays deliverable.
    elif cat == "marketing" and deadline is not None and send_at is not None:
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


# ---------------------------------------------------------------------------
# per-account SMS vocabulary (SWB-072)
# ---------------------------------------------------------------------------
# An account may name its consent tag, suppression tags, contact-cap field,
# quiet-hours window and launch-deadline source differently from the catalog
# defaults. A small JSON mapping file says so (`--vocab path`). The mapping
# renames WHAT is looked for; every rule must still be present as a native
# saved condition, so nothing here can switch a rule off. A mapping may be
# stricter than the defaults (a narrower window, a smaller cap) and never
# looser: a window wider than 08:00-21:00 or a cap above MARKETING_CAP is
# refused. Without a mapping the literal defaults above apply unchanged.
#
#   {"consent_tag": "...", "suppression_tags": ["..."],
#    "cap_field": "...", "cap_max": 5,
#    "quiet_hours": {"start": "09:00", "end": "20:00"},
#    "deadline": {"source": "native_wait_until_date", "date": "YYYY-MM-DD",
#                 "time": "HH:MM", "timezone": "America/New_York",
#                 "when_passed": "exit", "anchor": "doors_close_at"}}

VOCAB_KEYS = frozenset({"consent_tag", "suppression_tags", "cap_field",
                        "cap_max", "quiet_hours", "deadline"})
DEADLINE_SOURCES = frozenset({"condition", "native_wait_until_date"})
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("vocab %s must be a non-empty string" % label)
    return value


def load_vocab(raw) -> dict:
    """Validate a mapping object and return the effective vocabulary
    (defaults filled in). Raises ValueError for anything unknown, malformed
    or looser than the defaults; never guesses."""
    if not isinstance(raw, dict):
        raise ValueError("vocab must be a JSON object")
    unknown = sorted(set(raw) - VOCAB_KEYS)
    if unknown:
        raise ValueError("vocab has unknown keys: %s" % ",".join(unknown))
    vocab = {"consent_tag": "sms-subscribed",
             "suppression_tags": ["sms-opted-out"],
             "cap_field": "contact_marketing_sends",
             "cap_max": MARKETING_CAP,
             "quiet_hours": {"start": "08:00", "end": "21:00"},
             "deadline": {"source": "condition", "anchor": "doors_close_at"}}
    if "consent_tag" in raw:
        vocab["consent_tag"] = _nonempty(raw["consent_tag"], "consent_tag")
    if "suppression_tags" in raw:
        tags = raw["suppression_tags"]
        if not isinstance(tags, list) or not tags:
            raise ValueError("vocab suppression_tags must be a non-empty list")
        vocab["suppression_tags"] = [_nonempty(t, "suppression_tags entry") for t in tags]
    if "cap_field" in raw:
        vocab["cap_field"] = _nonempty(raw["cap_field"], "cap_field")
    if "cap_max" in raw:
        cap = raw["cap_max"]
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= MARKETING_CAP:
            raise ValueError("vocab cap_max must be an integer 1..%d" % MARKETING_CAP)
        vocab["cap_max"] = cap
    if "quiet_hours" in raw:
        qh = raw["quiet_hours"]
        if not isinstance(qh, dict) or set(qh) != {"start", "end"}:
            raise ValueError("vocab quiet_hours needs exactly start and end")
        start, end = qh["start"], qh["end"]
        if not (isinstance(start, str) and isinstance(end, str)
                and _HHMM_RE.match(start) and _HHMM_RE.match(end)):
            raise ValueError("vocab quiet_hours must be HH:MM strings")
        lo, hi = "%02d:00" % (QUIET_START // 60), "%02d:00" % (QUIET_END // 60)
        if not (lo <= start < end <= hi):
            raise ValueError("vocab quiet_hours must sit inside %s-%s" % (lo, hi))
        vocab["quiet_hours"] = {"start": start, "end": end}
    if "deadline" in raw:
        dl = raw["deadline"]
        if not isinstance(dl, dict):
            raise ValueError("vocab deadline must be an object")
        source = dl.get("source", "condition")
        if source not in DEADLINE_SOURCES:
            raise ValueError("vocab deadline.source must be one of %s" % sorted(DEADLINE_SOURCES))
        out = {"source": source, "anchor": _nonempty(dl.get("anchor", "doors_close_at"), "deadline.anchor")}
        if source == "native_wait_until_date":
            date, time_ = dl.get("date"), dl.get("time")
            if not (isinstance(date, str) and _DATE_RE.match(date)):
                raise ValueError("vocab deadline.date must be YYYY-MM-DD")
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("vocab deadline.date is not a real date")
            if not (isinstance(time_, str) and _HHMM_RE.match(time_)):
                raise ValueError("vocab deadline.time must be HH:MM")
            out.update({"date": date, "time": time_,
                        "timezone": _nonempty(dl.get("timezone"), "deadline.timezone"),
                        # A late entrant must leave, never fall through to a send.
                        "when_passed": _nonempty(dl.get("when_passed", "exit"), "deadline.when_passed")})
        vocab["deadline"] = out
    return vocab


def expected_rules(category_name: str, vocab=None):
    """[(rule, [expected conditions...])] for a category. With no vocab this is
    exactly EXPECTED_CONDITIONS; with one, the account's names are substituted."""
    if vocab is None:
        return [(rule, [expected]) for rule, expected in EXPECTED_CONDITIONS[category_name]]
    suppression = [{"type": "tag_absent", "value": t} for t in vocab["suppression_tags"]]
    quiet = {"type": "time_window", "start": vocab["quiet_hours"]["start"],
             "end": vocab["quiet_hours"]["end"], "timezone": "recipient_local"}
    if category_name == "operational":
        return [("suppression", suppression), ("quiet_hours", [quiet])]
    return [
        ("consent", [{"type": "tag_present", "value": vocab["consent_tag"]}]),
        ("suppression", suppression),
        ("aggregate_contact_cap", [{"type": "field_lt", "field": vocab["cap_field"],
                                    "value": vocab["cap_max"]}]),
        ("quiet_hours", [quiet]),
        ("launch_deadline", [{"type": "deadline", "anchor": vocab["deadline"]["anchor"]}]),
    ]


def _wait_hhmm(attrs):
    """HH:MM of a native specific-date wait node, or None."""
    try:
        hour, minute = int(attrs.get("specificTimeHour")), int(attrs.get("specificTimeMinute") or 0)
    except (TypeError, ValueError):
        return None
    period = str(attrs.get("specificTimePeriod") or "").upper()
    if period not in ("AM", "PM") or not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None
    if int(attrs.get("specificTimeSecond") or 0) != 0:
        return None
    return "%02d:%02d" % (hour % 12 + (12 if period == "PM" else 0), minute)


def _is_deadline_wait(step, deadline) -> bool:
    """A saved native wait-until-date node that IS the vocabulary's launch
    deadline: enabled, exact date and time, no offsets, and a contact who
    arrives after it leaves (`when_passed`). A wait for any other moment, or
    one that lets late contacts through, is a send time, not a deadline."""
    if not isinstance(step, dict) or str(step.get("type") or "").lower() != "wait":
        return False
    attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
    if step.get("disabled") is True or attrs.get("disabled") is True:
        return False
    return (attrs.get("type") == "specific_date"
            and attrs.get("specificDate") == deadline["date"]
            and _wait_hhmm(attrs) == deadline["time"]
            and attrs.get("specificDatePassed") == deadline["when_passed"]
            and not any(attrs.get(k) for k in ("specificDateOffsetDays", "specificDateOffsetHours",
                                               "specificDateOffsetMinutes"))
            and attrs.get("specificDateProceed", "on") == "on")


def deadline_covered(raw_steps, sms_steps, deadline, export_timezone=None) -> bool:
    """True only when EVERY SMS step sits downstream of a native deadline wait
    (walking `parentKey` / `parent` links up the saved canvas)."""
    if not sms_steps:
        return False
    if export_timezone not in (None, "account", deadline["timezone"]):
        return False
    by_id = {s.get("id"): s for s in raw_steps if isinstance(s, dict) and s.get("id")}
    for sms in sms_steps:
        seen, stack, hit = set(), [sms], False
        while stack and not hit:
            node = stack.pop()
            for key in ("parentKey", "parent"):
                pid = node.get(key)
                if isinstance(pid, str) and pid not in seen and pid in by_id:
                    seen.add(pid)
                    parent = by_id[pid]
                    if _is_deadline_wait(parent, deadline):
                        hit = True
                        break
                    stack.append(parent)
        if not hit:
            return False
    return True


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
        if observed.get("type") == "native_time_window":
            # The workflow's own saved send window (GoHighLevel `window`).
            # A window INSIDE the quiet-hours bounds is as strict or stricter.
            return (
                observed.get("condition") == "when"
                and isinstance(observed.get("start"), str)
                and isinstance(observed.get("end"), str)
                and expected["start"] <= observed["start"] < observed["end"] <= expected["end"]
            )
        return (observed.get("type") == "time_window"
                and observed.get("start") == expected["start"]
                and observed.get("end") == expected["end"]
                and observed.get("timezone") == expected["timezone"])
    if kind == "deadline":
        return (observed.get("type") == "deadline"
                and observed.get("anchor") == expected["anchor"])
    return False


def verify_saved_conditions(snapshot: dict, category_name: str, vocab=None) -> dict:
    """Prove the rules are saved native conditions, not template prose.
    `vocab` (from load_vocab) renames what is looked for; None = the defaults."""
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
    for rule, wanted in expected_rules(category_name, vocab):
        # every expected condition of a rule must be present (all suppression tags)
        ok = all(any(_matches(expected, condition) for condition in native)
                 for expected in wanted)
        found[rule] = ok
        if not ok:
            missing.append(rule)
            haystack = " \n".join(prose).lower()
            hints = list(PROSE_HINTS[rule])
            if vocab is not None:
                for expected in wanted:
                    hints += [str(expected.get(k)) for k in ("value", "field") if expected.get(k)]
            if any(hint.lower() in haystack for hint in hints):
                prose_only.append(rule)
    return {"ok": not missing, "missing": missing,
            "prose_only": prose_only, "found": found}


# ---------------------------------------------------------------------------
# saved-export check (the per-build QC entry point, qc-built-workflow.sh WF-25)
# ---------------------------------------------------------------------------

def _export_steps(export):
    """The step list of a saved workflow export, or None. Same lookup order as
    the QC script's WF-12: workflowData.templates wins over steps/actions/nodes."""
    if not isinstance(export, dict):
        return None
    for holder in (export, export.get("data"), export.get("workflow")):
        if not isinstance(holder, dict):
            continue
        wd = holder.get("workflowData")
        if isinstance(wd, dict) and isinstance(wd.get("templates"), list):
            return wd["templates"]
        for key in ("steps", "actions", "nodes", "templates"):
            if isinstance(holder.get(key), list):
                return holder[key]
    return None


def _is_sms(step) -> bool:
    return isinstance(step, dict) and "SMS" in str(step.get("type") or "").upper()


_TAG_PRESENT_OPS = ("index-of-true", "contains", "is")
_TAG_ABSENT_OPS = ("index-of-false", "does-not-contain", "is-not")
_LT_OPS = ("<", "lt", "less-than", "less_than", "less than")


def native_conditions(step):
    """Normalise the conditions of a saved GoHighLevel if/else CONDITION node
    (attributes.branches[].segments[].conditions[]) into the verifier's shape.
    Only a condition node is read; a branch arm or any other node yields none.
    Unrecognised conditions are dropped, never guessed."""
    attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
    if str(step.get("type") or "").lower() != "if_else" \
            or not isinstance(attrs.get("branches"), list):
        return []
    out = []
    for branch in attrs["branches"]:
        for segment in (branch.get("segments") or []) if isinstance(branch, dict) else []:
            for cond in (segment.get("conditions") or []) if isinstance(segment, dict) else []:
                if not isinstance(cond, dict):
                    continue
                op = str(cond.get("conditionOperator") or "").lower()
                sub = cond.get("conditionSubType")
                value = cond.get("conditionValue")
                values = value if isinstance(value, list) else [value]
                if cond.get("conditionType") == "contact_detail" and sub == "tags":
                    kind = ("tag_present" if op in _TAG_PRESENT_OPS
                            else "tag_absent" if op in _TAG_ABSENT_OPS else None)
                    if kind:
                        out.extend({"type": kind, "value": v} for v in values
                                   if isinstance(v, str))
                elif op in _LT_OPS and isinstance(sub, str):
                    try:
                        out.append({"type": "field_lt", "field": sub,
                                    "value": int(values[0])})
                    except (TypeError, ValueError, IndexError):
                        pass
    return out


def _export_holder(export):
    for holder in (export, export.get("data"), export.get("workflow")):
        if isinstance(holder, dict) and (
                isinstance(holder.get("workflowData"), dict)
                or any(isinstance(holder.get(k), list)
                       for k in ("steps", "actions", "nodes", "templates"))):
            return holder
    return export


def snapshot_from_export(export, vocab=None):
    """(snapshot, sms_steps) for verify_saved_conditions().

    A saved export keeps conditions and prose under `attributes`; the
    verifier reads them at the top of each step, so they are hoisted here.
    Nothing is invented: a step with no conditions stays without any.
    """
    steps = _export_steps(export)
    if steps is None:
        return None, []
    out, sms = [], []
    for step in steps:
        if not isinstance(step, dict):
            continue
        attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
        flat = {"type": str(step.get("type") or "").lower(),
                "disabled": step.get("disabled") is True or attrs.get("disabled") is True}
        conditions = step.get("conditions")
        flat["conditions"] = conditions if isinstance(conditions, list) else (
            attrs.get("conditions") if isinstance(attrs.get("conditions"), list) else [])
        for key in PROSE_FIELDS:
            value = step.get(key) if isinstance(step.get(key), str) else attrs.get(key)
            if isinstance(value, str):
                flat[key] = value
        flat["conditions"] = list(flat["conditions"]) + native_conditions(step)
        out.append(flat)
        if _is_sms(step):
            sms.append(step)
    holder = _export_holder(export)
    window = holder.get("window")
    if isinstance(window, dict) and window.get("condition") == "when":
        out.append({"type": "condition", "disabled": False, "conditions": [
            {"type": "native_time_window", "condition": "when",
             "start": window.get("start"), "end": window.get("end"),
             "timezone": holder.get("timezone")}]})
    deadline = (vocab or {}).get("deadline") or {}
    if deadline.get("source") == "native_wait_until_date" and deadline_covered(
            steps, sms, deadline, holder.get("timezone")):
        # Derived ONLY from native wait nodes upstream of every SMS node.
        out.append({"type": "wait_until", "disabled": False, "conditions": [
            {"type": "deadline", "anchor": deadline["anchor"]}]})
    return {"steps": out, "stop_on_response": holder.get("stopOnResponse") is True,
            "timezone": holder.get("timezone")}, sms


def export_category(sms_steps) -> str:
    """`operational` only when EVERY SMS node declares an operational category
    or kind; anything else is `marketing` (the stricter rule set)."""
    if not sms_steps:
        return "marketing"
    for step in sms_steps:
        attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
        declared = attrs.get("category") or step.get("category")
        kind = attrs.get("kind") or step.get("kind")
        if declared == "operational" or kind in OPERATIONAL_KINDS:
            continue
        return "marketing"
    return "operational"


def verify_saved_export(export, category_name="auto", vocab=None) -> dict:
    """verify_saved_conditions() over a saved workflow export.

    `ok` is True when the export has no SMS node (nothing to prove) or every
    rule for its category is a saved native condition. An unreadable export
    is `ok: False` with `unreadable: True`, never a pass.
    """
    snapshot, sms = snapshot_from_export(export, vocab)
    if snapshot is None:
        return {"ok": False, "unreadable": True, "category": None, "sms_nodes": 0,
                "missing": ["workflow.steps"], "prose_only": [], "found": {}}
    if not sms:
        return {"ok": True, "unreadable": False, "category": None, "sms_nodes": 0,
                "missing": [], "prose_only": [], "found": {}}
    chosen = export_category(sms) if category_name == "auto" else category_name
    result = verify_saved_conditions(snapshot, chosen, vocab)
    # Workflow-level Stop on Response is a native setting, not a condition node.
    result["stop_on_response"] = snapshot.get("stop_on_response") is True
    result["window_timezone"] = snapshot.get("timezone")
    result.update({"unreadable": False, "category": chosen, "sms_nodes": len(sms)})
    return result


def main(argv=None) -> int:
    """`verify-saved --export <export.json> [--category auto|marketing|operational] [--vocab <mapping.json>]`

    Exit 0 = every rule saved natively (or no SMS node), 1 = a rule is
    missing or prose only, 2 = the export or the --vocab mapping could not be read.
    """
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog="sms_eligibility.py")
    sub = parser.add_subparsers(dest="command", required=True)
    saved = sub.add_parser("verify-saved", help="prove SMS rules are saved native conditions")
    saved.add_argument("--export", required=True, help="saved workflow export JSON")
    saved.add_argument("--category", default="auto",
                       choices=("auto", "marketing", "operational"))
    saved.add_argument("--vocab", default=None,
                       help="per-account SMS vocabulary mapping JSON (default: the literal catalog names)")
    args = parser.parse_args(argv)
    vocab = None
    if args.vocab is not None:
        try:
            with open(args.vocab, encoding="utf-8") as handle:
                vocab = load_vocab(json.load(handle))
        except (OSError, ValueError) as exc:
            print(json.dumps({"ok": False, "unreadable": True,
                              "error": "vocab_invalid: %s" % exc}))
            return 2
    try:
        with open(args.export, encoding="utf-8") as handle:
            export = json.load(handle)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "unreadable": True,
                          "error": type(exc).__name__}))
        return 2
    result = verify_saved_export(export, args.category, vocab)
    print(json.dumps(result, sort_keys=True))
    if result.get("unreadable"):
        return 2
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
