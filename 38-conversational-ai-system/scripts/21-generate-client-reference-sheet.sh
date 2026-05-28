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
: "${PUBLIC_HOSTNAME:?PUBLIC_HOSTNAME must be set (e.g., claw.thewinningformulacourse.com)}"
: "${ROUTE_ID:?ROUTE_ID must be set (e.g., ZHC)}"
: "${HOOKS_TOKEN:?HOOKS_TOKEN must be set}"
: "${CLIENT_BUSINESS_NAME:?CLIENT_BUSINESS_NAME must be set}"
: "${CLIENT_TELEGRAM_CHAT_ID:?CLIENT_TELEGRAM_CHAT_ID must be set}"

# ----- optional / defaulted inputs -----
OPERATOR_TELEGRAM_CHAT_ID="${OPERATOR_TELEGRAM_CHAT_ID:-5252140759}"
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
    ("3. Generic Workflow AI Prompt Template", os.environ["SEC3"]),
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
    printf '\n\n# 3. Generic Workflow AI Prompt Template\n\n'
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
    printf 'You can skip everything below this line and just click that Notion link. Every piece you need (the webhook URL, the SMS workflow prompt you paste into Convert and Flow Workflow AI, the verification checklist) is laid out for you in one readable page with code blocks you can copy with one click.\n\n'
    printf 'Below is the same information in this chat, in case the Notion link does not open or you want a quick scan:\n\n'
    printf -- '--- begin embedded fallback ---\n'
    printf 'Webhook URL: https://%s/hooks/%s\n' "$PUBLIC_HOSTNAME" "$ROUTE_ID"
    printf 'Authorization header: Bearer %s\n' "$HOOKS_TOKEN"
    printf 'Content-Type header: application/json\n'
    printf 'First workflow to build: %s (SMS Inquiry Responder).\n' "$WORKFLOW_ID"
    printf 'In Convert and Flow: Automations -> Create workflow -> Use Workflow AI -> paste Section 2 of the Notion page.\n'
    printf 'Then open Section 4 (Verification Checklist) and walk top-to-bottom before publishing.\n'
    printf -- '--- end embedded fallback ---\n\n'
    printf 'Anything you do not understand: screenshot it and message me. - Keez\n'
  } > "$CLIENT_MSG_FILE"
else
  {
    printf 'Hi %s, your conversational AI brain is set up.\n\n' "$CLIENT_FIRST_NAME"
    printf 'I put your setup reference here on your Mac:\n\n'
    printf '    %s\n\n' "$MD_FALLBACK_PATH"
    printf 'Heads up - I recommend you get Notion (notion.so) and ask me to push these into a Notion page next time. It is free and much easier to copy-paste from than markdown files.\n\n'
    printf 'You can read the four files in that folder in order (01, 02, 03, 04). 02 is the prompt you paste into Convert and Flow Workflow AI. 04 is the checklist you walk after Workflow AI builds the workflow.\n\n'
    printf 'Quick reference if you just want the essentials:\n\n'
    printf 'Webhook URL: https://%s/hooks/%s\n' "$PUBLIC_HOSTNAME" "$ROUTE_ID"
    printf 'Authorization header: Bearer %s\n' "$HOOKS_TOKEN"
    printf 'Content-Type header: application/json\n\n'
    printf 'Anything you do not understand: screenshot it and message me. - Keez\n'
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
