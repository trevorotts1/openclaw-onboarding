#!/usr/bin/env bash
# pr-truth.sh -- answers "what is this PR's REAL state?" See TOOLS.md's
# "Git-truth tools" section and QC-PROTOCOL.md's binding citation rule.
#
# Three independent, content-level checks -- never GitHub's PR `state` or
# `merged` field for the verdict (that field EXCLUDES manually-pushed
# merges, which is exactly this repo's own `git merge --no-ff` + plain
# push discipline):
#
#   --zombie              Is this PR's content already on main? A DEEP
#                          CONTENT DIFF of every touched path, not mere
#                          ancestry -- a real zombie can carry a commit sha
#                          ancestry will never find (squash/rebase/
#                          independent identical reimplementation).
#   --stale-ref MERGE_SHA  Does the given merge commit's branch-side parent
#                          match the PR's LIVE HEAD right now? This is the
#                          check ancestry structurally cannot do: the
#                          merged parent can be a perfectly true ancestor of
#                          main while still being an OLDER point on the
#                          branch than its real tip.
#   --supersedes OTHER_PR  Does THIS pr's tree genuinely contain every file
#                          OTHER_PR's tree has, with identical content? A
#                          real, live, both-directions diff -- must be able
#                          to answer NO.
#
# Usage:
#   ./pr-truth.sh <pr-number> [--repo owner/repo] --zombie
#   ./pr-truth.sh <pr-number> [--repo owner/repo] --stale-ref <merge-sha>
#   ./pr-truth.sh <pr-number> [--repo owner/repo] --supersedes <other-pr>
#
# --repo defaults to trevorotts1/openclaw-onboarding. PR numbers are
# per-repo -- pass --repo explicitly for a PR that lives in
# trevorotts1/blackceo-command-center (do NOT assume a PR number implies
# openclaw-onboarding just because that's where this script lives).
#
# --repo-dir (local clone of --repo) defaults to an auto-managed,
# auto-fetched cache under $PR_TRUTH_CACHE_DIR (default
# ~/.cache/openclaw-git-truth-tools/<repo-name>); openclaw-onboarding
# defaults to this repo itself when --repo is left at its default.
#
# Exit codes: 0 = clean verdict (NOT-ZOMBIE / NOT-STALE / YES),
#             1 = bad verdict (ZOMBIE / STALE-REF / NO / DIVERGED / PARTIAL),
#             3 = UNKNOWN (never guessed).
#
# Examples proven by this tool's own test suite (the acceptance bar, not
# unit tests -- see tests/unit/pr-truth-historical.test.py):
#   ./pr-truth.sh 193 --repo trevorotts1/blackceo-command-center \
#       --stale-ref 5654cba882f4c0033bca70ee69eb6de4223d6322   -> STALE-REF
#   ./pr-truth.sh 617 --supersedes 599                          -> NO

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_PY="$SCRIPT_DIR/shared-utils/pr_truth_core.py"

if [ ! -f "$CORE_PY" ]; then
  echo "ERROR: $CORE_PY not found -- pr-truth.sh must live at the repo root next to shared-utils/." >&2
  exit 2
fi

usage() {
  sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

[ $# -ge 1 ] || usage
PR_NUM="$1"; shift
if ! [[ "$PR_NUM" =~ ^[0-9]+$ ]]; then
  echo "ERROR: PR number must be numeric, got '$PR_NUM'" >&2
  exit 2
fi

REPO="trevorotts1/openclaw-onboarding"
REPO_DIR=""
MODE_ARGS=()
JSON_OUT=0
CACHE_DIR="${PR_TRUTH_CACHE_DIR:-$HOME/.cache/openclaw-git-truth-tools}"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --repo-dir) REPO_DIR="$2"; shift 2 ;;
    --zombie) MODE_ARGS+=(--zombie); shift ;;
    --stale-ref) MODE_ARGS+=(--stale-ref "$2"); shift 2 ;;
    --supersedes) MODE_ARGS+=(--supersedes "$2"); shift 2 ;;
    --json) JSON_OUT=1; shift ;;
    -h|--help) usage ;;
    *) echo "ERROR: unknown arg '$1'" >&2; usage ;;
  esac
done

if [ ${#MODE_ARGS[@]} -eq 0 ]; then
  echo "ERROR: pass exactly one of --zombie / --stale-ref <merge-sha> / --supersedes <other-pr>" >&2
  usage
fi

REPO_NAME="${REPO##*/}"

if [ -z "$REPO_DIR" ]; then
  if [ "$REPO" = "trevorotts1/openclaw-onboarding" ] && [ -f "$SCRIPT_DIR/shared-utils/pr_truth_core.py" ] && git -C "$SCRIPT_DIR" remote get-url origin 2>/dev/null | grep -qi "openclaw-onboarding"; then
    REPO_DIR="$SCRIPT_DIR"
    git -C "$REPO_DIR" fetch -q origin main 2>/dev/null || echo "[pr-truth] WARNING: could not refresh $REPO_DIR origin/main" >&2
  else
    REPO_DIR="$CACHE_DIR/$REPO_NAME"
    mkdir -p "$CACHE_DIR"
    if [ -d "$REPO_DIR/.git" ]; then
      echo "[pr-truth] refreshing cached $REPO clone at $REPO_DIR ..." >&2
      git -C "$REPO_DIR" fetch -q origin main || echo "[pr-truth] WARNING: fetch failed, using stale cache" >&2
    else
      echo "[pr-truth] cloning $REPO into $REPO_DIR (one-time) ..." >&2
      git clone -q "https://github.com/$REPO.git" "$REPO_DIR"
    fi
  fi
fi

CLI_ARGS=(python3 "$CORE_PY" "$PR_NUM" --repo "$REPO" --repo-dir "$REPO_DIR" "${MODE_ARGS[@]}")
[ "$JSON_OUT" = "1" ] && CLI_ARGS+=(--json)

exec "${CLI_ARGS[@]}"
