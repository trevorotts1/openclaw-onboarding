#!/usr/bin/env bash
# tests/unit/presentation-schedules-installed.test.sh
#
# CI guard for F12a/F12b — "install and arm the self-healing layer fleet-wide".
#
# THE DEFECT THIS LOCKS. presentation-watchdog.sh carries the ONLY automated
# recovery this department has: the stall watchdog, the board reconcile, the
# SUPERVISOR (an engine process that dies behind an active run is detected and,
# in apply mode, restarted under a bounded backed-off budget) and run-discovery.
# Nothing in this repository had ever SCHEDULED it. Measured at v25.0.11
# (ea331f82a) with python3 str.count over the full file text — not grep:
#
#     install.sh        'presentation-watchdog' 0    'supervisor' 0
#                       CONTROL 'presentation-intake-poll' 25  (non-empty on the
#                       same instrument and the same file: the check is sound)
#     update-skills.sh  'presentation-watchdog' 0    'presentation-intake-poll' 0
#                       CONTROL 'watchdog' 2, 'supervise' 1     (non-empty)
#
# So no client box had stall detection or restart, and a fleet ROLL could repair
# NEITHER scheduler — the poller's installer was defined inline in install.sh
# where update-skills.sh could never reach it. Every parked deck needed a human.
#
# WHAT THIS PROVES, in both directions:
#   (A) SHARED LIB    -- lib-presentation-schedules.sh defines BOTH installers
#                        and the roll entry point, in ONE place.
#   (B) NO DRIFT      -- install.sh sources it and no longer defines the poller
#                        installer inline (the condition that made it unreachable).
#   (C) INSTALL PATH  -- install.sh actually CALLS install_watchdog_schedule.
#   (D) ROLL PATH     -- update-skills.sh sources the lib and calls
#                        install_presentation_schedules (both schedulers).
#   (E) RENDER        -- functional: the Mac branch writes a VALID LaunchAgent
#                        with the scheduler contract (label, argv, 600s, log,
#                        SCAN_ROOT, PATH, notify transport).
#   (F) F12c NOT ARMED-- PRESENTATION_SUPERVISE_APPLY is ABSENT by default
#                        (supervisor report-only), PRESENT when the operator
#                        exports it, and PRESERVED across a re-run so a roll can
#                        neither arm what an operator did not nor disarm what
#                        they did.
#   (G) NO FABRICATION-- OWNER_CHAT_ID is rendered only from a resolved NUMERIC
#                        source; a non-numeric one is discarded, not shipped.
#   (H) IDEMPOTENT    -- two runs leave one valid plist, reloaded, not stacked.
#   (I) VPS BRANCH    -- registers exactly ONE */10 SILENT main-session cron
#                        named presentation-watchdog, with no client-facing
#                        flag, and the second run registers none.
#   (J) DISCRIMINATES -- with presentation-watchdog.sh absent the installer
#                        RETURNS NONZERO and writes NO plist. A guard that
#                        passes on everything is worth nothing; this is the
#                        known-good negative control for (E)-(H).
#
# Fully sandboxed: HOME=mktemp, a stub launchctl and a mock openclaw on PATH.
# It never loads a real LaunchAgent, never registers a real cron and never
# touches a real ~/.openclaw.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
SCHED_LIB="$REPO_ROOT/lib-presentation-schedules.sh"
DEPT_SRC="$REPO_ROOT/23-ai-workforce-blueprint/templates/role-library/presentations/scripts"

SANDBOX="$(mktemp -d)"
export HOME="$SANDBOX/home"
mkdir -p "$HOME"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

echo "=== presentation-schedules-installed.test.sh ==="
echo "  sandbox: $SANDBOX"
echo ""

# ---------------------------------------------------------------------------
# (A) SHARED LIB — one home for both installers
# ---------------------------------------------------------------------------
echo "--- (A) SHARED LIB ---"
if [ -f "$SCHED_LIB" ]; then
  pass "A1: lib-presentation-schedules.sh exists"
else
  fail "A1: lib-presentation-schedules.sh MISSING at $SCHED_LIB — neither scheduler has a shared home"
fi
for fn in install_intake_poll_schedule install_watchdog_schedule install_presentation_schedules; do
  if [ -f "$SCHED_LIB" ] && grep -q "^${fn}() {" "$SCHED_LIB"; then
    pass "A2: lib defines ${fn}()"
  else
    fail "A2: lib does NOT define ${fn}()"
  fi
