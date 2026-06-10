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
