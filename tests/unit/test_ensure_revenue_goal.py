#!/usr/bin/env python3
"""ensure-revenue-goal.py: a box with no yearlyRevenueGoal gets ONE question
queued for its own agent; the answer is stored; it is never asked again.

  * missing goal            -> one marker-fenced question in AGENTS.md, nothing invented
  * run again               -> byte-identical (idempotent), no duplicate block
  * under a week            -> waits; a week or more -> one gentle reminder (counter bumps once)
  * --record                -> stores yearlyRevenueGoal, removes the question, keeps other keys
  * goal already set        -> nothing queued, a stale question is removed
  * bad answer / already set -> refused (exit 4), nothing written
  * damaged config / markers -> refused (exit 2), file untouched
  * AGENTS.md symlink       -> written THROUGH the link, link preserved
  * the section header must not be one update-skills.sh strips

Run: python3 tests/unit/test_ensure_revenue_goal.py
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "23-ai-workforce-blueprint" / "scripts" / "repair" / "ensure-revenue-goal.py"
BEGIN, END = "<!-- BEGIN REVENUE_GOAL_ASK_V1 -->", "<!-- END REVENUE_GOAL_ASK_V1 -->"
T0 = "2026-10-01T09:00:00+00:00"
T_DAY3 = "2026-10-04T09:00:00+00:00"
T_WEEK = "2026-10-08T09:00:00+00:00"
T_WEEK2 = "2026-10-15T09:00:01+00:00"

_spec = importlib.util.spec_from_file_location("ensure_revenue_goal", SCRIPT)
erg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(erg)


class Box(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.ws = self.tmp / "workspace"
        self.ws.mkdir()
        self.agents = self.ws / "AGENTS.md"
        self.agents.write_text("# Agent rules\n\nBe helpful.\n")
        self.cfg = self.tmp / "company-config.json"
        self.write_cfg({"companyName": "Example Co", "industry": "coaching"})
        self.env = dict(os.environ, HOME=str(self.tmp), PATH="/usr/bin:/bin")
        self.env.pop("OPENCLAW_COMPANY_CONFIG", None)

    def write_cfg(self, obj):
        self.cfg.write_text(json.dumps(obj, indent=2) + "\n")

    def cfg_data(self):
        return json.loads(self.cfg.read_text())

    def run_script(self, *extra, now=T0, config=True):
        cmd = [sys.executable, str(SCRIPT), "--workspace", str(self.ws), "--now", now, *extra]
        if config:
            cmd += ["--company-config", str(self.cfg)]
        return subprocess.run(cmd, capture_output=True, text=True, env=self.env)

    def state(self):
        return json.loads((self.tmp / ".revenue-goal-ask.json").read_text())

    def block_count(self):
        return self.agents.read_text().count(BEGIN)


class TestAsk(Box):
    def test_missing_goal_queues_exactly_one_question(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("state=queued", r.stdout)
        text = self.agents.read_text()
        self.assertEqual(text.count(BEGIN), 1)
        self.assertEqual(text.count(END), 1)
        self.assertIn("revenue goal for this year", text)
        self.assertIn("Be helpful.", text)  # existing content kept
        self.assertEqual(self.state()["status"], "pending")

    def test_never_invents_a_number(self):
        for now in (T0, T_WEEK, T_WEEK2):
            self.run_script(now=now)
        cfg = self.cfg_data()
        self.assertNotIn("yearlyRevenueGoal", cfg)
        self.assertEqual(cfg, {"companyName": "Example Co", "industry": "coaching"})

    def test_second_run_is_byte_identical(self):
        self.run_script()
        agents_1, state_1 = self.agents.read_bytes(), (self.tmp / ".revenue-goal-ask.json").read_bytes()
        r = self.run_script(now=T0)
        self.assertEqual(r.returncode, 0)
        self.assertIn("state=waiting", r.stdout)
        self.assertEqual(self.agents.read_bytes(), agents_1)
        self.assertEqual((self.tmp / ".revenue-goal-ask.json").read_bytes(), state_1)

    def test_under_a_week_waits_without_reminder(self):
        self.run_script(now=T0)
        r = self.run_script(now=T_DAY3)
        self.assertIn("state=waiting", r.stdout)
        self.assertEqual(self.state()["reminders"], 0)
        self.assertEqual(self.block_count(), 1)

    def test_a_week_later_one_gentle_reminder_not_a_second_block(self):
        self.run_script(now=T0)
        r = self.run_script(now=T_WEEK)
        self.assertIn("state=reminded", r.stdout)
        self.assertEqual(self.state()["reminders"], 1)
        self.assertEqual(self.block_count(), 1)
        self.assertIn("weekly reminder 1", self.agents.read_text())
        # same day again: no second reminder
        r = self.run_script(now=T_WEEK)
        self.assertIn("state=waiting", r.stdout)
        self.assertEqual(self.state()["reminders"], 1)
        # a further week: reminder two
        self.run_script(now=T_WEEK2)
        self.assertEqual(self.state()["reminders"], 2)
        self.assertEqual(self.block_count(), 1)

    def test_deleted_question_comes_back_without_a_new_ask_date(self):
        self.run_script(now=T0)
        self.agents.write_text("# Agent rules\n")  # something stripped the block
        self.run_script(now=T_DAY3)
        self.assertEqual(self.block_count(), 1)
        self.assertEqual(self.state()["lastAskedAt"], T0)  # not a fresh ask, no reminder bump
        self.assertEqual(self.state()["reminders"], 0)

    def test_creates_agents_md_when_absent(self):
        self.agents.unlink()
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.block_count(), 1)

    def test_dry_run_writes_nothing(self):
        before = self.agents.read_bytes()
        r = self.run_script("--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertIn("state=queued", r.stdout)
        self.assertEqual(self.agents.read_bytes(), before)
        self.assertFalse((self.tmp / ".revenue-goal-ask.json").exists())

    def test_no_company_config_is_skipped_never_created(self):
        self.cfg.unlink()
        r = self.run_script()
        self.assertEqual(r.returncode, 0)
        self.assertIn("skipped-no-company-config", r.stdout)
        self.assertFalse(self.cfg.exists())
        self.assertEqual(self.block_count(), 0)

    def test_section_header_survives_the_updater_strip(self):
        # update-skills.sh deletes every "## ... UPDATE PENDING ..." / "ONBOARDING PENDING"
        # section on each run. Our header must not match, or the question dies unanswered.
        self.run_script()
        strip = re.compile(r"(?m)^##[^\n]*(?:UPDATE PENDING|ONBOARDING PENDING)[^\n]*\n")
        self.assertIsNone(strip.search(self.agents.read_text()))
        # and the updater really does strip with that pattern (guards against it changing)
        self.assertIn("UPDATE PENDING|ONBOARDING PENDING", (ROOT / "update-skills.sh").read_text())

    def test_symlinked_agents_md_is_written_through_and_stays_a_link(self):
        shared = self.tmp / "shared-AGENTS.md"
        shared.write_text("# Shared rules\n")
        self.agents.unlink()
        self.agents.symlink_to(shared)
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.agents.is_symlink())
        self.assertIn(BEGIN, shared.read_text())


class TestAnswer(Box):
    def test_record_stores_goal_clears_question_keeps_other_keys(self):
        self.run_script()
        r = self.run_script("--record", "$750,000", now=T_DAY3)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.cfg_data(), {"companyName": "Example Co", "industry": "coaching",
                                           "yearlyRevenueGoal": "750000"})
        self.assertEqual(self.block_count(), 0)
        self.assertIn("Be helpful.", self.agents.read_text())
        self.assertEqual(self.state()["status"], "answered")

    def test_never_asks_again_once_answered(self):
        self.run_script()
        self.run_script("--record", "1.2m", now=T_DAY3)
        agents_after = self.agents.read_bytes()
        for now in (T_WEEK, T_WEEK2):
            r = self.run_script(now=now)
            self.assertIn("state=settled", r.stdout)
        self.assertEqual(self.agents.read_bytes(), agents_after)
        self.assertEqual(self.cfg_data()["yearlyRevenueGoal"], "1200000")

    def test_goal_set_by_hand_removes_a_stale_question(self):
        self.run_script()
        self.write_cfg(dict(self.cfg_data(), yearlyRevenueGoal=500000))
        r = self.run_script(now=T_WEEK)
        self.assertIn("state=settled", r.stdout)
        self.assertEqual(self.block_count(), 0)
        self.assertEqual(self.state()["status"], "answered")

    def test_goal_already_set_queues_nothing(self):
        self.write_cfg({"companyName": "Example Co", "yearlyRevenueGoal": "250k"})
        before = self.agents.read_bytes()
        r = self.run_script()
        self.assertIn("state=settled", r.stdout)
        self.assertEqual(self.agents.read_bytes(), before)
        self.assertFalse((self.tmp / ".revenue-goal-ask.json").exists())

    def test_alias_key_counts_as_set(self):
        self.write_cfg({"companyName": "Example Co", "revenueGoal": "1000000"})
        r = self.run_script()
        self.assertIn("state=settled", r.stdout)
        self.assertEqual(self.block_count(), 0)

    def test_empty_zero_or_junk_goal_counts_as_missing(self):
        for junk in ("", "0", 0, None, "TBD", "(set yearlyRevenueGoal in config)", -5, True):
            self.write_cfg({"companyName": "Example Co", "yearlyRevenueGoal": junk})
            self.agents.write_text("# Agent rules\n")
            (self.tmp / ".revenue-goal-ask.json").unlink(missing_ok=True)
            r = self.run_script()
            self.assertIn("state=queued", r.stdout, repr(junk))

    def test_bad_answers_are_refused_and_nothing_is_written(self):
        self.run_script()
        cfg_before, agents_before = self.cfg.read_bytes(), self.agents.read_bytes()
        for bad in ("", "lots", "-100", "0", "ten million", "1e9", "$"):
            r = self.run_script("--record", bad, now=T_DAY3)
            self.assertEqual(r.returncode, 4, repr(bad))
        self.assertEqual(self.cfg.read_bytes(), cfg_before)
        self.assertEqual(self.agents.read_bytes(), agents_before)

    def test_record_never_overwrites_an_existing_goal(self):
        self.write_cfg({"companyName": "Example Co", "yearlyRevenueGoal": "500000"})
        r = self.run_script("--record", "900000")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(self.cfg_data()["yearlyRevenueGoal"], "500000")

    def test_record_dry_run_writes_nothing(self):
        self.run_script()
        before = self.cfg.read_bytes()
        r = self.run_script("--record", "100000", "--dry-run", now=T_DAY3)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertEqual(self.block_count(), 1)

    def test_answered_then_value_lost_is_reported_not_re_asked(self):
        self.run_script()
        self.run_script("--record", "100000", now=T_DAY3)
        self.write_cfg({"companyName": "Example Co"})  # value vanished from the config
        r = self.run_script(now=T_WEEK2)
        self.assertEqual(r.returncode, 0)
        self.assertIn("answered-config-lost", r.stdout)
        self.assertEqual(self.block_count(), 0)
        self.assertNotIn("yearlyRevenueGoal", self.cfg_data())


class TestRefusals(Box):
    def test_unreadable_config_is_never_touched(self):
        self.cfg.write_text("{ not json")
        r = self.run_script()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.cfg.read_text(), "{ not json")
        self.assertEqual(self.block_count(), 0)

    def test_config_that_is_not_an_object_is_refused(self):
        self.cfg.write_text("[1, 2]")
        r = self.run_script("--record", "100000")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.cfg.read_text(), "[1, 2]")

    def test_unmatched_marker_leaves_agents_md_untouched(self):
        broken = "# Rules\n" + BEGIN + "\nhalf a block\n"
        self.agents.write_text(broken)
        r = self.run_script()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.agents.read_text(), broken)

    def test_missing_workspace_is_an_error_not_a_guess(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.tmp / "nope"),
                            "--company-config", str(self.cfg), "--now", T0],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.tmp / "nope").exists())


class TestAmounts(unittest.TestCase):
    def test_parse_amount(self):
        p = erg.parse_amount
        self.assertEqual(erg.normalize(p("$1,250,000")), "1250000")
        self.assertEqual(erg.normalize(p("750k")), "750000")
        self.assertEqual(erg.normalize(p("1.5M")), "1500000")
        self.assertEqual(erg.normalize(p(2000000)), "2000000")
        self.assertEqual(erg.normalize(p(1e6)), "1000000")
        for bad in (None, "", "0", "-1", "abc", "1e9", True, False, "1.2.3", "5 million"):
            self.assertIsNone(p(bad), repr(bad))


class TestNoPersonalData(unittest.TestCase):
    def test_script_has_no_chat_id_email_or_hardcoded_amount(self):
        text = SCRIPT.read_text()
        self.assertIsNone(re.search(r"\b\d{9,}\b", text), "chat-id-like number in script")
        self.assertIsNone(re.search(r"[\w.]+@[\w.]+\.\w+", text), "email in script")
        self.assertNotIn("openclaw config get", text)  # never dumps config (secrets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
