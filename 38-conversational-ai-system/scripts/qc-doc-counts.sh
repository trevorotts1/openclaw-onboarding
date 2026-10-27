#!/usr/bin/env bash
# qc-doc-counts.sh (D-11) - machine-enforce the asset counts stated in the docs
# against what is actually on disk.
#
# THE DEFECT THIS CLOSES: SKILL.md and INSTALL.md state how many protocols,
# references, scripts and journey templates this skill ships, as literal numbers.
# Nothing recomputed them, so they drifted silently (scripts was stated as 92
# while the scripts/ dir held 101 .sh files). The repo-root scripts/bump-version.sh
# carries an ADVISORY-ONLY version of this check: it WARNs and returns 0
# unconditionally, so drift survives a release bump. This gate fails.
#
# ─── COUNT DEFINITIONS (THE single place these are defined) ──────────────────
# Any other file that speaks about these counts defers to this block.
#
#   protocols         regular files matching  protocols/*.md
#   references        regular files matching  references/*.md
#                     (references/snapshot-inbound-workflow-fixture.json is JSON,
#                      deliberately NOT counted - SKILL.md states that exclusion)
#   scripts           regular files matching  scripts/*.sh
#                     (includes the .test.sh fixtures: the prose total is a .sh total)
#   journey-templates immediate SUBDIRECTORIES of templates/journey-templates/
#                     (templates/journey-templates/registry.md is a file, not counted)
#   install-range     the highest numeric prefix among scripts/<NN>-*.sh, i.e. the
#                     upper bound of the "`00`-`NN`" numbered-install-script range
#
# CLAIMS CHECKED (anchored to one line shape per claim, so a number appearing in
# prose elsewhere cannot be mistaken for a count claim):
#   SKILL.md    - <N> protocol files under `protocols/`
#   SKILL.md    - **<N> scripts** under `scripts/`
#   SKILL.md    - <N> reference documents under `references/`
#   SKILL.md    - **<N> customer journey templates** under `templates/journey-templates/`
#   SKILL.md/INSTALL.md   numbered install scripts (`00`-`<NN>`)
#   INSTALL.md  - <N> reference documents under `references/`
#
# The SELF-COUNTS comment block in SKILL.md is a change HISTORY (it records what
# the counts were at v1.8.0 and logs each drift it already admits). It is NOT a
# live claim and is deliberately not checked; the live claims are the bullets above.
#
# Exit codes: 0 = every stated count agrees with disk;
#             1 = at least one stated count disagrees (names both numbers);
#             2 = could NOT verify (a counted directory is missing, a claim line is
#                 absent, or python3 is unavailable) - never a pass.
#
# Usage:
#   bash scripts/qc-doc-counts.sh
#   bash scripts/qc-doc-counts.sh --root <skill-root>
#   bash scripts/qc-doc-counts.sh --json

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

JSON_MODE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --root) SKILL_ROOT="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,52p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "qc-doc-counts: python3 unavailable - cannot count, cannot judge."
  exit 2
fi

export SKILL_ROOT JSON_MODE

