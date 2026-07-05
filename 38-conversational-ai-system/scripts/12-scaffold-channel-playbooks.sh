#!/usr/bin/env bash
# 12-scaffold-channel-playbooks.sh — Skill 38 Step 8
# Scaffolds the 8 channel communication playbooks (SMS, Email, FB Messenger,
# FB Comments, IG DM, LinkedIn, Live Chat, All-in-One Chat) from the template
# in templates/channel-playbook-template.md.
#
# Layer 1 (preferred): if $NOTION_API_KEY is set, create a Notion page per
#   channel under the existing "zhc" parent page (or a new "Channel Playbooks"
#   parent if zhc is not found), and save the page id to
#   $MASTER_FILES_DIR/channel-playbooks/<channel>--notion-id.txt
# Layer 2 (fallback): write markdown to
#   $MASTER_FILES_DIR/channel-playbooks/<channel>.md
#
# Idempotent: existing files / notion-id files are preserved.

set -euo pipefail

# -------- OS detection --------
OS_KERNEL="$(uname -s 2>/dev/null || echo unknown)"
case "$OS_KERNEL" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      OS=other ;;
esac

# -------- Inputs --------
MASTER_FILES_POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
if [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(cat "$MASTER_FILES_POINTER")"
else
  MASTER_FILES_DIR="${MASTER_FILES_DIR:-${HOME}/.openclaw/skill-38-master-files}"
fi

# Resolve the skill root DYNAMICALLY from this script's own location — this script
# lives at <skill-root>/scripts/12-scaffold-channel-playbooks.sh, so the skill root is
# its parent's parent. Do NOT hardcode a legacy path like
# ~/clawd/skills/38-openclaw-cloudflare-tunnel (that directory no longer exists; the
# skill is 38-conversational-ai-system and may be installed under any skills root).
# SKILL38_ROOT may still be overridden via env for tests.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL38_ROOT="${SKILL38_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
TEMPLATE_PATH="${TEMPLATE_PATH:-$SKILL38_ROOT/templates/channel-playbook-template.md}"
CLIENT_BUSINESS_NAME="${CLIENT_BUSINESS_NAME:-<CLIENT_BUSINESS_NAME>}"
ESCALATION_TARGET="${ESCALATION_TARGET:-<ESCALATION_TARGET>}"

CHANNELS=(
  "SMS"
  "Email"
  "FB-Messenger"
  "FB-Comments"
  "IG-DM"
  "LinkedIn"
  "Live-Chat"
  "All-in-One-Chat"
)

OUT_DIR="$MASTER_FILES_DIR/channel-playbooks"
mkdir -p "$OUT_DIR"

if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "[ERROR] template not found: $TEMPLATE_PATH" >&2
  exit 1
fi

# -------- Persona registry (U-5) --------
# Seed the house-default persona once so persona resolution NEVER fails (playbook
# persona line -> channel default -> house default). Idempotent: an existing file
# is preserved. See protocols/persona-registry-protocol.md.
PERSONAS_DIR="$MASTER_FILES_DIR/personas"
HOUSE_PERSONA_PATH="$PERSONAS_DIR/house-standard.md"
PERSONA_ID="house-standard"

seed_house_persona() {
  mkdir -p "$PERSONAS_DIR"
  if [ -s "$HOUSE_PERSONA_PATH" ]; then
    echo "[SKIP] persona house-standard (already seeded)"
    return 0
  fi
  cat > "$HOUSE_PERSONA_PATH" <<PERSONA_EOF
# Persona: house-standard

voice-summary: warm, clear, and helpful - a friendly professional who gets to the point
formality-level: balanced
message-length-bias: short
emoji-policy: sparing
typo-policy: off
pacing: measured

## Vertical variables
business_name: $CLIENT_BUSINESS_NAME
service_noun: service
appointment_noun: appointment
PERSONA_EOF
  echo "[OK] persona house-standard -> $HOUSE_PERSONA_PATH"
}

# Prepend the persona: header line to a rendered playbook body (U-5). The line
# lets the runtime resolve the active persona (playbook persona line first).
add_persona_line() {
  # $1 = body text (stdin-free helper: passed as arg via command substitution)
  printf 'persona: %s\n\n%s' "$PERSONA_ID" "$1"
}

seed_house_persona

# -------- Notion helpers --------
NOTION_VERSION="2022-06-28"
notion_available() { [ -n "${NOTION_API_KEY:-}" ] && command -v curl >/dev/null 2>&1; }

notion_find_parent() {
  # Search for "zhc" page; fall back to "Channel Playbooks"
  local q resp id
  for q in "zhc" "Channel Playbooks"; do
    resp="$(curl -s -X POST "https://api.notion.com/v1/search" \
      -H "Authorization: Bearer $NOTION_API_KEY" \
      -H "Notion-Version: $NOTION_VERSION" \
      -H "Content-Type: application/json" \
      -d "{\"query\":\"$q\",\"filter\":{\"property\":\"object\",\"value\":\"page\"}}" 2>/dev/null || echo '')"
    id="$(printf '%s' "$resp" | sed -n 's/.*"id":"\([a-f0-9-]\{36\}\)".*/\1/p' | head -1)"
    if [ -n "$id" ]; then
      echo "$id"
      return 0
    fi
  done
  return 1
}

