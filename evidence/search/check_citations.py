#!/usr/bin/env python3
"""Verify every file:line citation against the pinned blob.

Reads evidence/search/citations.json, fetches each path with
`git show <pin>:<path>` (never the working tree), and asserts the expected
substring occurs on the stated line. Writes a plain-text report and exits
non-zero on any mismatch.

Usage: python3 -I evidence/search/check_citations.py --root <repo>
"""

import argparse
import json
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--out", default=None)
    opts = parser.parse_args()
    root = os.path.abspath(opts.root)

    spec_path = os.path.join(root, "evidence", "search", "citations.json")
    with open(spec_path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    pin = spec["pin"]

    blobs = {}
    rows = []
    failures = 0
    for cite in spec["citations"]:
        path = cite["path"]
        line_no = cite["line"]
        expect = cite["expect"]
        if path not in blobs:
            proc = subprocess.run(
                ["git", "show", "%s:%s" % (pin, path)],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            blobs[path] = (
                proc.stdout.decode("utf-8", "replace").splitlines()
                if proc.returncode == 0 else None
            )
        lines = blobs[path]
        if lines is None:
            rows.append((cite["interface"], path, line_no, "BLOB-MISSING", ""))
            failures += 1
            continue
        actual = lines[line_no - 1] if 0 < line_no <= len(lines) else "<out-of-range>"
        ok = expect in actual
        if not ok:
            failures += 1
        rows.append((cite["interface"], path, line_no, "OK" if ok else "MISMATCH", actual.strip()))

    out_path = opts.out or os.path.join(root, "evidence", "citations-report.txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("citation check at pin %s\n" % pin)
        fh.write("citations: %d   mismatches: %d\n\n" % (len(rows), failures))
        for iface, path, line_no, status, actual in rows:
            fh.write("%-6s %-8s %s:%d\n" % (iface, status, path, line_no))
            fh.write("        %s\n" % actual[:220])

    print("pin=%s citations=%d mismatches=%d -> %s" % (pin, len(rows), failures, out_path))
    for iface, path, line_no, status, actual in rows:
        if status != "OK":
            print("  %s %s:%d  %s" % (status, path, line_no, actual[:160]))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
