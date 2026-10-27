#!/usr/bin/env bash
# qc-doc-counts.test.sh - positive + negative fixture tests for qc-doc-counts.sh
# (D-11: the prose asset counts must agree with disk).
#
# Proves the gate:
#   * PASSES a fixture tree whose stated counts all equal what is on disk,
#   * FAILS a fixture whose stated script count is wrong, naming BOTH the stated
#     number and the real one,
#   * returns the distinct UNVERIFIED outcome (rc 2, never 0) when a counted
#     directory is missing,
#   * and PASSES the real skill tree, so the shipped docs are proven true here.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE="$SCRIPT_DIR/qc-doc-counts.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

exit_of() { local rc=0; bash "$GATE" --root "$1" >/dev/null 2>&1 || rc=$?; echo "$rc"; }
out_of()  { bash "$GATE" --root "$1" 2>&1; }
verdict_of() {
  bash "$GATE" --root "$1" --json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null
}

# --- fixture: 2 protocols, 3 references (+1 JSON fixture), 4 scripts, 2 journeys
build_fixture() {
  local r="$1"
  rm -rf "$r"
  mkdir -p "$r/protocols" "$r/references" "$r/scripts" \
           "$r/templates/journey-templates/coach" "$r/templates/journey-templates/wellness"
  printf 'x\n' > "$r/protocols/p1.md"
  printf 'x\n' > "$r/protocols/p2.md"
  printf 'x\n' > "$r/references/r1.md"
  printf 'x\n' > "$r/references/r2.md"
  printf 'x\n' > "$r/references/r3.md"
  printf '{}\n' > "$r/references/fixture.json"
  printf 'x\n' > "$r/scripts/00-a.sh"
  printf 'x\n' > "$r/scripts/01-b.sh"
  printf 'x\n' > "$r/scripts/02-c.sh"
  printf 'x\n' > "$r/scripts/qc-x.sh"
  # registry.md is a FILE inside journey-templates - must not be counted as a dir
  printf 'x\n' > "$r/templates/journey-templates/registry.md"
  cat > "$r/SKILL.md" <<'EOF'
# Fixture Skill

- 2 protocol files under `protocols/`
- **2 customer journey templates** under `templates/journey-templates/`
- **4 scripts** under `scripts/`
- 3 reference documents under `references/`

Install: the numbered install scripts (`00`–`02`) plus linters.
EOF
  cat > "$r/INSTALL.md" <<'EOF'
# Fixture Install

- Idempotent numbered install scripts (`00`–`02`, OS-aware: Darwin and Linux).
- 3 reference documents under `references/`
EOF
}

FIX="$TMP/agree"
build_fixture "$FIX"

# 1. counts agree -> pass
if [ "$(exit_of "$FIX")" = "0" ] && [ "$(verdict_of "$FIX")" = "PASS" ]; then
  ok "agreeing counts pass (rc 0, verdict PASS)"
else
  bad "agreeing counts should pass - got rc $(exit_of "$FIX"), verdict $(verdict_of "$FIX")"
fi

# 2. a deliberately wrong number -> fail, naming stated AND disk numbers
WRONG="$TMP/wrong"
build_fixture "$WRONG"
sed 's/\*\*4 scripts\*\*/**9 scripts**/' "$WRONG/SKILL.md" > "$WRONG/SKILL.new" \
  && mv "$WRONG/SKILL.new" "$WRONG/SKILL.md"
W_OUT="$(out_of "$WRONG")"
W_RC="$(exit_of "$WRONG")"
if [ "$W_RC" = "1" ] && [ "$(verdict_of "$WRONG")" = "FAIL" ]; then
  ok "wrong stated count FAILS (rc 1)"
else
  bad "wrong stated count should FAIL with rc 1 - got rc $W_RC"
fi
if printf '%s' "$W_OUT" | grep -q 'states scripts=9, disk has 4'; then
  ok "failure names both numbers (stated 9, disk 4)"
else
  bad "failure must name both numbers - output was: $(printf '%s' "$W_OUT" | grep -i 'scripts=' || echo '<no scripts= line>')"
fi

# 3. a missing counted directory -> UNVERIFIED (rc 2), never a pass
NOSCRIPTS="$TMP/missing"
build_fixture "$NOSCRIPTS"
rm -rf "$NOSCRIPTS/scripts"
M_RC="$(exit_of "$NOSCRIPTS")"
if [ "$M_RC" = "2" ] && [ "$(verdict_of "$NOSCRIPTS")" = "UNVERIFIED" ]; then
  ok "missing scripts/ dir is UNVERIFIED (rc 2), a distinct non-pass outcome"
else
  bad "missing scripts/ dir should be UNVERIFIED rc 2 - got rc $M_RC, verdict $(verdict_of "$NOSCRIPTS")"
fi
if printf '%s' "$(out_of "$NOSCRIPTS")" | grep -q 'this is NOT a PASS'; then
  ok "UNVERIFIED output says explicitly that it is not a pass"
else
  bad "UNVERIFIED output should state it is not a pass"
fi

# 3b. a claim line that vanished -> also UNVERIFIED, never a pass
NOCLAIM="$TMP/noclaim"
build_fixture "$NOCLAIM"
grep -v 'reference documents' "$NOCLAIM/SKILL.md" > "$NOCLAIM/SKILL.tmp" \
  && mv "$NOCLAIM/SKILL.tmp" "$NOCLAIM/SKILL.md"
if [ "$(exit_of "$NOCLAIM")" = "2" ]; then
  ok "a missing claim line is UNVERIFIED (rc 2), not a silent pass"
else
  bad "a missing claim line should be UNVERIFIED rc 2 - got rc $(exit_of "$NOCLAIM")"
fi

# 4. control: the real shipped skill tree must pass
if [ "$(exit_of "$SKILL_ROOT")" = "0" ] && [ "$(verdict_of "$SKILL_ROOT")" = "PASS" ]; then
  ok "the real skill tree's stated counts agree with disk"
else
  bad "the real skill tree FAILS its own count gate: $(out_of "$SKILL_ROOT" | grep -E '\[FAIL\]' | tr '\n' ' ')"
fi

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
