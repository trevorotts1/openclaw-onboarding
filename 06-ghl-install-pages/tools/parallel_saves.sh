#!/usr/bin/env bash
# parallel_saves.sh — fan-out up to AB_SAVE_CONCURRENCY (default 5, hard-clamped
# to [1,5]) autosave eval calls concurrently against the ONE singleton
# agent-browser session.  All browser lifecycle (lock, lease, TTL, breaker,
# teardown) lives in browser_manager.sh; this script SOURCES it and issues every
# eval via the lock-asserting AB() wrapper.
#
# DESIGN (PRIMARY approach per plan):
#   The Cloudflare-cleared session IS the one canonical agent-browser context that
#   bm_ensure opens.  Parallel saves fan out as concurrent "agent-browser eval"
#   invocations against the SAME session — the autosave POST is stateless, keyed
#   by pageId; distinct pages do not collide.  AB_MAX_SESSIONS stays 1 (one
#   browser); the new AB_SAVE_CONCURRENCY knob only caps the number of in-flight
#   eval calls.
#
# SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
# reaper backstop.
#
# USAGE:
#   source "$(dirname "$0")/parallel_saves.sh"
#   bm_save_concurrency          # prints clamped concurrency
#
#   # Or run as a standalone batch executor (reads a JSON spec file):
#   bash parallel_saves.sh run-batch <batch_spec.json>
#
#   # The batch spec is a JSON object:
#   # {
#   #   "session": "ghl-skill6-...",
#   #   "pages": [
#   #     { "page_id": "...", "js": "<the eval JS string for this page>" },
#   #     ...
#   #   ]
#   # }
#   # Output: one JSON line per page with {page_id, exit, output}.
#   # If ANY page exits non-zero the overall batch exits 1.
#
# VERSION (kept in sync by scripts/bump-version.sh):
PARALLEL_SAVES_VERSION="v14.3.7"

# ── Source the browser manager — MANDATORY.  This gives us AB(), bm_ensure,
#    _bm_teardown via the installed EXIT trap, and bm_session_name.
#    ALLOW_RE in guard-agent-browser-managed.sh matches `browser_manager` so this
#    source line satisfies the managed-only check for every eval we issue below. ──
_PS_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
# shellcheck source=./browser_manager.sh
source "${_PS_SELF_DIR}/browser_manager.sh"

# ── AB_SAVE_CONCURRENCY — new tunable, clamped to [1,5] ──────────────────────
# AB_MAX_SESSIONS STAYS 1 (one browser).  This is a SEPARATE cap on in-flight
# eval calls only.  Hard upper bound is 5 — the proven safe concurrency from the
# live five-concurrent-eval test.
_BM_SAVE_CONCURRENCY_DEFAULT=5

bm_save_concurrency() {
  local raw="${AB_SAVE_CONCURRENCY:-${_BM_SAVE_CONCURRENCY_DEFAULT}}"
  local n
  # Strip any non-numeric chars (defensive); default to the built-in if blank.
  n="$(printf '%s' "$raw" | tr -cd '0-9')"
  [ -z "$n" ] && n="$_BM_SAVE_CONCURRENCY_DEFAULT"
  # Clamp to [1,5] — hard upper bound regardless of the env value.
  [ "$n" -lt 1 ] 2>/dev/null && n=1
  [ "$n" -gt 5 ] 2>/dev/null && n=5
  printf '%s' "$n"
}

# ── _ps_run_page_eval — issue ONE page's autosave eval via AB() ───────────────
# Args: session page_id js_string
# Outputs: one JSON line to stdout: {page_id, exit, output}
# Never exits the parent shell — errors are captured and encoded into the JSON.
_ps_run_page_eval() {
  local session="$1" page_id="$2" js="$3"
  local out exitcode
  # AB() is the ONLY way we call agent-browser — satisfies the managed-only guard.
  if out="$(AB --session "$session" eval "$js" 2>&1)"; then
    exitcode=0
  else
    exitcode=$?
  fi
  # Emit a compact JSON line — no jq dependency (use printf).
  local safe_page safe_out safe_session
  safe_page="$(printf '%s' "$page_id" | sed 's/"/\\"/g')"
  safe_session="$(printf '%s' "$session" | sed 's/"/\\"/g')"
  # Truncate output to 4096 chars to keep the log readable; prefix any embedded
  # double-quotes with a backslash (best-effort; full JSON escaping is not
  # required for a log line).
  safe_out="$(printf '%s' "$out" | head -c 4096 | sed 's/"/\\"/g' | tr '\n' ' ')"
  printf '{"page_id":"%s","session":"%s","exit":%s,"output":"%s"}\n' \
    "$safe_page" "$safe_session" "$exitcode" "$safe_out"
}

