#!/usr/bin/env bash
# reconcile-rr-agent-map.sh — RR-031 (RR-W4-REGISTRY, lane RR-W4-INSTALL).
#
# Reconciles rr_agent_map (n8n data table, box_slug -> local_agent_id) against
# the VERIFIED runtime agents actually present inside each client's exact
# container. Supersedes the insert-only seeding in seed-rr-agent-map.sh, which
# read ONE page, filled only ABSENT slugs, never repaired a row that mapped a
# slug to the WRONG agent, used shared fixed /tmp paths, made unbounded SSH and
# HTTP calls, discovered agents on the HOST ONLY (so a Docker-installed box
# could never resolve its own container), and hardcoded operator host + table
# identity while its wrapper read a "skipped" exit 0 as "ok".
#
#   reconcile-rr-agent-map.sh [MODE] [options]
#
#   --check      (default, read-only, needs no API key) — prove the configured
#                identity and the registry inputs; print structured key=value
#                lines including the exact table id and whether it was frozen
#                by the rescue contract manifest or fell back to the documented
#                default. No network, no secret, no write. Exit 1 when any
#                roster slug has no usable execution context.
#   (default)    PLAN ONLY — resolve every box's runtime, diff against the
#                table, print the plan and the counts. Nothing written.
#   --apply      perform the writes the plan calls for.
#   --verify     write as needed, then read the table back and prove every
#                reconciled row matches the runtime. Refuses to claim
#                verification when the read-back is incomplete.
#   --dry-run    explicit plan-only (writes disabled even beside --apply).
#
#   --roster FILE            fleet roster (default fleet-prover/fleet-roster.json)
#   --boxes FILE             box registry (default fleet-prover/box-registry.json)
#   --table ID               override the table id (identity_source=flag)
#   --contract-manifest FILE rescue contract manifest that freezes the identity
#   --host URL               n8n base URL (default $N8N_HOST)
#   --lock-dir DIR           where the scoped lock dir lives
#   --state-dir DIR          state root (lock dir default here)
#   --stale-lock-seconds N   steal a pid-less lock older than N (default 600)
#   --max-pages N            hard page cap for the source snapshot (default 200)
#   --ssh-timeout N          ssh ConnectTimeout seconds (default 25)
#   --proc-timeout N         process deadline per box probe, seconds (default 45)
#   --no-deadline            disable the whole-run deadline (tests only)
#
# THE RR-031 CONTRACT, clause by clause
# ---------------------------------------------------------------------------
# 1. CONFIGURE TABLE/REGISTRY IDENTITY. Nothing is hardcoded and nothing is
#    silently trusted. The table id is CONFIGURED from the FLEET rescue
#    contract manifest (entry "rr_agent_map"): a FROZEN identity that must
#    equal the pinned TABLE_ID_DEFAULT or the run ABORTS — a manifest that
#    describes a different table is a contract violation, not an override.
#    With no manifest the id is the documented default and the run reports
#    identity_source=default (degraded, visible). --table sets
#    identity_source=flag. Roster identity comes from the fleet-prover roster,
#    box identity from the fleet-prover box registry, and each box's RUNTIME
#    identity from that box's own openclaw install inside its own container.
#
# 2. FETCH ALL PAGES WITH CHECKED STATUS/SCHEMA; ABORT WRITES ON INCOMPLETE
#    SOURCE. Every GET is bounded (--connect-timeout/--max-time) and its HTTP
#    status is CHECKED: a non-2xx (401, 500, an HTML error page) ABORTS the run
#    with zero writes. Pagination loops on nextCursor under a hard --max-pages
#    cap; hitting the cap, a bad status, a truncated body, or a body that is
#    not a JSON object with a `data` array all leave the snapshot INCOMPLETE
#    and abort before any write. Duplicate rows for one box_slug are detected
#    and can never be "reconciled" away (the API exposes no row delete), so
#    they abort the write path and surface as duplicates=N with slugs named.
#
# 3. RECONCILE EXISTING AND MISSING AGAINST VERIFIED RUNTIME AGENTS WITHIN THE
#    EXACT CONTAINER. Each box's agent list is read INSIDE that box's own
#    execution context, using the REUSED fleet-prover box descriptor
#    (kind local|mac|vps|contabo, ssh_alias, ssh_user, ssh_target, container)
#    and the same wrapper proof shape prove-zhe.py / prove-floor.py use:
#      local        -> the command runs here
#      mac          -> ssh <ssh_alias> zsh -lc <cmd>   (optional ssh_user@)
#      vps|contabo  -> ssh <ssh_target> docker exec -i -u node <container> sh -c <cmd>
#    The old host-side `ssh <box> openclaw agents list` is exactly the gap
#    RCV-09 names: on a Docker install the operator host has no openclaw, so
#    the box could never resolve and got silently skipped. `main` is NEVER
#    invented: the row carries the box's REAL default agent id.
#
# 4. ENFORCE UNIQUE TENANT+BOX MAPPING. The n8n data-table API exposes no row
#    upsert and no row delete, so the SUPPORTED atomic operation is the
#    filter-addressed PATCH /rows/update — a compare-and-set on box_slug. The
#    conflict policy is:
#      ACCEPT    existing row == verified runtime        -> verified, no write
#      REPAIR    existing row != verified runtime        -> PATCH box_slug
#      INSERT    no row for the slug                     -> POST {data:[row]}
#      CONFLICT  more than one row for one slug          -> ABORT (no guess)
#    A rerun after a REPAIR reports verified=N and re-PATCHes 0 rows; a row
#    whose PATCH or POST was interrupted is retried, which is a state-proving
#    write, not a no-op. No row is ever written when the source snapshot or the
#    box's runtime identity is unproved.
#
# 5. PER-RUN PRIVATE TEMP PATHS, SCOPED LOCK, FINITE HTTP/SSH/PROCESS
#    DEADLINES, SECURE CREDENTIAL TRANSPORT. Every artifact (snapshot pages,
#    plan, payloads, header file) lives under ONE 0700 per-run directory
#    created with mktemp -d and removed by the exit trap — no shared fixed
#    /tmp name is ever reused, so two concurrent runs cannot overwrite each
#    other. A scoped mkdir lock guards WRITE runs only (plan/check are
#    read-only and never lock): the loser exits 3 having written nothing, and
#    a stale lock (holder pid dead, or pid-less and older than
#    --stale-lock-seconds) is stolen exactly once, still with a single winner.
#    Every HTTP call carries --max-time/--connect-timeout; every SSH probe
#    carries ConnectTimeout + BatchMode and runs under a process deadline
#    (timeout/gtimeout, or an internal check when absent); the whole run is
#    additionally bounded by a watchdog. The n8n API key and any credential
#    ride in 0600 header files inside the 0700 private dir (curl -H @file) and
#    are never placed in argv, a child env, or a log.
#
# 6. PERSIST UNRESOLVED/INACCESSIBLE MAPPINGS AS PENDING WITH OWNER. A box
#    whose runtime cannot be read (unreachable, timed out, no openclaw), or
#    which exposes no usable default agent, gets NO row. It is recorded as
#    {"box_slug","status":"pending","owner","reason"} in the pending ledger
#    and printed as `pending <slug> owner=<owner> reason=<reason>`. The run
#    reports complete=0 and exits non-zero: a roster with pending entries is
#    never reported as complete.
#
# 7. REUSE HOST DESCRIPTOR; REPORT ACTUAL CHANGED/VERIFIED/PENDING COUNTS.
#    The last line is machine-readable and carries the ACTUAL counts:
#      changed verified pending failed aborted duplicates rows_inserted
#      rows_updated pages complete identity_source
#
# Exit codes: 0 reconciled / verified complete
#             1 run failed or incomplete (aborted snapshot, pending, dup, rc)
#             2 usage or configuration error
#             3 another write run holds the scoped lock (nothing written)
#
# Requirements: bash 3.2+, python3, curl. ssh (and docker on the far side) only
# for boxes the registry declares remote/containerized. Roster slugs only.

