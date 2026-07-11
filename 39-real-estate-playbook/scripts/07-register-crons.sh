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
# successful add each job is VERIFIED present via the JSON exact-name match below.
#
# IDEMPOTENCY (fix/industry-gate-and-idempotent-crons, 2026-07-11 — BUG FIX):
# the previous version guarded each add with a TEXT-TABLE `openclaw cron list |
# grep -qF <name>` presence check. `cron list`'s text table truncates names
# longer than ~22 chars (appends "..."); BOTH RE cron names exceed that
# (re-open-house-followup-scan=27, re-post-close-anniversary=25), so the check
# NEVER matched the truncated row and a fresh duplicate was added on every wire
# run (6x incident). Replaced with oc_cron_present() (shared-utils/cron-lib.sh)
# — an exact JSON `.name ==` match against `cron list --json`, the same fix
# scripts/ensure-pipeline-crons.sh already shipped (v13.0.2) for its own crons.
#
# INDUSTRY GATE (FAIL CLOSED): registers NOTHING unless this box's captured
# industry is real-estate (shared-utils/industry-gate.sh). Independent of the
# gate in 00-verify-prerequisites.sh / wire.sh so a direct/manual invocation of
# this registrar can never create RE crons on a non-RE box even if wire.sh is
# bypassed.

set -uo pipefail
P="[skill 39][crons]"
AGENT_ID="${ROUTING_AGENT_ID:-main}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---- INDUSTRY GATE (FAIL CLOSED) -------------------------------------------
_GATE_LIB=""
for _cand in \
  "$SKILL_ROOT/../shared-utils/industry-gate.sh" \
  "$(cd "$SKILL_ROOT/.." 2>/dev/null && pwd)/shared-utils/industry-gate.sh" \
  "${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/industry-gate.sh" \
  "/data/.openclaw/skills/shared-utils/industry-gate.sh"; do
  if [ -f "$_cand" ]; then
    _GATE_LIB="$_cand"
    break
  fi
done
if [ -z "$_GATE_LIB" ]; then
  echo "$P BLOCKED: shared-utils/industry-gate.sh not found — FAIL CLOSED: registering NOTHING (absence is never permission)."
  exit 0
fi
# shellcheck source=/dev/null
. "$_GATE_LIB"
if ! oc_is_real_estate_industry; then
  echo "$P SKIP — box industry is not real estate ($OC_INDUSTRY_GATE_REASON). Registering NOTHING (fail closed)."
  exit 0
fi
echo "$P industry gate PASS ($OC_INDUSTRY_GATE_REASON) — proceeding to register RE crons"

# ---- JSON-idempotency helper (oc_cron_present) -----------------------------
_CRON_LIB=""
for _cand in \
  "$SKILL_ROOT/../shared-utils/cron-lib.sh" \
  "$(cd "$SKILL_ROOT/.." 2>/dev/null && pwd)/shared-utils/cron-lib.sh" \
  "${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/skills}/shared-utils/cron-lib.sh" \
  "/data/.openclaw/skills/shared-utils/cron-lib.sh"; do
  if [ -f "$_cand" ]; then
    _CRON_LIB="$_cand"
    break
  fi
done
if [ -z "$_CRON_LIB" ]; then
  echo "$P FATAL: shared-utils/cron-lib.sh not found — refusing to register crons without the truncation-safe idempotency check (would risk re-introducing the 6x-duplicate bug)."
  exit 0
fi
# shellcheck source=/dev/null
. "$_CRON_LIB"

declare -a CRON_NAMES=( "re-open-house-followup-scan" "re-post-close-anniversary" )
# Minute jitter (Fix C, belt-and-suspenders): a deterministic 0-14 min offset
# derived from hostname+name keeps the two distinct hours (18/09) but spreads
# the exact minute across the fleet so many boxes don't all fire at :00.
_JIT1="$(oc_cron_minute_jitter "${CRON_NAMES[0]}" 15)"
_JIT2="$(oc_cron_minute_jitter "${CRON_NAMES[1]}" 15)"
declare -a CRON_SCHED=( "${_JIT1} 18 * * *"           "${_JIT2} 9 * * *" )
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

for i in "${!CRON_NAMES[@]}"; do
  name="${CRON_NAMES[$i]}"
  # DURABLE TOMBSTONE (2026-07-11 live-VPS finding): a cron an operator/tool
  # deliberately disabled/removed via scripts/tombstone-cron.sh must NEVER be
  # resurrected here — checked BEFORE the presence check because a disabled
  # job may be genuinely invisible to `cron list --json` on this CLI build
  # (see shared-utils/cron-lib.sh header). This is the guarantee that holds
  # regardless of what the CLI does or doesn't expose.
  if oc_cron_tombstoned "$name"; then
    echo "$P cron '$name' is TOMBSTONED (deliberately removed) — skipping, NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove '$name'"
    continue
  fi
  # JSON exact-name match (truncation-safe) — see cron-lib.sh header for why a
  # text-table grep here re-introduces the 6x-duplicate bug on long names.
  if oc_cron_present "$name"; then
    echo "$P cron '$name' already registered — skipping"
    continue
  fi
  if _add_cron "$name" "${CRON_SCHED[$i]}" "${CRON_MSG[$i]}"; then
    # VERIFY the job is actually registered (payload present, not a phantom add).
    if oc_cron_present "$name"; then
      echo "$P registered + verified cron '$name' (${CRON_SCHED[$i]}) ${DELIVERY_FLAG:-<default-delivery>}"
    else
      echo "$P WARN: '$name' add returned success but is NOT in 'cron list --json' — register manually:"
      echo "$P    $(manual_cmd "$i")"
    fi
  else
    echo "$P WARN: could not register '$name' — run manually:"
    echo "$P    $(manual_cmd "$i")"
  fi
done
exit 0
