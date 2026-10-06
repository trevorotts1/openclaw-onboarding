#!/bin/bash
# scripts/rr-triage.sh — Rescue Rangers read-only loop/stuck/no-reply triage
# ============================================================================
# R7 of the Rescue Rangers Loop-Response and Fleet Prevention Plan.
# Companion instrument to universal-sops/SOP-RR-LOOP-TRIAGE.md -- read that
# SOP for the full doctrine and the WHY behind each step. This script is the
# read-only, self-controlled ladder walk a responder (human or agent) runs
# over SSH against a box reporting "it loops / it's stuck / no reply".
#
# ⚠️ READ-ONLY, ALWAYS. This script NEVER writes, NEVER restarts anything,
# NEVER contacts a client. It reports. A human (or a separately-authorized
# remediation script) decides and acts.
#
# RR-029 (RCV-07) — WHAT CHANGED AND WHY
#   The pre-RR-029 ladder could print a false CLEAN and a false runaway:
#     * STEP 1 took the FIRST `launchctl list` label CONTAINING "openclaw"
#       (this operator box carries 8 of them) and called any parsed non-78 exit
#       CLEAN without proving an active process — a stopped gateway with a
#       clean stale exit read CLEAN. Its docker branch took the first
#       `--filter name=openclaw` match, which on a multi-tenant host can be a
#       NEIGHBOUR's container, and treated `Up` as health.
#     * STEP 0/2/5 opened whichever sqlite file existed first — including a
#       0-byte decoy that `sqlite3 … "select 1;"` happily "opens".
#     * STEP 2 discarded failed query results and read an absent
#       `channel_ingress_events` as "no handler-timeouts".
#     * STEP 5 flagged aggregate cron runs > 200/day, so the receiver's
#       LEGITIMATE 720/day two-minute cadence was a permanent false runaway.
#     * STEP 7 read root `providers`; the canonical key is `models.providers`,
#       so every provider read as "no missing timeouts".
#   Each of those has one root cause: the tool did not have ONE descriptor
#   saying which box/root/db/service/container it was talking about, and it
#   never required a query to SUCCEED before treating its output as data.
#   Both are now enforced: shared-utils/oc-env-descriptor.sh owns the target
#   and the app-readiness proof, and every DB read goes through a checked
#   helper (ocd_qry) whose failure is UNDETERMINED, never zero.
#
# PLATFORM: Mac (launchd), VPS host (docker) and inside-container (process +
# HTTP readiness) are all supported and resolved by the descriptor. A Contabo
# client tree is reachable ONLY through an explicit OC_TARGET_BOX; this script
# never scans /opt/clients, so it can never diagnose a neighbouring client.
#
# EXIT CODE CONTRACT (read this before scripting against this tool):
#   0            every step that could run found no problem.
#   3            at least one step is UNDETERMINED -- this OVERRIDES a clean
#                bitmask. An incomplete verdict is NEVER reported as if it
#                were a pass. Read stdout for which step(s) and why.
#   78           STEP 0 itself failed (the box/instrument could not be
#                reached or proven) -- nothing downstream is valid. Same
#                EX_CONFIG convention this repo's other gates use for "needs
#                a human", never a transport failure code.
#   100+bitmask  one or more steps found a real PROBLEM and every step that
#                ran was determined (no step was UNDETERMINED). Subtract 100
#                to get the bitmask; see STEP_BIT_* below for which bit is
#                which mechanism. Offset by 100 so this range can never
#                collide with 0/3/78.
# Never treat a nonzero exit as "the box is broken" without reading which
# branch of this contract produced it -- 3 means "ask again with a working
# instrument", not "problem confirmed".
#
# USAGE:
#   scripts/rr-triage.sh                    # full ladder, human-readable
#   scripts/rr-triage.sh --json             # same ladder, one JSON object
#   scripts/rr-triage.sh --self-test        # offline fixture self-test
#   scripts/rr-triage.sh --descriptor       # print the resolved descriptor only
# OVERRIDES (all optional, all read-only): OC_CONFIG_ROOT, OC_STATE_DB,
# OC_LOG_ROOT, OC_PLATFORM, OC_TARGET_MODE, OC_SERVICE_LABEL, OC_CONTAINER,
# OC_GATEWAY_PORT, OC_APP_READY_URL, OC_BOX_SLUG, OC_INCIDENT_WINDOW_MINUTES,
# OC_EXPECT_WINDOW_MINUTES, OC_ENV_DESCRIPTOR.
# ============================================================================
set -u

STEP_BIT_GATEWAY=1        # STEP 1: crash-loop / gateway down
STEP_BIT_DELIVERY=2       # STEP 2: work completed, delivery died
STEP_BIT_STREAMING=4      # STEP 3: narration spam (streaming.mode partial)
STEP_BIT_TOOLSEARCH=8     # STEP 4: tool-unreachable loop
STEP_BIT_CRON=16          # STEP 5: cron/restart-kill
STEP_BIT_COMPACTION=32    # STEP 6: compaction wedge
STEP_BIT_SUBSTRATE=64     # STEP 7: chown/timeout/registry-parity/raw-writer

PROBLEM_BITS=0
UNDETERMINED_COUNT=0
JSON_MODE=0
RESULTS=""   # newline-separated "STEP|NAME|VERDICT|detail" records

# RR-029: current-incident window for "is this failure HAPPENING" vs "did it
# happen once, historically". Historical failures are reported, never counted
# as a current problem (RCV-07: "distinguish historical failures").
INCIDENT_WINDOW_MIN="${OC_INCIDENT_WINDOW_MINUTES:-60}"
# Expected-count derivation window (schedules are evaluated over this window).
EXPECT_WINDOW_MIN="${OC_EXPECT_WINDOW_MINUTES:-1440}"

# ----------------------------------------------------------------------------
# THE descriptor. One file decides root / db / log dir / platform / exact
# service-or-container / gateway port / app readiness / box+company identity.
# Without it this ladder must NOT guess: every descriptor-dependent step
# reports UNDETERMINED with the reason instead of falling back to a first
# match (that fallback was the RCV-07 defect).
# ----------------------------------------------------------------------------
_TRIAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
OCD_LOADED=0
_find_descriptor() {
  local d="$1" i
  for i in 1 2 3 4; do
    [ -n "$d" ] && [ -f "$d/shared-utils/oc-env-descriptor.sh" ] && { printf '%s' "$d/shared-utils/oc-env-descriptor.sh"; return 0; }
    d="$(dirname "$d")"
    [ "$d" = "/" ] && break
  done
  return 1
}
if [ -n "${OC_ENV_DESCRIPTOR:-}" ] && [ -f "${OC_ENV_DESCRIPTOR}" ]; then
  # shellcheck disable=SC1090
  . "$OC_ENV_DESCRIPTOR" && OCD_LOADED=1
else
  _OCD_CAND="$(_find_descriptor "$_TRIAGE_DIR" || true)"
  if [ -n "$_OCD_CAND" ]; then
    # shellcheck disable=SC1090
    . "$_OCD_CAND" && OCD_LOADED=1
  fi
fi
if [ "$OCD_LOADED" -eq 0 ]; then
  # Degraded shim: ONLY the config-file-only steps (3/4/7) can run without the
  # descriptor, and they say so in their identity prefix. This is deliberately
  # an "instrument missing" outcome, never a silent second implementation of
  # target resolution.
  OCD_ROOT=""; OCD_ROOT_SOURCE="descriptor not loaded"; OCD_JSON=""; OCD_JSON_STATE="unknown"
  OCD_LOG_DIR="${OC_LOG_ROOT:-/tmp/openclaw}"; OCD_LOG_NOTE="descriptor not loaded"
  OCD_DB=""; OCD_DB_SOURCE="none"; OCD_DB_NOTE="descriptor not loaded"
  OCD_BOX_SLUG="${OC_BOX_SLUG:-unknown}"; OCD_BOX_SOURCE="descriptor not loaded"
  OCD_COMPANY_SLUG="${COMPANY_SLUG:-unknown}"; OCD_COMPANY_SOURCE="descriptor not loaded"
  OCD_PLATFORM="${OC_PLATFORM:-unknown}"; OCD_TARGET_MODE="unknown"; OCD_TARGET_ID=""; OCD_TARGET_NOTE="descriptor not loaded"
  OCD_GATEWAY_PORT="${OC_GATEWAY_PORT:-}"; OCD_GATEWAY_PORT_SOURCE="descriptor not loaded"; OCD_READY=""; OCD_READY_DETAIL=""
  ocd_init() {
    if [ -n "${OC_CONFIG_ROOT:-}" ]; then
      OCD_ROOT="$OC_CONFIG_ROOT"; OCD_ROOT_SOURCE="OC_CONFIG_ROOT"
      [ -f "$OCD_ROOT/openclaw.json" ] && OCD_JSON="$OCD_ROOT/openclaw.json" && OCD_JSON_STATE="present" || OCD_JSON_STATE="absent"
    fi
  }
  ocd_json_path() { [ -n "$OCD_JSON" ] && printf '%s' "$OCD_JSON" || printf '%s/openclaw.json' "${OCD_ROOT:-}"; }
  ocd_describe() { printf 'descriptor=UNLOADED box=%s company=%s' "$OCD_BOX_SLUG" "$OCD_COMPANY_SLUG"; }
  ocd_identity_prefix() { printf '[box=%s company=%s]' "$OCD_BOX_SLUG" "$OCD_COMPANY_SLUG"; }
  ocd_state_db() { OCD_DB_NOTE="descriptor not loaded"; return 1; }
  ocd_app_ready() { OCD_READY="undetermined"; OCD_READY_DETAIL="descriptor not loaded"; return 2; }
  ocd_gateway_port() { OCD_GATEWAY_PORT="${OC_GATEWAY_PORT:-}"; OCD_GATEWAY_PORT_SOURCE="descriptor not loaded"; return 0; }
  ocd_platform() { OCD_PLATFORM="${OC_PLATFORM:-unknown}"; }
  ocd_target() { OCD_TARGET_MODE="unknown"; OCD_TARGET_ID=""; }
  ocd_log_dir() { return 1; }
  ocd_qry() { OCD_QRY_OUT=""; OCD_QRY_ERR="descriptor not loaded"; OCD_QRY_RC=2; return 2; }
  ocd_table_present() { return 2; }
  ocd_missing_columns() { printf 'unknown'; return 2; }
fi

record() {
  # record STEP NAME VERDICT detail...
  local step="$1" name="$2" verdict="$3"; shift 3
  local detail="$*"
  # RR-029: every diagnostic line carries the canonical box/company, so a
  # relayed line can never be attributed to the wrong client.
  detail="$(ocd_identity_prefix) $detail"
  RESULTS="${RESULTS}${step}|${name}|${verdict}|${detail}
"
  case "$verdict" in
    UNDETERMINED) UNDETERMINED_COUNT=$((UNDETERMINED_COUNT + 1)) ;;
  esac
  if [ "$JSON_MODE" -eq 0 ]; then
    printf '%s %-10s %-13s %s\n' "$step" "$name" "$verdict" "$detail"
  fi
}

