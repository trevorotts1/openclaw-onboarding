#!/usr/bin/env bash
# test-smoke-provider-internal-channel.sh -- proves the S3 live-turn probe in
# smoke-test-provider-capabilities.sh is VERSION-AWARE about the 'internal'
# channel that OpenClaw removed in 2026.6.x.
#
# THE BUG IT GUARDS: on OpenClaw 2026.6.8 the old probe `openclaw message send
# --channel internal` returns `Error: Unknown channel: internal`, so S3 failed
# the whole provider-smoke gate on a version artifact (had to be bypassed with
# ZHC_SKIP_LIVE_PROBE=1 during a recent closeout). The fix probes via
# `openclaw agent` on 2026.6.x instead, keeping a genuine live-turn check.
#
# CASES (all driven with a MOCK openclaw on PATH so no real gateway is touched):
#   T1: OpenClaw 2026.6.8 + mock that REJECTS 'internal' but answers 'agent'
#        -> S3 probes via `openclaw agent` and PASSES (no Unknown-channel fail).
#   T2: OpenClaw 2026.5.30 (internal still supported) + mock that answers
#        'message send --channel internal' -> S3 probes via the legacy channel,
#        PASSES, and does NOT invoke `openclaw agent`.
#   T3: OpenClaw 2026.6.8 + mock whose `agent` turn returns a genuine provider
#        error (402/model error) -> S3 still FAILS LOUD (fail on real failure).
#   T4: capability fallback -- version unknown, mock `message send --help` does
#        NOT list 'internal' -> S3 picks the `agent` transport (capability probe).
#
# EXIT: 0 = all cases pass, 1 = script-under-test missing, 3 = a case failed.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE="$SCRIPT_DIR/smoke-test-provider-capabilities.sh"

if [[ ! -f "$SMOKE" ]]; then
  echo "FAIL: smoke-test-provider-capabilities.sh not found at $SMOKE" >&2
  exit 1
fi
command -v jq >/dev/null 2>&1 || { echo "FAIL: jq not installed" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 not installed" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAILED=0

# Minimal valid openclaw.json: memory disabled (so S4 is skipped) and a sane
# text-only embed provider with a real fallback (so S1/S2 pass cleanly). This
# isolates the test to S3's transport selection.
cat > "$TMP/openclaw.json" <<'JSON'
{
  "agents": {
    "defaults": {
      "memorySearch": {
        "enabled": false,
        "provider": "openai",
        "fallback": "openrouter"
      }
    },
    "list": []
  }
}
JSON

# build_mock <version> <internal_behavior> <agent_behavior>
#   internal_behavior: "reject"  -> `message send --channel internal` prints
#                                   "Error: Unknown channel: internal"
#                      "ok"      -> prints a valid {"reply": "..."} JSON
#   agent_behavior:    "ok"      -> `agent` prints {"text":"pong"} (real reply)
#                      "fail"    -> `agent` prints a provider error (402/model)
#                      "absent"  -> `agent` is unknown (mock errors)
# Also records which transport was invoked into $TMP/calls.log so we can assert.
build_mock() {
  local version="$1" internal="$2" agent="$3"
  cat > "$TMP/bin/openclaw" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$TMP/calls.log"
case "\$1" in
  --version)
    echo "OpenClaw $version (deadbee)"; exit 0 ;;
esac
# Re-scan args for the subcommand + channel.
sub="\$1"
case "\$sub" in
  message)
    # 'message send --help' enumerates supported channels.
    for a in "\$@"; do [ "\$a" = "--help" ] && {
      echo "  --channel <channel>  Channel:";
      if [ "$internal" = "ok" ]; then echo "    telegram|internal|whatsapp"; else echo "    telegram|whatsapp|qa-channel"; fi
      exit 0; }
    done
    # 'message send --channel internal ...'
    if printf '%s ' "\$@" | grep -q -- '--channel internal'; then
      if [ "$internal" = "ok" ]; then
        echo '{"reply":"pong"}'; exit 0
      else
        echo "Error: Unknown channel: internal" >&2; echo "Error: Unknown channel: internal"; exit 0
      fi
    fi
    echo '{"reply":"pong"}'; exit 0 ;;
  agent)
    case "$agent" in
      ok)   echo '{"text":"pong","handledBy":"core"}'; exit 0 ;;
      fail) echo '{"error":"402 model error: insufficient_quota"}'; exit 0 ;;
      absent) echo "error: unknown command 'agent'" >&2; exit 1 ;;
    esac ;;
  memory) echo '{"results":[]}'; exit 0 ;;
