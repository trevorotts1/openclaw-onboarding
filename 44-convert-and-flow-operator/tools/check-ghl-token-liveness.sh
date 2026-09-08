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
#   0  token VALID (or already-passed today — idempotent), or no token configured (.no-token stamp)
#   1  token INVALID — CONFIRMED credential failure (client notified once per day)
#   2  CONFIG PROBLEM — operator triage, client NEVER notified: placeholder credential, CRLF
#      secrets file, process-env value masking the secrets file, transient/ambiguous exchange
#      result, or DRIFT between the gateway env snapshot and secrets/.env (.drift stamp)
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
  "PODCAST_ENGINE_GHL_FIREBASE_REFRESH_TOKEN"
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
NOTIFIED_STAMP="${STATE_DIR}/ghl-token-liveness-${TODAY}.notified"

_log() { echo "[ghl-token-liveness] $*"; }

# ---------------------------------------------------------------------------
# Step 1 — Once-per-day guard (VALID branch short-circuit)
# ---------------------------------------------------------------------------
if [[ -f "$PASS_STAMP" ]]; then
  _log "PASS already confirmed today (${TODAY}) — skipping. Delete ${PASS_STAMP} to force recheck."
  exit 0
fi

# INVALID-token idempotency (symmetry with the PASS guard above): if today's
# check already found the token dead AND the client was already notified today,
# do NOT re-send. A second run the same day (double-fire cron, manual run, or
# fleet auto-redispatch) must not spam the client — this honours the "at most
# once per calendar day" contract on the INVALID branch too. Still exit 1 to
# signal the token is unhealthy. Delete the .notified stamp to force a re-notify.
if [[ -f "$NOTIFIED_STAMP" ]]; then
  _log "INVALID already detected today (${TODAY}) and client already notified — not re-sending (idempotent). Delete ${NOTIFIED_STAMP} to force re-notify."
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 2 — Resolve the refresh token with ENGINE PARITY.
#
# The Skill 44 engine is always entered through the `caf` wrapper
# (tools/engine/caf), which does `set -a; source ~/.openclaw/secrets/.env`.
# For the ENGINE, therefore, the canonical secrets file OVERRIDES whatever the
# gateway's process env carried (per key; last line in the file wins; `export`
# prefixes honoured). This check MUST test the same credential the engine will
# use, so it emulates that merge: file value when the file DEFINES the key,
# inherited process-env value otherwise, then the first non-empty candidate.
#
# WHY (landmine 2026-06-23 → 2026-08-27, 65 client notifications on one box):
# the old loader let the process env win. The gateway's env is a STATIC
# snapshot taken at process start (OpenClaw applies openclaw.json env.vars and
# ~/.openclaw/.env only for vars that are still missing), so a 63-character
# placeholder under GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN in env.vars beat the
# real 503-character token in secrets/.env for 47 days while the engine — which
# sources the file — was working. The CLIENT was told daily to re-grab a token
# that was already fine. Every condition below that is not a confirmed dead
# credential is an OPERATOR condition and never reaches the client.
#
# openclaw.json env.vars and workspace/.env are no longer read directly: the
# engine never reads them either — they reach it only through the process env,
# which is snapshotted here as ENVVAL_*.
# ---------------------------------------------------------------------------

# Inherited process env, captured BEFORE any file is read.
for VAR in "${REFRESH_ENV_VARS[@]}"; do
  eval "ENVVAL_${VAR}=\"\${${VAR}:-}\""
  eval "FILEVAL_${VAR}=''"
  eval "FILEDEF_${VAR}=0"
done

# Canonical secrets file — the one caf sources (first that exists).
CANON_FILE=""
for f in "${OC_ROOT}/secrets/.env" "${HOME}/.openclaw/secrets/.env" "/data/.openclaw/secrets/.env"; do
  [[ -f "$f" ]] && { CANON_FILE="$f"; break; }
done

# Parse `KEY=VALUE` / `export KEY=VALUE` into FILEVAL_<KEY> (+ FILEDEF_<KEY>=1).
# Last line wins (bash `source` semantics). Surrounding quotes and trailing
# whitespace are stripped (bash would not keep trailing blanks of an unquoted
# assignment). A CR is stripped but REMEMBERED: `source` keeps it, so the
# engine would present a corrupt token — that is a config problem, not expiry.
FILE_HAD_CR=0
_load_canon_file() {
  local f="$1" line k v
  [[ -f "$f" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    if [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Z_][A-Z0-9_]*)=(.*)$ ]]; then
      k="${BASH_REMATCH[2]}"; v="${BASH_REMATCH[3]}"
      [[ "$v" == *$'\r'* ]] && FILE_HAD_CR=1
      v="${v//$'\r'/}"
      v="${v%"${v##*[![:space:]]}"}"
      v="${v#\'}" ; v="${v%\'}"
      v="${v#\"}" ; v="${v%\"}"
      eval "FILEVAL_${k}=\$v"
      eval "FILEDEF_${k}=1"
    fi
  done < "$f"
}
_load_canon_file "$CANON_FILE" 2>/dev/null || true

