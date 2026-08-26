#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_payload.py -- validates an Agnes Image generation JSON request payload.

Authority: Spec §10.2-§10.5, §14.

Checks:
- `model`: required, must be "agnes-image-2.1-flash".
- `prompt`: required, non-empty string.
- `size`: required, must be in {"1K", "2K", "3K", "4K"} or legacy exact "WxH" (warns normalized).
- `ratio`: optional, must be in {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"} if provided.
- `response_format`: MUST NOT be at top-level (hard error exit 2). Allowed inside extra_body.response_format ("url" or "b64_json").
- `tags`: MUST NOT contain "img2img" (warn/info, ignored by endpoint).
- `extra_body.image`: optional array of strings (public HTTPS URLs or Data-URI Base64: data:image/(png|jpeg|jpg|webp);base64,...).
- Reference count: DO NOT hard-reject on count (spec §10.5); notes pricing formula for count > 3.
- `return_base64`: top-level boolean allowed.

Exit codes:
  0 -- valid payload
  2 -- validation failure (top-level response_format, bad model/size/ratio, invalid image data format)
  3 -- usage error / file read error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

SUPPORTED_MODELS = {"agnes-image-2.1-flash"}
SIZE_TIERS = {"1K", "2K", "3K", "4K"}
RATIOS = {"1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"}
VALID_FORMATS = {"url", "b64_json"}

DATA_URI_RE = re.compile(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=]+$")
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
EXACT_SIZE_RE = re.compile(r"^\d+x\d+$", re.IGNORECASE)


def validate_payload_data(data: dict) -> Tuple[bool, int, List[str], List[str]]:
    errors = []
    warnings = []

    # 1. Model
    model = data.get("model")
    if not model:
        errors.append("Missing required field: 'model'")
    elif model not in SUPPORTED_MODELS:
        errors.append(f"Invalid model '{model}'. Allowed: {sorted(list(SUPPORTED_MODELS))}")

    # 2. Prompt
    prompt = data.get("prompt")
    if prompt is None:
        errors.append("Missing required field: 'prompt'")
    elif not isinstance(prompt, str) or not prompt.strip():
        errors.append("Field 'prompt' must be a non-empty string.")

    # 3. Size
    size = data.get("size")
    if not size:
        errors.append("Missing required field: 'size'")
    elif isinstance(size, str):
        if size.upper() in SIZE_TIERS:
            pass
        elif EXACT_SIZE_RE.match(size):
            warnings.append(f"Legacy exact size '{size}' provided; service may normalize to nearest native tier.")
        else:
            errors.append(f"Invalid size '{size}'. Allowed tiers: {sorted(list(SIZE_TIERS))} or exact 'WxH'.")
    else:
        errors.append("Field 'size' must be a string.")

    # 4. Ratio
    ratio = data.get("ratio")
    if ratio is not None:
        if not isinstance(ratio, str) or ratio not in RATIOS:
            errors.append(f"Invalid ratio '{ratio}'. Allowed: {sorted(list(RATIOS))}")

    # 5. Top-level response_format (HARD ERROR)
    if "response_format" in data:
        errors.append(
            "Top-level 'response_format' is NOT allowed on Agnes Image API. "
            "Must be placed inside 'extra_body.response_format'."
        )

    # 6. Tags check
    tags = data.get("tags")
    if isinstance(tags, list) and any("img2img" in str(t).lower() for t in tags):
        warnings.append("Tag 'img2img' is unnecessary; presence of extra_body.image is sufficient.")

    # 7. return_base64
    return_b64 = data.get("return_base64")
    if return_b64 is not None and not isinstance(return_b64, bool):
        errors.append("Field 'return_base64' must be a boolean.")

    # 8. extra_body
    extra_body = data.get("extra_body")
    if extra_body is not None:
        if not isinstance(extra_body, dict):
            errors.append("Field 'extra_body' must be an object/dict.")
        else:
            # check extra_body.response_format
            resp_fmt = extra_body.get("response_format")
            if resp_fmt is not None and resp_fmt not in VALID_FORMATS:
                errors.append(f"Invalid extra_body.response_format '{resp_fmt}'. Allowed: {sorted(list(VALID_FORMATS))}")

            # check extra_body.image
            images = extra_body.get("image")
            if images is not None:
                if not isinstance(images, list):
                    errors.append("Field 'extra_body.image' must be an array of image URLs or Data URIs.")
                else:
                    count = len(images)
                    if count > 3:
                        warnings.append(
                            f"{count} reference images provided. First 3 free; list price from 4th is $0.003/image "
                            f"(formula: max(0, {count}-3)*$0.003; currently $0 during promo)."
                        )
                    for idx, img in enumerate(images):
                        if not isinstance(img, str) or not img.strip():
                            errors.append(f"extra_body.image[{idx}] must be a non-empty string.")
                        elif HTTP_URL_RE.match(img):
                            pass
                        elif DATA_URI_RE.match(img):
                            pass
                        else:
                            errors.append(
                                f"extra_body.image[{idx}] is neither a valid HTTP/HTTPS URL nor a supported "
                                "data:image/(png|jpeg|jpg|webp);base64,... URI."
                            )

    is_valid = len(errors) == 0
    exit_code = 0 if is_valid else 2
    return is_valid, exit_code, errors, warnings


def run_self_tests() -> int:
    fixtures = [
        # 1. Valid T2I payload -> exit 0
        ({
            "model": "agnes-image-2.1-flash",
            "prompt": "A scenic view",
            "size": "2K",
            "ratio": "16:9",
            "extra_body": {"response_format": "url"}
        }, 0),
        # 2. Top-level response_format -> exit 2
        ({
            "model": "agnes-image-2.1-flash",
            "prompt": "A scenic view",
            "size": "2K",
            "response_format": "url"
        }, 2),
        # 3. Valid multi-image (6 images) with Data URI -> exit 0 with pricing note
        ({
            "model": "agnes-image-2.1-flash",
            "prompt": "Restyle objects",
            "size": "1K",
            "extra_body": {
                "image": [
                    "https://example.com/1.png",
                    "https://example.com/2.png",
                    "https://example.com/3.png",
                    "https://example.com/4.png",
                    "https://example.com/5.png",
                    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                ],
                "response_format": "b64_json"
            }
        }, 0),
        # 4. Bad ratio -> exit 2
        ({
            "model": "agnes-image-2.1-flash",
            "prompt": "A view",
            "size": "1K",
            "ratio": "5:4"
        }, 2),
        # 5. Missing model -> exit 2
        ({
            "prompt": "A view",
            "size": "1K"
        }, 2),
    ]

    failed = 0
    for idx, (payload, expected_exit) in enumerate(fixtures, 1):
        _, actual_exit, errors, _ = validate_payload_data(payload)
        if actual_exit != expected_exit:
            print(f"Payload self-test fixture {idx} FAILED: expected exit {expected_exit}, got {actual_exit} ({errors})", file=sys.stderr)
            failed += 1

    if failed == 0:
        print("validate_payload.py --self-test: PASS (all fixtures verified)")
        return 0
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate Agnes Image generation JSON payload.")
    parser.add_argument("--self-test", action="store_true", help="Run deterministic test fixtures.")
    parser.add_argument("--payload", help="Path to JSON payload file.")
    parser.add_argument("--stdin", action="store_true", help="Read payload from stdin.")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_tests()

    payload_text = ""
    if args.payload:
        p = Path(args.payload)
        if not p.is_file():
            print(f"Error: file not found '{args.payload}'", file=sys.stderr)
            return 3
        payload_text = p.read_text(encoding="utf-8", errors="replace")
    elif args.stdin:
        payload_text = sys.stdin.read()
    else:
        parser.print_usage(sys.stderr)
        return 3

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON payload: {exc}", file=sys.stderr)
        return 3

    is_valid, exit_code, errors, warnings = validate_payload_data(data)
    result = {
        "valid": is_valid,
        "exit_code": exit_code,
        "errors": errors,
        "warnings": warnings
    }
    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
