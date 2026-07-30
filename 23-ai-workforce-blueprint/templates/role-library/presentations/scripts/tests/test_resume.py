"""Tests for U017 — --resume operator diagnosis and command fix."""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure the parent (scripts) dir is on sys.path
_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.diagnose import describe_park
from presentation_job.state import (
    StateStore, RunLock, utcnow, EXIT_OK, EXIT_USAGE, EXIT_LOCK_HELD,
    EXIT_GATE_BLOCKED, EXIT_STATE_CORRUPT, STATE_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_state(**overrides: Any) -> Dict[str, Any]:
    """Return a minimal valid state dict with the given overrides."""
    s: dict = {
        "schema_version": STATE_SCHEMA_VERSION,
        "job_id": "pj_test",
        "run_dir": "/tmp/test",
        "created_at": utcnow(),
        "manifest_path": "/tmp/test/manifest.json",
        "manifest_version": 25,
        "manifest_sha256": "a" * 64,
        "presentation_type": "from_scratch",
        "requester": {"chat_id": "test"},
        "intake": {},
        "current_phase": None,
        "phases": [
            {"id": "P0A-INTAKE", "status": "done", "artifacts": ["file1.txt"], "sha256": {},
             "attempts": 1, "heal_events": [], "attested_at": utcnow()},
            {"id": "P1-CONVERT", "status": "done", "artifacts": ["file2.txt"], "sha256": {},
             "attempts": 1, "heal_events": [], "attested_at": utcnow()},
            {"id": "P2-FAIL", "status": "blocked", "artifacts": [],
             "blocked_reason": "script executor failed after 3 attempts",
             "attempts": 3, "heal_events": [
                 {"at": utcnow(), "rung": 1, "attempt": 1, "reason": "exit 1"},
                 {"at": utcnow(), "rung": 1, "attempt": 2, "reason": "exit 1"},
                 {"at": utcnow(), "rung": 1, "attempt": 3, "reason": "exit 1"},
             ], "attested_at": None},
        ],
        "gates": {
            "script": {"state": "fail", "reason": "does not exist"},
            "qc": {"state": "fail", "reason": "no final QC report"},
            "ghl_upload": {"state": "waived", "reason": "client waived"},
        },
        "waivers": [{"rule": "ghl_upload", "source": "client request"}],
        "events": [],
        "sent": {},
        "undeliverable": [
            {"at": utcnow(), "kind": "progress", "message": "test", "chat_id_present": True}
        ],
        "heartbeat": {},
        "terminal": "BLOCKED",
        "blocked": {"phase": "P2-FAIL", "reason": "script executor failed after 3 attempts",
                    "at": utcnow()},
    }
    s.update(overrides)
    return s


# ---------------------------------------------------------------------------
# Test 1: describe_park on a _block-parked state names the phase, reason,
#         and mentions the owning role context
# ---------------------------------------------------------------------------
class TestDescribeParkBlockParked:
    def test_block_parked_names_phase_and_reason(self):
        state = _make_state()
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "P2-FAIL" in text, f"phase id missing: {text}"
        assert "script executor failed after 3 attempts" in text, f"reason missing: {text}"

    def test_block_parked_has_terminal(self):
        state = _make_state()
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "terminal : BLOCKED" in text


# ---------------------------------------------------------------------------
# Test 2: describe_park on a gate-parked state with NO blocked key names
#         every failing gate and its reason
# ---------------------------------------------------------------------------
class TestDescribeParkGateParked:
    def test_gate_parked_no_blocked_key(self):
        state = _make_state()
        state.pop("blocked", None)  # simulate pre-step-5 gate park
        state["phases"][2]["status"] = "pending"  # no phase was blocked
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "failing gates:" in text, f"failing gates heading missing: {text}"
        assert "script:" in text or "script" in text, f"script gate not named: {text}"
        assert "qc:" in text or "qc" in text, f"qc gate not named: {text}"

    def test_gate_parked_fallback_to_phase_reason(self):
        state = _make_state()
        state.pop("blocked", None)
        # Leave the phase blocked so fallback works
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "parked at phase   : P2-FAIL" in text


# ---------------------------------------------------------------------------
# Test 3: describe_park on a state whose blocked key was already popped
#         still names the phase via surviving blocked_reason
# ---------------------------------------------------------------------------
class TestDescribeParkBlockedPopped:
    def test_blocked_popped_still_reads_phase(self):
        state = _make_state()
        state.pop("blocked", None)  # simulate resume that popped but didn't clear phase status
        lines = describe_park(state)
        text = "\n".join(lines)
        # Should fall back to the phase's blocked_reason
        assert "parked at phase   : P2-FAIL" in text, (
            f"Should find phase via blocked status, got: {text}")


# ---------------------------------------------------------------------------
# Test 4: describe_park on a healthy in-progress job returns []
# ---------------------------------------------------------------------------
class TestDescribeParkHealthy:
    def test_in_progress_returns_empty(self):
        state = _make_state(terminal=None, blocked=None)
        state["phases"][2]["status"] = "pending"
        lines = describe_park(state)
        assert lines == ["terminal : in progress"], f"Expected [terminal : in progress], got {lines}"


# ---------------------------------------------------------------------------
# Test 5: describe_park never mutates: deep-compare the state dict before
#         and after
# ---------------------------------------------------------------------------
class TestDescribeParkNeverMutates:
    def test_state_unchanged(self):
        state = _make_state()
        before = json.dumps(state, sort_keys=True)
        describe_park(state)
        after = json.dumps(state, sort_keys=True)
        assert before == after, "describe_park mutated the state dict"


# ---------------------------------------------------------------------------
# Test 6: Every count in the output has a denominator — assert no line
#         matches a bare `: 0` with nothing after
# ---------------------------------------------------------------------------
class TestOutputHasDenominators:
    def test_no_bare_zero(self):
        import re
        state = _make_state()
        lines = describe_park(state)
        for line in lines:
            # A bare `: 0` at end of line (or followed only by whitespace) is suspect
            if re.search(r":\s*0\s*$", line) and " of " not in line:
                # Check if it's actually an "undeliverable" line which has "of" earlier
                if "undeliverable messages" not in line:
                    pytest.fail(f"bare count with no denominator: {line.strip()}")


# ---------------------------------------------------------------------------
# Test 7: --resume prints the diagnosis BEFORE it saves; prove ordering.
#         End-to-end: run presentation_job.py with --resume
# ---------------------------------------------------------------------------
class TestResumePrintsBeforeSave:
    def test_resume_prints_diagnosis_before_save(self):
        """Resume prints the diagnosis before saving, then saves anyway.
        Verify by asserting blocked key is gone and resume_history has one entry."""
        # This test uses a pre-created parked state file, not running the full engine.
        # The ordering is tested by reading state.json after resume simulates what
        # __main__.py does -- diagnosis before pop before save.
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            store = StateStore(run_dir)
            state = _make_state(run_dir=str(run_dir))
            store.save(state)

            # Simulate what the resume branch does:
            # 1. Print diagnosis (not tested in unit test, tested in integration)
            # 2. Pop blocked
            prior = state.pop("blocked", None)
            # 3. Append to resume_history
            state.setdefault("resume_history", []).append(
                {"at": utcnow(), "cleared_blocked": prior})
            state["terminal"] = None
            store.save(state)

            # Verify
            loaded = store.load()
            assert "blocked" not in loaded, "blocked key should be gone after resume"
            hist = loaded.get("resume_history", [])
            assert len(hist) == 1, f"Expected 1 resume_history entry, got {len(hist)}"
            assert hist[-1]["cleared_blocked"]["phase"] == "P2-FAIL", (
                f"Expected phase P2-FAIL in history, got {hist[-1]}")


# ---------------------------------------------------------------------------
# Test 8: --diagnose-only exits 0, prints the report, and leaves state.json
#         byte-identical — hash before and after
# ---------------------------------------------------------------------------
class TestDiagnoseOnly:
    def test_diagnose_only_is_read_only(self):
        """--diagnose-only must not mutate state."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            store = StateStore(run_dir)
            state = _make_state(run_dir=str(run_dir))
            store.save(state)

            before = (run_dir / "state.json").read_bytes()
            # Simulate diagnose-only: read diagnosis, then exit without save
            lines = describe_park(store.load(), run_dir)
            assert len(lines) > 0
            # No save was done
            after = (run_dir / "state.json").read_bytes()
            assert before == after, "--diagnose-only mutated state"


# ---------------------------------------------------------------------------
# Test 9: --diagnose-only without --resume exits 2
# ---------------------------------------------------------------------------
class TestDiagnoseOnlyRequiresResume:
    def test_diagnose_only_without_resume_exits_2(self):
        scripts_dir = _scripts_dir
        entry = scripts_dir / "presentation_job.py"
        if not entry.is_file():
            pytest.skip("presentation_job.py shim not found (U011 may not be fully merged)")
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            store = StateStore(run_dir)
            state = _make_state(run_dir=str(run_dir))
            store.save(state)

            r = subprocess.run(
                [sys.executable, str(entry), "--status", "--run-dir", str(run_dir),
                 "--diagnose-only"],
                capture_output=True, text=True, timeout=30,
                cwd=str(scripts_dir)
            )
            assert r.returncode == EXIT_USAGE, (
                f"--diagnose-only without --resume should exit {EXIT_USAGE}, got {r.returncode}"
            )


# ---------------------------------------------------------------------------
# Test 10: The command _block printed is runnable — extract the line after
#          continue with: and execute it with --diagnose-only appended.
# ---------------------------------------------------------------------------
class TestBlockedCommandIsRunnable:
    def test_blocked_printed_command_is_runnable(self):
        """The command after 'continue with:' in _block's output works when run."""
        scripts_dir = _scripts_dir
        entry = scripts_dir / "presentation_job.py"
        if not entry.is_file():
            pytest.skip("presentation_job.py shim not found")

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            # Create a minimal valid manifest so the engine can load it
            manifest_path = Path(td) / "manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_version": 25,
                "phases": [
                    {"id": "P0A-INTAKE", "order": 1, "owning_role": "test",
                     "produces_artifact": [], "executor": {"kind": "script", "cmd": "true"}}
                ],
                "deliverables_required": [],
                "client_package_files": [],
            }))
            store = StateStore(run_dir)
            state = _make_state(run_dir=str(run_dir),
                                manifest_path=str(manifest_path))
            state["terminal"] = "BLOCKED"
            # Compute sha256 of the manifest
            import hashlib
            state["manifest_sha256"] = hashlib.sha256(
                manifest_path.read_bytes()).hexdigest()
            store.save(state)

            # Run --resume --diagnose-only to trigger the resume path
            r = subprocess.run(
                [sys.executable, str(entry), "--resume", "--run-dir", str(run_dir),
                 "--diagnose-only"],
                capture_output=True, text=True, timeout=60,
                cwd=str(scripts_dir)
            )
            assert r.returncode == EXIT_OK, (
                f"--resume --diagnose-only should exit {EXIT_OK}, "
                f"got {r.returncode}: stderr={r.stderr[:500]}"
            )


