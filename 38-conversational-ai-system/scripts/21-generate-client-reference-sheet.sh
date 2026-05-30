#!/usr/bin/env bash
# 21-generate-client-reference-sheet.sh
# Skill 38 — Step 6: Generate the Client Reference Sheet (3-layer Notion-vs-markdown decision tree)
# AND deliver it to the client via Telegram with the Notion link prominently at the top.
#
# Layer 1: Notion skill installed (openclaw skills list shows notion)  -> use skill
# Layer 2: NOTION_API_KEY env present                                  -> direct Notion REST API call
# Layer 3: Neither                                                     -> markdown fallback + recommend Notion
#
# Code-block fidelity is the highest-priority requirement.
# Markdown -> Notion blocks is handled by python3 (NOT pure bash) to preserve newlines and chunk safely.
#
# OS-aware via uname -s. bash -n clean. set -euo pipefail.

set -euo pipefail

OS_NAME="$(uname -s)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR_DEFAULT="${SCRIPT_DIR}/../templates"
TEMPLATES_DIR="${SKILL38_TEMPLATES_DIR:-$TEMPLATES_DIR_DEFAULT}"

# ----- required inputs -----
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR must be set}"
: "${PUBLIC_HOSTNAME:?PUBLIC_HOSTNAME must be set (e.g., claw.example.com)}"
: "${ROUTE_ID:?ROUTE_ID must be set (e.g., ZHC)}"
: "${HOOKS_TOKEN:?HOOKS_TOKEN must be set}"
: "${CLIENT_BUSINESS_NAME:?CLIENT_BUSINESS_NAME must be set}"
: "${CLIENT_TELEGRAM_CHAT_ID:?CLIENT_TELEGRAM_CHAT_ID must be set}"

# ----- optional / defaulted inputs -----
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-}"
CLIENT_FIRST_NAME="${CLIENT_FIRST_NAME:-there}"
INDUSTRY_CONTEXT="${INDUSTRY_CONTEXT:-your industry}"
DESIRED_OUTCOME="${DESIRED_OUTCOME:-book a discovery call}"
WORKFLOW_ID="${WORKFLOW_ID:-sms-inquiry-responder}"
CHANNEL="${CHANNEL:-sms}"
NOTION_API_KEY="${NOTION_API_KEY:-}"

mkdir -p "$MASTER_FILES_DIR/conversation-workflows"
STAGE_DIR="$MASTER_FILES_DIR/conversation-workflows"

# ----- template paths -----
REF_TEMPLATE="${TEMPLATES_DIR}/client-reference-sheet-template.md"
SMS_TEMPLATE="${TEMPLATES_DIR}/sms-workflow-ai-prompt-template.md"
GENERIC_TEMPLATE="${TEMPLATES_DIR}/workflow-ai-prompt-template.md"
CHECKLIST_TEMPLATE="${TEMPLATES_DIR}/workflow-verification-checklist-template.md"

for f in "$REF_TEMPLATE" "$SMS_TEMPLATE" "$CHECKLIST_TEMPLATE"; do
  if [ ! -f "$f" ]; then
    echo "[21-generate-client-reference-sheet] WARN: template missing: $f" >&2
  fi
done

# ----- write helper python scripts to temp files (avoids heredoc-in-subshell parsing issues) -----
PY_SUB="$STAGE_DIR/.substitute.py"
PY_NOTION="$STAGE_DIR/.notion-publish.py"

write_substitute_py() {
  cat > "$PY_SUB" <<'PY_SUB_EOF'
import os, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as fh:
    txt = fh.read()
placeholders = [
    'CLIENT_BUSINESS_NAME', 'CLIENT_FIRST_NAME', 'PUBLIC_HOSTNAME',
    'ROUTE_ID', 'HOOKS_TOKEN', 'WORKFLOW_ID', 'CHANNEL',
    'INDUSTRY_CONTEXT', 'DESIRED_OUTCOME', 'MASTER_FILES_DIR',
]
for ph in placeholders:
    val = os.environ.get(ph, '')
    txt = txt.replace('<' + ph + '>', val)
    txt = txt.replace('{{' + ph + '}}', val)
sys.stdout.write(txt)
PY_SUB_EOF
}

write_notion_publish_py() {
  cat > "$PY_NOTION" <<'PY_NOTION_EOF'
import os, sys, json, re, urllib.request, urllib.error

API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": "Bearer " + os.environ["NOTION_API_KEY"],
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
CHUNK_LIMIT = 1800  # safely below Notions 2000-char per rich_text limit

def http(method, path, body=None):
    url = API + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.stderr.write("Notion API %s %s -> %s: %s\n" % (method, path, e.code, e.read().decode("utf-8","replace")))
        raise

def chunk_text(s, limit=CHUNK_LIMIT):
    out, buf = [], []
    cur = 0
    for line in s.split("\n"):
        ln = len(line) + 1
        if cur + ln > limit and buf:
            out.append("\n".join(buf))
            buf, cur = [], 0
        if len(line) > limit:
            if buf:
                out.append("\n".join(buf)); buf, cur = [], 0
            for i in range(0, len(line), limit):
                out.append(line[i:i+limit])
            continue
        buf.append(line); cur += ln
    if buf:
        out.append("\n".join(buf))
    return out or [""]

def rich(s):
    return [{"type": "text", "text": {"content": s}}]

def code_blocks(text, lang):
    lang = (lang or "plain text").lower().strip() or "plain text"
    notion_langs = {
        "bash":"bash","sh":"shell","shell":"shell","zsh":"shell",
        "json":"json","javascript":"javascript","js":"javascript",
        "typescript":"typescript","ts":"typescript","python":"python",
        "py":"python","yaml":"yaml","yml":"yaml","markdown":"markdown",
        "md":"markdown","html":"html","css":"css","text":"plain text",
        "plain":"plain text","":"plain text",
    }
    nl = notion_langs.get(lang, "plain text")
    chunks = chunk_text(text)
    blocks = []
    for c in chunks:
        blocks.append({
            "object":"block","type":"code",
            "code":{"rich_text":rich(c),"language":nl},
        })
    return blocks

def para(text):
    if not text.strip():
        return [{"object":"block","type":"paragraph","paragraph":{"rich_text":[]}}]
    blocks = []
    for c in chunk_text(text):
        blocks.append({"object":"block","type":"paragraph","paragraph":{"rich_text":rich(c)}})
    return blocks

def heading(text, level):
    t = {1:"heading_1",2:"heading_2",3:"heading_3"}.get(level, "heading_3")
    return [{"object":"block","type":t, t:{"rich_text":rich(text)}}]

def bullet(text):
    return [{"object":"block","type":"bulleted_list_item",
             "bulleted_list_item":{"rich_text":rich(text)}}]

def todo(text):
    return [{"object":"block","type":"to_do",
             "to_do":{"rich_text":rich(text),"checked":False}}]

def md_to_blocks(md):
    blocks = []
    lines = md.split("\n")
    i = 0
    fence = re.compile(r"^```(\S*)\s*$")
    while i < len(lines):
        line = lines[i]
        m = fence.match(line)
        if m:
            lang = m.group(1)
            body = []
            i += 1
            while i < len(lines) and not fence.match(lines[i]):
                body.append(lines[i]); i += 1
            i += 1
            blocks.extend(code_blocks("\n".join(body), lang))
            continue
        if line.startswith("# "):
            blocks.extend(heading(line[2:].strip(), 1)); i += 1; continue
        if line.startswith("## "):
            blocks.extend(heading(line[3:].strip(), 2)); i += 1; continue
        if line.startswith("### "):
            blocks.extend(heading(line[4:].strip(), 3)); i += 1; continue
        if re.match(r"^\s*- \[ \] ", line):
            blocks.extend(todo(re.sub(r"^\s*- \[ \] ","",line))); i += 1; continue
        if re.match(r"^\s*[-*] ", line):
            blocks.extend(bullet(re.sub(r"^\s*[-*] ","",line))); i += 1; continue
        buf = []
        while i < len(lines):
            cur = lines[i]
            if (not cur.strip() or cur.startswith("#") or fence.match(cur)
                    or re.match(r"^\s*[-*] ", cur) or re.match(r"^\s*- \[ \] ", cur)):
                break
            buf.append(cur); i += 1
        if buf:
            blocks.extend(para("\n".join(buf)))
        else:
            i += 1
    return blocks

parent_id = None
res = http("POST", "/search", {"query": os.environ["PARENT_SEARCH"],
                                "filter":{"property":"object","value":"page"}})
for r in res.get("results", []):
    title_parts = []
    props = r.get("properties", {})
    for p in props.values():
        if p.get("type") == "title":
            for t in p.get("title", []):
                title_parts.append(t.get("plain_text",""))
    title = "".join(title_parts).lower()
    if "zhc" in title:
        parent_id = r["id"]
        break

if parent_id is None:
    created = http("POST","/pages",{
        "parent":{"type":"workspace","workspace":True},
        "properties":{"title":[{"type":"text","text":{"content":"Conversational AI Brain - Setup Reference"}}]},
    })
    parent_id = created["id"]

section_titles = [
    ("1. Setup Reference Sheet", os.environ["SEC1"]),
    ("2. Your First Workflow - SMS Inquiry Responder", os.environ["SEC2"]),
    ("3. Generic Build-with-AI Prompt Template", os.environ["SEC3"]),
    ("4. Workflow Verification Checklist", os.environ["SEC4"]),
]
all_blocks = []
for title, path in section_titles:
    all_blocks.extend(heading(title, 1))
    try:
        with open(path,"r",encoding="utf-8") as fh:
            md = fh.read()
        all_blocks.extend(md_to_blocks(md))
    except FileNotFoundError:
        all_blocks.extend(para("(section template missing)"))

created = http("POST","/pages",{
    "parent":{"type":"page_id","page_id":parent_id},
    "properties":{"title":[{"type":"text","text":{"content":os.environ["PAGE_TITLE"]}}]},
    "children": all_blocks[:90],
})
page_id = created["id"]
remaining = all_blocks[90:]
batch = []
def flush():
    global batch
    if not batch:
        return
    http("PATCH","/blocks/"+page_id+"/children",{"children":batch})
    batch = []
for b in remaining:
    batch.append(b)
    if len(batch) >= 90:
        flush()
flush()

print(created.get("url",""))
PY_NOTION_EOF
}

