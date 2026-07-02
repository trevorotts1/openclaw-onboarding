#!/usr/bin/env bash
# mc-route.sh — SIGNED general task-routing helper (fleet-wide).
#
# This is the GENERAL version of route-presentation.sh: the same signed
# Command-Center ingest helper, but the department is an ARGUMENT instead of the
# hardcoded "presentations". It is the shipped implementation behind the
# `mc-route__route_task` routing tool the CEO/orchestrator uses to route ANY
# task to ANY department without self-executing.
#
#   USAGE:  mc-route.sh <department_slug> <title> [description...]
#
#     <department_slug>   target workspace/department (e.g. presentations,
#                         general-task, social-media, video). REQUIRED.
#     <title>             short task title (truncated to 120 chars). REQUIRED.
#     [description...]    the rest of the args are joined with single spaces
#                         into the task description (owner message, verbatim).
#
# WHY (identical to route-presentation.sh): the Command Center ships FAIL-CLOSED.
# Middleware 503s external ingest when WEBHOOK_SECRET is unset, and 401s when
# MC_API_TOKEN is set but no Bearer is sent; the /api/tasks/ingest route 401s when
# WEBHOOK_SECRET is set and x-webhook-signature is missing. A loopback curl gets NO
# same-origin exemption (it sends no Origin). So — exactly like the sanctioned
# producer 06-ghl-install-pages/tools/cc_board.py and route-presentation.sh — this
# helper signs BOTH layers:
#   Authorization: Bearer <MC_API_TOKEN>                          (middleware layer)
#   x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (route layer)
# Secrets are resolved at RUNTIME from the box's stores; NO secret value is ever
# written into this file.
#
# EXIT 0 on a 2xx ingest; non-zero on failure — on non-zero the CEO must tell the
# owner it is escalating to the operator (never self-intake, never ask intake
# questions, never retry forever).
#
# OPTIONAL ENV OVERRIDES (all have safe defaults; the security-critical secret
# resolution + signing are IDENTICAL to route-presentation.sh):
#   MC_ROUTE_INGEST_URL   ingest endpoint    (default http://127.0.0.1:4000/api/tasks/ingest)
#   MC_ROUTE_SOURCE       payload "source"   (default telegram)
#   MC_ROUTE_PRIORITY     payload "priority" (default medium)
#   MC_ROUTE_MAX_RETRIES  retries after 1st  (default 2)
set -uo pipefail

INGEST_URL="${MC_ROUTE_INGEST_URL:-http://127.0.0.1:4000/api/tasks/ingest}"
MAX_RETRIES="${MC_ROUTE_MAX_RETRIES:-2}"
SOURCE="${MC_ROUTE_SOURCE:-telegram}"
PRIORITY="${MC_ROUTE_PRIORITY:-medium}"

DEPARTMENT_SLUG="${1:-}"
TITLE="${2:-}"
# The rest of the args (3..N) form the description, joined with single spaces.
if [ "$#" -gt 2 ]; then
  shift 2
  DESCRIPTION="$*"
else
  DESCRIPTION=""
fi

_escalate() {
  echo "mc-route: FAILED — $1" >&2
  echo "ESCALATE_TO_OPERATOR: task routing failed. The CEO must tell the owner it is escalating this to the operator. Do NOT self-intake, do NOT ask intake questions, do NOT retry." >&2
  exit 1
}

[ -n "$DEPARTMENT_SLUG" ] || _escalate "empty department_slug argument (usage: mc-route.sh <department_slug> <title> [description...])"
[ -n "$TITLE" ]          || _escalate "empty title argument (usage: mc-route.sh <department_slug> <title> [description...])"

# ── Runtime secret resolution (reads only; never hardcoded) ──────────────────
# Store order mirrors the Command Center's own env precedence so the signature
# matches what the CC server validates against; the WEBHOOK_SECRET alias order
# (WEBHOOK_SECRET, then CC_WEBHOOK_SECRET) mirrors cc_board.py. Live process env
# is the last-resort fallback. IDENTICAL to route-presentation.sh.
_ENV_STORES=(
  "$HOME/projects/command-center/.env.local"
  "$HOME/projects/command-center/.env"
  "/data/projects/command-center/.env.local"
  "/data/projects/command-center/.env"
  "$HOME/.openclaw/secrets/.env"
  "/data/.openclaw/secrets/.env"
)

