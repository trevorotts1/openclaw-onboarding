#!/usr/bin/env python3
# =============================================================================
# SKILL 51 — SIGNATURE PRESENTATION :: INTAKE GATE PROVER
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED prover (Python stdlib only). Cloned in spirit
# from the deterministic stripped-length prover pattern (build_deck.py): every
# rule below is fail-closed — a violating intake record is NOT accepted, NOT run,
# NOT unlocked for slide authoring. A violation is sys.exit(2) with the named
# AF-SP-* code. No network, no model judgement, no third-party imports.
#
# WHAT THIS ENFORCES — the SACRED 8-Questions RECORD gate (Prime Directives 6,
# 7 & 8 of the Signature Presentation MASTERDOC, under Trevor's ruling that
# one-question-at-a-time wins). This is a RECORD-LAYER gate ONLY. It says
# NOTHING about how the questions were asked — the conversation is choice-first
# and one question at a time (that is the REQUIRED behavior, scanned separately
# by intake_trace_check.py / AF-INTAKE-BATCH). What this prover checks:
#   * All 8 Questions (q1..q8) are present — especially q7 (the offer question).
#   * The frame-selection question is present.
#   * The assembled intake ledger was COMMITTED AS ONE ATOMIC RECORD
#     (record_committed_atomically, a single record-commit id). This is the
#     record-integrity fact after the one-at-a-time conversation, NOT a licence
#     to dump the 8 Questions at the owner.
#   * A Signature frame is SET to one of: rulebook | vault | quest | original.
#   * Every answer carries CONTENT provenance proving the text came from the
#     client (answer_provenance: verbatim client_text + a client confirmation,
#     captured by the driver's --sig-answer / --sig-confirm quote-back step).
#     This closes the 2026-08-27 live defect: a record whose answers were
#     AUTHORED BY THE SYSTEM passed every structural check above. After the
#     PROVENANCE_GRACE_WINDOW_UNTIL migration window a provenance-less or
#     unconfirmed answer hard-fails AF-SP-PROVENANCE — fail-closed.
#
# It reads the intake JSON. By default it reads the section spec at
#   <skill>/intake/sp-8-questions.json
# but it also validates a runtime intake record (the shape described by that
# file's runtime_intake_contract, e.g. working/copy/sp_intake.json) when one is
# passed as the positional argument. Both shapes resolve through one model.
#
# FIELD NAMES (v1.1 — the machine layer no longer teaches batching):
#   record_committed_atomically  — the assembled ledger was written as ONE atomic
#       commit (deprecated alias: asked_all_at_once — accepted for one release).
#   record_commit_ids            — the id(s) of that atomic record commit; exactly
#       one (deprecated alias: question_block_msg_id — accepted for one release).
#   NOTE: one_question_per_turn is NO LONGER a record-layer signal — it describes
#       the CONVERSATION (which IS one-per-turn) and is intentionally not checked.
#
# AUTOFAIL CODES (verbatim from the intake contract):
#   AF-SP-8Q-MISSING   — any of q1..q8 missing or empty (Directive 6)
#   AF-SP-8Q-SPLIT     — the assembled RECORD was not committed as ONE atomic
#                        ledger write (record-only gate; the conversation stays
#                        one question per turn)
#   AF-SP-FRAME-UNSET  — signature_frame not one of the four allowed values
#   AF-SP-TYPE-MISMATCH— deck_type != signature_presentation
#   AF-SP-OFFER-UNDECLARED — q7's offer(s) not carried into the offer_token_ledger
#   AF-SP-PROVENANCE — an answer lacks content provenance: no answer_provenance
#       entry, no client_text, committed text != client_text, origin
#       'agent_authored', or the client never confirmed it (quote-back/direct)
#
# EXIT CODES:
#   0  PASS  — intake gate satisfied; slide authoring may unlock
#   2  AUTOFAIL — one or more AF-SP-* violations (fail-closed)
#   3  USAGE/IO — missing file, unreadable/invalid JSON (still fail-closed)
#
# USAGE:
#   python3 prove_sp_intake.py [intake.json] [--json]
#   python3 prove_sp_intake.py --self-test
# =============================================================================
"""Fail-closed deterministic prover for the Signature Presentation intake gate."""

import argparse
import hashlib
import hmac
import json
import sys
from datetime import date
from pathlib import Path

# ---- exit codes -------------------------------------------------------------
EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

# ---- autofail codes ---------------------------------------------------------
AF_MISSING = "AF-SP-8Q-MISSING"
AF_SPLIT = "AF-SP-8Q-SPLIT"
AF_FRAME = "AF-SP-FRAME-UNSET"
AF_TYPE = "AF-SP-TYPE-MISMATCH"
AF_OFFER = "AF-SP-OFFER-UNDECLARED"
AF_UNPACED = "AF-SP-INTAKE-UNPACED"
AF_PROVENANCE = "AF-SP-PROVENANCE"

# ---- GK-23 / D18 — turn-ledger provenance (record-layer pacing gate) --------
# See deck-intake-driver.py's matching comment block for the full threat-model
# note. TURN_LEDGER_KEY MUST match that file byte-for-byte — it is a published
# integrity key (not a secrecy boundary: evaluate() takes only the assembled
# dict, exactly like every other call site here including build_deck.py's
# _sp_delegate, so no out-of-band secret channel exists to thread a per-run
# secret through). It binds the turn array + deck_type + commit id together so
# the block cannot be edited piecemeal without invalidating the signature.
TURN_LEDGER_KEY = b"skill51-sp-intake-turn-ledger-provenance-v1"

# GK-D3-ratified migration window (Recommendation A's accepted cost: "one
# migration window for pre-stamp records"). A runtime record with NO
# turn_ledger_provenance block at all is grandfathered through this date;
# after it, an unstamped record hard-fails AF-SP-INTAKE-UNPACED too. REMOVE
# this exception in a dated follow-up line item once the fleet has rolled the
# driver's turn-ledger stamp (do not silently extend the date in place).
GRACE_WINDOW_UNTIL = date(2026, 8, 15)