write_substitute_py
write_notion_publish_py

# ----- helper: substitute placeholders into a template -----
substitute_template() {
  local tpl="$1"
  if [ ! -f "$tpl" ]; then
    printf '<!-- template missing: %s -->\n' "$tpl"
    return 0
  fi
  CLIENT_BUSINESS_NAME="$CLIENT_BUSINESS_NAME" \
  CLIENT_FIRST_NAME="$CLIENT_FIRST_NAME" \
  PUBLIC_HOSTNAME="$PUBLIC_HOSTNAME" \
  ROUTE_ID="$ROUTE_ID" \
  HOOKS_TOKEN="$HOOKS_TOKEN" \
  WORKFLOW_ID="$WORKFLOW_ID" \
  CHANNEL="$CHANNEL" \
  INDUSTRY_CONTEXT="$INDUSTRY_CONTEXT" \
  DESIRED_OUTCOME="$DESIRED_OUTCOME" \
  MASTER_FILES_DIR="$MASTER_FILES_DIR" \
  python3 "$PY_SUB" "$tpl"
}

# ----- render the 4 sections to staged files -----
SEC1="$STAGE_DIR/.reference-sheet.rendered.md"
SEC2="$STAGE_DIR/.sms-workflow-ai-prompt.rendered.md"
SEC3="$STAGE_DIR/.generic-workflow-ai-prompt.rendered.md"
SEC4="$STAGE_DIR/.verification-checklist.rendered.md"

substitute_template "$REF_TEMPLATE"      > "$SEC1"
substitute_template "$SMS_TEMPLATE"      > "$SEC2"
substitute_template "$GENERIC_TEMPLATE"  > "$SEC3"
substitute_template "$CHECKLIST_TEMPLATE" > "$SEC4"

# ============================================================================
# MANDATORY copy-paste artifacts — the "🚀 Quick Start" lead block + the FULL
# explanation/reference that follows it.
# These are PREPENDED to the TOP of the rendered reference sheet (SEC1) directly
# by this script so the sheet LEADS with a section literally named "🚀 Quick
# Start" carrying the exact copy-paste values in order:
#   (1) Webhook URL, (2) Authorization header — TWO code blocks ("Authorization"
#   + "Bearer <token>", NEVER combined), (2b) Content-Type header — TWO code
#   blocks ("Content-Type" + "application/json"), (3) Raw Body JSON (fenced
#   ```json, flat 23-key), (4) the manual Custom-Webhook fill steps, (5) the
#   create-tags-FIRST rule, (6) the POST-BUILD verification, (7) the Workflow-AI
#   prompt (Section 2 below).
# AND THEN — after Quick Start — a COMPLETE explanation/reference section (how it
# works, what each piece is, troubleshooting). Quick Start is NOT an excuse to
# drop the explanation; both are present. Every copyable value gets its OWN fenced
# code block (its own copy button) — clients are 50+ and copy each field
# individually. They ALWAYS appear as real, copyable fenced code blocks
# regardless of how the template wraps its prose.
#
# A live client opened a reference sheet that had NO bearer token and NO
# copyable Raw Body JSON — there was no `Authorization: Bearer <token>` to paste
# and no ```json body to drop into GHL's Build-with-AI, which stranded the client.
# AND: GHL's "Build with AI" only builds the workflow SHAPE (trigger + an EMPTY
# Custom Webhook action) — it does NOT reliably populate the URL, the
# Authorization/Bearer header, the Content-Type header, or the Raw Body JSON. So
# the client MUST open the Custom Webhook action and paste those values BY HAND.
# AND (the blank-tag gotcha): Build-with-AI created a trigger filter like "does
# not contain <tag>" but the referenced tag was blank / never created, so the
# filter silently matched nothing — the client MUST create the tag(s) FIRST and
# verify the built trigger references a REAL existing tag.
# qc-reference-sheet.sh machine-enforces that this output contains "🚀 Quick
# Start", an explanation section AFTER it, "Bearer", a ```json fence, the hook
# URL, the separate "Authorization" key + "Bearer" value code blocks, the
# manual-fill instructions, the tag-first instruction, AND the post-build
# verification (--require-manual-fill).
# ============================================================================

