#!/usr/bin/env bash
# cron-lib.sh — shared helpers for idempotent `openclaw cron` presence checks.
#
# WHY THIS EXISTS (fix/industry-gate-and-idempotent-crons, 2026-07-11):
# `openclaw cron list`'s TEXT TABLE truncates names longer than ~22 chars
# (appends "..."). A positive-presence check via `grep -qF "<full-name>"`
# against that text table FALSE-NEGATIVES on any longer name — the guard thinks
# the cron is absent and a duplicate is registered on every re-run/wire. This is
# the confirmed root cause of the 6x-duplicate-cron incident in the
# real-estate-playbook (Skill 39: re-open-house-followup-scan,
# re-post-close-anniversary) and the conversational-ai-system (Skill 38:
# conversation-log-summarizer, proactive-suggestions-scan, etc.) — every one of
# those names exceeds ~22 chars.
#
# scripts/ensure-pipeline-crons.sh already fixed this for its own registrars in
# v13.0.2 (JSON exact-name match, no text-table fallback). This file extracts
# and generalizes that helper (`_cron_present` there -> `oc_cron_present` here)
# so every OTHER registrar can share the fix instead of re-copy-pasting the
# buggy text-grep. scripts/ensure-pipeline-crons.sh is left untouched (it is
# already correct and is the reference implementation this file mirrors).
#
# USAGE: `source` this file, then call `oc_cron_present "<name>"` in place of
#   `openclaw cron list | grep -q "<name>"`. Returns 0 = present, 1 = absent
#   (or list unreadable — callers should then attempt registration).
#
# bash-not-zsh.

# oc_cron_present <name>
#
# Exact JSON `.name == <name>` match against `openclaw cron list --json`.
# Strategy (most to least reliable):
#   1. jq      — exact match against `--json` output.
#   2. python3 — same, via json.load (no jq dependency).
#   3. NEVER falls back to a positive text-table match — that is the root-cause
#      path. If neither JSON parser is available, fails OPEN (returns 1 =
#      "treat as absent") so callers re-attempt registration rather than
#      silently claiming false presence off a possibly-truncated table.
oc_cron_present() {
  local name="$1"
  local raw
  raw=$(openclaw cron list --json 2>/dev/null) || raw=""

  if [[ -n "$raw" ]] && command -v jq >/dev/null 2>&1; then
    if printf '%s' "$raw" | jq -e --arg n "$name" '
        ( if type == "array" then . else .jobs // [] end )
        | map(select(.name == $n))
        | length > 0
      ' >/dev/null 2>&1; then
      return 0
    else
      return 1
    fi
  fi

  if [[ -n "$raw" ]] && command -v python3 >/dev/null 2>&1; then
    # NOTE: JSON is passed via env var, not a pipe — `python3 -` already reads
    # its OWN script text from stdin via the heredoc below, so a pipe feeding
    # the SAME stdin would be silently overridden (shellcheck SC2259) and
    # `sys.stdin.read()` inside the script would see EOF, not the JSON.
    if OC_CRON_RAW="$raw" python3 - "$name" 2>/dev/null <<'PYEOF'
import json, os, sys
name = sys.argv[1]
raw = os.environ.get("OC_CRON_RAW", "")
try:
    data = json.loads(raw)
except Exception:
    sys.exit(1)
jobs = data if isinstance(data, list) else data.get("jobs", [])
sys.exit(0 if any(j.get("name") == name for j in jobs) else 1)
PYEOF
    then
      return 0
    else
      return 1
    fi
  fi

  echo "[cron-lib] WARN oc_cron_present($name): jq and python3 both unavailable — cannot do a JSON exact-name match; failing OPEN (treat as absent) rather than risk a truncation false-positive from text-table grep." >&2
  return 1
}

# oc_cron_minute_jitter <name> <max-minutes (default 15)>
#
# Deterministic 0..(max-1) minute offset derived from this box's hostname +
# the cron name — STABLE across repeated installs/wires on the SAME box (never
# re-randomizes and so never itself causes a reschedule-diff loop), but differs
# box-to-box. Used so daily/hourly crons sharing a base schedule across the
# fleet don't all fire in the exact same wall-clock minute against a shared
# backend (belt-and-suspenders once Fix B has already made duplicates
# impossible by construction).
oc_cron_minute_jitter() {
  local name="$1" max="${2:-15}"
  case "$max" in ''|*[!0-9]*) max=15 ;; esac
  [[ "$max" -lt 1 ]] && max=1
  local seed hash
  seed="$(hostname 2>/dev/null || echo box)-$name"
  hash=$(printf '%s' "$seed" | cksum | awk '{print $1}')
  echo $(( hash % max ))
}
