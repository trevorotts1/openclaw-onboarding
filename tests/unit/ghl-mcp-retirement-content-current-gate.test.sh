#!/usr/bin/env bash
# tests/unit/ghl-mcp-retirement-content-current-gate.test.sh
# ---------------------------------------------------------------------------
# DEFECT B3 (GHL-102). Two content-current early exits in update-skills.sh
# (the plain CONTENT RECHECK exit and the CONVERGENCE FAST PATH exit) used to
# `exit 0` BEFORE the wiring loop's retirement transaction, so an
# already-current box silently skipped the GHL community-MCP migration forever.
#
# CONTRACT PROVEN HERE
#   * both content-current exits call the SAME helper (_content_current_exit),
#     which calls the SAME function the full pass calls (wire_ghl_mcp) — one
#     code path, not a copy.
#   * the check runs BEFORE the temp tree is deleted (the delivered surfaces
#     are pruned, so the pulled bundle is the last resolver candidate).
#   * a failing check is LOUD and makes the content-current path exit 2
#     (non-zero), never 0.
#   * exactly once per process (idempotence latch), and an already-verified
#     retirement makes no second side effect.
#
# FIVE STATES: fresh install, ordinary upgrade, content-current rerun,
# interrupted migration (kill after staging, then rerun converges), idempotent
# repeat. Plus the two required negative controls.
#
# METHOD. The real wire_ghl_mcp / _content_current_exit functions are extracted
# VERBATIM from update-skills.sh (brace-matched, col-0 closing brace) and driven
# against stub `ghl-mcp-autostart.sh` / `ghl-mcp-assert-runtime.sh` in a
# throwaway box under $WORK. No network, no real ~/.openclaw, no real /data.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d -t ghl102-retirement-gate-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

extract_function() {
  awk -v fn="$1() {" '
    $0 == fn { p=1 }
    p { print }
    p && $0 == "}" { exit }
  ' "$UPDATER"
}

extract_function "wire_ghl_mcp"          > "$WORK/wire_ghl_mcp.inc"
extract_function "_content_current_exit" > "$WORK/content_current_exit.inc"
for f in wire_ghl_mcp content_current_exit; do
  [ -s "$WORK/$f.inc" ] || { echo "FATAL: could not extract $f() from update-skills.sh (drift?)"; exit 2; }
done
cat "$WORK/wire_ghl_mcp.inc" "$WORK/content_current_exit.inc" > "$WORK/functions.sh"
bash -n "$WORK/functions.sh" || { echo "FATAL: extracted functions do not parse"; exit 2; }

# ===========================================================================
# STATIC: one function, three reach points, defined before the early exits
# ===========================================================================
echo "== static: hoisted shared check, same code path on every exit =="
N_DEFS=$(grep -c '^wire_ghl_mcp() {' "$UPDATER")
[ "$N_DEFS" -eq 1 ] && ok "wire_ghl_mcp defined exactly once" || bad "wire_ghl_mcp defined $N_DEFS times (expected 1)"

N_EXITS=$(grep -c '^_content_current_exit() {' "$UPDATER")
[ "$N_EXITS" -eq 1 ] && ok "_content_current_exit defined exactly once" || bad "_content_current_exit defined $N_EXITS times (expected 1)"

CALLS=$(grep -c '^[[:space:]]*_content_current_exit$' "$UPDATER")
[ "$CALLS" -eq 2 ] && ok "exactly two content-current exit sites call _content_current_exit" \
  || bad "$CALLS call site(s) of _content_current_exit (expected 2 — plain recheck + fast path)"

grep -q '^  wire_ghl_mcp "36-ghl-mcp-setup"$' "$WORK/content_current_exit.inc" \
  && ok "_content_current_exit runs the SAME wire_ghl_mcp check (not a copy)" \
  || bad "_content_current_exit does not call wire_ghl_mcp \"36-ghl-mcp-setup\""

grep -q 'wire_ghl_mcp "\$SKILL_NAME"' "$UPDATER" \
  && ok "normal full path still calls wire_ghl_mcp from the wiring loop" \
  || bad "normal full path lost its wire_ghl_mcp call"

