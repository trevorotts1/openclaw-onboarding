#!/usr/bin/env python3
"""S75-052 (U-S01): the acceptance record written where the take is judged.

WHAT THIS PROVES (all through the REAL product call path):

  production -> one_variant -> song_dispatch.run_takes -> judge_take
      -> song_choices._record_take_acceptance -> song_dispatch.record_acceptance

with the REAL save transport (song_transports.make_save) and the REAL
multi-voice measurement (a MEASURED one-voice count on the take). The only
fake is the provider: an injected ``generate`` writes a local audio file and
no network, subprocess-to-provider, or paid call ever runs (ffmpeg, used to
build and copy the audio, is the same local tool the shipped tests use).

  (a) after a three-version run, ONE acceptance record exists per variant;
  (b) with three PASS records, ``fan_in`` offers three and pick 2 succeeds;
  (c) with variant 1 FAIL, ``fan_in`` offers two, names variant 1 as blocked,
      and pick 2 still succeeds;
  (d) D-4: with every take failed, pick 1 is REFUSED until the client's
      "keep one of these" decision for version 1 is recorded, then SUCCEEDS;
      the record lives at song-choices/client-kept/<variant>.json and carries
      who, when, the judge's named concerns and the client's own words;
  (e) deleting one record makes the offer refuse with "never judged";
  (f) a one-voice, no-rap fixture with measured PASS on story and pace is
      offered and pickable when the policy is ``applicable``;
  (g) the same fixture with the pace gate UNMEASURED is blocked and named;
  (h) music/acceptance/ holds ONLY <variant>.json files after a delivery;
  (i) the same one-voice, no-rap fixture under ``all_five`` is blocked and the
      message names D1 and D5.

The acceptance policy is read from acceptance-profile.json (committed value:
``all_five``). Case (f) passes ``applicable`` EXPLICITLY to ``required_for``,
exactly as the unit's amendment says; it never flips the committed value.

Run: python3 scripts/core/song_choices/test_acceptance_real_takes_s75_052.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _sub in ("", "song_choices", "song_dispatch", "suno_recipe"):
    _p = os.path.join(CORE, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

import length_formula as LF                                # noqa: E402
from song_dispatch import song_dispatch as SD              # noqa: E402
from song_choices import song_choices as SC                # noqa: E402
import song_transports as ST                               # noqa: E402
import suno_recipe as R                                    # noqa: E402

CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung",
          "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken",
          "lines": ["She Found Power in the Climb. Get the book. Link below."]}]
SCRIPT = "One closed door. She Found Power in the Climb. Get the book. Link below."
HOOKTXT = " ".join(HOOK)
PACE = {"drop": "half-time drop, thin drums",
        "return": "turn and rise back to the groove",
        "boundary_s": 15.0, "return_boundary_s": 38.0}
DURATION = 57.5

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))
    print("  %-72s %s" % (name, "ok" if cond else "FAIL"))


# ---- fixtures -------------------------------------------------------------

def _sheet_text():
    return R.build_request("soul-ballad", SHEET, CLIENT, "T", 58,
                           hook_plan=HOOK_PLAN, pace_plan=PACE)["input"]["lyrics"]


def _plan(**over):
    """The approved plan for a ONE-VOICE, NO-RAP song."""
    p = dict(LF.plan(60, (15, 20)), sheet_text=_sheet_text(),
             style_id="soul-ballad", hook_plan=HOOK_PLAN, _pace_plan=PACE,
             voice_count=1)
    p.update(over)
    return p


def _suno_words(lyrics):
    out = []
    for block in lyrics.split("\n\n"):
        head, *lines = block.split("\n")
        toks = " ".join(lines).split() or [""]
        out += [{"word": (head + "\n" + t + " ") if k == 0 else t + " "}
                for k, t in enumerate(toks)]
    return out


def _aligned(lyrics):
    """Aligned words whose FIRST APPROVED PLOT LINE lands at 2.1 s (D2 PASS)
    and whose first hook lands after the 13.4 s build-up window (the delivery
    gates PASS), with contiguous spans so the lexical coverage holds."""
    words = _suno_words(lyrics)
    n = len(words)
    starts = [0.1, 0.6, 1.1, 1.6, 2.1][:min(5, n)]
    for i in range(5, min(9, n)):
        starts.append(round(2.5 + (i - 5) * 3.3, 3))
    rest = n - 9
    for j in range(rest):
        starts.append(round(13.5 + j * (DURATION - 13.5) / rest, 3))
    return [dict(w, startS=starts[i],
                 endS=(starts[i + 1] if i + 1 < n else DURATION))
            for i, w in enumerate(words)]


def _measured(pace=True):
    """The measured fields the real measure transport returns for one take.
    ``pace=False`` omits the gear-change evidence, so the pace gate measures
    UNMEASURED (case g)."""
    take = {
        "segments": [{"delivery": "spoken", "start": 0, "end": 2,
                      "source": "measured"},
                     {"delivery": "sung", "start": 2.5, "end": 45,
                      "source": "measured"},
                     {"delivery": "spoken", "start": 45, "end": 54,
                      "source": "measured"}],
        "aligned_words": _aligned(_sheet_text()),
        "detector": "singing_detector 2.0.0", "duration_s": DURATION,
        "music_under_speech_ratio": 0.6, "tail_rms_dbfs": -30.0,
        "first_sung_s": 2.5,
        # D5: a MEASURED one-voice count (never the stub).
        "distinct_voice_count": 1, "voice_method": "injected-analyzer",
    }
    if pace:
        take.update(
            pace_before={"onset_rate_per_s": 3.0, "rms_dbfs": -14.0},
            pace_problem={"onset_rate_per_s": 1.4, "rms_dbfs": -18.5},
            pace_after={"onset_rate_per_s": 3.0, "rms_dbfs": -14.0})
    return take


def _request_doc():
    return {"style_id": "soul-ballad", "sheet_text": _sheet_text(),
            "client_text": CLIENT, "title": "T", "length_s": 58,
            "vocal_gender": "f", "hook_plan": HOOK_PLAN, "pace_plan": PACE}


def _mp3(path):
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=300:duration=1", path],
                   check=True, capture_output=True)


def _new_run(tmp):
    run = os.path.join(tempfile.mkdtemp(dir=tmp, prefix="s75-052-"), "run")
    os.makedirs(os.path.join(run, "music"))
    with open(os.path.join(run, "music", "req.json"), "w", encoding="utf-8") as f:
        json.dump(_request_doc(), f)
    return run


def _generate(tmp):
    """The only fake: the provider. Writes a local file and returns ONE take."""
    def generate(variant, _request):
        path = os.path.join(tmp, "%s.mp3" % variant["id"])
        _mp3(path)
        return [{"audio_path": path}]
    return generate


def _run_three(tmp, pace=True):
    """A full three-version run through one_variant, the judge and the REAL
    save transport -- nothing in the product path is stubbed."""
    run = _new_run(tmp)
    plan = _plan()
    reqs = SC.build_requests("soul-ballad", SHEET, CLIENT, "T", 58,
                             hook_plan=HOOK_PLAN, pace_plan=PACE)
    save = ST.make_save(run)
    measured = _measured(pace=pace)
    for i, (variant, request) in enumerate(reqs, 1):
        SC.one_variant(i, variant, request, plan, _generate(tmp),
                       lambda _t, _m=measured: dict(_m), save,
                       SCRIPT, HOOKTXT, None, style_id="soul-ballad",
                       run_dir=run, script_approval={"required": False},
                       kie=lambda fn, *a, **k: fn())
    return run, plan


def _refresh_records(run, results, plan, policy):
    """Rewrite each variant's record under ``policy`` from the take's judge
    receipt -- the same producer functions real runs use."""
    for r in results:
        binding = SD.take_binding(r["take"]["audio_path"], "u-s01-r1")
        res = SD.audio_results_for(r["take"], r["receipts"][0], plan, run,
                                   binding=binding)
        SD.record_acceptance(run, r["variant"]["id"], binding, res,
                             required=SD.required_for(plan, policy))


def _failure_receipt(plan):
    """A receipt whose pace gate measured FAIL (a take with no gear change):
    the pace evidence shows the same rate/level before and after."""
    take = _measured()
    take["pace_problem"] = {"onset_rate_per_s": 3.0, "rms_dbfs": -14.0}
    take["pace_after"] = {"onset_rate_per_s": 3.0, "rms_dbfs": -14.0}
    return SD.judge_take(take, plan, SCRIPT, HOOKTXT, (15, 20),
                         "soul-ballad", plan["sheet_text"])


def _unmeasured_pace_receipt(plan):
    """A receipt whose pace gate measured UNMEASURED (no gear-change evidence)."""
    take = _measured(pace=False)
    return SD.judge_take(take, plan, SCRIPT, HOOKTXT, (15, 20),
                         "soul-ballad", plan["sheet_text"])


def _state(run):
    with open(os.path.join(run, "song-choices", "state.json"), encoding="utf-8") as f:
        return json.load(f)


def _acceptance_files(run):
    return sorted(os.listdir(os.path.join(run, "music", "acceptance")))


# ---- cases ----------------------------------------------------------------

def case_a(tmp):
    run, _plan_ = _run_three(tmp)
    files = _acceptance_files(run)
    ids = [r["variant"]["id"] for r in SC.results_from_run(run)]
    check("(a) one acceptance record exists per variant",
          files == sorted("%s.json" % i for i in ids), files)


def case_b(tmp):
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    _refresh_records(run, results, plan, "applicable")
    acc = SD.acceptance_from_run(run)
    check("(b) applicable: three PASS records",
          acc["applicable"] and acc["allowed"] and acc["passing"] ==
          sorted(r["variant"]["id"] for r in results), acc["variants"].keys())
    SC.fan_in(results, run, os.path.join(tmp, "D-b"))
    state = _state(run)
    check("(b) offer lists three", sorted(state["offered"]) == ["1", "2", "3"],
          sorted(state["offered"]))
    check("(b) pick 2 succeeds", SC.record_pick(run, "2").startswith("2"))


def case_c(tmp):
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    _refresh_records(run, results, plan, "applicable")
    bad = _failure_receipt(plan)
    if bad["gates"]["pace_change"]["verdict"] != "FAIL":     # fixture drift guard
        check("(c) fixture: the pace gate measures FAIL", False,
              bad["gates"]["pace_change"])
        return
    v1 = results[0]
    binding = SD.take_binding(v1["take"]["audio_path"], "u-s01-r1")
    res1 = SD.audio_results_for(v1["take"], bad, plan, run, binding=binding)
    SD.record_acceptance(run, v1["variant"]["id"], binding, res1,
                         required=SD.required_for(plan, "applicable"))
    acc = SD.acceptance_from_run(run)
    check("(c) a failed version blocks only itself",
          acc["allowed"] and v1["variant"]["id"] in acc["blocked"], acc)
    SC.fan_in(results, run, os.path.join(tmp, "D-c"))
    state = _state(run)
    check("(c) offer lists two", sorted(state["offered"]) == ["2", "3"],
          sorted(state["offered"]))
    why = " ".join(state.get("concerns", {}).get("1") or [])
    check("(c) variant 1 is named as blocked", "D3" in why, why[:160])
    check("(c) pick 2 succeeds", SC.record_pick(run, "2").startswith("2"))


def case_e(tmp):
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    _refresh_records(run, results, plan, "applicable")
    SC.fan_in(results, run, os.path.join(tmp, "D-e1"))
    victim = os.path.join(run, "music", "acceptance",
                          "%s.json" % results[1]["variant"]["id"])
    os.remove(victim)
    try:
        SC.fan_in(results, run, os.path.join(tmp, "D-e2"))
    except SC.ChoiceError as exc:
        check("(e) a take saved but never judged refuses the offer",
              "never judged" in str(exc), str(exc)[:160])
    else:
        check("(e) a take saved but never judged refuses the offer", False,
              "the offer was delivered")


def case_f(tmp):
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    required = SD.required_for(plan, "applicable")
    check("(f) applicable requires D2 and D3 only for a one-voice, no-rap song",
          required == ("D2", "D3"), required)
    _refresh_records(run, results, plan, "applicable")
    acc = SD.acceptance_from_run(run)
    reasons = {v: (r.get("reasons") or []) for v, r in acc["variants"].items()}
    check("(f) the one-voice, no-rap fixture passes under applicable",
          acc["allowed"] and not any(reasons.values()), reasons)
    SC.fan_in(results, run, os.path.join(tmp, "D-f"))
    state = _state(run)
    check("(f) offered and pickable", sorted(state["offered"]) == ["1", "2", "3"]
          and SC.record_pick(run, "1").startswith("1"), sorted(state["offered"]))
    files = _acceptance_files(run)
    check("(h) music/acceptance holds only <variant>.json files",
          files == sorted("%s.json" % r["variant"]["id"] for r in results), files)


def case_g(tmp):
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    _refresh_records(run, results, plan, "applicable")
    bad = _unmeasured_pace_receipt(plan)
    if bad["gates"]["pace_change"]["verdict"] != "UNMEASURED":   # drift guard
        check("(g) fixture: the pace gate is UNMEASURED", False,
              bad["gates"]["pace_change"])
        return
    v1 = results[0]
    binding = SD.take_binding(v1["take"]["audio_path"], "u-s01-r1")
    res1 = SD.audio_results_for(v1["take"], bad, plan, run, binding=binding)
    rec = SD.record_acceptance(run, v1["variant"]["id"], binding, res1,
                               required=SD.required_for(plan, "applicable"))
    check("(g) an unmeasured pace gate blocks and is named",
          rec["verdict"] != "PASS"
          and any("D3" in r for r in (rec.get("reasons") or [])),
          rec.get("reasons"))
    SC.fan_in(results, run, os.path.join(tmp, "D-g"))
    state = _state(run)
    why = " ".join(state.get("concerns", {}).get("1") or [])
    check("(g) the offer names the blocked version",
          sorted(state["offered"]) == ["2", "3"] and "D3" in why,
          (sorted(state["offered"]), why[:160]))


def case_i(tmp):
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    _refresh_records(run, results, plan, None)      # the committed profile value
    check("(i) the committed policy is all_five",
          SD.required_for(plan) == ("D1", "D2", "D3", "D4", "D5"),
          SD.required_for(plan))
    acc = SD.acceptance_from_run(run)
    reasons = [x for v in acc["variants"].values() for x in (v.get("reasons") or [])]
    check("(i) all_five blocks the one-voice, no-rap song and names D1 and D5",
          not acc["allowed"]
          and any("D1" in x for x in reasons)
          and any("D5" in x for x in reasons), reasons[:6])


def case_d(tmp):
    """(d) D-4: the client's "keep one of these" is HONOURED with a record.

    Every take failed the judge (nothing is offered), the client keeps version
    1: pick 1 is refused until that decision is recorded, then succeeds. The
    record is keyed by the take's own variant id, lives OUTSIDE
    music/acceptance/ (h), and never rewrites a measured gate to PASS."""
    run, plan = _run_three(tmp)
    results = SC.results_from_run(run)
    bad = _failure_receipt(plan)
    if bad["gates"]["pace_change"]["verdict"] != "FAIL":     # fixture drift guard
        check("(d) fixture: the pace gate measures FAIL", False,
              bad["gates"]["pace_change"])
        return
    for r in results:
        binding = SD.take_binding(r["take"]["audio_path"], "u-s01-r1")
        res = SD.audio_results_for(r["take"], bad, plan, run, binding=binding)
        SD.record_acceptance(run, r["variant"]["id"], binding, res,
                             required=SD.required_for(plan, "applicable"))
    SC.fan_in(results, run, os.path.join(tmp, "D-d1"))
    state = _state(run)
    check("(d) nothing is offered when every take failed", state["offered"] == {},
          state["offered"])
    try:
        SC.record_pick(run, "1")
        refused = False
    except SC.ChoiceError:
        refused = True
    check("(d) pick 1 is refused until a keep-one decision for version 1 is recorded",
          refused)
    check("(d) no pick.json before the keep-one decision",
          not os.path.exists(os.path.join(run, "song-choices", "pick.json")))
    vid = results[0]["variant"]["id"]
    doc = SC.record_client_kept(run, "1", "keep one of these three",
                                who="client", channel="card")
    check("(d) the client-kept record is keyed by the take's variant id",
          doc.get("variant") == vid and os.path.isfile(SC.client_kept_path(run, vid)),
          doc)
    check("(d) the record carries who, when, the concerns and the client's words",
          doc.get("who") == "client" and len(str(doc.get("at") or "")) >= 10
          and isinstance(doc.get("concerns"), list) and doc["concerns"]
          and doc.get("client_words") == "keep one of these three", doc)
    acc = SD.acceptance_from_run(run)
    check("(d) the kept take is CLIENT_KEPT, never PASS",
          (acc["variants"].get(vid) or {}).get("verdict") == "CLIENT_KEPT",
          acc["variants"].get(vid))
    label = SC.record_pick(run, "1")
    with open(os.path.join(run, "song-choices", "pick.json"), encoding="utf-8") as f:
        pick = json.load(f)
    check("(d) pick 1 succeeds once the keep-one decision is recorded",
          label.startswith("1") and pick.get("client_kept") is True
          and pick.get("variant") == vid, pick)
    try:
        SC.record_pick(run, "2")
        v2_refused = False
    except SC.ChoiceError:
        v2_refused = True
    check("(d) a version with neither record is still refused", v2_refused)
    check("(d) the delivery boundary releases the picked kept take",
          SD.acceptance_refusal(run, "the pick") is None,
          SD.acceptance_refusal(run, "the pick"))
    files = _acceptance_files(run)
    ids = {r["variant"]["id"] for r in results}
    check("(h) music/acceptance holds only <variant>.json files",
          all(n.endswith(".json") and (n[:-5] in ids
                                       or n == SD.OPERATOR_DECISION_FILE)
              for n in files), files)
    check("(h) no client-kept record under music/acceptance/",
          not any("client-kept" in n for n in files), files)


def main():
    tmp = tempfile.mkdtemp(prefix="s75-052-")
    for name, fn in (("a", case_a), ("b", case_b), ("c", case_c),
                     ("d", case_d), ("e", case_e), ("f", case_f), ("g", case_g),
                     ("i", case_i)):
        print("case (%s)" % name)
        fn(tmp)
    print("checks: %d, failures: %d" % (len(checks), len(fails)))
    for f in fails:
        print("FAIL %s" % f)
    if fails:
        return 1
    print("test_acceptance_real_takes_s75_052: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
