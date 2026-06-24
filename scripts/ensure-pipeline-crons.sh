#!/usr/bin/env bash
# ensure-pipeline-crons.sh — SHARED, IDEMPOTENT registrar/backfiller for ALL
# closeout/pipeline trigger crons.
#
# WHY THIS EXISTS (root cause — see ZHC-EXPERIENCE-DIAGNOSIS Part 2/3):
#   The ZHC closeout experience (Skill 37) is fully state-machine-driven and its
#   files ship two independent ways, BUT the only automatic TRIGGER for closeout
#   was a single cron (workforce-build-resume) created in install.sh Step 13. The
#   fleet hot-patch path (update-skills.sh) registered NONE of the pipeline crons,
#   so a box patched only via update-skills.sh got new files but no trigger. And
#   the dedicated closeout-resume cron was only ever self-bootstrapped at runtime
#   by run-closeout.sh — which never runs if the build-resume cron is absent. So
#   the gap cascaded and the closeout silently never fired.
#
#   This script is the SINGLE SOURCE OF TRUTH that asserts the presence of every
#   pipeline trigger cron, registers any that are missing, and prints a one-line
#   audit. It is called by BOTH install.sh (end of run) and update-skills.sh
#   (after the wiring phase) so files AND triggers always land together.
#
# CRONS MANAGED (name-keyed, idempotent):
#   1. workforce-build-resume          (*/15, SILENT main-session) — Skill 23 build resume + closeout exec
#   2. interview-nudge                 (0 */6, COMMAND mode) — owner-facing idle-interview nudge
#   3. closeout-readiness-watchdog     (0 */6, COMMAND mode) — operator-facing stall escalation
#   4. closeout-resume                 (*/15, COMMAND mode)  — DEDICATED closeout trigger (REDUNDANT path)
#   5. index-model-drift-check         (hourly, COMMAND)     — config-vs-index embedding-model drift alarm (EMBEDDING-PREVENTION item 4)
#   6. orphan-temp-sweep               (hourly, COMMAND)     — clears failed-reindex *.sqlite.tmp orphans (item 5)
#   7. disk-usage-alert                (hourly, COMMAND)     — disk >85% alert (item 6)
#   8. pre-july14-embed-migrate        (daily, COMMAND)      — flags any box still on dying gemini-embedding-001 (item 7)
#   9. ghl-token-liveness              (daily 08:00 UTC, COMMAND) — Skills 44+46 Firebase token daily health check; notifies CLIENT if expired
#
# SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons): EVERY cron above is
#   now non-announcing. NONE wires `--channel/--to/--announce`. The COMMAND-mode
#   crons run pure shell (their scripts decide if/where to notify — operator
#   channel or the client via the script's own resolver, never an auto-announce).
#   The one agent-driven cron (workforce-build-resume) runs SILENT on the agent's
#   main session (`--agent main --session-target main --light-context`): the
#   agent works in its own context and surfaces owner-facing status only via its
#   own deliberate `message send`. Result: a fresh box never auto-pushes
#   internal maintenance/build/operator traffic to the CLIENT chat.
#
# REDUNDANCY (closes the single-point-of-failure): closeout fires if ANY of
#   {workforce-build-resume cron, closeout-resume cron, watchdog} reaches the
#   box. The closeout-resume cron is COMMAND mode (`bash resume-closeout-cron.sh`)
#   so it needs NO Telegram owner target — it runs even on a box with no resolved
#   owner chat. That removes the case where "no owner chat yet" silently disabled
#   the entire closeout trigger.
#
# NO OWNER-CHAT DEPENDENCY: because workforce-build-resume is now SILENT (no
#   auto-delivery), it no longer needs a non-operator owner target at all. The
#   old "no owner chat → skip" / operator-ID strand branch is gone — every cron
#   registers regardless of owner-chat resolution. The _resolve_owner_chat /
#   _resolve_channel_account helpers below are retained for any FUTURE
#   owner-facing cron but are no longer used by registrar #1.
#
# IDEMPOTENT: every registration is guarded by `openclaw cron list | grep -q
#   <name>`; safe to call repeatedly. Fail-loud on a true error, near-no-op when
#   everything is already present.
#
# bash-not-zsh (strict glob in zsh aborts silently — always invoke via bash).
#
# EXIT CODES:
#   0  all four crons present (or registered this run)
#   3  one or more crons could NOT be registered (caller should warn; install
#      continues — this is advisory, not fatal, so a partial box is not bricked)
#
# Onboarding repo version markers (kept in sync by scripts/bump-version.sh):
#   ENSURE_PIPELINE_CRONS_VERSION
# BUG-FIX v13.0.2 — JSON presence check, no text-table truncation
# v13.2.0 — EMBEDDING-PREVENTION BUNDLE: wire 4 memory-health crons fleet-wide.
# v13.3.0 — GHL token liveness cron: daily Skills 44+46 Firebase token health check.
ENSURE_PIPELINE_CRONS_VERSION="v13.8.12"

