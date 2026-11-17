#!/usr/bin/env python3
"""ceiling_cli.py - run the attempt ceiling over a run's attempt history.

    python3 scripts/core/lip_sync/lip_gate/ceiling_cli.py --history <file>

Prints ceiling_check(history) as JSON. Exit 4 when the ceiling says stop (the
cause is in the JSON), 0 when it does not, 1 when the history cannot be read.
The history may be a list of receipts or an object holding it under
"attempts" / "receipts".
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from attempt_ceiling import ceiling_check  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--history", required=True)
    a = ap.parse_args(argv)
    try:
        doc = json.load(open(a.history, encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"outcome": "error", "reason_code": "HISTORY_UNREADABLE",
                          "detail": str(exc)}, indent=2))
        return 1
    if isinstance(doc, dict):
        doc = doc.get("attempts", doc.get("receipts", []))
    out = ceiling_check(doc)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 4 if out.get("stop") else 0


if __name__ == "__main__":
    sys.exit(main())
