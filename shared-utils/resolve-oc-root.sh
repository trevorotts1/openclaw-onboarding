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
#
# Precedence, highest first:
#   1. $OPENCLAW_ROOT / $OC_ROOT when set to an existing directory (explicit
#      operator pin always wins — e.g. OPENCLAW_CONTAINER_NAME flows that
#      select one client container among several on a shared Contabo host).
#   2. /data/.openclaw when it is a directory (VPS/Docker first).
#   3. $HOME/.openclaw when it is a directory (Mac fallback).
# A /data path that canonicalizes to the same directory as $HOME/.openclaw
# (container image symlinking /data into the node user's home) is ONE
# installation, not two — prefer the $HOME spelling, matching
# platform/common.sh's canonical-path rule. Never prints secrets.
resolve_oc_root() {
  local _rr
  for _rr in "${OPENCLAW_ROOT:-}" "${OC_ROOT:-}"; do
    if [ -n "$_rr" ] && [ -d "$_rr" ]; then
      printf '%s\n' "$_rr"
      return 0
    fi
  done
  if [ -d /data/.openclaw ]; then
    if [ -d "$HOME/.openclaw" ]; then
      if command -v python3 >/dev/null 2>&1; then
        _rr="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' /data/.openclaw 2>/dev/null)" || _rr=""
        _hh="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$HOME/.openclaw" 2>/dev/null)" || _hh=""
        if [ -n "$_rr" ] && [ "$_rr" = "$_hh" ]; then
          printf '%s\n' "$HOME/.openclaw"
          return 0
        fi
      elif [ /data/.openclaw -ef "$HOME/.openclaw" ]; then
        printf '%s\n' "$HOME/.openclaw"
        return 0
      fi
    fi
    printf '%s\n' /data/.openclaw
    return 0
  fi
  if [ -d "$HOME/.openclaw" ]; then
    printf '%s\n' "$HOME/.openclaw"
    return 0
  fi
  return 1
}

# resolve_build_state_workspace — echo the workspace dir that ACTUALLY holds
# .workforce-build-state.json, or return 1 having searched everywhere.
#
# WHY: platform/common.sh sets OPENCLAW_WORKSPACE_PATH from openclaw.json's
# agents.defaults.workspace. On the operator's own box that points at a legacy
# directory, while the real state file lives at
# ~/.openclaw/workspace/.workforce-build-state.json.
# run-full-install.sh built STATE_FILE from that configured path, found no
# file, and the launch inspector returned requiresInitialization:true with
# companySlug:null — so `--update-only` exited 8 demanding an interactive
# interview on a fully built box. A configured path is a hint, not evidence:
# pick the first candidate that actually has the file.
#
# Sets OC_BUILD_STATE_SEARCHED to every path tried, so a caller that finds
# nothing can NAME what it checked instead of asserting a bare absence.
resolve_build_state_workspace() {
  local f=".workforce-build-state.json" c
  OC_BUILD_STATE_SEARCHED=""
  for c in "${OPENCLAW_WORKSPACE_PATH:-}" "${OC_ROOT:-}/workspace" \
           "$HOME/.openclaw/workspace" "/data/.openclaw/workspace"; do
    [ -n "$c" ] && [ "$c" != "/workspace" ] || continue
    case " $OC_BUILD_STATE_SEARCHED " in *" $c "*) continue ;; esac
    OC_BUILD_STATE_SEARCHED="${OC_BUILD_STATE_SEARCHED:+$OC_BUILD_STATE_SEARCHED }$c"
    if [ -f "$c/$f" ]; then
      printf '%s' "$c"
      return 0
    fi
  done
  return 1
}
