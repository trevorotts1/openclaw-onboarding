#!/usr/bin/env bash
# skills-rollback.sh — a way back from a skills update WITHOUT copying the skills folder.
#
# The repo-owned folders in the skills directory (NN-*, shared-utils, universal-sops) are
# files from ONE commit of the onboarding repo; the content manifest records which one
# (src_git_sha). So the state before an update is fully described by
#   1. that commit — git re-creates every repo file from it — plus
#   2. whatever this box changed inside those folders — a small patch.
# update-skills.sh records exactly that before it replaces anything, instead of writing a
# full skills-backup-<ts> copy of the whole folder on every run.
#
#   snapshot <skills-dir> <out-dir> [<git-dir to reuse>]
#       Writes into <out-dir>: rollback.json, local-changes.patch, entries.txt, and the
#       previous .onboarding-version / .onboarding-content-manifest.json.
#       exit 0  rollback recorded
#       exit 3  no previous commit is known (fresh or pre-manifest box): the caller must
#               use another way back (update-skills.sh falls back to its one-time copy)
#       other   could not record it: the caller must not proceed as if it had
#   restore <out-dir> [<skills-dir>]
#       Puts the repo-owned folders back to the recorded commit, re-applies the local patch,
#       removes repo-owned folders the update added, and restores the stamp + manifest.
#
# Local changes cover edits, deletions and extra files inside the repo-owned folders.
# Caches (node_modules, __pycache__, *.pyc, virtualenvs, .cache) are left out: they are
# rebuilt, not restored. Folders the repo does not own (a box's custom skills) are never
# touched by the update, so they are neither recorded nor restored.
set -uo pipefail

REPO_URL="${ONBOARDING_REPO_URL:-https://github.com/trevorotts1/openclaw-onboarding.git}"
OWNED_RE='^([0-9][^/]*|shared-utils|universal-sops)$'

die() { echo "skills-rollback: $*" >&2; exit "${2:-1}"; }
g() { git -c safe.directory='*' -c core.autocrlf=false "$@"; }

TMPS=()
cleanup() { local t; for t in "${TMPS[@]+"${TMPS[@]}"}"; do rm -rf "$t"; done; }
trap cleanup EXIT

