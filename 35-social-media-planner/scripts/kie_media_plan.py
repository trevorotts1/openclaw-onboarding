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
  * Only GPT Image generation 2.5 or newer is accepted. Older ones (gpt-image-1-5, legacy
    gpt-image-2; the latter is only for 3:1, 1:3, 9:21, which Skill 35 never produces) are
    ignored and reported.
  * EVERY string key and value in both config files, nested at any depth, is scanned for
    Sora, Nano Banana, Midjourney, Ideogram and flare; each hit is reported with its path.
  * Video is chosen by the Skill 67 selector. A Sora id in video-specs.json is ignored and
    reported; this script never names a video model other than the documented default request.
  * No prices, no prompt-length numbers here: Skill 74 `price` and `prompt-budget` own them.
  * plan 6.15 — the weekly drama-song ad (Skill 75 behind Skill 74, active mode
    only) is described in the plan's "drama_song" block. It is contract data:
    no dispatch, no spend, no second KIE client, and a KIE-off run reports
    drama-song-skipped.json with paid_calls_when_skipped 0.

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
GPT_GEN = re.compile(r"^gpt-image-(\d+)(?:-(\d+))?(?:-|$)")
BANNED = re.compile(r"sora|nano.?banana|midjourney|ideogram|flare", re.I)


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
    if "flare" in m:
        return False, "flare variants are not registered; they need a new owner ruling"
    g = GPT_GEN.match(m)
    if g:
        gen = (int(g.group(1)), int(g.group(2) or 0))
        if gen >= (2, 5):
            return True, "GPT Image 2.5 or newer"
        return False, "GPT Image generation below 2.5 (legacy gpt-image-2 is only for 3:1, 1:3 and 9:21, AGENTS.md N43); Skill 35 needs 2.5 or newer"
    return False, "not a Skill 35 image route (owner order 2026-10-05: social images are GPT Image 2.5 Sunburst)"


def scan_banned(obj, fname, path=""):
    """Yield a violation for every string key or value (any depth) naming a banned model."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = "%s.%s" % (path, k) if path else str(k)
            if BANNED.search(str(k)):
                yield {"file": fname, "path": p, "value": str(k), "action": "ignored", "reason": "banned model named in a key"}
            yield from scan_banned(v, fname, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from scan_banned(v, fname, "%s[%d]" % (path, i))
    elif isinstance(obj, str) and BANNED.search(obj):
        yield {"file": fname, "path": path, "value": obj, "action": "ignored",
               "reason": "banned model (Sora, Nano Banana, Midjourney, Ideogram or flare) is not a Skill 35 route"}


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
    violations += list(scan_banned(icfg, "image-model.json"))
    if requested and not accepted and not any(v["value"] == requested for v in violations):
        violations.append({"file": "image-model.json", "value": requested, "action": "ignored, default used", "reason": why})
    image_model = requested if (requested and accepted) else DEFAULT_T2I
    i2i = image_model.replace("text-to-image", "image-to-image") if "text-to-image" in image_model else DEFAULT_I2I

    vcfg, vnote = _load(video_cfg_path)
    vreq = _first_str(vcfg, VIDEO_MODEL_KEYS)
    violations += list(scan_banned(vcfg, "video-specs.json"))
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
        # plan 6.15 — the weekly drama-song ad rides the same cycle manifest.
        # Contract only: this script makes no call, spends nothing, and never
        # names a second KIE client.
        "drama_song": {
            "shape": "9:16",
            "one_per_week": True,
            "owner": "75-drama-song-ad-factory (Skill 75)",
            "kie_path": "skill-74",
            "kie_mode_required": "active",
            "skip_when": "Skill 74 not active -> drama-song-skipped.json, exit 0, plain-English client reason",
            "paid_calls_when_skipped": 0,
            "second_kie_client": False,
            "hard_cap_s": 59.0,
            "ninety_window_s": [88.0, 95.0],
            "stories": "15-second teaser only",
            "google_business_profile": "refused until a limit is verified",
            "sheet_schema_version": "1.3.0",
        },
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
