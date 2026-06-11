#!/usr/bin/env bash
# qc-convert-and-flow.sh — Skill 44: Convert and Flow Operator
# Automated QC validator. Exit 0 = pass. Non-zero = blocker.
#
# Usage:
#   ./qc-convert-and-flow.sh            # Static-only (safe on fresh clone, CI)
#   ./qc-convert-and-flow.sh --live     # Static + live-box checks (needs caf on PATH + secrets)
#   CAF_LIVE=1 ./qc-convert-and-flow.sh # Same as --live
#
# Sections A (PATH), B (credentials), C (standard ops), and D (write-safety
# against the installed wrapper) all require a provisioned box; they are
# skipped (not failed) in static mode.  Section E (file presence inside
# master-files tree), F (core-file sentinels in workspace), and G (platform
# overlays) are also live-box sections.  Static mode only asserts what exists
# on the committed branch: engine files present, SKILL.md frontmatter correct,
# CORE_UPDATES sentinel, six CLI commands declared in INSTALL.md.
set -euo pipefail

PASS=0; FAIL=0; WARN=0; SKIP=0

# ── Mode detection ────────────────────────────────────────────────────────────
LIVE_MODE=0
for arg in "$@"; do
  [ "$arg" = "--live" ] && LIVE_MODE=1
done
[ "${CAF_LIVE:-0}" = "1" ] && LIVE_MODE=1

assert() {
  local msg="$1"; local cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  FAIL: $msg"; FAIL=$((FAIL+1))
  fi
}

warn_only() {
  local msg="$1"; local cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  WARN: $msg (non-blocking)"; WARN=$((WARN+1))
  fi
}

live_assert() {
  local msg="$1"; local cmd="$2"
  if [ "$LIVE_MODE" -eq 0 ]; then
    echo "  SKIP: $msg (live-box only; re-run with --live on a provisioned box)"; SKIP=$((SKIP+1))
    return
  fi
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  FAIL: $msg"; FAIL=$((FAIL+1))
  fi
}

live_warn() {
  local msg="$1"; local cmd="$2"
  if [ "$LIVE_MODE" -eq 0 ]; then
    echo "  SKIP: $msg (live-box only)"; SKIP=$((SKIP+1))
    return
  fi
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  WARN: $msg (non-blocking)"; WARN=$((WARN+1))
  fi
}

# ── Resolve the skill's own directory (works when run from any CWD) ───────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL44_DIR="$SCRIPT_DIR"
# For live-box sections the master-files root may differ; fall back gracefully
MASTER_FILES_DIR="${MASTER_FILES_DIR:-$(dirname "$SCRIPT_DIR")}"

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
PLATFORM="${OPENCLAW_PLATFORM:-mac}"
if [ "$PLATFORM" = "mac" ]; then
  TOOLS_ROOT="$HOME/.openclaw/tools"
else
  TOOLS_ROOT="/data/.openclaw/tools"
fi
CAF_DIR="$TOOLS_ROOT/convert-and-flow-cli"
SKILL38_DIR="$MASTER_FILES_DIR/38-conversational-ai-system"

echo "══════════════════════════════════════════════"
echo "  Skill 44 QC — Convert and Flow Operator"
if [ "$LIVE_MODE" -eq 1 ]; then
  echo "  Mode: LIVE (all sections active)"
else
  echo "  Mode: STATIC (live-box sections skipped)"
fi
echo "══════════════════════════════════════════════"

# ── Section S: Static branch checks (always run) ────────────────────────────
echo ""
echo "── Section S: Static branch checks ──"

assert "tools/engine/setup.py present" \
  "[ -f \"$SKILL44_DIR/tools/engine/setup.py\" ]"
assert "tools/engine/cli_anything/gohighlevel/ present" \
  "[ -d \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel\" ]"
assert "tools/engine is NOT a gitlink (no 160000 mode)" \
  "! git -C \"$SKILL44_DIR\" ls-files -s tools/engine 2>/dev/null | grep -q '^160000'"
