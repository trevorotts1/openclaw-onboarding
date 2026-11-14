#!/usr/bin/env python3
"""Is a cron job with this name registered? 0 yes, 3 no, 1 cannot tell."""

import argparse
import json
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether a named cron job is registered.")
    parser.add_argument("--name", required=True, help="cron job name to look for")
    args = parser.parse_args()
    try:
        result = subprocess.run(["openclaw", "cron", "list", "--json"], capture_output=True, text=True)
    except OSError as exc:
        print(f"cannot run openclaw: {exc}")
        return 1
    if result.returncode != 0:
        print(f"openclaw cron list failed ({result.returncode}): {result.stderr.strip()}")
        return 1
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"openclaw cron list --json did not return JSON: {exc}")
        return 1
    if isinstance(entries, dict):
        entries = entries.get("jobs") or entries.get("crons") or entries.get("data") or []
    if any(isinstance(entry, dict) and entry.get("name") == args.name for entry in entries):
        print(f"present: {args.name}")
        return 0
    print(f"absent: {args.name}")
    return 3


if __name__ == "__main__":
    sys.exit(main())
