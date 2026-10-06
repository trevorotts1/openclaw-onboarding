#!/usr/bin/env python3
"""ILG-009: nudge carries the configured public /interview link, never a guess.

Offline. No gateway, no network, no client box. Imports the real worker
module (shared-utils/nudge-incomplete-interviews.py) and exercises:
  (a) resolve_interview_link() against the same source set the verified
      invitation path accepts (verified commandCenterPublicOrigin record,
      MC_TENANT_PUBLIC_URL, commandCenterUrl, OPENCLAW_DASHBOARD_URL);
  (b) send_telegram_nudge() skip-with-reason when no public origin is known
      (no chat resolution, no gateway invocation, returns False);
  (c) send_telegram_nudge() gateway --json receipt capture: rc==0 alone is
      NOT acceptance (returns False, failure counted by the caller), a real
      acknowledged receipt returns True, and the sent message carries the
      resolved link and the --json flag.
"""
import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared-utils"))
spec = importlib.util.spec_from_file_location(
    "nudge_incomplete_interviews", ROOT / "shared-utils" / "nudge-incomplete-interviews.py"
)
nudge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nudge)

ORIGIN = "https://client.example.com"
STATE = {
    "companyId": "client-a",
    "tenantId": "tenant-a",
    "installationId": "install-a",
    "commandCenterPublicOrigin": {
        "origin": ORIGIN,
        "verified": True,
        "protocol": "interview-launch.v1",
    },
    "commandCenterUrl": ORIGIN,
}
META = {"owner_name": "Test Owner", "progress_percent": 42,
        "last_question": "Q-D5", "owner_chat": "8399116757"}
CFG = {"key": "nudge_24h",
       "message_template": "Hi {name} ({progress}%) {last_question}: {link}"}


class ResolveInterviewLink(unittest.TestCase):
    def test_verified_origin_resolves_stable_interview_page(self):
        link, reason = nudge.resolve_interview_link(dict(STATE), env={})
        self.assertEqual(link, ORIGIN + "/interview")
        self.assertEqual(reason, "")

    def test_env_origin_accepted_when_state_record_absent(self):
        state = {k: v for k, v in STATE.items() if k != "commandCenterPublicOrigin"}
        link, _ = nudge.resolve_interview_link(
            state, env={"MC_TENANT_PUBLIC_URL": ORIGIN + "/"})
        self.assertEqual(link, ORIGIN + "/interview")

    def test_no_source_is_skip_with_named_reason(self):
        link, reason = nudge.resolve_interview_link({}, env={})
        self.assertIsNone(link)
        self.assertIn("commandCenterPublicOrigin", reason)

    def test_conflicting_sources_refuse(self):
        link, reason = nudge.resolve_interview_link(
            dict(STATE), env={"MC_TENANT_PUBLIC_URL": "https://other.example.com"})
        self.assertIsNone(link)
        self.assertIn("conflict", reason)

    def test_unverified_record_refuses(self):
        state = dict(STATE, commandCenterPublicOrigin={"origin": ORIGIN, "verified": False})
        link, reason = nudge.resolve_interview_link(state, env={})
        self.assertIsNone(link)
        self.assertIn("unverified", reason)

    def test_loopback_and_ip_and_http_refuse(self):
        for bad in ("http://client.example.com", "https://localhost:4000",
                    "https://127.0.0.1", "https://8.8.8.8"):
            with self.subTest(bad=bad):
                link, reason = nudge.resolve_interview_link(
                    {"commandCenterUrl": bad}, env={})
                self.assertIsNone(link)
                self.assertTrue(reason)

    def test_never_builds_resume_slug_or_placeholder_links(self):
        link, _ = nudge.resolve_interview_link(dict(STATE), env={})
        self.assertNotIn("onboarding/resume", link)
        self.assertNotIn("your-openclaw-bot", link)
        source = (ROOT / "shared-utils" / "nudge-incomplete-interviews.py").read_text()
        self.assertNotIn("your-openclaw-bot", source)
        self.assertNotIn("/onboarding/resume/", source)


class GatewayReceipt(unittest.TestCase):
    def _send(self, state, env_extra, cli_stdout, cli_rc=0, meta=None):
        env = {"OPENCLAW_DASHBOARD_URL": ORIGIN}
        env.update(env_extra)
        calls = []

        class Result:
            def __init__(self):
                self.returncode = cli_rc
                self.stdout = cli_stdout
                self.stderr = ""

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return Result()

        # The worker does `import subprocess as _sp` locally per call, so the
        # mock target is subprocess.run itself; environ is replaced wholesale
        # so a developer-machine variable can never leak into the assertion.
        with patch.dict(os.environ, env, clear=True), \
                patch("shutil.which", return_value="/usr/local/bin/openclaw"), \
                patch("subprocess.run", side_effect=fake_run):
            ok = nudge.send_telegram_nudge(dict(META if meta is None else meta),
                                           dict(CFG), "client-a",
                                           dry_run=False, _state=dict(state))
        return ok, calls

    def test_missing_origin_skips_before_gateway(self):
        with patch("shutil.which") as which:
            ok = nudge.send_telegram_nudge(dict(META), dict(CFG), "client-a",
                                           dry_run=False, _state={})
        self.assertFalse(ok)
        which.assert_not_called()

    def test_rc_zero_without_ack_is_failure(self):
        ok, calls = self._send(
            STATE, {"TELEGRAM_CHAT_ID": "8399116757"}, cli_stdout="{}", cli_rc=0)
        self.assertFalse(ok)
        self.assertEqual(len(calls), 1)
        self.assertIn("--json", calls[0])

    def test_acknowledged_receipt_sends(self):
        receipt = json.dumps({"channel": "telegram",
                              "payload": {"ok": True, "messageId": "m-1",
                                          "chatId": "8399116757"}})
        ok, calls = self._send(
            STATE, {"TELEGRAM_CHAT_ID": "8399116757"}, cli_stdout=receipt, cli_rc=0)
        self.assertTrue(ok)
        self.assertIn("--json", calls[0])
        sent_message = calls[0][calls[0].index("--message") + 1]
        self.assertIn(ORIGIN + "/interview", sent_message)

    def test_operator_chat_rejected(self):
        receipt = json.dumps({"channel": "telegram",
                              "payload": {"ok": True, "messageId": "m-1",
                                          "chatId": "5252140759"}})
        op_meta = dict(META, owner_chat="5252140759")
        ok, _ = self._send(
            {"commandCenterUrl": ORIGIN}, {"TELEGRAM_CHAT_ID": "5252140759"},
            cli_stdout=receipt, cli_rc=0, meta=op_meta)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
