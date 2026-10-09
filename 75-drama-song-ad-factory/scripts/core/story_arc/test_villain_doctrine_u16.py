#!/usr/bin/env python3
"""FU-U16 story doctrine tests: villain, pain, rise (Trevor order 2026-10-08).

    "People don't care about the hero until they meet the villain." - Trevor Otts

Covers: planner fails closed with no villain, fails closed when the villain
has no shot, pain share 10% -> FLAG, 28% -> PASS, the quote verbatim in
SKILL.md, and the checker's VILLAIN_DOCTRINE row.

Run: python3 scripts/core/story_arc/test_villain_doctrine_u16.py
pytest-collectable (stdlib only, no network, no spend).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # scripts/core/story_arc
CORE = HERE.parent                              # scripts/core
SKILL = HERE.parents[2]                         # the skill folder
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import length_formula.length_formula as LF        # noqa: E402
import delivery_checklist.delivery_checklist as DC  # noqa: E402

QUOTE_LINE = ('> "People don\'t care about the hero until they meet the villain."'
              ' - Trevor Otts')

RUNTIME = 60.0

def _villain_plan(**kw):
    plan = {"delivered_s": RUNTIME,
            "villain": {"name": "The second mortgage", "kind": "not_a_person"}}
    plan.update(kw)
    return plan

def _shot(tag, seconds):
    return {"shot_id": "s-%s" % tag, tag: True, "seconds": seconds}

def test_no_villain_fails():
    plan = {"delivered_s": RUNTIME}
    res = LF.plan_villain_doctrine(plan, [_shot("pain", 12.0),
                                          _shot("rise", 10.0)], [])
    assert res["verdict"] == "FAIL", res
    assert "NO_VILLAIN_NAMED" in res["fail_codes"], res

def test_villain_without_shot_fails():
    shots = [_shot("pain", 12.0), _shot("rise", 10.0)]   # no villain shot
    res = LF.plan_villain_doctrine(_villain_plan(), shots, [])
    assert res["verdict"] == "FAIL", res
    assert "VILLAIN_HAS_NO_SHOT" in res["fail_codes"], res
    assert res["villain_seconds"] == 0.0, res
    res2 = LF.plan_villain_doctrine(_villain_plan(), [], [])
    assert res2["verdict"] == "FAIL", res2
    assert "VILLAIN_HAS_NO_SHOT" in res2["fail_codes"], res2

def test_pain_share_10_percent_flags():
    shots = [_shot("villain", 6.0), _shot("pain", 6.0), _shot("rise", 8.0)]
    res = LF.plan_villain_doctrine(_villain_plan(), shots, [])
    assert res["verdict"] == "FLAG", res
    assert res["pain_percent"] == 10.0, res
    assert res["pain_seconds"] == 6.0, res
    assert res["in_target"] is False, res
    assert res["fail_codes"] == [], res          # never a hard block
    assert res["blocking"] is False, res

def test_pain_share_28_percent_passes():
    shots = [_shot("villain", 8.0), _shot("pain", 16.8), _shot("rise", 9.0)]
    res = LF.plan_villain_doctrine(_villain_plan(), shots, [])
    assert res["verdict"] == "PASS", res
    assert res["pain_percent"] == 28.0, res
    assert res["in_target"] is True, res

def test_quote_verbatim_in_skill_md():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert QUOTE_LINE in text, "FU-U16 quote missing from SKILL.md"
    assert "not music videos" in text, "doctrine line missing from SKILL.md"

def test_checker_row_reports_villain():
    shots = [_shot("villain", 6.0), _shot("pain", 16.8)]
    lines = [{"text": "I couldn't breathe", "pain": True, "seconds": 3.0}]
    row = DC.measure_villain_doctrine(shots, lines, RUNTIME,
                                      {"name": "The second mortgage"})
    assert row["verdict"] in ("PASS", "FLAG"), row
    assert row["villain_shots"] == 1, row
    assert row["villain_seconds"] == 6.0, row
    assert row["pain_seconds"] == 19.8, row
    assert row["blocking"] is False, row
    assert "The second mortgage" in row["measurement"], row

def _main():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("ok: %s" % fn.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL: %s (%s)" % (fn.__name__, e))
    print("%d/%d passed" % (len(fns) - failed, len(fns)))
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(_main())
