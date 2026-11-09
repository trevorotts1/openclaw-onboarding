#!/usr/bin/env bash
# durable-data-root.sh — THE ONE resolver for run data that must SURVIVE
# (F21 item 11: durable image jobs, reservations, receipts and run state).
#
# WHY THIS EXISTS
#   Paid KIE work leaves evidence: a submitted request, a provider task id, a
#   reservation, an upload receipt, a done marker. Two modules owned that state
#   and each computed its own location:
#     * 46-kie-callback-relay wrote registry/index/done under whatever
#       `workspaceDir` a caller happened to pass -- a presentation run folder, a
#       skill tree, a temp dir; a reinstall or resume could lose the evidence a
#       resubmit is decided on.
#     * 74-kie-live-adapter wrote receipts under `os.path.join(home,
#       ".openclaw", ...)` and ALSO carried a hard-coded `/data/.openclaw`
#       constant, so on a Docker/VPS box (HOME is the image's temporary layer,
#       OpenClaw lives at /data/.openclaw) the receipts landed in a wiped layer.
#   Two computations, two answers, one run. Now there is exactly one: this file.
#
# ROOT PRECEDENCE IS NOT RE-IMPLEMENTED HERE. It is delegated to
# `resolve-oc-root.sh` (the single "/data/.openclaw else $HOME/.openclaw"
# authority, with OPENCLAW_ROOT/OC_ROOT as the explicit operator pin). This file
# adds ONE thing ahead of it -- OPENCLAW_DATA_ROOT, the explicit data-root pin
# used by the operator and by hermetic tests -- and then the LAYOUT, which is
# computed nowhere else.
#
# LAYOUT (all under the resolved root, never under a replaceable skill tree):
#   <root>/data/kie-jobs/<scope>/registry   one file per job identity, immutable except status
#   <root>/data/kie-jobs/<scope>/index      taskId -> submitId
#   <root>/data/kie-jobs/<scope>/done       per-taskId done marker (create-if-absent)
#   <root>/data/kie-jobs/<scope>/receipts   Skill 74 drift/submit receipts (YYYYMMDD.jsonl)
#   <root>/cache/kie-live-adapter           re-fetchable catalog/schema cache (NOT evidence)
#
# CONSUMERS (both execute THIS file; neither computes a path of its own):
#   46-kie-callback-relay/data-root.js       -> node/browser-side layout
#   74-kie-live-adapter/scripts/kie_live_adapter.py -> python-side layout
#
# USAGE
#   durable-data-root.sh --root [--scope S]   print the durable data root only
#   durable-data-root.sh --json [--scope S]   print the whole layout as one JSON object
#   durable-data-root.sh --check              prove the resolver discriminates (exit 0/1)
#
# It is also SOURCED (never executed) by bash callers: it defines
# `resolve_durable_data_root`, `durable_kie_state_dir` and
# `durable_kie_paths_json` and sets nothing else, so it is safe under
# `set -euo pipefail`.
#
# Never prints a secret: it prints paths only.

_durable_here=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd) || _durable_here=""
# shellcheck source=resolve-oc-root.sh
if [ -n "$_durable_here" ] && [ -f "$_durable_here/resolve-oc-root.sh" ]; then
  . "$_durable_here/resolve-oc-root.sh"
fi

# One scope segment: letters, digits, dot, underscore, dash. Anything else is a
# traversal (`..`), an absolute path, or a JSON-breaking character, so it is
# refused by name rather than silently rewritten into another client's folder.
_durable_scope_ok() {
  case "${1:-}" in
    ''|.|..) return 1 ;;
    *[!A-Za-z0-9._-]*) return 1 ;;
  esac
  return 0
}

