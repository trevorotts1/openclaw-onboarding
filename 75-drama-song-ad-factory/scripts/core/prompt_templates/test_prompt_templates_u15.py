#!/usr/bin/env python3
"""U15a: template data layer + loader + caps reader. Stdlib only, no network, no spend.

Proves, fail-first (today there is no module):
  (a) every look x mode x shot type resolves through load();
  (b) caps("minimax-h3/image-to-video","prompt") == 7000 VERIFIED, read from the
      67 catalog, and caps("kling/ai-avatar-standard","prompt") == 2500
      UNVERIFIED, from the manifest (no catalog carries that row);
  (c) each mode block carries its record's key phrases; for realism the five
      RECIPE_REQUIRED_PHRASES from references/style-bibles/realism-cinematic.md.

Run: python3 scripts/core/prompt_templates/test_prompt_templates_u15.py
Exit 0 = all pass, 1 = failures. pytest-collectable (test_* functions, plain asserts).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Judge the SOURCE on disk, never a stale __pycache__ (U6 test pattern).
_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import prompt_templates as PT  # noqa: E402

# Fail first, and say why: on the base tree the module does not exist yet, so
# Python resolves the name to this directory (a namespace package) with none of
# the loader's names. Refuse here rather than at the first assertion.
if not hasattr(PT, "LOOKS"):
    if "pytest" in sys.modules:  # never sys.exit at import -- INTERNALERROR
        import pytest as _pytest
        _pytest.skip("U15a module missing on this tree (no LOOKS); "
                     "run `python3 test_prompt_templates_u15.py` there",
                     allow_module_level=True)
    print("FAIL: U15a module missing: %r has no LOOKS (base tree has no "
          "prompt_templates.py)" % getattr(PT, "__file__", PT))
    sys.exit(1)

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

# ---- (a) every look x mode x shot type resolves ---------------------------
def test_every_layer_resolves():
    looks = {}
    for look_id in PT.LOOKS:
        looks[look_id] = PT.load("look", look_id)
    check("all five look files load", sorted(looks) == sorted(PT.LOOKS), sorted(looks))
    modes = {}
    for mode_id in PT.MODES:
        modes[mode_id] = PT.load("mode", mode_id)
    check("all five mode files load", sorted(modes) == sorted(PT.MODES), sorted(modes))
    shots = {}
    for shot_id in PT.SHOT_TYPES:
        shots[shot_id] = PT.load("shot_type", shot_id)
    check("all six shot-type files load", sorted(shots) == sorted(PT.SHOT_TYPES), sorted(shots))
    # every look's modes and beat map point at a real mode file
    pairs = set()
    for look_id, look in sorted(looks.items()):
        for mode_id in look.get("modes") or []:
            pairs.add((look_id, mode_id))
        for beat, mode_id in (look.get("beat_mode") or {}).items():
            pairs.add((look_id, mode_id))
    unknown = sorted({m for _, m in pairs if m not in modes})
    check("every look mode and beat map resolves to a mode file", not unknown, unknown)
    check("every look x mode x shot type resolves",
          bool(pairs) and len(looks) == 5 and len(modes) == 5 and len(shots) == 6
          and len(pairs) >= 8, (len(looks), len(modes), len(shots), len(pairs)))
    # the other three layers load too
    check("manifest, length classes and all three music styles load",
          bool(PT.load("manifest")) and bool(PT.load("length_classes"))
          and all(PT.load("music", s) for s in ("soul-ballad", "rnb-flow", "soul-rise")))
    check("length classes carry the six card lengths",
          sorted(PT.load("length_classes").get("classes") or {})
          == ["120", "180", "300", "60", "600", "90"],
          sorted(PT.load("length_classes").get("classes") or {}))

def test_unknown_layer_and_missing_file_refuse():
    try:
        PT.load("nope")
        check("unknown layer refuses", False, "no error")
    except PT.PromptTemplateError as e:
        check("unknown layer refuses", e.code == "PROMPT_TEMPLATE_UNKNOWN_LAYER", e)
    try:
        PT.load("mode", "does-not-exist")
        check("missing mode file refuses", False, "no error")
    except PT.PromptTemplateError as e:
        check("missing mode file refuses", e.code == "PROMPT_TEMPLATE_UNREADABLE", e)
    check("required=False returns None instead of raising",
          PT.load("mode", "does-not-exist", required=False) is None)

# ---- (b) caps: catalogs first, manifest second ----------------------------
def test_caps_from_the_67_catalog():
    row = PT.caps("minimax-h3/image-to-video", "prompt")
    check("H3 image-to-video prompt cap is 7000", row["cap"] == 7000, row)
    check("H3 cap status is VERIFIED", row["status"] == "VERIFIED", row)
    check("H3 cap source names the 67 catalog, not the manifest",
          "67-kie-video" in row["source"] and "manifest" not in row["source"], row["source"])

def test_caps_from_the_manifest_for_the_avatar():
    row = PT.caps("kling/ai-avatar-standard", "prompt")
    check("avatar prompt cap is 2500", row["cap"] == 2500, row)
    check("avatar cap status is UNVERIFIED", row["status"] == "UNVERIFIED", row)
    check("avatar cap source names the manifest (no catalog row carries it)",
          "manifest" in row["source"], row["source"])

def test_manifest_is_the_fallback_not_a_second_catalog():
    # every other H3 shape reads the catalog too, so no second table can drift
    for model in ("minimax-h3/text-to-video", "minimax-h3/reference-to-video"):
        row = PT.caps(model, "prompt")
        check("cap for %s comes from the catalog" % model,
              row["cap"] == 7000 and "67-kie-video" in row["source"], row)
    row = PT.caps("kling/v2-5-turbo-image-to-video-pro", "prompt")
    check("a catalog-verified Kling row reads its own cap",
          row["cap"] == 2500 and row["status"] == "VERIFIED", row)
    suno = PT.caps("suno-generate", "lyrics")
    check("a Suno field reads the 68 catalog", suno["cap"] == 5000
          and "68-kie-audio" in suno["source"], suno)
    try:
        PT.caps("no-such-model", "prompt")
        check("an unknown model refuses", False, "no error")
    except PT.PromptTemplateError as e:
        check("an unknown model refuses", e.code == "PROMPT_TEMPLATE_NO_CAP", e)

def test_caps_agree_with_u6_prompt_limits():
    import prompt_limits as PL
    video, audio = PT.catalog_path("video"), PT.catalog_path("audio")
    check("the 67 and 68 catalogs both resolve in this tree",
          video is not None and audio is not None and video.is_file() and audio.is_file(),
          (str(video), str(audio)))
    check("U6 is the one catalog reader (no second caps table)",
          PL.video_caps("minimax-h3/image-to-video", models_path=video)["prompt"] == 7000
          and PL.OVERRIDES["kling/ai-avatar-standard"]["cap"] == 2500)

# ---- (c) each mode block carries its record's key phrases -----------------
RECORD_PHRASES = {
    "lifelike-3d": ["clearly animated", "lifelike faces", "believable weight",
                    "never photoreal live-action"],
    "painted-2d": ["hand-painted 2D", "contour lines", "cel shading",
                   "brush texture", "painterly", "no photoreal"],
    "sketch-ink": ["black-and-white", "ink line art", "hand-hatched",
                   "no colour", "no 3D render"],
    "realism": ["photoreal cinematic live-action", "natural skin texture",
                "shallow depth of field", "35mm film grade", "no cartoon"],
    "golden-realism": ["photoreal cinematic live-action", "natural skin texture",
                       "shallow depth of field", "35mm film grade", "no cartoon",
                       "finale grade"],
}

def _mode_text(mode_id):
    """A mode's full block: its own h3_block plus the block it extends."""
    block = PT.load("mode", mode_id)
    parts = [block.get("label"), block.get("h3_block"), block.get("h3_block_suffix"),
             block.get("kling_block")]
    if block.get("extends"):
        base = PT.load("mode", block["extends"])
        parts += [base.get("h3_block"), base.get("h3_block_suffix")]
    return " ".join(str(p or "") for p in parts)

