#!/usr/bin/env bash
# test-image-generators-kie74.sh
#
# generate-infographics.sh (workflow) and generate-visual-intelligence.sh run every KIE call through
# Skill 74 (the sibling 74-kie-live-adapter CLI) and keep their own policy: sunburst first,
# nano-banana-2 only as the fallback, the early switch when the primary is rejected, and a clear
# failure when Skill 74 is not installed (no second client).
#
# A local mock HTTP server stands in for KIE (Skill 74's localhost-only KIE_LIVE_API_BASE hook).
# No network, no real key, no credits.
#
# EXIT CODES: 0 = all PASS, 1 = any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$SKILL_DIR/.." && pwd)"
INFO="$SCRIPT_DIR/generate-infographics.sh"
VISI="$SCRIPT_DIR/generate-visual-intelligence.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }

[[ -f "$REPO_DIR/74-kie-live-adapter/scripts/kie_live_adapter.py" ]] || { echo "SKIP: Skill 74 is not a sibling of this checkout"; exit 0; }

WORK="$(mktemp -d)"
trap 'kill "${MOCK_PID:-}" 2>/dev/null; rm -rf "$WORK"' EXIT
export KIE_LIVE_MIN_SPACING=0 KIE_LIVE_POLL_INITIAL=0.1
MODELS_LOG="$WORK/models.log"; : > "$MODELS_LOG"

