#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_agnes_dispatch_e2e.py -- end-to-end tests for the assembled
A24 Leg 4 dispatch layer (agnes_dispatch.py wiring agnes_orchestrator,
agnes_gates, and agnes_response together).

Each test runs a full dispatch through all three layers with a fake
sender and a recording fake sleeper, offline:

(a) the 200 path: a synthetic provider body carrying a tiny real PNG
    produces a persisted output and a validated Agnes receipt, with
    the evaluated policy citation threaded explicitly (task_id null)
    and the governing registry citation resolved into the run's
    dispatch metadata;
(b) the ambiguous path: a first dispatch completes and stores its
    result; a second dispatch of the same request, whose sender
    times out, resolves through the fingerprint-keyed result store
    with no resubmission send after the ambiguity;
(c) a deliberately introduced ratio disagreement between the
    models.json authority and the adapter validator stops the
    dispatch closed by name before the sender is ever called;
(d) the G-15 check: a plain-http reference URL in extra_body.image
    is refused by name before any send, and a public HTTPS
    reference URL passes through the composed path.

Run: python3 -m unittest test_agnes_dispatch_e2e (from this directory)
or:  python3 test_agnes_dispatch_e2e.py
"""
from __future__ import annotations

import base64
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agnes_dispatch as ad
import agnes_orchestrator as orch
import agnes_response as resp
import transport
import validate_payload


def make_png(width: int, height: int) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + typ + data
            + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scan = b"".join(b"\x00" + b"\x00" * (width * 3) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scan))
        + chunk(b"IEND", b"")
    )


PNG_7X5 = make_png(7, 5)
MODEL = "agnes-image-2.5-flash"
PROMPT = "a lighthouse on a granite point at dawn, editorial photo"
ALL_ELEMENTS = ["subject", "environment", "style", "lighting",
                "composition", "output"]
ENV = {"AGNES_AI_API_KEY": "e2e-dummy-key-not-a-credential"}
GOVERNING_ENTRY_HASH = (
    "ace1998862604904b5e2e224c0f85c87daf1ea07b74d2b60608589a4631e0532")


def provider_body(image_bytes: bytes, *, model=MODEL,
                  request_id="req-e2e-1") -> bytes:
    doc = {
        "id": request_id,
        "model": model,
        "data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii"),
                  "url": None}],
    }
    return json.dumps(doc).encode("utf-8")


def make_request(**overrides) -> orch.DispatchRequest:
    fields = dict(
        prompt=PROMPT,
        size="2K",
        ratio="16:9",
        budget=transport.Budget(approved_remaining_usd=10.0,
                                 allow_unverified_cost=False),
        estimated_cost_usd=0.5,
    )
    fields.update(overrides)
    return orch.DispatchRequest(**fields)


class StaticSender:
    """Returns the same (status, body) for every invocation."""

    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body
        self.calls = 0

    def __call__(self, request: dict):
        self.calls += 1
        return self.status, self.body


class TimeoutSender:
    """Raises TimeoutError on every invocation, as a timed-out
    provider attempt does."""

    def __init__(self):
        self.calls = 0

    def __call__(self, request: dict):
        self.calls += 1
        raise TimeoutError("provider attempt timed out (fake)")


class RecordingSleeper:
    def __init__(self):
        self.delays: list = []

    def __call__(self, seconds):
        self.delays.append(seconds)


class AssembledDispatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)
        self.output_path = self.run_dir / "out.png"

    def run_ok(self, request, sender):
        return ad.run_dispatch(
            request,
            elements_present=ALL_ELEMENTS,
            output_path=self.output_path,
            run_dir=self.run_dir,
            sender=sender,
            env=ENV,
            sleeper=RecordingSleeper(),
        )

    # (a) The 200 path, all three layers, to a validated receipt.
    def test_200_path_receipt_with_threaded_citation(self):
        sender = StaticSender(200, provider_body(PNG_7X5))
        result = self.run_ok(make_request(), sender)

        self.assertEqual(sender.calls, 1)
        self.assertIsNotNone(result.response)
        self.assertIsNone(result.ambiguous)

        receipt = result.response["receipt"]
        self.assertIsNone(receipt["task_id"])
        self.assertEqual(receipt["prompt_policy_id"],
                         "signature_launch_completeness")
        resp.validate_receipt(receipt)  # raises if invalid
        self.assertEqual(result.response["dimensions"], "7x5")
        self.assertEqual(result.response["actual_model_status"],
                         "confirmed_equal")
        persisted = Path(result.response["output_path"])
        self.assertEqual(persisted.read_bytes(), PNG_7X5)

        # G-03 end to end: the governing citation resolved against
        # the registry of record is retained in the one run record.
        meta = result.run_record["dispatch_metadata"]
        self.assertEqual(meta["governing_citation"]["policy_id"],
                         "kie-rule-12-band")
        self.assertEqual(meta["governing_citation"]["entry_hash"],
                         GOVERNING_ENTRY_HASH)
        # Wiring item 5: one record carries resolution (with
        # provenance), policy, fingerprint, cost status, attempts.
        self.assertEqual(meta["resolution"]["model_id"], MODEL)
        self.assertEqual(meta["resolution"]["provenance"], "default")
        self.assertEqual(meta["fingerprint"],
                         result.outcome.fingerprint)
        self.assertEqual(meta["cost_status"],
                         result.outcome.cost_status)
        self.assertEqual(result.run_record["fingerprint"],
                         result.outcome.fingerprint)
        self.assertEqual(len(result.run_record["attempts"]), 1)
        self.assertEqual(result.run_record["attempts"][0]["outcome"],
                         "http_200")
        self.assertTrue(
            any(e["event"] == "result_persisted_and_receipted"
                for e in result.run_record["response_events"]))

        # G-13: the completed result is in the run's result store.
        entry = resp.check_existing_result(self.run_dir,
                                           result.outcome.fingerprint)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["receipt"]["result_sha256"],
                         receipt["result_sha256"])

    # (b) The ambiguous path resolving through the result store.
    def test_ambiguous_path_resolves_from_store_no_resend(self):
        first_sender = StaticSender(200, provider_body(PNG_7X5))
        first = self.run_ok(make_request(), first_sender)
        fingerprint = first.outcome.fingerprint
        first_receipt_sha = first.response["receipt"]["result_sha256"]

        timeout_sender = TimeoutSender()
        second = ad.run_dispatch(
            make_request(),
            elements_present=ALL_ELEMENTS,
            output_path=self.run_dir / "out-second.png",
            run_dir=self.run_dir,
            sender=timeout_sender,
            env=ENV,
            sleeper=RecordingSleeper(),
        )

        self.assertIsNone(second.response)
        self.assertIsNotNone(second.ambiguous)
        self.assertEqual(second.ambiguous["outcome"], "existing_result")
        self.assertEqual(second.ambiguous["fingerprint"], fingerprint)
        self.assertEqual(second.ambiguous["resubmission"], "not_performed")
        self.assertEqual(
            second.ambiguous["entry"]["receipt"]["result_sha256"],
            first_receipt_sha)
        # The only send of the second dispatch is the single
        # timed-out attempt itself: after AmbiguousOutcome the
        # composed layer consults the store and never resubmits.
        self.assertEqual(timeout_sender.calls, 1)
        self.assertEqual(second.run_record["dispatch_metadata"]
                         ["fingerprint"], fingerprint)

    # (c) A ratio disagreement stops the dispatch before the sender.
    def test_ratio_disagreement_stops_before_sender(self):
        patched = set(validate_payload.RATIOS) - {"21:9"}
        original = validate_payload.RATIOS
        validate_payload.RATIOS = patched
        self.addCleanup(setattr, validate_payload, "RATIOS", original)

        sender = StaticSender(200, provider_body(PNG_7X5))
        with self.assertRaises(orch.PayloadRefused) as caught:
            self.run_ok(make_request(), sender)
        self.assertEqual(sender.calls, 0)
        named = " ".join(caught.exception.errors)
        self.assertIn("21:9", named)
        self.assertIn(MODEL, named)

    # (d) G-15 through the composed path.
    def test_http_reference_url_refused_before_send(self):
        sender = StaticSender(200, provider_body(PNG_7X5))
        request = make_request(
            extra_body={"image": ["http://example.com/ref.png"]})
        with self.assertRaises(resp.ReferenceUrlError) as caught:
            self.run_ok(request, sender)
        self.assertEqual(sender.calls, 0)
        self.assertIn("http", str(caught.exception))

    def test_https_reference_url_passes_composed_path(self):
        sender = StaticSender(200, provider_body(PNG_7X5))
        request = make_request(
            extra_body={"image": ["https://example.com/ref.png"],
                        "response_format": "b64_json"})
        result = self.run_ok(request, sender)
        self.assertEqual(sender.calls, 1)
        self.assertIsNotNone(result.response)
        self.assertIsNone(result.response["receipt"]["task_id"])


if __name__ == "__main__":
    unittest.main()
