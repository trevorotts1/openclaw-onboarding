#!/usr/bin/env python3
"""AF-SHARE-U1 suite: D15 spoken-share retarget (45% target, 40-55 band).

Proves, stdlib only and with zero paid calls:
  1. The three numbers are 45 / 40 / 55 and nothing else -- no 0.70 ceiling,
     no per-length table survives in this package.
  2. The SAME band holds for every offered length (60/90/180/300/600) and
     every offered music style (Soul Ballad / R&B Flow / Soul Rise); rap
     counts as spoken-style delivery everywhere.
  3. The old 40-70 band and the old per-length targets are gone from the
     length engine surface (music_styles reads its numbers from here) and
     the old table names are not re-exported.
  4. The first sung line must start within about 10 seconds -- enforced by
     the planner-side rule, and by check_plan together with the band.
  5. Malformed input raises (caller bug); an out-of-band share is a FAIL
     verdict, never an exception.
  6. Hygiene: the package is stdlib only, no network, no provider/paid
     marker, no media file, no operator path.

Exit 0 = all pass, 1 = failures, 2 = tooling failure.
"""
from __future__ import annotations

import ast
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

import spoken_share as SS  # noqa: E402  (package under test)

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    except Exception as e:  # noqa: BLE001 - wrong exception is a failure
        print("  note: raised %s: %s" % (type(e).__name__, e))
        return None
    return None


# ------------------------------------------------------------ 1. three numbers
check("target-is-45", SS.SPOKEN_TARGET_PCT == 45, SS.SPOKEN_TARGET_PCT)
check("floor-is-40", SS.SPOKEN_MIN_PCT == 40, SS.SPOKEN_MIN_PCT)
check("cap-is-55", SS.SPOKEN_MAX_PCT == 55, SS.SPOKEN_MAX_PCT)
check("fractions", (SS.TARGET, SS.FLOOR, SS.CAP) == (0.45, 0.40, 0.55),
      (SS.TARGET, SS.FLOOR, SS.CAP))
check("cap-is-not-70", SS.CAP != 0.70, SS.CAP)

b = SS.band()
check("band-dict",
      (b["target_pct"], b["floor_pct"], b["cap_pct"]) == (45, 40, 55), b)
check("band-applies-to-every-length-and-style",
      b["applies_to"] == "every length and every music style", b["applies_to"])
check("band-rap-counts", b["rap_counts_as_spoken"] is True, b)
check("band-has-source", "Decision log 37" in b["source"], b["source"])

src = open(os.path.join(HERE, "spoken_share.py"), encoding="utf-8").read()
check("old-band-literal-gone", "40-70" not in src and "0.70" not in src,
      "old 40-70 band still in source")
check("per-length-table-gone",
      "D15_TARGETS" not in src and "SHARE_TARGETS_BY_LENGTH" not in src,
      "retired table name still present")

# --------------------------------------- 2. one band, every length and style
LENGTHS = (60, 90, 180, 300, 600)
bands = {}
for secs in LENGTHS:
    got = SS.seconds_for(secs)
    bands[secs] = (got["floor_s"], got["cap_s"], got["target_s"])
    check("length-%s-fractions" % secs,
          (round(got["floor_s"] / secs, 6), round(got["cap_s"] / secs, 6),
           round(got["target_s"] / secs, 6)) == (0.40, 0.55, 0.45), got)
    check("length-%s-first-sung-target" % secs,
          got["first_sung_target_s"] == round(secs * 0.15, 3)
          and got["first_sung_accept_s"] == [round(secs * 0.10, 3),
                                             round(secs * 0.20, 3)], got)

check("one-band-every-length",
      len({(round(f / s, 6), round(c / s, 6), round(t / s, 6))
           for s, (f, c, t) in bands.items()}) == 1, bands)

