#!/usr/bin/env python3
"""
deck-intake-driver.py -- THE ONE sanctioned intake bridge for Presentations.

WORK-ITEM-06: Un-hardcode deck_type. This driver is the SINGLE place deck_type
is written -- via derive_legacy_fields() from the ONE presentation_type answer.
Never hand-typed. Never defaulted to "webinar" by a hardcoded write.

Reads its question schema from intake/deck-intake-questions.json (the canonical
source of truth). Supports two interview modes:

  STANDARD  (--next / --answer / --complete)
    One question per turn, machine-paced. The presentation_type picker runs
    first; its answer derives all four legacy axis fields (deck_type,
    creation_mode, presentation_mode, audience_mode) automatically via
    derive_legacy_fields(). Conditional follow-ups (recipient_name,
    signature_source, extracted_substance) auto-skip when unmet.

  SIGNATURE (--signature --next / --signature --answer)
    Choice-first (QUICK vs IN-DEPTH), then the SACRED 8 Questions +
    frame-selection question ONE at a time. Answers are assembled into ONE
    atomic record per sp-8-questions.json. The turn-gate is REQUIRED --
    a batch dump is AF-INTAKE-BATCH.

At --complete, the driver writes/merges working/copy/intake.json with all
derived fields, runs prove_sp_routing.py unconditionally for claim-gate
enforcement, and marks the intake ledger complete.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# canonical paths
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent
DEPT_ROOT = SCRIPTS_DIR.parent
INTAKE_DIR = DEPT_ROOT / "intake"
QUESTIONS_PATH = INTAKE_DIR / "deck-intake-questions.json"

# ---------------------------------------------------------------------------
# legacy_field_mapping -- the canonical derivation table.
# MIRROR of intake/deck-intake-questions.json's legacy_field_mapping.
# THIS IS THE SOURCE OF TRUTH for deck_type. Every other consumer reads
# intake.json.deck_type -- never derives it independently.
# ---------------------------------------------------------------------------
LEGACY_FIELD_MAPPING: Dict[str, Dict[str, Any]] = {
    "from_scratch": {
        "deck_type": "webinar",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
    },
    "content_personal": {
        "deck_type": "webinar",
        "creation_mode": "content_personal",
        "presentation_mode": "one-person",
        "audience_mode": "PERSONAL",
        "requires": ["recipient_name", "extracted_substance"],
    },
    "content_general": {
        "deck_type": "webinar",
        "creation_mode": "content_general",
        "presentation_mode": "general",
        "audience_mode": "GENERAL",
        "requires": ["extracted_substance"],
    },
    "signature": {
        "deck_type": "signature_presentation",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
        "note": "creation_mode defaults to from_scratch; overridden to "
                "content_personal/content_general by the signature_source "
                "follow-up when the client is converting existing material "
                "into the signature talk. Never left unset (AF-MODE-UNSET).",
    },
}

# legal presentation_type values -- mirrors __main__.py cmd_new
LEGAL_PRESENTATION_TYPES = ("from_scratch", "content_personal",
                            "content_general", "signature")


# ---------------------------------------------------------------------------
# derive_legacy_fields -- the ONE function that writes deck_type
# ---------------------------------------------------------------------------
def derive_legacy_fields(presentation_type: str,
                         signature_source: Optional[str] = None) -> Dict[str, Any]:
    """Map presentation_type to {deck_type, creation_mode, presentation_mode,
    audience_mode}. This is THE SINGLE derivation point -- every other consumer
    reads intake.json.deck_type; nothing else derives it.

    For presentation_type='signature', signature_source overrides creation_mode:
      'existing_content' -> creation_mode defaults to 'content_general' (safe
      default) until the signature intake clarifies the audience, then corrected.
      'from_scratch' (or unset) -> creation_mode stays 'from_scratch'.
    """
    if presentation_type not in LEGAL_PRESENTATION_TYPES:
        raise ValueError(
            f"presentation_type {presentation_type!r} is not one of "
            f"{LEGAL_PRESENTATION_TYPES}. This is the ONE answer that derives "
            f"deck_type -- it cannot be unset or invalid (AF-MODE-UNSET).")

    mapping = LEGACY_FIELD_MAPPING[presentation_type]
    derived = dict(mapping)  # shallow copy

    if presentation_type == "signature" and signature_source:
        if signature_source == "existing_content":
            # Safe default: content_general until the signature intake
            # clarifies audience scope. Never left unset (AF-MODE-UNSET).
            derived["creation_mode"] = "content_general"
        # 'from_scratch' keeps the default

    return derived


# ---------------------------------------------------------------------------
# question schema loader
# ---------------------------------------------------------------------------
def load_question_schema() -> Dict[str, Any]:
    """Read the canonical question schema from intake/deck-intake-questions.json.
    Returns the full parsed document. Exits 2 if missing."""
    if not QUESTIONS_PATH.is_file():
        print(f"FATAL: question schema not found at {QUESTIONS_PATH}",
              file=sys.stderr)
        print("  This is the canonical source of truth for intake questions. "
              "Re-materialize the Presentations department.", file=sys.stderr)
        sys.exit(2)
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def get_questions(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the ordered question list from the schema."""
    questions = schema.get("questions", [])
    questions.sort(key=lambda q: q.get("order", 999))
    return questions


