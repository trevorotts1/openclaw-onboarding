#!/usr/bin/env bash
# =============================================================================
# fleet-refresh.sh — PRD item 1.11
# =============================================================================
# The ONE way changes reach clients (all three layers):
#   Layer 1 — pull the pinned onboarding + CC versions (deployed = merged)
#   Layer 2 — sessions.reset the CEO/main agent (loaded = deployed)
#   Layer 3 — verify the marker is in the INJECTED system prompt, NOT just on disk
#
# Architecture (mirrors migrate-zhc-to-master-files.sh):
#   This script = bash wrapper: flags, box fan-out, concurrency, isolation.
#   shared-utils/fleet_refresh_runner.py = per-box 8-step state machine + verifier.
#
# USAGE:
#   bash scripts/fleet-refresh.sh                    # DRY-RUN (default — safe, read-only)
#   bash scripts/fleet-refresh.sh --apply            # deploy to every box in the fleet
#   bash scripts/fleet-refresh.sh --box <name>       # restrict to one box (repeatable)
#   bash scripts/fleet-refresh.sh --boxes-file <f>   # explicit box manifest (JSON)
#   bash scripts/fleet-refresh.sh --local            # run against THIS box only (no SSH)
#   bash scripts/fleet-refresh.sh --verify-only      # read-only verifier sweep (no pull/build/reset)
#   bash scripts/fleet-refresh.sh --max-parallel N   # concurrency cap (default 8)
#   bash scripts/fleet-refresh.sh --force-cc         # stash CC dirty tree instead of aborting
#   bash scripts/fleet-refresh.sh --expected-sha <s> # inform verifier of expected onboarding SHA
#   bash scripts/fleet-refresh.sh --help
#
# BOX MANIFEST FORMAT (--boxes-file):
#   JSON array of objects:
#   [
#     {
#       "name": "karen-vaughn",
#       "ssh_target": "karenvaughn@<host>",
#       "cf_tunnel_id": "bfbd47ae...",
#       "cf_access_env_prefix": "CF_ACCESS_KAREN",
#       "platform": "mac"
#     },
#     ...
#   ]
#
# SAFETY GUARANTEES:
#   • --dry-run is the default.  --apply must be passed explicitly.
#   • NEVER issues `openclaw gateway restart` (Mac err 125 → box DOWN).
#     Only `sessions.reset` is issued (a gateway CALL, not a process restart).
#   • Per-box failure is isolated: one box failing never aborts others.
#   • Aggregate exit: 0=all ok; 2=any partial/failed (CI-visible nonzero).
#   • Not a standing loop (loop doctrine): operator-invoked, not a cron.
#
# EXIT CODES:
#   0  all boxes ok (or dry-run completed)
#   1  fatal (e.g., cannot find runner, bad flags)
#   2  at least one box partial or failed
#
# PRD 1.11 — v11.5.0 (WAVE 3)
# =============================================================================
set -euo pipefail

# ── Script location ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_UTILS="$REPO_ROOT/shared-utils"
RUNNER="$SHARED_UTILS/fleet_refresh_runner.py"

# ── Defaults ──────────────────────────────────────────────────────────────────
APPLY=0
VERIFY_ONLY=0
LOCAL=0
FORCE_CC=0
MAX_PARALLEL=8
EXPECTED_SHA=""
BOXES_FILE=""
declare -a BOX_NAMES=()

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)        APPLY=1; shift ;;
    --dry-run)      APPLY=0; shift ;;
    --verify-only)  VERIFY_ONLY=1; shift ;;
    --local)        LOCAL=1; shift ;;
    --force-cc)     FORCE_CC=1; shift ;;
    --box)          BOX_NAMES+=("$2"); shift 2 ;;
    --boxes-file)   BOXES_FILE="$2"; shift 2 ;;
    --max-parallel) MAX_PARALLEL="$2"; shift 2 ;;
    --expected-sha) EXPECTED_SHA="$2"; shift 2 ;;
    --help|-h)
      grep '^#' "$0" | grep -v '^#!/' | sed 's/^# \?//' | head -60
      exit 0
      ;;
    *)
      echo "Unknown flag: $1" >&2
      echo "Run $0 --help for usage." >&2
      exit 1
      ;;
  esac
