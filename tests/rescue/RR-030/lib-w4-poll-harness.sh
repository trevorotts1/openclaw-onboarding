#!/usr/bin/env bash
# tests/rescue/RR-030/lib-w4-poll-harness.sh   (RR plan wave 4 repo lane: F61 F62 F66)
#
# Shared harness: run the REAL 65-rescue-receiver/rescue-poll.sh against a loopback receiver
# stub and a stub `openclaw` that records every call. Sourced, never executed.
#
# HERMETIC BY CONSTRUCTION
#   * the receiver URL is 127.0.0.1 on a port this harness binds; nothing else is ever dialled
#   * HTTP(S)_PROXY point at a dead loopback port, so a stray call cannot leave the machine
#   * HOME is a temp dir; the token, slug and instruction ids are synthetic
#
# The caller sets REPO (repo root) and PASS/FAIL counters + ok()/bad().

W4_RECV_PID=""
W4_PORT=""
W4_RC=0
W4_POLL="$REPO/65-rescue-receiver/rescue-poll.sh"
W4_HELPER="$REPO/shared-utils/rescue-env.sh"
W4_SUPERVISE="$REPO/shared-utils/rescue-supervise.py"
for _f in "$W4_POLL" "$W4_HELPER" "$W4_SUPERVISE"; do
  [ -f "$_f" ] || { echo "FATAL: missing $_f"; exit 2; }
done
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required"; exit 2; }

w4_make_box() {  # <root> [slug]
  local root="$1" slug="${2:-box-synthetic}"
  mkdir -p "$root/.openclaw/skills/65-rescue-receiver" "$root/.openclaw/skills/shared-utils" \
           "$root/.openclaw/secrets" "$root/.openclaw/state/rr-receiver" "$root/bin"
  cp "$W4_POLL" "$root/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  cp "$REPO/65-rescue-receiver/rescue-notification.py" "$root/.openclaw/skills/65-rescue-receiver/"
  cp "$W4_HELPER" "$root/.openclaw/skills/shared-utils/rescue-env.sh"
  cp "$W4_SUPERVISE" "$root/.openclaw/skills/shared-utils/rescue-supervise.py"
  cat > "$root/bin/openclaw" <<'STUB'
#!/bin/bash
# one record line per call: the agent message is multi-line, so flatten newlines (argv itself is untouched)
{ printf 'CALL: %s\n' "$(printf '%s' "$*" | tr '\n' ' ')"; } >> "$OPENCLAW_RECORD"
if [ "$1" = "agents" ] && [ "$2" = "list" ]; then printf '%s\n' '[{"id":"main","isDefault":true}]'; exit 0; fi
if [ "$1" = "agent" ]; then printf '%s\n' '{"result":{"payloads":[{"text":"simulated reply text"}]}}'; exit 0; fi
printf '{}\n'; exit 0
STUB
  chmod +x "$root/bin/openclaw"
  printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/gw\nRR_BOX_TOKEN="synthetic-token-not-a-credential"\nRR_BOX_SLUG=%s\n' \
    "${W4_PORT:-1}" "$slug" > "$root/.openclaw/secrets/.env"
  chmod 600 "$root/.openclaw/secrets/.env"
}

# w4_start_receiver <root> <http-code> <response-json>  -> sets W4_PORT, W4_RECV_PID
# Binds an ephemeral loopback port; logs each request body to <root>/claims.log.
w4_start_receiver() {
  local root="$1" code="$2" resp="$3"
  rm -f "$root/port"
  python3 - "$root" "$code" "$resp" <<'PY' &
import http.server, sys
root, code, resp = sys.argv[1], int(sys.argv[2]), sys.argv[3]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0)); body = self.rfile.read(n)
        with open(root + '/claims.log', 'a') as fh: fh.write(body.decode('utf-8', 'replace') + "\n")
        out = resp.encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json')
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
w4_stop_receiver() {
  if [ -n "${W4_RECV_PID:-}" ]; then kill "$W4_RECV_PID" 2>/dev/null; wait "$W4_RECV_PID" 2>/dev/null; fi
  W4_RECV_PID=""; return 0
}

# w4_run_poll <root>   -> runs the installed copy once; rc in W4_RC
w4_run_poll() {
  local root="$1"
  OPENCLAW_RECORD="$root/agent-record.txt" HOME="$root" PATH="$root/bin:$PATH" RR_POLL_NO_JITTER=1 \
  HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 NO_PROXY=127.0.0.1,localhost \
    sh "$root/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" >"$root/out" 2>"$root/err"
  W4_RC=$?
}
w4_agent_calls() { local n; n=$(grep -c '^CALL: agent ' "$1" 2>/dev/null); case "$n" in ''|*[!0-9]*) n=0;; esac; echo "$n"; }
w4_claims() { local n; n=$(grep -c . "$1/claims.log" 2>/dev/null); case "$n" in ''|*[!0-9]*) n=0;; esac; echo "$n"; }
w4_state() { echo "$1/.openclaw/state/rr-receiver"; }
w4_b64() { printf '%s' "$1" | python3 -c 'import base64,sys; print(base64.b64encode(sys.stdin.buffer.read()).decode())'; }