set -euo pipefail

SCRIPT_TAG="reconcile-rr-agent-map"

# --- identity, configured below; never silently trusted ----------------------
TABLE_ID_DEFAULT="EFPgipZtKatC5xPw"       # rr_agent_map, per rescue contract
TABLE_ID="$TABLE_ID_DEFAULT"
IDENTITY_SOURCE="default"
CONTRACT_MANIFEST_DEFAULT="$HOME/blackceo-fleet-ops/rescue/contract-manifest.json"
ROSTER_DEFAULT="$HOME/clawd/fleet-prover/fleet-roster.json"
BOX_REGISTRY_DEFAULT="$HOME/clawd/fleet-prover/box-registry.json"
HOST="${N8N_HOST:-https://main.blackceoautomations.com}"
PENDING_OWNER="operator"
PENDING_LEDGER_FLAG=""

MODE="check"
ROSTER_FILE=""; BOXES_FILE=""; LOCK_DIR=""; STATE_DIR=""
STALE_LOCK_SECONDS=600
MAX_PAGES=200
SSH_TIMEOUT="${RR_REGISTRY_SSH_TIMEOUT:-25}"
PROC_TIMEOUT="${RR_REGISTRY_PROC_TIMEOUT:-45}"
RUN_DEADLINE="${RR_REGISTRY_DEADLINE:-900}"
DEADLINE_DISABLED=0

