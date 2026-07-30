#!/usr/bin/env python3
"""
test-interview-transcript-decryption.py — U048 encrypted-transcript fix lock
(2026-07-30 incident on a client Mac mini box / its rescue agent).

Proves the shared _interview_transcript.py reader — and the two gates that
consume it, qc-interview-completion.py and build-workforce.py's
_genuine_interview_answers_file() / verify_interview_complete() /
_enforce_consent_or_refuse() — correctly find and decrypt an encrypted
(.md.enc, chacha20-poly1305) transcript IN-MEMORY, while every fail-closed
guarantee that predates this fix keeps holding:

  T1  AFTER: an .enc-only fixture (no plaintext) with a REAL 28-question
      transcript -> qc-interview-completion.py PASSes (rc=0), AND
      build-workforce.py's _genuine_interview_answers_file() finds it AND
      verify_interview_complete() reports complete=True. Both gates agree.
  T2  FAIL-CLOSED (a): no transcript anywhere -> qc rc=1, reason 'not-found'.
  T3  FAIL-CLOSED (b): .enc present, WRONG decryption key -> qc rc=1, reason
      'undecryptable' (DISTINCT from 'not-found' — proves "unreadable" is
      never misreported as "missing").
  T4  FAIL-CLOSED (c): .enc decrypts fine but the content is genuinely
      incomplete (2 questions) -> qc HARD FAILs (rc=3) on the DECRYPTED
      content — decryption is not a bypass of the substance checks.
  T5  REGRESSION: a plaintext-only client (no encryption at all) still PASSes
      exactly as before this fix.
  T6  ANTI-FABRICATION ON DECRYPTED CONTENT: build-workforce.py's
      _genuine_interview_answers_file() still rejects (a) an encrypted
      transcript with < 3 real **Q:** blocks and (b) an encrypted transcript
      bearing the non-interactive synthetic header — proving the fabrication
      guard evaluates the DECRYPTED text with identical strictness, never
      the ciphertext.
  T7  _enforce_consent_or_refuse(): PERMITS the build on the genuine
      encrypted fixture (no sys.exit) and REFUSES (exit 87) on the
      synthetic-header encrypted fixture with no ownerConsent — the real
      caller chain behaves correctly end-to-end, not just the helper
      functions in isolation.
  T8  NOTHING SENSITIVE IS LOGGED: none of the subprocess stdout/stderr
      captured across every case above contains the fixture transcript's
      answer text or the encryption secret; no plaintext .md file is ever
      created next to a .enc-only fixture.
  T9  BLEED TEST: monkeypatching read_transcript()/read_transcript_at() to
      return a fabricated PASS-shaped result WITHOUT reading anything makes
      T1's build-workforce assertions FAIL — proving this suite actually
      exercises the decrypt path rather than rubber-stamping.

Every fixture lives under a tempdir; nothing is written to a real
~/.openclaw. NEVER prints the fixture answer text — only counts/booleans/paths.

EXIT: 0 = every assertion (incl. fail-closed and bleed-test) passed; 1 otherwise.
Usage: python3 test-interview-transcript-decryption.py [REPO_ROOT]
"""

import base64
import hashlib
import importlib.util
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
BUILD_SCRIPT = SCRIPTS / "build-workforce.py"

sys.path.insert(0, str(SCRIPTS))
import _interview_transcript as T  # noqa: E402

PASS = 0
FAIL = 0

# Secret answer text that must NEVER appear in any captured stdout/stderr.
SECRET_MARKER = "u048-decrypt-lock-canary-owner-answer-text-should-never-leak"
TEST_SECRET = "test-suite-secret-do-not-use-in-prod-2026"

# Extra PYTHONPATH so subprocess invocations (run under a FAKE $HOME fixture
# for path-resolution testing) can still import `cryptography` even though
# macOS user-site-packages resolution depends on $HOME. Captured from THIS
# interpreter's own working sys.path before any HOME override.
_EXTRA_PYTHONPATH = os.pathsep.join(p for p in sys.path if p)


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


# ── Fixture builders ─────────────────────────────────────────────────────────

