#!/usr/bin/env bash
# install-remote-rescue.sh - Skill 15 step that wires up the operator-side
# Remote Rescue agent (operator INBOUND access) + an OPT-IN operator escalation
# chat key.
#
# ISOLATION MODEL (v2.0.0+)
# --------------------------
# OpenClaw keys every conversation as agent:<agentId>:telegram:<chatId>.
# Operators (Trevor / Spaulding / LeAnne) must land in a session keyed to
# "remote-rescue", NEVER to "main" (the owner's agent).
#
# OPERATOR INBOUND (always applied — this is the desired "we can still reach the
# client agent" behavior): operator IDs are added to channels.telegram.allowFrom,
# stripped from groupAllowFrom, and bound to the remote-rescue agent.
#
# OPERATOR ESCALATION DESTINATION (OPT-IN — v12.4.0 co-mingling guard): the
# PROACTIVE-SEND chat (env.vars.OPERATOR_ESCALATION_CHAT_ID) is written ONLY when
# an operator chat id is explicitly provided (interactive prompt answer or
# OPERATOR_ESCALATION_CHAT_ID / OPERATOR_TELEGRAM_CHAT_ID env). There is NO
# hardcoded personal-chat default: a client box installed without one ships with
# operator escalation DISABLED and will never proactively message an operator.
#
# Idempotent. Safe to re-run. Backs up openclaw.json before any write.
# Modes: (default) interactive; --repair non-interactive re-apply.

set -euo pipefail

REPAIR_MODE=0
for arg in "$@"; do
  [[ "$arg" == "--repair" ]] && REPAIR_MODE=1
done

# OPT-IN escalation chat — NO hardcoded default. Empty == escalation disabled.
DEFAULT_CHAT_ID="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}"
TS="$(date -u +%Y%m%d-%H%M%S)"
RR_WORKSPACE_PATH="${RR_WORKSPACE:-$HOME/.openclaw/workspaces/remote-rescue}"

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
if [[ "$REPAIR_MODE" != "1" && "${NONINTERACTIVE:-0}" != "1" ]]; then
  if [[ -t 0 ]]; then
    echo "Operator escalation routes PROACTIVE messages (maintenance/escalation) to a"
    echo "chat. This is OPT-IN. Leave BLANK to DISABLE operator escalation on this box"
    echo "(operator inbound access is configured either way)."
    read -r -p "Operator escalation Telegram chat ID [blank = disabled]${DEFAULT_CHAT_ID:+ [$DEFAULT_CHAT_ID]}: " input || true
    CHAT_ID="${input:-$DEFAULT_CHAT_ID}"
  fi
fi

# CO-MINGLING GUARD (v12.4.0): only persist the escalation destination if one was
# explicitly provided. Empty => operator escalation stays DISABLED (no proactive
# send). We write BOTH the canonical key and the back-compat key.
if [[ -n "$CHAT_ID" ]]; then
  echo "Using operator escalation chat ID: $CHAT_ID"
  openclaw config set env.vars.OPERATOR_ESCALATION_CHAT_ID "\"$CHAT_ID\"" --strict-json >/dev/null
  openclaw config set env.vars.OPERATOR_TELEGRAM_CHAT_ID  "\"$CHAT_ID\"" --strict-json >/dev/null
  echo "Set env.vars.OPERATOR_ESCALATION_CHAT_ID = $CHAT_ID (and back-compat OPERATOR_TELEGRAM_CHAT_ID)"
else
  echo "No operator escalation chat provided — operator escalation DISABLED (opt-in)."
  echo "Operator INBOUND access is still configured below (allowFrom + remote-rescue binding)."
fi

# The three operator IDs always get INBOUND access (allowFrom + remote-rescue
# binding). This is the desired "operators can still message the client agent"
# behavior and is independent of the (opt-in) escalation destination above.
OPERATOR_IDS_JSON='["5252140759","6663821679","6771245262"]'

python3 - "$CFG" "$CHAT_ID" "$OPERATOR_IDS_JSON" "$RR_WORKSPACE_PATH" <<'PYEOF'
import json, sys

