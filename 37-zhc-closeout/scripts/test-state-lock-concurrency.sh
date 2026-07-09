#!/usr/bin/env bash
# ============================================================
# test-state-lock-concurrency.sh — SK1-13 regression test.
#
# Proves the shared, mkdir-mutex state_set (lib-closeout-state.sh):
#   A. UNLOCKED baseline LOSES updates under concurrent read-modify-write
#      (demonstrates the race is real + the test can detect it).
#   B. LOCKED state_set loses NO updates under the same concurrency
#      (the mutex fixes the lost-update window).
#   C. A STALE lock (crashed writer) is reclaimed — state_set does NOT hang.
#   D. A live-but-stuck lock is broken after the BOUNDED wait — no hang.
#   E. All 10 Skill-37 scripts are wired to source the shared lib.
#
# Writers run as independent processes racing on ONE state file, exactly like
# resume-closeout-cron.sh racing a nohup'd run-closeout.sh. Self-contained:
# uses a private temp workspace and cleans up. No network, no real workspace.
# ============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/lib-closeout-state.sh"

if [[ ! -f "$LIB" ]]; then
  echo "FATAL: lib-closeout-state.sh not found at $LIB" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "FATAL: jq is required for this test" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
STATE_FILE="$TMP_DIR/state.json"
WORKER="$TMP_DIR/worker.sh"

WRITERS=4
LOCKED_ITERS=50            # expected locked total = WRITERS*LOCKED_ITERS = 200
UNLOCKED_ITERS=25          # expected unlocked total (if no loss) = 100

fails=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# ---- worker process: increments .counter ITERS times in the given mode ----
# mode=locked      -> uses the real lib state_set (mkdir-mutex serialized).
# mode=unlocked    -> naive read / (widen window) / write, NO lock. Deterministic
#                     loss under concurrency: models the pre-fix jq->tmp->mv copy.
cat > "$WORKER" <<'WORKEREOF'
#!/usr/bin/env bash
set -u
STATE_FILE="$1"; ITERS="$2"; MODE="$3"; LIB="$4"
# shellcheck disable=SC1090
[[ "$MODE" == "locked" ]] && source "$LIB"
i=0
while (( i < ITERS )); do
  if [[ "$MODE" == "locked" ]]; then
    state_set '.counter += 1' || true
  else
    cur="$(jq -r '.counter' "$STATE_FILE" 2>/dev/null)"
    [[ -z "$cur" || "$cur" == "null" ]] && cur=0
    sleep 0.02                      # widen the read-modify-write window
    tmp="$(mktemp)"
    if jq ".counter = $((cur + 1))" "$STATE_FILE" > "$tmp" 2>/dev/null; then
      mv "$tmp" "$STATE_FILE"
    else
      rm -f "$tmp"
    fi
  fi
  i=$((i + 1))
done
WORKEREOF
chmod +x "$WORKER"

reset_state() { printf '{"counter": 0}\n' > "$STATE_FILE"; rm -rf "${STATE_FILE}.lock"; }
counter_now() { jq -r '.counter' "$STATE_FILE" 2>/dev/null; }

race() {   # race <mode> <iters>
  local mode="$1" iters="$2" p pids=()
  for ((p = 0; p < WRITERS; p++)); do
    bash "$WORKER" "$STATE_FILE" "$iters" "$mode" "$LIB" &
    pids+=("$!")
  done
  for p in "${pids[@]}"; do wait "$p"; done
}

echo "=============================================================="
echo "SK1-13 concurrency test  (writers=$WRITERS)"
echo "state file: $STATE_FILE"
echo "=============================================================="

# ---- A. UNLOCKED baseline: race MUST lose updates ----
reset_state
race unlocked "$UNLOCKED_ITERS"
got_unlocked="$(counter_now)"
exp_unlocked=$((WRITERS * UNLOCKED_ITERS))
echo "[A] unlocked: counter=$got_unlocked (no-loss would be $exp_unlocked)"
if [[ "$got_unlocked" =~ ^[0-9]+$ ]] && (( got_unlocked < exp_unlocked )); then
  pass "A unlocked baseline loses updates ($got_unlocked < $exp_unlocked) -> race is real"
