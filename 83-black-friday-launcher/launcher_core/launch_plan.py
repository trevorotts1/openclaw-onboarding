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
import functools
import importlib.util
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .constants import REPO_ROOT

PLAN_CONTRACT_REF = "shared-utils/signature_launch_contract/launch-plan.schema.json"
PLAN_VALIDATOR_REF = "shared-utils/signature_launch_contract/validate_launch_plan.py"
PLAN_SCHEMA_VERSION = "1.0.0"

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


@functools.lru_cache(maxsize=1)
def _contract_module():
    """The shared U-CONTRACT validator and its schema. None when not installed."""
    path = REPO_ROOT / PLAN_VALIDATOR_REF
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("s_launch_plan_contract", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CONTRACT_CODES = (
    ("waits_for cycle", "AF-LAUNCH-PLAN-CYCLE"),
    ("waits_for unknown unit", "AF-LAUNCH-PLAN-DEPENDENCY"),
    ("waits_for itself", "AF-LAUNCH-PLAN-DEPENDENCY"),
    ("used by more than one unit", "AF-LAUNCH-PLAN-DUPLICATE"),
    ("schema_version", "AF-LAUNCH-PLAN-SCHEMA"),
    ("draft_only", "AF-LAUNCH-PLAN-DRAFT"),
    ("promotional sets exceeds", "AF-LAUNCH-PLAN-TEXT-CAP"),
    ("conversation_ai", "AF-LAUNCH-PLAN-AI"),
    ("failed_payment", "AF-LAUNCH-PLAN-PAYMENT"),
)


def _contract_code(errors: List[str]) -> str:
    for needle, code in _CONTRACT_CODES:
        if any(needle in error for error in errors):
            return code
    return "AF-LAUNCH-PLAN-SCHEMA"


def contract_violations(plan: Any) -> List[str]:
    """Every violation the shared U-CONTRACT validator names, or one named refusal.

    Canonical validation is the shared validator's own: shape, schema_version,
    unique unit ids, ``waits_for`` resolution, cycles, ``draft_only`` consts,
    Conversation AI law and the promotional cap. This module never restates
    those rules; it only maps them to this skill's autofail codes.
    """
    module = _contract_module()
    if module is None:
        return [f"{PLAN_VALIDATOR_REF} is not installed; the launch plan cannot be validated"]
    try:
        return list(module.validate_plan(plan, module.load_json(module.SCHEMA_PATH)))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"the shared launch-plan validator is unusable ({exc})"]


def validate_plan(plan: Any) -> None:
    """Fail closed on a plan the shared contract refuses. File existence is not proof."""
    if not isinstance(plan, Mapping):
        raise LaunchPlanError("AF-LAUNCH-PLAN-SHAPE", "the launch plan must be an object")
    errors = contract_violations(plan)
    if errors:
        raise LaunchPlanError(_contract_code(errors), "; ".join(errors))


def _zone(value: Any) -> ZoneInfo:
    if not _nonempty_str(value):
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-ZONE",
                              "launch_calendar.timezone must name an IANA zone")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-ZONE",
                              f"launch_calendar.timezone {value!r} is not an IANA zone") from exc


def parse_deadline(value: Any, field: str,
                   zone: Optional[ZoneInfo] = None) -> datetime.datetime:
    """One aware deadline. A zone-less or DST-wrong offset is never a deadline.

    ``zone`` checks the claimed UTC offset against the IANA zone the calendar
    names at that instant, so a New York deadline written with a summer offset
    in winter is refused rather than silently moved by an hour.
    """
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
    if zone is not None:
        claimed = parsed.utcoffset()
        actual = parsed.astimezone(zone).utcoffset()
        if claimed != actual:
            raise LaunchPlanError(
                "AF-LAUNCH-CALENDAR-OFFSET",
                f"{field} {value!r} claims UTC offset {claimed} but {zone.key} is at "
                f"{actual} at that instant (DST-aware offsets only)")
    return parsed


def _time(value: Any, field: str, zone: Optional[ZoneInfo] = None) -> datetime.datetime:
    return parse_deadline(value, field, zone)


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

    zone = _zone(calendar["timezone"])
    teaser = _time(black_friday["teaser_at"], "black_friday.teaser_at", zone)
    countdown = _time(black_friday["countdown_at"], "black_friday.countdown_at", zone)
    doors_open = _time(calendar["doors_open_at"], "doors_open_at", zone)
    launch_at = _time(calendar["launch_at"], "launch_at", zone)
    cyber_monday = _time(black_friday["cyber_monday_at"], "black_friday.cyber_monday_at", zone)
    last_call = _time(black_friday["last_call_at"], "black_friday.last_call_at", zone)
    doors_close = _time(calendar["doors_close_at"], "doors_close_at", zone)

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
    if doors_open >= doors_close:
        raise LaunchPlanError("AF-LAUNCH-CALENDAR-ORDER",
                              "doors open at or after doors close; the open window is never empty")

    phases = [
        {"phase": "teaser", "at": black_friday["teaser_at"]},
        {"phase": "countdown", "at": black_friday["countdown_at"]},
        {"phase": "doors_open", "at": calendar["doors_open_at"]},
        {"phase": "cyber_monday", "at": black_friday["cyber_monday_at"]},
        {"phase": "last_call", "at": black_friday["last_call_at"]},
        {"phase": "doors_close", "at": calendar["doors_close_at"]},
    ]
    # The calendar's own deadlines are proved first so a malformed deadline keeps
    # its precise code; the shared contract then validates the rest of the plan.
    validate_plan(plan)
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


def calendar_violations(plan: Any) -> List[Dict[str, str]]:
    """The calendar's violations as data, for a compiler that cannot raise.

    L07 compiles schedule nodes from this calendar; it needs the refusal as a
    record, not an exception mid-compile. Empty list means the calendar holds.
    """
    try:
        black_friday_calendar(plan)
    except LaunchPlanError as exc:
        return [{"code": exc.code, "detail": exc.detail}]
    return []


def calendar_instants(plan: Mapping[str, Any]) -> Dict[str, datetime.datetime]:
    """Every phase as an aware instant, after the calendar has been validated.

    L07 compiles absolute and relative schedule nodes and applies past-time
    policy; both need the instant, never the string, and both must use the
    same validated calendar this skill seals.
    """
    calendar = black_friday_calendar(plan)
    zone = _zone(calendar["timezone"])
    black_friday = calendar["black_friday"]
    return {
        "teaser": parse_deadline(black_friday["teaser_at"], "black_friday.teaser_at", zone),
        "countdown": parse_deadline(black_friday["countdown_at"],
                                    "black_friday.countdown_at", zone),
        "doors_open": parse_deadline(calendar["doors_open_at"], "doors_open_at", zone),
        "launch": parse_deadline(calendar["launch_at"], "launch_at", zone),
        "cyber_monday": parse_deadline(black_friday["cyber_monday_at"],
                                       "black_friday.cyber_monday_at", zone),
        "last_call": parse_deadline(black_friday["last_call_at"],
                                    "black_friday.last_call_at", zone),
        "doors_close": parse_deadline(calendar["doors_close_at"], "doors_close_at", zone),
    }


def planned_units(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Every unit the plan promises, in plan order: pages, emails, texts, automations, AI.

    A unit id is unique across all sections (contract ``unit_id``). The optional
    Conversation AI is a planned unit exactly when the client requested it.
    The plan is canonically validated first, so a cycle or an unknown dependency
    is refused here, long before a scheduler could stall on it.
    """
    validate_plan(plan)
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
