"""Tests for the manifest-executor dispatch fix in run_signature_deck.py.

run_signature_deck.py is the runner presentation-canonical-entry.sh actually
invokes. Before this fix it read the `executor` field of exactly zero manifest
phases (grep -a -n "executor" run_signature_deck.py returned zero hits) -- any
phase without one of the six hardcoded special-case branches (copy-QC loop,
prompt-QC loop, pre-assembly checkpoint, P4-RENDER, P9.5-NOTES-SYNC, delivery)
fell into the generic branch, which only checked whether produces_artifact
already existed on disk and attested it. Nothing ever ran build_teleprompter.py
or ghl_media_push.py automatically.

This file tests the two pieces that fix adds:
  1. _build_executor_argvs -- tokenise-then-substitute argv construction (pure
     function, no subprocess).
  2. _dispatch_generic_executor -- the real subprocess dispatcher (exercises
     real subprocess.run calls against small shell-safe stub commands, not
     mocked -- same discipline test_heal.py uses for the sibling package).
  3. An end-to-end CLI regression check (real `python3 run_signature_deck.py
     --phase ...` subprocess, via --adhoc + a logged adhoc_authorization.json)
     proving executor: null phases are COMPLETELY unaffected -- the critical
     regression this fix must never break.

Flat file beside the code it tests, manages its own import path -- matching
every sibling in this directory (test_gates.py, test_client_package.py, etc.).

FIX-1 (AF-FORGED-APPROVAL): adhoc authorization is folded into the same
authenticity oracle as phase-skip approvals. EVERY adhoc record must carry an
owner_msg_id that RESOLVES to a real owner-authored message in Command Center
task_activities. These CLI tests therefore seed a genuine owner_msg_id and run
inside a tiny local CC owner-ids server (COMMAND_CENTER_URL pointed at it) so
the oracle resolves over real HTTP -- the same hermetic pattern
test_skip_approval_authenticity.py uses.
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import run_signature_deck as rsd  # noqa: E402


# ---------------------------------------------------------------------------
# 1. _build_executor_argvs -- pure tokenise-then-substitute, no subprocess.
# ---------------------------------------------------------------------------

class TestBuildExecutorArgvs:
    def test_simple_command(self, tmp_path):
        argvs = rsd._build_executor_argvs(
            "python3 scripts/pdf_export.py --run-dir {run_dir}", tmp_path, "P8.1-PDF-EXPORT")
        assert argvs == [["python3", "scripts/pdf_export.py", "--run-dir", str(tmp_path)]]

    def test_chained_and_splits_into_two_stages(self, tmp_path):
        """P9.1-SPEECH-PDF's real manifest executor chains two commands with a
        manifest-authored ` && ` -- confirm it becomes two argv lists, not one
        argv containing a literal '&&' token (which would not do what the
        manifest author intended, and would never have been reached anyway
        since shell=False never interprets '&&' as an operator)."""
        cmd = (
            "python3 a.py --out {run_dir}/x.json && "
            "python3 b.py --spec {run_dir}/x.json --out {run_dir}/y.pdf"
        )
        argvs = rsd._build_executor_argvs(cmd, tmp_path, "P9.1-SPEECH-PDF")
        assert argvs == [
            ["python3", "a.py", "--out", f"{tmp_path}/x.json"],
            ["python3", "b.py", "--spec", f"{tmp_path}/x.json", "--out", f"{tmp_path}/y.pdf"],
        ]

    def test_run_dir_with_shell_metacharacters_lands_as_one_token(self, tmp_path):
        """SECURITY INVARIANT: run_dir is derived from client-controlled intake
        text upstream. Tokenise-then-substitute means a run_dir crafted with
        shell metacharacters can only ever land INSIDE an already-tokenised
        argument -- it can never introduce a new argv token or a shell
        operator, because it is never re-parsed after substitution."""
        evil = tmp_path / "run dir; rm -rf /tmp/pwned && echo pwned"
        argvs = rsd._build_executor_argvs(
            "python3 scripts/pdf_export.py --run-dir {run_dir}", evil, "P8.1-PDF-EXPORT")
        assert argvs == [["python3", "scripts/pdf_export.py", "--run-dir", str(evil)]]
        assert len(argvs[0]) == 4  # exactly the 4 tokens the template declares -- nothing added

    def test_empty_cmd_raises_contract_error(self, tmp_path):
        with pytest.raises(rsd.PhaseExecutorContractError):
            rsd._build_executor_argvs("", tmp_path, "X")
        with pytest.raises(rsd.PhaseExecutorContractError):
            rsd._build_executor_argvs("   ", tmp_path, "X")

    def test_unparseable_segment_raises_contract_error(self, tmp_path):
        with pytest.raises(rsd.PhaseExecutorContractError):
            rsd._build_executor_argvs('python3 foo.py "unterminated', tmp_path, "X")



# ---------------------------------------------------------------------------
# 2. _dispatch_generic_executor -- REAL subprocess.run, shell=False, against
#    small shell-safe stub commands (matches test_heal.py's own discipline of
#    exercising the real dispatch path rather than mocking subprocess).
# ---------------------------------------------------------------------------

class TestDispatchGenericExecutor:
    def test_success_returns_zero_and_runs_for_real(self, tmp_path):
        marker = tmp_path / "ran.txt"
        executor = {"kind": "script",
                    "cmd": f"{sys.executable} -c \"open(r'{marker}', 'w').write('ok')\""}
        rc = rsd._dispatch_generic_executor(tmp_path, executor, "T-PHASE")
        assert rc == 0
        assert marker.read_text() == "ok"

    def test_nonzero_exit_returns_executor_failed(self, tmp_path):
        executor = {"kind": "script", "cmd": f"{sys.executable} -c \"import sys; sys.exit(7)\""}
        rc = rsd._dispatch_generic_executor(tmp_path, executor, "T-PHASE")
        assert rc == rsd.EXIT_EXECUTOR_FAILED

    def test_missing_binary_returns_executor_failed_not_a_crash(self, tmp_path):
        executor = {"kind": "script", "cmd": "this-binary-does-not-exist-anywhere --flag"}
        rc = rsd._dispatch_generic_executor(tmp_path, executor, "T-PHASE")
        assert rc == rsd.EXIT_EXECUTOR_FAILED

    def test_chained_stops_at_first_failure_second_stage_never_runs(self, tmp_path):
        """P9.1-SPEECH-PDF-shaped: two `&&`-chained stages. The second stage's
        side effect (writing stage2.txt) must NEVER happen when stage 1 fails."""
        stage2_marker = tmp_path / "stage2.txt"
        cmd = (
            f"{sys.executable} -c \"import sys; sys.exit(3)\" && "
            f"{sys.executable} -c \"open(r'{stage2_marker}', 'w').write('should not exist')\""
        )
        executor = {"kind": "script", "cmd": cmd}
        rc = rsd._dispatch_generic_executor(tmp_path, executor, "T-PHASE")
        assert rc == rsd.EXIT_EXECUTOR_FAILED
        assert not stage2_marker.exists(), "second stage ran despite the first stage failing"

    def test_chained_both_stages_run_on_success(self, tmp_path):
        m1, m2 = tmp_path / "s1.txt", tmp_path / "s2.txt"
        cmd = (
            f"{sys.executable} -c \"open(r'{m1}', 'w').write('1')\" && "
            f"{sys.executable} -c \"open(r'{m2}', 'w').write('2')\""
        )
        executor = {"kind": "script", "cmd": cmd}
        rc = rsd._dispatch_generic_executor(tmp_path, executor, "T-PHASE")
        assert rc == 0
        assert m1.read_text() == "1"
        assert m2.read_text() == "2"

    def test_malformed_executor_cmd_does_not_attest(self, tmp_path):
        executor = {"kind": "script", "cmd": ""}
        rc = rsd._dispatch_generic_executor(tmp_path, executor, "T-PHASE")
        assert rc == rsd.EXIT_EXECUTOR_FAILED


# ---------------------------------------------------------------------------
# 3. CLI regression: executor: null phases are COMPLETELY unaffected.
#
# Real subprocess invocation of run_signature_deck.py itself (not a mocked or
# in-process call), against the REAL installed manifest, via --adhoc (a
# pre-existing, owner-authorized escape that skips ONLY check_phase_preconditions
# / the Kie balance preflight -- not the dispatch logic under test here). This
# is the single most important check in this file: a regression here means the
# fix broke every real, already-working build.
# ---------------------------------------------------------------------------

def _write_nonce(run_dir: Path) -> str:
    nonce = secrets.token_hex(32)
    ck = run_dir / "working" / "checkpoints"
    ck.mkdir(parents=True, exist_ok=True)
    nf = ck / ".canonical-entry-nonce"
    nf.write_text(nonce)
    os.chmod(nf, 0o600)
    return nonce


# The GENUINE owner message id the regression tests' adhoc record resolves to.
# It is served by the local CC owner-ids oracle below (never a real id).
GENUINE_OWNER_MSG_ID = "owner-msg-regression-0001"


class _OwnerIdsHandler(http.server.BaseHTTPRequestHandler):
    """Serves GET /api/tasks/{id}/messages/owner-ids with GENUINE_OWNER_MSG_ID so
    the engine's authenticity oracle (FIX-1) resolves the adhoc record's
    owner_msg_id over real HTTP."""

    def do_GET(self):
        if self.path.endswith("/messages/owner-ids"):
            body = json.dumps([GENUINE_OWNER_MSG_ID]).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # quiet


class _LocalBoard:
    """Context manager: start the owner-ids server on an ephemeral port, point
    COMMAND_CENTER_URL at it, and restore the environment on exit."""

    def __init__(self):
        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OwnerIdsHandler)
        self.port = self._srv.server_address[1]
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in ("COMMAND_CENTER_URL", "CC_API_TOKEN")}
        self._thread.start()
        os.environ["COMMAND_CENTER_URL"] = f"http://127.0.0.1:{self.port}"
        os.environ["CC_API_TOKEN"] = "tok-test"
        return self

    def __exit__(self, *exc):
        self._srv.shutdown()
        self._srv.server_close()
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _run_cli(run_dir: Path, phase_id: str, slides_path: Path, out_path: Path):
    nonce = _write_nonce(run_dir)
    env = dict(os.environ)
    env["OC_DECK_ENTRY_NONCE"] = nonce
    # COMMAND_CENTER_URL is set by the enclosing _LocalBoard context; a real value
    # must be present or the authenticity oracle is UNDETERMINED (fail-closed).
    for k in ("PRESENTATION_OWNER_CHAT_ID", "OPENCLAW_OWNER_CHAT_ID", "OWNER_CHAT_ID",
              "OWNER_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    cmd = [sys.executable, str(SCRIPTS / "run_signature_deck.py"),
           "--run-dir", str(run_dir), "--slides", str(slides_path),
           "--out", str(out_path), "--phase", phase_id, "--adhoc"]
    return subprocess.run(cmd, cwd=str(SCRIPTS), env=env, capture_output=True,
                          text=True, timeout=120)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file perms / nonce handshake")
class TestNullExecutorRegressionCLI:
    def _setup(self, tmp_path):
        run_dir = tmp_path / "run"
        (run_dir / "working" / "copy").mkdir(parents=True)
        (run_dir / "working" / "checkpoints").mkdir(parents=True)
        intake = {"slides": [{"no": 1}], "DECK_SLUG": "test", "pitch_included": False}
        (run_dir / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
        # FIX-1 (AF-FORGED-APPROVAL): the adhoc record MUST carry an owner_msg_id
        # that resolves to a real owner-authored message via the CC owner-ids oracle.
        # The run's manifest names the CC task; the enclosing _LocalBoard serves
        # GENUINE_OWNER_MSG_ID as that task's real owner-message id.
        (run_dir / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-executor-regression"}))
        adhoc = {"owner_approved": True, "approved_by": "pytest harness (not self-granted)",
                 "reason": "regression test: executor: null phase must be unaffected",
                 "timestamp": "2026-08-06T12:00:00Z",
                 "owner_msg_id": GENUINE_OWNER_MSG_ID}
        (run_dir / "working" / "checkpoints" / "adhoc_authorization.json").write_text(
            json.dumps(adhoc))
        slides = tmp_path / "slides.json"
        slides.write_text(json.dumps([{"no": 1}]))
        return run_dir, slides, tmp_path / "out.pptx"

    def test_null_executor_phase_unaffected_no_dispatch_line(self, tmp_path):
        manifest = rsd.load_manifest()
        by_id = {p["id"]: p for p in manifest["phases"]}
        p0a_executor_kind = (by_id["P0A-INTAKE"].get("executor") or {}).get("kind")
        assert p0a_executor_kind != "script", (
            f"P0A-INTAKE executor changed to kind={p0a_executor_kind!r} — "
            "this test requires a non-dispatchable (null/agent) executor phase in the "
            "real manifest. If kind is 'script', pick a different phase for this test.")
        run_dir, slides, out = self._setup(tmp_path)
        with _LocalBoard():
            proc = _run_cli(run_dir, "P0A-INTAKE", slides, out)
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        assert "attested" in proc.stdout
        assert "DISPATCH" not in proc.stdout, (
            "executor: null phase P0A-INTAKE triggered a DISPATCH line -- the fix must "
            f"never dispatch a phase with no declared executor.\nstdout:\n{proc.stdout}")

    def test_non_null_executor_phase_dispatches_and_attests(self, tmp_path):
        """P7-TELEPROMPTER: real, zero-caller-until-this-fix executor, dispatched
        for real via the CLI. Needs PRESENTERS-SPEECH.md + intake.json on disk
        (the same "agent already did the work out of band" convention every
        other phase in this runner uses)."""
        manifest = rsd.load_manifest()
        target = next(p for p in manifest["phases"] if p["id"] == "P7-TELEPROMPTER")
        assert target.get("executor", {}).get("kind") == "script"

        run_dir, slides, out = self._setup(tmp_path)
        (run_dir / "working" / "deliverables").mkdir(parents=True)
        import build_teleprompter as bt
        (run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md").write_text(
            bt.SAMPLE_SPEECH_MD)

        with _LocalBoard():
            proc = _run_cli(run_dir, "P7-TELEPROMPTER", slides, out)
        assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        assert "DISPATCH P7-TELEPROMPTER" in proc.stdout
        assert "attested" in proc.stdout
        html = run_dir / "working" / "deliverables" / "presenter-teleprompter.html"
        assert html.is_file() and html.stat().st_size > 10240

    def test_failing_executor_is_not_attested(self, tmp_path):
        """P9.2-GHL-UPLOAD with no renders present fails for real (no images/
        deliverables to host) -- confirm NO attestation is written."""
        run_dir, slides, out = self._setup(tmp_path)
        with _LocalBoard():
            proc = _run_cli(run_dir, "P9.2-GHL-UPLOAD", slides, out)
        assert proc.returncode == rsd.EXIT_EXECUTOR_FAILED
        assert "NOT attested" in proc.stderr
        pm = run_dir / "working" / "checkpoints" / "process_manifest.json"
        if pm.is_file():
            obj = json.loads(pm.read_text())
            ids = {a.get("phase_id") for a in obj.get("phase_attestations", [])}
            assert "P9.2-GHL-UPLOAD" not in ids
