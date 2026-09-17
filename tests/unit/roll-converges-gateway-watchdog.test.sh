#!/usr/bin/env bash
# =============================================================================
# roll-converges-gateway-watchdog.test.sh
#
# THE DEFECT THIS LOCKS. platform/mac/service-selfheal/install-service-remediate.sh
# installs remediate.sh, gateway-health-watchdog.sh and the
# com.openclaw.service-remediate LaunchAgent that drives them every 5 minutes.
# `grep -rn install-service-remediate` found it called from exactly two places:
# install.sh (first-time onboarding) and
# 38-conversational-ai-system/scripts/14-install-cloudflared-service.sh.
# update-skills.sh, the ONLY thing that touches every box on every release,
# never converged it. A box onboarded before that installer shipped therefore
# rolled forever with no safety net over a dark gateway.
#
# That is not theoretical. A detached OpenClaw upgrade stops the gateway
# LaunchAgent for the whole update and restarts it only if the update finishes:
# 10 to 20 minutes routinely, and one Mac fleet box stalled and sat dark for
# about two hours with nothing restarting it. On that box `launchctl list`
# showed no com.openclaw.service-remediate and ~/.openclaw/service-env/ had no
# gateway-watchdog.sh at all.
#
# A SECOND DEFECT, in the watchdog itself. Its Mac heal was
# `launchctl kickstart -k gui/<uid>/<label>`, which does NOTHING against a
# label that is not bootstrapped. And installing the watchdog REMOVED the only
# bootstrap the gateway had, because remediate.sh delegates its whole gateway
# leg to the watchdog the moment the watchdog exists on disk. Dead plus booted
# out was therefore unhealable.
#
# A THIRD, from OpenClaw 2026.9.x. The gateway refuses to start at all while a
# legacy JSON session store is on disk, so restarting it just re-hits the gate.
#
# WHAT IS UNDER TEST.
#   T0  STATIC: the converge block is extractable from update-skills.sh between
#       its two named anchors, and update-skills.sh actually names the installer.
#   T1  STATIC: the roll-log line is [GATEWAY-WATCHDOG] state=<one of four>.
#   T2  BEHAVIOURAL: the extracted block on a fake Mac with nothing installed
#       RUNS the installer and prints state=installed.
#   T3  BEHAVIOURAL: with matching scripts, a plist, and a loaded LaunchAgent it
#       touches nothing and prints state=already-current.
#   T4  BEHAVIOURAL: a non-Mac platform, a container, and root all print
#       state=skipped-not-mac and never invoke the installer.
#   T5  BEHAVIOURAL: an installer that exits non-zero prints state=warn, returns
#       0, and names a STAGED path that outlives the temp clone.
#   T6  BEHAVIOURAL: the watchdog bootstraps a DEAD AND BOOTED-OUT gateway from
#       its plist, then kickstarts it.
#   T7  BEHAVIOURAL: a LOADED but hung gateway is only kickstarted, never
#       bootstrapped twice.
#   T8  BEHAVIOURAL: label resolution does not pick the sibling
#       ai.openclaw.gateway-watchdog label.
#   T9  BEHAVIOURAL: booted out AND no plist escalates instead of acting.
#   T10 BEHAVIOURAL: the 2026.9.x migration gate marker in the gateway log runs
#       the doctor import ONCE with the exact flags, then heals.
#   T11 BEHAVIOURAL: no marker in the log means doctor is never invoked.
#   T12 BEHAVIOURAL: the maintenance lock still stands the whole thing down.
#   T13 STATIC: every shell file in the blast radius parses.
#
# Hermetic: temp HOME, a fake checkout, and launchctl / curl / openclaw stubs on
# PATH. No network, no gateway, no launchd, no credentials, no box is touched.
# =============================================================================
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
UPDATER="$REPO_ROOT/update-skills.sh"
SELFHEAL_DIR="$REPO_ROOT/platform/mac/service-selfheal"
WATCHDOG="$SELFHEAL_DIR/gateway-health-watchdog.sh"
INSTALLER="$SELFHEAL_DIR/install-service-remediate.sh"

