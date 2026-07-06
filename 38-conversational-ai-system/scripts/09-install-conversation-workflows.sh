#!/usr/bin/env bash
# 09-install-conversation-workflows.sh
#
# Step 9 — "Set up conversation log system" + the conversation-workflows registry.
#
# Creates the conversation-workflows registry AND the conversational-logs dir
# under MASTER_FILES_DIR.
#
# What this does:
#   1. Reads MASTER_FILES_DIR from ~/.openclaw/.skill-38-master-files-dir
#      (this pointer file is written by 01-locate-master-files-folder.sh).
#   2. Creates `$MASTER_FILES_DIR/conversational-logs/` if missing AND ensures it
#      is OWNED BY THE RUNTIME USER (the gateway user — `node` on VPS/docker; the
#      login user on a Mac/Homebrew install) so the agent can WRITE to it. This is
#      mandatory: the per-contact conversation log is the ONLY memory a single-turn
#      GHL hook session has. On a live client the dir was created root-owned and the
#      agent could not append until it was chowned to `node` — the agent silently
#      "lost memory" mid-conversation. Read-before/append-after is dead without a
#      writable dir.
#   3. Creates `$MASTER_FILES_DIR/conversation-workflows/` if missing.
#   4. Writes `$MASTER_FILES_DIR/conversation-workflows/registry.md` with the
#      3-Layer architecture summary, file-naming conventions, and trigger
#      phrases — ONLY IF the registry does not already exist (idempotent).
#
# OS-aware (Darwin / Linux) but the source-of-truth for the path is the
# pointer file written by step 01.

set -euo pipefail

# -----------------------------------------------------------------------------
# Resolve MASTER_FILES_DIR
# -----------------------------------------------------------------------------
POINTER_FILE="${HOME}/.openclaw/.skill-38-master-files-dir"
if [[ ! -f "$POINTER_FILE" ]]; then
  echo "[09-install-conversation-workflows] pointer file missing: $POINTER_FILE" >&2
  echo "[09-install-conversation-workflows] run 01-locate-master-files-folder.sh first." >&2
  exit 1
fi

MASTER_FILES_DIR="$(cat "$POINTER_FILE")"
MASTER_FILES_DIR="${MASTER_FILES_DIR%$'\n'}"

if [[ -z "$MASTER_FILES_DIR" || ! -d "$MASTER_FILES_DIR" ]]; then
  echo "[09-install-conversation-workflows] MASTER_FILES_DIR is empty or not a directory: '$MASTER_FILES_DIR'" >&2
  exit 1
fi

WORKFLOWS_DIR="$MASTER_FILES_DIR/conversation-workflows"
REGISTRY="$WORKFLOWS_DIR/registry.md"
LOGS_DIR="$MASTER_FILES_DIR/conversational-logs"

# -----------------------------------------------------------------------------
# Conversation-log system (Step 9): create the per-contact conversational-logs
# dir and make it WRITABLE BY THE RUNTIME (gateway) USER.
#
# GHL inbound hook sessions are single-turn / stateless. The agent's only memory
# of a contact across messages is the per-contact log file in this dir, which it
# must READ before replying and APPEND to after sending. If this dir does not
# exist, or exists but is owned by root while the gateway runs as `node`, the
# agent silently cannot persist memory — exactly the live-client regression this
# step prevents. So: mkdir -p, then chown to the runtime user.
# -----------------------------------------------------------------------------
mkdir -p "$LOGS_DIR"

# Determine the gateway runtime user and chown the logs dir to it so the agent
# can write. On VPS/Docker the gateway runs as `node`; on a Mac/Homebrew install
# it runs as the login user (no chown needed there). Best-effort: never fail the
# install if chown is not permitted — but always report what was (or wasn't) done.
RUNTIME_USER="${OPENCLAW_RUNTIME_USER:-}"
if [[ -z "$RUNTIME_USER" ]]; then
  OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
  if [[ "$OS_NAME" == "Linux" ]]; then
    # VPS/Docker default gateway user.
    RUNTIME_USER="node"
  else
    # Mac/Homebrew: the gateway runs as the current login user already.
    RUNTIME_USER="$(id -un 2>/dev/null || echo "$USER")"
  fi
fi

