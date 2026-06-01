#!/usr/bin/env bash
# lib-master-files.sh -- Shared helpers for Skill 41 Build With AI Playbook Generator
# Resolution precedence matches 01-locate: env > skill-41 pointer > skill-38 pointer > OS default.
# Pointers are READ (head/cat), never sourced.

resolve_master_files_dir() {
  if [[ -n "${MASTER_FILES_DIR:-}" && -d "${MASTER_FILES_DIR:-}" ]]; then
    echo "$MASTER_FILES_DIR"; return 0
  fi
  local p41="$HOME/.openclaw/.skill-41-master-files-dir"
  local p38="$HOME/.openclaw/.skill-38-master-files-dir"
  local d
  if [[ -f "$p41" ]]; then
    d="$(head -n1 "$p41" | tr -d '\r')"
    [[ -d "$d" ]] && { echo "$d"; return 0; }
  fi
  if [[ -f "$p38" ]]; then
    d="$(head -n1 "$p38" | tr -d '\r')"
    [[ -d "$d" ]] && { echo "$d"; return 0; }
  fi
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "$HOME/Downloads/OpenClaw Master Files"
  else
    echo "/data/openclaw-master-files"
  fi
}

append_jsonl() {
  local event_type="$1"
  local payload="$2"
  local master_dir
  master_dir="$(resolve_master_files_dir)"
  local events_file="$master_dir/build-with-ai-events.jsonl"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local session_ref
  session_ref="${SESSION_REF:-sess_$(date +%s%N | tail -c 6)}"
  local line
  line="{\"ts\":\"$ts\",\"skill\":\"41-build-with-ai-playbook\",\"event\":\"$event_type\",\"session_ref\":\"$session_ref\",\"source\":\"script\",$payload}"
  echo "$line" >> "$events_file"
}

backup_core_files() {
  local workspace_root="$1"
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  local file src
  for file in AGENTS.md MEMORY.md TOOLS.md; do
    src="$workspace_root/$file"
    [[ -f "$src" ]] && cp "$src" "$src.bak-pre-skill41-$ts"
  done
  echo "[skill 41] Core files backed up with timestamp $ts"
}