esac
exit 0
EOF
  chmod +x "$TMP/bin/openclaw"
}

# run_s3 <name> <expect_rc> <expect_transport regex|-> <pin_version|-> <force_supported|->
run_s3() {
  local name="$1" expect_rc="$2" expect_transport="$3" pin_version="$4" force_supported="$5"
  : > "$TMP/calls.log"
  local rc out
  out=$(
    PATH="$TMP/bin:$PATH" \
    SMOKE_OC_CONFIG="$TMP/openclaw.json" \
    SMOKE_OC_VERSION_OVERRIDE="${pin_version}" \
    SMOKE_INTERNAL_CHANNEL_SUPPORTED="${force_supported}" \
      bash "$SMOKE" 2>&1
  )
  rc=$?
  local ok=1
  [[ "$rc" == "$expect_rc" ]] || { echo "  ✗ $name -- expected rc=$expect_rc got rc=$rc" >&2; ok=0; }
  if [[ "$expect_transport" != "-" ]]; then
    if ! grep -qE "$expect_transport" "$TMP/calls.log"; then
      echo "  ✗ $name -- expected a call matching /$expect_transport/ in:" >&2
      sed 's/^/      /' "$TMP/calls.log" >&2
      ok=0
    fi
  fi
  if [[ "$ok" == "1" ]]; then
    echo "  ✓ $name (rc=$rc, transport ok)"
    PASS=$((PASS + 1))
  else
    echo "      --- smoke output ---" >&2
    printf '%s\n' "$out" | sed 's/^/      /' >&2
    FAILED=$((FAILED + 1))
  fi
}

mkdir -p "$TMP/bin"
echo "[SMOKE TEST] smoke-test-provider-capabilities.sh S3 version-aware internal-channel probe"

# T1: 2026.6.8, internal rejected, agent answers -> probe via `agent`, PASS.
build_mock "2026.6.8" "reject" "ok"
run_s3 "T1: 2026.6.8 internal removed -> probes via 'openclaw agent', PASS" 0 '^agent ' "2026.6.8" ""

# T2: 2026.5.30, internal supported -> probe via legacy channel, PASS, no agent.
build_mock "2026.5.30" "ok" "ok"
run_s3 "T2: 2026.5.30 internal supported -> probes via legacy 'message send --channel internal', PASS" 0 'message send.*--channel internal' "2026.5.30" ""
if grep -qE '^agent ' "$TMP/calls.log"; then
  echo "  ✗ T2b: legacy path should NOT invoke 'openclaw agent'" >&2
  FAILED=$((FAILED + 1))
else
  echo "  ✓ T2b: legacy path did not invoke 'openclaw agent'"
  PASS=$((PASS + 1))
fi

# T3: 2026.6.8, agent turn returns a genuine provider error -> S3 FAILS LOUD.
build_mock "2026.6.8" "reject" "fail"
run_s3 "T3: 2026.6.8 agent turn returns 402/model error -> S3 FAILS LOUD (rc 1)" 1 '^agent ' "2026.6.8" ""

# T4: version unknown -> capability probe via `message send --help`; 'internal'
# absent there -> picks the agent transport and PASSES.
build_mock "2026.6.8" "reject" "ok"
run_s3 "T4: version unknown -> capability probe selects 'agent' transport, PASS" 0 '^agent ' "" ""

echo "--------------------------------------------"
if [[ "$FAILED" -eq 0 ]]; then
  echo "[SMOKE TEST] RESULT: ✅ all $PASS cases passed"
  exit 0
fi
echo "[SMOKE TEST] RESULT: ❌ $FAILED case(s) failed ($PASS passed)" >&2
exit 3
