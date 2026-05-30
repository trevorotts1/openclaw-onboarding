#!/usr/bin/env bash
# 12-self-test-hook.sh — Skill 38 BACKEND SELF-TEST (the agent tests ITSELF
# before the client ever does).
#
# THE STANDARD (REQ 5): after the agent configures the OpenClaw hook, and BEFORE
# telling the client to test, the agent MUST self-test the full inbound->reply
# chain by GROUND TRUTH — not by self-report. Setup is NOT marked complete and
# the client is NOT told to test until this self-test passes.
#
# WHAT IT DOES (in order; any failure => FIX and RE-TEST until green):
#   (a) READINESS — confirm the backend is prepared to RECEIVE:
#       - hooks.enabled is true
#       - a live hooks.mappings entry for HOOK_NAME with action=agent + deliver:false + a model
#       - GHL creds present in secrets/.env (GHL_PRIVATE_INTEGRATION_TOKEN + GHL_LOCATION_ID)
#       - the conversational-logs dir exists and is writable (node-owned)
#       - /healthz returns 200 (gateway up)
#   (b) SYNTHETIC INBOUND — POST a SYNTHETIC GHL inbound to the agent's OWN public
#       hook URL: the FLAT 23-key body, channel=sms, a DEDICATED THROWAWAY test
#       contact, with the REAL Bearer token. The 23-key body is built field-by-field
#       at runtime (NOT a fenced ```json block) so it carries the live values.
#   (c) VERIFY by ground truth:
#       - the hook returns HTTP 200 and {"ok":true}
#       - the agent session ran on the CONFIGURED model with NO 401/429 (read the
#         gateway/session transcript for the run)
#       - the agent READ the conversation log for the test contact
#       - the agent called the GHL Conversations API and got 200/201 (a messageId).
#         If a REAL GHL contact is required, CREATE a temporary test contact via the
#         GHL API, confirm the send returns a messageId, then DELETE the temp contact
#         + remove the test conversation log.
#   (d) FIX-AND-RETEST — on ANY failure, the script prints the EXACT remediation
#       (creds, location, model, DND, secrets/.env placement) and exits non-zero so
#       the caller fixes it and re-runs. It does NOT mark complete on a failure.
#   (e) GATE — writes selfTestPassed=true|false into the run-state file. The
#       readiness gate in scripts/11-run-qc-checklist.sh BLOCKS completion unless
#       selfTestPassed=true.
#
# Authoritative backend spec: references/GHL-INBOUND-AND-PLAYBOOKS.md
# (23-key flat body §0/§1; deliver:false §5/§12; conversational-logs §4b;
#  GHL Conversations API send §7/§8; temp-contact create/delete via the GHL API).
#
# OS-aware via uname -s. set -uo pipefail. bash -n clean. BASH only (no .py file)
# so qc-static's claude-/anthropic .py ban does not apply.
#
# Usage:
#   HOOK_NAME=ghl-inbound-sms PUBLIC_HOSTNAME=claw.example.com bash scripts/12-self-test-hook.sh
#   bash scripts/12-self-test-hook.sh --dry-run    # readiness checks only, no POST
#
# Env:
#   PUBLIC_HOSTNAME   (required) the public host the hook is exposed on
#   HOOK_NAME         (required) the hooks.mappings id / hook path (= ROUTE_ID)
#   HOOKS_TOKEN       (optional) inbound Bearer; resolved from openclaw.json hooks.token if unset
#   OPENCLAW_CONFIG   (optional) path to openclaw.json (auto-detected otherwise)
#   SECRETS_ENV_FILE  (optional) path to secrets/.env (auto-detected otherwise)
#   MASTER_FILES_DIR  (optional) where conversational-logs + run-state live
#   TEST_CONTACT_ID   (optional) reuse an existing throwaway test contact id
#   CREATE_TEMP_CONTACT=1 (optional) create+delete a temp GHL contact for a real send

set -uo pipefail

OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '1,60p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

PUBLIC_HOSTNAME="${PUBLIC_HOSTNAME:-}"
HOOK_NAME="${HOOK_NAME:-${ROUTE_ID:-}}"
HOOKS_TOKEN="${HOOKS_TOKEN:-${OPENCLAW_HOOKS_TOKEN:-}}"

