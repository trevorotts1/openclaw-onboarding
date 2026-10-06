#!/usr/bin/env bash
# seed-rr-agent-map.sh — DEPRECATED alias for reconcile-rr-agent-map.sh (RR-031).
#
# This script WAS the insert-only seeder for rr_agent_map, and it carried the
# confirmed RCV-09 defect class:
#   * it read ONE page of the table and filled only ABSENT slugs, so an
#     existing WRONG mapping (box -> not-the-default-agent) survived every run;
#   * it resolved each box's default agent on the OPERATOR HOST over SSH, so a
#     Docker-installed box — where the host has no openclaw at all — could
#     never resolve its own container and was silently skipped;
#   * it used shared fixed paths (/tmp/rr-seed-missing.txt, /tmp/rr-seed-payload.json,
#     /tmp/rr-seed-resolved.txt, /tmp/rr-seed-after.json), so two concurrent
#     operators overwrote each other's work;
#   * its HTTP and SSH calls had no overall deadline;
#   * it hardcoded the operator host and the table id.
# The wrapper that called it then read exit-0-with-skips as "ok".
#
# RR-031 supersedes it with scripts/reconcile-rr-agent-map.sh, which repairs
# existing wrong mappings as well as filling missing ones, resolves agents
# inside the exact container via the reused fleet-prover box descriptor,
# aborts writes when the source read is incomplete, uses per-run private temp
# paths under a scoped lock with finite deadlines, records unresolved boxes as
# pending with an owner, never invents `main`, and reports actual
# changed/verified/pending counts.
#
# This file remains ONLY so a stale caller cannot silently keep the old
# behaviour: it prints a deprecation notice and DELEGATES. It is not a second
# implementation and holds no logic of its own.
#
#   seed-rr-agent-map.sh [ROSTER_FILE] [--dry-run]   -> delegated plan
#   seed-rr-agent-map.sh --apply ...                 -> delegated write
#
# RR-027 credential hygiene is unchanged and still enforced by the delegate:
# the n8n key rides in a 0600 header file inside a 0700 private directory
# (curl -H @file), never in an argument list.

set -euo pipefail

_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_RECON="$_SELF_DIR/reconcile-rr-agent-map.sh"
if [ ! -f "$_RECON" ]; then
  echo "seed-rr-agent-map: DEPRECATED and its successor is missing ($_RECON) — refusing to run the retired seeder." >&2
  exit 2
fi

echo "seed-rr-agent-map: DEPRECATED — delegating to reconcile-rr-agent-map.sh (RR-031 supersedes the insert-only seed)." >&2

_args=()
_shim_tmp=""
_cleanup_shim() { [ -n "$_shim_tmp" ] && rm -rf "$_shim_tmp" 2>/dev/null; }
trap _cleanup_shim EXIT INT TERM
_expect_val=0
for _a in "$@"; do
  if [ "$_expect_val" -eq 1 ]; then _args+=("$_a"); _expect_val=0; continue; fi
  case "$_a" in
    --dry-run) _args+=(--dry-run) ;;
    --apply)   _args+=(--apply) ;;
    --verify|--check) _args+=("$_a") ;;
    --roster|--boxes|--table|--host|--contract-manifest|--lock-dir|--state-dir|--pending-owner|\
    --max-pages|--ssh-timeout|--proc-timeout|--stale-lock-seconds)
      _args+=("$_a"); _expect_val=1 ;;
    -*)        _args+=("$_a") ;;
    *)
      # The retired seeder took a SLUG LIST (one slug per line). The reconciler
      # takes the fleet ROSTER. Convert rather than silently reinterpret: the
      # slug set is carried over verbatim and the file is private and per-run.
      if [ -z "$_shim_tmp" ]; then
        _shim_tmp="$( (umask 077; mktemp -d "${TMPDIR:-/tmp}/rr-seed-shim.XXXXXX") )" || {
          echo "seed-rr-agent-map: cannot create a private temp dir for the slug list" >&2; exit 2; }
        chmod 700 "$_shim_tmp"
      fi
      _roster_json="$_shim_tmp/roster.json"
      python3 - "$_a" "$_roster_json" <<'PYEOF_SHIM'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
slugs = []
with open(src) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#"):
            slugs.append(line)
json.dump({"_doc": "converted from a slug list by the deprecated seeder shim",
           "boxes": {s: {} for s in slugs}}, open(dst, "w"), indent=1)
PYEOF_SHIM
      _args+=(--roster "$_roster_json")
      ;;
  esac
done

# No mode given: this used to WRITE by default. It now only PLANS, and says so,
# because an implicit write path is exactly what RR-031 removed.
_have_mode=0
for _a in "${_args[@]:-}"; do
  case "$_a" in --apply|--verify|--dry-run|--check) _have_mode=1 ;; esac
done
if [ "$_have_mode" -eq 0 ]; then
  echo "seed-rr-agent-map: no --apply given — running PLAN ONLY (the implicit write default is retired)." >&2
  _args+=(--dry-run)
fi

# The successor is a bash script (process substitution, arrays). RR-027's gate
# exercises THIS file under /bin/sh too, so exec it with bash explicitly rather
# than relying on the successor's shebang surviving an `sh script` invocation —
# the exec must not depend on how the caller invoked the shim.
exec bash "$_RECON" "${_args[@]}"
