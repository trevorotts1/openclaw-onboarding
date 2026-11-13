#!/usr/bin/env python3
"""
test-qc-counter-drift.py — the completion gate may refuse a counter that claims
MORE than the transcript holds, never one that sits BEHIND it.

BUG THIS LOCKS (WF-002, BU-02): count_questions() compared the transcript's raw
Q-block count against state.interviewProgress.lastQuestionNumber with a plain
absolute difference, so a progress counter that froze LOW refused a genuinely
complete interview. Three honest paths hit it:
  - the owner answers the 11 structured cards on the web deck, then keeps
    talking to the agent, whose counter restarts at its own count;
  - the Review screen appends one more block per inline edit without advancing
    the counter (ReviewScreen.tsx saveEdit sends no questionNumber);
  - any box whose progress writer broke (the v10.15.x frozen-counter class).
In every one of them the interview is REAL and the counter is the broken part.

THE FIX (BU-02):
  (a) the "**Q:**" form log_answer() actually writes is counted directly;
  (b) the comparison base is the number of DISTINCT normalized question texts
      parse_answer_blocks() finds — re-asking one question never inflates it;
  (c) only a counter ABOVE that count (by more than 3) hard-fails. A counter
      BELOW it is a warning and returns distinctQuestions for the record.

THIS SUITE PROVES (fixtures exactly as the package's reproduction):
  E  11 canonical cards answered on the web deck + 8 chat answers, agent
     counter restarted at 8                       -> exit 0, lag in warnings
  H  the 11 cards plus 3 Review-screen edits, counter not advanced
     -> exit 0
  D  11 cards only, but a counter of 30 (claims 19 more than the transcript
     holds)                                       -> exit 3, refusal names it

EXIT: 0 = every assertion passed; 1 otherwise.
Usage: python3 test-qc-counter-drift.py [REPO_ROOT]
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
QC_SCRIPT = SCRIPTS / "qc-interview-completion.py"
BRANDING_Q = REPO / "23-ai-workforce-blueprint" / "interview" / "branding-questions.json"
JARGON_LIST = REPO / "23-ai-workforce-blueprint" / "interview" / "forbidden-jargon.json"

PASS = 0
FAIL = 0

# The counter rule's own sentence, asserted in the transcript-AHEAD and
# transcript-BEHIND directions. Never asserted by exit code alone: another
# hard failure must not be able to earn this suite a pass.
COUNTER_FAILURE = "more questions than the transcript holds"
COUNTER_WARNING = "behind the transcript"


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


HEADER = "# Workforce Interview Answers\n\nStarted: test fixture\n\n---\n\n"

DECK = [
    ("company_name", "What is your company name?"),
    ("industry", "What industry are you in?"),
    ("brand_primary_color", "What is your primary brand color?"),
    ("brand_logo", "Do you have a logo? Paste a public link to it (or upload one)."),
    ("brand_evokes", "What feeling do you want your brand to evoke?"),
    ("customer_feeling", "What feeling do you want your customers to leave with after working with you?"),
    ("brand_descriptors", "What words would your best customer use to describe you?"),
    ("brand_voice", "How would you describe your brand voice?"),
    ("ideal_customer", "Who is your ideal customer — and why do they come to YOU specifically?"),
    ("unique_differentiator", "Why do people come to YOU versus anyone else who does what you do?"),
    ("command_center_name", "What would you like to name your company's home base?"),
]

LONG = {
    "company_name": "Acme Consulting Group",
    "industry": "Executive coaching for women founders",
    "brand_primary_color": "#1E3A8A",
    "brand_logo": "https://example.com/logo.png",
    "brand_evokes": "Calm confidence, like someone finally has your back.",
    "customer_feeling": "Relieved and ready to act, not overwhelmed any more.",
    "brand_descriptors": "Straight-talking, generous, organised, and always prepared.",
    "brand_voice": "Warm but direct. Example: Here is the plan, and here is step one.",
    "ideal_customer": "Women founders past 250 thousand dollars a year who are stuck doing everything themselves.",
    "unique_differentiator": "I have built and sold two companies, so I coach from scars and not from theory.",
    "command_center_name": "Mission Control",
}


def block(q: str, a: str) -> str:
    return f"**Q:** {q}\n**A:** {a}\n**Logged:** test fixture\n\n---\n\n"


def transcript(extra_blocks: int = 0) -> str:
    out = HEADER
    for qid, prompt in DECK:
        out += block(prompt, LONG[qid])
    for i in range(extra_blocks):
        out += block(
            f"Tell me how new customers usually find you (follow-up {i + 1})?",
            "Mostly referrals from past clients plus one podcast appearance every month.",
        )
    return out


def state(asked_by: str, last_q: int) -> dict:
    return {
        "interviewProgress": {"lastQuestionNumber": last_q, "lastQuestionAskedBy": asked_by},
        "canonicalReconciliation": {
            "decisions": {
                "marketing": {
                    "decision": "yes",
                    "source": "owner-interview",
                    "decidedAt": "2026-11-11T14:00:00Z",
                    "decidedBy": "fixture-owner",
                    "sessionId": "fixture",
                }
            }
        },
        "departments": [],
    }


def run_qc_cli(transcript_path: Path, state_path: Path) -> tuple:
    proc = subprocess.run(
        [sys.executable, str(QC_SCRIPT),
         "--transcript", str(transcript_path),
         "--state", str(state_path),
         "--jargon-list", str(JARGON_LIST),
         "--branding-questions", str(BRANDING_Q),
         "--repo-root", str(REPO),
         "--no-context-map",
         "--format", "json"],
        capture_output=True, text=True, timeout=120,
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        print(f"    (non-JSON stdout, rc={proc.returncode}): {proc.stdout[:500]}", file=sys.stderr)
        print(f"    stderr: {proc.stderr[:500]}", file=sys.stderr)
        return proc.returncode, {}


# name, expected exit, extra blocks, asked_by, counter
CASES = [
    ("E_cards_then_8_chat_answers_agent_counter_restarts", 0, 8, "main-agent", 8),
    ("H_all_cards_long_then_3_review_screen_edits", 0, 3, "interview-web", 11),
    ("D_cards_only_but_counter_claims_30", 3, 0, "interview-web", 30),
]


def main() -> int:
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1

    tmproot = Path(tempfile.mkdtemp(prefix="qc-counter-drift-test-"))
    try:
        results = {}
        for name, expected, extra, asked_by, counter in CASES:
            print(f"\n[{name}] expected exit {expected} "
                  f"({len(DECK) + extra} answered blocks, counter {counter})")
            d = tmproot / name
            d.mkdir()
            t = d / "workforce-interview-answers.md"
            s = d / ".workforce-build-state.json"
            t.write_text(transcript(extra), encoding="utf-8")
            s.write_text(json.dumps(state(asked_by, counter), indent=2), encoding="utf-8")

            rc, details = run_qc_cli(t, s)
            results[name] = details
            if rc == expected:
                ok(f"exit {rc} as expected")
            else:
                bad(f"expected exit {expected}, got {rc}; "
                    f"hardFailures={details.get('hardFailures')} "
                    f"warnings={details.get('warnings')}")

        # E: the lag must be REPORTED (proves the rule ran, not that a check
        # quietly disappeared), and it must never be a hard failure.
        details_e = results.get(CASES[0][0], {})
        warn_e = " ".join(details_e.get("warnings", []))
        hard_e = " ".join(details_e.get("hardFailures", []))
        if COUNTER_WARNING in warn_e.lower() and COUNTER_FAILURE not in hard_e:
            ok("case E: the counter lagging the transcript is surfaced as a warning "
               "and never as a counter hard failure")
        else:
            bad(f"case E: expected the lag in warnings and no counter hard failure; "
                f"warnings={details_e.get('warnings')} hardFailures={details_e.get('hardFailures')}")

        # H: three honest edits do not push the counters apart by more than 3,
        # so the honest completion is simply quiet — no counter failure at all.
        details_h = results.get(CASES[1][0], {})
        hard_h = " ".join(details_h.get("hardFailures", []))
        if details_h.get("verdict") == "PASS" and COUNTER_FAILURE not in hard_h:
            ok(f"case H: three Review-screen edits complete cleanly "
               f"(verdict={details_h.get('verdict')}, no counter failure)")
        else:
            bad(f"case H: expected PASS with no counter failure; "
                f"verdict={details_h.get('verdict')!r} hardFailures={details_h.get('hardFailures')}")

        # D: the ONLY thing wrong with this fixture is the counter, so the
        # refusal must name the counter rule — not something incidental.
        details_d = results.get(CASES[2][0], {})
        hard_d = " ".join(details_d.get("hardFailures", []))
        if COUNTER_FAILURE in hard_d:
            ok("case D: a counter claiming MORE than the transcript holds refuses "
               "on the counter rule itself (named in hardFailures)")
        else:
            bad(f"case D: expected the counter rule named in hardFailures; "
                f"hardFailures={details_d.get('hardFailures')}")

        # count_questions() returns the comparison base itself, so a reader can
        # audit what the rule measured instead of trusting the verdict alone.
        import importlib.util
        spec = importlib.util.spec_from_file_location("qc_under_test_counter", str(QC_SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        count_result_e = mod.count_questions(transcript(8), state("main-agent", 8))
        if (count_result_e.get("distinctQuestions") == len(DECK) + 8
                and count_result_e.get("disagreeWarning") is None
                and count_result_e.get("transcriptAheadWarning")):
            ok(f"count_questions() returns distinctQuestions="
               f"{count_result_e.get('distinctQuestions')} (the comparison base), no "
               f"disagreement, plus the transcript-ahead warning")
        else:
            bad(f"count_questions() result wrong for case E: {count_result_e}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"\n{'=' * 70}\nRESULTS: {PASS} passed, {FAIL} failed\n{'=' * 70}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