done
if [ -f "$SCHED_LIB" ] && bash -n "$SCHED_LIB" 2>/dev/null; then
  pass "A3: lib passes bash -n"
else
  fail "A3: lib fails bash -n (or is missing)"
fi

# ---------------------------------------------------------------------------
# (B) NO DRIFT — install.sh sources it, does not re-define it
# ---------------------------------------------------------------------------
echo ""
echo "--- (B) NO DRIFT: install.sh sources the lib, defines nothing inline ---"
if grep -q 'lib-presentation-schedules.sh' "$INSTALL_SH"; then
  pass "B1: install.sh sources lib-presentation-schedules.sh"
else
  fail "B1: install.sh does NOT source lib-presentation-schedules.sh"
fi
if grep -q '^install_intake_poll_schedule() {' "$INSTALL_SH"; then
  fail "B2: install.sh still defines install_intake_poll_schedule() inline — update-skills.sh can never reach it (the original defect)"
else
  pass "B2: install.sh does not define install_intake_poll_schedule() inline"
fi
if grep -q '^install_watchdog_schedule() {' "$INSTALL_SH"; then
  fail "B3: install.sh defines install_watchdog_schedule() inline (drift risk — it belongs in the shared lib)"
else
  pass "B3: install.sh does not define install_watchdog_schedule() inline"
fi

# ---------------------------------------------------------------------------
# (C) INSTALL PATH — install.sh calls the watchdog installer
# ---------------------------------------------------------------------------
echo ""
echo "--- (C) INSTALL PATH ---"
# A CALL, not a definition and not a fallback stub: a line that is exactly the
# bare invocation. The fail-closed fallback (`... || install_watchdog_schedule()
# { return 1; }`) and any comment mentioning the name must not satisfy this.
if grep -Eq '^[[:space:]]*install_watchdog_schedule[[:space:]]*$' "$INSTALL_SH"; then
  pass "C1: install.sh invokes install_watchdog_schedule"
else
  fail "C1: install.sh never invokes install_watchdog_schedule — a client box installs with NO stall detection and NO supervision"
fi
if grep -Eq '^[[:space:]]*install_intake_poll_schedule[[:space:]]*$' "$INSTALL_SH"; then
  pass "C2: install.sh still invokes install_intake_poll_schedule (FIX 61 unbroken by the move)"
else
  fail "C2: install.sh no longer invokes install_intake_poll_schedule — the move broke FIX 61"
fi

# ---------------------------------------------------------------------------
# (D) ROLL PATH — update-skills.sh repairs BOTH schedulers
# ---------------------------------------------------------------------------
echo ""
echo "--- (D) ROLL PATH ---"
if grep -q 'lib-presentation-schedules.sh' "$UPDATE_SH"; then
  pass "D1: update-skills.sh sources lib-presentation-schedules.sh"
else
  fail "D1: update-skills.sh does NOT source the schedules lib — a fleet roll repairs neither scheduler"
fi
if grep -q 'install_presentation_schedules' "$UPDATE_SH"; then
  pass "D2: update-skills.sh calls install_presentation_schedules (poll + watchdog)"
else
  fail "D2: update-skills.sh never calls install_presentation_schedules"
fi
# It must pin the MATERIALIZED department, not a temp clone that gets deleted.
if grep -q 'departments/Presentations/scripts/presentation-intake-poll.sh' "$UPDATE_SH"; then
  pass "D3: update-skills.sh pins the materialized department as the scripts source"
else
  fail "D3: update-skills.sh does not pin the materialized department — a roll could schedule launchd against a temp clone"
fi

# ---------------------------------------------------------------------------
# Functional harness — a fake department + stubs
# ---------------------------------------------------------------------------
WS="$SANDBOX/ws"
DEPT="$WS/departments/Presentations/scripts"
RUNS="$WS/departments/Presentations/runs"
mkdir -p "$DEPT" "$RUNS" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/openclaw"
# Real template + a stand-in for the two scripts the installers gate on.
cp "$DEPT_SRC/presentation-watchdog.plist.template" "$DEPT/" 2>/dev/null || true
printf '#!/bin/sh\nexit 0\n' > "$DEPT/presentation-watchdog.sh"
printf '#!/bin/sh\nexit 0\n' > "$DEPT/presentation-intake-poll.sh"
printf '#!/usr/bin/env python3\n' > "$DEPT/presentation-notify.py"
chmod +x "$DEPT/presentation-watchdog.sh" "$DEPT/presentation-intake-poll.sh"

