#!/usr/bin/env bash
# tests/rescue/RR-028/lib-readiness-harness.sh
#
# Shared harness for the RR-028 batteries. Builds a HERMETIC synthetic box
# (temp dirs only), a persistent mock `openclaw` CLI backed by a JSON job store
# plus a real sqlite `cron_jobs` store, and a loopback receiver stub. Nothing
# here touches a live gateway, a live receiver, a real credential or the repo
# tree.
#
# THE one rule every case follows: a state is asserted from the JSON the tool
# PRINTS plus the rc it returns, and every "the tool refused" assertion is
# paired with a control proving the observer could have seen the opposite
# (a recorded argv, a stored job, a written receipt).
#
# Sourced, never executed. Expects the battery to set PASS/FAIL and to define
# ok()/bad().

RR028_REPO="${RR028_REPO:?RR028_REPO must point at the repo root}"

rr028_require_files() {
  _miss=""
  for _f in "$RR028_REPO/65-rescue-receiver/wire.sh" \
            "$RR028_REPO/65-rescue-receiver/rr-readiness.sh" \
            "$RR028_REPO/65-rescue-receiver/rescue-poll.sh" \
            "$RR028_REPO/shared-utils/rr-readiness.sh" \
            "$RR028_REPO/shared-utils/rescue-env.sh" \
            "$RR028_REPO/shared-utils/oc-env-descriptor.sh"; do
    [ -f "$_f" ] || _miss="$_miss $_f"
  done
  if [ -n "$_miss" ]; then echo "FATAL: missing RR-028 file(s):$_miss"; exit 2; fi
  command -v python3 >/dev/null 2>&1 || { echo "FATAL: no python3"; exit 2; }
  command -v curl >/dev/null 2>&1 || { echo "FATAL: no curl"; exit 2; }
}

# ---------------------------------------------------------------------------
# rr028_make_box <box-dir> [store-lines-file]
#   Creates <box>/.openclaw with the installed skill layout (skills dir +
#   secrets + state + bin) and copies the REAL scripts under test. The store
#   defaults to an enrolled synthetic box.
# ---------------------------------------------------------------------------
rr028_make_box() {
  _box="$1"; _store="${2:-}"
  mkdir -p "$_box/.openclaw/skills/65-rescue-receiver" \
           "$_box/.openclaw/skills/shared-utils" \
           "$_box/.openclaw/secrets" \
           "$_box/.openclaw/state/rr-receiver" \
           "$_box/.openclaw/workspace" \
           "$_box/bin"
  cp "$RR028_REPO/65-rescue-receiver/rescue-poll.sh" "$_box/.openclaw/skills/65-rescue-receiver/"
  cp "$RR028_REPO/65-rescue-receiver/wire.sh"        "$_box/.openclaw/skills/65-rescue-receiver/"
  cp "$RR028_REPO/65-rescue-receiver/rr-readiness.sh" "$_box/.openclaw/skills/65-rescue-receiver/"
  cp "$RR028_REPO/shared-utils/rescue-env.sh"        "$_box/.openclaw/skills/shared-utils/"
  cp "$RR028_REPO/shared-utils/rr-readiness.sh"      "$_box/.openclaw/skills/shared-utils/"
  cp "$RR028_REPO/shared-utils/oc-env-descriptor.sh" "$_box/.openclaw/skills/shared-utils/"
  if [ -n "$_store" ] && [ -f "$_store" ]; then
    cp "$_store" "$_box/.openclaw/secrets/.env"
  else
    printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_TOKEN="tok-synthetic-rr028"\nRR_BOX_SLUG=box-synthetic\n' \
      > "$_box/.openclaw/secrets/.env"
  fi
  chmod 600 "$_box/.openclaw/secrets/.env"
  printf '{"jobs":[]}' > "$_box/jobs.json"
  : > "$_box/calls.log"
  : > "$_box/argv.log"
  rr028_mock_openclaw "$_box"
}

