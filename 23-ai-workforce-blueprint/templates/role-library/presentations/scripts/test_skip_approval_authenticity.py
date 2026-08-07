#!/usr/bin/env python3
"""
test_skip_approval_authenticity.py — FIX-1 (skill side) QC gate.

THE REQUIREMENT (GAUNTLET LOOP T-01 / QC row FIX-1):
  Phase-skip approvals must be AUTHENTIC. A phase_skip_approvals.json record is
  authentic ONLY when its owner_msg_id resolves to a REAL owner-authored message
  in Command Center task_activities. Presence of a string is never proof — the
  live E2E forged "e2e-test-002" and it authorized 9+ skips.

THE GATE (three runs, hermetic — no live CC):
  1. FORGED:   a skip record with owner_msg_id "e2e-test-002" that does NOT resolve
               to any real owner message -> the BUILD MUST FAIL (exit != 0) with
               AF-FORGED-APPROVAL in stderr; the plan print shows the phase
               `pending`, NEVER `SKIP(owner-authorized)`.
  2. GENUINE:  a skip record whose owner_msg_id resolves to a REAL owner-message id
               -> the build PASSES the authenticity gate (positive control).
  3. ADHOC:    a self-written adhoc_authorization.json (owner_approved:true) with
               no genuine owner message -> --adhoc is REFUSED (fail-closed).
  4. UNDETERMINED = DENIED: a record whose owner_msg_id cannot be oracle-verified
               (no cc_task_id on the run) FAILS CLOSED — a skip that cannot be
               proven authentic never opens the gate.
  5. OWNER_ACTION-ONLY (the original forgery vector): a record with
               owner_action="approved_skip" but NO owner_msg_id -> the BUILD MUST
               FAIL with AF-FORGED-APPROVAL. No owner_msg_id = no oracle query = a
               self-forged skip that must be denied (this is the exact attack the
               live E2E forger used).
  6. ADHOC-WITHOUT-MSG-ID: an adhoc_authorization.json with owner_approved:true +
               approved_by + reason but NO owner_msg_id -> --adhoc is REFUSED
               (exit 2, AF-FORGED-APPROVAL). A msg-id-less adhoc record must NOT
               pass the front door.

The oracle is mocked via cc_board's HTTP layer (the dept's own authed CC client),
so the full engine path — run_signature_deck.load_skip_approvals ->
cc_board.owner_message_ids_match -> cc_board.list_owner_message_ids ->
GET /api/tasks/[id]/messages/owner-ids — is exercised end to end, offline.

Run:  python3 test_skip_approval_authenticity.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""

import http.server
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cc_board  # noqa: E402
import run_signature_deck as rsd  # noqa: E402


# ---------------------------------------------------------------------------
# A tiny local CC owner-ids server. The engine calls the REAL route
# GET /api/tasks/{id}/messages/owner-ids; pointing COMMAND_CENTER_URL at this
# in-process HTTP server makes the oracle RESOLVE over real HTTP in both the
# subprocess CLI runs and the in-process calls. The token is a test value —
# never a client key.
# ---------------------------------------------------------------------------
class _OwnerIdsHandler(http.server.BaseHTTPRequestHandler):
    real_ids = frozenset()

    def do_GET(self):
        if self.path.endswith("/messages/owner-ids"):
            body = json.dumps(sorted(_OwnerIdsHandler.real_ids)).encode("utf-8")
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
    """Context manager: start the owner-ids server on an ephemeral port, set
    COMMAND_CENTER_URL to it, and restore the environment on exit."""

    def __init__(self, real_owner_ids):
        _OwnerIdsHandler.real_ids = frozenset(real_owner_ids)
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
        self._srv.server_close()  # release the listening socket (no ResourceWarning)
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _run_dir() -> Path:
    """A scratch run dir with the canonical checkpoints/copy skeleton."""
    rd = Path(tempfile.mkdtemp(prefix="deck_fix1_"))
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return rd


def _write_slides(rd: Path) -> Path:
    slides = rd / "slides.json"
    slides.write_text(json.dumps([{"no": 1}]))
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"slides": [{"no": 1}]}))
    return slides


def _write_nonce(rd: Path) -> str:
    nonce = secrets.token_hex(32)
    nf = rd / "working" / "checkpoints" / ".canonical-entry-nonce"
    nf.write_text(nonce)
    os.chmod(nf, 0o600)
    return nonce


def _forge_skip_record(rd: Path, phase_id: str, owner_msg_id: str) -> None:
    (rd / "working" / "checkpoints" / "phase_skip_approvals.json").write_text(
        json.dumps({"approvals": [{
            "phase_id": phase_id,
            "owner_approved": True,
            "approved_by": "E2E test operator",  # NOT a real person; NOT a self-grant marker
            "reason": "not applicable to this deck",
            "timestamp": "2026-08-06T12:00:00Z",
            "owner_msg_id": owner_msg_id,
            "owner_action": "approved_skip",
        }]}))


def _build_cli(rd: Path, slides: Path, out: Path, phase_id: str, env_extra=None) -> subprocess.CompletedProcess:
    """Run the REAL runner CLI against `rd` (canonical nonce handshake satisfied).
    The phase preconditions gate (check_phase_preconditions -> load_skip_approvals)
    is the surface under test — dispatch of a phase whose PRIOR phases are all
    skip-approved. Returns the CompletedProcess."""
    nonce = _write_nonce(rd)
    env = dict(os.environ)
    env["OC_DECK_ENTRY_NONCE"] = nonce
    # COMMAND_CENTER_URL is already set by the active _LocalBoard context; a real
    # value must be present or the oracle is UNDETERMINED (fail-closed). If the
    # caller passed env_extra it wins.
    if env_extra:
        env.update(env_extra)
    # Remove owner chat ids so the client-report path is quiet (no live send).
    for k in ("PRESENTATION_OWNER_CHAT_ID", "OPENCLAW_OWNER_CHAT_ID", "OWNER_CHAT_ID",
              "OWNER_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    return subprocess.run(
        [sys.executable, str(HERE / "run_signature_deck.py"),
         "--run-dir", str(rd), "--slides", str(slides), "--out", str(out),
         "--phase", phase_id],
        cwd=str(HERE), env=env, capture_output=True, text=True, timeout=120)


class ForgedApprovalTest(unittest.TestCase):
    """The QC gate's 3+1 runs, all hermetic against the real engine."""

    def test_forged_owner_msg_id_fails_build_with_af_forged_approval(self):
        """A skip record whose owner_msg_id ('e2e-test-002') does NOT resolve to a
        real owner message FAILS the build (exit != 0) with AF-FORGED-APPROVAL."""
        rd = _run_dir()
        slides = _write_slides(rd)
        # Dispatch P-0.5-RESEARCH: its ONLY prior is P-CONVERTER. Forge a skip for
        # P-CONVERTER with the exact forged id from the live E2E. The shared
        # build_deck gate sees owner_approved:true and passes; the authenticity
        # oracle (load_skip_approvals) is then the ONLY gate that can stop it.
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-e2e-forged"}))
        _forge_skip_record(rd, "P-CONVERTER", "e2e-test-002")

        # The task has NO real owner messages — the oracle returns an empty set.
        with _LocalBoard([]):
            proc = _build_cli(rd, slides, rd / "out.pptx", "P-0.5-RESEARCH")

        # The build MUST fail with exit != 0.
        self.assertNotEqual(proc.returncode, 0,
                            "forged skip must FAIL the build; it passed (stderr="
                            f"{proc.stderr[-400:]})")
        # The failure must name AF-FORGED-APPROVAL and the forged id.
        self.assertIn("AF-FORGED-APPROVAL", proc.stderr,
                      f"stderr should carry AF-FORGED-APPROVAL:\n{proc.stderr[-700:]}")
        self.assertIn("e2e-test-002", proc.stderr)

    def test_genuine_owner_msg_id_passes_build(self):
        """A skip record whose owner_msg_id RESOLVES to a real owner message in the
        oracle PASSES the authenticity gate (positive control)."""
        rd = _run_dir()
        slides = _write_slides(rd)
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-genuine"}))
        # Dispatch P-0.5-RESEARCH (prior P-CONVERTER) with a GENUINE skip id.
        _forge_skip_record(rd, "P-CONVERTER", "owner-msg-0042")

        # The task's REAL owner message log contains owner-msg-0042.
        with _LocalBoard(["owner-msg-0042"]):
            proc = _build_cli(rd, slides, rd / "out.pptx", "P-0.5-RESEARCH")

        # The authenticity gate must NOT be the reason for failure — a genuine id is
        # authentic. (The run may fail LATER on a genuine phase-precondition or render
        # need — but NOT with AF-FORGED-APPROVAL.)
        self.assertNotIn("AF-FORGED-APPROVAL", proc.stderr,
                         f"genuine id must not trip AF-FORGED-APPROVAL:\n{proc.stderr[-700:]}")

    def test_genuine_id_satisfies_next_turn_gate(self):
        """--next must treat a genuine owner-authorized skip as satisfied (the phase
        is NOT served as pending), proving load_skip_approvals returns it."""
        rd = _run_dir()
        phases = rsd.load_manifest()["phases"]
        ordered = sorted(phases, key=lambda p: p.get("order", 0))
        first_id = ordered[0]["id"]  # P-CONVERTER — the lowest-order phase
        # Genuine id, resolved by the oracle.
        _forge_skip_record(rd, first_id, "owner-msg-0042")
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-genuine"}))

        with _LocalBoard(["owner-msg-0042"]):
            approvals = rsd.load_skip_approvals(rd)
            ph, _, _ = rsd._next_required_phase(rd, phases)

        self.assertIn(first_id, approvals,
                      "a genuine owner-authorized skip must be honored")
        self.assertNotEqual(ph, first_id,
                            "--next must NOT serve a phase covered by a genuine skip")

    def test_forged_id_shows_pending_never_skip_in_plan_print(self):
        """The plan print must show the forged phase `pending`, NEVER
        SKIP(owner-authorized) — and must surface AF-FORGED-APPROVAL on stderr."""
        import io as _io
        import contextlib
        rd = _run_dir()
        phases = rsd.load_manifest()["phases"]
        ordered = sorted(phases, key=lambda p: p.get("order", 0))
        _forge_skip_record(rd, ordered[1]["id"], "e2e-test-002")
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-forged"}))

        with _LocalBoard([]):  # e2e-test-002 is NOT real
            buf = _io.StringIO()
            errbuf = _io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(errbuf):
                rsd.print_plan(rd, phases)

        plan = buf.getvalue()
        # The forged phase must show `pending`, never SKIP(owner-authorized).
        self.assertNotIn("SKIP(owner-authorized)", plan,
                         f"forged record must not print as owner-authorized:\n{plan}")
        self.assertIn("pending", plan)
        # The fatal AF-FORGED-APPROVAL is surfaced on stderr.
        self.assertIn("AF-FORGED-APPROVAL", errbuf.getvalue())

    def test_undetermined_oracle_fails_closed(self):
        """When the oracle cannot RESOLVE (no cc_task_id on the run / board disabled),
        an owner_msg_id-bearing record is DENIED — undetermined never opens the gate."""
        rd = _run_dir()
        phases = rsd.load_manifest()["phases"]
        ordered = sorted(phases, key=lambda p: p.get("order", 0))
        _forge_skip_record(rd, ordered[0]["id"], "some-id")
        # NO process_manifest.json -> no cc_task_id -> oracle UNDETERMINED.
        with self.assertRaises(rsd.ForgedApprovalError) as ctx:
            rsd.load_skip_approvals(rd)
        self.assertIn("AF-FORGED-APPROVAL", str(ctx.exception))
        self.assertIn("UNDETERMINED", str(ctx.exception))

    def test_owner_action_only_record_fails_build(self):
        """The ORIGINAL forgery attack (FIX-1 QC bypass path 1): a skip record with
        owner_action='approved_skip' but NO owner_msg_id must FAIL the build with
        AF-FORGED-APPROVAL. A record with no message id has nothing to resolve
        through the oracle — it is a self-forged skip and must be denied."""
        rd = _run_dir()
        slides = _write_slides(rd)
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-owner-action-only"}))
        # owner_action='approved_skip', NO owner_msg_id — the exact record shape
        # the live E2E forger used.
        (rd / "working" / "checkpoints" / "phase_skip_approvals.json").write_text(
            json.dumps({"approvals": [{
                "phase_id": "P-CONVERTER",
                "owner_approved": True,
                "approved_by": "E2E test operator",
                "reason": "not applicable to this deck",
                "timestamp": "2026-08-06T12:00:00Z",
                "owner_action": "approved_skip",
            }]}))

        # Even with the oracle healthy and reachable, the msg-id-less record must
        # FAIL — the absence of owner_msg_id is itself the forgery.
        with _LocalBoard(["owner-msg-real-1", "owner-msg-real-2"]):
            with self.assertRaises(rsd.ForgedApprovalError) as ctx:
                rsd.load_skip_approvals(rd)
        self.assertIn("AF-FORGED-APPROVAL", str(ctx.exception))
        self.assertIn("NO owner_msg_id", str(ctx.exception))

        # The full CLI build path must also fail (exit != 0) with AF-FORGED-APPROVAL.
        with _LocalBoard(["owner-msg-real-1", "owner-msg-real-2"]):
            proc = _build_cli(rd, slides, rd / "out.pptx", "P-0.5-RESEARCH")
        self.assertNotEqual(proc.returncode, 0,
                            "owner_action-only skip must FAIL the build")
        self.assertIn("AF-FORGED-APPROVAL", proc.stderr)
        self.assertIn("NO owner_msg_id", proc.stderr)

    def test_adhoc_without_msg_id_refused(self):
        """FIX-1 QC bypass path 2: an adhoc_authorization.json with
        owner_approved:true + approved_by + reason but NO owner_msg_id must be
        REFUSED (exit 2, AF-FORGED-APPROVAL). A msg-id-less adhoc record has
        nothing to resolve through the oracle — it must not pass the front door."""
        rd = _run_dir()
        slides = _write_slides(rd)
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-adhoc-nomsgid"}))
        (rd / "working" / "checkpoints" / "adhoc_authorization.json").write_text(
            json.dumps({
                "owner_approved": True,
                "approved_by": "E2E test operator",
                "reason": "self-written adhoc authorization",
                "timestamp": "2026-08-06T12:00:00Z",
                # NOTE: NO owner_msg_id — the bypass under test.
            }))
        # Even with the oracle healthy, the msg-id-less adhoc record must be refused.
        with _LocalBoard(["owner-msg-real-1"]):
            nonce = _write_nonce(rd)
            env = dict(os.environ)
            env["OC_DECK_ENTRY_NONCE"] = nonce
            for k in ("PRESENTATION_OWNER_CHAT_ID", "OPENCLAW_OWNER_CHAT_ID",
                      "OWNER_CHAT_ID", "OWNER_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"):
                env.pop(k, None)
            proc = subprocess.run(
                [sys.executable, str(HERE / "run_signature_deck.py"),
                 "--run-dir", str(rd), "--slides", str(slides),
                 "--out", str(rd / "out.pptx"), "--phase", "P0A-INTAKE", "--adhoc"],
                cwd=str(HERE), env=env, capture_output=True, text=True, timeout=120)

        self.assertNotEqual(proc.returncode, 0,
                            "adhoc-without-msg-id must be refused (exit != 0)")
        self.assertIn("AF-FORGED-APPROVAL", proc.stderr,
                      f"adhoc-without-msg-id must fail with AF-FORGED-APPROVAL:\n{proc.stderr[-500:]}")
        self.assertIn("NO owner_msg_id", proc.stderr)

    def test_adhoc_self_authorization_refused(self):
        """FIX-1 folded adhoc into the authenticity oracle: a self-written
        adhoc_authorization.json (owner_approved:true) with NO genuine owner message
        must be REFUSED (the --adhoc run must not pass the front door)."""
        rd = _run_dir()
        slides = _write_slides(rd)
        # The run is real (has a CC task), but the adhoc record's owner_msg_id is a
        # forged "e2e-test-002" that resolves to NO real owner message.
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-adhoc-forged"}))
        (rd / "working" / "checkpoints" / "adhoc_authorization.json").write_text(
            json.dumps({
                "owner_approved": True,
                "approved_by": "E2E test operator",
                "reason": "self-written adhoc authorization",
                "timestamp": "2026-08-06T12:00:00Z",
                "owner_msg_id": "e2e-test-002",
            }))
        # The oracle has NO real owner message matching e2e-test-002.
        with _LocalBoard([]):
            nonce = _write_nonce(rd)
            env = dict(os.environ)
            env["OC_DECK_ENTRY_NONCE"] = nonce
            for k in ("PRESENTATION_OWNER_CHAT_ID", "OPENCLAW_OWNER_CHAT_ID",
                      "OWNER_CHAT_ID", "OWNER_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"):
                env.pop(k, None)
            proc = subprocess.run(
                [sys.executable, str(HERE / "run_signature_deck.py"),
                 "--run-dir", str(rd), "--slides", str(slides),
                 "--out", str(rd / "out.pptx"), "--phase", "P0A-INTAKE", "--adhoc"],
                cwd=str(HERE), env=env, capture_output=True, text=True, timeout=120)

        # assert_adhoc_authorized must REFUSE the self-written adhoc record — a
        # forged owner_msg_id is AF-FORGED-APPROVAL (exit 2).
        self.assertNotEqual(proc.returncode, 0,
                            "self-written adhoc must be refused (exit != 0)")
        self.assertIn("AF-FORGED-APPROVAL", proc.stderr,
                      f"self-written adhoc must fail with AF-FORGED-APPROVAL:\n{proc.stderr[-500:]}")

    def test_owner_ids_oracle_hits_expected_route(self):
        """The oracle calls GET /api/tasks/{id}/messages/owner-ids (the CC route that
        powers authenticity) with the run's cc_task_id — proving the engine talks to
        the authoritative owner-message source."""
        rd = _run_dir()
        (rd / "working" / "checkpoints" / "process_manifest.json").write_text(
            json.dumps({"cc_task_id": "task-oracle-check"}))
        with _LocalBoard(["owner-msg-1"]):
            got = cc_board.owner_message_ids_match(rd, "")
        self.assertEqual(got, frozenset({"owner-msg-1"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