[ -f "$UPDATER" ]  || { echo "FATAL: update-skills.sh not found at $UPDATER"; exit 2; }
[ -f "$WATCHDOG" ] || { echo "FATAL: watchdog not found at $WATCHDOG"; exit 2; }

PASS=0; FAIL=0
ok()  { printf '  PASS  %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n== %s\n' "$1"; }

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# T0 - extract the converge block VERBATIM from the real updater
# ---------------------------------------------------------------------------
hdr "T0 - the converge block is extractable and the updater names the installer"

FRAG="$SANDBOX/converge.sh"
awk '/^  # ---- BEGIN gateway-watchdog converge ----$/{p=1}
     p{print}
     /^  # ---- END gateway-watchdog converge ----$/{if(p){exit}}' "$UPDATER" > "$FRAG"

if [ -s "$FRAG" ] && grep -q 'END gateway-watchdog converge' "$FRAG"; then
  ok "T0: converge block extracted between its two anchors ($(wc -l < "$FRAG" | tr -d ' ') lines)"
else
  bad "T0: could not extract the converge block from update-skills.sh (anchors missing or renamed)"
fi

if grep -q 'install-service-remediate.sh' "$UPDATER"; then
  ok "T0: update-skills.sh names install-service-remediate.sh (the roll converges the self-heal)"
else
  bad "T0: update-skills.sh never invokes install-service-remediate.sh - the fleet roll still ships boxes with no gateway watchdog"
fi

if bash -n "$FRAG" 2>/dev/null; then
  ok "T0: the extracted block parses on its own"
else
  bad "T0: the extracted block does not parse"
fi

# ---------------------------------------------------------------------------
# T1 - the greppable roll-log contract
# ---------------------------------------------------------------------------
hdr "T1 - roll-log line format"
grep -q '\[GATEWAY-WATCHDOG\] state=' "$FRAG" \
  && ok "T1: the block prints a greppable [GATEWAY-WATCHDOG] state= line" \
  || bad "T1: no [GATEWAY-WATCHDOG] state= line in the block"
for st in installed already-current skipped-not-mac warn; do
  grep -q "_GWWD_STATE=\"$st\"" "$FRAG" \
    && ok "T1: state '$st' is reachable" \
    || bad "T1: state '$st' is never set"
done

