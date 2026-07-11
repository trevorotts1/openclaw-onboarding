#!/usr/bin/env bash
# =============================================================================
# fix-power-resilience.sh — FLEET REMEDIATION for the power-outage defect
# =============================================================================
#
# A fleet audit proved that 0 of 11 client Macs survive a power outage. The
# provisioner shipped the defect; platform/mac/power-resilience/ fixes it for
# every FUTURE box. This script applies the FIXABLE parts to an EXISTING box.
#
# WHAT IT FIXES (all idempotent, safe to re-run):
#   1. pmset            — autorestart 1 / sleep 0 / disksleep 0 / womp 1
#   2. auto-login       — ONLY if FileVault is off (it is meaningless otherwise)
#   3. login-gated svcs — moves the Command Center tunnel from a user
#                         LaunchAgent to a root LaunchDaemon (a tunnel has zero
#                         GUI dependency, so it should never have been an agent)
#   4. pm2              — collapses com.<user>.pm2-resurrect / pm2.<user> /
#                         io.pm2.launch into ONE canonical com.openclaw.pm2-resurrect
#   5. tunnel tokens    — migrates cleartext `--token <jwt>` in world-readable
#                         plists (also visible in `ps` to ANY local user) to
#                         `--token-file` with mode 600
#
# WHAT IT CANNOT FIX — and REFUSES to pretend it fixed:
#   FileVault. Turning FileVault OFF requires the disk password and a human at
#   the machine. On a FileVault-ON Apple Silicon box the Mac halts at the
#   PRE-BOOT unlock screen: LaunchAgents don't run, LaunchDaemons don't run,
#   sshd doesn't run. There is NO remote fix. This script DETECTS that box,
#   REFUSES to run, and prints exactly what a human must do on site.
#
# USAGE:
#   bash scripts/fix-power-resilience.sh <box>            # DRY-RUN (default)
#   bash scripts/fix-power-resilience.sh <box> --apply    # actually change it
#   bash scripts/fix-power-resilience.sh --local          # DRY-RUN on THIS box
#   bash scripts/fix-power-resilience.sh --local --apply
#
# <box> is an SSH target (reached via the cloudflared ProxyCommand, same as
# scripts/fleet-refresh.sh). Remote mode COPIES this script and the library to
# the box and re-executes there, so all the logic lives in exactly one place.
#
# EXIT CODES:
#   0   remediated (or dry-run completed)
#   78  REFUSED — FileVault is on. A human must go to the machine.
#   1   a remediation step failed
# =============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIB="$REPO_ROOT/platform/mac/power-resilience/lib-power-resilience.sh"

BOX=""
LOCAL=0
APPLY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --local)  LOCAL=1 ;;
        --apply)  APPLY=1 ;;
        -h|--help) sed -n '2,45p' "${BASH_SOURCE[0]}"; exit 0 ;;
        -*)       echo "unknown flag: $1" >&2; exit 2 ;;
        *)        BOX="$1" ;;
    esac
    shift
done

if [ "$LOCAL" -eq 0 ] && [ -z "$BOX" ]; then
    echo "ERROR: pass a <box> (SSH target) or --local." >&2
    echo "Usage: bash scripts/fix-power-resilience.sh <box> [--apply]" >&2
    exit 2
fi

# ---- Remote mode: ship the code to the box and re-exec there -----------------
if [ "$LOCAL" -eq 0 ]; then
    CFD="$(command -v cloudflared || echo /opt/homebrew/bin/cloudflared)"
    SSH_OPTS=(-o "ProxyCommand=$CFD access ssh --hostname %h"
              -o StrictHostKeyChecking=accept-new
              -o ConnectTimeout=20)
    echo "[fix-power-resilience] target: $BOX (apply=$APPLY)"
    REMOTE_DIR="\$HOME/.openclaw/power-resilience"
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$BOX" "mkdir -p $REMOTE_DIR" || {
        echo "ERROR: cannot reach $BOX over SSH." >&2
        echo "  If this box just lost power and is FileVault-ON, it is sitting at" >&2
        echo "  the pre-boot unlock screen and sshd is NOT running. That is the" >&2
        echo "  defect. A human must go to the machine." >&2
        exit 1
    }
    scp "${SSH_OPTS[@]}" "$LIB" "${BASH_SOURCE[0]}" "$BOX:\$HOME/.openclaw/power-resilience/" >/dev/null || exit 1
    ssh "${SSH_OPTS[@]}" "$BOX" \
        "bash \$HOME/.openclaw/power-resilience/fix-power-resilience.sh --local $([ "$APPLY" -eq 1 ] && echo --apply)"
    exit $?