STUB="$SANDBOX/bin"; mkdir -p "$STUB"
LAUNCHCTL_LOG="$SANDBOX/launchctl.log"
cat > "$STUB/launchctl" <<'STUBEOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$LAUNCHCTL_LOG"
[ "${1:-}" = "list" ] && exit 1
exit 0
STUBEOF
chmod +x "$STUB/launchctl"

PLIST="$HOME/Library/LaunchAgents/com.blackceo.presentation-watchdog.plist"

run_watchdog_installer() {
  # Runs install_watchdog_schedule in a fresh bash with the sandbox HOME and
  # stubs. Extra env is passed by the caller through the environment.
  LAUNCHCTL_LOG="$LAUNCHCTL_LOG" \
  PATH="$STUB:$PATH" \
  OPENCLAW_PLATFORM="${OPENCLAW_PLATFORM:-mac}" \
  OPENCLAW_ROOT="$SANDBOX/root" \
  OPENCLAW_WORKSPACE_PATH="$WS" OPENCLAW_WORKSPACE_ROOT="$WS" \
  PRESENTATIONS_SCRIPTS_SRC="$DEPT" \
  bash -c 'set -euo pipefail; source "$1"; install_watchdog_schedule' _ "$SCHED_LIB" \
    > "$SANDBOX/wd.out" 2>&1
}

plist_get() {
  # $1 = key path inside EnvironmentVariables (or a top-level key with '/')
  python3 - "$PLIST" "$1" <<'PYEOF'
import plistlib, sys
path, key = sys.argv[1], sys.argv[2]
with open(path, 'rb') as fh:
    data = plistlib.load(fh)
if key.startswith('env/'):
    print(data.get('EnvironmentVariables', {}).get(key[4:], '<ABSENT>'))
else:
    print(data.get(key, '<ABSENT>'))
PYEOF
}

# ---------------------------------------------------------------------------
# (E) RENDER — the Mac branch produces a valid, contract-satisfying LaunchAgent
# ---------------------------------------------------------------------------
echo ""
echo "--- (E) RENDER: Mac LaunchAgent ---"
rm -f "$PLIST"; : > "$LAUNCHCTL_LOG"
if [ ! -f "$SCHED_LIB" ]; then
  fail "E0: schedules lib missing — the functional checks (E)-(J) cannot run"
else
  set +e; run_watchdog_installer; E_RC=$?; set -e
  if [ "$E_RC" -eq 0 ]; then
    pass "E1: install_watchdog_schedule returned 0"
  else
    fail "E1: install_watchdog_schedule returned $E_RC — output: $(head -5 "$SANDBOX/wd.out" | tr '\n' ' ')"
  fi
  if [ -f "$PLIST" ]; then
    pass "E2: wrote $PLIST"
  else
    fail "E2: no LaunchAgent written at $PLIST"
  fi
  if [ -f "$PLIST" ]; then
    [ "$(plist_get Label)" = "com.presentations.watchdog" ] \
      && pass "E3: Label is com.presentations.watchdog (the label this fleet already carries)" \
      || fail "E3: Label is $(plist_get Label)"
    [ "$(plist_get StartInterval)" = "600" ] \
      && pass "E4: StartInterval 600 (10-minute cadence)" \
      || fail "E4: StartInterval is $(plist_get StartInterval), expected 600"
    [ "$(plist_get env/SCAN_ROOT)" = "$RUNS" ] \
      && pass "E5: SCAN_ROOT is the department runs root" \
      || fail "E5: SCAN_ROOT is $(plist_get env/SCAN_ROOT), expected $RUNS"
    case "$(plist_get env/PATH)" in
      *"/opt/homebrew/bin"*) pass "E6: PATH carries a real prefix (launchd supplies none)" ;;
      *) fail "E6: PATH is $(plist_get env/PATH)" ;;
    esac
    case "$(plist_get env/PRESENTATION_NOTIFY_CMD)" in
      *presentation-notify.py*) pass "E7: PRESENTATION_NOTIFY_CMD points at the co-located transport" ;;
      *) fail "E7: PRESENTATION_NOTIFY_CMD is $(plist_get env/PRESENTATION_NOTIFY_CMD)" ;;
    esac
    [ "$(plist_get env/OPENCLAW_WORKSPACE_PATH)" = "$WS" ] \
      && pass "E8: workspace pin carried into launchd's empty environment" \
      || fail "E8: OPENCLAW_WORKSPACE_PATH is $(plist_get env/OPENCLAW_WORKSPACE_PATH)"
    grep -q "^load " "$LAUNCHCTL_LOG" \
      && pass "E9: launchctl load was invoked" \
      || fail "E9: launchctl load was never invoked (job rendered but not scheduled)"
  fi