# ---------------------------------------------------------------------------
# Scenario driver for the converge block
# ---------------------------------------------------------------------------
# Builds a fake Mac: temp HOME, a fake extracted checkout carrying the four
# real self-heal artifacts, a launchctl stub, and a fake installer whose calls
# and exit code the test controls.
run_converge() {
  # $1 scenario name. Toggles via env:
  #   CV_PLATFORM       OPENCLAW_PLATFORM value (default mac)
  #   CV_CONTAINER=1    create /data/.openclaw look-alike (simulated via a flag)
  #   CV_INSTALLER_RC   exit code the fake installer returns (default 0)
  #   CV_NO_INSTALLER=1 the bundle does not ship the installer
  #   CV_CONVERGED=1    scripts already match + plist present + agent loaded
  local name="$1"
  C_DIR="$SANDBOX/$name"
  C_HOME="$C_DIR/home"
  C_EXTRACT="$C_DIR/extract"
  C_OC="$C_HOME/.openclaw"
  C_LOG="$C_DIR/roll.log"
  C_BIN="$C_DIR/bin"
  C_CALLS="$C_DIR/installer.calls"
  mkdir -p "$C_HOME/Library/LaunchAgents" "$C_OC/service-env" "$C_OC/scripts" \
           "$C_EXTRACT/platform/mac/service-selfheal" "$C_BIN"
  : > "$C_LOG"; : > "$C_CALLS"

  # The bundle: the REAL artifacts, except the installer, which is faked so the
  # test never loads a LaunchAgent.
  cp "$SELFHEAL_DIR/remediate.sh" \
     "$SELFHEAL_DIR/gateway-health-watchdog.sh" \
     "$SELFHEAL_DIR/com.openclaw.service-remediate.plist.template" \
     "$C_EXTRACT/platform/mac/service-selfheal/"
  if [ "${CV_NO_INSTALLER:-0}" != "1" ]; then
    cat > "$C_EXTRACT/platform/mac/service-selfheal/install-service-remediate.sh" <<FAKEINST
#!/usr/bin/env bash
echo "install-service-remediate.sh \$*" >> "$C_CALLS"
exit ${CV_INSTALLER_RC:-0}
FAKEINST
    chmod +x "$C_EXTRACT/platform/mac/service-selfheal/install-service-remediate.sh"
  fi

  if [ "${CV_CONVERGED:-0}" = "1" ]; then
    cp "$SELFHEAL_DIR/remediate.sh"              "$C_OC/service-env/remediate.sh"
    cp "$SELFHEAL_DIR/gateway-health-watchdog.sh" "$C_OC/service-env/gateway-watchdog.sh"
    : > "$C_HOME/Library/LaunchAgents/com.openclaw.service-remediate.plist"
  fi

  cat > "$C_BIN/launchctl" <<LCEOF
#!/bin/sh
if [ "\${1:-}" = "print" ]; then
  [ "\${CV_AGENT_LOADED:-0}" = "1" ] && exit 0
  exit 113
fi
exit 0
LCEOF
  chmod +x "$C_BIN/launchctl"

  cat > "$C_DIR/driver.sh" <<'DRV'
set -u
EXTRACTED_DIR="$C_EXTRACT"
OC_CONFIG="$C_OC"
LOG_FILE="$C_LOG"
source "$FRAG"
exit 0
DRV

  env -i \
    HOME="$C_HOME" \
    PATH="$C_BIN:/usr/bin:/bin:/usr/sbin:/sbin" \
    OPENCLAW_PLATFORM="${CV_PLATFORM:-mac}" \
    CV_AGENT_LOADED="${CV_CONVERGED:-0}" \
    C_EXTRACT="$C_EXTRACT" C_OC="$C_OC" C_LOG="$C_LOG" FRAG="$FRAG" \
    bash "$C_DIR/driver.sh" > "$C_DIR/stdout" 2>&1
  CRC=$?
  CVOUT="$(cat "$C_DIR/stdout")"
  return 0
}

state_of() { printf '%s\n' "$CVOUT" | sed -n 's/.*\[GATEWAY-WATCHDOG\] state=\([a-z-]*\).*/\1/p' | head -1; }

# ---------------------------------------------------------------------------
# T2 - fresh Mac: the installer RUNS
# ---------------------------------------------------------------------------
hdr "T2 - a Mac with nothing installed converges (state=installed)"
run_converge t2
[ "$CRC" -eq 0 ] && ok "T2: the block exited 0" || bad "T2: the block exited $CRC"
[ "$(state_of)" = "installed" ] && ok "T2: state=installed" || bad "T2: expected state=installed, got '$(state_of)' / $CVOUT"
[ -s "$C_CALLS" ] && ok "T2: install-service-remediate.sh was actually invoked" || bad "T2: the installer was never invoked"
[ -x "$C_OC/scripts/service-selfheal/install-service-remediate.sh" ] \
  && ok "T2: a persistent copy is staged under \$OC_CONFIG/scripts/service-selfheal" \
  || bad "T2: nothing staged; the remedy line would name a deleted temp path"
for f in remediate.sh gateway-health-watchdog.sh com.openclaw.service-remediate.plist.template; do
  [ -f "$C_OC/scripts/service-selfheal/$f" ] && ok "T2: staged $f" || bad "T2: $f was not staged"
done

