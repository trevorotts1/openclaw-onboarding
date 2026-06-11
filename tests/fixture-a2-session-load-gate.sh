#!/usr/bin/env bash
# Fixture test for scripts/a2-session-load-gate.sh (A.2 v2)
#
# REWRITE of the broken Case 1/2 fixture from #160.
# The stub is STATE-AWARE: it tracks sessionId changes across resets so LEG A
# sees a real re-initialization signal.  The stub also enqueues a canary-echo
# message into chat.history so LEG B can match it.
#
# Four cases:
#   Case 1 HIGH    — LEG A pass (new sessionId) + LEG B pass (canary echoed)
#                    -> loaded_confidence=HIGH, exit 0, NO operator alert,
#                       canary stripped from fixture core file.
#   Case 2 LOW     — stub keeps SAME sessionId after reset (LEG A fail)
#                    -> loaded_confidence=LOW, exit 1, ALERT in output.
#   Case 3 UNKNOWN — stub reports no-model signal; LEG B cannot run
#                    -> loaded_confidence=UNKNOWN, exit 0, NO alert.
#   Case 4 MEDIUM  — LEG A passes; chat.history returns 'unknown method'
#                    -> loaded_confidence=MEDIUM, exit 0, no false alert.
#
# The gate does NOT block on a fixed sleep; it uses a bounded poll with
# A2_POLL_INTERVAL=0 and A2_PROBE_TIMEOUT=10 in the fixture.
#
# Usage: bash tests/fixture-a2-session-load-gate.sh
# Exit 0 = all cases passed.  Exit 1 = at least one failed.

set -euo pipefail

FIXTURE_DIR="/tmp/a2-fixture-v2-$$"
PASS=0
FAIL=0

cleanup() {
  rm -rf "$FIXTURE_DIR"
}
trap cleanup EXIT

# ── Fixture layout ─────────────────────────────────────────────────────────────
mkdir -p "$FIXTURE_DIR/workspace"
mkdir -p "$FIXTURE_DIR/agents/main/sessions"
mkdir -p "$FIXTURE_DIR/skills"
mkdir -p "$FIXTURE_DIR/bin"

# ── State files the stub reads/writes ─────────────────────────────────────────
STUB_STATE="$FIXTURE_DIR/stub-state.json"
RESET_LOG="$FIXTURE_DIR/reset-calls.log"
MESSAGE_SEND_LOG="$FIXTURE_DIR/message-send.log"

# ── Stub openclaw binary ───────────────────────────────────────────────────────
# The stub is intentionally kept simple and state-driven via $FIXTURE_DIR.
# It reads $STUB_STATE on every call and updates it on sessions.reset.
cat > "$FIXTURE_DIR/bin/openclaw" << 'STUB_EOF'
#!/usr/bin/env bash
# State-aware openclaw stub for A.2 v2 fixture tests
FIXTURE_DIR="FIXTURE_DIR_PLACEHOLDER"
STUB_STATE="$FIXTURE_DIR/stub-state.json"
RESET_LOG="$FIXTURE_DIR/reset-calls.log"
MESSAGE_SEND_LOG="$FIXTURE_DIR/message-send.log"

# Load stub mode from state file
MODE=$(python3 -c "import json; s=json.load(open('$STUB_STATE')); print(s.get('mode','happy'))" 2>/dev/null || echo "happy")
NO_MODEL=$(python3 -c "import json; s=json.load(open('$STUB_STATE')); print('1' if s.get('no_model') else '0')" 2>/dev/null || echo "0")
NO_CHAT_HISTORY=$(python3 -c "import json; s=json.load(open('$STUB_STATE')); print('1' if s.get('no_chat_history') else '0')" 2>/dev/null || echo "0")

case "$*" in
  *"sessions.reset"*)
    echo "$(date +%s) $*" >> "$RESET_LOG"
    if [[ "$MODE" == "sad" ]]; then
      # LEG A fail: keep SAME sessionId (do not update stub-state)
      echo '{"ok":true}'
    else
      # LEG A pass: mint new sessionId into stub-state
      python3 << 'PYEOF'
import json, time, random
p = "FIXTURE_DIR_PLACEHOLDER/stub-state.json"
s = json.load(open(p))
s['sessionId'] = f"sess-reset-{int(time.time())}-{random.randint(1000,9999)}"
s['sessionStartedAt'] = str(int(time.time()))
open(p,'w').write(json.dumps(s))
PYEOF
      echo '{"ok":true}'
    fi
    ;;
  *"sessions.get"* | *"sessions.describe"*)
    python3 -c "
