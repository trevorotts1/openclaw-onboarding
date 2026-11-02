"""The client summary never calls a design-only page finished (DTY-11 D1/thank-you, UPS-32 U1/U2)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

from launcher_core import launch_bridge  # noqa: E402


def report(*pages, **extra) -> dict:
    return {"pages": list(pages), "page_labels": list(pages),
            "lane_plan": {"phase_1_alone": [], "independent_pages": len(pages)},
            "parallel": "parallel", "paid_calls_allowed": False, "to_confirm": [], **extra}


def starting(lines, prefix):
    return [line for line in lines if line.startswith(prefix)]


class SummaryDesignOnlyTests(unittest.TestCase):
    def test_d1_and_thank_you_are_design_only_until_skill_6_records_a_read_back(self):
        rep = report("landing", "downsell_1", "thank_you")
        lines = launch_bridge.summary_lines(rep)
        self.assertEqual(len(starting(lines, "Downsell (D1): design only; not installed")), 1)
        self.assertEqual(len(starting(lines, "Thank-you page: design only; not installed")), 1)
        rep["skill06_readbacks"] = {"downsell_1": {"ok": True}}
        lines = launch_bridge.summary_lines(rep)
        self.assertEqual(starting(lines, "Downsell (D1)"), [])
        self.assertEqual(len(starting(lines, "Thank-you page: design only; not installed")), 1)

    def test_u1_and_u2_are_design_only_whatever_skill_6_recorded(self):
        rep = report("landing", "upsell_1", "upsell_2", skill06_readbacks={"upsell_1": {"ok": True}})
        lines = launch_bridge.summary_lines(rep)
        self.assertEqual(len(starting(lines, "Upsell 1 (U1): design only")), 1)
        self.assertEqual(len(starting(lines, "Upsell 2 (U2): design only")), 1)
        plain = launch_bridge.summary_lines(report("landing"))
        self.assertEqual(starting(plain, "Upsell"), [])
        self.assertEqual(starting(plain, "Downsell"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
