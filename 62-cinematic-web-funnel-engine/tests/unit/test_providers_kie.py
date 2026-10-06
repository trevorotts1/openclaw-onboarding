#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_providers_kie.py: offline unit tests for providers/kie.py (Skill 62).

NO NETWORK, NO KIE_API_KEY, NO LIVE/PAID CALL. Every HTTP interaction goes
through a FakeTransport (spec §19.2 "Kie adapter against mocked API fixtures")
that is bridged onto Skill 74's transport interface, so the REAL Skill 74
client (74-kie-live-adapter, loaded from the sibling skill folder) runs its
real submit/validate/prompt-budget/upload/wait/save/price code against the
fake. RequestsTransport is never instantiated by this suite.

Covers:
  - KieProvider submits through Skill 74 in ``active`` mode and logs
    ``path=skill74``; without Skill 74 it logs ``path=legacy`` and uses the
    quarantined fallback client.
  - generate_image / generate_video submit the exact body shape (model slug
    resolved ONLY through ModelRegistry); image-to-image sends ``input_urls``
    and never the undeclared ``output_format``.
  - Skill 74 schema validation refuses an out-of-schema body before createTask;
    prompt length comes from Skill 74 prompt-budget (over the maximum is
    refused, under the floor is reported).
  - Seedance two-image frame pinning, Veo 3.1 wire shape, quality-tier refusal.
  - get_task / download_results / upload_asset through Skill 74.
  - estimate_cost: live catalog price through Skill 74 first, labeled
    fallback constants otherwise.
  - 46-kie-callback-relay wiring (HMAC derivation, webhook verification,
    kv_read, callBackUrl attachment).

stdlib unittest only.
Run: python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch
from urllib.parse import urlparse

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from providers import base, kie  # noqa: E402

_FIXTURES_DIR = _TESTS_DIR.parent / "fixtures" / "kie"


_VEO_PRICING_DESC = (
    "Lite mode (text-to-video / image-to-video/ reference-to-video): 720P — 30 credits (≈ $0.15) per video; "
    "1080P — 35 credits (≈ $0.175) per video; 4K — 150 credits (≈ $0.75) per video.\n"
    "Fast mode (text-to-video / image-to-video / reference-to-video): 720P — 60 credits (≈ $0.30) per video; "
    "1080P — 65 credits (≈ $0.325) per video; 4K — 180 credits (≈ $0.90) per video.\n"
    "Quality mode (text-to-video / image-to-video): 720P — 250 credits (≈ $1.25) per video; "
    "1080P — 255 credits (≈ $1.275) per video; 4K — 370 credits (≈ $1.85) per video.\n\n"
    "High-tier top-ups (+10% bonus) reduce the effective cost by about 10%."
)


def _load_fixture(name: str) -> Dict[str, Any]:
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _resp(status_code: int, body: Dict[str, Any]) -> kie.HttpResponse:
    return kie.HttpResponse(status_code=status_code, json_body=body)


# ---------------------------------------------------------------------------
# FakeTransport: routed (catalog / schema / credit answer by path), with
# FIFO queues for createTask, recordInfo and the kv-read Worker. Never touches
# the network. ``post_calls`` holds createTask calls only; ``get_calls`` holds
# every non-discovery GET (recordInfo, kv-read).
# ---------------------------------------------------------------------------


