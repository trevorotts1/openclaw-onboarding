#!/usr/bin/env bash
# =============================================================================
# setup-tunnel-daemon.sh — Command Center cloudflared tunnel as a launchd service
# =============================================================================
#
# WHAT WAS BROKEN (fleet audit — this template shipped three defects)
# -------------------------------------------------------------------
#  1. IT WAS A USER LaunchAgent (~/Library/LaunchAgents).
#     A LaunchAgent lives in the `gui/<uid>` launchd domain, and THAT DOMAIN DOES
#     NOT EXIST until a console login creates it. RunAtLoad=true + KeepAlive=true
#     are a red herring: a perfect LaunchAgent at a login window is a dead
#     process. A tunnel has ZERO GUI dependency — it never should have been an
#     agent. It is now a ROOT LaunchDaemon (system domain, starts at boot, no
#     login required).
#
#  2. IT HARDCODED /opt/homebrew/bin/cloudflared.
#     That path DOES NOT EXIST on an Intel Mac (Homebrew is at /usr/local there).
#     One fleet box exits 78 (EX_CONFIG) on every single launch and has NEVER
#     ONCE RUN. The binary is now resolved with `command -v cloudflared`, with
#     both Homebrew prefixes as fallbacks.
#
#  3. IT REFERENCED ~/.cloudflared/config-command-center.yml, WHICH DOES NOT
#     EXIST on at least 3 fleet boxes. The tunnel is now run from the connector
#     TOKEN, which is what the registration webhook actually hands back — no
#     config file to go missing.
#
# AND ONE SECURITY DEFECT, fleet-wide
# -----------------------------------
#  4. Tunnel tokens were in CLEARTEXT in world-readable root plists and visible
#     in `ps` output to ANY local user. A connector token is a bearer credential
#     for the client's public hostname. This now uses `--token-file` with mode
#     600 (verified present in cloudflared 2026.6.1: "--token-file value —
#     Filepath at which to read the tunnel token"). One box
#     (com.cloudflare.ghl-inbound) already did this correctly; this is that
#     pattern, generalized.
#
# HONEST LIMIT — READ THIS
# ------------------------
#  A root LaunchDaemon still does NOT run on a FileVault-ON Apple Silicon box.
#  /Library and /Users are firmlinks onto the encrypted Data volume, so the Mac
#  halts at the PRE-BOOT unlock screen and macOS never finishes booting. Six
#  fleet boxes already have correctly-built root cloudflared LaunchDaemons with
#  RunAtLoad=true and would STILL be 100% dark after a power cut. The daemon is
#  necessary but NOT sufficient — the FileVault gate in
#  platform/mac/power-resilience/ is what makes it meaningful.
#
# USAGE
#   ./setup-tunnel-daemon.sh --token <connector-token>     # preferred
#   ./setup-tunnel-daemon.sh                               # reads CLOUDFLARE_TUNNEL_TOKEN
#                                                          # from ~/.openclaw/secrets/.env
#   ./setup-tunnel-daemon.sh --uuid <uuid> --config <path> # legacy named-tunnel form
#
# Idempotent. Safe to re-run. Requires sudo (a LaunchDaemon is a root artifact).
# =============================================================================
set -uo pipefail

TUNNEL_NAME="command-center"
LABEL="com.cloudflare.${TUNNEL_NAME}"
DAEMON_PLIST="/Library/LaunchDaemons/${LABEL}.plist"
LEGACY_AGENT_PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SECRETS_ENV="$HOME/.openclaw/secrets/.env"
TOKEN_FILE="$HOME/.openclaw/secrets/tunnel-${TUNNEL_NAME}.token"

TOKEN=""
UUID=""
CONFIG_PATH=""

