#!/usr/bin/env bash
# install-remote-rescue.sh — Skill 15 step that wires up the operator-side
# Remote Rescue agent (operator INBOUND access) + an OPT-IN operator escalation
# destination.
#
# RR-032 CONTRACT (v7.1.0)
# ------------------------
# 1. ENABLE / DISABLE / PRESERVE are three explicit, distinguishable outcomes.
#      enable   an operator chat id is supplied (prompt answer or env)     -> write
#      disable  the operator answered/exported the literal disable token   -> remove
#      preserve empty input on a box that already has an approved          -> keep
#               destination OR a valid custom workspace, and REPORT it
#    Empty input is NEVER treated as disable. That was the RR-032 defect: the
#    old else-branch PRINTED "operator escalation DISABLED (opt-in)" while
#    leaving a previously written OPERATOR_ESCALATION_CHAT_ID in the file, so a
#    repair run reported a state the config did not hold. A report must name a
#    state the file actually holds.
# 2. WORKSPACE comes from the VERIFIED OpenClaw root (resolve-oc-root.sh), not a
#    hardcoded $HOME/.openclaw — a Docker box resolves /data/.openclaw. An
#    existing valid custom mount (RR_WORKSPACE) is retained, never overwritten.
# 3. The source revision is LOCKED and verified by sha256 (CAS). A candidate is
#    written to a temporary file, validated, then ATOMICALLY promoted with a
#    rollback snapshot. The pre-RR-032 script wrote json.dump() straight onto
#    the live config and validated afterwards — so a validation failure left a
#    broken live config behind.
# 4. OPERATOR ROUTING is VERIFIED against the actual resolver shipped with the
#    installed OpenClaw, with isolated sessions per operator identity. Field
#    presence is not evidence: channels.telegram.allowFrom and a per-agent
#    workspace have ZERO routing effect, and agents.<id>.telegram is not even a
#    valid key. Routing requires a top-level bindings entry.
# 5. Authorized operator identities are preserved; owner and operator sessions
#    stay separate (agent:remote-rescue:direct:<id> vs agent:main:main).
#
# Modes: (default) interactive; --repair non-interactive re-apply; --check
# read-only, writes nothing and reports the state it found.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
ENGINE="$HERE/lib/rr-config-transaction.py"
ROUTING_VERIFIER="$HERE/lib/rr-verify-routing.mjs"
LOCK_LIB="$HERE/lib/rr-config-lock.sh"

REPAIR_MODE=0
CHECK_MODE=0
for arg in "$@"; do
  case "$arg" in
    --repair) REPAIR_MODE=1 ;;
    --check) CHECK_MODE=1 ;;
    *) echo "usage: $0 [--repair] [--check]" >&2; exit 2 ;;
  esac
done

# OPT-IN escalation destination. NO hardcoded personal-chat default.
REQUESTED_CHAT_ID="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}"

# Authorized operator identities. Preserved by every run, never removed.
OPERATOR_IDS="${RR_OPERATOR_IDS:-5252140759 6663821679 6771245262}"

# ---------------------------------------------------------------------------
# Resolve the VERIFIED OpenClaw root (Docker /data/.openclaw first, then HOME).
# Falls back to the in-tree helper, then to the engine's own resolution, so the
# script works both from a checkout and from a copied skill dir.
# ---------------------------------------------------------------------------
resolve_root() {
  if [ -f "$REPO_ROOT/shared-utils/resolve-oc-root.sh" ]; then
    # shellcheck source=/dev/null
    source "$REPO_ROOT/shared-utils/resolve-oc-root.sh"
    if resolve_oc_root 2>/dev/null; then
      return 0
    fi
    return 1
  fi
  if [ -d /data/.openclaw ]; then printf '%s\n' /data/.openclaw; return 0; fi
  if [ -d "$HOME/.openclaw" ]; then printf '%s\n' "$HOME/.openclaw"; return 0; fi
  return 1
}

if ! OC_ROOT="$(resolve_root)"; then
  echo "Cannot resolve a verified OpenClaw root: neither /data/.openclaw nor \$HOME/.openclaw exists." >&2
  echo "Nothing was written." >&2
  exit 2
fi

