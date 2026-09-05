#!/usr/bin/env python3
"""
deck-intake-driver.py -- THE ONE sanctioned intake bridge for Presentations.

WORK-ITEM-06: Un-hardcode deck_type. This driver is the SINGLE place deck_type
is written -- via derive_legacy_fields() from the ONE presentation_type answer.
Never hand-typed. Never defaulted to "webinar" by a hardcoded write.

Reads its question schema from intake/deck-intake-questions.json (the canonical
source of truth). Supports two interview modes:

  STANDARD  (--next / --answer / --complete)
    FIX 30 / schema v1.9.0: TWENTY-THREE numbered conversational turns
    (Trevor ruling, binding), down from 58 one-per-turn rows. Each turn row
    (kind "merged") may return several legacy subfields; every answer folds
    into one ledger entry per legacy question id -- captured, derived, or
    explicitly skipped with its documented default (never null) -- so every
    downstream consumer (build_deck mandatory-field gates, the waiver
    provenance contract, the interview-app payload aliases) sees exactly the
    legacy fields it has always seen. The presentation_type branch is turn 1;
    its answer derives all four legacy axis fields (deck_type, creation_mode,
    presentation_mode, audience_mode) automatically via derive_legacy_fields().
    Conditional subfields (recipient_name, signature_source,
    extracted_substance) auto-skip when unmet. ROLLBACK:
    PRESENTATION_INTAKE_V2=0 restores the legacy ask-all-physical-rows
    interview (alias rows re-enter the sequence); the bank itself keeps the
    exact pre-FIX-30 legacy rows verbatim as "alias" rows for that path.
    The drift driver copy (23-ai-workforce-blueprint/scripts/deck-intake-
    driver.py) is deliberately UNAFFECTED: it is a separate signature-mode
    instrument with its own bank consumption path.

  SIGNATURE (--signature --sig-next / --signature --sig-answer ID TEXT)
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
import re
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
# FIX 30: PRESENTATION_INTAKE_V2 -- merged-turn ask-sequence flag.
# DEFAULT ON. ON  -> get_questions() filters out the bank's "alias" rows, so
#                    the ask sequence is the 23 numbered merged turns.
# OFF (0/off/false/no in the env) -> every physical row is returned and asked
#                    one per turn: the pre-FIX-30 legacy interview, byte-for-
#                    byte the same rows the old v1.7.0 bank carried.
# Paired contract: intake/deck-intake-questions.json v1.8.0 (subfields on turn
# rows + verbatim legacy alias rows). With an older alias-less bank the filter
# is a no-op and behavior is the old one regardless of the flag.
# ---------------------------------------------------------------------------
def intake_v2_enabled() -> bool:
    raw = (os.environ.get("PRESENTATION_INTAKE_V2") or "on").strip().lower()
    return raw not in ("0", "off", "false", "no")

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
    """Extract the ordered question list from the schema.

    FIX 30: while PRESENTATION_INTAKE_V2 is on (the default) the bank's
    alias rows are filtered out of the ask sequence -- the 23 merged turn
    rows carry the interview. Flag off: every row returns (legacy behavior).
    """
    questions = list(schema.get("questions", []))
    if intake_v2_enabled():
        questions = [q for q in questions if not q.get("alias")]
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
    answers = _answer_view(entries)

    # FIX 30: pitchless sessions skip rows 11-15 with documented defaults.
    if apply_pitchless_skips(entries, schema, answers):
        ledger["entries"] = entries
        write_intake_ledger(run_dir, ledger)
        answers = _answer_view(entries)

    # If presentation_type is answered, auto-derive legacy fields.
    # FIX 30 fail-soft: a merged deck_type_source turn may store raw prose
    # that matches no legal type; --next must still surface the next question
    # (the interviewer re-prompts), while cmd_complete keeps the loud gate.
    ptype = answers.get("presentation_type")
    if ptype in LEGAL_PRESENTATION_TYPES:
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


# ---------------------------------------------------------------------------
# FIX 30 -- merged-turn derive logic.
# One numbered conversational turn may return several legacy subfields.
# derive_structured_answer() splits a free-text turn answer into
# {legacy_key: value} covering every subfield of the turn row (captured,
# derived, or the documented default/skip value -- never null), per the
# bank's "subfields" annotations. The 23-turn ceiling (Trevor ruling) is a
# property of the merged ask sequence (get_questions + intake_v2_enabled),
# never of parsing.
#
# Parsing contract (mirrored in the bank prompts): unlabelled prose routes
# to the row's FIRST subfield in full (never dropped); lines of the form
# "<legacy id or storeOn>: value" fill named subfields exactly once, in
# declaration order. A subfield captured explicitly is kept even if its
# conditional_on is unmet (client words are never discarded); an UNCAPTURED
# subfield with an unmet condition records its documented default/derived/
# none_value, and only a fully undocumentable skip leaves the marker entry.
# ---------------------------------------------------------------------------
_PITCHLESS_RE = re.compile(r"no\s+pitch|pitchless|without\s+(a\s+)?pitch", re.I)
_INT_RE = re.compile(r"(\d+)")
_WPM_RE = re.compile(r"(\d{2,4})\s*w(?:ords)?[\s-]*p(?:m|er\s?min)", re.I)
_MIN_RE = re.compile(r"(\d{1,3})\s*(?:minutes|minute|mins|m)\b", re.I)
_H_RE = re.compile(r"(\d{1,2})\s*(?:hours|hour|hrs|hr)\b", re.I)
_SLIDES_RE = re.compile(r"(\d{1,4})\s*slides?\b", re.I)

def derive_target_talk_minutes(duration_min: Any) -> Optional[int]:
    """Turn-7 (duration_and_slide_count) -> flat intake root
    target_talk_minutes. build_deck._chk_intake requires a positive NUMBER
    here; nothing wrote it before FIX 30 because the pre-v1.8 bank never
    asked duration in QUICK mode. Returns None when there is no usable
    duration so the caller can fall back to the documented default."""
    try:
        d = int(float(str(duration_min).strip()))
    except (TypeError, ValueError):
        return None
    return d if 5 <= d <= 600 else None

def derive_slide_count_from_duration(duration_min: Any) -> Optional[int]:
    """Blank slide count is DERIVED, not null: ~0.8 slides per talk minute
    (the engine's enforced SLIDES_PER_MINUTE floor is 1.3; 0.8 is the
    conservative planning target well clear of it)."""
    try:
        d = int(float(str(duration_min).strip()))
    except (TypeError, ValueError):
        return None
    if not (1 <= d <= 600):
        return None
    return max(1, int(round(d * 0.8)))

def pitchless_session(derived: Dict[str, Any]) -> bool:
    """Q4 (goal_cta_feeling) decides: a session with no sell has no pitch.
    Group-2 rows (11-15) are skipped-with-defaults when the client says so."""
    blob = " ".join(str(derived.get(k) or "")
                    for k in ("goal", "cta_action", "target_feeling"))
    return bool(_PITCHLESS_RE.search(blob))

def _answer_view(entries: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten ledger entries to a {key: value} answers view. Structured
    parent entries (value is a dict of subfields) additionally merge their
    subfields so conditional_on/ask_if checks against legacy ids keep
    working."""
    answers: Dict[str, Any] = {}
    for k, v in entries.items():
        if k.startswith("_"):
            continue
        val = v.get("value") if isinstance(v, dict) else v
        answers[k] = val
        if isinstance(val, dict):
            for sk, sv in val.items():
                answers.setdefault(sk, sv)
    return answers

