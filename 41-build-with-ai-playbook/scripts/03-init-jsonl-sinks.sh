#!/usr/bin/env bash
# 03-init-jsonl-sinks.sh -- Skill 41 Build With AI Playbook Generator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-master-files.sh"

MASTER_FILES_DIR="$(resolve_master_files_dir)"
EVENTS_FILE="$MASTER_FILES_DIR/build-with-ai-events.jsonl"
SCHEMA_FILE="$MASTER_FILES_DIR/build-with-ai-events.schema.json"

echo "[skill 41] Initializing JSONL sinks..."

# Create events log if not exists
if [[ ! -f "$EVENTS_FILE" ]]; then
  touch "$EVENTS_FILE"
  echo "[skill 41] Created $EVENTS_FILE"
else
  echo "[skill 41] $EVENTS_FILE already exists"
fi

# Create schema sidecar if not exists
if [[ ! -f "$SCHEMA_FILE" ]]; then
  cat > "$SCHEMA_FILE" << 'SCHEMAEOF'
{
  "skill": "41-build-with-ai-playbook",
  "file": "build-with-ai-events.jsonl",
  "format": "jsonl",
  "common_fields": {
    "ts": "ISO-8601 UTC timestamp",
    "skill": "string -- always 41-build-with-ai-playbook",
    "event": "string -- event type",
    "session_ref": "string -- opaque session reference",
    "source": "string -- data origin"
  },
  "event_types": {
    "brainstorm_started": {"operator_intent_summary": "string"},
    "dependency_audited": {"missing_tags": "array", "missing_fields": "array", "missing_values": "array"},
    "dependency_created": {"object_type": "tag|field|value", "object_name": "string", "zhc_prefixed": "boolean"},
    "prompt_generated": {"prompt_section_count": "integer", "sections_present": "array"},
    "build_initiated": {"operator_confirmed": "boolean"},
    "build_completed": {"workflow_name": "string", "verification_score": "integer"},
    "verification_failed": {"failed_items": "array", "fix_suggested": "string"},
    "webhook_configured": {"method": "string", "url_domain": "string", "save_response_enabled": "boolean"},
    "conversation_playbook_paired": {"workflow_id": "string", "playbook_path": "string"}
  }
}
SCHEMAEOF
  echo "[skill 41] Created $SCHEMA_FILE"
else
  echo "[skill 41] $SCHEMA_FILE already exists"
fi

echo "[skill 41] JSONL sinks ready"
