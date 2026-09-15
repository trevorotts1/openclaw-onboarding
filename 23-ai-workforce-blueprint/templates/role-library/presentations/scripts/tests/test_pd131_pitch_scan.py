"""PD-TEST-131 -- AF-PITCH-LEAK must scan CONTENT, not serialization.

THE DEFECT, measured on live run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.
`build_deck._chk_pitch_leak` lowercased the whole file and tested each forbidden
token as a bare substring. On that PITCHLESS deck it failed on two things that are
not pitch content at all:

  1. THE RECORD OF ABSENCE. The arc allocation documents its own suppression using
     the forbidden vocabulary, verbatim: "...intake declares pitch_included:false,
     so there is no anchor price, value stack, or price ladder in this deck."
     The producer did what a pitchless deck requires and then SAID SO.
  2. NULL-VALUED SCHEMA KEYS. The same file carries the schema's own field names
     with null values -- "price_ladder_section": null, "value_stack_section": null,
     "re_pitch_section": null, "offer_price_ladder_included": false -- so a key
     declaring a thing ABSENT was scanned as if it declared it PRESENT.

WHAT THESE TESTS PIN
  * a null-valued schema key is never a hit (values are scanned, keys are not);
  * prose ABOUT the artifact (`*_reason`, `*_note(s)`, `validation_notes`) is not
    content and is not scanned;
  * a GENUINE leak in a substantive field STILL fails -- the negative control that
    stops this from being a "make the check pass" patch;
  * an unparseable JSON file degrades to the whole-text scan, so a broken artifact
    can never become a SILENT pass.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import build_deck as bd  # noqa: E402


def _run(tmp_path: Path, arc: object, copy_text: str = "SLIDE 1\nsomething\n") -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"deck_type": "webinar", "pitch_included": False}))
    (rd / "working" / "copy" / "slides_copy.md").write_text(copy_text)
    p = rd / "working" / "copy" / "arc_allocation.json"
    if isinstance(arc, str):
        p.write_text(arc)                       # raw, for the unparseable case
    else:
        p.write_text(json.dumps(arc))
    return rd


# ---------------------------------------------------------------------------
# 1 -- NULL-VALUED SCHEMA KEYS ARE NOT A LEAK.
# ---------------------------------------------------------------------------
def test_null_valued_schema_keys_do_not_leak(tmp_path):
    rd = _run(tmp_path, {
        "pitch_included": False,
        "non_applicable_sections": {
            "price_ladder_section": None,
            "value_stack_section": None,
            "re_pitch_section": None,
            "anchor_price_section": None,
            "offer_price_ladder_included": False,
        },
    })
    assert bd._chk_pitch_leak(rd) == "", (
        "a key that declares a thing ABSENT must not be read as declaring it present")


# ---------------------------------------------------------------------------
# 2 -- PROSE ABOUT THE ARTIFACT IS NOT CONTENT.
# ---------------------------------------------------------------------------
def test_the_record_of_absence_does_not_leak(tmp_path):
    rd = _run(tmp_path, {
        "pitch_included": False,
        "arc_profile": {"offer_price_ladder_reason":
                        "intake.json records pitch_included:false and all offer, price, "
                        "and stack fields are empty; no offer, anchor, price-ladder, or "
                        "re-pitch beats are authored."},
        "peak_apex": {"note": "intake declares pitch_included:false, so there is no "
                              "anchor price, value stack, or price ladder in this deck."},
        "validation_notes": ["no offer, price, ladder, vip, or re-pitch content is "
                             "included because intake.json records pitch_included:false."],
    })
    assert bd._chk_pitch_leak(rd) == "", (
        "a sentence DENYING pitch content must not be read as pitch content")


# ---------------------------------------------------------------------------
# 3 -- THE NEGATIVE CONTROL: a real leak still fails.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("field,value,token", [
    ("section_id", "price_ladder", "price_ladder"),
    ("name", "Value Stack Reveal", "value stack"),
    ("move_tag", "RE-PITCH", "re-pitch"),
    ("slide_title", "Buy now before it closes", "buy now"),
])
def test_a_genuine_leak_in_a_substantive_field_still_fails(tmp_path, field, value, token):
    """Without this the fix would be a 'make the check pass' patch. `_reason` and
    `note` are skipped because they are prose ABOUT the artifact; `section_id`,
    `name`, `move_tag` and `slide_title` ARE the artifact, so a leak there is real."""
    rd = _run(tmp_path, {"pitch_included": False, field: value})
    msg = bd._chk_pitch_leak(rd)
    assert msg, f"a real leak in {field!r} must still fail"
    assert token in msg, msg


def test_a_leak_in_the_copy_still_fails(tmp_path):
    rd = _run(tmp_path, {"pitch_included": False},
              copy_text="SLIDE 1\nLIMITED TIME OFFER: act now\n")
    msg = bd._chk_pitch_leak(rd)
    assert msg and "act now" in msg, msg


# ---------------------------------------------------------------------------
# 4 -- A BROKEN ARTIFACT CAN NEVER BECOME A SILENT PASS.
# ---------------------------------------------------------------------------
def test_unparseable_json_degrades_to_the_whole_text_scan(tmp_path):
    rd = _run(tmp_path, '{"broken": "price ladder", ')   # raw, invalid JSON
    msg = bd._chk_pitch_leak(rd)
    assert msg and "price ladder" in msg, (
        "an unparseable artifact must fall back to the stricter whole-text scan, "
        f"never to a pass: {msg!r}")


# ---------------------------------------------------------------------------
# 5 -- the scan helper itself: keys are never returned.
# ---------------------------------------------------------------------------
def test_pitch_scan_texts_returns_values_never_keys(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"price_ladder_section": None,
                             "name": "Cost of Carrying It Yourself",
                             "nested": {"value_stack": "x"}}))
    texts = bd._pitch_scan_texts(p)
    joined = " | ".join(texts)
    assert "price_ladder_section" not in joined, "a KEY must never be scanned"
    assert "Cost of Carrying It Yourself" in joined, "values must be scanned"
    assert "x" in joined, "nested values must be scanned"


# ---------------------------------------------------------------------------
# Independent review of PR #1155 (2026-09-16) found that the first cut of the
# value-only scan opened two NEW leak channels:
#   D1 -- the prose skip was broader than the defect AND skipped whole subtrees,
#         so `speaker_notes` (delivered content, first-class in this department)
#         passed with a live price ladder inside it;
#   D2 -- dropping the key scan lost the AFFIRMATIVE case, so a producer asserting
#         `{"offer_price_ladder_included": true}` passed silently.
# These pin the closure of both, alongside the false positives the rewrite exists
# to remove -- so neither direction can regress unnoticed.
# ---------------------------------------------------------------------------

def _hits(tmp_path: Path, obj: object) -> list:
    p = tmp_path / "arc.json"
    p.write_text(json.dumps(obj))
    low = [s.lower() for s in bd._pitch_scan_texts(p)]
    return [t for t in bd.PITCHLESS_FORBIDDEN_TOKENS if any(t in s for s in low)]


@pytest.mark.parametrize("obj,label", [
    ({"speaker_notes": "Buy now: price ladder tier 2 is $2997, act now."},
     "D1a speaker_notes carries delivered content"),
    ({"speaker_notes": {"section_id": "price_ladder", "move_tag": "BUY_NOW"}},
     "D1b a prose-named key must not skip its subtree"),
    ({"offer_price_ladder_included": True}, "D2a affirmative key"),
    ({"price_ladder_section": {"rung_1": "$997"}}, "D2b affirmative nested key"),
    ({"non_applicable_sections": {"price_ladder_section": "Tier 1 $997"}},
     "D2c affirmative key under a container"),
])
def test_review_leak_channels_still_fail(tmp_path, obj, label):
    assert _hits(tmp_path, obj), f"leak escaped: {label}"


@pytest.mark.parametrize("obj,label", [
    ({"offer_price_ladder": None}, "null-valued schema key"),
    ({"offer_price_ladder_reason": "avoided the price ladder"}, "denial prose"),
    ({"peak_apex": {"note": "no anchor price here"}}, "nested denial note"),
    ({"non_applicable_sections": {"reason": "pitch suppressed"}}, "container of denial prose"),
    ({"validation_notes": ["no offer, price, ladder, VIP, or re-pitch content"]},
     "list of denial prose"),
])
def test_review_false_positives_stay_clean(tmp_path, obj, label):
    assert not _hits(tmp_path, obj), f"false positive returned: {label}"


# ---------------------------------------------------------------------------
# SECOND independent review of PR #1155 (2026-09-16) found that the D1/D2 fix
# itself opened THREE new FAIL->PASS channels, all reproduced before repair:
#   ESC1 -- normalising the key (`str(k).replace("_"," ")`) turned
#           `re_pitch_section` into "re pitch section", which matches no token
#           (the tuple holds "re-pitch"/"re_pitch"/"repitch"), so the re-pitch
#           family stopped being caught: a regression against origin/main.
#   ESC2 -- the blanket `*_note`/`*_notes` prose catch-all swallowed
#           content-bearing KEYS (`price_ladder_notes`, `offer_notes`), and
#           `_PITCH_SCAN_CONTENT_FIELDS` listed only PLURAL note fields while the
#           department's canonical delivered field is singular `presenter_note`.
#   ESC3 -- a prose key holding a LIST of dicts skipped the whole list, though a
#           prose key holding a bare dict was walked (asymmetric).
# These pin the closure of all three, plus the false positives that must survive.
# ---------------------------------------------------------------------------

def _hits(tmp_path: Path, obj: object) -> list:
    p = tmp_path / "arc.json"
    p.write_text(json.dumps(obj))
    low = [s.lower() for s in bd._pitch_scan_texts(p)]
    return [t for t in bd.PITCHLESS_FORBIDDEN_TOKENS if any(t in s for s in low)]


@pytest.mark.parametrize("obj,label", [
    ({"re_pitch_section": {"slide_count": 3}}, "ESC1 key normalisation must not lose re-pitch"),
    ({"re_pitch": {"x": 1}}, "ESC1b bare re_pitch key"),
    ({"price_ladder_notes": "Tier 1 $997, Tier 2 $2997"}, "ESC2 *_notes is not prose when the key names a token"),
    ({"offer_notes": "Buy now, act now."}, "ESC2c offer_notes"),
    ({"anchor_price_note": "$4997 anchored"}, "ESC2d anchor_price_note"),
    ({"presenter_note": "price ladder tier 2 is $2997"}, "ESC2b singular presenter_note is delivered content"),
    ({"speaker_note": "act now, buy now"}, "ESC2e singular speaker_note"),
    ({"validation_notes": [{"section_id": "price_ladder"}]}, "ESC3 list of dicts under a prose key"),
    ({"peak_apex": {"note": [{"price_ladder_section": {"rung_1": "$997"}}]}}, "ESC3b nested list of dicts"),
    ({"validation_notes": ["prose", {"move_tag": "BUY NOW"}]}, "ESC3c mixed prose + dict list"),
])
def test_second_review_escapes_are_closed(tmp_path, obj, label):
    assert _hits(tmp_path, obj), f"leak escaped: {label}"


@pytest.mark.parametrize("obj,label", [
    ({"offer_price_ladder": None}, "null-valued schema key"),
    ({"offer_price_ladder_reason": "avoided the price ladder"}, "*_reason stays prose"),
    ({"non_applicable_sections": {"reason": "pitch suppressed"}}, "nested exact reason"),
    ({"peak_apex": {"note": "no anchor price here"}}, "exact note stays prose"),
    ({"validation_notes": ["no offer, price, ladder, VIP, or re-pitch content"]},
     "list of prose under validation_notes"),
])
def test_second_review_false_positives_survive(tmp_path, obj, label):
    assert not _hits(tmp_path, obj), f"false positive returned: {label}"