# Resolve the actual hooks bearer token, in priority order:
#   1. HOOKS_TOKEN env (already :?-required above, so normally set)
#   2. OPENCLAW_HOOKS_TOKEN env
#   3. hooks.token read from the live openclaw.json config
# If none resolve, emit a clearly-marked placeholder AND warn loudly (non-fatal
# so the rest of the sheet still renders, but the operator is told the token is
# missing and must be filled in before hand-off).
RESOLVED_HOOKS_TOKEN="${HOOKS_TOKEN:-}"
if [ -z "$RESOLVED_HOOKS_TOKEN" ]; then
  RESOLVED_HOOKS_TOKEN="${OPENCLAW_HOOKS_TOKEN:-}"
fi
if [ -z "$RESOLVED_HOOKS_TOKEN" ]; then
  for cfg in "${OPENCLAW_CONFIG:-}" "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
    [ -n "$cfg" ] || continue
    [ -f "$cfg" ] || continue
    TOK="$(python3 - "$cfg" <<'PY_TOK_EOF' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
hooks = d.get("hooks") or {}
tok = hooks.get("token") or ""
if isinstance(tok, str) and tok.strip():
    sys.stdout.write(tok.strip())
PY_TOK_EOF
)"
    if [ -n "$TOK" ]; then
      RESOLVED_HOOKS_TOKEN="$TOK"
      break
    fi
  done
fi

TOKEN_IS_PLACEHOLDER=0
if [ -z "$RESOLVED_HOOKS_TOKEN" ]; then
  RESOLVED_HOOKS_TOKEN="REPLACE_ME__hooks_token_not_resolved_at_generation_time"
  TOKEN_IS_PLACEHOLDER=1
  echo "[21-generate-client-reference-sheet] WARN: could not resolve the hooks bearer token (HOOKS_TOKEN / OPENCLAW_HOOKS_TOKEN / hooks.token in openclaw.json all empty). Emitting a clearly-marked PLACEHOLDER — fill it in before hand-off." >&2
fi

# Derive the hook route + routing agent id in a way that works across both
# repo variants (Mac uses ROUTING_AGENT_ID; VPS uses HOOK_NAME/AGENT_ID).
REF_HOOK_NAME="${HOOK_NAME:-$ROUTE_ID}"
REF_AGENT_ID="${AGENT_ID:-${ROUTING_AGENT_ID:-main}}"
REF_ENDPOINT_URL="https://${PUBLIC_HOSTNAME}/hooks/${REF_HOOK_NAME}"

