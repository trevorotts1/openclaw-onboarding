#!/usr/bin/env bash
# check-ghl-token-liveness.sh — Daily GHL Firebase refresh-token liveness check.
#
# WHY THIS EXISTS
# ---------------
# Skill 44 (convert-and-flow-operator) depends on a live
# GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN to perform write operations against
# GoHighLevel / Convert and Flow's internal API. (Per operator request the daily
# check is cross-referenced from Skill 46, the Kie callback relay; Skill 46 does
# NOT itself consume the GHL token.) This script:
#
#   1. Resolves the client box's refresh token from the standard env-store order.
#   2. POSTs it to Google's securetoken.googleapis.com exchange endpoint (the
#      EXACT same URL and key already used in seed-ghl-auth.py and the
#      Skill 44 transport engine).
#   3. Classifies the result as VALID (exchange returns 200 + id_token) or
#      INVALID (400 with TOKEN_EXPIRED / USER_DISABLED / INVALID_REFRESH_TOKEN).
#   4. On VALID: logs a one-line PASS and exits 0. No notification is sent.
#   5. On INVALID: sends a client-facing notification via `openclaw message send`
#      explaining how to re-grab the token, then exits 1.
#
# IDEMPOTENT / ONCE-PER-DAY
# -------------------------
# A daily state file ($STATE_DIR/ghl-token-liveness-<date>.ok) prevents the
# notification from firing more than once per calendar day. The guard uses the
# date in UTC. Delete the state file to force a re-check.
#
# NOTIFICATION TARGET
# -------------------
# The notification always goes to the CLIENT's own configured Telegram chat
# (resolved from openclaw.json allowFrom, never to operator IDs). If no
# client chat is found the script logs a warning and exits 0 (non-blocking).
#
# OPERATOR IDs ARE NEVER TARGETED — hard-coded exclusion below.
#
# USAGE
#   bash check-ghl-token-liveness.sh
#
# EXIT CODES
#   0  token VALID (or already-passed today — idempotent)
#   1  token INVALID or expired (client notified once per day)
#   2  no token configured — nothing to check (exit 0 on the PASS branch below)
#
# bash-not-zsh: always invoke via `bash`, never `zsh` (strict-glob in zsh may
# silently abort on array expansions). Mirror of all other pipeline scripts.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants — PRESERVED from seed-ghl-auth.py and the Skill 44 transport engine.
# FIREBASE_API_KEY is GoHighLevel's public Firebase web API key (NOT a secret;
# it is hardcoded in the transport engine and in seed-ghl-auth.py).
# ---------------------------------------------------------------------------
FIREBASE_API_KEY="AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
FIREBASE_TOKEN_URL="https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}"

# Env-var resolution order — IDENTICAL to seed-ghl-auth.py and transport.py.
REFRESH_ENV_VARS=(
  "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN"
  "CAF_FIREBASE_REFRESH_TOKEN"
  "GHL_FIREBASE_REFRESH_TOKEN"
)

# Operator Telegram chat IDs — NEVER send notifications here.
# Trevor + LeAnne + Spaulding (from INSTALL-CONTRACT.md / ensure-pipeline-crons.sh).
OPERATOR_CHAT_IDS_RE='^(5252140759|6663821679|6771245262)$'

# ---------------------------------------------------------------------------
# State directory — used for the once-per-day idempotency guard.
# ---------------------------------------------------------------------------
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"
else
  echo "[ghl-token-liveness] WARN no OpenClaw root found; skipping check." >&2
  exit 0
fi

STATE_DIR="${OC_ROOT}/workspace/ghl-token-liveness"
mkdir -p "$STATE_DIR"

TODAY=$(date -u +%Y-%m-%d)
PASS_STAMP="${STATE_DIR}/ghl-token-liveness-${TODAY}.ok"

_log() { echo "[ghl-token-liveness] $*"; }

