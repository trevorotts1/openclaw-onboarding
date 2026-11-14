#!/usr/bin/env bash
# test-wiring-reads-slug-entries.sh — wiring-gate roster-and-state reading suite
#
# This file carries TWO regression suites that live together because both prove the
# same gate reads a live workforce the way the box actually stores it. The helpers
# below are shared; each case is labelled with the unit that owns it.
#
# ---------------------------------------------------------------------------
# SUITE 1 — BU-75 (WF-093, WF-089): a department is not always registered under
# the agent id "dept-<slug>". A box may carry the department under an
# owner-chosen id ("marketing-lead") whose workspace IS the department folder.
# The gate used to look for "dept-<slug>" only, so that department failed
# REGISTERED (exit 3) and its runtime-dir check looked at the wrong agent id — a
# fully wired department reported as broken. The workspace the roster entry
# points at is the identity that matters.
#
# Cases here:
#   1A. canonical id: agents.entries has "dept-marketing" -> exit 0 (baseline,
#       the behaviour that already worked must not change)
#   1B. another id:   agents.entries has "marketing-lead" whose workspace is the
#       marketing folder, and agents/marketing-lead/ exists -> exit 0, and the
#       gate prints "registered as marketing-lead"
#   1C. negative control: "marketing-lead" whose workspace is a DIFFERENT folder
#       -> still exit 3 (the match is workspace identity, not "any entry")
#
# ---------------------------------------------------------------------------
# SUITE 2 — BU-51 (WF-072): a .workforce-build-state.json department entry may
# be keyed by `slug` instead of `id`. The wiring gate used to read ONLY `.id`,
# so a slug-keyed state file produced an empty department list and hit the
# "schema mismatch" abort (exit 9) even though every department was fully
# materialised on disk. Worse, the state write-back keyed the per-dept results
# on `$d.id`, so a slug-keyed entry never received its `wiringStatus`.
# The gate now reads `.id // .slug` in both places.
#
# Cases here:
#   2A. departments: [{"slug":"marketing"}] -> exit 0, wiringStatus == "done"
#   2B. departments: [{"id":"marketing"}]   -> exit 0, wiringStatus == "done"
#   2C. departments: [{"name":"x"}]         -> still exit 9 (neither key: refuse)
#
# ---------------------------------------------------------------------------
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
# case B shapes (alternate roster id, slug-keyed state) genuinely fail before the
# change and pass after it.
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

FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/wiring-roster-fixture.XXXXXX")"
cleanup() { [[ -n "${FIXTURE_ROOT:-}" && -d "$FIXTURE_ROOT" ]] && rm -rf "$FIXTURE_ROOT"; }
trap cleanup EXIT

FIX_HOME="$FIXTURE_ROOT/home"
OC="$FIX_HOME/.openclaw"
WS="$OC/workspace"
DEPTS="$WS/departments"
STATE_FILE="$WS/.workforce-build-state.json"
OC_CFG="$OC/openclaw.json"

GATE_OUT=""
GATE_RC=""

# ---- shared helpers ----------------------------------------------------------
# materialize_marketing — one director-class role with a substantive how-to.md
# (>= HOW_TO_MIN_BYTES 3072, no unfilled-stub marker), so a case's exit 0 can
# only come from the checks under test passing.
materialize_marketing() {
  mkdir -p "$DEPTS/marketing/00-director-of-marketing"
  { printf '# Director of Marketing how-to\n\n## Section 9 SOPs\n'
    for _i in $(seq 1 60); do
      printf 'This role executes its standard operating procedure deterministically. '
      printf 'Step %s is recorded in the department activity log for audit.\n' "$_i"
    done
  } > "$DEPTS/marketing/00-director-of-marketing/how-to.md"
}

# write_fixture_secrets — the marketing connection-manifest requires two keys.
# Supplying obvious test values inside the fixture keeps the CONNECTION check
# passing, so these cases measure REGISTRATION and STATE READING only (no
# ambient env is relied on: the gate's own dotenv lookup expands "~" against the
# fixture HOME).
write_fixture_secrets() {
  mkdir -p "$OC/secrets"
  {
    printf 'GOHIGHLEVEL_API_KEY=test-value-not-a-real-credential-0001\n'
    printf 'GOHIGHLEVEL_LOCATION_ID=test-location-not-a-real-credential-0002\n'
  } > "$OC/secrets/.env"
}