# ---------------------------------------------------------------------------
# T3 - already converged: nothing is touched
# ---------------------------------------------------------------------------
hdr "T3 - an already-converged Mac is left alone (state=already-current)"
CV_CONVERGED=1 run_converge t3
[ "$(state_of)" = "already-current" ] && ok "T3: state=already-current" || bad "T3: expected already-current, got '$(state_of)' / $CVOUT"
[ ! -s "$C_CALLS" ] && ok "T3: the installer was NOT re-run (no needless bootout/bootstrap churn)" || bad "T3: the installer ran on an already-converged box"

# ---------------------------------------------------------------------------
# T4 - the three skip classes
# ---------------------------------------------------------------------------
hdr "T4 - non-Mac and container skip cleanly (state=skipped-not-mac)"
CV_PLATFORM=vps run_converge t4vps
[ "$(state_of)" = "skipped-not-mac" ] && ok "T4: a VPS prints skipped-not-mac" || bad "T4: VPS got '$(state_of)'"
[ ! -s "$C_CALLS" ] && ok "T4: the installer never ran on the VPS" || bad "T4: the installer ran on a VPS"
[ "$CRC" -eq 0 ] && ok "T4: the VPS leg exited 0" || bad "T4: the VPS leg exited $CRC"

# The container guard is a literal /data/.openclaw test, which a hermetic test
# cannot create. Assert it statically instead, so a rename is still caught.
grep -q 'elif \[ -d "/data/.openclaw" \]; then' "$FRAG" \
  && ok "T4: the container guard tests -d /data/.openclaw before doing anything" \
  || bad "T4: no /data/.openclaw container guard in the block"
grep -q 'elif \[ "$(id -u)" = "0" \]; then' "$FRAG" \
  && ok "T4: the root guard refuses to bootstrap a per-user GUI agent as root" \
  || bad "T4: no root guard in the block"

# ---------------------------------------------------------------------------
# T5 - fail-soft: a broken installer warns, never fails the roll
# ---------------------------------------------------------------------------
hdr "T5 - an installer that fails is a WARN, not a failed roll"
CV_INSTALLER_RC=7 run_converge t5
[ "$CRC" -eq 0 ] && ok "T5: the block still exited 0 (the roll is not failed, the stamp is not withheld)" || bad "T5: the block exited $CRC"
[ "$(state_of)" = "warn" ] && ok "T5: state=warn" || bad "T5: expected warn, got '$(state_of)' / $CVOUT"
case "$CVOUT" in
  *"$C_OC/scripts/service-selfheal/install-service-remediate.sh"*)
    ok "T5: the warn names the STAGED installer path, which outlives the temp clone" ;;
  *) bad "T5: the warn does not name a re-runnable path: $CVOUT" ;;
esac

hdr "T5b - an older bundle with no installer is a WARN, not a crash"
CV_NO_INSTALLER=1 run_converge t5b
[ "$CRC" -eq 0 ] && ok "T5b: exited 0" || bad "T5b: exited $CRC"
[ "$(state_of)" = "warn" ] && ok "T5b: state=warn on a bundle that does not ship the installer" || bad "T5b: got '$(state_of)'"