# An explicit config path is authoritative for WHERE THE ROOT IS. Deriving the
# workspace from a different root than the config would put the operator's
# session storage outside the tree the config lives in — and on a Docker box
# that is outside the mount entirely.
CFG_PATH="${OPENCLAW_CONFIG_PATH:-$OC_ROOT/openclaw.json}"
CFG_DIR="$(cd "$(dirname "$CFG_PATH")" && pwd)"
if [ "$CFG_DIR" != "$OC_ROOT" ]; then
  echo "Config path override: root taken from the config's own directory ($CFG_DIR)"
  OC_ROOT="$CFG_DIR"
fi
echo "OpenClaw root: $OC_ROOT"
if [ ! -f "$CFG_PATH" ]; then
  echo "No config at $CFG_PATH — nothing to repair, nothing written." >&2
  exit 2
fi

# Workspace: an explicit RR_WORKSPACE is a valid custom mount and is retained.
if [ -n "${RR_WORKSPACE:-}" ]; then
  WS="$RR_WORKSPACE"
  WS_EXPLICIT=1
else
  WS="$OC_ROOT/workspaces/remote-rescue"
  WS_EXPLICIT=0
fi

# ---------------------------------------------------------------------------
# Prompt (interactive only). The answer distinguishes all three outcomes:
# blank on an enabled box == preserve, `disable` == explicit removal.
# ---------------------------------------------------------------------------
if [ "$REPAIR_MODE" != "1" ] && [ "${NONINTERACTIVE:-0}" != "1" ] && [ "$CHECK_MODE" != "1" ]; then
  if [ -t 0 ]; then
    echo "Operator escalation routes PROACTIVE messages (maintenance/escalation) to a chat."
    echo "  blank    = keep the destination this box already has (preserved)"
    echo "  an id    = set that destination"
    echo "  disable  = remove operator escalation from this box"
    read -r -p "Operator escalation Telegram chat ID [blank = preserve]${REQUESTED_CHAT_ID:+ [$REQUESTED_CHAT_ID]}: " input || true
    if [ -n "${input:-}" ]; then
      REQUESTED_CHAT_ID="$input"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Serialize with a lock, then run the transaction engine.
# ---------------------------------------------------------------------------
# shellcheck source=/dev/null
source "$LOCK_LIB"
LOCK_DIR="$CFG_PATH.rr032-lock"
if ! rr_config_lock "$LOCK_DIR" 30; then
  echo "Another Remote Rescue run holds the config lock; nothing was written." >&2
  exit 4
fi
trap 'rr_config_unlock "$LOCK_DIR"' EXIT

SOURCE_SHA="$(python3 - "$CFG_PATH" <<'PYEOF'
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())
PYEOF
)"

ROLLBACK_SRC=""
if [ "$CHECK_MODE" != "1" ]; then
  ROLLBACK_SRC="$CFG_PATH.rr032-rollback-$(date -u +%Y%m%d-%H%M%S)"
fi

OPENCLAW_BIN="$(command -v openclaw || true)"

# Candidate validation runner: the INSTALLED openclaw validates the candidate.
# Fails closed — if openclaw is absent the candidate is not promoted on the
# strength of a structural check alone.
REPORT_JSON="$(mktemp -t rr032-report)"
set +e
python3 "$ENGINE" \
  --cfg "$CFG_PATH" \
  --mode "$([ "$REPAIR_MODE" = 1 ] && echo repair || echo interactive)" \
  $( [ "$REPAIR_MODE" = 1 ] && echo --repair ) \
  $( [ "${NONINTERACTIVE:-0}" = 1 ] && echo --noninteractive ) \
  --requested "$REQUESTED_CHAT_ID" \
  $( [ "$CHECK_MODE" = 1 ] && echo --check ) \
  --source-revision "sha256:$SOURCE_SHA" \
  --expect-sha "$SOURCE_SHA" \
  --oc-root "$OC_ROOT" \
  --workspace "$WS" \
  $( [ "$WS_EXPLICIT" = 1 ] && echo --workspace-explicit ) \
  --reconcile-operators \
  --reconcile-routing \
  --owner-agent-id "${RR_OWNER_AGENT_ID:-main}" \
  $( for id in $OPERATOR_IDS; do echo --operator-id "$id"; done ) \
  $( [ -n "$ROLLBACK_SRC" ] && printf '%s\n' --rollback-src "$ROLLBACK_SRC" ) \
  --validator-program "$HERE/lib/rr-validate-candidate.sh" \
  --promote-program "$HERE/lib/rr-promote-atomic.sh" \
  --report "$REPORT_JSON" >/dev/null
