#!/usr/bin/env python3
"""video_models: the four video models on the intake card, their prices for the
client's chosen length, and the exact KIE request each one sends.

One rates table (video_model_rates.json, with source URL and date). The price
itself is computed in catalog_calculator.card_render.price_envelope: the
question, the final card and dispatch all use that one function, fed by
rated_price_fn below at the resolution each model really renders.

Stdlib only. No network.
"""
import json
import os
import re
from decimal import Decimal

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "video_model_rates.json"), encoding="utf-8") as _f:
    RATES = json.load(_f)
MODELS = RATES["models"]

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


def credits_per_unit(model):
    """Credits per second (or per clip for Veo) at the resolution this model renders.
    1 KIE credit = $0.005 (same constant the calculator uses)."""
    return float(Decimal(str(model["rate_usd"])) / Decimal("0.005"))


def entry_for_lock(locked):
    """The table entry a run's F14 lock names, or None."""
    return next((m for m in MODELS if m.get("lock", m["kie_model"]) == locked), None)


def chosen(state_store=None, run_id=None, n=None):
    """The client's model: explicit n, else the run-state lock, else the default (H3)."""
    if n is not None:
        return model_for(int(n))
    if state_store and run_id:
        import kie_dispatch.model_lock as ML
        m = entry_for_lock(ML.read_locked_model(state_store, run_id))
        if m:
            return m
    return next(m for m in MODELS if m["recommended"])


def row_label(model):
    """The card's "Video model" row."""
    return "%s %s%s" % (model["name"], model["resolution"], " (RECOMMENDED)" if model["recommended"] else "")


def catalog_for(model, catalog):
    """The calculator catalog with this model's entry at the shot length and
    resolution the factory really renders (the card prices what dispatch sends)."""
    out = []
    for e in catalog["models"]:
        if e["id"] == model["kie_model"]:
            e = dict(e, max_shot_seconds=model["shot_s"], resolution=model["resolution"])
        out.append(e)
    return {"models": out}


def rated_price_fn(model, base=None):
    """Skill 74 `price` shaped callable for the one card/question price.

    The chosen model is priced from this table at ITS resolution (Skill 74's
    `price` returns the highest listed tier, which the factory never renders).
    Everything else goes to `base` (Skill 74); with no base, keyframes and the
    song use the table too, so the question prices without an adapter.
    """
    def ok(est, unit, src):
        return {"state": "ok", "data": {"credits_estimate": est, "unit": unit,
                                        "price_source": src, "preflight_required": None}}

    def run(model_id, units):
        if model_id == model["kie_model"]:
            per = credits_per_unit(model)
            return ok(per * units if model["unit"] == "second" else per, "per-second" if model["unit"] == "second" else "per-job",
                      "%s %s (%s)" % (model["name"], model["resolution"], RATES["checked"]))
        if base is not None:
            return base(model_id, units)
        if model_id.startswith("google/imagen"):
            return ok(RATES["keyframe_usd"] / 0.005 * units, "per-image", "video_model_rates.json")
        if model_id.startswith("ai-music-api"):
            return ok(RATES["song_usd"] / 0.005, "per-job", "video_model_rates.json")
        return {"state": "fail", "error": {"code": "price_unavailable", "msg": "no rate for " + model_id}}
    return run


def apply_locked_choice(request, locked):
    """The request dispatch sends: the locked model's resolution (and Veo tier)
    stamped into input, so the card's price and the render are the same job."""
    m = entry_for_lock(locked)
    if not m or not isinstance(request.get("input"), dict):
        return request
    inp = dict(request["input"], resolution=m["resolution"])
    if "kie_tier" in m:
        inp["model"] = m["kie_tier"]
    return dict(request, input=inp)


def request_for_run(state_store, run_id, prompt, duration, aspect_ratio="9:16", first_frame_url=None):
    """The shot request for the model this run's client chose (read from run state)."""
    return build_request(chosen(state_store, run_id), prompt, duration, aspect_ratio, first_frame_url)


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
