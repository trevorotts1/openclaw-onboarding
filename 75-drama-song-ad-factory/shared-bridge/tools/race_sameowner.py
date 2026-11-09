#!/usr/bin/env python3
"""race_sameowner.py — the PRODUCTION-shape analogue of run_checks check A.

check A in checks/run_checks.py races two owners ("runA"/"runB"). The shipped
bridge poller instead claims every order with ONE constant owner string
(studio_bridge.py: BRIDGE_OWNER = "studio-bridge"). This tool repeats check A's
exact command shape and assertion, but with BOTH processes naming the SAME
owner, which exercises the shape production actually uses.

Usage: python3 -I tools/race_sameowner.py <tree_dir> <n> <owner> <out.json>
Exit 0 always; prints a JSON summary.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

PY = sys.executable


def main():
    tree = pathlib.Path(sys.argv[1]).resolve()
    n = int(sys.argv[2])
    owner = sys.argv[3]
    out = pathlib.Path(sys.argv[4])
    bridge = str(tree / "studio_bridge.py")
    work = pathlib.Path(tempfile.mkdtemp(prefix="race-so-", dir=str(out.parent)))
    double = zero = okcount = 0
    hist = {}
    for i in range(n):
        db = str(work / ("claim-%d.db" % i))
        order = "r_so-%d" % i
        base = [PY, "-I", bridge, "claim", "--db", db, "--order", order,
                "--owner", owner]
        p1 = subprocess.Popen(base, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        p2 = subprocess.Popen(base, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        p1.communicate()
        p2.communicate()
        codes = sorted([p1.returncode, p2.returncode])
        hist["%s" % (codes,)] = hist.get("%s" % (codes,), 0) + 1
        winners = [c for c in (p1.returncode, p2.returncode) if c == 0]
        if len(winners) == 2:
            double += 1
        if len(winners) == 0:
            zero += 1
        if codes == [0, 2] and len(winners) == 1:
            okcount += 1
    res = {"tree": str(tree), "owner": owner, "iterations": n,
           "ok_single_winner": okcount, "double_winners": double,
           "zero_winners": zero, "codes_histogram": hist,
           "rc": 0 if okcount == n else 1}
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("iterations", "ok_single_winner",
                                          "double_winners", "zero_winners",
                                          "codes_histogram", "rc")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
