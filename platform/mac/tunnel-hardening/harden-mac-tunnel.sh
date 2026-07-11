#!/usr/bin/env bash
# harden-mac-tunnel.sh
# Bucket 3 -- one-time sudo hardening for an existing Mac-tunnel connector.
# Generalized from the Mac-Tunnel-StayConnected-Fix (fleet-hardened).
#
# Layers applied:
#   A  -- force --protocol http2 (TCP, no UDP idle-timeout drops)
#   B  -- KeepAlive=true (unconditional) + RunAtLoad=true
#   D  -- pmset AC-no-sleep
#
# Run once per box:
#   sudo bash harden-mac-tunnel.sh
#
# Safe to re-run; fully idempotent.
# Does NOT touch the user-level keepalive/watchdog agents (install-keepalive-agent.sh
# and install-watchdog-agent.sh handle those -- no sudo needed).
set -euo pipefail

# ---- Require root ------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: this script must run as root." >&2
  echo "Re-run with:  sudo bash $0" >&2
  exit 1
fi

PLIST="/Library/LaunchDaemons/com.cloudflare.cloudflared.plist"
BUDDY="/usr/libexec/PlistBuddy"

# ---- Pre-flight: connector daemon must exist ---------------------------------
if [[ ! -f "$PLIST" ]]; then
  echo "ERROR: $PLIST not found." >&2
  echo "The cloudflared connector daemon is not installed on this box." >&2
  echo "Run Skill-38 script 14-install-cloudflared-service.sh first," >&2
  echo "then re-run this hardening script." >&2
  exit 2
fi

# ---- Backup -----------------------------------------------------------------
TS="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="${PLIST}.bak-pre-harden-${TS}"
cp "$PLIST" "$BACKUP"
echo "Backed up to: $BACKUP"

# ---- Layer B -- KeepAlive=true + RunAtLoad=true (idempotent) ----------------
# Delete any existing KeepAlive (could be a dict like {SuccessfulExit=false})
# then set a plain boolean true.
echo "--- Layer B: KeepAlive + RunAtLoad ---"
$BUDDY -c "Delete :KeepAlive" "$PLIST" 2>/dev/null || true
$BUDDY -c "Add :KeepAlive bool true" "$PLIST"
$BUDDY -c "Set :RunAtLoad bool true" "$PLIST"
echo "KeepAlive=true, RunAtLoad=true applied."

# ---- Layer A -- --protocol http2 (idempotent) --------------------------------
echo "--- Layer A: --protocol http2 ---"
# Read all ProgramArguments to find the count and whether --protocol exists.
PROG_COUNT="$($BUDDY -c "Print :ProgramArguments:" "$PLIST" 2>/dev/null | grep -c 'Array {' || true)"
# Safer: count entries via grep
ENTRY_COUNT="$($BUDDY -c "Print :ProgramArguments" "$PLIST" | grep -c '^\s\+' || true)"

# Check if --protocol is already in the args
if $BUDDY -c "Print :ProgramArguments" "$PLIST" 2>/dev/null | grep -q -- '--protocol'; then
  # Find the index of --protocol and set the NEXT index to http2
  IDX=0
  while true; do
    VAL="$($BUDDY -c "Print :ProgramArguments:${IDX}" "$PLIST" 2>/dev/null || echo '__END__')"
    if [[ "$VAL" == "__END__" ]]; then
      break
    fi
    if [[ "$VAL" == "--protocol" ]]; then
      NEXT=$((IDX + 1))
      CURRENT_PROTO="$($BUDDY -c "Print :ProgramArguments:${NEXT}" "$PLIST" 2>/dev/null || echo '')"
      if [[ "$CURRENT_PROTO" != "http2" ]]; then
        $BUDDY -c "Set :ProgramArguments:${NEXT} http2" "$PLIST"
        echo "--protocol value updated from '$CURRENT_PROTO' to 'http2'."
      else
        echo "--protocol http2 already set; no change needed."
      fi
      break
    fi
    IDX=$((IDX + 1))
  done
else
  # Append --protocol http2 at the end of ProgramArguments
  COUNT=0
  while $BUDDY -c "Print :ProgramArguments:${COUNT}" "$PLIST" >/dev/null 2>&1; do
    COUNT=$((COUNT + 1))
  done
  $BUDDY -c "Add :ProgramArguments:${COUNT} string -- '--protocol'" "$PLIST"
  $BUDDY -c "Set :ProgramArguments:${COUNT} --protocol" "$PLIST"
  NEXT=$((COUNT + 1))
  $BUDDY -c "Add :ProgramArguments:${NEXT} string http2" "$PLIST"
  echo "--protocol http2 appended (args index $COUNT/$NEXT)."
fi

