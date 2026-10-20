#!/usr/bin/env python3
"""Check the launch-text SMS catalog (stdlib only).

Enforces the rules the launch plan contract and the text lane share:
six kinds, message/step parity, STOP in every message, quiet hours,
the 5-set promotional cap, and a closed placeholder set.

    python3 test_launch_text_catalog.py
Exit 0 = clean; 1 = failures printed one per line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "text-sets.json"

EXPECTED_KINDS = {
    "opt_in_confirmation",
    "event_reminder",
    "doors_open",
    "last_call",
    "abandoned_checkout",
    "access_link",
}
REQUIRED_SET_FIELDS = (
    "id", "kind", "messages", "promotional", "draft_only",
    "opt_out_keyword", "includes_reply_invitation", "send_window",
    "waits_for", "steps",
)
WINDOW_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
PLACEHOLDER_RE = re.compile(r"\{\{([a-z_]+)\}\}")
MAX_COPY = 320


def minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def check(catalog: dict) -> list[str]:
    errors: list[str] = []

    if catalog.get("channel") != "sms":
        errors.append("channel must be sms")
    if catalog.get("draft_only") is not True:
        errors.append("catalog draft_only must be true")
    if catalog.get("opt_out_keyword") != "STOP":
        errors.append("catalog opt_out_keyword must be STOP")

    quiet = catalog.get("quiet_hours") or {}
    if (quiet.get("start"), quiet.get("end")) != ("08:00", "21:00"):
        errors.append("quiet_hours must be 08:00-21:00")
    if quiet.get("timezone") != "recipient_local":
        errors.append("quiet_hours.timezone must be recipient_local")

    budget = catalog.get("promotional_budget") or {}
    if budget.get("cap") != 5:
        errors.append("promotional cap must be 5")

    allowed = set(catalog.get("placeholders") or [])
    sets = catalog.get("text_sets") or []
    if not isinstance(sets, list):
        return errors + ["text_sets must be a list"]

    seen_ids: set[str] = set()
    seen_kinds: list[str] = []
    promotional: list[str] = []

    for index, item in enumerate(sets, 1):
        where = "text_sets[%d]" % index
        if not isinstance(item, dict):
            errors.append("%s: not an object" % where)
            continue
        for field in REQUIRED_SET_FIELDS:
            if field not in item:
                errors.append("%s: missing %s" % (where, field))

        unit_id = item.get("id")
        if unit_id in seen_ids:
            errors.append("%s: duplicate id %r" % (where, unit_id))
        seen_ids.add(unit_id)
        where = str(unit_id)
        seen_kinds.append(item.get("kind"))
        if item.get("promotional") is True:
            promotional.append(where)

        if item.get("draft_only") is not True:
            errors.append("%s: draft_only must be true" % where)
        if item.get("opt_out_keyword") != "STOP":
            errors.append("%s: opt_out_keyword must be STOP" % where)
        if item.get("includes_reply_invitation") is not True:
            errors.append("%s: includes_reply_invitation must be true" % where)
        if not isinstance(item.get("waits_for"), list) or not item["waits_for"]:
            errors.append("%s: waits_for must be a non-empty list" % where)

        window = item.get("send_window") or {}
        start, end = window.get("start"), window.get("end")
        if not (isinstance(start, str) and WINDOW_RE.match(start)):
            errors.append("%s: bad send_window.start %r" % (where, start))
        if not (isinstance(end, str) and WINDOW_RE.match(end)):
            errors.append("%s: bad send_window.end %r" % (where, end))
        if isinstance(start, str) and isinstance(end, str) and WINDOW_RE.match(start) and WINDOW_RE.match(end):
            if minutes(start) >= minutes(end):
                errors.append("%s: send_window start must be before end" % where)
            if (start, end) != (quiet.get("start"), quiet.get("end")):
                errors.append("%s: send_window must equal quiet_hours" % where)
        if window.get("timezone") != "recipient_local":
            errors.append("%s: send_window.timezone must be recipient_local" % where)

        steps = item.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append("%s: steps must be a non-empty list" % where)
            continue
        if item.get("messages") != len(steps):
            errors.append(
                "%s: messages=%r but %d steps" % (where, item.get("messages"), len(steps))
            )
        for position, step in enumerate(steps, 1):
            label = "%s step %d" % (where, position)
            if step.get("step") != position:
                errors.append("%s: step number is %r" % (label, step.get("step")))
            for field in ("delay", "purpose", "copy"):
                if not isinstance(step.get(field), str) or not step[field].strip():
                    errors.append("%s: missing %s" % (label, field))
            copy = step.get("copy")
            if not isinstance(copy, str):
                continue
            if "STOP" not in copy:
                errors.append("%s: no STOP in copy" % label)
            if len(copy) > MAX_COPY:
                errors.append("%s: copy is %d chars (max %d)" % (label, len(copy), MAX_COPY))
            for token in PLACEHOLDER_RE.findall(copy):
                if token not in allowed:
                    errors.append("%s: unknown placeholder {{%s}}" % (label, token))

    if sorted(seen_kinds) != sorted(EXPECTED_KINDS):
        errors.append("kinds must be exactly %s, got %s" % (sorted(EXPECTED_KINDS), sorted(seen_kinds)))
    if len(promotional) > 5:
        errors.append("%d promotional sets exceeds the cap of 5" % len(promotional))
    if budget.get("used") != len(promotional):
        errors.append("promotional_budget.used=%r but %d sets are promotional" % (budget.get("used"), len(promotional)))
    if sorted(budget.get("sets") or []) != sorted(promotional):
        errors.append("promotional_budget.sets does not match the promotional sets")

    return errors


def main() -> int:
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("cannot read %s: %s" % (CATALOG, exc))
        return 1
    errors = check(catalog)
    for error in errors:
        print(error)
    if not errors:
        print("OK: %d text sets, %d promotional" % (
            len(catalog["text_sets"]),
            sum(1 for item in catalog["text_sets"] if item["promotional"]),
        ))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
