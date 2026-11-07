"""Council advice in launch planning (Skill 77).

Two things happen in this step and they are labelled separately:

1. **The readiness probe.** The installed package is asked whether it is intact
   through its documented offline entry point (``scripts/doctor.mjs``: no
   network, no writes). Its answer is recorded under ``package_check``. A
   passing doctor is a PACKAGE CHECK and is never presented as advice.

2. **The advice handoff.** At the coherent-plan stage the step asks the
   installed Council front door for a light sitting::

       council-ask ask --brief FILE --mode light --json

   The brief carries the launch's brand, offer ladder, purchase graph,
   fulfilment facts and its unresolved strategic decisions, plus the launch
   task personas that were actually applied. The returned session result is
   recorded verbatim under ``council_session``; a completed session's verdict
   label becomes ``advice``. When the front door is not installed, no model
   route is configured, or the service refuses, that fact is recorded and the
   build continues independently.

Rules this module enforces:

- A session in progress is NOT advice. ``council_session_held`` stays ``false``
  and the client summary keeps saying no Council advice was obtained until a
  session returned a verdict. Nothing here reads like a review that did not
  happen.
- By default a not-ready result is recorded and the build CONTINUES. The record
  carries ``blocks_build: false`` as a literal, so no caller can turn advice into
  a gate. A caller that wants real advice passes ``council_required=True`` and
  the step refuses (CouncilRequiredError) unless a session returned advice.
- Advice is never permission: ``is_permission`` is likewise a literal false.
- The Council roster is the installed nine-seat roster when it can be read, and
  the documented nine seats otherwise. The Skill 22 persona blueprints govern
  launch tasks; they are not Council seats. Simon Sinek and Russell Brunson are
  seats, Alex Hormozi is not, and no tenth seat is added.
- No quotation and no real-person endorsement is produced by this step.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .constants import (COUNCIL_ADVICE_SUMMARY, COUNCIL_ENTRY_POINT,
                        COUNCIL_NO_ADVICE_SUMMARY, COUNCIL_SKILL_SLUG,
                        REPO_ROOT, SEAMS, skill_path)

STEP = "council_launch_planning"
ADVICE_PENDING = "pending_live_session"
ADVICE_RETURNED = "returned"
STATUSES = ("ready_no_advice", "advice_returned", "not_ready")

COUNCIL_FRONT_DOOR = "council-ask"
COUNCIL_ASK_MODE = "light"
BRIEF_SCHEMA_VERSION = "wise-elders.brief/v1"
PERSONA_ADAPTER_REF = ("49-signature-funnel/scripts/launch_persona_adapter.py",
                       "signature-funnel/scripts/launch_persona_adapter.py")
# Presentation only. A launch plan's own IANA zone wins when the caller passes one.
DEFAULT_DISPLAY_TIMEZONE = "America/New_York"

# The documented fixed roster (Skill 77 SKILL.md, "The nine seats"), used when the
# installed advisors registry cannot be read. Never a tenth seat.
NINE_SEATS = ("simon-sinek", "td-jakes", "oprah-winfrey", "tiffany-aliche",
              "russell-brunson", "michelle-obama", "brene-brown",
              "dennis-kimbro", "les-brown")

Runner = Callable[[Dict[str, Any]], Dict[str, Any]]
_ADAPTER: Any = None


class CouncilRequiredError(Exception):
    """council_required was set and no Council session returned advice."""

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
# The readiness probe (unchanged semantics; never called "advice")
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
# Front door + roster
# --------------------------------------------------------------------------- #
def front_door() -> Optional[Path]:
    """The installed ``council-ask`` executable, or None. Never guessed into a path."""
    candidates = []
    explicit = os.environ.get("COUNCIL_ASK", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            candidates.append(path)
        else:
            found = shutil.which(explicit)
            if found:
                candidates.append(Path(found))
    found = shutil.which(COUNCIL_FRONT_DOOR)
    if found:
        candidates.append(Path(found))
    roots = [os.environ.get("OPENCLAW_ROOT"),
             os.environ.get("WISE_ELDERS_OPENCLAW_ROOT"),
             str(Path.home() / ".openclaw"),
             "/data/.openclaw"]
    for root in roots:
        if root:
            candidates.append(Path(root) / "council-runtime" / "bin" / COUNCIL_FRONT_DOOR)
    candidates.append(Path.home() / ".local" / "bin" / COUNCIL_FRONT_DOOR)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


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
    return NINE_SEATS, "documented roster (Skill 77 SKILL.md)"


# --------------------------------------------------------------------------- #
# The launch task personas (Skill 22 Task Mode, via the existing blend seam)
# --------------------------------------------------------------------------- #
def _persona_adapter() -> Any:
    """Load the launch persona adapter by path, in either repository layout.

    The onboarding layout keeps the skill at ``49-signature-funnel/``; a deployed
    999 tree keeps it at ``.claude/skills/signature-funnel/``.
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
            spec = importlib.util.spec_from_file_location("s49_launch_persona_adapter", path)
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
                "detail": "launch_persona_adapter.py is not installed; no launch task "
                          "persona was applied",
                "task_personas": []}
    try:
        return module.apply_launch_personas(launch=launch, run_dir=run_dir)
    except Exception as exc:  # noqa: BLE001 — a persona record never blocks a build
        return {"adapter": None,
                "detail": f"launch persona adapter failed: {type(exc).__name__}: {exc}",
                "task_personas": []}


