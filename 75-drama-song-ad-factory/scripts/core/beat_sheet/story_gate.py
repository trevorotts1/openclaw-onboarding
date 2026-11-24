"""beat_sheet.story_gate -- Gate 2, the story gate (N-99, section 3J.3).

Plan 2A engine 5 and 3F.1: the spine and the Story Beats pass their own gate
first, no script row exists before that, then the joined story script runs
every check at once, and the section 3J levels decide what happens:

  MAJOR on item 8 to 12  the pictures are gated (3J.3 "Story checks and the
                         story review: items 8 to 12 are MAJOR and gate the
                         pictures")
  MEDIUM                 passes, is logged, and is listed for the run owner
  MINOR                  is counted only

Nothing here recomputes a check: it calls the modules that own each row and
levels their findings through ``story_severity``. One verdict, one place.

Stdlib only; data in, a verdict out; no model call, no write.
"""
from __future__ import annotations

from .beat_sheet import MAJOR, validate_story_beats
from .cast_completeness import completeness_gate
from .continuity import continuity_defects
from .emotion_tags import emotion_rows_defects
from .line_match import buried_event_defects, match_defects
from .script import check_script
from .singer import hook_defects, singer_defects
from .spine import join_sections, spine_gate
from .story_severity import classify, review_levels

__all__ = ["GATE", "story_gate", "selftest"]

GATE = "story"


def _row_list(script):
    rows = script.get("rows") if isinstance(script, dict) else script
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def story_gate(spine, beats, script, *, cast_ids=None, scene_ids=None,
               measured_lines=None, hook_lines=None, voice_map=None,
               lyric_sheet=None, review=None, section_lists=None,
               cold_reader=None, profiles=None, world_defects=None):
    """The whole story gate, in the plan's order. Returns one verdict dict.

    ``beats`` is the beats record (``{"beats": [...]}``); ``script`` the rows
    every section writer produced. ``world_defects`` is supplied by U-WORLD so
    the completeness gate reports one verdict (N-123).
    """
    spine_verdict = spine_gate(spine, cast_ids=cast_ids, scene_ids=scene_ids)
    beats_verdict = validate_story_beats(beats, measured_lines=measured_lines,
                                         hook_lines=hook_lines)
    # N-74 is a sequencing rule, not a 3J finding: any spine defect stops the
    # script rows, whatever its level.
    spine_ok = not spine_verdict["defects"]
    findings = list(spine_verdict["defects"]) + list(beats_verdict["defects"])

    joined = {"ok": False, "rows": [], "defects": []}
    if spine_ok and beats_verdict["ok"]:
        joined = join_sections(_row_list(script))
        written = {"rows": joined["rows"]}
        findings.extend(joined["defects"])
        findings.extend(check_script(written, beats,
                                     lyric_lines=measured_lines)["defects"])
        findings.extend(continuity_defects(written))
        findings.extend(singer_defects(written, voice_map=voice_map,
                                      lyric_sheet=lyric_sheet))
        findings.extend(hook_defects(written, hook_lines))
        findings.extend(match_defects(written))
        findings.extend(buried_event_defects(written))
        findings.extend(emotion_rows_defects(joined["rows"]))
        findings.extend(completeness_gate(beats, section_lists=section_lists,
                                          cold_reader=cold_reader,
                                          profiles=profiles,
                                          world_defects=world_defects)["defects"])

    reviewed = classify(review_levels(review)["major"]
                        + review_levels(review)["medium"]
                        + review_levels(review)["minor"]) if review else None
    if review:
        findings.extend(review_levels(review)["major"]
                        + review_levels(review)["medium"]
                        + review_levels(review)["minor"])

    levels = classify(findings)
    counts = {"MAJOR": len(levels["major"]), "MEDIUM": len(levels["medium"]),
              "MINOR": len(levels["minor"])}
    return {
        "gate": GATE,
        # A MAJOR anywhere stops the gate: items 8-12 gate the pictures and
        # item 15 (a check that could not run) fails closed (3J.1).
        "ok": not levels["major"],
        "blocks_pictures": levels["blocks_pictures"],
        "script_rows_allowed": spine_ok and beats_verdict["ok"],
        "row_count": len(joined["rows"]),
        "spine": spine_verdict,
        "beats": beats_verdict,
        "reviewed": bool(reviewed),
        "defects": levels["major"] + levels["medium"] + levels["minor"],
        "majors_outside_the_story_items": [
            d for d in levels["major"]
            if d.get("item") not in (8, 9, 10, 11, 12)],
        "owner_notes": levels["owner_notes"],
        "counts": counts,
    }


def selftest():
    """A clean run passes; a MISMATCH line and a missing spine gate the pictures."""
    beats = {"beats": [
        {"beat_number": 1, "name": "she opens the letter",
         "start_s": 0.0, "end_s": 8.0,
         "lyric_lines": [{"line_id": "l1", "text": "line one"}],
         "who": {"on_screen": ["c1"], "singing": ["c1"], "listening": [],
                 "else_seen": "nobody else is seen here"},
         "location_id": "kitchen", "time_of_day": "morning",
         "wardrobe": {"c1": "w1"}, "entrances": [], "exits": [],
         "emotion_start": {"emotion": "worry", "intensity": 2},
         "emotion_end": {"emotion": "resolve", "intensity": 2},
         "change": "a decision", "event": None,
         "props_change": [], "lip_sync_candidates": [{"line_id": "l1"}]},
    ]}
    spine = {"text": "word " * 320, "cast": ["c1"], "places_in_order": ["kitchen"],
             "time_of_day_by_scene": {"kitchen": "morning"},
             "wardrobe_by_scene": {"kitchen": {"c1": "w1"}}, "arc": "worry to resolve"}
    cues = {"eyes": "level", "brows": "set", "mouth": "firm",
            "smile": "no", "teeth": "no", "tears": "none"}
    row = {"row_id": "r1", "line_id": "l1", "beat_number": 1,
           "start_s": 0.0, "end_s": 8.0, "line": "line one", "who_sings": "c1",
           "singing": ["c1"], "on_screen": ["c1"], "location_id": "kitchen",
           "time_of_day": "morning", "wardrobe": {"c1": "w1"}, "lip_sync": True,
           "emotion": "resolve", "intensity": 2, "facial_cues": cues,
           "line_match": "MATCH"}

    verdict = story_gate(spine, beats, {"rows": [row]}, cast_ids=["c1"],
                         scene_ids=["kitchen"],
                         voice_map={"stretches": [
                             {"start_s": 0.0, "end_s": 8.0, "voice_id": "c1"}]})
    assert verdict["script_rows_allowed"], verdict["defects"]
    assert verdict["ok"], [d for d in verdict["defects"] if d["level"] == MAJOR]

    bad = dict(row, line_match="MISMATCH")
    mism = story_gate(spine, beats, {"rows": [bad]}, cast_ids=["c1"],
                      scene_ids=["kitchen"],
                      voice_map={"stretches": [
                          {"start_s": 0.0, "end_s": 8.0, "voice_id": "c1"}]})
    assert mism["blocks_pictures"], mism["counts"]
    assert not mism["ok"]

    thin = dict(spine, text="word " * 20)
    short = story_gate(thin, beats, {"rows": [row]}, cast_ids=["c1"],
                       scene_ids=["kitchen"])
    assert short["script_rows_allowed"] is False
    assert short["row_count"] == 0
    return True


if __name__ == "__main__":  # pragma: no cover
    assert selftest()
    print("beat_sheet.story_gate selftest: OK")
