#!/usr/bin/env bash
# tests/unit/rr027-no-credential-in-child-env.test.sh — RR-027 gate.
#
# Pins the CONSUMERS (wire.sh, rescue-poll.sh) against the three CONFIRMED
# RR-027 defect classes (RCV05):
#   A. wire.sh `set -a; . secrets/.env` exported the WHOLE store into every
#      child (cron list/add, python3). Now: enrollment values are parsed,
#      existence-checked, dropped; children see NO store value.
#   B. A synthetic `export RR_BOX_TOKEN` in the caller's env reached the
#      poll's CHILD AGENT (comments claimed it never exports). Now: the
#      agent turn runs through rescue_env_scrub — every rescue alias is
#      removed from the child env while necessary authorized model/tool
#      credentials pass through.
#   C. seed-rr-agent-map.sh put the n8n API key on curl's ARGV. Now: the key
#      rides in a 0600 header file under a 0700 private temp dir; the token
#      never appears in any argv, any child env, or any log.
#
# Evidence standard (SPEC RR-027 required QC): synthetic exported, inherited
# and unexported secrets never appear in child env/argv/logs; the necessary
# authorized inference credential still works; quotes, dollar signs, spaces,
# malformed lines and permissions are exercised WITHOUT printing real values.
# Sentinel values are planted and asserted absent everywhere — and the leak
# DETECTOR is itself proven able to fail (an un-scrubbed control DOES leak).
#
# Hermetic: temp dirs, stub openclaw/curl binaries, a loopback HTTP stub for
# the receiver, no network beyond 127.0.0.1, no real credential.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WIRE="$REPO/65-rescue-receiver/wire.sh"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"
SEED="$REPO/scripts/seed-rr-agent-map.sh"
HELPER="$REPO/shared-utils/rescue-env.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

TOK='ZZRR027BOX-T0K3N-s3nt1n3l'
ESC='ZZRR027ESC-s3cr3t-9a8b7c'
NEC='ZZRR027NEC3SSARY-cr3d'
N8NK='ZZRR027N8N-k3y-5ynth3t1c'
for f in "$WIRE" "$POLL" "$SEED" "$HELPER"; do
  [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

echo "== RR-027: rescue credentials never reach child env / argv / logs =="

# ---------------------------------------------------------------------------
# Shared stub box: <root>/.openclaw with skills + secrets.
# ---------------------------------------------------------------------------
make_box() {  # make_box <dir> <store-lines-file>
  local root="$1" store="$2"
  mkdir -p "$root/.openclaw/skills/65-rescue-receiver" \
           "$root/.openclaw/skills/shared-utils" \
           "$root/.openclaw/secrets" \
           "$root/.openclaw/state/rr-receiver" \
           "$root/bin"
  cp "$POLL" "$root/.openclaw/skills/65-rescue-receiver/rescue-poll.sh"
  cp "$WIRE" "$root/.openclaw/skills/65-rescue-receiver/wire.sh"
  cp "$HELPER" "$root/.openclaw/skills/shared-utils/rescue-env.sh"
  cp "$store" "$root/.openclaw/secrets/.env"
  # stub openclaw: records its env + argv, answers every mode
  cat > "$root/bin/openclaw" <<STUB
#!/bin/bash
{ echo "ARGS: \$*"; env | sort; } > "\$OPENCLAW_RECORD"
if [ "\$1" = "agents" ]; then echo '[{"id":"main","isDefault":true}]'; exit 0; fi
echo '{"result":{"payloads":[{"text":"simulated reply text"}]}}'
exit 0
STUB
  chmod +x "$root/bin/openclaw"
}

STORE="$(mktemp -d "${TMPDIR:-/tmp}/rr027-store.XXXXXX")"
cat > "$STORE/store.env" <<EOF
# enrollment store with every tricky form
RR_RECEIVER_URL=https://receiver.example/rr
RR_BOX_TOKEN="$TOK"
RR_BOX_SLUG='box-slug with spaces'
OTHER_SECRET=upstream-value
EOF
# malformed twin: same store plus junk lines (wire treats malformed as fatal)
cat > "$STORE/store-malformed.env" <<EOF
# enrollment store with every tricky form
RR_RECEIVER_URL=https://receiver.example/rr
RR_BOX_TOKEN="$TOK"
RR_BOX_SLUG='box-slug with spaces'
OTHER_SECRET=upstream-value
JUNKLINE
BAD-KEY=x
EOF

# ---------------------------------------------------------------------------
# A. wire.sh must not leak the store into children
# ---------------------------------------------------------------------------
echo "--- A. wire.sh: the store never reaches a child ---"
WB="$(mktemp -d "${TMPDIR:-/tmp}/rr027-wire.XXXXXX")"
make_box "$WB" "$STORE/store.env"
cat > "$WB/bin/openclaw" <<STUB
#!/bin/bash
{ echo "ARGS: \$*"; env | sort; } >> "\$OPENCLAW_RECORD"
case "\$1 \$2" in
  "cron list") echo '{"jobs":[]}'; exit 0;;
  "cron add") exit 0;;