# --------------------------------------------------------------------------- #
# The decision brief handed to the front door
# --------------------------------------------------------------------------- #
def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(text: Any, fallback: str) -> str:
    """An opaque id the Council contract accepts (1-128 of [A-Za-z0-9._:-])."""
    raw = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(text or "")).strip("-.")
    if not raw or not raw[0].isalnum():
        raw = fallback + ("-" + raw if raw else "")
    return raw[:120]


def _display_timezone(launch: Dict[str, Any]) -> str:
    calendar = launch.get("launch_calendar")
    if isinstance(calendar, dict) and isinstance(calendar.get("timezone"), str) \
            and calendar["timezone"].strip():
        return calendar["timezone"].strip()
    if isinstance(launch.get("display_timezone"), str) and launch["display_timezone"].strip():
        return launch["display_timezone"].strip()
    return DEFAULT_DISPLAY_TIMEZONE


def _money(price: Dict[str, Any]) -> str:
    amount = price.get("amount_minor")
    currency = price.get("currency")
    return f"{amount} minor units of {currency}"


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


def purchase_graph(launch: Dict[str, Any], graph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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


def build_brief(launch: Dict[str, Any], *, graph: Optional[Dict[str, Any]] = None,
                personas: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The DecisionBrief the Council front door reads. Facts only, unknowns kept."""
    launch = launch if isinstance(launch, dict) else {}
    launch_id = launch.get("launch_id")
    revision = launch.get("revision") if isinstance(launch.get("revision"), int) else 1
    roster, _ = seat_ids()
    facts, unknowns, assumptions, constraints = [], [], [], []

    def fact(ident: str, statement: str) -> None:
        facts.append({"id": _id(ident, "fact"), "statement": statement, "evidence_ids": []})

    def unknown(ident: str, statement: str) -> None:
        unknowns.append({"id": _id(ident, "unknown"), "statement": statement, "evidence_ids": []})

    brand = launch.get("brand") if isinstance(launch.get("brand"), dict) else {}
    if brand.get("ref"):
        fact("fact-brand", f"The approved launch carries brand reference {brand.get('ref')!r} "
                           "and its brand hash; the launch record states no brand name, "
                           "colour or voice beyond that reference.")
        unknown("unknown-brand-voice",
                "The brand name, colours and voice are not stated in the launch record; "
                "the brand reference and hash are the only brand facts held.")
    if launch.get("copy_profile"):
        fact("fact-copy-profile", f"The launch's copy profile reference is {launch.get('copy_profile')!r}.")
    entitlement = launch.get("entitlement") if isinstance(launch.get("entitlement"), dict) else {}
    if entitlement.get("basis"):
        fact("fact-entitlement",
             f"Entitlement basis {entitlement.get('basis')!r}; a new purchase is "
             f"{'required' if entitlement.get('requires_purchase') else 'not required'}.")
    for index, row in enumerate(offer_ladder(launch), start=1):
        if row.get("price"):
            fact(f"fact-offer-{index}",
                 f"Offer {row.get('offer_id')!r} ({row.get('role')}) is {row.get('name')!r}, "
                 f"priced {_money(row['price'])}.")
        if row.get("level_state") == "supplied":
            fact(f"fact-offer-level-{index}",
                 f"Offer {row.get('offer_id')!r} level {row.get('level_name')!r} delivers: "
                 f"{'; '.join(row.get('deliverables') or []) or 'no deliverable stated'}.")
        elif row.get("role") in ("main", "bump", "upsell_1", "downsell_1", "upsell_2"):
            unknown(f"unknown-offer-level-{index}",
                    f"The level and deliverables of offer {row.get('offer_id')!r} are unknown.")
        if row.get("delivery_destination"):
            fact(f"fact-offer-delivery-{index}",
                 f"Buyers of offer {row.get('offer_id')!r} are sent to "
                 f"{row.get('delivery_destination')!r}.")
    promotion = launch.get("promotion") if isinstance(launch.get("promotion"), dict) else None
    if promotion is not None:
        fact("fact-promotion",
             "The client's approved promotion is recorded: kind "
             f"{promotion.get('kind')!r}, limitations {promotion.get('limitations')!r}, "
             f"buyers {promotion.get('buyers')!r}, follow-up {promotion.get('followup')!r}, "
             f"seat limit {promotion.get('seat_limit')!r} ({promotion.get('seat_limit_state')!r}).")
        assumptions.append({"id": "assumption-promotion-approved",
                            "statement": "The recorded promotion is the client's approved promotion.",
                            "evidence_ids": []})
    else:
        unknown("unknown-promotion",
                "The launch record carries no approved promotion (kind, limitations, "
                "buyers, follow-up and seat limit are not recorded).")
    choices = launch.get("client_choices")
    if isinstance(choices, list) and choices:
        fact("fact-client-choices",
             f"The client chose to leave these out of the launch: {', '.join(choices)}.")
    for note in unresolved_decisions(launch):
        unknown(f"unknown-decision-{note['id']}",
                f"Unresolved strategic decision {note['id']!r}: {note['decision']}")
    personas = personas if isinstance(personas, dict) else persona_application(launch)
    applied = [f"{p.get('task')} -> {p.get('persona_id')}"
               for p in personas.get("task_personas") or []]
    if applied:
        fact("fact-launch-task-personas",
             "Launch task personas actually applied (Skill 22 Task Mode, not Council seats): "
             + "; ".join(applied) + ".")

    constraints.extend([
        {"id": "constraint-nine-seats",
         "description": "The Council seats its fixed nine seats; Simon Sinek and Russell "
                        "Brunson are two of them, Alex Hormozi is not a seat, and no tenth "
                        "seat is added.",
         "hard": True, "applies_to_option_ids": []},
        {"id": "constraint-advice-not-permission",
         "description": "A Council result is advice, never permission; it authorizes no "
                        "publication, spend or client-facing send.",
         "hard": True, "applies_to_option_ids": []},
        {"id": "constraint-promotion-unchanged",
         "description": "The client's approved promotion is not changed, expanded or "
                        "replaced by this session.",
         "hard": True, "applies_to_option_ids": []},
        {"id": "constraint-no-quotes",
         "description": "No quotation, first-person authorship or real-person endorsement "
                        "is produced; persona material is style-inspired only.",
         "hard": True, "applies_to_option_ids": []},
    ])

    options = [
        {"id": "option-proceed-approved-plan", "kind": "status_quo",
         "label": "Proceed to build the approved launch plan exactly as recorded, with every "
                  "recorded unknown still unknown."},
        {"id": "option-proceed-with-conditions", "kind": "bounded_test",
         "label": "Proceed to build and carry the unresolved strategic decisions as named "
                  "conditions to settle before publication."},
        {"id": "option-hold-for-decisions", "kind": "bounded_test",
         "label": "Hold the build until the owner supplies the unresolved strategic decisions."},
    ]

    return {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "brief_id": _id(f"brief-launch-{launch_id}-r{revision}", "brief"),
        "session_id": _id(f"pending-session-{launch_id}-r{revision}", "pending-session"),
        "revision": 1,
        "question": (f"Is the approved Black Friday launch plan {launch_id!r} coherent — brand "
                     "promise and voice, offer ladder, purchase graph and fulfilment — and "
                     "what, if anything, must be settled before the build proceeds?"),
        "facts": facts,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "constraints": constraints,
        "options": options,
        "relevance_weights": {seat: 1 for seat in roster},
        "critical_domains": [],
        "evidence_manifest": [],
        "private_preference_ref": None,
        "created_at": _utc_now(),
        "display_timezone": _display_timezone(launch),
    }


def launch_context(launch: Dict[str, Any], *,
                   graph: Optional[Dict[str, Any]] = None,
                   personas: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the Council was asked to read, recorded beside the brief.

    The Council's DecisionBrief is a strict object, so this travels in the launch
    record (and ``council-advice.json``) instead of inside the brief."""
    personas = personas if isinstance(personas, dict) else persona_application(launch)
    roster, roster_source = seat_ids()
    return {
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
    }


def _run_json(argv: "list", timeout_s: int) -> "tuple":
    """Run the front door and parse its one JSON document. Never raises."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                              check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    text = (proc.stdout or "").strip()
    payload = None
    if text:
        try:
            payload = json.loads(text)
        except ValueError:
            start, end = text.find("{"), text.rfind("}")
            if 0 <= start < end:
                try:
                    payload = json.loads(text[start:end + 1])
                except ValueError:
                    payload = None
    err = (proc.stderr or "").strip()
    return payload, (err[-800:] if err else f"exit {proc.returncode}")


def run_council_ask(launch: Dict[str, Any], *, graph: Optional[Dict[str, Any]] = None,
                    personas: Optional[Dict[str, Any]] = None,
                    timeout_s: int = 180,
                    session_timeout_s: int = 45) -> Dict[str, Any]:
    """Ask the installed front door for a light sitting and record what came back."""
    entry = front_door()
    handoff: Dict[str, Any] = {"attempted": False, "front_door": None,
                               "mode": COUNCIL_ASK_MODE, "returned": False}
    if entry is None:
        handoff["reason"] = ("council-ask is not installed; the advice handoff did not run "
                             "(set OPENCLAW_ROOT or COUNCIL_ASK, or install the Council front door)")
        return {"status": "not_ready", "ready": False, "advice": None,
                "advice_state": ADVICE_PENDING,
                "detail": "no Council front door is installed, so no Council session was asked "
                          "for and no Council advice was obtained",
                "advice_handoff": handoff}
    brief = build_brief(launch, graph=graph, personas=personas)
    handoff.update({"attempted": True, "front_door": str(entry),
                    "brief_sha256": _sha256(json.dumps(brief, sort_keys=True))})
    with tempfile.TemporaryDirectory(prefix="bf-launch-council-") as tmp:
        brief_path = Path(tmp) / "council-brief.json"
        brief_path.write_text(json.dumps(brief, indent=2, sort_keys=True), encoding="utf-8")
        payload, detail = _run_json(
            [str(entry), "ask", "--brief", str(brief_path),
             "--mode", COUNCIL_ASK_MODE, "--json"], timeout_s)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error = (payload or {}).get("error") if isinstance(payload, dict) else None
        code = (error or {}).get("code") if isinstance(error, dict) else None
        message = (error or {}).get("message") if isinstance(error, dict) else detail
        handoff.update({"returned": False, "error_code": code, "error": message})
        return {"status": "not_ready", "ready": False, "advice": None,
                "advice_state": ADVICE_PENDING,
                "detail": f"the Council front door refused or failed ({code or 'no JSON answer'}): "
                          f"{message}; no Council advice was obtained",
                "brief": brief, "advice_handoff": handoff}
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        handoff.update({"returned": False, "error": "the convene answer carried no session id"})
        return {"status": "not_ready", "ready": False, "advice": None,
                "advice_state": ADVICE_PENDING,
                "detail": "the Council front door answered without a session id; nothing is "
                          "invented, so no Council advice was obtained",
                "brief": brief, "advice_handoff": handoff}
    session = {
        "session_id": session_id,
        "mode": payload.get("mode"),
        "route_id": payload.get("route_id"),
        "model_label": payload.get("model_label"),
        "selection_source": payload.get("selection_source"),
        "service_origin": payload.get("service_origin"),
        "chamber_link": payload.get("chamber_link"),
        "chamber_link_local": payload.get("chamber_link_local"),
        "session_url": payload.get("session_url"),
        "events_url": payload.get("events_url"),
        "prior_completed_same_question": payload.get("prior_completed_same_question") or [],
    }
    handoff.update({"returned": True, "session_id": session_id})
    read_payload, read_detail = _run_json(
        [str(entry), "session", session_id, "--json"], session_timeout_s)
    state = (read_payload or {}).get("state") if isinstance(read_payload, dict) else None
    label = (read_payload or {}).get("verdict_label") if isinstance(read_payload, dict) else None
    handoff["session_read"] = {"state": state, "verdict_label": label,
                               "detail": None if read_payload else read_detail}
    if state == "COMPLETED" and label:
        return {
            "status": "advice_returned", "ready": True,
            "advice": {"verdict_label": label, "session_id": session_id, "state": state,
                       "source": "council-ask session (service store)"},
            "advice_state": ADVICE_RETURNED,
            "detail": f"Council session {session_id} completed with verdict {label!r}.",
            "brief": brief, "council_session": session, "advice_handoff": handoff,
        }
    return {
        "status": "ready_no_advice", "ready": True, "advice": None,
        "advice_state": ADVICE_PENDING,
        "detail": (f"Council session {session_id} was convened in {COUNCIL_ASK_MODE} mode; no "
                   f"verdict was returned (session state {state or 'unknown'}), so no Council "
                   "advice was obtained."),
        "brief": brief, "council_session": session, "advice_handoff": handoff,
    }


def read_council_session(session_id: str, launch: Dict[str, Any], *,
                         timeout_s: int = 45) -> Dict[str, Any]:
    """Read an already-convened sitting through the front door and record its verdict.

    A sitting outlives the build step that opened it, so the honest record of a
    completed Council comes from this read, never from a second convene and never
    from a guess. Nothing is invented: no front door, an unknown session or no
    verdict all record "no advice was obtained" and the build continues.
    """
    entry = front_door()
    handoff: Dict[str, Any] = {"attempted": False, "front_door": None,
                               "mode": None, "returned": False, "read_only": True,
                               "session_id": session_id}
    if entry is None:
        handoff["reason"] = "council-ask is not installed, so the sitting cannot be read"
        return {"status": "not_ready", "ready": False, "advice": None,
                "advice_state": ADVICE_PENDING,
                "detail": "no Council front door is installed, so no Council advice was obtained",
                "advice_handoff": handoff}
    handoff.update({"attempted": True, "front_door": str(entry)})
    payload, detail = _run_json([str(entry), "session", session_id, "--json"], timeout_s)
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        error = (payload or {}).get("error") if isinstance(payload, dict) else None
        code = (error or {}).get("code") if isinstance(error, dict) else None
        message = (error or {}).get("message") if isinstance(error, dict) else detail
        handoff.update({"returned": False, "error_code": code, "error": message})
        return {"status": "not_ready", "ready": False, "advice": None,
                "advice_state": ADVICE_PENDING,
                "detail": f"the Council session {session_id} could not be read "
                          f"({code or 'no JSON answer'}): {message}; no Council advice was obtained",
                "advice_handoff": handoff}
    state = payload.get("state")
    label = payload.get("verdict_label")
    handoff.update({"returned": True, "session_read": {"state": state, "verdict_label": label,
                                                       "detail": None}})
    session = {
        "session_id": session_id,
        "mode": payload.get("mode"),
        "state": state,
        "verdict_label": label,
        "chamber_link": payload.get("chamber_link"),
        "chamber_link_local": payload.get("chamber_link_local"),
        "chamber_link_client_safe": payload.get("chamber_link_client_safe"),
        "report_url": payload.get("report_url"),
        "report_url_local": payload.get("report_url_local"),
        "report_url_client_safe": payload.get("report_url_client_safe"),
        "service_origin": payload.get("service_origin"),
    }
    if state == "COMPLETED" and label:
        return {
            "status": "advice_returned", "ready": True,
            "advice": {"verdict_label": label, "session_id": session_id, "state": state,
                       "source": "council-ask session (service store, read-only)"},
            "advice_state": ADVICE_RETURNED,
            "detail": f"Council session {session_id} completed with verdict {label!r}.",
            "council_session": session, "advice_handoff": handoff,
        }
    return {
        "status": "ready_no_advice", "ready": True, "advice": None,
        "advice_state": ADVICE_PENDING,
        "detail": (f"Council session {session_id} has no verdict yet (session state "
                   f"{state or 'unknown'}), so no Council advice was obtained."),
        "council_session": session, "advice_handoff": handoff,
    }


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _briefable(launch: Dict[str, Any]) -> bool:
    """A coherent plan exists to read: launch id, brand and at least one offer."""
    return (isinstance(launch, dict)
            and bool(launch.get("launch_id"))
            and isinstance(launch.get("brand"), dict)
            and isinstance(launch.get("offers"), list) and bool(launch["offers"]))


# --------------------------------------------------------------------------- #
# The planning step
# --------------------------------------------------------------------------- #
def planning_step(launch: Dict[str, Any],
                  runner: Optional[Runner] = None,
                  council_required: bool = False,
                  *,
                  graph: Optional[Dict[str, Any]] = None,
                  run_dir: Optional[str] = None,
                  ask: bool = True,
                  session_id: Optional[str] = None) -> Dict[str, Any]:
    """Run the Council planning step and return the record that travels with the build.

    The readiness probe always runs. The advice handoff runs when a caller-supplied
    runner is absent, ``ask`` is true and the launch is coherent enough to brief.
    With ``session_id`` an already-convened sitting is READ instead of a second one
    being opened, so a sitting that completed after the dispatch is recorded as
    advice. Every failure is a recorded not-ready result, and by default the step
    never blocks. With ``council_required=True`` it raises CouncilRequiredError when
    no Council session returned advice (a package check alone is not a session).
    """
    launch = launch if isinstance(launch, dict) else {}
    package_check = run_skill77(launch)
    personas = persona_application(launch, run_dir)
    handoff: Dict[str, Any] = {"attempted": False, "front_door": None,
                               "mode": COUNCIL_ASK_MODE, "returned": False, "reason": None}

    if runner is not None:
        try:
            result = runner(launch)
        except Exception as exc:  # a runner failure is a recorded fact, not a crash
            result = {"status": "not_ready", "ready": False,
                      "detail": f"council runner error: {exc}",
                      "advice": None, "advice_state": ADVICE_PENDING}
        handoff["reason"] = "a caller-supplied runner was used"
    elif session_id:
        result = read_council_session(str(session_id), launch)
        handoff.update(result.get("advice_handoff") or {})
    elif not ask:
        result = dict(package_check)
        handoff["reason"] = "the caller disabled the advice handoff"
    elif not _briefable(launch):
        result = dict(package_check)
        handoff["reason"] = ("no coherent launch plan to brief: a launch_id, a brand and at "
                             "least one offer are required before the Council can read the plan")
    else:
        result = run_council_ask(launch, graph=graph, personas=personas)
        handoff.update(result.get("advice_handoff") or {})

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
    session_held = status == "advice_returned" and advice_state == ADVICE_RETURNED \
        and bool(result.get("advice"))
    if council_required and not session_held:
        raise CouncilRequiredError(
            "council_required is set but no Council session returned advice "
            f"(status {status!r}); {COUNCIL_NO_ADVICE_SUMMARY}")

    attempted = bool(handoff.get("attempted"))
    record = {
        "step": STEP,
        "skill": COUNCIL_SKILL_SLUG,
        # The readiness probe's entry point. The advice handoff names its own below.
        "entry_point": COUNCIL_ENTRY_POINT,
        "advice_entry_point": (f"{COUNCIL_FRONT_DOOR} ask --brief FILE --mode "
                               f"{COUNCIL_ASK_MODE} --json" if attempted else None),
        "status": status,
        "ready": bool(result.get("ready")),
        "advice": result.get("advice"),
        "advice_state": advice_state,
        "detail": result.get("detail", ""),
        "council_session_held": session_held,
        "client_summary": COUNCIL_ADVICE_SUMMARY if session_held else COUNCIL_NO_ADVICE_SUMMARY,
        "blocks_build": False,
        "is_permission": False,
        # The readiness probe, kept under its own name. Never called advice.
        "package_check": {
            "entry_point": COUNCIL_ENTRY_POINT,
            "status": package_check.get("status"),
            "ready": bool(package_check.get("ready")),
            "detail": package_check.get("detail", ""),
        },
        "advice_handoff": handoff,
        "persona_application": personas,
    }
    if isinstance(result.get("council_session"), dict):
        record["council_session"] = result["council_session"]
    if isinstance(result.get("brief"), dict):
        record["brief"] = result["brief"]
    if attempted or _briefable(launch):
        record["launch_context"] = launch_context(launch, graph=graph, personas=personas)
    return record
