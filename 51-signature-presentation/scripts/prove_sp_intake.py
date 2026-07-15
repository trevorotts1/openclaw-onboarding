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
    if "mode" in intake:
        return intake.get("mode")
    delivery = intake.get("delivery")
    if isinstance(delivery, dict):
        return delivery.get("mode")
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
    intake_trace_check.py / AF-INTAKE-BATCH, which never gates the build).

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
    check_pass("runtime-record", _valid_runtime_fixture())
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
    f = _valid_runtime_fixture(); f["one_question_per_turn"] = True
    check_pass("per-turn-ignored", f)

    # 3) split record — more than one atomic record-commit id
    f = _valid_runtime_fixture(); f["record_commit_ids"] = ["rec_a", "rec_b"]
    check_fail("split-multi-commit", f, AF_SPLIT)

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
                        help="Override 'today' for the AF-SP-INTAKE-UNPACED dated grace window "
                             "(GK-23/D18). Evidence/proof runs only — omit for real enforcement.")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    return prove(args.intake, as_json=args.json, as_of=args.as_of)


if __name__ == "__main__":
    sys.exit(main())
