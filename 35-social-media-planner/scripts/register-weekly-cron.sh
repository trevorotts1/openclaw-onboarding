#!/usr/bin/env bash
# ============================================================
#  register-weekly-cron.sh
#  Skill 35 — Social Media Planner / Content Publishing Engine
#
#  Registers the weekly content-theme cron via the OpenClaw
#  gateway cron store (NOT .cron.jobs — that block does not
#  validate on 2026.5.27+).
#
#  IDEMPOTENT + DEDUPING:
#   - Reads `openclaw cron list` before registering.
#   - If ONE healthy (non-error) skill35-weekly-theme entry
#     exists with sessionTarget=main AND the intended schedule,
#     exits 0 (nothing to do).
#   - If DUPLICATE entries exist, a stale/erroring entry exists,
#     OR the existing entry is on the WRONG schedule, deletes the
#     bad one(s) then re-registers a clean single entry (U129: a
#     wrong-day job is no longer reported healthy).
#
#  FURNACE-SAFE:
#   - Schedule: 0 8 * * 6  (Saturday 8 AM only — weekly)
#   - No retry loop on failure; one clean registration attempt.
#   - Model: CHEAP/FREE — prefers flash or free OpenRouter
#     fallback, never the metered primary pro model.
#   - Idempotency marker: ~/.openclaw/data/skill35/weekly-theme-last-run.json
#     (written by the cron itself on each Saturday run to skip
#      double-fires). /tmp marker is NOT used — /tmp is not
#      persistent across reboots.
#
#  FAIL-LOUD: exits non-zero on any registration failure.
#  Callers (INSTALL.md Step 9) MUST check the exit code.
#
#  VPS context: runs inside the Hostinger Docker container
#  where `openclaw` CLI is on PATH. Same pattern as Skill 38's
#  04-register-crons.sh.
#
#  Cron: Saturday 8:00 AM (0 8 * * 6) — weekly theme + plan.
# ============================================================
set -euo pipefail

CRON_NAME="skill35-weekly-theme"
CRON_EXPR="0 8 * * 6"
# sessionTarget MUST be 'main' (isolated + channel-deliver is rejected by the gateway)
SESSION_TARGET="main"
# Use the cheap/free flash model; the cron prompt is lightweight (weekly question only).
# Never set to a metered pro model — this fires every Saturday fleet-wide.
AGENT_ID="${SKILL35_CRON_AGENT:-main}"

# Idempotency marker directory (persistent across reboots; /tmp is NOT persistent)
MARKER_DIR="${HOME}/.openclaw/data/skill35"
mkdir -p "$MARKER_DIR"

command -v openclaw >/dev/null 2>&1 || {
  echo "ERROR: openclaw CLI not on PATH — cannot register cron via the gateway cron store." >&2
  echo "Expose the openclaw CLI and re-run. Do NOT write to .cron.jobs — it does not validate on 2026.5.27+." >&2
  exit 2
}

# ----------------------------------------------------------
# Deduplication: detect and remove stale/erroring/duplicate
# entries before registering a clean one.
# ----------------------------------------------------------
_list_output="$(openclaw cron list 2>/dev/null || true)"

# Count existing entries with this cron name
_existing_count="$(echo "$_list_output" | grep -c "$CRON_NAME" || true)"

# Normalize a cron expression for comparison: collapse whitespace runs to a single
# space and trim leading/trailing space, so "0  8 * * 6" compares equal to "0 8 * * 6".
_normalize_cron() { printf '%s' "$1" | tr -s '[:space:]' ' ' | sed -e 's/^ //' -e 's/ $//'; }
_intended_norm="$(_normalize_cron "$CRON_EXPR")"

if [ "$_existing_count" -eq 1 ]; then
  # Exactly one entry — check if it is healthy: main target, non-error, AND on the
  # intended schedule. U129: the old check verified only row count + session target,
  # so an entry scheduled for the WRONG day (e.g. Monday "0 8 * * 1") satisfied both
  # checks and the weekly cycle silently ran on the wrong day. Parse the schedule out
  # of the existing row (a 5-field cron expression) and compare it to the intended
  # one; any mismatch falls through to delete + re-register.
  _is_main="$(echo "$_list_output" | grep "$CRON_NAME" | grep -c "main" || true)"
  _is_error="$(echo "$_list_output" | grep "$CRON_NAME" | grep -c "error" || true)"
  # Extract the existing 5-field cron schedule (minute hour dom month dow) from the
  # entry's row. If it cannot be parsed, _existing_norm is empty and the comparison
  # below fails closed (re-register) rather than trusting an unverifiable schedule.
  _existing_schedule="$(echo "$_list_output" | grep "$CRON_NAME" | head -1 \
    | grep -oE '[0-9*,/-]+[[:space:]]+[0-9*,/-]+[[:space:]]+[0-9*,/-]+[[:space:]]+[0-9*,/-]+[[:space:]]+[0-9*,/-]+' \
    | head -1 || true)"
  _existing_norm="$(_normalize_cron "$_existing_schedule")"

  if [ "$_is_main" -ge 1 ] && [ "$_is_error" -eq 0 ] && [ "$_existing_norm" = "$_intended_norm" ]; then
    echo "OK: cron '$CRON_NAME' already registered with a healthy main-target entry on the correct schedule ($_intended_norm) — nothing to do." >&2
    exit 0
  fi
  # One entry but it is erroring, not on main, or on the WRONG schedule — fall
  # through to delete + re-register.
  if [ "$_existing_norm" != "$_intended_norm" ]; then
    echo "NOTICE: existing '$CRON_NAME' entry is on schedule '${_existing_norm:-<unparseable>}' but expected '$_intended_norm' — will delete and re-register." >&2
  else
    echo "NOTICE: existing '$CRON_NAME' entry is stale or erroring — will delete and re-register." >&2
  fi
