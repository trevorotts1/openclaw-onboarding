import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests._support  # noqa: E402,F401 - puts the skill-tree module on sys.path

from capability_control.failures import (  # noqa: E402
    AccountBreaker, BoundedPolicy, classify,
)

NOW = 1_760_000_000.0


class TestClassification(unittest.TestCase):
    """Acceptance: hard-cap failures are classified distinctly from temporary
    throttling and transient service errors."""

    def test_credit_cap_is_hard(self):
        f = classify({"status": 402, "message": "Payment required: credit cap reached"}, now=NOW)
        self.assertEqual(f.kind, "CREDIT_EXHAUSTED")
        self.assertTrue(f.hard)

    def test_monthly_cap_is_hard_even_with_a_short_reset_message(self):
        f = classify({"status": 429, "message": "Monthly usage limit reached; try again tomorrow",
                      "headers": {"retry-after": "60"}}, now=NOW)
        self.assertEqual(f.kind, "HARD_QUOTA")
        self.assertTrue(f.hard)

    def test_throttle_is_not_hard_and_keeps_authoritative_retry_at(self):
        f = classify({"status": 429, "message": "Too many requests",
                      "headers": {"retry-after": "30"}}, now=NOW)
        self.assertEqual(f.kind, "THROTTLED")
        self.assertFalse(f.hard)
        self.assertEqual(f.retry_at, NOW + 30)
        self.assertEqual(f.retry_at_source, "authoritative")

    def test_transient_service_error(self):
        f = classify({"status": 502, "message": "Bad Gateway"}, now=NOW)
        self.assertEqual(f.kind, "TRANSIENT_SERVICE_ERROR")
        self.assertFalse(f.hard)

    def test_authorization_failure_is_hard(self):
        f = classify({"status": 401, "message": "Invalid API key"}, now=NOW)
        self.assertEqual(f.kind, "AUTHORIZATION_FAILURE")
        self.assertTrue(f.hard)

    def test_suspension_is_hard(self):
        f = classify({"status": 403, "message": "Account suspended"}, now=NOW)
        self.assertEqual(f.kind, "ACCOUNT_SUSPENDED")
        self.assertTrue(f.hard)

    def test_hard_cap_without_authoritative_retry_gets_no_invented_short_reset(self):
        f = classify({"status": 429, "message": "Monthly usage limit reached"}, now=NOW)
        self.assertEqual(f.kind, "HARD_QUOTA")
        self.assertIsNone(f.retry_at)
        self.assertEqual(f.retry_at_source, "none")

    def test_explicit_bounded_policy_is_labelled_policy_derived(self):
        policy = BoundedPolicy(hard_failure_retry_after_s=3600)
        f = classify({"status": 402, "message": "Payment required"}, policy=policy, now=NOW)
        self.assertEqual(f.retry_at, NOW + 3600)
        self.assertEqual(f.retry_at_source, "bounded_policy")


class TestBreaker(unittest.TestCase):
    """Acceptance: one actionable breaker event; queued launches suppressed;
    deterministic observation continues."""

    def test_one_actionable_event_under_a_swarm_of_identical_failures(self):
        breaker = AccountBreaker(now_fn=lambda: NOW)
        env = {"status": 402, "message": "Payment required: credit cap reached"}
        first = breaker.record_failure("openrouter-account", env)
        self.assertIsNotNone(first)
        for _ in range(25):
            self.assertIsNone(breaker.record_failure("openrouter-account", env))
        self.assertEqual(len(breaker.events), 1)
        self.assertEqual(len(breaker.open_events()), 1)
        self.assertTrue(first.action.startswith("operator:"))

    def test_queued_launches_suppressed_while_deterministic_scheduling_continues(self):
        breaker = AccountBreaker(now_fn=lambda: NOW)
        breaker.record_failure("acct", {"status": 402, "message": "Payment required"})
        admitted = [breaker.admit("acct") for _ in range(5)]
        self.assertEqual(admitted, [False] * 5)
        self.assertEqual(breaker.suppressed_count("acct"), 5)
        self.assertTrue(breaker.deterministic_admit())  # observation/report jobs keep running

    def test_throttle_and_transient_never_open_the_breaker(self):
        breaker = AccountBreaker(now_fn=lambda: NOW)
        self.assertIsNone(breaker.record_failure("acct", {"status": 429, "headers": {"retry-after": "5"}, "message": "Too many requests"}))
        self.assertIsNone(breaker.record_failure("acct", {"status": 503, "message": "Service Unavailable"}))
        self.assertTrue(breaker.admit("acct"))
        self.assertEqual(breaker.events, [])

    def test_completed_outputs_preserved_breaker_closes_once(self):
        breaker = AccountBreaker(now_fn=lambda: NOW)
        breaker.record_failure("acct", {"status": 403, "message": "Account suspended"})
        ev = breaker.close("acct")
        self.assertEqual(ev.status, "closed")
        self.assertFalse(breaker.is_open("acct"))
        self.assertIsNone(breaker.close("acct"))  # no second close event

    def test_hard_cap_retry_elapses_only_at_the_declared_time(self):
        clock = {"t": NOW}
        breaker = AccountBreaker(now_fn=lambda: clock["t"])
        breaker.record_failure("acct", {"status": 429, "message": "Quota exceeded", "headers": {"retry-after": "3600"}})
        self.assertFalse(breaker.admit("acct"))
        clock["t"] = NOW + 3601
        self.assertTrue(breaker.admit("acct"))


if __name__ == "__main__":
    unittest.main()
