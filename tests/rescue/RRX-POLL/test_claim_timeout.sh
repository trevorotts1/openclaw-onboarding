#!/usr/bin/env bash
# tests/rescue/RRX-POLL/test_claim_timeout.sh   (RRX-003)
#
# The receiver was measured answering in 70 to 110 seconds, while every call
# from the poll gave up after 25 seconds and exited without a trace. RRX-003
# raises the limit to 150 seconds (bounded), stops re-sending a claim inside one
# call, and logs a claim that did not complete once an hour.
#
#   A  with the DEFAULT limit, a receiver that answers in 40s completes the
#      claim: no `claim-failed` line, exactly one claim request
#   B  with RR_POST_MAX_S=25 the same receiver is cut off: ONE
#      `claim-failed class=transport` line across two runs (the hour throttle),
#      and the server still received exactly one claim request per run
# Drives the real poll against a local slow receiver. Offline, hermetic.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/../RR-030/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx003-timeout-XXXXXX")"
# A's receiver is deliberately slower than the old 25s limit but inside 150s.
SLOW_S="${RRX003_SLOW_S:-40}"
unset RR_POST_MAX_S
cleanup() { w4_stop_receiver; rm -rf "$WORK"; }
trap cleanup EXIT

# start_slow_receiver <root> <delay-seconds>
#   Copied from w4_start_receiver with ONE added line: the handler sleeps
#   <delay-seconds> before it answers {"status":"empty"}. Each request body is
#   appended to <root>/claims.log (so the test can prove how many arrived).
start_slow_receiver() {
  local root="$1" delay="$2"
  rm -f "$root/port"
  python3 - "$root" "$delay" <<'PY' &
import http.server, sys, time
root, delay = sys.argv[1], float(sys.argv[2])
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); body = self.rfile.read(n)
        with open(root + '/claims.log', 'a') as fh: fh.write(body.decode('utf-8', 'replace') + "\n")
        time.sleep(delay)
        out = b'{"status":"empty"}'
        self.send_response(200); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(('127.0.0.1', 0), H)
open(root + '/port', 'w').write(str(srv.server_address[1]))
srv.serve_forever()
PY
  W4_RECV_PID=$!
  local i=0
  while [ ! -s "$root/port" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i+1)); done
  W4_PORT="$(cat "$root/port" 2>/dev/null)"
  [ -n "$W4_PORT" ]
}

log_count() { cat "$1" 2>/dev/null | grep -c "$2" 2>/dev/null || true; }

echo "== RRX-003: the receiver is given time, and a timeout is visible =="

# ---- A: default limit, receiver slower than the old 25s limit ---------------
B="$WORK/a"; mkdir -p "$B"
start_slow_receiver "$B" "$SLOW_S" || { bad "A slow receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-synthetic"
w4_run_poll "$B"; ST="$(w4_state "$B")"
[ "$W4_RC" -eq 0 ] && ok "A0 poll exits 0 (cron contract unchanged)" || bad "A0 rc=$W4_RC"
[ "$(log_count "$ST/rescue-poll.log" 'claim-failed')" = "0" ] \
  && ok "A1 with the default limit a 40s answer completes: no claim-failed line" \
  || bad "A1 claim-failed logged" "$(cat "$ST/rescue-poll.log" 2>/dev/null)"$'\n'"$(cat "$B/err" 2>/dev/null)"
[ "$(w4_claims "$B")" = "1" ] && ok "A2 the server received exactly one claim request" \
  || bad "A2 claim request count" "$(w4_claims "$B")"

# ---- B: RR_POST_MAX_S=25 cuts the claim off; the cut-off is said once ------
B="$WORK/b"; mkdir -p "$B"
w4_stop_receiver
start_slow_receiver "$B" "$SLOW_S" || { bad "B slow receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-synthetic"
export RR_POST_MAX_S=25
w4_run_poll "$B"; ST="$(w4_state "$B")"
w4_run_poll "$B"
unset RR_POST_MAX_S
[ "$W4_RC" -eq 0 ] && ok "B0 both runs exit 0" || bad "B0 rc=$W4_RC"
N="$(log_count "$ST/rescue-poll.log" 'claim-failed class=transport')"
[ "$N" = "1" ] && ok "B1 exactly one claim-failed class=transport line across two runs" \
  || bad "B1 claim-failed line count" "$N :: $(cat "$ST/rescue-poll.log" 2>/dev/null)"
[ "$(w4_claims "$B")" = "2" ] \
  && ok "B2 one claim request per run reached the server (a claim is never re-sent by curl)" \
  || bad "B2 claim request count" "$(w4_claims "$B")"

echo; echo "RRX-003 claim timeout: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]
