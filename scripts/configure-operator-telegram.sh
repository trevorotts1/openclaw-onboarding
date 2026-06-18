#!/usr/bin/env bash
# configure-operator-telegram.sh — v10.15.48
#
# FIX 2 (systemic): OPERATOR / RESCUE traffic bleeds into the CLIENT's personal
# Telegram chat. Root cause: one bot + one shared agent:main:main session, so
# delivery resolves "the chat from the last session" = the owner's chat. A
# maintenance self-ping or a Rescue-Rangers message then lands in the client's
# DMs.
#
# PROVEN FIX (the pattern already live on Trevor's Mac): give the agent TWO
# Telegram accounts under channels.telegram.accounts —
#   • default  = the CLIENT bot (owner-facing, dmPolicy=pairing/allowlist of the
#                client's own chat id)
#   • operator = a SEPARATE operator bot (dmPolicy=allowlist, allowFrom = the
#                operator IDs ONLY: 5252140759 / 6663821679 / 6771245262, NEVER
#                the client's id)
# plus channels.telegram.defaultAccount="default" and a bindings route
#   { channel:"telegram", accountId:"operator" } -> agentId "main"
# so operator-account traffic is routed to the same agent on an ISOLATED session
# key (agent:main:operator) and replies go back out the operator bot — never the
# client bot. Schema verified at docs.openclaw.ai/tools/skills + the telegram
# channel docs: accounts.<id>.{botToken,dmPolicy,allowFrom}, defaultAccount,
# and named accounts do NOT inherit accounts.default.* values.
#
# Idempotent + ADDITIVE: never removes the client account, never narrows the
# client's allowFrom. Only ADDS the operator account + binding + defaultAccount.
#
# CAVEAT (surfaced loudly): an operator account needs its OWN bot token from
# BotFather. This script reads it from OPERATOR_TELEGRAM_BOT_TOKEN (env or
# secrets/.env or openclaw.json env.vars). If absent, it writes the STRUCTURE
# with an empty operator botToken and a clear TODO, so existing boxes are
# flagged for token provisioning rather than silently left co-mingled. It does
# NOT invent a token and does NOT claim the separation is live without one.

set -u

log() { printf '  [operator-telegram] %s\n' "$*"; }

# ── Path detection (mirrors apply-fleet-standards.sh) ────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"; OC_USER="node"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"; OC_USER="$(whoami)"
else
  log "cannot find openclaw.json in /data/.openclaw or \$HOME/.openclaw — skipping (no config to patch yet)"
  printf 'STATUS: operator-telegram=NO_CONFIG\n'
  exit 0
fi
OC_CONFIG="$OC_ROOT/openclaw.json"
SECRETS_ENV="$OC_ROOT/secrets/.env"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
OC_BACKUP="$OC_CONFIG.bak-operator-tg-$TIMESTAMP"

# ── Resolve the operator bot token (env -> secrets/.env -> openclaw.json) ────
_get_var() {
  local var="$1" v=""
  v="$(printenv "$var" 2>/dev/null || true)"
  if [ -z "$v" ] && [ -f "$SECRETS_ENV" ]; then
    v="$(grep -E "^${var}=" "$SECRETS_ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  fi
  if [ -z "$v" ] && command -v python3 >/dev/null 2>&1; then
    v="$(VAR="$var" OC_JSON="$OC_CONFIG" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    print(cfg.get("env", {}).get("vars", {}).get(os.environ["VAR"], "") or "")
except Exception:
    print("")
PYEOF
)"
  fi
  printf '%s' "$v"
}
OPERATOR_BOT_TOKEN="$(_get_var OPERATOR_TELEGRAM_BOT_TOKEN)"
# Operator escalation/help chat id (where maintenance / drive output goes).
# CO-MINGLING GUARD (v12.4.0): this destination is OPT-IN and CONFIGURABLE. We
# NEVER bake in a personal chat id. Resolve from (in order):
#   OPERATOR_ESCALATION_CHAT_ID -> OPERATOR_HELP_CHAT_ID -> OPERATOR_TELEGRAM_CHAT_ID
# and if none is provided, leave it EMPTY. An empty value means operator
# escalation is disabled until an operator explicitly opts in — a client box
# that has not opted in will therefore never proactively message any operator.
OPERATOR_HELP_CHAT_ID="$(_get_var OPERATOR_ESCALATION_CHAT_ID)"
[ -z "$OPERATOR_HELP_CHAT_ID" ] && OPERATOR_HELP_CHAT_ID="$(_get_var OPERATOR_HELP_CHAT_ID)"
[ -z "$OPERATOR_HELP_CHAT_ID" ] && OPERATOR_HELP_CHAT_ID="$(_get_var OPERATOR_TELEGRAM_CHAT_ID)"
# No hardcoded default — empty == operator escalation not configured (opt-in only).

