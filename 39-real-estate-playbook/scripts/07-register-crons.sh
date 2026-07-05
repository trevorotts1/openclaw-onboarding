#!/usr/bin/env bash
# 07-register-crons.sh — Skill 39
# Registers the two RE maintenance crons via `openclaw cron add` (the supported
# path — the cron.jobs JSON config block does NOT validate). Idempotent: skips a
# cron whose name already exists. If the openclaw CLI is unavailable, prints the
# exact commands for the operator to run and exits 0 (non-fatal).
#
#   re-open-house-followup-scan : daily 18:00  — open-house follow-up sweep
#   re-post-close-anniversary   : daily 09:00  — post-close anniversary / sphere nurture
#
# CRON SHAPE (fix T-39, FIX-XC-08c): the previous version passed `--schedule`
# (a flag that does NOT exist on the current CLI, so registration FAILED) and NO
# payload (a registered job with no message/command fires but does NOTHING). This
# version uses the real `--cron <expr>` flag + a real agent `--message` payload,
# and delivers SILENTLY: on CLI 2026.6.8 `cron add` defaults delivery=announce,
# which would spam the client's chat on every fire (silence-doctrine violation).
# The silent-delivery flag (`--no-deliver`, falling back to `--best-effort-deliver`)
# is FEATURE-DETECTED, with a no-optional-flag retry for older CLI shapes. After a
# successful add each job is VERIFIED present via `openclaw cron list`.

set -uo pipefail
P="[skill 39][crons]"
AGENT_ID="${ROUTING_AGENT_ID:-main}"

declare -a CRON_NAMES=( "re-open-house-followup-scan" "re-post-close-anniversary" )
declare -a CRON_SCHED=( "0 18 * * *"                  "0 9 * * *" )
declare -a CRON_MSG=(
  "Skill 39 daily open-house follow-up sweep. Run protocols/open-house-automation-protocol.md: for every open-house registration captured in the last 7 days that has no logged follow-up yet, send the next timed follow-up step and append one open_house event to <MASTER_FILES_DIR>/real-estate-events.jsonl. Operator-only maintenance - no client-facing chatter beyond the scheduled follow-ups themselves; report back only on error."
  "Skill 39 daily post-close anniversary + sphere-reactivation scan. Identify closings that hit a monthly or annual milestone today, queue the care-first anniversary/sphere touch per protocols/open-house-automation-protocol.md, and append the corresponding events to <MASTER_FILES_DIR>/real-estate-events.jsonl. Operator-only maintenance; report back only on error."
)

# Manual-fallback command string for a given index (real --cron + --message).
manual_cmd() {
  local i="$1"
  printf 'openclaw cron add --name %q --cron %q --agent %q --no-deliver --message %q' \
    "${CRON_NAMES[$i]}" "${CRON_SCHED[$i]}" "$AGENT_ID" "${CRON_MSG[$i]}"
}

if ! command -v openclaw >/dev/null 2>&1; then
  echo "$P openclaw CLI not on PATH — register these manually (non-fatal):"
  for i in "${!CRON_NAMES[@]}"; do
    echo "$P    $(manual_cmd "$i")"
  done
  exit 0
fi

# Feature-detect a flag on `openclaw cron add`.
_cli_supports_flag() { # <flag-name-without-leading-dashes>
  local flag="$1" help
  help="$(openclaw cron add --help 2>&1 || true)"
  printf '%s' "$help" | grep -qE -- "--$flag([[:space:]<=]|$)"
}

# Resolve the silent-delivery flag ONCE (silence-doctrine: never announce a
# maintenance cron to the client's chat). Prefer --no-deliver; fall back to
# --best-effort-deliver; empty if neither exists (the bare retry still registers).
DELIVERY_FLAG=""
if _cli_supports_flag "no-deliver"; then
  DELIVERY_FLAG="--no-deliver"
elif _cli_supports_flag "best-effort-deliver"; then
  DELIVERY_FLAG="--best-effort-deliver"
fi
LIGHT_CTX=""
_cli_supports_flag "light-context" && LIGHT_CTX="--light-context"

# Register one agent-message cron with the real payload + silent delivery, then
# fall back to a no-optional-flag shape. Returns 0 on a successful add.
_add_cron() { # <name> <cron-expr> <message>
  local name="$1" expr="$2" msg="$3"
  local -a opt=()
  [ -n "$DELIVERY_FLAG" ] && opt+=( "$DELIVERY_FLAG" )
  [ -n "$LIGHT_CTX" ] && opt+=( "$LIGHT_CTX" )
  # NOTE: `${opt[@]+"${opt[@]}"}` — safe empty-array expansion under `set -u`
  # (bare "${opt[@]}" is an "unbound variable" error on bash 3.2, macOS default).
  if openclaw cron add --name "$name" --cron "$expr" --agent "$AGENT_ID" ${opt[@]+"${opt[@]}"} --message "$msg" >/dev/null 2>&1; then
    return 0
  fi
  # Older CLI shapes: retry with no optional flags.
  openclaw cron add --name "$name" --cron "$expr" --agent "$AGENT_ID" --message "$msg" >/dev/null 2>&1
}

EXISTING="$(openclaw cron list 2>/dev/null || true)"
for i in "${!CRON_NAMES[@]}"; do
  name="${CRON_NAMES[$i]}"
  if printf '%s' "$EXISTING" | grep -qF "$name"; then
    echo "$P cron '$name' already registered — skipping"
    continue
  fi
  if _add_cron "$name" "${CRON_SCHED[$i]}" "${CRON_MSG[$i]}"; then
    # VERIFY the job is actually registered (payload present, not a phantom add).
    if openclaw cron list 2>/dev/null | grep -qF "$name"; then
      echo "$P registered + verified cron '$name' (${CRON_SCHED[$i]}) ${DELIVERY_FLAG:-<default-delivery>}"
    else
      echo "$P WARN: '$name' add returned success but is NOT in 'cron list' — register manually:"
      echo "$P    $(manual_cmd "$i")"
    fi
  else
    echo "$P WARN: could not register '$name' — run manually:"
    echo "$P    $(manual_cmd "$i")"
  fi
done
exit 0
