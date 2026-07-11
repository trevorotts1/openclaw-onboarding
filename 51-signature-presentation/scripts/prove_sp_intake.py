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
import json
import sys
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


# ---- core evaluation --------------------------------------------------------
def evaluate(intake):
    """Return a list of (AF_CODE, message) failures. Empty list == PASS."""
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

    return failures


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


# ---- runner -----------------------------------------------------------------
def prove(path, as_json=False):
    """Load the intake JSON at `path`, evaluate the gate, print, return exit code."""
    p = Path(path)
    if not p.is_file():
        _emit("USAGE", [("USAGE", "intake file not found: %s" % p)], as_json)
        return EXIT_USAGE
    try:
        intake = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit("USAGE", [("USAGE", "cannot read/parse intake JSON: %s" % exc)], as_json)
        return EXIT_USAGE

    failures = evaluate(intake)
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


def self_test():
    """Construct a VALID fixture (assert PASS) and each VIOLATION fixture
    (assert NONZERO). Returns 0 iff every assertion holds, else 1."""
    ok = True

    def check_pass(name, fixture):
        nonlocal ok
        failures = evaluate(fixture)
        code = decide_exit(failures)
        good = (not failures) and code == EXIT_PASS
        ok = ok and good
        print("  [%s] VALID %-22s -> exit %d %s"
              % ("PASS" if good else "MISS", name, code, "" if good else ("(unexpected: %r)" % failures)))

    def check_fail(name, fixture, expect_code):
        nonlocal ok
        failures = evaluate(fixture)
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
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    return prove(args.intake, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
