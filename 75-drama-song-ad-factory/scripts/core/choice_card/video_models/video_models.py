#!/usr/bin/env python3
"""video_models: the four video models on the intake card, their prices for the
client's chosen length, and the exact KIE request each one sends.

One rates table (video_model_rates.json, with source URL and date). The price
uses the card's own formula (price-menu.md, catalog_calculator._build_card):
video + one keyframe per shot + one song, then +20% redo allowance, each step
rounded half-up to the cent. One shape (9:16). Character reference pictures are
not known yet at this question, so they are not in the estimate.

Stdlib only. No network.
"""
import json
import math
import os
import re
from decimal import Decimal, ROUND_HALF_UP

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "video_model_rates.json"), encoding="utf-8") as _f:
    RATES = json.load(_f)
MODELS = RATES["models"]
_CENT = Decimal("0.01")


def _usd(x):
    return Decimal(str(x)).quantize(_CENT, ROUND_HALF_UP)


def length_seconds(label):
    """'60 seconds' / '3 minutes' / '10-minute long version' -> seconds."""
    m = re.match(r"\s*(\d+)\s*[- ]?\s*(second|minute)", str(label).lower())
    if not m:
        raise ValueError("cannot read a length from %r" % (label,))
    return int(m.group(1)) * (60 if m.group(2) == "minute" else 1)


def length_phrase(seconds):
    """60 -> '60-second', 180 -> '3-minute'."""
    return "%d-minute" % (seconds // 60) if seconds >= 180 and seconds % 60 == 0 \
        else "%d-second" % seconds


def model_for(n):
    return next(m for m in MODELS if m["n"] == n)


def price(model, seconds):
    """-> dict: shots, video, keyframes, song, total, redo, limit (Decimal USD)."""
    shots = -(-int(seconds) // model["shot_s"])
    video = _usd(Decimal(str(model["rate_usd"])) * (shots if model["unit"] == "clip" else int(seconds)))
    keys, song = _usd(Decimal(str(RATES["keyframe_usd"])) * shots), _usd(RATES["song_usd"])
    total = video + keys + song
    redo = _usd(total * Decimal(str(RATES["redo_rate"])))
    return {"shots": shots, "video": video, "keyframes": keys, "song": song,
            "total": total, "redo": redo, "limit": total + redo}


def label(model, seconds):
    return "$%s" % price(model, seconds)["limit"]


def build_request(model, prompt, duration, aspect_ratio="9:16", first_frame_url=None):
    """The exact Skill 74 request {model, input} for one silent shot.
    Raises ValueError for a duration the provider would refuse."""
    if duration > model["shot_s"] or duration < 4 or duration != int(duration):
        raise ValueError("%s shots run 4 to %d whole seconds" % (model["name"], model["shot_s"]))
    d, kid = int(duration), model["kie_model"]
    if kid.startswith("minimax-h3/"):
        inp = {"prompt": prompt, "duration": d, "resolution": model["resolution"]}
    elif kid.startswith("bytedance/seedance"):
        inp = {"prompt": prompt, "duration": d, "resolution": model["resolution"],
               "aspect_ratio": aspect_ratio, "generate_audio": False}
    else:  # veo-3-1: top-level id stays veo-3-1, the tier rides inside input
        if d not in (4, 6, 8):
            raise ValueError("Google Veo 3.1 shots run 4, 6 or 8 seconds")
        inp = {"model": model["kie_tier"], "prompt": prompt, "duration": d,
               "resolution": model["resolution"], "aspect_ratio": aspect_ratio,
               "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO" if first_frame_url else "TEXT_2_VIDEO"}
        if first_frame_url:
            inp["image_urls"] = [first_frame_url]
        return {"model": kid, "input": inp}
    if first_frame_url:
        inp["first_frame_url"] = first_frame_url
    return {"model": kid, "input": inp}


def lock_choice(state_store, run_id, n):
    """Write the chosen model to the F14 video-model lock (what dispatch checks)."""
    import kie_dispatch.model_lock as ML
    return ML.lock_run_model(state_store, run_id, (lambda m: m.get("lock", m["kie_model"]))(model_for(n)))