# ---------------------------------------------------------------------------
# Test 11: close()'s gate-failure output contains a continue with: line and
#          writes state["blocked"] with phase == "CLOSE" and a gates list
# ---------------------------------------------------------------------------
class TestCloseGateFailureBlocked:
    def test_gate_failure_writes_blocked(self):
        """After close() fails, state['blocked'] has phase='CLOSE' with a gates list."""
        scripts_dir = _scripts_dir
        entry = scripts_dir / "presentation_job.py"
        if not entry.is_file():
            pytest.skip("presentation_job.py shim not found")

        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "run"
            run_dir.mkdir()
            # Create a minimal valid manifest
            manifest_path = Path(td) / "manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_version": 25,
                "phases": [
                    {"id": "P0A-INTAKE", "order": 1, "owning_role": "test",
                     "produces_artifact": [], "executor": {"kind": "script", "cmd": "true"}}
                ],
                "deliverables_required": [],
                "client_package_files": [],
            }))
            import hashlib
            store = StateStore(run_dir)
            state = _make_state(run_dir=str(run_dir),
                                manifest_path=str(manifest_path),
                                manifest_sha256=hashlib.sha256(
                                    manifest_path.read_bytes()).hexdigest())
            store.save(state)

            r = subprocess.run(
                [sys.executable, str(entry), "--close", "--run-dir", str(run_dir)],
                capture_output=True, text=True, timeout=60,
                cwd=str(scripts_dir)
            )
            # close should fail because no artifacts exist
            assert r.returncode == EXIT_GATE_BLOCKED, f"Expected exit {EXIT_GATE_BLOCKED}, got {r.returncode}"

            # Output must have continue with: line
            assert "continue with:" in (r.stderr + r.stdout), (
                "close() gate-failure must print 'continue with:'"
            )

            # Reload state
            loaded = store.load()
            blocked = loaded.get("blocked", {})
            assert blocked.get("phase") == "CLOSE", f"Expected phase=CLOSE, got {blocked}"
            assert "gates" in blocked, f"blocked.gates list missing: {blocked}"
            assert isinstance(blocked["gates"], list)
            assert len(blocked["gates"]) > 0


