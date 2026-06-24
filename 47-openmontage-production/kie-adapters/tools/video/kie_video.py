"""KIE.ai video generation adapter for OpenMontage.

Provides capability "video_generation" via the KIE.ai API.

DEFAULT model:   gemini-omni-video (image-guided, 4-8s, aspect_ratio always
                 required, duration MUST be a STRING — the verified 422 fix).
FALLBACK model:  veo3_fast (text-to-video, durations 4/6/8s only, different
                 endpoint and poll URL).

Both model paths are verified against the fleet script:
  37-zhc-closeout/scripts/generate-celebration-video.sh
(lines 420-612, the Gemini Omni submit/poll + Veo submit/poll functions,
including the string-duration 422 fix, the aspect_ratio always-inject rule,
the image-fetch transient retry, and the veo3_fast fallback path).

INSTALL NOTE (Skill 47 INSTALL.md):
  This file is NOT part of OpenMontage source (AGPLv3).  It is an adapter
  authored by the fleet operator and shipped inside 47-openmontage-production/
  kie-adapters/tools/video/.  The Skill 47 installer drops it into the
  client's cloned OpenMontage tree at:

      <openmontage_dir>/tools/video/kie_video.py

  OpenMontage's tool_registry auto-discovers every BaseTool subclass in
  tools/video/ at startup, so no registry edits are needed.

SAFETY RULES (enforced here, never relax):
  - KIE_API_KEY value is NEVER committed; only the env-var NAME appears.
  - No FAL_KEY, RUNWAY_API_KEY, HEYGEN_API_KEY, etc. are read here.
  - duration for gemini-omni-video is ALWAYS passed as a STRING (not int)
    to avoid a 422 "Aspect ratio only supports…" / body-validation error
    (verified 2026-05-27, generate-celebration-video.sh line 432-434).
  - aspect_ratio is ALWAYS included in the request body for gemini-omni-video
    (KIE rejects requests without it, v10.X.4 fix,
     generate-celebration-video.sh line 421-431).
  - No OpenMontage source is copied or modified.
"""

from __future__ import annotations

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
# KIE.ai API constants (verified against generate-celebration-video.sh)
# ---------------------------------------------------------------------------
_KIE_API_BASE = "https://api.kie.ai"

# gemini-omni-video: uses /jobs/createTask + /jobs/recordInfo
_GEMINI_CREATE_URL  = f"{_KIE_API_BASE}/api/v1/jobs/createTask"
_GEMINI_POLL_URL    = f"{_KIE_API_BASE}/api/v1/jobs/recordInfo"  # ?taskId=<id>

# veo3 / veo3_fast: uses /veo/generate + /veo/record-info
# (verified 07-kie-setup/EXAMPLES.md Example 4 + generate-celebration-video.sh lines 540-559)
_VEO_CREATE_URL = f"{_KIE_API_BASE}/api/v1/veo/generate"
_VEO_POLL_URL   = f"{_KIE_API_BASE}/api/v1/veo/record-info"    # ?taskId=<id>

# Poll configuration (stay within 10 req/s status-query limit)
_POLL_INTERVAL_SECONDS = 10
_POLL_TIMEOUT_SECONDS  = 1800   # 30 min; matches ZHC_VIDEO_POLL_TIMEOUT_SEC default

# Valid duration values per model (generate-celebration-video.sh lines 388-415)
_GEMINI_VALID_DURATIONS = {"4", "5", "6", "7", "8"}
_VEO_VALID_DURATIONS    = {"4", "6", "8"}

# Default model/duration (mirrors generate-celebration-video.sh defaults)
_DEFAULT_MODEL    = "gemini-omni-video"
_FALLBACK_MODEL   = "veo3_fast"
_DEFAULT_DURATION = "8"   # STRING — the 422 fix

# Valid aspect ratios for KIE Gemini Omni (generate-celebration-video.sh line 425)
_VALID_ASPECT_RATIOS = {"16:9", "9:16"}