# ---------------------------------------------------------------------------
# The mock openclaw CLI. Persistent JSON store + a REAL sqlite cron_jobs store
# so the engine's two readback views can both be exercised. Every invocation is
# recorded as a NUL-safe, one-argv-element-per-line block so an assertion can
# prove an argument was NOT word-split.
# ---------------------------------------------------------------------------
rr028_mock_openclaw() {
  _box="$1"
  cat > "$_box/bin/openclaw" <<'MOCKEOF'
#!/usr/bin/env python3
"""RR-028 mock `openclaw` CLI. Store: $RR028_JOBS. Call log: $RR028_CALLLOG."""
import json, os, sqlite3, sys

JOBS = os.environ.get("RR028_JOBS", "")
LOG = os.environ.get("RR028_CALLLOG", "")
DB = os.environ.get("RR028_DB", "")
argv = sys.argv[1:]
if LOG:
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("CALL %d\n" % len(argv))
        for a in argv:
            fh.write("ARG " + a.replace("\n", "\\n") + "\n")

def load():
    try:
        with open(JOBS, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        d = {"jobs": []}
    if not isinstance(d, dict):
        d = {"jobs": []}
    d.setdefault("jobs", [])
    return d

def save(d):
    tmp = JOBS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    os.replace(tmp, JOBS)
    if DB:
        try:
            con = sqlite3.connect(DB)
            con.execute("create table if not exists cron_jobs (job_id text primary key, job_json text)")
            con.execute("delete from cron_jobs")
            for j in d.get("jobs", []):
                con.execute("insert or replace into cron_jobs (job_id, job_json) values (?, ?)",
                            (str(j.get("id", "")), json.dumps(j)))
            con.commit(); con.close()
        except Exception:
            pass

def flag(name):
    return name in argv

def val(name, default=""):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default

if not argv or argv[0] != "cron":
    sys.exit(0)
action = argv[1] if len(argv) > 1 else ""
rest = argv[2:]

def next_id(d):
    n = 0
    for j in d["jobs"]:
        try:
            n = max(n, int(str(j.get("id", "0"))))
        except Exception:
            n += 1
    return str(n + 1)

if action == "list" and "--help" in rest:
    # A build that HIDES disabled jobs from `cron list --json` must not advertise
    # a full-status listing flag: the engine's fail-closed rule is driven by what
    # the CLI's own help PROMISES, and a fixture that both hides a disabled job
    # and claims `--all` support would be modelling a CLI that lies about itself.
    # RR028_MOCK_NO_ALL=1 therefore makes the help text consistent with the list
    # behaviour: no flag is offered, so the engine cannot tell "absent" from
    # "present but disabled" and must refuse to mutate.
    if os.environ.get("RR028_MOCK_NO_ALL") == "1":
        print("usage: openclaw cron list [--json]")
        print("  --json")
    else:
        print("usage: openclaw cron list [--json] [--all]")
        print("  --json")
        print("  --all")
    sys.exit(0)

if action == "list":
    if os.environ.get("RR028_MOCK_LIST_MODE") == "unreadable":
        sys.stderr.write("mock: cron store unreadable\n")
        sys.exit(1)
    d = load()
    show_all = flag("--all") and os.environ.get("RR028_MOCK_NO_ALL") != "1"
    jobs = d["jobs"] if show_all else [j for j in d["jobs"] if j.get("enabled", True)]
    print(json.dumps({"jobs": jobs}))
    sys.exit(0)

if action == "add" and "--help" in rest:
    print("usage: openclaw cron add --name N --cron E --command C [--no-deliver]")
    if os.environ.get("RR028_MOCK_NO_DELIVER") == "1":
        print("  (this build has no --no-deliver)")
    sys.exit(0)

if action == "edit" and "--help" in rest:
    if os.environ.get("RR028_MOCK_NO_EDIT_FLAGS") == "1":
        # A build whose `cron edit` advertises NO editable field: the
        # reconciler must fall back to replace (rm + add), not claim success.
        print("usage: openclaw cron edit ID")
        sys.exit(0)
    print("usage: openclaw cron edit ID [--cron E] [--command C] [--no-deliver]")
    if os.environ.get("RR028_MOCK_NO_DELIVER") == "1":
        print("  (this build has no --no-deliver)")
    sys.exit(0)

if action == "add":
    if os.environ.get("RR028_MOCK_ADD_MODE") == "reject":
        sys.stderr.write("mock: cron add rejected\n"); sys.exit(1)
    if os.environ.get("RR028_MOCK_ADD_MODE") == "silent":
        sys.exit(0)   # exit 0 and store NOTHING: the failing-readback plant
    d = load()
    job = {
        "id": next_id(d),
        "name": val("--name"),
        "enabled": True,
        "schedule": {"kind": "cron", "expr": val("--cron")},
        "payload": {"kind": "command", "command": val("--command")},
        "delivery": {"mode": "none" if flag("--no-deliver") else "announce"},
    }
    d["jobs"].append(job)
    save(d)
    sys.exit(0)

if action == "edit":
    if os.environ.get("RR028_MOCK_EDIT_MODE") == "reject":
        sys.stderr.write("mock: cron edit rejected\n"); sys.exit(1)
    d = load()
    jid = rest[0] if rest else ""
    for j in d["jobs"]:
        if str(j.get("id")) == str(jid):
            if flag("--cron"):
                j.setdefault("schedule", {})["expr"] = val("--cron")
                j["schedule"]["kind"] = "cron"
            if flag("--command"):
                j.setdefault("payload", {})["command"] = val("--command")
                j["payload"]["kind"] = "command"
            if flag("--no-deliver"):
                j.setdefault("delivery", {})["mode"] = "none"
            break
    save(d)
    sys.exit(0)

if action in ("rm", "remove", "delete"):
    if os.environ.get("RR028_MOCK_RM_MODE") == "reject":
        sys.stderr.write("mock: cron rm rejected\n"); sys.exit(1)
    d = load()
    jid = rest[0] if rest else ""
    d["jobs"] = [j for j in d["jobs"] if str(j.get("id")) != str(jid)]
    save(d)
    sys.exit(0)

if action in ("disable", "enable"):
    d = load()
    jid = rest[0] if rest else ""
    for j in d["jobs"]:
        if str(j.get("id")) == str(jid):
            j["enabled"] = (action == "enable")
    save(d)
    sys.exit(0)

sys.exit(0)
MOCKEOF
  chmod +x "$_box/bin/openclaw"
}

# rr028_job <box> <json-object>  — append one job to the store (python3).
rr028_job() {
  _box="$1"; _job="$2"
  RR028_JOBS="$_box/jobs.json" RR028_DB="${3:-}" RR028_JOB="$_job" python3 - <<'PY'
import json, os, sqlite3
p = os.environ["RR028_JOBS"]
d = json.load(open(p, encoding="utf-8"))
d.setdefault("jobs", []).append(json.loads(os.environ["RR028_JOB"]))
json.dump(d, open(p, "w", encoding="utf-8"))
db = os.environ.get("RR028_DB", "")
if db:
    con = sqlite3.connect(db)
    con.execute("create table if not exists cron_jobs (job_id text primary key, job_json text)")
    con.execute("delete from cron_jobs")
    for j in d["jobs"]:
        con.execute("insert or replace into cron_jobs (job_id, job_json) values (?,?)",
                    (str(j.get("id", "")), json.dumps(j)))
    con.commit(); con.close()
PY
}

# rr028_make_db <box> — a real state DB holding the current store.
rr028_make_db() {
  _box="$1"
  [ -n "$(command -v sqlite3 || true)" ] || return 1
  RR028_JOBS="$_box/jobs.json" RR028_DB="$_box/.openclaw/state/openclaw.sqlite" python3 - <<'PY'
import json, os, sqlite3
d = json.load(open(os.environ["RR028_JOBS"], encoding="utf-8"))
con = sqlite3.connect(os.environ["RR028_DB"])
con.execute("create table if not exists cron_jobs (job_id text primary key, job_json text)")
con.execute("delete from cron_jobs")
for j in d.get("jobs", []):
    con.execute("insert or replace into cron_jobs (job_id, job_json) values (?,?)",
                (str(j.get("id", "")), json.dumps(j)))
con.commit(); con.close()
PY
}

# ---------------------------------------------------------------------------
# rr028_make_state_db <box> — a state DB that a REAL gateway could have written
# even before any cron exists (schema present, cron_jobs empty, readable by
# sqlite3). The descriptor's `ocd_state_db` ACCEPTS a DB only when it has at
# least one table, so an empty file is not a valid fixture for "the gateway
# store resolves and holds no cron". Cases that need a successful ADD use this;
# cases about the CLI-only blind spot deliberately do not.
# ---------------------------------------------------------------------------
rr028_make_state_db() {
  _box="$1"
  [ -n "$(command -v sqlite3 || true)" ] || return 1
  RR028_DB="$_box/.openclaw/state/openclaw.sqlite" python3 - <<'PY'
import os, sqlite3
con = sqlite3.connect(os.environ["RR028_DB"])
con.execute("create table if not exists cron_jobs (job_id text primary key, job_json text)")
con.commit(); con.close()
PY
}

# ---------------------------------------------------------------------------
# rr028_run <box> <tool> [args...] — run the REAL tool in the synthetic box.
# Env knobs travel through RR028_ENV_* so callers stay readable.
# Sets: RR028_OUT (stdout), RR028_ERRC (stderr path), RR028_RC.
# ---------------------------------------------------------------------------
rr028_run() {
  _box="$1"; shift
  _tool="$1"; shift
  # RR028_STDERR (optional): APPEND every run's stderr here, so a caller can
  # assert on the stderr of an EARLIER run after running the tool again (the
  # default per-box file is overwritten by each run).
  _err_target="$_box/stderr.txt"; _err_mode=">"
  if [ -n "${RR028_STDERR:-}" ]; then _err_target="$RR028_STDERR"; _err_mode=">>"; fi
  if [ "$_err_mode" = ">" ]; then : > "$_err_target" 2>/dev/null || true; fi
  RR028_OUT="$(env \
      RR_ROOT="$_box/.openclaw" \
      OC_CONFIG_ROOT="$_box/.openclaw" \
      RR028_JOBS="$_box/jobs.json" \
      RR028_CALLLOG="$_box/calls.log" \
      RR028_DB="${RR028_DB_FILE:-}" \
      OC_PLATFORM="${RR028_PLATFORM:-mac}" \
      OC_TARGET_MODE="${RR028_TARGET_MODE:-launchd}" \
      OC_TARGET_ID="${RR028_TARGET_ID:-ai.openclaw.gateway}" \
      OC_SERVICE_LABEL="${RR028_TARGET_ID:-ai.openclaw.gateway}" \
      OC_SKIP_CLI_PROBE=1 \
      HOME="$_box" \
      PATH="$_box/bin:$PATH" \
      ${RR028_EXTRA_ENV:-} \
      bash "$_tool" "$@" 2>>"$_err_target")"
  RR028_RC=$?
  RR028_ERRC="$_box/stderr.txt"
  return "$RR028_RC"
}

rr028_wire()  { rr028_run "$1" "$1/.openclaw/skills/65-rescue-receiver/wire.sh" "${@:2}"; }
rr028_readiness() { rr028_run "$1" "$1/.openclaw/skills/65-rescue-receiver/rr-readiness.sh" "${@:2}"; }

# rr028_field <json> <dotted.path> — read one field out of the --json report.
rr028_field() {
  printf '%s' "$1" | RR028_F="$2" python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
o = d
for k in os.environ["RR028_F"].split("."):
    if isinstance(o, dict) and k in o:
        o = o[k]
    else:
        print(""); raise SystemExit(0)
print(o if isinstance(o, str) else json.dumps(o))
'
}

# rr028_argv_blocks <box> — print the recorded argv vectors, one per line,
# elements joined with \x1f so a split argument is visible.
rr028_argv_blocks() {
  python3 - "$1/calls.log" <<'PY'
import sys
try:
    lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
except Exception:
    sys.exit(0)
cur = []
for ln in lines:
    if ln.startswith("CALL "):
        if cur: print("\x1f".join(cur))
        cur = []
    elif ln.startswith("ARG "):
        cur.append(ln[4:])
if cur: print("\x1f".join(cur))
PY
}

# rr028_calls_with <box> <substring> — argv blocks containing a token.
rr028_calls_with() {
  rr028_argv_blocks "$1" | grep -F -- "$2" || true
}

# ---------------------------------------------------------------------------
# The loopback receiver stub. Modes:
#   no_work       2xx structured {"status":"empty"}      (the ONLY pass)
#   instruction   2xx structured {"status":"instruction",...}
#   unstructured  2xx text/html
#   unauthorized  401
#   redirect      302
# It records every request line + body to <box>/receiver.log so an assertion
# can prove the probe sent no ack and the box slug rode the BODY (never argv).
# ---------------------------------------------------------------------------
rr028_start_receiver() {  # rr028_start_receiver <box> <port> <mode>
  _box="$1"; _port="$2"; _mode="$3"
  cat > "$_box/receiver.py" <<PYEOF
import http.server, json, sys

MODE = "$_mode"
LOG = "$_box/receiver.log"

class H(http.server.BaseHTTPRequestHandler):
    def _log(self, body):
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write("REQ %s %s\n" % (self.command, self.path))
            fh.write("BODY %s\n" % body.decode("utf-8", "replace"))
            fh.write("HDR X-RR-Box-Token %s\n" % ("present" if self.headers.get("X-RR-Box-Token") else "absent"))
    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(ln)
        self._log(body)
        if MODE == "unauthorized":
            self.send_response(401); self.end_headers(); return
        if MODE == "redirect":
            self.send_response(302); self.send_header("Location", "/login"); self.end_headers(); return
        if MODE == "unstructured":
            out = b"<html>login</html>"
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out); return
        if MODE == "instruction":
            resp = {"status": "instruction", "instruction_id": "ins-probe", "idempotency_key": "K-probe",
                    "ticket_id": "T-probe", "agent_id": "main", "session_key": "s-probe",
                    "payload_b64": "bm9wZQ==", "mode": "dry_run"}
        else:
            resp = {"status": "empty"}
        out = json.dumps(resp).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass

http.server.HTTPServer(("127.0.0.1", $_port), H).serve_forever()
PYEOF
  python3 "$_box/receiver.py" >/dev/null 2>&1 &
  RR028_RECEIVER_PID=$!
  rr028_register_pid "$_box" "$RR028_RECEIVER_PID"
  _i=0
  while [ "$_i" -lt 40 ]; do
    if python3 -c "
import socket,sys
s=socket.socket()
try:
    s.connect(('127.0.0.1',$_port)); s.close()
except Exception: sys.exit(1)
" 2>/dev/null; then return 0; fi
    sleep 0.05; _i=$((_i + 1))
  done
  return 1
}