fi

# ---------------------------------------------------------------------------
# (F) F12c NOT ARMED by default; armed on request; PRESERVED across a re-run
# ---------------------------------------------------------------------------
echo ""
echo "--- (F) SUPERVISOR APPLY (F12c) ---"
if [ -f "$PLIST" ]; then
  [ "$(plist_get env/PRESENTATION_SUPERVISE_APPLY)" = "<ABSENT>" ] \
    && pass "F1: PRESENTATION_SUPERVISE_APPLY ABSENT by default — supervisor is report-only (F12c is gated on F2)" \
    || fail "F1: PRESENTATION_SUPERVISE_APPLY is $(plist_get env/PRESENTATION_SUPERVISE_APPLY) — apply-mode armed early burns the 3-restart budget on manifest-pin deaths"

  rm -f "$PLIST"
  set +e; PRESENTATION_SUPERVISE_APPLY=1 run_watchdog_installer; set -e
  [ "$(plist_get env/PRESENTATION_SUPERVISE_APPLY)" = "1" ] \
    && pass "F2: operator-exported PRESENTATION_SUPERVISE_APPLY=1 IS rendered" \
    || fail "F2: operator-exported apply was not rendered (got $(plist_get env/PRESENTATION_SUPERVISE_APPLY))"

  # Re-run WITHOUT it: a roll must not disarm what an operator armed.
  set +e; run_watchdog_installer; set -e
  [ "$(plist_get env/PRESENTATION_SUPERVISE_APPLY)" = "1" ] \
    && pass "F3: a re-run with no apply in the environment PRESERVED the armed value" \
    || fail "F3: a re-run DISARMED the operator's supervisor (got $(plist_get env/PRESENTATION_SUPERVISE_APPLY)) — a roll must never undo live operator configuration"
fi

# ---------------------------------------------------------------------------
# (G) OWNER_CHAT_ID — resolved, never fabricated
# ---------------------------------------------------------------------------
echo ""
echo "--- (G) OWNER_CHAT_ID: resolved or absent, never invented ---"
if [ -f "$SCHED_LIB" ]; then
  rm -f "$PLIST"
  set +e; run_watchdog_installer; set -e
  [ "$(plist_get env/OWNER_CHAT_ID)" = "<ABSENT>" ] \
    && pass "G1: no source answered -> OWNER_CHAT_ID ABSENT (never a guessed id)" \
    || fail "G1: OWNER_CHAT_ID is $(plist_get env/OWNER_CHAT_ID) with no source configured — that value was invented"

  rm -f "$PLIST"
  set +e; OPENCLAW_OWNER_CHAT_ID=1234567890 run_watchdog_installer; set -e
  [ "$(plist_get env/OWNER_CHAT_ID)" = "1234567890" ] \
    && pass "G2: OPENCLAW_OWNER_CHAT_ID (install.sh's documented override) IS rendered" \
    || fail "G2: OPENCLAW_OWNER_CHAT_ID was not rendered (got $(plist_get env/OWNER_CHAT_ID))"

  rm -f "$PLIST"
  set +e; OPENCLAW_OWNER_CHAT_ID="not-a-chat-id" run_watchdog_installer; set -e
  [ "$(plist_get env/OWNER_CHAT_ID)" = "<ABSENT>" ] \
    && pass "G3: a NON-NUMERIC owner chat id is discarded, not shipped" \
    || fail "G3: a non-numeric owner chat id reached the plist as $(plist_get env/OWNER_CHAT_ID)"
fi