# The length engine / style engine reads the numbers from here: prove every
# style x every length carries this same band and the 45% target.
try:
    import music_styles as MS  # noqa: E402
    styles_ok = True
    detail = []
    for sid in MS.style_ids():
        for secs in LENGTHS:
            t = MS.spoken_target(sid, secs)
            ok = ((t["floor"], t["cap"], t["target"]) == (0.40, 0.55, 0.45)
                  and t["rap_counts_as_spoken"] is True)
            if not ok:
                styles_ok = False
                detail.append((sid, secs, t["floor"], t["cap"], t["target"]))
            if MS.d15_range(secs) != (0.40, 0.55):
                styles_ok = False
                detail.append(("d15_range", secs, MS.d15_range(secs)))
    check("every-style-every-length-45-40-55", styles_ok, detail)
    check("music-styles-reads-this-package",
          MS.SPOKEN_SHARE_TARGET == SS.TARGET
          and MS.SPOKEN_SHARE_MIN == SS.FLOOR
          and MS.SPOKEN_SHARE_MAX == SS.CAP,
          (MS.SPOKEN_SHARE_TARGET, MS.SPOKEN_SHARE_MIN, MS.SPOKEN_SHARE_MAX))
    check("music-styles-old-table-not-reexported",
          not hasattr(MS, "D15_TARGETS"), "D15_TARGETS still exported")
    check("music-styles-planner-rule-exposed",
          MS.check_first_sung is SS.check_first_sung, MS.check_first_sung)
except Exception as e:  # noqa: BLE001 - a broken engine import is a failure
    check("music-styles-import", False, "%s: %s" % (type(e).__name__, e))

# ---------------------------------------------------- 3. rap counts as spoken
RAP = [
    {"delivery": "spoken", "seconds": 30.0},
    {"delivery": "rap", "seconds": 10.5},
    {"delivery": "sung", "seconds": 49.5},
]
m = SS.measure_share(RAP)
check("rap-counted-in-measure", abs(m["share"] - 0.45) < 1e-9, m)
check("rap-flag", m["rap_counts_as_spoken"] is True, m)
check("rap-style-set", SS.SPOKEN_STYLE_DELIVERIES == frozenset({"spoken", "rap"}),
      sorted(SS.SPOKEN_STYLE_DELIVERIES))
check("sung-never-spoken",
      SS.measure_share([{"delivery": "sung", "seconds": 10.0}])
      ["spoken_style_seconds"] == 0.0)
check("is-spoken-style-rap", SS.is_spoken_style("rap") is True)
check("is-spoken-style-spoken", SS.is_spoken_style("Spoken ") is True)
check("is-spoken-style-sung-false", SS.is_spoken_style("sung") is False)

# ------------------------------------------------------- 4. band boundaries
check("floor-pass", SS.check_share(0.40)["verdict"] == "PASS",
      SS.check_share(0.40))
check("cap-is-flag-not-pass", SS.check_share(0.55)["verdict"] == "FLAG",
      SS.check_share(0.55))
check("target-pass", SS.check_share(0.45)["verdict"] == "PASS")
check("just-under-floor-flag", SS.check_share(0.3999)["verdict"] == "FLAG")
check("just-over-cap-redo", SS.check_share(0.5501)["verdict"] == "FAIL")
check("zero-fail", SS.check_share(0.0)["verdict"] == "FAIL")
check("full-fail", SS.check_share(1.0)["verdict"] == "FAIL")
check("over-70-fail", SS.check_share(0.70)["verdict"] == "FAIL",
      SS.check_share(0.70)["reasons"])
r = SS.check_share(0.70)
check("over-cap-reason-names-55",
      any("redo" in x for x in r["reasons"]), r["reasons"])
check("under-floor-reason-names-40",
      any("redo" in x for x in SS.check_share(0.30)["reasons"]),
      SS.check_share(0.30)["reasons"])
check("in-band-flag", SS.check_share(0.45)["in_band"] is True)
check("delta-from-target", abs(SS.check_share(0.45)["delta_from_target"]) < 1e-9)

check("refusal-empty-when-ok", SS.refusal(0.45) == "", SS.refusal(0.45))
check("refusal-text-when-fail",
      SS.refusal(0.70).startswith("REFUSED spoken share"), SS.refusal(0.70))

# share must agree with the timing measurement, or fail closed.
check("share-vs-segments-mismatch-fail",
      SS.check_share(0.50, RAP)["verdict"] == "FAIL",
      SS.check_share(0.50, RAP)["reasons"])
check("matching-share-and-segments-pass",
      SS.check_share(round(m["share"], 6), RAP)["verdict"] == "PASS",
      SS.check_share(round(m["share"], 6), RAP))

