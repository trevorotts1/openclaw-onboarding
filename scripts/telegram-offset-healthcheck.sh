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
# ============================================================================
# P1-6 HARDENING (2026-07-01) -- READ BEFORE RUNNING:
#
# Telegram allows exactly ONE long-poll getUpdates consumer per bot token. The
# OpenClaw gateway's telegram channel is ALSO long-polling getUpdates whenever
# it is running. If this script's getUpdates call races the live gateway
# poller, Telegram 409s ONE of the two callers -- and that can knock the
# gateway's poller into a silent-death loop (no crash, no log, just a bot that
# never receives another update). Running THIS diagnostic against a live
# gateway can therefore CAUSE the exact outage it exists to fix.
#
# This script is a MANUAL diagnostic. It must NEVER be wired into an
# unattended cron (a */15 watchdog was proposed in an earlier revision of this
# header -- that proposal is WITHDRAWN; it is the landmine, not the fix) or
# any automated bootstrap step that could run while the gateway is live.
# Only run it by hand, and only after you have confirmed (or the script has
# confirmed for you) that nothing else is holding the poll slot.
#
# Default behavior now detects whether the gateway/telegram channel looks
# live (HTTP health probe + `openclaw gateway status`, same signals used by
# platform/mac/service-selfheal/gateway-health-watchdog.sh). If it looks
# live, this script does NOT call getUpdates -- it calls getWebhookInfo
# instead, which reports pending_update_count / last_error WITHOUT consuming
# the single poll slot. That is informational only; it cannot detect or heal
# offset corruption (only a real getUpdates call can), but it is always safe.
#
# To run the real corruption check/heal against a box where the gateway
# looks live, you must:
#   1. Stop the telegram channel or the gateway yourself first. There is no
#      verified `openclaw channels stop telegram` (or `openclaw channels
#      stop`) subcommand anywhere in this repo's docs as of this revision --
#      only `openclaw channels restart telegram` is referenced (used below,
#      AFTER a successful heal, gated on the subcommand actually existing).
#      Do not invent a stop subcommand; stop the poller by your platform's
#      normal means (e.g. the process/container that runs the gateway) and
#      confirm it is actually down.
#   2. Re-run this script with `--force-getupdates`. It will re-verify
#      liveness immediately before calling getUpdates and ABORT (exit 3) if
#      the gateway still looks live, rather than trusting the flag blindly.
#   3. After a heal, restart the channel/gateway yourself if the script's
#      own `openclaw channels restart telegram` attempt (see below) did not
#      report success.
#
# Exit codes:
#   0  healthy -- either corruption was detected and healed via a real
#      getUpdates call, or getUpdates confirmed 0 pending / normal backlog,
#      or (poller looked live, no --force-getupdates) a safe getWebhookInfo
#      check ran and found nothing actionable to report.
#   2  could not run: missing dependency / config / token, a network
#      transport failure, or Telegram returned a non-409 non-ok error --
#      non-fatal, skip.
#   3  REFUSED: --force-getupdates was given but the gateway/telegram channel
#      still looks live on the safety re-check -- getUpdates was NOT called.
#   4  CONFLICT: Telegram returned HTTP 409 on a getUpdates call -- another
#      consumer (almost certainly the gateway's own poller) already holds the
#      poll slot for this bot token. getUpdates was aborted immediately; this
#      is reported distinctly, never folded into a generic WARN.
#   5  UNKNOWN: neither a migrated (update-offset-default.json.migrated) nor
#      a legacy (update-offset-default.json) offset file could be found or
#      parsed. Offset health could NOT be determined. This is intentionally
#      never reported as exit 0 "OK" -- "we found nothing" is not "healthy".
#
# Wired in ONE way only (see INSTALL / CHANGELOG): run by hand when a client
# reports "bot not responding" (SYSTEM-DIAGNOSTIC-CHECKLIST.md). It is NOT
# invoked by any other script in this repo and must stay that way unless a
# future revision adds real mutual-exclusion with the gateway poller.

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
MIGRATED_FILE="$TG_DIR/update-offset-default.json.migrated"
HEAL_LOG="$TG_DIR/offset-heal.log"
RESTART_FLAG="$TG_DIR/.needs-channel-restart"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  mkdir -p "$TG_DIR" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$HEAL_LOG"
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

