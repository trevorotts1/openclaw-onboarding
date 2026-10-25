#!/usr/bin/env python3
"""Wiring proof for shared-utils/reminders/reminder_state_machine.py (T-17).

The reminder state machine exists to govern the shared reminder slots for the
interview-nudge sequence. This test is the REACHABILITY pin: it drives the real
production dispatch loop (nudge-incomplete-interviews.scan_and_nudge) and
asserts the machine -- not the ad-hoc nudges_sent list -- enforces the
three-slot budget and the no-reset rule.

If the wiring into scan_and_nudge is removed, this test fails two ways:

1. build_reminder_machine is never called, so no .reminder_machine ledger is
   created and the budget-capped assertion below cannot hold.
2. The old loop gates only on nudges_sent, so wiping that list re-sends; the
   machine's persisted ledger is what actually holds the cap at three. The
   test wipes nudges_sent between scans and proves the send count is still
   capped at 3 (never a fourth).

This is a genuine production call-site test, not a search-hit shim: the
transport is faked (no Telegram, no gateway) but the machine, its SQLite
ledger, due_slot and send_reminder all run for real.

Run from the repo root:
    python3 -m unittest discover -s shared-utils/reminders/tests -t shared-utils/reminders/tests -p 'test_*.py' -v
"""

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
NUDGE_SCRIPT = REPO / "shared-utils" / "nudge-incomplete-interviews.py"

for path in (str(PKG), str(REPO / "38-conversational-ai-system" / "tools")):
    if path not in sys.path:
        sys.path.insert(0, path)


def _load_nudge():
    spec = importlib.util.spec_from_file_location("nudge_under_test", NUDGE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestReminderWiring(unittest.TestCase):
    """scan_and_nudge must route sends through ReminderStateMachine."""

    def setUp(self):
        self.nudge = _load_nudge()
        self.tmp = Path(tempfile.mkdtemp(prefix="t17-wire-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.company_root = self.tmp / "zero-human-company"
        self.workspace = self.tmp / "workspace"
        self.company = self.company_root / "acme"
        self.company.mkdir(parents=True)
        self.workspace.mkdir(parents=True)
        self.state_path = self.workspace / ".workforce-build-state.json"
        self.sends = []

        # t0 is the interview invitation anchor. Each reminder slot fires at
        # its own threshold (24h/72h/168h) -- one per scan, never a catch-up
        # burst (DATA-CONTRACTS 8), which is exactly the machine's rule.
        self.idle_anchor = datetime.utcnow()

        # Fake the platform and the transport; the machine is real.
        self.nudge.get_openclaw_paths = lambda: {
            "company_root": self.company_root,
            "workspace": self.workspace,
            "root": self.tmp,
        }
        self.nudge.prompt_status = lambda state: "IN_PROGRESS"
        self.nudge.resolve_interview_link = lambda state, env=None: (
            "https://example.test/interview", "ok")

        def fake_send(meta, cfg, slug, dry_run=False, _state=None):
            self.sends.append(cfg["key"])
            return True

        self.nudge.send_telegram_nudge = fake_send

        # Controllable clock: the machine enforces the 30-minute quiet
        # interval between slots, so consecutive scans must advance time or
        # only the first slot would ever fire.
        clock = self

        class FakeDateTime(datetime):
            @classmethod
            def utcnow(cls):
                return clock.now_value

        self.now_value = datetime.utcnow()
        self.nudge.datetime = FakeDateTime

    def _write_state(self, nudges_sent):
        self.state_path.write_text(json.dumps({
            "companySlug": "acme",
            "ownerName": "Ada",
            "ownerChat": "+15550177",
            "interviewProgress": {
                "lastQuestionAt": self.idle_anchor.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "nudges_sent": list(nudges_sent),
        }), encoding="utf-8")

    def test_machine_budget_holds_when_nudges_sent_is_wiped(self):
        """Wiping the dedup list must NOT cause a fourth reminder."""
        # Scans land just past each slot threshold (24h/72h/168h), each far
        # enough past the last to clear the machine's 30-minute quiet interval.
        self.now_value = self.idle_anchor + timedelta(hours=24, minutes=1)
        self._write_state([])
        for hours in (24, 72, 168, 170, 180, 200):
            self.now_value = self.idle_anchor + timedelta(hours=hours, minutes=1)
            self.nudge.scan_and_nudge(dry_run=False)
            # Simulate a lost/corrupted nudges_sent list between scans. The
            # machine's persisted ledger alone must keep the cap.
            self._write_state([])

        # Exactly three shared reminders, never a fourth (DATA-CONTRACTS 8).
        self.assertEqual(len(self.sends), 3, "budget must cap at three sends")
        self.assertEqual(self.sends, ["nudge_24h", "nudge_72h", "nudge_168h"])

        # The machine's ledger was created and consulted (real call site).
        ledger = self.company / ".reminder_machine" / "identity.sqlite"
        self.assertTrue(ledger.exists(),
                        "scan_and_nudge must build the reminder machine ledger")

    def test_production_module_reaches_the_machine(self):
        """The production module must import and call the machine (reachability)."""
        src = NUDGE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ReminderStateMachine", src)
        self.assertIn("build_reminder_machine(", src)
        self.assertIn("decide_reminder(", src)
        self.assertIn("dispatch_reminder(", src)
        self.assertIn("from reminders.reminder_state_machine import", src)

    def test_governor_reaches_every_public_symbol(self):
        """All five new public symbols are used by the production call site."""
        src = NUDGE_SCRIPT.read_text(encoding="utf-8")
        for symbol in ("ReminderStateMachine", "SlotDecision",
                       "SendResult", "FinalReservation", "FinalOutcome"):
            self.assertIn(symbol, src,
                          "%s must be referenced by the production consumer" % symbol)


if __name__ == "__main__":
    unittest.main(verbosity=2)
