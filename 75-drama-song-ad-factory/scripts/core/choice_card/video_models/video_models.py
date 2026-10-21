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

#: L3 (v2.9.73): the card names models, so its list must resolve against the
#: LIVE KIE catalog the run dispatches into.
REGISTRY_RELS = (
    ("74-kie-live-adapter", "references", "kie-model-registry.json"),
    ("onboarding", "74-kie-live-adapter", "references",
     "kie-model-registry.json"),
    ("skills", "74-kie-live-adapter", "references", "kie-model-registry.json"),
    (".claude", "skills", "74-kie-live-adapter", "references",
     "kie-model-registry.json"),
    ("installer-registration", "helpers", "74-kie-live-adapter", "references",
     "kie-model-registry.json"),
    ("999-setup", "installer-registration", "helpers", "74-kie-live-adapter",
     "references", "kie-model-registry.json"),
)
REGISTRY_CACHE = {}


class ModelResolutionError(ValueError):
    """A card model list that cannot be resolved from the live catalog.

    Carries the reason code (VIDEO_MODEL_UNRESOLVABLE default) and, for an
    individual row, the model the registry does not carry -- the card is
    refused by name, never printed with an unresolvable model."""

    def __init__(self, reason, message, models=()):
        super().__init__("%s: %s" % (reason, message))
        self.reason = reason
        self.models = list(models)


def resolve_registry(explicit=None):
    """Path to the live registry, or None (fail-closed: no name is invented).
    explicit is a caller-supplied path override (tests, twin installs)."""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    env = os.environ.get("KIE_MODEL_REGISTRY_JSON")
    if env:
        return env if os.path.isfile(env) else None
    for parent in _registry_roots():
        for rel in REGISTRY_RELS:
            cand = os.path.join(parent, *rel)
            if os.path.isfile(cand):
                return cand
    return None


def _registry_roots():
    """Every walk-up root: this module's dir, its parents, and cwd's parents
    (a script may run from a twin tree)."""
    roots, seen = [], set()
    here = os.path.abspath(_HERE)
    cwd = os.path.abspath(os.getcwd())
    for start in (here, cwd):
        cur = start
        while True:
            if cur not in seen:
                seen.add(cur)
                roots.append(cur)
            nxt = os.path.dirname(cur)
            if nxt == cur:
                break
            cur = nxt
    return sorted(roots, key=len)          # deepest first


def registry_ids(explicit=None):
    """The model ids the live registry carries, or None when unreadable."""
    path = resolve_registry(explicit)
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    return {m.get("id") for m in models if isinstance(m, dict) and m.get("id")}


def resolve_choices(explicit=None):
    """The rate-table rows proven in the live catalog: (rows, None), or
    (None, reason) when they cannot ALL be resolved. The registry must carry
    every row: the card's options are numbered and the client's answer is an
    option number, so a filtered list would silently renumber the card and
    lock a model different from the one the client pointed at -- the live
    defect class. An unreadable registry is also unresolvable. Fail-closed;
    the reason names what could not be resolved."""
    ids = registry_ids(explicit)
    if ids is None:
        registry = resolve_registry(explicit)
        return None, {"reason_code": "VIDEO_MODEL_UNRESOLVABLE",
                      "detail": ("the live KIE model registry cannot be read "
                                 "(%s) -- the card cannot prove its video "
                                 "models exist, so it refuses instead of "
                                 "printing one the catalog does not carry"
                                 % (registry or "no kie-model-registry.json "
                                    "found via KIE_MODEL_REGISTRY_JSON or "
                                    "walk-up"))}
    missing = [m for m in MODELS if m["kie_model"] not in ids]
    if missing:
        return None, {"reason_code": "MODEL_NOT_IN_REGISTRY",
                      "detail": ("the card offers model(s) the live KIE "
                                 "registry does not carry: %s (registry %s, "
                                 "%d ids)"
                                 % ("; ".join("%s (%s)" % (m["name"],
                                                           m["kie_model"])
                                              for m in missing),
                                    resolve_registry(explicit), len(ids)))}
    return list(MODELS), None


def require_choices(explicit=None):
    """MODELS as filtered through the live registry, or ModelResolutionError
    naming what could not be resolved. The card refuses, never guesses."""
    rows, reason = resolve_choices(explicit)
    if reason:
        raise ModelResolutionError(reason["reason_code"], reason["detail"])
    return rows


def assert_resolvable(model, explicit=None):
    """Refuse one model row the live registry does not carry (by exact id,
    or the family pattern when the row carries a lock). ModelResolutionError
    MODEL_NOT_IN_REGISTRY names the model and the registry."""
    ids = registry_ids(explicit)
    registry = resolve_registry(explicit)
    if ids is None:
        raise ModelResolutionError(
            "VIDEO_MODEL_UNRESOLVABLE",
            "the live KIE model registry cannot be read (%s) -- %r cannot be "
            "proven to exist" % (registry or "no registries found", model["name"]))
    if model["kie_model"] not in ids:
        raise ModelResolutionError(
            "MODEL_NOT_IN_REGISTRY",
            "%r's model %r is not in the live KIE registry (%s): the card "
            "refuses to offer a model the catalog does not carry"
            % (model["name"], model["kie_model"], registry))

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
    Raises ValueError for a duration the provider would refuse.

    The request shape is the table entry's own ``shape`` field -- the row
    names which input fields its provider schema takes, so no model name
    is branched on here (L3):
      plain          prompt/duration/resolution (+ first_frame_url)
      silent_aspect  + aspect_ratio and generate_audio=False (16.2 silent)
      tiered_input   kie_tier rides inside input, with generation_type and
                     image_urls; clip lengths come from ``clip_s``.
    """
    if duration > model["shot_s"] or duration < 4 or duration != int(duration):
        raise ValueError("%s shots run 4 to %d whole seconds" % (model["name"], model["shot_s"]))
    d, kid = int(duration), model["kie_model"]
    allowed = model.get("clip_s")
    if allowed and d not in allowed:
        raise ValueError("%s shots run %s whole seconds"
                         % (model["name"],
                            ", ".join(str(x) for x in allowed)))
    shape = model.get("shape", "plain")
    if shape == "tiered_input":
        inp = {"model": model["kie_tier"], "prompt": prompt, "duration": d,
               "resolution": model["resolution"], "aspect_ratio": aspect_ratio,
               "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO"
               if first_frame_url else "TEXT_2_VIDEO"}
        if first_frame_url:
            inp["image_urls"] = [first_frame_url]
        return {"model": kid, "input": inp}
    inp = {"prompt": prompt, "duration": d, "resolution": model["resolution"]}
    if shape == "silent_aspect":
        inp.update({"aspect_ratio": aspect_ratio, "generate_audio": False})
    if first_frame_url:
        inp["first_frame_url"] = first_frame_url
    return {"model": kid, "input": inp}


def lock_choice(state_store, run_id, n):
    """Write the chosen model to the F14 video-model lock (what dispatch checks).

    L3: refuses a model the live registry does not carry -- a lock for a
    model the catalog does not have can never dispatch, so it never writes."""
    m = model_for(n)
    assert_resolvable(m)
    import kie_dispatch.model_lock as ML
    return ML.lock_run_model(state_store, run_id, (lambda m: m.get("lock", m["kie_model"]))(m))