def _enum_match(text: str, allowed: List[str]) -> Optional[str]:
    lowered = (text or "").strip().lower()
    for v in allowed:
        if str(v).lower() == lowered:
            return v
    for v in allowed:
        toks = str(v).replace("_", " ").lower().split()
        if toks and all(t in lowered for t in toks):
            return v
    return None

def _yes_or_no(text: str) -> Optional[str]:
    lowered = (text or "").strip().lower()
    if re.match(r"^(y|yes|ya|yeah|yep|sure|do\b|want\b|need\b|please\b|add\b|include\b|build\b|keep\b|upload\b|with\b)", lowered):
        return "yes"
    if re.match(r"^(n|no|nope|none|without|skip\b|decline\b|don'?t|dont\b|negative)", lowered):
        return "no"
    return None

_PACE_WPM = {"default": 130, "medium": 140, "fast": 155}

def _truthy_value(cval: Any) -> bool:
    if isinstance(cval, bool):
        return cval
    if cval is None:
        return False
    return str(cval).strip().lower() not in ("", "no", "false", "none", "0")

def _condition_met(cond: Dict[str, Any], answers: Dict[str, Any]) -> bool:
    cid = cond.get("id", "")
    cval = answers.get(cid)
    if "equals" in cond:
        return str(cval if cval is not None else "") == str(cond["equals"])
    if "in" in cond:
        return cval in cond.get("in", [])
    if "truthy" in cond:
        return _truthy_value(cval)
    return True

# "<label>: value" anywhere in the answer. Left boundary: start or
# sentence-ish punctuation/whitespace; the key must name a subfield of the
# CURRENT row (checked in the caller) so arbitrary colons in prose survive.
_SUBFIELD_LABEL_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s.,;:!?]))([A-Za-z][A-Za-z0-9_ ]{0,40}?)\s*[=:]\s*")

def _claim_labels(qdef: Dict[str, Any], raw: str):
    """Scan one merged-turn answer for "<legacy id or storeOn>: value" labels
    (anywhere in the text, not only at line starts -- clients type them
    inline). Each subfield claims its label exactly once, first occurrence
    wins; a label's value runs to the next CLAIMED label's start. Returns
    (values_by_key, prose_head) where prose_head is the text before the first
    claimed label (or the whole answer when nothing is claimed)."""
    sub = qdef.get("subfields") or {}
    variants: Dict[str, str] = {}
    for k in sub:
        variants[k.lower()] = k
        variants[str(sub[k].get("storeOn", "")).lower()] = k
        # A subfield may declare the extra labels clients actually type for it
        # ("workhorse" for workhorse_model, "qc"/"judge" for qc_model). The
        # label vocabulary stays in the question bank -- the parser reads it,
        # it never hardcodes a field's synonyms. Spaces fold to underscores to
        # match the lookup below ("thinking mode" -> "thinking_mode").
        for label in (sub[k].get("labels") or []):
            token = str(label).strip().lower().replace(" ", "_")
            if token and token not in variants:
                variants[token] = k
    claims: List[List[int]] = []  # [key, value_start, match_start]
    seen: set = set()
    for m in _SUBFIELD_LABEL_RE.finditer(raw or ""):
        key = variants.get(m.group(1).strip().lower().replace(" ", "_"))
        if key is None or key in seen:
            continue
        seen.add(key)
        claims.append([key, m.end(), m.start()])
    values: Dict[str, str] = {}
    for i, item in enumerate(claims):
        end = claims[i + 1][2] if i + 1 < len(claims) else len(raw or "")
        values[item[0]] = (raw or "")[item[1]:end].strip()
    head = (raw or "")[:claims[0][2]].strip() if claims else (raw or "").strip()
    return values, head

