#!/usr/bin/env python3
"""MiniMax H3 is its own model: 7,000 chars, never the Hailuo id.

Owner directive 2026-10-22 (verbatim): "Don't you ever change the model.
I told you H3. I meant H3." This file is the guard that makes the mistake
that prompted it impossible to repeat:

  * H3's canonical KIE ids (`minimax-h3/*`) are on the video allowlist and
    in price-menu.md, so a card lock of H3 dispatches;
  * the H3 prompt band is measured off the 67 catalog entry - 7,000 chars -
    and NOT through the Hailuo 2,000 override;
  * nothing aliases an H3 id onto a Hailuo id, in either direction.

Stdlib only. Run: python3 scripts/core/kie_dispatch/test_model_identity_h3.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
ROOT = CORE.parent.parent
sys.path.insert(0, str(CORE))

FS = []


def check(name, cond, detail=""):
    if cond:
        print("ok " + name)
    else:
        print("FAIL " + name + (" -- %s" % (detail,) if detail else ""))
        FS.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = load("model_lock_h3_guard", HERE / "model_lock.py")
PL = load("prompt_limits_h3_guard", CORE / "prompt_limits.py")

H3_I2V = "minimax-h3/image-to-video"
H3_T2V = "minimax-h3/text-to-video"
HAILUO = "hailuo/02-image-to-video-standard"

# 1. H3 is allowlisted and locks.
check("1: H3 image-to-video is on the allowlist", H3_I2V in ML.ALLOWED_VIDEO_MODELS)
check("1: H3 family wildcard is on the allowlist", "minimax-h3/*" in ML.ALLOWED_VIDEO_MODELS)
check("1: assert_allowed accepts H3 i2v", ML.assert_allowed(H3_I2V) == H3_I2V)
check("1: assert_allowed accepts H3 t2v", ML.assert_allowed(H3_T2V) == H3_T2V)

# 2. The menu table and the static fallback agree (drift test).
menu = ML.parse_price_menu(ROOT / "references" / "price-menu.md")
check("2: price-menu.md parses to the static allowlist exactly",
      tuple(menu) == ML.ALLOWED_VIDEO_MODELS, "parsed=%r" % (menu,))
check("2: price-menu.md names the H3 id", H3_I2V in menu, "parsed=%r" % (menu,))

# 3. No alias/substitution between the two families.
check("3: model_lock defines no H3->Hailuo alias",
      "minimax-h3" not in json.dumps({k: v for k, v in vars(ML).items()
                                      if isinstance(v, str)}))
check("3: prompt_limits MARKET_ALIASES does not alias H3",
      not any("minimax-h3" in str(k) or "minimax-h3" in str(v)
              for k, v in PL.MARKET_ALIASES.items()),
      "aliases=%r" % (PL.MARKET_ALIASES,))

# 4. The prompt cap is H3's own 7,000, not the Hailuo 2,000.
caps = PL.video_caps(H3_I2V)
check("4: H3 prompt cap is 7000", caps.get("prompt") == 7000, "caps=%r" % (caps,))
hailuo_caps = PL.video_caps(HAILUO)
check("4: Hailuo keeps its own 2000 cap", hailuo_caps.get("prompt") == 2000,
      "caps=%r" % (hailuo_caps,))

# 5. Measured against a real final payload: 6,800 passes, 7,001 refuses.
req_ok = {"model": H3_I2V, "input": {"prompt": "x" * 6800}}
req_over = {"model": H3_I2V, "input": {"prompt": "x" * 7001}}
try:
    rows = PL.check_request(H3_I2V, req_ok)["measured"]
    check("5: 6800 chars pass the H3 cap", True, rows)
except PL.PromptLimitError as exc:                       # noqa: F841
    check("5: 6800 chars pass the H3 cap", False, str(exc))
try:
    PL.check_request(H3_I2V, req_over)
    check("5: 7001 chars refuse on H3", False, "no refusal")
except PL.PromptLimitError as exc:
    check("5: 7001 chars refuse on H3", exc.code == "PROMPT_OVER_CAP", exc.code)

print()
if FS:
    print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
    raise SystemExit(1)
print("ALL PASS")