rr028_stop_receiver() {
  [ -n "${RR028_RECEIVER_PID:-}" ] && kill "$RR028_RECEIVER_PID" 2>/dev/null || true
  wait "$RR028_RECEIVER_PID" 2>/dev/null || true
  RR028_RECEIVER_PID=""
}
# ---------------------------------------------------------------------------
# Receiver bookkeeping (RR-028 review M-5).
#
# `rr028_stop_receiver` used to know only the LAST pid, so a battery killed
# mid-run (a CI timeout, a tool cap) leaked every receiver it had started;
# enough orphans and the batteries fail spuriously on port or load collisions.
# Every spawned pid is now recorded in a PIDFILE the battery sets (normally
# inside its own $WORK, so the file dies with the run), and `rr028_killall`
# reaps all of them from a single EXIT/INT/TERM trap.
# ---------------------------------------------------------------------------

# rr028_pidfile <box> — the registry path for this battery.
rr028_pidfile() {
  [ -n "${RR028_PIDFILE:-}" ] && { printf '%s' "$RR028_PIDFILE"; return 0; }
  printf '%s/rr028-receivers.pid' "$1"
}

# rr028_register_pid <box> <pid>
rr028_register_pid() {
  _rp_file="$(rr028_pidfile "$1")"
  [ -n "$_rp_file" ] || return 0
  printf '%s\n' "$2" >> "$_rp_file" 2>/dev/null || true
}

