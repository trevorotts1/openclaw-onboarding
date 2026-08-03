#!/usr/bin/env bash
# tests/unit/ghl-mcp-probe.test.sh — v21.5.0
#
# Proves that scripts/ghl-mcp-probe.sh can actually DETECT the failure that hid
# from every other check for two days: a GHL community MCP that is running,
# listening, and returning {"status":"healthy"} on GET /health while answering
# NOTHING on the MCP endpoint (a stale compiled dist missing
# `await server.connect(transport)`).
#
# Cases, each against a throwaway local stub server:
#   (1) HEALTHY + ANSWERING   -> probe exits 0 (OK)
#   (2) HEALTHY + DEAF        -> probe exits 3 (DEAF)          ← the outage
#   (3) NOTHING LISTENING     -> probe exits 2 (NO_LISTENER)
#   (4) WRONG SERVICE (Cognee)-> probe exits 2 (NO_LISTENER)
#   (5) ANSWERING + 858 tools -> probe exits 4 (PROFILE_DRIFT) with a curated band
#
# No network, no GHL credentials, no real MCP required. python3 + curl only.
# Exit 0 = all cases pass.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE="$REPO_ROOT/scripts/ghl-mcp-probe.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

# ── R12: THIS TEST MUST NOT WRITE THE BOX'S PRODUCTION PROBE LOG ──────────────
# Every case below drives the probe to a real verdict, and the probe APPENDS each
# verdict to $LOG_DIR/probe.log. Until the probe honoured GHL_MCP_LOG_DIR there
# was no way to redirect that, so running this test wrote genuine-looking
# OK/DEAF/NO_LISTENER/PROFILE_DRIFT lines into the box's own probe.log — the
# operator box's log was found to be 100% test output, making a real DEAF verdict
# indistinguishable from a fixture in the probe's only durable record.
# Export it for the WHOLE run, and assert at the end that the production path was
# not touched.
export GHL_MCP_LOG_DIR="$(mktemp -d)"
PROD_LOG_DIR="${HOME}/Library/Logs/ghl-mcp"
[ -d /data/logs ] && PROD_LOG_DIR="/data/logs"
PROD_LOG="$PROD_LOG_DIR/probe.log"
# Baseline: size (and existence) of the production log BEFORE any case runs.
PROD_LOG_BEFORE="absent"
[ -f "$PROD_LOG" ] && PROD_LOG_BEFORE="$(wc -c < "$PROD_LOG" 2>/dev/null | tr -d ' ')"

echo "=== ghl-mcp-probe.test.sh (v21.5.0) ==="
echo ""

if [ ! -f "$PROBE" ]; then
  echo "  FAIL: probe not found at $PROBE"; exit 1
fi
for dep in python3 curl; do
  command -v "$dep" >/dev/null 2>&1 || { echo "  SKIP: $dep not available — cannot run the stub-server cases"; exit 0; }
done

STUB="$(mktemp -d)/stub.py"
mkdir -p "$(dirname "$STUB")"
cat > "$STUB" <<'PY'
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

MODE = sys.argv[1]          # answering | deaf | cognee
TOOLS = int(sys.argv[2])
PORT = int(sys.argv[3])

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == '/health':
            if MODE == 'cognee':
                body = {"status": "ready", "version": "0.5.3-local"}
            else:
                body = {"status": "healthy", "server": "ghl-mcp-server", "tools": TOOLS}
            # Compact separators so the bytes match the real server's /health
            # exactly ({"status":"healthy",...,"tools":43,...}).
            raw = json.dumps(body, separators=(',', ':')).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(length)
        if self.path != '/mcp':
            self.send_response(404); self.end_headers(); return
        if MODE == 'deaf':
            # Exactly the outage signature: the connection is accepted, headers
            # are sent, and the MCP layer never writes a response body.
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            import time
            time.sleep(30)
            return
        payload = {"result": {"protocolVersion": "2025-06-18",
                              "capabilities": {"tools": {"listChanged": True}},
                              "serverInfo": {"name": "ghl-mcp-server", "version": "2.0.0"}},
                   "jsonrpc": "2.0", "id": 1}
        raw = ("event: message\ndata: " + json.dumps(payload) + "\n\n").encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

HTTPServer(('127.0.0.1', PORT), H).serve_forever()
PY

