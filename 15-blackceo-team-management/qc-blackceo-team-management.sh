#!/usr/bin/env bash
# Skill 15 - BlackCEO Team Management - Install QC
# v2.0.0: HARD auto-fail gates for operator/owner session isolation.
# A rule not auto-failed at this gate does not exist.
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }
green(){ printf "\033[32m%s\033[0m\n" "$1"; }
yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  PASS -- $1"; PASS=$((PASS+1)); else red "  FAIL -- $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  PASS -- $1"; PASS=$((PASS+1)); else yellow "  WARN -- $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${CLIENT_ID:=}"

# RR-032: resolve the VERIFIED root (Docker /data/.openclaw wins over HOME) so a
# container box is not inspected through a stale HOME copy of the config.
CFG_PATH=""
if [ -f "$SKILL_DIR/../shared-utils/resolve-oc-root.sh" ]; then
  # shellcheck source=/dev/null
  . "$SKILL_DIR/../shared-utils/resolve-oc-root.sh"
  _root="$(resolve_oc_root 2>/dev/null || true)"
  [ -n "$_root" ] && [ -f "$_root/openclaw.json" ] && CFG_PATH="$_root/openclaw.json"
fi
if [ -z "$CFG_PATH" ]; then
  for p in /data/.openclaw/openclaw.json "$HOME/.openclaw/openclaw.json"; do
    [ -f "$p" ] && { CFG_PATH="$p"; break; }
  done
fi

echo ""
echo "=== Skill 15 - BlackCEO Team Management - Install QC ==="
echo ""

assert "Skill 15 folder present" "[ -d \"$SKILLS_DIR_DEFAULT/15-blackceo-team-management\" ]"
assert "CLIENT_ID env OR stored in MEMORY.md" \
  "[ -n \"$CLIENT_ID\" ] || grep -qE 'CLIENT_ID|owner.*telegram|telegram.*owner' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
warn_only "TEAM_MEMBER_*_ID values present (not placeholders)" \
  "env | grep -E '^TEAM_MEMBER_[0-9]+_ID=[0-9]{7,}' | grep -vE '_ID=1234567890|_ID=0000' | head -1 | grep -q ."
warn_only "AGENTS.md references team management" "grep -qiE 'team management|TEAM_MEMBER' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
warn_only "Python 3 installed" "command -v python3"

echo ""
echo "=== HARD GATE: Operator / Owner Session Isolation ==="
echo "    A rule not auto-failed here does not exist."
echo ""

if [ -z "$CFG_PATH" ]; then
  red "  FAIL -- cannot locate openclaw.json; skipping isolation gates"
  FAIL=$((FAIL+1))
else

assert "remote-rescue agent present in the roster (entries or list form)" \
  "python3 -c \"
import json
cfg = json.load(open('$CFG_PATH'))
ag = cfg.get('agents', {})
entries = ag.get('entries') if isinstance(ag.get('entries'), dict) else None
if entries is not None:
    assert 'remote-rescue' in entries, 'no remote-rescue entry'
else:
    next(a for a in ag.get('list', []) if a.get('id') == 'remote-rescue')
\""

# RR-032: a per-agent telegram.allowFrom and a per-agent workspace have NO
# routing effect (verified against the resolver: agents.<id>.telegram is not
# even a schema key). The routing mechanism is a top-level bindings entry.
assert "every operator DM has a real bindings route to remote-rescue (not field presence)" \
  "python3 -c \"
import json
cfg = json.load(open('$CFG_PATH'))
op_ids = {'5252140759', '6663821679', '6771245262'}
routed = set()
for b in (cfg.get('bindings') or []):
    if not isinstance(b, dict) or b.get('agentId') != 'remote-rescue':
        continue
    peer = ((b.get('match') or {}).get('peer') or {})
    if str(peer.get('id') or '') in op_ids:
        routed.add(str(peer.get('id')))
missing = op_ids - routed
assert not missing, f'operator DMs with no binding route: {sorted(missing)}'
\""

assert "remote-rescue has workspace field (session storage isolated from main)" \
  "python3 -c \"
import json
cfg = json.load(open('$CFG_PATH'))
ag = cfg.get('agents', {})
entries = ag.get('entries') if isinstance(ag.get('entries'), dict) else None
if entries is not None:
    rr = entries.get('remote-rescue')
else:
    rr = next((a for a in ag.get('list', []) if a.get('id') == 'remote-rescue'), None)
assert rr and rr.get('workspace'), 'no workspace'
\""

GATE4_RESULT=$(python3 - "$CFG_PATH" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
op_ids = {"5252140759", "6663821679", "6771245262"}
group_allow = set(cfg.get("channels", {}).get("telegram", {}).get("groupAllowFrom") or [])
leak = op_ids & group_allow
if leak:
    print("FAIL: " + str(sorted(leak)))
    sys.exit(1)
print("PASS")
PYEOF
)
if [[ "$GATE4_RESULT" == PASS ]]; then
  green "  PASS -- operator IDs not in groupAllowFrom (no group-session collision)"
  PASS=$((PASS+1))
