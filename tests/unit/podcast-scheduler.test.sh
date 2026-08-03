#!/usr/bin/env bash
# tests/unit/podcast-scheduler.test.sh -- act-4: the podcast production
# scheduler (the controller's heartbeat).
#
# THE CONTROLLER IS THE PROCESSOR; THE SCHEDULER IS ITS HEARTBEAT.
# Proves: the runner sources the podcast env, locks, runs the controller
# --once and mirrors its exit code; a missing controller is a green no-op;
# the installer is idempotent under a root prefix; the cron entry matches
# the repo cron.d idiom (5 schedule fields + user + command, every 5 min);
# guard-cron-inventory.py recognizes the box-level tick by name, excludes it
# from the per-client census, and still fails poller/announce-shaped impostors.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPTS="$REPO_ROOT/58-podcast-production-engine/scripts"
RUNNER="$SCRIPTS/podcast_scheduler_runner.sh"
INSTALLER="$SCRIPTS/install-podcast-scheduler.sh"
CRON_ENTRY="$REPO_ROOT/config/cron.d/podcast-scheduler"
PLIST_TEMPLATE="$REPO_ROOT/58-podcast-production-engine/config/launchd/com.openclaw.podcast-scheduler.plist.template"
GUARD="$SCRIPTS/guard-cron-inventory.py"
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/podcast-scheduler-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
PY="${PYTHON:-python3}"

echo "== T1 shell syntax (bash -n) =="
for f in "$RUNNER" "$INSTALLER"; do
  if bash -n "$f" 2>/dev/null; then pass "T1: bash -n $(basename "$f")"; else fail "T1: bash -n $(basename "$f")"; fi
done

echo "== T2 runner dry-run =="
OUT2="$WORK/t2.log"
if HOME="$WORK" PODCAST_SCHEDULER_LOG="$OUT2" PODCAST_SCHEDULER_LOCKDIR="$WORK/t2.lock" bash "$RUNNER" --dry-run >/dev/null 2>&1; then
  grep -q "DRY" "$OUT2" && pass "T2: dry-run exits 0 and logs DRY" || fail "T2: no DRY line"
else
  fail "T2: dry-run exit"
fi

echo "== T3 runner: controller absent -> green no-op =="
OUT3="$WORK/t3.log"
HOME="$WORK" PODCAST_SCHEDULER_LOG="$OUT3" PODCAST_SCHEDULER_LOCKDIR="$WORK/t3.lock" \
  PODCAST_CONTROLLER_PATH="$WORK/absent-controller.py" bash "$RUNNER" >/dev/null 2>&1
RC=$?
[ $RC -eq 0 ] && grep -q "WAIT" "$OUT3" && pass "T3: missing controller exits 0 with WAIT" || fail "T3: rc=$RC"

echo "== T4 runner: sources the podcast env, runs --once =="
CTRL4="$WORK/controller4.py"
cat > "$CTRL4" <<'EOF'
import os, sys
assert "--once" in sys.argv, "expected --once"
with open(sys.argv[0] + ".out", "w", encoding="utf-8") as fh:
    fh.write(os.environ.get("PODCAST_TEST_VAR", "<unset>"))
sys.exit(0)
EOF
ENVFILE="$WORK/podcast-env.sh"
printf 'export PODCAST_TEST_VAR=sourced-ok\n' > "$ENVFILE"
OUT4="$WORK/t4.log"
HOME="$WORK" PODCAST_ENV_FILE="$ENVFILE" PODCAST_SCHEDULER_LOG="$OUT4" \
  PODCAST_SCHEDULER_LOCKDIR="$WORK/t4.lock" PODCAST_CONTROLLER_PATH="$CTRL4" \
  bash "$RUNNER" >/dev/null 2>&1
RC=$?
[ $RC -eq 0 ] && [ "$(cat "$CTRL4.out" 2>/dev/null)" = "sourced-ok" ] \
  && grep -q "OK" "$OUT4" \
  && pass "T4: env sourced + controller --once ran clean" || fail "T4: rc=$RC out=$(cat "$CTRL4.out" 2>/dev/null)"

echo "== T5 runner mirrors the controller exit code =="
CTRL5="$WORK/controller5.py"; printf 'import sys; sys.exit(3)\n' > "$CTRL5"
OUT5="$WORK/t5.log"
HOME="$WORK" PODCAST_SCHEDULER_LOG="$OUT5" PODCAST_SCHEDULER_LOCKDIR="$WORK/t5.lock" \
  PODCAST_CONTROLLER_PATH="$CTRL5" bash "$RUNNER" >/dev/null 2>&1