die() { printf '%s: %s\n' "$SCRIPT_TAG" "$*" >&2; exit 2; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check)   MODE="check" ;;
    --apply)   MODE="apply" ;;
    --verify)  MODE="verify" ;;
    --dry-run) MODE="dry" ;;
    --roster)   shift; ROSTER_FILE="${1:-}" ;;
    --boxes)    shift; BOXES_FILE="${1:-}" ;;
    --table)    shift; TABLE_ID="${1:-}"; IDENTITY_SOURCE="flag" ;;
    --contract-manifest) shift; CONTRACT_MANIFEST_DEFAULT="${1:-}" ;;
    --host)     shift; HOST="${1:-}" ;;
    --lock-dir) shift; LOCK_DIR="${1:-}" ;;
    --state-dir) shift; STATE_DIR="${1:-}" ;;
    --stale-lock-seconds) shift; STALE_LOCK_SECONDS="${1:-600}" ;;
    --max-pages) shift; MAX_PAGES="${1:-200}" ;;
    --ssh-timeout) shift; SSH_TIMEOUT="${1:-25}" ;;
    --proc-timeout) shift; PROC_TIMEOUT="${1:-45}" ;;
    --pending-owner) shift; PENDING_OWNER="${1:-operator}" ;;
    --pending-ledger) shift; PENDING_LEDGER_FLAG="${1:-}" ;;
    --no-deadline) DEADLINE_DISABLED=1 ;;
    --selftest) : ;;
    --) shift; break ;;
    -*) die "unknown option: $1" ;;
    *)  die "unexpected argument: $1" ;;
  esac
  shift
done

for _n in "$STALE_LOCK_SECONDS" "$MAX_PAGES" "$SSH_TIMEOUT" "$PROC_TIMEOUT" "$RUN_DEADLINE"; do
  case "$_n" in ''|*[!0-9]*) die "numeric option expected a non-negative integer, got '$_n'" ;; esac
done

export PYTHONDONTWRITEBYTECODE=1
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$ROOT/scripts/_rr_registry_lib.py"
RESCUE_ENV="$ROOT/shared-utils/rescue-env.sh"
[ -f "$LIB" ] || die "reconcile-rr-agent-map: _rr_registry_lib.py not found beside this script ($LIB)"
[ -f "$RESCUE_ENV" ] || die "reconcile-rr-agent-map: shared-utils/rescue-env.sh not found ($RESCUE_ENV)"
py() { python3 "$LIB" "$@"; }

