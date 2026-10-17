#!/usr/bin/env python3
"""
conversation_layer.py - the FIX-PLAN Item 33b seam module (presentations side).

WHAT THIS IS
-------------------------------------------------------------------------------------
Skill 38 (conversational-ai-system) serves exactly three human-facing seams
for presentations, and this module is the department side of all three:

  (a) PARK / RESUME CLIENT COMMUNICATION. When a run parks for client action,
      the client hears what is needed in plain words and their reply routes
      back into the engine's own resume machinery. When a run parks for the
      operator or for a transient failure, the client hears NOTHING as if it
      were their move.
  (b) POST-DELIVERY FOLLOW-UP. After a deck is verifiably delivered, a
      bounded conversational sequence: thank-you, package questions, and the
      review-call booking ask (booked through Skill 44 calendars under Skill
      38's smart-booking protocol). The EMAIL half of post-delivery follow-up
      is FIX-PLAN Item 33c's election (Skill 50, draft-only through Skill 44
      after human approval) and is NOT built here; no email is sent from
      this module.
  (c) THE INTAKE FRONT DOOR. A greeting/qualification conversation that ends
      in a hand-off token into Skill 51's gated intake. The layer holds NO
      intake state of its own beyond the hand-off.

THE SCOPE BOUND (hard). Skill 51's gated intake itself is OUT of scope: this
layer never asks the intake questions, never writes intake answers, never
writes state.json, and never writes any engine artifact except through the
sanctioned writers named below. It hands off at the gate.

THE CONTRACT (B13 re-survey, Candidate 2; FIX-PLAN Item 33b)
-------------------------------------------------------------------------------------
  * The department supplies state; Skill 38 owns the conversation. At a seam
    event this module writes conversation-brief.json in the run folder
    (immutable per-event copies under working/conversation/briefs/): run id,
    GHL contact id, seam name (park-notice / delivery-followup /
    intake-frontdoor), the approved copy points for this run, the escalation
    target, and the consent posture already captured.
  * Skill 38 returns conversation-receipt.json records (playbook id,
    workflow id if any, memory log pointer, messages sent count, client
    outcome: booked / replied / opted out / escalated), appended through
    this module's one receipt writer so the shape has a single definition.
  * EVERY client-facing message the layer sends is recorded in the run
    record (FIX-PLAN Item 33b HOW). A message with no receipt record did
    not happen, by definition of this layer.
  * FALLBACK if Skill 38 is absent: today's one-way gateway notify,
    unchanged (report.dispatch), and the run record states the
    conversational layer was not available.

THE PARK SEAM (Item 10 is the input; this module never re-derives it)
-------------------------------------------------------------------------------------
The park classes, the plain-words labels, and the "needed" lines are Item
10's, defined in ONE place: presentation_job.auto_resume.classify_park /
park_status_record (PR #2030). This module CONSUMES state["park_status"]
(the record auto_resume stamps through the launcher's locked merge) and,
on a tree where the classifier exists but no record was stamped yet,
delegates to park_status_record(state) to build the same record in memory.
It never classifies a park itself, never reads the raw blocked reason into
client copy, and never writes park_status. On a tree with neither the
record nor the classifier (this base, ea22ed88, where Item 10 has not
landed), the park seam reports itself UNAVAILABLE with the reason stated;
it does not guess a class from the reason text.

THE REPLY HAND-OFF (specified precisely; the brief's core ask)
-------------------------------------------------------------------------------------
A client reply reaches this module as (message_id, kind, value) from the
conversation side. The module VERIFIES the kind against the run's own
artifacts before anything is written; a kind the artifacts do not support
is refused, recorded, and produces NO signal. Qualified replies route by
kind, each through the ONE sanctioned writer for that need:

  * kind "style_pick" (parked at P-STYLE-PICK, no choice file yet):
    the writer is deck-intake-driver.py --style-pick <value>
    --owner-msg-id <message_id>, the ONLY sanctioned client-side writer
    of working/copy/style_preview_choice.json. It refuses without a
    resolvable owner message id (AF-FORGED-APPROVAL discipline) and
    resolves A/B/C, "variant B", and 1/2/3 against the offered variants.
    RESUME SIGNAL: exactly one dispatch of the existing resume machinery,
    python3 -m presentation_job.launcher --resume --run-dir <dir> (the
    argv the board's resume button and the poller both use). No automatic
    path resumes an owner-decision park (auto_resume BOUND 1 / Item 10
    BOUND 2b refuse it by design), so the dispatch is the signal; the
    launcher itself refuses when an engine is already running.
  * kind "resource_plan" (a resource-plan answer is owed per
    resource_profile.pending_questions): the writer is
    capacity.record_plan_answer (the --answer-plan writer), which locks
    the tier onto the resource profile ask-once; the decline literal goes
    to resource_profile.record_conservative_default. A tier the cap table
    does not know is refused fail-closed BEFORE anything is written (the
    intake driver's own posture in _record_plan_tier).
    RESUME SIGNAL: the recorded answer itself. auto_resume's PRES-019 QC4
    known-plan fall-through reads the locked entry on the next poller
    tick and resumes under the ordinary cap/backoff bounds. This module
    deliberately does NOT also dispatch the launcher: two dispatchers
    would be two signals for one reply.
  * any other kind (a generic owner decision, missing intake, anything
    without a sanctioned writer in this tree): NOT qualified. The reply
    is preserved in the reply ledger, a receipt record marks the outcome
    "escalated" for the operator, and NO resume signal is produced. The
    waiver writer that would qualify owner-decision replies is Item
    12's line (PR #2022), unmerged at this base; routing around it with
    a hand-written artifact is exactly what this layer refuses to do.

EXACTLY ONE SIGNAL. Replies are deduplicated by message_id in the
adapter's own ledger (working/conversation/replies.json): a message id
with a recorded outcome returns that outcome and performs no writer
call, no dispatch, and no second record. The ask-once lock in the
resource profile and the choice file's existence check are the second
and third bolts on the same door.

WIRING NOTE
-------------------------------------------------------------------------------------
This module is invocable exactly the way the department's other seam
modules are (page_brief.py is the precedent): the run's agent calls the
CLI at the seam events, and Skill 38 reads the brief / returns receipts
through the same CLI. Always-on engine wiring (a manifest phase that
emits the brief) is sequenced with the manifest lockstep ceremony, the
same named remainder as Item 20's phase registration; nothing here
pretends otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

BRIEF_FORMAT = "conversation-brief"
BRIEF_VERSION = "1.0"
RECEIPT_FORMAT = "conversation-receipt"
RECEIPT_VERSION = "1.0"
HANDOFF_FORMAT = "pres-intake-handoff"
HANDOFF_VERSION = "1.0"
HANDOFF_SCOPE = "skill51-gated-intake"

SEAM_PARK = "park-notice"
SEAM_DELIVERY = "delivery-followup"
SEAM_FRONTDOOR = "intake-frontdoor"
SEAMS = (SEAM_PARK, SEAM_DELIVERY, SEAM_FRONTDOOR)

PARK_CLIENT_ACTION = "client_action"
PARK_OPERATOR_ACTION = "operator_action"
PARK_TRANSIENT_INFRA = "transient_infra"

#: The decline literal for the resource-plan question. Single-sourced in
#: the code that records it: resource_profile.record_conservative_default
#: writes locked_choice "use conservative default", and the intake bank's
#: conservative_value carries the same words to the client. The doctrine /
#: code agreement test in the Item 33b suite asserts this literal still
#: matches resource_profile's source, so the copy cannot drift silently.
DECLINE_LITERAL = "use conservative default"

#: Escalation target named in every brief: the operator surface that
#: already receives park and cap alerts (report.dispatch resolves the
#: "auto-resume" subsystem label to OWNER_CHAT_ID).
ESCALATION_TARGET = "operator (report subsystem label 'auto-resume')"

_TEMPLATES_PATH = _SCRIPTS_DIR / "conversation_templates.json"

#: Keys a hand-off token may carry, and nothing else. The token proves a
#: qualified hand-off happened; it is not an answer record, so the set is
#: closed and the validator refuses anything outside it.
HANDOFF_KEYS = {
    "format", "version", "token_id", "issued_at", "expires_at", "scope",
    "run_id", "session_ref", "ghl_contact_id", "intake_link",
    "qualification", "by",
}
QUALIFICATION_KEYS = {
    "intent_confirmed", "identity_confirmed", "channel",
    "consent_posture", "qualified_at",
}
#: Substrings that mark a key as intake-answer-shaped. A hand-off token
#: carrying any of these is refused: answers live behind Skill 51's gate,
#: never in this layer's records.
ANSWER_SHAPED_KEY_FRAGMENTS = (
    "answer", "intake_record", "sp_intake", "deck_brief", "question",
    "transcript", "ledger",
)

RECEIPT_OUTCOMES = ("booked", "replied", "opted out", "escalated")


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    try:
        from presentation_job.state import utcnow
        return utcnow()
    except Exception:  # noqa: BLE001 -- a stamp must never kill a seam event
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, path)


def _read_state(run_dir: Path) -> Optional[Dict[str, Any]]:
    doc = _read_json(run_dir / "state.json")
    return doc if isinstance(doc, dict) else None


def _run_id(run_dir: Path, state: Optional[Dict[str, Any]]) -> str:
    if state and isinstance(state.get("job_id"), str) and state["job_id"]:
        return state["job_id"]
    return run_dir.name


def load_templates() -> Dict[str, Any]:
    doc = _read_json(_TEMPLATES_PATH)
    if not isinstance(doc, dict):
        raise RuntimeError(f"conversation templates unreadable at {_TEMPLATES_PATH}")
    return doc


def render(template: str, **fields: Any) -> str:
    """Render one department template. A missing field is a refusal, never
    a half-rendered client message."""
    try:
        return template.format(**fields)
    except (KeyError, IndexError) as exc:
        raise ValueError(f"template field missing: {exc}") from exc


#: Client copy must never carry the machinery's vocabulary. The Item 33b
#: suite asserts every rendered client message against this list.
FORBIDDEN_CLIENT_TOKENS = (
    "park_class", "client_action", "operator_action", "transient_infra",
    "AF-", "auto_resume", "state.json", "park_status",
)


def assert_client_safe(text: str) -> None:
    for token in FORBIDDEN_CLIENT_TOKENS:
        if token in text:
            raise ValueError(f"client copy carries forbidden token {token!r}")
    import re
    if re.search(r"\bP-[A-Z][A-Z0-9.\-]*\b", text):
        raise ValueError("client copy carries a phase id")


# ---------------------------------------------------------------------------
# Contact + requester resolution (reads only; the definitions live elsewhere)
# ---------------------------------------------------------------------------

def resolve_ghl_contact_id(run_dir: Path,
                           state: Optional[Dict[str, Any]]) -> Tuple[Optional[str], str]:
    """(contact id, how it was resolved). Order: the run record's own
    requester block, then a top-level state field, then the intake record.
    An unresolved contact is a stated fact, never an invented id."""
    if state:
        req = state.get("requester")
        if isinstance(req, dict):
            for key in ("ghl_contact_id", "contact_id"):
                if req.get(key):
                    return str(req[key]), f"state.requester.{key}"
        if state.get("ghl_contact_id"):
            return str(state["ghl_contact_id"]), "state.ghl_contact_id"
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    if isinstance(intake, dict):
        for key in ("ghl_contact_id", "contact_id"):
            if intake.get(key):
                return str(intake[key]), f"working/copy/intake.json:{key}"
    return None, "unresolved: no GHL contact id on the run record or intake record"


def requester_chat_id(run_dir: Path,
                      state: Optional[Dict[str, Any]]) -> Optional[str]:
    """The requester's chat id as the run itself records it. This is the
    same two-step read auto_resume._requester_chat_id performs (Item 10):
    state["requester"]["chat_id"], else the intake ledger's
    requester_chat_id."""
    if state:
        req = state.get("requester")
        if isinstance(req, dict) and req.get("chat_id"):
            return str(req["chat_id"])
    ledger = _read_json(run_dir / "working" / "interview" / "intake_ledger.json")
    if isinstance(ledger, dict) and ledger.get("requester_chat_id"):
        return str(ledger["requester_chat_id"])
    return None


# ---------------------------------------------------------------------------
# The receipt ledger: the run record's conversation half (one writer)
# ---------------------------------------------------------------------------

def _receipt_path(run_dir: Path) -> Path:
    return run_dir / "conversation-receipt.json"


def read_receipts(run_dir: Path) -> Dict[str, Any]:
    doc = _read_json(_receipt_path(run_dir))
    if isinstance(doc, dict) and isinstance(doc.get("records"), list):
        return doc
    return {"format": RECEIPT_FORMAT, "version": RECEIPT_VERSION, "records": []}


def validate_receipt_record(record: Dict[str, Any]) -> List[str]:
    problems = []
    for key in ("at", "seam", "kind"):
        if not record.get(key):
            problems.append(f"receipt record missing {key!r}")
    if record.get("seam") not in SEAMS:
        problems.append(f"receipt record seam {record.get('seam')!r} is not one of {SEAMS}")
    outcome = record.get("outcome")
    if outcome is not None and outcome not in RECEIPT_OUTCOMES + (
            "brief_issued", "reply_routed", "resume_dispatched",
            "fallback_notify", "layer_unavailable", "client_silent",
            "refused",
            "not_qualified", "writer_refused", "duplicate", "not_parked",
            "kind_mismatch", "already_recorded", "not_owed", "handoff"):
        problems.append(f"receipt record outcome {outcome!r} is not in the vocabulary")
    return problems


def append_receipt(run_dir: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    """Append ONE record to conversation-receipt.json. This is the only
    writer of that file: the layer's own seam events and Skill 38's return
    records (through the record-receipt CLI) both land here, validated,
    so 'recorded in the run record' has exactly one meaning."""
    record = dict(record)
    record.setdefault("at", _utcnow())
    record.setdefault("by", "presentations.conversation_layer")
    problems = validate_receipt_record(record)
    if problems:
        raise ValueError("refusing an invalid receipt record: " + "; ".join(problems))
    doc = read_receipts(run_dir)
    doc["records"].append(record)
    _atomic_write_json(_receipt_path(run_dir), doc)
    return record


# ---------------------------------------------------------------------------
# Briefs (the outbound contract; B13's shape, validated at write time)
# ---------------------------------------------------------------------------

def validate_brief(brief: Dict[str, Any]) -> List[str]:
    problems = []
    if brief.get("format") != BRIEF_FORMAT:
        problems.append("brief format is not conversation-brief")
    for key in ("run_id", "seam", "issued_at", "escalation_target",
                "consent_posture", "copy_points"):
        if not brief.get(key):
            problems.append(f"brief missing {key!r}")
    if brief.get("seam") not in SEAMS:
        problems.append(f"brief seam {brief.get('seam')!r} is not one of {SEAMS}")
    if not isinstance(brief.get("copy_points"), dict) or not brief["copy_points"]:
        problems.append("brief copy_points must be a non-empty object")
    return problems


def write_brief(run_dir: Path, brief: Dict[str, Any]) -> Path:
    """Validate, then write the brief: an immutable per-event copy under
    working/conversation/briefs/ and the run-root conversation-brief.json
    refreshed to the newest brief (the surface B13 names)."""
    problems = validate_brief(brief)
    if problems:
        raise ValueError("refusing an incomplete brief: " + "; ".join(problems))
    briefs_dir = run_dir / "working" / "conversation" / "briefs"
    briefs_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(briefs_dir.glob(f"brief-{brief['seam']}-v*.json"))
    version = len(existing) + 1
    brief = dict(brief)
    brief["brief_version"] = version
    target = briefs_dir / f"brief-{brief['seam']}-v{version}.json"
    if target.exists():
        raise ValueError(f"brief {target} already exists; briefs are immutable")
    _atomic_write_json(target, brief)
    _atomic_write_json(run_dir / "conversation-brief.json", brief)
    return target


def _base_brief(run_dir: Path, state: Optional[Dict[str, Any]], seam: str,
                consent_posture: str) -> Dict[str, Any]:
    contact_id, how = resolve_ghl_contact_id(run_dir, state)
    return {
        "format": BRIEF_FORMAT,
        "version": BRIEF_VERSION,
        "run_id": _run_id(run_dir, state),
        "run_dir": str(run_dir),
        "ghl_contact_id": contact_id,
        "contact_resolution": how,
        "seam": seam,
        "issued_at": _utcnow(),
        "escalation_target": ESCALATION_TARGET,
        "consent_posture": consent_posture,
        "by": "presentations.conversation_layer",
    }


# ---------------------------------------------------------------------------
# Seam (a): park / resume communication
# ---------------------------------------------------------------------------

def load_park_view(run_dir: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """The client-safe park record for this run, or (None, why not).

    Consumes state["park_status"] verbatim when Item 10's writer stamped
    it; otherwise delegates to auto_resume.park_status_record (the same
    one definition) when this tree carries it. Never classifies here."""
    state = _read_state(run_dir)
    if state is None:
        return None, "state.json unreadable"
    record = state.get("park_status")
    if isinstance(record, dict) and record.get("park_class"):
        return record, 'state["park_status"] (Item 10 record, consumed verbatim)'
    try:
        from presentation_job import auto_resume as _ar
    except Exception:  # noqa: BLE001 -- absence is a stated outcome
        return None, ("no park_status record in state.json and "
                      "presentation_job.auto_resume is not importable")
    builder = getattr(_ar, "park_status_record", None)
    if builder is None:
        return None, ("no park_status record in state.json and this tree's "
                      "auto_resume carries no park classifier (Item 10 has "
                      "not landed here); the layer does not guess a class")
    return builder(state), "delegated to auto_resume.park_status_record (Item 10)"


def _need_kind(state: Optional[Dict[str, Any]], park: Dict[str, Any]) -> str:
    """Which client need a client_action park carries, from ARTIFACTS only
    (never from parsing copy): the style-pick phase names itself on the
    park record; a resource-plan park carries the configuration_pending
    stamp auto_resume writes for exactly that shape. Anything else uses
    the generic template, whose {needed} line already says the specifics
    in plain words."""
    if str(park.get("phase") or "") == "P-STYLE-PICK":
        return "style_pick"
    if isinstance(state, dict) and isinstance(state.get("configuration_pending"), dict):
        return "resource_plan"
    return ""


def park_client_surface(park: Dict[str, Any], need_kind: str = "",
                        templates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The client surface for one park, from the park record ONLY.

    client_action -> a client message (plain words: the record's own
    label and needed line inside the department's template).
    operator_action / transient_infra -> NO client message: the client is
    never told a wait is theirs when it is not. The returned surface
    states the silence and its reason for the run record."""
    templates = templates or load_templates()
    park_copy = templates["park_notice"]
    park_class = park.get("park_class")
    if park_class == PARK_CLIENT_ACTION:
        needed = str(park.get("needed") or "")
        by_need = park_copy.get("by_need") or {}
        template = by_need.get(need_kind) or park_copy["client_action"]
        message = render(template, needed=needed)
        assert_client_safe(message)
        return {"audience": "client", "client_message": message,
                "label": park.get("label"), "needed": needed,
                "waiting_on": park.get("waiting_on")}
    if park_class in (PARK_OPERATOR_ACTION, PARK_TRANSIENT_INFRA):
        return {"audience": "none", "client_message": None,
                "label": park.get("label"), "needed": park.get("needed"),
                "waiting_on": park.get("waiting_on"),
                "silence_reason": park_copy["silent_classes"][park_class]}
    return {"audience": "none", "client_message": None,
            "silence_reason": f"unknown park class {park_class!r}; the layer "
                              "stays silent rather than guess"}