# Build the LEAD block in spec order, then PREPEND it to SEC1 (the rest of the
# rendered reference-sheet template becomes the explanation/reference that follows).
LEAD_BLOCK="$STAGE_DIR/.reference-sheet.lead.md"
{
  printf '# 🚀 Quick Start\n\n'
  printf 'Everything you need to wire OpenClaw into GHL is in this Quick Start, in order. Do these steps top-to-bottom: create your tag(s), build the workflow with the prompt, then open the Custom Webhook action and paste the values by hand, verify, and publish. Each value below is its OWN copy block — tap the copy button and paste it straight into the matching GHL field. **The full explanation and reference (how it works, what each piece is, troubleshooting) is in the "📖 Full Reference & Explanation" section further down** — you do not need it to get live, but it is there when you want it.\n\n'
  printf '> READ THIS FIRST: GHL'\''s **"Build with AI"** only builds the workflow SHAPE (the trigger + an EMPTY Custom Webhook action). It does **NOT** fill in the URL, the Authorization/Bearer header, the Content-Type header, or the Raw Body JSON for you. You **MUST** open the Custom Webhook action yourself and paste the values below by hand. Build with AI will not fill these for you.\n\n'
  printf -- '---\n\n'

  # (0) Create tags FIRST (the a live client gotcha: a filter referenced a blank/never-created tag)
  printf '## 0. Create your tag(s) FIRST (before you build the workflow)\n\n'
  printf 'If this workflow uses ANY tag — a trigger or If/Else filter like "tag is" / "contains" / "does not contain", or an Add-Tag action — **create that tag FIRST so the filter references a REAL, existing tag.** Build with AI will happily create a filter that points at a tag that does not exist (e.g. "does not contain `<blank>`"), and that filter then silently matches nothing or everything — this is a known live-client bug.\n\n'
  printf -- '- **Preferred:** ask your AI agent to create the tag(s) for you via the GHL skill — name the exact tag(s) you want.\n'
  printf -- '- **Or in GHL by hand:** go to **Settings → Tags** and add each tag.\n'
  printf -- '- **Where to check:** **Settings → Tags** — you should SEE every tag this workflow uses listed there, spelled exactly as the workflow references it. If a tag is missing, the workflow filter that references it is broken until you create it.\n\n'
  printf '> The SMS Inquiry Responder starter (Section 2) does not require a tag. But the moment you add an If/Else branch or an Add-Tag step, do this step first.\n\n'

  # (1) Webhook URL
  printf '## 1. Webhook URL\n\n'
  printf 'Copy this into the Custom Webhook **URL** field (no trailing slash; keep the `/hooks/` segment):\n\n'
  printf '```\n'
  printf '%s\n' "$REF_ENDPOINT_URL"
  printf '```\n\n'

  # (2) Authorization header — TWO separate code blocks (key + value, NEVER combined)
  printf '## 2. Authorization header (TWO separate copy blocks)\n\n'
  if [ "$TOKEN_IS_PLACEHOLDER" = "1" ]; then
    printf '> WARNING: the hooks bearer token could not be read at generation time. The value block below is a PLACEHOLDER — replace it with your real `hooks.token` (from `~/.openclaw/openclaw.json`) before using this sheet.\n\n'
  fi
  printf 'Add this as a **manual header** on the Custom Webhook (leave the AUTHORIZATION dropdown set to "None"). The header has TWO parts — the **Key** and the **Value** — each in its own copy block so you can paste them into the two separate boxes GHL gives you. Copy each exactly — no leading/trailing spaces.\n\n'
  printf '**Header Key** (paste into the "Key" box):\n\n'
  printf '```\n'
  printf 'Authorization\n'
  printf '```\n\n'
  printf '**Header Value** (paste into the "Value" box):\n\n'
  printf '```\n'
  printf 'Bearer %s\n' "$RESOLVED_HOOKS_TOKEN"
  printf '```\n\n'

  # (2b) Content-Type header — TWO separate code blocks (key + value)
  printf '## 2b. Content-Type header (TWO separate copy blocks)\n\n'
  printf 'Add a SECOND header the same way — Key and Value in their own copy blocks.\n\n'
  printf '**Header Key** (paste into the "Key" box):\n\n'
  printf '```\n'
  printf 'Content-Type\n'
  printf '```\n\n'
  printf '**Header Value** (paste into the "Value" box):\n\n'
  printf '```\n'
  printf 'application/json\n'
  printf '```\n\n'

  # (3) Raw Body JSON (fenced json, flat 23-key)
  printf '## 3. GHL Custom Webhook — Raw Body (JSON)\n\n'
  printf '**Method:** POST   **Content-Type:** `application/json`\n\n'
  printf 'Paste this **RAW BODY** into the GHL Custom Webhook action. It is the canonical FLAT 23-key body — never paste a shorter one, never nest it, and keep `messageTemplate` placeholder-free so GHL does not mangle the JSON. Insert each `{{…}}` via GHL'\''s Custom Values picker. Only `channel` + the `session_key` prefix change per channel (this is the SMS body):\n\n'
  printf '```json\n'
  printf '{\n'
  printf '  "id": "%s",\n' "$REF_HOOK_NAME"
  printf '  "match": "%s",\n' "$REF_HOOK_NAME"
  printf '  "action": "agent",\n'
  printf '  "agent_id": "%s",\n' "$REF_AGENT_ID"
  printf '  "model": "ollama/deepseek-v4-flash:cloud",\n'
  printf '  "wakeMode": "now",\n'
  printf '  "name": "GHL Sales Inbound",\n'
  printf '  "session_key": "hook:ghl:sms:{{contact.id}}",\n'
  printf '  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",\n'
  printf '  "deliver": false,\n'
  printf '  "timeoutSeconds": 300,\n'
  printf '  "channel": "sms",\n'
  printf '  "to": "{{contact.phone}}",\n'
  printf '  "thinking": "medium",\n'
  printf '  "contact_id": "{{contact.id}}",\n'
  printf '  "first_name": "{{contact.first_name}}",\n'
  printf '  "last_name": "{{contact.last_name}}",\n'
  printf '  "email": "{{contact.email}}",\n'
  printf '  "phone": "{{contact.phone}}",\n'
  printf '  "subject": "{{message.subject}}",\n'
  printf '  "message_body": "{{message.body}}",\n'
  printf '  "location_id": "{{location.id}}",\n'
  printf '  "location_name": "{{location.name}}"\n'
  printf '}\n'
  printf '```\n\n'

  # (4) Manual Custom-Webhook fill steps ("Build with AI will not fill it, do it yourself")
  printf '## 4. Manually fill the Custom Webhook action (Build with AI will NOT do this for you)\n\n'
  printf 'After Build with AI runs, it leaves the Custom Webhook action EMPTY. In the GHL Custom Webhook UI, paste each value by hand, named precisely:\n\n'
  printf '1. **Method dropdown** = `POST` (choose POST — not GET/PUT).\n'
  printf '2. **URL box** = paste the Webhook URL from Section 1 above (no trailing slash; keep `/hooks/`).\n'
  printf '3. **AUTHORIZATION dropdown** = `None` (the token goes in Headers, NOT this dropdown).\n'
  printf '4. Under **HEADERS**, click **"Add item"**, then: **Key box** = `Authorization` (Section 2 key block), **Value box** = `Bearer <your token>` (Section 2 value block).\n'
  printf '5. Click **"Add item"** AGAIN, then: **Key box** = `Content-Type` (Section 2b key block), **Value box** = `application/json` (Section 2b value block).\n'
  printf '6. **Content-Type field** = `application/json`.\n'
  printf '7. **RAW BODY box** = paste the full 23-key JSON from Section 3 (Body type = Raw JSON), inserting each `{{…}}` via the Custom Values picker.\n'
  printf '8. **Save**, then **Publish** the workflow (not Draft).\n\n'
  printf '> **Build with AI will NOT fill these for you.** It only builds the trigger + an empty Custom Webhook action. **Verify every field above is non-empty before publishing** — an empty URL / missing Authorization header / empty Raw Body means the webhook silently does nothing and the customer gets no reply.\n\n'

  # (5) POST-BUILD VERIFICATION — DEAD SIMPLE, per area. One short line per
  # check + the exact value in a COPY CODE BLOCK + a one-line "if you do not
  # see it, paste this." Built for a 60-year-old: no essays, no 300-word
  # paragraphs. Order: open workflow; Trigger; Allow Re-entry; URL; Headers;
  # Raw Body; Save; Publish; Save.
  printf '## 5. Verify it after Build with AI runs (do each line, in order)\n\n'
  printf 'Each step is one line. Look for the thing. If you do not see it, copy the code block under that step and paste it in. That is the whole job.\n\n'
  printf '### 5.1 — Open the workflow you just built.\n\n'
  printf '### 5.2 — Click the **Trigger** at the top. You should see: **Customer Replied** / On Reply / Channel = SMS / Inbound.\n'
  printf 'If you do not see them, set them to:\n\n'
  printf '```\nCustomer Replied (On Reply) | Channel = SMS | Message Direction = Inbound\n```\n\n'
  printf '### 5.3 — Open **Settings**. **Allow Re-entry** should be **ON**.\n'
  printf 'If it is OFF, turn it ON (this lets the workflow run every time a contact texts, not just once).\n\n'
  printf '### 5.4 — Click the **Custom Webhook**. The **URL** should be:\n\n'
  printf '```\n%s\n```\n\n' "$REF_ENDPOINT_URL"
  printf 'If you do not see it, paste that into the URL box.\n\n'
  printf '### 5.5 — **Headers** should show two rows: `Authorization = Bearer ...` and `Content-Type = application/json`.\n'
  printf 'If you do not see them, click **Add item** and paste the **Key** then the **Value**:\n\n'
  printf '```\nAuthorization\n```\n\n'
  printf '```\nBearer %s\n```\n\n' "$RESOLVED_HOOKS_TOKEN"
  printf '```\nContent-Type\n```\n\n'
  printf '```\napplication/json\n```\n\n'
  printf '### 5.6 — The **Raw Body** should be the JSON below (all 23 lines).\n'
  printf 'If you do not see it, paste this into the Raw Body box (it is the same body as Section 3):\n\n'
  printf '```json\n'
  printf '{\n'
  printf '  "id": "%s",\n' "$REF_HOOK_NAME"
  printf '  "match": "%s",\n' "$REF_HOOK_NAME"
  printf '  "action": "agent",\n'
  printf '  "agent_id": "%s",\n' "$REF_AGENT_ID"
  printf '  "model": "ollama/deepseek-v4-flash:cloud",\n'
  printf '  "wakeMode": "now",\n'
  printf '  "name": "GHL Sales Inbound",\n'
  printf '  "session_key": "hook:ghl:sms:{{contact.id}}",\n'
  printf '  "messageTemplate": "Respond as the Sales agent and reply to this contact via the GHL Conversations API per TOOLS.md",\n'
  printf '  "deliver": false,\n'
  printf '  "timeoutSeconds": 300,\n'
  printf '  "channel": "sms",\n'
  printf '  "to": "{{contact.phone}}",\n'
  printf '  "thinking": "medium",\n'
  printf '  "contact_id": "{{contact.id}}",\n'
  printf '  "first_name": "{{contact.first_name}}",\n'
  printf '  "last_name": "{{contact.last_name}}",\n'
  printf '  "email": "{{contact.email}}",\n'
  printf '  "phone": "{{contact.phone}}",\n'
  printf '  "subject": "{{message.subject}}",\n'
  printf '  "message_body": "{{message.body}}",\n'
  printf '  "location_id": "{{location.id}}",\n'
  printf '  "location_name": "{{location.name}}"\n'
  printf '}\n'
  printf '```\n\n'
  printf '### 5.7 — Click **Save**.\n\n'
  printf '### 5.8 — Top-right: flip the toggle to **Publish** (it should read **Published**, not **Draft**).\n\n'
  printf '### 5.9 — Click **Save** again.\n\n'

  # (6) pointer to the Workflow-AI prompt (Section 2 of the full sheet)
  printf '## 6. Workflow-AI prompt\n\n'
  printf 'Use the **Workflow-AI prompt** (the SMS Inquiry Responder Build-with-AI prompt) in **Section 2 — Your First Workflow** further down this page. Paste it into GHL Automations → **Build with AI** to build the workflow SHAPE, then come back and do Section 4 (fill the empty Custom Webhook by hand) and Section 5 (verify) above.\n\n'
  printf -- '---\n\n'

  # (7) HOW TO TEST YOUR SYSTEM (REQ 4) — Contacts -> search self -> open
  # record -> text self -> reply on phone -> Automations -> open workflow ->
  # Execution Logs -> every step green (esp. Custom Webhook); red = failure.
  printf '## 7. How to test your system\n\n'
  printf 'When everything is built and published, test it end-to-end yourself. Do these in order:\n\n'
  printf -- '1. Go to **Contacts** (left menu).\n'
  printf -- '2. Type **your own name** in the search box.\n'
  printf -- '3. Open **your own contact record**.\n'
  printf -- '4. **Send yourself a text (SMS)** from inside that record.\n'
  printf -- '5. On your phone, **REPLY** to that text (a normal message like "hi, can you help me?").\n'
  printf -- '6. Go to **Automations** and **open the workflow you built**.\n'
  printf -- '7. Click **Execution Logs**.\n'
  printf -- '8. **Every step should show green / success — ESPECIALLY the Custom Webhook step.** Within a few seconds your phone should also get the AI reply back.\n\n'
  printf '> **Anything red = that step FAILED.** A red Custom Webhook is the most common one (URL, Authorization header, or Raw Body is wrong). Re-run the verification in Section 5, or contact support.\n\n'
  printf -- '---\n\n'

  # ============================================================================
  # YOUR COMMUNICATION PLAYBOOKS — placed AFTER the Quick Start, BEFORE the deep
  # Full Reference & Explanation. This answers the FIRST question every client
  # asks on their first test: "where are my workflows / communication playbooks?"
  # It is prominent (a top-level heading + a callout + a BIG BOLD "build a new
  # one" CTA) and machine-enforced by qc-reference-sheet.sh. It ALSO teaches the
  # NEW-playbook creation experience: a personal TRIGGER WORD (🔑 Alexa/Hey Siri
  # style), the "I Do / You Do" process (🤝 who does what + a great playbook takes
  # ~15-30 min ⏱️), and the brainstorm PREP (🧠 the "things to think about": goal,
  # audience, channel, offer/hook, tone, timing/follow-up, win action + "if you're
  # unsure that's what I'm here to brainstorm"). All three are machine-enforced by
  # qc-reference-sheet.sh --require-manual-fill.
  # ============================================================================
  printf '# 🗂️ Your Communication Playbooks\n\n'
  printf '> **Where are my workflows / communication playbooks?** 💬 Right here is the answer — read this before your first test.\n\n'
  printf '**Your communication playbooks live in two places, and they stay in sync:** 🔄\n\n'
  printf -- '- 🛠️ **The working copies** are stored in your OpenClaw master-files **`conversation-workflows/`** folder. That is the folder your AI reads on every reply to decide how to handle a conversation — it is the source of truth the agent runs from.\n'
  printf -- '- 📖 **The human-facing copies** (the ones YOU read) are in your **Notion** — and from Notion you can export to **Google Docs → plain text** any time. Same content, formatted for people instead of for the agent.\n\n'
  printf 'So: the agent runs from `conversation-workflows/`, and you read/share the Notion copy. Every playbook you have is recorded in your `conversation-workflows/registry.md` with a link to its human-facing doc. ✅\n\n'
  printf -- '---\n\n'
  printf '## ⭐ Want another communication playbook? Just ask me! 🚀\n\n'
  printf '**You do NOT build playbooks by hand. 🙌 Just tell your AI what you want and it does the rest.** In your chat with your AI, say something like:\n\n'
  printf '```\n'
  printf 'Help me build a missed-call follow-up playbook\n'
  printf '```\n\n'
  printf 'That is the whole ask. 💬 Swap in whatever you need — the pattern is always **"Help me build a [purpose] playbook."** A few more you can copy:\n\n'
  printf -- '- 📞 *"Help me build a missed-call follow-up playbook"*\n'
  printf -- '- 📅 *"Help me build an appointment-reminder playbook"*\n'
  printf -- '- 🌱 *"Help me build a lead-nurture playbook"*\n'
  printf -- '- ⭐ *"Help me build a review-request playbook"*\n\n'

  # ---- 🔑 Personal trigger word (Alexa / Hey Siri style) ----
  printf '## 🔑 Set a personal trigger word (like "Alexa" or "Hey Siri")\n\n'
  printf 'The first time you build a playbook, your AI will offer to set you a **personal trigger word** — a word or short phrase that instantly tells it you want to build a communication playbook, **just like saying "Alexa" or "Hey Siri."** 🗣️ Pick anything memorable — lots of people use something fun like **"Playbook time!"** Once it'\''s set, your AI remembers it, so any time you say it, it knows exactly what you mean and kicks off the build. ✅ (You can always just say *"Help me build a [purpose] playbook"* instead — the trigger word is just a fun shortcut.)\n\n'

  # ---- 🤝 The "I Do / You Do" process + ~15-30 min expectation ----
  printf '## 🤝 How we build it together — the "I Do / You Do" process ⏱️\n\n'
  printf 'Building a great playbook is a quick collaboration — it usually takes about **15-30 minutes** ⏱️ to get one really dialed in. Here'\''s who does what:\n\n'
  printf -- '1. **YOU** 🗣️ — trigger it (your trigger word, or *"Help me build a [purpose] playbook"*).\n'
  printf -- '2. **Your AI** 🧠 — asks you a few quick brainstorm questions, using what it already knows about your business (NOT a 50-question interrogation).\n'
  printf -- '3. **YOU** ✍️ — answer them (goal, audience, channel, offer, tone).\n'
  printf -- '4. **Your AI** 📝 — drafts the full playbook + conversation flow for your approval.\n'
  printf -- '5. **YOU** 👀 — review it and tell it any tweaks.\n'
  printf -- '6. **Your AI** 🗂️ — finalizes it, stores it (your `conversation-workflows/` folder, mirrored to Notion), and builds the matching **Workflow AI prompt** wired to your Convert and Flow account.\n'
  printf -- '7. **Your AI** ⚡ — wires the actions: creates tags 🏷️, updates your calendar 📅, creates/books appointments 🗓️.\n'
  printf -- '8. **YOU** ✅ — approve, and you go live!\n\n'

  # ---- 🧠 What to think about (the brainstorm prep) ----
  printf '## 🧠 What to think about before you ask (your AI will brainstorm the rest with you)\n\n'
  printf 'Your AI'\''s job is to **brainstorm with you to land the PERFECT playbook** — so you don'\''t need to have it all figured out. 💡 Just have a rough idea of these, and it will help you with the rest:\n\n'
  printf -- '- 🎯 **The goal** — what should this playbook do? (book a call, recover a sale, get a review, answer an FAQ)\n'
  printf -- '- 👥 **Who it'\''s for** — new leads, returning customers, hot prospects, cold/dormant contacts, existing clients?\n'
  printf -- '- 💬 **The channel(s)** — where it runs (SMS, email, Facebook/Instagram DM, WhatsApp, Live Chat).\n'
  printf -- '- 🪝 **The offer / hook** — what'\''s the pitch or the reason they'\''ll respond?\n'
  printf -- '- 🎙️ **The tone / brand voice** — how it should sound.\n'
  printf -- '- ⏰ **Timing & follow-up** — when it fires and how persistently it follows up.\n'
  printf -- '- 🏆 **The "win" action** — what counts as success (booked / replied / tagged / purchased).\n\n'
  printf '> **If you'\''re unsure about any of these, that'\''s exactly what your AI is here to brainstorm.** 🧠 You bring the idea, it asks the smart questions, and together you land the perfect playbook. 🚀\n\n'

  printf '**What your AI will DO when you ask (it does all of it WITH you):** 🛠️\n\n'
  printf -- '1. 🧠 **It brainstorms it with you** — a short, friendly back-and-forth (NOT a 50-question interrogation). It already knows your business, so it only asks what it genuinely needs, then shows you a quick "is this what you want?" summary to confirm.\n'
  printf -- '2. ✍️ **It creates the communication playbook for you** — written out, ready to run.\n'
  printf -- '3. 🗂️ **It stores it for you** — the working copy goes in your master-files **`conversation-workflows/`** folder (where the agent reads it on every reply), and it is **mirrored to your Notion** (→ Google Docs → plain text) so you can read and share it. It also registers it in your `conversation-workflows/registry.md`.\n'
  printf -- '4. 🤝 **It helps you create the matching Workflow AI prompt** — the prompt you paste into Convert and Flow (GoHighLevel) Automations → **Build with AI** — and it is wired to **YOUR** Convert and Flow account, not a generic one.\n'
  printf -- '5. ⚡ **It can take real actions in Convert and Flow on your behalf.** Your AI is connected to your Convert and Flow (GoHighLevel) account and can actually DO things in it for you — it can:\n'
  printf -- '   - 🏷️ **create and apply tags** on contacts,\n'
  printf -- '   - 📅 **update your calendar**,\n'
  printf -- '   - 🗓️ **create and book appointments**, and\n'
  printf -- '   - 🔁 similar automations across your account.\n\n'
  printf '> **You have an AI that is connected to your Convert and Flow account and can do these things for you — just ask.** 🚀 You describe the goal, your AI brainstorms it, creates the playbook, stores it (`conversation-workflows/` + Notion), wires the matching Workflow AI prompt to your Convert and Flow account, and can act in Convert and Flow on your behalf. Build as many as you want — that is the point of the system. ✅\n\n'
  printf -- '---\n\n'

  # ============================================================================
  # ⚙️ THINGS TO CONSIDER WHEN INSTALLING: VPS (Hostinger Docker) vs Mac mini
  # Placed AFTER the Quick Start + Communication Playbooks, BEFORE the deep Full
  # Reference. Two install targets diverge in WHERE env vars live, HOW to apply
  # them, HOW to restart, and HOW the public hook is exposed. Getting this wrong
  # is the single most common fleet install failure (env var written in the wrong
  # place, plain `restart` not reloading env_file, hooks.token rewritten on boot,
  # provider key not in the openclaw.json env block on Mac). Machine-enforced by
  # qc-reference-sheet.sh --require-manual-fill: the gate FAILs unless the doc
  # carries BOTH the VPS points (host /docker/<project>/.env + force-recreate +
  # container /data/.openclaw/secrets/.env + the hooks.token rewrite-on-boot
  # /OPENCLAW_HOOKS_TOKEN persistence point) AND the Mac points (provider keys in
  # the openclaw.json top-level env block + launchctl kickstart).
  # ============================================================================
  printf '# ⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini\n\n'
  printf 'OpenClaw runs on two kinds of box, and they handle config in **different places**. Most install failures come from doing a VPS step on a Mac (or vice-versa). Use the table that matches YOUR box. (If you do not know which you have: a **Hostinger Docker VPS** is a Linux server managed in the Hostinger panel with a `/docker/<project>/` folder; a **Mac mini** is a physical/virtual Mac running OpenClaw via Homebrew + launchd.)\n\n'

  printf '## 🐧 VPS (Hostinger Docker)\n\n'
  printf -- '- 🔑 **Env vars (API keys, tokens) live in the HOST file** `/docker/<project>/.env`. The Hostinger Docker Manager UI writes there — NOT to files inside the container under `/data/`.\n'
  printf -- '- 🔁 **Apply env changes with `docker compose up -d --force-recreate`** (run from `/docker/<project>/`). A plain `docker compose restart` does **NOT** reload `env_file` changes — the new vars never reach the running container. Always `up -d --force-recreate` after editing `.env`.\n'
  printf -- '- 🔐 **GHL + provider creds ALSO go in the container** `/data/.openclaw/secrets/.env` — that is where the GHL skill reads them. (The host `.env` is the canonical place for keys like Anthropic/OpenAI/Gemini; the GHL/secrets the skill reads at runtime live in the container `secrets/.env`. Both persist via the bind mount.)\n'
  printf -- '- 🪝 **The hooks token gets REWRITTEN on every boot.** The `/hostinger/server.mjs` wrapper rewrites `hooks.token` to `hooks_${OPENCLAW_GATEWAY_TOKEN}` on every container boot — so a token you set by hand silently reverts. **To make your hooks token persistent, set `OPENCLAW_HOOKS_TOKEN` in the host `/docker/<project>/.env`** (then `up -d --force-recreate`); the wrapper honors it instead of rewriting.\n'
  printf -- '- 🔌 **The gateway port is often NOT 18789.** Read the actual `PORT` env var (or run `openclaw gateway status`) before assuming a port — Hostinger frequently maps a different one.\n'
  printf -- '- 🌐 **Public hook URL** is exposed either via a **`cloudflared` tunnel** (run it under **PM2** and `pm2 save` so it survives reboot) **OR** via an existing **Traefik route** (`*.hstgr.cloud`). You do NOT need `sudo cloudflared service install` on a VPS.\n'
  printf -- '- 📦 **`apt` is a brew shim** on these containers (and brew is off PATH). Install packages with the full path: `/data/linuxbrew/.linuxbrew/bin/brew install <pkg>` — `apt`/`apt-get` will not do what you expect.\n\n'

  printf '## 🍎 Mac mini (Homebrew / launchd)\n\n'
  printf -- '- 🔑 **PROVIDER keys (e.g. `OLLAMA_API_KEY`) MUST go in the `openclaw.json` TOP-LEVEL `env` block.** The launchd service-env file does **NOT** carry provider keys to the gateway, and putting the key in `~/.openclaw/.env` alone is **insufficient** — the provider will fail to authenticate. Add provider keys to the `env` object at the top level of `~/.openclaw/openclaw.json`.\n'
  printf -- '- 🔐 **GHL creds still live in** `~/.openclaw/secrets/.env` (same as the VPS — the GHL skill reads `secrets/.env`).\n'
  printf -- '- 🔁 **Restart the gateway with** `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`. (There is NO Hostinger wrapper on a Mac, so the `hooks.token` in `openclaw.json` is **stable** — it is not rewritten on boot, and you do NOT need the `OPENCLAW_HOOKS_TOKEN` trick.)\n'
  printf -- '- 🛰️ **Remote access** is via a **Cloudflare tunnel + Access service token** (SSH in as the user'\''s own login; wrap remote commands in `zsh -lc "..."` or `node` is off PATH).\n'
  printf -- '- 🌐 **Public hook URL** is exposed via `sudo cloudflared service install <connector-token>` (installs a launchd LaunchDaemon). ⚠️ `sudo` prompts for the admin password and needs an interactive Terminal — it cannot run over a non-interactive rescue SSH session.\n\n'

  printf '## 🤝 Common to BOTH (do not skip regardless of box)\n\n'
  printf -- '- 📨 **The GHL Custom Webhook RAW BODY is the FLAT 23-key body** (Section 3 of the Quick Start) — never a shorter/stripped body, never nested.\n'
  printf -- '- 🔐 **GHL creds are read from `secrets/.env`** (container `/data/.openclaw/secrets/.env` on VPS, `~/.openclaw/secrets/.env` on Mac).\n'
  printf -- '- 📁 **The `conversational-logs/` directory is node-owned** (the gateway process creates + appends the per-contact conversation logs there) — do not chown it away from the node user or memory writes fail.\n'
  printf -- '- 🚫 **The inbound hook mapping uses `deliver: false`** (the agent sends its own reply via the GHL Conversations API; `deliver: true` double-sends and breaks).\n'
  printf -- '- 🧠 **Ollama Cloud `:cloud` models hard-cap `maxTokens` at 65536** — set `maxTokens: 65536` (a 384k value returns HTTP 400 on every call and silently breaks your primary model).\n\n'
  printf -- '---\n\n'

  # ---- THE FULL EXPLANATION / REFERENCE — comes AFTER Quick Start (both, not either) ----
  printf '# 📖 Full Reference & Explanation\n\n'
  printf 'Quick Start above is all you need to get live. This section explains HOW it works, WHAT each piece is, and HOW to troubleshoot — read it when you want the why behind the steps. **The Quick Start does not replace this; both are here on purpose.**\n\n'
  printf '## How the inbound pipe works (the 30-second version)\n\n'
  printf 'A customer messages your GHL number → your GHL workflow fires → its **Custom Webhook** POSTs the message to your OpenClaw at the **Webhook URL** (Section 1) → OpenClaw checks the **Authorization: Bearer** header (Section 2) to confirm it is really you → your AI agent reads the message, reads that contact'\''s conversation log, drafts a reply, and SENDS it back through the GHL Conversations API. The **Raw Body** (Section 3) is the envelope that carries the customer'\''s message + contact details to OpenClaw — all 23 fields, flat.\n\n'
  printf '## What each piece is\n\n'
  printf -- '- **Webhook URL** — your private OpenClaw address GHL posts to. One tunnel, many hook paths; this one is `/hooks/%s`.\n' "$REF_HOOK_NAME"
  printf -- '- **Authorization header (`Authorization` + `Bearer <token>`)** — the inbound password (your `HOOKS_TOKEN`). It lives in the **Headers** section, NOT the AUTHORIZATION dropdown (leave that dropdown on `None`). Two boxes in GHL = two copy blocks here.\n'
  printf -- '- **Content-Type header (`Content-Type` + `application/json`)** — tells OpenClaw the body is JSON.\n'
  printf -- '- **Raw Body (23-key, FLAT)** — the message envelope. FLAT (no nested objects) or every field arrives EMPTY. 23 keys is the minimum — never a shorter body. The body'\''s `messageTemplate` stays placeholder-free so GHL never mangles the JSON.\n'
  printf -- '- **Tags** — labels on a contact. If a workflow filters on a tag, that tag must EXIST first (Section 0) or the filter references a blank tag and breaks.\n\n'
  printf '## Troubleshooting (read the GHL execution log first)\n\n'
  printf -- '- **No execution at all** — the trigger never matched. Re-check the trigger TYPE and any tag filter (Section 5a): a blank/non-existent tag in a "contains"/"does not contain" filter matches nothing.\n'
  printf -- '- **401 Unauthorized** — the `Authorization` header is wrong or missing. Re-paste the Section 2 Key + Value blocks exactly (no extra spaces); the dropdown stays `None`.\n'
  printf -- '- **404 Not Found** — the URL is wrong. Re-paste Section 1 (must end `/hooks/%s`, no trailing slash).\n' "$REF_HOOK_NAME"
  printf -- '- **200 but no reply to the customer** — the agent received it but did not SEND. Check it was not classified as spam, that the GHL skill is installed + has its PIT, and that the server mapping carries the SEND directive.\n'
  printf -- '- **Empty fields at the hook** — the Raw Body was nested or the `{{…}}` tokens were typed as plain text instead of inserted via the Custom Values picker. Re-paste the FLAT Section 3 body and re-insert the tokens via the picker.\n\n'
  printf -- '---\n\n'
  printf '<!-- Everything below is additional explanation / reference (the rendered reference-sheet template). The Quick Start above + this Full Reference are the complete picture; you do not need anything below to get live. -->\n\n'
} > "$LEAD_BLOCK"

