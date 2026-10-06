"""KIE.ai video generation adapter for OpenMontage (Skill 47).

Provides capability "video_generation" via the KIE.ai API.

DEFAULT model:   gemini-omni-video (image-guided, 4-8s, aspect_ratio always
                 required, duration MUST be a STRING — the verified 422 fix).
FALLBACK model:  veo3_fast (text-to-video, durations 4/6/8s only, different
                 endpoint and poll URL).
ALSO SUPPORTED:  bytedance/seedance-1.5-pro (Skill 62 U5 extension, added
                 2026-07-15) — text-to-video (input_urls omitted) or
                 image-to-video with 1-2 `input_urls`. TWO images
                 (`input_urls[0]` = first frame, `input_urls[1]` = last
                 frame) pin BOTH endpoints of the clip ("frame pinning"),
                 the capability the Cinematic and Web Funnel Engine (Skill 62)
                 needs for seam-continuous connector clips between scenes
                 (spec §10.1/§10.2, CINEMATIC-AND-WEB-FUNNEL-ENGINE-SPEC.md).

ONE KIE PATH: this file is a thin BaseTool wrapper. Every KIE call (live-schema
validate, prompt-budget, credit preflight, createTask, wait, save) runs through
Skill 74 (74-kie-live-adapter), called per call in ``active`` mode. The Skill 74
client is taken from the installed sibling skill folder when it is present;
otherwise from the EMBEDDED COPY that lives in the sibling file
tools/graphics/kie_image.py (generated verbatim from Skill 74's source by
scripts/embed_kie_client.py and hash-locked by
scripts/test_kie_embedded_client_hashlock.py; the clone and the Docker image
carry only the two adapter files, so the copy travels inside one of them).
Each run prints which path ran: ``path=skill74`` or ``path=embedded``.

ONE EXCEPTION, kept on purpose: veo3 / veo3_fast use KIE's legacy
``POST /api/v1/veo/generate`` + ``GET /api/v1/veo/record-info`` route, which
Skill 74 does not model (it submits to the createTask path a schema declares and
polls jobs/recordInfo). That route's body and its successFlag poll are Skill 47's
own policy and live in ``_run_veo_legacy``; the transport under them (auth, HTTP,
retry on 429, redaction, result download) is still Skill 74's ``Adapter``.

INSTALL NOTE (Skill 47 INSTALL.md):
  This file is NOT part of OpenMontage source (AGPLv3).  It is an adapter
  authored by the fleet operator and shipped inside 47-movie-producer/
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

import json
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any
from urllib.parse import quote

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
# Models, durations and aspect sets (verified against generate-celebration-video.sh
# lines 388-415 and 07-kie-setup/kie-setup-full.md "Seedance 1.5 Pro"). The
# prompt length limits are NOT here: Skill 74 prompt-budget and the live schema own them.
# ---------------------------------------------------------------------------
_POLL_TIMEOUT_SECONDS = 1800   # 30 min; matches ZHC_VIDEO_POLL_TIMEOUT_SEC default
_VEO_POLL_INTERVAL_SECONDS = 10
_USD_PER_CREDIT = 0.005        # kie.ai/pricing: 1 credit ~= $0.005

_GEMINI_VALID_DURATIONS = {"4", "5", "6", "7", "8"}
_VEO_VALID_DURATIONS    = {"4", "6", "8"}

_DEFAULT_MODEL    = "gemini-omni-video"
_FALLBACK_MODEL   = "veo3_fast"
_DEFAULT_DURATION = "8"   # STRING — the 422 fix

_VALID_ASPECT_RATIOS = {"16:9", "9:16"}   # gemini-omni-video / veo (generate-celebration-video.sh line 425)

# bytedance/seedance-1.5-pro (Skill 62 U5 extension, 2026-07-15):
#   input_urls: array of 0-2 image URLs (frame pinning; 0=first, 1=last frame)
#   aspect_ratio: required, one of 1:1/4:3/3:4/16:9/9:16/21:9
#   resolution: 480p/720p/1080p
#   duration: 4, 8, or 12 seconds (as a STRING, mirroring the gemini-omni fix)
_SEEDANCE_MODEL              = "bytedance/seedance-1.5-pro"
_SEEDANCE_VALID_DURATIONS    = {"4", "8", "12"}
_SEEDANCE_DEFAULT_DURATION   = "8"
_SEEDANCE_VALID_RESOLUTIONS  = {"480p", "720p", "1080p"}
_SEEDANCE_DEFAULT_RESOLUTION = "720p"
_SEEDANCE_VALID_ASPECT_RATIOS = {"1:1", "4:3", "3:4", "16:9", "9:16", "21:9"}
_SEEDANCE_MAX_INPUT_URLS      = 2  # 0=text-to-video, 1=first-frame, 2=first+last frame pin

_TRANSIENT_FETCH_MARKERS = (
    "image fetch failed", "fetch image", "failed to fetch", "failed to download", "failed to load",
)


def _real_kie_key(raw):
    """Return the key only when the secret canon accepts it as a real KIE key.

    Uses shared-utils/secret_helper.py when this file sits in a repo checkout or an installed skills
    tree; the OpenMontage clone and the Docker image have no shared-utils, so the same gate then comes
    from the EMBEDDED copy of that helper in the sibling kie_image.py (generated verbatim, hash-locked).
    A placeholder such as the installer's YOUR_CLIENT_KIE_API_KEY_HERE is NOT-SET. Fail closed: a key
    the gate cannot approve counts as NOT-SET.
    """
    if not raw or not str(raw).strip():
        return None
    cands = [str(p / "shared-utils") for p in Path(__file__).resolve().parents]
    cands += [os.environ.get("OPENCLAW_SHARED_UTILS", ""),
              os.path.expanduser("~/.openclaw/skills/shared-utils"),
              "/data/.openclaw/skills/shared-utils"]
    for c in cands:
        if c and (Path(c) / "secret_helper.py").is_file():
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                from secret_helper import looks_like_real_key as shared_gate
            except Exception:
                break  # the shared copy is unusable: use the embedded one below
            return raw if shared_gate(raw, "KIE_API_KEY") else None
    block = _embedded_block(_SECRET_BEGIN, _SECRET_END)
    if block is None:
        return None  # no gate available at all: fail closed
    return raw if _exec_module(block, "kie_image.py#embedded-secret-helper").looks_like_real_key(raw, "KIE_API_KEY") else None


# ---------------------------------------------------------------------------
# Skill 74 client: installed sibling skill first, the embedded copy in the
# sibling kie_image.py second.
# ---------------------------------------------------------------------------
_SKILL74_DIRNAME = "74-kie-live-adapter"
_EMBED_BEGIN = "# >>> BEGIN EMBEDDED SKILL-74 CLIENT"
_EMBED_END = "# <<< END EMBEDDED SKILL-74 CLIENT"
_SECRET_BEGIN = "# >>> BEGIN EMBEDDED SECRET-HELPER"
_SECRET_END = "# <<< END EMBEDDED SECRET-HELPER"
_CLIENT: Any = None  # (client module, "skill74" | "embedded") or (None, None) when neither exists


def _skill74_candidates() -> list[Path]:
    override = os.environ.get("KIE_SKILL74_DIR")
    if override is not None:  # test hook: look only here ("" = Skill 74 not installed)
        return [Path(override)] if override else []
    roots = [p for p in Path(__file__).resolve().parents]  # repo checkout: the skills tree is an ancestor
    roots += [Path(os.environ["OPENCLAW_SKILLS_DIR"])] if os.environ.get("OPENCLAW_SKILLS_DIR") else []
    roots += [Path.home() / ".openclaw" / "skills", Path("/data/.openclaw/skills")]
    return [r / _SKILL74_DIRNAME for r in roots]


def _exec_module(code_text: str, filename: str) -> types.ModuleType:
    mod = types.ModuleType("kie_live_adapter_client")
    mod.__file__ = filename
    exec(compile(code_text, filename, "exec"), mod.__dict__)  # in memory: nothing is written next to the source
    return mod


def _embedded_block(begin: str, end: str) -> Any:
    """Text of a generated block in the sibling kie_image.py (same relative layout in the skill and in the clone), or None."""
    sibling = Path(__file__).resolve().parents[1] / "graphics" / "kie_image.py"
    if not sibling.is_file():
        return None
    text = sibling.read_text(encoding="utf-8")
    if begin not in text or end not in text:
        return None
    return text[text.index(begin):text.index(end)]


def _kie_client() -> Any:
    """-> (client module with Adapter / KieError, path label). Printed once per process."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = (None, None)
        for d in _skill74_candidates():
            f = d / "scripts" / "kie_live_adapter.py"
            if f.is_file():
                _CLIENT = (_exec_module(f.read_text(encoding="utf-8"), str(f)), "skill74")
                print(f"[kie-47] path=skill74 mode=active ({f})", file=sys.stderr)
                break
        else:
            block = _embedded_block(_EMBED_BEGIN, _EMBED_END)
            if block is not None:
                _CLIENT = (_exec_module(block, "kie_image.py#embedded-skill-74-client"), "embedded")
                print("[kie-47] path=embedded mode=active (Skill 74 not installed; generated copy from kie_image.py)", file=sys.stderr)
    return _CLIENT


