#!/usr/bin/env bash
# 14-install-cloudflared-service.sh
# Step 2 — Install cloudflared as a persistent system service (playbook v5.14 lines 994-1083).
# Idempotent. OS-aware via `uname -s`. Performs the mandatory Restart Survival Test.
set -euo pipefail

SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
[[ -f "$SECRETS_ENV_FILE" ]] && set -a && . "$SECRETS_ENV_FILE" && set +a || true

: "${CLOUDFLARE_TUNNEL_TOKEN:?CLOUDFLARE_TUNNEL_TOKEN missing — run 13-create-cloudflare-tunnel.sh first}"
: "${PUBLIC_HOSTNAME:?PUBLIC_HOSTNAME missing — run 13-create-cloudflare-tunnel.sh first}"

OS="$(uname -s)"
echo "OS detected: $OS" >&2

# ---- Install cloudflared binary if missing -----------------------------------
install_binary() {
  case "$OS" in
    Darwin)
      if ! command -v cloudflared >/dev/null 2>&1; then
        brew list cloudflared >/dev/null 2>&1 || brew install cloudflared
      fi
      ;;
    Linux)
      if ! command -v cloudflared >/dev/null 2>&1; then
        # Cloudflare official apt repo (https://pkg.cloudflare.com/index.html)
        if command -v apt-get >/dev/null 2>&1; then
          sudo mkdir -p --mode=0755 /usr/share/keyrings
          curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
            | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
          echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs 2>/dev/null || echo bookworm) main" \
            | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
          sudo apt-get update -y
          sudo apt-get install -y cloudflared
        else
          echo "Linux without apt detected — install cloudflared manually per https://pkg.cloudflare.com/index.html" >&2
          exit 11
        fi
      fi
      ;;
    *) echo "unsupported OS: $OS" >&2; exit 12 ;;
  esac
}
install_binary
echo "cloudflared: $(cloudflared --version 2>/dev/null | head -1)" >&2

# ---- Install as system service (idempotent) ----------------------------------
service_installed=0
case "$OS" in
  Darwin)
    if sudo launchctl list 2>/dev/null | grep -q com.cloudflare.cloudflared; then
      echo "cloudflared launchd service already installed" >&2
      service_installed=1
    else
      sudo cloudflared service install "$CLOUDFLARE_TUNNEL_TOKEN" >/dev/null
      echo "cloudflared launchd service installed" >&2
    fi

    # ---- Mac-tunnel hardening (Layers A + B + D) ----------------------------
    # Force --protocol http2 (TCP; eliminates UDP NAT idle-timeout drops on Wi-Fi),
    # set KeepAlive=true unconditionally, and disable AC sleep.
    # NOTE: Linux/systemd connectors run in datacenters and are NOT behind consumer
    # NAT -- the QUIC idle-timeout bug is Mac/Wi-Fi specific; leave Linux untouched.
    HARDEN_SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/platform/mac/tunnel-hardening/harden-mac-tunnel.sh"
    if [[ -f "$HARDEN_SCRIPT" ]]; then
      echo "Running Mac-tunnel hardening (http2 + KeepAlive + pmset)..." >&2
      bash "$HARDEN_SCRIPT" >&2 || {
        echo "WARN: Mac-tunnel hardening returned non-zero; check output above." >&2
        echo "      The connector is still running but may not be fully hardened." >&2
        echo "      Re-run manually: sudo bash $HARDEN_SCRIPT" >&2
      }
    else
      echo "WARN: harden-mac-tunnel.sh not found at $HARDEN_SCRIPT" >&2
      echo "      Skipping Mac-tunnel hardening -- tunnel will run with QUIC defaults." >&2
      echo "      Run manually: sudo bash platform/mac/tunnel-hardening/harden-mac-tunnel.sh" >&2
    fi

    # ---- User-level keepalive + watchdog agents (Layers C + D-nosudo) -------
    # These require no sudo and can run as the current login user.
    # KEEPALIVE_SCRIPT is invoked as the current user (not root).
    KEEPALIVE_SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/platform/mac/tunnel-hardening/install-keepalive-agent.sh"
    WATCHDOG_SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/platform/mac/tunnel-hardening/install-watchdog-agent.sh"
    # Service self-heal: re-bootstraps any booted-out gateway/cloudflared agent
    # and kickstarts any dead KeepAlive job (no sudo). See platform/mac/service-selfheal/.
    REMEDIATE_SCRIPT="$(cd "$(dirname "$0")/../.." && pwd)/platform/mac/service-selfheal/install-service-remediate.sh"
    # If running as root (typical in provisioning), use sudo -u to drop to the login user.
    LOGIN_USER="${SUDO_USER:-$(logname 2>/dev/null || id -un)}"
    for AGENT_SCRIPT in "$KEEPALIVE_SCRIPT" "$WATCHDOG_SCRIPT" "$REMEDIATE_SCRIPT"; do
      if [[ -f "$AGENT_SCRIPT" ]]; then
        echo "Installing user tunnel agent: $(basename $AGENT_SCRIPT)" >&2
        if [[ $EUID -eq 0 ]] && [[ -n "$LOGIN_USER" ]] && [[ "$LOGIN_USER" != "root" ]]; then
          sudo -u "$LOGIN_USER" bash "$AGENT_SCRIPT" >&2 || \
            echo "WARN: $(basename $AGENT_SCRIPT) returned non-zero -- check output." >&2
        else
          bash "$AGENT_SCRIPT" >&2 || \
            echo "WARN: $(basename $AGENT_SCRIPT) returned non-zero -- check output." >&2
        fi
      else
        echo "WARN: $(basename $AGENT_SCRIPT) not found -- skipping user agent install." >&2
      fi
    done
    ;;
  Linux)
    if systemctl list-unit-files 2>/dev/null | grep -q '^cloudflared.service'; then
      echo "cloudflared systemd unit already installed" >&2
      service_installed=1
    else
      sudo cloudflared service install "$CLOUDFLARE_TUNNEL_TOKEN" >/dev/null
      echo "cloudflared systemd unit installed" >&2
    fi
    sudo systemctl enable --now cloudflared >/dev/null 2>&1 || true
    ;;
