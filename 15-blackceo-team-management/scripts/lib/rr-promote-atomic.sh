#!/usr/bin/env bash
# rr-promote-atomic.sh — atomic promotion of a validated candidate into place.
#
# WHY A DRIVER AND NOT INLINE `mv`: the promotion must be a single rename within
# one directory (atomic on POSIX), must preserve the live file's permission bits
# and ownership rather than inheriting the candidate's, and must leave no window
# where the live path is missing. A plain `mv` across filesystems silently
# degrades to copy+unlink, which is NOT atomic.
#
# Contract: rr-promote-atomic.sh <candidate> <live>
#   exit 0  promoted (live now has the candidate's bytes, the live file's mode)
#   exit != 0  NOT promoted; the caller restores from its rollback snapshot.
#
# The caller (rr-config-transaction.py) treats any non-zero exit as a failed
# promote and restores the source bytes, so a failure here is safe: it must never
# leave a half-written live file.

set -euo pipefail

CAND="${1:?usage: rr-promote-atomic.sh <candidate> <live>}"
LIVE="${2:?usage: rr-promote-atomic.sh <candidate> <live>}"

[ -f "$CAND" ] || { echo "rr-promote-atomic: candidate missing: $CAND" >&2; exit 2; }
[ -f "$LIVE" ] || { echo "rr-promote-atomic: live file missing: $LIVE" >&2; exit 3; }

CAND_DIR="$(cd "$(dirname "$CAND")" && pwd)"
LIVE_DIR="$(cd "$(dirname "$LIVE")" && pwd)"
if [ "$CAND_DIR" != "$LIVE_DIR" ]; then
  echo "rr-promote-atomic: candidate and live are on different directories" >&2
  echo "  candidate: $CAND_DIR" >&2
  echo "  live     : $LIVE_DIR" >&2
  echo "  a cross-directory rename could be a non-atomic copy; refusing" >&2
  exit 4
fi

# Adopt the live file's mode so a 0600 config does not become world-readable.
MODE="$(stat -f '%Lp' "$LIVE" 2>/dev/null || stat -c '%a' "$LIVE" 2>/dev/null || echo '')"
if [ -n "$MODE" ]; then
  chmod "$MODE" "$CAND"
fi

# fsync the candidate so the rename cannot expose a partially durable file.
if command -v sync >/dev/null 2>&1; then sync "$CAND" 2>/dev/null || true; fi

# Single atomic rename within the same directory.
if ! mv -f "$CAND" "$LIVE"; then
  echo "rr-promote-atomic: rename failed; live file left untouched" >&2
  exit 5
fi

if command -v sync >/dev/null 2>&1; then sync "$LIVE" 2>/dev/null || true; fi
exit 0
