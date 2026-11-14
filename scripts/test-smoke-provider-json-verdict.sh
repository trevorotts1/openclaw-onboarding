#!/usr/bin/env bash
# test-smoke-provider-json-verdict.sh -- BU-61 acceptance fixture (WF-081 / WF-089).
#
# The provider health check must READ its verdict, not pattern-match text:
#   * S3: {"reply":"pong",...} passes; {"error":{...}} fails; plain text fails.
#   * S4: the exit code plus JSON without a top-level error decides.
# And the closeout must not ping a finished box: with closeoutStatus=done and a
# passing --closeout, the closeout exits before the provider smoke, so the
# `openclaw agent` stub is never called.
#
# Nothing leaves this machine: every openclaw/curl/verifier call is a stub in a
# temp dir, and the state files are fixture copies.
#
# EXIT: 0 all PASS, 1 any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$SCRIPT_DIR"
SRC23="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
SRC37="$REPO_ROOT/37-zhc-closeout/scripts"
SRCSU="$REPO_ROOT/shared-utils"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu61-smoke.XXXXXX")"
trap 'if [[ -z "${KEEP_WORK:-}" ]]; then rm -rf "$WORK"; fi' EXIT
echo "    fixture work dir: $WORK"

# Real jq must be reachable inside env -i runs (state writes and state reads).
JQ_DIR=""
if command -v jq >/dev/null 2>&1; then JQ_DIR="$(cd "$(dirname "$(command -v jq)")" && pwd)"; fi
BASE_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
[ -n "$JQ_DIR" ] && BASE_PATH="$JQ_DIR:$BASE_PATH"

# ─── Part 1: S3 / S4 verdicts come from the parsed JSON ────────────────────
SMOKE_BOX="$WORK/smoke-box"
mkdir -p "$SMOKE_BOX/.openclaw/workspace" "$SMOKE_BOX/bin"
CFG="$SMOKE_BOX/.openclaw/openclaw.json"
SSTATE="$SMOKE_BOX/.openclaw/workspace/.workforce-build-state.json"
CALLS="$SMOKE_BOX/openclaw-calls.log"
printf '%s\n' '{"agents":{"defaults":{"memorySearch":{"enabled":true,"provider":"openai","fallback":"openai"}}}}' > "$CFG"
printf '%s\n' '{"closeoutStatus":"pending"}' > "$SSTATE"
: > "$CALLS"

cat > "$SMOKE_BOX/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${OPENCLAW_CALLS:-/dev/null}"
case "${1:-}" in
  --version) printf 'openclaw 2026.6.8\n'; exit 0 ;;
  agent)     printf '%s\n' "${STUB_AGENT_OUT:-}"; exit "${STUB_AGENT_RC:-0}" ;;
  memory)    printf '%s\n' "${STUB_MEM_OUT:-}"; exit "${STUB_MEM_RC:-0}" ;;
  message)   printf '%s\n' "${STUB_AGENT_OUT:-}"; exit 0 ;;
esac
exit 0
STUB
chmod +x "$SMOKE_BOX/bin/openclaw"

# run_smoke AGENT_OUT MEM_OUT -> sets SMOKE_RC
run_smoke() {
  env -i \
    PATH="$SMOKE_BOX/bin:$BASE_PATH" \
    HOME="$SMOKE_BOX" \
    TMPDIR="${TMPDIR:-/tmp}" \
    SMOKE_OC_CONFIG="$CFG" \
    SMOKE_STATE_FILE="$SSTATE" \
    SMOKE_OC_VERSION_OVERRIDE=2026.6.8 \
    SMOKE_INTERNAL_CHANNEL_SUPPORTED=0 \
    OPENCLAW_CALLS="$CALLS" \
    STUB_AGENT_OUT="$1" \
    STUB_MEM_OUT="$2" \
    bash "$SRC/smoke-test-provider-capabilities.sh" --quiet > "$WORK/smoke.out" 2>&1
  SMOKE_RC=$?
}