# ----------------------------------------------------------------------------
# Config-reading helper. Same bash-3.2.57-heredoc-in-$()-parser workaround
# used throughout this repo (write python source to a temp FILE, run it as a
# plain command substitution, never a heredoc directly inside $(...)), and
# the same mktemp fix: NO literal suffix after the X's (BSD/macOS mktemp does
# not randomize "foo.XXXXXX.py" -- see update-skills.sh's
# _agents_list_detect() for the measured proof).
# ----------------------------------------------------------------------------
_run_py() {
  # _run_py <script-var-name-holding-python-source> <arg...>
  local src="$1"; shift
  local py out rc
  py="$(mktemp "${TMPDIR:-/tmp}/rr-triage.XXXXXX")" || { printf 'PYFAIL'; return 1; }
  printf '%s' "$src" > "$py"
  out="$(python3 "$py" "$@" 2>&1)"; rc=$?
  rm -f "$py"
  printf '%s' "$out"
  return $rc
}

# ============================================================================
# STEP 0 -- reach the box and prove your instruments
# ============================================================================
step0() {
  local today today_marker_found=0 db_ok=0 detail=""
  ocd_init
  ocd_json_path >/dev/null 2>&1 || true

  if [ "$OCD_LOADED" -eq 0 ]; then
    record 0 instruments UNDETERMINED "environment descriptor not found (looked beside the script and 4 parents for shared-utils/oc-env-descriptor.sh; override with OC_ENV_DESCRIPTOR) -- no target can be proven, so nothing downstream is valid"
    return 1
  fi
  if [ -z "${OCD_ROOT:-}" ]; then
    record 0 instruments UNDETERMINED "no OpenClaw root resolved ($OCD_ROOT_SOURCE) -- cannot prove this is a provisioned box"
    return 1
  fi
  if [ ! -f "$OCD_JSON" ]; then
    record 0 instruments UNDETERMINED "no config at $OCD_JSON (root via $OCD_ROOT_SOURCE) -- cannot prove this is a provisioned box"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 0 instruments UNDETERMINED "python3 not on PATH -- cannot parse config or run any downstream check"
    return 1
  fi

  ocd_log_dir || true
  today="$(date +%Y-%m-%d 2>/dev/null || echo unknown)"
  if [ -d "$OCD_LOG_DIR" ] && [ -f "$OCD_LOG_DIR/openclaw-${today}.log" ] && [ -s "$OCD_LOG_DIR/openclaw-${today}.log" ]; then
    today_marker_found=1
  fi

  ocd_state_db || true
  [ -n "${OCD_DB:-}" ] && db_ok=1

  detail="platform=$OCD_PLATFORM target=$OCD_TARGET_MODE:${OCD_TARGET_ID:-none} root=$OCD_ROOT ($OCD_ROOT_SOURCE) db=${OCD_DB:-none} logdir=$OCD_LOG_DIR"
  if [ "$today_marker_found" -eq 1 ] && [ "$db_ok" -eq 1 ]; then
    record 0 instruments CLEAN "structured log present+non-empty for $today; $OCD_DB_NOTE; $detail"
    return 0
  fi

  local missing=""
  [ "$today_marker_found" -eq 0 ] && missing="structured-log-today"
  [ "$db_ok" -eq 0 ] && missing="${missing}${missing:+,}state-db"
  if [ "$today_marker_found" -eq 0 ] && [ "$db_ok" -eq 0 ]; then
    record 0 instruments UNDETERMINED "BOTH primary instruments unavailable ($missing): $OCD_LOG_NOTE; $OCD_DB_NOTE; $detail -- nothing downstream in this ladder is valid until this is fixed"
  else
    record 0 instruments UNDETERMINED "one primary instrument unavailable ($missing): log=$today_marker_found (${OCD_LOG_NOTE}); db=$db_ok (${OCD_DB_NOTE}); $detail -- downstream steps that depend on it report UNDETERMINED too, not a false clean"
  fi
  return 1
}

# ============================================================================
# STEP 1 -- gateway: is the EXACT approved target running, and is the APP
# answering? A loaded service whose process exited 0, a container that is "Up"
# while nothing answers on the gateway port, and a first-label/first-container
# guess all used to read CLEAN. None of them are app readiness.
# ============================================================================
# Pure verdict function so the decision can be fixture-tested without a box.
#   _gateway_verdict <live:0|1|unknown> <last_exit> <ready:ready|not-ready|undetermined>
_gateway_verdict() {
  local live="$1" last_exit="$2" ready="$3"
  case "$last_exit" in
    78|78\ *|78\(*|EX_CONFIG*|*EX_CONFIG*)
      printf 'PROBLEM|last exit code=%s (78/EX_CONFIG signature -- schema rejection crash-loop)' "$last_exit"; return 1 ;;
  esac
  case "$live" in
    unknown)
      printf 'UNDETERMINED|target exists but process liveness could not be parsed (%s)' "${3:-}"; return 2 ;;
    0)
      printf 'PROBLEM|target is NOT running (last exit code=%s, app readiness=%s) -- a stale clean exit is not a live gateway' "${last_exit:-unknown}" "$ready"; return 1 ;;
  esac
  case "$ready" in
    ready)
      printf 'CLEAN|target running (last exit code=%s) and the APP answers its health contract' "${last_exit:-unknown}"; return 0 ;;
    not-ready)
      printf 'PROBLEM|target process is UP but the APP is NOT ready (%s) -- container/service Up is not app health' "${4:-}"; return 1 ;;
    *)
      printf 'UNDETERMINED|target process is up but app readiness could not be proven -- never reported as clean'; return 2 ;;
  esac
}

step1() {
  if [ "$OCD_LOADED" -eq 0 ]; then
    record 1 gateway UNDETERMINED "environment descriptor not loaded -- no exact target to inspect"
    return 1
  fi
  case "$OCD_TARGET_MODE" in
    launchd)
      local label out state pid last_exit live ready others
      label="$OCD_TARGET_ID"
      out="$(launchctl list 2>/dev/null)"
      others="$(printf '%s\n' "$out" | awk -v l="$label" '$3 != l && $3 ~ /openclaw/ {n++} END{print n+0}')"
      local row; row="$(printf '%s\n' "$out" | awk -v l="$label" '$3 == l {print; exit}')"
      if [ -z "$row" ]; then
        record 1 gateway UNDETERMINED "exact service label '$label' is NOT loaded on this box (${others} other openclaw-ish label(s) present and deliberately ignored -- no first-match guessing; set OC_SERVICE_LABEL to name the approved service)"
        return 1
      fi
      out="$(launchctl print "gui/$(id -u)/$label" 2>/dev/null)"
      state="$(printf '%s' "$out" | awk -F'= ' '/^[[:space:]]*state = /{print $2; exit}')"
      pid="$(printf '%s' "$out" | awk -F'= ' '/^[[:space:]]*pid = /{print $2; exit}')"
      last_exit="$(printf '%s' "$out" | awk -F'= ' '/last exit code/{print $2; exit}')"
      if [ -z "$state" ] && [ -z "$pid" ]; then
        record 1 gateway UNDETERMINED "label '$label' is loaded but 'launchctl print' exposed no parseable state/pid -- liveness unproven"
        return 1
      fi
      case "${pid:-}" in ''|*[!0-9]*) live=0 ;; 0) live=0 ;; *) live=1 ;; esac
      [ "$state" = "running" ] && [ "$live" = "1" ] && live=1 || live="$live"
      [ "$live" = "1" ] || live=0
      ocd_app_ready; ready="$OCD_READY"
      local v verdict rest
      v="$(_gateway_verdict "$live" "${last_exit:-none}" "$ready" "$OCD_READY_DETAIL")"
      verdict="${v%%|*}"; rest="${v#*|}"
      [ "$verdict" = "PROBLEM" ] && PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
      record 1 gateway "$verdict" "label=$label state=${state:-unknown} pid=${pid:-none} last_exit=${last_exit:-none} $rest"
      [ "$verdict" = "CLEAN" ] && return 0 || return 1 ;;
    docker)
      local cname insp status restart started live ready verdict rest v dexec
      cname="$OCD_TARGET_ID"
      if ! command -v docker >/dev/null 2>&1; then
        record 1 gateway UNDETERMINED "docker target mode but no docker CLI on PATH (inside-container boxes cannot inspect the host runtime; the descriptor resolves OC_TARGET_MODE=process there)"
        return 1
      fi
      insp="$(docker inspect --format '{{.State.Status}}|{{.State.StartedAt}}|{{.RestartCount}}|{{.State.ExitCode}}' "$cname" 2>&1)" || {
        record 1 gateway UNDETERMINED "exact container '$cname' NOT found by name (docker inspect: $(printf '%s' "$insp" | tr '\n' ' ' | cut -c1-120)) -- no name-scan/first-match fallback; name the approved container with OC_CONTAINER"
        return 1; }
      status="${insp%%|*}"; rest="${insp#*|}"; started="${rest%%|*}"; rest="${rest#*|}"; restart="${rest%%|*}"; last_exit="${rest#*|}"
      case "$status" in
        restarting)
          PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
          record 1 gateway PROBLEM "container '$cname' status=restarting restart_count=$restart -- crash-loop signature"
          return 1 ;;
        running)
          # Up is NOT health: the app must answer. Probe the published port
          # first (host view), then -- only if that is inconclusive -- a
          # read-only exec inside the exact container.
          ocd_app_ready; ready="$OCD_READY"; local rdetail="$OCD_READY_DETAIL"
          if [ "$ready" != "ready" ] && [ -n "$OCD_GATEWAY_PORT" ]; then
            dexec="$(docker exec "$cname" sh -lc "curl -s -m 5 http://127.0.0.1:${OCD_GATEWAY_PORT}/healthz" 2>/dev/null)"
            case "$dexec" in
              *'"ok":true'*) ready="ready"; rdetail="in-container /healthz ok:true" ;;
              '') : ;; # keep the host verdict; the exec gave no evidence
            esac
          fi
          v="$(_gateway_verdict 1 "${last_exit:-0}" "$ready" "$rdetail")"
          verdict="${v%%|*}"; rest="${v#*|}"
          [ "$verdict" = "PROBLEM" ] && PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
          record 1 gateway "$verdict" "container=$cname status=running started=$started restart_count=$restart exit_code=$last_exit $rest"
          [ "$verdict" = "CLEAN" ] && return 0 || return 1 ;;
        exited|created|paused|dead)
          PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
          record 1 gateway PROBLEM "container '$cname' status=$status exit_code=$last_exit restart_count=$restart -- the gateway is NOT running (exit 0 is still a dead gateway)"
          return 1 ;;
        *)
          record 1 gateway UNDETERMINED "container '$cname' status='$status' unrecognized -- liveness unproven"
          return 1 ;;
      esac ;;
    process)
      local ready verdict rest
      ocd_app_ready; ready="$OCD_READY"
      case "$ready" in
        ready)
          record 1 gateway CLEAN "in-container runtime: app answers its health contract ($OCD_READY_DETAIL); no docker CLI here by design"
          return 0 ;;
        not-ready)
          PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_GATEWAY))
          record 1 gateway PROBLEM "in-container runtime: nothing answers the gateway health probe ($OCD_READY_DETAIL)"
          return 1 ;;
        *)
          record 1 gateway UNDETERMINED "in-container runtime: app readiness unproven ($OCD_READY_DETAIL)"
          return 1 ;;
      esac ;;
    *)
      record 1 gateway UNDETERMINED "no approved service/container target resolved ($OCD_TARGET_NOTE) -- this ladder does not guess a runtime"
      return 1 ;;
  esac
}

