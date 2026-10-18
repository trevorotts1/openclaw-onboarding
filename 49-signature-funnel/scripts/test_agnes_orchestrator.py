#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for agnes_orchestrator.py (A24 Leg 4 build A: G-01, G-02,
G-08, G-09, G-10, G-12).

Stdlib unittest only. Every send runs against a scripted fake sender
and a recording fake sleeper; the concrete HTTP sender is exercised
only through an injected fake opener. No test touches the network and
no test uses a real credential: the credential value below is a dummy
string in a test-local env dict, present only so preflight's presence
check can pass and so the audit tests can prove the value never leaks
into any record.

Covers the contract section 11.5 subsets owned by build A: the
preflight failures with sender call count 0; unknown estimate with
unverified cost allowed returning "unverified" threaded into the send
result; the bounded retry matrix; timeout as AmbiguousOutcome
carrying the expected fingerprint with no automatic second call; a
200 returning the raw body, the full attempts list, and the
caller-supplied cost status; and fingerprint stability. Plus the
G-08/G-12 behaviour: the credential-free attempt audit on failure
paths and the fail-closed sender exception policy.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agnes_orchestrator as orch  # noqa: E402
import launch_prompt_policy as policy_mod  # noqa: E402
import resolve_model as resolver  # noqa: E402
import transport  # noqa: E402

TEST_CREDENTIAL = "TEST-CREDENTIAL-NOT-REAL"
ENV_OK = {"AGNES_AI_API_KEY": TEST_CREDENTIAL}
ENV_EMPTY: dict = {}

FULL_ELEMENTS = set(policy_mod.REQUIRED_ELEMENTS)


class FakeSender:
    """Scripted sender: each call consumes one scripted outcome, a
    (status, body) tuple to return or an exception instance to raise.
    Records the call count and a deep copy of each request seen."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.requests_seen = []

    def __call__(self, request):
        self.calls += 1
        self.requests_seen.append(copy.deepcopy(request))
        if not self.script:
            raise AssertionError("fake sender called more times than scripted")
        outcome = self.script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RecordingSleeper:
    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def make_hooks(elements=None):
    """Gate hooks backed by the real merged evaluator, the way the
    gates lane's module will behave for a complete request."""
    chosen = FULL_ELEMENTS if elements is None else elements

    def evaluate_policy(ctx):
        return policy_mod.evaluate_launch_policy(
            ctx.request.prompt, set(chosen),
            policy_mod.CapInfo(status="not_published", chars=None))

    return orch.GateHooks(evaluate_policy=evaluate_policy)


def make_request(**overrides):
    base = dict(
        prompt="A founder portrait in a bright studio, full scene.",
        size="2K",
        budget=transport.Budget(approved_remaining_usd=10.0,
                                allow_unverified_cost=False),
        estimated_cost_usd=0.5,
    )
    base.update(overrides)
    return orch.DispatchRequest(**base)


def run_dispatch(sender, request=None, hooks=None, env=ENV_OK, sleeper=None):
    return orch.dispatch(
        request if request is not None else make_request(),
        hooks=hooks if hooks is not None else make_hooks(),
        sender=sender,
        env=env,
        sleeper=sleeper if sleeper is not None else RecordingSleeper(),
    )


class PreflightGateTests(unittest.TestCase):
    """G-02 / section 11.5: preflight failures, sender call count 0."""

    def test_missing_credential_blocks_sender(self):
        sender = FakeSender([(200, b"img")])
        with self.assertRaises(transport.CredentialsMissing):
            run_dispatch(sender, env=ENV_EMPTY)
        self.assertEqual(sender.calls, 0)

    def test_missing_budget_blocks_sender(self):
        sender = FakeSender([(200, b"img")])
        with self.assertRaises(transport.BudgetBlocked):
            run_dispatch(sender, request=make_request(budget=None))
        self.assertEqual(sender.calls, 0)

    def test_unknown_estimate_not_allowed_blocks_sender(self):
        sender = FakeSender([(200, b"img")])
        request = make_request(estimated_cost_usd=None)
        with self.assertRaises(transport.BudgetBlocked):
            run_dispatch(sender, request=request)
        self.assertEqual(sender.calls, 0)

    def test_estimate_over_budget_blocks_sender(self):
        sender = FakeSender([(200, b"img")])
        request = make_request(estimated_cost_usd=10.01)
        with self.assertRaises(transport.BudgetBlocked):
            run_dispatch(sender, request=request)
        self.assertEqual(sender.calls, 0)

    def test_unverified_cost_threaded_into_send_result(self):
        sender = FakeSender([(200, b"img-bytes")])
        request = make_request(
            estimated_cost_usd=None,
            budget=transport.Budget(approved_remaining_usd=10.0,
                                    allow_unverified_cost=True))
        outcome = run_dispatch(sender, request=request)
        self.assertEqual(outcome.cost_status, "unverified")
        self.assertEqual(outcome.send_result.cost_status, "unverified")

    def test_verified_cost_status_threaded(self):
        sender = FakeSender([(200, b"img-bytes")])
        outcome = run_dispatch(sender)
        self.assertEqual(outcome.cost_status, "verified")
        self.assertEqual(outcome.send_result.cost_status, "verified")
        self.assertEqual(outcome.run_record["cost_status"], "verified")


