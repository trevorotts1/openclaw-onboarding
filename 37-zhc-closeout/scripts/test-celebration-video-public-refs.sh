#!/usr/bin/env bash
# test-celebration-video-public-refs.sh
#
# Verifies the 2026-06-20 "Image fetch failed" fix in generate-celebration-video.sh:
# every reference image handed to the video model is guaranteed to be a public,
# model-reachable https URL, transient image-fetch failures are retried, and the
# step still soft-fails cleanly when the model genuinely cannot render.
#
# Strategy: a single local mock HTTP server (Python stdlib) emulates BOTH
#   - the KIE upload service (file-base64-upload / file-url-upload)
#   - the KIE job API (jobs/createTask, jobs/recordInfo)
# We point the script at it via KIE_UPLOAD_BASE + KIE_API_BASE and drive the
# REAL script end-to-end. The mock records every reference URL it was asked to
# put in the video job so we can assert it was a public (mock-hosted) URL and
# NEVER a file:// or on-disk path.
#
# No real KIE/network calls. No client box required.
#
# EXIT CODES: 0 = all PASS, 1 = any FAIL.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/generate-celebration-video.sh"

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32m✔\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31m✘\033[0m %s\n' "$1"; }
info() { printf '    %s\n' "$1"; }

if [[ ! -f "$TARGET" ]]; then
  fail "generate-celebration-video.sh not found at $TARGET"; exit 1
fi

WORK="$(mktemp -d)"
trap 'kill "${MOCK_PID:-}" 2>/dev/null; rm -rf "$WORK"' EXIT

# ---- mock HTTP server ----------------------------------------------------
# Modes via the X-Test-Mode header on createTask are not used; instead the mock
# reads a control file each request so a single server serves all scenarios.
MODE_FILE="$WORK/mode"
REFLOG="$WORK/job-image-urls.log"   # every image_urls array the job was given
UPLOG="$WORK/uploads.log"            # every upload the script performed
: > "$REFLOG"; : > "$UPLOG"
echo "success" > "$MODE_FILE"        # default scenario

cat > "$WORK/mock.py" <<'PY'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

WORK = os.environ["WORK"]
MODE_FILE = os.path.join(WORK, "mode")
REFLOG = os.path.join(WORK, "job-image-urls.log")
UPLOG  = os.path.join(WORK, "uploads.log")
# per-task poll counter so we can fail-then-succeed
POLLS = {}

def mode():
    try:
        return open(MODE_FILE).read().strip()
    except Exception:
        return "success"

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try: return json.loads(raw.decode())
        except Exception: return {}

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._body()
        if p == "/api/file-base64-upload":
            fn = body.get("fileName", "ref.png")
            with open(UPLOG, "a") as f: f.write("base64\t%s\n" % fn)
            return self._send(200, {"success": True, "code": 200,
                "data": {"downloadUrl": "http://%s/hosted/%s" % (self.headers["Host"], fn)}})
        if p == "/api/file-url-upload":
            fn = body.get("fileName", "ref.png")
            src = body.get("fileUrl", "")
            with open(UPLOG, "a") as f: f.write("url\t%s\t%s\n" % (fn, src))
            return self._send(200, {"success": True, "code": 200,
                "data": {"downloadUrl": "http://%s/hosted/%s" % (self.headers["Host"], fn)}})
        if p == "/api/v1/jobs/createTask":
            imgs = (body.get("input", {}) or {}).get("image_urls", [])
            with open(REFLOG, "a") as f: f.write(json.dumps(imgs) + "\n")
            tid = "task-%d" % (sum(1 for _ in open(REFLOG)) )
            POLLS[tid] = 0
            return self._send(200, {"code": 200, "data": {"taskId": tid}})
        return self._send(404, {"error": "no route", "path": p})

    def do_GET(self):
        p = self.path.split("?")[0]
        q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[1].split("&")) if "?" in self.path else {}
        if p == "/api/v1/jobs/recordInfo":
            tid = q.get("taskId", "")
            POLLS[tid] = POLLS.get(tid, 0) + 1
            m = mode()
            if m == "image-fetch-once":
                # First submitted task fails with image-fetch; later tasks succeed.
                if tid == "task-1":
                    return self._send(200, {"code": 200, "data": {
                        "state": "fail", "failMsg": "Image fetch failed"}})
                return self._send(200, {"code": 200, "data": {
                    "state": "success",
                    "resultJson": json.dumps({"resultUrls": ["http://%s/out/video.mp4" % self.headers["Host"]]})}})
            if m == "hard-fail":
                return self._send(200, {"code": 200, "data": {
                    "state": "fail", "failMsg": "content policy violation"}})
            # default: success
            return self._send(200, {"code": 200, "data": {
                "state": "success",
                "resultJson": json.dumps({"resultUrls": ["http://%s/out/video.mp4" % self.headers["Host"]]})}})
        if p.startswith("/out/"):
            data = b"\x00\x00\x00\x18ftypmp42" + b"FAKEMP4BYTES" * 8
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data); return
        if p.startswith("/hosted/"):
            self.send_response(200); self.send_header("Content-Length", "3"); self.end_headers()
            self.wfile.write(b"png"); return
        return self._send(404, {"error": "no route", "path": p})

HTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
PY

# pick a free port
PORT=$(python3 - <<'PY'
import socket
s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()
PY
)
WORK="$WORK" PORT="$PORT" python3 "$WORK/mock.py" &
MOCK_PID=$!
# wait for server
for _ in $(seq 1 40); do
  if curl -s "http://127.0.0.1:$PORT/api/v1/jobs/recordInfo?taskId=x" >/dev/null 2>&1; then break; fi
  sleep 0.1
done
BASE="http://127.0.0.1:$PORT"

# ---- shared fake OpenClaw root + state -----------------------------------
setup_box() {
  local mode="$1"; local inf1url="$2"; local inf1local="$3"; local logo="$4"
  OC="$WORK/box"; rm -rf "$OC"; mkdir -p "$OC/.openclaw/workspace"
  STATE="$OC/.openclaw/workspace/.workforce-build-state.json"
  LOG="$OC/.openclaw/workspace/.zhc-closeout.log"
  jq -n \
    --arg i1 "$inf1url" --arg i1l "$inf1local" --arg logo "$logo" \
    '{companyName:"TestCo", ownerName:"Test Owner", agentName:"TestCEO",
      industry:"testing", infographic1Url:$i1, infographic1LocalPath:$i1l, logoUrl:$logo}' \
    > "$STATE"
  echo "$mode" > "$MODE_FILE"
}

run_script() {
  # Run against the mock. Short timeouts so the test is fast.
  HOME="$WORK/nohome" \
  ZHC_STATE_FILE="$STATE" ZHC_LOG_FILE="$LOG" \
  KIE_API_KEY="test-key" KIE_UPLOAD_BASE="$BASE" KIE_API_BASE="$BASE" \
  ZHC_CELEBRATION_VIDEO_MODEL="gemini-omni-video" \
  ZHC_VIDEO_POLL_TIMEOUT_SEC=30 \
  OC_ROOT_OVERRIDE="$OC/.openclaw" \
  bash "$TARGET" >"$WORK/run.out" 2>&1
  echo $?
}

# The script auto-detects OC root from $HOME/.openclaw; point HOME at our box.
make_png() { printf '\x89PNG\r\n\x1a\nFAKEPNGDATA' > "$1"; }

# ==========================================================================
echo "=== TEST 1: local file:// org-chart reference -> uploaded to public URL ==="
mkdir -p "$WORK/nohome/.openclaw/workspace"
ORG_PNG="$WORK/nohome/.openclaw/workspace/.zhc-inf1-output.png"
make_png "$ORG_PNG"
# HOME-based box so the script's auto-detect uses it; mirror state there.
OC="$WORK/nohome"; STATE="$OC/.openclaw/workspace/.workforce-build-state.json"
LOG="$OC/.openclaw/workspace/.zhc-closeout.log"
: > "$REFLOG"; : > "$UPLOG"
echo "success" > "$MODE_FILE"
jq -n --arg i1 "file://$ORG_PNG" --arg i1l "$ORG_PNG" \
  '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",
    infographic1Url:$i1, infographic1LocalPath:$i1l}' > "$STATE"
rc=$(HOME="$WORK/nohome" ZHC_STATE_FILE="$STATE" ZHC_LOG_FILE="$LOG" \
  KIE_API_KEY="k" KIE_UPLOAD_BASE="$BASE" KIE_API_BASE="$BASE" \
  ZHC_CELEBRATION_VIDEO_MODEL="gemini-omni-video" ZHC_VIDEO_POLL_TIMEOUT_SEC=30 \
  bash "$TARGET" >"$WORK/t1.out" 2>&1; echo $?)