# previous ref: the recorded commit, else the stamped version's tag
prev_ref() {
  local skills=$1 sha="" ver=""
  [ -f "$skills/.onboarding-content-manifest.json" ] && sha=$(python3 -c '
import json, sys
try: print(json.load(open(sys.argv[1])).get("src_git_sha", ""))
except Exception: pass' "$skills/.onboarding-content-manifest.json" 2>/dev/null)
  if printf '%s' "$sha" | grep -qE '^[0-9a-f]{40}$'; then echo "$sha"; return 0; fi
  [ -f "$skills/.onboarding-version" ] && ver=$(head -1 "$skills/.onboarding-version" | tr -d '[:space:]')
  if printf '%s' "$ver" | grep -qE '^v[0-9]+(\.[0-9]+)*$'; then echo "refs/tags/$ver"; return 0; fi
  return 1
}

# fetch <git-dir> <ref> -> prints the commit sha
fetch_commit() {
  g --git-dir="$1" fetch -q --depth 1 "$REPO_URL" "$2" >&2 || return 1
  g --git-dir="$1" rev-parse -q --verify 'FETCH_HEAD^{commit}'
}

new_git_dir() {
  local d; d=$(mktemp -d "${TMPDIR:-/tmp}/skills-rollback-git.XXXXXX") || return 1
  TMPS+=("$d"); g init -q --bare "$d" && echo "$d"
}

snapshot() {
  local skills=${1:-} out=${2:-} gd=${3:-} ref commit scope idx excl n
  [ -d "$skills" ] || die "skills dir not found: $skills"
  [ -n "$out" ] || die "usage: snapshot <skills-dir> <out-dir> [git-dir]"
  ref=$(prev_ref "$skills") || die "no previous commit recorded in $skills (no manifest sha, no version tag)" 3
  if [ -z "$gd" ] || [ ! -d "$gd" ]; then gd=$(new_git_dir) || die "mktemp failed"; fi
  commit=$(fetch_commit "$gd" "$ref") || die "could not fetch previous commit $ref from $REPO_URL"

  scope=$(g --git-dir="$gd" ls-tree --name-only "$commit" | grep -E "$OWNED_RE" | while IFS= read -r n; do
    [ -e "$skills/$n" ] && printf '%s\n' "$n"; done)
  mkdir -p "$out" || die "cannot create $out"

  idx=$(mktemp "${TMPDIR:-/tmp}/skills-rollback-index.XXXXXX") && TMPS+=("$idx") && rm -f "$idx"  # git creates it; an empty file is not a valid index
  excl=$(mktemp "${TMPDIR:-/tmp}/skills-rollback-excl.XXXXXX") && TMPS+=("$excl")
  printf '%s\n' 'node_modules/' '__pycache__/' '*.pyc' '.venv/' 'venv/' '.cache/' '.DS_Store' > "$excl"
  : > "$out/local-changes.patch"
  if [ -n "$scope" ]; then
    # index = the previous commit; stage the box's actual files over it; the staged diff
    # is exactly what this box changed. Nothing is copied: git hashes the files in place.
    GIT_INDEX_FILE="$idx" g --git-dir="$gd" --work-tree="$skills" read-tree "$commit" || die "read-tree failed"
    # shellcheck disable=SC2086
    GIT_INDEX_FILE="$idx" g -c core.excludesFile="$excl" --git-dir="$gd" --work-tree="$skills" \
      add -A -- $scope || die "could not compare $skills with $commit"
    # shellcheck disable=SC2086
    GIT_INDEX_FILE="$idx" g --git-dir="$gd" --work-tree="$skills" \
      diff --cached --binary "$commit" -- $scope > "$out/local-changes.patch" || die "diff failed"
  fi

  ls -A "$skills" > "$out/entries.txt"
  for n in .onboarding-version .onboarding-content-manifest.json; do
    [ -f "$skills/$n" ] && cp -p "$skills/$n" "$out/$n"
  done
  python3 - "$out/rollback.json" "$commit" "$ref" "$REPO_URL" "$skills" "$scope" <<'PY' || die "cannot write rollback.json"
import json, sys, datetime
path, commit, ref, url, skills, scope = sys.argv[1:7]
json.dump({"commit": commit, "ref": ref, "repo_url": url, "skills_dir": skills,
           "scope": [s for s in scope.split("\n") if s],
           "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
          open(path, "w"), indent=2)
PY
  echo "  rollback recorded (no copy of the skills folder): commit ${commit:0:12}," \
       "local changes $(wc -c < "$out/local-changes.patch" | tr -d ' ') bytes -> $out"
}

restore() {
  local out=${1:-} skills=${2:-} commit url scope gd idx n
  [ -f "$out/rollback.json" ] || die "no rollback.json in $out"
  commit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$out/rollback.json")
  url=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repo_url"])' "$out/rollback.json")
  scope=$(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["scope"]))' "$out/rollback.json")
  [ -n "$skills" ] || skills=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["skills_dir"])' "$out/rollback.json")
  [ -d "$skills" ] || die "skills dir not found: $skills"
  REPO_URL="$url"
  gd=$(new_git_dir) || die "mktemp failed"
  fetch_commit "$gd" "$commit" >/dev/null || die "could not fetch $commit from $url"

  # repo-owned folders the update ADDED (absent at snapshot time) go away
  ls -A "$skills" | while IFS= read -r n; do
    printf '%s' "$n" | grep -qE "$OWNED_RE" || continue
    grep -qxF -- "$n" "$out/entries.txt" && continue
    rm -rf -- "${skills:?}/$n" && echo "  removed (added by the update): $n"
  done
  if [ -n "$scope" ]; then
    printf '%s\n' "$scope" | while IFS= read -r n; do rm -rf -- "${skills:?}/$n"; done
    idx=$(mktemp "${TMPDIR:-/tmp}/skills-rollback-index.XXXXXX") && TMPS+=("$idx") && rm -f "$idx"  # git creates it; an empty file is not a valid index
    # shellcheck disable=SC2046
    GIT_INDEX_FILE="$idx" g --git-dir="$gd" --work-tree="$skills" checkout "$commit" -- $(printf '%s ' $scope) \
      || die "could not check out $commit into $skills"
  fi
  if [ -s "$out/local-changes.patch" ]; then
    (cd "$skills" && g --git-dir="$gd" --work-tree=. apply --binary --whitespace=nowarn "$out/local-changes.patch") \
      || die "commit restored, but the local-changes patch did not apply: $out/local-changes.patch"
  fi
  for n in .onboarding-version .onboarding-content-manifest.json; do
    [ -f "$out/$n" ] && cp -p "$out/$n" "$skills/$n"
  done
  echo "  restored $skills to ${commit:0:12} plus this box's local changes"
}

case "${1:-}" in
  snapshot) shift; snapshot "$@" ;;
  restore)  shift; restore "$@" ;;
  *) echo "usage: $0 snapshot <skills-dir> <out-dir> [git-dir] | restore <out-dir> [skills-dir]" >&2; exit 2 ;;
esac
