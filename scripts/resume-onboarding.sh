#!/usr/bin/env bash
# resume-onboarding.sh — v10.15.48  (FIX 1: INSTALL RESUME)
#
# Autonomous resume layer for SKILL ONBOARDING (the install/wire/QC pipeline),
# modeled on resume-workforce-build.sh. Reads
#   ~/.openclaw/workspace/.onboarding-state.json
# and, while ANY non-archived skill is still pending|downloaded|wired|qc-failed,
# self-pings the agent (via `openclaw message send`) to activate + verify those
# skills. It is the ONLY autonomous-recovery layer for onboarding — without it,
# an interrupted onboarding (or one that an over-eager agent self-declared
# "done") sits forever with un-registered skills.
#
# NEVER-STOP (Rule 8): this cron does NOT exit on a self-declared "done". It
# exits ONLY when the VERIFICATION GATE passes (every skill qc-passed, or an
# explicit interview-pending park). It runs the gate itself (sourcing
# onboarding-state.sh) — it does not trust prose or a hand-flipped flag.
#
# INTERVIEW_PENDING is a LEGITIMATE park, not terminal "done": a skill waiting on
# owner input is re-pinged to the OWNER on backoff (so the owner is reminded),
# and counts toward gate-success only when explicitly parked.
#
# Idempotent. Safe every */15. 10-min lockfile. Escalates to Rescue Rangers +
# operator once at the run cap, then slow-retries (2h backoff) — never stops.

set -u

# ── platform + paths ─────────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[resume-onboarding] no OpenClaw root found; aborting" >&2
  exit 0
fi

# Resolve this script's dir so it can source the gate library sibling.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
GATE_LIB=""
for _cand in \
  "$SCRIPT_DIR/onboarding-state.sh" \
  "$OC_ROOT/scripts/onboarding-state.sh" \
  "$OC_ROOT/onboarding/scripts/onboarding-state.sh" \
  "$HOME/.openclaw/scripts/onboarding-state.sh"; do
  [[ -f "$_cand" ]] && GATE_LIB="$_cand" && break
done

WS="$OC_ROOT/workspace"
STATE_FILE="$WS/.onboarding-state.json"
LOCK_FILE="$WS/.onboarding-resume.lock"
LOG_FILE="$WS/.onboarding-resume.log"
RUN_COUNT_FILE="$WS/.onboarding-resume-runs.count"
MAX_RUNS_BEFORE_ESCALATE=24   # 6h at */15 — then escalate + slow-retry (never stop)

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"; }

# ── operator chat resolver (Remote Rescue) — operator account, NOT client ────
resolve_operator_chat_id() {
  local v=""
  if command -v openclaw >/dev/null 2>&1; then
    v="$(openclaw config get env.vars.OPERATOR_HELP_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
    case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    if [[ -z "$v" ]]; then
      v="$(openclaw config get env.vars.OPERATOR_TELEGRAM_CHAT_ID 2>/dev/null | tail -1 | tr -d '[:space:]')"
      case "$v" in ""|*"not found"*|*"Error"*) v="" ;; esac
    fi
  fi
  [[ -z "$v" && -n "${OPERATOR_HELP_CHAT_ID:-}" ]] && v="$OPERATOR_HELP_CHAT_ID"
  [[ -z "$v" ]] && v="5252140759"
  printf '%s' "$v"
}

# ── find + self-remove this cron by name (only on REAL gate-pass) ────────────
find_self_cron_uuid() {
  command -v openclaw >/dev/null 2>&1 || { echo ""; return 0; }
  openclaw cron list 2>/dev/null \
    | awk '/onboarding-resume/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' \
    | head -1
}
self_remove_cron() {
  local reason="$1" uuid
  uuid="$(find_self_cron_uuid)"
  if [[ -z "$uuid" ]]; then
    log "self_remove_cron($reason): could not resolve onboarding-resume UUID — leaving cron in place"
    return 0
  fi
  log "self_remove_cron($reason): removing cron $uuid"
  if openclaw cron rm "$uuid" 2>>"$LOG_FILE"; then
    log "self_remove_cron($reason): removed $uuid"
    rm -f "$RUN_COUNT_FILE" 2>/dev/null || true
  else
    log "self_remove_cron($reason): openclaw cron rm $uuid FAILED"
  fi
}

mkdir -p "$WS" 2>/dev/null || true

# ── preconditions ────────────────────────────────────────────────────────────
if [[ ! -f "$STATE_FILE" ]]; then
  log "no state file at $STATE_FILE — nothing to resume; exiting clean"
  exit 0
fi
if ! command -v openclaw >/dev/null 2>&1; then
  log "openclaw CLI not on PATH — cannot dispatch resume; exiting"
  exit 0