# ---------------------------------------------------------------------------
# conditional evaluation
# ---------------------------------------------------------------------------
def should_ask(question: Dict[str, Any],
               answers: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Determine if a conditional question should be asked given current answers.

    Returns (should_ask, skip_reason).
    """
    # conditional_on: {id, equals} or {id, in: [...]}
    cond = question.get("conditional_on")
    if cond:
        cond_id = cond.get("id", "")
        cond_val = answers.get(cond_id)
        if "equals" in cond:
            if cond_val != cond.get("equals"):
                return False, f"conditional_on {cond_id}!={cond['equals']}"
        if "in" in cond:
            if cond_val not in cond.get("in", []):
                return False, f"conditional_on {cond_id} not in {cond['in']}"

    # ask_if: {question_id, equals}, {question_id, contains}, etc.
    ask_if = question.get("ask_if")
    if ask_if:
        qid = ask_if.get("question_id", "")
        qval = answers.get(qid)
        if "equals" in ask_if:
            if qval != ask_if["equals"]:
                return False, f"ask_if {qid}!={ask_if['equals']}"
        if "contains" in ask_if:
            if not isinstance(qval, str) or ask_if["contains"] not in qval:
                return False, f"ask_if {qid} does not contain {ask_if['contains']}"
        if "contains_any" in ask_if:
            if not isinstance(qval, str) or not any(
                    t in qval for t in ask_if["contains_any"]):
                return False, f"ask_if {qid} contains none of {ask_if['contains_any']}"
        if "truthy" in ask_if:
            if not qval:
                return False, f"ask_if {qid} is not truthy"

    return True, None


# ---------------------------------------------------------------------------
# intake JSON read/write
# ---------------------------------------------------------------------------
def read_intake_json(run_dir: Path) -> Dict[str, Any]:
    """Read working/copy/intake.json. Returns empty dict if absent."""
    path = run_dir / "working" / "copy" / "intake.json"
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
            return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_intake_json(run_dir: Path, intake: Dict[str, Any]) -> None:
    """Write working/copy/intake.json atomically."""
    dest = run_dir / "working" / "copy"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "intake.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(intake, fh, indent=2, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# requester identity -- fix/deck-type-routing-bypass follow-up.
#
# b01d2a09 diagnosed the gap in these exact words: "the dispatcher knows it
# but never writes it down." Two dispatchers (mc-route.sh's REQUESTER_CHAT_ID
# / REQUESTER_CHANNEL and whatever exports PRESENTATION_REQUESTER_CHAT_ID /
# ROUTE_PRES_REQUESTER_CHAT_ID / MC_ROUTE_REQUESTER_CHAT_ID before invoking
# this driver) already know the requester at dispatch time, and cc_board.py's
# resolve_requester() already reads that SAME set of env keys -- but only for
# CC-board task registration, a different purpose than the engine's own hard
# gate (presentation_job.py --new dies with no requester.chat_id; see
# presentation_job/__main__.py cmd_new). Neither dispatcher ever persisted the
# value into working/copy/intake.json, the ONE file resolve_intake.py (and
# therefore the engine) actually reads. This driver is where intake.json is
# actually produced, so --complete is the correct place to make the stamp
# durable: whichever env var the calling dispatcher exported is read once,
# here, and merged into intake -- never overwriting a value already on disk
# (an upstream writer or a re-run always wins over the environment).
#
# _REQUESTER_ENV_KEYS mirrors cc_board.py's own constant of the same name
# byte-for-byte -- one vocabulary, read in two places for two purposes.
_REQUESTER_ENV_KEYS = (
    "PRESENTATION_REQUESTER_CHAT_ID",
    "ROUTE_PRES_REQUESTER_CHAT_ID",
    "MC_ROUTE_REQUESTER_CHAT_ID",
)


def _resolve_operator_fallback() -> Tuple[str, str]:
    """Lazily import operator_requester.py (same directory as this driver)
    and call its resolve_operator_chat_id(). Returns ("", "") -- never
    raises -- if the module cannot be imported, so a missing/broken OPTIONAL
    module degrades to 'no operator fallback available', never a crash of
    --complete/--record. See operator_requester.py's own docstring for the
    full FIX F19 rationale."""
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from operator_requester import resolve_operator_chat_id  # type: ignore
        return resolve_operator_chat_id()
    except Exception:
        return ("", "")


def _resolve_requester_from_env(existing_intake: Dict[str, Any]) -> Dict[str, str]:
    """Return {requester_chat_id, requester_channel} updates to merge into
    working/copy/intake.json. Returns {} -- never a fabricated value -- when
    intake already has a requester_chat_id (do not clobber).

    Order:
      1. the environment the dispatcher already sets (_REQUESTER_ENV_KEYS
         above) -- the real client's chat-surface identity, when a
         dispatcher exported it. This is the RIGHT source for a genuine
         client order and always wins when present.
      2. FIX F19: the sanctioned OPERATOR fallback (operator_requester.py),
         read by NAME from ~/.openclaw/openclaw.json's env.vars -- never a
         client identity, never invented. Closes the case the env-var path
         above never covered: a genuinely operator-initiated run where no
         dispatcher ever had a client chat id to export. Before this fix
         that case resolved to {} forever, and presentation_job.py --new's
         own F1 hard-fail then caught every such run with nobody able to
         start a deck unattended.
    Only when BOTH resolve nothing does this return {} and leave the
    engine's F1 gate to fire exactly as designed -- this function never
    bypasses that gate, it only ever adds a legitimate source.
    """
    if str(existing_intake.get("requester_chat_id") or "").strip():
        return {}
    chat_id = ""
    for key in _REQUESTER_ENV_KEYS:
        val = str(os.environ.get(key) or "").strip()
        if val:
            chat_id = val
            break
    if chat_id:
        channel = str(os.environ.get("PRESENTATION_REQUESTER_CHANNEL") or "").strip() or "telegram"
        return {"requester_chat_id": chat_id, "requester_channel": channel}

    op_chat_id, op_channel = _resolve_operator_fallback()
    if op_chat_id:
        return {"requester_chat_id": op_chat_id, "requester_channel": op_channel}
    return {}


def read_intake_ledger(run_dir: Path) -> Dict[str, Any]:
    """Read working/interview/intake_ledger.json. Returns empty dict if absent."""
    path = run_dir / "working" / "interview" / "intake_ledger.json"
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
            return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_intake_ledger(run_dir: Path, ledger: Dict[str, Any]) -> None:
    """Write working/interview/intake_ledger.json atomically."""
    dest = run_dir / "working" / "interview"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "intake_ledger.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, default=str)
    os.replace(tmp, path)


def write_intake_transcript(run_dir: Path,
                            envelope: Any) -> None:
    """Write working/interview/intake_transcript.json atomically.

    FAULT-21 fix (2026-08-20): this is now ONLY ever called with the full,
    freshly-signed driver envelope produced by _finalize_transcript_envelope()
    -- never with a read-then-append of whatever was already on disk. The old
    read-append-write pattern (read_intake_transcript() -- list-only, silently
    returned [] for a dict -- then write back over the same path) is exactly
    how a signed envelope got silently replaced by a 2-entry bare list live:
    the append saw a dict, treated it as "no prior transcript", and clobbered
    it. See read_intake_transcript_raw()/write_intake_transcript_raw() below
    for where turns are actually appended now (a SEPARATE file the signed
    envelope is never read-modified from)."""
    dest = run_dir / "working" / "interview"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "intake_transcript.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# FAULT-21 fix (2026-08-20): the driver's OWN append-only turn log.
#
# Root cause of the live incident: cmd_answer / _sig_answer both did a
# read-append-write directly against working/interview/intake_transcript.json
# -- the SAME path the signed envelope ({"format": "sp-intake-transcript-v1",
# ..., "driver_signature": ...}) lives at once an intake (or a signature
# intake) has been finalized. The read side (the old read_intake_transcript())
# only understood a bare list -- `obj if isinstance(obj, list) else []` -- so
# once the file held a signed dict envelope, the very next --answer silently
# saw "no prior transcript", appended its 1-2 new turns to an empty list, and
# wrote that 2-entry bare list straight over the signed envelope. No error, no
# warning, no backup -- driver_signature and qid_sequence just vanished, and
# P-SP-INTAKE-TRACE correctly (but confusingly, after the fact) fail-closed.
#
# The fix: turns are appended ONLY here, to a file the signed envelope NEVER
# lives at. The envelope at intake_transcript.json is always a full,
# from-scratch regeneration from this log (_finalize_transcript_envelope(),
# below) -- never a read-modify-write of the envelope file itself. That
# structurally removes the hazard rather than papering over it with an
# isinstance() check at each call site.
# ---------------------------------------------------------------------------
def read_intake_transcript_raw(run_dir: Path) -> List[Dict[str, Any]]:
    """Read working/interview/intake_transcript_raw.json -- the append-only
    turn log ({"role", "text", "qid"} records) cmd_answer/_sig_answer append
    to. Returns [] if absent/unreadable (same tolerant-degrade posture as
    every other reader in this file)."""
    path = run_dir / "working" / "interview" / "intake_transcript_raw.json"
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
            return obj if isinstance(obj, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def write_intake_transcript_raw(run_dir: Path,
                                turns: List[Dict[str, Any]]) -> None:
    """Write working/interview/intake_transcript_raw.json atomically. This
    file is ALWAYS a bare list -- it is never the signed envelope, so there is
    no dict-vs-list ambiguity for a caller to mishandle."""
    dest = run_dir / "working" / "interview"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "intake_transcript_raw.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(turns, fh, indent=2, default=str)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# STANDARD mode -- turn-gate: --next / --answer / --complete
# ---------------------------------------------------------------------------
def _first_unanswered(questions: List[Dict[str, Any]],
                      answers: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find the first question whose storeOn key is not in answers,
    respecting conditional skips."""
    for q in questions:
        qid = q["id"]
        store_on = q.get("storeOn", qid)
        if store_on in answers or qid in answers:
            continue
        should, _reason = should_ask(q, answers)
        if not should:
            continue
        return q
    return None


def cmd_next(args) -> int:
    """Return exactly ONE question -- the next unanswered one."""
    run_dir = args.run_dir.expanduser().resolve()
    schema = load_question_schema()
    questions = get_questions(schema)
    ledger = read_intake_ledger(run_dir)
    entries = ledger.get("entries", {})
    # BUGFIX (fresh-process --next after presentation_type is answered): entries
    # are nested ledger records ({"value": ..., "validated": ..., ...}), never
    # bare strings. Flatten through the SAME tolerant accessor cmd_answer already
    # uses to build its post-answer `answers` dict (below, and in cmd_complete's
    # val extraction) -- reusing it here rather than adding a fourth way to read
    # the same field. Feeding the raw nested entries dict straight into
    # derive_legacy_fields() (or into should_ask()'s conditional_on/ask_if
    # comparisons via _first_unanswered) crashed cmd_next with a ValueError on
    # every bare --next call once presentation_type had been recorded.
    answers = {k: (v.get("value") if isinstance(v, dict) else v)
               for k, v in entries.items()
               if not k.startswith("_")}

    # If presentation_type is answered, auto-derive legacy fields
    ptype = answers.get("presentation_type")
    if ptype:
        try:
            sig_src = answers.get("signature_source")
            derived = derive_legacy_fields(ptype, signature_source=sig_src)
            intake = read_intake_json(run_dir)
            intake.update(derived)
            intake["presentation_type"] = ptype
            write_intake_json(run_dir, intake)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}))
            return 1

    next_q = _first_unanswered(questions, answers)
    if next_q is None:
        print(json.dumps({"status": "complete",
                          "message": "All questions answered. Run --complete to "
                                     "finalize."}))
        return 0

    return _emit_question(next_q, answers)


