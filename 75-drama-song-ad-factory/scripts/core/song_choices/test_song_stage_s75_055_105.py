#!/usr/bin/env python3
"""S75-055 / S75-105 / S75-001 (U-S03): the song stage's three paid-path fixes.

WHAT THIS PROVES, through the REAL product code (only the provider is faked):

  (1) S75-055 -- ``song_transports.make_save`` writes the take's OWN timing file
      under ``music/word-timings/<variant>-take-NN.json`` and records
      ``word_timings_path`` on the take; the pick then publishes
      ``music/word-timings.json``, byte for byte the picked take's file;
  (2) S75-055 negative control -- a picked take with NO measured timing is
      refused by name (SONG_WORD_TIMINGS_MISSING) and publishes no file;
  (3) S75-105 -- a length of 598 s is refused with SONG_LENGTH_NOT_SUPPORTED
      before any request is built, and the fake generator is never called; the
      ceiling is the prompt-limit catalog's own number, not a typed 360;
  (4) S75-001 -- ``song_dispatch.song_cost_cents()`` is the music line's own
      cents from ``card_render.price_envelope``, and that exact number is the
      estimate ``_real_generate`` hands the dispatcher (the ledger reserve).

Run: python3 scripts/core/song_choices/test_song_stage_s75_055_105.py
"""
import json
import os
import sys
import tempfile
import types

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import prompt_limits as PL                                  # noqa: E402
import song_transports as ST                                # noqa: E402
from song_choices import song_choices as SC                 # noqa: E402
from song_dispatch import song_dispatch as SD               # noqa: E402
from catalog_calculator import card_render as CR            # noqa: E402

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))
    print("  %-76s %s" % (name, "ok" if cond else "FAIL"))