_fp() { printf '%s' "$1" | shasum -a 256 2>/dev/null | cut -c1-8; }

# A documentation placeholder is not a credential. Real Firebase refresh tokens
# are several hundred characters; the 2026 landmine's impostor was 63.
_is_placeholder() {
  local v="$1"
  [[ -z "$v" ]] && return 0
  (( ${#v} < 100 )) && return 0
  case "$v" in
    changeme*|CHANGEME*|xxx*|XXX*|your-*|YOUR-*|your_*|YOUR_*|*_HERE|*-here|*_here|"<"*">"|'${'*'}') return 0 ;;
  esac
  return 1
}

# Emulated `set -a; source` merge, then the engine's first-non-empty pick.
REFRESH_TOKEN=""; REFRESH_VAR=""; REFRESH_SOURCE=""
FILE_HAS_CANDIDATE=0
for VAR in "${REFRESH_ENV_VARS[@]}"; do
  fdef="$(eval "printf '%s' \"\${FILEDEF_${VAR}}\"")"
  fval="$(eval "printf '%s' \"\${FILEVAL_${VAR}}\"")"
  eval_="$(eval "printf '%s' \"\${ENVVAL_${VAR}}\"")"
  [[ -n "$fval" ]] && FILE_HAS_CANDIDATE=1
  if [[ "$fdef" == "1" ]]; then merged="$fval"; origin="secrets-file"; else merged="$eval_"; origin="process-env"; fi
  if [[ -z "$REFRESH_TOKEN" && -n "$merged" ]]; then
    REFRESH_TOKEN="$merged"; REFRESH_VAR="$VAR"; REFRESH_SOURCE="$origin"
  fi
done

# DRIFT: a candidate whose inherited process-env value differs from the file, or
# exists only in the process env. Fingerprints only — values are never printed.
DRIFT=""
for VAR in "${REFRESH_ENV_VARS[@]}"; do
  ev="$(eval "printf '%s' \"\${ENVVAL_${VAR}}\"")"
  fv="$(eval "printf '%s' \"\${FILEVAL_${VAR}}\"")"
  fd="$(eval "printf '%s' \"\${FILEDEF_${VAR}}\"")"
  [[ -n "$ev" ]] || continue
  if [[ "$fd" != "1" ]]; then
    DRIFT="${DRIFT}${DRIFT:+; }${VAR}: process-env len=${#ev} fp=$(_fp "$ev") vs secrets-file ABSENT"
  elif [[ "$ev" != "$fv" ]]; then
    DRIFT="${DRIFT}${DRIFT:+; }${VAR}: process-env len=${#ev} fp=$(_fp "$ev") vs secrets-file len=${#fv} fp=$(_fp "$fv")"
  fi
done
[[ -n "$DRIFT" ]] && _log "DRIFT (operator condition — the gateway's start-time env snapshot disagrees with ${CANON_FILE:-secrets/.env}): ${DRIFT}"

_config_problem() { # <reason lines...> — operator triage, client NEVER notified, exit 2
  local l; for l in "$@"; do _log "CONFIG PROBLEM: $l"; done
  _log "  This is NOT a confirmed expired token and the client has NOT been notified."
  touch "${STATE_DIR}/ghl-token-liveness-${TODAY}.config-problem"
  exit 2
}

if [[ -z "$REFRESH_TOKEN" ]]; then
  if [[ -n "$DRIFT" ]]; then
    _config_problem "the engine has NO usable refresh token (secrets file defines the key(s) empty, or blanks them) while the gateway's process env carries one: ${DRIFT}" \
                    "Operator: an empty VAR= line in ${CANON_FILE} blanks the engine's value (caf sources the file). Put the real token there."
  fi
  _log "SKIP no GHL Firebase refresh token found (checked ${REFRESH_ENV_VARS[*]} in ${CANON_FILE:-<no secrets file>} and the process env). Skills 44/46 workflow writes will use Tier 4 backstop."
  touch "${STATE_DIR}/ghl-token-liveness-${TODAY}.no-token"
  exit 0
