#!/usr/bin/env bash
# telegram-offset-healthcheck.sh
#
# Self-heal for Telegram polling-offset corruption.
#
# THE BUG (2026-05-26 fleet incident, 6 of 8 clients silently went dark):
#   The stored polling offset (lastUpdateId / offset) in
#   update-offset-default.json gets advanced PAST pending Telegram updates
#   during a restart race. The bot then long-polls getUpdates with
#   offset = stored+1, which tells Telegram "I have already processed
#   everything up to stored". Telegram dutifully withholds the real pending
#   messages that sit BELOW the stored offset. The owner keeps texting; the
#   bot never sees a single update. No error is logged. The client is silently
#   dead.
#
# THE HEAL:
#   Ask Telegram (getUpdates with NO offset param) what is ACTUALLY pending.
#   If the oldest pending update_id is BELOW our stored offset, the offset is
#   corrupt -- it skipped real messages. Rewind the stored offset to
#   (oldest_pending - 1) so the very next poll re-fetches the backlog.
#
# Safe to run repeatedly (idempotent). Touches a restart-flag file so the
# gateway / a watchdog can bounce the telegram channel after a correction.
#
# Exit codes:
#   0  healthy, OR corruption detected and healed
#   2  could not run (missing token / config / curl / jq)  -- non-fatal
#
# Wired in two ways (see INSTALL / CHANGELOG):
#   1. container bootstrap, after gateway warmup
#   2. a 15-minute watchdog cron (openclaw cron create)

set -u

# ---- platform detection (VPS /data first, Mac fallback) ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[offset-heal] no OpenClaw root found; nothing to do" >&2
  exit 2
fi

CONFIG_FILE="$OC_ROOT/openclaw.json"
TG_DIR="$OC_ROOT/telegram"
OFFSET_FILE="$TG_DIR/update-offset-default.json"
HEAL_LOG="$TG_DIR/offset-heal.log"
RESTART_FLAG="$TG_DIR/.needs-channel-restart"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  mkdir -p "$TG_DIR" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$HEAL_LOG"
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

# ---- preflight ----
for cmd in curl jq python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "WARN" "missing dependency: $cmd -- skipping healthcheck"
    exit 2
  fi
done

if [[ ! -f "$CONFIG_FILE" ]]; then
  log "WARN" "config not found: $CONFIG_FILE -- skipping"
  exit 2
fi

# ---- 1. bot token ----
BOT_TOKEN=$(jq -r '.channels.telegram.botToken // .channels.telegram.token // empty' "$CONFIG_FILE" 2>/dev/null)
if [[ -z "$BOT_TOKEN" || "$BOT_TOKEN" == "null" ]]; then
  log "WARN" "no telegram botToken in $CONFIG_FILE -- telegram not configured; skipping"
  exit 2
fi

# ---- 2. stored offset (accept lastUpdateId OR offset) ----
if [[ ! -f "$OFFSET_FILE" ]]; then
  log "INFO" "no offset file yet ($OFFSET_FILE) -- nothing to heal; offset OK"
  exit 0
fi
STORED=$(jq -r '.lastUpdateId // .offset // empty' "$OFFSET_FILE" 2>/dev/null)
# Which key is actually present (so we rewrite the same one).
STORED_KEY=$(jq -r 'if has("lastUpdateId") then "lastUpdateId" elif has("offset") then "offset" else "lastUpdateId" end' "$OFFSET_FILE" 2>/dev/null)
if [[ -z "$STORED" || "$STORED" == "null" ]]; then
  log "INFO" "offset file has no numeric offset -- nothing to heal; offset OK"
  exit 0
fi

# ---- 3. ask Telegram what is REALLY pending (NO offset param) ----
API="https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?timeout=2&limit=20"
RESP=$(curl -fsS --max-time 15 "$API" 2>/dev/null) || {
  log "WARN" "getUpdates call failed (network / token) -- skipping this run"
  exit 2
}

OK=$(printf '%s' "$RESP" | jq -r '.ok // false' 2>/dev/null)
if [[ "$OK" != "true" ]]; then
  DESC=$(printf '%s' "$RESP" | jq -r '.description // "unknown"' 2>/dev/null)
  log "WARN" "telegram getUpdates not ok: $DESC -- skipping"
  exit 2
fi

PENDING_COUNT=$(printf '%s' "$RESP" | jq -r '.result | length' 2>/dev/null)
if [[ -z "$PENDING_COUNT" || "$PENDING_COUNT" == "0" ]]; then
  log "INFO" "offset OK -- 0 pending updates (stored ${STORED_KEY}=$STORED)"
  exit 0
fi

OLDEST=$(printf '%s' "$RESP" | jq -r '[.result[].update_id] | min' 2>/dev/null)
NEWEST=$(printf '%s' "$RESP" | jq -r '[.result[].update_id] | max' 2>/dev/null)

# ---- 4. corruption test: oldest pending update_id is BELOW stored offset ----
if [[ "$OLDEST" -lt "$STORED" ]] 2>/dev/null; then
  NEW_OFFSET=$((OLDEST - 1))
  BACKUP="$OFFSET_FILE.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$OFFSET_FILE" "$BACKUP" 2>/dev/null || true

  TMP=$(mktemp)
  if jq --arg k "$STORED_KEY" --argjson v "$NEW_OFFSET" '.[$k] = $v' "$OFFSET_FILE" > "$TMP" 2>/dev/null; then
    mv "$TMP" "$OFFSET_FILE"
    : > "$RESTART_FLAG" 2>/dev/null || true
    log "HEAL" "CORRUPTION DETECTED+FIXED: stored ${STORED_KEY}=$STORED but oldest pending update_id=$OLDEST (newest=$NEWEST, pending=$PENDING_COUNT). Rewound ${STORED_KEY} to $NEW_OFFSET. Backup: $BACKUP. Restart flag: $RESTART_FLAG"

    # Try to bounce the telegram channel so the corrected offset takes effect.
    if command -v openclaw >/dev/null 2>&1; then
      if openclaw channels --help 2>&1 | grep -qi 'restart'; then
        if openclaw channels restart telegram >/dev/null 2>&1; then
          log "INFO" "openclaw channels restart telegram -- ok; clearing restart flag"
          rm -f "$RESTART_FLAG" 2>/dev/null || true
        else
          log "WARN" "openclaw channels restart telegram failed -- left restart flag for watchdog/boot"
        fi
      else
        log "INFO" "no 'openclaw channels restart' subcommand -- left restart flag for boot resurrect to honor"
      fi
    fi
    exit 0
  else
    rm -f "$TMP" 2>/dev/null || true
    log "ERROR" "failed to rewrite offset file -- left original untouched (backup at $BACKUP)"
    exit 2
  fi
else
  log "INFO" "offset OK -- oldest pending update_id=$OLDEST >= stored ${STORED_KEY}=$STORED (pending=$PENDING_COUNT, normal backlog)"
  exit 0
fi
