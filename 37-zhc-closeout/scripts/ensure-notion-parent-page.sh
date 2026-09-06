#!/usr/bin/env bash
# Validate and persist an explicitly selected client-owned parent. Never infer
# ownership from a workspace-wide search or switch to agency resources.
set -u
if [[ -d /data/.openclaw ]]; then OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then OC_ROOT="$HOME/.openclaw"
else echo '[notion-parent] PENDING: OpenClaw root unavailable' >&2; exit 0; fi
WS_DIR="$OC_ROOT/workspace"
ENV_FILE="${ZHC_NOTION_ENV_FILE:-$WS_DIR/.env}"
STATE_FILE="${ZHC_STATE_FILE:-$WS_DIR/.workforce-build-state.json}"
source "$(dirname "${BASH_SOURCE[0]}")/lib-closeout-state.sh" || exit 2
pending() {
  echo "[notion-parent] PENDING: $1. Share a page in this client's own Notion with the ZHC integration and explicitly set NOTION_CLOSEOUT_PARENT_PAGE_ID; the staged closeout resumes after verification." >&2
  if [[ -f "$STATE_FILE" ]]; then state_set '.notionParentPagePending = true' || exit 2; fi
  exit 0
}
[[ -f "$STATE_FILE" ]] || pending 'company state unavailable'
company_id=$(jq -r '.companyId // .company_id // empty' "$STATE_FILE")
[[ -n "$company_id" && -n "${NOTION_API_TOKEN:-}" ]] || pending 'company identity or client token unavailable'
[[ -z "${ZHC_AGENCY_NOTION_TOKEN:-}" || "$NOTION_API_TOKEN" != "$ZHC_AGENCY_NOTION_TOKEN" ]] || pending 'agency token is forbidden'
[[ "$(jq -r '.notionTier // 1' "$STATE_FILE")" != '2' ]] || pending 'agency closeout requires explicit client-owned migration'
parent_id="${NOTION_CLOSEOUT_PARENT_PAGE_ID:-${NOTION_WORKSPACE_ROOT_ID:-}}"
if [[ -z "$parent_id" && -f "$ENV_FILE" ]]; then
  parent_id=$(sed -nE 's/^[[:space:]]*(export[[:space:]]+)?NOTION_CLOSEOUT_PARENT_PAGE_ID=([a-zA-Z0-9-]+)[[:space:]]*$/\2/p' "$ENV_FILE" | tail -1)
fi
[[ "$parent_id" =~ ^[a-zA-Z0-9-]+$ ]] || pending 'explicit parent identity unavailable'
[[ -z "${ZHC_AGENCY_NOTION_PARENT_PAGE_ID:-}" || "${parent_id//-/}" != "${ZHC_AGENCY_NOTION_PARENT_PAGE_ID//-/}" ]] || pending 'agency parent is forbidden'
prior_company=$(jq -r '.notionOwnership.companyId // empty' "$STATE_FILE")
prior_parent=$(jq -r '.notionOwnership.parentPageId // empty' "$STATE_FILE")
[[ -z "$prior_company" || "$prior_company" == "$company_id" ]] || pending 'stored company ownership conflicts'
[[ -z "$prior_parent" || "${prior_parent//-/}" == "${parent_id//-/}" ]] || pending 'stored parent ownership conflicts'
cfg=$(mktemp) || exit 2
chmod 600 "$cfg"
trap 'rm -f "$cfg"' EXIT
printf 'header = "Authorization: Bearer %s"\nheader = "Notion-Version: %s"\n' "$NOTION_API_TOKEN" "${NOTION_API_VERSION:-2022-06-28}" > "$cfg"
proof=$(curl -sS --fail-with-body -K "$cfg" -X GET "https://api.notion.com/v1/pages/$parent_id") || pending 'configured parent readback failed'
printf '%s' "$proof" | jq -e --arg id "${parent_id//-/}" '.object == "page" and (.id|gsub("-";"")) == $id and .archived != true and .in_trash != true' >/dev/null 2>&1 || pending 'configured parent is missing, foreign or archived'
# Only after readback confirms that exact selection may it become a durable pin.
mkdir -p "$(dirname "$ENV_FILE")" || exit 2
tmp=$(mktemp "${ENV_FILE}.XXXXXX") || exit 2
if [[ -f "$ENV_FILE" ]]; then sed '/^[[:space:]]*\(export[[:space:]]\+\)\?NOTION_CLOSEOUT_PARENT_PAGE_ID=/d' "$ENV_FILE" > "$tmp"; fi
printf 'NOTION_CLOSEOUT_PARENT_PAGE_ID=%s\n' "$parent_id" >> "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE" || exit 2
ownership=$(jq -cn --arg company "$company_id" --arg parent "$parent_id" '{companyId:$company,parentPageId:$parent}')
state_set ".notionParentPagePending = false | .notionCloseoutParentPageId = \"$parent_id\" | .notionOwnership = ((.notionOwnership // {}) + $ownership)" || exit 2
echo '[notion-parent] VERIFIED: explicit client parent pinned'