esac

# ---- Verify service is up ----------------------------------------------------
verify_running() {
  case "$OS" in
    Darwin)
      local pid
      pid="$(sudo launchctl list 2>/dev/null | awk '/com\.cloudflare\.cloudflared/ {print $1; exit}')"
      [[ "$pid" =~ ^[0-9]+$ ]] && return 0 || return 1
      ;;
    Linux)
      systemctl is-active --quiet cloudflared
      ;;
  esac
}
sleep 3
verify_running || { echo "cloudflared service NOT active after install" >&2; exit 13; }
echo "cloudflared service is active" >&2

# ---- Restart Survival Test (Step 2G — MANDATORY) -----------------------------
echo "running Restart Survival Test…" >&2
case "$OS" in
  Darwin)
    OLD_PID="$(sudo launchctl list | awk '/com\.cloudflare\.cloudflared/ {print $1; exit}')"
    if [[ "$OLD_PID" =~ ^[0-9]+$ ]]; then
      sudo launchctl kickstart -k system/com.cloudflare.cloudflared || sudo kill -9 "$OLD_PID" || true
    fi
    ;;
  Linux)
    OLD_PID="$(systemctl show cloudflared --property=MainPID --value 2>/dev/null || echo 0)"
    sudo systemctl restart cloudflared
    ;;
esac

# Poll up to 30s for a NEW non-zero PID
NEW_PID=""
for _ in $(seq 1 15); do
  sleep 2
  case "$OS" in
    Darwin) NEW_PID="$(sudo launchctl list | awk '/com\.cloudflare\.cloudflared/ {print $1; exit}')" ;;
    Linux)  NEW_PID="$(systemctl show cloudflared --property=MainPID --value 2>/dev/null || echo 0)" ;;
  esac
  [[ "$NEW_PID" =~ ^[0-9]+$ ]] && [[ "$NEW_PID" != "0" ]] && [[ "$NEW_PID" != "${OLD_PID:-}" ]] && break
done
if ! [[ "$NEW_PID" =~ ^[0-9]+$ ]] || [[ "$NEW_PID" == "0" ]]; then
  echo "Restart Survival Test FAILED — cloudflared did not respawn within 30s" >&2
  exit 14
fi
echo "Restart Survival Test PASSED (OLD_PID=${OLD_PID:-?} → NEW_PID=$NEW_PID)" >&2

# ---- Public smoke test -------------------------------------------------------
echo "public smoke test: GET https://$PUBLIC_HOSTNAME/healthz" >&2
HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "https://$PUBLIC_HOSTNAME/healthz" || echo "000")"
case "$HTTP_CODE" in
  000) echo "smoke test FAILED — timeout/no response (tunnel didn't come up)" >&2; exit 15 ;;
  *)   echo "smoke test response code: $HTTP_CODE (any non-timeout is acceptable here — 404 is normal pre-hooks)" >&2 ;;
esac

echo "OK: cloudflared persistent service verified. Next: scripts/15-configure-hooks-mappings.sh" >&2
