#!/usr/bin/env bash
# run-selector-drift-probe.sh — v1.1.0
#
# RENAMED (U30/B-U16, 2026-07-16): shipped as run-selector-canary.sh through
# U29 (module it wraps renamed ghl_selector_canary.py -> ghl_selector_drift_probe.py
# in the same commit — see that module's docstring for the full rename note).
#
# Daily-maintenance-window (or pre-build-optional) READ-ONLY selector-drift
# probe wrapper (U2 / F3; scheduled daily by U30/B-U16 item 4 — see
# schedule/skill6-selector-drift-probe.cron.json +
# scripts/install-selector-drift-probe-cron.sh).
#
# WHAT THIS RUNS: ghl_selector_drift_probe.py's --canary walk against the four
# object docs (form/survey/funnel/page), using the LIVE seeded browser session
# on the OPERATOR TEST sub-account only. It resolves every locked anchor's
# fallback chain (selectors-live.json) via the STOP-with-snapshot resolver and
# NEVER creates, edits, or deletes a GHL object — this is a pure read-only walk
# of list/create-modal/builder-chrome surfaces that already exist or that a
# live scratch-object capture run (W2) has already produced.
#
# THIS SCRIPT DOES NOT WIRE THE LIVE FINDER ITSELF. Wiring a real finder to
# browser_manager.sh requires an authenticated seeded session (seed-ghl-auth.py
# + inject-ghl-auth.sh) which this script deliberately does not drive — that is
# an operator-run live step (see live_finder_over_browser_manager() in
# ghl_selector_drift_probe.py for the wiring contract a live driver implements).
# What THIS script guarantees, portably on both Mac (bash 3.2, no flock) and
# VPS (bash 4+, flock): the OFFLINE gate — selectors-live.json loads, its schema
# is sane, and the resolver/report machinery is exercised end-to-end — runs
# clean before any live step is attempted, and the cron entry point is stable.
# A regression here is exactly the class of drift the daily probe exists to
# catch on the operator's own box BEFORE it ever reaches a client build — on
# failure this prints a SELECTOR-MISS-prefixed line (cc_board.py's taxonomy;
# see ghl_selector_drift_probe.dedupe_board_notifier for the idempotent,
# repeat-run-safe board-card form of this same signal once a live finder is
# wired) so log-tailing/monitoring can grep it the same way a live STOP would
# be graded. A probe that cannot even run its own offline gate (missing
# python3, missing selectors-live.json) is reported PARKED, not silently green.
#
# USAGE
#   scripts/run-selector-drift-probe.sh                 # offline gate only (default, safe for cron)
#   scripts/run-selector-drift-probe.sh --live           # placeholder for the operator's live wiring
#                                                          (exits 3, printing the manual command —
#                                                           no accidental live browser launch from cron)
#
# CRON (daily maintenance window — installed by
#       scripts/install-selector-drift-probe-cron.sh, NOT by this script):
#   0 5 * * * cd <repo>/06-ghl-install-pages && scripts/run-selector-drift-probe.sh >> \
#       "$HOME/.openclaw/workspace/.park/selector-drift-probe.log" 2>&1 || true
#   (mirrors the existing skill6-github-archive-reconcile-sweep daily-maintenance-
#    window pattern: fail-soft, log-and-continue, a probe outage never blocks
#    anything — it is advisory, not a build gate.)

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_TOOLS_DIR="${_HERE}/../tools"

_MODE="offline"
if [ "${1:-}" = "--live" ]; then
  _MODE="live"
fi

if [ "${_MODE}" = "live" ]; then
  echo "run-selector-drift-probe.sh: --live is an operator-run step, not a cron-safe default." >&2
  echo "Wire a real finder via ghl_selector_drift_probe.live_finder_over_browser_manager()" >&2
  echo "against a seeded session, then call run_canary() directly from Python. Example:" >&2
  echo "  python3 -c 'import ghl_selector_drift_probe as c; ...'  (see module docstring)" >&2
  exit 3
fi

if [ ! -f "${_TOOLS_DIR}/ghl_selector_drift_probe.py" ]; then
  echo "PARKED: run-selector-drift-probe.sh — tools/ghl_selector_drift_probe.py not found at ${_TOOLS_DIR} (repo layout drift, not a selector drift)." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "PARKED: run-selector-drift-probe.sh — python3 not on PATH; cannot run the offline gate." >&2
  exit 2
fi

echo "run-selector-drift-probe.sh: offline gate — selectors-live.json + resolver selftest"
_rc=0
python3 "${_TOOLS_DIR}/ghl_selector_drift_probe.py" --selftest || _rc=$?

if [ "${_rc}" -eq 0 ]; then
  echo "run-selector-drift-probe.sh: OK (offline gate clean). Live daily walk is operator-run."
else
  echo "SELECTOR-MISS: run-selector-drift-probe.sh — offline gate FAILED (selectors-live.json or resolver regressed, rc=${_rc})." >&2
fi

exit "${_rc}"