# ------------------------------------- 5. first real singing, 15% target
check("first-sung-target-is-15", SS.FIRST_SUNG_TARGET_PCT == 15)
check("old-fixed-seconds-check-is-gone",
      not hasattr(SS, "FIRST_SUNG_WITHIN_SECONDS"))
check("g10-one-constants-set",
      (SS.TARGET_ACCEPT_PCT, SS.TARGET_FLAG_PCT, SS.REAL_SINGING_STRETCH_S)
      == (SS.ACCEPT_PTS, SS.FLAG_PTS, SS.NO_REAL_SINGING_STRETCH_S))


def at(first, total=100.0):
    return SS.check_first_sung([
        {"delivery": "spoken", "start": 0.0, "end": first},
        {"delivery": "sung", "start": first, "end": total}])


# 100 s ad: target 15 s. 18% accept, 22% flag (7 pts), 27% redo (12 pts).
check("first-sung-15-accept", at(15)["verdict"] == "PASS", at(15))
check("first-sung-18-percent-accept",
      at(18)["verdict"] == "PASS" and at(18)["band"] == "ACCEPT", at(18))
check("first-sung-20-percent-accept-edge", at(20)["verdict"] == "PASS")
f22 = at(22)
check("first-sung-22-percent-flag",
      f22["verdict"] == "FLAG" and f22["flags"] and not f22["reasons"], f22)
f27 = at(27)
check("first-sung-27-percent-redo",
      f27["verdict"] == "FAIL" and any("redo" in x for x in f27["reasons"]),
      f27)
check("first-sung-10-percent-accept-early-edge", at(10)["verdict"] == "PASS")
check("first-sung-at-zero-redo", at(0.5)["verdict"] == "FAIL")
check("basis-is-reported", at(15)["basis"] == "planned"
      and SS.check_first_sung([{"delivery": "sung", "seconds": 60.0}],
                              "measured")["basis"] == "measured")
no_sung = [{"delivery": "spoken", "seconds": 60.0}]
check("no-sung-fail", SS.check_first_sung(no_sung)["verdict"] == "FAIL",
      SS.check_first_sung(no_sung))
blip = [{"delivery": "sung", "start": 5.0, "end": 8.0},
        {"delivery": "spoken", "start": 8.0, "end": 60.0}]
check("short-sung-blip-is-not-real-singing",
      SS.check_first_sung(blip)["verdict"] == "FAIL"
      and SS.check_first_sung(blip)["first_sung_start_s"] is None)
# A 3 s blip first, then a real stretch: the first REAL singing is judged.
blip_then_real = [{"delivery": "spoken", "start": 0.0, "end": 5.0},
                  {"delivery": "sung", "start": 5.0, "end": 8.0},
                  {"delivery": "spoken", "start": 8.0, "end": 15.0},
                  {"delivery": "sung", "start": 15.0, "end": 60.0}]
check("first-real-singing-skips-blip",
      SS.check_first_sung(blip_then_real)["first_sung_start_s"] == 15.0)
kies = SS.segments_from_sung_stretches([(41.0, 43.0)], 60.0)
check("measured-2s-sung-is-redo",
      SS.check_first_sung(kies, "measured")["verdict"] == "FAIL")
ok = SS.check_first_sung(SS.segments_from_sung_stretches([(9.0, 60.0)], 60.0),
                         "measured")
check("measured-hook-at-9s-accept", ok["verdict"] == "PASS", ok)
st = SS.steer_first_sung([{"delivery": "spoken", "seconds": 30.0},
                          {"delivery": "sung", "seconds": 30.0}])
check("steer-shorten-opener", st["action"] == "shorten_opener"
      and st["move_by_s"] == -21.0 and st["target_s"] == 9.0, st)
st = SS.steer_first_sung([{"delivery": "spoken", "seconds": 9.0},
                          {"delivery": "sung", "seconds": 51.0}])
check("steer-keep", st["action"] == "keep", st)
check("steer-add-hook",
      SS.steer_first_sung(no_sung)["action"] == "add_sung_hook")

