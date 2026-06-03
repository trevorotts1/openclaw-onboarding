#!/usr/bin/env bash
# lib-harness.sh -- Skill 41 v1.3.0 browser-execution harness shared library.
#
# This file is SOURCED by every L1-L5 level script and by 12-run-browser-harness.sh.
# It carries ZERO side effects on source: it only defines functions + sets a couple of
# read-only path variables. No level logic runs here.
#
# Design rules (match the existing skill scripts):
#   * `set -uo pipefail` discipline is the CALLER's job; this lib never relies on -e.
#   * Platform-aware via `uname -s` (Darwin -> Mac/~ , Linux -> VPS//data) like
#     references/platform-differences.md + lib-master-files.sh.
#   * SAFE: never makes a live external call, never reads/writes a real credential.
#     L1/L2 talk only to a LOCAL loopback mock GHL server this lib can spawn.
#   * Deterministic + offline: a run on a laptop with no network must behave identically
#     to a run on a Mac mini or a VPS container.

# --- platform detection -------------------------------------------------------
hf_os() { uname -s; }

# OpenClaw home (Mac ~/.openclaw vs VPS /data/.openclaw) -- matches the fleet convention.
hf_openclaw_home() {
  if [[ "$(uname -s)" == "Darwin" ]]; then echo "$HOME/.openclaw"; else echo "/data/.openclaw"; fi
}

# The service user the harness should *document* writing config as (VPS = node).
hf_service_user() {
  if [[ "$(uname -s)" == "Darwin" ]]; then echo "$(id -un)"; else echo "node"; fi
}

# python3 availability (Darwin uses it for the session_ref + the mock server). On a VPS the
# image ships python3; we degrade gracefully if it is genuinely absent.
hf_have_python3() { command -v python3 >/dev/null 2>&1; }

# --- logging ------------------------------------------------------------------
# Every line is prefixed so the runner can grep PASS/FAIL/ESCALATED per level.
hf_log()  { printf '%s\n' "[$HF_LEVEL] $*"; }
hf_pass() { printf '%s\n' "[$HF_LEVEL] PASS: $*"; }
hf_fail() { printf '%s\n' "[$HF_LEVEL] FAIL: $*" >&2; }
hf_info() { printf '%s\n' "[$HF_LEVEL]   - $*"; }

# A check helper: hf_check "<description>" <condition-cmd...>
# Increments HF_CHECKS / HF_FAILS. Returns the condition's status.
hf_check() {
  local desc="$1"; shift
  HF_CHECKS=$((HF_CHECKS + 1))
  if "$@"; then
    hf_info "ok  - $desc"
    return 0
  else
    hf_info "BAD - $desc"
    HF_FAILS=$((HF_FAILS + 1))
    return 1
  fi
}

# --- isolated sandbox ---------------------------------------------------------
# Each level runs in its own throwaway dir so nothing touches a real master-files dir
# or a real ~/.openclaw. The level scripts export MASTER_FILES_DIR to this sandbox so
# any append_jsonl from skill code lands here, never in production.
hf_make_sandbox() {
  local d
  d="$(mktemp -d 2>/dev/null || mktemp -d -t hf41)"
  echo "$d"
}

# --- mock GHL server (LOCAL loopback only -- never the real services.leadconnectorhq.com)
# hf_spawn_mock starts a tiny python3 HTTP server on 127.0.0.1:<port> that mimics the three
# GHL create/list endpoints just enough for L1/L2 to prove the auth+build flow without a
# real account. SAFE: it binds loopback only, requires a FAKE Bearer token, and records
# every request (method/path/auth-present, NEVER the token value) to mock-requests.log so
# L4 can prove PII-free logging and L2 can prove the build sequence executed.
HF_MOCK_PORT=""
HF_MOCK_PID=""
HF_MOCK_TOKEN=""
HF_MOCK_REQLOG=""
hf_spawn_mock() {
  local sandbox="$1"
  hf_have_python3 || return 3
  local reqlog="$sandbox/mock-requests.log"; : > "$reqlog"
  local token="test-bearer-DO-NOT-USE-not-a-real-key"
  local port
  port="$(python3 - <<'PY'
import socket
s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()
PY
)"
  python3 - "$port" "$token" "$reqlog" "$sandbox" >"$sandbox/mock-ghl.log" 2>&1 <<'PY' &