import json
s = json.load(open('$STUB_STATE'))
print(json.dumps({'sessionId': s.get('sessionId','sess-initial'), 'sessionStartedAt': s.get('sessionStartedAt','0'), 'lastInteractionAt': s.get('sessionStartedAt','0'), 'updatedAt': s.get('sessionStartedAt','0')}))
"
    ;;
  *"chat.history"*)
    if [[ "$NO_MODEL" == "1" ]]; then
      # Return a no-model error so _detect_model() returns False
      echo '{"error":"no model configured"}'
      exit 0
    fi
    if [[ "$NO_CHAT_HISTORY" == "1" ]]; then
      echo '{"error":"unknown method chat.history"}'
      exit 1
    fi
    # Return the canary-echo message if the state file has one
    CANARY=$(python3 -c "import json; s=json.load(open('$STUB_STATE')); print(s.get('pending_canary',''))" 2>/dev/null || echo "")
    if [[ -n "$CANARY" ]]; then
      python3 -c "
import json
canary = '$CANARY'
msgs = [{'id':'msg-probe-1','role':'assistant','content':f'Here is the token: {canary}'},
        {'id':'msg-probe-0','role':'user','content':'load-check: reply with the load-check token'}]
print(json.dumps(msgs))
"
    else
      echo '[]'
    fi
    ;;
  *"message send"*)
    echo "$(date +%s) $*" >> "$MESSAGE_SEND_LOG"
    # In happy mode (model present): enqueue the canary into stub state for chat.history
    if [[ "$MODE" != "sad" ]] && [[ "$NO_MODEL" != "1" ]]; then
      WORKSPACE="FIXTURE_DIR_PLACEHOLDER/workspace"
      CANARY=$(grep -oE 'A2CANARY[A-Za-z0-9]+' "$WORKSPACE/SOUL.md" 2>/dev/null | head -1 || echo "")
      if [[ -n "$CANARY" ]]; then
        python3 -c "
import json
p = 'FIXTURE_DIR_PLACEHOLDER/stub-state.json'
s = json.load(open(p))
s['pending_canary'] = '$CANARY'
open(p,'w').write(json.dumps(s))
"
      fi
    fi
    # message send is one-way: print nothing the gate mistakes for a reply
    exit 0
    ;;
  *)
    echo "STUB: unknown command: $*" >&2
    exit 1
    ;;
esac
STUB_EOF
chmod +x "$FIXTURE_DIR/bin/openclaw"

# Inject FIXTURE_DIR into stub
if sed --version 2>/dev/null | grep -q GNU; then
  sed -i "s|FIXTURE_DIR_PLACEHOLDER|$FIXTURE_DIR|g" "$FIXTURE_DIR/bin/openclaw"
else
  sed -i '' "s|FIXTURE_DIR_PLACEHOLDER|$FIXTURE_DIR|g" "$FIXTURE_DIR/bin/openclaw"
fi

# ── Base sessions.json ─────────────────────────────────────────────────────────
write_sessions_json() {
  cat > "$FIXTURE_DIR/agents/main/sessions/sessions.json" << 'SESS_EOF'
{
  "agent:main:telegram:direct:12345": {
    "sessionId": "sess-initial",
    "sessionStartedAt": "1000000",
    "lastInteractionAt": "1000000",
    "updatedAt": "1000000"
  }
}
SESS_EOF
}
write_sessions_json

# ── Locate the gate script ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_SCRIPT="$SCRIPT_DIR/../scripts/a2-session-load-gate.sh"
if [[ ! -f "$GATE_SCRIPT" ]]; then
  echo "ERROR: a2-session-load-gate.sh not found at $GATE_SCRIPT"
  exit 1
fi

# ── Helper: reset stub to a known state ───────────────────────────────────────
reset_stub() {
  local mode="${1:-happy}"
  local no_model="${2:-false}"
  local no_chat_history="${3:-false}"
  python3 -c "
import json
state = {
  'mode': '$mode',
  'no_model': $no_model,
  'no_chat_history': $no_chat_history,
  'sessionId': 'sess-initial',
  'sessionStartedAt': '1000000',
  'pending_canary': '',
}
open('$STUB_STATE', 'w').write(json.dumps(state))
"
  write_sessions_json
  rm -f "$RESET_LOG" "$MESSAGE_SEND_LOG"
  # Clear SOUL.md
  > "$FIXTURE_DIR/workspace/SOUL.md"
}

