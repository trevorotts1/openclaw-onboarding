#!/usr/bin/env python3
"""U15f: Kling as the card's video model (design 20-OPUS-PROMPT-TEMPLATE-SYSTEM
section 3.5 and unit table U15f).

The differences from H3 this proves:
  (a) a 2,501-char prompt for ``kling-3.0/video`` is REFUSED (hard max 2,500);
  (b) NO bracket syntax appears in any Kling prompt: the camera goes in PLAIN
      WORDS after the subject's motion, and an injected bracket is REFUSED;
  (c) a golden H3 spec re-assembled for ``kling-3.0-omni/image-to-video``
      lands inside 1,800-2,500.

Plus the rest of the design's 3.5 contract: the look is the mode's
``kling_block``, the negatives STAY IN the prompt, and the caps keep their
provenance (3,072 omni VERIFIED, 2,500 for 3.0/video UNVERIFIED, 2.5 turbo
VERIFIED) -- an UNVERIFIED cap is never silently promoted.

Stdlib only, offline, no paid calls, no network.

Run: python3 scripts/core/prompt_templates/test_prompt_templates_u15f.py
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import prompt_templates as PT  # noqa: E402

if not hasattr(PT, "assemble_kling_video"):
    if "pytest" in sys.modules:  # never sys.exit at import -- INTERNALERROR
        import pytest as _pytest
        _pytest.skip("U15f builder missing on this tree (no assemble_kling_video)",
                     allow_module_level=True)
    print("FAIL: U15f builder missing: %r has no assemble_kling_video "
          "(base tree)" % getattr(PT, "__file__", PT))
    sys.exit(1)

FIX = PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
OMNI = "kling-3.0-omni/image-to-video"
VIDEO3 = "kling-3.0/video"
TURBO = "kling/v2-5-turbo-image-to-video-pro"
FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _chars():
    return json.loads((FIX / "sample-characters.json").read_text("utf-8"))

def _specs():
    out = {}
    for p in sorted(FIX.glob("*-S*.json")):
        out[p.stem] = json.loads(p.read_text("utf-8"))
    return out

def _asm(spec, model, chars):
    s = copy.deepcopy(spec)
    s["model"] = model
    return PT.assemble_kling_video(s, chars)

# ---- (a) the hard max -----------------------------------------------------
def test_2501_refused_for_30_video():
    over = "x" * 2501
    v = PT.check_kling(over, {}, VIDEO3)
    check("(a) a 2,501-char prompt is REFUSE for kling-3.0/video",
          v["verdict"] == "REFUSE"
          and any(r.startswith("KLING_OVER_HARD_MAX") for r in v["reasons"]),
          (v["verdict"], v["reasons"]))
    # the control: the same length is NOT over the hard max for omni (3,072),
    # so the refusal above is the band's, not a blanket length rule.
    v2 = PT.check_kling("x" * 2501, {}, OMNI)
    check("(a) control: 2,501 on omni is not over ITS hard max",
          v2["verdict"] == "TRIM"
          and all("KLING_OVER_HARD_MAX" not in r for r in v2["reasons"]),
          (v2["verdict"], v2["reasons"]))
    # and 3,073 IS refused for omni
    v3 = PT.check_kling("x" * 3073, {}, OMNI)
    check("(a) 3,073 on omni is REFUSE (hard max 3,072 VERIFIED)",
          v3["verdict"] == "REFUSE"
          and any(r.startswith("KLING_OVER_HARD_MAX") for r in v3["reasons"]),
          (v3["verdict"], v3["reasons"]))

# ---- (b) no bracket syntax ------------------------------------------------
def test_no_bracket_syntax():
    chars = _chars()
    bad = []
    for name, spec in sorted(_specs().items()):
        prompt, _ = _asm(spec, OMNI, chars)
        if re.search(r"\[[^\]]*\]", prompt):
            bad.append(name)
        check("(b) %s assembled prompt carries no bracket group" % name,
              not re.search(r"\[[^\]]*\]", prompt),
              re.search(r"\[[^\]]*\]", prompt))
    check("(b) no assembled Kling prompt carries a bracket group",
          not bad, bad)
    # the checker refuses one, so a bracket can never reach a paid call
    spec = _specs()["talking-closeup-S07"]
    prompt, sections = _asm(spec, OMNI, chars)
    injected = prompt.replace("Camera movement follows", "[Push in] Camera movement follows", 1)
    v = PT.check_kling(injected, sections, OMNI)
    check("(b) an injected bracket is REFUSE KLING_BRACKET_SYNTAX",
          v["verdict"] == "REFUSE"
          and any(r.startswith("KLING_BRACKET_SYNTAX") for r in v["reasons"]),
          (v["verdict"], v["reasons"]))
    # the camera is PLAIN WORDS and sits AFTER the action section
    cam_line = [l for l in prompt.split("\n") if l.startswith("Camera:")]
    act_i = prompt.index("\nAction:")
    cam_i = prompt.index("\nCamera:")
    check("(b) the camera section is plain words after the action section",
          len(cam_line) == 1 and cam_i > act_i
          and "[" not in cam_line[0], cam_line)

# ---- (c) the golden specs land in the band --------------------------------
def test_golden_specs_land_in_band():
    chars = _chars()
    band = PT.band(OMNI)
    check("(c) omni band of record is floor 1800 / target 2500 / hard 3072",
          band["floor"] == 1800 and band["target_max"] == 2500
          and band["hard_max"] == 3072, band)
    n_ok = 0
    for name, spec in sorted(_specs().items()):
        prompt, sections = _asm(spec, OMNI, chars)
        v = PT.check_kling(prompt, sections, OMNI)
        in_band = 1800 <= len(prompt) <= 2500
        n_ok += bool(in_band and v["verdict"] == "PASS")
        check("(c) golden %s -> %d chars, PASS, in 1800-2500"
              % (name, len(prompt)), in_band and v["verdict"] == "PASS",
              (len(prompt), v["verdict"], v["reasons"]))
    check("(c) all six golden specs land inside the band", n_ok == 6, n_ok)
    # the 2.5 turbo band is the tighter one: 2,400 target, 2,500 hard max
    b25 = PT.band(TURBO)
    check("(c) 2.5 turbo shares the 1,800 floor and the 2,500 hard max",
          b25["floor"] == 1800 and b25["hard_max"] == 2500, b25)

# ---- the 3.5 contract: look, negatives, caps ------------------------------
def test_kling_block_look_and_negatives_stay_in():
    chars = _chars()
    spec = _specs()["talking-closeup-S07"]      # lifelike-3d, has kling_block
    prompt, sections = _asm(spec, OMNI, chars)
    mode = PT.load("mode", spec["mode"])
    check("the look carries the mode's kling_block, not the H3 block",
          mode["kling_block"][:40] in prompt
          and mode["h3_block"][:40] not in prompt,
          (mode["kling_block"][:40], ))
    check("the look is far shorter than the H3 look block",
          len(mode["kling_block"]) < len(mode["h3_block"]),
          (len(mode["kling_block"]), len(mode["h3_block"])))
    neg = [l for l in prompt.split("\n") if l.startswith("Avoid:")]
    check("negatives STAY IN the prompt (design 3.5)",
          len(neg) == 1 and "no scene cut" in neg[0], neg)
    check("no separate negative_prompt field is built",
          "negative_prompt" not in prompt, None)

def test_caps_keep_provenance():
    omni = PT.band_cap(OMNI)
    v3 = PT.band_cap(VIDEO3)
    trb = PT.band_cap(TURBO)
    check("omni cap 3,072 VERIFIED", omni["cap"] == 3072
          and omni["status"] == "VERIFIED", omni)
    check("3.0/video cap 2,500 stays UNVERIFIED (never promoted)",
          v3["cap"] == 2500 and v3["status"] == "UNVERIFIED", v3)
    check("2.5 turbo cap 2,500 VERIFIED", trb["cap"] == 2500
          and trb["status"] == "VERIFIED", trb)

def test_scale_limits_come_from_h3():
    lim = PT.kling_section_limits()
    h3 = PT.load("model", "minimax-h3")
    scale = float(PT.load("model", "kling-video")["section_scale"])
    wrong = []
    for s in h3["sections"]:
        want_max = int(round(s["max"] * scale)) if s["max"] else 0
        if lim[s["id"]]["max"] != want_max:
            wrong.append((s["id"], lim[s["id"]]["max"], want_max))
    check("every Kling section budget is H3's max * 0.38 (no second table)",
          not wrong, wrong)
    check("the scale is the one kling-video.json declares (0.38)",
          abs(scale - 0.38) < 1e-9, scale)

def test_model_gate():
    chars = _chars()
    spec = _specs()["talking-closeup-S07"]
    bad = copy.deepcopy(spec)
    bad["model"] = "minimax-h3/image-to-video"
    try:
        PT.assemble_kling_video(bad, chars)
        check("an H3 model is refused by the Kling assembler", False,
              "no error raised")
    except PT.PromptTemplateError as exc:
        check("an H3 model is refused by the Kling assembler",
              exc.code == "KLING_MODEL_NOT_IN_BLOCK", exc.code)

def main():
    print("U15f: Kling as the card's video model (design 3.5)")
    print("-" * 64)
    test_2501_refused_for_30_video()
    test_no_bracket_syntax()
    test_golden_specs_land_in_band()
    test_kling_block_look_and_negatives_stay_in()
    test_caps_keep_provenance()
    test_scale_limits_come_from_h3()
    test_model_gate()
    print("-" * 64)
    if FAILS:
        print("FAIL: %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ok: all U15f checks passed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