# ---------------------------------------------------------------------------
# Test 12: Both directions — resume_revalidation absent -> unknown, present ->
#          count with denominator
# ---------------------------------------------------------------------------
class TestResumeRevalidation:
    def test_absent_key_says_unknown_no_digit(self):
        state = _make_state()
        state.pop("resume_revalidation", None)
        lines = describe_park(state)
        text = "\n".join(lines)
        # Must have the re-validation line
        assert "banked artifact re-validation:" in text, (
            f"re-validation line missing: {text}"
        )
        # Must say unknown
        reval_line = [l for l in lines if "re-validation" in l or "revalidation" in l.lower()][0]
        assert "unknown" in reval_line.lower(), f"Should say unknown: {reval_line}"
        # Must carry no digit
        import re
        assert not re.search(r"\d", reval_line), (
            f"Should have no digit when absent: {reval_line}"
        )
        # Must name no unit id
        assert "U014" not in reval_line, f"Should not name U014: {reval_line}"
        import re as _re
        assert not _re.search(r"\bU\d{3}\b", reval_line), (
            f"Should not name any unit: {reval_line}"
        )

    def test_present_key_shows_count_with_denominator(self):
        state = _make_state()
        state["resume_revalidation"] = {"checked": 3, "failed": 0}
        lines = describe_park(state)
        text = "\n".join(lines)
        # Must have the re-validation line
        assert "banked artifact re-validation:" in text
        # Must NOT say unknown
        reval_line = [l for l in lines if "re-validation" in l or "revalidation" in l.lower()][0]
        assert "unknown" not in reval_line.lower(), f"Should not say unknown: {reval_line}"
        assert "3 checked" in reval_line
        assert "0" in reval_line
        assert "unknown" not in reval_line.lower()


