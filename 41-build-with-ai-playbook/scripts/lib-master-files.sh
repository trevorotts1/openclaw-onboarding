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
  # Remaining positional args are jq --arg key value pairs, last arg is the jq object expression
  # Caller passes discrete fields; we build the JSONL line with jq to avoid injection.
  # Usage: append_jsonl <event_type> <jq-object-expr> [--arg key val ...]
  # We use a different calling convention: caller passes a pre-built jq object string and
  # extra --arg pairs via eval-safe approach.  For backward compat the second arg is
  # interpreted as a jq expression that may reference $-variables supplied in remaining args.
  local jq_expr="$2"
  shift 2
  local master_dir
  master_dir="$(resolve_master_files_dir)"
  # Durability guard: ensure the sink dir exists + is writable. A missing or read-only
  # MASTER_FILES_DIR must surface a loud operator WARNING, never silently drop the event
  # (and must not abort a `set -e` caller mid-create).
  if [[ ! -d "$master_dir" ]] && ! mkdir -p "$master_dir" 2>/dev/null; then
    echo "[skill 41] WARNING: cannot create MASTER_FILES_DIR '$master_dir' -- event '$event_type' NOT logged" >&2
    return 0
  fi
  local events_file="$master_dir/build-with-ai-events.jsonl"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local session_ref
  if [[ -n "${SESSION_REF:-}" ]]; then
    session_ref="$SESSION_REF"
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    local _ns
    _ns="$(python3 -c 'import time;print(int(time.time()*1000)%1000000)' 2>/dev/null || true)"
    session_ref="sess_${_ns:-$RANDOM$RANDOM}"
  else
    session_ref="sess_$(date +%s%N | tail -c 6)"
  fi
  local line
  # A jq failure (bad jq_expr / --arg) leaves $line empty; appending that would write a BLANK
  # line into the strict-JSONL sink (printf still returns 0, so the write guard below would be
  # bypassed) -- log pollution / corruption. Guard on both jq success AND a non-empty line.
  if ! line="$(jq -nc \
    --arg ts "$ts" \
    --arg event_type "$event_type" \
    --arg session_ref "$session_ref" \
    "$@" \
    "{ts:\$ts,skill:\"41-build-with-ai-playbook\",event:\$event_type,session_ref:\$session_ref,source:\"script\"} + ($jq_expr)")" || [[ -z "$line" ]]; then
    echo "[skill 41] WARNING: could not build event '$event_type' (jq error) -- NOT logged, sink left clean" >&2
    return 0
  fi
  if ! printf '%s\n' "$line" >> "$events_file" 2>/dev/null; then
    echo "[skill 41] WARNING: cannot write '$events_file' -- event '$event_type' NOT logged" >&2
    return 0
  fi
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
