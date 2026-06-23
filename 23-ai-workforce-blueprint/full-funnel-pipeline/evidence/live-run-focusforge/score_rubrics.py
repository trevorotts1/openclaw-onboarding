#!/usr/bin/env python3
"""score_rubrics — thin adapter that scores THIS live evidence tree.

ONE canonical scorer (goal #196 grounded-finish). The magnitude formula lives in
``23-ai-workforce-blueprint/full-funnel-pipeline/funnel_rubrics.py``; this file is
NOT a second, separately-hardcoded scoring path. It imports that canonical engine
and runs it against the directory this file sits in, writing the committed
per-rubric scorecards. That guarantees the committed FocusForge scorecards are
produced by the SAME weighted-sub-check formula the CI rubric-gate and the pytest
graduation tests use — there is no divergent code path to drift.

Run:  python3 score_rubrics.py        # scores this dir, writes scorecard/*.json
"""
import os
import sys

EV = os.path.dirname(os.path.abspath(__file__))
# funnel_rubrics.py lives two dirs up (the pipeline root).
PIPELINE = os.path.dirname(os.path.dirname(EV))
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)

import funnel_rubrics as R  # noqa: E402


def main() -> int:
    results = R.score_all(EV)            # reads cc-invariant.json from this tree
    R.write_scorecards(EV, results)
    all_pass = all(r.passed for r in results)
    below = [f"{r.id}={r.score}" for r in results if not r.passed]
    print("ALL 11 >= 8.5 — PASS" if all_pass
          else f"BELOW THRESHOLD: {', '.join(below)}")
    for r in results:
        print(f"  {r.id:24s} {r.score:5.2f} {'PASS' if r.passed else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