while [ $# -gt 0 ]; do
    case "$1" in
        --token)  TOKEN="${2:-}"; shift ;;
        --uuid)   UUID="${2:-}"; shift ;;
        --config) CONFIG_PATH="${2:-}"; shift ;;
        -h|--help) sed -n '2,52p' "$0"; exit 0 ;;
        *)
            # Backwards compatibility with the old positional form:
            #   setup-tunnel-daemon.sh <tunnel-uuid> [config-path]
            if [ -z "$UUID" ]; then UUID="$1"; elif [ -z "$CONFIG_PATH" ]; then CONFIG_PATH="$1"; fi
            ;;
    esac
    shift
done

# ---- 1. Resolve the cloudflared binary (DEFECT 2) ---------------------------
CFD="$(command -v cloudflared 2>/dev/null || true)"
if [ -z "$CFD" ]; then
    for c in /opt/homebrew/bin/cloudflared /usr/local/bin/cloudflared; do
        [ -x "$c" ] && { CFD="$c"; break; }
    done
fi
if [ -z "$CFD" ] || [ ! -x "$CFD" ]; then
    echo "ERROR: cloudflared not found on PATH, /opt/homebrew/bin, or /usr/local/bin." >&2
    echo "       Install it:  brew install cloudflared" >&2
    echo "       (The old template hardcoded /opt/homebrew/bin/cloudflared, which is" >&2
    echo "        why an Intel Mac in the fleet has never once started its tunnel.)" >&2
    exit 1
fi
echo "[tunnel-daemon] cloudflared: $CFD"

# ---- 2. Resolve the token (DEFECT 3) ----------------------------------------
if [ -z "$TOKEN" ] && [ -f "$SECRETS_ENV" ]; then
    TOKEN="$(awk -F= '/^CLOUDFLARE_TUNNEL_TOKEN=/{sub(/^CLOUDFLARE_TUNNEL_TOKEN=/,""); print; exit}' "$SECRETS_ENV")"
fi

RUN_MODE=""
if [ -n "$TOKEN" ]; then
    # ---- 3. Token-file, mode 600 (DEFECT 4 — SECURITY) ----------------------
    mkdir -p "$(dirname "$TOKEN_FILE")"
    chmod 700 "$(dirname "$TOKEN_FILE")" 2>/dev/null || true
    ( umask 077; printf '%s' "$TOKEN" > "$TOKEN_FILE" )
    chmod 600 "$TOKEN_FILE"
    echo "[tunnel-daemon] token stored mode-600 at: $TOKEN_FILE"
    echo "[tunnel-daemon] the token is NOT on the command line, so it is not"
    echo "[tunnel-daemon] visible in \`ps\` to every local user."
    RUN_MODE="token"
elif [ -n "$UUID" ]; then
    # Legacy named-tunnel form. Only valid if the config file ACTUALLY EXISTS —
    # the old template defaulted to a path that is missing on 3+ fleet boxes and
    # then failed silently forever.
    CONFIG_PATH="${CONFIG_PATH:-$HOME/.cloudflared/config-${TUNNEL_NAME}.yml}"
    if [ ! -f "$CONFIG_PATH" ]; then
        echo "ERROR: legacy named-tunnel mode needs a config file, and" >&2
        echo "       $CONFIG_PATH DOES NOT EXIST." >&2
        echo "" >&2
        echo "       This is the exact defect that shipped: the old template pointed" >&2
        echo "       at ~/.cloudflared/config-command-center.yml, which is missing on" >&2
        echo "       at least 3 fleet boxes, and the service never ran." >&2
        echo "" >&2
        echo "       FIX: use the token form instead (this is what the registration" >&2
        echo "       webhook actually returns):" >&2
        echo "         $0 --token <connector-token>" >&2
        exit 1
    fi
    echo "[tunnel-daemon] legacy named-tunnel mode: uuid=$UUID config=$CONFIG_PATH"
    RUN_MODE="uuid"
else
    echo "ERROR: no tunnel token and no tunnel UUID." >&2
    echo "       Pass --token <connector-token>, or put CLOUDFLARE_TUNNEL_TOKEN in" >&2
    echo "       $SECRETS_ENV (scripts/create-tunnel.sh writes it there)." >&2
    exit 1
fi

