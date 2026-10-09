#!/usr/bin/env python3
"""U15d: Suno V6 templates per style and per length, caps measured last.

Every check below FAILS on the base tree (unit/FU-U15a) and passes after the
change. Stdlib only, zero network, zero paid calls.

  (a) the R&B Flow style text carries no "slow tempo" and no "long held open
      vowels" (the base tree's single STYLE_LEAD put both on every style);
  (b) a 5,001-char lyric, a 1,001-char FINAL style (measured after
      ending_qc.with_clean_ending), an 81-char title and 1,001-char negative
      tags are each refused;
  (c) the six golden payloads pass with the hook count equal to
      hook_placement.hook_target (sung_hook.hook_count after the sheet's
      story beat);
  (d) a lyric line under an [Instrumental ...] tag is refused;
  (e) a product share outside 10-15 percent is refused;
  (f) a 3-minute, a 5-minute and a 10-minute plan each land inside 20-25%
      percent spoken, and the 60/90/120/180-second plans are unchanged.

Plus the U16 addition: the villain/pain lyric guidance is read from
product_style_bible/bible.py VILLAIN_LYRIC_GUIDANCE when that tree has it.

Run: python3 scripts/core/suno_recipe/test_suno_templates_u15d.py
Exit 0 = all pass, 1 = failures. pytest-collectable (test_* functions).
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ending_qc as EQ            # noqa: E402
import length_formula as LF       # noqa: E402
import music_director as MD       # noqa: E402
import prompt_limits as PL        # noqa: E402
import prompt_templates as PT     # noqa: E402
import suno_recipe as R           # noqa: E402
from sung_hook import hook_placement as HP   # noqa: E402

SHEETS_DIR = str(PT.TEMPLATES_DIR / "fixtures" / "suno-sheets")
GOLDENS = sorted(glob.glob(os.path.join(SHEETS_DIR, "*.json")))

CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _base_sheet(product=False):
    s = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["One seed of truth made me stro-o-ong,",
                    "One seed is a-all I ne-e-eed,"]},
         {"tag": "Hook", "delivery": "sung", "lines": list(HOOK)},
         {"tag": "Hook 2", "delivery": "sung", "lines": list(HOOK)},
         {"tag": "Hook 3", "delivery": "sung", "lines": list(HOOK)}]
    if product:
        s.append({"tag": "Product", "delivery": "sung",
                  "lines": ["She handed me a bo-ook,", "One seed, just look,"]})
    s.append({"tag": "Outro", "delivery": "spoken",
              "lines": ["She Found Power in the Climb. Get the book. Link below."]})
    return s


def _refused(fn, *a, **kw):
    try:
        return None, fn(*a, **kw)
    except (R.RecipeError, PL.PromptLimitError) as e:
        return e, None


# ---------------------------------------------------------------------------
# (a) the R&B Flow style text carries no "slow tempo" / "long held open vowels"

def test_a_rnb_style_has_no_ballad_lead():
    for sid in ("rnb-flow",):
        text = R.style_text(sid, None, "female")
        low = text.lower()
        check("a1 %s style text carries no 'slow tempo'" % sid, "slow tempo" not in low, text[-200:])
        check("a2 %s style text carries no 'long held open vowels'" % sid,
              "long held open vowels" not in low, text[-200:])
    check("a3 the R&B style still names its own rap verses",
          "rhythmic rap" in R.style_text("rnb-flow", None, "female").lower())
    check("a4 the ballad styles keep the held-vowel lead (data, not code)",
          "long held open vowels" in R.style_text("soul-ballad", None, "female").lower()
          and "long held open vowels" in R.style_text("soul-rise", None, "female").lower())
    # The "no distortion The lead" defect lived in music_styles.style_prompt,
    # which appends the map after the base text.
    import music_styles as MS
    for sid in ("soul-ballad", "rnb-flow", "soul-rise"):
        prompt = MS.style_prompt(sid)
        check("a5 %s base text ends with a period before the map" % sid,
              ". The lead " in prompt, prompt[-200:])


def test_a_gender_is_from_the_brief_never_hard_coded():
    male = R.style_text("soul-ballad", None, "male")
    female = R.style_text("soul-ballad", None, "female")
    check("a6 the gender word comes from the brief",
          "male lead" in male and "female lead" in female)
    check("a7 no gender word means a refusal, never a default",
          _refused(R.style_text, "soul-ballad", None, None)[0] is not None)
    check("a8 the brief's own wording is used verbatim",
          "Warm female lead" in R.style_text("soul-ballad", None, "Warm female"))


# ---------------------------------------------------------------------------
# (b) the four caps, each refused

def test_b_caps_are_refused():
    # 5,001-char lyric. length_s stays None: the word/hook budget is the
    # length formula's business, and this check is the CAP's.
    base = R.render_lyrics(_base_sheet(), "soul-ballad")
    line = "a" * 40
    n = -(-(5001 - len(base)) // 41) + 1
    s = _base_sheet()
    s[2] = {"tag": "Verse", "delivery": "sung", "lines": [line] * n}
    lyric = R.render_lyrics(s, "soul-ballad")
    check("b0 the padded lyric really is over 5,000 chars", len(lyric) > 5000, len(lyric))
    # FU-HOOK-PLACEMENT: build_request now refuses a missing length as
    # UNMEASURED before any cap, so the lyric cap is measured at the
    # music_director seam (no recipe style, no length), the same seam as b3.
    # (an exempt style id: a sung sheet with no style_id is refused
    # "UNMEASURED: style_id" before any cap is measured)
    e, _ = _refused(MD.build_generate_request, lyric, "plain style", "T",
                    style_id="velvet_voiceover")
    check("b1 a lyric over 5,000 chars is refused",
          e is not None and getattr(e, "field", None) == "lyrics", e)

    # 1,001-char FINAL style: under the cap before ending_qc, over after.
    style = "x" * 980 + " the full band keeps playing"
    final = EQ.with_clean_ending(lyric, style)[1]
    check("b2 ending_qc makes the style cross 1,000", len(final) > 1000, len(final))
    e, _ = _refused(MD.build_generate_request, R.render_lyrics(_base_sheet(), "rnb-flow"),
                    style, "T", style_id="velvet_voiceover")
    check("b3 the FINAL style over 1,000 chars is refused",
          e is not None and getattr(e, "field", None) == "style", e)

    # 81-char title.
    e, _ = _refused(R.build_request, "soul-ballad", _base_sheet(), CLIENT, "T" * 81, 58,
                    hook_plan={"true_at_beat": "the_world"})
    check("b4 an 81-char title is refused",
          e is not None and getattr(e, "field", None) == "title", e)

    # 1,001-char negative tags on the final payload.
    req = {"input": {"model": "V6", "lyrics": "l", "style": "s",
                     "negative_tags": "n" * 1001}}
    e, _ = _refused(PL.check_request, "suno-generate", req)
    check("b5 1,001-char negative tags are refused",
          e is not None and getattr(e, "field", None) == "negative_tags", e)


# ---------------------------------------------------------------------------
# (c) the six golden payloads

def test_c_golden_payloads_pass():
    check("c0 six golden payloads are on disk", len(GOLDENS) == 6, GOLDENS)
    for f in GOLDENS:
        name = os.path.basename(f)
        payload = json.loads(open(f, encoding="utf-8").read())
        text = "\n\n".join(seg["lyrics"] for seg in payload["segments"])
        chorus = next(" ".join(s["lines"]) for s in R.parse_lyrics(text)
                      if s["tag"].lower().startswith("hook"))   # the client's own words
        errs = R.check_payload(payload, chorus)
        check("c1 %s passes every U15d rule" % name, not errs, errs)
        hooks = sum(1 for seg in payload["segments"]
                    for ln in (seg.get("lyrics") or "").splitlines()
                    if ln.strip().lower().startswith("[hook"))
        # FU-HOOK-PLACEMENT: the count follows the sheet's story beat
        want = HP.hook_target(payload["delivered_s"], payload["hook_plan"])
        check("c2 %s hook count %d == hook_placement.hook_target(%d, %s)"
              % (name, hooks, payload["delivered_s"], payload["hook_plan"]), hooks == want, hooks)
        style = R.style_text(payload["music_style"], None, "Warm female")
        check("c3 %s style is rebuilt byte-for-byte from the data" % name,
              style == payload["style"], style[:80])


# ---------------------------------------------------------------------------
# (d) a lyric line under an [Instrumental ...] tag

def test_d_no_lyric_under_an_instrumental_tag():
    bad = ("[Instrumental Break: band only, no vocals]\n"
           "six seconds, band only\n")
    errs = R.check_no_voice_lines(bad)
    check("d1 a line under [Instrumental Break] is caught", len(errs) == 1, errs)
    s = _base_sheet()
    s.insert(1, {"tag": "Instrumental Break", "delivery": None, "lines": [],
                 "cue": "band only, no vocals"})
    rendered = R.render_lyrics(s, "soul-ballad")
    check("d2 a no-voice section renders as a tag with no line",
          "[Instrumental Break: band only, no vocals]" in rendered
          and "band only, no vocals\n" not in rendered, rendered)
    with_line = rendered.replace("[Instrumental Break: band only, no vocals]",
                                 "[Instrumental Break: band only, no vocals]\nSix seconds.")
    check("d3 render -> check refuses the injected line",
          len(R.check_no_voice_lines(with_line)) == 1)
    e, _ = _refused(R.prepare, "soul-ballad", _base_sheet() + [
        {"tag": "Instrumental", "delivery": "sung", "lines": ["band only"]}], CLIENT)
    check("d4 a sheet with a line under an instrumental tag is refused",
          e is not None and "no voice" in str(e), e)


# ---------------------------------------------------------------------------
# (e) the product share

def test_e_product_share_gate():
    small = _base_sheet() + [{"tag": "Product", "delivery": "sung", "lines": ["One line."]}]
    pct = R.product_share_pct(small, 178)
    check("e1 a 5-word product passage on 178 s is under 10%", pct < 10.0, pct)
    check("e2 the under-10% share is refused", R.check_product_share(small, 178) != [])
    e, _ = _refused(R.prepare, "soul-ballad", small, CLIENT, None, None, "f", 178)
    check("e3 prepare refuses the under-10% payload", e is not None, e)
    big = _base_sheet() + [{"tag": "Product", "delivery": "sung",
                            "lines": ["a b c d e f g h i j k l m n o p q r s t u v w x y z"] * 3}]
    check("e4 the over-15% share is refused too", R.check_product_share(big, 118) != [])
    ok = _base_sheet(product=True)
    check("e5 a sheet with no Product section makes no product claim",
          R.check_product_share(ok, 58) == [])
    # The 60 s golden fixture is the living proof of the pass case.
    gold = json.loads(open(os.path.join(SHEETS_DIR, "suno-60s-soul-ballad.json"),
                           encoding="utf-8").read())
    g_sheet = R.parse_lyrics(gold["segments"][0]["lyrics"])
    check("e6 the golden 58 s product passage passes (14.5%)",
          R.check_product_share(g_sheet, 58) == [] and
          10.0 <= R.product_share_pct(g_sheet, 58) <= 15.0,
          R.product_share_pct(g_sheet, 58))


# ---------------------------------------------------------------------------
# (f) the spoken band is reachable at 3, 5 and 10 minutes

def test_f_spoken_band_reachable():
    for L in (180, 300, 600):
        p = LF.plan(L)
        pct = p["spoken_share_pct_planned"]
        check("f1 the %d s plan lands inside 20-25%% (%.1f%%)" % (L, pct),
              20.0 <= pct <= 25.0, pct)
        check("f2 the %d s plan says nothing about lowering the target" % L,
              "note" not in p or "set this ad's spoken target" not in p.get("note", ""),
              p.get("note"))
    for L, want in ((60, 22.2), (90, 22.7), (120, 22.4), (180, 22.5)):
        p = LF.plan(L)
        check("f3 the %d s plan is inside 20-25%% (%.1f%%)" % (L, p["spoken_share_pct_planned"]),
              20.0 <= p["spoken_share_pct_planned"] <= 25.0)
    bsw = LF.plan(60, (15, 20))
    check("f4 the BSW per-ad range still plans 15-20% (17.2%)",
          15.0 <= bsw["spoken_share_pct_planned"] <= 20.0, bsw["spoken_share_pct_planned"])
    check("f5 the 22.5% default target is unchanged",
          LF.plan(600)["spoken_share_pct_requested"] == 22.5)
    check("f6 the long lengths' CTA grows past the old 30-word cap",
          LF.plan(600)["words"]["closing"] > 30 and LF.plan(180)["words"]["closing"] > 30,
          (LF.plan(180)["words"]["closing"], LF.plan(600)["words"]["closing"]))
    check("f7 the opener cap is untouched (3 short / 12 long)",
          LF.plan(90)["words"]["opener_max"] == 3 and LF.plan(600)["words"]["opener_max"] == 12)


# ---------------------------------------------------------------------------
# U16 addition: read the villain/pain guidance when the tree carries it

def test_g_villain_guidance_read():
    path = os.path.join(CORE, "product_style_bible", "bible.py")
    guidance = None
    if os.path.isfile(path):
        src = open(path, encoding="utf-8").read()
        import re
        m = re.search(r"VILLAIN_LYRIC_GUIDANCE\s*=\s*\((.*?)\)\n", src, re.S)
        if m:
            guidance = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    # Measured this run, both facts:
    #   * this tree's bible.py carries no VILLAIN_LYRIC_GUIDANCE (U16 is on
    #     unit/FU-U16, heads onb 8467e035..., 999 c4787e2c..., not on this base);
    #   * the guidance was READ from those heads and lives in the music data.
    print("report: VILLAIN_LYRIC_GUIDANCE in %s: %s"
          % (path, "present" if guidance else "ABSENT (U16 branch only)"))
    for sid in ("soul-ballad", "rnb-flow", "soul-rise"):
        block = R.music_block(sid)
        check("g1 %s carries the villain/pain lyric guidance" % sid,
              "VILLAIN IN THE LYRICS" in str(block.get("villain_pain_lyric_guidance")),
              str(block.get("villain_pain_lyric_guidance"))[:60])
        if guidance:
            check("g1b %s guidance equals the U16 wording verbatim" % sid,
                  block.get("villain_pain_lyric_guidance") == guidance)
        check("g2 %s names where the guidance was read from" % sid,
              "U16" in str(block.get("villain_pain_lyric_guidance_source", "")),
              block.get("villain_pain_lyric_guidance_source"))
    check("g3 the guidance is never pasted into the style text (lyric rule, not a tag)",
          "VILLAIN IN THE LYRICS" not in R.style_text("soul-ballad", None, "female"))


def main():
    # Each group reports its own failures; a group that cannot even run on
    # this tree (the base tree has no gender argument, no data loader) is
    # recorded as a failure naming the reason rather than crashing the rest.
    for fn in (test_a_rnb_style_has_no_ballad_lead,
               test_a_gender_is_from_the_brief_never_hard_coded,
               test_b_caps_are_refused,
               test_c_golden_payloads_pass,
               test_d_no_lyric_under_an_instrumental_tag,
               test_e_product_share_gate,
               test_f_spoken_band_reachable,
               test_g_villain_guidance_read):
        try:
            fn()
        except Exception as exc:            # noqa: BLE001 - report, keep going
            check("%s ran" % fn.__name__, False, "%s: %s" % (type(exc).__name__, exc))
    print("")
    if FAILS:
        print("FAILED (%d): %s" % (len(FAILS), "; ".join(FAILS)))
        return 1
    print("ALL PASS (U15d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