usage() {
  cat <<'EOF'
telegram-offset-healthcheck.sh [--force-getupdates] [--help]

MANUAL diagnostic. Do not run on a schedule; do not run while assuming the
gateway is up. See the header comment in this file for the full contract.

  (no flags)          Safe default. If the gateway/telegram channel looks
                       live, uses getWebhookInfo (non-consuming) instead of
                       getUpdates. If it looks down, runs the real
                       getUpdates-based corruption check/heal directly.
  --force-getupdates   Attempt a real getUpdates call even though the poller
                       looked live on the first check. The caller must have
                       already stopped the channel/gateway manually -- this
                       script re-verifies immediately before calling
                       getUpdates and aborts (exit 3) if it still looks live.
EOF
}

FORCE_GETUPDATES=0
case "${1:-}" in
  --force-getupdates) FORCE_GETUPDATES=1 ;;
  --help|-h) usage; exit 0 ;;
  "") : ;;
  *) echo "[offset-heal] unknown argument: $1" >&2; usage; exit 2 ;;
esac

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

# ---- 2. stored offset: migrated file FIRST, legacy file as fallback ----
# On boxes that have been through the offset-file migration, the legacy
# update-offset-default.json is GONE and the real state lives in
# update-offset-default.json.migrated, keyed by tokenFingerprint. Checking
# only the legacy path (the old bug) makes every migrated box silently
# report "nothing to heal; offset OK" -- which is not true, it just means we
# never looked. Resolve defensively via python3 (json + hashlib are stdlib,
# no new dependency) since the migrated file's exact shape is not documented
# anywhere in this repo as of this revision.
resolve_offset() {
  BOT_TOKEN="$BOT_TOKEN" MIGRATED_FILE="$MIGRATED_FILE" OFFSET_FILE="$OFFSET_FILE" python3 - <<'PYEOF'
import json, hashlib, os

migrated_path = os.environ.get("MIGRATED_FILE", "")
legacy_path = os.environ.get("OFFSET_FILE", "")
token = os.environ.get("BOT_TOKEN", "")

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None

def as_int(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v)
    return None

def offset_from(obj):
    if not isinstance(obj, dict):
        return None
    for k in ("lastUpdateId", "offset"):
        if k in obj:
            v = as_int(obj.get(k))
            if v is not None:
                return k, v
    return None

def fp_candidates_for(tok):
    cands = set()
    if not tok:
        return cands
    tb = tok.encode()
    for algo in ("sha256", "sha1", "md5"):
        h = hashlib.new(algo, tb).hexdigest()
        cands.add(h)
        for n in (6, 8, 10, 12, 16, 20, 32, 40):
            if n < len(h):
                cands.add(h[:n])
    return cands

result = {"SOURCE": "none", "FILE": "", "KEY": "", "VALUE": "",
          "SHAPE": "", "FPKEY": "", "FPMATCH": "n/a", "NOTE": ""}

def set_result(**kw):
    result.update({k: v for k, v in kw.items()})

fp_cands = fp_candidates_for(token)
migrated_exists = bool(migrated_path) and os.path.isfile(migrated_path)
migrated_note = None

if migrated_exists:
    migrated = load(migrated_path)
    if migrated is None:
        migrated_note = f"migrated file present ({migrated_path}) but not valid JSON"
        set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)
    elif isinstance(migrated, dict):
        flat = offset_from(migrated)
        if flat is not None:
            k, v = flat
            fp = migrated.get("tokenFingerprint", "")
            match = "n/a"
            if fp:
                match = "yes" if fp in fp_cands else "no"
            set_result(SOURCE="migrated", FILE=migrated_path, KEY=k, VALUE=str(v),
                       SHAPE="flat", FPKEY=str(fp), FPMATCH=match,
                       NOTE="flat-shaped migrated offset file")
        elif migrated and all(isinstance(v, dict) for v in migrated.values()):
            keys = list(migrated.keys())
            matched = next((kk for kk in keys if kk in fp_cands), None)
            fpmatch = "yes" if matched else "no"
            if matched is None and len(keys) == 1:
                matched = keys[0]
                fpmatch = "unknown"
            if matched is not None:
                sub = offset_from(migrated[matched])
                if sub is not None:
                    k, v = sub
                    set_result(SOURCE="migrated", FILE=migrated_path, KEY=k, VALUE=str(v),
                               SHAPE="map", FPKEY=matched, FPMATCH=fpmatch,
                               NOTE=f"map-shaped migrated offset file ({len(keys)} tokenFingerprint entries)")
                else:
                    migrated_note = "migrated map entry has no numeric lastUpdateId/offset"
                    set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)
            else:
                migrated_note = (f"migrated file has {len(keys)} tokenFingerprint entries; "
                                  "none match the current bot token and more than one "
                                  "candidate exists -- cannot safely pick one")
                set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)
        else:
            migrated_note = f"migrated file present ({migrated_path}) but JSON shape not recognized"
            set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)
    elif isinstance(migrated, list) and migrated:
        matched = next((e for e in migrated if isinstance(e, dict)
                         and e.get("tokenFingerprint") in fp_cands), None)
        fpmatch = "yes" if matched else "no"
        if matched is None and len(migrated) == 1 and isinstance(migrated[0], dict):
            matched = migrated[0]
            fpmatch = "unknown"
        if matched is not None:
            sub = offset_from(matched)
            if sub is not None:
                k, v = sub
                set_result(SOURCE="migrated", FILE=migrated_path, KEY=k, VALUE=str(v),
                           SHAPE="list", FPKEY=str(matched.get("tokenFingerprint", "")),
                           FPMATCH=fpmatch,
                           NOTE=f"list-shaped migrated offset file ({len(migrated)} entries)")
            else:
                migrated_note = "matched migrated list entry has no numeric lastUpdateId/offset"
                set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)
        else:
            migrated_note = (f"migrated file is a list of {len(migrated)} tokenFingerprint "
                              "entries; none match the current bot token")
            set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)
    else:
        migrated_note = f"migrated file present ({migrated_path}) but empty/unrecognized JSON"
        set_result(SOURCE="unknown", FILE=migrated_path, NOTE=migrated_note)