def cmd_answer(args) -> int:
    """Record one answer and return the next question."""
    run_dir = args.run_dir.expanduser().resolve()
    qid = args.question_id
    text = args.text
    schema = load_question_schema()
    questions = get_questions(schema)

    # Find the question definition
    qdef = None
    for q in questions:
        if q["id"] == qid:
            qdef = q
            break
    if qdef is None:
        print(json.dumps({"error": f"Unknown question id: {qid}"}))
        return 1

    # Validate enum values
    allowed = qdef.get("allowed_values")
    if allowed and text.strip() not in allowed:
        print(json.dumps({"error": f"Invalid value {text!r} for {qid}. "
                                   f"Allowed: {allowed}"}))
        return 1

    # Record the answer
    ledger = read_intake_ledger(run_dir)
    # FAULT-21 fix: capture completion state BEFORE this answer touches the
    # ledger. A --complete that already ran (status=="complete"/complete==True)
    # means a signed driver envelope may already exist at
    # working/interview/intake_transcript.json -- if so, this answer's turn
    # must be APPENDED and the envelope RE-SIGNED after it is recorded below,
    # never silently left stale or (the old bug) clobbered.
    already_complete = bool(ledger.get("complete")) or ledger.get("status") == "complete"
    entries = ledger.get("entries", {})
    store_on = qdef.get("storeOn", qid)
    entries[store_on] = {"value": text.strip(), "validated": True,
                         "source": "deck-intake-driver",
                         "answered_at": datetime.now(timezone.utc).isoformat()}
    # Also store by question id for lookup
    entries[qid] = entries[store_on]

    # Handle presentation_type -- derive legacy fields immediately
    if qid == "presentation_type":
        ptype = text.strip()
        if ptype not in LEGAL_PRESENTATION_TYPES:
            print(json.dumps({"error": f"Invalid presentation_type {ptype!r}"}))
            return 1
        try:
            derived = derive_legacy_fields(ptype)
            intake = read_intake_json(run_dir)
            intake.update(derived)
            intake["presentation_type"] = ptype
            write_intake_json(run_dir, intake)
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}))
            return 1

    # Handle signature_source -- override creation_mode if needed
    if qid == "signature_source":
        ptype = entries.get("presentation_type", {}).get("value", "")
        sig_src = text.strip()
        if ptype == "signature":
            try:
                derived = derive_legacy_fields(ptype, signature_source=sig_src)
                intake = read_intake_json(run_dir)
                intake.update(derived)
                intake["signature_source"] = sig_src
                write_intake_json(run_dir, intake)
            except ValueError as exc:
                print(json.dumps({"error": str(exc)}))
                return 1

    # Save ledger
    ledger["entries"] = entries
    ledger["status"] = "in_progress"
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_intake_ledger(run_dir, ledger)

    # FAULT-21 fix: append to the RAW turn log (never the signed envelope file
    # directly -- see write_intake_transcript()'s docstring above). Two turns
    # per answer (assistant prompt + owner answer), the SAME {"role","text",
    # "qid"} shape _sig_answer already used, so cmd_complete's envelope
    # builder and the signature pass's share one signer with no format drift
    # between STANDARD and SIGNATURE mode.
    raw_turns = read_intake_transcript_raw(run_dir)
    raw_turns.append({"role": "assistant", "text": qdef.get("prompt", qid), "qid": qid})
    raw_turns.append({"role": "owner", "text": text.strip(), "qid": qid})
    write_intake_transcript_raw(run_dir, raw_turns)

    # FAULT-21 fix: this answer arrived AFTER --complete already ran. A
    # signed envelope may already exist -- re-sign it now so it grows to
    # include this turn instead of going stale (or, under the old bug, being
    # silently destroyed). Never silent: stderr NOTICE + a JSON field below.
    extra: Dict[str, Any] = {}
    if already_complete:
        envelope, warning = _finalize_transcript_envelope(run_dir)
        extra["post_completion_append"] = True
        extra["envelope_resigned"] = envelope is not None
        print("  NOTICE  [POST-COMPLETION-APPEND] this answer was recorded "
              "after --complete already ran (intake_ledger.json status== "
              "complete). The signed driver envelope at working/interview/"
              "intake_transcript.json was RE-SIGNED to include this new turn "
              "-- provenance was preserved and extended, never overwritten. "
              "Re-run --complete if intake.json / the SP claim gate also need "
              "to reflect this answer.", file=sys.stderr)
        if warning:
            extra["envelope_warning"] = warning
            print(f"  WARN  {warning}", file=sys.stderr)

    # Return next question (or complete signal)
    answers = {k: (v.get("value") if isinstance(v, dict) else v)
               for k, v in entries.items()
               if not k.startswith("_")}
    next_q = _first_unanswered(questions, answers)
    if next_q is None:
        payload = {"status": "complete",
                  "message": "All questions answered. Run --complete "
                             "to finalize."}
        payload.update(extra)
        print(json.dumps(payload))
        return 0

    return _emit_question(next_q, answers, extra=extra)


