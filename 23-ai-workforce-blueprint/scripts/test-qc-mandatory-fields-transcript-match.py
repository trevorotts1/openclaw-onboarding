#!/usr/bin/env python3
"""
test-qc-mandatory-fields-transcript-match.py — lock for the 2026-07-30
check_mandatory_fields() fix (Cassandra Henriquez / rescue-cassandra-henriquez
incident).

BUG THIS LOCKS: check_mandatory_fields() in qc-interview-completion.py used to
read the five branding required fields (brand_evokes, customer_feeling,
brand_descriptors, ideal_customer, unique_differentiator) ONLY from build-state
(state[fid] / state["brandingAnswers"][fid] / state["interview"][fid]). The
normal interview flow never writes those keys to build-state — a free-text
branding answer is logged ONLY to workforce-interview-answers.md via
log_answer(). A verified real client transcript had all five answered (each
534-921 chars) yet a 90-key build-state with NONE of the five branding keys
anywhere in it, so the gate reported all five "missing" for every client,
unconditionally, regardless of what they actually answered.

THE FIX: check_mandatory_fields() now ALSO matches the transcript's **Q:**/
**A:** blocks against the canonical branding-questions.json prompts, using
byte-identical ports of the Command Center's OWN matching semantics
(seam.ts:parseAnswerBlocks(), structured-progress.ts:normPrompt()/
computeAnsweredIds()) — see parse_answer_blocks() / compute_answered_ids() /
norm_prompt() in qc-interview-completion.py.

THIS SUITE PROVES:
  U1  BEFORE (pre-fix behavior reproduced): with transcript ignored (as the
      original code always did), a transcript containing all five answered
      fields is STILL reported as all-five-missing when build-state doesn't
      mirror them — literally the bug, reproduced via the SAME function with
      the transcript argument withheld.
  U2  AFTER: the SAME fixture, now passing the transcript through (as the
      real call site in main() does) -> zero of the five reported missing.
  U3  FAIL-CLOSED (a): a transcript genuinely missing two of the five
      canonical answers (and build-state also lacking them) -> exactly those
      two are reported missing. Real gaps still fail, named precisely.
  U4  FAIL-CLOSED (b): empty/unreadable transcript, state lacking all five
      -> all five reported missing (never silently passes on an unreadable
      transcript).
  U5  ENCRYPTED PATH: the SAME fixture transcript, encrypted (.enc,
      chacha20-poly1305, same wire format U048 uses) and run through the REAL
      qc-interview-completion.py CLI end-to-end, reports the identical
      missingFields as the plaintext run.
  U6  END-TO-END PASS: a realistic, full (28-question) transcript containing
      the five branding answers plus company/industry/owner/agent structural
      facts in build-state (but NOT the five branding keys) -> full gate
      verdict is PASS. Proves a genuinely-complete interview is no longer
      blocked.
  U7  BLEED TEST: monkeypatch compute_answered_ids() to always report every
      canonical id as answered (regardless of input) -> U3's two genuinely
      missing fields are NO LONGER DETECTED (the mutated check wrongly reports
      zero missing) -> proves the test is exercising real matching logic, not
      rubber-stamping. Restore -> U3 reconfirmed (still catches the two real
      gaps).

NEVER prints the fixture answer text — only counts, field names, and match
booleans. No client box touched; every fixture lives under a tempdir.

EXIT: 0 = every assertion passed; 1 otherwise.
Usage: python3 test-qc-mandatory-fields-transcript-match.py [REPO_ROOT]
"""

import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
QC_SCRIPT = SCRIPTS / "qc-interview-completion.py"
BRANDING_Q = REPO / "23-ai-workforce-blueprint" / "interview" / "branding-questions.json"
JARGON_LIST = REPO / "23-ai-workforce-blueprint" / "interview" / "forbidden-jargon.json"

sys.path.insert(0, str(SCRIPTS))

PASS = 0
FAIL = 0
TEST_SECRET = "u048-followon-test-secret-do-not-use-in-prod-2026"


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