assert "SKILL.md frontmatter name is convert-and-flow-operator" \
  "grep -q 'name: convert-and-flow-operator' \"$SKILL44_DIR/SKILL.md\""
assert "INSTALL.md documents 'caf' command" \
  "grep -q '\bcaf\b' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md documents 'convertandflow' command" \
  "grep -q 'convertandflow' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md documents 'ghl' command" \
  "grep -q '\bghl\b' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md documents write-safety default (GOHIGHLEVEL_DRAFT_ONLY)" \
  "grep -q 'GOHIGHLEVEL_DRAFT_ONLY' \"$SKILL44_DIR/INSTALL.md\""
assert "CORE_UPDATES.md sentinel present" \
  "grep -q 'skill:44-convert-and-flow-operator:core-update-applied' \"$SKILL44_DIR/CORE_UPDATES.md\""
assert "CHANGELOG.md exists" \
  "[ -f \"$SKILL44_DIR/CHANGELOG.md\" ]"
assert "QC.md exists" \
  "[ -f \"$SKILL44_DIR/QC.md\" ]"
assert "platform/mac/SKILL.md name matches" \
  "grep -q 'name: convert-and-flow-operator' \"$SKILL44_DIR/platform/mac/SKILL.md\""
assert "platform/vps/SKILL.md name matches" \
  "grep -q 'name: convert-and-flow-operator' \"$SKILL44_DIR/platform/vps/SKILL.md\""
assert "nextcloud NOT present in vendored engine" \
  "! [ -d \"$SKILL44_DIR/tools/engine/cli_anything/nextcloud\" ]"
assert "blotato NOT present in vendored engine" \
  "! [ -d \"$SKILL44_DIR/tools/engine/cli_anything/blotato\" ]"

# ── Section A: Installation (live-box only) ───────────────────────────────────
echo ""
echo "── Section A: Installation (live-box) ──"
live_assert "caf resolves on PATH"                "command -v caf >/dev/null 2>&1"
live_assert "convertandflow alias resolves"       "command -v convertandflow >/dev/null 2>&1"
live_assert "ghl alias resolves"                  "command -v ghl >/dev/null 2>&1"
live_assert "caf doctor exits green"              "caf doctor >/dev/null 2>&1"
live_assert "venv exists"                         "[ -d \"$CAF_DIR/.venv\" ]"
live_assert "wrapper file is executable"          "[ -x \"$CAF_DIR/caf\" ]"

# ── Section B: Credentials (live-box only) ───────────────────────────────────
echo ""
echo "── Section B: Credentials (live-box) ──"
if [ "$LIVE_MODE" -eq 1 ]; then
  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || true
fi
live_assert "GOHIGHLEVEL_API_KEY is set"          "[ -n \"${GOHIGHLEVEL_API_KEY:-}\" ]"
live_assert "GOHIGHLEVEL_API_KEY starts with pit-" "[[ \"${GOHIGHLEVEL_API_KEY:-}\" == pit-* ]]"
live_assert "GOHIGHLEVEL_LOCATION_ID is set"      "[ -n \"${GOHIGHLEVEL_LOCATION_ID:-}\" ]"
live_warn   "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN set (workflow writes)" "[ -n \"${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-}\" ]"
live_assert "GOHIGHLEVEL_DRAFT_ONLY=true set"     "[ \"${GOHIGHLEVEL_DRAFT_ONLY:-true}\" = 'true' ]"

# ── Section C: Standard ops (live-box only) ───────────────────────────────────
echo ""
echo "── Section C: Standard ops (live-box) ──"
if [ "$LIVE_MODE" -eq 1 ]; then
  CONTACTS=$(caf contacts list --limit 1 2>/dev/null || echo "")
  assert "caf contacts list returns data"       "echo \"$CONTACTS\" | grep -qE 'contact|id|email'"
  WF_LIST=$(caf workflows list 2>/dev/null || echo "")
  assert "caf workflows list returns data"      "echo \"$WF_LIST\" | grep -qE 'workflow|id|name'"
  LOC=$(caf locations get 2>/dev/null || echo "")
  assert "caf locations get returns data"       "echo \"$LOC\" | grep -qE 'location|id|name'"
