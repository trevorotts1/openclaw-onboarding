#!/bin/bash
#
# materialize-dept-agents-company-scope.test.sh
#
# 2026-08-04 "WANTED Woman" incident follow-up. materialize-dept-agents.sh's
# canonical ZHC dept scan used to iterate EVERY company subdirectory under
# zero-human-company/ with no scoping at all:
#
#   for _company_dir in "$_mf_root"/*/; do ...
#
# On an operator/demo box that hosts more than one client's ZHC build side by
# side, that registered ALL of their departments into THIS box's single
# openclaw.json agents.list[] — not just the box's own. This test proves the
# fix: the scan is now scoped to the box's own company slug (resolved from
# .workforce-build-state.json's companySlug/clientSlug, same convention
# run-full-install.sh / seed-workspaces.py already use), and only falls back
# to the old glob-all behavior (with a loud warning) when that slug cannot be
# resolved at all.
#
# Usage:
#   bash 32-command-center-setup/scripts/materialize-dept-agents-company-scope.test.sh
#
# Pass criteria (all must hold):
#   1. bash -n materialize-dept-agents.sh passes.
#   2. With companySlug set in build-state: only THIS box's own company's
#      department folders are scanned/registered; a second company's
#      department folder on the same box is NEVER mentioned.
#   3. Without a resolvable companySlug: the OLD glob-all behavior is
#      preserved (both companies scanned) — no regression for boxes that
#      predate this field — AND a loud warning is printed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/32-command-center-setup/scripts/materialize-dept-agents.sh"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

# ─── GUARD: bash -n ───────────────────────────────────────────────────────────
bash -n "$SCRIPT" || fail "bash -n materialize-dept-agents.sh failed"
pass "bash -n materialize-dept-agents.sh passes"

# ─── Hermetic fixture: a fake $HOME with its own .openclaw + ZHC tree ────────
setup_fixture() {
  local tmp
  tmp="$(mktemp -d)"
  mkdir -p "$tmp/.openclaw/workspace"
  echo '{"agents":{"list":[]}}' > "$tmp/.openclaw/openclaw.json"

  # Two DIFFERENT companies' ZHC builds sharing the same box (the hazard case).
  mkdir -p "$tmp/Downloads/openclaw-master-files/zero-human-company/wanted-woman/departments/marketing"
  echo 'role-definition' > "$tmp/Downloads/openclaw-master-files/zero-human-company/wanted-woman/departments/marketing/role-definition.md"
  mkdir -p "$tmp/Downloads/openclaw-master-files/zero-human-company/other-client/departments/legal"
  echo 'role-definition' > "$tmp/Downloads/openclaw-master-files/zero-human-company/other-client/departments/legal/role-definition.md"

  printf '%s' "$tmp"
}

# ─── Test 1: companySlug resolvable — scoped to THIS box's own company ───────
TMP1="$(setup_fixture)"
trap 'rm -rf "$TMP1"' EXIT
printf '{"interviewComplete": true, "companySlug": "wanted-woman"}' > "$TMP1/.openclaw/workspace/.workforce-build-state.json"

OUT1="$(HOME="$TMP1" bash "$SCRIPT" --dry-run 2>&1)" || fail "Test 1: script exited non-zero: $OUT1"

echo "$OUT1" | grep -q "scoping the canonical ZHC dept scan to this box's own company: wanted-woman" \
  || fail "Test 1: expected the company-scope log line, got: $OUT1"
echo "$OUT1" | grep -q "including ZHC dept path:.*wanted-woman/departments" \
  || fail "Test 1: expected wanted-woman's departments path to be scanned, got: $OUT1"
echo "$OUT1" | grep -q "dept-marketing" \
  || fail "Test 1: expected dept-marketing (wanted-woman's own dept) to be discovered, got: $OUT1"
if echo "$OUT1" | grep -qi "other-client\|dept-legal"; then
  fail "Test 1: FOREIGN company 'other-client' / its 'legal' dept leaked into the scan — cross-company glob hazard NOT fixed. Output: $OUT1"
fi
pass "Test 1: company-scoped scan registers ONLY the box's own company's departments (other-client never mentioned)"

rm -rf "$TMP1"
trap - EXIT

# ─── Test 2: no resolvable companySlug — falls back to glob-all (with warning), no regression ──
TMP2="$(setup_fixture)"
trap 'rm -rf "$TMP2"' EXIT
printf '{"interviewComplete": true}' > "$TMP2/.openclaw/workspace/.workforce-build-state.json"

OUT2="$(HOME="$TMP2" bash "$SCRIPT" --dry-run 2>&1)" || fail "Test 2: script exited non-zero: $OUT2"

echo "$OUT2" | grep -qi "could not resolve this box's own company slug" \
  || fail "Test 2: expected the no-slug-resolved warning, got: $OUT2"
echo "$OUT2" | grep -q "dept-marketing" \
  || fail "Test 2: fallback must still discover wanted-woman's marketing dept, got: $OUT2"
echo "$OUT2" | grep -q "dept-legal" \
  || fail "Test 2: fallback (no scoping possible) must preserve the OLD glob-all behavior — other-client's legal dept must still be found, got: $OUT2"
pass "Test 2: with no resolvable company slug, falls back to the old glob-all behavior (no regression) and warns loudly"

rm -rf "$TMP2"
trap - EXIT

echo ""
echo "All materialize-dept-agents.sh company-scope tests passed."
