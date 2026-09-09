#!/usr/bin/env bash
# ============================================================
#  register-weekly-cron.sh
#  Skill 35 — Social Media Planner / Content Publishing Engine
#
#  F07/F17 (social/wf10-weekly-expiry) — FORWARDING ADAPTER.
#
#  This script no longer owns the invitation cadence. The DURABLE
#  cycle service (shared-utils/social_cycle_service.py + the Command
#  Center's src/lib/jobs/social-cycle.ts on the node-cron scheduler)
#  owns the state machine: one cycle per company+local week, persisted
#  invitation/reminder/cutoff state, bounded reminders, next week
#  created independently of last week's response.
#
#  What remains here is the LEGACY TRIGGER REGISTRATION — kept as a
#  forwarding adapter during migration (F17): the cron fires a SHORT
#  message that (1) calls the cycle service advance step and exits.
#  It contains NO multi-hour wait, NO noon/6PM fallback instructions,
#  NO invitation prose — those all live in the durable service now.
#
#  IDEMPOTENT + DEDUPING: exactly one healthy entry; re-running is a
#  no-op. WRONG schedule / erroring entries are replaced.
#
#  ENGINE OWNERSHIP VERIFICATION (--verify): after registering, the
#  script verifies the durable engine-ownership record (exactly one
#  active owner per company; this legacy name recorded as superseded
#  by the durable engine when the CC half is live). --verify exits 0
#  on a verified forwarding-adapter posture, 5 when the ownership
#  record cannot be confirmed (informational; registration itself
#  already succeeded).
#
#  FURNACE-SAFE: 0 8 * * 6 (Saturday 8 AM weekly), cheap model, one
#  registration attempt, no retry loop.
#
#  FAIL-LOUD: exits non-zero on any registration failure.
#
#  VPS context: runs inside the Hostinger Docker container where
#  `openclaw` CLI is on PATH.
#
#  Cron: Saturday 8:00 AM (0 8 * * 6) — lightweight trigger only.
# ============================================================
set -euo pipefail

CRON_NAME="skill35-weekly-theme"
CRON_EXPR="0 8 * * 6"
# sessionTarget MUST be 'main' (isolated + channel-deliver is rejected by the gateway)
SESSION_TARGET="main"
AGENT_ID="${SKILL35_CRON_AGENT:-main}"

# Durable cycle-service state (the STATE MACHINE lives there now — this
# script only registers a lightweight trigger that advances it).
SOCIAL_CYCLE_DIR="${SOCIAL_CYCLE_STATE_DIR:-${HOME}/.openclaw/data/social-cycle}"
MARKER_DIR="${HOME}/.openclaw/data/skill35"
mkdir -p "$MARKER_DIR"

VERIFY_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --verify) VERIFY_ONLY=1 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
  esac
done

command -v openclaw >/dev/null 2>&1 || {
  echo "ERROR: openclaw CLI not on PATH — cannot register cron via the gateway cron store." >&2
  echo "Expose the openclaw CLI and re-run. Do NOT write to .cron.jobs — it does not validate on 2026.5.27+." >&2
  exit 2
}

if [ "$VERIFY_ONLY" -eq 1 ]; then
  # F17 --verify: the durable engine owns the schedule. Verify the engine-
  # ownership record (file-backed twin written by social_cycle_service.py).
  if [ -f "${SOCIAL_CYCLE_DIR}/engine-ownership.json" ] && python3 - "${SOCIAL_CYCLE_DIR}/engine-ownership.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        rows = json.load(fh).get("rows", [])
except (OSError, ValueError):
    print("VERIFY-FAIL: unreadable engine-ownership record"); sys.exit(5)
by_company = {}
for r in rows:
    e = by_company.setdefault(r.get("company_id"), {"active": 0, "superseded": 0})
    if r.get("state") == "active": e["active"] += 1
    elif r.get("state") == "superseded": e["superseded"] += 1
ok = bool(by_company) and all(v["active"] == 1 for v in by_company.values())
print("VERIFY-JSON: companies=%d active_owners=%d superseded=%d ok=%s" % (
    len(by_company), sum(1 for v in by_company.values() if v["active"] == 1),
    sum(v["superseded"] for v in by_company.values()), ok))
sys.exit(0 if ok else 5)
PY
  then
    echo "OK: durable engine-ownership record verified — forwarding adapter posture confirmed." >&2
    exit 0
  fi
  echo "NOTICE: engine-ownership.json not found or invalid under ${SOCIAL_CYCLE_DIR} — the durable cycle service has not claimed ownership yet (deployment-phase step; INSTALL.md documents the handover). The lightweight trigger remains the fallback owner." >&2
  exit 5
fi

# --verify-json: machine-checkable ownership verification (used by tests via
# SOCIAL_CYCLE_STATE_DIR override).
if [ "${1:-}" = "--verify-json" ]; then
  python3 - "${SOCIAL_CYCLE_DIR}" <<'PY'
import json, sys
state = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    with open(f"{state}/engine-ownership.json") as fh:
        data = json.load(fh)
except (OSError, ValueError):
    print("VERIFY-FAIL: no engine-ownership record")
    sys.exit(1)
rows = data.get("rows", [])
active = [r for r in rows if r.get("state") == "active"]
superseded = [r for r in rows if r.get("state") == "superseded"]
by_company = {}
for r in rows:
    by_company.setdefault(r.get("company_id"), {"active": 0, "superseded": 0})
    by_company[r.get("company_id")][r.get("state")] = by_company[r.get("company_id")].get(r.get("state"), 0) + 1
ok = all(v.get("active") == 1 for v in by_company.values()) if by_company else False
print(f"VERIFY-JSON: companies={len(by_company)} active_owners={sum(1 for v in by_company.values() if v.get('active')==1)} superseded={len(superseded)} ok={ok}")
sys.exit(0 if ok else 5)
PY
  exit $?