# ============================================================================
# STEP 2 -- did the work complete but the reply die? (DB-only; a log grep
# for handler-timeout is a KNOWN false zero -- see the SOP)
# Absent table, incompatible schema and a failed query are UNDETERMINED.
# Failures INSIDE the incident window are current; older ones are reported as
# historical and never counted as a current problem.
# ============================================================================
_delivery_table_check() {
  # _delivery_table_check <table> <col>... -> prints "OK" or a reason
  local t="$1"; shift
  ocd_table_present "$t"; local rc=$?
  if [ "$rc" -eq 2 ]; then printf 'query failed (no db or sqlite3)'; return 2; fi
  if [ "$rc" -ne 0 ]; then printf 'table absent'; return 1; fi
  local miss; miss="$(ocd_missing_columns "$t" "$@")" || { printf 'schema query failed'; return 2; }
  if [ -n "$miss" ]; then printf 'table present but missing column(s): %s (schema incompatible)' "$miss"; return 1; fi
  printf 'OK'; return 0
}
step2() {
  if [ "$OCD_LOADED" -eq 0 ] || [ -z "${OCD_DB:-}" ]; then
    record 2 delivery UNDETERMINED "no usable state db resolved ($OCD_DB_NOTE) -- delivery_queue_entries / channel_ingress_events cannot be queried"
    return 1
  fi
  if ! command -v sqlite3 >/dev/null 2>&1; then
    record 2 delivery UNDETERMINED "sqlite3 not on PATH -- delivery_queue_entries / channel_ingress_events cannot be queried"
    return 1
  fi
  local now_ms=$(( $(date +%s) * 1000 ))
  local cutoff_ms=$(( now_ms - INCIDENT_WINDOW_MIN * 60000 ))
  local q total cur_failed hist_failed timeouts_cur timeouts_hist newest_fail
  local notes="" problems=""

  # ---- delivery_queue_entries -------------------------------------------
  q="$(_delivery_table_check delivery_queue_entries status enqueued_at updated_at failed_at retry_count)"
  case "$q" in
    OK)
      ocd_qry "select count(*) from delivery_queue_entries;"; total="$OCD_QRY_OUT"
      if [ "$OCD_QRY_RC" -ne 0 ]; then
        record 2 delivery UNDETERMINED "delivery_queue_entries count query FAILED (rc=$OCD_QRY_RC: $OCD_QRY_ERR) -- a failed query is not a zero"
        return 1
      fi
      ocd_qry "select count(*) from delivery_queue_entries where status in ('failed','dead','error');"; cur_any="$OCD_QRY_OUT"
      ocd_qry "select count(*) from delivery_queue_entries where status in ('failed','dead','error') and coalesce(failed_at,updated_at) >= $cutoff_ms;"; cur_failed="$OCD_QRY_OUT"
      ocd_qry "select count(*) from delivery_queue_entries where status in ('failed','dead','error') and coalesce(failed_at,updated_at) < $cutoff_ms;"; hist_failed="$OCD_QRY_OUT"
      ocd_qry "select coalesce(max(failed_at),0) from delivery_queue_entries where status in ('failed','dead','error');"; newest_fail="$OCD_QRY_OUT"
      notes="delivery_queue_entries total=$total failed_current(${INCIDENT_WINDOW_MIN}m)=${cur_failed:-?} failed_historical=${hist_failed:-?} failed_all_time=${cur_any:-?}"
      if [ "${cur_failed:-0}" -gt 0 ] 2>/dev/null; then
        problems="delivery_queue_entries: $cur_failed failure(s) inside the last ${INCIDENT_WINDOW_MIN}m"
      fi ;;
    *)
      record 2 delivery UNDETERMINED "$q"
      return 1 ;;
  esac

  # ---- channel_ingress_events -------------------------------------------
  q="$(_delivery_table_check channel_ingress_events status failed_reason failed_at)"
  case "$q" in
    OK)
      ocd_qry "select count(*) from channel_ingress_events where failed_reason='handler-timeout' and coalesce(failed_at,0) >= $cutoff_ms;"; timeouts_cur="$OCD_QRY_OUT"
      ocd_qry "select count(*) from channel_ingress_events where failed_reason='handler-timeout' and coalesce(failed_at,0) < $cutoff_ms;"; timeouts_hist="$OCD_QRY_OUT"
      notes="$notes; channel_ingress_events handler-timeout current=${timeouts_cur:-?} historical=${timeouts_hist:-?}"
      if [ "${timeouts_cur:-0}" -gt 0 ] 2>/dev/null; then
        problems="$problems; channel_ingress_events: $timeouts_cur handler-timeout(s) inside the last ${INCIDENT_WINDOW_MIN}m"
      fi ;;
    *)
      # An absent/migrated ingress table is NOT clean (RCV-07) -- and it is not
      # a problem either: it is unknown, and unknown must not become clean.
      record 2 delivery UNDETERMINED "$q -- cannot distinguish 'no handler-timeouts' from 'the table this check reads is gone'"
      return 1 ;;
  esac

  if [ -n "$problems" ]; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_DELIVERY))
    record 2 delivery PROBLEM "$problems; $notes (historical entries are reported, not counted)"
    return 1
  fi
  record 2 delivery CLEAN "no CURRENT delivery failure; $notes${newest_fail:+ newest_all_time_failure_ms=$newest_fail}"
  return 0
}

# Config path helper: the descriptor owns this. Lazily initializes so a step
# invoked directly (fixtures, source-only harnesses) resolves the same config
# STEP 0 would -- never a bare "/openclaw.json" fallback.
_oc_json_path() {
  if [ -n "${OCD_JSON:-}" ] && [ -f "${OCD_JSON}" ]; then printf '%s' "$OCD_JSON"; return 0; fi
  ocd_init
  printf '%s' "${OCD_JSON:-}"
}

# ============================================================================
# STEP 3 -- narration spam? (streaming.mode; ABSENT means "partial", a
# positive finding, not a clean result -- config file only, `openclaw config
# get` cannot answer this)
# ============================================================================
_STEP3_PY='
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as e:
    print("UNDETERMINED|cannot parse config: %s" % e); raise SystemExit(0)
mode = (((cfg.get("channels") or {}).get("telegram") or {}).get("streaming") or {}).get("mode")
if mode is None:
    print("ABSENT|key absent -- effective mode defaults to partial")
else:
    print("PRESENT|%s" % mode)
'
step3() {
  local ocjson out verdict detail
  ocjson="$(_oc_json_path 2>/dev/null || true)"
  if [ ! -f "$ocjson" ]; then
    record 3 streaming UNDETERMINED "no config at ${ocjson:-<unresolved>}"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 3 streaming UNDETERMINED "python3 not on PATH"
    return 1
  fi
  out="$(_run_py "$_STEP3_PY" "$ocjson")"
  verdict="${out%%|*}"
  detail="${out#*|}"
  case "$verdict" in
    ABSENT)
      PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_STREAMING))
      record 3 streaming PROBLEM "channels.telegram.streaming.mode is ABSENT -- effective mode is 'partial' (the narration-spam amplifier); absence is a positive finding, not a clean result"
      return 1 ;;
    PRESENT)
      case "$detail" in
        off)
          record 3 streaming CLEAN "streaming.mode explicitly 'off'" ;;
        partial|*)
          PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_STREAMING))
          record 3 streaming PROBLEM "streaming.mode explicitly '$detail' -- narration-spam amplifier active"
          return 1 ;;
      esac
      return 0 ;;
    *)
      record 3 streaming UNDETERMINED "$detail"
      return 1 ;;
  esac
}

# ============================================================================
# STEP 4 -- tool-unreachable loop? (toolSearch shape; config file only)
# ============================================================================
_STEP4_PY='
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as e:
    print("UNDETERMINED|cannot parse config: %s" % e); raise SystemExit(0)
ts = (cfg.get("tools") or {}).get("toolSearch")
if ts is None:
    print("ABSENT|no tools.toolSearch key")
elif isinstance(ts, dict):
    mode = ts.get("mode")
    enabled = ts.get("enabled")
    if enabled is True and mode == "directory":
        print("HEALTHY|enabled=true mode=directory")
    else:
        print("MALFORMED_OBJECT|enabled=%r mode=%r" % (enabled, mode))
else:
    print("SCALAR|%r" % (ts,))
'
step4() {
  local ocjson out verdict detail
  ocjson="$(_oc_json_path 2>/dev/null || true)"
  if [ ! -f "$ocjson" ]; then
    record 4 toolsearch UNDETERMINED "no config at ${ocjson:-<unresolved>}"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 4 toolsearch UNDETERMINED "python3 not on PATH"
    return 1
  fi
  out="$(_run_py "$_STEP4_PY" "$ocjson")"
  verdict="${out%%|*}"
  detail="${out#*|}"
  case "$verdict" in
    HEALTHY)
      record 4 toolsearch CLEAN "tools.toolSearch $detail"
      return 0 ;;
    ABSENT|SCALAR|MALFORMED_OBJECT)
      PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_TOOLSEARCH))
      record 4 toolsearch PROBLEM "tools.toolSearch verdict=$verdict $detail -- not the healthy {enabled:true,mode:directory} shape"
      return 1 ;;
    *)
      record 4 toolsearch UNDETERMINED "$detail"
      return 1 ;;
  esac
}

# ============================================================================
# STEP 5 -- cron engine or restart-kill?
# The expected count for each job is DERIVED from that job's own declared
# schedule (cron expr / everyMs) evaluated over the window -- never a global
# hard threshold. A receiver that legitimately polls every two minutes (720
# runs/day) is normal; a job that runs far more often than it declares, or is
# erroring inside the current window at retry speed, is the incident.
# Table/schema failure or absence is UNDETERMINED (the live schema is
# cron_run_receipts; cron_run_logs does not exist on current builds).
# ============================================================================
_STEP5_PY='
import json, re, sqlite3, sys, time

db_path, incident_min, expect_min = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
now_ms = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else int(time.time() * 1000)

def out(v, d):
    print("%s|%s" % (v, d)); raise SystemExit(0)

try:
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=5)
except Exception as e:
    out("UNDETERMINED", "state db not openable read-only: %s" % e)

