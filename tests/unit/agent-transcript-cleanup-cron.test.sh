#!/usr/bin/env bash
# tests/unit/agent-transcript-cleanup-cron.test.sh
#
# Wiring for the daily agent transcript cleanup (scripts/agent-transcript-cleanup.py + .sh):
#   1. ensure-pipeline-crons.sh registers `agent-transcript-cleanup` at 04:30 daily in
#      America/New_York as a silent COMMAND cron (--no-deliver), once (idempotent), repairs an
#      existing loud copy, honours a tombstone, and skips cleanly when the script is absent;
#      it is in MANAGED_RECONCILE_CRONS, the main() audit list and the install.sh copy loop.
#   2. The wrapper exits 0 on skip/refusal paths and non-zero only when the python crashes, and
#      the real wrapper cleans a fixture box end to end.
# Hermetic: private $HOME and sandbox, fake `openclaw`, never the real one.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENSURE="$REPO_ROOT/scripts/ensure-pipeline-crons.sh"
INSTALL="$REPO_ROOT/install.sh"
WRAP="$REPO_ROOT/scripts/agent-transcript-cleanup.sh"
PYSCRIPT="$REPO_ROOT/scripts/agent-transcript-cleanup.py"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
NAME="agent-transcript-cleanup"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

echo "=== agent-transcript-cleanup-cron.test.sh ==="

echo "--- 1: wiring is in lockstep ---"
python3 - "$ENSURE" "$INSTALL" <<'PY' && pass "1a: registered, managed, audited and installed in lockstep" || fail "1a: wiring is not in lockstep (see above)"
import re, sys
ens, ins = (open(p).read() for p in sys.argv[1:3])
bad = []
if not re.search(r'_ensure_health_cron "agent-transcript-cleanup"\s+"30 4 \* \* \*"\s+"agent-transcript-cleanup\.sh"\s+"America/New_York"', ens):
    bad.append("no _ensure_health_cron agent-transcript-cleanup at 30 4 * * * America/New_York")
m = re.search(r'MANAGED_RECONCILE_CRONS=\(\n(.*?)\n\)', ens, re.S)
if not m or "agent-transcript-cleanup" not in re.findall(r'^\s*"([^"]+)"', m.group(1), re.M):
    bad.append("missing from MANAGED_RECONCILE_CRONS")
a = re.search(r'for _n in ((?:"[^"]+"\s*\\?\s*)+); do', ens)
if not a or "agent-transcript-cleanup" not in re.findall(r'"([^"]+)"', a.group(1)):
    bad.append("missing from the main() audit list")
loop = re.search(r'EMBEDDING-PREVENTION BUNDLE \(items 4-7\).*?for SCRIPT in ([^;]*); do', ins, re.S)
for f in ("agent-transcript-cleanup.sh", "agent-transcript-cleanup.py"):
    if not loop or f not in loop.group(1).split():
        bad.append(f + " missing from the install.sh copy loop")
if bad:
    print("\n".join("    " + b for b in bad))
sys.exit(1 if bad else 0)
PY

mk_box() { # <tag> <with-script 0|1>  -> sets H B J C
  local tag="$1" with="$2" s
  H="$SANDBOX/home-$tag"; B="$SANDBOX/bin-$tag"; J="$SANDBOX/jobs-$tag.json"; C="$SANDBOX/calls-$tag.log"
  mkdir -p "$H/.openclaw/scripts" "$H/clawd" "$B"
  for s in index-model-drift-check.sh orphan-temp-sweep.sh disk-usage-alert.sh pre-july14-embedding-migration-check.sh \
           toolsearch-drift-guard.sh agent-browser-reaper.sh bootstrap-validate-daily.sh bootstrap-compact-weekly.sh; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$H/.openclaw/scripts/$s"
  done
  [ "$with" = "1" ] && printf '#!/usr/bin/env bash\nexit 0\n' > "$H/.openclaw/scripts/$NAME.sh"
  chmod +x "$H/.openclaw/scripts/"*.sh
  printf '%s' '{}' > "$H/.openclaw/openclaw.json"
  printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$B/openclaw"; chmod +x "$B/openclaw"
  printf '[]' > "$J"; : > "$C"
}
run_ensure() { HOME="$H" PATH="$B:$PATH" FAKE_OC_JOBS_FILE="$J" FAKE_OC_CALLS_FILE="$C" bash "$ENSURE" > "$SANDBOX/ensure.log" 2>&1; }
job_field() { # <name> <count|mode|any job field>
  python3 - "$J" "$1" "$2" <<'PY'
import json, sys
path, name, what = sys.argv[1:4]
rows = [j for j in json.load(open(path)) if j.get("name") == name]
if what == "count":
    print(len(rows))
elif not rows:
    print("ABSENT")
elif what == "mode":
    print((rows[0].get("delivery") or {}).get("mode"))
else:
    print(rows[0].get(what))
PY
}

