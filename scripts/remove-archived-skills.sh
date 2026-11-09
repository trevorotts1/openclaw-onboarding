#!/usr/bin/env bash
# remove-archived-skills.sh -- take retired "NN-name-ARCHIVED" skill folders out of a box's skills folder.
#
# WHY. OpenClaw rescans the skills folder constantly and logs one error per scan for every
# folder it cannot load ("[skills] Skipping invalid skill: ... error=description is required",
# 234 times each in 13 hours on one client box). A retired skill folder has no use inside the
# skills folder, so it is moved out instead of tolerated. The repo no longer ships any *-ARCHIVED
# folder (see docs/archived-skill-tombstones.json); this clears the copies older rolls left behind.
#
# MOVED, NEVER DELETED. Each folder is moved to <parent of the skills folder>/retired-skills/, the
# same destination and naming update-skills.sh uses when it retires an old live copy of a retired
# skill (~/.openclaw/retired-skills on a Mac, /data/.openclaw/retired-skills on a Hostinger VPS,
# /home/node/.openclaw/retired-skills on a Contabo box). That folder is OUTSIDE the skills folder,
# so OpenClaw never scans it, and a box-local folder that never came from the repo (for example one
# made by hand) can still be put back by hand. If the destination name is already taken the
# move gets a "-<YYYYmmddHHMMSS>" suffix (and a "-<n>" counter if even that is taken): an earlier
# retired copy is never overwritten.
#
# WHAT IT MOVES. Only a real directory directly inside the skills folder whose name matches
# ^[0-9]+-.*-ARCHIVED$ exactly. Symlinks (skipped silently, every run), plain files and every
# other name (including live skills that merely contain the word "archive") are never touched.
#
# Idempotent: a second run finds nothing and prints nothing. Safe as the box user or as root
# (a move leaves no root-owned files behind in the skills folder). Exit 0 = nothing left to
# move, 1 = at least one folder could not be moved (reported on stderr; callers treat that as
# non-fatal).
#
# Usage: remove-archived-skills.sh [SKILLS_DIR]
#   SKILLS_DIR defaults to the same folder update-skills.sh uses:
#   ${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills}
set -u

skills_dir="${1:-${OC_SKILLS_DIR:-${OPENCLAW_ROOT:-${OC_CONFIG:-$HOME/.openclaw}}/skills}}"
skills_dir="${skills_dir%/}"
[ -d "$skills_dir" ] || exit 0
dest="$(dirname "$skills_dir")/retired-skills"

failed=0
for p in "$skills_dir"/*-ARCHIVED; do
  name="${p##*/}"
  [[ "$name" =~ ^[0-9]+-.*-ARCHIVED$ ]] || continue
  [ -L "$p" ] && continue
  [ -d "$p" ] || continue
  target="$dest/$name"
  if [ -e "$target" ] || [ -L "$target" ]; then
    stamp="$(date +%Y%m%d%H%M%S)"
    target="$dest/$name-$stamp"
    n=0
    while [ -e "$target" ] || [ -L "$target" ]; do
      n=$((n + 1))
      target="$dest/$name-$stamp-$n"
    done
  fi
  if mkdir -p "$dest" 2>/dev/null && mv -- "$p" "$target" 2>/dev/null && [ ! -e "$p" ]; then
    echo "  ✓ moved retired skill folder out of the skills folder: $name -> $target"
  else
    echo "  ⚠ could not move retired skill folder $p to $target (owner $(stat -c '%U' "$p" 2>/dev/null || stat -f '%Su' "$p" 2>/dev/null || echo unknown), running as $(id -un 2>/dev/null || echo unknown)); re-run as the box user" >&2
    failed=1
  fi
done
exit "$failed"
