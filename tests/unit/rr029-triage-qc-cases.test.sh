#!/usr/bin/env bash
# tests/unit/rr029-triage-qc-cases.test.sh
# ---------------------------------------------------------------------------
# RR-029 — the QC contract from Reference audits/receiver-audit.md RCV-07,
# proven as behaviour rather than by reading the source:
#
#   absent table · permissions · old failures · 720 normal polls · true retry
#   loop · canonical/legacy provider config · multiple services/containers ·
#   dead gateway with container Up  -> each must produce the CORRECT status.
#   Unknown can never become clean.
#
# Method: drive the REAL ladder functions out of scripts/rr-triage.sh
# (--source-only, JSON_MODE=1) against fixture configs and fixture sqlite
# databases, with stub launchctl/docker/curl on PATH. No live box is touched;
# every case asserts the VERDICT, not just an exit code.
# ---------------------------------------------------------------------------
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRIAGE="$REPO_ROOT/scripts/rr-triage.sh"
DESCRIPTOR="$REPO_ROOT/shared-utils/oc-env-descriptor.sh"
for f in "$TRIAGE" "$DESCRIPTOR"; do
  [ -f "$f" ] || { echo "FATAL: $f not found"; exit 2; }
done

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
NOW_MS=$(( $(date +%s) * 1000 ))
export OC_SKIP_CLI_PROBE=1 OC_ENV_DESCRIPTOR="$DESCRIPTOR"

# Fixture schema mirrors the live runtime exactly (cron_run_receipts, NOT the
# nonexistent cron_run_logs; millisecond timestamps).
RC_T='create table cron_run_receipts (receipt_id text primary key, store_key text not null, job_id text not null, config_revision text not null, agent_id text not null, request_run_id text, status text not null, owner_pid integer not null, owner_start_time integer, started_at_ms integer not null, finished_at_ms integer, error_text text);'
JOBS_T='create table cron_jobs (store_key text not null, job_id text not null, declaration_key text, owner_agent_id text, name text not null, description text, enabled integer not null, agent_id text, payload_kind text not null, job_json text not null, state_json text not null default "{}", runtime_updated_at_ms integer, schedule_identity text, sort_order integer not null default 0, updated_at integer not null);'
DQ_T='create table delivery_queue_entries (queue_name text not null, id text not null, status text not null, entry_kind text, session_key text, channel text, target text, account_id text, retry_count integer not null default 0, last_attempt_at integer, last_error text, recovery_state text, platform_send_started_at integer, entry_json text not null, enqueued_at integer not null, updated_at integer not null, failed_at integer);'
CI_T='create table channel_ingress_events (queue_name text not null, event_id text not null, channel_id text not null, account_id text not null, status text not null, lane_key text, payload_json text not null, metadata_json text, received_at integer not null, updated_at integer not null, claim_token text, claim_owner text, claimed_at integer, attempts integer not null default 0, last_attempt_at integer, last_error text, failed_reason text, failed_at integer, completed_at integer, completed_metadata_json text);'

mdb() { # mdb <path> <sql...>
  local db="$1"; shift; : > "$db"
  local s; for s in "$@"; do sqlite3 "$db" "$s" >/dev/null 2>&1 || return 1; done
}

# _drive <step-fn> <config-root> [state-db] [extra "KEY=VAL"]... -> "%s|%s" verdict|detail
_drive() {
  local fn="$1" root="$2" db="${3:-}"; shift 3 || shift 2
  OC_CONFIG_ROOT="$root" env ${db:+OC_STATE_DB="$db"} "$@" \
    bash -c '
      . "$1" --source-only 2>/dev/null
      ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
      "$2"; rc=$?
      # Field-splitting with awk would cut the detail at its first pipe, and
      # several step details legitimately contain pipes. Strip the two leading
      # fields with parameter expansion instead.
      line="$(printf "%s\n" "$RESULTS" | head -1)"
      r1="${line#*|}"; r2="${r1#*|}"      # drop step, then name
      v="${r2%%|*}"; d="${r2#*|}"
      printf "%s|%s|%s|%s" "$v" "$rc" "$PROBLEM_BITS" "$d"
    ' _ "$TRIAGE" "$fn"
}

