#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: notify-retry semantics tests
# -----------------------------------------------------------------------------
# Proves the NOTIFY-RETRY contract of alert-dedup.py at the dispatch site:
#   * TRANSPORT-DOWN failures keep retrying with capped exponential backoff and
#     are NEVER discarded (no terminal attempt cap exists; the alert is BLOCKED
#     until infrastructure returns).
#   * POISONED payloads (application-layer rejection) are parked automatically,
#     full content preserved in the operator-facing park file, and the key is
#     NEVER re-dispatched - not even by a later cron fire.
#   * UNDETERMINED failures default to the same unbounded backoff retry.
#   * No terminal retry cap: attempts grow without bound; only the DELAY is
#     capped, so an alert can never be dropped by a retry budget.
# Stdlib unittest only; the gateway send is monkeypatched so nothing egresses.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_notify_retry_semantics.py
# =============================================================================
"""Deterministic tests for the notify retry + park semantics (NOTIFY-RETRY)."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "alert-dedup.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("alert_dedup_nr", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AD = _load_module()


class _Recorder:
    """Stand-in for the gateway send. Failures can be scripted per-call with a
    chosen detail string (the ONLY evidence the dispatch site classifies on)."""

    def __init__(self, detail="forced failure"):
        self.detail = detail
        self.calls = []

    def __call__(self, target, text):
        self.calls.append((target, text))
        return (False, self.detail)


class NotifyRetrySemanticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="notify-retry-test-"))
        os.environ["PODCAST_FOUNDER_ALERT_CHAT"] = "test-operator-chat"
        # Shrink backoff so retry math is observable; the harness hook exists
        # for exactly this.
        os.environ["NOTIFY_RETRY_BASE_SECONDS"] = "2"
        self._orig_send = AD._gateway_send

    def tearDown(self):
        AD._gateway_send = self._orig_send
        os.environ.pop("PODCAST_FOUNDER_ALERT_CHAT", None)
        os.environ.pop("NOTIFY_RETRY_BASE_SECONDS", None)
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    # -- helpers --
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = AD.main(argv + ["--state-dir", str(self.tmp)])
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        decision = json.loads(lines[-1]) if lines else {}
        return code, decision

    def _raise(self, message="Fish Audio out of credits.", episode="ep1",
               failure="insufficient_credits", service="fish_audio"):
        return self._run(["raise", "--client", "acme", "--service", service,
                          "--failure-class", failure, "--message", message,
                          "--severity", "status", "--episode", episode])

    def _state(self):
        return json.loads(AD._state_path(self.tmp).read_text(encoding="utf-8"))

    def _park_rows(self):
        p = AD._park_path(self.tmp)
        if not p.is_file():
            return []
        return [json.loads(ln) for ln in
                p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _key_rec(self, key):
        return self._state()["keys"].get(key)

    # -- classification unit tests ------------------------------------------
    def test_classify_transport_evidence(self):
        for detail in ("gateway send timed out",
                       "gateway send failed: TimeoutExpired",
                       "openclaw binary not found on PATH (set OPENCLAW_BIN)",
                       "gateway rc=1 Connection refused",
                       "gateway send failed: OSError"):
            self.assertEqual(AD.classify_failure(detail), "transport", detail)

    def test_classify_poisoned_evidence(self):
        for detail in ("gateway rc=1 chat not found: 404 from Telegram",
                       "gateway rc=1 bad request: cannot parse entities",
                       "gateway rc=1 unauthorized: 401",
                       "gateway rc=1 user not found",
                       "gateway rc=1 message is too long"):
            self.assertEqual(AD.classify_failure(detail), "poisoned", detail)

    def test_classify_undetermined_defaults_to_transport_policy(self):
        # No distinguishing evidence: rc-only failures, empty detail.
        for detail in ("", "gateway rc=1", None, "gateway rc=3 something odd"):
            self.assertEqual(AD.classify_failure(detail), "undetermined", detail)

    # -- transport-down: retry forever with backoff, never discard ------------
    def test_transport_down_keeps_retrying_with_backoff(self):
        # Every fire fails with transport evidence; every fire MUST re-attempt
        # (the alert is never dropped) and the backoff must grow exponentially.
        # Between fires the backoff deadline is aged into the past, exactly as
        # a cron tick landing after the deadline would - the attempt counter
        # advances once per deadline pass, one gateway call per attempt.
        AD._gateway_send = _Recorder(detail="gateway send timed out")
        for i in range(8):
            if i > 0:
                self._age_deadline("acme|fish_audio|insufficient_credits")
            code, d = self._raise(episode="ep%d" % i)
            self.assertEqual(code, AD.EXIT_SEND_FAILED)
            self.assertEqual(d["action"], "retry_pending", "fire %d" % i)
            self.assertEqual(len(AD._gateway_send.calls), i + 1)
            rec = self._key_rec("acme|fish_audio|insufficient_credits")
            self.assertEqual(rec["retry"]["attempt"], i + 1)
            self.assertIsNotNone(rec["retry"]["next_attempt_at"])
            # The scheduled delay for attempt N is backoff(N): with the shrunken
            # base (2s) that is 2,4,8,16,32,64,128,256 - exponential, never flat.
            # The deadline must sit at least backoff(N) seconds in the future
            # (a few seconds of scheduling slack make the bound safe).
            self.assertGreaterEqual(
                self._delay_seconds(rec["retry"]["next_attempt_at"]),
                AD._backoff_delay(i + 1) - 2)
        # Delay grows without bound (never a flat retry) while attempts also
        # grow without bound; both are proven here.
        self.assertEqual(AD._backoff_delay(8), 256)

    def _age_deadline(self, key):
        state = self._state()
        rec = state["keys"][key]
        rec["retry"]["next_attempt_at"] = "2000-01-01T00:00:00Z"
        AD._state_path(self.tmp).write_text(json.dumps(state))

    def _delay_seconds(self, iso_ts):
        from datetime import datetime as _dt
        deadline = _dt.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ")
        now = _dt.utcnow()
        return max(int((deadline - now).total_seconds()), 0)

    def test_transport_down_retry_suppressed_until_deadline_then_attempts(self):
        # While a retry is pending, further fires are suppressed (no extra
        # gateway call); once the backoff deadline passes, the alert is
        # attempted again. NEVER discarded.
        AD._gateway_send = _Recorder(detail="gateway send timed out")
        code, d = self._raise(episode="ep1")
        self.assertEqual(code, AD.EXIT_SEND_FAILED)
        calls_after_first = len(AD._gateway_send.calls)
        # Immediate re-fire: suppressed by the pending retry (backoff 2s).
        code, d = self._raise(episode="ep2")
        self.assertEqual(d["action"], "suppressed")
        self.assertEqual(len(AD._gateway_send.calls), calls_after_first)
        # Force the deadline into the past: the next fire must attempt again.
        state = self._state()
        rec = state["keys"]["acme|fish_audio|insufficient_credits"]
        rec["retry"]["next_attempt_at"] = "2000-01-01T00:00:00Z"
        AD._state_path(self.tmp).write_text(json.dumps(state))
        code, d = self._raise(episode="ep3")
        self.assertEqual(code, AD.EXIT_SEND_FAILED)
        self.assertEqual(d["action"], "retry_pending")
        self.assertEqual(len(AD._gateway_send.calls), calls_after_first + 1)

    # -- poisoned: park + keep content + surface, never re-dispatched ---------
    def test_poisoned_parks_keeps_content_and_surfaces(self):
        AD._gateway_send = _Recorder(
            detail="gateway rc=1 chat not found: 404 from Telegram")
        text = "unique payload for the park file"
        code, d = self._raise(message=text)
        self.assertEqual(code, AD.EXIT_SEND_FAILED)
        self.assertEqual(d["action"], "parked")
        # Parked automatically: no flag anywhere, the file exists and holds the
        # FULL message content - the exact text the gateway was asked to carry.
        rows = self._park_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message"], AD._msg_first(
            "acme", "fish_audio", text, 1))
        self.assertIn(text, rows[0]["message"])
        self.assertEqual(rows[0]["key"], "acme|fish_audio|insufficient_credits")
        self.assertEqual(rows[0]["client"], "acme")
        self.assertEqual(rows[0]["service"], "fish_audio")
        self.assertEqual(rows[0]["failure_class"], "insufficient_credits")
        self.assertIn("chat not found", rows[0]["detail"])
        # The key is stamped parked and surfaced in the status view.
        rec = self._key_rec("acme|fish_audio|insufficient_credits")
        self.assertTrue(rec["retry"]["parked"])
        self.assertIsNone(rec["retry"]["next_attempt_at"])
        c, view = self._run(["status", "--client", "acme"])
        key_view = view["keys"]["acme|fish_audio|insufficient_credits"]
        self.assertTrue(key_view["retry"]["parked"])

    def test_poisoned_parked_never_redelivered_by_cron(self):
        # A parked key is structurally barred from re-entering the retry loop:
        # any later fire (a cron re-dispatch) is answered "parked" with NO new
        # gateway attempt, NO backoff scheduling, and exactly one park row.
        AD._gateway_send = _Recorder(detail="gateway rc=1 bad request: 400")
        code, d = self._raise(episode="ep1")
        self.assertEqual(d["action"], "parked")
        attempts_after_park = len(AD._gateway_send.calls)
        # Three cron re-fires: all parked, zero new attempts, one park row.
        for i in range(3):
            code, d = self._raise(episode="ep%d" % (i + 2))
            self.assertEqual(d["action"], "parked")
            self.assertEqual(code, AD.EXIT_OK)  # nothing more to do
            self.assertFalse(d["sent"])
        self.assertEqual(len(AD._gateway_send.calls), attempts_after_park)
        self.assertEqual(len(self._park_rows()), 1)  # one row, not four

    def test_poisoned_and_undetermined_are_distinct(self):
        # A poisoned payload parks; an undetermined failure retries. Same exit
        # code, opposite disposition - classification drives the disposition.
        AD._gateway_send = _Recorder(detail="gateway rc=1 chat not found")
        self._raise(service="svc_poison", failure="fc_a")
        AD._gateway_send = _Recorder(detail="gateway rc=1")
        self._raise(service="svc_unknown", failure="fc_b")
        self.assertTrue(
            self._key_rec("acme|svc_poison|fc_a")["retry"]["parked"])
        rec = self._key_rec("acme|svc_unknown|fc_b")
        self.assertNotIn("parked", rec["retry"])
        self.assertGreaterEqual(rec["retry"]["attempt"], 1)
        self.assertIsNotNone(rec["retry"]["next_attempt_at"])

    # -- undetermined: default unbounded backoff ------------------------------
    def test_undetermined_defaults_to_unbounded_backoff(self):
        # rc-only failure, no evidence: same retry-forever policy as transport.
        AD._gateway_send = _Recorder(detail="gateway rc=1")
        code, d = self._raise(episode="ep1")
        self.assertEqual(code, AD.EXIT_SEND_FAILED)
        self.assertEqual(d["action"], "retry_pending")
        rec = self._key_rec("acme|fish_audio|insufficient_credits")
        self.assertEqual(rec["retry"]["attempt"], 1)
        self.assertIsNotNone(rec["retry"]["next_attempt_at"])
        self.assertNotIn("parked", rec["retry"])

    # -- no terminal cap -------------------------------------------------------
    def test_no_terminal_retry_cap(self):
        # The attempt counter is unbounded: a transport-down alert is retried
        # forever. Only the DELAY is capped. Prove it over a long chain.
        AD._gateway_send = _Recorder(detail="gateway send timed out")
        for i in range(50):
            if i > 0:
                self._age_deadline("acme|fish_audio|insufficient_credits")
            code, d = self._raise(episode="ep%d" % i)
            self.assertEqual(code, AD.EXIT_SEND_FAILED)
            self.assertEqual(d["action"], "retry_pending")
            self.assertEqual(len(AD._gateway_send.calls), i + 1)
        rec = self._key_rec("acme|fish_audio|insufficient_credits")
        self.assertEqual(rec["retry"]["attempt"], 50)
        self.assertEqual(AD._backoff_delay(50), 900)  # delay capped, attempts not

    def test_structural_no_cap_in_source(self):
        # The shipped source must contain NO terminal retry budget: no attempt
        # ceiling constant, no max-retries gate. The only "cap" that may exist
        # caps the backoff DELAY.
        src = _SCRIPT.read_text(encoding="utf-8")
        for token in ("max_attempts", "max_retries", "MAX_RETRY",
                      "retry_limit", "RETRY_LIMIT", "give_up", "give_up_after"):
            self.assertNotIn(token, src, token)
        self.assertIn("BACKOFF_MAX_SECONDS", src)
        self.assertIn("NOTIFY_RETRY_BASE_SECONDS", src)

    def test_dry_run_never_retries_or_parks(self):
        # A dry-run failure renders the decision but changes no retry state and
        # writes no park row: the canary stays non-mutating.
        AD._gateway_send = _Recorder(detail="gateway rc=1 chat not found")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = AD.main(["raise", "--client", "acme", "--service", "fish_audio",
                            "--failure-class", "insufficient_credits",
                            "--message", "dry payload", "--severity", "status",
                            "--episode", "ep1", "--dry-run",
                            "--state-dir", str(self.tmp)])
        self.assertEqual(code, AD.EXIT_OK)
        self.assertEqual(len(AD._gateway_send.calls), 0)
        self.assertEqual(self._park_rows(), [])
        rec = self._key_rec("acme|fish_audio|insufficient_credits")
        self.assertIsNone(rec.get("retry"))


if __name__ == "__main__":
    unittest.main()
