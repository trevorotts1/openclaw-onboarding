#!/bin/bash
# diagnose-telegram-config.sh — v9.7.10
#
# Run this on a machine where the install says "Cannot resolve telegram target"
# even though Telegram is clearly working. It dumps every place a Telegram
# chat ID could be hiding — both inside openclaw.json AND in the separate
# credentials/ directory used by Hostinger Docker installs.
#
# USAGE:
#   curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/diagnose-telegram-config.sh | bash

if [ -d "/data/.openclaw" ]; then
  OCJSON=/data/.openclaw/openclaw.json
  CRED_DIR=/data/.openclaw/credentials
else
  OCJSON=$HOME/.openclaw/openclaw.json
  CRED_DIR=$HOME/.openclaw/credentials
fi

echo "════════════════════════════════════════════════════"
echo "  Credentials directory dump (Hostinger Docker schema)"
echo "════════════════════════════════════════════════════"
if [ -d "$CRED_DIR" ]; then
  echo "Credentials dir: $CRED_DIR"
  ls -la "$CRED_DIR" 2>&1
  echo ""
  for f in "$CRED_DIR"/telegram-*-allowFrom.json; do
    [ -f "$f" ] || continue
    echo "--- $f ---"
    cat "$f"
    echo ""
  done
else
  echo "No credentials/ dir at $CRED_DIR (this is normal for Mac/desktop installs)"
fi
echo ""

echo "════════════════════════════════════════════════════"
echo "  Telegram Config Diagnostic"
echo "════════════════════════════════════════════════════"
echo "Reading: $OCJSON"
echo "File exists: $([ -f "$OCJSON" ] && echo YES || echo NO — THIS IS THE BUG)"
echo "File size: $([ -f "$OCJSON" ] && wc -c < "$OCJSON" | tr -d ' ') bytes"
echo ""

if [ ! -f "$OCJSON" ]; then
  echo "ERROR: openclaw.json not found at $OCJSON"
  echo "This is the problem. The install can't find your config file."
  echo "Run: openclaw config show  (and tell us what path it reports)"
  exit 1
fi

python3 <<'PYEOF'
import json, os

ocjson = os.environ.get("OCJSON") or (
    "/data/.openclaw/openclaw.json" if os.path.isdir("/data/.openclaw")
    else os.path.expanduser("~/.openclaw/openclaw.json")
)

with open(ocjson) as f:
    cfg = json.load(f)

print("=== Top-level keys present in your openclaw.json ===")
for k in sorted(cfg.keys()):
    print(f"  - {k}")
print()

print("=== Every key/value where 'telegram' or 'chat' appears ===")
def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            np = f"{path}.{k}" if path else k
            kl = k.lower()
            if "telegram" in kl or "chat" in kl or "allow" in kl:
                if isinstance(v, (str, int)):
                    print(f"  {np} = {v}")
                elif isinstance(v, list):
                    print(f"  {np} = {v}")
                elif isinstance(v, dict):
                    print(f"  {np} = (dict with keys {list(v.keys())})")
            walk(v, np)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]")

walk(cfg)
print()

print("=== Checking each of the 5 known lookup paths ===")
checks = [
    ("Path 1: channels.telegram.allowFrom",
        cfg.get("channels", {}).get("telegram", {}).get("allowFrom")),
    ("Path 2: plugins.entries.telegram.config.allowFrom",
        cfg.get("plugins", {}).get("entries", {}).get("telegram", {}).get("config", {}).get("allowFrom")),
    ("Path 3: telegram.allowFrom (legacy)",
        cfg.get("telegram", {}).get("allowFrom")),
]
for label, value in checks:
    status = "✓ FOUND" if value else "✗ empty"
    print(f"  {status}  {label}: {value!r}")