fi

if [ "$_existing_count" -ge 1 ]; then
  # Delete ALL existing entries for this cron name (handles duplicates + erroring entries).
  # `openclaw cron delete --name` removes by name; if that flag is unavailable, use --all-named.
  echo "Removing ${_existing_count} existing '$CRON_NAME' cron entries before clean registration..." >&2

  # Try by-name deletion first (preferred, leaves other crons intact)
  if openclaw cron delete --name "$CRON_NAME" 2>/dev/null; then
    echo "Removed existing '$CRON_NAME' entries via --name flag." >&2
  else
    # Fallback: collect IDs from list output and delete individually
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
# Cron message — tells the agent exactly what to do on fire.
# Marker path is the persistent ~/.openclaw/data/skill35/
# weekly-theme-last-run.json (NOT /tmp — /tmp is cleared on
# reboot and does not survive between Saturdays reliably).
# ----------------------------------------------------------
CRON_MESSAGE="Skill 35 weekly theme trigger (Saturday 8 AM). \
Before doing anything, check the idempotency marker: \
${MARKER_DIR}/weekly-theme-last-run.json. \
If it exists and its 'weekISO' field matches the current ISO week \
(date +%G-W%V), skip gracefully — this week's theme request already ran. \
Otherwise: \
(1) Ask the owner: 'What is the content theme for this week's social media content? \
If you do not reply by noon I will use the evergreen theme.' \
Wait up to 1 hour for a reply. If no reply by 12:00 PM ask once more. \
If no reply by 6:00 PM, use the evergreen theme. \
(2) After the theme is confirmed or defaulted, run the weekly social media planning cycle: \
bash \${HOME}/.openclaw/skills/35-social-media-planner/scripts/run-publishing-cycle.sh \
for all topics due this week (read \${HOME}/.openclaw/config/content-calendar.json). \
(3) Write ${MARKER_DIR}/weekly-theme-last-run.json with \
{\"weekISO\": \"\$(date +%G-W%V)\", \"theme\": \"<chosen theme>\", \"firedAt\": \"\$(date -u +%Y-%m-%dT%H:%M:%SZ)\"} \
so re-fires this week are skipped. \
Model guidance: use the cheapest available model (flash or free OpenRouter fallback). \
Do NOT use a metered primary pro model for this weekly question."

# ----------------------------------------------------------
# Registration — FAIL-LOUD (set -e will propagate non-zero).
# sessionTarget MUST be 'main'; 'isolated' with --announce
# --channel is rejected by the gateway (confirmed on client install 2026-06-15).
# ----------------------------------------------------------
echo "Registering cron '$CRON_NAME' ($CRON_EXPR, sessionTarget=$SESSION_TARGET, agent=$AGENT_ID)..." >&2

openclaw cron add \
  --name "$CRON_NAME" \
  --cron "$CRON_EXPR" \
  --agent "$AGENT_ID" \
  --session-target "$SESSION_TARGET" \
  --message "$CRON_MESSAGE" \
  --light-context || {
    echo "ERROR: 'openclaw cron add' failed — Skill 35 weekly-theme cron NOT registered." >&2
    echo "This is a HARD FAIL. Do not proceed with Step 10 until the cron is registered." >&2
    exit 1
  }

echo "OK: cron '$CRON_NAME' registered ($CRON_EXPR — Saturday 8:00 AM weekly)." >&2

# ----------------------------------------------------------
# Post-registration QC assertion: exactly 1 entry, main target.
# Hard-fail if the count is wrong.
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

echo "QC PASS: exactly 1 '$CRON_NAME' cron registered, sessionTarget=main." >&2

# Validate config is still clean after registering
if openclaw config validate 2>/dev/null; then
  echo "OK: openclaw config validate passed." >&2
else
  echo "WARN: openclaw config validate returned non-zero after cron registration — inspect config." >&2
  # Non-fatal: config validate failure is a warning, not a blocker for cron registration.
fi

echo "OK: Skill 35 weekly-theme cron registered, deduped, and QC assertions passed." >&2