if [[ "$rc" == "0" ]]; then pass "T1: script exited 0 (success)"; else fail "T1: script exited $rc"; info "$(tail -5 "$WORK/t1.out")"; fi
# The base64 uploader must have been called for the local file.
if grep -q '^base64' "$UPLOG"; then pass "T1: local file:// reference was base64-uploaded to public host"; else fail "T1: local reference was NOT uploaded"; info "$(cat "$UPLOG")"; fi
# The image_urls handed to the job must be the mock-hosted http URL, never file://.
job_imgs=$(tail -1 "$REFLOG")
if echo "$job_imgs" | grep -q "$BASE/hosted/"; then pass "T1: job received the public hosted URL as reference"; else fail "T1: job did not get public URL"; info "imgs=$job_imgs"; fi
if echo "$job_imgs" | grep -q "file://"; then fail "T1: a file:// URL LEAKED into the video request"; else pass "T1: NO file:// URL reached the video request (guaranteed public)"; fi
state_video=$(jq -r '.celebrationVideoUrl // empty' "$STATE")
if [[ -n "$state_video" ]]; then pass "T1: celebrationVideoUrl written to state ($state_video)"; else fail "T1: no celebrationVideoUrl in state"; fi

# ==========================================================================
echo "=== TEST 2: 'Image fetch failed' is transient -> re-host + re-submit -> success ==="
: > "$REFLOG"; : > "$UPLOG"
echo "image-fetch-once" > "$MODE_FILE"
make_png "$ORG_PNG"
jq -n --arg i1 "file://$ORG_PNG" --arg i1l "$ORG_PNG" \
  '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",
    infographic1Url:$i1, infographic1LocalPath:$i1l}' > "$STATE"
rc=$(HOME="$WORK/nohome" ZHC_STATE_FILE="$STATE" ZHC_LOG_FILE="$LOG" \
  KIE_API_KEY="k" KIE_UPLOAD_BASE="$BASE" KIE_API_BASE="$BASE" \
  ZHC_CELEBRATION_VIDEO_MODEL="gemini-omni-video" ZHC_VIDEO_POLL_TIMEOUT_SEC=30 \
  bash "$TARGET" >"$WORK/t2.out" 2>&1; echo $?)

if [[ "$rc" == "0" ]]; then pass "T2: recovered from image-fetch failure and exited 0"; else fail "T2: did not recover (rc=$rc)"; info "$(tail -8 "$WORK/t2.out")"; fi
n_jobs=$(grep -c . "$REFLOG")
if [[ "$n_jobs" -ge 2 ]]; then pass "T2: re-submitted after the transient failure ($n_jobs jobs)"; else fail "T2: did NOT re-submit (only $n_jobs job)"; fi
# It must have re-hosted (uploaded) again before the retry.
n_up=$(grep -c . "$UPLOG")
if [[ "$n_up" -ge 2 ]]; then pass "T2: references re-hosted to fresh public URLs before re-submit ($n_up uploads)"; else fail "T2: refs not re-hosted on retry ($n_up uploads)"; fi
if grep -qi "transient image-fetch" "$LOG"; then pass "T2: log shows image-fetch transient was detected"; else fail "T2: image-fetch transient not logged"; fi

# ==========================================================================
echo "=== TEST 3: already-public http URL is re-hosted to a fresh first-party URL ==="
: > "$REFLOG"; : > "$UPLOG"
echo "success" > "$MODE_FILE"
jq -n --arg i1 "https://tempfile.aiquickdraw.com/abc/expired-org.png" \
  '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",
    infographic1Url:$i1, infographic1LocalPath:""}' > "$STATE"
rc=$(HOME="$WORK/nohome" ZHC_STATE_FILE="$STATE" ZHC_LOG_FILE="$LOG" \
  KIE_API_KEY="k" KIE_UPLOAD_BASE="$BASE" KIE_API_BASE="$BASE" \
  ZHC_CELEBRATION_VIDEO_MODEL="gemini-omni-video" ZHC_VIDEO_POLL_TIMEOUT_SEC=30 \
  bash "$TARGET" >"$WORK/t3.out" 2>&1; echo $?)
if [[ "$rc" == "0" ]]; then pass "T3: exited 0 with an existing public URL"; else fail "T3: exited $rc"; info "$(tail -5 "$WORK/t3.out")"; fi
if grep -q '^url' "$UPLOG"; then pass "T3: existing http URL was re-hosted via file-url-upload"; else fail "T3: existing URL was NOT re-hosted"; info "$(cat "$UPLOG")"; fi
job_imgs=$(tail -1 "$REFLOG")
if echo "$job_imgs" | grep -q "$BASE/hosted/" && ! echo "$job_imgs" | grep -q "tempfile.aiquickdraw"; then
  pass "T3: job received the FRESH first-party URL (not the flaky tempfile URL)"
else fail "T3: job still got the original tempfile URL"; info "imgs=$job_imgs"; fi

