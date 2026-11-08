"""Council planning in the launch plan (Skill 77).

Two things happen in this step and they are labelled separately:

1. **The readiness probe.** The installed package is asked whether it is intact
   through its documented offline entry point (``scripts/doctor.mjs``: no
   network, no writes, no model call). Its answer is recorded under
   ``package_check``. A passing doctor is a PACKAGE CHECK and is never
   presented as advice.

2. **The advice record.** This step does not open a Council sitting. It records
   a Council session result only when one has actually been returned and is
   supplied to the caller as data (``session=`` on ``planning_step``, or the
   ``runner`` seam the existing tests use). That record is carried verbatim
   under ``council_session`` and a completed verdict becomes ``advice``. When
   no such result exists, the fact is recorded — no session was held, no elder
   saw the offer, price or calendar — and the build continues independently.

Rules this module enforces:

- **No Council front door is invoked.** This module never runs the live advice
  front door, never convenes a session, never starts a round and never calls a
  model. The only executable it runs is the offline readiness entry point above.
- **A readiness result is a package check, never advice.** It is recorded under
  ``package_check`` and every record says so in ``detail`` and
  ``client_summary``.
- A session in progress is NOT advice. ``council_session_held`` stays ``false``
  until a returned result carries a verdict. Nothing here reads like a review
  that did not happen.
- By default a not-ready result is recorded and the build CONTINUES. The record
  carries ``blocks_build: false`` as a literal, so no caller can turn advice into
  a gate. A caller that wants real advice passes ``council_required=True`` and
  the step refuses (CouncilRequiredError) unless a returned session carries
  advice.
- Advice is never permission: ``is_permission`` is likewise a literal false.
- The Council roster is the installed nine-seat roster when it can be read, and
  the documented nine seats otherwise. The Skill 22 persona blueprints govern
  launch tasks; they are not Council seats. Simon Sinek and Russell Brunson are
  seats, Alex Hormozi is not, and no tenth seat is added.
- No quotation and no real-person endorsement is produced by this step.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .constants import (COUNCIL_ADVICE_SUMMARY, COUNCIL_ENTRY_POINT,
                        COUNCIL_NO_ADVICE_SUMMARY, COUNCIL_SKILL_SLUG,
                        REPO_ROOT, SEAMS, skill_path)

STEP = "council_launch_planning"
ADVICE_PENDING = "pending_live_session"
ADVICE_RETURNED = "returned"
STATUSES = ("ready_no_advice", "advice_returned", "not_ready")

PERSONA_ADAPTER_REF = ("49-signature-funnel/scripts/persona_brief.py",
                       "signature-funnel/scripts/persona_brief.py")
# Presentation only. A launch plan's own IANA zone wins when the caller passes one.
DEFAULT_DISPLAY_TIMEZONE = "America/New_York"

# The documented fixed roster (Skill 77 config/advisors.json, "The nine seats"),
# used when the installed advisors registry cannot be read. Never a tenth seat.
NINE_SEATS = ("simon-sinek", "td-jakes", "oprah-winfrey", "tiffany-aliche",
              "russell-brunson", "michelle-obama", "brene-brown",
              "dennis-kimbro", "les-brown")

Runner = Callable[[Dict[str, Any]], Dict[str, Any]]
_ADAPTER: Any = None


class CouncilRequiredError(Exception):
    """council_required was set and no returned Council session carried advice."""

    code = "AF-LAUNCH-COUNCIL-REQUIRED"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")
        self.detail = detail


def skill_root() -> Path:
    """The Council tree, resolved by slug under either naming convention."""
    return skill_path(COUNCIL_SKILL_SLUG)


def entry_point() -> Path:
    """The documented offline entry point used by the readiness probe."""
    return skill_root() / COUNCIL_ENTRY_POINT


# --------------------------------------------------------------------------- #
# The readiness probe (never called "advice", never a session)
# --------------------------------------------------------------------------- #
def run_skill77(launch: Dict[str, Any], timeout_s: int = 120) -> Dict[str, Any]:
    """Ask the installed Skill 77 package whether it is ready. Offline only.

    No session is started, no model is called, nothing is written. A missing
    tree, a missing runtime or a non-zero doctor exit is reported as not-ready,
    never guessed into a verdict.
    """
    root = skill_root()
    entry = entry_point()
    if not entry.is_file():
        return {"status": "not_ready", "ready": False,
                "detail": f"{COUNCIL_SKILL_SLUG}/{COUNCIL_ENTRY_POINT} is not installed",
                "advice": None, "advice_state": ADVICE_PENDING}
    node = shutil.which("node")
    if not node:
        return {"status": "not_ready", "ready": False,
                "detail": "no node runtime on PATH; the Skill 77 entry point cannot run",
                "advice": None, "advice_state": ADVICE_PENDING}
    try:
        proc = subprocess.run(
            [node, str(entry), "--root", str(root)],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "not_ready", "ready": False,
                "detail": f"Skill 77 entry point failed to run: {exc}",
                "advice": None, "advice_state": ADVICE_PENDING}
    ok = proc.returncode == 0
    lines = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip().splitlines()
    detail = "package check only, no Council session: " + (lines[-1] if lines else "")
    return {
        "status": "ready_no_advice" if ok else "not_ready",
        "ready": ok,
        "exit_code": proc.returncode,
        "detail": detail,
        "advice": None,
        "advice_state": ADVICE_PENDING,
    }


# --------------------------------------------------------------------------- #
# Roster
# --------------------------------------------------------------------------- #
def seat_ids() -> "tuple":
    """(roster, source). The installed registry wins; the documented roster is the fallback."""
    try:
        registry = skill_root() / "config" / "advisors.json"
        data = json.loads(registry.read_text(encoding="utf-8"))
        seats = tuple(seat["seat_id"] for seat in data["seats"] if seat.get("seat_id"))
        if len(seats) == len(NINE_SEATS):
            return seats, str(registry)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return NINE_SEATS, "documented roster (Skill 77 config/advisors.json)"


# --------------------------------------------------------------------------- #
# The launch task personas (Skill 22 Task Mode, via the existing blend seam)
# --------------------------------------------------------------------------- #
def _persona_adapter() -> Any:
    """Load the launch persona adapter by path, in either repository layout.

    The onboarding layout keeps the skill at ``49-signature-funnel/``; a deployed
    999 tree keeps it at ``.claude/skills/signature-funnel/``. The adapter is
    ``persona_brief.apply_launch_personas`` (F10) — one home, no second copy.
    """
    global _ADAPTER
    if _ADAPTER is not None:
        return _ADAPTER
    roots = [REPO_ROOT, REPO_ROOT / ".claude" / "skills", REPO_ROOT / "skills"]
    for ref in PERSONA_ADAPTER_REF:
        for root in roots:
            path = root / ref
            if not path.is_file():
                continue
            spec = importlib.util.spec_from_file_location("s49_persona_brief", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _ADAPTER = module
            return _ADAPTER
    return None


def persona_application(launch: Dict[str, Any],
                        run_dir: Optional[str] = None) -> Dict[str, Any]:
    """What the Skill 22 task personas actually governed. Never raises."""
    module = _persona_adapter()
    if module is None:
        return {"adapter": None,
                "detail": "signature-funnel/scripts/persona_brief.py is not installed; no "
                          "launch task persona was applied",
                "task_personas": []}
    try:
        return module.apply_launch_personas(launch=launch, run_dir=run_dir)
    except Exception as exc:  # noqa: BLE001 — a persona record never blocks a build
        return {"adapter": None,
                "detail": f"launch persona adapter failed: {type(exc).__name__}: {exc}",
                "task_personas": []}


# --------------------------------------------------------------------------- #
# The launch context the Council would need, recorded beside the advice
# --------------------------------------------------------------------------- #
def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _display_timezone(launch: Dict[str, Any]) -> str:
    calendar = launch.get("launch_calendar")
    if isinstance(calendar, dict) and isinstance(calendar.get("timezone"), str) \
            and calendar["timezone"].strip():
        return calendar["timezone"].strip()
    if isinstance(launch.get("display_timezone"), str) and launch["display_timezone"].strip():
        return launch["display_timezone"].strip()
    return DEFAULT_DISPLAY_TIMEZONE


def offer_ladder(launch: Dict[str, Any]) -> "list":
    """The offer ladder exactly as recorded: role, name, price, level, delivery."""
    ladder = []
    for offer in launch.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        level = offer.get("level") if isinstance(offer.get("level"), dict) else {}
        delivery = offer.get("delivery") if isinstance(offer.get("delivery"), dict) else {}
        ladder.append({
            "offer_id": offer.get("offer_id"),
            "role": offer.get("role"),
            "name": offer.get("name"),
            "price": offer.get("price"),
            "level_state": level.get("state"),
            "level_name": level.get("name"),
            "deliverables": list(level.get("deliverables") or []),
            "delivery_destination": delivery.get("destination"),
            "relationships": offer.get("relationships") or {},
        })
    return ladder


def purchase_graph(launch: Dict[str, Any],
                   graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The compiled route when the caller has it; otherwise the recorded roles."""
    if isinstance(graph, dict) and graph.get("nodes"):
        return {"nodes": [{"page_id": n.get("page_id"), "role": n.get("role")}
                          for n in graph.get("nodes") or []],
                "edges": [{"from": e.get("from"), "to": e.get("to"), "event": e.get("event")}
                          for e in graph.get("edges") or []],
                "source": "compiled route graph"}
    roles = []
    for offer in launch.get("offers") or []:
        if isinstance(offer, dict) and offer.get("role"):
            roles.append({"role": offer["role"], "offer_id": offer.get("offer_id")})
    return {"journey_mode": launch.get("journey_mode"), "offers": roles,
            "source": "recorded offers (route graph not supplied)"}


