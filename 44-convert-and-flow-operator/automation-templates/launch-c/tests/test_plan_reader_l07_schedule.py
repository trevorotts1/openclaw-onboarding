"""L07 (UL-010) calendar/schedule/eligibility compiler checks.

Synthetic-local only: no provider call, no send, no credential.
Run: python3 launch-c/tests/test_plan_reader_l07_schedule.py
"""

import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAUNCH_C = HERE.parent
_spec = importlib.util.spec_from_file_location("plan_reader_l07", LAUNCH_C / "plan_reader.py")
plan_reader = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plan_reader)

NOW = datetime.fromisoformat("2026-11-01T00:00:00-05:00")


def email_step(index):
    return {"id": "e%d" % index, "type": "email", "name": "Email %d" % index,
            "attributes": {"subject": "s%d" % index, "body": "<p>b</p>",
                           "html": "<p>b</p>", "fromName": "Synthetic Sender"}}


def wait_step(index, value, unit="days"):
    return {"id": "w%d" % index, "type": "wait", "name": "Wait",
            "attributes": {"type": "time",
                           "startAfter": {"type": unit, "value": value, "when": "after"}}}


def plan_doc(calendar=None, page_url="https://example.com/landing", sequences=None,
             automations=None, text_sets=None, offer=True):
    calendar = calendar or {
        "launch_at": "2026-11-03T12:00:00-05:00",
        "doors_open_at": "2026-11-03T09:00:00-05:00",
        "doors_close_at": "2026-11-10T23:59:00-05:00",
        "timezone": "America/New_York",
    }
    sequences = sequences or [("email_pre_launch", "pre_launch", 2, [])]
    doc = {
        "schema_version": "1.0.0",
        "launch_id": "l07-synthetic",
        "launch_calendar": calendar,
        "pages": [{"id": "page_landing", "kind": "landing", "url": page_url,
                   "waits_for": []}],
        "email_sequences": [
            {"id": seq_id, "kind": kind, "provider": "skill50",
             "email_count": count, "draft_only": True, "waits_for": waits}
            for seq_id, kind, count, waits in sequences
        ],
        "text_sets": text_sets or [],
        "automations": automations or [
            {"id": "auto_pre_launch", "family": "pre_launch", "template": "new",
             "build_rail": "skill44_engine", "draft_only": True,
             "trigger": {"type": "tag_added"}, "waits_for": ["email_pre_launch"]}
        ],
    }
    if offer:
        doc["offer"] = {"name": "Synthetic", "price_usd": 1, "currency": "USD",
                        "payment_plans": False}
    return doc


def build_doc(seq_id, email_count, waits=(), meta=None):
    templates = []
    for index in range(email_count):
        templates.append(email_step(index))
        if index < email_count - 1 and waits:
            value, unit = waits[min(index, len(waits) - 1)]
            templates.append(wait_step(index, value, unit))
    document = {
        "folder": "Synthetic Drafts",
        "_meta": {"sequence_id": seq_id, "draft_only": True,
                  "deploy_mode": "draft-only"},
        seq_id: {"name": seq_id, "status": "draft", "templates": templates},
    }
    if meta:
        document["_meta"].update(meta)
    return document


class Harness:
    def __init__(self, plan, builds):
        self.temp = Path(tempfile.mkdtemp())
        self.plan_path = self.temp / "plan.json"
        self.plan_path.write_text(json.dumps(plan))
        self.build_paths = []
        for seq_id, doc in builds.items():
            path = self.temp / ("build-%s.json" % seq_id)
            path.write_text(json.dumps(doc))
            self.build_paths.append(path)

    def run(self, now=NOW):
        argv = ["--launch-plan", str(self.plan_path), "--out",
                str(self.temp / "out.json"), "--now", now.isoformat()]
        for path in self.build_paths:
            argv += ["--build-plan", str(path)]
        rc = plan_reader.main(argv)
        out = self.temp / "out.json"
        return rc, (json.loads(out.read_text()) if out.exists() else None)


class CalendarTests(unittest.TestCase):
    def test_invalid_iana_zone_fails_closed(self):
        plan = plan_doc()
        plan["launch_calendar"]["timezone"] = "America/Not_A_City"
        rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 2)}).run()
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)

    def test_offset_disagreeing_with_zone_fails_closed(self):
        plan = plan_doc()
        plan["launch_calendar"]["launch_at"] = "2026-11-03T12:00:00-08:00"
        rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 2)}).run()
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)

    def test_dst_gap_fails_closed(self):
        plan = plan_doc(calendar={
            "launch_at": "2026-03-08T03:30:00-04:00",
            "doors_open_at": "2026-03-08T01:00:00-05:00",
            "doors_close_at": "2026-03-09T23:59:00-04:00",
            "timezone": "America/New_York",
        })
        plan["launch_calendar"]["launch_at"] = "2026-03-08T02:30:00-05:00"
        rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 2)}).run()
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)

    def test_dst_overlap_accepts_either_offset_and_normalizes(self):
        # 2026-11-01 01:30 America/New_York occurs twice (EDT -04:00, EST -05:00).
        for offset in ("-04:00", "-05:00"):
            plan = plan_doc(calendar={
                "launch_at": "2026-11-01T01:30:00%s" % offset,
                "doors_open_at": "2026-10-30T09:00:00-04:00",
                "doors_close_at": "2026-11-05T23:59:00-05:00",
                "timezone": "America/New_York",
            })
            rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 2)}).run()
            self.assertEqual(rc, 0, offset)
            self.assertTrue(doc["calendar"]["dst_ambiguous"])
            self.assertTrue(doc["calendar"]["launch_at"].endswith(offset), doc["calendar"])

    def test_phase_order_is_strict(self):
        plan = plan_doc()
        plan["launch_calendar"]["launch_at"] = plan["launch_calendar"]["doors_open_at"]
        rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 2)}).run()
        self.assertEqual(rc, 2)
        self.assertIsNone(doc)


