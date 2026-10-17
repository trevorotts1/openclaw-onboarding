"""Deadline display: show a launch's real deadline, honestly.

Owner: S71. Implements doc 16 section 1 ("Deadline display ... Real
deadline and timezone; never reset-fake scarcity") and the doc 16
section 8 automatic failure "invented proof/scarcity".

Input is supplied launch data:

    {"deadline_at": ISO-8601 string with offset, or None,
     "timezone":    IANA timezone name for display, e.g. "America/New_York",
     "label":       plain-text label, e.g. "Registration closes",
     "expired_text": optional plain-text override for the expired state}

States (the component has exactly three):

- absent:  no deadline_at supplied. Renders the shell with
  data-state="absent" and NO date, countdown or scarcity text. The
  component never invents a deadline to create urgency.
- active:  deadline is in the future relative to the injected ``now``.
  Renders the label, the deadline formatted in the launch timezone,
  and the remaining time computed from ``now``. The markup carries
  data-deadline-at / data-timezone so a page may tick the display
  client-side against the SAME fixed instant.
- expired: deadline is at or before ``now``. Renders the label, the
  deadline, and the expired text. The deadline is never extended,
  rolled forward or reset by this component.

``now`` is an explicit parameter (timezone-aware datetime) so rendering
is deterministic and testable; callers pass the real current time.
All interpolated text is HTML-escaped (doc 16 section 6).

Failure modes (all raised as ValueError, the component's one
documented error type, so callers handle a single exception):

- ``deadline_at`` without a UTC offset (a naive deadline) is rejected:
  an ambiguous deadline is not displayed.
- ``now`` without tzinfo is rejected.
- ``timezone`` that is not an IANA timezone name is rejected with a
  ValueError naming the offending value. (zoneinfo raises
  ZoneInfoNotFoundError, a KeyError subclass, for unknown names; this
  component converts it so the failure surface stays ValueError.)
  The timezone is only consulted when a deadline is present, so the
  absent state renders regardless of the timezone value.

Deterministic, standard library only.
"""

import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

COMPONENT_NAME = "deadline-display"
COMPONENT_VERSION = "1.0.0"
COMPONENT_OWNER = "S71"

DEFAULT_LABEL = "Deadline"
DEFAULT_EXPIRED_TEXT = "This deadline has passed."


def _esc(value):
    return html.escape(str(value), quote=True)


def _parse_deadline(raw):
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(
            "deadline_at must carry a UTC offset; a naive deadline is ambiguous"
        )
    return parsed


def _format_remaining(delta):
    total_seconds = int(delta.total_seconds())
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append("%d day%s" % (days, "" if days == 1 else "s"))
    if hours or days:
        parts.append("%d hour%s" % (hours, "" if hours == 1 else "s"))
    parts.append("%d minute%s" % (minutes, "" if minutes == 1 else "s"))
    return " ".join(parts)


def render_deadline_display(deadline, now, tokens=None):
    """Render the deadline display. Returns {"html", "state", ...}.

    deadline: dict as described in the module docstring (or None).
    now: timezone-aware datetime the render is computed against.
    tokens: accepted for call-site symmetry; branding arrives via the
    --sl-* CSS variables and design.css.
    """
    deadline = deadline or {}
    label = deadline.get("label") or DEFAULT_LABEL
    raw = deadline.get("deadline_at")
    instant = _parse_deadline(raw)

    if instant is None:
        return {
            "html": '<div class="sl-deadline" data-state="absent"></div>\n',
            "state": "absent",
            "deadline_at": None,
            "timezone": deadline.get("timezone"),
        }

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz_name = deadline.get("timezone") or "UTC"
    try:
        display_tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        raise ValueError(
            "unknown timezone: %r is not an IANA timezone name" % tz_name
        )
    local = instant.astimezone(display_tz)
    formatted = local.strftime("%B %d, %Y at %I:%M %p %Z")

    if instant <= now:
        expired_text = deadline.get("expired_text") or DEFAULT_EXPIRED_TEXT
        html_out = (
            '<div class="sl-deadline" data-state="expired" '
            'data-deadline-at="%s" data-timezone="%s">\n'
            '  <span class="sl-deadline-label">%s</span>\n'
            '  <time class="sl-deadline-when" datetime="%s">%s</time>\n'
            '  <span class="sl-deadline-status">%s</span>\n'
            "</div>\n"
            % (
                _esc(instant.astimezone(timezone.utc).isoformat()),
                _esc(tz_name),
                _esc(label),
                _esc(instant.isoformat()),
                _esc(formatted),
                _esc(expired_text),
            )
        )
        return {
            "html": html_out,
            "state": "expired",
            "deadline_at": instant.isoformat(),
            "timezone": tz_name,
        }

    remaining = _format_remaining(instant - now)
    html_out = (
        '<div class="sl-deadline" data-state="active" '
        'data-deadline-at="%s" data-timezone="%s">\n'
        '  <span class="sl-deadline-label">%s</span>\n'
        '  <time class="sl-deadline-when" datetime="%s">%s</time>\n'
        '  <span class="sl-deadline-remaining">%s remaining</span>\n'
        "</div>\n"
        % (
            _esc(instant.astimezone(timezone.utc).isoformat()),
            _esc(tz_name),
            _esc(label),
            _esc(instant.isoformat()),
            _esc(formatted),
            _esc(remaining),
        )
    )
    return {
        "html": html_out,
        "state": "active",
        "deadline_at": instant.isoformat(),
        "timezone": tz_name,
    }
