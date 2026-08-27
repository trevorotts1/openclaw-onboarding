#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
select_video_model.py - Skill 67 kie-video model selector.

Maps a natural-language video request to a KIE canonical_model_id, or
returns valid=false with an alternative when the request cannot be served.

STDLIB PYTHON3 ONLY. Deterministic. No network. No secrets read.

Exit codes:
  0  selected (valid=true)
  1  no model can serve the request as written (valid=false, alternative may be set)

Output: single JSON object on stdout.
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Routing registry for all 37 KIE Video models across all families.
# ---------------------------------------------------------------------------

REGISTRY = {
    "wan-3-0": {
        "name": "Wan 3.0 Video",
        "routes": {
            "std": {"canonical_model_id": "wan/3-0-video", "task": "text-to-video"},
            "prime": {"canonical_model_id": "wan/3-0-video-prime", "task": "high-throughput"},
        },
        "default": "std",
    },
    "kling-3-0-omni": {
        "name": "Kling 3.0 Omni",
        "routes": {
            "t2v": {"canonical_model_id": "kling-3.0-omni/text-to-video", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "kling-3.0-omni/image-to-video", "task": "image-to-video"},
            "transform": {"canonical_model_id": "kling-3.0-omni/transformation", "task": "transformation"},
            "r2v": {"canonical_model_id": "kling-3.0-omni/reference-to-video", "task": "reference-to-video"},
        },
        "default": "t2v",
    },
    "kling-3-0": {
        "name": "Kling 3.0",
        "routes": {
            "video": {"canonical_model_id": "kling-3.0/video", "task": "text-to-video"},
            "motion": {"canonical_model_id": "kling-3.0/motion-control", "task": "motion-control"},
        },
        "default": "video",
    },
    "kling-2-6": {
        "name": "Kling 2.6",
        "routes": {
            "motion": {"canonical_model_id": "kling-2.6/motion-control", "task": "motion-control"},
        },
        "default": "motion",
    },
    "kling-2-5-turbo": {
        "name": "Kling 2.5 Turbo",
        "routes": {
            "t2v": {"canonical_model_id": "kling/v2-5-turbo-text-to-video-pro", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "kling/v2-5-turbo-image-to-video-pro", "task": "image-to-video"},
        },
        "default": "t2v",
    },
    "bytedance": {
        "name": "ByteDance Seedance",
        "routes": {
            "seedance-2-5": {"canonical_model_id": "bytedance/seedance-2-5", "task": "text-to-video"},
            "seedance-2-mini": {"canonical_model_id": "bytedance/seedance-2-mini", "task": "text-to-video"},
        },
        "default": "seedance-2-5",
    },
    "pixverse-v6": {
        "name": "PixVerse V6",
        "routes": {
            "t2v": {"canonical_model_id": "pixverse-v6/text-to-video", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "pixverse-v6/image-to-video", "task": "image-to-video"},
            "transition": {"canonical_model_id": "pixverse-v6/transition", "task": "transition"},
            "extend": {"canonical_model_id": "pixverse-v6/extend", "task": "extend"},
            "r2v": {"canonical_model_id": "pixverse-v6/reference-to-video", "task": "reference-to-video"},
        },
        "default": "t2v",
    },
    "minimax-h3": {
        "name": "MiniMax H3",
        "routes": {
            "t2v": {"canonical_model_id": "minimax-h3/text-to-video", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "minimax-h3/image-to-video", "task": "image-to-video"},
            "r2v": {"canonical_model_id": "minimax-h3/reference-to-video", "task": "reference-to-video"},
        },
        "default": "t2v",
    },
    "wan-2-7": {
        "name": "Wan 2.7 Video",
        "routes": {
            "r2v": {"canonical_model_id": "wan/2-7-r2v", "task": "reference-to-video"},
            "videoedit": {"canonical_model_id": "wan/2-7-videoedit", "task": "video-edit"},
            "t2v": {"canonical_model_id": "wan/2-7-text-to-video", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "wan/2-7-image-to-video", "task": "image-to-video"},
        },
        "default": "t2v",
    },
    "happyhorse-1-1": {
        "name": "HappyHorse 1.1",
        "routes": {
            "t2v": {"canonical_model_id": "happyhorse-1-1/text-to-video", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "happyhorse-1-1/image-to-video", "task": "image-to-video"},
            "r2v": {"canonical_model_id": "happyhorse-1-1/reference-to-video", "task": "reference-to-video"},
        },
        "default": "t2v",
    },
    "happyhorse": {
        "name": "HappyHorse 1.0",
        "routes": {
            "t2v": {"canonical_model_id": "happyhorse/text-to-video", "task": "text-to-video"},
            "i2v": {"canonical_model_id": "happyhorse/image-to-video", "task": "image-to-video"},
            "r2v": {"canonical_model_id": "happyhorse/reference-to-video", "task": "reference-to-video"},
            "edit": {"canonical_model_id": "happyhorse/video-edit", "task": "video-edit"},
        },
        "default": "t2v",
    },
    "gemini-omni-video": {
        "name": "Gemini Omni Video",
        "routes": {
            "all": {"canonical_model_id": "gemini-omni-video", "task": "multimodal-video"},
        },
        "default": "all",
    },
    "runway": {
        "name": "Runway Dedicated",
        "routes": {
            "all": {"canonical_model_id": "runway", "task": "text-to-video"},
        },
        "default": "all",
    },
    "veo3": {
        "name": "Veo 3.1 Dedicated",
        "routes": {
            "quality": {"canonical_model_id": "veo3", "task": "text-to-video"},
            "fast": {"canonical_model_id": "veo3_fast", "task": "text-to-video"},
            "lite": {"canonical_model_id": "veo3_lite", "task": "text-to-video"},
        },
        "default": "fast",
    },
}

