#!/usr/bin/env bash
# resolve-owner-chat.sh — operator-rejecting owner-chat resolver
#
# Mirrors the core S0→S1→S2 logic of install.sh
# resolve_telegram_target_universal(), providing a single sourceable helper
# that update-skills.sh and any future scripts can use so the operator-rejection
# logic lives in ONE authoritative place.
#
# Usage (source this file, then call the function):
#   source "$(dirname "$0")/resolve-owner-chat.sh"
#   TARGET=$(resolve_owner_chat_id)
#
# Returns (stdout): the first valid non-operator owner chat ID, or empty string
# if none found.
#
# OPERATOR_CHAT_IDS must be kept in sync with:
#   install.sh            — OPERATOR_CHAT_IDS Python set (line ~249)
#   nudge-incomplete-interviews.py — OPERATOR_CHAT_IDS Python set (line ~37)
#   tests/unit/cron-owner-chat-guard.test.sh — OPERATOR_IDS assertion
#
# v12.3.8 / fix/v12.3.8-cron-resolver-parity

# The three known operator chat IDs. NEVER return these as client owner targets.
OPERATOR_CHAT_IDS_SH="5252140759 6663821679 6771245262"

resolve_owner_chat_id() {
    local ocjson="$HOME/.openclaw/openclaw.json"
    [ -d "/data/.openclaw" ] && ocjson="/data/.openclaw/openclaw.json"

    python3 - <<PYEOF 2>/dev/null
import json, os

# OPERATOR_CHAT_IDS — must match install.sh + nudge-incomplete-interviews.py exactly.
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}

def is_valid_owner_chat(v, bot_id=""):
    """Return the normalised chat ID if valid and non-operator, else empty string."""
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
    if s in OPERATOR_CHAT_IDS:
        return ""
    return s

oc_json = os.path.expanduser("$ocjson")
cfg = {}
try:
    cfg = json.load(open(oc_json))
except Exception:
    pass

bot_id = ""
bt = cfg.get("channels", {}).get("telegram", {}).get("botToken", "") or ""
if ":" in bt:
    bot_id = bt.split(":")[0]

# S0: OPENCLAW_OWNER_CHAT_ID env var — explicit operator override (wins first)
s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = is_valid_owner_chat(s0, bot_id)
    if cid:
        print(cid)
        raise SystemExit(0)

# S1: channels.telegram.allowFrom — first non-operator entry
for v in cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid:
        print(cid)
        raise SystemExit(0)

# S2: commands.ownerAllowFrom — first non-operator entry
for v in cfg.get("commands", {}).get("ownerAllowFrom", []):
    cid = is_valid_owner_chat(v, bot_id)
    if cid:
        print(cid)
        raise SystemExit(0)

# No valid non-operator owner chat found
print("")
PYEOF
}