echo "--- 2: registration ---"
mk_box reg 1; run_ensure
[ "$(job_field $NAME count)" = "1" ] && pass "2a: registered once" || fail "2a: count is $(job_field $NAME count), want 1"
[ "$(job_field $NAME cron)" = "30 4 * * *" ] && pass "2b: schedule 30 4 * * * (4:30 AM daily)" || fail "2b: schedule is $(job_field $NAME cron)"
[ "$(job_field $NAME kind)" = "command" ] && pass "2c: COMMAND kind (no model turn)" || fail "2c: kind is $(job_field $NAME kind)"
[ "$(job_field $NAME mode)" = "none" ] && pass "2d: born silent (delivery mode none)" || fail "2d: delivery mode is $(job_field $NAME mode)"
grep -q -- "cron add --name $NAME .*--tz America/New_York" "$C" && pass "2e: registered in America/New_York" || fail "2e: no --tz America/New_York on the registration"
grep -q -- "cron add --name $NAME .*--no-deliver" "$C" && pass "2f: --no-deliver passed at birth" || fail "2f: --no-deliver missing at birth"
job_field $NAME command | grep -q "$NAME.sh$" && pass "2g: runs $NAME.sh" || fail "2g: command is $(job_field $NAME command)"
run_ensure
[ "$(job_field $NAME count)" = "1" ] && pass "2h: a second run adds no second copy (idempotent)" || fail "2h: second run left $(job_field $NAME count) copies"

mk_box old 1
python3 - "$J" "$H" "$NAME" <<'PY'
import json, sys
json.dump([{"name": sys.argv[3], "cron": "30 4 * * *", "agent": "", "message": "", "kind": "command",
            "command": "bash %s/.openclaw/scripts/%s.sh" % (sys.argv[2], sys.argv[3]), "id": "pre-atc",
            "delivery": {"mode": "announce", "channel": "last", "to": None},
            "payload": {"kind": "command"}, "schedule": {"expr": "30 4 * * *"}}], open(sys.argv[1], "w"))
PY
run_ensure
[ "$(job_field $NAME mode)" = "none" ] && pass "2i: an existing loud copy is silenced by the reconcile pass" || fail "2i: existing copy left at delivery mode $(job_field $NAME mode)"

mk_box nos 0; run_ensure
[ "$(job_field $NAME count)" = "0" ] && pass "2j: script absent (older bundle): skipped, nothing registered" || fail "2j: registered without the script"
grep -q "SKIP $NAME" "$SANDBOX/ensure.log" && pass "2k: the skip is logged" || fail "2k: no SKIP line"

mk_box tomb 1
mkdir -p "$H/.openclaw"
cron_lib="$REPO_ROOT/shared-utils/cron-lib.sh"
if grep -q "oc_cron_tombstone()" "$cron_lib"; then
  ( export HOME="$H"; export PATH="$B:$PATH"; export FAKE_OC_JOBS_FILE="$J" FAKE_OC_CALLS_FILE="$C"
    . "$cron_lib" 2>/dev/null; oc_cron_tombstone "$NAME" >/dev/null 2>&1 )
  run_ensure
  [ "$(job_field $NAME count)" = "0" ] && pass "2l: a tombstoned cron is NOT re-registered" || fail "2l: tombstoned cron was re-registered"
else
  fail "2l: oc_cron_tombstone helper not found"
fi

echo "--- 3: wrapper ---"
mkdir -p "$SANDBOX/w"; cp "$WRAP" "$PYSCRIPT" "$SANDBOX/w/"
out="$(HOME="$SANDBOX/emptyhome" OPENCLAW_HOME="" OC_ROOT="" bash "$SANDBOX/w/agent-transcript-cleanup.sh" 2>&1)"; rc=$?
if [ ! -d /data/.openclaw ]; then
  [ $rc -eq 0 ] && echo "$out" | grep -q SKIPPED && pass "3a: no OpenClaw root: SKIPPED, exit 0" || fail "3a: rc=$rc out=$out"
else
  pass "3a: skipped (this machine has /data/.openclaw; not exercised)"
