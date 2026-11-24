"""SWB-095: the package check replays a LIVE checkout request with the clock Skill 79 demands.

Skill 79 refuses a production-bound request (test_only false) that is not given `now`. The producer's probe
(checkout.replay) passes it; the check's replay (checks._replay_checkout) did not, so a live package whose probe was
accepted failed with "the canonical request still lacks required facts, but the probe recorded 'accepted'".

Literals (codes, messages) are spelled out on purpose.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checks  # noqa: E402


def _stand_in(seen):
    """A validator that behaves like Skill 79 on the one point under test, and records how it was called."""
    module = types.ModuleType("stand_in_validate_checkout")

    def validate_request(request, now=None):
        seen.append((request.get("test_only"), now))
        if request.get("test_only") is False and now is None:
            raise ValueError("production-bound request requires `now` to check mapping expiry")
        if request.get("missing_fact"):
            raise ValueError("checkout_request schema validation failed: 'fulfillment_mapping_ref' is a required property")

    module.validate_request = validate_request
    return module


class LiveClockReplayTests(unittest.TestCase):
    def _replay(self, request):
        seen = []
        with mock.patch.object(checks, "_load_checkout_validator", return_value=_stand_in(seen)):
            return checks._replay_checkout(request), seen

    def test_a_live_request_is_replayed_with_a_clock_and_is_accepted(self):
        (outcome, _detail), seen = self._replay({"test_only": False})
        self.assertEqual(outcome, "accepted")
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0][0], False)
        self.assertTrue(isinstance(seen[0][1], str) and "T" in seen[0][1])

    def test_a_practice_request_is_replayed_without_a_clock_as_before(self):
        (outcome, _detail), seen = self._replay({"test_only": True})
        self.assertEqual(outcome, "accepted")
        self.assertEqual(seen, [(True, None)])

    def test_a_live_request_that_still_lacks_a_fact_is_still_rejected(self):
        (outcome, detail), _seen = self._replay({"test_only": False, "missing_fact": True})
        self.assertEqual(outcome, "rejected")
        self.assertIn("fulfillment_mapping_ref", detail)


if __name__ == "__main__":
    unittest.main()