class ScheduleCompileTests(unittest.TestCase):
    def _calendar(self):
        return {
            "launch_at": "2026-11-03T12:00:00-05:00",
            "doors_open_at": "2026-11-03T09:00:00-05:00",
            "doors_close_at": "2026-11-10T23:59:00-05:00",
            "timezone": "America/New_York",
        }

    def test_absolute_nodes_finish_before_their_phase_boundary(self):
        plan = plan_doc(
            calendar=self._calendar(),
            sequences=[
                ("email_pre_launch", "pre_launch", 2, []),
                ("email_doors_closing", "doors_closing", 2, ["email_pre_launch"]),
            ],
            automations=[{
                "id": "auto_pre_launch", "family": "pre_launch", "template": "new",
                "build_rail": "skill44_engine", "draft_only": True,
                "trigger": {"type": "tag_added"},
                "waits_for": ["email_pre_launch", "email_doors_closing"],
            }],
        )
        builds = {
            "email_pre_launch": build_doc("email_pre_launch", 2, waits=[(1, "days")]),
            "email_doors_closing": build_doc("email_doors_closing", 2, waits=[(2, "hours")]),
        }
        rc, doc = Harness(plan, builds).run()
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        self.assertEqual(build["state"], "ready", build["blocked_by"])
        nodes = build["schedule"]["nodes"]
        open_at = datetime.fromisoformat("2026-11-03T09:00:00-05:00")
        close_at = datetime.fromisoformat("2026-11-10T23:59:00-05:00")
        pre = [n for n in nodes if n["phase"] == "pre_launch"]
        closing = [n for n in nodes if n["phase"] == "doors_closing"]
        self.assertTrue(pre and all(n["kind"] == "absolute" for n in pre))
        self.assertTrue(all(datetime.fromisoformat(n["at"]) < open_at for n in pre))
        self.assertTrue(closing and all(datetime.fromisoformat(n["at"]) < close_at
                                        for n in closing))
        self.assertEqual([n["phase"] for n in build["schedule"]["calendar_nodes"]],
                         ["doors_open", "launch", "doors_close"])

    def test_late_compile_suppresses_expired_prelaunch_ctas(self):
        plan = plan_doc(calendar=self._calendar())
        late = datetime.fromisoformat("2026-11-03T10:00:00-05:00")
        rc, doc = Harness(plan, {"email_pre_launch": build_doc(
            "email_pre_launch", 2, waits=[(1, "days")])}).run(now=late)
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        self.assertEqual(build["state"], "blocked")
        self.assertIn("schedule_suppressed:email_pre_launch", build["blocked_by"])
        self.assertTrue(build["suppressed"])
        self.assertTrue(all(item["reason"] == "PAST-TIME-SUPPRESSED"
                            for item in build["suppressed"]))

    def test_short_prelaunch_suppresses_nodes_that_would_land_in_the_past(self):
        # 30-day pre-launch inside a 2-day window: every node is already past.
        plan = plan_doc(calendar=self._calendar())
        builds = {"email_pre_launch": build_doc(
            "email_pre_launch", 2, waits=[(30, "days")])}
        rc, doc = Harness(plan, builds).run(now=datetime.fromisoformat(
            "2026-11-03T08:59:30-05:00"))
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        self.assertEqual(build["state"], "blocked")
        self.assertEqual(len(build["suppressed"]), 2)

    def test_midnight_close_never_schedules_at_or_after_close(self):
        calendar = {
            "launch_at": "2026-11-03T12:00:00-05:00",
            "doors_open_at": "2026-11-03T09:00:00-05:00",
            "doors_close_at": "2026-11-11T00:00:00-05:00",
            "timezone": "America/New_York",
        }
        plan = plan_doc(
            calendar=calendar,
            sequences=[("email_doors_closing", "doors_closing", 2, [])],
            automations=[{
                "id": "auto_closing", "family": "pre_launch", "template": "new",
                "build_rail": "skill44_engine", "draft_only": True,
                "trigger": {"type": "tag_added"}, "waits_for": ["email_doors_closing"],
            }],
        )
        rc, doc = Harness(plan, {"email_doors_closing": build_doc(
            "email_doors_closing", 2, waits=[(2, "hours")])}).run()
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        close_at = datetime.fromisoformat(calendar["doors_close_at"])
        ats = [datetime.fromisoformat(n["at"]) for n in build["schedule"]["nodes"]]
        self.assertTrue(ats)
        self.assertTrue(all(at < close_at for at in ats), ats)
        self.assertEqual(build["state"], "ready", build["blocked_by"])

    def test_relative_phase_carries_runtime_close_guard(self):
        calendar = {
            "launch_at": "2026-11-03T12:00:00-05:00",
            "doors_open_at": "2026-11-03T09:00:00-05:00",
            "doors_close_at": "2026-11-10T23:59:00-05:00",
            "timezone": "America/New_York",
        }
        plan = plan_doc(
            calendar=calendar,
            sequences=[("email_abandoned_checkout", "abandoned_checkout", 2, [])],
            automations=[{
                "id": "auto_abandoned_checkout", "family": "abandoned_checkout",
                "template": "new", "build_rail": "skill44_engine",
                "draft_only": True, "trigger": {"type": "checkout_started_unpaid"},
                "waits_for": ["email_abandoned_checkout"],
            }],
        )
        rc, doc = Harness(plan, {"email_abandoned_checkout": build_doc(
            "email_abandoned_checkout", 2, waits=[(1, "hours")])}).run()
        self.assertEqual(rc, 0)
        nodes = doc["builds"][0]["schedule"]["nodes"]
        self.assertTrue(nodes)
        self.assertTrue(all(n["kind"] == "relative" and n["at"] is None for n in nodes))
        self.assertTrue(all(n["suppress_after"] == calendar["doors_close_at"]
                            for n in nodes))