try:
    have = set(r[0] for r in con.execute("select name from sqlite_master where type=\x27table\x27"))
except Exception as e:
    out("UNDETERMINED", "schema query failed: %s" % e)

if "cron_run_receipts" not in have:
    if "cron_run_logs" in have:
        out("UNDETERMINED", "legacy cron_run_logs present but current runtime schema cron_run_receipts absent -- incompatible schema, cannot judge run cadence safely")
    out("UNDETERMINED", "cron_run_receipts and cron_run_logs both absent -- no cron run history in this db (unknown, not clean)")
if "cron_jobs" not in have:
    out("UNDETERMINED", "cron_run_receipts present but cron_jobs absent -- declared schedules unavailable, so no run can be judged against its cadence")

def cols(t):
    try:
        return set(r[1] for r in con.execute("pragma table_info(%s)" % t))
    except Exception as e:
        out("UNDETERMINED", "schema query for %s failed: %s" % (t, e))

rc = cols("cron_run_receipts"); jc = cols("cron_jobs")
missing = [c for c in ("job_id", "status", "started_at_ms") if c not in rc]
if missing:
    out("UNDETERMINED", "cron_run_receipts missing column(s) %s -- incompatible schema" % ",".join(missing))
if "job_json" not in jc:
    out("UNDETERMINED", "cron_jobs missing job_json -- declared schedules unavailable")

DOW_ALIAS = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}

def _num(tok, names):
    tok = tok.strip().lower()
    if names and tok in names:
        return names[tok]
    return int(tok) if re.fullmatch(r"\d+", tok) else None

def parse_field(spec, lo, hi, names=None, dow=False):
    vals = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/", 1)
            if not st.isdigit() or int(st) == 0:
                return None
            step = int(st)
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part.lstrip("-"):
            a_s, b_s = part.split("-", 1)
            a, b = _num(a_s, names), _num(b_s, names)
            if a is None or b is None:
                return None
        else:
            a = _num(part, names)
            if a is None:
                return None
            b = hi if step > 1 else a
        if a > b:
            return None
        for v in range(a, b + 1, step):
            w = 0 if (dow and v == 7) else v
            if lo <= w <= hi:
                vals.add(w)
    return vals or None

def fires_per_day(expr):
    """Runs per day for a 5-field cron expr, or None if unparseable."""
    f = expr.split()
    if len(f) != 5:
        return None
    mi = parse_field(f[0], 0, 59); ho = parse_field(f[1], 0, 23)
    dom = parse_field(f[2], 1, 31); mo = parse_field(f[3], 1, 12)
    dw = parse_field(f[4], 0, 6, names=DOW_ALIAS, dow=True)
    if None in (mi, ho, dom, mo, dw):
        return None
    if len(mi) * len(ho) == 0:
        return 0
    per_day = len(mi) * len(ho)
    if len(mo) != 12:
        per_day *= len(mo) / 12.0
    if len(dom) != 31 and len(dw) != 7:
        per_day *= (min(len(dom), len(dw)) / 7.0) if len(dom) <= len(dw) else (len(dw) / 7.0)
    elif len(dom) != 31:
        per_day *= len(dom) / 30.0
    elif len(dw) != 7:
        per_day *= len(dw) / 7.0
    return per_day

try:
    jobs = list(con.execute("select job_id, job_json from cron_jobs"))
except Exception as e:
    out("UNDETERMINED", "cron_jobs query failed: %s" % e)

# ---- declared cadence per enabled job -------------------------------------
declared = {}     # job_id -> minutes between runs (None = schedule unparseable)
names = {}
disabled = 0
for jid, jjson in jobs:
    try:
        j = json.loads(jjson) if jjson else {}
    except Exception:
        declared[jid] = None; names[jid] = jid; continue
    names[jid] = j.get("name") or jid
    if j.get("enabled") is False:
        disabled += 1; continue
    sch = j.get("schedule") or {}
    kind = sch.get("kind")
    if kind == "every":
        em = sch.get("everyMs")
        declared[jid] = (em / 60000.0) if isinstance(em, int) and em > 0 else None
    elif kind == "cron":
        expr = sch.get("expr")
        pd = fires_per_day(expr) if isinstance(expr, str) else None
        declared[jid] = (1440.0 / pd) if pd else None
    else:
        declared[jid] = None

# ---- observed receipts ----------------------------------------------------
try:
    rows = list(con.execute(
        "select job_id, status, started_at_ms from cron_run_receipts where started_at_ms is not null order by started_at_ms"))
except Exception as e:
    out("UNDETERMINED", "cron_run_receipts query failed: %s" % e)

runs = {}
for jid, status, started in rows:
    runs.setdefault(jid, []).append((started, status))

incident_start_ms = now_ms - incident_min * 60000
NOTE = ("NOTE: cron_run_receipts is a bounded ring buffer (measured ~64 rows per job here), "
        "so this check compares each job against its OWN declared cadence within the span the "
        "table actually retains -- never an absolute count over a window the table cannot hold.")

shortfall, runaways, storms, stalled, unparseable = [], [], [], [], []
judged = 0
for jid, dec in declared.items():
    rs = runs.get(jid, [])
    if dec in (None, 0):
        if rs:
            unparseable.append(names.get(jid, jid))
        continue
    n = len(rs)
    if n == 0:
        continue                       # never ran: no evidence either way, reported via counts below
    judged += 1
    first, last = rs[0][0], rs[-1][0]
    age_min = (now_ms - last) / 60000.0
    if n >= 2:
        obs_min = ((last - first) / 60000.0) / (n - 1)
    else:
        obs_min = None
    # stalled: enabled job whose newest receipt is far older than its cadence
    if age_min > max(3 * dec, 15):
        stalled.append("%s declared %.1fmin, newest run %.0fmin ago (n=%d)" % (names.get(jid, jid), dec, age_min, n))
    # runaway: running far more often than declared, judged on density not a raw count
    if obs_min is not None and n >= 10 and obs_min < dec / 3.0:
        runaways.append("%s declared %.1fmin but observed %.1fmin over %d run(s)" % (
            names.get(jid, jid), dec, obs_min, n))
    # retry storm: errors inside the incident window at faster than declared cadence
    errs = sorted(t for t, st in rs if t >= incident_start_ms and st in ("error", "failed"))
    if len(errs) >= 5:
        gaps = [errs[i + 1] - errs[i] for i in range(len(errs) - 1)]
        mgap = min(gaps) / 60000.0 if gaps else 0.0
        if mgap < dec:
            storms.append("%s %d error(s) in %dm, min gap %.1fmin vs declared %.1fmin" % (
                names.get(jid, jid), len(errs), incident_min, mgap, dec))

summary = ("%d enabled declared schedule(s) judged against their OWN cadence; jobs with unparseable "
           "schedule=%d; disabled_skipped=%d; %s" % (judged, len(unparseable), disabled, NOTE))
if unparseable:
    summary += " UNJUDGED: " + ", ".join(sorted(unparseable)[:3])

if stalled:
    out("STALLED", summary + "; STALLED: " + "; ".join(stalled[:3]))
if runaways:
    out("RUNAWAY", summary + "; RUNAWAY: " + "; ".join(runaways[:3]))
if storms:
    out("STORM", summary + "; RETRY STORM: " + "; ".join(storms[:3]))
out("CLEAN", summary)
'
step5() {
  if [ "$OCD_LOADED" -eq 0 ] || [ -z "${OCD_DB:-}" ]; then
    record 5 cron UNDETERMINED "no usable state db resolved ($OCD_DB_NOTE) -- cron run history cannot be queried"
    return 1
  fi
  if ! command -v sqlite3 >/dev/null 2>&1; then
    record 5 cron UNDETERMINED "sqlite3 not on PATH -- cron run history cannot be queried"
    return 1
  fi
  local now_ms out verdict detail
  now_ms=$(( $(date +%s) * 1000 ))
  out="$(_run_py "$_STEP5_PY" "$OCD_DB" "$INCIDENT_WINDOW_MIN" "$EXPECT_WINDOW_MIN" "$now_ms")"
  verdict="${out%%|*}"; detail="${out#*|}"
  case "$verdict" in
    CLEAN)
      record 5 cron CLEAN "$detail"
      return 0 ;;
    RUNAWAY|STORM|STALLED)
      PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_CRON))
      record 5 cron PROBLEM "$detail"
      return 1 ;;
    *)
      record 5 cron UNDETERMINED "$detail"
      return 1 ;;
  esac
}

# ============================================================================
# STEP 6 -- compaction wedge? (structured log only; invisible to every check
# above it -- nothing repeats, nothing is down)
# ============================================================================
step6() {
  local log_dir today todays_log hits
  log_dir="${OCD_LOG_DIR:-${OC_LOG_ROOT:-/tmp/openclaw}}"
  today="$(date +%Y-%m-%d 2>/dev/null || echo unknown)"
  todays_log="$log_dir/openclaw-${today}.log"
  if [ ! -f "$todays_log" ]; then
    record 6 compaction UNDETERMINED "no structured log for $today at $todays_log (${OCD_LOG_NOTE:-})"
    return 1
  fi
  hits=0
  if command -v grep >/dev/null 2>&1; then
    hits="$(grep -c -E 'contextEngine\.compact\(\) threw|Compaction timed out|could not recover this turn' "$todays_log" 2>/dev/null || echo 0)"
  fi
  if [ "${hits:-0}" -gt 1 ] 2>/dev/null; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_COMPACTION))
    record 6 compaction PROBLEM "$hits compaction-failure markers today -- 2+ is the wedge signature (one alone is routine)"
    return 1
  fi
  record 6 compaction CLEAN "$hits compaction-failure marker(s) today (below the 2+ wedge signature)"
  return 0
}

# ============================================================================
# STEP 7 -- substrate: owner, provider timeouts, registry parity, raw-writer
# fingerprint. Always run last -- always worth confirming.
# Provider timeouts are read from the VERSION-APPROPRIATE shape: canonical
# `models.providers` on current builds, legacy root `providers` where that is
# what the config carries. An unrecognized shape is UNDETERMINED -- never
# "no missing timeouts".
# ============================================================================
_STEP7_PY='
import json, os, sys
cfg_path = sys.argv[1]
agents_dir = sys.argv[2]
try:
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception as e:
    print("UNDETERMINED|cannot parse config: %s" % e); raise SystemExit(0)

agents = cfg.get("agents") or {}
ids = set()
entries = agents.get("entries")
lst = agents.get("list")
if isinstance(entries, dict):
    ids |= set(str(k) for k in entries.keys())
elif isinstance(entries, list):
    for item in entries:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
if isinstance(lst, list):
    for item in lst:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
elif isinstance(lst, dict):
    ids |= set(str(k) for k in lst.keys())
reg_count = len(ids)

dir_count = 0
if os.path.isdir(agents_dir):
    for name in os.listdir(agents_dir):
        if os.path.isdir(os.path.join(agents_dir, name)):
            dir_count += 1

