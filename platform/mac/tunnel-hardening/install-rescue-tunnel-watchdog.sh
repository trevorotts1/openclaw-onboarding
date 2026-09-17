#!/usr/bin/env bash
# =============================================================================
# install-rescue-tunnel-watchdog.sh
# Layer E installer: the reboot-stale RESCUE tunnel watchdog (sudo, once).
# =============================================================================
#
# Installs:
#   1. rescue-tunnel-watchdog.sh -> /Library/BlackCEO/rescue-tunnel-watchdog.sh
#      (0755 root:wheel)
#   2. com.blackceo.rescue-tunnel-watchdog LaunchDaemon ->
#      /Library/LaunchDaemons/ (0644 root:wheel), StartInterval 120, RunAtLoad
#   3. Runs the watchdog's sshd leg ONCE immediately, so a box that came back
#      from a reboot with Remote Login off is reachable again before the
#      operator has to chase it.
#
# Run once per box:
#   sudo bash install-rescue-tunnel-watchdog.sh
#
# Fully idempotent. Safe to re-run. It never edits the rescue connector's own
# plist, never touches config or credentials, and never prints a secret.
#
# WHY A ROOT LaunchDaemon and not a user LaunchAgent: the rescue connector is a
# system-domain daemon and so is sshd. A gui/ agent can kickstart neither, and
# it does not run until a human logs in, which is precisely the window this is
# for. Precedent for a repo-shipped root artifact installed with sudo:
# 32-command-center-setup/scripts/setup-tunnel-daemon.sh.
# =============================================================================
set -uo pipefail

LABEL="com.blackceo.rescue-tunnel-watchdog"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
SRC_SCRIPT="$HERE/rescue-tunnel-watchdog.sh"
SRC_PLIST="$HERE/${LABEL}.plist.template"
DEST_DIR="/Library/BlackCEO"
DEST_SCRIPT="$DEST_DIR/rescue-tunnel-watchdog.sh"
DEST_PLIST="/Library/LaunchDaemons/${LABEL}.plist"
LOG_PATH="/Library/Logs/${LABEL}.log"

# ---- Require root (same guard as harden-mac-tunnel.sh) -----------------------
if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "ERROR: this script must run as root." >&2
  echo "Re-run with:  sudo bash $0" >&2
  exit 1
fi

# ---- Pre-flight: both artifacts must be in the bundle -------------------------
[ -f "$SRC_SCRIPT" ] || { echo "ERROR: $SRC_SCRIPT not found" >&2; exit 2; }
[ -f "$SRC_PLIST" ]  || { echo "ERROR: $SRC_PLIST not found" >&2; exit 2; }
bash -n "$SRC_SCRIPT" || { echo "ERROR: $SRC_SCRIPT does not parse; refusing to install it" >&2; exit 2; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"

# ---- 1. Install the watchdog script -------------------------------------------
mkdir -p "$DEST_DIR" || { echo "ERROR: could not create $DEST_DIR" >&2; exit 3; }
chown root:wheel "$DEST_DIR" 2>/dev/null || true
chmod 0755 "$DEST_DIR" 2>/dev/null || true
if install -m 0755 -o root -g wheel "$SRC_SCRIPT" "$DEST_SCRIPT"; then
  echo "[rescue-watchdog] installed: $DEST_SCRIPT (0755 root:wheel)"
else
  echo "ERROR: could not install $DEST_SCRIPT" >&2
  exit 3
fi

# ---- 2. Install the LaunchDaemon plist ----------------------------------------
# Back up an existing plist before overwriting it, so the box is always one
# command away from its previous state.
if [ -f "$DEST_PLIST" ]; then
  if cp -p "$DEST_PLIST" "${DEST_PLIST}.bak-${TS}"; then
    echo "[rescue-watchdog] backed up existing plist -> ${DEST_PLIST}.bak-${TS}"
  else
    echo "[rescue-watchdog] WARN: could not back up $DEST_PLIST; continuing" >&2
  fi
fi
if install -m 0644 -o root -g wheel "$SRC_PLIST" "$DEST_PLIST"; then
  echo "[rescue-watchdog] installed: $DEST_PLIST (0644 root:wheel)"
else
  echo "ERROR: could not install $DEST_PLIST" >&2
  exit 3
fi

# ---- 3. (Re)bootstrap in the SYSTEM domain, idempotent -------------------------
launchctl bootout "system/${LABEL}" >/dev/null 2>&1 || true
_BOOT_RC=0
launchctl bootstrap system "$DEST_PLIST" >/dev/null 2>&1 || _BOOT_RC=$?
if [ "$_BOOT_RC" -ne 0 ]; then
  # Older macOS: fall back to the legacy loader rather than failing the install.
  launchctl load "$DEST_PLIST" >/dev/null 2>&1 || true
fi

# ---- 4. Verify the job is actually there ---------------------------------------
if launchctl print "system/${LABEL}" >/dev/null 2>&1; then
  echo "[rescue-watchdog] VERIFIED loaded: launchctl print system/${LABEL} rc=0"
  echo "[rescue-watchdog] runs every 120s. Log: $LOG_PATH"
else
  echo "ERROR: ${LABEL} did not load. Check: sudo launchctl print system/${LABEL}" >&2
  echo "       plist: $DEST_PLIST" >&2
  exit 4
fi

# ---- 5. Run the sshd leg ONCE, right now ---------------------------------------
# A box that just came back from a reboot with Remote Login off should not have
# to wait 120s for the operator to be able to reach it.
echo "[rescue-watchdog] running the sshd leg once now..."
if RESCUE_WATCHDOG_SKIP_SSHD=0 bash "$DEST_SCRIPT" 2>&1 | sed 's/^/  /'; then
  echo "[rescue-watchdog] first pass complete."
else
  echo "[rescue-watchdog] first pass reported a non-zero rc (see the lines above). The daemon is installed and will retry every 120s." >&2
fi

echo "[rescue-watchdog] DONE. Re-running this script is safe and changes nothing."
exit 0