class RetryMatrixTests(unittest.TestCase):
    """Section 11.5 bounded retry matrix, via the recording sleeper
    (G-09: delays are asserted, never actually slept)."""

    def test_401_auth_stopped_one_call(self):
        sender = FakeSender([(401, b"no")])
        sleeper = RecordingSleeper()
        with self.assertRaises(transport.AuthStopped):
            run_dispatch(sender, sleeper=sleeper)
        self.assertEqual(sender.calls, 1)
        self.assertEqual(sleeper.delays, [])

    def test_403_auth_stopped_one_call(self):
        sender = FakeSender([(403, b"no")])
        sleeper = RecordingSleeper()
        with self.assertRaises(transport.AuthStopped):
            run_dispatch(sender, sleeper=sleeper)
        self.assertEqual(sender.calls, 1)
        self.assertEqual(sleeper.delays, [])

    def test_429_bounded_retry_matrix(self):
        sender = FakeSender([(429, b"")] * 4)
        sleeper = RecordingSleeper()
        with self.assertRaises(transport.RateLimited) as caught:
            run_dispatch(sender, sleeper=sleeper)
        self.assertEqual(sender.calls, 4)
        self.assertEqual(sleeper.delays, [2, 4, 8])
        audit = caught.exception.attempt_audit
        self.assertEqual([r["outcome"] for r in audit],
                         ["http_429"] * 4)

    def test_5xx_bounded_retry_matrix(self):
        sender = FakeSender([(500, b""), (503, b""), (500, b"")])
        sleeper = RecordingSleeper()
        with self.assertRaises(transport.TransportError) as caught:
            run_dispatch(sender, sleeper=sleeper)
        self.assertNotIsInstance(caught.exception, transport.RateLimited)
        self.assertEqual(sender.calls, 3)
        self.assertEqual(sleeper.delays, [2, 4])

    def test_400_transport_error_one_call(self):
        sender = FakeSender([(400, b"bad")])
        sleeper = RecordingSleeper()
        with self.assertRaises(transport.TransportError):
            run_dispatch(sender, sleeper=sleeper)
        self.assertEqual(sender.calls, 1)
        self.assertEqual(sleeper.delays, [])

    def test_200_returns_raw_body_attempts_and_cost_status(self):
        sender = FakeSender([(200, b"\x89PNG-raw-body")])
        outcome = run_dispatch(sender)
        result = outcome.send_result
        self.assertEqual(result.status, 200)
        self.assertEqual(result.body, b"\x89PNG-raw-body")
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0].outcome, "ok")
        self.assertEqual(result.cost_status, "verified")
        # The sender saw exactly the payload the outcome reports, and
        # the payload was not mutated by the send.
        self.assertEqual(sender.requests_seen[0], outcome.payload)
        self.assertEqual(outcome.payload["model"], "agnes-image-2.5-flash")


class TimeoutAmbiguityTests(unittest.TestCase):
    def test_timeout_ambiguous_outcome_carries_fingerprint(self):
        sender = FakeSender([TimeoutError("timed out")])
        request = make_request()
        expected_payload = {
            "model": "agnes-image-2.5-flash",
            "prompt": request.prompt,
            "size": "2K",
        }
        expected_fingerprint = orch.request_fingerprint(expected_payload)
        with self.assertRaises(transport.AmbiguousOutcome) as caught:
            run_dispatch(sender, request=request)
        exc = caught.exception
        self.assertEqual(exc.request_fingerprint, expected_fingerprint)
        self.assertEqual(sender.calls, 1)  # no automatic second call
        self.assertEqual(len(exc.attempt_audit), 1)
        self.assertEqual(exc.attempt_audit[0]["outcome"], "timeout")
        self.assertEqual(exc.dispatch_run_record["terminal"],
                         "AmbiguousOutcome")


