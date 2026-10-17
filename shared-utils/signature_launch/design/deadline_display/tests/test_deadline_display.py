"""Deterministic L1 tests for the deadline display (doc 16 s.1, s.8)."""

import importlib.util
import os
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.abspath(os.path.join(HERE, "..", ".."))


def _load(name, *relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(DESIGN, *relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deadline = _load("sl_deadline", "deadline_display", "deadline_display.py")

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


class AbsentState(unittest.TestCase):
    def test_absent_deadline_renders_no_scarcity(self):
        for data in (None, {}, {"deadline_at": None}, {"deadline_at": "  "}):
            result = deadline.render_deadline_display(data, NOW)
            self.assertEqual(result["state"], "absent")
            self.assertIn('data-state="absent"', result["html"])
            self.assertNotIn("<time", result["html"])
            self.assertNotIn("remaining", result["html"])
            self.assertNotIn("passed", result["html"])


class ExpiredState(unittest.TestCase):
    def test_past_deadline_is_expired_and_shows_real_date(self):
        result = deadline.render_deadline_display(
            {
                "deadline_at": "2026-10-01T17:00:00-04:00",
                "timezone": "America/New_York",
                "label": "Registration closes",
            },
            NOW,
        )
        self.assertEqual(result["state"], "expired")
        self.assertIn('data-state="expired"', result["html"])
        self.assertIn("October 01, 2026", result["html"])
        self.assertIn("EDT", result["html"])
        self.assertIn("This deadline has passed.", result["html"])
        self.assertIn("Registration closes", result["html"])

    def test_expired_text_override(self):
        result = deadline.render_deadline_display(
            {
                "deadline_at": "2026-10-01T17:00:00-04:00",
                "timezone": "America/New_York",
                "expired_text": "Enrollment is closed for this cohort.",
            },
            NOW,
        )
        self.assertIn("Enrollment is closed for this cohort.", result["html"])
        self.assertNotIn("This deadline has passed.", result["html"])


class ActiveState(unittest.TestCase):
    def test_future_deadline_active_with_timezone_and_remaining(self):
        result = deadline.render_deadline_display(
            {
                "deadline_at": "2026-10-20T13:00:00-04:00",
                "timezone": "America/New_York",
                "label": "Early registration ends",
            },
            NOW,
        )
        self.assertEqual(result["state"], "active")
        self.assertIn('data-state="active"', result["html"])
        self.assertIn('data-timezone="America/New_York"', result["html"])
        self.assertIn("October 20, 2026", result["html"])
        # Oct 15 12:00 UTC -> Oct 20 17:00 UTC is 5 days, 5 hours.
        self.assertIn("5 days 5 hours 0 minutes remaining", result["html"])


class HonestyGuards(unittest.TestCase):
    def test_unknown_timezone_raises_valueerror_naming_it(self):
        # Documented failure mode: an invalid IANA name surfaces as
        # the component's ValueError naming the value, never as
        # zoneinfo's undocumented ZoneInfoNotFoundError.
        with self.assertRaises(ValueError) as ctx:
            deadline.render_deadline_display(
                {
                    "deadline_at": "2026-10-20T13:00:00-04:00",
                    "timezone": "Not/AZone",
                },
                NOW,
            )
        self.assertIn("Not/AZone", str(ctx.exception))

    def test_absent_state_does_not_consult_timezone(self):
        # The timezone is only consulted when a deadline is present.
        result = deadline.render_deadline_display(
            {"deadline_at": None, "timezone": "Not/AZone"}, NOW
        )
        self.assertEqual(result["state"], "absent")

    def test_naive_deadline_is_rejected(self):
        with self.assertRaises(ValueError):
            deadline.render_deadline_display(
                {"deadline_at": "2026-10-20T17:00:00"}, NOW
            )

    def test_label_is_escaped(self):
        result = deadline.render_deadline_display(
            {
                "deadline_at": "2026-10-20T13:00:00-04:00",
                "timezone": "UTC",
                "label": "<script>alert(1)</script>",
            },
            NOW,
        )
        self.assertIn("&lt;script&gt;", result["html"])
        self.assertNotIn("<script>alert(1)</script>", result["html"])


if __name__ == "__main__":
    unittest.main()
