#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: FOUNDER-ALERT DELIVERY CONTRACT
# -----------------------------------------------------------------------------
# ONB58-ALERT-DELIVERY. End-to-end proof that podcast-smoke-test.py route_alert()
# and credit_queue.py's alert hook now invoke a REAL alert-dedup.py subcommand
# that exits 0 and WOULD deliver. The historical invocation shelled
# `alert-dedup.py notify --class <x>`, but alert-dedup.py only exposes
# {raise,recover,flush-digest,status} with --failure-class -- `notify` is an
# argparse invalid choice (exit 2, uncaught), so every founder alert was spooled
# to alerts-pending/*.jsonl yet NEVER pushed live to the gateway/Telegram.
#
# Drives the REAL alert-dedup.py (no mock), stdlib unittest only, fully offline:
# every invocation is --dry-run against a throwaway --state-dir, so the whole
# delivery decision is exercised without ever contacting a gateway or Telegram.
# Run:  python3 -m unittest \
#         58-podcast-production-engine/scripts/tests/test_alert_delivery.py
# =============================================================================
"""Delivery contract tests for founder alerts (Guardrail 7)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPTS = _HERE.parent.parent  # 58-podcast-production-engine/scripts
_SMOKE = _SCRIPTS / "podcast-smoke-test.py"
_CREDIT = _SCRIPTS / "credit_queue.py"
_DEDUP = _SCRIPTS / "alert-dedup.py"

# Decision actions from alert-dedup.py that mean "delivered, or would deliver".
_WOULD_DELIVER = {"would_send", "sent", "would_recover", "recovered",
                  "queued_digest", "flushed", "would_flush"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__ (credit_queue
    # uses dataclasses, which look the module up in sys.modules at decoration).
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SMOKE = _load("podcast_smoke_test", _SMOKE)
CQ = _load("credit_queue", _CREDIT)
DEDUP = _load("alert_dedup_delivery_target", _DEDUP)


def _run_dedup(argv):
    """Run the real alert-dedup.py and return (rc, last decision JSON)."""
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return proc.returncode, (json.loads(lines[-1]) if lines else {})


# Every name alert-dedup.py may resolve a target from, in the environment or in
# the box config file.
_FOUNDER_TARGET_ENV = ("PODCAST_FOUNDER_ALERT_CHAT", "OPERATOR_TELEGRAM_CHAT_ID",
                       "FOUNDER_TELEGRAM_CHAT_ID", "OPERATOR_ESCALATION_CHAT_ID")


def _clear_founder_env():
    for k in _FOUNDER_TARGET_ENV:
        os.environ.pop(k, None)


class RouteAlertDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="onb58-delivery-")
        _clear_founder_env()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- the argv route_alert now emits is a live invocation, not the dead one --
    def test_argv_uses_real_raise_never_dead_notify(self):
        argv = SMOKE._dedup_argv(
            sys.executable, str(_DEDUP), self.tmp, "acme", "smoke_test",
            "endpoints_missing", "status", "msg")
        self.assertIn("raise", argv)          # a real subcommand
        self.assertNotIn("notify", argv)      # the dead subcommand (exit 2)
        self.assertNotIn("--class", argv)     # the dead flag
        self.assertIn("--failure-class", argv)
        self.assertIn("--severity", argv)
        self.assertIn("--state-dir", argv)    # per-client, never the shared dir

    # -- helper: drive the REAL alert-dedup.py through route_alert, dry-run --
    def _route(self, service, failure_class, severity, episodes=None):
        proc = SMOKE.route_alert(self.tmp, "acme", service, failure_class,
                                 severity, "operator note", episodes=episodes,
                                 dry_run=True)
        self.assertIsNotNone(proc, "alert-dedup.py must be present and invoked")
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        return proc.returncode, (json.loads(lines[-1]) if lines else {})

    def test_status_alert_delivers(self):
        rc, d = self._route("kie", "unreachable_or_unfunded", "status")
        self.assertEqual(rc, 0)               # NOT 2 (the historical bug)
        self.assertIn(d["action"], _WOULD_DELIVER)
        self.assertEqual(d["severity"], "status")

    def test_overspend_canary_delivers_as_decision(self):
        # Overspend has no episode; it must still deliver (always-send decision).
        rc, d = self._route("smoke_test", "smoke_test_overspend", "canary")
        self.assertEqual(rc, 0)
        self.assertIn(d["action"], _WOULD_DELIVER)
        self.assertEqual(d["severity"], "decision")

    def test_digest_alert_batches_not_errors(self):
        rc, d = self._route("queue", "aged_out", "digest", episodes=["ep1"])
        self.assertEqual(rc, 0)
        self.assertEqual(d["action"], "queued_digest")
        self.assertEqual(d["severity"], "digest")

    def test_recovery_delivers_and_clears(self):
        # Seed an active status outage (dry-run still persists the key), then
        # recover it: the recovery must actually deliver, not noop.
        self._route("fish_audio", "unreachable_or_unfunded", "status")
        rc, d = self._route("fish_audio", "unreachable_or_unfunded", "recovery")
        self.assertEqual(rc, 0)
        self.assertEqual(d["action"], "would_recover")

    def test_spool_remains_source_of_truth(self):
        # The durable spool is written independent of the live delivery attempt.
        self._route("kie", "unreachable_or_unfunded", "status")
        adir = os.path.join(self.tmp, "alerts-pending")
        rows = []
        for fn in os.listdir(adir):
            with open(os.path.join(adir, fn), encoding="utf-8") as fh:
                rows += [json.loads(ln) for ln in fh if ln.strip()]
        self.assertTrue(
            any(r["failure_class"] == "unreachable_or_unfunded"
                and r["severity"] == "status" for r in rows),
            "route_alert must still spool the alert as the source of truth")

    def test_dead_notify_invocation_still_exits_2(self):
        # Regression guard: the invocation we replaced really is rejected by the
        # real alert-dedup.py, proving the founder alert never delivered before.
        rc, _ = _run_dedup([sys.executable, str(_DEDUP), "notify",
                            "--client", "acme", "--service", "s",
                            "--class", "fc", "--severity", "status",
                            "--message", "m", "--state-dir", self.tmp])
        self.assertEqual(rc, 2)


class CreditQueueDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="onb58-credit-")
        _clear_founder_env()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _drive(self, failure_class, affected):
        alert_cmd = [sys.executable, str(_DEDUP)]
        argv = CQ.build_dedup_raise_argv(
            alert_cmd, "acme", "fish_audio", failure_class,
            "held; will resume when funded", affected)
        self.assertIn("raise", argv)          # a real subcommand
        self.assertNotIn("notify", argv)      # the dead subcommand
        self.assertNotIn("--class", argv)     # the dead flag
        self.assertNotIn("--affected", argv)  # the nonexistent flag
        # Drive the REAL alert-dedup.py, dry-run, throwaway state dir.
        return _run_dedup(argv + ["--state-dir", self.tmp, "--dry-run"])

    def test_insufficient_credits_delivers_as_status(self):
        rc, d = self._drive("insufficient_credits", 20)
        self.assertEqual(rc, 0)               # NOT 2 (the historical bug)
        self.assertIn(d["action"], _WOULD_DELIVER)
        self.assertEqual(d["severity"], "status")
        self.assertEqual(d["affected_count"], 20)  # --queued-count carried

    def test_aged_out_batches_as_digest(self):
        rc, d = self._drive("queue_aged_out", 1)
        self.assertEqual(rc, 0)
        self.assertEqual(d["action"], "queued_digest")
        self.assertEqual(d["severity"], "digest")


class FounderTargetResolutionTest(unittest.TestCase):
    """Where a founder alert target comes from (Guardrail 7, ONB58-ALERT-DELIVERY).

    Nothing exports these names into the process environment on every box, so a
    box that only carries its escalation chat in openclaw.json must still
    resolve - and a value that is not a chat id (a tombstone placeholder) must
    count as UNSET rather than become a send target."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="onb58-target-")
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = self.tmp          # the box config lives under HOME
        _clear_founder_env()

    def tearDown(self):
        _clear_founder_env()
        if self._home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_box_config(self, env_vars):
        d = Path(self.tmp) / ".openclaw"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "openclaw.json", "w", encoding="utf-8") as fh:
            json.dump({"env": {"vars": env_vars}}, fh)

    def test_box_config_escalation_chat_resolves(self):
        self._write_box_config({"OPERATOR_ESCALATION_CHAT_ID": "-100123"})
        self.assertEqual(DEDUP._resolve_founder_target(None), "-100123")

    def test_environment_wins_over_box_config(self):
        self._write_box_config({"OPERATOR_ESCALATION_CHAT_ID": "-100123"})
        os.environ["PODCAST_FOUNDER_ALERT_CHAT"] = "founder-env-target"
        self.assertEqual(DEDUP._resolve_founder_target(None),
                         "founder-env-target")

    def test_value_that_is_not_a_chat_id_is_unset(self):
        # File tombstone: the config file is authoritative, so no target at all.
        self._write_box_config(
            {"OPERATOR_ESCALATION_CHAT_ID": "REMOVED-OPERATOR-CHAT-ID"})
        self.assertIsNone(DEDUP._resolve_founder_target(None))
        # Same tombstone arriving through the environment: also unset, and it
        # must not mask a usable legacy environment name either.
        self._write_box_config({})
        os.environ["OPERATOR_ESCALATION_CHAT_ID"] = "REMOVED-OPERATOR-CHAT-ID"
        self.assertIsNone(DEDUP._resolve_founder_target(None))
        os.environ["FOUNDER_TELEGRAM_CHAT_ID"] = "-4242"
        self.assertEqual(DEDUP._resolve_founder_target(None), "-4242")


if __name__ == "__main__":
    unittest.main()