# ---------------------------------------------------------------------------
# Step 1 — Once-per-day guard (VALID branch short-circuit)
# ---------------------------------------------------------------------------
if [[ -f "$PASS_STAMP" ]]; then
  _log "PASS already confirmed today (${TODAY}) — skipping. Delete ${PASS_STAMP} to force recheck."
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 2 — Resolve the refresh token from the standard env-store order.
# Search path mirrors seed-ghl-auth.py + MEMORY client-box-env-stores:
#   secrets/.env  → openclaw.json env.vars → workspace/.env
# ---------------------------------------------------------------------------
_load_env_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  # Source only KEY=VALUE lines; skip comments, blanks, and compound statements.
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    if [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]]; then
      local k="${BASH_REMATCH[1]}" v="${BASH_REMATCH[2]}"
      # Strip surrounding quotes (single or double) if present.
      v="${v#\'}" ; v="${v%\'}"
      v="${v#\"}" ; v="${v%\"}"
      # Only set if not already in environment (process env wins over file).
      [[ -z "${!k:-}" ]] && export "$k"="$v"
    fi
  done < "$f"
}

# Load env files in priority order (lowest wins — process env already wins).
for ENV_FILE in \
  "${OC_ROOT}/secrets/.env" \
  "${HOME}/.openclaw/secrets/.env" \
  "/data/.openclaw/secrets/.env" \
  "${OC_ROOT}/workspace/.env" \
  "${HOME}/.openclaw/workspace/.env" \
  "/data/.openclaw/workspace/.env"; do
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

# Resolve the first non-empty refresh token.
REFRESH_TOKEN=""
REFRESH_VAR=""
for VAR in "${REFRESH_ENV_VARS[@]}"; do
  VAL="${!VAR:-}"
  if [[ -n "$VAL" ]]; then
    REFRESH_TOKEN="$VAL"
    REFRESH_VAR="$VAR"
    break
  fi
done

if [[ -z "$REFRESH_TOKEN" ]]; then
  _log "SKIP no GHL Firebase refresh token found (checked ${REFRESH_ENV_VARS[*]}). Skills 44/46 workflow writes will use Tier 4 backstop."
  # Not a failure — the token may simply not be configured on this box yet.
  exit 0
fi

_log "Checking token liveness (source: ${REFRESH_VAR}, length: ${#REFRESH_TOKEN}) ..."

# ---------------------------------------------------------------------------
# Step 3 — POST to securetoken.googleapis.com (same logic as seed-ghl-auth.py).
# ---------------------------------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  # Python path — most reliable; handles SSL context, timeouts, error body parse.
  EXCHANGE_RESULT=$(python3 - "$REFRESH_TOKEN" "$FIREBASE_TOKEN_URL" 2>&1 <<'PYEOF'
import json, os, ssl, sys, urllib.error, urllib.request

refresh_token = sys.argv[1]
url = sys.argv[2]

body = f"grant_type=refresh_token&refresh_token={refresh_token}"
req = urllib.request.Request(
    url,
    data=body.encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    method="POST",
)
ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        resp = json.loads(r.read())
    # VALID: 200 + id_token present.
    if resp.get("id_token") or resp.get("access_token"):
        print("VALID")
    else:
        print("INVALID:NO_ID_TOKEN")
except urllib.error.HTTPError as e:
    detail = ""
    try:
        detail = json.loads(e.read()).get("error", {}).get("message", "")
    except Exception:
        detail = str(e.code)
    print(f"INVALID:{detail}")
except Exception as e:
    print(f"NETWORK_ERROR:{e}")
PYEOF
  )
