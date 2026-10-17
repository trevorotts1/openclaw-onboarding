#!/usr/bin/env python3
"""Fake browser engine for Item 33 tests (no real browser anywhere).

A "session" in this fake is a marker file: the session is alive while
its marker exists, exactly the observable the registry's probe reads.
Commands:

  hold --marker PATH [--seconds N]
      Create the marker and sleep (a browser process stand-in). The
      caller's pid for registry purposes is this process. Being killed
      leaves the marker behind, like a real crashed browser leaves its
      profile lock; the registry probe for pid-only sessions reads the
      pid, for marker sessions reads the marker.
  teardown --marker PATH [--fail]
      The adapter's teardown operation: remove the marker, exit 0.
      With --fail, exit 1 and leave the marker (an adapter that cannot
      close its session: the reaper must call it unaccounted).
"""
import argparse
import sys
import time
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fake browser engine (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("hold")
    p.add_argument("--marker", required=True)
    p.add_argument("--seconds", type=float, default=3600.0)
    p = sub.add_parser("teardown")
    p.add_argument("--marker", required=True)
    p.add_argument("--fail", action="store_true")
    args = ap.parse_args(argv)
    marker = Path(args.marker)
    if args.cmd == "hold":
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("alive\n", encoding="utf-8")
        print(f"HOLDING {marker}", flush=True)
        time.sleep(args.seconds)
        return 0
    if args.cmd == "teardown":
        if args.fail:
            print("teardown failed (simulated adapter failure)", file=sys.stderr)
            return 1
        marker.unlink(missing_ok=True)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