class KieVideo(BaseTool):
    """KIE.ai video generation — fleet-standard video provider for client boxes.

    Default model: gemini-omni-video (image-guided).
    Fallback model: veo3_fast (text-to-video, different endpoint).

    Routes through KIE.ai so that no FAL/Runway/HeyGen/Minimax/Kling keys
    are needed on the client box.  The video_selector auto-discovers this tool
    and prefers it when KIE_API_KEY is set and other paid providers are
    UNAVAILABLE (their keys are absent).

    The gemini-omni-video path accepts reference image URLs so brand visuals
    (org-chart, logo) carry through into the rendered clip — the same pattern
    used for ZHC celebration videos across the fleet (Skill 37).
    """

    name = "kie_video"
    version = "1.0.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "kie"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:KIE_API_KEY"]
    install_instructions = (
        "Set KIE_API_KEY to your KIE.ai API key in the .env file at the "
        "root of the OpenMontage clone.  This is the ONLY video-generation "
        "API key needed on the client box."
    )
    agent_skills = ["kie-setup"]

    capabilities = [
        "text_to_video",
        "image_to_video",
        "image_guided_video",
    ]
    supports = {
        "image_to_video": True,
        "text_to_video": True,
        "image_guided_video": True,   # gemini-omni-video reference images
        "native_audio": True,
        "generate_audio": True,
    }
    best_for = [
        "brand-consistent videos with reference images (gemini-omni-video)",
        "image-to-video generation from org charts and infographics",
        "fleet-standard production video via KIE.ai at ~$0.50-$1.00/clip",
        "text-to-video fallback via veo3_fast",
    ]
    not_good_for = [
        "free/zero-key generation (requires KIE_API_KEY)",
        "offline generation",
        "durations outside 4/6/8s (Veo) or 4-8s (Gemini Omni)",
    ]
    fallback_tools = ["kie_video"]  # internal fallback: gemini-omni -> veo3_fast

    # Bias the scoring engine toward this provider
    quality_score: float = 0.90
    latency_p50_seconds: float = 120.0

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Video generation prompt.",
            },
            "model": {
                "type": "string",
                "enum": ["gemini-omni-video", "veo3", "veo3_fast"],
                "default": "gemini-omni-video",
                "description": (
                    "KIE model to use.  gemini-omni-video is the default and "
                    "supports reference images (image-guided generation).  "
                    "veo3 / veo3_fast use a different endpoint; they are "
                    "text-to-video only (no image references)."
                ),
            },
            "duration": {
                "type": "string",
                "description": (
                    "Clip duration in seconds as a STRING.  "
                    "gemini-omni-video accepts '4'-'8'; veo3/veo3_fast accept '4', '6', or '8'.  "
                    "MUST be a string, not an integer (422 fix, verified 2026-05-27)."
                ),
                "default": "8",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16"],
                "default": "16:9",
                "description": (
                    "Output aspect ratio.  ALWAYS included in the request body "
                    "for gemini-omni-video (KIE 422 fix, v10.X.4)."
                ),
            },
            "generate_audio": {
                "type": "boolean",
                "default": True,
                "description": "Include synchronized audio in the generated clip.",
            },
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Reference image URLs for gemini-omni-video.  Each URL must "
                    "be publicly reachable by KIE/Gemini servers.  Upload local "
                    "files first (see kie_image._upload_local_image).  "
                    "Ignored for veo3/veo3_fast (text-to-video only)."
                ),
            },
            "image_url": {
                "type": "string",
                "description": "Single reference image URL (convenience alias for image_urls).",
            },
            # video_selector pass-through keys
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alias for image_urls (video_selector compat).",
            },
            "output_path": {
                "type": "string",
                "description": "Local path to save the downloaded MP4.",
            },
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "provider": {"type": "string", "const": "kie"},
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "output": {"type": "string", "description": "Local path to downloaded MP4"},
            "kie_task_id": {"type": "string", "description": "KIE task ID (render proof receipt)"},
            "kie_result_url": {"type": "string", "description": "Remote KIE result URL (render proof receipt)"},
            "has_audio": {"type": "boolean"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2,
        backoff_seconds=10.0,
        retryable_errors=["rate_limit", "timeout", "image_fetch_failed"],
    )
    idempotency_key_fields = ["prompt", "model", "duration", "aspect_ratio"]
    side_effects = [
        "calls api.kie.ai createTask or veo/generate API",
        "downloads generated video to output_path",
    ]
    user_visible_verification = [
        "Watch the downloaded MP4 for visual quality and motion",
        "Confirm kie_task_id and kie_result_url are present in result.data (render proof)",
        "Run: ffprobe -v error -show_entries format=duration,stream=codec_type <output>.mp4",
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
        """Approximate KIE video cost (credits, treated as USD equivalent)."""
        model = inputs.get("model", _DEFAULT_MODEL)
        duration_str = str(inputs.get("duration", _DEFAULT_DURATION))
        try:
            duration = int(duration_str)
        except ValueError:
            duration = 8
        if "fast" in model:
            return 0.10 * duration
        return 0.20 * duration

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        model = inputs.get("model", _DEFAULT_MODEL)
        if "fast" in model:
            return 60.0
        return 180.0

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------

    def _resolve_image_urls(self, inputs: dict[str, Any]) -> list[str]:
        """Collect reference image URLs from all recognised input keys."""
        urls: list[str] = []
        single = inputs.get("image_url")
        if single:
            urls.append(single)
        for u in inputs.get("image_urls") or []:
            urls.append(u)
        for u in inputs.get("reference_image_urls") or []:
            urls.append(u)
        # De-duplicate preserving order; only public http(s) URLs pass through
        seen: set[str] = set()
        result: list[str] = []
        for u in urls:
            if u not in seen and (u.startswith("https://") or u.startswith("http://")):
                seen.add(u)
                result.append(u)
        return result

    def _snap_duration(self, raw: str, model: str) -> str:
        """Snap duration to a model-valid string value.

        gemini-omni-video: accepts 4-8 (passed as STRING per 422 fix).
        veo3 / veo3_fast: accepts 4, 6, 8 (as STRING).
        """
        if model == "gemini-omni-video":
            if raw in _GEMINI_VALID_DURATIONS:
                return raw
            return _DEFAULT_DURATION
        else:
            if raw in _VEO_VALID_DURATIONS:
                return raw
            # Snap to nearest valid Veo duration
            try:
                n = int(raw)
                if n <= 4:
                    return "4"
                if n <= 6:
                    return "6"
                return "8"
            except ValueError:
                return _DEFAULT_DURATION

    def _snap_aspect(self, raw: str) -> str:
        if raw in _VALID_ASPECT_RATIOS:
            return raw
        return "16:9"

    # ------------------------------------------------------------------
    # Gemini Omni Video path (POST /api/v1/jobs/createTask)
    # ------------------------------------------------------------------

    def _submit_gemini_omni(
        self,
        prompt: str,
        duration: str,
        aspect_ratio: str,
        image_urls: list[str],
        generate_audio: bool,
        api_key: str,
    ) -> str:
        """Submit a gemini-omni-video job; return the taskId.

        Body shape (verified against generate-celebration-video.sh
        submit_gemini_omni(), lines 462-483):

          {
            "model": "gemini-omni-video",
            "input": {
              "prompt": <str>,
              "image_urls": [<url>, ...],   # when reference images present
              "duration": "<str>",           # MUST be a string (422 fix)
              "aspect_ratio": "16:9",        # ALWAYS included (422 fix)
              "generate_audio": true
            }
          }
        """
        import requests

        task_input: dict[str, Any] = {
            "prompt": prompt,
            "duration": duration,            # STRING — the verified 422 fix
            "aspect_ratio": aspect_ratio,    # ALWAYS present — the verified 422 fix
            "generate_audio": generate_audio,
        }
        if image_urls:
            task_input["image_urls"] = image_urls

        body = {"model": "gemini-omni-video", "input": task_input}

        resp = requests.post(
            _GEMINI_CREATE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = (data.get("data") or {}).get("taskId") or data.get("taskId")
        if not task_id:
            raise RuntimeError(f"kie_video gemini-omni-video submit: no taskId: {data}")
        return task_id

    def _poll_gemini_omni(self, task_id: str, api_key: str) -> str:
        """Poll GET /api/v1/jobs/recordInfo until success; return result URL.

        Handles transient image-fetch failures (rc=2 signal in the fleet script)
        by raising a retriable error so the caller can re-submit.

        Verified against generate-celebration-video.sh poll_gemini_omni(),
        lines 486-529.
        """
        import requests

        elapsed = 0
        headers = {"Authorization": f"Bearer {api_key}"}

        while elapsed < _POLL_TIMEOUT_SECONDS:
            time.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            resp = requests.get(
                _GEMINI_POLL_URL,
                params={"taskId": task_id},
                headers=headers,
                timeout=15,
            )
            if resp.status_code >= 500:
                continue
            resp.raise_for_status()
            body = resp.json()

            data_block = body.get("data") or {}
            state = data_block.get("state", "")

            if state == "success":
                result_json = data_block.get("resultJson") or {}
                result_urls = result_json.get("resultUrls") or []
                if result_urls:
                    return result_urls[0]
                # Fallbacks (mirrors poll_gemini_omni jq expressions)
                video_url = (
                    result_json.get("videoUrl")
                    or result_json.get("url")
                    or result_json.get("resultUrl")
                    or ""
                )
                if video_url:
                    return video_url
                raise RuntimeError(
                    f"kie_video: gemini-omni-video task {task_id} succeeded "
                    f"but no result URL found: {result_json}"
                )

            if state in ("fail", "failed", "error"):
                fail_msg = data_block.get("failMsg") or body.get("msg") or "unknown"
                # Transient image-fetch failure — flag for re-submit
                # (mirrors generate-celebration-video.sh lines 506-514)
                if any(kw in fail_msg.lower() for kw in (
                    "image fetch failed", "fetch image", "failed to fetch",
                    "failed to download", "failed to load",
                )):
                    raise _ImageFetchError(
                        f"kie_video: gemini-omni-video transient image-fetch "
                        f"failure for task {task_id}: {fail_msg}"
                    )
                raise RuntimeError(
                    f"kie_video: gemini-omni-video task {task_id} failed: {fail_msg}"
                )
            # Pending / processing — keep polling

        raise RuntimeError(
            f"kie_video: gemini-omni-video task {task_id} timed out "
            f"after {_POLL_TIMEOUT_SECONDS}s"
        )

    # ------------------------------------------------------------------
    # Veo fallback path (POST /api/v1/veo/generate)
    # ------------------------------------------------------------------

    def _submit_veo(
        self,
        model: str,
        prompt: str,
        duration: str,
        aspect_ratio: str,
        generate_audio: bool,
        api_key: str,
    ) -> str:
        """Submit a veo3 / veo3_fast job; return the taskId.

        Body shape (verified against generate-celebration-video.sh
        submit_veo(), lines 534-545 + 07-kie-setup/EXAMPLES.md Example 4):

          {
            "model": "veo3_fast",
            "prompt": <str>,
            "aspect_ratio": "16:9",
            "duration": <int>,         # NOTE: veo endpoint takes integer
            "generate_audio": true
          }

        NOTE: the veo/generate body differs from the createTask body — it has
        top-level 'prompt' (not nested under 'input') and takes duration as an
        integer (not a string).  This is NOT a typo; both behaviours are
        verified against the fleet script (submit_veo uses --argjson for
        duration, which emits an integer JSON value).
        """
        import requests

        try:
            duration_int = int(duration)
        except ValueError:
            duration_int = 8

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration_int,
            "generate_audio": generate_audio,
        }

        resp = requests.post(
            _VEO_CREATE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = (data.get("data") or {}).get("taskId") or data.get("taskId")
        if not task_id:
            raise RuntimeError(f"kie_video veo submit: no taskId: {data}")
        return task_id

    def _poll_veo(self, task_id: str, api_key: str) -> str:
        """Poll GET /api/v1/veo/record-info until success; return result URL.

        Treats HTTP 5xx and body errorCode=500 as transient (up to 3 times).

        Verified against generate-celebration-video.sh poll_veo(), lines 547-612.
        """
        import requests

        elapsed = 0
        headers = {"Authorization": f"Bearer {api_key}"}
        consecutive_500 = 0

        while elapsed < _POLL_TIMEOUT_SECONDS:
            time.sleep(_POLL_INTERVAL_SECONDS)
            elapsed += _POLL_INTERVAL_SECONDS

            resp = requests.get(
                _VEO_POLL_URL,
                params={"taskId": task_id},
                headers=headers,
                timeout=15,
            )
            http_code = resp.status_code
            body_err_code = ""
            try:
                body_json = resp.json()
                body_err_code = str(
                    (body_json.get("data") or {}).get("errorCode")
                    or body_json.get("errorCode")
                    or ""
                )
            except Exception:
                body_json = {}

            # Transient 5xx handling (mirrors poll_veo consecutive_500 logic)
            if http_code >= 500 or body_err_code == "500":
                consecutive_500 += 1
                if consecutive_500 > 3:
                    raise RuntimeError(
                        f"kie_video: Veo poll for {task_id}: "
                        "4 consecutive 500 errors; giving up"
                    )
                time.sleep(30)
                elapsed += 30
                continue
            consecutive_500 = 0

            if http_code >= 400:
                raise RuntimeError(
                    f"kie_video: Veo poll HTTP {http_code} for {task_id}"
                )

            resp.raise_for_status()

            data_block = body_json.get("data") or {}
            success_flag = str(data_block.get("successFlag") or "")

            if success_flag in ("1",):
                # Extract result URL (mirrors poll_veo jq expressions)
                response_block = data_block.get("response") or {}
                result_urls = response_block.get("resultUrls") or []
                if result_urls:
                    return result_urls[0]
                video_url = (
                    response_block.get("videoUrl")
                    or data_block.get("resultJson")
                    or ""
                )
                if isinstance(video_url, dict):
                    video_url = (
                        video_url.get("resultUrls", [None])[0]
                        or video_url.get("videoUrl")
                        or video_url.get("url")
                        or ""
                    )
                if video_url:
                    return str(video_url)
                raise RuntimeError(
                    f"kie_video: Veo task {task_id} succeeded but no result URL: {data_block}"
                )

            if success_flag in ("-1",):
                fail_msg = (
                    data_block.get("errorMessage")
                    or data_block.get("failMsg")
                    or body_json.get("msg")
                    or "unknown"
                )
                raise RuntimeError(f"kie_video: Veo task {task_id} failed: {fail_msg}")
            # Pending — keep polling

        raise RuntimeError(
            f"kie_video: Veo task {task_id} timed out after {_POLL_TIMEOUT_SECONDS}s"
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download_video(self, url: str, output_path: Path) -> None:
        """Download the generated video bytes to output_path.

        CRITICAL: downloads to disk rather than using the remote URL directly,
        because tempfile CDN URLs return content-disposition: attachment and
        cannot be embedded inline (e.g. by Telegram).  Always download first.
        (generate-celebration-video.sh lines 688-697)
        """
        import requests

        output_path.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(url, timeout=180, allow_redirects=True)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        """Generate a video via KIE.ai and download the MP4.

        Model routing:
          - gemini-omni-video: POST /api/v1/jobs/createTask,
              input.duration as STRING, aspect_ratio always set,
              image_urls accepted for image-guided generation.
              Poll: GET /api/v1/jobs/recordInfo?taskId=
          - veo3 / veo3_fast: POST /api/v1/veo/generate,
              duration as integer, no image references.
              Poll: GET /api/v1/veo/record-info?taskId=
          - On gemini-omni-video image-fetch transient failure, one automatic
              retry (re-host is the caller's responsibility for image freshness;
              here we simply retry with the same URLs).
          - On gemini-omni-video total failure, falls back to veo3_fast.

        Returns a ToolResult with data keys:
          provider, model, prompt, output,
          kie_task_id   (render proof receipt),
          kie_result_url (render proof receipt),
          has_audio.
        """
        import requests

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="KIE_API_KEY is not set. " + self.install_instructions,
            )

        start = time.time()
        prompt = inputs.get("prompt", "")
        model = inputs.get("model", _DEFAULT_MODEL)
        raw_duration = str(inputs.get("duration", _DEFAULT_DURATION))
        aspect_ratio = self._snap_aspect(inputs.get("aspect_ratio", "16:9"))
        generate_audio = bool(inputs.get("generate_audio", True))
        output_path = Path(inputs.get("output_path", "kie_video_output.mp4"))

        duration = self._snap_duration(raw_duration, model)
        image_urls = self._resolve_image_urls(inputs)

        task_id: str = ""
        result_url: str = ""
        used_model = model

        # --- Attempt gemini-omni-video (primary) ---
        if model == "gemini-omni-video":
            max_gemini_attempts = 2
            for attempt in range(1, max_gemini_attempts + 1):
                try:
                    task_id = self._submit_gemini_omni(
                        prompt, duration, aspect_ratio, image_urls,
                        generate_audio, api_key
                    )
                    result_url = self._poll_gemini_omni(task_id, api_key)
                    used_model = "gemini-omni-video"
                    break
                except _ImageFetchError:
                    # Transient image-fetch: retry once (generate-celebration-video.sh
                    # retries with re-hosted refs; here we retry with the same refs
                    # since the adapter does not own the upload state).
                    if attempt < max_gemini_attempts:
                        time.sleep(5)
                        continue
                    # Exhausted gemini retries; fall through to veo3_fast
                    break
                except requests.HTTPError as exc:
                    if attempt < max_gemini_attempts:
                        time.sleep(5)
                        continue
                    # Fall through to veo3_fast
                    break
                except RuntimeError:
                    if attempt < max_gemini_attempts:
                        time.sleep(5)
                        continue
                    # Fall through to veo3_fast
                    break

            # --- Fallback to veo3_fast if gemini-omni-video failed ---
            if not result_url:
                veo_duration = self._snap_duration(_DEFAULT_DURATION, _FALLBACK_MODEL)
                try:
                    task_id = self._submit_veo(
                        _FALLBACK_MODEL, prompt, veo_duration, aspect_ratio,
                        generate_audio, api_key
                    )
                    result_url = self._poll_veo(task_id, api_key)
                    used_model = _FALLBACK_MODEL
                except Exception as exc:
                    return ToolResult(
                        success=False,
                        error=(
                            f"kie_video: gemini-omni-video failed and "
                            f"veo3_fast fallback also failed: {exc}"
                        ),
                    )

        # --- Direct veo3 / veo3_fast path ---
        else:
            veo_duration = self._snap_duration(duration, model)
            try:
                task_id = self._submit_veo(
                    model, prompt, veo_duration, aspect_ratio,
                    generate_audio, api_key
                )
                result_url = self._poll_veo(task_id, api_key)
                used_model = model
            except Exception as exc:
                return ToolResult(
                    success=False,
                    error=f"kie_video: {model} failed: {exc}",
                )

        if not result_url:
            return ToolResult(
                success=False,
                error="kie_video: no result URL produced after all attempts",
            )

        # Download the MP4 bytes to disk (never use the remote URL directly —
        # CDN content-disposition attachment breaks downstream embed)
        try:
            self._download_video(result_url, output_path)
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"kie_video: download failed for {result_url}: {exc}",
            )

        return ToolResult(
            success=True,
            data={
                "provider": "kie",
                "model": used_model,
                "prompt": prompt,
                "output": str(output_path),
                "kie_task_id": task_id,           # render proof receipt
                "kie_result_url": result_url,     # render proof receipt
                "has_audio": generate_audio,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost({**inputs, "model": used_model}),
            duration_seconds=round(time.time() - start, 2),
            model=used_model,
        )


# ---------------------------------------------------------------------------
# Internal sentinel (not part of the public API)
# ---------------------------------------------------------------------------

class _ImageFetchError(RuntimeError):
    """Raised by _poll_gemini_omni when the model reports a transient
    image-fetch failure, signalling the caller to retry (mirrors rc=2
    in generate-celebration-video.sh poll_gemini_omni)."""
    pass