# --- per-run private temp tree (no shared fixed path, ever) ------------------
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/rr-registry.XXXXXX")" || die "cannot create private temp dir"
chmod 700 "$RUN_DIR"
_HDR_DIR="$RUN_DIR/hdr"; mkdir -p "$_HDR_DIR"; chmod 700 "$_HDR_DIR"
WATCHDOG_PID=""

# --- scoped lock -------------------------------------------------------------
if [ -n "$LOCK_DIR" ]; then LOCK_ROOT="$LOCK_DIR"
elif [ -n "$STATE_DIR" ]; then LOCK_ROOT="$STATE_DIR/locks"
else LOCK_ROOT="${RR_REGISTRY_STATE:-$HOME/.openclaw/state/rr-registry}"; fi
LOCK_PATH="$LOCK_ROOT/agent-map-reconcile.lock"
LOCK_HELD=0; LOCK_STOLEN=0; OWN_PID=$$

lock_holder_pid() { sed -n '1p' "$LOCK_PATH/pid" 2>/dev/null || true; }
dir_age_seconds() {
  local m; m="$(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || date +%s)"
  printf '%s' "$(( $(date +%s) - m ))"
}
acquire_lock() {
  mkdir -p "$LOCK_ROOT" 2>/dev/null || true
  chmod 700 "$LOCK_ROOT" 2>/dev/null || true
  if mkdir "$LOCK_PATH" 2>/dev/null; then LOCK_HELD=1; else
    local hp stale=0; hp="$(lock_holder_pid)"
    if [ -n "$hp" ]; then
      kill -0 "$hp" 2>/dev/null || stale=1
    elif [ -d "$LOCK_PATH" ] && [ "$(dir_age_seconds "$LOCK_PATH")" -gt "$STALE_LOCK_SECONDS" ]; then
      stale=1
    fi
    if [ "$stale" -eq 1 ]; then
      rm -rf "$LOCK_PATH" 2>/dev/null || true
      mkdir "$LOCK_PATH" 2>/dev/null && { LOCK_HELD=1; LOCK_STOLEN=1; }
    fi
    if [ "$LOCK_HELD" -ne 1 ]; then
      printf '%s: another reconcile run holds the scoped lock (%s, holder pid %s) — nothing written\n' \
        "$SCRIPT_TAG" "$LOCK_PATH" "${hp:-unknown}" >&2
      exit 3
    fi
  fi
  printf '%s\n' "$OWN_PID" > "$LOCK_PATH/pid"
}
release_lock() {
  [ "$LOCK_HELD" -eq 1 ] || return 0
  [ "$(lock_holder_pid)" = "$OWN_PID" ] || return 0
  rm -rf "$LOCK_PATH" 2>/dev/null || true
}
cleanup() {
  [ -n "$WATCHDOG_PID" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
  release_lock
  rm -rf "$RUN_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM HUP

DEADLINE_AT=0
[ "$DEADLINE_DISABLED" -eq 0 ] && DEADLINE_AT=$(( $(date +%s) + RUN_DEADLINE ))
deadline_left() {
  [ "$DEADLINE_AT" -eq 0 ] && { printf '%s' "$RUN_DEADLINE"; return 0; }
  local left=$(( DEADLINE_AT - $(date +%s) ))
  [ "$left" -gt 0 ] || left=0
  printf '%s' "$left"
}
start_watchdog() {
  [ "$DEADLINE_AT" -eq 0 ] && return 0
  ( sleep "$RUN_DEADLINE"
    if kill -0 "$OWN_PID" 2>/dev/null; then
      printf '%s: RUN DEADLINE exceeded (%ss) — terminating pid %s\n' "$SCRIPT_TAG" "$RUN_DEADLINE" "$OWN_PID" >&2
      kill -TERM "$OWN_PID" 2>/dev/null || true
    fi ) >/dev/null 2>&1 &
  WATCHDOG_PID=$!
}

# =============================================================================
# 1. CONFIGURE IDENTITY
# =============================================================================
configure_identity() {
  [ "$IDENTITY_SOURCE" = "flag" ] && return 0
  local mt=""
  if [ -f "$CONTRACT_MANIFEST_DEFAULT" ]; then
    mt="$(py table-id "$CONTRACT_MANIFEST_DEFAULT" 2>/dev/null || true)"
  fi
  if [ -n "$mt" ]; then
    [ "$mt" = "$TABLE_ID_DEFAULT" ] || die "table identity mismatch: the rescue contract manifest names table $mt but this script pins $TABLE_ID_DEFAULT — refusing to run against a table the contract does not describe"
    TABLE_ID="$mt"; IDENTITY_SOURCE="contract-manifest"
  fi
}
configure_identity

if [ -z "$ROSTER_FILE" ]; then ROSTER_FILE="$ROSTER_DEFAULT"; fi
if [ -z "$BOXES_FILE" ]; then BOXES_FILE="$BOX_REGISTRY_DEFAULT"; fi
# The pending ledger is DURABLE and outside the per-run dir: an unresolved box
# must still be actionable after the run that found it has exited. It records
# box_slug + status + owner + reason only, and it is replaced (not appended) so
# it always describes the CURRENT run's unresolved set.
if [ -n "$PENDING_LEDGER_FLAG" ]; then PENDING_LEDGER_PATH="$PENDING_LEDGER_FLAG"
elif [ -n "$STATE_DIR" ]; then PENDING_LEDGER_PATH="$STATE_DIR/rr-agent-map-pending.json"
else PENDING_LEDGER_PATH="${RR_REGISTRY_STATE:-$HOME/.openclaw/state/rr-registry}/rr-agent-map-pending.json"; fi

# =============================================================================
# 2. CHECK MODE — prove identity + registry inputs; write nothing, read nothing
# =============================================================================
if [ "$MODE" = "check" ]; then
  printf 'table_id=%s\n' "$TABLE_ID"
  printf 'identity_source=%s\n' "$IDENTITY_SOURCE"
  printf 'contract_manifest=%s\n' "$([ -f "$CONTRACT_MANIFEST_DEFAULT" ] && printf present || printf absent)"
  printf 'roster=%s\n' "$ROSTER_FILE"
  printf 'box_registry=%s\n' "$BOXES_FILE"
  printf 'host=%s\n' "$(py hostname "$HOST")"
  printf 'max_pages=%s\n' "$MAX_PAGES"
  printf 'ssh_timeout=%s\n' "$SSH_TIMEOUT"
  printf 'proc_timeout=%s\n' "$PROC_TIMEOUT"
  printf 'run_deadline=%s\n' "$RUN_DEADLINE"
  printf 'stale_lock_seconds=%s\n' "$STALE_LOCK_SECONDS"
  printf 'lock_path=%s\n' "$LOCK_PATH"
  printf 'pending_ledger=%s\n' "$PENDING_LEDGER_PATH"
  failed=0
  if [ ! -f "$ROSTER_FILE" ]; then printf 'roster_state=absent\n'; failed=1
  else printf 'roster_state=present\n'; fi
  if [ ! -f "$BOXES_FILE" ]; then printf 'box_registry_state=absent\n'; failed=1
  else printf 'box_registry_state=present\n'; fi
  if [ -f "$ROSTER_FILE" ] && [ -f "$BOXES_FILE" ]; then
    py check "$ROSTER_FILE" "$BOXES_FILE" || failed=1
  fi
  printf 'config_fail=%s\n' "$failed"
  exit "$failed"
fi

# =============================================================================
# 3. PLAN / APPLY / VERIFY
# =============================================================================
[ -f "$ROSTER_FILE" ] || die "fleet roster not found: $ROSTER_FILE (source identity unproved — refusing to run)"
[ -f "$BOXES_FILE" ]  || die "box registry not found: $BOXES_FILE (box identity unproved — refusing to run)"

WRITE=0
{ [ "$MODE" = "apply" ] || [ "$MODE" = "verify" ]; } && WRITE=1

if [ "$WRITE" -eq 1 ]; then
  if [ -z "${N8N_API_KEY:-}" ]; then
    echo "$SCRIPT_TAG: N8N_API_KEY not set — operator-only path, nothing written." >&2
    exit 0
  fi
  acquire_lock
fi
start_watchdog

_HDR_FILE=""
if [ -n "${N8N_API_KEY:-}" ]; then
  # shellcheck disable=SC1090
  . "$RESCUE_ENV"
  _HDR_FILE="$(rescue_env_header_file "$_HDR_DIR" "X-N8N-API-KEY" "$N8N_API_KEY")" || die "cannot write auth header file"
fi

N8N_ROWS_URL="${HOST%/}/api/v1/data-tables/$TABLE_ID/rows"
NSNAP="$RUN_DIR/snapshot.jsonl"
# Always present, even when there is no credential to read with: a run that
# never had a source must report pages=0, not fail on a missing file.
: > "$NSNAP"

# --- 3a. snapshot every page, checked status + checked schema ---------------
snapshot() {   # -> 0 complete; 1 incomplete with the reason on stdout
  local cursor="" page=0 code next f dl
  : > "$NSNAP"
  while :; do
    page=$((page + 1))
    [ "$page" -le "$MAX_PAGES" ] || { printf 'page-cap-exceeded max_pages=%s' "$MAX_PAGES"; return 1; }
    dl="$(deadline_left)"; [ "$dl" -gt 0 ] || { printf 'run-deadline-exhausted'; return 1; }
    f="$RUN_DIR/page-$page.json"
    local -a cargv=( -sS --max-time "$dl" --connect-timeout 10 -H "@$_HDR_FILE" -w '%{http_code}' -o "$f" )
    [ -n "$cursor" ] && cargv+=( -G --data-urlencode "cursor=$cursor" )
    code="$(curl "${cargv[@]}" "$N8N_ROWS_URL" 2>/dev/null || printf '000')"
    case "$code" in 2*) : ;; *) printf 'http-%s page=%s' "$code" "$page"; return 1 ;; esac
    next="$(py page "$f" "$NSNAP" 2>/dev/null)" || { printf 'schema-invalid page=%s' "$page"; return 1; }
    [ -n "$next" ] || return 0
    cursor="$next"
  done
}