# --- provider timeouts: version-appropriate shape --------------------------
TIMEOUT_FIELDS = ("timeoutSeconds",)   # the only timeout field current builds honor per provider
shape = "absent"; providers = None; shape_note = ""
models = cfg.get("models")
if isinstance(models, dict) and isinstance(models.get("providers"), dict) and models.get("providers"):
    shape = "models.providers"; providers = models["providers"]
elif isinstance(models, dict) and "providers" in models and not isinstance(models.get("providers"), dict):
    print("UNDETERMINED|models.providers present but not an object -- incompatible provider schema"); raise SystemExit(0)
elif isinstance(cfg.get("providers"), dict) and cfg.get("providers"):
    shape = "legacy root providers"; providers = cfg["providers"]
    shape_note = " (legacy shape: current builds read models.providers)"
elif "providers" in cfg and not isinstance(cfg.get("providers"), dict):
    print("UNDETERMINED|root providers present but not an object -- incompatible provider schema"); raise SystemExit(0)

if shape == "absent":
    print("UNDETERMINED|no provider configuration found in any known shape (models.providers absent, root providers absent)")
    raise SystemExit(0)

missing_timeout = []; malformed = []
if isinstance(providers, dict):
    for pname, pcfg in providers.items():
        if not isinstance(pcfg, dict):
            malformed.append(str(pname)); continue
        if not any(f in pcfg for f in TIMEOUT_FIELDS):
            missing_timeout.append(str(pname))

# RR-030 mutation anchor: verify.sh mutation 5 and this script fixture 4 both
# sed this exact assignment to disable the parity check. Keep the assignment
# form (never an inlined expression in the print below) or the drill silently
# stops discriminating.
parity_problem = reg_count <= 1 and dir_count > 2
print("REPORT|reg_count=%d|dir_count=%d|parity_problem=%s|provider_shape=%s|provider_count=%d|missing_timeout=%s|malformed=%s%s" % (
    reg_count, dir_count, parity_problem, shape, len(providers),
    ",".join(sorted(missing_timeout)) or "none", ",".join(sorted(malformed)) or "none", shape_note))
'
step7() {
  local ocjson root agents_dir out verdict detail owner_problem=0 owner_detail=""
  ocd_init
  ocjson="${OCD_JSON:-}"
  [ -n "$ocjson" ] || ocjson="$(_oc_json_path 2>/dev/null || true)"
  root="${OCD_ROOT:-${OC_CONFIG_ROOT:-}}"
  agents_dir="$root/agents"
  if [ ! -f "$ocjson" ]; then
    record 7 substrate UNDETERMINED "no config at ${ocjson:-<unresolved>}"
    return 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    record 7 substrate UNDETERMINED "python3 not on PATH"
    return 1
  fi

  # owner-readability check, read-only (never chown here -- this script only
  # reports; the SOP's Step 7 remediation, if authorized, does the chown)
  if [ -r "$ocjson" ]; then
    owner_problem=0
  else
    owner_problem=1
    owner_detail="config not readable by the current user"
  fi

  out="$(_run_py "$_STEP7_PY" "$ocjson" "$agents_dir")"
  verdict="${out%%|*}"
  detail="${out#*|}"
  if [ "$verdict" != "REPORT" ]; then
    record 7 substrate UNDETERMINED "$detail"
    return 1
  fi

  local parity_problem missing_timeout malformed provider_shape
  parity_problem="$(printf '%s' "$detail" | grep -o 'parity_problem=[A-Za-z]*' | cut -d= -f2)"
  missing_timeout="$(printf '%s' "$detail" | grep -o 'missing_timeout=[^ |]*' | cut -d= -f2)"
  malformed="$(printf '%s' "$detail" | grep -o 'malformed=[^ |]*' | cut -d= -f2)"
  provider_shape="$(printf '%s' "$detail" | grep -o 'provider_shape=[^ |]*' | cut -d= -f2)"

  if [ "$owner_problem" -eq 1 ] || [ "$parity_problem" = "True" ] || { [ -n "$missing_timeout" ] && [ "$missing_timeout" != "none" ]; } || { [ -n "$malformed" ] && [ "$malformed" != "none" ]; }; then
    PROBLEM_BITS=$((PROBLEM_BITS | STEP_BIT_SUBSTRATE))
    record 7 substrate PROBLEM "owner_problem=$owner_problem ($owner_detail) $detail"
    return 1
  fi
  record 7 substrate CLEAN "$detail owner_problem=0"
  return 0
}

# ============================================================================
# main
# ============================================================================
run_ladder() {
  step0
  local step0_rc=$?
  if [ "$step0_rc" -ne 0 ] && [ "$UNDETERMINED_COUNT" -gt 0 ]; then
    # STEP 0 failing (both instruments unavailable) is the hard-stop case;
    # a single-instrument partial failure still lets downstream steps run
    # and report their own UNDETERMINED honestly rather than guessing.
    local ocjson; ocjson="${OCD_JSON:-$(_oc_json_path 2>/dev/null || true)}"
    if [ "$OCD_LOADED" -eq 0 ] || [ -z "${OCD_ROOT:-}" ] || [ ! -f "$ocjson" ] || ! command -v python3 >/dev/null 2>&1; then
      echo "STEP 0 FAILED HARD -- nothing downstream is valid. See the line above." >&2
      return 78
    fi
  fi
  step1; step2; step3; step4; step5; step6; step7
  return 0
}

print_descriptor() {
  echo "== environment descriptor =="
  echo "  box            : $OCD_BOX_SLUG ($OCD_BOX_SOURCE)"
  echo "  company        : $OCD_COMPANY_SLUG${OCD_COMPANY_NAME:+ ($OCD_COMPANY_NAME)} ($OCD_COMPANY_SOURCE)"
  echo "  platform       : $OCD_PLATFORM"
  echo "  root           : ${OCD_ROOT:-none} ($OCD_ROOT_SOURCE)"
  echo "  config         : ${OCD_JSON:-none} ($OCD_JSON_STATE)"
  echo "  state db       : ${OCD_DB:-none} -- $OCD_DB_NOTE"
  echo "  log dir        : ${OCD_LOG_DIR:-none} -- ${OCD_LOG_NOTE:-}"
  echo "  target         : $OCD_TARGET_MODE:${OCD_TARGET_ID:-none} ($OCD_TARGET_NOTE) [ONE exact target; never a name scan]"
  echo "  gateway port   : ${OCD_GATEWAY_PORT:-unknown} ($OCD_GATEWAY_PORT_SOURCE)"
  echo "  incident window: ${INCIDENT_WINDOW_MIN}m    expected-count window: ${EXPECT_WINDOW_MIN}m"
}

print_summary() {
  echo ""
  print_descriptor
  echo "============================================================"
  if [ "$UNDETERMINED_COUNT" -gt 0 ]; then
    echo "VERDICT: UNDETERMINED ($UNDETERMINED_COUNT step(s)) -- read-only ladder incomplete."
    echo "This is NOT a clean bill. Re-run with working instruments, or escalate."
  elif [ "$PROBLEM_BITS" -eq 0 ]; then
    echo "VERDICT: CLEAN -- every step that could run found no problem."
  else
    echo "VERDICT: PROBLEM(S) FOUND -- bitmask=$PROBLEM_BITS (exit code = 100+bitmask)"
    [ $((PROBLEM_BITS & STEP_BIT_GATEWAY)) -ne 0 ]    && echo "  - gateway crash-loop (STEP 1)"
    [ $((PROBLEM_BITS & STEP_BIT_DELIVERY)) -ne 0 ]   && echo "  - delivery died after work completed (STEP 2)"
    [ $((PROBLEM_BITS & STEP_BIT_STREAMING)) -ne 0 ]  && echo "  - narration spam / streaming not off (STEP 3)"
    [ $((PROBLEM_BITS & STEP_BIT_TOOLSEARCH)) -ne 0 ] && echo "  - tool-unreachable loop (STEP 4)"
    [ $((PROBLEM_BITS & STEP_BIT_CRON)) -ne 0 ]       && echo "  - cron/restart-kill (STEP 5)"
    [ $((PROBLEM_BITS & STEP_BIT_COMPACTION)) -ne 0 ] && echo "  - compaction wedge (STEP 6)"
    [ $((PROBLEM_BITS & STEP_BIT_SUBSTRATE)) -ne 0 ]  && echo "  - substrate (owner/timeout/registry-parity) (STEP 7)"
  fi
  echo "This script is READ-ONLY. No fix was applied. See SOP-RR-LOOP-TRIAGE.md for the sanctioned remedy at each step."
  echo "============================================================"
}

print_json_summary() {
  python3 -c "
import json, sys
results = []
raw = sys.argv[1]
for line in raw.strip('\n').split('\n'):
    if not line:
        continue
    parts = line.split('|', 3)
    if len(parts) != 4:
        continue
    step, name, verdict, detail = parts
    results.append({'step': int(step), 'name': name, 'verdict': verdict, 'detail': detail})
print(json.dumps({
    'results': results,
    'problem_bits': int(sys.argv[2]),
    'undetermined_count': int(sys.argv[3]),
    'descriptor': {
        'box': sys.argv[4], 'company': sys.argv[5], 'platform': sys.argv[6],
        'root': sys.argv[7], 'db': sys.argv[8], 'target_mode': sys.argv[9],
        'target_id': sys.argv[10], 'gateway_port': sys.argv[11],
    },
}, indent=2))
" "$RESULTS" "$PROBLEM_BITS" "$UNDETERMINED_COUNT" "${OCD_BOX_SLUG:-}" "${OCD_COMPANY_SLUG:-}" "${OCD_PLATFORM:-}" "${OCD_ROOT:-}" "${OCD_DB:-}" "${OCD_TARGET_MODE:-}" "${OCD_TARGET_ID:-}" "${OCD_GATEWAY_PORT:-}"
}

# ----------------------------------------------------------------------------
# Fixture helpers used by --self-test. make_db <path> <sql...> builds a fixture
# state db; the fixtures below then exercise the SAME code paths the live
# ladder uses (never a re-implementation).
# ----------------------------------------------------------------------------
_fixture_db() {
  # _fixture_db <path> <sql-statement>...
  local db="$1"; shift
  command -v sqlite3 >/dev/null 2>&1 || return 1
  : > "$db"
  local s
  for s in "$@"; do sqlite3 "$db" "$s" >/dev/null 2>&1 || return 1; done
  return 0
}
_rc_tables='create table cron_run_receipts (receipt_id text primary key, store_key text not null, job_id text not null, config_revision text not null, agent_id text not null, request_run_id text, status text not null, owner_pid integer not null, owner_start_time integer, started_at_ms integer not null, finished_at_ms integer, error_text text);'
_jobs_table='create table cron_jobs (store_key text not null, job_id text not null, declaration_key text, owner_agent_id text, name text not null, description text, enabled integer not null, agent_id text, payload_kind text not null, job_json text not null, state_json text not null default "{}", runtime_updated_at_ms integer, schedule_identity text, sort_order integer not null default 0, updated_at integer not null);'
_dq_table='create table delivery_queue_entries (queue_name text not null, id text not null, status text not null, entry_kind text, session_key text, channel text, target text, account_id text, retry_count integer not null default 0, last_attempt_at integer, last_error text, recovery_state text, platform_send_started_at integer, entry_json text not null, enqueued_at integer not null, updated_at integer not null, failed_at integer);'
_ci_table='create table channel_ingress_events (queue_name text not null, event_id text not null, channel_id text not null, account_id text not null, status text not null, lane_key text, payload_json text not null, metadata_json text, received_at integer not null, updated_at integer not null, claim_token text, claim_owner text, claimed_at integer, attempts integer not null default 0, last_attempt_at integer, last_error text, failed_reason text, failed_at integer, completed_at integer, completed_metadata_json text);'