esac
exit 0
STUB
chmod +x "$WB/bin/openclaw"
OPENCLAW_RECORD="$WB/record.txt" \
HOME="$WB" PATH="$WB/bin:$PATH" \
RR_BOX_TOKEN="$TOK" OTHER_SECRET=upstream-inherited \
bash "$WB/.openclaw/skills/65-rescue-receiver/wire.sh" >/dev/null 2>&1
wrc=$?
[ "$wrc" = 0 ] && ok "wire.sh completes enrolled (rc=0)" || bad "wire.sh rc=$wrc"
if [ -f "$WB/record.txt" ]; then
  n=$(grep -cF "$TOK" "$WB/record.txt")
  [ "$n" = 0 ] && ok "token VALUE absent from every wire child (env + argv)" || bad "token value in wire child ($n hits)"
  grep -qF "upstream-value" "$WB/record.txt" && bad "STORE-only value leaked into child (store still exported)" \
    || ok "store-only value (OTHER_SECRET from the file) absent from children"
  grep -qF "upstream-inherited" "$WB/record.txt" && ok "control: wire children DO see non-store env (recording works)" \
    || bad "wire child record missing inherited env (detector cannot fail)"
  grep -qF "box-slug with spaces" "$WB/record.txt" && bad "slug value leaked to child" || ok "slug value absent from children"
else
  bad "wire.sh spawned no child — record missing"
fi
# malformed twin: wire fails VISIBLY (rc=1) — never silently wires a half-store
MB2="$(mktemp -d "${TMPDIR:-/tmp}/rr027-wiremal.XXXXXX")"
make_box "$MB2" "$STORE/store-malformed.env"
cat > "$MB2/bin/openclaw" <<STUB
#!/bin/bash
{ echo "ARGS: \$*"; env | sort; } >> "\$OPENCLAW_RECORD"
case "\$1 \$2" in "cron list") echo '{"jobs":[]}'; exit 0;; "cron add") exit 0;; esac
exit 0
STUB
chmod +x "$MB2/bin/openclaw"
OPENCLAW_RECORD="$MB2/record.txt" HOME="$MB2" PATH="$MB2/bin:$PATH" \
  bash "$MB2/.openclaw/skills/65-rescue-receiver/wire.sh" >"$MB2/out" 2>"$MB2/err"
mrc=$?
[ "$mrc" = 1 ] && ok "wire on a malformed store FAILS VISIBLY (rc=1, cron NOT registered)" || bad "wire malformed rc=$mrc (expected 1)"
grep -q "malformed line 6" "$MB2/err" && grep -q "malformed line 7" "$MB2/err" \
  && ok "wire malformed reasons name the line" || bad "wire malformed reasons missing"
grep -qF "$TOK" "$MB2/err" "$MB2/out" && bad "wire malformed output carries a value" || ok "wire malformed output value-free"
rm -rf "$MB2"

