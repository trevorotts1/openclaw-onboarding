#!/usr/bin/env python3
"""W-G-002 amend suite (Trevor order 2026-10-08 11:50 EDT, part G; review G4/G5).

Adversarial battery for the delivery-named tag grammar and the singability
rules. Stdlib only, zero paid calls. Proves BOTH directions:

  ACCEPT
  1. build_sheet names the delivery in EVERY emitted tag and its own output
     passes its own lint (idempotent, no reject loop).
  2. A reference-shaped sheet ([Sung - ...] repeated hook + a rhymed pair)
     passes check_sheet and the G5 singability check.
  3. Rap blocks pass through untouched; [Instrumental] is not a delivery.
  4. delivery_of_tag word-boundary controls: "trap beat" is not rap;
     "spoken-word" is spoken; the earliest delivery word wins.

  REJECT
  5. The O3 sheet is refused by check_sheet on the amend's three rules:
     bare [Verse]/[Chorus]/[Bridge] tags, a one-line sung block, and more
     than one delivery switch per 20 s.
  6. lyric_writer.validate_lyrics refuses O3-style prose marked sung
     ("prose-line-in-sung-block"), while a reference hook passes.

Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(HERE, "__pycache__")
if os.path.isdir(_CACHE):
    for _name in os.listdir(_CACHE):
        if _name.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _name))
            except OSError:
                pass

import lyric_writer as LW                     # noqa: E402
import lyric_structure as LS                  # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

# ---- fixtures -------------------------------------------------------------

#: The reference shape (review 04, section 3.1): a repeated sung hook and a
#: rhymed couplet, every tag naming its delivery.
REFERENCE_SHEET = """[Sung - lead, long held notes]
Girl, I got you
Girl, I got you

[Spoken - lead, plain natural speech over the music]
One check, that is all I have.

[Sung - lead, long held notes]
You can touch the sky
You can always fly
"""

#: The O3 fault shape (review 04, section 4.1): bare [Verse]/[Chorus]/[Bridge]
#: beside [Spoken Word], one one-line chorus, 8+ delivery switches in 90 s.
O3_SHEET = """[Spoken Word]
Eleven at night and the mind will not stop.

[Verse]
Your phone says rest
Your training says one more thing

[Spoken Word]
You were eight years old making snacks.

[Chorus]
And the cape got heavier

[Verse]
The question you stopped asking
Who is holding me

[Spoken Word]
Nobody claps for the woman who never puts it down.

[Verse]
Rest does not need to be earned
Softness is not quitting

[Spoken Word]
Say it out loud once.

[Bridge]
You spent decades proving you are strong enough
Let this be the era you set it down

[Chorus]
Wake Up Happy Sis
Built for the woman who did everything alone