cfg_path   = sys.argv[1]
extra_id   = sys.argv[2]
op_ids_raw = json.loads(sys.argv[3])
rr_ws      = sys.argv[4]

with open(cfg_path) as f:
    cfg = json.load(f)

# Operator INBOUND access set: the three operator IDs, plus the explicit escalation
# chat id ONLY if one was provided (never add an empty string to allowFrom).
team_ids = list(op_ids_raw)
if extra_id and extra_id.strip():
    team_ids.append(extra_id.strip())
team_ids = list(dict.fromkeys(team_ids))

tg = cfg.setdefault("channels", {}).setdefault("telegram", {})

existing_allow = tg.get("allowFrom") or []
if not isinstance(existing_allow, list):
    existing_allow = []
tg["allowFrom"] = list(dict.fromkeys([*existing_allow, *sorted(team_ids)]))

existing_group = tg.get("groupAllowFrom") or []
if isinstance(existing_group, list):
    cleaned = [x for x in existing_group if x not in set(team_ids)]
    tg["groupAllowFrom"] = cleaned
    removed = len(existing_group) - len(cleaned)
    if removed:
        print(f"  Removed {removed} operator ID(s) from groupAllowFrom (isolation fix)")

agents = cfg.setdefault("agents", {}).setdefault("list", [])
rr_index = next((i for i, a in enumerate(agents) if a.get("id") == "remote-rescue"), None)

rr_entry = {
    "id": "remote-rescue",
    "name": "Remote Rescue by T Otts",
    "description": (
        "Operator-side management agent. Bound exclusively to operator chat IDs. "
        "Messages from these IDs resolve here NEVER to the owner's main agent."
    ),
    "workspace": rr_ws,
    "subagents": {"allowAgents": ["*"]},
    "telegram": {
        "allowFrom": sorted(team_ids)
    },
}

if rr_index is not None:
    existing = agents[rr_index]
    existing["description"] = rr_entry["description"]
    existing["workspace"]   = rr_entry["workspace"]
    existing.setdefault("subagents", {})["allowAgents"] = ["*"]
    existing.setdefault("telegram", {})["allowFrom"] = sorted(team_ids)
    print("  Updated existing remote-rescue agent (workspace + telegram.allowFrom)")
else:
    agents.append(rr_entry)
    print("  Appended new remote-rescue agent")

with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")

print("Patched openclaw.json:")
print(f"  allowFrom      <- operator IDs added: {sorted(team_ids)}")
print(f"  groupAllowFrom <- operator IDs stripped (owner group stays clean)")
print(f"  remote-rescue  <- bound to operator IDs, workspace={rr_ws}")
PYEOF

openclaw config validate >/dev/null
echo "Config validated."

mkdir -p "$RR_WORKSPACE_PATH"
echo "Remote Rescue workspace: $RR_WORKSPACE_PATH"

if [[ "${SKIP_BOOTSTRAP_MSG:-0}" != "1" && -n "$CHAT_ID" ]]; then
  CLIENT_NAME_S="${CLIENT_NAME:-<client>}"
  BOT_S="${CLIENT_BOT_USERNAME:-<bot>}"
  PERSONA_S="${PERSONA:-<persona>}"
  HOST_S="${HOST_NAME:-$(hostname)}"

  MSG="Remote Rescue by T Otts is now active on ${CLIENT_NAME_S}'s OpenClaw setup.

ISOLATION: Your DMs to @${BOT_S} are automatically routed to the remote-rescue agent (isolated from the owner's session). No /agent switch needed -- routing is config-driven and permanent.

- Client persona: ${PERSONA_S}
- Host: ${HOST_S}
- Your session key: agent:remote-rescue:telegram:<your-chat-id>
- Owner session key: agent:main:telegram:<owner-chat-id>"

  if openclaw message send --channel telegram --target "$CHAT_ID" --message "$MSG" 2>/dev/null; then
    echo "Bootstrap message sent to $CHAT_ID"
  else
    echo "Warning: bootstrap message send failed." >&2
  fi
fi

echo "Remote Rescue install complete."
echo "Verify: openclaw config get agents.list | grep -A10 remote-rescue"
