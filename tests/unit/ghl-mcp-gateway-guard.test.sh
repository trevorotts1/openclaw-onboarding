#!/usr/bin/env bash
# tests/unit/ghl-mcp-gateway-guard.test.sh  (D03 + D07)
#
# D03: scripts/ghl-mcp-autostart.sh must never call the openclaw CLI while the
#      gateway is down (2026.10.1: a CLI call takes the offline maintenance lock
#      and kills the gateway at bootstrap). Gate = GET /healthz == 200 on
#      gateway.port, never the CLI.
# D07: on linux-home (Contabo) the GHL MCP log dir is under the persistent
#      OpenClaw root, and both probe cron commands mkdir -p it first.
#
# The shipped functions are extracted live from the script (not copied).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
LIB="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
TMP="$(cd "$(mktemp -d)" && pwd -P)"
HS_PID=""
trap '[ -n "$HS_PID" ] && kill "$HS_PID" 2>/dev/null; rm -rf "$TMP"' EXIT
echo "=== ghl-mcp-gateway-guard.test.sh ==="

# Extract gw_up, deregister_tier2 (+ its oc_mcp_* helpers) and install_periodic_probe.
ext() { awk -v s="$1" 'index($0, s)==1 {f=1} f {print} f && $0=="}" {exit}' "$SCRIPT"; }
{
  ext 'gw_up() {'
  ext 'install_periodic_probe() {'
  ext 'oc_mcp_unset() {'
  ext 'oc_mcp_unset_verb_supported() {'
} > "$TMP/fns.sh"
# W07 retirement: deregister_tier2() is deleted with the live start flow. The
# behaviour it proved — never calling the gateway CLI while the gateway is down —
# now lives in the retirement transaction, so assert it there instead.
if grep -q 'mcp unset' "$SCRIPT" && grep -q '_ghl_gw_up' "$SCRIPT"; then
  pass "0b: retirement de-registration is gateway-guarded"
else
  fail "0b: retirement de-registration lost its gateway guard"
fi
if sed 's/^[[:space:]]*#.*$//' "$SCRIPT" | grep -q 'config set env\.vars\.GHL_COMMUNITY_MCP_URL'; then
  fail "0c: script still writes GHL_COMMUNITY_MCP_URL (retirement requires it absent)"
else
  pass "0c: no GHL_COMMUNITY_MCP_URL write remains"
fi
for f in gw_up install_periodic_probe; do
  grep -q "^$f() {" "$TMP/fns.sh" && pass "0: extracted $f from the shipped script" || fail "0: could not extract $f"
done

# Fake openclaw logging argv; fake HOME with a gateway.port in openclaw.json.
mkdir -p "$TMP/bin" "$TMP/home/.openclaw"
cat > "$TMP/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
echo "$@" >> "$OC_CALLS"
exit 0
STUB
chmod +x "$TMP/bin/openclaw"
PORT_CLOSED=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
PORT_UP=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
write_cfg() { printf '{"gateway":{"port":%s}}' "$1" > "$TMP/home/.openclaw/openclaw.json"; }

run_case() {  # run_case <fn> ; echoes call-log path. env: no crontab on PATH so the CLI branch is reached.
  local fn="$1" calls; calls="$(mktemp "$TMP/calls.XXXXXX")"; : > "$calls"
  (
    export OC_CALLS="$calls" HOME="$TMP/home" OPENCLAW_CONFIG="$TMP/home/.openclaw/openclaw.json"
    export PATH="$TMP/bin:$(dirname "$(command -v python3)"):$(dirname "$(command -v curl)"):$(dirname "$(command -v grep)"):/usr/bin:/bin"
    export PLATFORM=linux-home GHL_MCP_PORT=18080 PROBE=/bin/true CRON_TAG_PROBE='# tag' LOG_DIR="$TMP/logs" GHL_MCP_PROBE_DISABLED=0
    log() { :; }; upsert_cron_line() { return 1; }; command() { if [ "$1" = "-v" ] && [ "$2" = "crontab" ]; then return 1; fi; builtin command "$@"; }
    # shellcheck disable=SC1090
    source "$TMP/fns.sh"
    "$fn" >/dev/null 2>&1 || true
  )
  printf '%s' "$calls"
}

echo "--- D03: gateway DOWN (closed port) -> zero openclaw calls ---"
write_cfg "$PORT_CLOSED"
for fn in install_periodic_probe; do
  c="$(run_case "$fn")"; n="$(wc -l < "$c" | tr -d ' ')"
  [ "$n" = "0" ] && pass "1: $fn made 0 openclaw CLI calls with the gateway down" \
                 || fail "1: $fn made $n openclaw CLI call(s) with the gateway down: $(tr '\n' '|' < "$c")"
done

echo "--- D03 control: fake /healthz 200 server -> calls happen ---"
python3 - "$PORT_UP" > "$TMP/srv.log" 2>&1 <<'PY' &
import sys, http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/healthz" else 404); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self,*a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
HS_PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$PORT_UP/healthz" && break; sleep 0.3; done
write_cfg "$PORT_UP"
for fn in install_periodic_probe; do
  c="$(run_case "$fn")"; n="$(wc -l < "$c" | tr -d ' ')"
  [ "$n" -ge 1 ] && pass "2: $fn calls the CLI when /healthz answers 200 ($n call(s))" \
                 || fail "2: $fn made no CLI call although /healthz answers 200 (guard over-blocks)"
done
kill "$HS_PID" 2>/dev/null; HS_PID=""

echo "--- D07: log dir persistent + cron commands mkdir -p it ---"
BOX="$TMP/box"; mkdir -p "$BOX/.openclaw"; printf '{}' > "$BOX/.openclaw/openclaw.json"
got="$( HOME="$BOX" GHL_MCP_DATA_ROOT="$TMP/nodata/.openclaw" GHL_MCP_UNAME_S=Linux OPENCLAW_ROOT= \
        bash -c '. "$1"; ghl_mcp_log_dir "$(ghl_mcp_platform)"' _ "$LIB" )"
[ "$got" = "$BOX/.openclaw/logs/ghl-mcp" ] && pass "3: linux-home log dir is under the OpenClaw root ($got)" \
  || fail "3: linux-home log dir is '$got', expected $BOX/.openclaw/logs/ghl-mcp"
n_cron="$(grep -c 'mkdir -p ${LOG_DIR} && GHL_MCP_LOG_DIR=${LOG_DIR}' "$SCRIPT")"
[ "$n_cron" = "2" ] && pass "4: both probe cron commands (crontab LINE + openclaw cron add) start with mkdir -p of the log dir" \
  || fail "4: expected 2 cron commands with 'mkdir -p \${LOG_DIR} &&', found $n_cron"

# Behavioural: the generated crontab line really creates the dir before the redirect opens.
LINE_T="$(grep -o 'local LINE="[^"]*CRON_TAG_PROBE}"' "$SCRIPT" | head -1 | sed 's/^local LINE="//; s/"$//')"
cmd="$(LOG_DIR="$TMP/fresh/logs/ghl-mcp" PROBE=/bin/true CRON_TAG_PROBE='#t' bash -c 'eval "printf %s \"$1\""' _ "$LINE_T" | sed 's/^\*\/15 \* \* \* \* //; s/ #t$//')"
bash -c "$cmd"
[ -f "$TMP/fresh/logs/ghl-mcp/probe.log" ] && pass "5: running the cron command on a box without the log dir creates it and the log" \
  || fail "5: cron command did not create $TMP/fresh/logs/ghl-mcp/probe.log (cmd: $cmd)"

echo ""; echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
