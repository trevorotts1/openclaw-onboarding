#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
select_image_model.py - Skill 66 kie-image model selector.

Maps a natural-language image request to a KIE Market canonical_model_id, or
returns valid=false with an alternative when the request cannot be served.

STDLIB PYTHON3 ONLY. Deterministic. No network. No secrets read.

Exit codes:
  0  selected (valid=true)
  1  no model can serve the request as written (valid=false, alternative may be set)

Output: single JSON object on stdout.
"""

import argparse
import json
import re
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Minimal routing table. Full per-model limits live in models.json (the
# registry). SELECTOR PADDING IS FORBIDDEN (spec 7.2 last line): only add a
# family here when it is in models.json and research-backed.
# ---------------------------------------------------------------------------

REGISTRY = {
    "gpt-image-2": {
        "name": "GPT Image 2",
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
            "edit": {"canonical_model_id": "seedream/4-5-edit", "task": "image-to-image"},
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
    # gpt family
    "gpt-img2": "gpt-image-2",
    "gpt img2": "gpt-image-2",
    "gpt image 2": "gpt-image-2",
    "gpt-image 2": "gpt-image-2",
    "gpt image 2.0": "gpt-image-2",
    "gpt-image-2.0": "gpt-image-2",
    "gpt-image-2": "gpt-image-2",
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


def choose_answer(family, request, explicit_model_id):
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

    # --- gpt-image-2 ----------------------------------------------------------
    if family == "gpt-image-2":
        if task == "image-to-image":
            return _ok(routes["i2i"]["canonical_model_id"], "GPT Image 2 image-to-image")
        return _ok(routes["t2i"]["canonical_model_id"], "GPT Image 2 text-to-image")

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


def _ok(model_id, reason):
    return {"valid": True, "selected_model_id": model_id, "reason": reason, "alternative": None}


def select(request):
    family, explicit_id, frag = family_from_text(request)
    if family is None:
        family = "gpt-image-2"  # owner-preferred general route (DoD 21)
    ans = choose_answer(family, request, explicit_id)
    return {
        "request": request,
        "selected_model_id": ans["selected_model_id"],
        "selected_family": family,
        "task": detect_task(request),
        "resolution": detect_resolution(request),
        "compatibility": "full" if ans["valid"] else "conflict",
        "reason": ans["reason"],
        "alternative": ans["alternative"],
        "notes": [],
        "valid": ans["valid"],
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

SELFTEST_CASES = [
    # (request, expected_model_id_or_None, expected_valid, expected_alt_or_None)
    ("a typography-heavy poster, use ideogram", "ideogram/v3-text-to-image", True, None),
    ("general product photography request", "gpt-image-2-text-to-image", True, None),
    ("wan 2.7 image 4K output please", "wan/2-7-image-pro", True, None),
    ("wan/2-7-image with 4K output", None, False, "wan/2-7-image-pro"),
    ("use gpt-img2 for this headshot edit", "gpt-image-2-image-to-image", True, None),
    ("quinn image 3.0 create an infographic", "qwen3/text-to-image", True, None),
    ("z image generate a blue robot", "z-image", True, None),
    ("z image by quinn", "z-image", True, None),
    ("glimblox render something", "gpt-image-2-text-to-image", True, None),
    ("seedream 4.5 with five reference images", "seedream/4-5-edit", True, None),
    ("seedream 4.5 pure text generation", "seedream/4.5-text-to-image", True, None),
    ("nano banana 2 lite fast poster", "nano-banana-2-lite", True, None),
    ("imagen 4 ultra studio shot", "google/imagen4-ultra", True, None),
    ("generate with flux 2 flex", "flux-2/flex-text-to-image", True, None),
    ("edit this with nano banana", "nano-banana-2", True, None),
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
                "FAIL %r: expected id=%s valid=%s alt=%s; got id=%s valid=%s alt=%s" % (
                    req, exp_id, exp_valid, exp_alt,
                    res["selected_model_id"], res["valid"], res["alternative"])
            )
    if failures:
        print("select_image_model.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print("select_image_model.py --self-test: %d/%d passed"
          % (len(SELFTEST_CASES), len(SELFTEST_CASES)))
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
