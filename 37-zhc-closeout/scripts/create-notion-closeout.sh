#!/usr/bin/env bash
# create-notion-closeout.sh — Build the 9-section Notion page tree in the
# client's own workspace and write notionRootPageUrl to state.
#
# Auth: NOTION_API_TOKEN (required), NOTION_API_VERSION (defaults 2022-06-28).
# Parent page: NOTION_CLOSEOUT_PARENT_PAGE_ID (optional — else search/create).
# Idempotent: if a page titled "Your Zero-Human Company — <Company>" already
# exists, returns its URL without re-creating.

set -u

if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[notion] no OpenClaw root" >&2
  exit 1
fi

STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"
LOG_FILE="$OC_ROOT/workspace/.zhc-closeout.log"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$SKILL_DIR/templates/notion-page-tree.json"
STEP_LABEL="notion"

NOTION_VERSION="${NOTION_API_VERSION:-2022-06-28}"

log() {
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2" >> "$LOG_FILE"
  printf '%s [%-5s] step=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$STEP_LABEL" "$2"
}
state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }
state_set() { local tmp; tmp=$(mktemp); jq "$1" "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"; }

notion_curl() {
  local method="$1"; shift
  local url="$1"; shift
  curl -sS --fail-with-body -X "$method" "$url" \
    -H "Authorization: Bearer $NOTION_API_TOKEN" \
    -H "Notion-Version: $NOTION_VERSION" \
    -H "Content-Type: application/json" \
    "$@"
}

with_retry() {
  # Run a notion API call with up to 3 retries + backoff.
  local attempt=0
  local out
  while (( attempt < 3 )); do
    attempt=$((attempt + 1))
    if out=$("$@" 2>&1); then
      echo "$out"
      return 0
    fi
    log "WARN" "notion call attempt $attempt failed: $(echo "$out" | head -c 200)"
    sleep $((2 ** attempt))
  done
  log "ERROR" "notion call exhausted 3 attempts"
  return 1
}

# ---- gather placeholders ----
COMPANY_NAME=$(state_get '.companyName'); [[ -z "$COMPANY_NAME" ]] && COMPANY_NAME="Your Company"
OWNER_NAME=$(state_get '.ownerName'); [[ -z "$OWNER_NAME" ]] && OWNER_NAME="the Owner"
AGENT_NAME=$(state_get '.agentName'); [[ -z "$AGENT_NAME" ]] && AGENT_NAME="the CEO Agent"
INFO_1=$(state_get '.infographic1Url')
INFO_2=$(state_get '.infographic2Url')
ROOT_TITLE="Your Zero-Human Company — ${COMPANY_NAME}"

# Departments + roles for Section 5
DEPT_JSON=$(jq -c '.departments' "$STATE_FILE")

# ---- resolve parent page ----
PARENT_PAGE_ID="${NOTION_CLOSEOUT_PARENT_PAGE_ID:-}"
if [[ -z "$PARENT_PAGE_ID" ]]; then
  log "INFO" "searching for an existing OpenClaw/BlackCEO parent page..."
  search_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
    -d '{"query":"BlackCEO","filter":{"value":"page","property":"object"},"page_size":5}' || echo "{}")
  PARENT_PAGE_ID=$(echo "$search_resp" | jq -r '.results[0].id // empty')
  if [[ -z "$PARENT_PAGE_ID" ]]; then
    search_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
      -d '{"query":"OpenClaw","filter":{"value":"page","property":"object"},"page_size":5}' || echo "{}")
    PARENT_PAGE_ID=$(echo "$search_resp" | jq -r '.results[0].id // empty')
  fi
fi
if [[ -z "$PARENT_PAGE_ID" ]]; then
  log "ERROR" "could not resolve a parent page (set NOTION_CLOSEOUT_PARENT_PAGE_ID env var, or create a parent page named 'BlackCEO' or 'OpenClaw' in the client's Notion workspace and share with the integration)"
  exit 1
fi
log "INFO" "parent page id=$PARENT_PAGE_ID"

# ---- idempotency: search for existing root page ----
existing_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/search" \
  -d "$(jq -n --arg q "$ROOT_TITLE" '{query:$q,filter:{value:"page",property:"object"},page_size:5}')" || echo "{}")