# Alias map for natural-language extraction (longest match wins)
ALIASES = {
    # Wan 3.0 / Prime
    "wan 3.0 video prime": "wan-3-0",
    "wan 3.0 prime": "wan-3-0",
    "wan 3 prime": "wan-3-0",
    "wan/3-0-video-prime": "wan-3-0",
    "wan/3-0-video": "wan-3-0",
    "wan 3.0 video": "wan-3-0",
    "wan 3.0": "wan-3-0",
    "wan 3": "wan-3-0",
    "wan3": "wan-3-0",
    # Kling Omni
    "kling-3.0-omni/reference-to-video": "kling-3-0-omni",
    "kling-3.0-omni/transformation": "kling-3-0-omni",
    "kling-3.0-omni/image-to-video": "kling-3-0-omni",
    "kling-3.0-omni/text-to-video": "kling-3-0-omni",
    "kling 3.0 omni": "kling-3-0-omni",
    "kling 3 omni": "kling-3-0-omni",
    "kling omni 3": "kling-3-0-omni",
    "kling-omni": "kling-3-0-omni",
    "kling omni": "kling-3-0-omni",
    "kling o3": "kling-3-0-omni",
    "kling-o3": "kling-3-0-omni",
    # Kling 3.0 Single/Multi / Motion Control
    "kling-3.0/motion-control": "kling-3-0",
    "kling-3.0/video": "kling-3-0",
    "kling 3.0 motion control": "kling-3-0",
    "kling 3 motion control": "kling-3-0",
    "kling 3.0 motion": "kling-3-0",
    "kling 3.0": "kling-3-0",
    "kling 3": "kling-3-0",
    "kling3": "kling-3-0",
    # Kling 2.6
    "kling-2.6/motion-control": "kling-2-6",
    "kling 2.6 motion control": "kling-2-6",
    "kling 2.6 motion": "kling-2-6",
    "kling 2.6": "kling-2-6",
    # Kling 2.5 Turbo
    "kling/v2-5-turbo-image-to-video-pro": "kling-2-5-turbo",
    "kling/v2-5-turbo-text-to-video-pro": "kling-2-5-turbo",
    "kling 2.5 turbo image": "kling-2-5-turbo",
    "kling 2.5 turbo pro": "kling-2-5-turbo",
    "kling 2.5 turbo": "kling-2-5-turbo",
    "kling turbo pro": "kling-2-5-turbo",
    "kling turbo": "kling-2-5-turbo",
    "kling 2.5": "kling-2-5-turbo",
    "kling": "kling-2-5-turbo",
    "cling": "kling-2-5-turbo",
    # ByteDance / Seedance
    "bytedance/seedance-2-5": "bytedance",
    "bytedance/seedance-2-mini": "bytedance",
    "seedance 2.5": "bytedance",
    "seedance-2-5": "bytedance",
    "seedance 2 mini": "bytedance",
    "seedance mini": "bytedance",
    "seedance-2-mini": "bytedance",
    "seedance": "bytedance",
    "seed dance": "bytedance",
    "sea dance": "bytedance",
    "bytedance": "bytedance",
    # PixVerse V6
    "pixverse-v6/reference-to-video": "pixverse-v6",
    "pixverse-v6/transition": "pixverse-v6",
    "pixverse-v6/extend": "pixverse-v6",
    "pixverse-v6/image-to-video": "pixverse-v6",
    "pixverse-v6/text-to-video": "pixverse-v6",
    "pixverse v6 transition": "pixverse-v6",
    "pixverse v6 extend": "pixverse-v6",
    "pixverse v6": "pixverse-v6",
    "pixverse-v6": "pixverse-v6",
    "pixverse 6": "pixverse-v6",
    "pixverse": "pixverse-v6",
    "pix verse": "pixverse-v6",
    # MiniMax H3
    "minimax-h3/reference-to-video": "minimax-h3",
    "minimax-h3/image-to-video": "minimax-h3",
    "minimax-h3/text-to-video": "minimax-h3",
    "minimax h3": "minimax-h3",
    "minimax-h3": "minimax-h3",
    "minimax": "minimax-h3",
    "mini max": "minimax-h3",
    "hailuo": "minimax-h3",
    # Wan 2.7
    "wan/2-7-videoedit": "wan-2-7",
    "wan/2-7-r2v": "wan-2-7",
    "wan/2-7-image-to-video": "wan-2-7",
    "wan/2-7-text-to-video": "wan-2-7",
    "wan 2.7 video edit": "wan-2-7",
    "wan 2.7 videoedit": "wan-2-7",
    "wan 2.7 r2v": "wan-2-7",
    "wan 2.7 video": "wan-2-7",
    "wan 2.7": "wan-2-7",
    "wan2.7": "wan-2-7",
    "wan": "wan-2-7",
    # HappyHorse 1.1
    "happyhorse-1-1/reference-to-video": "happyhorse-1-1",
    "happyhorse-1-1/image-to-video": "happyhorse-1-1",
    "happyhorse-1-1/text-to-video": "happyhorse-1-1",
    "happyhorse 1.1": "happyhorse-1-1",
    "happyhorse-1-1": "happyhorse-1-1",
    "happy horse 1.1": "happyhorse-1-1",
    # HappyHorse 1.0
    "happyhorse/video-edit": "happyhorse",
    "happyhorse/reference-to-video": "happyhorse",
    "happyhorse/image-to-video": "happyhorse",
    "happyhorse/text-to-video": "happyhorse",
    "happyhorse 1.0": "happyhorse",
    "happyhorse": "happyhorse",
    "happy horse": "happyhorse",
    # Gemini Omni Video
    "gemini-omni-video": "gemini-omni-video",
    "gemini omni video": "gemini-omni-video",
    "gemini omni": "gemini-omni-video",
    "gemini video": "gemini-omni-video",
    # Runway Dedicated
    "runway gen3": "runway",
    "runway gen 3": "runway",
    "runway gen-3": "runway",
    "runway": "runway",
    # Veo Dedicated
    "veo3_fast": "veo3",
    "veo3_lite": "veo3",
    "veo3": "veo3",
    "veo 3.1 fast": "veo3",
    "veo 3.1 lite": "veo3",
    "veo 3.1": "veo3",
    "veo 3 fast": "veo3",
    "veo 3 lite": "veo3",
    "veo 3": "veo3",
    "veo fast": "veo3",
    "veo lite": "veo3",
    "veo": "veo3",
}

