"""Scheduler checks — checklist S1, deterministic, stdlib unittest.

Run: python3 shared-utils/signature_launch/scheduler/test_scheduler.py
"""

import json
import sys
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scheduler

FIXTURES = HERE.parents[1] / "signature_launch_contract" / "fixtures"
LOCAL = HERE / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def local(name):
    return json.loads((LOCAL / name).read_text(encoding="utf-8"))


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
        self.assertEqual([row["id"] for row in report["blocked"]], ["page_1"])

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

    # --- L03 regressions -------------------------------------------------

    def test_returned_failure_never_unlocks_dependents(self):
        plan = {
            "launch_id": "l03-regression",
            "conversation_ai": {"requested": False, "mode": "none"},
            "pages": [
                {"id": "page_first", "kind": "landing", "url": "https://example.invalid/a",
                 "waits_for": []},
                {"id": "page_second", "kind": "sales", "url": "https://example.invalid/b",
                 "waits_for": ["page_first"]},
            ],
            "email_sequences": [], "text_sets": [], "automations": [],
        }
        calls = []

        def runner(unit_id, entry):
            calls.append(unit_id)
            if unit_id == "page_first":
                return {"status": "failed", "detail": "provider refused"}
            return {"status": "verified_success", "verified": True}

        report = scheduler.run_all(plan, runner)
        self.assertEqual(calls, ["page_first"], "dependent must never run")
        self.assertEqual(report["completed"], [])
        self.assertFalse(report["complete"])
        blocked = {row["id"]: row for row in report["blocked"]}
        self.assertIn("failed returned", " ".join(blocked["page_second"]["blockers"]))
        self.assertTrue(blocked["page_first"]["retryable"])

    def test_legacy_ok_false_is_a_failure(self):
        plan = free_pages_plan(2)

        def runner(unit_id, entry):
            return {"ok": False, "error": "synthetic refusal"}

        report = scheduler.run_all(plan, runner)
        self.assertEqual(report["completed"], [])
        self.assertEqual(len(report["failed"]), 2)
        self.assertIsNotNone(report["stall"])

    def test_dropped_is_terminal_and_failure_is_not(self):
        plan = free_pages_plan(1)

        def dropped(unit_id, entry):
            return {"status": "dropped", "detail": "client dropped"}

        report = scheduler.run_all(plan, dropped)
        self.assertEqual(report["dropped"], ["page_0"])
        self.assertEqual(report["completed"], [])
        self.assertTrue(report["complete"])

        def failed(unit_id, entry):
            return {"status": "failed"}

        report = scheduler.run_all(plan, failed)
        self.assertFalse(report["complete"])

    def test_run_all_returns_partial_results_instead_of_raising(self):
        plan = local("plan_stall.json")
        calls = []

        def runner(unit_id, entry):
            calls.append(unit_id)
            if unit_id == "page_landing":
                return {"status": "failed", "detail": "synthetic timeout"}
            return {"status": "awaiting_facts", "missing_facts": ["sender_name"]}

        report = scheduler.run_all(plan, runner)
        self.assertFalse(report["complete"])
        self.assertIsNotNone(report["stall"])
        self.assertIn("page_landing", report["failed"] + [r["id"] for r in report["blocked"]])
        blocked = {row["id"]: row for row in report["blocked"]}
        self.assertTrue(blocked["page_sales"]["causal"],
                        "a blocked unit carries its causal blocker")
        self.assertEqual(calls.count("page_landing"), 1)

    def test_running_unit_is_not_ready_work(self):
        plan = free_pages_plan(2)
        ready = scheduler.ready_units(plan, set(), running={"page_0"})
        self.assertEqual(ready, ["page_1"])
        report = scheduler.run_all(plan, lambda uid, entry: uid, running={"page_0"})
        self.assertNotIn("page_0", report["resolved"])

    def test_empty_plan_is_explicitly_empty(self):
        plan = local("plan_empty.json")
        self.assertEqual(scheduler.unit_index(plan), {})
        self.assertEqual(scheduler.schedule_waves(plan), [])
        report = scheduler.run_all(plan, lambda uid, entry: uid)
        self.assertTrue(report["complete"])
        self.assertTrue(report["empty"])
        self.assertEqual(report["completed"], [])
        self.assertEqual(report["waves"], [])

    def test_requested_ai_is_distinct_from_reply_wiring(self):
        on = scheduler.ai_state(local("plan_ai_on.json"))
        self.assertTrue(on["requested_config"]["requested"])
        self.assertEqual(on["requested_config"]["mode"], "faq")
        self.assertEqual(on["reply_wiring"]["units"], ["auto_ai_reply"])

        off = scheduler.ai_state(local("plan_ai_off.json"))
        self.assertFalse(off["requested_config"]["requested"])
        self.assertFalse(off["reply_wiring"]["wired"])
        self.assertTrue(off["consistent"])

        # Requested AI with no reply unit yet: still a valid schedule, and the
        # request is never mistaken for wiring.
        plan = local("plan_ai_off.json")
        plan["conversation_ai"] = {"requested": True, "mode": "faq"}
        ai = scheduler.ai_state(plan)
        self.assertFalse(ai["reply_wiring"]["wired"])
        self.assertTrue(ai["requested_config"]["requested"])
        waves = scheduler.schedule_waves(plan)
        self.assertIn("page_landing", waves[0])


if __name__ == "__main__":
    unittest.main()
