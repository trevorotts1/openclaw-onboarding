#!/usr/bin/env python3
"""Release one or both Skill 75 flavor facets and write each facet's receipt.

Each facet writes its own file into ``--out``:

    onboarding.json
    999.json

The file is that flavor's release record. Nothing in one facet's run reads the
other facet's record, so either facet can be released on its own.

Exit status is 0 only when every cell in every requested facet is PASS. A
BLOCKED_DEPENDENCY cell is reported, named and non-zero -- it is never a silent
pass.

Run:
    python3 75-drama-song-ad-factory/tests/story_first_acceptance/run_acceptance.py \
        --flavor both --out /tmp/s75t32
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cell_matrix as MATRIX  # noqa: E402

FLAVORS = ("onboarding", "999")


def run(flavors, out_dir, broken=False):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for flavor in flavors:
        record = MATRIX.run_facet(flavor, broken=broken)
        path = os.path.join(out_dir, "%s.json" % flavor)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)
            fh.write("\n")
        written.append((path, record))
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flavor", choices=FLAVORS + ("both",), default="both")
    parser.add_argument("--out", required=True)
    parser.add_argument("--broken", action="store_true",
                        help="run every cell with its condition deliberately broken")
    args = parser.parse_args(argv)

    flavors = FLAVORS if args.flavor == "both" else (args.flavor,)
    written = run(flavors, args.out, broken=args.broken)

    bad = 0
    for path, record in written:
        counts = record["counts"]
        print("%s: %s  (%d pass / %d fail / %d blocked of %d) -> %s" % (
            record["facet"], record["release_status"], counts["pass"],
            counts["fail"], counts["blocked"], counts["total"], path))
        for cell in record["cells"]:
            if cell["status"] != MATRIX.PASS:
                print("  %-28s %s %s" % (
                    cell["cell"], cell["status"],
                    ",".join(cell.get("missing", [])) or cell["observed"]))
        if record["release_status"] != MATRIX.PASS:
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
