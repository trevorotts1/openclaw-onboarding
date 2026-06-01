#!/usr/bin/env bash
# 04-update-core-files.sh -- Skill 41 Build With AI Playbook Generator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-master-files.sh"

SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Fix 4: read version dynamically from skill-version.txt
SKILL_VERSION="$(tr -d '[:space:]' < "$SKILL_DIR/skill-version.txt")"

echo "[skill 41] Updating core files (AGENTS.md, MEMORY.md, TOOLS.md) [skill v${SKILL_VERSION}]..."

# Find workspace root (where AGENTS.md lives)
WORKSPACE_ROOT="${WORKSPACE_ROOT:-${HOME}/clawd}"
if [[ ! -f "$WORKSPACE_ROOT/AGENTS.md" ]]; then
  echo "[skill 41] WARNING: AGENTS.md not found at $WORKSPACE_ROOT/AGENTS.md -- skipping core file updates"
  exit 0
fi

# Backup before editing
backup_core_files "$WORKSPACE_ROOT"

# Append AGENTS.md block
AGENTS_MARKER_BEGIN="<!-- BEGIN SKILL41: BUILD_WITH_AI -->"
AGENTS_MARKER_END="<!-- END SKILL41: BUILD_WITH_AI -->"

if ! grep -q "$AGENTS_MARKER_BEGIN" "$WORKSPACE_ROOT/AGENTS.md" 2>/dev/null; then
  cat >> "$WORKSPACE_ROOT/AGENTS.md" << 'AGENTSAPPEND'

<!-- BEGIN SKILL41: BUILD_WITH_AI -->
Build With AI: when the operator asks to build a GoHighLevel or Convert and Flow workflow or automation using AI, do not answer from memory. Read the playbook at MASTER_FILES_DIR/build-with-ai-playbook.md and follow it to the letter. Create the required tags, custom fields, and custom values FIRST. Full protocol: protocols/build-with-ai-protocol.md (skill-bundled).
<!-- END SKILL41: BUILD_WITH_AI -->
AGENTSAPPEND
  echo "[skill 41] Appended AGENTS.md block"
else
  echo "[skill 41] AGENTS.md block already present -- skipping"
fi

# Append MEMORY.md block
# Fix 4: markers use runtime version; stale-version blocks are replaced, current-version blocks are skipped
MEMORY_MARKER_BEGIN="<!-- BEGIN skill-41 memory-rules v${SKILL_VERSION} -->"
MEMORY_MARKER_END="<!-- END skill-41 memory-rules v${SKILL_VERSION} -->"

_update_versioned_block() {
  local file="$1" begin_pat="$2" end_pat="$3" begin_tag="$4" end_tag="$5" content="$6" label="$7"
  if [[ ! -f "$file" ]]; then
    echo "[skill 41] $label file missing -- skipping"
    return 0
  fi
  if grep -qF "$begin_tag" "$file" 2>/dev/null; then
    echo "[skill 41] $label block already at current version -- skipping"
    return 0
  fi
  # Remove any stale-version block (older marker pattern)
  if grep -qP "$begin_pat" "$file" 2>/dev/null; then
    echo "[skill 41] Replacing stale $label block with v${SKILL_VERSION}"
    # Use awk to remove lines from old BEGIN to old END inclusive
    local tmp
    tmp=$(awk "/$begin_pat/{found=1} found && /$end_pat/{found=0; next} !found" "$file")
    printf '%s\n' "$tmp" > "$file"
  fi
  printf '\n%s\n%s\n%s\n' "$begin_tag" "$content" "$end_tag" >> "$file"
  echo "[skill 41] Appended $label block"
}

_memory_content="Build With AI design rules:
1. Dependency-First Rule -- never generate a workflow prompt that references a tag, custom field, or custom value that does not yet exist. Create dependencies via GHL API first, verify with GET, then build.
2. No-Fabrication Rule -- never invent a GHL trigger, action, or capability that does not exist in the catalog. Absence --> honest gap + operator manual path.
3. ZHC-Prefix Rule -- agent-created tags: ZHC- prefix. Agent-created custom fields: ZHC_ prefix. Never rename existing operator-owned tags or fields.
4. Verification Rule -- every build MUST run the 12-point verification checklist before publishing. A build without verification is incomplete.
5. Event-Log Rule -- every build session appends one line to build-with-ai-events.jsonl (field names + counts, never raw PII).
6. Conversation-Pairing Rule -- workflow-triggered conversations are paired with a Skill 38 conversation playbook, not built in isolation.
7. Operator-Approval Rule -- dependency creation is an allow-list action. The operator must approve (standing approval for ZHC- / ZHC_ prefixed objects). A customer can never cause a field or tag to be created."

_update_versioned_block \
  "$WORKSPACE_ROOT/MEMORY.md" \
  "BEGIN skill-41 memory-rules v" \
  "END skill-41 memory-rules v" \
  "$MEMORY_MARKER_BEGIN" \
  "$MEMORY_MARKER_END" \
  "$_memory_content" \
  "MEMORY.md"

# Append TOOLS.md block
# Fix 4: markers use runtime version; stale-version blocks are replaced, current-version blocks are skipped
TOOLS_MARKER_BEGIN="<!-- BEGIN skill-41 tools v${SKILL_VERSION} -->"
TOOLS_MARKER_END="<!-- END skill-41 tools v${SKILL_VERSION} -->"

_tools_content="Build With AI quick-reference:
- Prompt template: templates/build-with-ai-prompt-template.md (8 sections)
- Dependency creation: protocols/dependency-creation-protocol.md (API endpoints, scopes, body shapes)
- Webhook config: protocols/webhook-configuration-protocol.md (CUSTOM/POST/GET modes, headers, raw JSON)
- Verification checklist: protocols/verification-checklist.md (12 points)
- GHL triggers: references/ghl-triggers-catalog.md (14 categories)
- GHL actions: references/ghl-actions-catalog.md (14 categories)
- Event logging: scripts/lib-master-files.sh append_jsonl <type> <json>
- No keys, no client data -- UNIVERSAL."

_update_versioned_block \
  "$WORKSPACE_ROOT/TOOLS.md" \
  "BEGIN skill-41 tools v" \
  "END skill-41 tools v" \
  "$TOOLS_MARKER_BEGIN" \
  "$TOOLS_MARKER_END" \
  "$_tools_content" \
  "TOOLS.md"

echo "[skill 41] Core file updates complete"