def encrypt_fixture(plaintext: str, secret: str = TEST_SECRET) -> str:
    """
    Re-implements the wire format documented in _interview_transcript.py /
    blackceo-command-center src/lib/interview/crypto.ts:
      "enc:v1:" + base64(nonce(12) || tag(16) || ciphertext)
    Manually cross-checked against REAL Node output (crypto.createCipheriv
    'chacha20-poly1305') during development of this fix — see the PR
    description for the byte-for-byte round-trip proof against Node.
    """
    key = hashlib.sha256(secret.strip().encode("utf-8")).digest()
    nonce = os.urandom(12)
    aead = ChaCha20Poly1305(key)
    ct_and_tag = aead.encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext, tag = ct_and_tag[:-16], ct_and_tag[-16:]
    envelope = nonce + tag + ciphertext
    return "enc:v1:" + base64.b64encode(envelope).decode("ascii")


def make_transcript(n_questions: int, header: str | None = None) -> str:
    lines = []
    if header:
        lines.append(header)
    lines += ["# Workforce Interview Answers", "", "---", ""]
    for i in range(1, n_questions + 1):
        lines.append(f"**Q:** Question number {i}: tell me about area {i} of your business?")
        lines.append(f"**A:** {SECRET_MARKER} — detailed owner answer for question {i}.")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


STATE_JSON = """{
  "interviewComplete": true,
  "companyName": "Acme Rescue Co",
  "industry": "Pet Rescue",
  "ownerChat": "12345",
  "agentName": "Rescue Agent",
  "brandingAnswers": {
    "brand_evokes": "trust and warmth",
    "customer_feeling": "safe and supported",
    "brand_descriptors": "caring, reliable, local",
    "ideal_customer": "pet owners in crisis",
    "unique_differentiator": "24/7 rescue response"
  },
  "departments": [{"id": "operations", "status": "done"}],
  "interviewProgress": {"lastQuestionNumber": %d}
}"""


def build_fixture_home(tmproot: Path, name: str, *, enc_content: str | None,
                        plaintext_content: str | None = None,
                        n_questions_for_state: int = 28) -> Path:
    """Build an isolated fake $HOME with .openclaw/workspace/company-discovery/."""
    home = tmproot / name
    cdd = home / ".openclaw" / "workspace" / "company-discovery"
    cdd.mkdir(parents=True, exist_ok=True)
    if enc_content is not None:
        (cdd / "workforce-interview-answers.md.enc").write_text(enc_content, encoding="utf-8")
    if plaintext_content is not None:
        (cdd / "workforce-interview-answers.md").write_text(plaintext_content, encoding="utf-8")
    state_path = home / ".openclaw" / "workspace" / ".workforce-build-state.json"
    state_path.write_text(STATE_JSON % n_questions_for_state, encoding="utf-8")
    return home