fi

# ---- Local mode: the real work ----------------------------------------------
# When re-executed on a remote box the library sits next to us, not in a repo.
[ -f "$LIB" ] || LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-power-resilience.sh"
[ -f "$LIB" ] || { echo "ERROR: lib-power-resilience.sh not found" >&2; exit 1; }
# shellcheck source=/dev/null
. "$LIB"

if [ "$APPLY" -eq 0 ]; then
    export PR_DRY_RUN=1
    pr_log "DRY-RUN. Nothing will be changed. Re-run with --apply to remediate."
fi

echo ""
echo "=============================================================="
echo " POWER-OUTAGE REMEDIATION — $(hostname -s 2>/dev/null || echo local)"
echo "=============================================================="

RC=0

# ---- STEP 0: FileVault — REFUSE, do not pretend ------------------------------
FV="$(pr_filevault_status)"
if [ "$FV" != "Off" ]; then
    {
        echo ""
        echo "=============================================================="
        echo " REFUSING TO REMEDIATE — FileVault is '$FV' on this box."
        echo "=============================================================="
        echo ""
        echo " There is NO remote fix. Everything below is a lie on this box:"
        echo "   - 'the LaunchDaemon will start it at boot'  → it will not."
        echo "   - 'SSH rescue will save us'                 → sshd never starts."
        echo "   - 'RunAtLoad=true so it comes back'         → it does not."
        echo ""
        echo " On Apple Silicon, /Library and /Users are firmlinks onto the"
        echo " ENCRYPTED Data volume. After a power cut this Mac halts at the"
        echo " PRE-BOOT unlock screen and macOS NEVER FINISHES BOOTING. No"
        echo " launchd job of any kind — Agent or Daemon — ever runs."
        echo ""
        echo " WHAT A HUMAN MUST DO, PHYSICALLY AT THIS MACHINE:"
        echo "   1. Log in at the console."
        echo "   2. System Settings → Privacy & Security → FileVault → Turn Off."
        echo "      (This needs the disk password. It cannot be done over SSH.)"
        echo "   3. WAIT for decryption to complete (can take hours on a big disk)."
        echo "   4. System Settings → Users & Groups → 'Automatically log in as'"
        echo "      → select this box's user. (macOS greys this out while"
        echo "      FileVault is on — that is why step 2 comes first.)"
        echo "   5. Re-run:  bash scripts/fix-power-resilience.sh <box> --apply"
        echo "   6. Prove it:  pull the power cord. The box must come back alone."
        echo ""
        echo " IF THE CLIENT REFUSES TO TURN FILEVAULT OFF:"
        echo "   That is a legitimate choice. It means this box is ATTENDED-ONLY:"
        echo "   after EVERY power loss a person with the disk password must be"
        echo "   physically present to unlock it. Say that out loud to the client."
        echo "   Do not ship it as resilient. It is not."
        echo "=============================================================="
        echo ""
    } >&2
    exit 78
fi
pr_log "STEP 0 OK: FileVault is Off — unattended recovery is achievable here."

# ---- STEP 1: pmset -----------------------------------------------------------
echo ""
pr_log "STEP 1: power policy (pmset)"
pr_apply_pmset || RC=1

# ---- STEP 2: auto-login (only safe because FileVault is off) ------------------
echo ""
pr_log "STEP 2: auto-login"
AL="$(pr_autologin_user)"
if [ -n "$AL" ]; then
    pr_log "  auto-login already set to '$AL' — nothing to do (idempotent)."