# --- 3b. snapshot: EVERY page, checked status + checked schema --------------
# No snapshot -> the source is unproved -> nothing may be written. A read-only
# plan with no credential still runs (it can only ever report, never write).
if [ -n "$_HDR_FILE" ]; then
  SNAP_REASON=""
  if ! SNAP_REASON="$(snapshot)"; then
    echo "$SCRIPT_TAG: table snapshot INCOMPLETE ($SNAP_REASON) — ABORTING with zero writes." >&2
    echo "$SCRIPT_TAG: the source of truth was not fully read, so no mapping may be changed."
    py emit-empty "aborted=1" 2>/dev/null || printf 'reconcile-rr-agent-map: aborted=1 changed=0 verified=0 pending=0 failed=0 duplicates=0 rows_inserted=0 rows_updated=0 pages=0 complete=0 identity_source=%s\n' "$IDENTITY_SOURCE"
    exit 1
  fi
fi
PAGES_READ="$(wc -l < "$NSNAP" 2>/dev/null | tr -d ' ')"
PAGES_READ="${PAGES_READ:-0}"

# --- 3c. plan: roster x table snapshot (no runtime yet) ---------------------
PLAN="$RUN_DIR/plan.json"
py plan "$ROSTER_FILE" "$BOXES_FILE" "$NSNAP" "$PLAN" "$TABLE_ID" "$PENDING_OWNER"