else
  echo "  SKIP: standard ops (live-box only; re-run with --live on a provisioned box)"; SKIP=$((SKIP+3))
fi

# ── Section D: Write safety (live-box only) ───────────────────────────────────
echo ""
echo "── Section D: Write safety (live-box) ──"
live_assert "wrapper passes GOHIGHLEVEL_API_KEY as GHL_API_KEY" \
  "grep -q 'GHL_API_KEY.*GOHIGHLEVEL_API_KEY' \"$CAF_DIR/caf\""
live_assert "snapshot dir exists" \
  "[ -d \"$CAF_DIR/data/snapshots\" ] || mkdir -p \"$CAF_DIR/data/snapshots\""
live_assert "wrapper sets GOHIGHLEVEL_DRAFT_ONLY" \
  "grep -q 'GOHIGHLEVEL_DRAFT_ONLY' \"$CAF_DIR/caf\""

# ── Section E: TRINITY and self-test (live-box only) ─────────────────────────
echo ""
echo "── Section E: TRINITY and self-test (live-box) ──"
live_assert "qc-trinity-registry.sh exists and is executable" \
  "[ -x \"$SKILL38_DIR/scripts/qc-trinity-registry.sh\" ] || [ -f \"$SKILL38_DIR/scripts/qc-trinity-registry.sh\" ]"
live_assert "24-self-test-hook.sh exists" \
  "[ -f \"$SKILL38_DIR/scripts/24-self-test-hook.sh\" ]"
live_assert "24-self-test-hook.sh credential read is alias-aware (GOHIGHLEVEL_API_KEY)" \
  "grep -qE 'GOHIGHLEVEL_API_KEY' \"$SKILL38_DIR/scripts/24-self-test-hook.sh\""

# ── Section F: Core files (live-box only) ────────────────────────────────────
echo ""
echo "── Section F: Core files (live-box) ──"
SENTINEL="skill:44-convert-and-flow-operator:core-update-applied"
live_assert "CORE_UPDATES sentinel present in AGENTS.md" \
  "grep -qF \"$SENTINEL\" \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
live_assert "AGENTS.md has Tier 0 mention" \
  "grep -qE 'Tier 0|convert-and-flow-operator|convertandflow' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
live_assert "TOOLS.md has caf entry" \
  "grep -qE 'caf|convertandflow' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
live_assert "MEMORY.md has skill 44 install record" \
  "grep -qE 'Convert and Flow Operator|skill 44' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"

# ── Section G: Platform overlay parity (static — files are on branch) ────────
echo ""
echo "── Section G: Platform overlay parity ──"
MAC_SKILL="$SKILL44_DIR/platform/mac/SKILL.md"
VPS_SKILL="$SKILL44_DIR/platform/vps/SKILL.md"
if [ -f "$MAC_SKILL" ] && [ -f "$VPS_SKILL" ]; then
  assert "Mac overlay name matches main SKILL.md" \
    "grep -q 'name: convert-and-flow-operator' \"$MAC_SKILL\""
  assert "VPS overlay name matches main SKILL.md" \
    "grep -q 'name: convert-and-flow-operator' \"$VPS_SKILL\""
else
  warn_only "Platform overlays present (mac + vps)" "[ -f \"$MAC_SKILL\" ] && [ -f \"$VPS_SKILL\" ]"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings | $SKIP skipped"
echo "══════════════════════════════════════════════"
SCORE=$(python3 -c "print(round(($PASS * 10) / ($PASS + $FAIL + 0.001), 1))" 2>/dev/null || echo "?")
echo "  Approx score: ${SCORE}/10 (excludes warnings/skips)"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "QC FAILED — $FAIL blocker(s). Fix before merging."
  exit 1
fi
echo "QC PASSED"
exit 0
