#!/usr/bin/env bash
# test-wiring-reads-slug-entries.sh — regression suite for BU-51 (WF-072)
#
# A .workforce-build-state.json department entry may be keyed by `slug` instead
# of `id`. The wiring gate used to read ONLY `.id`, so a slug-keyed state file
# produced an empty department list and hit the "schema mismatch" abort (exit 9)
# even though every department was fully materialised on disk. Worse, the state
# write-back keyed the per-dept results on `$d.id`, so a slug-keyed entry never
# received its `wiringStatus`.
#
# The gate now reads `.id // .slug` in both places. Proven here in BOTH shapes:
#   A. departments: [{"slug":"marketing"}] -> exit 0, wiringStatus == "done"
#   B. departments: [{"id":"marketing"}]   -> exit 0, wiringStatus == "done"
#   C. departments: [{"name":"x"}]         -> still exit 9 (neither key: refuse)
#
# HERMETIC: HOME is redirected into the fixture, so every path the gate resolves
# stays inside $FIXTURE_ROOT. The suite refuses to run if /data/.openclaw exists
# on this host (the gate prefers it over $HOME/.openclaw). No client box, no
# ~/.openclaw, no network.
#
# USAGE: bash test-wiring-reads-slug-entries.sh
# EXIT:  0 = all assertions pass, 1 = one or more failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# WIRING_GATE_UNDER_TEST lets a reviewer point this suite at a DIFFERENT copy of
# the gate — specifically the pre-fix copy from origin/main — to confirm the
# slug-keyed cases genuinely fail before the change and pass after it.
GATE="${WIRING_GATE_UNDER_TEST:-$SCRIPT_DIR/verify-wiring.sh}"

PASS=0
FAIL=0

ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }

# ---- preconditions -----------------------------------------------------------
for _bin in jq python3; do
  command -v "$_bin" >/dev/null 2>&1 || { echo "SKIP: $_bin not installed" >&2; exit 0; }
done
[[ -f "$GATE" ]] || { echo "FATAL: gate not found at $GATE" >&2; exit 1; }

# HERMETIC GUARD 1: verify-wiring.sh prefers /data/.openclaw over $HOME/.openclaw.
if [[ -d /data/.openclaw ]]; then
  echo "FATAL: /data/.openclaw exists — the gate would resolve there and a HOME" >&2
  echo "       override cannot redirect it. Refusing to run to protect a live workspace." >&2
  exit 1
fi

FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/wiring-slug-fixture.XXXXXX")"
cleanup() { [[ -n "${FIXTURE_ROOT:-}" && -d "$FIXTURE_ROOT" ]] && rm -rf "$FIXTURE_ROOT"; }
trap cleanup EXIT

FIX_HOME="$FIXTURE_ROOT/home"
OC="$FIX_HOME/.openclaw"
WS="$OC/workspace"
DEPTS="$WS/departments"
STATE_FILE="$WS/.workforce-build-state.json"
OC_CFG="$OC/openclaw.json"

# ---- fixture builder ---------------------------------------------------------
# reset_fixture <departments-json> — a self-contained OpenClaw root whose state
# file names `marketing` in exactly the shape the caller passes.
reset_fixture() {
  local departments="$1"
  rm -rf "$FIX_HOME"
  mkdir -p "$OC/agents" "$DEPTS/marketing" "$OC/agents/dept-marketing"
  printf '%s\n' '{"agents":{"list":[{"id":"dept-marketing","workspace":"'"$DEPTS"'/marketing"}]}}' \
    > "$OC_CFG"
  printf '%s\n' "{\"workspaceRoot\":\"$WS\",\"departments\":$departments}" > "$STATE_FILE"
  # A fully materialised department: one director-class role with a substantive
  # how-to.md (>= HOW_TO_MIN_BYTES 3072, no unfilled-stub marker).
  mkdir -p "$DEPTS/marketing/00-director-of-marketing"
  { printf '# Director of Marketing how-to\n\n## Section 9 SOPs\n'
    for _i in $(seq 1 60); do
      printf 'This role executes its standard operating procedure deterministically. '
      printf 'Step %s is recorded in the department activity log for audit.\n' "$_i"
    done
  } > "$DEPTS/marketing/00-director-of-marketing/how-to.md"
}

GATE_OUT=""
GATE_RC=""
run_gate() {
  # HERMETIC GUARD 2: assert the resolved root is inside the fixture.
  case "$OC" in
    "$FIXTURE_ROOT"/*) : ;;
    *) echo "FATAL: resolved OpenClaw root $OC is outside $FIXTURE_ROOT" >&2; exit 1 ;;
  esac
  HOME="$FIX_HOME" bash "$GATE" --dept marketing > "$FIXTURE_ROOT/gate-out.txt" 2>&1
  GATE_RC=$?
  GATE_OUT="$(cat "$FIXTURE_ROOT/gate-out.txt")"
}

expect_rc() {
  local label="$1" want="$2"
  if [[ "$GATE_RC" == "$want" ]]; then
    ok "$label (rc=$GATE_RC)"
  else
    bad "$label — expected rc=$want, got rc=$GATE_RC"
    printf '%s\n' "$GATE_OUT" | sed 's/^/        | /' >&2
  fi
}

# expect_wiring_status <want> <label> — the state file's single department entry.
expect_wiring_status() {
  local want="$1" label="$2" got
  got="$(jq -r '(.departments // [])[0].wiringStatus // "absent"' "$STATE_FILE" 2>/dev/null)"
  if [[ "$got" == "$want" ]]; then
    ok "$label (wiringStatus=$got)"
  else
    bad "$label — expected wiringStatus=$want, got $got"
    printf '%s\n' "$(cat "$STATE_FILE")" | sed 's/^/        | /' >&2
  fi
}

echo "=============================================================="
echo "verify-wiring.sh slug-keyed department entries (BU-51 / WF-072)"
echo "fixture: $FIXTURE_ROOT"
echo "=============================================================="

# --- A: a department entry keyed by slug --------------------------------------
echo ""
echo "[A] departments: [{\"slug\":\"marketing\",\"status\":\"done\"}]"
reset_fixture '[{"slug":"marketing","status":"done"}]'
run_gate
expect_rc "a slug-keyed department is read, not rejected as a schema mismatch" 0
expect_wiring_status "done" "the slug-keyed entry receives its wiring status"

# --- B: the unchanged shape, keyed by id --------------------------------------
echo ""
echo "[B] departments: [{\"id\":\"marketing\"}]"
reset_fixture '[{"id":"marketing"}]'
run_gate
expect_rc "an id-keyed department still passes (no regression)" 0
expect_wiring_status "done" "the id-keyed entry still receives its wiring status"

# --- C: neither key — still refuse -------------------------------------------
# Anti-regression: accepting .slug must not become accepting anything. An entry
# carrying neither .id nor .slug is a schema mismatch and must still abort loudly.
echo ""
echo "[C] departments: [{\"name\":\"x\"}]"
reset_fixture '[{"name":"x"}]'
run_gate
expect_rc "an entry with neither .id nor .slug still aborts as a schema mismatch" 9
if printf '%s' "$GATE_OUT" | grep -qF "neither .id nor .slug"; then
  ok "the abort names both fields"
else
  bad "the abort did not say 'neither .id nor .slug'"
  printf '%s\n' "$GATE_OUT" | sed 's/^/        | /' >&2
fi
expect_wiring_status "absent" "nothing is written for an entry that carries no key"

echo ""
echo "=============================================================="
echo "assertions: $PASS passed, $FAIL failed"
echo "=============================================================="
[[ $FAIL -eq 0 ]] || exit 1
exit 0
