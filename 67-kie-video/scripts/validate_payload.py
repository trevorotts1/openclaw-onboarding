#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_payload.py - Skill 67 kie-video payload validator.

Validates a KIE Video payload JSON against the registry (models.json) before submission.
Supports both generic Market API (api_family: "kie-market") and dedicated families
(api_family: "runway-dedicated", "veo3-dedicated").

STDLIB PYTHON3 ONLY. Deterministic. No network. No secrets read.

Exit codes:
  0  valid (warnings may exist)
  1  invalid (errors exist)

Output: single JSON object on stdout with fields:
  valid, model_id, api_family, errors[], warnings[], checked{}.
"""

import argparse
import base64
import json
import os
import re
import sys

VERSION = "1.0.0"

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")

MARKET_CREATE_ENDPOINT = "/api/v1/jobs/createTask"
RUNWAY_CREATE_ENDPOINT = "/api/v1/runway/generate"
VEO_CREATE_ENDPOINT = "/api/v1/veo/generate"


def load_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    by_id = {m["canonical_model_id"]: m for m in data["models"]}
    return data, by_id


def parse_data_uri(ref):
    if not isinstance(ref, str) or not ref.startswith("data:"):
        return None
    header, _, b64 = ref.partition(",")
    m = re.match(r"data:([^;,]+)?(;base64)?$", header)
    media = m.group(1) if m and m.group(1) else None
    if m and m.group(2):
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception:
            return {"error": "base64 decode failed"}
        return {"media": media, "bytes": len(raw)}
    return {"media": media, "bytes": None, "error": "non-base64 data URI (unsupported)"}


def parse_duration_seconds(dur_val):
    """Attempt to parse duration value to int/float seconds."""
    if isinstance(dur_val, (int, float)):
        return float(dur_val)
    if isinstance(dur_val, str):
        m = re.match(r"^(\d+(?:\.\d+)?)s?$", dur_val.strip())
        if m:
            return float(m.group(1))
    return None


def validate_duration_against_window(dur_sec, window, errors, warnings):
    """Check duration against duration_window_seconds (string or [low, high] array).

    Supported window shapes (verified 2026-08-27):
      [3, 15]                    JSON array range -> bounds check (kling-3.0-omni I2V/R2V, seedance-2-mini)
      "2-30s (or -1 auto)"       range string     -> bounds check
      "5s or 10s ('5', '10')"    discrete or-list -> membership required (kling 2.5 turbo, runway)
      "4, 6, 8s" / "4, 6, 8, 10s" discrete comma-list -> membership required (veo3, gemini omni)
      windows containing "-1"    auto duration allowed for dur_sec == -1
    """
    if dur_sec is None or not window:
        return
    # Auto duration: only valid when the window itself documents a -1 option.
    if isinstance(window, str) and dur_sec == -1 and "-1" in window:
        return

    # 1. Array window: [low, high] range (e.g. kling-3.0-omni image-to-video [3, 15]).
    if isinstance(window, list):
        if len(window) == 2 and all(isinstance(x, (int, float)) for x in window):
            low, high = float(window[0]), float(window[1])
            if dur_sec < low or dur_sec > high:
                errors.append(
                    f"duration {dur_sec}s outside supported range {low}s-{high}s ({window})"
                )
        else:
            warnings.append(f"unrecognized duration_window_seconds shape: {window!r}")
        return

    if not isinstance(window, str):
        warnings.append(f"unrecognized duration_window_seconds type: {type(window).__name__}")
        return

    # 2. Range string e.g. "2-30s" or "3-15s" or "4-15s" or "3-15s (1-15s/shot)".
    m_range = re.search(r"(\d+)\s*-\s*(\d+)\s*s", window)
    if m_range:
        low, high = float(m_range.group(1)), float(m_range.group(2))
        if dur_sec < low or dur_sec > high:
            errors.append(
                f"duration {dur_sec}s outside supported range {low}s-{high}s ({window})"
            )
        return

    # 3. Discrete enumeration e.g. "5s or 10s", "4, 6, 8s", "4, 6, 8, 10s".
    discrete_nums = [float(x) for x in re.findall(r"\b(\d+)\s*s?\b", window)]
    if discrete_nums:
        if dur_sec not in discrete_nums:
            errors.append(
                f"duration {dur_sec}s not in supported options {discrete_nums} ({window})"
            )
        return

    warnings.append(f"unrecognized duration_window_seconds format: {window!r}")


def check_media_refs(model, media_dict, errors, warnings):
    """Validate media references (image_url, video_url, input_urls, etc.) against model limits."""
    max_refs_str = model.get("max_media_refs")
    if not max_refs_str:
        return

    # Count inputs across possible keys
    total_imgs = 0
    total_vids = 0
    total_auds = 0

    if "image_url" in media_dict and media_dict["image_url"]:
        total_imgs += 1
    if "first_frame_url" in media_dict and media_dict["first_frame_url"]:
        total_imgs += 1
    if "last_frame_url" in media_dict and media_dict["last_frame_url"]:
        total_imgs += 1
    if "image_urls" in media_dict and isinstance(media_dict["image_urls"], list):
        total_imgs += len(media_dict["image_urls"])
    if "input_urls" in media_dict and isinstance(media_dict["input_urls"], list):
        total_imgs += len(media_dict["input_urls"])
    if "elements" in media_dict and isinstance(media_dict["elements"], list):
        total_imgs += len(media_dict["elements"])

    if "video_url" in media_dict and media_dict["video_url"]:
        total_vids += 1
    if "driving_video_url" in media_dict and media_dict["driving_video_url"]:
        total_vids += 1
    if "video_urls" in media_dict and isinstance(media_dict["video_urls"], list):
        total_vids += len(media_dict["video_urls"])

    if "audio_url" in media_dict and media_dict["audio_url"]:
        total_auds += 1
    if "voice_url" in media_dict and media_dict["voice_url"]:
        total_auds += 1

    # Check for models where None / 0 media allowed (e.g. pure text-to-video)
    if "None" in max_refs_str and (total_imgs > 0 or total_vids > 0):
        # If task is explicitly text-to-video and refs are passed
        if model.get("canonical_model_id") in [
            "kling/v2-5-turbo-text-to-video-pro",
            "pixverse-v6/text-to-video",
            "minimax-h3/text-to-video",
            "happyhorse-1-1/text-to-video",
            "happyhorse/text-to-video",
        ]:
            errors.append(
                f"media references ({total_imgs} images, {total_vids} videos) provided for pure text model {model['canonical_model_id']} ({max_refs_str})"
            )

    # Check Kling 3.0 Motion Control: requires 1 driving video + 1 character image
    if model.get("canonical_model_id") in ["kling-3.0/motion-control", "kling-2.6/motion-control"]:
        if total_vids > 1:
            errors.append(f"motion control accepts at most 1 driving video; got {total_vids}")
        if total_imgs > 1:
            errors.append(f"motion control accepts at most 1 character image; got {total_imgs}")

    # Check Wan 2.7 Video Edit: exactly 1 video
    if model.get("canonical_model_id") == "wan/2-7-videoedit":
        if total_vids > 1:
            errors.append(f"video edit accepts at most 1 source video; got {total_vids}")

    # Lenient check for total counts against string if numeric cap present
    m_img_cap = re.search(r"(\d+)\s*imgs?", max_refs_str)
    if m_img_cap:
        img_limit = int(m_img_cap.group(1))
        if total_imgs > img_limit:
            errors.append(f"image reference count {total_imgs} exceeds limit {img_limit} ({max_refs_str})")

    m_vid_cap = re.search(r"(\d+)\s*vids?", max_refs_str)
    if m_vid_cap:
        vid_limit = int(m_vid_cap.group(1))
        if total_vids > vid_limit:
            errors.append(f"video reference count {total_vids} exceeds limit {vid_limit} ({max_refs_str})")

    # Registry-numeric check: max_reference_images/videos/audios are machine-readable
    # integers added to models.json (2026-08-27). Prose regexes above miss limits
    # written as "images"/"videos" (e.g. "Up to 2 images", "1-7 image references"),
    # so the numeric fields are authoritative when present.
    max_imgs = model.get("max_reference_images")
    if max_imgs is not None and total_imgs > max_imgs:
        errors.append(
            f"image reference count {total_imgs} exceeds max_reference_images {max_imgs} for {model['canonical_model_id']}"
        )
    max_vids = model.get("max_reference_videos")
    if max_vids is not None and total_vids > max_vids:
        errors.append(
            f"video reference count {total_vids} exceeds max_reference_videos {max_vids} for {model['canonical_model_id']}"
        )
    max_auds = model.get("max_reference_audios")
    if max_auds is not None and total_auds > max_auds:
        errors.append(
            f"audio reference count {total_auds} exceeds max_reference_audios {max_auds} for {model['canonical_model_id']}"
        )


def validate(payload, model_id_override=None):
    registry, by_id = load_registry()
    errors = []
    warnings = []
    checked = {}

    if not isinstance(payload, dict):
        errors.append("payload must be a JSON object")
        return {
            "valid": False,
            "model_id": model_id_override,
            "api_family": None,
            "errors": errors,
            "warnings": warnings,
            "checked": checked,
        }

    # Detect API family and model name
    model_name = payload.get("model") or model_id_override
    api_family = payload.get("api_family")
    create_endpoint = payload.get("create_endpoint")

    # Runway dedicated payload special handling: no 'model' field required in body
    if model_name == "runway" or create_endpoint == RUNWAY_CREATE_ENDPOINT or api_family == "runway-dedicated":
        model_name = "runway"
        api_family = "runway-dedicated"
        expected_endpoint = RUNWAY_CREATE_ENDPOINT
    elif model_name in ["veo3", "veo3_fast", "veo3_lite"] or create_endpoint == VEO_CREATE_ENDPOINT or api_family == "veo3-dedicated":
        if not model_name:
            model_name = "veo3_fast"
        api_family = "veo3-dedicated"
        expected_endpoint = VEO_CREATE_ENDPOINT
    else:
        api_family = api_family or "kie-market"
        expected_endpoint = MARKET_CREATE_ENDPOINT

    checked["model"] = model_name
    checked["api_family"] = api_family

    if not model_name:
        errors.append("payload missing 'model' (or could not determine dedicated model)")
        return {
            "valid": False,
            "model_id": None,
            "api_family": api_family,
            "errors": errors,
            "warnings": warnings,
            "checked": checked,
        }

    model = by_id.get(model_name)
    if not model:
        errors.append(f"model {model_name!r} not present in registry ({REGISTRY_PATH})")
        return {
            "valid": False,
            "model_id": model_name,
            "api_family": api_family,
            "errors": errors,
            "warnings": warnings,
            "checked": checked,
        }

    # Enforce API family / endpoint matching
    reg_family = model.get("api_family")
    if api_family != reg_family:
        errors.append(f"api_family mismatch: payload claims {api_family!r} but registry model {model_name!r} requires {reg_family!r}")

    if create_endpoint and create_endpoint != model.get("create_endpoint"):
        errors.append(
            f"create_endpoint mismatch: payload has {create_endpoint!r} but model {model_name!r} requires {model.get('create_endpoint')!r}"
        )
    checked["create_endpoint"] = model.get("create_endpoint")

    # Determine input container:
    # Generic market models put params under 'input' dict
    # Dedicated runway / veo put params at top-level
    if api_family == "kie-market":
        inp = payload.get("input")
        if not isinstance(inp, dict):
            errors.append("kie-market payload requires an 'input' object")
            return {
                "valid": False,
                "model_id": model_name,
                "api_family": api_family,
                "errors": errors,
                "warnings": warnings,
                "checked": checked,
            }
    else:
        inp = payload

    # 1. Prompt check
    prompt = inp.get("prompt")
    if prompt is not None:
        if not isinstance(prompt, str):
            errors.append("prompt must be a string")
        else:
            p_len = len(prompt.strip())
            hard_cap = model.get("vendor_hard_cap_chars")
            cap_status = model.get("cap_status")
            if hard_cap is not None and p_len > hard_cap and cap_status == "VERIFIED":
                errors.append(
                    f"prompt is {p_len} chars; exceeds VERIFIED hard cap {hard_cap} for {model_name}"
                )
            checked["prompt_chars"] = p_len

    # 1b. Negative prompt cap: Wan 2.7 family publishes a separate 500-char
    # negative_prompt cap alongside the 5,000-char prompt cap (VERIFIED).
    negative_prompt = inp.get("negative_prompt")
    if isinstance(negative_prompt, str) and model_name.startswith("wan/2-7"):
        np_len = len(negative_prompt.strip())
        if np_len > 500:
            errors.append(
                f"negative_prompt is {np_len} chars; hard cap 500 for {model_name} (VERIFIED)"
            )
        checked["negative_prompt_chars"] = np_len

    # 2. Duration check
    dur = inp.get("duration")
    if dur is not None:
        dur_sec = parse_duration_seconds(dur)
        if dur_sec is not None:
            validate_duration_against_window(dur_sec, model.get("duration_window_seconds"), errors, warnings)
            checked["duration_seconds"] = dur_sec
        else:
            warnings.append(f"duration value {dur!r} could not be parsed to seconds")

    # 3. Resolution check
    res = inp.get("resolution") or inp.get("quality")
    allowed_res = model.get("resolutions") or []
    if res and allowed_res:
        # Strip parenthetical annotations ("1080p (5s only)" -> "1080p") so the
        # registry's human-readable annotations do not break membership checks.
        norm_res_list = [re.sub(r"\s*\(.*?\)", "", str(r)).strip().lower() for r in allowed_res]
        if str(res).lower() not in norm_res_list:
            errors.append(
                f"resolution/quality {res!r} not in allowed resolutions {allowed_res} for {model_name}"
            )
        checked["resolution"] = res

    # 4. Runway specific rule: 1080p only supports 5s (10s restricted to 720p)
    if model_name == "runway":
        qual = inp.get("quality")
        dur_val = inp.get("duration")
        if str(qual).lower() in ["1080p", "1080"] and dur_val in [10, "10", "10s"]:
            errors.append("Runway 1080p quality is restricted to 5 seconds duration; 10s requires 720p")

    # 4b. Veo generationType constraints (dedicated Veo API, verified 2026-08-27
    # against references/api-patterns.md):
    #   REFERENCE_2_VIDEO          -> model must be veo3_fast/veo3_lite (veo3 quality
    #                                 tier does not expose it), duration must be 8s,
    #                                 image_urls count 1-3
    #   FIRST_AND_LAST_FRAMES_2_VIDEO -> image_urls exactly 2
    #   default (TEXT_2_VIDEO, no generationType) -> image_urls 1-2
    # Only enforced when the relevant fields are present in the payload.
    if model_name in ["veo3", "veo3_fast", "veo3_lite"]:
        gen_type = inp.get("generationType")
        image_urls = inp.get("image_urls")
        img_count = len(image_urls) if isinstance(image_urls, list) else None

        if gen_type == "REFERENCE_2_VIDEO":
            if model_name == "veo3":
                errors.append(
                    "REFERENCE_2_VIDEO is restricted to veo3_fast / veo3_lite; veo3 (quality tier) does not support it"
                )
            dur_val = inp.get("duration")
            if dur_val is not None and dur_val not in [8, "8", "8s"]:
                errors.append("REFERENCE_2_VIDEO only supports duration 8s")
            if img_count is not None and not (1 <= img_count <= 3):
                errors.append(f"REFERENCE_2_VIDEO requires 1-3 image_urls; got {img_count}")
        elif gen_type == "FIRST_AND_LAST_FRAMES_2_VIDEO":
            if img_count is not None and img_count != 2:
                errors.append(f"FIRST_AND_LAST_FRAMES_2_VIDEO requires exactly 2 image_urls; got {img_count}")
        else:
            # Default / TEXT_2_VIDEO path: images allowed only as 1-2 references
            if img_count is not None and not (1 <= img_count <= 2):
                errors.append(f"veo generationType {gen_type or 'TEXT_2_VIDEO (default)'} allows 1-2 image_urls; got {img_count}")

    # 5. Media refs check
    check_media_refs(model, inp, errors, warnings)

    # 6. Auth env check
    auth_env = model.get("auth_env", "KIE_API_KEY")
    checked["auth_env"] = auth_env

    return {
        "valid": len(errors) == 0,
        "model_id": model_name,
        "api_family": api_family,
        "errors": errors,
        "warnings": warnings,
        "checked": checked,
    }


# ---------------------------------------------------------------------------
# Self-test battery
# ---------------------------------------------------------------------------

def selftest():
    failures = []

    test_cases = [
        # 1. Valid Wan 3.0 Market payload
        (
            "Valid Wan 3.0",
            {
                "model": "wan/3-0-video",
                "create_endpoint": "/api/v1/jobs/createTask",
                "input": {
                    "prompt": "A cinematic shot of a mountain river at sunset",
                    "duration": 5,
                    "resolution": "1080P",
                    "aspect_ratio": "16:9",
                    "audio": True,
                },
            },
            True,
            None,
        ),
        # 2. Wan 3.0 over character cap (20000)
        (
            "Wan 3.0 over cap",
            {
                "model": "wan/3-0-video",
                "input": {
                    "prompt": "x" * 21000,
                    "duration": 5,
                    "resolution": "1080P",
                },
            },
            False,
            "exceeds VERIFIED hard cap",
        ),
        # 3. Valid Runway dedicated payload
        (
            "Valid Runway dedicated",
            {
                "api_family": "runway-dedicated",
                "create_endpoint": "/api/v1/runway/generate",
                "prompt": "Cinematic sequence through city street",
                "duration": 5,
                "quality": "1080p",
                "aspectRatio": "16:9",
            },
            True,
            None,
        ),
        # 4. Runway 1080p + 10s rule violation -> must fail
        (
            "Runway 1080p 10s conflict",
            {
                "api_family": "runway-dedicated",
                "create_endpoint": "/api/v1/runway/generate",
                "prompt": "Cinematic sequence",
                "duration": 10,
                "quality": "1080p",
            },
            False,
            "restricted to 5 seconds",
        ),
        # 5. Wrong family: Runway using createTask -> must fail
        (
            "Runway wrong endpoint",
            {
                "model": "runway",
                "create_endpoint": "/api/v1/jobs/createTask",
                "input": {"prompt": "test"},
            },
            False,
            "create_endpoint mismatch",
        ),
        # 6. Valid Veo3 fast payload
        (
            "Valid Veo3 Fast",
            {
                "model": "veo3_fast",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "Aerial view of desert dunes",
                "duration": 8,
                "aspectRatio": "16:9",
                "generationType": "TEXT_2_VIDEO",
            },
            True,
            None,
        ),
        # 7. Kling 3.0 Omni invalid resolution (e.g. 8K) -> must fail
        (
            "Kling Omni invalid res",
            {
                "model": "kling-3.0-omni/text-to-video",
                "input": {
                    "prompt": "A sequence",
                    "duration": 5,
                    "resolution": "8K",
                },
            },
            False,
            "not in allowed resolutions",
        ),
        # 8. Pure text model given image references -> must fail
        (
            "Pure text model given image refs",
            {
                "model": "kling/v2-5-turbo-text-to-video-pro",
                "input": {
                    "prompt": "Fast clip",
                    "image_url": "https://example.com/img.png",
                },
            },
            False,
            "media references",
        ),
        # 9. Array window [3, 15]: in-range duration -> valid
        (
            "Kling omni I2V array window dur 5",
            {
                "model": "kling-3.0-omni/image-to-video",
                "input": {
                    "prompt": "A",
                    "duration": 5,
                    "resolution": "1080p",
                },
            },
            True,
            None,
        ),
        # 10. Array window [3, 15]: above range -> error (previously crashed on list)
        (
            "Kling omni I2V array window dur 16",
            {
                "model": "kling-3.0-omni/image-to-video",
                "input": {
                    "prompt": "A",
                    "duration": 16,
                    "resolution": "1080p",
                },
            },
            False,
            "outside supported range 3.0s-15.0s",
        ),
        # 11. Discrete comma-list window: veo3 dur 8 (default) -> valid
        (
            "Veo3 discrete dur 8",
            {
                "model": "veo3",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 8,
            },
            True,
            None,
        ),
        # 12. Discrete comma-list window: veo3 dur 12 -> error (previously silent pass)
        (
            "Veo3 discrete dur 12",
            {
                "model": "veo3",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 12,
            },
            False,
            "not in supported options",
        ),
        # 13. Discrete or-list window: gemini omni dur 10 -> valid
        (
            "Gemini omni discrete dur 10",
            {
                "model": "gemini-omni-video",
                "input": {"prompt": "A", "duration": 10, "resolution": "1080p"},
            },
            True,
            None,
        ),
        # 14. Discrete or-list window: gemini omni dur 12 -> error
        (
            "Gemini omni discrete dur 12",
            {
                "model": "gemini-omni-video",
                "input": {"prompt": "A", "duration": 12, "resolution": "1080p"},
            },
            False,
            "not in supported options",
        ),
        # 15. Discrete or-list window: runway dur 7 -> error (previously warning-only)
        (
            "Runway discrete dur 7",
            {
                "api_family": "runway-dedicated",
                "create_endpoint": "/api/v1/runway/generate",
                "prompt": "A",
                "duration": 7,
                "quality": "720p",
            },
            False,
            "not in supported options",
        ),
        # 16. Discrete or-list window: runway dur 10 at 720p -> valid
        (
            "Runway discrete dur 10 720p",
            {
                "api_family": "runway-dedicated",
                "create_endpoint": "/api/v1/runway/generate",
                "prompt": "A",
                "duration": 10,
                "quality": "720p",
            },
            True,
            None,
        ),
        # 17. Kling 2.5 turbo discrete window dur 7 -> error (previously warning-only)
        (
            "Kling turbo discrete dur 7",
            {
                "model": "kling/v2-5-turbo-text-to-video-pro",
                "input": {"prompt": "A", "duration": 7},
            },
            False,
            "not in supported options",
        ),
        # 18. Veo REFERENCE_2_VIDEO on veo3 (quality tier) -> error
        (
            "Veo3 REFERENCE_2_VIDEO rejected",
            {
                "model": "veo3",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 8,
                "generationType": "REFERENCE_2_VIDEO",
                "image_urls": ["u1", "u2"],
            },
            False,
            "restricted to veo3_fast / veo3_lite",
        ),
        # 19. Veo fast REFERENCE_2_VIDEO with 5 images -> error (1-3 allowed)
        (
            "Veo fast R2V 5 images",
            {
                "model": "veo3_fast",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 8,
                "generationType": "REFERENCE_2_VIDEO",
                "image_urls": ["u1", "u2", "u3", "u4", "u5"],
            },
            False,
            "requires 1-3 image_urls",
        ),
        # 20. Veo fast REFERENCE_2_VIDEO with 3 images at 8s -> valid
        (
            "Veo fast R2V 3 images 8s valid",
            {
                "model": "veo3_fast",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 8,
                "generationType": "REFERENCE_2_VIDEO",
                "image_urls": ["u1", "u2", "u3"],
            },
            True,
            None,
        ),
        # 21. Veo FIRST_AND_LAST_FRAMES with 3 images -> error (exactly 2 required)
        (
            "Veo first-last 3 images",
            {
                "model": "veo3_fast",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 8,
                "generationType": "FIRST_AND_LAST_FRAMES_2_VIDEO",
                "image_urls": ["u1", "u2", "u3"],
            },
            False,
            "exactly 2 image_urls",
        ),
        # 22. Veo default path with 3 images -> error (1-2 allowed)
        (
            "Veo default 3 images",
            {
                "model": "veo3_lite",
                "api_family": "veo3-dedicated",
                "create_endpoint": "/api/v1/veo/generate",
                "prompt": "A",
                "duration": 8,
                "image_urls": ["u1", "u2", "u3"],
            },
            False,
            "allows 1-2 image_urls",
        ),
        # 23. Registry-numeric media cap: pixverse I2V 7 images (max 2) -> error
        (
            "Pixverse I2V 7 images",
            {
                "model": "pixverse-v6/image-to-video",
                "input": {
                    "prompt": "A",
                    "duration": 5,
                    "image_urls": ["u1", "u2", "u3", "u4", "u5", "u6", "u7"],
                },
            },
            False,
            "exceeds max_reference_images 2",
        ),
        # 24. Registry-numeric media cap: wan 3.0 11 images (max 10) -> error
        (
            "Wan 3.0 11 images",
            {
                "model": "wan/3-0-video",
                "input": {
                    "prompt": "A",
                    "duration": 5,
                    "image_urls": ["u%d" % i for i in range(1, 12)],
                },
            },
            False,
            "11 exceeds",
        ),
        # 25. Registry-numeric media cap: happyhorse 1.1 R2V 10 images (max 9) -> error
        (
            "Happyhorse R2V 10 images",
            {
                "model": "happyhorse-1-1/reference-to-video",
                "input": {
                    "prompt": "A",
                    "duration": 5,
                    "image_urls": ["u%d" % i for i in range(1, 11)],
                },
            },
            False,
            "exceeds max_reference_images 9",
        ),
        # 26. Wan 2.7 negative_prompt over 500-char cap -> error
        (
            "Wan 2.7 negative prompt over cap",
            {
                "model": "wan/2-7-text-to-video",
                "input": {
                    "prompt": "A",
                    "duration": 5,
                    "negative_prompt": "n" * 600,
                },
            },
            False,
            "negative_prompt is 600 chars; hard cap 500",
        ),
        # 27. Wan 2.7 negative_prompt within cap -> valid
        (
            "Wan 2.7 negative prompt within cap",
            {
                "model": "wan/2-7-text-to-video",
                "input": {
                    "prompt": "A",
                    "duration": 5,
                    "negative_prompt": "n" * 400,
                },
            },
            True,
            None,
        ),
    ]

    for name, payload, exp_valid, exp_err in test_cases:
        res = validate(payload)
        if res["valid"] != exp_valid:
            failures.append(f"FAIL {name}: expected valid={exp_valid} got {res['valid']} ({res['errors']})")
            continue
        if exp_err and not any(exp_err in e for e in res["errors"]):
            failures.append(f"FAIL {name}: expected error {exp_err!r} got {res['errors']}")

    if failures:
        print("validate_payload.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print(f"validate_payload.py --self-test: {len(test_cases)}/{len(test_cases)} passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIE video payload validator (skill 67)")
    parser.add_argument("payload", nargs="?", help="JSON payload string, or '-' for stdin")
    parser.add_argument("--file", help="path to JSON payload file")
    parser.add_argument("--model", help="canonical_model_id override")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return selftest()

    raw = None
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            raw = fh.read()
    elif args.payload == "-":
        raw = sys.stdin.read()
    elif args.payload is not None:
        raw = args.payload
    else:
        parser.error("payload (JSON string, '-', or --file) required")

    try:
        data = json.loads(raw)
    except Exception as exc:
        out = {
            "valid": False,
            "model_id": args.model,
            "api_family": None,
            "errors": [f"JSON parse failure: {exc}"],
            "warnings": [],
            "checked": {},
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 1

    res = validate(data, model_id_override=args.model)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0 if res["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