RC=$?
[ $RC -eq 3 ] && grep -q "exit=3" "$OUT5" && pass "T5: exit code mirrored (3)" || fail "T5: rc=$RC"

echo "== T6 single-instance lock: overlapping tick yields =="
CTRL6="$WORK/controller6.py"; printf 'import sys; sys.exit(0)\n' > "$CTRL6"
LOCK6="$WORK/t6.lock"; mkdir -p "$LOCK6"
OUT6="$WORK/t6.log"
HOME="$WORK" PODCAST_SCHEDULER_LOG="$OUT6" PODCAST_SCHEDULER_LOCKDIR="$LOCK6" \
  PODCAST_CONTROLLER_PATH="$CTRL6" bash "$RUNNER" >/dev/null 2>&1
RC=$?
[ $RC -eq 0 ] && grep -q "SKIP" "$OUT6" && pass "T6: held lock -> SKIP, controller not run" || fail "T6: rc=$RC"

echo "== T7 installer cron.d mode under a prefix (idempotent) =="
ROOT7="$WORK/root7"
env HOME="$WORK" PODCAST_SCHEDULER_ROOT="$ROOT7" PODCAST_SCHEDULER_FORCE="cron.d" \
  PODCAST_NODE_USER="node" bash "$INSTALLER" >/dev/null 2>&1
RC=$?
INSTALLED_RUNNER="$ROOT7/usr/local/bin/podcast-scheduler-runner.sh"
INSTALLED_CRON="$ROOT7/etc/cron.d/podcast-scheduler"
if [ $RC -eq 0 ] && [ -f "$INSTALLED_RUNNER" ] && [ -x "$INSTALLED_RUNNER" ] && [ -f "$INSTALLED_CRON" ]; then
  pass "T7a: runner + cron.d entry installed"
else
  fail "T7a: rc=$RC runner=$([ -f "$INSTALLED_RUNNER" ] && echo y || echo n) cron=$([ -f "$INSTALLED_CRON" ] && echo y || echo n)"
fi
grep -q "^\*/5 \* \* \* \* node $INSTALLED_RUNNER$" "$INSTALLED_CRON" \
  && pass "T7b: entry is every-5-min as node, pointing at the runner" || fail "T7b: entry shape"
SUM1=$(shasum "$INSTALLED_RUNNER" "$INSTALLED_CRON" 2>/dev/null || sha256sum "$INSTALLED_RUNNER" "$INSTALLED_CRON")
env HOME="$WORK" PODCAST_SCHEDULER_ROOT="$ROOT7" PODCAST_SCHEDULER_FORCE="cron.d" \
  PODCAST_NODE_USER="node" bash "$INSTALLER" >/dev/null 2>&1
RC=$?
SUM2=$(shasum "$INSTALLED_RUNNER" "$INSTALLED_CRON" 2>/dev/null || sha256sum "$INSTALLED_RUNNER" "$INSTALLED_CRON")
[ $RC -eq 0 ] && [ "$SUM1" = "$SUM2" ] && pass "T7c: re-run is a no-op (idempotent)" || fail "T7c: rc=$RC or artifact churn"
env HOME="$WORK" PODCAST_SCHEDULER_ROOT="$ROOT7" PODCAST_SCHEDULER_FORCE="cron.d" \
  bash "$INSTALLER" --check >/dev/null 2>&1 \
  && pass "T7d: --check reports ACTIVE (exit 0)" || fail "T7d: --check"

echo "== T8 --check before install exits non-zero =="
ROOT8="$WORK/root8"
env HOME="$WORK" PODCAST_SCHEDULER_ROOT="$ROOT8" PODCAST_SCHEDULER_FORCE="cron.d" \
  bash "$INSTALLER" --check >/dev/null 2>&1
[ $? -ne 0 ] && pass "T8: --check exit non-zero when absent" || fail "T8"

echo "== T9 shipped cron.d entry matches the repo cron idiom =="
LINE9=$(grep -v '^#' "$CRON_ENTRY" | grep -v '^[[:space:]]*$' | head -1)
NFIELDS=$(printf '%s\n' "$LINE9" | awk '{print NF}')
SCHED=$(printf '%s\n' "$LINE9" | awk '{print $1" "$2" "$3" "$4" "$5}')
[ "$NFIELDS" -eq 7 ] && [ "$SCHED" = "*/5 * * * *" ] \
  && pass "T9: 5 schedule fields + user + command, every 5 min" || fail "T9: '$LINE9'"