class FakeTransport(kie.KieTransport):
    def __init__(self) -> None:
        self.post_calls: List[Dict[str, Any]] = []
        self.upload_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self.discovery_paths: List[str] = []
        self.download_calls: List[str] = []
        self._post_queue: List[kie.HttpResponse] = []
        self._get_queue: List[kie.HttpResponse] = []
        self._download_bytes = b"FIXTURE-DOWNLOAD-BYTES"
        self.catalog_models: List[Dict[str, Any]] = []
        self.catalog_code = 200
        self.prompt_max: Optional[int] = None
        self.input_overrides: Dict[str, Dict[str, Any]] = {}

    def queue_post(self, resp: kie.HttpResponse) -> None:
        self._post_queue.append(resp)

    def queue_get(self, resp: kie.HttpResponse) -> None:
        self._get_queue.append(resp)

    def _schema_body(self, model: str) -> Dict[str, Any]:
        prompt: Dict[str, Any] = {"type": "string"}
        if self.prompt_max is not None:
            prompt["maxLength"] = self.prompt_max
        props: Dict[str, Any] = {"prompt": prompt}
        props.update(self.input_overrides.get(model, {}))
        schema = {
            "type": "object",
            "required": ["model", "input"],
            "properties": {
                "model": {"type": "string"},
                "callBackUrl": {"type": "string"},
                "input": {"type": "object", "properties": props},
            },
        }
        openapi = {
            "openapi": "3.1.0",
            "paths": {"/api/v1/jobs/createTask": {"post": {"requestBody": {"content": {"application/json": {"schema": schema}}}}}},
        }
        return {"code": 200, "msg": "success", "data": {"openapi": openapi}}

    def post_json(self, url, *, headers, body, timeout):
        if url.endswith("/createTask"):
            self.post_calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
            return self._post_queue.pop(0) if self._post_queue else _resp(200, _load_fixture("create_task_success.json"))
        self.upload_calls.append({"url": url, "headers": headers, "body": body})
        return _resp(200, {"code": 200, "data": {"downloadUrl": "https://fixtures.example/uploaded-ref.png", "fileName": body.get("fileName")}})

    def get_json(self, url, *, headers, params, timeout):
        path = urlparse(url).path
        if path == "/api/v1/models":
            self.discovery_paths.append(path)
            if self.catalog_code != 200:
                return _resp(200, {"code": self.catalog_code, "msg": "unauthorized", "data": None})
            return _resp(200, {"code": 200, "msg": "success", "data": {"total": len(self.catalog_models), "models": self.catalog_models}})
        if path.startswith("/api/v1/models/") and path.endswith("/schema"):
            self.discovery_paths.append(path)
            return _resp(200, self._schema_body(path[len("/api/v1/models/"):-len("/schema")]))
        if path == "/api/v1/chat/credit":
            self.discovery_paths.append(path)
            return _resp(200, {"code": 200, "msg": "success", "data": 100000})
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if not self._get_queue:
            raise AssertionError(f"FakeTransport: no queued GET response for {url}")
        return self._get_queue.pop(0)

    def download(self, url, *, timeout):
        self.download_calls.append(url)
        return self._download_bytes


class _ProviderCase(unittest.TestCase):
    """Common setUp: fake transport + fixture key; stderr captured so the
    ``path=`` log line can be asserted."""

    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.env = patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = kie.KieProvider(transport=self.transport)
        self.stderr = io.StringIO()
        redirect = contextlib.redirect_stderr(self.stderr)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)


# ---------------------------------------------------------------------------
# Skill 74 is the transport (and the legacy fallback is the exception)
# ---------------------------------------------------------------------------