done

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [ ! -f "$RUNNER" ]; then
  echo "FATAL: runner not found at $RUNNER" >&2
  echo "Run this script from the openclaw-onboarding repo." >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/cc-compat.json" ]; then
  echo "FATAL: cc-compat.json not found at $REPO_ROOT/cc-compat.json" >&2
  echo "This file is required for fleet-refresh to know which CC version to deploy." >&2
  exit 1
fi

# ── Mode banner ───────────────────────────────────────────────────────────────
if [ $APPLY -eq 1 ]; then
  echo "[fleet-refresh] MODE: APPLY (--apply passed)"
  echo "[fleet-refresh] Will deploy onboarding + CC + reset CEO sessions."
elif [ $VERIFY_ONLY -eq 1 ]; then
  echo "[fleet-refresh] MODE: VERIFY-ONLY (read-only verifier sweep)"
else
  echo "[fleet-refresh] MODE: DRY-RUN (default — no mutations)"
  echo "[fleet-refresh] Pass --apply to perform a real deployment."
fi

# ── Build the flags for the runner ───────────────────────────────────────────
RUNNER_FLAGS=""
[ $APPLY -eq 1 ]       && RUNNER_FLAGS="$RUNNER_FLAGS --apply"
[ $VERIFY_ONLY -eq 1 ] && RUNNER_FLAGS="$RUNNER_FLAGS --verify-only"
[ $LOCAL -eq 1 ]       && RUNNER_FLAGS="$RUNNER_FLAGS --local"
[ $FORCE_CC -eq 1 ]    && RUNNER_FLAGS="$RUNNER_FLAGS --force-cc"
[ -n "$EXPECTED_SHA" ] && RUNNER_FLAGS="$RUNNER_FLAGS --expected-sha $EXPECTED_SHA"

# ── Resolve box list ──────────────────────────────────────────────────────────
TMPDIR_RESULTS="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RESULTS"' EXIT

# If --local, run once against this machine with no SSH
if [ $LOCAL -eq 1 ]; then
  echo "[fleet-refresh] Running in LOCAL mode (this box only, no SSH)"
  BOX_NAMES=("local")
fi