[Spoken Word]
Come sit with us at the site. The seat is saved.
"""

# ---- ACCEPT ---------------------------------------------------------------

def test_builder_names_delivery_in_every_tag():
    r = LS.build_sheet(LS.ALTERNATING_SHEET, 90)
    check("alternating sheet builds ok", r["outcome"] == "ok",
          "; ".join(r["lint"]["reasons"][:2]))
    tags = [blk["tag"] for blk in LS.parse_sheet(r["sheet"])]
    unnamed = [t for t in tags if LS.delivery_of_tag(t) is None]
    check("every emitted tag names its delivery", not unnamed, repr(unnamed))
    check("switches within the rate", r["switches"] <= r["switch_allowance"],
          "switches=%d allowance=%d" % (r["switches"], r["switch_allowance"]))
    # idempotent: feeding the built sheet back stays ok (no reject loop)
    r2 = LS.build_sheet(r["sheet"], 90)
    check("re-run stays ok", r2["outcome"] == "ok",
          "; ".join(r2["lint"]["reasons"][:2]))
    check("re-run keeps the delivery-named tags",
          not [b for b in LS.parse_sheet(r2["sheet"])
               if LS.delivery_of_tag(b["tag"]) is None])

def test_reference_sheet_passes():
    r = LS.check_sheet(REFERENCE_SHEET, 300)
    check("reference sheet passes check_sheet", r["outcome"] == "ok",
          "; ".join(r["reasons"][:3]))
    check("reference switches within rate", r["switches"] <= r["switch_allowance"],
          "switches=%d" % r["switches"])

def test_rap_passes_through_and_instrumental_is_not_delivery():
    sheet = REFERENCE_SHEET + "\n[Rap - lead, confident metered flow]\n" \
        "I count my wins on one hand\nI never needed your plan\n\n" \
        "[Instrumental]\n"
    r = LS.build_sheet(sheet, 300)
    check("rap sheet builds ok", r["outcome"] == "ok",
          "; ".join(r["lint"]["reasons"][:2]))
    check("rap block survives", "[Rap -" in r["sheet"])
    check("instrumental renders plain", "[Instrumental]" in r["sheet"])
    check("instrumental is not a delivery",
          LS.delivery_of_tag("Instrumental") == "instrumental")

def test_delivery_of_tag_word_boundaries():
    check("bare verse is unnamed", LS.delivery_of_tag("Verse") is None)
    check("bare chorus is unnamed", LS.delivery_of_tag("Chorus") is None)
    check("sung named", LS.delivery_of_tag("Sung - lead, long held notes") == "sung")
    check("spoken name wins over unknown", LS.delivery_of_tag("Spoken Word") == "spoken")
    check("hyphen normalizes", LS.delivery_of_tag("spoken-word") == "spoken")
    check("trap beat is NOT rap", LS.delivery_of_tag("Sung - trap beat") == "sung")
    check("rapid is NOT rap", LS.delivery_of_tag("Sung - rapid fire") == "sung")
    check("earliest delivery word wins",
          LS.delivery_of_tag("Chanel - female voice, sung smooth hook") == "sung")

def test_render_tag_is_idempotent_and_named():
    for tag in ("Verse", "Chorus", "Bridge", "Hook", "Spoken Word",
                "Sung - lead, long held notes"):
        out = LS.render_tag(tag)
        check("render_tag(%r) names delivery" % tag,
              LS.delivery_of_tag(out) is not None, repr(out))
        check("render_tag(%r) idempotent" % tag,
              LS.render_tag(out) == out, repr((out, LS.render_tag(out))))

def test_switch_allowance_scales():
    check("90s allows 4", LS.switch_allowance(90) == 4)
    check("60s allows 3", LS.switch_allowance(60) == 3)
    check("20s allows at least 1", LS.switch_allowance(20) >= 1)
    check("300s allows 15", LS.switch_allowance(300) == 15)

# ---- REJECT ---------------------------------------------------------------

def test_o3_sheet_refused_with_the_amend_reasons():
    r = LS.check_sheet(O3_SHEET, 90)
    check("O3 sheet refused", r["outcome"] == "rejected")
    reasons = " | ".join(r["reasons"])
    check("O3 refused: bare tags named",
          "delivery-named-tags" in reasons, reasons[:200])
    check("O3 refused: one-line sung block",
          "sung-block-two-lines" in reasons, reasons[:200])
    check("O3 refused: delivery switch rate",
          "delivery-switch-rate" in reasons, reasons[:200])
    check("O3 switch count over allowance",
          r["switches"] > r["switch_allowance"],
          "switches=%d allowance=%d" % (r["switches"], r["switch_allowance"]))

def test_o3_sheet_is_remedied_by_the_builder():
    r = LS.build_sheet(O3_SHEET, 90)
    check("O3 build converges", r["outcome"] == "ok",
          "; ".join(r["lint"]["reasons"][:3]))
    check("O3 input grammar carries the refusal record",
          r["input_grammar"]["verdict"] == "FAIL")

def test_one_line_sung_block_refused_bare():
    sheet = "[Sung - lead, long held notes]\nOne line only here\n"
    r = LS.check_sheet(sheet, 60)
    check("one-line sung block refused", r["outcome"] == "rejected")
    check("reason names the one-liner",
          any("sung-block-two-lines" in x for x in r["reasons"]), r["reasons"])

def test_lyric_writer_refuses_o3_prose_sung():
    bad = [
        {"line_id": "v1", "delivery": "sung",
         "text": "If you do not know when that split started"},
        {"line_id": "v2", "delivery": "sung",
         "text": "Built for the woman who did everything alone"},
    ]
    errs = LW.check_sung_lines(bad)
    codes = [e["error"] for e in errs]
    check("O3 prose marked sung refused",
          "prose-line-in-sung-block" in codes, repr(codes))
    check("O3 prose also fails the meter",
          "sung-line-not-metered" in codes, repr(codes))

def test_lyric_writer_accepts_reference_hook():
    good = [
        {"line_id": "h1", "delivery": "sung", "text": "Girl, I got you"},
        {"line_id": "h2", "delivery": "sung", "text": "Girl, I got you"},
        {"line_id": "h3", "delivery": "sung", "text": "You can touch the sky"},
        {"line_id": "h4", "delivery": "sung", "text": "You can always fly"},
    ]
    check("reference hook passes G5", LW.check_sung_lines(good) == [],
          repr(LW.check_sung_lines(good)))

def test_lyric_writer_unchanged_without_delivery_field():
    plain = [{"line_id": "p1", "text": "Some prose line here."}]
    check("no delivery field: no G5 judgement",
          LW.check_sung_lines(plain) == [])

def test_bad_input_raises():
    for bad_secs in (None, 0, "x"):
        try:
            LS.check_sheet(REFERENCE_SHEET, bad_secs)
            check("check_sheet raises on seconds=%r" % (bad_secs,), False)
        except LS.LyricStructureError:
            check("check_sheet raises on seconds=%r" % (bad_secs,), True)
    try:
        LS.check_sheet("", 90)
        check("empty sheet raises", False)
    except LS.LyricStructureError:
        check("empty sheet raises", True)

def main():
    test_builder_names_delivery_in_every_tag()
    test_reference_sheet_passes()
    test_rap_passes_through_and_instrumental_is_not_delivery()
    test_delivery_of_tag_word_boundaries()
    test_render_tag_is_idempotent_and_named()
    test_switch_allowance_scales()
    test_o3_sheet_refused_with_the_amend_reasons()
    test_o3_sheet_is_remedied_by_the_builder()
    test_one_line_sung_block_refused_bare()
    test_lyric_writer_refuses_o3_prose_sung()
    test_lyric_writer_accepts_reference_hook()
    test_lyric_writer_unchanged_without_delivery_field()
    test_bad_input_raises()
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
