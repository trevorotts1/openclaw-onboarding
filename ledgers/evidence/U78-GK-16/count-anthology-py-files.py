#!/usr/bin/env python3
"""
U78 (GK-16) correction — structural re-derivation of the anthology-engine
Python file count.

Run this file directly: `python3 count-anthology-py-files.py`

It is the exact tool this unit's corrected record cites for the T3
"48 python scripts" defect (owedLegs CORRECTION 1 in the QC ticket,
~/skill6-merge-queue/ONB/U78.json). It counts, per directory, using
`os.walk` (never `grep`, never a shell `find | wc -l` pipeline — the ticket's
own instruction is "derive counts with python, structurally"), at THREE
distinct locations, because the original defect was a path confusion, not
just a typo:

  1. LIVE_BOX   — ~/.openclaw/skills/59-anthology-engine
                  (what T3 actually asks about: the box under triage)
  2. REPO_SRC   — the openclaw-onboarding repo's own 59-anthology-engine/
                  (what GK-18/U80's tracking-doc reconciliation test cites)
  3. STALE_WT   — ~/clawd/_wt/anthology-drive-n8n-broker/59-anthology-engine
                  (the ONLY location on this box where "48" is a true
                  number for anything — shown here to prove where the
                  original defect's number actually came from, not to
                  reconcile to it)

No location's number is asserted as more "correct" in the abstract; each is
labeled with exactly what it counts and why it differs from the others.
"""
import json
import os
import sys


def count_py_top_level(dirpath):
    """Non-recursive: only *.py files directly inside dirpath."""
    if not os.path.isdir(dirpath):
        return None
    return len([
        f for f in os.listdir(dirpath)
        if f.endswith(".py") and os.path.isfile(os.path.join(dirpath, f))
    ])


def count_py_recursive(base):
    """Recursive: every *.py file anywhere under base (os.walk, not grep)."""
    if not os.path.isdir(base):
        return None
    total = 0
    for _root, _dirs, files in os.walk(base):
        total += sum(1 for f in files if f.endswith(".py"))
    return total


def manifest_script_inventory_count(base):
    manifest_path = os.path.join(base, "ENGINE-MANIFEST.json")
    if not os.path.isfile(manifest_path):
        return None
    with open(manifest_path) as f:
        data = json.load(f)

    def find_key(d, key):
        if isinstance(d, dict):
            for k, v in d.items():
                if k == key:
                    return v
                found = find_key(v, key)
                if found is not None:
                    return found
        elif isinstance(d, list):
            for v in d:
                found = find_key(v, key)
                if found is not None:
                    return found
        return None

    inv = find_key(data, "script_inventory")
    return len(inv) if isinstance(inv, list) else None


LOCATIONS = {
    "LIVE_BOX": os.path.expanduser("~/.openclaw/skills/59-anthology-engine"),
    "REPO_SRC": os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "59-anthology-engine"),
    "STALE_WT": os.path.expanduser("~/clawd/_wt/anthology-drive-n8n-broker/59-anthology-engine"),
}

if __name__ == "__main__":
    for label, base in LOCATIONS.items():
        base = os.path.normpath(base)
        exists = os.path.isdir(base)
        print(f"\n=== {label}: {base} (exists={exists}) ===")
        if not exists:
            continue
        scripts_n = count_py_top_level(os.path.join(base, "scripts"))
        tests_n = count_py_top_level(os.path.join(base, "tests"))
        fixtures_n = count_py_top_level(os.path.join(base, "fixtures", "golden"))
        total_n = count_py_recursive(base)
        manifest_n = manifest_script_inventory_count(base)
        print(f"  scripts/ (top-level .py)         = {scripts_n}")
        print(f"  tests/ (top-level .py)            = {tests_n}")
        print(f"  fixtures/golden (top-level .py)   = {fixtures_n}")
        print(f"  RECURSIVE total .py (os.walk)     = {total_n}")
        print(f"  ENGINE-MANIFEST.json script_inventory entries = {manifest_n}")
        parts = [n for n in (scripts_n, tests_n, fixtures_n) if n is not None]
        if parts and total_n is not None:
            print(f"  sum(scripts+tests+fixtures/golden) = {sum(parts)}  (matches RECURSIVE total: {sum(parts) == total_n})")