CURRENT_OWNER="$(stat -f '%Su' "$LOGS_DIR" 2>/dev/null || stat -c '%U' "$LOGS_DIR" 2>/dev/null || echo "")"
if [[ -n "$RUNTIME_USER" && "$CURRENT_OWNER" != "$RUNTIME_USER" ]]; then
  if chown -R "$RUNTIME_USER" "$LOGS_DIR" 2>/dev/null; then
    echo "[09-install-conversation-workflows] conversational-logs dir chowned to runtime user '$RUNTIME_USER' → $LOGS_DIR"
  elif command -v sudo >/dev/null 2>&1 && sudo -n chown -R "$RUNTIME_USER" "$LOGS_DIR" 2>/dev/null; then
    echo "[09-install-conversation-workflows] conversational-logs dir chowned (sudo) to runtime user '$RUNTIME_USER' → $LOGS_DIR"
  else
    echo "[09-install-conversation-workflows] WARNING: could not chown $LOGS_DIR to '$RUNTIME_USER' (current owner: '${CURRENT_OWNER:-unknown}')." >&2
    echo "[09-install-conversation-workflows] The gateway user MUST own this dir or the agent cannot append conversation logs (= silent memory loss)." >&2
    echo "[09-install-conversation-workflows] Run manually:  sudo chown -R $RUNTIME_USER \"$LOGS_DIR\"" >&2
  fi
else
  echo "[09-install-conversation-workflows] conversational-logs dir ready (owner '$CURRENT_OWNER') → $LOGS_DIR"
fi

mkdir -p "$WORKFLOWS_DIR"

# -----------------------------------------------------------------------------
# Write registry.md (idempotent — only when absent). Either way we FALL THROUGH
# to the human-facing playbook-doc step + verify/resume gate below, so an already
# present registry still gets its missing per-playbook docs created/recorded.
# -----------------------------------------------------------------------------
if [[ -f "$REGISTRY" ]]; then
  echo "[09-install-conversation-workflows] registry already present — leaving as-is: $REGISTRY"
else

# -----------------------------------------------------------------------------
# Write registry.md
# -----------------------------------------------------------------------------
cat > "$REGISTRY" <<'REG_EOF'
# Conversation Workflows — Registry

This folder holds every Conversation Workflow installed for this client.
The agent reads `registry.md` on every inbound to see which workflow (if
any) should fire for the customer's current intent.

## What is a Conversation Workflow?

A scenario-specific behavior override. Other conversational AI platforms
make operators build workflows in visual node-based UIs (n8n, Zapier, GHL
Workflow Builder). This system has operators TALK through workflows: the
agent asks intelligent questions, synthesizes a Conversation Playbook,
AND auto-builds the GHL routing layer the customer needs to reach the AI
in the first place.

Conversation Workflows are complementary to Communication Playbooks:

- **Communication Playbook** = baseline tone/voice for a channel. One per
  channel. Applies to every reply on that channel.
- **Conversation Workflow** = specific scenario behavior override. Many
  per client. Applies only when its trigger fires (pricing inquiry,
  booking request, FAQ, etc.).

When a workflow fires, its scenario instructions override the channel
playbook's body content, but the channel playbook's tone/signature is
still honored.

## 3-Layer Architecture summary

- **Layer 0 — Routing check.** Did this inbound match an existing
  workflow's trigger? If yes, fire that workflow. If no, fall through to
  the standard channel playbook.
- **Layer 1 — GHL side.** The GHL workflow + tag automations that route
  the inbound message into the agent in the first place. Auto-built
  during workflow setup; mirrored in `<workflow-id>--ghl-side.md`.
- **Layer 2 — OpenClaw playbook.** The agent-side scenario behavior:
  Phase 1 (acknowledge), Phase 2 (gather), Phase 3 (act), Phase 4
  (handoff). Stored in `<workflow-id>.md`.

Full builder protocol (Layers 0/1/2 walkthrough): see the skill's
`protocols/conversation-workflows-protocol.md`.

## File-naming conventions

For every workflow with id `<workflow-id>` (kebab-case, alphanumeric +
hyphens only):

- `<workflow-id>.md` — Layer 2 OpenClaw playbook (Phase 1-4 + edge cases)
- `<workflow-id>--ghl-side.md` — Layer 1 GHL routing mirror (tags,
  triggers, workflow IDs)
- `<workflow-id>--build-with-ai-prompt.md` — the Build-with-AI prompt
  (pasted into GHL Automations -> "Build with AI") used to build the GHL side
  (legacy name `<workflow-id>--workflow-ai-prompt.md` still accepted by QC)
- `<workflow-id>--verification-checklist.md` — operator-runnable
  verification checklist confirming the workflow is live end-to-end

