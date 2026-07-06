#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: alert-dedup.py unit tests
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: the gateway send is monkeypatched to a
# recorder so nothing ever leaves the box and no OpenClaw CLI is required.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_alert_dedup.py
# =============================================================================
"""Deterministic tests for the founder alert dedup guardrail (Guardrail 7)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "alert-dedup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("alert_dedup", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AD = _load_module()


class _Recorder:
    """Stand-in for the gateway send; records every (target, text) it is asked
    to deliver and reports success unless told to fail."""

    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def __call__(self, target, text):
        self.calls.append((target, text))
        return (self.ok, "recorded" if self.ok else "forced failure")


class AlertDedupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="alertdedup-test-")
        self.rec = _Recorder(ok=True)
        self._orig_send = AD._gateway_send
        AD._gateway_send = self.rec  # patch the sole egress
        # A resolvable founder target so real (non-dry-run) sends are exercised.
        os.environ["PODCAST_FOUNDER_ALERT_CHAT"] = "test-operator-chat"

    def tearDown(self):
        AD._gateway_send = self._orig_send
        os.environ.pop("PODCAST_FOUNDER_ALERT_CHAT", None)

    # -- helpers --
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = AD.main(argv + ["--state-dir", self.tmp])
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        decision = json.loads(lines[-1]) if lines else {}
        return code, decision

    def _raise(self, service="fish_audio", failure="insufficient_credits",
               message="Fish Audio out of credits.", episode=None,
               severity="status", extra=None):
        argv = ["raise", "--client", "acme", "--service", service,
                "--failure-class", failure, "--message", message,
                "--severity", severity]
        if episode:
            argv += ["--episode", episode]
        if extra:
            argv += extra
        return self._run(argv)

    # -- tests --
    def test_first_occurrence_sends(self):
        code, d = self._raise(episode="ep1")
        self.assertEqual(code, AD.EXIT_OK)
        self.assertEqual(d["action"], "sent")
        self.assertTrue(d["sent"])
        self.assertTrue(d["send_ok"])
        self.assertEqual(len(self.rec.calls), 1)
        self.assertIn("1 episode(s) affected", self.rec.calls[0][1])

    def test_repeat_within_window_suppressed(self):
        self._raise(episode="ep1")
        code, d = self._raise(episode="ep2")
        self.assertEqual(code, AD.EXIT_OK)
        self.assertEqual(d["action"], "suppressed")
        self.assertFalse(d["sent"])
        # Still exactly one gateway send for 2 failures of the same key.
        self.assertEqual(len(self.rec.calls), 1)
        # Affected list grew in place to 2.
        self.assertEqual(d["affected_count"], 2)

    def test_twenty_jobs_one_alert(self):
        for i in range(20):
            self._raise(episode="ep%d" % i)
        self.assertEqual(len(self.rec.calls), 1)  # ONE alert, not 20

    def test_window_expiry_sends_still_down(self):
        self._raise(episode="ep1")
        # Force the last_sent stamp far into the past so the window has elapsed.
        state_path = AD._state_path(Path(self.tmp))
        state = json.loads(state_path.read_text())
        key = "acme|fish_audio|insufficient_credits"
        state["keys"][key]["last_sent"] = "2000-01-01T00:00:00Z"
        state["keys"][key]["first_seen"] = "2000-01-01T00:00:00Z"
        state_path.write_text(json.dumps(state))
        code, d = self._raise(episode="ep2")
        self.assertEqual(code, AD.EXIT_OK)
        self.assertEqual(d["action"], "sent")
        self.assertEqual(len(self.rec.calls), 2)
        self.assertIn("still down", self.rec.calls[1][1])

    def test_storm_cap_defers_to_digest(self):
        # 4 distinct status keys each send once -> hit the daily cap of 4.
        for i in range(4):
            c, d = self._raise(service="svc%d" % i, episode="e%d" % i)
            self.assertEqual(d["action"], "sent")
        self.assertEqual(len(self.rec.calls), 4)
        # 5th distinct status alert must defer (storm cap).
        c, d = self._raise(service="svc5", episode="e5")
        self.assertEqual(d["action"], "deferred")
        self.assertTrue(d["capped"])
        self.assertEqual(len(self.rec.calls), 4)  # no 5th immediate send
        # It landed in the digest queue.
        c, view = self._run(["status", "--client", "acme"])
        self.assertEqual(view["digest_pending"], 1)

    def test_decision_always_sends_bypasses_cap(self):
        for i in range(4):
            self._raise(service="svc%d" % i, episode="e%d" % i)
        self.assertEqual(len(self.rec.calls), 4)  # cap reached
        # Decision-class (cost_hold) must still send despite the cap.
        c, d = self._raise(service="pipeline", failure="cost_hold",
                           message="Episode hit hard cost ceiling.",
                           episode="epX", severity="decision")
        self.assertEqual(d["action"], "sent")
        self.assertEqual(len(self.rec.calls), 5)
        self.assertIn("[PODCAST DECISION]", self.rec.calls[4][1])

    def test_decision_dedups_per_episode(self):
        a = ["raise", "--client", "acme", "--service", "qc",
             "--failure-class", "three_strike", "--message", "3 strikes",
             "--episode", "epZ", "--severity", "decision"]
        self._run(a)
        c, d = self._run(a)  # same episode + event again
        self.assertEqual(d["action"], "suppressed")
        self.assertEqual(len(self.rec.calls), 1)

    def test_decision_requires_episode(self):
        c, d = self._raise(service="pipeline", failure="cost_hold",
                           message="no episode", severity="decision")
        self.assertEqual(c, AD.EXIT_USAGE)

    def test_recovery_sends_and_clears(self):
        self._raise(episode="ep1")
        self._raise(episode="ep2")  # suppressed but tracked
        c, d = self._run(["recover", "--client", "acme", "--service", "fish_audio",
                          "--message", "Fish Audio restored"])
        self.assertEqual(d["action"], "recovered")
        self.assertIn("resuming", self.rec.calls[-1][1])
        # Key cleared: a new failure is a fresh first-occurrence send.
        c, d = self._raise(episode="ep3")
        self.assertEqual(d["action"], "sent")

    def test_digest_class_batches_then_flush(self):
        c, d = self._raise(service="queue", failure="aged_out",
                           message="episode aged out at 60 days",
                           episode="old1", severity="digest")
        self.assertEqual(d["action"], "queued_digest")
        self.assertEqual(len(self.rec.calls), 0)  # nothing sent immediately
        c, d = self._run(["flush-digest", "--client", "acme"])
        self.assertEqual(d["action"], "flushed")
        self.assertEqual(len(self.rec.calls), 1)
        self.assertIn("[PODCAST DIGEST]", self.rec.calls[0][1])

    def test_dry_run_never_sends(self):
        c, d = self._raise(episode="ep1", extra=["--dry-run"])
        self.assertEqual(c, AD.EXIT_OK)
        self.assertEqual(d["action"], "would_send")
        self.assertFalse(d["sent"])
        self.assertEqual(len(self.rec.calls), 0)

    def test_no_founder_target_flagged_not_client(self):
        os.environ.pop("PODCAST_FOUNDER_ALERT_CHAT", None)
        c, d = self._raise(episode="ep1")
        self.assertEqual(c, AD.EXIT_NO_FOUNDER)
        self.assertFalse(d["send_ok"])
        self.assertEqual(len(self.rec.calls), 0)  # never falls back to a client

    def test_target_is_masked_in_output(self):
        c, d = self._raise(episode="ep1")
        self.assertTrue(d["target"].startswith("***"))
        self.assertNotIn("test-operator-chat", json.dumps(d))

    def test_send_failure_exit_code(self):
        self.rec.ok = False  # gateway reports failure
        c, d = self._raise(episode="ep1")
        self.assertEqual(c, AD.EXIT_SEND_FAILED)
        self.assertTrue(d["sent"])
        self.assertFalse(d["send_ok"])

    def test_no_em_dash_or_backticks_in_source(self):
        # Needles are built via escapes so this test file itself stays clean of
        # the forbidden literals (em dash, triple backtick fence).
        src = _SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn(chr(0x2014), src)  # em dash (U+2014)
        self.assertNotIn(chr(96) * 3, src)  # triple backtick fence

    def test_no_runtime_model_provider_tokens_in_source(self):
        # The dedicated runtime model-provider guard is the real merge gate;
        # this is a local smoke of the same intent. Tokens are assembled from
        # fragments so no forbidden literal appears in this shipped test file.
        src = _SCRIPT.read_text(encoding="utf-8").lower()
        frag = lambda *parts: "".join(parts)
        for bad in (frag("clau", "de"), frag("anthro", "pic"),
                    frag("us.", "anthro", "pic")):
            self.assertNotIn(bad, src)

    def test_no_direct_telegram_api(self):
        src = _SCRIPT.read_text(encoding="utf-8").lower()
        host = "api." + "telegram" + ".org"  # fragments; no forbidden literal here
        self.assertNotIn(host, src)
        # The only egress is the gateway CLI.
        self.assertIn("message", src)
        self.assertIn("--channel", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