notion_create_page() {
  local parent_id="$1" title="$2" body="$3"
  local body_escaped
  body_escaped="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || printf '"%s"' "${body//\"/\\\"}")"
  curl -s -X POST "https://api.notion.com/v1/pages" \
    -H "Authorization: Bearer $NOTION_API_KEY" \
    -H "Notion-Version: $NOTION_VERSION" \
    -H "Content-Type: application/json" \
    -d "{\"parent\":{\"page_id\":\"$parent_id\"},\"properties\":{\"title\":[{\"text\":{\"content\":\"$title\"}}]},\"children\":[{\"object\":\"block\",\"type\":\"paragraph\",\"paragraph\":{\"rich_text\":[{\"type\":\"text\",\"text\":{\"content\":$body_escaped}}]}}]}" \
    | sed -n 's/.*"id":"\([a-f0-9-]\{36\}\)".*/\1/p' | head -1
}

# -------- Substitute placeholders into template --------
render_template() {
  local channel="$1"
  sed \
    -e "s|<Channel>|$channel|g" \
    -e "s|<CHANNEL_NAME>|$channel|g" \
    -e "s|<Client Name>|$CLIENT_BUSINESS_NAME|g" \
    -e "s|<CLIENT_BUSINESS_NAME>|$CLIENT_BUSINESS_NAME|g" \
    -e "s|<ESCALATION_TARGET>|$ESCALATION_TARGET|g" \
    "$TEMPLATE_PATH"
}

# -------- Main loop --------
PARENT_ID=""
if notion_available; then
  PARENT_ID="$(notion_find_parent || true)"
  if [ -z "$PARENT_ID" ]; then
    echo "[WARN] could not locate a Notion parent (zhc or Channel Playbooks); falling back to markdown"
  fi
fi

for ch in "${CHANNELS[@]}"; do
  md_path="$OUT_DIR/$ch.md"
  id_path="$OUT_DIR/$ch--notion-id.txt"

  if [ -s "$id_path" ] || [ -s "$md_path" ]; then
    echo "[SKIP] $ch (already scaffolded)"
    continue
  fi

  body="$(render_template "$ch")"
  # U-5: every scaffolded channel playbook references the house default persona.
  body="$(add_persona_line "$body")"

  if [ -n "$PARENT_ID" ]; then
    new_id="$(notion_create_page "$PARENT_ID" "$ch Communication Playbook — $CLIENT_BUSINESS_NAME" "$body" || true)"
    if [ -n "$new_id" ]; then
      printf '%s\n' "$new_id" > "$id_path"
      echo "[OK] $ch → Notion page $new_id"
      continue
    else
      echo "[WARN] Notion create failed for $ch; falling back to markdown"
    fi
  fi

  printf '%s\n' "$body" > "$md_path"
  echo "[OK] $ch → $md_path"
done

echo ""
echo "Scaffold complete. Output dir: $OUT_DIR"