## How to invoke the builder

The operator can trigger the Workflow Builder by sending the agent any
of these intent phrases (case-insensitive, fuzzy match — Step 9.20
Section A):

- "Help me build a conversation playbook"
- "Help me build a conversation workflow"
- "Build me a workflow for <X>"
- "Build me a playbook for <X>"
- "Create a workflow for <X>"
- "Create a playbook for <X>"
- "Set up a conversation flow for <X>"
- "I want a workflow that does <X>"
- "Walk me through building a workflow"

The agent then hands control to the Workflow Builder subagent walkthrough
(`protocols/conversation-workflows-protocol.md` Section B) and runs the
operator through the 3-Layer setup end-to-end.

## Active workflows

Append one ROW per installed workflow to the table below. This is the canonical
registry shape (matches `protocols/conversation-workflows-protocol.md` §F and the
`qc-trinity-registry.sh` validator). The `Layer 1?` column tells the validator
whether a Build-with-AI prompt is legitimately absent ("No (uses existing
inbound)") or required ("Yes").

The `Doc (Notion/Docs/text)` column is MANDATORY and machine-enforced by
`qc-playbook-doc.sh`: every playbook MUST also have a human-facing copy in the
CLIENT's own account, created in the fallback order Notion → Google Docs →
plain-text. Record that doc's URL/path in this column — a row with an empty /
`n/a` / placeholder doc cell FAILS QC (the install is NOT complete until the doc
is created and recorded). See `references/communications-playbook-standard.md` §4.

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist | Doc (Notion/Docs/text) |
|---|---|---|---|---|---|---|---|

<!-- workflows: none yet -->

<!--
  Legacy bullet form (- <workflow-id>: <one-line description>  [doc: <url-or-path>])
  is still understood by qc-trinity-registry.sh + qc-playbook-doc.sh for older
  installed registries, but new registrations should use the table row above so
  the Layer-1 disposition AND the human-facing doc reference are recorded.
-->
REG_EOF

echo "[09-install-conversation-workflows] registry created → $REGISTRY"
fi

# =============================================================================
# BINDING — per-playbook human-facing doc deliverable (Notion → Google Docs →
# plain-text). The install is NOT complete until every conversation playbook on
# disk has a human-facing copy created in the CLIENT's own account and its
# URL/path recorded in the registry's "Doc (Notion/Docs/text)" column.
#
# Root cause this enforces: on a live client this step was SKIPPED — the agent
# scaffolded the playbook files locally and reported "clean" but never created
# the client's Notion doc, leaving the customer with no human-facing reference.
# It was PROSE in the standard, not an enforced gate. This block + the registry
# state field + qc-playbook-doc.sh make it un-skippable (mirrors the
# send-directive / conversation-memory enforcement).
#
# Fallback order (NEVER co-mingle clients — always the client's OWN workspace):
#   (a) Notion   — create a subpage under the client's designated parent page
#                  using NOTION_API_KEY (integration must be shared with that
#                  parent; set NOTION_PARENT_PAGE_ID or NOTION_PARENT_SEARCH).
#   (b) Google Docs — if no Notion, use the Google Workspace helper per TOOLS.md.
#   (c) plain text  — if neither, write a .md the client can access and tell the
#                     operator exactly where it is.
# Each result's URL/path is recorded back into the registry doc column.
# =============================================================================

NOTION_API_KEY="${NOTION_API_KEY:-}"
NOTION_PARENT_PAGE_ID="${NOTION_PARENT_PAGE_ID:-}"
NOTION_PARENT_SEARCH="${NOTION_PARENT_SEARCH:-}"

