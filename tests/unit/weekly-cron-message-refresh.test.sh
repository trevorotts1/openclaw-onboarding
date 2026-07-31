#!/usr/bin/env bash
# tests/unit/weekly-cron-message-refresh.test.sh
#
# Proves the WEEKLY-CRON-FULL-REGISTRATION-V1 / WEEKLY-CRON-MESSAGE-REFRESH-V1
# blocks in update-skills.sh close the "cron content drift" bug: an EXISTING
# weekly-onboarding-update cron used to be a permanent no-op once created --
# cron-prompt.txt could gain new RULES (e.g. RULE 5.6, added 2026-07-30)
# forever without a single already-provisioned box ever seeing them, because
# only an ABSENT job or one with old auto-announce wiring ever got a fresh
# payload. This suite runs the REAL extracted registration code (not a
# reimplementation) against a self-contained fake `openclaw` + `curl` so the
# actual bash logic -- including its `set -euo pipefail` safety -- is what
# gets proven, exactly like tests/unit/fleet-standing-gate.test.sh does for
# the FLEET-STANDING-GATE-V1 block.
#
# The single most important property under test is FAIL-SAFE-ON-REFRESH: a
# fetch failure, an unreadable job, or a rejected edit must leave the OLD
# message in place and let the update continue -- never abort, never blank
# the payload. A regression here would either freeze the weekly update-check
# fleet-wide the moment GitHub raw hiccups, or (worse) wipe a client's cron
# message to empty.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/update-skills.sh"
CRON_LIB="$REPO_ROOT/shared-utils/cron-lib.sh"
PASS=0; FAIL=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

# --- extract the full registration block so we exercise real production code ---
BLOCK="$TMP/registration.sh"
awk '/^    #=== BEGIN WEEKLY-CRON-FULL-REGISTRATION-V1 ===$/,/^    #=== END WEEKLY-CRON-FULL-REGISTRATION-V1 ===$/' "$SRC" > "$BLOCK"
if [ ! -s "$BLOCK" ]; then
  echo "FAIL: could not extract WEEKLY-CRON-FULL-REGISTRATION-V1 block from $SRC"; exit 1
fi
bash -n "$BLOCK" || { echo "FAIL: extracted registration block is not valid bash"; exit 1; }
[ -f "$CRON_LIB" ] || { echo "FAIL: shared-utils/cron-lib.sh not found"; exit 1; }

# --- a fake `openclaw` CLI: a tiny JSON job store on disk we fully control ---
FAKEBIN="$TMP/bin"
mkdir -p "$FAKEBIN"
STATE="$TMP/jobs.json"
CALLS="$TMP/calls.log"

cat > "$FAKEBIN/openclaw" <<'PYEOF'
#!/usr/bin/env python3
"""Fake `openclaw` for weekly-cron-message-refresh.test.sh -- a self-contained
JSON job store simulating exactly the surface this suite's target code calls:
cron list --json/--help, cron get <id>, cron edit <id> [--message|--system-event],
cron add/create --help + create, cron delete --name. Not the shared
tests/fixtures/fake-openclaw-cron.py fixture (that one's `edit`/`delete` are
deliberate no-ops for a different suite) -- this is scoped to this test only.
"""
import json, os, sys

STATE = os.environ["FAKE_OC_STATE"]
CALLS = os.environ["FAKE_OC_CALLS"]


def log(argv):
    with open(CALLS, "a") as f:
        f.write(" ".join(argv) + "\n")


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return []


def save(jobs):
    with open(STATE, "w") as f:
        json.dump(jobs, f)


def parse_flags(rest):
    d = {}
    bools = {"--exact", "--light-context", "--no-deliver", "--best-effort-deliver", "--json", "--all"}
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in bools:
            d[a] = True
            i += 1
        elif a.startswith("--"):
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                d[a] = rest[i + 1]
                i += 2
            else:
                d[a] = True
                i += 1
        else:
            i += 1
    return d