python3 - "$PLIST_TEMPLATE" <<'EOF' && pass "T9b: launchd template renders to a valid plist" || fail "T9b: plist render"
import plistlib, sys, tempfile, os
tpl = open(sys.argv[1], encoding="utf-8").read()
rendered = tpl.replace("PODCAST_SCHEDULER_RUNNER_PATH", "/usr/local/bin/podcast-scheduler-runner.sh").replace("PODCAST_SCHEDULER_HOME", "/home/node")
assert "PODCAST_SCHEDULER_RUNNER_PATH" not in rendered and "PODCAST_SCHEDULER_HOME" not in rendered
with tempfile.NamedTemporaryFile(suffix=".plist", delete=False) as fh:
    fh.write(rendered.encode("utf-8")); path = fh.name
try:
    with open(path, "rb") as fh:
        d = plistlib.load(fh)
    assert d["Label"] == "com.openclaw.podcast-scheduler"
    assert d["StartInterval"] == 300
finally:
    os.unlink(path)
EOF

echo "== T10 guard recognizes the box-level scheduler tick =="
INV="$WORK/inventory.json"
cat > "$INV" <<'EOF'
[
  {"name": "podcast-scheduler", "schedule": "*/5 * * * *", "command": "podcast_scheduler_runner.sh", "client": "box"},
  {"name": "podcast-smoke-test-acme", "schedule": "12 6 * * *", "delivery": "silent", "client": "acme"}
]
EOF
"$PY" "$GUARD" --inventory "$INV" --json > "$WORK/t10.json" 2>/dev/null
"$PY" - "$WORK/t10.json" <<'EOF' && pass "T10a: tick recognized, census intact, sweep-clean" || fail "T10a"
import json, sys
d = json.load(open(sys.argv[1]))
assert d["pass"] is True, d
assert d["extra"]["scheduler_recognized"] == 1, d
assert d["findings"] == [], d
EOF
cat > "$WORK/inv2.json" <<'EOF'
[
  {"name": "podcast-scheduler", "schedule": "*/5 * * * *", "command": "runner"},
  {"name": "podcast-scheduler", "schedule": "*/5 * * * *", "command": "runner-copy"}
]
EOF
"$PY" "$GUARD" --inventory "$WORK/inv2.json" --json > "$WORK/t10b.json" 2>/dev/null
grep -q "more-than-one-box-scheduler-tick" "$WORK/t10b.json" \
  && pass "T10b: two ticks fail as a furnace" || fail "T10b"
cat > "$WORK/inv3.json" <<'EOF'
[{"name": "podcast-scheduler", "kind": "poller", "schedule": "*/5 * * * *", "client": "acme"}]
EOF
"$PY" "$GUARD" --inventory "$WORK/inv3.json" --json > "$WORK/t10c.json" 2>/dev/null
grep -q "queue-poller-or-watcher" "$WORK/t10c.json" \
  && pass "T10c: poller-shaped impostor still fails" || fail "T10c"

echo "== T11 style: zero em dashes, no triple-backtick fences =="
# The em dash is built from octals so this test file itself stays em-dash-free.
EM_DASH="$(printf '\342\200\224')"
EMDASH=0
for f in "$RUNNER" "$INSTALLER" "$CRON_ENTRY" "$PLIST_TEMPLATE" "$GUARD" "$REPO_ROOT/58-podcast-production-engine/SCHEDULER.md"; do
  if grep -q "$EM_DASH" "$f" 2>/dev/null; then EMDASH=1; fail "T11: em dash in $(basename "$f")"; fi
done
[ $EMDASH -eq 0 ] && pass "T11a: zero em dashes in all unit files"
# Build the triple-backtick pattern from characters so this test stays fence-free.
FENCE="$(printf '\140\140\140')"
if grep -q "$FENCE" "$REPO_ROOT/58-podcast-production-engine/SCHEDULER.md"; then
  fail "T11b: fence in SCHEDULER.md"
else
  pass "T11b: SCHEDULER.md fence-free"
fi

echo
echo "== podcast-scheduler unit test: PASS=$PASS FAIL=$FAIL =="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
