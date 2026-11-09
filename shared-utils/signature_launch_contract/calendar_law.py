#!/usr/bin/env python3
"""calendar_law.py — the ONE launch calendar law (U-CONTRACT, stdlib only).

Skill 83 (launch_plan.py), Skill 44 (plan_reader.py) and the shared validator
(validate_launch_plan.py) all judge the same ``launch_calendar``. They must
judge it by the same order, so the order lives here and nowhere else.

Black Friday order (a plan that carries ``launch_calendar.black_friday``):

    teaser < countdown <= doors_open <= launch < cyber_monday <= last_call < doors_close

Any other launch:

    doors_open <= launch < doors_close

``<=`` lets the launch instant be the moment the doors open (one shared rule,
DECISIONS 2026-11-02: launch time = doors open). Every deadline must carry a UTC
offset; a zone-less time cannot be ordered against one that has an offset.

``violations`` returns plain strings, one per broken rule, and never raises on a
bad value: each consumer keeps its own error codes and maps the strings.
"""

from __future__ import annotations

from datetime import datetime

# phase -> path inside launch_calendar
PHASE_FIELDS = {
    "teaser": ("black_friday", "teaser_at"),
    "countdown": ("black_friday", "countdown_at"),
    "doors_open": ("doors_open_at",),
    "launch": ("launch_at",),
    "cyber_monday": ("black_friday", "cyber_monday_at"),
    "last_call": ("black_friday", "last_call_at"),
    "doors_close": ("doors_close_at",),
}

BLACK_FRIDAY_ORDER = (
    ("teaser", "<", "countdown"),
    ("countdown", "<=", "doors_open"),
    ("doors_open", "<=", "launch"),
    ("launch", "<", "cyber_monday"),
    ("cyber_monday", "<=", "last_call"),
    ("last_call", "<", "doors_close"),
)
STANDARD_ORDER = (
    ("doors_open", "<=", "launch"),
    ("launch", "<", "doors_close"),
)


def _field(calendar: dict, phase: str):
    node = calendar
    for part in PHASE_FIELDS[phase]:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _label(phase: str) -> str:
    return ".".join(("launch_calendar",) + PHASE_FIELDS[phase])


def is_black_friday(calendar) -> bool:
    return isinstance(calendar, dict) and "black_friday" in calendar


def violations(calendar, black_friday_required: bool = False) -> list:
    """Every way ``calendar`` breaks the law. Empty list means the order holds.

    ``black_friday_required`` makes a missing ``black_friday`` block a violation
    (a consumer that knows the launch is a Black Friday launch passes True).
    """
    if not isinstance(calendar, dict):
        return ["launch_calendar: must be an object"]
    errors = []
    black_friday = is_black_friday(calendar)
    if black_friday_required and not black_friday:
        return ["launch_calendar.black_friday: required for a Black Friday launch "
                "(teaser_at, countdown_at, cyber_monday_at, last_call_at)"]
    if black_friday and not isinstance(calendar["black_friday"], dict):
        return ["launch_calendar.black_friday: must be an object"]
    order = BLACK_FRIDAY_ORDER if black_friday else STANDARD_ORDER

    when = {}
    for phase in {name for rule in order for name in (rule[0], rule[2])}:
        raw = _field(calendar, phase)
        if raw is None:
            errors.append("%s: missing" % _label(phase))
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            errors.append("%s: %r is not an ISO-8601 date-time" % (_label(phase), raw))
            continue
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            errors.append("%s: %r has no UTC offset; a deadline is never zone-less"
                          % (_label(phase), raw))
            continue
        when[phase] = parsed
    if errors:
        return sorted(errors)

    for earlier, op, later in order:
        if op == "<" and not when[earlier] < when[later]:
            errors.append("calendar order: %s must be before %s (%s is not before %s)"
                          % (earlier, later, when[earlier].isoformat(), when[later].isoformat()))
        elif op == "<=" and not when[earlier] <= when[later]:
            errors.append("calendar order: %s must not be after %s (%s is after %s)"
                          % (earlier, later, when[earlier].isoformat(), when[later].isoformat()))
    if not when["doors_open"] < when["doors_close"]:
        errors.append("launch_calendar: doors_close_at must be after doors_open_at")
    return errors


if __name__ == "__main__":
    good = {
        "launch_at": "2026-11-27T00:00:00-05:00",
        "doors_open_at": "2026-11-27T00:00:00-05:00",
        "doors_close_at": "2026-12-01T00:00:00-05:00",
        "black_friday": {
            "teaser_at": "2026-11-20T09:00:00-05:00",
            "countdown_at": "2026-11-24T09:00:00-05:00",
            "cyber_monday_at": "2026-11-30T00:00:00-05:00",
            "last_call_at": "2026-11-30T20:00:00-05:00",
        },
    }
    assert violations(good) == []
    bad = {**good, "black_friday": {**good["black_friday"], "countdown_at": "2026-11-20T09:00:00-05:00"}}
    assert violations(bad), "teaser == countdown must be refused"
    assert violations({k: v for k, v in good.items() if k != "black_friday"}, True)
    print("calendar_law self-check ok")
