"""Black Friday calendar, planned-unit completeness, and the plan record a package carries.

The launch plan is the shared contract (``shared-utils/signature_launch_contract/
launch-plan.schema.json``, U-CONTRACT). This module CONSUMES it: it validates the
Black Friday timing Skill 83 owns, lists every planned unit (pages, email
sequences, text sets, automations and the optional Conversation AI) and fails when
a planned unit was not delivered. It never restates the schema, never invents a
date and never invents a unit.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

PLAN_CONTRACT_REF = "shared-utils/signature_launch_contract/launch-plan.schema.json"

CALENDAR_KEYS = ("launch_at", "doors_open_at", "doors_close_at", "timezone")
BLACK_FRIDAY_KEYS = ("teaser_at", "countdown_at", "cyber_monday_at", "last_call_at")
UNIT_SECTIONS = (
    ("pages", "page"),
    ("email_sequences", "email"),
    ("text_sets", "text"),
    ("automations", "automation"),
)
AI_UNIT_ID = "conversation_ai"
COMPLETE_STATES = ("complete", "delivered")


class LaunchPlanError(Exception):
    """A plan or calendar that cannot be carried. Carries a stable autofail code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _time(value: Any, field: str) -> datetime.datetime:
    if not _nonempty_str(value):
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-MISSING", f"{field} must be an ISO-8601 date-time")
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-TIME",
                              f"{field} {value!r} is not an ISO-8601 date-time") from exc
    if parsed.tzinfo is None:
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-TIME",
                              f"{field} {value!r} has no UTC offset; a deadline is never zone-less")
    return parsed


def black_friday_calendar(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """The Black Friday calendar Skill 83 adds, validated against the launch's own clock.

    Every deadline a lane writes comes from here (spec §4: teaser, countdown, doors
    open, Cyber Monday, last call). The order is law: teaser < countdown < doors
    open <= launch < Cyber Monday <= last call < doors close.
    """
    if not isinstance(plan, Mapping):
        raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE", "the launch plan must be an object")
    calendar = plan.get("launch_calendar")
    if not isinstance(calendar, Mapping):
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-MISSING",
                              "the launch plan carries no launch_calendar")
    for key in CALENDAR_KEYS:
        if key not in calendar:
            raise LaunchPlanError("AF-LAUNCH-CALENDAR-MISSING",
                                  f"launch_calendar.{key} is required")
    if not _nonempty_str(calendar["timezone"]):
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-MISSING",
                              "launch_calendar.timezone must be an IANA zone")
    black_friday = calendar.get("black_friday")
    if not isinstance(black_friday, Mapping):
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-MISSING",
                              "a Black Friday launch needs launch_calendar.black_friday "
                              "(teaser, countdown, Cyber Monday, last call)")
    for key in BLACK_FRIDAY_KEYS:
        if key not in black_friday:
            raise LaunchPlanError("AF-LAUNCH-CALENDAR-MISSING",
                                  f"launch_calendar.black_friday.{key} is required")

    teaser = _time(black_friday["teaser_at"], "black_friday.teaser_at")
    countdown = _time(black_friday["countdown_at"], "black_friday.countdown_at")
    doors_open = _time(calendar["doors_open_at"], "doors_open_at")
    launch_at = _time(calendar["launch_at"], "launch_at")
    cyber_monday = _time(black_friday["cyber_monday_at"], "black_friday.cyber_monday_at")
    last_call = _time(black_friday["last_call_at"], "black_friday.last_call_at")
    doors_close = _time(calendar["doors_close_at"], "doors_close_at")

    order = (
        ("teaser", teaser, "countdown", countdown),
        ("countdown", countdown, "doors open", doors_open),
        ("doors open", doors_open, "launch", launch_at),
        ("launch", launch_at, "Cyber Monday", cyber_monday),
        ("Cyber Monday", cyber_monday, "last call", last_call),
        ("last call", last_call, "doors close", doors_close),
    )
    for earlier_name, earlier, later_name, later in order:
        if earlier > later:
            raise LaunchPlanError(
                "AF-LAUNCH-CALENDAR-ORDER",
                f"{earlier_name} ({earlier.isoformat()}) is after {later_name} "
                f"({later.isoformat()}); a deadline may not move backwards")
    if doors_open > doors_close:
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-ORDER",
                              "doors open after doors close")

    phases = [
        {"phase": "teaser", "at": black_friday["teaser_at"]},
        {"phase": "countdown", "at": black_friday["countdown_at"]},
        {"phase": "doors_open", "at": calendar["doors_open_at"]},
        {"phase": "cyber_monday", "at": black_friday["cyber_monday_at"]},
        {"phase": "last_call", "at": black_friday["last_call_at"]},
        {"phase": "doors_close", "at": calendar["doors_close_at"]},
    ]
    return {
        "contract": PLAN_CONTRACT_REF,
        "timezone": calendar["timezone"],
        "launch_at": calendar["launch_at"],
        "doors_open_at": calendar["doors_open_at"],
        "doors_close_at": calendar["doors_close_at"],
        "black_friday": {key: black_friday[key] for key in BLACK_FRIDAY_KEYS},
        "black_friday_date": doors_open.date().isoformat(),
        "phases": phases,
    }