DUPCOUNT="$(py get "$PLAN" duplicates_count)"
if [ "$DUPCOUNT" -gt 0 ]; then
  echo "$SCRIPT_TAG: DUPLICATE rows for the same box_slug — the n8n data-table API exposes no row delete, so a unique mapping cannot be reconciled automatically. ABORTING with zero writes." >&2
  py dupes "$PLAN" >&2
  py emit "$PLAN" "aborted=1"
  exit 1
fi

probe_runtime() {   # probe_runtime <slug> -> one JSON object on stdout
  local slug="$1" budget rc=0 out="" line=""
  budget="$(deadline_left)"
  [ "$budget" -gt "$PROC_TIMEOUT" ] && budget="$PROC_TIMEOUT"
  if [ "$budget" -le 0 ]; then printf '{"status":"timeout","reason":"run-deadline-exhausted"}'; return 0; fi
  local -a argv=()
  while IFS= read -r line; do [ -n "$line" ] && argv+=("$line"); done < <(py argv "$BOXES_FILE" "$slug" "$SSH_TIMEOUT" 2>/dev/null || true)
  if [ "${#argv[@]}" -eq 0 ]; then printf '{"status":"unreachable","reason":"no-execution-context"}'; return 0; fi
  if command -v timeout >/dev/null 2>&1; then
    out="$(timeout "$budget" "${argv[@]}" 2>/dev/null)" || rc=$?
  elif command -v gtimeout >/dev/null 2>&1; then
    out="$(gtimeout "$budget" "${argv[@]}" 2>/dev/null)" || rc=$?
  else
    out="$("${argv[@]}" 2>/dev/null)" || rc=$?
  fi
  if [ "$rc" -eq 124 ]; then printf '{"status":"timeout","reason":"process-deadline-%ss"}' "$budget"; return 0; fi
  if [ "$rc" -ne 0 ]; then printf '{"status":"unreachable","reason":"probe-rc-%s"}' "$rc"; return 0; fi
  if [ -z "$out" ]; then printf '{"status":"unreachable","reason":"empty-probe-output"}'; return 0; fi
  printf '%s' "$out" | py parse
}
# --- 3d. resolve every box's runtime INSIDE its exact container -------------
RUNTIMES="$RUN_DIR/runtimes.jsonl"
: > "$RUNTIMES"
for slug in $(py get "$PLAN" slugs); do
  [ -n "$slug" ] || continue
  rt="$(probe_runtime "$slug")"
  printf '%s\t%s\n' "$slug" "$rt" >> "$RUNTIMES"
