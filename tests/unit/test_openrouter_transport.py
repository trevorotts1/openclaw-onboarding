#!/usr/bin/env python3
"""D05 OpenRouter transport tests (JEV spec 1.1, ss 3.2/3.4/3.7).

Proves, against the REAL providers/openrouter_decisions.py implementation:
  * request packs {model,state,questions} with model typesafe/jev-1.13,
    no chat-completions keys, bearer key, correct endpoint;
  * strict normalization: required question IDs, choice/score/distribution
    types, candidate allow-list, probability keys exact, bounds, unit-sum
    within tolerance, finite numerics; extra metadata preserved;
  * returned snapshot: snapshot-in-family accepted, snapshot-foreign
    rejected;
  * error mapping: 401/403 auth_rejected, 422 request_defect, 429
    retry_later, 500/503/529 overload; missing/placeholder key ->
    missing_key without a call; invalid body -> caller-fallback classes;
  * single attempt per call (bounded retry is caller-owned); offline:
    every test uses injected transports (network denial by construction).

Run: pytest tests/unit/test_openrouter_transport.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_DE = _SHARED / "decision_engine"

sys.path.insert(0, str(_SHARED))

_loader = importlib.util.spec_from_file_location(
    "decision_engine_openrouter",
    _DE / "providers" / "openrouter_decisions.py",
)
mod = importlib.util.module_from_spec(_loader)
sys.modules["decision_engine_openrouter"] = mod
_loader.loader.exec_module(mod)


def _expected(cands):
    return [
        {
            "question_id": "q_intent",
            "answer": "choice",
            "choices": ["answer_only", "task_request"],
        },
        {"question_id": "q_score", "answer": "score", "levels": 3},
        {
            "question_id": "q_candidate_dist",
            "answer": "distribution",
            "candidates": cands,
        },
    ]


def _good_body(cands=("cand-a", "cand-b"), model="typesafe/jev-1.13"):
    return {
        "model": model,
        "judgments": [
            {"question_id": "q_intent", "answer": "task_request"},
            {"question_id": "q_score", "level": 2},
            {
                "question_id": "q_candidate_dist",
                "probabilities": {"cand-a": 0.6, "cand-b": 0.4},
            },
        ],
    }


class OpenRouterContract(unittest.TestCase):
    def test_constants_endpoint_model_keyname(self):
        self.assertEqual(
            mod.ENDPOINT, "https://openrouter.ai/api/alpha/decisions"
        )
        self.assertEqual(mod.REQUESTED_MODEL, "typesafe/jev-1.13")
        self.assertEqual(mod.API_KEY_NAME, "OPENROUTER_API_KEY")

    def test_body_has_no_chat_keys(self):
        body = mod.build_request({"text": "hi"}, [{"question_id": "q1"}])
        self.assertEqual(
            sorted(body.keys()), ["model", "questions", "state"]
        )
        self.assertEqual(body["model"], "typesafe/jev-1.13")
        for key in mod.FORBIDDEN_BODY_KEYS:
            self.assertNotIn(key, body)

    def test_valid_response_normalizes_and_preserves_extra(self):
        body = dict(_good_body())
        body["x_provider_meta"] = {"trace": "abc"}
        ok, errs, norm = mod.validate_response(
            body, _expected(["cand-a", "cand-b"])
        )
        self.assertTrue(ok, errs)
        self.assertEqual(norm["model_returned"], "typesafe/jev-1.13")
        self.assertEqual(norm["x_provider_meta"], {"trace": "abc"})

    def test_missing_question_id_rejected(self):
        body = _good_body()
        body["judgments"] = [j for j in body["judgments"] if j["question_id"] != "q_score"]
        ok, errs, _ = mod.validate_response(body, _expected(["cand-a", "cand-b"]))
        self.assertFalse(ok)
        self.assertTrue(any("q_score" in e for e in errs), errs)

    def test_wrong_type_and_unknown_candidate_rejected(self):
        body = _good_body()
        body["judgments"][0]["answer"] = "bogus_intent"
        body["judgments"][2]["probabilities"] = {"cand-a": 0.5, "intruder": 0.5}
        ok, errs, _ = mod.validate_response(body, _expected(["cand-a", "cand-b"]))
        self.assertFalse(ok)
        self.assertTrue(any("not in" in e for e in errs), errs)
        self.assertTrue(
            any("cand-b" in e or "intruder" in e for e in errs), errs
        )

    def test_incomplete_distribution_keys_and_bounds_rejected(self):
        cands = ["cand-a", "cand-b", "cand-c"]
        body = {
            "model": "typesafe/jev-1.13",
            "judgments": [
                {"question_id": "q_intent", "answer": "task_request"},
                {"question_id": "q_score", "level": 9},
                {
                    "question_id": "q_candidate_dist",
                    "probabilities": {"cand-a": 0.9, "cand-b": 0.1},
                },
            ],
        }
        ok, errs, _ = mod.validate_response(body, _expected(cands))
        self.assertFalse(ok)
        self.assertTrue(any("cand-c" in e or "keys" in e for e in errs), errs)
        self.assertTrue(any("bounds" in e or "[0, 3)" in e for e in errs), errs)

    def test_probability_sum_and_nonfinite_rejected(self):
        body = _good_body()
        body["judgments"][2]["probabilities"] = {"cand-a": 0.6, "cand-b": 0.5}
        ok, errs, _ = mod.validate_response(body, _expected(["cand-a", "cand-b"]))
        self.assertFalse(ok)
        self.assertTrue(any("sum" in e for e in errs), errs)
        body2 = _good_body()
        body2["judgments"][2]["probabilities"] = {"cand-a": float("nan"), "cand-b": 0.5}
        ok2, errs2, _ = mod.validate_response(body2, _expected(["cand-a", "cand-b"]))
        self.assertFalse(ok2)
        self.assertTrue(
            any("non-finite" in e or "finite" in e for e in errs2), errs2
        )

    def test_validator_never_raises(self):
        for bad in (None, "x", 42, [], {"model": "m"}, {"judgments": "nope"}):
            ok, errs, _ = mod.validate_response(bad, _expected(["cand-a"]))
            self.assertFalse(ok)
            self.assertTrue(errs)

    def test_snapshot_in_family_accepted_foreign_rejected(self):
        for snap in (
            "typesafe/jev-1.13",
            "typesafe/jev-1.13-20260901",
            "typesafe/jev-1.13:dated",
        ):
            self.assertTrue(mod.model_in_family(snap), snap)
        for snap in (
            "",
            "typesafe/jev-1.12",
            "typesafe/jev-1.130",
            "typesafe/jev-2.0",
            "openai/gpt-4",
            None,
            42,
        ):
            self.assertFalse(mod.model_in_family(snap), repr(snap))
        ok, _, _ = mod.validate_response(
            _good_body(model="typesafe/jev-1.13-20260901"), [],
        )
        self.assertTrue(ok)
        ok_f, errs_f, _ = mod.validate_response(
            _good_body(model="other/model-9"), [],
        )
        self.assertFalse(ok_f)
        self.assertTrue(any("snapshot-foreign" in e for e in errs_f), errs_f)

    def test_status_mapping(self):
        cases = {
            200: "ok",
            401: "auth_rejected",
            403: "auth_rejected",
            422: "request_defect",
            429: "retry_later",
            500: "overload",
            503: "overload",
            529: "overload",
            418: "transport_error",
        }
        for status, want in cases.items():
            self.assertEqual(mod.classify_status(status), want, status)
        self.assertEqual(mod.classify_status(None), "transport_error")

    def test_missing_key_makes_no_call(self):
        calls = []
        outcome, detail = mod.send_decisions(
            {"text": "hi"},
            [{"question_id": "q_intent"}],
            _expected(["cand-a", "cand-b"]),
            api_key=None,
            env={},
            allowed_candidates=["cand-a", "cand-b"],
            transport=lambda *a: (calls.append(a), (200, _good_body()))[1],
        )
        self.assertEqual(outcome, "missing_key")
        self.assertEqual(calls, [])
        outcome2, _ = mod.send_decisions(
            {"t": "x"},
            [],
            [],
            api_key="PASTE_REAL_TOKEN",
            env={},
            transport=lambda *a: (200, {}),
        )
        self.assertEqual(outcome2, "missing_key")

    def test_429_and_500_map_without_retry(self):
        for status, want in ((429, "retry_later"), (500, "overload")):
            calls = []

            def _t(url, headers, payload, _s=status):
                calls.append((url, headers))
                return _s, {}

            outcome, detail = mod.send_decisions(
                {"t": "x"},
                [],
                [],
                api_key="k-real-enough",
                allowed_candidates=[],
                transport=_t,
            )
            self.assertEqual(outcome, want, status)
            self.assertEqual(len(calls), 1)  # single attempt; caller owns backoff
            self.assertEqual(detail["status"], status)

    def test_auth_header_and_endpoint_used(self):
        seen = {}

        def _t(url, headers, payload):
            seen["url"] = url
            seen["headers"] = headers
            seen["payload"] = json.loads(payload.decode("utf-8"))
            return 200, _good_body()

        outcome, norm = mod.send_decisions(
            {"text": "hi"},
            [{"question_id": "q1"}],
            _expected(["cand-a", "cand-b"]),
            api_key="k-real-enough",
            allowed_candidates=["cand-a", "cand-b"],
            transport=_t,
        )
        self.assertEqual(outcome, "ok", norm)
        self.assertEqual(seen["url"], "https://openrouter.ai/api/alpha/decisions")
        self.assertTrue(
            seen["headers"]["Authorization"].startswith("Bearer "),
            seen["headers"],
        )
        self.assertNotIn("k-real-enough"[3:], json.dumps(seen["payload"]))
        self.assertEqual(seen["payload"]["model"], "typesafe/jev-1.13")

    def test_model_foreign_and_invalid_classes(self):
        bad = _good_body(model="other/model-9")
        outcome, _ = mod.send_decisions(
            {},
            [],
            [],
            api_key="k-real-enough",
            transport=lambda *a: (200, bad),
        )
        self.assertEqual(outcome, "model_foreign")
        broken = {"model": "typesafe/jev-1.13", "judgments": [{"nope": 1}]}
        outcome2, detail2 = mod.send_decisions(
            {},
            [{"question_id": "q_missing"}],
            [{"question_id": "q_missing", "answer": "choice", "choices": ["a"]}],
            api_key="k-real-enough",
            transport=lambda *a: (200, broken),
        )
        self.assertEqual(outcome2, "invalid_judgment")
        self.assertTrue(detail2["errors"])

    def test_resolve_key_rejects_placeholders(self):
        key, src = mod.resolve_key("PASTE_REAL_TOKEN", {"OPENROUTER_API_KEY": "sk-real"})
        self.assertEqual((key, src), ("sk-real", "env"))
        key2, src2 = mod.resolve_key(None, {"OPENROUTER_API_KEY": "  "})
        self.assertEqual((key2, src2), (None, "missing"))

    def test_over_budget_short_circuits(self):
        big = {"text": "x" * (mod.PACK_TOKEN_TARGET * 4 + 100)}
        outcome, detail = mod.send_decisions(
            big,
            [{"question_id": "q"}],
            [],
            api_key="k-real-enough",
            transport=lambda *a: (200, _good_body()),
        )
        self.assertEqual(outcome, "over_budget")
        self.assertTrue(detail["errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
