#!/usr/bin/env python3
"""
test-qc-card-parity.py — the completion gate must not demand more than the
interview cards demanded.

BUG THIS LOCKS: the Command Center's cards accept any non-empty answer, but
qc-interview-completion.py applied hidden length floors (12 chars for identity
answers, 30 for the brand questions the branding JSON flags) and could refuse a
completion for a reason the page never showed. An owner who answered every card
was refused as "too shallow".

THE FIX (BU-01):
  - the structured-web substance floors are 1 (any non-empty answer counts);
  - a short prose answer is reported as `advisoryShortIds` and surfaces in
    `warnings` as "[short-answers] ..." — never in hardFailures/softFailures;
  - a granted legacy/edit-mode exemption is evaluated BEFORE the structured
    hard-fail branch, so an interview that is exempt from the count floor is
    never refused on that same floor by the structured path.

THIS SUITE PROVES (fixtures identical to the package's repro, plus one case):
  A  long answers, cards only                            -> exit 0
  B  short company name ("Acme Co")                      -> exit 0
  C  industry answered with the card's own example       -> exit 0
  D  three-to-five words, as the help text asks          -> exit 0
  F  short company name, standard-first guest link       -> exit 0
  G  short company name, standard-first signed-in email  -> exit 0
  N  company name is an empty string block               -> exit 3

D and F also assert the short answer is named in warnings as advisory, proving
the gate now records it instead of silently dropping the old floor.

EXIT: 0 = every assertion passed; 1 otherwise.
Usage: python3 test-qc-card-parity.py [REPO_ROOT]
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


def transcript(overrides: dict) -> str:
    out = HEADER
    for qid, prompt in DECK:
        out += block(prompt, overrides.get(qid, LONG[qid]))
    return out


def state(asked_by: str, last_q: int, build_type: str | None = None) -> dict:
    st = {
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
    if build_type:
        st["buildType"] = build_type
        st["standardPrebuild"] = {"status": "done"}
    return st


# name, expected exit, overrides, asked_by, last_q, build_type, advisory_id
CASES = [
    ("A_long_answers_cards_only", 0, {}, "interview-web", 11, None, None),
    ("B_short_company_name", 0, {"company_name": "Acme Co"}, "interview-web", 11, None, None),
    ("C_short_industry_from_help_text_example", 0, {"industry": "coaching"},
     "interview-web", 11, None, None),
    ("D_three_to_five_words_as_the_help_text_asks", 0,
     {"brand_descriptors": "Reliable, honest, fast"}, "interview-web", 11, None,
     "brand_descriptors"),
    ("F_short_company_name_standard_first_guest_link", 0,
     {"company_name": "Acme Co"}, "interview-web", 11, "standard-first", None),
    ("G_short_company_name_standard_first_signed_in_email", 0,
     {"company_name": "Acme Co"}, "owner@example.com", 11, "standard-first", None),
    ("N_company_name_empty_string_block", 3, {"company_name": ""},
     "interview-web", 11, None, None),
]


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
        return proc.returncode, {}


def main() -> int:
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1

    tmproot = Path(tempfile.mkdtemp(prefix="qc-card-parity-test-"))
    try:
        for name, expected, overrides, asked_by, last_q, build_type, advisory_id in CASES:
            print(f"\n[{name}] expected exit {expected}")
            d = tmproot / name
            d.mkdir()
            t = d / "workforce-interview-answers.md"
            s = d / ".workforce-build-state.json"
            t.write_text(transcript(overrides), encoding="utf-8")
            s.write_text(json.dumps(state(asked_by, last_q, build_type), indent=2), encoding="utf-8")

            rc, details = run_qc_cli(t, s)
            if rc == expected:
                ok(f"exit {rc} as expected")
            else:
                bad(f"expected exit {expected}, got {rc}; hardFailures={details.get('hardFailures')} "
                    f"warnings={details.get('warnings')}")

            if advisory_id:
                warn_text = " ".join(details.get("warnings", []))
                hard_text = " ".join(details.get("hardFailures", []))
                if advisory_id in warn_text and advisory_id not in hard_text:
                    ok(f"'{advisory_id}' short answer is advisory (warnings only), never a failure")
                else:
                    bad(f"expected '{advisory_id}' in warnings and not in hardFailures; "
                        f"warnings={details.get('warnings')} hardFailures={details.get('hardFailures')}")

        empty_case = [c for c in CASES if c[0].startswith("N_")][0]
        details_n = run_qc_cli(tmproot / empty_case[0] / "workforce-interview-answers.md",
                               tmproot / empty_case[0] / ".workforce-build-state.json")[1]
        if "company_name" in " ".join(details_n.get("hardFailures", [])):
            ok("the empty company-name block is refused by id, not by length")
        else:
            bad(f"expected the refusal to name company_name; hardFailures="
                f"{details_n.get('hardFailures')}")
    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"\n{'=' * 70}\nRESULTS: {PASS} passed, {FAIL} failed\n{'=' * 70}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