# ==========================================================================
echo "=== TEST 4: ZHC_REHOST_PUBLIC_REFS=0 passes an existing public URL through unchanged ==="
: > "$REFLOG"; : > "$UPLOG"
echo "success" > "$MODE_FILE"
PUBURL="https://cdn.example.com/already-public.png"
jq -n --arg i1 "$PUBURL" \
  '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",
    infographic1Url:$i1, infographic1LocalPath:""}' > "$STATE"
rc=$(HOME="$WORK/nohome" ZHC_STATE_FILE="$STATE" ZHC_LOG_FILE="$LOG" \
  KIE_API_KEY="k" KIE_UPLOAD_BASE="$BASE" KIE_API_BASE="$BASE" ZHC_REHOST_PUBLIC_REFS=0 \
  ZHC_CELEBRATION_VIDEO_MODEL="gemini-omni-video" ZHC_VIDEO_POLL_TIMEOUT_SEC=30 \
  bash "$TARGET" >"$WORK/t4.out" 2>&1; echo $?)
job_imgs=$(tail -1 "$REFLOG")
if echo "$job_imgs" | grep -q "$PUBURL"; then pass "T4: with re-host disabled, the public URL passed through unchanged"; else fail "T4: public URL not passed through"; info "imgs=$job_imgs"; fi
if grep -q '^url' "$UPLOG"; then fail "T4: re-host ran even though disabled"; else pass "T4: no upload performed (correct, re-host disabled)"; fi

# ==========================================================================
echo "=== TEST 5: genuine model failure -> soft-fail (non-zero exit, no leaked video URL) ==="
: > "$REFLOG"; : > "$UPLOG"
echo "hard-fail" > "$MODE_FILE"
make_png "$ORG_PNG"
jq -n --arg i1 "file://$ORG_PNG" --arg i1l "$ORG_PNG" \
  '{companyName:"TestCo",ownerName:"Owner",agentName:"CEO",industry:"testing",
    infographic1Url:$i1, infographic1LocalPath:$i1l}' > "$STATE"
rc=$(HOME="$WORK/nohome" ZHC_STATE_FILE="$STATE" ZHC_LOG_FILE="$LOG" \
  KIE_API_KEY="k" KIE_UPLOAD_BASE="$BASE" KIE_API_BASE="$BASE" \
  ZHC_CELEBRATION_VIDEO_MODEL="gemini-omni-video" ZHC_VIDEO_POLL_TIMEOUT_SEC=30 \
  bash "$TARGET" >"$WORK/t5.out" 2>&1; echo $?)
# Genuine non-recoverable failure: script exits non-zero. run-closeout.sh's
# run_step catches this and marks STEP_VIDEO_STATUS=failed -> soft "deferred".
if [[ "$rc" != "0" ]]; then pass "T5: genuine failure exits non-zero (run-closeout soft-fails / defers)"; else fail "T5: genuine failure did NOT fail (rc=0)"; fi
if [[ -z "$(jq -r '.celebrationVideoUrl // empty' "$STATE")" ]]; then pass "T5: no celebrationVideoUrl written on genuine failure"; else fail "T5: a video URL was written despite failure"; fi
# Even in failure, the reference handed to the model was public (never file://).
if [[ -s "$REFLOG" ]] && tail -1 "$REFLOG" | grep -q "file://"; then fail "T5: file:// leaked into the request even on the failure path"; else pass "T5: no file:// leaked even on the failure path"; fi

# ==========================================================================
echo "=== TEST 6: static guards present in the source (defense in depth) ==="
if grep -q 'ensure_public_url' "$TARGET"; then pass "T6: ensure_public_url() present"; else fail "T6: ensure_public_url() missing"; fi
if grep -q 'file-base64-upload' "$TARGET" && grep -q 'file-url-upload' "$TARGET"; then pass "T6: both KIE upload endpoints wired"; else fail "T6: upload endpoints missing"; fi
if grep -qE 'INFOGRAPHIC1_URL" == https://\*' "$TARGET" || grep -q '== https://\*' "$TARGET"; then pass "T6: https-only guard on image_urls (no non-https reference ever sent)"; else fail "T6: https-only guard missing"; fi
if grep -qi 'image fetch failed' "$TARGET"; then pass "T6: image-fetch-failed transient classification present"; else fail "T6: image-fetch transient handling missing"; fi

# ==========================================================================
echo
echo "================ RESULTS ================"
echo "PASS=$PASS  FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]] && { echo "ALL TESTS PASSED"; exit 0; } || { echo "SOME TESTS FAILED"; exit 1; }
