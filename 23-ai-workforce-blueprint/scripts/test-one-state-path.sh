#!/usr/bin/env bash
# test-one-state-path.sh — BU-80 (WF-097, WF-022): every script resolves the
# build-state file through the same override order.
#
# For each script: HOME is redirected into a scratch fixture,
# WORKFORCE_BUILD_STATE_FILE names a scratch state path, and the script is run
# down its CHEAPEST path — a state that makes it exit early, never --help.
# Assertion: the script's output (its log tees to stdout, so the captured output
# IS the log) names that exact scratch path.
#
# Hermetic: HOME is a mktemp dir inside TMPDIR; a host that carries
# /data/.openclaw would make the scripts prefer it over HOME and the redirect
# would prove nothing, so the suite refuses to run there. No client box, no
# ~/.openclaw, no network.
#
# USAGE: bash test-one-state-path.sh
# EXIT:  0 = all assertions pass, 1 = one or more failed

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLOSEOUT_DIR="$(cd "$SKILL_DIR/../37-zhc-closeout/scripts" && pwd)"

PASS=0
FAIL=0

ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad() { echo "  FAIL: $1" >&2; FAIL=$((FAIL + 1)); }

for _bin in python3 jq; do
  command -v "$_bin" >/dev/null 2>&1 || { echo "SKIP: $_bin not installed" >&2; exit 0; }
done

if [ -d /data/.openclaw ]; then
  echo "FATAL: /data/.openclaw exists — the scripts would resolve there and a HOME" >&2
  echo "       override cannot redirect it. Refusing to run to protect a live workspace." >&2
  exit 1
fi

FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/one-state-path-fixture.XXXXXX")"
cleanup() { [ -n "${FIXTURE_ROOT:-}" ] && rm -rf "$FIXTURE_ROOT"; }
trap cleanup EXIT

FIX_HOME="$FIXTURE_ROOT/home"
mkdir -p "$FIX_HOME/.openclaw/workspace/departments/marketing/00-director-of-marketing" \
         "$FIX_HOME/.openclaw/logs"
# A minimal live workforce tree, so verify-library-gate's qc pass resolves a
# company and writes its artifact instead of short-circuiting as "no workforce".
printf '# Director of Marketing how-to\n\nThis role executes its SOP deterministically.\n' \
  > "$FIX_HOME/.openclaw/workspace/departments/marketing/00-director-of-marketing/how-to.md"

SCRATCH_STATE="$FIXTURE_ROOT/scratch-build-state.json"   # deliberately absent

# run_case <label> <expected-rc|any> <script-path> [args...]
run_case() {
  local label="$1" want_rc="$2"; shift 2
  local out="$FIXTURE_ROOT/$label.out"
  HOME="$FIX_HOME" WORKFORCE_BUILD_STATE_FILE="$SCRATCH_STATE" \
    bash "$@" >"$out" 2>&1
  local rc=$?
  case "$(cat "$out")" in
    *"$SCRATCH_STATE"*) ok "$label names \$WORKFORCE_BUILD_STATE_FILE" ;;
    *) bad "$label — output/log did not name $SCRATCH_STATE"
       sed 's/^/        | /' "$out" >&2 ;;
  esac
  if [ "$want_rc" = "any" ]; then
    if [ "$rc" -ne 127 ]; then
      ok "$label exited on a real path (rc=$rc)"
    else
      bad "$label — shell abort rc=127 (unresolvable command or interpreter)"
    fi
  elif [ "$rc" = "$want_rc" ]; then
    ok "$label exits early (rc=$rc)"
  else
    bad "$label — expected early exit rc=$want_rc, got rc=$rc"
    sed 's/^/        | /' "$out" >&2
  fi
  # never let one script's lock or log steer the next one
  rm -f "$FIX_HOME/.openclaw/workspace/.closeout-watchdog.lock" \
        "$FIX_HOME/.openclaw/workspace/.closeout-resume.lock"
}

echo "=============================================================="
echo "one state-file rule (BU-80 / WF-097, WF-022)"
echo "fixture: $FIXTURE_ROOT"
echo "scratch state: $SCRATCH_STATE (absent on purpose)"
echo "=============================================================="

echo ""
echo "[1] verify-zhc-standard.sh — no state file -> rc 7"
run_case "verify-zhc-standard" 7 "$SCRIPT_DIR/verify-zhc-standard.sh"

echo ""
echo "[2] verify-wiring.sh — no state file -> rc 9"
run_case "verify-wiring" 9 "$SCRIPT_DIR/verify-wiring.sh"

echo ""
echo "[3] send-presentation-dept-welcome.sh — no state file -> rc 9"
run_case "send-presentation-dept-welcome" 9 "$SCRIPT_DIR/send-presentation-dept-welcome.sh"

echo ""
echo "[4] retire-confirmed-decline.sh — no state file -> rc 2"
run_case "retire-confirmed-decline" 2 "$SCRIPT_DIR/retire-confirmed-decline.sh" --dept marketing

echo ""
echo "[5] verify-library-gate.sh — no state file -> verdict only (any real rc)"
run_case "verify-library-gate" any "$SCRIPT_DIR/verify-library-gate.sh"

echo ""
echo "[6] run-closeout.sh — no state file -> rc 1"
run_case "run-closeout" 1 "$CLOSEOUT_DIR/run-closeout.sh"

echo ""
echo "[7] resume-closeout-cron.sh — no state file -> rc 0"
run_case "resume-closeout-cron" 0 "$CLOSEOUT_DIR/resume-closeout-cron.sh"

echo ""
echo "[8] closeout-readiness-watchdog.sh --local — no state file -> rc 0"
run_case "closeout-readiness-watchdog" 0 "$SCRIPT_DIR/closeout-readiness-watchdog.sh" --local

echo ""
echo "=============================================================="
echo "assertions: $PASS passed, $FAIL failed"
echo "=============================================================="
[[ $FAIL -eq 0 ]] || exit 1
exit 0