DEF_LINE=$(grep -n '^wire_ghl_mcp() {' "$UPDATER" | cut -d: -f1)
FIRST_CALL=$(grep -n '^[[:space:]]*_content_current_exit$' "$UPDATER" | head -1 | cut -d: -f1)
[ "$DEF_LINE" -lt "$FIRST_CALL" ] && ok "check is DEFINED ($DEF_LINE) before the first early-exit call ($FIRST_CALL)" \
  || bad "check defined at $DEF_LINE but called at $FIRST_CALL — would be 'command not found' on the early exit"

grep -q '_GHL_MCP_RETIREMENT_CHECKED' "$WORK/wire_ghl_mcp.inc" \
  && ok "wire_ghl_mcp carries the exactly-once latch" \
  || bad "wire_ghl_mcp has no exactly-once latch"

grep -q 'ghl-mcp-autostart.sh --retire' "$UPDATER" \
  && ok "retirement transaction still invoked from the shared function" \
  || bad "retirement transaction call vanished"

# The check must precede the temp-tree removal it replaces at each exit site.
grep -A1 -B1 '_content_current_exit$' "$UPDATER" | grep -q 'exit 0' \
  && bad "a raw 'exit 0' still sits beside a content-current call site" \
  || ok "no raw 'exit 0' remains at the replaced content-current exit sites"

# ===========================================================================
# FIXTURE: throwaway box
# ===========================================================================
BOX="$WORK/box"
ST="$WORK/state"
BIN="$WORK/bin"
HOME_FAKE="$WORK/home"
for d in "$BOX/scripts" "$BOX/bundle/scripts" "$ST" "$BIN" "$HOME_FAKE/.openclaw/scripts" \
         "$WORK/skills/06-ghl-install-pages" "$WORK/skills/38-conversational-ai-system" \
         "$WORK/skills/44-convert-and-flow-operator"; do
  mkdir -p "$d"
done
# Minimal PATH: no real `openclaw` CLI may be discovered.
for t in bash grep sed tr rm mkdir cat dirname basename; do
  ln -s "$(command -v "$t")" "$BIN/$t"
done

cat > "$BOX/scripts/ghl-mcp-autostart.sh" <<'STUB'
#!/usr/bin/env bash
set -u
STATE_DIR="${STUB_STATE_DIR:?}"
state="$(cat "$STATE_DIR/state" 2>/dev/null || echo fresh)"
case " $* " in
  *" --status "*)
    case "$state" in
      retired) echo "STATUS: ghl-mcp-autostart=RETIRED_VERIFIED_OFF" ;;
      running) echo "STATUS: ghl-mcp-autostart=STILL_RUNNING (name=com.clawd.ghl-mcp)" ;;
      staged)  echo "STATUS: ghl-mcp-autostart=MIGRATION_FAILED (stage=staged-partial)" ;;
      *)       echo "STATUS: ghl-mcp-autostart=NOT_APPLICABLE" ;;
    esac
    exit 0 ;;
  *" --retire "*)
    n=$(cat "$STATE_DIR/retire_calls" 2>/dev/null || echo 0); echo $((n+1)) > "$STATE_DIR/retire_calls"
    if [ "$state" = "retired" ]; then
      echo "STATUS: ghl-mcp-autostart=RETIRED_VERIFIED_OFF"; exit 0
    fi
    if [ -f "$STATE_DIR/interrupt_once" ]; then
      rm -f "$STATE_DIR/interrupt_once"
      echo staged > "$STATE_DIR/state"
      echo 1 > "$STATE_DIR/archive_count"
      echo "  [ghl-mcp-autostart] MIGRATION_FAILED (staged, killed before stop)"
      echo "STATUS: ghl-mcp-autostart=MIGRATION_FAILED (stage=staged-partial)"
      exit 1
    fi
    a=$(cat "$STATE_DIR/archive_count" 2>/dev/null || echo 0)
    if [ "$state" = "staged" ] && [ "$a" -ne 1 ]; then
      echo "  [ghl-mcp-autostart] MIGRATION_FAILED (corrupt: expected 1 staged archive, found $a)"
      echo "STATUS: ghl-mcp-autostart=MIGRATION_FAILED (stage=corrupt)"
      exit 1
    fi
    if [ "$state" != "staged" ]; then
      echo $((a+1)) > "$STATE_DIR/archive_count"
    fi
    echo retired > "$STATE_DIR/state"
    echo "STATUS: ghl-mcp-autostart=RETIRED_VERIFIED_OFF"
    exit 0 ;;
