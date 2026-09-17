#!/usr/bin/env bash
# =============================================================================
# cc-watchdog-cron-registration.test.sh  (ISSUE-04)
#
# THE DEFECT THIS LOCKS. blackceo-command-center ships scripts/watchdog-cc.sh -
# the */5 self-heal for pm2 crash loops, EADDRINUSE, duplicate/legacy app-name
# zombies, cc-start.sh stale-build refusal receipts and the scheduler-stalled
# class - and NOTHING in this repo ever scheduled it. The only mention was a
# passing reference inside a comment in run-full-install.sh;
# mac-mini-bootstrap.sh registers the pm2 launchd job and nothing else. The
# watchdog therefore shipped to every box and fired on none: a live client Mac
# read "healthy" for 41 hours with no card moving until an operator restarted
# pm2 by hand. A self-heal that nothing schedules is the same as no self-heal.
#
# WHAT IS UNDER TEST. run-full-install.sh's cc_register_watchdog_cron and its
# three helpers, extracted VERBATIM from the real installer by name-anchored awk
# (no reimplementation), driven against a fake `openclaw` CLI backed by a JSON
# store. Plus static assertions that the registrar is actually CALLED, in a
# position that runs on both a full install and an --update-only refresh.
#
#   T0  the registrar, its helpers and its three constants are extractable.
#   T1  STATIC: cc_register_watchdog_cron is CALLED at top level, after the
#       Phase 6 block and before Phase 6h - i.e. on both install and update.
#   T2  STATIC: schedule is */5, declaration key is skill32-cc-watchdog, and
#       the env contract is exactly the three variables watchdog-cc.sh reads.
#   T3  fresh register on a modern CLI: exactly ONE job, right name/schedule/
#       key, delivery none, env passed, and the payload is a SINGLE plain
#       command string (no ';', no '||', no inline VAR= prefix).
#   T4  idempotent: running it twice leaves exactly ONE job.
#   T5  a pre-existing DISABLED job is re-enabled.
#   T6  a TOMBSTONED name is never re-registered.
#   T7  watchdog-cc.sh absent (older CC pin): clean skip, rc 0, logged.
#   T8  no openclaw CLI: loud PENDING, rc 0, install not failed.
#   T9  CLI without --command-env: wrapper written to
#       $OC_ROOT/scripts/cc-watchdog-run.sh, executable, exports the three
#       variables, and the cron payload stays a single plain command.
#   T10 CLI without --declaration-key: remove-then-add still ends at ONE job.
#   T11 `openclaw cron add` failing: loud PENDING, rc 0 (fail-soft posture).
#
# Hermetic: temp HOME/OC_ROOT/checkout, a fake `openclaw` on PATH. No network,
# no gateway, no pm2, no credentials, no box is touched.
# =============================================================================
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
INSTALLER="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

