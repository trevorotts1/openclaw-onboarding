#!/usr/bin/env bash
# vps-mount-proof.sh — v1.0.0 — B-U15 item 1 live-wrapper.
#
# Orchestrates the ENV-MATRIX.md `[ASSUMED, spec-carried]` session-persistence
# row proof: does `~/.agent-browser` (or an equivalent target dir) survive a
# REAL `docker compose up -d --force-recreate` on a REAL VPS?
#
# WHAT THIS SCRIPT DOES NOT DO: it never fabricates a PASS. The offline mode
# (default, cron/CI-safe) only exercises the classify/marker/receipt MECHANISM
# via `ghl_vps_mount_proof.py --selftest` (hermetic, no Docker). The `--live`
# mode requires a REAL `docker` binary AND an actual compose project on THIS
# box — when either is missing it REFUSES with a clear message (exit 3),
# mirroring `run-selector-canary.sh`'s "operator-run live step, not a cron
# default" pattern. This is the correct, honest shape for an operator-gated
# live leg: the mechanism ships now, the live round trip runs when an operator
# is actually on a real VPS.
#
# USAGE
#   scripts/vps-mount-proof.sh                     # offline gate only (default, safe for cron/CI)
#   scripts/vps-mount-proof.sh --live \
#       --path <dir> --run-id <id> --compose-file <file> \
#       [--evidence-root <dir>] [--box-label <name>]
#     Runs the real round trip: write the marker -> `docker compose -f
#     <file> up -d --force-recreate` -> verify the marker survived -> write
#     the receipt to <evidence-root>/routing/vps-mount-receipt.json.
#
# CRON: NOT installed by this script (the live leg is a one-time-per-box
# confirmation per ENV-MATRIX.md §9.4 step 10, not a recurring job).

set -euo pipefail

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_TOOLS_DIR="${_HERE}/../tools"
_PROOF_PY="${_TOOLS_DIR}/ghl_vps_mount_proof.py"

_MODE="offline"
if [ "${1:-}" = "--live" ]; then
  _MODE="live"
  shift
fi

if [ "${_MODE}" = "offline" ]; then
  echo "vps-mount-proof.sh: offline gate — classify/marker/receipt mechanism selftest"
  python3 "${_PROOF_PY}" --selftest
  _rc=$?
  if [ "${_rc}" -eq 0 ]; then
    echo "vps-mount-proof.sh: OK (offline gate clean). The live VPS round trip is operator-run:"
    echo "  scripts/vps-mount-proof.sh --live --path <dir> --run-id <id> --compose-file <file>"
  else
    echo "vps-mount-proof.sh: FAILED offline gate — ghl_vps_mount_proof.py regressed." >&2
  fi
  exit "${_rc}"
fi

# ── --live mode ────────────────────────────────────────────────────────────
_PATH_ARG=""
_RUN_ID=""
_COMPOSE_FILE=""
_EVIDENCE_ROOT=""
_BOX_LABEL=""

while [ $# -gt 0 ]; do
  case "$1" in
    --path) _PATH_ARG="$2"; shift 2 ;;
    --run-id) _RUN_ID="$2"; shift 2 ;;
    --compose-file) _COMPOSE_FILE="$2"; shift 2 ;;
    --evidence-root) _EVIDENCE_ROOT="$2"; shift 2 ;;
    --box-label) _BOX_LABEL="$2"; shift 2 ;;
    *) echo "vps-mount-proof.sh --live: unknown arg '$1'" >&2; exit 64 ;;
  esac
done

if [ -z "${_PATH_ARG}" ] || [ -z "${_RUN_ID}" ] || [ -z "${_COMPOSE_FILE}" ]; then
  echo "vps-mount-proof.sh --live: --path, --run-id, and --compose-file are all required." >&2
  exit 64
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "vps-mount-proof.sh --live: REFUSE — no 'docker' binary on this box's PATH." >&2
  echo "This is the operator-run live leg (B-U15 item 1) — run it on a real VPS with Docker." >&2
  exit 3
fi

if [ ! -f "${_COMPOSE_FILE}" ]; then
  echo "vps-mount-proof.sh --live: REFUSE — compose file '${_COMPOSE_FILE}' not found." >&2
  exit 3
fi

_PRE_ARGS=("${_PATH_ARG}" "--run-id" "${_RUN_ID}")
_POST_ARGS=("${_PATH_ARG}" "--run-id" "${_RUN_ID}")
if [ -n "${_EVIDENCE_ROOT}" ]; then
  _PRE_ARGS+=("--evidence-root" "${_EVIDENCE_ROOT}")
  _POST_ARGS+=("--evidence-root" "${_EVIDENCE_ROOT}")
fi
if [ -n "${_BOX_LABEL}" ]; then
  _PRE_ARGS+=("--box-label" "${_BOX_LABEL}")
  _POST_ARGS+=("--box-label" "${_BOX_LABEL}")
fi

echo "vps-mount-proof.sh --live: PRE — writing marker at ${_PATH_ARG}"
python3 "${_PROOF_PY}" pre "${_PRE_ARGS[@]}"

echo "vps-mount-proof.sh --live: force-recreating via 'docker compose -f ${_COMPOSE_FILE} up -d --force-recreate'"
docker compose -f "${_COMPOSE_FILE}" up -d --force-recreate

echo "vps-mount-proof.sh --live: POST — verifying marker survival at ${_PATH_ARG}"
python3 "${_PROOF_PY}" post "${_POST_ARGS[@]}"
_rc=$?

if [ "${_rc}" -eq 0 ]; then
  echo "vps-mount-proof.sh --live: PASS — ${_PATH_ARG} survived the force-recreate."
else
  echo "vps-mount-proof.sh --live: FAIL — ${_PATH_ARG} did NOT survive the force-recreate (see receipt)." >&2
fi
exit "${_rc}"