if result["SOURCE"] != "migrated":
    legacy_exists = bool(legacy_path) and os.path.isfile(legacy_path)
    if legacy_exists:
        legacy = load(legacy_path)
        if legacy is not None:
            flat = offset_from(legacy)
            if flat is not None:
                k, v = flat
                note = "legacy offset file"
                if migrated_note:
                    note += f" (migrated file also present but unusable: {migrated_note})"
                set_result(SOURCE="legacy", FILE=legacy_path, KEY=k, VALUE=str(v),
                           SHAPE="flat", NOTE=note)
            else:
                note = "legacy offset file present but no numeric lastUpdateId/offset"
                if migrated_note:
                    note += f"; also: {migrated_note}"
                set_result(SOURCE="unknown", FILE=legacy_path, NOTE=note)
        else:
            note = "legacy offset file present but not valid JSON"
            if migrated_note:
                note += f"; also: {migrated_note}"
            set_result(SOURCE="unknown", FILE=legacy_path, NOTE=note)
    elif result["SOURCE"] != "unknown":
        note = f"no offset file found -- checked migrated ({migrated_path}) and legacy ({legacy_path})"
        set_result(SOURCE="none", FILE="", NOTE=note)

for key in ("SOURCE", "FILE", "KEY", "VALUE", "SHAPE", "FPKEY", "FPMATCH", "NOTE"):
    val = str(result.get(key, "")).replace("\n", " ").replace("\r", " ")
    print(f"{key}={val}")
