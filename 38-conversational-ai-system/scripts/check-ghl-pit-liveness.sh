#!/usr/bin/env bash
# check-ghl-pit-liveness.sh — Daily RUNTIME GHL Private-Integration-Token (PIT)
# liveness check for Skill 38 (Conversational AI System).
#
# WHY THIS EXISTS
# ---------------
# Skill 38's conversational brain SENDS/READS every GHL reply on the location
# PIT (`GHL_PRIVATE_INTEGRATION_TOKEN`). If that PIT dies after handoff, EVERY
# conversational op 401s — the agent cannot send the reply. Skill 44 already
# watches the FIREBASE build token (check-ghl-token-liveness.sh); this is its
# RUNTIME-PIT twin. It:
#
#   1. Resolves the client box's PIT + location id from the standard env-store
#      order (canonical GOHIGHLEVEL_* names first, then the legacy GHL_* names).
#   2. Issues the skill's OWN in-scope runtime READ — GET /conversations/search
#      (scope `conversations.readonly`, which the skill already requires) — so a
#      VALID token never false-alarms on a missing locations-read scope.
#   3. Classifies: 2xx = VALID; 401 = dead/expired PIT.
#   4. On VALID: logs a one-line PASS + day-stamp, exits 0. No notification.
#   5. On 401: sends the CLIENT (never an operator) a plain-English "refresh your
#      GHL connection" message, once per day, then exits 1.
#   6. On any OTHER non-2xx (400/403/5xx/network): logs for the OPERATOR and
#      exits 0 — NEVER spams the client on an ambiguous/transient error.
#
# IDEMPOTENT / ONCE-PER-DAY
# -------------------------
# A daily state file ($STATE_DIR/ghl-pit-liveness-<UTC-date>.ok) short-circuits
# repeat PASS runs; a .notified stamp prevents notifying more than once per day.
# Delete the state file to force a re-check.
#
# NOTIFICATION TARGET
# -------------------
# The notification always goes to the CLIENT's own configured Telegram chat
# (resolved from openclaw.json allowFrom; operator IDs are hard-excluded). If no
# client chat resolves, it logs an operator warning and exits 1 (no send).
#
# bash-not-zsh: always invoke via `bash`, never `zsh`.
#
# EXIT CODES
#   0  PIT VALID, already-passed-today, no creds to check, or ambiguous/transient
#      error (operator-logged, client NOT spammed)
#   1  PIT is dead/expired (401) — client notified once per day (or operator
#      warned if no client chat could be resolved)

set -euo pipefail

GHL_API_BASE="${GHL_API_BASE:-https://services.leadconnectorhq.com}"
GHL_API_VERSION="${GHL_API_VERSION:-2021-04-15}"   # conversations module version

# Notification target resolution — PII-free (mirrors 22-notify-client-doc.sh);
# a UNIVERSAL skill carries NO hardcoded chat ids:
#   CLIENT_TELEGRAM_CHAT_ID    optional; the preferred CLIENT target (skips lookup)
#   OPERATOR_TELEGRAM_CHAT_ID  optional (default empty); a chat id to EXCLUDE so a
#                              refresh notice never lands on the operator instead
#                              of the client. Set it in the environment/config.
CLIENT_TELEGRAM_CHAT_ID="${CLIENT_TELEGRAM_CHAT_ID:-}"
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-}"

_log() { echo "[ghl-pit-liveness] $*"; }

# ---------------------------------------------------------------------------
# OpenClaw root (VPS /data first, then Mac $HOME).
# ---------------------------------------------------------------------------
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"
else
  _log "WARN no OpenClaw root found; skipping check."
  exit 0
fi

STATE_DIR="${OC_ROOT}/workspace/ghl-pit-liveness"
mkdir -p "$STATE_DIR"
TODAY=$(date -u +%Y-%m-%d)
PASS_STAMP="${STATE_DIR}/ghl-pit-liveness-${TODAY}.ok"
NOTIFIED_STAMP="${STATE_DIR}/ghl-pit-liveness-${TODAY}.notified"

# ---------------------------------------------------------------------------
# Once-per-day PASS guard.
# ---------------------------------------------------------------------------
if [[ -f "$PASS_STAMP" ]]; then
  _log "PASS already confirmed today (${TODAY}) — skipping. Delete ${PASS_STAMP} to force recheck."
  exit 0
fi

# ---------------------------------------------------------------------------
# Resolve creds from the standard env-store order (process env wins over files).
# Search path mirrors seed-ghl-auth.py + MEMORY client-box-env-stores.
# ---------------------------------------------------------------------------
_load_env_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    if [[ "$line" =~ ^(export[[:space:]]+)?([A-Z_][A-Z0-9_]*)=(.*)$ ]]; then
      local k="${BASH_REMATCH[2]}" v="${BASH_REMATCH[3]}"
      v="${v#\'}" ; v="${v%\'}"
      v="${v#\"}" ; v="${v%\"}"
      [[ -z "${!k:-}" ]] && export "$k"="$v"
    fi
  done < "$f"
}

