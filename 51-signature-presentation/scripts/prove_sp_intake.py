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
# WHAT THIS ENFORCES — the SACRED 8-Questions-in-ONE-block intake gate
# (Prime Directives 6 & 7 of the Signature Presentation MASTERDOC):
#   * All 8 Questions (q1..q8) are present — especially q7 (the offer question).
#   * The frame-selection question is present.
#   * The 8 Questions AND the frame-selection question were delivered as ONE
#     message block (asked_all_at_once, single block id, not one-per-turn).
#   * A Signature frame is SET to one of: rulebook | vault | quest | original.
#
# It reads the intake JSON. By default it reads the section spec at
#   <skill>/intake/sp-8-questions.json
# but it also validates a runtime intake record (the shape described by that
# file's runtime_intake_contract, e.g. working/copy/sp_intake.json) when one is
# passed as the positional argument. Both shapes resolve through one model.
#
# AUTOFAIL CODES (verbatim from the intake contract):
#   AF-SP-8Q-MISSING   — any of q1..q8 missing or empty (Directive 6)
#   AF-SP-8Q-SPLIT     — the 8 + frame question were not delivered as one block (Directive 7)
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
def _resolve_asked_all_at_once(intake):
    if "asked_all_at_once" in intake:
        return intake.get("asked_all_at_once")
    delivery = intake.get("delivery")
    if isinstance(delivery, dict) and "asked_all_at_once" in delivery:
        return delivery.get("asked_all_at_once")
    return None


def _resolve_one_question_per_turn(intake):
    if "one_question_per_turn" in intake:
        return intake.get("one_question_per_turn")
    delivery = intake.get("delivery")
    if isinstance(delivery, dict) and "one_question_per_turn" in delivery:
        return delivery.get("one_question_per_turn")
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

    # --- ONE-block delivery gate (AF-SP-8Q-SPLIT) ---
    asked_all_at_once = _resolve_asked_all_at_once(intake)
    if asked_all_at_once is not True:
        failures.append((AF_SPLIT, "asked_all_at_once is not true (got %r)" % (asked_all_at_once,)))

    one_per_turn = _resolve_one_question_per_turn(intake)
    if one_per_turn is True:
        failures.append((AF_SPLIT, "one_question_per_turn is true — 8 Questions were split across turns"))

    mode = _resolve_mode(intake)
    if mode is not None and mode != "one_block":
        failures.append((AF_SPLIT, "delivery.mode is %r, expected 'one_block'" % (mode,)))

    fsq = intake.get("frame_selection_question")
    if isinstance(fsq, dict) and "asked_in_same_block" in fsq and fsq.get("asked_in_same_block") is not True:
        failures.append((AF_SPLIT, "frame_selection_question.asked_in_same_block is not true"))

    msg_ids = intake.get("question_block_msg_id")
    if msg_ids is not None:
        if isinstance(msg_ids, (list, tuple)):
            real = [m for m in msg_ids if _nonempty_str(m)]
            if len(real) != 1:
                failures.append(
                    (AF_SPLIT, "question_block_msg_id must reference exactly ONE block, found %d" % len(real))
                )
        elif not _nonempty_str(msg_ids):
            failures.append((AF_SPLIT, "question_block_msg_id present but empty"))

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
    print("== Signature Presentation :: 8-Questions-in-ONE-block intake gate ==")
    print("source: %s" % source)
    if not failures:
        print("RESULT: PASS — all 8 Questions + frame question delivered as ONE block; frame set.")
        return
    print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(failures))
    for code, msg in failures:
        print("  [%s] %s" % (code, msg))


# ---- self-test --------------------------------------------------------------
def _valid_runtime_fixture():
    return {
        "deck_type": DECK_TYPE,
        "asked_all_at_once": True,
        "one_question_per_turn": False,
        "question_block_msg_id": "blk_0001",
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
        "delivery": {"mode": "one_block", "asked_all_at_once": True, "one_question_per_turn": False},
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

    # 1) split block — asked_all_at_once false
    f = _valid_runtime_fixture(); f["asked_all_at_once"] = False
    check_fail("split-not-oneshot", f, AF_SPLIT)

    # 2) split block — one_question_per_turn true
    f = _valid_runtime_fixture(); f["one_question_per_turn"] = True
    check_fail("split-per-turn", f, AF_SPLIT)

    # 3) split block — more than one message block id
    f = _valid_runtime_fixture(); f["question_block_msg_id"] = ["blk_a", "blk_b"]
    check_fail("split-multi-block", f, AF_SPLIT)

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
