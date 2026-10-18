#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_agnes_response.py -- stdlib unittest for agnes_response.py.

A24 Leg 4 (G-07, G-13, G-14, G-15) plus the dispatch contract
section 11.4 receipt cases and section 11.5 receipt lines. All
provider bodies are synthetic; the PNG and JPEG fixtures are tiny
real image byte strings generated here. No network, no provider.

Run: python3 -m unittest test_agnes_response (from this directory)
or:  python3 test_agnes_response.py
"""
from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agnes_response as ar


# ---------------------------------------------------------------------------
# Tiny real image fixtures
# ---------------------------------------------------------------------------

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


def make_jpeg(width: int, height: int) -> bytes:
    app0 = (
        b"\xff\xe0" + struct.pack(">H", 16)
        + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    )
    sof0 = (
        b"\xff\xc0" + struct.pack(">H", 17) + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


PNG_7X5 = make_png(7, 5)
JPEG_11X3 = make_jpeg(11, 3)
MODEL = "agnes-image-2.5-flash"
PROMPT = "a lighthouse on a granite point at dawn, editorial photo"
POLICY_LAUNCH = "signature_launch_completeness"
POLICY_LEGACY = "legacy_house_band"


def b64_body(image_bytes: bytes, *, model=MODEL, request_id="req-123",
             include_model=True, include_id=True, data_model=None) -> bytes:
    item = {"b64_json": base64.b64encode(image_bytes).decode("ascii"), "url": None}
    if data_model is not None:
        item["model"] = data_model
    doc = {"data": [item]}
    if include_model:
        doc["model"] = model
    if include_id:
        doc["id"] = request_id
    return json.dumps(doc).encode("utf-8")


def tmp_root() -> Path:
    env = os.environ.get("AGNES_RESPONSE_TEST_TMP")
    if env:
        return Path(env)
    lane = Path(__file__).resolve().parents[3] / "test-tmp"
    lane.mkdir(parents=True, exist_ok=True)
    return lane


class ResponseTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(dir=str(tmp_root()))
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "image.png"
        self.run_record: dict = {}

    def tearDown(self):
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Receipt cases (G-14, contract 9 and 11.4 / 11.5)
# ---------------------------------------------------------------------------

class ReceiptCases(ResponseTestCase):
    def test_receipt_from_persisted_png(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5), requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
            run_record=self.run_record,
        )
        receipt = result["receipt"]
        self.assertIsNone(receipt["task_id"])
        self.assertEqual(receipt["prompt_policy_id"], POLICY_LAUNCH)
        ar.validate_receipt(receipt)  # must not raise
        self.assertEqual(receipt["dimensions"], "7x5")
        self.assertEqual(receipt["result_bytes"], len(PNG_7X5))
        self.assertEqual(receipt["request_id"], "req-123")
        self.assertTrue(self.out.is_file())
        self.assertEqual(result["actual_model_status"], "confirmed_equal")

    def test_receipt_altered_task_id_fails_validation(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5), requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
        )
        altered = dict(result["receipt"])
        altered["task_id"] = "manufactured-id"
        with self.assertRaises(ar.ReceiptError):
            ar.validate_receipt(altered)

    def test_receipt_built_only_after_persistence(self):
        ar.process_success_body(
            b64_body(PNG_7X5), requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
        )
        self.assertTrue(self.out.is_file())
        self.out.unlink()
        with self.assertRaises(ar.ResponseProcessingError):
            ar.build_receipt_from_persisted(
                output_path=self.out, model_id=MODEL, prompt=PROMPT,
                prompt_policy_id=POLICY_LAUNCH, request_id=None,
            )

    def test_dimensions_measured_from_jpeg_fixture(self):
        out = self.dir / "image.jpg"
        result = ar.process_success_body(
            b64_body(JPEG_11X3), requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LAUNCH, output_path=out,
        )
        self.assertEqual(result["dimensions"], "11x3")
        self.assertEqual(result["receipt"]["dimensions"], "11x3")
        self.assertEqual(result["media_type"], "jpeg")

    def test_policy_citation_passed_explicitly(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5), requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LEGACY, output_path=self.out,
        )
        self.assertEqual(result["receipt"]["prompt_policy_id"], POLICY_LEGACY)

    def test_request_id_null_when_provider_returns_none(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5, include_id=False), requested_model_id=MODEL,
            prompt=PROMPT, prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
        )
        self.assertIsNone(result["receipt"]["request_id"])
        self.assertIsNone(result["request_id"])

    def test_non_image_payload_refused_before_persist(self):
        body = b64_body(b"<html><body>error page</body></html>")
        with self.assertRaises(ar.ResponseProcessingError):
            ar.process_success_body(
                body, requested_model_id=MODEL, prompt=PROMPT,
                prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
            )
        self.assertFalse(self.out.exists())


# ---------------------------------------------------------------------------
# Actual-model cases (G-07)
# ---------------------------------------------------------------------------

class ActualModelCases(ResponseTestCase):
    def test_matching_actual_model_proceeds(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5, model=MODEL), requested_model_id=MODEL,
            prompt=PROMPT, prompt_policy_id=POLICY_LAUNCH,
            output_path=self.out, run_record=self.run_record,
        )
        self.assertEqual(result["actual_model_status"], "confirmed_equal")
        events = [e["event"] for e in self.run_record["response_events"]]
        self.assertIn("actual_model_confirmed", events)

    def test_actual_model_from_data_item(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5, include_model=False, data_model=MODEL),
            requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
        )
        self.assertEqual(result["actual_model_status"], "confirmed_equal")

    def test_differing_actual_model_stops_with_mismatch_surfaced(self):
        with self.assertRaises(ar.ActualModelMismatch) as ctx:
            ar.process_success_body(
                b64_body(PNG_7X5, model="agnes-image-2.1-flash"),
                requested_model_id=MODEL, prompt=PROMPT,
                prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
                run_record=self.run_record,
            )
        self.assertEqual(ctx.exception.requested, MODEL)
        self.assertEqual(ctx.exception.actual, "agnes-image-2.1-flash")
        self.assertFalse(self.out.exists())  # stopped before persist/receipt
        events = [e for e in self.run_record["response_events"]
                  if e["event"] == "actual_model_mismatch"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["actual_model"], "agnes-image-2.1-flash")

    def test_absent_actual_model_evidence_records_limitation(self):
        result = ar.process_success_body(
            b64_body(PNG_7X5, include_model=False), requested_model_id=MODEL,
            prompt=PROMPT, prompt_policy_id=POLICY_LAUNCH,
            output_path=self.out, run_record=self.run_record,
        )
        self.assertEqual(result["actual_model_status"], "no_evidence_recorded")
        events = [e for e in self.run_record["response_events"]
                  if e["event"] == "actual_model_evidence_absent"]
        self.assertEqual(len(events), 1)
        self.assertIn("no actual-model evidence", events[0]["limitation"])


# ---------------------------------------------------------------------------
# Existing-result cases (G-13)
# ---------------------------------------------------------------------------

class ExistingResultCases(ResponseTestCase):
    def test_completed_fingerprint_returns_stored_result(self):
        calls = {"fetch": 0}

        def counting_fetcher(url):
            calls["fetch"] += 1
            return PNG_7X5

        result = ar.process_success_body(
            b64_body(PNG_7X5), requested_model_id=MODEL, prompt=PROMPT,
            prompt_policy_id=POLICY_LAUNCH, output_path=self.out,
            run_dir=self.dir, fingerprint="fp-001", fetcher=counting_fetcher,
        )
        self.assertEqual(calls["fetch"], 0)  # b64 form needed no fetch
        resolution = ar.resolve_ambiguous_outcome(self.dir, "fp-001",
                                                  run_record=self.run_record)
        self.assertEqual(resolution["outcome"], "existing_result")
        self.assertEqual(resolution["resubmission"], "not_performed")
        self.assertEqual(resolution["entry"]["output_path"], str(self.out))
        self.assertEqual(
            resolution["entry"]["receipt_result_sha256"],
            result["receipt"]["result_sha256"],
        )
        self.assertEqual(calls["fetch"], 0)  # zero sender involvement on lookup

    def test_unknown_fingerprint_discloses_and_never_resubmits(self):
        resolution = ar.resolve_ambiguous_outcome(self.dir, "fp-unknown",
                                                  run_record=self.run_record)
        self.assertEqual(resolution["outcome"], "no_existing_result")
        self.assertIn("duplicate-cost risk", resolution["duplicate_cost_risk"])
        self.assertEqual(resolution["resubmission"],
                         "separate_bounded_decision_required")
        self.assertFalse(resolution["automatic_resubmission"])
        self.assertIsNone(ar.check_existing_result(self.dir, "fp-unknown"))


# ---------------------------------------------------------------------------
# Reference-URL cases (G-15)
# ---------------------------------------------------------------------------

class ReferenceUrlCases(unittest.TestCase):
    def test_https_public_host_passes(self):
        url = "https://cdn.example.com/refs/portrait.png"
        self.assertEqual(ar.check_reference_url(url), url)

    def test_https_public_ip_literal_passes(self):
        url = "https://93.184.216.34/ref.png"
        self.assertEqual(ar.check_reference_url(url), url)

    def test_http_fails_by_name(self):
        with self.assertRaises(ar.ReferenceUrlError) as ctx:
            ar.check_reference_url("http://cdn.example.com/ref.png")
        self.assertIn("https", str(ctx.exception))

    def test_localhost_fails_by_name(self):
        for url in ("https://localhost/ref.png", "https://127.0.0.1:8000/ref.png"):
            with self.assertRaises(ar.ReferenceUrlError) as ctx:
                ar.check_reference_url(url)
            self.assertTrue(
                "localhost" in str(ctx.exception) or "non-public" in str(ctx.exception),
                str(ctx.exception),
            )

    def test_private_ip_literals_fail_by_name(self):
        for url in ("https://192.168.1.10/ref.png", "https://10.0.0.5/ref.png",
                    "https://172.16.4.9/ref.png", "https://[::1]/ref.png"):
            with self.assertRaises(ar.ReferenceUrlError) as ctx:
                ar.check_reference_url(url)
            self.assertIn("non-public", str(ctx.exception))

    def test_check_reference_urls_batch(self):
        urls = ["https://a.example.com/1.png", "https://b.example.com/2.png"]
        self.assertEqual(ar.check_reference_urls(urls), urls)
        with self.assertRaises(ar.ReferenceUrlError):
            ar.check_reference_urls(urls + ["http://c.example.com/3.png"])


# ---------------------------------------------------------------------------
# Body parsing (G-14 shape validation and URL-form extraction)
# ---------------------------------------------------------------------------

class BodyParsingCases(ResponseTestCase):
    def test_invalid_json_body_refused(self):
        with self.assertRaises(ar.ResponseProcessingError):
            ar.parse_provider_body(b"this is not json")

    def test_body_without_data_refused(self):
        with self.assertRaises(ar.ResponseProcessingError):
            ar.parse_provider_body(json.dumps({"model": MODEL}).encode("utf-8"))

    def test_url_form_image_via_injected_fetcher(self):
        seen = []

        def fake_fetcher(url):
            seen.append(url)
            return JPEG_11X3

        doc = {"model": MODEL, "id": "req-9",
               "data": [{"url": "https://provider.example/img.jpg", "b64_json": None}]}
        out = self.dir / "fetched.jpg"
        result = ar.process_success_body(
            json.dumps(doc).encode("utf-8"), requested_model_id=MODEL,
            prompt=PROMPT, prompt_policy_id=POLICY_LAUNCH, output_path=out,
            fetcher=fake_fetcher,
        )
        self.assertEqual(seen, ["https://provider.example/img.jpg"])
        self.assertEqual(result["dimensions"], "11x3")

    def test_url_form_without_fetcher_is_an_error(self):
        doc = {"model": MODEL,
               "data": [{"url": "https://provider.example/img.jpg", "b64_json": None}]}
        with self.assertRaises(ar.ResponseProcessingError):
            ar.process_success_body(
                json.dumps(doc).encode("utf-8"), requested_model_id=MODEL,
                prompt=PROMPT, prompt_policy_id=POLICY_LAUNCH,
                output_path=self.out,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
