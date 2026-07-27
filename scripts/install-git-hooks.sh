#!/bin/bash
# install-git-hooks.sh -- idempotent, fail-closed, self-reporting installer
set -euo pipefail
DRY_RUN=0; FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1;;
    --force) FORCE=1;;
    *) echo "install-git-hooks.sh: unknown argument: $arg" >&2; exit 2;;
  esac
done
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "install-git-hooks.sh: FATAL -- not a git repository" >&2; exit 2; }
cd "$REPO_ROOT"
HOOK_FILE=".githooks/pre-commit"
MISSING=0
if [ ! -e "$HOOK_FILE" ]; then echo "install-git-hooks.sh: FATAL -- $HOOK_FILE does not exist" >&2; MISSING=1
elif [ ! -f "$HOOK_FILE" ]; then echo "install-git-hooks.sh: FATAL -- $HOOK_FILE is not a regular file" >&2; MISSING=1
elif [ ! -x "$HOOK_FILE" ]; then echo "install-git-hooks.sh: FATAL -- $HOOK_FILE is not executable" >&2; MISSING=1; fi
[ "$MISSING" -eq 1 ] && exit 2
CURRENT="$(git config --local --get core.hooksPath 2>/dev/null || true)"
if [ -z "$CURRENT" ]; then echo "current core.hooksPath: <ABSENT>"
else echo "current core.hooksPath: $CURRENT"; fi
DESIRED=".githooks"
RESOLVED_DESIRED="$(cd "$REPO_ROOT" && realpath "$DESIRED" 2>/dev/null || echo "$REPO_ROOT/$DESIRED")"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] would set core.hooksPath to: $DESIRED"; echo "[dry-run] no changes written"; exit 0
fi
if [ -n "$CURRENT" ] && [ "$CURRENT" != "$DESIRED" ]; then
  RESOLVED_CURRENT=""
  if [ -d "$CURRENT" ]; then RESOLVED_CURRENT="$(cd "$CURRENT" 2>/dev/null && pwd -P 2>/dev/null || echo "$CURRENT")"
  elif [[ "$CURRENT" == /* ]]; then RESOLVED_CURRENT="$CURRENT"
  else RESOLVED_CURRENT="$(cd "$REPO_ROOT" 2>/dev/null && cd "$CURRENT" 2>/dev/null && pwd -P 2>/dev/null || echo "")"; fi
  MATCH=0
  [ -n "$RESOLVED_CURRENT" ] && [ "$RESOLVED_CURRENT" = "$RESOLVED_DESIRED" ] && MATCH=1
  if [ "$MATCH" -eq 0 ]; then
    if [ "$FORCE" -eq 0 ]; then
      echo "install-git-hooks.sh: REFUSING -- core.hooksPath is set to a foreign value" >&2
      echo "  existing value: $CURRENT" >&2; echo "  re-run with --force to overwrite:" >&2
      echo "    bash scripts/install-git-hooks.sh --force" >&2; exit 3
    else echo "install-git-hooks.sh: --force passed -- overwriting foreign core.hooksPath '$CURRENT'"; fi
  fi
fi
[ "$CURRENT" = "$DESIRED" ] && echo "install-git-hooks.sh: core.hooksPath already set to .githooks -- nothing to change"
git config --local core.hooksPath .githooks
echo "install-git-hooks.sh: set core.hooksPath -> .githooks"
VERIFY_VAL="$(git config --local --get core.hooksPath 2>/dev/null || true)"
[ "$VERIFY_VAL" != "$DESIRED" ] && { echo "install-git-hooks.sh: VERIFICATION FAILED" >&2; exit 4; }
RESOLVED_HOOK="$(git rev-parse --git-path hooks/pre-commit 2>/dev/null || true)"
[ ! -x "$RESOLVED_HOOK" ] && { echo "install-git-hooks.sh: VERIFICATION FAILED" >&2; exit 4; }
echo "install-git-hooks.sh: verified -- hook resolves to $RESOLVED_HOOK (executable)"
echo ""; echo "install-git-hooks.sh: done. Seven commit-time gates armed on this clone:"
echo "  1. Client-name guard (fleet privacy)"; echo "  2. WhatsApp fleet ban"
echo "  3. N28 -- no destructive cron payloads"; echo "  4. chmod-600 coverage on secrets/.env writers"
echo "  5. Version consistency"; echo "  6. agent-browser singleton gateway"
echo "  7. Persona-set count triad"
echo ""; echo "NOTE: this installer does NOT propagate hooks to any other clone."
echo "Every clone must run scripts/install-git-hooks.sh once."