def labeled_subfield_values(qdef: Dict[str, Any], text: str) -> Dict[str, str]:
    """Just the labeled {key: value} map of a merged-turn answer."""
    return _claim_labels(qdef, text)[0]

def derive_structured_answer(qdef: Dict[str, Any], text: str,
                             prior: Dict[str, Any]) -> Dict[str, Any]:
    """Split one merged-turn answer into {legacy_key: value}.

    Every declared subfield gets a value unless it is a conditionally-
    inapplicable field with NO documented default/derived/none value --
    those return as a SKIP marker instead (the caller writes a skipped
    entry, never a null answer)."""
    sub = qdef.get("subfields") or {}
    raw = (text or "").strip()
    keys = list(sub.keys())
    labeled, prose_head = _claim_labels(qdef, raw)
    captured: Dict[str, str] = {k: v for k, v in labeled.items() if v != ""}

    merged = dict(prior)
    merged.update(captured)

    # Unlabeled prose routes to the FIRST subfield in declaration order that
    # is neither already claimed nor blocked by an unmet conditional_on (the
    # audience row must not hand its head prose to a skipped recipient_name).
    first = keys[0] if keys else None
    if prose_head and first:
        target = None
        for k in keys:
            if k in captured:
                continue
            cond = (sub[k] or {}).get("conditional_on")
            if cond and not _condition_met(cond, merged):
                continue
            target = k
            break
        if target is None:
            target = first if first not in captured else None
        if target is not None:
            captured[target] = prose_head or raw
            merged[target] = captured[target]
    out: Dict[str, Any] = {}
    skipped: List[str] = []

    def _skip_or_default(k: str, ann: Dict[str, Any]) -> None:
        if "default" in ann:
            out[k] = ann["default"]
        elif ann.get("no_note"):
            out[k] = "no note."
        elif "none_value" in ann:
            out[k] = ann["none_value"]
        elif "conservative_value" in ann:
            out[k] = ann["conservative_value"]
        elif "derived" in ann or k == "target_wpm":
            pass  # handled by the per-field derivations below
        else:
            skipped.append(k)

    for k in keys:
        ann = sub[k]
        cond = ann.get("conditional_on")
        val = captured.get(k)
        if val is None and cond and not _condition_met(cond, merged):
            _skip_or_default(k, ann)
            if k not in out:
                continue
            merged[k] = out[k]
            continue
        if val is None:
            if "default" in ann:
                val = str(ann["default"])
            elif k == "target_wpm" or "derived" in ann:
                val = ""
            else:
                _skip_or_default(k, ann)
                if k in out:
                    merged[k] = out[k]
                continue
        # typed coercions
        if ann.get("boolish"):
            b = _yes_or_no(val)
            out[k] = b if b is not None else (val.strip() or str(ann.get("default", "yes")))
            merged[k] = out[k]
            continue
        if ann.get("enum"):
            e = _enum_match(val, ann["enum"])
            out[k] = e if e is not None else val.strip()
            merged[k] = out[k]
            continue
        if ann.get("kind") == "boolean":
            b = _yes_or_no(val)
            if b == "yes":
                out[k] = True
            elif b == "no":
                out[k] = False
            elif val.strip().lower() in ("free", "open", "access is free"):
                out[k] = True
            elif isinstance(ann.get("default"), bool):
                out[k] = ann["default"]
            else:
                out[k] = bool(val.strip())
            merged[k] = out[k]
            continue
        if ann.get("kind") == "integer" or k in ("duration_min", "target_wpm", "vip_spots"):
            nums = [int(x) for x in _INT_RE.findall(val)]
            if k == "target_wpm":
                wp = _WPM_RE.search(val)
                cand = [n for n in ([int(wp.group(1))] if wp else []) + nums if 60 <= n <= 400]
                if cand:
                    out[k] = cand[0]
                else:
                    pace = str(merged.get("speech_speed_preference") or "default").lower()
                    out[k] = _PACE_WPM.get(pace, _PACE_WPM["default"])
                merged[k] = out[k]
                continue
            if k == "duration_min":
                mins = list(nums)
                hm = _H_RE.search(val)
                if hm:
                    mins.insert(0, int(hm.group(1)) * 60)
                mm = _MIN_RE.search(val)
                if mm:
                    mins.insert(0, int(mm.group(1)))
                cand = [n for n in mins if 1 <= n <= 600]
                out[k] = cand[0] if cand else int(ann.get("default", 30))
                merged[k] = out[k]
                continue
            out[k] = nums[0] if nums else ann.get("default", 0)
            merged[k] = out[k]
            continue
        out[k] = val.strip()
        merged[k] = out[k]

    # ---- documented per-turn derivations (spec FIX 30) ----
    if "slide_count" in sub and "slide_count" not in captured:
        sm = _SLIDES_RE.search(captured.get(first or "", ""))
        if sm:
            out["slide_count"] = sm.group(1) + " (client-stated)"
        else:
            sc = derive_slide_count_from_duration(out.get("duration_min"))
            out["slide_count"] = str(sc) if sc is not None else "duration math decides"
        merged["slide_count"] = out["slide_count"]
    if "access_free" in sub and "access_free" not in captured:
        ev = str(out.get("event_price") or "").strip().lower()
        if any(t in ev for t in ("free", "no cost", "no charge")) or ev in ("", "none"):
            out["access_free"] = True
        elif "$" in ev or re.search(r"\d", ev):
            out["access_free"] = False
        else:
            out["access_free"] = _yes_or_no(ev) == "no"
        merged["access_free"] = out["access_free"]
    if "target_wpm" in sub and "target_wpm" not in captured:
        pace = str(out.get("speech_speed_preference") or merged.get("speech_speed_preference") or "default").lower()
        out["target_wpm"] = _PACE_WPM.get(pace, _PACE_WPM["default"])
        merged["target_wpm"] = out["target_wpm"]
    if "deliverable_set" in sub and "deliverable_set" not in captured:
        parts = ["deck"]
        if str(out.get("want_teleprompter", "yes")).lower().startswith("y"):
            parts.append("teleprompter")
        if str(out.get("want_speech_script", "yes")).lower().startswith("y"):
            parts.append("speech script")
        if str(out.get("want_audio_deliverable", "yes")).lower().startswith("y"):
            parts.append("audio deliverable")
        out["deliverable_set"] = ", ".join(parts) if len(parts) > 1 else "deck-only"
        merged["deliverable_set"] = out["deliverable_set"]
    result = dict(out)
    if skipped:
        result["__skipped__"] = skipped
    return result