# Prepend the lead block to SEC1 (lead values FIRST, template explanation AFTER).
cat "$LEAD_BLOCK" "$SEC1" > "$SEC1.withlead" && mv "$SEC1.withlead" "$SEC1"

# ----- detect Notion availability -----
LAYER="3"
NOTION_FALLBACK_REASON=""

if command -v openclaw >/dev/null 2>&1; then
  if openclaw skills list 2>/dev/null | grep -iq notion; then
    LAYER="1"
  fi
fi

if [ "$LAYER" = "3" ] && [ -n "$NOTION_API_KEY" ]; then
  LAYER="2"
fi

if [ "$LAYER" = "3" ]; then
  NOTION_FALLBACK_REASON="Neither the OpenClaw Notion skill nor NOTION_API_KEY env var was found. Saved as markdown instead."
fi

NOTION_PAGE_URL=""
MD_FALLBACK_PATH=""

# ----- LAYER 1: Notion via openclaw skill -----
if [ "$LAYER" = "1" ]; then
  echo "[21-generate-client-reference-sheet] Layer 1 - using OpenClaw Notion skill"
  COMBINED="$STAGE_DIR/.combined-for-notion.md"
  {
    printf '# Conversational AI Brain - Setup Reference and Workflows\n\n'
    printf '# 1. Setup Reference Sheet\n\n'
    cat "$SEC1"
    printf '\n\n# 2. Your First Workflow - SMS Inquiry Responder\n\n'
    cat "$SEC2"
    printf '\n\n# 3. Generic Build-with-AI Prompt Template\n\n'
    cat "$SEC3"
    printf '\n\n# 4. Workflow Verification Checklist\n\n'
    cat "$SEC4"
  } > "$COMBINED"

  set +e
  NOTION_OUT="$(openclaw skill run notion create-page --parent-search zhc --title "Conversational AI Brain - Setup Reference and Workflows" --markdown-file "$COMBINED" --preserve-code-blocks --print-url 2>/dev/null)"
  RC=$?
  set -e
  NOTION_PAGE_URL="$(printf '%s\n' "$NOTION_OUT" | tail -n1)"
  if [ $RC -ne 0 ] || [ -z "$NOTION_PAGE_URL" ]; then
    echo "[21-generate-client-reference-sheet] Notion skill call failed - falling through to Layer 2" >&2
    LAYER="2"
    if [ -z "$NOTION_API_KEY" ]; then
      LAYER="3"
      NOTION_FALLBACK_REASON="Notion skill call failed and no NOTION_API_KEY available."
    fi
    NOTION_PAGE_URL=""
  fi