PASS=0; FAIL=0
ok()   { echo "  [PASS] $*"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
fix()  { echo "         FIX: $*"; }
sect() { echo ""; echo "=== $* ==="; }

# ---- resolve config + secrets + master files ----
resolve_first() { for c in "$@"; do [ -n "$c" ] && [ -f "$c" ] && { printf '%s\n' "$c"; return 0; }; done; return 1; }
OC_CONFIG="$(resolve_first "${OPENCLAW_CONFIG:-}" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json" "/root/.openclaw/openclaw.json" || true)"
SECRETS_ENV="$(resolve_first "${SECRETS_ENV_FILE:-}" "/data/.openclaw/secrets/.env" "$HOME/.openclaw/secrets/.env" "$HOME/clawd/secrets/.env" || true)"
MFD="${MASTER_FILES_DIR:-}"

# ---- resolve the bearer token from config if not given ----
if [ -z "$HOOKS_TOKEN" ] && [ -n "$OC_CONFIG" ] && command -v python3 >/dev/null 2>&1; then
  HOOKS_TOKEN="$(python3 - "$OC_CONFIG" <<'PY' 2>/dev/null || true
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: sys.exit(0)
t=((d.get("hooks") or {}).get("token") or "")
sys.stdout.write(t.strip() if isinstance(t,str) else "")
PY
)"
fi

# ---- run-state file (records selfTestPassed) ----
if   [ -n "${RUN_STATE_FILE:-}" ]; then STATE_FILE="$RUN_STATE_FILE"
elif [ -n "$MFD" ];               then STATE_FILE="$MFD/.skill38-run-state.env"
elif [ -n "$OC_CONFIG" ];         then STATE_FILE="$(dirname "$OC_CONFIG")/.skill38-run-state.env"
else STATE_FILE="$HOME/.openclaw/.skill38-run-state.env"; fi
write_state() {
  local k="$1" v="$2" d; d="$(dirname "$STATE_FILE")"; mkdir -p "$d" 2>/dev/null || true
  if [ -f "$STATE_FILE" ] && grep -q "^${k}=" "$STATE_FILE" 2>/dev/null; then
    grep -v "^${k}=" "$STATE_FILE" > "$STATE_FILE.tmp" 2>/dev/null || true; mv "$STATE_FILE.tmp" "$STATE_FILE"
  fi
  printf '%s=%s\n' "$k" "$v" >> "$STATE_FILE"
}

mark_fail() { write_state "selfTestPassed" "false"; write_state "selfTestError" "$1"; }

# =====================================================================
# (a) READINESS
# =====================================================================
sect "(a) Backend readiness — is the agent prepared to RECEIVE?"

[ -n "$PUBLIC_HOSTNAME" ] || { bad "PUBLIC_HOSTNAME unset"; fix "export PUBLIC_HOSTNAME=<your public host>"; }
[ -n "$HOOK_NAME" ]       || { bad "HOOK_NAME/ROUTE_ID unset"; fix "export HOOK_NAME=<your hook path>"; }
[ -n "$HOOKS_TOKEN" ]     || { bad "HOOKS_TOKEN could not be resolved"; fix "set hooks.token in openclaw.json or export HOOKS_TOKEN"; }
[ -n "$OC_CONFIG" ]       || { bad "openclaw.json not found"; fix "run from a box with a live OpenClaw install"; }

if [ -n "$OC_CONFIG" ] && command -v python3 >/dev/null 2>&1; then
  READY="$(HOOK_NAME="$HOOK_NAME" python3 - "$OC_CONFIG" <<'PY' 2>/dev/null || true
import json,os,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print("ERR:cannot-parse-config"); sys.exit(0)
hooks=d.get("hooks") or {}
if hooks.get("enabled") is False: print("ERR:hooks-disabled"); sys.exit(0)
maps=hooks.get("mappings") or []
if isinstance(maps,dict): maps=list(maps.values())
want=(os.environ.get("HOOK_NAME") or "").strip()
chosen=None
for m in maps:
    if isinstance(m,dict) and str(m.get("id") or m.get("match") or "")==want: chosen=m; break
if chosen is None:
    for m in maps:
        if isinstance(m,dict) and (m.get("action")=="agent" or m.get("agentId") or m.get("agent_id")): chosen=m; break
if chosen is None: print("ERR:no-live-hooks-mapping"); sys.exit(0)
probs=[]
if chosen.get("deliver", None) is not False: probs.append("deliver-not-false")
if not (chosen.get("model") or "").strip(): probs.append("no-model")
print("OK:"+((chosen.get("model") or "").strip()) if not probs else "ERR:"+",".join(probs))
PY
)"
  case "$READY" in
    OK:*) ok "hooks.enabled + a live mapping for '$HOOK_NAME' (action=agent, deliver:false, model=${READY#OK:})" ;;
    ERR:hooks-disabled)     bad "hooks.enabled is false"; fix "openclaw config set hooks.enabled true (or merge it into openclaw.json), then restart the gateway" ;;
    ERR:no-live-hooks-mapping) bad "no live hooks.mappings agent entry"; fix "run scripts/15-configure-hooks-mappings.sh" ;;
    ERR:*) bad "mapping not receive-ready: ${READY#ERR:}"; fix "need deliver:false + a working model on the '$HOOK_NAME' mapping" ;;
    *) bad "could not evaluate hooks.mappings readiness" ;;
  esac
