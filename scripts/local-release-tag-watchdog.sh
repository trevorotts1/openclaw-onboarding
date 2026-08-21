#!/bin/bash
# local-release-tag-watchdog.sh
#
# Persistent LOCAL backstop for the release-tag ceremony. Fable delay-audit
# Recommendation R3 (CONTROL/DELAY-DIAGNOSIS-FABLE.md Section 2 D3, Section
# 4(b), Section 7 item 3): main sitting untagged blocked the entire merge
# lane EIGHT separate times in one day (2026-08-18 -> 2026-08-20), each time
# discovered by a human/agent only after it had already stalled something.
#
# WHY THIS EXISTS ON TOP OF THE CI AUTO-TAGGER
# ---------------------------------------------
# .github/workflows/auto-tag-on-merge.yml (scripts/auto-tag-if-version-changed.sh)
# already tags main automatically on every push, and as of 2026-08-21 IS
# working (main tagged at v22.0.65, last 4 workflow runs green). But it is a
# push-event, GitHub-Actions-hosted trigger: it depends on Actions staying
# enabled/permissioned/reachable, and on every relevant push actually firing
# the `push` event. If that path is ever silently skipped, main goes
# untagged with NOTHING watching -- the exact D3/G1b failure mode this
# recommendation exists to close.
#
# This script is the independent, LOCAL backstop that does not depend on
# GitHub Actions at all. It is deliberately STATE-based, not delta-based: it
# asks "is HEAD's version tagged right now?", not "did this one push change
# the version?" -- so it self-heals ANY untagged-main state regardless of how
# it happened (a skipped workflow run, a direct push, an Actions outage), on
# its own polling cadence, independent of the CI path succeeding or existing.
#
# THIS SCRIPT IS DELIBERATELY DUPLICATED.
# -----------------------------------------
# The reviewed, versioned copy ships in the repo at
# openclaw-onboarding/scripts/local-release-tag-watchdog.sh (this PR). The
# copy launchd actually executes lives OUTSIDE the repo, at
# ~/.claude/tools/local-release-tag-watchdog.sh -- because the repo checkout
# this script points at is a SHARED working tree with many concurrent agents
# switching branches constantly. A script invoked BY launchd from a path
# INSIDE that repo would go missing from disk the instant some other agent
# checks out a branch that predates it landing on main. This is the same
# reason pres-sentinel.sh and unpushed-branch-tripwire.sh (2026-08-20,
# this exact project) both live outside the repo and reach it via `-C`/`cd`.
# Keep the two copies byte-identical; update both together.
#
# LOGIC
# -----
#   1. Fetch origin/main + tags.
#   2. CURRENT_VER = origin/main's /version file.
#   3. If a tag CURRENT_VER already exists on the REMOTE -> no-op, log, exit 0.
#   4. Else, if CHANGELOG.md on origin/main documents CURRENT_VER (using the
#      EXACT same regex CI's own G2 gate uses --
#      .github/workflows/version-consistency.yml:
#      `^## \[?${tagname}\]?([[:space:]]|$)` -- so this watchdog can never
#      disagree with CI about what counts as "documented") -> publish it via
#      scripts/push-version-tag.sh. NEVER a bare `git push origin <tag>` --
#      that resolves the tag name against whatever LOCAL tag already exists
#      in THIS SHARED CHECKOUT'S tag namespace, which is exactly how
#      v20.0.89 / v20.0.90 got orphaned (see push-version-tag.sh's own
#      header for that incident).
#   5. Else (CHANGELOG lacks the entry) -> REFUSE to tag, say why, exit 0.
#      Never invent a tag for a version nobody has documented yet -- that
#      state is normal mid-merge (the CHANGELOG-bearing PR just hasn't
#      landed) and is not this watchdog's job to paper over.
#
# EXIT CODES (documented, not incidental -- a check that can't distinguish
# "ran fine, nothing to do" from "couldn't do its job" is worthless):
#   0 = ran to completion: no-op, successful tag, OR a correct refusal
#   2 = ENV FAILURE  -- a required tool missing/not executable, or lock busy
#   3 = REPO FAILURE -- repo path missing, not a git working tree, or
#       /version unreadable/malformed on origin/main
#   4 = REMOTE FAILURE -- git fetch failed
#   5 = push-version-tag.sh itself refused/failed on a real problem (tag
#       target not an ancestor of main, or a differing tag already
#       published at that name) -- NOT retried blindly by this script
#
# On this box, absolute paths matter: bare `git`/`bash`/`timeout` are not
# reliably on launchd's/cron's minimal PATH (delay-audit FAULT-29: 283 false
# "relaunched" lines from a bare `timeout`; FAULT-25: an HTTP-401 cron that
# ran under a PATH missing `gh` entirely and never said so). Every tool this
# script calls is resolved to an absolute path and preflight-checked before
# use.

set -u
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin

GIT_BIN=/usr/bin/git
BASH_BIN=/opt/homebrew/bin/bash
REPO=/Users/blackceomacmini/openclaw-onboarding
LOG=/Users/blackceomacmini/Library/Logs/openclaw/local-release-tag-watchdog.log
LOCK=/tmp/local-release-tag-watchdog.lockdir
REMOTE=origin
SELFTEST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --log) LOG="$2"; shift 2 ;;
    --remote) REMOTE="$2"; shift 2 ;;
    --selftest) SELFTEST=1; shift ;;
    -h|--help) sed -n '1,70p' "$0"; exit 0 ;;
    *) shift ;;
  esac
done