def _new_adapter(api_key: str, transport: Any = None, sleep: Any = None, now: Any = None) -> Any:
    """A Skill 74 Adapter pinned to ``active`` mode for this call (owner order: live)."""
    client, _label = _kie_client()
    if client is None:
        raise RuntimeError("no KIE client: Skill 74 is not installed and the embedded copy in kie_image.py is missing")
    env = {"KIE_API_KEY": api_key, "KIE_LIVE_ADAPTER_MODE": "active", "HOME": os.environ.get("HOME") or str(Path.home())}
    for name in ("KIE_LIVE_CACHE_DIR", "KIE_LIVE_RECEIPT_DIR", "KIE_LIVE_MIN_SPACING", "OC_CONFIG",
                 "KIE_LIVE_API_BASE", "KIE_LIVE_UPLOAD_BASE"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    kwargs: dict[str, Any] = {}
    if transport is not None:
        kwargs["transport"] = transport
    if sleep is not None:
        kwargs["sleep"] = sleep
    if now is not None:
        kwargs["now"] = now
    adapter = client.Adapter(env=env, **kwargs)
    adapter.mode = "active"
    return adapter


def _err_text(result: dict[str, Any]) -> str:
    err = result.get("error") or {}
    return f"{err.get('code')}: {err.get('msg')}" if err else f"state={result.get('state')}"


def _lost_answer(code: Any) -> bool:
    """A createTask failure that does not prove the request was rejected: a network error, a body that is not
    KIE JSON (a gateway 502 page), or any 5xx. The job may exist and be billed, so there is no fallback."""
    return code in ("network", "bad_response") or str(code).startswith("5")


class _KieUnresolved(RuntimeError):
    """A paid KIE job whose outcome is unknown: it timed out or could not be read (``task_id`` set), or the
    createTask answer was lost to a network error after the request may have been sent (``task_id`` None).
    Never fall back to another model and never resubmit: record the task id for the Dispatcher to re-poll."""

    def __init__(self, message: str, task_id: Any = None):
        super().__init__(message)
        self.task_id = task_id


def _first_result_url(*blocks: Any) -> str:
    """First result URL from the shapes the legacy Veo record-info returns."""
    for b in blocks:
        if isinstance(b, str):  # resultJson arrives as a JSON-ENCODED STRING
            try:
                b = json.loads(b)
            except ValueError:
                continue
        if not isinstance(b, dict):
            continue
        urls = b.get("resultUrls")
        if isinstance(urls, list) and urls and isinstance(urls[0], str):
            return urls[0]
        for k in ("videoUrl", "url", "resultUrl"):
            if isinstance(b.get(k), str) and b[k]:
                return b[k]
    return ""




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

    bytedance/seedance-1.5-pro (Skill 62 U5 extension) additionally supports
    TWO-IMAGE `input_urls` FRAME PINNING: passing exactly two images pins the
    first frame AND the last frame of the generated clip, which is what the
    Cinematic and Web Funnel Engine (Skill 62) needs to render seam-continuous
    connector clips between two already-approved scene stills.
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
        "first_frame_control",
        "first_and_last_frame_control",
    ]
    supports = {
        "image_to_video": True,
        "text_to_video": True,
        "image_guided_video": True,   # gemini-omni-video reference images
        "native_audio": True,
        "generate_audio": True,
        "first_frame_pinning": True,           # bytedance/seedance-1.5-pro, 1 input_urls entry
        "first_and_last_frame_pinning": True,  # bytedance/seedance-1.5-pro, 2 input_urls entries
    }
    best_for = [
        "brand-consistent videos with reference images (gemini-omni-video)",
        "image-to-video generation from org charts and infographics",
        "fleet-standard production video via KIE.ai at ~$0.50-$1.00/clip",
        "text-to-video fallback via veo3_fast",
        "seam-continuous scene/connector clips via bytedance/seedance-1.5-pro "
        "two-image first/last-frame pinning (input_urls)",
    ]
    not_good_for = [
        "free/zero-key generation (requires KIE_API_KEY)",
        "offline generation",
        "durations outside 4/6/8s (Veo), 4-8s (Gemini Omni), or 4/8/12s (Seedance)",
        "paid Seedance calls before a live price is confirmed — Kie.ai's own "
        "docs state pricing is not listed for bytedance/seedance-1.5-pro "
        "(07-kie-setup/kie-setup-full.md); Skill 74 preflight reports an "
        "unpriced model and proceeds, so the caller's budget gate must "
        "resolve a live price before any paid call",
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
                "enum": ["gemini-omni-video", "veo3", "veo3_fast", _SEEDANCE_MODEL],
                "default": "gemini-omni-video",
                "description": (
                    "KIE model to use.  gemini-omni-video is the default and "
                    "supports reference images (image-guided generation).  "
                    "veo3 / veo3_fast use a different endpoint; they are "
                    "text-to-video only (no image references).  "
                    "bytedance/seedance-1.5-pro (Skill 62 U5) supports 0-2 "
                    "`input_urls` -- 2 images pins BOTH the first and last "
                    "frame of the clip."
                ),
            },
            "duration": {
                "type": "string",
                "description": (
                    "Clip duration in seconds as a STRING.  "
                    "gemini-omni-video accepts '4'-'8'; veo3/veo3_fast accept '4', '6', or '8'; "
                    "bytedance/seedance-1.5-pro accepts '4', '8', or '12'.  "
                    "MUST be a string, not an integer (422 fix, verified 2026-05-27)."
                ),
                "default": "8",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
                "default": "16:9",
                "description": (
                    "Output aspect ratio.  ALWAYS included in the request body "
                    "for gemini-omni-video (KIE 422 fix, v10.X.4) and REQUIRED "
                    "for bytedance/seedance-1.5-pro.  gemini-omni-video/veo3/"
                    "veo3_fast only accept 16:9 or 9:16; other values snap to "
                    "16:9 for those models but are valid as-is for Seedance "
                    "(1:1/4:3/3:4/16:9/9:16/21:9)."
                ),
            },
            "generate_audio": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Include synchronized audio in the generated clip.  For "
                    "bytedance/seedance-1.5-pro the KIE default is false and "
                    "enabling it increases cost (07-kie-setup/kie-setup-full.md)."
                ),
            },
            "resolution": {
                "type": "string",
                "enum": ["480p", "720p", "1080p"],
                "default": "720p",
                "description": (
                    "Output resolution -- bytedance/seedance-1.5-pro only.  "
                    "Ignored for gemini-omni-video/veo3/veo3_fast, which use "
                    "their own fixed defaults."
                ),
            },
            "fixed_lens": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Lock the camera position -- bytedance/seedance-1.5-pro "
                    "only (KIE `fixed_lens` field). Ignored for other models."
                ),
            },
            "input_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "bytedance/seedance-1.5-pro FRAME PINNING.  0-2 public "
                    "image URLs, order-significant: index 0 = FIRST frame, "
                    "index 1 (optional) = LAST frame.  0 entries = pure "
                    "text-to-video; 1 entry = image-to-video from that start "
                    "frame; 2 entries = the clip is pinned to begin on the "
                    "first image and end on the second (spec §10.1/§10.2 "
                    "'two-image input_urls frame pinning').  Each URL must be "
                    "publicly reachable by KIE servers -- upload local files "
                    "first through Skill 74 upload (see kie_image).  Ignored for "
                    "every other model (they use image_urls/image_url instead)."
                ),
            },
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Reference image URLs for gemini-omni-video.  Each URL must "
                    "be publicly reachable by KIE/Gemini servers.  Upload local "
                    "files first through Skill 74 upload (see kie_image).  "
                    "Ignored for veo3/veo3_fast (text-to-video only) and for "
                    "bytedance/seedance-1.5-pro (use `input_urls` instead, "
                    "which preserves first/last-frame order)."
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
            "input_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Echo of the frame-pin input_urls actually submitted (bytedance/seedance-1.5-pro only; empty otherwise).",
            },
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
    idempotency_key_fields = ["prompt", "model", "duration", "aspect_ratio", "resolution", "input_urls"]
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
        return _real_kie_key(os.environ.get("KIE_API_KEY"))

    def get_status(self) -> ToolStatus:
        """AVAILABLE only when KIE_API_KEY is set to a real key (a placeholder is NOT-SET)."""
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
        bytedance/seedance-1.5-pro: accepts 4, 8, 12 (as STRING).
        """
        if model == "gemini-omni-video":
            if raw in _GEMINI_VALID_DURATIONS:
                return raw
            return _DEFAULT_DURATION
        elif model == _SEEDANCE_MODEL:
            if raw in _SEEDANCE_VALID_DURATIONS:
                return raw
            try:
                n = int(raw)
            except ValueError:
                return _SEEDANCE_DEFAULT_DURATION
            # Snap to nearest valid Seedance duration (4, 8, 12)
            if n <= 4:
                return "4"
            if n <= 8:
                return "8"
            return "12"
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

    def _snap_aspect(self, raw: str, model: str = "gemini-omni-video") -> str:
        """Snap aspect ratio to a model-valid value.

        bytedance/seedance-1.5-pro accepts a much wider set
        (1:1/4:3/3:4/16:9/9:16/21:9 -- kie-setup-full.md 'Seedance 1.5 Pro')
        than gemini-omni-video/veo3/veo3_fast (16:9/9:16 only).
        """
        if model == _SEEDANCE_MODEL:
            return raw if raw in _SEEDANCE_VALID_ASPECT_RATIOS else "16:9"
        return raw if raw in _VALID_ASPECT_RATIOS else "16:9"

    def _snap_resolution(self, raw: str) -> str:
        """Snap output resolution to a valid bytedance/seedance-1.5-pro value
        (480p/720p/1080p). Not used by gemini-omni-video/veo3/veo3_fast,
        which have no user-selectable resolution field."""
        return raw if raw in _SEEDANCE_VALID_RESOLUTIONS else _SEEDANCE_DEFAULT_RESOLUTION

    def _resolve_input_urls(self, inputs: dict[str, Any]) -> list[str]:
        """Ordered frame-pin URLs for bytedance/seedance-1.5-pro.

        Index 0 is the FIRST frame, index 1 (optional) is the LAST frame.
        Unlike `_resolve_image_urls` (gemini-omni's reference-image merge
        across several alias keys), frame identity here depends on POSITION,
        so this reads ONLY `inputs["input_urls"]` and preserves its exact
        order -- no merge, no re-sort. Capped at
        `_SEEDANCE_MAX_INPUT_URLS` (2); non-http(s)/non-string entries are
        dropped (fail-soft on a malformed entry, not a hard request error).
        """
        raw = inputs.get("input_urls") or []
        urls: list[str] = []
        for u in raw:
            if isinstance(u, str) and (u.startswith("https://") or u.startswith("http://")):
                urls.append(u)
            if len(urls) >= _SEEDANCE_MAX_INPUT_URLS:
                break
        return urls

    # ------------------------------------------------------------------
    # Skill 74 jobs
    # ------------------------------------------------------------------

    @staticmethod
    def _check_prompt(adapter: Any, model: str, prompt: str) -> tuple[str | None, list[str]]:
        """Prompt length comes from Skill 74 prompt-budget (no band is hard-coded here).
        -> (refusal text or None, warnings). Owner rule 12: a descriptive prompt over the model maximum
        or under 80 percent of it is a HARD REJECT, and the refusal names the exact characters to cut or add."""
        r = adapter.cmd_prompt_budget(model, check=True, prompt_text=prompt)
        err = r.get("error") or {}
        if err.get("code") == "prompt_above_max":
            return f"kie_video: {model} prompt exceeds the model limit: {err.get('msg')}", []
        if err.get("code") == "prompt_below_floor":
            return f"kie_video: {model} prompt is below the 80 percent floor: {err.get('msg')}", []
        return None, []

    @staticmethod
    def _preflight(adapter: Any, model: str, seconds: float) -> tuple[str | None, Any, list[str]]:
        """Credit preflight (price x 1.30 against the live balance). -> (refusal, credits estimate, warnings).
        Only a real shortfall blocks; an unpriced model or an unreadable balance is reported and the run proceeds."""
        pre = adapter.cmd_preflight(model, seconds)
        if (pre.get("error") or {}).get("code") == "insufficient_credits":
            return f"kie_video: {_err_text(pre)}", None, []
        warnings = [f"credit preflight not enforced for {model} ({_err_text(pre)})"] if pre["state"] == "fail" else []
        return None, (pre.get("data") or {}).get("credits_estimate"), warnings

    def _run_job(self, adapter: Any, model: str, task_input: dict[str, Any], seconds: float, save_dir: str) -> dict[str, Any]:
        """createTask models: prompt-budget, preflight, then Skill 74 submit + wait + save.
        -> {"ok", "error", "transient", "run", "credits", "warnings"}."""
        try:  # a transport fault while reading the prompt limit or the balance happens BEFORE any spend: fail closed, do not raise
            refusal, warnings = self._check_prompt(adapter, model, task_input.get("prompt", ""))
            if not refusal:
                refusal, credits, more = self._preflight(adapter, model, seconds)
                warnings += more
            else:
                credits = None
        except Exception as exc:  # noqa: BLE001 - any client-side fault (for example a truncated read) is a refusal with no spend
            refusal, warnings, credits = f"kie_video: {model} pre-flight check failed before any spend: {getattr(exc, 'msg', exc)}", [], None
        if refusal:
            return {"ok": False, "error": refusal, "transient": False, "unresolved": False, "refused": True,
                    "task_id": None, "run": {}, "credits": None, "warnings": warnings}
        try:
            run = adapter.cmd_run({"model": model, "input": task_input}, save_dir, timeout=_POLL_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - a fault after createTask may have been sent: the outcome is unknown, never resubmit
            return {"ok": False, "error": f"unexpected client fault during the paid run: {getattr(exc, 'msg', exc)}",
                    "transient": False, "unresolved": True, "task_id": None, "run": {}, "credits": credits, "warnings": warnings}
        if run["state"] == "success" and run["saved_paths"]:
            return {"ok": True, "error": "", "transient": False, "unresolved": False, "task_id": run["task_id"],
                    "run": run, "credits": credits, "warnings": warnings}
        msg = _err_text(run) + (f" (task {run['task_id']} may still finish)" if run.get("task_id") else "")
        err = run.get("error") or {}
        tid = run.get("task_id")
        verdict = run["state"] == "fail" and "state_raw" in (run.get("data") or {})  # KIE itself reported the task failed
        # Unknown outcome: a task id exists but KIE has not said it failed (timeout, unreadable status), or
        # createTask was sent and its answer was lost to a network error. Money may be spent either way.
        unresolved = (bool(tid) and not verdict) or (not tid and _lost_answer(err.get("code")))
        transient = verdict and any(k in msg.lower() for k in _TRANSIENT_FETCH_MARKERS)
        return {"ok": False, "error": msg, "transient": transient, "unresolved": unresolved, "task_id": tid,
                "run": run, "credits": credits, "warnings": warnings}

    def _run_veo_legacy(
        self, adapter: Any, model: str, prompt: str, duration: str, aspect_ratio: str,
        generate_audio: bool, save_dir: str,
    ) -> dict[str, Any]:
        """veo3 / veo3_fast on KIE's legacy Veo route (see the module docstring). The body has a
        top-level 'prompt' and an INTEGER duration (verified against generate-celebration-video.sh
        submit_veo(), lines 534-545 + 07-kie-setup/EXAMPLES.md Example 4). Raises RuntimeError."""
        try:
            duration_int = int(duration)
        except ValueError:
            duration_int = 8
        body = {"model": model, "prompt": prompt, "aspect_ratio": aspect_ratio,
                "duration": duration_int, "generate_audio": generate_audio}
        try:
            j = adapter.call("POST", adapter.api + "/api/v1/veo/generate", body)
        except Exception as exc:  # Skill 74's KieError: code + redacted msg
            if _lost_answer(getattr(exc, "code", None)) or not hasattr(exc, "code"):  # may have been sent: outcome unknown, never resubmit
                raise _KieUnresolved(f"Veo submit outcome unknown after a lost or unreadable answer ({getattr(exc, 'msg', exc)})")
            raise RuntimeError(f"Veo submit failed: {getattr(exc, 'msg', exc)}")
        task_id = (j.get("data") or {}).get("taskId") or j.get("taskId")
        if not task_id:
            raise RuntimeError(f"Veo submit returned no taskId: {j}")
        url = self._poll_veo(adapter, task_id)
        saved = adapter.cmd_save(task_id, save_dir, info={"task_id": task_id, "state": "success", "result_urls": [url]})
        if saved["state"] != "success" or not saved["saved_paths"]:
            raise _KieUnresolved(f"Veo task {task_id} succeeded but its result could not be saved: {_err_text(saved)}", task_id)
        return {"task_id": task_id, "url": url, "path": saved["saved_paths"][0]}

    def _poll_veo(self, adapter: Any, task_id: str) -> str:
        """Poll GET /api/v1/veo/record-info until success; return the result URL. Transient 5xx and
        body errorCode 500 are tolerated up to 3 times (generate-celebration-video.sh poll_veo(), lines 547-612)."""
        elapsed, transient = 0, 0
        while elapsed < _POLL_TIMEOUT_SECONDS:
            adapter.sleep(_VEO_POLL_INTERVAL_SECONDS)
            elapsed += _VEO_POLL_INTERVAL_SECONDS
            try:
                j = adapter.call("GET", "%s/api/v1/veo/record-info?taskId=%s" % (adapter.api, quote(task_id)))
            except Exception as exc:
                code = getattr(exc, "code", None)
                if code == "network" or str(code).startswith("5"):
                    transient += 1
                    if transient > 3:
                        raise _KieUnresolved(f"Veo poll for {task_id}: 4 consecutive transient errors; giving up", task_id)
                    adapter.sleep(30)
                    elapsed += 30
                    continue
                raise _KieUnresolved(f"Veo poll for {task_id} failed: {getattr(exc, 'msg', exc)}", task_id)
            data = j.get("data") or {}
            if str(data.get("errorCode") or j.get("errorCode") or "") == "500":
                transient += 1
                if transient > 3:
                    raise _KieUnresolved(f"Veo poll for {task_id}: 4 consecutive transient errors; giving up", task_id)
                adapter.sleep(30)
                elapsed += 30
                continue
            transient = 0
            flag = str(data.get("successFlag") or "")
            if flag == "1":
                url = _first_result_url(data.get("response"), data.get("resultJson"))
                if url:
                    return url
                raise _KieUnresolved(f"Veo task {task_id} succeeded but no result URL: {data}", task_id)
            if flag == "-1":
                raise RuntimeError(f"Veo task {task_id} failed: {data.get('errorMessage') or data.get('failMsg') or j.get('msg') or 'unknown'}")
        raise _KieUnresolved(f"Veo task {task_id} timed out after {_POLL_TIMEOUT_SECONDS}s (it may still finish)", task_id)

    @staticmethod
    def _unresolved_result(model: str, task_id: Any, message: str, label: str, warnings: list[str]) -> ToolResult:
        """A paid job whose outcome is unknown. No fallback model, no resubmission: the task id (when KIE
        returned one) is recorded in ``data`` for the Dispatcher to re-poll with Skill 74 ``wait``."""
        if task_id:
            advice = f"re-poll task {task_id} (Skill 74 wait --task-id {task_id}); do not resubmit or switch model"
        else:
            advice = "the createTask answer was lost: check the KIE task list before any resubmission; do not switch model"
        return ToolResult(
            success=False,
            error=f"kie_video: {model} outcome unknown: {message}; {advice}",
            data={
                "provider": "kie", "model": model, "kie_task_id": task_id or None,
                "kie_task_state": "unresolved" if task_id else "createTask_outcome_unknown",
                "needs_repoll": True, "kie_client_path": label, "warnings": warnings,
            },
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        """Generate a video via KIE.ai (through Skill 74) and save the MP4.

        Model routing:
          - gemini-omni-video: createTask, input.duration as STRING, aspect_ratio
              always set, image_urls accepted for image-guided generation.
              One retry on a transient image-fetch failure (the same URLs); any other
              failure falls back to veo3_fast. createTask is never retried after a
              network error (Skill 74 rule: that could charge twice).
          - bytedance/seedance-1.5-pro: createTask, 0-2 `input_urls` frame pins.
          - veo3 / veo3_fast: the legacy Veo route (see the module docstring),
              duration as integer, no image references.

        Returns a ToolResult with data keys:
          provider, model, prompt, output,
          kie_task_id   (render proof receipt),
          kie_result_url (render proof receipt),
          has_audio, kie_client_path ("skill74" or "embedded"), warnings.
        """
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(success=False, error="KIE_API_KEY is not set. " + self.install_instructions)

        start = time.time()
        prompt = inputs.get("prompt", "")
        model = inputs.get("model", _DEFAULT_MODEL)
        raw_duration = str(inputs.get("duration", _DEFAULT_DURATION))
        aspect_ratio = self._snap_aspect(inputs.get("aspect_ratio", "16:9"), model)
        generate_audio = bool(inputs.get("generate_audio", True))
        output_path = Path(inputs.get("output_path", "kie_video_output.mp4"))
        duration = self._snap_duration(raw_duration, model)
        image_urls = self._resolve_image_urls(inputs)

        try:
            adapter = _new_adapter(api_key, getattr(self, "_transport", None), getattr(self, "_sleep", None), getattr(self, "_now", None))
        except RuntimeError as exc:
            return ToolResult(success=False, error=f"kie_video: {exc}")
        label = _kie_client()[1]
        seconds = float(duration)

        task_id = result_url = saved_path = ""
        used_model = model
        used_input_urls: list[str] = []
        credits: Any = None
        warnings: list[str] = []
        save_dir = tempfile.mkdtemp(prefix="kie_video_")

        def adopt(job: dict[str, Any]) -> None:
            nonlocal task_id, result_url, saved_path, credits
            run = job["run"]
            task_id, result_url, saved_path = run["task_id"], (run["result_urls"] or [""])[0], run["saved_paths"][0]
            credits = job["credits"]

        try:
            # --- bytedance/seedance-1.5-pro (Skill 62 U5: text-to-video or 1-2 image `input_urls` frame pinning) ---
            if model == _SEEDANCE_MODEL:
                input_urls = self._resolve_input_urls(inputs)
                task_input: dict[str, Any] = {
                    "prompt": prompt.strip(),
                    "aspect_ratio": aspect_ratio,  # REQUIRED for Seedance (kie-setup-full.md)
                    "resolution": self._snap_resolution(inputs.get("resolution", _SEEDANCE_DEFAULT_RESOLUTION)),
                    "duration": duration,          # STRING, mirrors the gemini-omni 422-fix pattern
                    "fixed_lens": bool(inputs.get("fixed_lens", False)),
                    "generate_audio": generate_audio,
                }
                if input_urls:
                    task_input["input_urls"] = input_urls  # omitted entirely for text-to-video
                job = self._run_job(adapter, _SEEDANCE_MODEL, task_input, seconds, save_dir)
                warnings += job["warnings"]
                if job["unresolved"]:
                    return self._unresolved_result(_SEEDANCE_MODEL, job["task_id"], job["error"], label, warnings)
                if not job["ok"]:
                    return ToolResult(success=False, error=f"kie_video: {_SEEDANCE_MODEL} failed: {job['error']}")
                adopt(job)
                used_input_urls = input_urls

            # --- gemini-omni-video (primary), then veo3_fast ---
            elif model == "gemini-omni-video":
                task_input = {
                    "prompt": prompt,
                    "duration": duration,            # STRING, the verified 422 fix
                    "aspect_ratio": aspect_ratio,    # ALWAYS present, the verified 422 fix
                    "generate_audio": generate_audio,
                }
                if image_urls:
                    task_input["image_urls"] = image_urls
                last_error = ""
                for attempt in (1, 2):
                    job = self._run_job(adapter, "gemini-omni-video", task_input, seconds, save_dir)
                    warnings += job["warnings"]
                    if job["ok"]:
                        adopt(job)
                        break
                    if job["unresolved"]:  # timeout / unreadable status / lost createTask answer: money may be spent
                        return self._unresolved_result("gemini-omni-video", job["task_id"], job["error"], label, warnings)
                    if job.get("refused"):  # prompt or credit refusal: a different model must not bypass it
                        return ToolResult(success=False, error=job["error"])
                    last_error = job["error"]
                    if job["transient"] and attempt == 1:
                        adapter.sleep(5)  # transient image-fetch: one retry with the same references
                        continue
                    break
                if not result_url:
                    warnings.append(f"gemini-omni-video failed ({last_error}); falling back to {_FALLBACK_MODEL}")
                    try:
                        veo = self._run_veo_legacy(
                            adapter, _FALLBACK_MODEL, prompt, self._snap_duration(_DEFAULT_DURATION, _FALLBACK_MODEL),
                            aspect_ratio, generate_audio, save_dir,
                        )
                    except _KieUnresolved as exc:
                        return self._unresolved_result(_FALLBACK_MODEL, exc.task_id, str(exc), label, warnings)
                    except RuntimeError as exc:
                        return ToolResult(
                            success=False,
                            error=f"kie_video: gemini-omni-video failed and veo3_fast fallback also failed: {exc}",
                        )
                    task_id, result_url, saved_path, used_model = veo["task_id"], veo["url"], veo["path"], _FALLBACK_MODEL

            # --- direct veo3 / veo3_fast ---
            else:
                try:
                    veo = self._run_veo_legacy(
                        adapter, model, prompt, self._snap_duration(duration, model), aspect_ratio, generate_audio, save_dir,
                    )
                except _KieUnresolved as exc:
                    return self._unresolved_result(model, exc.task_id, str(exc), label, warnings)
                except RuntimeError as exc:
                    return ToolResult(success=False, error=f"kie_video: {model} failed: {exc}")
                task_id, result_url, saved_path = veo["task_id"], veo["url"], veo["path"]

            if not result_url or not saved_path:
                return ToolResult(success=False, error="kie_video: no result URL produced after all attempts")

            # The saved MP4 goes to disk, never the remote URL (CDN content-disposition attachment
            # breaks downstream embed; generate-celebration-video.sh lines 688-697).
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(saved_path, str(output_path))
            except OSError as exc:
                return ToolResult(success=False, error=f"kie_video: could not place the result at {output_path}: {exc}")
        finally:
            shutil.rmtree(save_dir, ignore_errors=True)

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
                "input_urls": used_input_urls,   # frame-pin echo (Seedance only; [] otherwise)
                "kie_client_path": label,
                "warnings": warnings,
            },
            artifacts=[str(output_path)],
            cost_usd=(round(credits * _USD_PER_CREDIT, 4) if isinstance(credits, (int, float))
                      else self.estimate_cost({**inputs, "model": used_model})),
            duration_seconds=round(time.time() - start, 2),
            model=used_model,
        )
