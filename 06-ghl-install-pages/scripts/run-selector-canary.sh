#!/usr/bin/env bash
# run-selector-canary.sh — v1.0.0
#
# Weekly (or pre-build-optional) READ-ONLY selector-drift canary wrapper (U2 / F3).
#
# WHAT THIS RUNS: ghl_selector_canary.py's --canary walk against the four object
# docs (form/survey/funnel/page), using the LIVE seeded browser session on the
# OPERATOR TEST sub-account only. It resolves every locked anchor's fallback
# chain (selectors-live.json) via the STOP-with-snapshot resolver and NEVER
# creates, edits, or deletes a GHL object — this is a pure read-only walk of
# list/create-modal/builder-chrome surfaces that already exist or that a live
# scratch-object capture run (W2) has already produced.
#
# THIS SCRIPT DOES NOT WIRE THE LIVE FINDER ITSELF. Wiring a real finder to
# browser_manager.sh requires an authenticated seeded session (seed-ghl-auth.py
# + inject-ghl-auth.sh) which this script deliberately does not drive — that is
# an operator-run live step (see live_finder_over_browser_manager() in
# ghl_selector_canary.py for the wiring contract a live driver implements).
# What THIS script guarantees, portably on both Mac (bash 3.2, no flock) and
# VPS (bash 4+, flock): the OFFLINE gate — selectors-live.json loads, its schema
# is sane, and the resolver/report machinery is exercised end-to-end — runs
# clean before any live step is attempted, and the cron entry point is stable.
#
# USAGE
#   scripts/run-selector-canary.sh                 # offline gate only (default, safe for cron)
#   scripts/run-selector-canary.sh --live           # placeholder for the operator's live wiring
#                                                     (exits 3, printing the manual command —
#                                                      no accidental live browser launch from cron)
#
# CRON (weekly, operator-installed, NOT installed by this script):
#   0 6 * * 1 cd <repo>/06-ghl-install-pages && scripts/run-selector-canary.sh >> \
#       "$HOME/.openclaw/workspace/.park/selector-canary.log" 2>&1 || true
#   (mirrors the existing hourly-reaper cron pattern: fail-soft, log-and-continue,
#    a canary outage never blocks anything — it is advisory, not a build gate.)

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_TOOLS_DIR="${_HERE}/../tools"

_MODE="offline"
if [ "${1:-}" = "--live" ]; then
  _MODE="live"
fi

if [ "${_MODE}" = "live" ]; then
  echo "run-selector-canary.sh: --live is an operator-run step, not a cron-safe default." >&2
  echo "Wire a real finder via ghl_selector_canary.live_finder_over_browser_manager()" >&2
  echo "against a seeded session, then call run_canary() directly from Python. Example:" >&2
  echo "  python3 -c 'import ghl_selector_canary as c; ...'  (see module docstring)" >&2
  exit 3
fi

echo "run-selector-canary.sh: offline gate — selectors-live.json + resolver selftest"
python3 "${_TOOLS_DIR}/ghl_selector_canary.py" --selftest
_rc=$?

if [ "${_rc}" -eq 0 ]; then
  echo "run-selector-canary.sh: OK (offline gate clean). Live weekly walk is operator-run."
else
  echo "run-selector-canary.sh: FAILED offline gate — selectors-live.json or resolver regressed." >&2
fi

exit "${_rc}"