ENGINE_RC=$?
set -e

python3 - "$REPORT_JSON" "$CFG_PATH" <<'PYEOF'
import json, sys
rep = json.load(open(sys.argv[1]))
print("Remote Rescue state: %s" % rep.get("state"))
print("  destination     : %s" % (rep.get("destination") or "(none)"))
print("  source revision : %s" % (rep.get("source_revision") or "unnamed"))
print("  cas             : %s" % rep.get("cas"))
print("  candidate       : %s (%s)" % (rep.get("validation"), rep.get("validation_detail") or "ok"))
print("  promote         : %s" % rep.get("promote"))
print("  rollback        : %s" % rep.get("rollback"))
print("  workspace       : %s [%s]" % (rep.get("workspace"), rep.get("mount_state")))
for note in rep.get("notes") or []:
    print("  note            : %s" % note)
for tr in rep.get("transitions") or []:
    print("  transition      : %s -> %s (%s)" % (tr.get("from"), tr.get("to"), tr.get("cause")))
PYEOF

STATE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("state"))' "$REPORT_JSON")"

# ---------------------------------------------------------------------------
# Routing acceptance: the REAL resolver, per operator identity, on the config
# that is now live. Field presence is not evidence — this resolves the route.
# ---------------------------------------------------------------------------
RESOLVER=""
for cand in \
  "${OPENCLAW_ROUTING_MODULE:-}" \
  "$(npm root -g 2>/dev/null || true)/openclaw/dist/plugin-sdk/routing.js" \
  "$HOME/.npm-global/lib/node_modules/openclaw/dist/plugin-sdk/routing.js" \
  "/usr/lib/node_modules/openclaw/dist/plugin-sdk/routing.js" \
  "/usr/local/lib/node_modules/openclaw/dist/plugin-sdk/routing.js"; do
  if [ -n "$cand" ] && [ -f "$cand" ]; then RESOLVER="$cand"; break; fi
done

ROUTING_ACCEPTED=0
if [ -n "$RESOLVER" ]; then
  ROUTE_ARGS=()
  for id in $OPERATOR_IDS; do ROUTE_ARGS+=(--operator-id "$id"); done
  if [ -n "${RR_OWNER_CHAT_ID:-}" ]; then ROUTE_ARGS+=(--owner-id "$RR_OWNER_CHAT_ID"); fi
  set +e
  node "$ROUTING_VERIFIER" --config "$CFG_PATH" --module "$RESOLVER" \
       "${ROUTE_ARGS[@]}" > "$REPORT_JSON.routing" 2>&1
  ROUTE_RC=$?
  set -e
  python3 - "$REPORT_JSON.routing" <<'PYEOF'
import json, sys
path = sys.argv[1]
raw = open(path).read()
try:
    d = json.loads(raw)
except Exception as exc:
    print("routing verdict: BLOCKED (unreadable verifier output: %s)" % exc)
    sys.exit(0)
print("routing verdict: %s" % d.get("verdict"))
for c in d.get("checks") or []:
    actual = c.get("actual") or {}
    print("  %-8s %s -> agent=%s session=%s matchedBy=%s" % (
        "ok" if c.get("ok") else "MISMATCH", c.get("subject"),
        actual.get("agentId", "-"), actual.get("sessionKey", "-"),
        actual.get("matchedBy", c.get("detail", "-"))))
PYEOF
  if [ "$ROUTE_RC" = "0" ]; then
    ROUTING_ACCEPTED=1
  else
    echo "Routing acceptance did NOT pass for every operator identity (verifier rc=$ROUTE_RC)." >&2
  fi
else
  echo "Routing acceptance BLOCKED: no installed OpenClaw resolver found." >&2
  echo "  Set OPENCLAW_ROUTING_MODULE to <openclaw>/dist/plugin-sdk/routing.js for the target version." >&2
fi

if [ "$CHECK_MODE" = "1" ]; then
  echo "Check mode: state reported, nothing written."
fi

echo "Remote Rescue install complete (state: $STATE)."
echo "Verify: python3 -c 'import json;print(json.load(open(\"$CFG_PATH\"))[\"bindings\"])'"
exit "$ENGINE_RC"
