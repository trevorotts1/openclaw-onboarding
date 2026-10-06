#!/usr/bin/env python3
"""kie_media_plan.py - Skill 35 media plan for one publishing cycle (STDLIB ONLY).

run-publishing-cycle.sh calls this once per cycle. It reads the client's optional
~/.openclaw/config/image-model.json and video-specs.json and prints ONE JSON object
that goes into cycle-manifest.json under "media": the image model the cycle will
use, the Skill 74 steps every paid job runs, and where Skill 67 (video) lives.

Policy (owner order 2026-10-05, AGENTS.md N43, 07-kie-setup/references/kie-common-rules.md):
  * Social images are KIE GPT Image 2.5 Sunburst. Rule 13 keeps that default at the newest
    GPT Image generation: the resolver is `kie_live_adapter.py latest-family --family gpt-image`
    (Skill 74). This script makes no network call; the cycle agent runs the resolver.
  * Nano Banana, Midjourney, Ideogram and any other non-GPT-Image id in image-model.json is
    NOT a Skill 35 route: it is ignored and reported as a violation (never silent).
  * Legacy gpt-image-2 (not 2.5) is only for the ratios 3:1, 1:3, 9:21, which Skill 35 never
    produces: ignored and reported.
  * Video is chosen by the Skill 67 selector. A Sora id in video-specs.json is ignored and
    reported; this script never names a video model other than the documented default request.
  * No prices, no prompt-length numbers here: Skill 74 `price` and `prompt-budget` own them.

Exit 0 always for a readable plan (violations are data); 2 on bad arguments.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_T2I = "gpt-image-2-5-sunburst-text-to-image"
DEFAULT_I2I = "gpt-image-2-5-sunburst-image-to-image"
DEFAULT_VIDEO_REQUEST = "veo3_lite"  # Skill 35 default request; the Skill 67 selector decides
MODEL_KEYS = ("model", "image_model", "default_model", "default", "primary")
VIDEO_MODEL_KEYS = ("model", "video_model", "provider_model", "engine", "default_model")
LEGACY_V2 = re.compile(r"^gpt-image-2(?!-5)(-|$)")


def _load(path):
    if not path:
        return None, "not configured"
    p = Path(path)
    if not p.is_file():
        return None, "file not present"
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, "unreadable: %s" % type(exc).__name__
    return (obj if isinstance(obj, dict) else None), (None if isinstance(obj, dict) else "not a JSON object")


def _first_str(obj, keys):
    for k in keys:
        v = obj.get(k) if isinstance(obj, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def judge_image_model(requested):
    """-> (accepted: bool, reason). Only the GPT Image family at the 2.5 generation or newer."""
    m = (requested or "").strip().lower().split("/")[-1]
    if not m:
        return True, "none requested"
    if LEGACY_V2.match(m):
        return False, "legacy GPT Image 2 is only for 3:1, 1:3 and 9:21 (AGENTS.md N43); Skill 35 produces none"
    if "flare" in m:
        return False, "flare variants are not registered; they need a new owner ruling"
    if m.startswith("gpt-image-"):
        return True, "GPT Image family"
    return False, "not a Skill 35 image route (owner order 2026-10-05: social images are GPT Image 2.5 Sunburst)"


def find_skill(skill_dir, openclaw_dir, name, rel):
    roots = [Path(skill_dir).parent, Path(openclaw_dir) / "skills", Path("/data/.openclaw/skills")]
    for r in roots:
        p = r / name / rel
        if p.is_file():
            return str(p)
    return None


def build_plan(image_cfg_path, video_cfg_path, skill_dir, openclaw_dir):
    violations = []
    icfg, inote = _load(image_cfg_path)
    requested = _first_str(icfg, MODEL_KEYS)
    accepted, why = judge_image_model(requested)
    if requested and not accepted:
        violations.append({"file": "image-model.json", "value": requested, "action": "ignored, default used", "reason": why})
    image_model = requested if (requested and accepted) else DEFAULT_T2I
    i2i = image_model.replace("text-to-image", "image-to-image") if "text-to-image" in image_model else DEFAULT_I2I

    vcfg, vnote = _load(video_cfg_path)
    vreq = _first_str(vcfg, VIDEO_MODEL_KEYS)
    if vreq and "sora" in vreq.lower():
        violations.append({"file": "video-specs.json", "value": vreq, "action": "ignored, Skill 67 selector used",
                           "reason": "OpenAI Sora is prohibited; Skill 67 owns video model selection"})
    adapter = find_skill(skill_dir, openclaw_dir, "74-kie-live-adapter", "scripts/kie_live_adapter.py")
    selector = find_skill(skill_dir, openclaw_dir, "67-kie-video", "scripts/select_video_model.py")
    cli = "python3 %s" % (adapter or "74-kie-live-adapter/scripts/kie_live_adapter.py")
    return {
        "policy": "07-kie-setup/references/kie-common-rules.md (rules 12 and 13)",
        "image": {
            "config_file": image_cfg_path, "config_note": inote,
            "text_to_image": image_model, "image_to_image": i2i,
            "auto_latest": "%s latest-family --family gpt-image --capability \"Text to Image,Image to Image\" --current-default %s --json" % (cli, DEFAULT_T2I),
            "per_job_steps": [
                "pregen_prompt_gate.py check (Skill 35 gate, Section 8a)",
                "%s prompt-budget --model <id> --check --prompt-file <f>" % cli,
                "%s validate --model <id> --payload <input.json>" % cli,
                "%s preflight --model <id>" % cli,
                "%s run --request <req.json> --save-dir <dir> --mode active --json" % cli,
                "upload the saved file to the GHL Media Library; use only the CDN url",
            ],
        },
        "video": {
            "config_file": video_cfg_path, "config_note": vnote,
            "owner": "67-kie-video", "selector": selector, "default_request": DEFAULT_VIDEO_REQUEST,
            "ffmpeg_specs_from_config_only": True,
        },
        "adapter": {"path": adapter, "found": bool(adapter),
                    "note": None if adapter else "Skill 74 not found: dispatch uses the policy owner's static path (Skills 66 and 67) and records that fact"},
        "violations": violations,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--image-config")
    ap.add_argument("--video-config")
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--openclaw-dir", default=os.path.expanduser("~/.openclaw"))
    a = ap.parse_args(argv)
    print(json.dumps(build_plan(a.image_config, a.video_config, a.skill_dir, a.openclaw_dir), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