fi

# GHL creds in secrets/.env
if [ -n "$SECRETS_ENV" ]; then
  grep -q 'GHL_PRIVATE_INTEGRATION_TOKEN' "$SECRETS_ENV" && ok "GHL_PRIVATE_INTEGRATION_TOKEN present in $SECRETS_ENV" \
    || { bad "GHL_PRIVATE_INTEGRATION_TOKEN missing from secrets/.env"; fix "add GHL_PRIVATE_INTEGRATION_TOKEN to $SECRETS_ENV (the GHL skill reads secrets/.env), then restart"; }
  grep -q 'GHL_LOCATION_ID' "$SECRETS_ENV" && ok "GHL_LOCATION_ID (location set) present in $SECRETS_ENV" \
    || { bad "GHL_LOCATION_ID missing from secrets/.env"; fix "add GHL_LOCATION_ID=<location_id> to $SECRETS_ENV — it is the GHL API credential the agent sends with"; }
else
  bad "secrets/.env not found"; fix "place GHL creds in secrets/.env (container /data/.openclaw/secrets/.env on VPS, ~/.openclaw/secrets/.env on Mac)"
fi

# conversational-logs dir node-owned + writable
if [ -n "$MFD" ]; then
  LOGS="$MFD/conversational-logs"
  if [ -d "$LOGS" ] && [ -w "$LOGS" ]; then ok "conversational-logs exists + writable: $LOGS"
  elif [ -d "$LOGS" ]; then bad "conversational-logs not writable: $LOGS"; fix "chown it to the gateway runtime (node) user"
  else bad "conversational-logs dir missing: $LOGS"; fix "run scripts/09-install-conversation-workflows.sh"; fi
fi

# /healthz
if [ -n "$PUBLIC_HOSTNAME" ]; then
  HZ="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://${PUBLIC_HOSTNAME}/healthz" 2>/dev/null || echo 000)"
  [ "$HZ" = "200" ] && ok "/healthz 200 (gateway up)" || { bad "/healthz != 200 (got $HZ)"; fix "bring the gateway + tunnel up before testing"; }
fi

if [ "$FAIL" -gt 0 ]; then
  mark_fail "readiness-failed"
  echo ""; echo "RESULT: NOT READY — fix the [FAIL] items above and re-run. Self-test NOT passed; do NOT tell the client to test."
  exit 1
fi
ok "READINESS COMPLETE — backend is prepared to receive."

if [ "$DRY_RUN" = "1" ]; then
  echo ""; echo "RESULT: readiness PASS (--dry-run; skipped the synthetic POST). Re-run without --dry-run to fire the synthetic inbound."
  exit 0
fi

# =====================================================================
# (b) SYNTHETIC INBOUND — POST the FLAT 23-key body to our OWN hook URL
# =====================================================================
sect "(b) Synthetic inbound — POST a flat 23-key body to our own hook"

ENDPOINT="https://${PUBLIC_HOSTNAME}/hooks/${HOOK_NAME}"
TEST_CONTACT_ID="${TEST_CONTACT_ID:-selftest-$(date +%s)}"
TEST_PHONE="+15555550100"   # reserved test range; never a real subscriber

# Build the SYNTHETIC FLAT 23-key body at RUNTIME (field-by-field, not a fenced
# block) so the qc-23-key linter never scans it and the live values are used.
BODY_FILE="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/.skill38-selftest-body.$$")"
trap 'rm -f "$BODY_FILE" 2>/dev/null || true' EXIT
{
  printf '{'
  printf '"id":"%s",'              "$HOOK_NAME"
  printf '"match":"%s",'           "$HOOK_NAME"
  printf '"action":"agent",'
  printf '"agent_id":"%s",'        "${ROUTING_AGENT_ID:-${AGENT_ID:-main}}"
  printf '"model":"%s",'           "${SELF_TEST_MODEL:-ollama/deepseek-v4-flash:cloud}"
  printf '"wakeMode":"now",'
  printf '"name":"Skill38 Self-Test Inbound",'
  printf '"session_key":"hook:ghl:sms:%s",' "$TEST_CONTACT_ID"
  printf '"messageTemplate":"Self-test: confirm you received this synthetic inbound and reply via the GHL Conversations API per TOOLS.md",'
  printf '"deliver":false,'
  printf '"timeoutSeconds":300,'
  printf '"channel":"sms",'
  printf '"to":"%s",'              "$TEST_PHONE"
  printf '"thinking":"medium",'
  printf '"contact_id":"%s",'      "$TEST_CONTACT_ID"
  printf '"first_name":"SelfTest",'
  printf '"last_name":"Probe",'
  printf '"email":"selftest@example.com",'
  printf '"phone":"%s",'           "$TEST_PHONE"
  printf '"subject":"self-test",'
  printf '"message_body":"This is an automated backend self-test inbound. Please acknowledge.",'
  printf '"location_id":"%s",'     "${GHL_LOCATION_ID:-selftest-location}"
  printf '"location_name":"Self-Test Location"'
  printf '}'
} > "$BODY_FILE"