existing_id=$(echo "$existing_resp" | jq -r --arg t "$ROOT_TITLE" '.results[] | select((.properties.title.title[0].plain_text // .properties.Name.title[0].plain_text // "") == $t) | .id' | head -1)
if [[ -n "$existing_id" ]]; then
  existing_url=$(echo "https://www.notion.so/${existing_id//-/}")
  log "INFO" "root page already exists id=$existing_id — re-using"
  state_set ".notionRootPageUrl = \"$existing_url\""
  exit 0
fi

# ---- create root page ----
log "INFO" "creating root page: $ROOT_TITLE"
root_body=$(jq -n \
  --arg parent "$PARENT_PAGE_ID" \
  --arg title "$ROOT_TITLE" \
  '{
    parent: {page_id: $parent},
    properties: {title: {title: [{type: "text", text: {content: $title}}]}},
    children: [
      {object: "block", type: "heading_1", heading_1: {rich_text: [{type:"text", text:{content: $title}}]}},
      {object: "block", type: "paragraph", paragraph: {rich_text: [{type:"text", text:{content: "This is your full closeout doc. Read it in order — the sections build on each other. The 9 sections below explain what you have, how it works, and how to use it."}}]}}
    ]
  }')
root_resp=$(with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$root_body")
ROOT_ID=$(echo "$root_resp" | jq -r '.id')
if [[ -z "$ROOT_ID" || "$ROOT_ID" == "null" ]]; then
  log "ERROR" "root page creation returned no id; response: $(echo "$root_resp" | head -c 300)"
  exit 1
fi
ROOT_URL="https://www.notion.so/${ROOT_ID//-/}"
log "INFO" "root page created id=$ROOT_ID url=$ROOT_URL"

# Helper to create a child page under root
create_child_page() {
  local title="$1"
  local body_json="$2"   # JSON array of blocks (must be valid JSON)
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
  with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$body" \
    | jq -r '.id // empty'
}

p() {
  # paragraph block
  jq -n --arg t "$1" '{object:"block",type:"paragraph",paragraph:{rich_text:[{type:"text",text:{content:$t}}]}}'
}
h() {
  # heading_2 block
  jq -n --arg t "$1" '{object:"block",type:"heading_2",heading_2:{rich_text:[{type:"text",text:{content:$t}}]}}'
}
img() {
  jq -n --arg url "$1" '{object:"block",type:"image",image:{type:"external",external:{url:$url}}}'
}
bul() {
  jq -n --arg t "$1" '{object:"block",type:"bulleted_list_item",bulleted_list_item:{rich_text:[{type:"text",text:{content:$t}}]}}'
}

# Section 1
log "INFO" "creating section 1: What Is a Zero-Human Company?"
sec1_blocks=$(jq -s '.' <(p "A Zero-Human Company is a business where you, the owner, are freed from execution. You make decisions, set direction, and approve big moves. Every other layer of work — research, drafting, scheduling, follow-up, delivery, reporting — is done by your AI workforce.") \
  <(p "It is NOT 'no humans involved.' You are absolutely involved — at the top, where your judgment matters. The 'zero' refers to zero humans grinding execution work. That is what your AI workforce is for.") \
  <(p "It is NOT 'a chatbot.' A chatbot answers questions. A Zero-Human Company runs your operation.") \
  <(p "It IS owner-led, AI-executed.") )
create_child_page "1. What Is a Zero-Human Company?" "$sec1_blocks" >/dev/null

# Section 2
log "INFO" "creating section 2: What Is a Zero-Human Workforce?"
sec2_blocks=$(jq -s '.' <(p "Think of your AI workforce like a team of real employees — but they never sleep, never quit, never need a raise, and they're trained on your exact business voice.") \
  <(p "Each Department is a team. Each Role inside a department is an AI employee. They report up to a Department Head (also an AI). The Department Heads report up to your CEO Agent (${AGENT_NAME}). And ${AGENT_NAME} reports to you.") \
  <(p "Why this matters for delegation: instead of trying to remember 50 individual AI prompts, you just talk to ${AGENT_NAME}. ${AGENT_NAME} routes the work to the right team and the right person. You stay in CEO mode, not operator mode.") )
create_child_page "2. What Is a Zero-Human Workforce?" "$sec2_blocks" >/dev/null

# Section 3 — embed Infographic #1
log "INFO" "creating section 3: Your Workforce Structure"
if [[ -n "$INFO_1" && "$INFO_1" != "null" ]]; then
  sec3_blocks=$(jq -s '.' <(p "Here is the structure of your AI workforce. Owner at the top. ${AGENT_NAME} (CEO Agent) reports to you. Department Heads report to ${AGENT_NAME}. AI Employees report to their Department Head.") \
    <(img "$INFO_1") \
    <(p "Read it top-down. The CEO sees everything. Each Department Head only worries about their team. Each AI Employee only worries about their role.") )
else
  sec3_blocks=$(jq -s '.' <(p "(Workforce structure infographic will appear here once generated.)"))
fi
create_child_page "3. Your Workforce Structure" "$sec3_blocks" >/dev/null

# Section 4 — embed Infographic #2
log "INFO" "creating section 4: How Your Workforce Runs"
if [[ -n "$INFO_2" && "$INFO_2" != "null" ]]; then
  sec4_blocks=$(jq -s '.' <(p "Here is how the work flows. You give a task to ${AGENT_NAME}. ${AGENT_NAME} routes it to the right Department. The Department Head dispatches the right AI Employee (or spawns a temporary sub-agent for the specific job). The output comes back through the same chain.") \
    <(img "$INFO_2") \
    <(p "You usually only ever talk to ${AGENT_NAME}. The routing is invisible to you, by design.") )
else
  sec4_blocks=$(jq -s '.' <(p "(Workflow infographic will appear here once generated.)"))
fi
create_child_page "4. How Your Workforce Runs" "$sec4_blocks" >/dev/null

# Section 5 — Departments & Roles (one sub-page per department)
log "INFO" "creating section 5: Departments & Roles + per-dept sub-pages"
sec5_intro_blocks=$(jq -s '.' <(p "Below are your departments. Each department has its own sub-page listing every role, what each role does, when to use it, and what to say to trigger it. Read these once so you know what's available — and refer back when you're not sure which AI employee to ask for.") \
  <(p "Total departments: $(echo "$DEPT_JSON" | jq 'length')."))
SEC5_ID=$(create_child_page "5. Departments & Roles" "$sec5_intro_blocks")
log "INFO" "section 5 root id=$SEC5_ID"

# Create one sub-page per department under section 5
n_depts=$(echo "$DEPT_JSON" | jq 'length')
for i in $(seq 0 $((n_depts - 1))); do
  dept_name=$(echo "$DEPT_JSON" | jq -r ".[$i].name // .[$i].slug")
  dept_slug=$(echo "$DEPT_JSON" | jq -r ".[$i].slug")
  dept_roles_n=$(echo "$DEPT_JSON" | jq -r ".[$i].rolesDone // 0")
  dept_blocks=$(jq -s '.' <(h "Department: $dept_name") \
    <(p "Slug: $dept_slug. Roles built: $dept_roles_n.") \
    <(p "Roles in this department:") \
    <(bul "(Roles are materialized in your workforce filesystem under departments/$dept_slug/. Open any role's README.md for the full role spec — name, what they do, purpose, ideal use cases, trigger phrases.)") )
  # POST as child of SEC5_ID
  body=$(jq -n \
    --arg parent "$SEC5_ID" \
    --arg title "$dept_name" \
    --argjson children "$dept_blocks" \
    '{parent:{page_id:$parent},properties:{title:{title:[{type:"text",text:{content:$title}}]}},children:$children}')
  with_retry notion_curl POST "https://api.notion.com/v1/pages" -d "$body" >/dev/null || log "WARN" "failed creating dept sub-page for $dept_name"
done

# Section 6
log "INFO" "creating section 6: Communication Hierarchy"
sec6_blocks=$(jq -s '.' <(p "The hierarchy: Owner → ${AGENT_NAME} (CEO Agent) → Department Heads → AI Employees.") \
  <(p "Why you talk to ${AGENT_NAME} by default: ${AGENT_NAME} knows everything that's happening across all departments. ${AGENT_NAME} picks the right team and the right role, routes the work, and reports back.") \
  <(p "Department Heads spawn temporary sub-agents to get specific jobs done. For example, the Marketing Head might spawn a 'Black-Friday-Promo-Writer' sub-agent for one campaign, use it, then dismiss it. You don't see that — but it's how scale happens behind the scenes.") \
  <(p "When you SHOULD talk to a Department Head directly: when you want to go deep on one department's strategy. Drop into that department's Telegram topic in your Command Center and have a focused conversation.") \
  <(p "When you should NEVER talk to an AI Employee directly: in normal day-to-day. The CEO and Department Heads exist to route. Don't bypass them — you'll just confuse the workflow."))
create_child_page "6. Communication Hierarchy" "$sec6_blocks" >/dev/null

# Section 7 — Six Sigma
log "INFO" "creating section 7: Six Sigma in Your ZHC"
sec7_blocks=$(jq -s '.' <(p "Six Sigma is the framework your AI workforce uses to keep getting better at running your business. It's how we measure, learn, and improve — not just execute.") \
  <(p "DMAIC stands for Define, Measure, Analyze, Improve, Control. Each department applies DMAIC to its own work:") \
  <(bul "DEFINE — What is this department actually trying to accomplish for the owner? (Documented in the department's IDENTITY.md.)") \
  <(bul "MEASURE — Track what's happening: tasks completed, errors made, time-to-output, quality scores.") \
  <(bul "ANALYZE — When something goes wrong, root-cause it. Don't just patch the symptom. Update the department's MEMORY.md so the same mistake doesn't repeat.") \
  <(bul "IMPROVE — Make the change. Update the prompt, the workflow, the trigger phrase, whatever.") \
  <(bul "CONTROL — Lock the improvement in. Re-test on real work. Make sure the fix sticks.") \
  <(p "Every Friday, ${AGENT_NAME} runs a DMAIC review across all departments and reports gaps. That's how the workforce gets sharper over time."))
create_child_page "7. Six Sigma in Your ZHC" "$sec7_blocks" >/dev/null

# Section 8 — Book-to-Persona
log "INFO" "creating section 8: Book-to-Persona System"
sec8_blocks=$(jq -s '.' <(p "The Book-to-Persona System is how your AI workforce decides HOW to handle every task — not just what to do, but the voice, style, and frame of reference to use.") \
  <(p "Every task gets scored on 5 dimensions: Relevance, Authority, Recency, Depth, Fit. Based on the scoring, the agent picks the right 'persona' — a book or expert framework that's been pre-trained into your workforce — to guide the work.") \
  <(p "Example: a sales task scores high on Relevance and Authority for Cialdini's 'Influence' → the agent writes the outreach using Cialdini's principles. A coaching task scores high for Brené Brown → the agent uses her vulnerability-first framing.") \
  <(p "This is why your outputs feel coherent and not random. The persona system imposes a consistent intelligence behind every department's work.") \
  <(p "See Skill 22 (Book-to-Persona Coaching Leadership System) in your installer for the full framework."))
create_child_page "8. Book-to-Persona System" "$sec8_blocks" >/dev/null

# Section 9 — First 7 Days
log "INFO" "creating section 9: Your First 7 Days"
sec9_blocks=$(jq -s '.' <(p "Action plan for week 1. Don't try to use everything at once. Build a habit.") \
  <(h "Day 1 — Orientation") \
  <(bul "Open your Command Center URL and look around. Click each department's Kanban column. See what's there.") \
  <(bul "Have a 10-minute conversation with ${AGENT_NAME} in Telegram. Just chat. Ask what each department does.") \
  <(h "Day 2 — One real task") \
  <(bul "Pick ONE small, real task that's been sitting on your plate. Give it to ${AGENT_NAME}. See what happens.") \
  <(bul "Don't critique the output immediately. Just notice: did it get done? How fast? Was the voice right?") \
  <(h "Day 3 — Adjust the voice") \
  <(bul "If yesterday's output sounded off, message ${AGENT_NAME} and say what was wrong specifically. The agent updates its MEMORY.md and won't repeat the mistake.") \
  <(h "Day 4 — Test a different department") \
  <(bul "Move to a department you haven't touched yet. Give it a real task. Compare the experience.") \
  <(h "Day 5 — Delegate a recurring task") \
  <(bul "Find something you do every week and hand it off permanently. Schedule it as a recurring task in the Command Center.") \
  <(h "Day 6 — Reflect") \
  <(bul "How much time did you save this week? What did the workforce get right? What still feels off?") \
  <(h "Day 7 — Plan week 2") \
  <(bul "Tell ${AGENT_NAME} what you want to add next. The workforce grows with you."))
create_child_page "9. Your First 7 Days" "$sec9_blocks" >/dev/null

# ---- finalize ----
state_set ".notionRootPageUrl = \"$ROOT_URL\""
log "INFO" "notion page tree complete — root url=$ROOT_URL"
exit 0