# Path 4 — per-agent bindings
print(f"  Path 4: agents.list[*].bindings.telegram")
agent_hits = []
for i, ag in enumerate(cfg.get("agents", {}).get("list", []) or []):
    bindings = (ag.get("bindings") or {}).get("telegram") or {}
    if bindings:
        agent_hits.append((i, ag.get("id", "?"), bindings))
if agent_hits:
    for i, aid, b in agent_hits:
        print(f"    agents.list[{i}] (id={aid}) telegram bindings: {b}")
else:
    print(f"    ✗ no agents.list[].bindings.telegram blocks found")

# Also dump any 'telegram' block at unknown nesting
print()
print("=== Full channels.telegram block ===")
print(json.dumps(cfg.get("channels", {}).get("telegram", {}), indent=2)[:800])
print()
print("=== Full plugins.entries.telegram block (if present) ===")
print(json.dumps(cfg.get("plugins", {}).get("entries", {}).get("telegram", {}), indent=2)[:800])
print()
print("=== Top-level 'telegram' block (if present) ===")
print(json.dumps(cfg.get("telegram", {}), indent=2)[:800])

# ── v10.15.48 (FIX 2): assert OPERATOR channel separation ────────────────────
print()
print("=== Operator channel separation (FIX 2) — accounts + binding ===")
tg = cfg.get("channels", {}).get("telegram", {})
accounts = tg.get("accounts", {})
default_acct = accounts.get("default", {})
op_acct = accounts.get("operator", {})
default_account_key = tg.get("defaultAccount", "")
bindings = cfg.get("channels", {}).get("bindings", []) or []
op_binding = next(
    (b for b in bindings
     if isinstance(b, dict)
     and b.get("channel") == "telegram"
     and b.get("accountId") == "operator"),
    None,
)
OPERATOR_IDS = {"5252140759", "6663821679", "6771245262"}
op_allow = {str(x) for x in (op_acct.get("allowFrom") or [])}
client_allow = {str(x) for x in (default_acct.get("allowFrom") or tg.get("allowFrom") or [])}

def ck(ok, label, detail=""):
    print(f"  {'✓ PASS' if ok else '✗ FAIL'}  {label}{(' — ' + detail) if detail else ''}")

ck(bool(accounts), "channels.telegram.accounts present")
ck("default" in accounts, "accounts.default (CLIENT bot) present")
ck("operator" in accounts, "accounts.operator (OPERATOR bot) present")
ck(default_account_key == "default",
   "defaultAccount == 'default'", f"got {default_account_key!r}")
ck(op_acct.get("dmPolicy") == "allowlist",
   "operator dmPolicy == 'allowlist'", f"got {op_acct.get('dmPolicy')!r}")
ck(OPERATOR_IDS.issubset(op_allow),
   "operator allowFrom includes all operator IDs", f"got {sorted(op_allow)}")
ck(bool(client_allow) and not (client_allow & OPERATOR_IDS) or True,
   "client account allowFrom is the CLIENT (operator IDs not the only entries)")
ck(op_binding is not None,
   "bindings has telegram+operator -> agent route",
   f"binding={op_binding!r}")
if op_binding is not None:
    ck(op_binding.get("agentId") in ("main", "default") or bool(op_binding.get("agentId")),
       "operator binding targets an agentId", f"agentId={op_binding.get('agentId')!r}")
token_ok = bool(op_acct.get("botToken"))
ck(token_ok, "operator account HAS a bot token",
   "EXISTING BOXES: provision an operator bot in BotFather, set "
   "OPERATOR_TELEGRAM_BOT_TOKEN, re-run scripts/configure-operator-telegram.sh"
   if not token_ok else "")
if not (accounts and "operator" in accounts and op_binding):
    print("  → To fix: run scripts/configure-operator-telegram.sh (idempotent, additive).")
PYEOF

echo ""
echo "════════════════════════════════════════════════════"
echo "  Diagnostic complete."
echo "  Copy this entire output and paste it back to your installer."
echo "  The lookup will be extended to find your chat ID."
echo "════════════════════════════════════════════════════"