# reset_fixture <roster-json> <agent-dir-name> [departments-json]
# A self-contained OpenClaw root: the roster is exactly the JSON the caller
# passes, the runtime agent dir named by the caller exists, and the state file
# names `marketing` in the caller's department shape (default: the id-keyed
# shape every builder writes).
reset_fixture() {
  local roster="$1" agent_dir_name="$2"
  local departments="${3:-}"
  [[ -n "$departments" ]] || departments='[{"id":"marketing","status":"done"}]'
  rm -rf "$FIX_HOME"
  mkdir -p "$OC/agents" "$DEPTS/marketing" "$OC/agents/$agent_dir_name"
  write_fixture_secrets
  printf '%s\n' "$roster" > "$OC_CFG"
  printf '%s\n' "{\"workspaceRoot\":\"$WS\",\"departments\":$departments}" > "$STATE_FILE"
  materialize_marketing
}

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

expect_output_contains() {
  local needle="$1" label="$2"
  if printf '%s' "$GATE_OUT" | grep -qF -- "$needle"; then
    ok "$label"
  else
    bad "$label — output did not contain: $needle"
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
echo "verify-wiring.sh roster reading (BU-75 / WF-093, WF-089)"
echo "             + slug-keyed state reading (BU-51 / WF-072)"
echo "fixture: $FIXTURE_ROOT"
echo "=============================================================="

# ==============================================================================
# SUITE 1 — roster reading (BU-75)
# ==============================================================================

# --- 1A: the canonical dept-<slug> id still registers --------------------------
echo ""
echo "[1A] agents.entries: dept-marketing -> the marketing folder"
reset_fixture '{"agents":{"entries":{"dept-marketing":{"workspace":"'"$DEPTS"'/marketing"}}}}' "dept-marketing"
run_gate
expect_rc "a canonical dept-<slug> entry still passes" 0
expect_wiring_status "done" "the department receives its wiring status"

# --- 1B: registered under another id, matched by its workspace -----------------
# The spec's case: roster entry `marketing-lead` whose workspace is the marketing
# folder, with agents/marketing-lead/ present -> exit 0.
echo ""
echo "[1B] agents.entries: marketing-lead (workspace = the marketing folder)"
reset_fixture '{"agents":{"entries":{"marketing-lead":{"workspace":"'"$DEPTS"'/marketing"}}}}' "marketing-lead"
run_gate
expect_rc "a department registered under another agent id passes" 0
expect_output_contains "registered as marketing-lead" "the gate names the id it accepted"
expect_wiring_status "done" "the department registered under another id is marked wired"

# --- 1C: negative control — a different workspace is not a match ---------------
echo ""
echo "[1C] agents.entries: marketing-lead -> a DIFFERENT department folder"
reset_fixture '{"agents":{"entries":{"marketing-lead":{"workspace":"'"$DEPTS"'/other"}}}}' "marketing-lead"
mkdir -p "$DEPTS/other"
run_gate
expect_rc "an entry serving a different folder is still not this department's registration" 3
expect_output_contains "not found in openclaw.json" "the gate still fails the registration loudly"
expect_wiring_status "failed" "the unwired department is marked failed, not wired"

# ==============================================================================
# SUITE 2 — slug-keyed state entries (BU-51)
# ==============================================================================

# --- 2A: a department entry keyed by slug --------------------------------------
echo ""
echo "[2A] departments: [{\"slug\":\"marketing\",\"status\":\"done\"}]"
reset_fixture '{"agents":{"list":[{"id":"dept-marketing","workspace":"'"$DEPTS"'/marketing"}]}}' "dept-marketing" \
  '[{"slug":"marketing","status":"done"}]'
run_gate
expect_rc "a slug-keyed department is read, not rejected as a schema mismatch" 0
expect_wiring_status "done" "the slug-keyed entry receives its wiring status"

# --- 2B: the unchanged shape, keyed by id --------------------------------------
echo ""
echo "[2B] departments: [{\"id\":\"marketing\"}]"
reset_fixture '{"agents":{"list":[{"id":"dept-marketing","workspace":"'"$DEPTS"'/marketing"}]}}' "dept-marketing" \
  '[{"id":"marketing"}]'
run_gate
expect_rc "an id-keyed department still passes (no regression)" 0
expect_wiring_status "done" "the id-keyed entry still receives its wiring status"

# --- 2C: neither key — still refuse -------------------------------------------
# Anti-regression: accepting .slug must not become accepting anything. An entry
# carrying neither .id nor .slug is a schema mismatch and must still abort loudly.
echo ""
echo "[2C] departments: [{\"name\":\"x\"}]"
reset_fixture '{"agents":{"list":[{"id":"dept-marketing","workspace":"'"$DEPTS"'/marketing"}]}}' "dept-marketing" \
  '[{"name":"x"}]'
run_gate
expect_rc "an entry with neither .id nor .slug still aborts as a schema mismatch" 9
expect_output_contains "neither .id nor .slug" "the abort names both fields"
expect_wiring_status "absent" "nothing is written for an entry that carries no key"

echo ""
echo "=============================================================="
echo "assertions: $PASS passed, $FAIL failed"
echo "=============================================================="
[[ $FAIL -eq 0 ]] || exit 1
exit 0
