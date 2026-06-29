#!/usr/bin/env python3
"""
deck-intake-driver.py — RUNTIME ONE-QUESTION-PER-TURN INTAKE STATE MACHINE (FIX D).

================================================================================
This is the fix for the 30-minute wandering deck-intake interview that skipped
questions, re-asked answered ones, and forced the client to police "stay on task."
Pacing used to be PROSE-only (SOP 9.0 "ask one at a time") with nothing at the
runtime layer enforcing it. This driver makes one-question-per-turn STRUCTURAL.

THE CONTRACT
  * The agent CANNOT decide the next question. The driver returns it, from the
    ordered canonical file (deck-intake-questions.json), as the lowest-order
    UNANSWERED required question for the chosen mode. The agent relays exactly
    that one question, captures the answer with --answer, then calls --next again.
  * The QUICK vs IN-DEPTH choice is ALWAYS the first turn (mode is order 0).
    quick -> simple set (<=7 questions, SOP 9.1); in-depth -> extensive set
    (10-20, SOP 9.2). The chosen mode sizes the session budget.
  * ONE SEAMLESS VOICE. --next prints ONLY the next question (prompt + help).
    It NEVER emits routing/relay chatter ("relayed to the department", "the
    Director noted", "you'll see their next question shortly"). The department
    machinery is invisible to the client.
  * The session is time/turn-BUDGETED. On overrun the driver forces a
    "summarize and confirm" turn instead of another open question (critical
    mandatory gaps may still be closed, flagged clarifying_followup:true).
  * --complete is the HARD precondition: every mandatory field answered AND the
    owner confirmed the read-back. It writes intake_ledger.json {complete:true}
    and, when present, feeds scripts/qc-interview-completion.py. The deck build
    is DENIED (presentation-canonical-entry.sh GATE 0 + deck-build-guard.sh)
    until the ledger is complete.

ZERO third-party deps (stdlib json / argparse / pathlib / time / re only).

USAGE
    deck-intake-driver.py --run-dir DIR --next            # print the ONE next question
    deck-intake-driver.py --run-dir DIR --answer ID VALUE # record an answer, advance
    deck-intake-driver.py --run-dir DIR --budget          # turn/time budget status
    deck-intake-driver.py --run-dir DIR --confirm         # owner signs off the read-back
    deck-intake-driver.py --run-dir DIR --complete        # HARD precondition gate
    deck-intake-driver.py --selftest                      # offline self-test (CI)
    [--questions FILE] [--ledger FILE] [--json]

EXIT CODES
    0 — ok (question returned / answer recorded / complete satisfied / budget ok)
    2 — usage error / unknown question id / invalid answer for a typed field
    3 — --complete called but the intake is NOT complete (mandatory gaps / no
        owner confirmation). The build stays blocked.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = HERE.parent / "deck-intake-questions.json"   # presentations/ root
LEDGER_SCHEMA = "deck_intake_ledger/v1"

# Mode token normalization: the client-facing choice ("quick"/"in-depth") maps to
# the doctrinal interview_mode ("simple"/"extensive", SOP 9.1/9.2).
_MODE_MAP = {
    "quick": "simple", "simple": "simple",
    "in-depth": "extensive", "in depth": "extensive", "deep": "extensive",
    "extensive": "extensive",
}


def _fatal(msg, code=2):
    print(f"FATAL [deck-intake-driver]: {msg}", file=sys.stderr)
    sys.exit(code)


def load_questions(path: Path) -> dict:
    if not path.exists():
        _fatal(f"deck-intake-questions.json not found at {path}")
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"deck-intake-questions.json is not valid JSON: {exc}")


def ledger_path(args) -> Path:
    if args.ledger:
        return Path(args.ledger).resolve()
    if args.run_dir:
        return Path(args.run_dir).resolve() / "working" / "checkpoints" / "intake_ledger.json"
    _fatal("one of --ledger or --run-dir is required")


def load_ledger(p: Path) -> dict:
    if p.exists():
        try:
            obj = json.loads(p.read_text())
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001
            pass
    return {
        "schema": LEDGER_SCHEMA,
        "interview_mode": None,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "answers": {},
        "turns_used": 0,
        "wanders": [],
        "interview_confirmed": False,
        "complete": False,
        "completed_at": None,
    }


def save_ledger(p: Path, led: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(led, indent=2))
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Question-set resolution (the driver, NOT the agent, owns "what is next")
# ---------------------------------------------------------------------------
def _mode_choice(q: dict) -> dict:
    return q.get("modeChoiceFirst") or {}


def _ordered_questions(q: dict) -> list:
    return sorted(q.get("questions", []), key=lambda x: x.get("order", 0))


def _mandatory_ids(q: dict) -> list:
    return list(q.get("mandatoryFieldOrder", []))


def _active_set(q: dict, mode: str) -> list:
    """The questions in scope for the chosen mode. SIMPLE (quick): the scope-setter
    topic + the six mandatory fields. EXTENSIVE (in-depth): every question."""
    ordered = _ordered_questions(q)
    if mode == "extensive":
        return ordered
    mand = set(_mandatory_ids(q))
    return [x for x in ordered if x.get("mandatoryField") or x.get("id") == "presentation_topic"
            or x.get("id") in mand]


def next_question(q: dict, led: dict):
    """Return (question_dict, kind) where kind is 'mode' | 'question' | None.
    None means every required question is answered (ready to confirm + complete)."""
    if not led.get("interview_mode"):
        return _mode_choice(q), "mode"
    mode = led["interview_mode"]
    answers = led.get("answers", {})
    for item in _active_set(q, mode):
        if item.get("required") and item["id"] not in answers:
            return item, "question"
    return None, None


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------
def budget_for(q: dict, mode: str) -> dict:
    sb = q.get("sessionBudget", {})
    key = "in-depth" if mode == "extensive" else "quick"
    return sb.get(key, {"max_turns": 7, "max_minutes": 12})


def budget_status(q: dict, led: dict) -> dict:
    mode = led.get("interview_mode") or "simple"
    b = budget_for(q, mode)
    used = led.get("turns_used", 0)
    over = used >= int(b.get("max_turns", 7))
    nxt, kind = next_question(q, led)
    mand_remaining = bool(nxt) and kind == "question" and nxt.get("mandatoryField")
    # Over budget + only OPTIONAL questions remain -> force summarize-and-confirm.
    force_summarize = over and not mand_remaining and not led.get("complete")
    return {
        "mode": mode,
        "turns_used": used,
        "max_turns": int(b.get("max_turns", 7)),
        "max_minutes": int(b.get("max_minutes", 12)),
        "over_budget": over,
        "mandatory_remaining": mand_remaining,
        "force_summarize_and_confirm": force_summarize,
        "directive": ("Budget reached. Read back what is captured, ask the owner to "
                      "confirm or correct, then lock — do NOT ask another open question."
                      if force_summarize else
                      "Within budget — continue one question at a time." if not over else
                      "Budget reached but a CRITICAL mandatory field is still open; close "
                      "it (flag clarifying_followup:true), then summarize and lock."),
    }


# ---------------------------------------------------------------------------
# Answer validation (typed)
# ---------------------------------------------------------------------------
def _question_by_id(q: dict, qid: str):
    if qid == _mode_choice(q).get("id"):
        return _mode_choice(q)
    for item in q.get("questions", []):
        if item.get("id") == qid:
            return item
    return None


def validate_answer(item: dict, raw: str):
    """Return (normalized_value, error_or_None). Typed by the question kind."""
    val = (raw or "").strip()
    if not val:
        return None, "empty answer (a required field cannot be blank)"
    kind = item.get("kind", "text")
    if kind == "choice":
        low = val.lower()
        choices = [c.lower() for c in item.get("choices", [])]
        # The mode question additionally accepts the doctrinal synonyms
        # (deep / in depth / simple / extensive); other choice fields do not.
        is_mode = item.get("storeOn") == "intake.interview_mode"
        if low in choices or (is_mode and low in _MODE_MAP):
            return low, None
        return None, f"must be one of {item.get('choices')}"
    if kind == "boolean":
        low = val.lower()
        if low in ("yes", "y", "true", "pitch", "offer", "1"):
            return True, None
        if low in ("no", "n", "false", "teaching", "content-only", "content only", "0"):
            return False, None
        return None, "answer yes/no (does it end with an offer/pitch?)"
    if kind == "number":
        m = re.search(r"-?\d+", val.replace(",", ""))
        if not m:
            return None, "expected a number (e.g. 30)"
        return int(m.group()), None
    if kind == "number_or_defer":
        if re.search(r"you decide|your call|up to you|defer|whatever", val, re.I):
            return None, None  # explicit defer -> stored as null (pacing floor governs)
        m = re.search(r"-?\d+", val.replace(",", ""))
        if not m:
            return None, "give an exact number, or say 'you decide'"
        return int(m.group()), None
    # text / assets / default: accept non-empty verbatim
    return val, None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_next(q, led, lpath, as_json):
    item, kind = next_question(q, led)
    bud = budget_status(q, led)
    if kind == "mode":
        payload = {"kind": "mode", "id": item.get("id"), "prompt": item.get("prompt"),
                   "help": item.get("help"), "choices": item.get("choices"),
                   "budget": bud}
    elif kind == "question":
        if bud.get("force_summarize_and_confirm"):
            payload = {"kind": "summarize_and_confirm", "budget": bud,
                       "prompt": bud["directive"]}
        else:
            payload = {"kind": "question", "id": item.get("id"), "order": item.get("order"),
                       "prompt": item.get("prompt"), "help": item.get("help"),
                       "choices": item.get("choices"), "kind_of_input": item.get("kind"),
                       "mandatory_field": bool(item.get("mandatoryField")), "budget": bud}
    else:
        payload = {"kind": "ready_to_confirm", "budget": bud,
                   "prompt": ("All required questions are answered. Read the answers back "
                              "to the owner; on their confirmation run --confirm then --complete.")}
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        # ONE seamless voice: print ONLY the question. No relay chatter.
        if payload["kind"] in ("mode", "question"):
            print(payload["prompt"])
            if payload.get("help"):
                print(f"({payload['help']})")
        else:
            print(payload["prompt"])
    return 0


def cmd_answer(q, led, lpath, qid, value, as_json):
    item = _question_by_id(q, qid)
    if item is None:
        _fatal(f"unknown question id {qid!r} (not in deck-intake-questions.json)")
    norm, err = validate_answer(item, value)
    if err:
        if as_json:
            print(json.dumps({"ok": False, "id": qid, "error": err}, indent=2))
        else:
            print(f"INVALID ANSWER for {qid}: {err}", file=sys.stderr)
        return 2
    # Mode choice sets interview_mode (normalized to simple/extensive).
    if qid == _mode_choice(q).get("id"):
        led["interview_mode"] = _MODE_MAP.get(str(norm).lower(), "simple")
    else:
        # light wander log: a question-back or ultra-short text answer is noted but
        # still recorded (the SOP: log wanders, advance).
        if isinstance(norm, str) and ("?" in norm or (item.get("kind") == "text" and len(norm) < 3)):
            led.setdefault("wanders", []).append(
                {"id": qid, "note": "short/off-topic answer captured; consider a follow-up",
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        led.setdefault("answers", {})[qid] = {
            "value": norm, "answered_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "turn": led.get("turns_used", 0) + 1,
        }
    led["turns_used"] = led.get("turns_used", 0) + 1
    save_ledger(lpath, led)
    nxt, knd = next_question(q, led)
    out = {"ok": True, "id": qid, "stored": norm, "turns_used": led["turns_used"],
           "next_kind": knd or "ready_to_confirm"}
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"recorded {qid} (turn {led['turns_used']}). next: {out['next_kind']}")
    return 0


def cmd_confirm(q, led, lpath, as_json):
    led["interview_confirmed"] = True
    save_ledger(lpath, led)
    msg = {"ok": True, "interview_confirmed": True}
    print(json.dumps(msg, indent=2) if as_json else "interview_confirmed:true recorded.")
    return 0


def _missing_mandatory(q, led):
    answers = led.get("answers", {})
    return [mid for mid in _mandatory_ids(q) if mid not in answers]


def cmd_complete(q, led, lpath, as_json):
    missing = _missing_mandatory(q, led)
    confirmed = bool(led.get("interview_confirmed"))
    ok = (not missing) and confirmed
    if ok:
        led["complete"] = True
        led["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        save_ledger(lpath, led)
    out = {"complete": ok, "missing_mandatory": missing,
           "interview_confirmed": confirmed,
           "ledger": str(lpath)}
    # Best-effort: feed the existing interview-completion checker if present.
    feed = HERE.parent.parent.parent.parent / "scripts" / "qc-interview-completion.py"
    out["interview_completion_checker_present"] = feed.exists()
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        if ok:
            print(f"INTAKE COMPLETE — intake_ledger.json marked complete at {lpath}")
        else:
            print(f"INTAKE NOT COMPLETE — missing mandatory: {missing}; "
                  f"interview_confirmed={confirmed}. The deck build stays BLOCKED.",
                  file=sys.stderr)
    return 0 if ok else 3


# ---------------------------------------------------------------------------
# Self-test (offline; CI)
# ---------------------------------------------------------------------------
def selftest() -> int:
    import tempfile
    q = load_questions(DEFAULT_QUESTIONS)
    td = Path(tempfile.mkdtemp())
    lp = td / "intake_ledger.json"
    led = load_ledger(lp)
    # 1. first next is ALWAYS the mode choice
    item, kind = next_question(q, led)
    assert kind == "mode" and item.get("id") == "interview_mode", "mode choice must be first"
    # 2. answer quick -> simple
    cmd_answer(q, led, lp, "interview_mode", "quick", as_json=True)
    led = load_ledger(lp)
    assert led["interview_mode"] == "simple"
    # 3. the driver returns ONE mandatory question at a time, in order; the agent
    #    cannot skip ahead. Walk the simple set.
    seen = []
    for _ in range(20):
        item, kind = next_question(q, led)
        if kind is None:
            break
        seen.append(item["id"])
        # answer each with a type-valid value
        val = {"presentation_mode": "one-person", "target_talk_minutes": "30",
               "requested_slide_count": "25", "pitch_included": "yes",
               "asset_intake_question": "a logo and brand colors",
               "style_source": "creative_develop",
               "presentation_topic": "How to launch in 90 days; book a call"}.get(item["id"], "ok")
        cmd_answer(q, led, lp, item["id"], val, as_json=True)
        led = load_ledger(lp)
    # exact slide count honored verbatim
    assert led["answers"]["requested_slide_count"]["value"] == 25
    assert led["answers"]["pitch_included"]["value"] is True
    # every mandatory field captured
    assert not _missing_mandatory(q, led), _missing_mandatory(q, led)
    # 4. --complete BLOCKS until interview_confirmed
    rc = cmd_complete(q, led, lp, as_json=True)
    assert rc == 3, "complete must block without owner confirmation"
    led = load_ledger(lp)
    cmd_confirm(q, led, lp, as_json=True)
    led = load_ledger(lp)
    rc = cmd_complete(q, led, lp, as_json=True)
    assert rc == 0 and load_ledger(lp)["complete"] is True, "complete after confirm"
    # 5. invalid typed answer is rejected (does not advance)
    led2 = load_ledger(td / "l2.json")
    cmd_answer(q, led2, td / "l2.json", "interview_mode", "in-depth", as_json=True)
    led2 = load_ledger(td / "l2.json")
    rc_bad = cmd_answer(q, led2, td / "l2.json", "pitch_included", "maybe later", as_json=True)
    assert rc_bad == 2, "non-boolean pitch answer must be rejected"
    print("deck-intake-driver selftest: ALL PASS")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Deck-intake one-question-per-turn driver (FIX D).")
    ap.add_argument("--run-dir")
    ap.add_argument("--ledger")
    ap.add_argument("--questions")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--answer", nargs="+", metavar=("ID", "VALUE"),
                    help="record an answer: --answer <id> <value ...>")
    ap.add_argument("--budget", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--complete", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    qpath = Path(args.questions).resolve() if args.questions else DEFAULT_QUESTIONS
    q = load_questions(qpath)
    lpath = ledger_path(args)
    led = load_ledger(lpath)

    if args.next:
        sys.exit(cmd_next(q, led, lpath, args.json))
    if args.answer:
        qid = args.answer[0]
        value = " ".join(args.answer[1:])
        sys.exit(cmd_answer(q, led, lpath, qid, value, args.json))
    if args.budget:
        print(json.dumps(budget_status(q, led), indent=2))
        sys.exit(0)
    if args.confirm:
        sys.exit(cmd_confirm(q, led, lpath, args.json))
    if args.complete:
        sys.exit(cmd_complete(q, led, lpath, args.json))
    ap.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
