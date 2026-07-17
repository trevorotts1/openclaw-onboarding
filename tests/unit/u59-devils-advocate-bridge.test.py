#!/usr/bin/env python3
"""Unit tests for shared-utils/devils-advocate-bridge.py — U55d (master U59), the
thin bridge from the Devil's Advocate generator to the Command Center's
POST /api/da-challenges (U55c, other repo/train).

Proves:
  * build_payload() produces the exact documented wire contract, task_id
    included only when present, department degrading to "" rather than
    KeyError.
  * bridge_config()/_sign() carry the SAME auth convention as
    06-ghl-install-pages/tools/cc_board.py (dual-header: Bearer + HMAC).
  * post_challenge() NEVER raises across every failure mode (board
    unconfigured, generator load failure, unreachable host, non-2xx
    response) and returns an honest result dict every time.
  * A REAL loopback HTTP POST (no mocking of urllib internals — a genuine
    local server) proves the bytes-on-the-wire: correct headers, an HMAC
    signature that verifies against the exact body sent, and a body that
    round-trips through json.loads back to build_payload()'s output.
  * The CLI (--dry-run, --selftest, and the disabled-board exit code) all
    behave as documented.

Run:
    python3 tests/unit/u59-devils-advocate-bridge.test.py
    or: pytest tests/unit/u59-devils-advocate-bridge.test.py
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
assert _SHARED.is_dir(), f"shared-utils not found at {_SHARED}"


def _load(name: str):
    """Load a hyphenated shared-utils script by file path (not import-able as
    a normal module name), matching the convention used across tests/unit/."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), _SHARED / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name.replace("-", "_")] = mod
    spec.loader.exec_module(mod)
    return mod


bridge = _load("devils-advocate-bridge")
generator = _load("devils-advocate")


# ---------------------------------------------------------------------------
# A real, minimal local HTTP server standing in for the CC-side
# POST /api/da-challenges route — proves actual wire bytes, not a mock.
# ---------------------------------------------------------------------------
class _RecordingHandler(BaseHTTPRequestHandler):
    """Captures the last request's headers + raw body, replies with a
    pre-configured status/body set by the test via class attributes."""

    response_status = 201
    response_body: bytes = b'{"ok":true,"id":"da-challenge-1"}'
    last_headers = None
    last_body = None

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's own naming
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        # HTTP header names are case-insensitive (RFC 7230 §3.2); urllib's own
        # Request.add_header() re-cases what we send (e.g. "x-webhook-signature"
        # -> "X-webhook-signature"), exactly as any real HTTP stack may. Store
        # lowercased so assertions below match on the correct, protocol-honest
        # semantics rather than incidental wire casing.
        type(self).last_headers = {k.lower(): v for k, v in self.headers.items()}
        type(self).last_body = body
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, fmt, *args):  # silence default stderr access logs
        pass


class _LocalServer:
    """Context manager: starts _RecordingHandler on 127.0.0.1:<ephemeral>,
    stops it on exit. Real sockets, real HTTP, no urllib internals mocked."""

    def __enter__(self):
        self.httpd = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


_FIXTURE_CONTEXT = {
    "task_id": "t-critical-1",
    "title": "Launch the new pricing page",
    "department": "marketing",
    "priority": "critical",
}


class TestBuildPayload(unittest.TestCase):
    def test_full_shape_with_task_id(self):
        generated = generator.generate_challenge("critical_task", _FIXTURE_CONTEXT)
        payload = bridge.build_payload("critical_task", _FIXTURE_CONTEXT, generated)
        self.assertEqual(payload["trigger_type"], "critical_task")
        self.assertEqual(payload["department"], "marketing")
        self.assertEqual(payload["task_id"], "t-critical-1")
        for key in ("challenge", "specific_concern", "assumptions", "severity", "raw_response"):
            self.assertIn(key, payload)
            self.assertEqual(payload[key], generated[key])
        self.assertEqual(payload["confidence"], generated["confidence"])

    def test_task_id_omitted_when_absent(self):
        generated = {"challenge": "q", "specific_concern": "c", "assumptions": "a",
                     "severity": "low", "confidence": 0.3, "raw_response": "r"}
        payload = bridge.build_payload("sensitive_dept", {"department": "legal"}, generated)
        self.assertNotIn("task_id", payload)

    def test_department_defaults_to_empty_string(self):
        generated = {"challenge": "q", "specific_concern": "c", "assumptions": "a",
                     "severity": "low", "confidence": 0.3, "raw_response": "r"}
        payload = bridge.build_payload("kpi_swing", {}, generated)
        self.assertEqual(payload["department"], "")

    def test_pure_function_no_mutation_of_inputs(self):
        context = dict(_FIXTURE_CONTEXT)
        generated = {"challenge": "q", "specific_concern": "c", "assumptions": "a",
                     "severity": "low", "confidence": 0.3, "raw_response": "r"}
        context_copy = dict(context)
        generated_copy = dict(generated)
        bridge.build_payload("critical_task", context, generated)
        self.assertEqual(context, context_copy)
        self.assertEqual(generated, generated_copy)