else
    ME="${SUDO_USER:-$(id -un)}"
    pr_warn "  auto-login is NOT set. Every LaunchAgent on this box (gateway, pm2,"
    pr_warn "  tunnels, self-heal) is DEAD until a human logs in."
    pr_run sudo "$PR_DEFAULTS" write "$PR_LOGINWINDOW_PLIST" autoLoginUser -string "$ME" || RC=1
    pr_log "  autoLoginUser set to '$ME'."
    pr_warn "  MANUAL STEP REQUIRED — a human must finish this at the machine:"
    pr_warn "    macOS also needs /etc/kcpassword (the auto-login password blob),"
    pr_warn "    which can ONLY be created by System Settings → Users & Groups →"
    pr_warn "    'Automatically log in as'. Setting autoLoginUser alone is NOT"
    pr_warn "    enough and this script will NOT claim otherwise."
    pr_warn "    Do it in the GUI, then reboot and confirm the box reaches the"
    pr_warn "    desktop with nobody touching it."
fi

# ---- STEP 3: Command Center tunnel → root LaunchDaemon + token-file -----------
echo ""
pr_log "STEP 3: Command Center tunnel (LaunchAgent → root LaunchDaemon, token-file)"
CFD_BIN="$(pr_resolve_cloudflared)" || { pr_err "  cannot continue without cloudflared"; RC=1; CFD_BIN=""; }
if [ -n "$CFD_BIN" ]; then
    pr_log "  cloudflared resolved to: $CFD_BIN"
    pr_log "  (the old template HARDCODED /opt/homebrew/bin/cloudflared, which does"
    pr_log "   not exist on an Intel Mac — one fleet box exits 78 EX_CONFIG on every"
    pr_log "   launch and has never once run.)"

    AGENT_PLIST="$PR_LAUNCHAGENTS_DIR/$PR_CC_TUNNEL_LABEL.plist"
    DAEMON_PLIST="$PR_LAUNCHDAEMONS_DIR/$PR_CC_TUNNEL_LABEL.plist"

    # Recover the token from wherever it currently lives: the old plist's
    # cleartext --token arg, or the secrets env.
    TOKEN=""
    if [ -f "$AGENT_PLIST" ]; then
        TOKEN="$(/usr/libexec/PlistBuddy -c "Print :ProgramArguments" "$AGENT_PLIST" 2>/dev/null \
                 | awk '/--token$/{getline; gsub(/^[[:space:]]+|[[:space:]]+$/,""); print; exit}')"
    fi
    if [ -z "$TOKEN" ] && [ -f "$PR_SECRETS_DIR/.env" ]; then
        TOKEN="$(awk -F= '/^CLOUDFLARE_TUNNEL_TOKEN=/{sub(/^CLOUDFLARE_TUNNEL_TOKEN=/,""); print; exit}' "$PR_SECRETS_DIR/.env")"
    fi

    if [ -z "$TOKEN" ]; then
        pr_warn "  no Command Center tunnel token found (no LaunchAgent, no"
        pr_warn "  CLOUDFLARE_TUNNEL_TOKEN in secrets). Skipping — nothing to migrate."
    else
        TOKEN_FILE="$(pr_install_tunnel_token_file "command-center" "$TOKEN")"
        pr_log "  token written to mode-600 file: $TOKEN_FILE"
        pr_log "  the token is no longer on any command line, so it is no longer"
        pr_log "  visible in \`ps\` to every local user."

        TMP_PLIST="$(mktemp)"
        pr_render_tunnel_daemon_plist "$PR_CC_TUNNEL_LABEL" "$CFD_BIN" "$TOKEN_FILE" > "$TMP_PLIST"
        if [ "$PR_DRY_RUN" = "1" ]; then
            pr_log "  DRY-RUN would install root LaunchDaemon: $DAEMON_PLIST"
        else
            sudo install -m 0644 -o root -g wheel "$TMP_PLIST" "$DAEMON_PLIST" || RC=1
            sudo launchctl bootout "system/$PR_CC_TUNNEL_LABEL" 2>/dev/null || true
            sudo launchctl bootstrap system "$DAEMON_PLIST" 2>/dev/null || \
                sudo launchctl load "$DAEMON_PLIST" 2>/dev/null || RC=1
            pr_log "  root LaunchDaemon installed + bootstrapped: $DAEMON_PLIST"
            # Retire the login-gated agent ONLY after the daemon is up.
            if [ -f "$AGENT_PLIST" ]; then
                launchctl bootout "gui/$(id -u)/$PR_CC_TUNNEL_LABEL" 2>/dev/null || true
                mv "$AGENT_PLIST" "$AGENT_PLIST.retired-login-gated" 2>/dev/null || true
                pr_log "  retired the old login-gated LaunchAgent (kept as .retired-login-gated)"
            fi
        fi
        rm -f "$TMP_PLIST"
    fi
