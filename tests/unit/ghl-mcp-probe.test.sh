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

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
