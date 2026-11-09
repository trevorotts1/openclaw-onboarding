#!/usr/bin/env bash
# reassert-apt-deps.sh -- re-install the apt packages a container recreate dropped.
#
# apt installs live in the throwaway layer: every `docker compose up -d --force-recreate`
# erases them, and then a skill that shells out to ffmpeg / pdftoppm / tesseract fails
# with "command not found" on a box that was working an hour earlier
# (docker-persistence.md D3). This script is the ONE persistent reassert for a Hostinger
# box: /data/.openclaw/scripts/reassert-apt-deps.sh, owner uid 1000, mode 755, wired from
# container-startup.sh at boot. Never add a second one.
#
# Idempotent by construction: every expected binary resolving means exit 0 and no apt run.
#
# Env:
#   OPENCLAW_DATA          persistent root (default /data)
#   REASSERT_BINS          space-separated binaries that must resolve (overrides the default)
#   REASSERT_PKGS          space-separated packages to install when they do not
#   REASSERT_LDSO_LIBS     ld.so search paths for /etc/ld.so.conf.d/fleet-local.conf
#                          (empty disables that step)
#
# Exit: 0 every binary resolves (or was installed and now resolves), 1 still missing.
# Never /usr/local/bin/apt-get: on these images it is a "use brew" refusal stub.
set -u

DATA="${OPENCLAW_DATA:-/data}"
LOG="${DATA}/.openclaw/logs/reassert-apt-deps.log"
APT_GET=/usr/bin/apt-get

# Binaries the D3 package list provides, paired with the packages that install them.
# This is the template default - a box's own copy extends it with what its apt history
# actually shows (docker-persistence.md D3 step 1); never invent packages beyond that.
BINS="${REASSERT_BINS:-ffmpeg pdftoppm tesseract jq sqlite3 convert}"
PKGS="${REASSERT_PKGS:-ffmpeg poppler-utils tesseract-ocr jq sqlite3 imagemagick}"
LDSO_LIBS="${REASSERT_LDSO_LIBS-/data/.local/lib}"

log() {
  mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG" 2>/dev/null || true
}

missing() {
  local b
  for b in $BINS; do
    command -v "$b" >/dev/null 2>&1 || printf '%s ' "$b"
  done
}

# sudo -n only when we are not already root; a container running as node needs it.
as_root() {
  if [ "$(id -u)" = "0" ]; then "$@"; else sudo -n "$@"; fi
}

restore_ldso() {
  [ -n "$LDSO_LIBS" ] || return 0
  [ -f /etc/ld.so.conf.d/fleet-local.conf ] && return 0
  # Restoring this file is best-effort and must never fail the run: it only widens the
  # linker search path for tools unpacked into the persistent root.
  if printf '%s\n' "$LDSO_LIBS" | as_root tee /etc/ld.so.conf.d/fleet-local.conf >/dev/null 2>&1; then
    as_root ldconfig 2>/dev/null || true
    log "restored /etc/ld.so.conf.d/fleet-local.conf ($LDSO_LIBS) and ran ldconfig"
  else
    log "could not restore /etc/ld.so.conf.d/fleet-local.conf (no sudo -n); host timer must do it"
  fi
}

restore_ldso

OUT="$(missing)"
if [ -z "$OUT" ]; then
  log "all expected binaries resolve; nothing to reinstall"
  exit 0
fi
log "missing: ${OUT% } - reinstalling: $PKGS"

if [ ! -x "$APT_GET" ]; then
  log "FAILED: $APT_GET is not executable; cannot reinstall"
  exit 1
fi

as_root "$APT_GET" update -qq >> "$LOG" 2>&1 || log "apt-get update failed (continuing to install)"
# shellcheck disable=SC2086  # PKGS is a deliberate space-separated list
as_root "$APT_GET" install -y --no-install-recommends $PKGS >> "$LOG" 2>&1 \
  || log "apt-get install failed"

OUT2="$(missing)"
if [ -n "$OUT2" ]; then
  log "FAILED: still missing after install: ${OUT2% }"
  exit 1
fi
log "reinstalled; every expected binary resolves"
exit 0