def test_mode_blocks_carry_their_record_phrases():
    for mode_id, phrases in sorted(RECORD_PHRASES.items()):
        lower = _mode_text(mode_id).lower()
        missing = [p for p in phrases if p.lower() not in lower]
        check("mode %s carries its record's key phrases" % mode_id, not missing, missing)

def test_realism_block_carries_the_five_recipe_phrases():
    """The design 2.4 rule: the realism block carries RECIPE_REQUIRED_PHRASES."""
    import style_bibles.hybrid.hybrid_bible as HB
    block = PT.load("mode", "realism")["h3_block"]
    lower = block.lower()
    missing = [p for p in HB.RECIPE_REQUIRED_PHRASES if p.lower() not in lower]
    check("realism h3_block carries all five RECIPE_REQUIRED_PHRASES",
          len(HB.RECIPE_REQUIRED_PHRASES) == 5 and not missing, missing)

def test_look_text_exists_once():
    """One copy of every look text: each mode's h3_block appears in exactly one file."""
    blocks = {}
    for mode_id in PT.MODES:
        block = PT.load("mode", mode_id).get("h3_block")
        if block:
            blocks[mode_id] = block
    check("the four modes with an h3_block have distinct text",
          len(blocks) == 4 and len(set(blocks.values())) == 4, sorted(blocks))

def main():
    test_every_layer_resolves()
    test_unknown_layer_and_missing_file_refuse()
    test_caps_from_the_67_catalog()
    test_caps_from_the_manifest_for_the_avatar()
    test_manifest_is_the_fallback_not_a_second_catalog()
    test_caps_agree_with_u6_prompt_limits()
    test_mode_blocks_carry_their_record_phrases()
    test_realism_block_carries_the_five_recipe_phrases()
    test_look_text_exists_once()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