# ---- FIX 30 wiring helpers ----
def validate_labeled_enums(qdef: Dict[str, Any], text: str) -> Optional[str]:
    """An explicitly labeled answer for an enum subfield must resolve to one of
    the enum values (exact or keyword-containment) BEFORE anything is written;
    prose routed to the first subfield is matched leniently by the engine."""
    values = labeled_subfield_values(qdef, text)
    for k, ann in (qdef.get("subfields") or {}).items():
        allowed = ann.get("enum")
        if not allowed or k not in values:
            continue
        val = values[k]
        if _enum_match(val, allowed) is None:
            return (f"Invalid value {val!r} for {k}. Allowed: {allowed}")
    return None

def _skip_default_value(ann: Dict[str, Any]) -> Any:
    if "default" in ann:
        return ann["default"]
    if ann.get("no_note"):
        return "no note."
    if "none_value" in ann:
        return ann["none_value"]
    if "conservative_value" in ann:
        return ann["conservative_value"]
    return ""

def apply_pitchless_skips(entries: Dict[str, Any],
                          schema: Dict[str, Any],
                          answers: Dict[str, Any]) -> bool:
    """FIX 30 / spec rows 11-15: a session with no pitch skips the five group-2
    turns. A skip writes each subfield's documented default/none value with a
    skipped marker -- never null. Returns True when entries changed."""
    if not pitchless_session(answers):
        return False
    now = datetime.now(timezone.utc).isoformat()
    store_target = schema.get("storeTarget") or {}
    changed = False
    for q in schema.get("questions", []):
        if not q.get("pitchless_skip") or q["id"] in entries:
            continue
        vals: Dict[str, Any] = {}
        for k, ann in (q.get("subfields") or {}).items():
            v = _skip_default_value(ann)
            vals[k] = v
            rec = {"value": v, "validated": False, "skipped": True,
                   "skip_reason": "pitchless session: rows 11-15 not applicable",
                   "source": "deck-intake-driver", "answered_at": now,
                   "normalized": v, "answer": str(v)}
            entries[k] = rec
            so = str(ann.get("storeOn") or "")
            if so in store_target and so != k:
                entries[so] = rec
        entries[q["id"]] = {"value": vals, "validated": False, "skipped": True,
                            "skip_reason": "pitchless session: rows 11-15 not applicable",
                            "source": "deck-intake-driver", "answered_at": now,
                            "normalized": vals, "answer": "skipped (pitchless)"}
        changed = True
    return changed

# ---------------------------------------------------------------------------
# CLIENT MODEL PLAN -- the intake half of the "nothing is forced" contract
# ---------------------------------------------------------------------------
#: subfield id -> (model-plan slot, ledger key). The ledger keys are written
#: EXPLICITLY here rather than through schema["storeTarget"]: storeTarget
#: entries flow into working/copy/intake.json (the run directory, which ships
#: in the client package), and a client's model plan belongs in the
#: secrets-adjacent profile store, not in the run directory.
_MODEL_PLAN_SUBFIELDS = (
    ("workhorse_model", "workhorse", "WORKHORSE_MODEL"),
    ("reasoning_model", "reasoning", "REASONING_MODEL"),
    ("qc_model", "judge", "QC_MODEL"),
)
_THINKING_SUBFIELD = ("thinking_mode", "THINKING_MODE")