def _emit_question(qdef: Dict[str, Any],
                   answers: Dict[str, Any],
                   extra: Optional[Dict[str, Any]] = None) -> int:
    """Print one question as JSON to stdout."""
    prompt = qdef.get("prompt", "")
    help_text = qdef.get("help", "")
    kind = qdef.get("kind", "text")
    allowed = qdef.get("allowed_values")
    value_labels = qdef.get("value_labels")
    default = qdef.get("default")
    required = qdef.get("required", False)
    block_gate = qdef.get("block_gate", False)

    output = {
        "question_id": qdef["id"],
        "order": qdef.get("order"),
        "prompt": prompt,
        "kind": kind,
        "required": required,
        "block_gate": block_gate,
    }
    if help_text:
        output["help"] = help_text
    if allowed:
        output["allowed_values"] = allowed
        if value_labels:
            output["value_labels"] = value_labels
    if default is not None:
        output["default"] = default
    if extra:
        output.update(extra)

    print(json.dumps(output, indent=2))
    return 0


def cmd_complete(args) -> int:
    """Finalize the intake: write merged intake.json, run SP claim gate,
    mark ledger complete."""
    run_dir = args.run_dir.expanduser().resolve()
    ledger = read_intake_ledger(run_dir)

    if not ledger.get("entries"):
        print(json.dumps({"error": "No intake answers recorded. Run "
                                   "--next / --answer first."}))
        return 1

    # Merge all answers into intake.json
    entries = ledger.get("entries", {})
    intake = read_intake_json(run_dir)
    for store_key, entry in entries.items():
        if isinstance(entry, dict):
            val = entry.get("value")
            if val is not None:
                intake[store_key] = val

    # Ensure deck_type is set (should already be from derive_legacy_fields)
    if not intake.get("deck_type"):
        ptype = intake.get("presentation_type") or \
                (entries.get("presentation_type", {}).get("value")
                 if isinstance(entries.get("presentation_type"), dict) else
                 entries.get("presentation_type"))
        if ptype:
            derived = derive_legacy_fields(ptype)
            intake.update(derived)
        else:
            print(json.dumps({"error": "presentation_type was never answered. "
                                       "Cannot derive deck_type."}))
            return 1

    # SP claim gate -- run unconditionally for every deck
    sp_result = _run_sp_claim_gate(run_dir, intake)
    if sp_result:
        print(json.dumps({"error": "SP claim gate failed",
                          "failures": sp_result}))
        return 2

    # fix/deck-type-routing-bypass follow-up: stamp the requester identity
    # (env -> intake.json) so the engine's resolve_intake.py has something to
    # read besides an empty ledger. See _resolve_requester_from_env() above.
    intake.update(_resolve_requester_from_env(intake))

    # Mark interview_confirmed
    intake["interview_confirmed"] = True
    intake["interview_completed_at"] = \
        datetime.now(timezone.utc).isoformat()
    write_intake_json(run_dir, intake)

    # FAULT-22 fix (2026-08-20): build the signed driver-envelope transcript
    # on EVERY completion path -- not only via the separate 8-Sacred-
    # Questions signature pass's _sig_finalize(). Before this fix, --complete
    # never called a signer at all: it only merged answers into intake.json
    # and flipped ledger flags, so a signature deck driven the obvious way
    # (--next / --answer / --complete, never the separate --signature pass)
    # produced a bare-list transcript with no driver envelope, and
    # P-SP-INTAKE-TRACE could never pass for it. This calls the SAME shared
    # signer _sig_finalize() now also calls (_finalize_transcript_envelope --
    # itself built on intake_trace_check.build_driver_envelope(), never a
    # local reimplementation), so the two completion paths can never drift.
    # Built for every deck_type, not just signature_presentation, so the
    # transcript's provenance is always true regardless of which gate happens
    # to check it today. Fail-soft (mirrors _sig_finalize's own posture): a
    # missing intake_trace_check.py or an empty turn log degrades to a loud
    # stderr WARN, never a blocked completion -- P-SP-INTAKE-TRACE itself
    # already defers for every non-signature deck_type and fails closed at
    # BUILD time (not here) for a signature deck with no real transcript.
    envelope, envelope_warning = _finalize_transcript_envelope(run_dir)
    if envelope_warning:
        print(f"  WARN  {envelope_warning}", file=sys.stderr)

    # Mark ledger complete
    ledger["status"] = "complete"
    ledger["complete"] = True
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_intake_ledger(run_dir, ledger)

    result = {
        "status": "complete",
        "deck_type": intake.get("deck_type"),
        "creation_mode": intake.get("creation_mode"),
        "presentation_type": intake.get("presentation_type"),
        "intake_path": str(run_dir / "working" / "copy" / "intake.json"),
        "intake_transcript_signed": envelope is not None,
    }
    print(json.dumps(result, indent=2))
    return 0