# ── run_gate helper ────────────────────────────────────────────────────────────
run_gate() {
  PATH="$FIXTURE_DIR/bin:$PATH" \
  FLEET_REFRESH_ROOT="$FIXTURE_DIR" \
  SESSIONS_JSON_OVERRIDE="$FIXTURE_DIR/agents/main/sessions/sessions.json" \
  A2_PROBE_TIMEOUT="10" \
  A2_POLL_INTERVAL="0" \
  OPERATOR_TELEGRAM_CHAT_ID="5252140759" \
  OC_JSON="$FIXTURE_DIR/openclaw.json" \
  bash "$GATE_SCRIPT" \
    --box "fixture-test" \
    --workspace "$FIXTURE_DIR/workspace" \
    --ceo-chat-id "12345" \
    --probe-timeout "10" \
    --poll-interval "0" \
    "$@"
}

# Write a fixture openclaw.json so resolve_injected_core_files targets our workspace
python3 -c "
import json
open('$FIXTURE_DIR/openclaw.json','w').write(json.dumps({'agents':{'defaults':{'workspace':'$FIXTURE_DIR/workspace'},'list':[]}}))
"

# =============================================================================
echo ""
echo "=== Case 1: HIGH — LEG A + LEG B both pass (canary echoed) ==="
# =============================================================================
reset_stub "happy" "false" "false"

CASE1_EXIT=0
CASE1_OUTPUT=$(run_gate 2>&1) || CASE1_EXIT=$?

echo "$CASE1_OUTPUT"
echo "--- Case 1 exit: $CASE1_EXIT ---"

CASE1_CONFIDENCE=$(echo "$CASE1_OUTPUT" | grep 'loaded_confidence=' | tail -1 | cut -d= -f2 || echo "")
RESET_COUNT=$(wc -l < "$RESET_LOG" 2>/dev/null | tr -d ' ' || echo "0")
MSG_COUNT=$(wc -l < "$MESSAGE_SEND_LOG" 2>/dev/null | tr -d ' ' || echo "0")
CANARY_REMAINING=$(grep -c 'a2-canary-probe' "$FIXTURE_DIR/workspace/SOUL.md" 2>/dev/null || echo "0")

echo "Case 1: confidence=$CASE1_CONFIDENCE  exit=$CASE1_EXIT  resets=$RESET_COUNT  messages=$MSG_COUNT  canary_remaining=$CANARY_REMAINING"

CASE1_PASS=true
[[ "$CASE1_EXIT" -ne 0 ]] && { echo "FAIL Case 1: expected exit 0, got $CASE1_EXIT"; CASE1_PASS=false; }
[[ "$CASE1_CONFIDENCE" != "HIGH" ]] && { echo "FAIL Case 1: expected HIGH, got '$CASE1_CONFIDENCE'"; CASE1_PASS=false; }
[[ "$CANARY_REMAINING" -ne 0 ]] && { echo "FAIL Case 1: canary not stripped from SOUL.md"; CASE1_PASS=false; }

if [[ "$CASE1_PASS" == "true" ]]; then
  echo "PASS: Case 1 — HIGH, exit 0, no alert, canary stripped"
  PASS=$((PASS+1))
else
  FAIL=$((FAIL+1))
fi

# =============================================================================
echo ""
echo "=== Case 2: LOW — LEG A fails (same sessionId after reset) ==="
# =============================================================================
reset_stub "sad" "false" "false"

CASE2_EXIT=0
CASE2_OUTPUT=$(run_gate 2>&1) || CASE2_EXIT=$?

echo "$CASE2_OUTPUT"
echo "--- Case 2 exit: $CASE2_EXIT ---"

CASE2_CONFIDENCE=$(echo "$CASE2_OUTPUT" | grep 'loaded_confidence=' | tail -1 | cut -d= -f2 || echo "")
CASE2_ALERT_COUNT=$(wc -l < "$MESSAGE_SEND_LOG" 2>/dev/null | tr -d ' ' || echo "0")

