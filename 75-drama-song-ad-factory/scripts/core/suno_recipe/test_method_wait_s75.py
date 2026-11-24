#!/usr/bin/env python3
"""S75 (2026-11-19): a METHOD run WAITS -- no singing until the groove drops.

Run: python3 core/suno_recipe/test_method_wait_s75.py     (or pytest, no fixtures)

WHY THIS EXISTS. The method lane was never measured, so it inherited the old
ERM Drop wording with no refusal in it and a method stem sang about 5 s in.
The same order naming "no singing until the groove drops" held the first sung
line back to 38-46 s, inside the ERM window the method's own plan sets. Three
things follow from that measurement, and this file proves all three on the
REAL assembled payloads:

  * the ERM Drop now LEADS with the refusal and still keeps the anchor;
  * a method style carries the spoken-band sentence verbatim, so the band is
    told to keep playing under the narrated backstory;
  * a method lyric sheet must have ENOUGH spoken lead-in to reach the ERM
    apex minus the C3 tolerance, and not overrun the ERM window -- the
    pre-ERM gate (check_pre_erm_opening) refuses the short one before spend.

The Soul Ballad variant styles are proved at the 1000-character cap because
the refusal append is a raise, never a truncation.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "intake_preflight"))

from song_choices import song_choices as SC                     # noqa: E402
from suno_recipe import suno_recipe as R                         # noqa: E402
from song_contract import song_contract as _SC                   # noqa: E402

#: The method order that motivated this unit: an explicit drop and return.
ORDER = {"method": True,
         "drop": "full groove drops in, heavier half-time with a deep kick",
         "return": "key change up, drums pull back, space opens"}
#: A method order that names NO drop at all: the default clause must still
#: carry the refusal, and check_pace_style must accept it.
ORDER_NO_DROP = {"method": True}

#: The non-method style text BEFORE this unit, byte for byte. A non-method run
#: must never see the method wording.
BASE_SOUL_BALLAD = (
    "soul ballad, slow emotional 62-68 bpm, warm felt piano, brushed kit entering "
    "at the chorus, deep rounded bass, soulful lead vocal with melismatic runs, "
    "close dry upfront vocal, minor key, restrained verse opening into a "
    "full-voiced chorus, no distortion. female lead, sung melody with long held "
    "open vowels, slow tempo. The lead SPEAKS the lines tagged Spoken in a plain "
    "natural voice over the music, and SINGS the lines tagged Sung with long held "
    "notes. Only the short intro and the final outro are spoken; the full band "
    "keeps playing continuously under them, natural resolved ending, final chord "
    "rings out and fades. Sing the sections in the order written; the song never "
    "opens with the hook: build up through the verse first."
)
BASE_SOUL_BALLAD_SHA256 = "a4e7fec9ee545bd2d2206a88d45a294307ac7ecb07ecca26002d0536d8199fb5"

_BANK = ("morning coffee kitchen window quiet hallway letter promise daughter "
         "bills table silence mirror evening porch light").split()


def _line(n, start=0):
    return " ".join(_BANK[(start + i) % len(_BANK)] for i in range(n))


def _hook():
    return "rest and rise with me tonight"


def _sung_sheet(intro_words=12, backstory_words=None, instrumental=False):
    """A minimal method song sheet: spoken lead-in, then sung sections."""
    sheet = []
    if instrumental:
        sheet.append({"tag": "Instrumental", "delivery": None, "lines": []})
    if intro_words:
        sheet.append({"tag": "Intro", "delivery": "spoken",
                      "lines": [_line(intro_words, 0)]})
    if backstory_words:
        sheet.append({"tag": "Backstory", "delivery": "spoken",
                      "lines": [_line(backstory_words, 3)]})
    sheet.append({"tag": "Verse 1", "delivery": "sung",
                  "lines": ["i was tired and alone", "then you called my name"]})
    sheet.append({"tag": "Hook 1", "delivery": "sung", "lines": [_hook()]})
    sheet.append({"tag": "Hook 2", "delivery": "sung", "lines": [_hook()]})
    return sheet


# ---- the style: the refusal is written, the spoken band sentence kept -----
def test_method_style_carries_the_no_singing_lead_and_the_spoken_clause():
    """On a method order the final style refuses singing until the drop and
    says the band keeps playing under the spoken lines -- and never says the
    intro/outro are the only spoken sections (false on a method run)."""
    text = R.style_text("soul-ballad", pace_plan=ORDER)
    assert ("no singing until the groove drops, then full groove drops in"
            in text), text
    assert R.METHOD_SPOKEN_CLAUSE.rstrip(".") in text, text
    assert "Only the short intro" not in text, text
    assert R.check_style_text(text) == [], R.check_style_text(text)
    assert _SC.check_pace_style(text, ORDER) == [], _SC.check_pace_style(text, ORDER)


def test_method_order_with_no_drop_still_carries_the_default_and_passes():
    """A method order that names no drop uses METHOD_ERM_DROP_CLAUSE, which
    still leads with the refusal; the pace gate accepts it."""
    text = R.style_text("soul-ballad", pace_plan=ORDER_NO_DROP)
    assert R.METHOD_ERM_DROP_CLAUSE in text, text
    assert "no singing until the groove drops, and the first sung line enters" in text
    assert _SC.check_pace_style(text, ORDER_NO_DROP) == [], \
        _SC.check_pace_style(text, ORDER_NO_DROP)


def test_the_lead_is_prefixed_only_once():
    """An explicit drop that already names the refusal is not prefixed again."""
    drop = R.METHOD_NO_SINGING_LEAD + "the floor opens up"
    text = R.style_text("soul-ballad", pace_plan={"method": True, "drop": drop})
    assert text.count("no singing until the groove drops") == 1, text


def test_non_method_style_text_is_byte_identical():
    """A non-method run is untouched by this unit."""
    text = R.style_text("soul-ballad")
    assert text == BASE_SOUL_BALLAD
    assert hashlib.sha256(text.encode()).hexdigest() == BASE_SOUL_BALLAD_SHA256


def test_soul_ballad_variant_styles_stay_under_the_cap():
    """Each of the three variants' final style is <= 1000 chars and passes the
    style gate, WITH the longer method clause appended."""
    for v in SC.variants_for("soul-ballad"):
        text = R.brief_style_text(
            "soul-ballad", SC._brief_text(v, "f"), None, "f", ORDER,
            tail_clause=v["brief"]["arrangement"],
            revoices_lead=bool(v.get("revoices_lead")))
        assert len(text) <= R.SUNO_STYLE_FIELD_MAX, (v["id"], len(text))
        assert R.check_style_text(text) == [], (v["id"], R.check_style_text(text))
        assert R.METHOD_SPOKEN_CLAUSE.rstrip(".") in text, v["id"]


def test_the_backstory_cue_says_no_singing_yet():
    """The [Backstory] tag resolves to a cue that refuses singing."""
    cue = R.cue_for("spoken", "Backstory")
    assert "no singing yet" in cue, cue
    assert cue == R.model_block()["cue_vocabulary"]["spoken"]["backstory"]


# ---- the gate: the spoken lead-in must fill the gap before the ERM --------
def test_pre_erm_gate_passes_the_sheet_that_worked():
    """12-word Intro + 48-word Backstory = 60 words at 1.85 w/s = 32.4 s,
    inside [31.0, 40.0] (apex 32.5 +/- 1.5 to the ERM window's close)."""
    assert R.check_pre_erm_opening(_sung_sheet(12, 48), 178) == []


def test_pre_erm_gate_refuses_a_short_lead_in():
    """12 spoken words = 6.5 s, short of 31.0 s; the message names the 58
    words the sheet needs."""
    errs = R.check_pre_erm_opening(_sung_sheet(12, None), 178)
    assert len(errs) == 1, errs
    assert errs[0].startswith("PRE_ERM_SPOKEN_SHORT"), errs[0]
    assert "58" in errs[0], errs[0]


def test_pre_erm_gate_refuses_a_long_lead_in():
    """100 spoken words = 54.1 s, past the ERM window's 40.0 s."""
    errs = R.check_pre_erm_opening(_sung_sheet(100, None), 178)
    assert len(errs) == 1, errs
    assert errs[0].startswith("PRE_ERM_SPOKEN_LONG"), errs[0]


def test_pre_erm_gate_warns_on_an_instrumental_lead_in():
    """A sheet that OPENS on a no-voice tag warns instead of refusing: the
    render may hold the silence, but the sheet does not guarantee it."""
    warnings = []
    errs = R.check_pre_erm_opening(_sung_sheet(12, None, instrumental=True), 178,
                                   warnings_out=warnings)
    assert errs == [], errs
    assert len(warnings) == 1 and warnings[0].startswith("PRE_ERM_LEAD_IN_UNPLANNED"), warnings


def test_check_lyric_sheet_runs_the_gate_only_on_a_method_run():
    """check_lyric_sheet(method=True) flags the short sheet; method=False does
    not -- the 15 percent rule stays the judge for every non-method run."""
    sheet = _sung_sheet(12, None)
    client = _hook()
    method_errs = R.check_lyric_sheet(sheet, client, 178, style_id="soul-ballad",
                                      method=True)
    assert any(e.startswith("PRE_ERM_SPOKEN_SHORT") for e in method_errs), method_errs
    other_errs = R.check_lyric_sheet(sheet, client, 178, style_id="soul-ballad",
                                     method=False)
    assert not any("PRE_ERM" in e for e in other_errs), other_errs


def main():
    fails = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print("  ok   %s" % name)
        except Exception as e:                      # noqa: BLE001 - self-check
            fails += 1
            print("  FAIL %s: %s: %s" % (name, type(e).__name__, e))
    if not fails:
        print("  ALL PASS")
    else:
        print("  %d FAILED" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