def _import_resource_profile():
    """Import presentation_job.resource_profile beside this driver.

    Fail-soft by design: an intake box that carries the driver but not the
    engine package must still take the interview. Absence is announced LOUDLY
    on stderr and the answer is still recorded in the ledger -- it is never
    swallowed, and it is never reported as a successfully recorded plan."""
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        from presentation_job import resource_profile as _rp  # noqa: PLC0415
        return _rp
    except Exception as exc:  # noqa: BLE001 -- a partial deploy must not kill intake
        print(f"  WARN  [MODEL-PLAN] presentation_job.resource_profile is not "
              f"importable from {SCRIPTS_DIR} ({exc.__class__.__name__}: {exc}) "
              f"-- the client's model choice was recorded in the intake ledger "
              f"but NOT persisted to the resource profile, so routing will use "
              f"the department defaults. Fix the deploy, then re-answer "
              f"resource_plan.", file=sys.stderr)
        return None


def _record_client_model_plan(derived: Dict[str, Any],
                              entries: Dict[str, Any]) -> int:
    """Persist the resource_plan turn's model subfields as a client model plan.

    Returns 0 when there is nothing to record or the plan was recorded, and 1
    (after printing {"error": ...}) when the client's declaration is refused --
    so the client is told AT INTAKE, with the wired inventory named, instead of
    at dispatch time. Called BEFORE the ledger is written, so a refused answer
    never half-lands."""
    # The merged-turn label parser hands a value through with the client's own
    # punctuation still attached ("...@deepseek-direct; qc: ..."), so the
    # trailing separator is trimmed HERE -- once -- and the ledger records the
    # same cleaned text that is recorded on the profile.
    def _clean(raw):
        return str(raw or "").strip().strip(";,.").strip()

    picks = {slot: _clean(derived.get(sub))
             for sub, slot, _key in _MODEL_PLAN_SUBFIELDS}
    thinking = _clean(derived.get(_THINKING_SUBFIELD[0])).lower()
    if not any(picks.values()) and not thinking:
        return 0  # every slot omitted: the department defaults stand

    # Mirror the answers onto their storeOn ledger keys (see the note above:
    # deliberately not routed through storeTarget/intake.json).
    now_iso = datetime.now(timezone.utc).isoformat()
    for sub, slot, key in _MODEL_PLAN_SUBFIELDS:
        value = picks[slot]
        entries[key] = {"value": value, "validated": True,
                        "source": "deck-intake-driver", "answered_at": now_iso,
                        "normalized": value, "answer": value}
    entries[_THINKING_SUBFIELD[1]] = {
        "value": thinking, "validated": True, "source": "deck-intake-driver",
        "answered_at": now_iso, "normalized": thinking, "answer": thinking}

    rp = _import_resource_profile()
    if rp is None:
        return 0  # already announced loudly on stderr; the answer is kept
    plan: Dict[str, Any] = {slot: (picks[slot] or None)
                            for _sub, slot, _key in _MODEL_PLAN_SUBFIELDS}
    plan["thinking"] = thinking or None
    try:
        rp.record_model_plan(plan, source="interview")
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    except Exception as exc:  # noqa: BLE001 -- a store failure is loud, not silent
        print(json.dumps({"error": f"could not record the model plan "
                                   f"({exc.__class__.__name__}): {exc}"}))
        return 1
    return 0


