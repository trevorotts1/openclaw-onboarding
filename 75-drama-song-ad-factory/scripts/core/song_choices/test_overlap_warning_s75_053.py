#!/usr/bin/env python3
"""S75-053 (U-S02): the overlap measurement is a receipt line, not a client stop.

WHAT THIS PROVES (through the REAL product call path):

  three judged, saved takes -> fan_in -> deliver_choices -> record_pick

with the REAL save transport (song_transports.make_save) and the REAL overlap
receipt writer (song_choices.receipt_for). The only fake is the provider, as in
test_acceptance_real_takes_s75_052.py, whose fixtures this file reuses.

  (1) three ACCEPTED takes whose provider clocks do NOT overlap -- the exact
      failure in S75-053 (a fast take, a slow submit) -- are still offered
      (1, 2, 3) and pickable, and nothing raises;
  (2) the choices receipt (song-choices/state.json) carries
      ``overlap: {verdict, seconds}`` with verdict FAIL;
  (3) the same delivery records the named warning SONG_OVERLAP_NOT_SHOWN
      through loud_failure, on the receipt and in the loud_failure buffer;
  (4) negative control: genuinely overlapping clocks record PASS and raise no
      SONG_OVERLAP_NOT_SHOWN warning -- so the warning is not always-on.

Run: python3 scripts/core/song_choices/test_overlap_warning_s75_053.py
"""
import json
import os
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_acceptance_real_takes_s75_052 as base        # noqa: E402  (fixtures)
from song_choices import song_choices as SC               # noqa: E402
import loud_failure                                       # noqa: E402

#: Provider clocks for the three initial attempts, one pair per variant.
#: (1) SEQUENTIAL -- each song terminated before the next was accepted, so
#: min(terminal_at) - max(accepted_submit_at) is NEGATIVE: the S75-053 case.
SEQUENTIAL = [("2026-11-12T10:00:00.000000Z", "2026-11-12T10:00:02.000000Z"),
              ("2026-11-12T10:00:02.000000Z", "2026-11-12T10:00:04.000000Z"),
              ("2026-11-12T10:00:04.000000Z", "2026-11-12T10:00:06.000000Z")]
#: (2) OVERLAPPING -- a common 3 s window: the control.
OVERLAPPING = [("2026-11-12T10:00:00.000000Z", "2026-11-12T10:00:05.000000Z"),
               ("2026-11-12T10:00:01.000000Z", "2026-11-12T10:00:06.000000Z"),
               ("2026-11-12T10:00:02.000000Z", "2026-11-12T10:00:07.000000Z")]

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))
    print("  %-72s %s" % (name, "ok" if cond else "FAIL"))


def _write_receipts(run, results, clocks):
    """Write each variant's overlap receipt with the given provider clocks."""
    rows = []
    for r, (submitted, terminal) in zip(results, clocks):
        variant = r["variant"]
        rows.append(SC.receipt_for(run, variant,
                                   {"style_id": variant.get("id"), "length_s": 58},
                                   "a1", "task-%s" % variant["id"],
                                   submitted, terminal))
    return rows


def _run_and_offer(tmp, clocks):
    """A full three-version run, judged and saved, then offered for a pick."""
    run, plan = base._run_three(tmp)
    results = SC.results_from_run(run)
    check("fixture: three takes were produced and saved", len(results) == 3,
          len(results))
    # The acceptance records are refreshed under the `applicable` policy the
    # S75-052 test uses, so the offer boundary is decided by the overlap alone.
    base._refresh_records(run, results, plan, "applicable")
    rows = _write_receipts(run, results, clocks)
    check("fixture: three overlap receipts were written (%d initial)"
          % len(rows), len(rows) == 3, len(rows))
    loud_failure.reset()
    delivery = tempfile.mkdtemp(dir=tmp, prefix="D-")
    SC.fan_in(results, run, delivery)
    with open(os.path.join(run, "song-choices", "state.json"), encoding="utf-8") as f:
        state = json.load(f)
    return run, state


def _warning_codes(state):
    return [e.get("code") for e in (state.get("warnings") or [])]


def case_sequential(tmp):
    run, state = _run_and_offer(tmp, SEQUENTIAL)
    check("(1) three accepted takes with no provider overlap are offered",
          sorted(state.get("offered") or {}) == ["1", "2", "3"],
          sorted(state.get("offered") or {}))
    check("(1) pick 2 succeeds (the overlap is not a pick stop)",
          SC.record_pick(run, "2").startswith("2"))
    row = state.get("overlap") or {}
    check("(2) the choices receipt carries overlap {verdict, seconds}",
          set(row) == {"verdict", "seconds"}, row)
    check("(2) the recorded verdict is FAIL", row.get("verdict") == "FAIL", row)
    check("(2) the recorded overlap is a real negative number of seconds",
          isinstance(row.get("seconds"), float) and row["seconds"] < 1.0, row)
    check("(3) the receipt carries the SONG_OVERLAP_NOT_SHOWN warning",
          "SONG_OVERLAP_NOT_SHOWN" in _warning_codes(state),
          _warning_codes(state))
    check("(3) loud_failure recorded the same named warning",
          any(e.get("code") == "SONG_OVERLAP_NOT_SHOWN"
              and e.get("kind") == "WARNING" for e in loud_failure.entries()),
          loud_failure.lines())


def case_overlapping(tmp):
    run, state = _run_and_offer(tmp, OVERLAPPING)
    row = state.get("overlap") or {}
    check("(4) control: genuinely overlapping clocks record PASS",
          row.get("verdict") == "PASS", row)
    check("(4) control: no SONG_OVERLAP_NOT_SHOWN warning",
          "SONG_OVERLAP_NOT_SHOWN" not in _warning_codes(state),
          _warning_codes(state))
    check("(4) control: the three takes are offered and pickable",
          sorted(state.get("offered") or {}) == ["1", "2", "3"]
          and SC.record_pick(run, "3").startswith("3"),
          sorted(state.get("offered") or {}))


def main():
    tmp = tempfile.mkdtemp(prefix="s75-053-")
    for name, fn in (("sequential", case_sequential), ("overlapping", case_overlapping)):
        print("case (%s)" % name)
        fn(tmp)
    print("checks: %d, failures: %d" % (len(checks), len(fails)))
    for f in fails:
        print("FAIL %s" % f)
    if fails:
        return 1
    print("test_overlap_warning_s75_053: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