def planned_units(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Every unit the plan promises, in plan order: pages, emails, texts, automations, AI.

    A unit id is unique across all sections (contract ``unit_id``). The optional
    Conversation AI is a planned unit exactly when the client requested it.
    """
    if not isinstance(plan, Mapping):
        raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE", "the launch plan must be an object")
    units: List[Dict[str, Any]] = []
    seen: Dict[str, str] = {}
    for section, unit_type in UNIT_SECTIONS:
        items = plan.get(section)
        if not isinstance(items, list):
            raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE",
                                  f"{section} must be a list of planned units")
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE",
                                      f"{section}[{index}] must be an object")
            unit_id = item.get("id")
            if not _nonempty_str(unit_id):
                raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE",
                                      f"{section}[{index}].id must be a non-empty string")
            if unit_id in seen:
                raise LaunchPlanError("AF-LAUNCH-PLAN-DUPLICATE",
                                      f"unit id {unit_id!r} appears in {seen[unit_id]} and {section}")
            seen[unit_id] = section
            waits = item.get("waits_for") or []
            if not isinstance(waits, list) or not all(_nonempty_str(w) for w in waits):
                raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE",
                                      f"{section}[{index}].waits_for must be a list of unit ids")
            units.append({
                "id": unit_id,
                "type": unit_type,
                "kind": item.get("kind") or item.get("family") or "",
                "waits_for": list(waits),
            })

    conversation_ai = plan.get("conversation_ai")
    if not isinstance(conversation_ai, Mapping):
        raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE",
                              "conversation_ai must say whether the client requested the bot")
    requested = conversation_ai.get("requested")
    mode = conversation_ai.get("mode")
    if not isinstance(requested, bool):
        raise LaunchPlanError("AF-LAUNCH-PLAN-AI", "conversation_ai.requested must be a boolean")
    if requested:
        if mode in (None, "", "none"):
            raise LaunchPlanError("AF-LAUNCH-PLAN-AI",
                                  "Conversation AI is requested, so its mode may not be 'none'")
        if AI_UNIT_ID in seen:
            raise LaunchPlanError("AF-LAUNCH-PLAN-DUPLICATE",
                                  f"unit id {AI_UNIT_ID!r} is reserved for the requested bot")
        units.append({"id": AI_UNIT_ID, "type": "conversation_ai",
                      "kind": str(mode), "waits_for": []})
    elif mode not in (None, "none"):
        raise LaunchPlanError("AF-LAUNCH-PLAN-AI",
                              "Conversation AI is not requested, so its mode must be 'none'")
    return units


def _delivery_state(result: Any) -> Optional[str]:
    if result is True:
        return "complete"
    if isinstance(result, str):
        return result
    if isinstance(result, Mapping):
        state = result.get("state") or result.get("status")
        return state if isinstance(state, str) else None
    return None


def completeness(plan: Mapping[str, Any],
                 delivered: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Which planned units arrived. Missing (or not complete) is a failed delivery."""
    units = planned_units(plan)
    results = delivered or {}
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    for unit in units:
        state = _delivery_state(results.get(unit["id"]))
        complete = state in COMPLETE_STATES
        if not complete:
            missing.append(unit["id"])
        rows.append({**unit, "state": state or "missing",
                     "delivered": complete})
    total, arrived = len(units), len(units) - len(missing)
    percentage = 100 if not total else int(round(100 * arrived / total))
    conversation_ai = plan.get("conversation_ai") or {}
    return {
        "planned": [u["id"] for u in units],
        "delivered": [u["id"] for u in rows if u["delivered"]],
        "missing": missing,
        "complete": not missing,
        "units": rows,
        "counts": {"planned": total, "delivered": arrived, "missing": len(missing)},
        "percentage": percentage,
        "conversation_ai": ("requested" if conversation_ai.get("requested") is True
                            else "not requested"),
    }


def assert_complete(result: Mapping[str, Any]) -> None:
    """Fail closed when a planned unit is missing or not complete."""
    if not result.get("complete"):
        counts = result.get("counts") or {}
        raise LaunchPlanError(
            "AF-LAUNCH-PLAN-MISSING",
            f"planned item(s) not delivered: {', '.join(result.get('missing') or [])} "
            f"({counts.get('delivered', 0)}/{counts.get('planned', 0)} complete)")


def record(plan: Mapping[str, Any],
           delivered: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The record the manifest and receipt carry: calendar + planned-unit completeness."""
    calendar = black_friday_calendar(plan)
    result = completeness(plan, delivered)
    return {
        "contract": PLAN_CONTRACT_REF,
        "launch_id": plan.get("launch_id"),
        "calendar": calendar,
        "completeness": result,
        "conversation_ai": {
            "requested": bool((plan.get("conversation_ai") or {}).get("requested")),
            "mode": (plan.get("conversation_ai") or {}).get("mode"),
            "state": result["conversation_ai"],
        },
    }
