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
# v14.1.1 — RECONCILE PASS (agent-browser-reaper-announce-spam fix): v13.8.16 made
#   NEW crons silent, but this registrar only ever checked _cron_present and
#   returned "already present" — it never inspected/repaired an EXISTING cron's
#   delivery. So every box onboarded before the silent-cron change kept the old
#   announce+last reaper (spamming the client every 10 min) and, where it was an
#   agentTurn, burned ~1.4-1.66M client tokens/day. The reconcile pass below runs
#   on every install.sh / update-skills.sh: for each MANAGED maintenance/health/
#   onboarding cron that already exists, if its delivery resolves to
#   mode==announce OR channel==last OR a client/operator --to is set, it flips it
#   SILENT in place (`openclaw cron edit <id> --no-deliver`), converts an
#   agentTurn reaper back to command-kind (zero LLM tokens), and throttles the
#   reaper */10 -> hourly. Idempotent + logs every flip. This makes
#   silent-by-default CONVERGE on already-deployed boxes, not just fresh installs.
# v14.1.6 — add weekly-onboarding-update to MANAGED_RECONCILE_CRONS as a
#   belt-and-suspenders backstop for fix/existing-box-cron-rewrite (v14.19.1).
#   install.sh + update-skills.sh now do a delete+recreate on detect; this entry
#   catches any box where that delete failed (CLI error / no python3) by silencing
#   the delivery in-place via --no-deliver.
# v14.1.7 — STALE-LIFECYCLE-CRON SWEEP (fix/cron-nudge-sweep-selfheal-2026-06-29):
#   Adds _sweep_stale_lifecycle_crons() that ACTIVELY removes interview-nudge and
#   closeout-readiness-watchdog crons from already-complete boxes on every
#   `openclaw update` / update-skills.sh run. Before this, a box where
#   interviewComplete==true or closeoutStatus==done still had the burner crons
#   registered (they would self-remove on their next fire, but the update pass
#   never proactively swept them). The sweep runs BEFORE the registrars so a
#   swept cron is never immediately re-added. Also adds completion guards to
#   _ensure_interview_nudge() and _ensure_closeout_watchdog() to prevent
#   re-registration on already-complete boxes.
ENSURE_PIPELINE_CRONS_VERSION="v14.1.7"

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

# ---------------------------------------------------------------------------
# DURABLE TOMBSTONE support (fix/industry-gate-and-idempotent-crons, live-VPS
# finding, 2026-07-11): `openclaw cron list --json` was observed on a live box
# returning ONLY enabled jobs (16 of 31 actual rows) — a DISABLED cron is
# invisible to _cron_present() below, so the next install.sh/update-skills.sh
# run (which calls this script) silently RESURRECTS it. A durable, file-based
# tombstone (shared-utils/cron-lib.sh::oc_cron_tombstoned/oc_cron_tombstone,
# mirroring this file's own BOX_PARK_MARKER pattern above) makes a deliberate
# disable/removal survive re-registration regardless of what `cron list --json`
# does or doesn't expose. Sourced ONLY for the tombstone helpers — this file's
# OWN `_cron_present` below (the proven v13.0.2 reference implementation) is
# otherwise left as-is, per "do not regress it," but is ALSO hardened with the
# same best-effort full-visibility flag detection cron-lib.sh uses. Fails OPEN
# (never tombstoned) if the shared lib can't be found — never blocks
# registration outright over a missing helper file.
_CRON_LIB_TOMBSTONE=""
for _cand in \
  "$(dirname "${BASH_SOURCE[0]:-$0}")/../shared-utils/cron-lib.sh" \
  "$SKILLS_DIR/shared-utils/cron-lib.sh" \
  "/data/.openclaw/skills/shared-utils/cron-lib.sh"; do
  if [[ -f "$_cand" ]]; then
    _CRON_LIB_TOMBSTONE="$_cand"
    break
  fi
done
if [[ -n "$_CRON_LIB_TOMBSTONE" ]]; then
  # shellcheck source=/dev/null
  source "$_CRON_LIB_TOMBSTONE"