verdict_of() { printf '%s' "${1%%|*}"; }
rc_of()      { local r="${1#*|}"; printf '%s' "${r%%|*}"; }
bits_of()    { local r="${1#*|*|}"; printf '%s' "${r%%|*}"; }
detail_of()  { printf '%s' "${1#*|*|*|}"; }

CFG_OK='{"agents":{"list":[{"id":"main"}]},"channels":{"telegram":{"streaming":{"mode":"off"}}},"tools":{"toolSearch":{"enabled":true,"mode":"directory"}},"models":{"providers":{"anthropic":{"timeoutSeconds":120}}}}'

# ===========================================================================
echo "== [RR-029] DB-backed cases (absent table, permissions, history, cron) =="
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "  (sqlite3 absent — DB cases skipped, NOT counted as passes)"
else
  # --- ABSENT TABLE: missing channel_ingress_events must be UNDETERMINED -----
  mkdir -p "$WORK/absent"
  mdb "$WORK/absent/state.sqlite" "$DQ_T"
  r="$(_drive step2 "$WORK/absent" "$WORK/absent/state.sqlite")"
  [ "$(verdict_of "$r")" = "UNDETERMINED" ] && [ "$(rc_of "$r")" -ne 0 ] \
    && ok "absent table -> UNDETERMINED (never CLEAN)" \
    || bad "absent table produced $(verdict_of "$r") rc=$(rc_of "$r")"

  # --- PERMISSIONS: unreadable db must be rejected WITH the reason -----------
  if [ "$(id -u)" -ne 0 ]; then
    mkdir -p "$WORK/perm"
    mdb "$WORK/perm/state.sqlite" "$DQ_T" "$CI_T"
    chmod 000 "$WORK/perm/state.sqlite"
    r="$(_drive step2 "$WORK/perm" "$WORK/perm/state.sqlite")"
    [ "$(verdict_of "$r")" = "UNDETERMINED" ] \
      && ok "permissions (unreadable db) -> UNDETERMINED" \
      || bad "permissions produced $(verdict_of "$r")"
    chmod 600 "$WORK/perm/state.sqlite"
  fi

  # --- OLD FAILURES: 3-day-old resolved failure must NOT be a current problem
  mkdir -p "$WORK/old" "$WORK/now"
  OLD_MS=$(( NOW_MS - 3 * 86400000 ))
  mdb "$WORK/old/state.sqlite" "$DQ_T" "$CI_T"
  sqlite3 "$WORK/old/state.sqlite" "insert into delivery_queue_entries values ('q','o','failed',null,null,null,null,null,1,$OLD_MS,'x',null,null,'{}',$OLD_MS,$OLD_MS,$OLD_MS);" >/dev/null 2>&1
  mdb "$WORK/now/state.sqlite" "$DQ_T" "$CI_T"
  sqlite3 "$WORK/now/state.sqlite" "insert into delivery_queue_entries values ('q','n','failed',null,null,null,null,null,1,$NOW_MS,'x',null,null,'{}',$NOW_MS,$NOW_MS,$NOW_MS);" >/dev/null 2>&1
  ro="$(_drive step2 "$WORK/old" "$WORK/old/state.sqlite")"
  rn="$(_drive step2 "$WORK/now" "$WORK/now/state.sqlite")"
  [ "$(verdict_of "$ro")" = "CLEAN" ] && [ "$(verdict_of "$rn")" = "PROBLEM" ] \
    && ok "historical failure CLEAN vs in-window failure PROBLEM (window bounded)" \
    || bad "history discrimination: old=$(verdict_of "$ro") now=$(verdict_of "$rn")"

  # --- 720 NORMAL POLLS: the receiver cadence must read CLEAN ---------------
  mkdir -p "$WORK/poll"
  mdb "$WORK/poll/state.sqlite" "$RC_T" "$JOBS_T"
  sqlite3 "$WORK/poll/state.sqlite" "insert into cron_jobs values ('d','p','k','main','rescue-rr-box-poll',null,1,'main','command','{\"id\":\"p\",\"name\":\"rescue-rr-box-poll\",\"enabled\":true,\"schedule\":{\"kind\":\"cron\",\"expr\":\"*/2 * * * *\"}}','{}',null,null,0,$NOW_MS);" >/dev/null 2>&1
  i=0; while [ "$i" -lt 65 ]; do
    sqlite3 "$WORK/poll/state.sqlite" "insert into cron_run_receipts values ('r$i','d','p','rev','main',null,'ok',1,null,$(( NOW_MS - i * 120000 )),null,null);" >/dev/null 2>&1
    i=$((i + 1))
  done
  r="$(_drive step5 "$WORK/poll" "$WORK/poll/state.sqlite")"
  [ "$(verdict_of "$r")" = "CLEAN" ] && [ "$(rc_of "$r")" -eq 0 ] \
    && ok "720/day two-minute poll reads CLEAN (old aggregate >200 rule false-flagged it)" \
    || bad "normal polls produced $(verdict_of "$r") rc=$(rc_of "$r") bits=$(bits_of "$r")"

  # --- TRUE RETRY LOOP: declared hourly, actually far denser, erroring -------
  mkdir -p "$WORK/loop"
  mdb "$WORK/loop/state.sqlite" "$RC_T" "$JOBS_T"
  sqlite3 "$WORK/loop/state.sqlite" "insert into cron_jobs values ('d','l','k','main','runaway-job',null,1,'main','command','{\"id\":\"l\",\"name\":\"runaway-job\",\"enabled\":true,\"schedule\":{\"kind\":\"cron\",\"expr\":\"17 * * * *\"}}','{}',null,null,0,$NOW_MS);" >/dev/null 2>&1
  i=0; while [ "$i" -lt 60 ]; do
    sqlite3 "$WORK/loop/state.sqlite" "insert into cron_run_receipts values ('L$i','d','l','rev','main',null,'error',1,null,$(( NOW_MS - i * 60000 )),null,'boom');" >/dev/null 2>&1
    i=$((i + 1))
  done
  r="$(_drive step5 "$WORK/loop" "$WORK/loop/state.sqlite")"
  [ "$(verdict_of "$r")" = "PROBLEM" ] && [ $(( $(bits_of "$r") & 16 )) -ne 0 ] \
    && ok "true retry loop (declared hourly, observed 1min, erroring) -> PROBLEM with CRON bit" \
    || bad "retry loop produced $(verdict_of "$r") bits=$(bits_of "$r")"

  # --- UNKNOWN CANNOT BECOME CLEAN: no cron table at all --------------------
  mkdir -p "$WORK/nocron"
  mdb "$WORK/nocron/state.sqlite" "$DQ_T"
  r="$(_drive step5 "$WORK/nocron" "$WORK/nocron/state.sqlite")"
  [ "$(verdict_of "$r")" = "UNDETERMINED" ] && [ "$(rc_of "$r")" -ne 0 ] \
    && ok "no cron history table -> UNDETERMINED (unknown never became clean)" \
    || bad "missing cron table produced $(verdict_of "$r")"
