#!/usr/bin/env python3
"""L4.4 (v2.9.73): the attempt ceiling — stop after 3 consecutive identical
structural failures and NAME the cause. Live proof: the Voyage To Virtue run
made 65 lip-sync attempts, every one FAIL FACE_COUNT "0 faces found", with no
early abort.

Proves, behaviourally (stdlib only, no network, no spend, $0):
  1. 65 identical FAIL FACE_COUNT receipts (the live run) -> stop at the
     ceiling, count carries the full trailing run, cause named
     ATTEMPT_CEILING_REACHED and the plain remedy "no face in these stills —
     choose a face-visible format" with the measured 0-face count.
  2. Two identical structural failures -> no stop (the ceiling is 3).
  3. A changed measured value (0 -> face_count 2 -> 0) breaks the streak:
     consecutive, not cumulative — a different still is a different input.
  4. A transient failure breaks the run and never counts (empty reasons,
     non-structural codes).
  5. Unusable/empty history never stops (fail-closed the other way: no
     fabricated abort), and a bad `ceiling` argument cannot stop (never < 1).
  6. The receipt shape picture_gate.write_receipt actually records is the
     shape this gate reads (compat), so a live loop feeding it real receipts
     trips exactly at 3.
  7. The documented stop wording names the measured field, for the operator
     and for the person the stage asks next.

Run: python3 scripts/core/lip_sync/lip_gate/test_attempt_ceiling_v2973.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # core/

import attempt_ceiling as AC                                # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def fcrec(count):
    """A picture_gate-shaped FAIL FACE_COUNT receipt with count faces."""
    return {"image": "stills/shot-1.png", "sha256": "0" * 64,
            "verdict": "FAIL",
            "reasons": [["FACE_COUNT", "%d faces found; exactly 1 is required"
                         % count]],
            "numbers": {"face_count": count}}


def main():
    # 1. the live run: 65 identical attempts
    receipts = [fcrec(0) for _ in range(65)]
    chk = AC.ceiling_check(receipts)
    check("65 identical FAIL FACE_COUNT receipts STOP", chk["stop"] is True,
          str(chk))
    check("trailing count is the full run of 65", chk["count"] == 65)
    check("cause code named", chk["cause"] == "ATTEMPT_CEILING_REACHED")
    check("structural code is FACE_COUNT",
          chk["structural_code"] == "FACE_COUNT")
    check("structural value carries the measured 0",
          chk["structural_value"] == "0")
    check("message names the remedy and the measured count",
          "no face in these stills" in chk["message"]
          and "face-visible format" in chk["message"]
          and "0 face(s)" in chk["message"], chk["message"])

    # 2. two identical: no stop
    chk2 = AC.ceiling_check([fcrec(0), fcrec(0)])
    check("2 identical structural failures do NOT stop", chk2["stop"] is False,
          str(chk2))
    check("2-failure count is 2", chk2["count"] == 2)

    # 3. ceiling is CONSECUTIVE: an intervening different still breaks it
    mixed = [fcrec(0)] * 3 + [fcrec(2)] + [fcrec(0)] * 2
    chk3 = AC.ceiling_check(mixed)
    check("0-0-0-2-0-0 stops at 2 (changed input broke it)",
          chk3["stop"] is False and chk3["count"] == 2, str(chk3))

    # 3b. ...but resumes again once the new shape also re-fails identically
    mixed2 = [fcrec(0)] * 5 + [fcrec(2)] + [fcrec(0)] * 3
    chk3b = AC.ceiling_check(mixed2)
    check("0*5-2-0*3 stops again at 3", chk3b["stop"] is True
          and chk3b["count"] == 3, str(chk3b))

    # 4. transient failures never count
    transient = [{"reasons": [], "verdict": "UNMEASURABLE"},
                 {"reasons": [["FACE_COUNT", "0 faces found"]]}]
    chk4 = AC.ceiling_check(transient + [fcrec(0)])
    check("empty-reason (transient) receipt breaks the run",
          chk4["stop"] is False and chk4["count"] == 1, str(chk4))
    nonstruct = [{"reasons": [["NET_429", "rate limited"]]}]
    chk4b = AC.ceiling_check(nonstruct * 5)
    check("a non-structural code never counts toward the ceiling",
          chk4b["stop"] is False, str(chk4b))

    # 5. unusable/empty history and bad ceiling never stop
    check("empty history never stops", AC.ceiling_check([])["stop"] is False)
    check("None history never stops", AC.ceiling_check(None)["stop"] is False)
    check("string history never stops", AC.ceiling_check("x")["stop"] is False)
    check("ceiling 0 cannot stop", AC.ceiling_check([fcrec(0)] * 5,
                                                    ceiling=0)["stop"] is False)
    check("ceiling negative cannot stop",
          AC.ceiling_check([fcrec(0)] * 5, ceiling=-1)["stop"] is False)

    # 6. exact trip at 3
    for n, stop in ((2, False), (3, True), (4, True)):
        got = AC.ceiling_check([fcrec(0)] * n)
        check("trip exactly at %d: stop=%s" % (n, stop),
              got["stop"] is stop, str(got))

    # 7. consecutive_identical returns the shared key
    c, k = AC.consecutive_identical([fcrec(0), fcrec(0), fcrec(2), fcrec(2)])
    check("consecutive_identical trailing run counts the tail",
          (c, k[1]) == (2, "2"), str((c, k)))
    check("non-dict receipt is not structural",
          AC.structural_key("junk") is None
          and AC.structural_key({"verdict": "FAIL"}) is None)

    print()
    if FAILS:
        print("FAILED: %d checks: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("test_attempt_ceiling_v2973: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())