fi
command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }
command -v oc_cron_list_json_flags >/dev/null 2>&1 || oc_cron_list_json_flags() { return 1; }

# v14.1.5 — DURABLE PARK marker (the SAME file the Skill-23 resume cron
# resume-workforce-build.sh and the agent-browser circuit-breaker
# 06-ghl-install-pages/tools/browser_manager.sh read/write). If present, this
# box's build is intentionally PARKED: this registrar must NOT (re)register the
# workforce-build-resume cron — doing so would resurrect, on the weekly
# update-skills.sh run, the very furnace an operator parked. Operator un-park:
# scripts/unpark-build.sh.
BOX_PARK_MARKER="$OC_ROOT/workspace/.park/workforce-build.parked"

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
  local -a _extra_flags=()
  local _detected
  # Best-effort full-visibility flag (fix/industry-gate-and-idempotent-crons,
  # live-VPS finding): only used if `cron list --help` ITSELF advertises one —
  # never assumed. See shared-utils/cron-lib.sh header for the full rationale;
  # oc_cron_list_json_flags is a no-op (returns 1) if that lib wasn't found.
  if _detected="$(oc_cron_list_json_flags 2>/dev/null)" && [[ -n "$_detected" ]]; then
    # shellcheck disable=SC2206
    _extra_flags=( $_detected )
  fi
  local raw
  raw=$(openclaw cron list --json ${_extra_flags[@]+"${_extra_flags[@]}"} 2>/dev/null) || raw=""

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
  #
  # SC2259 FIX (fix/industry-gate-and-idempotent-crons): JSON is passed via an
  # env var, not a pipe — `python3 -` already reads its OWN script text from
  # stdin via the heredoc below, so a pipe feeding the SAME stdin is silently
  # OVERRIDDEN (the heredoc wins) and `sys.stdin.read()` inside the script would
  # see EOF, not the JSON — the exact same pattern already used two screens down
  # in _reconcile_rows() (OC_CRON_RAW env var), applied here for consistency.
  if [[ -n "$raw" ]] && command -v python3 >/dev/null 2>&1; then
    if OC_CRON_RAW="$raw" python3 - "$name" 2>/dev/null <<'PYEOF'
import json, os, sys
name = sys.argv[1]
raw = os.environ.get("OC_CRON_RAW", "")
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