class Skill74TransportTests(_ProviderCase):
    def test_submit_runs_through_skill74_active_mode_and_logs_the_path(self) -> None:
        self.provider.generate_image(
            base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="a red barn")
        )
        self.assertEqual(self.provider.client_path, "skill74")
        self.assertIn("path=skill74 mode=active", self.stderr.getvalue())
        # Skill 74 read the live schema before createTask; the key never appears in a log line.
        self.assertTrue(any(p.endswith("/schema") for p in self.transport.discovery_paths))
        self.assertEqual(len(self.transport.post_calls), 1)
        self.assertNotIn("FIXTURE-KEY", self.stderr.getvalue())

    def test_out_of_schema_body_is_refused_by_skill74_before_createtask(self) -> None:
        self.transport.input_overrides["gpt-image-2-5-sunburst-text-to-image"] = {
            "aspect_ratio": {"type": "string", "enum": ["16:9"]}
        }
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.provider.generate_image(
                base.ImageGenerationRequest(
                    model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="a barn", aspect_ratio="1:1"
                )
            )
        self.assertIn("validation_failed", str(ctx.exception))
        self.assertEqual(len(self.transport.post_calls), 0)

    def test_prompt_over_the_model_maximum_is_refused_via_prompt_budget(self) -> None:
        self.transport.prompt_max = 50
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.provider.generate_image(
                base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="x" * 80)
            )
        self.assertIn("exceeds the model limit", str(ctx.exception))
        self.assertIn("CUT exactly 30", str(ctx.exception))
        self.assertEqual(len(self.transport.post_calls), 0)

    def test_prompt_inside_the_budget_is_submitted_silently(self) -> None:
        self.transport.prompt_max = 50
        self.provider.generate_image(
            base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="x" * 48)
        )
        self.assertEqual(len(self.transport.post_calls), 1)
        self.assertNotIn("WARNING", self.stderr.getvalue())

    def test_prompt_under_the_floor_is_reported_and_still_submitted(self) -> None:
        self.transport.prompt_max = 1000
        self.provider.generate_image(
            base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="a barn")
        )
        self.assertEqual(len(self.transport.post_calls), 1)
        self.assertIn("below the prompt-budget floor", self.stderr.getvalue())

    def test_upload_asset_goes_through_skill74_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "ref.png"
            png.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            url = self.provider.upload_asset(base.AssetUploadRequest(path=str(png), purpose="approved_concept_reference"))
        self.assertEqual(url, "https://fixtures.example/uploaded-ref.png")
        call = self.transport.upload_calls[0]
        self.assertTrue(call["url"].endswith("/api/file-base64-upload"))
        self.assertEqual(call["body"]["uploadPath"], "images/cinematic-web-funnel-engine/approved_concept_reference")
        self.assertEqual(call["body"]["fileName"], "ref.png")
        self.assertEqual(call["headers"]["Authorization"], "Bearer FIXTURE-KEY")

    def test_without_skill74_the_quarantined_fallback_runs_and_says_so(self) -> None:
        with patch.dict("os.environ", {"CWFE_SKILL74_DIR": ""}):
            provider = kie.KieProvider(transport=self.transport)
            handle = provider.generate_image(
                base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="a red barn")
            )
        self.assertEqual(provider.client_path, "legacy")
        self.assertIn("path=legacy", self.stderr.getvalue())
        self.assertEqual(handle.status, "queued")
        self.assertEqual(self.transport.discovery_paths, [])  # no schema/catalog reads on the fallback
        self.assertEqual(self.transport.post_calls[0]["body"]["model"], "gpt-image-2-5-sunburst-text-to-image")

    def test_fallback_download_and_status_use_the_legacy_client(self) -> None:
        with patch.dict("os.environ", {"CWFE_SKILL74_DIR": ""}):
            provider = kie.KieProvider(transport=self.transport)
            self.transport.queue_get(_resp(200, _load_fixture("record_info_success_video.json")))
            self.assertEqual(provider.get_task("t").status, "success")
            self.transport.queue_get(_resp(200, _load_fixture("record_info_success_video.json")))
            with tempfile.TemporaryDirectory() as tmp:
                paths = provider.download_results("t", str(Path(tmp) / "clip.mp4"))
                self.assertEqual(Path(paths[0]).read_bytes(), b"FIXTURE-DOWNLOAD-BYTES")