# check_plan enforces BOTH halves: band and first-sung rule.
# 90 s cut on the target: 6 s spoken + 34.5 s rap = 40.5 s spoken-style
# (45%), the sung line opens at 6 s, the second sung block closes it out.
good = [
    {"delivery": "spoken", "start": 0.0, "end": 13.5},
    {"delivery": "sung", "start": 13.5, "end": 19.5},
    {"delivery": "rap", "start": 19.5, "end": 47.0},
    {"delivery": "sung", "start": 47.0, "end": 90.0},
]
p = SS.check_plan(90, good)
check("plan-in-band-pass", p["share_check"]["verdict"] == "PASS",
      p["share_check"])
check("plan-first-sung-pass", p["first_sung"]["verdict"] == "PASS",
      p["first_sung"])
check("plan-pass", p["verdict"] == "PASS", p["reasons"])
check("plan-refusal-empty", SS.plan_refusal(90, good) == "")

late_plan = [
    {"delivery": "spoken", "start": 0.0, "end": 40.0},
    {"delivery": "sung", "start": 40.0, "end": 90.0},
]
p2 = SS.check_plan(90, late_plan)
check("plan-late-first-sung-fail",
      p2["verdict"] == "FAIL" and p2["first_sung"]["verdict"] == "FAIL", p2)
check("plan-refusal-text",
      SS.plan_refusal(90, late_plan).startswith("REFUSED 90s plan"),
      SS.plan_refusal(90, late_plan))

# Too talky: 58 s spoken-style of 90 = 64.4%, over the 55% ceiling, while the
# sung line still opens on time -- only the band can catch this one.
talky = [
    {"delivery": "spoken", "start": 0.0, "end": 6.0},
    {"delivery": "sung", "start": 6.0, "end": 14.0},
    {"delivery": "spoken", "start": 14.0, "end": 66.0},
    {"delivery": "sung", "start": 66.0, "end": 90.0},
]
p3 = SS.check_plan(90, talky)
check("plan-over-cap-fail", p3["share_check"]["verdict"] == "FAIL", p3)
check("plan-over-cap-reason-names-55",
      any("redo" in x for x in p3["reasons"]), p3["reasons"])


# ------------------------------------------------ H8: one rule, one band
check("h8-band-constants", (SS.ACCEPT_PTS, SS.FLAG_PTS,
      SS.NO_REAL_SINGING_STRETCH_S) == (5, 10, 6.0))
check("h8-judge-5-accept", SS.judge_gap(5.0) == "PASS")
check("h8-judge-5.1-flag", SS.judge_gap(5.1) == "FLAG")
check("h8-judge-10-flag", SS.judge_gap(10.0) == "FLAG")
check("h8-judge-10.1-redo", SS.judge_gap(10.1) == "FAIL")
check("h8-judge-negative-gap", SS.judge_gap(-7) == "FLAG")
# share: 45 goal -> 50 accept, 52 flag, 56 redo
check("h8-share-50-accept", SS.check_share(0.50)["verdict"] == "PASS")
f52 = SS.check_share(0.52)
check("h8-share-52-flag-carries-flag",
      f52["verdict"] == "FLAG" and len(f52["flags"]) == 1, f52)
check("h8-share-56-redo", SS.check_share(0.56)["verdict"] == "FAIL")
check("h8-flag-never-refuses", SS.refusal(0.52) == "")
# THE singing rule: only a missing 6 s sung stretch is a hard reject.
short = [{"delivery": "spoken", "start": 0.0, "end": 20.0},
         {"delivery": "sung", "start": 20.0, "end": 25.0},
         {"delivery": "spoken", "start": 25.0, "end": 60.0}]
check("h8-5s-stretch-is-no-real-singing",
      SS.check_real_singing(short)["real_singing"] is False)
six = [{"delivery": "spoken", "start": 0.0, "end": 20.0},
       {"delivery": "sung", "start": 20.0, "end": 26.0},
       {"delivery": "spoken", "start": 26.0, "end": 60.0}]
check("h8-6s-stretch-is-real-singing",
      SS.check_real_singing(six)["real_singing"] is True)
joined = [{"delivery": "sung", "start": 0.0, "end": 3.0},
          {"delivery": "sung", "start": 3.1, "end": 7.0}]
check("h8-adjacent-sung-segments-join",
      SS.longest_sung_stretch_s(joined) == 6.9, SS.longest_sung_stretch_s(joined))
