#!/usr/bin/env bash
#  OpenClaw Onboarding Installer — Unified (Mac + VPS)
#  PRD 2.1 — unified repo (trevorotts1/openclaw-onboarding)
#  Requires bash (uses `< <(...)`, `[[ ]]`, arrays). Shebang added v16.2.12 so a
#  direct `./install.sh` runs under bash even when the caller's shell is sh/zsh.
#  Branch: prd-2.1-unified-repo
#
#  Run via: curl -fSL --progress-bar https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
#
#  Supports both platforms:
#    Mac mini / macOS   — ~/.openclaw/ config root, ~/Downloads/ for backups
#    Hostinger Docker VPS — /data/.openclaw/ config root (auto-detected)
#
#  Platform detection: OPENCLAW_PLATFORM env var (mac|vps) overrides auto-detect.
#  Auto-detect: presence of /data/.openclaw → vps, otherwise → mac.
#
#  Platform-specific bootstrap lives in platform/mac/bootstrap.sh and
#  platform/vps/bootstrap.sh. These set OC_CONFIG, OC_JSON, and all
#  canonical path variables, then run platform pre-flight checks.
#
#  Canonical paths per platform:
#    Mac:  ~/.openclaw/  |  ~/Downloads/openclaw-master-files/  |  ~/Downloads/openclaw-backups/
#    VPS:  /data/.openclaw/  |  /data/.openclaw/master-files/  |  /data/.openclaw/backups/
#
#  NOTE: set -euo pipefail is NOT set before the platform bootstrap block
#  because VPS container re-exec uses conditional commands that may fail.
# ============================================================

ONBOARDING_VERSION="v19.50.0"

# ----------------------------------------------------------
# Platform detection + bootstrap (MUST run before set -euo pipefail)
# ----------------------------------------------------------
# Determine platform: env override takes priority, then auto-detect.
_DETECT_PLATFORM="${OPENCLAW_PLATFORM:-}"
if [ -z "$_DETECT_PLATFORM" ]; then
    if [ -d "/data/.openclaw" ]; then
        _DETECT_PLATFORM="vps"
    else
        _DETECT_PLATFORM="mac"
    fi
fi
export OPENCLAW_PLATFORM="$_DETECT_PLATFORM"

# Source platform bootstrap (sets OC_CONFIG, OC_JSON, OC_PLATFORM, etc.
# and runs platform-specific pre-flight).
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
_PLATFORM_BOOTSTRAP="${_SCRIPT_DIR}/platform/${OPENCLAW_PLATFORM}/bootstrap.sh"
if [ -f "$_PLATFORM_BOOTSTRAP" ]; then
    # shellcheck source=/dev/null
    source "$_PLATFORM_BOOTSTRAP"
else
    # Fallback when running via curl (no local repo clone yet).
    # Inline the minimal path setup required before the clone happens.
    if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
        OC_PLATFORM="vps"
        OC_CONFIG="/data/.openclaw"
        OC_JSON="/data/.openclaw/openclaw.json"
        OC_SECRETS_ENV="/data/.openclaw/secrets/.env"
        OC_WORKSPACE_DEFAULT="/data/.openclaw/workspace"
        OC_CREDENTIALS="/data/.openclaw/credentials"
        OC_AGENTS="/data/.openclaw/agents"
        OC_SKILLS_DIR="/data/.openclaw/skills"
        OC_LOGS="/data/.openclaw/logs"
        OC_BACKUPS="/data/.openclaw/backups"
        OC_INSTALL_LOG_DIR="/data/.openclaw/logs/install"
        OC_AUTH_PROFILES="/data/.openclaw/agents/main/agent/auth-profiles.json"
        OC_DOWNLOADS="/data/Downloads"
        # v13.8.3: set LOG_FILE on the VPS curl-fallback path too. Without it,
        # `note "Log file: $LOG_FILE"` (and every `>> "$LOG_FILE"`) aborts under
        # `set -euo pipefail` with `LOG_FILE: unbound variable`. Mirrors the mac
        # fallback branch below and platform/vps/bootstrap.sh §7.
        mkdir -p "$OC_INSTALL_LOG_DIR"
        LOG_FILE="$OC_INSTALL_LOG_DIR/openclaw-install-$(date +%Y%m%d-%H%M%S).log"
        exec 1> >(tee -a "$LOG_FILE") 2>&1
    else
        OC_PLATFORM="mac"
        OC_CONFIG="$HOME/.openclaw"
        OC_JSON="$HOME/.openclaw/openclaw.json"
        OC_CREDENTIALS="$HOME/.openclaw/credentials"
        OC_AGENTS="$HOME/.openclaw/agents"
        OC_SKILLS_DIR="$HOME/.openclaw/skills"
        OC_LOGS="$HOME/.openclaw/logs"
        OC_AUTH_PROFILES="$HOME/.openclaw/agents/main/agent/auth-profiles.json"
        OC_SECRETS_ENV="$HOME/.openclaw/secrets/.env"
        OC_DOWNLOADS="$HOME/Downloads"
        OC_BACKUPS="$HOME/Downloads/openclaw-backups"
        OC_INSTALL_LOG_DIR="$HOME/Downloads/openclaw-backups/install-logs"
        OC_LEGACY_CLAWD="$HOME/clawd"
        OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"
        mkdir -p "$OC_BACKUPS" "$OC_INSTALL_LOG_DIR"
        LOG_FILE="$OC_INSTALL_LOG_DIR/openclaw-install-$(date +%Y%m%d-%H%M%S).log"
        exec 1> >(tee -a "$LOG_FILE") 2>&1
    fi
fi

set -euo pipefail

# ----------------------------------------------------------
# Shared library — source if available (best-effort, never required).
# Provides detect_platform(), find_master_files(), and other helpers
# used by update-skills.sh / check-updates.sh / skills' QC scripts.
# ----------------------------------------------------------
_lib_shared_self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-shared.sh"
if [ -f "$_lib_shared_self" ]; then
  # shellcheck source=/dev/null
  source "$_lib_shared_self"
  export OPENCLAW_LIB_SHARED_SOURCED=1
fi

# ----------------------------------------------------------
# Onboarding state-machine (v10.16.48 — FIX 1 ONBOARDING HONESTY).
# Canonical file: lib-onboarding-state.sh (sourced by both platforms).
# ----------------------------------------------------------
_lib_onboarding_state_self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-onboarding-state.sh"
if [ -f "$_lib_onboarding_state_self" ]; then
  # shellcheck source=/dev/null
  source "$_lib_onboarding_state_self"
  export OPENCLAW_LIB_ONBOARDING_STATE_SOURCED=1
fi
# No-op fallbacks so the rest of install.sh never aborts if the lib is missing.
command -v oc_state_seed          >/dev/null 2>&1 || oc_state_seed()          { :; }
command -v oc_onboarding_complete >/dev/null 2>&1 || oc_onboarding_complete() { return 1; }
command -v oc_state_summary       >/dev/null 2>&1 || oc_state_summary()       { OC_VERIFIED=0; OC_TOTAL=0; OC_FAILED_LIST=""; OC_PENDING_LIST=""; OC_INTERVIEW_LIST=""; }

# ----------------------------------------------------------
# Shared onboarding-resume cron installer (v17.0.21). SINGLE canonical
# definition of install_onboarding_resume_cron(), shared with update-skills.sh
# so the roll/hot-patch path installs the SAME SILENT, bounded, self-removing
# resume cron with no copy-paste drift. Best-effort source.
# ----------------------------------------------------------
_lib_resume_cron_self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-onboarding-resume-cron.sh"
if [ -f "$_lib_resume_cron_self" ]; then
  # shellcheck source=/dev/null
  source "$_lib_resume_cron_self"
  export OPENCLAW_LIB_RESUME_CRON_SOURCED=1
fi
# No-op fallback so Step 13b never aborts if the lib is missing (older bundle).
command -v install_onboarding_resume_cron >/dev/null 2>&1 || install_onboarding_resume_cron() { :; }

# ── Runtime-compatible SILENT main-session cron helper (fix/cron-flag-skew). ───
# Guaranteed here at top-level (before any cron-installing function runs). The
# resume-cron lib sourced just above also defines this — guarded so its copy
# wins. Registers a SILENT main-session cron with the flags the INSTALLED runtime
# accepts: 2026.6.11+ REMOVED `--session-target` and requires `--session main
# --system-event` for main-session jobs; older CLIs use `--session-target main
# --message`. Probes `openclaw cron add --help`, falls through every known-good
# form, and degrades to a SILENT isolated agent-message job — never hard-fails.
#   $1 name  $2 agent  $3 cron-expr  $4 tz  $5 prompt ; $6.. = extra flags
command -v _oc_cron_silent_main >/dev/null 2>&1 || _oc_cron_silent_main() {
    local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5"; shift 5
    local _extra=( "$@" ); local _n=${#_extra[@]}
    local _base=( --name "$_name" --agent "$_agent" --cron "$_expr" --tz "$_tz" )
    local _help _modern=0
    _help="$(openclaw cron add --help 2>&1 || true)"
    printf '%s' "$_help" | grep -qE '^[[:space:]]*--session[[:space:]<]' && _modern=1
    local _order _k
    if [ "$_modern" = "1" ]; then _order="modern old"; else _order="old modern"; fi
    for _k in $_order; do
        if [ "$_k" = "modern" ]; then
            [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
            openclaw cron create "${_base[@]}" --session main --system-event "$_prompt" >/dev/null 2>&1 && return 0
        else
            [ "$_n" -gt 0 ] && openclaw cron create "${_base[@]}" "${_extra[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
            openclaw cron create "${_base[@]}" --session-target main --message "$_prompt" >/dev/null 2>&1 && return 0
        fi
    done
    openclaw cron create "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --tz "$_tz" --session main >/dev/null 2>&1 && return 0
    openclaw cron create "${_base[@]}" --message "$_prompt" --no-deliver >/dev/null 2>&1 && return 0
    return 1
}

# ── JSON-exact cron presence check (fix/industry-gate-and-idempotent-crons). ───
# `openclaw cron list`'s TEXT TABLE truncates names longer than ~22 chars, so a
# positive-presence check via `grep -qi "<name>"` against that table
# false-negatives on a longer name and re-registers a duplicate on every re-run
# (the confirmed root cause of the Skill 39 / Skill 38 6x-duplicate incident —
# see shared-utils/cron-lib.sh). Several of install.sh's OWN cron names exceed
# that threshold too (workforce-build-resume=23, watchdog-onboarding-loop=25,
# closeout-readiness-watchdog=28), so this helper is sourced/defined here once
# and reused by every Step-13.x installer below instead of each re-doing its own
# (buggy) text-table grep.
_lib_cron_present_self="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/shared-utils/cron-lib.sh"
if [ -f "$_lib_cron_present_self" ]; then
  # shellcheck source=/dev/null
  source "$_lib_cron_present_self"
fi
command -v oc_cron_present >/dev/null 2>&1 || oc_cron_present() {
    local _name="$1" _raw
    _raw=$(openclaw cron list --json 2>/dev/null) || _raw=""
    if [ -n "$_raw" ] && command -v jq >/dev/null 2>&1; then
        printf '%s' "$_raw" | jq -e --arg n "$_name" '
          ( if type == "array" then . else .jobs // [] end ) | map(select(.name == $n)) | length > 0
        ' >/dev/null 2>&1
        return $?
    fi
    if [ -n "$_raw" ] && command -v python3 >/dev/null 2>&1; then
        OC_CRON_RAW="$_raw" python3 - "$_name" 2>/dev/null <<'PYEOF'
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
        return $?
    fi
    return 1
}
# DURABLE TOMBSTONE fallback (fix/industry-gate-and-idempotent-crons, live-VPS
# finding): if shared-utils/cron-lib.sh wasn't found above, oc_cron_tombstoned
# is undefined — fail OPEN (never tombstoned) rather than block registration
# outright over a missing helper file. When the shared lib IS found, its real
# oc_cron_tombstoned (durable file-marker check) is used instead.
command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }

# ----------------------------------------------------------
# Path variables are already set by the platform bootstrap block above.
# Re-export derived vars for backward compat with existing skill scripts
# that reference OC_WORKSPACE (used before OC_WORKSPACE_DEFAULT existed).
# ----------------------------------------------------------
OC_WORKSPACE="${OC_WORKSPACE_DEFAULT}"

# ----------------------------------------------------------
# FRESH-INSTALL DETECTION (chore/silent-kickoff — WE MOVE IN SILENCE).
# ----------------------------------------------------------
# The interactive onboarding kickoff handshake (the "paste this to start"
# Telegram message sent by send_kickoff_telegram) is OWNER-FACING. It must fire
# ONLY on a true fresh, never-onboarded box — NEVER on an update / re-roll of a
# box that was already onboarded (firing it then is unsolicited chatter to an
# existing client, exactly what the silent-updater work kills).
#
# Capture freshness HERE, before any install step writes the .onboarding-version
# stamp (Step 10b) or copies skills, so we read the box's PRE-INSTALL state. A
# box is "already onboarded" if it carries an .onboarding-version marker
# (install.sh itself writes this on every prior run) OR an existing openclaw.json
# with at least one configured agent. Default-safe: anything that trips a marker
# is treated as NOT fresh (silent); only a clean, never-onboarded box is fresh.
OPENCLAW_IS_FRESH_INSTALL=1
for _vm in \
    "$HOME/.openclaw/skills/.onboarding-version" \
    "/data/.openclaw/skills/.onboarding-version" \
    "$HOME/Downloads/openclaw-master-files/.onboarding-version" \
    "$HOME/.openclaw/onboarding/.onboarding-version"; do
    if [ -f "$_vm" ]; then OPENCLAW_IS_FRESH_INSTALL=0; break; fi
done
if [ "$OPENCLAW_IS_FRESH_INSTALL" = "1" ] && command -v python3 >/dev/null 2>&1; then
    for _ocj in "$HOME/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json"; do
        if [ -f "$_ocj" ] && OC_J="$_ocj" python3 -c '
import json, os, sys
try:
    d = json.load(open(os.environ["OC_J"]))
except Exception:
    sys.exit(1)
agents = (d.get("agents", {}) or {}).get("list", []) or []
sys.exit(0 if agents else 1)
' 2>/dev/null; then
            OPENCLAW_IS_FRESH_INSTALL=0; break
        fi
    done
fi
export OPENCLAW_IS_FRESH_INSTALL
if [ "$OPENCLAW_IS_FRESH_INSTALL" = "1" ]; then
    echo "[fresh-install] no prior onboarding stamp/config — FRESH install; the owner kickoff handshake will fire."
else
    echo "[fresh-install] prior onboarding detected — UPDATE/RE-ROLL; the owner kickoff handshake is SUPPRESSED (WE MOVE IN SILENCE)."
fi

# ----------------------------------------------------------
# Bash 3.2 Compatible UI Helpers
# ----------------------------------------------------------
step() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

success() {
    echo "  ✓ $1"
}

note() {
    echo "  ℹ️  $1"
}

warn() {
    echo "  ⚠️  $1"
}

error() {
    echo ""
    echo "  ✗ ERROR: $1"
    echo ""
}

# ----------------------------------------------------------
# Cron-create positional-form fallback (v14.1.3 — 2026.6.8 flag drift)
# ----------------------------------------------------------
# DEFECT: every silent-cron chain in this installer registers crons with the
# flag form `openclaw cron create --cron "<expr>" --message "<prompt>"
# --session-target main [--light-context]`. On OpenClaw 2026.6.8 (verified
# against docs.openclaw.ai/cli/cron) the CANONICAL surface is:
#     openclaw cron create "<schedule>" "<prompt>" --name N --agent A --session main [--light-context] [--tz Z]
# i.e. the schedule + prompt are POSITIONAL, and the session flag is `--session`
# (NOT `--cron`/`--message`/`--session-target`). When the flag form is rejected
# the cron silently fails to register (the chains are guarded so the install
# does NOT abort, but the cron is simply absent). This helper provides the
# docs-canonical positional form as a FINAL fallback the per-site chains call
# after their existing flag-form attempts — strictly additive, so boxes where
# the old flag form still works are untouched, and 2026.6.8 boxes recover the
# cron. OS-portable (pure CLI). Returns 0 on success.
#   $1=name  $2=agent  $3=cron-expr  $4=tz  $5=prompt  $6="lc" to add --light-context
_cron_create_positional() {
    local _name="$1" _agent="$2" _expr="$3" _tz="$4" _prompt="$5" _lc="${6:-}"
    local _args=( "$_expr" "$_prompt" --name "$_name" --agent "$_agent" --session main )
    [ -n "$_tz" ] && _args+=( --tz "$_tz" )
    [ "$_lc" = "lc" ] && _args+=( --light-context )
    local _out="" _rc=0
    _out=$(openclaw cron create "${_args[@]}" 2>&1) || _rc=$?
    echo "$_out" >> "${LOG_FILE:-/dev/null}"
    return "$_rc"
}

# ----------------------------------------------------------
# Bash 3.2 Compatible Arrays (Indexed only)
# ----------------------------------------------------------
SKILLS_INSTALLED=""
SKILLS_UPDATED=""
SKILLS_SKIPPED=""
SKILL_COUNT=0

add_to_list() {
    local list_name="$1"
    local item="$2"
    case "$list_name" in
        installed) SKILLS_INSTALLED="$SKILLS_INSTALLED|$item" ;;
        updated) SKILLS_UPDATED="$SKILLS_UPDATED|$item" ;;
        skipped) SKILLS_SKIPPED="$SKILLS_SKIPPED|$item" ;;
    esac
}

count_list() {
    local list="$1"
    list="${list#|}"
    if [ -z "$list" ]; then
        echo "0"
    else
        echo "$list" | tr '|' '\n' | wc -l | tr -d ' '
    fi
}

# ----------------------------------------------------------
# Bulletproof Mac Telegram chat ID resolver (v10.0.0)
# ----------------------------------------------------------
# On Mac, the canonical pairing flow always succeeds before onboarding runs.
# If we don't find a chat ID, it's because we didn't look in the right place.
# This resolver searches 23 locations in priority order, stops at first hit,
# logs which source matched.
#
# Tier 1 — primary Mac locations:
#   1. openclaw config get channels.telegram.allowFrom
#   2. openclaw config get commands.ownerAllowFrom
#   3. ~/.openclaw/credentials/telegram-*-allowFrom.json glob
#   4. ~/.openclaw/credentials/telegram-pairing.json
# Tier 2 — alternate schema:
#   5. channels.telegram.groupAllowFrom
#   6. commands.allowFrom.telegram (older schema)
#   7. plugins.entries.telegram.config.allowFrom
# Tier 3 — per-agent bindings:
#   8. agents.list[*].bindings.telegram.chatId
#   9. agents.list[*].channels.telegram
# Tier 4 — Mac config files in multiple known locations:
#   10. ~/.openclaw/openclaw.json (direct)
#   11. ~/Library/Application Support/openclaw/openclaw.json
#   12. ~/.config/openclaw/openclaw.json
#   13. ~/.openclaw-dev/openclaw.json (dev profile)
# Tier 5 — runtime CLI introspection:
#   14. openclaw channels telegram list
#   15. openclaw devices list --json
# Tier 6 — Mac secrets/env files:
#   16. ~/.openclaw/secrets/.env
#   17. ~/.openclaw/.env
#   18. ~/clawd/secrets/.env (legacy)
#   19. env.vars block in openclaw.json
#   20. Mac shell env: TELEGRAM_CHAT_ID, TELEGRAM_OWNER_ID, TG_CHAT_ID, etc
# Tier 7 — exhaustive last-resort:
#   21. Recursive walk of ~/.openclaw/ for any JSON with telegram chat IDs
#   22. Recursive walk of ~/clawd/ for telegram-related configs
#   23. Audit log scan: ~/.openclaw/logs/*.jsonl for pairing.approved events
#
# Validation: chat ID must be 6-20 digits (optional leading -), must NOT be
# the bot's own ID.

TELEGRAM_LAST_RESULT=""
TELEGRAM_TARGET_CACHED=""
TELEGRAM_ACCOUNT_CACHED=""
TELEGRAM_SOURCE_CACHED=""
TELEGRAM_RESOLVED=false

resolve_telegram_target_universal() {
    local result
    result=$(python3 - <<'PYEOF' 2>/dev/null
import json, os, glob, subprocess, re

HOME = os.path.expanduser("~")
OC_CONFIG = os.path.join(HOME, ".openclaw")
OC_JSON = os.path.join(OC_CONFIG, "openclaw.json")
OC_CREDS = os.path.join(OC_CONFIG, "credentials")
OC_LOGS = os.path.join(OC_CONFIG, "logs")

# BUG-FIX (fix/cron-owner-chat-routing): these are OPERATOR chat IDs (Trevor /
# E.R. Spaulding / LeAnne Dolce).  They must NEVER be returned as a client
# owner-chat target — doing so routes every cron delivery to the operator
# instead of the client.  Confirmed live misrouting on multiple client boxes
# (all crons wired to the operator ID instead of the client).
# The operator's Mac env may export TELEGRAM_CHAT_ID=5252140759 (or equivalent)
# and the SSH session that runs install.sh inherits it, causing S20 to resolve
# the operator ID instead of the client owner ID.
OPERATOR_CHAT_IDS = {"5252140759", "6663821679", "6771245262"}

def is_chat_id(v, bot_id=""):
    if not isinstance(v, (str, int)): return False
    s = str(v).strip().replace("telegram:", "").replace("tg:", "")
    if not s: return False
    digits = s.lstrip("-")
    if not (digits.isdigit() and 6 <= len(digits) <= 20): return False
    if bot_id and s == bot_id: return False
    # NEVER return a known operator chat ID as the client owner target.
    if s in OPERATOR_CHAT_IDS: return False
    return s

def cli_get(path):
    try:
        r = subprocess.run(["openclaw", "config", "get", path],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0 or not r.stdout.strip(): return None
        return r.stdout.strip()
    except Exception: return None

def parse_json_safe(s):
    try: return json.loads(s)
    except Exception: return None

# Load openclaw.json once
cfg = {}
try: cfg = json.load(open(OC_JSON))
except Exception: pass

bot_id = ""
bt = cfg.get("channels", {}).get("telegram", {}).get("botToken", "") or ""
if ":" in bt:
    bot_id = bt.split(":")[0]

result_chat = ""
result_account = ""
result_source = ""

def try_value(val, src, account_hint=""):
    global result_chat, result_account, result_source
    if result_chat: return
    if val is None: return
    cid = is_chat_id(val, bot_id)
    if cid:
        result_chat = cid
        result_account = account_hint
        result_source = src

def try_list(values, src, account_hint=""):
    if result_chat: return
    if not isinstance(values, list): return
    for v in values:
        cid = is_chat_id(v, bot_id)
        if cid:
            try_value(cid, src, account_hint); return

# ─── S0: OPENCLAW_OWNER_CHAT_ID env var — explicit operator override ───
# The operator may set this before running install to pin the correct owner
# chat ID for boxes where auto-detection is ambiguous.  Checked FIRST so it
# wins before any config-file walk.  Operator IDs are still rejected by
# is_chat_id() — this slot is for the CLIENT owner only.
_s0 = os.environ.get("OPENCLAW_OWNER_CHAT_ID", "").strip()
if _s0:
    try_value(_s0, "S0:env.OPENCLAW_OWNER_CHAT_ID")

# ─── S1: channels.telegram.allowFrom (Mac primary) ───
raw = cli_get("channels.telegram.allowFrom")
if raw:
    data = parse_json_safe(raw)
    if isinstance(data, list): try_list(data, "S1:channels.telegram.allowFrom (CLI)")
elif "allowFrom" in cfg.get("channels", {}).get("telegram", {}):
    try_list(cfg["channels"]["telegram"]["allowFrom"], "S1:channels.telegram.allowFrom (json)")

# ─── S2: commands.ownerAllowFrom ───
if not result_chat:
    raw = cli_get("commands.ownerAllowFrom")
    if raw:
        data = parse_json_safe(raw)
        if isinstance(data, list): try_list(data, "S2:commands.ownerAllowFrom (CLI)")
    elif "ownerAllowFrom" in cfg.get("commands", {}):
        try_list(cfg["commands"]["ownerAllowFrom"], "S2:commands.ownerAllowFrom (json)")

# ─── S3: credentials/telegram-*-allowFrom.json ───
if not result_chat and os.path.isdir(OC_CREDS):
    try: fnames = sorted(os.listdir(OC_CREDS))
    except Exception: fnames = []
    fnames.sort(key=lambda f: ("default" not in f, f))
    for fname in fnames:
        m = re.match(r"^telegram-(.+)-allowFrom\.json$", fname)
        if not m: continue
        try: data = json.load(open(os.path.join(OC_CREDS, fname)))
        except Exception: continue
        try_list(data.get("allowFrom") or [], f"S3:credentials/{fname}", m.group(1))
        if result_chat: break

# ─── S4: credentials/telegram-pairing.json ───
if not result_chat:
    pp = os.path.join(OC_CREDS, "telegram-pairing.json")
    if os.path.isfile(pp):
        try: data = json.load(open(pp))
        except Exception: data = {}
        def walk_pair(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if any(x in k.lower() for x in ("chat", "user", "owner")):
                        cid = is_chat_id(v, bot_id)
                        if cid: return cid
                    r = walk_pair(v)
                    if r: return r
            elif isinstance(obj, list):
                for it in obj:
                    r = walk_pair(it)
                    if r: return r
            return None
        found = walk_pair(data)
        if found: try_value(found, "S4:credentials/telegram-pairing.json")

# ─── S5: channels.telegram.groupAllowFrom ───
if not result_chat:
    try_list(cfg.get("channels", {}).get("telegram", {}).get("groupAllowFrom", []),
             "S5:channels.telegram.groupAllowFrom")

# ─── S6: commands.allowFrom.telegram (older schema) ───
if not result_chat:
    af = cfg.get("commands", {}).get("allowFrom", {})
    if isinstance(af, dict): try_list(af.get("telegram", []), "S6:commands.allowFrom.telegram")

# ─── S7: plugins.entries.telegram.config.allowFrom ───
if not result_chat:
    pte = cfg.get("plugins", {}).get("entries", {}).get("telegram", {})
    try_list(pte.get("config", {}).get("allowFrom", []), "S7:plugins.entries.telegram.config.allowFrom")

# ─── S8 + S9: per-agent bindings & channels ───
if not result_chat:
    for i, ag in enumerate(cfg.get("agents", {}).get("list", []) or []):
        if not isinstance(ag, dict): continue
        bind = (ag.get("bindings") or {}).get("telegram") or {}
        if isinstance(bind, dict):
            for key in ("chatId", "chatID", "userId", "id"):
                cid = is_chat_id(bind.get(key, ""), bot_id)
                if cid:
                    try_value(cid, f"S8:agents.list[{i}].bindings.telegram.{key}"); break
        if result_chat: break
        ch = (ag.get("channels") or {}).get("telegram") or {}
        if isinstance(ch, dict):
            for key in ("chatId", "userId", "allowFrom"):
                v = ch.get(key)
                if isinstance(v, list): try_list(v, f"S9:agents.list[{i}].channels.telegram.{key}")
                else:
                    cid = is_chat_id(v, bot_id)
                    if cid: try_value(cid, f"S9:agents.list[{i}].channels.telegram.{key}")
        if result_chat: break

# ─── S10-S13: Mac config files in multiple known locations ───
if not result_chat:
    extra_paths = [
        os.path.join(HOME, "Library", "Application Support", "openclaw", "openclaw.json"),
        os.path.join(HOME, ".config", "openclaw", "openclaw.json"),
        os.path.join(HOME, ".openclaw-dev", "openclaw.json"),
    ]
    for p in extra_paths:
        if not os.path.isfile(p): continue
        try: extra_cfg = json.load(open(p))
        except Exception: continue
        try_list(extra_cfg.get("channels", {}).get("telegram", {}).get("allowFrom", []),
                 f"S10-13:extra-config:{os.path.basename(p)}")
        if result_chat: break

# ─── S14 + S15: CLI live introspection ───
if not result_chat:
    for cmd in (["channels", "telegram", "list", "--json"],
                ["pairing", "list", "telegram", "--json"]):
        try:
            r = subprocess.run(["openclaw"] + cmd, capture_output=True, text=True, timeout=10)
            if r.returncode != 0: continue
            data = parse_json_safe(r.stdout) or []
            def walk_cmd(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if any(x in k.lower() for x in ("chat", "user", "owner", "allowfrom")):
                            cid = is_chat_id(v, bot_id)
                            if cid: return cid
                        r = walk_cmd(v)
                        if r: return r
                elif isinstance(obj, list):
                    for it in obj:
                        r = walk_cmd(it)
                        if r: return r
            found = walk_cmd(data)
            if found: try_value(found, f"S14-15:cli {' '.join(cmd)}")
            if result_chat: break
        except Exception: continue

# ─── S16-S18: Mac secrets/env files ───
if not result_chat:
    env_files = [
        os.path.join(HOME, ".openclaw", "secrets", ".env"),
        os.path.join(HOME, ".openclaw", ".env"),
        os.path.join(HOME, "clawd", "secrets", ".env"),
    ]
    keys = ("TELEGRAM_CHAT_ID", "TELEGRAM_OWNER_ID", "TG_CHAT_ID", "TELEGRAM_USER_ID")
    for envf in env_files:
        if not os.path.isfile(envf): continue
        try:
            for line in open(envf):
                line = line.strip()
                if "=" not in line or line.startswith("#"): continue
                k, _, v = line.partition("=")
                if k in keys and v:
                    v = v.strip().strip('"').strip("'")
                    cid = is_chat_id(v, bot_id)
                    if cid: try_value(cid, f"S16-18:{envf}:{k}"); break
            if result_chat: break
        except Exception: continue

# ─── S19: env.vars block inside openclaw.json (Trevor's inline pattern) ───
if not result_chat:
    env_vars = cfg.get("env", {}).get("vars", {})
    for k in ("TELEGRAM_CHAT_ID", "TELEGRAM_OWNER_ID", "TG_CHAT_ID", "TELEGRAM_USER_ID"):
        v = env_vars.get(k, "")
        cid = is_chat_id(v, bot_id)
        if cid: try_value(cid, f"S19:env.vars.{k}"); break

# ─── S20: Mac shell env vars ───
if not result_chat:
    for var in ("TELEGRAM_CHAT_ID", "TELEGRAM_OWNER_ID", "TG_CHAT_ID", "TELEGRAM_USER_ID"):
        v = (os.environ.get(var) or "").strip()
        if not v: continue
        cid = is_chat_id(v, bot_id)
        if cid: try_value(cid, f"S20:env.{var}"); break

# ─── S21: exhaustive recursive walk of ~/.openclaw/ ───
if not result_chat:
    KEY_HINTS = ("telegram", "chat", "allowfrom", "owner", "user")
    def deep_walk(obj, under_tel=False):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower()
                tel_branch = under_tel or "telegram" in kl
                key_hit = any(h in kl for h in KEY_HINTS)
                if (tel_branch or key_hit):
                    cid = is_chat_id(v, bot_id)
                    if cid: return cid
                    if isinstance(v, list):
                        for it in v:
                            cid = is_chat_id(it, bot_id)
                            if cid: return cid
                r = deep_walk(v, tel_branch)
                if r: return r
        elif isinstance(obj, list):
            for it in obj:
                r = deep_walk(it, under_tel)
                if r: return r
        return None
    for root, dirs, files in os.walk(OC_CONFIG):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "npm", ".git", "media", "logs", "tmp", "cache")]
        for f in files:
            if not f.endswith(".json"): continue
            p = os.path.join(root, f)
            try: data = json.load(open(p))
            except Exception: continue
            found = deep_walk(data)
            if found:
                try_value(found, f"S21:walk:{os.path.relpath(p, OC_CONFIG)}")
                break
        if result_chat: break

# ─── S22: recursive walk of ~/clawd/ for telegram configs ───
if not result_chat and os.path.isdir(os.path.join(HOME, "clawd")):
    for root, dirs, files in os.walk(os.path.join(HOME, "clawd")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", ".clawhub", ".agents")]
        if root.count(os.sep) - os.path.join(HOME, "clawd").count(os.sep) > 3: continue  # max depth 3
        for f in files:
            if not (f.endswith(".json") or f.endswith(".md")): continue
            if "telegram" not in f.lower() and "config" not in f.lower(): continue
            p = os.path.join(root, f)
            try:
                if f.endswith(".json"):
                    data = json.load(open(p))
                    found = deep_walk(data) if 'deep_walk' in dir() else None
                    if found: try_value(found, f"S22:walk:{os.path.relpath(p, HOME)}"); break
            except Exception: continue
        if result_chat: break

# ─── S23: audit log scan ───
if not result_chat and os.path.isdir(OC_LOGS):
    for f in sorted(os.listdir(OC_LOGS), reverse=True)[:5]:  # last 5 log files
        if not f.endswith(".jsonl"): continue
        try:
            for line in open(os.path.join(OC_LOGS, f)):
                if "pairing" not in line.lower(): continue
                if "approved" not in line.lower() and "accept" not in line.lower(): continue
                rec = parse_json_safe(line)
                if not rec: continue
                def walk_rec(o):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            if any(x in str(k).lower() for x in ("chat", "user", "owner")):
                                cid = is_chat_id(v, bot_id)
                                if cid: return cid
                            r = walk_rec(v)
                            if r: return r
                    elif isinstance(o, list):
                        for it in o:
                            r = walk_rec(it)
                            if r: return r
                found = walk_rec(rec)
                if found: try_value(found, f"S23:logs/{f}"); break
            if result_chat: break
        except Exception: continue

print(f"{result_chat}|{result_account}|{result_source}")
PYEOF
)
    TELEGRAM_TARGET_CACHED=$(echo "$result" | cut -d'|' -f1)
    TELEGRAM_ACCOUNT_CACHED=$(echo "$result" | cut -d'|' -f2)
    TELEGRAM_SOURCE_CACHED=$(echo "$result" | cut -d'|' -f3-)
    TELEGRAM_RESOLVED=true
    if [ -n "$TELEGRAM_TARGET_CACHED" ]; then
        local acc_note=""
        [ -n "$TELEGRAM_ACCOUNT_CACHED" ] && acc_note=" (account=$TELEGRAM_ACCOUNT_CACHED)"
        note "Telegram target resolved: $TELEGRAM_TARGET_CACHED$acc_note via $TELEGRAM_SOURCE_CACHED"
    else
        warn "Telegram chat ID NOT FOUND in any of 23 search locations."
        warn "This should not happen on a paired Mac install."
        warn "Dumping each source's actual state for debugging:"
        {
            echo "--- channels.telegram.allowFrom (CLI):"
            openclaw config get channels.telegram.allowFrom 2>&1 || true
            echo "--- commands.ownerAllowFrom (CLI):"
            openclaw config get commands.ownerAllowFrom 2>&1 || true
            echo "--- credentials/ listing:"
            ls -la "$OC_CREDENTIALS/" 2>&1 || true
            echo "--- env (telegram-related):"
            printenv | grep -iE "^(TELEGRAM_|TG_)" 2>&1 || true
        } | sed 's/^/    /' | head -50
    fi
}

# v10.13.5: Resolve owner first name from env var or openclaw.json. Shared
# helper used by both early-kickoff (after Step 10) and final triplet.
resolve_owner_name() {
    local oc_json="${1:-$HOME/.openclaw/openclaw.json}"
    [ -d "/data/.openclaw" ] && oc_json="/data/.openclaw/openclaw.json"
    local name
    name=$(python3 -c "
import json, os, sys
candidates = []
env_name = os.environ.get('OPENCLAW_OWNER_NAME','').strip()
if env_name: candidates.append(env_name)
try:
    d = json.load(open('$oc_json'))
    for path in (('meta','ownerName'), ('owner','name'), ('wizard','ownerName'),
                 ('meta','owner','name'), ('owner','firstName')):
        cur = d
        for k in path:
            cur = cur.get(k, {}) if isinstance(cur, dict) else {}
        if isinstance(cur, str) and cur.strip():
            candidates.append(cur.strip())
            break
except Exception:
    pass
for n in candidates:
    print(n.split()[0]); sys.exit(0)
" 2>/dev/null)
    echo "${name:-there}"
}

# v10.13.11: SINGLE unified message mirroring VPS v10.14.7+ pattern.
# Replaces the v10.13.6 two-message split (intro + paste block) which made
# Mac UX worse than VPS — no scissor lines, no friendly closing, double
# waiting. VPS-style: ONE message containing friendly opening + scissor-
# delimited paste block + friendly closing. Mac-specific content (paths,
# wave cap, platform discriminator) substituted in.
#
# Size budget: ~3,950 UTF-16 units after substitution (well under Telegram's
# 4,096 limit). Achieved by using `~/.openclaw` paths (11 chars) instead of
# `$HOME/.openclaw` expansion (~24 chars on a real Mac). Agent expands `~`
# at execution time — owner pastes literal text.
#
# Apostrophe-free body required by macOS bash 3.2 quoted-heredoc-in-$() parser
# (see v10.13.6 changelog). Uses "do not" / "is not" / "I will" verbatim.
build_kickoff_paste_block() {
    # Legacy shim — kept for back-compat. Returns ONLY the paste block (between
    # scissor lines). New code should call build_kickoff_telegram_message which
    # wraps this with the friendly opening + closing.
    local owner_name="$1"
    local template
    template=$(cat <<'PASTEEOF'
Start the OpenClaw onboarding process. Follow this procedure exactly.

DEPLOYMENT PLATFORM — READ THIS FIRST:
This is a Mac mini install (local macOS). All paths under ~/.openclaw/. When INSTALL-CONTRACT.md, START HERE.md, or any doc has BOTH "Mac mini" AND "VPS" sections, USE ONLY THE MAC MINI SECTION. Skip every "VPS" reference.
- Wave concurrency cap: 10 helpers max (NOT 5 — that is VPS)
- File paths: ~/.openclaw/ (NOT /data/.openclaw/ — that is VPS)
- Backups: ~/Downloads/openclaw-backups/ (NOT /data/.openclaw/backups/)
- Process supervision: macOS launchd (NOT container nohup)

Default to Mac when ambiguous. Do NOT ask __OWNER_NAME__ ("Mac or VPS?") — always Mac.

PHASE 1 — Read the docs first (do not skip):
1. Read ~/.openclaw/Start Here.md end to end.
2. Read ~/.openclaw/INSTALL-CONTRACT.md end to end. Non-negotiable: Rule 0 (wave cap = 10), Rule 1 (read every .md first), Rule 16 (read INSTALL-GOTCHAS.md).
3. Run web research pre-flight: bash ~/.openclaw/scripts/web-research-preflight.sh
4. Settings: maxChars=200000, maxTotalChars=400000, maxSpawnDepth=4, maxChildren=20, maxConcurrent=100, thinking=high.
5. Set up workspace files (USER.md, AGENTS.md, TOOLS.md at workspace root, symlinked into per-role workspaces).

PHASE 2 — Install skills in waves, with PROGRESS UPDATES to __OWNER_NAME__:
Before each wave, send __OWNER_NAME__ a Telegram message in PLAIN ENGLISH (no jargon): Starting Wave 2 of 5 — about to set up X skills, ~Y minutes.
After each wave: Wave 2 done. X skills working. Now starting Wave 3.
Gate each wave: bash ~/.openclaw/scripts/check-wave-concurrency.sh --proposed N --reason wave-N
Skill folders live at ~/.openclaw/skills/01-... through ~/.openclaw/skills/61-... (56 active + 5 archived).
Per skill: read all .md + scripts, execute INSTALL.md in order, score >= 8.5/10, up to 5 retry loops.

PHASE 3 — Verify:
6. Run ~/.openclaw/scripts/qc-system-integrity.sh — must exit 0.
6b. After Phase 4 workforce build completes, run bash ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh "$(hostname)" --apply — its Step 2b floor-fill (scripts/floor-fill-driver.py, fed by scripts/make-gap-from-staleness.py) idempotently MATERIALIZES any missing canonical floor roles/SOPs (e.g. the v16 per-dept devils-advocate / healer and the video/graphics/presentations expansions) from the box's own role-library. This is a skip-existing, no-clobber completeness backstop: on a fresh fully-built floor it is a no-op, but it guarantees BOTH the install path and the update path end with a complete floor. Then run bash ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-completeness.sh — read-only check that role-library materialization + IDENTITY.md + SOPs landed for every dept. Status must be PASS. On PARTIAL/FAIL the script Telegrams the operator with a per-dept breakdown; do not declare install complete until at PASS or operator explicitly waives.
7. Message __OWNER_NAME__: All skills installed. Ready for the 30-question business interview? About 35 min of your focused time — your answers shape your entire AI team. Reply yes when ready.
Wait for confirmation before proceeding.

PHASE 4 — Build the workforce:
8. Run AI Workforce Interview (Skill 23) with __OWNER_NAME__. ZHC workspace on Mac: ~/.openclaw/workspace/zero-human-company/<slug>/
9. After interview, run ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/create_role_workspaces.py to write per-department governing-personas.md.
10. Message __OWNER_NAME__ confirming workforce is built and listing departments created. Then run bash ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-completeness.sh — if STATUS is PARTIAL or FAIL, follow its Telegram-delivered remediation hints before moving to Phase 5.

PHASE 5 — Wrap up:
11. Walk __OWNER_NAME__ through Telegram supergroup setup (Skill 32 INSTALL.md Phase 2 — 7 manual phone steps, one at a time).
12. Final summary in plain English: what was installed, what is working, what did not work.

HARD RULES:
- No shortcuts. No self-QC.
- All helpers use non-Anthropic models (Ollama Cloud primary, OpenRouter fallback).
- Persona governance on every non-mechanical task.
- Master Orchestrator only dispatches; never does work directly.
- Telegram progress updates between waves are mandatory (N28 binding).
- Speak to __OWNER_NAME__ in plain English. NO jargon (QC, sub-agent, manifest).
PASTEEOF
)
    local msg="${template//__OWNER_NAME__/$owner_name}"
    printf '%s' "$msg"
}

# v10.13.11: Single unified kickoff message — VPS-pattern (one message with
# friendly opening + scissor-delimited paste block + friendly closing).
# Returns the FULL message text the owner sees. send_kickoff_telegram sends it
# as ONE Telegram message; size budgeted to ~3,950 UTF-16 units (under the
# 4,096 limit). Gateway fallback handles any edge cases.
build_kickoff_telegram_message() {
    local owner_name="$1"
    local paste
    paste=$(build_kickoff_paste_block "$owner_name")
    cat <<KICKMSGEOF
Hi ${owner_name}! 👋

Your AI workforce is ready to set up. There is just ONE thing you need to do to start.

📋 Copy the entire message below (everything between the scissor lines), paste it back to me in this chat, and hit Send. That is the only step — I take over from there.

✂️━━━━━━━━━ COPY EVERYTHING BELOW THIS LINE ━━━━━━━━━✂️

${paste}

✂️━━━━━━━━━ COPY EVERYTHING ABOVE THIS LINE ━━━━━━━━━✂️

Once you paste that back to me here and hit Send, I will respond within a minute and start setting up your team. Total setup takes about an hour, including a 30-question business interview in the middle. I will keep you posted as I work. 🚀
KICKMSGEOF
}

# v10.13.5: Send the kickoff message via the most reliable path available.
# Tries openclaw CLI first, then tg_send_direct (direct Bot API). Sets the
# global KICKOFF_TG_FIRED=true on success so the final triplet doesn't dupe.
# Idempotent: returns immediately if already fired.
send_kickoff_telegram() {
    [ "${KICKOFF_TG_FIRED:-false}" = "true" ] && return 0
    # FRESH-INSTALL GATE (WE MOVE IN SILENCE): the owner kickoff handshake fires
    # ONLY on a true fresh install. On an update / re-roll of an already-onboarded
    # box, suppress it — the agent picks up the SILENT AGENTS.md UPDATE-PENDING
    # flag instead; the client gets no unsolicited onboarding chatter. This is the
    # single chokepoint both call sites (early fire + final triplet) flow through.
    # Default-safe: if OPENCLAW_IS_FRESH_INSTALL is unset, treat as NOT fresh.
    if [ "${OPENCLAW_IS_FRESH_INSTALL:-0}" != "1" ]; then
        echo "[kickoff] suppressed — update/re-roll, not a fresh install: no owner-facing onboarding handshake sent (WE MOVE IN SILENCE)" >> "${LOG_FILE:-/dev/null}" 2>&1
        return 1
    fi
    local owner_name msg
    owner_name=$(resolve_owner_name)
    msg=$(build_kickoff_telegram_message "$owner_name")

    # v10.13.11: SINGLE unified message (VPS pattern). Bot API direct first;
    # gateway fallback if size exceeds Telegram limit (the gateway handles
    # long messages — same chain VPS v10.14.7+ uses successfully).
    if tg_send_direct "$msg"; then
        export KICKOFF_TG_FIRED="true"
        export KICKOFF_TG_PATH="direct-bot-api"
        return 0
    fi
    if command -v openclaw >/dev/null 2>&1 && openclaw message send --message "$msg" 2>/dev/null; then
        export KICKOFF_TG_FIRED="true"
        export KICKOFF_TG_PATH="openclaw-cli-gateway"
        return 0
    fi
    return 1
}

# v10.13.4: Direct Bot API send — bypasses gateway entirely. Reads bot token +
# allowed chat ID from openclaw.json. Used as the final fallback when the
# `openclaw message send` gateway path fails. This is what guarantees a paired
# owner ALWAYS gets the kickoff message, even if the gateway is unresponsive,
# scopes aren't right, or the CLI hangs.
tg_send_direct() {
    local message="$1"
    local oc_json="$HOME/.openclaw/openclaw.json"
    [ ! -f "$oc_json" ] && return 1
    local creds
    creds=$(python3 - <<PYEOF 2>/dev/null
import json
try:
    d = json.load(open("$oc_json"))
    tg = d.get("channels", {}).get("telegram", {}) or {}
    bot = tg.get("botToken") or d.get("env", {}).get("vars", {}).get("TELEGRAM_BOT_TOKEN", "")
    chat = ""
    for c in (tg.get("allowFrom") or []):
        chat = str(c); break
    if bot and chat:
        print(f"{bot}|{chat}")
except Exception:
    pass
PYEOF
)
    [ -z "$creds" ] && return 1
    local bot_token chat_id
    bot_token="${creds%|*}"
    chat_id="${creds##*|}"
    [ -z "$bot_token" ] || [ -z "$chat_id" ] && return 1
    # Send via Bot API; return 0 on ok:true, 1 otherwise
    local resp
    resp=$(curl -s --max-time 10 "https://api.telegram.org/bot${bot_token}/sendMessage" \
        --data-urlencode "chat_id=${chat_id}" \
        --data-urlencode "text=${message}" 2>/dev/null)
    case "$resp" in
        *'"ok":true'*) echo "$resp" >> "$LOG_FILE" 2>/dev/null; return 0 ;;
        *) echo "tg_send_direct failed: $resp" >> "$LOG_FILE" 2>/dev/null; return 1 ;;
    esac
}

# ----------------------------------------------------------
# Install/update progress notification — OPERATOR-ROUTED, NEVER the client chat.
# ----------------------------------------------------------
# WE MOVE IN SILENCE (chore/silent-updater). Install / update / maintenance
# progress is INTERNAL traffic. It must NEVER reach the owner's / client's chat
# — no "Downloaded onboarding package", no "Extracted … N skills detected …
# Installing them now", no skill counts, no version announcements, no
# "install complete" brag. The agent surfaces its own owner-facing summary on
# its OWN terms (the AGENTS.md UPDATE-PENDING / kickoff flag); the Terminal
# backup block printed at install end covers the human running this by hand.
#
# RECURRENCE NOTE — why the client-chat leak came back after the prior fix:
# the v12.4.0 fix routed ONLY update-skills.sh's send_telegram_progress to the
# operator. THIS function — in install.sh, the canonical installer the fleet
# roll actually re-runs on a client box to push a new version — kept resolving
# the CLIENT chat (resolve_telegram_target_universal → allowFrom) and falling
# back to tg_send_direct (a direct api.telegram.org Bot-API call that also
# bypasses the gateway). So every progress line auto-DM'd the client. It is now
# operator-routed / log-only, identical to update-skills.sh, and the
# client-target + direct-Bot-API paths are removed from this function entirely.
#
# Resolution: env.vars.OPERATOR_ESCALATION_CHAT_ID / OPERATOR_HELP_CHAT_ID →
# operator account/session. If unset → LOG-ONLY (no send). We deliberately do
# NOT resolve the client target here and do NOT fall back to the client chat.
send_telegram_progress() {
    local message="$1"
    TELEGRAM_LAST_RESULT="skipped"

    local OCJSON="$HOME/.openclaw/openclaw.json"
    [ -d "/data/.openclaw" ] && OCJSON="/data/.openclaw/openclaw.json"

    # Resolve the OPERATOR escalation chat ONLY — never the client default chat.
    local OPERATOR_CHAT=""
    if [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
        OPERATOR_CHAT=$(OC_JSON="$OCJSON" python3 - <<'PYEOF' 2>/dev/null
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
except Exception:
    cfg = {}
env = (cfg.get("env", {}) or {}).get("vars", {}) or {}
for k in ("OPERATOR_ESCALATION_CHAT_ID", "OPERATOR_HELP_CHAT_ID"):
    v = str(env.get(k, "") or "").strip()
    if v:
        print(v); raise SystemExit(0)
print("")
PYEOF
)
    fi

    # No operator escalation chat configured, or no openclaw CLI → LOG-ONLY.
    # We deliberately do NOT fall back to the client default / allowFrom[0] and
    # do NOT use the direct Bot-API path.
    if [ -z "$OPERATOR_CHAT" ] || ! command -v openclaw >/dev/null 2>&1; then
        {
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] install progress (operator escalation chat not configured / no CLI — LOG-ONLY, NOT sent to any client chat):"
            printf '%s\n' "$message"
        } >> "$LOG_FILE" 2>&1
        TELEGRAM_LAST_RESULT="logged-no-operator-chat"
        return 0
    fi

    # Send on the OPERATOR session key, reply out the operator account — mirrors
    # update-skills.sh / the OPERATOR-MAINTENANCE operator-drive contract.
    if openclaw message send \
        --channel telegram \
        --account operator \
        --session-key agent:main:operator \
        --target "$OPERATOR_CHAT" \
        --message "$message" >> "$LOG_FILE" 2>&1; then
        TELEGRAM_LAST_RESULT="sent-operator:$OPERATOR_CHAT"
    else
        # Operator send failed → LOG-ONLY. Never fall back to the client chat.
        {
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] install progress operator send FAILED — LOG-ONLY, NOT routed to any client chat:"
            printf '%s\n' "$message"
        } >> "$LOG_FILE" 2>&1
        TELEGRAM_LAST_RESULT="failed-operator:see-$LOG_FILE"
    fi
    return 0   # NEVER kill the install — Telegram is optional
}

# ----------------------------------------------------------
# v10.13.10: Shared Operator Secrets Injector
# ----------------------------------------------------------
# Some credentials (Podbean OAuth app, future Google service account, etc.)
# are SHARED across every client — they belong to Trevor's master account, not
# to each individual client. Public GitHub repo can't hold them. Solution:
# operator exports them as env vars in ~/.zshrc before running curl|bash.
# install.sh reads them HERE and writes to the client's local secrets file
# (chmod 600) + openclaw.json env.vars block.
#
# Operator setup (one-time, in ~/.zshrc on operator's Mac):
#   # PREFERRED for client boxes — the n8n Podbean broker (no app secret on the box):
#   export OPENCLAW_PODBEAN_BROKER_URL="https://main.blackceoautomations.com/webhook/podbean-broker"
#   export OPENCLAW_PODBEAN_BROKER_TOKEN="..."   # the PODBEAN_BROKER_TOKEN set inside n8n
#   # Operator OWN box / legacy fallback ONLY (BlackCEO's single shared Podbean app):
#   export OPENCLAW_PODBEAN_CLIENT_ID="..."
#   export OPENCLAW_PODBEAN_CLIENT_SECRET="..."
#   # (future: OPENCLAW_GOOGLE_SERVICE_ACCOUNT_JSON, etc.)
#
# Per-client install:
#   OPENCLAW_OWNER_NAME="Sample Client" curl ...install.sh | bash
#   (vars from operator's ~/.zshrc inherited automatically)
inject_shared_operator_secrets() {
    local injected_count=0
    local mode_oc_json_ready="no"
    [ -f "$OC_JSON" ] && mode_oc_json_ready="yes"

    # Ensure secrets/.env exists with safe perms BEFORE we write to it
    mkdir -p "$(dirname "$OC_SECRETS_ENV")" 2>/dev/null || true
    if [ ! -f "$OC_SECRETS_ENV" ]; then
        touch "$OC_SECRETS_ENV"
        chmod 600 "$OC_SECRETS_ENV" 2>/dev/null || true
    fi

    # Helper: append VAR=value to secrets/.env (replacing any existing line for VAR)
    _shared_write_env() {
        local var="$1"; local val="$2"
        # Remove any existing line for this var
        grep -v "^${var}=" "$OC_SECRETS_ENV" > "$OC_SECRETS_ENV.tmp" 2>/dev/null || true
        mv "$OC_SECRETS_ENV.tmp" "$OC_SECRETS_ENV" 2>/dev/null || true
        # Append new line
        printf '%s=%s\n' "$var" "$val" >> "$OC_SECRETS_ENV"
        chmod 600 "$OC_SECRETS_ENV" 2>/dev/null || true
    }

    # Helper: write to openclaw.json env.vars block (if openclaw.json exists)
    _shared_write_ocjson() {
        local var="$1"; local val="$2"
        [ "$mode_oc_json_ready" != "yes" ] && return 0
        # Use python to safely merge into env.vars (preserves other keys)
        VAR="$var" VAL="$val" OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
p = os.environ['OC_JSON']
v = os.environ['VAR']
val = os.environ['VAL']
try:
    d = json.load(open(p))
except Exception:
    d = {}
d.setdefault('env', {}).setdefault('vars', {})[v] = val
json.dump(d, open(p, 'w'), indent=2)
PYEOF
    }

    # Podbean credential BROKER pair (PREFERRED for client boxes): inject only the
    # broker webhook URL + a low-privilege shared token. BlackCEO's Podbean app
    # client_id/client_secret then stay INSIDE n8n and never land on a client box.
    # The engine (58-podcast-production-engine/scripts/podbean_publish.sh) runs in
    # broker mode whenever both of these resolve. The client still supplies only
    # their Podbean Channel ID. See 58-podcast-production-engine/config/n8n/README.md.
    if [ -n "${OPENCLAW_PODBEAN_BROKER_URL:-}" ] && [ -n "${OPENCLAW_PODBEAN_BROKER_TOKEN:-}" ]; then
        _shared_write_env "PODBEAN_BROKER_WEBHOOK_URL" "$OPENCLAW_PODBEAN_BROKER_URL"
        _shared_write_env "PODBEAN_BROKER_TOKEN" "$OPENCLAW_PODBEAN_BROKER_TOKEN"
        _shared_write_ocjson "PODBEAN_BROKER_WEBHOOK_URL" "$OPENCLAW_PODBEAN_BROKER_URL"
        _shared_write_ocjson "PODBEAN_BROKER_TOKEN" "$OPENCLAW_PODBEAN_BROKER_TOKEN"
        success "Podbean broker pair injected from operator env (no Podbean app secret on this box; chmod 600)"
        injected_count=$((injected_count + 2))
    elif [ -n "${OPENCLAW_PODBEAN_BROKER_URL:-}" ] || [ -n "${OPENCLAW_PODBEAN_BROKER_TOKEN:-}" ]; then
        warn "Only one of OPENCLAW_PODBEAN_BROKER_URL / OPENCLAW_PODBEAN_BROKER_TOKEN set — both required. Skipping Podbean broker injection."
    fi

    # Podbean shared OAuth app credentials — operator OWN box / legacy fallback ONLY.
    # For client boxes prefer the broker pair above so BlackCEO's app secret never
    # lands on a client box. These are BlackCEO's single shared app (one Podbean
    # account hosts every client show), never the client's, and never asked from the client.
    if [ -n "${OPENCLAW_PODBEAN_CLIENT_ID:-}" ] && [ -n "${OPENCLAW_PODBEAN_CLIENT_SECRET:-}" ]; then
        _shared_write_env "PODBEAN_CLIENT_ID" "$OPENCLAW_PODBEAN_CLIENT_ID"
        _shared_write_env "PODBEAN_CLIENT_SECRET" "$OPENCLAW_PODBEAN_CLIENT_SECRET"
        _shared_write_ocjson "PODBEAN_CLIENT_ID" "$OPENCLAW_PODBEAN_CLIENT_ID"
        _shared_write_ocjson "PODBEAN_CLIENT_SECRET" "$OPENCLAW_PODBEAN_CLIENT_SECRET"
        success "Podbean shared OAuth app credentials injected from operator env (operator/legacy fallback; chmod 600)"
        injected_count=$((injected_count + 2))
    elif [ -n "${OPENCLAW_PODBEAN_CLIENT_ID:-}" ] || [ -n "${OPENCLAW_PODBEAN_CLIENT_SECRET:-}" ]; then
        warn "Only one of OPENCLAW_PODBEAN_CLIENT_ID / OPENCLAW_PODBEAN_CLIENT_SECRET set — both required. Skipping Podbean injection."
    fi

    # Rescue Rangers escalation webhook (n8n). Client agents escalate unsolvable
    # problems by POSTing to this URL (see AGENTS.md "Rescue Rangers"). It is NOT a
    # secret — it is a public, outbound-reachable webhook — but it IS seeded into
    # the agent's env so the escalation command can reference $RESCUE_RANGERS_WEBHOOK_URL
    # rather than a hardcoded URL. Overridable via the operator env var of the same name.
    local RR_WEBHOOK_DEFAULT="https://main.blackceoautomations.com/webhook/rescue-rangers"
    local RR_WEBHOOK="${RESCUE_RANGERS_WEBHOOK_URL:-$RR_WEBHOOK_DEFAULT}"
    _shared_write_env "RESCUE_RANGERS_WEBHOOK_URL" "$RR_WEBHOOK"
    _shared_write_ocjson "RESCUE_RANGERS_WEBHOOK_URL" "$RR_WEBHOOK"
    success "Rescue Rangers escalation webhook seeded (RESCUE_RANGERS_WEBHOOK_URL=$RR_WEBHOOK)"
    injected_count=$((injected_count + 1))

    # Rescue Rangers webhook SHARED SECRET (n8n entry-webhook authentication).
    # The n8n relay can require an `X-Rescue-Secret` header on the escalation
    # webhook so a stranger who learns the public URL cannot inject tickets. Every
    # escalation SENDER on this box (the AGENTS.md curl + the Skill-6 safety alarms
    # + the resume/closeout watchdogs) includes that header ONLY WHEN this var is
    # set — so seeding it here makes the box's escalations survive the webhook's
    # auth enforcement, and leaving it unset stays fully backward-compatible (no
    # header; the relay accepts it during the soft phase). UNLIKE the webhook URL
    # above, the secret is NEVER a committed default — it flows ONLY from the
    # operator's OWN env var of the same name at install time, gateway-inherited
    # via openclaw.json env.vars (the SAME mechanism that delivers
    # RESCUE_RANGERS_WEBHOOK_URL / RESCUE_RANGERS_HELP_CHAT_ID / PODBEAN_*).
    # Empty => escalations post unauthenticated; the box picks the secret up on
    # its next install/update once the operator's env carries it.
    if [ -n "${RESCUE_RANGERS_WEBHOOK_SECRET:-}" ]; then
        _shared_write_env    "RESCUE_RANGERS_WEBHOOK_SECRET" "$RESCUE_RANGERS_WEBHOOK_SECRET"
        _shared_write_ocjson "RESCUE_RANGERS_WEBHOOK_SECRET" "$RESCUE_RANGERS_WEBHOOK_SECRET"
        success "Rescue Rangers webhook secret seeded (RESCUE_RANGERS_WEBHOOK_SECRET, length=${#RESCUE_RANGERS_WEBHOOK_SECRET})"
        injected_count=$((injected_count + 1))
    else
        warn "RESCUE_RANGERS_WEBHOOK_SECRET not in operator env — client agents on this box will POST without the auth header (backward-compatible until relay enforces auth). Backfill with ~/clawd/fleet-heartbeat/scripts/propagate-rescue-webhook.sh."
    fi

    # Rescue Rangers escalation CHAT ID (operator Telegram GROUP). The Skill-6
    # safety alarms (browser_manager.sh circuit-breaker trip + agent-browser-reaper.sh
    # leak tripwire) read $RESCUE_RANGERS_HELP_CHAT_ID and otherwise no-op SILENTLY,
    # so without this seed both alarms are dead. UNLIKE the webhook URL above, a chat
    # id is NEVER hardcoded as a committed default — it flows ONLY from the operator's
    # own env var of the same name at install time, gateway-inherited via openclaw.json
    # env.vars (the SAME mechanism that delivers RESCUE_RANGERS_WEBHOOK_URL / PODBEAN_*
    # to every gateway child on Mac AND VPS). It MUST be the operator GROUP id (a
    # Telegram supergroup, ^-100…) — NEVER a client and NEVER an individual DM. There
    # is no fallback: empty => the alarms stay silent (never a wrong target).
    if [ -n "${RESCUE_RANGERS_HELP_CHAT_ID:-}" ]; then
        if printf '%s' "$RESCUE_RANGERS_HELP_CHAT_ID" | grep -Eq '^-100[0-9]+$'; then
            _shared_write_env   "RESCUE_RANGERS_HELP_CHAT_ID" "$RESCUE_RANGERS_HELP_CHAT_ID"
            _shared_write_ocjson "RESCUE_RANGERS_HELP_CHAT_ID" "$RESCUE_RANGERS_HELP_CHAT_ID"
            success "Rescue Rangers help chat id seeded (operator group, gateway-inherited)"
            injected_count=$((injected_count + 1))
        else
            warn "RESCUE_RANGERS_HELP_CHAT_ID is set but is NOT an operator group id (^-100…) — refusing to seed it (the safety alarm must never DM a client or individual). Skill-6 alarms will stay silent on this box."
        fi
    else
        warn "RESCUE_RANGERS_HELP_CHAT_ID not in operator env — Skill-6 safety alarms (breaker trip + reaper leak tripwire) will stay SILENT on this box (no client fallback). Backfill with ~/clawd/fleet-heartbeat/scripts/propagate-rescue-chat-id.sh."
    fi

    # ── BOX-LEVEL HEADLESS PIN (v14.1.4) ─────────────────────────────────────
    # THE CORE LOCK. agent-browser is headless by DEFAULT, but a single inherited
    # AGENT_BROWSER_HEADED env var OR a {"headed":true} config can silently open a
    # VISIBLE Chromium window on a client screen. Skill 06 forced headless only
    # INSIDE its own wrappers (browser_manager.sh `--headed false`), so three paths
    # bypassed it: (1) a raw agent-typed `agent-browser open`; (2) the Skill-03
    # install smoke test; (3) an inherited/leftover {"headed":true}. We close that
    # at the BOX level by pinning AGENT_BROWSER_HEADED=false in the GATEWAY-INHERITED
    # env (openclaw.json env.vars — the SAME mechanism that delivers PODBEAN_* /
    # RESCUE_RANGERS_* / Skill-44 GHL creds to every gateway child, confirmed
    # gateway-inherited on BOTH Mac and VPS) PLUS secrets/.env as a belt. EVERY
    # browser the gateway spawns — including a raw `agent-browser open` and an
    # OLD-guard Skill-6 call — now defaults to headless. There is NO legitimate
    # headed use on any client box: the GHL headless-canvas wall was cracked, so
    # everything runs headless. Schema-safe: env.vars is an established key (unlike
    # the removed browser.agentBrowser, which crashed 2026.6.8's strict schema).
    # OS-portable: python3 + a plain VAR=value line, identical Mac + Linux.
    _shared_write_env "AGENT_BROWSER_HEADED" "false"
    _shared_write_ocjson "AGENT_BROWSER_HEADED" "false"
    success "Box-level headless pin set (AGENT_BROWSER_HEADED=false in gateway-inherited env + secrets/.env — no visible browser window can open on this box)"
    injected_count=$((injected_count + 1))

    # (future shared secrets get added here — same pattern)

    if [ "$injected_count" -gt 0 ]; then
        note "Shared operator secrets: $injected_count value(s) written to $OC_SECRETS_ENV"
    else
        note "Shared operator secrets: none in env. For client boxes set OPENCLAW_PODBEAN_BROKER_URL + OPENCLAW_PODBEAN_BROKER_TOKEN in ~/.zshrc (preferred; keeps the Podbean app secret in n8n). OPENCLAW_PODBEAN_CLIENT_ID + _CLIENT_SECRET are the operator/legacy fallback only."
    fi
}

# ----------------------------------------------------------
# Config Backup Protocol
# ----------------------------------------------------------
backup_config_file() {
    local file="$1"
    if [ -f "$file" ]; then
        mkdir -p "$OC_BACKUPS"
        local ts filename backup
        ts=$(date +%Y-%m-%d-%H%M%S)
        filename=$(basename "$file")
        backup="$OC_BACKUPS/${filename}-backup-${ts}.txt"
        cp "$file" "$backup"
        note "Backed up: $backup"
    fi
}

# ----------------------------------------------------------
# Bulletproof Mac Credential Discovery (v10.0.0)
# ----------------------------------------------------------
# Sources searched (in order, first hit wins per credential):
#   1. Shell env vars (printenv)             — operator exports in shell rc files
#   2. ~/.openclaw/secrets/.env              — canonical Mac secrets file
#   3. ~/.openclaw/.env                      — alternate (often symlink)
#   4. ~/clawd/secrets/.env                  — legacy location, still seen on some clients
#   5. env.vars block in ~/.openclaw/openclaw.json  — inline pattern (your Mac uses this)
#   6. models.providers.<name>.apiKey        — LLM keys baked into config
#   7. plugins.entries.<plugin>.config.*     — plugin-level secrets
#   8. auth-profiles.json profiles.*.key     — per-agent api_key entries
#   9. ~/.openclaw/secrets.json              — official OpenClaw secrets file (per docs)
#  10. Recursive scan of openclaw.json for any field named apiKey|token|secret
#
# Alias map handles naming variants per credential.

CREDS_FOUND_LIST=""

get_alias_list() {
    case "$1" in
        GOHIGHLEVEL_API_KEY)
            echo "GOHIGHLEVEL_API_KEY GHL_PRIVATE_INTEGRATION_TOKEN GHL_API_KEY GHL_PIT HIGHLEVEL_API_KEY HIGHLEVEL_TOKEN GHL_PRIVATE_TOKEN" ;;
        GOHIGHLEVEL_LOCATION_ID)
            echo "GOHIGHLEVEL_LOCATION_ID GHL_LOCATION_ID HIGHLEVEL_LOCATION_ID LOCATION_ID" ;;
        TELEGRAM_BOT_TOKEN)
            echo "TELEGRAM_BOT_TOKEN TG_BOT_TOKEN BOT_TOKEN" ;;
        GEMINI_API_KEY)
            # Google's Gemini API key is the SAME credential as GOOGLE_API_KEY — a client
            # had GOOGLE_API_KEY set and Gemini was reported "Not configured" (10.13.1 bug).
            echo "GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_GEMINI_API_KEY GOOGLE_AI_STUDIO_API_KEY GOOGLE_GENERATIVE_AI_API_KEY GOOGLE_AI_API_KEY GEMINI_KEY" ;;
        GOOGLE_API_KEY)
            echo "GOOGLE_API_KEY GEMINI_API_KEY GOOGLE_GEMINI_API_KEY GOOGLE_AI_STUDIO_API_KEY GOOGLE_GENERATIVE_AI_API_KEY GOOGLE_AI_API_KEY GOOGLE_CLOUD_API_KEY" ;;
        OPENAI_API_KEY)
            echo "OPENAI_API_KEY OPENAI_TOKEN" ;;
        OPENROUTER_API_KEY)
            echo "OPENROUTER_API_KEY OR_API_KEY" ;;
        FISH_AUDIO_API_KEY)
            echo "FISH_AUDIO_API_KEY FISHAUDIO_API_KEY FISH_API_KEY" ;;
        FISH_AUDIO_VOICE_ID)
            echo "FISH_AUDIO_VOICE_ID FISHAUDIO_VOICE_ID" ;;
        PODBEAN_API_KEY|PODBEAN_CLIENT_ID)
            echo "PODBEAN_CLIENT_ID PODBEAN_API_KEY" ;;
        PODBEAN_API_SECRET|PODBEAN_CLIENT_SECRET)
            echo "PODBEAN_CLIENT_SECRET PODBEAN_API_SECRET" ;;
        PODBEAN_PODCAST_ID)
            echo "PODBEAN_PODCAST_ID PODBEAN_CHANNEL_ID PODCAST_ID" ;;
        TAVILY_API_KEY)
            echo "TAVILY_API_KEY TAVILY_KEY" ;;
        KIE_API_KEY)
            echo "KIE_API_KEY KIE_AI_API_KEY" ;;
        OLLAMA_API_KEY)
            echo "OLLAMA_API_KEY OLLAMA_CLOUD_API_KEY OLLAMA_KEY OLLAMA_TOKEN" ;;
        SUPABASE_SERVICE_ROLE_KEY)
            echo "SUPABASE_SERVICE_ROLE_KEY SUPABASE_SERVICE_KEY" ;;
        VERCEL_TOKEN)
            echo "VERCEL_TOKEN VERCEL_API_TOKEN" ;;
        GITHUB_TOKEN)
            echo "GITHUB_TOKEN GH_TOKEN" ;;
        ANTHROPIC_API_KEY)
            echo "ANTHROPIC_API_KEY CLAUDE_API_KEY" ;;
        CONTEXT7_API_KEY)
            echo "CONTEXT7_API_KEY CTX7_API_KEY" ;;
        AIRTABLE_TOKEN)
            echo "AIRTABLE_TOKEN AIRTABLE_API_KEY AIRTABLE_PAT" ;;
        DEEPSEEK_API_KEY)
            echo "DEEPSEEK_API_KEY DEEPSEEK_KEY DEEP_SEEK_API_KEY" ;;
        ELEVENLABS_API_KEY)
            echo "ELEVENLABS_API_KEY ELEVEN_API_KEY" ;;
        BRAVE_API_KEY)
            echo "BRAVE_API_KEY BRAVE_SEARCH_API_KEY" ;;
        FAL_API_KEY)
            echo "FAL_API_KEY FAL_KEY" ;;
        *)
            echo "$1" ;;
    esac
}

# v10.13.7: looks_like_real_key — REAL validator based on gitleaks methodology
# (regex + Shannon entropy), not just a guessed substring blocklist.
#
# Three-stage check, value passes if ALL stages pass:
#   1. Provider-specific regex — if VAR_NAME corresponds to a known provider
#      AND the value matches that provider's documented key shape, accept it.
#      (e.g. OPENAI_API_KEY must start with sk-, GOOGLE_API_KEY with AIza,
#      ANTHROPIC_API_KEY with sk-ant-api03-, SUPABASE_SERVICE_ROLE_KEY with
#      eyJ or sb_secret_, etc.) Failing the regex = NOT this provider's key.
#   2. Shannon entropy — real API keys are high-entropy random strings.
#      Placeholders like "your_key_here" or "AKIAIOSFODNN7EXAMPLE" have low
#      entropy. Threshold: 3.5 bits/char minimum.
#   3. Length + obvious-placeholder substring check — belt-and-suspenders
#      for anything regex+entropy might miss.
#
# Provider regex sources: gitleaks default ruleset
# (https://github.com/gitleaks/gitleaks/blob/master/config/gitleaks.toml),
# GitGuardian docs (docs.gitguardian.com/secrets-detection/...), and each
# provider's own API documentation (verified May 2026).
#
# Called from: Source 1 (printenv), Source 1b (env-file walker), Source 1c
# (sourced rc files), and bash-side belt-and-suspenders after Python returns.
# Python's PYEOF block has a parallel implementation.
#
# Usage: looks_like_real_key <value> [canonical_var_name]
#   - $1 = value to validate (required)
#   - $2 = canonical variable name for provider-regex lookup (optional but
#     strongly recommended — without it, we skip stage 1 and rely only on
#     entropy + substring checks)
looks_like_real_key() {
    local val="$1"
    local canonical="${2:-}"

    # ── Stage 0: empty / trivial rejects ────────────────────────────
    [ -z "$val" ] && return 1
    [ ${#val} -lt 10 ] && return 1
    local lo
    lo=$(printf '%s' "$val" | tr '[:upper:]' '[:lower:]')
    case "$lo" in
        true|false|yes|no|null|none|undefined|n/a|na|"-"|"—") return 1 ;;
    esac

    # ── Stage 1: provider-specific regex match (when canonical is known) ──
    # If the canonical var maps to a known provider, the value MUST match
    # that provider's documented key shape. This is the strongest check.
    if [ -n "$canonical" ]; then
        local regex_matched="unknown"  # unknown = no provider mapping
        case "$canonical" in
            OPENAI_API_KEY)
                # sk-, sk-proj-, sk-svcacct-, sk-admin-; 40+ chars total
                if printf '%s' "$val" | grep -qE '^sk-(proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            ANTHROPIC_API_KEY)
                # sk-ant-api03-..., 100+ chars
                if printf '%s' "$val" | grep -qE '^sk-ant-(api03-)?[A-Za-z0-9_-]{80,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            GEMINI_API_KEY|GOOGLE_API_KEY)
                # AIza followed by 35 chars
                if printf '%s' "$val" | grep -qE '^AIza[A-Za-z0-9_-]{35}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            OPENROUTER_API_KEY)
                # sk-or-v1-...
                if printf '%s' "$val" | grep -qE '^sk-or-(v1-)?[A-Za-z0-9_-]{32,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            GITHUB_TOKEN)
                # ghp_/gho_/ghu_/ghs_/ghr_ + 36 chars, OR 40-char hex (legacy)
                if printf '%s' "$val" | grep -qE '^(gh[poursr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|[a-f0-9]{40})$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            BRAVE_API_KEY)
                # BSA + 20+ chars
                if printf '%s' "$val" | grep -qE '^BSA[A-Za-z][A-Za-z0-9_-]{20,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            TAVILY_API_KEY)
                # tvly-...
                if printf '%s' "$val" | grep -qE '^tvly-[A-Za-z0-9_-]{20,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            AIRTABLE_TOKEN)
                # pat<14>.<64+> for PAT, OR key<14> for legacy (deprecated 2024-02 but some still have them)
                if printf '%s' "$val" | grep -qE '^(pat[A-Za-z0-9]{14}\.[A-Za-z0-9]{60,}|key[A-Za-z0-9]{14})$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            SUPABASE_SERVICE_ROLE_KEY)
                # JWT (eyJ...) or new sb_secret_...
                if printf '%s' "$val" | grep -qE '^(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sb_secret_[A-Za-z0-9_-]{20,})$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            TELEGRAM_BOT_TOKEN)
                # <bot_id>:<token>  e.g. 123456789:AAFake-Example-Token-Not-A-Real-Secret00
                if printf '%s' "$val" | grep -qE '^[0-9]{8,12}:[A-Za-z0-9_-]{30,40}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            VERCEL_TOKEN)
                # vcp_<24> or 24-char alphanumeric
                if printf '%s' "$val" | grep -qE '^(vcp_)?[A-Za-z0-9]{24,40}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            NOTION_API_TOKEN|NOTION_API_KEY)
                # ntn_<11 digits><32 alphanum><3 alphanum> = 50 total after prefix
                if printf '%s' "$val" | grep -qE '^ntn_[A-Za-z0-9]{40,50}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            CONTEXT7_API_KEY)
                # ctx7sk-<UUID>  (verified May 2026)
                if printf '%s' "$val" | grep -qE '^ctx7sk-[A-Za-z0-9_-]{20,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            FAL_API_KEY)
                # key_id:sk_live_secret  (format with colon)
                if printf '%s' "$val" | grep -qE '^[A-Za-z0-9_-]{8,}:[A-Za-z0-9_-]{20,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            ELEVENLABS_API_KEY)
                # 32-char hex (no fixed prefix)
                if printf '%s' "$val" | grep -qE '^[a-f0-9]{32}$|^sk_[A-Za-z0-9_-]{32,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            DEEPSEEK_API_KEY)
                # sk-<hex32> (DeepSeek mirrors OpenAI's older format)
                if printf '%s' "$val" | grep -qE '^sk-[a-f0-9]{32,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            OLLAMA_API_KEY)
                # Ollama Cloud tokens are typically long alphanumeric, no fixed prefix
                if printf '%s' "$val" | grep -qE '^[A-Za-z0-9]{32,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            KIE_API_KEY)
                # KIE.ai tokens — verify shape varies; accept 24+ alphanumeric
                if printf '%s' "$val" | grep -qE '^[A-Za-z0-9_-]{24,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            FISH_AUDIO_API_KEY)
                # Fish Audio uses UUID-like hex tokens, 32+ chars
                if printf '%s' "$val" | grep -qE '^[a-f0-9]{32,}$|^[A-Za-z0-9_-]{32,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            FISH_AUDIO_VOICE_ID)
                # Voice IDs are typically short identifiers
                if printf '%s' "$val" | grep -qE '^[a-z0-9_-]{8,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            PODBEAN_CLIENT_ID|PODBEAN_API_KEY|PODBEAN_CLIENT_SECRET|PODBEAN_API_SECRET)
                # Real Podbean OAuth app credentials are 20-21 char hex strings
                # (verified May 2026 — previous v10.13.7 spec of {32,} was wrong
                # and rejected real keys). Accept lower-case hex with hyphens
                # too (Podbean has been known to use both).
                if printf '%s' "$val" | grep -qiE '^[a-f0-9]{16,40}$|^[A-Za-z0-9_-]{16,40}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            PODBEAN_PODCAST_ID)
                # Podcast IDs are alphanumeric strings (varies by Podbean URL slug)
                if printf '%s' "$val" | grep -qE '^[A-Za-z0-9_-]{6,}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            GOHIGHLEVEL_API_KEY)
                # GHL PIT tokens are JWT-style or pit-prefixed; varies
                if printf '%s' "$val" | grep -qE '^(eyJ[A-Za-z0-9_.-]{30,}|pit-[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{40,})$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
            GOHIGHLEVEL_LOCATION_ID)
                # GHL location IDs are 24-char alphanumeric (MongoDB ObjectId-style)
                if printf '%s' "$val" | grep -qE '^[A-Za-z0-9]{20,28}$'; then
                    regex_matched="yes"; else regex_matched="no"; fi ;;
        esac
        # If we have a provider mapping AND it didn't match, REJECT.
        # If we have no mapping (regex_matched=unknown), fall through to entropy.
        if [ "$regex_matched" = "no" ]; then
            return 1
        fi
        # If matched a known pattern, still run entropy/placeholder checks as
        # belt-and-suspenders (defends against e.g. a real-shaped value that's
        # actually a deliberate test string from a tutorial).
    fi

    # ── Stage 2: obvious-placeholder substring rejection ────────────
    case "$lo" in
        *xxxxx*|*your_key*|*your-key*|*your_api*|*your-api*|*yourkey*|*your_token*) return 1 ;;
        *replace_me*|*replace-me*|*replaceme*|*changeme*|*change_me*|*change-me*) return 1 ;;
        *_here*|*-here*|*placeholder*|*example*|*sample*|*dummy*|*demo*) return 1 ;;
        *test_key*|*fake_key*|*sk-test*|*sk-xxx*|*sk-example*|*sk-replace*) return 1 ;;
        *todo*|*tbd*|*fill_in*|*fillin*|*paste-your*|*paste_your*) return 1 ;;
        *insert_your*|*enter_your*|*set_your*|*no_key*|*none_yet*) return 1 ;;
        # The exact "EXAMPLE" suffix gitleaks documentation uses (AKIAIOSFODNN7EXAMPLE)
        *EXAMPLE|*example) return 1 ;;
    esac
    case "$val" in
        \<*\>|\[*\]|\{\{*\}\}) return 1 ;;
    esac

    # ── Stage 3: Shannon entropy check ──────────────────────────────
    # Real API keys are high-entropy. Placeholders like "abcdef1234567890"
    # or "the-quick-brown-fox" have low entropy. Threshold: 3.0 bits/char
    # (gitleaks uses 3-4 for most patterns). Computed in Python because
    # bash can't do log2 without invoking bc/python anyway.
    local entropy
    entropy=$(printf '%s' "$val" | python3 -c "
import sys, math
s = sys.stdin.read()
if len(s) == 0: print(0); sys.exit()
freq = {c: s.count(c) for c in set(s)}
ent = -sum((f/len(s)) * math.log2(f/len(s)) for f in freq.values())
print(f'{ent:.2f}')
" 2>/dev/null || echo "0")
    # Use awk for float comparison (bash can't)
    if awk -v e="$entropy" 'BEGIN { exit !(e < 3.0) }'; then
        return 1
    fi

    return 0
}

# search_env_var_mac <CANONICAL_VAR> — bulletproof Mac-only lookup across 10
# sources. Prints stderr line showing which source/alias matched.
search_env_var_mac() {
    local CANONICAL="$1"
    local aliases
    aliases=$(get_alias_list "$CANONICAL")

    # Source 1: shell env vars (printenv — only sees what's been exported into this process)
    for VAR_NAME in $aliases; do
        local env_val
        env_val=$(printenv "$VAR_NAME" 2>/dev/null || true)
        if [ -n "$env_val" ] && looks_like_real_key "$env_val" "$CANONICAL"; then
            [ "$VAR_NAME" != "$CANONICAL" ] && echo "    [src: env.$VAR_NAME → $CANONICAL]" >&2
            echo "$env_val"
            return
        elif [ -n "$env_val" ]; then
            echo "    [skip: env.$VAR_NAME=<rejected as placeholder or wrong shape for $CANONICAL>]" >&2
        fi
    done

    # Source 1b (v10.13.3): bulletproof env-file discovery — replaces the v10.13.2
    # hardcoded-path approach. Operators store API keys in arbitrary `.env`-style
    # files (~/.env, ~/sequence/.env, ~/codex/.env, ~/clawd/.env, ~/Documents/.env,
    # ~/projects/<thing>/.env, etc.). Instead of guessing, we:
    #   1) build an ENV_FILES list of every plausible env-style file under $HOME
    #      (depth-limited to keep it fast), with the canonical OpenClaw paths
    #      first so they still take priority,
    #   2) for each file, grep for the alias VAR=... line and return on first hit,
    #   3) plus shell-source common rc files in a subshell so values that arrive
    #      via `source ~/some-other-file` also get caught.
    #
    # This is the cache-bust answer to a client bug: keys lived in a file the
    # v10.13.2 scanner did not enumerate. v10.13.3 enumerates ALL of them.
    local HOME_DIR="${HOME}"

    # Build the candidate-file list once per process and cache it on the env.
    if [ -z "${MAC_ENV_FILE_LIST:-}" ]; then
        local CACHE=""
        # Tier 1: canonical OpenClaw / Clawd locations (still highest priority)
        for f in \
            "$HOME_DIR/.openclaw/secrets/.env" \
            "$HOME_DIR/.openclaw/secrets/secrets.env" \
            "$HOME_DIR/.openclaw/.env" \
            "$HOME_DIR/.openclaw/env" \
            "$HOME_DIR/clawd/secrets/.env" \
            "$HOME_DIR/clawd/.env" \
            "$HOME_DIR/.config/openclaw/secrets.env" \
            "$HOME_DIR/.config/openclaw/.env" \
            "$HOME_DIR/.config/clawd/.env" \
            "$HOME_DIR/.env" \
            "$HOME_DIR/.env.local" \
            "$HOME_DIR/.env.openclaw" \
            "$HOME_DIR/sequence/.env" \
            "$HOME_DIR/sequence/secrets.env" \
            "$HOME_DIR/codex/.env" \
            "$HOME_DIR/.codex/.env" \
            "$HOME_DIR/.codex/secrets.env" \
            "$HOME_DIR/.zshrc" \
            "$HOME_DIR/.zshenv" \
            "$HOME_DIR/.zprofile" \
            "$HOME_DIR/.bash_profile" \
            "$HOME_DIR/.bashrc" \
            "$HOME_DIR/.profile"; do
            [ -f "$f" ] && CACHE="${CACHE}${f}"$'\n'
        done
        # Tier 2: find ANY *.env / *secrets*.env / *.envrc file under $HOME
        # up to depth 4. Excludes:
        #  - heavy dirs: node_modules, .git, Library, Downloads, .Trash,
        #    .npm-global, .cache, .venv, venv, __pycache__, .pyenv
        #  - template/example files: .env.example, .env.sample, .env.template,
        #    .env.dist, .env.test, .env.spec, .env.demo  — v10.13.4 fix for the
        #    false-positive bug where v10.13.3 scraped placeholder values like
        #    `OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxx` from `.env.example` files in
        #    npm packages / SDK example dirs.
        #  - common project dirs that ship example envs: examples/, samples/,
        #    fixtures/, test/, tests/, __tests__/, spec/
        local found_extra
        found_extra=$(find "$HOME_DIR" -maxdepth 4 \
            \( -path "*/node_modules" -o -path "*/.git" -o -path "*/Library" \
               -o -path "*/Downloads" -o -path "*/.Trash" -o -path "*/.npm-global" \
               -o -path "*/.cache" -o -path "*/.venv" -o -path "*/venv" \
               -o -path "*/__pycache__" -o -path "*/.pyenv" \
               -o -path "*/examples" -o -path "*/example" \
               -o -path "*/samples" -o -path "*/sample" \
               -o -path "*/fixtures" -o -path "*/fixture" \
               -o -path "*/test" -o -path "*/tests" -o -path "*/__tests__" \
               -o -path "*/spec" -o -path "*/specs" \
               -o -path "*/docs" -o -path "*/doc" \
            \) -prune -o \
            -type f \( -name "*.env" -o -name ".env" \
                       -o -name "secrets.env" -o -name "*.envrc" \) \
            ! -name "*.example" ! -name "*.sample" ! -name "*.template" \
            ! -name "*.dist" ! -name "*.test" ! -name "*.spec" \
            ! -name "*.demo" ! -name "*.tmpl" \
            ! -name "*.example.*" ! -name "*.sample.*" \
            -size -2048k -print 2>/dev/null | head -200)
        if [ -n "$found_extra" ]; then
            CACHE="${CACHE}${found_extra}"$'\n'
        fi
        export MAC_ENV_FILE_LIST="$CACHE"
    fi

    # Iterate alias × file; first match wins. v10.13.4: also validate the value
    # looks like a real API key, not a placeholder. If the file is a known
    # template (slipped past the find-exclusion), the value will fail the
    # looks_like_real_key check and we keep walking.
    local ENV_FILE
    while IFS= read -r ENV_FILE; do
        [ -z "$ENV_FILE" ] && continue
        [ ! -f "$ENV_FILE" ] && continue
        for VAR_NAME in $aliases; do
            local rc_val
            # Match `export VAR=val`, `VAR=val`, with optional quotes, strip inline comments
            rc_val=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${VAR_NAME}=" "$ENV_FILE" 2>/dev/null \
                | grep -vE "^[[:space:]]*#" \
                | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${VAR_NAME}=//" \
                | sed -E 's/[[:space:]]*#.*$//' \
                | head -1 || true)
            rc_val="${rc_val%\"}"; rc_val="${rc_val#\"}"
            rc_val="${rc_val%\'}"; rc_val="${rc_val#\'}"
            if [ -n "$rc_val" ] && looks_like_real_key "$rc_val" "$CANONICAL"; then
                local pretty="${ENV_FILE/#$HOME_DIR/~}"
                echo "    [src: $pretty:$VAR_NAME]" >&2
                echo "$rc_val"
                return
            elif [ -n "$rc_val" ]; then
                local pretty="${ENV_FILE/#$HOME_DIR/~}"
                echo "    [skip: $pretty:$VAR_NAME=<rejected as placeholder or wrong shape for $CANONICAL>]" >&2
            fi
        done
    done <<EOFLIST
$MAC_ENV_FILE_LIST
EOFLIST

    # Source 1c (v10.13.3): shell-source fallback. If keys reach the shell via
    # `source ~/some-other-file` inside .zshrc (and that file isn't itself an
    # env file we'd recognize), simulate it. Source rc files in a clean subshell
    # and capture exported vars.
    for rc_file in "$HOME_DIR/.zshenv" "$HOME_DIR/.zprofile" "$HOME_DIR/.zshrc" "$HOME_DIR/.bash_profile" "$HOME_DIR/.bashrc" "$HOME_DIR/.profile"; do
        [ ! -f "$rc_file" ] && continue
        for VAR_NAME in $aliases; do
            local sourced_val
            sourced_val=$(env -i HOME="$HOME_DIR" PATH="/usr/bin:/bin:/usr/local/bin" \
                bash -c "set +e; source '$rc_file' >/dev/null 2>&1; printf '%s' \"\${$VAR_NAME:-}\"" 2>/dev/null)
            if [ -n "$sourced_val" ] && looks_like_real_key "$sourced_val" "$CANONICAL"; then
                local pretty="${rc_file/#$HOME_DIR/~}"
                echo "    [src: sourced($pretty):$VAR_NAME]" >&2
                echo "$sourced_val"
                return
            fi
        done
    done

    [ ! -f "$OC_JSON" ] && { echo ""; return; }

    # Sources 5-10 — single python pass over openclaw.json + auth-profiles.json
    local result
    result=$(CANONICAL="$CANONICAL" ALIASES="$aliases" OC_JSON="$OC_JSON" OC_AUTH="$OC_AUTH_PROFILES" OC_CONFIG_DIR="$OC_CONFIG" python3 - <<'PYEOF' 2>/dev/null
import json, os, re, sys
CANONICAL = os.environ['CANONICAL']
ALIASES = os.environ['ALIASES'].split()
OC_JSON = os.environ['OC_JSON']
OC_AUTH = os.environ['OC_AUTH']
SECRETS_JSON = os.path.join(os.environ['OC_CONFIG_DIR'], 'secrets.json')

# v10.13.7: Python validator using gitleaks methodology (regex + entropy)
# rather than substring guessing. Stage 1: provider-specific regex match
# against CANONICAL var name (rejects shape mismatches immediately —
# Fish Audio / Podbean / Brave / Fal etc. all have documented key formats).
# Stage 2: obvious-placeholder substring rejection. Stage 3: Shannon entropy
# (placeholders like "AKIAIOSFODNN7EXAMPLE" have low entropy; real keys are
# high-entropy random strings). Threshold 3.0 bits/char per gitleaks defaults.

PROVIDER_REGEX = {
    "OPENAI_API_KEY":            r"^sk-(proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}$",
    "ANTHROPIC_API_KEY":         r"^sk-ant-(api03-)?[A-Za-z0-9_-]{80,}$",
    "GEMINI_API_KEY":            r"^AIza[A-Za-z0-9_-]{35}$",
    "GOOGLE_API_KEY":            r"^AIza[A-Za-z0-9_-]{35}$",
    "OPENROUTER_API_KEY":        r"^sk-or-(v1-)?[A-Za-z0-9_-]{32,}$",
    "GITHUB_TOKEN":              r"^(gh[poursr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}|[a-f0-9]{40})$",
    "BRAVE_API_KEY":             r"^BSA[A-Za-z][A-Za-z0-9_-]{20,}$",
    "TAVILY_API_KEY":            r"^tvly-[A-Za-z0-9_-]{20,}$",
    "AIRTABLE_TOKEN":            r"^(pat[A-Za-z0-9]{14}\.[A-Za-z0-9]{60,}|key[A-Za-z0-9]{14})$",
    "SUPABASE_SERVICE_ROLE_KEY": r"^(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|sb_secret_[A-Za-z0-9_-]{20,})$",
    "TELEGRAM_BOT_TOKEN":        r"^[0-9]{8,12}:[A-Za-z0-9_-]{30,40}$",
    "VERCEL_TOKEN":              r"^(vcp_)?[A-Za-z0-9]{24,40}$",
    "NOTION_API_TOKEN":          r"^ntn_[A-Za-z0-9]{40,50}$",
    "NOTION_API_KEY":            r"^ntn_[A-Za-z0-9]{40,50}$",
    "CONTEXT7_API_KEY":          r"^ctx7sk-[A-Za-z0-9_-]{20,}$",
    "FAL_API_KEY":               r"^[A-Za-z0-9_-]{8,}:[A-Za-z0-9_-]{20,}$",
    "ELEVENLABS_API_KEY":        r"^([a-f0-9]{32}|sk_[A-Za-z0-9_-]{32,})$",
    "DEEPSEEK_API_KEY":          r"^sk-[a-f0-9]{32,}$",
    "OLLAMA_API_KEY":            r"^[A-Za-z0-9]{32,}$",
    "KIE_API_KEY":               r"^[A-Za-z0-9_-]{24,}$",
    "FISH_AUDIO_API_KEY":        r"^[A-Za-z0-9_-]{32,}$",
    "FISH_AUDIO_VOICE_ID":       r"^[a-z0-9_-]{8,}$",
    "PODBEAN_CLIENT_ID":         r"^[A-Za-z0-9_-]{16,40}$",
    "PODBEAN_API_KEY":           r"^[A-Za-z0-9_-]{16,40}$",
    "PODBEAN_CLIENT_SECRET":     r"^[A-Za-z0-9_-]{16,40}$",
    "PODBEAN_API_SECRET":        r"^[A-Za-z0-9_-]{16,40}$",
    "PODBEAN_PODCAST_ID":        r"^[A-Za-z0-9_-]{6,}$",
    "GOHIGHLEVEL_API_KEY":       r"^(eyJ[A-Za-z0-9_.-]{30,}|pit-[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{40,})$",
    "GOHIGHLEVEL_LOCATION_ID":   r"^[A-Za-z0-9]{20,28}$",
}

PLACEHOLDER_SUBSTRINGS = (
    'xxxxx', 'your_key', 'your-key', 'your_api', 'your-api', 'yourkey',
    'your_token', 'replace_me', 'replace-me', 'replaceme', 'changeme',
    'change_me', 'change-me', '_here', '-here', 'placeholder',
    'sample', 'dummy', 'demo', 'test_key', 'fake_key', 'sk-test', 'sk-xxx',
    'sk-example', 'sk-replace', 'todo', 'tbd', 'fill_in', 'fillin',
    'paste-your', 'paste_your', 'insert_your', 'enter_your',
    'set_your', 'no_key', 'none_yet',
)

def shannon_entropy(s):
    if not s: return 0.0
    import math
    from collections import Counter
    counts = Counter(s)
    n = len(s)
    return -sum((c/n) * math.log2(c/n) for c in counts.values())

def looks_like_real_key(val, canonical=None):
    # Stage 0: trivial rejects
    if isinstance(val, bool): return False
    if not isinstance(val, str):
        val = str(val) if val else ""
    if not val or not val.strip(): return False
    if len(val) < 10: return False
    if val.strip().lower() in ('true','false','yes','no','null','none','undefined','n/a','na','-','—'):
        return False

    # Stage 1: provider-specific regex (when canonical is known)
    if canonical and canonical in PROVIDER_REGEX:
        if not re.match(PROVIDER_REGEX[canonical], val):
            return False  # wrong shape for this provider

    # Stage 2: placeholder substring rejection (case-insensitive)
    lo = val.lower()
    for sub in PLACEHOLDER_SUBSTRINGS:
        if sub in lo: return False
    if val.startswith('<') and val.endswith('>'): return False
    if val.startswith('[') and val.endswith(']'): return False
    if val.startswith('{{') and val.endswith('}}'): return False
    # The exact "EXAMPLE" suffix gitleaks uses for placeholder examples
    if val.endswith('EXAMPLE') or val.endswith('example'): return False
    # AWS-style EXAMPLE marker anywhere
    if 'EXAMPLE' in val and len(val) < 25: return False

    # Stage 3: Shannon entropy (threshold 3.0 bits/char per gitleaks)
    if shannon_entropy(val) < 3.0: return False

    return True

def emit(src_label, value):
    # Common emit gate so EVERY Python source goes through the validator.
    # CANONICAL is bound at the top of the PYEOF block so we pass it through.
    if looks_like_real_key(value, CANONICAL):
        print(f"src={src_label}"); print(value); raise SystemExit(0)
    print(f"    [skip: {src_label}=<rejected: wrong shape, low entropy, or placeholder for {CANONICAL}>]", file=sys.stderr)

cfg = {}
try: cfg = json.load(open(OC_JSON))
except Exception: pass

# Source 5: env.vars block inside openclaw.json (Trevor's inline pattern — Mac has 70 keys here)
env_vars = cfg.get("env", {}).get("vars", {})
for alias in ALIASES:
    if alias in env_vars and env_vars[alias]:
        emit(f"env.vars.{alias}", env_vars[alias])

# Source 6: models.providers.<name>.apiKey
provider_map = {
    "OPENROUTER_API_KEY": "openrouter",
    "OPENAI_API_KEY": "openai",
    "GEMINI_API_KEY": "google",
    "GOOGLE_API_KEY": "google",
    "OLLAMA_API_KEY": "ollama",
    "ANTHROPIC_API_KEY": "anthropic",
    "DEEPSEEK_API_KEY": "deepseek",
}
pk = provider_map.get(CANONICAL)
if pk:
    val = cfg.get("models", {}).get("providers", {}).get(pk, {}).get("apiKey", "")
    if val:
        emit(f"models.providers.{pk}.apiKey", val)

# Source 7: plugins.entries.<plugin>.config.*
for pname, p in (cfg.get("plugins", {}).get("entries", {}) or {}).items():
    pc = p.get("config", {}) if isinstance(p, dict) else {}
    for alias in ALIASES:
        if alias in pc and pc[alias]:
            emit(f"plugins.entries.{pname}.config.{alias}", pc[alias])
    for fld in ("apiKey", "token", "secret", "key"):
        v = pc.get(fld, "")
        if v and CANONICAL.lower().replace("_","") in (pname + fld).lower().replace("_",""):
            emit(f"plugins.entries.{pname}.config.{fld}", v)

# Source 8: auth-profiles.json
try:
    auth = json.load(open(OC_AUTH))
    for prof_id, prof in (auth.get("profiles") or {}).items():
        if not isinstance(prof, dict): continue
        provider = prof.get("provider", "").lower()
        canonical_provider = CANONICAL.replace("_API_KEY","").lower()
        if provider and provider == canonical_provider and prof.get("key"):
            emit(f"auth-profiles.{prof_id}.key", prof["key"])
except Exception: pass

# Source 9: ~/.openclaw/secrets.json
if os.path.isfile(SECRETS_JSON):
    try:
        s = json.load(open(SECRETS_JSON))
        def find(obj, target_aliases):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in target_aliases and isinstance(v, (str,int)) and not isinstance(v, bool) and v:
                        return (k, v)
                    if isinstance(v, (dict, list)):
                        r = find(v, target_aliases)
                        if r: return r
            elif isinstance(obj, list):
                for it in obj:
                    r = find(it, target_aliases)
                    if r: return r
            return None
        f = find(s, ALIASES)
        if f: emit(f"secrets.json.{f[0]}", f[1])
    except Exception: pass

# Source 10: deep recursive scan of openclaw.json for any field name matching alias.
# v10.13.7: exclude bool values (isinstance(True, int) was returning True before,
# matching permission flags like {"FISH_AUDIO_API_KEY": true} as a "found" key).
def deep_find(obj, target_aliases, parent=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{parent}.{k}" if parent else k
            if k in target_aliases and isinstance(v, (str,int)) and not isinstance(v, bool) and v:
                return (full, v)
            r = deep_find(v, target_aliases, full)
            if r: return r
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            r = deep_find(it, target_aliases, f"{parent}[{i}]")
            if r: return r
    return None
f = deep_find(cfg, ALIASES)
if f: emit(f"deep:{f[0]}", f[1])
PYEOF
)
    if [ -n "$result" ]; then
        local src val
        src=$(echo "$result" | head -1 | sed 's/^src=//')
        val=$(echo "$result" | sed -n '2p')
        # v10.13.7: belt-and-suspenders — even if Python's emit() somehow let
        # a placeholder through (shouldn't, but defense in depth), validate
        # again at the bash boundary before reporting "Found" to the operator.
        # Pass $CANONICAL so the provider-regex stage 1 check runs.
        if [ -n "$val" ] && looks_like_real_key "$val" "$CANONICAL"; then
            echo "    [src: $src]" >&2
            echo "$val"
            return
        elif [ -n "$val" ]; then
            echo "    [skip: $src=<rejected as placeholder or wrong shape for $CANONICAL>]" >&2
        fi
    fi

    echo ""
}

# Back-compat shim for older callers
search_env_var() { search_env_var_mac "$@"; }

# build_env_locations — platform-conditional env/secrets location reporter (W7.2).
# Echoes the canonical env/secrets paths for this box to stdout (one per line).
# Read-only: never writes. Safe to call from any context.
# Mac:  ~/.openclaw/secrets/.env (primary secrets store)
# VPS:  live process env is primary (docker exec <ctr> printenv);
#       host compose env file is the write target (/docker/<project>/.env);
#       persistent container secrets store is /data/.openclaw/secrets/.env.
build_env_locations() {
    if [ -d "/data/.openclaw" ]; then
        # VPS Docker (Hostinger / Contabo)
        echo "live-process-env: docker exec <container> printenv  # check this first"
        echo "host-compose-env: /docker/<project>/.env  # write target; feed via compose env_file"
        echo "container-secrets: /data/.openclaw/secrets/.env  # persistent inside container"
    elif [ -d "$HOME/.openclaw" ]; then
        # Mac (new install)
        echo "$HOME/.openclaw/secrets/.env"
    elif [ -d "$HOME/clawd" ]; then
        # Mac legacy
        echo "$HOME/clawd/secrets/.env"
    else
        echo "UNKNOWN: no OpenClaw root found at /data/.openclaw or $HOME/.openclaw" >&2
        return 1
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# has_usable_gemini_key — SMART Google/Gemini key detection (v13.2.1)
# ──────────────────────────────────────────────────────────────────────────────
# WHY THIS EXISTS (the v13.2.0 regression it fixes):
#   v13.2.0's configure_active_memory HARD-PINNED gemini-embedding-2 as the
#   embedding default whenever it ran. On 6 boxes that have NO usable Google key
#   that pinned a model the box cannot serve — the embed index then fails on
#   every search (it requests a model with no credential). The fix is to make the
#   gemini default CONDITIONAL on a usable key. But "no key" must be a HIGH BAR:
#   a single Google credential is the SAME key under THREE different env NAMES and
#   can live in SEVERAL stores. We must check ALL of them before concluding
#   "no key" (item: google-api-key-three-aliases + client-box-env-stores +
#   credential-check-live-process-env-first).
#
# Aliases (ALL three are the SAME Google AI Studio key):
#   GOOGLE_API_KEY  ==  GOOGLE_AI_STUDIO_API_KEY  ==  GEMINI_API_KEY
#   (get_alias_list "GEMINI_API_KEY" already returns these three plus
#    GOOGLE_GEMINI_API_KEY / GOOGLE_GENERATIVE_AI_API_KEY / GOOGLE_AI_API_KEY).
#
# Stores checked (first hit wins → return true):
#   1. search_env_var "GEMINI_API_KEY"  — the bulletproof discovery path. On Mac
#      this already covers: live shell env (printenv, all aliases), every .env /
#      secrets / .envrc / shell-rc file under $HOME (incl. ~/.openclaw/secrets/.env,
#      ~/clawd/secrets/.env, ~/.env …), openclaw.json env.vars, the
#      models.providers.google.apiKey provider block, plugin configs, secrets.json,
#      and a deep recursive scan. (Every value passes looks_like_real_key, which
#      also enforces the AIza… shape — so a placeholder cannot register as "found".)
#   2. ~/.openclaw/workspace/.env                — explicitly named store, not in
#      the Mac walker's tier-1 list (it lives under workspace/, walker depth covers
#      it but we check it explicitly for both platforms).
#   3. VPS host /docker/<project>/.env           — the docker-compose env_file that
#      feeds the container; NOT visible to the Mac $HOME walker.
#   4. Live CONTAINER env (docker exec <ctr> printenv) — the definitive runtime
#      env on a VPS; a key injected only at compose-time still shows here.
#
# Echoes the resolved key to stdout (so callers may reuse it) and returns 0 when
# ANY alias is found in ANY store; returns 1 (and echoes nothing) when GENUINELY
# absent everywhere.
GEMINI_ALL_ALIASES="GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_AI_STUDIO_API_KEY GOOGLE_GEMINI_API_KEY GOOGLE_GENERATIVE_AI_API_KEY GOOGLE_AI_API_KEY"

has_usable_gemini_key() {
    local _found=""

    # 1. Bulletproof discovery (covers the 3 aliases + every Mac store + config).
    _found=$(search_env_var "GEMINI_API_KEY" 2>/dev/null || true)
    if [ -n "$_found" ]; then echo "$_found"; return 0; fi

    # 2. ~/.openclaw/workspace/.env — explicitly named in the requirement.
    local _wsenv="${HOME}/.openclaw/workspace/.env"
    [ -f "/data/.openclaw/workspace/.env" ] && _wsenv="/data/.openclaw/workspace/.env"
    if [ -f "$_wsenv" ]; then
        for _a in $GEMINI_ALL_ALIASES; do
            _found=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${_a}=" "$_wsenv" 2>/dev/null \
                | grep -vE "^[[:space:]]*#" \
                | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${_a}=//" \
                | sed -E 's/[[:space:]]*#.*$//' | head -1 || true)
            _found="${_found%\"}"; _found="${_found#\"}"
            _found="${_found%\'}"; _found="${_found#\'}"
            if [ -n "$_found" ] && looks_like_real_key "$_found" "GEMINI_API_KEY"; then
                echo "    [src: workspace/.env:$_a → GEMINI_API_KEY]" >&2
                echo "$_found"; return 0
            fi
        done
    fi

    # 3. VPS host docker-compose env_file: /docker/<project>/.env (+ /data/docker).
    if [ -d "/docker" ] || [ -d "/data/docker" ]; then
        local _ef
        while IFS= read -r _ef; do
            [ -z "$_ef" ] && continue
            for _a in $GEMINI_ALL_ALIASES; do
                _found=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${_a}=" "$_ef" 2>/dev/null \
                    | grep -vE "^[[:space:]]*#" \
                    | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${_a}=//" \
                    | sed -E 's/[[:space:]]*#.*$//' | head -1 || true)
                _found="${_found%\"}"; _found="${_found#\"}"
                _found="${_found%\'}"; _found="${_found#\'}"
                if [ -n "$_found" ] && looks_like_real_key "$_found" "GEMINI_API_KEY"; then
                    echo "    [src: $_ef:$_a → GEMINI_API_KEY]" >&2
                    echo "$_found"; return 0
                fi
            done
        done < <(find /docker /data/docker -maxdepth 2 -name ".env" 2>/dev/null)
    fi

    # 4. Live CONTAINER env (definitive on a VPS — key may be injected at
    #    compose-time only). Try the running OpenClaw container's printenv.
    if command -v docker >/dev/null 2>&1; then
        local _ctr
        _ctr=$(docker ps --format '{{.Names}}' 2>/dev/null \
            | grep -iE 'openclaw|clawd' | head -1 || true)
        if [ -n "$_ctr" ]; then
            for _a in $GEMINI_ALL_ALIASES; do
                _found=$(docker exec "$_ctr" printenv "$_a" 2>/dev/null | head -1 || true)
                if [ -n "$_found" ] && looks_like_real_key "$_found" "GEMINI_API_KEY"; then
                    echo "    [src: docker exec $_ctr printenv $_a → GEMINI_API_KEY]" >&2
                    echo "$_found"; return 0
                fi
            done
        fi
    fi

    # Genuinely absent in every alias × every store.
    return 1
}

discover_all_credentials() {
    step "Bulletproof Credential Discovery (v10.1.1 — Mac mini)"
    note "Lookup priority: shell env → \$HOME-wide .env / secrets / .envrc / shell-rc walk (depth 4) → sourced rc files (subshell) → openclaw.json env.vars/providers/plugins → auth-profiles.json → secrets.json → deep scan"
    # v10.13.3: emit how many candidate env files we'll search so the operator
    # can SEE if their file got enumerated (and can grep the log if not).
    local _file_count
    _file_count=$(printf '%s\n' "${MAC_ENV_FILE_LIST:-}" | grep -c '^/' 2>/dev/null || true)
    [ -z "$_file_count" ] && _file_count=0
    if [ "$_file_count" -eq 0 ]; then
        # Warm the cache so the count is non-zero. Call once with a dummy var.
        search_env_var_mac _OPENCLAW_PROBE_NONEXISTENT >/dev/null 2>&1 || true
        _file_count=$(printf '%s\n' "${MAC_ENV_FILE_LIST:-}" | grep -c '^/' 2>/dev/null || true)
        [ -z "$_file_count" ] && _file_count=0
    fi
    note "Candidate env files discovered under \$HOME: $_file_count"

    # Canonical credential names. Aliases are handled inside search_env_var_mac
    # via get_alias_list — extending the alias set requires editing only that.
    local CRED_LIST="GOOGLE_API_KEY:Google"
    CRED_LIST="$CRED_LIST|GEMINI_API_KEY:Gemini"
    CRED_LIST="$CRED_LIST|OPENAI_API_KEY:OpenAI"
    CRED_LIST="$CRED_LIST|OPENROUTER_API_KEY:OpenRouter"
    CRED_LIST="$CRED_LIST|OLLAMA_API_KEY:Ollama Cloud"
    CRED_LIST="$CRED_LIST|ANTHROPIC_API_KEY:Anthropic Claude"
    CRED_LIST="$CRED_LIST|DEEPSEEK_API_KEY:DeepSeek"
    CRED_LIST="$CRED_LIST|GOHIGHLEVEL_API_KEY:GHL (PIT — GoHighLevel Private Integration Token)"
    CRED_LIST="$CRED_LIST|GOHIGHLEVEL_LOCATION_ID:GHL Location ID"
    CRED_LIST="$CRED_LIST|FISH_AUDIO_API_KEY:Fish Audio"
    CRED_LIST="$CRED_LIST|FISH_AUDIO_VOICE_ID:Fish Audio Voice"
    CRED_LIST="$CRED_LIST|ELEVENLABS_API_KEY:ElevenLabs"
    # v19.16.1: Podbean publishing goes through BlackCEO's n8n credential BROKER.
    # A client box holds ONLY the broker pair (PODBEAN_BROKER_WEBHOOK_URL +
    # PODBEAN_BROKER_TOKEN) plus the per-client Podbean Channel ID (podcast_id).
    # The Podbean OAuth app client_id/client_secret are BlackCEO's SINGLE shared
    # app: they live ONLY inside the n8n broker, are NEVER asked from the client,
    # and are NEVER required or discovered on a client box (the local
    # client_credentials mint is an operator-OWN-box fallback resolved directly by
    # podbean_publish.sh, not a prerequisite). So discovery checks the broker pair
    # + Channel ID here — NOT client_id/secret (which would falsely report
    # "missing" on every broker-mode box).
    CRED_LIST="$CRED_LIST|PODBEAN_BROKER_WEBHOOK_URL:Podbean n8n broker webhook URL (broker mode)"
    CRED_LIST="$CRED_LIST|PODBEAN_BROKER_TOKEN:Podbean n8n broker shared token (broker mode)"
    # PODBEAN_PODCAST_ID is the per-client Podbean Channel ID — the ONLY Podbean
    # value the client supplies (it selects their show under BlackCEO's host
    # account) and it is not a secret.
    CRED_LIST="$CRED_LIST|PODBEAN_PODCAST_ID:Podbean Channel ID (podcast_id, per-client)"
    CRED_LIST="$CRED_LIST|TAVILY_API_KEY:Tavily Search"
    CRED_LIST="$CRED_LIST|BRAVE_API_KEY:Brave Search"
    CRED_LIST="$CRED_LIST|KIE_API_KEY:KIE.ai (skill 27)"
    CRED_LIST="$CRED_LIST|FAL_API_KEY:Fal.ai"
    CRED_LIST="$CRED_LIST|TELEGRAM_BOT_TOKEN:Telegram Bot"
    CRED_LIST="$CRED_LIST|CONTEXT7_API_KEY:Context7 MCP"
    CRED_LIST="$CRED_LIST|AIRTABLE_TOKEN:Airtable"
    CRED_LIST="$CRED_LIST|GITHUB_TOKEN:GitHub"
    CRED_LIST="$CRED_LIST|VERCEL_TOKEN:Vercel"
    CRED_LIST="$CRED_LIST|SUPABASE_SERVICE_ROLE_KEY:Supabase"

    local found_count=0
    local missing_creds=""
    local creds="$CRED_LIST"

    while [ -n "$creds" ]; do
        local CRED_ENTRY
        if echo "$creds" | grep -q "|"; then
            CRED_ENTRY=$(echo "$creds" | cut -d'|' -f1)
            creds=$(echo "$creds" | cut -d'|' -f2-)
        else
            CRED_ENTRY="$creds"; creds=""
        fi
        local VAR_NAME=$(echo "$CRED_ENTRY" | cut -d':' -f1)
        local SERVICE=$(echo "$CRED_ENTRY" | cut -d':' -f2-)
        local VALUE
        VALUE=$(search_env_var "$VAR_NAME")
        if [ -n "$VALUE" ]; then
            found_count=$((found_count + 1))
            success "Found $VAR_NAME — $SERVICE"
            CREDS_FOUND_LIST="$CREDS_FOUND_LIST|$VAR_NAME"
        else
            missing_creds="$missing_creds|$VAR_NAME ($SERVICE)"
        fi
    done

    note "$found_count credentials discovered."
    if [ -n "$missing_creds" ]; then
        warn "Not configured yet (some skills will skip or require these later):"
        echo "$missing_creds" | tr '|' '\n' | grep -v '^$' | sed 's/^/      /'
    fi
}

# has_cred <CANONICAL_VAR> — returns 0 if discover_all_credentials found it
has_cred() {
    case "|${CREDS_FOUND_LIST}|" in
        *"|$1|"*) return 0 ;;
        *) return 1 ;;
    esac
}

# ----------------------------------------------------------
# Directory Discovery
# ----------------------------------------------------------
discover_skills_dir() {
    # Mac canonical skills location is ~/Downloads/openclaw-master-files (where
    # this installer extracts to). Fallbacks include the onboarding stage dir,
    # legacy locations, and the ~/openclaw-onboarding clone if present.
    local CANDIDATES="$OC_DOWNLOADS/openclaw-master-files"
    CANDIDATES="$CANDIDATES|$OC_CONFIG/skills"
    CANDIDATES="$CANDIDATES|$OC_CONFIG/onboarding"
    CANDIDATES="$CANDIDATES|$HOME/openclaw-onboarding"

    local dirs="$CANDIDATES"
    while [ -n "$dirs" ]; do
        local DIR
        if echo "$dirs" | grep -q "|"; then
            DIR=$(echo "$dirs" | cut -d'|' -f1)
            dirs=$(echo "$dirs" | cut -d'|' -f2-)
        else
            DIR="$dirs"; dirs=""
        fi
        if [ -d "$DIR" ]; then
            local SKILL_COUNT
            SKILL_COUNT=$(find "$DIR" -maxdepth 1 -type d -name "[0-9]*" 2>/dev/null | wc -l | tr -d ' ')
            if [ "$SKILL_COUNT" -gt "0" ]; then
                echo "$DIR"
                return
            fi
        fi
    done
    
    echo "$OC_DOWNLOADS/openclaw-master-files"
}

discover_skills() {
    # PRD 3.2: *-ARCHIVED skill folders are excluded from both counts so they
    # are never reflected in Telegram progress messages and do not inflate the
    # SKILL_COUNT that drives the install loop.  The install loop itself also
    # guards with a case-match on *ARCHIVED*, so both layers agree.
    local base_dir="${1:-$OC_CONFIG/onboarding}"
    local numbered_count
    numbered_count=$(find "$base_dir" -maxdepth 1 -type d -name "[0-9][0-9]-*" 2>/dev/null \
        | grep -v -- '-ARCHIVED$' | wc -l | tr -d ' ' || true)
    local skill_md_count
    skill_md_count=$(find "$base_dir" -maxdepth 2 -name "SKILL.md" 2>/dev/null \
        | grep -v -- '-ARCHIVED/' | wc -l | tr -d ' ' || true)

    local max_count=$numbered_count
    if [ "$skill_md_count" -gt "$max_count" ] 2>/dev/null; then
        max_count=$skill_md_count
    fi
    echo "$max_count"
}

# ----------------------------------------------------------
# v10.15.51 — link_shared_core_files (Zero-Human-Workforce file model)
# ----------------------------------------------------------
# On EVERY box, ALL of that account's agents + sub-agents SHARE the box's ONE
# canonical AGENTS.md / TOOLS.md / USER.md via symlink (NOT duplicated). Per-agent
# files (IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md) stay each agent's OWN.
#
# CANON_DIR = the box's DEFAULT AGENT WORKSPACE (agents.defaults.workspace, same
# resolver as install.sh Step 10 / obs_resolve_workspace). The symlink target is
# ALWAYS THIS LOCAL box's own canonical — NEVER a hardcoded or cross-box/cross-
# account path. The client is the USER: a client box links to the CLIENT's own
# files only (co-mingling guard, N0).
#
# NESTED WORKFLOW AGENT EXEMPTION: any workspace path matching */workflows/*/agents/*
# (internal workflow micro-agents) is NEVER touched.
#
# Idempotent: a correct existing symlink is a no-op; an absent file stays absent;
# a second run produces no new backups and no churn. Every action logs with the
# [link-shared] prefix. A real file is BACKED UP (never deleted) to
# <file>.bak-unify-<ts>, and any of its content not already in the canonical file
# is APPENDED (additive only) to the agent's OWN IDENTITY.md under a guarded marker
# before the file is replaced with the symlink.
# ----------------------------------------------------------
link_shared_core_files() {
  local CANON_DIR="${1:-}"

  # Resolve CANON_DIR = THIS box's own default agent workspace. Read THIS box's
  # openclaw.json only (co-mingling guard) — never a foreign/hardcoded path.
  local _OCJSON="$OC_JSON"
  [ -f "/data/.openclaw/openclaw.json" ] && _OCJSON="/data/.openclaw/openclaw.json"
  if [ -z "$CANON_DIR" ]; then
    if command -v obs_resolve_workspace >/dev/null 2>&1; then
      CANON_DIR="$(obs_resolve_workspace)"
    elif [ -f "$_OCJSON" ] && command -v python3 >/dev/null 2>&1; then
      CANON_DIR="$(OC_JSON="$_OCJSON" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict) and ag.get("id") == "main" and ag.get("workspace"):
            print(os.path.expanduser(ag["workspace"])); break
    else:
        ws = cfg.get("agents", {}).get("defaults", {}).get("workspace")
        if ws:
            print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
)"
    fi
  fi
  if [ -z "$CANON_DIR" ]; then
    if [ -d "/data/.openclaw" ]; then
      CANON_DIR="/data/.openclaw/workspace"
    else
      CANON_DIR="$OC_WORKSPACE_DEFAULT"
    fi
  fi

  note "[link-shared] Zero-Human-Workforce file unification"
  note "[link-shared] CANON_DIR (this box's own canonical) = $CANON_DIR"
  mkdir -p "$CANON_DIR" 2>/dev/null || true

  local f
  for f in AGENTS.md TOOLS.md USER.md; do
    [ -e "$CANON_DIR/$f" ] || { touch "$CANON_DIR/$f" 2>/dev/null || true; }
  done

  local CANON_REAL
  CANON_REAL="$(cd "$CANON_DIR" 2>/dev/null && pwd -P || echo "$CANON_DIR")"

  local TS
  TS="$(date +%Y%m%d-%H%M%S)"

  # Enumerate agent workspaces: openclaw.json agents[].workspace + scan dirs.
  local WS_LIST_FILE
  WS_LIST_FILE="$(mktemp 2>/dev/null || echo "/tmp/link-shared-ws-$$.txt")"
  : > "$WS_LIST_FILE"

  if [ -f "$_OCJSON" ] && command -v python3 >/dev/null 2>&1; then
    OC_JSON="$_OCJSON" python3 - >> "$WS_LIST_FILE" 2>/dev/null <<'PYEOF' || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict):
            ws = ag.get("workspace")
            if ws:
                print(os.path.expanduser(ws))
except Exception:
    pass
PYEOF
  fi

  local OC_ROOT="$HOME/.openclaw"
  [ -d "/data/.openclaw" ] && OC_ROOT="/data/.openclaw"
  local _scan
  for _scan in \
      "$OC_ROOT/workspaces" \
      "$CANON_REAL/agents" \
      "$CANON_REAL/departments"; do
    [ -d "$_scan" ] || continue
    find "$_scan" -type d -print 2>/dev/null \
      | while IFS= read -r d; do
          if [ -e "$d/AGENTS.md" ] || [ -e "$d/IDENTITY.md" ] || [ -e "$d/SOUL.md" ]; then
            echo "$d"
          fi
        done >> "$WS_LIST_FILE" 2>/dev/null || true
  done

  local LINKED=0 REPOINTED=0 BACKED_UP=0 PRESERVED=0 SKIPPED_ANT=0 NOOP=0

  local W
  while IFS= read -r W; do
    [ -n "$W" ] || continue
    W="$(printf '%s' "$W" | sed 's:/*$::')"
    [ -d "$W" ] || continue

    local W_REAL
    W_REAL="$(cd "$W" 2>/dev/null && pwd -P || echo "$W")"

    # Skip the canonical workspace itself — it OWNS the real files.
    [ "$W_REAL" = "$CANON_REAL" ] && continue

    # NESTED WORKFLOW AGENT EXEMPTION: never touch */workflows/*/agents/* micro-agents.
    case "$W_REAL/" in
      */workflows/*/agents/*)
        note "[link-shared] SKIP (nested workflow agent exempt): $W_REAL"
        SKIPPED_ANT=$((SKIPPED_ANT + 1))
        continue
        ;;
    esac

    for f in AGENTS.md TOOLS.md USER.md; do
      local TARGET="$CANON_REAL/$f"
      local LINKPATH="$W_REAL/$f"

      if [ -L "$LINKPATH" ]; then
        local CUR
        CUR="$(readlink "$LINKPATH" 2>/dev/null || echo '')"
        local CUR_REAL
        CUR_REAL="$(cd "$(dirname "$LINKPATH")" 2>/dev/null && cd "$(dirname "$CUR")" 2>/dev/null && pwd -P 2>/dev/null)/$(basename "$CUR")"
        if [ "$CUR" = "$TARGET" ] || [ "$CUR_REAL" = "$TARGET" ]; then
          NOOP=$((NOOP + 1))
        else
          ln -sfn "$TARGET" "$LINKPATH" 2>/dev/null \
            && { note "[link-shared] REPOINT $LINKPATH -> $TARGET (was: $CUR)"; REPOINTED=$((REPOINTED + 1)); } \
            || warn "[link-shared] could not repoint $LINKPATH"
        fi

      elif [ -f "$LINKPATH" ]; then
        local BAK="$LINKPATH.bak-unify-$TS"
        cp -p "$LINKPATH" "$BAK" 2>/dev/null \
          && { note "[link-shared] BACKUP $LINKPATH -> $BAK"; BACKED_UP=$((BACKED_UP + 1)); } \
          || { warn "[link-shared] backup failed for $LINKPATH — leaving file untouched"; continue; }

        local AGENT_NAME
        AGENT_NAME="$(basename "$W_REAL")"
        local IDFILE="$W_REAL/IDENTITY.md"
        local PMARK="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification ${TS}) -->"
        local PMARK_PREFIX="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification "
        if ! grep -qF "$PMARK_PREFIX" "$IDFILE" 2>/dev/null; then
          AGENT_F="$LINKPATH" CANON_F="$TARGET" ID_F="$IDFILE" PMARK="$PMARK" \
            python3 - <<'PYEOF' 2>/dev/null || true
import os
src   = os.environ["AGENT_F"]
canon = os.environ["CANON_F"]
idf   = os.environ["ID_F"]
mark  = os.environ["PMARK"]
try:
    src_text = open(src, encoding="utf-8", errors="replace").read()
except Exception:
    src_text = ""
try:
    canon_text = open(canon, encoding="utf-8", errors="replace").read()
except Exception:
    canon_text = ""
blocks, cur = [], []
for line in src_text.splitlines():
    if line.strip() == "":
        if cur:
            blocks.append("\n".join(cur)); cur = []
    else:
        cur.append(line)
if cur:
    blocks.append("\n".join(cur))
unique = [b for b in blocks if b.strip() and b.strip() not in canon_text]
if unique:
    with open(idf, "a", encoding="utf-8") as fh:
        fh.write("\n\n" + mark + "\n")
        fh.write("\n\n".join(unique))
        fh.write("\n")
    print("PRESERVED")
PYEOF
          if grep -qF "$PMARK" "$IDFILE" 2>/dev/null; then
            note "[link-shared] PRESERVE unique $f content -> $IDFILE"
            PRESERVED=$((PRESERVED + 1))
          fi
        fi

        rm -f "$LINKPATH" 2>/dev/null
        ln -sfn "$TARGET" "$LINKPATH" 2>/dev/null \
          && { note "[link-shared] LINK $LINKPATH -> $TARGET"; LINKED=$((LINKED + 1)); } \
          || warn "[link-shared] could not create symlink $LINKPATH"

      else
        :  # absent → leave absent (no churn)
      fi
    done
  done < <(sort -u "$WS_LIST_FILE")

  rm -f "$WS_LIST_FILE" 2>/dev/null || true

  note "[link-shared] done: linked=$LINKED repointed=$REPOINTED backed-up=$BACKED_UP preserved=$PRESERVED workflow-agent-skipped=$SKIPPED_ANT already-ok=$NOOP"
  note "[link-shared] IDENTITY/SOUL/MEMORY/HEARTBEAT left as each agent's OWN files (per-agent, not shared)."
}

# ----------------------------------------------------------
# Concurrency Configuration
# ----------------------------------------------------------
configure_concurrency_LEGACY_UNUSED() {
    step "Configuring Sub-Agent Concurrency"
    
    local OPENCLAW_JSON="$OC_JSON"

    if [ ! -f "$OPENCLAW_JSON" ]; then
        warn "openclaw.json not found - skipping concurrency config"
        return
    fi

    backup_config_file "$OPENCLAW_JSON"

    OPENCLAW_JSON="$OPENCLAW_JSON" python3 << 'PYEOF'
import json, os, sys

path = os.environ['OPENCLAW_JSON']
try:
    with open(path) as f:
        config = json.load(f)

    agents = config.setdefault('agents', {})
    defaults = agents.setdefault('defaults', {})
    sub = defaults.setdefault('subagents', {})
    
    # v8.7.0 concurrency settings
    sub['maxConcurrent'] = 50
    sub['maxQueue'] = 10
    sub['maxDepth'] = 4
    
    defaults['subagents'] = sub
    agents['defaults'] = defaults
    config['agents'] = agents
    
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print("  ✓ Set maxConcurrent=50, maxQueue=10, maxDepth=4")
except Exception as e:
    print(f"  ✗ Could not update concurrency: {e}", file=sys.stderr)
PYEOF
}

# ----------------------------------------------------------
# Bookkeeping: install dir + stale-state cleanup (v10.5.5)
# ----------------------------------------------------------
# Self-healing: we do NOT downgrade ONBOARDING_VERSION to whatever the
# previous install wrote to disk. The constant in THIS script is the
# truth. Any stale ~/.openclaw/onboarding/version file from a prior
# install is informational only — it will be rewritten at end of run.
#
# We also auto-clear .install-in-progress if it's older than 1 hour
# (i.e. a previous run crashed). No more "rm to clear" tax on clients.
ONBOARDING_DIR="$OC_CONFIG/onboarding"
mkdir -p "$ONBOARDING_DIR"
INSTALL_FLAG="$ONBOARDING_DIR/.install-in-progress"

# Capture prior version for purely informational logging
PRIOR_VERSION=""
if [ -f "$ONBOARDING_DIR/version" ] 2>/dev/null; then
    PRIOR_VERSION=$(cat "$ONBOARDING_DIR/version" 2>/dev/null | tr -d '[:space:]')
    if [ -n "$PRIOR_VERSION" ] && [ "$PRIOR_VERSION" != "$ONBOARDING_VERSION" ]; then
        note "Upgrading from $PRIOR_VERSION → $ONBOARDING_VERSION"
    fi
fi

# Stale-lock auto-clear: if the lock file exists but is > 60 minutes old,
# the previous run crashed mid-install. Wipe it instead of blocking.
if [ -f "$INSTALL_FLAG" ]; then
    LOCK_AGE_MINS=$(( ( $(date +%s) - $(stat -f %m "$INSTALL_FLAG" 2>/dev/null || stat -c %Y "$INSTALL_FLAG" 2>/dev/null || echo 0) ) / 60 ))
    if [ "$LOCK_AGE_MINS" -gt 60 ] 2>/dev/null; then
        warn "Stale install lock detected (${LOCK_AGE_MINS} min old) — auto-clearing and continuing"
        rm -f "$INSTALL_FLAG"
    else
        step "Installation Already In Progress"
        error "Another installation is running (started ${LOCK_AGE_MINS} min ago)."
        error "If you know it crashed, run: rm $INSTALL_FLAG"
        exit 0
    fi
fi

touch "$INSTALL_FLAG"
trap 'rm -f "$INSTALL_FLAG"' EXIT

# ----------------------------------------------------------
# Main Header
# ----------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     OpenClaw Onboarding Installer        ║"
echo "║              ${ONBOARDING_VERSION}                      ║"
echo "╚══════════════════════════════════════════╝"
echo ""
# v13.8.3: ${LOG_FILE:-} guard (defense-in-depth). LOG_FILE is set by the
# platform bootstrap (mac/vps §log-file setup) or the install.sh curl-fallback;
# this guard ensures the main header can never abort under `set -u` if a future
# code path forgets to set it (the VPS-clone-path regression fixed in v13.8.3).
note "Log file: ${LOG_FILE:-(not set — check platform bootstrap)}"

# ----------------------------------------------------------
# CLI Scope Auto-Repair (v10.0.3)
# ----------------------------------------------------------
# Per a Mac client (Floyd) reproduction documented at:
#   https://github.com/trevorotts1/openclaw-onboarding/issues
# Fresh OpenClaw pairings can leave the CLI device with only
# [operator.read, operator.pairing] — missing operator.write/admin.
# Result: `openclaw message send` and `openclaw cron create` fail with
# "scope upgrade pending approval" + "device is asking for more scopes
# than currently approved" + gateway status reports "Capability: read-only".
#
# Detection: `openclaw gateway status --verbose | grep "Capability:"`
# Healthy = "admin-capable" | "write-capable". Broken = "read-only".
#
# Auto-repair strategy:
#   PLAN A: openclaw devices rotate --token <master> (sanctioned CLI path)
#   PLAN B: direct edit of ~/.openclaw/devices/paired.json (proven on Floyd's
#           machine; uses OpenClaw's own state files — schema verified live
#           against 2026.5.x).
# Both end with `openclaw gateway restart` + verification via Capability check.
#
# Master token comes from gateway.auth.token in openclaw.json — the same token
# the gateway uses to authenticate itself. Per --token CLI flag (documented),
# operations authenticated with this token run at gateway-master level rather
# than per-device, which can bypass the chicken-and-egg approval problem.

get_master_token() {
    python3 -c "
import json, os, sys
try:
    cfg = json.load(open(os.path.expanduser('$OC_JSON')))
    print(cfg.get('gateway',{}).get('auth',{}).get('token','') or '')
except Exception: pass
" 2>/dev/null
}

get_gateway_capability() {
    openclaw gateway status --verbose 2>/dev/null | grep -E "^Capability:" | awk '{print $2}' | head -1 || true
}

# auto_repair_cli_scopes — detect read-only state, try CLI repair with master
# token, fall back to direct file edit. Returns 0 on success or no-op, 1 on
# failure (install continues either way; Telegram/cron will fail visibly).
auto_repair_cli_scopes() {
    local capability master_token cli_id paired_file pending_file

    capability=$(get_gateway_capability)
    if [ -z "$capability" ]; then
        note "Gateway capability check skipped (could not query — gateway may not be running yet)."
        return 0
    fi
    if [ "$capability" != "read-only" ]; then
        success "Gateway capability OK: $capability — no scope repair needed."
        return 0
    fi

    warn "Gateway reports Capability: read-only — CLI device is missing operator.write."
    warn "This blocks Telegram, cron, and every CLI-side gateway call. Auto-repairing..."

    master_token=$(get_master_token)
    if [ -z "$master_token" ]; then
        warn "Cannot read gateway.auth.token from $OC_JSON — auto-repair not possible."
        warn "Manual fix: see https://github.com/trevorotts1/openclaw-onboarding/blob/main/docs/scope-repair.md"
        return 1
    fi

    # Find the CLI device id (the one with clientId=cli and missing write scope)
    cli_id=$(openclaw devices list --token "$master_token" --json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    paired = d.get('paired', []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
    for p in paired:
        if not isinstance(p, dict): continue
        if p.get('clientId') != 'cli': continue
        scopes = set(p.get('scopes', []) or [])
        if 'operator.write' not in scopes and 'operator.admin' not in scopes:
            print(p.get('deviceId') or ''); break
except Exception: pass
" 2>/dev/null) || cli_id=""

    # ─── PLAN A: CLI rotate + approve with master token ───
    if [ -n "$cli_id" ]; then
        note "Plan A: trying CLI rotate with master token for device ${cli_id:0:20}..."
        local rotate_out=""
        rotate_out=$(openclaw devices rotate --device "$cli_id" --role operator \
            --scope operator.read --scope operator.write --scope operator.admin \
            --scope operator.pairing --scope operator.approvals \
            --token "$master_token" 2>&1)
        echo "$rotate_out" >> "$LOG_FILE"
        sleep 2

        # If rotate created a pending request, approve it with master token
        local pending_id=""
        pending_id=$(openclaw devices list --token "$master_token" --json 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    items = d.get('pending', []) or []
    for it in items:
        if not isinstance(it, dict): continue
        rid = it.get('requestId') or it.get('id')
        if rid: print(rid); break
except Exception: pass
" 2>/dev/null) || pending_id=""

        if [ -n "$pending_id" ]; then
            note "Plan A: pending request $pending_id created — approving with master token..."
            if openclaw devices approve "$pending_id" --token "$master_token" >> "$LOG_FILE" 2>&1; then
                openclaw gateway restart >> "$LOG_FILE" 2>&1
                sleep 5
                capability=$(get_gateway_capability)
                if [ "$capability" != "read-only" ] && [ -n "$capability" ]; then
                    success "Plan A succeeded — capability now: $capability"
                    return 0
                fi
            fi
        fi
        warn "Plan A insufficient (rotate/approve via CLI didn't restore write capability)."
    fi

    # ─── PLAN B: direct paired.json edit (Floyd's proven approach) ───
    note "Plan B: editing $HOME/.openclaw/devices/paired.json directly..."
    paired_file="$HOME/.openclaw/devices/paired.json"
    pending_file="$HOME/.openclaw/devices/pending.json"

    if [ ! -f "$paired_file" ]; then
        warn "$paired_file not found — cannot auto-repair."
        return 1
    fi

    # Backup
    cp "$paired_file" "$paired_file.bak-$(date +%Y%m%d-%H%M%S)"
    note "Backed up paired.json"

    PAIRED_FILE="$paired_file" python3 - <<'PYEOF'
import json, os, sys
paired_file = os.environ['PAIRED_FILE']
TARGET = {'operator.read', 'operator.write', 'operator.admin', 'operator.pairing', 'operator.approvals'}

try:
    with open(paired_file) as f:
        data = json.load(f)
except Exception as e:
    print(f"READ_ERR:{e}"); sys.exit(0)

def upgrade(device):
    """Add target scopes to scopes, approvedScopes, and tokens.operator.scopes."""
    changed = False
    if device.get('clientId') != 'cli': return False
    for field in ('scopes', 'approvedScopes'):
        cur = set(device.get(field, []) or [])
        if not TARGET.issubset(cur):
            device[field] = sorted(cur | TARGET)
            changed = True
    tokens = device.get('tokens', {})
    op_token = tokens.get('operator', {}) if isinstance(tokens, dict) else {}
    if isinstance(op_token, dict):
        cur = set(op_token.get('scopes', []) or [])
        if not TARGET.issubset(cur):
            op_token['scopes'] = sorted(cur | TARGET)
            changed = True
    return changed

fixed_count = 0
# Schema A: dict keyed by deviceId
if isinstance(data, dict):
    for did, device in data.items():
        if isinstance(device, dict) and upgrade(device):
            fixed_count += 1
# Schema B: list of devices
elif isinstance(data, list):
    for device in data:
        if isinstance(device, dict) and upgrade(device):
            fixed_count += 1

if fixed_count:
    with open(paired_file, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"FIXED:{fixed_count}")
else:
    print("NO_CHANGE")
PYEOF

    # Clear stuck pending requests
    if [ -f "$pending_file" ]; then
        cp "$pending_file" "$pending_file.bak-$(date +%Y%m%d-%H%M%S)"
        echo '{}' > "$pending_file"
        note "Cleared pending.json"
    fi

    # Restart gateway so it re-reads paired.json
    note "Restarting gateway to apply scope repair..."
    openclaw gateway restart >> "$LOG_FILE" 2>&1
    sleep 6

    # Verify
    capability=$(get_gateway_capability)
    if [ "$capability" = "read-only" ] || [ -z "$capability" ]; then
        warn "Auto-repair completed but capability check returned '$capability'."
        warn "Manual fix required. See: https://docs.openclaw.ai/gateway/operator-scopes"
        return 1
    fi
    success "Plan B succeeded — capability now: $capability"
    return 0
}

# Run BEFORE first Telegram send so the gateway has write capability when it needs it.
auto_repair_cli_scopes || warn "Scope auto-repair did not complete successfully — Telegram/cron may fail (install will continue)."

send_telegram_progress "Starting OpenClaw Onboarding install ${ONBOARDING_VERSION}..."

# ----------------------------------------------------------
# Step 0: Bootstrap — orchestrator model + sub-agent config + state carryover
# ----------------------------------------------------------
step "Step 0: Bootstrap (model selection + sub-agent config)"

# 0.1 — Recommend /new session for fresh context (not required)
note "Recommendation: if you are over 5 minutes into the current session, start a fresh session with /new BEFORE continuing. The install will pick up where you left off via the state-carryover file at ~/.openclaw/.install-resume.json."
note "This is a recommendation only — the install will proceed either way."

# 0.2 — Write/refresh the state-carryover file
OCJSON="$OC_JSON"
RESUME_FILE="$OC_CONFIG/.install-resume.json"
mkdir -p "$(dirname "$RESUME_FILE")"
cat > "$RESUME_FILE" <<RESUME_JSON
{
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "${ONBOARDING_VERSION}",
  "phase": "A",
  "wave": "1",
  "completed_skills": [],
  "active_skills": [],
  "pending_skills": [],
  "owner_decisions": {},
  "next_step": "Step 0 bootstrap complete — proceeding to credential discovery"
}
RESUME_JSON
success "State carryover initialized at $RESUME_FILE"

# 0.3 — Canonical sub-agent + bootstrap config (v9.7.8)
# Hard-overwrites the numeric limits (these are protocol gates, not preferences).
# Preserves agents.defaults.subagents.model.fallbacks if a client has customized it.
# Sets allowAgents=["*"] on every agents.list entry (wildcard subagent permission).
note "Configuring canonical sub-agent + bootstrap settings (v9.7.8 spec)..."
backup_config_file "$OCJSON"

python3 << PYEOF
import json, os, sys

path = "$OCJSON"
if not os.path.exists(path):
    print(f"  ⚠  {path} does not exist yet — Step 0 will be retried after CLI install", file=sys.stderr)
    sys.exit(0)

with open(path) as f:
    cfg = json.load(f)

agents = cfg.setdefault('agents', {})
defaults = agents.setdefault('defaults', {})
sub = defaults.setdefault('subagents', {})

# Hard-overwrite numeric limits (protocol gates)
sub['maxChildrenPerAgent'] = 20
sub['maxSpawnDepth']       = 4
# maxConcurrent: hard-overwrite to 100, with a min-clamp of 50 (never less)
prev_concurrent = sub.get('maxConcurrent', 100)
try:
    prev_concurrent = int(prev_concurrent)
except (TypeError, ValueError):
    prev_concurrent = 100
sub['maxConcurrent'] = max(100, prev_concurrent) if prev_concurrent >= 50 else 100
# Hard set thinking level
sub['thinking'] = 'high'

# PRESERVE model fallbacks if already set; only seed if missing
model_block = sub.get('model')
if not isinstance(model_block, dict) or 'fallbacks' not in model_block:
    sub['model'] = {
        'fallbacks': [
            'ollama/kimi-k2.6:cloud',
            'openrouter/xiaomi/mimo-v2.5-pro',
            'deepseek/deepseek-v4-pro'
        ]
    }
    print("  ✓ subagents.model.fallbacks seeded (was missing)")
else:
    print("  ℹ  subagents.model.fallbacks preserved (already customized)")

# Bootstrap character limits — hard overwrite
prev_max   = defaults.get('bootstrapMaxChars')
prev_total = defaults.get('bootstrapTotalMaxChars')
defaults['bootstrapMaxChars']       = 200000
defaults['bootstrapTotalMaxChars']  = 400000

print(f"  ✓ bootstrapMaxChars: {prev_max} → 200000")
print(f"  ✓ bootstrapTotalMaxChars: {prev_total} → 400000")
print(f"  ✓ subagents.maxChildrenPerAgent → 20")
print(f"  ✓ subagents.maxConcurrent → {sub['maxConcurrent']} (min-clamp 50)")
print(f"  ✓ subagents.maxSpawnDepth → 4")
print(f"  ✓ subagents.thinking → high")

# NOTE (v11.3.1 fix): agents.defaults.tools.exec is NOT a valid key on
# OpenClaw 2026.6.1+ — the schema validator rejects it with
# "agents.defaults: Invalid input" and openclaw doctor --fix auto-reverts it.
# The correct exec policy lives at TOP-LEVEL tools.exec (set in Step 8 below).
# Generation departments (graphics/video/audio) get explicit per-agent
# tools.allow so they can invoke image_generate/video_generate/music_generate
# even if a parent deny list is in effect. (Set in build-workforce.py.)

# Wildcard allowAgents on every agents.list entry
agent_list = agents.get('list', [])
updated_entries = 0
for entry in agent_list:
    if not isinstance(entry, dict):
        continue
    entry_sub = entry.setdefault('subagents', {})
    prev_allow = entry_sub.get('allowAgents', None)
    if prev_allow != ['*']:
        entry_sub['allowAgents'] = ['*']
        updated_entries += 1
print(f"  ✓ allowAgents=['*'] applied to {updated_entries} agents.list entries (wildcard subagent permission)")

cfg['agents'] = agents
with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)
print("  ✓ openclaw.json written")
PYEOF
success "Canonical sub-agent + bootstrap config applied"

# 0.3b — runRetries ceiling (FLEET-FIX Area 3 / C.2–C.4)
# Seeds agents.defaults.runRetries.{base,perProfile,min,max} SET-IF-ABSENT.
#
# C.1 VERDICT (recorded, do not re-derive): runRetries counts OUTER-RUN-LOOP
# RETRY ITERATIONS, not tool cycles — the installed runtime's own schema doc
# says "Outer run loop retry iteration boundaries for the embedded OpenClaw
# runner to prevent infinite execution loops during failure recovery."
# Ceiling = clamp(base + perProfile * profileCandidateCount, min, max), resolved
# by resolveMaxRunRetryIterations() with 24 / 8 / 32 / 160.
#
# We seed the runtime's OWN defaults, so this is behaviour-neutral on every box
# — it makes the ceiling explicit and auditable instead of buried in the
# runtime. An operator value is NEVER overwritten (set-if-absent, per subkey).
#
# GATED on a per-box schema grep of the runtime actually installed here. Boxes
# on a runtime that lacks the key are SKIPPED and reported as
# CEILING_NOT_SUPPORTED@<version> — writing an unknown key would trip the strict
# schema validator and get the WHOLE config rejected (same failure class as the
# v11.3.1 agents.defaults.tools.exec defect noted above). Never fatal.
# NOTE: this runs under `set -u` (line 97). ONBOARDING_DIR is defined above (see
# the OC_CONFIG/onboarding assignment); SCRIPTS_DIR is NOT — it is only defined
# LATER in this script, so it must never be referenced here. Both expansions are
# written :-safe anyway, so a reordering upstream can't turn this into an
# unbound-variable abort of the whole install.
_WIRE_RUN_RETRIES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/wire-run-retries.sh"
[ -f "$_WIRE_RUN_RETRIES" ] || _WIRE_RUN_RETRIES="${ONBOARDING_DIR:-}/scripts/wire-run-retries.sh"
if [ -f "$_WIRE_RUN_RETRIES" ]; then
    note "Wiring agents.defaults.runRetries ceiling (set-if-absent, schema-gated)..."
    backup_config_file "$OCJSON"
    _RUN_RETRIES_OUT="$(OC_JSON="$OCJSON" bash "$_WIRE_RUN_RETRIES" 2>&1)"
    echo "$_RUN_RETRIES_OUT"
    echo "$_RUN_RETRIES_OUT" >> "$LOG_FILE" 2>/dev/null || true
    case "$_RUN_RETRIES_OUT" in
        *RUNRETRIES_STATUS=SEEDED*)
            success "agents.defaults.runRetries seeded (set-if-absent)" ;;
        *RUNRETRIES_STATUS=PRESERVED*)
            note "agents.defaults.runRetries already set — preserved, not overwritten" ;;
        *RUNRETRIES_STATUS=CEILING_NOT_SUPPORTED@*)
            warn "runRetries ceiling unsupported by this box's runtime — skipped (see CEILING_NOT_SUPPORTED@<version> above)" ;;
        *RUNRETRIES_STATUS=CONFLICT_SKIPPED*)
            warn "agents.defaults.runRetries left untouched (pre-existing non-conforming value)" ;;
        *)
            warn "runRetries wiring returned no status line (non-fatal; see $LOG_FILE)" ;;
    esac
else
    note "scripts/wire-run-retries.sh not found — skipping runRetries ceiling wiring (older bundle)"
fi

# 0.4 — Model selection (advisory; agent picks at runtime based on what's available)
note "Master orchestrator model priority (per INSTALL-CONTRACT.md Rule 10):"
note "  1. Subscription / OAuth (no per-call cost): codex/gpt-5.5, openai-codex/gpt-5.5"
note "  2. Ollama cloud (very low cost): ollama/kimi-k2.6:cloud (orchestrator), ollama/deepseek-v4-pro:cloud (sub-agents)"
note "  3. OpenRouter (priced per token): openrouter/moonshot/kimi-k2.6 thinking=high"
note "  FORBIDDEN by default: claude-opus-*, claude-sonnet-*, openai/* (too expensive — explicit owner consent required)"
note "If the agent cannot determine available models, it must ASK the owner (per Rule 10)."

# ----------------------------------------------------------
# Step 1: Check OpenClaw CLI
# ----------------------------------------------------------
step "Step 1: Verifying OpenClaw CLI"

if ! command -v openclaw >/dev/null 2>&1; then
    error "OpenClaw CLI not found in PATH"
    echo "  Install with: npm install -g openclaw"
    send_telegram_progress "ERROR: OpenClaw CLI not found. Install failed."
    exit 1
fi

success "OpenClaw CLI found: $(command -v openclaw)"

# ----------------------------------------------------------
# Step 1.5: Inject shared operator secrets (v10.13.10+)
# ----------------------------------------------------------
# BEFORE credential discovery — so the values are in secrets/.env + openclaw.json
# when Step 2 runs, and discovery reports them as "Found" via the shared label.
step "Step 1.5: Injecting shared operator secrets (Podbean app credentials etc.)"
inject_shared_operator_secrets

# ----------------------------------------------------------
# Step 2: Silent Credential Discovery
# ----------------------------------------------------------
discover_all_credentials

# ----------------------------------------------------------
# Step 2.5: Base runtime tools (Linux containers) — jq, unzip, python3-pip
# ----------------------------------------------------------
# DEFECT (v14.1.3): a FRESH Contabo / Debian Bookworm OpenClaw container ships
# node, npm, python3, git, curl — but NOT `jq`, NOT `unzip`, and often NOT
# `python3-pip` (no `pip`/`pip3` and no `python3 -m pip`). The installer relies
# on all three downstream:
#   • unzip  — Step 4 extraction fallback (python3 zipfile now covers the gap,
#              but unzip is faster and is the preferred Linux path)
#   • jq     — cron-UUID capture + state-file writes (Steps 13.5/13.5b)
#   • pip    — Gemini engine deps + presentation pipeline (reportlab/python-pptx)
# Without them, a fresh container hit "unzip: command not found" / silent jq
# no-ops / pip failures. We install them ONCE here, OS-aware, BEFORE the
# download+extract step. NON-FATAL: missing apt or a failed install only warns
# (python3 zipfile + `command -v jq` guards cover the absence downstream).
#
# Hostinger note: /usr/local/bin/apt-get is a Linuxbrew SHIM on those images
# (INSTALL-GOTCHAS); /usr/bin/apt-get is the genuine dpkg-backed apt. We resolve
# the real apt the same way Step 6.5 does. Mac: nothing to do — Homebrew + the
# macOS base already provide unzip/ditto; jq/pip are handled by their own steps.
if [ "$OC_PLATFORM" = "vps" ] || { [ -z "${OC_PLATFORM:-}" ] && [ "$(uname -s 2>/dev/null)" = "Linux" ]; }; then
    step "Step 2.5: Installing base runtime tools (jq, unzip, python3-pip) — Linux"
    _BASE_APT="/usr/bin/apt-get"
    [ -x "$_BASE_APT" ] || _BASE_APT="$(command -v apt-get 2>/dev/null || true)"
    _need_base=""
    command -v jq    >/dev/null 2>&1 || _need_base="${_need_base}jq "
    command -v unzip >/dev/null 2>&1 || _need_base="${_need_base}unzip "
    # pip presence = either a pip3/pip binary OR `python3 -m pip` importable.
    if ! command -v pip3 >/dev/null 2>&1 && ! command -v pip >/dev/null 2>&1 \
         && ! python3 -m pip --version >/dev/null 2>&1; then
        _need_base="${_need_base}python3-pip "
    fi
    if [ -z "$_need_base" ]; then
        success "Base runtime tools already present (jq, unzip, pip)"
    elif [ -n "$_BASE_APT" ] && [ -x "$_BASE_APT" ]; then
        note "Installing missing base tools via real apt ($_BASE_APT): $_need_base"
        # -o DPkg::Lock::Timeout=60: if another process holds the dpkg/apt lock
        # (e.g. an unattended-upgrades run on a fresh Contabo/Debian container),
        # wait up to 60s then fail-fast instead of hanging the whole installer.
        # shellcheck disable=SC2086
        ( "$_BASE_APT" -o DPkg::Lock::Timeout=60 update -y \
          && DEBIAN_FRONTEND=noninteractive "$_BASE_APT" -o DPkg::Lock::Timeout=60 install -y --no-install-recommends $_need_base ) \
            >> "$LOG_FILE" 2>&1 \
            && success "Base runtime tools installed: $_need_base" \
            || warn "apt install of base tools ($_need_base) failed — downstream guards (python3 zipfile / command -v jq) will cover the gap. Manual: $_BASE_APT install -y $_need_base"
    else
        warn "No usable apt-get found on Linux — could not auto-install base tools ($_need_base). Downstream guards cover the gap, but install jq/unzip/python3-pip manually for full functionality."
    fi
fi

# ----------------------------------------------------------
# Step 3: Download Package
# ----------------------------------------------------------
step "Step 3: Downloading Onboarding Package"

SKILLS_DIR=$(discover_skills_dir)
export SKILLS_DIR

note "Source: $ONBOARDING_DIR"
note "Destination: $SKILLS_DIR/"

TEMP_ZIP="/tmp/openclaw-onboarding-pkg.zip"
TEMP_EXTRACT="/tmp/openclaw-onboarding-extract"

curl -fSL --progress-bar "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
if [ ! -f "$TEMP_ZIP" ]; then
    error "Failed to download onboarding package"
    send_telegram_progress "ERROR: Download failed. Install aborted."
    exit 1
fi

success "Downloaded to $TEMP_ZIP"
send_telegram_progress "Downloaded onboarding package ${ONBOARDING_VERSION}"

# ----------------------------------------------------------
# Step 4: Extract Package
# ----------------------------------------------------------
step "Step 4: Extracting Package"

rm -rf "$TEMP_EXTRACT"
mkdir -p "$TEMP_EXTRACT"

# OS-AWARE EXTRACTION (v14.1.3).
# Mac (`ditto`): v10.13.2 switched from `unzip` to `ditto -x -k` — Mac's native
# extractor. Info-ZIP's `unzip` mangles UTF-8 filenames (em-dashes etc.),
# partial-writes the bad file, then prompts "Continue? (y/n/^C)" — which hangs
# install.sh forever when the operator isn't watching. `ditto` is UTF-8 clean
# and silent, so it stays the PREFERRED Mac path.
# Linux (Hostinger/Contabo): `ditto` does NOT exist (it's a macOS tool). A fresh
# Contabo Debian Bookworm container also ships WITHOUT `unzip` (INSTALL-GOTCHAS
# #1). The previous code fell through `ditto`→`unzip` and, if `unzip` was also
# absent, silently produced no extract dir → "Unexpected archive structure"
# abort (this broke a client's Contabo onboarding). FIX: branch on $OC_PLATFORM,
# and on Linux fall back to `python3` zipfile — python3 is ALWAYS present (the
# platform bootstrap hard-requires it). All three methods are tested-equivalent
# for the GitHub-archive zip we download.
_extract_zip() {
    # $1 = zip, $2 = dest dir. Returns 0 on success.
    if [ "$OC_PLATFORM" = "mac" ] && command -v ditto >/dev/null 2>&1; then
        ditto -x -k "$1" "$2" 2>/dev/null && return 0
        warn "ditto extraction failed; falling back to unzip/python3"
    fi
    # Linux + Mac fallback chain: unzip (non-interactive, auto-skip conflicts)
    # then python3 zipfile (always available; the INSTALL-GOTCHAS #1 fallback).
    if command -v unzip >/dev/null 2>&1; then
        yes n 2>/dev/null | unzip -qn "$1" -d "$2" 2>/dev/null && return 0
        warn "unzip extraction failed; falling back to python3 zipfile"
    fi
    note "Extracting via python3 zipfile (unzip not available — normal on fresh Linux containers)"
    SRC_ZIP="$1" DEST_DIR="$2" python3 - <<'PYEOF' 2>/dev/null && return 0
import os, zipfile
with zipfile.ZipFile(os.environ["SRC_ZIP"]) as z:
    z.extractall(os.environ["DEST_DIR"])
PYEOF
    return 1
}
_extract_zip "$TEMP_ZIP" "$TEMP_EXTRACT" || warn "All extraction methods failed — the structure check below will catch it."

if [ ! -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
    error "Unexpected archive structure"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    send_telegram_progress "ERROR: Extract failed. Archive structure unexpected."
    exit 1
fi

cp -r "$TEMP_EXTRACT/openclaw-onboarding-main/"* "$ONBOARDING_DIR/"
rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"

success "Extracted to $ONBOARDING_DIR"

SKILL_COUNT=$(discover_skills "$ONBOARDING_DIR")
success "Skills found: $SKILL_COUNT"
send_telegram_progress "📦 Extracted onboarding package. ${SKILL_COUNT} skills detected. Installing them now (this takes about 1-2 minutes)…"

# ----------------------------------------------------------
# Step 5: Install Skills
# ----------------------------------------------------------
step "Step 5: Installing Skills"

mkdir -p "$SKILLS_DIR"

for SKILL_DIR in "$ONBOARDING_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    
    SKILL_NAME=$(basename "$SKILL_DIR")
    
    # Skip archived skills
    case "$SKILL_NAME" in
        *ARCHIVED*) note "Skipped (archived): $SKILL_NAME"; continue ;;
    esac
    
    mkdir -p "$SKILLS_DIR/$SKILL_NAME"
    
    for ITEM in "$SKILL_DIR"/*; do
        ITEM_NAME=$(basename "$ITEM")
        case "$ITEM_NAME" in
            AGENTS.md|MEMORY.md|SOUL.md|USER.md|IDENTITY.md|HEARTBEAT.md|TOOLS.md)
                # Skip core .md files - handled surgically
                ;;
            *)
                if [ -d "$ITEM" ]; then
                    cp -r "$ITEM" "$SKILLS_DIR/$SKILL_NAME/"
                else
                    cp "$ITEM" "$SKILLS_DIR/$SKILL_NAME/"
                fi
                ;;
        esac
    done
    
    add_to_list "installed" "$SKILL_NAME"
    SKILL_COUNT=$((SKILL_COUNT + 1))
done

success "$SKILL_COUNT skills installed"

# Step 5b (v12.0.0): Per-skill prerequisite check -- non-blocking.
# For each installed skill that has a PREREQS.json, check prerequisites.
# Exit 2 = installed-with-missing-prereqs (informational, never a failure).
# Exit 3 = malformed PREREQS.json (warn and continue).
# Self-records into .onboarding-state.json missingPrereqs/prereqCheckedAt.
PREREQ_CHECKER="$SKILLS_DIR/shared-utils/check-skill-prereqs.sh"
if [[ -x "$PREREQ_CHECKER" ]]; then
  note "Running prerequisite checks for installed skills (non-blocking)..."
  for SKILL_DIR_CHECK in "$SKILLS_DIR"/[0-9]*/; do
    [[ -d "$SKILL_DIR_CHECK" ]] || continue
    SKILL_NAME_CHECK="$(basename "$SKILL_DIR_CHECK")"
    [[ -f "$SKILL_DIR_CHECK/PREREQS.json" ]] || continue
    PREREQ_RC=0
    bash "$PREREQ_CHECKER" "$SKILL_DIR_CHECK" || PREREQ_RC=$?
    if [[ $PREREQ_RC -eq 2 ]]; then
      note "Skill $SKILL_NAME_CHECK: installed with missing prerequisites (see MISSING-PREREQUISITES.md)"
    elif [[ $PREREQ_RC -eq 3 ]]; then
      warn "Skill $SKILL_NAME_CHECK: malformed PREREQS.json (skipped)"
    fi
  done
fi

# v10.13.9: STOP creating ~/clawd. Clawd is dead — OpenClaw replaced it.
# Previous behavior (mkdir -p ~/clawd) was actively spreading the legacy
# path even on fresh installs, causing the agent to read from one place
# and install.sh to write to another. Now we ENSURE ~/.openclaw/workspace
# (the canonical OpenClaw default) exists instead.
mkdir -p "$OC_WORKSPACE_DEFAULT" 2>/dev/null && note "Ensured OpenClaw workspace exists: $OC_WORKSPACE_DEFAULT"

# Copy root files (v10.13.0: added AGENTS.md, INSTALL-CONTRACT.md,
# ONBOARDING-TRIGGERS.md, direct-to-agent-install.md so the workspace
# has CEO_DEFERRAL + N1-N27 + N22 semantics on a fresh install).
for ROOT_FILE in \
    "Start Here.md" \
    README.md \
    CHANGELOG.md \
    version \
    AGENTS.md \
    INSTALL-CONTRACT.md \
    ONBOARDING-TRIGGERS.md \
    direct-to-agent-install.md; do
    if [ -f "$ONBOARDING_DIR/$ROOT_FILE" ]; then
        cp "$ONBOARDING_DIR/$ROOT_FILE" "$SKILLS_DIR/../"
    fi
done

# v10.10.0 P0-007: Trigger agent execution of Start Here.md, not just copy.
# The bash install.sh has done its bootstrap. The actual onboarding work
# (read 52 skills, wave-install, run interview, build ZHC, etc.) is the
# agent's job — driven by Start Here.md. We've copied the file; we now
# need to MAKE SURE the agent reads it. Three independent channels (the
# triple-fire in fire_install_kickoff_triplet at end of install.sh) all
# include a direct instruction: "Read $SKILLS_DIR/../Start Here.md end to
# end." This block ensures the file at that path has the same content the
# triple-fire instructs the agent to read.
START_HERE_LANDED="$SKILLS_DIR/../Start Here.md"
if [ -f "$START_HERE_LANDED" ]; then
    success "Start Here.md placed at $START_HERE_LANDED — agent will be instructed to execute it via the triple-fire trigger at install.sh end"
else
    warn "Start Here.md NOT found at expected path $START_HERE_LANDED — agent dispatch may fail"
fi

# Copy scripts folder
if [ -d "$ONBOARDING_DIR/scripts" ]; then
    cp -r "$ONBOARDING_DIR/scripts" "$SKILLS_DIR/../"
fi

# v10.5.1: Install shared-utils to skills root for v2.1 helper imports
if [ -d "$ONBOARDING_DIR/shared-utils" ]; then
    mkdir -p "$SKILLS_DIR/shared-utils"
    cp -r "$ONBOARDING_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"
    chmod +x "$SKILLS_DIR/shared-utils/"*.sh 2>/dev/null || true
    chmod +x "$SKILLS_DIR/shared-utils/"*.py 2>/dev/null || true
    success "shared-utils installed to $SKILLS_DIR/shared-utils"
fi

# v14.24.0: Install universal-sops/ SOP cluster (Skills 47/48 source tree).
# Neither install nor update previously delivered this directory; Skills 47/48
# wiring FAILed with a FATAL looking for funnel/presentation/video/ad SOPs.
if [ -d "$ONBOARDING_DIR/universal-sops" ]; then
    mkdir -p "$SKILLS_DIR/universal-sops"
    cp -r "$ONBOARDING_DIR/universal-sops/." "$SKILLS_DIR/universal-sops/"
    success "universal-sops installed to $SKILLS_DIR/universal-sops"
fi

# v0.2.0 (AC-14): Wire Social Media in a Box (Skill 57). Idempotent + non-fatal —
# ensures the shared universal-sops/social-media-craft/ SOP cluster + the 57
# engine tree are present under the skills root (belt-and-suspenders atop the
# wholesale copies above). Cron registration is deliberately left to the operator
# via `scripts/wire-social-media.sh --apply` (the engine's registrar dedups). A
# wiring hiccup must NEVER abort the install.
if [ -f "$ONBOARDING_DIR/scripts/wire-social-media.sh" ]; then
    if ONBOARDING_DIR="$ONBOARDING_DIR" SKILLS_DIR="$SKILLS_DIR" \
        bash "$ONBOARDING_DIR/scripts/wire-social-media.sh" >/dev/null 2>&1; then
        success "Social Media in a Box (Skill 57) wired (social-media-craft + engine)"
    else
        warn "Social Media in a Box wiring reported an issue (non-fatal); run scripts/wire-social-media.sh --apply manually"
    fi
fi
send_telegram_progress "✓ Skills + helpers installed. Setting up your AI engines next…"

# ----------------------------------------------------------
# Step 6: Install Gemini Scripts
# ----------------------------------------------------------
step "Step 6: Installing Gemini Engine Scripts"

# v10.13.9: Gemini engine scripts go to ~/.openclaw/scripts, not ~/clawd/scripts.
# Clawd is dead — installing to that path means the agent (which reads from
# the OpenClaw config root) can't find them.
SCRIPTS_DIR="$OC_CONFIG/scripts"
mkdir -p "$SCRIPTS_DIR"

for SCRIPT in gemini-indexer.py gemini-search.py; do
    if [ -f "$ONBOARDING_DIR/scripts/$SCRIPT" ]; then
        cp "$ONBOARDING_DIR/scripts/$SCRIPT" "$SCRIPTS_DIR/"
        chmod +x "$SCRIPTS_DIR/$SCRIPT"
        success "Installed: $SCRIPT"
    fi
done

# ----------------------------------------------------------
# Step 6b: Provision the prebuilt persona index (gemini-index.sqlite)
# ----------------------------------------------------------
# WHY: Step 6 above only copies the indexer/search SCRIPTS. Without the actual
# vector DB present, gemini-search.py silently degrades to keyword matching and
# the canonical personas (54 as of v2.1.0) are unselectable. We download the
# canonical prebuilt 54-persona section-tagged index from the GitHub Release
# named in the SHARED MANIFEST (single source of truth:
# shared-utils/prebuilt-index/INDEX-MANIFEST.json), verify its sha256 BEFORE
# decompressing, and install it into place — ONLY when absent or stale.
#
# Idempotency / furnace-kill: the shared helper (provision-persona-index.sh)
# skips download if BOTH (a) section_number + mode columns are present AND
# (b) .prebuilt-index-version sentinel == manifest release_tag. This means the
# live operator coaching index (already section-tagged at v2.1.0) is NEVER
# clobbered or rebuilt by install/update.
#
# sha256 is a HARD gate: a corrupt asset is never installed (box keyword-degrades
# and warns instead, which the agent surfaces).
PERSONA_INDEX_MANIFEST="$ONBOARDING_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
COACHING_DB_DIR="$OC_WORKSPACE/data/coaching-personas"

step "Step 6b: Provisioning prebuilt persona index (canonical 54, section-tagged)"
_PROVISION_HELPER="$ONBOARDING_DIR/shared-utils/provision-persona-index.sh"
[ -f "$_PROVISION_HELPER" ] || _PROVISION_HELPER="$SKILLS_DIR/shared-utils/provision-persona-index.sh"
if [ -f "$_PROVISION_HELPER" ]; then
    # shellcheck source=/dev/null
    source "$_PROVISION_HELPER"
    # v14.27.2: reconcile the canonical persona-categories.json + 54
    # persona-blueprint.md into the workspace BEFORE the index gate runs, so the
    # persona-dir count is 54 by gate time (furnace-safe) and drifted boxes
    # (40/54) converge to the canonical 54.
    reconcile_persona_assets "$SKILLS_DIR/22-book-to-persona-coaching-leadership-system" "$COACHING_DB_DIR" "$OC_WORKSPACE"
    provision_persona_index "$PERSONA_INDEX_MANIFEST" "$COACHING_DB_DIR"
    # FIX 1 (BREAK 1): pipeline OWNS the qmd persona store — repoint/re-index it
    # at the canonical personas dir (BM25 only, furnace-safe) so the agent can
    # never read a frozen "March" cache. Both-paths parity with update-skills.sh.
    reconcile_qmd_persona_index "$COACHING_DB_DIR"
    # FIX 4 (cascade): on a fresh install the SET is always "new" (_SET_CHANGED=1),
    # so re-wire governing-personas.md + bust stickiness. Static/idempotent; the
    # full workforce build also authors these, so this is belt-and-suspenders.
    if [ "${_SET_CHANGED:-0}" = "1" ]; then
        rewire_on_persona_set_change "$SKILLS_DIR" "$OC_WORKSPACE"
    fi
else
    warn "provision-persona-index.sh not found — skipping prebuilt index provisioning (additive)"
fi
# P11-1: belt-and-suspenders QC-visible surfacing. provision-persona-index.sh's
# own skip paths already print a "  ⚠️  " line (matching warn()'s own output),
# which print_install_summary() picks up automatically since this whole
# script's stdout is tee'd to $LOG_FILE — but decouple the completion report
# from that internal formatting detail by also re-asserting through warn()
# itself here, keyed off the exported _PIDX_SKIP_WARNINGS accumulator.
if [ -n "${_PIDX_SKIP_WARNINGS:-}" ]; then
    warn "Persona-index provisioning had skip warnings: $_PIDX_SKIP_WARNINGS"
fi

# Step 6b-catalog: Wire GHL funnel catalog path vars (GHL_FUNNEL_CATALOG + GHL_FUNNEL_INDEX)
# so Skill 06 and agents can resolve funnel templates without hardcoding paths.
if [ -f "$_PROVISION_HELPER" ]; then
    wire_ghl_funnel_catalog "$SKILLS_DIR" "$OC_SECRETS_ENV" "$OC_JSON"
fi

# EMBEDDING-PREVENTION BUNDLE (items 4-7): persist the memory-health cron scripts
# to ~/.openclaw/scripts (or /data/.openclaw/scripts) so ensure-pipeline-crons.sh
# can resolve them on EVERY box, and so the registered crons survive a temp-clone
# cleanup. ensure-pipeline-crons.sh wires them into cron fleet-wide (end of run).
for SCRIPT in index-model-drift-check.sh orphan-temp-sweep.sh disk-usage-alert.sh pre-july14-embedding-migration-check.sh ensure-pipeline-crons.sh agent-browser-reaper.sh; do
    if [ -f "$ONBOARDING_DIR/scripts/$SCRIPT" ]; then
        cp -f "$ONBOARDING_DIR/scripts/$SCRIPT" "$SCRIPTS_DIR/"
        chmod +x "$SCRIPTS_DIR/$SCRIPT"
        success "Installed memory-health cron script: $SCRIPT"
    fi
done

# LOOP / FURNACE PROTECTION activation helper + operator canary (Skill 60 EWS +
# Skill 61 Loop Protection). Persisted to ~/.openclaw/scripts (or /data/...) so
# the end-of-run activation step and the operator canary can resolve them after a
# temp-clone cleanup, and so the updater's shared hook has one canonical copy (no
# copy-paste drift). Neither ARMS a box; client activation is gated HELD by
# default (61-loop-protection-system/config/rollout.json). See Topic 2 §2.3.
for SCRIPT in activate-loop-protection.sh loop-protection-canary.sh; do
    if [ -f "$ONBOARDING_DIR/scripts/$SCRIPT" ]; then
        cp -f "$ONBOARDING_DIR/scripts/$SCRIPT" "$SCRIPTS_DIR/"
        chmod +x "$SCRIPTS_DIR/$SCRIPT"
        success "Installed loop-protection script: $SCRIPT"
    fi
done

# SINGLETON POOLED BROWSER backstop: ensure ~/.agent-browser exists (mode 700),
# make the Skill-06 gateway + reaper executable, then ONE-SHOT reap any
# pre-existing orphan agent-browser sessions/descriptors on first contact (the
# HOURLY reaper cron is wired by ensure-pipeline-crons.sh at end of install, as a
# SILENT command-kind job — v14.1.1 throttled it */10->hourly). Pure additive,
# env-default-gated, runs as the box user (NEVER root).
mkdir -p "$HOME/.agent-browser" 2>/dev/null || true
chmod 700 "$HOME/.agent-browser" 2>/dev/null || true
_BM_GW="$ONBOARDING_DIR/skills/06-ghl-install-pages/tools/browser_manager.sh"
[ -f "$_BM_GW" ] || _BM_GW="$ONBOARDING_DIR/06-ghl-install-pages/tools/browser_manager.sh"
[ -f "$_BM_GW" ] && chmod +x "$_BM_GW" 2>/dev/null || true
if [ -f "$SCRIPTS_DIR/agent-browser-reaper.sh" ]; then
    chmod +x "$SCRIPTS_DIR/agent-browser-reaper.sh" 2>/dev/null || true
    note "One-shot agent-browser reap (clears any pre-existing orphans on first contact)"
    bash "$SCRIPTS_DIR/agent-browser-reaper.sh" 2>/dev/null || warn "one-shot agent-browser reap rc!=0 (non-fatal; the hourly cron backfills)"
fi

# SINGLETON POOLED BROWSER advisory config — REMOVED + SELF-HEAL (v14.1.3),
# plus HEADED SCRUB (v14.1.4): also strips any truthy `headed` key anywhere in
# openclaw.json (browser.*.headed / {"headed":true}) so a leftover/inherited
# headed config can never override the box-level AGENT_BROWSER_HEADED=false pin.
# DEFECT: the old block deep-merged a `browser.agentBrowser` object into
# openclaw.json. OpenClaw 2026.6.8 tightened the config schema to strict
# additionalProperties:false (same mechanism that rejected the root
# `extension_registry` key and `agents.defaults.tools.*` — see CHANGELOG
# v13.1.3 / register-routing-dept.py fix). `browser.agentBrowser` is an
# UNKNOWN sub-key under the `browser` object, so on a fresh 2026.6.8 container
# the gateway refuses to start → CRASH-LOOP (this took a client's Contabo box
# down). The block's own comment admitted it was ADVISORY-ONLY: agent-browser
# ignores it natively; the REAL session/process caps live in browser_manager.sh
# + agent-browser-reaper.sh (env-overridable). So writing it gained nothing and
# cost a crash-loop. We now: (1) never write the key, and (2) SELF-HEAL — strip
# any pre-existing `browser.agentBrowser` left by an older installer, via a
# safe, backed-up, atomic JSON round-trip, so an already-poisoned box repairs
# itself on the next install/update run. OS-portable (python3 only; runs on Mac
# + Linux identically). Non-fatal: any failure just warns.
if [ -f "$OC_JSON" ]; then
    # The python block prints STRIPPED (a legacy key was actually removed) or
    # NOOP (no legacy key present) to stdout, exiting 1 only on a JSON read
    # failure. The shell branches on that token so the log message reflects what
    # really happened — the no-op case no longer falsely claims it "stripped" a key.
    _BROWSER_HEAL_OUT="$(OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os, shutil
p = os.environ["OC_JSON"]
try:
    d = json.load(open(p))
except Exception:
    raise SystemExit(1)

changed = []

# (a) Legacy poison key: browser.agentBrowser (crashed strict 2026.6.8 schema).
browser = d.get("browser")
if isinstance(browser, dict) and "agentBrowser" in browser:
    del browser["agentBrowser"]
    changed.append("browser.agentBrowser")
    # Drop an emptied browser object too, so we don't leave {} noise.
    if not browser:
        d.pop("browser", None)

# (b) HEADED SCRUB (v14.1.4): ANY truthy "headed" key anywhere in openclaw.json
#     (top-level, browser.headed, browser.<sub>.headed, …) would silently force a
#     VISIBLE window and OVERRIDE the box-level AGENT_BROWSER_HEADED=false pin.
#     Remove every truthy "headed" so the headless default + the env pin govern.
#     A benign "headed": false is left untouched (already headless, no churn).
def _truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(v, (int, float)):
        return v != 0
    return False

def _scrub(node, path):
    if isinstance(node, dict):
        if "headed" in node and _truthy(node.get("headed")):
            del node["headed"]
            changed.append((path + ".headed").lstrip("."))
        for k, v in list(node.items()):
            _scrub(v, path + "." + k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scrub(v, path + "[" + str(i) + "]")

_scrub(d, "")

if changed:
    # Back up once, strip, atomic-replace.
    shutil.copy2(p, p + ".prebrowserheal.bak")
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, p)
    print("STRIPPED:" + ",".join(changed))
else:
    print("NOOP")
PYEOF
)"
    case "$_BROWSER_HEAL_OUT" in
        STRIPPED:*)
            success "browser config self-heal: stripped ${_BROWSER_HEAL_OUT#STRIPPED:} (legacy agentBrowser and/or any truthy 'headed' removed — headless is now governed by the box-level AGENT_BROWSER_HEADED=false pin)"
            ;;
        NOOP)
            success "browser config self-heal: clean (no legacy agentBrowser key, no truthy 'headed' — headless governed by the box-level pin)"
            ;;
        *)
            warn "browser config self-heal skipped (non-fatal; manager+reaper+env pin still force headless)"
            ;;
    esac
    unset _BROWSER_HEAL_OUT
fi

# Install google-genai if needed.
# v14.1.3: use `python3 -m pip` (portable) instead of the bare `pip3` binary.
# On a fresh Linux container python3-pip may be installed as a module with NO
# `pip3` on PATH, so `pip3 install` would be "command not found". `python3 -m pip`
# also guarantees the package lands in the SAME interpreter the import check uses.
if ! python3 -c "import google.genai" 2>/dev/null; then
    note "Installing google-genai package..."
    python3 -m pip install google-genai --break-system-packages 2>/dev/null || \
        python3 -m pip install google-genai 2>/dev/null || \
        warn "google-genai install failed - manual install required"
else
    success "google-genai already installed"
fi

# ----------------------------------------------------------
# v6.6.0 / Step 6.4: Skill 22 Python pipeline dependencies (Mac)
# ----------------------------------------------------------
# Install pdfplumber, pypdf, ebooklib, mobi, beautifulsoup4, aiohttp, numpy.
# Each verified individually; failures LOUDLY warn (not silently swallowed).
# Mac install order: uv → pip3 --break-system-packages → pip3 → pipx fallback.
# ────────────────────────────────────────────────────────────────────────────

step "Step 6.4: Installing Skill 22 Python pipeline dependencies (Mac)"

_install_py_pkg_mac() {
    local pkg="$1"
    local import="$2"
    local display="${3:-$pkg}"

    if python3 -c "import $import" 2>/dev/null; then
        success "$display already installed"
        return 0
    fi
    note "Installing $display..."

    # Attempt 1: uv pip install
    if command -v uv >/dev/null 2>&1; then
        if uv pip install "$pkg" >> "$LOG_FILE" 2>&1; then
            if python3 -c "import $import" 2>/dev/null; then
                success "$display installed via uv"
                return 0
            fi
        fi
    fi

    # Attempt 2: pip --break-system-packages (macOS 13+ externally-managed python).
    # v14.1.3: `python3 -m pip` instead of bare `pip3` — portable. Resolves to the
    # SAME pip on Mac, and works on a fresh Linux container where pip is installed
    # as a module with no `pip3` binary on PATH (this helper now also runs Skill 22
    # deps on VPS, where bare `pip3` would have been "command not found").
    if python3 -m pip install --user "$pkg" --break-system-packages >> "$LOG_FILE" 2>&1; then
        if python3 -c "import $import" 2>/dev/null; then
            success "$display installed via pip --break-system-packages"
            return 0
        fi
    fi

    # Attempt 3: pip without the flag (older pip that lacks --break-system-packages)
    if python3 -m pip install --user "$pkg" >> "$LOG_FILE" 2>&1; then
        if python3 -c "import $import" 2>/dev/null; then
            success "$display installed via pip"
            return 0
        fi
    fi

    warn "WARN: $display installation failed after all attempts."
    warn "      Skill 22 book extraction may fail for formats requiring $display."
    warn "      Manual fix: python3 -m pip install --user $pkg --break-system-packages"
    return 1
}

_install_py_pkg_mac "pdfplumber"     "pdfplumber"  "pdfplumber (PDF extraction primary)"
_install_py_pkg_mac "pypdf"          "pypdf"       "pypdf (PDF extraction fallback)"
_install_py_pkg_mac "ebooklib"       "ebooklib"    "ebooklib (EPUB extraction)"
_install_py_pkg_mac "lxml"           "lxml"        "lxml (XML/HTML parser)"
_install_py_pkg_mac "mobi"           "mobi"        "mobi (MOBI Python extractor)"
_install_py_pkg_mac "beautifulsoup4" "bs4"         "beautifulsoup4 (HTML parser)"
_install_py_pkg_mac "aiohttp"        "aiohttp"     "aiohttp (async HTTP client)"
_install_py_pkg_mac "numpy"          "numpy"       "numpy (embeddings math)"

_s22_deps_ok_mac=true
for _dep_check in "pdfplumber" "pypdf" "ebooklib" "bs4" "aiohttp" "numpy"; do
    if ! python3 -c "import $_dep_check" 2>/dev/null; then
        warn "  MISSING after install attempts: $_dep_check"
        _s22_deps_ok_mac=false
    fi
done
if [ "$_s22_deps_ok_mac" = "true" ]; then
    success "All Skill 22 Python deps verified (pdfplumber, pypdf, ebooklib, mobi, bs4, aiohttp, numpy)"
else
    warn "One or more Skill 22 Python deps are missing. See $LOG_FILE for details."
fi

# ----------------------------------------------------------
# Step 6.5: Presentation pipeline runtime dependencies
# ----------------------------------------------------------
# Skill 23 (AI Workforce Blueprint) includes a presentation pipeline that needs:
#   • reportlab       — presenter-guide PDF renderer (presenters_speech_pdf.py)
#   • python-pptx     — PPTX deck assembly (build_deck.py)
#   • poppler/pdftoppm — PDF→PNG page extraction for Phase-6 QC
#   • LibreOffice/soffice — PPTX→PDF export (PPTX Assembly Specialist, SOP 9.2)
#
# Platform branches:
#   Mac  — Python deps via _install_py_pkg_mac; poppler via formula; LibreOffice
#          via NONINTERACTIVE cask (no sudo hang); symlink on PATH.
#   VPS  — System packages (libreoffice-impress, poppler-utils) via the REAL
#          Debian apt at /usr/bin/apt-get — NOT the Linuxbrew shim at
#          /usr/local/bin/apt-get (INSTALL-GOTCHAS.md: apt/apt-get redirect to
#          brew on these images). Python deps (reportlab, python-pptx) via pip
#          --break-system-packages into the SAME python3 that build_deck.py runs.
#          NOTE — VPS DURABILITY: the upstream Docker image is external and cannot
#          be edited from this repo, so neither the apt packages nor the pip deps
#          live in a layer that survives `docker compose up --force-recreate`
#          (only the /data bind-mount persists). We therefore RE-ASSERT all four
#          deps EVENT-shaped on the GATE-1 deps-missing path
#          (presentation-canonical-entry.sh) plus a DAILY backstop via the OpenClaw
#          scheduler (`openclaw cron create`, "0 4 * * *"; FIX-PRES-09(iv) retired
#          the old */15 furnace), which is the same durable recurring-task
#          mechanism every other VPS cron in this installer uses — its definition
#          lives in the gateway config on /data and the gateway (PID 1) re-loads it
#          on each container start, then fires it on the schedule. There is NO cron
#          daemon in the container, so a system @reboot crontab would NOT fire;
#          that approach was removed.
#
# The Capacity & Reliability Engineer (capacity-reliability-engineer.md §11) verifies
# all four at Phase-0.5. The qc-completeness.sh gate (install step 6b) hard-fails
# (command -v soffice / command -v pdftoppm / python3 -c "import reportlab, pptx")
# if any dep is missing at the time the operator declares install complete.
# ────────────────────────────────────────────────────────────────────────────

step "Step 6.5: Installing presentation pipeline runtime dependencies (reportlab, python-pptx, poppler, LibreOffice)"

if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
    # ── VPS ARM ──────────────────────────────────────────────────────────────
    # Resolve the REAL Debian apt-get (NOT the Linuxbrew shim). On these images
    # /usr/local/bin/apt-get redirects to brew (INSTALL-GOTCHAS.md), which cannot
    # install libreoffice-impress / poppler-utils. /usr/bin/apt-get is the genuine
    # dpkg-backed apt. We also resolve the python3 that build_deck.py will run so
    # reportlab/python-pptx land in the interpreter that actually imports them.
    _APT_GET="/usr/bin/apt-get"
    _PY3="$(command -v python3 || echo /usr/bin/python3)"
    note "VPS: using real Debian apt at $_APT_GET and python3 at $_PY3"

    # Write the reassert script FIRST so the install path and the cron path run
    # IDENTICAL logic (the install below simply invokes it once).
    _VPS_REASSERT_SCRIPT="/data/.openclaw/scripts/reassert-presentation-deps.sh"
    mkdir -p /data/.openclaw/scripts /data/.openclaw/logs
    cat > "$_VPS_REASSERT_SCRIPT" << 'REASSERT_EOF'
#!/usr/bin/env bash
# reassert-presentation-deps.sh — (re)installs the four presentation-pipeline deps
# on a VPS container. The upstream Docker image is external and cannot be edited
# from this repo, so apt packages (libreoffice-impress, poppler-utils) and pip
# deps (reportlab, python-pptx) do NOT survive `docker compose up --force-recreate`
# (only the /data bind-mount persists). This script is invoked once by install.sh
# Step 6.5 AND re-fired on a schedule by the OpenClaw scheduler cron
# "reassert-presentation-deps" so the deps are re-installed per container start.
# Idempotent — safe to re-run. Installed by install.sh Step 6.5. DO NOT EDIT.
set -uo pipefail
LOG=/data/.openclaw/logs/reassert-presentation-deps.log
mkdir -p "$(dirname "$LOG")"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "[$(ts)] reassert-presentation-deps starting" >> "$LOG"

# Real Debian apt (NOT the /usr/local/bin brew shim).
APT_GET="/usr/bin/apt-get"
PY3="$(command -v python3 || echo /usr/bin/python3)"

# --- System packages: libreoffice-impress (provides soffice) + poppler-utils (pdftoppm)
if [ -x "$APT_GET" ]; then
    if ! command -v soffice >/dev/null 2>&1 || ! command -v pdftoppm >/dev/null 2>&1; then
        echo "[$(ts)] apt-get update + install libreoffice-impress poppler-utils" >> "$LOG"
        ( "$APT_GET" update -y && \
          DEBIAN_FRONTEND=noninteractive "$APT_GET" install -y --no-install-recommends \
              libreoffice-impress poppler-utils ) >> "$LOG" 2>&1 \
            && echo "[$(ts)] apt packages OK" >> "$LOG" \
            || echo "[$(ts)] WARN: apt install failed (see above)" >> "$LOG"
    else
        echo "[$(ts)] soffice + pdftoppm already present — apt install skipped" >> "$LOG"
    fi
else
    echo "[$(ts)] WARN: real apt-get not found at $APT_GET — cannot install soffice/pdftoppm" >> "$LOG"
fi

# --- Python deps into the SAME interpreter build_deck.py runs.
"$PY3" -m pip install --break-system-packages --quiet reportlab >> "$LOG" 2>&1 \
    && echo "[$(ts)] reportlab OK" >> "$LOG" \
    || echo "[$(ts)] WARN: reportlab install failed" >> "$LOG"
"$PY3" -m pip install --break-system-packages --quiet python-pptx >> "$LOG" 2>&1 \
    && echo "[$(ts)] python-pptx OK" >> "$LOG" \
    || echo "[$(ts)] WARN: python-pptx install failed" >> "$LOG"

# --- Verify (same checks qc-completeness.sh hard-fails on).
command -v soffice  >/dev/null 2>&1 && echo "[$(ts)] verify soffice OK"  >> "$LOG" || echo "[$(ts)] WARN: soffice missing"  >> "$LOG"
command -v pdftoppm >/dev/null 2>&1 && echo "[$(ts)] verify pdftoppm OK" >> "$LOG" || echo "[$(ts)] WARN: pdftoppm missing" >> "$LOG"
"$PY3" -c "import reportlab, pptx" >/dev/null 2>&1 && echo "[$(ts)] verify reportlab+pptx OK" >> "$LOG" || echo "[$(ts)] WARN: reportlab/pptx import failed" >> "$LOG"

echo "[$(ts)] reassert-presentation-deps done" >> "$LOG"
REASSERT_EOF
    chmod +x "$_VPS_REASSERT_SCRIPT"

    # Run the reassert script ONCE now to install all four deps for this container.
    note "VPS: installing all four presentation deps via $_VPS_REASSERT_SCRIPT ..."
    bash "$_VPS_REASSERT_SCRIPT" >> "$LOG_FILE" 2>&1 || true

    # Report per-dep result (read the verifier-equivalent checks directly).
    command -v soffice  >/dev/null 2>&1 \
        && success "soffice (libreoffice-impress) on PATH: $(soffice --version 2>&1 | head -1 || true)" \
        || warn "soffice NOT on PATH after install — PPTX→PDF export will fail. Manual fix: $_APT_GET update && DEBIAN_FRONTEND=noninteractive $_APT_GET install -y libreoffice-impress"
    command -v pdftoppm >/dev/null 2>&1 \
        && success "pdftoppm (poppler-utils) on PATH" \
        || warn "pdftoppm NOT on PATH after install — Phase-6 QC PNG extraction will fail. Manual fix: $_APT_GET install -y poppler-utils"
    "$_PY3" -c "import reportlab" >/dev/null 2>&1 \
        && success "reportlab importable in $_PY3" \
        || warn "reportlab NOT importable — presenter-guide PDF will not render. Manual fix: $_PY3 -m pip install --break-system-packages reportlab"
    "$_PY3" -c "import pptx" >/dev/null 2>&1 \
        && success "python-pptx importable in $_PY3" \
        || warn "python-pptx NOT importable — deck assembly will fail at Phase 4. Manual fix: $_PY3 -m pip install --break-system-packages python-pptx"

    # ── VPS DURABILITY via the OpenClaw scheduler ────────────────────────────
    # The container has NO cron daemon and the gateway is PID 1, so a system
    # @reboot crontab would never fire. Use `openclaw cron create` — the SAME
    # durable recurring-task mechanism every other VPS cron in this installer
    # uses. Its state lives in the gateway config on the /data bind-mount, so the
    # cron definition survives force-recreate, and the gateway re-loads it on each
    # start. The job messages the agent to run the idempotent reassert script on a
    # DAILY backstop schedule (FIX-PRES-09(iv): was a */15 furnace of ~96 near-no-op
    # turns/day). The primary self-heal is now EVENT-shaped — the GATE-1 deps-missing
    # path in presentation-canonical-entry.sh runs the same reassert on demand — so
    # the daily cron only covers a box that force-recreates without building that
    # day. (The OpenClaw scheduler is time-based, not a vixie-cron daemon, so there
    # is no @reboot trigger to hook.)
    install_presentation_deps_cron() {
        if ! command -v openclaw >/dev/null 2>&1; then
            warn "openclaw CLI not on PATH — skipping presentation-deps re-assert cron. Re-run update-skills.sh later."
            return 0
        fi
        if oc_cron_tombstoned "reassert-presentation-deps"; then
            warn "reassert-presentation-deps is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove reassert-presentation-deps"
            return 0
        fi
        # JSON-exact presence check (fix/industry-gate-and-idempotent-crons
        # sweep): "reassert-presentation-deps" is 26 chars — over the ~22-char
        # threshold at which `openclaw cron list`'s text table truncates names
        # — the same defect that caused the Skill 39/38 6x-duplicate incident.
        if oc_cron_present "reassert-presentation-deps"; then
            success "Presentation-deps re-assert cron already installed — skipping"
            return 0
        fi
        # ── SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons) ──────────
        # reassert-presentation-deps is PURE MAINTENANCE (re-install runtime
        # deps that don't survive a Docker force-recreate). The old form wired
        # `--channel telegram --to $TG_TARGET`, auto-delivering the reassert
        # prompt to the CLIENT chat every 15 min — internal infra traffic the
        # owner must never see. FIX: SILENT main-session agent-message cron
        # (no --channel/--to/--announce). No owner target needed → no
        # operator-ID strand. Output stays in the agent's own context (log-only).
        local CHANNEL_AGENT="main"
        if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
            CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
        fi
        local REASSERT_PROMPT="[PRESENTATION-DEPS] Re-assert the presentation-pipeline runtime deps (libreoffice-impress, poppler-utils, reportlab, python-pptx) which do not survive a Docker force-recreate: bash $_VPS_REASSERT_SCRIPT . This is an idempotent maintenance script; it is a near-no-op once the deps are present."
        # The OpenClaw scheduler is time-based (5-field cron), not a vixie-cron
        # daemon, so there is no @reboot hook to fire on container start.
        # FIX-PRES-09(iv): the old "*/15 * * * *" cadence was a furnace — ~96
        # agent turns/day firing a near-no-op reassert. The real self-heal is now
        # EVENT-shaped: presentation-canonical-entry.sh runs this same idempotent
        # reassert on the GATE-1 deps-missing path (i.e. the moment a build would
        # otherwise fail), so deps are restored on demand. This cron is only a
        # DAILY backstop ("0 4 * * *") for a box that force-recreates but does not
        # build that day. The cron definition lives in the gateway config on /data
        # and so survives force-recreate.
        # Runtime-compatible SILENT main-session cron (fix/cron-flag-skew): probe
        # the CLI and emit `--session main --system-event` (2026.6.11+) or
        # `--session-target main --message` (older CLIs). Never hard-fails.
        if _oc_cron_silent_main "reassert-presentation-deps" "$CHANNEL_AGENT" "0 4 * * *" "America/New_York" "$REASSERT_PROMPT" --light-context; then
            success "Presentation-deps re-assert cron installed (SILENT main-session, no client auto-announce — survives force-recreate)"
            return 0
        fi
        warn "Presentation-deps re-assert cron creation failed. Manual install (SILENT — no client auto-announce):"
        warn "  openclaw cron create --name reassert-presentation-deps --agent $CHANNEL_AGENT \\"
        warn "    --cron '0 4 * * *' --tz America/New_York \\"
        warn "    --session main --system-event '[PRESENTATION-DEPS] bash $_VPS_REASSERT_SCRIPT'   # older CLIs: --session-target main --message"
        return 0
    }
    install_presentation_deps_cron

else
    # ── MAC ARM ───────────────────────────────────────────────────────────────
    # Python deps via the _install_py_pkg_mac helper already defined in Step 6.4.
    _install_py_pkg_mac "reportlab"   "reportlab" "reportlab (presenter-guide PDF)"
    _install_py_pkg_mac "python-pptx" "pptx"      "python-pptx (deck assembly)"

    # poppler (pdftoppm): Homebrew formula — no cask, no admin prompt.
    if command -v pdftoppm >/dev/null 2>&1; then
        success "pdftoppm (poppler) already on PATH"
    elif command -v brew >/dev/null 2>&1; then
        note "Installing poppler (pdftoppm) via Homebrew formula..."
        brew install poppler 2>&1 | tee -a "$LOG_FILE" | tail -3 \
            && success "poppler (pdftoppm) installed" \
            || warn "brew install poppler failed — pdftoppm unavailable. Phase-6 QC PNG extraction will fail."
    else
        warn "Homebrew not found — cannot install poppler. pdftoppm unavailable. Phase-6 QC PNG extraction will fail."
    fi

    # LibreOffice (soffice): NONINTERACTIVE cask so it never hangs on a TTY
    # password prompt in a headless/CI context. If it genuinely requires an admin
    # password the cask fails fast; the qc-completeness.sh gate then hard-fails so
    # the gap can't ship silently. The operator must run `brew install --cask
    # libreoffice` interactively once on that Mac and re-run the gate.
    if command -v soffice >/dev/null 2>&1 || [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
        if command -v soffice >/dev/null 2>&1; then
            success "soffice (LibreOffice) already on PATH: $(soffice --version 2>&1 | head -1 || true)"
        else
            # Binary present but not on PATH — wire a symlink (same pattern as Calibre).
            _MAC_LO_BIN="/Applications/LibreOffice.app/Contents/MacOS/soffice"
            note "LibreOffice already installed at $_MAC_LO_BIN — adding to PATH via symlink..."
            sudo ln -sf "$_MAC_LO_BIN" /usr/local/bin/soffice 2>/dev/null \
                && success "soffice symlinked to /usr/local/bin/soffice" \
                || warn "Could not symlink soffice (no sudo or symlink failed). Operator must run: sudo ln -sf $_MAC_LO_BIN /usr/local/bin/soffice OR the PPTX Assembly Specialist must use the full path $_MAC_LO_BIN"
        fi
    elif command -v brew >/dev/null 2>&1; then
        note "Installing LibreOffice (soffice) via Homebrew cask (NONINTERACTIVE — will not block on TTY)..."
        if NONINTERACTIVE=1 brew install --cask libreoffice 2>&1 | tee -a "$LOG_FILE" | tail -5; then
            if command -v soffice >/dev/null 2>&1; then
                success "LibreOffice installed and soffice is on PATH: $(soffice --version 2>&1 | head -1 || true)"
            elif [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
                _MAC_LO_BIN="/Applications/LibreOffice.app/Contents/MacOS/soffice"
                note "LibreOffice installed to /Applications/LibreOffice.app. Adding to PATH via symlink..."
                sudo ln -sf "$_MAC_LO_BIN" /usr/local/bin/soffice 2>/dev/null \
                    && success "soffice symlinked: /usr/local/bin/soffice -> $_MAC_LO_BIN" \
                    || warn "Could not symlink soffice (sudo failed). Skill 23 PPTX assembly must use full path: $_MAC_LO_BIN"
            else
                warn "brew install --cask libreoffice ran but soffice not found. Operator: re-run interactively or check /Applications/LibreOffice.app."
                warn "The qc-completeness.sh gate (step 6b) will FAIL until soffice is resolvable."
            fi
        else
            warn "NONINTERACTIVE LibreOffice cask install failed (may require admin password)."
            warn "Operator fix: run interactively once: brew install --cask libreoffice"
            warn "Then re-run qc-completeness.sh to confirm the gate passes."
            warn "The qc-completeness.sh gate (step 6b) will FAIL until soffice is resolvable."
        fi
    else
        warn "Homebrew not found — cannot install LibreOffice. PPTX-to-PDF export will fail."
        warn "Operator fix: install Homebrew (https://brew.sh), then: brew install --cask libreoffice"
    fi
fi

# ----------------------------------------------------------
# v10.3.0: Install Calibre (ebook-convert) for Skill 22 book extraction
# ----------------------------------------------------------
# Skill 22 needs `ebook-convert` to handle MOBI, AZW, AZW3, KFX formats.
# Without Calibre, the book-to-persona pipeline silently skips those formats
# and only processes PDF/EPUB — which is fine for many books but causes
# silent gaps for Kindle libraries. Auto-install here so it's ready by the
# time Skill 22 runs in Wave 5.
#
# Mac: Homebrew cask (the canonical Mac install path). Falls back gracefully
# if brew is missing or the install fails — Skill 22 has graceful degradation
# for missing Calibre.
# v10.15.17: Guard every `ebook-convert --version` with a hard timeout.
# On a headless Mac, `ebook-convert --version` can wedge forever (Calibre tries
# to spin up a Qt/GUI subsystem with no display), which stalls the whole install
# at this gate. Resolve a timeout wrapper up front: GNU coreutils ships
# `gtimeout` on Mac (via Homebrew coreutils); fall back to a plain `timeout` if
# present; if neither exists, run bare (the `|| true` keeps the gate non-fatal).
if command -v gtimeout >/dev/null 2>&1; then
    EBOOK_TIMEOUT="gtimeout 20"
elif command -v timeout >/dev/null 2>&1; then
    EBOOK_TIMEOUT="timeout 20"
else
    EBOOK_TIMEOUT=""
fi
if command -v ebook-convert >/dev/null 2>&1; then
    success "Calibre (ebook-convert) already installed: $($EBOOK_TIMEOUT ebook-convert --version 2>&1 | head -1 || true)"
else
    note "Installing Calibre (ebook-convert) for Skill 22 ebook extraction..."
    if command -v brew >/dev/null 2>&1; then
        if brew install --cask calibre 2>&1 | tee -a "$LOG_FILE" | tail -3; then
            if command -v ebook-convert >/dev/null 2>&1; then
                success "Calibre installed: $($EBOOK_TIMEOUT ebook-convert --version 2>&1 | head -1 || true)"
            else
                # Calibre installs to /Applications/calibre.app on Mac; ebook-convert is inside
                CALIBRE_BIN="/Applications/calibre.app/Contents/MacOS/ebook-convert"
                if [ -x "$CALIBRE_BIN" ]; then
                    note "Calibre installed to /Applications/calibre.app. Adding to PATH via symlink..."
                    sudo ln -sf "$CALIBRE_BIN" /usr/local/bin/ebook-convert 2>/dev/null || \
                        warn "Could not symlink ebook-convert — Skill 22 will need to use the full path /Applications/calibre.app/Contents/MacOS/ebook-convert"
                else
                    warn "Calibre install ran but ebook-convert not found on PATH. Skill 22 ebook extraction will be limited to PDF/EPUB."
                fi
            fi
        else
            warn "brew install --cask calibre failed. Skill 22 ebook extraction limited to PDF/EPUB."
            warn "To install manually: brew install --cask calibre"
        fi
    else
        warn "Homebrew not found on this Mac. Skill 22 ebook extraction will be limited to PDF/EPUB."
        warn "To install Calibre manually: install Homebrew (https://brew.sh), then run: brew install --cask calibre"
    fi
fi

# ----------------------------------------------------------
# v6.6.0 / Step 6.7: Install Skill 22 persona-inbox-watcher cron (Mac)
# ----------------------------------------------------------
# Installs a */10 launchctl-backed cron for the Mac so new files dropped into
# coaching-personas/inbox/ are automatically converted to personas.
# TOKEN-SAFE: MAX_PER_RUN=5 cap, lock files, stale-lock reaping, self-disables.
# ────────────────────────────────────────────────────────────────────────────
step "Step 6.7: Installing persona-inbox-watcher cron (Skill 22 auto-processing, Mac)"

# v14.1.3: MAC-GATED. This step uses the macOS skills path ($HOME/.openclaw/skills)
# and the system `crontab` daemon. A VPS container has neither (skills live at
# /data/.openclaw/skills and there is NO cron daemon — gateway is PID 1), so on
# Linux it previously just emitted a spurious "not found at ~/.openclaw/skills"
# warning and a no-op crontab attempt. Gate it to mac so the Linux run stays
# clean; VPS persona auto-processing, if needed, is handled by an OpenClaw
# scheduler cron elsewhere, not a system crontab.
if [ "$OC_PLATFORM" = "mac" ]; then
    # On Mac, skills live at ~/.openclaw/skills/
    _MAC_SKILLS_DIR="$HOME/.openclaw/skills"
    _INBOX_WATCHER_SCRIPT_MAC="$_MAC_SKILLS_DIR/22-book-to-persona-coaching-leadership-system/scripts/persona-inbox-watcher.sh"

    if [ -f "$_INBOX_WATCHER_SCRIPT_MAC" ]; then
        chmod +x "$_INBOX_WATCHER_SCRIPT_MAC" 2>/dev/null || true

        # Resolve canonical log path (Mac)
        _WATCHER_LOG_MAC="$HOME/.openclaw/logs/persona-inbox-watcher.log"
        mkdir -p "$(dirname "$_WATCHER_LOG_MAC")"
        _CRON_LINE_MAC="*/10 * * * * bash $_INBOX_WATCHER_SCRIPT_MAC >> $_WATCHER_LOG_MAC 2>&1"

        if crontab -l 2>/dev/null | grep -qF "persona-inbox-watcher.sh"; then
            success "persona-inbox-watcher cron already installed — skipping"
        else
            ( crontab -l 2>/dev/null | grep -v "persona-inbox-watcher"; echo "$_CRON_LINE_MAC" ) | crontab - 2>/dev/null \
                && success "persona-inbox-watcher cron installed (*/10 min)" \
                || warn "crontab install failed. Run manually: crontab -e and add: $_CRON_LINE_MAC"
        fi

        # Create inbox dir
        _INBOX_DIR_MAC="$HOME/.openclaw/workspace/data/coaching-personas/inbox"
        mkdir -p "$_INBOX_DIR_MAC" "$_INBOX_DIR_MAC/processed" "$_INBOX_DIR_MAC/.locks"
        success "Persona inbox ready: $_INBOX_DIR_MAC"
        note "Drop PDF/EPUB/video/text files here and the watcher will auto-convert them to personas."
    else
        warn "persona-inbox-watcher.sh not found at $_INBOX_WATCHER_SCRIPT_MAC — cron NOT installed."
    fi
else
    note "persona-inbox-watcher cron skipped (VPS: no system crontab; gateway is PID 1)"
fi

# ----------------------------------------------------------
# Step 7: Configure Concurrency
# ----------------------------------------------------------
# NOTE (v9.7.8): canonical sub-agent + bootstrap config is now applied in
# Step 0 via configure_subagent_and_bootstrap_canonical(). The legacy
# configure_concurrency() function (renamed _LEGACY_UNUSED) used wrong
# field names (maxQueue/maxDepth) and lower values (50/10/4). Step 0 sets
# maxChildrenPerAgent=20, maxConcurrent=100 (min-clamp 50), maxSpawnDepth=4,
# bootstrapMaxChars=200000, bootstrapTotalMaxChars=400000, plus the
# allowAgents=["*"] wildcard on every agents.list entry.
note "Step 7: Sub-agent + bootstrap config already applied in Step 0 — skipping"

# ----------------------------------------------------------
# Step 7a: Configure Active Memory (Layer 8)
# ----------------------------------------------------------
configure_active_memory() {
    step "Step 7a: Configuring Active Memory (Layer 8)"

    local OPENCLAW_JSON="$OC_JSON"

    if [ ! -f "$OPENCLAW_JSON" ]; then
        warn "openclaw.json not found - skipping Active Memory config"
        return
    fi

    backup_config_file "$OPENCLAW_JSON"

    # PRD 2.6: detect a second embeddings provider key so we can write the
    # KNOWN-ISSUES #1 mitigation (memorySearch.fallback.* + memorySearch.cache.*)
    # automatically.  Primary provider is Gemini; if OpenAI is also present it
    # becomes the fallback provider (lowest latency on rate-limit trip).  If
    # only OpenAI is present we promote it to primary with no fallback object.
    #
    # v13.2.1 CONDITIONAL embedding-default: v13.2.0 HARD-PINNED gemini-embedding-2
    # whenever this ran, which broke 6 boxes that have NO usable Google key (it
    # pinned a model they cannot serve). The Gemini default is now CONDITIONAL on
    # a usable key, detected via has_usable_gemini_key() — which checks all THREE
    # Google aliases across every store + the live container env before ever
    # concluding "no key". When NONE is found we keep the box's existing working
    # embedding model (if non-dying) or fall back to whatever embedding-capable
    # key the box DOES have. We NEVER pin a model the box has no key for.
    local _GEMINI_KEY _OPENAI_KEY _OPENROUTER_KEY _GEMINI_OK
    if _GEMINI_KEY=$(has_usable_gemini_key 2>/dev/null); then
        _GEMINI_OK=1
    else
        _GEMINI_KEY=""
        _GEMINI_OK=0
    fi
    _OPENAI_KEY=$(search_env_var "OPENAI_API_KEY" 2>/dev/null || true)
    _OPENROUTER_KEY=$(search_env_var "OPENROUTER_API_KEY" 2>/dev/null || true)

    if [ "$_GEMINI_OK" = "1" ]; then
        note "  Embedding default: usable Google/Gemini key FOUND → pinning gemini-embedding-2 @3072 (fleet standard)"
    elif [ -n "$_OPENAI_KEY" ]; then
        note "  Embedding default: NO usable Google/Gemini key (all 3 aliases × every store) → keeping/falling back to OpenAI text-embedding-3-small (never pin a keyless model)"
    elif [ -n "$_OPENROUTER_KEY" ]; then
        note "  Embedding default: NO usable Google/Gemini key → falling back to OpenRouter openai/text-embedding-3-large (never pin a keyless model)"
    else
        note "  Embedding default: NO usable Google/Gemini/OpenAI/OpenRouter key found → leaving any EXISTING working memorySearch model in place; not forcing gemini"
    fi

    OPENCLAW_JSON="$OPENCLAW_JSON" \
    OC_GEMINI_KEY="$_GEMINI_KEY" \
    OC_OPENAI_KEY="$_OPENAI_KEY" \
    OC_OPENROUTER_KEY="$_OPENROUTER_KEY" \
    python3 << 'PYEOF'
import json, os, sys

path           = os.environ['OPENCLAW_JSON']
gemini_key     = os.environ.get('OC_GEMINI_KEY', '').strip()
openai_key     = os.environ.get('OC_OPENAI_KEY', '').strip()
openrouter_key = os.environ.get('OC_OPENROUTER_KEY', '').strip()

try:
    with open(path) as f:
        config = json.load(f)

    # v16.1.4 BUGFIX (supersedes the v9.7.8 "delete" workaround):
    # active-memory IS a real plugin — dist/extensions/active-memory/
    # openclaw.plugin.json (activation.onStartup) — and AGENTS.md expects Layer-8
    # Active Memory ENABLED. Its options are plugin CONFIG and MUST be nested under
    # plugins.entries.active-memory.config. The entries.<id> schema is
    # additionalProperties:false (only enabled/hooks/subagent/llm/config), so the
    # six option keys (agents, allowedChatTypes, queryMode, promptStyle, timeoutMs,
    # maxSummaryChars) as TOP-LEVEL siblings of 'enabled' fail validation
    # ("plugins.entries.active-memory: Invalid input"), killing the gateway. The
    # earlier fix DELETED the block (dropping Layer 8); we instead WRITE it valid
    # (enabled + nested config) and SELF-HEAL any pre-existing flat keys.
    #
    # Active Memory's provider/search layers are ALSO configured below via:
    #   - agents.defaults.memorySearch.{enabled, sources, provider, fallback, ...}
    #   - plugins.entries.memory-core.config.* (provider plugin)
    #   - plugins.entries.memory-wiki.config.* (wiki layer)

    plugins = config.setdefault('plugins', {})
    entries = plugins.setdefault('entries', {})

    # Enable active-memory with options nested under config; migrate (never delete)
    # any flat option keys a prior broken install wrote.
    AM_ENTRY_TOP = ("enabled", "hooks", "subagent", "llm", "config")
    AM_DEFAULTS = {
        "agents": ["main"], "allowedChatTypes": ["direct"], "queryMode": "recent",
        "promptStyle": "balanced", "timeoutMs": 15000, "maxSummaryChars": 220,
    }
    am = entries.get('active-memory')
    am_fresh = not isinstance(am, dict)
    if am_fresh:
        am = {}
    am_cfg = am.get('config') if isinstance(am.get('config'), dict) else {}
    _am_moved = [x for x in list(am) if x not in AM_ENTRY_TOP]
    for _k in _am_moved:
        am_cfg.setdefault(_k, am.pop(_k))
    if am_fresh and not am_cfg:
        am_cfg = dict(AM_DEFAULTS)
    am['enabled'] = True
    am['config'] = am_cfg
    entries['active-memory'] = am
    if _am_moved:
        print("  ✓ Repaired plugins.entries.active-memory — nested %d flat option key(s) under config (Layer 8 preserved)" % len(_am_moved))
    else:
        print("  ✓ Active Memory (Layer 8) enabled with options nested under config")

    # Ensure memory-core plugin is enabled (the real memory plugin)
    mc = entries.setdefault('memory-core', {})
    mc['enabled'] = True

    # Optional: ensure memory-wiki is present + enabled (for structured docs)
    mw = entries.setdefault('memory-wiki', {})
    mw.setdefault('enabled', True)

    # Configure agents.defaults.memorySearch — this is where Active Memory
    # behavior actually lives in the live schema
    agents = config.setdefault('agents', {})
    defaults = agents.setdefault('defaults', {})
    ms = defaults.setdefault('memorySearch', {})
    ms['enabled']  = True
    # Sources: "memory" reads MEMORY.md + memory/ files; "qmd" reads cross-agent transcripts
    ms.setdefault('sources', ["memory"])

    # ── v13.2.1 CONDITIONAL embedding default ────────────────────────────────
    # Determine primary provider/model from discovered keys. The rule:
    #   • A usable Google/Gemini key (any of 3 aliases, any store, incl. live
    #     container env) → PIN gemini-embedding-2 @3072 (fleet standard). This is
    #     the v13.2.0 behavior, now GATED on the key actually being usable.
    #   • Genuinely NO Gemini key anywhere → do NOT force gemini. Instead:
    #       (a) keep the box's EXISTING working memorySearch provider/model if it
    #           is already set and non-dying (e.g. openai/text-embedding-3-small,
    #           or an openrouter embedding) — never disturb a working box;
    #       (b) else pick a sane fallback based on the embedding-capable key the
    #           box DOES have: OpenAI → text-embedding-3-small;
    #           OpenRouter → openai/text-embedding-3-large.
    #   • NEVER pin a model the box has no key for (the v13.2.0 bug).
    #
    # DYING_OR_LEGACY models we always migrate AWAY from when we own the choice:
    #   - gemini-embedding-001 HARD-SHUTS-DOWN 2026-07-14.
    #   - gemini-embedding-exp-03-07 (experimental, retired).
    # NOTE: text-embedding-3-small is "legacy" ONLY relative to gemini — it is a
    # perfectly serveable OpenAI model, so it is NOT migrated away from on a
    # no-gemini box (that was the regression: forcing gemini over a working
    # OpenAI model the box could actually serve).
    CANON_EMBED_MODEL = "gemini-embedding-2"
    CANON_EMBED_DIM   = 3072
    # Models we MUST migrate off of even on a gemini box (truly dying/legacy).
    GEMINI_DYING      = {"gemini-embedding-001", "gemini-embedding-exp-03-07"}
    # Embedding models the runtime can serve WITHOUT a Google key (keep these).
    NON_GEMINI_OK     = {"text-embedding-3-small", "text-embedding-3-large",
                         "openai/text-embedding-3-small", "openai/text-embedding-3-large"}

    if gemini_key:
        # Usable Google/Gemini key present → pin the GA fleet-standard embedding.
        ms['provider'] = "gemini"
        cur = ms.get('model')
        # Force-set canonical when unset, on a dying gemini model, OR currently on
        # a non-gemini model that we are now upgrading because a real key exists.
        if (not cur) or (cur in GEMINI_DYING) or (cur != CANON_EMBED_MODEL):
            ms['model'] = CANON_EMBED_MODEL
            if cur and cur != CANON_EMBED_MODEL:
                print(f"  ✓ memorySearch.model migrated {cur!r} → {CANON_EMBED_MODEL!r} (usable Gemini key present; pre-2026-07-14 shutdown guard)")
        ms['dimensions'] = CANON_EMBED_DIM
    else:
        # ── NO usable Gemini key anywhere — do NOT force gemini. ──────────────
        cur_provider = str(ms.get('provider') or "").lower()
        cur_model    = ms.get('model')

        # CRITICAL UN-PIN: if a prior (v13.2.0) run hard-pinned gemini on this
        # keyless box, that model can never be served. Repair it to whatever the
        # box CAN serve. We treat provider=='gemini' OR model starting 'gemini'
        # as "stranded on a keyless gemini pin".
        stranded_on_gemini = (cur_provider == "gemini") or \
                             (isinstance(cur_model, str) and cur_model.lower().startswith("gemini"))

        if (not stranded_on_gemini) and cur_provider in ("openai", "openrouter") \
           and isinstance(cur_model, str) and cur_model in NON_GEMINI_OK:
            # (a) Box already has a working, serveable non-gemini embedding —
            #     leave it exactly as-is (never disturb a working box).
            ms['dimensions'] = ms.get('dimensions', 1536)
            print(f"  ✓ No usable Gemini key — keeping existing working memorySearch {cur_provider}/{cur_model!r} (no false gemini pin)")
        elif openai_key:
            # (b) Fall back to OpenAI (text-embedding-3-small).
            ms['provider'] = "openai"
            ms['model']    = "text-embedding-3-small"
            ms['dimensions'] = 1536
            if stranded_on_gemini:
                print(f"  ✓ No usable Gemini key — UN-PINNED keyless gemini → openai/text-embedding-3-small (box can serve this)")
            else:
                print(f"  ✓ No usable Gemini key — set memorySearch → openai/text-embedding-3-small")
        elif openrouter_key:
            # (b) Fall back to OpenRouter (openai/text-embedding-3-large).
            ms['provider'] = "openrouter"
            ms['model']    = "openai/text-embedding-3-large"
            ms['dimensions'] = 3072
            if stranded_on_gemini:
                print(f"  ✓ No usable Gemini key — UN-PINNED keyless gemini → openrouter/openai/text-embedding-3-large")
            else:
                print(f"  ✓ No usable Gemini key — set memorySearch → openrouter/openai/text-embedding-3-large")
        else:
            # No embedding-capable key at all. Do NOT pin gemini. Keep whatever
            # the box already has (it may have a manually-configured provider we
            # don't recognize); only strip a stranded keyless gemini pin if we
            # have literally nothing better — leaving provider unset is safer than
            # pinning a model that 100% cannot resolve.
            if stranded_on_gemini:
                ms.pop('provider', None)
                ms.pop('model', None)
                ms.pop('dimensions', None)
                print(f"  ⚠ No embedding-capable key (Gemini/OpenAI/OpenRouter) found — removed keyless gemini pin; memorySearch provider/model left UNSET until a key is added (avoids pinning an unservable model)")
            else:
                print(f"  ⚠ No embedding-capable key found — leaving existing memorySearch provider/model untouched")

    # ── PRD 2.6 / KNOWN-ISSUES #1: embeddings-stall mitigation ─────────────
    # When the primary provider rate-limits, the memory-search step blocks the
    # entire agent loop (no timeout, infinite retry spin).  Mitigation: write
    # a structured fallback object + cache settings so the runtime trips over
    # to the fallback provider instead of stalling.  This is applied
    # automatically whenever a SECOND provider key is present.
    #
    # Documented config knobs (KNOWN-ISSUES.md §1, fleet-confirmed):
    #   memorySearch.fallback.provider   — second provider name
    #   memorySearch.fallback.model      — embedding model for that provider
    #   memorySearch.fallback.apiKey     — resolved key (written so gateway
    #                                      picks it up without a separate env
    #                                      lookup; still present in env too)
    #   memorySearch.cache.enabled       — short-circuit repeat queries
    #   memorySearch.cache.maxEntries    — keep last N embeddings in RAM
    # ────────────────────────────────────────────────────────────────────────
    has_second_provider = (gemini_key and openai_key)
    if has_second_provider:
        # Gemini is primary; OpenAI is the fast, low-latency fallback.
        fb = ms.setdefault('fallback', {})
        if isinstance(fb, str):
            # Upgrade legacy string value ("openai") to a full object.
            fb = {}
            ms['fallback'] = fb
        fb.setdefault('provider', 'openai')
        fb.setdefault('model',    'text-embedding-3-small')
        fb.setdefault('apiKey',   openai_key)

        cache = ms.setdefault('cache', {})
        cache['enabled']       = True
        cache.setdefault('maxEntries', 512)

        print("  ✓ memorySearch.fallback.{provider,model,apiKey} written (KNOWN-ISSUES #1 mitigation)")
        print("  ✓ memorySearch.cache.{enabled,maxEntries} written")
    elif gemini_key and not openai_key:
        # Gemini primary, no second provider — keep the legacy "openai" string
        # fallback for compat (matches prior behavior; harmless name-only hint).
        ms.setdefault('fallback', "openai")
    else:
        # No gemini key. Do NOT leave a dangling "openai" string fallback when
        # the box has no OpenAI key (v13.2.1): a name-only fallback to a keyless
        # provider is misleading. The single resolved provider above stands on
        # its own; strip any legacy fallback string/object pointing nowhere.
        ms.pop('fallback', None)

    # ── EMBEDDING-PREVENTION BUNDLE item 2: DEFAULT INDEX SCOPING ────────────
    # The OpenClaw runtime UNIONS each agent's memorySearch.extraPaths onto
    # agents.defaults.memorySearch.extraPaths. A giant master-files corpus placed
    # in defaults gets re-embedded into EVERY department's DB (multi-GB bloat per
    # box). Keep the DEFAULT lean: declare an EMPTY extraPaths so new/updated boxes
    # inherit a lean index. The shared corpus is attached ONCE to the main agent
    # only (Skill 31 activate-memory-stack.sh). Defensive: if a legacy install
    # planted ANY path into defaults.extraPaths, strip it back to empty here.
    if not isinstance(ms.get('extraPaths'), list):
        ms['extraPaths'] = []
    elif ms['extraPaths']:
        print(f"  ✓ memorySearch.extraPaths reset to [] in defaults (index-scoping; was {len(ms['extraPaths'])} path(s) — bloat source)")
        ms['extraPaths'] = []

    # ── EMBEDDING-PREVENTION BUNDLE item 3: PROVIDER-SELF-LOOP GUARDRAIL ──────
    # A cycled-then-cleared embedding provider can land memorySearch.provider /
    # .model / .fallback on the literal string "none", which breaks the embed
    # index (multimodal-memory killer). No embedding/model field may be 'none'.
    # If we find 'none', repair it to a provider/model THE BOX CAN ACTUALLY SERVE
    # (v13.2.1: never repair to gemini unless a usable Gemini key exists — that
    # was the keyless-pin regression). Repair preference mirrors the conditional
    # default above: gemini (only with key) → openai → openrouter.
    if gemini_key:
        _GUARD_DEFAULT_PROVIDER = "gemini"
    elif openai_key:
        _GUARD_DEFAULT_PROVIDER = "openai"
    elif openrouter_key:
        _GUARD_DEFAULT_PROVIDER = "openrouter"
    else:
        _GUARD_DEFAULT_PROVIDER = None
    _GUARD_PROVIDER = ms.get('provider') if ms.get('provider') not in (None, "", "none") else _GUARD_DEFAULT_PROVIDER
    # Never let the guard re-pin gemini on a keyless box.
    if _GUARD_PROVIDER == "gemini" and not gemini_key:
        _GUARD_PROVIDER = _GUARD_DEFAULT_PROVIDER
    _GUARD_MODEL_MAP = {
        "gemini": "gemini-embedding-2",
        "openai": "text-embedding-3-small",
        "openrouter": "openai/text-embedding-3-large",
    }
    _GUARD_MODEL = _GUARD_MODEL_MAP.get(_GUARD_PROVIDER)
    if str(ms.get('provider')).lower() == "none" and _GUARD_PROVIDER:
        ms['provider'] = _GUARD_PROVIDER
        print(f"  ✓ memorySearch.provider was 'none' → repaired to {_GUARD_PROVIDER!r} (provider-self-loop guard)")
    if str(ms.get('model')).lower() == "none" and _GUARD_MODEL:
        ms['model'] = _GUARD_MODEL
        print(f"  ✓ memorySearch.model was 'none' → repaired to {_GUARD_MODEL!r} (provider-self-loop guard)")
    # fallback may legitimately be a provider-name string OR an object; only the
    # literal 'none' is illegal (it disables fallback while looking configured).
    if isinstance(ms.get('fallback'), str) and ms['fallback'].lower() == "none":
        ms.pop('fallback', None)
        print("  ✓ memorySearch.fallback was 'none' → removed (provider-self-loop guard)")
    if isinstance(ms.get('fallback'), dict) and str(ms['fallback'].get('provider')).lower() == "none":
        ms.pop('fallback', None)
        print("  ✓ memorySearch.fallback.provider was 'none' → fallback removed (provider-self-loop guard)")

    # v10.x.6 recovery knob: hard agent-turn timeout in SECONDS.
    # Schema-confirmed (agents.defaults.timeoutSeconds, positive int, dist 2026.5.20).
    # 600s = 10 min: long enough for legit deepseek thinking=high runs (2-5 min),
    # short enough to recover from a true hang. Also scales the internal CLI stall
    # watchdog window so a stalled long-thinking session recovers automatically.
    defaults.setdefault('timeoutSeconds', 600)

    # plugins.slots.memory — point at memory-core (the canonical memory backend)
    slots = plugins.setdefault('slots', {})
    slots['memory'] = "memory-core"

    with open(path, 'w') as f:
        json.dump(config, f, indent=2)

    print("  ✓ Active Memory configured (Layer 8) — canonical schema")
    print("  ✓ plugins.entries.memory-core.enabled = true")
    print("  ✓ plugins.entries.memory-wiki.enabled = true")
    print("  ✓ agents.defaults.memorySearch.{enabled, sources, provider, model} set")
    print("  ✓ plugins.slots.memory = memory-core")
except Exception as e:
    print(f"  ✗ Could not configure Active Memory: {e}", file=sys.stderr)
PYEOF
}

configure_active_memory

# ----------------------------------------------------------
# Step 7a-qc: QC — assert memorySearch fallback + cache keys (PRD 2.6)
# ----------------------------------------------------------
# KNOWN-ISSUES #1 mitigation check: when both Gemini and OpenAI keys exist
# the full fallback object and cache settings MUST be present in openclaw.json.
# If they are missing, the agent loop can stall under embeddings rate-limits.
qc_check_memory_search_fallback() {
    step "QC: memorySearch fallback + cache presence check (PRD 2.6)"

    local OPENCLAW_JSON="$OC_JSON"
    if [ ! -f "$OPENCLAW_JSON" ]; then
        warn "  openclaw.json not found — skipping memorySearch QC check"
        return
    fi

    local _G _O
    _G=$(search_env_var "GEMINI_API_KEY" 2>/dev/null || true)
    _O=$(search_env_var "OPENAI_API_KEY" 2>/dev/null || true)

    if [ -z "$_G" ] || [ -z "$_O" ]; then
        note "  memorySearch fallback QC: only one provider key present — fallback object not required"
        return 0
    fi

    # Both keys exist — assert the full fallback object and cache settings.
    OPENCLAW_JSON="$OPENCLAW_JSON" python3 << 'QC_PYEOF'
import json, os, sys

path = os.environ['OPENCLAW_JSON']
try:
    with open(path) as f:
        cfg = json.load(f)
except Exception as e:
    print(f"  [QC FAIL] Cannot read openclaw.json: {e}", file=sys.stderr)
    sys.exit(1)

ms = (cfg
      .get('agents', {})
      .get('defaults', {})
      .get('memorySearch', {}))

failures = []

# 1. fallback must be an object (not the legacy string)
fb = ms.get('fallback')
if not isinstance(fb, dict):
    failures.append("memorySearch.fallback is absent or not an object (got: {!r})".format(fb))
else:
    for key in ('provider', 'model', 'apiKey'):
        if not fb.get(key):
            failures.append(f"memorySearch.fallback.{key} is missing or empty")

# 2. cache block must exist with enabled=true
cache = ms.get('cache')
if not isinstance(cache, dict):
    failures.append("memorySearch.cache is absent or not an object")
elif not cache.get('enabled'):
    failures.append("memorySearch.cache.enabled is not true")

if failures:
    print("  [QC FAIL] memorySearch fallback/cache keys incomplete:", file=sys.stderr)
    for f in failures:
        print(f"    ✗ {f}", file=sys.stderr)
    sys.exit(1)

print("  ✓ memorySearch.fallback.{provider,model,apiKey} — present")
print("  ✓ memorySearch.cache.{enabled} — present")
print("  [QC PASS] KNOWN-ISSUES #1 mitigation verified in openclaw.json")
QC_PYEOF

    local qc_exit=$?
    if [ $qc_exit -ne 0 ]; then
        error "memorySearch fallback/cache QC FAILED — re-running configure_active_memory"
        # Auto-remediate: re-run the config step once and check again.
        configure_active_memory
        OPENCLAW_JSON="$OPENCLAW_JSON" python3 << 'QC_RETRY_PYEOF'
import json, os, sys
path = os.environ['OPENCLAW_JSON']
with open(path) as f:
    cfg = json.load(f)
ms = cfg.get('agents', {}).get('defaults', {}).get('memorySearch', {})
fb = ms.get('fallback')
cache = ms.get('cache')
ok = (isinstance(fb, dict) and
      fb.get('provider') and fb.get('model') and fb.get('apiKey') and
      isinstance(cache, dict) and cache.get('enabled'))
if not ok:
    print("  [QC FAIL] Still missing after remediation — manual review required", file=sys.stderr)
    sys.exit(1)
print("  [QC PASS] memorySearch fallback/cache confirmed after remediation")
QC_RETRY_PYEOF
    fi
}

qc_check_memory_search_fallback

# ----------------------------------------------------------
# Step 7b: Dreaming (memory consolidation) -- DEFAULT OFF (v11.25.0)
# ----------------------------------------------------------
# v11.25.0: dreaming is now left OFF by default on new installs.
# Rationale: dreaming fires a nightly memory-consolidation session that
# launches a sub-agent and burns tokens. On boxes with many agents this
# compounds the [heartbeat poll] loop problem. Operator must explicitly
# opt in via: plugins.entries.memory-core.config.dreaming.enabled = true
# Existing fleet is unaffected (dreaming stays enabled where already on).
configure_dreaming() {
    step "Step 7b: Dreaming config (leaving OFF by default -- operator opt-in required)"
    local OPENCLAW_JSON="$OC_JSON"
    if [ ! -f "$OPENCLAW_JSON" ]; then
        warn "openclaw.json not found - skipping dreaming config"
        return
    fi
    backup_config_file "$OPENCLAW_JSON"
    OPENCLAW_JSON="$OPENCLAW_JSON" python3 << 'PYEOF_INNER'
import json, os, sys
path = os.environ['OPENCLAW_JSON']
try:
    with open(path) as f:
        cfg = json.load(f)
    mc = cfg.setdefault('plugins', {}).setdefault('entries', {}).setdefault('memory-core', {})
    mc_cfg = mc.setdefault('config', {})
    dreaming = mc_cfg.setdefault('dreaming', {})
    # v11.25.0: leave dreaming OFF on new installs (operator opt-in only)
    dreaming.setdefault('enabled', False)
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)
    print("  \u2713 plugins.entries.memory-core.config.dreaming.enabled = false (default; operator may enable)")
    print("  \u2713 To enable: set plugins.entries.memory-core.config.dreaming.enabled = true in openclaw.json")
except Exception as e:
    print(f"  \u2717 Could not write dreaming config: {e}", file=sys.stderr)
PYEOF_INNER
}

configure_dreaming

# ----------------------------------------------------------
# Step 7c: Idle-Session Reset Policy (PRD 1.11 — Layer-2 prevention)
# ----------------------------------------------------------
# PRD 1.11: A long-lived session that resumes after a skill/SOUL.md update
# will still read the OLD system prompt (Layer-2 failure: deployed != loaded).
# An idle-reset policy ensures the session is automatically rebuilt from disk
# after N hours of idle, so any fix deployed to disk is guaranteed to reach
# the model context within the next half-day at most.
#
# IMPORTANT — schema confirmation note:
# The key agents.defaults.session.idleResetMinutes is written using the
# direct JSON deep-merge pattern (NOT `openclaw config set`) per the
# memory-activation rule — nested `agents.defaults.*` keys fail with
# "Invalid input" via openclaw config set on 2026.5.20+.
# The key name and unit were checked against CHANGELOG v11.3.2 and
# the existing agents.defaults.timeoutSeconds pattern (same schema level).
# If this key is invalid for the installed gateway version, `openclaw config validate`
# will catch it below and the section will be logged as a warning, not a fatal.
#
# Default: 720 minutes (12 hours). Long enough to survive a conversation pause
# or overnight idle; short enough that a deployed fix reaches context by morning.
# Operator override: set IDLE_RESET_MINUTES env var before running install.sh.

configure_idle_session_reset() {
    step "Step 7c: Configuring idle-session reset policy (PRD 1.11)"
    local OPENCLAW_JSON="$OC_JSON"
    if [ ! -f "$OPENCLAW_JSON" ]; then
        warn "openclaw.json not found - skipping idle-session reset config"
        return
    fi
    backup_config_file "$OPENCLAW_JSON"
    local IDLE_MINUTES="${IDLE_RESET_MINUTES:-720}"
    OPENCLAW_JSON="$OPENCLAW_JSON" IDLE_MINUTES="$IDLE_MINUTES" python3 << 'PYEOF_IDLE'
import json, os, sys
path = os.environ['OPENCLAW_JSON']
idle_minutes = int(os.environ.get('IDLE_MINUTES', '720'))
try:
    with open(path, 'r') as f:
        config = json.load(f)

    agents = config.setdefault('agents', {})
    defaults = agents.setdefault('defaults', {})
    session = defaults.setdefault('session', {})

    # Only set if not already configured (idempotent)
    if session.get('idleResetMinutes') != idle_minutes:
        session['idleResetMinutes'] = idle_minutes
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"  ✓ agents.defaults.session.idleResetMinutes = {idle_minutes} (12-hour idle rebuild)")
    else:
        print(f"  ✓ agents.defaults.session.idleResetMinutes already {idle_minutes} — no-op")
except Exception as e:
    print(f"  ✗ Could not configure idle-session reset: {e}", file=sys.stderr)
PYEOF_IDLE

    # QC assertion: verify the key landed and config validates
    if command -v openclaw >/dev/null 2>&1; then
        if openclaw config validate 2>/dev/null; then
            echo "  ✓ openclaw config validate passed after idle-session reset config"
        else
            warn "  openclaw config validate FAILED after idle-session reset config"
            warn "  agents.defaults.session.idleResetMinutes may not be supported on this version"
            warn "  Reverting to pre-config backup..."
            if [ -f "${OPENCLAW_JSON}.bak" ]; then
                cp "${OPENCLAW_JSON}.bak" "$OPENCLAW_JSON"
                warn "  Reverted. Idle-session reset not applied; apply manually if needed."
            fi
        fi
    fi
}

configure_idle_session_reset

# ----------------------------------------------------------
# Step 8: Exec Security Configuration
# ----------------------------------------------------------
send_telegram_progress "✓ AI engines configured. Locking down permissions next so your agent only does what you approve…"
step "Step 8: Applying Exec Security Configuration"

OPENCLAW_JSON="$OC_JSON"
if [ -f "$OPENCLAW_JSON" ]; then
    backup_config_file "$OPENCLAW_JSON"

    OPENCLAW_JSON="$OPENCLAW_JSON" python3 << 'PYEOF'
import json, os

path = os.environ['OPENCLAW_JSON']
if os.path.exists(path):
    with open(path) as f:
        cfg = json.load(f)
    
    cfg.setdefault('tools', {})['exec'] = {
        'security': 'full',
        'ask': 'off'
    }
    
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)
    print("  ✓ tools.exec: security=full, ask=off")
PYEOF
fi

EXEC_APPROVALS="$OC_CONFIG/exec-approvals.json"
if [ -f "$EXEC_APPROVALS" ]; then
    backup_config_file "$EXEC_APPROVALS"
    
    python3 - "$EXEC_APPROVALS" << 'PYEOF'
import json, sys
p = sys.argv[1]
cfg = json.load(open(p))
cfg.setdefault('defaults', {}).update({
    'security': 'full',
    'ask': 'off',
    'askFallback': 'full',
    'autoAllowSkills': True
})
json.dump(cfg, open(p, 'w'), indent=2)
print("  ✓ exec-approvals.json patched")
PYEOF
else
    note "exec-approvals.json not found - will apply on next run"
fi

# ----------------------------------------------------------
# Step 8b: Tiered Speech-to-Text (faster-whisper LOCAL + OpenAI fallback)
# ----------------------------------------------------------
# This is the MAC installer (Apple Silicon). On Mac, audio transcription runs
# LOCALLY via faster-whisper (CTranslate2 backend) on the Neural Engine:
#   • model "medium" — the balanced default (fast on Apple Silicon, free, private)
#   • runs on-box → no token cost, no audio ever leaves the client's machine
#   • OpenAI cloud (gpt-4o-mini-transcribe) is the FINAL fallback so transcription
#     never hard-fails if the local model is missing or errors.
#
# The VPS platform overlay (platform/vps/ in this unified repo) does NOT bake
# a local model — it uses the cloud (Groq) config only. Keep these
# platform-correct: do not copy this local-model block into VPS config.
#
# OpenClaw schema (docs.openclaw.ai/gateway/config-tools, verified):
#   tools.media.audio = { enabled, maxBytes, models:[ ...entries ] }
#   The FIRST entry in models[] is primary; later entries are fallbacks.
#   CLI entry  : { type:"cli", command, args:[... "{{MediaPath}}"], timeoutSeconds }
#   Cloud entry: { provider, model }
#   {{MediaPath}} is substituted with the local audio file path at run time.
#   The CLI must exit 0 and print the transcript as PLAIN TEXT on stdout.
step "Step 8b: Configuring tiered Speech-to-Text (local faster-whisper 'medium' + OpenAI cloud fallback)"

# 8b.1 — Ensure a faster-whisper CLI is installed locally on this Mac.
# We standardize on a thin wrapper named `oc-faster-whisper` so the openclaw.json
# `command` is deterministic regardless of which underlying CLI shipped. The
# wrapper drives faster-whisper (via whisper-ctranslate2, the CTranslate2/
# faster-whisper engine) and prints the transcript text to stdout (model "medium").
OC_BIN_DIR="$OC_CONFIG/bin"
FW_WRAPPER="$OC_BIN_DIR/oc-faster-whisper"
mkdir -p "$OC_BIN_DIR"

install_faster_whisper() {
    # Already have a working faster-whisper engine CLI? Then we're done.
    if command -v whisper-ctranslate2 >/dev/null 2>&1 || command -v faster-whisper >/dev/null 2>&1; then
        note "faster-whisper engine CLI already present"
        return 0
    fi
    note "Installing faster-whisper locally (Apple Silicon, runs on the Neural Engine)…"
    # Preferred: uv tool install (isolated, fast). The whisper-ctranslate2 package
    # exposes the faster-whisper (CTranslate2) engine through a `whisper`-compatible
    # CLI and supports `--model medium`.
    if command -v uv >/dev/null 2>&1; then
        if uv tool install whisper-ctranslate2 2>&1 | tee -a "$LOG_FILE" | tail -3; then
            note "Installed faster-whisper via 'uv tool install whisper-ctranslate2'"
            return 0
        fi
        # Secondary uv attempt: the SYSTRAN faster-whisper library + faster-whisper-cli front-end.
        uv tool install faster-whisper-cli 2>&1 | tee -a "$LOG_FILE" | tail -3 && {
            note "Installed faster-whisper via 'uv tool install faster-whisper-cli'"; return 0; }
    fi
    # Fallback: pipx (also isolated).
    if command -v pipx >/dev/null 2>&1; then
        pipx install whisper-ctranslate2 2>&1 | tee -a "$LOG_FILE" | tail -3 && {
            note "Installed faster-whisper via 'pipx install whisper-ctranslate2'"; return 0; }
    fi
    # Last resort: pip3 --user.
    if command -v pip3 >/dev/null 2>&1; then
        pip3 install --user whisper-ctranslate2 2>&1 | tee -a "$LOG_FILE" | tail -3 && {
            note "Installed faster-whisper via 'pip3 install --user whisper-ctranslate2'"; return 0; }
    fi
    warn "Could not auto-install faster-whisper. Local transcription will fall back to OpenAI cloud."
    warn "To install manually: 'uv tool install whisper-ctranslate2' (or 'pipx install whisper-ctranslate2')."
    return 1
}
install_faster_whisper || true

# 8b.2 — Write the deterministic wrapper. It resolves whichever faster-whisper
# CLI is present, forces model "medium", and emits PLAIN TEXT on stdout (the form
# OpenClaw's CLI transcriber expects). Exits non-zero on failure so OpenClaw
# advances to the OpenAI cloud fallback entry.
cat > "$FW_WRAPPER" <<'WRAPEOF'
#!/usr/bin/env bash
# oc-faster-whisper — deterministic local transcription wrapper (model: medium).
# Usage: oc-faster-whisper <audio-file>
# Prints the transcript as plain text to stdout. Exit 0 on success.
# Drives the faster-whisper (CTranslate2) engine on Apple Silicon. Free + private.
set -euo pipefail
MEDIA="${1:?usage: oc-faster-whisper <audio-file>}"
MODEL="${OC_WHISPER_MODEL:-medium}"
# Surface common Homebrew + uv/pipx tool bins for non-login shells.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.openclaw/bin:$PATH"

if command -v whisper-ctranslate2 >/dev/null 2>&1; then
  TMPDIR_OUT="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR_OUT"' EXIT
  # CTranslate2/faster-whisper engine; write plain-text transcript, then cat it.
  whisper-ctranslate2 "$MEDIA" --model "$MODEL" --output_format txt \
    --output_dir "$TMPDIR_OUT" >/dev/null 2>&1
  TXT="$(find "$TMPDIR_OUT" -name '*.txt' | head -1)"
  [ -n "$TXT" ] && cat "$TXT" && exit 0
  exit 1
elif command -v faster-whisper >/dev/null 2>&1; then
  # faster-whisper-cli front-end prints transcript to stdout.
  faster-whisper --model "$MODEL" "$MEDIA"
  exit $?
else
  echo "oc-faster-whisper: no local faster-whisper CLI found" >&2
  exit 127
fi
WRAPEOF
chmod +x "$FW_WRAPPER"
note "Wrote local transcription wrapper: $FW_WRAPPER (model: medium)"

# ----------------------------------------------------------
# Step 8c: Harden Google Workspace (gws) credential resilience (fleet-wide)
# ----------------------------------------------------------
# Bakes in the guard against the v16.1.x gws SELF-WIPE: a bare `gws` run headless
# under the default OS "keyring" backend rewrites ~/.config/gws/credentials.enc
# to credential_source:"none" — erasing every account's OAuth. The hardener is
# idempotent + additive and (1) forces the FILE keyring backend for every shell
# via an append-only ~/.zshenv (+ ~/.bashrc, ~/.profile) managed block, (2)
# installs the `gws-as` PATH wrapper that forces the file backend for scripted/
# cron calls, and (3) writes an off-box encrypted snapshot of the default
# credential store so a wipe is always recoverable. Best-effort (never fatal);
# runs as the box user (the hardener refuses/re-drops if invoked as root).
_HARDEN_GWS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/harden-gws-credential-resilience.sh"
[ -f "$_HARDEN_GWS" ] || _HARDEN_GWS="$ONBOARDING_DIR/scripts/harden-gws-credential-resilience.sh"
[ -f "$_HARDEN_GWS" ] || _HARDEN_GWS="$SCRIPTS_DIR/harden-gws-credential-resilience.sh"
if [ -f "$_HARDEN_GWS" ]; then
    OC_CONFIG="$OC_CONFIG" bash "$_HARDEN_GWS" >> "$LOG_FILE" 2>&1 \
        && note "gws credential-resilience hardening ran (file keyring backend + gws-as wrapper + off-box backup)" \
        || note "gws credential-resilience hardening reported an issue (non-fatal; see $LOG_FILE)"
else
    note "harden-gws-credential-resilience.sh not found — skipping gws hardening (older bundle)"
fi

# 8b.3 — Bake tools.media.audio into openclaw.json (local primary + OpenAI fallback).
OPENCLAW_JSON="$OC_JSON"
if [ -f "$OPENCLAW_JSON" ]; then
    backup_config_file "$OPENCLAW_JSON"
    OPENCLAW_JSON="$OPENCLAW_JSON" FW_WRAPPER="$FW_WRAPPER" python3 << 'PYEOF'
import json, os, sys
path = os.environ['OPENCLAW_JSON']
wrapper = os.environ['FW_WRAPPER']
try:
    with open(path) as f:
        cfg = json.load(f)
    tools = cfg.setdefault('tools', {})
    media = tools.setdefault('media', {})
    # Mac-correct tiered transcription:
    #   1) LOCAL faster-whisper (model "medium") via the deterministic wrapper — primary.
    #   2) OpenAI cloud (gpt-4o-mini-transcribe) — FINAL fallback (never hard-fail).
    media['audio'] = {
        'enabled': True,
        'maxBytes': 26214400,  # 25MB — comfortably above OpenClaw's 20MB default
        'models': [
            {
                'type': 'cli',
                'command': wrapper,
                'args': ['{{MediaPath}}'],
                'timeoutSeconds': 300
            },
            {
                'provider': 'openai',
                'model': 'gpt-4o-mini-transcribe'
            }
        ]
    }
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)
    print("  ✓ tools.media.audio: LOCAL faster-whisper 'medium' (primary) → OpenAI cloud (fallback)")
except Exception as e:
    print(f"  ✗ Could not configure tools.media.audio: {e}", file=sys.stderr)
PYEOF
else
    note "openclaw.json not found - tiered STT config will apply on next run"
fi

# ----------------------------------------------------------
# Step 9: Setup Backup Folders
# ----------------------------------------------------------
step "Step 9: Setting Up Backup Folders"

mkdir -p "$OC_BACKUPS"
mkdir -p "$OC_DOWNLOADS/openclaw-master-files"
mkdir -p "$OC_DOWNLOADS/openclaw-master-files/coaching-personas/personas"
mkdir -p "$OC_DOWNLOADS/openclaw-master-files/project-prds"
# PRD 1.9: create the canonical zero-human-company root and drop the DO-NOT-DELETE marker.
mkdir -p "$OC_DOWNLOADS/openclaw-master-files/zero-human-company"
_DNDM="$OC_DOWNLOADS/openclaw-master-files/DO-NOT-DELETE.md"
if [ ! -f "$_DNDM" ] && [ -f "$SKILLS_DIR/shared-utils/DO-NOT-DELETE.md" ]; then
  cp "$SKILLS_DIR/shared-utils/DO-NOT-DELETE.md" "$_DNDM"
fi
unset _DNDM

success "Backup folders created at $OC_BACKUPS, master files at $OC_DOWNLOADS/openclaw-master-files"

# ----------------------------------------------------------
# Step 9a: EMBEDDING-PREVENTION BUNDLE item 8 — exclude the memory index cache
# from Time Machine (Mac only).
# ----------------------------------------------------------
# The OpenClaw memory index (~/.openclaw/memory) is a derived vector-DB cache:
# large, churns constantly (every reindex/embed rewrites it), and is fully
# rebuildable from MEMORY.md + the corpus. Letting Time Machine back it up wastes
# backup space and slows snapshots — and a restored stale index is exactly the
# kind of model-mismatched index this bundle exists to prevent. So we mark it as
# a Time Machine exclusion. Idempotent (tmutil addexclusion is a no-op if already
# excluded). Mac-only; best-effort (never fails the install).
if [ "$OC_PLATFORM" = "mac" ]; then
    step "Step 9a: Excluding memory index cache from Time Machine (~/.openclaw/memory)"
    _MEM_DIR="$HOME/.openclaw/memory"
    mkdir -p "$_MEM_DIR" 2>/dev/null || true
    if command -v tmutil >/dev/null 2>&1; then
        if tmutil addexclusion "$_MEM_DIR" >/dev/null 2>&1; then
            success "Time Machine exclusion set: $_MEM_DIR (derived index cache — rebuildable, not backed up)"
        else
            # Sticky (path-based) fallback when the volume-scoped form is unavailable.
            if tmutil addexclusion -p "$_MEM_DIR" >/dev/null 2>&1; then
                success "Time Machine sticky exclusion set: $_MEM_DIR"
            else
                note "tmutil addexclusion returned non-zero for $_MEM_DIR (Full Disk Access may be required) — harmless; index cache is rebuildable either way"
            fi
        fi
    else
        note "tmutil not available — skipping Time Machine exclusion (non-Mac or stripped environment)"
    fi
    unset _MEM_DIR
fi

send_telegram_progress "✓ Security + backups configured. Almost done — finalizing your agent's playbook now…"

# ----------------------------------------------------------
# Step 10: Write UPDATE PENDING Flag with 5-Phase Processing
# ----------------------------------------------------------
step "Step 10: Writing UPDATE PENDING Flag to AGENTS.md"

# Mac workspace resolver (v10.13.9 — Clawd is dead).
# OpenClaw agents read core .md files from agents.defaults.workspace OR a
# per-agent override at agents.list[*].workspace. Writing to the wrong path
# means the agent never sees the UPDATE PENDING flag (this was Floyd's bug
# AND a v10.13.8 Mac bug — install.sh wrote to ~/clawd, agent read from
# ~/.openclaw/workspace, install looked silently broken).
# Resolution priority:
#   1. agents.list[<main>].workspace (per-agent override — wins if set)
#   2. agents.defaults.workspace via `openclaw config get`
#   3. ~/.openclaw/workspace (canonical OpenClaw default — always)
# We DO NOT consider ~/clawd as a fallback anymore. If a client has stale
# data there from a pre-rename install, it stays inert. Step 10 also calls
# `openclaw config set agents.defaults.workspace` so the canonical path is
# explicit in openclaw.json from now on.
WORKSPACE_DIR=""

# Step 1: per-agent workspace override on the "main" agent
if [ -f "$OC_JSON" ]; then
    WORKSPACE_DIR=$(python3 -c "
import json
try:
    cfg=json.load(open('$OC_JSON'))
    for ag in cfg.get('agents',{}).get('list',[]) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                import os; print(os.path.expanduser(ws)); break
except Exception: pass
" 2>/dev/null)
fi

# Step 2: agents.defaults.workspace via CLI
# v10.13.8 (P0 from a Mac v10.13.6 install): `openclaw config get
# agents.defaults.workspace` exits NON-ZERO on a fresh install where the
# key has never been set. With `set -euo pipefail` at line 2, this kills
# the whole install silently. The observed symptom: install reached the
# Step 10 banner via Telegram progress, then no more messages — script
# died here. Fix: wrap the pipeline-bearing command substitution with
# `|| WORKSPACE_DIR=""` so a non-zero exit becomes an empty string and
# the disk fallback below takes over. Matches the protection pattern at
# line 508/510 (config get with `|| true`).
if [ -z "$WORKSPACE_DIR" ] && command -v openclaw >/dev/null 2>&1; then
    WORKSPACE_DIR=$(openclaw config get agents.defaults.workspace 2>/dev/null \
        | head -1 | python3 -c "
import sys, json, os
try:
    raw = sys.stdin.read().strip()
    if raw.startswith('\"'): print(os.path.expanduser(json.loads(raw)))
    else: print(os.path.expanduser(raw))
except Exception: pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi

# Step 3: disk fallback. v10.13.9 (Mac path bug): the previous code preferred
# ~/clawd if it existed because some clients still had that directory from the
# Clawd→OpenClaw rename. That made install.sh write UPDATE PENDING to
# ~/clawd/AGENTS.md while the agent reads from ~/.openclaw/workspace/AGENTS.md
# (OpenClaw's documented default). Result: install completes, agent never sees
# the flag, looks like the install silently failed.
#
# Clawd is DEAD. We always default to ~/.openclaw/workspace. The clawd
# directory existing on disk is no longer a signal to write there — if it's
# there at all, it's leftover from a pre-rename install and should be ignored.
WORKSPACE_DIR="${WORKSPACE_DIR:-$OC_WORKSPACE_DEFAULT}"
if [ ! -d "$WORKSPACE_DIR" ]; then
    WORKSPACE_DIR="$OC_WORKSPACE_DEFAULT"
fi

# v10.13.9: also explicitly set agents.defaults.workspace so future installs
# (and the agent itself when it reads its own config) confirm the canonical
# path. Without this, the resolver would re-discover from disk fallback every
# time, and clients with stale ~/clawd directories would keep getting their
# UPDATE PENDING flag written to the wrong file.
if command -v openclaw >/dev/null 2>&1; then
    openclaw config set agents.defaults.workspace "$WORKSPACE_DIR" 2>/dev/null || true
fi

mkdir -p "$WORKSPACE_DIR"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
note "Agent workspace resolved: $WORKSPACE_DIR (UPDATE PENDING flag goes into $AGENTS_FILE)"

# Remove existing flags
touch "$AGENTS_FILE"
# FIX 1 (v10.15.48): FULLY strip prior UPDATE/ONBOARDING PENDING/COMPLETE
# SECTIONS (header → next "## " or EOF), not just the single header line. The
# old line-only `grep -v` left multi-line bodies behind and STACKED a fresh full
# flag on every install — duplicate flags accreted forever.
AGENTS_FILE="$AGENTS_FILE" python3 - <<'PYEOF' 2>/dev/null || true
import os, re
p = os.environ["AGENTS_FILE"]
try:
    text = open(p, encoding="utf-8", errors="replace").read()
except Exception:
    text = ""
pattern = re.compile(
    r'(?m)^##[^\n]*(?:UPDATE PENDING|ONBOARDING PENDING|ONBOARDING COMPLETE)[^\n]*\n'
    r'(?:(?!^##\s).*\n?)*',
)
new = re.sub(r'\n{3,}', '\n\n', pattern.sub("", text))
open(p, "w", encoding="utf-8").write(new)
PYEOF

# FIX 1 (PRD 2.1 / v10.16.48): seed the per-skill onboarding STATE FILE
# (.onboarding-state.json) with every non-archived skill at "pending". The agent
# (and the onboarding-resume cron) drive each skill to qc-passed; "done" is the
# verification gate, never this prose. Idempotent — re-seeding preserves status.
# Canonical lib: lib-onboarding-state.sh (sourced at top of install.sh).
# scripts/onboarding-state.sh is a compat shim that sources the canonical.
if command -v oc_state_seed >/dev/null 2>&1; then
    # SIGNATURE: oc_state_seed <src_skills_dir> [version]  (lib-onboarding-state.sh).
    # v17.0.21 FIX: args were REVERSED here — the version string ("v17.0.x") was
    # passed as <src_skills_dir>, so the install-time seed pointed at a non-existent
    # directory and discovered ZERO numbered skills (silent no-op; the roll-time
    # obs_* seed + resume cron then had to do all the work). Correct order below.
    SKILLS_DIR="$SKILLS_DIR" oc_state_seed "$SKILLS_DIR" "$ONBOARDING_VERSION" \
        && success "Onboarding state seeded → (every skill pending; gate drives to qc-passed)" \
        || warn "oc_state_seed reported an issue (install continues)"
elif [ -f "$ONBOARDING_DIR/scripts/onboarding-state.sh" ]; then
    # Fallback for older bundles without lib-onboarding-state.sh at root.
    # shellcheck disable=SC1091
    SKILLS_DIR="$SKILLS_DIR" source "$ONBOARDING_DIR/scripts/onboarding-state.sh"
    obs_seed_state "$ONBOARDING_VERSION" "$SKILLS_DIR" \
        && success "Onboarding state seeded (compat shim) → $OBS_STATE_FILE" \
        || warn "onboarding-state seed reported an issue (install continues)"
else
    warn "lib-onboarding-state.sh not found — honesty state machine not seeded (older bundle?)"
fi

# ── Seed nudge lifecycle state file (idempotent; reset on fresh install) ─────
# The nudge state file lives at $WS/.onboarding-nudge-state (plain key=value).
# Seeded fresh here so a clean install starts from attempt 0, not dormant.
# Re-running install (update/resume) does NOT reset it — if we're mid-lifecycle
# we want to preserve the current attempt count and dormant flag.
_NUDGE_STATE_FILE="$OC_CONFIG/workspace/.onboarding-nudge-state"
if [ ! -f "$_NUDGE_STATE_FILE" ]; then
    mkdir -p "$OC_CONFIG/workspace" 2>/dev/null || true
    printf 'nudge_attempts=0\nlast_nudge_ts=0\ndormant=false\ncredit_fail_ts=0\ncredit_notified=false\n' \
        > "$_NUDGE_STATE_FILE" 2>/dev/null \
        && success "Nudge lifecycle state initialized → $_NUDGE_STATE_FILE" \
        || warn "Could not write nudge state file (non-fatal)"
else
    success "Nudge lifecycle state already exists → $_NUDGE_STATE_FILE (preserved)"
fi

# v10.5.4 Tier-3 fallback: also write the payload to a standalone file so the
# operator can recover with `cat`+paste even if both Telegram fails AND the
# AGENTS.md append fails. Single source of truth via tee — same bytes go to
# both files.
UPDATE_PENDING_FILE="$ONBOARDING_DIR/UPDATE-PENDING.md"

cat << 'FLAGCONTENT' | tee "$UPDATE_PENDING_FILE" >> "$AGENTS_FILE"

## UPDATE PENDING - Skills Activation Required

A system update was installed. Read the instructions below and activate each skill.
When the verification gate passes, remove this section from AGENTS.md.

---

### 🔴 SOURCE OF TRUTH RULE

**When skill instructions conflict with generic OpenClaw docs, skill files ALWAYS win:**
- SKILL.md > OpenClaw docs
- CORE_UPDATES.md > TYP storage rules
- INSTALL.md > generic install patterns
- Skill examples > your assumptions

---

### 🔴 GHL ALIAS AWARENESS (BINDING — APPLIES TO EVERY GHL-RELATED TASK)

All of these refer to **the same single platform**. Treat them as 100% synonymous in every context — credentials, API calls, MCP routing, documentation, conversation with the owner:

- **GHL**
- **GoHighLevel**
- **Go High Level** (two words)
- **HighLevel** / **High Level**
- **Convert and Flow** (this owner's white-label brand)
- **LeadConnector** / **leadconnectorhq.com** (their API host domain)
- **CnF** (abbreviation)

When the owner says any of these names, they mean the same system. The same Private Integration Token, the same Location ID, the same MCPs (`ghl-mcp` and `ghl-community-mcp`), the same skill 36, the same skill 35, the same skill 29.

**GHL DOES NOT USE API KEYS.** They were deprecated ~2 years ago. GHL uses **Private Integration Tokens (PITs)**. The env variable named `GOHIGHLEVEL_API_KEY` in this system is a legacy variable name — its value is a PIT, not an API key. Never tell the owner they need an "API key" for GHL — they need a Private Integration Token (PIT). Get it from Settings → Integrations → Private Integrations.

---

### 🔴 5-PHASE PROCESSING ORDER (MANDATORY)

**Phase A: Parallel Install — dependency-aware waves (Timeout: 1800s / 30 minutes per wave)**

The 56 active skills install in 5 dependency-aware waves, not by number order.
Sub-agents within a wave run in parallel (up to maxConcurrent in openclaw.json).
A wave cannot start until the previous wave's QC has all skills at 8.5+.

**Wave 1 — FOUNDATION (sequential, must finish before Wave 2 starts):**
- 01-teach-yourself-protocol  (REQUIRED — every other skill depends on TYP)
- 02-back-yourself-up-protocol  (REQUIRED — config backup before any other skill modifies config)

**Wave 2 — INDEPENDENT INTEGRATIONS (parallel, up to 20 sub-agents per maxChildrenPerAgent — 10 skills in this wave):**
- 03-agent-browser
- 04-superpowers
- 05-ghl-setup
- 06-ghl-install-pages
- 07-kie-setup
- 08-vercel-setup
- 09-context7
- 10-github-setup
- 12-openrouter-setup
- 14-google-workspace-integration

**Wave 3 — CONTENT + SERVICE TOOLS (parallel, up to 20 sub-agents — 14 skills in this wave, all within the maxChildrenPerAgent cap):**
- 15-blackceo-team-management
- 16-summarize-youtube
- 17-self-improving-agent
- 18-proactive-agent
- 19-humanizer
- 20-youtube-watcher
- 24-storyboard-writer
- 25-video-creator
- 26-caption-creator
- 27-video-editor
- 28-cinematic-forge
- 29-ghl-convert-and-flow
- 30-fish-audio-api-reference
- 43-graphify-knowledge-graph  (maps the client's OWN workforce/code with the CLIENT'S OWN model; semantic pass owner-triggered, AST hook free/automatic — see skill INSTALL.md)

**Wave 4 — INFRASTRUCTURE (sequential — Memory, then MCP, then Command Center):**
- 31-upgraded-memory-system  (memory architecture must be ready before persona/CC)
- 36-ghl-mcp-setup  (MCP layer for GHL — needed by Skill 35 and Command Center)

**Wave 5 — USER-INTERACTION-AWARE SUB-AGENT DISPATCH (sequential — N22 surfaces interview/decision steps; N2 keeps the orchestrator out of the install work):**
- 22-book-to-persona-coaching-leadership-system  (needs Memory from Wave 4 — dispatch sub-agent)
- 23-ai-workforce-blueprint  (depends on Skill 22 persona index — triple-fire trigger surfaces the owner interview prompt, then dispatch sub-agent)
- 32-command-center-setup  (needs ORG-CHART from Skill 23 — dispatch sub-agent)
- 35-social-media-planner  (needs Persona, Memory, MCP — dispatch sub-agent; MCP-first routing via Skill 36)

N2 ENFORCEMENT: These four skills install via SUB-AGENTS like every other skill. The orchestrator coordinates the wait/dispatch handoff via the triple-fire trigger (N22) for user-interaction steps, then dispatches the install sub-agent. Concurrency cap stays Mac=10 / VPS=5 (these dispatch one at a time, well under cap). NO orchestrator-direct installation.

**Wave 1 + 4 + 5 are sequential. Waves 2 + 3 are massively parallel.**

### 🔴🔴🔴 NO-SHORTCUT RULE FOR EVERY SUB-AGENT (HARD ENFORCEMENT)

Every sub-agent installing a skill MUST read ALL files in that skill's folder BEFORE running any execution step. This is non-negotiable. Skill installs that skip the read step routinely write the wrong content to AGENTS.md/MEMORY.md, miss required env vars, install the wrong dependency versions, or skip CORE_UPDATES.md entirely.

**REQUIRED FILES (per skill, every sub-agent reads each one fully, top to bottom, BEFORE any execution):**

1. `SKILL.md` — what this skill does, prerequisites, model requirements
2. `INSTALL.md` — the actual install steps (read FULLY before executing ANY step)
3. `INSTRUCTIONS.md` — runtime behavior + how the agent uses the skill at runtime
4. `CORE_UPDATES.md` — what gets added to AGENTS.md / MEMORY.md / TOOLS.md / IDENTITY.md / SOUL.md (this file is non-optional — skipping it leaves the agent unable to use the skill)
5. `EXAMPLES.md` — concrete usage examples (if present)
6. `QC.md` — the install verification checklist (every item must pass after install)
7. `CHANGELOG.md` — version history (if present)
8. Any `*-full.md` master reference document
9. Any `references/*.md` subdirectory files (e.g. Skill 29 has 12 reference files — every single one must be read)
10. Any `agent-prompts/*.md` (Skill 22 has these for each pipeline phase)
11. Any `pipeline/*.md` or `PIPELINE.md`
12. Any `CHECKLIST.md`, `PERSONA-ROUTER.md`, `GEMINI-RETRIEVAL-GUIDE.md`, `GOOD-AND-BAD-EXAMPLES.md` etc — skill-specific docs are NOT optional

**MANDATORY VERIFICATION STEP (sub-agent runs this BEFORE any install command):**

```bash
# List every .md file in the skill folder + every reference subdirectory
SKILL_DIR="$HOME/.openclaw/skills/<skill-folder>"
find "$SKILL_DIR" -type f \( -name "*.md" -o -name "*.skill" \) | sort
```

The sub-agent MUST report back to the master orchestrator a structured read-log BEFORE any install step runs:

```
Skill: <skill-folder-name>
Files read in this session (full read, top to bottom):
- SKILL.md (read at HH:MM:SS, N bytes)
- INSTALL.md (read at HH:MM:SS, N bytes)
- INSTRUCTIONS.md (read at HH:MM:SS, N bytes)
- CORE_UPDATES.md (read at HH:MM:SS, N bytes)
- [every other .md / reference file in the skill folder]
Total files read: N
Total files in skill folder: N
Coverage: 100%
```

**Coverage MUST be 100%. If not, the sub-agent STOPS, requests permission to continue, and identifies which files were missed and why.**

**REFUSAL PATTERN (built into every sub-agent's bootstrap):**

If a sub-agent is asked to "install skill X quickly" or "skip the docs" or "you already know how this works":

> "I cannot install this skill without first reading every file in the skill folder. Skipping reads causes incorrect AGENTS.md/MEMORY.md updates, missed dependencies, and silent install failures (see INSTALL-CONTRACT.md Rule 7). Reading the files takes 2-5 minutes; cleaning up a broken install takes 30+ minutes. I'm reading the files now."

**MASTER ORCHESTRATOR CHECK (after sub-agent reports complete):**

Before marking the skill as installed, the master orchestrator validates the sub-agent's read-log by independently listing the same files and confirming the count matches:

```bash
# Master runs this to verify the sub-agent didn't lie about coverage
EXPECTED=$(find "$HOME/.openclaw/skills/<skill-folder>" -type f \( -name "*.md" -o -name "*.skill" \) | wc -l)
REPORTED=<count from sub-agent's read-log>
[ "$EXPECTED" = "$REPORTED" ] || error "Sub-agent skipped files"
```

If the counts don't match, the install for that skill is marked FAILED and the sub-agent is asked to read the missing files before any further execution.

### Sub-agent retry policy (per INSTALL-CONTRACT.md Rule 6)
1. Retry once with same model on failure
2. Retry with next fallback model
3. Escalate to master orchestrator

Gateway-restart guard (per INSTALL-CONTRACT.md Rule 5):
- ONLY the master orchestrator calls `openclaw gateway restart`
- Master MUST run `openclaw subagents list` and confirm empty BEFORE restart
- Never restart in the middle of a wave

**Phase B: Foundation (Timeout: 2700s / 45 minutes)**
- Configure memory architecture (all 8 layers)
- Verify Active Memory (Layer 8) is enabled
- Set up persona system
- Initialize Gemini Engine indexing
- Verify credential sync across all locations

**Phase C: Interactive (Timeout: 3600s / 60 minutes per sub-agent — Book-to-Persona phases can take this long with large books)**
- Run AI Workforce Interview (if needed)
- Generate company departments and ORG-CHART
- Dispatch Skill 23 sub-agent (AI Workforce Blueprint) — N22 surfaces interview prompts, sub-agent does the work (N2)
- Dispatch Skill 22 sub-agent (Book-to-Persona) — orchestrator coordinates; sub-agent runs the pipeline (N2)
  - Each phase sub-agent (Extraction, Analysis, Synthesis) gets 60 min
  - With 20+ books and 3 phases each, total wall time can run 1.5-3 hours
  - DO NOT timeout a Book-to-Persona phase under 30 min

**Phase D: Ready but Waiting (Timeout: 3600s / 60 minutes)**
- Validate all skill installations
- Run QC checks on critical skills
- Verify sub-agent spawning works
- Test Telegram notifications

**Phase E: QC (No timeout - complete verification)**
- Full system verification
- Memory layer integrity check
- Persona routing validation
- Document completion in MEMORY.md

---

### 🔴 CRITICAL RULES

**Skills 22-23: USER-INTERACTION-AWARE SUB-AGENT DISPATCH (N2 + N22)**
- DISPATCH SUB-AGENTS — orchestrator does NOT install personally (N2)
- User-interaction steps surface via the triple-fire trigger (N22): Telegram + AGENTS.md flag + terminal block
- Sequential, not parallel: Skill 22 must complete + QC-pass before Skill 23 dispatches

**Memory Architecture - ALL 8 LAYERS REQUIRED:**
1. Markdown files (AGENTS.md, MEMORY.md, etc.)
2. Memory flush system
3. Session indexing
4. Gemini Embedding 2
5. memory-core (active memory)
6. Cognee
7. Obsidian Vault
8. Wiki System

**DREAMS.md IS REQUIRED** - Must exist in workspace root.

**Timeout References (v9.7.8 — 30-60 min minimums for heavy-reasoning sub-agents):**
- Phase A: 1800s (30 min per wave)
- Phase B: 2700s (45 min)
- Phase C: 3600s (60 min — Book-to-Persona-aware; heavy-reasoning phases need this)
- Phase D: 3600s (60 min)
- Phase E: No timeout

**Sub-agent timeout floor (binding):**
- ANY sub-agent spawned for heavy-reasoning work (Skill 22 phases, Skill 23 interview, persona synthesis, complex analysis) must have timeout ≥ 1800s (30 min). 60 min preferred.
- Mid-tier sub-agents (creative, routine): min 600s (10 min).
- Fast/bulk sub-agents: min 300s (5 min).
- The maxConcurrent=100 ceiling protects against runaway parallel spawn; per-spawn timeout protects each one from premature kill.

---

### 🔴 STEP-BY-STEP EXECUTION

**STEP 1: SEARCH FOR EXISTING DATA**
Check for existing interview data:
- workforce-interview-answers.md
- interview-handoff.md
- company-config.json
- departments.json
- ORG-CHART.md
- departments/ folder
- company-discovery/ folder

**STEP 2: DETERMINE INTERVIEW STATE**
- **STATE A - NEVER STARTED**: No evidence found → Conduct full AI Workforce Interview
- **STATE B - IN PROGRESS**: workforce-interview-answers.md exists, no departments/ → Complete interview
- **STATE C - COMPLETE**: departments/ exists, ORG-CHART.md exists → Process all skills normally

**STEP 3: PROCESS ALL SKILLS**
For EACH skill folder in ~/.openclaw/skills/:
1. Read SKILL.md completely
2. Read INSTALL.md, follow all setup steps
3. Read QC.md, run all verification checks
4. Read CORE_UPDATES.md, surgically update core files
5. **ACTIVATE ALL SKILLS** - do not skip any

**Skills requiring special handling:**
- Skill 22: Book-to-Persona (main orchestrator only)
- Skill 23: AI Workforce Blueprint (main orchestrator only, check interview state first)
- Skill 35: Social Media Planner (requires Skills 22, 31; Skill 30 / Fish Audio is OPTIONAL — enables podcast voiceover only)

**STEP 4: VERIFY MEMORY ARCHITECTURE**
```
python3 ~/.openclaw/scripts/gemini-indexer.py --status
# Check DREAMS.md exists in workspace root
# Check memory-core is configured
# Check Obsidian Vault path is set
# Check Active Memory (Layer 8) is enabled in plugins.entries.active-memory
```

**STEP 5: VERIFY PERSONA SYSTEM**
- coaching-personas/ folder exists with persona files
- persona-categories.json exists
- PERSONA-ROUTER.md exists
- Gemini Engine indexed coaching-personas collection

**STEP 6: CLEAN UP openclaw.json**
- Remove deprecated model IDs
- Ensure subagent config under agents.defaults.subagents
- Verify tools.exec has security=full, ask=off (TOP-LEVEL only — agents.defaults.tools.exec is INVALID on 2026.6.1+)
- Verify agents.defaults.subagents.allowAgents=["*"] (spawned sub-agents fully permitted)

**STEP 7: SURGICAL CORE FILE UPDATES**
For each skill's CORE_UPDATES.md:
- Add entries that don't exist
- Update entries that have changed
- Remove outdated entries
- Do NOT duplicate
- Do NOT touch personal content
- Use skill headers: "### [Skill Name] (Skill [Number])"

The \`wire_core_updates()\` function in \`update-skills.sh\` (v12.3.11+) runs a format-robust
parser that recognises ALL header conventions present in the repo — including em-dash
(## X.md — UPDATE REQUIRED), bracket h2/h3 (## [ADD TO X.md] / ### [ADD TO X.md]),
bold-bracket (**[ADD TO X.md]**), plain h3 under "Suggested snippets" (### X.md),
verb-first (## Add to X.md), paren-suffix (## X.md (append)), mixed-suffix
(## X.md Addition / ## X.md Update), and bare-filename h2 (## X.md). It targets all six
core files: AGENTS.md, TOOLS.md, MEMORY.md, SOUL.md, IDENTITY.md, USER.md. Every appended
block is wrapped in <!-- BEGIN skill:<folder>:<target> --> / <!-- END ... --> markers for
idempotent re-runs. Every shipping skill MUST stamp the sentinel
\`<!-- skill:<folder>:core-update-applied -->\` in AGENTS.md (the VERIFICATION GATE checks
for its presence). The parser stamps the sentinel unconditionally — even for all-skip-section
skills — so the gate always passes when the merger ran.

**STEP 8: VERIFICATION GATE — THE ONLY DEFINITION OF “DONE”**
This onboarding is NOT complete until the GATE passes. Files on disk = DOWNLOADED, never “installed”. Source the gate and evaluate state:
- State file: \`~/.openclaw/workspace/.onboarding-state.json\` (per-skill: pending → downloaded → wired → qc-passed | qc-failed)
- Gate library: \`lib-onboarding-state.sh\` (repo root, canonical) or compat shim at \`scripts/onboarding-state.sh\`
- Run: source the library, then \`obs_gate_summary\`. A skill counts INSTALLED only when (a) \`openclaw skills info <name>\` shows it, (b) its CORE_UPDATES sentinel is present (if it ships CORE_UPDATES.md), and (c) its \`qc-*.sh\` exits 0 (if it ships one).
- **NEVER tell the owner “installed / done / onboarded” for any skill that is not \`qc-passed\`** (or a legitimate INTERVIEW_PENDING park — re-ping the owner on backoff; that is NOT terminal “done”).
- Onboarding is “complete” ONLY when every non-archived skill is \`qc-passed\` (or explicitly INTERVIEW_PENDING) AND closeout (Skill 37) has fired where applicable.

**STEP 8b: REPORT TO OWNER (HONESTLY)**
- If the gate PASSES: "All skills verified-installed ([X]/[Y]). Memory layers verified. Interview state: [A/B/C]."
- If the gate does NOT pass yet: report the TRUTH — "[X]/[Y] skills verified-installed, [Z] still being activated: <list>. I'll keep going and confirm when every one passes." The \`onboarding-resume\` cron also re-fires activation + QC until all pass.

**STEP 9: CLEAN UP — ONLY AFTER THE GATE PASSES**
- Do NOT remove this flag until \`obs_gate_summary\` returns success.
- Then remove this entire UPDATE PENDING section from AGENTS.md
- Add to MEMORY.md under "## System Updates":
  "[DATE]: Install ${ONBOARDING_VERSION}. Verification gate PASSED — [X] skills verified-installed. All 8 memory layers verified."

---

## 🛠️ If This Install Had Errors — Self-Healing Guide

If the operator reports Telegram/cron didn't work during install, or you see
"scope upgrade pending approval" errors in the install log, the CLI device
is missing operator.write/admin scopes. Here's how to fix it:

### Quick diagnostic
```bash
openclaw gateway status --verbose | grep "Capability:"
```
- `admin-capable` or `write-capable` = healthy
- `read-only` = CLI device is missing write scope (this is the bug)

### Auto-repair (one command)
The install.sh has an `auto_repair_cli_scopes` function that handles this.
Just re-run the install — it detects the read-only state and repairs it:
```bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

### Manual repair (if auto-repair didn't work)
1. Back up paired.json:
   ```bash
   cp ~/.openclaw/devices/paired.json ~/.openclaw/devices/paired.json.bak
   ```
2. Edit ~/.openclaw/devices/paired.json — find the entry where
   `clientId == "cli"` and add `operator.write` + `operator.admin` to:
   - `scopes` array
   - `approvedScopes` array
   - `tokens.operator.scopes` array
3. Clear pending: `echo '{}' > ~/.openclaw/devices/pending.json`
4. Restart: `openclaw gateway restart`
5. Verify: `openclaw gateway status --verbose | grep "Capability:"` should now show admin-capable

### Documentation
- Operator scopes: https://docs.openclaw.ai/gateway/operator-scopes
- Device management: https://docs.openclaw.ai/cli/devices
- Troubleshooting: https://docs.openclaw.ai/gateway/troubleshooting

---
FLAGCONTENT

# v9.7.9: Read-back verification. Don't just trust the heredoc — actually
# confirm the flag is in the file. If not, surface a HARD ERROR so the user
# knows it didn't land instead of being told everything worked.
if grep -q "UPDATE PENDING" "$AGENTS_FILE" 2>/dev/null; then
    AGENTS_SIZE=$(wc -c < "$AGENTS_FILE" 2>/dev/null | tr -d ' ')
    success "UPDATE PENDING flag written to $AGENTS_FILE (file is now $AGENTS_SIZE bytes)"
    note "Verify your AGENT reads from $AGENTS_FILE. If it reads a DIFFERENT path, the flag is invisible to it."
    note "Quick test: ask your agent 'What is the size of your AGENTS.md and what's the last section?' — should report $AGENTS_SIZE bytes ending with 'UPDATE PENDING' section."
    note "Tier-3 backup: identical payload also saved to $UPDATE_PENDING_FILE — use for cat+paste recovery if AGENTS.md is ever wrong."

    # v10.13.5: Fire the Telegram kickoff message NOW — the moment the
    # UPDATE PENDING flag is verified. Owner can paste the block as soon as
    # install.sh's stdout reaches its final scissor-lines (Steps 10b/11/12
    # remaining are housekeeping; the bot is already functionally ready).
    # Previously the kickoff fired at the very end which left the owner
    # waiting 30-90 extra seconds with no idea what to do.
    if send_kickoff_telegram; then
        success "Kickoff message sent to your phone (via ${KICKOFF_TG_PATH:-?}). Check your Telegram for what to do next."
    else
        warn "Kickoff Telegram message could not be sent right now — will retry at end of install. The same instructions will appear in this terminal too."
    fi
else
    error "AGENTS.md write FAILED — flag NOT present in $AGENTS_FILE after write."
    error "File exists: $([ -f "$AGENTS_FILE" ] && echo yes || echo NO)"
    error "File size: $(wc -c < "$AGENTS_FILE" 2>/dev/null | tr -d ' ') bytes"
    error "RECOVERY: the full UPDATE PENDING payload was ALSO saved to $UPDATE_PENDING_FILE."
    error "  To paste manually:  cat \"$UPDATE_PENDING_FILE\" | pbcopy   (then paste into your agent)"
    error "  Or send via gateway: openclaw message send --channel telegram --message \"\$(cat \"$UPDATE_PENDING_FILE\")\""
    error "Please report with this log: $LOG_FILE"
fi

# ----------------------------------------------------------
# Step 10a: Shared core-file unification (Zero-Human-Workforce file model)
# Now that the workspace is resolved + the bootstrap files exist in
# CANON_DIR ($WORKSPACE_DIR), symlink every agent/sub-agent's AGENTS.md /
# TOOLS.md / USER.md to THIS box's own canonical. Per-agent IDENTITY/SOUL/
# MEMORY/HEARTBEAT stay each agent's own. Nested workflow agents exempt. Idempotent.
# CANON_DIR is THIS box's own workspace (co-mingling guard) — passed explicitly
# as the resolved $WORKSPACE_DIR so it matches the path the agent actually reads.
# ----------------------------------------------------------
step "Step 10a: Unifying shared core files (AGENTS/TOOLS/USER symlinked to this box's canonical)"
link_shared_core_files "$WORKSPACE_DIR" || warn "link_shared_core_files reported warnings (install continues)"

# ----------------------------------------------------------
# Step 10b: Seed Core.md Terminology into MEMORY.md (idempotent)
# ----------------------------------------------------------
step "Step 10b: Seeding Core.md terminology in MEMORY.md"

MEMORY_FILE="$WORKSPACE_DIR/MEMORY.md"
touch "$MEMORY_FILE"

if ! grep -q "## Terminology — Core.md Files" "$MEMORY_FILE" 2>/dev/null; then
  cat >> "$MEMORY_FILE" << 'COREMDEOF'

## Terminology — Core.md Files

When the owner says **"Core.md files"** they mean the OpenClaw bootstrap files loaded every session — not a literal file called `core.md`. The Core.md files are:

- **IDENTITY.md** — the role the agent is playing. It contains the **experiences and the skills they need to embody** that role. Not just surface metadata (name / vibe / emoji) — the lived background and capability set of the character being played.
- **SOUL.md** — the **personality** of the agent, its **true mission**, its **beliefs**, its **rules**, its **goals**, its **belief systems**, its **principles**. Who the agent IS, not who they are playing. First file injected each session.
- **AGENTS.md** — operating procedures, protocols, workflows, memory rules. *What the agent does and how*
- **USER.md** — the human being helped (name, timezone, preferences, communication style)
- **TOOLS.md** — local tool notes and conventions (camera names, SSH aliases, environment-specific specifics) — NOT a permissions registry
- **MEMORY.md** — curated long-term durable facts, decisions, preferences. Loaded in main private sessions; paired with daily logs at `memory/YYYY-MM-DD.md`

When the owner says "update the Core.md files" or "this needs to live in the Core.md files," choose the right one of these six based on its purpose:
- Personality / principle → SOUL.md
- Procedure / workflow → AGENTS.md
- Tool note → TOOLS.md
- Durable fact / decision → MEMORY.md
- User info → USER.md
- Identity metadata → IDENTITY.md

Never interpret "Core.md" as a literal filename.

COREMDEOF
  success "Core.md terminology seeded into MEMORY.md"
else
  note "Core.md terminology already present in MEMORY.md — skipped"
fi

# ----------------------------------------------------------
# Step 11: Generate Manifest
# ----------------------------------------------------------
send_telegram_progress "✓ Memory + playbook seeded. Generating your skill manifest now — last few steps…"
step "Step 11: Generating Skill Manifest"

MANIFEST_PATH="$SKILLS_DIR/.skill-manifest.json"

echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"

python3 -c "
import os, json
from datetime import datetime, timezone

skills_dir = '$SKILLS_DIR'
manifest = {
    'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'onboardingVersion': '$ONBOARDING_VERSION',
    'skills': {}
}

for entry in sorted(os.listdir(skills_dir)):
    full = os.path.join(skills_dir, entry)
    if not os.path.isdir(full):
        continue
    if not entry[0].isdigit():
        continue
    ver_file = os.path.join(full, 'skill-version.txt')
    if os.path.isfile(ver_file):
        with open(ver_file) as f:
            ver = f.read().strip()
    else:
        ver = 'unknown'
    manifest['skills'][entry] = ver

with open('$MANIFEST_PATH', 'w') as f:
    json.dump(manifest, f, indent=2)

print(f'  ✓ Manifest: {len(manifest[\"skills\"])} skills recorded')
" 2>/dev/null || warn "Could not generate skill manifest"

# ----------------------------------------------------------
# Completion
# ----------------------------------------------------------
step "Installation Complete"

count_installed=$(count_list "$SKILLS_INSTALLED")

success "OpenClaw Onboarding ${ONBOARDING_VERSION} installed"
success "$count_installed skills processed"
success "Log saved to: $LOG_FILE"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║           NEXT STEPS                     ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  1. Gateway restart will now begin..."
echo "  2. Wait for gateway to come back online"
echo "  3. Process the UPDATE PENDING section"
echo "     in your AGENTS.md file"
echo "  4. Follow the 5-Phase Processing Order"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Send completion notification BEFORE gateway restart (so the gateway is still up to deliver it).
# The body contains paste-ready instructions in case the agent's session loses context during restart.
send_telegram_progress "✅ OpenClaw Onboarding ${ONBOARDING_VERSION} install complete.

📦 ${count_installed} skills processed.
⏳ Gateway restart starting now — agent will be unavailable for ~30 seconds.

When the gateway is back, paste this to your agent:

▶ \"I just ran the OpenClaw onboarding install. There is an UPDATE PENDING flag at the top of my AGENTS.md. Please follow the 5-Phase Processing Order in that flag to activate all skills. Start with Phase A (parallel install in waves). Do not skip any phase. Run QC after each skill. Send me a summary when complete.\"

(If you did not receive THIS Telegram note, see the same instructions printed in your Terminal where you ran the install command.)"

# v9.7.9: Echo Telegram result with EXPLICIT delivery caveat. Important on
# fresh-install machines where the openclaw.json has a chat ID but the bot
# itself may not be the one the owner has a conversation with on their phone.
# `openclaw message send` returns success when the gateway accepts the message
# — but if the bot token differs from the one your phone messages, the note
# goes to a different Telegram account.
case "$TELEGRAM_LAST_RESULT" in
    sent:*)
        success "Telegram completion note sent to chat ID ${TELEGRAM_LAST_RESULT#sent:}"
        note "IF you didn't actually receive it in Telegram on your phone:"
        note "  This machine's bot may not be the bot you message from your phone."
        note "  - Open Telegram on phone. Search for the BlackCEO / OpenClaw bot you use."
        note "  - Look for a Telegram message arriving right now from any bot."
        note "  - If nothing arrived, this machine has its own bot you haven't opened a chat with."
        note "  Read the backup instruction box below — agent will activate from there."
        ;;
    no-openclaw-cli)     warn "Telegram skipped — openclaw CLI not on PATH yet (first-install case)" ;;
    no-telegram-target)  warn "Telegram skipped — no telegram chat ID found anywhere in openclaw.json" ;;
    failed:*)            warn "Telegram completion note FAILED — using backup instructions below" ;;
esac

# Always print the backup instructions block to terminal — no client gets stranded.
# Unquoted heredoc so $UPDATE_PENDING_FILE expands to the real path.
cat <<BACKUP_BLOCK

╔════════════════════════════════════════════════════════════════════╗
║  TIER 2 — IF YOU DID NOT GET A TELEGRAM NOTE                       ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  After the gateway restart completes (about 30 seconds), open      ║
║  whatever you use to talk to your OpenClaw agent (Telegram,        ║
║  web UI, terminal chat — whatever you have set up).                ║
║                                                                    ║
║  Paste this EXACT message to your agent (copy from between the     ║
║  >>> and <<< markers):                                             ║
║                                                                    ║
║  >>>                                                               ║
║  I just ran the OpenClaw onboarding install. There is an           ║
║  UPDATE PENDING flag at the top of my AGENTS.md. Please follow     ║
║  the 5-Phase Processing Order in that flag to activate all         ║
║  skills. Start with Phase A (parallel install in waves). Do not    ║
║  skip any phase. Run QC after each skill. Send me a summary        ║
║  when complete.                                                    ║
║  <<<                                                               ║
║                                                                    ║
║  Your agent will read the UPDATE PENDING flag from your            ║
║  AGENTS.md file and walk through the rest of the install for      ║
║  you. You do not need to type any other commands.                 ║
║                                                                    ║
╠════════════════════════════════════════════════════════════════════╣
║  TIER 3 — IF YOUR AGENT ALSO CAN'T FIND THE FLAG IN AGENTS.md      ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  The full UPDATE PENDING payload was ALSO saved to a standalone    ║
║  file on this machine. The agent does NOT need to read AGENTS.md   ║
║  to use it — the file IS the activation instructions.              ║
║                                                                    ║
║  Location:                                                         ║
║                                                                    ║
║    $UPDATE_PENDING_FILE
║                                                                    ║
║  Recovery — one of these depending on your setup:                  ║
║                                                                    ║
║  (a) Copy to clipboard, then paste into agent chat:                ║
║       cat "$UPDATE_PENDING_FILE" | pbcopy
║                                                                    ║
║  (b) Send directly to your agent via Telegram (if it works):       ║
║       openclaw message send --channel telegram \\                  ║
║         --message "\$(cat "$UPDATE_PENDING_FILE")"
║                                                                    ║
║  (c) Or just open the file and read/paste it yourself:             ║
║       open "$UPDATE_PENDING_FILE"
║                                                                    ║
║  The file contains the full 5-Phase Processing Order with every    ║
║  skill activation step inline — no AGENTS.md lookup required.      ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

BACKUP_BLOCK

# ----------------------------------------------------------
# Step 12: Install Sunday weekly update-check cron (idempotent)
# ----------------------------------------------------------
step "Step 12: Installing Sunday weekly update-check cron"

install_weekly_cron() {
    # Skip if openclaw CLI isn't available
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping cron install. Re-run update-skills.sh later to install it."
        return 0
    fi

    # v10.0.1 — REMOVED approve_pending_scopes() pre-flight here too. Same reason
    # as the top-of-script removal: every paired client already has operator.write
    # (their daily Telegram usage requires it). `openclaw cron create` works
    # directly without scope manipulation.

    # CRON REWRITE MIGRATION (fix/existing-box-cron-rewrite v14.19.1):
    # Boxes provisioned BEFORE the silent-cron fix (v14.10.2) carry the OLD
    # weekly-onboarding-update cron wired with --announce --channel telegram
    # --to <client-chat-id>.  The scheduler auto-delivers raw maintenance traffic
    # into the CLIENT's Telegram chat every Sunday.  A plain "already installed"
    # skip leaves the leaking cron in place on every pre-existing box.  Fix:
    # detect old delivery wiring via openclaw cron list --json and delete the
    # stale entry so the creation code below always lands the SILENT main-session
    # form.  If python3 is absent, the detection conservatively skips deletion
    # (ensure-pipeline-crons.sh reconcile pass then catches it via --no-deliver).
    if openclaw cron list 2>/dev/null | grep -qi "weekly-onboarding-update"; then
        local _cron_has_old_wiring=false
        if command -v python3 >/dev/null 2>&1; then
            local _oc_raw_json
            _oc_raw_json=$(openclaw cron list --json 2>/dev/null) || _oc_raw_json=""
            if [ -n "$_oc_raw_json" ] && \
               OC_CRON_JSON="$_oc_raw_json" python3 - <<'PYEOF' 2>/dev/null
import json, os, sys
raw = os.environ.get('OC_CRON_JSON', '')
try:
    data = json.loads(raw)
except Exception:
    sys.exit(1)
jobs = data if isinstance(data, list) else data.get('jobs', [])
for j in jobs:
    if j.get('name') == 'weekly-onboarding-update':
        dl = j.get('delivery') or {}
        if dl.get('mode') == 'announce' or dl.get('to'):
            sys.exit(0)  # old auto-announce wiring detected
sys.exit(1)
PYEOF
            then
                _cron_has_old_wiring=true
            fi
        fi
        if [ "$_cron_has_old_wiring" = "true" ]; then
            warn "Existing weekly-onboarding-update cron has old auto-announce delivery — deleting for silent-form recreate"
            openclaw cron delete --name "weekly-onboarding-update" >/dev/null 2>&1 || true
            # Fall through to creation logic below (cron is now absent)
        else
            success "Sunday weekly update-check cron already installed (SILENT — no client auto-announce)"
            return 0
        fi
    fi

    # Reuse the bulletproof 23-location resolver from the top of this script.
    # Cached after first call, so this is a no-op if already resolved.
    if [ "$TELEGRAM_RESOLVED" != "true" ]; then
        resolve_telegram_target_universal
    fi
    local TG_TARGET="$TELEGRAM_TARGET_CACHED"

    if [ -z "$TG_TARGET" ]; then
        warn "Telegram chat ID not found by bulletproof resolver — cannot install weekly cron."
        warn "Run the diagnostic to dump every location that was checked:"
        warn "  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/diagnose-telegram-config.sh | bash"
        return 0
    fi
    # REGRESSION GUARD (fix/cron-owner-chat-routing): operator IDs must NEVER
    # be wired as a cron delivery target — crons must reach the CLIENT OWNER.
    # is_chat_id() now rejects them inside the Python resolver; this second
    # check catches any future path that bypasses the resolver.
    case "$TG_TARGET" in
        5252140759|6663821679|6771245262)
            warn "ERROR: weekly-onboarding-update cron target resolved to an OPERATOR chat ID ($TG_TARGET)."
            warn "This would route every weekly update to the operator, not the client owner. Aborting cron install."
            warn "Set OPENCLAW_OWNER_CHAT_ID=<client-owner-chat-id> before running install.sh to force the correct target."
            return 1
            ;;
    esac
    note "Telegram cron target resolved: $TG_TARGET (source: $TELEGRAM_SOURCE_CACHED)"

    # Pull cron prompt from the just-installed repo files
    local PROMPT_FILE=""
    for candidate in "$SKILLS_DIR/.cron-prompt.txt" "$OC_DOWNLOADS/openclaw-master-files/.cron-prompt.txt" "/tmp/openclaw-cron-prompt-${ONBOARDING_VERSION}.txt"; do
        [ -f "$candidate" ] && PROMPT_FILE="$candidate" && break
    done

    # If not staged locally, fetch from GitHub
    if [ -z "$PROMPT_FILE" ]; then
        PROMPT_FILE="/tmp/openclaw-cron-prompt-${ONBOARDING_VERSION}.txt"
        curl -fsSL --max-time 15 "https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/cron-prompt.txt" -o "$PROMPT_FILE" 2>/dev/null || {
            warn "Failed to fetch cron-prompt.txt from GitHub — skipping cron install"
            return 0
        }
    fi
    if [ ! -s "$PROMPT_FILE" ]; then
        warn "cron-prompt.txt is empty — skipping cron install"
        return 0
    fi

    # v9.7.8: Detect multi-account Telegram setup AND auto-detect the default
    # agent ID. Older onboarding hardcoded "--agent main" but some installs
    # use a different default agent name. We pull both from the live config.
    local CHANNEL_ACCOUNT=""
    local DEFAULT_AGENT=""
    local DETECT_OUT
    DETECT_OUT=$(python3 -c "
import json, os, re
HOME = os.path.expanduser('~')
candidates = [
    os.path.expanduser('~/.openclaw/openclaw.json'),
    os.path.expanduser('~/Library/Application Support/openclaw/openclaw.json'),
    os.path.expanduser('~/.config/openclaw/openclaw.json'),
]
account = ''
agent_id = ''

# Detect account from credentials/telegram-<account>-allowFrom.json (Mac canonical location).
for cdir in (os.path.join(HOME, '.openclaw', 'credentials'),
             os.path.expanduser('~/Library/Application Support/openclaw/credentials')):
    if not os.path.isdir(cdir):
        continue
    try:
        for fn in os.listdir(cdir):
            m = re.match(r'^telegram-(.+)-allowFrom\.json\$', fn)
            if m:
                account = m.group(1)
                break
    except Exception:
        pass
    if account:
        break

for p in candidates:
    if not os.path.isfile(p):
        continue
    try:
        cfg = json.load(open(p))
        if not account:
            accounts = cfg.get('channels', {}).get('telegram', {}).get('accounts', {})
            if isinstance(accounts, dict) and accounts:
                account = 'default' if 'default' in accounts else list(accounts.keys())[0]
        for a in cfg.get('agents', {}).get('list', []) or []:
            if isinstance(a, dict) and a.get('default'):
                agent_id = a.get('id', '')
                break
        if not agent_id:
            for a in cfg.get('agents', {}).get('list', []) or []:
                if isinstance(a, dict) and a.get('id'):
                    agent_id = a.get('id')
                    break
        break
    except Exception:
        continue
print(f'{account}|{agent_id}')
" 2>/dev/null)
    CHANNEL_ACCOUNT="${DETECT_OUT%%|*}"
    DEFAULT_AGENT="${DETECT_OUT##*|}"
    [ -n "$DEFAULT_AGENT" ] && note "Default agent detected: $DEFAULT_AGENT"
    [ -n "$CHANNEL_ACCOUNT" ] && note "Multi-account Telegram detected; will use --account $CHANNEL_ACCOUNT"

    local PROMPT_CONTENT
    PROMPT_CONTENT=$(cat "$PROMPT_FILE")

    # ── SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons) ──────────────
    # weekly-onboarding-update is a MAINTENANCE/update-check cron, NOT an
    # owner-facing announcement. The old form registered it with
    # `--channel telegram --to $TG_TARGET` (+ a final `--announce` attempt),
    # which made the OpenClaw scheduler AUTO-DELIVER the raw maintenance prompt
    # straight into the CLIENT's chat every Sunday — internal operator traffic
    # the client was never meant to see (the exact leak OPERATOR-MAINTENANCE.md
    # "operator-drive contract" forbids).
    #
    # FIX: register it as a SILENT AGENT-MESSAGE cron on the agent's OWN main
    # session — `--agent <main> --session-target main --light-context` with NO
    # `--channel`, NO `--to`, NO `--announce`. The cron fires the update-check
    # in the agent's own context (log-only); the agent then decides, using its
    # own deliberate `openclaw message send`, whether to surface an
    # owner-facing "an update is available, may I apply it?" question. Nothing
    # is auto-pushed to the client chat. This mirrors the silent main-session
    # pattern used by Skill 35 (register-weekly-cron.sh) and the 5.x
    # agent-message fallback in ensure-pipeline-crons.sh.
    #
    # $TG_TARGET is still resolved + operator-guarded above so the agent knows
    # the owner chat to send to WHEN it decides to — we just never wire it as
    # the cron's auto-delivery sink.
    local CRON_AGENT="${DEFAULT_AGENT:-main}"

    # Runtime-compatible SILENT main-session cron (fix/cron-flag-skew). The old
    # ladder only emitted `--session-target main` forms, ALL of which the 2026.6.11
    # runtime rejects ("does not recognize option --session-target" / "Main jobs
    # require --system-event") — so a fresh install on 6.11 registered NO weekly
    # cron. _oc_cron_silent_main probes `openclaw cron add --help` and emits the
    # accepted form (`--session main --system-event` on 6.11+), degrading gracefully.
    if _oc_cron_silent_main "weekly-onboarding-update" "$CRON_AGENT" "0 3 * * 0" "America/New_York" "$PROMPT_CONTENT" --light-context; then
        success "Sunday update-check cron installed — Sundays 3am ET, SILENT main-session (no client auto-announce)"
        return 0
    fi

    # All silent attempts failed — leave a recovery hint (still SILENT: no
    # --channel/--to/--announce in the manual command either).
    warn "Cron creation failed. Manual install command (SILENT — no client auto-announce):"
    warn "  openclaw cron create --name weekly-onboarding-update --agent $CRON_AGENT \\"
    warn "    --cron '0 3 * * 0' --tz America/New_York \\"
    warn "    --session main --system-event \"\$(cat $PROMPT_FILE)\"   # older CLIs: --session-target main --message"
    warn ""
    warn "If that fails too, send Trevor the EXACT error message (see $LOG_FILE)."
    return 0
}

install_weekly_cron

# ----------------------------------------------------------
# Step 13: Install workforce-build resume cron (v10.13.15)
# ----------------------------------------------------------
# Why: post-interview workforce builds occasionally die mid-way (token limit,
# tool error, agent thinks it's done). Without a resume layer, the build sits
# half-built forever. This cron fires every 15 minutes, reads
# .workforce-build-state.json, and self-pings the agent if there are pending
# or stale-building departments. See Skill 23 INSTRUCTIONS.md → "Post-Interview
# Handoff Protocol" for the full contract.
step "Step 13: Installing workforce-build resume cron (15-min check, fires only if state is dirty)"

install_workforce_resume_cron() {
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping workforce-resume cron. Re-run update-skills.sh later."
        return 0
    fi

    # PARK-AWARE (v14.1.5): never (re)install a parked box's resume cron. A stuck
    # build writes a DURABLE park marker + disables this cron on purpose; resuming
    # is operator-only (scripts/unpark-build.sh). Respect it here too so a manual
    # re-install cannot resurrect the furnace an operator intentionally parked.
    local _PARK_MARKER
    _PARK_MARKER="$(dirname "$SKILLS_DIR")/workspace/.park/workforce-build.parked"
    if [ -f "$_PARK_MARKER" ]; then
        warn "Workforce-build resume cron NOT installed — build is PARKED ($_PARK_MARKER). Un-park is operator-only: scripts/unpark-build.sh"
        return 0
    fi

    if oc_cron_tombstoned "workforce-build-resume"; then
        warn "workforce-build-resume is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove workforce-build-resume"
        return 0
    fi
    if oc_cron_present "workforce-build-resume"; then
        success "Workforce-build resume cron already installed"
        return 0
    fi

    local RESUME_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
    if [ ! -f "$RESUME_SCRIPT" ]; then
        warn "resume-workforce-build.sh not found at $RESUME_SCRIPT — cron install skipped (older skill bundle?)"
        return 0
    fi
    chmod +x "$RESUME_SCRIPT" 2>/dev/null || true

    # ── CHEAP COMMAND-MODE (fix/industry-gate-and-idempotent-crons, Fix C) ────
    # workforce-build-resume used to be a SILENT main-session AGENT-MESSAGE cron
    # (the full resume-prompt.txt fed as the system-event payload) — every */15
    # fire spun up a COMPLETE LLM turn just to reach resume-workforce-build.sh's
    # own "nothing to resume" verdict (the diagnosed no-op furnace). That script
    # is ALREADY a cheap, token-free check on its own (plain bash + jq); it
    # escalates to an actual agent turn — via `openclaw message send`, the SAME
    # self-ping mechanism closeout-resume already uses — ONLY when there is
    # genuinely pending/stale work. So this now registers the CRON ITSELF in
    # command mode (`bash resume-workforce-build.sh`), mirroring
    # scripts/ensure-pipeline-crons.sh::_ensure_workforce_build_resume and the
    # already-correct closeout-resume pattern. Falls back to a SHORT
    # run-the-script agent-message cron (NOT the old full resume-prompt.txt) on a
    # CLI without --command support.
    local CHANNEL_AGENT="main"
    if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
        CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
    fi

    local _wbr_help _wbr_has_command=0
    _wbr_help="$(openclaw cron add --help 2>&1 || true)"
    printf '%s' "$_wbr_help" | grep -qE '^[[:space:]]*--command[[:space:]<]' && _wbr_has_command=1

    if [ "$_wbr_has_command" -eq 1 ] && openclaw cron add --name "workforce-build-resume" \
         --cron "*/15 * * * *" --command "bash $RESUME_SCRIPT" >/dev/null 2>&1; then
        success "Workforce-build resume cron installed — every 15 min, COMMAND mode (zero LLM tokens per tick; an agent turn dispatches only when the script finds real work)"
        return 0
    fi

    local _wbr_msg="[PIPELINE-CRON workforce-build-resume] Run this exact shell command now and report only on failure: bash $RESUME_SCRIPT"
    if _oc_cron_silent_main "workforce-build-resume" "$CHANNEL_AGENT" "*/15 * * * *" "America/New_York" "$_wbr_msg" --light-context; then
        success "Workforce-build resume cron installed — every 15 min, SILENT main-session agent-message fallback (older CLI, no --command support; short run-the-script message, not the old full resume-prompt.txt payload)"
        return 0
    fi

    warn "Workforce-build resume cron creation failed. Manual install (COMMAND mode preferred):"
    warn "  openclaw cron add --name workforce-build-resume --cron '*/15 * * * *' --command 'bash $RESUME_SCRIPT'"
    return 0
}

install_workforce_resume_cron

# ----------------------------------------------------------
# Step 13b: Install the onboarding-resume cron (FIX 1, v10.15.48)
# ----------------------------------------------------------
# Why: install.sh copies skills to disk but ACTIVATION (read INSTALL.md, merge
# CORE_UPDATES, run qc) is the agent's job — and an interrupted/over-eager run
# used to leave un-registered skills while reporting "done". This cron is the
# autonomous resume layer for ONBOARDING: every 15 min it runs the verification
# gate and, while any skill is pending|downloaded|wired|qc-failed, self-pings
# the agent to activate + verify. It NEVER stops on a self-declared "done" —
# only on a real gate-pass (handled by the shell guard scripts/resume-onboarding.sh).
# Modeled on install_workforce_resume_cron; reuses max-runs + Rescue Rangers.
step "Step 13b: Installing onboarding-resume cron (every 30 min — interview gate + backoff in script)"

# install_onboarding_resume_cron() is defined ONCE in lib-onboarding-resume-cron.sh
# (sourced near the top of this script) so install.sh and update-skills.sh share
# the SAME SILENT, idempotent, bounded, self-removing installer with no drift. It
# registers a */30 main-session self-ping (no --channel/--to/--announce); all
# boundedness lives in scripts/resume-onboarding.sh. See that lib for details.
install_onboarding_resume_cron

# ----------------------------------------------------------
# Step 13.4: Install watchdog-onboarding-loop cron (PRD-2.13, every 10 min)
# ----------------------------------------------------------
# Why: the existing resume cron (Step 13) fires every 15 min and dispatches
# a broad "resume onboarding" message. PRD 2.13 adds a separate watchdog that
# (a) runs a cheap state-file goal check FIRST (near-zero tokens), (b) only
# prompts the agent when a specific wave is incomplete, (c) uses the EXACT
# per-wave prompt (never a vague "continue"), (d) stops the loop on 3-strike
# escalation, and (e) self-kills when the overall goal verifies. The watchdog
# is registered in the loop registry for closeout QC assertion.
step "Step 13.4: Installing watchdog-onboarding-loop cron (PRD-2.13, 10-min cheap check)"

install_watchdog_loop_cron() {
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping watchdog-onboarding-loop cron. Re-run update-skills.sh later."
        return 0
    fi
    if oc_cron_tombstoned "watchdog-onboarding-loop"; then
        warn "watchdog-onboarding-loop is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove watchdog-onboarding-loop"
        return 0
    fi
    if oc_cron_present "watchdog-onboarding-loop"; then
        success "watchdog-onboarding-loop cron already installed"
        return 0
    fi

    local WATCHDOG_SCRIPT="$ONBOARDING_DIR/scripts/watchdog-onboarding-loop.sh"
    if [ ! -f "$WATCHDOG_SCRIPT" ]; then
        warn "watchdog-onboarding-loop.sh not found at $WATCHDOG_SCRIPT — watchdog cron skipped"
        return 0
    fi
    chmod +x "$WATCHDOG_SCRIPT" 2>/dev/null || true
    chmod +x "$ONBOARDING_DIR/scripts/loop-registry.sh" 2>/dev/null || true

    # ── SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons) ──────────────
    # watchdog-onboarding-loop is a MAINTENANCE self-ping (cheap state-file
    # goal check; prompts the agent only when a wave is incomplete). The old
    # form wired `--channel telegram --to $TG_TARGET`, auto-delivering the
    # watchdog prompt to the CLIENT chat every 20 min. FIX: SILENT main-session
    # agent-message cron (no --channel/--to/--announce). No owner target needed
    # → no operator-ID strand. The watchdog itself drives the agent in its own
    # context; any owner-facing message is the agent's own deliberate send.
    local CHANNEL_AGENT="main"
    if [ -n "${TELEGRAM_DEFAULT_AGENT_CACHED:-}" ]; then
        CHANNEL_AGENT="$TELEGRAM_DEFAULT_AGENT_CACHED"
    fi

    local WATCHDOG_PROMPT="[ONBOARDING-WATCHDOG] Run the onboarding watchdog: bash ~/.openclaw/scripts/watchdog-onboarding-loop.sh || bash /data/.openclaw/scripts/watchdog-onboarding-loop.sh 2>/dev/null || true. This is a cheap state-file check — it self-removes when the overall goal is verified."

    # Runtime-compatible SILENT main-session cron (fix/cron-flag-skew): probe the
    # CLI and emit `--session main --system-event` (2026.6.11+) or
    # `--session-target main --message` (older CLIs). */20, --light-context.
    if _oc_cron_silent_main "watchdog-onboarding-loop" "$CHANNEL_AGENT" "*/20 * * * *" "America/New_York" "$WATCHDOG_PROMPT" --light-context; then
        # The helper swallows create output, so look the UUID up by name from the
        # cron list — the loop-registry uses it to self-remove on overall-goal pass.
        local CRON_UUID
        CRON_UUID=$(openclaw cron list 2>/dev/null | awk '/watchdog-onboarding-loop/ { for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }' | head -1 || true)
        if [ -n "$CRON_UUID" ] && [ -f "$ONBOARDING_DIR/scripts/loop-registry.sh" ]; then
            # shellcheck disable=SC1090
            LOOP_REGISTRY_FILE="${OC_CONFIG}/workspace/.loop-registry.json" \
            source "$ONBOARDING_DIR/scripts/loop-registry.sh" 2>/dev/null || true
            LOOP_REGISTRY_FILE="${OC_CONFIG}/workspace/.loop-registry.json" \
            lr_register "watchdog-onboarding-loop" "$CRON_UUID" "openclaw cron rm $CRON_UUID" 2>/dev/null || true
        fi
        success "watchdog-onboarding-loop cron installed (PRD-2.13, */20) — SILENT main-session (no client auto-announce); interview gate + wave-backoff + shared dispatch lock; self-kills on overall goal pass"
        return 0
    fi

    warn "watchdog-onboarding-loop cron creation failed. Manual install (SILENT — no client auto-announce):"
    warn "  openclaw cron create --name watchdog-onboarding-loop --agent $CHANNEL_AGENT \\"
    warn "    --cron '*/20 * * * *' --tz America/New_York \\"
    warn "    --session main --system-event '[ONBOARDING-WATCHDOG] bash ~/.openclaw/scripts/watchdog-onboarding-loop.sh'   # older CLIs: --session-target main --message"
    return 0
}

install_watchdog_loop_cron

# ----------------------------------------------------------
# Step 13.5: Install interview-nudge cron (PRD-2.15, every 6h)
# ----------------------------------------------------------
# Why: incomplete interviews go stale when owners stop responding. This cron
# fires every 6h, reads .workforce-build-state.json (primary) / interview-handoff.md
# (fallback), and sends a gateway-routed nudge at 24h/72h/168h idle thresholds.
# The cron is a cheap trigger — it calls nudge-incomplete-interviews.py (worker)
# which handles the send, idempotency, and state recording.
# All sends go through `openclaw message send` — NEVER direct to api.telegram.org.
#
# v12.3.10 CHANGES (fix/v12.3.10-nudge-cron-selfremove-no-operator-announce):
#   COMMAND MODE (no --channel/--to/--message): converted from announce/agentTurn
#   mode to silent command mode (mirrors closeout-resume pattern). The cron now
#   just runs interview-nudge-cron.sh; all status goes to the script log, NOT to
#   any Telegram chat. No operator-chat status announce.
#   UUID CAPTURE: the cron UUID is captured from `openclaw cron add --json` output
#   and persisted to build-state as .interviewNudgeUuid so run-closeout.sh can
#   self-remove it when interviewComplete=true reaches closeoutStatus=done.
step "Step 13.5: Installing interview-nudge cron (6-hour idle check, PRD-2.15)"

install_interview_nudge_cron() {
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping interview-nudge cron. Re-run update-skills.sh later."
        return 0
    fi
    if openclaw cron list 2>/dev/null | grep -qi "interview-nudge"; then
        success "interview-nudge cron already installed"
        return 0
    fi

    # Resolve skill dir (same pattern as other cron installs)
    local _NUDGE_SCRIPT=""
    for _candidate in \
        "${HOME}/.openclaw/skills/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh" \
        "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh" \
        "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/23-ai-workforce-blueprint/scripts/interview-nudge-cron.sh"; do
        if [ -f "$_candidate" ]; then
            _NUDGE_SCRIPT="$_candidate"
            break
        fi
    done

    if [ -z "$_NUDGE_SCRIPT" ]; then
        warn "interview-nudge-cron.sh not found — cron NOT installed."
        return 0
    fi

    # COMMAND MODE (v12.3.10): silent command cron — no --channel/--to/--message.
    # The shim runs interview-nudge-cron.sh; status is log-only, never a Telegram
    # announce. The operator-rejection guard is inside the shim itself (via the
    # v12.3.8 resolve-owner-chat.sh / nudge-incomplete-interviews.py).
    local RC=0
    local OUT
    OUT=$(openclaw cron add \
        --name "interview-nudge" \
        --schedule "0 */6 * * *" \
        --command "bash $_NUDGE_SCRIPT" \
        --json \
        2>&1) || RC=$?
    # v14.1.3: docs-canonical positional form (2026.6.8) — the schedule is a
    # POSITIONAL arg, NOT a `--schedule` flag (verified docs.openclaw.ai/cli/cron;
    # `--json` is also not an add/create flag). Retry positionally if the flag
    # form failed. Non-fatal either way.
    if [ "$RC" -ne 0 ]; then
        RC=0
        OUT=$(openclaw cron create "0 */6 * * *" \
            --name "interview-nudge" \
            --command "bash $_NUDGE_SCRIPT" \
            2>&1) || RC=$?
    fi
    if [ "$RC" -eq 0 ]; then
        # Capture UUID and persist to build-state for self-removal at closeout
        local CRON_UUID
        CRON_UUID=$(printf '%s' "$OUT" | jq -r '.uuid // .id // empty' 2>/dev/null || true)
        if [ -n "$CRON_UUID" ] && [ "$CRON_UUID" != "null" ]; then
            local _STATE_FILE="${OC_ROOT:-${HOME}/.openclaw}/workspace/.workforce-build-state.json"
            if [ -f "$_STATE_FILE" ] && command -v jq >/dev/null 2>&1; then
                local _NOW
                _NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)
                local _TMP
                _TMP=$(mktemp)
                if jq \
                    --arg uuid "$CRON_UUID" \
                    --arg ts "$_NOW" \
                    '.interviewNudgeUuid = $uuid | .interviewNudgeRegisteredAt = $ts' \
                    "$_STATE_FILE" > "$_TMP" 2>/dev/null; then
                    mv "$_TMP" "$_STATE_FILE"
                else
                    rm -f "$_TMP"
                fi
            fi
            # Register with loop-registry for hygiene
            if [ -f "$ONBOARDING_DIR/scripts/loop-registry.sh" ]; then
                # shellcheck disable=SC1090
                LOOP_REGISTRY_FILE="${OC_ROOT:-${HOME}/.openclaw}/workspace/.loop-registry.json" \
                source "$ONBOARDING_DIR/scripts/loop-registry.sh" 2>/dev/null || true
                LOOP_REGISTRY_FILE="${OC_ROOT:-${HOME}/.openclaw}/workspace/.loop-registry.json" \
                lr_register "interview-nudge" "$CRON_UUID" "openclaw cron rm $CRON_UUID" 2>/dev/null || true
            fi
        fi
        success "interview-nudge cron installed (every 6h, silent command mode — no operator announce)"
    else
        warn "interview-nudge cron creation failed (non-fatal)."
        warn "  Manual: openclaw cron add --name interview-nudge --schedule '0 */6 * * *' --command 'bash $_NUDGE_SCRIPT' --json"
    fi
    return 0
}

install_interview_nudge_cron

# ----------------------------------------------------------
# Step 13.5b: Install closeout-readiness-watchdog cron (PRD-2.15, v12.3.12)
# ----------------------------------------------------------
# WHY: the interview-nudge cron is owner-facing only. The closeout-readiness-
# watchdog is the OPERATOR-FACING twin: it surfaces stalled interviews, failed
# QC, wedged builds, and blocked closeouts to the operator + Rescue Rangers so
# Trevor learns on day 5 instead of "never". Fires every 6h (token-free).
# Mirrors the interview-nudge install block exactly.
# ----------------------------------------------------------
step "Step 13.5b: Installing closeout-readiness-watchdog cron (6-hour operator escalation, PRD-2.15 v12.3.12)"

install_closeout_watchdog_cron() {
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping closeout-readiness-watchdog cron. Re-run update-skills.sh later."
        return 0
    fi

    if oc_cron_tombstoned "closeout-readiness-watchdog"; then
        warn "closeout-readiness-watchdog is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove closeout-readiness-watchdog"
        return 0
    fi
    if oc_cron_present "closeout-readiness-watchdog"; then
        success "closeout-readiness-watchdog cron already installed"
        return 0
    fi

    _WATCHDOG_SCRIPT=""
    for _cand in \
        "${HOME}/.openclaw/skills/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh" \
        "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh" \
        "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"; do
        if [[ -f "$_cand" ]]; then
            _WATCHDOG_SCRIPT="$_cand"
            break
        fi
    done

    if [[ -z "$_WATCHDOG_SCRIPT" ]]; then
        warn "closeout-readiness-watchdog.sh not found — cron NOT installed."
        return 0
    fi

    # Register as COMMAND mode (no --channel/--to/--message) — status is log-only.
    # Matches the interview-nudge cron pattern (v12.3.10 OPERATOR-ANNOUNCE RULE).
    _WATCHDOG_CRON_OUT=$(openclaw cron add \
        --name "closeout-readiness-watchdog" \
        --schedule "0 */6 * * *" \
        --command "bash $_WATCHDOG_SCRIPT" \
        --json 2>/dev/null || true)
    # v14.1.3: docs-canonical positional fallback (2026.6.8) — schedule is a
    # POSITIONAL arg, not `--schedule`; `--json` is not an add/create flag.
    if [[ -z "$_WATCHDOG_CRON_OUT" ]]; then
        _WATCHDOG_CRON_OUT=$(openclaw cron create "0 */6 * * *" \
            --name "closeout-readiness-watchdog" \
            --command "bash $_WATCHDOG_SCRIPT" 2>/dev/null || true)
    fi

    if [[ -n "$_WATCHDOG_CRON_OUT" ]]; then
        _WATCHDOG_UUID=$(printf '%s' "$_WATCHDOG_CRON_OUT" | jq -r '.id // .uuid // empty' 2>/dev/null || true)
        if [[ -n "$_WATCHDOG_UUID" ]]; then
            # Write UUID to state for later self-removal if needed
            _WD_STATE_FILE="${OC_CONFIG:-${HOME}/.openclaw}/workspace/.workforce-build-state.json"
            if [[ -f "$_WD_STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
                _tmp=$(mktemp)
                jq --arg uuid "$_WATCHDOG_UUID" '.closeoutWatchdogCronUuid = $uuid' \
                    "$_WD_STATE_FILE" > "$_tmp" && mv "$_tmp" "$_WD_STATE_FILE" || rm -f "$_tmp"
            fi
        fi
        success "closeout-readiness-watchdog cron installed (every 6h, silent command mode — operator escalation via Telegram + Rescue Rangers)"
    else
        warn "closeout-readiness-watchdog cron creation failed (non-fatal)."
        warn "  Manual: openclaw cron add --name closeout-readiness-watchdog --schedule '0 */6 * * *' --command 'bash $_WATCHDOG_SCRIPT' --json"
    fi
    return 0
}

install_closeout_watchdog_cron

# ----------------------------------------------------------
# Step 13.6: Install onboarding re-arm hook (nudge lifecycle)
# ----------------------------------------------------------
# WHY: when the owner sends ANY message after the nudge lifecycle has gone
# DORMANT, onboarding must automatically wake up (re-arm) without requiring
# a manual operator action. The hook is a lightweight OpenClaw incoming-
# message hook that touches $WS/.onboarding-nudge-rearm whenever a message
# arrives from the owner chat. resume-onboarding.sh detects the touch file
# on its next (cheap) cron fire and resets the attempt counter.
#
# IMPLEMENTATION:
#   OpenClaw hooks are registered in openclaw.json under
#   hooks.onMessage[].command. The hook script is written to
#   $OC_CONFIG/scripts/onboarding-rearm-hook.sh and registered idempotently.
#   The hook itself is pure shell (touch + log) — zero model calls.
# ----------------------------------------------------------
step "Step 13.6: Installing onboarding re-arm hook (nudge lifecycle wakeup on owner message)"

install_rearm_hook() {
    if ! command -v openclaw >/dev/null 2>&1; then
        warn "openclaw CLI not on PATH — skipping re-arm hook install."
        return 0
    fi

    local HOOK_DIR="$OC_CONFIG/scripts"
    local HOOK_SCRIPT="$HOOK_DIR/onboarding-rearm-hook.sh"
    local NUDGE_STATE="$OC_CONFIG/workspace/.onboarding-nudge-state"
    local REARM_FILE="$OC_CONFIG/workspace/.onboarding-nudge-rearm"
    local REARM_LOG="$OC_CONFIG/workspace/.onboarding-rearm-hook.log"
    mkdir -p "$HOOK_DIR" 2>/dev/null || true

    # Write the hook script (idempotent — overwrite to pick up any updates)
    cat > "$HOOK_SCRIPT" <<'HOOK_EOF'
#!/usr/bin/env bash
# onboarding-rearm-hook.sh — nudge lifecycle re-arm on owner message
# Called by OpenClaw's onMessage hook. Pure file I/O — zero model calls.
# Arguments: $1=channel, $2=chatId, $3=messageText (optional, may be absent)
set -u
if [[ -d /data/.openclaw ]]; then OC_ROOT=/data/.openclaw
elif [[ -d "${HOME}/.openclaw" ]]; then OC_ROOT="${HOME}/.openclaw"
else exit 0; fi

WS="$OC_ROOT/workspace"
NUDGE_STATE="$WS/.onboarding-nudge-state"
REARM_FILE="$WS/.onboarding-nudge-rearm"
LOG="$WS/.onboarding-rearm-hook.log"

# Only act if the nudge state file exists (onboarding is active on this box).
[ -f "$NUDGE_STATE" ] || exit 0

# Only re-arm if currently dormant (avoid resetting mid-lifecycle unnecessarily).
_dormant="$(grep '^dormant=' "$NUDGE_STATE" 2>/dev/null | head -1 | cut -d= -f2-)"
if [ "$_dormant" = "true" ]; then
    touch "$REARM_FILE" 2>/dev/null || true
    printf '%s onboarding-rearm-hook: owner message detected — re-arm file created\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG" 2>/dev/null || true
fi
exit 0
HOOK_EOF
    chmod +x "$HOOK_SCRIPT" 2>/dev/null || true
    success "Re-arm hook script written → $HOOK_SCRIPT"

    # Register the hook in openclaw.json via openclaw config set (idempotent).
    # The hook fires on every inbound message; the script self-gates on dormant.
    # Use openclaw config to check if already registered before adding.
    local _existing_hooks
    _existing_hooks="$(openclaw config get hooks.onMessage 2>/dev/null | tr -d '[:space:]' || echo "")"
    if echo "$_existing_hooks" | grep -qF "onboarding-rearm-hook"; then
        success "Re-arm hook already registered in openclaw.json — skipping"
        return 0
    fi

    # Append the hook using safe_json_edit (defined earlier in install.sh)
    # to avoid clobbering existing hooks.
    local _oc_json="$OC_CONFIG/openclaw.json"
    if [ -f "$_oc_json" ] && command -v python3 >/dev/null 2>&1; then
        local _tmp; _tmp="$(mktemp)"
        python3 - "$_oc_json" "$HOOK_SCRIPT" <<'PYEOF' > "$_tmp" 2>/dev/null && mv "$_tmp" "$_oc_json" || rm -f "$_tmp"
import json, sys
path, hook_script = sys.argv[1], sys.argv[2]
with open(path) as f:
    cfg = json.load(f)
hooks = cfg.setdefault("hooks", {})
on_msg = hooks.setdefault("onMessage", [])
# Idempotent: only add if not already present
if not any(isinstance(h, dict) and "onboarding-rearm-hook" in h.get("command","") for h in on_msg):
    on_msg.append({"command": hook_script, "async": True})
cfg["hooks"]["onMessage"] = on_msg
print(json.dumps(cfg, indent=2))
PYEOF
        # Validate the JSON we just wrote
        if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$_oc_json" 2>/dev/null; then
            success "Re-arm hook registered in openclaw.json (hooks.onMessage)"
        else
            warn "openclaw.json validation failed after hook registration — rolled back"
            git checkout "$_oc_json" 2>/dev/null || true
        fi
    else
        warn "Could not register re-arm hook in openclaw.json (no python3 or config not found). Manual: add '$HOOK_SCRIPT' to hooks.onMessage in $OC_CONFIG/openclaw.json"
    fi
    return 0
}

install_rearm_hook

# ----------------------------------------------------------
# Step 14: Install Skill 37 (ZHC Closeout) (v10.13.16)
# ----------------------------------------------------------
# Why: post-build closeout — fire Skill 32, generate 2 infographics + a
# celebration video via KIE.AI, build a 9-section Notion page tree in the
# client's workspace, and deliver 6 paced Telegram messages to the owner.
# Triggered automatically via the workforce-build-resume cron (Step 13)
# detecting closeoutStatus dirty state. See:
#   23-ai-workforce-blueprint/INSTRUCTIONS.md → "Moment 4: Closeout Pipeline"
#   37-zhc-closeout/INSTRUCTIONS.md
step "Step 14: Installing Skill 37 (ZHC Closeout) — automatic post-build celebration pipeline"

install_skill_37_zhc_closeout() {
    local SKILL_SRC="$ONBOARDING_DIR/37-zhc-closeout"
    local SKILL_DEST="$SKILLS_DIR/37-zhc-closeout"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 37 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    # Idempotent: skip if dest looks current
    if [ -f "$SKILL_DEST/skill-version.txt" ] && [ -f "$SKILL_DEST/scripts/run-closeout.sh" ]; then
        local SKILL37_CURRENT
        SKILL37_CURRENT=$(cat "$SKILL_DEST/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        local SKILL37_SRC_VER
        SKILL37_SRC_VER=$(cat "$SKILL_SRC/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$SKILL37_CURRENT" ] && [ "$SKILL37_CURRENT" = "$SKILL37_SRC_VER" ]; then
            success "Skill 37 already installed at v${SKILL37_CURRENT}"
            chmod +x "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true
            return 0
        fi
        note "Skill 37 present at v${SKILL37_CURRENT:-?}, source is v${SKILL37_SRC_VER:-?} — refreshing"
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 37 from $SKILL_SRC → $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true

    # Env-var preflight (warn-only — Skill 37 no-ops cleanly without these)
    if [ -z "${KIE_API_KEY:-}" ]; then
        warn "KIE_API_KEY not set in current env — Skill 37 will no-op when triggered. Set it in your shell rc or ~/.openclaw/config/.env to enable closeout."
    else
        success "KIE_API_KEY present — Skill 37 image+video generation enabled"
    fi
    if [ -z "${NOTION_API_TOKEN:-}" ]; then
        warn "NOTION_API_TOKEN not set in current env — Skill 37's Notion step will fail. Set it in your shell rc or ~/.openclaw/config/.env to enable closeout docs."
    else
        success "NOTION_API_TOKEN present — Skill 37 Notion page-tree creation enabled"
        # NOTION PARENT-PAGE PROVISIONING (root-page-create-failed permanent fix):
        # An INTERNAL Notion integration CANNOT create a workspace-root page — it can
        # only write UNDER a page that has been explicitly shared with it. Establish
        # that shared parent ONCE here: if any page is already shared, pin it as
        # NOTION_CLOSEOUT_PARENT_PAGE_ID; otherwise emit a crisp one-time client
        # instruction. Non-fatal either way — the closeout re-checks every run and
        # auto-completes the moment a page is shared.
        local _NOTION_PARENT_SCRIPT="$SKILL_DEST/scripts/ensure-notion-parent-page.sh"
        if [ -f "$_NOTION_PARENT_SCRIPT" ]; then
            chmod +x "$_NOTION_PARENT_SCRIPT" 2>/dev/null || true
            if bash "$_NOTION_PARENT_SCRIPT" >> "$LOG_FILE" 2>&1; then
                success "Notion closeout parent page ensured (pinned an accessible page, or emitted the one-time share instruction — closeout will not fail on root-page-create)"
            else
                warn "ensure-notion-parent-page.sh returned non-zero (non-fatal — closeout's own fail-clear path will re-check and stage content)."
            fi
        else
            warn "ensure-notion-parent-page.sh not found in Skill 37 scripts — closeout's in-script parent resolution + fail-clear staging still apply."
        fi
    fi

    success "Skill 37 (ZHC Closeout) installed → $SKILL_DEST"

    # v12.34.0 (ZHC-EXPERIENCE fix BREAK #2/#3): closeout MUST NOT depend solely
    # on the Step 13 workforce-build-resume cron. Register the DEDICATED,
    # REDUNDANT closeout-resume cron here, at install time. It is COMMAND mode
    # (`bash resume-closeout-cron.sh`) so it needs NO owner Telegram target and
    # fires run-closeout.sh even on a box where Step 13 was skipped/aborted.
    local _CLOSEOUT_CRON_INSTALLER="$SKILL_DEST/scripts/install-closeout-resume-cron.sh"
    if [ -f "$_CLOSEOUT_CRON_INSTALLER" ]; then
        chmod +x "$_CLOSEOUT_CRON_INSTALLER" 2>/dev/null || true
        if bash "$_CLOSEOUT_CRON_INSTALLER" >> "$LOG_FILE" 2>&1; then
            success "Dedicated closeout-resume cron registered (REDUNDANT trigger — closeout no longer hangs off a single cron)"
        else
            warn "install-closeout-resume-cron.sh reported a non-zero rc (closeout-resume cron may not have registered — ensure-pipeline-crons.sh will backfill at end of run)"
        fi
    else
        warn "install-closeout-resume-cron.sh not found in Skill 37 scripts — relying on ensure-pipeline-crons.sh backfill for the closeout trigger."
    fi

    note "Skill 37 fires via REDUNDANT triggers: the dedicated closeout-resume cron (registered here), the workforce-build-resume cron (Step 13), AND the closeout-readiness-watchdog. ensure-pipeline-crons.sh (end of run) backfills any missing trigger. No single point of failure."
    return 0
}

install_skill_37_zhc_closeout

# ----------------------------------------------------------
# Step 14a: Start the GHL MCP server (FIX 3, v10.15.48)
# ----------------------------------------------------------
# Why: Skill 36 registers the GHL community MCP in mcp.servers but nothing ever
# STARTS the local server on :8765 — so the GHL tools never resolve at runtime.
# The launchd plist lived only as PROSE in 36-ghl-mcp-setup/INSTALL.md §5.5
# (downloaded, never executed). This step runs the EXECUTED autostart: build if
# needed, install the canonical launchd KeepAlive plist (com.clawd.ghl-mcp) on
# :8765, health-check, and register. Idempotent; honest SKIP if GHL creds absent.
step "Step 14a: Starting GHL MCP server (launchd KeepAlive :8765 + healthcheck)"

start_ghl_mcp_autostart() {
    local AUTOSTART="$ONBOARDING_DIR/scripts/ghl-mcp-autostart.sh"
    if [ ! -x "$AUTOSTART" ]; then
        [ -f "$AUTOSTART" ] && chmod +x "$AUTOSTART" 2>/dev/null || true
    fi
    if [ ! -f "$AUTOSTART" ]; then
        warn "ghl-mcp-autostart.sh not found at $AUTOSTART — GHL MCP server NOT started (older bundle?). GHL tools will not resolve until it is run."
        return 0
    fi
    local OUT RC=0
    OUT="$(bash "$AUTOSTART" 2>&1)" || RC=$?
    printf '%s\n' "$OUT" >> "$LOG_FILE"
    local STATUS_LINE
    STATUS_LINE="$(printf '%s\n' "$OUT" | grep -E '^STATUS:' | tail -1 || true)"
    case "$STATUS_LINE" in
        *HEALTHY_ALREADY*|*"=HEALTHY"*) success "GHL MCP server running + registered (${STATUS_LINE:-healthy})" ;;
        *SKIPPED_NO_CREDS*)             note "GHL MCP server not started — GHL token absent (honest gap). ${STATUS_LINE}" ;;
        *STARTED_UNHEALTHY*)            warn "GHL MCP service installed but /health not green yet — KeepAlive will retry. ${STATUS_LINE}" ;;
        *BUILD_FAILED*)                 warn "GHL MCP server build failed — GHL tools will not resolve until fixed. ${STATUS_LINE}" ;;
        *)                              note "GHL MCP autostart ran. ${STATUS_LINE:-(no STATUS line captured — see $LOG_FILE)}" ;;
    esac
    return 0
}

start_ghl_mcp_autostart

# ----------------------------------------------------------
# Step 14b: Installing Skill 38 (Conversational AI System v5.14)
# ----------------------------------------------------------
# Why: skill 38 is the conversational AI BRAIN that runs ON TOP of skill 29
# (GHL Convert and Flow). It packages the v5.14 playbook (~8,800 lines, 14
# version iterations) as 27 protocols + 8 journey templates + 9 install
# scripts + 7 references. Requires skills 05, 10, 19, 29 as prerequisites
# (checked at runtime by the skill's own 00-verify-prerequisites.sh).
# Idempotent.
step "Step 14b: Installing Skill 38 (Conversational AI System v5.14) — sales brain + intelligent follow-up + dual-mode CS+support + typed KBs + weekly tune-up + model version freshness"

install_skill_38_conversational_ai_system() {
    local SKILL_SRC="$ONBOARDING_DIR/38-conversational-ai-system"
    local SKILL_DEST="$SKILLS_DIR/38-conversational-ai-system"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 38 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    # Idempotent: skip if dest version matches src
    if [ -f "$SKILL_DEST/skill-version.txt" ] && [ -d "$SKILL_DEST/protocols" ]; then
        local SKILL38_CURRENT
        SKILL38_CURRENT=$(cat "$SKILL_DEST/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        local SKILL38_SRC_VER
        SKILL38_SRC_VER=$(cat "$SKILL_SRC/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$SKILL38_CURRENT" ] && [ "$SKILL38_CURRENT" = "$SKILL38_SRC_VER" ]; then
            success "Skill 38 already installed at v${SKILL38_CURRENT}"
            chmod +x "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true
            return 0
        fi
        note "Skill 38 present at v${SKILL38_CURRENT:-?}, source is v${SKILL38_SRC_VER:-?} — refreshing"
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 38 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true

    success "Skill 38 (Conversational AI System v5.14) installed -> $SKILL_DEST"
    note "Skill 38 brings 27 protocols, 8 journey templates, 9 install scripts, 7 references."
    note "After this install completes, run: $SKILL_DEST/scripts/00-verify-prerequisites.sh"
    note "  then 01..08 in order. Skills 05, 10, 19, 29 must be installed FIRST."
    return 0
}

install_skill_38_conversational_ai_system

# ----------------------------------------------------------
# Step 14c: Installing Skill 39 (Real Estate Playbook & Property Intelligence)
# ----------------------------------------------------------
# Why: skill 39 is the real-estate VERTICAL on top of skill 38 (Conversational
# AI System). It adds property intelligence (geocode/lookup/comps/Street View
# via an operator-keyed provider abstraction — honest gap, never fabricated),
# buyer/seller/investor qualification, a showing scheduler, a 50-state disclosure
# pointer matrix, lead routing by agent specialty, open-house + pre-foreclosure
# playbooks (the latter pairs with skill 40), and an ADDITIVE Sales-Brain RE
# extension that drops into skill 38 without editing skill 38's own protocol.
# Emits <MASTER_FILES_DIR>/real-estate-events.jsonl. Idempotent.
step "Step 14c: Installing Skill 39 (Real Estate Playbook & Property Intelligence) — property intelligence + buyer/seller qualification + showing scheduler + state disclosure + lead routing + pre-foreclosure (pairs with Skill 40) + additive Sales-Brain RE extension"

install_skill_39_real_estate_playbook() {
    local SKILL_SRC="$ONBOARDING_DIR/39-real-estate-playbook"
    local SKILL_DEST="$SKILLS_DIR/39-real-estate-playbook"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 39 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    # Idempotent: skip if dest version matches src
    if [ -f "$SKILL_DEST/skill-version.txt" ] && [ -d "$SKILL_DEST/protocols" ]; then
        local SKILL39_CURRENT
        SKILL39_CURRENT=$(cat "$SKILL_DEST/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        local SKILL39_SRC_VER
        SKILL39_SRC_VER=$(cat "$SKILL_SRC/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$SKILL39_CURRENT" ] && [ "$SKILL39_CURRENT" = "$SKILL39_SRC_VER" ]; then
            success "Skill 39 already installed at v${SKILL39_CURRENT}"
            chmod +x "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true
            return 0
        fi
        note "Skill 39 present at v${SKILL39_CURRENT:-?}, source is v${SKILL39_SRC_VER:-?} — refreshing"
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 39 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true

    success "Skill 39 (Real Estate Playbook & Property Intelligence) installed -> $SKILL_DEST"
    note "Skill 39 is the real-estate vertical ON TOP of Skill 38 (a hard prerequisite, checked by its own 00-verify-prerequisites.sh)."
    note "After this install completes, run: $SKILL_DEST/scripts/00-verify-prerequisites.sh then 01..08 in order."
    note "All property-data provider keys are OPERATOR-SUPPLIED via env; absence is an honest gap, never fabricated data."
    return 0
}

install_skill_39_real_estate_playbook

# ----------------------------------------------------------
# Step 14d: Installing Skill 40 (ZHC Public Records Scraper)
# ----------------------------------------------------------
# Why: skill 40 is the tiered, compliance-first public-records intelligence
# layer and the data SIBLING of skill 39. address/ZIP -> county+state -> Tier 1
# (curated configs for 18 major counties) -> Tier 2 (platform-adapter framework
# + example adapters) -> Tier 3 (operator-buildable, validated config) -> else
# Tier 4 (HONEST GAP, never fabricated). robots.txt respected, ToS referenced
# per target, source+timestamp attribution; cost cap + per-day + per-target rate
# limits with up-front bulk cost estimate + operator confirm; 30-day cache.
# Emits <MASTER_FILES_DIR>/public-records-queries.jsonl. Idempotent.
step "Step 14d: Installing Skill 40 (ZHC Public Records Scraper) — tiered (curated counties / platform adapters / operator config / honest gap) + robots+ToS+attribution compliance + cost/rate caps + 30-day cache; data sibling of Skill 39"

install_skill_40_zhc_public_records_scraper() {
    local SKILL_SRC="$ONBOARDING_DIR/40-zhc-public-records-scraper"
    local SKILL_DEST="$SKILLS_DIR/40-zhc-public-records-scraper"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 40 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    # Idempotent: skip if dest version matches src
    if [ -f "$SKILL_DEST/skill-version.txt" ] && [ -d "$SKILL_DEST/protocols" ]; then
        local SKILL40_CURRENT
        SKILL40_CURRENT=$(cat "$SKILL_DEST/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        local SKILL40_SRC_VER
        SKILL40_SRC_VER=$(cat "$SKILL_SRC/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$SKILL40_CURRENT" ] && [ "$SKILL40_CURRENT" = "$SKILL40_SRC_VER" ]; then
            success "Skill 40 already installed at v${SKILL40_CURRENT}"
            chmod +x "$SKILL_DEST/scripts/"*.sh "$SKILL_DEST/scripts/adapters/"*.sh 2>/dev/null || true
            return 0
        fi
        note "Skill 40 present at v${SKILL40_CURRENT:-?}, source is v${SKILL40_SRC_VER:-?} — refreshing"
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 40 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/scripts/"*.sh "$SKILL_DEST/scripts/adapters/"*.sh 2>/dev/null || true

    success "Skill 40 (ZHC Public Records Scraper) installed -> $SKILL_DEST"
    note "Skill 40 is tiered + compliance-first: robots.txt respected, ToS referenced per target, every record attributed; cost/rate caps with bulk cost confirm; 30-day cache. NEVER fabricates a record (no source -> Tier 4 honest gap)."
    note "After this install completes, run: $SKILL_DEST/scripts/00-verify-prerequisites.sh then 01..04 in order; 05/06 are per-target (validate before any live run)."
    return 0
}

install_skill_40_zhc_public_records_scraper

# ----------------------------------------------------------
# Step 14e: Wire Skill 44 (Convert and Flow Operator) GHL env + fail-loud verify
# ----------------------------------------------------------
# Why: skill 44 ships the `caf` GHL operator CLI. The agent invokes it from the
# gateway PROCESS, which inherits env from openclaw.json `env.vars` (and, on a
# Hostinger VPS, from the docker-compose `env_file` /docker/<project>/.env) — NOT
# from ~/.openclaw/secrets/.env, which the gateway never loads. A client VPS
# (2026-06-11) proved the gap: creds lived only in secrets/.env and the docker
# env_file had empty `GOHIGHLEVEL_*=` placeholder lines (docker injects those as
# EMPTY STRINGS, masking everything), so caf died at
# "Error: GHL_LOCATION_ID environment variable is not set." while the install had
# already reported success. This step wires all 5 GHL vars into the
# gateway-inherited env via the skill's single-source wire-ghl-env.sh, then runs a
# fail-loud live verify (verify-ghl-live.sh) so we NEVER report skill-44 success
# when caf can't reach GHL. Genuinely-absent creds → installed-with-missing-prereqs
# (which vars are listed), never a fabricated success. Idempotent.
step "Step 14e: Wiring Skill 44 (Convert and Flow Operator) GHL creds into gateway-inherited env + fail-loud live verify"

install_skill_44_convert_and_flow_operator_env() {
    local SKILL_DEST="$SKILLS_DIR/44-convert-and-flow-operator"
    local WIRE="$SKILL_DEST/tools/engine/wire-ghl-env.sh"
    local VERIFY="$SKILL_DEST/tools/engine/verify-ghl-live.sh"

    if [ ! -f "$WIRE" ]; then
        warn "Skill 44 wire-ghl-env.sh not found at $WIRE — skipping env-wiring (older onboarding bundle?)"
        return 0
    fi
    chmod +x "$WIRE" "$VERIFY" 2>/dev/null || true

    # Mac rescue rule: the wire script NEVER restarts the gateway; it documents
    # that a launchctl kickstart may be needed for full inheritance. VPS: it
    # updates openclaw.json env.vars (gateway-inherited) and, if /docker is
    # reachable from this context, the host env_file (replacing empty placeholders).
    note "Wiring GHL env (env.vars deep-merge + VPS docker env_file placeholder replace)…"
    set +e
    OC_JSON="$OC_JSON" OC_SECRETS_ENV="$OC_SECRETS_ENV" bash "$WIRE"
    local WIRE_RC=$?
    set -e
    if [ "$WIRE_RC" -eq 2 ]; then
        warn "Skill 44 INSTALLED-WITH-MISSING-PREREQS — required GHL creds (GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_LOCATION_ID) absent on this box. Add them to $OC_SECRETS_ENV and re-run $WIRE. CLI is installed; it cannot reach GHL until then."
        add_to_list "installed" "44-convert-and-flow-operator (missing-prereqs: GHL creds)"
        return 0
    elif [ "$WIRE_RC" -ne 0 ]; then
        warn "Skill 44 wire-ghl-env.sh returned rc=$WIRE_RC — env wiring may be incomplete; see output above."
    else
        success "Skill 44 GHL env wired into gateway-inherited config."
    fi

    # Fail-loud live verify: a real read using ONLY inherited process env.
    if [ -f "$VERIFY" ]; then
        note "Running fail-loud live verify (verify-ghl-live.sh)…"
        set +e
        OC_SECRETS_ENV="$OC_SECRETS_ENV" bash "$VERIFY"
        local VERIFY_RC=$?
        set -e
        case "$VERIFY_RC" in
            0) success "Skill 44 LIVE-VERIFIED: caf reached GHL with a real read." ;;
            2) warn "Skill 44 installed-with-missing-prereqs (verify could not run a live read — creds absent). NOT a success; NOT a hard failure." ;;
            *) warn "Skill 44 LIVE VERIFY FAILED (rc=$VERIFY_RC): caf could NOT reach GHL despite creds present (VPS env-inheritance failure mode — env not inherited / empty docker placeholder / auth). Skill 44 is NOT live-verified. See output above; re-run $WIRE then force-recreate (VPS) or restart the gateway (Mac)." ;;
        esac
    fi
    return 0
}

install_skill_44_convert_and_flow_operator_env

# ----------------------------------------------------------
# Skill 47: Movie Producer (Automated Video Production — autonomous multi-pipeline video)
# ----------------------------------------------------------
# AGPLv3 BOUNDARY: this template install ONLY copies the Skill 47 folder
# (installer + wrapper + docs + our OWN Kie adapter files). It NEVER clones or
# vendors OpenMontage source here. The actual `git clone OpenMontage` + `make
# setup` + runtime-dep preflight happens on the CLIENT box per INSTALL.md, on the
# client's own optional keys. We only mark the skill's scripts executable and
# point the agent at the fail-loud preflight.
install_skill_47_movie_producer() {
    local SKILL_SRC="$ONBOARDING_DIR/47-movie-producer"
    local SKILL_DEST="$SKILLS_DIR/47-movie-producer"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 47 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    # Idempotent: skip if dest version matches src
    if [ -f "$SKILL_DEST/skill-version.txt" ] && [ -d "$SKILL_DEST/kie-adapters" ]; then
        local SKILL47_CURRENT SKILL47_SRC_VER
        SKILL47_CURRENT=$(cat "$SKILL_DEST/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        SKILL47_SRC_VER=$(cat "$SKILL_SRC/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$SKILL47_CURRENT" ] && [ "$SKILL47_CURRENT" = "$SKILL47_SRC_VER" ]; then
            success "Skill 47 already installed at v${SKILL47_CURRENT}"
            chmod +x "$SKILL_DEST/"*.sh 2>/dev/null || true
            return 0
        fi
        note "Skill 47 present at v${SKILL47_CURRENT:-?}, source is v${SKILL47_SRC_VER:-?} — refreshing"
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 47 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/"*.sh 2>/dev/null || true

    # SK1-63 (fleet-installer wiring): executive_producer.py's load_manifest()
    # resolves the manifest via a repo-root walk-up FIRST (finds universal-sops/
    # as a sibling of this skill dir under $SKILLS_DIR — already delivered above)
    # before it ever reaches the runtime-dir copy Skill 47's OWN install.sh
    # places at activation time (Step 4.5, when the client clones OpenMontage).
    # That walk-up fallback is the common case today, but it is NOT something
    # this fleet installer path guarantees on its own — a future single-skill
    # distribution channel, or universal-sops going missing/partial on a box,
    # would silently remove it. So mirror Skill 47's own Step 4.5 HERE too: a
    # pure local file copy (no clone, no npm/pip, no network) placing the
    # manifest at the SAME runtime path _runtime_manifest_path() expects
    # ($HOME/.openclaw/openmontage-runtime/, or OPENCLAW_OPENMONTAGE_DIR's
    # parent) so load_manifest() resolves even if the walk-up fallback ever
    # stops working. Skill 47 is optional/opt-in — never fail the whole fleet
    # install over this; warn and continue on any problem.
    local S47_MANIFEST_SRC="$SKILLS_DIR/universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json"
    local S47_OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"
    local S47_MANIFEST_DEST
    S47_MANIFEST_DEST="$(dirname "$S47_OPENMONTAGE_DIR")/VIDEO-PIPELINE-MANIFEST.json"
    if [ -f "$S47_MANIFEST_SRC" ]; then
        mkdir -p "$(dirname "$S47_MANIFEST_DEST")" 2>/dev/null
        if cp "$S47_MANIFEST_SRC" "$S47_MANIFEST_DEST" 2>>"$LOG_FILE" && \
           python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$S47_MANIFEST_DEST" 2>>"$LOG_FILE"; then
            success "Skill 47: VIDEO-PIPELINE-MANIFEST.json placed at $S47_MANIFEST_DEST (fleet-installer path)"
        else
            warn "Skill 47: could not place VIDEO-PIPELINE-MANIFEST.json at $S47_MANIFEST_DEST — load_manifest() will fall back to the universal-sops sibling walk-up (see $LOG_FILE)"
        fi
    else
        warn "Skill 47: universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json not found at $S47_MANIFEST_SRC — runtime-dir copy skipped (universal-sops install step above may have failed; load_manifest() will hard-exit 2 if this is never resolved)"
    fi

    success "Skill 47 (Movie Producer — Automated Video Production) installed -> $SKILL_DEST"
    note "Skill 47 powers the video dept Automated Video Production Specialist (OpenMontage Pipeline Operator)."
    note "AGPLv3: OpenMontage is cloned on the CLIENT box at activation per INSTALL.md — its source is NEVER vendored into this template."
    note "Before producing: run $SKILL_DEST/preflight.sh (fail-loud check for FFmpeg / Node>=18 / npx hyperframes / Piper); then INSTALL.md (clone + make setup + drop kie-adapters + KIE_API_KEY-only .env + low budget cap)."
    note "All asset generation routes through Kie.AI on the CLIENT's own KIE_API_KEY; native paid providers stay UNAVAILABLE. Free render engines + free stock corpus + Piper TTS are preserved."
    return 0
}

install_skill_47_movie_producer

# ----------------------------------------------------------
# Skill 48: Facebook & Instagram Ad Generator (paid-advertisement — 10-ad batch pipeline)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 48 folder (foreman +
# offline checkers + enforcement spine + vendored ghl_media.py + SOPs are read
# repo-side). NO external clone. All paid calls route through the CLIENT's own
# KIE_API_KEY (image gen) and the client's own location-scoped GoHighLevel PIT
# (image hosting) — never the operator's keys. PLAI is the only ad path (no Meta
# API). We mark the skill's scripts executable and point the agent at preflight.
install_skill_48_facebook_ad_generator() {
    local SKILL_SRC="$ONBOARDING_DIR/48-facebook-ad-generator"
    local SKILL_DEST="$SKILLS_DIR/48-facebook-ad-generator"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 48 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    # Idempotent: skip if dest version matches src
    if [ -f "$SKILL_DEST/skill-version.txt" ] && [ -f "$SKILL_DEST/scripts/ad_director.py" ]; then
        local SKILL48_CURRENT SKILL48_SRC_VER
        SKILL48_CURRENT=$(cat "$SKILL_DEST/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        SKILL48_SRC_VER=$(cat "$SKILL_SRC/skill-version.txt" 2>/dev/null | tr -d '[:space:]')
        if [ -n "$SKILL48_CURRENT" ] && [ "$SKILL48_CURRENT" = "$SKILL48_SRC_VER" ]; then
            success "Skill 48 already installed at v${SKILL48_CURRENT}"
            chmod +x "$SKILL_DEST/"*.sh 2>/dev/null || true
            return 0
        fi
        note "Skill 48 present at v${SKILL48_CURRENT:-?}, source is v${SKILL48_SRC_VER:-?} — refreshing"
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 48 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/"*.sh 2>/dev/null || true

    success "Skill 48 (Facebook & Instagram Ad Generator) installed -> $SKILL_DEST"
    note "Skill 48 powers the paid-advertisement Facebook & Instagram Ad-Run Producer + Direct-Response Ad Copywriter seats (10-ad batch: overlays → pick-10 → bodies/headlines/prompts → Kie gpt-image-* → PLAI-shape targeting → GoHighLevel hosting → copy-paste ad-text doc → PLAI handoff)."
    note "Image gen uses the CLIENT's own KIE_API_KEY; image hosting uses the client's own location-scoped GoHighLevel PIT (medias.write). PLAI is the only ad path — no direct Meta API."
    note "Before producing: run $SKILL_DEST/preflight.sh (fail-loud: python3, department + live agent + copy-capable seat, Telegram topic, KIE_API_KEY, GoHighLevel location PIT, money ceiling); then INSTALL.md."
    return 0
}

install_skill_48_facebook_ad_generator

# ----------------------------------------------------------
# Skill 49: Signature Funnel (SACRED 12-section funnel methodology + gates)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 49 folder (SKILL.md,
# MASTERDOC.md, FUNNEL-MANIFEST.json, structure/funnel_structure.json, the intake
# gate, the BAKED provider-agnostic copy + image prompts, the five fail-closed
# deterministic model-free provers, the no-skip orchestrator, and the canonical
# fail-closed entry). NO external clone. Skill 49 owns the IP + the gates: it
# AUTHORS the SACRED 12-section Hero copy + the per-section 5,000-19,000-char
# gpt-image-2 prompts inside its own fail-closed pipeline, then DELEGATES image
# generation to Skill 47 (kie_image.py) and ALL GoHighLevel media + funnel/page
# build to Skill 6 (the ONE GHL delivery rail). It never forks a Kie call or a GHL
# REST call. A "signature funnel" request routes here through the shared STEP-0
# funnel-engine selector in Skill 6 (06-ghl-install-pages/funnel-engines/registry.json
# — this is the first registered engine). On a client box it uses the CLIENT's own
# configured providers/keys — never the operator's, never Anthropic model ids. Skill
# 6, Skill 47, and Skill 07 (Kie.ai setup) are prerequisites.
install_skill_49_signature_funnel() {
    local SKILL_SRC="$ONBOARDING_DIR/49-signature-funnel"
    local SKILL_DEST="$SKILLS_DIR/49-signature-funnel"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 49 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 49 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/signature-funnel-entry.sh" "$SKILL_DEST/run_signature_funnel.py" \
             "$SKILL_DEST/verify.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true

    success "Skill 49 (Signature Funnel) installed -> $SKILL_DEST"
    note "Skill 49 is the methodology + enforcement layer for the Trevor Otts Signature Funnel: the SACRED 12-section Hero copy system, per-section 5,000-19,000-char gpt-image-2 prompts, and a configurable 3/5/7-step GHL funnel (Main -> Checkout -> Upsell-1 -> Downsell-1 -> Upsell-2 -> Downsell-2 -> Thank-You with accept/decline branching), each gated as a SACRED structure by five fail-closed deterministic model-free provers (intake, 12-section copy contract, image-prompt two-floor gate, no-pitch thank-you + image-provenance, signed certificate)."
    note "It runs P0..P10 through one canonical entry (signature-funnel-entry.sh) with a deps/bypass-scan/hash-pin/nonce fail-closed gate, then delegates image generation to Skill 47 (kie_image.py) and ALL GHL media + funnel/page build to Skill 6 (the ONE GHL delivery rail). A 'signature funnel' request routes here via the shared STEP-0 funnel-engine selector in Skill 6. Nothing is published without explicit human approval. Skill 6, Skill 47, and Skill 07 (Kie.ai) are prerequisites."
    return 0
}

install_skill_49_signature_funnel

# ----------------------------------------------------------
# Skill 50: Email Engine (governed email skill + Email Superlibrary)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 50 folder (SKILL.md,
# EMAIL-MANIFEST.json, the intake gate, the email-library catalog + prebuilt index,
# the email_matcher, the model-free floor prover prove-email.py, and the draft-only
# build-plan emitter). NO external clone. Skill 50 owns the IP + the gates: it
# SELECTS a framework, GENERATES corpus-faithful copy, QCs it against prove-email.py,
# and hands a DRAFT-ONLY deploy plan to the Convert & Flow (GoHighLevel) operator
# (Skill 44) — nothing is ever sent without explicit human approval. It never forks
# the sender. On a client box it uses the CLIENT's own configured providers/keys —
# never the operator's, never Anthropic model ids. Skill 44 is the deploy prerequisite.
install_skill_50_email_engine() {
    local SKILL_SRC="$ONBOARDING_DIR/50-email-engine"
    local SKILL_DEST="$SKILLS_DIR/50-email-engine"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 50 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 50 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/email-engine-entry.sh" "$SKILL_DEST/run_email_engine.py" \
             "$SKILL_DEST/verify.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/tools/"*.py 2>/dev/null || true

    success "Skill 50 (Email Engine) installed -> $SKILL_DEST"
    note "Skill 50 is the governed email skill + Email Superlibrary for the marketing/CRM/sales seats: 13 frameworks, 12 persona styles, the buyer-type -> email# -> framework map, the 4 sequence objectives, the 10-email landing-page promo sequence and the 12-email buyer-type/high-ticket-appointment sequences, each gated as a SACRED structure by the deterministic model-free floor prover prove-email.py."
    note "It runs P1 SELECT -> P2 GENERATE -> P3 QC -> P4 DEPLOY through one canonical entry (email-engine-entry.sh) with a deps/bypass/hash-pin/nonce fail-closed gate, then hands a DRAFT-ONLY build plan to the Convert & Flow operator (Skill 44) for deploy. Nothing is ever sent without explicit human approval. Skill 44 is the deploy prerequisite."
    return 0
}

install_skill_50_email_engine

# ----------------------------------------------------------
# Skill 51: Signature Presentation (methodology layer for the presentations dept)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 51 folder (MASTERDOC.md,
# the 8-Questions intake gate, the four teaching frames, the sacred-structure
# ledger, and the three fail-closed provers). NO external clone. Skill 51 is a
# governed DECK TYPE (deck_type: signature_presentation) that runs THROUGH the
# Presentations department engine (skill 23's build_deck.py) — it never forks the
# render path. Its provers wire into the department's scripts/ at wire time.
# Skill 23 (Presentations department engine) is the prerequisite.
install_skill_51_signature_presentation() {
    local SKILL_SRC="$ONBOARDING_DIR/51-signature-presentation"
    local SKILL_DEST="$SKILLS_DIR/51-signature-presentation"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 51 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 51 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true

    success "Skill 51 (Signature Presentation) installed -> $SKILL_DEST"
    note "Skill 51 adds the signature_presentation deck type to the Presentations department: the 4-phase, minimum-100-slide signature-talk methodology (Avatar -> Signature Story -> Transformational Teaching -> Purpose Pitch), gated by three fail-closed provers (8-Questions intake, sacred-structure ledger, Phase-3 no-pitch hygiene) and four teaching frames (The Rulebook, The Vault, The Quest, The Original)."
    note "It never forks build_deck.py — the department engine (skill 23) does all rendering, assembly, delivery, and Kanban. Skill 23 is the prerequisite."
    return 0
}

install_skill_51_signature_presentation

# ----------------------------------------------------------
# Skill 52: Avatar Alchemist (Avatar Alchemist brand-intelligence engine + gates)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 52 folder (SKILL.md,
# MASTERDOC.md, AA-PIPELINE-MANIFEST.json, AVATAR-MANIFEST.json, the 40 baked
# provider-agnostic generator prompt dirs, the intake + Book/Brand version selector,
# the foreman aa_director.py, the fail-closed model-free provers, the packager, and
# the canonical fail-closed entry). NO external clone. Skill 52 owns the IP + the
# gates: it turns ONE completed brand-intake interview into the full brand-intelligence
# package — 40 generators across 7 subsystems (Avatar Core, Awareness, Bios, Tone,
# a 13-set Facebook Ad system, Booking Bots, Landing/Hero) → 16 named deliverables
# (37 documents), replacing the retired 233-node n8n / Airtable / Google Drive / Slack /
# Gmail workflow with a LOCAL-ONLY pipeline on the CLIENT's own model providers — never
# the operator's, never Anthropic model ids. A Book/Brand version selector runs FIRST
# (version=brand runs the 40-stage pipeline; version=book routes to Skill 53 or parks
# fail-closed "book-skill-not-available"). Every SACRED count/floor is MEASURED by a
# model-free prover (self-reported counts are ignored). Delivery is a labeled ~/Downloads
# bundle with a signed provenance certificate; it touches no n8n / Airtable / Drive /
# Slack / Gmail at runtime. Cross-linked with (never merged into) Skill 55 Product Bio.
# The tone subsystem is a lockstep copy of the shared shared-utils/tone-writing-core/.
install_skill_52_avatar_intelligence() {
    local SKILL_SRC="$ONBOARDING_DIR/52-avatar-alchemist"
    local SKILL_DEST="$SKILLS_DIR/52-avatar-alchemist"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 52 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 52 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/entry.sh" "$SKILL_DEST/preflight.sh" \
             "$SKILL_DEST/verify.sh" "$SKILL_DEST/verify-deps.sh" \
             "$SKILL_DEST/qc-avatar-alchemist.sh" "$SKILL_DEST/install.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true

    success "Skill 52 (Avatar Alchemist) installed -> $SKILL_DEST"
    note "Skill 52 is the methodology + enforcement layer for the Trevor Otts Avatar Alchemist brand-intelligence package: it turns ONE completed brand-intake interview into 40 generators across 7 subsystems (Avatar Core, Awareness, Bios, Tone, a 13-set Facebook Ad system, Booking Bots, Landing/Hero) -> 16 named deliverables (37 documents). A Book/Brand version selector runs FIRST (version=brand runs the 40-stage pipeline; version=book routes to Skill 53 or parks fail-closed 'book-skill-not-available', never the brand pipeline). Every SACRED count/floor is MEASURED by fail-closed, model-free provers (self-reported counts are ignored)."
    note "It runs through the ONE sanctioned front door (entry.sh: deps -> bypass-scan -> hash-pin -> nonce) then the foreman scripts/aa_director.py, which schedules the 40 stages in dependency waves on the CLIENT's own model providers — never the operator's, never Anthropic model ids (G-NOANTHROPIC hard-fails any run whose resolved model id matches /anthropic|claude/i). Delivery is a labeled ~/Downloads bundle with a signed provenance certificate on a full 40/40 pass; it replaces the retired 233-node n8n / Airtable / Google Drive / Slack / Gmail workflow with a LOCAL-ONLY pipeline (no n8n / Airtable / Drive / Slack / Gmail at runtime). Cross-linked with (never merged into) Skill 55 Product Bio. Standalone — no prerequisite skill."
    return 0
}

install_skill_52_avatar_intelligence

# ----------------------------------------------------------
# Skill 53: Book Writer (Avatar Alchemist, BOOK version — ghostwriting engine + gates)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 53 folder (SKILL.md,
# MASTERDOC.md, GOLDEN-BOOK-BIBLE.md, BOOK-WRITER-MANIFEST.json, the baked
# provider-agnostic prompt dirs — stages 04-08 are a lockstep copy of the shared
# shared-utils/tone-writing-core — the Book/Brand selector intake, the twelve
# fail-closed model-free provers, the deterministic assembler/certifier, the
# canonical fail-closed entry, the 7 dispatchable role SOPs, and the worked
# golden-Marcus-Halloway example). NO external clone. Skill 53 is the BOOK
# version of the Avatar Alchemist (Skill 52 is the BRAND version): the shared
# Book/Brand selector (Q0) routes version=book here and version=brand to Skill
# 52 — an explicit, receipted hand-off, never a silent cross-version fallback.
# It turns ONE completed book-intake interview into a tone-matched 12-chapter
# nonfiction book plus companion assets (avatar dossier, the blended "The
# {First} {Last} Tone", locked title/subtitle + approved outline, print-ready
# manuscript, a 30-Day Challenge, an AI cover prompt, plus 4x3x3 offer-book
# extras handed to Skill 51), replacing the retired 8-workflow n8n ghostwriting
# factory (the 153-node "Book Writer" + the 121-node "4x3x3 w Book Writer") with
# a LOCAL-ONLY pipeline on the CLIENT's own model providers — never the
# operator's, never Anthropic model ids. Every SACRED count/floor is MEASURED by
# a model-free prover (self-reported counts are ignored); a run cannot claim
# "done" without a signed PROCESS-CERTIFICATE. Cross-linked with (never merged
# into) Skill 54 Anthology Writer; both bake a lockstep copy of the shared
# shared-utils/tone-writing-core/. Standalone — no prerequisite skill.
install_skill_53_book_writer() {
    local SKILL_SRC="$ONBOARDING_DIR/53-book-writer"
    local SKILL_DEST="$SKILLS_DIR/53-book-writer"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 53 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 53 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/book-writer-entry.sh" "$SKILL_DEST/run_book_writer.py" \
             "$SKILL_DEST/verify.sh" "$SKILL_DEST/verify-deps.sh" \
             "$SKILL_DEST/preflight.sh" "$SKILL_DEST/qc-book-writer.sh" \
             "$SKILL_DEST/install.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true
    chmod +x "$SKILL_DEST/examples/golden-marcus-halloway/broken-variants/make_broken.py" 2>/dev/null || true

    success "Skill 53 (Book Writer) installed -> $SKILL_DEST"
    note "Skill 53 is the BOOK version of the Avatar Alchemist (Skill 52 is the BRAND version): it turns ONE completed book-intake interview into a tone-matched 12-chapter nonfiction book plus companion assets — avatar dossier, the blended 'The {First} {Last} Tone', locked title/subtitle + approved outline, print-ready manuscript, a 30-Day Challenge, and an AI cover prompt — delivered as labeled files in ~/Downloads. Modes full (flagship 12-chapter book) and 4x3x3 (offer book: 30 titles / 4 Transformational Outcomes / KP doc / 433_Deck_Data.json handed to Skill 51). The shared Book/Brand selector (Q0) routes version=book here and version=brand to Skill 52 — an explicit, receipted hand-off, never a silent cross-version fallback."
    note "It runs through the ONE sanctioned front door (book-writer-entry.sh: deps -> bypass-scan -> hash-pin -> nonce) then run_book_writer.py, the deterministic assembler/certifier, which walks phases P0->P8 in order with NO skips (intake -> avatar -> tone -> titles-gate -> outline-gate -> four STRICTLY-SEQUENTIAL chapter batches with proven continuity -> package -> QC -> deliver), with in-chat checkpoint approvals (GATE-1 titles / GATE-2 outline / GATE-3 approval / GATE-4 second revision). Twelve fail-closed provers MEASURE the stripped text (12 chapters exactly, 2000-3500 stripped words each, batch continuity, blended tone >= 3000 stripped words, 30-Day Challenge exactly 30 days, 4x3x3 counts, title lock byte-exact everywhere, no placeholders, no Anthropic model ids, anonymization); a full pass mints a signed PROCESS-CERTIFICATE ('done' is claimed only with the certificate path). Runs on the CLIENT's own model providers — never the operator's, never Anthropic model ids. Cross-linked with (never merged into) Skill 54 Anthology Writer; both share a lockstep copy of shared-utils/tone-writing-core/. Standalone — no prerequisite skill."
    return 0
}

install_skill_53_book_writer

# ----------------------------------------------------------
# Skill 54: Anthology Writer (multi-contributor anthology chapter engine + gates)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 54 folder (SKILL.md,
# MASTERDOC.md, ANTHOLOGY-MANIFEST.json, the baked provider-agnostic authoring
# prompts (06 suggested-titles / 07 book-blurb / 08 create-outline / 09
# write-chapter / 10 chapter-rewrite) plus a lockstep copy of the shared tone
# stages 04-08, the locked intake schema, the fail-closed model-free provers,
# the deterministic state machine, the canonical fail-closed entry, and the
# worked golden-unbroken-ground example). NO external clone. Skill 54 is the
# SEPARATE sibling of Skill 53 (Book Writer) — Trevor's standing decision, never
# consolidated — sharing the ONE shared-utils/tone-writing-core: the anthology
# is many contributors, one chapter each; the book is one author, many chapters.
# It turns ONE contributor intake (anthology title, contributor name, chapter
# premise, real personal stories) into a finished, gated anthology chapter
# (2,000-3,500 words) in that contributor's blended signature voice, plus the
# supporting blended tone doc, locked title/subtitle, blurb, and outline,
# delivered as a labeled LOCAL bundle, replacing the source n8n / Airtable /
# Google Docs / Slack / Gmail workflow with a LOCAL-ONLY pipeline on the
# CLIENT's own model providers — never the operator's, never Anthropic model
# ids. Every SACRED floor is MEASURED by a model-free prover (self-reported
# counts are ignored); a run cannot claim "done" without a signed
# PROCESS-CERTIFICATE. Cross-linked with (never merged into) Skill 53 Book
# Writer. Standalone — no prerequisite skill.
install_skill_54_anthology_writer() {
    local SKILL_SRC="$ONBOARDING_DIR/54-anthology-writer"
    local SKILL_DEST="$SKILLS_DIR/54-anthology-writer"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 54 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 54 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/anthology-entry.sh" "$SKILL_DEST/run_anthology.py" \
             "$SKILL_DEST/verify.sh" "$SKILL_DEST/verify-deps.sh" \
             "$SKILL_DEST/preflight.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true

    success "Skill 54 (Anthology Writer) installed -> $SKILL_DEST"
    note "Skill 54 is the methodology + enforcement layer for a multi-contributor anthology: one finished chapter per contributor, authored in that contributor's blended signature voice, gated so nothing ships that missed a SACRED floor. It turns ONE contributor intake (anthology title, contributor name, chapter premise, real personal stories) into a gated 2,000-3,500-word chapter plus its supporting tone doc, locked title/subtitle, blurb, and outline — delivered as a labeled LOCAL bundle in ~/Downloads. Skill 54 (Anthology Writer) and Skill 53 (Book Writer) are SEPARATE skills (Trevor's standing decision, never consolidated) that share the ONE shared-utils/tone-writing-core: the anthology is many contributors, one chapter each; the book is one author, many chapters."
    note "It runs through the ONE sanctioned front door (anthology-entry.sh: deps -> bypass-scan -> hash-pin -> nonce) then run_anthology.py, the deterministic state machine, which walks phases P0 INTAKE -> P1 FIDELITY -> P2 TONE -> P3 TONE-QC -> P4 TITLE-LOCK -> P5 CHAPTER -> P6 CHAPTER-QC -> P7 DELIVER with NO phase skips, one contributor at a time. Fail-closed model-free provers MEASURE the stripped text (intake completeness + no credential-shaped fields, prompt-fidelity sha256 pins, tone-core lockstep, exactly 4 blended tone influences, tone floor >= 3,000 stripped words, chapter band 2,000-3,500 stripped words, completion-verification block, no placeholders, title lock + story placement byte-exact, no Anthropic model ids, a 2-rewrite budget per contributor); a full pass mints a signed PROCESS-CERTIFICATE ('done' is claimed only with the certificate path). Runs on the CLIENT's own model providers — never the operator's, never Anthropic model ids (aw_build_check.py / G-NOANTHROPIC hard-fails any run whose ledger shows an /anthropic|claude/i id). Cross-linked with (never merged into) Skill 53 Book Writer. Standalone — no prerequisite skill."
    return 0
}

install_skill_54_anthology_writer

# ----------------------------------------------------------
# Skill 55: Product Bio Engine (master-brain product bio methodology + gates)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 55 folder (SKILL.md,
# MASTERDOC.md, PRODUCT-BIO-MANIFEST.json, the two BAKED sha256-pinned IP prompts,
# the intake gate + schema, the model-map template, the five fail-closed model-free
# provers, the no-skip orchestrator, and the canonical fail-closed entry). NO
# external clone. Skill 55 owns the IP + the gates: it turns a 4-field intake into
# the 6,000-7,000-word, 10-section master-brain product bio + its Google-Docs-
# importable HTML, replacing the retired 25-node n8n / Google Drive / Slack / Gmail
# workflow with a LOCAL-ONLY pipeline on the CLIENT's own model providers — never
# the operator's, never Anthropic model ids. Every SACRED count is MEASURED by a
# model-free prover (self-reported counts are ignored). Delivery is a labeled
# ~/Downloads bundle; it touches no n8n / Drive / Slack / Gmail / Airtable at
# runtime. Standalone — no prerequisite skill. Cross-linked with (never merged
# into) Skill 52 Avatar Alchemist.
install_skill_55_product_bio() {
    local SKILL_SRC="$ONBOARDING_DIR/55-product-bio"
    local SKILL_DEST="$SKILLS_DIR/55-product-bio"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 55 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 55 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/product-bio-entry.sh" "$SKILL_DEST/run_product_bio.py" \
             "$SKILL_DEST/verify.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true

    success "Skill 55 (Product Bio Engine) installed -> $SKILL_DEST"
    note "Skill 55 is the methodology + enforcement layer for the Trevor Otts master-brain product bio: a 6,000-7,000-word, 10-section sales knowledge base (10 intros, 15-20 power adjectives, ICP, description, positioning, 8-10 objections, 10-12 FAQs, 8-10 social proof, StoryBrand 2.0, 24 named signature closes + a completion-verification block) AND its Google-Docs-importable HTML, from a 4-field intake. It bakes two verbatim sha256-pinned IP prompts and gates every SACRED count with five fail-closed model-free provers that MEASURE the stripped text (self-reported counts are ignored)."
    note "It runs P0 INTAKE -> P1 FIDELITY -> P2 BIO -> P3 BIO-QC -> P4 HTML -> P5 HTML-QC -> P6 DELIVER through one canonical entry (product-bio-entry.sh) with a deps/bypass-scan/hash-pin/nonce fail-closed gate, then delivers a labeled ~/Downloads bundle + a signed PROCESS-CERTIFICATE. It replaces the retired 25-node n8n / Google Drive / Slack / Gmail workflow with a LOCAL-ONLY pipeline on the CLIENT's own model providers — never the operator's, never Anthropic model ids; no n8n / Drive / Slack / Gmail / Airtable at runtime. Standalone — no prerequisite skill."
    return 0
}

install_skill_55_product_bio

# ----------------------------------------------------------
# Skill 56: Sales Page Assets (Direct-Response methodology + gates)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 56 folder (SKILL.md,
# MASTERDOC.md, SALESPAGE-MANIFEST.json, the 12-field intake gate + schema, the
# BAKED provider-agnostic copy/image prompts, the labeling grammar + structure,
# the eight fail-closed model-free provers, the no-skip orchestrator, and the
# canonical fail-closed entry). NO external clone. Skill 56 is the DIRECT-RESPONSE
# sibling of Skill 49 (Signature Funnel): it AUTHORS the 8-section main sales page
# (A/B + countdown timer), the Trevor Otts 9-section upsell (A/B), a downsell
# recovery page, the Sovereign Architect 6,500-7,100-word high-ticket long-form,
# 40-80-word order-bump copy with a checkbox close, and a slice-covered image plan,
# from one "Ultimate AI Sales Page Writer" survey. Every SACRED count/band is
# MEASURED by a model-free prover (self-reported counts are ignored). It registers
# as the SECOND STEP-0 funnel engine in Skill 6's registry, then DELEGATES image
# generation to Skill 47 (or the client's OWN image provider) and ALL GoHighLevel
# media + funnel/page build to Skill 6 (the ONE GHL delivery rail); the order-bump
# routes to Skill 44. It OWNS the <client>__<funnel>__<stage>__<type>__vNN labeling
# grammar (reciprocal with Skill 49). On a client box it uses the CLIENT's own model
# providers — never the operator's, never Anthropic model ids. Skill 6, Skill 47,
# and Skill 44 are prerequisites.
install_skill_56_sales_page_assets() {
    local SKILL_SRC="$ONBOARDING_DIR/56-sales-page-assets"
    local SKILL_DEST="$SKILLS_DIR/56-sales-page-assets"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 56 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 56 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/sales-page-assets-entry.sh" "$SKILL_DEST/run_sales_page_assets.py" \
             "$SKILL_DEST/verify.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true

    success "Skill 56 (Sales Page Assets) installed -> $SKILL_DEST"
    note "Skill 56 is the methodology + enforcement layer for the Trevor Otts Direct-Response sales-page asset stack (the DR sibling of Skill 49): the 8-section main sales page (A/B + countdown timer), the Trevor Otts 9-section upsell (A/B personas), a downsell recovery page, the Sovereign Architect 6,500-7,100-word high-ticket long-form page, 40-80-word order-bump copy with a checkbox close, and a slice-covered image plan, from one 'Ultimate AI Sales Page Writer' survey. It bakes provider-agnostic copy/image prompts and gates every SACRED count/band with eight fail-closed model-free provers (prove_sp_intake / image_plan / main_structure / upsell_structure / highticket_band / bump_band / bundle / cert) that MEASURE the stripped text (self-reported counts are ignored)."
    note "It runs P0 INTAKE -> P1 IMAGE-PLAN -> P2 IMAGES -> P3 COPY x7 -> P4 MEDIA -> P5 FRAGMENTS -> P6 DOCS -> P7 BUNDLE -> P8 DELIVER -> P9 HANDOFF through one canonical entry (sales-page-assets-entry.sh) with a deps/version/hash-pin/bypass-scan/0600-nonce fail-closed gate, then issues a signed PROCESS-CERTIFICATE only on all-phases-pass. It registers as the SECOND STEP-0 funnel engine in Skill 6's registry, delegates image generation to Skill 47 (or the client's OWN image provider) and ALL GHL media + funnel/page build to Skill 6 (the ONE GHL delivery rail), and routes the order-bump to Skill 44. It OWNS the <client>__<funnel>__<stage>__<type>__vNN labeling grammar (reciprocal with Skill 49). Client runtime uses the CLIENT's own model providers — never the operator's, never Anthropic model ids. Skill 6, Skill 47, and Skill 44 are prerequisites."
    return 0
}

install_skill_56_sales_page_assets

# ----------------------------------------------------------
# Skill 57: Social Media in a Box (unified organic social engine; supersedes Skill 35)
# ----------------------------------------------------------
# Self-contained: this template install copies the Skill 57 folder (SKILL.md,
# SOCIAL-MANIFEST.json, the baked prompts/, config/bands.json, the fail-closed
# model-free provers scripts/*.py, the deterministic orchestrator run_social_media.py,
# the front-door-nonce entry social-media-entry.sh, the read-only verify.sh, the
# weekly-theme cron registrar, and the golden fixtures). NO external clone, NO n8n,
# NO Airtable at runtime. Skill 57 is the ONE governed ORGANIC social engine for the
# social-media / marketing / podcast / graphics / crm seats: it runs the weekly
# 7-part cliffhanger, carousels, Sora video, podcast, newsletter, blog, engagement
# report and the client-driven creative modes through ONE canonical entry, mints a
# signed PROCESS-CERTIFICATE proving ZERO Anthropic per run (CLIENT providers only —
# the client's own OpenRouter model + fallbacks / Gemini vision QC / Kie.ai media and
# the client's own GoHighLevel PIT + accounts), and posts GHL-direct to the client's
# own location. It never hand-rolls a poster (BYPASS-SCAN refuses one). The shared
# cross-department procedure ships in universal-sops/social-media-craft/ (delivered
# with the universal-sops tree copied above). Skill 35 retirement is PARKED.
install_skill_57_social_media_in_a_box() {
    local SKILL_SRC="$ONBOARDING_DIR/57-social-media-in-a-box"
    local SKILL_DEST="$SKILLS_DIR/57-social-media-in-a-box"

    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 57 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi

    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 57 from $SKILL_SRC -> $SKILL_DEST"
        return 0
    }
    chmod +x "$SKILL_DEST/social-media-entry.sh" "$SKILL_DEST/run_social_media.py" \
             "$SKILL_DEST/verify.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py "$SKILL_DEST/scripts/"*.sh 2>/dev/null || true

    success "Skill 57 (Social Media in a Box) installed -> $SKILL_DEST"
    note "Skill 57 is the ONE governed ORGANIC social engine for the social-media / marketing / podcast / graphics / crm seats: the weekly 7-part cliffhanger, carousels, Sora video, podcast (audio + 1400x1400 cover), newsletter, blog, read-only engagement report, and the client-driven creative modes (brief / campaign / client-copy / reactive) plus the twitter publisher sub-mode — all through ONE canonical entry (social-media-entry.sh) with a deps / BYPASS-SCAN / hash-pin / nonce fail-closed gate and a no-phase-skip machine."
    note "Every run mints a signed PROCESS-CERTIFICATE proving ZERO Anthropic per run (CLIENT providers only: OpenRouter model + 2 fallbacks / Gemini vision QC / Kie.ai media) and the client's OWN GoHighLevel PIT + accounts, posts GHL-direct, and claims done only from the certificate PLUS a live GHL post-listing. NO n8n / NO Airtable at runtime. Shared procedure: universal-sops/social-media-craft/. Supersedes Skill 35 (per-client retirement is PARKED pending an explicit go)."
    return 0
}

install_skill_57_social_media_in_a_box

# ----------------------------------------------------------
# Step 15: Register Skill 32's materialize-dept-agents.sh (v10.13.18)
# ----------------------------------------------------------
# Why: pre-v10.13.18 Skill 23 marked depts "done" purely on file presence,
# Skill 32 Phase 4 was prose-not-code, and Skill 37 closeout sent a
# celebration claiming an N-dept M-role workforce was LIVE while the
# OpenClaw runtime saw exactly one agent (the default "main"). The new
# materialize-dept-agents.sh actually mutates openclaw.json agents.list[]
# so dept workspace folders become real runtime agents. Skill 37 v10.13.18
# invokes it as a binding preflight in Step 1 (Command Center) — this step
# just guarantees the script is present, executable, and discoverable.
step "Step 15: Registering Skill 32 materialize-dept-agents.sh (the materialize-dept-agents binding contract)"

install_materialize_dept_agents() {
    local SRC="$ONBOARDING_DIR/32-command-center-setup/scripts/materialize-dept-agents.sh"
    local DEST_DIR="$SKILLS_DIR/32-command-center-setup/scripts"
    local DEST="$DEST_DIR/materialize-dept-agents.sh"

    if [ ! -f "$SRC" ]; then
        warn "materialize-dept-agents.sh not found in onboarding bundle at $SRC — skipping (older bundle?)"
        warn "Skill 37 closeout will REFUSE to mark commandCenterStatus=done without this script — onboarding is incomplete."
        return 0
    fi

    mkdir -p "$DEST_DIR"
    cp "$SRC" "$DEST" 2>>"$LOG_FILE" || {
        warn "Failed to copy materialize-dept-agents.sh → $DEST"
        return 1
    }
    chmod +x "$DEST" 2>/dev/null || true

    # Sanity-check: script must be executable and pass bash -n
    if [ ! -x "$DEST" ]; then
        warn "materialize-dept-agents.sh installed but not executable at $DEST"
        return 1
    fi
    if ! bash -n "$DEST" 2>>"$LOG_FILE"; then
        warn "materialize-dept-agents.sh installed but failed bash syntax check"
        return 1
    fi

    success "Skill 32 materialize-dept-agents.sh installed → $DEST"
    note "Skill 37 closeout's Step 1 will invoke this script automatically and verify agents.list[].length >= 2 before marking commandCenterStatus=done."
    return 0
}

install_materialize_dept_agents

# ----------------------------------------------------------
# Step 15b: Copy run-full-install.sh (D5 both-paths delivery; v14.27.0)
# ----------------------------------------------------------
# update-skills.sh invokes run-full-install.sh --update-only after every skill
# sync to refresh the CC web-app on existing boxes. This step ensures the script
# is present at $SKILLS_DIR/32-command-center-setup/scripts/ on fresh installs
# too (same location that update-skills.sh looks for it). The Skill-37 closeout
# agent invokes run-full-install.sh directly for the full Phase 6 install.
install_run_full_install_sh() {
    local SRC="$ONBOARDING_DIR/32-command-center-setup/scripts/run-full-install.sh"
    local DEST_DIR="$SKILLS_DIR/32-command-center-setup/scripts"
    local DEST="$DEST_DIR/run-full-install.sh"

    if [ ! -f "$SRC" ]; then
        warn "run-full-install.sh not found in onboarding bundle at $SRC — skipping (older bundle?)"
        return 0
    fi

    mkdir -p "$DEST_DIR"
    cp "$SRC" "$DEST" 2>>"$LOG_FILE" || {
        warn "Failed to copy run-full-install.sh → $DEST"
        return 1
    }
    chmod +x "$DEST" 2>/dev/null || true
    success "Skill 32 run-full-install.sh installed → $DEST (D5 both-paths CC refresh)"
    return 0
}

install_run_full_install_sh

# ----------------------------------------------------------
# Telegram diagnostic note (v10.0.1)
# ----------------------------------------------------------
# Surfaces just the Telegram-specific outcome — the full install summary
# below will also show any errors/warnings from the entire run.
case "$TELEGRAM_LAST_RESULT" in
    sent:*|"") : ;;
    *)
        warn "Telegram progress messages didn't all go through (this install's notifications only — your daily Telegram chats are unaffected)."
        ;;
esac

# ----------------------------------------------------------
# v10.13.12: Auto-kickoff Stage 2 / Wave execution
# ----------------------------------------------------------
# BMW-off-the-lot fix: previously the owner had to paste the kickoff text
# block to their bot to trigger Wave 1-5 execution. Now install.sh schedules
# a one-shot cron that fires ~3 minutes after install completes, delivering
# the kickoff synthetically. The agent receives it, reads AGENTS.md's
# UPDATE PENDING block, and starts Wave 1 autonomously. Owner only needs
# to engage at Wave 5 (the AI Workforce interview, which requires owner
# input that can't be delegated). Mirrors the VPS v10.14.12 fix.
#
# Bulletproof design: A → B → C fallback chain.
#   A. openclaw cron one-shot (preferred)
#   B. Direct Telegram ingress-spool write (fallback when A fails)
#   C. Existing manual-paste completion notice (always present as safety net)
# Failure of A and B does NOT block install completion — install always exits 0.

# --- Mechanism A: openclaw cron one-shot (preferred) ---
_kickoff_mech_a_cron() {
    local chat_id="$1"
    local kickoff_msg="$2"

    if ! command -v openclaw >/dev/null 2>&1; then
        return 1
    fi

    if openclaw cron list 2>/dev/null | grep -qE "auto-kickoff-"; then
        note "Auto-kickoff cron already present from a prior install — skipping mechanism A (treat as success)."
        return 0
    fi

    local target_ts target_min target_hour target_day target_month
    if date -u -d '+3 minutes' '+%s' >/dev/null 2>&1; then
        target_ts=$(date -u -d '+3 minutes' '+%s')
    else
        target_ts=$(date -u -v+3M '+%s' 2>/dev/null)
    fi
    [ -z "$target_ts" ] && return 1

    target_min=$(date -u -d "@$target_ts" '+%M' 2>/dev/null || date -u -r "$target_ts" '+%M' 2>/dev/null)
    target_hour=$(date -u -d "@$target_ts" '+%H' 2>/dev/null || date -u -r "$target_ts" '+%H' 2>/dev/null)
    target_day=$(date -u -d "@$target_ts" '+%d' 2>/dev/null || date -u -r "$target_ts" '+%d' 2>/dev/null)
    target_month=$(date -u -d "@$target_ts" '+%m' 2>/dev/null || date -u -r "$target_ts" '+%m' 2>/dev/null)

    local cron_expr="$target_min $target_hour $target_day $target_month *"
    local cron_name="auto-kickoff-${ONBOARDING_VERSION}-$(date +%s)"
    local full_msg
    full_msg="$kickoff_msg

IMPORTANT — Cron self-cleanup (do this BEFORE Wave 1): install.sh scheduled this kickoff via a one-shot cron named '$cron_name'. Delete it NOW so it does not fire again:

  openclaw cron delete --name '$cron_name'

Then proceed with Wave 1."

    # DEFENSE-IN-DEPTH GUARD (v12.3.8 parity): the resolver already filters
    # operator IDs, but add the same second-layer case guard that all other
    # delivery --to call sites carry, so every cron --to is uniformly guarded.
    case "$chat_id" in
        5252140759|6663821679|6771245262)
            warn "Auto-kickoff cron target resolved to an OPERATOR chat ID ($chat_id) — skipping kickoff cron."
            warn "Set OPENCLAW_OWNER_CHAT_ID=<client-owner-chat-id> before running install.sh to force the correct target."
            return 0
            ;;
    esac
    if openclaw cron create \
         --name "$cron_name" \
         --cron "$cron_expr" \
         --tz UTC \
         --channel telegram \
         --to "$chat_id" \
         --agent main \
         --message "$full_msg" >> "$LOG_FILE" 2>&1; then
        success "Auto-kickoff (mechanism A: cron) scheduled — Wave 1 starts in ~3 min (cron '$cron_name' @ '$cron_expr' UTC)."
        return 0
    fi
    # v14.1.3: docs-canonical positional form (2026.6.8) — schedule + prompt are
    # POSITIONAL, not `--cron`/`--message` (verified docs.openclaw.ai/cli/cron).
    # Retry positionally before falling through to mechanism B (spool write).
    if openclaw cron create "$cron_expr" "$full_msg" \
         --name "$cron_name" \
         --tz UTC \
         --channel telegram \
         --to "$chat_id" \
         --agent main >> "$LOG_FILE" 2>&1; then
        success "Auto-kickoff (mechanism A: cron, positional 2026.6.8 form) scheduled — Wave 1 starts in ~3 min (cron '$cron_name' @ '$cron_expr' UTC)."
        return 0
    fi
    return 1
}

# --- Mechanism B: Direct Telegram ingress-spool write (fallback) ---
# On Mac, the spool dir is typically ~/.openclaw/telegram/ingress-spool-default.
# On VPS (/data), it's /data/.openclaw/telegram/ingress-spool-default.
# Detect via $OC_CONFIG which is set earlier in install.sh.
_kickoff_mech_b_spool() {
    local chat_id="$1"
    local kickoff_msg="$2"

    local spool_dir="$OC_CONFIG/telegram/ingress-spool-default"
    local offset_file="$OC_CONFIG/telegram/update-offset-default.json"

    if [ ! -d "$spool_dir" ]; then
        note "Mechanism B unavailable: spool dir '$spool_dir' missing."
        return 1
    fi

    local last_offset new_update_id
    last_offset=$(python3 -c "import json,sys;d=json.load(open('$offset_file'));print(d.get('offset',0))" 2>/dev/null)
    if [ -n "$last_offset" ] && [ "$last_offset" -gt 0 ] 2>/dev/null; then
        new_update_id=$((last_offset + 100))
    else
        new_update_id=$(date +%s)
    fi
    local now_sec=$(date +%s)
    local now_ms=$((now_sec * 1000))
    local spool_file
    spool_file=$(printf "%s/%016d.json" "$spool_dir" "$new_update_id")

    OC_KICKOFF_MSG="$kickoff_msg" CHAT_ID="$chat_id" UPDATE_ID="$new_update_id" \
    NOW_SEC="$now_sec" NOW_MS="$now_ms" SPOOL_FILE="$spool_file" \
    python3 - << 'PYEOF_INNER' 2>>"$LOG_FILE"
import json, os
payload = {
    "version": 1,
    "updateId": int(os.environ["UPDATE_ID"]),
    "receivedAt": int(os.environ["NOW_MS"]),
    "update": {
        "update_id": int(os.environ["UPDATE_ID"]),
        "message": {
            "message_id": int(os.environ["UPDATE_ID"]),
            "from": {
                "id": int(os.environ["CHAT_ID"]),
                "is_bot": False,
                "first_name": "Owner",
                "language_code": "en",
            },
            "chat": {
                "id": int(os.environ["CHAT_ID"]),
                "first_name": "Owner",
                "type": "private",
            },
            "date": int(os.environ["NOW_SEC"]),
            "text": os.environ["OC_KICKOFF_MSG"],
        }
    }
}
with open(os.environ["SPOOL_FILE"], "w") as f:
    json.dump(payload, f)
os.chmod(os.environ["SPOOL_FILE"], 0o600)
print(f"  spool file written: {os.environ['SPOOL_FILE']}")
PYEOF_INNER

    local rc=$?
    if [ "$rc" -eq 0 ] && [ -f "$spool_file" ]; then
        success "Auto-kickoff (mechanism B: spool write) injected — gateway will pick it up within ~30s as if owner sent the kickoff via Telegram."
        return 0
    fi
    return 1
}

schedule_auto_kickoff() {
    local chat_id="$1"
    if [ -z "$chat_id" ] || [ "$chat_id" = "skipped" ] || [ "$chat_id" = "no-openclaw-cli" ] || [ "$chat_id" = "no-telegram-target" ] || [ "${chat_id#failed:}" != "$chat_id" ]; then
        warn "Auto-kickoff skipped — no Telegram chat target resolved ('$chat_id'). Owner can still paste the kickoff manually from the completion notice below."
        return 0
    fi
    chat_id="${chat_id#sent:}"
    # Strip any non-numeric suffix the Mac install sometimes appends (e.g. "direct-bot-api(no-cli)")
    case "$chat_id" in
        direct-bot-api*) warn "Auto-kickoff skipped — chat_id is a placeholder ('$chat_id'), not a real Telegram numeric id. Owner can paste the kickoff manually."; return 0 ;;
    esac

    local kickoff_msg="I just ran the OpenClaw onboarding install. There is an UPDATE PENDING flag at the top of my AGENTS.md. Please follow the 5-Phase Processing Order in that flag to activate all skills. Start with Phase A (parallel install in waves). Do not skip any phase. Run QC after each skill. Send me a summary when complete."

    note "Auto-kickoff: trying mechanism A (openclaw cron one-shot)..."
    if _kickoff_mech_a_cron "$chat_id" "$kickoff_msg"; then
        note "Owner does NOT need to paste the kickoff. The bot will begin Wave 1 autonomously and send progress updates."
        return 0
    fi

    warn "Mechanism A (cron) failed. Falling back to mechanism B (direct spool write)..."
    if _kickoff_mech_b_spool "$chat_id" "$kickoff_msg"; then
        note "Owner does NOT need to paste the kickoff. The bot will begin Wave 1 autonomously and send progress updates."
        return 0
    fi

    warn "Both mechanisms A and B failed (see $LOG_FILE). Owner CAN still paste the kickoff manually from the completion notice — that path remains supported."
    return 0
}

# Fire the auto-kickoff. Failure here never blocks install completion.
schedule_auto_kickoff "$TELEGRAM_LAST_RESULT" || true

# ----------------------------------------------------------
# v10.13.19: proactive config heal before gateway restart.
# ----------------------------------------------------------
# The Telegram/whatsapp plugin auto-config-append step (which fires on every
# gateway restart) can write deprecated field names (e.g.
# messages.groupChat.unmentionedInbound) that fail validation against the
# current OpenClaw schema. When that happens the gateway exits 0 on next
# start and the entire bot goes silent — confirmed in the wild 2026-05-23
# with "Invalid config at openclaw.json. messages.groupChat: Unrecognized
# key: 'unmentionedInbound'". `openclaw doctor --fix` strips deprecated keys
# cleanly. Idempotent and safe — no-op when config is already clean.
if command -v openclaw >/dev/null 2>&1; then
    step "Running openclaw doctor --fix to strip any stale plugin-injected config keys"
    openclaw doctor --fix 2>&1 | tail -5 || warn "doctor --fix had issues — continuing anyway (gateway may complain at start)"
fi

# ----------------------------------------------------------
# v12.14.3: WhatsApp permanent ban (fleet-wide, non-negotiable)
# ----------------------------------------------------------
# ROOT CAUSE: The Hostinger Docker wrapper (server.mjs boot logic) calls
# meetsRequirements() and auto-installs + enables the WhatsApp plugin on
# EVERY gateway boot when WHATSAPP_NUMBER is present in the project .env
# file (/docker/<project>/.env), regardless of openclaw.json. An un-paired
# WhatsApp install immediately crashes the gateway into a QR-scan restart-loop.
#
# FIX LAYER 1: Disable the plugin in openclaw.json so the gateway never
# activates it — covers both Mac and VPS.
#
# FIX LAYER 2 (VPS only): Comment out WHATSAPP_NUMBER in the Hostinger Docker
# project .env so the wrapper's boot check never triggers the auto-install path.
# This is the durable fix; layer 1 alone is not sufficient because the wrapper
# fires before the gateway reads openclaw.json.
#
# Both steps are idempotent, non-blocking, and auto-applied on every
# install/update. See FLEET-STANDARDS.md §3 and KNOWN-ISSUES.md §5.
step "Applying WhatsApp permanent ban (fleet-wide enforcement)"

# Layer 1: disable plugin in openclaw.json
_whatsapp_ban_json() {
    local _cfg="$1"
    python3 - "$_cfg" <<'WABPYEOF'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
cfg = json.loads(p.read_text())
plugins = cfg.setdefault("plugins", {})
entries = plugins.setdefault("entries", {})
wa = entries.setdefault("whatsapp", {})
if wa.get("enabled") is False:
    print("  [whatsapp-ban] plugins.entries.whatsapp.enabled already false — no-op")
else:
    wa["enabled"] = False
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    print("  [whatsapp-ban] set plugins.entries.whatsapp.enabled = false in " + str(p))

# Hard-assert: must be false after this point
cfg2 = json.loads(p.read_text())
enabled = cfg2.get("plugins", {}).get("entries", {}).get("whatsapp", {}).get("enabled", False)
if enabled:
    print("ERROR: WhatsApp plugin is still enabled after ban step — HARD FAIL", file=sys.stderr)
    sys.exit(1)
print("  [whatsapp-ban] QC: plugins.entries.whatsapp.enabled = false — PASS")
WABPYEOF
}

if [ -f "$OC_JSON" ]; then
    _whatsapp_ban_json "$OC_JSON" || warn "WhatsApp ban json step had issues — continuing (gateway restart still blocked)"
else
    note "WhatsApp ban: $OC_JSON not found yet — will be applied by apply-fleet-standards.sh"
fi

# Layer 2 (VPS only): comment out WHATSAPP_NUMBER in Hostinger Docker .env
if [ "$OPENCLAW_PLATFORM" = "vps" ] || [ -d "/docker" ]; then
    _wa_env_found=0
    for _wa_envf in /docker/*/.env /data/docker/*/.env; do
        [ -f "$_wa_envf" ] || continue
        _wa_env_found=1
        if grep -qE '^[[:space:]]*WHATSAPP_NUMBER[[:space:]]*=[^#]' "$_wa_envf" 2>/dev/null; then
            _wa_bak="${_wa_envf}.bak-whatsapp-ban-$(date +%Y%m%d%H%M%S)"
            cp "$_wa_envf" "$_wa_bak"
            # Comment out the active WHATSAPP_NUMBER line
            perl -i -pe 's{^([[:space:]]*)(WHATSAPP_NUMBER[[:space:]]*=.+)$}{$1# WHATSAPP_NUMBER PERMANENTLY DISABLED (fleet ban v12.14.3 -- see FLEET-STANDARDS.md SS3)\n# $2}' "$_wa_envf"
            note "WhatsApp ban: commented out WHATSAPP_NUMBER in $_wa_envf (backup: $_wa_bak)"
        else
            note "WhatsApp ban: WHATSAPP_NUMBER already absent/commented in $_wa_envf — no-op"
        fi
    done
    [ "$_wa_env_found" -eq 0 ] && note "WhatsApp ban: no /docker/*/.env found from this context — Layer 1 (openclaw.json) is sufficient"
fi

# ----------------------------------------------------------
# v10.13.26: 2-day-learnings install hardening (Mac subset)
# ----------------------------------------------------------
# Findings cross-pollinated from VPS v10.14.34, scoped to Mac-applicable items:
#   #13 hooks.token auto-generate when hooks.enabled but no token
#   #16 brew (not apt) assumption check — warn if brew missing
#   #20 yt-dlp + whisper-cpp + ffmpeg backfill (Skill 22 needs them)
# Idempotent + non-blocking.
_hardening_self="$ONBOARDING_DIR/scripts/install-hardening.sh"
if [ -f "$_hardening_self" ]; then
    step "Running install hardening (2-day-learnings defenses, Mac subset)"
    bash "$_hardening_self" 2>&1 | tail -20 || warn "install-hardening returned non-zero (treated as informational)"
else
    note "install-hardening.sh not in bundle — skipping (older onboarding bundle, harmless)"
fi

# ----------------------------------------------------------
# v12.34.0 (ZHC-EXPERIENCE fix BREAK #1/#4): END-OF-RUN PIPELINE CRON BACKFILL.
# A single, idempotent assertion that ALL closeout/pipeline trigger crons are
# present (workforce-build-resume, interview-nudge, closeout-readiness-watchdog,
# closeout-resume). Steps 13/13.5/13.5b/14 register them individually; this
# end-of-run sweep is the safety net that catches any that skipped (no owner
# chat yet, container recreate that dropped crons, ordering) so a box never ends
# an install with files-but-no-trigger. Shared registrar — also called by
# update-skills.sh so the hot-patch path is self-sufficient too.
# ----------------------------------------------------------
step "Backfilling pipeline trigger crons (ensure-pipeline-crons.sh — closeout trigger safety net)"
_ENSURE_CRONS="$ONBOARDING_DIR/scripts/ensure-pipeline-crons.sh"
if [ -f "$_ENSURE_CRONS" ]; then
    if bash "$_ENSURE_CRONS" 2>&1 | tee -a "$LOG_FILE"; then
        success "Pipeline trigger crons asserted — closeout experience has at least one live trigger"
    else
        warn "ensure-pipeline-crons.sh reported a non-zero rc — one or more pipeline crons could not be registered (see log). Re-run update-skills.sh to backfill."
    fi
else
    warn "ensure-pipeline-crons.sh not in bundle ($_ENSURE_CRONS) — pipeline cron backfill skipped (older onboarding bundle)."
fi

# ----------------------------------------------------------
# v16.2.8: Mac SERVICE self-heal + gateway-health watchdog (no-sudo).
# ----------------------------------------------------------
# Wires the previously manual-only platform/mac/service-selfheal installer into
# the install flow. It copies remediate.sh AND gateway-health-watchdog.sh into
# ~/.openclaw/service-env/ and loads the com.openclaw.service-remediate
# LaunchAgent (every 5 min). remediate.sh then DELEGATES the gateway HEALTH leg
# to the watchdog (HTTP {"ok":true} probe + launchctl kickstart of a hung
# gateway), closing the gateway-deferral-deadlock dark-gateway gap that launchd
# KeepAlive alone cannot cover (KeepAlive only respawns a still-LOADED job; a
# hung-but-loaded gateway stays dark). Mac-only (launchd). The VPS host
# equivalent is platform/vps/service-selfheal/install-host-watchdog-cron.sh, which the operator
# runs ON THE DOCKER HOST (install.sh re-execs INTO the container, so it cannot
# install a host cron itself). Idempotent, fail-soft — never blocks the install.
if [ "$OC_PLATFORM" = "mac" ]; then
    step "Installing Mac service self-heal + gateway-health watchdog (com.openclaw.service-remediate)"
    _SELFHEAL_INSTALLER="$ONBOARDING_DIR/platform/mac/service-selfheal/install-service-remediate.sh"
    if [ -f "$_SELFHEAL_INSTALLER" ]; then
        if bash "$_SELFHEAL_INSTALLER" 2>&1 | tee -a "$LOG_FILE"; then
            success "Service self-heal + gateway watchdog installed (runs every 5 min, no sudo)"
        else
            warn "install-service-remediate.sh returned non-zero — self-heal not confirmed (re-run manually: bash $_SELFHEAL_INSTALLER)"
        fi
    else
        note "service-selfheal installer not in bundle ($_SELFHEAL_INSTALLER) — skipping (older onboarding bundle, harmless)"
    fi
fi

# ----------------------------------------------------------
# Final: Restart gateway (agent reloads AGENTS.md and sees the UPDATE PENDING flag on next session)
# ----------------------------------------------------------
note "Restarting OpenClaw gateway..."
if command -v openclaw >/dev/null 2>&1; then
    openclaw gateway restart
    success "Gateway restart triggered. Your agent will reload AGENTS.md on next session."
else
    warn "openclaw command not found - restart manually: openclaw gateway restart"
fi

# ----------------------------------------------------------
# Install summary (v10.0.2) — scan log for warnings/errors, print actionable
# report block right in the terminal so issues are visible without scrolling.
# ----------------------------------------------------------
print_install_summary() {
    # Patterns that indicate something went wrong:
    #   warn() prints `  ⚠️  ...`
    #   error() prints `  ✗ ERROR: ...`
    #   openclaw gateway/transport errors include these tokens
    local err_pat='^  ✗ ERROR:|GatewayClientRequestError|GatewayTransportError|gateway connect failed|scope upgrade pending|pairing required'
    local warn_pat='^  ⚠️'

    local err_count warn_count
    err_count=$(grep -cE "$err_pat" "$LOG_FILE" 2>/dev/null | head -1 || true)
    warn_count=$(grep -cE "$warn_pat" "$LOG_FILE" 2>/dev/null | head -1 || true)
    err_count=${err_count:-0}
    warn_count=${warn_count:-0}

    echo ""
    echo "══════════════════════════════════════════════════════════════════════"
    if [ "$err_count" -eq 0 ] && [ "$warn_count" -eq 0 ]; then
        echo "  ✅ INSTALL COMPLETED CLEANLY — no warnings or errors detected"
        echo ""
        echo "     Log (durable, survives reboot):"
        echo "       $LOG_FILE"
        echo "══════════════════════════════════════════════════════════════════════"
        return 0
    fi

    echo "  ⚠️  PLEASE REPORT THE FOLLOWING TO THE TRACKER"
    echo "     ${err_count} error(s), ${warn_count} warning(s) detected during install."
    echo ""
    echo "  ─── First 10 issues (most recent first) ──────────────────────────────"
    grep -nE "$err_pat|$warn_pat" "$LOG_FILE" 2>/dev/null | tail -10 | sed 's/^/     /' || true
    echo ""
    echo "  ─── Full log (durable, survives reboot) ──────────────────────────────"
    echo "     $LOG_FILE"
    echo ""
    echo "  ─── To copy the full log to your clipboard ───────────────────────────"
    echo "     cat \"$LOG_FILE\" | pbcopy"
    echo ""
    echo "  ─── Report at ────────────────────────────────────────────────────────"
    echo "     https://github.com/trevorotts1/openclaw-onboarding/issues/new"
    echo "     (paste the log contents into the issue body)"
    echo "══════════════════════════════════════════════════════════════════════"
}
print_install_summary

# ============================================================
#  v10.8.0 — P0-9 Triple-Fire Install Kickoff Trigger (N22)
#  The terminal-side install.sh has finished bootstrapping the repo files.
#  Now we MUST trigger the agent to actually perform the onboarding work
#  through THREE independent channels so the user is never stranded:
#    1. Telegram message to the paired chat
#    2. AGENTS.md flag (so the next agent session sees the install-pending)
#    3. Terminal fallback instruction block (always printed)
#  All three fire, not "any one of three."
# ============================================================
fire_install_kickoff_triplet() {
    local plat
    if [ -d "/data/.openclaw" ]; then plat="vps"; else plat="mac"; fi
    local agents_md skills_dir openclaw_json
    if [ "$plat" = "vps" ]; then
        agents_md="/data/.openclaw/AGENTS.md"
        skills_dir="/data/.openclaw/skills"
        openclaw_json="/data/.openclaw/openclaw.json"
    else
        agents_md="$HOME/.openclaw/AGENTS.md"
        skills_dir="$HOME/.openclaw/skills"
        openclaw_json="$HOME/.openclaw/openclaw.json"
    fi

    # v10.13.5: kickoff Telegram now uses shared helpers (resolve_owner_name +
    # build_kickoff_telegram_message + send_kickoff_telegram). The send helper
    # has its own idempotency guard via KICKOFF_TG_FIRED — if the early fire
    # after Step 10 already succeeded, this is a no-op and tg_fired stays
    # accurate. Otherwise this is the final-attempt fire.
    local tg_fired="false" flag_fired="false"
    local tg_reason="" flag_reason=""

    if [ "${OPENCLAW_IS_FRESH_INSTALL:-0}" != "1" ]; then
        # WE MOVE IN SILENCE: update / re-roll of an already-onboarded box. NEVER
        # send the owner kickoff handshake — not via send_kickoff_telegram and not
        # via the send-telegram.sh fallback below. The AGENTS.md flag + the
        # Terminal block carry the agent/operator-facing handoff silently. This
        # branch is FIRST so the fallback can never bypass the fresh-install gate.
        tg_fired="false"
        tg_reason="suppressed: update/re-roll, not a fresh install (WE MOVE IN SILENCE)"
    elif [ "${KICKOFF_TG_FIRED:-false}" = "true" ]; then
        tg_fired="true"
        tg_reason="already-fired-after-step-10:${KICKOFF_TG_PATH:-?}"
    elif send_kickoff_telegram; then
        tg_fired="true"
        tg_reason="path:${KICKOFF_TG_PATH:-?}"
    else
        # Last-ditch fallback to send-telegram.sh helper (FRESH INSTALL ONLY —
        # this branch is unreachable on an update/re-roll because of the guard
        # above). Build the message text manually since send_kickoff_telegram
        # already failed.
        local owner_name
        owner_name=$(resolve_owner_name "$openclaw_json")
        local tg_msg
        tg_msg=$(build_kickoff_telegram_message "$owner_name")
        local tg_helper="$skills_dir/scripts/send-telegram.sh"
        if [ -x "$tg_helper" ] && "$tg_helper" "$tg_msg" 2>/dev/null; then
            tg_fired="true"
            tg_reason="path:send-telegram.sh-helper"
        else
            tg_reason="all paths failed: gateway, direct Bot API, helper. Bot token or chat ID likely missing from openclaw.json."
        fi
    fi

    # 2. AGENTS.md flag — UNCONDITIONAL attempt (N22). Create the parent dir
    #    if needed; only skip if mkdir + write both fail.
    mkdir -p "$(dirname "$agents_md")" 2>/dev/null || true
    local flag_marker
    flag_marker="<!-- OPENCLAW_ONBOARDING_KICKOFF:${ONBOARDING_VERSION:-?} -->"
    if [ -f "$agents_md" ] && grep -qF "$flag_marker" "$agents_md" 2>/dev/null; then
        flag_fired="true"
    else
        {
            echo ""
            echo "$flag_marker"
            echo "## OpenClaw onboarding kickoff: ${ONBOARDING_VERSION:-?}"
            echo "Triggered at $(date -u +%Y-%m-%dT%H:%M:%SZ) via install.sh on platform=$plat."
            echo ""
            echo "The bash install.sh has finished bootstrapping repo files at $skills_dir."
            echo "Read the terminal kickoff block (printed at install.sh end) and execute"
            echo "those instructions in order. Begin with: read $skills_dir/Start\\ Here.md"
            echo "and $skills_dir/INSTALL-CONTRACT.md end to end before any work."
            echo "<!-- OPENCLAW_ONBOARDING_KICKOFF_END -->"
        } >> "$agents_md" 2>/dev/null && flag_fired="true" \
                                        || flag_reason="could not write $agents_md (mkdir -p $(dirname "$agents_md") also tried)"
    fi

    # 3. Terminal fallback — ALWAYS printed regardless of 1 and 2
    # v10.13.1: rewritten for owner-friendly UX (average user is 60+,
    # non-technical). Removes all internal jargon and adds clear paste-
    # block delimiters + concrete timeline.
    cat <<TERMEOF

═══════════════════════════════════════════════════════════════════════
  ✓ All set, ${owner_name}! Your AI workforce is installed.
═══════════════════════════════════════════════════════════════════════

  Version: ${ONBOARDING_VERSION:-?}
  Installed on: $plat ($(date +%Y-%m-%d at %H:%M))

═══════════════════════════════════════════════════════════════════════
  📋  WHAT TO DO NEXT — JUST ONE STEP
═══════════════════════════════════════════════════════════════════════

  Open your Telegram bot (the one your agent runs on) and paste in the
  long block of text below. That message tells your bot exactly what to
  do — it'll take it from there and keep you posted along the way.

  Step-by-step:
    1. Open Telegram on your phone or computer
    2. Find your bot (the AI agent you talk to)
    3. Highlight everything between the two long lines below
       (between "COPY EVERYTHING BELOW" and "COPY EVERYTHING ABOVE")
    4. Copy it (Cmd+C on Mac, Ctrl+C on Windows)
    5. Paste it into the chat with your bot
    6. Hit Send

  Your bot will reply within 30 seconds.

────────── 📋 COPY EVERYTHING BELOW THIS LINE 📋 ──────────

Hi! Please start the OpenClaw onboarding process now. Here's the procedure
to follow exactly:

PHASE 1 — Read the docs first (don't skip):
  1. Read $skills_dir/Start\ Here.md end to end.
  2. Read $skills_dir/INSTALL-CONTRACT.md end to end. Rules that are
     non-negotiable: Rule 0 (max 10 helpers running at once on Mac,
     5 on VPS), Rule 1 (read every .md file in a skill before doing
     anything).
  3. Run the web research pre-flight to make sure model and pricing
     info is current:
        bash $skills_dir/web-research-preflight.sh
  4. Confirm settings: maxChars=200000, maxTotalChars=400000,
     maxSpawnDepth=4, maxChildren=20, maxConcurrent=100, thinking=high.
  5. Set up canonical workspace files (USER.md, AGENTS.md, TOOLS.md
     at workspace root, symlinked into every per-role workspace).

PHASE 2 — Install the skills in waves, with PROGRESS UPDATES:

  This is mandatory in v10.13.1+: tell me (the owner) what you're doing
  in PLAIN ENGLISH before and after each wave. Keep it short and warm.
  Average owner is non-technical and may be over 60 — no jargon, no
  acronyms ("QC", "sub-agent", "manifest"), no technical paths.

  BEFORE each wave, send a Telegram message like:
    "Starting on Wave 2 of 5 now. About to set up 18 utility skills
     in parallel — this should take about 10 minutes."

  AFTER each wave, send a Telegram message like:
    "Wave 2 is done. 18 skills are working. Now starting Wave 3."

  If anything goes wrong in a wave, message me with what broke and
  what you're going to try next, in plain English.

  Wave gating command (use before each wave):
      bash $skills_dir/check-wave-concurrency.sh --proposed <N> --reason "wave-N"

  Per skill: read all of the skill's .md files and scripts, execute
  its INSTALL.md in order, score it ≥ 8.5/10, up to 5 retry loops.

PHASE 3 — Verify everything:
  6. Run skills/qc-system-integrity.sh — must exit 0.
  7. Send me a Telegram message:
       "All skills installed and verified. Now we're going to do the
        most important step: a 30-question interview about your
        business. This will take about 35 minutes of your time. Your
        answers shape your entire AI team — please block out
        uninterrupted time. Ready to start?"
     Wait for "yes" or equivalent before proceeding.

PHASE 4 — Build the AI workforce:
  8. Run the AI Workforce Interview (Skill 23) to build the company
     structure from my answers. ZHC location:
     ~/.openclaw/workspace/zero-human-company/<slug>/ (Mac) or
     /data/.openclaw/workspace/zero-human-company/<slug>/ (VPS).
  9. After the interview, run create_role_workspaces.py to write
     per-department governing-personas.md.
  10. Send me a Telegram message confirming the workforce is built
      and which departments were created.

PHASE 5 — Wrap up:
  11. Walk me through the Telegram supergroup setup (Skill 32 INSTALL.md
      Phase 2 — 7 manual steps on my phone, one at a time, with
      screenshots if you can describe them in words).
  12. Final summary in plain English: "Here's what I installed,
      here's what's ready to use today, here's anything that didn't
      work and why."

HARD RULES (v10.13.1+):
  • No shortcuts. No self-QC.
  • All helpers (sub-agents) use non-Anthropic models — Ollama Cloud
    primary, OpenRouter fallback.
  • Persona governance applies to every non-mechanical task.
  • Master Orchestrator does NO work directly — only dispatches and
    reports.
  • Send Telegram progress updates between waves (N28 binding).
  • Speak to the owner in plain English. NO jargon. They're paying
    you to make this easy.

────────── 📋 COPY EVERYTHING ABOVE THIS LINE 📋 ──────────

═══════════════════════════════════════════════════════════════════════
  ⏱  WHAT YOU'LL SEE — APPROXIMATE TIMELINE
═══════════════════════════════════════════════════════════════════════

  Minute 0:        Your bot starts reading the docs (silent)
  Minute 5:        Bot messages you "Starting Wave 1"
  Minute 15:       Bot messages you "Wave 1 done, starting Wave 2"
  Minute 30:       Bot messages you "Wave 2 done, starting Wave 3"
  Minute 40-45:    Bot says "Now we need to interview you about your
                   business — ready for 35 min of focused time?"
  Minute 45-80:    The 30-question interview happens — this is YOUR
                   active time. Best answers = best AI workforce.
  Minute 80-90:    Bot builds your departments and helps you set up
                   the Telegram supergroup.

  Total: about an hour and a half. Half of that is reading the
  interview questions and answering them.

═══════════════════════════════════════════════════════════════════════
  ℹ️  IF SOMETHING SEEMS OFF
═══════════════════════════════════════════════════════════════════════

  • If you don't hear from your bot within 2 minutes of pasting the
    block above, paste it once more.
  • If the bot asks for "admin permission" or "scope upgrade" approval,
    reply "approve" or "yes". This is a one-time thing for the
    automatic Sunday updates.

═══════════════════════════════════════════════════════════════════════
TERMEOF
}

# Apply fleet standards (sub-agents fully permitted + Telegram media limit 50MB)
echo ""
note "Applying fleet standards (sub-agents fully permitted, Telegram media 50MB)..."
if [ -f "$ONBOARDING_DIR/scripts/apply-fleet-standards.sh" ]; then
    bash "$ONBOARDING_DIR/scripts/apply-fleet-standards.sh" || warn "Fleet standards application reported errors (install continues)"
    success "Fleet standards applied"
else
    warn "Fleet standards script not found at $ONBOARDING_DIR/scripts/apply-fleet-standards.sh"
fi
echo ""

# ----------------------------------------------------------
# F6 (v16.x): EXECUTED-SHELL floor-fill backstop on the INSTALL path.
# Previously the ONLY floor-fill reference on the install path was PROSE inside
# the agent paste-prompt heredoc (build_kickoff_paste_block, step 6b) — it ran
# only if the install agent obeyed the prompt. The update path runs the real
# shell (update-skills.sh "Running workforce migration"). This block brings the
# install path to PARITY: it invokes migrate-existing-workforce.sh as real code,
# so the floor-fill + dept-script-refresh chain (floor-fill-driver.py ->
# create_role_workspaces.py scaffold_department, which refreshes a stale
# build_deck.py) runs regardless of agent compliance. migrate-existing-workforce.sh
# Step 2b self-guards: on a fresh box whose workforce the agent has not built yet
# it is a clean no-op (logs "skipping"); on a resume / re-run / post-build
# invocation it materializes the missing floor and refreshes changed dept
# scripts. Idempotent, additive (never clobbers client edits), box-user (this
# installer runs as the box owner, never root).
# ----------------------------------------------------------
note "Running workforce floor-fill backstop (migrate-existing-workforce.sh — executed shell, install==update parity)..."
_MIGRATE_WF="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh"
if [ -f "$_MIGRATE_WF" ]; then
    if bash "$_MIGRATE_WF" "$(hostname)" --apply >> "$LOG_FILE" 2>&1; then
        success "Workforce floor-fill backstop completed (floor materialized / dept scripts refreshed where needed)"
    else
        warn "Workforce floor-fill backstop reported warnings (install continues — re-runs on next update). See $LOG_FILE"
    fi
else
    note "migrate-existing-workforce.sh not found at $_MIGRATE_WF — skipping floor-fill backstop (older bundle)"
fi
echo ""

# Apply routing-defect permanent fix (4-layer: doctrine path, pptx deny, symlink unblock, dept seeding)
# Must run AFTER workspace + openclaw.json + mission-control.db are initialised.
note "Applying routing-defect permanent fix (Layers 1-4)..."
if [ -f "$ONBOARDING_DIR/scripts/apply-routing-fix.sh" ]; then
    bash "$ONBOARDING_DIR/scripts/apply-routing-fix.sh" || warn "Routing fix reported errors (install continues — re-run apply-routing-fix.sh)"
    success "Routing fix applied"
else
    warn "apply-routing-fix.sh not found at $ONBOARDING_DIR/scripts/apply-routing-fix.sh"
fi
echo ""

# ----------------------------------------------------------
# CEO PreToolUse intent-gate — WIRE THE RUNTIME BRAKE (v16.2.19).
# apply-routing-fix.sh (above) stamps the presentation reflex + the SIGNED
# route-presentation.sh helper, but that reflex is only ENFORCED at runtime by the
# PreToolUse intent-gate hook (hooks/ceo-intent-gate.sh): the hook denies a raw
# `python3 build_deck.py` on the router/CEO and redirects it to route. The hook +
# its installer shipped but were never invoked, so the brake stayed OFF on every
# box. Wire it here on the fresh-install path (mirror of update-skills.sh), right
# after the routing fix so the reflex/helper and openclaw.json topology exist.
# The installer is idempotent (self-skips when already wired), self-skips on
# PA-default boxes, runs as the box owner (never root), and is non-fatal
# (a wiring error is a warning — install continues, mirroring apply-routing-fix.sh).
# ----------------------------------------------------------
note "Wiring CEO PreToolUse intent-gate (runtime brake for the presentation reflex)..."
if [ -f "$ONBOARDING_DIR/scripts/install-ceo-intent-gate.sh" ]; then
    bash "$ONBOARDING_DIR/scripts/install-ceo-intent-gate.sh" || warn "install-ceo-intent-gate.sh reported errors (install continues — re-run scripts/install-ceo-intent-gate.sh)"
    success "CEO intent-gate wired (or already wired / PA-box skip)"
else
    warn "install-ceo-intent-gate.sh not found at $ONBOARDING_DIR/scripts/install-ceo-intent-gate.sh"
fi
echo ""

# ----------------------------------------------------------
# Post-stamp verification: verify-routing.sh static gates G1–G8 (v16.2.19).
# The install applied the 4-layer routing fix + wired the intent-gate above but
# never VERIFIED them, so a box that silently failed a layer went unflagged.
# Run the gate now and surface per-gate PASS/FAIL. LOUD WARNING on failure —
# NOT a hard install abort (mirrors the update-skills.sh post-stamp block and
# the non-fatal convention of the surrounding steps). Read-only static gates
# G1–G8 only (no --probe: the Command Center may not be live yet at this phase).
# ----------------------------------------------------------
note "Verifying routing wiring (verify-routing.sh static gates G1–G8)..."
if [ -f "$ONBOARDING_DIR/scripts/verify-routing.sh" ]; then
    if bash "$ONBOARDING_DIR/scripts/verify-routing.sh"; then
        success "verify-routing: all static gates PASS"
    else
        warn "verify-routing: one or more gates FAILED — routing/intent-gate wiring incomplete on this box."
        warn "Install continues; re-run apply-routing-fix.sh + install-ceo-intent-gate.sh, then 'bash scripts/verify-routing.sh' to see which gate."
    fi
else
    warn "verify-routing.sh not found at $ONBOARDING_DIR/scripts/verify-routing.sh (skipping post-stamp routing verification)"
fi
echo ""

# FIX 2 (v10.15.48): Operator Telegram channel separation.
# Adds channels.telegram.accounts.{default,operator} + defaultAccount=default +
# an operator->main binding so operator/rescue traffic NEVER bleeds into the
# client's personal chat. Idempotent + additive. Honest STATUS line: if the
# operator bot token is not provisioned, it writes the STRUCTURE and flags the
# box for token provisioning — it never claims separation is live without one.
note "Configuring operator Telegram channel separation (operator account + binding)..."
if [ -f "$ONBOARDING_DIR/scripts/configure-operator-telegram.sh" ]; then
    _OPTG_OUT="$(bash "$ONBOARDING_DIR/scripts/configure-operator-telegram.sh" 2>&1)" || true
    printf '%s\n' "$_OPTG_OUT" >> "$LOG_FILE"
    _OPTG_STATUS="$(printf '%s\n' "$_OPTG_OUT" | grep -E '^STATUS:' | tail -1 || true)"
    case "$_OPTG_STATUS" in
        *=CONFIGURED*)                       success "Operator Telegram separation live (${_OPTG_STATUS})" ;;
        *STRUCTURE_ONLY_NEEDS_TOKEN*)        warn "Operator Telegram STRUCTURE written but needs a BotFather operator bot token. ${_OPTG_STATUS} — set OPERATOR_TELEGRAM_BOT_TOKEN in ~/.openclaw/secrets/.env and re-run scripts/configure-operator-telegram.sh." ;;
        *VALIDATE_FAILED*)                   warn "Operator Telegram merge failed validation and was rolled back. ${_OPTG_STATUS}" ;;
        *)                                   note "Operator Telegram config ran. ${_OPTG_STATUS:-(no STATUS line — see $LOG_FILE)}" ;;
    esac
else
    warn "configure-operator-telegram.sh not found at $ONBOARDING_DIR/scripts/configure-operator-telegram.sh"
fi
echo ""

# v14.24.0: Fix D (furnace-fix v2/v3): Sane heartbeat defaults — extracted into
# scripts/ensure-heartbeat-defaults.sh so the same idempotent + conditional logic
# is shared with the update-skills.sh apply phase.
# CONDITIONAL: only writes when unset or below 6h (< 360 min); never resets an
# operator who intentionally tuned heartbeat to a longer interval.
note "Setting sane heartbeat defaults via ensure-heartbeat-defaults.sh (CONDITIONAL: 6h min)..."
_ENSURE_HB="$ONBOARDING_DIR/scripts/ensure-heartbeat-defaults.sh"
if [ -f "$_ENSURE_HB" ]; then
    bash "$_ENSURE_HB" 2>&1 | tee -a "$LOG_FILE" | tail -5
else
    note "ensure-heartbeat-defaults.sh not in bundle — skipping (set manually: openclaw config set agents.defaults.heartbeat.every 6h)"
fi

# ----------------------------------------------------------
# Loop / furnace protection activation (Skill 60 EWS + Skill 61 Loop Protection).
# GRAPHICS-FURNACE-CONTEXT-RESCUE-SPEC Topic 2, §2.3 item 2. Runs the shared
# activate-loop-protection.sh helper (the SAME one update-skills.sh calls — no
# copy-paste drift). Client-box activation is GATED HELD by default per SKILL.md
# law 8 (CANARY, THEN HOLD) + the 7-03 repo-only HOLD: the helper installs the
# 60-then-61 per-box watchdogs (ews-tick + loop-tick crons + ledgers) in DRY_RUN
# observe-only ONLY when the fleet rollout gate is enabled (rollout.json /
# OPENCLAW_LOOP_PROTECTION_ROLLOUT); otherwise it prints a HELD note and no-ops.
# It NEVER arms a box (Tier-1 arming is the operator canary's separate action).
# Runs BEFORE the final gateway restart so any registered crons are picked up.
# Best-effort — never aborts the install.
# ----------------------------------------------------------
note "Loop/furnace protection (Skill 60 + 61): running the activation gate (HELD by default; DRY_RUN, never arms)..."
_ACT_LOOP="$ONBOARDING_DIR/scripts/activate-loop-protection.sh"
[ -f "$_ACT_LOOP" ] || _ACT_LOOP="$SCRIPTS_DIR/activate-loop-protection.sh"
if [ -f "$_ACT_LOOP" ]; then
    bash "$_ACT_LOOP" --role client --skills-dir "$SKILLS_DIR" 2>&1 | tee -a "$LOG_FILE" | tail -6 || true
else
    note "activate-loop-protection.sh not in bundle — loop protection wiring skipped (older bundle)."
fi

fire_install_kickoff_triplet

# ----------------------------------------------------------
# v14.24.0: Final gateway restart — apply scripts (operator-telegram,
# heartbeat, routing-fix) all mutate openclaw.json.  The earlier restart at
# ~line 6805 fires BEFORE these; this one fires AFTER so the running gateway
# picks up all config changes before the operator's first session.
# Guard: requires openclaw on PATH (skips silently on partial installs).
# ----------------------------------------------------------
if command -v openclaw >/dev/null 2>&1; then
    note "Final gateway restart (picks up operator-telegram + heartbeat + routing keys)..."
    openclaw gateway restart >> "$LOG_FILE" 2>&1 \
        && success "Gateway restarted — all end-of-install config changes are now live" \
        || warn "Final gateway restart returned non-zero — restart manually: openclaw gateway restart"
fi
