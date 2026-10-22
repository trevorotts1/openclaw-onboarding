#!/usr/bin/env python3
"""vector_check.py — read-only gate: is the accepted source vector pinned yet?

Exit 0 = vector valid AND pinned (real canaries may run, subject to GO).
Exit 3 = vector valid but NOT pinned (expected during preparation; real canaries
         stay fail-closed).
Exit 1 = vector malformed.
Exit 2 = vector file unreadable.

Reads only. Writes nothing. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import canary_common as cc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vector", required=True)
    a = ap.parse_args()
    try:
        v = cc.load_vector(a.vector)
    except (OSError, ValueError) as e:
        print("vector unreadable: %s" % e)
        return 2

    ok, problems = cc.validate_vector(v)
    if not ok:
        print("vector MALFORMED:")
        for p in problems:
            print("  - %s" % p)
        return 1

    if not v.get("pinned"):
        print("vector valid but NOT pinned (pinned=false).")
        print("Real canary execution stays fail-closed until every revision is "
              "the accepted post-merge main SHA and pinned=true.")
        for name in cc.VECTOR_REPOS:
            rev = v["repositories"][name].get("revision")
            print("  %-40s %s" % (name, rev or "(unpinned)"))
        return 3

    pinned_ok, reason = cc.require_pinned(v)
    if not pinned_ok:
        print("vector pinned flag set but revisions incomplete: %s" % reason)
        return 1
    print("vector PINNED — real canaries may run (still requires execution GO):")
    for name in cc.VECTOR_REPOS:
        print("  %-40s %s" % (name, v["repositories"][name]["revision"]))
    print("pinned_at=%s pinned_by=%s" % (v.get("pinned_at"), v.get("pinned_by")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
