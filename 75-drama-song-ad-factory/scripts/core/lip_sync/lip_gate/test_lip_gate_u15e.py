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

def _refused(fn, *args, **kw):
    """S-42 / N-08: the lip-sync model is OmniHuman 2.0 and it takes NO prompt.
    The Kling avatar prompt is retired; the assembler and the checker refuse."""
    try:
        fn(*args, **kw)
    except Exception as exc:                            # noqa: BLE001
        text = str(exc)
        assert "LIPSYNC_PROMPT_PRESENT" in text or "LIPSYNC_MODEL_MISMATCH" in text, exc
        return exc
    raise AssertionError("%s still assembles a retired prompt" % (fn,))


def test_a_kling_avatar_prompt_is_retired():
    """kling_prompt and assemble_kling_avatar refuse for every mode and line:
    no lip-sync prompt is ever built (S-42, N-08). The refusal names the
    replacement, OmniHuman 2.0."""
    exc = _refused(L.kling_prompt, "spoken", "woman", "weary", mode="realism")
    assert "omnihuman-2-0" in str(exc), exc
    _refused(L.kling_prompt, "sung", "woman")
    _refused(PT.assemble_kling_avatar, "realism", "woman", "says", "weary", "Her")
    for mode in ("sketch-ink", "golden-realism", "lifelike-3d"):
        _refused(PT.assemble_kling_avatar, mode, "woman", "sings", "calm", "Her")
    for verb in ("says", "sings", "raps"):
        _refused(PT.assemble_kling_avatar, "realism", "woman", verb, "calm", "Her")
    try:
        PT.kling_avatar_model()
    except Exception as exc:                            # noqa: BLE001
        assert "LIPSYNC_MODEL_MISMATCH" in str(exc), exc
    else:
        raise AssertionError("kling_avatar_model still returns a template")


def test_b_the_checker_refuses_any_prompt():
    """Every prompt is refused, the measured control and a 2,501-char one alike;
    the refusal is total, never a sentence or emotion judgement."""
    assert len(TODAYS_SUNG_PROMPT) == 239 and TODAYS_SUNG_PROMPT.count(".") == 4
    long_prompt = "A 3D animated woman sings this line. " + ("word " * 500)
    assert len(long_prompt) > 2500, len(long_prompt)
    for prompt in (TODAYS_SUNG_PROMPT, long_prompt):
        res = PT.check_kling_avatar(prompt, emotion="calm")
        assert res["pass"] is False, res
        joined = " | ".join(res["errors"])
        assert "LIPSYNC_PROMPT_PRESENT" in joined, res
        assert "LIPSYNC_MODEL_MISMATCH" in joined, res
        assert res["verdict"] == "REFUSE", res
        assert res["sentences"] == 0, res
        assert res["cap_status"] == "RETIRED", res


def test_c_golden_rows_are_retired_too():
    """The golden Kling rows can no longer be assembled: the template is gone.
    The fixtures still hold the measured K1-K3 rows (274/289/301 chars, 864
    total) -- the data survived, the template did not."""
    rows = _golden()
    assert [r["id"] for r in rows] == ["K1", "K2", "K3"], rows
    assert [r["chars"] for r in rows] == [274, 289, 301], rows
    assert sum(len(r["prompt"]) for r in rows) == 864, rows
    for row in rows:
        mode, noun, verb, emotion, poss = row["args"]
        _refused(PT.assemble_kling_avatar, mode, noun, verb, emotion, poss, **row["kw"])
        res = PT.check_kling_avatar(row["prompt"], line=row["line"], emotion=emotion)
        assert res["pass"] is False, (row["id"], res)
        assert "LIPSYNC_PROMPT_PRESENT" in " | ".join(res["errors"]), (row["id"], res)


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