# ── Runtime-compatible SILENT main-session cron registration. ──────────────────
# (fix/cron-flag-skew.) The silent main-session agent-cron shape changed across
# OpenClaw CLI builds: 2026.6.8/5.x use `--session-target main --message`, but
# 2026.6.11+ REMOVED `--session-target` and require `--session main --system-event`
# for main-session jobs (a `--message` main job is rejected: "Main jobs require
# --system-event"). The old workforce-build-resume registration only ever emitted
# `--session-target main --message`, so a rolled box on 2026.6.11 silently
# installed NO resume cron. This helper probes `openclaw cron add --help`, emits
# the form the runtime accepts, falls through the other known-good forms, and
# degrades to a SILENT isolated agent-message job (--no-deliver). Every path is
# silent (no --channel/--to/--announce); a rejected form creates nothing.
#   $1 name  $2 agent  $3 cron-expr  $4 tz  $5 prompt ; $6.. = extra flags
_oc_cron_silent_main() {
  local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5"; shift 5
  local _extra=( "$@" ); local _n=${#_extra[@]}
  local _base=( --name "$_name" --agent "$_agent" --cron "$_expr" --tz "$_tz" )
  local _help _modern=0
  _help="$(openclaw cron add --help 2>&1 || true)"
  printf '%s' "$_help" | grep -qE '^[[:space:]]*--session[[:space:]<]' && _modern=1
  local _order _k
  if [[ "$_modern" == "1" ]]; then _order="modern old"; else _order="old modern"; fi
  for _k in $_order; do
    if [[ "$_k" == "modern" ]]; then
      [[ "$_n" -gt 0 ]] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
      openclaw cron create "${_base[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
    else
      [[ "$_n" -gt 0 ]] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
      openclaw cron create "${_base[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
    fi
  done
  openclaw cron create "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --tz "$_tz" --session main >/dev/null 2>&1 && return 0
  openclaw cron create "${_base[@]}" --message "$_prompt" --no-deliver >/dev/null 2>&1 && return 0
  return 1
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
  if oc_cron_tombstoned "$name"; then
    _log "SKIP $name — TOMBSTONED (deliberately removed). NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove $name"
    return 0
  fi
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
  # PARK-AWARE (v14.1.5): never resurrect a parked box's resume cron. This is the
  # backstop that makes the resume cron's self-disable STICK across the weekly
  # update-skills.sh / install.sh backfill — without it, a parked cron would be
  # re-added within a week and the loop would return.
  if [[ -f "$BOX_PARK_MARKER" ]]; then
    _log "SKIP workforce-build-resume — build is PARKED ($BOX_PARK_MARKER). NOT re-registering (would resurrect the furnace an operator parked). Un-park: scripts/unpark-build.sh."
    return 0
  fi
  if oc_cron_tombstoned "workforce-build-resume"; then
    _log "SKIP workforce-build-resume — TOMBSTONED (deliberately removed). NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove workforce-build-resume"
    return 0
  fi
  if _cron_present "workforce-build-resume"; then
    _log "OK  workforce-build-resume cron already present"
    return 0
  fi

  # CHEAP COMMAND-MODE (fix/industry-gate-and-idempotent-crons, Fix C — v14.1.7+):
  # this cron used to be a SILENT main-session AGENT-MESSAGE job (the full
  # resume-prompt.txt fed as the system-event payload), so EVERY */15 fire spun
  # up a complete LLM turn just to reach the shell guard's "nothing to resume"
  # verdict — a token furnace on any box with no active build (the diagnosed
  # no-op furnace: resume-workforce-build.sh's own gating logic then discovers
  # "nothing to do" and exits, but the expensive turn was already spent).
  #
  # resume-workforce-build.sh is ALREADY a cheap, token-free check when run
  # directly as plain bash: it reads build-state via jq and only in the case
  # there is genuinely pending/stale work, an unmet library/comms/closeout gate,
  # etc. does it escalate — via `openclaw message send`, the SAME self-ping
  # mechanism closeout-resume already uses — to an actual agent turn. So
  # registering the CRON ITSELF in command mode (`bash resume-workforce-build.sh`
  # via _register_command_cron, mirroring the already-correct
  # _ensure_closeout_resume above) makes the 15-min tick cost ZERO LLM tokens on
  # every box with nothing to resume; an agent turn now dispatches ONLY when the
  # script's own logic decides one is warranted. resume-workforce-build.sh's
  # internal decision/dispatch logic is UNCHANGED by this — only WHO invokes it
  # on the tick changes (cheap shell vs. an expensive agent turn).
  local script
  script="$(_find_script 23-ai-workforce-blueprint scripts/resume-workforce-build.sh)" || true
  if [[ -z "${script:-}" ]]; then
    _log "SKIP workforce-build-resume — resume-workforce-build.sh not found (older skill bundle)"
    return 1
  fi
  chmod +x "$script" 2>/dev/null || true
  if _register_command_cron "workforce-build-resume" "*/15 * * * *" "$script"; then
    _log "DONE workforce-build-resume cron registered (*/15, $(_cli_supports_command && echo 'command mode — zero LLM tokens per tick' || echo 'agent-message fallback (older CLI, no --command support) — short run-the-script message, not the old full resume-prompt.txt payload'))"
    return 0
  fi
  _log "FAIL workforce-build-resume cron creation failed (openclaw cron add rc!=0 or name not in cron list)"
  return 1
}

# 2. interview-nudge (COMMAND mode, 0 */6). Owner-facing idle-interview nudge.
_ensure_interview_nudge() {
  # Completion guard (v14.1.7): do not (re-)register on a box where the interview
  # lifecycle is already finished. The sweep (_sweep_stale_lifecycle_crons) removes
  # any existing cron first; this guard ensures we never re-add it immediately after.
  if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
    local _ic; _ic=$(jq -r '.interviewComplete // empty' "$STATE_FILE" 2>/dev/null)
    if [[ "$_ic" == "true" ]]; then
      _log "SKIP interview-nudge — interviewComplete=true on this box; lifecycle cron not needed"
      return 0
    fi
  fi
  if oc_cron_tombstoned "interview-nudge"; then
    _log "SKIP interview-nudge — TOMBSTONED (deliberately removed). NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove interview-nudge"
    return 0
  fi
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
  # Completion guard (v14.1.7): do not (re-)register on a box where closeout is done.
  if [[ -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
    local _cs; _cs=$(jq -r '.closeoutStatus // empty' "$STATE_FILE" 2>/dev/null)
    if [[ "$_cs" == "done" || "$_cs" == "sent" ]]; then
      _log "SKIP closeout-readiness-watchdog — closeoutStatus=${_cs}; lifecycle cron not needed"
      return 0
    fi
  fi
  if oc_cron_tombstoned "closeout-readiness-watchdog"; then
    _log "SKIP closeout-readiness-watchdog — TOMBSTONED (deliberately removed). NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove closeout-readiness-watchdog"
    return 0
  fi
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
  if oc_cron_tombstoned "closeout-resume"; then
    _log "SKIP closeout-resume — TOMBSTONED (deliberately removed). NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove closeout-resume"
    return 0
  fi
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
  if oc_cron_tombstoned "ghl-token-liveness"; then
    _log "SKIP ghl-token-liveness — TOMBSTONED (deliberately removed). NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove ghl-token-liveness"
    return 0
  fi
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

# ===========================================================================
# RECONCILE PASS (v14.1.1 — agent-browser-reaper-announce-spam fix)
# ===========================================================================
# WHY: see the file header. _cron_present-only idempotency never repaired an
# EXISTING cron's delivery, so boxes onboarded before the silent-cron change
# kept the old announce+last reaper (client Telegram spam every 10 min) and, on
# agentTurn boxes, a ~1.4-1.66M-token/day furnace on the CLIENT's funded key.
#
# WHAT: for each MANAGED maintenance/health/onboarding cron that already exists,
# read its delivery + payload.kind. If delivery resolves to a chat
# (mode==announce OR channel=="last" OR a non-empty `to`), flip it SILENT in
# place with `openclaw cron edit <id> --no-deliver` (sets delivery.mode=none →
# the runner stops fallback-delivering to any chat). For the reaper specifically:
# also convert an agentTurn payload back to command-kind (zero LLM tokens) and
# throttle a */10 schedule to hourly. Idempotent: a cron already silent (mode
# none, no `to`) and on the right kind/schedule is left untouched and logged OK.
#
# SCOPE / SAFETY: ONLY the names in MANAGED_RECONCILE_CRONS below are touched.
# Personal/client reminder crons on the same box are never inspected or edited.
# Runs as the invoking (node/process) user — install.sh + update-skills.sh both
# call this script un-elevated. Never root.
#
# The CLI in the field (2026.6.8) exposes `--no-deliver` (the authoritative
# silencer; NO `--clear-channel`/`--clear-to` flag exists), `--cron <expr>`
# (reschedule), and `--command <shell>` (set a command payload). We use exactly
# those. `--no-deliver` leaves a vestigial `channel:"last"` string in the JSON
# but with mode=none nothing is ever delivered.

# The exact set of crons this registrar manages — the ONLY names reconcile may
# edit. Keep in lockstep with the registrars + main() audit list above.
MANAGED_RECONCILE_CRONS=(
  "workforce-build-resume"
  "interview-nudge"
  "closeout-readiness-watchdog"
  "closeout-resume"
  "index-model-drift-check"
  "orphan-temp-sweep"
  "disk-usage-alert"
  "pre-july14-embed-migrate"
  "agent-browser-reaper"
  "ghl-token-liveness"
  # v14.1.6 — belt-and-suspenders for the existing-box cron-rewrite migration
  # (fix/existing-box-cron-rewrite).  install.sh + update-skills.sh now detect
  # old announce/to wiring and delete+recreate.  If that delete fails (CLI error
  # or python3 absent), the reconcile pass here catches any remaining announce-
  # mode or non-empty `to` delivery and silences it via --no-deliver.
  "weekly-onboarding-update"
)

# Emit one TSV row per managed cron that currently exists, with the fields the
# reconcile pass needs. Columns (tab-separated):
#   name  id  delivery_mode  delivery_channel  delivery_to  payload_kind  schedule_expr
# Only rows whose name is in MANAGED_RECONCILE_CRONS are emitted. Uses the same
# JSON path as _cron_present (jq → python3). Prints nothing if neither parser is
# available or the list call fails (reconcile then no-ops, logged).
#
# EMPTY-FIELD SENTINEL: bash `read` treats TAB (a whitespace IFS char) as a
# COLLAPSING delimiter, so two adjacent tabs (an empty middle field like an
# absent `to`) would shift every later column left by one — silently mis-reading
# kind/schedule. To keep columns aligned we emit the literal token "\x1e" (ASCII
# RS, which can never appear in a cron name/id/mode/channel/chatId/kind/expr) in
# place of any empty field, and the consumer (_reconcile_one) decodes it back to
# "". This makes the row a true fixed-7-column record under `read`.
_RECONCILE_EMPTY=$'\x1e'
_reconcile_rows() {
  local raw
  raw=$(openclaw cron list --json 2>/dev/null) || raw=""
  [[ -n "$raw" ]] || return 0

  local names_csv
  names_csv=$(printf '%s,' "${MANAGED_RECONCILE_CRONS[@]}")

  if command -v python3 >/dev/null 2>&1; then
    # Pass the JSON + the managed-name CSV via the ENVIRONMENT, not stdin.
    # `python3 - <<'PY'` already consumes stdin to read the PROGRAM, so we must
    # NOT also pipe the JSON to stdin (that would make python try to execute the
    # JSON as the program → NameError). Env vars avoid the stdin collision.
    OC_CRON_RAW="$raw" OC_CRON_NAMES="$names_csv" python3 - <<'PYEOF' 2>/dev/null
import json, os
managed = set(x for x in os.environ.get("OC_CRON_NAMES", "").split(",") if x)
raw = os.environ.get("OC_CRON_RAW", "")
try:
    data = json.loads(raw)
except Exception:
    raise SystemExit(0)
jobs = data if isinstance(data, list) else data.get("jobs", [])
for j in jobs:
    name = j.get("name", "")
    if name not in managed:
        continue
    jid = j.get("id", "")
    dl = j.get("delivery") or {}
    mode = dl.get("mode")
    chan = dl.get("channel")
    to = dl.get("to")
    pk = (j.get("payload") or {}).get("kind", "")
    sch = (j.get("schedule") or {}).get("expr", "")
    SENT = "\x1e"  # ASCII RS — empty-field sentinel (see shell comment)
    def s(v):
        return SENT if v is None or v == "" else str(v)
    # Tab-separated, fixed 7 columns; empty fields become the RS sentinel so the
    # shell `read` keeps columns aligned. Names/ids/exprs never contain tabs.
    print("\t".join([s(name), s(jid), s(mode), s(chan), s(to), s(pk), s(sch)]))
PYEOF
    return 0
  fi

  # jq fallback (no python3). Same columns + same empty-field RS sentinel.
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$raw" | jq -r --arg names "$names_csv" '
      def nz: if (. == null or . == "") then "\u001e" else (.|tostring) end;
      ($names | split(",") | map(select(length>0))) as $m
      | (if type=="array" then . else .jobs // [] end)
      | map(select(.name as $n | $m | index($n)))
      | .[]
      | [ (.name|nz), (.id|nz), (.delivery.mode|nz),
          (.delivery.channel|nz), (.delivery.to|nz),
          (.payload.kind|nz), (.schedule.expr|nz) ]
      | @tsv
    ' 2>/dev/null
    return 0
  fi

  _log "WARN reconcile: neither python3 nor jq available — cannot read cron deliveries; skipping reconcile"
  return 0
}

# Reconcile a single cron row. Args = the 7 TSV columns.
# Returns the number of edits made on stdout is NOT used; logs each action.
_reconcile_one() {
  local name="$1" id="$2" mode="$3" chan="$4" to="$5" kind="$6" expr="$7"
  # Decode the empty-field RS sentinel back to "" (see _reconcile_rows comment).
  local _s="$_RECONCILE_EMPTY"
  [[ "$name" == "$_s" ]] && name=""
  [[ "$id"   == "$_s" ]] && id=""
  [[ "$mode" == "$_s" ]] && mode=""
  [[ "$chan" == "$_s" ]] && chan=""
  [[ "$to"   == "$_s" ]] && to=""
  [[ "$kind" == "$_s" ]] && kind=""
  [[ "$expr" == "$_s" ]] && expr=""
  [[ -n "$id" ]] || { _log "RECONCILE skip $name — no id resolved"; return 0; }

  # Build the edit-flag list. Empty = nothing to do.
  local -a edit_flags=()
  local reasons=""

  # (a) Delivery resolves to a chat? announce mode, or channel "last", or any
  #     non-empty `to`. Flip silent. (mode already "none" with no `to` = OK.)
  if [[ "$mode" == "announce" || "$chan" == "last" || -n "$to" ]]; then
    # Only act if it is not ALREADY fully silent. "Fully silent" = mode none AND
    # no `to`. A vestigial channel:"last" with mode none + no to is harmless, but
    # we still strip the announce/`to`; re-running --no-deliver on an already
    # mode:none cron is a harmless no-op, so we gate on the meaningful signals.
    if [[ "$mode" == "announce" || -n "$to" ]]; then
      edit_flags+=(--no-deliver)
      reasons="${reasons}delivery(mode=${mode:-none},to=${to:-none}) "
    fi
  fi

  # (b) Reaper-specific: convert agentTurn -> command-kind (zero LLM tokens) and
  #     throttle a */10 schedule to hourly.
  if [[ "$name" == "agent-browser-reaper" ]]; then
    if [[ "$kind" == "agentTurn" ]]; then
      local rscript
      rscript="$(_find_health_script "agent-browser-reaper.sh")" || true
      if [[ -n "${rscript:-}" ]]; then
        edit_flags+=(--command "bash $rscript")
        reasons="${reasons}agentTurn->command "
      else
        _log "RECONCILE warn $name is agentTurn but agent-browser-reaper.sh not found in persistent scripts dir — cannot convert to command-kind this run"
      fi
    fi
    if [[ "$expr" == "*/10 * * * *" ]]; then
      edit_flags+=(--cron "13 * * * *")
      reasons="${reasons}throttle(*/10->hourly) "
    fi
  fi

  if [[ "${#edit_flags[@]}" -eq 0 ]]; then
    _log "OK  reconcile $name — already silent + correct kind/schedule (no change)"
    return 0
  fi

  if openclaw cron edit "$id" "${edit_flags[@]}" >/dev/null 2>&1; then
    _log "DONE reconcile $name — flipped: ${reasons% } (cron edit $id ${edit_flags[*]})"
  else
    _log "WARN reconcile $name — cron edit rc!=0 (id=$id, flags: ${edit_flags[*]}); will retry next run"
  fi
  return 0
}

# Top-level reconcile pass. Idempotent; safe to re-run. Logs a one-line summary.
_reconcile_managed_crons() {
  command -v openclaw >/dev/null 2>&1 || return 0
  _log "RECONCILE pass — repairing delivery/kind/schedule of pre-existing managed crons"
  local rows
  rows="$(_reconcile_rows)"
  if [[ -z "$rows" ]]; then
    _log "RECONCILE no managed crons present yet (or cron list unreadable) — nothing to reconcile"
    return 0
  fi
  local IFS_OLD="$IFS"
  while IFS=$'\t' read -r r_name r_id r_mode r_chan r_to r_kind r_expr; do
    [[ -n "$r_name" ]] || continue
    _reconcile_one "$r_name" "$r_id" "$r_mode" "$r_chan" "$r_to" "$r_kind" "$r_expr"
  done <<< "$rows"
  IFS="$IFS_OLD"
}

# ---------------------------------------------------------------------------
# _sweep_stale_lifecycle_crons  (v14.1.7 — stale-lifecycle-cron migration)
#
# WHY: interview-nudge and closeout-readiness-watchdog are LIFECYCLE crons —
# they exist only while the associated work is in-progress. On boxes installed
# before v12.3.10/v12.3.13 those crons were registered but never removed when
# the lifecycle completed, because (a) older script versions lacked self-removal
# and (b) the update path only registered missing crons, never swept stale ones.
# On such boxes the crons fired silently (exit 0 fast-path after v12.3.x was
# deployed) but remained permanently in the registry, burning cron slots.
#
# WHAT: reads interviewComplete and closeoutStatus from build-state (token-free
# jq). If complete, resolves the cron UUID from state (.interviewNudgeUuid /
# .closeoutWatchdogCronUuid) or falls back to a name-scan, then calls
# `openclaw cron rm`. Best-effort (non-fatal on rm failure — the script's own
# self-removal is the authoritative path; this is the fleet-wide update-time
# convergence backstop).
#
# ORDER: must run BEFORE the registrars so a swept cron is not immediately
# re-registered. The completion guards in _ensure_interview_nudge() and
# _ensure_closeout_watchdog() provide a second layer of protection.
# ---------------------------------------------------------------------------
_sweep_stale_lifecycle_crons() {
  [[ -f "$STATE_FILE" ]] || return 0
  command -v openclaw >/dev/null 2>&1 || return 0
  command -v jq >/dev/null 2>&1 || return 0

  local interview_complete closeout_status
  interview_complete=$(jq -r '.interviewComplete // empty' "$STATE_FILE" 2>/dev/null)
  closeout_status=$(jq -r '.closeoutStatus // empty' "$STATE_FILE" 2>/dev/null)

  # Bail fast when neither lifecycle is complete — avoids an unnecessary cron list call
  if [[ "$interview_complete" != "true" && "$closeout_status" != "done" && "$closeout_status" != "sent" ]]; then
    return 0
  fi

  # Resolve cron UUID: state field first, then name-scan fallback.
  # $1=cron name  $2=state key holding the UUID
  _sweep_resolve_uuid() {
    local cron_name="$1" state_key="$2"
    local uuid=""
    uuid=$(jq -r ".${state_key} // empty" "$STATE_FILE" 2>/dev/null || true)
    if [[ -z "$uuid" || "$uuid" == "null" ]]; then
      # Name-scan fallback (caches the raw list so we only call once per sweep)
      if [[ -z "${_SWEEP_CRON_RAW:-}" ]]; then
        _SWEEP_CRON_RAW=$(openclaw cron list --json 2>/dev/null) || _SWEEP_CRON_RAW=""
      fi
      [[ -z "$_SWEEP_CRON_RAW" ]] && { echo ""; return; }
      if command -v python3 >/dev/null 2>&1; then
        uuid=$(printf '%s' "$_SWEEP_CRON_RAW" | python3 -c "
import json,sys
try:
  data=json.loads(sys.stdin.read())
  jobs=data if isinstance(data,list) else data.get('jobs',[])
  m=[j for j in jobs if j.get('name')=='${cron_name}']
  print(m[0].get('id','') if m else '')
except:
  print('')
" 2>/dev/null || true)
      elif command -v jq >/dev/null 2>&1; then
        uuid=$(printf '%s' "$_SWEEP_CRON_RAW" | jq -r \
          --arg n "$cron_name" \
          '(if type=="array" then . else .jobs//[] end)|map(select(.name==$n))|.[0].id//empty' \
          2>/dev/null || true)
      fi
    fi
    echo "${uuid:-}"
  }

  # Remove one stale lifecycle cron. $1=label $2=cron name $3=state key for UUID
  _sweep_remove() {
    local label="$1" cron_name="$2" state_key="$3"
    if ! _cron_present "$cron_name"; then
      _log "SWEEP $label — cron not present (already removed); skip"
      return 0
    fi
    local uuid
    uuid=$(_sweep_resolve_uuid "$cron_name" "$state_key")
    if [[ -z "$uuid" || "$uuid" == "null" ]]; then
      _log "SWEEP WARN $label — $cron_name present but UUID not resolved; cannot remove this run (will retry next update)"
      return 0
    fi
    if openclaw cron rm "$uuid" >/dev/null 2>&1; then
      _log "SWEEP DONE $label — removed stale $cron_name (uuid=${uuid})"
      # Clear UUID from state (best-effort)
      local tmp; tmp=$(mktemp 2>/dev/null) || true
      if [[ -n "$tmp" ]] && jq ".${state_key} = null" "$STATE_FILE" > "$tmp" 2>/dev/null; then
        mv "$tmp" "$STATE_FILE"
      fi
    else
      _log "SWEEP WARN $label — openclaw cron rm ${uuid} rc!=0 (non-fatal; will retry next run)"
    fi
  }

  local _SWEEP_CRON_RAW=""  # lazy-populated on first name-scan call

  # interview-nudge: stale when interviewComplete==true
  if [[ "$interview_complete" == "true" ]]; then
    _log "SWEEP interviewComplete=true — interview-nudge is a stale lifecycle cron; sweeping"
    _sweep_remove "interview-nudge" "interview-nudge" "interviewNudgeUuid"
  fi

  # closeout-readiness-watchdog: stale when closeoutStatus==done|sent
  if [[ "$closeout_status" == "done" || "$closeout_status" == "sent" ]]; then
    _log "SWEEP closeoutStatus=${closeout_status} — closeout-readiness-watchdog is stale; sweeping"
    _sweep_remove "closeout-watchdog" "closeout-readiness-watchdog" "closeoutWatchdogCronUuid"
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

  # ── STALE-LIFECYCLE-CRON SWEEP (v14.1.7) ────────────────────────────────────
  # Must run BEFORE registrars: sweeps interview-nudge + closeout-readiness-watchdog
  # crons on already-complete boxes so they are not immediately re-added below.
  _sweep_stale_lifecycle_crons

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
  # SINGLETON POOLED BROWSER backstop: HOURLY reaper sweeps orphaned agent-browser
  # sessions/descriptors + tripwires scoped Chromium (NEVER bare chrome/Claude).
  # v14.1.1: throttled */10 -> hourly (13 * * * *). The old */10 cadence ran the
  # reaper 144x/day; on agentTurn boxes that was a ~1.4M-token/day furnace and the
  # diagnostic noise was being announced to the client. Hourly is ample for a
  # crash-leak backstop and joins the 17/37/47 hourly-health family. Registered
  # via _ensure_health_cron, which always creates a COMMAND-kind cron (zero LLM
  # tokens) on the 2026.6.x CLI. The reconcile pass below repairs pre-existing
  # */10 / agentTurn / announce reapers on already-deployed boxes.
  _ensure_health_cron "agent-browser-reaper"     "13 * * * *" "agent-browser-reaper.sh"                   || fails=$((fails + 1))

  # ── GHL TOKEN LIVENESS (Skills 44 + 46) ─────────────────────────────────────
  # Daily at 08:00 UTC: checks if the client's GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN
  # is still exchangeable at securetoken.googleapis.com. On INVALID, the check
  # script sends a plain-English re-grab notification to the CLIENT's own chat.
  # A missing script (Skill 44 not installed) is a SKIP (advisory, not fatal).
  _ensure_ghl_token_liveness || fails=$((fails + 1))

  # ── RECONCILE PASS (v14.1.1) ────────────────────────────────────────────────
  # Repair the DELIVERY/KIND/SCHEDULE of any pre-existing managed cron that the
  # presence-only registrars above left in the old announce+last (and agentTurn
  # */10 reaper) shape. This is what converges silent-by-default on boxes
  # onboarded before the silent-cron change — the registrars only ADD missing
  # crons; this pass REPAIRS existing ones. Advisory (never fatal): a failed edit
  # is logged WARN and retried on the next install/update run.
  _reconcile_managed_crons

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
