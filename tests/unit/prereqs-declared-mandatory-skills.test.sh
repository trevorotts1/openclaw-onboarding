#!/usr/bin/env bash
# tests/unit/prereqs-declared-mandatory-skills.test.sh
#
# REGRESSION GUARD — the machine-readable prerequisites declare the skill
# dependencies their SKILL.md calls mandatory (finding T0-40).
#
# THE GAP THIS CLOSES.  The installer (install.sh / update-skills.sh, via
# shared-utils/check-skill-prereqs.sh) can only warn about prerequisites that are
# represented in PREREQS.json.  Before this:
#   06-ghl-install-pages/PREREQS.json  had exactly ONE entry (Skill 05), while
#       SKILL.md declares three further mandatory dependencies -- Skill 01
#       (teach-yourself protocol), Skill 02 (backup protocol) and Skill 03
#       (agent-browser, the PRIMARY browser engine).
#   05-ghl-setup/PREREQS.json          had two credential entries and NO skill
#       entries, while SKILL.md declares Skill 01 and Skill 02 under
#       "You MUST have these installed first".
# A selective or drifted installation therefore got a CLEAN prerequisite result
# while mandatory dependencies were absent, and the failure surfaced later and
# further from its cause.
#
# WHAT THIS FILE PROVES (hermetic; fixture skill trees in a tempdir).  Crucially
# it does NOT merely assert that an id STRING appears in the file -- a
# declaration that cannot resolve is a fabricated artifact, not a fix.  Every
# entry is driven through the REAL checker in BOTH directions:
#   T1  the entry exists, is type=skill, and its check names a directory that
#       really exists in this repo
#   T2  dependency PRESENT  -> the real checker reports it SATISFIED
#       (this is what a broken check -- e.g. the `{"skillId": 1}` form, which
#        check_skill() cannot read -- would fail, because it can never resolve)
#   T3  dependency ABSENT   -> the real checker reports it UNMET, naming the id
#       (so the entry is not a no-op that always passes)
#   T4  neither file adds a violation to scripts/qc-prereqs-json.sh
#
# NOTE ON SEVERITY.  These entries are severity "optional".  INSTALL-CONTRACT.md
# Rule 16 is explicit that "Neither `required` nor `optional` prereqs ever block
# INSTALL" -- exit 2 is informational and both install.sh and update-skills.sh
# treat it as note-and-continue -- and unmet entries of BOTH severities are
# reported identically.  "optional" is used because scripts/qc-prereqs-json.sh
# accepts only {required, optional}; it keeps these declarations incapable of
# failing a healthy box while still making the installer able to warn.
#
# Exit 0 = pass.  Exit 1 = a declared-mandatory dependency is missing from the
# machine-readable file, or an entry cannot actually resolve.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECKER="$REPO_ROOT/shared-utils/check-skill-prereqs.sh"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== prereqs-declared-mandatory-skills.test.sh (T0-40) ==="
echo ""

if [ ! -f "$CHECKER" ]; then echo "  FAIL: $CHECKER not found"; exit 1; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# The dependencies each SKILL.md declares mandatory, transcribed from the prose
# "Prerequisites" sections that PREREQS.json is the executable mirror of.
#   05-ghl-setup        SKILL.md: "You MUST have these installed first:
#                                  1. Teach Yourself Protocol (TYP) - Skill 01
#                                  2. Back Yourself Up Protocol - Skill 02"
#   06-ghl-install-pages SKILL.md: TYP (01), Backup (02), agent-browser (03),
#                                  GHL Setup (05)
EXPECT_05="skill-01-typ:01-teach-yourself-protocol skill-02-backup:02-back-yourself-up-protocol"
EXPECT_06="skill-05:05-ghl-setup skill-01-typ:01-teach-yourself-protocol skill-02-backup:02-back-yourself-up-protocol skill-03-agent-browser:03-agent-browser"

# entry_check_folder <prereqs.json> <id> -> prints the check.skill folder, or ""
entry_check_folder() {
  python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
for p in d.get("prerequisites", []):
    if p.get("id") == sys.argv[2] and p.get("type") == "skill":
        print(p.get("check", {}).get("skill", ""))
        break
' "$1" "$2"
}

