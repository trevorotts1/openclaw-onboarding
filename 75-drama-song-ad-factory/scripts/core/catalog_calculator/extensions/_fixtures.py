"""Shared fixtures for the price-extension tests (not a test: run_all.sh
globs test_*.py).

``FakeSkill74`` answers ``price --model ID --units N`` exactly the way Skill
74's adapter answers it - estimate = highest listed tier x units for scaling
units, ``--units`` ignored for per-job units, preflight = estimate x 1.30
rounded up to 0.01 - so the tests exercise the real contract with zero network
and zero spend. The rate table is a mock of Skill 74's answers, copied from
unit V2-W0-U2's fixture plus the D33 lip-sync roster snapshot; nothing in the
module under test reads it.
"""
import copy
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_ID = "minimax-h3/image-to-video"
MUSIC_ID = "ai-music-api/generate"
IMAGE_ID = "google/imagen4-fast"
LIPSYNC_ID = "kling/ai-avatar-standard"
LIPSYNC_BACKUP_ID = "infinitalk/from-audio"


def load_catalog():
    with open(os.path.join(HERE, "fixtures", "catalog.json"), encoding="utf-8") as f:
        return json.load(f)


def load_responses():
    with open(os.path.join(HERE, "fixtures", "skill74-responses.json"),
              encoding="utf-8") as f:
        return json.load(f)


def catalog_with(**changes):
    """catalog_with(**{"id.field": value}) -> mutated deep copy."""
    cat = copy.deepcopy(load_catalog())
    for path, value in changes.items():
        model_id, field = path.rsplit(".", 1)
        for entry in cat["models"]:
            if entry["id"] == model_id:
                entry[field] = value
                break
        else:
            raise KeyError("no catalog entry %s" % model_id)
    return cat


def choice(length=60, shapes=("9:16",), model=None, music=MUSIC_ID,
           image=IMAGE_ID, lip_sync=None, voice_packs=None):
    out = {"length_seconds": length, "shapes": list(shapes), "model": model,
           "music_model": music, "image_model": image}
    if lip_sync is not None:
        out["lip_sync"] = dict(lip_sync) if isinstance(lip_sync, dict) else lip_sync
    if voice_packs is not None:
        out["voice_packs"] = dict(voice_packs) if isinstance(voice_packs, dict) \
            else voice_packs
    return out


def lipsync(model=LIPSYNC_ID, seconds=35, lines=7):
    return {"model": model, "seconds": seconds, "lines": lines}


def packs(count=3):
    return {"count": count}


def preflight_amount(credits):
    """Skill 74 adapter's preflight_amount: price x 1.30, up to 0.01 credit."""
    return None if credits is None else math.ceil(round(credits * 1.30 * 100, 6)) / 100.0


class FakeSkill74:
    """Injected price runner. modes, per model:

      price_unavailable   -> state fail, code price_unavailable (adapter path)
      price_unestimable   -> state ok, credits_estimate null (data path)
      bad_unit            -> state ok, unit outside the adapter's unit set
      runner_error        -> raises (runner blew up; live rate not read)

    An unknown model id answers price_unavailable, exactly like the adapter.
    """

    SCALING = ("per-second", "per-1k-chars", "per-image", "per-1m-tokens")

    def __init__(self, responses=None, modes=None):
        self.responses = copy.deepcopy(load_responses() if responses is None
                                       else responses)
        self.modes = dict(modes or {})
        self.calls = []  # [(model, units), ...]

    def __call__(self, model, units):
        self.calls.append((model, units))
        mode = self.modes.get(model)
        if mode == "runner_error":
            raise RuntimeError("skill74 transport failure")
        if mode == "price_unavailable" or model not in self.responses:
            return {"state": "fail", "model_id": model,
                    "error": {"code": "price_unavailable",
                              "msg": "no live catalog entry and no registry "
                                     "entry for %s" % model}}
        spec = self.responses[model]
        unit = "per-1m-tokens" if mode == "bad_unit" else spec["unit"]
        tier = spec["tier_credits"]
        source = spec.get("source", "registry")
        if unit in self.SCALING:
            est = round(tier * units, 4)
        else:  # per-job: units ignored, one job priced
            est = round(tier, 4)
        if mode == "price_unestimable":
            est = None
        return {"state": "ok", "model_id": model, "schema_source": source,
                "warnings": [],
                "data": {"pricing_desc": "%s credits (%s)" % (tier, unit),
                         "credits_min": tier, "credits_max": tier, "unit": unit,
                         "units": units, "credits_estimate": est,
                         "preflight_required": preflight_amount(est),
                         "preflight_multiplier": 1.30, "price_source": source}}


def walk_numbers(obj, key_suffixes=("credits", "usd", "price_credits",
                                    "price_usd", "preflight_required",
                                    "retake_allowance_usd",
                                    "spending_limit_usd")):
    """Every numeric price-ish value anywhere in an envelope (no-invented check)."""
    found = []

    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool) and any(
                        k == s or k.endswith(s) for s in key_suffixes):
                    found.append((k, v))
                else:
                    rec(v)
        elif isinstance(o, list):
            for v in o:
                rec(v)

    rec(obj)
    return found


def doubled(responses):
    """Same mock answers, every tier doubled - proves prices track live rates."""
    out = {}
    for key, value in responses.items():
        value = dict(value)
        value["tier_credits"] = round(value["tier_credits"] * 2, 4)
        out[key] = value
    return out