done



FINAL="$RUN_DIR/final.json"
py merge "$PLAN" "$RUNTIMES" "$FINAL"

CHANGED="$(py get "$FINAL" changed)"
VERIFIED="$(py get "$FINAL" verified)"
PENDING="$(py get "$FINAL" pending)"

py announce "$FINAL"

# --- 3e. writes ---------------------------------------------------------------
INS=0; UPD=0; FAILED=0; RC=0
if [ "$WRITE" -eq 1 ] && [ "$CHANGED" -gt 0 ]; then
  echo "$SCRIPT_TAG: ANNOUNCING WRITE — $CHANGED row(s) into rr_agent_map (table $TABLE_ID, identity_source=$IDENTITY_SOURCE)"
  mkdir -p "$RUN_DIR/chunks"
  while IFS= read -r job; do
    op="${job%%|*}"; cf="$RUN_DIR/chunks/${job#*|}"
    [ -f "$cf" ] || continue
    dl="$(deadline_left)"
    if [ "$dl" -le 0 ]; then echo "$SCRIPT_TAG: run deadline hit mid-write — remaining rows unwritten" >&2; RC=1; break; fi
    if [ "$op" = "PATCH" ]; then
      code="$(curl -sS --max-time "$dl" --connect-timeout 10 -X PATCH \
        -H "@$_HDR_FILE" -H 'Content-Type: application/json' \
        -o "$RUN_DIR/patch.out" -w '%{http_code}' --data-binary "@$cf" \
        "$N8N_ROWS_URL/update" 2>/dev/null || printf '000')"
      case "$code" in
        2*) python3 -c 'import json,sys;print("true" if json.load(open(sys.argv[1])) is True else "not-true")' "$RUN_DIR/patch.out" 2>/dev/null | grep -q '^true$' \
              && { UPD=$((UPD + 1)); } || { FAILED=$((FAILED + 1)); RC=1; printf '  patch %s: HTTP %s but not the documented true verdict\n' "$slug" "$code" >&2; } ;;
        *)  FAILED=$((FAILED + 1)); RC=1; printf '  patch %s: HTTP %s FAILED\n' "$slug" "${code:-none}" >&2 ;;
      esac
    else
      code="$(curl -sS --max-time "$dl" --connect-timeout 10 -X POST \
        -H "@$_HDR_FILE" -H 'Content-Type: application/json' \
        -o "$RUN_DIR/post.out" -w '%{http_code}' --data-binary "@$cf" \
        "$N8N_ROWS_URL" 2>/dev/null || printf '000')"
      case "$code" in
        2*) n="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("insertedRows",0))' "$RUN_DIR/post.out" 2>/dev/null || printf 0)"
            case "$n" in ''|*[!0-9]*) n=0 ;; esac
            INS=$((INS + n))
            [ "$n" -gt 0 ] || { FAILED=$((FAILED + 1)); RC=1; printf '  insert %s: HTTP %s insertedRows=%s (unproved)\n' "$slug" "$code" "$n" >&2; }
            printf '  insert: HTTP %s insertedRows=%s\n' "$code" "$n" ;;
        *)  FAILED=$((FAILED + 1)); RC=1; printf '  insert %s: HTTP %s FAILED\n' "$slug" "${code:-none}" >&2 ;;
      esac
    fi
  done < <(py jobs "$FINAL")
