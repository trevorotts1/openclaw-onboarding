#!/usr/bin/env bash
# tests/unit/fleet-standing-gate.test.sh
#
# Proves the FLEET-STANDING-GATE-V1 block in update-skills.sh behaves correctly.
#
# The single most important property under test is FAIL OPEN: only an explicit
# "blocked" verdict may stop an update. Everything else -- unreachable gate,
# HTTP 500, garbage body, missing config, unknown box -- must proceed. A
# regression to fail-closed would freeze updates fleet-wide the moment n8n
# hiccups, so these tests exist to make that regression impossible to merge.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; [ -n "${SRV_PID:-}" ] && kill "$SRV_PID" 2>/dev/null' EXIT

ok()   { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

# --- extract just the gate block so we can exercise it in isolation ---
GATE="$TMP/gate.sh"
awk '/^#=== BEGIN FLEET-STANDING-GATE-V1 ===$/,/^#=== END FLEET-STANDING-GATE-V1 ===$/' "$SRC" \
  | grep -v '^fleet_standing_gate$' > "$GATE"

if [ ! -s "$GATE" ]; then
  echo "FAIL: could not extract FLEET-STANDING-GATE-V1 block from $SRC"; exit 1
fi
bash -n "$GATE" || { echo "FAIL: extracted gate block is not valid bash"; exit 1; }

# --- a tiny stub gate server whose reply we control per-test ---
REPLY_FILE="$TMP/reply.json"
CODE_FILE="$TMP/code.txt"
echo '{"ok":true,"good_standing":true,"verdict":"allowed","reason":"","client_message":""}' > "$REPLY_FILE"
echo 200 > "$CODE_FILE"

python3 - "$TMP" <<'PY' &
import http.server, sys, os
tmp = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        code = int(open(os.path.join(tmp, "code.txt")).read().strip())
        body = open(os.path.join(tmp, "reply.json"), "rb").read()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 8791), H)
open(os.path.join(tmp, "port.txt"), "w").write("8791")
srv.serve_forever()
PY
SRV_PID=$!
sleep 1.5

URL="http://127.0.0.1:8791/gate"

# run the gate in a subshell; capture output + exit code
run_gate() {
  ( set -euo pipefail
    OC_CONFIG="$TMP/oc"; OC_JSON="$TMP/oc/openclaw.json"
    mkdir -p "$OC_CONFIG"; : > "$OC_CONFIG/AGENTS.md"
    # shellcheck source=/dev/null
    source "$GATE"
    fleet_standing_gate
    echo "__REACHED_END__"
  ) 2>&1
}

set_reply() { printf '%s' "$1" > "$REPLY_FILE"; printf '%s' "${2:-200}" > "$CODE_FILE"; }

echo "== FAIL-OPEN cases (must all proceed) =="

# 1. no config at all
out="$(FLEET_STANDING_GATE_URL="" FLEET_STANDING_GATE_SECRET="" FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "unconfigured box proceeds" || bad "unconfigured box should proceed: $out"

# 2. gate unreachable (dead port)
out="$(FLEET_STANDING_GATE_URL="http://127.0.0.1:9/gate" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "unreachable gate proceeds" || bad "unreachable gate should proceed: $out"

# 3. HTTP 500
set_reply '{"verdict":"blocked"}' 500
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "HTTP 500 proceeds (even with blocked body)" || bad "HTTP 500 should proceed: $out"

# 4. garbage body
set_reply 'not json at all' 200
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "garbage body proceeds" || bad "garbage body should proceed: $out"

# 5. empty body
set_reply '' 200
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "empty body proceeds" || bad "empty body should proceed: $out"

# 6. verdict unmatched
set_reply '{"ok":false,"good_standing":false,"verdict":"unmatched","reason":"no_record_found"}' 200
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "verdict=unmatched proceeds" || bad "unmatched should proceed: $out"

# 7. verdict held
set_reply '{"ok":false,"good_standing":false,"verdict":"held","reason":"lookup_error"}' 200
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "verdict=held proceeds" || bad "held should proceed: $out"

# 8. verdict allowed
set_reply '{"ok":true,"good_standing":true,"verdict":"allowed","reason":""}' 200
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "verdict=allowed proceeds" || bad "allowed should proceed: $out"

echo "== BLOCK case (the only stop) =="

# 9. verdict blocked -> must NOT reach end
set_reply '{"ok":false,"good_standing":false,"verdict":"blocked","reason":"good_standing_is_false","client_message":"..."}' 200
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" != *"__REACHED_END__"* ]] && ok "verdict=blocked STOPS the update" || bad "blocked must stop the update: $out"
[[ "$out" == *"not current on payments"* ]] && ok "blocked prints the polite message" || bad "blocked should print polite message"

echo "== escape hatches =="

# 10. bypass
out="$(FLEET_STANDING_GATE_BYPASS=1 FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "BYPASS=1 proceeds even when blocked" || bad "bypass should proceed: $out"

# 11. shadow mode
out="$(FLEET_STANDING_GATE_SHADOW=1 FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET=s FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "SHADOW=1 proceeds" || bad "shadow should proceed: $out"
[[ "$out" == *"would have BLOCKED"* ]] && ok "SHADOW=1 reports what it would have done" || bad "shadow should report"

echo "== secret hygiene =="

# 12. the secret must never appear in output
out="$(FLEET_STANDING_GATE_URL="$URL" FLEET_STANDING_GATE_SECRET="SUPERSECRETVALUE123" FLEET_STANDING_BOX_SLUG=b1 run_gate)"
[[ "$out" != *"SUPERSECRETVALUE123"* ]] && ok "secret never printed" || bad "SECRET LEAKED IN OUTPUT"

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
