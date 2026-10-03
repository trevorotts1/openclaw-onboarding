#!/usr/bin/env bash
# tests/rescue/RR-030/test_alarm_senders.sh   (RR plan fix F50)
# Three repo alarms used to post client=$(hostname) with no boxName, which RR-01
# answers 400 "unresolvable box" -- and `curl -s ... || true` hid it:
#   scripts/disk-usage-alert.sh
#   scripts/pre-july14-embedding-migration-check.sh
#   06-ghl-install-pages/tools/browser_manager.sh   (circuit-breaker trip)
# Each is forced down its alert path under an isolated HOME/TMPDIR, with
# RESCUE_RANGERS_WEBHOOK_URL pointed at a LOOPBACK stub (127.0.0.1) started here.
# Nothing here can reach a real webhook: every run is `env -i` with only the stub URL.
#   - FLEET_STANDING_BOX_SLUG=test-box  -> body carries boxName test-box, never the hostname
#   - FLEET_STANDING_CLIENT_LABEL unset -> clientName falls back to the slug
#   - slug unset                        -> NO post, a WARN is logged
#   - stub answers 400                  -> a WARN is logged (no longer silent)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }
PY="$(command -v python3)" || { echo "FATAL: python3 missing"; exit 2; }
W="$(mktemp -d "${TMPDIR:-/tmp}/rr030-alarm-XXXXXX")"
SRV_PID=""
cleanup() { [ -n "$SRV_PID" ] && kill "$SRV_PID" 2>/dev/null; rm -rf "$W"; }
trap cleanup EXIT

# --- loopback stub: records every POST body + the X-Rescue-Secret presence, answers $W/status ---
cat > "$W/stub.py" <<'PYSTUB'
import http.server, json, os, sys
W = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")
        with open(os.path.join(W, "posts.log"), "a") as fh:
            fh.write(json.dumps({"body": body, "has_secret": "X-Rescue-Secret" in self.headers}) + "\n")
        try:
            code = int(open(os.path.join(W, "status")).read().strip())
        except Exception:
            code = 200
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b'{"status":"stub"}')
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
open(os.path.join(W, "port"), "w").write(str(srv.server_address[1]))
srv.serve_forever()
PYSTUB
"$PY" "$W/stub.py" "$W" & SRV_PID=$!
for _ in $(seq 1 50); do [ -s "$W/port" ] && break; sleep 0.1; done
[ -s "$W/port" ] || { echo "FATAL: stub did not start"; exit 2; }
URL="http://127.0.0.1:$(cat "$W/port")/stub"
case "$URL" in http://127.0.0.1:*) ;; *) echo "FATAL: URL is not loopback"; exit 2;; esac
echo 200 > "$W/status"

posts() { [ -f "$W/posts.log" ] && wc -l < "$W/posts.log" | tr -d ' ' || echo 0; }
field() { "$PY" - "$W/posts.log" "$1" <<'PYF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print(json.loads(rows[-1]["body"]).get(sys.argv[2], "<missing>"))
PYF
}
fresh_home() { rm -rf "$W/home" "$W/tmp" "$W/posts.log"; mkdir -p "$W/home/.openclaw" "$W/tmp"; }
# run <script-runner...> with a minimal env; $SLUG (may be empty) controls the slug
base_env() {
  local e=(HOME="$W/home" TMPDIR="$W/tmp" PATH="/usr/bin:/bin:/usr/sbin:/sbin:$(dirname "$PY")"
           RESCUE_RANGERS_WEBHOOK_URL="$URL" RESCUE_RANGERS_WEBHOOK_SECRET="synthetic-secret-123")
  [ -n "${SLUG:-}" ] && e+=(FLEET_STANDING_BOX_SLUG="$SLUG")
  [ -n "${LABEL:-}" ] && e+=(FLEET_STANDING_CLIENT_LABEL="$LABEL")
  printf '%s\0' "${e[@]}"
}
run_env() { local arr=(); while IFS= read -r -d '' x; do arr+=("$x"); done < <(base_env); env -i "${arr[@]}" "$@"; }

