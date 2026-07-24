#!/usr/bin/env bash
# Unit test: U107 — Fish Audio skill-number correction
# Verifies every file under 30-fish-audio-api-reference/ uses "Skill 30" (not
# "Skill 31"), and that no cross-skill resume instruction remains.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/../../30-fish-audio-api-reference" && pwd)"
PASS=0; FAIL=0

red()   { printf "\033[31m%s\033[0m\n" "$1"; }
green() { printf "\033[32m%s\033[0m\n" "$1"; }

assert() {
  local label="$1" cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    green "  PASS — $label"
    PASS=$((PASS + 1))
  else
    red "  FAIL — $label"
    FAIL=$((FAIL + 1))
  fi
}

echo ""
echo "═══════════════════════════════════════════════════"
echo "  U107 — Fish Audio skill-number correction"
echo "═══════════════════════════════════════════════════"
echo ""

# === Main behavior: every file says Skill 30, never Skill 31 ===
assert "INSTALL.md says Skill 30 in title" \
  "grep -q 'Skill 30' '$SKILL_DIR/INSTALL.md'"

assert "INSTALL.md has no Skill 31 reference" \
  "! grep -qi 'Skill 31' '$SKILL_DIR/INSTALL.md'"

assert "INSTALL.md has no Skill 31 numeric reference" \
  "! grep -qi 'skill-31' '$SKILL_DIR/INSTALL.md'"

assert "README.md says Skill 30 in title" \
  "grep -q 'Skill 30' '$SKILL_DIR/README.md'"

assert "README.md has no Skill 31 reference" \
  "! grep -qi 'Skill 31' '$SKILL_DIR/README.md'"

assert "SKILL.md says Skill 30 in title" \
  "grep -q 'Skill 30' '$SKILL_DIR/SKILL.md'"

assert "SKILL.md has no Skill 31 reference" \
  "! grep -qi 'Skill 31' '$SKILL_DIR/SKILL.md'"

assert "QC.md says Skill 30 in title" \
  "grep -q 'Skill 30' '$SKILL_DIR/QC.md'"

assert "QC.md has no Skill 31 reference" \
  "! grep -qi 'Skill 31' '$SKILL_DIR/QC.md'"

assert "qc-fish-audio-api-reference.sh says Skill 30" \
  "grep -q 'Skill 30' '$SKILL_DIR/qc-fish-audio-api-reference.sh'"

assert "qc-fish-audio-api-reference.sh has no Skill 31" \
  "! grep -qi 'Skill 31' '$SKILL_DIR/qc-fish-audio-api-reference.sh'"

assert "fish-audio-voice-sop.md has no Skill 31" \
  "! grep -qi 'Skill 31' '$SKILL_DIR/fish-audio-voice-sop.md'"

# === Edge case: no cross-skill resume instruction ===
assert "No 'Resume at' instruction in any file" \
  "! grep -qri 'resume at' '$SKILL_DIR'"

# === Edge case: no stale Voice Call Plugin references ===
assert "README.md has no stale 'Voice Call Plugin' ref" \
  "! grep -qi 'Voice Call Plugin' '$SKILL_DIR/README.md'"

# === Edge case: verify the skill-version.txt is present ===
assert "skill-version.txt exists" \
  "[ -f '$SKILL_DIR/skill-version.txt' ]"

echo ""
echo "═══════ Result: $PASS passed | $FAIL failed ═══════"
[ $FAIL -gt 0 ] && { red "U107 FAILED"; exit 1; } || { green "U107 PASS"; exit 0; }