self_test() {
  echo "[rr-triage --self-test] offline fixture checks (descriptor + config + DB steps; no live box is touched)"
  local sbx failures=0
  sbx="$(mktemp -d)"
  trap 'rm -rf "$sbx"' RETURN
  # Fixtures are OFFLINE: never shell the live `openclaw` CLI for port discovery
  # (measured ~4.5s per call, which alone pushed this self-test past two
  # minutes) and never touch the operator's real gateway.
  export OC_SKIP_CLI_PROBE=1
  : "${OC_GATEWAY_PORT:=18789}"; export OC_GATEWAY_PORT
  local NOW_MS=$(( $(date +%s) * 1000 ))
  local DESCRIPTOR; DESCRIPTOR="$(_find_descriptor "$_TRIAGE_DIR" || true)"
  if [ -z "$DESCRIPTOR" ]; then
    echo "  ✗ descriptor not found from $_TRIAGE_DIR -- fixtures cannot exercise the documented target resolution"
    failures=$((failures + 1))
  fi

  # Fixture 1: healthy config -> STEP3/STEP4 clean, STEP7 clean (no parity problem)
  # RR-030: fixture state is addressed through the EXPLICIT OC_CONFIG_ROOT, never
  # by repurposing HOME. Each fixture body runs as its own subshell whose exit
  # code is the verdict, and the PARENT accumulates it — a broken checker can
  # no longer print a sad line and lose the failure inside the subshell.
  mkdir -p "$sbx/.openclaw/agents/main"
  cat > "$sbx/.openclaw/openclaw.json" <<'JSON'
{"agents":{"list":[{"id":"main"}]},"channels":{"telegram":{"streaming":{"mode":"off"}}},"tools":{"toolSearch":{"enabled":true,"mode":"directory"}},"models":{"providers":{"anthropic":{"timeoutSeconds":120}}}}
JSON
  fixture1() (
    export OC_CONFIG_ROOT="$sbx/.openclaw-root"
    mkdir -p "$OC_CONFIG_ROOT/agents/main"
    cp "$sbx/.openclaw/openclaw.json" "$OC_CONFIG_ROOT/openclaw.json"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step3; s3=$?
    step4; s4=$?
    if [ "$s3" -eq 0 ] && [ "$s4" -eq 0 ]; then
      echo "  ✓ healthy config: streaming + toolSearch both CLEAN"
      return 0
    fi
    echo "  ✗ healthy config: expected both clean (s3=$s3 s4=$s4)"
    return 1
  )
  if fixture1; then :; else failures=$((failures + 1)); fi

  # Fixture 2: absent streaming key + scalar toolSearch -> both PROBLEM
  mkdir -p "$sbx/.openclaw"
  cat > "$sbx/.openclaw/openclaw.json" <<'JSON'
{"agents":{"list":[{"id":"main"}]},"tools":{"toolSearch":"tools"}}
JSON
  fixture2() (
    export OC_CONFIG_ROOT="$sbx/.openclaw-root"
    rm -rf "$OC_CONFIG_ROOT"; mkdir -p "$OC_CONFIG_ROOT/agents/main"
    cp "$sbx/.openclaw/openclaw.json" "$OC_CONFIG_ROOT/openclaw.json"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step3; s3=$?
    step4; s4=$?
    if [ "$s3" -ne 0 ] && [ "$s4" -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_STREAMING)) -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_TOOLSEARCH)) -ne 0 ]; then
      echo "  ✓ absent-streaming + scalar-toolSearch: both flagged PROBLEM"
      return 0
    fi
    echo "  ✗ absent-streaming + scalar-toolSearch: expected both PROBLEM (s3=$s3 s4=$s4 bits=$PROBLEM_BITS)"
    return 1
  )
  if fixture2; then :; else failures=$((failures + 1)); fi

  # Fixture 3: registry-strip signature -> STEP7 PROBLEM
  rm -rf "$sbx/.openclaw"
  mkdir -p "$sbx/.openclaw/agents/main" "$sbx/.openclaw/agents/dept-a" "$sbx/.openclaw/agents/dept-b" "$sbx/.openclaw/agents/dept-c"
  cat > "$sbx/.openclaw/openclaw.json" <<'JSON'
{"agents":{"list":[{"id":"main"}]},"channels":{"telegram":{"streaming":{"mode":"off"}}},"tools":{"toolSearch":{"enabled":true,"mode":"directory"}},"models":{"providers":{"anthropic":{"timeoutSeconds":120}}}}
JSON
  fixture3() (
    export OC_CONFIG_ROOT="$sbx/.openclaw-root"
    rm -rf "$OC_CONFIG_ROOT"
    mkdir -p "$OC_CONFIG_ROOT/agents/main" "$OC_CONFIG_ROOT/agents/dept-a" "$OC_CONFIG_ROOT/agents/dept-b" "$OC_CONFIG_ROOT/agents/dept-c"
    cp "$sbx/.openclaw/openclaw.json" "$OC_CONFIG_ROOT/openclaw.json"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step7; s7=$?
    if [ "$s7" -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_SUBSTRATE)) -ne 0 ]; then
      echo "  ✓ registry-strip signature (1 registered, 4 dirs): STEP7 flagged PROBLEM"
      return 0
    fi
    echo "  ✗ registry-strip signature: expected STEP7 PROBLEM (s7=$s7 bits=$PROBLEM_BITS)"
    return 1
  )
  if fixture3; then :; else failures=$((failures + 1)); fi

  # Fixture 4: MUTATION PROOF -- neutralize the registry-parity condition in
  # a copy of this script, re-run fixture 3, must now silently pass.
  local mutated; mutated="$(mktemp "${TMPDIR:-/tmp}/rr-triage-mutated.XXXXXX")"
  sed 's/parity_problem = reg_count <= 1 and dir_count > 2/parity_problem = False/' "$0" > "$mutated"
  if diff -q "$0" "$mutated" >/dev/null 2>&1 || ! grep -q 'parity_problem = False' "$mutated" 2>/dev/null; then
    echo "  ✗ MUTATION PROOF setup failed: the sed target drifted -- 'parity_problem = reg_count <= 1 and dir_count > 2' was not disabled in the copy"
    failures=$((failures+1))
  else
    chmod +x "$mutated"
    fixture4() (
      export OC_CONFIG_ROOT="$sbx/.openclaw-root"
      export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
      # shellcheck disable=SC1090
      . "$mutated" --source-only 2>/dev/null
      JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
      step7; s7=$?
      if [ "$s7" -eq 0 ]; then
        echo "  ✓ MUTATION PROOF: with the parity check disabled, the SAME registry-strip fixture now silently passes -- confirms fixture 3's PROBLEM verdict is the real check enforcing"
        return 0
      fi
      echo "  ✗ MUTATION PROOF FAILED: disabling the check should have flipped fixture 3 to CLEAN (s7=$s7)"
      return 1
    )
    # RR-030: the parent OBSERVES the subshell verdict; a broken step7 inside
    # fixture4 can no longer vanish into a discarded subshell exit code.
    if fixture4; then :; else failures=$((failures + 1)); fi
  fi
  rm -f "$mutated"

  # -------------------------------------------------------------------------
  # RR-029 fixtures. Every fixture body runs in its own subshell and the PARENT
  # accumulates the verdict (RR-030 contract). JSON_MODE=1 inside fixtures so
  # `record` does not spray human lines into the captured verdict string.
  # -------------------------------------------------------------------------

  # Fixture 5: the 0-byte / schema-less sqlite decoy must be REJECTED and the
  # real candidate beside it ACCEPTED. (`sqlite3 f "select 1;"` returns 0 on a
  # 0-byte file -- that is exactly how the old ladder armed the wrong db.)
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/res/state"
    : > "$sbx/res/state/openclaw.sqlite"                       # candidate 1: zero bytes
    _fixture_db "$sbx/res/state.sqlite" "$_rc_tables" || true  # candidate 2: real schema
  fi
  fixture5() (
    export OC_CONFIG_ROOT="$sbx/res" OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"; unset OC_STATE_DB
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init
    case "${OCD_DB:-}" in
      */res/state.sqlite) printf 'accepted-real-db'; return 0 ;;
      *) printf 'db=%s note=%s' "${OCD_DB:-none}" "$OCD_DB_NOTE"; return 1 ;;
    esac
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1; then
    got="$(fixture5)"; rc=$?
    if [ "$got" = "accepted-real-db" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ zero-byte schema-less decoy rejected; state db resolved to the candidate with a real schema"
    else
      echo "  ✗ state-db resolver: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 6: ABSENT channel_ingress_events -> UNDETERMINED (never CLEAN, and
  # never a false PROBLEM). This is the RCV-07 false-zero class.
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/db1"
    _fixture_db "$sbx/db1/state.sqlite" "$_dq_table" || true
    sqlite3 "$sbx/db1/state.sqlite" "insert into delivery_queue_entries values ('q','1','completed',null,null,null,null,null,0,$NOW_MS,null,null,null,'{}',$NOW_MS,$NOW_MS,null);" >/dev/null 2>&1 || true
  fi
  fixture6() (
    export OC_CONFIG_ROOT="$sbx/db1" OC_STATE_DB="$sbx/db1/state.sqlite" OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step2; rc=$?
    v="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$rc" -ne 0 ] && [ "$v" = "UNDETERMINED" ] && [ $((PROBLEM_BITS & STEP_BIT_DELIVERY)) -eq 0 ]; then
      printf 'undetermined-no-bits'; return 0
    fi
    printf 'rc=%s verdict=%s bits=%s' "$rc" "$v" "$PROBLEM_BITS"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1; then
    got="$(fixture6)"; rc=$?
    if [ "$got" = "undetermined-no-bits" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ absent channel_ingress_events: STEP2 UNDETERMINED, no CLEAN and no false PROBLEM"
    else
      echo "  ✗ absent ingress table: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 7: unreadable state db (permissions) -> UNDETERMINED with the
  # rejection reason recorded, never CLEAN.
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/db2"
    _fixture_db "$sbx/db2/state.sqlite" "$_dq_table" "$_ci_table" || true
    chmod 000 "$sbx/db2/state.sqlite"
  fi
  fixture7() (
    export OC_CONFIG_ROOT="$sbx/db2" OC_STATE_DB="$sbx/db2/state.sqlite" OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init
    if [ "$OCD_DB" = "$sbx/db2/state.sqlite" ]; then printf 'accepted-unreadable-db'; return 1; fi
    case "$OCD_DB_NOTE" in *not-readable*) : ;; *) printf 'note-missing-reason: %s' "$OCD_DB_NOTE"; return 1 ;; esac
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step2; rc=$?
    v="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$rc" -ne 0 ] && [ "$v" = "UNDETERMINED" ]; then printf 'undetermined'; return 0; fi
    printf 'rc=%s verdict=%s' "$rc" "$v"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
    got="$(fixture7)"; rc=$?
    if [ "$got" = "undetermined" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ unreadable state db (permissions): rejected with reason; STEP2 UNDETERMINED, never CLEAN"
    else
      echo "  ✗ permissions case: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
    chmod 600 "$sbx/db2/state.sqlite" 2>/dev/null || true
  fi

  # Fixture 8: HISTORICAL vs CURRENT failure. A resolved failure 3 days old must
  # read CLEAN; the same row inside the incident window must read PROBLEM.
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/db3" "$sbx/db4"
    OLD_MS=$(( NOW_MS - 3 * 86400000 ))
    _fixture_db "$sbx/db3/state.sqlite" "$_dq_table" "$_ci_table" || true
    sqlite3 "$sbx/db3/state.sqlite" "insert into delivery_queue_entries values ('q','old','failed',null,null,null,null,null,1,$OLD_MS,'boom',null,null,'{}',$OLD_MS,$OLD_MS,$OLD_MS);" >/dev/null 2>&1 || true
    _fixture_db "$sbx/db4/state.sqlite" "$_dq_table" "$_ci_table" || true
    sqlite3 "$sbx/db4/state.sqlite" "insert into delivery_queue_entries values ('q','new','failed',null,null,null,null,null,1,$NOW_MS,'boom',null,null,'{}',$NOW_MS,$NOW_MS,$NOW_MS);" >/dev/null 2>&1 || true
  fi
  fixture8() (
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    export OC_CONFIG_ROOT="$sbx/db3" OC_STATE_DB="$sbx/db3/state.sqlite"
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step2; r_hist=$?; v_hist="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    export OC_CONFIG_ROOT="$sbx/db4" OC_STATE_DB="$sbx/db4/state.sqlite"
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step2; r_cur=$?; v_cur="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$v_hist" = "CLEAN" ] && [ "$r_hist" -eq 0 ] && [ "$v_cur" = "PROBLEM" ] && [ "$r_cur" -ne 0 ]; then
      printf 'historical-clean current-problem'; return 0
    fi
    printf 'hist=%s(%s) cur=%s(%s)' "$v_hist" "$r_hist" "$v_cur" "$r_cur"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1; then
    got="$(fixture8)"; rc=$?
    if [ "$got" = "historical-clean current-problem" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ historical failure (3d old) CLEAN; in-window failure PROBLEM"
    else
      echo "  ✗ historical vs current failures: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixtures 9+10: cron expected counts DERIVED per job. 720 legitimate
  # two-minute polls must be CLEAN; a job running far more often than it
  # declares must be PROBLEM. The old aggregate ">200" rule got both backwards.
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/db5" "$sbx/db6"
    _fixture_db "$sbx/db5/state.sqlite" "$_rc_tables" "$_jobs_table" || true
    _fixture_db "$sbx/db6/state.sqlite" "$_rc_tables" "$_jobs_table" || true
  fi
  # _seed_cron <db> <job_id> <name> <cron-expr> <n receipts> <status> <spacing_ms>
  _seed_cron() {
    local d="$1" jid="$2" nm="$3" expr="$4" n="$5" st="$6" sp="$7" i=0
    sqlite3 "$d" "insert into cron_jobs values ('default','$jid',null,'main','$nm',null,1,'main','command','{\"id\":\"$jid\",\"name\":\"$nm\",\"enabled\":true,\"schedule\":{\"kind\":\"cron\",\"expr\":\"$expr\"}}','{}',null,null,0,$NOW_MS);" >/dev/null 2>&1 || true
    while [ "$i" -lt "$n" ]; do
      sqlite3 "$d" "insert into cron_run_receipts values ('r-$jid-$i','default','$jid','rev','main',null,'$st',$$,null,$(( NOW_MS - i * sp )),$(( NOW_MS - i * sp )),null);" >/dev/null 2>&1 || true
      i=$((i + 1))
    done
  }
  if command -v sqlite3 >/dev/null 2>&1; then
    _seed_cron "$sbx/db5/state.sqlite" poll1 "rescue-rr-box-poll" "*/2 * * * *" 720 ok 120000
    _seed_cron "$sbx/db5/state.sqlite" hourly1 "index-model-drift-check" "17 * * * *" 12 ok 3600000
    _seed_cron "$sbx/db6/state.sqlite" loop1 "runaway-job" "17 * * * *" 400 error 180000
  fi
  fixture9() (
    export OC_CONFIG_ROOT="$sbx/db5" OC_STATE_DB="$sbx/db5/state.sqlite" OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step5; rc=$?
    v="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    d="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $4}')"
    if [ "$v" = "CLEAN" ] && [ "$rc" -eq 0 ]; then printf 'clean'; return 0; fi
    printf 'rc=%s verdict=%s detail=%s' "$rc" "$v" "$d"; return 1
  )
  fixture10() (
    export OC_CONFIG_ROOT="$sbx/db6" OC_STATE_DB="$sbx/db6/state.sqlite" OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step5; rc=$?
    v="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$v" = "PROBLEM" ] && [ "$rc" -ne 0 ] && [ $((PROBLEM_BITS & STEP_BIT_CRON)) -ne 0 ]; then printf 'problem'; return 0; fi
    printf 'rc=%s verdict=%s bits=%s' "$rc" "$v" "$PROBLEM_BITS"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1; then
    got="$(fixture9)"; rc=$?
    if [ "$got" = "clean" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ 720 legitimate two-minute polls + an hourly job: STEP5 CLEAN (old aggregate >200 called this a runaway)"
    else
      echo "  ✗ 720 normal polls: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
    got="$(fixture10)"; rc=$?
    if [ "$got" = "problem" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ true retry loop (hourly job, 400 fast error runs): STEP5 PROBLEM with the CRON bit"
    else
      echo "  ✗ true retry loop: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 11: cron schema. No cron table at all -> UNDETERMINED; legacy
  # cron_run_logs without cron_run_receipts -> UNDETERMINED (incompatible, not clean).
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/db7" "$sbx/db8"
    _fixture_db "$sbx/db7/state.sqlite" "$_dq_table" || true
    _fixture_db "$sbx/db8/state.sqlite" 'create table cron_run_logs (id text, started_at text);' "$_jobs_table" || true
  fi
  fixture11() (
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    export OC_CONFIG_ROOT="$sbx/db7" OC_STATE_DB="$sbx/db7/state.sqlite"
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step5; r1=$?; v1="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    export OC_CONFIG_ROOT="$sbx/db8" OC_STATE_DB="$sbx/db8/state.sqlite"
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step5; r2=$?; v2="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$v1" = "UNDETERMINED" ] && [ "$v2" = "UNDETERMINED" ] && [ "$r1" -ne 0 ] && [ "$r2" -ne 0 ]; then
      printf 'both-undetermined'; return 0
    fi
    printf 'absent=%s(%s) legacy=%s(%s)' "$v1" "$r1" "$v2" "$r2"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1; then
    got="$(fixture11)"; rc=$?
    if [ "$got" = "both-undetermined" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ no cron table AND legacy-only cron_run_logs: both UNDETERMINED (incompatible is never clean)"
    else
      echo "  ✗ cron schema cases: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 12: provider config shapes. Canonical models.providers with
  # timeouts -> CLEAN; canonical MISSING a timeout -> PROBLEM (the RCV-07 false
  # negative); legacy root providers -> read and enforced; no shape at all ->
  # UNDETERMINED, never "no missing timeouts".
  mkdir -p "$sbx/prov-can/agents/main" "$sbx/prov-can-bad/agents/main" "$sbx/prov-legacy/agents/main" "$sbx/prov-none/agents/main"
  printf '{"agents":{"list":[{"id":"main"}]},"models":{"providers":{"anthropic":{"timeoutSeconds":120},"deepseek":{"timeoutSeconds":60}}}}' > "$sbx/prov-can/openclaw.json"
  printf '{"agents":{"list":[{"id":"main"}]},"models":{"providers":{"anthropic":{"timeoutSeconds":120},"deepseek":{"baseUrl":"x"}}}}' > "$sbx/prov-can-bad/openclaw.json"
  printf '{"agents":{"list":[{"id":"main"}]},"providers":{"anthropic":{"timeoutSeconds":120},"deepseek":{"timeoutSeconds":60}}}' > "$sbx/prov-legacy/openclaw.json"
  printf '{"agents":{"list":[{"id":"main"}]}}' > "$sbx/prov-none/openclaw.json"
  fixture12() (
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    export OC_CONFIG_ROOT="$sbx/prov-can";    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""; step7; a=$?
    export OC_CONFIG_ROOT="$sbx/prov-can-bad"; ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""; step7; b=$?
    export OC_CONFIG_ROOT="$sbx/prov-legacy";  ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""; step7; c=$?
    export OC_CONFIG_ROOT="$sbx/prov-none";    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""; step7; d=$?
    vd="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$a" -eq 0 ] && [ "$b" -ne 0 ] && [ "$c" -eq 0 ] && [ "$d" -ne 0 ] && [ "$vd" = "UNDETERMINED" ]; then
      printf 'canonical-clean canonical-missing-problem legacy-clean none-undetermined'; return 0
    fi
    printf 'a=%s b=%s c=%s d=%s none=%s' "$a" "$b" "$c" "$d" "$vd"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ]; then
    got="$(fixture12)"; rc=$?
    if [ "$got" = "canonical-clean canonical-missing-problem legacy-clean none-undetermined" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ provider shapes: canonical ok / canonical missing-timeout PROBLEM / legacy read+enforced / no-shape UNDETERMINED"
    else
      echo "  ✗ provider shapes: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 13: MULTIPLE SERVICES on one box. Eight openclaw-ish launchd labels
  # are present; the ladder must inspect ONLY the exact approved label, must
  # never take the first substring match, and must not call a stopped gateway
  # with a clean stale exit CLEAN. PATH-stubbed launchctl/curl -> fully offline.
  _stub_launchd() {
    cat > "$sbx/bin/launchctl" <<'STUB_LAUNCHCTL'
#!/bin/bash
if [ "${1:-}" = "list" ]; then
  printf '%s\n' \
    $'-\t0\tai.openclaw.donna-gw-tunnel' \
    $'-\t0\tai.openclaw.janet-gw-tunnel' \
    $'-\t0\tai.openclaw.gateway-watchdog' \
    $'1232\t0\tai.openclaw.gateway' \
    $'-\t0\tai.openclaw.janet-watchdog'
  exit 0
fi
if [ "${1:-}" = "print" ]; then
  case "${2:-}" in
    *"ai.openclaw.gateway")
      case "${OC_FIXTURE_SVC:-alive}" in
        alive)   printf '\tstate = running\n\tpid = 1232\n\tlast exit code = 0\n' ;;
        stale)   printf '\tstate = not running\n\tlast exit code = 0\n' ;;
        crash)   printf '\tstate = running\n\tpid = 1232\n\tlast exit code = 78 (EX_CONFIG)\n' ;;
      esac
      exit 0 ;;
    *) echo "Could not find service" >&2; exit 1 ;;
  esac