MODEL_TO_FAMILY = {}
for fam, spec in REGISTRY.items():
    for rinfo in spec["routes"].values():
        MODEL_TO_FAMILY[rinfo["canonical_model_id"]] = fam

TASKS = {
    "transition": "transition",
    "extend": "extend",
    "extension": "extend",
    "transformation": "transformation",
    "transform": "transformation",
    "style transfer": "transformation",
    "motion control": "motion-control",
    "motion-control": "motion-control",
    "motion transfer": "motion-control",
    "puppet": "motion-control",
    "puppeteer": "motion-control",
    "video edit": "video-edit",
    "video-edit": "video-edit",
    "videoedit": "video-edit",
    "edit video": "video-edit",
    "reference-to-video": "reference-to-video",
    "reference to video": "reference-to-video",
    "r2v": "reference-to-video",
    "reference": "reference-to-video",
    "references": "reference-to-video",
    "image-to-video": "image-to-video",
    "image to video": "image-to-video",
    "i2v": "image-to-video",
    "animate image": "image-to-video",
    "first frame": "image-to-video",
    "keyframe": "image-to-video",
    "text-to-video": "text-to-video",
    "text to video": "text-to-video",
    "t2v": "text-to-video",
    "generate": "text-to-video",
    "create": "text-to-video",
}

RESOLUTION_HINTS = {
    "4k": "4k",
    "2k": "2k",
    "1080p": "1080p",
    "720p": "720p",
    "540p": "540p",
    "480p": "480p",
    "360p": "360p",
}