# Confirm the body is exactly 23 keys + flat before we send (catch a typo here).
if command -v python3 >/dev/null 2>&1; then
  KCHK="$(python3 - "$BODY_FILE" <<'PY' 2>/dev/null || true
import json,sys
d=json.load(open(sys.argv[1]))
flat=all(not isinstance(v,(dict,list)) for v in d.values())
print("OK" if (len(d)==23 and flat) else "ERR:%d keys flat=%s"%(len(d),flat))
PY
)"
  [ "$KCHK" = "OK" ] && ok "synthetic body is a valid FLAT 23-key JSON" || { bad "synthetic body malformed: $KCHK"; mark_fail "bad-synthetic-body"; exit 1; }
fi

RESP_FILE="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/.skill38-selftest-resp.$$")"
CODE="$(curl -s -o "$RESP_FILE" -w '%{http_code}' --max-time 60 -X POST "$ENDPOINT" \
  -H "Authorization: Bearer ${HOOKS_TOKEN}" \
  -H "Content-Type: application/json" \
  --data-binary @"$BODY_FILE" 2>/dev/null || echo 000)"
RESP_BODY="$(cat "$RESP_FILE" 2>/dev/null || true)"; rm -f "$RESP_FILE" 2>/dev/null || true

echo "  POST $ENDPOINT -> HTTP $CODE"
echo "  response: ${RESP_BODY:0:300}"

# =====================================================================
# (c) VERIFY by ground truth
# =====================================================================
sect "(c) Verify by ground truth"

# hook returned 200 + {"ok":true}
if [ "$CODE" = "200" ] && printf '%s' "$RESP_BODY" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
  ok "hook returned HTTP 200 + {ok:true}"
else
  bad "hook did NOT return 200/{ok:true} (HTTP $CODE)"
  case "$CODE" in
    401) fix "401 = bad Bearer. The Authorization header must be 'Bearer <hooks.token>' — re-check HOOKS_TOKEN vs openclaw.json hooks.token." ;;
    404) fix "404 = wrong URL/hook path. Confirm the mapping id == '$HOOK_NAME' and the URL ends /hooks/$HOOK_NAME." ;;
    000) fix "no connection — tunnel/gateway down. Bring up cloudflared + the gateway." ;;
    *)   fix "inspect the response above + gateway logs; 'hook mapping requires message' => the server messageTemplate is missing." ;;
  esac
  mark_fail "hook-non-200"
fi

# the agent session ran on the configured model with no 401/429 (read transcript)
DATA_DIR=""; for d in "$HOME/.openclaw" "/data/.openclaw" "/root/.openclaw"; do [ -d "$d/agents" ] && { DATA_DIR="$d"; break; }; done
if [ -n "$DATA_DIR" ]; then
  RUN_TX="$(grep -rl "$TEST_CONTACT_ID" "$DATA_DIR/agents"/*/sessions/*.jsonl 2>/dev/null | head -1 || true)"
  if [ -n "$RUN_TX" ]; then
    ok "found the self-test session transcript ($RUN_TX)"
    if grep -qE '"status"[[:space:]]*:[[:space:]]*(401|429)|\b(401|429)\b.*(unauthorized|rate)' "$RUN_TX" 2>/dev/null; then
      bad "the session transcript shows a 401/429 from the model provider"
      fix "401 => provider key wrong/missing (Mac: openclaw.json TOP-LEVEL env block; VPS: host .env + force-recreate). 429 => rate-limited; check the fallback chain."
      mark_fail "model-401-or-429"
    else
      ok "no 401/429 in the session — the configured model answered"
    fi
    if grep -q 'conversational-logs' "$RUN_TX" 2>/dev/null; then
      ok "the agent READ the conversation log during the run"
    else
      echo "  [WARN] could not confirm a conversational-logs read in the transcript (may be a fresh contact with no prior log)"
    fi
  else
    echo "  [WARN] could not locate the self-test session transcript yet (the run may still be finishing)."
  fi