def park_notice(run_dir: Path, *, layer_available: bool,
                templates: Optional[Dict[str, Any]] = None,
                dispatch_fn=None) -> Dict[str, Any]:
    """The park seam event. Returns a result dict and records everything
    in the run record:

    * park record unavailable -> receipt outcome layer_unavailable, no
      brief, no message (the seam's honest state on a pre-Item-10 tree).
    * non-client classes -> receipt outcome client_silent, no brief, no
      client message.
    * client_action + layer available -> the park-notice brief is
      written; Skill 38 owns the conversation from there; this module
      sends nothing itself.
    * client_action + layer unavailable -> the FALLBACK: today's one-way
      gateway notify (report.dispatch) carrying the same words the
      template renders, recorded with its delivery outcome. This is the
      one path where this module sends, because the fallback IS the
      pre-layer behavior, unchanged."""
    templates = templates or load_templates()
    state = _read_state(run_dir)
    park, source = load_park_view(run_dir)
    if park is None:
        record = append_receipt(run_dir, {
            "seam": SEAM_PARK, "kind": "park_surface",
            "outcome": "layer_unavailable",
            "detail": source})
        return {"status": "layer_unavailable", "detail": source,
                "receipt": record}
    surface = park_client_surface(park, _need_kind(state, park), templates)
    if surface["audience"] != "client":
        record = append_receipt(run_dir, {
            "seam": SEAM_PARK, "kind": "park_surface",
            "outcome": "client_silent",
            "park_class": park.get("park_class"),
            "detail": surface["silence_reason"],
            "park_source": source})
        return {"status": "client_silent", "park_class": park.get("park_class"),
                "receipt": record}
    consent = "captured at intake (run record)" if state else "unknown"
    brief = _base_brief(run_dir, state, SEAM_PARK, consent)
    brief["copy_points"] = {
        "what_parked": surface["label"],
        "what_is_needed": surface["needed"],
        "waiting_on": surface["waiting_on"],
        "client_message": surface["client_message"],
        "park_class": park.get("park_class"),
        "since": park.get("since"),
    }
    brief_path = write_brief(run_dir, brief)
    if layer_available:
        record = append_receipt(run_dir, {
            "seam": SEAM_PARK, "kind": "brief", "outcome": "brief_issued",
            "brief_ref": str(brief_path.relative_to(run_dir)),
            "park_class": park.get("park_class"), "park_source": source})
        return {"status": "brief_issued", "brief": str(brief_path),
                "client_message": surface["client_message"], "receipt": record}
    # Fallback: the one-way gateway notify, unchanged, and the run record
    # states the conversational layer was not available (B13 fallback).
    chat_id = requester_chat_id(run_dir, state)
    sent = False
    if chat_id is not None:
        if dispatch_fn is None:
            from presentation_job.report import dispatch as dispatch_fn  # noqa
        try:
            sent = bool(dispatch_fn(chat_id, "blocked", surface["client_message"]))
        except Exception:  # noqa: BLE001 -- a transport failure is recorded
            sent = False
    record = append_receipt(run_dir, {
        "seam": SEAM_PARK, "kind": "fallback", "outcome": "fallback_notify",
        "brief_ref": str(brief_path.relative_to(run_dir)),
        "detail": ("the conversational layer was not available; today's "
                   "one-way gateway notify carried the park message"),
        "delivered": sent,
        "addressed": bool(chat_id)})
    return {"status": "fallback_notify", "delivered": sent,
            "brief": str(brief_path), "receipt": record}


