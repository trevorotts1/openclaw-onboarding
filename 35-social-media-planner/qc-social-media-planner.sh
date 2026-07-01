#!/usr/bin/env bash
# ============================================================
#  qc-social-media-planner.sh — Skill 35 Install QC (compat shim)
#
#  This script used to be a near-duplicate of qc-skill35.sh and the
#  two copies drifted (e.g. one carried a broken --announce assert
#  longer than the other). It is now a THIN DELEGATOR so there is
#  exactly ONE source of truth: qc-skill35.sh. The historical entry-
#  point name is preserved for any caller that still invokes it.
#
#  All QC logic — credentials, software, GHL access, cron presence,
#  fix assertions — lives in qc-skill35.sh. Edit that file, not this.
# ============================================================
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
CANON="$HERE/qc-skill35.sh"
if [ ! -f "$CANON" ]; then
  CANON="$HOME/.openclaw/skills/35-social-media-planner/qc-skill35.sh"
fi
if [ ! -f "$CANON" ]; then
  echo "ERROR: canonical QC script qc-skill35.sh not found next to this shim ($HERE)." >&2
  echo "qc-social-media-planner.sh now delegates to qc-skill35.sh — ensure it is installed." >&2
  exit 1
fi

exec bash "$CANON" "$@"