class DependencyAndMetadataTests(unittest.TestCase):
    def test_missing_page_url_blocks(self):
        plan = plan_doc()
        plan["automations"][0]["waits_for"] = ["page_landing", "email_pre_launch"]
        plan["pages"][0]["url"] = None
        rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 2)}).run()
        self.assertEqual(rc, 0)
        self.assertIn("page_url:page_landing", doc["builds"][0]["blocked_by"])
        self.assertEqual(doc["builds"][0]["state"], "blocked")

    def test_count_mismatch_blocks(self):
        plan = plan_doc()
        rc, doc = Harness(plan, {"email_pre_launch": build_doc("email_pre_launch", 1)}).run()
        self.assertEqual(rc, 0)
        self.assertIn("email_count:email_pre_launch", doc["builds"][0]["blocked_by"])

    def test_missing_suppression_guards_block(self):
        plan = plan_doc()
        meta = {"lifecycle": {"stop_rules": [{"rule": "stop_on_verified_purchase"}],
                              "suppression_rules": []}}
        rc, doc = Harness(plan, {"email_pre_launch": build_doc(
            "email_pre_launch", 2, meta=meta)}).run()
        self.assertEqual(rc, 0)
        reasons = doc["builds"][0]["blocked_by"]
        self.assertTrue(any(reason.startswith("guards:email_pre_launch:") for reason in reasons),
                        reasons)
        self.assertEqual(doc["builds"][0]["state"], "blocked")

    def test_eligibility_lifecycle_and_sender_metadata_are_carried(self):
        plan = plan_doc()
        meta = {
            "enrollment_conditions": [{"rule": "email_consent_required",
                                       "policy_ref": "approved_communication_policy"}],
            "lifecycle": {
                "stop_rules": [{"rule": "stop_on_verified_purchase",
                                "scope": "this_campaign_only"},
                               {"rule": "stop_on_unsubscribe",
                                "scope": "this_campaign_only"}],
                "suppression_rules": [
                    {"rule": "suppress_promotion_after_verified_purchase",
                     "event": "purchase_verified", "applies_to": "all_remaining_email_steps"},
                    {"rule": "recheck_eligibility_immediately_before_send",
                     "applies_to": "each_scheduled_email_step",
                     "checks": ["verified_purchase", "unsubscribe"]},
                ],
            },
            "sender_config_refs": {"sender_profile_ref": "sender-config:launch",
                                   "reply_to_ref": "sender-config:launch"},
        }
        rc, doc = Harness(plan, {"email_pre_launch": build_doc(
            "email_pre_launch", 2, meta=meta)}).run()
        self.assertEqual(rc, 0)
        build = doc["builds"][0]
        self.assertEqual(build["state"], "ready", build["blocked_by"])
        self.assertEqual(build["eligibility"],
                         [{"rule": "email_consent_required",
                           "policy_ref": "approved_communication_policy"}])
        self.assertEqual(build["sender"]["sender_profile_ref"], "sender-config:launch")
        rules = {rule["rule"] for rule in build["lifecycle"]["suppression_rules"]}
        self.assertIn("suppress_promotion_after_verified_purchase", rules)
        self.assertEqual(build["required_outputs"], ["workflows", "schedule", "guards"])
        self.assertIn(build["unit_key"], doc["journal"]["stable_unit_keys"])
        self.assertEqual(len(build["expected_graph_hash"]), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
