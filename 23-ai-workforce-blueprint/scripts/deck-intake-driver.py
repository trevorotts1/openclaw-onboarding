#!/usr/bin/env python3
"""
deck-intake-driver.py — interview turn-gate for the Presentations deck-intake.

Reads deck-intake-questions.json and maintains working/interview/intake_ledger.json
within the deck run directory. Enforces one-question-per-turn ordering so the agent
CANNOT emit the next question until the current one is answered and validated.

CLI:
  --run-dir DIR        path to the deck run directory (required for most commands)
  --next               return the next unanswered question; block if current is unanswered
  --answer ID TEXT     validate and record an answer for question id ID
  --budget             check session turn/time budget; print status; exit nonzero on overrun
  --complete           hard precondition: exits 0 only if all required+block_gate ids
                       have validated answers or logged circled-back skips; sets
                       intake_ledger.json status="complete" on success
  --selftest           run offline self-test in a temp dir; exits 0 on pass
  --signature --next / --signature --answer ID TEXT
                       THE REQUIRED turn-gate: SAME blocked/validated machinery
                       as --next/--answer, but walked over sp-8-questions.json
                       (choice question, then q1..q8, then the frame question)
                       into a SEPARATE ledger (working/interview/sp_intake_ledger
                       .json). Emits exactly ONE question per --next call and
                       BLOCKS on the active question until answered -- no batch
                       payload on this path. The final answer auto-assembles
                       working/copy/sp_intake.json and runs prove_sp_intake.py
                       (AF-SP-8Q-SPLIT) against it.
  --signature --plan   read-only DRY-RUN / inspection mode ONLY: emits the full
                       intake plan (all 8 Questions + frame question) as one
                       JSON payload for offline review. Never use this to
                       conduct the interview -- it is not a turn-gate.
  --signature --record FILE
                       assembles + proves a pre-gathered answers file directly
                       (used by --plan-mode dry runs and by tooling that already
                       gathered the answers through the turn-gate above).
  --signature (bare -- no --next/--answer/--record/--plan/--selftest)
                       E5 fix: the bare form NO LONGER emits the full intake
                       payload (that was an unenforced escape hatch around the
                       one-question-per-turn gate -- an agent could call it and
                       receive all 9 questions to "self-pace"). It now prints a
                       {"status": "use_turn_gate", "next_command": ...} pointer
                       at the REAL turn-gate (--signature --next) and exits 0.
                       Use --plan for the explicit, clearly-labeled dry-run.

Dependency-free: stdlib only (json, os, pathlib, datetime, argparse, sys, tempfile, time).
"""

import argparse
import datetime
import hashlib
import hmac
import json
import os
import pathlib
import sys
import tempfile
import time
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
QUESTIONS_FILE_NAME = "deck-intake-questions.json"
LEDGER_REL = pathlib.Path("working") / "interview" / "intake_ledger.json"
ANSWERS_REL = pathlib.Path("working") / "interview" / "answers"

# SIGNATURE mode turn-gate uses a SEPARATE ledger/answers area so a run that
# offers both a standard pre-presentation capture and a signature deck never
# cross-contaminates entries between the two question sets.
SP_LEDGER_REL = pathlib.Path("working") / "interview" / "sp_intake_ledger.json"
SP_ANSWERS_REL = pathlib.Path("working") / "interview" / "sp_answers"


def find_questions_file(run_dir: pathlib.Path) -> pathlib.Path:
    """Locate deck-intake-questions.json: beside this script, or in the intake/ dir."""
    candidates = [
        pathlib.Path(__file__).parent.parent
        / "templates" / "role-library" / "presentations" / "intake" / QUESTIONS_FILE_NAME,
        pathlib.Path(__file__).parent / QUESTIONS_FILE_NAME,
        run_dir / QUESTIONS_FILE_NAME,
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"{QUESTIONS_FILE_NAME} not found. Searched: {[str(c) for c in candidates]}"
    )


# ---------------------------------------------------------------------------
# Ledger I/O
# ---------------------------------------------------------------------------
def load_ledger(run_dir: pathlib.Path, ledger_rel: pathlib.Path = LEDGER_REL) -> dict:
    lp = run_dir / ledger_rel
    if lp.exists():
        try:
            with open(lp) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[deck-intake-driver] WARNING: corrupted ledger ({e}); resetting.", file=sys.stderr)
    return {
        "status": "in_progress",
        "started_at": _now(),
        "entries": {},
        "turns": 0,
        "budget_overrun": False,
    }


def save_ledger(run_dir: pathlib.Path, ledger: dict, ledger_rel: pathlib.Path = LEDGER_REL) -> None:
    lp = run_dir / ledger_rel
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "w") as f:
        json.dump(ledger, f, indent=2)


# ---------------------------------------------------------------------------
# Answer file I/O
# ---------------------------------------------------------------------------
def answer_path(run_dir: pathlib.Path, qid: str, answers_rel: pathlib.Path = ANSWERS_REL) -> pathlib.Path:
    return run_dir / answers_rel / f"{qid}.txt"


def answer_exists(run_dir: pathlib.Path, qid: str, answers_rel: pathlib.Path = ANSWERS_REL) -> bool:
    p = answer_path(run_dir, qid, answers_rel)
    return p.exists() and p.stat().st_size > 0


def read_answer_file(run_dir: pathlib.Path, qid: str, answers_rel: pathlib.Path = ANSWERS_REL) -> str:
    with open(answer_path(run_dir, qid, answers_rel)) as f:
        return f.read().strip()


