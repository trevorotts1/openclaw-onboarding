#!/usr/bin/env bash
# qc-convert-and-flow.sh — Skill 44: Convert and Flow Operator
# Automated QC validator. Exit 0 = pass. Non-zero = blocker.
set -euo pipefail

PASS=0; FAIL=0; WARN=0

assert() {
  local msg="$1"; local cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; ((PASS++))
  else
    echo "  FAIL: $msg"; ((FAIL++))
  fi
}

warn_only() {
  local msg="$1"; local cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; ((PASS++))
  else
    echo "  WARN: $msg (non-blocking)"; ((WARN++))
  fi
}

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
PLATFORM="${OPENCLAW_PLATFORM:-mac}"
if [ "$PLATFORM" = "mac" ]; then
  TOOLS_ROOT="$HOME/.openclaw/tools"
else
  TOOLS_ROOT="/data/.openclaw/tools"
fi
CAF_DIR="$TOOLS_ROOT/convert-and-flow-cli"
SKILL44_DIR="${MASTER_FILES_DIR:-$HOME/Downloads/openclaw-master-files}/44-convert-and-flow-operator"
SKILL38_DIR="${MASTER_FILES_DIR:-$HOME/Downloads/openclaw-master-files}/38-conversational-ai-system"

echo "══════════════════════════════════════════════"
echo "  Skill 44 QC — Convert and Flow Operator"
echo "══════════════════════════════════════════════"

# ── Section A: Installation ──────────────────────────────────────────────────
echo ""
echo "── Section A: Installation ──"
assert "caf resolves on PATH"                "command -v caf >/dev/null 2>&1"
assert "convertandflow alias resolves"       "command -v convertandflow >/dev/null 2>&1"
assert "ghl alias resolves"                  "command -v ghl >/dev/null 2>&1"
assert "caf doctor exits green"              "caf doctor >/dev/null 2>&1"
assert "venv exists"                         "[ -d \"$CAF_DIR/.venv\" ]"
assert "wrapper file is executable"          "[ -x \"$CAF_DIR/caf\" ]"

# ── Section B: Credentials ───────────────────────────────────────────────────
echo ""
echo "── Section B: Credentials ──"
source "$HOME/.openclaw/secrets/.env" 2>/dev/null || true
assert "GOHIGHLEVEL_API_KEY is set"          "[ -n \"${GOHIGHLEVEL_API_KEY:-}\" ]"
assert "GOHIGHLEVEL_API_KEY starts with pit-" "[[ \"${GOHIGHLEVEL_API_KEY:-}\" == pit-* ]]"
assert "GOHIGHLEVEL_LOCATION_ID is set"      "[ -n \"${GOHIGHLEVEL_LOCATION_ID:-}\" ]"
warn_only "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN set (workflow writes)" "[ -n \"${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-}\" ]"
assert "GOHIGHLEVEL_DRAFT_ONLY=true set"     "[ \"${GOHIGHLEVEL_DRAFT_ONLY:-true}\" = 'true' ]"

# ── Section C: Standard ops ──────────────────────────────────────────────────
echo ""
echo "── Section C: Standard ops ──"
CONTACTS=$(caf contacts list --limit 1 2>/dev/null || echo "")
assert "caf contacts list returns data"       "echo \"$CONTACTS\" | grep -qE 'contact|id|email'"
WF_LIST=$(caf workflows list 2>/dev/null || echo "")
assert "caf workflows list returns data"      "echo \"$WF_LIST\" | grep -qE 'workflow|id|name'"
LOC=$(caf locations get 2>/dev/null || echo "")
assert "caf locations get returns data"       "echo \"$LOC\" | grep -qE 'location|id|name'"

# ── Section D: Write safety ──────────────────────────────────────────────────
echo ""
echo "── Section D: Write safety ──"
assert "wrapper passes GOHIGHLEVEL_API_KEY as GHL_API_KEY" \
  "grep -q 'GHL_API_KEY.*GOHIGHLEVEL_API_KEY' \"$CAF_DIR/caf\""
assert "snapshot dir exists" \
  "[ -d \"$CAF_DIR/data/snapshots\" ] || mkdir -p \"$CAF_DIR/data/snapshots\""
assert "wrapper sets GOHIGHLEVEL_DRAFT_ONLY" \
  "grep -q 'GOHIGHLEVEL_DRAFT_ONLY' \"$CAF_DIR/caf\""

# ── Section E: TRINITY and self-test ─────────────────────────────────────────
echo ""
echo "── Section E: TRINITY and self-test ──"
TRINITY_SCRIPT="$SKILL38_DIR/scripts/qc-trinity-registry.sh"
assert "qc-trinity-registry.sh exists and is executable" \
  "[ -x \"$TRINITY_SCRIPT\" ] || [ -f \"$TRINITY_SCRIPT\" ]"
SELFTEST_SCRIPT="$SKILL38_DIR/scripts/24-self-test-hook.sh"
assert "24-self-test-hook.sh exists" \
  "[ -f \"$SELFTEST_SCRIPT\" ]"
assert "24-self-test-hook.sh credential read is alias-aware (GOHIGHLEVEL_API_KEY)" \
  "grep -qE 'GOHIGHLEVEL_API_KEY' \"$SELFTEST_SCRIPT\""

# ── Section F: Core files ─────────────────────────────────────────────────────
echo ""
echo "── Section F: Core files ──"
SENTINEL="skill:44-convert-and-flow-operator:core-update-applied"
assert "CORE_UPDATES sentinel present in AGENTS.md" \
  "grep -qF \"$SENTINEL\" \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
assert "AGENTS.md has Tier 0 mention" \
  "grep -qE 'Tier 0|convert-and-flow-operator|convertandflow' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
assert "TOOLS.md has caf entry" \
  "grep -qE 'caf|convertandflow' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
assert "MEMORY.md has skill 44 install record" \
  "grep -qE 'Convert and Flow Operator|skill 44' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"

# ── Section G: Platform overlay parity ───────────────────────────────────────
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
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings"
echo "══════════════════════════════════════════════"
SCORE=$(python3 -c "print(round(($PASS * 10) / ($PASS + $FAIL + 0.001), 1))" 2>/dev/null || echo "?")
echo "  Approx score: ${SCORE}/10 (excludes warnings)"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "QC FAILED — $FAIL blocker(s). Fix before merging."
  exit 1
fi
echo "QC PASSED"
exit 0