fi

# ----- LAYER 2: direct Notion API via python3 -----
if [ "$LAYER" = "2" ]; then
  echo "[21-generate-client-reference-sheet] Layer 2 - calling Notion API directly"
  if [ -z "$NOTION_API_KEY" ]; then
    LAYER="3"
    NOTION_FALLBACK_REASON="Layer 2 attempted but NOTION_API_KEY was empty."
  else
    set +e
    NOTION_OUT="$(NOTION_API_KEY="$NOTION_API_KEY" SEC1="$SEC1" SEC2="$SEC2" SEC3="$SEC3" SEC4="$SEC4" PARENT_SEARCH="zhc" PAGE_TITLE="Conversational AI Brain - Setup Reference and Workflows" python3 "$PY_NOTION" 2>/dev/null)"
    RC=$?
    set -e
    NOTION_PAGE_URL="$(printf '%s\n' "$NOTION_OUT" | tail -n1)"
    if [ $RC -ne 0 ] || [ -z "$NOTION_PAGE_URL" ]; then
      echo "[21-generate-client-reference-sheet] Notion API call failed - falling through to Layer 3" >&2
      LAYER="3"
      NOTION_FALLBACK_REASON="Notion API call returned non-zero. Check NOTION_API_KEY scope and integration access."
      NOTION_PAGE_URL=""
    fi
  fi