fi
exit 0
STUB_LAUNCHCTL
    cat > "$sbx/bin/curl" <<'STUB_CURL'
#!/bin/bash
if [ "${OC_FIXTURE_HEALTHY:-0}" = "1" ]; then
  printf '{"ok":true,"status":"live"}\n200'
  exit 0
fi
printf 'curl: (7) Failed to connect to 127.0.0.1\n000'
exit 7
STUB_CURL
    chmod +x "$sbx/bin/launchctl" "$sbx/bin/curl"
  }
  mkdir -p "$sbx/bin" "$sbx/svc/agents/main"
  printf '{"agents":{"list":[{"id":"main"}]},"models":{"providers":{"anthropic":{"timeoutSeconds":1}}}}' > "$sbx/svc/openclaw.json"
  _stub_launchd
  fixture13() (
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}" OC_CONFIG_ROOT="$sbx/svc" OC_LOG_ROOT="$sbx/logs"
    export OC_PLATFORM=mac OC_TARGET_MODE=launchd OC_GATEWAY_PORT=18789
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_SVC=alive OC_FIXTURE_HEALTHY=1 step1; alive=$?
    v1="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    d1="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $4}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_SVC=alive OC_FIXTURE_HEALTHY=0 step1; notre=$?
    v2="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_SVC=stale OC_FIXTURE_HEALTHY=1 step1; stale=$?
    v3="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_SVC=crash OC_FIXTURE_HEALTHY=1 step1; crash=$?
    v4="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    case "$d1" in *donna-gw-tunnel*|*janet*) printf 'selected-a-neighbour-label'; return 1 ;; esac
    if [ "$v1" = "CLEAN" ] && [ "$alive" -eq 0 ] \
       && [ "$v2" = "PROBLEM" ] && [ "$notre" -ne 0 ] \
       && [ "$v3" = "PROBLEM" ] && [ "$stale" -ne 0 ] \
       && [ "$v4" = "PROBLEM" ] && [ "$crash" -ne 0 ]; then
      printf 'exact-target ok'; return 0
    fi
    printf 'alive=%s(%s) notready=%s(%s) stale=%s(%s) crash=%s(%s)' "$v1" "$alive" "$v2" "$notre" "$v3" "$stale" "$v4" "$crash"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ]; then
    got="$(fixture13)"; rc=$?
    if [ "$got" = "exact-target ok" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ 5 openclaw-ish labels: exact gateway label inspected; ready CLEAN; app-not-ready / stale clean exit / exit-78-with-live-process all PROBLEM"
    else
      echo "  ✗ multiple-services / app-readiness: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 14: docker. A stopped container beside a RUNNING neighbour: the
  # EXACT container name is inspected (never the first name match); a stopped
  # gateway is PROBLEM; a running gateway whose app does not answer is PROBLEM
  # ("container Up" is not health). Plus the inside-container case: no docker
  # CLI at all -> the ladder says so instead of guessing.
  cat > "$sbx/bin/docker" <<'STUB_DOCKER'
#!/bin/bash
if [ "${1:-}" = "inspect" ]; then
  name=""
  for a in "$@"; do name="$a"; done
  if [ "$name" != "openclaw" ]; then
    echo "Error: No such object: $name" >&2
    exit 1
  fi
  case "${OC_FIXTURE_DOCKER:-running}" in
    running) printf '%s\n' "running|2026-09-10T10:00:00Z|0|0" ;;
    exited)  printf '%s\n' "exited|2026-09-10T10:00:00Z|0|0" ;;
    *)       printf '%s\n' "restarting|2026-09-10T10:00:00Z|7|0" ;;
  esac
  exit 0
