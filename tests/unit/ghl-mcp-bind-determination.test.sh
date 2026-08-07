#!/usr/bin/env bash
# ghl-mcp-bind-determination.test.sh
#
# DEFECT 3: scripts/ghl-mcp-assert-runtime.sh check 13 must never silently
# downgrade "I could not determine the bind address" into a pass.
#
# THE DEFECT, as measured. In the VPS container there is no lsof. The old check
# was `if command -v lsof …` with NO else branch, so _BIND_VERDICT stayed
# "unknown" and printed an INFO line reading "no listener observed (or lsof
# unavailable)". That one sentence conflated:
#     the port is FREE                      (a real answer — fine)
#     we have NO WAY TO TELL what is bound  (a check that did not run)
# and reported the second as INFO, which is indistinguishable from a pass. It
# masked a genuine 0.0.0.0:8765 exposure that was independently confirmed via
# /proc/net/tcp (LISTEN state 0A).
#
# WHAT IS PROVEN HERE — the four verdicts, driven through the REAL gate:
#   1. a real socket bound to 0.0.0.0 is FATAL          (tool-independent: an
#      actual listening socket, not a fixture)
#   2. a real socket bound to 127.0.0.1 PASSES          (not a permanent FAIL)
#   3. no method available => FATAL "undeterminable"    (never INFO)
#   4. a genuinely free port => INFO, not a failure     (a real answer stays one)
#
# Cases 1 and 2 bind actual sockets, so they hold on whichever of lsof / ss /
# /proc/net/tcp the runner happens to have. Case 3 is only reachable by removing
# every source, which is why the two /proc paths carry documented override hooks
# (the same convention as GHL_MCP_DIR / GHL_MCP_PLIST / GHL_MCP_OC_JSON in that
# file) — otherwise the fail-path would be untestable on Linux, and an untested
# fail-path is what let the silent downgrade survive in the first place.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
GATE="$REPO_ROOT/scripts/ghl-mcp-assert-runtime.sh"

FAILURES=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }

[ -f "$GATE" ] || { printf 'FATAL: %s not found\n' "$GATE" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { printf 'FATAL: python3 required\n' >&2; exit 1; }

BOX="$(mktemp -d "${TMPDIR:-/tmp}/ghl-bind-box.XXXXXX")"
cleanup() {
  [ -n "${LISTENER_PID:-}" ] && kill "$LISTENER_PID" 2>/dev/null
  rm -rf "$BOX"
}
trap cleanup EXIT

# A minimal simulated box: an MCP dir so the gate does not exit 2 (SKIP), and a
# pin file so it has an expectation to compare against. Every OTHER check is
# expected to fail here — this test reads ONLY the check-13 lines, by content,
# so it is unaffected by the rest of the gate's verdicts.
# The gate resolves its pin from "$SELF_DIR/../config/ghl-mcp-pin.env" FIRST, so
# it must RUN FROM THE BOX for the fixture pin (and its port) to win over the
# repo's real one. Copying it there is also closer to how it runs on a box:
# delivered into $OC_ROOT/scripts/ with $OC_ROOT/config/ as its sibling.
mkdir -p "$BOX/mcp" "$BOX/config" "$BOX/logs" "$BOX/scripts"
cp "$GATE" "$BOX/scripts/ghl-mcp-assert-runtime.sh"
BOX_GATE="$BOX/scripts/ghl-mcp-assert-runtime.sh"

pinfile() {  # pinfile <port>
  cat > "$BOX/config/ghl-mcp-pin.env" <<EOF
GHL_MCP_VETTED_COMMIT="0000000000000000000000000000000000000000"
GHL_MCP_TOOL_PROFILE="curated"
GHL_MCP_REPO_URL="https://example.invalid/mirror.git"
GHL_MCP_PIN_VETTED_VERDICT="CLEAN"
GHL_MCP_PORT=$1
EOF
}

# run_gate <port> [extra env assignments...] -> output in $OUT
run_gate() {
  local _port="$1"; shift
  pinfile "$_port"
  OUT="$(
    env "$@" \
      GHL_MCP_DIR="$BOX/mcp" \
      GHL_MCP_LOG_DIR_OVERRIDE="$BOX/logs" \
      GHL_MCP_OC_JSON="$BOX/nonexistent.json" \
      GHL_MCP_PLIST="$BOX/nonexistent.plist" \
      GHL_MCP_PROBE_PLIST="$BOX/nonexistent-probe.plist" \
      GHL_MCP_SYSTEMD_UNIT="$BOX/nonexistent.service" \
      HOME="$BOX" \
      /bin/bash "$BOX_GATE" 2>&1 || true
  )"
}

# Bind a real listening socket and hold it open. Sets $PORT and $LISTENER_PID.
#
# NOT a command substitution: `$( … )` waits for the subshell's stdout to CLOSE,
# and a backgrounded child inherits that stdout — so the substitution would block
# for the listener's whole lifetime. The port is handed back through a file, and
# the child's stdio is fully detached.
LISTENER_SCRIPT="$BOX/listener.py"
cat > "$LISTENER_SCRIPT" <<'PYEOF'
import socket, sys, time
host, portfile = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((host, 0))
s.listen(5)
with open(portfile, "w") as fh:
    fh.write(str(s.getsockname()[1]))
time.sleep(60)
PYEOF