[ -f "$INSTALLER" ] || { echo "FATAL: installer not found at $INSTALLER"; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required"; exit 2; }

PASS=0; FAIL=0
ok()  { printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# T0 - extract the code under test verbatim from the real installer
# ---------------------------------------------------------------------------
extract_func() {
  local name="$1" file="$2"
  awk -v pat="^${name}\\\\(\\\\) \\\\{" '
    $0 ~ pat { p=1 }
    p { print }
    p && /^}/ { exit }
  ' "$file"
}

FRAG="$SANDBOX/frag.sh"
: > "$FRAG"

hdr "T0 - registrar + helpers + constants extractable from the real installer"
MISSING=0
CONSTS="$(grep -E '^CC_WATCHDOG_CRON_(NAME|DECL|EXPR)=' "$INSTALLER" || true)"
if [ "$(printf '%s\n' "$CONSTS" | grep -c 'CC_WATCHDOG_CRON_')" -eq 3 ]; then
  printf '%s\n\n' "$CONSTS" >> "$FRAG"
else
  bad "T0: expected 3 CC_WATCHDOG_CRON_* constants in the installer"
  MISSING=$((MISSING+1))
fi
for fn in cc_cron_add_supports cc_watchdog_cron_lookup cc_watchdog_write_wrapper cc_register_watchdog_cron; do
  body="$(extract_func "$fn" "$INSTALLER")"
  if [ -z "$body" ]; then
    bad "T0: could not extract '$fn' from the installer (missing, or name/shape drift)"
    MISSING=$((MISSING+1))
  else
    printf '%s\n\n' "$body" >> "$FRAG"
  fi
done
[ "$MISSING" -eq 0 ] && ok "T0: 4 functions + 3 constants extracted verbatim"

# ---------------------------------------------------------------------------
# T1/T2 - static contract assertions against the installer source
# ---------------------------------------------------------------------------
hdr "T1 - the registrar is CALLED on both the install and the update path"
CALL_LN="$(grep -n '^cc_register_watchdog_cron$' "$INSTALLER" | head -1 | cut -d: -f1)"
# Anchored WITHOUT the em dash that follows "PHASE 6" in the source: a '.'
# there matches one BYTE under LANG=C, and an em dash is three, so the anchor
# would silently miss on a C-locale CI runner.
P6_LN="$(grep -n '^# PHASE 6 ' "$INSTALLER" | head -1 | cut -d: -f1)"
P6H_LN="$(grep -n '^# PHASE 6h ' "$INSTALLER" | head -1 | cut -d: -f1)"
if [ -z "$CALL_LN" ]; then
  bad "T1: run-full-install.sh never CALLS cc_register_watchdog_cron at top level - the watchdog is defined but still unscheduled"
elif [ -z "$P6_LN" ] || [ -z "$P6H_LN" ]; then
  bad "T1: could not locate the Phase 6 / Phase 6h anchors (installer layout drift)"
elif [ "$CALL_LN" -gt "$P6_LN" ] && [ "$CALL_LN" -lt "$P6H_LN" ]; then
  ok "T1: called at line $CALL_LN, after Phase 6 ($P6_LN) and before Phase 6h ($P6H_LN) - outside the update-only/full branch, so it runs in every mode"
else
  bad "T1: the call at line $CALL_LN is outside the Phase 6 -> Phase 6h window ($P6_LN..$P6H_LN); it may not run on both paths"
fi

# The call must NOT sit inside the `if [[ "$UPDATE_ONLY" == "true" ]]` phase-6
# branch, which would make it update-only or install-only. An unindented call
# between the two anchors is at top level by construction (the phase-6 block
# closes with an unindented `fi` before it), so verify that `fi` is there.
if [ -n "$CALL_LN" ] && [ -n "$P6_LN" ]; then
  if awk -v a="$P6_LN" -v b="$CALL_LN" 'NR>a && NR<b && /^fi$/ {found=1} END{exit found?0:1}' "$INSTALLER"; then
    ok "T1: the phase-6 if/elif/else closes before the call, so all three branches converge on it"
  else
    bad "T1: no top-level 'fi' between the Phase 6 header and the call - the call may be nested inside a mode branch"
  fi
fi

hdr "T2 - schedule, declaration key and env contract are pinned"
grep -q '^CC_WATCHDOG_CRON_EXPR="\*/5 \* \* \* \*"$' "$INSTALLER" \
  && ok "T2: schedule is */5 * * * *" \
  || bad "T2: schedule is not */5 * * * *"
grep -q '^CC_WATCHDOG_CRON_NAME="cc-watchdog"$' "$INSTALLER" \
  && ok "T2: job name is cc-watchdog" \
  || bad "T2: job name is not cc-watchdog"
grep -q '^CC_WATCHDOG_CRON_DECL="skill32-cc-watchdog"$' "$INSTALLER" \
  && ok "T2: declaration key is skill32-cc-watchdog" \
  || bad "T2: declaration key is not skill32-cc-watchdog"
# The env contract is what watchdog-cc.sh actually reads. Locked here so a
# rename on either side is caught instead of silently producing a watchdog that
# runs with defaults (self-heal OFF, port 4000, canonical dir unset).
for v in WATCHDOG_SELF_HEAL WATCHDOG_PORT WATCHDOG_CANONICAL_DIR; do
  grep -q "$v" "$INSTALLER" && ok "T2: $v is passed to the watchdog" || bad "T2: $v is NOT passed to the watchdog"
done

# ---------------------------------------------------------------------------
# Fake openclaw CLI
# ---------------------------------------------------------------------------
FAKE_BIN="$SANDBOX/bin"
mkdir -p "$FAKE_BIN"
FAKE_PY="$SANDBOX/fake-oc.py"

cat > "$FAKE_PY" <<'PYFAKE'
import json, os, sys, uuid

store = os.environ["FAKE_OC_STORE"]

def load():
    try:
        with open(store, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"jobs": []}

def save(data):
    with open(store, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)

op = sys.argv[1]
args = sys.argv[2:]
data = load()

if op == "add":
    job = {"name": None, "declKey": None, "cron": None, "command": None,
           "env": [], "delivery": "last", "enabled": True}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--name":
            job["name"] = args[i + 1]; i += 2
        elif a == "--cron":
            job["cron"] = args[i + 1]; i += 2
        elif a == "--declaration-key":
            job["declKey"] = args[i + 1]; i += 2
        elif a == "--command":
            job["command"] = args[i + 1]; i += 2
        elif a == "--command-env":
            job["env"].append(args[i + 1]); i += 2
        elif a == "--no-deliver":
            job["delivery"] = "none"; i += 1
        else:
            i += 1
    if job["declKey"]:
        for existing in data["jobs"]:
            if existing.get("declKey") == job["declKey"]:
                for k, v in job.items():
                    if k != "enabled":
                        existing[k] = v
                save(data)
                print("converged")
                sys.exit(0)
    job["id"] = str(uuid.uuid4())
    data["jobs"].append(job)
    save(data)
    print("created")
    sys.exit(0)

if op == "list":
    include_disabled = "--all" in args
    jobs = [j for j in data["jobs"] if include_disabled or j.get("enabled", True)]
    print(json.dumps({"jobs": jobs}))
    sys.exit(0)

if op == "rm":
    target = args[0] if args else ""
    before = len(data["jobs"])
    data["jobs"] = [j for j in data["jobs"] if j.get("id") != target]
    save(data)
    sys.exit(0 if len(data["jobs"]) < before else 1)

if op == "enable":
    target = args[0] if args else ""
    for j in data["jobs"]:
        if j.get("id") == target:
            j["enabled"] = True
            save(data)
            sys.exit(0)
    sys.exit(1)

sys.exit(2)
PYFAKE

cat > "$FAKE_BIN/openclaw" <<'FAKEOC'
#!/usr/bin/env bash
set -u
[ "${1:-}" = "cron" ] || { echo "fake openclaw: unsupported command $*" >&2; exit 2; }
shift
sub="${1:-}"; shift || true
case "$sub" in
  add)
    if [ "${1:-}" = "--help" ]; then
      echo "Usage: openclaw cron add [options]"
      echo "  --name <name>            Job name"
      echo "  --cron <expr>            Cron expression"
      echo "  --command <shell>        Command payload"
      echo "  --no-deliver             Disable runner fallback delivery"
      if [ "${FAKE_OC_NO_DECL:-0}" != "1" ]; then
        echo "  --declaration-key <key>  Idempotent declaration identity key"
      fi
      if [ "${FAKE_OC_NO_CMDENV:-0}" != "1" ]; then
        echo "  --command-env <KEY=VALUE>  Environment override for command payloads"
      fi
      exit 0
    fi
    if [ "${FAKE_OC_ADD_FAILS:-0}" = "1" ]; then
      echo "fake openclaw: gateway unreachable" >&2
      exit 1
    fi
    exec python3 "$FAKE_OC_PY" add "$@"
    ;;
  list)
    if [ "${1:-}" = "--help" ]; then
      echo "Usage: openclaw cron list [options]"
      echo "  --all   Include disabled jobs"
      echo "  --json  Output JSON"
      exit 0
    fi
    exec python3 "$FAKE_OC_PY" list "$@"
    ;;
  rm)     exec python3 "$FAKE_OC_PY" rm "$@" ;;
  enable) exec python3 "$FAKE_OC_PY" enable "$@" ;;
  *) echo "fake openclaw: unsupported subcommand $sub" >&2; exit 2 ;;
