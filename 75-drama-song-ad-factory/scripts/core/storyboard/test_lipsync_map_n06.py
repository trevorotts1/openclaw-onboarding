#!/usr/bin/env python3
"""test_lipsync_map_n06.py: the lip-sync map carries one of the five labels.

Run: python3 scripts/core/storyboard/test_lipsync_map_n06.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from storyboard import lipsync_map as M      # noqa: E402

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        "" if cond else "  <- %r" % (detail,)))
    if not cond:
        FAILS.append(name)

def row(**kw):
    base = {"shot_id": "T1", "song_start": 0.0, "song_end": 6.0,
            "speaker": "Ava", "character_ids": ["Ava", "choir-member-1"],
            "lyric_line_ids": ["L1"], "route": "omnihuman", "lip_sync": True}
    base.update(kw)
    return base

def pic(**kw):
    base = row(**kw)
    base["picture_faces"] = [{"character": "Ava", "role": "lead", "place": 0},
                             {"character": "choir-1", "role": "backing",
                              "place": 1}]
    return base

VOICE_MAP = [{"start_s": 0.0, "end_s": 10.0, "singers": ["ava", "choir-1"]}]

def test_n06_n117():
    del FAILS[:]
    # N-06: a plan of lines with no map is refused before any spend.
    check("N-06 a plan of lines with no map is refused",
          [f["code"] for f in M.check_map([row()])] == ["LIPSYNC_MAP_MISSING"],
          M.check_map([row()]))

    # The plan's own example: Ava alone with the choir behind is the lead.
    out = M.build_map([row()], lead_id="Ava")
    check("N-06 the lead beside a choir row is the lead", out["outcome"] == "pass"
          and out["pieces"][0]["label"] == "lead", out)

    # Section 3.3's choir label: ensemble hook lines are sung by the choir.
    out = M.build_map([row(shot_id="T17", speaker="choir")])
    check("N-06 a choir line is the choir label",
          out["pieces"][0]["label"] == "choir", out)

    # Section 3.3's over-picture label: nobody mouths it.
    out = M.build_map([row(shot_id="T27", speaker="narrator-voiceover",
                           lip_sync=False, route="h3_start_end")])
    check("N-06 a voice-over line plays over the picture",
          out["pieces"][0]["label"] == "over picture", out)

    # Another named character is the other-speaker label.
    out = M.build_map([row(shot_id="T05", speaker="choir-member-1",
                           character_ids=["choir-member-1"],
                           lipsync_label="lead inside the choir")])
    check("N-06 a declared label is kept",
          out["pieces"][0]["label"] == "lead inside the choir", out)

    # A speaker absent from the cast earns no label at all.
    out = M.build_map([row(shot_id="T17", speaker="Ava",
                           character_ids=["choir-member-1", "choir-member-2"])])
    check("N-06 an absent singer earns no label",
          out["outcome"] == "fail"
          and out["findings"][0]["code"] == "LIPSYNC_MAP_LABEL_MISSING", out)

    # Every label the map writes is one of the five.
    out = M.build_map([row(), row(shot_id="T17", speaker="choir"),
                       row(shot_id="T27", speaker="narrator-voiceover",
                           lip_sync=False, route="h3_start_end")],
                      lead_id="Ava")
    check("N-06 every written label is one of the five",
          all(p["label"] in set(M.LABELS) for p in out["pieces"])
          and sorted(out["by_label"]) == sorted(M.LABELS), out["by_label"])

    # A wordless story shot is not a line and carries no label.
    out = M.build_map([{"shot_id": "T09", "song_start": 8.0, "song_end": 12.0,
                        "visual_objective": "the empty kitchen"}])
    check("N-06 a wordless story shot carries no label", out["pieces"] == [], out)

    # --- N-117 (story half): the lip-sync picture record, section 3N.3 ----

    check("N-117 exactly the singers in the picture passes",
          M.check_picture_faces([pic()], VOICE_MAP) == [],
          M.check_picture_faces([pic()], VOICE_MAP))

    # A silent person kept in the frame is refused: 3N.3 says not in the picture.
    silent = pic()
    silent["picture_faces"].append({"character": "ruth", "role": "backing",
                                    "place": 2})
    codes = [f["code"] for f in M.check_picture_faces([silent], VOICE_MAP)]
    check("N-117 a face the map does not sing is refused",
          codes == ["LIPSYNC_WRONG_FACES"], codes)

    # A lip-sync picture with no record at all is refused before any spend.
    bare = row()
    codes = [f["code"] for f in M.check_picture_faces([bare], VOICE_MAP)]
    check("N-117 a picture with no face record is refused",
          codes == ["LIPSYNC_PICTURE_RECORD_INCOMPLETE"], codes)

    # The record must name each face's role, and its place left to right.
    bad = pic()
    bad["picture_faces"][1]["role"] = "extra"
    codes = [f["code"] for f in M.check_picture_faces([bad], VOICE_MAP)]
    check("N-117 a face with no lead or backing role is refused",
          codes == ["LIPSYNC_PICTURE_RECORD_INCOMPLETE"], codes)

    gap = pic()
    gap["picture_faces"][1]["place"] = 2
    codes = [f["code"] for f in M.check_picture_faces([gap], VOICE_MAP)]
    check("N-117 places must run left to right with no hole",
          codes == ["LIPSYNC_PICTURE_RECORD_INCOMPLETE"], codes)

    # A face record on a shot the map does not cover is not judged here.
    outside = pic(song_start=40.0, song_end=46.0)
    check("N-117 a stretch the map does not name is left to its own check",
          M.check_picture_faces([outside], VOICE_MAP) == [], "unexpected")

    assert not FAILS, FAILS


if __name__ == "__main__":
    test_n06_n117()
    print()
    print("FAILED: %d" % len(FAILS) if FAILS else "PASS: all checks")
    sys.exit(1 if FAILS else 0)
