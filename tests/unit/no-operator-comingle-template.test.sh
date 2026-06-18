#!/usr/bin/env bash
# tests/unit/no-operator-comingle-template.test.sh
#
# REGRESSION GUARD (v12.4.0): fails the build if a CLIENT-box template in this
# repo ships a hardcoded operator Telegram chat ID as a PROACTIVE SEND TARGET, or
# stamps the operator team as routed "workers" in a client routing template.
#
# This is the upstream backstop for the Fleet Operator Co-Mingling Audit
# (2026-06-18): the onboarding template must never regenerate the leak where
# every client box ships a `5252140759` proactive-send fallback or an operator
# dispatcher table.
#
# What is FLAGGED (build FAIL):
#   (A) Any `*.sh` line that uses an operator ID as a fallback DEFAULT for a send
#       target, e.g.  ${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}  or  v="5252140759"
#       used as a resolver terminal fallback, or `-t 5252140759` / `--target 5252140759`.
#   (B) Any CLIENT routing template (TEAM_CONFIG.md / WORKFLOW_AUTO templates in
#       skill 15) that lists an operator ID as a routed worker / reply-target.
#
# What is NOT flagged (CORRECT — must stay):
#   - The OPERATOR_CHAT_IDS / OPERATOR_IDS REJECTION sets (operator-rejecting
#     resolver, allowlist for the operator account). These compare/reject; they
#     never send.
#   - Operator IDs in openclaw.json allowFrom / groupAllowFrom config (inbound
#     operator access — legitimate).
#   - `case ... 5252140759|6663821679|6771245262)` operator-rejection guards.
#   - BANNED= privacy-scan denylists (qc-no-personal-data.sh) — those are guards.
#   - Comment lines, docs (*.md prose), and OPERATOR-BOX-ONLY gated content.
#   - Test fixtures under tests/ (they assert the rejection behavior).
#
# Exit 0 = pass. Exit 1 = a co-mingling template regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

OP_IDS='5252140759|6663821679|6771245262'

echo "=== no-operator-comingle-template.test.sh ==="
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# (A) No operator ID used as a SEND-TARGET fallback default in any *.sh
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (A) No hardcoded operator ID as a send-target fallback in scripts ---"

# Scan all tracked .sh files EXCEPT the tests dir (fixtures assert rejection) and
# the rejection-set helpers/configurators that legitimately list operator IDs.
SH_FILES=$(find "$REPO_ROOT" \
  -path "$REPO_ROOT/.git" -prune -o \
  -path "$REPO_ROOT/tests" -prune -o \
  -name '*.sh' -print 2>/dev/null)

A_FAIL=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  rel="${f#$REPO_ROOT/}"
  # Drop comment lines, then look for operator IDs used as SEND targets / fallbacks.
  #   - `${VAR:-<opid>}`            (env fallback default to operator id)
  #   - `="<opid>"` / `=<opid>`     (resolver terminal fallback assignment)
  #   - `-t <opid>` / `--target <opid>` / `--to <opid>`  (literal send target)
  hits=$(grep -nE "$OP_IDS" "$f" 2>/dev/null \
    | grep -vE '^[0-9]+:[[:space:]]*#' \
    | grep -vE 'OPERATOR_CHAT_IDS|OPERATOR_IDS|OP_IDS_RE|op_ids|OPERATOR_CHAT_IDS_SH' \
    | grep -vE "case .*\)|[0-9]+:\s*(\"?5252140759\"?\|)" \
    | grep -vE 'BANNED=' \
    | grep -E ":-(${OP_IDS})|=[\"']?(${OP_IDS})[\"']?([^0-9]|$)|--?t(arget)?[[:space:]]+[\"']?(${OP_IDS})|--to[[:space:]]+[\"']?(${OP_IDS})" \
    || true)
  if [ -n "$hits" ]; then
    fail "$rel: operator ID used as a send-target / fallback default:"
    echo "$hits" | sed 's/^/        /'
    A_FAIL=1
  fi
done <<< "$SH_FILES"

if [ "$A_FAIL" -eq 0 ]; then
  pass "no operator ID is a send-target fallback default in any script"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (B) CLIENT routing templates must be owner-only (no operator IDs as workers)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (B) Client routing templates carry no operator IDs as routed workers ---"

# TEAM_CONFIG.md is shipped verbatim to client boxes (install.sh copies it). It
# must NOT contain operator IDs in any non-comment, non-OPERATOR-BOX-gated line.
TEAM_CONFIG="$REPO_ROOT/15-blackceo-team-management/TEAM_CONFIG.md"
if [ -f "$TEAM_CONFIG" ]; then
  # Strip markdown comment lines (# ...) and flag any remaining operator ID.
  tc_hits=$(grep -nE "$OP_IDS" "$TEAM_CONFIG" 2>/dev/null \
    | grep -vE '^[0-9]+:[[:space:]]*#' || true)
  if [ -n "$tc_hits" ]; then
    fail "TEAM_CONFIG.md ships operator IDs in client routing (must be owner-only / {{OWNER_CHAT_ID}}):"
    echo "$tc_hits" | sed 's/^/        /'
  else
    pass "TEAM_CONFIG.md is owner-only (no operator IDs in routing)"
  fi
else
  fail "TEAM_CONFIG.md not found at $TEAM_CONFIG"
fi

# The skill-15 CORE_UPDATES.md client-box stamping blocks must use the owner
# placeholder, not operator IDs, in any non-comment, non-OPERATOR-BOX line.
CORE_UPDATES="$REPO_ROOT/15-blackceo-team-management/CORE_UPDATES.md"
if [ -f "$CORE_UPDATES" ]; then
  # Lines under the "OPERATOR BOX ONLY" section are exempt; we approximate by
  # flagging any operator ID that appears (CORE_UPDATES should reference operators
  # only by description, never by raw ID, in the client-box blocks).
  cu_hits=$(grep -nE "$OP_IDS" "$CORE_UPDATES" 2>/dev/null || true)
  if [ -n "$cu_hits" ]; then
    fail "CORE_UPDATES.md client-box blocks contain a raw operator ID (use {{OWNER_CHAT_ID}}):"
    echo "$cu_hits" | sed 's/^/        /'
  else
    pass "CORE_UPDATES.md client-box blocks use the owner placeholder (no raw operator IDs)"
  fi
else
  fail "CORE_UPDATES.md not found at $CORE_UPDATES"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (C) Sanity: the central resolver defaults to EMPTY (no baked-in personal chat)
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (C) Central operator-chat resolver defaults to empty (opt-in) ---"

RESOLVER="$REPO_ROOT/shared-utils/operator-chat-id.sh"
if [ -f "$RESOLVER" ]; then
  if grep -qE "printf '%s' \"5252140759\"|v=\"5252140759\"" "$RESOLVER" 2>/dev/null; then
    fail "operator-chat-id.sh still hardcodes 5252140759 as a fallback default"
  else
    pass "operator-chat-id.sh has no hardcoded operator-id fallback default"
  fi
  if grep -q 'OPERATOR_ESCALATION_CHAT_ID' "$RESOLVER" 2>/dev/null; then
    pass "operator-chat-id.sh resolves the configurable OPERATOR_ESCALATION_CHAT_ID key"
  else
    fail "operator-chat-id.sh does not reference OPERATOR_ESCALATION_CHAT_ID"
  fi
else
  fail "operator-chat-id.sh not found at $RESOLVER"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — operator co-mingling template regression detected"
  exit 1
fi
echo "PASS: no operator co-mingling template regressions"
exit 0