fi
rm -f "$SANDBOX/w/agent-transcript-cleanup.py"
out="$(OPENCLAW_HOME="$SANDBOX/oc" bash "$SANDBOX/w/agent-transcript-cleanup.sh" 2>&1)"; rc=$?
[ $rc -eq 0 ] && echo "$out" | grep -q "older bundle" && pass "3b: python missing: SKIPPED, exit 0" || fail "3b: rc=$rc out=$out"
cp "$PYSCRIPT" "$SANDBOX/w/"
mkdir -p "$SANDBOX/oc/agents/main/agent"
printf 'not a database at all' > "$SANDBOX/oc/agents/main/agent/openclaw-agent.sqlite"
out="$(OPENCLAW_HOME="$SANDBOX/oc" bash "$SANDBOX/w/agent-transcript-cleanup.sh" 2>&1)"; rc=$?
[ $rc -eq 0 ] && echo "$out" | grep -q "rc=1" && pass "3c: an unreadable database is an error line, exit 0 (never auto-disables the cron)" || fail "3c: rc=$rc out=$out"
printf 'import sys\nraise SystemExit(7)\n' > "$SANDBOX/w/agent-transcript-cleanup.py"
out="$(OPENCLAW_HOME="$SANDBOX/oc" bash "$SANDBOX/w/agent-transcript-cleanup.sh" 2>&1)"; rc=$?
[ $rc -eq 7 ] && echo "$out" | grep -q CRASH && pass "3d: a crash exits non-zero" || fail "3d: rc=$rc out=$out"

echo "--- 4: real wrapper end to end on a fixture box ---"
cp "$PYSCRIPT" "$SANDBOX/w/agent-transcript-cleanup.py"
E2E="$SANDBOX/e2e"
python3 - "$REPO_ROOT/tests/unit/agent-transcript-cleanup.test.py" "$E2E/agents/main/agent/openclaw-agent.sqlite" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("atct", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m); m.build_db(sys.argv[2])
PY
out="$(OPENCLAW_HOME="$E2E" bash "$SANDBOX/w/agent-transcript-cleanup.sh" 2>&1)"; rc=$?
left="$(python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select count(*) from session_windows').fetchone()[0])" "$E2E/agents/main/agent/openclaw-agent.sqlite")"
[ $rc -eq 0 ] && [ "$left" = "7" ] && pass "4a: wrapper run removed the 7 old windows, kept the 7 protected ones, exit 0" || fail "4a: rc=$rc left=$left out=$out"
[ -s "$E2E/logs/agent-transcript-cleanup.log" ] && ls "$E2E"/archives/agent-transcripts/main/*.sqlite >/dev/null 2>&1 \
  && pass "4b: summary line logged and archive written" || fail "4b: log or archive missing"
[ -z "$out" ] && pass "4c: quiet under the wrapper's maintenance mode (no stdout)" || fail "4c: stdout was: $out"

# a refused database with NO OpenClaw variables set (only HOME): the wrapper must exit 0 and log it
NOENV="$SANDBOX/noenv-home"
python3 - "$REPO_ROOT/tests/unit/agent-transcript-cleanup.test.py" "$NOENV/.openclaw/agents/main/agent/openclaw-agent.sqlite" <<'PY'
import importlib.util, sqlite3, sys
spec = importlib.util.spec_from_file_location("atct", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m); m.build_db(sys.argv[2])
c = sqlite3.connect(sys.argv[2]); c.execute("PRAGMA user_version=28"); c.close()
PY
out="$(env -i HOME="$NOENV" PATH="$PATH" bash "$SANDBOX/w/agent-transcript-cleanup.sh" 2>&1)"; rc=$?
[ $rc -eq 0 ] && echo "$out" | grep -q "rc=2" && ! echo "$out" | grep -qi "unbound" \
  && grep -q "status=REFUSED" "$NOENV/.openclaw/logs/agent-transcript-cleanup.log" \
  && pass "4e: refused database, only HOME set: wrapper exits 0 (no unbound variable) and the refusal is logged" \
  || fail "4e: rc=$rc out=$out"

E2E2="$SANDBOX/e2e-parent"
python3 - "$REPO_ROOT/tests/unit/agent-transcript-cleanup.test.py" "$E2E2/.openclaw/agents/main/agent/openclaw-agent.sqlite" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("atct", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m); m.build_db(sys.argv[2])
PY
OPENCLAW_HOME="$E2E2" bash "$SANDBOX/w/agent-transcript-cleanup.sh" >/dev/null 2>&1
left="$(python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select count(*) from session_windows').fetchone()[0])" "$E2E2/.openclaw/agents/main/agent/openclaw-agent.sqlite")"
[ "$left" = "7" ] && pass "4d: OPENCLAW_HOME as the PARENT of .openclaw works through the wrapper" || fail "4d: parent-shaped OPENCLAW_HOME left $left windows"

echo
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