PYEOF
}

OFFSET_SOURCE="none"; OFFSET_SOURCE_FILE=""; STORED_KEY=""; STORED=""
MIGRATED_SHAPE=""; MIGRATED_FPKEY=""; FPMATCH="n/a"; RESOLVE_NOTE=""
while IFS='=' read -r rk rv; do
  case "$rk" in
    SOURCE) OFFSET_SOURCE="$rv" ;;
    FILE) OFFSET_SOURCE_FILE="$rv" ;;
    KEY) STORED_KEY="$rv" ;;
    VALUE) STORED="$rv" ;;
    SHAPE) MIGRATED_SHAPE="$rv" ;;
    FPKEY) MIGRATED_FPKEY="$rv" ;;
    FPMATCH) FPMATCH="$rv" ;;
    NOTE) RESOLVE_NOTE="$rv" ;;
  esac
done < <(resolve_offset)

if [[ "$OFFSET_SOURCE" == "none" || "$OFFSET_SOURCE" == "unknown" || -z "$STORED" ]]; then
  log "UNKNOWN" "offset state UNKNOWN -- ${RESOLVE_NOTE:-no legacy ($OFFSET_FILE) or migrated ($MIGRATED_FILE) offset file found/parseable}. Cannot verify health -- this is NOT the same as healthy."
  exit 5
fi
log "INFO" "resolved stored offset from $OFFSET_SOURCE file ($OFFSET_SOURCE_FILE): ${STORED_KEY}=$STORED${MIGRATED_FPKEY:+ (tokenFingerprint=$MIGRATED_FPKEY match=$FPMATCH)}"

# ---- 3. gateway/telegram-channel liveness gate (the actual P1-6 fix) ----
# Reuses the same verified 3-signal probe pattern as
# platform/mac/service-selfheal/gateway-health-watchdog.sh: HTTP {"ok":true}
# on the gateway root, HTTP 200 on /healthz, then an `openclaw gateway
# status` text fallback. If the gateway is up and telegram is configured
# (we already confirmed BOT_TOKEN above), its telegram channel is presumed
# to be actively holding the getUpdates poll slot.
detect_gateway_port() {
  local p=""
  if [[ -n "${TGHC_GATEWAY_PORT:-}" ]]; then
    p="$TGHC_GATEWAY_PORT"
  elif command -v openclaw >/dev/null 2>&1; then
    p=$(openclaw gateway status 2>/dev/null | grep -iE 'listen' | grep -oE '[0-9]{2,5}' | tail -1)
  fi
  [[ -z "$p" && -n "${PORT:-}" ]] && p="$PORT"
  [[ -z "$p" && -n "${OPENCLAW_GATEWAY_PORT:-}" ]] && p="$OPENCLAW_GATEWAY_PORT"
  [[ -z "$p" && -n "${OPENCLAW_PORT:-}" ]] && p="$OPENCLAW_PORT"
  [[ -z "$p" && -n "${GATEWAY_PORT:-}" ]] && p="$GATEWAY_PORT"
  [[ -z "$p" ]] && p="18789"
  printf '%s' "$p"
}

gateway_is_up() {
  local port body code st
  port=$(detect_gateway_port)
  body=$(curl -fsS --max-time 5 "http://127.0.0.1:${port}/" 2>/dev/null)
  case "$body" in
    *'"ok":true'*|*'"ok": true'*) return 0 ;;
  esac
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${port}/healthz" 2>/dev/null)
  [[ "$code" == "200" ]] && return 0
  if command -v openclaw >/dev/null 2>&1; then
    st=$(openclaw gateway status 2>/dev/null)
    if printf '%s\n' "$st" | grep -qiE 'not running|not listening|not connected|probe:[[:space:]]*(failed|error|timeout)|unhealthy|stopped|dead|offline'; then
      return 1
    elif printf '%s\n' "$st" | grep -qE 'Connectivity probe:[[:space:]]*ok|Listening:[[:space:]]*[0-9][0-9.]*:[0-9]{2,5}|Capability:[[:space:]]*write-capable|"status"[[:space:]]*:[[:space:]]*"(ok|running|healthy)"'; then
      return 0
    fi
  fi
  return 1
}