fi

# --- 3f. verify: read back, prove every reconciled row matches the runtime ---
VRC=0; VREASON=""
if [ "$MODE" = "verify" ] && [ -n "$_HDR_FILE" ]; then
  if VREASON="$(snapshot)"; then
    py verify "$FINAL" "$NSNAP" || VRC=1
  else
    echo "$SCRIPT_TAG: post-write read-back INCOMPLETE ($VREASON) — verification unproved" >&2
    VRC=1
  fi
fi

# --- 3g. report ACTUAL counts -------------------------------------------------
if [ "$PENDING" -gt 0 ]; then
  echo "$SCRIPT_TAG: PENDING entries ($PENDING) — roster is NOT complete (owner=$PENDING_OWNER)"
  py pending "$FINAL"
fi
# Persist the pending set (unresolved/inaccessible mappings with an owner) so
# the follow-up work survives this process. A zero-pending run still writes the
# ledger — an empty ledger is the proof that the roster reconciled clean.
if mkdir -p "$(dirname "$PENDING_LEDGER_PATH")" 2>/dev/null; then
  chmod 700 "$(dirname "$PENDING_LEDGER_PATH")" 2>/dev/null || true
  if py ledger "$FINAL" "$PENDING_LEDGER_PATH" "$PENDING_OWNER" "$IDENTITY_SOURCE" "$TABLE_ID" "$PAGES_READ" 2>/dev/null; then
    chmod 600 "$PENDING_LEDGER_PATH" 2>/dev/null || true
    echo "$SCRIPT_TAG: pending ledger -> $PENDING_LEDGER_PATH"
  else
    echo "$SCRIPT_TAG: WARNING — could not write the pending ledger ($PENDING_LEDGER_PATH)" >&2
    [ "$PENDING" -gt 0 ] && RC=1
  fi
else
  echo "$SCRIPT_TAG: WARNING — pending ledger directory not writable ($PENDING_LEDGER_PATH)" >&2
  [ "$PENDING" -gt 0 ] && RC=1
fi
COMPLETE=1
[ "$PENDING" -eq 0 ] && [ "$FAILED" -eq 0 ] && [ "$RC" -eq 0 ] && [ "$VRC" -eq 0 ] || COMPLETE=0
if [ "$MODE" = "dry" ]; then
  py emit "$FINAL" "aborted=0 duplicates=0 complete=$COMPLETE pages=$PAGES_READ"
else
  py emit "$FINAL" "aborted=0 duplicates=0 rows_inserted=$INS rows_updated=$UPD failed=$FAILED complete=$COMPLETE pages=$PAGES_READ identity_source=$IDENTITY_SOURCE"
fi
[ "$COMPLETE" -eq 1 ] || RC=1
exit "$RC"