# ---- 4. Render the ROOT LaunchDaemon (DEFECT 1) -----------------------------
TMP_PLIST="$(mktemp)"
{
    cat <<HDR
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CFD}</string>
        <string>tunnel</string>
        <string>--no-autoupdate</string>
        <string>--protocol</string>
        <string>http2</string>
HDR
    if [ "$RUN_MODE" = "token" ]; then
        cat <<TOK
        <string>run</string>
        <string>--token-file</string>
        <string>${TOKEN_FILE}</string>
TOK
    else
        cat <<UUD
        <string>--config</string>
        <string>${CONFIG_PATH}</string>
        <string>run</string>
        <string>${UUID}</string>
UUD
    fi
    cat <<FTR
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>/var/log/${LABEL}.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/${LABEL}.err.log</string>
</dict>
</plist>
FTR
} > "$TMP_PLIST"

echo "[tunnel-daemon] installing ROOT LaunchDaemon: $DAEMON_PLIST"
echo "[tunnel-daemon] (it was a login-gated user LaunchAgent — it could not start"
echo "[tunnel-daemon]  until a human logged in.)"
sudo install -m 0644 -o root -g wheel "$TMP_PLIST" "$DAEMON_PLIST" || {
    echo "ERROR: could not install $DAEMON_PLIST (needs sudo)." >&2
    rm -f "$TMP_PLIST"; exit 1
}
rm -f "$TMP_PLIST"

# ---- 5. (Re)bootstrap in the SYSTEM domain — idempotent ----------------------
sudo launchctl bootout "system/${LABEL}" 2>/dev/null || true
sudo launchctl bootstrap system "$DAEMON_PLIST" 2>/dev/null \
  || sudo launchctl load "$DAEMON_PLIST" 2>/dev/null \
  || { echo "ERROR: launchctl could not bootstrap ${LABEL}" >&2; exit 1; }

# ---- 6. Retire the old login-gated LaunchAgent, if present -------------------
if [ -f "$LEGACY_AGENT_PLIST" ]; then
    launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
    mv "$LEGACY_AGENT_PLIST" "${LEGACY_AGENT_PLIST}.retired-login-gated"
    echo "[tunnel-daemon] retired the old login-gated LaunchAgent"
    echo "[tunnel-daemon]   -> ${LEGACY_AGENT_PLIST}.retired-login-gated"
fi

# ---- 7. Verify it is actually running ---------------------------------------
sleep 3
PID="$(sudo launchctl print "system/${LABEL}" 2>/dev/null | awk -F'=' '/^[[:space:]]*pid =/{gsub(/[^0-9]/,"",$2); print $2; exit}')"
if [ -n "$PID" ] && [ "$PID" != "0" ]; then
    echo "[tunnel-daemon] OK: ${LABEL} is running as a system LaunchDaemon (pid=$PID)."
    echo "[tunnel-daemon] It will start at BOOT, with no login required."
else
    echo "WARN: ${LABEL} is installed but has no PID yet. Check:" >&2
    echo "        sudo launchctl print system/${LABEL}" >&2
    echo "        tail -50 /var/log/${LABEL}.err.log" >&2
    exit 1
fi

# ---- 8. The honest caveat ----------------------------------------------------
if command -v fdesetup >/dev/null 2>&1 && fdesetup status 2>/dev/null | grep -q "FileVault is On"; then
    echo "" >&2
    echo "############################################################" >&2
    echo "# WARNING: FileVault is ON on this box." >&2
    echo "#" >&2
    echo "# This LaunchDaemon is correctly built and RunAtLoad=true," >&2
    echo "# and it will STILL BE 100% DARK after a power cut. On Apple" >&2
    echo "# Silicon the Mac halts at the PRE-BOOT unlock screen and" >&2
    echo "# macOS never finishes booting — no LaunchDaemon, no" >&2
    echo "# LaunchAgent, no sshd. There is no remote rescue." >&2
    echo "#" >&2
    echo "# Fix:  bash scripts/fix-power-resilience.sh <box>" >&2
    echo "############################################################" >&2
fi