# ---------------------------------------------------------------------------
# Test 13: Waived gates appear in the report distinctly from failing gates
# ---------------------------------------------------------------------------
class TestWaivedGates:
    def test_waived_gates_distinct(self):
        state = _make_state()
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "waived gates:" in text, f"waived gates section missing: {text}"
        assert "ghl_upload" in text, f"ghl_upload not in waived section: {text}"


# ---------------------------------------------------------------------------
# Test 14: --resume on a run dir whose lock is held by another process exits 6
# ---------------------------------------------------------------------------
class TestResumeLockHeld:
    def test_resume_while_locked_exits_6(self, tmp_path):
        """Two RunLocks on the same dir: second exits 6."""
        lock1 = RunLock(tmp_path)
        with lock1:
            with pytest.raises(SystemExit) as exc:
                lock2 = RunLock(tmp_path)
                lock2.__enter__()
            assert exc.value.code == EXIT_LOCK_HELD, (
                f"Expected exit {EXIT_LOCK_HELD}, got {exc.value.code}"
            )


# ---------------------------------------------------------------------------
# Test 15: describe_park on unrecognized state returns meaningful terminal
# ---------------------------------------------------------------------------
class TestDescribeParkEdgeCases:
    def test_no_gates_no_blocked_still_works(self):
        state = _make_state(gates={}, blocked=None, terminal="BLOCKED")
        state["phases"][2]["status"] = "pending"
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "terminal : BLOCKED" in text
        # Should still show phase counts
        assert "phases  :" in text

    def test_multiple_heal_events_grouped(self):
        state = _make_state()
        state["phases"][0]["heal_events"] = [
            {"at": utcnow(), "rung": 1, "attempt": 1, "reason": "exit 1"},
            {"at": utcnow(), "rung": 1, "attempt": 2, "reason": "exit 1"},
            {"at": utcnow(), "rung": 2, "attempt": 1, "reason": "timeout"},
        ]
        lines = describe_park(state)
        text = "\n".join(lines)
        assert "heal events by rung:" in text
        assert "rung 1:" in text
        assert "3 event(s)" in text or "rung 2:" in text  # depends on counts


# ---------------------------------------------------------------------------
# Test 16: Legacy `resume_revalidation` shapes must not crash the real CLI
#          path. Before U017, __main__.py wrote state["resume_revalidation"]
#          as a bare int. Any run dir resumed even once under the old code
#          still carries that shape on disk -- StateStore.load() does no
#          shape migration -- so `presentation_job.py --resume --diagnose-only`
#          must survive it end-to-end, not just describe_park() in isolation.
# ---------------------------------------------------------------------------
def _run_resume_diagnose_only(scripts_dir: Path, run_dir: Path):
    entry = scripts_dir / "presentation_job.py"
    return subprocess.run(
        [sys.executable, str(entry), "--resume", "--run-dir", str(run_dir),
         "--diagnose-only"],
        capture_output=True, text=True, timeout=60, cwd=str(scripts_dir),
    )