class FingerprintTests(unittest.TestCase):
    """G-10: the documented algorithm, stability and sensitivity."""

    def test_fingerprint_matches_documented_algorithm(self):
        payload = {"size": "2K", "prompt": "abc", "model": "m"}
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8")
        self.assertEqual(orch.request_fingerprint(payload),
                         hashlib.sha256(canonical).hexdigest())

    def test_fingerprint_stable_across_key_order(self):
        first = {"model": "m", "prompt": "p", "size": "2K",
                 "extra_body": {"b": 1, "a": 2}}
        second = {"extra_body": {"a": 2, "b": 1}, "size": "2K",
                  "prompt": "p", "model": "m"}
        self.assertEqual(orch.request_fingerprint(first),
                         orch.request_fingerprint(second))

    def test_fingerprint_changes_with_any_field(self):
        base = {"model": "m", "prompt": "p", "size": "2K"}
        changed = dict(base, size="3K")
        self.assertNotEqual(orch.request_fingerprint(base),
                            orch.request_fingerprint(changed))

    def test_fingerprint_threaded_to_record_and_outcome(self):
        sender = FakeSender([(200, b"img")])
        outcome = run_dispatch(sender)
        self.assertEqual(outcome.fingerprint,
                         orch.request_fingerprint(outcome.payload))
        self.assertEqual(outcome.run_record["fingerprint"],
                         outcome.fingerprint)


class HttpSenderContractTests(unittest.TestCase):
    """G-01: the concrete sender, driven only through a fake opener."""

    class FakeResponse:
        def __init__(self, status, body):
            self.status = status
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_sender_returns_status_and_body_and_injects_credential(self):
        captured = {}

        def opener(http_request, timeout=None):
            captured["request"] = http_request
            captured["timeout"] = timeout
            return self.FakeResponse(200, b"provider-body")

        sender = orch.make_http_sender(env=ENV_OK, opener=opener)
        payload = {"model": "agnes-image-2.5-flash", "prompt": "p",
                   "size": "2K"}
        before = copy.deepcopy(payload)
        status, body = sender(payload)
        self.assertEqual((status, body), (200, b"provider-body"))
        self.assertEqual(payload, before)  # request dict never mutated
        http_request = captured["request"]
        self.assertEqual(http_request.get_header("Authorization"),
                         f"Bearer {TEST_CREDENTIAL}")
        self.assertEqual(http_request.data,
                         orch.canonical_request_bytes(payload))
        # The credential is in no serialized form of the payload.
        self.assertNotIn(TEST_CREDENTIAL,
                         http_request.data.decode("utf-8"))

    def test_sender_returns_http_error_status_and_body(self):
        def opener(http_request, timeout=None):
            raise urllib.error.HTTPError(
                http_request.full_url, 429, "rate limited", {},
                io.BytesIO(b"slow down"))

        sender = orch.make_http_sender(env=ENV_OK, opener=opener)
        status, body = sender({"model": "m"})
        self.assertEqual((status, body), (429, b"slow down"))

    def test_sender_timeout_raises_timeout_error(self):
        def opener(http_request, timeout=None):
            raise urllib.error.URLError(TimeoutError("timed out"))

        sender = orch.make_http_sender(env=ENV_OK, opener=opener)
        with self.assertRaises(TimeoutError):
            sender({"model": "m"})

    def test_sender_network_failure_is_named_sender_error(self):
        def opener(http_request, timeout=None):
            raise urllib.error.URLError(
                ConnectionRefusedError("connection refused"))

        sender = orch.make_http_sender(env=ENV_OK, opener=opener)
        with self.assertRaises(orch.SenderNetworkError) as caught:
            sender({"model": "m"})
        self.assertEqual(caught.exception.kind, "network")

    def test_sender_missing_credential_fails_closed(self):
        sender = orch.make_http_sender(env=ENV_EMPTY,
                                       opener=lambda req, timeout=None: None)
        with self.assertRaises(transport.CredentialsMissing):
            sender({"model": "m"})

    def test_sender_rejects_non_https_endpoint_at_construction(self):
        with self.assertRaises(orch.SenderConstructionError) as caught:
            orch.make_http_sender(endpoint="http://example.invalid/x")
        self.assertEqual(caught.exception.kind, "construction")