def load_qc_module():
    """Fresh import of qc-interview-completion.py per call (module-level regex
    constants are harmless to reload; keeps each test isolated)."""
    spec = importlib.util.spec_from_file_location("qc_under_test", str(QC_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Canonical branding prompts (must match branding-questions.json EXACTLY —
# pulled from the file itself, never hardcoded twice, so this suite can never
# silently drift from the canonical source). ─────────────────────────────────
_BQ = json.loads(BRANDING_Q.read_text(encoding="utf-8"))
_REQUIRED_QUESTIONS = [q for q in _BQ["questions"] if q.get("required")]
_REQUIRED_IDS = [q["id"] for q in _REQUIRED_QUESTIONS]
assert set(_REQUIRED_IDS) == {
    "brand_evokes", "customer_feeling", "brand_descriptors",
    "ideal_customer", "unique_differentiator",
}, f"branding-questions.json required set changed unexpectedly: {_REQUIRED_IDS}"

# Realistic-length (534-921 char range, matching the real verified fixture)
# owner-authored answer bodies. Content is inert placeholder prose — never the
# real client's words.
_ANSWER_BODIES = {
    "brand_evokes": (
        "I want people to feel a sense of calm confidence the moment they interact "
        "with us — like they can finally exhale because someone competent is handling "
        "the details they've been carrying alone. Not corporate-cold, not falsely "
        "cheerful — grounded, warm, capable. The kind of feeling you get when a friend "
        "who actually knows what they're doing steps in and says 'I've got this, here's "
        "exactly what happens next.' That steadiness is the whole brand promise, and it "
        "should carry through every single touchpoint, from the first phone call to the "
        "last invoice, without ever once feeling rehearsed or scripted."
    ),
    "customer_feeling": (
        "By the time we're done working together I want them to feel like they finally "
        "have their arms around something that used to feel unmanageable. Relieved, "
        "yes, but more specifically — capable again. Like they got their own competence "
        "handed back to them instead of just being told to relax. Not 'happy', not "
        "generic satisfaction — the specific feeling of having untangled a real knot."
    ),
    "brand_descriptors": (
        "Reliable, direct, deeply prepared, unflashy, the person who actually answers "
        "the phone. Clients tell their friends we're 'the ones who just handle it' — no "
        "drama, no jargon, no disappearing after the sale. A few have said we're the "
        "first vendor who ever explained WHY something was happening instead of just "
        "billing for it, and that honesty is the descriptor that comes up most."
    ),
    "ideal_customer": (
        "Small business owners, usually five to twenty employees, who have grown past "
        "spreadsheets but are terrified of a system that locks them in or requires a "
        "dedicated IT hire. They come to us specifically because we onboard them "
        "personally instead of handing them a help-center link, and because we've been "
        "burned by the same overpriced enterprise vendors they're currently fleeing — "
        "so we build for the exact frustration we lived through ourselves."
    ),
    "unique_differentiator": (
        "Honestly? We actually pick up the phone, and we tell people the truth even "
        "when the truth is 'you don't need this yet.' Everyone else in this space "
        "upsells first and explains never. The real reason people stay is that we've "
        "turned down revenue more than once because it wasn't the right fit for that "
        "client, and word travels fast in a small industry — that's the differentiator "
        "we'd tell a friend, not the polished line we'd tell a prospect."
    ),
}
for _fid, _body in _ANSWER_BODIES.items():
    # Realistic-length prose (the proven real fixture ranged 534-921 chars per field);
    # a generous band, not an exact match — the point is non-trivial, paragraph-length
    # owner answers, not the precise byte count of a real client's words.
    assert 300 <= len(_body) <= 1200, f"{_fid} answer body out of the realistic 300-1200 char range ({len(_body)})"


def _qa_block(question: str, answer: str) -> str:
    return f"**Q:** {question}\n**A:** {answer}\n"


def build_branding_blocks(omit_ids=()) -> str:
    """Build **Q:**/**A:** blocks (seam.ts format) for every REQUIRED branding
    question except any id listed in `omit_ids` (used for the fail-closed
    genuine-gap test). Blocks are separated by '---' lines exactly like
    build-workforce.py's log_answer() writes them."""
    parts = []
    for q in _REQUIRED_QUESTIONS:
        if q["id"] in omit_ids:
            continue
        parts.append(_qa_block(q["prompt"], _ANSWER_BODIES[q["id"]]))
    return "\n---\n".join(parts) + ("\n---\n" if parts else "")


def build_full_transcript(n_filler_questions=23, omit_ids=()) -> str:
    """A realistic transcript: header + the branding blocks + filler
    conversational Q/A to reach a normal 25-35 question count for the
    end-to-end PASS proof."""
    lines = ["# Workforce Interview Answers", "", "---", ""]
    lines.append(build_branding_blocks(omit_ids=omit_ids))
    for i in range(1, n_filler_questions + 1):
        lines.append(_qa_block(
            f"Question number {i}: tell me about area {i} of your business operations?",
            f"My detailed answer for question {i} is that we focus on helping clients "
            f"succeed through careful attention to their specific situation and needs.",
        ))
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


STATE_NO_BRANDING_KEYS = {
    # Structural facts a real interview DOES persist to build-state (per the
    # proven Cassandra fixture: 90 keys present, but NONE of the five branding
    # keys, no brandingAnswers map, no interview sub-object).
    "interviewComplete": True,
    "companyName": "Acme Rescue Co",
    "industry": "Pet Rescue",
    "ownerChat": "12345",
    "agentName": "Rescue Agent",
    "departments": [{"id": "operations", "status": "done"}],
    "interviewProgress": {"lastQuestionNumber": 28},
    # Explicitly absent on purpose: brandingAnswers, interview, and all five
    # top-level branding keys — this is the proven real-world shape.
}


def encrypt_fixture(plaintext: str, secret: str = TEST_SECRET) -> str:
    """Same wire format as blackceo-command-center crypto.ts / U048:
    'enc:v1:' + base64(nonce(12) || tag(16) || ciphertext), chacha20-poly1305."""
    key = hashlib.sha256(secret.strip().encode("utf-8")).digest()
    nonce = os.urandom(12)
    aead = ChaCha20Poly1305(key)
    ct_and_tag = aead.encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext, tag = ct_and_tag[:-16], ct_and_tag[-16:]
    envelope = nonce + tag + ciphertext
    return "enc:v1:" + base64.b64encode(envelope).decode("ascii")


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
        print(f"    (non-JSON stdout, rc={proc.returncode}): {proc.stdout[:300]}", file=sys.stderr)
        print(f"    stderr: {proc.stderr[:300]}", file=sys.stderr)
        return {}


def main():
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1

    tmproot = Path(tempfile.mkdtemp(prefix="qc-mandatory-fields-test-"))
    try:
        qc = load_qc_module()

        branding_only_transcript = build_branding_blocks()

        # ── U1: BEFORE — transcript withheld reproduces the pre-fix bug ──────
        print("\n[U1] BEFORE (pre-fix behavior): transcript withheld -> all five reported missing")
        result_before = qc.check_mandatory_fields(
            STATE_NO_BRANDING_KEYS, BRANDING_Q, transcript=""
        )
        missing_before = set(result_before["missing"]) & set(_REQUIRED_IDS)
        if missing_before == set(_REQUIRED_IDS):
            ok(f"reproduces the bug: all {len(_REQUIRED_IDS)} branding fields reported "
               f"missing when the transcript is not consulted (build-state alone, "
               f"exactly as check_mandatory_fields() behaved before this fix)")
        else:
            bad(f"expected all 5 required ids missing pre-fix, got: {sorted(missing_before)}")

        # ── U2: AFTER — same fixture, transcript wired in -> zero missing ───
        print("\n[U2] AFTER: same fixture with the transcript wired in -> zero of the five missing")
        result_after = qc.check_mandatory_fields(
            STATE_NO_BRANDING_KEYS, BRANDING_Q, transcript=branding_only_transcript
        )
        missing_after = set(result_after["missing"]) & set(_REQUIRED_IDS)
        if not missing_after:
            ok("all 5 branding fields recognized as answered via transcript match "
               "(build-state still has none of them)")
        else:
            bad(f"expected zero of the 5 required ids missing post-fix, got: {sorted(missing_after)}")

        # ── U3: FAIL-CLOSED (a) — two genuine gaps still fail, named exactly ──
        print("\n[U3] FAIL-CLOSED: transcript genuinely missing 2 of 5 -> exactly those 2 reported")
        omit = {"brand_evokes", "unique_differentiator"}
        partial_transcript = build_branding_blocks(omit_ids=omit)
        result_partial = qc.check_mandatory_fields(
            STATE_NO_BRANDING_KEYS, BRANDING_Q, transcript=partial_transcript
        )
        missing_partial = set(result_partial["missing"]) & set(_REQUIRED_IDS)
        if missing_partial == omit:
            ok(f"exactly the 2 genuinely-unanswered fields reported missing: {sorted(missing_partial)} "
               f"(the 3 genuinely-answered fields are NOT flagged)")
        else:
            bad(f"expected exactly {sorted(omit)} missing, got: {sorted(missing_partial)}")

        # ── U4: FAIL-CLOSED (b) — empty/unreadable transcript still fails closed ──
        print("\n[U4] FAIL-CLOSED: empty transcript, state lacking all five -> all five missing")
        result_empty = qc.check_mandatory_fields(
            STATE_NO_BRANDING_KEYS, BRANDING_Q, transcript=""
        )
        missing_empty = set(result_empty["missing"]) & set(_REQUIRED_IDS)
        if missing_empty == set(_REQUIRED_IDS):
            ok("an empty/unreadable transcript never silently passes — all 5 still reported missing")
        else:
            bad(f"expected all 5 missing for empty transcript, got: {sorted(missing_empty)}")

        # ── U5: ENCRYPTED PATH — identical result via the real CLI, plaintext vs .enc ──
        print("\n[U5] encrypted path: plaintext vs .enc transcript -> identical missingFields via the real CLI")
        full_transcript = build_full_transcript()
        state_path = tmproot / "state.json"
        state_path.write_text(json.dumps(STATE_NO_BRANDING_KEYS), encoding="utf-8")

        plain_path = tmproot / "transcript-plain.md"
        plain_path.write_text(full_transcript, encoding="utf-8")
        details_plain = run_qc_cli(plain_path, state_path)

        enc_path = tmproot / "transcript-enc.md.enc"
        enc_path.write_text(encrypt_fixture(full_transcript), encoding="utf-8")
        # Encrypted path needs the key material available; pass it via env.
        env = dict(os.environ)
        env["MC_INTERVIEW_SECRET"] = TEST_SECRET
        proc_enc = subprocess.run(
            [sys.executable, str(QC_SCRIPT),
             "--transcript", str(enc_path),
             "--state", str(state_path),
             "--jargon-list", str(JARGON_LIST),
             "--branding-questions", str(BRANDING_Q),
             "--repo-root", str(REPO),
             "--no-context-map",
             "--format", "json"],
            capture_output=True, text=True, env=env, timeout=60,
        )
        try:
            details_enc = json.loads(proc_enc.stdout)
        except Exception:
            details_enc = {}

        missing_plain = sorted(set(details_plain.get("missingFields", [])) & set(_REQUIRED_IDS))
        missing_enc = sorted(set(details_enc.get("missingFields", [])) & set(_REQUIRED_IDS))
        if not missing_plain and not missing_enc and missing_plain == missing_enc:
            ok("plaintext and .enc runs of the SAME fixture both report zero missing "
               "branding fields via the real CLI (identical behavior)")
        else:
            bad(f"plaintext missingFields={missing_plain} vs enc missingFields={missing_enc} "
                f"(expected both empty and equal); enc stderr={proc_enc.stderr[:200]}")
        if TEST_SECRET not in (proc_enc.stdout + proc_enc.stderr):
            ok("encryption secret not leaked into captured CLI output")
        else:
            bad("encryption secret LEAKED into captured CLI output")

        # ── U6: END-TO-END PASS — a genuinely-complete interview now PASSes ──
        print("\n[U6] end-to-end: realistic 28-question transcript -> full gate verdict PASS")
        if details_plain.get("verdict") == "PASS":
            ok(f"full gate verdict PASS on a realistic, genuinely-complete interview "
               f"(questionCount={details_plain.get('questionCount')})")
        else:
            bad(f"expected verdict=PASS, got verdict={details_plain.get('verdict')!r} "
                f"hardFailures={details_plain.get('hardFailures')}")

        # ── U7: BLEED TEST ────────────────────────────────────────────────────
        print("\n[U7] bleed test: force compute_answered_ids() to always report everything answered")
        orig_fn = qc.compute_answered_ids

        def _fake_always_answered(blocks, questions):  # noqa: ANN001
            return {q.get("id") for q in questions}

        qc.compute_answered_ids = _fake_always_answered
        try:
            mutated_result = qc.check_mandatory_fields(
                STATE_NO_BRANDING_KEYS, BRANDING_Q, transcript=partial_transcript
            )
            mutated_missing = set(mutated_result["missing"]) & set(_REQUIRED_IDS)
            if mutated_missing != omit:
                ok(f"mutation DOES flip U3's result (mutated missing={sorted(mutated_missing)} "
                   f"!= real gap {sorted(omit)}) — proves U3 exercises the real matching "
                   f"logic, not a rubber-stamp")
            else:
                bad("mutating compute_answered_ids() to always-answer had NO EFFECT on U3's "
                    "result — the check may not be wired to the real matcher (suspicious pass)")
        finally:
            qc.compute_answered_ids = orig_fn

        restored_result = qc.check_mandatory_fields(
            STATE_NO_BRANDING_KEYS, BRANDING_Q, transcript=partial_transcript
        )
        restored_missing = set(restored_result["missing"]) & set(_REQUIRED_IDS)
        if restored_missing == omit:
            ok("restoring the real compute_answered_ids() re-confirms the genuine 2-field "
               "gap is caught again — the suite is not vacuously passing")
        else:
            bad(f"restore did not return to catching the real gap: {sorted(restored_missing)}")

    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"\n{'='*70}\nRESULTS: {PASS} passed, {FAIL} failed\n{'='*70}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