# ---------------------------------------------------------------------------
# Watchdog harness
# ---------------------------------------------------------------------------
# Drives the REAL gateway-health-watchdog.sh with launchctl, curl and openclaw
# stubbed on PATH. The stubs' call logs are the evidence.
#
# The watchdog is a /bin/sh file, and /bin/sh is dash on the CI runner but
# bash-in-sh-mode on a Mac. Prefer a real dash when one is installed, so a
# bashism cannot pass here and then die on a client box.
WD_SH="$(command -v dash 2>/dev/null || echo sh)"
run_watchdog() {
  # $1 scenario name. Toggles via env:
  #   WD_LOADED=1            the gateway label is bootstrapped
  #   WD_PLIST=1             ~/Library/LaunchAgents/<label>.plist exists
  #   WD_LIST                text `launchctl list` returns
  #   WD_GWLOG_MARKER=1      write the 2026.9.x refusal into the gateway log
  #   WD_NO_OPENCLAW=1       no openclaw CLI on PATH
  #   WD_LOCK=1              hold a fresh maintenance lock
  local name="$1"
  W_DIR="$SANDBOX/$name"
  W_HOME="$W_DIR/home"
  W_BIN="$W_DIR/bin"
  W_LC="$W_DIR/launchctl.calls"
  W_OCCALLS="$W_DIR/openclaw.calls"
  mkdir -p "$W_HOME/.openclaw" "$W_HOME/Library/LaunchAgents" "$W_HOME/Library/Logs/openclaw" "$W_BIN"
  : > "$W_LC"; : > "$W_OCCALLS"

  [ "${WD_PLIST:-0}" = "1" ] && : > "$W_HOME/Library/LaunchAgents/ai.openclaw.gateway.plist"
  [ "${WD_LOCK:-0}" = "1" ]  && : > "$W_HOME/.openclaw/.openclaw-maintenance-lock"
  if [ "${WD_GWLOG_MARKER:-0}" = "1" ]; then
    printf 'boot\nLegacy session store requires migration: %s/.openclaw/sessions/sessions.json. Run "openclaw doctor --fix" against the same state/config before starting OpenClaw.\n' \
      "$W_HOME" > "$W_HOME/Library/Logs/openclaw/gateway.log"
  else
    printf 'gateway started\n' > "$W_HOME/Library/Logs/openclaw/gateway.log"
  fi

  cat > "$W_BIN/launchctl" <<LCEOF
#!/bin/sh
echo "launchctl \$*" >> "$W_LC"
case "\${1:-}" in
  list)  printf '%s\n' "\${WD_LIST:-}" ;;
  print) [ "\${WD_LOADED:-0}" = "1" ] && exit 0; exit 113 ;;
esac
exit 0
LCEOF
  chmod +x "$W_BIN/launchctl"

  # curl always fails => the gateway is unhealthy on every probe.
  printf '#!/bin/sh\nexit 7\n' > "$W_BIN/curl"; chmod +x "$W_BIN/curl"
  # docker must be absent so box detection lands on "mac".
  if [ "${WD_NO_OPENCLAW:-0}" != "1" ]; then
    cat > "$W_BIN/openclaw" <<OCEOF
#!/bin/sh
echo "openclaw \$*" >> "$W_OCCALLS"
[ "\${1:-}" = "gateway" ] && { echo "not running"; exit 0; }
exit 0
OCEOF
    chmod +x "$W_BIN/openclaw"
  fi

  # Threshold 1 so one cycle is enough; cooldown 0 so nothing is suppressed.
  env -i \
    HOME="$W_HOME" \
    PATH="$W_BIN:/usr/bin:/bin:/usr/sbin:/sbin" \
    GATEWAY_WATCHDOG_FAILS=1 \
    GATEWAY_WATCHDOG_COOLDOWN=0 \
    GATEWAY_WATCHDOG_PORT=18789 \
    WD_LOADED="${WD_LOADED:-0}" \
    WD_LIST="${WD_LIST:-}" \
    "$WD_SH" "$WATCHDOG" > "$W_DIR/stdout" 2>&1
  WRC=$?
  WLOG="$(cat "$W_HOME/Library/Logs/openclaw/gateway-watchdog.log" 2>/dev/null || true)"
  WCALLS="$(cat "$W_LC")"
  WOC="$(cat "$W_OCCALLS" 2>/dev/null || true)"
  return 0
}

# ---------------------------------------------------------------------------
# T6 - DEAD AND BOOTED OUT is bootstrapped, then kickstarted
# ---------------------------------------------------------------------------
hdr "T6 - a dead, booted-out gateway is BOOTSTRAPPED from its plist"
WD_LOADED=0 WD_PLIST=1 WD_LIST="" run_watchdog t6
case "$WCALLS" in
  *"launchctl bootstrap gui/"*"ai.openclaw.gateway.plist"*)
    ok "T6: launchctl bootstrap was issued against the plist" ;;
  *) bad "T6: no bootstrap issued; a booted-out gateway is still unhealable. calls: $WCALLS" ;;
