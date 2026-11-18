#!/bin/bash
# auto-update-tick.sh -- the ONE crontab entry of the Tuesday/Friday/Sunday auto-update.
#   */5 * * * * /bin/bash '<openclaw root>/scripts/auto-update-tick.sh' # openclaw-auto-update
# Cron runs with PATH=/usr/bin:/bin: add the places openclaw, node and python3 live, then hand
# everything to auto_update.py, which keeps its own Eastern clock (DST-correct, independent of the
# box time zone) and does nothing on every tick that is not 2:15 AM - 5:30 AM Eastern on a
# Tuesday, Friday or Sunday. Silent: it never prints to a client chat.
set -u
SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
for d in "${OPENCLAW_ROOT:-/nonexistent}/npm-global/bin" /data/.openclaw/npm-global/bin \
         "$HOME/.openclaw/npm-global/bin" "$HOME/.npm-global/bin" "$HOME/.local/bin" \
         /usr/local/bin /opt/homebrew/bin; do
  [ -d "$d" ] && case ":$PATH:" in *":$d:"*) ;; *) PATH="$d:$PATH" ;; esac
done
export PATH
LOG="${OPENCLAW_ROOT:-$( [ -d /data/.openclaw ] && echo /data/.openclaw || echo "$HOME/.openclaw" )}/skills/.update-log"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
command -v python3 >/dev/null 2>&1 || { echo "[$(date '+%Y-%m-%d %H:%M:%S')] auto-update tick: python3 not found" >> "$LOG"; exit 1; }
python3 "$SELF_DIR/auto_update.py" tick >> "$LOG" 2>&1
