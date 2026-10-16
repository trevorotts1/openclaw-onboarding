"""S63-07 transport policy tests. Offline: sender and sleeper are stubs."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import transport  # noqa: E402

ENV_WITH_KEY = {"AGNES_AI_API_KEY": "test-value-never-asserted"}


class Sequence:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class PreflightTests(unittest.TestCase):
    def test_missing_credential_blocks(self):
        with self.assertRaises(transport.CredentialsMissing):
            transport.preflight("fp", env={}, budget=transport.Budget(1.0),
                                estimated_cost_usd=0.0)

    def test_no_budget_blocks(self):
        with self.assertRaises(transport.BudgetBlocked):
            transport.preflight("fp", env=ENV_WITH_KEY, budget=None,
                                estimated_cost_usd=0.0)

    def test_unverified_cost_blocks_unless_allowed(self):
        with self.assertRaises(transport.BudgetBlocked):
            transport.preflight("fp", env=ENV_WITH_KEY,
                                budget=transport.Budget(1.0), estimated_cost_usd=None)
        status = transport.preflight(
            "fp", env=ENV_WITH_KEY,
            budget=transport.Budget(1.0, allow_unverified_cost=True),
            estimated_cost_usd=None)
        self.assertEqual(status, "unverified")

    def test_over_budget_blocks(self):
        with self.assertRaises(transport.BudgetBlocked):
            transport.preflight("fp", env=ENV_WITH_KEY,
                                budget=transport.Budget(0.10),
                                estimated_cost_usd=0.50)

    def test_presence_never_leaks_value(self):
        self.assertTrue(transport.credential_present(ENV_WITH_KEY))
        try:
            transport.preflight("fp", env={"OTHER": "x"}, budget=transport.Budget(1.0),
                                estimated_cost_usd=0.0)
        except transport.CredentialsMissing as exc:
            self.assertNotIn("test-value", str(exc))


class SendPolicyTests(unittest.TestCase):
    def test_200_first_try(self):
        sender = Sequence([(200, b"{}")])
        result = transport.send_with_policy(sender, {}, request_fingerprint="fp")
        self.assertEqual(result.status, 200)
        self.assertEqual(sender.calls, 1)

    def test_auth_stops_without_retry(self):
        for code in (401, 403):
            sender = Sequence([(code, b"")] * 5)
            with self.assertRaises(transport.AuthStopped):
                transport.send_with_policy(sender, {}, request_fingerprint="fp")
            self.assertEqual(sender.calls, 1)

    def test_429_bounded_backoff_then_success(self):
        sleeps = []
        sender = Sequence([(429, b""), (429, b""), (200, b"{}")])
        result = transport.send_with_policy(sender, {}, request_fingerprint="fp",
                                            sleeper=sleeps.append)
        self.assertEqual(result.status, 200)
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_429_exhaustion_raises(self):
        sender = Sequence([(429, b"")] * 10)
        with self.assertRaises(transport.RateLimited):
            transport.send_with_policy(sender, {}, request_fingerprint="fp")
        self.assertEqual(sender.calls, 1 + transport.MAX_429_RETRIES)

    def test_5xx_bounded_retry(self):
        sender = Sequence([(503, b"")] * 10)
        with self.assertRaises(transport.TransportError):
            transport.send_with_policy(sender, {}, request_fingerprint="fp")
        self.assertEqual(sender.calls, 1 + transport.MAX_5XX_RETRIES)

    def test_timeout_is_ambiguous_and_never_resubmits(self):
        sender = Sequence([TimeoutError("read timed out"), (200, b"{}")])
        with self.assertRaises(transport.AmbiguousOutcome) as ctx:
            transport.send_with_policy(sender, {}, request_fingerprint="fp-123")
        self.assertEqual(ctx.exception.request_fingerprint, "fp-123")
        self.assertEqual(sender.calls, 1)

    def test_400_not_retried(self):
        sender = Sequence([(400, b"")] * 5)
        with self.assertRaises(transport.TransportError):
            transport.send_with_policy(sender, {}, request_fingerprint="fp")
        self.assertEqual(sender.calls, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