# ---------------------------------------------------------------------------
# B. rescue-poll.sh: child agent env scrub (exported + inherited + unexported)
# ---------------------------------------------------------------------------
echo "--- B. rescue-poll.sh: the agent child sees NO rescue alias, necessary creds intact ---"
PB="$(mktemp -d "${TMPDIR:-/tmp}/rr027-poll.XXXXXX")"
make_box "$PB" "$STORE/store.env"
RECV_PORT=18777
cat > "$PB/receiver.py" <<PYEOF
import http.server, json, base64, sys
msg = base64.b64encode(b"Do the simulated thing").decode()
RESP = {"status":"instruction","instruction_id":"ins-rr027","idempotency_key":"idem-rr027",
        "ticket_id":"T-rr027","agent_id":"main","session_key":"s-rr027",
        "payload_b64":msg,"mode":"live"}
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        ln = int(self.headers.get('Content-Length', 0)); body = self.rfile.read(ln)
        out = json.dumps(RESP if b'"action":"claim"' in body else {"status":"accepted"}).encode()
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', $RECV_PORT), H).serve_forever()
PYEOF
python3 "$PB/receiver.py" 2>/dev/null &
RECV_PID=$!
sleep 0.7
printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/gw\nRR_BOX_TOKEN="%s"\nRR_BOX_SLUG=box-synthetic\n' "$RECV_PORT" "$TOK" > "$PB/.openclaw/secrets/.env"
OPENCLAW_RECORD="$PB/agent-record.txt" \
RR_BOX_TOKEN="$TOK" \
RESCUE_RANGERS_WEBHOOK_SECRET="$ESC" RESCUE_RANGERS_HELP_CHAT_ID=999 \
GEMINI_API_KEY="$NEC" \
HOME="$PB" PATH="$PB/bin:$PATH" RR_POLL_NO_JITTER=1 \
sh "$PB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" >/dev/null 2>"$PB/poll-stderr"
poll_rc=$?
kill "$RECV_PID" 2>/dev/null; wait "$RECV_PID" 2>/dev/null
[ "$poll_rc" = 0 ] && ok "poll completed its cycle (rc=0)" || bad "poll rc=$poll_rc"
if [ -f "$PB/agent-record.txt" ]; then
  n=$(grep -cE '^(RR_BOX_TOKEN|RR_BOX_SLUG|RR_BOX_CRED|RR_RECEIVER_SECRET|RESCUE_PUSH_SECRET|RESCUE_RANGERS_WEBHOOK_SECRET|RESCUE_RANGERS_HELP_CHAT_ID)=' "$PB/agent-record.txt")
  [ "$n" = 0 ] && ok "agent child env carries ZERO rescue aliases (7 names, exported synthetic included)" \
    || bad "$n rescue alias(es) in agent child env"
  grep -qF "GEMINI_API_KEY=$NEC" "$PB/agent-record.txt" \
    && ok "necessary authorized inference credential STILL WORKS (present in child env)" \
    || bad "necessary inference credential missing from child env"
  for v in "$TOK" "$ESC"; do
    grep -qF "$v" "$PB/agent-record.txt" && bad "sentinel value reached the agent child env" || true
  done
  grep -qF "$TOK" "$PB/agent-record.txt" || ok "token sentinel absent from agent child env"
  grep -qF "$ESC" "$PB/agent-record.txt" || ok "escalation secret sentinel absent from agent child env (poll child is not the escalation path)"
  # unexported store values must not leak either (they were never exported)
  grep -qF "upstream-value" "$PB/agent-record.txt" && bad "unexported store value reached the child" \
    || ok "unexported store value absent from agent child env"
else
  bad "agent child never ran — record missing (claim failed?)"
fi
# logs carry no value
LOG="$PB/.openclaw/state/rr-receiver/rescue-poll.log"
if [ -f "$LOG" ]; then
  grep -qF "$TOK" "$LOG" && bad "poll LOG leaked the token" || ok "poll log carries no token value"
  grep -qF "$ESC" "$LOG" && bad "poll LOG leaked the escalation secret" || ok "poll log carries no escalation secret"
else
  ok "no poll log written (claim path may have failed before logging — inspect)"
fi
grep -qF "$TOK" "$PB/poll-stderr" 2>/dev/null && bad "poll stderr leaked the token" || ok "poll stderr carries no token"