esac
case "$WCALLS" in
  *"launchctl kickstart -k gui/"*"ai.openclaw.gateway"*)
    ok "T6: the kickstart still follows the bootstrap" ;;
  *) bad "T6: no kickstart after the bootstrap. calls: $WCALLS" ;;
esac
case "$WLOG" in
  *"BOOTED-OUT"*) ok "T6: the booted-out state is logged, not silent" ;;
  *) bad "T6: the booted-out heal is silent in the log" ;;
esac

# ---------------------------------------------------------------------------
# T7 - LOADED but hung: kickstart only
# ---------------------------------------------------------------------------
hdr "T7 - a loaded but hung gateway is kickstarted, not re-bootstrapped"
WD_LOADED=1 WD_PLIST=1 WD_LIST="1234 0 ai.openclaw.gateway" run_watchdog t7
case "$WCALLS" in
  *"launchctl bootstrap"*) bad "T7: a LOADED gateway was bootstrapped again. calls: $WCALLS" ;;
  *) ok "T7: no redundant bootstrap on a loaded job" ;;
esac
case "$WCALLS" in
  *"kickstart -k gui/"*"ai.openclaw.gateway"*) ok "T7: kickstart issued" ;;
  *) bad "T7: no kickstart on a loaded-but-hung gateway. calls: $WCALLS" ;;
esac

# ---------------------------------------------------------------------------
# T8 - the sibling watchdog label is never mistaken for the gateway
# ---------------------------------------------------------------------------
hdr "T8 - ai.openclaw.gateway-watchdog is NOT resolved as the gateway"
WD_LOADED=1 WD_PLIST=1 \
  WD_LIST="$(printf -- '- 0 ai.openclaw.gateway-watchdog\n999 0 ai.openclaw.gateway\n')" \
  run_watchdog t8
case "$WCALLS" in
  *"gui/"*"/ai.openclaw.gateway-watchdog"*)
    bad "T8: the watchdog's own LaunchAgent was kickstarted instead of the gateway. calls: $WCALLS" ;;
  *"kickstart -k gui/"*"/ai.openclaw.gateway"*)
    ok "T8: resolved ai.openclaw.gateway even with the sibling label listed FIRST" ;;
  *) bad "T8: no gateway kickstart at all. calls: $WCALLS" ;;
esac

# ---------------------------------------------------------------------------
# T9 - booted out with no plist escalates
# ---------------------------------------------------------------------------
hdr "T9 - booted out AND no plist: escalate, never guess"
WD_LOADED=0 WD_PLIST=0 WD_LIST="" run_watchdog t9
case "$WCALLS" in
  *"launchctl bootstrap"*) bad "T9: bootstrap was attempted with no plist on disk" ;;
  *) ok "T9: no bootstrap attempted without a plist" ;;
esac
case "$WLOG" in
  *"ESCALATE"*"no plist"*) ok "T9: the escalation names the missing plist" ;;
  *) bad "T9: no escalation logged. log tail: $(printf '%s' "$WLOG" | tail -3)" ;;
esac
[ "$WRC" -eq 1 ] && ok "T9: exit 1 so a supervising cron can alert" || bad "T9: exit was $WRC, expected 1"

# ---------------------------------------------------------------------------
# T10 - the 2026.9.x session-store migration gate is cleared
# ---------------------------------------------------------------------------
hdr "T10 - the session-store migration gate is cleared before healing"
WD_LOADED=1 WD_PLIST=1 WD_GWLOG_MARKER=1 WD_LIST="1 0 ai.openclaw.gateway" run_watchdog t10
case "$WOC" in
  *"doctor --session-sqlite import --session-sqlite-all-agents --yes --non-interactive"*)
    ok "T10: the doctor import ran with the exact flags" ;;
  *) bad "T10: the migration gate was not cleared. openclaw calls: $WOC" ;;