class TestAuthConvention(unittest.TestCase):
    def test_bridge_config_disabled_without_url(self):
        self.assertIsNone(bridge.bridge_config({}))

    def test_bridge_config_strips_trailing_slash_and_reads_all_keys(self):
        cfg = bridge.bridge_config({
            "MISSION_CONTROL_URL": "https://example.zerohumanworkforce.com/",
            "MC_API_TOKEN": "tok-123",
            "WEBHOOK_SECRET": "sec-456",
            "DA_BRIDGE_TIMEOUT": "3",
        })
        self.assertEqual(cfg["base_url"], "https://example.zerohumanworkforce.com")
        self.assertEqual(cfg["token"], "tok-123")
        self.assertEqual(cfg["secret"], "sec-456")
        self.assertEqual(cfg["timeout"], 3)

    def test_bridge_config_accepts_cc_webhook_secret_alias(self):
        cfg = bridge.bridge_config({
            "MISSION_CONTROL_URL": "https://x.example.com",
            "CC_WEBHOOK_SECRET": "alias-secret",
        })
        self.assertEqual(cfg["secret"], "alias-secret")

    def test_sign_none_without_secret(self):
        self.assertIsNone(bridge._sign("", b"hello"))

    def test_sign_matches_hmac_reference(self):
        sig = bridge._sign("mysecret", b"hello")
        expected = hmac.new(b"mysecret", b"hello", hashlib.sha256).hexdigest()
        self.assertEqual(sig, expected)
        self.assertEqual(len(sig), 64)


class TestPostChallengeFailureModes(unittest.TestCase):
    def test_no_board_configured_is_clean_noop_never_raises(self):
        result = bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={})
        self.assertFalse(result["ok"])
        self.assertFalse(result["board_configured"])
        self.assertIsNotNone(result["error"])
        self.assertIsNotNone(result["challenge"], "generator should still run even with no board configured")
        self.assertIsNotNone(result["payload"])

    def test_generator_load_failure_is_caught_not_raised(self):
        with mock.patch.object(bridge, "_GENERATOR_PATH", Path("/nonexistent/devils-advocate.py")):
            result = bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={})
        self.assertFalse(result["ok"])
        self.assertIsNone(result["challenge"])
        self.assertIn("generator load failed", result["error"])

    def test_unreachable_host_is_caught_not_raised(self):
        result = bridge.post_challenge(
            "critical_task", _FIXTURE_CONTEXT,
            env={"MISSION_CONTROL_URL": "http://127.0.0.1:1", "DA_BRIDGE_TIMEOUT": "2"},
        )
        self.assertTrue(result["board_configured"])
        self.assertFalse(result["ok"])
        self.assertIsNotNone(result["error"])


class TestPostChallengeRealLoopback(unittest.TestCase):
    """Genuine local HTTP server — proves actual wire bytes, not a mock."""

    def test_success_2xx_sends_correct_headers_and_body(self):
        _RecordingHandler.response_status = 201
        _RecordingHandler.response_body = b'{"ok":true,"id":"da-challenge-1"}'
        with _LocalServer() as srv:
            result = bridge.post_challenge(
                "critical_task", _FIXTURE_CONTEXT,
                env={
                    "MISSION_CONTROL_URL": srv.base_url,
                    "MC_API_TOKEN": "test-token-abc",
                    "WEBHOOK_SECRET": "test-secret-xyz",
                },
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status_code"], 201)
        self.assertEqual(result["response"], {"ok": True, "id": "da-challenge-1"})

        # The server actually received both auth headers, correctly formed.
        self.assertEqual(_RecordingHandler.last_headers.get("authorization"), "Bearer test-token-abc")
        received_sig = _RecordingHandler.last_headers.get("x-webhook-signature")
        expected_sig = hmac.new(b"test-secret-xyz", _RecordingHandler.last_body, hashlib.sha256).hexdigest()
        self.assertEqual(received_sig, expected_sig, "HMAC signature must sign the EXACT bytes sent")

        # The body received IS build_payload()'s output, byte-for-byte via JSON.
        received_payload = json.loads(_RecordingHandler.last_body)
        self.assertEqual(received_payload, result["payload"])
        self.assertEqual(received_payload["trigger_type"], "critical_task")
        self.assertEqual(received_payload["department"], "marketing")
        self.assertEqual(received_payload["task_id"], "t-critical-1")

    def test_no_secret_no_token_omits_both_headers(self):
        _RecordingHandler.response_status = 201
        _RecordingHandler.response_body = b'{"ok":true}'
        with _LocalServer() as srv:
            bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={"MISSION_CONTROL_URL": srv.base_url})
        self.assertNotIn("authorization", _RecordingHandler.last_headers)
        self.assertNotIn("x-webhook-signature", _RecordingHandler.last_headers)

    def test_non_2xx_response_is_reported_not_raised(self):
        _RecordingHandler.response_status = 422
        _RecordingHandler.response_body = b'{"error":"unresolvable department"}'
        with _LocalServer() as srv:
            result = bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={"MISSION_CONTROL_URL": srv.base_url})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 422)
        self.assertEqual(result["response"], {"error": "unresolvable department"})
        self.assertIn("422", result["error"])

    def test_posts_to_da_challenges_path(self):
        captured_path = {}
        orig_do_post = _RecordingHandler.do_POST

        def _capturing_do_post(self):
            captured_path["path"] = self.path
            orig_do_post(self)

        _RecordingHandler.response_status = 201
        _RecordingHandler.response_body = b'{"ok":true}'
        with mock.patch.object(_RecordingHandler, "do_POST", _capturing_do_post):
            with _LocalServer() as srv:
                bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={"MISSION_CONTROL_URL": srv.base_url})
        self.assertEqual(captured_path["path"], "/api/da-challenges")


