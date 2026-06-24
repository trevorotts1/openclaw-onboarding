#!/usr/bin/env bash
# ensure-notion-parent-page.sh -- establish ONE shared Notion parent page that the
# ZHC closeout always builds under, so the closeout never fails on
# "root-page-create-failed".
#
# ROOT CAUSE this addresses (confirmed fleet-wide):
#   The closeout uses an INTERNAL Notion integration token. Notion's API does NOT
#   let an internal integration create a workspace-ROOT page -- it can only create
#   pages UNDER a page that has been explicitly shared with the integration. A
#   client who never shared a page yields notionFailureReason
#   "root-page-create-failed: API returned no id". There is NO API bypass.
#
# WHAT THIS DOES (idempotent, safe to run any number of times):
#   1. If NOTION_CLOSEOUT_PARENT_PAGE_ID is already set (env or persisted) -> no-op.
#   2. Else, ask the Notion search API for ANY page already shared with the
#      integration. If one exists, PIN the first as NOTION_CLOSEOUT_PARENT_PAGE_ID
#      in the workspace .env so the closeout ALWAYS builds under that parent.
#   3. If ZERO pages are shared, emit a crisp ONE-TIME client instruction and a
#      machine marker, then exit NON-FATAL (rc 0) -- the closeout's own fail-clear
#      path re-checks on every run and auto-completes the instant a page is shared.
#
# This script NEVER fabricates a page and NEVER fails the onboarding run.
#
# Exit codes:
#   0  pinned a parent page  OR  already pinned  OR  no token (skipped, non-fatal)
#   0  no page shared yet (instruction emitted) -- intentionally non-fatal
#   2  hard error (bad jq / unwritable env file)  -- caller may warn, not abort

set -u

# ---- locate OpenClaw root + workspace .env ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[notion-parent] no OpenClaw root -- skipping (non-fatal)" >&2
  exit 0
fi
WS_DIR="$OC_ROOT/workspace"
ENV_FILE="${ZHC_NOTION_ENV_FILE:-$WS_DIR/.env}"
STATE_FILE="${ZHC_STATE_FILE:-$WS_DIR/.workforce-build-state.json}"
LOG_FILE="$WS_DIR/.zhc-closeout.log"
mkdir -p "$WS_DIR" 2>/dev/null || true

NOTION_VERSION="${NOTION_API_VERSION:-2022-06-28}"

log() {
  printf '%s [%-5s] step=notion-parent %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >> "$LOG_FILE" 2>/dev/null || true
  printf '%s [%-5s] step=notion-parent %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >&2
}

# The canonical client instruction -- kept byte-identical to create-notion-closeout.sh.
client_action_line() {
  printf '%s' "Share any one Notion page with your 'ZHC' integration (Notion -> open a page -> ... -> Connections -> add ZHC), or set NOTION_CLOSEOUT_PARENT_PAGE_ID to a page id you've shared. It auto-completes on the next run -- nothing else to do."
}

# ---- 0. token gate (skip cleanly when not configured) ----
if [[ -z "${NOTION_API_TOKEN:-}" ]]; then
  log "INFO" "NOTION_API_TOKEN not set -- skipping parent-page provisioning (non-fatal)"
  exit 0
fi

# ---- 1. already pinned? (env wins, then persisted .env) ----
existing_pin="${NOTION_CLOSEOUT_PARENT_PAGE_ID:-${NOTION_WORKSPACE_ROOT_ID:-}}"
if [[ -z "$existing_pin" && -f "$ENV_FILE" ]]; then
  existing_pin=$(grep -E "^[[:space:]]*(export[[:space:]]+)?NOTION_CLOSEOUT_PARENT_PAGE_ID=" "$ENV_FILE" 2>/dev/null \
    | tail -1 | sed -E "s/^[^=]*=//; s/^['\"]//; s/['\"][[:space:]]*$//")
fi
if [[ -n "$existing_pin" ]]; then
  log "INFO" "NOTION_CLOSEOUT_PARENT_PAGE_ID already set ($existing_pin) -- nothing to do"
  exit 0
fi

# ---- notion search helper (with light retry) ----
notion_search_any_page() {
  local attempt=0 out
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    out=$(curl -sS -X POST "https://api.notion.com/v1/search" \
      -H "Authorization: Bearer ${NOTION_API_TOKEN}" \
      -H "Notion-Version: $NOTION_VERSION" \
      -H "Content-Type: application/json" \
      -d '{"filter":{"value":"page","property":"object"},"page_size":5}' 2>/dev/null) && { echo "$out"; return 0; }
    sleep $((attempt))
  done
  echo "{}"
  return 0
}