esac
FAKEOC
chmod +x "$FAKE_BIN/openclaw"

# ---------------------------------------------------------------------------
# Scenario driver
# ---------------------------------------------------------------------------
# Each scenario gets a fresh sandbox: its own OC_ROOT, its own CC checkout, its
# own cron store, its own log. Returns the registrar's exit code in RC and
# leaves the store at $S_STORE and the log at $S_LOG.
run_scenario() {
  # $1 = scenario name; remaining args are VAR=VALUE toggles for the fake CLI
  local name="$1"; shift
  S_DIR="$SANDBOX/$name"
  S_STORE="$S_DIR/cron.json"
  S_LOG="$S_DIR/install.log"
  S_OC_ROOT="$S_DIR/.openclaw"
  S_CC="$S_DIR/command-center"
  mkdir -p "$S_OC_ROOT" "$S_CC/scripts"
  [ "${SCENARIO_NO_WATCHDOG:-0}" = "1" ] || printf '#!/usr/bin/env bash\nexit 0\n' > "$S_CC/scripts/watchdog-cc.sh"
  : > "$S_LOG"
  printf '{"jobs": []}\n' > "$S_STORE"
  [ -n "${SCENARIO_SEED_STORE:-}" ] && printf '%s\n' "$SCENARIO_SEED_STORE" > "$S_STORE"

  local path_prefix="$FAKE_BIN:"
  [ "${SCENARIO_NO_CLI:-0}" = "1" ] && path_prefix=""

  cat > "$S_DIR/driver.sh" <<'DRIVER'
set -u
LOG_FILE="$S_LOG"
DASHBOARD_DIR="$S_CC"
DASHBOARD_PORT="4000"
OC_ROOT="$S_OC_ROOT"
log() { printf '%s [%-5s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE"; }
oc_cron_tombstoned() { [ -f "$S_DIR/.tombstone" ]; }
source "$FRAG"
cc_register_watchdog_cron
exit $?
DRIVER

  env -i \
    HOME="$S_DIR" \
    PATH="${path_prefix}/usr/bin:/bin:/usr/sbin:/sbin" \
    FAKE_OC_STORE="$S_STORE" \
    FAKE_OC_PY="$FAKE_PY" \
    S_LOG="$S_LOG" S_CC="$S_CC" S_OC_ROOT="$S_OC_ROOT" S_DIR="$S_DIR" FRAG="$FRAG" \
    "$@" \
    bash "$S_DIR/driver.sh" >"$S_DIR/stdout" 2>&1
  RC=$?
  return 0
}

jobs_count() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["jobs"]))' "$1"; }
job_field()  { python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
for j in d["jobs"]:
    if j.get("name")==sys.argv[2]:
        print(json.dumps(j.get(sys.argv[3])))
        break
' "$1" "$2" "$3"; }

# ---------------------------------------------------------------------------
# T3 - fresh register on a modern CLI
# ---------------------------------------------------------------------------
hdr "T3 - fresh register on a CLI with --declaration-key and --command-env"
run_scenario t3
[ "$RC" -eq 0 ] && ok "T3: registrar exited 0" || bad "T3: registrar exited $RC"
[ "$(jobs_count "$S_STORE")" = "1" ] && ok "T3: exactly ONE job registered" || bad "T3: expected 1 job, got $(jobs_count "$S_STORE")"
[ "$(job_field "$S_STORE" cc-watchdog cron)" = '"*/5 * * * *"' ] && ok "T3: schedule stored as */5 * * * *" || bad "T3: wrong schedule: $(job_field "$S_STORE" cc-watchdog cron)"
[ "$(job_field "$S_STORE" cc-watchdog declKey)" = '"skill32-cc-watchdog"' ] && ok "T3: declaration key stored" || bad "T3: declaration key missing"
[ "$(job_field "$S_STORE" cc-watchdog delivery)" = '"none"' ] && ok "T3: delivery mode none (--no-deliver)" || bad "T3: delivery mode is not none"
T3_CMD="$(job_field "$S_STORE" cc-watchdog command)"
case "$T3_CMD" in
  *';'*|*'||'*|*'&&'*) bad "T3: the cron payload is not a single plain command: $T3_CMD" ;;
  *watchdog-cc.sh*)    ok  "T3: payload is a single plain command invoking watchdog-cc.sh" ;;
  *)                   bad "T3: payload does not invoke watchdog-cc.sh: $T3_CMD" ;;