fi

# ===========================================================================
echo "== [RR-029] provider config shapes =="
# --- LEGACY config: root `providers` present, canonical models.providers absent
mkdir -p "$WORK/legacy/agents/main" "$WORK/canonical/agents/main" "$WORK/missing/agents/main"
printf '{"agents":{"list":[{"id":"main"}]},"providers":{"anthropic":{"timeoutSeconds":120},"deepseek":{"timeoutSeconds":60}}}' > "$WORK/legacy/openclaw.json"
printf '{"agents":{"list":[{"id":"main"}]},"models":{"providers":{"anthropic":{"timeoutSeconds":120},"deepseek":{"baseUrl":"x"}}}}' > "$WORK/missing/openclaw.json"
mkdir -p "$WORK/none/agents/main"
printf '{"agents":{"list":[{"id":"main"}]}}' > "$WORK/none/openclaw.json"

rl="$(_drive step7 "$WORK/legacy")"
rc_="$(_drive step7 "$WORK/missing")"
rn_="$(_drive step7 "$WORK/none")"
case "$(detail_of "$rl")" in
  *"legacy root providers"*) ok "legacy root providers is READ (not silently skipped as 'no providers')" ;;
  *) bad "legacy config: $(detail_of "$rl")" ;;
esac
[ "$(verdict_of "$rc_")" = "PROBLEM" ] \
  && ok "canonical models.providers MISSING a timeout -> PROBLEM (the RCV-07 false negative)" \
  || bad "missing-provider-timeout produced $(verdict_of "$rc_")"