# ---- Layer D -- pmset: no-sleep AND POWER-OUTAGE RESTART ----------------------
# WAS BROKEN: this layer set sleep/disablesleep but NEVER set `autorestart`.
# `autorestart` defaults to 0 on macOS, so when mains power came back the Mac
# JUST STAYED OFF. A fleet audit found it at 0 on 5 boxes; the 5 that had it set
# got it by hand, inconsistently. A tunnel hardened against sleep on a Mac that
# never powers back on is worthless. Added `autorestart 1` and `womp 1`.
#
# LAPTOPS: `autorestart` is largely meaningless on a battery-backed Mac (it does
# not lose power when the mains does), and `sleep 0` on BATTERY would drain it
# flat. So on a laptop we apply AC-only settings and say so, rather than
# pretending it is a mini.
echo "--- Layer D: pmset (no-sleep + power-outage restart) ---"
echo "Current pmset -g:"
pmset -g | grep -E 'autorestart|womp|sleep|disablesleep' || true

if ioreg -rc AppleSmartBattery 2>/dev/null | grep -q AppleSmartBattery; then
  echo "LAPTOP detected (internal battery). Applying AC-only power policy."
  pmset -c sleep 0
  pmset -c disksleep 0
  pmset -c disablesleep 1
  pmset -c autorestart 1 2>/dev/null || echo "  (autorestart unsupported here — expected on a laptop)"
  pmset -c womp 1 2>/dev/null || echo "  (womp unsupported here — no wake-on-LAN interface)"
  echo "WARNING: a laptop cannot be made fully outage-resilient. Keep it on AC." >&2
  echo "         A client box should be a Mac mini." >&2
else
  echo "DESKTOP / Mac mini. Applying the non-negotiable power policy (-a = all sources)."
  pmset -a autorestart 1
  pmset -a sleep 0
  pmset -a disksleep 0
  pmset -a womp 1 2>/dev/null || echo "  (womp unsupported here — no wake-on-LAN interface)"
  pmset -c disablesleep 1
  echo "autorestart=1, sleep=0, disksleep=0, womp=1 applied."
fi

# ---- Reload the daemon -------------------------------------------------------
echo "--- Reloading com.cloudflare.cloudflared daemon ---"
# Try modern launchctl first; fall back to legacy on older macOS.
if launchctl bootout system/com.cloudflare.cloudflared 2>/dev/null; then
  echo "launchctl bootout OK"
else
  launchctl unload "$PLIST" 2>/dev/null || true
  echo "launchctl unload OK (legacy path)"
fi
sleep 1
if launchctl bootstrap system "$PLIST" 2>/dev/null; then
  echo "launchctl bootstrap OK"
else
  launchctl load "$PLIST" 2>/dev/null || true
  echo "launchctl load OK (legacy path)"
fi

# ---- Wait for respawn (up to 30s) -------------------------------------------
echo "Waiting for cloudflared to respawn..."
NEW_PID=""
for i in $(seq 1 15); do
  sleep 2
  NEW_PID="$(launchctl print system/com.cloudflare.cloudflared 2>/dev/null \
             | grep -E 'pid =' | awk '{print $NF}' || echo '')"
  if [[ "$NEW_PID" =~ ^[0-9]+$ ]] && [[ "$NEW_PID" != "0" ]]; then
    break
  fi
  NEW_PID=""
done

if [[ -z "$NEW_PID" ]]; then
  echo "" >&2
  echo "FAIL: cloudflared did not respawn within 30s after reload." >&2
  echo "Check:  sudo launchctl print system/com.cloudflare.cloudflared" >&2
  echo "Backup plist is at: $BACKUP" >&2
  exit 3
fi

# ---- Verification block (print for the operator log) ------------------------
echo ""
echo "===== VERIFICATION ====="
echo "PID: $NEW_PID"
echo ""
echo "1. ProgramArguments (confirm --protocol http2 is present):"
$BUDDY -c "Print :ProgramArguments" "$PLIST"
echo ""
echo "2. KeepAlive + RunAtLoad:"
$BUDDY -c "Print :KeepAlive" "$PLIST" || echo "(not set)"
$BUDDY -c "Print :RunAtLoad" "$PLIST" || echo "(not set)"
echo ""
echo "3. pmset -g (confirm autorestart=1 AND sleep=0):"
pmset -g | grep -E 'autorestart|womp|sleep|disablesleep' || true
_AR="$(pmset -g | awk '/^[[:space:]]*autorestart/{print $2; exit}')"
if [ "${_AR:-0}" != "1" ]; then
  echo "   WARNING: autorestart is '${_AR:-unset}', not 1. When mains power" >&2
  echo "            returns this Mac will STAY OFF. (Expected on a laptop.)" >&2
fi
echo ""
echo "4. Connector log tail (last 10 lines):"
LOG_PATH="/Library/Logs/com.cloudflare.cloudflared.err.log"
[[ -f "$LOG_PATH" ]] && tail -10 "$LOG_PATH" || echo "(log not found at $LOG_PATH)"
echo ""
echo "===== PASS: Mac-tunnel harden complete. PID=$NEW_PID ====="
echo "Next steps (no sudo needed):"
echo "  bash platform/mac/tunnel-hardening/install-keepalive-agent.sh"
echo "  bash platform/mac/tunnel-hardening/install-watchdog-agent.sh"