esac
exit 0
STUB

cat > "$BOX/scripts/ghl-mcp-assert-runtime.sh" <<'STUB'
#!/usr/bin/env bash
set -u
STATE_DIR="${STUB_STATE_DIR:?}"
n=$(cat "$STATE_DIR/assert_calls" 2>/dev/null || echo 0); echo $((n+1)) > "$STATE_DIR/assert_calls"
rc="$(cat "$STATE_DIR/assert_rc" 2>/dev/null || echo 0)"
if [ "$rc" = "0" ]; then
  echo "[ghl-mcp-runtime] VERDICT: RETIRED_OK"
else
  echo "[ghl-mcp-runtime] FAIL: name=com.clawd.ghl-mcp still loaded"
  echo "[ghl-mcp-runtime] VERDICT: STILL_RUNNING"
fi
exit "$rc"
STUB
chmod +x "$BOX/scripts/"*.sh
cp "$BOX/scripts/"*.sh "$BOX/bundle/scripts/"
mkdir -p "$WORK/pristine"
cp "$BOX/scripts/"*.sh "$WORK/pristine/"
printf '{"mcp":{"servers":{"ghl-mcp":{"command":"stub"}}}}\n' > "$BOX/openclaw.json"

reset_box() {  # reset_box <state> [assert_rc]
  rm -rf "$ST"; mkdir -p "$ST"
  printf '%s\n' "$1" > "$ST/state"
  printf '%s\n' "${2:-0}" > "$ST/assert_rc"
  printf '0\n' > "$ST/retire_calls"
  printf '0\n' > "$ST/assert_calls"
  rm -f "$ST/interrupt_once" "$ST/archive_count"
}

box_env() {
  export PATH="$BIN"
  export HOME="$HOME_FAKE"
  export STUB_STATE_DIR="$ST"
  export SKILLS_DIR="$WORK/skills"
  export OC_CONFIG="$BOX"
  export OC_PERSISTENT_SCRIPTS_DIR="$BOX/scripts"
  export ONBOARDING_DIR="$BOX/bundle"
  export LOG_FILE="$WORK/roll.log"
  export ONBOARDING_VERSION="v-test"
  export TEMP_EXTRACT="$WORK/temp-extract"
  export TEMP_ZIP="$WORK/temp.zip"
  mkdir -p "$TEMP_EXTRACT"; : > "$TEMP_ZIP"
  unset OC_PERSISTENT_CONFIG_DIR 2>/dev/null || true
}

# Runs the shared check as the FULL PASS does (direct wire_ghl_mcp call).
run_normal_path() {
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/functions.sh"
    box_env
    GHL_MCP_RUNTIME_FATAL="no"; GHL_MCP_RUNTIME_DETAIL=""; _GHL_MCP_RETIREMENT_CHECKED=0
    wire_ghl_mcp "36-ghl-mcp-setup" || true
    printf 'FATAL=%s\n' "${GHL_MCP_RUNTIME_FATAL:-no}"
  )
}

# Runs the shared check as BOTH content-current exits do.
run_content_current() {
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/functions.sh"
    box_env
    GHL_MCP_RUNTIME_FATAL="no"; GHL_MCP_RUNTIME_DETAIL=""; _GHL_MCP_RETIREMENT_CHECKED=0
    _content_current_exit
    echo "NEVER_REACHED"
  )
}

count() { cat "$ST/$1" 2>/dev/null || echo 0; }

# ===========================================================================
# STATE 1 — FRESH INSTALL (normal pass; no community MCP ever installed)
# ===========================================================================
echo ""
echo "== state 1: fresh install =="
reset_box fresh 2   # assert: NOT_APPLICABLE (rc 2)
OUT="$(run_normal_path 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "fresh install: normal path continues (rc=0)" || bad "fresh install rc=$RC: $OUT"
[ "$(count retire_calls)" = "1" ] && ok "fresh install: retirement transaction ran once (idempotent no-op)" \
  || bad "fresh install: retire_calls=$(count retire_calls) (expected 1): $OUT"
echo "$OUT" | grep -q 'FATAL=no' && ok "fresh install: no fatal latched (NOT_APPLICABLE is a skip, not a failure)" \
  || bad "fresh install latched a fatal: $OUT"