run_smoke '{"reply":"pong","usage":{"total_tokens":431}}' '{"results":[]}'
if [[ "$SMOKE_RC" -eq 0 ]]; then
  pass "S3+S4 pass on a real reply object and a clean memory JSON (rc=0)"
else
  fail "S3+S4 rc=$SMOKE_RC on a real reply object (expected 0)"
  tail -8 "$WORK/smoke.out" | sed 's/^/    /'
fi

run_smoke '{"error":{"message":"upstream 503"}}' '{"results":[]}'
if [[ "$SMOKE_RC" -eq 1 ]]; then
  pass "S3 fails on a top-level error object (rc=1)"
else
  fail "S3 rc=$SMOKE_RC on a top-level error object (expected 1)"
  tail -8 "$WORK/smoke.out" | sed 's/^/    /'
fi

if command -v jq >/dev/null 2>&1; then
  blocked_status="$(jq -r '.closeoutStatus // "absent"' "$SSTATE" 2>/dev/null)"
  if [[ "$blocked_status" == "blocked-provider-mismatch" ]]; then
    pass "the failure wrote closeoutStatus=blocked-provider-mismatch through workforce_state_set"
  else
    fail "closeoutStatus=$blocked_status after a provider failure (expected blocked-provider-mismatch)"
  fi
else
  echo "    SKIP: jq is not installed here; the state-write assertion cannot run"
fi

run_smoke 'pong' '{"results":[]}'
if [[ "$SMOKE_RC" -eq 1 ]]; then
  pass "S3 fails on plain text, not JSON (rc=1)"
else
  fail "S3 rc=$SMOKE_RC on plain text (expected 1)"
  tail -8 "$WORK/smoke.out" | sed 's/^/    /'
fi

run_smoke '{"reply":"pong"}' 'memory search exploded'
if [[ "$SMOKE_RC" -eq 1 ]]; then
  pass "S4 fails when the memory probe output is not JSON (rc=1)"
else
  fail "S4 rc=$SMOKE_RC on non-JSON memory output (expected 1)"
  tail -8 "$WORK/smoke.out" | sed 's/^/    /'
fi

run_smoke '{"reply":"pong"}' '{"error":{"message":"embedding failed"}}'
if [[ "$SMOKE_RC" -eq 1 ]]; then
  pass "S4 fails on a memory JSON carrying a top-level error (rc=1)"
else
  fail "S4 rc=$SMOKE_RC on a memory JSON with error (expected 1)"
  tail -8 "$WORK/smoke.out" | sed 's/^/    /'
fi

# ─── Part 2: a finished box never pings the provider ───────────────────────
BOX="$WORK/closeout-box"
OC="$BOX/.openclaw"
SK="$OC/skills"
mkdir -p "$SK/37-zhc-closeout/scripts" "$SK/23-ai-workforce-blueprint/scripts" \
         "$SK/shared-utils" "$OC/workspace" "$BOX/bin"

cp "$SRC37/run-closeout.sh" "$SRC37/lib-closeout-state.sh" "$SRC37/cleanup-closeout.py" \
   "$SK/37-zhc-closeout/scripts/" || { echo "fixture: copy 37 failed" >&2; exit 1; }
cp "$SRC23/lib-workforce-state.sh" "$SRC23/workforce_state.py" "$SRC23/workforce_completion.py" \
   "$SRC23/interview_eligibility.py" "$SK/23-ai-workforce-blueprint/scripts/" \
   || { echo "fixture: copy 23 failed" >&2; exit 1; }
cp "$SRCSU/resolve-oc-root.sh" "$SRCSU/operator-chat-id.sh" \
   "$SK/shared-utils/" || { echo "fixture: copy shared-utils failed" >&2; exit 1; }

# Preflights exist and pass (the done-box must exit before any of them anyway).
printf '#!/usr/bin/env bash\nexit 0\n' > "$SK/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$SK/23-ai-workforce-blueprint/scripts/verify-wiring.sh"
chmod +x "$SK/23-ai-workforce-blueprint/scripts/verify-zhc-standard.sh" \
         "$SK/23-ai-workforce-blueprint/scripts/verify-wiring.sh"

