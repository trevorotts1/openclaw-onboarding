#!/usr/bin/env bash
# tests/unit/whatsapp-ban.test.sh
#
# CI guard: verifies that WhatsApp is permanently banned from the fleet.
# This test hard-fails if WhatsApp is re-introduced to any allowable configuration
# in the onboarding repo. See FLEET-STANDARDS.md §3 and KNOWN-ISSUES.md §5.
#
# Assertions:
#   (A) apply-fleet-standards.sh CANONICAL block must NOT have whatsapp.enabled=true
#   (B) install.sh must contain the WhatsApp ban enforcement step
#   (C) FLEET-STANDARDS.md must contain the WhatsApp ban policy
#   (D) KNOWN-ISSUES.md must document the WhatsApp auto-install issue
#   (E) No file in the repo (excluding docs/workarounds) should set
#       plugins.entries.whatsapp.enabled = true in a config template
#
# Add a new assertion here any time a new allowable-skills or plugin config
# is introduced that could re-enable WhatsApp.

set -euo pipefail

PASS=0
FAIL=0
ERRORS=()

ok() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo ""
echo "=== WhatsApp ban guard (fleet-wide enforcement) ==="
echo ""

# ─── (A) apply-fleet-standards.sh CANONICAL must disable whatsapp ────────────
echo "--- (A) apply-fleet-standards.sh CANONICAL block ---"
AFS="$REPO_ROOT/scripts/apply-fleet-standards.sh"
if [ ! -f "$AFS" ]; then
  fail "(A) apply-fleet-standards.sh not found at $AFS"
else
  # The CANONICAL dict must contain "whatsapp" with enabled: False
  if grep -q '"whatsapp"' "$AFS" && grep -q 'False' "$AFS"; then
    ok "(A) apply-fleet-standards.sh contains whatsapp disable block"
  else
    fail "(A) apply-fleet-standards.sh is missing the whatsapp ban block — add it to the CANONICAL dict"
  fi
  # Must NOT have enabled: True for whatsapp anywhere
  if grep -A5 '"whatsapp"' "$AFS" | grep -q '"enabled".*True'; then
    fail "(A) apply-fleet-standards.sh has whatsapp enabled=True — REGRESSION"
  else
    ok "(A) apply-fleet-standards.sh does not enable whatsapp"
  fi
  # QC guard must be present
  if grep -q 'whatsapp-ban.*QC\|WhatsApp ban QC\|WAQCEOF' "$AFS"; then
    ok "(A) apply-fleet-standards.sh contains whatsapp ban QC guard"
  else
    fail "(A) apply-fleet-standards.sh is missing the whatsapp ban QC guard (hard-fail after merge)"
  fi
fi

# ─── (B) install.sh must contain the WhatsApp ban step ───────────────────────
echo ""
echo "--- (B) install.sh WhatsApp ban step ---"
INSTALL="$REPO_ROOT/install.sh"
if [ ! -f "$INSTALL" ]; then
  fail "(B) install.sh not found"
else
  if grep -q 'whatsapp.*ban\|WhatsApp.*ban\|WHATSAPP.*ban\|WABPYEOF' "$INSTALL"; then
    ok "(B) install.sh contains WhatsApp ban enforcement step"
  else
    fail "(B) install.sh is missing the WhatsApp ban enforcement step — add it before the gateway restart"
  fi
  if grep -q 'WHATSAPP_NUMBER.*PERMANENTLY DISABLED\|whatsapp-ban.*PERMANENTLY' "$INSTALL"; then
    ok "(B) install.sh comments out WHATSAPP_NUMBER in VPS .env"
  else
    fail "(B) install.sh does not comment out WHATSAPP_NUMBER in VPS .env — add the Layer 2 fix"
  fi
fi

# ─── (C) FLEET-STANDARDS.md must document the ban ───────────────────────────
echo ""
echo "--- (C) FLEET-STANDARDS.md policy ---"
FS="$REPO_ROOT/FLEET-STANDARDS.md"
if [ ! -f "$FS" ]; then
  fail "(C) FLEET-STANDARDS.md not found"
else
  if grep -qi 'WhatsApp.*Permanently Banned\|WhatsApp.*Ban\|whatsapp.*banned' "$FS"; then
    ok "(C) FLEET-STANDARDS.md contains the WhatsApp ban policy"
  else
    fail "(C) FLEET-STANDARDS.md is missing the WhatsApp ban policy — add it as a fleet standard"
  fi
fi

# ─── (D) KNOWN-ISSUES.md must document the WhatsApp loop ────────────────────
echo ""
echo "--- (D) KNOWN-ISSUES.md documentation ---"
KI="$REPO_ROOT/KNOWN-ISSUES.md"
if [ ! -f "$KI" ]; then
  fail "(D) KNOWN-ISSUES.md not found"
else
  if grep -qi 'WhatsApp auto-install\|whatsapp.*crash.*loop\|whatsapp.*boot.*loop' "$KI"; then
    ok "(D) KNOWN-ISSUES.md documents the WhatsApp auto-install crash-loop"
  else
    fail "(D) KNOWN-ISSUES.md is missing WhatsApp auto-install documentation — add it as issue #5"
  fi
fi

# ─── (E) No config template should enable whatsapp ──────────────────────────
echo ""
echo "--- (E) No config template enables whatsapp ---"
# Search for JSON/config files (excluding tests, docs, role-library prose) that
# could set plugins.entries.whatsapp.enabled = true
_bad_files=()
while IFS= read -r -d '' _f; do
  # Skip this test file itself and documentation/prose files
  case "$_f" in
    *tests/*|*CHANGELOG*|*KNOWN-ISSUES*|*FLEET-STANDARDS*|*.md) continue ;;
  esac
  if grep -q '"whatsapp"' "$_f" 2>/dev/null; then
    if grep -A3 '"whatsapp"' "$_f" | grep -q '"enabled".*true\|"enabled": true'; then
      _bad_files+=("$_f")
    fi
  fi
done < <(find "$REPO_ROOT" -type f \( -name "*.json" -o -name "*.sh" -o -name "*.mjs" -o -name "*.js" \) \
  -not -path "*/.claude/*" -not -path "*/node_modules/*" -print0 2>/dev/null)

if [ "${#_bad_files[@]}" -gt 0 ]; then
  for _bf in "${_bad_files[@]}"; do
    fail "(E) Config file enables whatsapp: $_bf"
  done
else
  ok "(E) No config template or script enables whatsapp"
fi

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "FAILURES:"
  for _e in "${ERRORS[@]}"; do
    echo "  - $_e"
  done
  echo ""
  echo "WhatsApp is permanently banned fleet-wide (FLEET-STANDARDS.md §3)."
  echo "Fix all failures above before merging."
  exit 1
fi

echo "All WhatsApp ban guards passed."
exit 0