# One shared HTTP helper so we NEVER use `curl -f` against the Telegram API:
# `-f` discards the response body on HTTP >=400, which is exactly what makes
# a 409 Conflict indistinguishable from a generic network failure. Capture
# the HTTP status code and body separately instead.
http_get() {
  local url="$1" tmp
  tmp=$(mktemp) || { HTTP_CODE=""; RESP=""; CURL_RC=1; return 0; }
  HTTP_CODE=$(curl -sS --max-time 15 -o "$tmp" -w '%{http_code}' "$url" 2>/dev/null)
  CURL_RC=$?
  RESP=$(cat "$tmp" 2>/dev/null)
  rm -f "$tmp" 2>/dev/null
  return 0
}

safe_webhookinfo_check() {
  local url="https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
  http_get "$url"
  if [[ "$CURL_RC" -ne 0 ]]; then
    log "WARN" "getWebhookInfo transport failure (curl exit=$CURL_RC) -- skipping"
    exit 2
  fi
  if [[ "$HTTP_CODE" == "409" ]]; then
    local desc
    desc=$(printf '%s' "$RESP" | jq -r '.description // "Conflict"' 2>/dev/null)
    log "CONFLICT" "unexpected HTTP 409 on getWebhookInfo: $desc"
    exit 4
  fi
  local ok
  ok=$(printf '%s' "$RESP" | jq -r '.ok // false' 2>/dev/null)
  if [[ "$ok" != "true" ]]; then
    local desc
    desc=$(printf '%s' "$RESP" | jq -r '.description // "unknown"' 2>/dev/null)
    log "WARN" "getWebhookInfo not ok (http=$HTTP_CODE): $desc -- skipping"
    exit 2
  fi
  local pending lasterr
  pending=$(printf '%s' "$RESP" | jq -r '.result.pending_update_count // 0' 2>/dev/null)
  lasterr=$(printf '%s' "$RESP" | jq -r '.result.last_error_message // empty' 2>/dev/null)
  log "INFO" "gateway/telegram poller appears LIVE -- used getWebhookInfo (non-consuming) instead of getUpdates. pending_update_count=$pending${lasterr:+, last_error=\"$lasterr\"}. This does NOT confirm/deny offset corruption (only a real getUpdates call can). To run the full check: stop the telegram channel/gateway yourself (no verified 'openclaw channels stop telegram' subcommand exists in this repo), confirm it is down, then re-run with --force-getupdates."
  exit 0
}

if gateway_is_up; then
  if [[ "$FORCE_GETUPDATES" -eq 0 ]]; then
    safe_webhookinfo_check   # exits inside
  fi
  # --force-getupdates was given: re-verify immediately before touching
  # getUpdates. Never trust the flag alone -- the whole point of P1-6 is that
  # a stale assumption here is how the gateway poller gets 409'd.
  if gateway_is_up; then
    log "REFUSED" "gateway is actively polling -- refusing to run getUpdates concurrently. --force-getupdates was given but the safety re-check still shows the gateway/telegram channel live. Stop it yourself, confirm it is actually down, then re-run."
    exit 3
  fi
  log "INFO" "--force-getupdates: gateway no longer looks live on re-check -- proceeding with getUpdates"
fi

# ---- 4. ask Telegram what is REALLY pending (NO offset param) ----
API="https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?timeout=2&limit=20"
http_get "$API"
if [[ "$CURL_RC" -ne 0 ]]; then
  log "WARN" "getUpdates transport failure (curl exit=$CURL_RC / network / token) -- skipping this run"
  exit 2
fi