# Persist the escalation chat into openclaw.json env.vars ONLY if one was
# explicitly provided, so the maintenance contract (and resume crons) can resolve
# it later. We write BOTH the new canonical key (OPERATOR_ESCALATION_CHAT_ID) and
# the back-compat key (OPERATOR_HELP_CHAT_ID). Idempotent. If empty, we write
# nothing — leaving the box in the safe, no-operator-send default.
if [ -n "$OPERATOR_HELP_CHAT_ID" ] && command -v openclaw >/dev/null 2>&1; then
  openclaw config set env.vars.OPERATOR_ESCALATION_CHAT_ID "$OPERATOR_HELP_CHAT_ID" >/dev/null 2>&1 || true
  openclaw config set env.vars.OPERATOR_HELP_CHAT_ID "$OPERATOR_HELP_CHAT_ID" >/dev/null 2>&1 || true
elif [ -z "$OPERATOR_HELP_CHAT_ID" ]; then
  log "no operator escalation chat provided (OPERATOR_ESCALATION_CHAT_ID unset) — leaving operator escalation DISABLED (opt-in). Account separation/binding still applied below."
fi

# ── Backup ───────────────────────────────────────────────────────────────────
cp "$OC_CONFIG" "$OC_BACKUP" 2>/dev/null || true
log "config: $OC_CONFIG (backup → $OC_BACKUP)"

# ── Additive deep-merge: accounts.{default,operator} + defaultAccount + binding ─
RESULT="$(OPERATOR_BOT_TOKEN="$OPERATOR_BOT_TOKEN" OPERATOR_HELP_CHAT_ID="$OPERATOR_HELP_CHAT_ID" OC_CONFIG="$OC_CONFIG" python3 - <<'PYEOF'
import json, os, sys

p = os.environ["OC_CONFIG"]
op_token = os.environ.get("OPERATOR_BOT_TOKEN", "").strip()
op_help_chat = os.environ.get("OPERATOR_HELP_CHAT_ID", "").strip()

# The ONLY operator IDs allowed on the operator account. The client's id is
# NEVER added here (that is the whole point of the separation).
OPERATOR_IDS = ["5252140759", "6663821679", "6771245262"]

try:
    cfg = json.load(open(p))
except Exception as e:
    print("ERROR_LOAD:" + str(e)); sys.exit(0)

before = json.dumps(cfg, sort_keys=True)

tg = cfg.setdefault("channels", {}).setdefault("telegram", {})

# 1) Existing single-bot config -> migrate its botToken/allowFrom into a
#    `default` (CLIENT) account WITHOUT removing anything. We do not touch the
#    top-level allowFrom (named accounts may still inherit it), we just make the
#    client account explicit.
accounts = tg.setdefault("accounts", {})
default_acct = accounts.setdefault("default", {})

# Carry over the existing single-bot token/allowFrom into default if present and
# default doesn't already have them. ADDITIVE — never clobber an existing,
# already-configured default account.
legacy_token = tg.get("botToken", "")
legacy_allow = tg.get("allowFrom", [])
if legacy_token and not default_acct.get("botToken"):
    default_acct["botToken"] = legacy_token
if legacy_allow and not default_acct.get("allowFrom"):
    # client account keeps the client's own allow list / pairing
    default_acct["allowFrom"] = list(legacy_allow)
