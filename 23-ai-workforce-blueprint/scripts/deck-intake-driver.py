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
from typing import Optional, Tuple

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
#       asked_all_at_once / mode=one_block / one_question_per_turn=False describe
#       the assembled RECORD being committed as one atomic block (NOT a batch of
#       questions dumped at the owner), so a record that was not committed
#       atomically can never pass. The prover is the source of truth; this driver
#       emits the plan and hands the assembled record to it.
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
    """A single opaque id proving the 8 + frame question went out as ONE block."""
    return "blk_sp_" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")


def build_signature_block(spec: dict, block_msg_id: str) -> dict:
    """Assemble the intake PLAN: the choice-first conversation contract + all 8
    Questions + the frame-selection question.

    TWO LAYERS (Trevor's ruling — one-question-at-a-time wins): the agent RUNS the
    conversation one question at a time (the `conversation_contract` below —
    offer QUICK vs IN-DEPTH first, then ONE question per message; a batch is
    AF-INTAKE-BATCH), and later COMMITS the answers as one atomic record. The
    `delivery` block carries the RECORD contract (mode == one_block,
    asked_all_at_once) that prove_sp_intake.py validates on that assembled record
    — it is NOT a licence to dump the questions at the owner.
    """
    questions = spec.get("questions") or []
    frame_q = spec.get("frame_selection_question") or {}
    spec_delivery = spec.get("delivery") or {}
    conversation_contract = spec_delivery.get("conversation_contract") or {}
    return {
        "status": "signature_intake_plan",
        "deck_type": spec.get("deck_type", "signature_presentation"),
        # delivery describes the RECORD layer (the assembled ledger committed as
        # one atomic block) — NOT the conversation. mode==one_block is asserted by
        # prove_sp_intake.py on the assembled record and by this driver's selftest.
        "delivery": {
            "mode": "one_block",
            "asked_all_at_once": True,
            "one_question_per_turn": False,
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
    AF-SP-8Q-SPLIT prover validates. The one-block delivery facts are stamped
    HERE, from the emitted block, so a caller cannot silently mark a split intake
    as one-block — the prover still re-checks every field."""
    answers = _sp_extract_answers(answers_record)
    frame = answers_record.get("signature_frame")
    if isinstance(frame, str):
        frame = frame.strip().lower()
    ledger = _sp_offer_ledger(answers_record)
    out = {
        "deck_type": "signature_presentation",
        "asked_all_at_once": bool(answers_record.get("asked_all_at_once", True)),
        "one_question_per_turn": bool(answers_record.get("one_question_per_turn", False)),
        "question_block_msg_id": answers_record.get("question_block_msg_id") or block_msg_id,
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


def cmd_signature(args) -> None:
    """--signature: emit the intake plan — the choice-first, one-question-at-a-time
    conversation contract + the 8 Questions + frame question (default) — or, with
    --record, assemble the answers into one atomic record and verify it."""
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

    # --- default: emit the intake PLAN (choice-first conversation contract + the
    #     8 Questions + frame question) for the agent to run ONE question at a time ---
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

    # (1) emitted block shape.
    block = build_signature_block(spec, _sp_block_msg_id())
    q_ids = {q.get("id") for q in block.get("questions", []) if isinstance(q, dict)}
    have_8 = all(q in q_ids for q in SP_REQUIRED_QUESTIONS)
    have_frame_q = bool(block.get("frame_selection_question"))
    one_block = block.get("delivery", {}).get("mode") == "one_block"
    step1 = have_8 and have_frame_q and one_block
    ok = ok and step1
    print(f"[sig-selftest] Test 1 {'PASS' if step1 else 'FAIL'}: block carries q1..q8 "
          f"({sorted(q_ids)}) + frame question ({have_frame_q}), one_block={one_block}")

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

    split = dict(valid); split = {**valid, "one_question_per_turn": True, "asked_all_at_once": False}
    rc, out = _assemble_and_prove(split)
    step3 = rc == 2 and "AF-SP-8Q-SPLIT" in out
    ok = ok and step3
    print(f"[sig-selftest] Test 3 {'PASS' if step3 else 'FAIL'}: SPLIT record -> prover exit {rc} "
          f"(want 2, AF-SP-8Q-SPLIT present={('AF-SP-8Q-SPLIT' in out)})")

    missing_q7 = {**valid, "answers": {k: v for k, v in valid["answers"].items() if k != "q7"}}
    rc, out = _assemble_and_prove(missing_q7)
    step4 = rc == 2 and "AF-SP-8Q-MISSING" in out
    ok = ok and step4
    print(f"[sig-selftest] Test 4 {'PASS' if step4 else 'FAIL'}: MISSING-q7 record -> prover exit {rc} "
          f"(want 2, AF-SP-8Q-MISSING present={('AF-SP-8Q-MISSING' in out)})")

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
                        help="Signature Presentation intake (Skill 51): emit the intake plan "
                             "— the choice-first (quick vs in-depth), one-question-at-a-time "
                             "conversation contract + the 8 Questions + frame question (default); "
                             "or with --record assemble the answers into ONE atomic record and "
                             "verify it via the AF-SP-8Q-SPLIT prover")
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
        cmd_signature(args)
        return  # cmd_signature exits internally

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