fi

# ----------------------------------------------------------
# Deduplication: detect and remove stale/erroring/duplicate
# entries before registering a clean one.
# ----------------------------------------------------------
_list_output="$(openclaw cron list 2>/dev/null || true)"

_existing_count="$(echo "$_list_output" | grep -c "$CRON_NAME" || true)"

if [ "$_existing_count" -eq 1 ]; then
  _is_main="$(echo "$_list_output" | grep "$CRON_NAME" | grep -c "main" || true)"
  _is_error="$(echo "$_list_output" | grep "$CRON_NAME" | grep -c "error" || true)"
  _schedule_ok="$(echo "$_list_output" | grep "$CRON_NAME" | grep -cF "$CRON_EXPR" || true)"

  if [ "$_is_main" -ge 1 ] && [ "$_is_error" -eq 0 ] && [ "$_schedule_ok" -ge 1 ]; then
    echo "OK: cron '$CRON_NAME' already registered with a healthy main-target entry and correct schedule ($CRON_EXPR) — nothing to do." >&2
    exit 0
  fi
  if [ "$_schedule_ok" -eq 0 ]; then
    echo "NOTICE: existing '$CRON_NAME' entry has wrong schedule (expected $CRON_EXPR) — will delete and re-register." >&2
  else
    echo "NOTICE: existing '$CRON_NAME' entry is stale or erroring — will delete and re-register." >&2
  fi
fi

if [ "$_existing_count" -ge 1 ]; then
  echo "Removing ${_existing_count} existing '$CRON_NAME' cron entries before clean registration..." >&2

  if openclaw cron delete --name "$CRON_NAME" 2>/dev/null; then
    echo "Removed existing '$CRON_NAME' entries via --name flag." >&2
  else
    _ids="$(echo "$_list_output" | grep "$CRON_NAME" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' || true)"
    if [ -n "$_ids" ]; then
      while IFS= read -r _id; do
        [ -z "$_id" ] && continue
        openclaw cron delete --id "$_id" 2>/dev/null && echo "Deleted cron id $_id" >&2 || \
          echo "WARN: could not delete cron id $_id — continuing" >&2
      done <<< "$_ids"
    fi
  fi
fi

# ----------------------------------------------------------
# Cron message — the FORWARDING ADAPTER trigger. SHORT by law: it runs the
# cycle-service advance step (a bounded, row-at-a-time operation) and exits.
# The invitation text, the noon/6PM fallback ladder, and every wait live in
# the DURABLE cycle service — never again inside a prompt.
# ----------------------------------------------------------
CRON_MESSAGE="Skill 35 weekly cycle trigger (Saturday 8 AM) — forwarding adapter for the durable cycle service. \
Run ONLY this short step and exit: \
python3 \${HOME}/.openclaw/skills/../../shared-utils/social_cycle_service.py advance \
  (or, when the Command Center is live on this box, its /api/cron/register scheduler already owns the cadence — \
   verify engine ownership instead of running a second cadence). \
The cycle service ensures this client-local week's cycle, sends the invitation through the theme-intake \
outbox, fires bounded reminders, applies the cutoff disposition, and rolls next week. \
NEVER wait for a reply inside this session. NEVER hardcode a noon/6PM fallback — the durable service \
owns reminder and cutoff timing. \
Model guidance: cheapest available model — this is a short trigger, not a conversation."

# ----------------------------------------------------------
# Registration — FAIL-LOUD (set -e will propagate non-zero).
# ----------------------------------------------------------
echo "Registering cron '$CRON_NAME' ($CRON_EXPR, sessionTarget=$SESSION_TARGET, agent=$AGENT_ID)..." >&2

openclaw cron add \
  --name "$CRON_NAME" \
  --cron "$CRON_EXPR" \
  --agent "$AGENT_ID" \
  --session-target "$SESSION_TARGET" \
  --message "$CRON_MESSAGE" \
  --light-context || {
    echo "ERROR: 'openclaw cron add' failed — Skill 35 weekly trigger NOT registered." >&2
    echo "This is a HARD FAIL. Do not proceed with Step 10 until the cron is registered." >&2
    exit 1
  }

echo "OK: cron '$CRON_NAME' registered ($CRON_EXPR — Saturday 8:00 AM weekly, forwarding adapter)." >&2

# ----------------------------------------------------------
# Post-registration QC assertion: exactly 1 entry, main target.
# ----------------------------------------------------------
_post_count="$(openclaw cron list 2>/dev/null | grep -c "$CRON_NAME" || true)"
if [ "$_post_count" -ne 1 ]; then
  echo "ERROR: QC ASSERT FAILED — expected exactly 1 '$CRON_NAME' cron, found $_post_count." >&2
  echo "Possible duplicate. Run 'openclaw cron list | grep $CRON_NAME' to inspect." >&2
  exit 3
fi

_post_main="$(openclaw cron list 2>/dev/null | grep "$CRON_NAME" | grep -c "main" || true)"
if [ "$_post_main" -lt 1 ]; then
  echo "ERROR: QC ASSERT FAILED — registered '$CRON_NAME' cron does not show 'main' sessionTarget." >&2
  exit 4
fi

echo "QC PASS: exactly 1 '$CRON_NAME' cron registered, sessionTarget=main."

# Validate config is still clean after registering
if openclaw config validate 2>/dev/null; then
  echo "OK: openclaw config validate passed." >&2
else
  echo "WARN: openclaw config validate returned non-zero after cron registration — inspect config." >&2
fi

echo "OK: Skill 35 weekly trigger registered (forwarding adapter; durable cycle service owns the cadence)."