cat > "$WORK/mock.py" <<'PY'
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
WORK = os.environ["WORK"]
REJECT = os.environ.get("REJECT_MODEL", "")
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = json.loads(self.rfile.read(n).decode() or "{}")
        if self.path.split("?")[0] == "/api/v1/jobs/createTask":
            with open(os.path.join(WORK, "models.log"), "a") as f: f.write(body.get("model", "") + "\n")
            return self._send(200, {"code": 200, "data": {"taskId": "task-1"}})
        return self._send(404, {"code": 404, "msg": "no route"})
    def do_GET(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/v1/models/") and p.endswith("/schema"):
            model = p.split("/api/v1/models/")[1][:-7]
            if REJECT and model == REJECT:
                return self._send(200, {"code": 422, "msg": "model name not supported"})
            return self._send(200, {"code": 200, "data": {"model": model, "openapi": {"paths": {
                "/api/v1/jobs/createTask": {"post": {"requestBody": {"content": {"application/json": {"schema": {
                    "type": "object", "properties": {"model": {"type": "string"}, "input": {"type": "object"}}}}}}}}}}}})
        if p == "/api/v1/jobs/recordInfo":
            return self._send(200, {"code": 200, "data": {"state": "success", "resultJson": json.dumps(
                {"resultUrls": ["https://tempfile.example/img.png"]})}})
        return self._send(404, {"code": 404, "msg": "no route"})
HTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
PY

start_mock() {
  local reject="$1"
  kill "${MOCK_PID:-}" 2>/dev/null
  PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
  WORK="$WORK" PORT="$PORT" REJECT_MODEL="$reject" python3 "$WORK/mock.py" &
  MOCK_PID=$!
  for _ in $(seq 1 40); do curl -s "http://127.0.0.1:$PORT/x" >/dev/null 2>&1 && break; sleep 0.1; done
  BASE="http://127.0.0.1:$PORT"
}

new_box() {  # fresh HOME with a state file; prints nothing
  rm -rf "$WORK/home"; mkdir -p "$WORK/home/.openclaw/workspace"
  STATE="$WORK/home/.openclaw/workspace/.workforce-build-state.json"
  jq -n '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",departments:[{slug:"ops",name:"Operations",rolesDone:3}]}' > "$STATE"
  : > "$MODELS_LOG"
}

run() {  # run <script> [args]
  local script="$1"; shift
  HOME="$WORK/home" ZHC_STATE_FILE="$STATE" KIE_API_KEY="zhc-test-key-0123456789" KIE_LIVE_API_BASE="$BASE" \
    ZHC_VISUAL_INTEL_CAP=3 bash "$script" "$@" >"$WORK/run.out" 2>&1
  echo $?
}

echo "=== TEST 1: workflow infographic goes through Skill 74, sunburst first ==="
start_mock ""; new_box
rc=$(run "$INFO" workflow)
[[ "$rc" == "0" ]] && pass "T1: exit 0" || { fail "T1: exit $rc"; tail -5 "$WORK/run.out"; }
[[ "$(head -1 "$MODELS_LOG")" == "gpt-image-2-5-sunburst-text-to-image" ]] && pass "T1: first model is sunburst" || fail "T1: first model was $(head -1 "$MODELS_LOG")"
[[ "$(jq -r '.infographic2Url // empty' "$STATE")" == "https://tempfile.example/img.png" ]] && pass "T1: result URL written to state" || fail "T1: state url missing"

echo "=== TEST 2: primary rejected as unsupported -> early switch to nano-banana-2 ==="
start_mock "gpt-image-2-5-sunburst-text-to-image"; new_box
rc=$(run "$INFO" workflow)
[[ "$rc" == "0" ]] && pass "T2: exit 0 on the fallback" || { fail "T2: exit $rc"; tail -5 "$WORK/run.out"; }
[[ "$(head -1 "$MODELS_LOG")" == "nano-banana-2" ]] && pass "T2: only the fallback model was dispatched (rejected primary never spent)" || fail "T2: models: $(tr '\n' ' ' < "$MODELS_LOG")"
if grep -q "switching to fallback" "$WORK/run.out"; then pass "T2: early switch logged"; else fail "T2: no early switch log"; cat "$WORK/run.out"; fi

echo "=== TEST 3: visual intelligence set goes through Skill 74 ==="
start_mock ""; new_box
rc=$(run "$VISI")
[[ "$rc" == "0" ]] && pass "T3: exit 0" || { fail "T3: exit $rc"; tail -5 "$WORK/run.out"; }
[[ "$(jq -r '.visualIntelligenceUrls | length' "$STATE")" -ge 3 ]] && pass "T3: at least 3 image URLs in state" || fail "T3: fewer than 3 URLs"
[[ "$(sort -u "$MODELS_LOG" | tr '\n' ' ')" == "gpt-image-2-5-sunburst-text-to-image " ]] && pass "T3: sunburst only (no fallback needed)" || fail "T3: models: $(sort -u "$MODELS_LOG" | tr '\n' ' ')"

echo "=== TEST 4: Skill 74 not installed -> clear failure, no fallback client, no HTTP ==="
start_mock ""; new_box
rm -rf "$WORK/skills"; mkdir -p "$WORK/skills"
cp -R "$SKILL_DIR" "$WORK/skills/37-zhc-closeout"
rc=$(HOME="$WORK/home" ZHC_STATE_FILE="$STATE" KIE_API_KEY="zhc-test-key-0123456789" KIE_LIVE_API_BASE="$BASE" \
  bash "$WORK/skills/37-zhc-closeout/scripts/generate-infographics.sh" workflow >"$WORK/run.out" 2>&1; echo $?)
[[ "$rc" == "1" ]] && pass "T4: exit 1" || fail "T4: exit $rc"
if grep -q 'Skill 74.*not installed' "$WORK/run.out"; then pass "T4: message names Skill 74 as the missing transport"; else fail "T4: no clear message"; fi
[[ ! -s "$MODELS_LOG" ]] && pass "T4: no KIE request was made" || fail "T4: a request was made"

echo "=== TEST 5: no KIE host, endpoint or auth header left in the three generators or the lib ==="
if ! grep -qE 'api\.kie\.ai|redpandaai|Authorization: Bearer|recordInfo|jobs/createTask' "$INFO" "$VISI" "$SCRIPT_DIR/generate-celebration-video.sh" "$SCRIPT_DIR/lib-kie74.sh"; then
  pass "T5: one KIE path (Skill 74)"
else fail "T5: a second KIE client crept back in"; fi

echo
echo "PASS=$PASS  FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && { echo "ALL TESTS PASSED"; exit 0; } || { echo "SOME TESTS FAILED"; exit 1; }
