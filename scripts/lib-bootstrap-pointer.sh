#!/usr/bin/env bash
# lib-bootstrap-pointer.sh — shared helpers for POINTER stamping of managed
# bootstrap blocks. Source it; it defines functions and sets no traps.
#
# WHY
#   Bootstrap files (AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md / IDENTITY.md /
#   USER.md) are re-billed to the model on EVERY turn. Long managed text stamped
#   there is paid for forever. This library lets every stamper in the repo write
#   a compact POINTER into the bootstrap file and the VERBATIM full text into a
#   reference file under the box's master-files root.
#
#   Hand-moving a block out of AGENTS.md does not hold — the next roll's
#   idempotency guard sees the marker gone and re-appends the full text. The fix
#   has to live in the WRITER. That is what this library is for.
#
# THE BOX-LEVEL OVERRIDE
#   bp_mode() returns "pointer" (the default) or "full". Resolution order:
#     1. $OPENCLAW_BOOTSTRAP_POINTER_MODE           (env, highest)
#     2. $OC_CONFIG/bootstrap-pointer.conf          (per-box file)
#     3. agents.defaults.bootstrapPointerMode in openclaw.json
#     4. "pointer"                                  (repo default)
#   "full" restores the historical behaviour verbatim for a box that needs it;
#   nothing else in the roll changes. An unrecognised value is treated as
#   "pointer" and a warning is printed, because silently honouring a typo as
#   "full" would quietly re-bloat a box.
#
# MASTER-FILES ROOT
#   bp_master_files_dir() follows the convention every skill installer in this
#   repo already uses:
#     $OPENCLAW_MASTER_FILES_DIR                    (explicit override)
#     /data/.openclaw/master-files                  (VPS: /data/.openclaw/openclaw.json exists)
#     $HOME/Downloads/openclaw-master-files         (Mac default)
#
# SAFETY
#   Never prints a token, key or secret. Never removes an existing marker pair:
#   the engine REPLACES a pair's body in place, so every idempotency guard,
#   pair-balance check and dedup pass in the repo keeps working unchanged.

# shellcheck shell=bash

_BP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BP_ENGINE="${BP_ENGINE:-$_BP_LIB_DIR/bootstrap-pointerize.py}"

# ── Where this box keeps its reference corpus ────────────────────────────────
bp_master_files_dir() {
  if [ -n "${OPENCLAW_MASTER_FILES_DIR:-}" ]; then
    printf '%s' "${OPENCLAW_MASTER_FILES_DIR%/}"
  elif [ -f /data/.openclaw/openclaw.json ]; then
    printf '%s' "/data/.openclaw/master-files"
  else
    printf '%s' "$HOME/Downloads/openclaw-master-files"
  fi
}

# ── The reference file a given bootstrap file's pointers name ────────────────
# bp_reference_for <bootstrap-basename>   e.g. AGENTS.md -> .../AGENTS.md
bp_reference_for() {
  local base="${1:-AGENTS.md}"
  printf '%s/bootstrap-references/%s' "$(bp_master_files_dir)" "$base"
}

# ── pointer | full ───────────────────────────────────────────────────────────
bp_mode() {
  local mode="" cfg_root="${OC_CONFIG:-$HOME/.openclaw}"
  if [ -n "${OPENCLAW_BOOTSTRAP_POINTER_MODE:-}" ]; then
    mode="$OPENCLAW_BOOTSTRAP_POINTER_MODE"
  elif [ -s "$cfg_root/bootstrap-pointer.conf" ]; then
    mode="$(head -n1 "$cfg_root/bootstrap-pointer.conf" 2>/dev/null | tr -d '[:space:]')"
  elif [ -f "$cfg_root/openclaw.json" ] && command -v python3 >/dev/null 2>&1; then
    mode="$(OC_JSON="$cfg_root/openclaw.json" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    v = cfg.get("agents", {}).get("defaults", {}).get("bootstrapPointerMode")
    if isinstance(v, str):
        print(v.strip())
except Exception:
    pass
PYEOF
)"
  fi
  case "${mode:-}" in
    full)    printf 'full' ;;
    pointer|'') printf 'pointer' ;;
    *)
      printf 'pointer'
      printf '  [bootstrap-pointer] WARN: unrecognised mode %s — using pointer\n' \
        "$mode" >&2
      ;;
  esac
}

# ── Stamp ONE managed block as a pointer ─────────────────────────────────────
# bp_stamp <bootstrap-file> <marker-name> <heading> <summary> <triggers> [full-text-file]
#
#   <triggers>  newline-separated exact phrases (may be empty)
#
# Returns 0 when the block is present and correct (written OR already correct),
# non-zero only on a real refusal. A refusal NEVER leaves a dangling pointer:
# the engine writes the reference file first and refuses to stamp if it cannot.
bp_stamp() {
  local bootstrap="$1" marker="$2" heading="$3" summary="$4" triggers="$5"
  local full_text_file="${6:-}"
  local base ref args=() rc=0

  command -v python3 >/dev/null 2>&1 || {
    printf '  [bootstrap-pointer] python3 missing — leaving %s untouched\n' \
      "$(basename "$bootstrap")" >&2
    return 0
  }
  [ -f "$BP_ENGINE" ] || {
    printf '  [bootstrap-pointer] engine missing at %s — leaving %s untouched\n' \
      "$BP_ENGINE" "$(basename "$bootstrap")" >&2
    return 0
  }

  base="$(basename "$bootstrap")"
  ref="$(bp_reference_for "$base")"

  args=(--bootstrap "$bootstrap" --marker "$marker" --ref-file "$ref"
        --heading "$heading" --summary "$summary" --mode "$(bp_mode)")
  if [ -n "$triggers" ]; then
    while IFS= read -r _t; do
      [ -n "$_t" ] && args+=(--trigger "$_t")
    done <<<"$triggers"
  fi
  [ -n "$full_text_file" ] && args+=(--full-text-file "$full_text_file")

  python3 "$BP_ENGINE" "${args[@]}" >/dev/null 2>&1 || rc=$?
  case "$rc" in
    0|10) return 0 ;;                       # written, or already correct
    *)
      printf '  [bootstrap-pointer] REFUSED to stamp %s in %s (rc=%s) — file unchanged\n' \
        "$marker" "$base" "$rc" >&2
      return "$rc"
      ;;
  esac
}