# The provider smoke itself: any invocation records a marker file.
mkdir -p "$SK/scripts"
cat > "$SK/scripts/smoke-test-provider-capabilities.sh" <<'STUB'
#!/usr/bin/env bash
printf 'provider-smoke\n' >> "$SMOKE_MARKER"
exit 0
STUB
chmod +x "$SK/scripts/smoke-test-provider-capabilities.sh"

CALLS2="$WORK/closeout-openclaw-calls.log"
SMOKE_MARKER="$WORK/provider-smoke-ran.log"
: > "$CALLS2"
: > "$SMOKE_MARKER"

cat > "$BOX/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${OPENCLAW_CALLS:-/dev/null}"
exit 0
STUB
cat > "$BOX/bin/curl" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$BOX/bin/openclaw" "$BOX/bin/curl"

# --has-identity and --closeout pass; everything else is the real python.
cat > "$BOX/bin/workforce-python" <<'WRAP'
#!/usr/bin/env bash
_wc=0; _flag=0
for a in "$@"; do
  case "$a" in
    *workforce_completion.py) _wc=1 ;;
    --has-identity|--closeout) _flag=1 ;;
  esac
done
if [ "$_wc" = "1" ] && [ "$_flag" = "1" ]; then exit 0; fi
exec python3 "$@"
WRAP
chmod +x "$BOX/bin/workforce-python"

CSTATE="$OC/workspace/.workforce-build-state.json"
printf '%s\n' '{
  "companyName": "Fixture Workforce",
  "companySlug": "fixture",
  "buildId": "22222222-2222-2222-2222-222222222222",
  "buildCompletedAt": "2026-06-01T00:00:00Z",
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "closeoutStatus": "done"
}' > "$CSTATE"

rc=0
# KIE_API_KEY / NOTION_API_TOKEN are the pipeline's own credential-presence
# preflight (unchanged by this unit); a fixture passes placeholders past it so
# the assertion can reach the done-block it is about. Nothing reads the values.
env -i \
  PATH="$BOX/bin:$BASE_PATH" \
  HOME="$BOX" \
  TMPDIR="${TMPDIR:-/tmp}" \
  WORKFORCE_PYTHON="$BOX/bin/workforce-python" \
  OPENCLAW_CALLS="$CALLS2" \
  SMOKE_MARKER="$SMOKE_MARKER" \
  KIE_API_KEY="fixture-kie-key" \
  NOTION_API_TOKEN="fixture-notion-token" \
  ZHC_SKIP_TG_PREFLIGHT=1 \
  ZHC_SKIP_ROUTING_PREFLIGHT=1 \
  bash "$SK/37-zhc-closeout/scripts/run-closeout.sh" > "$WORK/run.out" 2>&1 || rc=$?
echo "    run-closeout rc=$rc (log: $WORK/run.out)"

if [[ "$rc" -eq 0 ]]; then
  pass "run-closeout.sh exits 0 for a box whose closeoutStatus is done"
else
  fail "run-closeout.sh exits $rc for a done box (expected 0)"
  tail -15 "$WORK/run.out" | sed 's/^/    /'
fi

agent_calls="$(while IFS= read -r line; do case "$line" in agent*) echo x ;; esac; done < "$CALLS2" | wc -l | tr -d ' ')"
if [[ "$agent_calls" == "0" ]]; then
  pass "openclaw agent was never called (no provider ping on a finished box)"
else
  fail "openclaw agent was called $agent_calls time(s) on a finished box (expected 0)"
fi

if [[ ! -s "$SMOKE_MARKER" ]]; then
  pass "the provider smoke never ran for a finished box"
else
  fail "the provider smoke ran for a finished box ($(wc -l < "$SMOKE_MARKER" | tr -d ' ') invocation(s))"
fi

printf '\nTotal: %d passed, %d failed\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then exit 0; else exit 1; fi
