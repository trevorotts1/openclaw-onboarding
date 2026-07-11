#!/usr/bin/env bash
# ============================================================
# platform/mac/bootstrap.sh — Mac mini / macOS platform pre-flight
# ============================================================
#
# Sourced by install.sh (unified) when OPENCLAW_PLATFORM=mac or when
# running on macOS.
#
# Extracted from Mac install.sh v10.13.0–v10.15.48 for PRD 2.1 unified.
#
# Contains:
#   1. Mac platform guard (reject if running on VPS by mistake)
#   2. Homebrew / macOS prerequisites check
#   3. Mac canonical path variable setup
#   4. Log file setup (durable — survives reboot via ~/Downloads)
# ============================================================

# ── 1. Platform guard ─────────────────────────────────────────────────────────
if [ -d "/data/.openclaw" ] && [ ! -d "$HOME/.openclaw" ]; then
    echo "ERROR: This is the Mac mini installer; /data/.openclaw exists which means you're on a VPS." >&2
    echo "Re-run without --platform mac, or use the VPS bootstrap directly." >&2
    exit 1
fi

# ── 2. Homebrew / macOS prereqs ──────────────────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
    echo "[install] Homebrew not found on PATH." >&2
    echo "          Install Homebrew first: https://brew.sh" >&2
    echo "          Then re-run this installer." >&2
    exit 1
fi

for _required in curl python3; do
    command -v "$_required" >/dev/null 2>&1 || {
        echo "ERROR: $_required is required but not found." >&2
        echo "       On Mac, install via Homebrew: brew install $_required" >&2
        exit 1
    }
done

# ── 3. Mac canonical path variables ──────────────────────────────────────────
OC_PLATFORM="mac"
OC_CONFIG="$HOME/.openclaw"
OC_JSON="$HOME/.openclaw/openclaw.json"
OC_CREDENTIALS="$HOME/.openclaw/credentials"
OC_AGENTS="$HOME/.openclaw/agents"
OC_SKILLS_DIR="$HOME/.openclaw/skills"
OC_LOGS="$HOME/.openclaw/logs"
OC_AUTH_PROFILES="$HOME/.openclaw/agents/main/agent/auth-profiles.json"
OC_SECRETS_ENV="$HOME/.openclaw/secrets/.env"
OC_DOWNLOADS="$HOME/Downloads"
OC_BACKUPS="$HOME/Downloads/openclaw-backups"
OC_INSTALL_LOG_DIR="$HOME/Downloads/openclaw-backups/install-logs"
OC_LEGACY_CLAWD="$HOME/clawd"        # dead legacy path — never write here
OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"  # canonical default (v10.13.9+)

# ── 4. Log file setup ────────────────────────────────────────────────────────
# /tmp is wiped on reboot; persist install logs to ~/Downloads/openclaw-backups
# so they survive a restart and can be referenced when reporting issues. (v10.0.2)
mkdir -p "$OC_BACKUPS" "$OC_INSTALL_LOG_DIR"
LOG_FILE="$OC_INSTALL_LOG_DIR/openclaw-install-$(date +%Y%m%d-%H%M%S).log"
exec 1> >(tee -a "$LOG_FILE") 2>&1

# ── 5. POWER-OUTAGE SURVIVAL PRE-FLIGHT (HARD GATE) ──────────────────────────
#
# WHY THIS IS A GATE AND NOT A WARNING:
#   A fleet audit measured 0 of 11 client Macs surviving a power outage. The
#   installer happily laid LaunchAgent-based services (gateway, pm2 resurrect,
#   Command Center tunnel, self-heal remediator) onto FileVault-locked boxes
#   that never auto-log-in — and REPORTED SUCCESS. Those boxes are undead: they
#   look provisioned and they never come back after a power cut.
#
#   A user LaunchAgent lives in the `gui/<uid>` launchd domain. That domain DOES
#   NOT EXIST until a console login creates it. RunAtLoad=true and KeepAlive=true
#   are a RED HERRING — a perfect LaunchAgent at a login window is a dead
#   process. Measured on a real client box: gateway DEAD for 3 days 14 hours,
#   machine powered on, networked, both tunnels green. It started the exact
#   second a human logged in.
#
#   And with FileVault ON on Apple Silicon it is worse: /Library and /Users are
#   firmlinks onto the ENCRYPTED Data volume, so the Mac halts at the PRE-BOOT
#   unlock screen and macOS never finishes booting. LaunchDaemons do not run
#   either. sshd does not run. "SSH rescue will save us" is FALSE.
#
#   So: the installer must FAIL if it is about to lay a login-gated service onto
#   a box that never logs in. It must not ship another undead Mac.
#
#   Full rationale + the LaunchDaemon-vs-checked-LaunchAgent decision:
#     platform/mac/power-resilience/lib-power-resilience.sh
#     platform/mac/power-resilience/README.md
_PR_LIB="${_SCRIPT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}/platform/mac/power-resilience/lib-power-resilience.sh"
if [ -f "$_PR_LIB" ]; then
    # shellcheck source=/dev/null
    . "$_PR_LIB"
    echo "[install] Power-outage survival pre-flight..."
    if ! pr_assert_unattended_boot_capable; then
        echo "[install] ABORTED at the power-resilience gate (EX_CONFIG 78)." >&2
        echo "[install] Nothing was installed. Fix the box and re-run." >&2
        echo "[install] To remediate an EXISTING box:" >&2
        echo "[install]   bash scripts/fix-power-resilience.sh <box> --apply" >&2
        exit 78
    fi
    # DEFECT 2: pmset was never touched by the provisioner. autorestart defaults
    # to 0 → mains returns and the Mac just stays off. Non-negotiable; needs sudo.
    if [ "$(id -u)" -eq 0 ] || sudo -n true 2>/dev/null; then
        pr_apply_pmset || echo "[install] WARNING: pmset policy not fully applied" >&2
    else
        echo "[install] WARNING: no non-interactive sudo — pmset NOT applied." >&2
        echo "[install]          Without it, this Mac stays OFF when mains returns." >&2
        echo "[install]          Run:  sudo pmset -a autorestart 1 sleep 0 disksleep 0 womp 1" >&2
    fi
    pr_check_ethernet
else
    echo "[install] WARNING: power-resilience library not found at $_PR_LIB" >&2
    echo "[install]          Skipping the outage-survival gate. This box may be" >&2
    echo "[install]          provisioned into the undead state (looks fine, never" >&2
    echo "[install]          comes back after a power cut)." >&2
fi
