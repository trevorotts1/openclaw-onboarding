#!/usr/bin/env bash
# test_generate_cover_kie74.sh - generate_cover.sh runs every KIE call through Skill 74 and keeps its own
# policy: typed exit codes (0 ok, 2 setup, 3 createTask, 4 poll timeout, 5 task failed, 6 download), the
# bounded poll, the image probe and the ffmpeg finalize chain. A local mock stands in for KIE (Skill 74's
# localhost-only KIE_LIVE_API_BASE hook). No network, no real key, no credits.
#
# EXIT: 0 all pass, 1 any fail.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/../.." && pwd)"
REPO_DIR="$(cd "$SKILL_DIR/.." && pwd)"
TARGET="$SKILL_DIR/scripts/generate_cover.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1"; }

for t in ffmpeg ffprobe jq python3 file; do
  command -v "$t" >/dev/null 2>&1 || { echo "SKIP: $t not installed"; exit 0; }
done
[[ -f "$REPO_DIR/74-kie-live-adapter/scripts/kie_live_adapter.py" ]] || { echo "SKIP: Skill 74 is not a sibling of this checkout"; exit 0; }

WORK="$(mktemp -d)"
trap 'kill "${MOCK_PID:-}" 2>/dev/null; rm -rf "$WORK"' EXIT
ffmpeg -v error -f lavfi -i "color=c=red:s=1600x1600" -frames:v 1 -y "$WORK/cover.png" || { echo "SKIP: ffmpeg cannot make a test image"; exit 0; }
echo success > "$WORK/mode"
export KIE_LIVE_MIN_SPACING=0
export KIE_API_KEY="cover-test-key-0123456789"