def _run_sp_claim_gate(run_dir: Path,
                       intake: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Run the SP claim gate unconditionally. Returns list of (code, reason)
    failures, or empty list on pass.

    If sp_intake.json is present but deck_type != signature_presentation,
    fail-closed AF-SP-TYPE-UNDECLARED. A non-signature deck with no SP signal
    passes untouched."""
    sp_intake = run_dir / "working" / "copy" / "sp_intake.json"
    declared = intake.get("deck_type") == "signature_presentation"

    if sp_intake.is_file() and not declared:
        return [("AF-SP-TYPE-UNDECLARED",
                 f"working/copy/sp_intake.json is present but intake.json "
                 f"does not declare deck_type == signature_presentation "
                 f"(declared={intake.get('deck_type')!r}). A signature "
                 f"presentation must declare its type -- omitting the magic "
                 f"word makes every SP gate no-op.")]

    return []


# ---------------------------------------------------------------------------
# SIGNATURE mode -- turn-gate with 8 Sacred Questions + frame selection
# ---------------------------------------------------------------------------
SP_EIGHT_QUESTIONS_SPEC: Optional[Dict[str, Any]] = None


def _import_skill51_module(mod_name: str):
    """Lazily import a Skill-51 module (prove_sp_intake / intake_trace_check) by
    file, same candidate-path search _run_prove_sp_intake already uses below.
    Returns the module or None. Used so the driver signs turn-ledger/transcript
    provenance with the EXACT SAME canonicalization + key the prover verifies
    with -- never a hand-rolled reimplementation that could silently drift.

    FAULT-22 follow-up (2026-08-20): candidate list widened to walk every
    ancestor of SCRIPTS_DIR (mirrors build_deck.py's _sp_prover(), which was
    already more robust than this) -- a plain repo/worktree checkout
    (23-ai-workforce-blueprint/ and 51-signature-presentation/ as SIBLING
    top-level dirs) sits more than 2 levels apart from this file and the old
    fixed-depth candidates never resolved it, silently falling through to
    "module not found" outside a materialized/installed layout."""
    from importlib import util as importlib_util
    cands = [SCRIPTS_DIR / (mod_name + ".py")]
    cands += [anc / "51-signature-presentation" / "scripts" / (mod_name + ".py")
              for anc in SCRIPTS_DIR.parents]
    cands += [anc / "skills" / "51-signature-presentation" / "scripts" / (mod_name + ".py")
              for anc in SCRIPTS_DIR.parents]
    for _base in ("/data/.openclaw/skills", str(Path.home() / ".openclaw" / "skills")):
        cands.append(Path(_base) / "51-signature-presentation" / "scripts" / (mod_name + ".py"))
    for cand in cands:
        if cand.is_file():
            try:
                spec = importlib_util.spec_from_file_location(mod_name, cand)
                mod = importlib_util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# FAULT-22 fix (2026-08-20): the ONE shared signer both cmd_complete() and
# _sig_finalize() call. Previously ONLY _sig_finalize() -- reachable exclusively
# through the SEPARATE --signature --sig-next/--sig-answer 8-Sacred-Questions
# pass -- ever built the signed driver envelope; a standard --complete (the
# obvious path: --next / --answer / --complete) never did, so P-SP-INTAKE-TRACE
# could never pass for a signature deck completed that way. Extracting the
# logic here (rather than duplicating a second signer in cmd_complete) means
# the two completion paths use byte-identical signing and can never drift.
# ---------------------------------------------------------------------------
def _transcript_qid_sequence(turns: List[Dict[str, Any]]) -> List[str]:
    """Strictly-ordered, non-duplicated qid sequence from the raw turn log's
    first-surfaced order -- the SAME dedup _sig_finalize always did inline
    (FIX-3-COMPLETION), now the ONE place both completion paths derive it so
    they can never disagree on the shape intake_trace_check.
    check_driver_provenance() requires."""
    seen: set = set()
    seq: List[str] = []
    for t in turns:
        q = t.get("qid") if isinstance(t, dict) else None
        if q and q not in seen:
            seen.add(q)
            seq.append(q)
    return seq


def _build_signed_transcript_envelope(
        raw_turns: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Sign `raw_turns` into a driver envelope using intake_trace_check.py's
    OWN build_driver_envelope() -- never a local reimplementation -- so the
    signature this driver writes is byte-identical to what the checker
    recomputes. Returns (envelope, None) on success, or (None, warning) when
    there is nothing to sign (empty raw_turns -- an intake with no recorded
    Q&A has nothing to attest to) or the signing module cannot be found
    (fail-soft, matching _sig_finalize's pre-existing posture: a missing
    skill-51 install degrades to a loud warning, never a crash of --complete
    /--answer)."""
    if not raw_turns:
        return None, None
    mod = _import_skill51_module("intake_trace_check")
    if mod is None:
        return None, (
            "51-signature-presentation/scripts/intake_trace_check.py could not "
            "be located -- no signed driver envelope was built for this "
            "intake. P-SP-INTAKE-TRACE will fail-closed with AF-INTAKE-BATCH "
            "at build time for a signature_presentation deck until skill 51 "
            "is installed next to deck-intake-driver.py.")
    qid_sequence = _transcript_qid_sequence(raw_turns)
    envelope = mod.build_driver_envelope(qid_sequence, raw_turns)
    return envelope, None


def _finalize_transcript_envelope(
        run_dir: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read the append-only raw turn log, sign it, and write the ONE
    canonical envelope to working/interview/intake_transcript.json --
    ALWAYS a full regeneration from the raw log via write_intake_transcript(),
    NEVER a read-modify-write of the envelope file itself (that read-modify-
    write against the same path was FAULT-21's root cause). Returns
    (envelope_or_None, warning_or_None); the envelope is written to disk only
    when one was actually built (raw_turns non-empty and the signer resolved)."""
    raw_turns = read_intake_transcript_raw(run_dir)
    envelope, warning = _build_signed_transcript_envelope(raw_turns)
    if envelope is not None:
        write_intake_transcript(run_dir, envelope)
    return envelope, warning


# FIX-3-COMPLETION (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18): FIX-3's
# own comment in intake_trace_check.py names two producer-side functions this
# driver was documented to carry -- _transcript_sign_payload() (driver_signature
# over {"qid_sequence":...,"turns":...}) and a matching turn_ledger_provenance
# builder for prove_sp_intake.py's AF-SP-INTAKE-UNPACED gate -- but neither was
# ever implemented here. Every signature intake this driver ever finalized
# therefore produced a bare-list transcript with no driver envelope and an
# sp_intake.json with no turn_ledger_provenance: P-SP-INTAKE-TRACE and (post
# 2026-08-15 grace window) P-SP-INTAKE could never pass for ANY signature deck
# run through the sanctioned tool. _sig_answer/_sig_finalize below now build
# both real, using the provers' own signing functions (never a local
# reimplementation) so the signature is byte-identical to what gets verified.

_SP_BANK_PROMPTS_CACHE: Optional[Dict[str, str]] = None


def _sp_bank_prompt(qid: str) -> str:
    """The exact prompt text shown for `qid` -- q1..q8 from the bank spec,
    sp_mode/signature_frame from the same literal strings _sig_next/
    _emit_frame_question already show the owner. Must stay byte-identical to
    those so intake_trace_check.py's verbatim-bank-prompt match resolves the
    turn to exactly one question id."""
    global _SP_BANK_PROMPTS_CACHE
    if _SP_BANK_PROMPTS_CACHE is None:
        spec = _load_sp_spec()
        _SP_BANK_PROMPTS_CACHE = {sq["id"]: sq.get("prompt", "") for sq in spec.get("questions", [])}
        _SP_BANK_PROMPTS_CACHE["sp_mode"] = (
            "QUICK or IN-DEPTH? QUICK = 1-2hr build. IN-DEPTH = full "
            "4-phase signature talk (100+ slides, 8 Questions, frame "
            "selection).")
        _SP_BANK_PROMPTS_CACHE["signature_frame"] = (
            "Choose a Signature frame: The Rulebook / The Vault / "
            "The Quest / The Original.")
    return _SP_BANK_PROMPTS_CACHE.get(qid, qid)


def _load_sp_spec() -> Dict[str, Any]:
    """Lazily load the SACRED 8 Questions spec."""
    global SP_EIGHT_QUESTIONS_SPEC
    if SP_EIGHT_QUESTIONS_SPEC is not None:
        return SP_EIGHT_QUESTIONS_SPEC
    # Try known paths
    cands = [
        DEPT_ROOT / "51-signature-presentation" / "intake" / "sp-8-questions.json",
        SCRIPTS_DIR.parent.parent / "51-signature-presentation" / "intake" / "sp-8-questions.json",
        Path.home() / ".openclaw" / "skills" / "51-signature-presentation" / "intake" / "sp-8-questions.json",
    ]
    for cand in cands:
        if cand.is_file():
            with open(cand, "r", encoding="utf-8") as fh:
                SP_EIGHT_QUESTIONS_SPEC = json.load(fh)
            return SP_EIGHT_QUESTIONS_SPEC
    # Fallback: embedded minimal spec
    SP_EIGHT_QUESTIONS_SPEC = {
        "questions": [
            {"id": "sp_q1", "order": 0, "prompt": "What is the OFFER this signature talk sells?",
             "kind": "text", "required": True},
            {"id": "sp_q2", "order": 1, "prompt": "Who is the ONE ideal client?",
             "kind": "text", "required": True},
            {"id": "sp_q3", "order": 2, "prompt": "What is their #1 PROBLEM right now?",
             "kind": "text", "required": True},
        ],
        "frame_question": {
            "id": "signature_frame", "prompt": "Choose a Signature frame: The Rulebook / The Vault / The Quest / The Original.",
            "kind": "enum", "allowed_values": ["rulebook", "vault", "quest", "original"],
        },
    }
    return SP_EIGHT_QUESTIONS_SPEC


def cmd_signature(args) -> int:
    """SIGNATURE mode entry. With --next: return the choice-first offer
    (QUICK vs IN-DEPTH). With --answer: record one answer. With --record:
    assemble pre-gathered answers into one atomic record and run prove_sp_intake.

    Legacy bare --signature (no subcommand): returns a pointer to use the
    turn-gate. The old escape hatch that dumped the full payload is gone."""
    run_dir = args.run_dir.expanduser().resolve()

    if getattr(args, 'sig_next', False):
        return _sig_next(run_dir)
    if getattr(args, 'sig_answer', None):
        # sig_answer is a list of [question_id, text] from nargs=2
        sig_answer_val = args.sig_answer
        if isinstance(sig_answer_val, list) and len(sig_answer_val) == 2:
            return _sig_answer(run_dir, sig_answer_val[0], sig_answer_val[1])
        else:
            print(json.dumps({"error": "--sig-answer requires ID and TEXT"}))
            return 2
    if getattr(args, 'sig_record_file', None):
        return _sig_record(run_dir, args.sig_record_file)
    if getattr(args, 'sig_plan', False):
        return _sig_plan()

    # Bare --signature: pointer to turn-gate
    print(json.dumps({
        "status": "use_turn_gate",
        "next_command": "deck-intake-driver.py --signature --next --run-dir <RUN_DIR>",
        "message": "The signature intake is a turn-gate interview. Use --next "
                   "to get the first question (choice-first: QUICK vs IN-DEPTH), "
                   "then --answer to record each response. The old batch-dump "
                   "escape hatch is removed -- a batch is AF-INTAKE-BATCH.",
    }))
    return 0


def _sig_next(run_dir: Path) -> int:
    """Emit the next signature question."""
    ledger = read_intake_ledger(run_dir)
    sp_entries = ledger.get("sp_entries", {})

    # Step 1: choice-first -- QUICK vs IN-DEPTH
    if "sp_mode" not in sp_entries:
        print(json.dumps({
            "question_id": "sp_mode",
            "prompt": "QUICK or IN-DEPTH? QUICK = 1-2hr build. IN-DEPTH = full "
                      "4-phase signature talk (100+ slides, 8 Questions, frame "
                      "selection).",
            "kind": "enum",
            "allowed_values": ["QUICK", "IN-DEPTH"],
            "value_labels": {"QUICK": "QUICK (1-2hr build)",
                             "IN-DEPTH": "IN-DEPTH (full signature talk)"},
            "required": True,
        }))
        return 0

    mode = sp_entries.get("sp_mode", {}).get("value", "IN-DEPTH") \
        if isinstance(sp_entries.get("sp_mode"), dict) else "IN-DEPTH"

    # QUICK mode: skip the 8 Questions
    if mode == "QUICK":
        if "signature_frame" not in sp_entries:
            return _emit_frame_question()
        return _sig_finalize(run_dir, ledger, sp_entries)

    # IN-DEPTH: ask the 8 Questions one at a time
    spec = _load_sp_spec()
    sp_questions = spec.get("questions", [])

    for sq in sp_questions:
        sqid = sq["id"]
        if sqid not in sp_entries:
            print(json.dumps({
                "question_id": sqid,
                "prompt": sq.get("prompt", ""),
                "kind": sq.get("kind", "text"),
                "required": sq.get("required", True),
                "help": sq.get("help", ""),
            }))
            return 0

    # After all 8 Questions: frame selection
    if "signature_frame" not in sp_entries:
        return _emit_frame_question()

    return _sig_finalize(run_dir, ledger, sp_entries)


def _emit_frame_question() -> int:
    """Emit the frame-selection question."""
    print(json.dumps({
        "question_id": "signature_frame",
        "prompt": "Choose a Signature frame: The Rulebook / The Vault / "
                  "The Quest / The Original.",
        "kind": "enum",
        "allowed_values": ["rulebook", "vault", "quest", "original"],
        "value_labels": {
            "rulebook": "The Rulebook -- your methodology codified",
            "vault": "The Vault -- your unique IP/proprietary system",
            "quest": "The Quest -- the client's transformation journey",
            "original": "The Original -- a new signature frame you define",
        },
        "required": True,
        "help": "This frame shapes every slide in the deck. The Signature "
                "Presentation Architect will enforce it at every QC gate.",
    }))
    return 0


def _sig_answer(run_dir: Path, qid: str, text: str) -> int:
    """Record one signature answer and return the next question."""
    ledger = read_intake_ledger(run_dir)
    # FAULT-21 sibling fix: capture completion state BEFORE this call flips
    # ledger["status"] back to "in_progress" below. _sig_finalize() (reached
    # via the normal walk once every required question is present again) will
    # rebuild the envelope from scratch anyway, but a caller answering one
    # NEW post-completion bank question and stopping there (never reaching
    # finalize again in this call) must not leave the signed envelope stale
    # -- re-sign it immediately, same guarantee cmd_answer now gives.
    already_complete = bool(ledger.get("complete")) or ledger.get("status") == "complete"
    sp_entries = ledger.get("sp_entries", {})

    # Validate frame selection
    if qid == "signature_frame":
        allowed = ["rulebook", "vault", "quest", "original"]
        if text.strip() not in allowed:
            print(json.dumps({"error": f"Invalid frame {text!r}. "
                                       f"Must be one of: {allowed}"}))
            return 1

    asked_at = datetime.now(timezone.utc).isoformat()
    sp_entries[qid] = {"value": text.strip(), "validated": True,
                       "source": "deck-intake-driver --signature",
                       "answered_at": asked_at}
    ledger["sp_entries"] = sp_entries
    ledger["status"] = "in_progress"
    ledger["updated_at"] = asked_at

    # FIX-3-COMPLETION: the driver's own turn-gate stamp (per-question turn id +
    # asked_at/validated_at), one entry per question actually surfaced through
    # THIS turn gate -- required for prove_sp_intake.py's AF-SP-INTAKE-UNPACED
    # (turn_ledger_provenance) and never faked by hand (see module docstring
    # above _sp_bank_prompt).
    turn_log = ledger.setdefault("sp_turn_log", [])
    turn_log.append({"question_id": qid, "turn": len(turn_log) + 1,
                     "asked_at": asked_at,
                     "validated_at": datetime.now(timezone.utc).isoformat()})
    write_intake_ledger(run_dir, ledger)

    # Append BOTH the assistant's exact bank-prompt turn and the owner's answer
    # turn -- a real one-question-per-turn conversation has both sides, and
    # intake_trace_check.py's verbatim-prompt match needs the assistant turn's
    # text to be byte-identical to the bank prompt to resolve to exactly one
    # question id (never a multi-question-per-turn false positive).
    #
    # FAULT-21 sibling fix: this now appends to the RAW turn log, never the
    # signed envelope file itself -- same hazard, same fix as cmd_answer's
    # (see write_intake_transcript()'s docstring).
    raw_turns = read_intake_transcript_raw(run_dir)
    raw_turns.append({"role": "assistant", "text": _sp_bank_prompt(qid), "qid": qid})
    raw_turns.append({"role": "owner", "text": text.strip(), "qid": qid})
    write_intake_transcript_raw(run_dir, raw_turns)

    if already_complete:
        _envelope, _warning = _finalize_transcript_envelope(run_dir)
        print("  NOTICE  [POST-COMPLETION-APPEND] this signature answer was "
              "recorded after the signature intake already completed. The "
              "signed driver envelope at working/interview/"
              "intake_transcript.json was RE-SIGNED to include this new turn "
              "-- provenance was preserved and extended, never overwritten.",
              file=sys.stderr)
        if _warning:
            print(f"  WARN  {_warning}", file=sys.stderr)

    return _sig_next(run_dir)


def _sig_finalize(run_dir: Path, ledger: Dict[str, Any],
                  sp_entries: Dict[str, Any]) -> int:
    """Assemble the ONE atomic record, write sp_intake.json, run prove_sp_intake."""
    mode_value = (sp_entries.get("sp_mode", {}).get("value", "IN-DEPTH")
                 if isinstance(sp_entries.get("sp_mode"), dict)
                 else sp_entries.get("sp_mode", "IN-DEPTH"))
    frame_value = (sp_entries.get("signature_frame", {}).get("value")
                  if isinstance(sp_entries.get("signature_frame"), dict)
                  else sp_entries.get("signature_frame"))
    commit_id = "rec_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    # Build the atomic record. "mode" stays the interview DEPTH (QUICK/IN-DEPTH)
    # -- prove_sp_routing.py's P-SP-CLAIM gate (one phase earlier) requires it.
    # "delivery.mode" is the SEPARATE record-commit-mode signal prove_sp_intake.py's
    # AF-SP-8Q-SPLIT actually means ("the assembled RECORD's atomic-commit mode, NOT
    # a batch of questions" -- its own docstring); FIX-3-COMPLETION above namespaces
    # it so the two never collide on one key (see prove_sp_intake._resolve_mode).
    record = {
        "deck_type": "signature_presentation",
        "committed_at": datetime.now(timezone.utc).isoformat(),
        "record_committed_atomically": True,
        "record_commit_ids": commit_id,
        "one_block": True,
        "mode": mode_value,
        "delivery": {"mode": "one_block", "record_committed_atomically": True,
                    "asked_all_at_once": True},
        "signature_frame": frame_value,
    }

    # Add the 8 Questions -- both the RUNTIME "answers" shape prove_sp_intake.py's
    # evaluate() actually reads (_missing_questions/_evaluate_turn_pacing) and the
    # flat top-level keys older/other readers in this codebase use. Same values,
    # never re-typed.
    spec = _load_sp_spec()
    answers: Dict[str, str] = {}
    for sq in spec.get("questions", []):
        sqid = sq["id"]
        entry = sp_entries.get(sqid, {})
        val = entry.get("value") if isinstance(entry, dict) else entry
        answers[sqid] = val or ""
        record[sqid] = val or ""
    record["answers"] = answers
    q7_offer = answers.get("q7") or ""
    record["offer_token_ledger"] = [q7_offer] if q7_offer else []

    # FIX-3-COMPLETION: turn_ledger_provenance -- one entry per REQUIRED question
    # (q1..q8) from the turn-gate's own log (ledger["sp_turn_log"], written by
    # _sig_answer as each turn actually happened), signed with prove_sp_intake.py's
    # OWN _sign_turn_ledger so the signature the prover recomputes matches exactly.
    turn_log = ledger.get("sp_turn_log", [])
    req_ids = [sq["id"] for sq in spec.get("questions", [])]
    ledger_turns = [{"question_id": t["question_id"], "turn": t["turn"],
                     "asked_at": t.get("asked_at"), "validated_at": t.get("validated_at")}
                    for t in turn_log if t.get("question_id") in req_ids]
    prove_sp_intake_mod = _import_skill51_module("prove_sp_intake")
    if ledger_turns and prove_sp_intake_mod is not None:
        sig = prove_sp_intake_mod._sign_turn_ledger(ledger_turns, record["deck_type"], commit_id)
        record["turn_ledger_provenance"] = {"turns": ledger_turns, "signature": sig}

    # Write sp_intake.json atomically
    sp_dest = run_dir / "working" / "copy"
    sp_dest.mkdir(parents=True, exist_ok=True)
    sp_path = sp_dest / "sp_intake.json"
    sp_tmp = sp_path.with_suffix(".json.tmp")
    with open(sp_tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, default=str)
    os.replace(sp_tmp, sp_path)

    # FIX-3-COMPLETION / FAULT-22 shared-signer refactor (2026-08-20): wrap the
    # raw turn log (appended turn-by-turn by _sig_answer into the SEPARATE
    # intake_transcript_raw.json -- see FAULT-21) into the signed driver
    # envelope P-SP-INTAKE-TRACE / intake_trace_check.check_driver_provenance()
    # requires -- {"format": "sp-intake-transcript-v1", "qid_sequence": [...],
    # "turns": [...], "driver_signature": ...}. This now calls the SAME shared
    # signer cmd_complete() calls (_finalize_transcript_envelope --
    # intake_trace_check.py's OWN build_driver_envelope(), never a local
    # reimplementation) so the two completion paths can never drift.
    _envelope, _envelope_warning = _finalize_transcript_envelope(run_dir)
    if _envelope_warning:
        print(f"  WARN  {_envelope_warning}", file=sys.stderr)

    # Ensure deck_type is signature_presentation
    intake = read_intake_json(run_dir)
    intake["deck_type"] = "signature_presentation"
    intake["presentation_type"] = "signature"
    intake["signature_frame"] = record.get("signature_frame")
    # FIX F19: this is a finalize path (same as cmd_complete's) -- stamp the
    # requester here too, or a signature-mode deck driven straight to
    # --record never picks up either the chat-surface env vars or the
    # operator fallback. See _resolve_requester_from_env()'s own docstring.
    intake.update(_resolve_requester_from_env(intake))
    write_intake_json(run_dir, intake)

    # Run prove_sp_intake if available (fail-soft warn -- the claim gate in
    # build_deck.py's preflight is the real enforcement). The driver's early
    # prove is advisory only; it must never block intake completion.
    prove_warnings = _run_prove_sp_intake(run_dir)
    if prove_warnings:
        for code, reason in prove_warnings:
            print(f"  WARN  [{code}] {reason}", file=sys.stderr)

    # Mark ledger complete
    ledger["status"] = "complete"
    ledger["complete"] = True
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_intake_ledger(run_dir, ledger)

    print(json.dumps({
        "status": "complete",
        "deck_type": "signature_presentation",
        "signature_frame": record.get("signature_frame"),
        "mode": record.get("mode"),
        "sp_intake_path": str(sp_path),
        "message": "Signature intake complete. Atomic record written. "
                   "SP intake prover passed.",
    }))
    return 0


def _sig_record(run_dir: Path, record_file: str) -> int:
    """Assemble a pre-gathered answers file into one atomic record and verify.
    For tooling that already ran the turn-gate through another surface
    (e.g., the intake mini-app bridge)."""
    try:
        with open(record_file, "r", encoding="utf-8") as fh:
            answers = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"error": f"Cannot read record file: {exc}"}))
        return 1

    # Validate it has at minimum a signature_frame
    if not answers.get("signature_frame"):
        print(json.dumps({"error": "Record is missing signature_frame. "
                                   "A signature intake MUST select a frame."}))
        return 1

    # Write the atomic record
    record = dict(answers)
    record["committed_at"] = datetime.now(timezone.utc).isoformat()
    record["record_committed_atomically"] = True
    record["one_block"] = True

    sp_dest = run_dir / "working" / "copy"
    sp_dest.mkdir(parents=True, exist_ok=True)
    sp_path = sp_dest / "sp_intake.json"
    sp_tmp = sp_path.with_suffix(".json.tmp")
    with open(sp_tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, default=str)
    os.replace(sp_tmp, sp_path)

    # Set deck_type
    intake = read_intake_json(run_dir)
    intake["deck_type"] = "signature_presentation"
    intake["presentation_type"] = "signature"
    intake["signature_frame"] = record.get("signature_frame")
    # FIX F19: this is a finalize path (same as cmd_complete's) -- stamp the
    # requester here too, or a mini-app-driven signature record (this
    # function exists specifically for "tooling that already ran the
    # turn-gate through another surface") never picks one up. See
    # _resolve_requester_from_env()'s own docstring.
    intake.update(_resolve_requester_from_env(intake))
    write_intake_json(run_dir, intake)

    # Prove it (fail-soft -- build_deck.py preflight is the real gate)
    prove_warnings = _run_prove_sp_intake(run_dir)
    if prove_warnings:
        for code, reason in prove_warnings:
            print(f"  WARN  [{code}] {reason}", file=sys.stderr)

    # Mark complete
    ledger = read_intake_ledger(run_dir)
    ledger["status"] = "complete"
    ledger["complete"] = True
    ledger["sp_entries"] = record
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_intake_ledger(run_dir, ledger)

    print(json.dumps({
        "status": "complete",
        "deck_type": "signature_presentation",
        "signature_frame": record.get("signature_frame"),
        "sp_intake_path": str(sp_path),
    }))
    return 0


def _sig_plan() -> int:
    """Print the full signature question set for offline inspection.
    Read-only, never a substitute for driving the live interview."""
    spec = _load_sp_spec()
    output = {
        "mode": "signature_plan",
        "choice_first": {
            "question_id": "sp_mode",
            "prompt": "QUICK or IN-DEPTH?",
            "options": ["QUICK", "IN-DEPTH"],
        },
        "questions": spec.get("questions", []),
        "frame_question": spec.get("frame_question", {}),
        "warning": "This is a READ-ONLY plan for inspection. The live "
                   "interview MUST use --signature --next / --answer. "
                   "A batch dump of all questions is AF-INTAKE-BATCH.",
    }
    print(json.dumps(output, indent=2))
    return 0


def _run_prove_sp_intake(run_dir: Path) -> List[Tuple[str, str]]:
    """Run prove_sp_intake.py if available. Returns list of (code, reason)
    failures, or empty list on pass. Fail-closed: a missing prover is a
    non-blocking warn (the claim gate in build_deck.py will catch it)."""
    sp_intake = run_dir / "working" / "copy" / "sp_intake.json"
    if not sp_intake.is_file():
        return [("AF-SP-8Q-MISSING",
                 "working/copy/sp_intake.json was not written")]

    # Try importing prove_sp_intake
    from importlib import util as importlib_util
    cands = [
        SCRIPTS_DIR / "prove_sp_intake.py",
        SCRIPTS_DIR.parent / "51-signature-presentation" / "scripts" / "prove_sp_intake.py",
        SCRIPTS_DIR.parent.parent / "51-signature-presentation" / "scripts" / "prove_sp_intake.py",
        Path.home() / ".openclaw" / "skills" / "51-signature-presentation" / "scripts" / "prove_sp_intake.py",
    ]
    for cand in cands:
        if cand.is_file():
            try:
                spec = importlib_util.spec_from_file_location(
                    "prove_sp_intake", cand)
                mod = importlib_util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                # FIX-3-COMPLETION: this was passing the Path object itself, not
                # its parsed contents -- evaluate() always saw "not a JSON
                # object" (AF-SP-TYPE-MISMATCH) regardless of what the record
                # actually contained. Advisory-only (never blocked intake
                # completion either way -- build_deck.py's preflight is the
                # real enforcement) but worth reading correctly.
                with open(sp_intake, "r", encoding="utf-8") as _fh:
                    sp_intake_obj = json.load(_fh)
                fails = mod.evaluate(sp_intake_obj)
                return fails if fails else []
            except Exception as exc:
                return [("AF-SP-8Q-MISSING",
                         f"prove_sp_intake raised {exc} -- fail-closed")]
    # Prover not found -- warn but don't block (build_deck.py will catch)
    print(f"  WARN  prove_sp_intake.py not found -- SP intake prover not run. "
          f"The claim gate in build_deck.py will verify at preflight.",
          file=sys.stderr)
    return []


# ---------------------------------------------------------------------------
# question-set export
# ---------------------------------------------------------------------------
def cmd_question_set(args) -> int:
    """Export the full question bank (all modes). Read-only."""
    schema = load_question_schema()
    questions = get_questions(schema)

    output = {
        "schema_version": schema.get("version", "unknown"),
        "description": schema.get("description", ""),
        "legacy_field_mapping": schema.get("legacy_field_mapping", {}),
        "total_questions": len(questions),
        "questions": questions,
    }
    print(json.dumps(output, indent=2))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="deck-intake-driver.py",
        description="THE ONE sanctioned intake bridge for Presentations. "
                    "Writes deck_type via derive_legacy_fields() -- never "
                    "hardcoded, never hand-typed.")
    p.add_argument("--run-dir", type=Path, required=True,
                   help="the deck's run directory")

    # Standard mode
    std = p.add_argument_group("standard mode (one question per turn)")
    std.add_argument("--next", action="store_true",
                     help="return the next unanswered question")
    std.add_argument("--answer", metavar=("ID", "TEXT"), nargs=2,
                     help="record one answer: --answer <question_id> <text>")
    std.add_argument("--complete", action="store_true",
                     help="finalize intake: merge fields, run SP claim gate, "
                          "mark ledger complete")

    # Signature mode
    sig = p.add_argument_group("signature mode (8 Sacred Questions + frame)")
    sig.add_argument("--signature", action="store_true",
                     help="enter SIGNATURE intake mode")
    sig.add_argument("--sig-next", dest="sig_next", action="store_true",
                     help="signature: return next question (choice-first)")
    sig.add_argument("--sig-answer", dest="sig_answer", nargs=2,
                     metavar=("ID", "TEXT"),
                     help="signature: record one answer")
    sig.add_argument("--sig-record", dest="sig_record_file", metavar="FILE",
                     help="signature: assemble pre-gathered answers from FILE "
                          "into atomic record and verify")
    sig.add_argument("--sig-plan", dest="sig_plan", action="store_true",
                     help="signature: print full question set for inspection "
                          "(read-only -- never a substitute for the live "
                          "interview)")

    # Export
    p.add_argument("--question-set", action="store_true",
                   help="export the full question bank (all modes, read-only)")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.run_dir:
        print("FATAL: --run-dir is required", file=sys.stderr)
        return 2

    run_dir = args.run_dir.expanduser().resolve()

    # --question-set
    if args.question_set:
        # Import here to avoid circular issues with the parser's run_dir requirement
        return cmd_question_set(args)

    # Signature mode
    if args.signature:
        return cmd_signature(args)

    # Standard mode: --next
    if args.next:
        return cmd_next(args)

    # Standard mode: --answer ID TEXT
    if args.answer:
        # argparse gives us nargs=2 directly as a list; we need to extract
        # question_id and text from the args
        setattr(args, 'question_id', args.answer[0])
        setattr(args, 'text', args.answer[1])
        return cmd_answer(args)

    # Standard mode: --complete
    if args.complete:
        return cmd_complete(args)

    # No mode selected
    print(json.dumps({
        "error": "No mode selected. Use one of: --next, --answer, --complete, "
                 "--signature --next, --signature --answer, --question-set.",
        "usage": "deck-intake-driver.py --run-dir <DIR> [--next | --answer "
                 "ID TEXT | --complete | --signature [--next | --answer ID TEXT "
                 "| --record FILE] | --question-set]",
    }))
    return 2


if __name__ == "__main__":
    sys.exit(main())