elif command -v curl >/dev/null 2>&1; then
  # curl fallback — used when python3 is absent (rare on fleet boxes).
  HTTP_BODY=$(curl -s -w "\n%{http_code}" \
    --max-time 15 \
    -X POST "$FIREBASE_TOKEN_URL" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "grant_type=refresh_token" \
    --data-urlencode "refresh_token=${REFRESH_TOKEN}" 2>/dev/null) || HTTP_BODY=""
  HTTP_CODE="${HTTP_BODY##*$'\n'}"
  HTTP_BODY="${HTTP_BODY%$'\n'*}"
  if [[ "$HTTP_CODE" == "200" ]] && echo "$HTTP_BODY" | grep -q '"id_token"'; then
    EXCHANGE_RESULT="VALID"
  else
    ERROR_MSG=$(echo "$HTTP_BODY" | grep -o '"message":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "HTTP_${HTTP_CODE:-unknown}")
    EXCHANGE_RESULT="INVALID:${ERROR_MSG}"
  fi
else
  _log "WARN neither python3 nor curl found — cannot check token liveness. Skipping."
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 4 — Classify result.
# ---------------------------------------------------------------------------
if [[ "$EXCHANGE_RESULT" == "VALID" ]]; then
  _log "PASS token is VALID — exchange returned 200 + id_token."
  # Write the once-per-day stamp so subsequent runs short-circuit.
  touch "$PASS_STAMP"
  exit 0
fi

# Token is INVALID. Log the error code.
ERROR_CODE="${EXCHANGE_RESULT#INVALID:}"
_log "FAIL token is INVALID (${ERROR_CODE}). Resolving client notification target..."

# ---------------------------------------------------------------------------
# Step 5 — Resolve the CLIENT's Telegram chat ID.
# Must NEVER target operator IDs. Mirrors the resolver in ensure-pipeline-crons.sh.
# ---------------------------------------------------------------------------
CLIENT_CHAT_ID=""
if command -v python3 >/dev/null 2>&1 && [[ -f "${OC_ROOT}/openclaw.json" ]]; then
  CLIENT_CHAT_ID=$(python3 - "${OC_ROOT}/openclaw.json" 2>/dev/null <<'PYEOF'
import json, os, sys, re

OPERATOR_IDS = {"5252140759", "6663821679", "6771245262"}

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

# S0: explicit env override
s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = valid_client_chat(s0, bot_id)
    if cid:
        print(cid)
        raise SystemExit(0)

# S1: channels.telegram.allowFrom
for v in (cfg.get("channels", {}).get("telegram", {}) or {}).get("allowFrom", []) or []:
    cid = valid_client_chat(v, bot_id)
    if cid:
        print(cid)
        raise SystemExit(0)

# S2: commands.ownerAllowFrom
for v in (cfg.get("commands", {}) or {}).get("ownerAllowFrom", []) or []:
    cid = valid_client_chat(v, bot_id)
    if cid:
        print(cid)
        raise SystemExit(0)

print("")
PYEOF
  )
fi

if [[ -z "${CLIENT_CHAT_ID:-}" ]]; then
  _log "WARN no client chat ID resolved — cannot send notification. Check openclaw.json allowFrom."
  _log "     Operator action required: token at ${REFRESH_VAR} is expired/invalid (${ERROR_CODE})."
  exit 1
fi

# Sanity-check: never send to an operator ID even if the resolver slipped.
if [[ "$CLIENT_CHAT_ID" =~ $OPERATOR_CHAT_IDS_RE ]]; then
  _log "WARN resolved chat ID ${CLIENT_CHAT_ID} is an operator ID — refusing to send there."
  _log "     Operator action required: token at ${REFRESH_VAR} is expired/invalid (${ERROR_CODE})."
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 6 — Send the client-facing notification via openclaw message send.
# Plain English, no technical jargon, 8 numbered re-grab steps inline.
# ---------------------------------------------------------------------------

NOTIFICATION_MSG="Hi — just a heads-up from your AI agent.

Your workflow automation connection to Convert and Flow (GoHighLevel) needs a quick refresh. The secure key that lets me build automations for you has expired. This is normal and only takes about 2 minutes to fix.

Here is how to refresh it (same steps as your original setup):

1. Open Chrome and log into Convert and Flow at app.convertandflow.com. Log out first, then log back in — this makes sure you get a fresh key.

2. Click the pinkish Convert and Flow Token Grabber icon in your Chrome toolbar. If you do not see it, click the puzzle-piece icon first, then find the Token Grabber and click the pin to bring it back.

3. Click \"Grab the token,\" then click \"Copy the token.\"

4. Send me a message with the copied key, like this:
   Here is the Convert and Flow GHL Firebase token: [paste here] — please update my settings.

That is it. Once you send it, I will update your settings and confirm it is working again.

If you have any trouble finding the Token Grabber extension, reply and I will walk you through each step."

_log "Sending token-expired notification to client chat ${CLIENT_CHAT_ID}..."

if openclaw message send --channel telegram --target "$CLIENT_CHAT_ID" --message "$NOTIFICATION_MSG" >/dev/null 2>&1; then
  _log "DONE notification sent to client chat ${CLIENT_CHAT_ID}."
  # Write a per-day FAIL stamp so we do not spam the same notification again today.
  touch "${STATE_DIR}/ghl-token-liveness-${TODAY}.notified"
else
  _log "WARN openclaw message send failed — client was NOT notified. Check Telegram config."
fi

exit 1