def cmd_cron(rest):
    sub = rest[0] if rest else ""
    args = rest[1:]

    if sub in ("add", "create"):
        if "--help" in args:
            sys.stdout.write(
                "--name <name>  --agent <id>  --cron <expr>  --tz <iana>\n"
                "--session <target>  --system-event <text>  --message <text>\n"
                "--description <text>  --exact  --light-context  --thinking <level>\n"
                "--timeout-seconds <n>  --no-deliver\n"
            )
            return 0
        flags = parse_flags(args)
        if not flags.get("--name"):
            return 1
        jobs = load()
        job = {
            "id": "fake-%03d" % (len(jobs) + 1),
            "name": flags["--name"],
            "delivery": {"mode": "none", "channel": None, "to": None},
            "payload": {"kind": "", "message": None, "systemEvent": None},
            "schedule": {"expr": flags.get("--cron", ""), "tz": flags.get("--tz", "")},
        }
        if "--system-event" in flags:
            job["payload"]["kind"] = "systemEvent"
            job["payload"]["systemEvent"] = flags["--system-event"]
        elif "--message" in flags:
            job["payload"]["kind"] = "agentTurn"
            job["payload"]["message"] = flags["--message"]
        jobs.append(job)
        save(jobs)
        return 0

    if sub == "list":
        if "--help" in args:
            sys.stdout.write("--agent <id>  --json  --all\n")
            return 0
        jobs = load()
        if "--json" in args:
            sys.stdout.write(json.dumps({"jobs": jobs}))
        return 0

    if sub == "get":
        if not args:
            return 1
        jid = args[0]
        for j in load():
            if j.get("id") == jid:
                if os.environ.get("FAKE_OC_GET_FAIL") == "1":
                    return 1
                sys.stdout.write(json.dumps(j))
                return 0
        return 1

    if sub == "edit":
        if not args:
            return 1
        jid = args[0]
        flags = parse_flags(args[1:])
        if os.environ.get("FAKE_OC_EDIT_FAIL") == "1":
            return 1
        jobs = load()
        found = False
        for j in jobs:
            if j.get("id") == jid:
                found = True
                if "--system-event" in flags:
                    j["payload"]["kind"] = "systemEvent"
                    j["payload"]["systemEvent"] = flags["--system-event"]
                elif "--message" in flags:
                    j["payload"]["kind"] = "agentTurn"
                    j["payload"]["message"] = flags["--message"]
        if not found:
            return 1
        save(jobs)
        return 0

    if sub == "delete":
        flags = parse_flags(args)
        name = flags.get("--name")
        jobs = [j for j in load() if j.get("name") != name]
        save(jobs)
        return 0

    return 0