else
  red "  FAIL -- operator IDs in groupAllowFrom: $GATE4_RESULT"
  red "         Run: bash scripts/install-remote-rescue.sh --repair"
  FAIL=$((FAIL+1))
fi

GATE5_RESULT=$(python3 - "$CFG_PATH" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
op_ids = {"5252140759", "6663821679", "6771245262"}
# RR-032: the previous version of this gate read main["telegram"]["allowFrom"],
# a key that does not exist — so the set was always empty and the gate passed
# vacuously. What actually routes an operator DM is a top-level bindings entry.
collision = set()
for b in (cfg.get("bindings") or []):
    if not isinstance(b, dict):
        continue
    peer = ((b.get("match") or {}).get("peer") or {})
    peer_id = str(peer.get("id") or "")
    agent_id = b.get("agentId")
    if peer_id in op_ids and agent_id != "remote-rescue":
        collision.add(f"{peer_id}->{agent_id}")
if collision:
    print("FAIL: " + ", ".join(sorted(collision)))
    sys.exit(1)
print("PASS")
PYEOF
)
if [[ "$GATE5_RESULT" == PASS ]]; then
  green "  PASS -- operator IDs not bound to main agent (no agentId collision)"
  PASS=$((PASS+1))
else
  red "  FAIL -- operator IDs bound to main agent: $GATE5_RESULT"
  red "         Run: bash scripts/install-remote-rescue.sh --repair"
  FAIL=$((FAIL+1))
fi

assert "operator IDs present in channels.telegram.allowFrom" \
  "python3 -c \"
import json
cfg = json.load(open('$CFG_PATH'))
op_ids = {'5252140759','6663821679','6771245262'}
allow = set(cfg.get('channels',{}).get('telegram',{}).get('allowFrom') or [])
missing = op_ids - allow
assert not missing, f'missing: {missing}'
\""

warn_only "env.vars.OPERATOR_ESCALATION_CHAT_ID set (OPT-IN — empty is OK on a client box)" \
  "python3 -c \"import json; cfg=json.load(open('$CFG_PATH')); v=cfg.get('env',{}).get('vars',{}); assert v.get('OPERATOR_ESCALATION_CHAT_ID') or v.get('OPERATOR_TELEGRAM_CHAT_ID')\""

fi

# ─────────────────────────────────────────────────────────────────────────────
# HARD GATE 6 (v12.4.0): CLIENT-box routing must be OWNER-ONLY (no operator
# co-mingling). On a client box (IS_OPERATOR_BOX != 1), the materialized routing
# files must NOT carry an operator ID as a routed worker / reply-target. Operator
# IDs in openclaw.json allowFrom/groupAllowFrom are NOT inspected here (that is
# legitimate inbound access, gated separately above) — only the ROUTING DOCS.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== HARD GATE 6: CLIENT-box routing is owner-only (no operator co-mingling) ==="
echo ""

if [ "${IS_OPERATOR_BOX:-0}" = "1" ]; then
  yellow "  SKIP -- IS_OPERATOR_BOX=1: operator dispatcher roster is allowed on the operator box"
else
  OP_IDS_RE='5252140759|6663821679|6771245262'
  ROUTING_FILES=(
    "$SKILLS_DIR_DEFAULT/15-blackceo-team-management/TEAM_CONFIG.md"
    "$WORKSPACE/WORKFLOW_AUTO.md"
    "$HOME/.openclaw/workspace/WORKFLOW_AUTO.md"
    "$WORKSPACE/AGENTS.md"
    "$WORKSPACE/MEMORY.md"
    "$WORKSPACE/TOOLS.md"
  )
  GATE6_FAIL=0
  for rf in "${ROUTING_FILES[@]}"; do
    [ -f "$rf" ] || continue
    # Flag any non-comment line that contains an operator ID. On a client box,
    # an operator ID has no business being in a routing doc at all (operators are
    # inbound-only via remote-rescue, which lives in openclaw.json, not these docs).
    if grep -vE '^\s*#|^\s*//' "$rf" 2>/dev/null | grep -qE "$OP_IDS_RE"; then
      red "  FAIL -- $rf contains an operator Telegram ID in routing (co-mingling)"
      red "         A client box must ship reply-to-sender + owner-only. Remove the"
      red "         operator roster; operators are inbound-only via remote-rescue."
      GATE6_FAIL=1
    fi
  done
  if [ "$GATE6_FAIL" -eq 0 ]; then
    green "  PASS -- no operator IDs found in client-box routing docs"
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1))
  fi
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed | $WARN warnings ==="
[ $FAIL -gt 0 ] && { red "Skill 15 QC FAILED"; exit 1; } || { green "Skill 15 QC PASS"; exit 0; }