class ExceptionPolicyTests(unittest.TestCase):
    """G-12 and G-08: fail closed, named in the record, no retry
    inference, and a credential-free audit."""

    def test_foreign_sender_exception_wrapped_fail_closed(self):
        sender = FakeSender([ValueError("boom")])
        with self.assertRaises(orch.SenderNetworkError) as caught:
            run_dispatch(sender)
        exc = caught.exception
        self.assertIsInstance(exc.__cause__, ValueError)
        self.assertEqual(sender.calls, 1)  # no retry was inferred
        record = exc.attempt_audit[0]
        self.assertEqual(record["outcome"], "exception")
        self.assertEqual(record["exception_kind"], "unclassified")
        self.assertEqual(record["exception_type"], "ValueError")
        self.assertEqual(exc.dispatch_run_record["terminal"],
                         "SenderNetworkError")

    def test_sender_error_propagates_unchanged(self):
        sender = FakeSender([orch.SenderConstructionError("bad build")])
        with self.assertRaises(orch.SenderConstructionError) as caught:
            run_dispatch(sender)
        self.assertEqual(sender.calls, 1)
        record = caught.exception.attempt_audit[0]
        self.assertEqual(record["exception_kind"], "construction")

    def test_audit_and_run_record_never_contain_credential(self):
        sender = FakeSender([(429, b"")] * 4)
        with self.assertRaises(transport.RateLimited) as caught:
            run_dispatch(sender)
        blob = json.dumps(caught.exception.attempt_audit) + \
            json.dumps(caught.exception.dispatch_run_record)
        self.assertNotIn(TEST_CREDENTIAL, blob)
        ok_sender = FakeSender([(200, b"img")])
        outcome = run_dispatch(ok_sender)
        blob = json.dumps(outcome.attempt_audit) + \
            json.dumps(outcome.run_record)
        self.assertNotIn(TEST_CREDENTIAL, blob)


class SequenceGateTests(unittest.TestCase):
    """The sequence stops before spend at each earlier gate."""

    def test_resolution_error_rejects_text_model_before_anything(self):
        sender = FakeSender([(200, b"img")])
        request = make_request(model_request="agnes-video-2.5-flash")
        with self.assertRaises(resolver.ResolutionError):
            run_dispatch(sender, request=request)
        self.assertEqual(sender.calls, 0)

    def test_invalid_policy_stops_before_spend(self):
        sender = FakeSender([(200, b"img")])
        hooks = make_hooks(elements=FULL_ELEMENTS - {"output"})
        with self.assertRaises(orch.PolicyRefused):
            run_dispatch(sender, hooks=hooks)
        self.assertEqual(sender.calls, 0)

    def test_named_policy_mismatch_stops_before_spend(self):
        sender = FakeSender([(200, b"img")])
        request = make_request(named_policy_id="legacy_house_band")
        with self.assertRaises(orch.PolicyRefused):
            run_dispatch(sender, request=request)
        self.assertEqual(sender.calls, 0)

    def test_payload_gate_stops_before_spend(self):
        sender = FakeSender([(200, b"img")])
        request = make_request(size="5K")
        with self.assertRaises(orch.PayloadRefused):
            run_dispatch(sender, request=request)
        self.assertEqual(sender.calls, 0)

    def test_ratio_hook_failure_stops_before_spend(self):
        sender = FakeSender([(200, b"img")])
        hooks = orch.GateHooks(
            evaluate_policy=make_hooks().evaluate_policy,
            check_ratios=lambda ctx: ["ratio 5:4 disagrees by name"])
        with self.assertRaises(orch.PayloadRefused):
            run_dispatch(sender, hooks=hooks)
        self.assertEqual(sender.calls, 0)

    def test_stored_config_handoff_point(self):
        sender = FakeSender([(200, b"img")])
        request = make_request(stored=True,
                               stored_provenance="generated_default",
                               model_request="agnes-image-2.1-flash")
        outcome = run_dispatch(sender, request=request)
        self.assertEqual(outcome.resolution.model_id,
                         "agnes-image-2.5-flash")
        self.assertEqual(outcome.resolution.provenance, "default")
        self.assertEqual(outcome.payload["model"],
                         "agnes-image-2.5-flash")


if __name__ == "__main__":
    unittest.main()
