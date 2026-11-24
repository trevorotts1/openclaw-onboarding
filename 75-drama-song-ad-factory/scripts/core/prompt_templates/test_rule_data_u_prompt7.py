#!/usr/bin/env python3
"""Guard: the Emotion Track and animation rule data files exist and are whole.

Asserts (a) expression-rules.json carries every one of the ten section 3G.1
emotions, each with the three beat-sheet columns, a cues line and a
contradiction list whose words never appear in that emotion's own cues; (b)
the seven fixed expression sheets are named; (c) animation-rules.json carries
the eleven section 3L.1 rules, the four camera speed words and the H8 move
lengths. A missing emotion or a truncated rule list fails here.

Stdlib only, offline, no spend.
Run: python3 scripts/core/prompt_templates/test_rule_data_u_prompt7.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
REF = os.path.join(ROOT, "references", "prompt-templates")

EMOTIONS = ("pain", "worry", "exhaustion", "anger", "hope", "relief", "joy",
            "pride", "tenderness", "resolve")
SHEETS = {"neutral", "sad", "worried", "tired", "hopeful", "joyful",
          "determined"}

FS = []


def check(name, cond, detail=""):
    print(("ok " if cond else "FAIL ") + name +
          ((" -- %s" % (detail,)) if detail and not cond else ""))
    if not cond:
        FS.append(name)


def test_rule_data():
    expr = json.load(open(os.path.join(REF, "expression-rules.json")))
    emo = expr.get("emotions") or {}
    check("1: all ten emotions present", set(emo) == set(EMOTIONS),
          sorted(set(EMOTIONS) ^ set(emo)))
    for e in EMOTIONS:
        row = emo.get(e) or {}
        check("2: %s carries cues, smile, teeth" % e,
              isinstance(row.get("cues"), str) and "smile" in row
              and "teeth" in row)
        cont = row.get("contradicts") or []
        check("3: %s names contradicting words" % e, len(cont) >= 3)
        low = (row.get("cues") or "").lower()
        bad = [w for w in cont if w.lower() in low]
        check("4: %s lists no word its own cues use" % e, not bad, bad)
    check("5: beat-sheet columns are the three 3G.1 names",
          expr.get("beat_sheet_columns") == ["emotion", "intensity",
                                             "facial_cues"])
    check("6: refusals name EXPRESSION_MISSING and EXPRESSION_CONTRADICTS",
          {"EXPRESSION_MISSING", "EXPRESSION_CONTRADICTS"} <=
          set(expr.get("refusals") or {}))
    check("7: no lip-sync prompt is ever sent",
          "no prompt" in (expr.get("note") or "").lower())
    sheets = [s for s in (expr.get("expression_sheets") or [])]
    check("8: the seven fixed expression sheets are named",
          set(sheets) == SHEETS, sheets)
    mapped = set((expr.get("expression_sheet_map") or {}).values())
    check("9: every emotion maps to a sheet (angry is made on demand)",
          set(EMOTIONS) <= set(expr.get("expression_sheet_map") or {}))

    anim = json.load(open(os.path.join(REF, "animation-rules.json")))
    rules = anim.get("rules") or []
    check("10: the eleven 3L.1 animation rules are present", len(rules) == 11,
          len(rules))
    check("11: the four camera speed words are named",
          set(anim.get("camera_speed_words") or {}) ==
          {"very slow", "slow", "steady", "brisk"})
    ml = anim.get("camera_move_length") or {}
    check("12: H8 move lengths are 6 / 8-10 / 15 s",
          ml.get("any_move_min_s") == 6
          and ml.get("slow_move_across_room_choir_group_s") == [8, 10]
          and ml.get("move_is_the_point_max_s") == 15)
    check("13: the stillness sentence is refused for performance clips",
          "never carries a stillness instruction"
          in (anim.get("no_stillness_sentence") or "").lower())

    print()
    if FS:
        print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    test_rule_data()
