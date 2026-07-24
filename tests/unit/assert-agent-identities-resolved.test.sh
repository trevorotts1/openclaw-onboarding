#!/usr/bin/env bash
# tests/unit/assert-agent-identities-resolved.test.sh
#
# Behavioral tests for U060: _is_user_template exclusion logic in
# scripts/qc-assert-agent-identities-resolved.sh.
#
#   a) Root IDENTITY.md (intentional user template) is skipped — no false-positive
#   b) 18-proactive-agent/upstream-original/assets/SOUL.md is skipped — no false-positive
#   c) A non-excluded agent file with an unresolved fill-in prompt IS detected
#   d) A non-excluded agent file with {{GENERATED_FOR}} IS detected (exit 1)
#
# All tests run inside temporary directories — no real repo files touched.
# Exit 0 = all checks pass.  Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/qc-assert-agent-identities-resolved.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== assert-agent-identities-resolved.test.sh ==="
echo ""

[ -f "$SCRIPT" ] || { echo "FATAL: $SCRIPT not found"; exit 1; }

# ── Helper: create the smallest clean workspace that passes the gate ────────
# Every test workspace must include a clean 54-anthology-writer with SOUL.md +
# IDENTITY.md, because those are REQUIRED_FILES in the script.
_clean_workspace() {
  local root="$1"
  mkdir -p "$root/54-anthology-writer"
  printf '# SOUL.md\n## Voice\nResolved agent voice. No placeholders.\n' > "$root/54-anthology-writer/SOUL.md"
  printf "# IDENTITY.md\n**Department:** Anthology\n**Version:** 1.0\n**Last updated:** 2026-07-23\n**Generated for:** Black CEO Media\n\n## Identity\nReal content.\n" > "$root/54-anthology-writer/IDENTITY.md"
}

# ============================================================================
echo "--- Test A: Script skips root IDENTITY.md (intentional user template) ---"
W_A="$(mktemp -d)"
trap 'rm -rf "$W_A" 2>/dev/null || true' EXIT
_clean_workspace "$W_A"
# Place a root IDENTITY.md full of template markers — the same ones the script checks
cat > "$W_A/IDENTITY.md" <<'EOF'
# IDENTITY.md - Who Am I?

_Fill this in during your first conversation. Make it yours._

I'm [Agent Name]. [One-line identity description].

Help [Human Name] [achieve their primary goal].

Customize this file with your agent's identity, principles, and boundaries.

{{GENERATION_DATE}}
{{COMPANY_INDUSTRY}}
{{ASSIGNED_PERSONA_VERSION}}
{{OWNER_NAME}}
{{GENERATED_FOR}}

Generated for: {{TOKEN}}
Generated for: {{COMPANY_NAME}}
EOF
if bash "$SCRIPT" "$W_A" >/dev/null 2>&1; then
  pass "root IDENTITY.md with template markers is skipped (no false-positive)"
else
  fail "root IDENTITY.md should be skipped but gate exited non-zero"
fi

# ============================================================================
echo ""
echo "--- Test B: Script skips 18-proactive-agent/upstream-original/assets/SOUL.md ---"
W_B="$(mktemp -d)"
trap 'rm -rf "$W_A" "$W_B" 2>/dev/null || true' EXIT
_clean_workspace "$W_B"
mkdir -p "$W_B/18-proactive-agent/upstream-original/assets"
cat > "$W_B/18-proactive-agent/upstream-original/assets/SOUL.md" <<'EOF'
# SOUL.md - Who I Am

> Customize this file with your agent's identity, principles, and boundaries.

I'm [Agent Name]. [One-line identity description].

{{OWNER_NAME}}
{{ROLE_TITLE}}
{{GENERATED_FOR}}
EOF
if bash "$SCRIPT" "$W_B" >/dev/null 2>&1; then
  pass "18-proactive-agent/upstream-original/assets/SOUL.md with template markers is skipped (no false-positive)"
else
  fail "18-proactive-agent/upstream-original/assets/SOUL.md should be skipped but gate exited non-zero"
fi

# ============================================================================
echo ""
echo "--- Test C: Non-excluded agent file with unresolved fill-in IS detected ---"
W_C="$(mktemp -d)"
trap 'rm -rf "$W_A" "$W_B" "$W_C" 2>/dev/null || true' EXIT
_clean_workspace "$W_C"
mkdir -p "$W_C/42-personal-assistant-library/specialists/01-test"
# Clean SOUL.md and IDENTITY.md for this agent, but put the fill-in prompt in SOUL.md
printf "# SOUL.md\n> Customize this file with your agent's identity, principles, and boundaries.\n## Principles\n" > "$W_C/42-personal-assistant-library/specialists/01-test/SOUL.md"
printf "# IDENTITY.md\n**Department:** Test\n**Version:** 1.0\n**Last updated:** 2026-07-23\n\n## Identity\nReal content.\n" > "$W_C/42-personal-assistant-library/specialists/01-test/IDENTITY.md"
if ! bash "$SCRIPT" "$W_C" >/dev/null 2>&1; then
  pass "non-excluded agent with unresolved fill-in prompt DETECTED (exit non-zero)"
else
  fail "non-excluded agent with unresolved fill-in prompt should have been detected but exited 0"
fi

# ============================================================================
echo ""
echo "--- Test D: Non-excluded agent file with {{GENERATED_FOR}} IS detected ---"
W_D="$(mktemp -d)"
trap 'rm -rf "$W_A" "$W_B" "$W_C" "$W_D" 2>/dev/null || true' EXIT
_clean_workspace "$W_D"
mkdir -p "$W_D/53-book-writer"
# Use SOUL.md (not IDENTITY.md, which is excluded for ALL paths by IDENTITY\.md$)
printf '# SOUL.md\n## Voice\nGenerated for: {{GENERATED_FOR}}\n' > "$W_D/53-book-writer/SOUL.md"
printf "# IDENTITY.md\n**Department:** Books\n**Version:** 1.0\n**Last updated:** 2026-07-23\n\n## Identity\nReal content.\n" > "$W_D/53-book-writer/IDENTITY.md"
if ! bash "$SCRIPT" "$W_D" >/dev/null 2>&1; then
  pass "non-excluded agent with {{GENERATED_FOR}} DETECTED (exit non-zero)"
else
  fail "non-excluded agent with {{GENERATED_FOR}} should have been detected but exited 0"
fi

# ============================================================================
echo ""
echo "=== assert-agent-identities-resolved.test.sh: $([ "$FAIL" -eq 0 ] && echo 'ALL ASSERTIONS PASSED' || echo 'FAILED') ==="
exit $FAIL