# ===========================================================================
# STATE 2 — ORDINARY UPGRADE (service still running, retirement succeeds)
# ===========================================================================
echo ""
echo "== state 2: ordinary upgrade =="
reset_box running 0
OUT="$(run_normal_path 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "ordinary upgrade: rc=0" || bad "ordinary upgrade rc=$RC: $OUT"
[ "$(count retire_calls)" = "1" ] && ok "ordinary upgrade: retirement ran exactly once" \
  || bad "ordinary upgrade: retire_calls=$(count retire_calls)"
echo "$OUT" | grep -q 'RETIRED and VERIFIED_OFF' && ok "ordinary upgrade: reports verified retirement" \
  || bad "ordinary upgrade: missing verified-retirement message: $OUT"
echo "$OUT" | grep -q 'FATAL=no' && ok "ordinary upgrade: no fatal latched" || bad "ordinary upgrade latched a fatal: $OUT"

# ===========================================================================
# STATE 3 — CONTENT-CURRENT RERUN (early exit; delivered surfaces pruned)
# ===========================================================================
echo ""
echo "== state 3: content-current rerun (the B3 path) =="
reset_box retired 0
# Mirror the real roll: prune_retired_ghl_mcp_surfaces removes the delivered
# copies BEFORE the content recheck, so the check must resolve from the pulled
# bundle — i.e. it must run BEFORE TEMP_EXTRACT is deleted.
rm -f "$BOX/scripts/"ghl-mcp-*.sh
OUT="$(run_content_current 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "content-current rerun: exits 0 when already verified" || bad "content-current rerun rc=$RC: $OUT"
echo "$OUT" | grep -q 'NEVER_REACHED' && bad "content-current exit did not fire" || ok "content-current exit fired (no fall-through)"
echo "$OUT" | grep -q 'already RETIRED (VERIFIED_OFF)' && ok "content-current rerun: retirement check actually RAN" \
  || bad "content-current rerun did not run the retirement check: $OUT"
[ "$(count retire_calls)" = "0" ] && ok "content-current rerun: no retire side effect on an already-retired box" \
  || bad "content-current rerun: retire_calls=$(count retire_calls) (expected 0)"
[ "$(count assert_calls)" = "1" ] && ok "content-current rerun: runtime assertion ran once" \
  || bad "content-current rerun: assert_calls=$(count assert_calls) (expected 1)"
[ ! -d "$WORK/temp-extract" ] && ok "content-current rerun: temp tree cleaned up as before" \
  || bad "content-current rerun: temp tree left behind"

# ===========================================================================
# STATE 4 — INTERRUPTED MIGRATION (kill after staging, rerun must converge)
# ===========================================================================
echo ""
echo "== state 4: interrupted migration =="
reset_box running 0
: > "$ST/interrupt_once"
OUT="$(run_content_current 2>&1)"; RC=$?
[ "$RC" -ne 0 ] && ok "interrupted migration: loud non-zero (rc=$RC), never 0" \
  || bad "interrupted migration: exited 0 — silent skip of a failed migration"
[ "$RC" -eq 2 ] && ok "interrupted migration: exit 2 = content current, infrastructure needs attention" \
  || bad "interrupted migration: rc=$RC (expected 2)"
echo "$OUT" | grep -q 'MIGRATION_FAILED' && ok "interrupted migration: failure is named loudly" \
  || bad "interrupted migration: no MIGRATION_FAILED banner: $OUT"
OUT2="$(run_content_current 2>&1)"; RC2=$?
[ "$RC2" -eq 0 ] && ok "rerun after interruption: converges and exits 0" || bad "rerun after interruption rc=$RC2: $OUT2"
[ "$(count state)" = "retired" ] || [ "$(cat "$ST/state")" = "retired" ] && ok "rerun after interruption: box converged to retired" \
  || bad "rerun after interruption: state=$(cat "$ST/state")"
[ "$(count archive_count)" = "1" ] && ok "rerun after interruption: no duplicate/corrupt archive (count=1)" \
  || bad "rerun after interruption: archive_count=$(count archive_count) (expected 1)"

