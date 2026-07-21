#!/usr/bin/env bash
# test-humanizer-rule-check.sh — T0-61 predicate contract for Skill 19.
#
# The defect: the em-dash check alternated the RULE PHRASE with the BANNED
# CHARACTER, so the check passed precisely when the character it bans was
# present. This test constructs BOTH cases, because a predicate proven in one
# direction has not been proven at all (QUALITY-CONTROL rule E6).
#
#   case 1  em dash present, NO ban rule   -> the check must report the rule ABSENT
#   case 2  ban rule present               -> the check must report the rule PRESENT
#   case 3  the check reads only the files CORE_UPDATES.md authorises
#
# Hermetic: builds throwaway workspaces under a temp dir, points WORKSPACE and
# SKILLS_DIR_DEFAULT at them, touches no real workspace and no fleet box.
#
# Usage: bash 19-humanizer/test/test-humanizer-rule-check.sh
# Exit:  0 = the predicate behaves as contracted; 1 = it does not.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="${HUMANIZER_GATE:-$SKILL_DIR/qc-humanizer.sh}"

fails=0
pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; fails=$((fails + 1)); }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/humanizer-rule-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

EM_DASH=$'—'
BAN_RULE='Never use em dashes in any client-facing copy.'

# build_ws <name> <agents-md-body> [tools-md-body] [soul-md-body] -> prints a fake HOME
#
# The gate sources lib-shared.sh and calls resolve_platform_paths(), which
# EXPORTS WORKSPACE and SKILLS_DIR_DEFAULT and therefore overrides anything the
# caller sets. lib-shared.sh:38-46 derives both from $HOME on the mac platform,
# so a fake HOME is the only hermetic seam — without it this test would read the
# operator's real workspace and its result would depend on that machine.
build_ws() {
  local name="$1" agents="$2" tools="${3:-}" soul="${4:-}"
  local home="$WORK/$name"
  local ws="$home/.openclaw/workspace"
  mkdir -p "$ws" "$home/.openclaw/skills/19-humanizer"
  printf '%s\n' "$agents" > "$ws/AGENTS.md"
  printf '%s\n' "$tools"  > "$ws/TOOLS.md"
  printf '%s\n' "$soul"   > "$ws/SOUL.md"
  printf '%s\n' "$home"
}

# rule_verdict <fake-home> -> prints PRESENT or ABSENT
# Reads the gate's own line for the em-dash rule. The gate is warn_only for this
# check, so the exit code cannot carry the answer; the printed verdict is what an
# operator reads and is what this test asserts on.
rule_verdict() {
  local home="$1" out
  out="$(HOME="$home" bash "$GATE" 2>&1)"
  if printf '%s' "$out" | grep -q 'PASS.*em-dash ban rule\|PASS.*bans em dashes'; then
    printf 'PRESENT\n'
  elif printf '%s' "$out" | grep -q 'WARN.*em-dash ban rule\|WARN.*bans em dashes'; then
    printf 'ABSENT\n'
  else
    printf 'UNREADABLE\n'
  fi
}

echo "== Skill 19 :: T0-61 em-dash rule predicate =="

# ---------------------------------------------------------------------------
# 1. THE INVERTED CASE. The banned character is in the workspace prose and no
#    ban rule is installed anywhere. The check must NOT report the rule present.
# ---------------------------------------------------------------------------
# NOTE: this fixture must carry the CHARACTER and none of the rule language, or
# it stops being the inverted case.
ws1="$(build_ws inverted "Quarterly review ${EM_DASH} shipped on time ${EM_DASH} no blockers." "" "")"
v1="$(rule_verdict "$ws1")"
if [ "$v1" = "ABSENT" ]; then
  pass "em dash present, no ban rule -> reports ABSENT (predicate is not inverted)"
else
  fail "em dash present, no ban rule -> reported $v1; the banned character is satisfying the check"
fi

# ---------------------------------------------------------------------------
# 2. THE POSITIVE CASE (anti-false-fail control). With the rule installed in an
#    authorised file the check must report it present.
# ---------------------------------------------------------------------------
ws2="$(build_ws installed "$BAN_RULE" "" "")"
v2="$(rule_verdict "$ws2")"
if [ "$v2" = "PRESENT" ]; then
  pass "ban rule in AGENTS.md -> reports PRESENT"
else
  fail "ban rule in AGENTS.md -> reported $v2; the check cannot see an installed rule"
fi

ws3="$(build_ws installed-tools "no rule here" "$BAN_RULE" "")"
v3="$(rule_verdict "$ws3")"
if [ "$v3" = "PRESENT" ]; then
  pass "ban rule in TOOLS.md -> reports PRESENT (CORE_UPDATES.md authorises TOOLS.md)"
else
  fail "ban rule in TOOLS.md -> reported $v3"
fi

# ---------------------------------------------------------------------------
# 3. SCOPE. CORE_UPDATES.md lists SOUL.md under "Non-relevant (do not edit)".
#    A rule that only exists in SOUL.md was not installed by this skill and must
#    not be counted as this skill's installation.
# ---------------------------------------------------------------------------
ws4="$(build_ws soul-only "no rule here" "" "$BAN_RULE")"
v4="$(rule_verdict "$ws4")"
if [ "$v4" = "ABSENT" ]; then
  pass "ban rule only in SOUL.md -> reports ABSENT (skill may not write SOUL.md)"
else
  fail "ban rule only in SOUL.md -> reported $v4; the check reads a file the skill is forbidden to edit"
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
  echo "RESULT: PASS — the check matches rule language only, in the authorised files."
  exit 0
fi
echo "RESULT: FAIL — $fails case(s) did not behave as contracted."
exit 1