# ---------------------------------------------------------------------------
# (H) IDEMPOTENT — two runs, one plist, reloaded not stacked
# ---------------------------------------------------------------------------
echo ""
echo "--- (H) IDEMPOTENT ---"
if [ -f "$SCHED_LIB" ]; then
  rm -f "$PLIST"; : > "$LAUNCHCTL_LOG"
  set +e; run_watchdog_installer; run_watchdog_installer; set -e
  agents=$(find "$HOME/Library/LaunchAgents" -name 'com.blackceo.presentation-watchdog*.plist' | wc -l | tr -d ' ')
  [ "$agents" = "1" ] \
    && pass "H1: two runs left exactly ONE LaunchAgent (no stacking, no temp file left behind)" \
    || fail "H1: $agents watchdog LaunchAgents present after two runs (expected 1)"
  unloads=$(grep -c '^unload ' "$LAUNCHCTL_LOG" 2>/dev/null || true)
  [ "${unloads:-0}" -ge 1 ] \
    && pass "H2: the re-run unloaded before loading (picks up a re-rendered copy)" \
    || fail "H2: no unload before load — a re-render would not take effect"
  if python3 -c 'import plistlib,sys; plistlib.load(open(sys.argv[1],"rb"))' "$PLIST" 2>/dev/null; then
    pass "H3: the plist after two runs is still valid and parseable"
  else
    fail "H3: the plist after two runs is not a parseable plist"
  fi
fi

# ---------------------------------------------------------------------------
# (I) VPS BRANCH — one silent */10 cron, no client-facing flag, idempotent
# ---------------------------------------------------------------------------
echo ""
echo "--- (I) VPS BRANCH ---"
if [ -f "$SCHED_LIB" ]; then
  MOCK_ARGS="$SANDBOX/cron-create-args.txt"; : > "$MOCK_ARGS"
  cat > "$STUB/openclaw" <<'MOCKEOF'
#!/usr/bin/env bash
sub="${1:-}"; shift || true
if [ "$sub" = "cron" ]; then
  action="${1:-}"; shift || true
  case "$action" in
    add)    echo "  --session <target>" ;;
    create)
      printf 'CREATE %s\n' "$*" >> "$OPENCLAW_MOCK_ARGS"
      # PRES-034: the installer reads the real job list (not only the
      # presence probe), so the mock MUST model what create registered —
      # otherwise a present job looks absent to the reconciler and a
      # duplicate is registered (the exact defect). Shape matches the live
      # gateway's `cron list --json` output; the payload text is the argv
      # after --system-event (word-split here is fine: the prompt's own
      # spaces only matter for the DRIFT comparison, which uses the same
      # split value on both runs).
      python3 - "$OPENCLAW_MOCK_PRESENT" "$*" <<'PYEOF'
import json, sys
out_path, args = sys.argv[1], sys.argv[2]
flags = args.split()
text = ""
for i, a in enumerate(flags):
    if a == "--system-event" and i + 1 < len(flags):
        text = " ".join(flags[i + 1:])
        break
job = {"id": "wd-present-1", "name": "presentation-watchdog", "enabled": True,
       "agentId": "main",
       "schedule": {"kind": "cron", "expr": "*/10 * * * *", "tz": "America/New_York"},
       "sessionTarget": "main",
       "payload": {"kind": "systemEvent", "text": text},
       "delivery": {"mode": "none"}}
json.dump({"jobs": [job]}, open(out_path, "w"))
PYEOF
      ;;
    list)
      # The present JSON (written by create above) is what the reconciler sees.
      if [ "${OC_CRON_PRESENT_FORCE:-absent}" = "present" ]; then
        cat "$OPENCLAW_MOCK_PRESENT" 2>/dev/null || printf '%s\n' '{"jobs":[]}'
      fi
      ;;
    *)      : ;;
  esac
  exit 0
