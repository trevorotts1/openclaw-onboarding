#!/usr/bin/env bash
# Shared motion render runtime -- ROLLBACK (MG-041)
#
# provision.sh promotes a new runtime only after its probe passes, and it
# never deletes a previous version directory. Rollback is therefore a
# pointer flip, never a rebuild: this script points .runtime/current
# back at an earlier verified version and refreshes the active lock copy.
#
# Usage:
#   rollback.sh                flip to the newest other version whose
#                              recorded probe passed
#   rollback.sh <version-id>   flip to versions/<version-id> (its recorded
#                              probe must have passed)
#
# Refusals (exit 1, FAIL line, pointer untouched):
#   - the target version does not exist, or its runtime-lock.json does
#     not record a passing probe for the mandatory engines;
#   - .runtime/active-renders.json records a render whose process is
#     still alive: a rollback never lands mid-render (MG-041 rule: let
#     already-running jobs finish on their pinned runtime);
#   - node is unavailable (lock records cannot be verified without it).
#
# MOTION_RUNTIME_HOME overrides the runtime home (default: this script's
# directory). It exists so an operator can verify a staged copy before
# touching the live one, and so tests can run against a fixture runtime.
# Nothing is ever deleted by this script.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_HOME="${MOTION_RUNTIME_HOME:-$SCRIPT_DIR}"
STATE_DIR="$RUNTIME_HOME/.runtime"
VERSIONS_DIR="$STATE_DIR/versions"
CURRENT_LINK="$STATE_DIR/current"

red()   { printf "\033[31mFAIL\033[0m %s\n" "$1" >&2; }
green() { printf "\033[32m OK \033[0m %s\n" "$1"; }
fail_out() { red "$1"; exit 1; }

command -v node >/dev/null 2>&1 || fail_out "node is not installed; runtime lock records cannot be verified without it."
[ -d "$VERSIONS_DIR" ] || fail_out "No versions directory at $VERSIONS_DIR; nothing to roll back to."

# --- Refuse while a render is active --------------------------------------
if [ -f "$STATE_DIR/active-renders.json" ]; then
  LIVE_PIDS="$(node -e '
    const fs = require("fs");
    let doc;
    try { doc = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); } catch { process.exit(0); }
    const live = [];
    for (const entry of (doc.renders || [])) {
      if (entry && Number.isInteger(entry.pid)) {
        try { process.kill(entry.pid, 0); live.push(entry.pid); } catch { /* stale record */ }
      }
    }
    process.stdout.write(live.join(" "));
  ' "$STATE_DIR/active-renders.json")"
  [ -n "$LIVE_PIDS" ] && fail_out "A render is active (pid(s): $LIVE_PIDS). Rollback is refused mid-render; the running job keeps its pinned runtime."
fi

# --- Resolve the current target -------------------------------------------
CURRENT_TARGET=""
if [ -L "$CURRENT_LINK" ]; then
  CURRENT_TARGET="$(cd "$STATE_DIR" && readlink current || true)"
fi

# lock_passes <version-dir>: recorded probe passed for mandatory engines.
lock_passes() {
  node -e '
    const fs = require("fs");
    let lock;
    try { lock = JSON.parse(fs.readFileSync(process.argv[1] + "/runtime-lock.json", "utf8")); }
    catch { process.exit(1); }
    if (lock.result !== "pass") process.exit(1);
    const engines = lock.engines || {};
    for (const name of ["remotion", "hyperframes"]) {
      if (engines[name] && engines[name].status !== "pass") process.exit(1);
    }
    process.exit(0);
  ' "$1"
}

# --- Pick the target --------------------------------------------------------
TARGET_ID="${1:-}"
if [ -n "$TARGET_ID" ]; then
  [ -d "$VERSIONS_DIR/$TARGET_ID" ] || fail_out "No runtime version versions/$TARGET_ID under $VERSIONS_DIR."
else
  # Newest (by mtime) verified version other than the current target.
  TARGET_ID="$(
    for d in "$VERSIONS_DIR"/*/; do
      [ -d "$d" ] || continue
      name="$(basename "$d")"
      [ "versions/$name" = "$CURRENT_TARGET" ] && continue
      lock_passes "$d" || continue
      printf '%s %s\n' "$(stat -c %Y "$d" 2>/dev/null || stat -f %m "$d" 2>/dev/null || echo 0)" "$name"
    done | sort -rn | head -1 | cut -d' ' -f2-
  )"
  [ -n "$TARGET_ID" ] || fail_out "No other verified runtime version to roll back to (current: ${CURRENT_TARGET:-none})."
fi

TARGET_DIR="$VERSIONS_DIR/$TARGET_ID"
lock_passes "$TARGET_DIR" || fail_out "versions/$TARGET_ID has no passing probe record; refusing to activate an unverified runtime."
[ "versions/$TARGET_ID" = "$CURRENT_TARGET" ] && { green "=== Already on versions/$TARGET_ID; nothing to do. ==="; exit 0; }

# --- Atomic flip (same semantics as provision.sh promote()) ---------------
ln -s "versions/$TARGET_ID" "$STATE_DIR/current.tmp.$$"
mv -Tf "$STATE_DIR/current.tmp.$$" "$CURRENT_LINK" 2>/dev/null || { rm -f "$CURRENT_LINK"; ln -s "versions/$TARGET_ID" "$CURRENT_LINK"; }
cp "$TARGET_DIR/runtime-lock.json" "$STATE_DIR/runtime-lock.json"

green "=== Shared motion render runtime ROLLED BACK: .runtime/current -> versions/$TARGET_ID (was ${CURRENT_TARGET:-none}). ==="
printf "     Proof record: %s\n" "$STATE_DIR/runtime-lock.json"
exit 0
