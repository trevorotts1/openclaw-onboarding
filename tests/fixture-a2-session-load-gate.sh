#!/usr/bin/env bash
# Fixture test for scripts/a2-session-load-gate.sh
# Tests Case 1 (loaded=YES) and Case 2 (loaded=NO -> retry -> alert)
# No live OpenClaw required — stubs the openclaw binary.
#
# Usage: bash tests/fixture-a2-session-load-gate.sh
# Exit 0 = both cases passed. Exit 1 = at least one case failed.

set -euo pipefail

FIXTURE_DIR="/tmp/a2-fixture-$$"
PASS=0
FAIL=0

cleanup() {
  rm -rf "$FIXTURE_DIR"
}
trap cleanup EXIT

mkdir -p "$FIXTURE_DIR/workspace"
mkdir -p "$FIXTURE_DIR/agents/main/sessions"
mkdir -p "$FIXTURE_DIR/skills"

# ── Stub openclaw ─────────────────────────────────────────────────────────────
STUB_DIR="$FIXTURE_DIR/bin"
mkdir -p "$STUB_DIR"
RESET_LOG="$FIXTURE_DIR/reset-calls.log"

cat > "$STUB_DIR/openclaw" << 'STUB_EOF'
#!/usr/bin/env bash
# Stub openclaw binary for A.2 fixture tests
RESET_LOG="FIXTURE_DIR_PLACEHOLDER/reset-calls.log"
case "$1 $2" in
  "gateway call")
    echo '{"ok":true}'
    echo "$(date +%s) $*" >> "$RESET_LOG"
    exit 0
    ;;
  "message send")
    echo "ALERT_SENT: $*"
    exit 0
    ;;
  *)
    echo "STUB: unknown command: $*" >&2
    exit 1
    ;;
esac
STUB_EOF
chmod +x "$STUB_DIR/openclaw"
# Inject the real fixture dir path into the stub
if sed --version 2>/dev/null | grep -q GNU; then
  sed -i "s|FIXTURE_DIR_PLACEHOLDER|$FIXTURE_DIR|g" "$STUB_DIR/openclaw"
else
  sed -i '' "s|FIXTURE_DIR_PLACEHOLDER|$FIXTURE_DIR|g" "$STUB_DIR/openclaw"
fi

# ── Fake sessions.json ─────────────────────────────────────────────────────────
cat > "$FIXTURE_DIR/agents/main/sessions/sessions.json" << 'SESSIONS_EOF'
{
  "agent:main:telegram:direct:12345": {
    "lastUpdate": 1234567890,
    "messages": []
  }
}
SESSIONS_EOF

# ── Locate the gate script ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_SCRIPT="$SCRIPT_DIR/../scripts/a2-session-load-gate.sh"
if [[ ! -f "$GATE_SCRIPT" ]]; then
  echo "ERROR: a2-session-load-gate.sh not found at $GATE_SCRIPT"
  exit 1
fi

run_gate() {
  PATH="$STUB_DIR:$PATH" \
  OPENCLAW_WORKSPACE="$FIXTURE_DIR/workspace" \
  SESSIONS_JSON_OVERRIDE="$FIXTURE_DIR/agents/main/sessions/sessions.json" \
  A2_WAIT_SECONDS="0" \
  OPERATOR_TELEGRAM_CHAT_ID="5252140759" \
  bash "$GATE_SCRIPT" --box "fixture-test" --workspace "$FIXTURE_DIR/workspace" "$@"
}

# ═══════════════════════════════════════════════════════════════════════════════
echo "=== Case 1: loaded=YES (marker present, edit before reset) ==="
# ═══════════════════════════════════════════════════════════════════════════════

AGENTS_MD="$FIXTURE_DIR/workspace/AGENTS.md"
cat > "$AGENTS_MD" << 'AGENTS_EOF'
# AGENTS.md (fixture)
## Skills
<!-- convertandflow-migration:rules-15-16:1.6.0 -->
AGENTS_EOF

# Set mtime to 2 minutes ago (edit happened before reset)
PAST_TIME=$(date -d '2 minutes ago' '+%Y%m%d%H%M.%S' 2>/dev/null || date -v-2M '+%Y%m%d%H%M.%S')
touch -t "$PAST_TIME" "$AGENTS_MD"

rm -f "$RESET_LOG"
GATE_EXIT=0
OUTPUT=$(run_gate 2>&1) || GATE_EXIT=$?

echo "$OUTPUT"
echo "--- Case 1 exit code: $GATE_EXIT ---"

if [[ "$GATE_EXIT" -eq 0 ]] && echo "$OUTPUT" | grep -q "loaded=YES"; then
  echo "PASS: Case 1 — loaded=YES, exit 0"
  PASS=$((PASS+1))
else
  echo "FAIL: Case 1 — expected loaded=YES and exit 0"
  echo "  Got exit: $GATE_EXIT"
  echo "  Output: $OUTPUT"
  FAIL=$((FAIL+1))
fi

# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "=== Case 2: loaded=NO -> retry -> alert (marker absent) ==="
# ═══════════════════════════════════════════════════════════════════════════════

# AGENTS.md with NO migration marker
cat > "$AGENTS_MD" << 'AGENTS_NO_MARKER_EOF'
# AGENTS.md (fixture — no migration marker)
## Skills
v11.18.0 UPDATE PENDING
AGENTS_NO_MARKER_EOF

# Set mtime to 2 minutes ago (edit before reset — only the marker is missing)
touch -t "$PAST_TIME" "$AGENTS_MD"

rm -f "$RESET_LOG"
CASE2_EXIT=0
OUTPUT2=$(run_gate 2>&1) || CASE2_EXIT=$?

echo "$OUTPUT2"
echo "--- Case 2 exit code: $CASE2_EXIT ---"

RESET_CALL_COUNT=$(wc -l < "$RESET_LOG" 2>/dev/null || echo 0)
RESET_CALL_COUNT=$(echo "$RESET_CALL_COUNT" | tr -d ' ')

echo "Reset calls made: $RESET_CALL_COUNT"

CASE2_PASS=true
if [[ "$CASE2_EXIT" -ne 1 ]]; then
  echo "FAIL: Case 2 — expected exit 1, got $CASE2_EXIT"
  CASE2_PASS=false
fi
if ! echo "$OUTPUT2" | grep -q "loaded=NO"; then
  echo "FAIL: Case 2 — expected 'loaded=NO' in output"
  CASE2_PASS=false
fi
if ! echo "$OUTPUT2" | grep -qiE "ALERT|operator"; then
  echo "FAIL: Case 2 — expected ALERT/operator in output"
  CASE2_PASS=false
fi
if [[ "$RESET_CALL_COUNT" -lt 2 ]]; then
  echo "FAIL: Case 2 — expected 2 reset calls, got $RESET_CALL_COUNT"
  CASE2_PASS=false
fi

if [[ "$CASE2_PASS" == "true" ]]; then
  echo "PASS: Case 2 — loaded=NO, exit 1, 2 reset calls, alert sent"
  PASS=$((PASS+1))
else
  FAIL=$((FAIL+1))
fi

# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "=== Fixture Results ==="
echo "PASSED: $PASS"
echo "FAILED: $FAIL"
# ═══════════════════════════════════════════════════════════════════════════════

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
