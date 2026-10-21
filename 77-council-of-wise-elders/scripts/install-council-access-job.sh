#!/usr/bin/env bash
# install-council-access-job.sh [--enable | --disable | --status]
#
# Operator Mac only. Installs the LaunchAgent that runs council-access-autoprovision.sh
# --apply every 30 minutes. With no flag it only PRINTS what it would install and
# changes nothing. --enable writes the plist and loads it; --disable unloads and
# removes it; --status shows whether it is loaded.
#
# ENV: COUNCIL_ACCESS_LAUNCH_DIR (default $HOME/Library/LaunchAgents)
#      COUNCIL_ACCESS_LOG_DIR    (default $HOME/.claude/state/council-elders/access-provision)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="ai.blackceo.council-access-autoprovision"
TEMPLATE="$HERE/../launchd/$LABEL.plist.template"
PROGRAM="$HERE/council-access-autoprovision.sh"
LAUNCH_DIR="${COUNCIL_ACCESS_LAUNCH_DIR:-$HOME/Library/LaunchAgents}"
LOG_DIR="${COUNCIL_ACCESS_LOG_DIR:-$HOME/.claude/state/council-elders/access-provision}"
PLIST="$LAUNCH_DIR/$LABEL.plist"
DOMAIN="gui/$(id -u)"

render() { sed -e "s#__PROGRAM__#$PROGRAM#g" -e "s#__HOME__#$HOME#g" -e "s#__LOG_DIR__#$LOG_DIR#g" "$TEMPLATE"; }

case "${1:-}" in
  "")
    echo "Would install (nothing changed; pass --enable to do it):"
    echo "  plist:    $PLIST"
    echo "  runs:     /bin/bash $PROGRAM --apply   every 1800s and at load"
    echo "  logs:     $LOG_DIR/council-access-autoprovision.{out,err}.log"
    echo "  load:     launchctl bootstrap $DOMAIN $PLIST"
    echo "  receipts: $LOG_DIR/last-run.json and runs.log"
    ;;
  --enable)
    [ -r "$TEMPLATE" ] && [ -x "$PROGRAM" ] || { echo "template or program missing next to this script" >&2; exit 1; }
    mkdir -p "$LAUNCH_DIR" "$LOG_DIR" && render > "$PLIST" && plutil -lint "$PLIST" >/dev/null || { echo "could not write a valid plist" >&2; exit 1; }
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "$DOMAIN" "$PLIST" || { echo "launchctl bootstrap failed" >&2; exit 1; }
    echo "enabled: $LABEL ($PLIST)"
    ;;
  --disable)
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    rm -f "$PLIST"
    echo "disabled: $LABEL"
    ;;
  --status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then echo "loaded: $LABEL"; else echo "not loaded: $LABEL"; fi
    [ -f "$PLIST" ] && echo "plist present: $PLIST" || echo "plist absent: $PLIST"
    ;;
  *) echo "usage: $0 [--enable | --disable | --status]" >&2; exit 2 ;;
esac
