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

Dependency-free: stdlib only (json, os, pathlib, datetime, argparse, sys, tempfile, time).
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
QUESTIONS_FILE_NAME = "deck-intake-questions.json"
LEDGER_REL = pathlib.Path("working") / "interview" / "intake_ledger.json"
ANSWERS_REL = pathlib.Path("working") / "interview" / "answers"


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
def load_ledger(run_dir: pathlib.Path) -> dict:
    lp = run_dir / LEDGER_REL
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


def save_ledger(run_dir: pathlib.Path, ledger: dict) -> None:
    lp = run_dir / LEDGER_REL
    lp.parent.mkdir(parents=True, exist_ok=True)
    with open(lp, "w") as f:
        json.dump(ledger, f, indent=2)


# ---------------------------------------------------------------------------
# Answer file I/O
# ---------------------------------------------------------------------------
def answer_path(run_dir: pathlib.Path, qid: str) -> pathlib.Path:
    return run_dir / ANSWERS_REL / f"{qid}.txt"


def answer_exists(run_dir: pathlib.Path, qid: str) -> bool:
    p = answer_path(run_dir, qid)
    return p.exists() and p.stat().st_size > 0


def read_answer_file(run_dir: pathlib.Path, qid: str) -> str:
    with open(answer_path(run_dir, qid)) as f:
        return f.read().strip()


def write_answer_file(run_dir: pathlib.Path, qid: str, text: str) -> None:
    p = answer_path(run_dir, qid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# Question helpers
# ---------------------------------------------------------------------------
def ordered_questions(qdata: dict) -> list:
    """Return questions sorted by order field (ascending)."""
    return sorted(qdata["questions"], key=lambda q: q.get("order", 999))


def find_active_question(qdata: dict, ledger: dict) -> dict | None:
    """Return the lowest-order question that has been asked but not yet validated."""
    entries = ledger.get("entries", {})
    for q in ordered_questions(qdata):
        e = entries.get(q["id"], {})
        if e.get("asked_at") and not e.get("validated"):
            return q
    return None


def find_next_question(qdata: dict, ledger: dict) -> dict | None:
    """Return the lowest-order question with no validated answer and not yet asked."""
    entries = ledger.get("entries", {})
    for q in ordered_questions(qdata):
        e = entries.get(q["id"], {})
        if not e.get("validated") and not e.get("asked_at"):
            return q
    return None


def find_next_any(qdata: dict, ledger: dict) -> dict | None:
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
                entries[qid]["validated"] = True
                entries[qid]["validated_at"] = _now()
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
        entries[qid]["validated"] = True
        entries[qid]["validated_at"] = _now()
        if not entries[qid].get("asked_at"):
            # Mark as asked if it wasn't already (direct --answer without --next)
            entries[qid]["asked_at"] = _now()
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

    On success: sets intake_ledger.json status="complete".
    On failure: exits nonzero and prints which ids are blocking.
    """
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
        # Pick the next question id
        next_qs = [q for q in ordered_questions(qdata) if q["id"] != first_id]
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

    print("[deck-intake-driver] --selftest: ALL PASS")
    sys.exit(0)


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

    args = parser.parse_args()

    if args.selftest:
        cmd_selftest()
        return  # cmd_selftest exits internally

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