python3 - <<'PYEOF'
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ["SKILL_ROOT"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

# (file, count-key, pattern). Group 1 is the stated number.
CLAIMS = [
    ("SKILL.md", "protocols",
     r"^-\s+(\d+)\s+protocol files under `protocols/`"),
    ("SKILL.md", "scripts",
     r"^-\s+\*\*(\d+) scripts\*\* under `scripts/`"),
    ("SKILL.md", "references",
     r"^-\s+(\d+)\s+reference documents under `references/`"),
    ("SKILL.md", "journey-templates",
     r"^-\s+\*\*(\d+) customer journey templates\*\* under `templates/journey-templates/`"),
    ("SKILL.md", "install-range",
     r"numbered install scripts \(`00`[-–]`(\d+)`"),
    ("INSTALL.md", "references",
     r"^-\s+(\d+)\s+reference documents under `references/`"),
    ("INSTALL.md", "install-range",
     r"numbered install scripts \(`00`[-–]`(\d+)`"),
]

# Directories that MUST exist for a count to mean anything.
REQUIRED_DIRS = [
    ("protocols", ROOT / "protocols"),
    ("references", ROOT / "references"),
    ("scripts", ROOT / "scripts"),
    ("journey-templates", ROOT / "templates" / "journey-templates"),
]

failures = []
unverified = []


def count_md(d):
    return len([p for p in d.glob("*.md") if p.is_file()])


def count_sh(d):
    return len([p for p in d.glob("*.sh") if p.is_file()])


def count_dirs(d):
    return len([p for p in d.iterdir() if p.is_dir()])


def highest_numbered(d):
    hi = None
    for p in d.iterdir():
        m = re.match(r"^(\d+)-", p.name)
        if m and p.is_file() and p.name.endswith(".sh"):
            n = int(m.group(1))
            hi = n if hi is None else max(hi, n)
    return hi


# --- measure disk -----------------------------------------------------------
missing = []
for key, d in REQUIRED_DIRS:
    if not d.is_dir():
        missing.append("%s (expected at %s)" % (key, d))
if missing:
    unverified.append("counted director%s missing: %s"
                      % ("y" if len(missing) == 1 else "ies", "; ".join(missing)))

counts = {}
if not missing:
    counts["protocols"] = count_md(ROOT / "protocols")
    counts["references"] = count_md(ROOT / "references")
    counts["scripts"] = count_sh(ROOT / "scripts")
    counts["journey-templates"] = count_dirs(ROOT / "templates" / "journey-templates")
    an = highest_numbered(ROOT / "scripts")
    if an is None:
        unverified.append("no numbered scripts/<NN>-*.sh found - install-range unverifiable")
    else:
        counts["install-range"] = an

# --- compare every stated claim --------------------------------------------
checked = []
for fname, key, pattern in CLAIMS:
    path = ROOT / fname
    if not path.is_file():
        unverified.append("%s is missing - its count claim cannot be checked" % fname)
        continue
    rx = re.compile(pattern)
    hits = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        m = rx.search(line)
        if not m:
            continue
        hits += 1
        stated = int(m.group(1))
        if key not in counts:
            unverified.append("%s:%d states %s=%d but the count could not be measured"
                              % (fname, lineno, key, stated))
            continue
        actual = counts[key]
        ok = stated == actual
        checked.append({
            "file": fname,
            "line": lineno,
            "count": key,
            "stated": stated,
            "disk": actual,
            "ok": ok,
        })
        if not ok:
            failures.append("%s:%d states %s=%d, disk has %d"
                            % (fname, lineno, key, stated, actual))
    if hits == 0:
        unverified.append("%s does not state a %s count - nothing to verify "
                          "(expected a line matching %s)" % (fname, key, pattern))

if unverified:
    verdict = "UNVERIFIED"
elif failures:
    verdict = "FAIL"
else:
    verdict = "PASS"

if JSON_MODE:
    print(json.dumps({
        "gate": "qc-doc-counts",
        "verdict": verdict,
        "root": str(ROOT),
        "counts": counts,
        "checked": checked,
        "failures": failures,
        "unverified": unverified,
    }, indent=2))
else:
    print("=== qc-doc-counts: prose counts vs disk ===")
    print("skill root: %s" % ROOT)
    if counts:
        print("disk: " + " ".join("%s=%s" % (k, counts[k])
                                  for k in ("protocols", "references", "scripts",
                                            "journey-templates", "install-range")
                                  if k in counts))
    print("checked: %d claim(s)" % len(checked))
    for c in checked:
        print("  [%s] %s:%d %s stated=%d disk=%d"
              % ("PASS" if c["ok"] else "FAIL", c["file"], c["line"],
                 c["count"], c["stated"], c["disk"]))
    for u in unverified:
        print("  [UNVERIFIED] %s" % u)
    for f in failures:
        print("  [FAIL] %s" % f)
    print("")
    if verdict == "UNVERIFIED":
        print("RESULT: UNVERIFIED - %d claim(s) could not be measured; this is NOT a PASS."
              % len(unverified))
    elif verdict == "FAIL":
        print("RESULT: FAIL - %d stated count(s) disagree with disk." % len(failures))
    else:
        print("RESULT: PASS - every stated count agrees with disk (%d claim(s))."
              % len(checked))

sys.exit({"PASS": 0, "FAIL": 1}.get(verdict, 2))
PYEOF