start_listener() {  # start_listener <host>   -> sets PORT, LISTENER_PID
  local _host="$1" _portfile="$BOX/port.txt"
  rm -f "$_portfile"
  python3 "$LISTENER_SCRIPT" "$_host" "$_portfile" >/dev/null 2>&1 &
  LISTENER_PID=$!
  local _i=0
  while [ ! -s "$_portfile" ] && [ "$_i" -lt 100 ]; do sleep 0.1; _i=$((_i+1)); done
  PORT="$(cat "$_portfile" 2>/dev/null)"
}

stop_listener() {
  [ -n "${LISTENER_PID:-}" ] && kill "$LISTENER_PID" 2>/dev/null
  wait "${LISTENER_PID:-0}" 2>/dev/null
  LISTENER_PID=""
  rm -f "$BOX/port.txt" 2>/dev/null
}

printf 'ghl-mcp-bind-determination: DEFECT 3 — a security check that cannot answer has FAILED\n\n'

# ── CASE 1. A REAL 0.0.0.0 bind must be FATAL, not a warning. ────────────────
start_listener 0.0.0.0
if [ -n "${PORT:-}" ]; then
  run_gate "$PORT"
  if printf '%s' "$OUT" | grep -q "FAIL.*:${PORT} is bound to ALL INTERFACES"; then
    pass "a real 0.0.0.0 bind is FATAL (was a WARN; the R2 bind guard has landed, so the exemption is gone)"
  else
    fail "a real 0.0.0.0 bind did NOT produce a FATAL — check 13 output was: $(printf '%s' "$OUT" | grep -i "${PORT}" | head -2)"
  fi
else
  fail "could not start a 0.0.0.0 listener — case 1 did not run"
fi
stop_listener

# ── CASE 2. A REAL loopback bind must PASS (the guard is not a permanent FAIL).
start_listener 127.0.0.1
if [ -n "${PORT:-}" ]; then
  run_gate "$PORT"
  if printf '%s' "$OUT" | grep -q "PASS.*:${PORT} is bound to LOOPBACK"; then
    pass "a real 127.0.0.1 bind PASSES — the check still has a green path"
  else
    fail "a real loopback bind did NOT pass — check 13 output was: $(printf '%s' "$OUT" | grep -i "${PORT}" | head -2)"
  fi
else
  fail "could not start a loopback listener — case 2 did not run"
fi
stop_listener

# ── CASE 3. NO METHOD AVAILABLE => FATAL "undeterminable", never INFO. ───────
# Every source removed: an empty PATH hides lsof and ss, and both /proc paths
# are pointed at files that do not exist. This is the VPS container shape.
# A SANITISED PATH, not an empty one. Emptying PATH outright also removes
# dirname/sed/grep and the gate cannot even start — which would "pass" this case
# for entirely the wrong reason. Symlink in everything the gate needs and
# deliberately omit lsof and ss, so the ONLY thing missing is the ability to
# determine a bind. Both /proc paths are then pointed at files that do not
# exist. That is precisely the VPS container shape.
mkdir -p "$BOX/sanitisedbin"
for _t in dirname basename sed grep awk cat cut tr wc head tail sort id date \
          python3 printf uname stat cmp cp mv rm mkdir ls; do
  _src="$(command -v "$_t" 2>/dev/null || true)"
  [ -n "$_src" ] && ln -sf "$_src" "$BOX/sanitisedbin/$_t" 2>/dev/null
done
if command -v lsof >/dev/null 2>&1 || command -v ss >/dev/null 2>&1; then
  : # they exist on this runner, and are deliberately NOT linked in
fi
run_gate 8765 \
  PATH="$BOX/sanitisedbin" \
  GHL_MCP_PROC_NET_TCP="$BOX/no-such-proc-tcp" \
  GHL_MCP_PROC_NET_TCP6="$BOX/no-such-proc-tcp6"
if printf '%s' "$OUT" | grep -q "FAIL.*UNDETERMINABLE"; then
  pass "no determination method => FATAL 'undeterminable' (was a silent INFO that masked a live 0.0.0.0 exposure)"
elif printf '%s' "$OUT" | grep -qi "INFO.*bind"; then
  fail "an undeterminable bind was reported as INFO — the exact silent downgrade this fixes"
else
  fail "undeterminable case produced neither the FATAL nor a recognisable line: $(printf '%s' "$OUT" | tail -3)"
fi

# ── CASE 4. A genuinely free port is a REAL answer and must stay INFO. ───────
FREE_PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
run_gate "$FREE_PORT"
if printf '%s' "$OUT" | grep -q "INFO.*nothing is LISTENING on :${FREE_PORT}"; then
  pass "a proven-free port stays INFO — determination succeeded, so it is not a failure"
elif printf '%s' "$OUT" | grep -q "FAIL.*:${FREE_PORT}"; then
  fail "a proven-free port was reported FATAL — over-broad; every stopped server would go red"
else
  fail "free-port case produced no recognisable check-13 line: $(printf '%s' "$OUT" | tail -3)"
fi

printf '\n'
if [ "$FAILURES" -gt 0 ]; then
  printf 'ghl-mcp-bind-determination: %s FAILURE(S) — the bind check can still pass without answering.\n' "$FAILURES" >&2
  exit 1
fi
printf 'ghl-mcp-bind-determination: all cases passed.\n'
exit 0