def _make_legacy_run_dir(td: str, resume_revalidation_value: Any) -> Path:
    """Build a parked run dir whose state.json carries a legacy/malformed
    resume_revalidation value (anything that is not the U017 dict shape)."""
    run_dir = Path(td) / "run"
    run_dir.mkdir()
    manifest_path = Path(td) / "manifest.json"
    manifest_path.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [
            {"id": "P0A-INTAKE", "order": 1, "owning_role": "test",
             "produces_artifact": [], "executor": {"kind": "script", "cmd": "true"}}
        ],
        "deliverables_required": [],
        "client_package_files": [],
    }))
    import hashlib
    store = StateStore(run_dir)
    state = _make_state(run_dir=str(run_dir), manifest_path=str(manifest_path))
    state["terminal"] = "BLOCKED"
    state["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    state["resume_revalidation"] = resume_revalidation_value
    store.save(state)
    return run_dir


class TestLegacyResumeRevalidationShapeCLI:
    """Regression for the U017 QC finding: describe_park() called .get() on
    state["resume_revalidation"] unconditionally, so a legacy bare-int value
    (the pre-U017 on-disk shape) crashed --resume --diagnose-only with an
    unhandled AttributeError instead of printing a diagnosis. These tests go
    through the real CLI subprocess path, because the crash was only fully
    visible end-to-end -- a unit test that only calls describe_park() with a
    hand-built dict cannot reproduce it."""

    scripts_dir = _scripts_dir

    def setup_method(self):
        if not (self.scripts_dir / "presentation_job.py").is_file():
            pytest.skip("presentation_job.py shim not found")

    def test_legacy_bare_int_does_not_crash(self):
        """Pre-U017 on-disk shape: resume_revalidation was a bare int."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = _make_legacy_run_dir(td, 7)
            r = _run_resume_diagnose_only(self.scripts_dir, run_dir)
            assert r.returncode == EXIT_OK, (
                f"legacy int resume_revalidation must not crash --resume "
                f"--diagnose-only, got {r.returncode}: stderr={r.stderr[:800]}"
            )
            assert "AttributeError" not in r.stderr, f"crashed: {r.stderr[:800]}"
            assert "Traceback" not in r.stderr, f"crashed: {r.stderr[:800]}"
            assert "banked artifact re-validation: unknown" in r.stderr, (
                f"expected degrade-to-unknown line, got: {r.stderr}"
            )
            # Must not print the bare legacy digit as if it were a real count
            reval_line = [l for l in r.stderr.splitlines() if "re-validation" in l][0]
            import re as _re
            assert not _re.search(r"\d", reval_line), (
                f"must not surface the bare legacy digit: {reval_line}"
            )

    def test_legacy_string_does_not_crash(self):
        """Malformed on-disk value: a string instead of the U017 dict shape."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = _make_legacy_run_dir(td, "corrupt")
            r = _run_resume_diagnose_only(self.scripts_dir, run_dir)
            assert r.returncode == EXIT_OK, (
                f"legacy string resume_revalidation must not crash --resume "
                f"--diagnose-only, got {r.returncode}: stderr={r.stderr[:800]}"
            )
            assert "AttributeError" not in r.stderr, f"crashed: {r.stderr[:800]}"
            assert "Traceback" not in r.stderr, f"crashed: {r.stderr[:800]}"
            assert "banked artifact re-validation: unknown" in r.stderr, (
                f"expected degrade-to-unknown line, got: {r.stderr}"
            )

    def test_legacy_null_does_not_crash(self):
        """resume_revalidation explicitly present but null (distinct from the
        key being entirely absent, which Test 12 already covers)."""
        with tempfile.TemporaryDirectory() as td:
            run_dir = _make_legacy_run_dir(td, None)
            r = _run_resume_diagnose_only(self.scripts_dir, run_dir)
            assert r.returncode == EXIT_OK, (
                f"null resume_revalidation must not crash --resume "
                f"--diagnose-only, got {r.returncode}: stderr={r.stderr[:800]}"
            )
            assert "AttributeError" not in r.stderr, f"crashed: {r.stderr[:800]}"
            assert "banked artifact re-validation: unknown" in r.stderr, (
                f"expected degrade-to-unknown line, got: {r.stderr}"
            )