class TestEvidenceReceipt(unittest.TestCase):
    def test_receipt_written_on_disabled_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={}, evidence_root=tmp)
            receipt_path = Path(tmp) / "routing" / "da-challenge-bridge-receipt.json"
            self.assertTrue(receipt_path.is_file())
            record = json.loads(receipt_path.read_text())
            self.assertEqual(record["trigger_type"], "critical_task")
            self.assertFalse(record["board_configured"])
            self.assertFalse(record["ok"])

    def test_no_evidence_root_is_a_clean_noop(self):
        # Should not raise even though no directory is created anywhere.
        bridge.post_challenge("critical_task", _FIXTURE_CONTEXT, env={}, evidence_root=None)


class TestSelftestAndCLI(unittest.TestCase):
    def test_selftest_function_passes(self):
        self.assertEqual(bridge._selftest(), 0)

    def test_cli_selftest_flag_exits_zero(self):
        self.assertEqual(bridge.main(["--selftest"]), 0)

    def test_cli_dry_run_prints_exact_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx_path = Path(tmp) / "ctx.json"
            ctx_path.write_text(json.dumps(_FIXTURE_CONTEXT))
            out = io.StringIO()
            with redirect_stdout(out):
                code = bridge.main(["--trigger", "critical_task", "--context-json", str(ctx_path), "--dry-run"])
            self.assertEqual(code, 0)
            printed = json.loads(out.getvalue())
            self.assertEqual(printed["trigger_type"], "critical_task")
            self.assertEqual(printed["department"], "marketing")
            self.assertEqual(printed["task_id"], "t-critical-1")

    def test_cli_exits_two_when_board_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx_path = Path(tmp) / "ctx.json"
            ctx_path.write_text(json.dumps(_FIXTURE_CONTEXT))
            out = io.StringIO()
            with mock.patch.dict("os.environ", {}, clear=True):
                with redirect_stdout(out):
                    code = bridge.main(["--trigger", "critical_task", "--context-json", str(ctx_path)])
            self.assertEqual(code, 2)

    def test_cli_exits_zero_on_successful_post(self):
        _RecordingHandler.response_status = 201
        _RecordingHandler.response_body = b'{"ok":true,"id":"da-1"}'
        with tempfile.TemporaryDirectory() as tmp:
            ctx_path = Path(tmp) / "ctx.json"
            ctx_path.write_text(json.dumps(_FIXTURE_CONTEXT))
            with _LocalServer() as srv:
                out = io.StringIO()
                with mock.patch.dict("os.environ", {"MISSION_CONTROL_URL": srv.base_url}, clear=True):
                    with redirect_stdout(out):
                        code = bridge.main(["--trigger", "critical_task", "--context-json", str(ctx_path)])
            self.assertEqual(code, 0)


class TestTriggerSetParity(unittest.TestCase):
    """Regression lock: if the generator's trigger set ever changes, this
    fails so the bridge's KNOWN_TRIGGERS/docstring get updated in lockstep."""

    def test_known_triggers_each_run_cleanly_through_the_real_generator(self):
        # generate_challenge() itself never validates trigger_type (the
        # generator's own argparse --trigger choices is the enforcement
        # point) -- confirm every trigger this bridge claims to know runs
        # cleanly and echoes itself back.
        for trigger in bridge.KNOWN_TRIGGERS:
            result = generator.generate_challenge(trigger, {"title": "x"})
            self.assertEqual(result["trigger_type"], trigger)

    def test_generator_argparse_rejects_unknown_trigger(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx_path = Path(tmp) / "ctx.json"
            ctx_path.write_text(json.dumps({"title": "x"}))
            sys_argv_backup = sys.argv
            try:
                sys.argv = ["devils-advocate.py", "--trigger", "not-a-real-trigger",
                            "--context-json", str(ctx_path)]
                with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                    with self.assertRaises(SystemExit):
                        generator.main()
            finally:
                sys.argv = sys_argv_backup


if __name__ == "__main__":
    unittest.main(verbosity=2)