fi
exit 0
MOCKEOF
  chmod +x "$STUB/openclaw"

  run_vps_installer() {
    OPENCLAW_MOCK_ARGS="$MOCK_ARGS" \
    OPENCLAW_MOCK_PRESENT="$SANDBOX/cron-present.txt" \
    PATH="$STUB:$PATH" \
    OPENCLAW_PLATFORM=vps \
    OPENCLAW_ROOT="$SANDBOX/root" \
    OPENCLAW_WORKSPACE_PATH="$WS" OPENCLAW_WORKSPACE_ROOT="$WS" \
    PRESENTATIONS_SCRIPTS_SRC="$DEPT" \
    OC_CRON_PRESENT_FORCE="${OC_CRON_PRESENT_FORCE:-absent}" \
    bash -c '
      set -euo pipefail
      # Stub the presence/tombstone probes BEFORE sourcing: the lib guards its
      # own fallbacks with `command -v`, so these win and the test exercises the
      # installer, not cron-lib.sh.
      oc_cron_tombstoned() { return 1; }
      oc_cron_present() { [ "${OC_CRON_PRESENT_FORCE}" = "present" ]; }
      source "$1"
      install_watchdog_schedule
    ' _ "$SCHED_LIB" > "$SANDBOX/vps.out" 2>&1
  }

  set +e; run_vps_installer; I_RC=$?; set -e
  creates=$(grep -c '^CREATE ' "$MOCK_ARGS" 2>/dev/null || true)
  [ "$I_RC" -eq 0 ] && pass "I1: VPS branch returned 0" || fail "I1: VPS branch returned $I_RC — $(head -3 "$SANDBOX/vps.out" | tr '\n' ' ')"
  [ "${creates:-0}" -eq 1 ] \
    && pass "I2: registered exactly ONE cron" \
    || fail "I2: registered ${creates:-0} crons (expected 1)"
  grep -q -- '--name presentation-watchdog' "$MOCK_ARGS" \
    && pass "I3: cron registered under the name presentation-watchdog" \
    || fail "I3: cron was not named presentation-watchdog"
  grep -q -- '\*/10 \* \* \* \*' "$MOCK_ARGS" \
    && pass "I4: cadence is */10 (10-minute watchdog pass)" \
    || fail "I4: cadence is not */10"
  if grep -qE -- '--channel|--to |--announce' "$MOCK_ARGS"; then
    fail "I5: cron carried a client-facing flag — the watchdog must never auto-push to a client chat"
  else
    pass "I5: cron carried NO --channel/--to/--announce (silent)"
  fi
  grep -qE -- '--session main|--session-target main' "$MOCK_ARGS" \
    && pass "I6: cron is a main-session self-ping" \
    || fail "I6: cron is not a main-session job"
  # Idempotence: a present job must not be re-registered. PRES-034: the mock
  # above wrote the registered job into cron-present.txt, so the second run
  # reads a REAL present job — an in-sync one is left untouched.
  set +e; OC_CRON_PRESENT_FORCE=present run_vps_installer; set -e
  creates2=$(grep -c '^CREATE ' "$MOCK_ARGS" 2>/dev/null || true)
  [ "${creates2:-0}" -eq 1 ] \
    && pass "I7: an already-present cron is left in place (no duplicate)" \
    || fail "I7: a second run brought the total to ${creates2:-0} (expected 1)"
fi

# ---------------------------------------------------------------------------
# (J) NEGATIVE CONTROL — the guard must be able to FAIL
# ---------------------------------------------------------------------------
echo ""
echo "--- (J) NEGATIVE CONTROL: the installer refuses a department with no watchdog ---"
if [ -f "$SCHED_LIB" ]; then
  BROKEN="$SANDBOX/broken-dept"; mkdir -p "$BROKEN"
  cp "$DEPT/presentation-watchdog.plist.template" "$BROKEN/" 2>/dev/null || true
  rm -f "$PLIST"; : > "$LAUNCHCTL_LOG"
  set +e
  LAUNCHCTL_LOG="$LAUNCHCTL_LOG" PATH="$STUB:$PATH" OPENCLAW_PLATFORM=mac \
  OPENCLAW_ROOT="$SANDBOX/root" OPENCLAW_WORKSPACE_PATH="$WS" OPENCLAW_WORKSPACE_ROOT="$WS" \
  PRESENTATIONS_SCRIPTS_SRC="$BROKEN" \
  bash -c 'set -euo pipefail; source "$1"; install_watchdog_schedule' _ "$SCHED_LIB" \
    > "$SANDBOX/broken.out" 2>&1
  J_RC=$?
  set -e
  [ "$J_RC" -ne 0 ] \
    && pass "J1: returns nonzero ($J_RC) when presentation-watchdog.sh is absent" \
    || fail "J1: returned 0 with no watchdog script present — the installer reports success on nothing"
  [ ! -f "$PLIST" ] \
    && pass "J2: wrote NO LaunchAgent in the failure case" \
    || fail "J2: wrote a LaunchAgent for a department that has no watchdog script"
  grep -qi 'not found' "$SANDBOX/broken.out" \
    && pass "J3: the failure names the missing file" \
    || fail "J3: the failure did not say what was missing"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed -- CI guard triggered"
  exit 1
fi
echo "PASS: the Presentations schedulers are installed by install.sh and repaired by update-skills.sh"
exit 0