def run_qc(home: Path, secret: str | None, *, extra_env: dict | None = None):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = _EXTRA_PYTHONPATH + os.pathsep + env.get("PYTHONPATH", "")
    if secret is not None:
        env["MC_INTERVIEW_SECRET"] = secret
    else:
        env.pop("MC_INTERVIEW_SECRET", None)
    env.pop("MC_BOX_SECRET", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, str(QC_SCRIPT),
         "--state", str(home / ".openclaw" / "workspace" / ".workforce-build-state.json"),
         "--repo-root", str(REPO), "--format", "human"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    return proc


def load_build_workforce_module():
    spec = importlib.util.spec_from_file_location("bw_under_test_u048", str(BUILD_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.COMPANY_DISCOVERY_DIR = None
    return mod


def run_bw_probe(home: Path, secret: str | None, fn_name: str):
    """Run a build-workforce.py function in a subprocess under a fixture HOME
    (module-level state like COMPANY_DISCOVERY_DIR must not leak between
    fixtures, so each probe gets a fresh interpreter)."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = _EXTRA_PYTHONPATH + os.pathsep + env.get("PYTHONPATH", "")
    if secret is not None:
        env["MC_INTERVIEW_SECRET"] = secret
    else:
        env.pop("MC_INTERVIEW_SECRET", None)
    env.pop("MC_BOX_SECRET", None)
    code = f"""
import importlib.util, sys, json
spec = importlib.util.spec_from_file_location("bw", {str(BUILD_SCRIPT)!r})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.COMPANY_DISCOVERY_DIR = None
if {fn_name!r} == "genuine":
    g = mod._genuine_interview_answers_file()
    print("GENUINE=" + (g or "None"))
elif {fn_name!r} == "verify":
    v = mod.verify_interview_complete()
    print("COMPLETE=" + str(v["complete"]))
    print("METHOD=" + v["method"])
elif {fn_name!r} == "enforce":
    try:
        mod._enforce_consent_or_refuse({{"option": "B"}})
        print("ENFORCE=permitted")
    except SystemExit as e:
        print("ENFORCE=refused:" + str(e.code))
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=env, timeout=60)
    return proc


def assert_no_leak(procs: list, tag: str):
    for label, proc in procs:
        for stream_name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if SECRET_MARKER in (stream or ""):
                bad(f"{tag}: {label} {stream_name} LEAKED the fixture answer text — HARD FAIL")
                return
            if TEST_SECRET in (stream or ""):
                bad(f"{tag}: {label} {stream_name} LEAKED the encryption secret — HARD FAIL")
                return
    ok(f"{tag}: no transcript content or secret leaked into any captured output")


def main():
    if not QC_SCRIPT.is_file():
        print(f"FATAL: {QC_SCRIPT} not found", file=sys.stderr)
        return 1
    if not BUILD_SCRIPT.is_file():
        print(f"FATAL: {BUILD_SCRIPT} not found", file=sys.stderr)
        return 1

    tmproot = Path(tempfile.mkdtemp(prefix="u048-transcript-test-"))
    all_procs = []
    try:
        genuine_transcript = make_transcript(28)
        genuine_enc = encrypt_fixture(genuine_transcript)

        # ── T1: AFTER — .enc-only genuine fixture PASSes / is genuine / complete ──
        print("\n[T1] .enc-only genuine transcript — both gates must agree it's real")
        home1 = build_fixture_home(tmproot, "t1-genuine", enc_content=genuine_enc)

        qc1 = run_qc(home1, TEST_SECRET)
        all_procs.append(("T1-qc", qc1))
        if qc1.returncode == 0 and "[PASS]" in qc1.stdout:
            ok("qc-interview-completion.py PASSes (rc=0) on .enc-only genuine transcript")
        else:
            bad(f"qc-interview-completion.py did NOT pass: rc={qc1.returncode}\n{qc1.stdout}\n{qc1.stderr}")

        genuine_probe = run_bw_probe(home1, TEST_SECRET, "genuine")
        all_procs.append(("T1-genuine", genuine_probe))
        if "GENUINE=None" not in genuine_probe.stdout and "GENUINE=" in genuine_probe.stdout:
            ok("_genuine_interview_answers_file() finds the encrypted transcript")
        else:
            bad(f"_genuine_interview_answers_file() did NOT find it: {genuine_probe.stdout} {genuine_probe.stderr}")

        verify_probe = run_bw_probe(home1, TEST_SECRET, "verify")
        all_procs.append(("T1-verify", verify_probe))
        if "COMPLETE=True" in verify_probe.stdout:
            ok("verify_interview_complete() reports complete=True on the encrypted transcript")
        else:
            bad(f"verify_interview_complete() did NOT report complete: {verify_probe.stdout} {verify_probe.stderr}")

        enforce_probe = run_bw_probe(home1, TEST_SECRET, "enforce")
        all_procs.append(("T1-enforce", enforce_probe))
        if "ENFORCE=permitted" in enforce_probe.stdout:
            ok("_enforce_consent_or_refuse() PERMITS the build on the genuine encrypted transcript")
        else:
            bad(f"_enforce_consent_or_refuse() did not permit: {enforce_probe.stdout} {enforce_probe.stderr}")

        # ── T2: FAIL-CLOSED (a) — nothing at all ──
        print("\n[T2] fail-closed (a): no transcript anywhere")
        home2 = build_fixture_home(tmproot, "t2-none", enc_content=None)
        qc2 = run_qc(home2, TEST_SECRET)
        all_procs.append(("T2-qc", qc2))
        if qc2.returncode == 1 and "not-found" in qc2.stderr:
            ok("qc rc=1 with reason 'not-found' when no transcript exists at all")
        else:
            bad(f"expected rc=1 + 'not-found', got rc={qc2.returncode} stderr={qc2.stderr}")

        # ── T3: FAIL-CLOSED (b) — .enc present, WRONG key ──
        print("\n[T3] fail-closed (b): .enc present but undecryptable (wrong key)")
        qc3 = run_qc(home1, "totally-different-wrong-secret")
        all_procs.append(("T3-qc", qc3))
        if qc3.returncode == 1 and "undecryptable" in qc3.stderr:
            ok("qc rc=1 with DISTINCT reason 'undecryptable' when the key is wrong")
        else:
            bad(f"expected rc=1 + 'undecryptable', got rc={qc3.returncode} stderr={qc3.stderr}")
        if "not-found" in qc3.stderr:
            bad("'undecryptable' case incorrectly ALSO reported as 'not-found' — reasons must be distinct")
        else:
            ok("'undecryptable' and 'not-found' reasons are distinguishable (not conflated)")

        # ── T4: FAIL-CLOSED (c) — decryptable but genuinely incomplete ──
        print("\n[T4] fail-closed (c): decrypts fine, content genuinely incomplete (2 questions)")
        short_enc = encrypt_fixture(make_transcript(2))
        home4 = build_fixture_home(tmproot, "t4-short", enc_content=short_enc, n_questions_for_state=2)
        qc4 = run_qc(home4, TEST_SECRET)
        all_procs.append(("T4-qc", qc4))
        if qc4.returncode == 3 and "[FAIL]" in qc4.stdout:
            ok("qc HARD FAILs (rc=3) on decrypted-but-genuinely-short content")
        else:
            bad(f"expected rc=3 HARD FAIL, got rc={qc4.returncode}\n{qc4.stdout}\n{qc4.stderr}")

        # ── T5: REGRESSION — plaintext-only client unaffected ──
        print("\n[T5] regression: plaintext-only client (no encryption at all)")
        home5 = build_fixture_home(tmproot, "t5-plaintext", enc_content=None,
                                    plaintext_content=genuine_transcript)
        qc5 = run_qc(home5, None)
        all_procs.append(("T5-qc", qc5))
        if qc5.returncode == 0 and "[PASS]" in qc5.stdout:
            ok("plaintext-only transcript still PASSes exactly as before this fix")
        else:
            bad(f"plaintext regression broke: rc={qc5.returncode}\n{qc5.stdout}\n{qc5.stderr}")
        if "decrypted in-memory" in qc5.stderr:
            bad("plaintext-only run incorrectly claimed to have decrypted something")
        else:
            ok("plaintext-only run does NOT claim a decrypt happened")

        # ── T6: ANTI-FABRICATION on DECRYPTED content ──
        print("\n[T6] anti-fabrication guard evaluates DECRYPTED content, not ciphertext")
        fewq_enc = encrypt_fixture(make_transcript(2))
        home6a = build_fixture_home(tmproot, "t6-fewq", enc_content=fewq_enc)
        p6a = run_bw_probe(home6a, TEST_SECRET, "genuine")
        all_procs.append(("T6-fewq", p6a))
        if "GENUINE=None" in p6a.stdout:
            ok("< 3 real **Q:** blocks (decrypted) is still REJECTED as not-genuine")
        else:
            bad(f"fewer-than-3-questions fixture was WRONGLY accepted as genuine: {p6a.stdout}")

        synthetic_transcript = make_transcript(
            28, header="# Workforce Interview Answers (Non-Interactive)")
        synthetic_enc = encrypt_fixture(synthetic_transcript)
        home6b = build_fixture_home(tmproot, "t6-synthetic", enc_content=synthetic_enc)
        p6b = run_bw_probe(home6b, TEST_SECRET, "genuine")
        all_procs.append(("T6-synthetic", p6b))
        if "GENUINE=None" in p6b.stdout:
            ok("synthetic non-interactive header (decrypted) is still REJECTED as not-genuine")
        else:
            bad(f"synthetic-header fixture was WRONGLY accepted as genuine: {p6b.stdout}")

        # ── T7: _enforce_consent_or_refuse refuses the synthetic-header fixture ──
        print("\n[T7] _enforce_consent_or_refuse refuses a fabricated (synthetic-header) transcript")
        p7 = run_bw_probe(home6b, TEST_SECRET, "enforce")
        all_procs.append(("T7-enforce", p7))
        if "ENFORCE=refused:87" in p7.stdout:
            ok("_enforce_consent_or_refuse() REFUSES (exit 87) the synthetic-header transcript, no consent present")
        else:
            bad(f"expected ENFORCE=refused:87, got: {p7.stdout} {p7.stderr}")

        # ── T8: nothing sensitive logged, nothing plaintext written to disk ──
        print("\n[T8] no plaintext written to disk; no secret/content in any captured output")
        assert_no_leak(all_procs, "T8")
        for name, home in (("t1-genuine", home1), ("t4-short", home4),
                           ("t6-fewq", home6a), ("t6-synthetic", home6b)):
            plain = home / ".openclaw" / "workspace" / "company-discovery" / "workforce-interview-answers.md"
            if plain.exists():
                bad(f"T8: {name}: a PLAINTEXT transcript was written to disk ({plain}) — must never happen")
            else:
                ok(f"T8: {name}: no plaintext transcript materialized on disk")

        # ── T9: BLEED TEST — prove this suite actually exercises the decrypt path ──
        print("\n[T9] bleed test: stub out the shared reader to fabricate a PASS with no real read")
        orig_read_at = T.read_transcript_at
        try:
            def _fake_read_at(base):  # noqa: ANN001
                return T.TranscriptResult(make_transcript(28), base, False, None, [])
            # NOTE: do NOT patch T.read_transcript_at yet — the sanity check below
            # must run against the REAL, unpatched reader first, or it can never
            # observe a genuine reject (this bit the first draft of this test:
            # patching too early made the "sanity" check meaningless).
            probe_home = home6a  # 2-question fixture: genuine must be None normally
            spec = importlib.util.spec_from_file_location("bw_bleed", str(BUILD_SCRIPT))
            bw_bleed = importlib.util.module_from_spec(spec)
            old_home = os.environ.get("HOME")
            old_secret = os.environ.get("MC_INTERVIEW_SECRET")
            os.environ["HOME"] = str(probe_home)
            os.environ["MC_INTERVIEW_SECRET"] = TEST_SECRET
            try:
                spec.loader.exec_module(bw_bleed)
                bw_bleed.COMPANY_DISCOVERY_DIR = None
                # Sanity: with the REAL reader, this fixture is correctly rejected.
                real_result = bw_bleed._genuine_interview_answers_file()
                if real_result is not None:
                    bad("T9 setup invalid: fewer-than-3-question fixture was accepted "
                        "even BEFORE stubbing — cannot run bleed test")
                else:
                    # Now stub the module's OWN imported reference and confirm the
                    # bleed (fabricated PASS) is detectable, then restore and
                    # reconfirm the real check still rejects it.
                    bw_bleed._shared_transcript_reader.read_transcript_at = _fake_read_at
                    bled_result = bw_bleed._genuine_interview_answers_file()
                    if bled_result is not None:
                        ok("bleed test: stubbing the reader to fabricate 28 questions DOES "
                           "flip the result (proves the check is reading the reader's output, "
                           "not hardcoded) — restoring now")
                    else:
                        bad("bleed test: stubbing the reader had NO EFFECT — the check may not "
                            "be wired to the shared reader at all (suspicious pass)")
                    bw_bleed._shared_transcript_reader.read_transcript_at = orig_read_at
                    restored_result = bw_bleed._genuine_interview_answers_file()
                    if restored_result is None:
                        ok("bleed test: restoring the real reader re-confirms REJECT — "
                           "the suite is not vacuously passing")
                    else:
                        bad("bleed test: restore did not return to REJECT — test isolation broken")
            finally:
                if old_home is not None:
                    os.environ["HOME"] = old_home
                else:
                    os.environ.pop("HOME", None)
                if old_secret is not None:
                    os.environ["MC_INTERVIEW_SECRET"] = old_secret
                else:
                    os.environ.pop("MC_INTERVIEW_SECRET", None)
        finally:
            T.read_transcript_at = orig_read_at

    finally:
        shutil.rmtree(tmproot, ignore_errors=True)

    print(f"\n{'='*70}\nRESULTS: {PASS} passed, {FAIL} failed\n{'='*70}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