free_port() { python3 -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()"; }

run_case() {
  # $1 label  $2 mode  $3 tools  $4 expected_rc  $5 extra probe args
  local label="$1" mode="$2" tools="$3" want="$4" extra="${5:-}"
  local port pid rc
  port="$(free_port)"
  python3 "$STUB" "$mode" "$tools" "$port" >/dev/null 2>&1 &
  pid=$!
  # wait for the socket
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    curl -s -m 1 "http://127.0.0.1:${port}/health" >/dev/null 2>&1 && break
    sleep 0.3
  done
  # shellcheck disable=SC2086
  GHL_MCP_EXPECT_MIN_TOOLS=1 GHL_MCP_EXPECT_MAX_TOOLS=200 \
    bash "$PROBE" --once --quiet --timeout 3 --url "http://127.0.0.1:${port}" $extra >/dev/null 2>&1
  rc=$?
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  if [ "$rc" = "$want" ]; then pass "$label (exit $rc)"; else fail "$label — expected exit $want, got $rc"; fi
}

run_case "(1) healthy + answering -> OK"                     answering 43  0
run_case "(2) healthy + DEAF (the outage) -> DEAF"           deaf      43  3
run_case "(4) wrong service on the port (Cognee) -> NO_LISTENER" cognee 0  2
run_case "(5) answering but 858 tools -> PROFILE_DRIFT"      answering 858 4

# (3) nothing listening at all
PORT_DEAD="$(free_port)"
bash "$PROBE" --once --quiet --timeout 3 --url "http://127.0.0.1:${PORT_DEAD}" >/dev/null 2>&1
RC=$?
if [ "$RC" = "2" ]; then pass "(3) nothing listening -> NO_LISTENER (exit 2)"; else fail "(3) nothing listening — expected exit 2, got $RC"; fi

# The deaf case must ALSO be invisible to a plain /health check — that is the
# whole point of the probe. Prove the old-style check would have passed it.
PORT_DEAF="$(free_port)"
python3 "$STUB" deaf 43 "$PORT_DEAF" >/dev/null 2>&1 &
DEAF_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s -m 1 "http://127.0.0.1:${PORT_DEAF}/health" >/dev/null 2>&1 && break; sleep 0.3; done
if curl -fsS -m 3 "http://127.0.0.1:${PORT_DEAF}/health" 2>/dev/null | grep -q '"status":"healthy"'; then
  pass "(6) the DEAF server still reports /health healthy — proving a health check alone is not liveness"
else
  fail "(6) stub deaf server did not report a healthy /health (fixture broken)"
fi
kill "$DEAF_PID" 2>/dev/null || true
wait "$DEAF_PID" 2>/dev/null || true

# ── R13: alert escalation is STREAK-BASED, and pages a human exactly once ────
# A single transient must NOT page anyone (the probe already self-heals once), a
# 45-minute unbroken outage must, and a long outage must not re-page every 15
# minutes: Rescue Rangers enforces a hard 25-exchange-per-day cap, so a probe
# that re-escalated each cycle would burn a client's entire daily budget on one
# incident and lock out genuine escalations.
ESC_DIR="$(mktemp -d)"
ESC_PORT="$(free_port)"
cat > "$ESC_DIR/catcher.py" <<'PY'
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
out, port = sys.argv[1], int(sys.argv[2])
n = [0]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
        n[0] += 1
        open("%s/esc-%d.json" % (out, n[0]), "wb").write(body)
        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
HTTPServer(('127.0.0.1', port), H).serve_forever()
PY
python3 "$ESC_DIR/catcher.py" "$ESC_DIR" "$ESC_PORT" >/dev/null 2>&1 &
ESC_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
  curl -s -m 1 -X POST "http://127.0.0.1:${ESC_PORT}/" >/dev/null 2>&1 && break
  sleep 0.3
done
rm -f "$ESC_DIR"/esc-*.json 2>/dev/null || true   # discard the readiness ping

STREAK_LOG_DIR="$(mktemp -d)"
DEAD_PORT="$(free_port)"
esc_count() { ls "$ESC_DIR"/esc-*.json 2>/dev/null | wc -l | tr -d ' '; }
run_streak_probe() {
  GHL_MCP_LOG_DIR="$STREAK_LOG_DIR" \
  RESCUE_RANGERS_WEBHOOK_URL="http://127.0.0.1:${ESC_PORT}" \
  FLEET_STANDING_BOX_SLUG="unit-test-box" \
    bash "$PROBE" --once --quiet --timeout 2 --url "http://127.0.0.1:${DEAD_PORT}" >/dev/null 2>&1
}

run_streak_probe; run_streak_probe          # probes 1 and 2
if [ "$(esc_count)" = "0" ]; then
  pass "(9) two consecutive failures do NOT page Rescue Rangers (a transient must not escalate)"
else
  fail "(9) escalated after only $(esc_count) — the 3-probe (~45 min) threshold is not being honoured"
fi

run_streak_probe                            # probe 3 -> the 45-minute threshold
if [ "$(esc_count)" = "1" ]; then
  pass "(10) the 3rd consecutive identical failure escalates exactly once (~45 minutes)"
else
  fail "(10) expected exactly 1 escalation on the 3rd failure, got $(esc_count)"
fi

run_streak_probe; run_streak_probe          # probes 4 and 5
if [ "$(esc_count)" = "1" ]; then
  pass "(11) a continuing outage does NOT re-page every cycle (protects the 25/day Rangers cap)"
else
  fail "(11) re-escalated on a continuing outage — now $(esc_count) escalations"
fi

# The payload must carry the canonical fleet slug as boxName: an escalation with
# the wrong boxName cannot be attributed and is not counted against the right
# account, which is the entire purpose of that field.
# NOTE: do not assume the filename. The catcher's counter also advanced for the
# readiness ping, so the first real escalation is not necessarily esc-1.json.
ESC_FILE="$(ls "$ESC_DIR"/esc-*.json 2>/dev/null | head -1)"
if [ -n "$ESC_FILE" ] && ESC_FILE="$ESC_FILE" python3 -c "
import json,os,sys
d=json.load(open(os.environ['ESC_FILE']))
need=['action','person','clientName','agentName','boxName','boxType','openclawVersion','problem','alreadyTried','returnTo']
sys.exit(0 if all(k in d for k in need) and d['boxName']=='unit-test-box' else 1)" 2>/dev/null; then
  pass "(12) the escalation payload carries all nine required fields with the canonical boxName"
else
  fail "(12) the escalation payload is malformed or boxName is not the fleet slug"
fi

# ── bash 3.2 COMPATIBILITY, on the interpreter the schedulers actually use ───
# macOS ships /bin/bash 3.2.57, and BOTH periodic callers invoke this script as
# `/bin/bash <probe>` — the launchd probe plist and the VPS cron line. Constructs
# that are fine in bash 5 (notably expanding an EMPTY array as "${arr[@]}" under
# `set -u`) abort outright there. Re-running the escalation path under the real
# /bin/bash is the only way this class of bug shows up before a client box hits it.
if [ -x /bin/bash ]; then
  BASH32_DIR="$(mktemp -d)"
  ESC_BEFORE_32="$(esc_count)"
  # No RESCUE_RANGERS_WEBHOOK_SECRET set: the empty-header case that broke.
  for _ in 1 2 3; do
    env -u RESCUE_RANGERS_WEBHOOK_SECRET \
      GHL_MCP_LOG_DIR="$BASH32_DIR" \
      RESCUE_RANGERS_WEBHOOK_URL="http://127.0.0.1:${ESC_PORT}" \
      FLEET_STANDING_BOX_SLUG="unit-test-box-32" \
      /bin/bash "$PROBE" --once --quiet --timeout 2 --url "http://127.0.0.1:${DEAD_PORT}" >/dev/null 2>&1
  done
  if [ "$(esc_count)" = "$((ESC_BEFORE_32 + 1))" ]; then
    pass "(14) the escalation path runs and escalates under /bin/bash $(/bin/bash --version | head -1 | sed 's/.*version \([0-9.]*\).*/\1/') with no secret set"
  else
    fail "(14) escalation under /bin/bash did not fire exactly once ($ESC_BEFORE_32 -> $(esc_count)) — likely a bash 3.2 incompatibility (empty array under set -u?)"
  fi
fi

# Identity is FAIL-CLOSED: with no FLEET_STANDING_BOX_SLUG the probe must NOT
# send an unattributable payload into the shared Rangers queue.
ESC_BEFORE="$(esc_count)"
NOSLUG_DIR="$(mktemp -d)"
for _ in 1 2 3; do
  GHL_MCP_LOG_DIR="$NOSLUG_DIR" \
  RESCUE_RANGERS_WEBHOOK_URL="http://127.0.0.1:${ESC_PORT}" \
  FLEET_STANDING_BOX_SLUG="" \
    bash "$PROBE" --once --quiet --timeout 2 --url "http://127.0.0.1:${DEAD_PORT}" >/dev/null 2>&1
done
if [ "$(esc_count)" = "$ESC_BEFORE" ]; then
  pass "(13) with no FLEET_STANDING_BOX_SLUG the probe sends NO escalation (identity is fail-closed)"
else
  fail "(13) sent an unattributable escalation with no box slug ($ESC_BEFORE -> $(esc_count))"
fi

kill "$ESC_PID" 2>/dev/null || true
wait "$ESC_PID" 2>/dev/null || true

# ── (7) R12: the test must not have polluted the production probe log ────────
# This is the regression guard for the defect itself: if someone reverts the
# probe's GHL_MCP_LOG_DIR support, or drops the export at the top of this file,
# this case fails instead of silently poisoning a box's diagnostics again.
PROD_LOG_AFTER="absent"
[ -f "$PROD_LOG" ] && PROD_LOG_AFTER="$(wc -c < "$PROD_LOG" 2>/dev/null | tr -d ' ')"
if [ "$PROD_LOG_BEFORE" = "$PROD_LOG_AFTER" ]; then
  pass "(7) production probe.log untouched by this test (was: $PROD_LOG_BEFORE, now: $PROD_LOG_AFTER)"
else
  fail "(7) this test WROTE the production probe.log at $PROD_LOG (was: $PROD_LOG_BEFORE, now: $PROD_LOG_AFTER) — the probe is ignoring GHL_MCP_LOG_DIR again"
fi

# And the redirected log must actually have received the verdicts, proving the
# isolation is real redirection and not merely a silenced writer.
if [ -s "$GHL_MCP_LOG_DIR/probe.log" ]; then
  pass "(8) verdicts were written to the isolated GHL_MCP_LOG_DIR instead"
else
  fail "(8) no probe.log in the isolated GHL_MCP_LOG_DIR — the probe wrote its verdicts somewhere unexpected"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