cat > "$WORK/mock.py" <<'PY'
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
W = os.environ["WORK"]
def mode():
    return open(os.path.join(W, "mode")).read().strip()
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
            with open(os.path.join(W, "creates.log"), "a") as f: f.write(json.dumps(body) + "\n")
            if mode() == "auth":
                return self._send(200, {"code": 401, "msg": "bad key"})
            return self._send(200, {"code": 200, "data": {"taskId": "cover-1"}})
        return self._send(404, {"code": 404})
    def do_GET(self):
        p = self.path.split("?")[0]
        if p.startswith("/api/v1/models/") and p.endswith("/schema"):
            return self._send(200, {"code": 200, "data": {"openapi": {"paths": {"/api/v1/jobs/createTask": {"post": {
                "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
                    "model": {"type": "string"}, "input": {"type": "object"}}}}}}}}}}}})
        if p == "/api/v1/jobs/recordInfo":
            m = mode()
            if m == "taskfail":
                return self._send(200, {"code": 200, "data": {"state": "fail", "failMsg": "content policy"}})
            if m == "stuck":
                return self._send(200, {"code": 200, "data": {"state": "generating"}})
            return self._send(200, {"code": 200, "data": {"state": "success", "resultJson": json.dumps(
                {"resultUrls": ["http://%s/out/cover.png" % self.headers["Host"]]})}})
        if p == "/out/cover.png":
            if mode() == "baddl":
                self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
            data = open(os.path.join(W, "cover.png"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        return self._send(404, {"code": 404})
HTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
PY
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
WORK="$WORK" PORT="$PORT" python3 "$WORK/mock.py" &
MOCK_PID=$!
for _ in $(seq 1 40); do curl -s "http://127.0.0.1:$PORT/x" >/dev/null 2>&1 && break; sleep 0.1; done
export KIE_API_BASE="http://127.0.0.1:$PORT"

run() {  # run <mode> [extra env as VAR=val ...]
  local m="$1"; shift
  echo "$m" > "$WORK/mode"; : > "$WORK/creates.log"; rm -f "$WORK/out.jpg" "$WORK/receipt.json"
  env HOME="$WORK/home" KIE_POLL_TIMEOUT_SECONDS=2 KIE_CREATE_RETRIES=0 "$@" \
    bash "$TARGET" --prompt "a podcast cover" --title "Ep One" --out "$WORK/out.jpg" --receipt "$WORK/receipt.json" \
    >"$WORK/stdout" 2>"$WORK/stderr"
  echo $?
}

rc=$(run success KIE_BACKOFF_SCHEDULE="5")
if [[ "$rc" == "0" ]]; then pass "success: exit 0"; else fail "success: exit $rc"; tail -5 "$WORK/stderr"; fi
[[ "$(jq -r '.status' "$WORK/receipt.json" 2>/dev/null)" == "ok" ]] && pass "success: receipt status ok" || fail "success: receipt not ok"
[[ "$(jq -r '.model' "$WORK/receipt.json" 2>/dev/null)" == "gpt-image-2-5-sunburst-text-to-image" ]] && pass "success: receipt names the sunburst model" || fail "success: model missing"
[[ "$(jq -r '.kie_task_id' "$WORK/receipt.json" 2>/dev/null)" == "cover-1" ]] && pass "success: receipt keeps the KIE task id" || fail "success: task id missing"
[[ "$(jq -r '.kie_result_url' "$WORK/receipt.json" 2>/dev/null)" == http* ]] && pass "success: receipt keeps the result URL" || fail "success: result url missing"
[[ "$(jq -r '.format + " " + (.width|tostring)' "$WORK/receipt.json" 2>/dev/null)" == "jpeg 1600" ]] && pass "success: finalized square JPEG at 1600" || fail "success: finalize result wrong ($(jq -c . "$WORK/receipt.json" 2>/dev/null))"
[[ "$(wc -l < "$WORK/creates.log" | tr -d ' ')" == "1" ]] && pass "success: exactly one createTask" || fail "success: createTask count"
[[ "$(jq -r '.input.aspect_ratio + " " + .input.output_format' "$WORK/creates.log" 2>/dev/null)" == "1:1 png" ]] && pass "success: request keeps the cover aspect and png output" || fail "success: request shape"

rc=$(run auth)
[[ "$rc" == "3" ]] && pass "auth failure: exit 3 (createTask)" || fail "auth failure: exit $rc"
[[ "$(wc -l < "$WORK/creates.log" | tr -d ' ')" == "1" ]] && pass "auth failure: not retried" || fail "auth failure: retried"

rc=$(run taskfail)
[[ "$rc" == "5" ]] && pass "task failure: exit 5" || fail "task failure: exit $rc"

rc=$(run stuck)
[[ "$rc" == "4" ]] && pass "bounded poll: exit 4 on timeout" || fail "bounded poll: exit $rc"

rc=$(run baddl)
[[ "$rc" == "6" ]] && pass "download failure: exit 6" || fail "download failure: exit $rc"

# Skill 74 missing: copy the skill alone (no sibling 74) and run it.
rm -rf "$WORK/skills"; mkdir -p "$WORK/skills"; cp -R "$SKILL_DIR" "$WORK/skills/58-podcast-production-engine"
echo success > "$WORK/mode"
rc=$(env HOME="$WORK/home" bash "$WORK/skills/58-podcast-production-engine/scripts/generate_cover.sh" --prompt p --out "$WORK/x.jpg" >/dev/null 2>"$WORK/stderr"; echo $?)
[[ "$rc" == "2" ]] && pass "Skill 74 missing: exit 2" || fail "Skill 74 missing: exit $rc"
grep -q 'Skill 74.*not installed' "$WORK/stderr" && pass "Skill 74 missing: clear message, no fallback client" || fail "Skill 74 missing: no clear message"

# One KIE path: no host, endpoint, auth header or curl download left in the script.
if ! grep -qE 'api\.kie\.ai|Authorization: Bearer|recordInfo|jobs/createTask|curl ' "$TARGET"; then pass "no second KIE client in generate_cover.sh"; else fail "second KIE client crept back in"; fi

echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
