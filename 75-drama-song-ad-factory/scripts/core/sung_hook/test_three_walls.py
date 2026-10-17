#!/usr/bin/env python3
"""Three-walls self-check (2026-10-17). No network, no spend.

    python3 core/sung_hook/test_three_walls.py

Fixtures are a real 48 s run (one brand token replaced): the approved sheet
and plan, Suno's own timed words WITH headers, and local transcription words
(no headers) of a take whose singer changed the hook words.

  A. hook_placement reads hook time from timed hook words when headers are
     absent; the same take read both ways gives the same first-hook second.
     Missing, partial or untrusted evidence stays UNMEASURED, never PASS.
  B. headers present but none a hook: FAIL, never a PASS with no first hook.
  C. validate_request refuses a final style missing either pace direction;
     run_takes checks the order the judge reads (pace_change or _pace_plan).
  D. duration: delivered target 48 s, exact request 48; headroom 56 recorded.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from sung_hook import hook_placement as HP            # noqa: E402
from song_dispatch import song_dispatch as SD          # noqa: E402
from length_formula import length_formula as LF        # noqa: E402
import suno_recipe as R                                # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def _j(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


RUN = _j("gala-48s-approved.json")
SUNO = _j("gala-48s-suno-aligned-headers.json")
LOCAL = _j("gala-48s-local-words.json")["words"]
SID, D, PLAN, SHEET = RUN["style_id"], RUN["length_s"], RUN["hook_plan"], RUN["sheet_text"]
SUNG = [{"delivery": "sung", "start": 4.7, "end": 42.8, "source": "measured"}]
BARE = [dict(w, word=re.sub(r"\[[^\]]*\]?|^[^\[]*\]", "", w["word"])) for w in SUNO]


def show(label, r):
    print("%-48s %s first=%s returned=%s %s" % (label, r["verdict"], r.get("first_hook_s"),
                                                r.get("hook_blocks_returned"), r["reasons"]))


# ---- A: header vs lexical on the same real take ---------------------------
hdr = HP.check_returned(SHEET, SUNO, SID, D, PLAN)
show("A0 Suno words WITH headers", hdr)
assert hdr["basis"] == "headers" and hdr["first_hook_s"] is not None
lex = HP.check_returned(SHEET, BARE, SID, D, PLAN, segments=SUNG)
show("A1 same words, headers stripped", lex)
assert lex["basis"] == "lexical" and lex["verdict"] == "PASS", lex
assert abs(lex["first_hook_s"] - hdr["first_hook_s"]) < 0.01, (lex, hdr)
late = HP.check_returned(SHEET, BARE, SID, D, {"true_at_beat": "the_turn"}, segments=SUNG)
show("A2 same take, later story beat", late)
assert late["verdict"] == "FAIL" and "before 'the_turn'" in late["reasons"][0], late
for label, words, segs in (("A3 no detector segments", BARE, None),
                           ("A4 aligned segments only", BARE,
                            [dict(SUNG[0], source="aligned")]),
                           ("A5 hook not sung (spoken segment)", BARE,
                            [dict(SUNG[0], delivery="spoken")]),
                           ("A6 time runs backwards", BARE[:30] + [dict(BARE[30], startS=1.0)]
                            + BARE[31:], SUNG),
                           ("A7 empty words", [], SUNG),
                           ("A8 local words, singer changed hook", LOCAL, SUNG)):
    r = HP.check_returned(SHEET, words, SID, D, PLAN, segments=segs)
    show(label, r)
    assert r["verdict"] == "FAIL" and r["reasons"][0].startswith("UNMEASURED"), (label, r)
one = BARE[:42]                                       # first hook only, second cut off
r = HP.check_returned(SHEET, one, SID, D, PLAN, segments=SUNG)
show("A9 one of two hooks heard", r)
assert r["verdict"] == "FAIL" and r["reasons"][0].startswith("UNMEASURED"), r
extra = BARE + [dict(w, startS=w["startS"] + 27, endS=w["endS"] + 27) for w in BARE[23:33]]
r = HP.check_returned(SHEET, extra, SID, D, PLAN,
                      segments=[dict(SUNG[0], end=60.0)])
show("A10 an extra sung hook", r)
assert r["verdict"] == "FAIL" and "3 hook blocks, the sheet has 2" in r["reasons"][0], r
# hook 1 sung straight after the vocalise: same words, reordered, retimed in order
order = BARE[:5] + BARE[23:33] + BARE[5:23] + BARE[33:]
early = [dict(w, startS=5.0 + i * 0.8, endS=5.6 + i * 0.8) for i, w in enumerate(order)]
r = HP.check_returned(SHEET, early, SID, D, PLAN, segments=[dict(SUNG[0], end=60.0)])
show("A11 first hook sung inside build-up", r)
assert r["verdict"] == "FAIL" and "inside the" in " ".join(r["reasons"]), r

# ---- B: headers present, none a hook --------------------------------------
nohook = [dict(w, word=w["word"].replace("[Hook 1", "[Bridge").replace("[Hook 2", "[Bridge"))
          for w in SUNO]
r = HP.check_returned(SHEET, nohook, SID, D, {"true_at_beat": "the_world"})
show("B0 headers, none a hook", r)
assert r["verdict"] == "FAIL" and any("no returned section header names a hook" in x
                                      for x in r["reasons"]), r
assert r["first_hook_s"] is None

# ---- C: pace directions at the request boundary ----------------------------
sheet = R.parse_lyrics(SHEET)
req = R.build_request(SID, sheet, SHEET, "T", D, hook_plan=PLAN, pace_plan=RUN["pace_plan"])
good = req["input"]["style"]
print("C0 emitted style tail:", good[-150:])
assert SD.validate_request(req, SID, SHEET, D, pace_plan=RUN["pace_plan"]) == []
for part in ("drop", "return"):
    bad = dict(req, input=dict(req["input"], style=good.replace(RUN["pace_plan"][part], "")))
    rt = json.loads(json.dumps(bad))                   # what the provider would receive
    errs = SD.validate_request(rt, SID, SHEET, D, pace_plan=RUN["pace_plan"])
    print("C1 %-6s removed, before=%r" % (part, SD._SCM.check_pace_style(good, RUN["pace_plan"])))
    print("   after=%r" % errs)
    assert any("PACE_DIRECTION_MISSING" in e and part in e for e in errs), errs
nopace = R.build_request(SID, sheet, SHEET, "T", D, hook_plan=PLAN)
plan = dict(LF.plan(D + LF.END_EARLY_S), sheet_text=nopace["input"]["lyrics"], style_id=SID,
            hook_plan=PLAN, _pace_plan=RUN["pace_plan"])
sent = []
try:
    SD.run_takes(nopace, plan, lambda rq: sent.append(rq) or [], lambda t: {},
                 lambda t, r: None, SHEET, "x", cap_cents=6)
    raise AssertionError("C2 run_takes sent a style with no pace direction")
except SD.DispatchError as e:
    print("C2 run_takes, order as _pace_plan, style without it:", str(e)[:110])
    assert "PACE_DIRECTION_MISSING" in str(e) and not sent

# ---- D: duration -----------------------------------------------------------
p = LF.plan(D + LF.END_EARLY_S)
print("D0 chosen %s -> delivered %s; request duration %s" % (p["chosen_length_s"],
                                                              p["delivered_s"],
                                                              req["input"]["duration"]))
assert p["delivered_s"] == 48 == req["input"]["duration"]
pace_req = R.build_request(SID, sheet, SHEET, "T", D, hook_plan=PLAN, pace_plan=RUN["pace_plan"])
plan = dict(plan, pace_change=RUN["pace_plan"])
out = SD.run_takes(pace_req, plan, lambda rq: [], lambda t: {}, lambda t, r: None,
                   SHEET, "x", cap_cents=6)
print("D1 exact:", out["duration"])
assert out["duration"] == {"requested_s": 48, "delivered_target_s": 48, "mode": "exact"}
err = io.StringIO()
with redirect_stderr(err):
    try:
        SD.run_takes(dict(pace_req, input=dict(pace_req["input"], duration=56)), plan,
                     lambda rq: [], lambda t: {}, lambda t, r: None, SHEET, "x", cap_cents=6)
        raise AssertionError("D2 the bare 15 percent headroom was admitted with no owner approval")
    except SD.DispatchError as e:
        print("D2 bare headroom refused:", str(e)[:90])
        assert "duration_headroom_approved" in str(e), e
# CPR-R2: an owner-selected headroom request is still honored, and RECORDED.
approved = dict(plan, duration_headroom_approved={"owner": "trevor", "reason": "self-check"})
err = io.StringIO()
with redirect_stderr(err):
    out = SD.run_takes(dict(pace_req, input=dict(pace_req["input"], duration=56)), approved,
                       lambda rq: [], lambda t: {}, lambda t, r: None, SHEET, "x", cap_cents=6)
print("D3 owner override:", out["duration"], "|", err.getvalue().strip()[:60])
assert out["duration"]["mode"] == "headroom_override" and "DURATION_HEADROOM_OVERRIDE" in err.getvalue()
assert out["duration"]["headroom_approved"] == approved["duration_headroom_approved"]
print("PASS three walls self-check")