esac
case "$WLOG" in
  *"MIGRATION-GATE"*"Legacy session store requires migration"*)
    ok "T10: the matched refusal string is logged with its source log path" ;;
  *) bad "T10: the migration-gate detection is silent" ;;
esac
case "$WCALLS" in
  *"kickstart -k"*) ok "T10: the normal heal still follows the import" ;;
  *) bad "T10: the gate was cleared but the gateway was never restarted" ;;
esac

hdr "T10b - no openclaw CLI: the gate is reported, never silently skipped"
WD_LOADED=1 WD_PLIST=1 WD_GWLOG_MARKER=1 WD_NO_OPENCLAW=1 WD_LIST="1 0 ai.openclaw.gateway" run_watchdog t10b
case "$WLOG" in
  *"MIGRATION-GATE: no 'openclaw' CLI on PATH"*)
    ok "T10b: the missing CLI is logged with the operator's manual command" ;;
  *) bad "T10b: a missing CLI silently swallowed the migration gate" ;;
esac

# ---------------------------------------------------------------------------
# T11 - no marker, no doctor
# ---------------------------------------------------------------------------
hdr "T11 - an ordinary dead gateway never triggers the doctor import"
WD_LOADED=1 WD_PLIST=1 WD_GWLOG_MARKER=0 WD_LIST="1 0 ai.openclaw.gateway" run_watchdog t11
case "$WOC" in
  *"--session-sqlite"*) bad "T11: doctor --session-sqlite ran on a box with no migration gate. calls: $WOC" ;;
  *) ok "T11: doctor --session-sqlite was NOT invoked without the marker" ;;
esac
case "$WCALLS" in
  *"kickstart -k"*) ok "T11: the ordinary heal still happened" ;;
  *) bad "T11: the ordinary heal did not happen" ;;
esac

# ---------------------------------------------------------------------------
# T12 - the maintenance lock still wins
# ---------------------------------------------------------------------------
hdr "T12 - a fresh maintenance lock stands the whole watchdog down"
WD_LOADED=0 WD_PLIST=1 WD_LOCK=1 WD_GWLOG_MARKER=1 WD_LIST="" run_watchdog t12
[ "$WRC" -eq 0 ] && ok "T12: exited 0 under the lock" || bad "T12: exited $WRC under the lock"
case "$WCALLS" in
  *"launchctl bootstrap"*|*"kickstart"*) bad "T12: the watchdog acted during an atomic upgrade window" ;;
  *) ok "T12: no bootstrap and no kickstart while the lock is held" ;;
esac
case "$WOC" in
  *"--session-sqlite"*) bad "T12: the doctor import ran during an atomic upgrade window" ;;
  *) ok "T12: no doctor import while the lock is held" ;;
esac
case "$WLOG" in
  *"MAINTENANCE LOCK HELD"*) ok "T12: the stand-down is logged" ;;
  *) bad "T12: the stand-down is silent" ;;
esac

# ---------------------------------------------------------------------------
# T13 - syntax
# ---------------------------------------------------------------------------
hdr "T13 - every file in the blast radius parses"
bash -n "$UPDATER" 2>/dev/null && ok "T13: update-skills.sh is bash -n clean" || bad "T13: update-skills.sh does not parse"
sh -n "$WATCHDOG" 2>/dev/null   && ok "T13: gateway-health-watchdog.sh is sh -n clean (it is a /bin/sh file)" || bad "T13: the watchdog does not parse under sh"
sh -n "$SELFHEAL_DIR/remediate.sh" 2>/dev/null && ok "T13: remediate.sh is sh -n clean" || bad "T13: remediate.sh does not parse under sh"
bash -n "$INSTALLER" 2>/dev/null && ok "T13: install-service-remediate.sh is bash -n clean" || bad "T13: the installer does not parse"

printf '\nResult: %d passed | %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