# ---- CONTENT-PROVENANCE migration window (2026-08-27 live defect) ------------
# A runtime record carrying a valid turn-ledger stamp but NO per-answer
# content provenance (answer_provenance with client_text + confirmation) is
# grandfathered through this date; after it, a provenance-less record
# hard-fails AF-SP-PROVENANCE too. REMOVE this exception in a dated follow-up
# line item once the fleet has rolled the driver's quote-back stamp (do not
# silently extend the date in place). Chosen so every record assembled by the
# pre-provenance driver during the rollout window still builds, while the
# teeth are deterministically provable on both sides of the cutoff via
# --as-of / the `today` injection — same pattern as GRACE_WINDOW_UNTIL above.
PROVENANCE_GRACE_WINDOW_UNTIL = date(2026, 9, 15)

# ---- contract constants -----------------------------------------------------
DECK_TYPE = "signature_presentation"
ALLOWED_FRAMES = ("rulebook", "vault", "quest", "original")
REQUIRED_QUESTIONS = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")
# q7 is the OFFER question — the offer-token ledger seed; called out explicitly.
OFFER_QUESTION = "q7"

# Default intake path: <skill>/intake/sp-8-questions.json, resolved relative to
# this script so the prover is portable fleet-wide (scripts/ -> ../intake/).
_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INTAKE = _SCRIPT_DIR.parent / "intake" / "sp-8-questions.json"


# ---- small helpers ----------------------------------------------------------
def _nonempty_str(value):
    """True only for a non-empty, non-whitespace string."""
    return isinstance(value, str) and value.strip() != ""


