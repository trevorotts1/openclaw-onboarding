#!/usr/bin/env bash
# tests/unit/qc-skill35-installed-layout.test.sh
#
# REGRESSION GUARD — Skill 35 QC: installed-copy layout (finding T2-02).
#
# THE FALSE FAIL THIS CLOSES.  qc-skill35.sh computed
#     REPO_ROOT_LATTICE="$(cd "$(dirname "$0")/.." && pwd)"
# and then ran "$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py"
# through a HARD assert.  In the source repo the skill sits at the repo root, so
# ".." resolves and docs/ is a sibling.  On a client box the skill installs to
# ~/.openclaw/skills/35-social-media-planner, so ".." is ~/.openclaw/skills --
# which has NO docs/ directory -- and python3 exited 2 ("can't open file").
# Measured on a staged installed copy of origin/main: "27 passed | 1 failed",
# and that ONE failure was this checker.  35-social-media-planner/INSTALL.md
# mandates this script exit 0, so a CORRECT install could never be completed --
# the exact failure mode that trains operators to bypass gates.
#
# WHAT THIS FILE PROVES (hermetic; fixtures in a tempdir, no box touched):
#   T1  installed layout (no docs/ sibling) -> the lattice check SKIPS VISIBLY
#   T2  ...and contributes ZERO failures (no permanently-red gate)
#   T3  ...and the skip is NOT converted into a pass, and IS counted as a skip
#   T4  repo layout with the checker present and citations intact ->
#       the check RUNS and PASSES (the guard did not disable it)
#   T5  repo layout with a DELIBERATELY BROKEN citation -> it still FAILS
#       (the skip path did not blunt the tripwire)
#
# T4/T5 REPAIR the citation line numbers inside the FIXTURE copy of
# docs/lattice-citations.json before running.  That is deliberate: it keeps this
# guard measuring the SKIP-vs-ASSERT behaviour this fix owns, and independent of
# any unrelated citation drift that may exist in the manifest at any given time.
# It never writes to the real manifest.
#
# Exit 0 = pass.  Exit 1 = the false fail regressed, or the tripwire went blind.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/35-social-media-planner"
QC_REL="35-social-media-planner/qc-skill35.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-skill35-installed-layout.test.sh (T2-02) ==="
echo ""

for f in "$SKILL_DIR/qc-skill35.sh" "$REPO_ROOT/docs/tools/check_lattice_citation.py" \
         "$REPO_ROOT/docs/lattice-citations.json"; do
  if [ ! -f "$f" ]; then echo "  FAIL: $f not found"; exit 1; fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

strip_ansi() { sed -e 's/\x1b\[[0-9;]*m//g'; }

# The exact assertion label the tripwire uses, so PASS/FAIL/SKIP for THIS check
# can be told apart from every other line the script prints.
TRIPWIRE_LABEL='SKILL.md pointer to docs/CONTENT-CONVERSATION-LATTICE.md'

# ── T1/T2/T3: INSTALLED layout — skill dir with no docs/ sibling ─────────────
mkdir -p "$TMP/installed/skills"
cp -R "$SKILL_DIR" "$TMP/installed/skills/35-social-media-planner"
INSTALLED_OUT="$(bash "$TMP/installed/skills/35-social-media-planner/qc-skill35.sh" 2>&1 | strip_ansi)"

if printf '%s\n' "$INSTALLED_OUT" | grep -q 'SKIP:.*lattice citation tripwire'; then
  pass "T1 installed layout -> lattice tripwire reports a VISIBLE SKIP"
else
  pass_line="$(printf '%s\n' "$INSTALLED_OUT" | grep -i lattice || true)"
  fail "T1 installed layout -> no visible SKIP line for the lattice tripwire; saw: ${pass_line:-<nothing>}"
fi

if printf '%s\n' "$INSTALLED_OUT" | grep -q "FAIL — $TRIPWIRE_LABEL"; then
  fail "T2 installed layout -> the lattice tripwire STILL hard-fails (the false fail regressed)"
else
  pass "T2 installed layout -> the lattice tripwire contributes zero failures"
fi

if printf '%s\n' "$INSTALLED_OUT" | grep -q "PASS — $TRIPWIRE_LABEL"; then
  fail "T3a the absent checker was converted into a silent PASS"
else
  pass "T3a the absent checker was NOT counted as a pass"