default_acct.setdefault("dmPolicy", "pairing")

# 2) operator account — SEPARATE bot, allowlist of operator IDs ONLY.
op_acct = accounts.setdefault("operator", {})
# additive: set token only if we have one and it's not already set
if op_token and not op_acct.get("botToken"):
    op_acct["botToken"] = op_token
elif "botToken" not in op_acct:
    # leave an explicit empty token + TODO so this box is flagged for provisioning
    op_acct["botToken"] = ""
op_acct["dmPolicy"] = "allowlist"
# allowFrom = operator IDs ONLY; merge-in (never include the client id)
existing_allow = [str(x) for x in (op_acct.get("allowFrom") or [])]
for oid in OPERATOR_IDS:
    if oid not in existing_allow:
        existing_allow.append(oid)
op_acct["allowFrom"] = existing_allow
if op_help_chat:
    op_acct.setdefault("helpChatId", op_help_chat)

# 3) defaultAccount -> the CLIENT account, so owner-facing routing is unchanged.
tg["defaultAccount"] = "default"

# 4) bindings route: operator account -> agent main (isolated session key).
bindings = cfg.setdefault("channels", {}).setdefault("bindings", [])
if not isinstance(bindings, list):
    bindings = []
    cfg["channels"]["bindings"] = bindings
have_op_binding = any(
    isinstance(b, dict)
    and b.get("channel") == "telegram"
    and b.get("accountId") == "operator"
    for b in bindings
)
if not have_op_binding:
    bindings.append({"channel": "telegram", "accountId": "operator", "agentId": "main"})

after = json.dumps(cfg, sort_keys=True)

if before == after:
    print("NOOP")
else:
    json.dump(cfg, open(p, "w"), indent=2)
    open(p, "a").write("\n")
    print("MERGED")

# report token state for the caller's honesty contract
print("TOKEN_PRESENT:" + ("yes" if op_acct.get("botToken") else "no"))
PYEOF
)"

printf '%s\n' "$RESULT" | grep -v '^TOKEN_PRESENT:' | sed 's/^/  [operator-telegram] /'
TOKEN_STATE="$(printf '%s\n' "$RESULT" | grep '^TOKEN_PRESENT:' | cut -d: -f2)"

case "$RESULT" in
  ERROR_LOAD:*)
    log "could not parse $OC_CONFIG — left untouched"
    printf 'STATUS: operator-telegram=PARSE_ERROR\n'
    exit 0 ;;
esac

# ── Chown back (VPS container) ───────────────────────────────────────────────
[ "$OC_ROOT" = "/data/.openclaw" ] && chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true

# ── Validate + rollback on failure ───────────────────────────────────────────
if command -v openclaw >/dev/null 2>&1; then
  if ! openclaw config validate >/dev/null 2>&1; then
    log "openclaw config validate FAILED after merge — rolling back to $OC_BACKUP"
    cp "$OC_BACKUP" "$OC_CONFIG" 2>/dev/null || true
    printf 'STATUS: operator-telegram=VALIDATE_FAILED_ROLLED_BACK\n'
    exit 0
  fi
fi

# ── Honest STATUS ────────────────────────────────────────────────────────────
if [ "$TOKEN_STATE" = "yes" ]; then
  log "operator account + binding configured WITH a bot token — operator/rescue traffic now routes through the operator bot, NOT the client's chat."
  printf 'STATUS: operator-telegram=CONFIGURED (operator account + binding live; token present)\n'
else
  log "STRUCTURE written but the operator account has NO bot token yet."
  log "ACTION REQUIRED: create an operator bot in BotFather, then set"
  log "  OPERATOR_TELEGRAM_BOT_TOKEN=<token> in $SECRETS_ENV (or openclaw.json env.vars)"
  log "  and re-run this script. Until then, the operator account exists in config"
  log "  but cannot send/receive — provision the token to fully separate channels."
  printf 'STATUS: operator-telegram=STRUCTURE_ONLY_NEEDS_TOKEN (operator bot token NOT provisioned — separation not yet live)\n'
fi
exit 0
