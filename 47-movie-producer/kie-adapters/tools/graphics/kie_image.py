"""KIE.ai image generation adapter for OpenMontage.

Provides capability "image_generation" via the KIE.ai API using the
gpt-image-2-image-to-image model (for edit/reference jobs) or the
gpt-image-2-text-to-image model (for text-to-image jobs when no source
image is supplied).

INSTALL NOTE (Skill 47 INSTALL.md):
  This file is NOT part of OpenMontage source (AGPLv3).  It is an adapter
  authored by the fleet operator and shipped inside 47-movie-producer/
  kie-adapters/tools/graphics/.  The Skill 47 installer drops it into the
  client's cloned OpenMontage tree at:

      <openmontage_dir>/tools/graphics/kie_image.py

  OpenMontage's tool_registry auto-discovers every BaseTool subclass in
  tools/graphics/ at startup, so no registry edits are needed.

API references (do NOT modify without verifying against fleet receipts):
  - Endpoint shape:  07-kie-setup/EXAMPLES.md (Examples 1, 3, 10)
  - Model id:        46-kie-callback-relay/kie-slide-submitter.js
                       MODEL_TIMEOUTS gpt-image-2-image-to-image /
                       gpt-image-2-text-to-image
  - createTask body: same kie-slide-submitter.js _kiePost / body block
                       (model, input.prompt, input.image_input,
                        input.aspect_ratio, input.resolution,
                        input.output_format)
  - Poll endpoint:   GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=
  - Result URL path: .data.resultJson.resultUrls[0]
                     OR .data.resultJson.images[0].url  (nano-banana style)

Rate limits (source: 07-kie-setup/kie-setup-full.md, verified 2026-06-14):
  - Task creation: 20 per 10 seconds per account
  - Status query:  10 per second per API key

SAFETY RULES (enforced here, never relax):
  - KIE_API_KEY value is NEVER committed; only the env-var NAME appears.
  - No FAL_KEY, RUNWAY_API_KEY, HEYGEN_API_KEY, OPENAI_API_KEY, etc. are
    read here; the native paid providers stay UNAVAILABLE on the client box.
  - No OpenMontage source is copied or modified.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

# ---------------------------------------------------------------------------
# KIE.ai API constants (verified against fleet scripts)
# ---------------------------------------------------------------------------
_KIE_API_BASE = "https://api.kie.ai"
_CREATE_TASK_URL = f"{_KIE_API_BASE}/api/v1/jobs/createTask"
_RECORD_INFO_URL = f"{_KIE_API_BASE}/api/v1/jobs/recordInfo"

# Model ids verified in 46-kie-callback-relay/kie-slide-submitter.js
# MODEL_TIMEOUTS block (2026-06-14).
_MODEL_EDIT = "gpt-image-2-image-to-image"   # when source image(s) provided
_MODEL_TEXT = "gpt-image-2-text-to-image"    # when no source image

# Poll config (stay within 10 req/s status-query limit)
_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 300   # 5 min; matches kie-slide-submitter MODEL_TIMEOUTS


def _decode_result_json(raw: Any) -> dict[str, Any]:
    """Normalise KIE's ``resultJson`` field into a parsed dict.

    KIE's recordInfo poll endpoint (/api/v1/jobs/recordInfo) returns
    ``resultJson`` as a JSON-ENCODED STRING — a string whose contents are
    themselves JSON — NOT an already-parsed object.  The original adapter read
    it as if it were already a dict and called ``.get()`` on the raw string, so
    the result URL was never extracted on a client box (confirmed live against
    api.kie.ai during the v14.1.x render proof).  This mirrors the fleet
    reference script generate-celebration-video.sh, which pipes
    ``jq -r '.data.resultJson'`` (raw string) into a SECOND ``jq`` to parse it.

    Defensive contract:
      - str   -> json.loads() (returns {} if it does not decode to a dict)
      - dict  -> used as-is (tolerate an already-parsed object)
      - other -> {} (None, list, number, etc.)
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(raw, dict):
        return raw
    return {}


