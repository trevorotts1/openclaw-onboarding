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
#   • Aggregate exit: 0=all ok; 2=any partial/failed; 3=any unknown (CI-visible nonzero).
#   • CC deploy goes through scripts/atomic-deploy.sh ONLY (B.2).
#     No raw npm build or direct pm2 restart paths exist.
#   • Not a standing loop (loop doctrine): operator-invoked, not a cron.
#
# EXIT CODES:
#   0  all boxes ok (or dry-run completed)
#   1  fatal (e.g., cannot find runner, bad flags)
#   2  at least one box partial or failed
#   3  at least one box UNKNOWN (atomic-deploy exit 3 — CC state indeterminate)
#
# PRD 1.11 — v11.14.0 (WAVE 5)
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

# ── Wave-5 deploy preflight (FAIL-CLOSED — NO BYPASS) ────────────────────────
# Runs unconditionally BEFORE any box work (including dry-run).
# Blocks the entire fan-out until B.1 + B.2 + B.3 are merged to origin/main of
# trevorotts1/blackceo-command-center.
# There is NO flag and NO env-var that bypasses this check.
wave5_deploy_preflight() {
  local repo="trevorotts1/blackceo-command-center"
  local b1="scripts/cc-health-check.sh"
  local b2="scripts/atomic-deploy.sh"
  # B.3 duck-test: probe duck-test.ts first (TypeScript source), fall back to
  # duck-test (extensionless/shell).  First 200 wins; both absent = BLOCKED.
  local b3_candidates=("tests/e2e/duck-test.ts" "tests/e2e/duck-test")
  local missing=()

  echo "[fleet-refresh] Wave-5 preflight: checking B.1 + B.2 + B.3 on origin/main of ${repo} ..."

  # ── B.1 and B.2: single-path checks ─────────────────────────────────────────
  for entry in "B.1:${b1}" "B.2:${b2}"; do
    local label="${entry%%:*}"
    local path="${entry#*:}"
    local api_url="https://api.github.com/repos/${repo}/contents/${path}?ref=main"

    local http_code
    local curl_opts=(-s -o /dev/null -w "%{http_code}" --max-time 20)
    if [ -n "${GITHUB_TOKEN:-}" ]; then
      curl_opts+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
    fi
    curl_opts+=(-H "Accept: application/vnd.github+json" "$api_url")

    if command -v curl >/dev/null 2>&1; then
      http_code=$(curl "${curl_opts[@]}" 2>/dev/null || echo "000")
    else
      http_code="000"
    fi

    if [ "$http_code" = "200" ]; then
      echo "[fleet-refresh]   ${label} PRESENT on main: ${path}"
    else
      missing+=("${label}:${path}:${http_code}")
      echo "[fleet-refresh]   ${label} MISSING on main (HTTP ${http_code}): ${path}" >&2
    fi
  done

  # ── B.3: duck-test path duck-test (duck-test.ts OR duck-test) ───────────────
  # Probes duck-test.ts first; if absent tries extensionless duck-test.
  # Either 200 satisfies the gate.  This makes the preflight resilient to CC
  # repos that ship either the TypeScript source or a compiled/extensionless copy.
  local b3_found=0
  for b3_candidate in "${b3_candidates[@]}"; do
    local b3_url="https://api.github.com/repos/${repo}/contents/${b3_candidate}?ref=main"
    local b3_curl_opts=(-s -o /dev/null -w "%{http_code}" --max-time 20)
    if [ -n "${GITHUB_TOKEN:-}" ]; then
      b3_curl_opts+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
    fi
    b3_curl_opts+=(-H "Accept: application/vnd.github+json" "$b3_url")

    local b3_http="000"
    if command -v curl >/dev/null 2>&1; then
      b3_http=$(curl "${b3_curl_opts[@]}" 2>/dev/null || echo "000")
    fi

    if [ "$b3_http" = "200" ]; then
      b3_found=1
      echo "[fleet-refresh]   B.3 PRESENT on main: ${b3_candidate}"
      break
    fi
  done

  if [ $b3_found -eq 0 ]; then
    missing+=("B.3:tests/e2e/duck-test{.ts,}:404")
    echo "[fleet-refresh]   B.3 MISSING on main (checked duck-test.ts AND duck-test)" >&2
  fi

  if [ ${#missing[@]} -gt 0 ]; then
    echo "" >&2
    echo "[fleet-refresh] ╔══════════════════════════════════════════════════════════════════╗" >&2
    echo "[fleet-refresh] ║  FATAL: Wave-5 deploy BLOCKED — B.1+B.2+B.3 preflight FAILED    ║" >&2
    echo "[fleet-refresh] ╠══════════════════════════════════════════════════════════════════╣" >&2
    for entry in "${missing[@]}"; do
      local lbl="${entry%%:*}"
      local rest="${entry#*:}"
      local fp="${rest%%:*}"
      echo "[fleet-refresh] ║  MISSING from ${repo} @ main:              ║" >&2
      echo "[fleet-refresh] ║    [${lbl}] ${fp}" >&2
    done
    echo "[fleet-refresh] ╠══════════════════════════════════════════════════════════════════╣" >&2
    echo "[fleet-refresh] ║  Wave 5 is BLOCKED until ALL three paths are merged to main:     ║" >&2
    echo "[fleet-refresh] ║    B.1  scripts/cc-health-check.sh                               ║" >&2
    echo "[fleet-refresh] ║    B.2  scripts/atomic-deploy.sh                                 ║" >&2
    echo "[fleet-refresh] ║    B.3  tests/e2e/duck-test.ts  (or duck-test)                   ║" >&2
    echo "[fleet-refresh] ║                                                                  ║" >&2
    echo "[fleet-refresh] ║  Merge B.1 + B.2 + B.3 to main in blackceo-command-center,      ║" >&2
    echo "[fleet-refresh] ║  then retry.                                                     ║" >&2
    echo "[fleet-refresh] ╚══════════════════════════════════════════════════════════════════╝" >&2
    exit 1
  fi

  echo "[fleet-refresh] Wave-5 preflight PASSED — B.1 + B.2 + B.3 all present on origin/main."
}

wave5_deploy_preflight

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

  # Remote clone-path resolution happens AFTER the SSH env (CF Access) is set up,
  # so the detection probe reuses the same connection options.  See the
  # detect-remote-onboarding-root block below (right before the runner invocation).

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

  # ── Detect the on-box onboarding clone location ─────────────────────────────
  # The clone is NOT at a single fixed path across the fleet: legacy boxes keep it
  # at ~/.openclaw/skills/onboarding, but the majority now live at
  # ~/clawd/openclaw-onboarding (and a few at the install.sh CANDIDATES layouts).
  # Probe the known candidates ON THE REMOTE BOX and use whichever actually holds
  # shared-utils/fleet_refresh_runner.py.  An explicit REMOTE_ONBOARDING_ROOT
  # override still wins (and is verified) so operators can force a path.
  #
  # The detection runs in a single SSH round-trip; the remote snippet prints the
  # resolved clone root to stdout, or nothing if no candidate is valid.
  local remote_root remote_su remote_runner
  local remote_candidates
  if [ -n "${REMOTE_ONBOARDING_ROOT:-}" ]; then
    # Operator-forced path: still verify it carries the runner before using it.
    # Normalize a leading '~/' to '$HOME/' so the remote shell expands it.
    local forced="${REMOTE_ONBOARDING_ROOT/#\~\//\$HOME/}"
    remote_candidates="\"$forced\""
  else
    # Probe order: legacy default first (backward-compatible), then the layout
    # the majority of the fleet actually uses, then the install.sh CANDIDATES.
    remote_candidates='"$HOME/.openclaw/skills/onboarding" "$HOME/clawd/openclaw-onboarding" "$HOME/openclaw-onboarding" "$HOME/.openclaw/onboarding"'
  fi
  # Remote snippet: walk the candidates, print the first that carries the runner.
  local detect_script="for d in $remote_candidates; do
  [ -f \"\$d/shared-utils/fleet_refresh_runner.py\" ] && { printf '%s\\n' \"\$d\"; exit 0; }
done; exit 0"

  # shellcheck disable=SC2086
  remote_root=$(env $ssh_extra_env ssh $ssh_opts "$ssh_target" "$detect_script" 2>/dev/null \
    | head -1 | tr -d '\r')

  if [ -z "$remote_root" ]; then
    local probed
    if [ -n "${REMOTE_ONBOARDING_ROOT:-}" ]; then
      probed="REMOTE_ONBOARDING_ROOT=$REMOTE_ONBOARDING_ROOT"
    else
      probed="~/.openclaw/skills/onboarding, ~/clawd/openclaw-onboarding, ~/openclaw-onboarding, ~/.openclaw/onboarding"
    fi
    echo "{\"box\":\"$box\",\"result\":\"failed\",\"errors\":[\"onboarding clone not found on box: no candidate dir contains shared-utils/fleet_refresh_runner.py (probed: $probed). Clone trevorotts1/openclaw-onboarding to one of those paths, or set REMOTE_ONBOARDING_ROOT to its location, then retry.\"]}" > "$result_file"
    return 2
  fi

  # Resolve the runner + shared-utils relative to the detected clone root.
  remote_su="$remote_root/shared-utils"
  remote_runner="$remote_su/fleet_refresh_runner.py"
  echo "[fleet-refresh]   $box — using onboarding clone: $remote_root" >&2

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
ANY_UNKNOWN=0

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
  # B.6: embedding-health outcome (extracted from steps dict)
  emb_health=$(echo "$box_result" | python3 -c "
import json,sys
d=json.load(sys.stdin)
v=d.get('steps',{}).get('embedding-health','not-run')
if v=='pass': print('PASS')
elif v is None or v=='not-run': print('NOT-RUN')
elif str(v).startswith('warn:'): print('WARN')
elif str(v).startswith('failed:'): print('FAIL')
else: print(str(v)[:16])
" 2>/dev/null || echo "?")

  case "$result_val" in
    ok)      icon="✓" ;;
    dry-run) icon="○" ;;
    partial)
      # Check for [exit-3] transient marker in steps — if present, mark UNKNOWN
      # rather than FAILED.  UNKNOWN boxes are retried; on repeated failure they
      # are marked UNKNOWN in the fleet manifest (never destructive on exit-3).
      has_exit3=$(echo "$box_result" | python3 -c "
import json,sys
d=json.load(sys.stdin)
steps=d.get('steps',{})
print('yes' if any('[exit-3]' in str(v) for v in steps.values()) else 'no')
" 2>/dev/null || echo "no")
      if [ "$has_exit3" = "yes" ]; then
        icon="?"; ANY_UNKNOWN=1
        echo "[fleet-refresh]   ? $box — TRANSIENT (exit-3): retry then mark UNKNOWN if repeated"
      else
        icon="△"; ANY_FAILED=1
      fi
      ;;
    unknown) icon="?"; ANY_UNKNOWN=1 ;;
    *)       icon="✗"; ANY_FAILED=1; ALL_OK=0 ;;
  esac

  echo "[fleet-refresh]   $icon  $box  [result=$result_val  onb=$onb_ver  cc=v$cc_ver  loaded=$loaded($confidence)  embed=$emb_health]"
  [ -n "$errors" ] && echo "[fleet-refresh]        ERRORS: $errors"

  # Accumulate into fleet summary JSON
  ALL_RESULTS=$(echo "$ALL_RESULTS" | python3 -c "
import json,sys
arr = json.load(sys.stdin)
arr.append($box_result)
print(json.dumps(arr))
" 2>/dev/null || echo "$ALL_RESULTS")
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

# ── Retirement trigger check (APPLY mode only — never dry-run) ────────────────
# Persists per-box loaded=YES state to the fleet loaded-state manifest.
# When every box in the manifest reports loaded=YES, opens/updates the
# "retire legacy shim + clawd fallbacks" GitHub issue exactly once.
#
# DRY-RUN SAFETY: the retirement_triggered flag is NEVER set during dry-run.
# This was the root cause of the AF4 QC gap: an earlier design persisted
# retirement_triggered=True during --dry-run --update-box, which permanently
# blocked gh issue creation. The correct intent (documented in the original
# code comment: "retirement trigger check with real gh runs once at the end")
# requires that dry-run is fully inert for this path.
LOADED_STATE_FILE="$REPO_ROOT/.fleet-loaded-state.json"
RETIREMENT_ISSUE_TITLE="Retire legacy shim + clawd fallbacks (auto-triggered: all boxes loaded)"
RETIREMENT_ISSUE_LABEL="retirement-tracker"

# Only run the retirement-trigger machinery in APPLY mode.
# Dry-run and verify-only are 100% inert for this path.
if [ $APPLY -eq 1 ]; then
  python3 - <<PYEOF
import json, os, sys, subprocess, time
from pathlib import Path

loaded_state_file = Path("$LOADED_STATE_FILE")
all_results_json  = """$ALL_RESULTS"""
apply             = True
dry_run           = False

# Load the current per-box loaded-state manifest (create if absent).
state = {}
if loaded_state_file.is_file():
    try:
        state = json.loads(loaded_state_file.read_text())
    except Exception:
        state = {}

# Validate the state schema:
#   state["boxes"]              = { box_name: { "loaded": bool, "ts": int, ... } }
#   state["retirement_triggered"] = bool  (set to True once; never unset)
if "boxes" not in state or not isinstance(state["boxes"], dict):
    state["boxes"] = {}
if "retirement_triggered" not in state:
    state["retirement_triggered"] = False

# Parse this run's results and update per-box loaded state.
try:
    results = json.loads(all_results_json)
except Exception:
    results = []

for box_result in results:
    box  = box_result.get("box", "")
    if not box:
        continue
    loaded_present = box_result.get("loaded", {}).get("present", False)
    result_val     = box_result.get("result", "unknown")
    # Only count a box as loaded if the run actually applied (result=ok).
    # A dry-run result is never propagated here (APPLY=1 guard above),
    # but be explicit: dry-run result strings MUST NOT advance the state.
    if result_val in ("ok",):
        state["boxes"][box] = {
            "loaded":    loaded_present,
            "result":    result_val,
            "ts":        int(time.time()),
            "onboarding_version": box_result.get("onboarding_version", "unknown"),
        }

# Persist updated state to the manifest (APPLY only — dry-run never reaches here).
try:
    loaded_state_file.write_text(json.dumps(state, indent=2))
    print(f"[fleet-refresh] Retirement manifest updated: {loaded_state_file}")
except Exception as e:
    print(f"[fleet-refresh] WARNING: could not write loaded-state manifest: {e}", file=sys.stderr)

# Check whether ALL tracked boxes are now loaded=YES.
if not state["boxes"]:
    print("[fleet-refresh] Retirement check: no boxes in manifest yet — skipping")
    sys.exit(0)

all_loaded = all(entry.get("loaded", False) for entry in state["boxes"].values())
not_loaded = [b for b, e in state["boxes"].items() if not e.get("loaded", False)]

print(f"[fleet-refresh] Retirement check: {len(state['boxes'])} boxes tracked; "
      f"not-loaded={not_loaded if not_loaded else '(none)'}")

if not all_loaded:
    print(f"[fleet-refresh] Retirement trigger NOT fired: {len(not_loaded)} box(es) not loaded yet.")
    sys.exit(0)

if state["retirement_triggered"]:
    print("[fleet-refresh] Retirement trigger: all boxes loaded=YES — issue already opened; skipping duplicate create.")
    sys.exit(0)

# ALL boxes loaded=YES and retirement not yet triggered — fire the trigger.
print("[fleet-refresh] RETIREMENT TRIGGER: all boxes loaded=YES — opening/updating retirement tracker issue.")

issue_title  = "$RETIREMENT_ISSUE_TITLE"
issue_label  = "$RETIREMENT_ISSUE_LABEL"
box_list     = "\n".join(f"- {b}" for b in sorted(state["boxes"].keys()))
triggered_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

issue_body = f"""## Automated Retirement Trigger

The fleet-refresh.sh retirement-clock fired because **every tracked box
reports \`loaded=YES\`** (CEO_ORCHESTRATOR_RULE_V2 is in the live system
prompt). The deprecation shim and legacy-root fallbacks documented in
\`docs/LEGACY-RETIREMENT.md\` are now safe to remove.

**Triggered:** {triggered_ts}

**All-loaded boxes ({len(state['boxes'])}):**
{box_list}

## Retirement tasks

Follow the plan in \`docs/LEGACY-RETIREMENT.md\`:

1. Remove the \`roots.extend([HOME / "clawd" / ..., ...])\` blocks from:
   - \`32-command-center-setup/scripts/generate-kpi-rollup.py\`
   - \`32-command-center-setup/scripts/generate-brand-css.py\`
   - \`32-command-center-setup/scripts/seed-workspaces.py\`
   - \`32-command-center-setup/scripts/seed-dashboard-content.py\`
2. Remove equivalent blocks from Skill 23 and Skill 22 files (see \`LEGACY-RETIREMENT.md\`).
3. Consolidate \`shared-utils/key_resolver.py\` secrets path into \`api_key_utils.py\`.
4. Remove the DEPRECATED SHIM marker from \`23-ai-workforce-blueprint/scripts/select-persona-for-task.py\`.
5. Clear \`docs/LEGACY-RETIREMENT.md\` tracked-files tables (empty = zero local loops allowed).
6. The CI guard (\`AF3: local-candidate-loop guard\`) will then enforce zero local loops.

_Auto-opened by fleet-refresh.sh v11.13.0 retirement-clock._
"""

# Attempt to create/update the GitHub issue via `gh`.
gh_bin = subprocess.run(["which", "gh"], capture_output=True, text=True).stdout.strip()
if not gh_bin:
    print("[fleet-refresh] WARNING: gh not on PATH — writing trigger sentinel file instead.")
    trigger_file = Path("$REPO_ROOT") / ".fleet-retirement-triggered"
    trigger_file.write_text(json.dumps({
        "triggered_ts": triggered_ts,
        "boxes": list(state["boxes"].keys()),
        "reason": "gh not on PATH",
    }, indent=2))
    print(f"[fleet-refresh] Retirement trigger sentinel written: {trigger_file}")
else:
    # Check for an existing open retirement-tracker issue first.
    existing = subprocess.run(
        ["gh", "issue", "list",
         "--repo", "trevorotts1/openclaw-onboarding",
         "--label", issue_label,
         "--state", "open",
         "--json", "number,title",
         "--limit", "5"],
        capture_output=True, text=True, timeout=30,
    )
    existing_number = None
    if existing.returncode == 0:
        try:
            existing_issues = json.loads(existing.stdout)
            for iss in existing_issues:
                if "retire" in iss.get("title", "").lower() or "retirement" in iss.get("title", "").lower():
                    existing_number = iss["number"]
                    break
        except Exception:
            pass

    if existing_number:
        # Update (comment on) the existing issue.
        result = subprocess.run(
            ["gh", "issue", "comment", str(existing_number),
             "--repo", "trevorotts1/openclaw-onboarding",
             "--body", f"**Retirement clock re-confirmed {triggered_ts}:** all {len(state['boxes'])} boxes still loaded=YES.\\n\\n{box_list}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print(f"[fleet-refresh] Updated existing retirement issue #{existing_number}")
        else:
            print(f"[fleet-refresh] WARNING: gh issue comment failed: {result.stderr[:200]}", file=sys.stderr)
    else:
        # Create a new issue.
        result = subprocess.run(
            ["gh", "issue", "create",
             "--repo", "trevorotts1/openclaw-onboarding",
             "--title", issue_title,
             "--label", issue_label,
             "--body", issue_body],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            print(f"[fleet-refresh] Retirement issue created: {issue_url}")
        else:
            print(f"[fleet-refresh] WARNING: gh issue create failed: {result.stderr[:200]}", file=sys.stderr)
            # Fall back to sentinel file so the trigger isn't lost.
            trigger_file = Path("$REPO_ROOT") / ".fleet-retirement-triggered"
            trigger_file.write_text(json.dumps({
                "triggered_ts": triggered_ts,
                "boxes": list(state["boxes"].keys()),
                "gh_error": result.stderr[:200],
            }, indent=2))
            print(f"[fleet-refresh] Retirement trigger sentinel written: {trigger_file}")

# Mark retirement_triggered=True in the manifest so we never duplicate.
state["retirement_triggered"] = True
try:
    loaded_state_file.write_text(json.dumps(state, indent=2))
except Exception as e:
    print(f"[fleet-refresh] WARNING: could not persist retirement_triggered flag: {e}", file=sys.stderr)

PYEOF
fi

if [ $ANY_FAILED -eq 1 ]; then
  echo "[fleet-refresh] RESULT: PARTIAL/FAILED — check errors above"
  exit 2
elif [ $ANY_UNKNOWN -eq 1 ]; then
  echo "[fleet-refresh] RESULT: UNKNOWN — at least one box returned exit 3 (CC state indeterminate)"
  echo "[fleet-refresh]   atomic-deploy.sh exit 3 means the health-check was inconclusive after all retries."
  echo "[fleet-refresh]   No rollback was performed on those boxes. Operator must investigate."
  exit 3
else
  echo "[fleet-refresh] RESULT: OK — all boxes refreshed"
  exit 0
fi