# ---------------------------------------------------------------------------
# Seam (b): post-delivery follow-up (conversational half only)
# ---------------------------------------------------------------------------

def delivery_facts(run_dir: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """The verified delivery record for this run, or (None, why not).

    The follow-up may only ever speak about a delivery the Delivery
    Concierge's own records verify (delivery-concierge SOP 9.4):
    media_library.json carries delivery_complete true, a verified_at
    stamp, and every destination verified. Anything less is not a
    delivered deck, and this seam refuses to thank a client for a
    delivery that has not been proven (the Wiring Gate posture)."""
    media = _read_json(run_dir / "working" / "checkpoints" / "media_library.json")
    if not isinstance(media, dict):
        return None, "no media_library.json delivery record for this run"
    if media.get("delivery_complete") is not True:
        return None, "the delivery record does not carry delivery_complete: true"
    destinations = media.get("delivery_destinations")
    if not isinstance(destinations, list) or not destinations:
        return None, "the delivery record names no destinations"
    unverified = [d for d in destinations
                  if not (isinstance(d, dict)
                          and (d.get("verified") is True
                               or d.get("status") == "verified"))]
    if unverified:
        return None, ("the delivery record carries destinations that are "
                      "not verified; follow-up never precedes verification")
    qc = _read_json(run_dir / "working" / "qc" / "final_deck_qc.json")
    score = qc.get("qc_score") if isinstance(qc, dict) else None
    if score is None:
        return None, ("no final QC score on record (working/qc/"
                      "final_deck_qc.json); the delivery notification and "
                      "this follow-up both carry the score, so neither is "
                      "composed without it")
    facts = {
        "delivery_verified_at": media.get("delivery_verified_at"),
        "delivery_notification_sent_at": media.get("delivery_notification_sent_at"),
        "destinations": destinations,
        "qc_score": score,
    }
    return facts, "working/checkpoints/media_library.json (SOP 9.4 verified)"


def _destination_lines(destinations: List[Dict[str, Any]]) -> str:
    lines = []
    for dest in destinations:
        kind = str(dest.get("type") or "file")
        where = dest.get("path") or dest.get("remote_name") or dest.get("drive_file_id") or ""
        lines.append(f"{kind}: {where}".strip())
    return "; ".join(lines)


def delivery_followup_brief(run_dir: Path, *,
                            templates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The delivery-followup seam event: a brief carrying the bounded
    conversational sequence (thank-you, package questions, review-call
    booking ask) rendered from the VERIFIED delivery record. The email
    half is Item 33c's election and is named in the brief as out of
    seam, so no reader can mistake this for it."""
    templates = templates or load_templates()
    state = _read_state(run_dir)
    facts, source = delivery_facts(run_dir)
    if facts is None:
        record = append_receipt(run_dir, {
            "seam": SEAM_DELIVERY, "kind": "delivery_surface",
            "outcome": "refused", "detail": source})
        return {"status": "refused", "detail": source, "receipt": record}
    follow = templates["delivery_followup"]
    destinations_text = _destination_lines(facts["destinations"])
    touches = []
    for touch in follow["touches"]:
        text = render(touch["template"], qc_score=facts["qc_score"],
                      destinations=destinations_text)
        assert_client_safe(text)
        touches.append({"id": touch["id"], "when": touch["when"], "text": text})
    brief = _base_brief(run_dir, state, SEAM_DELIVERY,
                        "captured at intake (run record)")
    brief["copy_points"] = {
        "delivered": True,
        "delivery_source": source,
        "delivery_verified_at": facts["delivery_verified_at"],
        "qc_score": facts["qc_score"],
        "destinations": facts["destinations"],
        "sequence": touches,
        "review_call_booking": follow["booking"],
        "boundary": follow["boundary"],
    }
    brief_path = write_brief(run_dir, brief)
    record = append_receipt(run_dir, {
        "seam": SEAM_DELIVERY, "kind": "brief", "outcome": "brief_issued",
        "brief_ref": str(brief_path.relative_to(run_dir))})
    return {"status": "brief_issued", "brief": str(brief_path), "receipt": record}


# ---------------------------------------------------------------------------
# Seam (c): the intake front door (greeting / qualification / hand-off)
# ---------------------------------------------------------------------------

def validate_handoff(token: Dict[str, Any]) -> List[str]:
    """The hand-off token's closed shape. It proves a qualified hand-off
    into Skill 51's gated intake happened; it carries NO intake answers,
    and any key outside the closed set (or any answer-shaped key) is a
    refusal, because answers live behind the gate, never in this layer."""
    problems = []
    extra = set(token) - HANDOFF_KEYS
    if extra:
        problems.append(f"hand-off token carries keys outside the closed set: {sorted(extra)}")
    for key in token:
        low = str(key).lower()
        if any(fragment in low for fragment in ANSWER_SHAPED_KEY_FRAGMENTS):
            problems.append(f"hand-off token carries an answer-shaped key: {key!r}")
    for key in ("format", "token_id", "issued_at", "scope", "intake_link",
                "qualification"):
        if not token.get(key):
            problems.append(f"hand-off token missing {key!r}")
    if token.get("format") != HANDOFF_FORMAT:
        problems.append("hand-off token format is not pres-intake-handoff")
    if token.get("scope") != HANDOFF_SCOPE:
        problems.append(f"hand-off token scope is not {HANDOFF_SCOPE}")
    qual = token.get("qualification")
    if isinstance(qual, dict):
        qextra = set(qual) - QUALIFICATION_KEYS
        if qextra:
            problems.append(f"qualification carries keys outside its closed set: {sorted(qextra)}")
        if qual.get("intent_confirmed") is not True:
            problems.append("qualification intent_confirmed is not true")
        if qual.get("identity_confirmed") is not True:
            problems.append("qualification identity_confirmed is not true")
    else:
        problems.append("hand-off token qualification is not an object")
    return problems


def frontdoor_handoff(run_dir: Path, *, ghl_contact_id: Optional[str],
                      intake_link: str, channel: str,
                      consent_posture: str,
                      session_ref: str = "",
                      expires_at: str = "",
                      templates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The front door's one output: a hand-off token into Skill 51's
    gated intake, plus the intake-frontdoor brief. The intake link is
    the department's own bridge-minted capability link (/s/<token>),
    carried verbatim; this layer mints nothing and stores no answers.
    The layer holds no intake state beyond this token: nothing under
    working/interview/ is created or touched here."""
    templates = templates or load_templates()
    state = _read_state(run_dir)
    now = _utcnow()
    token = {
        "format": HANDOFF_FORMAT,
        "version": HANDOFF_VERSION,
        "token_id": uuid.uuid4().hex,
        "issued_at": now,
        "expires_at": expires_at,
        "scope": HANDOFF_SCOPE,
        "run_id": _run_id(run_dir, state),
        "session_ref": session_ref,
        "ghl_contact_id": ghl_contact_id,
        "intake_link": intake_link,
        "qualification": {
            "intent_confirmed": True,
            "identity_confirmed": True,
            "channel": channel,
            "consent_posture": consent_posture,
            "qualified_at": now,
        },
        "by": "presentations.conversation_layer",
    }
    problems = validate_handoff(token)
    if problems:
        raise ValueError("refusing an invalid hand-off token: " + "; ".join(problems))
    target = run_dir / "working" / "conversation" / "intake-handoff.json"
    _atomic_write_json(target, token)
    door = templates["frontdoor"]
    brief = _base_brief(run_dir, state, SEAM_FRONTDOOR, consent_posture)
    brief["copy_points"] = {
        "greeting": door["greeting"],
        "qualification_prompts": door["qualification"],
        "handoff_message": render(door["handoff"], intake_link=intake_link),
        "handoff_token_ref": str(target.relative_to(run_dir)),
        "scope": HANDOFF_SCOPE,
        "note": ("The layer's involvement ends at this hand-off. The "
                 "gated intake (Skill 51) owns every question from here; "
                 "this token carries no answers."),
    }
    brief_path = write_brief(run_dir, brief)
    record = append_receipt(run_dir, {
        "seam": SEAM_FRONTDOOR, "kind": "handoff", "outcome": "handoff",
        "brief_ref": str(brief_path.relative_to(run_dir)),
        "handoff_token_ref": str(target.relative_to(run_dir))})
    return {"status": "handoff_issued", "token": token,
            "brief": str(brief_path), "receipt": record}


# ---------------------------------------------------------------------------
# The reply adapter: a qualified client reply -> exactly one resume signal
# ---------------------------------------------------------------------------

def _reply_ledger_path(run_dir: Path) -> Path:
    return run_dir / "working" / "conversation" / "replies.json"


def _read_reply_ledger(run_dir: Path) -> Dict[str, Any]:
    doc = _read_json(_reply_ledger_path(run_dir))
    if isinstance(doc, dict) and isinstance(doc.get("records"), list):
        return doc
    return {"format": "conversation-replies", "version": "1.0", "records": []}


def _record_reply(run_dir: Path, record: Dict[str, Any]) -> Dict[str, Any]:
    doc = _read_reply_ledger(run_dir)
    doc["records"].append(record)
    _atomic_write_json(_reply_ledger_path(run_dir), doc)
    return record


def _default_resume_dispatch(run_dir: Path) -> Dict[str, Any]:
    """ONE dispatch of the existing resume machinery: the exact argv the
    board's resume button uses (Item 19) and the poller's launcher line
    wraps. The launcher refuses on its own when an engine is already
    running, so a dispatch can never start a second engine."""
    argv = [sys.executable, "-m", "presentation_job.launcher",
            "--resume", "--run-dir", str(run_dir)]
    proc = subprocess.run(argv, cwd=str(_SCRIPTS_DIR), capture_output=True,
                          text=True, timeout=120)
    return {"argv": argv, "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-400:],
            "stderr_tail": (proc.stderr or "")[-400:]}


def _route_style_pick(run_dir: Path, state: Dict[str, Any], value: str,
                      message_id: str, resume_dispatch) -> Dict[str, Any]:
    blocked = state.get("blocked") if isinstance(state.get("blocked"), dict) else {}
    if str(blocked.get("phase") or "") != "P-STYLE-PICK":
        return {"outcome": "kind_mismatch",
                "detail": "the run is not parked at the style-pick gate; a "
                          "style pick answers nothing that is outstanding"}
    choice_path = run_dir / "working" / "copy" / "style_preview_choice.json"
    if choice_path.is_file():
        return {"outcome": "already_recorded",
                "detail": "a style choice is already on record for this run; "
                          "the engine re-verifies it at the gate on resume. "
                          "No second write, no second signal."}
    driver = _SCRIPTS_DIR / "deck-intake-driver.py"
    argv = [sys.executable, str(driver), "--run-dir", str(run_dir),
            "--style-pick", value, "--owner-msg-id", message_id]
    proc = subprocess.run(argv, cwd=str(_SCRIPTS_DIR), capture_output=True,
                          text=True, timeout=120)
    if proc.returncode != 0:
        return {"outcome": "writer_refused",
                "detail": ("the sanctioned style-pick writer refused the "
                           f"reply (exit {proc.returncode}): "
                           f"{(proc.stdout or proc.stderr or '')[:300]}")}
    dispatch = resume_dispatch(run_dir)
    return {"outcome": "reply_routed",
            "writer": "deck-intake-driver.py --style-pick (sanctioned writer)",
            "resume_signal": {"type": "launcher_resume_dispatch",
                              "dispatch": dispatch},
            "detail": "the pick is recorded with the client's own message "
                      "id; exactly one resume dispatch follows it"}


def _route_resource_plan(run_dir: Path, value: str,
                         config_dir: Optional[Path]) -> Dict[str, Any]:
    from presentation_job import capacity as cap
    from presentation_job import resource_profile as rp
    pending = [q for q in rp.pending_questions(config_dir=config_dir)
               if q.get("id") == "resource_plan" and q.get("provider")]
    owed = list(dict.fromkeys(str(q["provider"]) for q in pending))
    if not owed:
        return {"outcome": "not_owed",
                "detail": "no resource-plan answer is outstanding (it was "
                          "never owed, or it is already recorded and locked "
                          "ask-once); nothing is written and the question "
                          "is not re-asked"}
    text = str(value or "").strip()
    if text.lower() == DECLINE_LITERAL:
        for provider in owed:
            rp.record_conservative_default(provider, config_dir)
        return {"outcome": "reply_routed",
                "writer": "resource_profile.record_conservative_default",
                "resume_signal": None,
                "answer_recorded": {"providers": owed,
                                    "choice": DECLINE_LITERAL},
                "detail": "the decline is locked ask-once, exactly as the "
                          "intake records it; it is never re-asked. No "
                          "resume follows a decline: the run stays parked "
                          "and auto_resume reports the known-plan decline "
                          "until the operator widens it the way the "
                          "KNOWN-PLAN decision names"}
    matched: List[Tuple[str, str]] = []
    for provider in owed:
        plan = cap.normalize_plan(text, provider)
        if plan and plan in (cap.PLANS_BY_PROVIDER.get(provider) or ()):
            matched.append((provider, plan))
    if not matched:
        # Owner ruling 2026-10-15: a NO_CAP provider (deepseek-direct,
        # openrouter) never owes a plan answer, but a tier label the client
        # states for one it owns is recorded as metadata through the same
        # writer's BYOK branch -- the deck-intake-driver's matcher carries
        # the identical arm, so a DeepSeek tier named in a reply is
        # recorded, never refused whole.
        try:
            prof = rp.load_profile(config_dir)
            owned_nocap = [cap.normalize_provider(pid)
                           for pid in (prof.get("providers") or {})]
        except Exception:  # noqa: BLE001 -- metadata matching is best-effort
            owned_nocap = []
        for provider in owned_nocap:
            if provider and provider in cap.NO_CAP_PROVIDERS \
                    and provider not in owed:
                plan = cap.normalize_plan(text, provider)
                if plan:
                    matched.append((provider, plan))
    if not matched:
        offers = "; ".join(
            f"{p}: {', '.join(cap.PLANS_BY_PROVIDER.get(p) or ()) or '(none)'}"
            for p in owed)
        return {"outcome": "writer_refused",
                "detail": (f"refusing the plan answer {text!r}: it is not a "
                           f"plan any provider still owing an answer can be "
                           f"on. Accepted tiers: {offers}. Nothing was "
                           "written; the answer is refused here rather "
                           "than accepted and dropped.")}
    written = []
    for provider, plan in matched:
        cap.record_plan_answer(provider, plan, config_dir)
        written.append({"provider": provider, "plan": plan})
    return {"outcome": "reply_routed",
            "writer": "capacity.record_plan_answer (the --answer-plan writer)",
            "resume_signal": {"type": "plan_answer_recorded",
                              "providers": written,
                              "honored_by": "auto_resume's PRES-019 QC4 "
                                            "known-plan fall-through on the "
                                            "next poller tick, under the "
                                            "ordinary cap/backoff bounds; "
                                            "this adapter dispatches no "
                                            "second signal"},
            "detail": "the tier is locked onto the resource profile "
                      "ask-once; the run unblocks exactly once the answer "
                      "is recorded"}


def route_reply(run_dir: Path, *, message_id: str, kind: str, value: str,
                config_dir: Optional[Path] = None,
                resume_dispatch=None) -> Dict[str, Any]:
    """Route ONE client reply. The full hand-off contract is in this
    module's docstring. Guarantees:

    * dedupe by message_id: a recorded message id returns its recorded
      outcome and performs no writer call, no dispatch, no second record;
    * qualification is verified against the run's artifacts, never taken
      on the caller's word;
    * at most one resume signal per reply, of exactly one type."""
    run_dir = Path(run_dir).expanduser()
    message_id = str(message_id or "").strip()
    if not message_id:
        raise ValueError("a reply without a message id cannot be routed: "
                         "there is nothing to dedupe it by, and for a "
                         "style pick nothing for the approvals oracle to "
                         "resolve (AF-FORGED-APPROVAL discipline)")
    ledger = _read_reply_ledger(run_dir)
    for prior in ledger["records"]:
        if prior.get("message_id") == message_id:
            return {"status": "duplicate", "duplicate": True,
                    "recorded_outcome": prior.get("outcome"),
                    "record": prior}
    state = _read_state(run_dir)
    base = {"message_id": message_id, "kind": kind, "at": _utcnow(),
            "by": "presentations.conversation_layer"}
    if state is None or str(state.get("terminal") or "") != "BLOCKED":
        result = {"outcome": "not_parked",
                  "detail": "the run is not parked; a reply cannot resume "
                            "a run that is not waiting"}
    elif kind == "style_pick":
        result = _route_style_pick(
            run_dir, state, value, message_id,
            resume_dispatch or _default_resume_dispatch)
    elif kind == "resource_plan":
        result = _route_resource_plan(run_dir, value, config_dir)
    else:
        result = {"outcome": "escalated",
                  "detail": (f"no sanctioned writer exists in this tree "
                             f"for a reply of kind {kind!r}; the reply is "
                             "preserved here for the operator and NO resume "
                             "signal is produced. (Owner-decision replies "
                             "gain a writer with the waiver path, Item 12 "
                             "line; hand-writing the artifact here is the "
                             "forgery this layer exists to prevent.)"),
                  "reply_text": str(value)[:500]}
    record = _record_reply(run_dir, {**base, "resume_signal": None, **result})
    append_receipt(run_dir, {
        "seam": SEAM_PARK, "kind": "reply",
        "outcome": result["outcome"], "message_id": message_id,
        "reply_kind": kind,
        "resume_signal": (result.get("resume_signal") or {}).get("type")})
    return {"status": result["outcome"], "record": record}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="conversation_layer.py",
        description=("The presentations side of the Skill 38 conversational "
                     "layer (FIX-PLAN Item 33b): park-notice briefs and "
                     "fallback, delivery-followup briefs, the intake "
                     "front-door hand-off, and the qualified-reply adapter."))
    p.add_argument("--selftest", action="store_true",
                   help="run the offline self-test and exit")
    sub = p.add_subparsers(dest="command")

    pk = sub.add_parser("park-notice", help="the park seam event for one run")
    pk.add_argument("--run-dir", type=Path, required=True)
    avail = pk.add_mutually_exclusive_group(required=True)
    avail.add_argument("--layer-available", action="store_true",
                       help="Skill 38 will own the conversation (brief only)")
    avail.add_argument("--layer-unavailable", action="store_true",
                       help="fall back to today's one-way gateway notify")

    dl = sub.add_parser("delivery-brief", help="the delivery-followup brief")
    dl.add_argument("--run-dir", type=Path, required=True)

    fd = sub.add_parser("frontdoor", help="issue an intake front-door hand-off")
    fd.add_argument("--run-dir", type=Path, required=True)
    fd.add_argument("--contact-id", default=None)
    fd.add_argument("--intake-link", required=True,
                    help="the bridge-minted capability link (/s/<token>), "
                         "carried verbatim")
    fd.add_argument("--channel", default="ghl-conversation")
    fd.add_argument("--consent-posture", required=True,
                    help="the consent posture already captured for this client")
    fd.add_argument("--session-ref", default="")
    fd.add_argument("--expires-at", default="")

    rp = sub.add_parser("reply", help="route one qualified client reply")
    rp.add_argument("--run-dir", type=Path, required=True)
    rp.add_argument("--message-id", required=True)
    rp.add_argument("--kind", required=True,
                    help="style_pick | resource_plan | (anything else is "
                         "recorded and escalated, never routed)")
    rp.add_argument("--value", required=True,
                    help="the qualified reply value (the pick token, or the "
                         "plan answer text)")
    rp.add_argument("--config-dir", type=Path, default=None,
                    help="the department config dir holding the resource "
                         "profile (default: resource_profile's own "
                         "resolution)")

    rr = sub.add_parser("record-receipt",
                        help="append a Skill 38 return record (JSON on stdin "
                             "or via --json)")
    rr.add_argument("--run-dir", type=Path, required=True)
    rr.add_argument("--json", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return cmd_selftest()
    if not args.command:
        print(json.dumps({"error": "no command given; see --help"}))
        return 2
    try:
        if args.command == "park-notice":
            result = park_notice(args.run_dir.expanduser(),
                                 layer_available=bool(args.layer_available))
            print(json.dumps(result, indent=2, default=str))
            return 0 if result["status"] != "layer_unavailable" else 4
        if args.command == "delivery-brief":
            result = delivery_followup_brief(args.run_dir.expanduser())
            print(json.dumps(result, indent=2, default=str))
            return 0 if result["status"] == "brief_issued" else 3
        if args.command == "frontdoor":
            result = frontdoor_handoff(
                args.run_dir.expanduser(), ghl_contact_id=args.contact_id,
                intake_link=args.intake_link, channel=args.channel,
                consent_posture=args.consent_posture,
                session_ref=args.session_ref, expires_at=args.expires_at)
            print(json.dumps(result, indent=2, default=str))
            return 0
        if args.command == "reply":
            result = route_reply(args.run_dir.expanduser(),
                                 message_id=args.message_id, kind=args.kind,
                                 value=args.value, config_dir=args.config_dir)
            print(json.dumps(result, indent=2, default=str))
            return 0 if result["status"] in ("reply_routed", "duplicate") else 3
        if args.command == "record-receipt":
            raw = args.json if args.json else sys.stdin.read()
            record = json.loads(raw)
            saved = append_receipt(args.run_dir.expanduser(), record)
            print(json.dumps(saved, indent=2, default=str))
            return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 3
    return 2


def cmd_selftest() -> int:
    """Offline exercise of the three seams against scratch run dirs.
    Every check prints PASS/FAIL; exits 1 on any failure."""
    import tempfile

    failures: List[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"[selftest] {'PASS' if cond else 'FAIL'}: {name} {detail}")
        if not cond:
            failures.append(name)

    templates = load_templates()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # --- park surfaces per class -------------------------------------
        client_park = {"park_class": "client_action", "label": "Waiting for you",
                       "waiting_on": "client", "phase": "P-STYLE-PICK",
                       "needed": "We need your style pick: reply A, B or C "
                                 "for the style samples you were sent. The "
                                 "deck continues as soon as you pick.",
                       "auto_resume": False, "since": "2026-10-14T00:00:00+00:00"}
        surface = park_client_surface(client_park, "style_pick", templates)
        check("client_action park produces a client message",
              surface["audience"] == "client" and "reply A, B or C" in surface["client_message"])
        for cls in ("operator_action", "transient_infra"):
            s = park_client_surface({**client_park, "park_class": cls}, "", templates)
            check(f"{cls} park is silent to the client",
                  s["audience"] == "none" and s["client_message"] is None)

        # --- reply dedupe: a recorded id never routes twice ---------------
        run = root / "run-dedupe"
        run.mkdir()
        (run / "state.json").write_text(json.dumps(
            {"terminal": "BLOCKED",
             "blocked": {"phase": "P-STYLE-PICK", "reason": "x",
                         "at": "2026-10-14T00:00:00+00:00"}}))
        dispatches: List[Path] = []
        fake = lambda rd: dispatches.append(rd) or {"argv": ["fake"], "returncode": 0}  # noqa: E731
        # The driver subprocess is the real writer; without samples it
        # records the raw pick (its no-manifest posture). Provide variants.
        samples = run / "working" / "style-preview"
        samples.mkdir(parents=True)
        (samples / "style_samples_manifest.json").write_text(
            json.dumps({"variants": ["A", "B", "C"]}))
        r1 = route_reply(run, message_id="m-1", kind="style_pick", value="B",
                         resume_dispatch=fake)
        r2 = route_reply(run, message_id="m-1", kind="style_pick", value="B",
                         resume_dispatch=fake)
        check("qualified style pick routes", r1["status"] == "reply_routed",
              r1["status"])
        check("the same message id never signals twice",
              r2.get("duplicate") is True and len(dispatches) == 1)

        # --- front door: the token carries no answers ----------------------
        token_run = root / "run-door"
        token_run.mkdir()
        out = frontdoor_handoff(token_run, ghl_contact_id="c-1",
                                intake_link="/s/tok", channel="sms",
                                consent_posture="captured")
        check("hand-off token validates", validate_handoff(out["token"]) == [])
        bad = dict(out["token"]); bad["answers"] = {"q1": "x"}
        check("an answer-shaped key is refused",
              validate_handoff(bad) != [])
        check("the front door writes no intake state",
              not (token_run / "working" / "interview").exists()
              and not (token_run / "working" / "copy" / "intake.json").exists())

    if failures:
        print(f"[selftest] FAILED: {failures}", file=sys.stderr)
        return 1
    print("[selftest] ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
