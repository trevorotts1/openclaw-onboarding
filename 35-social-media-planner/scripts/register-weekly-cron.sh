#!/usr/bin/env bash
# register-weekly-cron.sh — Skill 35: Social Media Planner
# U126 fix: uses oc_cron_present() (JSON exact-match) for idempotency.
set -euo pipefail
CRON_NAME="skill35-weekly-theme"; CRON_EXPR="0 8 * * 6"; SESSION_TARGET="main"
AGENT_ID="${SKILL35_CRON_AGENT:-main}"
MARKER_DIR="${HOME}/.openclaw/data/skill35"; mkdir -p "$MARKER_DIR"
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CRON_LIB=""
for _cand in "$_SCRIPT_DIR/../../shared-utils/cron-lib.sh" "${HOME}/.openclaw/skills/shared-utils/cron-lib.sh" "/data/.openclaw/skills/shared-utils/cron-lib.sh"; do
  if [[ -f "$_cand" ]]; then CRON_LIB="$_cand"; break; fi
done
if [[ -n "$CRON_LIB" ]]; then source "$CRON_LIB"
else echo "WARN: shared-utils/cron-lib.sh not found — falling back to grep-based presence check (truncation risk)." >&2; fi
command -v oc_cron_present >/dev/null 2>&1 || oc_cron_present() { return 1; }
command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }
command -v openclaw >/dev/null 2>&1 || { echo "ERROR: openclaw CLI not on PATH." >&2; exit 2; }
if oc_cron_tombstoned "$CRON_NAME"; then
  echo "SKIP: cron '$CRON_NAME' is TOMBSTONED — NOT re-registering." >&2; exit 0
fi
if oc_cron_present "$CRON_NAME"; then
  echo "OK: cron '$CRON_NAME' already present (JSON exact-name match) — nothing to do." >&2; exit 0
fi
_list_output="$(openclaw cron list 2>/dev/null || true)"
_existing_count="$(echo "$_list_output" | grep -c "$CRON_NAME" || true)"
if [ "$_existing_count" -eq 1 ]; then
  _is_main="$(echo "$_list_output" | grep "$CRON_NAME" | grep -c "main" || true)"
  _is_error="$(echo "$_list_output" | grep "$CRON_NAME" | grep -c "error" || true)"
  if [ "$_is_main" -ge 1 ] && [ "$_is_error" -eq 0 ]; then
    echo "OK: cron '$CRON_NAME' already registered with healthy main-target entry — nothing to do." >&2; exit 0
  fi
  echo "NOTICE: existing '$CRON_NAME' entry is stale or erroring — will delete and re-register." >&2
fi
if [ "$_existing_count" -ge 1 ]; then
  echo "Removing ${_existing_count} existing '$CRON_NAME' cron entries..." >&2
  if openclaw cron delete --name "$CRON_NAME" 2>/dev/null; then echo "Removed existing '$CRON_NAME' entries via --name flag." >&2
  else
    _ids="$(echo "$_list_output" | grep "$CRON_NAME" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' || true)"
    if [ -n "$_ids" ]; then
      while IFS= read -r _id; do [ -z "$_id" ] && continue; openclaw cron delete --id "$_id" 2>/dev/null && echo "Deleted cron id $_id" >&2 || echo "WARN: could not delete cron id $_id — continuing" >&2; done <<< "$_ids"
    fi
  fi
fi
CRON_MESSAGE="Skill 35 weekly theme trigger (Saturday 8 AM). \
Before doing anything, check the idempotency marker: ${MARKER_DIR}/weekly-theme-last-run.json. \
If it exists and its 'weekISO' field matches the current ISO week (date +%G-W%V), skip gracefully. \
Otherwise: (1) Ask the owner: 'What is the content theme for this week?' \
Wait up to 1 hour. If no reply by 6:00 PM, use the evergreen theme. \
(2) Run the weekly social media planning cycle. \
(3) Write ${MARKER_DIR}/weekly-theme-last-run.json so re-fires this week are skipped. \
Model guidance: use the cheapest available model."
echo "Registering cron '$CRON_NAME' ($CRON_EXPR)..." >&2
openclaw cron add --name "$CRON_NAME" --cron "$CRON_EXPR" --agent "$AGENT_ID" --session-target "$SESSION_TARGET" --message "$CRON_MESSAGE" --light-context || {
  echo "ERROR: 'openclaw cron add' failed — Skill 35 weekly-theme cron NOT registered." >&2; exit 1
}
echo "OK: cron '$CRON_NAME' registered ($CRON_EXPR — Saturday 8:00 AM weekly)." >&2
if command -v oc_cron_present >/dev/null 2>&1 && oc_cron_present "$CRON_NAME"; then
  echo "QC PASS: cron '$CRON_NAME' present (JSON exact-name match)." >&2
else
  _post_count="$(openclaw cron list 2>/dev/null | grep -c "$CRON_NAME" || true)"
  if [ "$_post_count" -ne 1 ]; then echo "ERROR: QC ASSERT FAILED." >&2; exit 3; fi
  echo "QC PASS: exactly 1 '$CRON_NAME' cron registered, sessionTarget=main." >&2
fi
openclaw config validate 2>/dev/null && echo "OK: openclaw config validate passed." >&2 || echo "WARN: openclaw config validate returned non-zero." >&2
echo "OK: Skill 35 weekly-theme cron registered, deduped, and QC assertions passed." >&2
