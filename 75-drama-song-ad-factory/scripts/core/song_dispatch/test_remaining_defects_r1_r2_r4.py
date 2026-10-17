#!/usr/bin/env python3
"""CPR remaining defects R1/R2/R4 on the dispatch seam. Zero network, zero spend.

Proves:
  R4 (hook plan forwarded): validate_request honors a plan carried on the
     REQUEST as ``_hook_plan`` and a plan passed as the argument, still refuses
     a genuinely bad plan, and song_choices attaches it BEFORE the pre-spend
     validation (a bad plan raises ChoiceError, not a paid generation).
  R2 (strict duration): the admitted request duration EQUALS the plan's
     delivered seconds; the bare 15 percent Suno headroom is refused unless the
     owner selected it on the plan, and then the override is recorded, not
     silently dropped. The headroom FORMULA is unchanged.
  R1 (pace coverage): validate_request FAILS when either approved pace
     direction is removed from the final style, reading the order from the
     argument OR the request's ``_pace_plan``; the audio thresholds are the
     same numbers (0.30 onset share, 3.0 dB).

Run: python3 core/song_dispatch/test_remaining_defects_r1_r2_r4.py
     (from scripts/core). Exit 0 = all pass, 1 = failures.
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr

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
import music_qc.pace_change as PC    # noqa: E402
from song_choices import song_choices as SC   # noqa: E402
from song_dispatch import song_dispatch as SD   # noqa: E402
import suno_recipe as R              # noqa: E402
from sung_hook import hook_placement as HP    # noqa: E402
import words_fit as WF               # noqa: E402

FIX = os.path.join(CORE, "sung_hook", "fixtures")


def _j(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


RUN = _j("gala-48s-approved.json")
SID, D, CLIENT = RUN["style_id"], RUN["length_s"], RUN["sheet_text"]
SHEET = R.parse_lyrics(CLIENT)
GOOD_HP = RUN["hook_plan"]
BAD_HP = {"true_at_beat": "call_to_action"}     # hooks sit far earlier: a real refusal
PACE = dict(RUN["pace_plan"])

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % (detail,)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def req(pace=True, duration=None):
    r = R.build_request(SID, SHEET, CLIENT, "T", D, hook_plan=GOOD_HP,
                        pace_plan=PACE if pace else None)
    if duration is not None:
        r = dict(r, input=dict(r["input"], duration=duration))
    return r


# ---- R4: the hook plan is forwarded, and forwarded BEFORE spend -----------
base = req()
check("R4 control: the approved hook plan passes validate_request",
      SD.validate_request(base, SID, CLIENT, D, pace_plan=PACE) == [],
      SD.validate_request(base, SID, CLIENT, D, pace_plan=PACE))
# A bad plan is genuinely refused by the hook gates (the plan is real input).
check("R4 a genuinely bad plan is refused by the hook gate",
      bool(HP.check_story(SHEET, BAD_HP, D, SID)) and not HP.check_story(SHEET, GOOD_HP, D, SID),
      (HP.check_story(SHEET, BAD_HP, D, SID), HP.check_story(SHEET, GOOD_HP, D, SID)))
# validate_request must HAND the plan to check_lyric_sheet (the pre-spend gate).
_seen = []
_real = R.check_lyric_sheet


def _spy(*a, **kw):
    _seen.append(kw.get("hook_plan"))
    return _real(*a, **kw)


R.check_lyric_sheet = _spy
try:
    by_request = dict(base, _hook_plan=BAD_HP)
    SD.validate_request(by_request, SID, CLIENT, D, pace_plan=PACE)
    check("R4 a plan carried as _hook_plan reaches the pre-spend sheet check",
          _seen[-1] == BAD_HP, _seen[-1])
    SD.validate_request(base, SID, CLIENT, D, pace_plan=PACE, hook_plan=BAD_HP)
    check("R4 a plan passed as the argument reaches the pre-spend sheet check",
          _seen[-1] == BAD_HP, _seen[-1])
    SD.validate_request(base, SID, CLIENT, D, pace_plan=PACE)
    check("R4 no plan anywhere stays None (never a silent stand-in)",
          _seen[-1] is None, _seen[-1])
finally:
    R.check_lyric_sheet = _real
ok_meta = SD.validate_request(dict(base, _hook_plan=GOOD_HP), SID, CLIENT, D, pace_plan=PACE)
check("R4 the approved plan carried on the request still passes", ok_meta == [], ok_meta)
# song_choices must attach BOTH plans BEFORE it validates (a plan attached after
# validation is a gate that never runs: the pre-spend call saw None).
_seen_val = []
_real_val = SD.validate_request


def _val_spy(rq, *a, **kw):
    _seen_val.append((rq.get("_hook_plan"), kw.get("pace_plan")))
    return _real_val(rq, *a, **kw)


SD.validate_request = _val_spy
try:
    rows = SC.build_requests(SID, SHEET, CLIENT, "T", D, hook_plan=GOOD_HP, pace_plan=PACE)
finally:
    SD.validate_request = _real_val
check("R4 song_choices attaches _hook_plan BEFORE validate_request",
      len(_seen_val) == 3 and all(hp == GOOD_HP for hp, _pp in _seen_val), _seen_val)
check("R1 song_choices supplies the pace order BEFORE validate_request",
      len(_seen_val) == 3 and all(pp == PACE for _hp, pp in _seen_val), _seen_val)
check("R4 the built requests still carry _hook_plan for the judge",
      all(r.get("_hook_plan") == GOOD_HP for _v, r in rows) and len(rows) == 3)

# ---- R2: exact delivered duration; explicit, recorded owner override ------
plan = dict(LF.plan(D + LF.END_EARLY_S), sheet_text=CLIENT, style_id=SID,
            hook_plan=GOOD_HP, pace_change=PACE)
headroom = WF.max_suno_duration(plan["delivered_s"])
check("R2 headroom formula unchanged (48 s plan -> 56 s request)",
      (round(WF.suno_duration_s(48.0), 6), headroom) == (55.2, 56),
      (WF.suno_duration_s(48.0), headroom))
sent = []
out = SD.run_takes(dict(base, input=dict(base["input"], duration=plan["delivered_s"])), plan,
                   lambda rq: sent.append(rq) or [], lambda t: {}, lambda t, r: None,
                   CLIENT, "x", cap_cents=6)
check("R2 the exact delivered duration is admitted",
      out["duration"] == {"requested_s": plan["delivered_s"],
                          "delivered_target_s": plan["delivered_s"], "mode": "exact"},
      out["duration"])
before = list(sent)
try:
    SD.run_takes(dict(base, input=dict(base["input"], duration=headroom)), plan,
                 lambda rq: sent.append(rq) or [], lambda t: {}, lambda t, r: None,
                 CLIENT, "x", cap_cents=6)
    check("R2 the bare 15 percent headroom is refused before any spend", False, "admitted")
except SD.DispatchError as e:
    check("R2 the bare 15 percent headroom is refused before any spend",
          "duration_headroom_approved" in str(e) and sent == before, str(e))
approved = dict(plan, duration_headroom_approved={"owner": "trevor", "reason": "self-check"})
err = io.StringIO()
with redirect_stderr(err):
    out_ok = SD.run_takes(dict(base, input=dict(base["input"], duration=headroom)), approved,
                          lambda rq: [], lambda t: {}, lambda t, r: None,
                          CLIENT, "x", cap_cents=6)
check("R2 an owner-selected override is honored and recorded",
      out_ok["duration"]["mode"] == "headroom_override"
      and out_ok["duration"]["headroom_approved"] == approved["duration_headroom_approved"]
      and "DURATION_HEADROOM_OVERRIDE" in err.getvalue(), out_ok["duration"])

# ---- R1: both pace directions are required; thresholds untouched ----------
good_style = base["input"]["style"]
check("R1 control: a style carrying both directions passes",
      SD.validate_request(base, SID, CLIENT, D, pace_plan=PACE) == [])
for part in ("drop", "return"):
    bad = dict(base, input=dict(base["input"], style=good_style.replace(PACE[part], "")))
    errs = SD.validate_request(bad, SID, CLIENT, D, pace_plan=PACE)
    check("R1 a removed %s direction is refused" % part,
          any("PACE_DIRECTION_MISSING" in e and part in e for e in errs), errs)
    keyed = dict(bad, _pace_plan=PACE)
    errs = SD.validate_request(keyed, SID, CLIENT, D)      # request key only
    check("R1 the request's _pace_plan alone still catches the %s removal" % part,
          any("PACE_DIRECTION_MISSING" in e and part in e for e in errs), errs)
check("R1 pace audio thresholds untouched (0.30 onset share, 3.0 dB drop/return)",
      (PC.PACE_ONSET_REDUCTION, PC.PACE_ENERGY_DROP_DB, PC.PACE_RETURN_DB) == (0.30, 3.0, 3.0),
      (PC.PACE_ONSET_REDUCTION, PC.PACE_ENERGY_DROP_DB, PC.PACE_RETURN_DB))

print()
if FAILS:
    print("FAILED: %d" % len(FAILS))
    for f in FAILS:
        print("  - %s" % f)
    sys.exit(1)
print("PASS remaining defects R1/R2/R4 self-check")