fi

# ----- LAYER 3: markdown fallback -----
if [ "$LAYER" = "3" ]; then
  echo "[21-generate-client-reference-sheet] Layer 3 - markdown fallback under $STAGE_DIR"
  MD_REF="$STAGE_DIR/01-client-reference-sheet.md"
  MD_SMS="$STAGE_DIR/02-${WORKFLOW_ID}--workflow-ai-prompt.md"
  MD_GEN="$STAGE_DIR/03-generic-workflow-ai-prompt-template.md"
  MD_CHK="$STAGE_DIR/04-${WORKFLOW_ID}--verification-checklist.md"
  cp "$SEC1" "$MD_REF"
  cp "$SEC2" "$MD_SMS"
  cp "$SEC3" "$MD_GEN"
  cp "$SEC4" "$MD_CHK"
  MD_FALLBACK_PATH="$STAGE_DIR"
fi

if [ -n "$NOTION_PAGE_URL" ]; then
  printf '%s\n' "$NOTION_PAGE_URL" > "$MASTER_FILES_DIR/.notion-reference-page-url"
fi

# ----- compose Telegram message to client (Notion link AT THE TOP, prominently) -----
CLIENT_MSG_FILE="$STAGE_DIR/.client-telegram-message.txt"
if [ -n "$NOTION_PAGE_URL" ]; then
  {
    printf 'Hi %s, your conversational AI brain is set up.\n\n' "$CLIENT_FIRST_NAME"
    printf 'I made you a clean, copy-paste-ready setup page in Notion:\n\n'
    printf '    %s\n\n' "$NOTION_PAGE_URL"
    printf 'You can skip everything below this line and just click that Notion link. Every piece you need (the webhook URL, the SMS workflow prompt you paste into Convert and Flow Automations -> Build with AI, the verification checklist) is laid out for you in one readable page with code blocks you can copy with one click.\n\n'
    printf 'Below is the same information in this chat, in case the Notion link does not open or you want a quick scan:\n\n'
    printf -- '--- begin embedded fallback ---\n'
    printf 'Webhook URL: https://%s/hooks/%s\n' "$PUBLIC_HOSTNAME" "$ROUTE_ID"
    printf 'Authorization header: Bearer %s\n' "$HOOKS_TOKEN"
    printf 'Content-Type header: application/json\n'
    printf 'First workflow to build: %s (SMS Inquiry Responder).\n' "$WORKFLOW_ID"
    printf 'In Convert and Flow: Automations -> new automation -> click "Build with AI" (top-right) -> paste Section 2 of the Notion page.\n'
    printf 'Then open Section 4 (Verification Checklist) and walk top-to-bottom before publishing.\n'
    printf -- '--- end embedded fallback ---\n\n'
    printf 'Anything you do not understand: screenshot it and message me. - your setup admin\n'
  } > "$CLIENT_MSG_FILE"
