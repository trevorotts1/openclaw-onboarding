#!/usr/bin/env python3
"""Run ONE fixture driver in an isolated interpreter. Prints one JSON object."""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drivers  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--core-999", required=True)
    ap.add_argument("--pending-head", required=True)
    ap.add_argument("--timer-dir", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--fixtures-dir", required=True)
    a = ap.parse_args()
    fx = json.load(open(os.path.join(a.fixtures_dir, a.fixture + ".json")))
    # Fresh scratch per fixture per invocation: a reproduction always starts
    # from the fixture's own seeded state, never from a previous run's residue.
    import shutil
    fixture_tmp = os.path.join(a.tmp, a.fixture)
    if os.path.isdir(fixture_tmp):
        shutil.rmtree(fixture_tmp)
    os.makedirs(fixture_tmp, exist_ok=True)
    p = drivers.Paths(a.core_999, a.pending_head, a.timer_dir, fixture_tmp)
    try:
        observed = drivers.DRIVERS[a.fixture](p, fx)
        out = {"fixture_id": a.fixture, "status": "ran", "observed": observed}
    except Exception as e:  # noqa: BLE001 - reported, never hidden
        out = {"fixture_id": a.fixture, "status": "driver-error",
               "error": "%s: %s" % (type(e).__name__, str(e)[:400])}
    print(json.dumps(out, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