fi

if [[ "$FILE_HAD_CR" -eq 1 ]]; then
  _config_problem "${CANON_FILE} has CRLF line endings — caf's \`source\` keeps the CR and hands the engine a corrupt token. Operator: convert the file to LF."
fi

if _is_placeholder "$REFRESH_TOKEN"; then
  _config_problem "the credential the engine would use (${REFRESH_VAR} from ${REFRESH_SOURCE}, length ${#REFRESH_TOKEN}) is a PLACEHOLDER, not a token." \
                  "Operator: put the real token in ${CANON_FILE:-${OC_ROOT}/secrets/.env} under ${REFRESH_VAR}; if the placeholder is in the process env, fix service-env / ~/.openclaw/.env / env.vars and restart the gateway."
fi

if [[ "$REFRESH_SOURCE" == "process-env" && "$FILE_HAS_CANDIDATE" -eq 1 ]]; then
  _config_problem "the engine would use ${REFRESH_VAR} from the gateway's process env, which MASKS a real credential held under another name in ${CANON_FILE}." \
                  "Operator: remove the stale ${REFRESH_VAR} from service-env / ~/.openclaw/.env / env.vars (or add it to secrets/.env) and restart the gateway."
fi

_log "Checking token liveness (var: ${REFRESH_VAR}, source: ${REFRESH_SOURCE}, length: ${#REFRESH_TOKEN}, fp: $(_fp "$REFRESH_TOKEN")) ..."

# Test hook — resolution only: no network call, no notification, no stamp.
if [[ "${GHL_LIVENESS_RESOLVE_ONLY:-0}" == "1" ]]; then
  echo "RESOLVED var=${REFRESH_VAR} source=${REFRESH_SOURCE} len=${#REFRESH_TOKEN} fp=$(_fp "$REFRESH_TOKEN") drift=$([[ -n "$DRIFT" ]] && echo yes || echo no)"
  exit 0
fi

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
# Step 4 — Classify result. ONLY a confirmed credential failure may reach the
# client (the header always promised this; the code never enforced it — a DNS
# blip, a 429 or a 5xx from Google used to send the "re-grab your token" text).
# ---------------------------------------------------------------------------
if [[ "$EXCHANGE_RESULT" == "VALID" ]]; then
  _log "PASS token is VALID — exchange returned 200 + id_token (var: ${REFRESH_VAR}, source: ${REFRESH_SOURCE})."
  touch "$PASS_STAMP"
  if [[ -n "$DRIFT" ]]; then
    _log "DRIFT PERSISTS: the engine (caf sources secrets/.env) is healthy, but the gateway's process env carries a different value for a candidate: ${DRIFT}"
    _log "  Operator action: re-run 44-convert-and-flow-operator/tools/engine/wire-ghl-env.sh, sync service-env / ~/.openclaw/.env to secrets/.env, restart the gateway. Client NOT notified."
    touch "${STATE_DIR}/ghl-token-liveness-${TODAY}.drift"
    exit 2
  fi
  exit 0
fi

ERROR_CODE="${EXCHANGE_RESULT#*:}"
case "$EXCHANGE_RESULT" in
  INVALID:TOKEN_EXPIRED*|INVALID:USER_DISABLED*|INVALID:USER_NOT_FOUND*|INVALID:INVALID_REFRESH_TOKEN*)
    _log "FAIL token is INVALID (${ERROR_CODE}) — confirmed credential failure (var: ${REFRESH_VAR}, source: ${REFRESH_SOURCE}). Resolving client notification target..."
    ;;
  *)
    _config_problem "the exchange did not return a classifiable credential failure (${EXCHANGE_RESULT%%:*}: ${ERROR_CODE}) — transient/ambiguous; operator triage."
    ;;
esac

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

if [[ "${GHL_LIVENESS_NO_SEND:-0}" == "1" ]]; then
  _log "NO_SEND hook: would notify client chat ${CLIENT_CHAT_ID} — not sending (test mode)."
  exit 1
fi

if openclaw message send --channel telegram --target "$CLIENT_CHAT_ID" --message "$NOTIFICATION_MSG" >/dev/null 2>&1; then
  _log "DONE notification sent to client chat ${CLIENT_CHAT_ID}."
  # Write a per-day FAIL stamp so we do not spam the same notification again today.
  # The top-of-script guard reads this to short-circuit any later run today.
  touch "$NOTIFIED_STAMP"
else
  _log "WARN openclaw message send failed — client was NOT notified. Check Telegram config."
fi

exit 1