HOSTNAME_NOW="$(hostname 2>/dev/null || echo box)"

# ---- the three triggers --------------------------------------------------------------------
t_disk()   { run_env OC_DISK_THRESHOLD=0 OC_DISK_ESCALATE=1 bash "$REPO/scripts/disk-usage-alert.sh" >"$W/out" 2>&1; }
t_embed()  { printf '%s' '{"agents":{"defaults":{"memorySearch":{"model":"gemini-embedding-001"}}}}' > "$W/home/.openclaw/openclaw.json"
             run_env OC_MIGRATE_ESCALATE=1 bash "$REPO/scripts/pre-july14-embedding-migration-check.sh" >"$W/out" 2>&1; }
t_breaker() { run_env BM_DURABLE_ROOT_OVERRIDE= GHL_LOCATION_ID=test-loc AB_BREAKER_MAX=2 AB_BREAKER_WINDOW=7200 \
                bash -c '
                  source "$1/06-ghl-install-pages/tools/browser_manager.sh" || exit 90
                  now=$(date -u +%s); printf "%s\n%s\n" "$now" "$now" > "$(_bm_breaker_file)"
                  bm_breaker_check' _ "$REPO" >"$W/out" 2>&1; }

for name in disk embed breaker; do
  echo "== $name alarm =="
  # 1. slug set -> boxName = slug, clientName falls back to the slug, secret header sent, no hostname
  fresh_home; echo 200 > "$W/status"; SLUG="test-box"; "t_$name"
  [ "$(posts)" = 1 ] && ok "$name: posts exactly once" || bad "$name: expected 1 post, got $(posts) ($(tail -2 "$W/out" | tr '\n' ' '))"
  if [ "$(posts)" -ge 1 ]; then
    [ "$(field boxName)" = "test-box" ]    && ok "$name: boxName == test-box"             || bad "$name: boxName == '$(field boxName)'"
    [ "$(field clientName)" = "test-box" ] && ok "$name: clientName falls back to slug"    || bad "$name: clientName == '$(field clientName)'"
    [ "$(field action)" = "escalate" ]     && ok "$name: action == escalate"               || bad "$name: action == '$(field action)'"
    [ "$(field client)" = "<missing>" ]    && ok "$name: no hostname-valued 'client' field" || bad "$name: legacy client field still sent"
    case "$(field boxName)|$(field clientName)" in *"$HOSTNAME_NOW"*) bad "$name: hostname used as an identity field";; *) ok "$name: hostname is not used as boxName/clientName";; esac
    grep -q '"has_secret": true' "$W/posts.log" && ok "$name: X-Rescue-Secret header sent" || bad "$name: secret header missing"
  fi
  # 2. explicit client label wins
  fresh_home; SLUG="test-box"; LABEL="Test Client"; "t_$name"; LABEL=""
  [ "$(posts)" -ge 1 ] && [ "$(field clientName)" = "Test Client" ] && ok "$name: FLEET_STANDING_CLIENT_LABEL becomes clientName" || bad "$name: label not used"
  # 3. slug unset -> no post, WARN logged
  fresh_home; SLUG=""; "t_$name"
  [ "$(posts)" = 0 ] && ok "$name: slug unset -> nothing posted" || bad "$name: posted with no slug"
  grep -q 'WARN.*FLEET_STANDING_BOX_SLUG' "$W/out" && ok "$name: slug unset -> WARN logged" || bad "$name: no WARN for missing slug ($(tail -3 "$W/out" | tr '\n' ' '))"
  # 4. intake rejects (400) -> a WARN, not silence
  fresh_home; echo 400 > "$W/status"; SLUG="test-box"; "t_$name"
  grep -q 'WARN.*HTTP 400' "$W/out" && ok "$name: HTTP 400 -> WARN names the status" || bad "$name: 400 was silent ($(tail -3 "$W/out" | tr '\n' ' '))"
  echo 200 > "$W/status"
done

echo; echo "RR-030 alarm senders: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