NOW_TS="$(date '+%m-%d %H:%M:%S' 2>/dev/null || echo unknown)"
say() {
  local line="$NOW_TS $*"
  echo "$line"
  local logdir
  logdir="$(dirname "$LOG" 2>/dev/null)"
  if [ -n "$logdir" ] && [ -d "$logdir" ]; then
    echo "$line" >> "$LOG" 2>/dev/null
  fi
}

# ---- STEP 1: prove every tool exists and is EXECUTABLE, not just a name ----
for b in "$GIT_BIN" "$BASH_BIN"; do
  if [ ! -x "$b" ]; then
    say "ABORT env-failure: required tool missing/not executable: $b (PATH=$PATH)"
    exit 2
  fi
done
if ! "$GIT_BIN" --version >/dev/null 2>&1; then
  say "ABORT env-failure: $GIT_BIN resolved but failed to execute"
  exit 2
fi

if [ "$SELFTEST" = "1" ]; then
  say "SELFTEST preflight ok; git=$GIT_BIN ($("$GIT_BIN" --version)) bash=$BASH_BIN repo=$REPO remote=$REMOTE"
  echo "preflight OK"
  exit 0
fi

# ---- STEP 2: prove the repo exists and is a real git working tree ----------
if [ -z "$REPO" ] || [ ! -d "$REPO" ]; then
  say "ABORT repo-failure: repo path does not exist: '$REPO'"
  exit 3
fi
if ! IS_WT=$("$GIT_BIN" -C "$REPO" rev-parse --is-inside-work-tree 2>&1); then
  say "ABORT repo-failure: '$REPO' is not a git working tree (git said: $IS_WT)"
  exit 3
fi

# ---- STEP 3: simple mkdir-based lock (no flock on this box); stale >10min --
if ! mkdir "$LOCK" 2>/dev/null; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$AGE" -gt 600 ]; then
    rm -rf "$LOCK"
    if ! mkdir "$LOCK" 2>/dev/null; then
      say "ABORT lock-failure: could not acquire $LOCK even after clearing a stale one"
      exit 2
    fi
  else
    say "SKIP another run holds $LOCK (age ${AGE}s, <600s) -- not double-running"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# ---- STEP 4: fetch origin main + tags --------------------------------------
if ! FETCH_OUT=$("$GIT_BIN" -C "$REPO" fetch "$REMOTE" main --tags --quiet 2>&1); then
  say "ABORT remote-failure: git fetch $REMOTE main --tags failed: $(echo "$FETCH_OUT" | tr '\n' ' ' | cut -c1-300)"
  exit 4
fi

# ---- STEP 5: read /version from origin/main (never the local working tree,
# which may currently be checked out to any branch in this shared repo) -----
CURRENT_VER=$("$GIT_BIN" -C "$REPO" show "$REMOTE/main:version" 2>/dev/null | head -1 | tr -d '[:space:]')
if [ -z "$CURRENT_VER" ]; then
  say "ABORT repo-failure: could not read /version from $REMOTE/main"
  exit 3
fi
if [[ ! "$CURRENT_VER" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  say "ABORT repo-failure: $REMOTE/main:/version is '$CURRENT_VER', not a vX.Y.Z string -- refusing to act"
  exit 3
fi

# ---- STEP 6: is it already tagged on the REMOTE? (authoritative -- never
# trust this shared checkout's local tag namespace, see header) -------------
REMOTE_TAG_LINE=$("$GIT_BIN" -C "$REPO" ls-remote --tags "$REMOTE" "refs/tags/${CURRENT_VER}" 2>/dev/null)
if [ -n "$REMOTE_TAG_LINE" ]; then
  say "OK $CURRENT_VER already published on $REMOTE -- nothing to do"
  exit 0
fi

# ---- STEP 7: does CHANGELOG.md on origin/main document this version? ------
# Identical regex to CI's own G2 gate (.github/workflows/version-consistency.yml
# check-released-versions-tagged step) so this watchdog can never disagree
# with CI about what counts as "documented": ^## \[?VER\]?([[:space:]]|$)
CHANGELOG_CONTENT=$("$GIT_BIN" -C "$REPO" show "$REMOTE/main:CHANGELOG.md" 2>/dev/null)
if ! echo "$CHANGELOG_CONTENT" | grep -qE "^## \[?${CURRENT_VER}\]?([[:space:]]|\$)"; then
  say "REFUSE $CURRENT_VER is untagged on $REMOTE/main AND CHANGELOG.md has no '## [$CURRENT_VER]' entry -- NOT tagging. Either an in-flight release (the CHANGELOG-bearing PR hasn't merged yet) or a genuine gap; a human/agent must add the CHANGELOG entry. This watchdog never invents a tag."
  exit 0
fi

# ---- STEP 8: publish it -- ONLY via the repo's own sanctioned script ------
MAIN_SHA=$("$GIT_BIN" -C "$REPO" rev-parse "$REMOTE/main")
say "ACT $CURRENT_VER is untagged on $REMOTE/main but CHANGELOG.md documents it -- publishing via scripts/push-version-tag.sh (never a bare 'git push origin <tag>')"
TAG_OUT=$(cd "$REPO" && "$BASH_BIN" scripts/push-version-tag.sh "$CURRENT_VER" "$MAIN_SHA" --remote "$REMOTE" 2>&1)
TAG_RC=$?
say "push-version-tag.sh rc=$TAG_RC output: $(echo "$TAG_OUT" | tr '\n' ' | ')"
if [ "$TAG_RC" -ne 0 ]; then
  say "ABORT push-version-tag.sh refused/failed (rc=$TAG_RC) for $CURRENT_VER -- see output above; NOT retried blindly, NOT falling back to a bare push"
  exit 5
fi
say "OK published $CURRENT_VER at ${MAIN_SHA:0:12}"
exit 0
