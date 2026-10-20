"""Scheduler checks — checklist S1, deterministic, stdlib unittest.

Run: python3 shared-utils/signature_launch/scheduler/test_scheduler.py
"""

import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scheduler

FIXTURES = Path(__file__).resolve().parents[2] / "signature_launch_contract" / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def free_pages_plan(count=3):
    plan = fixture("elevation.json")
    plan["pages"] = [
        {"id": "page_%d" % number, "kind": "other",
         "url": "https://example.com/%d" % number, "waits_for": []}
        for number in range(count)
    ]
    plan["email_sequences"] = []
    plan["text_sets"] = []
    plan["automations"] = []
    return plan


class SchedulerTests(unittest.TestCase):
    def test_free_units_share_one_wave(self):
        waves = scheduler.schedule_waves(fixture("elevation.json"))
        self.assertEqual(waves[0], ["page_landing", "page_sales"])

    def test_ready_work_is_not_queued(self):
        # page_checkout, email_pre_launch and email_main_launch all become
        # ready the moment their own deps finish; they start together.
        waves = scheduler.schedule_waves(fixture("elevation.json"))
        self.assertEqual(
            waves[1], ["email_main_launch", "email_pre_launch", "page_checkout"]
        )

    def test_every_fixture_schedules_without_stalling(self):
        for path in sorted(FIXTURES.glob("*.json")):
            plan = json.loads(path.read_text(encoding="utf-8"))
            waves = scheduler.schedule_waves(plan)
            covered = [unit for wave in waves for unit in wave]
            self.assertEqual(len(covered), len(set(covered)), path.name)
            self.assertEqual(len(covered), len(scheduler.unit_index(plan)), path.name)

    def test_automation_waits_for_its_emails(self):
        plan = fixture("elevation.json")
        index = scheduler.unit_index(plan)
        done = {"page_landing", "page_sales", "page_checkout", "page_thank_you"}
        reasons = scheduler.blockers("auto_pre_launch", index, done)
        self.assertIn("waits for email_pre_launch", reasons)

    def test_automation_waits_for_page_urls(self):
        plan = fixture("elevation.json")
        plan["pages"][1]["url"] = None  # page_sales planned, no approved URL
        index = scheduler.unit_index(plan)
        done = set(index) - {"auto_pre_launch"}
        reasons = scheduler.blockers("auto_pre_launch", index, done)
        self.assertIn("page page_sales has no approved URL", reasons)

    def test_wave_starts_all_ready_units_concurrently(self):
        plan = free_pages_plan(3)
        barrier = threading.Barrier(3)

        def runner(unit_id, entry):
            barrier.wait(timeout=5)  # serial execution breaks the barrier
            return unit_id

        started = scheduler.start(plan, set(), runner)
        self.assertEqual([entry["id"] for entry in started],
                         ["page_0", "page_1", "page_2"])
        self.assertTrue(all(entry["ok"] for entry in started), started)

    def test_one_failure_does_not_cancel_the_wave(self):
        plan = free_pages_plan(3)

        def runner(unit_id, entry):
            if unit_id == "page_1":
                raise RuntimeError("boom")
            return unit_id

        started = scheduler.start(plan, set(), runner)
        status = {entry["id"]: entry["ok"] for entry in started}
        self.assertEqual(status, {"page_0": True, "page_1": False, "page_2": True})
        failed = [entry for entry in started if not entry["ok"]][0]
        self.assertIn("RuntimeError: boom", failed["error"])

    def test_run_all_does_not_retry_a_failed_unit(self):
        plan = free_pages_plan(3)
        calls = []

        def runner(unit_id, entry):
            calls.append(unit_id)
            if unit_id == "page_1":
                raise RuntimeError("boom")
            return unit_id

        report = scheduler.run_all(plan, runner)
        self.assertEqual(calls.count("page_1"), 1)
        self.assertEqual(report["completed"], ["page_0", "page_2"])
        self.assertEqual(report["blocked"], ["page_1"])

    def test_implicit_stall_is_reported(self):
        plan = fixture("elevation.json")
        plan["pages"] = [{"id": "page_landing", "kind": "landing",
                          "url": "https://example.com/elevation",
                          "waits_for": ["auto_pre_launch"]}]
        plan["email_sequences"] = []
        plan["text_sets"] = []
        plan["automations"] = [{"id": "auto_pre_launch", "family": "pre_launch",
                                "template": "new", "build_rail": "unknown",
                                "draft_only": True,
                                "trigger": {"type": "launch_calendar"},
                                "waits_for": []}]
        with self.assertRaises(scheduler.SchedulerError) as caught:
            scheduler.schedule_waves(plan)
        self.assertIn("stalled", str(caught.exception))

    def test_invalid_plan_is_refused(self):
        plan = fixture("elevation.json")
        plan["pages"][0]["waits_for"] = ["does_not_exist"]
        with self.assertRaises(scheduler.SchedulerError):
            scheduler.validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
