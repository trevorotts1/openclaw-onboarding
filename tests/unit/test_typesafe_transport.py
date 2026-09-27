#!/usr/bin/env python3
"""D04 TypeSafe direct-transport tests (JEV spec 1.1, 3.2/3.4/3.7).

Proves, against the REAL providers/typesafe_direct.py (no reimplemented
logic, no network — every HTTP path injects a fake ``http_post``):
  * pinned contract: endpoint, ``jev-1.13.0``, decisions-only body
    (``model``/``state``/``typed questions``; never ``messages``,
    ``temperature`` or tool keys);
  * credential routing by VALUE lookup, never key-name-only:
    ``TYPESAFE_API_KEY`` preferred over ``JEV_API_KEY`` alias, placeholders
    and references rejected before any call, key material never in outputs;
  * strict normalization: valid select/score/noul accepted; malformed,
    non-finite, missing-answer, wrong-candidate, out-of-bounds,
    wrong-type, incomplete keys, unit-sum failure rejected with diagnostics;
    unknown metadata preserved; no ``confidence`` synthesized;
  * 3.4 outcomes: auth_rejected/rate_limited/overloaded/network/timeout/
    integration_defect/not_configured, one attempt per call, low-confidence
    a warning (callable result) rather than a second-endpoint trigger.

Run: python3 tests/unit/test_typesafe_transport.py
 or: pytest tests/unit/test_typesafe_transport.py -q
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_DE = _SHARED / "decision_engine"
sys.path.insert(0, str(_SHARED))

_spec = importlib.util.spec_from_file_location(
    "decision_engine_providers_typesafe_direct",
    _DE / "providers" / "typesafe_direct.py")
ts = importlib.util.module_from_spec(_spec)
sys.modules["decision_engine_providers_typesafe_direct"] = ts
_spec.loader.exec_module(ts)


# High-entropy fixture secrets: must pass secret_helper.looks_like_real_key
# (REALISH shape + 3.0 bits/char entropy); low-entropy strings read absent.
_TS_KEY_A = "tsTestKey9Qm4Zx7Vb2Nw8Ld5"
_TS_KEY_B = "jevAliasKey3Kp8Rn5Tu2Wx6"


def _select_specs():
    return {"q1": {"type": "select",
                   "candidates": ["a", "b"],
                   "prob_keys": ["a", "b"]}}


def _good_select_payload(top=0.7):
    return {"model": ts.TYPESAFE_MODEL, "judgments": [{
        "question_id": "q1", "type": "select", "answer": "a",
        "probabilities": {"a": top, "b": 1.0 - top}}]}


def _sender(status=200, payload=None, record=None, exc=None):
    def fake(url, body, headers, timeout):
        assert url == ts.TYPESAFE_ENDPOINT, f"wrong endpoint: {url}"
        assert headers.get("Authorization", "").startswith("Bearer "), \
            "bearer auth required"
        assert headers.get("Content-Type") == "application/json", \
            "json content type required"
        parsed = json.loads(body.decode("utf-8"))
        assert set(parsed) == {"model", "state", "questions"}, \
            f"decisions-only body, got {sorted(parsed)}"
        if record is not None:
            record.append((url, headers, parsed))
        if exc is not None:
            raise exc
        return status, payload
    return fake


class PinnedContract(unittest.TestCase):
    def test_endpoint_and_model_pinned(self):
        self.assertEqual(ts.TYPESAFE_ENDPOINT,
                         "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(ts.TYPESAFE_MODEL, "jev-1.13.0")

    def test_build_request_exact_keys(self):
        body = ts.build_request({"s": 1},
                                [{"id": "q1", "type": "select"}])
        self.assertEqual(set(body), {"model", "state", "questions"})
        self.assertEqual(body["model"], "jev-1.13.0")
        self.assertEqual(ts.check_body_clean(body), [])

    def test_build_request_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):
            ts.build_request({}, [{"id": "q", "type": "select"},
                                  {"id": "q", "type": "select"}])

    def test_forbidden_chat_keys_flagged(self):
        body = ts.build_request({"s": 1}, [{"id": "q", "type": "select"}])
        for key in ("messages", "temperature", "reasoning_effort",
                    "tools", "tool_calls"):
            dirty = dict(body, **{key: object()})
            self.assertTrue(
                any("forbidden" in v for v in ts.check_body_clean(dirty)),
                f"{key} must be rejected")

    def test_no_network_or_environ_at_import(self):
        import os
        before = dict(os.environ)
        fresh = importlib.util.spec_from_file_location(
            "ts_reimport_check", _DE / "providers" / "typesafe_direct.py")
        mod = importlib.util.module_from_spec(fresh)
        fresh.loader.exec_module(mod)
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(mod.TYPESAFE_ENDPOINT, ts.TYPESAFE_ENDPOINT)
        src = (_DE / "providers" / "typesafe_direct.py").read_text(
            encoding="utf-8")
        self.assertNotIn("import socket", src)

    def test_key_names_documented(self):
        self.assertEqual(ts.DIRECT_KEY_PRIMARY, "TYPESAFE_API_KEY")
        self.assertEqual(ts.DIRECT_KEY_ALIAS, "JEV_API_KEY")
        self.assertEqual(ts.DIRECT_KEY_NAMES[0], "TYPESAFE_API_KEY")

    def test_model_snapshot_family(self):
        self.assertTrue(ts.is_approved_model("jev-1.13.0"))
        self.assertTrue(ts.is_approved_model("jev-1.13.0.20260901"))
        self.assertFalse(ts.is_approved_model("jev-2.0.0"))
        self.assertFalse(ts.is_approved_model("other-model"))
        self.assertFalse(ts.is_approved_model(None))


class CredentialRouting(unittest.TestCase):
    def test_primary_wins_over_alias(self):
        r = ts.resolve_direct_key({"TYPESAFE_API_KEY": _TS_KEY_A,
                                   "JEV_API_KEY": _TS_KEY_B})
        self.assertEqual(r["state"], "configured")
        self.assertEqual(r["key_name"], "TYPESAFE_API_KEY")
        self.assertEqual(r["value"], _TS_KEY_A)

    def test_alias_used_when_primary_absent(self):
        r = ts.resolve_direct_key({"JEV_API_KEY": _TS_KEY_B})
        self.assertEqual((r["state"], r["key_name"]),
                         ("configured", "JEV_API_KEY"))

    def test_value_lookup_not_key_name_only(self):
        # A present-but-garbage primary must NOT win over a usable alias.
        r = ts.resolve_direct_key({"TYPESAFE_API_KEY": "PASTE_REAL_TOKEN",
                                   "JEV_API_KEY": _TS_KEY_B})
        self.assertEqual((r["state"], r["key_name"]),
                         ("configured", "JEV_API_KEY"))

    def test_placeholders_rejected_before_call(self):
        for junk in ("", "   ", "PASTE_REAL_TOKEN", "${TYPESAFE_API_KEY}",
                     "$TYPESAFE_API_KEY", "ref:vault/key", "short"):
            r = ts.resolve_direct_key({"TYPESAFE_API_KEY": junk})
            self.assertEqual(r["state"], "absent", repr(junk))
            out = ts.post_decisions(
                ts.build_request({}, [{"id": "q1", "type": "select"}]),
                api_key=junk, http_post=_sender())
            self.assertEqual(out["outcome"], "not_configured", repr(junk))

    def test_absent_key_never_calls_http(self):
        calls = []
        out = ts.post_decisions(
            ts.build_request({}, [{"id": "q1", "type": "select"}]),
            api_key="", http_post=_sender(record=calls))
        self.assertEqual(out["outcome"], "not_configured")
        self.assertEqual(calls, [])

    def test_key_material_never_in_result(self):
        secret = _TS_KEY_A
        out = ts.post_decisions(
            ts.build_request({}, [{"id": "q1", "type": "select"}]),
            api_key=secret, http_post=_sender(200, _good_select_payload()))
        self.assertNotIn(secret, json.dumps(out))
        self.assertEqual(out["outcome"], "ok")

    def test_availability_configured_not_verified(self):
        a = ts.describe_availability({"TYPESAFE_API_KEY": _TS_KEY_A})
        self.assertEqual((a["state"], a["verified"]),
                         ("configured", False))
        a = ts.describe_availability({})
        self.assertEqual((a["state"], a["verified"]), ("absent", False))


class StrictNormalization(unittest.TestCase):
    def test_valid_select_score_noul(self):
        ok, judgments, diags = ts.normalize_response(
            _good_select_payload(), _select_specs())
        self.assertTrue(ok)
        self.assertEqual(judgments[0]["answer"], "a")
        ok, _, _ = ts.normalize_response(
            {"judgments": [{"question_id": "q2", "type": "score",
                            "value": 3}]},
            {"q2": {"type": "score", "levels": [1, 2, 3, 4, 5]}})
        self.assertTrue(ok)
        ok, judgments, _ = ts.normalize_response(
            {"judgments": [{"question_id": "q3", "type": "noul",
                            "probability": 0.42}]},
            {"q3": {"type": "noul"}})
        self.assertTrue(ok)
        self.assertEqual(judgments[0]["probability"], 0.42)

    def test_malformed_payload(self):
        for bad in (None, [], "x", {"nope": 1},
                    {"judgments": "x"}, {"judgments": []}):
            ok, judgments, diags = ts.normalize_response(bad, _select_specs())
            self.assertFalse(ok)
            self.assertIsNone(judgments)
            self.assertTrue(diags)

    def test_missing_answer_wrong_type(self):
        ok, _, diags = ts.normalize_response({"judgments": []},
                                             _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "missing_answer")
        ok, _, diags = ts.normalize_response(
            {"judgments": [{"question_id": "q1", "type": "score",
                            "value": 1}]}, _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "type_mismatch")

    def test_wrong_candidate_rejected(self):
        ok, _, diags = ts.normalize_response(
            {"judgments": [{"question_id": "q1", "type": "select",
                            "answer": "zzz",
                            "probabilities": {"a": 0.5, "b": 0.5}}]},
            _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "wrong_candidate")

    def test_nonfinite_rejected(self):
        ok, _, diags = ts.normalize_response(
            {"judgments": [{"question_id": "q1", "type": "select",
                            "answer": "a",
                            "probabilities": {"a": math.nan, "b": 0.5}}]},
            _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "nonfinite")

    def test_out_of_bounds_and_incomplete_keys(self):
        ok, _, diags = ts.normalize_response(
            {"judgments": [{"question_id": "q1", "type": "select",
                            "answer": "a",
                            "probabilities": {"a": 1.5, "b": -0.5}}]},
            _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "out_of_bounds")
        ok, _, diags = ts.normalize_response(
            {"judgments": [{"question_id": "q1", "type": "select",
                            "answer": "a", "probabilities": {"a": 1.0}}]},
            _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "incomplete_prob_keys")

    def test_unit_sum_boundary(self):
        def payload(top):
            return {"judgments": [{
                "question_id": "q1", "type": "select", "answer": "a",
                "probabilities": {"a": top, "b": 1.0 - top}}]}
        ok, _, _ = ts.normalize_response(payload(0.7), _select_specs())
        self.assertTrue(ok)
        ok, _, diags = ts.normalize_response(payload(0.6), _select_specs(),
                                             min_top_prob=0.99)
        self.assertTrue(ok)  # low confidence warns, still valid
        self.assertEqual(diags[-1]["code"], "low_confidence")
        drifted = {"judgments": [{
            "question_id": "q1", "type": "select", "answer": "a",
            "probabilities": {"a": 0.6, "b": 0.3000001}}]}
        ok, _, diags = ts.normalize_response(drifted, _select_specs())
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "unit_sum_fail")

    def test_unit_sum_tolerance_documented(self):
        self.assertEqual(ts.UNIT_SUM_TOLERANCE, 1e-6)

    def test_score_uses_caller_levels_not_0_10(self):
        ok, _, _ = ts.normalize_response(
            {"judgments": [{"question_id": "q2", "type": "score",
                            "value": 11}]},
            {"q2": {"type": "score", "levels": [7, 9, 11]}})
        self.assertTrue(ok)
        ok, _, diags = ts.normalize_response(
            {"judgments": [{"question_id": "q2", "type": "score",
                            "value": 10}]},
            {"q2": {"type": "score", "levels": [7, 9, 11]}})
        self.assertFalse(ok)
        self.assertEqual(diags[0]["code"], "out_of_levels")

    def test_no_confidence_synthesized_metadata_preserved(self):
        payload = dict(_good_select_payload(), extra={"note": "keep"},
                       vendor="typesafe")
        ok, judgments, _ = ts.normalize_response(payload, _select_specs())
        self.assertTrue(ok)
        self.assertNotIn("confidence", judgments[0])
        self.assertEqual(payload["extra"], {"note": "keep"})
        self.assertEqual(payload["vendor"], "typesafe")

    def test_never_raises_on_bad_input(self):
        for bad in (None, 42, {"judgments": [{"question_id": 7}]},
                    {"judgments": [{"question_id": "q1"}]}):
            ts.normalize_response(bad, _select_specs())  # must not raise
            ts.normalize_response(_good_select_payload(), bad if isinstance(
                bad, dict) else "x")  # must not raise


class TransportOutcomes(unittest.TestCase):
    def _body(self):
        return ts.build_request({"s": 1}, [{"id": "q1", "type": "select"}])

    def test_ok_records_model_snapshot(self):
        out = ts.post_decisions(
            self._body(), api_key=_TS_KEY_A,
            http_post=_sender(200, {"model": "jev-1.13.0.20260901",
                                    "judgments": []}))
        self.assertEqual(out["outcome"], "ok")
        self.assertEqual(out["model_snapshot"], "jev-1.13.0.20260901")

    def test_status_table(self):
        cases = {401: "auth_rejected", 422: "integration_defect",
                 429: "rate_limited", 529: "overloaded",
                 500: "overloaded", 400: "integration_defect"}
        for status, outcome in cases.items():
            out = ts.post_decisions(self._body(), api_key=_TS_KEY_A,
                                    http_post=_sender(status, None))
            self.assertEqual(out["outcome"], outcome, str(status))
            self.assertEqual(out["status"], status)

    def test_network_and_timeout(self):
        out = ts.post_decisions(self._body(), api_key=_TS_KEY_A,
                                http_post=_sender(exc=OSError("down")))
        self.assertEqual(out["outcome"], "network_error")
        out = ts.post_decisions(self._body(), api_key=_TS_KEY_A,
                                http_post=_sender(exc=TimeoutError()))
        self.assertEqual(out["outcome"], "timeout")

    def test_integration_defect_on_dirty_body(self):
        body = self._body()
        body["temperature"] = 0.7
        calls = []
        out = ts.post_decisions(body, api_key=_TS_KEY_A,
                                http_post=_sender(record=calls))
        self.assertEqual(out["outcome"], "integration_defect")
        self.assertEqual(calls, [])  # never sent

    def test_single_attempt_per_call(self):
        calls = []
        ts.post_decisions(self._body(), api_key=_TS_KEY_A,
                          http_post=_sender(200, _good_select_payload(),
                                            record=calls))
        self.assertEqual(len(calls), 1)

    def test_invalid_200_is_invalid_response(self):
        out = ts.post_decisions(self._body(), api_key=_TS_KEY_A,
                                http_post=_sender(200, None))
        self.assertEqual(out["outcome"], "invalid_response")


class PackingBounds(unittest.TestCase):
    def test_target_and_hard_limits(self):
        self.assertEqual(ts.PACKING_TARGET_TOKENS, 24000)
        self.assertEqual(ts.DIRECT_HARD_LIMIT_STATE_ALL, 64000)
        self.assertEqual(ts.DIRECT_HARD_LIMIT_STATE_LONGEST, 32000)
        self.assertEqual(ts.MAX_REPACKS, 1)

    def test_estimator_counts_everything(self):
        small = ts.request_estimate_tokens({"s": "x"}, [{"id": "q"}])
        big = ts.request_estimate_tokens(
            {"s": "x"}, [{"id": "q"}], instructions="rubric " * 500)
        self.assertGreater(big, small)

    def test_verdict_and_batches(self):
        v = ts.packing_verdict({"s": "x"}, [{"id": "q", "type": "select"}])
        self.assertEqual(v["estimator"], ts.ESTIMATOR_LABEL)
        self.assertTrue(v["fits_target"] and v["fits_hard"])
        self.assertEqual(v["max_repacks"], 1)
        qs = [{"id": f"q{i}", "type": "select", "pad": "x" * 40000}
              for i in range(3)]
        batches = ts.batch_questions(qs, {"s": "y"})
        self.assertGreaterEqual(len(batches), 2)
        self.assertEqual(sum(map(len, batches)), 3)


if __name__ == "__main__":
    unittest.main()