esac
case "$T3_CMD" in
  '"bash '*) ok "T3: payload has no inline VAR= prefix (env travels via --command-env)" ;;
  *)         bad "T3: payload does not start with 'bash ': $T3_CMD" ;;
esac
T3_ENV="$(job_field "$S_STORE" cc-watchdog env)"
for v in 'WATCHDOG_SELF_HEAL=1' 'WATCHDOG_PORT=4000' "WATCHDOG_CANONICAL_DIR=$S_CC"; do
  case "$T3_ENV" in
    *"$v"*) ok "T3: env carries $v" ;;
    *)      bad "T3: env is missing $v (got $T3_ENV)" ;;
  esac
done

# ---------------------------------------------------------------------------
# T4 - idempotency
# ---------------------------------------------------------------------------
hdr "T4 - running the registrar twice leaves exactly ONE job"
run_scenario t4
run_scenario t4   # same sandbox, store persists
[ "$(jobs_count "$S_STORE")" = "1" ] && ok "T4: still exactly ONE job after a second run (converged, not duplicated)" || bad "T4: expected 1 job after two runs, got $(jobs_count "$S_STORE")"

# ---------------------------------------------------------------------------
# T5 - a disabled job is re-enabled
# ---------------------------------------------------------------------------
hdr "T5 - an existing but DISABLED job is re-enabled"
SCENARIO_SEED_STORE='{"jobs": [{"id": "fixed-id-1", "name": "cc-watchdog", "declKey": "skill32-cc-watchdog", "cron": "*/5 * * * *", "command": "bash /old/watchdog-cc.sh", "env": [], "delivery": "none", "enabled": false}]}'
run_scenario t5
unset SCENARIO_SEED_STORE
[ "$(jobs_count "$S_STORE")" = "1" ] && ok "T5: still exactly ONE job" || bad "T5: expected 1 job, got $(jobs_count "$S_STORE")"
[ "$(job_field "$S_STORE" cc-watchdog enabled)" = "true" ] && ok "T5: the disabled job was re-enabled" || bad "T5: the job is still disabled"
grep -q 'was DISABLED - re-enabled' "$S_LOG" && ok "T5: the re-enable is logged" || bad "T5: no re-enable log line"