echo "Case 2: confidence=$CASE2_CONFIDENCE  exit=$CASE2_EXIT  alerts=$CASE2_ALERT_COUNT"

CASE2_PASS=true
[[ "$CASE2_EXIT" -ne 1 ]] && { echo "FAIL Case 2: expected exit 1, got $CASE2_EXIT"; CASE2_PASS=false; }
[[ "$CASE2_CONFIDENCE" != "LOW" ]] && { echo "FAIL Case 2: expected LOW, got '$CASE2_CONFIDENCE'"; CASE2_PASS=false; }
[[ "$CASE2_ALERT_COUNT" -lt 1 ]] && { echo "FAIL Case 2: expected operator alert on LOW"; CASE2_PASS=false; }

if [[ "$CASE2_PASS" == "true" ]]; then
  echo "PASS: Case 2 — LOW, exit 1, alert sent"
  PASS=$((PASS+1))
else
  FAIL=$((FAIL+1))
fi

# =============================================================================
echo ""
echo "=== Case 3: UNKNOWN — no live model, no operator alert ==="
# =============================================================================
reset_stub "happy" "true" "false"

CASE3_EXIT=0
CASE3_OUTPUT=$(run_gate 2>&1) || CASE3_EXIT=$?

echo "$CASE3_OUTPUT"
echo "--- Case 3 exit: $CASE3_EXIT ---"

CASE3_CONFIDENCE=$(echo "$CASE3_OUTPUT" | grep 'loaded_confidence=' | tail -1 | cut -d= -f2 || echo "")
CASE3_ALERT_COUNT=$(wc -l < "$MESSAGE_SEND_LOG" 2>/dev/null | tr -d ' ' || echo "0")

echo "Case 3: confidence=$CASE3_CONFIDENCE  exit=$CASE3_EXIT  alerts=$CASE3_ALERT_COUNT"

CASE3_PASS=true
[[ "$CASE3_EXIT" -ne 0 ]] && { echo "FAIL Case 3: expected exit 0 (UNKNOWN is not a fail), got $CASE3_EXIT"; CASE3_PASS=false; }
[[ "$CASE3_CONFIDENCE" != "UNKNOWN" ]] && { echo "FAIL Case 3: expected UNKNOWN, got '$CASE3_CONFIDENCE'"; CASE3_PASS=false; }
[[ "$CASE3_ALERT_COUNT" -gt 0 ]] && { echo "FAIL Case 3: operator alert must NOT fire on UNKNOWN"; CASE3_PASS=false; }

if [[ "$CASE3_PASS" == "true" ]]; then
  echo "PASS: Case 3 — UNKNOWN, exit 0, no alert"
  PASS=$((PASS+1))
else
  FAIL=$((FAIL+1))
fi

# =============================================================================
echo ""
echo "=== Case 4: MEDIUM — LEG A passes, chat.history unavailable (non-model) ==="
# =============================================================================
reset_stub "happy" "false" "true"

CASE4_EXIT=0
CASE4_OUTPUT=$(run_gate 2>&1) || CASE4_EXIT=$?

echo "$CASE4_OUTPUT"
echo "--- Case 4 exit: $CASE4_EXIT ---"

CASE4_CONFIDENCE=$(echo "$CASE4_OUTPUT" | grep 'loaded_confidence=' | tail -1 | cut -d= -f2 || echo "")

echo "Case 4: confidence=$CASE4_CONFIDENCE  exit=$CASE4_EXIT"

CASE4_PASS=true
[[ "$CASE4_EXIT" -ne 0 ]] && { echo "FAIL Case 4: expected exit 0 (MEDIUM is degraded, not fail), got $CASE4_EXIT"; CASE4_PASS=false; }
[[ "$CASE4_CONFIDENCE" != "MEDIUM" ]] && { echo "FAIL Case 4: expected MEDIUM, got '$CASE4_CONFIDENCE'"; CASE4_PASS=false; }

if [[ "$CASE4_PASS" == "true" ]]; then
  echo "PASS: Case 4 — MEDIUM, exit 0, no false alert"
  PASS=$((PASS+1))
else
  FAIL=$((FAIL+1))
fi

# =============================================================================
echo ""
echo "=== Fixture Results ==="
echo "PASSED: $PASS"
echo "FAILED: $FAIL"
# =============================================================================

[[ "$FAIL" -gt 0 ]] && exit 1
exit 0
