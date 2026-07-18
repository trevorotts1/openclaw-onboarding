#!/usr/bin/env bash
# unit-status.sh -- answers "is this unit REALLY done?" See TOOLS.md's
# "Git-truth tools" section and QC-PROTOCOL.md's binding citation rule.
#
# Resolves the unit's required repo legs from its ledger row's OWN leg tag
# (never a branch name -- literal "(both, ...)" / "(ONB, ...)" / "(CC, ...)"
# / compound "(CC (+ONB), ...)" forms), then for each required leg checks
# live git truth: an own-named branch, OR (if none exists) an independently
# re-verified cross-reference citation from the ledger's own prose, OR a
# non-namespaced branch carrying the unit id as a token. CI is checked via
# the PAGINATED check-runs API, never the legacy combined-status endpoint.
# Prints DONE / NOT-DONE / UNKNOWN plus the full evidence trail. Never
# guesses: absence of a same-named branch is NOT treated as proof of
# non-completion (see the U108/U79 cases this tool's test suite proves).
#
# Usage:
#   ./unit-status.sh <unit-id> [options]     single unit
#   ./unit-status.sh --all [options]         every unit with a row in the
#                                            searched ledgers, one summary line
#   ./unit-status.sh --units U1,U2 [options] aggregate over an explicit list
#
# Options:
#   --onb-dir DIR   local clone of openclaw-onboarding (default: this repo)
#   --cc-dir DIR    local clone of blackceo-command-center (default: an
#                   auto-managed, auto-fetched cache under
#                   $UNIT_STATUS_CACHE_DIR, default ~/.cache/openclaw-git-truth-tools)
#   --ledger PATH   ledger file to search (repeatable; default: all
#                   ledgers/*.md in the ONB repo, skill6 kanban ledger first)
#   --skip-ci       skip the paginated check-runs lookup (faster, for
#                   iteration/testing; the verdict then reflects merge/
#                   ancestry evidence only, never CI)
#   --json          machine-readable output
#
# Machine-readable live-leg state (single-unit JSON and per-unit aggregate
# JSON): owed_non_repo_components lists any non-repo legs a compound tag
# owes ("ONB + live" -> ["live"]); live_leg_owed is true only when the repo
# legs are DONE but a live/non-repo leg is still owed; completion_state is
# "fully-done" vs "repo-legs-done-live-leg-owed". A DONE verdict with
# live_leg_owed=true is NOT the same as fully DONE -- callers (e.g. the
# ledger-truth gate) can branch on it programmatically.
#
# Aggregate output: one compact line per unit, then ONE summary line --
#   UNITS CHECKED: N -- DONE: n, DONE-LIVE-OWED: n, NOT-DONE: n, UNKNOWN: n
#
# Exit codes: 0 = DONE, 1 = NOT-DONE, 3 = UNKNOWN (never guessed). Aggregate
# mode: 1 if any unit is NOT-DONE, else 3 if any is UNKNOWN, else 0.
#
# Examples proven by this tool's own test suite (the acceptance bar, not
# unit tests -- see tests/unit/unit-status-historical.test.py):
#   ./unit-status.sh U108   -> DONE (CC leg shipped inside U110's branch)
#   ./unit-status.sh U79    -> DONE (compound tag, non-namespaced CC branch)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_PY="$SCRIPT_DIR/shared-utils/unit_status_core.py"

if [ ! -f "$CORE_PY" ]; then
  echo "ERROR: $CORE_PY not found -- unit-status.sh must live at the repo root next to shared-utils/." >&2
  exit 2
fi

usage() {
  sed -n '2,46p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

[ $# -ge 1 ] || usage
MODE=single
UNIT_ID=""
UNITS_ARG=""
case "$1" in
  --all)
    MODE=all; shift ;;
  --units)
    [ $# -ge 2 ] || { echo "ERROR: --units needs a comma-separated list (e.g. --units U108,U79)" >&2; exit 2; }
    MODE=units; UNITS_ARG="$2"; shift 2 ;;
  -h|--help) usage ;;
  *)
    UNIT_ID="$1"; shift
    if ! [[ "$UNIT_ID" =~ ^U[0-9]+$ ]]; then
      echo "ERROR: unit id must look like U<digits> (e.g. U108), or use --all / --units U1,U2 -- got '$UNIT_ID'" >&2
      exit 2
    fi ;;
esac

ONB_DIR="$SCRIPT_DIR"
CC_DIR=""
LEDGER_ARGS=()
SKIP_CI=0
JSON_OUT=0
CACHE_DIR="${UNIT_STATUS_CACHE_DIR:-$HOME/.cache/openclaw-git-truth-tools}"

while [ $# -gt 0 ]; do
  case "$1" in
    --onb-dir) ONB_DIR="$2"; shift 2 ;;
    --cc-dir) CC_DIR="$2"; shift 2 ;;
    --ledger) LEDGER_ARGS+=(--ledger "$2"); shift 2 ;;
    --skip-ci) SKIP_CI=1; shift ;;
    --json) JSON_OUT=1; shift ;;
    -h|--help) usage ;;
    *) echo "ERROR: unknown arg '$1'" >&2; usage ;;
  esac
done

if [ ${#LEDGER_ARGS[@]} -eq 0 ]; then
  PRIMARY="$ONB_DIR/ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md"
  [ -f "$PRIMARY" ] && LEDGER_ARGS+=(--ledger "$PRIMARY")
  if [ -d "$ONB_DIR/ledgers" ]; then
    while IFS= read -r -d '' f; do
      [ "$f" = "$PRIMARY" ] && continue
      LEDGER_ARGS+=(--ledger "$f")
    done < <(find "$ONB_DIR/ledgers" -maxdepth 1 -type f -name '*.md' -print0 | sort -z)
  fi
fi
if [ ${#LEDGER_ARGS[@]} -eq 0 ]; then
  echo "ERROR: no ledger files found under $ONB_DIR/ledgers -- pass --ledger explicitly." >&2
  exit 2
fi

if [ -z "$CC_DIR" ]; then
  CC_DIR="$CACHE_DIR/blackceo-command-center"
  mkdir -p "$CACHE_DIR"
  if [ -d "$CC_DIR/.git" ]; then
    echo "[unit-status] refreshing cached blackceo-command-center clone at $CC_DIR ..." >&2
    git -C "$CC_DIR" fetch -q origin main || echo "[unit-status] WARNING: fetch failed, using stale cache" >&2
  else
    echo "[unit-status] cloning blackceo-command-center into $CC_DIR (one-time) ..." >&2
    git clone -q https://github.com/trevorotts1/blackceo-command-center.git "$CC_DIR"
  fi
fi

git -C "$ONB_DIR" fetch -q origin main 2>/dev/null || echo "[unit-status] WARNING: could not refresh $ONB_DIR origin/main" >&2

CLI_ARGS=(python3 "$CORE_PY")
case "$MODE" in
  single) CLI_ARGS+=("$UNIT_ID") ;;
  all)    CLI_ARGS+=(--all) ;;
  units)  CLI_ARGS+=(--units "$UNITS_ARG") ;;
esac
CLI_ARGS+=(--onb-dir "$ONB_DIR" --cc-dir "$CC_DIR" "${LEDGER_ARGS[@]}")
[ "$SKIP_CI" = "1" ] && CLI_ARGS+=(--skip-ci)
[ "$JSON_OUT" = "1" ] && CLI_ARGS+=(--json)

exec "${CLI_ARGS[@]}"