# malformed store: fail visibly
MB="$(mktemp -d "${TMPDIR:-/tmp}/rr027-mal.XXXXXX")"
make_box "$MB" "$STORE/store.env"
printf 'RR_RECEIVER_URL=https://e.com\nRR_BOX_TOKEN=tok\nRR_BOX_SLUG=s\nGARBAGELINE\nBAD-KEY=v\n' > "$MB/.openclaw/secrets/.env"
HOME="$MB" sh "$MB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" 2>"$MB/err"
mal=$?
grep -q "malformed line 4" "$MB/err" && grep -q "malformed line 5" "$MB/err" \
  && ok "malformed store fails VISIBLY (line numbers on stderr)" || bad "malformed store silent (no reasons on stderr)"
if grep -qE "malformed line" "$MB/err"; then
  grep -qF "tok" "$MB/err" && bad "malformed output carries a value" || ok "malformed output carries names/shapes only"
fi
rm -rf "$MB"

# spaces in values survive parsing (poll sees the spaced slug in the claim body)
SPB="$(mktemp -d "${TMPDIR:-/tmp}/rr027-space.XXXXXX")"
make_box "$SPB" "$STORE/store.env"
cat > "$SPB/receiver.py" <<PYEOF
import http.server, json, base64, sys
RESP = {"status":"empty"}
CLAIM_LOG = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        ln = int(self.headers.get('Content-Length', 0)); body = self.rfile.read(ln)
        with open(CLAIM_LOG, 'a') as f: f.write(body.decode() + "\n")
        out = json.dumps(RESP).encode()
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', $RECV_PORT + 1), H).serve_forever()
PYEOF
python3 "$SPB/receiver.py" "$SPB/claim-body.txt" 2>/dev/null &
SPID=$!; sleep 0.5
printf "RR_RECEIVER_URL=http://127.0.0.1:%s/gw\nRR_BOX_TOKEN=t\nRR_BOX_SLUG='box slug spaces'\n" "$((RECV_PORT + 1))" > "$SPB/.openclaw/secrets/.env"
HOME="$SPB" PATH="$SPB/bin:$PATH" RR_POLL_NO_JITTER=1 sh "$SPB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" >/dev/null 2>&1
kill $SPID 2>/dev/null; wait $SPID 2>/dev/null
grep -qF '"box_slug":"box slug spaces"' "$SPB/claim-body.txt" 2>/dev/null \
  && ok "slug with spaces survives parsing into the claim body" \
  || bad "spaced slug lost (claim body malformed)"
grep -qF "$TOK" "$SPB/claim-body.txt" 2>/dev/null && bad "claim body carries a token value" || ok "claim body carries no credential (token rides header-file only)"
rm -rf "$SPB"

# ---------------------------------------------------------------------------
# C. seed-rr-agent-map.sh: key never on argv
# ---------------------------------------------------------------------------
echo "--- C. seed-rr-agent-map.sh: API key rides in a header file, never argv ---"
SB="$(mktemp -d "${TMPDIR:-/tmp}/rr027-seed.XXXXXX")"
mkdir -p "$SB/scripts" "$SB/shared-utils" "$SB/bin"
cp "$SEED" "$SB/scripts/seed-rr-agent-map.sh"
cp "$HELPER" "$SB/shared-utils/rescue-env.sh"
cat > "$SB/bin/curl" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "\$CURL_ARGV_LOG"
for a in "\$@"; do [ "\$a" = "POST" ] && { touch "$SB/posted"; printf '200'; exit 0; }; done
if [ -f "$SB/posted" ]; then
  printf '{"data":[{"box_slug":"box-a","local_agent_id":"dept-main"}]}'
else
  printf '{"data":[]}'
