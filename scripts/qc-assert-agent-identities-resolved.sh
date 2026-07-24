#!/usr/bin/env bash
set -euo pipefail
# U060 — Block activation of any agent whose SOUL.md / IDENTITY.md still
# matches generator template. Gate: exit 0 if all resolved, exit 1 otherwise.
#
# Usage:
#   bash scripts/qc-assert-agent-identities-resolved.sh [ROOT]
#   bash scripts/qc-assert-agent-identities-resolved.sh --json [ROOT]
#   bash scripts/qc-assert-agent-identities-resolved.sh --self-test

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JSON_MODE=0
SELF_TEST=0
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

for arg in "$@"; do
  case "$arg" in
    --json)      JSON_MODE=1 ;;
    --self-test) SELF_TEST=1 ;;
    --help|-h)   echo "Usage: $0 [--json] [--self-test] [ROOT]"; exit 0 ;;
    *)           ROOT="$arg" ;;
  esac
done

# ── Self-test ────────────────────────────────────────────────────────────
if [ "$SELF_TEST" -eq 1 ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  fails=0; ok() { printf '  [PASS] %s\n' "$1"; }; bad() { printf '  [FAIL] %s\n' "$1"; fails=$((fails + 1)); }

  # 1. Clean workspace passes.
  mkdir -p "$TMP/42-personal-assistant-library/specialists/01-test"
  mkdir -p "$TMP/54-anthology-writer"
  printf '# SOUL.md\n## Voice\nResolved agent voice. No placeholders.\n' > "$TMP/42-personal-assistant-library/specialists/01-test/SOUL.md"
  printf "# IDENTITY.md\n**Department:** Test\n**Version:** 1.0\n**Last updated:** 2026-07-23\n**Generated for:** the company\n\n## Identity\nReal content.\n" > "$TMP/42-personal-assistant-library/specialists/01-test/IDENTITY.md"
  printf '# Anthology Writer SOUL\n' > "$TMP/54-anthology-writer/SOUL.md"
  printf '# Anthology Writer IDENTITY\n' > "$TMP/54-anthology-writer/IDENTITY.md"
  if bash "$0" "$TMP" >/dev/null 2>&1; then ok "clean workspace PASS (exit 0)"; else bad "clean workspace FAIL (expected exit 0)"; fi

  # 2. Mutation: {{GENERATION_DATE}} triggers FAIL.
  printf '# SOUL.md\n**Last updated:** {{GENERATION_DATE}}\n## Voice\n' > "$TMP/42-personal-assistant-library/specialists/01-test/SOUL.md"
  if ! bash "$0" "$TMP" >/dev/null 2>&1; then ok "{{GENERATION_DATE}} FAILS (exit non-zero)"; else bad "{{GENERATION_DATE}} should have failed but exited 0"; fi

  # 3. Mutation: fill-in prompt triggers FAIL.
  printf "# SOUL.md\n> Customize this file with your agent's identity, principles, and boundaries.\n## Principles\n" > "$TMP/42-personal-assistant-library/specialists/01-test/SOUL.md"
  if ! bash "$0" "$TMP" >/dev/null 2>&1; then ok "fill-in prompt FAILS (exit non-zero)"; else bad "fill-in prompt should have failed but exited 0"; fi

  # 4. Revert to clean, then mutation: missing required file fails.
  printf '# SOUL.md\n## Voice\nFully resolved.\n' > "$TMP/42-personal-assistant-library/specialists/01-test/SOUL.md"
  rm -f "$TMP/54-anthology-writer/SOUL.md"
  if ! bash "$0" "$TMP" >/dev/null 2>&1; then ok "missing required SOUL.md FAILS (exit non-zero)"; else bad "missing SOUL.md should have failed but exited 0"; fi

  # 5. Mutation: {{OWNER_NAME}} (body text marker) triggers FAIL.
  printf '# SOUL.md\n## Voice\nFully resolved.\n' > "$TMP/42-personal-assistant-library/specialists/01-test/SOUL.md"
  printf '# SOUL.md\n' > "$TMP/54-anthology-writer/SOUL.md"
  printf '# SOUL.md\nYou speak with {{OWNER_NAME}} warmth.\n' > "$TMP/42-personal-assistant-library/specialists/01-test/SOUL.md"
  if ! bash "$0" "$TMP" >/dev/null 2>&1; then ok "{{OWNER_NAME}} FAILS (exit non-zero)"; else bad "{{OWNER_NAME}} should have failed but exited 0"; fi

  echo "=== qc-assert-agent-identities-resolved.sh --self-test: $([ "$fails" -eq 0 ] && echo 'ALL ASSERTIONS PASSED' || echo 'FAILED') ==="
  exit $fails
fi

FAILURES=()

# A. Literal generator fill-in prompts (grep -E regex)
FILL_IN_PATTERNS=(
  'Fill this in during your first conversation\. Make it yours\.'
  "I'm \[Agent Name\]\. \[One-line identity description\]\."
  'Help \[Human Name\] \[achieve their primary goal\]\.'
  "Customize this file with your agent's identity, principles, and boundaries\."
)

# B. Unresolved template variables (grep -F fixed string)
UNRESOLVED_VARS=(
  '{{GENERATION_DATE}}'
  '{{COMPANY_INDUSTRY}}'
  '{{ASSIGNED_PERSONA_VERSION}}'
)

# C. "Generated for:" with bare template token (grep -E regex)
UNRESOLVED_GENFOR=(
  'Generated for:.*\{\{TOKEN\}\}'
  'Generated for:.*\{\{COMPANY_NAME\}\}'
)

# C2. Comprehensive: ANY {{VARIABLE}} template marker anywhere in body text.
# Catches ALL generator placeholders: {{OWNER_NAME}}, {{ROLE_TITLE}},
# {{EMAIL_TOOL}}, {{DOCS_TOOL}}, etc.
UNRESOLVED_ANY_MARKER_RE='\{\{[A-Za-z_][A-Za-z0-9_]*\}\}'

# D. Required agent files (must exist)
REQUIRED_FILES=(
  '54-anthology-writer/SOUL.md'
  '54-anthology-writer/IDENTITY.md'
)

mapfile -t ID_FILES < <(find "$ROOT" -type f \( -name 'SOUL.md' -o -name 'IDENTITY.md' \) -not -path '*/.claude/*' 2>/dev/null | sort)

# Files intentionally left as user-fillable templates (not unresolved)
#   - Root IDENTITY.md: workspace identity — user fills in at first use
#   - 18-proactive-agent/assets/SOUL.md: upstream original — user customizes
USER_TEMPLATE_PATTERNS=(
  'IDENTITY\.md$'
  '18-proactive-agent/upstream-original/assets/SOUL\.md$'
)
_is_user_template() {
  local rel="$1"
  for p in "${USER_TEMPLATE_PATTERNS[@]}"; do
    if [[ "$rel" =~ $p ]]; then return 0; fi
  done
  return 1
}

# Check 1: Required files exist
for rf in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$ROOT/$rf" ]]; then
    FAILURES+=("missing-required-file:$rf")
  fi
done

# Check 2: Literal fill-in prompts (skip intentional user templates)
for f in "${ID_FILES[@]}"; do
  rel="${f#$ROOT/}"
  if _is_user_template "$rel"; then continue; fi
  for pat in "${FILL_IN_PATTERNS[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      FAILURES+=("unresolved-fill-in:$rel")
      break
    fi
  done
done

# Check 3: Template variables (skip intentional user templates)
for f in "${ID_FILES[@]}"; do
  rel="${f#$ROOT/}"
  if _is_user_template "$rel"; then continue; fi
  for var in "${UNRESOLVED_VARS[@]}"; do
    if grep -qF "$var" "$f" 2>/dev/null; then
      FAILURES+=("unresolved-var:$rel:$var")
      break
    fi
  done
done

# Check 4: Generated-for with template token (skip intentional user templates)
for f in "${ID_FILES[@]}"; do
  rel="${f#$ROOT/}"
  if _is_user_template "$rel"; then continue; fi
  for pat in "${UNRESOLVED_GENFOR[@]}"; do
    if grep -qE "$pat" "$f" 2>/dev/null; then
      FAILURES+=("unresolved-generated-for:$rel")
      break
    fi
  done
done

# Check 5: Comprehensive {{}} template marker scan (skip intentional user templates)
for f in "${ID_FILES[@]}"; do
  rel="${f#$ROOT/}"
  if _is_user_template "$rel"; then continue; fi
  if grep -qE "$UNRESOLVED_ANY_MARKER_RE" "$f" 2>/dev/null; then
    markers_found=$(grep -oE "$UNRESOLVED_ANY_MARKER_RE" "$f" 2>/dev/null | sort -u | tr '\n' ' ' | sed 's/ $//')
    FAILURES+=("unresolved-template-marker:$rel:[$markers_found]")
  fi
done

# Output
if [[ ${#FAILURES[@]} -eq 0 ]]; then
  if [[ "$JSON_MODE" -eq 1 ]]; then echo '[]'; else echo "PASS: All agent identity files are resolved."; fi
  exit 0
fi

if [[ "$JSON_MODE" -eq 1 ]]; then
  printf '['; for i in "${!FAILURES[@]}"; do printf '"%s"' "${FAILURES[$i]}"; [[ $i -lt $((${#FAILURES[@]} - 1)) ]] && printf ','; done; printf ']\n'
else
  echo "FAIL: ${#FAILURES[@]} unresolved agent identity file(s) found:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
fi
exit 1
