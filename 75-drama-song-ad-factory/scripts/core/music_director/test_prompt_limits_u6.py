#!/usr/bin/env python3
"""FU-U6: Suno request limits, fail closed, measured LAST. Zero network, zero spend.

Proves (each refused with field, chars, cap, source, status; nothing truncated):
  1. lyrics over 5,000 chars are refused (catalog 68 suno-generate, VERIFIED);
  2. a FINAL style over 1,000 chars is refused AFTER ending_qc appended the
     ending (today the guard runs before the append and never re-measures);
  3. a title over 80 chars is refused (80 is generate; 100 is extend only);
  4. negative_tags over 1,000 are refused and stamped UNVERIFIED with its
     source URL and the free confirm step;
  5. every refusal NAMES field, chars, cap, source, status, and truncates
     nothing (the payload is never mutated into a passing one);
  6. the caps come from the 68 catalog (read live), never copied;
  7. the all-clear path still builds (no false refusal);
  8. song_dispatch accepts the G9 headroom duration and still refuses a patch.

Run: python3 core/music_director/test_prompt_limits_u6.py   (from scripts/core)
Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(CORE, "__pycache__")
if os.path.isdir(_CACHE):
    for _n in os.listdir(_CACHE):
        if _n.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _n))
            except OSError:
                pass

import length_formula as LF          # noqa: E402
import music_director as MD          # noqa: E402
import prompt_limits as PL           # noqa: E402
import song_dispatch as SD           # noqa: E402
import suno_recipe as R              # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

CLIENT = "I am not small. I never was. One seed of truth made me strong. She Found Power in the Climb."
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}   # FU-HOOK-PLACEMENT: hooks measured from the sheet
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken", "lines": ["She Found Power in the Climb. Get the book. Link below."]}]

def refused(fn, *a, **kw):
    """(True, error) when fn raises PromptLimitError, else (False, result)."""
    try:
        return False, fn(*a, **kw)
    except PL.PromptLimitError as e:
        return True, e

def names_all(e):
    text = str(e)
    return all(part in text for part in
               ("PROMPT_OVER_CAP", "field", "chars", "cap", "source", "status"))


# ---- 1. catalog is the source, not a copy ---------------------------------
def test_caps_come_from_the_catalog():
    caps = PL.suno_caps()
    check("68 catalog caps read (lyrics 5000, style 1000, title 80)",
          (caps["lyrics"], caps["style"], caps["title"]) == (5000, 1000, 80), caps)
    check("cap source names the 68 catalog and the VERIFIED date",
          "models.json" in caps["source"] and "VERIFIED" in caps["source"], caps["source"])
    check("duration window read (10-360)",
          caps["duration"] == {"min_seconds": 10, "max_seconds": 360}, caps["duration"])
    check("negativeTags override is UNVERIFIED with URL + confirm step",
          PL.OVERRIDES["negative_tags"]["status"] == "UNVERIFIED"
          and PL.OVERRIDES["negative_tags"]["source_url"].startswith("https://docs.kie.ai/")
          and "docs.kie.ai" in PL.OVERRIDES["negative_tags"]["confirm"])
    check("avatar override is UNVERIFIED with URL + confirm step",
          PL.OVERRIDES["kling/ai-avatar-standard"]["cap"] == 2500
          and PL.OVERRIDES["kling/ai-avatar-standard"]["status"] == "UNVERIFIED"
          and "docs.kie.ai" in PL.OVERRIDES["kling/ai-avatar-standard"]["source_url"])


# ---- 2. the four refusals --------------------------------------------------
def test_lyrics_over_5001_refused():
    ok, got = refused(PL.check_request, "suno-generate",
                      {"input": {"model": "V6", "lyrics": "x" * 5001, "style": "s", "title": "t",
                                 "negative_tags": "n"}})
    check("5,001-char lyrics refused", ok and got.field == "lyrics" and got.chars == 5001
          and got.cap == 5000, got)
    check("lyrics refusal names field/chars/cap/source/status", ok and names_all(got), str(got))
    check("lyrics refusal carries the VERIFIED status", ok and got.status == "VERIFIED"
          and "models.json" in got.source, str(getattr(got, "source", "")))
    check("lyrics never truncated (input untouched)", ok)


def test_final_style_over_1001_refused_after_the_ending():
    # The E.2 order-of-mutation hole, exactly: a free-form style at 1,000 chars
    # passes suno_recipe.guard_request, then ending_qc.with_clean_ending appends
    # ", natural resolved ending, final chord rings out and fades" (54 chars)
    # -> a 1,054-char FINAL style that the API receives. The gate runs AFTER
    # the append, on the final payload; nothing is truncated.
    ENDING = ", natural resolved ending, final chord rings out and fades"
    style = ("female lead, dry close vocal, slow tempo, " + ("warm analog strings, " * 60))[:1000].rstrip(", ")
    req = {"model": "suno-generate", "input": {"custom_mode": True, "model": "V6",
           "style": style + ENDING, "title": "T", "lyrics": "line", "negative_tags": "choir"}}
    ok, got = refused(MD.build_generate_request, "line", style, "T",
                       style_id="velvet_voiceover")  # no style + lyrics = UNMEASURED
    check("the FINAL style (ending appended) is refused through build_generate_request",
          ok and got.field == "style" and got.chars == len(style) + len(ENDING), got)
    check("style refusal names the style field, its chars, cap 1,000",
          ok and got.field == "style" and got.chars > 1000 and got.cap == 1000, str(got))
    check("the over-cap final style is refused, never truncated into a pass",
          ok and got.chars - got.cap == len(ENDING) - (1000 - len(style)), getattr(got, "chars", None))
    ok2, got2 = refused(PL.check_request, "suno-generate", req)
    check("a 1,001-char final style is refused by check_request", ok2 and got2.field == "style", got2)


def test_title_over_81_refused():
    ok, got = refused(PL.check_request, "suno-generate",
                      {"input": {"model": "V6", "title": "T" * 81, "lyrics": "l",
                                 "style": "s", "negative_tags": "n"}})
    check("81-char title refused at cap 80 (100 is extend only)", ok and got.field == "title"
          and got.chars == 81 and got.cap == 80, got)
    check("80-char title passes (extend's 100 is not the generate cap)",
          PL.check_request("suno-generate", {"input": {"model": "V6", "title": "T" * 80}}), None)


def test_negative_tags_over_1001_refused_unverified():
    ok, got = refused(PL.check_request, "suno-generate",
                      {"input": {"model": "V6", "negative_tags": "n" * 1001, "lyrics": "l", "style": "s"}})
    check("1,001-char negative_tags refused at the declared cap 1,000",
          ok and got.field == "negative_tags" and got.chars == 1001 and got.cap == 1000, got)
    check("negative_tags refusal is stamped UNVERIFIED with its URL",
          ok and got.status == "UNVERIFIED" and got.source.startswith("https://docs.kie.ai/"), str(got))
    check("negative_tags refusal carries the confirm step in the override table",
          "docs.kie.ai" in PL.OVERRIDES["negative_tags"]["confirm"])


# ---- 3. the clear paths still pass ----------------------------------------
def test_clear_path_builds_and_is_measured():
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)
    rows = {m["field"]: m for m in PL.check_request("suno-generate", req)["measured"]}
    check("clean payload passes and every field is measured",
          set(rows) >= {"lyrics", "style", "title", "negative_tags"}, sorted(rows))
    check("clean style row is under cap", rows["style"]["chars"] <= rows["style"]["cap"], rows["style"])
    check("build_generate_request passes on the clean sheet",
          bool(MD.build_generate_request(R.render_lyrics(SHEET), R.style_text("soul-ballad"), "T",
                                         style_id="soul-ballad", client_text=CLIENT,
                                         length_s=58, true_at_beat="the_world")))


# ---- 4. the 999 dispatch seam: G9 headroom allowed, a patch still refused -
def test_dispatch_allows_headroom_duration():
    plan = dict(LF.plan(60, (15, 20)), style_id="soul-ballad", hook_plan=HOOK_PLAN)
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", plan["delivered_s"], hook_plan=HOOK_PLAN)
    req["duration"] = 67.0  # stub take, never real audio
    GOOD = {"segments": [{"delivery": "spoken", "start": 0, "end": 2, "source": "measured"},
                         {"delivery": "sung", "start": 2.5, "end": 45, "source": "measured"},
                         {"delivery": "spoken", "start": 45, "end": 54, "source": "measured"}],
            "detector": "singing_detector 2.0.0", "duration_s": 57.5, "first_sung_s": 2.5,
            "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0}
    # FU-HOOK-PLACEMENT: Suno's aligned words carry each section header inline
    # on the section's first word; the always-on hook_placement gate reads them.
    words = []
    for block in req["lyrics"].split("\n\n"):
        head, *lines = block.split("\n")
        toks = " ".join(lines).split() or [""]
        words += [{"word": (head + "\n" + w + " ") if k == 0 else w + " "} for k, w in enumerate(toks)]
    words = [dict(w, startS=i, endS=i + 0.5) for i, w in enumerate(words)]
    GOOD["aligned_words"] = [dict(w, startS=3 + i, endS=3.5 + i) for i, w in enumerate(words)]
    hook = " ".join(HOOK)
    script = "One closed door. She Found Power in the Climb. Get the book. Link below."
    # headroom (plan + >=15%) and the exact planned length are both accepted;
    # a patch/short duration is still refused before any spend.
    out = SD.run_takes(req, plan, lambda rq: [dict(GOOD), dict(GOOD)], lambda t: {},
                       lambda t, r: None, script, hook, (15, 20), kie=lambda fn, lbl, generation=False: fn(),
                       style_id="soul-ballad")
    check("G9 headroom duration accepted (no whole-track refusal)",
          out["verdict"] in ("PASS", "FLAG", "FAIL") and out["spent_cents"] == 6, out)
    out2 = SD.run_takes(dict(req, duration=plan["delivered_s"]), plan, lambda rq: [dict(GOOD), dict(GOOD)],
                        lambda t: {}, lambda t, r: None, script, hook, (15, 20),
                        kie=lambda fn, lbl, generation=False: fn(), style_id="soul-ballad")
    check("exact planned duration still accepted", out2["spent_cents"] == 6, out2)
    try:
        SD.run_takes(dict(req, duration=30), plan, lambda rq: [], lambda t: {}, lambda t, r: None,
                     script, hook, (15, 20))
        check("a patch/short duration is still refused", False, "30 s accepted")
    except SD.DispatchError:
        check("a patch/short duration is still refused", True)


def main():
    test_caps_come_from_the_catalog()
    test_lyrics_over_5001_refused()
    test_final_style_over_1001_refused_after_the_ending()
    test_title_over_81_refused()
    test_negative_tags_over_1001_refused_unverified()
    test_clear_path_builds_and_is_measured()
    test_dispatch_allows_headroom_duration()
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
