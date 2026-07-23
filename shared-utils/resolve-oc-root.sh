#!/usr/bin/env bash
# Shared OpenClaw-root resolver — the SINGLE source of truth for the
# "/data/.openclaw (VPS) else $HOME/.openclaw (Mac)" root detection that the
# ZHC/closeout/dept scripts previously each re-implemented inline.
#
# WHY THIS EXISTS (false-negative #3 / wrong-tree root cause): when eight
# sibling scripts each hand-roll the same detection, a future edit to one (or a
# stale/duplicate .openclaw layout on a box) can silently make two scripts
# resolve DIFFERENT roots and therefore read DIFFERENT .workforce-build-state.json
# copies — one certifying a tree the other never touched. Centralizing the
# decision here makes divergence impossible: every caller computes the SAME
# OC_ROOT because there is now exactly one implementation.
#
# BEHAVIOR CONTRACT — this MUST compute exactly what every caller computed
# before (verified byte-for-byte against the pre-refactor inline blocks):
#   * /data/.openclaw wins when it is a directory (VPS first);
#   * else $HOME/.openclaw when it is a directory (Mac fallback);
#   * else NOT FOUND — returns 1 and prints nothing (each caller keeps its OWN
#     "no root" message + exit code, which differ across scripts).
#
# It deliberately does NOT consult a pre-existing $OC_ROOT: only one caller
# (closeout-readiness-watchdog.sh) honors an OC_ROOT override, and it keeps its
# own `[[ -z "${OC_ROOT:-}" ]]` wrapper around this call — so override semantics
# and non-detection behavior stay per-caller and unchanged.
#
# This file is SOURCED, never executed. It defines `resolve_oc_root` and sets
# nothing else, so it is safe to source under `set -euo pipefail`.

# resolve_oc_root: echo the resolved OpenClaw root and return 0, or return 1
# (and echo nothing) when no root exists. Never exits — the caller decides.
resolve_oc_root() {
  if [ -d /data/.openclaw ]; then
    printf '%s\n' /data/.openclaw
    return 0
  fi
  if [ -d "$HOME/.openclaw" ]; then
    printf '%s\n' "$HOME/.openclaw"
    return 0
  fi
  return 1
}