else
  fail "A unlocked baseline did NOT show loss (got=$got_unlocked exp<$exp_unlocked) -- test cannot prove the fix"
fi

# ---- B. LOCKED: race MUST NOT lose a single update ----
reset_state
race locked "$LOCKED_ITERS"
got_locked="$(counter_now)"
exp_locked=$((WRITERS * LOCKED_ITERS))
echo "[B] locked: counter=$got_locked (expected exactly $exp_locked)"
if [[ "$got_locked" == "$exp_locked" ]]; then
  pass "B mkdir-mutex prevents lost updates (counter == $exp_locked)"
else
  fail "B lost update WITH lock (got=$got_locked expected=$exp_locked)"
fi
if [[ ! -e "${STATE_FILE}.lock" ]]; then
  pass "B lock dir released after all writers finished (no leftover lock)"
else
  fail "B lock dir leaked after writers finished"
fi

# ---- C. STALE lock is reclaimed (crashed-writer case): no hang ----
reset_state
mkdir "${STATE_FILE}.lock"
touch -t 202001010101 "${STATE_FILE}.lock"    # backdate mtime -> very stale
c_start=$SECONDS
( export ZHC_STATE_LOCK_STALE_SECS=120
  # shellcheck disable=SC1090
  source "$LIB"; state_set '.counter += 1' ) 2>/dev/null
c_elapsed=$((SECONDS - c_start))
got_c="$(counter_now)"
echo "[C] stale-lock reclaim: elapsed=${c_elapsed}s counter=$got_c"
if (( c_elapsed <= 5 )) && [[ "$got_c" == "1" ]] && [[ ! -e "${STATE_FILE}.lock" ]]; then
  pass "C stale lock reclaimed quickly (${c_elapsed}s), write landed, lock cleared"
else
  fail "C stale-lock handling wrong (elapsed=${c_elapsed}s counter=$got_c lock_present=$( [[ -e "${STATE_FILE}.lock" ]] && echo yes || echo no ))"
fi

# ---- D. Live-but-stuck lock is broken after the BOUNDED wait: no hang ----
# Fresh lock (NOT stale), so only the bounded-wait breaker can free it.
reset_state
mkdir "${STATE_FILE}.lock"                     # fresh mtime -> not "stale"
d_start=$SECONDS
( export ZHC_STATE_LOCK_WAIT_SECS=2 ZHC_STATE_LOCK_STALE_SECS=600
  # shellcheck disable=SC1090
  source "$LIB"; state_set '.counter += 1' ) 2>/dev/null
d_elapsed=$((SECONDS - d_start))
got_d="$(counter_now)"
echo "[D] bounded-wait break: elapsed=${d_elapsed}s counter=$got_d"
if (( d_elapsed >= 1 )) && (( d_elapsed <= 8 )) && [[ "$got_d" == "1" ]]; then
  pass "D non-stale stuck lock broken after bounded wait (${d_elapsed}s ~= 2s), no hang, write landed"
else
  fail "D bounded-wait breaker wrong (elapsed=${d_elapsed}s counter=$got_d)"
fi

# ---- E. wiring: every Skill-37 state writer sources the shared lib ----
wired_ok=1
for s in run-closeout.sh resume-closeout-cron.sh wire-n8n-closeout.sh \
         create-notion-closeout.sh send-telegram-celebration.sh \
         generate-visual-intelligence.sh send-operator-summary.sh \
         generate-infographics.sh upload-ghl-media.sh generate-celebration-video.sh; do
  if ! grep -q 'lib-closeout-state.sh' "$SCRIPT_DIR/$s"; then
    echo "    NOT wired: $s"
    wired_ok=0
  fi
done
if (( wired_ok == 1 )); then
  pass "E all 10 Skill-37 scripts source lib-closeout-state.sh"
else
  fail "E one or more scripts not wired to the shared lib"
fi

echo "=============================================================="
if (( fails == 0 )); then
  echo "RESULT: ALL PASS"
  exit 0
fi
echo "RESULT: $fails FAILURE(S)"
exit 1