for ENV_FILE in \
  "${OC_ROOT}/secrets/.env" \
  "${HOME}/.openclaw/secrets/.env" \
  "/data/.openclaw/secrets/.env" \
  "${OC_ROOT}/secrets.env" \
  "${HOME}/.openclaw/secrets.env" \
  "${OC_ROOT}/.env" \
  "${HOME}/.openclaw/.env" \
  "${OC_ROOT}/workspace/.env" \
  "${HOME}/.openclaw/workspace/.env"; do
  _load_env_file "$ENV_FILE" 2>/dev/null || true
done

# Also pull env.vars from openclaw.json if python3 is available.
if command -v python3 >/dev/null 2>&1 && [[ -f "${OC_ROOT}/openclaw.json" ]]; then
  while IFS='=' read -r k v; do
    [[ -n "$k" && -n "$v" ]] && [[ -z "${!k:-}" ]] && export "$k"="$v"
  done < <(python3 - "${OC_ROOT}/openclaw.json" 2>/dev/null <<'PYEOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
    env_vars = (cfg.get("env", {}) or {}).get("vars", {}) or {}
    for k, v in env_vars.items():
        if isinstance(v, str) and v:
            print(f"{k}={v}")
except Exception:
    pass
PYEOF
  )
fi

# The location PIT — canonical PIT names first, then GOHIGHLEVEL_*/GHL_* aliases.
PIT=""
for VAR in GHL_PRIVATE_INTEGRATION_TOKEN GOHIGHLEVEL_AGENCY_PIT GHL_PIT_TOKEN GOHIGHLEVEL_API_KEY GHL_API_KEY; do
  if [[ -n "${!VAR:-}" ]]; then PIT="${!VAR}"; break; fi
done

# The sub-account (location) id — canonical GOHIGHLEVEL_LOCATION_ID first.
LOCATION_ID=""
for VAR in GOHIGHLEVEL_LOCATION_ID GHL_LOCATION_ID; do
  if [[ -n "${!VAR:-}" ]]; then LOCATION_ID="${!VAR}"; break; fi
done

if [[ -z "$PIT" || -z "$LOCATION_ID" ]]; then
  _log "SKIP no runtime PIT and/or location id configured (checked GHL_PRIVATE_INTEGRATION_TOKEN/GOHIGHLEVEL_API_KEY + GOHIGHLEVEL_LOCATION_ID/GHL_LOCATION_ID). Nothing to check."
  exit 0
fi

if ! command -v curl >/dev/null 2>&1; then
  _log "WARN curl not found — cannot probe the PIT. Skipping."
  exit 0
fi

# ---------------------------------------------------------------------------
# Probe: the skill's own in-scope runtime READ (conversations.readonly).
# A valid PIT returns 2xx even with zero results; a dead PIT returns 401.
# ---------------------------------------------------------------------------
PROBE_URL="${GHL_API_BASE}/conversations/search?locationId=${LOCATION_ID}&limit=1"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
  -H "Authorization: Bearer ${PIT}" \
  -H "Version: ${GHL_API_VERSION}" \
  -H "Content-Type: application/json" \
  "$PROBE_URL" 2>/dev/null || echo "000")"

case "$HTTP_CODE" in
  2??)
    _log "PASS runtime PIT is VALID — ${PROBE_URL%%\?*} returned HTTP ${HTTP_CODE}."
    touch "$PASS_STAMP"
    exit 0
    ;;
  401)
    _log "FAIL runtime PIT is DEAD/EXPIRED (HTTP 401). Resolving client notification target..."
    ;;
  *)
    # 400 / 403 / 5xx / 000 network — ambiguous or transient. Operator-log only;
    # do NOT spam the client (a scope/transient issue is not a dead token).
    _log "WARN probe returned HTTP ${HTTP_CODE} (ambiguous/transient — not a clean 401). Operator: verify PIT scope conversations.readonly + location id. NOT notifying the client."
    exit 0
    ;;
esac

# ---------------------------------------------------------------------------
# 401 path: resolve the CLIENT's Telegram chat (never an operator id).
# Mirrors the resolver in Skill 44's check-ghl-token-liveness.sh.
# ---------------------------------------------------------------------------
if [[ -f "$NOTIFIED_STAMP" ]]; then
  _log "already notified the client today (${TODAY}) — not re-sending. Delete ${NOTIFIED_STAMP} to force."
  exit 1
fi

