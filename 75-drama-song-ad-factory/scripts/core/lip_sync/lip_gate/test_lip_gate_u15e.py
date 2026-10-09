#!/usr/bin/env python3
"""U15e: Kling avatar template (design 20-OPUS-PROMPT-TEMPLATE-SYSTEM 2.3/5.1). $0.

The avatar prompt is ASSEMBLED from the look's mode (the `who` descriptor and
the wording), never from a hard-coded "3D animated". Fail-first on the base
tree, where lip_gate._PROMPT still hard-codes "3D animated" and there is no
prompt_templates.assemble_kling_avatar / check_kling_avatar at all:

  (a) a Canvas to Life realism close-up gets "photoreal", not "3D animated";
  (b) a sketch-ink or golden-realism mode is REFUSED (LIPSYNC_NOT_ALLOWED_FOR_MODE);
  (c) today's 4-sentence, two-emotion prompt FAILS the checker;
  (d) a 2,501-char prompt is REFUSED by the checker and by the assembler;
  (e) the three golden rows in fixtures/kling-rows.json assemble byte-identically
      and pass the checker;
  (f) image_gate.closeup_prompt takes mode.keyframe_clause (the realism close-up
      says "photoreal", never "same 3D character").

Stdlib only. Run: python3 scripts/core/lip_sync/lip_gate/test_lip_gate_u15e.py
Exit 0 = all pass. pytest-collectable (test_* functions, plain asserts).
"""
from __future__ import annotations

import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import image_gate as G                                  # noqa: E402
import lip_gate as L                                    # noqa: E402
import prompt_templates as PT                           # noqa: E402

SKILL = os.path.dirname(os.path.dirname(CORE))          # .../<skill>
FIXTURES = os.path.join(SKILL, "references", "prompt-templates",
                        "fixtures", "kling-rows.json")

#: The exact string today's lip_gate._PROMPT.format(...) produced (the control):
#: 239 chars, 4 sentences, two emotion words.
TODAYS_SUNG_PROMPT = (
    "A 3D animated woman sings this line to the camera with a calm, earnest "
    "expression. Minimal head movement, steady locked camera, natural blinks, "
    "relaxed shoulders. Her whole face and mouth stay fully visible. No text, "
    "captions or watermark.")

def _golden():
    with open(FIXTURES, encoding="utf-8") as f:
        return json.load(f)["examples"]

def test_lip_gate_delegates_and_removes_the_hard_coded_look():
    """The module no longer carries a hard-coded 'A 3D animated' template."""
    assert not hasattr(L, "_PROMPT"), (
        "lip_gate._PROMPT still hard-codes the look for every look (design 5.1)")
    assert hasattr(PT, "assemble_kling_avatar"), (
        "prompt_templates.assemble_kling_avatar missing (design 2.2)")

def test_a_canvas_to_life_realism_closeup_is_photoreal():
    """(a) Canvas to Life realism close-up -> 'photoreal', not '3D animated'."""
    p = L.kling_prompt("says" if False else "spoken", "woman", "weary",
                       mode="realism")
    assert p.startswith("A photoreal woman "), p
    assert "3D animated" not in p, p
    d = PT.assemble_kling_avatar("realism", "woman", "says", "weary", "Her")
    assert d == p, (d, p)

def test_b_sketch_and_golden_modes_are_refused():
    """(b) sketch-ink and golden-realism may not be lip-synced."""
    for mode in ("sketch-ink", "golden-realism"):
        for fn, args in ((L.kling_prompt, ("sung", "woman", "calm")),
                         (PT.assemble_kling_avatar,
                          (mode, "woman", "sings", "calm", "Her"))):
            try:
                if fn is L.kling_prompt:
                    fn(*args, mode=mode)
                else:
                    fn(*args)
            except Exception as exc:                    # noqa: BLE001
                assert "LIPSYNC_NOT_ALLOWED_FOR_MODE" in str(exc), (mode, exc)
            else:
                raise AssertionError("%s: mode %s was not refused" % (fn, mode))

def test_c_todays_four_sentence_two_emotion_prompt_fails_the_checker():
    """(c) the fail-first control: today's prompt is 4 sentences, 2 emotions."""
    n, s = len(TODAYS_SUNG_PROMPT), TODAYS_SUNG_PROMPT.count(".")
    assert n == 239 and s == 4, (n, s)               # the measured control
    res = PT.check_kling_avatar(TODAYS_SUNG_PROMPT, emotion="calm, earnest")
    assert res["pass"] is False, res
    joined = " | ".join(res["errors"])
    assert "SENTENCES" in joined, res
    assert "MORE_THAN_ONE_EMOTION" in joined, res

def test_d_a_2501_char_prompt_is_refused():
    """(d) over the UNVERIFIED 2,500 hard cap -> refused, never truncated."""
    long_prompt = "A 3D animated woman sings this line. " + ("word " * 500)
    assert len(long_prompt) > 2500, len(long_prompt)
    res = PT.check_kling_avatar(long_prompt, emotion="calm")
    assert res["pass"] is False and "OVER_HARD_MAX" in " | ".join(res["errors"]), res
    try:
        PT.assemble_kling_avatar("lifelike-3d", "w" * 2501, "sings", "calm", "Her")
    except Exception as exc:                            # noqa: BLE001
        assert "KLING_AVATAR_OVER_HARD_MAX" in str(exc), exc
    else:
        raise AssertionError("assembler did not refuse a 2,501-char prompt")

def test_e_golden_rows_assemble_byte_identically():
    """(e) K1-K3 from fixtures/kling-rows.json, 274/289/301 chars, all pass."""
    for row in _golden():
        mode, noun, verb, emotion, poss = row["args"]
        kw = row["kw"]
        p = PT.assemble_kling_avatar(mode, noun, verb, emotion, poss, **kw)
        assert p == row["prompt"], (row["id"], p)
        assert len(p) == row["chars"], (row["id"], len(p))
        res = PT.check_kling_avatar(p, line=row["line"], emotion=emotion)
        assert res["pass"], (row["id"], res)
        assert res["sentences"] == 3, (row["id"], res)
    assert sum(len(r["prompt"]) for r in _golden()) == 864

def test_f_closeup_prompt_takes_the_mode_keyframe_clause():
    """(f) the realism close-up carries the mode clause, not 'same 3D character'."""
    p = G.closeup_prompt("A tired mother in her thirties, curly brown hair",
                         mode="realism")
    assert "same person as a photoreal cinematic still" in p, p
    assert "same 3D character" not in p, p
    q = G.closeup_prompt("A tired mother in her thirties, curly brown hair",
                         mode="painted-2d")
    assert "hand-painted 2D style" in q and "same 3D character" not in q, q
    # unchanged for callers that pass no mode (test_image_gate.py)
    r = G.closeup_prompt("A tired mother in her thirties, curly brown hair",
                         "soft 3D render", "ref set image 1")
    assert "same 3D character" in r and "soft 3D render" in r, r

def main():
    fails, total = [], 0
    names = sorted(n for n in globals() if n.startswith("test_"))
    for name in names:
        total += 1
        try:
            globals()[name]()
            print("ok  ", name)
        except Exception:                               # noqa: BLE001
            fails.append(name)
            print("FAIL", name)
            traceback.print_exc()
    if fails:
        print("\nFAILED: %d of %d" % (len(fails), total))
        return 1
    print("\nALL PASS (%d)" % total)
    return 0

if __name__ == "__main__":
    sys.exit(main())