fi

if printf '%s\n' "$INSTALLED_OUT" | grep -qE 'Result:.*[0-9]+ skipped'; then
  pass "T3b the skip is reported in the result tally (visible, not silent)"
else
  fail "T3b the result tally does not report the skip: $(printf '%s\n' "$INSTALLED_OUT" | grep -E 'Result:' || true)"
fi

# ── Fixture builder for the REPO layout ─────────────────────────────────────
# Copies the skill + docs/, then repairs each skill-35 citation's line number to
# wherever its must_contain substring actually lives in the fixture.
build_repo_fixture() {
  local dest="$1"
  mkdir -p "$dest"
  cp -R "$SKILL_DIR" "$dest/35-social-media-planner"
  cp -R "$REPO_ROOT/docs" "$dest/docs"
  python3 - "$dest" <<'PY'
import json, os, sys
root = sys.argv[1]
mpath = os.path.join(root, "docs", "lattice-citations.json")
m = json.load(open(mpath))
repaired = 0
for edge in m.get("edges", []):
    if not str(edge.get("owner_skill", "")).startswith("35-"):
        continue
    for c in edge.get("citations", []):
        need = c.get("must_contain")
        f = c.get("file")
        if not need or not f:
            continue
        p = os.path.join(root, f)
        if not os.path.isfile(p):
            continue
        lines = open(p, encoding="utf-8").read().split("\n")
        for i, line in enumerate(lines, start=1):
            if need in line:
                if c.get("line") != i:
                    c["line"] = i
                    repaired += 1
                break
json.dump(m, open(mpath, "w", encoding="utf-8"), indent=2)
print("    (fixture: repaired %d skill-35 citation line number(s))" % repaired)
PY
}

# ── T4: REPO layout — checker present, citations intact -> runs and passes ───
build_repo_fixture "$TMP/repo"
REPO_OUT="$(bash "$TMP/repo/35-social-media-planner/qc-skill35.sh" 2>&1 | strip_ansi)"
if printf '%s\n' "$REPO_OUT" | grep -q "PASS — $TRIPWIRE_LABEL"; then
  pass "T4 repo layout -> lattice tripwire RUNS and PASSES (still enforced)"
else
  fail "T4 repo layout -> tripwire did not run/pass: $(printf '%s\n' "$REPO_OUT" | grep -i lattice || true)"
fi

# ── T5: REPO layout + a genuinely broken citation -> must still FAIL ─────────
build_repo_fixture "$TMP/drift"
python3 - "$TMP/drift" <<'PY'
import json, os, sys
root = sys.argv[1]
m = json.load(open(os.path.join(root, "docs", "lattice-citations.json")))
target = None
for edge in m.get("edges", []):
    if str(edge.get("owner_skill", "")).startswith("35-"):
        for c in edge.get("citations", []):
            if c.get("line") and c.get("must_contain"):
                target = c
                break
    if target:
        break
if not target:
    print("NO-CITATION-TO-BREAK")
    raise SystemExit(0)
path = os.path.join(root, target["file"])
lines = open(path, encoding="utf-8").read().split("\n")
idx = int(target["line"]) - 1
# REMOVE the cited substring -- merely prefixing it would leave the line still
# CONTAINING the substring, and the tripwire would correctly still pass.
lines[idx] = lines[idx].replace(target["must_contain"], "DRIFTED-CITATION-MARKER")
assert target["must_contain"] not in lines[idx], "fixture failed to break the citation"
open(path, "w", encoding="utf-8").write("\n".join(lines))
print("    (fixture: broke %s line %s)" % (target["file"], target["line"]))
PY
DRIFT_OUT="$(bash "$TMP/drift/35-social-media-planner/qc-skill35.sh" 2>&1 | strip_ansi)"
if printf '%s\n' "$DRIFT_OUT" | grep -q "FAIL — $TRIPWIRE_LABEL"; then
  pass "T5 repo layout + broken citation -> lattice tripwire still FAILS"
else
  fail "T5 repo layout + broken citation -> tripwire did NOT fail (gate blunted!)"
fi

echo ""
echo "  Result: $PASS passed | $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "qc-skill35-installed-layout.test.sh: FAILED"
  exit 1
fi
echo "qc-skill35-installed-layout.test.sh: PASSED"
exit 0
