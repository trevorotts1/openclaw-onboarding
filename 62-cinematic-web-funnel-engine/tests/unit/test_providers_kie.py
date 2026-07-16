#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_providers_kie.py — offline unit tests for providers/kie.py (Skill 62, U5).

NO NETWORK, NO KIE_API_KEY, NO LIVE/PAID CALL. Every HTTP interaction goes
through a FakeTransport driven by the fixtures in tests/fixtures/kie/ (spec
§19.2 "Kie adapter against mocked API fixtures") — RequestsTransport (the
only implementation that ever touches the network) is never instantiated by
this suite.

Covers:
  - KieProvider.generate_image / generate_video submit the exact body shape
    (model slug resolved ONLY through ModelRegistry, never hardcoded).
  - Seedance two-image `input_urls` FRAME PINNING: order preserved exactly
    (index 0 = first frame, index 1 = last frame), and the registry's
    max_images cap (2) is enforced before any HTTP call.
  - get_task() state mapping (success/fail/pending) against mocked
    recordInfo fixtures.
  - download_results() end-to-end: poll -> decode resultJson (JSON-encoded
    STRING, matching the v14.1.2 fix already shipped in kie_video.py/
    kie_image.py) -> download -> write to disk.
  - estimate_cost() resolves through ModelRegistry.estimate(strict=False):
    an unpriced model (Seedance) comes back honestly unverified; a verified
    model (veo3_fast) comes back with a real total.
  - Secrets resolved by NAME only: a missing KIE_API_KEY raises with the
    env-var NAME in the message, never a value.
  - 46-kie-callback-relay wiring:
      * build_callback_ticket()'s HMAC derivation matches a hand-computed
        vector (same algorithm as kie-slide-submitter.js).
      * verify_kie_webhook_signature() true/false against known vectors,
        matching 46-kie-callback-relay/worker/src/index.js verifyKieSignature.
      * kv_read() found / not-found / 401 / confused-deputy-submitId-mismatch.
      * KieProvider(use_callback=True) attaches a callBackUrl built by the
        SAME derivation, and poll_callback_result() round-trips through
        kv_read() using the stored ticket.

stdlib unittest only — no third-party test runner required.
Run: python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from providers import base, kie  # noqa: E402

_FIXTURES_DIR = _TESTS_DIR.parent / "fixtures" / "kie"


def _load_fixture(name: str) -> Dict[str, Any]:
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# FakeTransport — FIFO-queued responses, never touches the network.
# ---------------------------------------------------------------------------


class FakeTransport(kie.KieTransport):
    def __init__(self) -> None:
        self.post_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self.download_calls: List[str] = []
        self._post_queue: List[kie.HttpResponse] = []
        self._get_queue: List[kie.HttpResponse] = []
        self._download_bytes = b"FIXTURE-DOWNLOAD-BYTES"

    def queue_post(self, resp: kie.HttpResponse) -> None:
        self._post_queue.append(resp)

    def queue_get(self, resp: kie.HttpResponse) -> None:
        self._get_queue.append(resp)

    def post_json(self, url, *, headers, body, timeout):
        self.post_calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        if not self._post_queue:
            raise AssertionError(f"FakeTransport: no queued POST response for {url}")
        return self._post_queue.pop(0)

    def get_json(self, url, *, headers, params, timeout):
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if not self._get_queue:
            raise AssertionError(f"FakeTransport: no queued GET response for {url}")
        return self._get_queue.pop(0)

    def download(self, url, *, timeout):
        self.download_calls.append(url)
        return self._download_bytes


def _resp(status_code: int, body: Dict[str, Any]) -> kie.HttpResponse:
    return kie.HttpResponse(status_code=status_code, json_body=body)


# ---------------------------------------------------------------------------
# KieProvider.generate_image / generate_video — body shape + registry-only resolution
# ---------------------------------------------------------------------------


class GenerateImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.env = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = kie.KieProvider(transport=self.transport)

    def test_generate_image_resolves_slug_from_registry_not_hardcoded(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        handle = self.provider.generate_image(
            base.ImageGenerationRequest(model_id="kie-gpt-image-2-text-to-image", prompt="a red barn")
        )
        body = self.transport.post_calls[0]["body"]
        self.assertEqual(body["model"], "gpt-image-2-text-to-image")  # the registry slug, not the model_id
        self.assertEqual(handle.status, "queued")
        self.assertEqual(handle.provider, "kie")
        self.assertEqual(handle.model_id, "kie-gpt-image-2-text-to-image")

    def test_generate_image_includes_reference_urls_as_image_input(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        self.provider.generate_image(
            base.ImageGenerationRequest(
                model_id="kie-gpt-image-2-image-to-image",
                prompt="edit this",
                reference_image_urls=("https://fixtures.example/ref1.png", "https://fixtures.example/ref2.png"),
            )
        )
        body = self.transport.post_calls[0]["body"]
        self.assertEqual(
            body["input"]["image_input"],
            ["https://fixtures.example/ref1.png", "https://fixtures.example/ref2.png"],
        )

    def test_generate_image_appends_negative_prompt_clause(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        self.provider.generate_image(
            base.ImageGenerationRequest(
                model_id="kie-gpt-image-2-text-to-image", prompt="a barn", negative_prompt="clouds"
            )
        )
        body = self.transport.post_calls[0]["body"]
        self.assertIn("Do not include: clouds", body["input"]["prompt"])

    def test_missing_api_key_raises_with_env_var_name_never_a_value(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = kie.KieProvider(transport=self.transport)
            with self.assertRaises(base.ProviderTaskError) as ctx:
                provider.generate_image(
                    base.ImageGenerationRequest(model_id="kie-gpt-image-2-text-to-image", prompt="x")
                )
            self.assertIn("KIE_API_KEY", str(ctx.exception))
            self.assertEqual(len(self.transport.post_calls), 0)  # refused before any HTTP call


class GenerateVideoSeedanceFramePinningTests(unittest.TestCase):
    """The central proof for this unit: two-image input_urls frame pinning,
    order preserved, registry-enforced cap."""

    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.env = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = kie.KieProvider(transport=self.transport)
        self.first_frame = "https://fixtures.example/scene-04-last-frame.png"
        self.last_frame = "https://fixtures.example/scene-05-first-frame.png"

    def test_two_image_input_urls_pins_first_and_last_frame_in_order(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        handle = self.provider.generate_video(
            base.VideoGenerationRequest(
                model_id="kie-bytedance-seedance-1.5-pro",
                prompt="camera glides between two scenes",
                duration_seconds=8,
                aspect_ratio="21:9",
                resolution="1080p",
                input_urls=(self.first_frame, self.last_frame),
            )
        )
        body = self.transport.post_calls[0]["body"]
        self.assertEqual(body["model"], "bytedance/seedance-1.5-pro")
        self.assertEqual(body["input"]["input_urls"], [self.first_frame, self.last_frame])
        self.assertEqual(body["input"]["aspect_ratio"], "21:9")
        self.assertEqual(body["input"]["resolution"], "1080p")
        self.assertEqual(body["input"]["duration"], "8")
        self.assertIsInstance(body["input"]["duration"], str)
        self.assertEqual(handle.model_id, "kie-bytedance-seedance-1.5-pro")

    def test_text_to_video_omits_input_urls_key_entirely(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        self.provider.generate_video(
            base.VideoGenerationRequest(
                model_id="kie-bytedance-seedance-1.5-pro",
                prompt="a boy rides a bike at sunset",
                duration_seconds=8,
            )
        )
        body = self.transport.post_calls[0]["body"]
        self.assertNotIn("input_urls", body["input"])

    def test_exceeding_registry_max_images_raises_before_any_http_call(self) -> None:
        entry = self.provider.registry.get_model("kie-bytedance-seedance-1.5-pro")
        max_images = entry["reference_image_support"]["max_images"]
        self.assertEqual(max_images, 2)  # sanity: this test's premise
        with self.assertRaises(base.ProviderTaskError):
            self.provider.generate_video(
                base.VideoGenerationRequest(
                    model_id="kie-bytedance-seedance-1.5-pro",
                    prompt="too many frames",
                    duration_seconds=8,
                    input_urls=(self.first_frame, self.last_frame, "https://fixtures.example/extra.png"),
                )
            )
        self.assertEqual(len(self.transport.post_calls), 0)


# ---------------------------------------------------------------------------
# get_task / download_results — poll + resultJson-string decode + download
# ---------------------------------------------------------------------------


class TaskLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.env = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = kie.KieProvider(transport=self.transport)

    def test_get_task_maps_success_state(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("record_info_success_video.json")))
        handle = self.provider.get_task("fixture-task-seedance-frame-pin-0001")
        self.assertEqual(handle.status, "success")
        self.assertIsNone(handle.detail)

    def test_get_task_maps_failed_state_with_detail(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("record_info_failed.json")))
        handle = self.provider.get_task("fixture-task-failed-0001")
        self.assertEqual(handle.status, "failed")
        self.assertEqual(handle.detail, "content policy violation")

    def test_get_task_maps_absent_state_as_queued(self) -> None:
        self.transport.queue_get(_resp(200, {"code": 200, "data": {}}))
        handle = self.provider.get_task("fixture-task-unknown")
        self.assertEqual(handle.status, "queued")

    def test_cancel_task_always_returns_false_no_kie_cancel_endpoint(self) -> None:
        self.assertFalse(self.provider.cancel_task("any-task-id"))

    def test_download_results_decodes_resultjson_string_and_writes_file(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("record_info_success_video.json")))
        with_tmp = _TESTS_DIR / "_tmp_download_results"
        try:
            paths = self.provider.download_results("fixture-task-seedance-frame-pin-0001", str(with_tmp / "clip.mp4"))
            self.assertEqual(len(paths), 1)
            written = Path(paths[0])
            self.assertTrue(written.exists())
            self.assertEqual(written.read_bytes(), b"FIXTURE-DOWNLOAD-BYTES")
            self.assertEqual(
                self.transport.download_calls,
                ["https://tempfile.aiquickdraw.com/s/fixture-seedance-connector-clip.mp4"],
            )
        finally:
            import shutil

            if with_tmp.exists():
                shutil.rmtree(with_tmp)

    def test_download_results_raises_on_failed_task(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("record_info_failed.json")))
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.provider.download_results("fixture-task-failed-0001", "/tmp/should-not-be-written.mp4")
        self.assertIn("content policy violation", str(ctx.exception))


# ---------------------------------------------------------------------------
# estimate_cost — registry-resolved, honest about unpriced Seedance
# ---------------------------------------------------------------------------


class EstimateCostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.env = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = kie.KieProvider(transport=self.transport)

    def test_seedance_estimate_is_honestly_unverified(self) -> None:
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(
                model_id="kie-bytedance-seedance-1.5-pro", prompt="x", duration_seconds=8
            )
        )
        self.assertFalse(estimate.verified)
        self.assertIsNone(estimate.estimated_total)

    def test_veo3_fast_estimate_is_verified_and_priced_per_clip_not_per_second(self) -> None:
        # veo3_fast is usd_per_clip (07-kie-setup/kie-setup-full.md). An 8s
        # request must NOT be multiplied by 8 -- that would silently assume
        # a per-second unit the registry does not declare for this model.
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(model_id="kie-veo3-fast", prompt="x", duration_seconds=8)
        )
        self.assertTrue(estimate.verified)
        self.assertEqual(estimate.unit, "usd_per_clip")
        self.assertEqual(estimate.unit_price, 0.40)
        self.assertEqual(estimate.estimated_total, 0.40)

    def test_gemini_omni_video_estimate_is_priced_per_second(self) -> None:
        # gemini-omni-video IS usd_per_second, so duration_seconds must
        # actually multiply the unit price here (the opposite case from
        # veo3_fast above -- proves the unit-aware branch both ways).
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(model_id="kie-gemini-omni-video", prompt="x", duration_seconds=8)
        )
        self.assertEqual(estimate.unit, "usd_per_second")
        self.assertEqual(estimate.unit_price, 0.10)
        self.assertEqual(estimate.estimated_total, 0.80)


