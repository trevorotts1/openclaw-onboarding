#!/usr/bin/env python3
"""test_f21_f22_intake_transcript_envelope.py -- FIX F21/F22 pin.

THE TWO FAULTS (root-caused by unit E7 from the driver source; this unit
fixes at source)
------------------------------------------------------------------------
FAULT-22 (root cause): cmd_complete() NEVER built the signed transcript
envelope ({"format": "sp-intake-transcript-v1", "driver", "qid_sequence",
"turns", "driver_signature"}). Only _sig_finalize() -- reachable exclusively
through the SEPARATE 8-Sacred-Questions signature pass (--signature
--sig-next / --sig-answer) -- ever built it. An operator following the
obvious path (--next / --answer / --complete) therefore produced an UNSIGNED
transcript, and P-SP-INTAKE-TRACE could never pass for a signature deck
completed that way.

FAULT-21 (symptom): cmd_answer's (and, on audit, _sig_answer's) read-append-
write of working/interview/intake_transcript.json was NOT dict-safe. Once
that file held a signed dict envelope, the next --answer call read it via a
list-only reader (silently returning [] for a dict), appended its new
turn(s) to that empty list, and overwrote the file -- destroying
driver_signature and qid_sequence with no warning, no refusal, no backup.
Observed live: a 57-turn signed envelope became a 2-entry bare list (356
bytes). P-SP-INTAKE-TRACE then correctly fail-closed on "zero turns
(unreadable format)". Triggered by answering newly-synced bank questions
after completion -- "a completely reasonable thing for a real client flow to
do."

THE FIX proven here
--------------------
  1. cmd_complete() now builds the signed envelope on EVERY completion path,
     via the SAME shared signer _sig_finalize() calls
     (_finalize_transcript_envelope -> intake_trace_check.build_driver_envelope,
     never a local reimplementation) -- so the two paths can never drift.
  2. cmd_answer / _sig_answer are dict-safe: turns are appended to a SEPARATE
     append-only raw log (intake_transcript_raw.json) that is never the
     signed-envelope file, so there is no read-modify-write hazard against
     the envelope itself. A post-completion answer APPENDS the turn and
     RE-SIGNS the envelope (chosen over fail-loud: the trigger scenario --
     newly-synced bank questions after completion -- is a legitimate real
     client flow, per the unit brief) -- loudly, via a stderr NOTICE AND a
     `post_completion_append`/`envelope_resigned` field in the JSON reply.
     Silent provenance loss is eliminated either way.
  3. The verifier's teeth are untouched: check_driver_provenance() still
     rejects a bare list / tampered signature / unsigned turns exactly as
     before -- this file proves that too, so a fabricated/batched transcript
     can never be signed off.

Subprocess-level (drives the REAL, unmodified deck-intake-driver.py CLI) plus
direct calls into the real intake_trace_check.py / build_deck.py checkers --
no kie.ai spend, no renderer, no network, never touches the live box's real
run dirs. Flat file inside tests/, manages its own import path -- matching
every sibling in this directory (see test_f19_requester_stamp.py).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PRES_DEPT = SCRIPTS.parent
DRIVER_PATH = SCRIPTS / "deck-intake-driver.py"

sys.path.insert(0, str(SCRIPTS))
import build_deck  # noqa: E402

# Walk up from this repo's presentations/scripts to find the sibling
# 51-signature-presentation/scripts/intake_trace_check.py (repo/worktree
# layout: 23-ai-workforce-blueprint/ and 51-signature-presentation/ are
# SIBLING top-level dirs) -- mirrors build_deck._sp_prover()'s own resolution
# exactly, so this test exercises the identical checker the driver signs
# against.
def _find_intake_trace_check():
    for anc in SCRIPTS.parents:
        cand = anc / "51-signature-presentation" / "scripts" / "intake_trace_check.py"
        if cand.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location("intake_trace_check", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


ITC = _find_intake_trace_check()

pytestmark = pytest.mark.skipif(
    ITC is None, reason="51-signature-presentation/scripts/intake_trace_check.py not found "
                        "(repo/worktree sibling-dir layout required)"
)


# ---------------------------------------------------------------------------
# fixture plumbing
# ---------------------------------------------------------------------------
def _run_driver(run_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DRIVER_PATH), "--run-dir", str(run_dir), *args],
        capture_output=True, text=True,
    )


def _envelope(run_dir: Path) -> dict:
    path = run_dir / "working" / "interview" / "intake_transcript.json"
    assert path.is_file(), f"no signed envelope written at {path}"
    obj = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(obj, dict), f"envelope at {path} is not a dict: {type(obj)}"
    return obj


# ---------------------------------------------------------------------------
# 1 -- FAULT-22: a STANDARD (non-signature) --complete produces a valid
# signed envelope. Before the fix, cmd_complete() never called a signer at
# all -- this file would not have existed.
# ---------------------------------------------------------------------------
class TestFault22StandardCompleteSigns:
    def test_standard_complete_writes_signed_envelope(self, tmp_path):
        run_dir = tmp_path / "run"
        r = _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
        assert r.returncode == 0, f"--answer failed: {r.stdout}\n{r.stderr}"
        r = _run_driver(run_dir, "--complete")
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        payload = json.loads(r.stdout)
        assert payload.get("intake_transcript_signed") is True

        env = _envelope(run_dir)
        assert env.get("format") == "sp-intake-transcript-v1"
        assert isinstance(env.get("driver_signature"), str) and env["driver_signature"]
        assert isinstance(env.get("turns"), list) and len(env["turns"]) > 0
        assert isinstance(env.get("qid_sequence"), list) and env["qid_sequence"]

    def test_standard_complete_envelope_passes_real_provenance_checker(self, tmp_path):
        run_dir = tmp_path / "run"
        _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
        r = _run_driver(run_dir, "--complete")
        assert r.returncode == 0
        env = _envelope(run_dir)
        fails = ITC.check_driver_provenance(env)
        assert fails == [], f"real checker rejected driver-produced envelope: {fails}"

    def test_standard_non_signature_deck_passes_the_real_pipeline_gate(self, tmp_path):
        """The gate actually wired into build_deck.py's preflight
        (_chk_sp_intake_trace) DEFERS for a non-signature deck_type -- but it
        must not find anything BROKEN on the path it takes before deferring."""
        run_dir = tmp_path / "run"
        _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
        r = _run_driver(run_dir, "--complete")
        assert r.returncode == 0
        result = build_deck._chk_sp_intake_trace(run_dir)
        assert result == "", f"expected PASS/DEFER, got: {result!r}"


# ---------------------------------------------------------------------------
# 2 -- FAULT-21: --answer AFTER --complete must not destroy the envelope.
# Before the fix this silently replaced the signed dict with a bare list of
# just the new turn(s) -- driver_signature and qid_sequence gone, no warning.
# ---------------------------------------------------------------------------
class TestFault21PostCompletionAnswerSurvives:
    def test_answer_after_complete_envelope_survives_as_dict_and_grows(self, tmp_path):
        run_dir = tmp_path / "run"
        _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
        r = _run_driver(run_dir, "--complete")
        assert r.returncode == 0
        before = _envelope(run_dir)
        before_turns = len(before["turns"])
        before_sig = before["driver_signature"]

        r = _run_driver(run_dir, "--answer", "offer_name", "The Momentum Method")
        assert r.returncode == 0, f"--answer after --complete failed: {r.stdout}\n{r.stderr}"

        after = _envelope(run_dir)
        assert isinstance(after, dict), "envelope was replaced by a non-dict (FAULT-21 regression)"
        assert after.get("format") == "sp-intake-transcript-v1"
        assert len(after["turns"]) > before_turns, "new turn was not appended"
        assert "offer_name" in after["qid_sequence"]
        assert after["driver_signature"] != before_sig, "envelope must be RE-SIGNED, not left stale"

        # And the re-signed envelope must still be genuinely valid to the
        # real checker -- not merely dict-shaped.
        fails = ITC.check_driver_provenance(after)
        assert fails == [], f"re-signed envelope failed real provenance check: {fails}"

    def test_answer_after_complete_is_never_silent(self, tmp_path):
        run_dir = tmp_path / "run"
        _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
        _run_driver(run_dir, "--complete")
        r = _run_driver(run_dir, "--answer", "offer_name", "The Momentum Method")
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload.get("post_completion_append") is True
        assert payload.get("envelope_resigned") is True
        assert "POST-COMPLETION-APPEND" in r.stderr, (
            "a post-completion append must be announced on stderr, never silent")

    def test_answer_before_complete_is_not_flagged_post_completion(self, tmp_path):
        """Negative control: a normal in-progress answer (never completed
        yet) must NOT be mistaken for a post-completion append."""
        run_dir = tmp_path / "run"
        r = _run_driver(run_dir, "--answer", "presentation_type", "from_scratch")
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert "post_completion_append" not in payload
        assert "POST-COMPLETION-APPEND" not in r.stderr


# ---------------------------------------------------------------------------
# 3 -- signature mode (the pre-existing _sig_finalize path): still signs, and
# the SAME dict-safety now covers _sig_answer's sibling instance of the
# FAULT-21 hazard (found on audit -- read-append-write against the same
# envelope path).
# ---------------------------------------------------------------------------
class TestSignatureModeRegressionAndFault21Sibling:
    def _quick_signature_complete(self, run_dir: Path):
        r = _run_driver(run_dir, "--signature", "--sig-answer", "sp_mode", "QUICK")
        assert r.returncode == 0, f"sp_mode failed: {r.stdout}\n{r.stderr}"
        r = _run_driver(run_dir, "--signature", "--sig-answer", "signature_frame", "vault")
        assert r.returncode == 0, f"signature_frame failed: {r.stdout}\n{r.stderr}"
        return r

    def test_signature_quick_flow_signs_and_passes_real_gate(self, tmp_path):
        run_dir = tmp_path / "run"
        r = self._quick_signature_complete(run_dir)
        payload = json.loads(r.stdout)
        assert payload.get("status") == "complete"
        env = _envelope(run_dir)
        fails = ITC.check_driver_provenance(env)
        assert fails == [], f"signature envelope failed real provenance check: {fails}"
        gate = build_deck._chk_sp_intake_trace(run_dir)
        assert gate == "", f"expected the real pipeline gate to PASS, got: {gate!r}"

    def test_sig_answer_after_finalize_never_destroys_envelope(self, tmp_path):
        run_dir = tmp_path / "run"
        self._quick_signature_complete(run_dir)
        before = _envelope(run_dir)
        before_turns = len(before["turns"])

        # A newly-synced bank question answered after the signature intake
        # already finalized -- the sibling of FAULT-21's own trigger scenario.
        r = _run_driver(run_dir, "--signature", "--sig-answer", "sp_mode", "QUICK")
        assert r.returncode == 0, f"post-finalize sig-answer failed: {r.stdout}\n{r.stderr}"
        assert "POST-COMPLETION-APPEND" in r.stderr

        after = _envelope(run_dir)
        assert isinstance(after, dict)
        assert len(after["turns"]) > before_turns
        fails = ITC.check_driver_provenance(after)
        assert fails == [], f"envelope after post-finalize sig-answer failed: {fails}"


# ---------------------------------------------------------------------------
# 4 -- teeth intact: a genuinely unreadable/batched/fabricated transcript
# still FAILS. This fix must never weaken the verifier.
# ---------------------------------------------------------------------------
class TestVerifierTeethIntact:
    def test_hand_written_bare_list_still_rejected(self, tmp_path):
        """The EXACT shape the live incident (and the 2026-08-06 E2E audit
        error) produced: a bare JSON list with no envelope, no signature."""
        bare = [{"role": "assistant", "text": "hi", "qid": "q1"},
               {"role": "owner", "text": "hello", "qid": "q1"}]
        fails = ITC.check_driver_provenance(bare)
        assert fails, "a hand-written bare-list transcript must be rejected"
        assert fails[0][0] == "NO-DRIVER-ENVELOPE"

    def test_tampered_signature_still_rejected(self, tmp_path):
        env = ITC.build_driver_envelope(
            ["q1"], [{"role": "assistant", "text": "What is X?", "qid": "q1"},
                    {"role": "owner", "text": "Y", "qid": "q1"}])
        env["turns"][1]["text"] = "TAMPERED"
        fails = ITC.check_driver_provenance(env)
        assert any(code == "BAD-DRIVER-SIGNATURE" for code, _ in fails)

    def test_real_pipeline_gate_fails_closed_on_zero_turns(self, tmp_path):
        """The EXACT failure text the live incident's own FAULT-21 report
        quotes: 'the intake transcript parsed to zero turns (unreadable
        format)'. Built via the real _chk_sp_intake_trace gate against a
        deliberately-corrupted transcript for a signature-declared deck."""
        run_dir = tmp_path / "run"
        (run_dir / "working" / "copy").mkdir(parents=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(
            json.dumps({"deck_type": "signature_presentation"}))
        (run_dir / "working" / "interview").mkdir(parents=True)
        (run_dir / "working" / "interview" / "intake_transcript.json").write_text("")
        result = build_deck._chk_sp_intake_trace(run_dir)
        assert result.startswith("AF-INTAKE-BATCH"), f"expected fail-closed, got: {result!r}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