fi

# ── heal config before any gateway interaction ──────────────────────────────
openclaw doctor --fix >/dev/null 2>&1 || true

# ── BELT: only a REAL gate-pass is terminal ──────────────────────────────────
# Run the verification gate. If it passes, onboarding is genuinely complete →
# self-remove. We do NOT trust any self-declared "done" or a hand-edited state.
GATE_RC=1
GATE_HUMAN=""
if [[ -n "$GATE_LIB" ]]; then
  # shellcheck disable=SC1090
  source "$GATE_LIB" 2>/dev/null || true
  if command -v obs_gate_summary >/dev/null 2>&1; then
    GATE_HUMAN="$(obs_gate_summary 2>/dev/null | grep '^GATE-HUMAN:' | sed 's/^GATE-HUMAN: //')"
    if obs_gate_summary >/dev/null 2>&1; then GATE_RC=0; fi
  fi
else
  log "gate library not found — falling back to JSON status scan (no live skills-info check)"
fi

# Fallback gate when the library is unavailable: every skill must be qc-passed
# or interview-pending in the JSON.
if [[ -z "$GATE_LIB" ]] && command -v python3 >/dev/null 2>&1; then
  GATE_RC=$(STATE_FILE="$STATE_FILE" python3 - <<'PYEOF'
import json, os, sys
try:
    s = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    print(1); sys.exit(0)
sk = s.get("skills", {})
bad = [k for k, v in sk.items() if v.get("status") not in ("qc-passed", "interview-pending")]
print(0 if (sk and not bad) else 1)
PYEOF
)
fi

if [[ "$GATE_RC" == "0" ]]; then
  log "VERIFICATION GATE PASSED (${GATE_HUMAN:-all skills qc-passed/parked}) — onboarding complete; self-removing cron"
  self_remove_cron "gate-passed"
  exit 0
fi

# ── NEVER-STOP run accounting ────────────────────────────────────────────────
_run_count=0
[[ -f "$RUN_COUNT_FILE" ]] && _run_count="$(tr -dc '0-9' < "$RUN_COUNT_FILE" | head -c 6)"
[[ -z "$_run_count" ]] && _run_count=0
_run_count=$((_run_count + 1))
echo "$_run_count" > "$RUN_COUNT_FILE" 2>/dev/null || true

if (( _run_count > MAX_RUNS_BEFORE_ESCALATE )); then
  _over=$(( _run_count - MAX_RUNS_BEFORE_ESCALATE ))
  if (( _over % 8 != 1 )); then
    log "NEVER-STOP: run #$_run_count past cap — 2h-backoff slow mode, skipping this fire. NOT self-removing."
    exit 0
  fi
  # escalate once
  _already="$(command -v jq >/dev/null 2>&1 && jq -r '.resumeEscalated // false' "$STATE_FILE" 2>/dev/null || echo false)"
  if [[ "$_already" != "true" ]]; then
    _op="$(resolve_operator_chat_id)"
    [[ -n "$_op" ]] && openclaw message send --channel telegram -t "$_op" \
      -m "⚠️ onboarding-resume on $(hostname) hit $_run_count runs without the verification gate passing (${GATE_HUMAN:-skills still un-verified}). Now slow-retrying (it does NOT stop). State: $STATE_FILE" 2>>"$LOG_FILE" || true
    # Escalate via the n8n Rescue Rangers webhook (NOT bot-to-bot Telegram —
    # bots can't read other bots, so the old group post never reached the rescue agent).
    _rr_webhook="${RESCUE_RANGERS_WEBHOOK_URL:-https://main.blackceoautomations.com/webhook/rescue-rangers}"
    if [[ -n "$_rr_webhook" ]] && command -v curl >/dev/null 2>&1; then
      _rr_msg="onboarding on $(hostname) past $_run_count resume runs without a gate-pass. Run scripts/onboarding-state.sh -> obs_gate_summary on the box. State: $STATE_FILE. OpenClaw version: $(openclaw --version 2>/dev/null | head -1)"
      _rr_payload=$(jq -nc --arg c "$(hostname)" --arg a "main" --arg m "$_rr_msg" \
        '{action:"escalate",client:$c,agent:$a,message:$m}' 2>/dev/null)
      curl -s -X POST "$_rr_webhook" -H "Content-Type: application/json" -d "$_rr_payload" >>"$LOG_FILE" 2>&1 || true
    fi
    if command -v jq >/dev/null 2>&1; then
      _tmp="$(mktemp)"; jq '.resumeEscalated = true' "$STATE_FILE" > "$_tmp" 2>/dev/null && mv "$_tmp" "$STATE_FILE" || rm -f "$_tmp"
    fi
  fi
  log "NEVER-STOP: run #$_run_count past cap — slow-retry fire; continuing (NOT self-removing)."