# ---------------------------------------------------------------------------
# 46-kie-callback-relay wiring
# ---------------------------------------------------------------------------


class CallbackTicketTests(unittest.TestCase):
    def test_build_callback_ticket_matches_hand_computed_hmac(self) -> None:
        ticket = kie.build_callback_ticket(
            worker_base_url="https://kie-callback.example.workers.dev",
            client_slug="fixture-client",
            callback_hmac_key="fixture-per-client-key",
        )
        expected_validator = hmac.new(
            b"fixture-per-client-key", f"fixture-client:{ticket.submit_id}".encode(), hashlib.sha256
        ).hexdigest()
        expected_secret_hmac = hmac.new(
            b"fixture-per-client-key", ticket.per_task_secret.encode(), hashlib.sha256
        ).hexdigest()
        expected_url = (
            f"https://kie-callback.example.workers.dev/cb?c=fixture-client"
            f"&j={ticket.submit_id}&s={expected_validator}&h={expected_secret_hmac}"
        )
        self.assertEqual(ticket.callback_url, expected_url)
        self.assertEqual(len(ticket.submit_id), 32)  # 128-bit hex = 32 chars
        self.assertEqual(len(ticket.per_task_secret), 64)  # 256-bit hex = 64 chars

    def test_no_raw_secret_appears_in_the_callback_url(self) -> None:
        ticket = kie.build_callback_ticket(
            worker_base_url="https://kie-callback.example.workers.dev",
            client_slug="fixture-client",
            callback_hmac_key="fixture-per-client-key",
        )
        self.assertNotIn(ticket.per_task_secret, ticket.callback_url)
        self.assertNotIn("fixture-per-client-key", ticket.callback_url)

    def test_two_tickets_never_collide(self) -> None:
        a = kie.build_callback_ticket(
            worker_base_url="https://x.example", client_slug="c", callback_hmac_key="k"
        )
        b = kie.build_callback_ticket(
            worker_base_url="https://x.example", client_slug="c", callback_hmac_key="k"
        )
        self.assertNotEqual(a.submit_id, b.submit_id)
        self.assertNotEqual(a.per_task_secret, b.per_task_secret)
        self.assertNotEqual(a.callback_url, b.callback_url)


