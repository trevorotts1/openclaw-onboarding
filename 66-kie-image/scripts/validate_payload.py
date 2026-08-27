#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_payload.py - Skill 66 kie-image payload validator.

Validates a KIE Market createTask payload JSON against the registry
(models.json) before submission. STDLIB PYTHON3 ONLY. Deterministic.
No network. No secrets read.

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

TASK_ENDPOINT = "/api/v1/jobs/createTask"

MIME_BY_EXT = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "gif": "image/gif",
    "tif": "image/tiff", "tiff": "image/tiff",
}


def load_registry():
    with open(REGISTRY_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    by_id = {}
    for m in data["models"]:
        by_id[m["canonical_model_id"]] = m
    return data, by_id


def norm_media(value):
    """Normalize a format token: extensions and MIME types alike -> lower."""
    return value.strip().lower()


def format_matches(token, formats):
    """True when token (ext like 'jpg' or mime like 'image/jpeg') is covered by the formats list."""
    if not formats:
        return None  # unknown, skip
    token = norm_media(token)
    normalized = [norm_media(f) for f in formats]
    if token in normalized:
        return True
    # token is ext, formats are mime (or vice versa)
    mime = MIME_BY_EXT.get(token.replace(".", ""))
    if mime and mime in normalized:
        return True
    ext = token.split("/")[-1] if "/" in token else token.replace(".", "")
    for f in normalized:
        if f.replace(".", "").split("/")[-1] == ext:
            return True
    return False


def parse_data_uri(ref):
    if not ref.startswith("data:"):
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


def ref_media_type(ref):
    """Best-effort media type from a url or data uri: ext name or mime."""
    if ref.startswith("data:"):
        info = parse_data_uri(ref)
        return info.get("media") if info else None
    path = ref.split("?")[0].split("#")[0]
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext or None


def check_refs(model, refs_value, errors, warnings):
    """Validate reference image list against registry caps (count / mb / formats)."""
    max_count = model.get("reference_images_max")
    max_mb = model.get("reference_image_max_mb")
    formats = model.get("reference_image_formats")

    if not isinstance(refs_value, list):
        errors.append("reference input must be a list of urls")
        return

    if max_count is not None:
        if len(refs_value) > max_count:
            errors.append(
                "reference image count %d exceeds published maximum %d (%s)" % (
                    len(refs_value), max_count, model["canonical_model_id"]))
        elif (model.get("canonical_model_id") == "seedream/4-5-edit"
                and max_count == 14 and len(refs_value) >= 11):
            warnings.append(
                "reference count %d is inside the field-editor maximum (14) but the README "
                "states support for up to 10 reference images; UNDETERMINED which governs" % len(refs_value))

    if max_mb is not None:
        for i, ref in enumerate(refs_value):
            size = None
            if isinstance(ref, str) and ref.startswith("data:"):
                info = parse_data_uri(ref)
                if info and info.get("error"):
                    warnings.append("ref[%d]: %s" % (i, info["error"]))
                    continue
                size = info.get("bytes")
                media = info.get("media")
                if formats and media and not format_matches(media, formats):
                    warnings.append("ref[%d]: data URI media %r not in exposed format list %r" % (
                        i, media, formats))
            elif isinstance(ref, str):
                warnings.append("ref[%d]: remote URL - size and format unverifiable client-side" % i)
            else:
                warnings.append("ref[%d]: not a string url" % i)
            if size is not None and max_mb is not None:
                limit = int(max_mb * 1024 * 1024)
                if size > limit:
                    errors.append(
                        "ref[%d]: %d bytes exceeds %s MB limit (%d bytes)" % (i, size, max_mb, limit))
    elif formats:
        for i, ref in enumerate(refs_value if isinstance(refs_value, list) else []):
            if isinstance(ref, str):
                mt = ref_media_type(ref)
                if mt and not format_matches(mt, formats):
                    warnings.append("ref[%d]: media %r not in exposed format list %r" % (i, mt, formats))


def validate(payload, model_id_override=None):
    registry, by_id = load_registry()
    errors = []
    warnings = []
    checked = {}

    if not isinstance(payload, dict):
        errors.append("payload must be a JSON object")
        return {"valid": False, "model_id": model_id_override, "api_family": None,
                "errors": errors, "warnings": warnings, "checked": checked}

    unknown_top = [k for k in payload if k not in ("model", "input", "callBackUrl", "api_family", "create_endpoint")]
    if unknown_top:
        warnings.append("unknown top-level keys: %s" % ", ".join("%s (ignored)" % k for k in unknown_top))

    if payload.get("create_endpoint") not in (None, TASK_ENDPOINT):
        errors.append("create_endpoint must be %s" % TASK_ENDPOINT)
    checked["create_endpoint"] = payload.get("create_endpoint") or TASK_ENDPOINT

    api_family = payload.get("api_family")
    if api_family is not None and api_family != "kie-market":
        errors.append("api_family %r is not kie-market" % api_family)

    model_name = payload.get("model")
    if not model_name:
        errors.append("payload missing 'model'")
        return {"valid": False, "model_id": None, "api_family": api_family,
                "errors": errors, "warnings": warnings, "checked": checked}

    if model_id_override and model_name != model_id_override:
        errors.append("payload model %r does not match expected model %r" % (model_name, model_id_override))

    model = by_id.get(model_name)
    if not model:
        errors.append("model %r not present in registry (%s)" % (model_name, REGISTRY_PATH))
        return {"valid": False, "model_id": model_name, "api_family": api_family,
                "errors": errors, "warnings": warnings, "checked": checked}

    checked["model"] = model_name
    if api_family is None:
        api_family = model.get("api_family")
    checked["api_family"] = api_family

    if model.get("api_family") != "kie-market":
        errors.append("registry api_family %r is not kie-market" % model.get("api_family"))

    inp = payload.get("input")
    if not isinstance(inp, dict):
        errors.append("payload 'input' must be an object")
        return {"valid": False, "model_id": model_name, "api_family": api_family,
                "errors": errors, "warnings": warnings, "checked": checked}

    known_fields = set(model.get("control_fields") or [])
    if "prompt" in inp or True:
        known_fields = known_fields | {
            "prompt", "negative_prompt", "aspect_ratio", "resolution", "output_format",
            "input_urls", "image_urls", "image_input", "seed", "quality", "nsfw_checker",
            "prompt_extend", "style", "rendering_speed", "expand_prompt", "image_size",
            "style_codes", "mask_url", "strength", "num_images", "bbox_list",
            "enable_sequential", "thinking_mode", "n", "color_palette", "watermark",
            "im_no", "mode", "limit", "first_image", "second_image",
        }
    unknown_in = [k for k in inp if k not in known_fields]
    if unknown_in:
        warnings.append("unknown input keys (route may ignore): %s" % ", ".join(unknown_in))

    if "prompt" not in inp:
        errors.append("input missing 'prompt'")
    else:
        checked["prompt_chars"] = len(str(inp["prompt"]).strip())

    if model.get("canonical_model_id") == "seedream/4.5-text-to-image" and "output_format" in inp:
        warnings.append("Seedream 4.5 text-to-image exposes NO output_format field; route may ignore it")

    if model.get("canonical_model_id") == "google/nano-banana" and "resolution" in inp:
        warnings.append("Legacy Nano Banana exposes NO resolution parameter")

    if model.get("canonical_model_id") == "nano-banana-2-lite" and (
            "resolution" in inp or "output_format" in inp):
        warnings.append("Nano Banana 2 Lite exposes only prompt / image_urls / aspect_ratio; "
                        "resolution and output_format may be ignored")

    # ---- reference images -------------------------------------------------
    ref_keys = [k for k in ("input_urls", "image_urls", "image_input") if k in inp]
    if ref_keys:
        refs = inp[ref_keys[0]]
        check_refs(model, refs, errors, warnings)
        checked["ref_key"] = ref_keys[0]
        checked["ref_count"] = len(refs) if isinstance(refs, list) else None
    else:
        checked["ref_count"] = 0
        if model.get("reference_images_max") is not None and model.get("reference_images_max") == 1:
            warnings.append("route expects exactly one reference image (edit/remix); none provided")

    if model.get("canonical_model_id") == "ideogram/v3-edit" and "image_url" in inp:
        # single-image edit: image_url is a scalar
        if isinstance(inp["image_url"], list):
            errors.append("ideogram/v3-edit expects a single image_url string, got a list")
        else:
            single_mock = [inp["image_url"]]
            check_refs(model, single_mock, errors, warnings)

    if model.get("canonical_model_id") == "ideogram/v3-remix" and "strength" in inp:
        s = inp["strength"]
        if not (isinstance(s, (int, float)) and 0.01 <= s <= 1.0):
            errors.append("ideogram/v3-remix strength must be in [0.01, 1.0] (got %r)" % (s,))
        checked["strength"] = s

    # ---- aspect ratio / resolution ----------------------------------------
    ratio = inp.get("aspect_ratio") or inp.get("image_size")
    res = inp.get("resolution")
    if ratio is not None:
        allowed = model.get("aspect_ratios")
        if allowed and str(ratio) not in [str(a) for a in allowed]:
            errors.append("aspect_ratio %r not in exposed enum %s" % (ratio, allowed))
    if res is not None:
        allowed = model.get("resolutions")
        if allowed and str(res) not in [str(a) for a in allowed]:
            errors.append("resolution %r not in exposed enum %s" % (res, allowed))

    # GPT Image 2 per-resolution exclusions (docs verbatim)
    if model.get("canonical_model_id", "").startswith("gpt-image-2"):
        excl = model.get("ratio_resolution_exclusions") or []
        if res in ("2K", "4K") and ratio in excl:
            errors.append(
                "GPT Image 2: aspect ratio %s is NOT supported at %s resolution (2K/4K exclude "
                "5:4, 4:5, 3:1, 1:3, 9:21)" % (ratio, res))
        if ratio == "auto" and res not in (None, "1K"):
            errors.append("GPT Image 2: aspect ratio 'auto' converts to 1K only; %s requested" % res)
        if ratio == "1:1" and res == "4K":
            errors.append("GPT Image 2: 1:1 aspect ratio cannot be converted to 4K images")

    # ---- Wan ---------------------------------------------------------------
    if model.get("canonical_model_id", "").startswith("wan/"):
        n = inp.get("n")
        seq = inp.get("enable_sequential")
        if n is not None:
            if isinstance(n, bool):
                errors.append("wan n must be an int, got bool")
            else:
                try:
                    n_int = int(n)
                except (TypeError, ValueError):
                    errors.append("wan n must be an integer, got %r" % (n,))
                    n_int = None
                if n_int is not None:
                    hi = 12 if seq else 4
                    if not (1 <= n_int <= hi):
                        errors.append("wan n must be 1-%d (or 1-12 with enable_sequential=true); got %d"
                                      % (hi, n_int))
                    checked["wan_n"] = n_int
        bbox = inp.get("bbox_list")
        urls = inp.get("input_urls") or []
        if bbox is not None:
            if not isinstance(bbox, list):
                errors.append("bbox_list must be a list parallel to input_urls")
            else:
                if isinstance(urls, list) and len(bbox) > len(urls):
                    errors.append("bbox_list has %d entries for %d input images" % (len(bbox), len(urls)))
                for i, b in enumerate(bbox):
                    boxes = None
                    if isinstance(b, str):
                        try:
                            parsed = json.loads(b)
                            boxes = parsed if isinstance(parsed, list) else [parsed]
                        except Exception:
                            boxes = None
                    elif isinstance(b, list):
                        boxes = b
                    if boxes is None:
                        warnings.append("bbox_list[%d]: unparseable box spec %r" % (i, b))
                    elif len(boxes) > 2:
                        errors.append("bbox_list[%d]: %d boxes; each image supports up to 2 boxes" % (i, len(boxes)))

    # ---- output format ------------------------------------------------------
    of = inp.get("output_format")
    if of is not None and model.get("output_formats"):
        if str(of).lower() not in [str(x).lower() for x in model["output_formats"]]:
            errors.append("output_format %r not in exposed enum %s" % (of, model["output_formats"]))

    checked["errors"] = len(errors)
    checked["warnings"] = len(warnings)
    return {"valid": not errors, "model_id": model_name, "api_family": api_family,
            "errors": errors, "warnings": warnings, "checked": checked}


# ---------------------------------------------------------------------------
# Self-test: spec 18.3 boundary fixtures plus rule checks.
# ---------------------------------------------------------------------------

def _base(model_id, input_extra, extra_top=None):
    inp = {"prompt": "a test prompt"} if "prompt" not in input_extra else {}
    inp.update(input_extra)
    payload = {"model": model_id, "callBackUrl": "https://example.invalid/cb", "input": inp}
    if extra_top:
        payload.update(extra_top)
    return payload


def _refs(n, size_mb=None, prefix="https://cdn.example.invalid/img_%d.png"):
    out = []
    for i in range(n):
        out.append(prefix % i)
    return out


def selftest():
    cases = []

    def case(name, payload, expect_valid, expect_err_contains=None, expect_warn_contains=None):
        cases.append((name, payload, expect_valid, expect_err_contains, expect_warn_contains))

    # 18.3 boundary pairs
    case("gpt-image-2 i2i 16 refs OK",
         _base("gpt-image-2-image-to-image", {"input_urls": _refs(16)}), True)
    case("gpt-image-2 i2i 17 refs FAIL",
         _base("gpt-image-2-image-to-image", {"input_urls": _refs(17)}), False,
         expect_err_contains="exceeds published maximum 16")
    case("nano-banana-2 14 refs OK",
         _base("nano-banana-2", {"image_input": _refs(14)}), True)
    case("nano-banana-2 15 refs FAIL",
         _base("nano-banana-2", {"image_input": _refs(15)}), False,
         expect_err_contains="exceeds published maximum 14")
    case("nano-banana-2-lite 10 refs OK",
         _base("nano-banana-2-lite", {"image_urls": _refs(10)}), True)
    case("nano-banana-2-lite 11 refs FAIL",
         _base("nano-banana-2-lite", {"image_urls": _refs(11)}), False,
         expect_err_contains="exceeds published maximum 10")
    case("nano-banana-pro 8 refs OK",
         _base("nano-banana-pro", {"image_input": _refs(8)}), True)
    case("nano-banana-pro 9 refs FAIL",
         _base("nano-banana-pro", {"image_input": _refs(9)}), False,
         expect_err_contains="exceeds published maximum 8")
    case("seedream 5 pro i2i 10 refs OK",
         _base("seedream/5-pro-image-to-image", {"image_urls": _refs(10)}), True)
    case("seedream 5 pro i2i 11 refs FAIL",
         _base("seedream/5-pro-image-to-image", {"image_urls": _refs(11)}), False,
         expect_err_contains="exceeds published maximum 10")
    case("seedream 5 lite i2i 14 refs OK",
         _base("seedream/5-lite-image-to-image", {"image_urls": _refs(14)}), True)
    case("seedream 5 lite i2i 15 refs FAIL",
         _base("seedream/5-lite-image-to-image", {"image_urls": _refs(15)}), False,
         expect_err_contains="exceeds published maximum 14")
    case("seedream 4.5 edit 14 refs OK (warn)",
         _base("seedream/4-5-edit", {"image_urls": _refs(14)}), True,
         expect_warn_contains="10 reference images")
    case("seedream 4.5 edit 11 refs OK (warn)",
         _base("seedream/4-5-edit", {"image_urls": _refs(11)}), True,
         expect_warn_contains="10 reference images")
    case("seedream 4.5 edit 10 refs OK (no warn)",
         _base("seedream/4-5-edit", {"image_urls": _refs(10)}), True)
    case("seedream 4.5 edit 15 refs FAIL",
         _base("seedream/4-5-edit", {"image_urls": _refs(15)}), False,
         expect_err_contains="exceeds published maximum 14")
    case("wan 2.7 image 9 refs OK",
         _base("wan/2-7-image", {"input_urls": _refs(9)}), True)
    case("wan 2.7 image 10 refs FAIL",
         _base("wan/2-7-image", {"input_urls": _refs(10)}), False,
         expect_err_contains="exceeds published maximum 9")

    # GPT Image 2 resolution/ratio rules
    case("gpt-image-2 2K with 5:4 FAIL",
         _base("gpt-image-2-text-to-image", {"aspect_ratio": "5:4", "resolution": "2K"}), False,
         expect_err_contains="NOT supported at 2K")
    case("gpt-image-2 4K with 9:21 FAIL",
         _base("gpt-image-2-text-to-image", {"aspect_ratio": "9:21", "resolution": "4K"}), False,
         expect_err_contains="NOT supported at 4K")
    case("gpt-image-2 4K with 16:9 OK",
         _base("gpt-image-2-text-to-image", {"aspect_ratio": "16:9", "resolution": "4K"}), True)
    case("gpt-image-2 1:1 to 4K FAIL",
         _base("gpt-image-2-text-to-image", {"aspect_ratio": "1:1", "resolution": "4K"}), False,
         expect_err_contains="cannot be converted to 4K")
    case("gpt-image-2 auto with 2K FAIL",
         _base("gpt-image-2-text-to-image", {"aspect_ratio": "auto", "resolution": "2K"}), False,
         expect_err_contains="auto")

    # Wan n / bbox
    case("wan n=4 OK", _base("wan/2-7-image", {"n": 4}), True)
    case("wan n=5 FAIL", _base("wan/2-7-image", {"n": 5}), False, expect_err_contains="1-4")
    case("wan n=12 gallery OK", _base("wan/2-7-image", {"n": 12, "enable_sequential": True}), True)
    case("wan n=13 gallery FAIL",
         _base("wan/2-7-image", {"n": 13, "enable_sequential": True}), False,
         expect_err_contains="1-12")
    case("wan bbox 2 boxes OK",
         _base("wan/2-7-image", {"input_urls": _refs(1), "bbox_list": ["[[10,10,100,100],[150,150,200,200]]"]}),
         True)
    case("wan bbox 3 boxes FAIL",
         _base("wan/2-7-image", {"input_urls": _refs(1),
                                 "bbox_list": ["[[0,0,1,1],[2,2,3,3],[4,4,5,5]]"]}), False,
         expect_err_contains="up to 2 boxes")

    # Ideogram remix strength
    case("remix strength 0.8 OK", _base("ideogram/v3-remix", {"image_url": "https://x.invalid/a.png", "strength": 0.8}), True)
    case("remix strength 0.0 FAIL", _base("ideogram/v3-remix", {"image_url": "https://x.invalid/a.png", "strength": 0.0}), False,
         expect_err_contains="strength")
    case("remix strength 1.5 FAIL", _base("ideogram/v3-remix", {"image_url": "https://x.invalid/a.png", "strength": 1.5}), False,
         expect_err_contains="strength")

    # data-uri size decode
    big_b64 = base64.b64encode(b"x" * (31 * 1024 * 1024)).decode()
    case("gpt-image-2 i2i 31MB data uri FAIL",
         _base("gpt-image-2-image-to-image", {"input_urls": ["data:image/png;base64," + big_b64]}), False,
         expect_err_contains="exceeds 30 MB")
    small_b64 = base64.b64encode(b"x" * 1024).decode()
    case("gpt-image-2 i2i 1KB data uri OK",
         _base("gpt-image-2-image-to-image", {"input_urls": ["data:image/png;base64," + small_b64]}), True)

    # unknown keys -> warning, not error
    case("unknown input key warns",
         _base("gpt-image-2-text-to-image", {"frobnicate": True}), True,
         expect_warn_contains="unknown input keys")
    case("unknown top-level key warns",
         _base("gpt-image-2-text-to-image", {}, extra_top={"wat": 1}), True,
         expect_warn_contains="unknown top-level")

    # api_family enforcement
    case("api_family wrong FAIL",
         _base("gpt-image-2-text-to-image", {}, extra_top={"api_family": "google-vertex"}), False,
         expect_err_contains="kie-market")
    case("create_endpoint wrong FAIL",
         _base("gpt-image-2-text-to-image", {}, extra_top={"create_endpoint": "/api/v1/other"}), False,
         expect_err_contains="create_endpoint")

    # aspect enum membership
    case("aspect_ratio bogus FAIL",
         _base("z-image", {"aspect_ratio": "7:9"}), False, expect_err_contains="not in exposed enum")

    # unknown model
    case("unknown model FAIL", {"model": "not/a-model", "input": {"prompt": "x"}}, False,
         expect_err_contains="not present in registry")

    failures = []
    for name, payload, exp_valid, exp_err, exp_warn in cases:
        result = validate(payload)
        if result["valid"] != exp_valid:
            failures.append("FAIL %s: expected valid=%s got valid=%s errors=%s" % (
                name, exp_valid, result["valid"], result["errors"]))
            continue
        if exp_err and not any(exp_err in e for e in result["errors"]):
            failures.append("FAIL %s: expected error containing %r, got errors=%s" % (
                name, exp_err, result["errors"]))
        if exp_warn and not any(exp_warn in w for w in result["warnings"]):
            failures.append("FAIL %s: expected warning containing %r, got warnings=%s" % (
                name, exp_warn, result["warnings"]))

    if failures:
        print("validate_payload.py --self-test FAILED", file=sys.stderr)
        for f in failures:
            print("  " + f, file=sys.stderr)
        return 1
    print("validate_payload.py --self-test: %d/%d passed" % (len(cases), len(cases)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="KIE payload validator (skill 66)")
    parser.add_argument("payload", nargs="?", help="path to payload JSON, or '-' for stdin")
    parser.add_argument("--model", help="expected canonical_model_id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return selftest()

    if not args.payload:
        parser.error("payload required (path or '-') or use --self-test")
    if args.payload == "-":
        data = sys.stdin.read()
    else:
        with open(args.payload, "r", encoding="utf-8") as fh:
            data = fh.read()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "model_id": args.model, "api_family": None,
                          "errors": ["invalid JSON: %s" % exc], "warnings": [], "checked": {}}))
        return 1
    result = validate(payload, model_id_override=args.model)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