else
  {
    printf 'Hi %s, your conversational AI brain is set up.\n\n' "$CLIENT_FIRST_NAME"
    printf 'I put your setup reference here on your Mac:\n\n'
    printf '    %s\n\n' "$MD_FALLBACK_PATH"
    printf 'Heads up - I recommend you get Notion (notion.so) and ask me to push these into a Notion page next time. It is free and much easier to copy-paste from than markdown files.\n\n'
    printf 'You can read the four files in that folder in order (01, 02, 03, 04). 02 is the prompt you paste into Convert and Flow Automations -> Build with AI. 04 is the checklist you walk after Build with AI builds the workflow.\n\n'
    printf 'Quick reference if you just want the essentials:\n\n'
    printf 'Webhook URL: https://%s/hooks/%s\n' "$PUBLIC_HOSTNAME" "$ROUTE_ID"
    printf 'Authorization header: Bearer %s\n' "$HOOKS_TOKEN"
    printf 'Content-Type header: application/json\n\n'
    printf 'Anything you do not understand: screenshot it and message me. - your setup admin\n'
  } > "$CLIENT_MSG_FILE"
fi

# ----- send to client via openclaw gateway -----
CLIENT_MSG_ID=""
if command -v openclaw >/dev/null 2>&1; then
  set +e
  CLIENT_OUT="$(openclaw message send --channel telegram -t "$CLIENT_TELEGRAM_CHAT_ID" --file "$CLIENT_MSG_FILE" 2>&1)"
  RC=$?
  set -e
  CLIENT_MSG_ID="$(printf '%s\n' "$CLIENT_OUT" | tail -n1)"
  if [ $RC -ne 0 ]; then
    echo "[21-generate-client-reference-sheet] WARN: client Telegram send returned non-zero (out=$CLIENT_MSG_ID)" >&2
  fi
else
  echo "[21-generate-client-reference-sheet] WARN: openclaw CLI not in PATH - Telegram sends skipped" >&2
fi

# ----- operator summary -----
SECTION_COUNT="4"
L1=$(wc -l < "$SEC1" 2>/dev/null || echo 0)
L2=$(wc -l < "$SEC2" 2>/dev/null || echo 0)
L3=$(wc -l < "$SEC3" 2>/dev/null || echo 0)
L4=$(wc -l < "$SEC4" 2>/dev/null || echo 0)
TOTAL_LINES=$(( L1 + L2 + L3 + L4 ))

OP_MSG_FILE="$STAGE_DIR/.operator-telegram-message.txt"
{
  printf '[Skill 38 / Step 6] Client Reference Sheet delivered.\n\n'
  printf 'Client: %s (chat %s)\n' "$CLIENT_BUSINESS_NAME" "$CLIENT_TELEGRAM_CHAT_ID"
  printf 'Layer chosen: %s\n' "$LAYER"
  if [ -n "$NOTION_PAGE_URL" ]; then
    printf 'Notion page: %s\n' "$NOTION_PAGE_URL"
  else
    printf 'Markdown fallback path: %s\n' "$MD_FALLBACK_PATH"
    printf 'Fallback reason: %s\n' "$NOTION_FALLBACK_REASON"
  fi
  printf 'Sections: %s\n' "$SECTION_COUNT"
  printf 'Total content lines: %s\n' "$TOTAL_LINES"
  printf 'Client Telegram send result: %s\n' "${CLIENT_MSG_ID:-unknown}"
} > "$OP_MSG_FILE"

if command -v openclaw >/dev/null 2>&1; then
  openclaw message send --channel telegram -t "$OPERATOR_TELEGRAM_CHAT_ID" --file "$OP_MSG_FILE" >/dev/null 2>&1 || \
    echo "[21-generate-client-reference-sheet] WARN: operator Telegram send failed" >&2
fi

echo "[21-generate-client-reference-sheet] DONE  layer=$LAYER  url=${NOTION_PAGE_URL:-<none>}  fallback=${MD_FALLBACK_PATH:-<none>}"