# Stage a Notion-publish helper (mirrors scripts/21-generate-client-reference-sheet.sh).
PY_NOTION_DOC="$WORKFLOWS_DIR/.playbook-doc-notion.py"
write_playbook_doc_notion_py() {
  cat > "$PY_NOTION_DOC" <<'PY_DOC_EOF'
import os, sys, json, re, urllib.request, urllib.error

API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": "Bearer " + os.environ["NOTION_API_KEY"],
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
CHUNK_LIMIT = 1800

def http(method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def chunk_text(s, limit=CHUNK_LIMIT):
    out, buf, cur = [], [], 0
    for line in s.split("\n"):
        ln = len(line) + 1
        if cur + ln > limit and buf:
            out.append("\n".join(buf)); buf, cur = [], 0
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

def para(text):
    if not text.strip():
        return [{"object":"block","type":"paragraph","paragraph":{"rich_text":[]}}]
    return [{"object":"block","type":"paragraph","paragraph":{"rich_text":rich(c)}}
            for c in chunk_text(text)]

def heading(text, level):
    t = {1:"heading_1",2:"heading_2",3:"heading_3"}.get(level, "heading_3")
    return [{"object":"block","type":t, t:{"rich_text":rich(text)}}]

def bullet(text):
    return [{"object":"block","type":"bulleted_list_item",
             "bulleted_list_item":{"rich_text":rich(text)}}]

def md_to_blocks(md):
    blocks, lines, i = [], md.split("\n"), 0
    fence = re.compile(r"^```(\S*)\s*$")
    while i < len(lines):
        line = lines[i]
        m = fence.match(line)
        if m:
            body = []
            i += 1
            while i < len(lines) and not fence.match(lines[i]):
                body.append(lines[i]); i += 1
            i += 1
            for c in chunk_text("\n".join(body)):
                blocks.append({"object":"block","type":"code",
                               "code":{"rich_text":rich(c),"language":"plain text"}})
            continue
        if line.startswith("# "):  blocks.extend(heading(line[2:].strip(),1)); i+=1; continue
        if line.startswith("## "): blocks.extend(heading(line[3:].strip(),2)); i+=1; continue
        if line.startswith("### "):blocks.extend(heading(line[4:].strip(),3)); i+=1; continue
        if re.match(r"^\s*[-*] ", line):
            blocks.extend(bullet(re.sub(r"^\s*[-*] ","",line))); i+=1; continue
        buf = []
        while i < len(lines):
            cur = lines[i]
            if not cur.strip() or cur.startswith("#") or fence.match(cur) or re.match(r"^\s*[-*] ", cur):
                break
            buf.append(cur); i += 1
        if buf:
            blocks.extend(para("\n".join(buf)))
        else:
            i += 1
    return blocks

# Resolve the client's designated PARENT page (never co-mingle clients).
parent_id = os.environ.get("NOTION_PARENT_PAGE_ID", "").strip()
if not parent_id:
    q = os.environ.get("NOTION_PARENT_SEARCH", "").strip()
    if not q:
        sys.stderr.write("no NOTION_PARENT_PAGE_ID and no NOTION_PARENT_SEARCH — cannot place the doc in the client's workspace\n")
        sys.exit(3)
    res = http("POST", "/search", {"query": q,
               "filter": {"property": "object", "value": "page"}})
    for r in res.get("results", []):
        title = ""
        for p in r.get("properties", {}).values():
            if p.get("type") == "title":
                title = "".join(t.get("plain_text","") for t in p.get("title", []))
        if q.lower() in title.lower():
            parent_id = r["id"]; break
    if not parent_id and res.get("results"):
        parent_id = res["results"][0]["id"]
    if not parent_id:
        sys.stderr.write("no accessible parent page matched NOTION_PARENT_SEARCH=%r (share the integration with the client's page)\n" % q)
        sys.exit(3)

with open(os.environ["DOC_BODY_PATH"], "r", encoding="utf-8") as fh:
    md = fh.read()
all_blocks = md_to_blocks(md)

created = http("POST", "/pages", {
    "parent": {"type": "page_id", "page_id": parent_id},
    "properties": {"title": [{"type": "text", "text": {"content": os.environ["DOC_TITLE"]}}]},
    "children": all_blocks[:90],
})
page_id = created["id"]
batch = []
for b in all_blocks[90:]:
    batch.append(b)
    if len(batch) >= 90:
        http("PATCH", "/blocks/"+page_id+"/children", {"children": batch}); batch = []
if batch:
    http("PATCH", "/blocks/"+page_id+"/children", {"children": batch})

print(created.get("url",""))
PY_DOC_EOF
}

# create_playbook_doc <slug> — ensure a human-facing doc exists for <slug> and
# echo its recorded reference (URL or path). Tries Notion → Google Docs → text.
create_playbook_doc() {
  local slug="$1"
  local body_file="$WORKFLOWS_DIR/$slug.md"
  local title="Conversation Playbook — $slug"
  local doc_body
  doc_body="$(mktemp "${TMPDIR:-/tmp}/playbook-doc-XXXXXX.md")"
  {
    printf '# %s\n\n' "$title"
    printf 'Human-facing reference of this conversation playbook (created in the client account).\n\n'
    if [[ -f "$body_file" ]]; then
      cat "$body_file"
    else
      printf '(Layer-2 playbook body %s not yet on disk at doc-creation time.)\n' "$body_file"
    fi
    for companion in "$slug--build-with-ai-prompt.md" "$slug--workflow-ai-prompt.md" "$slug--verification-checklist.md"; do
      if [[ -f "$WORKFLOWS_DIR/$companion" ]]; then
        printf '\n\n---\n\n## %s\n\n' "$companion"
        cat "$WORKFLOWS_DIR/$companion"
      fi
    done
  } > "$doc_body"

  # (a) Notion first.
  if [[ -n "$NOTION_API_KEY" ]] && { [[ -n "$NOTION_PARENT_PAGE_ID" ]] || [[ -n "$NOTION_PARENT_SEARCH" ]]; }; then
    write_playbook_doc_notion_py
    local url
    set +e
    url="$(NOTION_API_KEY="$NOTION_API_KEY" \
           NOTION_PARENT_PAGE_ID="$NOTION_PARENT_PAGE_ID" \
           NOTION_PARENT_SEARCH="$NOTION_PARENT_SEARCH" \
           DOC_TITLE="$title" DOC_BODY_PATH="$doc_body" \
           python3 "$PY_NOTION_DOC" 2>/dev/null | tail -n1)"
    local rc=$?
    set -e
    if [[ $rc -eq 0 && -n "$url" ]]; then
      echo "[09-install-conversation-workflows] playbook '$slug' doc → CREATED IN CLIENT NOTION: $url" >&2
      rm -f "$doc_body"
      printf '%s\n' "$url"
      return 0
    fi
    echo "[09-install-conversation-workflows] Notion doc for '$slug' failed (no key/parent or API error) — falling back to Google Docs/text" >&2
  fi

  # (b) Google Docs (per the Google Workspace helper in TOOLS.md, if present).
  local gdocs_helper=""
  for cand in "$HOME/clawd/google-api.js" "$HOME/clawd/scripts/google-api.js"; do
    [[ -f "$cand" ]] && gdocs_helper="$cand" && break
  done
  if [[ -n "$gdocs_helper" ]] && command -v node >/dev/null 2>&1; then
    local gurl
    set +e
    gurl="$(node "$gdocs_helper" docs-create --title "$title" --markdown-file "$doc_body" --print-url 2>/dev/null | tail -n1)"
    local grc=$?
    set -e
    if [[ $grc -eq 0 && "$gurl" == http* ]]; then
      echo "[09-install-conversation-workflows] playbook '$slug' doc → CREATED IN CLIENT GOOGLE DOCS: $gurl" >&2
      rm -f "$doc_body"
      printf '%s\n' "$gurl"
      return 0
    fi
    echo "[09-install-conversation-workflows] Google Docs helper for '$slug' failed — falling back to plain text" >&2
  fi

  # (c) Plain-text doc the client can access (in the client's master-files dir).
  local docs_dir="$MASTER_FILES_DIR/playbook-docs"
  mkdir -p "$docs_dir"
  local text_path="$docs_dir/$slug-doc.md"
  cp "$doc_body" "$text_path"
  rm -f "$doc_body"
  echo "[09-install-conversation-workflows] playbook '$slug' doc → NO Notion/Google Docs available; wrote PLAIN-TEXT doc the client can access: $text_path" >&2
  printf '%s\n' "$text_path"
}

# record_doc_in_registry <slug> <doc-ref> — write the doc reference into the
# registry. Updates the matching table row's last cell, or appends a bullet with
# a [doc: …] tail under "## Active workflows" if the slug isn't a table row yet.
record_doc_in_registry() {
  local slug="$1" docref="$2"
  SLUG="$slug" DOCREF="$docref" REGFILE="$REGISTRY" python3 - <<'PY_REC_EOF'
import os, re
slug = os.environ["SLUG"]
docref = os.environ["DOCREF"]
reg = os.environ["REGFILE"]
text = open(reg, "r", encoding="utf-8").read()
lines = text.split("\n")
out = []
done = False
for line in lines:
    s = line.strip()
    if s.startswith("|") and not done:
        cells = [c.strip() for c in s.strip("|").split("|")]
        rid = cells[0].strip("`").strip() if cells else ""
        if rid == slug:
            # Replace/append the trailing doc cell.
            if len(cells) >= 8:
                cells[-1] = docref
            else:
                cells.append(docref)
            out.append("| " + " | ".join(cells) + " |")
            done = True
            continue
    out.append(line)
if not done:
    # Append a bullet under "## Active workflows".
    new = []
    inserted = False
    for line in out:
        new.append(line)
        if not inserted and line.strip().lower().startswith("## active workflow"):
            new.append("")
            new.append("- %s: human-facing doc recorded  [doc: %s]" % (slug, docref))
            inserted = True
    if not inserted:
        new.append("")
        new.append("- %s: human-facing doc recorded  [doc: %s]" % (slug, docref))
    out = new
open(reg, "w", encoding="utf-8").write("\n".join(out))
PY_REC_EOF
}

# -----------------------------------------------------------------------------
# Verify/resume gate: for every conversation playbook on disk that has NO recorded
# human-facing doc, create one (Notion → Google Docs → text) and record it. This
# is the RESUME half — an incomplete doc is retried, never silently skipped.
# -----------------------------------------------------------------------------
QC_DOC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/qc-playbook-doc.sh"

# Enumerate playbook slugs on disk (<slug>.md, excluding registry + companions).
# Portable (bash 3.2+) — no mapfile, no case-in-process-substitution.
DISK_SLUGS=""
for f in "$WORKFLOWS_DIR"/*.md; do
  [[ -e "$f" ]] || continue
  base="$(basename "$f")"
  case "$base" in
    registry.md) continue ;;
    *--build-with-ai-prompt.md|*--workflow-ai-prompt.md|*--verification-checklist.md|*--ghl-side.md) continue ;;
  esac
  DISK_SLUGS="$DISK_SLUGS ${base%.md}"
done
DISK_SLUGS="$(printf '%s\n' $DISK_SLUGS | sort -u | tr '\n' ' ')"

if [[ -z "${DISK_SLUGS// /}" ]]; then
  echo "[09-install-conversation-workflows] no conversation playbooks on disk yet — the per-playbook human-facing doc (Notion → Google Docs → text) is created when the FIRST playbook (appointment booking, F.7) is built; qc-playbook-doc.sh will gate it at QC."
else
  for slug in $DISK_SLUGS; do
    # Already recorded? Skip (idempotent).
    if [[ -f "$QC_DOC" ]] && bash "$QC_DOC" --dir "$WORKFLOWS_DIR" --json 2>/dev/null \
         | SLUG="$slug" python3 -c "import json,sys,os; d=json.load(sys.stdin); s=os.environ['SLUG']; sys.exit(0 if any(p['slug']==s and not p['problems'] for p in d.get('playbooks',[])) else 1)"; then
      echo "[09-install-conversation-workflows] playbook '$slug' already has a recorded human-facing doc — leaving as-is."
      continue
    fi
    DOC_REF="$(create_playbook_doc "$slug")"
    if [[ -n "$DOC_REF" ]]; then
      record_doc_in_registry "$slug" "$DOC_REF"
      echo "[09-install-conversation-workflows] recorded doc for '$slug' in registry → $DOC_REF"
    else
      echo "[09-install-conversation-workflows] WARNING: failed to create a human-facing doc for '$slug' — qc-playbook-doc.sh will FAIL until this is resolved." >&2
    fi
  done
fi

# =============================================================================
# Part 4, THE VISUAL (U-11): after doc creation, generate the workflow visual for
# every on-disk playbook and record the Visual column. scripts/31-generate-workflow-
# visual.sh parses the playbook via the canonical engine, emits diagram.mmd, renders
# diagram.png via npx mermaid-cli (free), generates the budget-capped Kie hero, and
# records the Visual column in registry.md + the manifest. Best-effort: the truth
# diagram must NEVER block the install, so a failure WARNs and never changes exit.
# =============================================================================
GEN_VISUAL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/31-generate-workflow-visual.sh"
if [[ -f "$GEN_VISUAL" ]] && [[ -n "${DISK_SLUGS// /}" ]]; then
  for slug in $DISK_SLUGS; do
    if bash "$GEN_VISUAL" "$slug" --dir "$WORKFLOWS_DIR" >/dev/null 2>&1; then
      echo "[09-install-conversation-workflows] generated + recorded the Visual (Part 4) for '$slug'"
    else
      echo "[09-install-conversation-workflows] WARNING: could not generate the Visual for '$slug' (mermaid-cli/Kie offline?); the truth diagram never blocks the install. Rerun scripts/31-generate-workflow-visual.sh $slug once online." >&2
    fi
  done
fi

rm -f "$PY_NOTION_DOC" 2>/dev/null || true