def normalize(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def detect_task(text):
    norm = normalize(text)
    for key, task in TASKS.items():
        if re.search(r"(^|[\s,.!?/])" + re.escape(key) + r"($|[\s,.!?/])", norm):
            return task
    return "text-to-video"


def detect_resolution(text):
    norm = normalize(text)
    for k, v in RESOLUTION_HINTS.items():
        if re.search(r"\b" + re.escape(k) + r"\b", norm):
            return v
    return None


def detect_duration(text):
    """Detect duration in seconds if specified (e.g. 20s, 20 seconds, 90-second)."""
    norm = normalize(text)
    m = re.search(r"\b(\d+)\s*-?\s*(?:s\b|sec\b|secs\b|second\b|seconds\b)", norm)
    if m:
        return int(m.group(1))
    return None


def match_alias(norm):
    best_alias, best_fam = None, None
    for alias, fam in ALIASES.items():
        if re.search(r"(^|[\s,.!?/])" + re.escape(alias) + r"($|[\s,.!?/])", norm):
            if best_alias is None or len(alias) > len(best_alias):
                best_alias, best_fam = alias, fam
    return best_alias, best_fam


def match_canonical(norm):
    for model_id in sorted(MODEL_TO_FAMILY, key=len, reverse=True):
        pat = r"(^|[\s,./])" + re.escape(model_id) + r"($|[\s,./])"
        if re.search(pat, norm):
            return model_id
    return None


def family_from_text(text):
    norm = normalize(text)
    model_id = match_canonical(norm)
    if model_id:
        return MODEL_TO_FAMILY[model_id], model_id, model_id
    alias, fam = match_alias(norm)
    if fam:
        return fam, None, alias
    return None, None, None


def autonomous_route(request):
    """Route autonomously using capability hierarchy in references/models.md section 2."""
    norm = normalize(request)
    dur = detect_duration(request)
    task = detect_task(request)
    res = detect_resolution(request)

    # 1. Dedicated requests
    if re.search(r"\brunway\b", norm):
        return "runway", None
    if re.search(r"\bveo\b", norm):
        return "veo3", None

    # 2. Puppeteering / motion control
    if task == "motion-control" or re.search(r"\b(puppet|puppeteer|motion transfer|driving video)\b", norm):
        return "kling-3-0", "kling-3.0/motion-control"

    # 3. Video editing / modification
    if task == "video-edit" or re.search(r"\b(video edit|edit video|inpainting|repainting)\b", norm):
        return "wan-2-7", "wan/2-7-videoedit"

    # 4. Multi-shot storyboard / cinematic storyboard
    if re.search(r"\b(multi[- ]shot|storyboard|shots|shot sequence)\b", norm):
        return "kling-3-0-omni", "kling-3.0-omni/text-to-video"

    # 5. Character consistency / character slots
    if re.search(r"\b(character slot|character slots|character[- ]consistent|char_id)\b", norm):
        return "gemini-omni-video", "gemini-omni-video"

    # 6. High resolution 2K native
    if res == "2k" or re.search(r"\b2k\b", norm):
        if task == "image-to-video":
            return "minimax-h3", "minimax-h3/image-to-video"
        if task == "reference-to-video":
            return "minimax-h3", "minimax-h3/reference-to-video"
        return "minimax-h3", "minimax-h3/text-to-video"

    # 7. Long-form (>15s) or rich multimodal references
    if (dur is not None and dur > 15) or re.search(r"\b(long[- ]form|narrative|extended duration|30s|20s|25s)\b", norm):
        if re.search(r"\b(seedance|bytedance|50 assets|30 images)\b", norm):
            return "bytedance", "bytedance/seedance-2-5"
        return "wan-3-0", "wan/3-0-video"

    # 8. Short + cheap / fast turnaround
    if re.search(r"\b(short\s*\+\s*cheap|cheap|fast turnaround|budget|low cost)\b", norm):
        if task == "image-to-video":
            return "kling-2-5-turbo", "kling/v2-5-turbo-image-to-video-pro"
        return "kling-2-5-turbo", "kling/v2-5-turbo-text-to-video-pro"

    # 9. PixVerse transition / extend
    if task == "transition":
        return "pixverse-v6", "pixverse-v6/transition"
    if task == "extend":
        return "pixverse-v6", "pixverse-v6/extend"

    # Default general high-fidelity video route -> Wan 3.0
    return "wan-3-0", "wan/3-0-video"


def choose_answer(family, request, explicit_model_id):
    norm = normalize(request)
    fam_spec = REGISTRY[family]
    routes = fam_spec["routes"]
    task = detect_task(request)
    res = detect_resolution(request)
    dur = detect_duration(request)

    # If explicit canonical model id matched in request, check validity and return it
    if explicit_model_id:
        return _ok(explicit_model_id, f"Explicit canonical model requested: {explicit_model_id}")

    # --- Wan 3.0 ---
    if family == "wan-3-0":
        if re.search(r"\b(prime|throughput|fast)\b", norm):
            return _ok(routes["prime"]["canonical_model_id"], "Wan 3.0 Prime route chosen")
        return _ok(routes["std"]["canonical_model_id"], "Wan 3.0 Video standard route")

    # --- Kling 3.0 Omni ---
    if family == "kling-3-0-omni":
        if task == "transformation" or re.search(r"\b(transform|transformation|style transfer)\b", norm):
            return _ok(routes["transform"]["canonical_model_id"], "Kling 3.0 Omni transformation route")
        if task == "reference-to-video" or re.search(r"\b(reference|r2v)\b", norm):
            return _ok(routes["r2v"]["canonical_model_id"], "Kling 3.0 Omni reference-to-video route")
        if task == "image-to-video" or re.search(r"\b(i2v|image to video|animate image|first frame)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "Kling 3.0 Omni image-to-video route")
        return _ok(routes["t2v"]["canonical_model_id"], "Kling 3.0 Omni text-to-video route")

    # --- Kling 3.0 ---
    if family == "kling-3-0":
        if task == "motion-control" or re.search(r"\b(motion|puppet|puppeteer)\b", norm):
            return _ok(routes["motion"]["canonical_model_id"], "Kling 3.0 motion control route")
        return _ok(routes["video"]["canonical_model_id"], "Kling 3.0 video route")

    # --- Kling 2.6 ---
    if family == "kling-2-6":
        return _ok(routes["motion"]["canonical_model_id"], "Kling 2.6 motion control route")

    # --- Kling 2.5 Turbo ---
    if family == "kling-2-5-turbo":
        if task == "image-to-video" or re.search(r"\b(image to video|i2v|image)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "Kling 2.5 Turbo image-to-video pro route")
        return _ok(routes["t2v"]["canonical_model_id"], "Kling 2.5 Turbo text-to-video pro route")

    # --- ByteDance / Seedance ---
    if family == "bytedance":
        if re.search(r"\b(mini|lite|speed|fast)\b", norm):
            return _ok(routes["seedance-2-mini"]["canonical_model_id"], "ByteDance Seedance 2.0 Mini route")
        return _ok(routes["seedance-2-5"]["canonical_model_id"], "ByteDance Seedance 2.5 route")

    # --- PixVerse V6 ---
    if family == "pixverse-v6":
        if task == "transition" or re.search(r"\btransition\b", norm):
            return _ok(routes["transition"]["canonical_model_id"], "PixVerse V6 transition route")
        if task == "extend" or re.search(r"\b(extend|extension)\b", norm):
            return _ok(routes["extend"]["canonical_model_id"], "PixVerse V6 extend route")
        if task == "reference-to-video" or re.search(r"\b(reference|r2v)\b", norm):
            return _ok(routes["r2v"]["canonical_model_id"], "PixVerse V6 reference-to-video route")
        if task == "image-to-video" or re.search(r"\b(image to video|i2v|image)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "PixVerse V6 image-to-video route")
        return _ok(routes["t2v"]["canonical_model_id"], "PixVerse V6 text-to-video route")

    # --- MiniMax H3 ---
    if family == "minimax-h3":
        if task == "reference-to-video" or re.search(r"\b(reference|r2v)\b", norm):
            return _ok(routes["r2v"]["canonical_model_id"], "MiniMax H3 reference-to-video route")
        if task == "image-to-video" or re.search(r"\b(image to video|i2v|image)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "MiniMax H3 image-to-video route")
        return _ok(routes["t2v"]["canonical_model_id"], "MiniMax H3 text-to-video route")

    # --- Wan 2.7 ---
    if family == "wan-2-7":
        if task == "video-edit" or re.search(r"\b(edit|videoedit|inpainting|repainting)\b", norm):
            return _ok(routes["videoedit"]["canonical_model_id"], "Wan 2.7 video edit route")
        if task == "reference-to-video" or re.search(r"\b(reference|r2v|voice)\b", norm):
            return _ok(routes["r2v"]["canonical_model_id"], "Wan 2.7 reference-to-video route")
        if task == "image-to-video" or re.search(r"\b(image to video|i2v|image)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "Wan 2.7 image-to-video route")
        return _ok(routes["t2v"]["canonical_model_id"], "Wan 2.7 text-to-video route")

    # --- HappyHorse 1.1 ---
    if family == "happyhorse-1-1":
        if task == "reference-to-video" or re.search(r"\b(reference|r2v)\b", norm):
            return _ok(routes["r2v"]["canonical_model_id"], "HappyHorse 1.1 reference-to-video route")
        if task == "image-to-video" or re.search(r"\b(image to video|i2v|image)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "HappyHorse 1.1 image-to-video route")
        return _ok(routes["t2v"]["canonical_model_id"], "HappyHorse 1.1 text-to-video route")

    # --- HappyHorse 1.0 ---
    if family == "happyhorse":
        if task == "video-edit" or re.search(r"\b(edit|videoedit)\b", norm):
            return _ok(routes["edit"]["canonical_model_id"], "HappyHorse 1.0 video edit route")
        if task == "reference-to-video" or re.search(r"\b(reference|r2v)\b", norm):
            return _ok(routes["r2v"]["canonical_model_id"], "HappyHorse 1.0 reference-to-video route")
        if task == "image-to-video" or re.search(r"\b(image to video|i2v|image)\b", norm):
            return _ok(routes["i2v"]["canonical_model_id"], "HappyHorse 1.0 image-to-video route")
        return _ok(routes["t2v"]["canonical_model_id"], "HappyHorse 1.0 text-to-video route")

    # --- Gemini Omni Video ---
    if family == "gemini-omni-video":
        return _ok(routes["all"]["canonical_model_id"], "Gemini Omni Video route")

    # --- Runway Dedicated ---
    if family == "runway":
        return _ok(routes["all"]["canonical_model_id"], "Runway dedicated route")

    # --- Veo Dedicated ---
    if family == "veo3":
        if re.search(r"\b(quality|ultra|pro)\b", norm):
            return _ok(routes["quality"]["canonical_model_id"], "Veo 3.1 Quality route")
        if re.search(r"\blite\b", norm):
            return _ok(routes["lite"]["canonical_model_id"], "Veo 3.1 Lite route")
        return _ok(routes["fast"]["canonical_model_id"], "Veo 3.1 Fast route (default)")

    # Fallback default
    default = fam_spec.get("default")
    if default and default in routes:
        return _ok(routes[default]["canonical_model_id"], fam_spec["name"] + " default route")
    first = list(routes.values())[0]
    return _ok(first["canonical_model_id"], fam_spec["name"] + " first route")


def _ok(model_id, reason):
    return {"valid": True, "selected_model_id": model_id, "reason": reason, "alternative": None}


# Module cache for registry lookups (duration_window_seconds high bounds)
_REG_DATA = None
_REG_BY_ID = None


def registry_by_id():
    """Load models.json registry for duration max lookups (stdlib json only)."""
    global _REG_DATA, _REG_BY_ID
    if _REG_BY_ID is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")
        with open(path, "r", encoding="utf-8") as fh:
            _REG_DATA = json.load(fh)
        _REG_BY_ID = {m["canonical_model_id"]: m for m in _REG_DATA["models"]}
    return _REG_BY_ID


def duration_max_for(model_id):
    """Return the max supported duration (high bound) for a model, or None.

    Handles both window shapes found in models.json:
      [3, 15]             -> 15
      "2-30s (or -1 auto)" -> 30
      "4, 6, 8s (default 8)" -> 8 (max discrete option)
    """
    entry = registry_by_id().get(model_id)
    if entry is None:
        return None
    window = entry.get("duration_window_seconds")
    if isinstance(window, list) and len(window) == 2:
        return float(window[1])
    if isinstance(window, str):
        m = re.search(r"(\d+)\s*-\s*(\d+)\s*s", window)
        if m:
            return float(m.group(2))
        nums = [float(x) for x in re.findall(r"\b(\d+)\s*s?\b", window)]
        if nums:
            return max(nums)
    return None


def clip_plan_note(model_id, dur):
    """Note when the detected target duration exceeds the model's max."""
    max_dur = duration_max_for(model_id)
    if max_dur is None or dur is None or dur <= max_dur:
        return None
    n = int(-(-dur // max_dur))  # ceil without importing math
    return (
        f"target {dur}s exceeds {model_id} max {int(max_dur) if max_dur == int(max_dur) else max_dur}s; "
        f"plan {n} clips (N = ceil({dur}/{int(max_dur) if max_dur == int(max_dur) else max_dur})) or choose a "
        f"longer-max model (Wan 3.0 / Seedance 2.5 reach 30s)"
    )


def select(request):
    family, explicit_id, frag = family_from_text(request)
    if family is None:
        family, auto_model_id = autonomous_route(request)
        if explicit_id is None:
            explicit_id = auto_model_id
    ans = choose_answer(family, request, explicit_id)

    notes = []
    dur = detect_duration(request)
    note = clip_plan_note(ans["selected_model_id"], dur)
    if note:
        notes.append(note)

    return {
        "request": request,
        "selected_model_id": ans["selected_model_id"],
        "selected_family": family,
        "task": detect_task(request),
        "resolution": detect_resolution(request),
        "duration": dur,
        "compatibility": "full" if ans["valid"] else "conflict",
        "reason": ans["reason"],
        "alternative": ans["alternative"],
        "notes": notes,
        "valid": ans["valid"],
    }


# ---------------------------------------------------------------------------
# Self-test battery: at least 30 fixtures covering all families and routing
# ---------------------------------------------------------------------------

SELFTEST_CASES = [
    # 1. Wan 3.0 Video standard
    ("cinematic documentary of ocean, use wan 3.0 video", "wan/3-0-video", True, None),
    # 2. Wan 3.0 Prime
    ("high throughput wan 3.0 prime video generation", "wan/3-0-video-prime", True, None),
    # 3. Kling 3.0 Omni T2V
    ("kling 3.0 omni text to video 5 shot storyboard", "kling-3.0-omni/text-to-video", True, None),
    # 4. Kling 3.0 Omni I2V
    ("kling 3.0 omni image to video keyframe animation", "kling-3.0-omni/image-to-video", True, None),
    # 5. Kling 3.0 Omni Transformation
    ("kling 3.0 omni transformation style transfer on source video", "kling-3.0-omni/transformation", True, None),
    # 6. Kling 3.0 Omni Reference to video
    ("kling 3.0 omni reference to video with 3 subject images", "kling-3.0-omni/reference-to-video", True, None),
    # 7. Kling 3.0 Video
    ("kling 3.0 video single shot scene", "kling-3.0/video", True, None),
    # 8. Kling 3.0 Motion Control
    ("kling 3.0 motion control driving video puppet character", "kling-3.0/motion-control", True, None),
    # 9. Kling 2.6 Motion Control
    ("kling 2.6 motion control character puppet", "kling-2.6/motion-control", True, None),
    # 10. Kling 2.5 Turbo T2V
    ("kling 2.5 turbo text to video pro fast generation", "kling/v2-5-turbo-text-to-video-pro", True, None),
    # 11. Kling 2.5 Turbo I2V
    ("kling 2.5 turbo image to video pro start image", "kling/v2-5-turbo-image-to-video-pro", True, None),
    # 12. ByteDance Seedance 2.5
    ("bytedance seedance 2.5 extended 30s scene with audio", "bytedance/seedance-2-5", True, None),
    # 13. ByteDance Seedance 2.0 Mini
    ("seedance 2 mini fast lower cost generation", "bytedance/seedance-2-mini", True, None),
    # 14. PixVerse V6 T2V
    ("pixverse v6 text to video commercial clip", "pixverse-v6/text-to-video", True, None),
    # 15. PixVerse V6 I2V
    ("pixverse v6 image to video dynamic motion", "pixverse-v6/image-to-video", True, None),
    # 16. PixVerse V6 Transition
    ("pixverse v6 transition between start and end image", "pixverse-v6/transition", True, None),
    # 17. PixVerse V6 Extend
    ("pixverse v6 extend previous video clip", "pixverse-v6/extend", True, None),
    # 18. PixVerse V6 R2V
    ("pixverse v6 reference to video with background reference", "pixverse-v6/reference-to-video", True, None),
    # 19. MiniMax H3 T2V
    ("minimax h3 text to video in 2k resolution", "minimax-h3/text-to-video", True, None),
    # 20. MiniMax H3 I2V
    ("minimax h3 image to video high definition animation", "minimax-h3/image-to-video", True, None),
    # 21. MiniMax H3 R2V
    ("minimax h3 reference to video driving assets", "minimax-h3/reference-to-video", True, None),
    # 22. Wan 2.7 R2V
    ("wan 2.7 r2v with voice clone audio driving", "wan/2-7-r2v", True, None),
    # 23. Wan 2.7 Video Edit
    ("wan 2.7 video edit repainting source video", "wan/2-7-videoedit", True, None),
    # 24. Wan 2.7 T2V
    ("wan 2.7 text to video with soundtrack", "wan/2-7-text-to-video", True, None),
    # 25. Wan 2.7 I2V
    ("wan 2.7 image to video first frame", "wan/2-7-image-to-video", True, None),
    # 26. HappyHorse 1.1 T2V
    ("happyhorse 1.1 text to video bilingual scene", "happyhorse-1-1/text-to-video", True, None),
    # 27. HappyHorse 1.1 I2V
    ("happyhorse 1.1 image to video portrait", "happyhorse-1-1/image-to-video", True, None),
    # 28. HappyHorse 1.1 R2V
    ("happyhorse 1.1 reference to video using [Image 1] syntax", "happyhorse-1-1/reference-to-video", True, None),
    # 29. HappyHorse 1.0 T2V
    ("happyhorse text to video scene", "happyhorse/text-to-video", True, None),
    # 30. HappyHorse 1.0 Edit
    ("happyhorse video edit modification", "happyhorse/video-edit", True, None),
    # 31. Gemini Omni Video
    ("gemini omni video with character slots and voice sync", "gemini-omni-video", True, None),
    # 32. Runway Dedicated
    ("cinematic sequence via runway gen 3", "runway", True, None),
    # 33. Veo 3.1 Quality
    ("veo 3.1 quality 8s scene", "veo3", True, None),
    # 34. Veo 3.1 Fast
    ("veo 3.1 fast generation 6s", "veo3_fast", True, None),
    # 35. Veo 3.1 Lite
    ("veo 3 lite lightweight render", "veo3_lite", True, None),
    # 36. Autonomous routing: Long-form >15s -> wan/3-0-video
    ("generate a 25s continuous dramatic narrative video of space station", "wan/3-0-video", True, None),
    # 37. Autonomous routing: Multi-shot storyboard -> kling-3.0-omni/text-to-video
    ("create a multi-shot storyboard sequence of a detective investigation", "kling-3.0-omni/text-to-video", True, None),
    # 38. Autonomous routing: 2K resolution -> minimax-h3/text-to-video
    ("render high quality 2K video of futuristic sports car", "minimax-h3/text-to-video", True, None),
    # 39. Autonomous routing: Puppeteer -> kling-3.0/motion-control
    ("puppeteer this character portrait using the driving dance video", "kling-3.0/motion-control", True, None),
    # 40. Autonomous routing: Short + cheap -> kling/v2-5-turbo-text-to-video-pro
    ("fast turnaround short + cheap video clip of rain falling", "kling/v2-5-turbo-text-to-video-pro", True, None),
]


def note_cases():
    """Cases where an over-max target duration must produce a clip-plan note."""
    return [
        # "90 second" form: routed to wan/3-0-video, note with ceil(90/30)=3 clips
        ("generate a 90 second cinematic trailer", "wan/3-0-video", "target 90s exceeds"),
        # "90-second" hyphenated form: same detection via updated regex
        ("90-second epic opening sequence", "wan/3-0-video", "target 90s exceeds"),
        # 60s target on wan 3.0 (max 30s) -> 2 clips
        ("generate a 60 second cinematic trailer", "wan/3-0-video", "plan 2 clips"),
    ]


def selftest():
    failures = []
    for req, exp_id, exp_valid, exp_alt in SELFTEST_CASES:
        res = select(req)
        got_bad = (
            res["selected_model_id"] != exp_id
            or res["valid"] != exp_valid
            or res["alternative"] != exp_alt
        )
        if got_bad:
            failures.append(
                f"FAIL {req!r}: expected id={exp_id} valid={exp_valid} alt={exp_alt}; "
                f"got id={res['selected_model_id']} valid={res['valid']} alt={res['alternative']}"
            )
    if failures:
        print("select_video_model.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1

    for req, exp_id, expect_note in note_cases():
        res = select(req)
        if res["selected_model_id"] != exp_id:
            failures.append(f"FAIL note-case {req!r}: expected id={exp_id} got={res['selected_model_id']}")
        elif not any(expect_note in n for n in res["notes"]):
            failures.append(
                f"FAIL note-case {req!r}: expected note containing {expect_note!r} got notes={res['notes']}"
            )

    if failures:
        print("select_video_model.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    total = len(SELFTEST_CASES) + len(note_cases())
    print(f"select_video_model.py --self-test: {total}/{total} passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIE video model selector (skill 67)")
    parser.add_argument("request", nargs="?", help="natural-language video request")
    parser.add_argument("--self-test", action="store_true", help="run deterministic battery and exit")
    parser.add_argument("--json", action="store_true", help="same as default output (JSON)")
    args = parser.parse_args(argv)

    if args.self_test:
        return selftest()
    if not args.request:
        parser.error("request required (or use --self-test)")
    result = select(args.request)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