class GenerateImageTests(_ProviderCase):
    def test_generate_image_resolves_slug_from_registry_not_hardcoded(self) -> None:
        handle = self.provider.generate_image(
            base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="a red barn")
        )
        body = self.transport.post_calls[0]["body"]
        self.assertEqual(body["model"], "gpt-image-2-5-sunburst-text-to-image")  # the registry slug, not the model_id
        self.assertEqual(handle.status, "queued")
        self.assertEqual(handle.provider, "kie")
        self.assertEqual(handle.model_id, "kie-gpt-image-2-5-sunburst-text-to-image")

    def test_generate_image_sends_only_declared_fields_with_input_urls_for_references(self) -> None:
        self.provider.generate_image(
            base.ImageGenerationRequest(
                model_id="kie-gpt-image-2-5-sunburst-image-to-image",
                prompt="edit this",
                reference_image_urls=("https://fixtures.example/ref1.png", "https://fixtures.example/ref2.png"),
            )
        )
        task_input = self.transport.post_calls[0]["body"]["input"]
        self.assertEqual(task_input["input_urls"], ["https://fixtures.example/ref1.png", "https://fixtures.example/ref2.png"])
        self.assertNotIn("image_input", task_input)  # the Nano Banana field is not the sunburst field
        self.assertNotIn("output_format", task_input)  # neither sunburst schema declares it

    def test_generate_image_appends_negative_prompt_clause(self) -> None:
        self.provider.generate_image(
            base.ImageGenerationRequest(
                model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="a barn", negative_prompt="clouds"
            )
        )
        self.assertIn("Do not include: clouds", self.transport.post_calls[0]["body"]["input"]["prompt"])

    def test_missing_api_key_raises_with_env_var_name_never_a_value(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = kie.KieProvider(transport=self.transport)
            with self.assertRaises(base.ProviderTaskError) as ctx:
                provider.generate_image(
                    base.ImageGenerationRequest(model_id="kie-gpt-image-2-5-sunburst-text-to-image", prompt="x")
                )
            self.assertIn("KIE_API_KEY", str(ctx.exception))
            self.assertEqual(len(self.transport.post_calls), 0)  # refused before any HTTP call


class GenerateVideoSeedanceFramePinningTests(_ProviderCase):
    """The central proof for this unit: two-image input_urls frame pinning,
    order preserved, registry-enforced cap."""

    def setUp(self) -> None:
        super().setUp()
        self.first_frame = "https://fixtures.example/scene-04-last-frame.png"
        self.last_frame = "https://fixtures.example/scene-05-first-frame.png"

    def test_two_image_input_urls_pins_first_and_last_frame_in_order(self) -> None:
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
        self.provider.generate_video(
            base.VideoGenerationRequest(
                model_id="kie-bytedance-seedance-1.5-pro", prompt="a boy rides a bike at sunset", duration_seconds=8
            )
        )
        self.assertNotIn("input_urls", self.transport.post_calls[0]["body"]["input"])

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
        self.assertEqual(self.transport.discovery_paths, [])  # refused before Skill 74 was even called


# ---------------------------------------------------------------------------
# Veo 3.1 on createTask: model id + input shape pinned to the LIVE KIE schema
# (GET /api/v1/models/veo-3-1/schema, 2026-10-05). The legacy ids veo3 /
# veo3_fast are NOT supported on createTask (schema lookup answers code 404).
# ---------------------------------------------------------------------------


class GenerateVideoVeoCreateTaskTests(_ProviderCase):
    def _submit(self, model_id: str = "kie-veo3-fast", **kw: Any) -> Dict[str, Any]:
        self.provider.generate_video(
            base.VideoGenerationRequest(model_id=model_id, prompt="a dog in a park", **kw),
            use_callback=False,
        )
        call = self.transport.post_calls[-1]
        self.assertTrue(call["url"].endswith("/api/v1/jobs/createTask"))
        return call["body"]

    def test_registry_never_resolves_legacy_veo_ids_for_createtask(self) -> None:
        for model_id in ("kie-veo3-fast", "kie-veo3-quality"):
            self.assertEqual(self.provider.registry.slug_for(model_id), "veo-3-1")

    def test_quality_id_is_refused_instead_of_silently_sending_the_fast_request(self) -> None:
        # createTask veo-3-1 documents no tier selector, so Quality would be
        # byte-identical to Fast. It is status=planned and must not submit.
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.provider.generate_video(
                base.VideoGenerationRequest(model_id="kie-veo3-quality", prompt="x", duration_seconds=8)
            )
        self.assertIn("planned", str(ctx.exception))
        self.assertEqual(len(self.transport.post_calls), 0)
        self.assertEqual(self.transport.discovery_paths, [])

    def test_text_to_video_body_matches_live_schema(self) -> None:
        body = self._submit(duration_seconds=8, aspect_ratio="9:16", resolution="1080p")
        self.assertEqual(body["model"], "veo-3-1")
        self.assertEqual(
            body["input"],
            {
                "prompt": "a dog in a park",
                "aspect_ratio": "9:16",
                "resolution": "1080p",
                "duration": 8,
                "generation_type": "TEXT_2_VIDEO",
            },
        )
        self.assertIsInstance(body["input"]["duration"], int)  # integer enum, not the string other models use
        self.assertNotIn("generate_audio", body["input"])  # no such field on veo-3-1
        self.assertNotIn("input_urls", body["input"])

    def test_two_frames_use_image_urls_in_order_not_input_urls(self) -> None:
        first, last = "https://fixtures.example/a.png", "https://fixtures.example/b.png"
        body = self._submit(duration_seconds=6, input_urls=(first, last))
        self.assertEqual(body["input"]["image_urls"], [first, last])
        self.assertNotIn("input_urls", body["input"])
        self.assertEqual(body["input"]["generation_type"], "FIRST_AND_LAST_FRAMES_2_VIDEO")

    def test_resolution_is_lowercased_for_4k(self) -> None:
        body = self._submit(model_id="kie-veo3-fast", duration_seconds=4, resolution="4K")
        self.assertEqual(body["input"]["resolution"], "4k")

    def test_out_of_schema_values_raise_before_any_http_call(self) -> None:
        for kw in (
            {"duration_seconds": 5},  # not in 4|6|8
            {"duration_seconds": 8, "resolution": "480p"},  # not in 720p|1080p|4k
            {"duration_seconds": 8, "aspect_ratio": "21:9"},  # not in 16:9|9:16|Auto
        ):
            with self.assertRaises(base.ProviderTaskError):
                self.provider.generate_video(
                    base.VideoGenerationRequest(model_id="kie-veo3-fast", prompt="x", **kw)
                )
        self.assertEqual(len(self.transport.post_calls), 0)

    def test_documented_recordinfo_resultjson_string_shape_is_decoded_and_saved(self) -> None:
        # Get Task Details doc: data.resultJson is a JSON STRING {"resultUrls": [...]}, state success|fail.
        body = {"code": 200, "data": {"state": "success", "resultJson": json.dumps({"resultUrls": ["https://fixtures.example/r.mp4"]})}}
        self.transport.queue_get(_resp(200, body))
        self.transport.queue_get(_resp(200, body))
        with tempfile.TemporaryDirectory() as tmp:
            self.provider.download_results("veo-task", str(Path(tmp) / "veo.mp4"))
        self.assertEqual(self.transport.download_calls, ["https://fixtures.example/r.mp4"])

    def test_callback_payload_urls_list_and_string_forms(self) -> None:
        ok = {"code": 200, "data": {"taskId": "t", "info": {"resultUrls": ["https://fixtures.example/a.mp4"]}}}
        self.assertEqual(kie.result_urls_from_callback(ok), ["https://fixtures.example/a.mp4"])
        as_string = {"code": 200, "data": {"info": {"resultUrls": "[\"https://fixtures.example/b.mp4\"]"}}}
        self.assertEqual(kie.result_urls_from_callback(as_string), ["https://fixtures.example/b.mp4"])
        self.assertEqual(kie.result_urls_from_callback({"code": 501, "data": {"taskId": "t"}}), [])


# ---------------------------------------------------------------------------
# get_task / download_results: Skill 74 wait + save
# ---------------------------------------------------------------------------


class TaskLifecycleTests(_ProviderCase):
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

    def test_get_task_maps_a_running_state_as_processing(self) -> None:
        self.transport.queue_get(_resp(200, {"code": 200, "data": {"state": "generating"}}))
        self.assertEqual(self.provider.get_task("t").status, "processing")

    def test_get_task_raises_on_an_api_error_instead_of_reporting_failed(self) -> None:
        self.transport.queue_get(_resp(200, {"code": 401, "msg": "unauthorized"}))
        with self.assertRaises(base.ProviderTaskError):
            self.provider.get_task("t")

    def test_cancel_task_always_returns_false_no_kie_cancel_endpoint(self) -> None:
        self.assertFalse(self.provider.cancel_task("any-task-id"))

    def test_download_results_decodes_resultjson_string_and_writes_file(self) -> None:
        for _ in range(2):  # Skill 74 wait, then save
            self.transport.queue_get(_resp(200, _load_fixture("record_info_success_video.json")))
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.provider.download_results("fixture-task-seedance-frame-pin-0001", str(Path(tmp) / "sub" / "clip.mp4"))
            self.assertEqual(len(paths), 1)
            written = Path(paths[0])
            self.assertEqual(written.name, "clip.mp4")
            self.assertEqual(written.read_bytes(), b"FIXTURE-DOWNLOAD-BYTES")
            self.assertEqual(
                self.transport.download_calls,
                ["https://tempfile.aiquickdraw.com/s/fixture-seedance-connector-clip.mp4"],
            )

    def test_download_results_into_a_directory_names_the_file_after_the_task(self) -> None:
        for _ in range(2):
            self.transport.queue_get(_resp(200, _load_fixture("record_info_success_video.json")))
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.provider.download_results("task-1", tmp + "/")
            self.assertEqual(Path(paths[0]).name, "task-1.mp4")

    def test_download_results_raises_on_failed_task(self) -> None:
        self.transport.queue_get(_resp(200, _load_fixture("record_info_failed.json")))
        with self.assertRaises(base.ProviderTaskError) as ctx:
            self.provider.download_results("fixture-task-failed-0001", "/tmp/should-not-be-written.mp4")
        self.assertIn("content policy violation", str(ctx.exception))
        self.assertEqual(self.transport.download_calls, [])


# ---------------------------------------------------------------------------
# estimate_cost: registry-resolved, honest about unpriced Seedance; live
# catalog price through Skill 74 first
# ---------------------------------------------------------------------------


class EstimateCostTests(_ProviderCase):
    def test_seedance_estimate_is_honestly_unverified(self) -> None:
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(model_id="kie-bytedance-seedance-1.5-pro", prompt="x", duration_seconds=8)
        )
        self.assertFalse(estimate.verified)
        self.assertIsNone(estimate.estimated_total)

    def test_veo3_fast_estimate_falls_back_to_labeled_dated_constants_when_live_unavailable(self) -> None:
        self.transport.catalog_code = 401  # live catalog unreadable -> Skill 74 only has its snapshot -> not a live read
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(model_id="kie-veo3-fast", prompt="x", duration_seconds=8, resolution="1080p")
        )
        # usd_per_clip: an 8s request must NOT be multiplied by 8.
        self.assertEqual(estimate.unit, "usd_per_clip")
        self.assertEqual(estimate.unit_price, 0.325)
        self.assertEqual(estimate.estimated_total, 0.325)
        self.assertIn("FALLBACK", estimate.note)

    def test_veo_live_price_is_read_first_through_skill74_and_wins_over_registry_constants(self) -> None:
        self.transport.catalog_models = [
            {"model": "veo-3-1", "taskType": ["Text to Video"], "pricingDesc": _VEO_PRICING_DESC.replace("$0.325", "$0.500")}
        ]
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(model_id="kie-veo3-fast", prompt="x", duration_seconds=8, resolution="1080p")
        )
        self.assertEqual(estimate.unit_price, 0.5)
        self.assertTrue(estimate.verified)
        self.assertIn("LIVE", estimate.note)
        self.assertEqual(self.transport.discovery_paths[0], "/api/v1/models")

    def test_veo_live_price_non_200_body_code_falls_back(self) -> None:
        self.transport.catalog_code = 401
        estimate = self.provider.estimate_cost(
            base.VideoGenerationRequest(model_id="kie-veo3-fast", prompt="x", duration_seconds=8, resolution="720p")
        )
        self.assertEqual(estimate.unit_price, 0.30)
        self.assertIn("FALLBACK", estimate.note)

    def test_parse_pricing_desc_matches_live_numbers(self) -> None:
        table = kie.parse_pricing_desc(_VEO_PRICING_DESC)
        self.assertEqual(table["fast"], {"720p": 0.30, "1080p": 0.325, "4k": 0.90})
        self.assertEqual(table["quality"], {"720p": 1.25, "1080p": 1.275, "4k": 1.85})
        self.assertEqual(table["lite"], {"720p": 0.15, "1080p": 0.175, "4k": 0.75})

    def test_registry_fallback_constants_equal_live_catalog_numbers(self) -> None:
        table = kie.parse_pricing_desc(_VEO_PRICING_DESC)
        for model_id, mode in (("kie-veo3-fast", "fast"), ("kie-veo3-quality", "quality")):
            self.assertEqual(self.provider.registry.get_model(model_id)["price"]["amount_by_resolution"], table[mode])

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