def fulfilment(launch: Dict[str, Any]) -> Dict[str, Any]:
    """Where a buyer actually receives each offer, exactly as recorded."""
    rows = []
    for offer in launch.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        delivery = offer.get("delivery") if isinstance(offer.get("delivery"), dict) else {}
        rows.append({"offer_id": offer.get("offer_id"), "role": offer.get("role"),
                     "destination": delivery.get("destination"),
                     "owner_confirmed": delivery.get("owner_confirmed")})
    return {"offers": rows, "cross_sales_teaching": "pending"}


def unresolved_decisions(launch: Dict[str, Any]) -> "list":
    """The open owner decisions, named from this skill's own seam registry."""
    out = [{"id": seam["id"], "decision": seam["decision"], "code_seam": seam["code_seam"]}
           for seam in SEAMS]
    choices = launch.get("client_choices")
    if isinstance(choices, list) and choices:
        out.append({"id": "client_scope_choices", "decision": "client choices recorded",
                    "detail": list(choices)})
    return out


def launch_context(launch: Dict[str, Any], *,
                   graph: Optional[Dict[str, Any]] = None,
                   personas: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What a Council would be asked to read, recorded beside the advice.

    The build passes brand, offer ladder, purchase graph, fulfilment and the
    unresolved strategic decisions so a returned session can be grounded in
    them and the record shows exactly what was held. Nothing here is advice.
    """
    personas = personas if isinstance(personas, dict) else persona_application(launch)
    roster, roster_source = seat_ids()
    brand = launch.get("brand") if isinstance(launch.get("brand"), dict) else {}
    return {
        "brand": {"ref": brand.get("ref"), "hash": brand.get("hash")},
        "promotion": launch.get("promotion"),
        "entitlement": launch.get("entitlement"),
        "offer_ladder": offer_ladder(launch),
        "purchase_graph": purchase_graph(launch, graph),
        "fulfilment": fulfilment(launch),
        "unresolved_strategic_decisions": unresolved_decisions(launch),
        "roster": list(roster),
        "roster_source": roster_source,
        "persona_application": {
            "voice_persona_id": personas.get("voice_persona_id"),
            "topic_persona_id": personas.get("topic_persona_id"),
            "task_personas": [p.get("persona_id") for p in personas.get("task_personas") or []],
        },
        "council_seat_note": (
            "The Council keeps its fixed nine seats; Simon Sinek and Russell Brunson are "
            "two of them, Alex Hormozi is not a seat, and no tenth seat is added. The "
            "Skill 22 task personas govern launch work, never Council seats."),
        "recorded_at": _utc_now(),
    }


# --------------------------------------------------------------------------- #
# A returned session result, supplied as data — never fetched, never convened
# --------------------------------------------------------------------------- #
def _advice_from_session(session: Any) -> Optional[Dict[str, Any]]:
    """The advice a supplied, already-returned session result actually carries."""
    if not isinstance(session, dict):
        return None
    advice = session.get("advice")
    if isinstance(advice, dict) and advice:
        return dict(advice)
    label = session.get("verdict_label")
    if isinstance(label, str) and label.strip():
        return {"verdict_label": label.strip(),
                "session_id": session.get("session_id"),
                "state": session.get("state"),
                "source": "recorded Council session result (supplied as data)"}
    return None


def session_result(session: Any) -> Dict[str, Any]:
    """Normalize a supplied, already-returned session result. Never raises."""
    advice = _advice_from_session(session)
    if advice is not None:
        carried = {k: session.get(k) for k in
                   ("session_id", "mode", "state", "verdict_label", "route_id", "model_label",
                    "selection_source", "chamber_link", "session_url", "report_url")
                   if isinstance(session, dict) and session.get(k) is not None}
        return {"status": "advice_returned", "ready": True, "advice": advice,
                "advice_state": ADVICE_RETURNED,
                "detail": "a returned Council session result carries advice; recorded verbatim.",
                "council_session": carried}
    return {"status": "ready_no_advice", "ready": True, "advice": None,
            "advice_state": ADVICE_PENDING,
            "detail": ("a Council session result was supplied but it carries no verdict, so no "
                       "Council advice was obtained.")}


# --------------------------------------------------------------------------- #
# The planning step
# --------------------------------------------------------------------------- #
def planning_step(launch: Dict[str, Any],
                  runner: Optional[Runner] = None,
                  council_required: bool = False,
                  *,
                  graph: Optional[Dict[str, Any]] = None,
                  run_dir: Optional[str] = None,
                  session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the Council planning step and return the record that travels with the build.

    The offline readiness probe always runs. The advice record is filled only
    from a result that actually came back: a caller-supplied ``runner`` (the
    existing test seam) or an already-returned session result passed as
    ``session`` data. No front door is called and no sitting is opened. Every
    failure is a recorded not-ready result, and by default the step never
    blocks. With ``council_required=True`` it raises CouncilRequiredError when
    no returned session carries advice (a package check alone is not a session).
    """
    launch = launch if isinstance(launch, dict) else {}
    package_check = run_skill77(launch)
    personas = persona_application(launch, run_dir)
    advice_source: Optional[str] = None

    if runner is not None:
        try:
            result = runner(launch)
        except Exception as exc:  # a runner failure is a recorded fact, not a crash
            result = {"status": "not_ready", "ready": False,
                      "detail": f"council runner error: {exc}",
                      "advice": None, "advice_state": ADVICE_PENDING}
        advice_source = "caller-supplied runner"
    elif session is not None:
        result = session_result(session)
        advice_source = "caller-supplied returned session result"
    else:
        result = dict(package_check)
        advice_source = None

    if not isinstance(result, dict):
        result = {"status": "not_ready", "ready": False,
                  "detail": f"council runner returned {type(result).__name__}",
                  "advice": None, "advice_state": ADVICE_PENDING}
    status = result.get("status")
    if status not in STATUSES:
        status = "not_ready"
    advice_state = result.get("advice_state")
    if advice_state not in (ADVICE_PENDING, ADVICE_RETURNED):
        advice_state = ADVICE_RETURNED if result.get("advice") else ADVICE_PENDING
    session_held = (status == "advice_returned" and advice_state == ADVICE_RETURNED
                    and bool(result.get("advice")))
    if council_required and not session_held:
        raise CouncilRequiredError(
            "council_required is set but no returned Council session carried advice "
            f"(status {status!r}); {COUNCIL_NO_ADVICE_SUMMARY}")

    record = {
        "step": STEP,
        "skill": COUNCIL_SKILL_SLUG,
        # The readiness probe's entry point, kept under its own name. Never advice.
        "entry_point": COUNCIL_ENTRY_POINT,
        "status": status,
        "ready": bool(result.get("ready")),
        "advice": result.get("advice"),
        "advice_state": advice_state,
        "detail": result.get("detail", ""),
        "council_session_held": session_held,
        "client_summary": COUNCIL_ADVICE_SUMMARY if session_held else COUNCIL_NO_ADVICE_SUMMARY,
        "blocks_build": False,
        "is_permission": False,
        "is_package_check_only": not session_held,
        "advice_source": advice_source,
        "package_check": {
            "entry_point": COUNCIL_ENTRY_POINT,
            "status": package_check.get("status"),
            "ready": bool(package_check.get("ready")),
            "detail": package_check.get("detail", ""),
            "is_advice": False,
        },
        "persona_application": personas,
        "launch_context": launch_context(launch, graph=graph, personas=personas),
    }
    if isinstance(result.get("council_session"), dict) and result["council_session"]:
        record["council_session"] = result["council_session"]
    return record