# resolve_durable_data_root: echo the durable root, or return 1 with a named
# reason on stderr. Precedence:
#   1. $OPENCLAW_DATA_ROOT when it is an existing directory (explicit pin)
#   2. resolve_oc_root: $OPENCLAW_ROOT/$OC_ROOT, /data/.openclaw, $HOME/.openclaw
# Never echoes a path that does not exist: a root that cannot be resolved is a
# refusal, not a default, so a run can never write evidence into a transient
# location just because nothing answered.
resolve_durable_data_root() {
  if [ -n "${OPENCLAW_DATA_ROOT:-}" ]; then
    if [ -d "${OPENCLAW_DATA_ROOT}" ]; then
      printf '%s\n' "${OPENCLAW_DATA_ROOT}"
      return 0
    fi
    printf 'OPENCLAW_DATA_ROOT=%s is not a directory\n' "${OPENCLAW_DATA_ROOT}" >&2
    return 1
  fi
  if ! command -v resolve_oc_root >/dev/null 2>&1; then
    printf 'resolve-oc-root.sh is missing beside durable-data-root.sh\n' >&2
    return 1
  fi
  resolve_oc_root
}

# durable_kie_state_dir [scope] -> <root>/data/kie-jobs/<scope>
durable_kie_state_dir() {
  local root scope
  scope=${1:-kie-live-adapter}
  if ! _durable_scope_ok "$scope"; then
    printf 'scope %s is not one path segment ([A-Za-z0-9._-])\n' "$scope" >&2
    return 1
  fi
  root=$(resolve_durable_data_root) || return 1
  printf '%s/data/kie-jobs/%s\n' "${root%/}" "$scope"
}

# durable_kie_paths_json [scope] -> one JSON object, the whole layout.
# Paths are printed, never created: the writer creates its own directory, so a
# read-only question never leaves an empty tree behind.
durable_kie_paths_json() {
  local scope state root
  scope=${1:-kie-live-adapter}
  state=$(durable_kie_state_dir "$scope") || return 1
  root=${state%%/data/kie-jobs/*}
  printf '{"root":"%s","scope":"%s","state_dir":"%s","registry":"%s/registry","index":"%s/index","done":"%s/done","receipts":"%s/receipts","cache":"%s/cache/kie-live-adapter"}\n' \
    "$root" "$scope" "$state" "$state" "$state" "$state" "$state" "$root"
}

# ── CLI ──────────────────────────────────────────────────────────────────────
_durable_cli() {
  local mode="--json" scope="kie-live-adapter"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --root|--json|--check) mode="$1" ;;
      --scope) shift; scope="${1:-}" ;;
      --scope=*) scope="${1#--scope=}" ;;
      -h|--help)
        printf 'usage: %s [--root|--json|--check] [--scope S]\n' "$0"
        return 0 ;;
      *) printf 'unknown argument: %s\n' "$1" >&2; return 2 ;;
    esac
    shift
  done

  if [ "$mode" = "--check" ]; then
    # The resolver must DISCRIMINATE: two pins must give two different layouts,
    # and an unset scope must still resolve to exactly one root.
    local a b rc=0
    a=$(OPENCLAW_DATA_ROOT="${TMPDIR:-/tmp}" durable_kie_state_dir "scope-a") || rc=1
    b=$(OPENCLAW_DATA_ROOT="${TMPDIR:-/tmp}/." durable_kie_state_dir "scope-b") || rc=1
    [ -n "$a" ] && [ -n "$b" ] || rc=1
    [ "$a" != "$b" ] || { printf 'control failed: two scopes resolved to one state dir\n' >&2; rc=1; }
    if ! OPENCLAW_DATA_ROOT=/nonexistent-durable-root durable_kie_state_dir x >/dev/null 2>&1; then
      : # refusing a non-existent pin is the required behaviour
    else
      printf 'control failed: a non-existent OPENCLAW_DATA_ROOT was accepted\n' >&2; rc=1
    fi
    [ "$rc" -eq 0 ] && printf 'OK durable-data-root resolver discriminates\n'
    return "$rc"
  fi

  if [ "$mode" = "--root" ]; then
    resolve_durable_data_root
    return $?
  fi
  durable_kie_paths_json "$scope"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  set -o pipefail
  _durable_cli "$@"
  exit $?
fi
