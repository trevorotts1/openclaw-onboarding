#!/usr/bin/env bash
# tests/rescue/RR-025/lib-envelope-harness.sh
#
# Shared harness for the RR-025 gate: run the REAL rescue-poll.sh against a
# loopback receiver stub and record EVERY agent invocation it makes.
#
# Why a real run and not a unit test of _parse_claim alone: the SPEC's required
# QC is "invalid input makes ZERO agent calls". Whether a turn ran is a fact
# about the box, not about a shell function's return code — so the evidence has
# to come from a stub `openclaw` binary that logs every call it receives. The
# negative assertion ("no agent call") is then falsifiable: the same recorder is
# proven to FIRE on a legitimate claim (the positive control), so a silent log
# means the poll refused, not that the recorder was broken.
#
# Sourced by the RR-025 gate; defines harness_run_case.
set -u

harness_make_box() {  # <root> [slug]
    local root="$1" slug="${2:-box-synthetic}"
    mkdir -p "$root/.openclaw/skills/65-rescue-receiver" \
             "$root/.openclaw/skills/shared-utils" \
             "$root/.openclaw/secrets" \
             "$root/.openclaw/state/rr-receiver" \
             "$root/bin"
    cp "$POLL" "$root/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
    cp "$HELPER" "$root/.openclaw/skills/shared-utils/rescue-env.sh"
    cp "$SUPERVISE" "$root/.openclaw/skills/shared-utils/rescue-supervise.py"
    # Stub openclaw. RECORDS EVERY CALL: one line per invocation, plus the env
    # of the agent turn. `agents list --json` answers a roster so the RR-025
    # capability check has something truthful to resolve against.
    cat > "$root/bin/openclaw" <<'STUB'
#!/bin/bash
{ printf 'CALL: %s\n' "$*"; env | sort; } >> "$OPENCLAW_RECORD"
# NOTE: no `${VAR:-{...}}` default here — the first `}` inside a brace-bearing
# default closes the parameter expansion and silently truncates the value,
# which made every roster read look like garbage JSON.
if [ "$1" = "agents" ]; then
  case "$2" in
    list)
      if [ -n "${STUB_ROSTER:-}" ]; then printf '%s\n' "$STUB_ROSTER"
      else printf '%s\n' '[{"id":"main","isDefault":true}]'
      fi
      exit 0;;
  esac
fi
if [ "$1" = "agent" ]; then
  if [ -n "${STUB_AGENT_OUT:-}" ]; then printf '%s\n' "$STUB_AGENT_OUT"
  else printf '%s\n' '{"result":{"payloads":[{"text":"simulated reply text"}]}}'
  fi
  if [ -n "${STUB_AGENT_RC:-}" ]; then exit "$STUB_AGENT_RC"; fi
  exit 0
fi
printf '{}\n'
exit 0
STUB
    chmod +x "$root/bin/openclaw"
    : > "$root/.openclaw/state/rr-receiver/.keep"
}

harness_write_store() {  # <root> <port> [slug]
    local root="$1" port="$2" slug="${3:-box-synthetic}"
    printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/gw\nRR_BOX_TOKEN="synthetic-token-not-a-credential"\nRR_BOX_SLUG=%s\n' \
        "$port" "$slug" > "$root/.openclaw/secrets/.env"
    chmod 600 "$root/.openclaw/secrets/.env"
}

harness_start_receiver() {  # <port> <response-json> <claim-log>
    python3 - "$1" "$2" "$3" <<'PY' &
import http.server, json, sys
port, resp, log = int(sys.argv[1]), sys.argv[2], sys.argv[3]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        with open(log, 'a') as fh:
            fh.write(body.decode('utf-8', 'replace') + "\n")
        out = resp.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)
    def log_message(self, *a):
        pass
http.server.HTTPServer(('127.0.0.1', port), H).serve_forever()
PY
    echo $!
}

harness_agent_calls() {  # <record-file> -> count of agent-turn invocations
    # Count only the TURN form ('agent --agent ...'), never the roster probe.
    # The bare `grep -c || echo 0` form double-prints ("0\n0") because a
    # zero-match grep still writes its own 0 AND exits 1 — which then trips
    # every `[ "$N" -eq 0 ]` with "integer expected".
    if [ ! -f "$1" ]; then echo 0; return 0; fi
    local n
    n=$(grep -c '^CALL: .*agent --agent' "$1" 2>/dev/null)
    case "$n" in ''|*[!0-9]*) n=0 ;; esac
    echo "$n"
}