[ "$(verdict_of "$rn_")" = "UNDETERMINED" ] \
  && ok "no provider config in any known shape -> UNDETERMINED, never 'no missing timeouts'" \
  || bad "no-provider-shape produced $(verdict_of "$rn_")"

# ===========================================================================
echo "== [RR-029] exact service/container target + app readiness =="
mkdir -p "$WORK/bin" "$WORK/svc/agents/main"
printf '%s' "$CFG_OK" > "$WORK/svc/openclaw.json"

# stub: 5 openclaw-ish labels on the box, only ai.openclaw.gateway is ours
cat > "$WORK/bin/launchctl" <<'SL'
#!/bin/bash
# "absent" mode: the approved label is NOT loaded, but a neighbouring
# openclaw-ish label IS -- the ladder must not fall back to it.
if [ "${OC_FIX_SVC:-}" = "absent" ]; then
  if [ "${1:-}" = "list" ]; then printf '%s\n' $'-\t0\tai.openclaw.donna-gw-tunnel'; exit 0; fi
  echo "Could not find service" >&2; exit 1
fi
if [ "${1:-}" = "list" ]; then
  printf '%s\n' $'-\t0\tai.openclaw.donna-gw-tunnel' $'-\t0\tai.openclaw.janet-gw-tunnel' \
    $'1232\t0\tai.openclaw.gateway' $'-\t0\tai.openclaw.gateway-watchdog' $'-\t0\tai.openclaw.other'
  exit 0
fi
if [ "${1:-}" = "print" ]; then
  case "${2:-}" in
    *"ai.openclaw.gateway")
      case "${OC_FIX_SVC:-alive}" in
        alive) printf '\tstate = running\n\tpid = 1232\n\tlast exit code = 0\n' ;;
        stale) printf '\tstate = not running\n\tlast exit code = 0\n' ;;
      esac
      exit 0 ;;
    *) echo "Could not find service" >&2; exit 1 ;;
  esac
fi
exit 0
SL
cat > "$WORK/bin/curl" <<'CU'
#!/bin/bash
[ "${OC_FIX_HEALTHY:-0}" = "1" ] && { printf '{"ok":true,"status":"live"}\n200'; exit 0; }
printf 'curl: (7) Failed to connect\n000'; exit 7
CU
cat > "$WORK/bin/docker" <<'DK'
#!/bin/bash
if [ "${1:-}" = "inspect" ]; then
  n=""; for a in "$@"; do n="$a"; done
  [ "$n" = "openclaw" ] || { echo "Error: No such object: $n" >&2; exit 1; }
  case "${OC_FIX_DOCKER:-running}" in
    running) printf 'running|2026-09-10T10:00:00Z|0|0\n' ;;
    exited)  printf 'exited|2026-09-10T10:00:00Z|0|0\n' ;;
  esac
  exit 0
fi
[ "${1:-}" = "exec" ] && exit 1
exit 0
DK
chmod +x "$WORK/bin/"*

# --- MULTIPLE SERVICES: never the first substring match ---------------------
r="$(PATH="$WORK/bin:$PATH" OC_PLATFORM=mac OC_TARGET_MODE=launchd OC_GATEWAY_PORT=18789 \
     OC_FIX_SVC=alive OC_FIX_HEALTHY=1 _drive step1 "$WORK/svc")"
