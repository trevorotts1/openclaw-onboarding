#!/usr/bin/env bash
# =============================================================================
# 23-ai-workforce-blueprint/wire.sh
# Skill-23 wiring installer -- installs presentation-notify.sh into
# ~/.openclaw/tools/, the directory production's PRESENTATION_NOTIFY_CMD
# actually reads from (see 23-ai-workforce-blueprint/templates/role-library/
# presentations/scripts/presentation_job/report.py, which dispatches to
# whatever PRESENTATION_NOTIFY_CMD points at).
#
# WHY THIS FILE EXISTS (root cause it fixes):
#   presentation-notify.sh (invoked by the Presentations department engine's
#   Reporter via PRESENTATION_NOTIFY_CMD) was written directly onto the live
#   operator box at ~/.openclaw/tools/presentation-notify.sh, OUTSIDE version
#   control -- confirmed absent from origin/main, every fetched branch's merge
#   base, and all open PRs; it existed only as an uncommitted live file and,
#   separately, as a hardened rewrite sitting on an unmerged branch at the
#   WRONG repo path (templates/role-library/presentations/scripts/ -- which
#   even a working department-materialization pass would only ever deploy to
#   ~/.openclaw/workspace/departments/Presentations/scripts/, never to
#   ~/.openclaw/tools/). No repo path mapped to a LOOSE file directly under
#   ~/.openclaw/tools/ before this commit -- the one existing precedent,
#   skill 44's convert-and-flow-cli, installs into a NAMED SUBDIRECTORY of
#   ~/.openclaw/tools/ via its own root wire.sh, a different target shape.
#   This wire.sh sits at the skill-23 ROOT so update-skills.sh's generic
#   wiring loop (priority: wire.sh > install.sh > scripts/install.sh, see
#   update-skills.sh's "Wiring installed skills" loop) picks it up on every
#   roll and installs the committed, hardened script to the exact path
#   production reads from -- closing the gap between "fixed in git" and
#   "reachable by any box."
#
# WHAT IT DOES (idempotent, fail-soft, single file, no side effects beyond it):
#   - copies tools/presentation-notify.sh (single source of truth, committed
#     alongside this installer) over ~/.openclaw/tools/presentation-notify.sh
#     whenever the two differ
#   - makes the installed copy executable
#   - fast no-op when the installed copy already matches the committed source
#     byte-for-byte (cmp, not a version stamp -- this file has no
#     skill-version.txt-driven build step to stamp, unlike caf)
#   - NEVER aborts the overall update: every failure is logged loudly and the
#     script still exits 0 (the wiring loop continues regardless)
#
# Invoked by update-skills.sh as: bash wire.sh --idempotent  (arg ignored --
# idempotency is unconditional here). Honours TOOLS_DIR env override for
# tests. No bare `gws`, no destructive ops, no client-specific values, touches
# nothing outside presentation-notify.sh's own install path.
# =============================================================================

# Fail-soft by contract: do NOT use `set -e` / `set -u`. A per-skill installer
# must never take down the fleet-wide update. Errors are handled explicitly
# and this script ALWAYS exits 0.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[skill23/wire] $*"; }

SRC="$SCRIPT_DIR/tools/presentation-notify.sh"

# ---- platform-aware tools root (mirrors skill 44's wire.sh convention) -----
if [ -z "${TOOLS_DIR:-}" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    TOOLS_DIR="$HOME/.openclaw/tools"
  else
    TOOLS_DIR="/data/.openclaw/tools"
  fi
fi
DEST="$TOOLS_DIR/presentation-notify.sh"

# ---- preflight: missing source -> log + bow out (update continues) --------
if [ ! -f "$SRC" ]; then
  log "ERROR: source not found at $SRC -- cannot install presentation-notify.sh. Skipping (update continues)."
  exit 0
fi

if ! mkdir -p "$TOOLS_DIR" 2>/dev/null; then
  log "ERROR: could not create $TOOLS_DIR -- skipping (update continues)."
  exit 0
fi

# ---- idempotency: fast no-op when the installed copy already matches -------
if [ -f "$DEST" ] && cmp -s "$SRC" "$DEST" 2>/dev/null; then
  log "presentation-notify.sh already current at $DEST -- no copy needed."
  chmod +x "$DEST" 2>/dev/null || true
  exit 0
fi

# ---- install (idempotent): copy committed source over the live tool -------
if cp "$SRC" "$DEST" 2>/dev/null && chmod +x "$DEST" 2>/dev/null; then
  log "OK: presentation-notify.sh installed -> $DEST"
else
  log "WARN: could not install presentation-notify.sh to $DEST (see above). Update continues; next roll will retry."
fi

# Fail-soft contract: ALWAYS succeed so the wiring loop never aborts.
exit 0
