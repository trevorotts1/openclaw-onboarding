#!/usr/bin/env python3
"""
test-qc-question-count-structured-coverage.py — lock for the 2026-07-30
check #1 (question count) coverage-aware fix. Fourth defect of this exact
shape in this file (after the transcript-path fix / PR #772, the
mandatory-fields fix / PR #775, and the nudge-cadence fix / PR #777): a check
that measures the wrong proxy for the structured-web interview path.

BUG THIS LOCKS: count_questions() counts RAW **Q:** blocks and build_verdict()
required 25-35 of them for EVERY interview, regardless of how it was
conducted. That is the right proxy for a free-form, agent-led conversational
(Telegram) interview, but the Command Center's STRUCTURED WEB DECK has an
entire canonical question set of only ~11 questions (2 identity + 8 branding +
1 operations — see qc.IDENTITY_QUESTIONS_CANONICAL / branding-questions.json /
qc.OPERATIONS_QUESTIONS_CANONICAL). A client who substantively answers EVERY
one of those 11 questions can never reach 25 raw blocks without the
interviewer drilling an already-answered question again for zero new
coverage. Verified on a real client transcript (rescue-<client>):
11/11 canonical questions matched, every required branding field answered with
534-921 real characters, yet only 18-19 raw blocks (a couple of fields were
drilled multiple rounds) — HARD-FAILED as "too shallow" on an interview that
was, by every other measure, complete.

THE FIX: is_structured_web_interview(state) reads
state.interviewProgress.lastQuestionAskedBy — a field the Command Center's
/api/interview/answer route (the structured web deck's OWN submission
endpoint) ALREADY stamps with the literal "interview-web" whenever no
authenticated-operator identity is present (the normal case for a client
filling out cards themselves), and the conversational Telegram-agent flow
ALREADY stamps with the real agent name instead (see SKILL.md's
update-interview-state.sh --asked-by "$AGENT_NAME" usage). No new config flag.
For an interview so identified, check_structured_coverage() replaces raw count
with coverage + substance of the canonical set; the conversational path's
25-35 standard (and its legacy/tailored exemptions) is completely UNCHANGED.

THIS SUITE PROVES:
  U1  FULL-COVERAGE STRUCTURED INTERVIEW PASSES: askedBy=interview-web,
      every canonical question (11 total) answered with real substance,
      including realistic multi-round drilling on two fields (mirroring the
      proven fixture: customer_feeling x6, brand_voice x3) -> raw count lands
      at 18, well outside 25-35 -> full gate verdict is still PASS.
  U2  SHALLOW STRUCTURED INTERVIEW STILL FAILS: askedBy=interview-web, one
      required canonical question ('industry') is NEVER asked at all and
      another required one ('customer_feeling') is answered with a trivial
      one-word non-answer -> full gate verdict is FAIL, and the hard failure
      names both gaps by id.
  U3  CONVERSATIONAL, GENUINELY TOO FEW, STILL FAILS: askedBy is a real agent
      name (never "interview-web"), raw count is ~10 (well under 24), no
      legacy/tailored signal recorded -> still HARD FAILS under the existing,
      UNCHANGED raw-count standard.
  U4  RICH CONVERSATIONAL STILL PASSES (no regression): askedBy is a real
      agent name, a realistic 28-question transcript -> full gate verdict is
      still PASS, exactly as before this fix.
  U5  BLEED TEST: monkeypatch check_structured_coverage() to always report
      complete=True regardless of input, re-run U2's shallow fixture directly
      (in-process, so the monkeypatch takes effect) -> the genuine gap is NO
      LONGER caught (mutated verdict flips to PASS) -> proves U2 exercises the
      real coverage logic, not a rubber-stamp. Restore -> U2's gap is caught
      again.

NEVER prints transcript answer content beyond short synthetic fixture strings
that are never real client business answers — only counts, ids, and verdicts.
No client box touched; every fixture lives under a tempdir or in-memory.

EXIT: 0 = every assertion passed; 1 otherwise.
Usage: python3 test-qc-question-count-structured-coverage.py [REPO_ROOT]
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
QC_SCRIPT = SCRIPTS / "qc-interview-completion.py"
BRANDING_Q = REPO / "23-ai-workforce-blueprint" / "interview" / "branding-questions.json"
JARGON_LIST = REPO / "23-ai-workforce-blueprint" / "interview" / "forbidden-jargon.json"

sys.path.insert(0, str(SCRIPTS))

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


def load_qc_module():
    spec = importlib.util.spec_from_file_location("qc_under_test_count", str(QC_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BQ = json.loads(BRANDING_Q.read_text(encoding="utf-8"))
_BRANDING_QUESTIONS = _BQ["questions"]

# Synthetic (non-client) placeholder prose, >=30 chars each, for canonical
# branding questions the JSON itself flags (via interviewGuidance) as needing a
# specific, non-generic answer.
_SUBSTANTIVE_BODIES = {
    "brand_evokes": (
        "A grounded, quietly confident feeling -- like a steady hand stepped in "
        "and everything is now handled with care instead of being rushed."
    ),
    "customer_feeling": (
        "Relieved and capable again, like they finally have their arms around "
        "something that used to feel completely unmanageable on their own."
    ),
    "brand_descriptors": (
        "Reliable, direct, deeply prepared -- the ones who actually answer the "
        "phone and explain the why behind every decision instead of just billing."
    ),
    "brand_voice": (
        "Warm but plainspoken -- we say 'here is exactly what happens next' "
        "instead of burying the answer in jargon or a hedge."
    ),
    "ideal_customer": (
        "Small rescue operators who have outgrown spreadsheets but are wary of a "
        "system that locks them into a long contract with a dedicated IT hire."
    ),
    "unique_differentiator": (
        "We pick up the phone and tell people the truth even when the truth is "
        "that they do not need us yet -- that is the whole differentiator."
    ),
}
for _fid, _body in _SUBSTANTIVE_BODIES.items():
    assert len(_body) >= 30, f"{_fid} fixture body must be >=30 chars, got {len(_body)}"

_NON_SUBSTANCE_DEFAULTS = {
    "brand_primary_color": "#1E3A8A",
    "brand_logo": "https://example.com/logo.png",
}

_IDENTITY_DEFAULTS = {
    "company_name": "Acme Rescue Co",
    "industry": "Pet rescue and animal welfare services",
}
_OPERATIONS_DEFAULTS = {
    "command_center_name": "Mission Control",
}


def _qa_block(question: str, answer: str) -> str:
    return f"**Q:** {question}\n**A:** {answer}\n"


def build_structured_transcript(qc, omit_ids=(), shallow_ids=(), drill_extra=None) -> str:
    """
    Build a **Q:**/**A:** transcript covering the canonical structured deck
    (identity -> branding -> operations), pulling ids/prompts straight from the
    qc module's OWN canonical constants + the real branding-questions.json --
    never a second hand-copy of question text, so this fixture can never drift
    from what check_structured_coverage() actually matches against.

    omit_ids:    canonical ids left COMPLETELY unanswered (never asked at all).
    shallow_ids: canonical ids answered, but with a trivial/generic one-word
                 reply below the relevant substance floor.
    drill_extra: {id: [extra_answer, ...]} -- additional answered ROUNDS for
                 that id, mirroring a real multi-round drill (the proven real
                 fixture drilled customer_feeling x6, brand_voice x3).
    """
    drill_extra = drill_extra or {}
    lines = ["# Workforce Interview Answers", "", "Started: test fixture", "", "---", ""]

    def emit(qid, prompt, default_answer, needs_substance):
        if qid in omit_ids:
            return
        answer = default_answer
        if qid in shallow_ids:
            answer = "Professional" if needs_substance else "no"
        lines.append(_qa_block(prompt, answer))
        lines.append("---")
        lines.append("")
        for extra in drill_extra.get(qid, []):
            lines.append(_qa_block(prompt, extra))
            lines.append("---")
            lines.append("")

    for q in qc.IDENTITY_QUESTIONS_CANONICAL:
        emit(q["id"], q["prompt"], _IDENTITY_DEFAULTS[q["id"]], needs_substance=False)

    for q in _BRANDING_QUESTIONS:
        qid = q["id"]
        needs_substance = bool(q.get("interviewGuidance"))
        if qid in _SUBSTANTIVE_BODIES:
            default = _SUBSTANTIVE_BODIES[qid]
        else:
            default = _NON_SUBSTANCE_DEFAULTS.get(qid, "A short real answer")
        emit(qid, q["prompt"], default, needs_substance=needs_substance)

    for q in qc.OPERATIONS_QUESTIONS_CANONICAL:
        emit(q["id"], q["prompt"], _OPERATIONS_DEFAULTS[q["id"]], needs_substance=False)

    return "\n".join(lines)


def build_conversational_transcript(n_questions: int) -> str:
    """A realistic FREE-FORM conversational transcript: n_questions filler
    Q/A blocks whose question text does NOT normalize-match any canonical
    structured prompt (a real Telegram-agent conversation), PLUS the 5
    required branding canonical blocks (an agent may ask the exact canonical
    wording too -- SKILL.md drives from the same question bank) so check #3
    (mandatory fields) passes independently of this test's target (check #1)."""
    lines = ["# Workforce Interview Answers", "", "Started: test fixture", "", "---", ""]
    for q in _BRANDING_QUESTIONS:
        if not q.get("required"):
            continue
        answer = _SUBSTANTIVE_BODIES.get(q["id"], "A short real answer, still substantive enough")
        lines.append(_qa_block(q["prompt"], answer))
        lines.append("---")
        lines.append("")
    for i in range(1, n_questions + 1):
        lines.append(_qa_block(
            f"Free-form conversational question {i}: tell me about area {i} of your operations?",
            f"My detailed answer for area {i} is that we focus on careful, hands-on "
            f"attention to each client's specific situation and needs.",
        ))
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _base_state(asked_by: str, last_question_number: int = 11) -> dict:
    """
    FIXTURE FIX: `last_question_number` used to be hardcoded to 11 for every
    case. That is not a neutral default — it is the exact "frozen counter"
    signature the counter-vs-transcript disagreement HARD FAIL exists to catch
    (qc-interview-completion.py, 2026-06-10 anti-fabrication decision). Any case
    whose transcript held materially more than 11 Q-blocks therefore hard-failed
    on the DISAGREEMENT, never reaching the count/coverage logic this suite is
    meant to exercise — so U1 (19 blocks) and U4 (29 blocks) had been red since
    the day this file was written, for a reason unrelated to what they assert.

    Each case now passes a counter consistent with its own transcript. The
    disagreement guard is NOT weakened anywhere — it keeps its full strength in
    production, is still covered by test-interview-completion-evidence-gate.sh,
    and U6 below now pins it directly in this file as well.
    """
    return {
        "interviewComplete": True,
        "companyName": "Acme Rescue Co",
        "industry": "Pet Rescue",
        "ownerChat": "12345",
        "agentName": "Rescue Agent",
        "departments": [{"id": "operations", "status": "done"}],
        "interviewProgress": {
            "lastQuestionNumber": last_question_number,
            "lastQuestionAskedBy": asked_by,
        },
    }


def run_qc_cli(transcript_path: Path, state_path: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(QC_SCRIPT),
         "--transcript", str(transcript_path),
         "--state", str(state_path),
         "--jargon-list", str(JARGON_LIST),
         "--branding-questions", str(BRANDING_Q),
         "--repo-root", str(REPO),
         "--no-context-map",
         "--format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return json.loads(proc.stdout)
    except Exception:
        print(f"    (non-JSON stdout, rc={proc.returncode}): {proc.stdout[:500]}", file=sys.stderr)
        print(f"    stderr: {proc.stderr[:500]}", file=sys.stderr)
        return {}


def main():
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1

    qc = load_qc_module()

    import tempfile
    import shutil

    tmproot = Path(tempfile.mkdtemp(prefix="qc-question-count-structured-test-"))
    try:
        # ── U1: FULL-COVERAGE STRUCTURED INTERVIEW PASSES ────────────────────
        print("\n[U1] Full-coverage structured interview (askedBy=interview-web, "
              "all 11 canonical questions answered with substance) -> PASS even at ~18 raw blocks")
        full_transcript = build_structured_transcript(
            qc,
            drill_extra={
                "customer_feeling": [_SUBSTANTIVE_BODIES["customer_feeling"]] * 5,  # -> 6 total rounds
                "brand_voice": [_SUBSTANTIVE_BODIES["brand_voice"]] * 2,             # -> 3 total rounds
            },
        )
        raw_blocks = full_transcript.count("**Q:**")
        state_path_1 = tmproot / "state1.json"
        # Counter consistent with THIS fixture's own transcript (see _base_state).
        state_path_1.write_text(
            json.dumps(_base_state("interview-web", last_question_number=raw_blocks)),
            encoding="utf-8",
        )
        transcript_path_1 = tmproot / "transcript1.md"
        transcript_path_1.write_text(full_transcript, encoding="utf-8")
        details_1 = run_qc_cli(transcript_path_1, state_path_1)

        if details_1.get("verdict") == "PASS" and 25 > details_1.get("questionCount", 0) >= 11:
            ok(f"full gate verdict PASS on a genuinely-complete structured interview "
               f"(raw questionCount={details_1.get('questionCount')}, well outside 25-35; "
               f"structuredCoverage={details_1.get('structuredCoverage', {}).get('result', {}).get('answeredIds', [])})")
        else:
            bad(f"expected verdict=PASS with raw count < 25, got verdict={details_1.get('verdict')!r} "
                f"questionCount={details_1.get('questionCount')} hardFailures={details_1.get('hardFailures')}")

        sc1 = details_1.get("structuredCoverage", {})
        if sc1.get("isStructuredWebInterview") and sc1.get("result", {}).get("complete"):
            ok("structuredCoverage.isStructuredWebInterview=True and result.complete=True "
               "(the coverage standard was actually applied, not incidentally passing)")
        else:
            bad(f"expected structuredCoverage to be applied and complete, got: {sc1}")

        if raw_blocks < 25:
            ok(f"sanity: the fixture's raw **Q:** block count ({raw_blocks}) is itself outside "
               f"25-35, proving this PASS could NOT have come from the old raw-count standard")
        else:
            bad(f"fixture sanity check failed: raw_blocks={raw_blocks} is NOT below 25 -- "
                f"this test would not distinguish the fix from the old behavior")

        # ── U2: SHALLOW STRUCTURED INTERVIEW STILL FAILS ─────────────────────
        print("\n[U2] Shallow structured interview (askedBy=interview-web, 'industry' never "
              "asked + 'customer_feeling' answered with a one-word non-answer) -> still FAILS, naming both gaps")
        shallow_transcript = build_structured_transcript(
            qc, omit_ids={"industry"}, shallow_ids={"customer_feeling"},
        )
        state_path_2 = tmproot / "state2.json"
        state_path_2.write_text(json.dumps(_base_state("interview-web")), encoding="utf-8")
        transcript_path_2 = tmproot / "transcript2.md"
        transcript_path_2.write_text(shallow_transcript, encoding="utf-8")
        details_2 = run_qc_cli(transcript_path_2, state_path_2)

        hard_fail_text = " ".join(details_2.get("hardFailures", []))
        if (details_2.get("verdict") == "FAIL" and details_2.get("exit_code", details_2.get("exitCode", 3)) != 0
                and "industry" in hard_fail_text and "customer_feeling" in hard_fail_text
                and "structured-coverage" in hard_fail_text):
            ok(f"shallow structured interview correctly FAILS, naming both gaps: {hard_fail_text[:300]}")
        else:
            bad(f"expected FAIL naming 'industry' and 'customer_feeling' in a "
                f"[structured-coverage] hard failure, got verdict={details_2.get('verdict')!r} "
                f"hardFailures={details_2.get('hardFailures')}")

        # ── U3: CONVERSATIONAL, GENUINELY TOO FEW, STILL FAILS ───────────────
        print("\n[U3] Conversational interview, genuinely too few questions (askedBy=real agent "
              "name, ~10 raw blocks) -> still HARD FAILS under the unchanged raw-count standard")
        few_transcript = build_conversational_transcript(n_questions=3)  # 5 branding + 3 filler = 8
        state_path_3 = tmproot / "state3.json"
        state_path_3.write_text(json.dumps(_base_state("Rescue Agent")), encoding="utf-8")
        transcript_path_3 = tmproot / "transcript3.md"
        transcript_path_3.write_text(few_transcript, encoding="utf-8")
        details_3 = run_qc_cli(transcript_path_3, state_path_3)

        hard_fail_text_3 = " ".join(details_3.get("hardFailures", []))
        if (details_3.get("verdict") == "FAIL"
                and details_3.get("questionCount", 99) < 24
                and "outside the acceptable range" in hard_fail_text_3
                and not details_3.get("structuredCoverage", {}).get("isStructuredWebInterview")):
            ok(f"conversational interview with genuinely too few questions "
               f"(questionCount={details_3.get('questionCount')}, askedBy=Rescue Agent) still "
               f"HARD FAILS under the existing raw-count standard, unchanged by this fix")
        else:
            bad(f"expected the conversational path's raw-count standard to still hard-fail, got: "
                f"verdict={details_3.get('verdict')!r} questionCount={details_3.get('questionCount')} "
                f"structuredCoverage={details_3.get('structuredCoverage')}")

        # ── U4: RICH CONVERSATIONAL STILL PASSES (no regression) ────────────
        print("\n[U4] Rich conversational interview (askedBy=real agent name, realistic "
              "28-question transcript) -> still PASSES, exactly as before this fix")
        rich_transcript = build_conversational_transcript(n_questions=23)  # 5 branding + 23 filler = 28
        state_path_4 = tmproot / "state4.json"
        # Counter consistent with THIS fixture's own transcript (see _base_state).
        state_path_4.write_text(
            json.dumps(_base_state(
                "Rescue Agent",
                last_question_number=rich_transcript.count("**Q:**"),
            )),
            encoding="utf-8",
        )
        transcript_path_4 = tmproot / "transcript4.md"
        transcript_path_4.write_text(rich_transcript, encoding="utf-8")
        details_4 = run_qc_cli(transcript_path_4, state_path_4)

        if (details_4.get("verdict") == "PASS"
                and not details_4.get("structuredCoverage", {}).get("isStructuredWebInterview")):
            ok(f"rich conversational interview still PASSES (questionCount="
               f"{details_4.get('questionCount')}, askedBy=Rescue Agent, structured path NOT engaged) "
               f"-- no regression to the path that already worked")
        else:
            bad(f"expected the rich conversational interview to still PASS, got "
                f"verdict={details_4.get('verdict')!r} hardFailures={details_4.get('hardFailures')} "
                f"structuredCoverage={details_4.get('structuredCoverage')}")

        # ── U5: BLEED TEST ────────────────────────────────────────────────────
        print("\n[U5] bleed test: force check_structured_coverage() to always report complete=True")
        state_shallow = _base_state("interview-web")
        count_result = qc.count_questions(shallow_transcript, state_shallow)
        jargon_hits = []
        field_result = qc.check_mandatory_fields(state_shallow, BRANDING_Q, shallow_transcript)
        nudge_result = qc.check_nudges_wired(REPO)
        legacy_result = qc.is_legacy_interview(shallow_transcript, state_shallow, False)

        real_coverage = qc.check_structured_coverage(shallow_transcript, BRANDING_Q)
        verdict_real, exit_real, details_real = qc.build_verdict(
            count_result, jargon_hits, field_result, nudge_result,
            fabrication_result=None, legacy_result=legacy_result, legacy_substance=None,
            state=state_shallow, web_store_result=None,
            structured_coverage=real_coverage,
        )
        if verdict_real == "FAIL":
            ok("pre-mutation control: the real check_structured_coverage() still fails the "
               "shallow fixture in-process (matches U2's CLI result)")
        else:
            bad(f"pre-mutation control unexpectedly passed: verdict={verdict_real}")

        orig_fn = qc.check_structured_coverage

        def _fake_always_complete(transcript, branding_questions_path):  # noqa: ANN001
            real = orig_fn(transcript, branding_questions_path)
            real["complete"] = True
            real["missingRequiredIds"] = []
            real["shallowRequiredIds"] = []
            return real

        qc.check_structured_coverage = _fake_always_complete
        try:
            mutated_coverage = qc.check_structured_coverage(shallow_transcript, BRANDING_Q)
            verdict_mut, exit_mut, details_mut = qc.build_verdict(
                count_result, jargon_hits, field_result, nudge_result,
                fabrication_result=None, legacy_result=legacy_result, legacy_substance=None,
                state=state_shallow, web_store_result=None,
                structured_coverage=mutated_coverage,
            )
            if verdict_mut == "PASS":
                ok(f"mutation DOES flip the result: forcing complete=True makes the SAME shallow "
                   f"fixture verdict PASS (exit={exit_mut}) -- proves U2 exercises the real coverage "
                   f"logic, not a rubber-stamp")
            else:
                bad(f"mutating check_structured_coverage() to always-complete had NO EFFECT "
                    f"(verdict={verdict_mut}) -- the check may not be wired to the real function")
        finally:
            qc.check_structured_coverage = orig_fn

        restored_coverage = qc.check_structured_coverage(shallow_transcript, BRANDING_Q)
        verdict_restored, exit_restored, details_restored = qc.build_verdict(
            count_result, jargon_hits, field_result, nudge_result,
            fabrication_result=None, legacy_result=legacy_result, legacy_substance=None,
            state=state_shallow, web_store_result=None,
            structured_coverage=restored_coverage,
        )
        if verdict_restored == "FAIL":
            ok("restoring the real check_structured_coverage() re-confirms the genuine gap is "
               "caught again -- the suite is not vacuously passing")
        else:
            bad(f"restore did not return to catching the real gap: verdict={verdict_restored}")

        # ── U6: THE DISAGREEMENT HARD FAIL STILL BITES ───────────────────────
        # Guard for the fixture change in _base_state(). The old fixture pinned
        # lastQuestionNumber=11 for every case, which meant U1/U4 were failing on
        # the counter-vs-transcript DISAGREEMENT rather than on anything this
        # suite asserts. Those two cases now carry a consistent counter -- so this
        # case exists to prove that consistency did NOT come from the guard going
        # soft. Same PASSING fixture as U4, counter frozen back to 11: it MUST
        # hard-fail, and it must fail specifically on the disagreement.
        print("\n[U6] anti-regression: a frozen lastQuestionNumber still HARD FAILS "
              "(the 2026-06-10 anti-fabrication guard is intact, not weakened by the U1/U4 fixture fix)")
        state_path_6 = tmproot / "state6.json"
        state_path_6.write_text(
            json.dumps(_base_state("Rescue Agent", last_question_number=11)),
            encoding="utf-8",
        )
        details_6 = run_qc_cli(transcript_path_4, state_path_6)  # U4's PASSING transcript
        hard_fail_text_6 = " ".join(details_6.get("hardFailures", []))
        if details_6.get("verdict") == "FAIL" and "disagree" in hard_fail_text_6:
            ok(f"frozen counter (11) against the same {details_6.get('questionCount')}-question "
               f"transcript that PASSES in U4 still HARD FAILS on the disagreement -- the guard "
               f"has teeth and the U1/U4 fixture fix did not launder it")
        else:
            bad(f"the counter-vs-transcript disagreement hard fail did NOT fire on a frozen "
                f"counter -- the guard may have been weakened. verdict={details_6.get('verdict')!r} "
                f"hardFailures={details_6.get('hardFailures')}")

    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"\n{'='*70}\nRESULTS: {PASS} passed, {FAIL} failed\n{'='*70}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