# ---------------------------------------------------------------------------
# T6 - a tombstoned name is never resurrected
# ---------------------------------------------------------------------------
hdr "T6 - a TOMBSTONED cc-watchdog is never re-registered"
S_PRE="$SANDBOX/t6"; mkdir -p "$S_PRE"; : > "$S_PRE/.tombstone"
run_scenario t6
[ "$RC" -eq 0 ] && ok "T6: registrar exited 0" || bad "T6: registrar exited $RC"
[ "$(jobs_count "$S_STORE")" = "0" ] && ok "T6: NO job registered over the tombstone" || bad "T6: the tombstone was overridden"
grep -q 'TOMBSTONED' "$S_LOG" && ok "T6: the refusal is logged" || bad "T6: no tombstone log line"

# ---------------------------------------------------------------------------
# T7 - older CC pin with no watchdog-cc.sh
# ---------------------------------------------------------------------------
hdr "T7 - watchdog-cc.sh absent (older CC pin): clean skip"
SCENARIO_NO_WATCHDOG=1 run_scenario t7
[ "$RC" -eq 0 ] && ok "T7: registrar exited 0 (the install is not failed)" || bad "T7: registrar exited $RC"
[ "$(jobs_count "$S_STORE")" = "0" ] && ok "T7: no job registered for a script that does not exist" || bad "T7: a job was registered anyway"
grep -q 'SKIPPED' "$S_LOG" && ok "T7: the skip is logged with a reason" || bad "T7: the skip is silent"