# If --boxes-file, load it
declare -a BOX_ENTRIES=()
if [ -n "$BOXES_FILE" ]; then
  if [ ! -f "$BOXES_FILE" ]; then
    echo "FATAL: --boxes-file not found: $BOXES_FILE" >&2
    exit 1
  fi
  # Extract box names from the JSON manifest
  while IFS= read -r name; do
    BOX_ENTRIES+=("$name")
  done < <(python3 -c "
import json, sys
entries = json.load(open('$BOXES_FILE'))
for e in entries:
    print(e.get('name',''))
" 2>/dev/null)
  if [ ${#BOX_ENTRIES[@]} -eq 0 ]; then
    echo "FATAL: boxes-file has no valid entries" >&2
    exit 1
  fi
  echo "[fleet-refresh] Loaded ${#BOX_ENTRIES[@]} boxes from $BOXES_FILE"
fi

# If specific boxes named, use those
if [ ${#BOX_NAMES[@]} -gt 0 ]; then
  echo "[fleet-refresh] Restricting to boxes: ${BOX_NAMES[*]}"
fi

# Determine final box set
FINAL_BOXES=()
if [ ${#BOX_NAMES[@]} -gt 0 ]; then
  FINAL_BOXES=("${BOX_NAMES[@]}")
elif [ ${#BOX_ENTRIES[@]} -gt 0 ]; then
  FINAL_BOXES=("${BOX_ENTRIES[@]}")
elif [ $LOCAL -eq 1 ]; then
  FINAL_BOXES=("local")
else
  echo "[fleet-refresh] No boxes specified. Use --local for this box, --box <name>, or --boxes-file <file>."
  echo "[fleet-refresh] In --local mode the runner operates on this machine directly."
  exit 1
fi

echo "[fleet-refresh] Running on ${#FINAL_BOXES[@]} box(es): ${FINAL_BOXES[*]}"
echo "[fleet-refresh] max-parallel: $MAX_PARALLEL"
echo ""

# ── Fan-out: run each box in parallel (bounded by MAX_PARALLEL) ───────────────
run_box_local() {
  local box="$1"
  local result_file="$TMPDIR_RESULTS/${box}.json"

  python3 "$RUNNER" \
    --box "$box" \
    --shared-utils "$SHARED_UTILS" \
    --repo-root "$REPO_ROOT" \
    $RUNNER_FLAGS \
    > "$result_file" 2>&1
  local rc=$?

  # If exit code is 1 or 2 and the result file is not JSON, wrap it
  if [ $rc -ne 0 ] && ! python3 -c "import json; json.load(open('$result_file'))" 2>/dev/null; then
    local msg
    msg=$(cat "$result_file" 2>/dev/null | head -5)
    echo "{\"box\":\"$box\",\"result\":\"failed\",\"errors\":[\"runner exited $rc: $msg\"]}" > "$result_file"
  fi
  return $rc
}

run_box_ssh() {
  local box="$1"
  local box_config="$2"
  local result_file="$TMPDIR_RESULTS/${box}.json"

  # Extract SSH target from the boxes-file config
  local ssh_target
  ssh_target=$(python3 -c "
import json
entries = json.load(open('$BOXES_FILE'))
for e in entries:
    if e.get('name') == '$box':
        print(e.get('ssh_target',''))
        break
")
  if [ -z "$ssh_target" ]; then
    echo "{\"box\":\"$box\",\"result\":\"failed\",\"errors\":[\"ssh_target not found in boxes-file\"]}" > "$result_file"
    return 2
  fi

  # Build the remote command (the runner + shared-utils must be on the remote box)
  # The runner is invoked via SSH; shared-utils and repo-root are the remote paths
  local remote_runner="${REMOTE_ONBOARDING_ROOT:-~/.openclaw/skills/onboarding}/shared-utils/fleet_refresh_runner.py"
  local remote_su="${REMOTE_ONBOARDING_ROOT:-~/.openclaw/skills/onboarding}/shared-utils"
  local remote_root="${REMOTE_ONBOARDING_ROOT:-~/.openclaw/skills/onboarding}"

  # CF Access tunnel support
  local cf_prefix
  cf_prefix=$(python3 -c "
import json
entries = json.load(open('$BOXES_FILE'))
for e in entries:
    if e.get('name') == '$box':
        print(e.get('cf_access_env_prefix',''))
        break
" 2>/dev/null)

  # SSH with CF Access service token if available
  local ssh_opts="-o StrictHostKeyChecking=no -o ConnectTimeout=30"
  local ssh_extra_env=""
  if [ -n "$cf_prefix" ]; then
    local client_id_var="${cf_prefix}_SVC_CLIENT_ID"
    local secret_var="${cf_prefix}_SVC_CLIENT_SECRET"
    if [ -n "${!client_id_var:-}" ] && [ -n "${!secret_var:-}" ]; then
      ssh_extra_env="CF_ACCESS_CLIENT_ID=${!client_id_var} CF_ACCESS_CLIENT_SECRET=${!secret_var}"
    fi
  fi

  # shellcheck disable=SC2086
  env $ssh_extra_env ssh $ssh_opts "$ssh_target" \
    "python3 $remote_runner \
      --box $box \
      --shared-utils $remote_su \
      --repo-root $remote_root \
      $RUNNER_FLAGS" \
    > "$result_file" 2>&1
  local rc=$?

  if [ $rc -ne 0 ] && ! python3 -c "import json; json.load(open('$result_file'))" 2>/dev/null; then
    local msg
    msg=$(cat "$result_file" 2>/dev/null | head -3)
    echo "{\"box\":\"$box\",\"result\":\"failed\",\"errors\":[\"SSH/runner exited $rc: $msg\"]}" > "$result_file"
  fi
  return $rc
}

# Track active jobs
declare -a PIDS=()
declare -a PID_BOXES=()

run_with_concurrency() {
  local box="$1"

  # Wait if at max-parallel
  while [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ]; do
    local new_pids=()
    local new_boxes=()
    for i in "${!PIDS[@]}"; do
      if kill -0 "${PIDS[$i]}" 2>/dev/null; then
        new_pids+=("${PIDS[$i]}")
        new_boxes+=("${PID_BOXES[$i]}")
      fi
    done
    PIDS=("${new_pids[@]+"${new_pids[@]}"}")
    PID_BOXES=("${new_boxes[@]+"${new_boxes[@]}"}")
    [ "${#PIDS[@]}" -ge "$MAX_PARALLEL" ] && sleep 0.5
  done

  if [ $LOCAL -eq 1 ] || [ "$box" = "local" ] || [ -z "$BOXES_FILE" ]; then
    run_box_local "$box" &
  else
    run_box_ssh "$box" "$BOXES_FILE" &
  fi
  PIDS+=($!)
  PID_BOXES+=("$box")
}

for box in "${FINAL_BOXES[@]}"; do
  echo "[fleet-refresh] Queuing box: $box"
  run_with_concurrency "$box"
done

# Wait for all remaining jobs
for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
  wait "$pid" || true
done

echo ""
echo "[fleet-refresh] ═══════════════════════════════════════════"
echo "[fleet-refresh]  FLEET SUMMARY"
echo "[fleet-refresh] ═══════════════════════════════════════════"

# ── Collect + print results ───────────────────────────────────────────────────
ALL_RESULTS="[]"
ALL_OK=1
ANY_FAILED=0

for box in "${FINAL_BOXES[@]}"; do
  result_file="$TMPDIR_RESULTS/${box}.json"
  if [ ! -f "$result_file" ]; then
    echo "[fleet-refresh]   $box — FATAL: no result file"
    ANY_FAILED=1
    continue
  fi

  box_result=$(cat "$result_file")

  # Validate JSON
  if ! echo "$box_result" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
    echo "[fleet-refresh]   $box — FATAL: invalid JSON result"
    echo "$box_result" | head -5
    ANY_FAILED=1
    continue
  fi

  # Extract key fields
  result_val=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('result','unknown'))")
  onb_ver=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('onboarding_version','?'))")
  cc_ver=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('cc_version','?'))")
  loaded=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); l=d.get('loaded',{}); print('YES' if l.get('present') else 'NO')")
  confidence=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('loaded',{}).get('loaded_confidence','?'))")
  errors=$(echo "$box_result" | python3 -c "import json,sys; d=json.load(sys.stdin); errs=d.get('errors',[]); print('; '.join(errs[:2]) if errs else '')")

  case "$result_val" in
    ok)      icon="✓" ;;
    dry-run) icon="○" ;;
    partial) icon="△"; ANY_FAILED=1 ;;
    *)       icon="✗"; ANY_FAILED=1; ALL_OK=0 ;;
  esac

  echo "[fleet-refresh]   $icon  $box  [result=$result_val  onb=$onb_ver  cc=v$cc_ver  loaded=$loaded($confidence)]"
  [ -n "$errors" ] && echo "[fleet-refresh]        ERRORS: $errors"

  # Accumulate into fleet summary JSON
  ALL_RESULTS=$(echo "$ALL_RESULTS" | python3 -c "
import json,sys
arr = json.load(sys.stdin)
arr.append($box_result)
print(json.dumps(arr))
" 2>/dev/null || echo "$ALL_RESULTS")

  # ── AF4: update fleet manifest with per-box loaded state ──────────────────
  # This is the "loaded=YES" tracker that drives the legacy-retirement trigger.
  # Only update for apply/verify runs (not dry-run) because dry-run does not
  # mutate client boxes and the loaded state may be stale.
  if [ $APPLY -eq 1 ] || [ $VERIFY_ONLY -eq 1 ]; then
    python3 "$SHARED_UTILS/fleet_manifest.py" \
      --repo-root "$REPO_ROOT" \
      --update-box "$box" \
      --box-result "$box_result" \
      --dry-run \
      2>/dev/null || true
    # Note: --dry-run here means "skip the gh issue call for per-box updates"
    # The retirement trigger check (with real gh) runs once at the end.
  fi
done

echo "[fleet-refresh] ═══════════════════════════════════════════"

# Write fleet summary
SUMMARY_FILE="$REPO_ROOT/.fleet-refresh-summary.json"
echo "$ALL_RESULTS" | python3 -c "
import json,sys
arr = json.load(sys.stdin)
print(json.dumps(arr, indent=2))
" > "$SUMMARY_FILE" 2>/dev/null || true
echo "[fleet-refresh] Fleet summary written to: $SUMMARY_FILE"

# ── AF4: check retirement trigger once all boxes are collected ────────────────
# After every apply/verify run, check if ALL known boxes in fleet-manifest.json
# now have loaded=YES.  If so, fire the deterministic retirement trigger:
# write the legacy-retirement-triggered sentinel + open/update the GitHub issue.
# This is a LOUD observable event — logged to stderr and to the sentinel file.
#
# The trigger is idempotent: subsequent runs do nothing if already triggered.
# dry-run mode: sentinel is written but `gh issue create` is skipped.
if [ $APPLY -eq 1 ] || [ $VERIFY_ONLY -eq 1 ]; then
  echo ""
  echo "[fleet-refresh] ── AF4 Legacy Retirement Trigger check ──────────────"
  FLEET_MANIFEST_DRY_RUN=$([ $APPLY -eq 1 ] && echo "0" || echo "1")
  export FLEET_MANIFEST_DRY_RUN
  TRIGGER_STATUS=$(python3 "$SHARED_UTILS/fleet_manifest.py" \
    --repo-root "$REPO_ROOT" \
    --check-trigger \
    2>/dev/null || echo '{"trigger_fired":false,"error":"fleet_manifest.py failed"}')
  TRIGGER_FIRED=$(echo "$TRIGGER_STATUS" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print(d.get('trigger_fired',False))" 2>/dev/null || echo "False")
  ALREADY=$(echo "$TRIGGER_STATUS" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print(d.get('already_triggered',False))" 2>/dev/null || echo "False")
  NOT_LOADED=$(echo "$TRIGGER_STATUS" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); nl=d.get('not_loaded_boxes',[]); print(', '.join(nl) if nl else '(none)')" 2>/dev/null || echo "?")
  TOTAL=$(echo "$TRIGGER_STATUS" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print(d.get('total_boxes',0))" 2>/dev/null || echo "0")
  LOADED_N=$(echo "$TRIGGER_STATUS" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print(len(d.get('loaded_boxes',[])))" 2>/dev/null || echo "0")

  if [ "$TRIGGER_FIRED" = "True" ]; then
    echo "[fleet-refresh] ✓ RETIREMENT TRIGGER FIRED — all $TOTAL boxes loaded=YES"
    echo "[fleet-refresh]   Sentinel written: $REPO_ROOT/legacy-retirement-triggered"
    ISSUE_NUM=$(echo "$TRIGGER_STATUS" | python3 -c \
      "import json,sys; d=json.load(sys.stdin); n=d.get('issue_number'); print(f'#{n}' if n else '(dry-run or gh unavailable)')" 2>/dev/null || echo "")
    echo "[fleet-refresh]   GitHub issue: $ISSUE_NUM"
    echo "[fleet-refresh]   Action: retire legacy shim + clawd fallbacks (see docs/LEGACY-RETIREMENT.md)"
  elif [ "$ALREADY" = "True" ]; then
    echo "[fleet-refresh]   Retirement trigger already fired previously — no action needed"
  else
    echo "[fleet-refresh]   Retirement trigger: $LOADED_N/$TOTAL boxes loaded=YES (waiting: $NOT_LOADED)"
  fi
  echo "[fleet-refresh] ─────────────────────────────────────────────────────"
fi

if [ $ANY_FAILED -eq 1 ]; then
  echo "[fleet-refresh] RESULT: PARTIAL/FAILED — check errors above"
  exit 2
else
  echo "[fleet-refresh] RESULT: OK — all boxes refreshed"
  exit 0
fi
