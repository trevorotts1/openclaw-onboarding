"""Compile agent-understood timing into a native GHL UI outline, NOT an API payload.

No credentials, network, or CRM writes. The agent interprets the user's language;
this helper enforces its explicit timing contract and inserts the event-start node.
Run directly with a JSON file containing requirements and anchors.
"""
from __future__ import annotations

import argparse
import json
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNITS = {"minutes": 1, "hours": 60, "days": 1440, "weeks": 10080}


def plan_timing(requirements: list, anchors: dict) -> dict:
    """Emit ordered timing nodes for ONE execution path, preserving event offsets.

    requirements: [{id, kind: event|delay, offset, unit, anchor?}]
    anchors: {key: {source, timezone, past_due: skip|continue|exit,
                    reentry: once|separate_registration}}
    source describes a verified per-registration field/trigger value or event date.
    This helper cannot prove the field exists: dependency pre-check and UI readback do.
    """
    if not isinstance(requirements, list) or not isinstance(anchors, dict):
        raise ValueError("timing requires a requirements list and an anchors object")
    nodes, seen, positions = [], set(), {}
    active_anchor = None
    for requirement in requirements:
        if not isinstance(requirement, dict):
            raise ValueError("each timing requirement must be an object")
        step_id = requirement.get("id")
        if not isinstance(step_id, str) or not step_id.strip() or step_id in seen:
            raise ValueError("timing step IDs must be nonempty and unique")
        seen.add(step_id)
        kind = requirement.get("kind")
        offset, unit = requirement.get("offset"), requirement.get("unit")
        if (isinstance(offset, bool) or not isinstance(offset, (int, float))
                or not math.isfinite(offset) or not isinstance(unit, str) or unit not in UNITS):
            raise ValueError(f"{step_id}: specify a finite numeric offset and minutes/hours/days/weeks")
        if kind == "delay":
            if offset < 0 or requirement.get("anchor"):
                raise ValueError(f"{step_id}: a relative delay cannot be negative or have an event anchor")
            nodes.append({"action": "wait_duration", "step_id": step_id,
                          "offset": offset, "unit": unit})
            continue
        if kind != "event":
            raise ValueError(f"{step_id}: resolve whether timing is event-based or a delay")
        key = requirement.get("anchor")
        if not isinstance(key, str) or not key or not isinstance(anchors.get(key), dict):
            raise ValueError(f"{step_id}: resolve the event/registration date source before building")
        anchor = anchors[key]
        for field in ("source", "timezone"):
            if not isinstance(anchor.get(field), str) or not anchor[field].strip():
                raise ValueError(f"{step_id}: anchor {key} needs {field}")
        try:
            ZoneInfo(anchor["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"{step_id}: use a valid IANA timezone") from None
        if anchor.get("past_due") not in ("skip", "continue", "exit"):
            raise ValueError(f"{step_id}: choose an explicit past-due policy")
        if anchor.get("reentry") not in ("once", "separate_registration"):
            raise ValueError(f"{step_id}: choose once or a separate registration instance; never reset an active clock")
        position = offset * UNITS[unit]
        if key in positions and position < positions[key]:
            raise ValueError(f"{step_id}: event offsets run backwards on this path; resolve ordering or use separate branches")
        positions[key] = position
        if active_anchor != key:
            nodes.append({"action": "set_event_start_time", "anchor": key,
                          "source": anchor["source"], "timezone": anchor["timezone"],
                          "reentry": anchor["reentry"]})
            active_anchor = key
        nodes.append({"action": "wait_until_event", "step_id": step_id,
                      "anchor": key, "offset": offset, "unit": unit,
                      "past_due": anchor["past_due"]})
    return {"nodes": nodes, "requires_event_start": any(
        n["action"] == "set_event_start_time" for n in nodes),
        "format": "semantic-ui-outline-not-api-payload"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="JSON file with requirements and anchors")
    args = parser.parse_args()
    try:
        with open(args.plan) as stream:
            spec = json.load(stream)
        if not isinstance(spec, dict):
            raise ValueError("timing plan must be an object")
        result = plan_timing(spec.get("requirements"), spec.get("anchors", {}))
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
