"""Dispatch-boundary wiring tests (unit S75-W04-U2, finding D30).

These prove the CONSUMER, not the module in isolation: the Skill 75 model
selection / dispatch admission path (choice_card/intake_card/ai_models.py,
admit_dispatch) consults capability_control before any worker is called, so an
unsupported capability claim and a failed account are refused with typed codes
instead of being attempted.

Run: python3 -I -m unittest discover -s tests -t .
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests._support  # noqa: E402,F401 - puts the skill-tree modules on sys.path

from choice_card.intake_card import ai_models as AM  # noqa: E402

MIMO = "openrouter/xiaomi/mimo-v2.6-pro"   # reasoning, NO effort selector
GLM = "openrouter/z-ai/glm-5.3"            # reasoning WITH effort selector


def bound_run():
    run_dir = tempfile.mkdtemp(prefix="s75w04u2-wiring-")
    res = AM.bind_roles(run_dir, MIMO, GLM)
    assert res["ok"], res
    return run_dir


class TestCapabilityClaim(unittest.TestCase):
    """An unsupported capability claim is refused, never attempted."""

    def test_unsupported_effort_claim_is_refused(self):
        run_dir = bound_run()
        res = AM.admit_dispatch(run_dir, "build", capability_claim={"effort": "high"})
        self.assertFalse(res["ok"])
        self.assertEqual("CAPABILITY_UNSUPPORTED", res["error_code"])
        self.assertIn("no effort selector", res["reason"])

    def test_unsupported_capability_need_is_refused(self):
        run_dir = bound_run()
        res = AM.admit_dispatch(run_dir, "check", capability_claim={"needs": ["vision"]})
        self.assertFalse(res["ok"])
        self.assertEqual("CAPABILITY_UNSUPPORTED", res["error_code"])
        self.assertIn("vision", res["reason"])


class TestAccountFailure(unittest.TestCase):
    """A hard account failure opens one breaker event and refuses the launch."""

    def test_failed_account_produces_typed_outcome(self):
        run_dir = bound_run()
        account = "acct-synth-credit-0001"
        ev = AM.record_account_failure(account, {"status": 402, "message": "insufficient credit"})
        self.assertIsNotNone(ev)
        self.assertEqual("CREDIT_EXHAUSTED", ev.kind)
        self.assertIsNone(ev.retry_at)  # no invented short reset for a hard cap
        res = AM.admit_dispatch(run_dir, "build", account=account)
        self.assertFalse(res["ok"])
        self.assertEqual("ACCOUNT_FAILED", res["error_code"])
        self.assertEqual(1, len([e for e in AM.ACCOUNT_BREAKER.open_events()
                                 if e.account == account]))


class TestNormalDispatch(unittest.TestCase):
    """A normal request through the same gate is unchanged."""

    def test_normal_dispatch_still_admits(self):
        run_dir = bound_run()
        res = AM.admit_dispatch(run_dir, "build")
        self.assertTrue(res["ok"])
        self.assertEqual("admit", res["decision"])
        self.assertEqual(MIMO, res["binding"]["model_id"])
        self.assertEqual(AM.dispatch_id(MIMO, "claude-nine"), res["dispatch"]["call_id"])
        healthy = AM.admit_dispatch(run_dir, "build", account="acct-synth-healthy-0001")
        self.assertTrue(healthy["ok"])


if __name__ == "__main__":
    unittest.main()
