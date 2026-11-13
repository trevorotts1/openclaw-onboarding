#!/usr/bin/env python3
"""test_acceptance_real_takes_s75_052.py — D-4: "keep one of these" is honoured.

Finding S75-052 (lane S). When the song judge fails a take, the client may
answer the ONE fork with "keep one of these". Decision D-4 (answered by Trevor:
"yes, with a client-kept record") makes that a real permission: the run may go
on, and the choice is RECORDED -- who, when, the judge's named concerns and the
client's own words -- at <run>/song-choices/client-kept/<variant>.json.

What this test proves, on a run whose take 1 is a produced take the judge
failed (no PASS acceptance record) and takes 2 and 3 are offered:

  (d) `pick 1` is REFUSED until a keep-one decision for version 1 is recorded,
      then SUCCEEDS -- and the pick is marked client_kept;
  (h) afterwards music/acceptance/ holds only <variant>.json files (and
      operator-decision.json when present): the client-kept record is NEVER
      written there;
  * the record carries who, when, the named concerns and the client's words;
  * the boundary's verdict for that take is CLIENT_KEPT, never PASS -- no
    measured gate is re-written;
  * a take with NEITHER a PASS record nor a client-kept record is still refused;
  * a kept record missing a required field does NOT release the boundary, and
    the writer REFUSES to write a keep-one record that names nobody.

Script-style stdlib test: run by file. No network, no spend, no browser.

Run: python3 -B scripts/core/song_choices/test_acceptance_real_takes_s75_052.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
sys.path.insert(0, os.path.join(CORE, "intake_preflight"))

from song_choices import song_choices as SC      # noqa: E402
from song_dispatch import song_dispatch as SD    # noqa: E402

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))


def new_run(tmp):
    """A run where ALL THREE takes failed the judge (the carried case): each
    take folder is the variant's own id (as _real_generate names it), nothing
    is offered, every version is presented for listening, and the pick is the
    number -- the run's recorded mapping joins them."""
    run = os.path.join(tempfile.mkdtemp(dir=tmp, prefix="s75-052-"), "run")
    offer = os.path.join(run, "SONG-CHOICES")
    listen = os.path.join(offer, "for-listening")
    os.makedirs(listen)
    presented = []
    for n, vid, name in ((1, "polished-modern", "Slow build (piano)"),
                         (2, "warm-live-band", "Bright (full band)"),
                         (3, "cinematic-strings", "Warm (strings)")):
        os.makedirs(os.path.join(run, "music", "takes", vid))
        with open(os.path.join(run, "music", "takes", vid, "take-1.mp3"), "wb") as f:
            f.write(("the take the judge failed: %s" % vid).encode())
        p = os.path.join(listen, "%d - %s - NOT PASSED.mp3" % (n, name))
        with open(p, "wb") as f:
            f.write(("the version the client heard: %s" % vid).encode())
        presented.append(p)
    os.makedirs(os.path.join(run, "song-choices"), exist_ok=True)
    with open(os.path.join(run, "song-choices", "state.json"), "w") as f:
        json.dump({"required": True, "failure_fork": True,
                   "variants": {"1": "polished-modern", "2": "warm-live-band",
                                "3": "cinematic-strings"},
                   "offered": {},
                   "concerns": {"1": ["D4: FAIL - the pace change is not heard",
                                      "D2: FAIL - the story does not start"],
                                "2": ["D5: FAIL - one voice only"],
                                "3": ["D1: FAIL - no rap"]},
                   "presented": presented}, f)
    return run