def _answered(value):
    """True when an answer slot carries real content."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    if isinstance(value, bool):
        # An explicit boolean answer counts as answered.
        return True
    return True  # numbers and other scalars count as answered


# ---- field resolvers (handle both the spec shape and a runtime record) ------
# The RECORD-layer atomic-commit fact carries a canonical name plus a deprecated
# alias, accepted for ONE release so a new prover validates an old record and an
# old prover validates a new record during a fleet rollout (no ordering risk).
_COMMITTED_KEYS = ("record_committed_atomically", "asked_all_at_once")
_COMMIT_ID_KEYS = ("record_commit_ids", "question_block_msg_id")


def _collect(intake, keys):
    """All present values for `keys` across the top level AND a nested
    `delivery` object (canonical name first, then the deprecated alias)."""
    found = []
    containers = [intake]
    delivery = intake.get("delivery")
    if isinstance(delivery, dict):
        containers.append(delivery)
    for container in containers:
        for key in keys:
            if key in container:
                found.append(container[key])
    return found


def _resolve_record_committed(intake):
    """True only when the assembled ledger was committed as ONE atomic record.
    Fail-closed: if any present variant (canonical or the deprecated alias, top
    level or under delivery) is not exactly True, the record is NOT atomic.
    Returns None when neither field is present at all."""
    vals = _collect(intake, _COMMITTED_KEYS)
    if not vals:
        return None
    return all(v is True for v in vals)


def _resolve_commit_ids(intake):
    """The record-commit id value (canonical `record_commit_ids`, else the
    deprecated alias `question_block_msg_id`). None when neither is present."""
    for key in _COMMIT_ID_KEYS:
        if key in intake:
            return intake.get(key)
    delivery = intake.get("delivery")
    if isinstance(delivery, dict):
        for key in _COMMIT_ID_KEYS:
            if key in delivery:
                return delivery.get(key)
    return None


def _resolve_mode(intake):
    """Resolve the RECORD's atomic-commit-mode signal (consumed ONLY by the
    AF-SP-8Q-SPLIT check below). This is deliberately NOT the interview DEPTH
    signal (QUICK/IN-DEPTH) that a live record also carries under the bare
    top-level `mode` key -- see deck-intake-driver.py's _sig_finalize comment:
    "mode" stays the interview DEPTH (read by prove_sp_routing.py's
    P-SP-CLAIM gate); "delivery.mode" is the SEPARATE record-commit-mode
    signal this gate actually means ("the assembled RECORD's atomic-commit
    mode, NOT a batch of questions"). Prefer delivery.mode; fall back to the
    bare top-level `mode` ONLY when delivery.mode is absent -- back-compat for
    an older intake shape that carried just the one (pre-namespacing) field."""
    delivery = intake.get("delivery")
    if isinstance(delivery, dict) and "mode" in delivery:
        return delivery.get("mode")
    if "mode" in intake:
        return intake.get("mode")
    return None


def _resolve_frame(intake):
    """Resolve a SELECTED frame value (lowercased) from any supported shape."""
    if _nonempty_str(intake.get("signature_frame")):
        return intake["signature_frame"].strip().lower()
    answers = intake.get("answers")
    if isinstance(answers, dict):
        for key in ("signature_frame", "frame", "frame_selection"):
            if _nonempty_str(answers.get(key)):
                return answers[key].strip().lower()
    fsq = intake.get("frame_selection_question")
    if isinstance(fsq, dict):
        for key in ("selected", "value", "answer", "chosen"):
            if _nonempty_str(fsq.get(key)):
                return fsq[key].strip().lower()
    return None


def _frame_question_present(intake):
    """True when the frame-selection question was asked (defined or answered)."""
    if isinstance(intake.get("frame_selection_question"), dict):
        return True
    # A resolved frame value implies the frame question was asked.
    return _resolve_frame(intake) is not None


def _missing_questions(intake):
    """Return the required question ids that are absent/empty, in order."""
    answers = intake.get("answers")
    if isinstance(answers, dict):
        # Runtime record: presence == a non-empty answer.
        return [q for q in REQUIRED_QUESTIONS if not _answered(answers.get(q))]
    # Spec/contract shape: presence == defined with a non-empty prompt.
    defined = {}
    questions = intake.get("questions")
    if isinstance(questions, list):
        for item in questions:
            if isinstance(item, dict):
                defined[item.get("id")] = item.get("prompt")
    return [q for q in REQUIRED_QUESTIONS if not _nonempty_str(defined.get(q))]


# ---- CONTENT provenance (AF-SP-PROVENANCE, 2026-08-27 live defect) ----------
# The 2026-08-27 live run (rec_20260827T221120131024, signature 8cb0cd7d…)
# proved the gate above verifies STRUCTURE, not CONTENT FIDELITY: q6 and q8
# were AUTHORED BY THE SYSTEM (never typed by the client, never asked as
# phrased), yet the record passed 8/8 with a valid turn-ledger HMAC — because
# the driver's --sig-answer accepts text from ANY caller and stamps the
# transcript's owner turn itself. Structure cannot tell those answers apart
# from real ones. The only thing that can is a per-answer record of the
# CLIENT'S OWN WORDS, captured at answer time and confirmed back to the
# client before the record commits.
#
# Contract (written by deck-intake-driver.py's _sig_answer/--sig-confirm):
#   answer_provenance: {
#     "<qid>": {
#       "client_text":        <verbatim client words for this answer>,
#       "origin":             "client" | "agent_authored",
#       "confirmed_by_client": true|false,
#       "confirmation":       "quote_back" | "direct" | None,
#     }, ... }
#
# RULES (all fail-closed):
#   * committed answer text must equal client_text (whitespace-normalized)
#     — an answer the client did not at least see verbatim cannot ride their
#     name into the deck;
#   * origin "agent_authored" NEVER passes — an operator/agent may pre-fill
#     an answer only as a visibly-marked DRAFT, and it can never satisfy
#     this gate as a client answer;
#   * confirmed_by_client must be True with confirmation "quote_back" or
#     "direct" — an unconfirmed answer is surfaced by name, not waved
#     through.
def _ws_normalized(value):
    """Whitespace-normalized text for byte-for-byte quote comparison: all
    whitespace runs collapse to one space, ends trimmed. Case is PRESERVED
    (the client's capitalization is part of their words)."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split())


def _evaluate_answer_provenance(intake, today=None):
    """AF-SP-PROVENANCE — refuses an intake record whose answers cannot show
    they came from the client. Returns a list of (code, message) failures.

    Only meaningful for a RUNTIME record (carries an `answers` dict) — the
    static sp-8-questions.json spec/contract shape has no answers object and
    is exempt, exactly like _evaluate_turn_pacing. `today` is an injectable
    override (default: real date) so the dated migration window is
    deterministically testable on both sides of its cutoff."""
    if not isinstance(intake.get("answers"), dict):
        return []

    as_of = today or date.today()
    prov = intake.get("answer_provenance")

    if prov is None:
        if as_of <= PROVENANCE_GRACE_WINDOW_UNTIL:
            return []  # pre-provenance driver record: grandfathered (accepted rollout cost)
        return [(AF_PROVENANCE,
                 "intake record carries no answer_provenance — per-answer client provenance "
                 "(client_text + confirmed_by_client, captured by deck-intake-driver.py's "
                 "--sig-answer/--sig-confirm quote-back step) is required after the %s migration "
                 "window closed; answers without provenance cannot be shown to be the client's "
                 "own words." % PROVENANCE_GRACE_WINDOW_UNTIL.isoformat())]

    if not isinstance(prov, dict):
        return [(AF_PROVENANCE,
                 "answer_provenance is present but not a JSON object (got %s)"
                 % type(prov).__name__)]

    answers = intake.get("answers") or {}
    fails = []
    for qid in REQUIRED_QUESTIONS:
        answer_text = answers.get(qid)
        if not _answered(answer_text):
            continue  # completeness is AF-SP-8Q-MISSING's job, not this gate's
        block = prov.get(qid)
        if not isinstance(block, dict):
            fails.append((AF_PROVENANCE,
                           "%s carries no answer_provenance entry — there is no record that this "
                           "answer is the client's own words (fail-closed)." % qid))
            continue
        client_text = block.get("client_text")
        if not _nonempty_str(client_text):
            fails.append((AF_PROVENANCE,
                           "%s answer_provenance carries no client_text — the verbatim client "
                           "words the answer was built from are missing (fail-closed)." % qid))
            continue
        if _ws_normalized(client_text) != _ws_normalized(answer_text):
            fails.append((AF_PROVENANCE,
                           "%s committed answer does not match its recorded client_text — the "
                           "answer was edited after the client's words were captured (fail-closed)."
                           % qid))
            continue
        origin = block.get("origin")
        if origin == "agent_authored":
            fails.append((AF_PROVENANCE,
                           "%s answer is marked origin='agent_authored' — the system authored it, "
                           "not the client. An agent-authored answer is a visibly-marked draft "
                           "only and can never satisfy the gate." % qid))
            continue
        if origin not in (None, "client"):
            fails.append((AF_PROVENANCE,
                           "%s answer_provenance.origin is %r, expected 'client' (or the older "
                           "shape with origin absent)." % (qid, origin)))
            continue
        if block.get("confirmed_by_client") is not True:
            fails.append((AF_PROVENANCE,
                           "%s answer is NOT confirmed by the client (confirmed_by_client is %r) — "
                           "run deck-intake-driver.py --sig-confirm %s to read the answer back and "
                           "record the client's confirmation before committing." % (
                               qid, block.get("confirmed_by_client"), qid)))
            continue
        confirmation = block.get("confirmation")
        if confirmation not in ("quote_back", "direct"):
            fails.append((AF_PROVENANCE,
                           "%s confirmed but confirmation mode is %r — must be 'quote_back' (the "
                           "driver read the answer back verbatim and the client confirmed it) or "
                           "'direct' (the client typed/voiced the answer themselves)." % (
                               qid, confirmation)))
    return fails


# ---- turn-ledger provenance (AF-SP-INTAKE-UNPACED, GK-23 / D18) -------------
def _canonical_turns_payload(turns, deck_type, commit_id):
    """Must match deck-intake-driver.py's _canonical_turns_payload() exactly."""
    payload = {"deck_type": deck_type, "record_commit_ids": commit_id, "turns": turns}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign_turn_ledger(turns, deck_type, commit_id):
    return hmac.new(TURN_LEDGER_KEY, _canonical_turns_payload(turns, deck_type, commit_id),
                     hashlib.sha256).hexdigest()


def _evaluate_turn_pacing(intake, today=None):
    """AF-SP-INTAKE-UNPACED — the record-layer half of GK-23/D18: refuses an
    intake record lacking valid driver turn-ledger provenance, or whose ledger
    shows two questions sharing one turn (batch-dumped, not paced one at a
    time). Says NOTHING about the conversation itself (that stays scanned by
    intake_trace_check.py / AF-INTAKE-BATCH, an out-of-band scan that does not
    itself gate the build — the gating enforcer is the required preflight
    P-SP-INTAKE-TRACE, build_deck._chk_sp_intake_trace, phase order 0.16).

    Only meaningful for a RUNTIME record (carries an `answers` dict) — the
    static sp-8-questions.json spec/contract shape has no ledger and is exempt.
    `today` is an injectable override (default: real date) so the dated grace
    window is deterministically testable on both sides of its cutoff."""
    if not isinstance(intake.get("answers"), dict):
        return []

    as_of = today or date.today()
    prov = intake.get("turn_ledger_provenance")

    if prov is None:
        if as_of <= GRACE_WINDOW_UNTIL:
            return []  # pre-stamp / --record-assembled record: grandfathered (GK-D3 accepted cost)
        return [(AF_UNPACED,
                 "intake record carries no turn_ledger_provenance — the driver's turn-gate stamp "
                 "(per-question turn id + asked_at/validated_at) is required after the %s migration "
                 "window closed; assemble the intake through deck-intake-driver.py --signature "
                 "--next/--answer, never by hand or via a bare --record with no ledger behind it."
                 % GRACE_WINDOW_UNTIL.isoformat())]

    if not isinstance(prov, dict):
        return [(AF_UNPACED, "turn_ledger_provenance is present but not a JSON object")]

    turns = prov.get("turns")
    if not isinstance(turns, list) or not turns:
        return [(AF_UNPACED, "turn_ledger_provenance.turns is missing/empty")]

    fails = []
    seen_turns = {}
    ordered_ids = []
    turn_seq = []
    for t in turns:
        if not isinstance(t, dict):
            fails.append((AF_UNPACED, "a turn_ledger_provenance.turns entry is not an object"))
            continue
        qid = t.get("question_id")
        turn_no = t.get("turn")
        if not _nonempty_str(qid) or not isinstance(turn_no, int) or isinstance(turn_no, bool):
            fails.append((AF_UNPACED, "turn entry %r is missing a valid question_id/turn" % (t,)))
            continue
        ordered_ids.append(qid)
        turn_seq.append(turn_no)
        seen_turns.setdefault(turn_no, set()).add(qid)

    dup_turns = {k: sorted(v) for k, v in seen_turns.items() if len(v) > 1}
    if dup_turns:
        fails.append((AF_UNPACED,
                      "ledger shows multi-question turns (batch-dumped, not paced one at a time): %s"
                      % dup_turns))

    if turn_seq and (turn_seq != sorted(turn_seq) or len(set(turn_seq)) != len(turn_seq)):
        fails.append((AF_UNPACED,
                      "turn ids are not strictly increasing across the recorded questions (got %r) — "
                      "a genuinely paced ledger assigns one ascending id per turn" % turn_seq))

    # Completeness: every ANSWERED required question must carry a turn-ledger
    # entry — an answer with no turn id could not have come from the real
    # turn gate (cmd_sp_answer never writes `turn`; only cmd_sp_next does).
    answers = intake.get("answers") or {}
    answered_ids = {q for q in REQUIRED_QUESTIONS if _answered(answers.get(q))}
    missing_turns = sorted(answered_ids - set(ordered_ids))
    if missing_turns:
        fails.append((AF_UNPACED,
                      "answered question(s) %s carry no turn-ledger entry — answered outside the "
                      "driver's turn gate" % missing_turns))

    if fails:
        return fails

    sig = prov.get("signature")
    if not _nonempty_str(sig):
        fails.append((AF_UNPACED, "turn_ledger_provenance has no signature"))
    else:
        expected = _sign_turn_ledger(turns, intake.get("deck_type"), _resolve_commit_ids(intake))
        if not hmac.compare_digest(expected, sig):
            fails.append((AF_UNPACED,
                          "turn_ledger_provenance.signature does not match its recomputed digest — "
                          "the block was tampered or copied from a different record"))
    return fails


# ---- core evaluation --------------------------------------------------------
def evaluate(intake, today=None):
    """Return a list of (AF_CODE, message) failures. Empty list == PASS.

    `today` is an optional override for the AF-SP-INTAKE-UNPACED dated grace
    window (default: real date). Every existing call site (build_deck.py's
    _sp_delegate, this file's own self-test) calls evaluate(intake) with a
    single positional argument and is unaffected."""
    failures = []

    if not isinstance(intake, dict):
        failures.append((AF_TYPE, "intake root is not a JSON object"))
        return failures

    # --- deck_type sanity (AF-SP-TYPE-MISMATCH) ---
    deck_type = intake.get("deck_type")
    if deck_type is not None and deck_type != DECK_TYPE:
        failures.append((AF_TYPE, "deck_type is %r, expected %r" % (deck_type, DECK_TYPE)))

    # --- ONE-atomic-record commit gate (AF-SP-8Q-SPLIT) — RECORD LAYER ONLY ---
    # This gate checks ONLY that the assembled intake ledger was committed as ONE
    # atomic record. It says NOTHING about conversation pacing: the conversation
    # is one question at a time (the REQUIRED behavior, enforced separately by
    # intake_trace_check.py / AF-INTAKE-BATCH). one_question_per_turn is NOT
    # checked here — it describes the conversation, not the record commit.
    record_committed = _resolve_record_committed(intake)
    if record_committed is not True:
        failures.append((AF_SPLIT,
                         "the assembled intake RECORD was not committed as ONE atomic ledger write "
                         "(record_committed_atomically is not true, got %r) — record-only gate; "
                         "the conversation stays one question per turn" % (record_committed,)))

    mode = _resolve_mode(intake)
    if mode is not None and mode != "one_block":
        failures.append((AF_SPLIT,
                         "delivery.mode is %r, expected 'one_block' (the assembled RECORD's "
                         "atomic-commit mode, NOT a batch of questions)" % (mode,)))

    fsq = intake.get("frame_selection_question")
    if isinstance(fsq, dict) and "asked_in_same_block" in fsq and fsq.get("asked_in_same_block") is not True:
        failures.append((AF_SPLIT, "frame_selection_question.asked_in_same_block is not true "
                                   "(the frame answer must ride the same atomic record commit)"))

    commit_ids = _resolve_commit_ids(intake)
    if commit_ids is not None:
        if isinstance(commit_ids, (list, tuple)):
            real = [m for m in commit_ids if _nonempty_str(m)]
            if len(real) != 1:
                failures.append(
                    (AF_SPLIT, "record_commit_ids must reference exactly ONE atomic record commit, found %d" % len(real))
                )
        elif not _nonempty_str(commit_ids):
            failures.append((AF_SPLIT, "record_commit_ids present but empty"))

    # --- 8 Questions completeness (AF-SP-8Q-MISSING) ---
    missing = _missing_questions(intake)
    if missing:
        note = ""
        if OFFER_QUESTION in missing:
            note = " (includes q7 — the OFFER question)"
        failures.append((AF_MISSING, "missing/empty required questions: %s%s" % (", ".join(missing), note)))

    # --- frame-selection question present (AF-SP-FRAME-UNSET) ---
    if not _frame_question_present(intake):
        failures.append((AF_FRAME, "frame-selection question absent from the intake"))

    # --- frame SET to a valid value (AF-SP-FRAME-UNSET) ---
    frame = _resolve_frame(intake)
    if frame is None:
        failures.append((AF_FRAME, "signature_frame is not set"))
    elif frame not in ALLOWED_FRAMES:
        failures.append(
            (AF_FRAME, "signature_frame is %r, must be one of: %s" % (frame, "|".join(ALLOWED_FRAMES)))
        )

    # --- offer-token ledger (runtime record only) (AF-SP-OFFER-UNDECLARED) ---
    # Only enforced for a runtime record (has an `answers` object). q7's exact
    # product/offer name(s) must be carried into offer_token_ledger.
    if isinstance(intake.get("answers"), dict):
        ledger = intake.get("offer_token_ledger")
        if not (isinstance(ledger, list) and any(_nonempty_str(x) for x in ledger)):
            failures.append((AF_OFFER, "offer_token_ledger missing/empty — q7 offer(s) not declared"))

    # --- one-question-at-a-time UNFAKEABLE record-layer gate (AF-SP-INTAKE-UNPACED) ---
    failures.extend(_evaluate_turn_pacing(intake, today=today))

    # --- CONTENT provenance: answers must provably be the client's own words
    # (AF-SP-PROVENANCE) — the 2026-08-27 live defect: 2 of 8 answers were
    # authored by the system on a record that passed every structural check.
    failures.extend(_evaluate_answer_provenance(intake, today=today))

    return failures


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


# ---- runner -----------------------------------------------------------------
def prove(path, as_json=False, as_of=None):
    """Load the intake JSON at `path`, evaluate the gate, print, return exit code.
    `as_of` (YYYY-MM-DD) overrides "today" for the AF-SP-INTAKE-UNPACED dated
    grace window — evidence runs can pin a date to prove the check has teeth
    on either side of the cutoff without waiting for the calendar."""
    p = Path(path)
    if not p.is_file():
        _emit("USAGE", [("USAGE", "intake file not found: %s" % p)], as_json)
        return EXIT_USAGE
    try:
        intake = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit("USAGE", [("USAGE", "cannot read/parse intake JSON: %s" % exc)], as_json)
        return EXIT_USAGE

    today = None
    if as_of:
        try:
            today = date.fromisoformat(as_of)
        except ValueError as exc:
            _emit("USAGE", [("USAGE", "--as-of must be YYYY-MM-DD: %s" % exc)], as_json)
            return EXIT_USAGE

    failures = evaluate(intake, today=today)
    exit_code = decide_exit(failures)
    _emit(str(p), failures, as_json)
    return exit_code


def _emit(source, failures, as_json):
    if as_json:
        payload = {
            "gate": "signature-presentation-intake",
            "source": source,
            "pass": not failures,
            "failures": [{"code": c, "message": m} for c, m in failures],
        }
        print(json.dumps(payload, indent=2))
        return
    print("== Signature Presentation :: 8-Questions atomic-RECORD intake gate ==")
    print("source: %s" % source)
    if not failures:
        print("RESULT: PASS — all 8 Questions + frame question present, committed as ONE atomic record; frame set.")
        return
    print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(failures))
    for code, msg in failures:
        print("  [%s] %s" % (code, msg))


# ---- self-test --------------------------------------------------------------
def _valid_runtime_fixture():
    return {
        "deck_type": DECK_TYPE,
        "record_committed_atomically": True,
        "record_commit_ids": "rec_0001",
        # deprecated aliases, still emitted for one release (fleet-ordering safety)
        "asked_all_at_once": True,
        "question_block_msg_id": "rec_0001",
        "answers": {
            "q1": "The Sovereign Method",
            "q2": "no",
            "q3": "burnout; no repeatable systems",
            "q4": "left the day job; built the practice from scratch",
            "q5": "7 Secrets to a Self-Running Practice",
            "q6": "no",
            "q7": "The Momentum Accelerator",
            "q8": "keep the tone punchy and direct",
        },
        "signature_frame": "rulebook",
        "offer_token_ledger": ["The Momentum Accelerator"],
    }


def _valid_spec_fixture():
    return {
        "deck_type": DECK_TYPE,
        "delivery": {"mode": "one_block", "record_committed_atomically": True, "asked_all_at_once": True},
        "questions": [{"id": q, "order": i + 1, "prompt": "Question %s prompt" % q} for i, q in enumerate(REQUIRED_QUESTIONS)],
        "frame_selection_question": {
            "asked_in_same_block": True,
            "allowed_values": list(ALLOWED_FRAMES),
            "selected": "vault",
        },
    }


def _valid_turn_ledger_provenance(deck_type, commit_id, question_ids=None):
    """Build a well-formed turn_ledger_provenance block exactly the way the
    driver would (strictly-ascending turn ids, one per question, in order) —
    used to prove the record-layer PASS side of AF-SP-INTAKE-UNPACED."""
    ids = list(question_ids) if question_ids is not None else list(REQUIRED_QUESTIONS)
    turns = [
        {
            "question_id": qid,
            "turn": i + 1,
            "asked_at": "2026-07-15T12:%02d:00" % i,
            "validated_at": "2026-07-15T12:%02d:30" % i,
        }
        for i, qid in enumerate(ids)
    ]
    return {"turns": turns, "signature": _sign_turn_ledger(turns, deck_type, commit_id)}


def _valid_runtime_fixture_paced():
    """Fixture A (GK-23/D18 BINARY acceptance): a driver-paced interview —
    the base valid runtime record PLUS a genuine, correctly-signed turn-ledger
    provenance block. Must PASS every gate including AF-SP-INTAKE-UNPACED."""
    f = _valid_runtime_fixture()
    f["turn_ledger_provenance"] = _valid_turn_ledger_provenance(f["deck_type"], f["record_commit_ids"])
    return f


def _valid_answer_provenance(answers):
    """Build a well-formed answer_provenance block exactly the way the driver
    would (verbatim client_text per answered question, confirmed quote-back) —
    used to prove the record-layer PASS side of AF-SP-PROVENANCE."""
    return {
        qid: {
            "client_text": text,
            "origin": "client",
            "confirmed_by_client": True,
            "confirmation": "quote_back",
        }
        for qid, text in (answers or {}).items()
        if _answered(text)
    }


def _valid_runtime_fixture_provenanced():
    """The full genuine record (2026-08-27 contract): driver-paced turn ledger
    PLUS per-answer client provenance (verbatim client_text, quote-back
    confirmed). Must PASS every gate including AF-SP-PROVENANCE at any date."""
    f = _valid_runtime_fixture_paced()
    f["answer_provenance"] = _valid_answer_provenance(f["answers"])
    return f


def self_test():
    """Construct a VALID fixture (assert PASS) and each VIOLATION fixture
    (assert NONZERO). Returns 0 iff every assertion holds, else 1."""
    ok = True

    def check_pass(name, fixture, today=None):
        nonlocal ok
        failures = evaluate(fixture, today=today)
        code = decide_exit(failures)
        good = (not failures) and code == EXIT_PASS
        ok = ok and good
        print("  [%s] VALID %-22s -> exit %d %s"
              % ("PASS" if good else "MISS", name, code, "" if good else ("(unexpected: %r)" % failures)))

    def check_fail(name, fixture, expect_code, today=None):
        nonlocal ok
        failures = evaluate(fixture, today=today)
        codes = [c for c, _ in failures]
        exit_code = decide_exit(failures)
        good = bool(failures) and exit_code != EXIT_PASS and expect_code in codes
        ok = ok and good
        print("  [%s] VIOLATION %-18s -> exit %d codes=%s (want %s)"
              % ("PASS" if good else "MISS", name, exit_code, codes, expect_code))

    print("== self-test: VALID fixtures (must PASS / exit 0) ==")
    # GK-23/D18: the bare record has been ungrandfathered since GRACE_WINDOW_UNTIL
    # (2026-08-15) — a genuine must-PASS runtime record needs the driver-paced
    # turn_ledger_provenance stamp, same as every other "must PASS" fixture below.
    # 2026-08-27 content-provenance contract: the full genuine record ALSO carries
    # per-answer client provenance (verbatim client_text + quote-back confirmation),
    # so it must PASS on both sides of PROVENANCE_GRACE_WINDOW_UNTIL.
    check_pass("runtime-record", _valid_runtime_fixture_provenanced())
    check_pass("runtime-record-post-prov-grace",
               _valid_runtime_fixture_provenanced(), today=date(2026, 10, 1))
    check_pass("spec-contract", _valid_spec_fixture())

    print("== self-test: VIOLATION fixtures (must FAIL / exit nonzero) ==")

    # 1) record not committed atomically — record_committed_atomically false
    f = _valid_runtime_fixture(); f["record_committed_atomically"] = False
    check_fail("record-not-atomic", f, AF_SPLIT)

    # 1b) the DEPRECATED alias alone still gates (old-record backward compat):
    #     a record carrying only asked_all_at_once=False (no canonical field)
    #     must still fail — this is exactly what a stale box's record looks like.
    f = _valid_runtime_fixture()
    del f["record_committed_atomically"]; f["asked_all_at_once"] = False
    check_fail("record-alias-false", f, AF_SPLIT)

    # 2) one_question_per_turn is NO LONGER a violation — it describes the
    #    (correct) conversation, not the record. A record that carries it True
    #    but is committed atomically must PASS: the record-only gate ignores it.
    #    GK-23/D18: must-PASS, so it needs the driver-paced provenance stamp too
    #    (and the 2026-08-27 content-provenance contract on top).
    f = _valid_runtime_fixture_provenanced(); f["one_question_per_turn"] = True
    check_pass("per-turn-ignored", f)

    # 3) split record — more than one atomic record-commit id
    f = _valid_runtime_fixture(); f["record_commit_ids"] = ["rec_a", "rec_b"]
    check_fail("split-multi-commit", f, AF_SPLIT)

    # ---- E3-20260819: _resolve_mode must read the COMMIT signal (delivery.mode),
    # never the interview DEPTH signal (bare top-level `mode`) that a live record
    # ALSO carries under the same namesake key. Regression cover for the live-box
    # defect: a real signature intake carries top-level mode="IN-DEPTH" (interview
    # depth, read by prove_sp_routing.py's P-SP-CLAIM gate) PLUS delivery.mode=
    # "one_block" (this gate's actual atomic-commit signal) -- see
    # deck-intake-driver.py's _sig_finalize comment for the namespacing intent.
    print("== self-test: E3-20260819 mode-resolver DEPTH-vs-COMMIT namespacing ==")

    # 3c) the REAL live shape: top-level mode is the DEPTH value ("IN-DEPTH"),
    # delivery.mode is the COMMIT value ("one_block") -- must PASS (this is
    # exactly the regression fixture that was wrongly AUTOFAILing on the live box).
    f = _valid_runtime_fixture_provenanced()
    f["mode"] = "IN-DEPTH"
    f["delivery"] = {"mode": "one_block", "record_committed_atomically": True,
                      "asked_all_at_once": True}
    check_pass("mode-depth-vs-commit-namespaced", f)

    # 3d) a genuinely batched/non-atomic intake (delivery.mode != "one_block")
    # must still FAIL -- the fix corrects WHICH FIELD is read, never whether the
    # gate can fail. Top-level `mode` is deliberately left as a DEPTH-looking
    # value ("IN-DEPTH") to prove delivery.mode -- not the depth field -- is what
    # decides the outcome.
    f = _valid_runtime_fixture_paced()
    f["mode"] = "IN-DEPTH"
    f["delivery"] = {"mode": "batched", "record_committed_atomically": True,
                      "asked_all_at_once": True}
    check_fail("mode-delivery-batched-still-fails", f, AF_SPLIT)

    # 3e) back-compat: an OLDER intake shape with only a bare top-level
    # mode="one_block" and NO delivery object at all must still PASS --
    # _resolve_mode falls back to the top-level field only when delivery.mode
    # is absent.
    f = _valid_runtime_fixture_provenanced()
    f["mode"] = "one_block"
    assert "delivery" not in f
    check_pass("mode-top-level-only-backcompat", f)

    # 3f) neither top-level `mode` nor `delivery.mode` present at all -- the
    # mode check contributes nothing (mode resolves to None) and the fixture's
    # other atomic-commit fields (record_committed_atomically, record_commit_ids)
    # alone decide the outcome, exactly as before this fix (no field to read ==
    # no opinion from this specific check).
    f = _valid_runtime_fixture_provenanced()
    assert "mode" not in f and "delivery" not in f
    check_pass("mode-absent-entirely-unaffected", f)

    # 4) missing q7 (the OFFER question)
    f = _valid_runtime_fixture(); del f["answers"]["q7"]
    check_fail("missing-q7-offer", f, AF_MISSING)

    # 5) empty required question (q3)
    f = _valid_runtime_fixture(); f["answers"]["q3"] = "   "
    check_fail("empty-question", f, AF_MISSING)

    # 6) frame unset entirely
    f = _valid_runtime_fixture(); del f["signature_frame"]
    check_fail("frame-unset", f, AF_FRAME)

    # 7) frame set to an invalid value
    f = _valid_runtime_fixture(); f["signature_frame"] = "blueprint"
    check_fail("frame-invalid", f, AF_FRAME)

    # 8) deck_type mismatch
    f = _valid_runtime_fixture(); f["deck_type"] = "webinar_deck"
    check_fail("type-mismatch", f, AF_TYPE)

    # 9) offer ledger empty on a runtime record
    f = _valid_runtime_fixture(); f["offer_token_ledger"] = []
    check_fail("offer-undeclared", f, AF_OFFER)

    # ---- GK-23 / D18 — AF-SP-INTAKE-UNPACED (one-question-at-a-time UNFAKEABLE
    # at the record layer). Named to match the unit's own BINARY acceptance text.
    print("== self-test: GK-23/D18 turn-ledger provenance (AF-SP-INTAKE-UNPACED) ==")

    # Fixture A: a driver-paced interview (one turn per question, valid HMAC
    # signature) -> record PASSES.
    check_pass("GK-23-fixtureA-driver-paced", _valid_runtime_fixture_paced())

    # Fixture B: IDENTICAL answers assembled WITHOUT the driver / batch-dumped
    # (no turn_ledger_provenance at all) -> REFUSED with AF-SP-INTAKE-UNPACED
    # once the dated migration window has closed. `today` is pinned past the
    # cutoff so this is deterministic today, not dependent on the calendar.
    check_fail("GK-23-fixtureB-batch-dumped-post-grace", _valid_runtime_fixture(),
               AF_UNPACED, today=date(2026, 9, 1))

    # 10) the SAME unstamped record still PASSES *within* the migration window
    # (GK-D3 recommendation A's accepted, ratified cost) — proves the grace
    # window is real and dated, not merely theoretical.
    check_pass("unpaced-no-provenance-within-grace", _valid_runtime_fixture(),
               today=date(2026, 7, 20))

    # 11) a forged provenance block claiming two questions on the SAME turn
    # (the literal "ledger shows multi-question turns" case) fails regardless
    # of the grace window — this is direct evidence of batching, not merely
    # an old-shape record.
    f = _valid_runtime_fixture_paced()
    f["turn_ledger_provenance"]["turns"][1]["turn"] = f["turn_ledger_provenance"]["turns"][0]["turn"]
    check_fail("unpaced-multi-question-turn", f, AF_UNPACED)

    # 12) a tampered/forged signature (turns look fine but don't match the
    # HMAC) — must fail even though the shape is otherwise well-formed.
    f = _valid_runtime_fixture_paced()
    f["turn_ledger_provenance"]["signature"] = "0" * 64
    check_fail("unpaced-bad-signature", f, AF_UNPACED)

    # 13) an answered required question with no corresponding turn-ledger entry
    # (answered outside the turn gate, e.g. direct --answer with no --next).
    f = _valid_runtime_fixture_paced()
    f["turn_ledger_provenance"]["turns"] = [
        t for t in f["turn_ledger_provenance"]["turns"] if t["question_id"] != "q3"
    ]
    check_fail("unpaced-missing-turn-for-answered-q", f, AF_UNPACED)

    # ---- 2026-08-27 live defect — AF-SP-PROVENANCE (content provenance:
    # every answer must provably be the client's own words). The literal live
    # failure mode: q6/q8 were AUTHORED BY THE SYSTEM on a record whose
    # structural checks (8/8 present, frame set, turns signed, atomic commit)
    # all passed. These fixtures prove the gate now tells them apart.
    print("== self-test: content provenance (AF-SP-PROVENANCE) ==")

    # 14) a genuinely client-provided, quote-back-confirmed answer PASSES —
    # at ANY date (today pinned past the migration window to prove the full
    # contract carries teeth, not just the grace-window grandfather).
    check_pass("provenance-client-quote-back-passes",
               _valid_runtime_fixture_provenanced(), today=date(2026, 10, 1))

    # 15) the client typed/voiced the answer themselves ('direct' confirmation)
    # — passes identically to the quote-back path.
    f = _valid_runtime_fixture_provenanced()
    for blk in f["answer_provenance"].values():
        blk["confirmation"] = "direct"
    check_pass("provenance-client-direct-passes", f, today=date(2026, 10, 1))

    # 16) an AGENT-AUTHORED answer (origin='agent_authored') is REFUSED even
    # when its client_text matches and someone set confirmed_by_client=True —
    # an agent-authored answer is a visibly-marked draft only, never a client
    # answer. This is the literal 2026-08-27 live failure mode.
    f = _valid_runtime_fixture_provenanced()
    f["answer_provenance"]["q6"]["origin"] = "agent_authored"
    check_fail("provenance-agent-authored-refused", f, AF_PROVENANCE, today=date(2026, 10, 1))

    # 17) an agent-authored DRAFT without confirmation — the other half of the
    # live failure mode: the operator types an answer on the client's behalf
    # and nothing confirms it. Must be refused and named.
    f = _valid_runtime_fixture_provenanced()
    f["answer_provenance"]["q8"].update({"origin": "agent_authored",
                                         "confirmed_by_client": False,
                                         "confirmation": None})
    check_fail("provenance-unconfirmed-draft-refused", f, AF_PROVENANCE, today=date(2026, 10, 1))

    # 18) an unconfirmed CLIENT answer — text matches, origin client, but the
    # quote-back confirmation never happened. Refused with the exact remedy
    # (run --sig-confirm).
    f = _valid_runtime_fixture_provenanced()
    f["answer_provenance"]["q3"]["confirmed_by_client"] = False
    f["answer_provenance"]["q3"]["confirmation"] = None
    check_fail("provenance-unconfirmed-refused", f, AF_PROVENANCE, today=date(2026, 10, 1))

    # 19) the committed answer was EDITED after the client's words were
    # captured (client_text no longer matches answers[qid]) — the exact way a
    # system-authored answer would sneak in on top of real client text.
    f = _valid_runtime_fixture_provenanced()
    f["answers"]["q6"] = "Settled -- The Trust Ledger Protocol is the name, no alternates"
    f["answer_provenance"]["q6"]["client_text"] = "yes use the protocol name"
    check_fail("provenance-text-mismatch-refused", f, AF_PROVENANCE, today=date(2026, 10, 1))

    # 20) an answered question with NO provenance entry at all — no record
    # that the answer is the client's words.
    f = _valid_runtime_fixture_provenanced()
    del f["answer_provenance"]["q6"]
    check_fail("provenance-missing-entry-refused", f, AF_PROVENANCE, today=date(2026, 10, 1))

    # 21) the WHOLE provenance block absent, pinned PAST the migration window
    # — hard-fails (the pre-provenance driver's shape after the rollout ends).
    check_fail("provenance-absent-post-grace-refused", _valid_runtime_fixture_paced(),
               AF_PROVENANCE, today=date(2026, 10, 1))

    # 22) REGRESSION GUARD: the SAME provenance-less record still PASSES
    # *within* the migration window — pre-provenance driver records keep
    # building during the fleet rollout (accepted, dated cost).
    check_pass("provenance-absent-within-grace-passes", _valid_runtime_fixture_paced(),
               today=date(2026, 9, 1))

    # 23) whitespace-insensitive quote comparison: the client's words with a
    # double space / newline normalization still match (case IS preserved).
    f = _valid_runtime_fixture_provenanced()
    f["answer_provenance"]["q6"]["client_text"] = "  no\n "
    check_pass("provenance-whitespace-normalized-match", f, today=date(2026, 10, 1))

    # 24) confirmation mode must be a real mode — 'confirmed_by_client': true
    # with no recorded HOW is not evidence.
    f = _valid_runtime_fixture_provenanced()
    f["answer_provenance"]["q6"]["confirmation"] = "operator-eyeballed-it"
    check_fail("provenance-bogus-confirmation-mode-refused", f, AF_PROVENANCE, today=date(2026, 10, 1))

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


# ---- main -------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fail-closed prover for the Signature Presentation 8-Questions-in-ONE-block intake gate.",
    )
    parser.add_argument(
        "intake",
        nargs="?",
        default=str(DEFAULT_INTAKE),
        help="Path to the intake JSON (default: <skill>/intake/sp-8-questions.json).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--self-test", dest="self_test", action="store_true",
                        help="Run built-in VALID + VIOLATION fixtures and exit.")
    parser.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD",
                        help="Override 'today' for the dated grace windows "
                             "(AF-SP-INTAKE-UNPACED GK-23/D18 and AF-SP-PROVENANCE). "
                             "Evidence/proof runs only — omit for real enforcement.")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    return prove(args.intake, as_json=args.json, as_of=args.as_of)


if __name__ == "__main__":
    sys.exit(main())