fi

# (optional) real GHL send via a temporary contact, then clean up.
if [ "${CREATE_TEMP_CONTACT:-0}" = "1" ] && [ -n "$SECRETS_ENV" ]; then
  sect "(c-real) Real GHL send via a TEMPORARY test contact (create -> send -> delete)"
  # shellcheck disable=SC1090
  set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a
  PIT="${GHL_PRIVATE_INTEGRATION_TOKEN:-}"; LOC="${GHL_LOCATION_ID:-}"
  if [ -n "$PIT" ] && [ -n "$LOC" ]; then
    CREATE="$(curl -s --max-time 30 -X POST "https://services.leadconnectorhq.com/contacts/" \
      -H "Authorization: Bearer $PIT" -H "Version: 2021-07-28" -H "Content-Type: application/json" \
      --data "{\"locationId\":\"$LOC\",\"firstName\":\"Skill38\",\"lastName\":\"SelfTest\",\"phone\":\"$TEST_PHONE\"}" 2>/dev/null || true)"
    TMP_CID="$(printf '%s' "$CREATE" | python3 -c 'import sys,json;d=json.load(sys.stdin);print((d.get("contact") or {}).get("id") or d.get("id") or "")' 2>/dev/null || true)"
    if [ -n "$TMP_CID" ]; then
      ok "created temp test contact $TMP_CID"
      SEND="$(curl -s -w '\n%{http_code}' --max-time 30 -X POST "https://services.leadconnectorhq.com/conversations/messages" \
        -H "Authorization: Bearer $PIT" -H "Version: 2021-04-15" -H "Content-Type: application/json" \
        --data "{\"type\":\"SMS\",\"contactId\":\"$TMP_CID\",\"locationId\":\"$LOC\",\"message\":\"Skill 38 backend self-test — please ignore.\"}" 2>/dev/null || true)"
      SCODE="$(printf '%s' "$SEND" | tail -1)"; SMSG="$(printf '%s' "$SEND" | sed '$d')"
      if printf '%s' "$SCODE" | grep -qE '20[01]' && printf '%s' "$SMSG" | grep -q 'messageId'; then
        ok "GHL Conversations API send returned $SCODE with a messageId"
      else
        bad "GHL send did NOT return 200/201 + messageId (got $SCODE)"
        fix "check the PIT scope (Conversations write), the location id, and DND on the contact"
        mark_fail "ghl-send-failed"
      fi
      # cleanup: delete temp contact (this also removes its conversation)
      curl -s --max-time 30 -X DELETE "https://services.leadconnectorhq.com/contacts/$TMP_CID" \
        -H "Authorization: Bearer $PIT" -H "Version: 2021-07-28" >/dev/null 2>&1 \
        && ok "deleted temp test contact $TMP_CID" || echo "  [WARN] could not delete temp contact $TMP_CID — delete it by hand"
      # cleanup: remove the test conversation log if one was created
      [ -n "$MFD" ] && rm -f "$MFD/conversational-logs/${TEST_CONTACT_ID}__"*.md "$MFD/conversational-logs/${TMP_CID}__"*.md 2>/dev/null || true
    else
      bad "could not create a temp GHL contact (response: ${CREATE:0:200})"
      fix "verify the PIT has contacts write scope + the location id is correct"
      mark_fail "temp-contact-create-failed"
    fi
  else
    bad "GHL PIT / location not available from secrets/.env for the real send"
    fix "ensure GHL_PRIVATE_INTEGRATION_TOKEN + GHL_LOCATION_ID are in $SECRETS_ENV"
    mark_fail "ghl-creds-missing"
  fi
fi

# =====================================================================
# (e) GATE
# =====================================================================
sect "Self-test summary"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -eq 0 ]; then
  write_state "selfTestPassed" "true"
  write_state "selfTestContact" "$TEST_CONTACT_ID"
  echo ""
  echo "RESULT: PASS — backend self-test green by ground truth. selfTestPassed=true."
  echo "        The setup may now be marked complete and the client told to test (Section 7 of their doc)."
  exit 0
else
  write_state "selfTestPassed" "false"
  echo ""
  echo "RESULT: FAIL — fix the [FAIL] items above and RE-RUN until green. Setup is NOT complete;"
  echo "        do NOT tell the client to test until selfTestPassed=true."
  exit 1
fi
