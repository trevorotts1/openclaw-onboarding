#!/usr/bin/env bash
# prove-web-parity.sh — WEB↔TELEGRAM build-parity gate (WG-6 onboarding half).
#
# WHY THIS EXISTS: a client onboarded through the WEB /interview path runs the
# SAME canonical build scripts as a TELEGRAM-built one, so it MUST clear the same
# Zero-Human-Experience gates AND land an EQUAL provisioning receipt / expected
# set — with NO genuine-build shortcuts (fabricated transcript, missing decision,
# unprovenanced decline). This wrapper is the clean, self-contained invocation
# the CI wiring step calls: it runs prove-zhe.py --web-parity-selftest, which
# proves the parity mode PASSES on a good web-built fixture AND FAILS on every
# seeded shortcut (non-vacuous).
#
# It is fully offline and self-contained: it materializes the shipped fixture
# into a PRIVATE sandbox temp dir and sandboxes HOME so nothing under
# ~/.openclaw or ~/.clawdbot is ever read for output or written.
#
# USAGE
#   prove-web-parity.sh                 # non-vacuous self-test (good PASS + shortcuts FAIL)
#   prove-web-parity.sh --once          # prove ONLY the good fixture (exit 0/1)
#   prove-web-parity.sh --web-root W --ref-root R   # prove two REAL OpenClaw roots
#
# EXIT CODES
#   0  parity proven (all expectations hold)
#   1  parity broken (a gate failed / a shortcut did not fail as it must)
#   2  bad invocation
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROVER="$SCRIPT_DIR/prove-zhe.py"

if [ ! -f "$PROVER" ]; then
  echo "prove-web-parity: FATAL prove-zhe.py not found at $PROVER" >&2
  exit 2
fi

# ── HOME sandbox: the parity fixture + parity receipt must never resolve to the
#    operator's real home. Point HOME at a fresh temp dir for the run. This is a
#    defense-in-depth belt: prove-zhe --web-parity already writes only into its
#    own tempdir, but a sandboxed HOME guarantees no stray ~/.openclaw touch.
SANDBOX_HOME="$(mktemp -d "${TMPDIR:-/tmp}/zhe-web-parity-home.XXXXXX")"
cleanup() { rm -rf "$SANDBOX_HOME"; }
trap cleanup EXIT
export HOME="$SANDBOX_HOME"

# prove-zhe.py resolves platform paths at import (via detect_platform) and hard-
# exits when no ~/.openclaw exists — which is always true under the sandboxed
# HOME here. This is the documented static-check override: the parity fixture is
# purely local, so no live box paths are needed.
export OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}"

case "${1:-}" in
  ""|--selftest)
    exec python3 "$PROVER" --web-parity-selftest
    ;;
  --once)
    exec python3 "$PROVER" --web-parity
    ;;
  --web-root|--ref-root)
    # Pass through explicit real-root parity args unchanged.
    exec python3 "$PROVER" --web-parity "$@"
    ;;
  -h|--help)
    sed -n '2,29p' "$0"; exit 0
    ;;
  *)
    echo "prove-web-parity: unknown argument: $1" >&2
    exit 2
    ;;
esac
