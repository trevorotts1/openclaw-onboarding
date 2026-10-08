#!/usr/bin/env bash
# test_starter_tasks_gate.sh -- phase 6e seeds "Welcome to <dept>" starter tasks
# ONLY on a full install whose build has closed out. The Command Center's intake
# sweep auto-dispatches every seeded card and the notifier then messages the
# owner's chat, so a card seeded before closeout is an unrequested owner message.
# Runs the REAL starter_tasks_allowed() extracted from run-full-install.sh.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"
PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

BLOCK="$(sed -n '/>>> STARTER-TASKS-GATE-BEGIN/,/<<< STARTER-TASKS-GATE-END/p' "$SRC")"
[ -n "$BLOCK" ] || { echo "FAIL: STARTER-TASKS-GATE block not found in run-full-install.sh"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
case_run() {  # $1=BLOCK_B_UPDATE_ONLY (== UPDATE_ONLY except on a first standard-placeholder build)  $2=closeoutStatus (or "")
  local state="$TMP/state.json"
  if [ -n "$2" ]; then printf '{"closeoutStatus":"%s"}' "$2" > "$state"; else echo '{}' > "$state"; fi
  BLOCK_B_UPDATE_ONLY="$1" STATE_FILE="$state" bash -c '
    state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
    '"$BLOCK"'
    starter_tasks_allowed && echo SEED || echo SKIP'
}

[ "$(case_run false "")" = SKIP ]        && ok "full install, build not closed out: no starter tasks" || bad "full install before closeout seeds starter tasks"
[ "$(case_run false generating)" = SKIP ] && ok "full install, closeout generating: no starter tasks" || bad "seeded during closeout"
[ "$(case_run true done)" = SKIP ]        && ok "update-only roll: never" || bad "update-only roll seeds starter tasks"
[ "$(case_run false done)" = SEED ]      && ok "full install after closeout: seeded (control)" || bad "control: closed-out full install did not seed"

echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