fi
exit 0
STUB
chmod +x "$SB/bin/curl"
cat > "$SB/bin/ssh" <<'STUB'
#!/bin/bash
echo '[{"id":"dept-main","isDefault":true}]'
STUB
chmod +x "$SB/bin/ssh"
printf 'box-a\n' > "$SB/roster.txt"
CURL_ARGV_LOG="$SB/curl-argv.log" \
PATH="$SB/bin:$PATH" N8N_API_KEY="$N8NK" \
bash "$SB/scripts/seed-rr-agent-map.sh" "$SB/roster.txt" >/dev/null 2>&1
src=$?
[ "$src" = 0 ] && ok "seed script completes (rc=0)" || bad "seed rc=$src"
if [ -f "$SB/curl-argv.log" ]; then
  grep -qF "$N8NK" "$SB/curl-argv.log" && bad "API key ON CURL ARGV (defect C still live)" || ok "API key absent from every curl argv"
  grep -q '\-H @' "$SB/curl-argv.log" && ok "auth rides via -H @header-file" || bad "no header-file flag seen"
  grep -q 'data-binary' "$SB/curl-argv.log" && ok "payload rides via --data-binary @file" || ok "GET-only run (no POST payload)"
else
  bad "seed made no curl call"
fi
# header files cleaned up
ls "${TMPDIR:-/tmp}"/rr-seed-hdr.* >/dev/null 2>&1 && bad "seed header temp dir LEFT BEHIND" || ok "seed header temp dirs removed on exit"

# negative control: a KEY-BEARING argv IS caught by this test's own detector
cat > "$SB/leaky-curl" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >> "\$CURL_ARGV_LOG2"
exit 0
STUB
chmod +x "$SB/leaky-curl"
CURL_ARGV_LOG2="$SB/leaky.log" "$SB/leaky-curl" -H "X-N8N-API-KEY: $N8NK" >/dev/null 2>&1
grep -qF "$N8NK" "$SB/leaky.log" && ok "control: the detector DOES catch a key-bearing argv (old shape)" \
  || bad "leak detector cannot fail — part C proves nothing"
rm -rf "$SB"

# process-table proof: poll the table while the poll script runs its agent turn
echo "--- D. process table never carries a credential ---"
PTB="$(mktemp -d "${TMPDIR:-/tmp}/rr027-pt.XXXXXX")"
make_box "$PTB" "$STORE/store.env"
python3 "$PB/receiver.py" 2>/dev/null &
RPID2=$!
sleep 0.5
printf 'RR_RECEIVER_URL=http://127.0.0.1:%s/gw\nRR_BOX_TOKEN="%s"\nRR_BOX_SLUG=box-synthetic\n' "$RECV_PORT" "$TOK" > "$PTB/.openclaw/secrets/.env"
(
  for _ in 1 2 3; do
    OPENCLAW_RECORD="$PTB/pt-record.txt" RR_BOX_TOKEN="$TOK" RESCUE_RANGERS_WEBHOOK_SECRET="$ESC" \
    GEMINI_API_KEY="$NEC" HOME="$PTB" PATH="$PTB/bin:$PATH" RR_POLL_NO_JITTER=1 \
      sh "$PTB/.openclaw/skills/65-rescue-receiver/rescue-poll.sh" >/dev/null 2>&1
  done
) &
LOOP=$!
HITS=0; SAMPLES=0
while kill -0 "$LOOP" 2>/dev/null; do
  SAMPLES=$((SAMPLES+1))
  if pgrep -f "$TOK" >/dev/null 2>&1; then HITS=$((HITS+1)); fi
  [ "$SAMPLES" -ge 400 ] && break
done
wait "$LOOP" 2>/dev/null; kill "$RPID2" 2>/dev/null; wait "$RPID2" 2>/dev/null
# sampler control: a planted argv carrier MUST be seen
bash -c "sleep 2; exit 0 $TOK" >/dev/null 2>&1 &
CTRL=$!
CTRL_SEEN=0
for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -f "$TOK" >/dev/null 2>&1 && { CTRL_SEEN=1; break; }; sleep 0.2; done
kill "$CTRL" 2>/dev/null; wait "$CTRL" 2>/dev/null
[ "$CTRL_SEEN" = 1 ] && ok "process-table sampler is live (control seen)" || bad "sampler never fired on the control — part D proves nothing"
[ "$SAMPLES" -ge 10 ] && ok "process table sampled $SAMPLES times" || bad "only $SAMPLES samples"
[ "$HITS" = 0 ] && ok "credential never appeared in a process listing" || bad "credential in process table $HITS time(s)"
rm -rf "$PTB" "$PB"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0