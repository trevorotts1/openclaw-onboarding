#!/usr/bin/env python3
"""U15b: H3 assembler, the 5,000-6,800 band, expand/trim, receipt, refusal.

Fail-first proof for the U15b unit (design 20-OPUS-PROMPT-TEMPLATE-SYSTEM,
sections 3.2/3.3/3.6 and 8):

  (a) the six golden specs assemble inside 5,000-6,800 chars, PASS, carry NO
      square-bracket markers except the one camera group, and repeat no
      sentence (quality_rules: max_duplicate_sentence_chars 40,
      max_repeated_8gram_ratio 0.04);
  (b) a deliberately thin spec is FLAG below the floor, and expand() raises
      H3_THIN_SPEC -- it never pads;
  (c) a prompt over 6,800 is TRIM; over 7,000 is REFUSE H3_OVER_HARD_MAX;
  (d) a 5,200-char assembled prompt passes Skill 74's prompt-budget under
      U15c's owner band (prompt_band_chars);
  (e) a prompt whose sha256 has no matching receipt (or whose receipt says
      REFUSE/TRIM) is refused by kie_dispatch with PROMPT_NOT_TEMPLATED,
      before the ledger or any Skill 74 call;
  (f) the VIDEO path of the style bibles and bible.compile_visual_prompt
      emits no [MOTION] and no square-bracket markers, while the keyframe
      image path (unchanged) still does; assert_compiled accepts a matching
      receipt for a marker-free video prompt;
  (g) hybrid's realism block survives into the emitted prompt with the D19
      RECIPE_REQUIRED_PHRASES (defect 2);
  (h) music_styles' soul-ballad base text ends with a period (defect 4);
  (i) the villain shot type carries the U16 VILLAIN_SHOT_GUIDANCE into the
      assembled action section.

Stdlib only, offline: the Skill 74 check is the adapter CLI in prompt-budget
mode with no key and no network. No spend.

Run: python3 scripts/core/prompt_templates/test_prompt_templates_u15b.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

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

if not hasattr(PT, "assemble_h3"):
    if "pytest" in sys.modules:  # never sys.exit at import -- INTERNALERROR
        import pytest as _pytest
        _pytest.skip("U15b builder missing on this tree (no assemble_h3)",
                     allow_module_level=True)
    print("FAIL: U15b builder missing: %r has no assemble_h3 (base tree)"
          % getattr(PT, "__file__", PT))
    sys.exit(1)

SKILL_ROOT = PT.SKILL_ROOT
FIX = PT.TEMPLATES_DIR / "fixtures" / "h3-specs"
FAILS = []
H3 = "minimax-h3/image-to-video"

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def _specs():
    chars = json.loads((FIX / "sample-characters.json").read_text("utf-8"))
    out = {}
    for p in sorted(FIX.glob("*-S*.json")):
        out[p.stem] = (json.loads(p.read_text("utf-8")), chars)
    return out

def _golden_prompt(spec, chars):
    prompt, sections = PT.assemble_h3(spec, chars)
    return prompt, sections, PT.check(prompt, sections, model=spec["model"])

# ---- (a) the six golden specs ---------------------------------------------
def test_six_golden_specs_pass_in_band():
    band = PT.band(H3)
    check("band of record is floor 5000 / target 5000-6800 / hard max 7000",
          band["floor"] == 5000 and band["target_min"] == 5000
          and band["target_max"] == 6800 and band["hard_max"] == 7000, band)
    n_pass, bracket_bad, dup_bad = 0, [], []
    for name, (spec, chars) in sorted(_specs().items()):
        prompt, sections, v = _golden_prompt(spec, chars)
        ok = v["verdict"] == "PASS" and 5000 <= len(prompt) <= 6800
        n_pass += bool(ok)
        check("golden %s assembles %d chars, PASS" % (name, len(prompt)), ok,
              (len(prompt), v["verdict"], v["reasons"]))
        groups = [g for g in prompt.split("[")[1:]]
        if len(groups) != 1:
            bracket_bad.append((name, len(groups)))
        cut = 40
        sents = [s.strip() for s in
                 __import__("re").split(r"(?<=[.!?])\s+", prompt)
                 if len(s.strip()) >= cut]
        if len(set(sents)) != len(sents):
            dup_bad.append(name)
    check("all six golden specs PASS inside the band", n_pass == 6, n_pass)
    check("golden prompts carry exactly one bracket group (the camera)",
          not bracket_bad, bracket_bad)
    check("golden prompts have no duplicate sentence (>=40 chars)",
          not dup_bad, dup_bad)

# ---- (b) thin spec: FLAG then H3_THIN_SPEC, never padding -----------------
def test_thin_spec_flags_then_refuses():
    spec, chars = _specs()["talking-closeup-S07"]
    thin = copy.deepcopy(spec)
    thin.update({
        "subject": "She sits.",
        "composition": "One light.",
        "lens_light": "Soft light.",
        "motion_physics": "She breathes.",
        "beats": [["0.0-6.0 s", "She sits still."]],
        "intent": "A quiet beat.",
    })
    thin["action"] = {"start": "She sits.", "end": "She sits.",
                      "direction": "Still."}
    prompt, sections = PT.assemble_h3(thin, chars)
    v = PT.check(prompt, sections, model=thin["model"])
    check("thin spec is FLAG (below floor / section-thin), never PASS",
          v["verdict"] == "FLAG"
          and any("H3_BELOW_FLOOR" in r or r.startswith("SECTION_THIN")
                  for r in v["reasons"]),
          (v["verdict"], v["reasons"]))
    try:
        PT.expand(thin, chars, prompt, v)
        check("thin spec refuses H3_THIN_SPEC instead of padding", False,
              "no raise")
    except PT.PromptTemplateError as e:
        check("thin spec refuses H3_THIN_SPEC instead of padding",
              e.code == "H3_THIN_SPEC", str(e))

# ---- (c) TRIM over target, REFUSE over hard max ---------------------------
def test_trim_and_hard_max():
    spec, chars = _specs()["product-book-S09"]
    prompt, sections, v = _golden_prompt(spec, chars)
    over = prompt + " The overhead lamp hums low as dust drifts slowly " \
                    "through its cone of light above the table edge."
    v2 = PT.check(over, sections, model=spec["model"])
    check("a prompt over 6800 is TRIM (not PASS, not REFUSE)",
          v2["verdict"] == "TRIM", (len(over), v2["verdict"], v2["reasons"]))
    huge = over + (" Extra filler words that should never survive. " * 8)
    v3 = PT.check(huge, sections, model=spec["model"])
    check("a prompt over 7000 is REFUSE H3_OVER_HARD_MAX",
          v3["verdict"] == "REFUSE"
          and any("H3_OVER_HARD_MAX" in r for r in v3["reasons"]),
          (len(huge), v3["verdict"], v3["reasons"]))

# ---- (d) the band through Skill 74's prompt-budget (U15c) -----------------
def _adapter_path():
    """The 74-kie-live-adapter CLI. ONB: <repo>/74-kie-live-adapter/scripts/.
    999: <repo>/installer-registration/helpers/74-kie-live-adapter/scripts/."""
    roots = [SKILL_ROOT.parent]
    roots += [p for p in SKILL_ROOT.parents] + list(SKILL_ROOT.parents)
    cands = []
    for r in roots:
        cands.append(r / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py")
        cands.append(r / "installer-registration" / "helpers"
                     / "74-kie-live-adapter" / "scripts" / "kie_live_adapter.py")
    for c in cands:
        if c.is_file():
            return c
    return None

def test_skill74_prompt_budget_honours_the_owner_band():
    adapter = _adapter_path()
    check("the 74-kie-live-adapter CLI resolves from the skill tree",
          adapter is not None, [str(c) for c in (SKILL_ROOT.parent,)] )
    if adapter is None:
        return
    spec, chars = _specs()["struggle-beat-S05"]
    base, _, _ = _golden_prompt(spec, chars)
    prompt = base + " " * max(0, 5200 - len(base))  # 5,200 chars: under the old 5,600 floor
    prompt = prompt[:5200]
    tmp = tempfile.mkdtemp(prefix="u15b-band-")
    pf = os.path.join(tmp, "prompt.txt")
    with open(pf, "w", encoding="utf-8") as f:
        f.write(prompt)
    rc = subprocess.run(
        [sys.executable, str(adapter), "prompt-budget", "--model", H3,
         "--check", "--prompt-file", pf, "--mode", "active", "--json"],
        capture_output=True, text=True)
    out = rc.stdout or ""
    check("a 5,200-char H3 prompt passes skill 74 (exit 0, band floor 5000)",
          rc.returncode == 0 and '"status": "OK"' in out
          and '"floor": 5000' in out and '"target_max": 6800' in out,
          (rc.returncode, out[-240:], (rc.stderr or "")[-160:]))

# ---- (e) PROMPT_NOT_TEMPLATED at dispatch ---------------------------------
def test_no_receipt_refuses_before_any_spend():
    import kie_dispatch as D
    good = "prompt text"
    sha = hashlib.sha256(good.encode("utf-8")).hexdigest()
    r = D.prompt_templated_refusal(
        H3, {"prompt_receipt": {"prompt_sha256": sha,
                                "check": {"verdict": "PASS"}}}, good)
    check("a matching PASS receipt dispatches", r is None, r)
    r2 = D.prompt_templated_refusal(H3, {}, good)
    check("no receipt -> PROMPT_NOT_TEMPLATED",
          r2 and r2["reason_code"] == "PROMPT_NOT_TEMPLATED", r2)
    r3 = D.prompt_templated_refusal(H3, {"prompt_receipt": {
        "prompt_sha256": sha, "check": {"verdict": "TRIM"}}}, good)
    check("a TRIM receipt -> PROMPT_NOT_TEMPLATED",
          r3 and r3["reason_code"] == "PROMPT_NOT_TEMPLATED", r3)
    r4 = D.prompt_templated_refusal(
        H3, {"prompt_receipt": {"prompt_sha256": "0" * 64}}, good)
    check("a receipt for different bytes -> PROMPT_NOT_TEMPLATED",
          r4 and r4["reason_code"] == "PROMPT_NOT_TEMPLATED", r4)
    r5 = D.prompt_templated_refusal("kling/ai-avatar-standard", {}, good)
    check("a non-H3 model is untouched by this gate", r5 is None, r5)

def test_receipt_shape_from_receipt_fn():
    spec, chars = _specs()["end-card-S14"]
    prompt, sections, v = _golden_prompt(spec, chars)
    rec = PT.receipt(spec, prompt, sections, v)
    check("receipt carries sha256 + template version + section map",
          rec["prompt_sha256"] == hashlib.sha256(
              prompt.encode("utf-8")).hexdigest()
          and rec["template_version"] == PT.load("manifest")["template_version"]
          and rec["sections"] and rec["chars"] == len(prompt), rec)
    check("the receipt passes has_receipt()", PT.has_receipt(
        rec["prompt_sha256"], [rec]) is True)

# ---- (f) video path: no markers, receipt proves compiledness --------------
_C3_SHOT = {"shot_id": "s1", "base_prompt": "wake-up close-up"}

def test_video_paths_carry_no_brackets_and_no_generic_motion():
    import style_bibles.hybrid.hybrid_bible as HB
    import style_bibles.canvas_to_life.canvas_to_life_bible as C2L
    import style_bibles.canvas_to_3d.canvas_3d_bible as C3
    ident = {"character": "K", "face": "round", "hair": "black bob",
             "glasses": "none", "accessories": "watch", "wardrobe": "jeans"}
    lock = C2L.identity_lock("K", ["ref-1"], ["brave"])
    outs = {
        "hybrid sketch": HB.compile_prompt(_C3_SHOT, HB.MODE_SKETCH, video=True),
        "canvas_to_life painted": C2L.compile_prompt(
            _C3_SHOT, C2L.MODE_PAINTED, lock, video=True),
        "canvas_to_life golden": C2L.compile_prompt(
            _C3_SHOT, C2L.MODE_GOLDEN, lock, video=True),
        "canvas_to_3d": C3.compile_prompt(_C3_SHOT, C3.MODE_3D, ident,
                                          video=True),
    }
    for name, out in outs.items():
        p = out["prompt"]
        check("%s: video prompt carries no square brackets" % name,
              "[" not in p and "]" not in p, p[:160])
        check("%s: video prompt drops the generic [MOTION] line" % name,
              "The subject moves naturally through the frame" not in p,
              p[-160:])
    img = HB.compile_prompt(_C3_SHOT, HB.MODE_SKETCH)
    check("the keyframe image path keeps the compiled mark and [MOTION]",
          "[compiled:" in img["prompt"] and "[MOTION]" in img["prompt"])

def test_assert_compiled_accepts_a_matching_receipt():
    import product_style_bible.bible as B
    import style_bibles.hybrid.hybrid_bible as HB
    p = HB.compile_prompt(_C3_SHOT, HB.MODE_SKETCH, video=True)["prompt"]
    rec = {"prompt_sha256": hashlib.sha256(p.encode("utf-8")).hexdigest()}
    check("marker-free video prompt passes with its receipt",
          B.assert_compiled(p, rec) is True)
    check("marker-free video prompt fails without a receipt",
          B.assert_compiled(p) is False)
    check("a receipt for different bytes never passes",
          B.assert_compiled(p, {"prompt_sha256": "0" * 64}) is False)
    check("the image marker path is unchanged",
          B.assert_compiled("[compiled:style=x model=m aspect=9:16]\n"
                            "[STYLE]a[/STYLE]") is True)

def test_bible_compile_visual_prompt_video_flag():
    import product_style_bible.bible as B
    style = {"schema_version": "1.0.0", "style_id": "s1", "aspect_ratio": "9:16",
             "aesthetic": "a", "rendering_style": "r", "camera_language": "c",
             "lens_tendencies": "l", "lighting_doctrine": "d",
             "contrast_architecture": "ca", "environment_texture": "e",
             "grain_sharpness": "g",
             "color_palette": ["p"], "visual_continuity_constraints": ["v"],
             "banned_visual_cliches": ["b"]}
    product = {"product_id": "p1", "schema_version": "1.0.0",
               "packaging_reference": "x", "logo_mark": "x", "color": "x",
               "geometry": "x", "label_placement": "x", "cap_lid": "x",
               "prohibited_invented_text": ["bad"],
               "required_product_reference_images": ["img-1"],
               "approved_texts": []}
    chars = [{"character_id": "c1", "approved_reference_asset_ids": ["ref-1"]}]
    shot = {"shot_id": "s1", "base_prompt": "a kitchen at night",
            "character_ids": ["c1"]}
    v = B.compile_visual_prompt(style, chars, product, shot, video=True)
    check("bible video prompt carries no square brackets",
          "[" not in v["prompt"] and "]" not in v["prompt"], v["prompt"][:160])
    i = B.compile_visual_prompt(style, chars, product, shot)
    check("bible image prompt keeps the compiled marker path",
          "[compiled:style=" in i["prompt"] and "[MOTION]" in i["prompt"])

# ---- (g) realism recipe survives into the hybrid video prompt -------------
def test_hybrid_video_prompt_carries_the_d19_phrases():
    import style_bibles.hybrid.hybrid_bible as HB
    out = HB.compile_prompt({"shot_id": "s1", "base_prompt": "the elevator"},
                            HB.MODE_REALISM, video=True)
    low = out["prompt"].lower()
    missing = [p for p in HB.RECIPE_REQUIRED_PHRASES if p.lower() not in low]
    check("hybrid realism video prompt carries all five RECIPE_REQUIRED_PHRASES",
          len(HB.RECIPE_REQUIRED_PHRASES) == 5 and not missing, missing)

# ---- (h) music_styles: the base text ends its sentence --------------------
def test_music_style_text_ends_with_a_period():
    import music_styles as MS
    p = MS.STYLES["soul-ballad"]["suno_style_prompt"]
    check("soul-ballad style text ends its base sentence with a period",
          "no distortion." in p, p[-60:])
    check("no style text ends a comma-run without a full stop",
          not any(s["suno_style_prompt"].rstrip().endswith("distortion")
                  for s in MS.STYLES.values()))

# ---- (i) the villain shot type carries the U16 guidance -------------------
def test_villain_shot_type_carries_u16_guidance():
    import product_style_bible.bible as B
    st = PT.load("shot_type", "villain")
    check("the villain shot type file exists and names the U16 carry-in",
          st.get("shot_type") == "villain" and "u16_carry_in" in st, st.keys())
    spec, chars = _specs()["struggle-beat-S05"]
    vspec = copy.deepcopy(spec)
    vspec["shot_type"] = "villain"
    prompt, sections = PT.assemble_h3(vspec, chars)
    check("the assembled villain prompt carries VILLAIN_SHOT_GUIDANCE",
          B.VILLAIN_SHOT_GUIDANCE in prompt, prompt[:200])
    check("the villain prompt still carries no in-prompt compile markers",
          "[compiled:" not in prompt and "[STYLE]" not in prompt)
    v = PT.check(prompt, sections, model=vspec["model"])
    check("the villain prompt stays inside the band or flags honestly",
          v["verdict"] in ("PASS", "FLAG", "TRIM"), (v["verdict"], len(prompt)))

# ---- (j) shot_planner.prompt_spec_for writes FACTS, never prose -----------
def test_prompt_spec_for_writes_facts():
    import shot_planner as SP
    shot = {"shot_id": "s1", "song_start": 3.0, "song_end": 9.0,
            "story_stage": "frozen",
            "visual_objective": "Renee hears her own doubt in the sung line.",
            "camera_direction": "Her gaze travels upward toward screen-left.",
            "motion_physics": "Her breath lifts the cardigan every four seconds.",
            "beats": [["0.0-3.0 s", "Still, eyes down."],
                      ["3.0-6.0 s", "Her eyes lift past the lens."]],
            "continuity_constraints": ["same cardigan"],
            "negative_constraints": ["no smiling"]}
    contract = {"lyric_text": "I am still here",
                "viewer_understanding": "She decides not to cry.",
                "character_action": "She lifts her eyes and exhales.",
                "visible_emotion": "held-back grief",
                "change_from_prior": "she stops hiding",
                "treatment": "literal-repeat", "necessity": "the turn"}
    look_plan = {"look": "lifelike-3d", "mode": "lifelike-3d",
                 "shot_type": "talking-closeup",
                 "camera": {"command": "[Push in]", "plain": "very slowly"},
                 "lens_light": "85 mm equivalent, warm key from screen-right."}
    spec = SP.prompt_spec_for(shot, contract, look_plan)
    check("prompt_spec_for stores the spec on the shot", shot.get("prompt_spec") is spec)
    check("the spec carries subject, composition, action and camera",
          bool(spec["subject"]) and bool(spec["composition"])
          and spec["action"]["start"] and spec["action"]["end"]
          and spec["camera"]["command"] == "[Push in]", spec)
    check("a factless contract refuses PROMPT_SPEC_INCOMPLETE",
          _refuses_spec(SP, dict(contract, visible_emotion="")))
    check("an empty beat list refuses PROMPT_SPEC_INCOMPLETE",
          _refuses_spec(SP, contract, beats=[]))

def _refuses_spec(SP, contract, beats=None):
    shot = {"shot_id": "s1", "song_start": 0.0, "song_end": 6.0,
            "visual_objective": "objective", "camera_direction": "direction",
            "motion_physics": "physics",
            "beats": beats if beats is not None
            else [["0-3 s", "a"], ["3-6 s", "b"]]}
    look_plan = {"look": "lifelike-3d", "mode": "lifelike-3d",
                 "camera": {"command": "[Static shot]", "plain": "still"},
                 "lens_light": "soft"}
    try:
        SP.prompt_spec_for(shot, contract, look_plan)
        return False
    except SP.PlanError as e:
        return e.code == "PROMPT_SPEC_INCOMPLETE"

def main():
    test_six_golden_specs_pass_in_band()
    test_thin_spec_flags_then_refuses()
    test_trim_and_hard_max()
    test_skill74_prompt_budget_honours_the_owner_band()
    test_no_receipt_refuses_before_any_spend()
    test_receipt_shape_from_receipt_fn()
    test_video_paths_carry_no_brackets_and_no_generic_motion()
    test_assert_compiled_accepts_a_matching_receipt()
    test_bible_compile_visual_prompt_video_flag()
    test_hybrid_video_prompt_carries_the_d19_phrases()
    test_music_style_text_ends_with_a_period()
    test_villain_shot_type_carries_u16_guidance()
    test_prompt_spec_for_writes_facts()
    print()
    if FAILS:
        print("FAILED: %d" % len(FAILS))
        for f in FAILS:
            print("  - %s" % f)
        return 1
    print("ALL PASS: U15b assembler, band, expand/trim, receipt, refusal.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
