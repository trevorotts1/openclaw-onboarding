#!/usr/bin/env bash
# install-remote-rescue.sh — Skill 15 step that wires up the operator-side
# Remote Rescue agent + the OPERATOR_TELEGRAM_CHAT_ID config key.
#
# Idempotent. Safe to re-run. Backs up openclaw.json before any write.
#
# Run on the Mac host (or wherever the openclaw CLI is on PATH).
#
# Env overrides:
#   OPERATOR_TELEGRAM_CHAT_ID  — chat ID to prompt-default to (else 5252140759)
#   NONINTERACTIVE             — set to 1 to skip the prompt and use default
#   CLIENT_NAME                — client display name for the bootstrap message
#   CLIENT_BOT_USERNAME        — client bot username for the bootstrap message
#   PERSONA                    — persona name for the bootstrap message
#   HOST_NAME                  — host label for the bootstrap message
#   SKIP_BOOTSTRAP_MSG         — set to 1 to skip sending the message

set -euo pipefail

DEFAULT_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
TS="$(date -u +%Y%m%d-%H%M%S)"

resolve_config_path() {
  if openclaw config file >/dev/null 2>&1; then
    openclaw config file 2>/dev/null | tail -1
  elif [[ -f "$HOME/.openclaw/openclaw.json" ]]; then
    echo "$HOME/.openclaw/openclaw.json"
  elif [[ -f /data/.openclaw/openclaw.json ]]; then
    echo /data/.openclaw/openclaw.json
  else
    echo "Cannot locate openclaw.json" >&2
    exit 1
  fi
}

CFG="$(resolve_config_path)"
echo "Config file: $CFG"

cp -a "$CFG" "${CFG}.bak-pre-remote-rescue-${TS}"
echo "Backup: ${CFG}.bak-pre-remote-rescue-${TS}"

CHAT_ID="$DEFAULT_CHAT_ID"
if [[ "${NONINTERACTIVE:-0}" != "1" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Operator Telegram chat ID for escalations [$DEFAULT_CHAT_ID]: " input || true
    CHAT_ID="${input:-$DEFAULT_CHAT_ID}"
  fi
fi
echo "Using operator chat ID: $CHAT_ID"

openclaw config set env.vars.OPERATOR_TELEGRAM_CHAT_ID "\"$CHAT_ID\"" --strict-json >/dev/null
echo "Set env.vars.OPERATOR_TELEGRAM_CHAT_ID = $CHAT_ID"

python3 - "$CFG" "$CHAT_ID" <<'PYEOF'
import json, sys
cfg_path, chat_id = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    cfg = json.load(f)
tg = cfg.setdefault("channels", {}).setdefault("telegram", {})
team_ids = {"5252140759", "6663821679", "6771245262", chat_id}
for k in ("allowFrom", "groupAllowFrom"):
    existing = tg.get(k) or []
    if not isinstance(existing, list):
        existing = []
    merged = list(dict.fromkeys([*existing, *sorted(team_ids)]))
    tg[k] = merged

agents = cfg.setdefault("agents", {}).setdefault("list", [])
have_rr = any(a.get("id") == "remote-rescue" for a in agents)
if not have_rr:
    agents.append({
        "id": "remote-rescue",
        "name": "Remote Rescue by T Otts",
        "description": (
            "Operator-side rescue agent for Trevor Otts. Full privileges on "
            "this box: subagents allow-list is wildcard, no sandbox override, "
            "no tool restrictions beyond global config. Reachable via "
            "`/agent remote-rescue` or `openclaw agent --agent remote-rescue ...`."
        ),
        "subagents": {"allowAgents": ["*"]},
    })

with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print("Patched openclaw.json (allowFrom + groupAllowFrom + remote-rescue agent)")
PYEOF

openclaw config validate >/dev/null
echo "Config validated."

if [[ "${SKIP_BOOTSTRAP_MSG:-0}" != "1" ]]; then
  CLIENT_NAME_S="${CLIENT_NAME:-<client>}"
  BOT_S="${CLIENT_BOT_USERNAME:-<bot>}"
  PERSONA_S="${PERSONA:-<persona>}"
  HOST_S="${HOST_NAME:-$(hostname)}"

  MSG="Hi Trevor, Remote Rescue by T Otts is now active on ${CLIENT_NAME_S}'s OpenClaw setup.

I am the operator-side agent on this box. You have full privileges here (slash commands, any model, full filesystem).

How to reach this instance:
- Client bot: @${BOT_S}
- Client persona: ${PERSONA_S}
- Host: ${HOST_S}
- Your direct route: DM @${BOT_S} then run /agent remote-rescue

Save this in your records."

  if openclaw message send --channel telegram --target "$CHAT_ID" --message "$MSG" 2>/dev/null; then
    echo "Bootstrap message sent to $CHAT_ID"
  else
    echo "Warning: bootstrap message send failed. Re-run manually:" >&2
    echo "  openclaw message send --channel telegram --target $CHAT_ID --message '...'" >&2
  fi
fi

echo "Remote Rescue install complete."