d="$(detail_of "$r")"
[ "$(verdict_of "$r")" = "CLEAN" ] && [ "$(rc_of "$r")" -eq 0 ] \
  && ok "exact approved label running + app ready -> CLEAN" \
  || bad "exact target: $(verdict_of "$r") rc=$(rc_of "$r") $d"
case "$d" in
  *donna-gw-tunnel*|*janet*) bad "selected a NEIGHBOURING service label (first-substring-match regression)" ;;
  *) ok "never selected a neighbouring openclaw-ish label" ;;
esac

# --- STALE EXIT: loaded, not running, clean last exit -> PROBLEM -----------
r="$(PATH="$WORK/bin:$PATH" OC_PLATFORM=mac OC_TARGET_MODE=launchd OC_GATEWAY_PORT=18789 \
     OC_FIX_SVC=stale OC_FIX_HEALTHY=1 _drive step1 "$WORK/svc")"
[ "$(verdict_of "$r")" = "PROBLEM" ] && [ "$(rc_of "$r")" -ne 0 ] \
  && ok "stale clean exit (not running) -> PROBLEM, not CLEAN" \
  || bad "stale exit produced $(verdict_of "$r")"

# --- DEAD GATEWAY WITH CONTAINER UP: Up is not health ---------------------
r="$(PATH="$WORK/bin:$PATH" OC_PLATFORM=vps-host OC_TARGET_MODE=docker OC_CONTAINER=openclaw \
     OC_GATEWAY_PORT=18789 OC_FIX_DOCKER=running OC_FIX_HEALTHY=0 _drive step1 "$WORK/svc")"
v="$(verdict_of "$r")"
[ "$v" = "PROBLEM" ] && [ "$(rc_of "$r")" -ne 0 ] \
  && ok "dead gateway with container Up -> PROBLEM (app readiness required)" \
  || bad "container-Up-but-dead produced $v"
case "$(detail_of "$r")" in
  *1743*|*18789*) ok "readiness probe targeted the resolved gateway port (not a guessed one)" ;;
  *) bad "readiness detail does not name the resolved port: $(detail_of "$r")" ;;
esac

# --- EXITED container -> PROBLEM ------------------------------------------
r="$(PATH="$WORK/bin:$PATH" OC_PLATFORM=vps-host OC_TARGET_MODE=docker OC_CONTAINER=openclaw \
     OC_GATEWAY_PORT=18789 OC_FIX_DOCKER=exited OC_FIX_HEALTHY=1 _drive step1 "$WORK/svc")"
[ "$(verdict_of "$r")" = "PROBLEM" ] \
  && ok "exited container -> PROBLEM even though the app would answer" \
  || bad "exited container produced $(verdict_of "$r")"

# --- UNKNOWN TARGET: approved service not loaded -> UNDETERMINED, never CLEAN.
# Driven through the stub (gateway label ABSENT) so this case can never consult
# the host's real launchd.
r="$(PATH="$WORK/bin:$PATH" OC_PLATFORM=mac OC_TARGET_MODE=launchd OC_GATEWAY_PORT=18789 \
     OC_FIX_SVC=absent OC_FIX_HEALTHY=1 _drive step1 "$WORK/svc")"
[ "$(verdict_of "$r")" = "UNDETERMINED" ] \
  && ok "unresolvable runtime target -> UNDETERMINED (unknown cannot become clean)" \
  || bad "unknown target produced $(verdict_of "$r")"

# ===========================================================================
echo "== [RR-029] canonical identity on every diagnostic line =="
mkdir -p "$WORK/id/agents/main"
printf '%s' "$CFG_OK" > "$WORK/id/openclaw.json"
r="$(OC_BOX_SLUG=qc-box COMPANY_SLUG=qc-co _drive step3 "$WORK/id")"
case "$(detail_of "$r")" in
  *"[box=qc-box company=qc-co]"*) ok "diagnostic line carries canonical box + company" ;;
  *) bad "identity missing from: $(detail_of "$r")" ;;
esac

# ===========================================================================
echo "[rr029-triage-qc-cases] PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "[rr029-triage-qc-cases] PASS (RR-029 QC cases)"
exit 0