_resolve() {
  # $@ = candidate key names (aliases). First non-empty across the dotenv stores
  # (in order) then the live process env. Prints ONLY the value. Uses python3 for
  # robust dotenv parsing (export / quotes / comments).
  RP_KEYS="$*" python3 - "${_ENV_STORES[@]}" <<'PYRESOLVE'
import os, sys
keys = os.environ.get("RP_KEYS", "").split()
stores = sys.argv[1:]

def parse(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[len("export "):]
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip(); v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                out[k] = v
    except Exception:
        return {}
    return out

for path in stores:
    kv = parse(path)
    for k in keys:
        if kv.get(k):
            sys.stdout.write(kv[k]); sys.exit(0)
for k in keys:
    v = os.environ.get(k)
    if v:
        sys.stdout.write(v); sys.exit(0)
PYRESOLVE
}

MC_API_TOKEN="$(_resolve MC_API_TOKEN)"
WEBHOOK_SECRET="$(_resolve WEBHOOK_SECRET CC_WEBHOOK_SECRET)"

# ── Build the EXACT raw body once (compact JSON, like cc_board.py) ───────────
BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/mc-route.XXXXXX")" || _escalate "mktemp failed"
trap 'rm -f "$BODY_FILE"' EXIT
if ! DEPARTMENT_SLUG="$DEPARTMENT_SLUG" TITLE="$TITLE" DESCRIPTION="$DESCRIPTION" \
     SOURCE="$SOURCE" PRIORITY="$PRIORITY" python3 - >"$BODY_FILE" <<'PYBODY'
import json, os, sys
payload = {
    "title": os.environ.get("TITLE", "")[:120],
    "description": os.environ.get("DESCRIPTION", ""),
    "department_slug": os.environ.get("DEPARTMENT_SLUG", ""),
    "source": os.environ.get("SOURCE", "telegram"),
    "priority": os.environ.get("PRIORITY", "medium"),
}
sys.stdout.write(json.dumps(payload, separators=(",", ":")))
PYBODY
then
  _escalate "could not build request body"
fi

# ── Sign the RAW body: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (openssl) ─────
# BYTE-FOR-BYTE identical to route-presentation.sh so the signature the CC server
# validates is produced the same way regardless of which helper routed the task.
SIG=""
if [ -n "$WEBHOOK_SECRET" ]; then
  if command -v openssl >/dev/null 2>&1; then
    SIG="$(openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" <"$BODY_FILE" 2>/dev/null | sed -E 's/^.*= *//' | tr -d ' \r\n')"
  fi
  if [ -z "$SIG" ]; then
    # openssl unavailable / parse miss — python3 hmac fallback over the SAME bytes.
    SIG="$(WEBHOOK_SECRET="$WEBHOOK_SECRET" python3 - "$BODY_FILE" <<'PYSIG'
import hashlib, hmac, os, sys
sys.stdout.write(hmac.new(os.environ.get("WEBHOOK_SECRET", "").encode("utf-8"),
                          open(sys.argv[1], "rb").read(), hashlib.sha256).hexdigest())
PYSIG
)"
  fi
fi

# ── Headers: send Bearer / signature ONLY when the respective secret exists ──
_H=(-H 'Content-Type: application/json' -H 'Accept: application/json')
[ -n "$MC_API_TOKEN" ] && _H+=(-H "Authorization: Bearer $MC_API_TOKEN")
[ -n "$SIG" ]          && _H+=(-H "x-webhook-signature: $SIG")

# ── POST with retries (MAX_RETRIES retries after the first attempt) ──────────
attempt=0
http_code=""
resp_body=""
while :; do
  RAW="$(curl -sS -X POST "$INGEST_URL" "${_H[@]}" --data-binary @"$BODY_FILE" -w $'\n%{http_code}' 2>/dev/null || true)"
  http_code="${RAW##*$'\n'}"
  resp_body="${RAW%$'\n'*}"
  case "$http_code" in
    2[0-9][0-9]) break ;;
  esac
  [ "$attempt" -ge "$MAX_RETRIES" ] && break
  attempt=$((attempt + 1))
  sleep 1
done

echo "mc-route: HTTP ${http_code:-<none>} from $INGEST_URL (department=$DEPARTMENT_SLUG)"
[ -n "$resp_body" ] && printf '%s\n' "$resp_body"

case "$http_code" in
  2[0-9][0-9])
    # Workspace-mismatch guard: warn if the card did NOT land on the requested
    # department workspace (mirrors route-presentation.sh's presentations check,
    # generalized to the department_slug argument).
    WS="$(printf '%s' "$resp_body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    sys.stdout.write(str(d.get("workspace_id", "")) if isinstance(d, dict) else "")
except Exception:
    sys.stdout.write("")' 2>/dev/null || true)"
    if [ -n "$WS" ] && [ "$WS" != "$DEPARTMENT_SLUG" ]; then
      echo "mc-route: WARNING — task landed on workspace '$WS', NOT '$DEPARTMENT_SLUG'." >&2
      echo "ESCALATE_TO_OPERATOR: the '$DEPARTMENT_SLUG' department may be absent on this box. The CEO must tell the owner it is escalating to the operator instead of proceeding or self-intaking." >&2
    fi
    exit 0
    ;;
  *)
    _escalate "ingest POST returned HTTP ${http_code:-<none>} after ${attempt} retr(y|ies)"
    ;;
esac