# ---- 2. find any shared page ----
log "INFO" "searching for a page already shared with the ZHC integration..."
search_resp=$(notion_search_any_page)
parent_id=""
if printf '%s' "$search_resp" | jq -e . >/dev/null 2>&1; then
  # Skip Notion API error objects.
  obj=$(printf '%s' "$search_resp" | jq -r '.object // empty' 2>/dev/null)
  if [[ "$obj" == "error" ]]; then
    code=$(printf '%s' "$search_resp" | jq -r '.code // "unknown"' 2>/dev/null)
    msg=$(printf '%s' "$search_resp" | jq -r '.message // ""' 2>/dev/null)
    log "WARN" "Notion search returned API error ($code: $msg) -- treating as no shared page (will emit instruction)"
  else
    parent_id=$(printf '%s' "$search_resp" | jq -r '.results[0].id // empty' 2>/dev/null)
  fi
else
  log "WARN" "Notion search returned non-JSON -- treating as no shared page"
fi

# ---- 3a. found one: pin it ----
if [[ -n "$parent_id" ]]; then
  parent_title=$(printf '%s' "$search_resp" | jq -r \
    '.results[0].properties.title.title[0].plain_text // .results[0].properties.Name.title[0].plain_text // "(untitled)"' 2>/dev/null || echo "(untitled)")
  # Upsert NOTION_CLOSEOUT_PARENT_PAGE_ID into the workspace .env (idempotent).
  touch "$ENV_FILE" 2>/dev/null || { log "ERROR" "cannot write $ENV_FILE"; exit 2; }
  tmp=$(mktemp 2>/dev/null) || tmp="$ENV_FILE.tmp.$$"
  grep -vE "^[[:space:]]*(export[[:space:]]+)?NOTION_CLOSEOUT_PARENT_PAGE_ID=" "$ENV_FILE" 2>/dev/null > "$tmp" || true
  printf 'NOTION_CLOSEOUT_PARENT_PAGE_ID=%s\n' "$parent_id" >> "$tmp"
  mv "$tmp" "$ENV_FILE" 2>/dev/null || { log "ERROR" "cannot replace $ENV_FILE"; rm -f "$tmp"; exit 2; }
  log "INFO" "pinned NOTION_CLOSEOUT_PARENT_PAGE_ID=$parent_id (page: $parent_title) in $ENV_FILE -- closeout will always build under it"
  # Record in build-state when present (best-effort; closeout reads env, not this).
  if [[ -f "$STATE_FILE" ]]; then
    st=$(mktemp 2>/dev/null) || st="$STATE_FILE.tmp.$$"
    if jq ".notionClosoutParentPinnedAt = \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" | .notionCloseoutParentPageId = \"$parent_id\"" "$STATE_FILE" > "$st" 2>/dev/null; then
      mv "$st" "$STATE_FILE" 2>/dev/null || rm -f "$st"
    else
      rm -f "$st"
    fi
  fi
  echo "[notion-parent] PINNED parent page $parent_id ($parent_title)"
  exit 0
fi

# ---- 3b. nothing shared: emit ONE-TIME crisp client instruction (non-fatal) ----
action="$(client_action_line)"
log "WARN" "no Notion page is shared with the ZHC integration yet"
echo "" >&2
echo "  ============================================================" >&2
echo "  ONE-TIME NOTION SETUP (required for your closeout document)" >&2
echo "  ------------------------------------------------------------" >&2
echo "  $action" >&2
echo "  ============================================================" >&2
echo "" >&2
# Machine marker so the resume cron / status tooling can surface this.
if [[ -f "$STATE_FILE" ]]; then
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  st=$(mktemp 2>/dev/null) || st="$STATE_FILE.tmp.$$"
  if jq "
      .notionParentPagePending = true
      | .closeoutBlockers = (
          (.closeoutBlockers // [])
          | map(select(.class != \"notion-parent-page-pending\"))
          | . + [{\"class\":\"notion-parent-page-pending\",\"reason\":\"no Notion page shared with the ZHC integration yet\",\"since\":\"$ts\",\"escalatedAt\":null,\"cleared\":false,\"resumable\":true,\"actionable\":\"$action\"}]
        )
    " "$STATE_FILE" > "$st" 2>/dev/null; then
    mv "$st" "$STATE_FILE" 2>/dev/null || rm -f "$st"
  else
    rm -f "$st"
  fi
fi
echo "[notion-parent] PENDING: no shared page yet -- instruction emitted (auto-completes on next run)"
# Intentionally NON-FATAL: onboarding/closeout must still complete.
exit 0