fi

# ---- STEP 4: pm2 — one canonical job ----------------------------------------
echo ""
pr_log "STEP 4: pm2 resurrect (collapse 3 hand-rolled names into 1)"
PM2_BIN="$(command -v pm2 2>/dev/null || true)"
if [ -z "$PM2_BIN" ]; then
    pr_log "  pm2 not installed on this box — nothing to do."
else
    LEGACY="$(pr_legacy_pm2_plists)"
    if [ -n "$LEGACY" ]; then
        pr_log "  legacy pm2 launchd jobs found (template drift):"
        printf '%s\n' "$LEGACY" | sed 's/^/               /'
    fi
    TMP_PM2="$(mktemp)"
    pr_render_pm2_plist "$(id -un)" "$HOME" "$PM2_BIN" "$(dirname "$PM2_BIN")" > "$TMP_PM2"
    CANON="$PR_LAUNCHAGENTS_DIR/$PR_PM2_LABEL.plist"
    if [ "$PR_DRY_RUN" = "1" ]; then
        pr_log "  DRY-RUN would install canonical: $CANON"
        pr_log "  DRY-RUN would retire the legacy jobs listed above"
    else
        mkdir -p "$PR_LAUNCHAGENTS_DIR" "$HOME/Library/Logs/openclaw"
        install -m 0644 "$TMP_PM2" "$CANON"
        launchctl bootout "gui/$(id -u)/$PR_PM2_LABEL" 2>/dev/null || true
        launchctl bootstrap "gui/$(id -u)" "$CANON" 2>/dev/null || true
        pr_log "  canonical pm2 job installed: $PR_PM2_LABEL"
        printf '%s\n' "$LEGACY" | while read -r f; do
            [ -n "$f" ] || continue
            launchctl bootout "gui/$(id -u)/$(basename "$f" .plist)" 2>/dev/null || true
            mv "$f" "$f.retired-drift" 2>/dev/null || true
            pr_log "  retired legacy: $(basename "$f")"
        done
    fi
    rm -f "$TMP_PM2"
    pr_log "  NOTE: pm2's own saved process list must exist for resurrect to do"
    pr_log "        anything. Run 'pm2 save' after starting your processes."
fi

# ---- STEP 5: gateway — report, do not silently convert -----------------------
echo ""
pr_log "STEP 5: gateway session-coupling audit"
if pr_gateway_can_be_daemon; then
    pr_log "  This box has NO session-coupled plugin enabled, so a system"
    pr_log "  LaunchDaemon is technically viable here."
    pr_log "  NOT converting automatically, on purpose: the ai.openclaw.gateway"
    pr_log "  plist is OWNED and REWRITTEN by the upstream 'openclaw' CLI. A"
    pr_log "  hand-installed daemon is clobbered on the next 'openclaw update'"
    pr_log "  and you end up running BOTH, fighting over port 18789."
    pr_log "  Auto-login (STEP 2) already fixes this box. That is the supported path."
    pr_log "  If you truly want the daemon, see pr_render_gateway_daemon_plist()."
fi

# ---- STEP 6: Ethernet --------------------------------------------------------
echo ""
pr_log "STEP 6: network path"
pr_check_ethernet

# ---- STEP 7: prove it --------------------------------------------------------
if [ "$PR_DRY_RUN" != "1" ]; then
    pr_acceptance_gate || RC=1
fi

echo ""
if [ "$RC" -eq 0 ]; then
    pr_log "REMEDIATION COMPLETE (rc=0)."
    if [ "$PR_DRY_RUN" = "1" ]; then
        pr_log "That was a DRY-RUN. Re-run with --apply to actually change the box."
    else
        pr_log "FINAL PROOF IS PHYSICAL: pull the power cord, plug it back in, and"
        pr_log "confirm the box returns with nobody touching it. Nothing short of"
        pr_log "that proves outage survival."
    fi
else
    pr_err "REMEDIATION INCOMPLETE (rc=$RC). Read the errors above."
fi
exit "$RC"
