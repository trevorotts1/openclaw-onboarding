#!/bin/sh
# git_ff_sync.sh <repo> -- fast-forward a clone, safely handling a GONE upstream.
#
# CAN005: a clone left on a branch whose upstream was merged and deleted on the
# remote made a bare `git pull --ff-only` abort ("no such ref was fetched").
# Used by fleet_refresh_runner.step_update_999 and lib-frontdoor.sh
# frontdoor_update_999 so both 999-setup refresh paths behave the same.
#
# Exit 0  synced (one status line on stdout, e.g. "switched <br> -> main ...")
# Exit 3  NEEDS ATTENTION: left untouched; the reason is on stdout
# Exit 1  git failure; git's message is on stdout
# Never: reset --hard, stash, branch delete, discarding local changes.
repo=${1:?usage: git_ff_sync.sh <repo>}
g() { git -C "$repo" "$@"; }

out=$(g fetch --prune --quiet origin 2>&1) || { echo "git fetch --prune failed: $out"; exit 1; }

br=$(g symbolic-ref -q --short HEAD)   # empty when detached: plain pull below reports it
if [ -n "$br" ] && [ "$(g config --get "branch.$br.remote")" = origin ]; then
  up=$(g config --get "branch.$br.merge")
  if [ -n "$up" ] && ! g rev-parse -q --verify "refs/remotes/origin/${up#refs/heads/}" >/dev/null; then
    # Upstream configured but gone from origin (merged + deleted).
    def=$(g symbolic-ref -q --short refs/remotes/origin/HEAD); def=${def#origin/}
    [ -n "$def" ] || for def in main master; do
      g rev-parse -q --verify "refs/remotes/origin/$def" >/dev/null && break; def=
    done
    [ -n "$def" ] || { echo "branch $br: upstream gone and origin default branch unknown; left untouched"; exit 3; }
    if [ -n "$(g status --porcelain --untracked-files=no)" ]; then
      echo "branch $br: upstream gone and the tree has local changes; left untouched"; exit 3
    fi
    n=$(g rev-list --count "origin/$def..HEAD")
    if [ "$n" != 0 ]; then
      echo "branch $br: upstream gone (deleted on origin) and $n commit(s) are not in origin/$def; left untouched"; exit 3
    fi
    if g rev-parse -q --verify "refs/heads/$def" >/dev/null \
       && [ "$(g rev-list --count "origin/$def..$def")" != 0 ]; then
      echo "branch $br: upstream gone, but local $def has $(g rev-list --count "origin/$def..$def") commit(s) not in origin/$def; left untouched"; exit 3
    fi
    out=$(g checkout --quiet "$def" 2>&1) || { echo "checkout $def failed: $out"; exit 1; }
    # All-or-nothing: if the ff fails (e.g. untracked file clashes), go back to $br.
    out=$(g merge --ff-only --quiet "origin/$def" 2>&1) || {
      g checkout --quiet "$br" >/dev/null 2>&1
      echo "left on $br (ff $def failed): $out"; exit 1; }
    echo "switched $br -> $def (upstream gone, 0 unmerged commits); $br kept"
    exit 0
  fi
fi

out=$(g pull --ff-only --quiet 2>&1) || { echo "$out"; exit 1; }
exit 0