import sys, json, http.server, socketserver
port=int(sys.argv[1]); TOKEN=sys.argv[2]; REQLOG=sys.argv[3]; SANDBOX=sys.argv[4]
STORE={"tags":[], "customFields":[], "customValues":[]}
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # silence default stderr noise
    def _record(self, method):
        auth=self.headers.get("Authorization","")
        ver=self.headers.get("Version","")
        # SAFE-BY-DESIGN: we log method+path+whether-auth-present, NEVER the token value.
        with open(REQLOG,"a") as f:
            f.write(json.dumps({"method":method,"path":self.path,
                                "auth_present":bool(auth),"version":ver})+"\n")
        return auth, ver
    def _auth_ok(self, auth, ver):
        return auth==("Bearer "+TOKEN) and ver!=""
    def do_GET(self):
        auth,ver=self._record("GET")
        if not self._auth_ok(auth,ver):
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"unauthorized"}'); return
        key=None
        for k in STORE:
            if "/"+k in self.path: key=k
        body=json.dumps({key or "tags": STORE.get(key,[])}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        auth,ver=self._record("POST")
        n=int(self.headers.get("Content-Length","0") or 0)
        raw=self.rfile.read(n) if n else b""
        if not self._auth_ok(auth,ver):
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"unauthorized"}'); return
        try: data=json.loads(raw or b"{}")
        except Exception:
            self.send_response(400); self.end_headers(); self.wfile.write(b'{"error":"bad json"}'); return
        key=None
        for k in STORE:
            if "/"+k in self.path: key=k
        if key is None:
            self.send_response(404); self.end_headers(); self.wfile.write(b'{"error":"no route"}'); return
        rec={"id":key[:3]+"_"+str(len(STORE[key])+1), **data}
        STORE[key].append(rec)
        body=json.dumps(rec).encode()
        self.send_response(201); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
class Srv(socketserver.TCPServer):
    allow_reuse_address=True
with Srv(("127.0.0.1",port),H) as httpd:
    # write the store on shutdown so L2 can assert what got built
    import signal, atexit
    def dump():
        try:
            with open(SANDBOX+"/mock-store.json","w") as f: json.dump(STORE,f)
        except Exception: pass
    atexit.register(dump)
    signal.signal(signal.SIGTERM, lambda *a: (dump(), sys.exit(0)))
    httpd.serve_forever()
PY
  HF_MOCK_PID=$!
  HF_MOCK_PORT="$port"
  HF_MOCK_TOKEN="$token"
  HF_MOCK_REQLOG="$reqlog"
  echo "$HF_MOCK_PID" > "$sandbox/mock-ghl.pid"
  # wait for readiness (loopback, fast). No foreground sleep loops > a couple seconds.
  local i
  for i in $(seq 1 40); do
    if hf_have_python3 && python3 - "$port" <<'PY' >/dev/null 2>&1
import socket,sys
s=socket.socket(); s.settimeout(0.2)
try: s.connect(("127.0.0.1",int(sys.argv[1]))); print("up")
except Exception: sys.exit(1)
finally: s.close()
PY
    then return 0; fi
    python3 -c 'import time;time.sleep(0.1)' 2>/dev/null || true
  done
  return 1
}

hf_stop_mock() {
  local sandbox="$1"
  local pid
  [[ -f "$sandbox/mock-ghl.pid" ]] && pid="$(cat "$sandbox/mock-ghl.pid")"
  [[ -n "${pid:-}" ]] && kill "$pid" >/dev/null 2>&1 || true
  # give it a beat to dump the store
  python3 -c 'import time;time.sleep(0.2)' 2>/dev/null || true
}

# A loopback HTTP GET/POST helper using curl against the mock ONLY. Guardrail: refuses any
# host that is not 127.0.0.1 / localhost so the harness can never reach a live endpoint.
hf_curl() {
  local url=""
  for a in "$@"; do case "$a" in http*://*) url="$a";; esac; done
  case "$url" in
    http://127.0.0.1:*|http://localhost:*|"") : ;;
    *) hf_fail "BLOCKED non-loopback URL in harness: $url"; return 7 ;;
  esac
  curl -sS "$@"
}

