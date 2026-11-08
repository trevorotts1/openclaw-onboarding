#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
select_image_model.py - Skill 66 kie-image model selector.

Maps a natural-language image request to a KIE Market canonical_model_id, or
returns valid=false with an alternative when the request cannot be served.

STDLIB PYTHON3 ONLY. No secrets read. The GPT Image default follows the newest GPT Image generation
in KIE's live catalog (owner order 2026-10-05): resolved through Skill 74 `latest-family` when that
adapter is present and reachable, else the models.json default below. Explicit model/alias pins and
department pins are unchanged. GPT Image 2.6 Sunburst serves all 16 enum aspect ratios natively, so
a ratio inside that enum is dispatched LITERALLY -- never rerouted to the legacy route and never
substituted -- and a ratio outside the enum is refused.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter_bridge  # noqa: E402  (Skill 74 bridge; optional at runtime)

VERSION = "2.2.0"

MODELS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models.json")

# ---------------------------------------------------------------------------
# Minimal routing table. Full per-model limits live in models.json (the
# registry). SELECTOR PADDING IS FORBIDDEN (spec 7.2 last line): only add a
# family here when it is in models.json and research-backed.
# ---------------------------------------------------------------------------

REGISTRY = {
    # GPT Image 2.5 Sunburst family -- operator default. The family carries the
    # GPT Image 2.6 aspect-ratio enum (16 values, every one native), so an
    # aspect ratio is never a routing input. GPT Image 2 (legacy, below) is
    # RETAINED, not retired, and stays reachable by explicit pin; it is no
    # longer the required route for any ratio.
    "gpt-image-2-5-sunburst": {
        "name": "GPT Image 2.5",
        "routes": {
            "t2i": {"canonical_model_id": "gpt-image-2-5-sunburst-text-to-image", "task": "text-to-image"},
            "i2i": {"canonical_model_id": "gpt-image-2-5-sunburst-image-to-image", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "gpt-image-2": {
        "name": "GPT Image 2 (Legacy)",
        "routes": {
            "t2i": {"canonical_model_id": "gpt-image-2-text-to-image", "task": "text-to-image"},
            "i2i": {"canonical_model_id": "gpt-image-2-image-to-image", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "qwen-image-3.0": {
        "name": "Qwen Image 3.0",
        "routes": {
            "t2i": {"canonical_model_id": "qwen3/text-to-image", "task": "text-to-image"},
            "i2i": {"canonical_model_id": "qwen3/image-to-image", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "qwen-image-3.0-pro": {
        "name": "Qwen Image 3.0 Pro",
        "routes": {
            "t2i": {"canonical_model_id": "qwen3-pro/text-to-image", "task": "text-to-image"},
            "i2i": {"canonical_model_id": "qwen3-pro/image-to-image", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "seedream-5.0-pro": {
        "name": "Seedream 5.0 Pro",
        "routes": {
            "t2i": {"canonical_model_id": "seedream/5-pro-text-to-image", "task": "text-to-image"},
            "i2i": {"canonical_model_id": "seedream/5-pro-image-to-image", "task": "image-to-image"},
            "layer": {"canonical_model_id": "seedream/5-pro-layer-decomposition", "task": "layer-decomposition"},
        },
        "default": "t2i",
    },
    "seedream-5.0-lite": {
        "name": "Seedream 5.0 Lite",
        "routes": {
            "t2i": {"canonical_model_id": "seedream/5-lite-text-to-image", "task": "text-to-image"},
            "i2i": {"canonical_model_id": "seedream/5-lite-image-to-image", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "seedream-4.5": {
        "name": "Seedream 4.5",
        "routes": {
            "t2i": {"canonical_model_id": "seedream/4.5-text-to-image", "task": "text-to-image"},
            "edit": {"canonical_model_id": "seedream/4.5-edit", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "nano-banana-2": {
        "name": "Nano Banana 2",
        "routes": {
            "all": {"canonical_model_id": "nano-banana-2", "task": "image-to-image"},
        },
        "default": "all",
    },
    "nano-banana-2-lite": {
        "name": "Nano Banana 2 Lite",
        "routes": {
            "all": {"canonical_model_id": "nano-banana-2-lite", "task": "image-to-image"},
        },
        "default": "all",
    },
    "nano-banana-pro": {
        "name": "Nano Banana Pro",
        "routes": {
            "all": {"canonical_model_id": "nano-banana-pro", "task": "image-to-image"},
        },
        "default": "all",
    },
    "nano-banana-legacy": {
        "name": "Nano Banana (Legacy)",
        "routes": {
            "all": {"canonical_model_id": "google/nano-banana", "task": "image-to-image"},
        },
        "default": "all",
    },
    "wan-2.7-image": {
        "name": "Wan 2.7 Image",
        "routes": {
            "std": {"canonical_model_id": "wan/2-7-image", "task": "image-to-image"},
            "pro": {"canonical_model_id": "wan/2-7-image-pro", "task": "image-to-image"},
        },
        "default": "std",
    },
    "flux-2": {
        "name": "FLUX.2",
        "routes": {
            "pro-t2i": {"canonical_model_id": "flux-2/pro-text-to-image", "task": "text-to-image"},
            "pro-i2i": {"canonical_model_id": "flux-2/pro-image-to-image", "task": "image-to-image"},
            "flex-t2i": {"canonical_model_id": "flux-2/flex-text-to-image", "task": "text-to-image"},
            "flex-i2i": {"canonical_model_id": "flux-2/flex-image-to-image", "task": "image-to-image"},
        },
        "default": "pro-t2i",
    },
    "z-image": {
        "name": "Z-Image",
        "routes": {
            "all": {"canonical_model_id": "z-image", "task": "text-to-image"},
        },
        "default": "all",
    },
    "ideogram-v3": {
        "name": "Ideogram V3",
        "routes": {
            "t2i": {"canonical_model_id": "ideogram/v3-text-to-image", "task": "text-to-image"},
            "edit": {"canonical_model_id": "ideogram/v3-edit", "task": "image-to-image"},
            "remix": {"canonical_model_id": "ideogram/v3-remix", "task": "image-to-image"},
        },
        "default": "t2i",
    },
    "imagen-4": {
        "name": "Imagen 4",
        "routes": {
            "fast": {"canonical_model_id": "google/imagen4-fast", "task": "text-to-image"},
            "std": {"canonical_model_id": "google/imagen4", "task": "text-to-image"},
            "ultra": {"canonical_model_id": "google/imagen4-ultra", "task": "text-to-image"},
        },
        "default": "std",
    },
}

# ---------------------------------------------------------------------------
# Alias map (spec 13). Z-Image guard: "z image by quinn" stays z-image -
# Z-Image is its own family and NEVER merges into Qwen.
# ---------------------------------------------------------------------------

ALIASES = {
    # phonetics / typos
    "cling": "ideogram-v3",
    "kling": "ideogram-v3",
    "idiogram": "ideogram-v3",
    "imagine 4": "imagen-4",
    # quinn -> qwen
    "quinn": "qwen-image-3.0",
    "quinn image": "qwen-image-3.0",
    "quinn image 3.0": "qwen-image-3.0",
    "quinn image 3": "qwen-image-3.0",
    # c dream / seed dream -> seedream
    "c dream": "seedream-5.0-pro",
    "c-dream": "seedream-5.0-pro",
    "seed dream": "seedream-5.0-pro",
    # gpt family -- operator ruling 2026-09-09 (Ruling 6): short human aliases
    # now resolve to the GPT Image 2.5 Sunburst default. The retained legacy
    # GPT Image 2 route is still reachable via an explicit canonical model id
    # (gpt-image-2-text-to-image / gpt-image-2-image-to-image, matched via
    # MODEL_TO_FAMILY below) or the "legacy"-qualified phrases added here.
    "gpt-img2": "gpt-image-2",
    "gpt img2": "gpt-image-2",
    "gpt image 2": "gpt-image-2",
    "gpt-image 2": "gpt-image-2",
    "gpt image 2.0": "gpt-image-2",
    "gpt-image-2.0": "gpt-image-2",
    "gpt-image-2": "gpt-image-2",
    # gpt 2.5 / sunburst phrasing (new, added alongside the retargeted aliases
    # above -- no existing alias key was deleted)
    "gpt image 2.5": "gpt-image-2-5-sunburst",
    "gpt-image 2.5": "gpt-image-2-5-sunburst",
    "gpt-image-2.5": "gpt-image-2-5-sunburst",
    "gpt image 2.5 sunburst": "gpt-image-2-5-sunburst",
    "gpt-img2.5": "gpt-image-2-5-sunburst",
    "sunburst": "gpt-image-2-5-sunburst",
    # version-less generic names: the fleet default, which follows the newest generation (owner order 2026-10-05)
    "gpt image": "gpt-image-2-5-sunburst",
    "gpt-image": "gpt-image-2-5-sunburst",
    "openai image": "gpt-image-2-5-sunburst",
    # explicit legacy pin phrasing (retained route, ruling 2026-09-09)
    "gpt image 2 legacy": "gpt-image-2",
    "legacy gpt image 2": "gpt-image-2",
    "gpt-image-2 legacy": "gpt-image-2",
    # seedream variants (longest match wins)
    "seedream 5 lite": "seedream-5.0-lite",
    "seedream 5.0 lite": "seedream-5.0-lite",
    "seedream lite": "seedream-5.0-lite",
    "seedream 5 pro": "seedream-5.0-pro",
    "seedream 5.0 pro": "seedream-5.0-pro",
    "seedream pro": "seedream-5.0-pro",
    "seedream 5": "seedream-5.0-pro",
    "seedream 5.0": "seedream-5.0-pro",
    "seedream": "seedream-5.0-pro",
    "seedream 4.5": "seedream-4.5",
    "seedream 4": "seedream-4.5",
    # qwen variants
    "qwen image 3.0 pro": "qwen-image-3.0-pro",
    "qwen-image 3.0-pro": "qwen-image-3.0-pro",
    "qwen3-pro": "qwen-image-3.0-pro",
    "qwen 3 pro": "qwen-image-3.0-pro",
    "qwen image 3.0": "qwen-image-3.0",
    "qwen image 3": "qwen-image-3.0",
    "qwen image": "qwen-image-3.0",
    "qwen3": "qwen-image-3.0",
    "qwen 3": "qwen-image-3.0",
    # nano banana
    "nano banana 2 lite": "nano-banana-2-lite",
    "nano-banana-2-lite": "nano-banana-2-lite",
    "nano banana lite": "nano-banana-2-lite",
    "nano banana light": "nano-banana-2-lite",
    "nano-banana-light": "nano-banana-2-lite",
    "nano banana 2": "nano-banana-2",
    "nano banana": "nano-banana-2",
    "nano-banana": "nano-banana-2",
    "nano banana pro": "nano-banana-pro",
    "nano-banana-pro": "nano-banana-pro",
    "legacy nano banana": "nano-banana-legacy",
    "nano banana 1": "nano-banana-legacy",
    "google/nano-banana": "nano-banana-legacy",
    # wan
    "wan 2.7 image pro": "wan-2.7-image",
    "wan 2.7 pro": "wan-2.7-image",
    "wan pro": "wan-2.7-image",
    "wan2.7-pro": "wan-2.7-image",
    "wan2.7": "wan-2.7-image",
    "wan 2.7 image": "wan-2.7-image",
    "wan 2.7": "wan-2.7-image",
    "wan": "wan-2.7-image",
    # flux
    "flux.2 pro": "flux-2",
    "flux 2 pro": "flux-2",
    "flux pro": "flux-2",
    "flux.2 flex": "flux-2",
    "flux 2 flex": "flux-2",
    "flux flex": "flux-2",
    "flux.2": "flux-2",
    "flux 2": "flux-2",
    "flux": "flux-2",
    # z-image: own family, never qwen
    "z image": "z-image",
    "z-image": "z-image",
    "z image turbo": "z-image",
    "z-image turbo": "z-image",
    # ideogram
    "ideogram v3": "ideogram-v3",
    "ideogram 3": "ideogram-v3",
    "ideogram": "ideogram-v3",
    # imagen
    "imagen 4 fast": "imagen-4",
    "imagen4-fast": "imagen-4",
    "imagen 4 ultra": "imagen-4",
    "imagen4-ultra": "imagen-4",
    "imagen 4": "imagen-4",
    "imagen4": "imagen-4",
    "imagen": "imagen-4",
}

MODEL_TO_FAMILY = {}
for fam, spec in REGISTRY.items():
    for rinfo in spec["routes"].values():
        MODEL_TO_FAMILY[rinfo["canonical_model_id"]] = fam

# ---------------------------------------------------------------------------
# Registry-driven capability data (loaded lazily from models.json on first
# use). This is capability DATA, not selector padding: the padding ban forbids
# adding un-researched FAMILIES to REGISTRY above, never reading models.json.
# ---------------------------------------------------------------------------

_REG_BY_ID = None


def registry_by_id():
    global _REG_BY_ID
    if _REG_BY_ID is None:
        with open(MODELS_JSON_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        _REG_BY_ID = {m["canonical_model_id"]: m for m in data["models"]}
    return _REG_BY_ID

TASKS = {
    "layer decomposition": "layer-decomposition",
    "layer-decomposition": "layer-decomposition",
    "layer separation": "layer-decomposition",
    "layers": "layer-decomposition",
    "image-to-image": "image-to-image",
    "image to image": "image-to-image",
    "i2i": "image-to-image",
    "edit": "image-to-image",
    "inpaint": "image-to-image",
    "remix": "image-to-image",
    "reference": "image-to-image",
    "references": "image-to-image",
    "text-to-image": "text-to-image",
    "text to image": "text-to-image",
    "t2i": "text-to-image",
    "generate": "text-to-image",
    "generation": "text-to-image",
    "create": "text-to-image",
}

RESOLUTION_HINTS = {"4k": "4k", "2k": "2k", "1k": "1k"}


def normalize(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def detect_task(text):
    norm = normalize(text)
    for key, task in TASKS.items():
        if re.search(r"(^|[\s,.!?/])" + re.escape(key) + r"($|[\s,.!?/])", norm):
            return task
    return "text-to-image"  # default: generation


def detect_resolution(text):
    norm = normalize(text)
    for k, v in RESOLUTION_HINTS.items():
        if re.search(r"\b" + re.escape(k) + r"\b", norm):
            return v
    return None


def match_alias(norm):
    """Longest alias phrase present in norm. Returns (alias, family) or (None, None)."""
    best_alias, best_fam = None, None
    for alias, fam in ALIASES.items():
        if re.search(r"(^|[\s,.!?/])" + re.escape(alias) + r"($|[\s,.!?/])", norm):
            if best_alias is None or len(alias) > len(best_alias):
                best_alias, best_fam = alias, fam
    return best_alias, best_fam


def match_canonical(norm):
    """Explicit canonical model id present in norm. Returns model_id or None."""
    for model_id in sorted(MODEL_TO_FAMILY, key=len, reverse=True):
        pat = r"(^|[\s,./])" + re.escape(model_id) + r"($|[\s,./])"
        if re.search(pat, norm):
            return model_id
    return None


def family_from_text(text):
    """(family, explicit_canonical_id_or_None, matched_fragment)"""
    norm = normalize(text)
    model_id = match_canonical(norm)
    if model_id:
        return MODEL_TO_FAMILY[model_id], model_id, model_id
    alias, fam = match_alias(norm)
    if fam:
        return fam, None, alias
    return None, None, None


# GPT Image 2.6 Sunburst aspect-ratio handling. The vendor OpenAPI enum is
# exactly: auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4, 4:5, 16:9, 9:16, 2:1, 1:2,
# 21:9, 9:21, 3:1, 1:3. Every member is native, so the requested ratio is
# passed through untouched. The 2.5-era workarounds are gone: no ratio reroutes
# to the legacy GPT Image 2 route, and no ratio is substituted for another
# (a 5:4 request must never be dispatched as 4:3). The enum itself is NOT
# duplicated here -- it is read from models.json via capability_conflict, so a
# ratio outside it (27:16, 16:27, 9:8, 8:9, ...) is refused as invalid rather
# than coerced.

# Version-less generic names ("gpt image", "gpt-image", "openai image") mean "the fleet GPT Image default" and
# follow the newest generation (owner order 2026-10-05). Names that carry a version ("gpt image 2", "gpt-img2",
# "gpt image 2.5", "sunburst") or a canonical model id are pins and never move: "gpt image 2" is the
# legacy GPT Image 2 family (used with its own N43 ratio rules).
GENERIC_GPT_ALIASES = {"gpt image", "gpt-image", "openai image"}
_DEFAULT_MEMO = {}


def gpt_default_routes():
    """{'t2i','i2i','source','changed','fallback'}: newest GPT Image generation via Skill 74, else models.json."""
    if "v" in _DEFAULT_MEMO:
        return _DEFAULT_MEMO["v"]
    st = REGISTRY["gpt-image-2-5-sunburst"]["routes"]
    out = {"t2i": st["t2i"]["canonical_model_id"], "i2i": st["i2i"]["canonical_model_id"],
           "source": "models.json", "changed": False, "fallback": None}
    got = adapter_bridge.latest_family("gpt-image", current=out["t2i"])
    routes = (got or {}).get("routes") or {}
    t2i, i2i = routes.get("Text to Image"), routes.get("Image to Image")
    if t2i and i2i:
        out.update(t2i=t2i, i2i=i2i, source="skill-74:" + str(got.get("source")), changed=bool(got.get("changed")))
        if (t2i, i2i) != (st["t2i"]["canonical_model_id"], st["i2i"]["canonical_model_id"]):
            # owner order: if the newer model fails dispatch or validation, retry the previous default for that job
            out["fallback"] = {"t2i": st["t2i"]["canonical_model_id"], "i2i": st["i2i"]["canonical_model_id"]}
    _DEFAULT_MEMO["v"] = out
    return out


def choose_answer(family, request, explicit_model_id, dynamic=False):
    """Return dict with selected_model_id / valid / reason / alternative."""
    norm = normalize(request)
    fam_spec = REGISTRY[family]
    routes = fam_spec["routes"]
    task = detect_task(request)
    res = detect_resolution(request)

    # --- Wan special cases -------------------------------------------------
    if family == "wan-2.7-image" and "pro" in routes:
        wants_pro = bool(re.search(r"\bpro\b", norm))
        if explicit_model_id:
            if explicit_model_id == "wan/2-7-image" and res == "4k" and not wants_pro:
                return {
                    "valid": False,
                    "selected_model_id": None,
                    "reason": "Wan 2.7 Image (standard) publishes 1K|2K only; 4K is Pro-only. "
                              "Explicit standard pin cannot serve 4K.",
                    "alternative": "wan/2-7-image-pro",
                }
        if res == "4k" or wants_pro:
            return {
                "valid": True,
                "selected_model_id": "wan/2-7-image-pro",
                "reason": "4K (or explicit Pro) requested; Pro route chosen",
                "alternative": None,
            }
        return {
            "valid": True,
            "selected_model_id": "wan/2-7-image",
            "reason": "Wan 2.7 Image standard route",
            "alternative": None,
        }

    # --- layer decomposition (seedream 5 pro only) --------------------------
    if task == "layer-decomposition" and "layer" in routes:
        return _ok(routes["layer"]["canonical_model_id"], "layer decomposition requested")

    # --- qwen pro/base -------------------------------------------------------
    if family.startswith("qwen-image-3.0"):
        pro_fam = family == "qwen-image-3.0-pro"
        if not pro_fam and re.search(r"\bpro\b", norm):
            return _ok(REGISTRY["qwen-image-3.0-pro"]["routes"]["t2i"]["canonical_model_id"],
                       "Qwen Pro requested; Pro route chosen")
        key = "i2i" if task == "image-to-image" else "t2i"
        if key not in routes:
            return _ok(routes["t2i"]["canonical_model_id"], "route unavailable; t2i fallback")
        return _ok(routes[key]["canonical_model_id"], "Qwen %s" % key)

    # --- seedream ------------------------------------------------------------
    if family.startswith("seedream"):
        if family == "seedream-4.5":
            if task == "image-to-image":
                return _ok(routes["edit"]["canonical_model_id"], "Seedream 4.5 edit (reference/edit route)")
            return _ok(routes["t2i"]["canonical_model_id"], "Seedream 4.5 text-to-image")
        if re.search(r"\blite\b", norm) and family != "seedream-5.0-lite":
            return _ok(REGISTRY["seedream-5.0-lite"]["routes"]["t2i"]["canonical_model_id"],
                       "Seedream Lite requested")
        if re.search(r"\bpro\b", norm) and family == "seedream-5.0-lite":
            return _ok(REGISTRY["seedream-5.0-pro"]["routes"]["t2i"]["canonical_model_id"],
                       "Seedream Pro requested")
        if task == "image-to-image" and "i2i" in routes:
            return _ok(routes["i2i"]["canonical_model_id"], "Seedream image-to-image")
        return _ok(routes["t2i"]["canonical_model_id"], "Seedream text-to-image")

    # --- GPT Image default (newest generation, currently 2.6 Sunburst) ------
    if family == "gpt-image-2-5-sunburst":
        key = "i2i" if task == "image-to-image" else "t2i"
        dflt = gpt_default_routes() if dynamic else None
        if dflt:  # auto-latest default (owner order 2026-10-05)
            routes = {k: {"canonical_model_id": dflt[k], "task": routes[k]["task"]} for k in ("t2i", "i2i")}
        task_label = "image-to-image" if key == "i2i" else "text-to-image"
        # Every ratio in the 2.6 enum is native here, so the ratio travels
        # untouched; capability_conflict in select() rejects a ratio outside it.
        return _ok(routes[key]["canonical_model_id"], "GPT Image default %s (%s)" % (
            task_label, ("auto-latest via %s" % dflt["source"]) if dflt else "2.6 sunburst pinned"))

    # --- gpt-image-2 (legacy, retained by operator ruling 2026-09-09) -------
    if family == "gpt-image-2":
        if task == "image-to-image":
            return _ok(routes["i2i"]["canonical_model_id"], "GPT Image 2 (legacy) image-to-image")
        return _ok(routes["t2i"]["canonical_model_id"], "GPT Image 2 (legacy) text-to-image")

    # --- ideogram -------------------------------------------------------------
    if family == "ideogram-v3":
        if re.search(r"\bremix\b", norm):
            return _ok(routes["remix"]["canonical_model_id"], "Ideogram V3 remix")
        if task == "image-to-image" and "edit" in routes:
            return _ok(routes["edit"]["canonical_model_id"], "Ideogram V3 edit")
        return _ok(routes["t2i"]["canonical_model_id"], "Ideogram V3 text-to-image")

    # --- imagen ---------------------------------------------------------------
    if family == "imagen-4":
        if re.search(r"\bultra\b", norm):
            return _ok(routes["ultra"]["canonical_model_id"], "Imagen 4 Ultra")
        if re.search(r"\bfast\b", norm):
            return _ok(routes["fast"]["canonical_model_id"], "Imagen 4 Fast")
        return _ok(routes["std"]["canonical_model_id"], "Imagen 4 standard")

    # --- flux ------------------------------------------------------------------
    if family == "flux-2":
        pro = bool(re.search(r"\bpro\b", norm))
        flex = bool(re.search(r"\bflex\b", norm))
        if task == "image-to-image":
            if flex:
                return _ok(routes["flex-i2i"]["canonical_model_id"], "FLUX.2 Flex image-to-image")
            if pro:
                return _ok(routes["pro-i2i"]["canonical_model_id"], "FLUX.2 Pro image-to-image")
            return _ok(routes["pro-i2i"]["canonical_model_id"], "FLUX.2 Pro image-to-image (default i2i)")
        if flex:
            return _ok(routes["flex-t2i"]["canonical_model_id"], "FLUX.2 Flex text-to-image")
        return _ok(routes["pro-t2i"]["canonical_model_id"], "FLUX.2 Pro text-to-image (default)")

    # --- single-route families --------------------------------------------------
    if "all" in routes:
        return _ok(routes["all"]["canonical_model_id"], fam_spec["name"] + " route")

    # --- generic fallback ---------------------------------------------------------
    default = fam_spec.get("default")
    if default and default in routes:
        return _ok(routes[default]["canonical_model_id"], fam_spec["name"] + " default route")
    first = list(routes.values())[0]
    return _ok(first["canonical_model_id"], fam_spec["name"] + " first route")


def _ok(model_id, reason, notes=None):
    return {
        "valid": True,
        "selected_model_id": model_id,
        "reason": reason,
        "alternative": None,
        "notes": list(notes) if notes else [],
    }


def capability_entry(model_id, family):
    """The models.json row that governs `model_id`'s limits, or None.

    The auto-latest default can name a generation newer than the models.json
    snapshot (e.g. the live id gpt-image-2-6/sunburst-text-to-image while the
    snapshot still calls that generation gpt-image-2-5-sunburst-*). That
    newer id has no row, and a missing row must never mean "no limits", so
    this family's own registry row supplies the capability data. An exact row
    always wins.
    """
    reg = registry_by_id()
    if model_id in reg:
        return reg[model_id]
    for rinfo in REGISTRY.get(family or "", {}).get("routes", {}).values():
        if rinfo["canonical_model_id"] in reg:
            return reg[rinfo["canonical_model_id"]]
    return None


def capability_conflict(entry, request, res):
    """Registry-driven capability check: when the request names a resolution or
    aspect ratio and the selected route's registry entry publishes a non-null
    list that does not contain the requested value, return the rejection shape
    (suggesting a same-family route that does support it when one exists).

    The requested ratio is checked literally. Nothing resolves it to a
    different ratio before the check, because no ratio substitution exists.
    """
    if entry is None:
        return None
    norm = normalize(request)

    req_res = res or detect_resolution(request)
    allowed_res = entry.get("resolutions")
    if req_res and allowed_res:
        wanted = {"4k": "4K", "2k": "2K", "1k": "1K"}.get(req_res, req_res)
        if wanted not in [str(x) for x in allowed_res]:
            alt = _same_family_alternative(entry, "resolutions", wanted)
            return {
                "valid": False,
                "selected_model_id": None,
                "reason": "%s publishes %s resolution(s) only; %s requested" % (
                    entry["canonical_model_id"], "|".join(str(x) for x in allowed_res), wanted),
                "alternative": alt,
            }

    ratio = detect_aspect_ratio(request)
    allowed_ar = entry.get("aspect_ratios")
    if ratio and allowed_ar and ratio not in [str(x) for x in allowed_ar]:
        alt = _same_family_alternative(entry, "aspect_ratios", ratio)
        return {
            "valid": False,
            "selected_model_id": None,
            "reason": "%s publishes aspect ratios %s only; %s requested" % (
                entry["canonical_model_id"], ", ".join(str(x) for x in allowed_ar), ratio),
            "alternative": alt,
        }

    # Per-ratio resolution exclusion, registry-driven and per-generation: GPT
    # Image 2 (legacy) carries its own old 5-item 2K/4K exclusion list (5:4,
    # 4:5, 3:1, 1:3, 9:21). GPT Image 2.6 Sunburst carries none -- the vendor
    # document states no per-resolution aspect-ratio exclusions, and the
    # 2.5-only "1K only" rule for 27:16/16:27/9:8/8:9 is retired because those
    # ratios are not enum members at all (caught by the check above). Each
    # entry's own list governs; never merged.
    excluded = entry.get("ratio_resolution_exclusions")
    if ratio and excluded and req_res and ratio in [str(x) for x in excluded]:
        wanted_res = {"4k": "4K", "2k": "2K", "1k": "1K"}.get(req_res, req_res)
        if wanted_res in ("2K", "4K"):
            return {
                "valid": False,
                "selected_model_id": None,
                "reason": "%s: aspect ratio %s is 1K-only on this route; %s requested" % (
                    entry["canonical_model_id"], ratio, wanted_res),
                "alternative": None,
            }
    return None


def _same_family_alternative(entry, key, wanted):
    """Another route of the same family whose registry entry supports `wanted`, or None."""
    fam = entry.get("family")
    if not fam:
        return None
    for other in registry_by_id().values():
        if other.get("family") == fam and other["canonical_model_id"] != entry["canonical_model_id"]:
            if other.get(key) and wanted in [str(x) for x in other[key]]:
                return other["canonical_model_id"]
    return None


RATIO_TOKENS = [
    "21:9", "9:21", "1:8", "8:1", "16:9", "9:16", "4:5", "5:4", "3:4", "4:3",
    "2:3", "3:2", "1:2", "2:1", "1:3", "3:1", "1:4", "4:1", "1:1",
    # Outside the GPT Image 2.6 enum. Listed so they are DETECTED and refused,
    # never silently dropped from the request and never coerced to a member.
    "27:16", "16:27", "9:8", "8:9",
]

NAMED_RATIOS = ["square_hd", "square", "portrait_4_3", "portrait_16_9",
                "landscape_4_3", "landscape_16_9"]


def detect_aspect_ratio(text):
    """Named aspect token (square, landscape_16_9, ...) or N:N ratio in the text."""
    norm = normalize(text)
    for named in NAMED_RATIOS:
        if re.search(r"(^|[\s,.!?/])" + re.escape(named) + r"($|[\s,.!?/])", norm):
            return named
    for ratio in RATIO_TOKENS:
        if re.search(r"(^|[\s,.!?/])" + re.escape(ratio) + r"($|[\s,.!?/])", norm):
            return ratio
    return None


def select(request):
    family, explicit_id, frag = family_from_text(request)
    dynamic = False
    if family is None:
        family = "gpt-image-2-5-sunburst"  # owner-preferred general route (DoD 21; operator ruling 2026-09-09)
        dynamic = True
    elif family == "gpt-image-2-5-sunburst" and explicit_id is None and frag in GENERIC_GPT_ALIASES:
        dynamic = True
    ans = choose_answer(family, request, explicit_id, dynamic)
    # registry-driven capability check applies to ALL families; explicit pins
    # are re-checked too, against the literally requested ratio.
    conflict = None
    if ans["selected_model_id"]:
        conflict = capability_conflict(
            capability_entry(ans["selected_model_id"], family), request, detect_resolution(request))
    notes = list(ans.get("notes") or [])
    if conflict is not None:
        ans = conflict
    return {
        "request": request,
        "selected_model_id": ans["selected_model_id"],
        "selected_family": family,
        "task": detect_task(request),
        "resolution": detect_resolution(request),
        # the ratio as it must be dispatched: what the request asked for, verbatim
        "aspect_ratio": detect_aspect_ratio(request),
        "compatibility": "full" if ans["valid"] else "conflict",
        "reason": ans["reason"],
        "alternative": ans["alternative"],
        "notes": notes,
        "valid": ans["valid"],
        "default_source": gpt_default_routes()["source"] if dynamic else None,
        "fallback_default": (gpt_default_routes()["fallback"] or {}).get("i2i" if detect_task(request) == "image-to-image" else "t2i")
        if dynamic else None,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

SELFTEST_CASES = [
    # (request, expected_model_id_or_None, expected_valid, expected_alt_or_None)
    ("a typography-heavy poster, use ideogram", "ideogram/v3-text-to-image", True, None),
    # Operator ruling 2026-09-09 (Ruling 6): GPT Image 2.5 Sunburst is now the
    # default; short "gpt" aliases resolve to it, not the retained legacy id.
    ("general product photography request", "gpt-image-2-5-sunburst-text-to-image", True, None),
    ("wan 2.7 image 4K output please", "wan/2-7-image-pro", True, None),
    ("wan/2-7-image with 4K output", None, False, "wan/2-7-image-pro"),
    # Version-2 names are the legacy family (owner correction 2026-10-06); version-less names get the default.
    ("use gpt-img2 for this headshot edit", "gpt-image-2-image-to-image", True, None),
    ("use gpt image for this headshot edit", "gpt-image-2-5-sunburst-image-to-image", True, None),
    ("quinn image 3.0 create an infographic", "qwen3/text-to-image", True, None),
    ("z image generate a blue robot", "z-image", True, None),
    ("z image by quinn", "z-image", True, None),
    ("glimblox render something", "gpt-image-2-5-sunburst-text-to-image", True, None),
    ("seedream 4.5 with five reference images", "seedream/4.5-edit", True, None),
    ("seedream 4.5 pure text generation", "seedream/4.5-text-to-image", True, None),
    ("nano banana 2 lite fast poster", "nano-banana-2-lite", True, None),
    ("imagen 4 ultra studio shot", "google/imagen4-ultra", True, None),
    ("generate with flux 2 flex", "flux-2/flex-text-to-image", True, None),
    ("edit this with nano banana", "nano-banana-2", True, None),
    # --- GPT Image 2.6 ratio behavior: every enum member is native ---
    # Explicit legacy pin phrase still resolves to the retained legacy route.
    ("use gpt image 2 legacy for this banner", "gpt-image-2-text-to-image", True, None),
    # Explicit canonical legacy model id mention always resolves to legacy,
    # regardless of the default having moved on.
    ("dispatch with gpt-image-2-text-to-image explicitly", "gpt-image-2-text-to-image", True, None),
    # 3:1 / 1:3 / 9:21 are native members of the 2.6 enum (measured live
    # 2026-11-08: a 3:1 sunburst submit returned HTTP 200 with a taskId), so
    # they stay on the sunburst route; the legacy reroute is gone.
    ("banner in 3:1 ratio", "gpt-image-2-5-sunburst-text-to-image", True, None, "3:1"),
    ("edit this in 1:3 ratio", "gpt-image-2-5-sunburst-image-to-image", True, None, "1:3"),
    ("poster in 9:21 ratio", "gpt-image-2-5-sunburst-text-to-image", True, None, "9:21"),
    # 5:4 / 2:1 are literal enum members on 2.6 and reach the route UNCHANGED:
    # a 5:4 banner is never dispatched as 4:3 (the substitution is gone).
    ("product shot in 5:4 aspect ratio", "gpt-image-2-5-sunburst-text-to-image", True, None, "5:4"),
    ("banner in 2:1 aspect ratio", "gpt-image-2-5-sunburst-text-to-image", True, None, "2:1"),
    # 9:8 / 16:27 / 27:16 / 8:9 are NOT members of the GPT Image 2.6 enum at
    # all, so they hard-fail at EVERY resolution -- not just at 2K/4K. The
    # ratio is still detected; nothing coerces it to a member.
    ("photo at 9:8 aspect ratio in 4K", None, False, None, "9:8"),
    ("photo at 9:8 aspect ratio", None, False, None, "9:8"),
]


# (name, fake adapter answer or None=no adapter or "broken", request,
#  expected_model_id [, expected_aspect_ratio])
NEWER = {"state": "success", "data": {"family": "gpt-image", "source": "live", "changed": True, "routes": {
    "Text to Image": "gpt-image-3-aurora-text-to-image", "Image to Image": "gpt-image-3-aurora-image-to-image"}}}
DYNAMIC_CASES = [
    ("newer generation becomes the default (t2i)", NEWER, "general product photography request",
     "gpt-image-3-aurora-text-to-image"),
    ("newer generation becomes the default (i2i)", NEWER, "edit this headshot with gpt image",
     "gpt-image-3-aurora-image-to-image"),
    ("version-less generic alias follows the newest generation", NEWER, "use gpt image for this poster",
     "gpt-image-3-aurora-text-to-image"),
    ("openai image follows the newest generation", NEWER, "make an openai image of a leaf",
     "gpt-image-3-aurora-text-to-image"),
    ("gpt image 2 names version 2: legacy, not auto-latest", NEWER, "use gpt image 2 for this poster",
     "gpt-image-2-text-to-image"),
    ("gpt-img2 names version 2: legacy, not auto-latest", NEWER, "edit this headshot with gpt-img2",
     "gpt-image-2-image-to-image"),
    ("explicit 2.5 alias is a pin and never moves", NEWER, "use gpt image 2.5 sunburst for this poster",
     "gpt-image-2-5-sunburst-text-to-image"),
    ("explicit canonical id is a pin", NEWER, "dispatch with gpt-image-2-5-sunburst-text-to-image explicitly",
     "gpt-image-2-5-sunburst-text-to-image"),
    ("another family pin is untouched", NEWER, "use ideogram for typography", "ideogram/v3-text-to-image"),
    ("legacy 3:1 is native on 2.6 and follows the newest default", NEWER, "banner in 3:1 ratio",
     "gpt-image-3-aurora-text-to-image", "3:1"),
    ("4:5 passes through literally on the newest default", NEWER, "product shot in 4:5 aspect ratio",
     "gpt-image-3-aurora-text-to-image", "4:5"),
    ("adapter unreachable falls back to models.json", "broken", "general product photography request",
     "gpt-image-2-5-sunburst-text-to-image"),
    # an auto-latest id newer than the models.json snapshot still gets the
    # family's capability row, so an out-of-enum ratio stays refused
    ("out-of-enum ratio is refused on the newest default", NEWER, "photo at 9:8 aspect ratio",
     None, "9:8"),
]


def _dynamic_selftest():
    import tempfile
    failures = []
    saved = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "kie_live_adapter.py")
        with open(script, "w") as fh:
            fh.write("import json, os, sys\nsys.stdout.write(open(os.path.join(os.path.dirname(__file__), 'answer.json')).read())\n")
        for case in DYNAMIC_CASES:
            name, answer, req, exp = case[:4]
            exp_ratio = case[4] if len(case) > 4 else None
            _DEFAULT_MEMO.clear()
            if answer is None:
                os.environ["KIE_LIVE_ADAPTER_PATH"] = ""
            elif answer == "broken":
                with open(os.path.join(d, "answer.json"), "w") as fh:
                    fh.write("this is not json")
                os.environ["KIE_LIVE_ADAPTER_PATH"] = script
            else:
                with open(os.path.join(d, "answer.json"), "w") as fh:
                    json.dump(answer, fh)
                os.environ["KIE_LIVE_ADAPTER_PATH"] = script
            res = select(req)
            got = res["selected_model_id"]
            if got != exp:
                failures.append("FAIL %s: %r expected %s got %s" % (name, req, exp, got))
            if exp_ratio is not None and res["aspect_ratio"] != exp_ratio:
                failures.append("FAIL %s: %r expected aspect_ratio %s unchanged, got %s" % (
                    name, req, exp_ratio, res["aspect_ratio"]))
    if saved is None:
        os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
    else:
        os.environ["KIE_LIVE_ADAPTER_PATH"] = saved
    _DEFAULT_MEMO.clear()
    return failures


def selftest():
    # the static battery must not depend on the network or on a sibling adapter: bridge off
    saved = os.environ.get("KIE_LIVE_ADAPTER_PATH")
    os.environ["KIE_LIVE_ADAPTER_PATH"] = ""
    _DEFAULT_MEMO.clear()
    failures = []
    for case in SELFTEST_CASES:
        req, exp_id, exp_valid, exp_alt = case[:4]
        exp_ratio = case[4] if len(case) > 4 else None
        res = select(req)
        got_bad = (
            res["selected_model_id"] != exp_id
            or res["valid"] != exp_valid
            or res["alternative"] != exp_alt
            or (exp_ratio is not None and res["aspect_ratio"] != exp_ratio)
        )
        if got_bad:
            failures.append(
                "FAIL %r: expected id=%s valid=%s alt=%s ratio=%s; got id=%s valid=%s alt=%s ratio=%s" % (
                    req, exp_id, exp_valid, exp_alt, exp_ratio,
                    res["selected_model_id"], res["valid"], res["alternative"], res["aspect_ratio"])
            )
    if saved is None:
        os.environ.pop("KIE_LIVE_ADAPTER_PATH", None)
    else:
        os.environ["KIE_LIVE_ADAPTER_PATH"] = saved
    failures += _dynamic_selftest()
    total = len(SELFTEST_CASES) + len(DYNAMIC_CASES)
    if failures:
        print("select_image_model.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print("select_image_model.py --self-test: %d/%d passed" % (total, total))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIE image model selector (skill 66)")
    parser.add_argument("request", nargs="?", help="natural-language image request")
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
