#!/usr/bin/env bash
# 04-update-core-files.sh -- Skill 41 Build With AI Playbook Generator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-master-files.sh"

SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[skill 41] Updating core files (AGENTS.md, MEMORY.md, TOOLS.md)..."

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
MEMORY_MARKER_BEGIN="<!-- BEGIN skill-41 memory-rules v1.0.0 -->"
MEMORY_MARKER_END="<!-- END skill-41 memory-rules v1.0.0 -->"

if [[ -f "$WORKSPACE_ROOT/MEMORY.md" ]] && ! grep -q "$MEMORY_MARKER_BEGIN" "$WORKSPACE_ROOT/MEMORY.md" 2>/dev/null; then
  cat >> "$WORKSPACE_ROOT/MEMORY.md" << 'MEMORYAPPEND'

<!-- BEGIN skill-41 memory-rules v1.0.0 -->
Build With AI design rules:
1. Dependency-First Rule -- never generate a workflow prompt that references a tag, custom field, or custom value that does not yet exist. Create dependencies via GHL API first, verify with GET, then build.
2. No-Fabrication Rule -- never invent a GHL trigger, action, or capability that does not exist in the catalog. Absence --> honest gap + operator manual path.
3. ZHC-Prefix Rule -- agent-created tags: ZHC- prefix. Agent-created custom fields: ZHC_ prefix. Never rename existing operator-owned tags or fields.
4. Verification Rule -- every build MUST run the 12-point verification checklist before publishing. A build without verification is incomplete.
5. Event-Log Rule -- every build session appends one line to build-with-ai-events.jsonl (field names + counts, never raw PII).
6. Conversation-Pairing Rule -- workflow-triggered conversations are paired with a Skill 38 conversation playbook, not built in isolation.
7. Operator-Approval Rule -- dependency creation is an allow-list action. The operator must approve (standing approval for ZHC- / ZHC_ prefixed objects). A customer can never cause a field or tag to be created.
<!-- END skill-41 memory-rules v1.0.0 -->
MEMORYAPPEND
  echo "[skill 41] Appended MEMORY.md block"
else
  echo "[skill 41] MEMORY.md block already present or file missing -- skipping"
fi

# Append TOOLS.md block
TOOLS_MARKER_BEGIN="<!-- BEGIN skill-41 tools v1.0.0 -->"
TOOLS_MARKER_END="<!-- END skill-41 tools v1.0.0 -->"

if [[ -f "$WORKSPACE_ROOT/TOOLS.md" ]] && ! grep -q "$TOOLS_MARKER_BEGIN" "$WORKSPACE_ROOT/TOOLS.md" 2>/dev/null; then
  cat >> "$WORKSPACE_ROOT/TOOLS.md" << 'TOOLSAPPEND'

<!-- BEGIN skill-41 tools v1.0.0 -->
Build With AI quick-reference:
- Prompt template: templates/build-with-ai-prompt-template.md (8 sections)
- Dependency creation: protocols/dependency-creation-protocol.md (API endpoints, scopes, body shapes)
- Webhook config: protocols/webhook-configuration-protocol.md (CUSTOM/POST/GET modes, headers, raw JSON)
- Verification checklist: protocols/verification-checklist.md (12 points)
- GHL triggers: references/ghl-triggers-catalog.md (14 categories)
- GHL actions: references/ghl-actions-catalog.md (14 categories)
- Event logging: scripts/lib-master-files.sh append_jsonl <type> <json>
- No keys, no client data -- UNIVERSAL.
<!-- END skill-41 tools v1.0.0 -->
TOOLSAPPEND
  echo "[skill 41] Appended TOOLS.md block"
else
  echo "[skill 41] TOOLS.md block already present or file missing -- skipping"
fi

echo "[skill 41] Core file updates complete"