# run_checker <skills-dir> <skill-name> -> prints the checker output
run_checker() {
  local skills_dir="$1" skill="$2"
  env -i HOME="$TMP/nohome" PATH="/usr/bin:/bin:/usr/local/bin" \
    /bin/bash "$CHECKER" "$skills_dir/$skill" 2>&1 || true
}

check_skill_file() {
  local skill="$1" expect="$2"
  local pj="$REPO_ROOT/$skill/PREREQS.json"
  echo "── $skill ──"

  if [ ! -f "$pj" ]; then fail "$skill: PREREQS.json not found"; return; fi

  # Fixture A: every declared dependency PRESENT.
  local present="$TMP/$skill-present"
  mkdir -p "$present/$skill"
  cp "$pj" "$present/$skill/PREREQS.json"
  # Fixture B: every declared dependency ABSENT.
  local absent="$TMP/$skill-absent"
  mkdir -p "$absent/$skill"
  cp "$pj" "$absent/$skill/PREREQS.json"

  local pair id folder ok_static=1
  for pair in $expect; do
    id="${pair%%:*}"; folder="${pair##*:}"
    local got; got="$(entry_check_folder "$pj" "$id")"
    if [ -z "$got" ]; then
      fail "T1 $skill: no type=skill entry '$id' with a readable check.skill (declared mandatory in SKILL.md)"
      ok_static=0; continue
    fi
    if [ "$got" != "$folder" ]; then
      fail "T1 $skill: entry '$id' checks '$got', expected '$folder'"
      ok_static=0; continue
    fi
    if [ ! -d "$REPO_ROOT/$folder" ]; then
      fail "T1 $skill: entry '$id' names '$folder', which is not a directory in this repo"
      ok_static=0; continue
    fi
    mkdir -p "$present/$folder"
  done
  [ "$ok_static" = "1" ] && pass "T1 $skill: every declared-mandatory dependency has a resolvable type=skill entry"

  # T2 — dependencies present -> the real checker must report NONE of them unmet.
  local out_present; out_present="$(run_checker "$present" "$skill")"
  local unmet_when_present=""
  for pair in $expect; do
    id="${pair%%:*}"
    printf '%s\n' "$out_present" | grep -q "\] $id ::" && unmet_when_present="$unmet_when_present $id"
  done
  if [ -z "$unmet_when_present" ]; then
    pass "T2 $skill: with the dependencies installed, the real checker reports them satisfied"
  else
    fail "T2 $skill: reported UNMET even though present ->$unmet_when_present (the check cannot resolve -- e.g. a skillId-style entry)"
  fi

  # T3 — dependencies absent -> the real checker must name each one.
  local out_absent; out_absent="$(run_checker "$absent" "$skill")"
  local missed=""
  for pair in $expect; do
    id="${pair%%:*}"
    printf '%s\n' "$out_absent" | grep -q "\] $id ::" || missed="$missed $id"
  done
  if [ -z "$missed" ]; then
    pass "T3 $skill: with the dependencies absent, the real checker names every one as unmet"
  else
    fail "T3 $skill: absent dependencies NOT reported ->$missed (entry is a no-op that always passes)"
  fi
}

mkdir -p "$TMP/nohome"
check_skill_file "05-ghl-setup"        "$EXPECT_05"
check_skill_file "06-ghl-install-pages" "$EXPECT_06"

# ── T4: neither file contributes a schema violation ─────────────────────────
echo "── schema lint ──"
LINT_OUT="$(bash "$REPO_ROOT/scripts/qc-prereqs-json.sh" 2>&1 || true)"
MINE="$(printf '%s\n' "$LINT_OUT" | grep -E '^  ERROR: (05-ghl-setup|06-ghl-install-pages)/PREREQS\.json' || true)"
if [ -z "$MINE" ]; then
  pass "T4 neither 05-ghl-setup nor 06-ghl-install-pages PREREQS.json has a schema violation"
else
  fail "T4 schema violations in the two files this guard owns:
$MINE"
fi

echo ""
echo "  Result: $PASS passed | $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "prereqs-declared-mandatory-skills.test.sh: FAILED"
  exit 1
fi
echo "prereqs-declared-mandatory-skills.test.sh: PASSED"
exit 0