check("h8-all-spoken-hard-reject",
      SS.check_plan(60, [{"delivery": "spoken", "seconds": 60.0}])
      ["real_singing"]["verdict"] == "FAIL")
# a share miss with real singing is NOT a no-real-singing reject: only band.
p = SS.check_plan(60, [{"delivery": "sung", "start": 0.0, "end": 8.0},
                       {"delivery": "spoken", "start": 8.0, "end": 60.0}])
check("h8-share-miss-is-band-not-singing-reject",
      p["real_singing"]["real_singing"] is True and
      p["share_check"]["verdict"] == "FAIL", p["reasons"])
# length goal uses the band too: 60 s goal, 63 s accept, 66 s flag, 70 s redo
def run(total):
    return [{"delivery": "spoken", "seconds": total * 0.45},
            {"delivery": "sung", "seconds": total * 0.55}]
check("h8-length-63-accept",
      SS.check_plan(60, run(63))["length_check"]["verdict"] == "PASS")
check("h8-length-66-flag",
      SS.check_plan(60, run(66))["length_check"]["verdict"] == "FLAG")
check("h8-length-70-redo",
      SS.check_plan(60, run(70))["length_check"]["verdict"] == "FAIL")
check("h8-lipsync-seconds-short-band",
      SS.judge_seconds(12, 15, 60, only="short")["verdict"] == "PASS"
      and SS.judge_seconds(10, 15, 60, only="short")["verdict"] == "FLAG"
      and SS.judge_seconds(5, 15, 60, only="short")["verdict"] == "FAIL"
      and SS.judge_seconds(30, 15, 60, only="short")["verdict"] == "PASS")

# --------------------------------------------- 6. malformed input = caller bug
check("empty-segments-raises",
      raises(lambda: SS.measure_share([]), SS.SpokenShareError) is not None)
check("zero-runtime-raises",
      raises(lambda: SS.measure_share([{"delivery": "sung", "seconds": 0}]),
             SS.SpokenShareError) is not None)
check("bad-delivery-raises",
      raises(lambda: SS.measure_share([{"delivery": "yodel", "seconds": 3}]),
             SS.SpokenShareError) is not None)
check("bool-share-raises",
      raises(lambda: SS.check_share(True), SS.SpokenShareError) is not None)
check("nan-share-raises",
      raises(lambda: SS.check_share(float("nan")), SS.SpokenShareError)
      is not None)
check("bad-length-raises",
      raises(lambda: SS.seconds_for(0), SS.SpokenShareError) is not None)
check("bad-segment-raises",
      raises(lambda: SS.measure_share([{"delivery": "spoken"}]),
             SS.SpokenShareError) is not None)
e = raises(lambda: SS.check_share(True), SS.SpokenShareError)
check("error-code-is-caller-bug", e is not None and e.code == "BAD_SHARE",
      getattr(e, "code", None))

# ------------------------------------------------------------ 7. hygiene
MODULE_FILES = [os.path.join(HERE, f) for f in ("__init__.py",
                                                "spoken_share.py")]
PERMIT = {"__future__", "argparse", "collections", "functools", "itertools",
          "json", "math", "os", "pathlib", "re", "sys", "typing"}
NETWORK = {"urllib", "socket", "http", "requests", "ssl", "ftplib",
           "smtplib", "aiohttp"}
PAID = {"createTask", "playwright", "pm2", "curl", "subprocess"}
MEDIA = (".mp3", ".wav", ".m4a", ".mp4", ".png", ".jpg", ".jpeg", ".flac")
for path in MODULE_FILES:
    text = open(path, encoding="utf-8").read()
    base = os.path.basename(path)
    tree = ast.parse(text, filename=path)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module.split(".")[0])
    check("stdlib-only-" + base, mods <= PERMIT, sorted(mods - PERMIT))
    check("no-network-" + base, not (mods & NETWORK), sorted(mods & NETWORK))
    check("no-paid-marker-" + base,
          not any(marker in text for marker in PAID),
          [m for m in PAID if m in text])
    check("no-media-file-" + base,
          not any(ext in text for ext in MEDIA),
          [e for e in MEDIA if e in text])
    check("no-operator-path-" + base, "/Users/" not in text, "/Users/")

print()
if FAILS:
    print("FAILED %d checks: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("ALL CHECKS PASS")
sys.exit(0)