def pick(run, reply):
    """The real CLI pick path; returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = SC.main(["pick", "--run-dir", run, "--reply", reply])
    return code, out.getvalue(), err.getvalue()


def main():
    tmp = tempfile.mkdtemp(prefix="s75-052-test-")
    try:
        run = new_run(tmp)

        # (d) BEFORE the keep-one decision the pick is REFUSED.
        code, out, err = pick(run, "1")
        print("  pick 1 before keep-one -> rc=%d err=%r" % (code, err.strip()[:120]))
        check("pick of the failed version refused before keep-one", code != 0, out)
        check("the refusal names the acceptance boundary",
              "acceptance boundary" in err or "not one of the offered" in err, err)
        check("no pick.json written yet",
              not os.path.exists(os.path.join(run, "song-choices", "pick.json")))

        # the client answers the fork: "keep one of these three".
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc_keep = SC.main(["keep", "--run-dir", run, "--variant", "1",
                               "--who", "client", "--reply", "keep one of these three"])
        print("  keep --variant 1 -> rc=%d out=%r" % (rc_keep, out.getvalue().strip()[:80]))
        check("keep-one recorded", rc_keep == 0, err.getvalue())

        p = os.path.join(run, "song-choices", "client-kept", "polished-modern.json")
        check("client-kept record keyed by the take's own variant id", os.path.isfile(p), p)
        doc = json.load(open(p)) if os.path.isfile(p) else {}
        check("record: variant id", doc.get("variant") == "polished-modern", doc)
        check("record: the pick number the client used", doc.get("n") == "1", doc)
        check("record: who", doc.get("who") == "client", doc)
        check("record: when", isinstance(doc.get("at"), str) and len(doc["at"]) >= 10, doc)
        check("record: the judge's named concerns",
              doc.get("concerns") == ["D4: FAIL - the pace change is not heard",
                                      "D2: FAIL - the story does not start"], doc)
        check("record: the client's own words",
              doc.get("client_words") == "keep one of these three", doc)

        # (h) the record is NOT under music/acceptance/.
        acc = os.path.join(run, "music", "acceptance")
        check("music/acceptance/ holds no client-kept record",
              not os.path.isdir(acc)
              or not any(".client-kept" in n for n in os.listdir(acc)), acc)
        if os.path.isdir(acc):
            names = sorted(os.listdir(acc))
            check("music/acceptance/ holds only <variant>.json files + the operator decision",
                  all(n.endswith(".json") for n in names)
                  and all(n == SD.OPERATOR_DECISION_FILE
                          or n[:-5] in ("polished-modern", "warm-live-band", "cinematic-strings")
                          for n in names), names)
        else:
            check("music/acceptance/ holds only <variant>.json files + the operator decision", True)

        # the boundary marks the take CLIENT_KEPT, never PASS.
        chk = SD.acceptance_from_run(run)
        print("  boundary -> applicable=%r allowed=%r variants=%r"
              % (chk["applicable"], chk["allowed"],
                 {k: v["verdict"] for k, v in (chk.get("variants") or {}).items()}))
        check("the kept take is not blocked",
              "polished-modern" not in (chk.get("blocked") or []), chk)
        check("the kept take is CLIENT_KEPT, never PASS",
              (chk["variants"].get("polished-modern") or {}).get("verdict") == "CLIENT_KEPT",
              chk.get("variants"))
        check("no PASS record was written for the kept take",
              not os.path.exists(os.path.join(acc, "polished-modern.json")), acc)

        # (d) AFTER the keep-one decision the pick SUCCEEDS.
        code, out, err = pick(run, "1")
        print("  pick 1 after keep-one -> rc=%d out=%r" % (code, out.strip()[:80]))
        check("pick of the kept version succeeds", code == 0, err)
        pickdoc = json.load(open(os.path.join(run, "song-choices", "pick.json")))
        check("the pick is marked client_kept", pickdoc.get("client_kept") is True, pickdoc)
        check("the pick names the take's variant id",
              pickdoc.get("variant") == "polished-modern", pickdoc)
        check("the picked file is the version the client heard",
              os.path.isfile(os.path.join(run, "music", "picked-song.mp3")))
        check("the run is no longer refused", SC.refusal(run) is None, SC.refusal(run))

        # the OTHER failed take on disk stays truthfully unrecorded...
        chk3 = SD.acceptance_from_run(run)
        check("an unrecorded take stays flagged, never a PASS",
              chk3["allowed"] is False
              and (chk3["variants"].get("warm-live-band") or {}).get("verdict") == "FAIL", chk3)
        # ...and the recorded client choice is what lets the picked take through.
        check("the delivery boundary releases the picked kept take",
              SD.acceptance_refusal(run, "the pick") is None,
              SD.acceptance_refusal(run, "the pick"))
        try:
            import factory as F                              # noqa: PLC0415
            hold = F._song_hold(run)
        except Exception as e:                               # noqa: BLE001
            hold = e
        check("the music stage's song hold opens for the kept pick", hold is None, hold)

        # a version the client did NOT keep is still refused.
        code, out, err = pick(run, "2")
        print("  pick 2 (not kept) -> rc=%d err=%r" % (code, err.strip()[:100]))
        check("a version with neither record is still refused", code != 0, out)
        check("no client-kept record was invented for version 2",
              not os.path.exists(os.path.join(run, "song-choices", "client-kept",
                                              "warm-live-band.json")))

        # a keep-one record that names nobody is refused and writes nothing.
        run3 = new_run(tmp)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc3 = SC.main(["keep", "--run-dir", run3, "--variant", "1",
                           "--reply", "keep one of these three"])
        print("  keep without --who -> rc=%d err=%r" % (rc3, err.getvalue().strip()[:100]))
        check("a keep-one record naming nobody is refused", rc3 != 0, out.getvalue())
        check("nothing was written for the nameless record",
              not os.path.exists(SC.client_kept_path(run3, "polished-modern")))

        # a malformed kept record releases nothing.
        run2 = new_run(tmp)
        p2 = SC.client_kept_path(run2, "polished-modern")
        os.makedirs(os.path.dirname(p2), exist_ok=True)
        with open(p2, "w") as f:
            json.dump({"schema": SD.CLIENT_KEPT_SCHEMA, "answer": "keep_one",
                       "variant": "polished-modern", "n": "1", "who": "",
                       "at": "2026-11-13T00:00:00Z", "concerns": [],
                       "client_words": "keep one"}, f)
        chk2 = SD.acceptance_from_run(run2)
        print("  malformed kept record -> allowed=%r reasons=%r"
              % (chk2["allowed"],
                 (chk2["variants"].get("polished-modern") or {}).get("reasons")))
        check("a kept record naming nobody does not release the boundary",
              chk2.get("allowed") is not True, chk2)
        code, out, err = pick(run2, "1")
        check("pick still refused with a malformed kept record", code != 0, out)

        print("\nchecks: %d, failures: %d" % (len(checks), len(fails)))
        for f in fails:
            print("FAIL %s" % f)
        if fails:
            sys.exit(1)
        print("test_acceptance_real_takes_s75_052: PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