class VerifyKieWebhookSignatureTests(unittest.TestCase):
    """Same algorithm as 46-kie-callback-relay/worker/src/index.js
    verifyKieSignature: HMAC-SHA256(taskId + "." + timestamp, hmacKey),
    base64-encoded, constant-time compared."""

    def test_correct_signature_verifies(self) -> None:
        task_id, timestamp, key = "task-abc123", "1752566400", "fixture-webhook-hmac-key"
        digest = hmac.new(key.encode(), f"{task_id}.{timestamp}".encode(), hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("ascii")
        self.assertTrue(
            kie.verify_kie_webhook_signature(
                task_id=task_id, timestamp_seconds=timestamp, signature_b64=signature, webhook_hmac_key=key
            )
        )

    def test_wrong_key_fails(self) -> None:
        task_id, timestamp = "task-abc123", "1752566400"
        digest = hmac.new(b"right-key", f"{task_id}.{timestamp}".encode(), hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("ascii")
        self.assertFalse(
            kie.verify_kie_webhook_signature(
                task_id=task_id, timestamp_seconds=timestamp, signature_b64=signature, webhook_hmac_key="wrong-key"
            )
        )

    def test_tampered_timestamp_fails(self) -> None:
        task_id, key = "task-abc123", "fixture-webhook-hmac-key"
        digest = hmac.new(key.encode(), f"{task_id}.1752566400".encode(), hashlib.sha256).digest()
        signature = base64.b64encode(digest).decode("ascii")
        # Signature was computed over timestamp 1752566400; verifying against
        # a different timestamp must fail (a forged/replayed timestamp).
        self.assertFalse(
            kie.verify_kie_webhook_signature(
                task_id=task_id, timestamp_seconds="1752566401", signature_b64=signature, webhook_hmac_key=key
            )
        )

    def test_missing_inputs_return_false_never_raise(self) -> None:
        self.assertFalse(kie.verify_kie_webhook_signature(task_id="", timestamp_seconds="1", signature_b64="x", webhook_hmac_key="k"))
        self.assertFalse(kie.verify_kie_webhook_signature(task_id="t", timestamp_seconds="", signature_b64="x", webhook_hmac_key="k"))
        self.assertFalse(kie.verify_kie_webhook_signature(task_id="t", timestamp_seconds="1", signature_b64="", webhook_hmac_key="k"))
        self.assertFalse(kie.verify_kie_webhook_signature(task_id="t", timestamp_seconds="1", signature_b64="x", webhook_hmac_key=""))


class KvReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()

    def test_found_matching_submit_id_returns_result(self) -> None:
        fixture = _load_fixture("kv_read_found.json")
        fixture["result"]["submitId"] = "the-real-submit-id"
        fixture["result"]["taskId"] = "the-real-task-id"
        self.transport.queue_get(_resp(200, fixture))
        result = kie.kv_read(
            self.transport,
            worker_base_url="https://kie-callback.example.workers.dev",
            client_slug="fixture-client",
            submit_id="the-real-submit-id",
            kv_read_token="fixture-token",
            per_task_secret="fixture-secret-preimage",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["taskId"], "the-real-task-id")
        # Fix G: the preimage travels in a header, never a query param.
        call = self.transport.get_calls[0]
        self.assertEqual(call["headers"]["X-Kie-Preimage"], "fixture-secret-preimage")
        self.assertEqual(call["headers"]["Authorization"], "Bearer fixture-token")
        self.assertNotIn("fixture-secret-preimage", call["url"])

    def test_not_found_returns_none(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("kv_read_not_found.json")))
        result = kie.kv_read(
            self.transport,
            worker_base_url="https://x.example",
            client_slug="c",
            submit_id="s",
            kv_read_token="t",
            per_task_secret="p",
        )
        self.assertIsNone(result)

    def test_unauthorized_returns_none_not_an_exception(self) -> None:
        self.transport.queue_get(_resp(401, {"error": "unauthorized"}))
        result = kie.kv_read(
            self.transport,
            worker_base_url="https://x.example",
            client_slug="c",
            submit_id="s",
            kv_read_token="wrong-token",
            per_task_secret="p",
        )
        self.assertIsNone(result)

    def test_confused_deputy_submit_id_mismatch_is_dropped(self) -> None:
        """Fix 34 (box-kv-poller.js _validatePerTaskSecret, ported): a
        result for a DIFFERENT submitId must never be accepted."""
        fixture = _load_fixture("kv_read_found.json")
        fixture["result"]["submitId"] = "a-different-tasks-submit-id"
        self.transport.queue_get(_resp(200, fixture))
        result = kie.kv_read(
            self.transport,
            worker_base_url="https://x.example",
            client_slug="c",
            submit_id="the-submit-id-i-actually-asked-for",
            kv_read_token="t",
            per_task_secret="p",
        )
        self.assertIsNone(result)


class KieProviderCallbackIntegrationTests(unittest.TestCase):
    """End-to-end: KieProvider attaches a callBackUrl on submit and later
    resolves the result via poll_callback_result() -> kv_read()."""

    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.env = patch.dict(
            "os.environ",
            {
                "KIE_API_KEY": "FIXTURE-KEY",
                "KIE_KV_BASE_URL": "https://kie-callback.example.workers.dev",
                "KIE_CALLBACK_HMAC_KEY": "fixture-per-client-callback-key",
                "KVREAD_TOKEN": "fixture-per-client-kv-read-token",
                "KIE_CLIENT_SLUG": "fixture-client",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = kie.KieProvider(transport=self.transport)

    def test_callback_enabled_true_when_all_three_env_vars_present(self) -> None:
        self.assertTrue(self.provider.callback_enabled())

    def test_callback_enabled_false_when_one_env_var_missing(self) -> None:
        with patch.dict("os.environ", {"KIE_CLIENT_SLUG": ""}, clear=False):
            self.assertFalse(self.provider.callback_enabled())

    def test_generate_video_attaches_callback_url_matching_the_same_derivation(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        handle = self.provider.generate_video(
            base.VideoGenerationRequest(
                model_id="kie-bytedance-seedance-1.5-pro", prompt="x", duration_seconds=8
            ),
            use_callback=True,
        )
        body = self.transport.post_calls[0]["body"]
        self.assertIn("callBackUrl", body)
        self.assertTrue(body["callBackUrl"].startswith("https://kie-callback.example.workers.dev/cb?c=fixture-client&j="))
        ticket = self.provider._callback_tickets[handle.task_id]
        self.assertEqual(body["callBackUrl"], ticket.callback_url)

    def test_generate_video_without_use_callback_flag_omits_callback_url(self) -> None:
        # use_callback=None (default) resolves via callback_enabled() -- all
        # three env vars ARE present in this fixture, so it attaches by
        # default. Explicitly passing False must override that.
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        self.provider.generate_video(
            base.VideoGenerationRequest(model_id="kie-bytedance-seedance-1.5-pro", prompt="x", duration_seconds=8),
            use_callback=False,
        )
        body = self.transport.post_calls[0]["body"]
        self.assertNotIn("callBackUrl", body)

    def test_poll_callback_result_round_trips_through_kv_read(self) -> None:
        self.transport.queue_post(_resp(200, _load_fixture("create_task_success.json")))
        handle = self.provider.generate_video(
            base.VideoGenerationRequest(model_id="kie-bytedance-seedance-1.5-pro", prompt="x", duration_seconds=8),
            use_callback=True,
        )
        ticket = self.provider._callback_tickets[handle.task_id]

        kv_fixture = _load_fixture("kv_read_found.json")
        kv_fixture["result"]["submitId"] = ticket.submit_id
        kv_fixture["result"]["taskId"] = handle.task_id
        self.transport.queue_get(_resp(200, kv_fixture))

        result = self.provider.poll_callback_result(handle.task_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["taskId"], handle.task_id)
        kv_call = self.transport.get_calls[-1]
        self.assertEqual(kv_call["headers"]["X-Kie-Preimage"], ticket.per_task_secret)
        self.assertEqual(kv_call["headers"]["Authorization"], "Bearer fixture-per-client-kv-read-token")

    def test_poll_callback_result_returns_none_for_unknown_task(self) -> None:
        self.assertIsNone(self.provider.poll_callback_result("never-submitted-task-id"))
        self.assertEqual(len(self.transport.get_calls), 0)  # never even attempts a call


if __name__ == "__main__":
    unittest.main()