CLIENT_CHAT_ID=""
# 1) Explicit client target from env wins (never the excluded operator id).
if [[ -n "$CLIENT_TELEGRAM_CHAT_ID" ]] && \
   { [[ -z "$OPERATOR_TELEGRAM_CHAT_ID" ]] || [[ "$CLIENT_TELEGRAM_CHAT_ID" != "$OPERATOR_TELEGRAM_CHAT_ID" ]]; }; then
  CLIENT_CHAT_ID="$CLIENT_TELEGRAM_CHAT_ID"
fi
# 2) Else resolve from openclaw.json allowFrom, EXCLUDING the operator id supplied
#    via $OPERATOR_TELEGRAM_CHAT_ID (empty by default — no id is hardcoded).
if [[ -z "$CLIENT_CHAT_ID" ]] && command -v python3 >/dev/null 2>&1 && [[ -f "${OC_ROOT}/openclaw.json" ]]; then
  CLIENT_CHAT_ID=$(python3 - "${OC_ROOT}/openclaw.json" 2>/dev/null <<'PYEOF'
import json, os, sys

# The single operator id to exclude comes from the environment (default empty);
# a UNIVERSAL skill hardcodes NO chat ids.
_op = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "").strip()
OPERATOR_IDS = {_op} if _op else set()

def valid_client_chat(v, bot_id=""):
    if not isinstance(v, (str, int)):
        return ""
    s = str(v).strip().replace("telegram:", "").replace("tg:", "")
    if not s:
        return ""
    digits = s.lstrip("-")
    if not (digits.isdigit() and 6 <= len(digits) <= 20):
        return ""
    if bot_id and s == bot_id:
        return ""
    if s in OPERATOR_IDS:
        return ""
    return s

cfg = {}
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    pass

bot_id = ""
bt = (cfg.get("channels", {}).get("telegram", {}) or {}).get("botToken", "") or ""
if ":" in bt:
    bot_id = bt.split(":")[0]

s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = valid_client_chat(s0, bot_id)
    if cid:
        print(cid); raise SystemExit(0)

for v in (cfg.get("channels", {}).get("telegram", {}) or {}).get("allowFrom", []) or []:
    cid = valid_client_chat(v, bot_id)
    if cid:
        print(cid); raise SystemExit(0)

for v in (cfg.get("commands", {}) or {}).get("ownerAllowFrom", []) or []:
    cid = valid_client_chat(v, bot_id)
    if cid:
        print(cid); raise SystemExit(0)

print("")
PYEOF
  )
fi

if [[ -z "${CLIENT_CHAT_ID:-}" ]]; then
  _log "WARN no client chat ID resolved — cannot send notification. Check openclaw.json allowFrom."
  _log "     Operator action required: the runtime PIT (GHL_PRIVATE_INTEGRATION_TOKEN) is expired/invalid (401)."
  exit 1
fi

if [[ -n "$OPERATOR_TELEGRAM_CHAT_ID" && "$CLIENT_CHAT_ID" == "$OPERATOR_TELEGRAM_CHAT_ID" ]]; then
  _log "WARN resolved chat ID matches the excluded operator id (OPERATOR_TELEGRAM_CHAT_ID) — refusing to send there."
  _log "     Operator action required: the runtime PIT is expired/invalid (401)."
  exit 1
fi

# ---------------------------------------------------------------------------
# Send the client-facing refresh message (plain English, no jargon).
# ---------------------------------------------------------------------------
NOTIFICATION_MSG="Hi — a quick heads-up from your AI agent.

My connection to your GoHighLevel / Convert and Flow account needs a quick refresh, so I can keep sending replies to your leads. The secure key (your Private Integration Token) has stopped working — this is normal and only takes a couple of minutes to fix.

Here is how to refresh it:

1. Log into GoHighLevel / Convert and Flow, then open Settings -> Private Integrations (or API Keys).

2. Re-issue (or copy) your Private Integration Token. Make sure it still has the messaging, calendars, and invoices permissions it started with.

3. Send it to me like this:
   Here is my updated GoHighLevel Private Integration Token: [paste here] — please update my settings.

That is it — once you send it, I will update your settings and confirm replies are flowing again. If anything looks different from your original setup, just reply and I will walk you through it."

_log "Sending PIT-expired notification to client chat ${CLIENT_CHAT_ID}..."
if command -v openclaw >/dev/null 2>&1 && \
   openclaw message send --channel telegram --target "$CLIENT_CHAT_ID" --message "$NOTIFICATION_MSG" >/dev/null 2>&1; then
  _log "DONE notification sent to client chat ${CLIENT_CHAT_ID}."
  touch "$NOTIFIED_STAMP"
else
  _log "WARN openclaw message send failed (or CLI absent) — client was NOT notified. Check Telegram config."
fi

exit 1