class KieImage(BaseTool):
    """KIE.ai image generation — fleet-standard provider for all client boxes.

    Routes through KIE.ai so that no FAL/Runway/HeyGen/OpenAI/Google image
    keys are needed on the client box.  The image_selector auto-discovers
    this tool and prefers it when KIE_API_KEY is set and other paid providers
    are UNAVAILABLE (their keys are absent).

    Supports both text-to-image (gpt-image-2-text-to-image) and
    image-edit/reference jobs (gpt-image-2-image-to-image) with up to 8
    source images at 2K resolution, 16:9 aspect ratio.
    """

    name = "kie_image"
    version = "1.0.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "kie"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:KIE_API_KEY"]
    install_instructions = (
        "Set KIE_API_KEY to your KIE.ai API key in the .env file at the "
        "root of the OpenMontage clone.  Obtain a key at https://kie.ai — "
        "this is the ONLY image-generation API key needed on the client box."
    )
    agent_skills = ["kie-setup"]

    capabilities = [
        "text_to_image",
        "image_edit",
        "image_to_image",
        "reference_image_generation",
    ]
    supports = {
        "image_edit": True,          # the image_selector uses this to route edit jobs here
        "text_to_image": True,
        "image_to_image": True,
        "custom_aspect_ratio": True,
        "resolution_2k": True,
    }
    best_for = [
        "fleet-standard image generation at 2K resolution",
        "brand-consistent image editing with up to 8 reference images",
        "16:9 aspect ratio output for video and presentation assets",
        "high success rate on client production pipelines (~$0.05/image)",
    ]
    not_good_for = [
        "free/zero-key generation (requires KIE_API_KEY)",
        "offline generation",
        "very large batches (respect 20-per-10s creation rate limit)",
    ]

    # Bias the scoring engine toward this provider: 0.90 > flux (0.85),
    # so Kie wins when both are available — but the client box only sets
    # KIE_API_KEY, so native paid providers are UNAVAILABLE in practice.
    quality_score: float = 0.90
    latency_p50_seconds: float = 30.0

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Image generation or editing prompt.",
            },
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Up to 8 reference image URLs.  When provided, the adapter "
                    "uses gpt-image-2-image-to-image (edit/reference mode).  "
                    "Each URL must be publicly reachable by KIE servers; "
                    "upload local files first via the KIE base64-upload API."
                ),
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Local file paths to source images.  The adapter reads "
                    "and encodes them, then uploads via the KIE base64-upload "
                    "API to obtain public URLs before the createTask call."
                ),
            },
            "image_url": {
                "type": "string",
                "description": "Single source image URL (convenience alias for image_urls with one item).",
            },
            "image_path": {
                "type": "string",
                "description": "Single local source image path (convenience alias for image_paths with one item).",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                "default": "16:9",
                "description": "Output aspect ratio.  KIE default is 16:9.",
            },
            "resolution": {
                "type": "string",
                "enum": ["2K", "1080p", "720p"],
                "default": "2K",
                "description": "Output resolution tier.",
            },
            "output_format": {
                "type": "string",
                "enum": ["png", "jpg", "webp"],
                "default": "png",
            },
            "output_path": {
                "type": "string",
                "description": "Local path to save the downloaded image.",
            },
            # Pass-through keys forwarded by image_selector — accepted silently
            "generation_mode": {"type": "string"},
            "negative_prompt": {"type": "string"},
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "seed": {"type": "integer"},
            "n": {"type": "integer"},
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "provider": {"type": "string", "const": "kie"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "output": {"type": "string", "description": "Local path to downloaded image"},
            "kie_task_id": {"type": "string", "description": "KIE task ID (render proof receipt)"},
            "kie_result_url": {"type": "string", "description": "Remote KIE result URL (render proof receipt)"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2,
        backoff_seconds=5.0,
        retryable_errors=["rate_limit", "timeout", "500"],
    )
    idempotency_key_fields = ["prompt", "aspect_ratio", "resolution"]
    side_effects = [
        "calls api.kie.ai createTask API",
        "downloads generated image to output_path",
    ]
    user_visible_verification = [
        "Inspect the downloaded image for prompt adherence and quality",
        "Confirm kie_task_id and kie_result_url are present in result.data (render proof)",
    ]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _get_api_key(self) -> str | None:
        return os.environ.get("KIE_API_KEY")

    def get_status(self) -> ToolStatus:
        """AVAILABLE only when KIE_API_KEY is set in the environment."""
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        """Approximate KIE image cost (credits, treated as USD equivalent)."""
        resolution = inputs.get("resolution", "2K")
        if resolution == "2K":
            return 0.05
        return 0.03

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 30.0

    # ------------------------------------------------------------------
    # Reference-image upload helpers
    # ------------------------------------------------------------------

    def _upload_local_image(self, path_str: str, api_key: str) -> str:
        """Upload a local file to KIE's base64-upload endpoint.

        Returns a publicly reachable KIE-hosted URL.
        Raises RuntimeError on failure.

        Endpoint: POST https://kieai.redpandaai.co/api/file-base64-upload
        (verified in 07-kie-setup/EXAMPLES.md Example 7 + generate-celebration-video.sh)
        """
        import base64
        import requests

        path = Path(path_str)
        if not path.exists():
            raise RuntimeError(f"kie_image: local reference file not found: {path}")

        # Detect MIME type
        suffix = path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/png")

        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        data_uri = f"data:{mime};base64,{b64}"

        payload = {
            "base64Data": data_uri,
            "uploadPath": "images/openmontage",
            "fileName": path.name,
        }
        resp = requests.post(
            "https://kieai.redpandaai.co/api/file-base64-upload",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        url = (
            body.get("data", {}).get("downloadUrl")
            or body.get("downloadUrl")
            or body.get("data", {}).get("url")
        )
        if not url or not url.startswith("http"):
            raise RuntimeError(f"kie_image: base64 upload returned no usable URL: {body}")
        return url

    def _resolve_image_inputs(
        self, inputs: dict[str, Any], api_key: str
    ) -> list[str]:
        """Collect and normalise all source image references into public URLs.

        Merges image_url / image_path / image_urls / image_paths, uploads any
        local files, and returns a de-duplicated list of public https URLs.
        Returns an empty list when no source images are provided (text-to-image).
        """
        urls: list[str] = []

        # Collect URLs first (no upload needed)
        single_url = inputs.get("image_url")
        if single_url:
            urls.append(single_url)
        for u in inputs.get("image_urls") or []:
            urls.append(u)

        # Collect local paths and upload each
        paths: list[str] = []
        single_path = inputs.get("image_path")
        if single_path:
            paths.append(single_path)
        for p in inputs.get("image_paths") or []:
            paths.append(p)

        for local_path in paths:
            public_url = self._upload_local_image(local_path, api_key)
            urls.append(public_url)

        # De-duplicate while preserving order; cap at 8 (KIE limit)
        seen: set[str] = set()
        result: list[str] = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result[:8]

    # ------------------------------------------------------------------
    # API call helpers
    # ------------------------------------------------------------------

    def _create_task(self, body: dict, api_key: str) -> str:
        """POST createTask and return the taskId string.

        Endpoint: POST https://api.kie.ai/api/v1/jobs/createTask
        Body shape verified against 46-kie-callback-relay/kie-slide-submitter.js
        and 07-kie-setup/EXAMPLES.md.
        """
        import requests

        resp = requests.post(
            _CREATE_TASK_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"kie_image createTask error: {data}")
        task_id = data.get("data", {}).get("taskId")
        if not task_id:
            raise RuntimeError(f"kie_image createTask returned no taskId: {data}")
        return task_id

    def _poll_task(self, task_id: str, api_key: str) -> str:
        """Poll GET recordInfo until success; return the result URL.

        Endpoint: GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>
        Result path: .data.resultJson.resultUrls[0]
                  OR .data.resultJson.images[0].url
        Verified against 07-kie-setup/EXAMPLES.md Example 2.
        """
        import requests

        elapsed = 0
        headers = {"Authorization": f"Bearer {api_key}"}

        while elapsed < _POLL_TIMEOUT_SECONDS:
            time.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            resp = requests.get(
                _RECORD_INFO_URL,
                params={"taskId": task_id},
                headers=headers,
                timeout=15,
            )
            # Treat 5xx as transient
            if resp.status_code >= 500:
                continue
            resp.raise_for_status()
            body = resp.json()

            state = (body.get("data") or {}).get("state", "")
            if state == "success":
                # resultJson arrives as a JSON-ENCODED STRING from KIE; decode
                # it before reading the result URL(s).  Tolerates an already-
                # parsed dict.  (generate-celebration-video.sh pipes
                # `jq -r .data.resultJson` into a SECOND jq to parse it.)
                result_json = _decode_result_json((body.get("data") or {}).get("resultJson"))
                # Try resultUrls first (primary path per generate-celebration-video.sh)
                result_urls = result_json.get("resultUrls") or []
                if result_urls:
                    return result_urls[0]
                # Fallback to images[].url (nano-banana-pro style per EXAMPLES.md)
                images = result_json.get("images") or []
                if images:
                    return images[0].get("url", "")
                raise RuntimeError(
                    f"kie_image: task {task_id} succeeded but no result URL found: {result_json}"
                )
            if state in ("fail", "failed", "error"):
                fail_msg = (body.get("data") or {}).get("failMsg") or body.get("msg") or "unknown"
                raise RuntimeError(f"kie_image: task {task_id} failed: {fail_msg}")
            # Still pending / processing — continue polling

        raise RuntimeError(
            f"kie_image: task {task_id} timed out after {_POLL_TIMEOUT_SECONDS}s"
        )

    def _download_image(self, url: str, output_path: Path) -> None:
        """Download the generated image bytes to output_path."""
        import requests

        output_path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        """Generate or edit an image via KIE.ai and download the result.

        Request body shape (verified against kie-slide-submitter.js body
        block and 07-kie-setup/EXAMPLES.md):

          {
            "model": "gpt-image-2-image-to-image" | "gpt-image-2-text-to-image",
            "input": {
              "prompt": <str>,
              "image_input": [<url>, ...],   # only when source images provided
              "aspect_ratio": "16:9",
              "resolution": "2K",
              "output_format": "png"
            }
          }

        Returns a ToolResult with data keys:
          provider, model, prompt, output,
          kie_task_id   (render proof receipt),
          kie_result_url (render proof receipt).
        """
        import requests

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error=(
                    "KIE_API_KEY is not set. " + self.install_instructions
                ),
            )

        start = time.time()
        prompt = inputs.get("prompt", "")
        # FIX-IMG-09 (i): the adapter accepted `negative_prompt` in its input
        # schema but silently dropped it — it never reached the createTask body.
        # gpt-image-2 has no dedicated negative-prompt field, so forward it
        # in-prompt (the documented way to steer it away from unwanted content):
        # append a "Do not include:" clause so the exclusion is actually honored
        # instead of being silently ignored.
        negative_prompt = str(inputs.get("negative_prompt", "") or "").strip()
        if negative_prompt:
            prompt = f"{prompt} Do not include: {negative_prompt}"
        aspect_ratio = inputs.get("aspect_ratio", "16:9")
        resolution = inputs.get("resolution", "2K")
        output_format = inputs.get("output_format", "png")
        output_path = Path(inputs.get("output_path", f"kie_generated.{output_format}"))

        # Resolve source images (upload local files if needed)
        try:
            source_urls = self._resolve_image_inputs(inputs, api_key)
        except Exception as exc:
            return ToolResult(success=False, error=f"kie_image: reference upload failed: {exc}")

        # Select model based on whether source images are present
        model = _MODEL_EDIT if source_urls else _MODEL_TEXT

        # Build createTask body (verified against kie-slide-submitter.js)
        task_input: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "output_format": output_format,
        }
        if source_urls:
            task_input["image_input"] = source_urls

        body = {"model": model, "input": task_input}

        try:
            task_id = self._create_task(body, api_key)
            result_url = self._poll_task(task_id, api_key)
            self._download_image(result_url, output_path)
        except requests.HTTPError as exc:
            return ToolResult(success=False, error=f"kie_image HTTP error: {exc}")
        except RuntimeError as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"kie_image unexpected error: {exc}")

        return ToolResult(
            success=True,
            data={
                "provider": "kie",
                "model": model,
                "prompt": prompt,
                "output": str(output_path),
                "kie_task_id": task_id,          # render proof receipt
                "kie_result_url": result_url,    # render proof receipt
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
