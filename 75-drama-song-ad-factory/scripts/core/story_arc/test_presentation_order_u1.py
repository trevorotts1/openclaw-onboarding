#!/usr/bin/env python3
"""S75X-W2-U1: explicit PRESENTATION order, consequence-first.

Covers: the twelve canonical beats stay the causal contract (same ids, same
order, all twelve required -- no validator relaxed, no scene relabelled); a
consequence-first presentation is accepted when it is EXPLICIT data and the
script, performed lines and shot sequence agree; the same record is refused
when a beat is dropped, duplicated, invented, when a view disagrees, when the
opening/rewind is inconsistent, and when a beat cannot state its five parts;
and the performed-beat manifest is emitted in the presented order so the
performed lines reconcile with the script and the shots.

Run: python3 -m pytest -q 75-drama-song-ad-factory/scripts/core/story_arc/test_presentation_order_u1.py
stdlib only, no network, no spend.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # scripts/core/story_arc
CORE = HERE.parent                              # scripts/core
sys.path.insert(0, str(CORE))

import story_arc.story_arc as SA                 # noqa: E402

#: Consequence-first: the outcome is shown, then the telling rewinds.
CONSEQUENCE_FIRST = ["vindication", "ordinary_world", "humiliation", "wound_deepens",
                     "frozen", "seeing_it_too", "failed_solutions", "mentor",
                     "product_intro", "doubt", "climb", "return_cta"]

STATEMENT = {
    "action": "she sets the last statement down and stops apologising",
    "change": "the debt stops growing",
    "understood": "the turn she described is the reason the bill is gone",
    "question": "how did she get from the kitchen table to here",
    "carrier": "close on the paid stamp, then her hands going still",
}

def _rows():
    """One five-part statement per canonical beat."""
    return [dict(STATEMENT, story_beat_id=b) for b in SA.BEATS]

def _story(order=None, **over):
    story = {"story_id": "demo-arc-01", "beats": list(SA.BEATS),
             "product_reveal": 8, "story_beats": _rows()}
    if order is not None:
        story["presentation"] = {
            "order": list(order),
            "script": list(order),
            "performed": [{"beat": b} for b in order],
            "shots": [{"beat": b, "shot_id": "s%02d" % i} for i, b in enumerate(order)],
            "opening": order[0],
            "rewind_to": SA.DEFAULT_REWIND_TO,
        }
    story.update(over)
    return story

def _codes(story, purpose=None):
    return [e["error"] for e in SA.validate_story(story, purpose=purpose)["errors"]]

# --- the canonical contract is not relaxed --------------------------------

def test_undeclared_presentation_is_judged_exactly_as_before():
    story = SA.load_fixture("valid.json")
    assert not SA.declares_presentation(story)
    assert SA.presentation_order(story) == SA.BEATS
    assert SA.validate_story(story)["outcome"] == "ok"
    assert SA.selftest() == 0

def test_declared_presentation_still_requires_canonical_causal_order():
    shuffled = list(SA.BEATS)
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    r = SA.validate_story(_story(CONSEQUENCE_FIRST, beats=shuffled))
    assert r["outcome"] == "rejected", r
    assert "beat-order" in [e["error"] for e in r["errors"]], r

def test_relabelling_a_beat_is_refused_never_a_way_to_pass():
    relabelled = [("the_win" if b == "vindication" else b) for b in SA.BEATS]
    codes = _codes(_story(CONSEQUENCE_FIRST, beats=relabelled))
    assert "beat-unknown" in codes, codes

def test_all_twelve_beats_stay_required_in_the_presentation():
    dropped = [b for b in CONSEQUENCE_FIRST if b != "frozen"]
    r = SA.validate_story(_story(dropped))
    assert r["outcome"] == "rejected", r
    assert "presentation-missing" in [e["error"] for e in r["errors"]], r
    assert SA.validate_story(_story(dropped + ["frozen"]))["outcome"] == "ok"

def test_duplicate_and_invented_beats_are_refused():
    dup = list(CONSEQUENCE_FIRST)
    dup[1] = "vindication"
    assert "presentation-duplicate" in _codes(_story(dup))
    assert "presentation-missing" in _codes(_story(dup))
    invented = list(CONSEQUENCE_FIRST)
    invented[3] = "victory_lap"
    assert "presentation-unknown" in _codes(_story(invented))

# --- consequence-first presentation accepted -------------------------------

def test_consequence_first_presentation_is_accepted_as_explicit_data():
    story = _story(CONSEQUENCE_FIRST)
    r = SA.validate_story(story)
    assert (r["outcome"], r["reason_code"]) == ("ok", "story-valid"), r
    # stable ids and causal order survive: only the presentation moved
    assert r["beats"] == list(SA.BEATS)
    assert SA.presentation_order(story) == tuple(CONSEQUENCE_FIRST)
    chk = SA.check_presentation_order(story)
    assert chk["outcome"] == "ok", chk
    assert chk["consequence_first"] is True
    assert chk["opening"] == "vindication"
    assert chk["rewind_to"] == "ordinary_world"
    assert chk["statement_count"] == 12
    assert sorted(chk["order"]) == sorted(SA.BEATS)

def test_views_reconcile_script_performed_and_shots_together():
    chk = SA.check_presentation_order(_story(CONSEQUENCE_FIRST))
    assert set(chk["views"]) == {"script", "performed", "shots"}
    for view in SA.PRESENTATION_VIEWS:
        assert chk["views"][view] == chk["order"], (view, chk["views"][view])

def test_a_disagreeing_view_is_refused():
    story = _story(CONSEQUENCE_FIRST)
    story["presentation"]["shots"] = list(SA.BEATS)     # shots still canonical
    r = SA.validate_story(story)
    assert r["outcome"] == "rejected", r
    assert "presentation-view-mismatch" in [e["error"] for e in r["errors"]], r

def test_opening_and_rewind_must_be_consistent():
    story = _story(CONSEQUENCE_FIRST)
    story["presentation"]["opening"] = "ordinary_world"
    assert "presentation-opening-invalid" in _codes(story)
    story = _story(CONSEQUENCE_FIRST)
    story["presentation"]["rewind_to"] = "no_such_beat"
    assert "presentation-opening-invalid" in _codes(story)
    story = _story(CONSEQUENCE_FIRST)
    story["presentation"]["rewind_to"] = "vindication"   # the opening itself
    assert "presentation-opening-invalid" in _codes(story)

def test_every_beat_must_state_its_five_parts():
    story = _story(CONSEQUENCE_FIRST)
    story["story_beats"] = [r for r in story["story_beats"]
                            if r["story_beat_id"] != "mentor"]
    r = SA.validate_story(story)
    assert "beat-statement-missing" in [e["error"] for e in r["errors"]], r
    detail = next(e["detail"] for e in r["errors"] if e["error"] == "beat-statement-missing")
    assert detail.startswith("mentor: "), detail
    for field in SA.BEAT_STATEMENT_FIELDS:
        assert field in detail, (field, detail)

def test_one_blank_statement_field_is_named():
    story = _story(CONSEQUENCE_FIRST)
    story["story_beats"][4]["carrier"] = "   "
    r = SA.validate_story(story)
    detail = next(e["detail"] for e in r["errors"] if e["error"] == "beat-statement-missing")
    assert detail.startswith("%s: carrier" % SA.BEATS[4]), detail

def test_a_toplevel_script_or_shot_plan_is_not_mistaken_for_a_view():
    # a top-level `script`/`shots` means something else in this factory: only
    # the views INSIDE the presentation block are reconciled.
    story = _story(CONSEQUENCE_FIRST)
    story["script"] = ["scene one", "scene two"]
    story["shots"] = [{"shot_id": "s01", "seconds": 3.0}]
    assert SA.validate_story(story)["outcome"] == "ok"
    assert set(SA.check_presentation_order(story)["views"]) == {"script", "performed", "shots"}

# --- performed lines and the manifest --------------------------------------

def _source():
    """One approved line per beat, in canonical order."""
    return {b: {"lines": ["%s line" % b], "delivery": "sung", "pace": "mid"}
            for b in SA.BEATS}

def _heard(order, step=10.0):
    words, t = [], 0.0
    for beat in order:
        for tok in ("%s line" % beat).split():
            words.append({"word": tok, "startS": t, "endS": t + 0.5})
            t += 1.0
        t += step
    return words

def test_manifest_row_order_defaults_to_canonical_and_is_unchanged():
    m = SA.build_manifest(_source())
    assert [r["beat"] for r in m["beats"]] == list(SA.BEATS)
    assert m["presentation_order"] == list(SA.BEATS)
    assert m["consequence_first"] is False
    assert [r["causal_position"] for r in m["beats"]] == list(range(1, 13))
    assert [r["presentation_position"] for r in m["beats"]] == list(range(1, 13))
    assert m["present_count"] == 12 and m["missing"] == []

def test_manifest_follows_the_presented_order_with_stable_ids():
    m = SA.build_manifest(_source(), presentation=["vindication"] + CONSEQUENCE_FIRST[1:])
    assert [r["beat"] for r in m["beats"]] == CONSEQUENCE_FIRST
    assert m["consequence_first"] is True
    positions = {r["beat"]: (r["causal_position"], r["presentation_position"])
                 for r in m["beats"]}
    assert positions["vindication"] == (11, 1)
    assert positions["ordinary_world"] == (1, 2)
    assert sorted(r["beat"] for r in m["beats"]) == sorted(SA.BEATS)

def test_manifest_refuses_a_malformed_presentation():
    for bad in ([], ["vindication"], list(SA.BEATS) + ["vindication"]):
        try:
            SA.build_manifest(_source(), presentation=bad)
        except SA.StoryArcError:
            continue
        raise AssertionError("accepted a malformed presentation: %r" % (bad,))

def test_performed_lines_reconcile_with_the_presented_order():
    story = _story(CONSEQUENCE_FIRST)
    m = SA.build_manifest(_source(), presentation=story["presentation"])
    binding = SA.bind_revision("rev-presented", m)
    r = SA.check_performed_manifest(m, binding, _heard(CONSEQUENCE_FIRST))
    assert r["verdict"] == "PASS", r
    assert r["heard_beats"] == CONSEQUENCE_FIRST, r

def test_performing_the_canonical_order_under_a_presented_sheet_is_refused():
    story = _story(CONSEQUENCE_FIRST)
    m = SA.build_manifest(_source(), presentation=story["presentation"])
    binding = SA.bind_revision("rev-presented", m)
    # the take is sung in causal order, not the order the sheet presents
    r = SA.check_performed_manifest(m, binding, _heard(list(SA.BEATS)))
    assert r["verdict"] == "FAIL", r
    assert "BEAT_REORDERED" in r["failed"], r

def test_presentation_changes_the_creative_fingerprint():
    a = SA.build_manifest(_source())
    b = SA.build_manifest(_source(), presentation=CONSEQUENCE_FIRST)
    assert a["fingerprint"] != b["fingerprint"]
    assert list(SA.BEATS) == [r["beat"] for r in a["beats"]]