fi

# ── lock (no double self-ping) ───────────────────────────────────────────────
if [[ -f "$LOCK_FILE" ]]; then
  lock_mtime="$(stat -c %Y "$LOCK_FILE" 2>/dev/null || stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)"
  now="$(date +%s)"; age=$(( now - lock_mtime ))
  if (( age < 600 )); then
    log "lock held ${age}s (<600) — another resume in flight; exiting"
    exit 0
  fi
  log "stale lock (age ${age}s) — clearing"
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# ── compute the work list (pending/downloaded/wired/qc-failed) ───────────────
WORK_LIST=""
PARK_LIST=""
if command -v python3 >/dev/null 2>&1; then
  WORK_LIST="$(STATE_FILE="$STATE_FILE" python3 - <<'PYEOF'
import json, os
try:
    s = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    s = {"skills": {}}
bad = [k for k, v in s.get("skills", {}).items()
       if v.get("status") in ("pending", "downloaded", "wired", "qc-failed", "unknown")]
print(", ".join(sorted(bad)))
PYEOF
)"
  PARK_LIST="$(STATE_FILE="$STATE_FILE" python3 - <<'PYEOF'
import json, os
try:
    s = json.load(open(os.environ["STATE_FILE"]))
except Exception:
    s = {"skills": {}}
park = [k for k, v in s.get("skills", {}).items() if v.get("status") == "interview-pending"]
print(", ".join(sorted(park)))
PYEOF
)"
fi

if [[ -z "$WORK_LIST" && -z "$PARK_LIST" ]]; then
  log "no un-verified skills found but gate did not pass — re-running gate next cycle"
  exit 0
fi

# ── target chat: owner (paired) preferred; else operator (Remote Rescue) ─────
owner_chat=""
if command -v jq >/dev/null 2>&1; then
  owner_chat="$(jq -r '.ownerChat // empty' "$STATE_FILE" 2>/dev/null)"
fi
TARGET_CHAT="$owner_chat"
[[ -z "$TARGET_CHAT" || "$TARGET_CHAT" == "null" ]] && TARGET_CHAT="$(resolve_operator_chat_id)"
[[ -z "$TARGET_CHAT" ]] && { log "no usable target chat — cannot dispatch"; exit 0; }

# ── INTERVIEW_PENDING owner re-ping (legitimate park, on backoff) ────────────
# Re-ping the OWNER about parked skills periodically (every 4th fire ≈ hourly)
# so a real owner-input wait is not silently forgotten. NOT treated as failure.
if [[ -n "$PARK_LIST" ]] && (( _run_count % 4 == 0 )); then
  openclaw message send --channel telegram -t "$TARGET_CHAT" \
    -m "👋 Quick reminder: these are ready as soon as you have a moment to answer a couple of questions — ${PARK_LIST}. No rush; just don't want them to stall." 2>>"$LOG_FILE" || true
  log "re-pinged owner about INTERVIEW_PENDING parks: $PARK_LIST"
fi

# ── dispatch the resume self-ping (internal — drives activation + gate) ──────
msg="[ONBOARDING-RESUME] The skill onboarding is NOT verified-complete. These skills are not yet qc-passed: ${WORK_LIST:-none}. ${PARK_LIST:+(parked awaiting owner input: ${PARK_LIST}.) }DO THIS: (1) source the gate library ~/.openclaw/scripts/onboarding-state.sh; (2) for EACH not-passed skill folder under ~/.openclaw/skills/: read SKILL.md+INSTALL.md+CORE_UPDATES.md, EXECUTE INSTALL.md activation (read ≠ execute), merge CORE_UPDATES surgically, then run obs_verify_skill <folder> and loop activate→verify until it returns qc-passed; (3) a skill that genuinely needs owner input may be parked via obs_set_status <folder> interview-pending (then ask the owner) — that is the ONLY non-passed terminal state; (4) when obs_gate_summary returns success, remove the UPDATE PENDING flag from AGENTS.md and tell the owner the HONEST count. Do NOT report installed/done/onboarded for any skill that is not qc-passed. This resume is internal — keep owner messages to plain-English progress only. Run #$_run_count."

if openclaw message send --channel telegram -t "$TARGET_CHAT" -m "$msg" >>"$LOG_FILE" 2>&1; then
  log "dispatched ONBOARDING-RESUME self-ping to $TARGET_CHAT (work: ${WORK_LIST:-none}; park: ${PARK_LIST:-none})"
else
  log "FAILED to dispatch resume self-ping to $TARGET_CHAT (see log)"
fi
exit 0