def main():
    argv = sys.argv[1:]
    log(argv)
    if argv and argv[0] == "cron":
        return cmd_cron(argv[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$FAKEBIN/openclaw"

# --- a fake `curl` simulating the raw.githubusercontent.com cron-prompt.txt fetch ---
cat > "$FAKEBIN/curl" <<'BASHEOF'
#!/usr/bin/env bash
# Recognizes only the shape update-skills.sh actually uses:
#   curl -fsSL --max-time N <url> -o <file>
out=""
args=( "$@" )
for ((i=0; i<${#args[@]}; i++)); do
  if [ "${args[$i]}" = "-o" ]; then
    out="${args[$((i+1))]}"
  fi
done
if [ "${FAKE_CURL_FAIL:-0}" = "1" ]; then
  exit 1
fi
if [ -n "$out" ]; then
  cp "$FAKE_CURL_CONTENT_FILE" "$out"
fi
exit 0
BASHEOF
chmod +x "$FAKEBIN/curl"

seed_state() { printf '%s' "$1" > "$STATE"; }
job_field() {
  # job_field <id> <dotted.path> -- reads back from $STATE via python3
  python3 - "$STATE" "$1" "$2" <<'PYEOF'
import json, sys
state, jid, path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    jobs = json.load(open(state))
except Exception:
    jobs = []
for j in jobs:
    if j.get("id") == jid:
        cur = j
        for p in path.split("."):
            cur = (cur or {}).get(p)
        print(cur if cur is not None else "")
        sys.exit(0)
print("")
PYEOF
}
job_count() { python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$STATE" 2>/dev/null || echo 0; }

run_registration() {
  ( set -euo pipefail
    export PATH="$FAKEBIN:$PATH"
    export FAKE_OC_STATE="$STATE"
    export FAKE_OC_CALLS="$CALLS"
    # These are only ever set (non-exported) as prefix assignments by callers
    # of this function -- fork inheritance makes them visible to bash CODE in
    # this subshell either way, but the fake `curl`/`openclaw` are separate
    # EXECUTABLES reached via exec(), which only inherit EXPORTED vars. Export
    # them here (with safe defaults so `set -u` never trips on an unset one).
    export FAKE_CURL_CONTENT_FILE="${FAKE_CURL_CONTENT_FILE:-}"
    export FAKE_CURL_FAIL="${FAKE_CURL_FAIL:-0}"
    export FAKE_OC_GET_FAIL="${FAKE_OC_GET_FAIL:-0}"
    export FAKE_OC_EDIT_FAIL="${FAKE_OC_EDIT_FAIL:-0}"
    # shellcheck source=/dev/null
    source "$CRON_LIB"
    # shellcheck source=/dev/null
    source "$BLOCK"
    echo "__REACHED_END__"
  ) 2>&1
}

# NOTE: `grep -c` PRINTS "0" (reliably) even on zero matches -- it only ever
# exits nonzero in that case, which is irrelevant here since we only read its
# stdout. An `|| echo 0` fallback would fire on that same "0 matches" exit
# and print a SECOND "0" line, corrupting the count -- deliberately absent.
edit_call_count() { grep -c '^cron edit ' "$CALLS" 2>/dev/null; }
create_call_count() { grep -cE '^cron (add|create) ' "$CALLS" 2>/dev/null; }

echo "== (a) job ABSENT -> created fresh from cron-prompt.txt =="
: > "$CALLS"; seed_state '[]'
echo -n "RULES V1 CONTENT" > "$TMP/content.txt"
FAKE_CURL_CONTENT_FILE="$TMP/content.txt" out="$(run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "absent-job run reaches end (no abort)" || bad "absent-job run should reach end: $out"
[ "$(job_count)" = "1" ] && ok "absent-job run creates exactly one job" || bad "expected exactly 1 job, got $(job_count)"
NEW_ID=$(python3 -c "import json; print(json.load(open('$STATE'))[0]['id'])" 2>/dev/null || echo "")
CONTENT_NOW=$(job_field "$NEW_ID" "payload.systemEvent")
[ "$CONTENT_NOW" = "RULES V1 CONTENT" ] && ok "created job's payload carries the fetched cron-prompt.txt content" || bad "created job content mismatch: got [$CONTENT_NOW]"
[ "$(edit_call_count)" = "0" ] && ok "absent-job path never calls cron edit" || bad "absent-job path should never call cron edit"

echo "== (b) job EXISTS with STALE content -> message refreshed in place =="
: > "$CALLS"
seed_state '[{"id":"j1","name":"weekly-onboarding-update","delivery":{"mode":"none","channel":null,"to":null},"payload":{"kind":"agentTurn","message":"OLD STALE CONTENT"},"schedule":{"expr":"0 3 * * 0","tz":"America/New_York"}}]'
echo -n "NEW FRESH CONTENT" > "$TMP/content.txt"
FAKE_CURL_CONTENT_FILE="$TMP/content.txt" out="$(run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "stale-content run reaches end" || bad "stale-content run should reach end: $out"
[ "$(job_field j1 payload.message)" = "NEW FRESH CONTENT" ] && ok "stale message refreshed to current cron-prompt.txt content" || bad "message not refreshed: $(job_field j1 payload.message)"
[ "$(job_field j1 schedule.expr)" = "0 3 * * 0" ] && ok "schedule untouched by the refresh" || bad "schedule was altered by a message-only refresh"
[ "$(job_field j1 schedule.tz)" = "America/New_York" ] && ok "timezone untouched by the refresh" || bad "timezone was altered by a message-only refresh"
[ "$(job_field j1 delivery.mode)" = "none" ] && ok "delivery untouched by the refresh" || bad "delivery was altered by a message-only refresh"
[ "$(create_call_count)" = "0" ] && ok "present-job refresh never calls cron add/create" || bad "present-job refresh should never call cron create"

echo "== (c) job EXISTS with IDENTICAL content -> idempotent, no rewrite =="
: > "$CALLS"
seed_state '[{"id":"j1","name":"weekly-onboarding-update","delivery":{"mode":"none","channel":null,"to":null},"payload":{"kind":"agentTurn","message":"SAME CONTENT AS REPO"},"schedule":{"expr":"0 3 * * 0","tz":"America/New_York"}}]'
echo -n "SAME CONTENT AS REPO" > "$TMP/content.txt"
FAKE_CURL_CONTENT_FILE="$TMP/content.txt" out="$(run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "identical-content run reaches end" || bad "identical-content run should reach end: $out"
[ "$(edit_call_count)" = "0" ] && ok "identical content triggers NO cron edit call (idempotent)" || bad "identical content should not call cron edit"
[[ "$out" == *"already current, no rewrite needed"* ]] && ok "logs the no-rewrite-needed message" || bad "missing no-rewrite-needed log line: $out"
# Run it again -- a second identical pass must be equally inert.
out2="$(FAKE_CURL_CONTENT_FILE="$TMP/content.txt" run_registration)"
[[ "$out2" == *"__REACHED_END__"* ]] && ok "second identical run also reaches end" || bad "second identical run should reach end: $out2"
[ "$(edit_call_count)" = "0" ] && ok "two consecutive identical runs still call cron edit zero times" || bad "repeated runs should stay at 0 edits, got $(edit_call_count)"

echo "== (d) FETCH FAILS or returns EMPTY -> nothing changes, script continues (most important case) =="

echo "-- (d1) curl fails outright --"
: > "$CALLS"
seed_state '[{"id":"j1","name":"weekly-onboarding-update","delivery":{"mode":"none","channel":null,"to":null},"payload":{"kind":"agentTurn","message":"ORIGINAL CONTENT"},"schedule":{"expr":"0 3 * * 0","tz":"America/New_York"}}]'
echo -n "SHOULD NEVER BE APPLIED" > "$TMP/content.txt"
out="$(FAKE_CURL_CONTENT_FILE="$TMP/content.txt" FAKE_CURL_FAIL=1 run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "curl failure still reaches end (update not aborted)" || bad "curl failure must not abort the update: $out"
[ "$(job_field j1 payload.message)" = "ORIGINAL CONTENT" ] && ok "curl failure leaves the OLD message in place (never blanked)" || bad "message must be unchanged on curl failure: $(job_field j1 payload.message)"
[ "$(edit_call_count)" = "0" ] && ok "curl failure never calls cron edit" || bad "curl failure should never call cron edit"

echo "-- (d2) curl succeeds but returns an EMPTY file --"
: > "$CALLS"
seed_state '[{"id":"j1","name":"weekly-onboarding-update","delivery":{"mode":"none","channel":null,"to":null},"payload":{"kind":"agentTurn","message":"ORIGINAL CONTENT"},"schedule":{"expr":"0 3 * * 0","tz":"America/New_York"}}]'
: > "$TMP/empty.txt"
out="$(FAKE_CURL_CONTENT_FILE="$TMP/empty.txt" run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "empty fetch still reaches end" || bad "empty fetch must not abort the update: $out"
[ "$(job_field j1 payload.message)" = "ORIGINAL CONTENT" ] && ok "empty fetch leaves the OLD message in place" || bad "message must be unchanged on empty fetch: $(job_field j1 payload.message)"
[ "$(edit_call_count)" = "0" ] && ok "empty fetch never calls cron edit" || bad "empty fetch should never call cron edit"

echo "-- (d3) fetch succeeds but 'openclaw cron get' fails (gateway hiccup) --"
: > "$CALLS"
seed_state '[{"id":"j1","name":"weekly-onboarding-update","delivery":{"mode":"none","channel":null,"to":null},"payload":{"kind":"agentTurn","message":"ORIGINAL CONTENT"},"schedule":{"expr":"0 3 * * 0","tz":"America/New_York"}}]'
echo -n "NEW CONTENT" > "$TMP/content.txt"
out="$(FAKE_CURL_CONTENT_FILE="$TMP/content.txt" FAKE_OC_GET_FAIL=1 run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "cron-get failure still reaches end" || bad "cron-get failure must not abort the update: $out"
[ "$(job_field j1 payload.message)" = "ORIGINAL CONTENT" ] && ok "cron-get failure leaves the OLD message in place" || bad "message must be unchanged when cron get fails: $(job_field j1 payload.message)"
[ "$(edit_call_count)" = "0" ] && ok "cron-get failure never calls cron edit" || bad "cron-get failure should never call cron edit"

echo "-- (d4) fetch + read succeed but 'openclaw cron edit' is REJECTED (the worst case: never leave a blank payload) --"
: > "$CALLS"
seed_state '[{"id":"j1","name":"weekly-onboarding-update","delivery":{"mode":"none","channel":null,"to":null},"payload":{"kind":"agentTurn","message":"ORIGINAL CONTENT"},"schedule":{"expr":"0 3 * * 0","tz":"America/New_York"}}]'
echo -n "NEW CONTENT" > "$TMP/content.txt"
out="$(FAKE_CURL_CONTENT_FILE="$TMP/content.txt" FAKE_OC_EDIT_FAIL=1 run_registration)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "rejected edit still reaches end" || bad "rejected edit must not abort the update: $out"
[ "$(job_field j1 payload.message)" = "ORIGINAL CONTENT" ] && ok "rejected edit leaves the OLD message in place (never blank/partial)" || bad "message must be unchanged when edit is rejected: $(job_field j1 payload.message)"
[[ "$out" == *"WARN"* ]] && ok "rejected edit logs a WARN (visible, not silent)" || bad "rejected edit should log a WARN: $out"

echo "== (e) job EXISTS, no old wiring, python3 UNAVAILABLE -> refresh path must not abort (v21.4.41 fix: \$_OC_RAW_JSON unbound-variable regression) =="
# _OC_RAW_JSON is only ever assigned inside `if command -v python3 ...; then`
# a few lines above (the old-wiring detector). oc_cron_present only needs ONE
# of jq/python3 to confirm the job is present, so a box with jq but genuinely
# NO python3 reaches this "already installed" branch with _OC_RAW_JSON never
# assigned at all. The refresh sub-block used to reference $_OC_RAW_JSON
# completely outside that guard -- an unbound-variable abort under
# `set -euo pipefail` on exactly that box shape. This subtest forces the
# shape directly: oc_cron_present() overridden to report "present" (so we hit
# the branch) with NO python3 anywhere on PATH, proving the block reaches the
# end and falls back to the SKIP log line instead of dying.
NOPY_BIN="$TMP/bin-nopython3"
mkdir -p "$NOPY_BIN"
NOPY_CALLS="$TMP/nopy-calls.log"
: > "$NOPY_CALLS"
cat > "$NOPY_BIN/openclaw" <<EOF
#!/bin/bash
echo "\$@" >> "$NOPY_CALLS"
exit 0
EOF
chmod +x "$NOPY_BIN/openclaw"

run_registration_no_python3() {
  ( set -euo pipefail
    export PATH="$NOPY_BIN"
    # shellcheck source=/dev/null
    source "$CRON_LIB"
    # Simulate a box where the job is confirmed present (e.g. via jq) but
    # python3 is genuinely absent -- override AFTER sourcing cron-lib.sh so
    # this replaces its real jq/python3-probing implementation outright.
    oc_cron_present() { return 0; }
    # shellcheck source=/dev/null
    source "$BLOCK"
    echo "__REACHED_END__"
  ) 2>&1
}

out="$(run_registration_no_python3)"
[[ "$out" == *"__REACHED_END__"* ]] && ok "python3-unavailable run reaches end (no unbound-variable abort)" || bad "python3-unavailable run must not abort: $out"
[[ "$out" == *"unbound variable"* || "$out" == *"parameter not set"* ]] && bad "python3-unavailable run must NEVER hit an unbound/unset parameter error: $out" || ok "no unbound-variable error surfaced"
[[ "$out" == *"could not resolve job id for weekly-onboarding-update"* ]] && ok "falls back to the SKIP log line when python3 is unavailable to resolve the job id" || bad "expected the no-python3 SKIP log line: $out"
[ ! -s "$NOPY_CALLS" ] && ok "python3-unavailable path never shells out to openclaw at all" || bad "unexpected openclaw call(s) in python3-unavailable path: $(cat "$NOPY_CALLS")"

echo
echo "passed=$PASS failed=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