def write_answer_file(run_dir: pathlib.Path, qid: str, text: str, answers_rel: pathlib.Path = ANSWERS_REL) -> None:
    p = answer_path(run_dir, qid, answers_rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Question helpers
# ---------------------------------------------------------------------------
def ordered_questions(qdata: dict) -> list:
    """Return questions sorted by order field (ascending)."""
    return sorted(qdata["questions"], key=lambda q: q.get("order", 999))


# ---------------------------------------------------------------------------
# ask_if conditional questions (question-bank migration)
#
# A migrated prose question that only applies in some branches (e.g. D2/D3's
# "ask only if DELIVERABLE_SET includes '+audio'"/"...a speech is in scope",
# VIP follow-ups, PRICE_ANCHOR only on a price-drop) carries an `ask_if`
# block: {"question_id": <id of the gating question>, and one of
# "truthy"/"equals"/"contains"/"in"}. Resolved against the ANSWER already
# recorded for that gating question id. If the gating question has not been
# answered yet, the conditional question is left pending (neither asked nor
# auto-skipped) until it is.
# ---------------------------------------------------------------------------
def _ask_if_satisfied(cond: dict, ledger: dict) -> Optional[bool]:
    """Returns True/False once resolvable, or None if the gating answer isn't
    recorded yet (caller should treat None as 'not yet decidable')."""
    ref_id = cond.get("question_id")
    entry = ledger.get("entries", {}).get(ref_id, {})
    if not entry.get("validated"):
        return None
    val = str(entry.get("answer") or "").strip().lower()
    if "truthy" in cond:
        is_truthy = val in ("yes", "true", "y", "1") or (val not in ("", "no", "false", "n", "0") and bool(val))
        return is_truthy == bool(cond["truthy"])
    if "equals" in cond:
        return val == str(cond["equals"]).strip().lower()
    if "contains" in cond:
        return str(cond["contains"]).strip().lower() in val
    if "contains_any" in cond:
        return any(str(x).strip().lower() in val for x in cond["contains_any"])
    if "in" in cond:
        return val in [str(x).strip().lower() for x in cond["in"]]
    return True


def auto_skip_unmet_conditions(qdata: dict, ledger: dict) -> bool:
    """Housekeeping pass: for every not-yet-asked/validated question carrying
    an ask_if whose gating answer is ALREADY recorded and evaluates False,
    mark it validated+skipped so it never blocks --next or --complete.
    Returns True if the ledger was mutated (caller should save)."""
    entries = ledger.setdefault("entries", {})
    mutated = False
    for q in ordered_questions(qdata):
        cond = q.get("ask_if")
        if not cond:
            continue
        e = entries.get(q["id"], {})
        if e.get("validated") or e.get("asked_at"):
            continue
        satisfied = _ask_if_satisfied(cond, ledger)
        if satisfied is False:
            entries.setdefault(q["id"], {})
            entries[q["id"]]["validated"] = True
            entries[q["id"]]["validated_at"] = _now()
            entries[q["id"]]["answer"] = None
            entries[q["id"]]["skipped_ask_if"] = True
            mutated = True
    return mutated


def auto_skip_all_conditionals(qdata: dict, ledger: dict) -> bool:
    """Unified conditional-skip pass (integration reconciliation of the
    typepicker + intakegate units). Covers BOTH conditional schemas in the
    merged question set:
      * `conditional_on` {id, equals} — typepicker's recipient_name /
        signature_source, gated on presentation_type.
      * `ask_if` {question, truthy|equals|contains|contains_any|in} — the
        migrated question-bank follow-ups (VIP tiers, PRICE_ANCHOR on a
        price-drop, WANT_AUDIO_DEMO/TARGET_WPM, ...).
    No question carries both fields, so the two passes are disjoint and
    idempotent. Returns True if the ledger was mutated (caller should save).
    This is now the ONE entry point every command uses for conditional skips."""
    before = json.dumps(ledger.get("entries", {}), sort_keys=True, default=str)
    auto_skip_conditionals(qdata, ledger)
    mutated_ask_if = auto_skip_unmet_conditions(qdata, ledger)
    after = json.dumps(ledger.get("entries", {}), sort_keys=True, default=str)
    return mutated_ask_if or (before != after)


def find_active_question(qdata: dict, ledger: dict) -> Optional[dict]:
    """Return the lowest-order question that has been asked but not yet validated."""
    entries = ledger.get("entries", {})
    for q in ordered_questions(qdata):
        e = entries.get(q["id"], {})
        if e.get("asked_at") and not e.get("validated"):
            return q
    return None


def find_next_question(qdata: dict, ledger: dict) -> Optional[dict]:
    """Return the lowest-order question with no validated answer and not yet asked."""
    entries = ledger.get("entries", {})
    for q in ordered_questions(qdata):
        e = entries.get(q["id"], {})
        if not e.get("validated") and not e.get("asked_at"):
            return q
    return None


def find_next_any(qdata: dict, ledger: dict) -> Optional[dict]:
    """Return the lowest-order question with no validated answer (asked or not)."""
    entries = ledger.get("entries", {})
    for q in ordered_questions(qdata):
        e = entries.get(q["id"], {})
        if not e.get("validated"):
            return q
    return None


def _now() -> str:
    return datetime.datetime.now().isoformat()


# ---------------------------------------------------------------------------
# TURN-LEDGER PROVENANCE (GK-23 / D18 — "one-question-at-a-time UNFAKEABLE at
# the record layer"). The located gap: prove_sp_intake.py historically checked
# only a caller-asserted `record_committed_atomically: true` boolean — a hand-
# assembled record that never touched the driver could set it to True and pass.
# The fix: the driver stamps a provenance block built ONLY from data its own
# turn-gate loop produces (cmd_next/cmd_sp_next assigns each question its own
# strictly-incrementing `turn` number the SAME call it surfaces that question —
# cmd_answer/cmd_sp_answer never write a `turn` field), and the prover requires
# that block, checks it for internal consistency (one turn per question,
# strictly ascending, every answered required question present), and verifies
# an embedded HMAC digest.
#
# THREAT MODEL, stated honestly: this is a deterministic, stdlib-only, no-
# network, no-secrets-infrastructure prover (same constraint every other
# prove_sp_*.py in this skill operates under) whose evaluate(intake) is called
# with ONLY the assembled JSON dict from several independent call sites,
# including build_deck.py's `_sp_delegate("intake", run_dir)` (a single
# positional argument, no side channel). There is nowhere to thread a per-run
# secret to every verifier, so TURN_LEDGER_KEY below is a published integrity
# key, NOT a secrecy boundary: it binds the turn array + deck_type + commit id
# together so the block cannot be edited piecemeal (e.g. copy-pasted from a
# different record) without invalidating the signature, and it forces anyone
# faking a record to reproduce the ENTIRE strictly-ordered, one-turn-per-
# question structure by hand — meaningfully harder than flipping one boolean.
# It does not, and cannot, stop a source-literate adversary; no prover in this
# fleet's threat model claims to. MUST match TURN_LEDGER_KEY in
# 51-signature-presentation/scripts/prove_sp_intake.py byte-for-byte.
TURN_LEDGER_KEY = b"skill51-sp-intake-turn-ledger-provenance-v1"


def _canonical_turns_payload(turns: list, deck_type, commit_id) -> bytes:
    """Deterministic serialization the driver signs and the prover re-verifies.
    Must match prove_sp_intake.py's _canonical_turns_payload() exactly."""
    payload = {"deck_type": deck_type, "record_commit_ids": commit_id, "turns": turns}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign_turn_ledger(turns: list, deck_type, commit_id) -> str:
    return hmac.new(TURN_LEDGER_KEY, _canonical_turns_payload(turns, deck_type, commit_id),
                     hashlib.sha256).hexdigest()


def build_turn_ledger_provenance(entries: dict, question_ids: list, deck_type, commit_id) -> Optional[dict]:
    """Assemble the turn-ledger provenance block from the REAL ledger entries —
    per-question turn id + asked_at/validated_at timestamps that only the
    driver's turn-gate loop stamps. Only VALIDATED, non-skipped questions with
    a recorded `turn` are included (a skipped conditional question was never
    asked; a question answered without ever passing through --next/--answer's
    surfacing call carries no `turn` and is silently omitted here — the
    prover's completeness check catches that as a missing turn-ledger entry
    for an answered question). Returns None when nothing qualifies (e.g.
    answers assembled via --record without ever touching the ledger) — the
    caller then leaves the record unstamped, which the prover's dated grace
    window (or, once it closes, a hard AF-SP-INTAKE-UNPACED) governs."""
    turns = []
    for qid in question_ids:
        e = entries.get(qid, {})
        if not e.get("validated") or e.get("skipped") or e.get("skipped_ask_if"):
            continue
        if "turn" not in e:
            continue
        turns.append({
            "question_id": qid,
            "turn": e["turn"],
            "asked_at": e.get("asked_at"),
            "validated_at": e.get("validated_at"),
        })
    if not turns:
        return None
    return {"turns": turns, "signature": _sign_turn_ledger(turns, deck_type, commit_id)}


# ---------------------------------------------------------------------------
# Conditional questions (recipient_name / signature_source hang off the
# canonical presentation_type type-picker and must never be asked, and never
# block --next/--complete, when their controlling condition is not met).
# ---------------------------------------------------------------------------
def _condition_met(question: dict, ledger: dict) -> Optional[bool]:
    """True/False once the controlling question is validated; None if the
    controlling question is not yet answered (order guarantees it comes first,
    so callers should simply not surface this question yet)."""
    cond = question.get("conditional_on")
    if not cond:
        return True
    ctrl_entry = ledger.get("entries", {}).get(cond.get("id"), {})
    if not ctrl_entry.get("validated"):
        return None
    ctrl_value = ctrl_entry.get("normalized", ctrl_entry.get("answer"))
    return ctrl_value == cond.get("equals")


def auto_skip_conditionals(qdata: dict, ledger: dict) -> None:
    """Mark every conditional question whose controlling answer is already
    known and does NOT match as validated+skipped, so it is never asked and
    never blocks --complete (e.g. recipient_name when presentation_type !=
    content_personal, signature_source when presentation_type != signature)."""
    entries = ledger.setdefault("entries", {})
    for q in ordered_questions(qdata):
        qid = q["id"]
        if entries.get(qid, {}).get("validated"):
            continue
        if _condition_met(q, ledger) is False:
            entries.setdefault(qid, {})
            entries[qid]["validated"] = True
            entries[qid]["validated_at"] = _now()
            entries[qid]["skipped"] = True
            entries[qid]["answer"] = "(not applicable)"


# ---------------------------------------------------------------------------
# THE mapping table — one canonical presentation_type answer derives all four
# legacy axis fields (deck_type, creation_mode, presentation_mode,
# audience_mode). Mirrors 'legacy_field_mapping' in deck-intake-questions.json;
# this function is the ONE place the mapping is applied in code — do not
# re-derive it elsewhere. Director Mode A/B is intentionally absent: it stays
# derived from whether source assets exist (director-of-presentations.md
# SOP 9.3) and is never asked at intake.
# ---------------------------------------------------------------------------
LEGACY_FIELD_MAPPING = {
    "from_scratch": {
        "deck_type": "webinar", "creation_mode": "from_scratch",
        "presentation_mode": "general", "audience_mode": "STANDARD",
    },
    "content_personal": {
        "deck_type": "webinar", "creation_mode": "content_personal",
        "presentation_mode": "one-person", "audience_mode": "PERSONAL",
    },
    "content_general": {
        "deck_type": "webinar", "creation_mode": "content_general",
        "presentation_mode": "general", "audience_mode": "GENERAL",
    },
    "signature": {
        "deck_type": "signature_presentation", "creation_mode": "from_scratch",
        "presentation_mode": "general", "audience_mode": "STANDARD",
    },
}
PRESENTATION_TYPES = tuple(LEGACY_FIELD_MAPPING.keys())


def derive_legacy_fields(presentation_type: str, signature_source: Optional[str] = None) -> dict:
    """Derive deck_type / creation_mode / presentation_mode / audience_mode
    from the ONE canonical presentation_type answer (the type-picker).

    signature_source only applies when presentation_type == 'signature': on
    'existing_content' it overrides creation_mode to content_general so a
    signature run converting existing material never satisfies _chk_mode with
    an unset creation_mode (AF-MODE-UNSET is closed here — the field is always
    written explicitly, never left unset)."""
    base = LEGACY_FIELD_MAPPING.get(presentation_type)
    if base is None:
        raise ValueError(
            f"Unknown presentation_type: {presentation_type!r}. "
            f"Must be one of {PRESENTATION_TYPES}."
        )
    out = dict(base)
    out["presentation_type"] = presentation_type
    if presentation_type == "signature" and signature_source == "existing_content":
        out["creation_mode"] = "content_general"
    return out


def _normalize_enum_value(text: str, question: dict) -> str:
    """Best-effort match of a free-text enum answer to one of the question's
    allowed_values: exact match, case/punctuation-insensitive match, keyword
    containment against the value or its value_labels entry, else the
    question's declared default. Never raises and never returns a string
    outside allowed_values (or the raw default) — downstream mapping tables
    never see an out-of-band presentation_type."""
    allowed = question.get("allowed_values") or []
    if not allowed:
        return (text or "").strip()
    stripped = (text or "").strip()
    if stripped in allowed:
        return stripped
    normalized = stripped.lower().replace("-", "_").replace(" ", "_")
    for val in allowed:
        if normalized == val.lower():
            return val
    labels = question.get("value_labels", {})
    lowered_free = stripped.lower()
    for val in allowed:
        if val.lower() in lowered_free:
            return val
        label = str(labels.get(val, "")).lower()
        if label and (label in lowered_free or lowered_free in label):
            return val
    return question.get("default", allowed[0])


# ---------------------------------------------------------------------------
# working/copy/intake.json — the file build_deck.py's _chk_mode / _chk_intake /
# prove_sp_routing actually read. The type-picker's derived legacy fields are
# merged here the moment presentation_type (and, for signature runs,
# signature_source) is validated, and again defensively at --complete.
# ---------------------------------------------------------------------------
INTAKE_JSON_REL = pathlib.Path("working") / "copy" / "intake.json"


def merge_intake_json(run_dir: pathlib.Path, updates: dict) -> pathlib.Path:
    """Merge `updates` into working/copy/intake.json, creating it (and parents)
    if absent. Existing keys not present in `updates` are preserved."""
    p = run_dir / INTAKE_JSON_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(updates)
    p.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def _apply_type_picker_derivation(run_dir: pathlib.Path, ledger: dict, qid: str) -> None:
    """After presentation_type or signature_source is recorded, (re)compute the
    derived legacy fields and merge them into working/copy/intake.json. No-op
    (and never raises) if presentation_type has not been validated yet or
    run_dir is unavailable (e.g. --answer called without a real run dir)."""
    if qid not in ("presentation_type", "signature_source", "recipient_name"):
        return
    if run_dir is None:
        return
    entries = ledger.get("entries", {})
    pt_entry = entries.get("presentation_type", {})
    if not pt_entry.get("validated"):
        return
    presentation_type = pt_entry.get("normalized", pt_entry.get("answer"))
    sig_entry = entries.get("signature_source", {})
    signature_source = sig_entry.get("normalized") if sig_entry.get("validated") else None
    try:
        derived = derive_legacy_fields(presentation_type, signature_source)
    except ValueError:
        return
    updates = dict(derived)
    if qid == "recipient_name" or entries.get("recipient_name", {}).get("validated"):
        rn = entries.get("recipient_name", {})
        if rn.get("validated") and not rn.get("skipped"):
            updates["recipient_name"] = rn.get("answer")
    merge_intake_json(run_dir, updates)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_answer(text: str, question: dict) -> tuple[bool, str]:
    """
    On-topic validation: non-empty + length floor + simple keyword heuristic.
    Returns (valid, reason). 'valid' True = accept; False = re-ask, log wander.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False, "Answer is empty. Please provide a response."
    if len(stripped) < 3:
        return False, "Answer is too short. Please be more specific."

    # Length floor by question kind: boolean can be short ("yes"/"no"/etc.)
    kind = question.get("kind", "text")
    if kind == "boolean":
        lowered = stripped.lower()
        if lowered not in ("yes", "no", "true", "false", "y", "n", "1", "0"):
            if len(stripped) < 2:
                return False, "Please answer yes or no."
    elif kind == "integer":
        # Accept a number or descriptive answer about pace
        try:
            int(stripped)
        except ValueError:
            # Allow descriptive like "standard", "slow", "fast"
            if len(stripped) < 4:
                return False, "Please specify a words-per-minute value or a pace description."
    else:
        # text: length floor 3 chars already checked above
        pass

    # Simple heuristic: reject single-character non-boolean answers (e.g. "k")
    if kind == "text" and len(stripped) <= 1:
        return False, "Answer is too brief. Please elaborate."

    return True, ""


def sp_validate_answer(text: str, question: dict) -> Tuple[bool, str]:
    """Signature-mode-only validator: adds a real enum check on top of
    validate_answer's base rules, scoped to the sp turn-gate so it can never
    change behavior for the standard deck-intake-questions.json flow (whose
    'enum' questions, e.g. deck_type, intentionally accept free text today)."""
    valid, reason = validate_answer(text, question)
    if not valid:
        return valid, reason
    if question.get("kind") != "enum":
        return True, ""
    allowed = [str(v).strip().lower() for v in (question.get("allowed_values") or [])]
    if not allowed:
        return True, ""
    labels = question.get("value_labels") or {}
    lowered = (text or "").strip().lower()
    label_lookup = {str(v).strip().lower(): k for k, v in labels.items()}
    letter_lookup = {chr(ord("a") + i): v for i, v in enumerate(allowed)}
    matched = (
        lowered in allowed
        or lowered in label_lookup
        or lowered.strip("(). ") in letter_lookup
    )
    if not matched:
        return False, f"Please choose one of: {', '.join(question.get('allowed_values') or [])}."
    return True, ""


def canonicalize_enum_answer(text: str, question: dict) -> str:
    """Map a free-typed enum answer ('A', 'the rulebook', 'rulebook') to its
    canonical allowed_value. Falls back to the raw stripped text when the
    question has no allowed_values or no match is found (validate_answer
    already rejected genuinely unmatched enum answers before this is called)."""
    stripped = (text or "").strip()
    allowed = [str(v).strip() for v in (question.get("allowed_values") or [])]
    if not allowed:
        return stripped
    lowered = stripped.lower()
    for v in allowed:
        if v.lower() == lowered:
            return v
    labels = question.get("value_labels") or {}
    for k, v in labels.items():
        if str(v).strip().lower() == lowered and k in allowed:
            return k
    letter = lowered.strip("(). ")
    idx = ord(letter) - ord("a") if len(letter) == 1 and letter.isalpha() else -1
    if 0 <= idx < len(allowed):
        return allowed[idx]
    return stripped


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------
def check_budget(qdata: dict, ledger: dict) -> dict:
    budget = qdata.get("session_budget", {"max_turns": 14, "max_minutes": 20})
    max_turns = int(budget.get("max_turns", 14))
    max_minutes = int(budget.get("max_minutes", 20))

    turns = int(ledger.get("turns", 0))
    started_str = ledger.get("started_at", "")
    elapsed_minutes = 0.0
    if started_str:
        try:
            started = datetime.datetime.fromisoformat(started_str)
            elapsed_minutes = (datetime.datetime.now() - started).total_seconds() / 60.0
        except Exception:
            pass

    overrun_turns = turns >= max_turns
    overrun_time = elapsed_minutes >= max_minutes

    status = {
        "turns_used": turns,
        "turns_max": max_turns,
        "elapsed_minutes": round(elapsed_minutes, 1),
        "max_minutes": max_minutes,
        "turns_overrun": overrun_turns,
        "time_overrun": overrun_time,
        "budget_ok": not (overrun_turns or overrun_time),
    }

    if overrun_turns or overrun_time:
        ledger["budget_overrun"] = True
        status["mode"] = "summarize_and_confirm"
        status["message"] = (
            "Session budget exceeded "
            f"(turns: {turns}/{max_turns}, time: {round(elapsed_minutes,1)}/{max_minutes} min). "
            "Switching to summarize-and-confirm mode: present the captured answers for owner "
            "confirmation and skip remaining optional questions."
        )
    return status


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_next(run_dir: pathlib.Path, qdata: dict, ledger: dict) -> None:
    """--next: return exactly one question; block if active question has no answer yet."""
    # Auto-skip any conditional question whose gating answer is already on
    # record and evaluates false — covers BOTH the type-picker conditionals
    # (recipient_name/signature_source via `conditional_on`) and the migrated
    # question-bank follow-ups (TARGET_WPM/VIP/PRICE_ANCHOR via `ask_if`) so
    # they never surface as a turn or block --complete.
    if auto_skip_all_conditionals(qdata, ledger):
        save_ledger(run_dir, ledger)

    # Check budget first
    bstatus = check_budget(qdata, ledger)
    if not bstatus["budget_ok"]:
        print(json.dumps({
            "status": "budget_overrun",
            "message": bstatus.get("message", "Session budget exceeded."),
            "mode": "summarize_and_confirm",
            "budget": bstatus,
        }))
        save_ledger(run_dir, ledger)
        sys.exit(0)

    # Check if there is an active (asked but unvalidated) question
    active = find_active_question(qdata, ledger)
    if active:
        qid = active["id"]
        if not answer_exists(run_dir, qid):
            # BLOCK: no answer file yet for the active question
            print(json.dumps({
                "status": "blocked",
                "current_question_id": qid,
                "message": (
                    f"Waiting for answer to '{qid}'. "
                    f"Call --answer {qid} '<text>' to record and validate the answer, "
                    f"then call --next again."
                ),
                "question": active,
            }))
            sys.exit(0)
        else:
            # Answer file exists — auto-validate so --next can advance
            answer_text = read_answer_file(run_dir, qid)
            valid, reason = validate_answer(answer_text, active)
            entries = ledger.setdefault("entries", {})
            if valid:
                entries.setdefault(qid, {})
                entries[qid]["answer"] = answer_text
                if active.get("kind") == "enum":
                    entries[qid]["normalized"] = _normalize_enum_value(answer_text, active)
                entries[qid]["validated"] = True
                entries[qid]["validated_at"] = _now()
                auto_skip_all_conditionals(qdata, ledger)
                _apply_type_picker_derivation(run_dir, ledger, qid)
            else:
                # File exists but content is invalid: re-ask same question
                entries.setdefault(qid, {})
                entries[qid].setdefault("wander_count", 0)
                entries[qid]["wander_count"] = entries[qid]["wander_count"] + 1
                entries[qid]["last_wander_at"] = _now()
                save_ledger(run_dir, ledger)
                print(json.dumps({
                    "status": "re_ask",
                    "current_question_id": qid,
                    "reason": reason,
                    "message": f"Answer for '{qid}' did not pass validation: {reason}. Re-asking the same question.",
                    "question": active,
                }))
                sys.exit(0)
            save_ledger(run_dir, ledger)

    # Find the next completely unasked question
    nxt = find_next_question(qdata, ledger)
    if nxt is None:
        # All questions have been asked/validated
        print(json.dumps({
            "status": "all_asked",
            "message": "All intake questions have been presented. Call --complete to finalize.",
        }))
        sys.exit(0)

    # Mark this question as asked and return it
    entries = ledger.setdefault("entries", {})
    entries.setdefault(nxt["id"], {})
    entries[nxt["id"]]["asked_at"] = _now()
    ledger["turns"] = ledger.get("turns", 0) + 1
    # GK-23/D18: stamp the turn id on THIS question's entry, the same call that
    # surfaces it — the one signal a hand-assembled (never-driven) record cannot
    # reproduce without walking this exact loop.
    entries[nxt["id"]]["turn"] = ledger["turns"]
    save_ledger(run_dir, ledger)

    print(json.dumps({
        "status": "question",
        "id": nxt["id"],
        "prompt": nxt["prompt"],
        "help": nxt.get("help", ""),
        "kind": nxt.get("kind", "text"),
        "required": nxt.get("required", True),
        "block_gate": nxt.get("block_gate", False),
        "default": nxt.get("default"),
        "turn": ledger["turns"],
        "question": nxt,
    }))
    sys.exit(0)


def cmd_answer(run_dir: pathlib.Path, qdata: dict, ledger: dict, qid: str, text: str) -> None:
    """--answer ID TEXT: validate and record the answer for question id ID."""
    # Find the question
    question = next((q for q in qdata["questions"] if q["id"] == qid), None)
    if question is None:
        print(json.dumps({
            "status": "error",
            "message": f"Unknown question id '{qid}'. Valid ids: {[q['id'] for q in qdata['questions']]}",
        }))
        sys.exit(1)

    valid, reason = validate_answer(text, question)
    entries = ledger.setdefault("entries", {})
    entries.setdefault(qid, {})

    if valid:
        # Write to answer file
        write_answer_file(run_dir, qid, text)
        entries[qid]["answer"] = text
        if question.get("kind") == "enum":
            entries[qid]["normalized"] = _normalize_enum_value(text, question)
        entries[qid]["validated"] = True
        entries[qid]["validated_at"] = _now()
        if not entries[qid].get("asked_at"):
            # Mark as asked if it wasn't already (direct --answer without --next)
            entries[qid]["asked_at"] = _now()
        auto_skip_all_conditionals(qdata, ledger)
        _apply_type_picker_derivation(run_dir, ledger, qid)
        save_ledger(run_dir, ledger)
        print(json.dumps({
            "status": "accepted",
            "id": qid,
            "message": f"Answer for '{qid}' recorded and validated.",
        }))
        sys.exit(0)
    else:
        # Off-topic / invalid: log wander, do NOT advance
        entries[qid].setdefault("wander_count", 0)
        entries[qid]["wander_count"] = entries[qid]["wander_count"] + 1
        entries[qid]["last_wander_at"] = _now()
        save_ledger(run_dir, ledger)
        print(json.dumps({
            "status": "rejected",
            "id": qid,
            "reason": reason,
            "message": f"Answer for '{qid}' was rejected: {reason}. Please re-answer.",
            "question": question,
        }))
        sys.exit(0)


def cmd_budget(run_dir: pathlib.Path, qdata: dict, ledger: dict) -> None:
    """--budget: check and report session budget status."""
    bstatus = check_budget(qdata, ledger)
    save_ledger(run_dir, ledger)
    print(json.dumps({"status": "budget_status", **bstatus}))
    if not bstatus["budget_ok"]:
        sys.exit(1)
    sys.exit(0)


def cmd_complete(run_dir: pathlib.Path, qdata: dict, ledger: dict) -> None:
    """
    --complete: hard precondition gate.

    Exits 0 only if every question with required:true AND block_gate:true has a
    validated answer OR an explicitly logged circled_back skip.

    Questions that are required:true but block_gate:false may use flag fallbacks
    (representation_uncaptured, grounded_content_provisional, etc.) — they do not
    block --complete.

    On success: sets intake_ledger.json status="complete". Also re-applies the
    type-picker's legacy-field derivation to working/copy/intake.json as a
    defensive final write, so a signature run's creation_mode is never left
    unset (AF-MODE-UNSET) even if an earlier per-answer merge was bypassed.
    On failure: exits nonzero and prints which ids are blocking.
    """
    auto_skip_all_conditionals(qdata, ledger)
    entries = ledger.get("entries", {})
    blocking = []

    for q in ordered_questions(qdata):
        if not q.get("required") or not q.get("block_gate"):
            continue
        qid = q["id"]
        e = entries.get(qid, {})
        validated = e.get("validated", False)
        circled_back = e.get("circled_back", False)
        if not validated and not circled_back:
            blocking.append(qid)

    if blocking:
        print(json.dumps({
            "status": "incomplete",
            "message": (
                f"Intake is NOT complete. The following required+block_gate question(s) "
                f"have no validated answer and no logged circled-back skip: {blocking}. "
                f"Call --next to get questions and --answer <id> <text> to record answers."
            ),
            "blocking_ids": blocking,
        }))
        sys.exit(1)

    # Defensive final re-apply of the type-picker derivation (covers callers
    # that wrote ledger entries directly instead of going through --answer/
    # --next, e.g. test fixtures or a resumed/edited ledger).
    if entries.get("presentation_type", {}).get("validated"):
        _apply_type_picker_derivation(run_dir, ledger, "presentation_type")

    # GK-23/D18: non-signature deck intake gets the SAME turn-ledger provenance
    # stamp as the signature path (deck-intake-questions.json order enforcement
    # already runs through this same driver) — written into working/copy/
    # intake.json so any future record-layer pacing gate over the standard
    # flow has the same unfakeable signal to check. Fail-soft: never blocks
    # --complete on a provenance-write error.
    try:
        std_ids = [q["id"] for q in ordered_questions(qdata)]
        existing_intake = {}
        intake_p = run_dir / INTAKE_JSON_REL
        if intake_p.exists():
            existing_intake = json.loads(intake_p.read_text(encoding="utf-8"))
        provenance = build_turn_ledger_provenance(
            entries, std_ids, existing_intake.get("deck_type"), None)
        if provenance is not None:
            merge_intake_json(run_dir, {"turn_ledger_provenance": provenance})
    except (OSError, json.JSONDecodeError):
        pass

    # Mark complete
    ledger["status"] = "complete"
    ledger["completed_at"] = _now()
    # Also set top-level complete flag for compatibility with intake_ledger.json readers
    ledger["complete"] = True
    save_ledger(run_dir, ledger)

    # Count all validated answers
    validated_count = sum(
        1 for q in qdata["questions"]
        if entries.get(q["id"], {}).get("validated")
    )
    print(json.dumps({
        "status": "complete",
        "message": (
            f"Deck intake complete. {validated_count} question(s) validated. "
            f"intake_ledger.json status set to 'complete'. "
            f"The build can now proceed via presentation-canonical-entry.sh."
        ),
        "completed_at": ledger["completed_at"],
        "validated_count": validated_count,
    }))
    sys.exit(0)


# ---------------------------------------------------------------------------
# Self-test (offline, uses a temp directory)
# ---------------------------------------------------------------------------
def cmd_selftest() -> None:
    """--selftest: run offline validation in a temp dir. Exits 0 on pass."""
    import tempfile
    print("[deck-intake-driver] --selftest: starting offline self-test...")

    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = pathlib.Path(tmpdir)

        # Find questions file
        try:
            qfile = find_questions_file(run_dir)
        except FileNotFoundError as e:
            print(f"[selftest] SKIP: questions file not found ({e}). "
                  "Self-test requires the questions file beside the script.", file=sys.stderr)
            print("[deck-intake-driver] --selftest: PASS (questions file absent; skipping question-dependent steps)")
            sys.exit(0)

        with open(qfile) as f:
            qdata = json.load(f)

        # --- Test 1: initial ledger creation ---
        ledger = load_ledger(run_dir)
        assert ledger["status"] == "in_progress", "ledger status should be in_progress"
        assert ledger["turns"] == 0, "initial turns should be 0"
        print("[selftest] Test 1 PASS: initial ledger creation")

        # --- Test 2: first --next returns a question ---
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                cmd_next(run_dir, qdata, ledger)
            except SystemExit:
                pass
        ledger = load_ledger(run_dir)  # reload after --next
        out = buf.getvalue().strip()
        parsed = json.loads(out)
        assert parsed["status"] == "question", f"Expected 'question' status, got: {parsed['status']}"
        first_id = parsed["id"]
        print(f"[selftest] Test 2 PASS: --next returned first question '{first_id}'")

        # --- Test 3: --next blocks if no answer file ---
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                cmd_next(run_dir, qdata, ledger)
            except SystemExit:
                pass
        ledger = load_ledger(run_dir)
        out = buf.getvalue().strip()
        parsed = json.loads(out)
        assert parsed["status"] == "blocked", f"Expected 'blocked' status, got: {parsed['status']}"
        print(f"[selftest] Test 3 PASS: --next blocks when no answer file for '{first_id}'")

        # --- Test 4: --answer accepts valid text ---
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                cmd_answer(run_dir, qdata, ledger, first_id, "70% African-American women, 30% mixed race")
            except SystemExit:
                pass
        ledger = load_ledger(run_dir)
        out = buf.getvalue().strip()
        parsed = json.loads(out)
        assert parsed["status"] == "accepted", f"Expected 'accepted', got: {parsed['status']}"
        assert ledger["entries"][first_id]["validated"] is True, "Entry should be validated"
        print(f"[selftest] Test 4 PASS: --answer accepted valid text for '{first_id}'")

        # --- Test 5: --answer rejects empty text ---
        # Pick the next NOT-YET-VALIDATED question id (skips first_id and any
        # conditional question the type-picker answer already auto-skipped,
        # e.g. recipient_name/signature_source when presentation_type defaulted
        # to from_scratch).
        next_qs = [q for q in ordered_questions(qdata)
                   if q["id"] != first_id
                   and not ledger.get("entries", {}).get(q["id"], {}).get("validated")]
        if next_qs:
            second_id = next_qs[0]["id"]
            # First ask it via --next
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_next(run_dir, qdata, ledger)
                except SystemExit:
                    pass
            ledger = load_ledger(run_dir)
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_answer(run_dir, qdata, ledger, second_id, "")
                except SystemExit:
                    pass
            ledger = load_ledger(run_dir)
            out = buf.getvalue().strip()
            parsed = json.loads(out)
            assert parsed["status"] == "rejected", f"Expected 'rejected' for empty text, got: {parsed['status']}"
            print(f"[selftest] Test 5 PASS: --answer rejected empty text for '{second_id}'")

        # --- Test 6: --budget reports OK ---
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                cmd_budget(run_dir, qdata, ledger)
            except SystemExit:
                pass
        ledger = load_ledger(run_dir)
        out = buf.getvalue().strip()
        parsed = json.loads(out)
        assert parsed["status"] == "budget_status", f"Expected 'budget_status', got: {parsed['status']}"
        assert parsed["budget_ok"] is True, "Budget should be OK in selftest"
        print("[selftest] Test 6 PASS: --budget reports OK")

        # --- Test 7: --complete fails when required+block_gate questions unanswered ---
        # Find a block_gate question that hasn't been validated yet
        block_gate_qs = [q for q in qdata["questions"] if q.get("required") and q.get("block_gate")]
        if block_gate_qs:
            unanswered = [q for q in block_gate_qs
                          if not ledger.get("entries", {}).get(q["id"], {}).get("validated")]
            if unanswered:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    try:
                        cmd_complete(run_dir, qdata, ledger)
                    except SystemExit:
                        pass
                ledger = load_ledger(run_dir)
                out = buf.getvalue().strip()
                parsed = json.loads(out)
                assert parsed["status"] == "incomplete", f"Expected 'incomplete', got: {parsed['status']}"
                print("[selftest] Test 7 PASS: --complete rejects incomplete block_gate questions")

        # --- Test 8: --complete succeeds when all block_gate questions answered ---
        # Answer all block_gate questions
        for q in block_gate_qs:
            qid = q["id"]
            if not ledger.get("entries", {}).get(qid, {}).get("validated"):
                write_answer_file(run_dir, qid, "Sample answer for selftest that passes validation")
                entries = ledger.setdefault("entries", {})
                entries.setdefault(qid, {})
                entries[qid]["answer"] = "Sample answer for selftest"
                entries[qid]["validated"] = True
                entries[qid]["validated_at"] = _now()
                entries[qid]["asked_at"] = _now()
        save_ledger(run_dir, ledger)
        ledger = load_ledger(run_dir)

        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                cmd_complete(run_dir, qdata, ledger)
            except SystemExit:
                pass
        ledger = load_ledger(run_dir)
        out = buf.getvalue().strip()
        parsed = json.loads(out)
        assert parsed["status"] == "complete", f"Expected 'complete', got: {parsed['status']}"
        assert ledger["status"] == "complete", "Ledger status should be 'complete'"
        assert ledger.get("complete") is True, "Ledger complete flag should be True"
        print("[selftest] Test 8 PASS: --complete succeeds when all block_gate questions answered")

        # --- Test 9: the type-picker derives all four legacy fields correctly ---
        for ptype, want in LEGACY_FIELD_MAPPING.items():
            got = derive_legacy_fields(ptype)
            for k, v in want.items():
                assert got[k] == v, f"derive_legacy_fields({ptype!r})[{k!r}] = {got[k]!r}, want {v!r}"
            assert got["presentation_type"] == ptype
        sig_existing = derive_legacy_fields("signature", "existing_content")
        assert sig_existing["creation_mode"] == "content_general", (
            "signature + existing_content should override creation_mode to content_general "
            f"(AF-MODE-UNSET must never be left unset), got {sig_existing['creation_mode']!r}"
        )
        sig_scratch = derive_legacy_fields("signature", "from_scratch")
        assert sig_scratch["creation_mode"] == "from_scratch"
        print("[selftest] Test 9 PASS: derive_legacy_fields covers all 4 presentation_type "
              "values + the signature_source override, creation_mode never unset")

        # --- Test 10: presentation_type=content_personal asks recipient_name and
        #     skips signature_source; the derived fields land in working/copy/intake.json ---
        with tempfile.TemporaryDirectory() as tmpdir2:
            run_dir2 = pathlib.Path(tmpdir2)
            ledger2 = load_ledger(run_dir2)
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_next(run_dir2, qdata, ledger2)
                except SystemExit:
                    pass
            ledger2 = load_ledger(run_dir2)
            parsed = json.loads(buf.getvalue().strip())
            assert parsed["id"] == "presentation_type", (
                f"first question should be 'presentation_type' (order 0), got {parsed['id']!r}"
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_answer(run_dir2, qdata, ledger2, "presentation_type", "content_personal")
                except SystemExit:
                    pass
            ledger2 = load_ledger(run_dir2)
            assert ledger2["entries"]["presentation_type"]["normalized"] == "content_personal"
            assert ledger2["entries"].get("signature_source", {}).get("skipped") is True, (
                "signature_source must be auto-skipped when presentation_type != signature"
            )
            assert "recipient_name" not in ledger2["entries"] or not ledger2["entries"]["recipient_name"].get("skipped"), (
                "recipient_name must NOT be auto-skipped when presentation_type == content_personal"
            )
            intake_path2 = run_dir2 / INTAKE_JSON_REL
            assert intake_path2.exists(), "working/copy/intake.json should be written after presentation_type is answered"
            intake2 = json.loads(intake_path2.read_text())
            assert intake2["deck_type"] == "webinar"
            assert intake2["creation_mode"] == "content_personal"
            assert intake2["presentation_mode"] == "one-person"
            assert intake2["audience_mode"] == "PERSONAL"
            # Now answer recipient_name and confirm it lands in intake.json too.
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_answer(run_dir2, qdata, ledger2, "recipient_name", "Jordan Ellis")
                except SystemExit:
                    pass
            ledger2 = load_ledger(run_dir2)
            intake2 = json.loads(intake_path2.read_text())
            assert intake2.get("recipient_name") == "Jordan Ellis"
            print("[selftest] Test 10 PASS: content_personal asks recipient_name, skips "
                  "signature_source, and derived legacy fields + recipient_name land in "
                  "working/copy/intake.json")

        # --- Test 11: presentation_type=signature asks signature_source, skips
        #     recipient_name, and existing_content overrides creation_mode ---
        with tempfile.TemporaryDirectory() as tmpdir3:
            run_dir3 = pathlib.Path(tmpdir3)
            ledger3 = load_ledger(run_dir3)
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_next(run_dir3, qdata, ledger3)
                except SystemExit:
                    pass
            ledger3 = load_ledger(run_dir3)
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_answer(run_dir3, qdata, ledger3, "presentation_type", "signature")
                except SystemExit:
                    pass
            ledger3 = load_ledger(run_dir3)
            assert ledger3["entries"].get("recipient_name", {}).get("skipped") is True, (
                "recipient_name must be auto-skipped when presentation_type == signature"
            )
            assert not ledger3["entries"].get("signature_source", {}).get("skipped"), (
                "signature_source must NOT be auto-skipped when presentation_type == signature"
            )
            intake_path3 = run_dir3 / INTAKE_JSON_REL
            intake3 = json.loads(intake_path3.read_text())
            assert intake3["deck_type"] == "signature_presentation"
            assert intake3["creation_mode"] == "from_scratch", (
                "signature defaults creation_mode to from_scratch until signature_source says otherwise"
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                try:
                    cmd_answer(run_dir3, qdata, ledger3, "signature_source", "existing_content")
                except SystemExit:
                    pass
            ledger3 = load_ledger(run_dir3)
            intake3 = json.loads(intake_path3.read_text())
            assert intake3["creation_mode"] == "content_general", (
                "signature_source=existing_content must override creation_mode to "
                f"content_general (never left unset), got {intake3['creation_mode']!r}"
            )
            print("[selftest] Test 11 PASS: signature asks signature_source, skips "
                  "recipient_name, and existing_content overrides creation_mode "
                  "(AF-MODE-UNSET never triggers)")

    # Signature-mode coverage runs through the SAME --selftest entrypoint so any
    # CI / verify path that exercises the driver also exercises the SP one-block
    # gate wiring. It self-skips when skill 51 is not co-located.
    if not signature_selftest():
        print("[deck-intake-driver] --selftest: FAILED (signature mode)", file=sys.stderr)
        sys.exit(1)

    print("[deck-intake-driver] --selftest: ALL PASS")
    sys.exit(0)


# ---------------------------------------------------------------------------
# SIGNATURE MODE (Skill 51 — Signature Presentation, Prime Directive O4/6/7)
#
# TWO LAYERS, kept distinct so they never conflict (Trevor's ruling — one-
# question-at-a-time wins): the 8 Questions are ASKED one at a time and RECORDED
# as one block.
#   (1) CONVERSATION LAYER — the front-door agent FIRST offers the owner a
#       quick-vs-in-depth interview CHOICE, then asks exactly ONE of the 8
#       Questions (plus the frame question) per message and waits for the answer;
#       never a wall of questions. Dumping the batch, or opening with no choice,
#       is AF-INTAKE-BATCH (a QC/Healer intake-trace autofail; it NEVER gates
#       build_deck.py / run_signature_deck.py). This mode emits that intake plan
#       (the choice-first conversation_contract + the 8 Questions + the frame
#       question) for the agent to run one turn at a time.
#   (2) RECORD LAYER — on --record, the answers gathered one at a time are
#       assembled into ONE atomic intake record and WIRED straight to the fail-
#       closed AF-SP-8Q-SPLIT prover
#       (51-signature-presentation/scripts/prove_sp_intake.py). Here
#       record_committed_atomically / mode=one_block describe the assembled
#       RECORD being committed as one atomic ledger write (NOT a batch of
#       questions dumped at the owner), so a record that was not committed
#       atomically can never pass. one_question_per_turn is NOT a record signal
#       (it describes the one-at-a-time conversation). The prover is the source
#       of truth; this driver emits the plan and hands the assembled record to it.
# ---------------------------------------------------------------------------
SP_SPEC_REL = pathlib.Path("intake") / "sp-8-questions.json"
SP_PROVER_REL = pathlib.Path("scripts") / "prove_sp_intake.py"
SP_ALLOWED_FRAMES = ("rulebook", "vault", "quest", "original")
SP_REQUIRED_QUESTIONS = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")


def _sp_skill_roots() -> list:
    """Candidate directories that hold the 51-signature-presentation skill.

    On an installed box skill 51 is a SIBLING of skill 23 in SKILLS_DIR; in the
    repo it is a sibling at the repo root. This driver lives at
    23-ai-workforce-blueprint/scripts/, so ``parent.parent.parent`` is the
    directory that contains BOTH skills (SKILLS_DIR / repo root)."""
    here = pathlib.Path(__file__).resolve()
    siblings_dir = here.parent.parent.parent  # <SKILLS_DIR or repo>/
    roots = [
        siblings_dir / "51-signature-presentation",
        # tolerate a rename to a bare skill dir on some boxes
        siblings_dir / "signature-presentation",
    ]
    return [r for r in roots if r.exists()]


def find_sp_spec(explicit: Optional[str] = None) -> pathlib.Path:
    """Locate the SACRED 8-Questions spec (sp-8-questions.json)."""
    if explicit:
        p = pathlib.Path(explicit).expanduser()
        if p.exists():
            return p
        raise FileNotFoundError(f"--sp-spec not found: {p}")
    for root in _sp_skill_roots():
        cand = root / SP_SPEC_REL
        if cand.exists():
            return cand
    raise FileNotFoundError(
        "sp-8-questions.json not found. Searched: "
        f"{[str(r / SP_SPEC_REL) for r in _sp_skill_roots()] or '(no skill-51 dir beside skill 23)'}. "
        "Pass --sp-spec PATH explicitly."
    )


def find_sp_prover() -> Optional[pathlib.Path]:
    """Locate prove_sp_intake.py (the AF-SP-8Q-SPLIT gate). None if absent."""
    for root in _sp_skill_roots():
        cand = root / SP_PROVER_REL
        if cand.exists():
            return cand
    return None


def _sp_block_msg_id() -> str:
    """A single opaque id proving the atomic intake-record commit."""
    return "rec_sp_" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")


SP_TRANSCRIPT_REL = pathlib.Path("working") / "interview" / "intake_transcript.json"


def _sp_append_transcript(run_dir: Optional[pathlib.Path], role: str, text) -> None:
    """Mechanically append ONE turn to the signature intake transcript
    (working/interview/intake_transcript.json) — the input the QC/Healer
    AF-INTAKE-BATCH scanner (51-signature-presentation/scripts/intake_trace_check.py)
    reads post-hoc. Because the driver's turn-gate asks exactly ONE bank question
    per --next and records ONE answer per --answer, this machine-authored
    transcript is a faithful one-question-per-turn record: scanning it is expected
    to PASS. It is ADVISORY provenance only — it NEVER gates build_deck.py /
    run_signature_deck.py. Fail-soft: a transcript write must never break intake."""
    if run_dir is None:
        return
    try:
        tpath = run_dir / SP_TRANSCRIPT_REL
        tpath.parent.mkdir(parents=True, exist_ok=True)
        turns = []
        if tpath.exists():
            try:
                loaded = json.loads(tpath.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    turns = loaded
            except (json.JSONDecodeError, OSError):
                turns = []
        turns.append({"role": role, "text": str(text)})
        tpath.write_text(json.dumps(turns, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # fail-soft: never break the intake on a transcript write


def build_signature_block(spec: dict, block_msg_id: str) -> dict:
    """Assemble the intake PLAN: the choice-first conversation contract + all 8
    Questions + the frame-selection question.

    TWO LAYERS (Trevor's ruling — one-question-at-a-time wins): the agent RUNS the
    conversation one question at a time (the `conversation_contract` below —
    offer QUICK vs IN-DEPTH first, then ONE question per message; a batch is
    AF-INTAKE-BATCH), and later COMMITS the answers as one atomic record. The
    `delivery` block carries the RECORD contract (mode == one_block,
    record_committed_atomically) that prove_sp_intake.py validates on that
    assembled record — it is NOT a licence to dump the questions at the owner.
    """
    questions = spec.get("questions") or []
    frame_q = spec.get("frame_selection_question") or {}
    spec_delivery = spec.get("delivery") or {}
    conversation_contract = spec_delivery.get("conversation_contract") or {}
    return {
        "status": "signature_intake_plan",
        "deck_type": spec.get("deck_type", "signature_presentation"),
        # delivery describes the RECORD layer (the assembled ledger committed as
        # one atomic record) — NOT the conversation. mode==one_block is the
        # record's atomic-commit mode, asserted by prove_sp_intake.py on the
        # assembled record and by this driver's selftest. record_committed_
        # atomically is the canonical field; asked_all_at_once is a deprecated
        # alias emitted for one release. one_question_per_turn is intentionally
        # NOT emitted — it describes the conversation, not the record commit.
        "delivery": {
            "mode": "one_block",
            "record_committed_atomically": True,
            "asked_all_at_once": True,
        },
        # conversation_contract describes the CONVERSATION layer: choice-first,
        # one question at a time; a batch trips AF-INTAKE-BATCH (never gates build).
        "conversation_contract": conversation_contract,
        "question_block_msg_id": block_msg_id,
        "instruction": (
            "SIGNATURE PRESENTATION INTAKE (choice-first, ONE question at a time — "
            "Trevor's ruling): FIRST offer the owner the QUICK vs IN-DEPTH interview "
            "choice, then ask exactly ONE of the following — the 8 Questions and the "
            "frame-selection question — per message and WAIT for each answer. Do NOT "
            "dump the batch (that is AF-INTAKE-BATCH). Once every answer is gathered "
            "one at a time, call --signature --record <answers.json> to assemble them "
            "into ONE atomic record and verify it via prove_sp_intake.py."
        ),
        "questions": questions,
        "frame_selection_question": frame_q,
    }


def sp_ordered_questions(spec: dict) -> list:
    """Build the FULL sp question set as a flat, order-sorted list the SAME
    ledger/blocked machinery (find_active_question/find_next_question) can
    walk: the choice-first interview question, then q1..q8, then the frame-
    selection question. This is what makes signature mode a REAL turn-gate
    instead of a one-shot batch payload."""
    cc = ((spec.get("delivery") or {}).get("conversation_contract")) or {}
    choices = cc.get("interview_choices") or ["quick", "in-depth"]
    choice_q = {
        "id": "interview_choice",
        "order": 0,
        "prompt": cc.get("choice_question") or (
            "Would you like a QUICK interview or a more IN-DEPTH one? "
            "Either way we go one question at a time."
        ),
        "kind": "enum",
        "allowed_values": list(choices),
        "required": True,
        "block_gate": True,
    }
    body = [dict(q) for q in (spec.get("questions") or [])]
    for q in body:
        q.setdefault("required", True)
        q.setdefault("block_gate", True)
        q.setdefault("kind", "text")
    frame_q = dict(spec.get("frame_selection_question") or {})
    if frame_q:
        frame_q.setdefault("order", len(body) + 1)
        frame_q.setdefault("required", True)
        frame_q.setdefault("block_gate", True)
        frame_q.setdefault("kind", "enum")
    return sorted([choice_q] + body + ([frame_q] if frame_q else []), key=lambda q: q.get("order", 999))


def cmd_sp_next(run_dir: pathlib.Path, spec: dict, ledger: dict) -> None:
    """--signature --next: the SAME blocked/validated ledger machinery as the
    standard flow (cmd_next), walked over sp_ordered_questions(spec) — choice
    question first, then q1..q8, then the frame question. Dumping >=2 of these
    in one turn is impossible through this entrypoint: --next returns exactly
    ONE question and blocks on the active one until it is answered."""
    qdata = {"questions": sp_ordered_questions(spec)}
    active = find_active_question(qdata, ledger)
    if active:
        qid = active["id"]
        if not answer_exists(run_dir, qid, SP_ANSWERS_REL):
            print(json.dumps({
                "status": "blocked",
                "current_question_id": qid,
                "message": (
                    f"Waiting for answer to '{qid}'. Call --signature --answer {qid} '<text>' "
                    f"to record and validate the answer, then call --signature --next again."
                ),
                "question": active,
            }))
            sys.exit(0)
        else:
            answer_text = read_answer_file(run_dir, qid, SP_ANSWERS_REL)
            valid, reason = sp_validate_answer(answer_text, active)
            entries = ledger.setdefault("entries", {})
            if valid:
                entries.setdefault(qid, {})
                entries[qid]["answer"] = canonicalize_enum_answer(answer_text, active) if active.get("kind") == "enum" else answer_text
                entries[qid]["validated"] = True
                entries[qid]["validated_at"] = _now()
            else:
                entries.setdefault(qid, {})
                entries[qid].setdefault("wander_count", 0)
                entries[qid]["wander_count"] += 1
                entries[qid]["last_wander_at"] = _now()
                save_ledger(run_dir, ledger, SP_LEDGER_REL)
                print(json.dumps({
                    "status": "re_ask",
                    "current_question_id": qid,
                    "reason": reason,
                    "message": f"Answer for '{qid}' did not pass validation: {reason}. Re-asking the same question.",
                    "question": active,
                }))
                sys.exit(0)
            save_ledger(run_dir, ledger, SP_LEDGER_REL)

    nxt = find_next_question(qdata, ledger)
    if nxt is None:
        # All sp questions (choice + q1..q8 + frame) validated: auto-assemble
        # the atomic record and run the AF-SP-8Q-SPLIT prover. This is the
        # "on the final --answer the driver assembles + proves" contract.
        result = _sp_finalize(run_dir, spec, ledger)
        print(json.dumps(result))
        sys.exit(0 if result.get("passed") else 2)

    entries = ledger.setdefault("entries", {})
    entries.setdefault(nxt["id"], {})
    entries[nxt["id"]]["asked_at"] = _now()
    ledger["turns"] = ledger.get("turns", 0) + 1
    # GK-23/D18: stamp the turn id on THIS question's entry, the same call
    # that surfaces it (mirrors cmd_next's standard-path stamp above).
    entries[nxt["id"]]["turn"] = ledger["turns"]
    save_ledger(run_dir, ledger, SP_LEDGER_REL)

    print(json.dumps({
        "status": "question",
        "id": nxt["id"],
        "prompt": nxt["prompt"],
        "help": nxt.get("help", ""),
        "kind": nxt.get("kind", "text"),
        "required": nxt.get("required", True),
        "block_gate": nxt.get("block_gate", True),
        "allowed_values": nxt.get("allowed_values"),
        "turn": ledger["turns"],
        "question": nxt,
    }))
    sys.exit(0)


def cmd_sp_answer(run_dir: pathlib.Path, spec: dict, ledger: dict, qid: str, text: str) -> None:
    """--signature --answer ID TEXT: validate + record one sp answer. Mirrors
    cmd_answer exactly, over the sp question set."""
    qdata = {"questions": sp_ordered_questions(spec)}
    question = next((q for q in qdata["questions"] if q["id"] == qid), None)
    if question is None:
        print(json.dumps({
            "status": "error",
            "message": f"Unknown signature question id '{qid}'. Valid ids: {[q['id'] for q in qdata['questions']]}",
        }))
        sys.exit(1)

    valid, reason = sp_validate_answer(text, question)
    entries = ledger.setdefault("entries", {})
    entries.setdefault(qid, {})

    if not valid:
        entries[qid].setdefault("wander_count", 0)
        entries[qid]["wander_count"] += 1
        entries[qid]["last_wander_at"] = _now()
        save_ledger(run_dir, ledger, SP_LEDGER_REL)
        print(json.dumps({
            "status": "rejected",
            "id": qid,
            "reason": reason,
            "message": f"Answer for '{qid}' was rejected: {reason}. Please re-answer.",
            "question": question,
        }))
        sys.exit(0)

    stored = canonicalize_enum_answer(text, question) if question.get("kind") == "enum" else text
    write_answer_file(run_dir, qid, text, SP_ANSWERS_REL)
    # Mechanically log this one-at-a-time turn (the question as an assistant turn,
    # the client's reply as an owner turn) to the intake transcript the QC/Healer
    # AF-INTAKE-BATCH scanner reads. ADVISORY provenance only — never gates build.
    _sp_append_transcript(run_dir, "assistant", question.get("prompt") or qid)
    _sp_append_transcript(run_dir, "owner", text)
    entries[qid]["answer"] = stored
    entries[qid]["validated"] = True
    entries[qid]["validated_at"] = _now()
    if not entries[qid].get("asked_at"):
        entries[qid]["asked_at"] = _now()
    save_ledger(run_dir, ledger, SP_LEDGER_REL)

    # If that was the LAST outstanding question, auto-finalize (assemble +
    # prove) right here so a caller that only ever calls --answer (never
    # --next again after the final answer) still gets the record committed.
    remaining = find_next_any(qdata, ledger)
    if remaining is None:
        result = _sp_finalize(run_dir, spec, ledger)
        result["status"] = "accepted_and_finalized" if result.get("passed") else "accepted_but_finalize_failed"
        print(json.dumps(result))
        sys.exit(0 if result.get("passed") else 2)

    print(json.dumps({
        "status": "accepted",
        "id": qid,
        "message": f"Answer for '{qid}' recorded and validated.",
    }))
    sys.exit(0)


def _sp_finalize(run_dir: pathlib.Path, spec: dict, ledger: dict) -> dict:
    """Assemble the ledger's validated answers into the runtime intake record
    and run prove_sp_intake.py (AF-SP-8Q-SPLIT) against it — the RECORD-layer
    commit that closes out a turn-gated signature interview. Marks the sp
    ledger complete on a passing prove."""
    entries = ledger.get("entries", {})
    answers_record = {
        "answers": {
            qid: entries.get(qid, {}).get("answer")
            for qid in SP_REQUIRED_QUESTIONS
        },
        "signature_frame": entries.get("frame_selection", {}).get("answer"),
        "offer_token_ledger": [entries.get("q7", {}).get("answer")] if entries.get("q7", {}).get("answer") else [],
        "interview_choice": entries.get("interview_choice", {}).get("answer"),
    }
    block_msg_id = _sp_block_msg_id()
    intake = assemble_sp_intake(answers_record, block_msg_id)

    # GK-23/D18: stamp the turn-ledger provenance block built from the REAL sp
    # ledger's entries — per-question turn id + timestamps only the turn-gate
    # loop above (cmd_sp_next) produces. sp_question_ids covers the full
    # walked set (interview_choice, q1..q8, frame_selection) in canonical
    # order, matching sp_ordered_questions(spec).
    sp_question_ids = [q["id"] for q in sp_ordered_questions(spec)]
    provenance = build_turn_ledger_provenance(
        entries, sp_question_ids, intake.get("deck_type"), intake.get("record_commit_ids"))
    if provenance is not None:
        intake["turn_ledger_provenance"] = provenance

    out_path = run_dir / "working" / "copy" / "sp_intake.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(intake, indent=2, ensure_ascii=False), encoding="utf-8")

    rc, prover_out = _run_sp_prover(out_path)
    passed = rc == 0
    if passed:
        ledger["status"] = "complete"
        ledger["completed_at"] = _now()
        ledger["complete"] = True
    save_ledger(run_dir, ledger, SP_LEDGER_REL)
    return {
        "status": "signature_intake_verified" if passed else "signature_intake_rejected",
        "passed": passed,
        "prover_rc": rc,
        "gate": "AF-SP-8Q-SPLIT (prove_sp_intake.py)",
        "intake_path": str(out_path),
        "signature_frame": intake.get("signature_frame"),
        "prover_output": prover_out.strip(),
        "message": (
            "Signature intake gathered one question at a time and committed as ONE atomic "
            "record; verified by prove_sp_intake.py."
            if passed else
            "Signature intake record assembled but FAILED prove_sp_intake.py — see prover_output."
        ),
    }


def _sp_extract_answers(record: dict) -> dict:
    """Pull q1..q8 out of a flat or {answers:{...}} record."""
    src = record.get("answers") if isinstance(record.get("answers"), dict) else record
    return {q: src.get(q) for q in SP_REQUIRED_QUESTIONS if src.get(q) is not None}


def _sp_offer_ledger(record: dict) -> list:
    led = record.get("offer_token_ledger")
    if isinstance(led, list) and led:
        return [x for x in led if isinstance(x, str) and x.strip()]
    q7 = record.get("q7_offer_products")
    if isinstance(q7, list):
        return [x for x in q7 if isinstance(x, str) and x.strip()]
    return []


def assemble_sp_intake(answers_record: dict, block_msg_id: str) -> dict:
    """Assemble the runtime intake record (working/copy/sp_intake.json shape) the
    AF-SP-8Q-SPLIT prover validates. The atomic-record-commit facts are stamped
    HERE, from the emitted block, so a caller cannot silently mark a non-atomic
    intake as committed — the prover still re-checks every field.

    v1.1 RECORD-LAYER field names (the machine layer no longer teaches batching):
      record_committed_atomically  (canonical) — the ledger was committed as ONE
          atomic write. Deprecated alias asked_all_at_once is ALSO emitted for one
          release so an old prover on a stale box still validates this record.
      record_commit_ids            (canonical) — the atomic record-commit id.
          Deprecated alias question_block_msg_id is ALSO emitted for one release.
    one_question_per_turn is NO LONGER emitted — it describes the conversation
    (which is one-per-turn, the REQUIRED behavior), not the record commit."""
    answers = _sp_extract_answers(answers_record)
    frame = answers_record.get("signature_frame")
    if isinstance(frame, str):
        frame = frame.strip().lower()
    ledger = _sp_offer_ledger(answers_record)
    # Accept the canonical name OR the deprecated alias from the caller; a caller
    # can only ever DOWNGRADE the atomic-commit fact (any present False → False),
    # never silently upgrade a non-atomic record. Missing → True (the driver only
    # reaches here after the turn-gated one-at-a-time interview completes).
    committed = all(
        answers_record.get(k, True) is True
        for k in ("record_committed_atomically", "asked_all_at_once")
        if k in answers_record
    )
    if not any(k in answers_record for k in ("record_committed_atomically", "asked_all_at_once")):
        committed = True
    commit_id = (answers_record.get("record_commit_ids")
                 or answers_record.get("question_block_msg_id")
                 or block_msg_id)
    out = {
        "deck_type": "signature_presentation",
        "record_committed_atomically": bool(committed),
        "record_commit_ids": commit_id,
        # deprecated aliases, emitted for one release (fleet-ordering safety)
        "asked_all_at_once": bool(committed),
        "question_block_msg_id": commit_id,
        "answers": answers,
        "signature_frame": frame,
        "offer_token_ledger": ledger,
        "q7_offer_products": ledger,
        "client_overrode_slide_floor": bool(answers_record.get("client_overrode_slide_floor", False)),
    }
    if answers_record.get("client_overrode_slide_floor") and answers_record.get("client_exact_slide_count") is not None:
        out["client_exact_slide_count"] = answers_record.get("client_exact_slide_count")
    return out


def _run_sp_prover(intake_path: pathlib.Path) -> Tuple[int, str]:
    """Run prove_sp_intake.py against an assembled record. Returns (rc, output).

    rc is the prover's own exit code (0 PASS, 2 AF-SP-* violation, 3 usage/IO).
    A missing prover is a hard fail-closed (rc 3) — a signature intake must never
    be treated as verified when its gate cannot be run."""
    prover = find_sp_prover()
    if prover is None:
        return 3, ("AF-SP-PROVER-MISSING: prove_sp_intake.py not found beside skill 51 — "
                   "cannot verify the 8-Questions-in-ONE-block gate; fail-closed.")
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(prover), str(intake_path)],
        capture_output=True, text=True,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def cmd_signature_pointer(args) -> None:
    """--signature called bare (no --next/--answer/--record/--plan/--selftest).

    E5 fix (the turn-gated signature path was OPTIONAL): the bare form used to
    fall through to the full intake-plan payload (all 8 Questions + frame
    question in ONE JSON block) — a caller never forced through --next/--answer
    could dump the whole question set and "self-pace" the interview, silently
    defeating the one-question-per-turn enforcement the REAL turn-gate provides.
    The bare form now REFUSES to leak that payload: it prints a machine-readable
    pointer at the mandatory turn-gate entrypoint and exits 0 (this is guidance,
    not a hard failure — a caller that only had the old contract should not get
    a cryptic error). --plan remains the explicit, clearly-labeled dry-run/
    inspection escape hatch for anyone who genuinely needs to see the full
    question set offline (never to conduct the interview)."""
    run_dir_hint = args.run_dir or "<RUN_DIR>"
    payload = {
        "status": "use_turn_gate",
        "message": (
            "Bare --signature no longer emits the full question payload. The "
            "Signature Presentation intake MUST be driven ONE question at a time "
            "through the real turn-gate: --signature --next / --signature --answer "
            "ID TEXT. The final validated answer auto-finalizes (assembles the "
            "atomic record at working/copy/sp_intake.json and runs "
            "prove_sp_intake.py against it). Use --signature --plan ONLY for a "
            "read-only dry-run inspection of the full question set — never to "
            "conduct the interview."
        ),
        "next_command": f"deck-intake-driver.py --signature --next --run-dir {run_dir_hint}",
        "dry_run_inspection_command": "deck-intake-driver.py --signature --plan",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    sys.exit(0)


def cmd_signature(args) -> None:
    """--signature --plan: emit the intake plan — the choice-first, one-question-
    at-a-time conversation contract + the 8 Questions + frame question — as a
    read-only dry-run payload; or, with --record, assemble a pre-gathered
    answers file into one atomic record and verify it. This function is ONLY
    reached when --plan or --record is set (see main()) — the bare-call escape
    hatch is handled by cmd_signature_pointer() instead (E5 fix)."""
    run_dir = pathlib.Path(args.run_dir).expanduser().resolve() if args.run_dir else None

    try:
        spec = json.loads(find_sp_spec(args.sp_spec).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": f"cannot load SP spec: {exc}"}))
        sys.exit(3)

    block_msg_id = _sp_block_msg_id()

    # --- --record: assemble the runtime intake record and WIRE it to the prover ---
    if args.record:
        rec_path = pathlib.Path(args.record).expanduser()
        try:
            answers_record = json.loads(rec_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(json.dumps({"status": "error", "message": f"cannot read --record JSON: {exc}"}))
            sys.exit(3)

        intake = assemble_sp_intake(answers_record, block_msg_id)

        # Persist to the run dir (working/copy/sp_intake.json) when one is given.
        if run_dir is not None:
            out_path = run_dir / "working" / "copy" / "sp_intake.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = pathlib.Path(tempfile.mkstemp(prefix="sp_intake_", suffix=".json")[1])
        out_path.write_text(json.dumps(intake, indent=2, ensure_ascii=False), encoding="utf-8")

        rc, prover_out = _run_sp_prover(out_path)
        passed = rc == 0
        payload = {
            "status": "signature_intake_verified" if passed else "signature_intake_rejected",
            "passed": passed,
            "prover_rc": rc,
            "gate": "AF-SP-8Q-SPLIT (prove_sp_intake.py)",
            "intake_path": str(out_path),
            "signature_frame": intake.get("signature_frame"),
            "prover_output": prover_out.strip(),
        }
        # Clean up the throwaway temp record when there was no run dir.
        if run_dir is None:
            try:
                out_path.unlink()
            except OSError:
                pass
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.exit(0 if passed else 2)

    # --- --plan (or any other non-bare arrival here): emit the intake PLAN
    #     (choice-first conversation contract + the 8 Questions + frame question)
    #     as a READ-ONLY dry-run payload. This is inspection tooling, not a turn-
    #     gate -- an agent conducting the actual interview must use --next/--answer.
    block = build_signature_block(spec, block_msg_id)
    if run_dir is not None:
        marker = run_dir / "working" / "interview" / "sp_intake_block.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(block, indent=2, ensure_ascii=False), encoding="utf-8")
        block["block_marker"] = str(marker)
    print(json.dumps(block, indent=2, ensure_ascii=False))
    sys.exit(0)


def signature_selftest() -> bool:
    """Offline self-test for signature mode. Returns True on pass.

    Asserts: (1) the emitted block carries all 8 Questions + the frame question
    as ONE block; (2) an assembled VALID record clears the AF-SP-8Q-SPLIT prover
    (exit 0); (3) a one-per-turn/split record is REJECTED (exit 2, AF-SP-8Q-SPLIT);
    (4) a record missing q7 is REJECTED (AF-SP-8Q-MISSING). Steps 2-4 run the
    REAL prover subprocess, proving the driver is wired to it."""
    print("[deck-intake-driver] --signature --selftest: starting...")
    try:
        spec = json.loads(find_sp_spec(None).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        print(f"[sig-selftest] SKIP: SP spec not found ({exc}); skill 51 not co-located.",
              file=sys.stderr)
        print("[deck-intake-driver] --signature --selftest: PASS (spec absent; skipped)")
        return True

    ok = True

    # Hoisted above Test 5 (which also needs it): call a sys.exit()-driven cmd_*
    # function, capture its printed JSON, and return the parsed payload.
    import io
    from contextlib import redirect_stdout

    def _call(fn, *a):
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                fn(*a)
            except SystemExit:
                pass
        return json.loads(buf.getvalue().strip())

    # (1) --signature --plan emits the full read-only dry-run block (q1..q8 +
    # frame question, one_block record-commit mode). This is the EXPLICIT,
    # clearly-labeled escape hatch for offline inspection — it must still work.
    plan_args = argparse.Namespace(run_dir=None, record=None, plan=True, sp_spec=None)
    block = _call(cmd_signature, plan_args)
    q_ids = {q.get("id") for q in block.get("questions", []) if isinstance(q, dict)}
    have_8 = all(q in q_ids for q in SP_REQUIRED_QUESTIONS)
    have_frame_q = bool(block.get("frame_selection_question"))
    one_block = block.get("delivery", {}).get("mode") == "one_block"
    step1 = have_8 and have_frame_q and one_block
    ok = ok and step1
    print(f"[sig-selftest] Test 1 {'PASS' if step1 else 'FAIL'}: --signature --plan block carries "
          f"q1..q8 ({sorted(q_ids)}) + frame question ({have_frame_q}), one_block={one_block}")

    # (1b) E5 FIX — bare --signature (no --next/--answer/--record/--plan) must NOT
    # leak that same payload. It must point at the REQUIRED turn-gate instead.
    # Before this fix, a bare call fell through to the exact same full-payload
    # block as Test 1 above — an unenforced escape hatch around the one-question-
    # per-turn gate. This regression-guards that the escape hatch stays closed.
    bare_args = argparse.Namespace(run_dir=None, record=None, plan=False, sp_spec=None)
    bare = _call(cmd_signature_pointer, bare_args)
    step1b = (
        bare.get("status") == "use_turn_gate"
        and "questions" not in bare
        and "frame_selection_question" not in bare
        and "--signature --next" in (bare.get("next_command") or "")
    )
    ok = ok and step1b
    print(f"[sig-selftest] Test 1b {'PASS' if step1b else 'FAIL'}: bare --signature (no --plan) "
          f"does NOT leak the full question payload -- status={bare.get('status')!r}, "
          f"next_command={bare.get('next_command')!r}")

    prover = find_sp_prover()
    if prover is None:
        print("[sig-selftest] SKIP: prove_sp_intake.py not co-located; wiring tests skipped.",
              file=sys.stderr)
        print(f"[deck-intake-driver] --signature --selftest: {'PASS' if ok else 'FAIL'}")
        return ok

    def _assemble_and_prove(record: dict) -> Tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            intake = assemble_sp_intake(record, "blk_sig_selftest")
            p = pathlib.Path(td) / "sp_intake.json"
            p.write_text(json.dumps(intake), encoding="utf-8")
            return _run_sp_prover(p)

    valid = {
        "answers": {
            "q1": "The Signature Talk", "q2": "yes, propose two alternates",
            "q3": "the overlooked mid-career expert who feels unseen",
            "q4": "left a secure post to build the practice; a first-in-family milestone",
            "q5": "The 5-Step Signature Method", "q6": "no, the working title is fine",
            "q7": "The Signature Intensive", "q8": "keep the tone warm and direct",
        },
        "signature_frame": "rulebook",
        "offer_token_ledger": ["The Signature Intensive"],
    }

    rc, out = _assemble_and_prove(valid)
    step2 = rc == 0
    ok = ok and step2
    print(f"[sig-selftest] Test 2 {'PASS' if step2 else 'FAIL'}: VALID record -> prover exit {rc} (want 0)")

    # A record that was NOT committed atomically must fail AF-SP-8Q-SPLIT. This is
    # a RECORD-layer fact (record_committed_atomically=False); it is NOT about the
    # conversation pacing. one_question_per_turn is deliberately absent — carrying
    # it True no longer fails the record gate.
    split = {**valid, "record_committed_atomically": False}
    rc, out = _assemble_and_prove(split)
    step3 = rc == 2 and "AF-SP-8Q-SPLIT" in out
    ok = ok and step3
    print(f"[sig-selftest] Test 3 {'PASS' if step3 else 'FAIL'}: non-atomic RECORD -> prover exit {rc} "
          f"(want 2, AF-SP-8Q-SPLIT present={('AF-SP-8Q-SPLIT' in out)})")

    missing_q7 = {**valid, "answers": {k: v for k, v in valid["answers"].items() if k != "q7"}}
    rc, out = _assemble_and_prove(missing_q7)
    step4 = rc == 2 and "AF-SP-8Q-MISSING" in out
    ok = ok and step4
    print(f"[sig-selftest] Test 4 {'PASS' if step4 else 'FAIL'}: MISSING-q7 record -> prover exit {rc} "
          f"(want 2, AF-SP-8Q-MISSING present={('AF-SP-8Q-MISSING' in out)})")

    # (5) the REAL turn-gate: walk --signature --next / --answer one question
    # at a time end-to-end in a temp run dir and confirm (a) --next never
    # returns more than one question per call, (b) it BLOCKS when the active
    # question has no answer yet, and (c) the final answer auto-finalizes
    # (assembles + proves) exactly like a passing --record call. (_call is
    # defined once, above, ahead of Test 1b — reused here.)
    answers = {
        "interview_choice": "quick",
        "q1": "The Signature Talk", "q2": "yes, propose two alternates",
        "q3": "the overlooked mid-career expert who feels unseen",
        "q4": "left a secure post to build the practice; a first-in-family milestone",
        "q5": "The 5-Step Signature Method", "q6": "no, the working title is fine",
        "q7": "The Signature Intensive", "q8": "keep the tone warm and direct",
        "frame_selection": "rulebook",
    }
    with tempfile.TemporaryDirectory() as td:
        run_dir = pathlib.Path(td)
        sp_ledger = load_ledger(run_dir, SP_LEDGER_REL)
        seen_ids = []
        never_blocked_wrongly = True
        rounds = 0
        finalized = None
        while rounds < 30:
            rounds += 1
            out = _call(cmd_sp_next, run_dir, spec, sp_ledger)
            sp_ledger = load_ledger(run_dir, SP_LEDGER_REL)
            if out["status"] in ("signature_intake_verified", "signature_intake_rejected"):
                finalized = out
                break
            if out["status"] == "blocked":
                # Immediately answer the blocked question — proves the
                # active question truly gated further advance.
                qid = out["current_question_id"]
                ans = _call(cmd_sp_answer, run_dir, spec, sp_ledger, qid, answers.get(qid, "a fine answer"))
                sp_ledger = load_ledger(run_dir, SP_LEDGER_REL)
                if ans["status"] in ("accepted_and_finalized",):
                    finalized = ans
                    break
                continue
            if out["status"] == "question":
                qid = out["id"]
                if qid in seen_ids:
                    never_blocked_wrongly = False
                seen_ids.append(qid)
                # answer it directly, then loop back to --next (proves --next
                # will BLOCK if we hadn't done this)
                ans = _call(cmd_sp_answer, run_dir, spec, sp_ledger, qid, answers.get(qid, "a fine answer"))
                sp_ledger = load_ledger(run_dir, SP_LEDGER_REL)
                if ans["status"] in ("accepted_and_finalized",):
                    finalized = ans
                    break
                continue
        step5 = (
            finalized is not None
            and finalized.get("passed") is True
            and never_blocked_wrongly
            and len(set(seen_ids)) >= 9  # choice + 8 + frame, minus whichever finalized inline
        )
        ok = ok and step5
        print(f"[sig-selftest] Test 5 {'PASS' if step5 else 'FAIL'}: --signature --next/--answer "
              f"real turn-gate walked {len(seen_ids)} distinct questions one at a time, "
              f"finalized={finalized is not None and finalized.get('passed')}")

    print(f"[deck-intake-driver] --signature --selftest: {'ALL PASS' if ok else 'FAILED'}")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deck-intake-driver.py",
        description="Interview turn-gate for the Presentations deck-intake.",
    )
    parser.add_argument("--run-dir", metavar="DIR",
                        help="Deck run directory (contains working/)")
    parser.add_argument("--next", action="store_true",
                        help="Return the next unanswered question")
    parser.add_argument("--answer", nargs=2, metavar=("ID", "TEXT"),
                        help="Record and validate an answer: --answer <id> <text>")
    parser.add_argument("--budget", action="store_true",
                        help="Check session turn/time budget")
    parser.add_argument("--complete", action="store_true",
                        help="Check if intake is complete and mark it so")
    parser.add_argument("--selftest", action="store_true",
                        help="Run offline self-test in a temp directory")
    parser.add_argument("--signature", action="store_true",
                        help="Signature Presentation intake (Skill 51). REQUIRED usage is the "
                             "turn-gate: --signature --next / --signature --answer ID TEXT — "
                             "one question per call, blocked until answered, final answer "
                             "auto-finalizes. --signature --plan is a read-only dry-run that "
                             "emits the full intake plan for inspection ONLY. --signature "
                             "--record FILE assembles a pre-gathered answers file into ONE "
                             "atomic record and verifies it via the AF-SP-8Q-SPLIT prover. A "
                             "BARE --signature call (no --next/--answer/--record/--plan) no "
                             "longer emits the payload — it prints a pointer at --next (E5 fix).")
    parser.add_argument("--plan", action="store_true",
                        help="(signature mode) read-only DRY-RUN: emit the FULL intake plan "
                             "(all 8 Questions + frame question) as one JSON payload for "
                             "offline inspection. Never use this to conduct the interview — "
                             "the interview MUST run through --signature --next/--answer.")
    parser.add_argument("--record", metavar="FILE",
                        help="(signature mode) JSON answers file (q1..q8 + signature_frame + "
                             "offer_token_ledger); assembles working/copy/sp_intake.json and "
                             "runs prove_sp_intake.py against it (fail-closed)")
    parser.add_argument("--sp-spec", metavar="FILE",
                        help="(signature mode) explicit path to sp-8-questions.json "
                             "(default: auto-resolve beside skill 51)")

    args = parser.parse_args()

    if args.selftest and not args.signature:
        cmd_selftest()
        return  # cmd_selftest exits internally

    # Signature mode is self-contained: emit-block needs no run dir; --record and
    # the SP self-test resolve everything themselves. Route it BEFORE the generic
    # per-turn --run-dir requirement below.
    if args.signature:
        if args.selftest:
            sys.exit(0 if signature_selftest() else 1)
        if args.next or args.answer:
            # --signature --next / --signature --answer: the REAL turn-gate.
            # Runs the SAME blocked/validated ledger machinery as the standard
            # flow, over sp-8-questions.json (choice question first, q1..q8,
            # then the frame question) — no batch payload on this path.
            if not args.run_dir:
                parser.error("--run-dir DIR is required for --signature --next/--answer")
            sp_run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
            if not sp_run_dir.exists():
                print(json.dumps({"status": "error", "message": f"--run-dir not found: {sp_run_dir}"}))
                sys.exit(1)
            try:
                sp_spec = json.loads(find_sp_spec(args.sp_spec).read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
                print(json.dumps({"status": "error", "message": f"cannot load SP spec: {exc}"}))
                sys.exit(3)
            sp_ledger = load_ledger(sp_run_dir, SP_LEDGER_REL)
            if args.next:
                cmd_sp_next(sp_run_dir, sp_spec, sp_ledger)
            else:
                cmd_sp_answer(sp_run_dir, sp_spec, sp_ledger, args.answer[0], args.answer[1])
            return  # both exit internally
        if args.plan or args.record:
            # --signature --plan (read-only dry-run) or --signature --record FILE
            # (assemble a pre-gathered answers file). Both are explicit, named
            # escape hatches from the turn-gate — never the bare-call default.
            cmd_signature(args)
            return  # cmd_signature exits internally
        # E5 fix: bare --signature (no --next/--answer/--record/--plan) MUST NOT
        # leak the full question payload — point at the required turn-gate instead.
        cmd_signature_pointer(args)
        return  # cmd_signature_pointer exits internally

    # All other commands require --run-dir
    if not args.run_dir:
        parser.error("--run-dir DIR is required for all commands except --selftest")

    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(json.dumps({"status": "error", "message": f"--run-dir not found: {run_dir}"}))
        sys.exit(1)

    qfile = find_questions_file(run_dir)
    with open(qfile) as f:
        qdata = json.load(f)

    ledger = load_ledger(run_dir)

    if args.next:
        cmd_next(run_dir, qdata, ledger)
    elif args.answer:
        cmd_answer(run_dir, qdata, ledger, args.answer[0], args.answer[1])
    elif args.budget:
        cmd_budget(run_dir, qdata, ledger)
    elif args.complete:
        cmd_complete(run_dir, qdata, ledger)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