# ---------------------------------------------------------------------------
# T8 - no openclaw CLI on PATH
# ---------------------------------------------------------------------------
hdr "T8 - no openclaw CLI: loud PENDING, install continues"
SCENARIO_NO_CLI=1 run_scenario t8
[ "$RC" -eq 0 ] && ok "T8: registrar exited 0 (fail-soft, matching install.sh's cron registrars)" || bad "T8: registrar exited $RC"
grep -q 'PENDING' "$S_LOG" && ok "T8: PENDING is logged loudly" || bad "T8: no PENDING log line"
grep -q 'openclaw cron add --name cc-watchdog' "$S_LOG" && ok "T8: the log carries a copy-paste manual registration command" || bad "T8: no manual remedy in the log"

# ---------------------------------------------------------------------------
# T9 - CLI without --command-env falls back to the generated wrapper
# ---------------------------------------------------------------------------
hdr "T9 - CLI without --command-env: env moves into a generated wrapper"
run_scenario t9 FAKE_OC_NO_CMDENV=1
[ "$RC" -eq 0 ] && ok "T9: registrar exited 0" || bad "T9: registrar exited $RC"
WRAP="$S_OC_ROOT/scripts/cc-watchdog-run.sh"
[ -f "$WRAP" ] && ok "T9: wrapper written to \$OC_ROOT/scripts/cc-watchdog-run.sh" || bad "T9: no wrapper at $WRAP"
[ -x "$WRAP" ] && ok "T9: wrapper is executable" || bad "T9: wrapper is not executable"
if [ -f "$WRAP" ]; then
  for v in WATCHDOG_SELF_HEAL WATCHDOG_PORT WATCHDOG_CANONICAL_DIR; do
    grep -q "export $v=" "$WRAP" && ok "T9: wrapper exports $v" || bad "T9: wrapper does not export $v"
  done
  bash -n "$WRAP" && ok "T9: wrapper passes bash -n" || bad "T9: wrapper is not valid bash"
fi
T9_CMD="$(job_field "$S_STORE" cc-watchdog command)"
case "$T9_CMD" in
  *';'*|*'||'*|*'&&'*) bad "T9: the fallback payload is not a single plain command: $T9_CMD" ;;
  *cc-watchdog-run.sh*) ok "T9: the cron payload invokes the wrapper as a single plain command" ;;
  *) bad "T9: the payload does not invoke the wrapper: $T9_CMD" ;;
esac

# ---------------------------------------------------------------------------
# T10 - CLI without --declaration-key still converges to one job
# ---------------------------------------------------------------------------
hdr "T10 - CLI without --declaration-key: remove-then-add, still ONE job"
run_scenario t10 FAKE_OC_NO_DECL=1
run_scenario t10 FAKE_OC_NO_DECL=1
[ "$RC" -eq 0 ] && ok "T10: registrar exited 0" || bad "T10: registrar exited $RC"
[ "$(jobs_count "$S_STORE")" = "1" ] && ok "T10: exactly ONE job after two runs on a CLI with no converge flag" || bad "T10: expected 1 job, got $(jobs_count "$S_STORE")"

# ---------------------------------------------------------------------------
# T11 - a failing `cron add` is fail-soft but loud
# ---------------------------------------------------------------------------
hdr "T11 - 'openclaw cron add' failing: loud PENDING, rc 0"
run_scenario t11 FAKE_OC_ADD_FAILS=1
[ "$RC" -eq 0 ] && ok "T11: registrar exited 0 (the install is not failed by a cron problem)" || bad "T11: registrar exited $RC"
[ "$(jobs_count "$S_STORE")" = "0" ] && ok "T11: no job recorded" || bad "T11: a job was recorded despite the failure"
grep -q 'PENDING' "$S_LOG" && ok "T11: the failure is logged as PENDING with a remedy" || bad "T11: the failure is silent"

printf '\n\033[1mResult: %d passed | %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