# --------------------------------------------------------------- fixtures ---
def _w(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _passing_receipt(take):
    """A REAL constituent receipt (all required gates PASS) via song_dispatch."""
    gates = {g: {"verdict": "PASS"} for g in SD.REQUIRED_TAKE_GATES}
    rcpt = {"verdict": "PASS", "gates": gates,
            "required_gates": list(SD.REQUIRED_TAKE_GATES)}
    return SD.constituent_receipt(take, rcpt, {})


def _saved_take(tmp, vid, with_words):
    """One REAL save transport call: take audio + (optionally) measured words."""
    run = os.path.join(tmp, "run-" + ("words" if with_words else "nowords"))
    src = os.path.join(run, "incoming", vid + ".mp3")
    os.makedirs(os.path.dirname(src), exist_ok=True)
    with open(src, "wb") as f:
        f.write(b"ID3 fake take bytes, one paid take")
    take = {"audio_path": src, "duration_s": 58.0}
    if with_words:
        take.update(
            aligned_words=[{"word": "hook", "start": 0.5, "end": 0.9},
                           {"word": "line", "start": 1.1, "end": 1.5}],
            measurement_owners={"transcription_and_timing": {
                "owner": "asr", "source": "suno-alignedWords"}})
    kept = ST.make_save(run)({"id": vid}, take, {"verdict": "PASS"})
    # the acceptance boundary the pick consults: a real PASS record per variant
    _w(os.path.join(run, "music", "acceptance", vid + ".json"),
       {"variant_id": vid, "verdict": "PASS"})
    return run, vid, take, kept


def _offer(run, vid, take):
    offered = {"2": {"label": "2 - Polished Modern (warm)",
                     "file": take["audio_path"],
                     "duration": "0:58",
                     "take": take,
                     "receipt": _passing_receipt(take),
                     "variant_id": vid}}
    SC._write(run, "state.json", {"required": True, "offered": offered})
    return offered


# ------------------------------------------------------------------ case 1 ---
def case_pick_publishes_the_takes_timing(tmp):
    """S75-055: save writes the take's timing file; the pick publishes it."""
    run, vid, take, kept = _saved_take(tmp, "polished-modern", with_words=True)
    rel = take.get("word_timings_path")
    per_take = os.path.join(run, rel) if rel else ""
    check("(1) make_save wrote the take's own timing file under music/word-timings/",
          isinstance(rel, str)
          and rel.replace(os.sep, "/").startswith("music/word-timings/")
          and os.path.isfile(per_take), rel)
    check("(1) the per-take file is named for the variant and take",
          os.path.basename(per_take) == "polished-modern-take-01.json",
          os.path.basename(per_take))
    doc = json.load(open(per_take, encoding="utf-8")) if per_take else {}
    check("(1) it carries the take's OWN measured words, never invented",
          [w.get("word") for w in (doc.get("words") or [])] == ["hook", "line"]
          and doc.get("source") == "suno-alignedWords", doc)

    _offer(run, vid, take)
    label = SC.record_pick(run, "2")
    dest = os.path.join(run, "music", "word-timings.json")
    check("(1) the pick published music/word-timings.json", os.path.isfile(dest), dest)
    check("(1) the published file equals the picked take's timing file",
          os.path.isfile(dest) and open(dest, "rb").read() == open(per_take, "rb").read())
    pick = json.load(open(os.path.join(run, "song-choices", "pick.json"),
                          encoding="utf-8"))
    check("(1) the pick records the timing it copied",
          str(pick.get("word_timings") or "").replace(os.sep, "/")
          == "music/word-timings.json", pick.get("word_timings"))
    check("(1) the pick returned the offered label", label.startswith("2 - "), label)


# ------------------------------------------------------------------ case 2 ---
def case_missing_timing_is_named(tmp):
    """S75-055 control: no measured timing -> a named refusal, no file written."""
    run, vid, take, kept = _saved_take(tmp, "polished-modern", with_words=False)
    check("(2) a take with no words gets no timing file",
          "word_timings_path" not in take, take.get("word_timings_path"))
    _offer(run, vid, take)
    msg = ""
    try:
        SC.record_pick(run, "2")
    except SC.ChoiceError as exc:
        msg = str(exc)
    dest = os.path.join(run, "music", "word-timings.json")
    check("(2) the pick is refused BY NAME", "SONG_WORD_TIMINGS_MISSING" in msg, msg)
    check("(2) no timing file was published", not os.path.exists(dest), dest)
    check("(2) no pick was recorded",
          not os.path.exists(os.path.join(run, "song-choices", "pick.json")))


# ------------------------------------------------------------------ case 3 ---
def case_unsupported_length(tmp):
    """S75-105: 598 s is refused by name before any request or generation."""
    run = os.path.join(tmp, "run-length")
    os.makedirs(run, exist_ok=True)
    generated = []

    def fake_generate(variant, request):
        generated.append(variant.get("id"))
        return []

    spec = {"style_id": "soul-ballad",
            "sheet": [{"tag": "Hook", "delivery": "sung",
                       "lines": ["same hook line"]}] * 2,
            "sheet_text": "same hook line\nsame hook line",
            "client_text": "", "title": "T", "length_s": 598,
            "vocal_gender": "f", "hook_plan": None, "pace_plan": None,
            "client_references": None, "run_authorities": {}}
    real_load = SC._load_request
    SC._load_request = lambda *a, **k: dict(spec)
    msg = ""
    try:
        args = types.SimpleNamespace(run_dir=run, request="req.json", ledger="",
                                     run_id="", variant="", unit_id="")
        SC.cmd_generate(args, generate=fake_generate, measure=lambda t: {},
                        save=lambda v, t, r: None)
    except SC.ChoiceError as exc:
        msg = str(exc)
    finally:
        SC._load_request = real_load
    check("(3) length 598 is refused with SONG_LENGTH_NOT_SUPPORTED",
          "SONG_LENGTH_NOT_SUPPORTED" in msg, msg)
    check("(3) the fake generator was never called", generated == [], generated)
    cap = (PL.suno_caps() or {}).get("duration") or {}
    check("(3) the ceiling is the prompt-limit catalog's number, not a typed 360",
          SC.suno_max_seconds() == cap.get("max_seconds"),
          (SC.suno_max_seconds(), cap.get("max_seconds")))
    check("(3) the refusal names the real ceiling in one sentence",
          ("%s seconds" % cap.get("max_seconds")) in msg, msg)


# ------------------------------------------------------------------ case 4 ---
def case_estimate_is_the_price_authority(tmp):
    """S75-001: the ledger estimate is the priced one-song cents, not 6."""
    env, _m = CR.price_envelope(
        {"length": "60 seconds", "shape": "9:16", "main_characters": 1}, None)
    line = None
    if isinstance(env, dict) and env.get("state") == "ok":
        line = next((li for li in (env.get("card") or {}).get("line_items") or []
                     if li.get("component") == "music"), None)
    expect = int(round(float(line["usd"]) * 100)) if line else None
    check("(4) price_envelope prices one song generation", expect and expect > 0,
          (env.get("state"), env.get("reasons")))
    check("(4) song_cost_cents is that number",
          expect is not None and SD.song_cost_cents() == expect,
          (SD.song_cost_cents() if expect is not None else None, expect))

    run = os.path.join(tmp, "run-price")
    os.makedirs(os.path.join(run, "music", "takes"), exist_ok=True)
    seen = {}

    def fake_dispatch(**kw):
        seen.update(kw)
        return {"outcome": "ok", "reason_code": "KIE_DISPATCH_OK",
                "attempt_id": "att-1",
                "evidence": {"task_id": "task-1", "saved_paths": []}}

    gen = SC._real_generate(run, os.path.join(run, "spend.sqlite3"), "r1",
                            dispatcher=fake_dispatch)
    gen({"id": "v1"}, {"model": "ai-music-api/generate",
                       "input": {"style": "s", "duration": 60}})
    check("(4) the estimate passed to the ledger is that same number",
          seen.get("estimated_cost") == expect,
          (seen.get("estimated_cost"), expect))


def main():
    tmp = tempfile.mkdtemp(prefix="s75-055-105-")
    for name, fn in (("pick publishes the timing", case_pick_publishes_the_takes_timing),
                     ("missing timing refused", case_missing_timing_is_named),
                     ("unsupported length refused", case_unsupported_length),
                     ("estimate from the price authority",
                      case_estimate_is_the_price_authority)):
        print("case (%s)" % name)
        fn(tmp)
    print("checks: %d, failures: %d" % (len(checks), len(fails)))
    for f in fails:
        print("FAIL %s" % f)
    if fails:
        return 1
    print("test_song_stage_s75_055_105: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
