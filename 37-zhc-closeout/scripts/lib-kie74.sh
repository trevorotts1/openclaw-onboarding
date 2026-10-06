#!/usr/bin/env bash
# lib-kie74.sh - Skill 37's one KIE path: every KIE call is Skill 74's CLI
# (74-kie-live-adapter/scripts/kie_live_adapter.py ... --mode active --json).
# Skill 37 keeps its own policy (model order, prompts, 8.5 gate, state fields, receipts); it has no
# submit, poll, upload or download code of its own. Source this file, then call kie74_locate.
#
# Needs the caller's log() (level, message), jq and python3. Never prints the key (Skill 74 reads
# KIE_API_KEY from the environment or the shared key resolver itself).
#
#   kie74_locate                       -> sets KIE74_PY, or logs and returns 1 when Skill 74 is not installed
#   kie74_image_url MODEL PROMPT [SEC] -> sets KIE74_URL (first result URL) and returns 0; on failure sets
#                                         KIE74_ERR and returns 1 (call it directly, not in $(...), so both survive)
#   kie74_upload_file PATH             -> prints a public KIE URL for a local file (retried), or returns 1
#   kie74_upload_url URL               -> prints a fresh KIE-hosted URL for a public URL (retried), or returns 1
#   kie74_run REQUEST_FILE SAVE_DIR SEC-> prints Skill 74's `run` JSON; returns 0 on state=success

# Test hooks (localhost only; Skill 74 refuses any other host): the pre-consolidation names are still honored.
[[ -n "${KIE_API_BASE:-}" && -z "${KIE_LIVE_API_BASE:-}" ]] && export KIE_LIVE_API_BASE="$KIE_API_BASE"
[[ -n "${KIE_UPLOAD_BASE:-}" && -z "${KIE_LIVE_UPLOAD_BASE:-}" ]] && export KIE_LIVE_UPLOAD_BASE="$KIE_UPLOAD_BASE"

KIE74_PY=""
KIE74_ERR=""
KIE74_URL=""

_kie74_log() { if declare -F log >/dev/null 2>&1; then log "$1" "$2"; else printf '[kie74] %s %s\n' "$1" "$2" >&2; fi; }

kie74_locate() {
  local here root cand
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  for root in "$here" "${OPENCLAW_SKILLS_DIR:-}" "${OC_ROOT:-}/skills" "$HOME/.openclaw/skills" "/data/.openclaw/skills"; do
    [[ -n "$root" ]] || continue
    cand="$root/74-kie-live-adapter/scripts/kie_live_adapter.py"
    if [[ -f "$cand" ]]; then KIE74_PY="$cand"; return 0; fi
  done
  _kie74_log "ERROR" "Skill 74 (74-kie-live-adapter, the single KIE transport) is not installed; Skill 37 has no KIE client of its own and will not fall back to one. Install or update it (update-skills.sh)."
  return 1
}

# _kie74 <cli args...>: run the CLI in active mode, print its JSON, never fail the shell.
_kie74() { python3 "$KIE74_PY" "$@" --mode active --json 2>/dev/null || true; }

# _kie74_error <json>: a short "code msg" string from a failed result (or the raw start of the output).
_kie74_error() {
  local e
  e=$(printf '%s' "$1" | jq -r '"\(.error.code // "") \(.error.msg // "")"' 2>/dev/null)
  [[ -n "${e// /}" ]] || e="$(printf '%s' "$1" | head -c 300)"
  printf '%s' "${e:0:300}"
}

kie74_image_url() {
  local model="$1" prompt="$2" timeout="${3:-600}" req out task_id url
  KIE74_URL=""; KIE74_ERR=""
  req="$(mktemp "${TMPDIR:-/tmp}/zhc-kie74-req.XXXXXX")"
  jq -n --arg model "$model" --arg prompt "$prompt" \
    '{model: $model, input: {prompt: $prompt, aspect_ratio: "16:9", resolution: "2K", output_format: "png"}}' > "$req"
  out=$(_kie74 submit --request "$req")
  rm -f "$req"
  task_id=$(printf '%s' "$out" | jq -r '.task_id // empty' 2>/dev/null)
  if [[ -z "$task_id" ]]; then KIE74_ERR="$(_kie74_error "$out")"; return 1; fi
  out=$(_kie74 wait --task-id "$task_id" --timeout "$timeout")
  url=$(printf '%s' "$out" | jq -r 'if .state == "success" then (.result_urls[0] // empty) else empty end' 2>/dev/null)
  if [[ -z "$url" ]]; then KIE74_ERR="job $task_id: $(_kie74_error "$out")"; return 1; fi
  KIE74_URL="$url"
}

# _kie74_retry <attempts> <cli args...>: retries only transport-class failures (network, 429, 5xx).
_kie74_retry() {
  local attempts="$1" i out code; shift
  for (( i=1; i<=attempts; i++ )); do
    out=$(_kie74 "$@")
    if [[ "$(printf '%s' "$out" | jq -r '.state // empty' 2>/dev/null)" == "success" ]]; then printf '%s' "$out"; return 0; fi
    code=$(printf '%s' "$out" | jq -r '.error.code // empty' 2>/dev/null)
    case "$code" in
      network|429|5??|"") _kie74_log "WARN" "kie74 $1: transient failure (code=${code:-none}, attempt $i/$attempts); retrying"; sleep $(( i * i * 2 )) ;;
      *) KIE74_ERR="$(_kie74_error "$out")"; _kie74_log "WARN" "kie74 $1: non-retryable: $KIE74_ERR"; return 1 ;;
    esac
  done
  KIE74_ERR="exhausted $attempts attempts"
  return 1
}

kie74_upload_file() {
  local src="$1" tmpd named out url rc
  [[ -s "$src" ]] || { _kie74_log "WARN" "ref-upload: local file missing/empty: $src"; return 1; }
  tmpd="$(mktemp -d "${TMPDIR:-/tmp}/zhc-kie74-up.XXXXXX")"
  named="$tmpd/zhc-ref-$(date -u +%s)-$(basename "$src")"
  cp "$src" "$named"
  out=$(_kie74_retry 4 upload --file "$named" --upload-path "images/zhc-closeout"); rc=$?
  rm -rf "$tmpd"
  (( rc == 0 )) || return 1
  url=$(printf '%s' "$out" | jq -r '.data.download_url // empty' 2>/dev/null)
  [[ "$url" == http* ]] || { _kie74_log "WARN" "ref-upload: no download_url in result"; return 1; }
  printf '%s' "$url"
}

kie74_upload_url() {
  local out url
  out=$(_kie74_retry 4 upload --url "$1" --upload-path "images/zhc-closeout") || return 1
  url=$(printf '%s' "$out" | jq -r '.data.download_url // empty' 2>/dev/null)
  [[ "$url" == http* ]] || { _kie74_log "WARN" "ref-rehost: no download_url in result"; return 1; }
  printf '%s' "$url"
}

kie74_run() {
  local out
  out=$(_kie74 run --request "$1" --save-dir "$2" --timeout "$3")
  printf '%s' "$out"
  [[ "$(printf '%s' "$out" | jq -r '.state // empty' 2>/dev/null)" == "success" ]]
}
