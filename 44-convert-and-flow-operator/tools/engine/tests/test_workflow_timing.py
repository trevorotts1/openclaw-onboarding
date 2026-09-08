"""Offline timing and build refusal regressions; no client data or network."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cli_anything.gohighlevel.utils.workflow_timing import plan_timing
from cli_anything.gohighlevel.utils.workflow_builder import CampaignBuilder, validate_campaign, wait_step


def anchor(source="fixture.registration_timestamp"):
    return dict(source=source, timezone="America/New_York", past_due="skip", reentry="once")


def event(step_id, offset, key="registration", unit="days"):
    return dict(id=step_id, kind="event", anchor=key, offset=offset, unit=unit)


class TimingTests(unittest.TestCase):
    def test_day_four_and_seven_share_day_zero(self):
        result = plan_timing([event("d4", 4), event("d7", 7)], {"registration": anchor()})
        self.assertEqual([n["action"] for n in result["nodes"]],
                         ["set_event_start_time", "wait_until_event", "wait_until_event"])
        self.assertEqual([n["offset"] for n in result["nodes"][1:]], [4, 7])
        self.assertTrue(result["requires_event_start"])

    def test_webinar_before_uses_webinar_not_registration(self):
        result = plan_timing([event("remind", -1, "webinar")],
                             {"registration": anchor(), "webinar": anchor("fixture.webinar_start")})
        self.assertEqual(result["nodes"][0]["source"], "fixture.webinar_start")
        self.assertEqual(result["nodes"][1]["offset"], -1)

    def test_previous_message_delay_does_not_add_event(self):
        result = plan_timing([dict(id="later", kind="delay", offset=2, unit="hours")], {})
        self.assertFalse(result["requires_event_start"])
        self.assertEqual(len(result["nodes"]), 1)

    def test_switching_anchors_restores_correct_reference(self):
        result = plan_timing([event("a", 4), event("b", -1, "webinar"), event("c", 7)],
                             {"registration": anchor(), "webinar": anchor("fixture.webinar_start")})
        self.assertEqual([n["anchor"] for n in result["nodes"] if n["action"] == "set_event_start_time"],
                         ["registration", "webinar", "registration"])

    def test_delay_does_not_reset_event_start(self):
        result = plan_timing([event("a", 4), dict(id="b", kind="delay", offset=2, unit="hours"), event("c", 7)],
                             {"registration": anchor()})
        self.assertEqual(sum(n["action"] == "set_event_start_time" for n in result["nodes"]), 1)

    def test_missing_or_invalid_anchor_configuration_is_rejected(self):
        for field, value in [("source", ""), ("timezone", "Moon/Base"), ("past_due", None), ("reentry", "reset")]:
            with self.subTest(field=field):
                data = anchor()
                data[field] = value
                with self.assertRaises(ValueError):
                    plan_timing([event("a", 4)], {"registration": data})
        with self.assertRaisesRegex(ValueError, "date source"):
            plan_timing([event("a", 4)], {})

    def test_bad_requirements_are_rejected(self):
        for requirements in ([event("a", 7), event("b", 4)], [event("a", 4), event("a", 7)],
                             [event("a", float("nan"))], [event("a", True)],
                             [dict(id="a", kind="unknown", offset=2, unit="days")],
                             [dict(id="a", kind="delay", offset=-1, unit="hours")]):
            with self.subTest(requirements=requirements), self.assertRaises(ValueError):
                plan_timing(requirements, {"registration": anchor()})

    def test_planning_is_repeatable_without_mutating_source(self):
        requirements, anchors = [event("a", 4)], {"registration": anchor()}
        original = copy.deepcopy(anchors)
        self.assertEqual(plan_timing(requirements, anchors), plan_timing(requirements, anchors))
        self.assertEqual(anchors, original)

    def test_event_plan_cannot_fall_through_to_duration_api_or_network(self):
        client = MagicMock()
        client.location_id = "FIXTURE_LOCATION"
        builder = CampaignBuilder(client)
        campaign = {"wf": {"name": "Fixture", "templates": [wait_step("Day 4", 4, id="d4")],
                           "timing": {"requirements": [event("d4", 4)], "anchors": {"registration": anchor()}}}}
        result = builder._build_locked(campaign, folder_name="Fixture")
        self.assertIn("managed browser", " ".join(result["errors"]))
        client.request.assert_not_called()

    def test_invalid_legacy_step_also_stops_before_network(self):
        client = MagicMock()
        result = CampaignBuilder(client)._build_locked({"wf": {"name": "Fixture", "templates": [{}]}}, folder_name="Fixture")
        self.assertTrue(result["errors"])
        client.request.assert_not_called()

    def test_ordinary_wait_contract_checks_actual_payload(self):
        wf = {"name": "Fixture", "templates": [wait_step("Later", 2, "hours", id="later")],
              "timing": {"requirements": [dict(id="later", kind="delay", offset=2, unit="hours")]}}
        self.assertEqual(validate_campaign({"wf": wf}), [])
        wf["templates"][0]["attributes"]["startAfter"]["value"] = 7
        self.assertIn("does not match", " ".join(validate_campaign({"wf": wf})))

    def test_legacy_ordinary_wait_remains_valid(self):
        self.assertEqual(validate_campaign({"wf": {"name": "Fixture", "templates": [wait_step("Later", 2)]}}), [])


if __name__ == "__main__":
    unittest.main()
