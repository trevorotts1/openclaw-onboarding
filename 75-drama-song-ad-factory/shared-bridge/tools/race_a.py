#!/usr/bin/env python3
"""race_a.py — repeat run_checks check A faithfully, N times, fresh DB each time.

check_a_double_claim in checks/run_checks.py runs ONE attempt against a shared
DB/work dir, so it cannot be looped without reusing a claimed order. This tool
repeats the SAME command shape and the SAME assertion, but with a fresh DB and
a fresh order id per attempt so each attempt is a clean trial.

Faithful to run_checks.check_a_double_claim:
  base = [PY, BRIDGE, "claim", "--db", db, "--order", order]
  p1 = Popen(base + ["--owner","runA"]); p2 = Popen(base + ["--owner","runB"])
  winners = exit codes that are 0; ok = sorted(codes)==[0,2] and len(winners)==1

Usage: python3 -I tools/race_a.py <tree_dir> <n> <out.json>
Exit 0 always (the measurement is the product); prints a JSON summary.
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
    out = pathlib.Path(sys.argv[3])
    bridge = str(tree / "studio_bridge.py")
    work = pathlib.Path(tempfile.mkdtemp(prefix="race-a-", dir=str(out.parent)))
    double = 0
    zero = 0
    okcount = 0
    codes_hist = {}
    detail = []
    for i in range(n):
        db = str(work / ("claim-%d.db" % i))
        order = "r_deadbeef-%d" % i
        base = [PY, "-I", bridge, "claim", "--db", db, "--order", order]
        p1 = subprocess.Popen(base + ["--owner", "runA"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        p2 = subprocess.Popen(base + ["--owner", "runB"], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        p1.communicate()
        p2.communicate()
        codes = sorted([p1.returncode, p2.returncode])
        key = "%s" % (codes,)
        codes_hist[key] = codes_hist.get(key, 0) + 1
        winners = [c for c in (p1.returncode, p2.returncode) if c == 0]
        ok = codes == [0, 2] and len(winners) == 1
        if len(winners) == 2:
            double += 1
        if len(winners) == 0:
            zero += 1
        if ok:
            okcount += 1
        if len(winners) == 2 and len(detail) < 5:
            detail.append({"i": i, "codes": codes})
    res = {
        "tree": str(tree),
        "iterations": n,
        "ok_single_winner": okcount,
        "double_winners": double,
        "zero_winners": zero,
        "codes_histogram": codes_hist,
        "double_examples": detail,
        "rc": 0 if okcount == n else 1,
    }
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps({k: res[k] for k in ("iterations", "ok_single_winner",
                                          "double_winners", "zero_winners",
                                          "codes_histogram", "rc")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
