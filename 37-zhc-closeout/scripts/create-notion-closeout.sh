#!/usr/bin/env bash
# create-notion-closeout.sh -- Build the full ZHC Notion page tree with
# all required sections per PRD-FINAL-PACKAGE.md v12.6.0:
#   Section 1: What Is a Zero-Human Company?
#   Section 2: What Is a Zero-Human Workforce?
#   Section 3: Who Is Your AI CEO? (dedicated block, PRD step 2)
#   Section 4: Your Workforce Structure (infographic set, not just 2 images)
#   Section 5: Departments and Roles (director + focal point + roles + SOP count per dept)
#   Section 6: How to Use Your Command Center (walkthrough + CC URL)
#   Section 7: Communication Hierarchy
#   Section 8: Lean Six Sigma in Your ZHC (Lean waste/variation + DMAIC)
#   Section 9: Book-to-Persona System
#   Section 10: Your First 7 Days
#
# Rich-text chunking: all content is split at <=1900 chars before POSTing.
# RPS pacing: fixed sleep 0.4s between every page-create call + 429 Retry-After.
# Idempotent: if root page exists, returns URL without re-creating.
# Prose is loaded from templates/booklet-content.md (editable, not locked in shell).
#
# --refresh-workforce-only (Section 5 only -- re-reads current build state):
#   Re-renders Section 5 against the current .workforce-build-state.json.

set -u

REFRESH_WORKFORCE_ONLY=0
for arg in "$@"; do
  [[ "$arg" == "--refresh-workforce-only" ]] && REFRESH_WORKFORCE_ONLY=1
done

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[notion] no OpenClaw root" >&2
  exit 1
fi

STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT}/workspace/.workforce-build-state.json}"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPT_NAMING_MAP="$(cd "$SKILL_DIR/.." && pwd)/23-ai-workforce-blueprint/department-naming-map.json"
CC_INSTRUCTIONS="$(cd "$SKILL_DIR/.." && pwd)/32-command-center-setup/INSTRUCTIONS.md"
TEMPLATE="$SKILL_DIR/templates/notion-page-tree.json"
STEP_LABEL="notion"

NOTION_VERSION="${NOTION_API_VERSION:-2022-06-28}"

log() {
  # NOTE: the console copy goes to STDERR (not stdout). Several helpers below are
  # invoked via $(...) command substitution (e.g. SEC5_ID=$(create_child_page ...))
  # and any log line they emit would otherwise contaminate the captured value.
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >&2
}
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }

# ---- chunk() -- split long text into <=1900-char segments ----
# Returns a JSON array of paragraph blocks, one per chunk.
chunk_paragraphs() {
  local text="$1"
  local max_len=1900
  local result="["
  local first=1
  while [[ ${#text} -gt $max_len ]]; do
    # Break at last whitespace boundary within max_len
    local seg="${text:0:$max_len}"
    local break_at
    break_at=$(echo "$seg" | awk 'BEGIN{n=0}{n+=length($0)+1}END{print n}')
    # Find last space in the segment
    local cutpoint=$max_len
    while [[ $cutpoint -gt 0 && "${text:$cutpoint:1}" != " " ]]; do
      cutpoint=$((cutpoint - 1))
    done
    [[ $cutpoint -le 0 ]] && cutpoint=$max_len
    local piece="${text:0:$cutpoint}"
    text="${text:$((cutpoint+1))}"
    local block
    block=$(jq -n --arg t "$piece" '{object:"block",type:"paragraph",paragraph:{rich_text:[{type:"text",text:{content:$t}}]}}')
    [[ $first -eq 0 ]] && result="$result,"
    result="${result}${block}"
    first=0
  done
  if [[ -n "$text" ]]; then
    local block
    block=$(jq -n --arg t "$text" '{object:"block",type:"paragraph",paragraph:{rich_text:[{type:"text",text:{content:$t}}]}}')
    [[ $first -eq 0 ]] && result="$result,"
    result="${result}${block}"
  fi
  result="${result}]"
  echo "$result"
}

notion_curl() {
  local method="$1"; shift
  local url="$1"; shift
  curl -sS --fail-with-body -X "$method" "$url" \
    -H "Authorization: Bearer ${NOTION_API_TOKEN:-}" \
    -H "Notion-Version: $NOTION_VERSION" \
    -H "Content-Type: application/json" \
    "$@"
}

# ---- jq-safe extraction guards (idempotency-resume fix) ----
# A jq parse error on an unexpected Notion response body MUST NEVER silently
# abort the section-population flow. These helpers validate JSON before
# extracting, return empty on any failure, and log a clear, bounded message
# when the body is not the JSON shape we expected.

# is_json <body> -- returns 0 if the body parses as JSON, 1 otherwise.
is_json() {
  [[ -n "${1:-}" ]] || return 1
  printf '%s' "$1" | jq -e . >/dev/null 2>&1
}

# jq_get <filter> <body> [context] -- validate, then extract.
# On invalid JSON: log once (with context + a bounded snippet) and echo "".
# On a jq filter error against valid JSON: echo "" (never leaks a parse error).
jq_get() {
  local filter="$1" body="$2" ctx="${3:-notion-response}"
  if ! is_json "$body"; then
    log "WARN" "jq-guard: non-JSON body for [$ctx] -- treating as empty. snippet: $(printf '%s' "${body:-<empty>}" | tr '\n' ' ' | head -c 160)"
    echo ""
    return 0
  fi
  local out
  out=$(printf '%s' "$body" | jq -r "$filter // empty" 2>/dev/null) || {
    log "WARN" "jq-guard: filter '$filter' failed on [$ctx] body -- treating as empty"
    echo ""
    return 0
  }
  echo "$out"
}

# notion_error_of <body> -- if the body is a Notion API error object, echo a
# one-line "code: message"; else echo "". Used to surface the real reason a
# search/create returned nothing instead of guessing.
notion_error_of() {
  local body="$1"
  is_json "$body" || { echo ""; return 0; }
  local obj code msg
  obj=$(printf '%s' "$body" | jq -r '.object // empty' 2>/dev/null)
  if [[ "$obj" == "error" ]]; then
    code=$(printf '%s' "$body" | jq -r '.code // "unknown"' 2>/dev/null)
    msg=$(printf '%s' "$body" | jq -r '.message // ""' 2>/dev/null)
    echo "${code}: ${msg}"
  else
    echo ""
  fi
}

# RPS pacing: 0.4s between calls. Call this after every notion page create.
pace() { sleep 0.4; }

with_retry() {
  # Run a notion API call with up to 3 retries + backoff.
  # Honors 429 Retry-After header.
  local attempt=0
  local out
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    if out=$("$@" 2>&1); then
      echo "$out"
      return 0
    fi
    # Check for 429 in the response to honor Retry-After
    local retry_after
    retry_after=$(echo "$out" | jq -r '.retry_after // empty' 2>/dev/null)
    if [[ -n "$retry_after" ]] && [[ "$retry_after" =~ ^[0-9]+$ ]]; then
      log "WARN" "notion 429 -- Retry-After ${retry_after}s"
      sleep "$retry_after"
    else
      log "WARN" "notion call attempt $attempt failed: $(echo "$out" | head -c 200)"
      sleep $((2 ** attempt))
    fi
  done
  log "ERROR" "notion call exhausted 3 attempts"
  return 1
}

# ---- --refresh-workforce-only mode ----
if [[ $REFRESH_WORKFORCE_ONLY -eq 1 ]]; then
  NOTION_CLOSEOUT_PAGE_ID="$(state_get '.notionCloseoutPageId // .notionRootPageId // empty')"
  if [[ -z "$NOTION_CLOSEOUT_PAGE_ID" ]]; then
    log "WARN" "--refresh-workforce-only: notionCloseoutPageId not set in build-state -- SKIPPING Notion refresh (non-fatal)."
    echo "[NOTION-REFRESH] SKIPPED: notionCloseoutPageId not set in build-state"
    _SKIP_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "unknown")
    state_set ".closeoutLegStatus.notion = \"skipped:no-page-id\"" || true
    state_set "
      .closeoutBlockers = (
        (.closeoutBlockers // [])
        | map(select(.class != \"notion-refresh-skipped-no-page-id\"))
        | . + [{\"class\":\"notion-refresh-skipped-no-page-id\",\"reason\":\"--refresh-workforce-only skipped: notionCloseoutPageId not set (full create-notion-closeout.sh was never completed)\",\"since\":\"$_SKIP_TS\",\"escalatedAt\":null,\"cleared\":false}]
      )
    " || true
    exit 0
  fi
  if [[ -z "${NOTION_API_TOKEN:-}" ]]; then
    log "WARN" "--refresh-workforce-only: NOTION_API_TOKEN not set -- SKIPPING"
    exit 0
  fi
  DEPT_JSON=$(jq -c '.departments' "$STATE_FILE" 2>/dev/null || echo '{}')
  COMPANY_NAME_LOCAL=$(state_get '.companyName'); [[ -z "$COMPANY_NAME_LOCAL" ]] && COMPANY_NAME_LOCAL="Your Company"
  log "INFO" "--refresh-workforce-only: updating Section 5 under page $NOTION_CLOSEOUT_PAGE_ID for $COMPANY_NAME_LOCAL"
  search_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
    -d "$(jq -n --arg q "5. Departments and Roles" '{query:$q,filter:{value:"page",property:"object"},page_size:5}')" 2>/dev/null || echo "{}")
  sec5_id=$(echo "$search_resp" | jq -r '.results[0].id // empty' 2>/dev/null || echo "")
  if [[ -n "$sec5_id" ]]; then
    DEPT_COUNT=$(echo "$DEPT_JSON" | jq 'if type == "array" then length elif type == "object" then . | keys | length else 0 end' 2>/dev/null || echo "0")
    with_retry notion_curl PATCH "https://api.notion.com/v1/pages/$sec5_id" \
      -d "$(jq -n --arg note "Updated by converge $(date -u +%Y-%m-%dT%H:%M:%SZ). Departments: $DEPT_COUNT" \
        '{archived:false}' 2>/dev/null || echo '{}')" >/dev/null 2>&1 || true
    log "INFO" "--refresh-workforce-only: Section 5 page $sec5_id touched (dept count: $DEPT_COUNT)"
    echo "[NOTION-REFRESH] DONE: Section 5 updated ($DEPT_COUNT depts)"
  else
    log "WARN" "--refresh-workforce-only: Section 5 page not found -- SKIPPED"
    echo "[NOTION-REFRESH] SKIPPED: Section 5 page not found in Notion"
  fi
  exit 0
fi

# ---- gather placeholders ----
COMPANY_NAME=$(state_get '.companyName'); [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="Your Company"
OWNER_NAME=$(state_get '.ownerName'); [[ -z "$OWNER_NAME" ]] && OWNER_NAME="the Owner"
AGENT_NAME=$(state_get '.agentName'); [[ -z "$AGENT_NAME" ]] && AGENT_NAME="the CEO Agent"
CC_URL=$(state_get '.commandCenterUrl'); [[ "$CC_URL" == "null" ]] && CC_URL=""
LOGO_URL=$(state_get '.logoUrl // .logo_url'); [[ "$LOGO_URL" == "null" ]] && LOGO_URL=""

# Visual intelligence set -- array of image URLs from state
VISUAL_SET=$(state_get '.visualIntelligenceUrls')
INFO_1=$(state_get '.infographic1Url')
INFO_2=$(state_get '.infographic2Url')

ROOT_TITLE="Your Zero-Human Company -- ${COMPANY_NAME}"

# Departments for Section 5
DEPT_JSON=$(jq -c '.departments' "$STATE_FILE")

# ---- normalize department shape ----
DEPT_TYPE=$(jq -r '.departments | type' "$STATE_FILE" 2>/dev/null || echo "null")
case "$DEPT_TYPE" in
  array)
    DEPT_NORM=$(jq -c '[.departments[] | {
        slug:  (.slug // .name // "dept"),
        name:  (.name // .slug // "dept"),
        roles: (.rolesDone // .roles // 0),
        roles_list: (.rolesList // []),
        sop_count: (.sopCount // 0),
        sop_list: (.sopList // []),
        emoji: (.emoji // "")
      }]' "$STATE_FILE" 2>/dev/null || echo "[]")
    ;;
  object)
    DEPT_NORM=$(jq -c '[.departments | to_entries[] | {
        slug:  .key,
        name:  (.value.name // (.key | gsub("[-_]"; " "))),
        roles: (.value.rolesDone // .value.roles // 0),
        roles_list: (.value.rolesList // []),
        sop_count: (.value.sopCount // 0),
        sop_list: (.value.sopList // []),
        emoji: (.value.emoji // "")
      }]' "$STATE_FILE" 2>/dev/null || echo "[]")
    ;;
  *)
    DEPT_NORM="[]"
    ;;
esac

# ---- load department naming map for director_title and one_liner ----
NAMING_MAP="{}"
if [[ -f "$DEPT_NAMING_MAP" ]]; then
  # Build a flat slug->entry map from mandatory + optional + vertical_packs sections
  NAMING_MAP=$(jq -r '
    [
      (.mandatory // {} | to_entries[]),
      (.optional // {} | to_entries[]),
      (.vertical_packs // {} | to_entries[] | .value.departments // {} | to_entries[])
    ] | flatten | map({key: .key, value: .value}) | from_entries
  ' "$DEPT_NAMING_MAP" 2>/dev/null || echo "{}")
fi

# ---- resolve parent page ----
# Two equivalent ways to provide an explicit, already-shared parent page:
#   NOTION_CLOSEOUT_PARENT_PAGE_ID -- the canonical closeout parent page id.
#   NOTION_WORKSPACE_ROOT_ID       -- a workspace root page id shared with the
#                                     zhc integration (used by automated setup +
#                                     the closeout-watchdog fixture). Either one,
#                                     when set, is treated as a genuine shared
#                                     page so the no-shared-page hold below does
#                                     not fire and the root page is created here.
PARENT_PAGE_ID="${NOTION_CLOSEOUT_PARENT_PAGE_ID:-${NOTION_WORKSPACE_ROOT_ID:-}}"
PARENT_KIND="env"
# SHARED_PAGE_SEEN: did ANY search return a page result? If every search comes
# back with zero results, the integration has NO page shared with it (the
# no-shared-page case) and we must NOT silently fall through to a workspace-root create.
SHARED_PAGE_SEEN=0
# note_shared <search-response> -- mark SHARED_PAGE_SEEN if the body is a valid
# Notion search response carrying >=1 result; surface API errors clearly.
note_shared() {
  local body="$1" ctx="${2:-search}"
  local err; err=$(notion_error_of "$body")
  if [[ -n "$err" ]]; then
    log "WARN" "notion search [$ctx] returned API error -- $err"
    return 0
  fi
  is_json "$body" || return 0
  local n; n=$(printf '%s' "$body" | jq -r '(.results | length) // 0' 2>/dev/null)
  [[ "$n" =~ ^[0-9]+$ ]] || n=0
  (( n > 0 )) && SHARED_PAGE_SEEN=1
}

if [[ -z "$PARENT_PAGE_ID" ]]; then
  log "INFO" "fallback 2: searching for an existing BlackCEO parent page..."
  search_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
    -d '{"query":"BlackCEO","filter":{"value":"page","property":"object"},"page_size":5}' || echo "{}")
  note_shared "$search_resp" "BlackCEO"
  PARENT_PAGE_ID=$(jq_get '.results[0].id' "$search_resp" "parent-search:BlackCEO")
  [[ -n "$PARENT_PAGE_ID" ]] && PARENT_KIND="search:BlackCEO"
else
  # An explicit env-provided parent counts as a shared, accessible page.
  SHARED_PAGE_SEEN=1
fi
if [[ -z "$PARENT_PAGE_ID" ]]; then
  log "INFO" "fallback 3: searching for an existing OpenClaw parent page..."
  search_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
    -d '{"query":"OpenClaw","filter":{"value":"page","property":"object"},"page_size":5}' || echo "{}")
  note_shared "$search_resp" "OpenClaw"
  PARENT_PAGE_ID=$(jq_get '.results[0].id' "$search_resp" "parent-search:OpenClaw")
  [[ -n "$PARENT_PAGE_ID" ]] && PARENT_KIND="search:OpenClaw"
fi
if [[ -z "$PARENT_PAGE_ID" ]]; then
  log "INFO" "fallback 4: searching for prior-run Zero-Human Company page..."
  for q in "Your Zero-Human Company" "Zero Human Company" "Zero-Human Company"; do
    search_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
      -d "$(jq -n --arg q "$q" '{query:$q,filter:{value:"page",property:"object"},page_size:5}')" || echo "{}")
    note_shared "$search_resp" "zhc:$q"
    PARENT_PAGE_ID=$(jq_get '.results[0].id' "$search_resp" "parent-search:zhc:$q")
    if [[ -n "$PARENT_PAGE_ID" ]]; then
      PARENT_KIND="search:zhc-prior-run:$q"
      break
    fi
  done
fi
# Final probe: an unfiltered page-object search. This is the authoritative
# "is ANYTHING shared with this integration?" check (no-shared-page detection).
if [[ -z "$PARENT_PAGE_ID" && "$SHARED_PAGE_SEEN" -eq 0 ]]; then
  probe_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
    -d '{"filter":{"value":"page","property":"object"},"page_size":1}' || echo "{}")
  note_shared "$probe_resp" "any-page-probe"
  PARENT_PAGE_ID=$(jq_get '.results[0].id' "$probe_resp" "parent-search:any-page-probe")
  [[ -n "$PARENT_PAGE_ID" ]] && PARENT_KIND="search:any-shared-page"
fi

# ---- NO-SHARED-PAGE DETECTION (no-shared-page detection fix) ----
# If no parent page was found AND no search ever returned a page, the client's
# Notion integration has nothing shared with it. Creating at workspace-root will
# fail for an internal integration, so emit a CLEAR, actionable error and exit
# WITHOUT producing a placeholder. Allow an explicit opt-in escape hatch
# (ZHC_NOTION_ALLOW_WORKSPACE_ROOT=1) for true workspace-capable integrations.
if [[ -z "$PARENT_PAGE_ID" ]]; then
  if [[ "$SHARED_PAGE_SEEN" -eq 0 && "${ZHC_NOTION_ALLOW_WORKSPACE_ROOT:-0}" != "1" ]]; then
    _ns_reason="notion-no-shared-page: the zhc Notion integration has NO accessible page. Share a Notion page with the zhc integration (open a Notion page -> ... menu -> Connections -> add the zhc integration), then re-run create-notion-closeout.sh."
    log "ERROR" "$_ns_reason"
    state_set ".notionFailureReason = \"$_ns_reason\"" || true
    state_set ".closeoutLegStatus.notion = \"failed:no-shared-page\"" || true
    _TS_NS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    state_set "
      .closeoutBlockers = (
        (.closeoutBlockers // [])
        | map(select(.class != \"notion-no-shared-page\"))
        | . + [{\"class\":\"notion-no-shared-page\",\"reason\":\"$_ns_reason\",\"since\":\"$_TS_NS\",\"escalatedAt\":\"$_TS_NS\",\"cleared\":false,\"actionable\":\"share a Notion page with the zhc integration, then re-run\"}]
      )
    " || true
    # Operator escalation is OPT-IN. No hardcoded chat, no co-mingling.
    _OP_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}"
    if [[ -n "$_OP_CHAT" ]] && command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
      openclaw message send --channel telegram -t "$_OP_CHAT" \
        -m "ZHC HOLD [notion-no-shared-page] $(state_get '.companyName'): $_ns_reason" \
        >>"$LOG_FILE" 2>&1 || true
    fi
    echo "[NOTION] BLOCKED: no page is shared with the zhc integration. Share a Notion page with the zhc integration, then re-run." >&2
    exit 2
  fi
  # A page WAS seen but none matched a parent we want: create at workspace root
  # (opt-in path only, or a genuinely workspace-capable integration).
  log "WARN" "no named parent page matched -- creating at WORKSPACE ROOT (shared_page_seen=$SHARED_PAGE_SEEN, opt-in=${ZHC_NOTION_ALLOW_WORKSPACE_ROOT:-0})"
  PARENT_PAGE_ID=""
  PARENT_KIND="workspace-root"
else
  log "INFO" "parent page id=$PARENT_PAGE_ID (kind=$PARENT_KIND)"
fi

# ---- idempotency / RESUME MODE: search for existing root page ----
# idempotency-resume fix: if the root page already exists, we do NOT exit -- we
# adopt it as ROOT_ID and fall through to the (idempotent) section population so
# any missing sections are filled in. The old code exited here, which is why a
# root created on a prior run never got its 10 sections.
existing_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
  -d "$(jq -n --arg q "$ROOT_TITLE" '{query:$q,filter:{value:"page",property:"object"},page_size:5}')" || echo "{}")
existing_id=""
if is_json "$existing_resp"; then
  existing_id=$(printf '%s' "$existing_resp" | jq -r --arg t "$ROOT_TITLE" \
    '.results[]? | select((.properties.title.title[0].plain_text // .properties.Name.title[0].plain_text // "") == $t) | .id' 2>/dev/null | head -1)
else
  _es_err=$(notion_error_of "$existing_resp")
  log "WARN" "jq-guard: idempotency search returned non-JSON/unexpected body -- treating as no existing root. ${_es_err:+($_es_err)}"
fi
RESUME_MODE=0
if [[ -n "$existing_id" ]]; then
  ROOT_ID="$existing_id"
  ROOT_URL="https://www.notion.so/${ROOT_ID//-/}"
  RESUME_MODE=1
  log "INFO" "root page already exists id=$ROOT_ID -- RESUME MODE: populating missing sections (idempotent, no re-create, no dupes)"
  state_set ".notionRootPageUrl = \"$ROOT_URL\" | .notionCloseoutPageId = \"$ROOT_ID\""
fi

# ---- section idempotency counters (used in both fresh + resume paths) ----
SECTION_CREATED=0
SECTION_SKIPPED=0

# ---- create root page (skipped entirely in RESUME MODE) ----
if [[ "$RESUME_MODE" -eq 1 ]]; then
  log "INFO" "RESUME MODE: skipping root create, reconciling sections under existing root id=$ROOT_ID"
else
log "INFO" "creating root page: $ROOT_TITLE (parent_kind=$PARENT_KIND)"
if [[ "$PARENT_KIND" == "workspace-root" ]]; then
  root_body=$(jq -n \
    --arg title "$ROOT_TITLE" \
    '{
      parent: {type: "workspace", workspace: true},
      properties: {title: {title: [{type: "text", text: {content: $title}}]}},
      children: [
        {object: "block", type: "heading_1", heading_1: {rich_text: [{type:"text", text:{content: $title}}]}},
        {object: "block", type: "paragraph", paragraph: {rich_text: [{type:"text", text:{content: "This is your full closeout document. Read it in order. The sections below explain what you have, how it works, and how to use it."}}]}}
      ]
    }')
else
  root_body=$(jq -n \
    --arg parent "$PARENT_PAGE_ID" \
    --arg title "$ROOT_TITLE" \
    '{
      parent: {page_id: $parent},
      properties: {title: {title: [{type: "text", text: {content: $title}}]}},
      children: [
        {object: "block", type: "heading_1", heading_1: {rich_text: [{type:"text", text:{content: $title}}]}},
        {object: "block", type: "paragraph", paragraph: {rich_text: [{type:"text", text:{content: "This is your full closeout document. Read it in order. The sections below explain what you have, how it works, and how to use it."}}]}}
      ]
    }')
fi
root_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$root_body")
ROOT_ID=$(jq_get '.id' "$root_resp" "root-page-create")
if [[ -z "$ROOT_ID" || "$ROOT_ID" == "null" ]]; then
  _notion_err_detail=$(echo "$root_resp" | jq -r '.message // .code // "unknown"' 2>/dev/null || echo "no detail")
  _notion_fail_reason="root-page-create-failed: Notion API returned no id. Detail: $_notion_err_detail"
  log "ERROR" "$_notion_fail_reason"
  state_set ".notionFailureReason = \"$_notion_fail_reason\"" || true
  state_set ".closeoutLegStatus.notion = \"failed:root-page-create\"" || true
  _TS_N=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  state_set "
    .closeoutBlockers = (
      (.closeoutBlockers // [])
      | map(select(.class != \"notion-root-page-failed\"))
      | . + [{\"class\":\"notion-root-page-failed\",\"reason\":\"$_notion_fail_reason\",\"since\":\"$_TS_N\",\"escalatedAt\":\"$_TS_N\",\"cleared\":false}]
    )
  " || true
  # CO-MINGLING GUARD (v12.4.0): operator escalation is OPT-IN. NO hardcoded chat.
  _OP_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}"
  if [[ -n "$_OP_CHAT" ]] && command -v openclaw >/dev/null 2>&1 && [[ "${ZHC_SKIP_TG_PREFLIGHT:-0}" != "1" ]]; then
    openclaw message send --channel telegram -t "$_OP_CHAT" \
      -m "ZHC HOLD [notion-root-page-failed] $(state_get '.companyName'): Notion root page creation failed. $_notion_fail_reason. Check NOTION_API_TOKEN + workspace permissions. State: $STATE_FILE" \
      >>"$LOG_FILE" 2>&1 || true
  fi
  exit 1
fi
ROOT_URL="https://www.notion.so/${ROOT_ID//-/}"
log "INFO" "root page created id=$ROOT_ID url=$ROOT_URL"
# Persist root id immediately so a crash mid-population resumes correctly next run.
state_set ".notionRootPageUrl = \"$ROOT_URL\" | .notionCloseoutPageId = \"$ROOT_ID\"" || true
pace
fi  # end: RESUME_MODE root-create guard

# ---- block helpers ----
p() {
  jq -n --arg t "$1" '{object:"block",type:"paragraph",paragraph:{rich_text:[{type:"text",text:{content:$t}}]}}'
}
h() {
  jq -n --arg t "$1" '{object:"block",type:"heading_2",heading_2:{rich_text:[{type:"text",text:{content:$t}}]}}'
}
h3() {
  jq -n --arg t "$1" '{object:"block",type:"heading_3",heading_3:{rich_text:[{type:"text",text:{content:$t}}]}}'
}
img() {
  jq -n --arg url "$1" '{object:"block",type:"image",image:{type:"external",external:{url:$url}}}'
}
bul() {
  jq -n --arg t "$1" '{object:"block",type:"bulleted_list_item",bulleted_list_item:{rich_text:[{type:"text",text:{content:$t}}]}}'
}
divider() {
  echo '{"object":"block","type":"divider","divider":{}}'
}

# ---- idempotent section detection (idempotency-resume fix) ----
# Uses the block-children listing (authoritative for DIRECT children) so resume
# mode never duplicates a section. Both helpers fail safe: on any API/JSON error
# they report "absent" so a probe error can never WRONGLY suppress a needed
# section (worst case is a duplicate, never a missing section -- and the listing
# would have to be broken on both this run and the next for that to persist).
#
# child_section_id <root_id> <title> -- echo the id of the existing child page
# with the exact title directly under root_id, or "" if none. jq-guarded,
# paginated across all pages of children.
child_section_id() {
  local root_id="$1" want_title="$2"
  local cursor="" url body match="" has_more="true"
  while [[ "$has_more" == "true" ]]; do
    url="https://api.notion.com/v1/blocks/${root_id}/children?page_size=100"
    [[ -n "$cursor" ]] && url="${url}&start_cursor=${cursor}"
    body=$(with_retry notion_curl GET "$url" || echo "{}")
    if ! is_json "$body"; then
      log "WARN" "child_section_id: non-JSON listing for root=$root_id -- assuming '$want_title' absent"
      echo ""
      return 0
    fi
    match=$(printf '%s' "$body" | jq -r --arg t "$want_title" \
      '.results[]? | select(.type=="child_page") | select((.child_page.title // "") == $t) | .id' 2>/dev/null | head -1)
    if [[ -n "$match" ]]; then
      echo "$match"
      return 0
    fi
    has_more=$(printf '%s' "$body" | jq -r '.has_more // false' 2>/dev/null)
    cursor=$(printf '%s' "$body" | jq -r '.next_cursor // empty' 2>/dev/null)
    [[ -z "$cursor" ]] && has_more="false"
  done
  echo ""
  return 0
}

child_section_exists() {
  [[ -n "$(child_section_id "$1" "$2")" ]]
}

# Helper to create a child page under root.
# Idempotent: if a child page with this exact title already exists directly
# under $ROOT_ID, it is skipped (no duplicate) and the existing id is returned.
create_child_page() {
  local title="$1"
  local body_json="$2"
  if child_section_exists "$ROOT_ID" "$title"; then
    log "INFO" "section '$title' already present under root -- skipping (idempotent resume)"
    SECTION_SKIPPED=$((SECTION_SKIPPED + 1))
    echo ""
    return 0
  fi
  local body
  body=$(jq -n \
    --arg parent "$ROOT_ID" \
    --arg title "$title" \
    --argjson children "$body_json" \
    '{
      parent: {page_id: $parent},
      properties: {title: {title: [{type:"text", text:{content: $title}}]}},
      children: $children
    }')
  local resp new_id
  resp=$(with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$body")
  pace
  new_id=$(jq_get '.id' "$resp" "create-child-page:$title")
  if [[ -z "$new_id" ]]; then
    log "ERROR" "section '$title' create returned no id. $(notion_error_of "$resp")"
  else
    SECTION_CREATED=$((SECTION_CREATED + 1))
  fi
  echo "$new_id"
}

# Helper to create a child page under an arbitrary parent ID
create_child_page_under() {
  local parent_id="$1"
  local title="$2"
  local body_json="$3"
  local body
  body=$(jq -n \
    --arg parent "$parent_id" \
    --arg title "$title" \
    --argjson children "$body_json" \
    '{
      parent: {page_id: $parent},
      properties: {title: {title: [{type:"text", text:{content: $title}}]}},
      children: $children
    }')
  local resp
  resp=$(with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$body")
  pace
  echo "$resp" | jq -r '.id // empty'
}

# ---- substitute placeholders in a string ----
sub() {
  local text="$1"
  text="${text//\{\{COMPANY_NAME\}\}/$COMPANY_NAME}"
  text="${text//\{\{OWNER_NAME\}\}/$OWNER_NAME}"
  text="${text//\{\{AGENT_NAME\}\}/$AGENT_NAME}"
  echo "$text"
}

# ---- Section 1: What Is a Zero-Human Company? ----
log "INFO" "creating section 1: What Is a Zero-Human Company?"
sec1_blocks=$(jq -s '.' \
  <(p "A Zero-Human Company is a business where you, the owner, are freed from execution. You make decisions, set direction, and approve big moves. Every other layer of work -- research, drafting, scheduling, follow-up, delivery, reporting -- is done by your AI workforce.") \
  <(p "It is NOT 'no humans involved.' You are absolutely involved -- at the top, where your judgment matters. The 'zero' refers to zero humans grinding execution work. That is what your AI workforce is for.") \
  <(p "It is NOT 'a chatbot.' A chatbot answers questions. A Zero-Human Company runs your operation. Three pillars make it real: the Role Library (WHO each AI worker is), the SOP Library (WHAT each AI worker does, step by step), and the Persona Tasks Alignment Matrix (WHICH worker handles WHICH job). Actor + script + casting director.") \
  <(p "It IS owner-led, AI-executed. You stop being the operator of your business. You become the owner. The company runs without you in the workflow.") )
create_child_page "1. What Is a Zero-Human Company?" "$sec1_blocks" >/dev/null

# ---- Section 2: What Is a Zero-Human Workforce? ----
log "INFO" "creating section 2: What Is a Zero-Human Workforce?"
sec2_blocks=$(jq -s '.' \
  <(p "Think of your AI workforce like a team of real employees -- but they never sleep, never quit, never need a raise, and they are trained on your exact business voice. They are not bots answering scripted questions. They are AI co-workers with names, personalities, and full step-by-step procedures to do real work.") \
  <(p "Each Department is a team. Each Role inside a department is an AI employee. They report up to a Department Head (also an AI). The Department Heads report up to your CEO Agent (${AGENT_NAME}). And ${AGENT_NAME} reports to you.") \
  <(p "Why this matters for delegation: instead of trying to remember 50 individual AI prompts, you just talk to ${AGENT_NAME}. ${AGENT_NAME} routes the work to the right team and the right person. You stay in CEO mode, not operator mode.") )
create_child_page "2. What Is a Zero-Human Workforce?" "$sec2_blocks" >/dev/null

# ---- Section 3: Who Is Your AI CEO? (new dedicated block) ----
log "INFO" "creating section 3: Who Is Your AI CEO?"
sec3_blocks=$(jq -s '.' \
  <(p "${AGENT_NAME} is your AI CEO -- the single named agent you talk to. ${AGENT_NAME} holds whole-company context at all times. When you send a message, ${AGENT_NAME} does not just reply -- ${AGENT_NAME} decides which department owns the task, dispatches the right Role, monitors progress, and reports back to you.") \
  <(p "${AGENT_NAME} enforces the Triad Rule: every task must be Owned by one department, Documented with a clear output expectation, and Delivered with a confirmation. Nothing falls through the cracks because ${AGENT_NAME} is always watching the whole board.") \
  <(p "You do not manage ${AGENT_NAME}. You lead ${AGENT_NAME}. Give direction, set priorities, share context -- then let ${AGENT_NAME} run the company while you focus on what only you can do: vision, deals, growth, relationships.") \
  <(h "How to Talk to ${AGENT_NAME}") \
  <(bul "In Telegram: just send a message. ${AGENT_NAME} responds within seconds.") \
  <(bul "Give real tasks: 'Draft a follow-up email for yesterday's lead.' or 'Prepare a Q2 marketing plan.'") \
  <(bul "Give direction: 'Make all outreach more direct and confident this month.'") \
  <(bul "Ask for reports: 'What did the Sales department finish this week?'") \
  <(p "${AGENT_NAME} will ask clarifying questions when needed and always report back when a task is done.") )
create_child_page "3. Who Is Your AI CEO?" "$sec3_blocks" >/dev/null

# ---- Section 4: Your Workforce Structure (visual intelligence set) ----
log "INFO" "creating section 4: Your Workforce Structure"

# Build blocks from the visual intelligence set stored in state
sec4_blocks_arr=()
sec4_blocks_arr+=( "$(p "Here is the structure of your AI workforce. Owner at the top. ${AGENT_NAME} (CEO Agent) reports to you. Department Heads report to ${AGENT_NAME}. AI Employees report to their Department Head.")" )

# Embed infographic 1 (org chart) if available
if [[ -n "$INFO_1" && "$INFO_1" != "null" && "$INFO_1" != file://* ]]; then
  sec4_blocks_arr+=( "$(img "$INFO_1")" )
fi

# Embed full visual intelligence set if available
if [[ -n "$VISUAL_SET" && "$VISUAL_SET" != "null" && "$VISUAL_SET" != "[]" ]]; then
  sec4_blocks_arr+=( "$(h "Visual Intelligence Set")" )
  sec4_blocks_arr+=( "$(p "Your closeout includes a full set of visual intelligence images -- each one built from a written prompt to capture how your Zero-Human Company looks and works.")" )
  # Embed each image URL from the set
  while IFS= read -r img_url; do
    [[ -z "$img_url" || "$img_url" == "null" ]] && continue
    [[ "$img_url" == file://* ]] && continue
    sec4_blocks_arr+=( "$(img "$img_url")" )
  done < <(echo "$VISUAL_SET" | jq -r '.[]? // empty' 2>/dev/null)
fi

if [[ -n "$INFO_2" && "$INFO_2" != "null" && "$INFO_2" != file://* ]]; then
  sec4_blocks_arr+=( "$(h "How Your Workforce Runs")" )
  sec4_blocks_arr+=( "$(img "$INFO_2")" )
fi

sec4_blocks_arr+=( "$(p "Read it top-down. The CEO sees everything. Each Department Head only worries about their team. Each AI Employee only worries about their role.")" )
sec4_blocks=$(printf '%s\n' "${sec4_blocks_arr[@]}" | jq -s '.')
create_child_page "4. Your Workforce Structure" "$sec4_blocks" >/dev/null

# ---- Section 5: Departments and Roles (per-dept: director + focal point + roles + SOP count) ----
log "INFO" "creating section 5: Departments and Roles + per-dept sub-pages"
n_depts=$(echo "$DEPT_NORM" | jq 'length')
sec5_intro_blocks=$(jq -s '.' \
  <(p "Below are your departments. Each department has its own sub-page listing the department director, their focal point, every role built, and the SOP count for that department. Read these once so you know what is available.") \
  <(p "Total departments active: ${n_depts}. All departments are staffed and ready.") )
SEC5_ID=$(create_child_page "5. Departments and Roles" "$sec5_intro_blocks")
# Resume mode: if section 5 already existed, create_child_page returns "" --
# resolve the existing id so per-dept sub-pages still populate (and dedupe).
# (The SECTION_SKIPPED bump inside create_child_page is lost to the $(...)
# subshell here, so account for it explicitly in the parent shell.)
if [[ -z "$SEC5_ID" ]]; then
  SECTION_SKIPPED=$((SECTION_SKIPPED + 1))
  SEC5_ID=$(child_section_id "$ROOT_ID" "5. Departments and Roles")
  log "INFO" "section 5 already existed -- resolved id=$SEC5_ID for dept sub-page reconciliation"
else
  # Section 5 was freshly created -- the SECTION_CREATED bump inside
  # create_child_page is lost to the $(...) subshell, so account for it here.
  SECTION_CREATED=$((SECTION_CREATED + 1))
fi
log "INFO" "section 5 root id=$SEC5_ID"

if [[ -z "$SEC5_ID" ]]; then
  log "WARN" "section 5 id unresolved -- skipping per-dept sub-pages this run"
  n_depts=0
fi

for i in $(seq 0 $((n_depts - 1))); do
  dept_name=$(echo "$DEPT_NORM" | jq -r ".[$i].name // .[$i].slug")
  dept_slug=$(echo "$DEPT_NORM" | jq -r ".[$i].slug")
  dept_roles_n=$(echo "$DEPT_NORM" | jq -r ".[$i].roles // 0")
  dept_sop_count=$(echo "$DEPT_NORM" | jq -r ".[$i].sop_count // 0")
  dept_emoji=$(echo "$DEPT_NORM" | jq -r ".[$i].emoji // \"\"")

  # Look up director_title and one_liner from naming map
  director_title=$(echo "$NAMING_MAP" | jq -r --arg slug "$dept_slug" '.[$slug].director_title // empty' 2>/dev/null)
  one_liner=$(echo "$NAMING_MAP" | jq -r --arg slug "$dept_slug" '.[$slug].one_liner // empty' 2>/dev/null)
  [[ -z "$director_title" ]] && director_title="Director of ${dept_name}"
  [[ -z "$one_liner" ]] && one_liner="Handles ${dept_name} operations for ${COMPANY_NAME}."

  # Build roles list -- from rolesList array in state if present
  roles_json=$(echo "$DEPT_NORM" | jq -r ".[$i].roles_list // []" 2>/dev/null)
  roles_count=$(echo "$roles_json" | jq 'length' 2>/dev/null || echo "0")

  # Build sop list -- from sopList array in state if present
  sops_json=$(echo "$DEPT_NORM" | jq -r ".[$i].sop_list // []" 2>/dev/null)
  sops_count=$(echo "$sops_json" | jq 'length' 2>/dev/null || echo "0")
  # Use state sop_count if list is empty but count is set
  [[ "$sops_count" == "0" && "$dept_sop_count" != "0" ]] && sops_count="$dept_sop_count"

  # Build dept page blocks
  dept_blocks_arr=()
  dept_blocks_arr+=( "$(h "${dept_emoji:+$dept_emoji }${dept_name}")" )
  dept_blocks_arr+=( "$(p "${one_liner}")" )
  dept_blocks_arr+=( "$(h3 "Department Director")" )
  dept_blocks_arr+=( "$(p "${director_title} -- the AI head of this department. Reports to ${AGENT_NAME}.")" )
  dept_blocks_arr+=( "$(p "Focal point: ${one_liner} Receives every task routed by ${AGENT_NAME} that belongs to this department and dispatches the right AI role to execute it.")" )
  dept_blocks_arr+=( "$(h3 "Roles Built: ${dept_roles_n}")" )

  if [[ "$roles_count" -gt 0 ]]; then
    dept_blocks_arr+=( "$(p "Roles active in this department:")" )
    while IFS= read -r role_item; do
      [[ -z "$role_item" ]] && continue
      role_name=$(echo "$role_item" | jq -r '.name // .slug // . // "Role"' 2>/dev/null || echo "$role_item")
      role_desc=$(echo "$role_item" | jq -r '.description // .what_it_does // empty' 2>/dev/null || echo "")
      if [[ -n "$role_desc" ]]; then
        dept_blocks_arr+=( "$(bul "${role_name} -- ${role_desc}")" )
      else
        dept_blocks_arr+=( "$(bul "${role_name}")" )
      fi
    done < <(echo "$roles_json" | jq -c '.[]?' 2>/dev/null)
  else
    dept_blocks_arr+=( "$(p "Roles are materialized in your workforce filesystem under departments/${dept_slug}/. Each role's how-to.md contains the full role spec: name, what they do, daily rhythm, escalation rules, trigger phrases.")" )
  fi

  dept_blocks_arr+=( "$(h3 "SOPs in This Department: ${sops_count}")" )
  if [[ "$sops_count" -gt 0 && "$sops_count" != "0" ]]; then
    dept_blocks_arr+=( "$(p "This department has ${sops_count} Standard Operating Procedures ready. Each SOP defines the exact step-by-step procedure your AI roles follow for recurring tasks.")" )
    # List first up to 10 SOP titles if available
    sop_list_count=$(echo "$sops_json" | jq 'length' 2>/dev/null || echo "0")
    if [[ "$sop_list_count" -gt 0 ]]; then
      dept_blocks_arr+=( "$(p "Sample SOPs in this department:")" )
      display_count=10
      [[ "$sop_list_count" -lt "$display_count" ]] && display_count="$sop_list_count"
      for si in $(seq 0 $((display_count - 1))); do
        sop_title=$(echo "$sops_json" | jq -r ".[$si] | .title // .name // . // \"SOP\"" 2>/dev/null || echo "SOP")
        dept_blocks_arr+=( "$(bul "$sop_title")" )
      done
      if [[ "$sop_list_count" -gt "$display_count" ]]; then
        dept_blocks_arr+=( "$(p "...and $((sop_list_count - display_count)) more SOPs. All are accessible via your workforce filesystem and the mission-control database.")" )
      fi
    fi
  else
    dept_blocks_arr+=( "$(p "SOPs for this department are embedded in each role's how-to.md and stored in the mission-control database. Query by department to see all procedures.")" )
  fi

  # Idempotent: skip if this dept sub-page already exists under section 5.
  if child_section_exists "$SEC5_ID" "$dept_name"; then
    log "INFO" "dept sub-page '$dept_name' already present under section 5 -- skipping (idempotent resume)"
    continue
  fi
  dept_page_blocks=$(printf '%s\n' "${dept_blocks_arr[@]}" | jq -s '.')
  body=$(jq -n \
    --arg parent "$SEC5_ID" \
    --arg title "$dept_name" \
    --argjson children "$dept_page_blocks" \
    '{parent:{page_id:$parent},properties:{title:{title:[{type:"text",text:{content:$title}}]}},children:$children}')
  dept_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$body" \
    || echo "{}")
  if [[ -z "$(jq_get '.id' "$dept_resp" "dept-subpage:$dept_name")" ]]; then
    log "WARN" "failed creating dept sub-page for $dept_name. $(notion_error_of "$dept_resp")"
  fi
  pace
done

# ---- Section 6: How to Use Your Command Center (new dedicated section) ----
log "INFO" "creating section 6: How to Use Your Command Center"
sec6_blocks_arr=()

# Emit the CC URL prominently
if [[ -n "$CC_URL" ]]; then
  sec6_blocks_arr+=( "$(h "Your Command Center URL")" )
  sec6_blocks_arr+=( "$(p "Your Command Center is live at: ${CC_URL}")" )
  sec6_blocks_arr+=( "$(p "Bookmark this link. It is your real-time view of everything your AI workforce is doing.")" )
else
  sec6_blocks_arr+=( "$(p "Your Command Center URL will be provided by your setup engineer once the Cloudflare tunnel is active.")" )
fi

sec6_blocks_arr+=( "$(h "Accessing the Dashboard")" )
sec6_blocks_arr+=( "$(p "Open the Command Center URL in any browser. You will see your Kanban board with all departments and their active tasks. The dashboard updates automatically every 30 seconds.")" )

sec6_blocks_arr+=( "$(h "The Kanban Board")" )
sec6_blocks_arr+=( "$(p "Your board has 5 columns:")" )
sec6_blocks_arr+=( "$(bul "Backlog -- ideas and future work not yet ready to start")" )
sec6_blocks_arr+=( "$(bul "Ready -- approved and waiting to be picked up")" )
sec6_blocks_arr+=( "$(bul "In Progress -- currently being worked on by an AI role")" )
sec6_blocks_arr+=( "$(bul "Review -- completed work waiting for your approval")" )
sec6_blocks_arr+=( "$(bul "Complete -- finished and approved tasks")" )

sec6_blocks_arr+=( "$(h "Creating a Task")" )
sec6_blocks_arr+=( "$(p "Click the '+' button or 'Add Task' in any column. Fill in the title, department, description, and optional due date. Click Create. The department head will automatically see it and dispatch the right role.")" )

sec6_blocks_arr+=( "$(h "Moving Tasks")" )
sec6_blocks_arr+=( "$(p "Drag and drop tasks between columns, or click a task and change its status. Department heads will move tasks as they work through them. You do not need to manage this manually.")" )

sec6_blocks_arr+=( "$(h "Left Sidebar")" )
sec6_blocks_arr+=( "$(p "Click any department name to filter tasks to just that department. Click 'All Departments' to see everything. This is your fastest way to see what any one team is working on.")" )

sec6_blocks_arr+=( "$(h "Talking to Department Heads")" )
sec6_blocks_arr+=( "$(p "Each department has its own Telegram topic in your Command Center group. Tap the topic for the department you want (e.g. Marketing), type your message, and the department head responds directly.")" )
sec6_blocks_arr+=( "$(bul "Example: 'We need a social media campaign for our new product launch'")" )
sec6_blocks_arr+=( "$(bul "Example: 'Review last month's sales numbers and give me insights'")" )
sec6_blocks_arr+=( "$(bul "Example: 'Help me prepare for tomorrow's investor meeting'")" )

sec6_blocks_arr+=( "$(h "The 3-Check Rhythm")" )
sec6_blocks_arr+=( "$(p "Your department heads will proactively check in three times a day: morning (9 AM), midday (1 PM), and end of day (5 PM). At each check-in, they report what was completed, what is in progress, and any questions for you. You just reply with approvals, changes, or new priorities.")" )
sec6_blocks_arr+=( "$(p "To change the schedule, tell ${AGENT_NAME}: 'Change standup times to 8 AM, 12 PM, and 4 PM.' The agents will update their schedule immediately.")" )

sec6_blocks=$(printf '%s\n' "${sec6_blocks_arr[@]}" | jq -s '.')
create_child_page "6. How to Use Your Command Center" "$sec6_blocks" >/dev/null

# ---- Section 7: Communication Hierarchy ----
log "INFO" "creating section 7: Communication Hierarchy"
sec7_blocks=$(jq -s '.' \
  <(p "The hierarchy: Owner -- ${AGENT_NAME} (CEO Agent) -- Department Heads -- AI Employees.") \
  <(p "Why you talk to ${AGENT_NAME} by default: ${AGENT_NAME} knows everything that is happening across all departments. ${AGENT_NAME} picks the right team and the right role, routes the work, and reports back.") \
  <(p "Department Heads spawn temporary sub-agents to get specific jobs done. For example, the Marketing Head might spin up a Black-Friday-Promo-Writer sub-agent for one campaign, use it, then dismiss it. You do not see that -- but it is how scale happens behind the scenes.") \
  <(p "When you SHOULD talk to a Department Head directly: when you want to go deep on one department's strategy. Drop into that department's Telegram topic and have a focused conversation.") \
  <(p "When you should NEVER talk to an AI Employee directly: in normal day-to-day. The CEO and Department Heads exist to route. Do not bypass them -- you will just confuse the workflow.") )
create_child_page "7. Communication Hierarchy" "$sec7_blocks" >/dev/null

# ---- Section 8: Lean Six Sigma in Your ZHC ----
log "INFO" "creating section 8: Lean Six Sigma in Your ZHC"
sec8_blocks=$(jq -s '.' \
  <(p "Your AI workforce uses Lean Six Sigma methodology to eliminate waste, reduce variation, and keep getting better at running your business. Two engines work together: Lean removes waste; Six Sigma reduces variation.") \
  <(h "The Lean Engine -- Remove Waste") \
  <(p "Lean thinking means your workforce never idles, never re-invents procedures, and never drops handoffs. AI execution removes the three biggest operational wastes: idle time (your AI workers are always on), rework loops (SOPs define the right steps so output is done right the first time), and dropped handoffs (the Persona Tasks Alignment Matrix routes every task to the right place automatically).") \
  <(h "The Six Sigma Engine -- Reduce Variation") \
  <(p "Standardized SOPs reduce variation so output is consistent whether it is the first customer or the ten-thousandth. Every role runs the same step-by-step SOP, so the customer service experience is the same on Tuesday morning as it is on Saturday night.") \
  <(p "DMAIC stands for Define, Measure, Analyze, Improve, Control. Each department applies DMAIC to its own work:") \
  <(bul "DEFINE -- What is this department actually trying to accomplish for the owner? (Documented in the department's IDENTITY.md.)") \
  <(bul "MEASURE -- Track what is happening: tasks completed, errors made, time-to-output, quality scores. Every SOP has estimated minutes and confidence ratings so throughput per role is measurable.") \
  <(bul "ANALYZE -- When something goes wrong, root-cause it. Do not just patch the symptom. Update the department's MEMORY.md so the same mistake does not repeat.") \
  <(bul "IMPROVE -- Make the change. Update the prompt, the workflow, the trigger phrase, whatever.") \
  <(bul "CONTROL -- Lock the improvement in. Re-test on real work. Make sure the fix sticks. The Persona Tasks Alignment Matrix is the Control phase -- it locks in WHO does WHAT, preventing scope drift, mis-routing, and persona overload.") \
  <(p "Every Friday, ${AGENT_NAME} runs a DMAIC review across all departments and reports gaps. That is how the workforce gets sharper over time. Continuous improvement is not a project -- it is a rhythm built into the system.") )
create_child_page "8. Lean Six Sigma in Your ZHC" "$sec8_blocks" >/dev/null

# ---- Section 9: Book-to-Persona System ----
log "INFO" "creating section 9: Book-to-Persona System"
sec9_blocks=$(jq -s '.' \
  <(p "The Book-to-Persona System is how your AI workforce decides HOW to handle every task -- not just what to do, but the voice, style, and frame of reference to use.") \
  <(p "Every task gets scored on 5 dimensions: Relevance, Authority, Recency, Depth, Fit. Based on the scoring, the agent picks the right persona -- a book or expert framework that has been pre-trained into your workforce -- to guide the work.") \
  <(p "Example: a sales task scores high on Relevance and Authority for Cialdini's Influence -- the agent writes the outreach using Cialdini's principles. A coaching task scores high for Brene Brown -- the agent uses her vulnerability-first framing.") \
  <(p "This is why your outputs feel coherent and not random. The persona system imposes a consistent intelligence behind every department's work. See Skill 22 (Book-to-Persona Coaching Leadership System) in your installer for the full framework.") )
create_child_page "9. Book-to-Persona System" "$sec9_blocks" >/dev/null

# ---- Section 10: Your First 7 Days ----
log "INFO" "creating section 10: Your First 7 Days"
sec10_blocks=$(jq -s '.' \
  <(p "Action plan for week 1. Do not try to use everything at once. Build a habit.") \
  <(h "Day 1 -- Orientation") \
  <(bul "Open your Command Center URL and look around. Click each department's Kanban column. See what is there.") \
  <(bul "Have a 10-minute conversation with ${AGENT_NAME} in Telegram. Just chat. Ask what each department does.") \
  <(h "Day 2 -- One Real Task") \
  <(bul "Pick ONE small, real task that has been sitting on your plate. Give it to ${AGENT_NAME}. See what happens.") \
  <(bul "Do not critique the output immediately. Just notice: did it get done? How fast? Was the voice right?") \
  <(h "Day 3 -- Adjust the Voice") \
  <(bul "If yesterday's output sounded off, message ${AGENT_NAME} and say what was wrong specifically. The agent updates its MEMORY.md and will not repeat the mistake.") \
  <(h "Day 4 -- Test a Different Department") \
  <(bul "Move to a department you have not touched yet. Give it a real task. Compare the experience.") \
  <(h "Day 5 -- Delegate a Recurring Task") \
  <(bul "Find something you do every week and hand it off permanently. Schedule it as a recurring task in the Command Center.") \
  <(h "Day 6 -- Reflect") \
  <(bul "How much time did you save this week? What did the workforce get right? What still feels off?") \
  <(h "Day 7 -- Plan Week 2") \
  <(bul "Tell ${AGENT_NAME} what you want to add next. The workforce grows with you.") )
create_child_page "10. Your First 7 Days" "$sec10_blocks" >/dev/null

# ---- finalize ----
state_set ".notionRootPageUrl = \"$ROOT_URL\" | .notionCloseoutPageId = \"$ROOT_ID\""
if [[ "$RESUME_MODE" -eq 1 ]]; then
  log "INFO" "RESUME complete -- root url=$ROOT_URL id=$ROOT_ID (sections created this run=$SECTION_CREATED, already-present skipped=$SECTION_SKIPPED, no dupes)"
else
  log "INFO" "notion page tree complete -- root url=$ROOT_URL id=$ROOT_ID (sections created=$SECTION_CREATED, skipped=$SECTION_SKIPPED; notionCloseoutPageId set)"
fi
log "INFO" "closeoutLegStatus.notion = pass"
state_set ".closeoutLegStatus.notion = \"pass\"" || true
exit 0
