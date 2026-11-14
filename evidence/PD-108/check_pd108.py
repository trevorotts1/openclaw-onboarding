#!/usr/bin/env python3
"""PD-108 acceptance A1: no path beginning `~/` remains in WORKBOOK-BUILDER-SOP.md,
and the three named replacements are present exactly once.

Run: python3 evidence/PD-108/check_pd108.py [path-to-SOP]
Exit 0 = all rows hold. Exit 1 = at least one row failed (prints each row).

Every row is a substring test on line text; no fnmatch/glob, so no path
separator can silently defeat a pattern.
"""
import sys
import pathlib

SOP = pathlib.Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "23-ai-workforce-blueprint/templates/role-library/presentations/sops/WORKBOOK-BUILDER-SOP.md"
)

text = SOP.read_text(encoding="utf-8")
lines = text.splitlines()

# A1 primary: no line contains a home-anchored path ("~/").
home_path_lines = [(i + 1, ln) for i, ln in enumerate(lines) if "~/" in ln]

# A1 secondary: the two GAUNTLET-LOOP-WORK references are gone.
gauntlet = [(i + 1, ln) for i, ln in enumerate(lines) if "GAUNTLET-LOOP-WORK" in ln]

# The three explicit replacements from the spec.
REPLACEMENTS = [
    # (row id, needle, expected occurrence count)
    ("R-scratch", "saved to a scratch folder the operator names", 1),
    ("R-sources", "The engine starts this phase when the deck, the intake and the copy exist. The speech rows are used when present.", 1),
    ("R-supersede", "the piece this SOP supersedes", 1),
]

failures = []

if home_path_lines:
    failures.append(f"A1 home path: {len(home_path_lines)} line(s) still contain '~/': "
                    + "; ".join(f"L{n}" for n, _ in home_path_lines))
if gauntlet:
    failures.append(f"GAUNTLET-LOOP-WORK: {len(gauntlet)} line(s) still reference it: "
                    + "; ".join(f"L{n}" for n, _ in gauntlet))

for rid, needle, want in REPLACEMENTS:
    got = text.count(needle)
    if got != want:
        failures.append(f"{rid}: expected {want} occurrence(s) of {needle!r}, found {got}")

print(f"SOP: {SOP}")
print(f"lines: {len(lines)}")
print(f"A1 lines containing '~/': {len(home_path_lines)}")
print(f"GAUNTLET-LOOP-WORK lines: {len(gauntlet)}")
for rid, needle, want in REPLACEMENTS:
    print(f"{rid}: {text.count(needle)} (want {want})")

if failures:
    print("\nFAIL")
    for f in failures:
        print("  - " + f)
    sys.exit(1)

print("\nPASS: all PD-108 rows hold")
sys.exit(0)