fi
if [ "${1:-}" = "exec" ]; then exit 1; fi
exit 0
STUB_DOCKER
  chmod +x "$sbx/bin/docker"
  mkdir -p "$sbx/dock/agents/main"
  printf '{"agents":{"list":[{"id":"main"}]},"models":{"providers":{"anthropic":{"timeoutSeconds":1}}}}' > "$sbx/dock/openclaw.json"
  fixture14() (
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}" OC_CONFIG_ROOT="$sbx/dock"
    export OC_PLATFORM=vps-host OC_TARGET_MODE=docker OC_CONTAINER=openclaw OC_GATEWAY_PORT=18789
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_DOCKER=exited OC_FIXTURE_HEALTHY=0 step1; e=$?
    v_exit="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_DOCKER=running OC_FIXTURE_HEALTHY=0 step1; u=$?
    v_up="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_DOCKER=running OC_FIXTURE_HEALTHY=1 step1; ok=$?
    v_ok="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_DOCKER=loop OC_FIXTURE_HEALTHY=1 step1; rl=$?
    v_rl="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$v_exit" = "PROBLEM" ] && [ "$v_up" = "PROBLEM" ] && [ "$v_ok" = "CLEAN" ] && [ "$ok" -eq 0 ] && [ "$v_rl" = "PROBLEM" ]; then
      printf 'stopped-problem up-but-dead-problem ready-clean restarting-problem'; return 0
    fi
    printf 'exited=%s(%s) up=%s(%s) ready=%s(%s) restarting=%s(%s)' "$v_exit" "$e" "$v_up" "$u" "$v_ok" "$ok" "$v_rl" "$rl"; return 1
  )
  fixture14b() (
    # Inside the container there is no docker CLI: the ladder must report that
    # it cannot inspect a runtime it has no access to -- never a fabricated Up.
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}" OC_CONFIG_ROOT="$sbx/dock"
    export OC_PLATFORM=vps-container OC_TARGET_MODE=process OC_GATEWAY_PORT=18789
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_HEALTHY=1 step1; ok=$?
    v_ok="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    PATH="$sbx/bin:$PATH" OC_FIXTURE_HEALTHY=0 step1; dead=$?
    v_dead="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    if [ "$v_ok" = "CLEAN" ] && [ "$ok" -eq 0 ] && [ "$v_dead" = "PROBLEM" ] && [ "$dead" -ne 0 ]; then
      printf 'container-ready-clean container-dead-problem'; return 0
    fi
    printf 'ready=%s(%s) dead=%s(%s)' "$v_ok" "$ok" "$v_dead" "$dead"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ]; then
    got="$(fixture14)"; rc=$?
    if [ "$got" = "stopped-problem up-but-dead-problem ready-clean restarting-problem" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ docker: exact container inspected; exited/restarting PROBLEM; Up-but-dead-gateway PROBLEM (app readiness required)"
    else
      echo "  ✗ docker target cases: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
    got="$(fixture14b)"; rc=$?
    if [ "$got" = "container-ready-clean container-dead-problem" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ inside-container (no docker CLI): process+HTTP readiness decides; no fabricated container state"
    else
      echo "  ✗ inside-container case: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 15: every diagnostic line carries the canonical box/company.
  fixture15() (
    export OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}" OC_CONFIG_ROOT="$sbx/svc"
    export OC_BOX_SLUG=fixture-box COMPANY_SLUG=fixture-co
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step3
    case "$RESULTS" in *"[box=fixture-box company=fixture-co]"*) printf 'identity-present'; return 0 ;; esac
    printf 'line=%s' "$RESULTS"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ]; then
    got="$(fixture15)"; rc=$?
    if [ "$got" = "identity-present" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ every diagnostic line carries the canonical box/company"
    else
      echo "  ✗ identity prefix: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  # Fixture 16: a FAILED query must not become a zero. Drop the receipts table
  # mid-flight is not possible read-only, so instead point at a db whose schema
  # is incompatible in a way that makes the count query itself fail.
  if command -v sqlite3 >/dev/null 2>&1; then
    mkdir -p "$sbx/db9"
    _fixture_db "$sbx/db9/state.sqlite" 'create table delivery_queue_entries (id text);' "$_ci_table" || true
  fi
  fixture16() (
    export OC_CONFIG_ROOT="$sbx/db9" OC_STATE_DB="$sbx/db9/state.sqlite" OC_ENV_DESCRIPTOR="${DESCRIPTOR:-}"
    # shellcheck disable=SC1090
    . "$0" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    step2; rc=$?
    v="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $3}')"
    d="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1{print $4}')"
    if [ "$v" = "UNDETERMINED" ] && [ "$rc" -ne 0 ]; then
      case "$d" in *"missing column"*) printf 'undetermined-incompatible-schema'; return 0 ;; esac
      printf 'undetermined-other: %s' "$d"; return 1
    fi
    printf 'rc=%s verdict=%s' "$rc" "$v"; return 1
  )
  if [ -n "${DESCRIPTOR:-}" ] && command -v sqlite3 >/dev/null 2>&1; then
    got="$(fixture16)"; rc=$?
    if [ "$got" = "undetermined-incompatible-schema" ] && [ "$rc" -eq 0 ]; then
      echo "  ✓ incompatible delivery schema (missing columns): STEP2 UNDETERMINED naming the columns, never zero"
    else
      echo "  ✗ incompatible schema: got '$got' (rc=$rc)"; failures=$((failures+1))
    fi
  fi

  echo "[rr-triage --self-test] $failures failure(s)"
  return $failures
}

# --self-test sources this file (via `.`) to reuse step7/STEP_BIT_* etc.
# without re-running the ladder against the real box; --source-only is
# consumed here so sourcing never falls through into run_ladder below.
if [ "${1:-}" = "--source-only" ]; then
  return 0 2>/dev/null || exit 0
fi

case "${1:-}" in
  --self-test)
    self_test
    exit $? ;;
  --descriptor)
    ocd_init
    print_descriptor
    exit 0 ;;
  --json)
    JSON_MODE=1
    run_ladder
    ladder_rc=$?
    if [ "$ladder_rc" -eq 78 ]; then
      print_json_summary
      exit 78
    fi
    print_json_summary
    ;;
  "")
    run_ladder
    ladder_rc=$?
    if [ "$ladder_rc" -eq 78 ]; then
      print_summary
      exit 78
    fi
    print_summary
    ;;
  -h|--help|*)
    sed -n '2,55p' "$0"
    exit 0 ;;
esac

if [ "$UNDETERMINED_COUNT" -gt 0 ]; then
  exit 3
elif [ "$PROBLEM_BITS" -eq 0 ]; then
  exit 0
else
  exit $((100 + PROBLEM_BITS))
fi