def cmd_answer(args) -> int:
    """Record one answer and return the next question."""
    run_dir = args.run_dir.expanduser().resolve()
    qid = args.question_id
    text = args.text
    schema = load_question_schema()
    questions = get_questions(schema)

    # Find the question definition. FIX 30: resolve against the FULL physical
    # row list (turn rows AND alias rows) so an alias id stays answerable even
    # while the flag filters it out of the ask sequence (the anti-fab test
    # drives --answer presentation_type / named_methodology / time_to_result
    # with V2 on; those rows are aliases).
    all_rows = list(schema.get("questions", []))
    qdef = None
    for q in all_rows:
        if q["id"] == qid:
            qdef = q
            break
    if qdef is None:
        print(json.dumps({"error": f"Unknown question id: {qid}"}))
        return 1

    # Validate enum values (plain rows keep the legacy exact-match gate)
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

    # FIX 30: merged-turn answer -- split into legacy subfield records, each
    # with the SAME shape the drift-side waiver builder reads (validated +
    # normalized + answer), then apply the legacy special handlers.
    structured_intake_writes: Dict[str, Any] = {}
    if qdef.get("subfields"):
        err = validate_labeled_enums(qdef, text)
        if err:
            print(json.dumps({"error": err}))
            return 1
        prior = _answer_view(entries)
        derived = derive_structured_answer(qdef, text, prior)
        skipped_keys = derived.pop("__skipped__", [])
        now_iso = datetime.now(timezone.utc).isoformat()
        store_target = schema.get("storeTarget") or {}
        for k, v in derived.items():
            rec = {"value": v, "validated": True, "source": "deck-intake-driver",
                   "answered_at": now_iso, "normalized": v, "answer": str(v)}
            entries[k] = rec
            so = str((qdef["subfields"].get(k) or {}).get("storeOn") or "")
            if so in store_target and so != k:
                entries[so] = rec
        for k in skipped_keys:
            rec = {"value": "", "validated": False, "skipped": True,
                   "skip_reason": "no value given and no documented default",
                   "source": "deck-intake-driver", "answered_at": now_iso,
                   "normalized": "", "answer": ""}
            entries[k] = rec
        # Parent record keyed by the turn id, holding the full split. FIX 30:
        # when the turn's id IS one of its own subfield ids (resource_plan,
        # proof_assets, visual_mix), the subfield loop above already wrote the
        # scalar record there -- keep it scalar; consumers read a plain value.
        if qid not in derived:
            parent = {k: derived.get(k, "") for k in (qdef["subfields"] or {})}
            entries[qid] = {"value": parent, "validated": True,
                            "source": "deck-intake-driver",
                            "answered_at": now_iso,
                            "normalized": parent, "answer": text.strip()}
        # presentation_type special (mirrors the legacy plain-row handler)
        ptype = derived.get("presentation_type")
        if ptype in LEGAL_PRESENTATION_TYPES:
            try:
                dl = derive_legacy_fields(
                    ptype,
                    signature_source=derived.get("signature_source")
                    if ptype == "signature" else None)
            except ValueError as exc:
                print(json.dumps({"error": str(exc)}))
                return 1
            structured_intake_writes.update(dl)
            structured_intake_writes["presentation_type"] = ptype
        elif ptype is not None and str(ptype).strip():
            # prose that resolved to no legal type: do NOT silently derive a
            # wrong deck_type; cmd_complete keeps its own loud gate.
            pass
        # duration -> flat root target_talk_minutes (build_deck._chk_intake)
        ttm = derive_target_talk_minutes(derived.get("duration_min"))
        if ttm:
            structured_intake_writes["target_talk_minutes"] = ttm
        # client-STATED slide count -> client_requested_slide_count. A
        # duration-derived count must NOT set it (craft_judgement treats
        # presence as client-fixed).
        sc_raw = derived.get("slide_count")
        sc_m = re.search(r"\d+", str(sc_raw or ""))
        if sc_m and ("(client-stated)" in str(sc_raw)
                     or re.search(r"slide[_ ]?count\s*[:=]", text, re.I)):
            structured_intake_writes["client_requested_slide_count"] = int(sc_m.group(0))

        # CLIENT MODEL PLAN (operator requirement 2026-09-04): the client is
        # never forced onto a department default. Recorded HERE, at intake, so
        # a provider the profile does not carry or a model it does not wire is
        # refused while the client is still in the conversation -- never
        # twenty minutes into a dispatch. The plan's home is the
        # secrets-adjacent resource profile (never intake.json, never the run
        # directory): the P4-PROMPT fan-out children re-resolve routes in a
        # separate process that inherits the profile path but has no run_dir.
        if qid == "resource_plan":
            rc = _record_client_model_plan(derived, entries)
            if rc != 0:
                return rc

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

    # FIX 30: structured-turn intake.json writes (deck_type derivation,
    # target_talk_minutes, client-stated slide count), applied AFTER the
    # ledger persisted so a rejection above can never half-write.
    if structured_intake_writes:
        intake = read_intake_json(run_dir)
        intake.update(structured_intake_writes)
        write_intake_json(run_dir, intake)

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
    answers = _answer_view(entries)
    if apply_pitchless_skips(entries, schema, answers):
        ledger["entries"] = entries
        write_intake_ledger(run_dir, ledger)
        answers = _answer_view(entries)
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

    # FIX 30: mirror every captured field into its bank-declared storeTarget
    # location (pre_presentation_capture.* / deck_brief.*). build_deck.py's
    # _intake_provenance_gate reads the SIX mandatory fields from
    # intake.json.pre_presentation_capture, and the pre-FIX-30 chat driver
    # never wrote them (only the interview-app bridge writer did) -- so a
    # driver-run intake failed the gate on a fully-answered interview. This
    # mirrors using the SAME storeTarget table the merged turns annotate, so
    # the chat driver and the app writer now produce the same record shape.
    # Only under the V2 flag: PRESENTATION_INTAKE_V2=0 restores the exact
    # pre-FIX-30 behavior, capture-absence included.
    store_target = {}
    if intake_v2_enabled():
        store_target = load_question_schema().get("storeTarget") or {}
    for field, path in store_target.items():
        entry = entries.get(field)
        if not isinstance(entry, dict):
            continue
        val = entry.get("value")
        if val is None:
            continue
        parts = path.split(".")
        node = intake
        for p in parts[:-1]:
            nxt = node.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                node[p] = nxt
            node = nxt
        node[parts[-1]] = val

    # Ensure deck_type is set (should already be from derive_legacy_fields)
    if not intake.get("deck_type"):
        ptype = intake.get("presentation_type") or \
                (entries.get("presentation_type", {}).get("value")
                 if isinstance(entries.get("presentation_type"), dict) else
                 entries.get("presentation_type"))
        if ptype:
            try:
                derived = derive_legacy_fields(ptype)
            except ValueError as exc:
                print(json.dumps({"error": str(exc)}))
                return 1
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
    """SIGNATURE mode entry. With --sig-next: return the choice-first offer
    (QUICK vs IN-DEPTH). With --sig-answer ID TEXT: record one answer. With
    --sig-record:
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
            origin = getattr(args, 'sig_origin', None) or "client"
            return _sig_answer(run_dir, sig_answer_val[0], sig_answer_val[1],
                               origin=origin)
        else:
            print(json.dumps({"error": "--sig-answer requires ID and TEXT"}))
            return 2
    if getattr(args, 'sig_confirm', None):
        return _sig_confirm(run_dir, args.sig_confirm,
                            confirmed=bool(getattr(args, 'sig_confirmed', False)))
    if getattr(args, 'sig_record_file', None):
        return _sig_record(run_dir, args.sig_record_file)
    if getattr(args, 'sig_plan', False):
        return _sig_plan()

    # Bare --signature: pointer to turn-gate
    print(json.dumps({
        "status": "use_turn_gate",
        "next_command": "deck-intake-driver.py --signature --sig-next --run-dir <RUN_DIR>",
        "message": "The signature intake is a turn-gate interview. Use "
                   "--sig-next to get the first question (choice-first: QUICK "
                   "vs IN-DEPTH), then --sig-answer ID TEXT to record each "
                   "response. The old batch-dump "
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


def _sig_answer(run_dir: Path, qid: str, text: str,
                origin: str = "client") -> int:
    """Record one signature answer and return the next question.

    CONTENT-PROVENANCE contract (2026-08-27 live defect: 2 of 8 answers on a
    passing record were AUTHORED BY THE SYSTEM): every recorded answer carries
    the caller-declared `origin` — "client" (the text is the client's own
    words as received) or "agent_authored" (an operator/agent drafted it).
    An agent-authored answer is a VISIBLY-MARKED DRAFT: it is recorded with
    confirmed_by_client=False, and prove_sp_intake.py's AF-SP-PROVENANCE gate
    refuses it until the client confirms it via --sig-confirm. The flag is a
    DECLARATION by the caller, not proof — the proof is the --sig-confirm
    quote-back step, which is the only thing that can flip
    confirmed_by_client to True (origin stays visible either way)."""
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

    if origin not in ("client", "agent_authored"):
        print(json.dumps({"error": f"Invalid origin {origin!r}. "
                                   f"Must be 'client' or 'agent_authored'."}))
        return 2

    # Validate frame selection
    if qid == "signature_frame":
        allowed = ["rulebook", "vault", "quest", "original"]
        if text.strip() not in allowed:
            print(json.dumps({"error": f"Invalid frame {text!r}. "
                                       f"Must be one of: {allowed}"}))
            return 1

    asked_at = datetime.now(timezone.utc).isoformat()
    # CONTENT-PROVENANCE: the answer entry records WHO the words came from and
    # whether the client has confirmed them. Only --sig-confirm sets
    # confirmed_by_client=True (it is the one step that reads the answer back
    # to the client); a fresh --sig-answer always (re)opens unconfirmed, so an
    # edited answer can never ride a confirmation captured for older wording.
    sp_entries[qid] = {"value": text.strip(), "validated": True,
                       "source": "deck-intake-driver --signature",
                       "origin": origin,
                       "confirmed_by_client": False,
                       "confirmation": None,
                       "answered_at": asked_at}
    ledger["sp_entries"] = sp_entries
    ledger["status"] = "in_progress"
    ledger["updated_at"] = asked_at
    if origin == "agent_authored":
        print("  NOTICE  [AGENT-AUTHORED-DRAFT] this answer was recorded with "
              f"origin='agent_authored' (qid={qid}) -- the text was NOT typed "
              "by the client. It is a visibly-marked draft: it will carry "
              "confirmed_by_client=false into sp_intake.json and AF-SP-"
              "PROVENANCE will refuse the record until the client confirms it "
              f"via: deck-intake-driver.py --run-dir <RUN_DIR> --sig-confirm {qid}",
              file=sys.stderr)

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


def _sig_confirm(run_dir: Path, qid: str, confirmed: bool = False) -> int:
    """QUOTE-BACK CONFIRMATION (2026-08-27 content-provenance contract): read
    the recorded answer for `qid` back VERBATIM and mark it confirmed by the
    client. The operator/agent running the driver relays the quoted text to
    the client and re-runs this command with --confirmed once (and only once)
    the client has actually seen and approved their own words. The no-flag
    first leg prints the quote and exits with the answer STILL UNCONFIRMED
    (fail-closed by construction: nothing here confirms on the client's
    behalf — a confirmation requires a second, explicit --confirmed call).

    The confirmation mode is recorded as 'quote_back'. The gate also accepts
    'direct' (the client voiced/typed the answer themselves) which --sig-answer
    stamps when the caller declares it; origin stays visible on every path."""
    ledger = read_intake_ledger(run_dir)
    sp_entries = ledger.get("sp_entries", {})
    entry = sp_entries.get(qid)

    if not isinstance(entry, dict) or "value" not in entry:
        print(json.dumps({"error": f"No recorded answer for {qid!r} -- nothing "
                                   f"to confirm. Use --sig-answer {qid} <text> first."}))
        return 1

    value = str(entry.get("value") or "")

    if not confirmed:
        # First leg: emit the verbatim quote-back and STOP, unconfirmed.
        print(json.dumps({
            "quote_back": True,
            "question_id": qid,
            "client_text": value,
            "origin": entry.get("origin", "client"),
            "confirmed_by_client": bool(entry.get("confirmed_by_client")),
            "message": "Read this answer back to the client verbatim. Re-run with "
                       "--confirmed ONLY after the client approves their own words: "
                       "deck-intake-driver.py --run-dir <RUN_DIR> --sig-confirm "
                       f"{qid} --confirmed",
        }, indent=2))
        return 0

    entry["confirmed_by_client"] = True
    entry["confirmation"] = "quote_back"
    entry["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    ledger["sp_entries"] = sp_entries
    ledger["updated_at"] = entry["confirmed_at"]
    write_intake_ledger(run_dir, ledger)
    if entry.get("origin") == "agent_authored":
        print("  NOTICE  [AGENT-AUTHORED-CONFIRMED] the client confirmed the "
              f"agent-authored draft for {qid} via quote-back. The record will "
              "carry origin='agent_authored' with confirmed_by_client=true -- "
              "the provenance stays visible, but NOTE: prove_sp_intake.py's "
              "AF-SP-PROVENANCE gate still refuses an agent-authored answer. "
              "Have the client re-answer with --sig-answer --origin client "
              "(or accept that this record must be re-assembled from client "
              "answers only).", file=sys.stderr)
    print(json.dumps({
        "confirmed": True,
        "question_id": qid,
        "client_text": value,
        "origin": entry.get("origin", "client"),
        "confirmation": "quote_back",
        "confirmed_at": entry["confirmed_at"],
    }, indent=2))
    return 0


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

    # CONTENT-PROVENANCE (2026-08-27): answer_provenance -- one entry per
    # REQUIRED question, carried straight from the sp_entries the turn gate
    # wrote (verbatim client_text, origin, confirmed_by_client, confirmation).
    # NEVER fabricated here: an answer recorded before the provenance fields
    # existed (or via a path that did not stamp them) gets an EXPLICIT
    # unprovenanced entry, which AF-SP-PROVENANCE refuses after its dated
    # migration window -- fail-closed, never silently attested.
    answer_provenance: Dict[str, Any] = {}
    for sq in spec.get("questions", []):
        sqid = sq["id"]
        entry = sp_entries.get(sqid, {})
        if not isinstance(entry, dict):
            continue
        val = entry.get("value") or ""
        if not val:
            continue
        origin = entry.get("origin")
        confirmed = bool(entry.get("confirmed_by_client"))
        answer_provenance[sqid] = {
            "client_text": val,
            "origin": origin if origin in ("client", "agent_authored") else "client",
            "confirmed_by_client": confirmed,
            "confirmation": entry.get("confirmation")
                            if confirmed and entry.get("confirmation") in ("quote_back", "direct")
                            else None,
        }
    if answer_provenance:
        record["answer_provenance"] = answer_provenance

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
        # FIX 29: prefer the one-time envelope API so this record carries
        # key_id + signed_at INSIDE the authenticated payload, signed with the
        # CURRENT rotation key from the secrets store. The store-backed 3-arg
        # shim remains the fallback for a pre-FIX-29 sibling checkout.
        signer = getattr(prove_sp_intake_mod, "sign_turn_ledger", None)
        if signer is not None:
            record["turn_ledger_provenance"] = signer(
                ledger_turns, record["deck_type"], commit_id)
        else:
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

    # CONTENT-PROVENANCE surface (2026-08-27): unconfirmed / agent-authored
    # answers are named HERE at finalize time, not only at build preflight --
    # the operator assembling the record sees the exact questions and the
    # exact remedy while the conversation is still open.
    unconfirmed = [qid for qid, blk in answer_provenance.items()
                   if not blk.get("confirmed_by_client")]
    agent_authored = [qid for qid, blk in answer_provenance.items()
                      if blk.get("origin") == "agent_authored"]
    for qid in agent_authored:
        print(f"  WARN  [AF-SP-PROVENANCE] {qid} is origin='agent_authored' -- the "
              f"system authored this answer. AF-SP-PROVENANCE refuses it; the "
              f"client must re-answer it themselves (or confirm via quote-back "
              f"and re-answer as client).", file=sys.stderr)
    for qid in unconfirmed:
        print(f"  WARN  [AF-SP-PROVENANCE] {qid} is NOT confirmed by the client -- "
              f"run: deck-intake-driver.py --run-dir {run_dir} --sig-confirm {qid} "
              f"(then --confirmed after the client approves the verbatim quote).",
              file=sys.stderr)

    # Mark ledger complete
    ledger["status"] = "complete"
    ledger["complete"] = True
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    ledger["answer_provenance"] = answer_provenance
    write_intake_ledger(run_dir, ledger)

    print(json.dumps({
        "status": "complete",
        "deck_type": "signature_presentation",
        "signature_frame": record.get("signature_frame"),
        "mode": record.get("mode"),
        "sp_intake_path": str(sp_path),
        "unconfirmed_answers": unconfirmed,
        "agent_authored_answers": agent_authored,
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
                   "interview MUST use --signature --sig-next / --sig-answer. "
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
    sig.add_argument("--sig-origin", dest="sig_origin",
                     choices=["client", "agent_authored"], default=None,
                     help="signature: declare who the --sig-answer text came from "
                          "(default 'client'). 'agent_authored' records a "
                          "visibly-marked draft the client must confirm via "
                          "--sig-confirm before the record can pass AF-SP-PROVENANCE")
    sig.add_argument("--sig-confirm", dest="sig_confirm", metavar="ID",
                     help="signature: quote-back confirmation -- print the recorded "
                          "answer verbatim for the client to approve (no flag), or "
                          "mark it confirmed after the client approved (--sig-confirmed)")
    sig.add_argument("--sig-confirmed", dest="sig_confirmed", action="store_true",
                     help="with --sig-confirm: record the client's approval of the "
                          "quoted answer (confirmed_by_client=true, mode=quote_back)")
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
                 "--signature --sig-next, --signature --sig-answer ID TEXT, "
                 "--question-set.",
        "usage": "deck-intake-driver.py --run-dir <DIR> [--next | --answer "
                 "ID TEXT | --complete | --signature [--sig-next | --sig-answer "
                 "ID TEXT | --sig-record FILE] | --question-set]",
    }))
    return 2


if __name__ == "__main__":
    sys.exit(main())
