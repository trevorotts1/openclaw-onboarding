#!/usr/bin/env python3
"""U-PROMPT lane 8: the refusal rules the data files state, proved in check().

Covers the rows that name a template test and had none:
  * F-PM-5 / R-2 — a stillness or angle-cheat phrase is refused.
  * F-PIC-3      — three places stacked in one frame are refused.
  * G-STORY-04   — an Avoid sentence that empties a full room (5+ singers) is
                   refused; the same sentence on a small cast passes.
  * G-MOTION-01  — the H3 template and the animation rules both state that a
                   performance prompt never carries the stillness sentence.

Stdlib only; no network, no spend. Run:
    python3 scripts/core/prompt_templates/test_rule_data_u_prompt8.py
Exit 0 = all pass.
"""
from __future__ import annotations

import json
import os
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

FIX = PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
FAILS = []


def check(name, ok, detail=None):
    if ok:
        print("PASS  " + name)
    else:
        FAILS.append(name)
        print("FAIL  %s  %s" % (name, detail if detail is not None else ""))


def _golden(name="talking-closeup-S07"):
    chars = json.loads((FIX / "sample-characters.json").read_text("utf-8"))
    spec = json.loads((FIX / (name + ".json")).read_text("utf-8"))
    prompt, sections = PT.assemble_h3(spec, chars)
    return prompt, sections, spec


def _reasons(prompt, **kw):
    v = PT.check(prompt, None, model="minimax-h3/image-to-video", **kw)
    return v["verdict"], " ".join(v.get("reasons") or [])


def test_stillness_and_angle_cheat_are_refused():
    prompt, _sections, _spec = _golden()
    verdict, why = _reasons(prompt + " Minimal head movement, steady locked camera.")
    check("F-PM-5: a stillness sentence is refused",
          verdict == "REFUSE" and "STILLNESS_WORD" in why, (verdict, why[:120]))
    verdict, why = _reasons(prompt + " Cheat the angle to hide the mouth.")
    check("R-2: an angle-cheat phrase is refused",
          verdict == "REFUSE" and ("ANGLE_CHEAT" in why or "STILLNESS_WORD" in why),
          (verdict, why[:120]))
    verdict, _why = _reasons(prompt)
    check("F-PM-5: the clean golden prompt is not refused for stillness",
          verdict != "REFUSE", verdict)


def test_multi_location_is_refused():
    prompt, _sections, _spec = _golden()
    stacked = prompt + (" Meanwhile in the kitchen, cut to the hallway, "
                        "and we see both the upstairs and the living room and the kitchen.")
    verdict, why = _reasons(stacked)
    check("F-PIC-3: three places stacked in one frame are refused",
          verdict == "REFUSE" and "H3_MULTI_LOCATION" in why, (verdict, why[:120]))
    verdict, why = _reasons(prompt)
    check("F-PIC-3: a one-place prompt is not refused for place markers",
          "H3_MULTI_LOCATION" not in why, why[:120])


def test_empty_room_needs_a_full_cast():
    prompt, _sections, _spec = _golden()
    empties = prompt + " Avoid: no congregation in the pews beyond the two named."
    verdict, why = _reasons(empties, cast={"singers": 9})
    check("G-STORY-04: emptying a 9-singer room is refused",
          verdict == "REFUSE" and "H3_EMPTY_ROOM" in why, (verdict, why[:120]))
    verdict, why = _reasons(empties, cast={"singers": 2})
    check("G-STORY-04: the same sentence on a 2-singer cast is not refused",
          "H3_EMPTY_ROOM" not in why, why[:120])


def test_g_motion_01_is_stated_not_just_implied():
    h3 = json.loads((PT.TEMPLATES_DIR / "models" / "minimax-h3.json")
                    .read_text("utf-8"))
    rules = (h3.get("content_rules") or {}).get("no_stillness_sentence") or ""
    check("G-MOTION-01: the H3 template forbids the stillness sentence on a "
          "performance clip", "stillness" in rules.lower() and "body action" in rules.lower(),
          rules[:80])
    anim = json.loads((PT.TEMPLATES_DIR / "animation-rules.json")
                      .read_text("utf-8"))
    check("G-MOTION-01: the animation rules carry the same rule",
          "no_stillness_sentence" in json.dumps(anim))
    for path in sorted((PT.TEMPLATES_DIR / "shot-types").glob("*.json")):
        st = json.loads(path.read_text("utf-8"))
        lead = (st.get("camera_default") or "").lower()
        check("F-PM-5: %s camera default does not lead with a stillness word"
              % path.stem,
              not lead.startswith(("[static shot]", "still", "settle", "hold")),
              lead[:60])


def main():
    test_stillness_and_angle_cheat_are_refused()
    test_multi_location_is_refused()
    test_empty_room_needs_a_full_cast()
    test_g_motion_01_is_stated_not_just_implied()
    if FAILS:
        print("\n%d FAILED" % len(FAILS))
        return 1
    print("\nALL PASS: lane 8 refusal rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