# --- the Big-Brother seeded-defect scanner core (used by L3) -------------------
# This is the executable embodiment of the "Big-Brother core must catch" requirement.
# Given a built-workflow JSON fixture, it returns a list of DEFECT codes it detects.
# It is intentionally pure (no I/O beyond reading the fixture) so it is deterministic and
# unit-testable, and it never makes an external call. Each defect code maps 1:1 to a
# seeded-defect fixture in scripts/test/fixtures/.
#
# Detected defect classes (the section-6 seeded defects):
#   D1_MISSING_DEPENDENCY   a tag/field/value referenced but not in the created-deps set
#   D2_UNFILTERED_TRIGGER   a trigger with no filters and no explicit allow_everyone:true
#   D3_NO_NONE_BRANCH       an If/Else with branches but no fallback/None branch
#   D4_MISSING_ZHC_PREFIX   an agent-created tag/field without the ZHC-/ZHC_ prefix
#   D5_REFIRE_UNGUARDED     a repeat-capable trigger with no re-fire guard
#   D6_WEBHOOK_FULL_URL     a webhook action storing a full URL containing a token/secret
#   D7_PII_IN_LOG           an event line carrying raw PII (email/phone/api key)
#
# Output: one defect code per line on stdout. Empty output = clean. Exit 0 always
# (detection result is the stdout, not the exit code) unless the fixture is unreadable.
hf_bigbrother_scan() {
  local fixture="$1"
  [[ -r "$fixture" ]] || { echo "ERR_UNREADABLE"; return 2; }
  # We use jq for the structured checks. Each emits its code if the defect is present.
  # D1: dependency referenced but not created.
  jq -r '
    (.created_dependencies // []) as $created
    | ( [ .references[]? ] ) as $refs
    | ($refs - $created) as $missing
    | if ($missing|length) > 0 then "D1_MISSING_DEPENDENCY" else empty end
  ' "$fixture" 2>/dev/null
  # D2: a trigger with empty filters and not explicitly allow_everyone.
  jq -r '
    [ .triggers[]?
      | select(((.filters // []) | length) == 0 and (.allow_everyone != true)) ]
    | if length > 0 then "D2_UNFILTERED_TRIGGER" else empty end
  ' "$fixture" 2>/dev/null
  # D3: an if_else with branches but no none/fallback branch.
  jq -r '
    [ .conditions[]?
      | select((.branches // []) | length > 0)
      | select([ .branches[]? | select((.is_none==true) or (.name=="None") or (.fallback==true)) ] | length == 0) ]
    | if length > 0 then "D3_NO_NONE_BRANCH" else empty end
  ' "$fixture" 2>/dev/null
  # D4: an agent-created tag without ZHC- prefix, or field without ZHC_ prefix.
  jq -r '
    [ .created_objects[]?
      | select(.created_by=="agent")
      | select( (.type=="tag"   and (.name|startswith("ZHC-")|not))
             or (.type=="field" and (.name|startswith("ZHC_")|not)) ) ]
    | if length > 0 then "D4_MISSING_ZHC_PREFIX" else empty end
  ' "$fixture" 2>/dev/null
  # D5: a repeat-capable trigger with no refire guard.
  jq -r '
    [ .triggers[]?
      | select(.repeat_capable==true and (.refire_guard != true)) ]
    | if length > 0 then "D5_REFIRE_UNGUARDED" else empty end
  ' "$fixture" 2>/dev/null
  # D6: a webhook action whose stored url contains a query/token (full URL with secret).
  jq -r '
    [ .actions[]?
      | select(.type=="webhook")
      | select((.stored_url // "") | test("[?].*(token|key|secret|sig)=")) ]
    | if length > 0 then "D6_WEBHOOK_FULL_URL" else empty end
  ' "$fixture" 2>/dev/null
  # D7: a log_preview line carrying raw PII. We scan the fixture's declared log_preview
  # array for email / E.164 phone / obvious api-key shapes.
  jq -r '
    [ .log_preview[]?
      | select( test("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}")
             or test("\\+?[0-9]{10,15}")
             or test("(sk-|Bearer |pit-|eyJ)[A-Za-z0-9._-]{8,}") ) ]
    | if length > 0 then "D7_PII_IN_LOG" else empty end
  ' "$fixture" 2>/dev/null
  return 0
}