# ── ps_fan_out — execute N page evals in parallel, capped at AB_SAVE_CONCURRENCY
# Args:
#   $1 session      — the canonical session name
#   $2 tmp_out_dir  — a caller-supplied tmp dir to collect per-page output files
#   $3+ page_specs  — space-separated list of "page_id:js_b64" items where
#                     js_b64 is the eval JS base64-encoded (to avoid IFS issues)
#
# Returns 0 if ALL pages exited 0; 1 if any page failed.
# Each page's JSON line is written to "$tmp_out_dir/$page_id.json".
#
# CONCURRENCY MODEL (macOS bash 3.2 safe, NO GNU parallel):
#   We issue pages as background jobs and track in-flight count via `jobs -p`
#   (returns live PIDs of background jobs).  When the in-flight count hits the
#   cap we wait for any one job to finish before issuing the next.  `wait` at
#   the end collects all remaining jobs.  Per-job exit codes are collected from
#   the output files (each worker writes its JSON, which carries the exit code).
ps_fan_out() {
  local session="$1"; shift
  local tmp_out_dir="$1"; shift
  # Remaining args are page_specs: "page_id:js_b64"
  local cap
  cap="$(bm_save_concurrency)"
  local overall_exit=0
  local page_id js_raw out_file

  for spec in "$@"; do
    # Split on the FIRST colon only.
    page_id="${spec%%:*}"
    local js_b64="${spec#*:}"
    # Decode the base64 JS (macOS + Linux both support `base64 -d` via -D on BSD).
    if js_raw="$(printf '%s' "$js_b64" | base64 -d 2>/dev/null || printf '%s' "$js_b64" | base64 -D 2>/dev/null)"; then
      :
    else
      js_raw=""
    fi
    out_file="${tmp_out_dir}/${page_id}.json"

    # Wait for a slot if at the concurrency cap.
    while :; do
      # Count running background jobs.
      local n_jobs
      n_jobs="$(jobs -p 2>/dev/null | grep -c . || true)"
      if [ "$n_jobs" -lt "$cap" ]; then
        break
      fi
      # No slot — harvest any finished job (portable: `wait -n` is bash 4.3+;
      # use a short sleep + re-check for bash 3.2 safety).
      sleep 0.05
    done

    # Launch this page's eval in the background.
    (
      _ps_run_page_eval "$session" "$page_id" "$js_raw" > "$out_file" 2>&1
    ) &
  done

  # Harvest all remaining background jobs.
  wait

  # Aggregate results from output files; print each line and detect failures.
  for spec in "$@"; do
    page_id="${spec%%:*}"
    out_file="${tmp_out_dir}/${page_id}.json"
    if [ -f "$out_file" ]; then
      cat "$out_file"
      local pg_exit
      pg_exit="$(grep -o '"exit":[0-9]*' "$out_file" 2>/dev/null | grep -o '[0-9]*$' || echo '1')"
      if [ "$pg_exit" != "0" ]; then
        overall_exit=1
      fi
    else
      printf '{"page_id":"%s","exit":1,"output":"no output file (fan-out worker did not write)"}\n' "$page_id"
      overall_exit=1
    fi
  done

  return "$overall_exit"
}

# ── ps_run_batch — standalone batch executor (reads JSON spec file) ───────────
# Called when this script is executed directly: `bash parallel_saves.sh run-batch spec.json`
# Spec format: {"session": "...", "pages": [{"page_id": "...", "js": "..."}, ...]}
# Uses bm_ensure (ONE lock + lease + TTL + teardown trap) then fans out evals.
# The teardown trap from browser_manager.sh's bm_ensure fires on EXIT.
ps_run_batch() {
  local spec_file="$1"
  if [ ! -f "$spec_file" ]; then
    echo "FAIL: batch spec file not found: $spec_file" >&2
    exit 1
  fi

  # Parse the spec with python3 (no jq dependency required).
  local session
  session="$(python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(d['session'])
" "$spec_file" 2>/dev/null)" || {
    echo "FAIL: could not parse session from spec $spec_file" >&2
    exit 1
  }

  # Assert this matches the canonical session name (exit 64 if not, via bm_assert_session).
  bm_assert_session "$session"

  # Acquire the singleton lock + start TTL + install teardown trap.
  bm_ensure || exit $?

  # Build the list of page specs (page_id:js_b64).
  local tmp_out_dir
  tmp_out_dir="$(mktemp -d "${LOCKDIR}/ps-batch-XXXXXX" 2>/dev/null || mktemp -d)"
  # The tmp_out_dir is cleaned up by the EXIT trap (or on normal exit below).

  mapfile -t page_specs < <(python3 -c "
import base64, json, sys
d = json.load(open(sys.argv[1]))
for p in d.get('pages', []):
    pid = p['page_id']
    js_b64 = base64.b64encode(p['js'].encode()).decode()
    print('%s:%s' % (pid, js_b64))
" "$spec_file" 2>/dev/null) || {
    echo "FAIL: could not parse pages from spec $spec_file" >&2
    rm -rf "$tmp_out_dir" 2>/dev/null || true
    exit 1
  }

  if [ "${#page_specs[@]}" -eq 0 ]; then
    echo "WARN: batch spec has no pages; nothing to do." >&2
    rm -rf "$tmp_out_dir" 2>/dev/null || true
    exit 0
  fi

  local cap
  cap="$(bm_save_concurrency)"
  echo "BATCH: session=$session pages=${#page_specs[@]} concurrency_cap=$cap" >&2

  local batch_exit=0
  ps_fan_out "$session" "$tmp_out_dir" "${page_specs[@]}" || batch_exit=$?

  rm -rf "$tmp_out_dir" 2>/dev/null || true

  if [ "$batch_exit" -eq 0 ]; then
    echo "BATCH-DONE: all ${#page_specs[@]} page saves succeeded." >&2
  else
    echo "BATCH-FAIL: one or more page saves failed (see output above)." >&2
  fi
  exit "$batch_exit"
}

# ── Standalone verb dispatch (only when executed, not sourced) ────────────────
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _verb="${1:-}"; shift 2>/dev/null || true
  case "$_verb" in
    save-concurrency)
      bm_save_concurrency; echo
      ;;
    run-batch)
      ps_run_batch "${1:-}"
      ;;
    *)
      echo "usage: parallel_saves.sh {save-concurrency|run-batch <spec.json>}" >&2
      exit 64
      ;;
  esac
fi
