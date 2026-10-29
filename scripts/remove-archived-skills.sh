#!/usr/bin/env bash
# remove-archived-skills.sh -- delete retired "NN-name-ARCHIVED" skill folders from a box.
#
# WHY. OpenClaw rescans the skills folder constantly and logs one error per scan for every
# folder it cannot load ("[skills] Skipping invalid skill: ... error=description is required",
# 234 times each in 13 hours on one client box). A retired skill folder has no value on a
# box, so it is removed instead of tolerated. The repo no longer ships any *-ARCHIVED folder
# (see docs/archived-skill-tombstones.json); this removes the copies older rolls left behind.
#
# WHAT IT REMOVES. Only a real directory directly inside the skills folder whose name matches
# ^[0-9]+-.*-ARCHIVED$ exactly. Symlinks, plain files and every other name (including live
# skills that merely contain the word "archive") are never touched.
#
# Idempotent: a second run finds nothing and prints nothing. Safe as the box user or as root
# (deleting leaves no root-owned files behind). Exit 0 = nothing left to remove, 1 = at least
# one folder could not be removed (reported on stderr; callers treat that as non-fatal).
#
# Usage: remove-archived-skills.sh [SKILLS_DIR]
#   SKILLS_DIR defaults to the same folder update-skills.sh uses:
#   ${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills}
set -u

skills_dir="${1:-${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills}}"
[ -d "$skills_dir" ] || exit 0

failed=0
for p in "$skills_dir"/*-ARCHIVED; do
  name="${p##*/}"
  [[ "$name" =~ ^[0-9]+-.*-ARCHIVED$ ]] || continue
  if [ -L "$p" ]; then
    echo "  - left retired skill link alone (symlink, not a folder): $p"
    continue
  fi
  [ -d "$p" ] || continue
  if rm -rf -- "$p" 2>/dev/null && [ ! -e "$p" ]; then
    echo "  ✓ removed retired skill folder: $name (from $skills_dir)"
  else
    echo "  ⚠ could not remove retired skill folder $p (owner $(stat -c '%U' "$p" 2>/dev/null || stat -f '%Su' "$p" 2>/dev/null || echo unknown), running as $(id -un 2>/dev/null || echo unknown)); re-run as the box user" >&2
    failed=1
  fi
done
exit "$failed"