set -u

# ---------------------------------------------------------------------------
# Platform detection — VPS (/data) first, then Mac ($HOME). Mirrors every other
# pipeline script's detection block so paths resolve identically on both.
# ---------------------------------------------------------------------------
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "${HOME}/.openclaw" ]]; then
  OC_ROOT="${HOME}/.openclaw"
else
  echo "[ensure-pipeline-crons] no OpenClaw root found (.openclaw absent) — nothing to wire" >&2
  exit 0
fi

SKILLS_DIR="$OC_ROOT/skills"
STATE_FILE="$OC_ROOT/workspace/.workforce-build-state.json"

# OPERATOR chat ids — MUST match install.sh OPERATOR_CHAT_IDS exactly.
OPERATOR_CHAT_IDS_RE='^(5252140759|6663821679|6771245262)$'

_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null; }

_log() { echo "[ensure-pipeline-crons] $*"; }

# ---------------------------------------------------------------------------
# _cron_present NAME
#
# Returns 0 if a cron with EXACT name NAME exists in `openclaw cron list`,
# returns 1 if absent or list fails.
#
# WHY JSON (BUG-FIX v13.0.2): the text table produced by `openclaw cron list`
# truncates names longer than ~22 chars, appending "...". The cron named
# "closeout-readiness-watchdog" (27 chars) was rendered as
# "closeout-readiness-wa..." in every text-table row, so any grep on the
# full name always returned non-zero (false "absent") — causing the script to
# re-register a duplicate on every run AND to false-negative on the post-
# registration success check (exit 3 even when the cron registered fine).
#
# Strategy (most to least reliable):
#   1. jq  — exact `.jobs[].name` match against `--json` output
#   2. python3 — same but via json.load (no jq dep)
#   3. NEVER fall back to text-table grep — that is the root-cause path.
#      If both jq and python3 are absent we fail OPEN (return 1) so callers
#      attempt re-registration rather than silently claiming presence.
# ---------------------------------------------------------------------------
_cron_present() {
  local name="$1"
  local raw
  raw=$(openclaw cron list --json 2>/dev/null) || raw=""

  # Strategy 1: jq exact match
  if [[ -n "$raw" ]] && command -v jq >/dev/null 2>&1; then
    if printf '%s' "$raw" | jq -e --arg n "$name" '
        # Accept both array-at-root and {jobs:[...]} wrapper shapes
        ( if type == "array" then . else .jobs // [] end )
        | map(select(.name == $n))
        | length > 0
      ' >/dev/null 2>&1; then
      return 0
    else
      return 1
    fi
  fi

  # Strategy 2: python3 exact match (no jq required)
  if [[ -n "$raw" ]] && command -v python3 >/dev/null 2>&1; then
    if printf '%s' "$raw" | python3 - "$name" 2>/dev/null <<'PYEOF'
import json, sys
name = sys.argv[1]
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    sys.exit(1)
jobs = data if isinstance(data, list) else data.get("jobs", [])
if any(j.get("name") == name for j in jobs):
    sys.exit(0)
sys.exit(1)
PYEOF
    then
      return 0
    else
      return 1
    fi
  fi

  # Strategy 3: --json flag not supported or both parsers absent.
  # Fall back to the text table ONLY as a last resort.  We use a fixed-width-
  # aware grep anchored at the start of the name column so it does NOT match
  # truncated "name..." rows — but we also note that if truncation IS occurring
  # we may still false-negative here.  This path is logged as a warning so the
  # operator can see it.
  _log "WARN _cron_present: jq and python3 unavailable — falling back to text-table grep (truncation risk!)"
  openclaw cron list 2>/dev/null | grep -Fq "$name"
}

# ---------------------------------------------------------------------------
# CLI capability detection (BUG-FIX v13.0.1 — fleet cron registration).
#
# Two independent CLI-shape facts decided the registration form:
#   1. SCHEDULE FLAG: every deployed CLI (2026.5.4 / 5.22 / 5.28 / 6.8) takes
#      the schedule via `--cron "<expr>"`. The flag `--schedule` DOES NOT EXIST
#      on ANY of them (the old code used it → every box rejected the cron with
#      `OpenClaw does not recognize option "--schedule"`). We ALWAYS use --cron.
#   2. JOB TYPE: 2026.6.x `cron add` supports `--command "<shell>"` (a real
#      command-mode job). The 2026.5.x line has NO `--command` (only --message /
#      --system-event agent jobs). So on the older CLI we register an AGENT
#      MESSAGE job that instructs the main agent to run the SAME script via the
#      shell. Both forms register a cron under the same name → qc-closeout-
#      wiring.sh C4 (which only checks `cron list` for the name) passes either way.
#
# _cli_supports_command: returns 0 if `openclaw cron add --help` advertises a
# `--command` option, else 1. Memoised. Fail-closed (assume NO --command) if the
# help text can't be read, so we never emit an unsupported flag to an old CLI.
# ---------------------------------------------------------------------------
_CLI_CMD_SUPPORT=""   # "" = unknown, "1" = yes, "0" = no
_cli_supports_command() {
  if [[ -z "$_CLI_CMD_SUPPORT" ]]; then
    local help
    help="$(openclaw cron add --help 2>&1 || true)"
    if printf '%s' "$help" | grep -qE '^[[:space:]]*--command[[:space:]<]'; then
      _CLI_CMD_SUPPORT="1"
    else
      _CLI_CMD_SUPPORT="0"
    fi
  fi
  [[ "$_CLI_CMD_SUPPORT" == "1" ]]
}

# Register ONE command-style pipeline cron in a CLI-portable way.
#   $1 name        cron name (idempotency key)
#   $2 schedule    cron expression (5-field), passed via --cron
#   $3 script      absolute path to the bash script the cron must run
#   $4 uuid_key    build-state key to persist the returned uuid into (optional)
#   $5 reg_at_key  build-state key to stamp the registration time (optional)
# Returns 0 on present-or-registered, 1 on a real registration failure.
#
# IDEMPOTENT: guarded by `openclaw cron list | grep -q <name>` (caller already
# checked, but we re-guard so the helper is safe standalone).
# FAIL-LOUD: a non-zero `cron add` rc is reported (caller increments fails →
# script exits 3 → qc-closeout-wiring.sh / installer surfaces the gap).
_register_command_cron() {
  local name="$1" schedule="$2" script="$3" uuid_key="${4:-}" reg_at_key="${5:-}"
  local out uuid

  if _cli_supports_command; then
    # 2026.6.x+ : native command-mode job. --cron (NOT --schedule).
    out=$(openclaw cron add --name "$name" --cron "$schedule" \
            --command "bash $script" --json 2>/dev/null) || out=""
  else
    # 2026.5.x : no --command. Register an AGENT MESSAGE job that runs the SAME
    # script through the shell. Silent (no --channel/--to) so it never announces
    # to a chat — it runs in the main agent's own context, mirroring the
    # 38-conversational-ai-system 2026.5.27-targeted registration pattern.
    local msg
    msg="[PIPELINE-CRON ${name}] Run this exact shell command now and report only on failure: bash ${script}"
    out=$(openclaw cron add --name "$name" --cron "$schedule" \
            --agent main --light-context --best-effort-deliver \
            --message "$msg" --json 2>/dev/null) || out=""
    # Some 5.x builds reject --json; retry without it (cron still registers).
    if [[ -z "$out" ]]; then
      if openclaw cron add --name "$name" --cron "$schedule" \
            --agent main --light-context --best-effort-deliver \
            --message "$msg" >/dev/null 2>&1; then
        out="{}"
      fi
    fi
  fi

  if [[ -n "$out" ]] && _cron_present "$name"; then
    uuid=$(printf '%s' "$out" | jq -r '.uuid // .id // empty' 2>/dev/null || true)
    [[ -n "$uuid_key" && -n "$uuid" && "$uuid" != "null" ]] && _persist_uuid "$uuid_key" "$uuid"
    [[ -n "$reg_at_key" ]] && _persist_field "$reg_at_key" "$(_now_iso)"
    return 0
  fi
  return 1
}

# Find a pipeline script across the canonical skill locations.
# $1 = skill folder (e.g. 23-ai-workforce-blueprint), $2 = relative script path.
_find_script() {
  local skill="$1" rel="$2" cand
  for cand in \
    "$OC_ROOT/skills/$skill/$rel" \
    "${HOME}/.openclaw/skills/$skill/$rel" \
    "/data/.openclaw/skills/$skill/$rel"; do
    if [[ -f "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

# Find a memory-health cron script (EMBEDDING-PREVENTION BUNDLE items 4-7).
# These live in the persistent ~/.openclaw/scripts (or /data/.openclaw/scripts),
# where install.sh + update-skills.sh land them. $1 = bare script name.
_find_health_script() {
  local name="$1" cand
  for cand in \
    "$OC_ROOT/scripts/$name" \
    "${HOME}/.openclaw/scripts/$name" \
    "/data/.openclaw/scripts/$name" \
    "${OC_PERSISTENT_SCRIPTS_DIR:-}/$name"; do
    [[ -n "$cand" ]] || continue
    if [[ -f "$cand" ]]; then
      printf '%s\n' "$cand"
      return 0
    fi
  done
  return 1
}

# Register ONE memory-health cron. $1 name, $2 schedule, $3 bare script name.
# Resolves the script from the persistent scripts dir; SKIPs (returns 1) if the
# script is not present (older bundle). Reuses the CLI-portable command-cron
# registrar so it works on both the 2026.5.x and 2026.6.x CLI lines.
_ensure_health_cron() {
  local name="$1" schedule="$2" script_name="$3"
  if _cron_present "$name"; then
    _log "OK  $name cron already present"
    return 0
  fi
  local script
  script="$(_find_health_script "$script_name")" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP $name — $script_name not found in persistent scripts dir (older bundle)"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "$name" "$schedule" "$script"; then
    _log "DONE $name cron registered ($schedule, $(_cli_supports_command && echo 'command mode' || echo 'agent-message fallback'))"
    return 0
  fi
  _log "FAIL $name cron creation failed (openclaw cron add rc!=0 or name not in cron list)"
  return 1
}

# Resolve a non-operator owner Telegram target (for the MESSAGE-mode cron only).
# Prints the chat id on stdout, or empty string if none / operator-only.
# Mirrors the three-layer resolver in install.sh + update-skills.sh.
_resolve_owner_chat() {
  command -v python3 >/dev/null 2>&1 || { printf ''; return 0; }
  python3 - "$OC_ROOT" <<'PYEOF' 2>/dev/null
import json, os, sys
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}
oc_root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.openclaw")
oc_json = os.path.join(oc_root, "openclaw.json")

def valid(v, bot_id=""):
    if not isinstance(v, (str, int)):
        return ""
    s = str(v).strip().replace("telegram:", "").replace("tg:", "")
    if not s:
        return ""
    digits = s.lstrip("-")
    if not (digits.isdigit() and 6 <= len(digits) <= 20):
        return ""
    if bot_id and s == bot_id:
        return ""
    if s in OPERATOR_CHAT_IDS:
        return ""
    return s

cfg = {}
try:
    cfg = json.load(open(oc_json))
except Exception:
    pass

bot_id = ""
bt = (cfg.get("channels", {}).get("telegram", {}) or {}).get("botToken", "") or ""
if ":" in bt:
    bot_id = bt.split(":")[0]

# S0: explicit env override
s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if s0:
    cid = valid(s0, bot_id)
    if cid:
        print(cid); raise SystemExit(0)

# S1: channels.telegram.allowFrom
for v in (cfg.get("channels", {}).get("telegram", {}) or {}).get("allowFrom", []) or []:
    cid = valid(v, bot_id)
    if cid:
        print(cid); raise SystemExit(0)

# S2: commands.ownerAllowFrom
for v in (cfg.get("commands", {}) or {}).get("ownerAllowFrom", []) or []:
    cid = valid(v, bot_id)
    if cid:
        print(cid); raise SystemExit(0)

print("")
PYEOF
}

# Resolve the channel account (if any) for the message-mode cron.
_resolve_channel_account() {
  command -v python3 >/dev/null 2>&1 || { printf ''; return 0; }
  python3 - "$OC_ROOT" <<'PYEOF' 2>/dev/null
import json, os, sys
oc_root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.openclaw")
oc_json = os.path.join(oc_root, "openclaw.json")
cfg = {}
try:
    cfg = json.load(open(oc_json))
except Exception:
    pass
tg = cfg.get("channels", {}).get("telegram", {}) or {}
acct = tg.get("account") or tg.get("accountId") or ""
print(acct if isinstance(acct, str) else "")
PYEOF
}

# ---------------------------------------------------------------------------
# Registrars — one per cron. Each is name-keyed + idempotent.
# Returns 0 on present-or-registered, 1 on a real registration failure.
# ---------------------------------------------------------------------------

# 1. workforce-build-resume (SILENT main-session AGENT-MESSAGE mode, */15).
#    Drives Skill 23 build resume AND in-process execs run-closeout.sh on the
#    auto-complete hop.
#
#    SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons): this is a
#    MAINTENANCE self-ping, NOT an owner-facing announcement. The old form wired
#    `--channel telegram --to <owner-chat>`, so the scheduler AUTO-DELIVERED the
#    raw resume prompt into the CLIENT chat every 15 min — internal build/operator
#    traffic the owner was never meant to see. It is now a SILENT main-session
#    agent-message cron (--agent main --session-target main --light-context, NO
#    --channel/--to/--announce). The resume runs in the agent's own context
#    (log-only); the agent surfaces owner-facing progress only via its own
#    deliberate `message send`. Because nothing is auto-delivered, NO owner chat
#    is required → the historical "no owner chat → skip" and operator-ID strand
#    branches are gone. This matches the silent install.sh Step 13 form exactly
#    (hot-patch parity).
_ensure_workforce_build_resume() {
  if _cron_present "workforce-build-resume"; then
    _log "OK  workforce-build-resume cron already present"
    return 0
  fi

  local prompt_file
  prompt_file="$(_find_script 23-ai-workforce-blueprint resume-prompt.txt)" || true
  if [[ -z "${prompt_file:-}" ]]; then
    _log "SKIP workforce-build-resume — resume-prompt.txt not found (older skill bundle)"
    return 1
  fi

  local prompt
  prompt="$(cat "$prompt_file")"
  local base=(--name "workforce-build-resume" --agent main --cron "*/15 * * * *" --tz "America/New_York" --session-target main --light-context)
  if openclaw cron create "${base[@]}" --message "$prompt" >/dev/null 2>&1; then
    _log "DONE workforce-build-resume cron registered (*/15, SILENT main-session — no client auto-announce)"
    return 0
  fi
  # no-light-context fallback (older CLI may not advertise the flag)
  if openclaw cron create --name "workforce-build-resume" --agent main --cron "*/15 * * * *" --tz "America/New_York" --session-target main --message "$prompt" >/dev/null 2>&1; then
    _log "DONE workforce-build-resume cron registered (silent main-session, no-light-context fallback)"
    return 0
  fi
  _log "FAIL workforce-build-resume cron creation failed (openclaw cron create rc!=0)"
  return 1
}

# 2. interview-nudge (COMMAND mode, 0 */6). Owner-facing idle-interview nudge.
_ensure_interview_nudge() {
  if _cron_present "interview-nudge"; then
    _log "OK  interview-nudge cron already present"
    return 0
  fi
  local script
  script="$(_find_script 23-ai-workforce-blueprint scripts/interview-nudge-cron.sh)" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP interview-nudge — interview-nudge-cron.sh not found"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "interview-nudge" "0 */6 * * *" "$script" interviewNudgeUuid; then
    _log "DONE interview-nudge cron registered (0 */6, $(_cli_supports_command && echo 'command mode' || echo 'agent-message fallback'))"
    return 0
  fi
  _log "FAIL interview-nudge cron creation failed (openclaw cron add rc!=0 or name not in cron list)"
  return 1
}

# 3. closeout-readiness-watchdog (COMMAND mode, 0 */6). Operator escalation.
_ensure_closeout_watchdog() {
  if _cron_present "closeout-readiness-watchdog"; then
    _log "OK  closeout-readiness-watchdog cron already present"
    return 0
  fi
  local script
  script="$(_find_script 23-ai-workforce-blueprint scripts/closeout-readiness-watchdog.sh)" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP closeout-readiness-watchdog — closeout-readiness-watchdog.sh not found"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "closeout-readiness-watchdog" "0 */6 * * *" "$script" closeoutWatchdogCronUuid; then
    _log "DONE closeout-readiness-watchdog cron registered (0 */6, $(_cli_supports_command && echo 'command mode' || echo 'agent-message fallback'))"
    return 0
  fi
  _log "FAIL closeout-readiness-watchdog cron creation failed (openclaw cron add rc!=0 or name not in cron list)"
  return 1
}

# 4. closeout-resume (COMMAND mode, */15). The DEDICATED, REDUNDANT closeout
#    trigger. No Telegram target needed — runs run-closeout.sh via the resume
#    cron script regardless of owner-chat resolution. This is the fix that makes
#    closeout fire even on boxes where Step 13's message-mode cron was skipped.
_ensure_closeout_resume() {
  if _cron_present "closeout-resume"; then
    _log "OK  closeout-resume cron already present"
    return 0
  fi
  local script
  script="$(_find_script 37-zhc-closeout scripts/resume-closeout-cron.sh)" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP closeout-resume — resume-closeout-cron.sh not found (Skill 37 not installed yet)"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "closeout-resume" "*/15 * * * *" "$script" closeoutResumeUuid closeoutResumeRegisteredAt; then
    _log "DONE closeout-resume cron registered (*/15, $(_cli_supports_command && echo 'command mode' || echo 'agent-message fallback') — REDUNDANT trigger, no owner chat required)"
    return 0
  fi
  _log "FAIL closeout-resume cron creation failed (openclaw cron add rc!=0 or name not in cron list)"
  return 1
}

# 9. ghl-token-liveness (COMMAND mode, 0 8 * * *). Daily Skills 44+46 Firebase
#    token health check. Runs check-ghl-token-liveness.sh once per day at 08:00
#    UTC; the script is self-idempotent (day-stamp guard) so firing it via cron
#    AND via direct invocation is safe. No Telegram owner chat is needed here —
#    the check script resolves the client chat itself.
_ensure_ghl_token_liveness() {
  if _cron_present "ghl-token-liveness"; then
    _log "OK  ghl-token-liveness cron already present"
    return 0
  fi
  local script
  script="$(_find_script 44-convert-and-flow-operator tools/check-ghl-token-liveness.sh)" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP ghl-token-liveness — check-ghl-token-liveness.sh not found in Skill 44 tools/ (Skill 44 not installed yet)"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "ghl-token-liveness" "0 8 * * *" "$script"; then
    _log "DONE ghl-token-liveness cron registered (0 8 * * *, daily at 08:00 UTC, $(_cli_supports_command && echo 'command mode' || echo 'agent-message fallback'))"
    return 0
  fi
  _log "FAIL ghl-token-liveness cron creation failed (openclaw cron add rc!=0 or name not in cron list)"
  return 1
}

# Persist a cron UUID into build-state (best-effort; never fatal).
_persist_uuid() {
  local key="$1" uuid="$2"
  [[ -f "$STATE_FILE" ]] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  local tmp
  tmp=$(mktemp) || return 0
  if jq --arg uuid "$uuid" ".${key} = \$uuid" "$STATE_FILE" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
  fi
}

_persist_field() {
  local key="$1" val="$2"
  [[ -f "$STATE_FILE" ]] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  local tmp
  tmp=$(mktemp) || return 0
  if jq --arg v "$val" ".${key} = \$v" "$STATE_FILE" > "$tmp" 2>/dev/null; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
  fi
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  if ! command -v openclaw >/dev/null 2>&1; then
    _log "openclaw CLI not on PATH — cannot register pipeline crons. Re-run after CLI is installed."
    # Not fatal: install/update continues; the next run backfills.
    exit 0
  fi

  _log "asserting pipeline trigger crons (idempotent backfill) — $ENSURE_PIPELINE_CRONS_VERSION"

  local fails=0
  # The two COMMAND-mode triggers first — these never depend on a Telegram
  # owner chat, so the closeout experience is guaranteed a deterministic trigger
  # even when the message-mode resume cron cannot be wired.
  _ensure_closeout_resume          || fails=$((fails + 1))
  _ensure_closeout_watchdog        || fails=$((fails + 1))
  _ensure_interview_nudge          || fails=$((fails + 1))
  # The message-mode resume cron last (its self-ping needs a non-operator chat).
  _ensure_workforce_build_resume   || fails=$((fails + 1))

  # ── EMBEDDING-PREVENTION BUNDLE: memory-health crons (items 4-7) ───────────
  # These are command-mode host crons (no owner chat needed). A missing script
  # (older bundle) is a SKIP (counts toward fails as advisory, never fatal).
  #   - index-model-drift-check       hourly  : config-vs-index model drift alarm
  #   - orphan-temp-sweep             hourly  : clears failed-reindex *.sqlite.tmp
  #   - disk-usage-alert              hourly  : >85% disk alert
  #   - pre-july14-embedding-migration daily  : flags boxes still on dying 001 model
  _ensure_health_cron "index-model-drift-check"  "17 * * * *" "index-model-drift-check.sh"               || fails=$((fails + 1))
  _ensure_health_cron "orphan-temp-sweep"        "37 * * * *" "orphan-temp-sweep.sh"                      || fails=$((fails + 1))
  _ensure_health_cron "disk-usage-alert"         "47 * * * *" "disk-usage-alert.sh"                       || fails=$((fails + 1))
  _ensure_health_cron "pre-july14-embed-migrate" "23 9 * * *" "pre-july14-embedding-migration-check.sh"  || fails=$((fails + 1))
  # SINGLETON POOLED BROWSER backstop: */10 reaper sweeps orphaned agent-browser
  # sessions/descriptors + tripwires scoped Chromium (NEVER bare chrome/Claude).
  # */10 (not */5) matches the hourly-family cadence + minimizes host load.
  _ensure_health_cron "agent-browser-reaper"     "*/10 * * * *" "agent-browser-reaper.sh"                 || fails=$((fails + 1))

  # ── GHL TOKEN LIVENESS (Skills 44 + 46) ─────────────────────────────────────
  # Daily at 08:00 UTC: checks if the client's GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN
  # is still exchangeable at securetoken.googleapis.com. On INVALID, the check
  # script sends a plain-English re-grab notification to the CLIENT's own chat.
  # A missing script (Skill 44 not installed) is a SKIP (advisory, not fatal).
  _ensure_ghl_token_liveness || fails=$((fails + 1))

  # One-line audit of current cron presence (exact JSON match, no truncation).
  local present=""
  local _n
  for _n in "workforce-build-resume" "interview-nudge" "closeout-readiness-watchdog" "closeout-resume" \
            "index-model-drift-check" "orphan-temp-sweep" "disk-usage-alert" "pre-july14-embed-migrate" \
            "agent-browser-reaper" "ghl-token-liveness"; do
    _cron_present "$_n" && present="${present}${_n} "
  done
  present="${present% }"  # trim trailing space
  _log "AUDIT crons present after run: [${present:-none}]"

  if [[ "$fails" -gt 0 ]]; then
    _log "WARN $fails pipeline cron(s) could not be registered this run (see lines above). Install/update continues; re-run to backfill."
    exit 3
  fi
  _log "ALL pipeline trigger crons present."
  exit 0
}

main "$@"
