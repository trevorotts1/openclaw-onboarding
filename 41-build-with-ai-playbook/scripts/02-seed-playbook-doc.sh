#!/usr/bin/env bash
# 02-seed-playbook-doc.sh -- Skill 41 Build With AI Playbook Generator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-master-files.sh"

MASTER_FILES_DIR="$(resolve_master_files_dir)"
PLAYBOOK_PATH="$MASTER_FILES_DIR/build-with-ai-playbook.md"

echo "[skill 41] Seeding build-with-ai-playbook.md..."

if [[ -f "$PLAYBOOK_PATH" ]]; then
  echo "[skill 41] Playbook already exists at $PLAYBOOK_PATH -- skipping"
  exit 0
fi

cat > "$PLAYBOOK_PATH" << 'PLAYBOOKEOF'
# Build With AI Playbook

## When to use this playbook

When the operator asks to build a GoHighLevel or Convert and Flow workflow or automation using AI.

## Steps

1. Read protocols/build-with-ai-protocol.md (skill-bundled)
2. Brainstorm: summarize intent, ask smart gaps, confirm with YES
3. Dependency audit: list all tags, custom fields, custom values the workflow will reference
4. Create dependencies FIRST via GHL API (ZHC- tags, ZHC_ fields)
5. Generate the standardized 8-section Build With AI prompt
6. Direct operator to paste into GHL Workflow AI Builder (Automations > Build using AI)
7. Run 12-point verification checklist after build
8. Log to build-with-ai-events.jsonl

## Quick reference

- Prompt template: templates/build-with-ai-prompt-template.md
- Dependency creation: protocols/dependency-creation-protocol.md
- Verification checklist: protocols/verification-checklist.md
- Webhook config: protocols/webhook-configuration-protocol.md
- Triggers catalog: references/ghl-triggers-catalog.md
- Actions catalog: references/ghl-actions-catalog.md
PLAYBOOKEOF

echo "[skill 41] Playbook seeded at $PLAYBOOK_PATH"