if [[ "$HTTP_CODE" == "409" ]]; then
  DESC=$(printf '%s' "$RESP" | jq -r '.description // "Conflict"' 2>/dev/null)
  log "CONFLICT" "gateway is actively polling — refusing to run getUpdates concurrently (HTTP 409: $DESC). Another consumer already holds the poll slot for this bot token. Stop it before retrying."
  exit 4
fi

OK=$(printf '%s' "$RESP" | jq -r '.ok // false' 2>/dev/null)
if [[ "$OK" != "true" ]]; then
  DESC=$(printf '%s' "$RESP" | jq -r '.description // "unknown"' 2>/dev/null)
  log "WARN" "telegram getUpdates not ok (http=$HTTP_CODE): $DESC -- skipping"
  exit 2
fi

PENDING_COUNT=$(printf '%s' "$RESP" | jq -r '.result | length' 2>/dev/null)
if [[ -z "$PENDING_COUNT" || "$PENDING_COUNT" == "0" ]]; then
  log "INFO" "offset OK -- 0 pending updates (stored ${STORED_KEY}=$STORED, source=$OFFSET_SOURCE)"
  exit 0
fi

OLDEST=$(printf '%s' "$RESP" | jq -r '[.result[].update_id] | min' 2>/dev/null)
NEWEST=$(printf '%s' "$RESP" | jq -r '[.result[].update_id] | max' 2>/dev/null)

# ---- 5. corruption test: oldest pending update_id is BELOW stored offset ----
if [[ "$OLDEST" -lt "$STORED" ]] 2>/dev/null; then
  NEW_OFFSET=$((OLDEST - 1))
  BACKUP="$OFFSET_SOURCE_FILE.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$OFFSET_SOURCE_FILE" "$BACKUP" 2>/dev/null || true

  TMP=$(mktemp)
  WRITE_OK=1
  if [[ "$OFFSET_SOURCE" == "migrated" && "$MIGRATED_SHAPE" == "map" ]]; then
    jq --arg fp "$MIGRATED_FPKEY" --arg k "$STORED_KEY" --argjson v "$NEW_OFFSET" \
       '.[$fp][$k] = $v' "$OFFSET_SOURCE_FILE" > "$TMP" 2>/dev/null || WRITE_OK=0
  elif [[ "$OFFSET_SOURCE" == "migrated" && "$MIGRATED_SHAPE" == "list" ]]; then
    jq --arg fp "$MIGRATED_FPKEY" --arg k "$STORED_KEY" --argjson v "$NEW_OFFSET" \
       '(.[] | select(.tokenFingerprint == $fp))[$k] = $v' "$OFFSET_SOURCE_FILE" > "$TMP" 2>/dev/null || WRITE_OK=0
  else
    jq --arg k "$STORED_KEY" --argjson v "$NEW_OFFSET" \
       '.[$k] = $v' "$OFFSET_SOURCE_FILE" > "$TMP" 2>/dev/null || WRITE_OK=0
  fi

  if [[ "$WRITE_OK" -eq 1 ]]; then
    mv "$TMP" "$OFFSET_SOURCE_FILE"
    : > "$RESTART_FLAG" 2>/dev/null || true
    log "HEAL" "CORRUPTION DETECTED+FIXED: stored ${STORED_KEY}=$STORED (source=$OFFSET_SOURCE: $OFFSET_SOURCE_FILE) but oldest pending update_id=$OLDEST (newest=$NEWEST, pending=$PENDING_COUNT). Rewound ${STORED_KEY} to $NEW_OFFSET. Backup: $BACKUP. Restart flag: $RESTART_FLAG"

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
    log "ERROR" "failed to rewrite offset file ($OFFSET_SOURCE_FILE) -- left original untouched (backup at $BACKUP)"
    exit 2
  fi
else
  log "INFO" "offset OK -- oldest pending update_id=$OLDEST >= stored ${STORED_KEY}=$STORED (pending=$PENDING_COUNT, normal backlog, source=$OFFSET_SOURCE)"
  exit 0
fi