# rr028_killall <box> — reap EVERY receiver this battery recorded. The registry
# is the primary source (it lists all of them, not just the last); a
# command-line match is a bounded SUPPLEMENT so a receiver started before the
# registry existed, or after it was removed, is still cleaned up. Never fails:
# a trap must not abort the exit path.
rr028_killall() {
  _rk_box="${1:-}"
  _rk_file=""
  [ -n "$_rk_box" ] && _rk_file="$(rr028_pidfile "$_rk_box")"
  if [ -n "$_rk_file" ] && [ -s "$_rk_file" ]; then
    while read -r _rk_pid; do
      case "$_rk_pid" in ''|*[!0-9]*) continue ;; esac
      kill "$_rk_pid" 2>/dev/null || true
    done < "$_rk_file"
  fi
  [ -n "${RR028_RECEIVER_PID:-}" ] && kill "$RR028_RECEIVER_PID" 2>/dev/null || true
  # Match this battery's OWN stub path only (its box lives under its $WORK), and
  # never this shell or its parent.
  if [ -n "$_rk_box" ] && command -v pgrep >/dev/null 2>&1; then
    for _rk_pid in $(pgrep -f "$_rk_box/receiver.py" 2>/dev/null || true); do
      case "$_rk_pid" in ''|*[!0-9]*|"$$"|"$PPID") continue ;; esac
      kill "$_rk_pid" 2>/dev/null || true
    done
  fi
  RR028_RECEIVER_PID=""
  return 0
}

# The trap body every battery uses: reap receivers, then remove $WORK. The
# RR028_DONE flag (set at a clean finish) no longer decides WHETHER to reap —
# that gate is what leaked receivers when a battery was killed mid-run.
rr028_cleanup() {
  rr028_killall "${RR028_PIDFILE_BOX:-}"
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
  return 0
}

# A port unique-ish per battery process AND per case index.
rr028_port() { echo $(( 24000 + ($$ % 3000) + ${1:-0} )); }

# A path-safe name holding shell metacharacters and spaces.
rr028_weird_root() { printf '%s/rr028 box;touch PWNED$(id -u) & <x>/' "${TMPDIR:-/tmp}"; }