# ===========================================================================
# STATE 5 — IDEMPOTENT REPEAT (+ exactly-once latch inside one process)
# ===========================================================================
echo ""
echo "== state 5: idempotent repeat =="
BEFORE_RETIRE=$(count retire_calls)
OUT="$(run_content_current 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "idempotent repeat: exits 0" || bad "idempotent repeat rc=$RC: $OUT"
[ "$(count retire_calls)" = "$BEFORE_RETIRE" ] && ok "idempotent repeat: no second retirement side effect" \
  || bad "idempotent repeat: retire_calls moved $BEFORE_RETIRE -> $(count retire_calls)"

reset_box running 0
OUT="$(
  set -euo pipefail
  # shellcheck source=/dev/null
  source "$WORK/functions.sh"
  box_env
  GHL_MCP_RUNTIME_FATAL="no"; GHL_MCP_RUNTIME_DETAIL=""; _GHL_MCP_RETIREMENT_CHECKED=0
  wire_ghl_mcp "36-ghl-mcp-setup"
  wire_ghl_mcp "36-ghl-mcp-setup"
  echo done
)" 2>&1
[ "$(count retire_calls)" = "1" ] && ok "two calls in one process run the transaction exactly once" \
  || bad "two calls in one process ran the transaction $(count retire_calls) times (expected 1)"
echo "$OUT" | grep -q 'already checked in this run' && ok "second call reports the exactly-once skip (visible, not silent)" \
  || bad "second call did not report the exactly-once skip: $OUT"

# ===========================================================================
# NEGATIVE CONTROL (a) — retirement check forcibly FAILS in content-current mode
# ===========================================================================
echo ""
echo "== negative control (a): forcible retirement failure in content-current mode =="
reset_box running 1   # assertion says STILL_RUNNING even though retire claimed success
OUT="$(run_content_current 2>&1)"; RC=$?
[ "$RC" -ne 0 ] && ok "content-current mode is NON-ZERO when the retirement check fails (rc=$RC)" \
  || bad "content-current mode exited 0 despite a failed retirement check"
[ "$RC" -eq 2 ] && ok "failure maps to exit 2 (content current, infrastructure needs attention)" \
  || bad "failure mapped to rc=$RC (expected 2)"
echo "$OUT" | grep -q 'ASSERTION FAILED' && ok "failure is loud (ASSERTION FAILED banner on stderr)" \
  || bad "failure banner missing: $OUT"
echo "$OUT" | grep -q 'exiting 2, never 0' && ok "failure states the exit contract explicitly" \
  || bad "failure did not state the exit contract: $OUT"

# Also: a missing retirement tool must fail loudly, not silently pass.
reset_box retired 0
rm -f "$BOX/scripts/ghl-mcp-autostart.sh" "$BOX/bundle/scripts/ghl-mcp-autostart.sh" "$HOME_FAKE/.openclaw/scripts/ghl-mcp-autostart.sh"
OUT="$(run_content_current 2>&1)"; RC=$?
[ "$RC" -eq 2 ] && ok "missing retirement tool: content-current mode exits 2, never 0" \
  || bad "missing retirement tool exited $RC (expected 2): $OUT"
echo "$OUT" | grep -q 'ghl-mcp-autostart.sh not found' && ok "missing retirement tool is named loudly" \
  || bad "missing retirement tool not named: $OUT"

# ===========================================================================
# NEGATIVE CONTROL (b) — already verified => no second side effect
# ===========================================================================
echo ""
echo "== negative control (b): retirement already verified makes no second side effect =="
cp "$WORK/pristine/ghl-mcp-autostart.sh" "$BOX/scripts/ghl-mcp-autostart.sh"
cp "$WORK/pristine/ghl-mcp-assert-runtime.sh" "$BOX/scripts/ghl-mcp-assert-runtime.sh"
reset_box retired 0
printf 'retired\n' > "$ST/state"
BEFORE=$(count retire_calls)
run_content_current >/dev/null 2>&1; RC=$?
[ "$RC" -eq 0 ] && ok "verified-retired rerun exits 0" || bad "verified-retired rerun rc=$RC"
[ "$(count retire_calls)" = "$BEFORE" ] && ok "verified-retired rerun: --retire NOT invoked (zero second side effects)" \
  || bad "verified-retired rerun invoked --retire ($BEFORE -> $(count retire_calls))"
[ "$(count archive_count)" = "0" ] && ok "verified-retired rerun: no new archive written" \
  || bad "verified-retired rerun wrote archive_count=$(count archive_count)"

# ===========================================================================
echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
