#!/usr/bin/env python3
"""S75-001: run_takes refuses a spend cap above the declared per-run maximum.

The callee's own default (``SPEND_CAP_CENTS`` = 1000 cents) bought up to 166
paid generations for any caller that left it alone; the money was only safe
because the single production caller overrode it with one generation.  The
guard now lives INSIDE ``run_takes``: the module default and any cap above
``MAX_RUN_CAP_CENTS`` are refused before the generation callable runs, and the
production cap (one generation) still works.

Zero network, zero spend: ``generate`` is a counter and every other injected
direction is a stub.  Plain script, exit code 1 on any failure:
    python3 core/song_dispatch/test_s75_001_spend_cap_max.py
"""
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "suno_recipe"))

from song_dispatch import song_dispatch as SD   # noqa: E402  the MODULE

FAILS = []


def check(label, ok, detail=""):
    if ok:
        print("ok: %s" % label)
    else:
        print("FAIL: %s %s" % (label, detail))
        FAILS.append(label)


def _request():
    return {"model": "ai-music-api/generate", "lyrics": "hello",
            "input": {"duration": 60, "style": "s", "lyrics": "hello"}}


def _run(cap_cents):
    """One run_takes call with every direction stubbed; returns (out, err, calls)."""
    calls = []
    plan = {"delivered_s": 60, "pace_change": {"turns": ["a", "b"]}}
    started = []
    try:
        mp = mock.patch.multiple(
            SD, refuse_asr=lambda x: None, judge_take=lambda *a, **k: {},
            _outbound_view=lambda r: {}, _with_shipped_aliases=lambda c: {"x": 1},
            _input_of=lambda r: r.get("input") or {},
            _lyrics_of=lambda r: r.get("lyrics") or "")
        mp.start()
        started.append(mp)
        for obj, name, val in (
                (SD._WF, "max_suno_duration", lambda n: n),
                (SD._R, "check_envelope", lambda r: []),
                (SD._PC, "check_pace_plan", lambda o: []),
                (SD._SCM, "check_pace_style", lambda s, o: []),
                (SD._PC, "pace_provider_leak", lambda r: False),
                (SD._PG, "guard_or_raise", lambda v, c: {"payload": {}}),
                (SD._SA, "script_sha_near", lambda *d: None),
                (SD._SA, "record_near", lambda *d: {"required": True, "status": "approved"}),
                (SD._SA, "check_script_approval", lambda rec, lyr, sha=None: None)):
            p = mock.patch.object(obj, name, val)
            p.start()
            started.append(p)

        def generate(rq):
            calls.append(rq)
            return []

        try:
            out = SD.run_takes(_request(), plan, generate, lambda t: {},
                               lambda t, r: None, "hello", "hook",
                               cap_cents=cap_cents,
                               kie=lambda fn, label, generation=False: fn())
            err = None
        except SD.DispatchError as exc:
            out, err = None, exc
        return out, err, calls
    finally:
        for p in reversed(started):
            p.stop()


def main():
    # 0. The declared per-run maximum exists and is a real number.
    check("the module declares MAX_RUN_CAP_CENTS",
          isinstance(getattr(SD, "MAX_RUN_CAP_CENTS", None), int),
          "MAX_RUN_CAP_CENTS=%r" % (getattr(SD, "MAX_RUN_CAP_CENTS", None),))
    max_cap = getattr(SD, "MAX_RUN_CAP_CENTS", SD.SPEND_CAP_CENTS)

    # 1. THE MODULE'S OWN DEFAULT CAP IS REFUSED, never spent.
    out, err, calls = _run(SD.SPEND_CAP_CENTS)
    check("the module default cap (SPEND_CAP_CENTS) is refused by name",
          err is not None and "SPEND_CAP_ABOVE_MAX" in str(err),
          "out=%r err=%r" % (out, err))
    check("the module default cap never reaches the generation callable",
          calls == [], "generation_calls=%d" % (len(calls),))

    # 2. ANY CAP ABOVE THE DECLARED MAXIMUM IS REFUSED, never spent.
    over = max_cap + SD.GEN_COST_CENTS
    out, err, calls = _run(over)
    check("a cap above MAX_RUN_CAP_CENTS is refused by name",
          err is not None and "SPEND_CAP_ABOVE_MAX" in str(err),
          "out=%r err=%r" % (out, err))
    check("a cap above MAX_RUN_CAP_CENTS never reaches the generation callable",
          calls == [], "generation_calls=%d" % (len(calls),))

    # 3. POSITIVE CONTROL: the production cap (one generation) still generates.
    out, err, calls = _run(SD.GEN_COST_CENTS)
    check("the production cap (one generation) is accepted and runs once",
          err is None and out["spent_cents"] == SD.GEN_COST_CENTS and len(calls) == 1,
          "out=%r err=%r calls=%r" % (out, err, calls))

    print()
    if FAILS:
        print("FAILED: %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("PASS test_s75_001_spend_cap_max")
    return 0


if __name__ == "__main__":
    sys.exit(main())
