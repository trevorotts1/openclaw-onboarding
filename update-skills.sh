#!/usr/bin/env bash
#  PRD 2.1 -- unified repo (trevorotts1/openclaw-onboarding)
#
#  NOTE: this script REQUIRES bash (uses process substitution `< <(...)`, `[[ ]]`,
#  and bash arrays). Without the shebang above `./update-skills.sh` was executed by
#  the caller's login shell (sh/zsh on some boxes), where `< <(...)` is a syntax
#  error, forcing agents to fall back to `bash update-skills.sh`. The shebang makes
#  a direct `./update-skills.sh` invocation always run under bash. (v16.2.12)
#
#  Platform auto-detected via OPENCLAW_PLATFORM env var or presence of /data/.openclaw.
#  VPS: sources platform/vps/bootstrap.sh for container re-exec + path setup.
#  Mac: sources platform/mac/bootstrap.sh for Homebrew prereqs + path setup.
# ============================================================

# Platform detection + bootstrap (MUST run before set -euo pipefail -- VPS container
# re-exec uses conditional commands that may fail intentionally).
_DETECT_PLATFORM="${OPENCLAW_PLATFORM:-}"
if [ -z "$_DETECT_PLATFORM" ]; then
    [ -d "/data/.openclaw" ] && _DETECT_PLATFORM="vps" || _DETECT_PLATFORM="mac"
fi
export OPENCLAW_PLATFORM="$_DETECT_PLATFORM"

# DEFECT 3 (v13.1.3) — PLATFORM unbound-variable guard.
# A stale/dirty checkout of this script (pre-fix) referenced a bare $PLATFORM in
# the stale-artifact detection block (~line 1431 of that version) that was never
# assigned; under `set -euo pipefail` (active below) the first reference aborted
# with "PLATFORM: unbound variable" and the .onboarding-version stamp never wrote.
# Initialize PLATFORM here (aliased to the canonical OPENCLAW_PLATFORM) BEFORE any
# possible use so the script is robust even if any code path references the bare
# name. The canonical variable remains OPENCLAW_PLATFORM.
PLATFORM="${PLATFORM:-$OPENCLAW_PLATFORM}"
export PLATFORM

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
_PLATFORM_BOOTSTRAP="${_SCRIPT_DIR}/platform/${OPENCLAW_PLATFORM}/bootstrap.sh"
if [ -f "$_PLATFORM_BOOTSTRAP" ]; then
    # shellcheck source=/dev/null
    source "$_PLATFORM_BOOTSTRAP"
else
    # Inline minimal fallback when running via curl (no local clone yet).
    if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
        OC_PLATFORM="vps"; OC_CONFIG="/data/.openclaw"; OC_JSON="/data/.openclaw/openclaw.json"
        OC_SKILLS_DIR="/data/.openclaw/skills"; OC_WORKSPACE_DEFAULT="/data/.openclaw/workspace"
    else
        OC_PLATFORM="mac"; OC_CONFIG="$HOME/.openclaw"; OC_JSON="$HOME/.openclaw/openclaw.json"
        OC_SKILLS_DIR="$HOME/.openclaw/skills"; OC_WORKSPACE_DEFAULT="$HOME/.openclaw/workspace"
    fi
fi

set -euo pipefail

ONBOARDING_VERSION="v20.0.65"

LOG_FILE="/tmp/openclaw-update-$(date +%Y%m%d-%H%M%S).log"

# ----------------------------------------------------------
# DEFECT 3 (v13.1.3) — SELF-SYNC GUARD (always wire from the intended version).
# ----------------------------------------------------------
# When this script is run from a LOCAL git checkout (e.g. the Sunday cron does
# `bash ~/.../update-skills.sh`), a dirty/stale checkout would run OLD script
# LOGIC even though the content-download step git-clones fresh files — and the
# stale logic carried the PLATFORM bug that aborted before the version stamp.
#
# This guard runs BEFORE any wiring:
#   • curl|bash (no local file / not a git tree) → SKIP (fresh by definition).
#   • local git checkout, clean + up-to-date     → proceed.
#   • local git checkout, dirty or behind:
#       - OPENCLAW_UPDATE_AUTO_SYNC=1 → `git fetch origin main` +
#         `git reset --hard origin/main`, then RE-EXEC this script so the
#         intended version's logic runs.
#       - otherwise (default, non-destructive) → FAIL LOUD with exact remediation.
# Set OPENCLAW_UPDATE_SKIP_SELF_SYNC=1 to bypass (e.g. when intentionally testing
# a local edit). Re-exec is gated by OPENCLAW_UPDATE_SELF_SYNCED to avoid a loop.
self_sync_guard() {
  [ "${OPENCLAW_UPDATE_SKIP_SELF_SYNC:-0}" = "1" ] && { echo "  [self-sync] skipped (OPENCLAW_UPDATE_SKIP_SELF_SYNC=1)"; return 0; }
  [ "${OPENCLAW_UPDATE_SELF_SYNCED:-0}" = "1" ] && { echo "  [self-sync] already re-exec'd from origin/main — proceeding"; return 0; }

  # Not invoked from a real file (curl|bash → BASH_SOURCE is empty or 'bash')?
  local src="${BASH_SOURCE[0]:-}"
  case "$src" in
    ""|bash|sh|-bash|-sh) echo "  [self-sync] running via pipe (no local checkout) — fresh by definition, skipping"; return 0 ;;
  esac
  [ -f "$src" ] || { echo "  [self-sync] script path not a regular file — skipping"; return 0; }

  command -v git >/dev/null 2>&1 || { echo "  [self-sync] git not available — skipping (cannot verify checkout currency)"; return 0; }

  local repo_root
  repo_root="$(cd "$_SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$repo_root" ] || { echo "  [self-sync] not a git checkout — skipping (likely a copied script)"; return 0; }

  # Confirm this is the onboarding repo (don't touch an unrelated repo).
  local origin
  origin="$(git -C "$repo_root" remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    *trevorotts1/openclaw-onboarding*) : ;;
    *) echo "  [self-sync] checkout origin ($origin) is not the onboarding repo — skipping self-sync"; return 0 ;;
  esac

  # Determine dirty / behind state vs origin/main.
  local dirty="" behind=""
  [ -n "$(git -C "$repo_root" status --porcelain 2>/dev/null)" ] && dirty=1
  git -C "$repo_root" fetch --quiet origin main 2>/dev/null || echo "  [self-sync] WARN: git fetch failed — currency check may be stale"
  local local_sha remote_sha
  local_sha="$(git -C "$repo_root" rev-parse HEAD 2>/dev/null || true)"
  remote_sha="$(git -C "$repo_root" rev-parse origin/main 2>/dev/null || true)"
  [ -n "$remote_sha" ] && [ "$local_sha" != "$remote_sha" ] && behind=1

  if [ -z "$dirty" ] && [ -z "$behind" ]; then
    echo "  [self-sync] local checkout is clean and current with origin/main — proceeding"
    return 0
  fi

  if [ "${OPENCLAW_UPDATE_AUTO_SYNC:-0}" = "1" ]; then
    echo "  [self-sync] checkout is $( [ -n "$dirty" ] && printf 'DIRTY ' )$( [ -n "$behind" ] && printf 'BEHIND ' )— OPENCLAW_UPDATE_AUTO_SYNC=1: hard-syncing to origin/main"
    git -C "$repo_root" fetch origin main
    git -C "$repo_root" reset --hard origin/main
    echo "  [self-sync] re-syncing complete — re-exec'ing the intended version"
    OPENCLAW_UPDATE_SELF_SYNCED=1 exec bash "$src" "${SELF_SYNC_ARGS[@]+"${SELF_SYNC_ARGS[@]}"}"
  fi

  # Non-destructive default: fail loud with exact remediation.
  echo "" >&2
  echo "ERROR (self-sync): refusing to wire from a $( [ -n "$dirty" ] && printf 'DIRTY ' )$( [ -n "$behind" ] && printf 'STALE/BEHIND ' )local checkout." >&2
  echo "  Checkout: $repo_root" >&2
  echo "  Local HEAD:  ${local_sha:-unknown}" >&2
  echo "  origin/main: ${remote_sha:-unknown}" >&2
  echo "" >&2
  echo "  Wiring from a stale checkout installs the OLD version. Resolve, then re-run:" >&2
  echo "    git -C \"$repo_root\" fetch origin main && git -C \"$repo_root\" reset --hard origin/main" >&2
  echo "  OR run the curl path (always fresh):" >&2
  echo "    curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh | bash" >&2
  echo "  OR re-run with auto-sync (destructive — discards local changes):" >&2
  echo "    OPENCLAW_UPDATE_AUTO_SYNC=1 bash \"$src\"" >&2
  exit 1
}

# ----------------------------------------------------------
# Update-result notification — OPERATOR-ROUTED, NEVER the client chat.
# ----------------------------------------------------------
# SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons): a skill-UPDATE result
# is INTERNAL maintenance traffic. The agent-facing push is the UPDATE PENDING
# flag written into AGENTS.md (write_update_pending_flag) — the agent picks it
# up on its next session and surfaces an owner-facing summary itself, on its own
# terms. The Terminal backup block (printed unconditionally below) covers the
# human running the updater by hand.
#
# The OLD form sent the raw "update applied / partial" result via
# `message send --target allowFrom[0]`, which on most boxes is the CLIENT's own
# chat (and on operator-first boxes, blindly the operator). Either way it
# AUTO-PUSHED internal update chatter to a chat. Per OPERATOR-MAINTENANCE.md
# (FIX 2 / v12.4.0): maintenance notifications use the OPERATOR session key /
# operator escalation chat — NEVER the client default — and NO-OP when no
# operator escalation chat is configured (no hardcoded default chat).
#
# Resolution: env.vars.OPERATOR_ESCALATION_CHAT_ID (written by
# configure-operator-telegram.sh) → operator account/session. If unset, we
# LOG-ONLY (no send) rather than fall back to any owner/allowFrom chat.
TELEGRAM_LAST_RESULT=""
send_telegram_progress() {
  local message="$1"
  local OCJSON="$HOME/.openclaw/openclaw.json"
  [ -d "/data/.openclaw" ] && OCJSON="/data/.openclaw/openclaw.json"
  local OPERATOR_CHAT=""
  TELEGRAM_LAST_RESULT="skipped"

  if ! command -v openclaw >/dev/null 2>&1; then
    TELEGRAM_LAST_RESULT="no-openclaw-cli"
    return 0
  fi

  # Resolve the OPERATOR escalation chat only — never the client default chat.
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

  if [ -z "$OPERATOR_CHAT" ]; then
    # No operator escalation chat configured → LOG-ONLY (the AGENTS.md UPDATE
    # PENDING flag + the Terminal backup block already cover the agent + human).
    # We deliberately do NOT fall back to allowFrom[0] / the client chat.
    {
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] update-result notification (operator escalation chat not configured — LOG-ONLY, NOT sent to any client chat):"
      printf '%s\n' "$message"
    } >> "$LOG_FILE" 2>&1
    TELEGRAM_LAST_RESULT="logged-no-operator-chat"
    return 0
  fi

  # Send on the OPERATOR session key, reply out the operator account — mirrors
  # the OPERATOR-MAINTENANCE.md operator-drive contract.
  if openclaw message send \
      --channel telegram \
      --account operator \
      --session-key agent:main:operator \
      --target "$OPERATOR_CHAT" \
      --message "$message" >> "$LOG_FILE" 2>&1; then
    TELEGRAM_LAST_RESULT="sent-operator:$OPERATOR_CHAT"
  else
    # Operator send failed (e.g. operator account has no token yet). Do NOT fall
    # back to the client chat — LOG-ONLY.
    {
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] update-result operator send FAILED (operator account likely missing token) — LOG-ONLY, NOT routed to any client chat:"
      printf '%s\n' "$message"
    } >> "$LOG_FILE" 2>&1
    TELEGRAM_LAST_RESULT="failed-operator:see-$LOG_FILE"
  fi
}

# ----------------------------------------------------------
# Write UPDATE PENDING flag to AGENTS.md
# ----------------------------------------------------------
write_update_pending_flag() {
  local version="$1"
  local new_skills="$2"

  # v10.15.48: resolve the canonical workspace the agent ACTUALLY reads from.
  # Prefer the OBS-resolved workspace (per-agent override -> defaults ->
  # canonical default). NEVER prefer the dead ~/clawd -- writing the flag there
  # while the agent reads ~/.openclaw/workspace is the classic "agent never sees
  # the flag" bug. Falls back to the canonical default only.
  local WORKSPACE_DIR=""
  if command -v obs_resolve_workspace >/dev/null 2>&1; then
    # v16.2.13: guard the substitution (mirror the guarded call at ~L1175) so a
    # non-zero from obs_resolve_workspace cannot abort the updater under
    # `set -euo pipefail` (this runs on the always-executed normal path via
    # write_update_pending_flag); the empty fallback below already handles it.
    WORKSPACE_DIR="$(obs_resolve_workspace 2>/dev/null || true)"
  fi
  [ -z "$WORKSPACE_DIR" ] && WORKSPACE_DIR="$HOME/.openclaw/workspace"
  mkdir -p "$WORKSPACE_DIR"
  local AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"

  touch "$AGENTS_FILE"
  # FIX 1: FULLY strip ALL prior UPDATE PENDING / ONBOARDING PENDING SECTIONS
  # (header → next "## " heading or EOF). The old `grep -v "UPDATE PENDING"`
  # only removed the single header LINE, leaving the multi-line body behind and
  # STACKING a fresh full flag on every run -- duplicates accreted forever.
  AGENTS_FILE="$AGENTS_FILE" python3 - <<'PYEOF' 2>/dev/null || true
import os, re
p = os.environ["AGENTS_FILE"]
try:
    text = open(p, encoding="utf-8", errors="replace").read()
except Exception:
    text = ""
# Remove any "## ... UPDATE PENDING ..." or "## ... ONBOARDING PENDING ..."
# section: from its "## " header up to (but not including) the next top-level
# "## " heading, or EOF. Non-greedy, multiline.
pattern = re.compile(
    r'(?m)^##[^\n]*(?:UPDATE PENDING|ONBOARDING PENDING)[^\n]*\n'   # the header
    r'(?:(?!^##\s).*\n?)*',                                         # body until next "## "
)
new = pattern.sub("", text)
# Collapse >2 blank lines left behind.
new = re.sub(r'\n{3,}', '\n\n', new)
open(p, "w", encoding="utf-8").write(new)
PYEOF

  local DATE_STAMP
  DATE_STAMP=$(date +%Y-%m-%d)

  cat >> "$AGENTS_FILE" <<FLAGCONTENT

## UPDATE PENDING -- Skill Update to ${version}

A skill update was applied via update-skills.sh on ${DATE_STAMP}. Activate each new skill below,
run the verification gate, then remove this section from AGENTS.md when the gate passes.

### 🔴 THE GATE IS THE TRUTH -- NOT THIS PROSE, NOT YOUR OWN "done"
This update is **NOT complete** until the VERIFICATION GATE passes. Files on disk = DOWNLOADED, not installed. Source the gate and check state:
- State file: \`~/.openclaw/workspace/.onboarding-state.json\` (per-skill: pending → downloaded → wired → qc-passed | qc-failed)
- Gate library: \`~/.openclaw/scripts/onboarding-state.sh\` (or the onboarding repo's \`scripts/\`)
- Run: source the library, then \`obs_gate_summary\`. A skill counts INSTALLED only when (a) \`openclaw skills info <name>\` shows it, (b) its CORE_UPDATES sentinel is present (if it ships CORE_UPDATES.md), and (c) its \`qc-*.sh\` exits 0 (if it ships one).
- **NEVER tell the owner "installed / done / onboarded" for any skill that is not \`qc-passed\` (or an explicit INTERVIEW_PENDING park).**

### What changed in this update
- Onboarding version: ${version}
- New skills installed (require ACTIVATION + GATE): ${new_skills:-none -- updates only}

### How to process each skill that is NOT yet qc-passed
For each such skill folder under \`~/.openclaw/skills/\`:
1. READ all files (Teach Yourself Protocol): SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md, plus any \`references/*.md\` files
2. CHECK prerequisites and search ALL standard credential locations (canonical: \`~/.openclaw/secrets/.env\` on Mac, \`/data/.openclaw/secrets/.env\` on VPS, plus \`openclaw.json\` env.vars). Skip asking the owner if values already exist.
3. EXECUTE the activation steps in INSTALL.md (read ≠ execute)
4. APPLY CORE_UPDATES.md surgically -- add to AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md only the sections explicitly labeled in that file
5. RUN the gate (\`obs_verify_skill <folder>\`); loop activate→verify until it returns \`qc-passed\`. Skills that legitimately await owner input may be parked \`interview-pending\` (re-ping the owner; do NOT treat as terminal "done").
6. REPORT to owner ONLY what is verified-installed, plus what remains gated.

### Discipline (binding)
- Skills 22-23: MAIN ORCHESTRATOR ONLY, never delegate
- Tier order in any tiered skill (e.g. skill 36 GHL MCP): try Tier N before Tier N+1, no skipping
- Disclosure headers (e.g. \`[GHL tier used: N -- tool_name]\`) required per any skill's SOUL-level rules
- No destructive shortcuts: no \`--force\`, no \`--no-verify\`, no \`--break-system-packages\` unless explicitly instructed

### When the GATE passes (and ONLY then)
- Remove this entire UPDATE PENDING section from AGENTS.md
- Add to MEMORY.md under "## System Updates":
  "${version} update applied on ${DATE_STAMP}. Verification gate PASSED. Skills activated: ${new_skills:-none}."

FLAGCONTENT
  echo "  ✓ UPDATE PENDING flag written (deduped) to $AGENTS_FILE"

  # Seed Core.md terminology into MEMORY.md (idempotent)
  local MEMORY_FILE="$WORKSPACE_DIR/MEMORY.md"
  touch "$MEMORY_FILE"
  if ! grep -q "## Terminology -- Core.md Files" "$MEMORY_FILE" 2>/dev/null; then
    cat >> "$MEMORY_FILE" << 'COREMDEOF'

## Terminology -- Core.md Files

When the owner says **"Core.md files"** they mean the OpenClaw bootstrap files loaded every session -- not a literal file called `core.md`. The Core.md files are:

- **IDENTITY.md** -- the role the agent is playing. It contains the **experiences and the skills they need to embody** that role. Not just surface metadata (name / vibe / emoji) -- the lived background and capability set of the character being played.
- **SOUL.md** -- the **personality** of the agent, its **true mission**, its **beliefs**, its **rules**, its **goals**, its **belief systems**, its **principles**. Who the agent IS, not who they are playing. First file injected each session.
- **AGENTS.md** -- operating procedures, protocols, workflows, memory rules. *What the agent does and how*
- **USER.md** -- the human being helped (name, timezone, preferences, communication style)
- **TOOLS.md** -- local tool notes and conventions (camera names, SSH aliases, environment-specific specifics) -- NOT a permissions registry
- **MEMORY.md** -- curated long-term durable facts, decisions, preferences. Loaded in main private sessions; paired with daily logs at `memory/YYYY-MM-DD.md`

When the owner says "update the Core.md files" or "this needs to live in the Core.md files," choose the right one of these six based on its purpose:
- Personality / principle → SOUL.md
- Procedure / workflow → AGENTS.md
- Tool note → TOOLS.md
- Durable fact / decision → MEMORY.md
- User info → USER.md
- Identity metadata → IDENTITY.md

Never interpret "Core.md" as a literal filename.

COREMDEOF
    echo "  ✓ Core.md terminology seeded into MEMORY.md"
  fi
}

# ----------------------------------------------------------
# SKILLS DIRECTORY SECTION -- Active-dir-first detection
# ----------------------------------------------------------
# Platform detection:
#   VPS  (Hostinger Docker) → active dir is /data/.openclaw/skills
#   Mac                     → active dir is ~/.openclaw/skills
# We ALWAYS prefer the directory the running agent actually loads,
# falling back to ~/Downloads/openclaw-master-files only when the
# active dir doesn't exist.  Updating a stale Downloads copy while
# the active dir is untouched is a silent no-op (the classic bug).
# ----------------------------------------------------------

# ----------------------------------------------------------
# Discover skills directory -- active dir first
# ----------------------------------------------------------
discover_skills_dir() {
  # Detect platform: VPS has /data, Mac does not
  if [ -d /data ]; then
    # VPS (Hostinger Docker) -- active path is /data/.openclaw/skills
    local ACTIVE_DIR="/data/.openclaw/skills"
  else
    # Mac -- active path is ~/.openclaw/skills
    local ACTIVE_DIR="$HOME/.openclaw/skills"
  fi

  # Use the active dir whenever it exists and is non-empty
  if [ -d "$ACTIVE_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$ACTIVE_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$ACTIVE_DIR"
      return
    fi
  fi

  # Active dir exists but is empty (first-install into it) -- still prefer it
  if [ -d "$ACTIVE_DIR" ]; then
    echo "$ACTIVE_DIR"
    return
  fi

  # Fallback: check Downloads copy (legacy / pre-active-dir installs)
  local LEGACY_DIR="$HOME/Downloads/openclaw-master-files"
  if [ -d "$LEGACY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$LEGACY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$LEGACY_DIR"
      return
    fi
  fi

  # Fuzzy search for folders with "openclaw" and "master" in name (case-insensitive)
  local FUZZY_DIR=$(find "$HOME" -maxdepth 2 -type d -iname "*openclaw*" 2>/dev/null | grep -i "master" | head -1 || true)
  if [ -n "$FUZZY_DIR" ] && [ -d "$FUZZY_DIR" ]; then
    local SKILL_COUNT=$(ls -d "$FUZZY_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
    if [ "$SKILL_COUNT" -gt "0" ]; then
      echo "$FUZZY_DIR"
      return
    fi
  fi

  # Last resort: create and target the active dir (fresh install)
  echo "$ACTIVE_DIR"
}

# ----------------------------------------------------------
# UPDATE PENDING flag handling -- search correct locations
# ----------------------------------------------------------
check_update_pending() {
  # Search Mac primary location first, then secondary
  local PENDING_PATHS=(
    "$HOME/Downloads/openclaw-master-files/.pending-setup.md"
    "$HOME/.openclaw/skills/.pending-setup.md"
    "$HOME/.openclaw/onboarding/.pending-setup.md"
  )

  for PENDING in "${PENDING_PATHS[@]}"; do
    if [ -f "$PENDING" ]; then
      echo "$PENDING"
      return
    fi
  done

  # Return empty if not found
  echo ""
}

# ----------------------------------------------------------
# Check .onboarding-version -- search multiple paths
# Priority MUST match discover_skills_dir() (active dir first, legacy second)
# so the version we READ is the same location we WRITE to. If the legacy
# Downloads path is checked first the script sees the old stale marker even
# after a successful update → perpetual "needs update" false-positive (Bug B).
# ----------------------------------------------------------
get_current_version() {
  # Active dir first (mirrors discover_skills_dir priority)
  local VERSION_PATHS=(
    "$HOME/.openclaw/skills/.onboarding-version"
    "$HOME/Downloads/openclaw-master-files/.onboarding-version"
    "$HOME/.openclaw/onboarding/.onboarding-version"
  )

  for VERSION_FILE in "${VERSION_PATHS[@]}"; do
    if [ -f "$VERSION_FILE" ]; then
      cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]'
      return
    fi
  done

  # Return empty if not found
  echo ""
}

# ----------------------------------------------------------
# v20.0.65 - safe_json_edit
# Harden any direct write to openclaw.json: back up, apply the
# python3 transform, validate with `openclaw config validate`,
# and ROLL BACK from the backup on failure so one bad key can
# never abort the updater under set -euo pipefail.
#
# The root-cause bug that aborted a multi-client update was
# skills.path written into openclaw.json on VPS (2026.5.x rejects
# the key with "skills Unrecognized key path / skills Invalid input").
# This helper ensures any future json edits are validated before they
# can corrupt the config and kill the run.
#
# Usage:
#   safe_json_edit OCJSON_PATH DESCRIPTION python3_transform_func
# where python3_transform_func is a bash function that:
#   - receives OCJSON_PATH as $1
#   - edits the file in-place
#   - exits 0 on success, non-zero on failure
#
# Note: the Mac updater has NO direct json.dump writes today --
# GHL MCP wiring uses `openclaw mcp set` which validates its own
# input. This helper is provided here as a forward-defense guard
# so future changes are forced to go through validation + rollback.
# ----------------------------------------------------------
safe_json_edit() {
  local OCJSON="$1"
  local DESCRIPTION="${2:-openclaw.json edit}"
  local EDIT_FUNC="$3"

  if [ ! -f "$OCJSON" ]; then
    echo "  [safe_json_edit] $OCJSON not found -- skipping $DESCRIPTION"
    return 0
  fi

  local BACKUP="${OCJSON}.bak-$(date +%Y%m%d-%H%M%S)"
  cp -f "$OCJSON" "$BACKUP" 2>/dev/null || {
    echo "  [safe_json_edit] WARN: could not create backup -- skipping $DESCRIPTION"
    return 0
  }

  # Run the edit function
  if ! "$EDIT_FUNC" "$OCJSON"; then
    echo "  [safe_json_edit] WARN: edit function failed -- rolling back $DESCRIPTION"
    cp -f "$BACKUP" "$OCJSON" 2>/dev/null || true
    rm -f "$BACKUP" 2>/dev/null || true
    return 0
  fi

  # Validate with the CLI if available
  if command -v openclaw >/dev/null 2>&1; then
    if ! openclaw config validate >> "$LOG_FILE" 2>&1; then
      echo "  [safe_json_edit] WARN: openclaw config validate FAILED after $DESCRIPTION -- rolling back"
      cp -f "$BACKUP" "$OCJSON" 2>/dev/null || true
      rm -f "$BACKUP" 2>/dev/null || true
      return 0
    fi
  fi

  rm -f "$BACKUP" 2>/dev/null || true
  echo "  [safe_json_edit] $DESCRIPTION applied and validated OK"
}

# ----------------------------------------------------------
# v10.15.51 -- link_shared_core_files
# ----------------------------------------------------------
# Zero-Human-Workforce file model: on EVERY box, ALL of that account's agents
# + sub-agents SHARE the box's ONE canonical AGENTS.md / TOOLS.md / USER.md
# (symlinked, NOT duplicated). Per-agent files (IDENTITY.md, SOUL.md, MEMORY.md,
# HEARTBEAT.md) stay each agent's OWN real files -- never touched here (except
# additive content preservation into IDENTITY.md, see below).
#
# CANON_DIR = the box's DEFAULT AGENT WORKSPACE (agents.defaults.workspace, with
# the same resolver as obs_resolve_workspace / install.sh Step 10). The canonical
# AGENTS.md/TOOLS.md/USER.md live there. The symlink target is ALWAYS this LOCAL
# box's own canonical -- NEVER a hardcoded path and NEVER a cross-box/cross-account
# path. The client is the USER; a client box links to the CLIENT's own files only.
# This is the co-mingling guard (N0): we read THIS box's openclaw.json and resolve
# THIS box's workspace -- we never write a foreign path into a client's symlink.
#
# NESTED WORKFLOW AGENT EXEMPTION: any workspace path matching */workflows/*/agents/*
# is an internal workflow micro-agent and is NEVER touched.
#
# Idempotent: a second run produces no new backups and no churn -- a symlink that
# already points at CANON_DIR/<f> is a no-op; an absent file is left absent.
# Every action is logged with the [link-shared] prefix.
# ----------------------------------------------------------
link_shared_core_files() {
  local CANON_DIR="${1:-}"

  # --- Resolve CANON_DIR (box's own default agent workspace) ---------------
  # Precedence mirrors obs_resolve_workspace / install.sh Step 10:
  #   per-agent main override -> agents.defaults.workspace -> ~/.openclaw/workspace.
  # We ALWAYS read THIS box's openclaw.json -- never a foreign/hardcoded path.
  local OCJSON="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && OCJSON="/data/.openclaw/openclaw.json"
  if [ -z "$CANON_DIR" ]; then
    if command -v obs_resolve_workspace >/dev/null 2>&1; then
      CANON_DIR="$(obs_resolve_workspace)"
    elif [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
      CANON_DIR="$(OC_JSON="$OCJSON" python3 - <<'PYEOF' 2>/dev/null || true
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
  # Final fallback: the canonical OpenClaw default for this box. (Clawd is dead;
  # only fall back to ~/clawd as an absolute last resort if it is the workspace.)
  if [ -z "$CANON_DIR" ]; then
    if [ -d "/data/.openclaw" ]; then
      CANON_DIR="/data/.openclaw/workspace"
    else
      CANON_DIR="$HOME/.openclaw/workspace"
    fi
  fi

  echo "  [link-shared] Zero-Human-Workforce file unification"
  echo "  [link-shared] CANON_DIR (this box's own canonical) = $CANON_DIR"
  mkdir -p "$CANON_DIR" 2>/dev/null || true

  # The canonical files must exist before we can link to them. touch ensures a
  # symlink target is always present (empty is fine; later wiring fills them).
  local f
  for f in AGENTS.md TOOLS.md USER.md; do
    [ -e "$CANON_DIR/$f" ] || { touch "$CANON_DIR/$f" 2>/dev/null || true; }
  done

  # Resolve CANON_DIR to an absolute, symlink-free real path so comparisons and
  # link targets are stable + correct.
  local CANON_REAL
  CANON_REAL="$(cd "$CANON_DIR" 2>/dev/null && pwd -P || echo "$CANON_DIR")"

  local TS
  TS="$(date +%Y%m%d-%H%M%S)"

  # --- Enumerate agent workspaces ------------------------------------------
  # Sources: (a) every agents[].workspace declared in THIS box's openclaw.json,
  # (b) a scan of the workspaces/ dir (immediate children + agents/* role dirs).
  # We only ever operate on dirs under this box. Dedup; skip CANON; skip nested workflow agents.
  local WS_LIST_FILE
  WS_LIST_FILE="$(mktemp 2>/dev/null || echo "/tmp/link-shared-ws-$$.txt")"
  : > "$WS_LIST_FILE"

  if [ -f "$OCJSON" ] && command -v python3 >/dev/null 2>&1; then
    OC_JSON="$OCJSON" python3 - >> "$WS_LIST_FILE" 2>/dev/null <<'PYEOF' || true
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

  # Scan the workspaces dir tree for agent-shaped dirs. The canonical default
  # parent is .openclaw/ (or /data/.openclaw); also scan the workspace's own
  # departments/ + agents/ trees where role workspaces live.
  local OC_ROOT="$HOME/.openclaw"
  [ -d "/data/.openclaw" ] && OC_ROOT="/data/.openclaw"
  local _scan
  for _scan in \
      "$OC_ROOT/workspaces" \
      "$CANON_REAL/agents" \
      "$CANON_REAL/departments"; do
    [ -d "$_scan" ] || continue
    # Any dir that already carries one of the shared files (real or link) is an
    # agent workspace candidate. find -type d then filter in the loop below.
    find "$_scan" -type d \( -name 'AGENTS.md' -prune \) -o -type d -print 2>/dev/null \
      | while IFS= read -r d; do
          if [ -e "$d/AGENTS.md" ] || [ -e "$d/IDENTITY.md" ] || [ -e "$d/SOUL.md" ]; then
            echo "$d"
          fi
        done >> "$WS_LIST_FILE" 2>/dev/null || true
  done

  local LINKED=0 REPOINTED=0 BACKED_UP=0 PRESERVED=0 SKIPPED_ANT=0 NOOP=0

  # Dedup workspace list, then process each.
  local W
  while IFS= read -r W; do
    [ -n "$W" ] || continue
    W="$(printf '%s' "$W" | sed 's:/*$::')"   # strip trailing slashes
    [ -d "$W" ] || continue

    # Resolve to absolute real path for a correct CANON comparison.
    local W_REAL
    W_REAL="$(cd "$W" 2>/dev/null && pwd -P || echo "$W")"

    # Skip the canonical workspace itself -- it OWNS the real files.
    if [ "$W_REAL" = "$CANON_REAL" ]; then
      continue
    fi

    # NESTED WORKFLOW AGENT EXEMPTION: never touch */workflows/*/agents/* micro-agents.
    case "$W_REAL/" in
      */workflows/*/agents/*)
        echo "  [link-shared] SKIP (nested workflow agent exempt): $W_REAL"
        SKIPPED_ANT=$((SKIPPED_ANT + 1))
        continue
        ;;
    esac

    for f in AGENTS.md TOOLS.md USER.md; do
      local TARGET="$CANON_REAL/$f"
      local LINKPATH="$W_REAL/$f"

      if [ -L "$LINKPATH" ]; then
        # Already a symlink -- repoint ONLY if it points somewhere wrong.
        local CUR
        CUR="$(readlink "$LINKPATH" 2>/dev/null || echo '')"
        # Resolve current target to a real path for comparison.
        local CUR_REAL
        CUR_REAL="$(cd "$(dirname "$LINKPATH")" 2>/dev/null && cd "$(dirname "$CUR")" 2>/dev/null && pwd -P 2>/dev/null)/$(basename "$CUR")"
        if [ "$CUR" = "$TARGET" ] || [ "$CUR_REAL" = "$TARGET" ]; then
          NOOP=$((NOOP + 1))   # idempotent: correct link, no churn
        else
          ln -sfn "$TARGET" "$LINKPATH" 2>/dev/null \
            && { echo "  [link-shared] REPOINT $LINKPATH -> $TARGET (was: $CUR)"; REPOINTED=$((REPOINTED + 1)); } \
            || echo "  [link-shared] WARN: could not repoint $LINKPATH"
        fi

      elif [ -f "$LINKPATH" ]; then
        # A REAL file. Back it up (NEVER delete), preserve unique content into
        # this agent's OWN IDENTITY.md (additive only), then replace with a link.
        local BAK="$LINKPATH.bak-unify-$TS"
        cp -p "$LINKPATH" "$BAK" 2>/dev/null \
          && { echo "  [link-shared] BACKUP $LINKPATH -> $BAK"; BACKED_UP=$((BACKED_UP + 1)); } \
          || { echo "  [link-shared] WARN: backup failed for $LINKPATH -- leaving file untouched"; continue; }

        # Best-effort PRESERVE: append any content NOT already in CANON/<f> to
        # this agent's OWN IDENTITY.md under a guarded marker (only ADD; create
        # IDENTITY.md if absent). Guard prevents duplicate preservation on re-run.
        local AGENT_NAME
        AGENT_NAME="$(basename "$W_REAL")"
        local IDFILE="$W_REAL/IDENTITY.md"
        local PMARK="<!-- PRESERVED FROM ${AGENT_NAME} ${f} (unification ${TS}) -->"
        # Marker prefix (sans timestamp) used to detect prior preservation of the
        # same agent+file so re-runs never re-append.
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
# Split the agent's file into blank-line-delimited blocks; keep only blocks
# whose stripped text is non-empty AND not already present in the canonical file.
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
            echo "  [link-shared] PRESERVE unique $f content -> $IDFILE"
            PRESERVED=$((PRESERVED + 1))
          fi
        fi

        # Replace the real file with a symlink to the box's own canonical.
        rm -f "$LINKPATH" 2>/dev/null
        ln -sfn "$TARGET" "$LINKPATH" 2>/dev/null \
          && { echo "  [link-shared] LINK $LINKPATH -> $TARGET"; LINKED=$((LINKED + 1)); } \
          || echo "  [link-shared] WARN: could not create symlink $LINKPATH"

      else
        # Absent → leave absent. (No churn.)
        :
      fi
    done
  done < <(sort -u "$WS_LIST_FILE")

  rm -f "$WS_LIST_FILE" 2>/dev/null || true

  echo "  [link-shared] done: linked=$LINKED repointed=$REPOINTED backed-up=$BACKED_UP preserved=$PRESERVED workflow-agent-skipped=$SKIPPED_ANT already-ok=$NOOP"
  echo "  [link-shared] IDENTITY/SOUL/MEMORY/HEARTBEAT left as each agent's OWN files (per-agent, not shared)."
}

# ----------------------------------------------------------
# Main update logic
# ----------------------------------------------------------
main() {
  # DEFECT 3 (v13.1.3): always wire from the intended version. Capture argv for a
  # possible re-exec, then run the self-sync guard BEFORE any download/wiring.
  SELF_SYNC_ARGS=("$@")
  self_sync_guard

  # ----------------------------------------------------------
  # SECURITY/PRIVACY (v20.0.9) — MAINTENANCE-SILENT for the WHOLE roll. A fleet
  # roll / skill update is inherently MAINTENANCE: no step may push an internal
  # notification to a client chat. Export OPENCLAW_MAINTENANCE_SILENT=1 for the
  # entire duration of this run so EVERY subprocess it spawns inherits it —
  # migrate-existing-workforce.sh (which runs qc-completeness.sh at its Step 5)
  # AND the embedded qc-completeness.sh call later in this function.
  # qc-completeness.sh treats this as a HARD send-suppression gate that is
  # INDEPENDENT of any box's chat/account config, so a box whose operator-
  # escalation chat is mis-pointed at the client still cannot leak the QC gap
  # table during a roll. It gates NOTIFICATION only, never what QC computes.
  # ----------------------------------------------------------
  export OPENCLAW_MAINTENANCE_SILENT=1

  # ----------------------------------------------------------
  # Parse CLI args: --only "05,06,35" installs only those skill folders
  # (number prefix matches skill folder name prefix)
  # ----------------------------------------------------------
  ONLY_SKILLS=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --only)
        shift
        ONLY_SKILLS="${1:-}"
        ;;
      --only=*)
        ONLY_SKILLS="${1#--only=}"
        ;;
      --help|-h)
        echo "Usage: update-skills.sh [--only \"05,06,35\"]"
        echo "  --only LIST   Install only skill folders whose number prefix matches LIST (comma-separated)"
        echo "                Example: --only \"05,06,36\" installs only skills 05-ghl-setup, 06-ghl-install-pages, 36-ghl-mcp-setup"
        echo "  (no flag)     Install/update all skills"
        exit 0
        ;;
    esac
    shift || true
  done

  echo "============================================"
  echo "   OpenClaw Skills Updater (Mac)"
  echo "   Version: ${ONBOARDING_VERSION}"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE -- only [$ONLY_SKILLS]"
  fi
  echo "============================================"
  echo ""

  # Discover skills directory
  SKILLS_DIR=$(discover_skills_dir)
  export SKILLS_DIR
  echo "  📂 Skills directory: $SKILLS_DIR"

  # ----------------------------------------------------------
  # Catchup check: if last weekly cron check is older than 7 days,
  # surface a note so the user knows the Sunday cron may have missed.
  # ----------------------------------------------------------
  if [ -f "$SKILLS_DIR/.last-update-check" ]; then
    LAST_CHECK_TS=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$(cat "$SKILLS_DIR/.last-update-check")" +%s 2>/dev/null || \
                    date -d "$(cat "$SKILLS_DIR/.last-update-check")" +%s 2>/dev/null || echo 0)
    NOW_TS=$(date +%s)
    if [ "$LAST_CHECK_TS" -gt 0 ]; then
      DAYS_SINCE=$(( (NOW_TS - LAST_CHECK_TS) / 86400 ))
      if [ "$DAYS_SINCE" -gt 7 ]; then
        echo "  ℹ️  Weekly Sunday check last ran ${DAYS_SINCE} days ago -- your machine may have been asleep."
        echo "      This manual run will catch up."
      fi
    fi
  fi

  # Check for UPDATE PENDING flag
  PENDING_FILE=$(check_update_pending)
  if [ -n "$PENDING_FILE" ]; then
    echo "  ⚠️  UPDATE PENDING flag found at: $PENDING_FILE"
    echo "      Review this file before updating: cat $PENDING_FILE"
    echo ""
    # TTY GUARD (v17.0.18): only prompt when stdin is an interactive terminal.
    # Non-interactive (cron / curl|bash / SSH pipe): auto-decline so the updater
    # can never hang on stdin during a re-roll. Interactive behaviour is unchanged.
    if [ -t 0 ]; then
      read -p "Continue with update? (y/N) " -n 1 -r
      echo
    else
      echo "  (non-interactive: no TTY — auto-declining the pending-flag prompt)"
      REPLY="N"
    fi
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "  Update cancelled."
      exit 0
    fi
  fi

  # Check current version
  CURRENT_VERSION=$(get_current_version)
  if [ -n "$CURRENT_VERSION" ]; then
    echo "  Current version: $CURRENT_VERSION"
    echo "  Latest version:  $ONBOARDING_VERSION"
    if [ "$CURRENT_VERSION" = "$ONBOARDING_VERSION" ]; then
      echo ""
      # TTY GUARD (v17.0.18): a re-roll at the SAME version always reaches this
      # prompt. Only prompt on an interactive terminal; non-interactively
      # auto-decline the force-reinstall and exit 0 (already up to date — a clean,
      # idempotent no-op) instead of hanging on stdin.
      if [ -t 0 ]; then
        read -p "Already up to date. Force re-install? (y/N) " -n 1 -r
        echo
      else
        echo "  (non-interactive: no TTY — already up to date, not forcing re-install)"
        REPLY="N"
      fi
      if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  Update cancelled."
        exit 0
      fi
    fi
  else
    echo "  No previous version found -- fresh install"
  fi

  echo ""
  echo "  Downloading latest skills from GitHub..."

  # v10.15.18: clone instead of curl|unzip. Info-ZIP's `unzip` MANGLES UTF-8
  # filenames (the role-library has em-dash filenames like
  # `qc-specialist----sales.md` and `deep-research-role----openclaw-maintenance.md`)
  # and silently partial-writes them, so a zip-based update would drop or
  # corrupt those role docs. `git clone` preserves every filename byte-for-byte.
  TEMP_ZIP="/tmp/openclaw-onboarding-update.zip"
  TEMP_EXTRACT="/tmp/openclaw-onboarding-update"
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
  EXTRACTED_DIR=""

  if command -v git >/dev/null 2>&1; then
    if git clone --depth 1 "https://github.com/trevorotts1/openclaw-onboarding.git" "$TEMP_EXTRACT" 2>/dev/null; then
      # HARD verify the remote is exactly the intended repo (no leftover-clone mix-up)
      _origin="$(git -C "$TEMP_EXTRACT" remote get-url origin 2>/dev/null)"
      case "$_origin" in
        https://github.com/trevorotts1/openclaw-onboarding.git|https://github.com/trevorotts1/openclaw-onboarding)
          EXTRACTED_DIR="$TEMP_EXTRACT"
          # A2: capture source git SHA for content-manifest
          SRC_GIT_SHA="$(git -C "$TEMP_EXTRACT" rev-parse HEAD 2>/dev/null || echo "")"
          SRC_FROM_ZIP=0 ;;
        *)
          echo "ERROR: cloned remote ($_origin) is NOT trevorotts1/openclaw-onboarding -- refusing to use it."
          rm -rf "$TEMP_EXTRACT"; EXTRACTED_DIR="" ;;
      esac
    fi
  fi

  # Fallback ONLY if git is unavailable or the clone failed: zip + Mac-native
  # `ditto` (NOT Info-ZIP unzip) which handles UTF-8 filenames correctly.
  if [ -z "$EXTRACTED_DIR" ]; then
    echo "  (git clone unavailable/failed -- falling back to zip + ditto)"
    curl -fSL --progress-bar "https://github.com/trevorotts1/openclaw-onboarding/archive/refs/heads/main.zip" -o "$TEMP_ZIP"
    rm -rf "$TEMP_EXTRACT"; mkdir -p "$TEMP_EXTRACT"
    if command -v ditto >/dev/null 2>&1; then
      ditto -x -k "$TEMP_ZIP" "$TEMP_EXTRACT" 2>/dev/null || true
    else
      unzip -qo "$TEMP_ZIP" -d "$TEMP_EXTRACT" 2>/dev/null || true
    fi
    if [ -d "$TEMP_EXTRACT/openclaw-onboarding-main" ]; then
      EXTRACTED_DIR="$TEMP_EXTRACT/openclaw-onboarding-main"
    else
      # v16.2.13: `| head -1` closes the pipe early → `find` can die with SIGPIPE
      # (rc 141) which `pipefail` promotes to the pipeline status; `|| true` keeps
      # the plain assignment from aborting the updater under `set -e` (the first
      # dir is still captured before the SIGPIPE).
      EXTRACTED_DIR=$(find "$TEMP_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1 || true)
    fi
    # A2: zip fallback — no git SHA available; content-set hash still works
    SRC_GIT_SHA="zip-fallback-$(date -u +%Y%m%dT%H%M%SZ)"
    SRC_FROM_ZIP=1
  fi

  if [ -z "$EXTRACTED_DIR" ] || [ ! -d "$EXTRACTED_DIR" ]; then
    echo "ERROR: Could not obtain the latest skills (git clone + zip fallback both failed)"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # v10.15.48: canonical onboarding dir for the freshly-pulled repo. Root-level
  # scripts/ (apply-fleet-standards.sh, ghl-mcp-autostart.sh, the new
  # resume-onboarding wiring) live here. Previously $ONBOARDING_DIR was
  # referenced (fleet-standards call) but never set under `set -u` -- a latent
  # bug. Define it once here so every downstream script reference resolves.
  ONBOARDING_DIR="$EXTRACTED_DIR"
  export ONBOARDING_DIR

  # A2: Compute SOURCE manifest from the pulled tree BEFORE the copy loop.
  # This is what the destination must match after install (A3 gate).
  _CONTENT_HASH_SCRIPT="$EXTRACTED_DIR/scripts/skill-content-hash.sh"
  SRC_MANIFEST=""
  if [ -f "$_CONTENT_HASH_SCRIPT" ]; then
    SRC_MANIFEST=$(bash "$_CONTENT_HASH_SCRIPT" "$EXTRACTED_DIR" 2>/dev/null || true)
    printf '%s\n' "$SRC_MANIFEST" > /tmp/openclaw-update-src-manifest.txt
    echo "  [A2] Source content manifest computed ($(echo "$SRC_MANIFEST" | wc -l | tr -d ' ') lines)"
  else
    echo "  [A2] skill-content-hash.sh not found in source — content verification unavailable (non-fatal for this install)"
    SRC_MANIFEST=""
  fi

  # v10.15.48 (FIX 1): source the onboarding STATE MACHINE + verification GATE.
  # Seed the state file with every non-archived skill at "pending" from the
  # freshly-pulled source. Statuses then advance downloaded -> wired -> qc-passed
  # as the run progresses; the "complete" report is GATED on these (below).
  # v17.0.19 FIX: resolve + source the onboarding-state shim ROBUSTLY by absolute
  # path — prefer the freshly-pulled tree ($ONBOARDING_DIR), fall back to this
  # updater's own dir ($_SCRIPT_DIR) so the obs_* API stays reachable even if
  # $ONBOARDING_DIR is somehow unset. The shim DEFINES the obs_* honesty
  # state-machine + verification GATE (obs_seed_state / obs_verify_skill /
  # obs_gate_summary / ...); sourcing the canonical oc_* lib ALONE does NOT define
  # obs_*, which is why the seed printed "obs_seed_state: command not found" and the
  # verification gate (command -v obs_verify_skill) degraded to file-sync-only on
  # every roll. After sourcing we SELF-VERIFY obs_seed_state is actually defined
  # before invoking it, so a bundle mismatch degrades LOUDLY (clear message)
  # instead of emitting a raw "command not found".
  _OBS_SHIM=""
  for _obs_cand in "$ONBOARDING_DIR/scripts/onboarding-state.sh" "${_SCRIPT_DIR:-}/scripts/onboarding-state.sh"; do
    if [ -n "$_obs_cand" ] && [ -f "$_obs_cand" ]; then _OBS_SHIM="$_obs_cand"; break; fi
  done
  if [ -n "$_OBS_SHIM" ]; then
    # shellcheck disable=SC1090
    source "$_OBS_SHIM"
    # v17.0.21: source the SHARED onboarding-resume cron installer (repo-root lib)
    # so the roll/hot-patch path can install the SAME SILENT, bounded, self-removing
    # resume cron install.sh registers — no copy-paste drift. Sourced NOW (before the
    # temp-clone cleanup below) so the function persists in-shell; the prompt file it
    # reads is persisted to $OC_PERSISTENT_SCRIPTS_DIR just below.
    for _rc_lib in "$ONBOARDING_DIR/lib-onboarding-resume-cron.sh" "${_SCRIPT_DIR:-}/lib-onboarding-resume-cron.sh"; do
      if [ -n "$_rc_lib" ] && [ -f "$_rc_lib" ]; then
        # shellcheck disable=SC1090
        source "$_rc_lib"; break
      fi
    done
    command -v install_onboarding_resume_cron >/dev/null 2>&1 || install_onboarding_resume_cron() { :; }
    if command -v obs_seed_state >/dev/null 2>&1; then
      obs_seed_state "$ONBOARDING_VERSION" "$EXTRACTED_DIR" || echo "  ⚠ onboarding-state seed reported an issue (continuing)"
    else
      echo "  ⚠ onboarding-state.sh sourced ($_OBS_SHIM) but obs_seed_state is UNDEFINED -- honesty gate disabled for this run (bundle mismatch)."
    fi
    # Make the gate library + helper scripts available to the running agent at
    # the canonical ~/.openclaw/scripts/ (where install.sh also lands them).
    _OC_SCRIPTS_DEST="$HOME/.openclaw/scripts"
    [ -d "/data/.openclaw" ] && _OC_SCRIPTS_DEST="/data/.openclaw/scripts"
    mkdir -p "$_OC_SCRIPTS_DEST" 2>/dev/null || true
    # BUG-FIX v13.0.1: ensure-pipeline-crons.sh is ADDED here so it is persisted
    # to ~/.openclaw/scripts (a path that SURVIVES the temp-clone cleanup at the
    # "# Cleanup" rm -rf below). The cron-backfill block runs AFTER that cleanup,
    # so it must NOT depend on $ONBOARDING_DIR (the wiped clone) — it reads the
    # persistent copy instead. Same reason apply-fleet-standards.sh is here.
    # install-ceo-intent-gate.sh + verify-routing.sh are persisted here (v16.2.19)
    # so the intent-gate wire + post-stamp verification below can resolve them after
    # the temp-clone cleanup, same as apply-routing-fix.sh / apply-fleet-standards.sh.
    # D20 rename (U93): loop-protection-canary.sh -> loop-protection-first-proof.sh.
    # BOTH names are persisted here for one release — the old path is now a thin
    # compatibility shim that execs the new one, so an existing live-box cron
    # registration still calling the old path keeps resolving after this cleanup.
    for _s in onboarding-state.sh ghl-mcp-autostart.sh configure-operator-telegram.sh heal-config-shapes.py resume-onboarding.sh apply-fleet-standards.sh apply-routing-fix.sh install-ceo-intent-gate.sh verify-routing.sh repair-model-sovereignty.sh install-hardening.sh ensure-heartbeat-defaults.sh ensure-pipeline-crons.sh diagnose-telegram-config.sh index-model-drift-check.sh orphan-temp-sweep.sh disk-usage-alert.sh pre-july14-embedding-migration-check.sh agent-browser-reaper.sh harden-gws-credential-resilience.sh activate-loop-protection.sh loop-protection-first-proof.sh loop-protection-canary.sh; do
      [ -f "$ONBOARDING_DIR/scripts/$_s" ] && cp -f "$ONBOARDING_DIR/scripts/$_s" "$_OC_SCRIPTS_DEST/$_s" 2>/dev/null || true
      [ -f "$_OC_SCRIPTS_DEST/$_s" ] && chmod +x "$_OC_SCRIPTS_DEST/$_s" 2>/dev/null || true
    done
    # v17.0.21: persist the onboarding-resume cron PROMPT (a .txt, NOT covered by
    # the .sh loop above) so install_onboarding_resume_cron can resolve it AFTER
    # the temp-clone cleanup wipes $ONBOARDING_DIR (same persistence rationale as
    # resume-onboarding.sh). Resolved via $OC_PERSISTENT_SCRIPTS_DIR at cron time.
    [ -f "$ONBOARDING_DIR/scripts/resume-onboarding-prompt.txt" ] && \
      cp -f "$ONBOARDING_DIR/scripts/resume-onboarding-prompt.txt" "$_OC_SCRIPTS_DEST/resume-onboarding-prompt.txt" 2>/dev/null || true
    # Export the persistent scripts dir so the post-cleanup cron-backfill /
    # fleet-standards blocks can resolve these scripts after $ONBOARDING_DIR is gone.
    export OC_PERSISTENT_SCRIPTS_DIR="$_OC_SCRIPTS_DEST"
  else
    echo "  ⚠ onboarding-state.sh not found in pulled repo -- honesty gate disabled for this run (older bundle?)"
  fi

  # Backup existing skills
  if [ -d "$SKILLS_DIR" ] && [ "$(ls -A "$SKILLS_DIR" 2>/dev/null)" ]; then
    BACKUP_DIR="$HOME/Downloads/openclaw-backups/skills-backup-$(date +%Y%m%d-%H%M%S)"
    echo "  Creating backup: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    cp -r "$SKILLS_DIR"/* "$BACKUP_DIR/" 2>/dev/null || true
  fi

  # Ensure skills directory exists
  mkdir -p "$SKILLS_DIR"

  # Copy new skills
  echo "  Installing skills to $SKILLS_DIR..."
  NEW_SKILLS_CSV=""
  SKIPPED_COUNT=0
  for SKILL_DIR in "$EXTRACTED_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")

    # Skip archived skills
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # --only filter: if ONLY_SKILLS is set, install only matching prefixes
    if [ -n "$ONLY_SKILLS" ]; then
      SKILL_PREFIX=$(echo "$SKILL_NAME" | cut -d'-' -f1)
      MATCH="false"
      OIFS=$IFS; IFS=','
      for want in $ONLY_SKILLS; do
        want_trimmed=$(echo "$want" | tr -d '[:space:]')
        if [ "$SKILL_PREFIX" = "$want_trimmed" ]; then
          MATCH="true"
          break
        fi
      done
      IFS=$OIFS
      if [ "$MATCH" != "true" ]; then
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        continue
      fi
    fi

    # Check if this is a NEW skill (doesn't exist in current install)
    if [ ! -d "$SKILLS_DIR/$SKILL_NAME" ]; then
      # Track for flag + Telegram
      if [ -z "$NEW_SKILLS_CSV" ]; then
        NEW_SKILLS_CSV="$SKILL_NAME"
      else
        NEW_SKILLS_CSV="$NEW_SKILLS_CSV, $SKILL_NAME"
      fi
      echo ""
      echo "  🆕 NEW SKILL DETECTED: $SKILL_NAME"
      echo "  ============================================"
      echo "  This skill requires ACTIVATION after install."
      echo "  The agent MUST follow these steps:"
      echo ""
      echo "  a. READ all files (Teach Yourself Protocol)"
      echo "     → SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md"
      echo "     → Plus any references/*.md files"
      echo ""
      echo "  b. CHECK prerequisites, search .env files"
      echo "     → Verify API keys, credentials, software"
      echo "     → Check ~/.openclaw/skills/ for dependencies"
      echo ""
      echo "  c. EXECUTE setup (different from reading!)"
      echo "     → Follow INSTALL.md activation steps"
      echo "     → Copy scripts, create files, run commands"
      echo "     → 'Teach Yourself' means READ. 'Activate' means EXECUTE."
      echo ""
      echo "  d. APPLY CORE_UPDATES.md surgically"
      echo "     → Add to AGENTS.md, TOOLS.md, MEMORY.md"
      echo "     → Update HEARTBEAT.md if needed"
      echo ""
      echo "  e. RUN QC.md checks"
      echo "     → Verify all components work"
      echo "     → Test API connections"
      echo ""
      echo "  f. TELL client what was set up"
      echo "     → List activated features"
      echo "     → Note any pending items"
      echo ""
      echo "  ============================================"
    fi

    # Remove old version if exists
    rm -rf "$SKILLS_DIR/$SKILL_NAME"

    # Copy new version.
    # IMPORTANT: strip the trailing slash from SKILL_DIR before passing to cp.
    # The glob pattern [0-9]*/ always appends a trailing slash.
    # `cp -r "path/01-skill/" dest/` copies the CONTENTS of 01-skill/ flat
    # into dest/ (the dir itself is not created) -- this is the root cause of
    # the "132 loose files dumped into ~/.openclaw/skills/" flatten bug.
    # `cp -r "path/01-skill" dest/` (no trailing slash) copies the dir as a
    # named subdirectory, producing dest/01-skill/ as intended.
    cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"
    echo "    Updated: $SKILL_NAME"
    # FIX 1: state transition -- files are on disk = DOWNLOADED (NOT installed).
    command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "downloaded"
  done

  # ----------------------------------------------------------
  # v14.24.0: Refresh shared-utils/ on every update so PR-delivered helpers
  # (adaptive_weights.py, prebuilt-index manifest) reach update-only boxes.
  # Mirrors install.sh:2876-2882.
  # ----------------------------------------------------------
  _SHAREDUTILS_STATUS="ok"
  if [ -d "$EXTRACTED_DIR/shared-utils" ]; then
    mkdir -p "$SKILLS_DIR/shared-utils"
    cp -r "$EXTRACTED_DIR/shared-utils/." "$SKILLS_DIR/shared-utils/"
    chmod +x "$SKILLS_DIR/shared-utils/"*.sh "$SKILLS_DIR/shared-utils/"*.py 2>/dev/null || true
    # v20.0.11: VERIFY the refresh actually landed every source top-level entry.
    # shared-utils/ (incl. sop-embed-once/) is NOT covered by the A3 numbered-skill
    # content-gate (skill-content-hash.sh enumerates only [0-9]* dirs), so a silently
    # partial cp here previously left boxes missing entire helper trees while still
    # getting stamped (observed: a box missing the whole sop-embed-once/ dir). We assert
    # source ⊆ dest (missing source entries only — dest supersets are fine) and gate the
    # stamp on it via _STEP_GATE_FAILS below.
    _SU_MISSING=""
    for _su_src in "$EXTRACTED_DIR/shared-utils/"*; do
      [ -e "$_su_src" ] || continue
      _su_base="$(basename "$_su_src")"
      [ -e "$SKILLS_DIR/shared-utils/$_su_base" ] || _SU_MISSING="${_SU_MISSING} $_su_base"
    done
    if [ -n "$_SU_MISSING" ]; then
      _SHAREDUTILS_STATUS="fail"
      echo "  ✗ shared-utils refresh INCOMPLETE — source entries missing from box:${_SU_MISSING}"
    else
      echo "  ✓ shared-utils refreshed in $SKILLS_DIR/shared-utils"
    fi
  fi

  # v14.24.0: Deliver universal-sops/ SOP cluster (Skills 47/48 source tree).
  # Neither install nor update copied this before; Skills 47/48 wiring FAILed
  # with a FATAL looking for funnel/presentation/video/ad SOPs.
  if [ -d "$EXTRACTED_DIR/universal-sops" ]; then
    rm -rf "$SKILLS_DIR/universal-sops"
    cp -r "$EXTRACTED_DIR/universal-sops" "$SKILLS_DIR/"
    echo "  ✓ universal-sops refreshed in $SKILLS_DIR/universal-sops"
  fi

  # SK1-63 (fleet-installer wiring, update path): mirror the same runtime-dir
  # manifest placement install.sh's install_skill_47_movie_producer() does on
  # fresh installs. executive_producer.py's load_manifest() resolves the
  # manifest via a repo-root walk-up (finds universal-sops/ as a sibling of
  # 47-movie-producer/ under $SKILLS_DIR, refreshed just above) BEFORE it ever
  # reaches this runtime-dir copy, so this is defense-in-depth — not the only
  # path — but it is the one Skill 47's OWN install.sh documents as canonical
  # and the fleet installer must not depend solely on the walk-up continuing to
  # work. Only runs when Skill 47 is actually installed on this box (opt-in
  # skill — never install OpenMontage or touch the network here, pure local
  # file copy). Non-fatal: never fails the update over an optional video skill.
  if [ -d "$SKILLS_DIR/47-movie-producer" ]; then
    S47_MANIFEST_SRC="$SKILLS_DIR/universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json"
    S47_OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"
    S47_MANIFEST_DEST="$(dirname "$S47_OPENMONTAGE_DIR")/VIDEO-PIPELINE-MANIFEST.json"
    if [ -f "$S47_MANIFEST_SRC" ]; then
      mkdir -p "$(dirname "$S47_MANIFEST_DEST")" 2>/dev/null
      if cp "$S47_MANIFEST_SRC" "$S47_MANIFEST_DEST" 2>>"$LOG_FILE" && \
         python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$S47_MANIFEST_DEST" 2>>"$LOG_FILE"; then
        echo "  ✓ Skill 47: VIDEO-PIPELINE-MANIFEST.json refreshed at $S47_MANIFEST_DEST (fleet-installer path)"
      else
        echo "  ⚠ Skill 47: could not refresh VIDEO-PIPELINE-MANIFEST.json at $S47_MANIFEST_DEST (see $LOG_FILE) — load_manifest() falls back to the universal-sops sibling walk-up"
      fi
    fi
  fi

  # ----------------------------------------------------------
  # UNIFIED COMPLETENESS-GATE LATCHES (D3/D4/D5 convergence). Initialized here,
  # BEFORE Step U6b, so every latch is set -u safe no matter which branch below
  # runs. PASS values by default (0 / "ok" / 1) -- flipped to FAIL only on a
  # genuine completeness-critical miss. The single stamp gate inserted between
  # the A3 content-gate and the version-stamp write reads all of these; see
  # that block for the consolidated pass/fail contract. Universal convention:
  # PASS == fully completed OR a benign/legitimate skip (idempotent no-op,
  # already-current, pre-interview no-op, nothing-to-do, out-of-scope); FAIL
  # ONLY when a completeness-critical action genuinely did not happen.
  # ----------------------------------------------------------
  # CONTENT-integrity latches (each GATES the .onboarding-version stamp -- a fail
  # WITHHOLDS the stamp because the skills CONTENT is not verifiably current):
  _U6B_PERSONA_FAIL=0            # persona-index CONTENT wiring (sentinel != pinned release_tag, triad-divergent library, or helper did not run)
  _D2_REFRESH_STATUS="ok"       # in-scope role/SOP CONTENT refresh (refresh-stale-roles.py rc 3 -- new library content that SHOULD have re-applied to an EXISTING artifact did not)
  _SHAREDCORE_STATUS="ok"       # shared-core-file wiring step (link_shared_core_files)
  # WORKFORCE-provisioning latches (v20.0.10: DECOUPLED from the content stamp --
  # they describe "is the client's workforce fully built", NOT "is the skills
  # content current". A miss is surfaced as an advisory and driven to completion
  # by the POST-stamp qc-completeness run + the onboarding-resume cron; it NEVER
  # withholds the skills-version stamp):
  _D2_MIGRATE_STATUS="ok"       # workforce floor-fill / workforce QC (migrate-existing-workforce.sh: empty depts for an interview-incomplete client, or a dept below the 95% floor)
  _D5_ACTIVATION_PASS=1         # dept-agent activation (materialize-dept-agents.sh: agents.list[] below this box's computed department floor)
  _D5_NOTLIVE_DETAIL=""
  _D5_AGENT_COUNT=0
  _D5_DEPT_STATE="skipped"
  _STEP_GATE_FAILS=""
  _WORKFORCE_INCOMPLETE_NOTES=""  # workforce-provisioning advisories -- surfaced, NEVER stamp-gating

  # ----------------------------------------------------------
  # Step U6b: Provision prebuilt persona index + wire GHL funnel catalog
  # (v14.25.0) — mirrors install.sh Step 6b so update-only boxes receive
  # the section-tagged canonical persona DB and catalog path vars identically to a
  # fresh install.  Uses shared-utils/provision-persona-index.sh (copied
  # above by the shared-utils refresh block).
  #
  # F2.1: reconcile_persona_assets now UNION-merges persona-categories.json
  # (client-local personas preserved, not clobbered) and provision_persona_index
  # treats a client canonical+local-delta index as canonical (superset) instead
  # of re-downloading over it. A genuine re-download preserves origin:local rows;
  # any it cannot preserve are queued in .persona-local-reembed-queue, surfaced
  # to the operator below.
  #
  # COACHING_DB_DIR: OC_WORKSPACE is defined later (line 1677+) so we
  # resolve the coaching DB dir inline using the same platform detection
  # already set at the top of this script (OC_CONFIG).
  # ----------------------------------------------------------
  _U6B_MANIFEST="$SKILLS_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
  [ -f "$_U6B_MANIFEST" ] || _U6B_MANIFEST="$EXTRACTED_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"

  _U6B_COACHING_DB_DIR="$HOME/.openclaw/workspace/data/coaching-personas"
  [ -d "/data/.openclaw" ] && _U6B_COACHING_DB_DIR="/data/.openclaw/workspace/data/coaching-personas"

  _U6B_OC_JSON="$HOME/.openclaw/openclaw.json"
  [ -f "/data/.openclaw/openclaw.json" ] && _U6B_OC_JSON="/data/.openclaw/openclaw.json"
  _U6B_OC_SECRETS_ENV="$HOME/.openclaw/secrets/.env"
  [ -d "/data/.openclaw" ] && _U6B_OC_SECRETS_ENV="/data/.openclaw/secrets/.env"

  _U6B_HELPER="$SKILLS_DIR/shared-utils/provision-persona-index.sh"
  [ -f "$_U6B_HELPER" ] || _U6B_HELPER="$EXTRACTED_DIR/shared-utils/provision-persona-index.sh"

  # Workspace + Skill-22 source for the persona reconcile (v14.27.2).
  _U6B_WS="$HOME/.openclaw/workspace"
  [ -d "/data/.openclaw" ] && _U6B_WS="/data/.openclaw/workspace"
  _U6B_SK22="$SKILLS_DIR/22-book-to-persona-coaching-leadership-system"

  if [ -f "$_U6B_MANIFEST" ] && [ -f "$_U6B_HELPER" ]; then
    # shellcheck source=/dev/null
    source "$_U6B_HELPER"
    # PRE-ROLL PERSONA-SET TRIAD (fail-closed backstop). Before shipping the
    # pulled persona library to this box, the N38 count triad — blueprint dirs ==
    # persona-categories.json keys == INDEX-MANIFEST persona_count == canonical —
    # MUST agree. CI enforces this at the PR boundary; this is the roll-side
    # backstop so a roll off a non-main / dirty / mid-catch-up checkout REFUSES to
    # provision a stale/divergent persona set instead of silently shipping the OLD
    # count. On divergence we SKIP persona provisioning (keep the box's current
    # set) and surface a loud operator warning, rather than shipping a broken set.
    _U6B_TRIAD_GUARD="$_U6B_SK22/pipeline/assert-personas-published.sh"
    _U6B_TRIAD_OK=1
    if [ -f "$_U6B_TRIAD_GUARD" ]; then
      if ! bash "$_U6B_TRIAD_GUARD" --repo "$SKILLS_DIR" --repo-only >/dev/null 2>&1; then
        _U6B_TRIAD_OK=0
      fi
    fi
    # ASSET-FRESHNESS PRE-ROLL (FDN-7 / F1.3 gate 2). A manifest carrying
    # asset_rebuild_required:true was count-synced by a --no-asset staging bump:
    # the four SET counts agree (so the triad guard above passes) but the
    # published gemini-index.sqlite.gz still lacks vectors for the newest
    # persona(s). Provisioning from it would ship a counted-but-vector-less
    # library (Layer-5 degrades to keyword for those personas). REFUSE and KEEP
    # the box's current index until a real build-and-publish.sh clears the flag.
    # Coordinates with the FDN-6 triad pre-roll above — BOTH must pass to
    # provision. Fail-open on a read error (never block a roll on a parse hiccup).
    _U6B_ASSET_OK=1
    if command -v python3 >/dev/null 2>&1; then
      _U6B_ASSET_REBUILD="$(python3 -c 'import json,sys
try:
    print("true" if json.load(open(sys.argv[1])).get("asset_rebuild_required") is True else "false")
except Exception:
    print("false")' "$_U6B_MANIFEST" 2>/dev/null || echo false)"
      [ "$_U6B_ASSET_REBUILD" = "true" ] && _U6B_ASSET_OK=0
    fi
    if [ "$_U6B_TRIAD_OK" != "1" ]; then
      _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-set triad DIVERGENT in the pulled repo (blueprint dirs / categories keys / INDEX-MANIFEST persona_count disagree) — persona provisioning SKIPPED (refused to ship a stale library). Run 22-…/pipeline/publish-personas-to-fleet.sh, merge, and re-roll."
      _U6B_PERSONA_FAIL=1  # D3: triad-divergent skip is completeness-critical, not benign
      echo "  ✗ PRE-ROLL persona-set triad DIVERGENT — REFUSING to provision a stale/divergent persona library on this box."
      echo "     Fix the repo with 22-book-to-persona-coaching-leadership-system/pipeline/publish-personas-to-fleet.sh and re-roll."
    elif [ "$_U6B_ASSET_OK" != "1" ]; then
      _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }INDEX-MANIFEST asset_rebuild_required:true (a --no-asset staging manifest — the published asset lacks vectors for the newest persona(s)) — persona index provisioning SKIPPED (kept the box's current index). Rebuild+publish the asset via shared-utils/prebuilt-index/build-and-publish.sh, merge, and re-roll."
      _U6B_PERSONA_FAIL=1  # D3: asset-rebuild-required skip is completeness-critical, not benign
      echo "  ✗ PRE-ROLL asset_rebuild_required:true — REFUSING to (re)provision from a staged --no-asset manifest (would ship a counted-but-vector-less library). Keeping the box's current persona index."
      echo "     Rebuild+publish the real asset with shared-utils/prebuilt-index/build-and-publish.sh and re-roll."
    else
      # Reconcile categories + blueprints to the workspace FIRST so the index
      # gate sees the persona dirs (furnace-safe), then provision the index.
      reconcile_persona_assets "$_U6B_SK22" "$_U6B_COACHING_DB_DIR" "$_U6B_WS"
      provision_persona_index "$_U6B_MANIFEST" "$_U6B_COACHING_DB_DIR"

      # ----------------------------------------------------------
      # D3 (C4): COMPLETION RE-ASSERTION. reconcile_persona_assets /
      # provision_persona_index both always `return 0` (so a bare caller under
      # set -euo pipefail never aborts mid-provision) -- truth is carried
      # out-of-band via the exported _RECONCILE_OK (0/1) plus the on-disk
      # .prebuilt-index-version sentinel. Re-check BOTH here so a reconcile
      # failure or a sentinel that never reached the manifest's release_tag
      # flips the completeness-gate latch instead of silently passing.
      # ----------------------------------------------------------
      _U6B_RELEASE_TAG="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("release_tag",""))
except Exception:
    print("")' "$_U6B_MANIFEST" 2>/dev/null || true)"
      _U6B_SENTINEL_VAL="$(cat "$_U6B_COACHING_DB_DIR/.prebuilt-index-version" 2>/dev/null | tr -d '[:space:]' || true)"
      if [ "${_RECONCILE_OK:-1}" = "0" ] || [ -z "$_U6B_RELEASE_TAG" ] || [ "$_U6B_SENTINEL_VAL" != "$_U6B_RELEASE_TAG" ]; then
        _U6B_PERSONA_FAIL=1
        _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-index completion re-assertion FAILED (reconcile_ok=${_RECONCILE_OK:-unset}, sentinel=${_U6B_SENTINEL_VAL:-<missing>}, manifest release_tag=${_U6B_RELEASE_TAG:-<unknown>}) — persona provisioning incomplete on this box"
        echo "  ✗ [D3] U6b completion re-assertion FAILED — sentinel(${_U6B_SENTINEL_VAL:-<missing>}) != release_tag(${_U6B_RELEASE_TAG:-<unknown>}) or reconcile not ok(${_RECONCILE_OK:-unset})"
      else
        echo "  ✓ [D3] U6b completion re-assertion PASSED (sentinel == manifest release_tag, reconcile ok)"
      fi

      # F2.1: if a re-download could not preserve some client-local persona
      # rows, provision_persona_index leaves a .persona-local-reembed-queue
      # marker. Surface it in the operator completion report (never client-
      # visible) so the operator re-embeds those personas with the CLIENT's own
      # key — their blueprints remain on disk, so this is a delta re-embed.
      _U6B_REEMBED_QUEUE="$_U6B_COACHING_DB_DIR/.persona-local-reembed-queue"
      if [ -s "$_U6B_REEMBED_QUEUE" ]; then
        _U6B_QN="$(grep -c . "$_U6B_REEMBED_QUEUE" 2>/dev/null || echo '?')"
        _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }${_U6B_QN} client-local persona(s) need a delta re-embed with the client's own key (see $_U6B_REEMBED_QUEUE) — index re-download could not carry their vectors over"
        echo "  ⚠️  ${_U6B_QN} client-local persona(s) queued for delta re-embed (client's OWN key) — $_U6B_REEMBED_QUEUE"
      fi
      # FIX 1 (BREAK 1): pipeline OWNS the qmd persona store — repoint/re-index it
      # at the canonical personas dir (BM25 only, furnace-safe) so the agent can
      # never read a frozen "March" cache. Runs AFTER reconcile + provision so the
      # canonical dir holds the current blueprints.
      reconcile_qmd_persona_index "$_U6B_COACHING_DB_DIR"
      # FIX 4 (cascade): if reconcile_persona_assets detected the SET grew
      # (_SET_CHANGED=1), re-wire matching + Command Center + the dept persona
      # reflex (governing-personas.md refresh + stickiness bust). Static/idempotent.
      if [ "${_SET_CHANGED:-0}" = "1" ]; then
        echo "  → persona SET changed — re-wiring governing-personas.md + busting stickiness"
        rewire_on_persona_set_change "$SKILLS_DIR" "$_U6B_WS"
      fi
      wire_ghl_funnel_catalog "$SKILLS_DIR" "$_U6B_OC_SECRETS_ENV" "$_U6B_OC_JSON"
    fi
  else
    # P11-1: this is the "helper/bundle missing" skip at the CALLER level (the
    # file itself is absent, so provision-persona-index.sh's own
    # _pidx_skip_warn accumulator was never sourced). Feed the same
    # _PIDX_SKIP_WARNINGS accumulator directly so this box's completion report
    # (built below from ONBOARDING_GATE_SUMMARY/QC_STATUS_LINE) surfaces it
    # too, instead of a plain log line an operator would never see.
    _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }persona-index manifest or provision helper not found — Step U6b did not run"
    _U6B_PERSONA_FAIL=1  # D3: manifest/helper missing means U6b genuinely did not run -- completeness-critical, not benign
    echo "  ⚠️  Persona-index provisioning SKIPPED: manifest or provision helper not found — Step U6b did not run"
  fi

  # ----------------------------------------------------------
  # v10.15.47: WIRING PHASE -- per-skill executed steps (not prose).
  # For every installed skill folder, this phase:
  #   1. Runs the skill's own installer (wire.sh > install.sh > setup-*.sh) if present, idempotent.
  #   2. Idempotently merges CORE_UPDATES.md into workspace AGENTS/TOOLS/MEMORY/SOUL files.
  #   3. Installs OS prereqs (imagemagick/ffmpeg) via brew (Mac) idempotently.
  #   4. Wires skill 36's GHL MCP under nested mcp.servers via `openclaw mcp set`.
  #
  # State guard: each skill writes a sentinel file $SKILLS_DIR/<skill>/.wired-<version>
  # so the loop is safe to re-run -- it skips already-wired skills.
  #
  # Scope: additive only. Never edits IDENTITY.md, never rebuilds workforce,
  # never clobbers existing AGENTS.md sections -- only appends new ones.
  # ----------------------------------------------------------

  # Resolve workspace directory (2026.x-aware; mirrors write_update_pending_flag).
  # v14.3.15 2026.x agent-dir fix: the old heuristic checked $HOME/clawd first — on VPS
  # boxes that still carry a legacy /data/clawd/ (or symlink at $HOME/clawd) the
  # sentinels and core-update blocks were written to that dead path while the
  # running agent read from the 2026.x agent dir, not the legacy workspace. The gate
  # then reported core-sentinel-missing even when the wiring ran cleanly.
  # FIX: use obs_resolve_workspace (which honours openclaw.json agents[].workspace)
  # as the primary resolver; fall back to the legacy heuristic only when the CLI
  # helper is absent.  Then ALSO detect the active 2026.x agent dir and dual-write
  # sentinels there so both the legacy-workspace path AND the agent-dir path are
  # covered — whichever path the running agent reads from will see the sentinel.
  WIRE_WORKSPACE_DIR=""
  if command -v obs_resolve_workspace >/dev/null 2>&1; then
    WIRE_WORKSPACE_DIR="$(obs_resolve_workspace 2>/dev/null || true)"
  fi
  if [ -z "$WIRE_WORKSPACE_DIR" ]; then
    WIRE_WORKSPACE_DIR="$HOME/clawd"
    [ ! -d "$WIRE_WORKSPACE_DIR" ] && WIRE_WORKSPACE_DIR="$HOME/.openclaw/workspace"
  fi
  mkdir -p "$WIRE_WORKSPACE_DIR"

  # Detect the active 2026.x agent dir for dual-write.
  # On VPS the agent reads from /data/.openclaw/agents/<name>/AGENTS.md;
  # on Mac from $HOME/.openclaw/agents/<name>/AGENTS.md.  Prefer /data prefix.
  _OC_AGENTS_ROOT="$HOME/.openclaw/agents"
  [ -d "/data/.openclaw/agents" ] && _OC_AGENTS_ROOT="/data/.openclaw/agents"
  WIRE_AGENT_DIR=""
  if [ -d "$_OC_AGENTS_ROOT/main" ]; then
    WIRE_AGENT_DIR="$_OC_AGENTS_ROOT/main"
  else
    for _oa in "$_OC_AGENTS_ROOT"/*/; do
      [ -d "${_oa%/}" ] && { WIRE_AGENT_DIR="${_oa%/}"; break; }
    done
    unset _oa
  fi
  unset _OC_AGENTS_ROOT

  # Brew path (Mac only; VPS branch kept out, VPS uses update-skills-vps.sh)
  BREW_CMD="$(command -v brew 2>/dev/null || echo '')"

  # ---- Helper: idempotent CORE_UPDATES.md merger (v12.3.11 format-robust) ----
  # Recognises ALL 14 header conventions found in the repo (em-dash, bracket h2/h3,
  # bold-bracket, plain h3, Add-to, (append), Addition, Update, bare filename h2).
  # Adds IDENTITY and USER to target_map. Wraps appended blocks in BEGIN/END markers
  # for future in-place updates. Stamps sentinel even when 0 mergeable sections found.
  # Emits UNRECOGNIZED HEADER warnings; exits non-zero under CORE_UPDATES_STRICT=1.
  wire_core_updates() {
    local SKILL_FOLDER="$1"   # e.g. "36-ghl-mcp-setup"
    local CU_FILE="$SKILLS_DIR/$SKILL_FOLDER/CORE_UPDATES.md"
    [ -f "$CU_FILE" ] || return 0

    # Map section headers to workspace target files
    local AGENTS_FILE="$WIRE_WORKSPACE_DIR/AGENTS.md"
    local TOOLS_FILE="$WIRE_WORKSPACE_DIR/TOOLS.md"
    local MEMORY_FILE="$WIRE_WORKSPACE_DIR/MEMORY.md"
    local SOUL_FILE="$WIRE_WORKSPACE_DIR/SOUL.md"
    local IDENTITY_FILE="$WIRE_WORKSPACE_DIR/IDENTITY.md"
    local USER_FILE="$WIRE_WORKSPACE_DIR/USER.md"
    touch "$AGENTS_FILE" "$TOOLS_FILE" "$MEMORY_FILE" "$SOUL_FILE" \
          "$IDENTITY_FILE" "$USER_FILE" 2>/dev/null || true

    # Sentinel: skip if this skill's core updates are already merged.
    # v14.3.15: also check the 2026.x agent dir AGENTS.md so a box that was
    # previously wired via the agent-dir path is not re-wired into the workspace.
    local SENTINEL="<!-- skill:${SKILL_FOLDER}:core-update-applied -->"
    if grep -qF "$SENTINEL" "$AGENTS_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$TOOLS_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$MEMORY_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$SOUL_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$IDENTITY_FILE" 2>/dev/null || \
       grep -qF "$SENTINEL" "$USER_FILE" 2>/dev/null || \
       ([ -n "$WIRE_AGENT_DIR" ] && grep -qF "$SENTINEL" "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null); then
      return 0
    fi

    # Parse CORE_UPDATES.md with the format-robust normalising parser.
    # Recognises ALL header conventions across all 14 formats in the repo:
    #   FORMAT 1/3: ## X.md - UPDATE REQUIRED  (ASCII / en-dash h2)
    #   FORMAT 2:   ## X.md — UPDATE REQUIRED  (em-dash h2)
    #   FORMAT 4:   ## [ADD TO X.md]           (bracket h2, optional trailing note)
    #   FORMAT 5:   ### [ADD TO X.md]          (bracket h3)
    #   FORMAT 6:   **[ADD TO X.md]**          (bold-bracket inline)
    #   FORMAT 7:   ### X.md                   (plain h3, under Suggested snippets)
    #   FORMAT 8/9: ## Add to X.md             (verb-first h2)
    #   FORMAT 10:  ## X.md (append)           (paren suffix h2)
    #   FORMAT 11:  ## X.md append             (bare suffix word h2)
    #   FORMAT 12:  ## X.md Addition/Update    (mixed suffix h2)
    #   FORMAT 13:  ## X.md                    (bare filename h2, where:+fenced)
    # python3 is a hard dependency on Mac (already noted in the existing comment).
    python3 - \
        "$CU_FILE" "$AGENTS_FILE" "$TOOLS_FILE" "$MEMORY_FILE" \
        "$SOUL_FILE" "$IDENTITY_FILE" "$USER_FILE" \
        "$SENTINEL" "$SKILL_FOLDER" \
        "${CORE_UPDATES_STRICT:-0}" <<'PYEOF'
import sys, re, os

(cu_path, agents_f, tools_f, memory_f, soul_f,
 identity_f, user_f, sentinel, skill_folder, strict_mode) = sys.argv[1:]
strict = (strict_mode == "1")

target_map = {
    'agents':   agents_f,
    'tools':    tools_f,
    'memory':   memory_f,
    'soul':     soul_f,
    'identity': identity_f,
    'user':     user_f,
}

try:
    text = open(cu_path, encoding='utf-8', errors='replace').read()
except Exception:
    sys.exit(0)

# ---------------------------------------------------------------------------
# HEADER RECOGNITION
# A "core section header" is a line that:
#   (a) starts with ## or ### (h2/h3), OR is a **[ADD TO X.md]** bold-bracket,
#   (b) AND contains exactly one of the six target filenames.
#
# The regex captures:
#   group(hashes)  — ## or ### (or None for bold-bracket)
#   group(target)  — AGENTS|TOOLS|MEMORY|SOUL|IDENTITY|USER (case-insensitive)
#   group(rest)    — remainder of the line after ".md" (for directive parsing)
#
# We build a single pattern that handles all known formats.
# The "no update" / "no change" signals come from the full line text (rest).
# ---------------------------------------------------------------------------

TARGETS = r'(AGENTS|TOOLS|MEMORY|SOUL|IDENTITY|USER)'

# Structural headers that must NOT be treated as target sections even though
# they contain one of the target names (e.g. "## Relevant (update allowed)")
STRUCTURAL_PREFIXES = (
    'rule', 'relevant', 'optional', 'non-relevant', 'what not',
    'where to', 'purpose', 'quick reference', 'core .md', 'what to add',
    'suggested snippets', 'verification', 'placement decision',
    'credential storage', 'add this', 'paste these', 'check if running',
)

def is_structural(line_text):
    """Return True if the heading looks like a structural/meta header."""
    # Strip leading #, *, [, whitespace
    stripped = re.sub(r'^[#*\[\s]+', '', line_text).strip().lower()
    return any(stripped.startswith(p) for p in STRUCTURAL_PREFIXES)

def classify_directive(rest_text):
    """
    Given the text AFTER '<TARGET>.md' on a header line, decide:
      'skip'   — this section is a no-op (no-update / no-change / do-not-edit)
      'merge'  — real content section
    """
    t = rest_text.lower()
    # Explicit skip signals
    skip_signals = ('no update', 'no change', 'do not edit', 'not relevant',
                    'no update needed', 'no update required')
    for sig in skip_signals:
        if sig in t:
            return 'skip'
    return 'merge'

# Build the master header recognition regex.
# It matches lines in these forms:
#   1. ^(#{2,3})\s+  ... TARGET\.md ...   (h2/h3 with target anywhere on line)
#   2. ^\*\*\[ADD TO TARGET\.md\]\*\*     (bold-bracket)
#
# We use MULTILINE so ^ matches start-of-line.
# We capture the target name and the full line text so we can classify it.

HEADER_PATTERN = re.compile(
    r'^(?:'
    # h2/h3: optional leading [, optional ADD/APPEND TO, target, optional rest
    r'(#{2,3})\s+(?:\[?(?:ADD\s+TO|APPEND\s+TO|ADD|APPEND|UPDATE)?\s*)?'
    + TARGETS + r'\.md(.*?)'
    r'|'
    # bold-bracket: **[ADD TO TARGET.md]** (optional trailing text)
    r'\*\*\[(?:ADD\s+TO|APPEND\s+TO)?\s*' + TARGETS + r'\.md\]?\*\*(.*?)'
    r')$',
    re.IGNORECASE | re.MULTILINE
)

def extract_target_and_directive(m):
    """
    From a regex match, return (target_key, directive) where
      target_key  — lowercase 'agents'|'tools'|'memory'|'soul'|'identity'|'user'
      directive   — 'merge' or 'skip'
    """
    # Group layout: (hashes, target_h2, rest_h2, target_bold, rest_bold)
    # group(1)=hashes, group(2)=target for h2/h3, group(3)=rest for h2/h3
    # group(4)=target for bold, group(5)=rest for bold
    target = (m.group(2) or m.group(4) or '').lower()
    rest   = (m.group(3) or m.group(5) or '')
    directive = classify_directive(rest)
    return target, directive

# ---------------------------------------------------------------------------
# STRUCTURAL HEADER DETECTION (for section boundary purposes)
# Any h2 that does NOT match a target name stops the current section.
# ---------------------------------------------------------------------------
ANY_H2_RE = re.compile(r'^#{1,3}\s+\S', re.MULTILINE)

# ---------------------------------------------------------------------------
# SCAN: collect all section matches with their positions
# ---------------------------------------------------------------------------
all_matches = list(HEADER_PATTERN.finditer(text))

# Filter out structural headers
real_sections = []
for m in all_matches:
    full_line = m.group(0)
    if is_structural(full_line):
        continue
    target, directive = extract_target_and_directive(m)
    if not target or target not in target_map:
        continue
    real_sections.append((m, target, directive))

# ---------------------------------------------------------------------------
# UNRECOGNIZED HEADER detection
# Any line that contains "TARGET.md" in a heading/bold context but was NOT
# captured by our regex is potentially an unrecognized format.
# ---------------------------------------------------------------------------
LOOSE_RE = re.compile(
    r'^(?:#{2,3}|\*\*\[)[^\n]*' + TARGETS + r'\.md[^\n]*$',
    re.IGNORECASE | re.MULTILINE
)
all_loose = set(m.group(0).strip() for m in LOOSE_RE.finditer(text))
recognized_lines = set(m[0].group(0).strip() for m in real_sections)
# Also count structural headers as recognized (they are intentionally not merged)
structural_lines = set()
for m in all_matches:
    if is_structural(m.group(0)):
        structural_lines.add(m.group(0).strip())

unrecognized = []
for line in all_loose:
    if line not in recognized_lines and line not in structural_lines:
        unrecognized.append(line)

if unrecognized:
    for u in unrecognized:
        print(f'[CORE_UPDATES] UNRECOGNIZED HEADER in {skill_folder}: {u}', file=sys.stderr)
    if strict:
        sys.exit(1)

# ---------------------------------------------------------------------------
# MERGE PHASE
# For each real non-skip section, extract content up to the next section header
# (of any kind) and append it wrapped in BEGIN/END markers.
# ---------------------------------------------------------------------------

# Fenced-code spans: headings INSIDE a ``` ... ``` fence are payload text, not
# section boundaries. CORE_UPDATES.md puts the real "exact text to add" inside a
# fenced block whose FIRST line is often itself an h2 (e.g. the skill-22 AGENTS.md
# payload starts with "## Book-to-Persona Skill (Installed)"). Without this guard
# the boundary scan cut the section at that in-fence heading, so the actual
# payload (the Persona Reflex / Task-Mode body) never merged while the sentinel
# was still stamped — a marker with no body. Excluding in-fence heading positions
# lets the WHOLE fenced payload transfer.
def _fenced_spans(s):
    spans = []
    start = None
    for fm in re.finditer(r'^[ \t]*```', s, re.MULTILINE):
        if start is None:
            start = fm.start()
        else:
            spans.append((start, fm.end()))
            start = None
    return spans

_FENCES = _fenced_spans(text)

def _in_fence(pos):
    return any(a <= pos < b for (a, b) in _FENCES)

# Build a flat list of all heading positions (for section boundary detection),
# skipping any heading that lives inside a fenced code block (payload, not boundary).
all_heading_positions = sorted(
    [m.start() for m in ANY_H2_RE.finditer(text) if not _in_fence(m.start())] +
    [m.start() for m in re.finditer(r'^\*\*\[', text, re.MULTILINE) if not _in_fence(m.start())]
)

def next_section_start(pos):
    """Return start of next heading at or after pos, or len(text)."""
    for hp in all_heading_positions:
        if hp > pos:
            return hp
    return len(text)

merged_count = 0

for (m, target, directive) in real_sections:
    if directive == 'skip':
        continue
    target_file = target_map[target]

    # Extract block: from end of matched header line to next heading
    content_start = m.end()
    content_end = next_section_start(m.start() + 1)
    block = text[content_start:content_end].strip()

    if not block:
        continue

    # Check for BEGIN/END idempotency marker in target file
    begin_marker = f'<!-- BEGIN skill:{skill_folder}:{target} -->'
    end_marker   = f'<!-- END skill:{skill_folder}:{target} -->'

    try:
        existing = open(target_file, encoding='utf-8', errors='replace').read()
    except Exception:
        existing = ''

    if begin_marker in existing:
        # Already merged for this target — skip
        continue

    # Append wrapped block
    with open(target_file, 'a', encoding='utf-8') as fh:
        fh.write(f'\n\n{begin_marker}\n')
        fh.write(block)
        fh.write(f'\n{end_marker}\n')

    merged_count += 1

# ---------------------------------------------------------------------------
# WARN on zero-section skills (possible format regression, but not an error)
# ---------------------------------------------------------------------------
mergeable_sections = [(m, t, d) for (m, t, d) in real_sections if d != 'skip']
if not mergeable_sections:
    print(f'[CORE_UPDATES] WARN: {skill_folder} produced no mergeable section', file=sys.stderr)

# ---------------------------------------------------------------------------
# SENTINEL: always stamp to AGENTS.md so install.sh VERIFICATION GATE passes.
# This is unconditional — even for genuine no-op skills (all-skip sections).
# ---------------------------------------------------------------------------
try:
    existing = open(agents_f, encoding='utf-8', errors='replace').read()
except Exception:
    existing = ''
if sentinel not in existing:
    with open(agents_f, 'a', encoding='utf-8') as fh:
        fh.write('\n' + sentinel + '\n')

PYEOF
    # v14.3.15 dual-write: stamp sentinel to the 2026.x agent dir AGENTS.md too.
    # On VPS boxes that have a legacy $HOME/clawd/ (or /data/clawd/), the Python
    # block above writes to WIRE_WORKSPACE_DIR/AGENTS.md.  If the running agent
    # reads from $HOME/.openclaw/agents/<name>/AGENTS.md instead, the gate sees
    # core-sentinel-missing.  Writing to BOTH paths is safe (idempotent grep check
    # guards against duplicates) and ensures the sentinel is visible regardless of
    # which read-path the agent uses.
    if [ -n "$WIRE_AGENT_DIR" ] && \
       [ "$WIRE_AGENT_DIR/AGENTS.md" != "$AGENTS_FILE" ]; then
      touch "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null || true
      if ! grep -qF "$SENTINEL" "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null; then
        printf '\n%s\n' "$SENTINEL" >> "$WIRE_AGENT_DIR/AGENTS.md" 2>/dev/null || true
      fi
    fi
    echo "    Wired CORE_UPDATES.md: $SKILL_FOLDER"
  }

  # ---- Helper: install OS prereqs for a skill (idempotent) ----
  wire_prereqs() {
    local SKILL_FOLDER="$1"
    # Skills 25/26/27/28 need ffmpeg + imagemagick; 16 needs nothing extra.
    # We detect by folder prefix; adding explicit cases is safer than parsing INSTALL.md.
    local NEED_FFMPEG=0
    local NEED_IMAGEMAGICK=0
    case "$SKILL_FOLDER" in
      25-video-creator|26-caption-creator|27-video-editor|28-cinematic-forge)
        NEED_FFMPEG=1; NEED_IMAGEMAGICK=1 ;;
    esac

    [ "$NEED_FFMPEG" -eq 0 ] && [ "$NEED_IMAGEMAGICK" -eq 0 ] && return 0
    [ -z "$BREW_CMD" ] && { echo "    (brew not found -- skipping prereqs for $SKILL_FOLDER)"; return 0; }

    if [ "$NEED_FFMPEG" -eq 1 ]; then
      if command -v ffmpeg >/dev/null 2>&1; then
        echo "    ffmpeg: already installed"
      else
        echo "    Installing ffmpeg via brew..."
        "$BREW_CMD" install ffmpeg >> "$LOG_FILE" 2>&1 && echo "    ffmpeg: installed" || echo "    ffmpeg: install failed (see $LOG_FILE)"
      fi
    fi

    if [ "$NEED_IMAGEMAGICK" -eq 1 ]; then
      if command -v convert >/dev/null 2>&1 || command -v magick >/dev/null 2>&1; then
        echo "    imagemagick: already installed"
      else
        echo "    Installing imagemagick via brew..."
        "$BREW_CMD" install imagemagick >> "$LOG_FILE" 2>&1 && echo "    imagemagick: installed" || echo "    imagemagick: install failed (see $LOG_FILE)"
      fi
    fi
  }

  # ---- Helper: wire skill 36 GHL MCP under nested mcp.servers (idempotent) ----
  wire_ghl_mcp() {
    local SKILL_FOLDER="$1"
    [ "$SKILL_FOLDER" = "36-ghl-mcp-setup" ] || return 0

    if ! command -v openclaw >/dev/null 2>&1; then
      echo "    (openclaw CLI not found -- skipping GHL MCP registration)"
      return 0
    fi

    # Check if ghl-mcp is already registered under nested mcp.servers
    local OCJSON="$HOME/.openclaw/openclaw.json"
    if [ -f "$OCJSON" ] && python3 -c "
import json, sys
try:
    cfg = json.load(open('$OCJSON'))
    servers = cfg.get('mcp', {}).get('servers', {})
    if 'ghl-mcp' in servers or 'ghl-community-mcp' in servers:
        sys.exit(0)
    sys.exit(1)
except:
    sys.exit(1)
" 2>/dev/null; then
      echo "    GHL MCP: already registered under mcp.servers"
      return 0
    fi

    # Read GHL MCP URL from skill's INSTALL.md or default to the community server
    # The canonical CLI path per audit finding (d): openclaw mcp set
    local GHL_MCP_PORT=8765
    local GHL_MCP_INSTALL_MD="$SKILLS_DIR/36-ghl-mcp-setup/INSTALL.md"
    if [ -f "$GHL_MCP_INSTALL_MD" ]; then
      local DETECTED_PORT
      DETECTED_PORT=$(grep -oE 'localhost:[0-9]+' "$GHL_MCP_INSTALL_MD" 2>/dev/null | head -1 | cut -d: -f2 || true)
      [ -n "$DETECTED_PORT" ] && GHL_MCP_PORT="$DETECTED_PORT"
    fi

    echo "    Registering GHL community MCP under mcp.servers (port $GHL_MCP_PORT)..."
    if openclaw mcp set ghl-community-mcp "{\"type\":\"streamable-http\",\"url\":\"http://localhost:${GHL_MCP_PORT}/mcp\"}" >> "$LOG_FILE" 2>&1; then
      echo "    GHL MCP: registered under mcp.servers (ghl-community-mcp → localhost:${GHL_MCP_PORT})"
    else
      echo "    GHL MCP: registration attempt completed (see $LOG_FILE for details)"
    fi

    # FIX 3 (v10.15.48): registration alone NEVER starts the local server, so
    # the GHL tools don't resolve. Run the EXECUTED autostart (launchd KeepAlive
    # on :8765 + healthcheck + auto-restart). Idempotent -- no-op if already
    # healthy + registered; honest SKIP line if GHL creds are absent.
    # BUG FIX (v10.15.49): run NON-BLOCKING so the wiring loop + .onboarding-version
    # stamp always complete. macOS has no `timeout`, so backgrounding is the safe
    # cross-platform fix. The MCP still starts; the updater no longer waits on it.
    local AUTOSTART="$ONBOARDING_DIR/scripts/ghl-mcp-autostart.sh"
    if [ -x "$AUTOSTART" ]; then
      echo "    Starting GHL MCP server in background (launchd :${GHL_MCP_PORT}) -- log: /tmp/ghl-mcp-autostart.log"
      ( GHL_MCP_PORT="$GHL_MCP_PORT" bash "$AUTOSTART" >/tmp/ghl-mcp-autostart.log 2>&1 & )
    else
      echo "    (ghl-mcp-autostart.sh not found at $AUTOSTART -- server NOT started; GHL tools will not resolve until it is run)"
    fi
  }

  # ---- Main wiring loop ----
  echo ""
  echo "  Wiring installed skills (CORE_UPDATES, prereqs, MCP registration)..."
  WIRED_COUNT=0
  SKIPPED_WIRED_COUNT=0

  for SKILL_DIR in "$SKILLS_DIR"/[0-9]*/; do
    [ -d "$SKILL_DIR" ] || continue
    SKILL_NAME=$(basename "$SKILL_DIR")
    case "$SKILL_NAME" in *ARCHIVED*) continue ;; esac

    # Per-box model-map RE-RESOLVE -- NOT sentinel-gated (runs BEFORE the wired-sentinel
    # short-circuit below). The anthology-engine's tier map (skill-dir model-map.json,
    # preflight.sh's default output) is resolved from the CLIENT's OWN configured models;
    # if a client changes their models
    # between update passes, the .wired-<version> sentinel would otherwise skip install.sh
    # and leave a STALE map -- which then fails closed deep at S9 (UnresolvedMapError) or
    # trips judge-independence. Re-resolve every pass (idempotent; fail is non-fatal here,
    # the engine's own GATE 1b RESOLVE-then-check is the fail-closed gate at run time).
    if [ -f "$SKILL_DIR/preflight.sh" ] && [ -f "$SKILL_DIR/config/model-map.template.json" ]; then
      echo "    Re-resolving model-map (preflight.sh) for $SKILL_NAME (not sentinel-gated)..."
      if bash "$SKILL_DIR/preflight.sh" >> "$LOG_FILE" 2>&1; then
        echo "    Model-map re-resolved: $SKILL_NAME"
      else
        echo "    Model-map re-resolve FAILED CLOSED for $SKILL_NAME (client has no resolvable/independent model; see $LOG_FILE) -- engine GATE 1b will refuse at run time until fixed"
      fi
    fi

    # Per-skill idempotency sentinel
    WIRED_SENTINEL="$SKILL_DIR/.wired-${ONBOARDING_VERSION}"
    if [ -f "$WIRED_SENTINEL" ]; then
      SKIPPED_WIRED_COUNT=$((SKIPPED_WIRED_COUNT + 1))
      continue
    fi

    # Step 1: Run the skill's own executable installer if present
    # Priority: wire.sh > install.sh > setup-*.sh (first match)
    SKILL_INSTALLER=""
    for _candidate in "$SKILL_DIR/wire.sh" "$SKILL_DIR/install.sh" "$SKILL_DIR/scripts/install.sh"; do
      if [ -x "$_candidate" ]; then
        SKILL_INSTALLER="$_candidate"
        break
      fi
    done
    # Also check for setup-*.sh pattern
    if [ -z "$SKILL_INSTALLER" ]; then
      for _candidate in "$SKILL_DIR"/setup-*.sh "$SKILL_DIR"/scripts/setup-*.sh; do
        if [ -x "$_candidate" ]; then
          SKILL_INSTALLER="$_candidate"
          break
        fi
      done
    fi

    if [ -n "$SKILL_INSTALLER" ]; then
      echo "    Running installer: $(basename "$SKILL_INSTALLER") for $SKILL_NAME..."
      if bash "$SKILL_INSTALLER" --idempotent >> "$LOG_FILE" 2>&1; then
        echo "    Installer OK: $SKILL_NAME"
      else
        echo "    Installer reported warnings for $SKILL_NAME (see $LOG_FILE) -- continuing"
      fi
    fi

    # Step 2: Idempotently merge CORE_UPDATES.md into workspace files
    wire_core_updates "$SKILL_NAME"

    # Step 3: Install OS prereqs (ffmpeg/imagemagick for video skills)
    wire_prereqs "$SKILL_NAME"

    # Step 4: Wire GHL MCP (skill 36 only)
    wire_ghl_mcp "$SKILL_NAME"

    # Step 5 (v12.0.0): Per-skill prerequisite check -- NOT sentinel-gated.
    # Runs on every wiring pass so a prereq satisfied between runs clears on
    # the next update. Exit 2 = installed-with-missing-prereqs (note + continue).
    # Exit 3 = malformed PREREQS.json (warn + continue). Read-only; self-records.
    PREREQ_CHECKER_UPDATE="$SKILLS_DIR/shared-utils/check-skill-prereqs.sh"
    if [[ -x "$PREREQ_CHECKER_UPDATE" && -f "$SKILL_DIR/PREREQS.json" ]]; then
      PREREQ_RC_UPDATE=0
      bash "$PREREQ_CHECKER_UPDATE" "$SKILL_DIR" || PREREQ_RC_UPDATE=$?
      if [[ $PREREQ_RC_UPDATE -eq 2 ]]; then
        echo "    [prereq] $SKILL_NAME: installed with missing prerequisites"
      elif [[ $PREREQ_RC_UPDATE -eq 3 ]]; then
        echo "    [prereq] $SKILL_NAME: WARN malformed PREREQS.json (skipped)"
      fi
    fi

    # Mark skill as wired for this version
    touch "$WIRED_SENTINEL" 2>/dev/null || true
    # FIX 1: state transition -- installer + CORE_UPDATES merge ran = WIRED
    # (still NOT "installed" until the verification gate passes below).
    command -v obs_set_status >/dev/null 2>&1 && obs_set_status "$SKILL_NAME" "wired"
    WIRED_COUNT=$((WIRED_COUNT + 1))
  done

  echo "  Wiring complete: $WIRED_COUNT skill(s) wired, $SKIPPED_WIRED_COUNT already wired (idempotent skip)"

  # ----------------------------------------------------------
  # v16.2.6: DEFENSIVE tool-drift report (installed CLIs vs skill source).
  # Some skills install a standalone CLI by copying their engine into
  # ~/.openclaw/tools/<tool>/ and `pip install -e` on the copy (e.g. caf, skill
  # 44). The routine sync updates skill SOURCE files but the installed binary can
  # still drift. scripts/tool-drift-check.sh reads each tool's .installed-from
  # stamp, compares it to skill-version.txt, and capability-probes the binary.
  # This is REPORT-ONLY and MUST NOT change the update's exit status: it runs
  # only when the script is present + executable, and any non-zero verdict is
  # swallowed (`|| true`) so a stale/missing tool never fails the update here —
  # it is surfaced loudly for an operator/agent rebuild instead.
  TOOL_DRIFT_CHECK="$ONBOARDING_DIR/scripts/tool-drift-check.sh"
  if [ -x "$TOOL_DRIFT_CHECK" ]; then
    TOOL_DRIFT_JSON="${LOG_FILE%.log}-tool-drift.json"
    echo ""
    echo "  Checking installed CLI tools for drift vs skill source (report-only)..."
    if bash "$TOOL_DRIFT_CHECK" --json-only > "$TOOL_DRIFT_JSON" 2>>"$LOG_FILE"; then
      echo "  tool-drift: all installed CLIs in sync with source."
    else
      echo "  tool-drift: STALE/UNPROVEN TOOLING DETECTED -- see $TOOL_DRIFT_JSON"
      echo "  (rebuild commands are printed in that JSON; rebuild is opt-in, never auto-run here)"
    fi || true
  fi

  # ----------------------------------------------------------
  # Harden Google Workspace (gws) credential resilience on the ROLL path too.
  # ----------------------------------------------------------
  # Same guard install.sh Step 8c runs, so an updated box also gets: the file
  # keyring backend forced for every shell (append-only ~/.zshenv etc.), the
  # gws-as PATH wrapper, and an off-box encrypted snapshot of the default gws
  # credential store. This closes the v16.1.x self-wipe class on every box that
  # only ever takes the update path. Idempotent + additive + box-user; best-effort
  # so it can never change the update's exit status.
  HARDEN_GWS="$ONBOARDING_DIR/scripts/harden-gws-credential-resilience.sh"
  [ -f "$HARDEN_GWS" ] || HARDEN_GWS="$OC_CONFIG/scripts/harden-gws-credential-resilience.sh"
  if [ -f "$HARDEN_GWS" ]; then
    echo ""
    echo "  Hardening gws credential resilience (file keyring backend + gws-as wrapper + off-box backup)..."
    if OC_CONFIG="${OC_CONFIG:-}" bash "$HARDEN_GWS" >> "$LOG_FILE" 2>&1; then
      echo "  harden-gws-credential-resilience.sh: OK"
    else
      echo "  harden-gws-credential-resilience.sh: completed with warnings (see $LOG_FILE)"
    fi || true
  else
    echo "  (harden-gws-credential-resilience.sh not found -- skipping gws hardening; older bundle)"
  fi

  # ----------------------------------------------------------
  # v10.15.42: Run migrate-existing-workforce.sh so copied skills
  # actually install into the client's live department tree.
  # This script is idempotent and additive -- it never deletes or
  # overwrites existing departments, only fills gaps.
  #
  # v16.0.2: migrate-existing-workforce.sh Step 2b now MATERIALIZES missing
  # canonical floor roles/SOPs via floor-fill-driver.py (fed by
  # make-gap-from-staleness.py). Before v16.0.2 the update path DETECTED the
  # missing v16 floor roles (devils-advocate/healer per dept, video/graphics/
  # presentations expansions) but never FILLED them, leaving every v16-updated
  # box with an incomplete floor. Running migrate here closes that on the update
  # path (the same floor-fill backstop runs on the install path -- see
  # install.sh step 6b). Idempotent, skip-existing, no-clobber, box-user.
  # ----------------------------------------------------------
  MIGRATE_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh"
  if [ -x "$MIGRATE_SCRIPT" ]; then
    echo ""
    echo "  Running workforce migration (installs copied skills into department tree)..."
    if bash "$MIGRATE_SCRIPT" "$(hostname)" --apply >> "$LOG_FILE" 2>&1; then
      echo "  migrate-existing-workforce.sh: OK"
    else
      echo "  migrate-existing-workforce.sh: completed with warnings (see $LOG_FILE)"
      # v20.0.10: migrate-existing-workforce.sh is WORKFORCE floor-fill -- its
      # exit code is its Step-5 qc-completeness WORKFORCE verdict (rc 2 = a dept
      # below the 95% floor; rc 3 = a dept at zero materialization / no workforce
      # built yet for an interview-incomplete client). Those are WORKFORCE-
      # provisioning states, NOT skills-content problems: the A3 content-gate, the
      # U6b persona-content re-assertion, and the refresh-stale-roles IN-SCOPE
      # content-refresh check are what protect the content stamp. A half-built
      # workforce must NOT withhold the skills-version stamp (the box IS on current
      # content) -- it is surfaced as an advisory and driven to completion by the
      # POST-stamp qc-completeness run + the onboarding-resume cron. So route it to
      # the workforce latch, decoupled from the content stamp (was _D2_REFRESH_STATUS,
      # which conflated workforce floor-fill with in-scope content refresh).
      _D2_MIGRATE_STATUS="fail"
    fi
  else
    echo "  (migrate-existing-workforce.sh not found or not executable -- skipping)"
  fi

  # ----------------------------------------------------------
  # v12.27.0: PER-ARTIFACT STALENESS DETECTION (drives the refresh flow).
  # After the new library version lands and the migration filled structural gaps,
  # ask detect-stale-artifacts.py whether THIS client's built roles / depts / SOPs
  # are out of date vs the installed role-library content manifest. The hash is
  # canonical-source based (computed over the library TEMPLATE with {{TOKENS}}
  # intact, NOT rendered client bytes), so this has ZERO per-client false
  # positives: a future edit to ONE role .md flags ONLY clients built from the old
  # content_sha, for ONLY that artifact. rc 10 + the --json item list are the
  # refresh work queue: STALE roles are re-instantiated via the SAME copy+token-fill
  # path migrate-existing-workforce.sh / build-workforce use, MISSING roles are
  # added, build-state.artifactProvenance is rewritten, and the per-file
  # workforce-provenance marker is re-stamped — returning the client to CURRENT.
  # READ-ONLY here (report + queue); the re-instantiation reuses the existing
  # additive migration path so this never deletes or overwrites client edits.
  # ----------------------------------------------------------
  DETECT_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/detect-stale-artifacts.py"
  DETECT_MANIFEST="$SKILLS_DIR/23-ai-workforce-blueprint/templates/role-library/_index.json"
  if [ "$OPENCLAW_PLATFORM" = "vps" ]; then
    OC_WORKSPACE="/data/.openclaw/workspace"
  else
    OC_WORKSPACE="$HOME/.openclaw/workspace"
  fi
  if [ -f "$DETECT_SCRIPT" ] && [ -f "$DETECT_MANIFEST" ] && \
     { [ -d "$OC_WORKSPACE/departments" ] || [ -f "$OC_WORKSPACE/.workforce-build-state.json" ]; } && \
     command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "  Detecting per-artifact staleness (role / dept / SOP) vs new library content manifest..."
    if DETECT_OUT="$(python3 "$DETECT_SCRIPT" --workspace "$OC_WORKSPACE" --manifest "$DETECT_MANIFEST" --json 2>>"$LOG_FILE")"; then DETECT_RC=0; else DETECT_RC=$?; fi
    if [ -n "$DETECT_OUT" ]; then
      # Persist the refresh work queue so the orchestrator / a follow-up
      # re-instantiation pass can consume it (and for audit).
      QUEUE_FILE="$OC_WORKSPACE/.artifact-refresh-queue.json"
      printf '%s' "$DETECT_OUT" > "$QUEUE_FILE" 2>/dev/null || true
      printf '%s' "$DETECT_OUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
s = d.get('summary', {})
act = s.get('stale',0)+s.get('missing',0)+s.get('orphan',0)+s.get('untracked',0)
print(f\"  artifact staleness: CURRENT={s.get('current',0)} STALE={s.get('stale',0)} \"
      f\"MISSING={s.get('missing',0)} ORPHAN={s.get('orphan',0)} UNTRACKED={s.get('untracked',0)}\")
if act:
    print(f'  -> {act} artifact(s) queued for refresh (.artifact-refresh-queue.json); '
          'STALE/MISSING re-instantiate via the additive library-fill path')
else:
    print('  -> all artifacts CURRENT (nothing to refresh)')
" 2>/dev/null || true
      if [ "$DETECT_RC" -eq 10 ]; then
        echo "  (refresh queue written: $QUEUE_FILE)"
      fi
    else
      echo "  (detect-stale-artifacts.py produced no output -- skipping; see $LOG_FILE)"
    fi
  else
    echo "  (detect-stale-artifacts.py / manifest / workspace not present -- skipping per-artifact staleness check)"
  fi

  # ----------------------------------------------------------
  # P2-08 step 2: ARTIFACT-REFRESH-QUEUE CONSUMER.
  # The queue write above (.artifact-refresh-queue.json) has had a producer
  # since v12.27.0 but NEVER a consumer for the STALE-role case -- a box kept
  # OLD role docs forever after an upgrade (Presentation spec Section 13.9
  # deploy trap; the v16.0.2 floor-fill-driver.py only ever handled MISSING
  # roles, skip-existing/no-clobber by design, so it never touches a role
  # that already has a folder on disk). refresh-stale-roles.py drains ONLY
  # kind=="role" AND status=="STALE" queue rows: it re-copies the current
  # library content into the EXISTING role's how-to.md via the SAME
  # library_lookup()/try_library_fill() path create_role_workspace() uses for
  # a brand-new role, then re-stamps the provenance marker with the CURRENT
  # content_sha so a future detect-stale-artifacts.py run classifies it
  # CURRENT. SOP/dept/persona rows and MISSING/ORPHAN/UNTRACKED rows are left
  # in the queue untouched (out of this consumer's scope). A poisoned row
  # (nonexistent role path, corrupt JSON, no library match) is skipped with a
  # loud WARN and left queued -- it never aborts the update. Best-effort:
  # any failure here is swallowed (`|| true`) so a missing/broken consumer
  # tool can never fail the update itself.
  # ----------------------------------------------------------
  REFRESH_CONSUMER="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/refresh-stale-roles.py"
  if [ -f "$REFRESH_CONSUMER" ] && command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "  Draining artifact-refresh-queue (STALE role docs -> fresh library content)..."
    # D4[F]: pipefail-correct capture (set -euo pipefail active at L50) -- the
    # old `cmd | tee ... || echo` swallowed refresh-stale-roles.py's own exit
    # code (0=drain complete/benign, 3=in-scope refresh incomplete,
    # 1=usage-only) because `tee`'s exit status, not python3's, terminated the
    # pipeline. `if PIPE; then` under `set -o pipefail` correctly reflects the
    # FIRST failing command in the pipe.
    if python3 "$REFRESH_CONSUMER" --workspace "$OC_WORKSPACE" --apply 2>&1 | tee -a "$LOG_FILE"; then
      :
    else
      echo "  refresh-stale-roles.py: completed with warnings (see $LOG_FILE)"
      _D2_REFRESH_STATUS="fail"
    fi
  else
    echo "  (refresh-stale-roles.py not found or python3 unavailable -- skipping artifact-refresh-queue drain; older bundle)"
  fi

  # ----------------------------------------------------------
  # v10.15.51: SHARED CORE FILE UNIFICATION (Zero-Human-Workforce file model).
  # AFTER skills + workspaces + CORE_UPDATES wiring + workforce migration, every
  # agent/sub-agent on THIS box shares the box's ONE canonical AGENTS.md /
  # TOOLS.md / USER.md via symlink. Per-agent IDENTITY/SOUL/MEMORY/HEARTBEAT stay
  # each agent's own. Nested workflow agents exempt. Idempotent. Reads THIS box's
  # openclaw.json only (co-mingling guard) -- never a foreign/hardcoded target.
  # ----------------------------------------------------------
  echo ""
  echo "  Unifying shared core files (AGENTS/TOOLS/USER symlinked to this box's canonical)..."
  if link_shared_core_files; then
    :
  else
    echo "  ⚠ link_shared_core_files reported warnings (update continues)"
    _SHAREDCORE_STATUS="fail"  # D4[G]: renamed from the old _D5_ACTIVATION_STATUS name collision
  fi

  # ----------------------------------------------------------
  # D5 -- PRE-STAMP dept-agent activation gate (feeds the unified completeness
  # gate below). Runs materialize-dept-agents.sh here so a genuine
  # registration failure blocks the version stamp; the existing POST-stamp
  # materialize block further down (routing-correct final registration) is
  # LEFT IN PLACE and still runs its own idempotent re-pass afterward -- D5
  # keeps BOTH runs. A pre-interview self-skip (INTERVIEW_NOT_COMPLETE) and a
  # box where Skill 32 is not yet installed are BOTH benign -- PASS, not
  # fail. A genuine non-zero exit always flips _D5_ACTIVATION_PASS. For an
  # interview-complete run, agents.list[] is compared against THIS box's real
  # expected department count (department-floor.py's expected_floor_count --
  # the 22-mandatory + 6-universal-primary 28-department floor from
  # department-naming-map.json, net of any owner-declined department) rather
  # than a fixed "under 2" magic number -- a box whose activation genuinely
  # failed for most departments but still kept >=2 agents no longer sails
  # through. When department-floor.py cannot resolve a verdict for this box
  # (older bundle, or no departments dir yet), the gate falls back to the
  # prior "under 2" wiring-only check rather than false-FAIL a box with no
  # computable floor.
  # ----------------------------------------------------------
  _D5_MATERIALIZE="$SKILLS_DIR/32-command-center-setup/scripts/materialize-dept-agents.sh"
  if [ -f "$_D5_MATERIALIZE" ]; then
    echo ""
    echo "  [D5] Pre-stamp dept-agent activation check (materialize-dept-agents.sh)..."
    if _D5_OUT="$(bash "$_D5_MATERIALIZE" 2>&1)"; then _D5_RC=0; else _D5_RC=$?; fi
    if [ "$_D5_RC" -ne 0 ]; then
      _D5_ACTIVATION_PASS=0
      _D5_DEPT_STATE="fail"
      _D5_NOTLIVE_DETAIL="materialize-dept-agents.sh exited $_D5_RC"
      echo "  ✗ [D5] materialize-dept-agents.sh exited $_D5_RC — dept agents NOT registered"
    elif printf '%s' "$_D5_OUT" | grep -q "INTERVIEW_NOT_COMPLETE"; then
      _D5_DEPT_STATE="interview-not-complete"
      echo "  ✓ [D5] pre-interview self-skip (INTERVIEW_NOT_COMPLETE) — benign, not a failure"
    else
      _D5_AGENT_COUNT=0
      if [ -f "$OC_JSON" ]; then
        _D5_AGENT_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OC_JSON')); sys.stdout.write(str(len(d.get('agents',{}).get('list',[]))))" 2>/dev/null || echo "0")
      fi
      # D5[F2]: gate on THIS box's real expected department count instead of a
      # fixed "-lt 2" magic number. A genuine interview-complete box carries the
      # 28-department universal floor (department-naming-map.json: 22 mandatory
      # + 6 universal-primary, net of any owner-declined dept) -- "-lt 2" let a
      # box whose activation genuinely failed for MOST departments but still
      # kept >=2 agents.list[] entries false-PASS. department-floor.py is the
      # single source of truth qc-completeness.sh's own floor gate already
      # imports, so this stays in lockstep with the rest of the completeness
      # contract instead of drifting from it.
      _D5_EXPECTED_COUNT=""
      _D5_FLOOR_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/department-floor.py"
      if [ -f "$_D5_FLOOR_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
        _D5_FLOOR_JSON="$(python3 "$_D5_FLOOR_SCRIPT" --json 2>/dev/null || true)"
        _D5_EXPECTED_COUNT="$(printf '%s' "$_D5_FLOOR_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
n = d.get('expected_floor_count')
if isinstance(n, int) and n > 0:
    sys.stdout.write(str(n))
" 2>/dev/null || true)"
      fi
      if [ -n "$_D5_EXPECTED_COUNT" ]; then
        # Precise per-box floor available -- gate on THIS box's real expected count.
        if [ -z "$_D5_AGENT_COUNT" ] || [ "$_D5_AGENT_COUNT" -lt "$_D5_EXPECTED_COUNT" ]; then
          _D5_ACTIVATION_PASS=0
          _D5_DEPT_STATE="fail"
          _D5_NOTLIVE_DETAIL="agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize, below this box's computed department floor of ${_D5_EXPECTED_COUNT} (interview complete)"
          echo "  ✗ [D5] WIRING-ASSERT FAIL: agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize, below the computed department floor of ${_D5_EXPECTED_COUNT}"
        else
          _D5_DEPT_STATE="registered"
          echo "  ✓ [D5] dept agents registered (${_D5_AGENT_COUNT} agents in agents.list[], floor=${_D5_EXPECTED_COUNT})"
        fi
      elif [ -z "$_D5_AGENT_COUNT" ] || [ "$_D5_AGENT_COUNT" -lt 2 ]; then
        # department-floor.py unavailable / no verdict for this box -- fall
        # back to the prior wiring-only check so we never false-FAIL a box
        # we have no computable floor for.
        _D5_ACTIVATION_PASS=0
        _D5_DEPT_STATE="fail"
        _D5_NOTLIVE_DETAIL="agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize (interview complete; department-floor.py unavailable -- fell back to the wiring-only check)"
        echo "  ✗ [D5] WIRING-ASSERT FAIL: agents.list[] has only ${_D5_AGENT_COUNT:-0} entries after materialize"
      else
        _D5_DEPT_STATE="registered"
        echo "  ✓ [D5] dept agents registered (${_D5_AGENT_COUNT} agents in agents.list[]; department-floor.py unavailable -- wiring-only check)"
      fi
    fi
  else
    echo "  (materialize-dept-agents.sh not found -- Skill 32 not yet installed on this box; D5 pre-stamp activation check SKIPPED, benign)"
  fi

  # ----------------------------------------------------------
  # A3: CONTENT-GATE — verify installed content matches source
  # BEFORE writing the version stamp. This replaces the old
  # tautological verify (script wrote its own constant) with a
  # real content assertion (destination digest == source digest).
  # If ANY installed skill's content does not match the source,
  # the stamp is NEVER written and the script exits 1.
  # ----------------------------------------------------------
  _A3_GATE_PASS=1
  _A3_MISMATCH_SKILLS=""
  if [ -n "$SRC_MANIFEST" ] && [ -f "$_CONTENT_HASH_SCRIPT" ]; then
    echo ""
    echo "  [A3] Running content-gate: verifying destination matches source..."
    DEST_MANIFEST=$(bash "$_CONTENT_HASH_SCRIPT" "$SKILLS_DIR" 2>/dev/null || true)

    # Compare per-skill digests for skills that were installed this run.
    # We skip skills that were not in scope (ARCHIVED, or not updated by --only).
    while IFS='|' read -r skill_name src_digest; do
      [ -z "$skill_name" ] && continue
      [[ "$skill_name" == "__TREE_SHA__" ]] && continue
      case "$skill_name" in *ARCHIVED*) continue ;; esac

      dest_digest=$(echo "$DEST_MANIFEST" | grep "^${skill_name}|" | cut -d'|' -f2 | head -1 || true)
      if [ -z "$dest_digest" ]; then
        echo "    [A3] MISMATCH: $skill_name — present in source but NOT in destination" >&2
        _A3_MISMATCH_SKILLS="${_A3_MISMATCH_SKILLS}  $skill_name: expected=$src_digest found=<missing>\n"
        _A3_GATE_PASS=0
      elif [ "$dest_digest" != "$src_digest" ]; then
        echo "    [A3] MISMATCH: $skill_name — content digest differs" >&2
        _A3_MISMATCH_SKILLS="${_A3_MISMATCH_SKILLS}  $skill_name: expected=$src_digest found=$dest_digest\n"
        _A3_GATE_PASS=0
      else
        : # echo "    [A3] OK: $skill_name"
      fi
    done <<< "$SRC_MANIFEST"

    if [ "$_A3_GATE_PASS" -eq 0 ]; then
      echo ""
      echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
      echo "  A3 CONTENT-GATE FAILED — stamp NOT written."
      echo "  The following skills have content that does not match source:"
      printf '%b' "$_A3_MISMATCH_SKILLS"
      echo ""
      echo "  The version stamp is NEVER written when content is mismatched."
      echo "  Re-run update-skills.sh to retry the install from scratch."
      echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
      rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
      exit 1
    fi
    echo "  [A3] Content-gate PASSED — all installed skills match source."
  else
    echo "  [A3] skill-content-hash.sh unavailable — skipping content verification (legacy path)"
  fi

  # ----------------------------------------------------------
  # CONTENT-COMPLETENESS GATE (v20.0.10: content-vs-workforce split).
  # The .onboarding-version stamp certifies "this box's skills CONTENT is current
  # and matches the pinned tag" -- NOT "this client's workforce is fully built".
  # Runs strictly AFTER the A3 content-gate above and reuses its exit-1 discipline.
  # A healthy box ALWAYS reaches the stamp below: a fail here is reserved for a
  # genuine SKILLS-CONTENT integrity miss. Workforce-provisioning incompleteness
  # (empty depts for an interview-incomplete client, floor-fill for a box with no
  # workforce, a dept below the 95% floor) is surfaced as an ADVISORY and driven to
  # completion by the POST-stamp qc-completeness run + the onboarding-resume cron --
  # it NO LONGER withholds the content stamp (the ~11-box "content current but
  # unstamped" defect this release fixes).
  #
  # STAMP-GATING (content/wiring integrity -- WITHHOLD the stamp on fail):
  #   - A3 content-gate (above): installed skill digests == source digests.
  #   - _U6B_PERSONA_FAIL: persona-index CONTENT wiring -- triad-divergent library,
  #     asset lacking vectors, installed sentinel != manifest release_tag (installed
  #     persona content does NOT match the pinned tag), or the provision helper
  #     genuinely did not run.
  #   - _D2_REFRESH_STATUS: refresh-stale-roles.py rc 3 -- an IN-SCOPE role/SOP
  #     content refresh that SHOULD have re-applied the new library content to an
  #     EXISTING artifact genuinely failed. (Out-of-scope / MISSING / floor-fill
  #     rows exit 0 and never land here.)
  #   - _SHAREDCORE_STATUS: link_shared_core_files wiring step errored.
  #   - _SHAREDUTILS_STATUS: shared-utils/ refresh landed incomplete (a source
  #     top-level entry — e.g. sop-embed-once/ — is missing from the box). This tree
  #     is NOT covered by the A3 numbered-skill content-gate, so it is gated here.
  # NOT STAMP-GATING (workforce provisioning -- advisory only): _D2_MIGRATE_STATUS,
  #   _D5_ACTIVATION_PASS (handled in the advisory block below).
  # ----------------------------------------------------------
  if [ "${_U6B_PERSONA_FAIL:-0}" -eq 1 ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - persona index (U6b, provision-persona-index.sh): content incomplete${_PIDX_SKIP_WARNINGS:+ — ${_PIDX_SKIP_WARNINGS}}\n"
  fi
  if [ "${_D2_REFRESH_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - in-scope role/SOP content refresh (D2, refresh-stale-roles.py rc 3): an in-scope refresh that SHOULD have applied did not — see $LOG_FILE\n"
  fi
  if [ "${_SHAREDCORE_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - shared core file unification (link_shared_core_files): incomplete\n"
  fi
  if [ "${_SHAREDUTILS_STATUS:-ok}" != "ok" ]; then
    _STEP_GATE_FAILS="${_STEP_GATE_FAILS}  - shared-utils refresh (cp -r shared-utils): incomplete — source entries missing from box (e.g. sop-embed-once/); not covered by the A3 numbered-skill gate\n"
  fi

  # WORKFORCE-provisioning advisories (v20.0.10): recorded + surfaced, but they
  # NEVER withhold the content stamp. The POST-stamp qc-completeness run
  # (QC_COMPLETENESS_RC) and the onboarding-resume cron drive these to completion.
  if [ "${_D2_MIGRATE_STATUS:-ok}" != "ok" ]; then
    _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - workforce floor-fill (migrate-existing-workforce.sh): workforce below floor / interview-incomplete — see $LOG_FILE\n"
  fi
  if [ "${_D5_ACTIVATION_PASS:-1}" -ne 1 ]; then
    _WORKFORCE_INCOMPLETE_NOTES="${_WORKFORCE_INCOMPLETE_NOTES}  - dept-agent activation (D5, materialize-dept-agents.sh): incomplete${_D5_NOTLIVE_DETAIL:+ — ${_D5_NOTLIVE_DETAIL}}\n"
  fi
  if [ -n "$_WORKFORCE_INCOMPLETE_NOTES" ]; then
    echo ""
    echo "  ------------------------------------------------------------"
    echo "  WORKFORCE-PROVISIONING INCOMPLETE (advisory — does NOT withhold the"
    echo "  skills-content stamp; this box IS on current $ONBOARDING_VERSION content):"
    printf '%b' "$_WORKFORCE_INCOMPLETE_NOTES"
    echo "  Driven to completion by the post-stamp qc-completeness run and the"
    echo "  onboarding-resume cron (re-fires wiring + QC until green)."
    echo "  ------------------------------------------------------------"
  fi

  if [ -n "$_STEP_GATE_FAILS" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  CONTENT-COMPLETENESS GATE FAILED — stamp NOT written."
    echo "  The following skills-content integrity step(s) did not finish:"
    printf '%b' "$_STEP_GATE_FAILS"
    echo ""
    echo "  The version stamp is NEVER written when a content-integrity step fails."
    echo "  Re-run update-skills.sh to retry the incomplete step(s)."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # ----------------------------------------------------------
  # A3: CONTENT-MANIFEST + VERSION-STAMP (v20.0.11 ROOT-CAUSE FIX for the fleet
  # false-"done" defect). Ordering is now MANIFEST-FIRST, STAMP-LAST:
  #
  #   Previously the .onboarding-version stamp was written UNCONDITIONALLY here,
  #   BEFORE the manifest, and the manifest write was (a) gated on a possibly-empty
  #   $SRC_MANIFEST (so it was silently SKIPPED whenever skill-content-hash.sh was
  #   unavailable in the source, i.e. the "legacy path" that also skips A3) and
  #   (b) swallowed with "... || echo WARN (non-fatal)" so a python3/mv failure
  #   left the box STAMPED but WITHOUT a manifest. check-updates.sh (A4) then reads
  #   a missing manifest as "first install — not an error" and reports the box
  #   CURRENT on a version match. Net effect: v20.0.x stamp over stale/unverifiable
  #   content that no drift-detector can ever catch (A4 needs the manifest to compare).
  #
  #   The stamp is a "content is current AND recorded" certificate. It must NEVER
  #   exist without a matching manifest. So we now: build + validate the manifest
  #   to a temp file, FAIL THE WHOLE UPDATE (withhold the stamp) if it cannot be
  #   written or committed, and only THEN drop the stamp as the LAST artifact.
  #   Even on the legacy path (empty $SRC_MANIFEST) we still emit a DEGRADED
  #   manifest (content_verified="unavailable", empty skills map) so the stamp is
  #   never orphaned and A4 can treat the box as degraded rather than silently current.
  # ----------------------------------------------------------
  _NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  _MANIFEST_TMP=$(mktemp)
  _SKILLS_JSON=""
  _TREE_SHA="unknown"
  _CONTENT_VERIFIED="true"
  if [ -n "$SRC_MANIFEST" ]; then
    # Build the per-skill JSON block from the A2/A3 source manifest.
    while IFS='|' read -r _sn _sd; do
      [ -z "$_sn" ] && continue
      [[ "$_sn" == "__TREE_SHA__" ]] && continue
      case "$_sn" in *ARCHIVED*) continue ;; esac
      [ -n "$_SKILLS_JSON" ] && _SKILLS_JSON="${_SKILLS_JSON},"
      _SKILLS_JSON="${_SKILLS_JSON}\"${_sn}\":\"${_sd}\""
    done <<< "$SRC_MANIFEST"
    _TREE_SHA=$(echo "$SRC_MANIFEST" | grep "^__TREE_SHA__|" | cut -d'|' -f2 | head -1 || true)
    [ -z "$_TREE_SHA" ] && _TREE_SHA="unknown"
  else
    # Legacy path: skill-content-hash.sh was unavailable in source, so A3 was
    # skipped and there are no per-skill digests. Still emit a manifest so the
    # stamp is never orphaned; mark content unverifiable so A4 sees a degraded box.
    _CONTENT_VERIFIED="unavailable"
  fi

  # Build + validate the manifest to a temp file. A build failure is FATAL:
  # the stamp is withheld so this box is never reported "current" without a manifest.
  if ! python3 -c "
import json, sys
data = {
    'version': '${ONBOARDING_VERSION}',
    'src_git_sha': '${SRC_GIT_SHA:-unknown}',
    'src_from_zip': bool(${SRC_FROM_ZIP:-0}),
    'tree_sha': '${_TREE_SHA:-unknown}',
    'content_verified': '${_CONTENT_VERIFIED}',
    'installed_at': '${_NOW_ISO}',
    'skills': {${_SKILLS_JSON}},
    'activation': {
        'deptAgents': '${_D5_DEPT_STATE:-skipped}',
        'deptAgentCount': ${_D5_AGENT_COUNT:-0},
        'skillVerifyGate': '${ONBOARDING_GATE_OK:-pending-resume-cron}'
    }
}
with open('${_MANIFEST_TMP}', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"; then
    rm -f "$_MANIFEST_TMP"
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  A3 MANIFEST-WRITE FAILED — version stamp NOT written."
    echo "  Could not build the content-manifest companion file (python3 error)."
    echo "  The stamp is withheld so this box is never reported 'current' without a"
    echo "  matching manifest. Re-run update-skills.sh to retry."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Commit the manifest atomically. A commit failure is FATAL for the same reason.
  if ! mv "$_MANIFEST_TMP" "$SKILLS_DIR/.onboarding-content-manifest.json"; then
    rm -f "$_MANIFEST_TMP"
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  A3 MANIFEST-COMMIT FAILED — version stamp NOT written."
    echo "  Could not move the content-manifest into $SKILLS_DIR. Stamp withheld."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Post-write re-assertion: re-read and confirm tree_sha persisted intact. If the
  # manifest we just wrote is unreadable or diverged, the active dir was modified
  # mid-write — abort with the stamp STILL withheld.
  _RECHECK_TREE=$(python3 -c "import json; d=json.load(open('$SKILLS_DIR/.onboarding-content-manifest.json')); print(d.get('tree_sha',''))" 2>/dev/null || echo "")
  if [ "$_RECHECK_TREE" != "$_TREE_SHA" ]; then
    echo ""
    echo "  A3 POST-WRITE ASSERTION FAILED: tree_sha in manifest does not match what was just written."
    echo "  Expected: $_TREE_SHA  Found: ${_RECHECK_TREE:-<unreadable>}"
    echo "  Active dir may have been modified during the write — aborting (stamp withheld)."
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # Manifest is committed and validated. NOW write the version stamp as the LAST
  # artifact — ordering guarantees a box is never stamped-without-manifest (the
  # exact false-"done" condition this fix eliminates).
  echo "$ONBOARDING_VERSION" > "$SKILLS_DIR/.onboarding-version"

  # Sync version marker to legacy locations if they exist
  for _LEGACY_MARKER in \
      "$HOME/Downloads/openclaw-master-files/.onboarding-version" \
      "$HOME/.openclaw/onboarding/.onboarding-version"; do
    if [ -f "$_LEGACY_MARKER" ]; then
      echo "$ONBOARDING_VERSION" > "$_LEGACY_MARKER" 2>/dev/null || true
    fi
  done

  # Secondary check: verify the stamp was physically written (defense-in-depth)
  VERIFY_VER=$(cat "$SKILLS_DIR/.onboarding-version" 2>/dev/null | tr -d '[:space:]')
  if [ "$VERIFY_VER" != "$ONBOARDING_VERSION" ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  FAILURE: active skills dir was NOT updated!"
    echo "  Expected version : $ONBOARDING_VERSION"
    echo "  Found version    : ${VERIFY_VER:-<missing>}"
    echo "  Active dir       : $SKILLS_DIR"
    echo "  The running agent is still on the OLD skills."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi
  VERIFY_SKILL_COUNT=$(ls -d "$SKILLS_DIR"/[0-9]*/ 2>/dev/null | wc -l | tr -d ' ')
  if [ "$VERIFY_SKILL_COUNT" -eq 0 ]; then
    echo ""
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "  FAILURE: no skill folders found in active dir after update!"
    echo "  Active dir : $SKILLS_DIR"
    echo "  The running agent is still on the OLD skills."
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"
    exit 1
  fi

  # v14.24.0: Persist hooks/ library before temp-clone is removed.
  # grant-ceo-consent.sh + lib-ceo-tool-gate.sh look for lib-ceo-consent.sh at
  # ~/.openclaw/hooks/ (or /data/.openclaw/hooks/ on VPS) as a fallback after
  # the temp clone is gone.  Without this, update-only boxes keep the pre-#398/#403
  # gate library until the next full install.
  _OC_HOOKS_DEST="$HOME/.openclaw/hooks"
  [ -d "/data/.openclaw" ] && _OC_HOOKS_DEST="/data/.openclaw/hooks"
  mkdir -p "$_OC_HOOKS_DEST" 2>/dev/null || true
  if [ -d "$EXTRACTED_DIR/hooks" ]; then
    cp -f "$EXTRACTED_DIR/hooks/"*.sh "$_OC_HOOKS_DEST/" 2>/dev/null || true
    chmod +x "$_OC_HOOKS_DEST/"*.sh 2>/dev/null || true
    echo "  ✓ hooks/ library persisted to $_OC_HOOKS_DEST"
  fi

  # Cleanup
  rm -rf "$TEMP_EXTRACT" "$TEMP_ZIP"

  # ----------------------------------------------------------
  # FIX 1: VERIFICATION GATE -- run the gate on EVERY non-archived skill.
  # A skill counts INSTALLED only if (a) openclaw skills info shows it,
  # (b) its CORE_UPDATES sentinel is present (if it ships one), and (c) its
  # qc-*.sh exits 0 (if it ships one). We DO NOT claim "installed/onboarded"
  # for un-registered skills. The "complete" Telegram below is CONDITIONAL on
  # this gate. ONBOARDING_GATE_OK / _SUMMARY drive the honest report.
  # ----------------------------------------------------------
  ONBOARDING_GATE_OK="unknown"
  ONBOARDING_GATE_SUMMARY=""
  if command -v obs_verify_skill >/dev/null 2>&1; then
    echo ""
    echo "  Running the per-skill VERIFICATION GATE (skills info + CORE_UPDATES sentinel + qc-*.sh)..."
    for _gskill in "$SKILLS_DIR"/[0-9]*/; do
      [ -d "$_gskill" ] || continue
      _gname="$(basename "$_gskill")"
      case "$_gname" in *ARCHIVED*) continue ;; esac
      if _greason="$(obs_verify_skill "$_gname" "$SKILLS_DIR")"; then
        echo "    ✓ verified-installed: $_gname"
      else
        echo "    ✗ NOT verified: $_gname -- ${_greason}"
      fi
    done
    ONBOARDING_GATE_SUMMARY="$(obs_gate_summary "$SKILLS_DIR" 2>/dev/null | grep '^GATE-HUMAN:' | sed 's/^GATE-HUMAN: //' || true)"
    if obs_gate_summary "$SKILLS_DIR" >/dev/null 2>&1; then
      ONBOARDING_GATE_OK="yes"
    else
      ONBOARDING_GATE_OK="no"
    fi
  else
    echo "  ⚠ verification gate unavailable (onboarding-state.sh not sourced) -- cannot honestly verify; will report file-sync only."
  fi

  echo ""
  echo "============================================"
  if [ "$ONBOARDING_GATE_OK" = "yes" ]; then
    echo "   Skills updated AND verified-installed."
  elif [ "$ONBOARDING_GATE_OK" = "no" ]; then
    echo "   Skills FILE-SYNCED to disk -- NOT all verified-installed yet."
    echo "   ${ONBOARDING_GATE_SUMMARY:-(gate summary unavailable)}"
    echo "   (The onboarding-resume cron will re-fire wiring + QC until all pass.)"
  else
    echo "   Skills file-synced to disk (verification gate did not run)."
  fi
  echo "   Version: $ONBOARDING_VERSION"
  echo "   Location: $SKILLS_DIR"
  echo "   Files on disk: $VERIFY_SKILL_COUNT skill folders confirmed in active dir"
  if [ -n "$ONLY_SKILLS" ]; then
    echo "   Mode: SELECTIVE -- only [$ONLY_SKILLS]"
    echo "   Skipped: $SKIPPED_COUNT other skills (not in --only list)"
  fi
  echo "============================================"

  # Mark the check timestamp so the catchup logic in future runs is accurate
  date -u +%Y-%m-%dT%H:%M:%SZ > "$SKILLS_DIR/.last-update-check" 2>/dev/null || true

  # ----------------------------------------------------------
  # Ensure the Sunday weekly update-check cron exists (idempotent)
  # Existing clients on pre-v9.2.0 won't have it; running the updater
  # backfills it.
  # ----------------------------------------------------------
  # JSON-exact cron presence check (fix/industry-gate-and-idempotent-crons):
  # `weekly-onboarding-update` is 24 chars — over the ~22-char threshold at
  # which `openclaw cron list`'s TEXT TABLE truncates names — so a text-grep
  # presence gate here false-negatives and re-adds a duplicate on every update
  # run (the same defect confirmed in Skill 39 / Skill 38's own registrars; see
  # shared-utils/cron-lib.sh). Sourced with an inline fallback so this update
  # pass never depends on a specific working directory.
  command -v oc_cron_present >/dev/null 2>&1 || {
    _lib_cron_present_uskl="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/shared-utils/cron-lib.sh"
    if [ -f "$_lib_cron_present_uskl" ]; then
      # shellcheck source=/dev/null
      source "$_lib_cron_present_uskl"
    fi
  }
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
  # DURABLE TOMBSTONE fallback (fix/industry-gate-and-idempotent-crons,
  # live-VPS finding): fail OPEN (never tombstoned) if shared-utils/cron-lib.sh
  # wasn't found above — never block registration outright over a missing
  # helper file. The real oc_cron_tombstoned (durable file-marker check) is
  # used automatically when the shared lib IS found.
  command -v oc_cron_tombstoned >/dev/null 2>&1 || oc_cron_tombstoned() { return 1; }

  if command -v openclaw >/dev/null 2>&1 && oc_cron_tombstoned "weekly-onboarding-update"; then
    echo "  weekly-onboarding-update is TOMBSTONED (deliberately removed) — NOT re-registering. Un-tombstone: bash scripts/tombstone-cron.sh --remove weekly-onboarding-update"
  elif command -v openclaw >/dev/null 2>&1; then
    # CRON REWRITE MIGRATION (fix/existing-box-cron-rewrite v14.19.1):
    # Boxes provisioned BEFORE the silent-cron fix (v14.10.2) carry the OLD
    # weekly-onboarding-update cron wired with --announce --channel telegram
    # --to <client-chat-id>.  The scheduler auto-delivers the raw maintenance
    # prompt into the CLIENT's Telegram chat every Sunday — internal operator
    # traffic the client was never meant to see.  A plain "already installed"
    # skip leaves the leaking cron in place.  Fix: detect old delivery wiring
    # via openclaw cron list --json and delete the stale entry so the creation
    # block below always lands the SILENT main-session form.
    if oc_cron_present "weekly-onboarding-update"; then
      _CRON_HAS_OLD_WIRING=false
      if command -v python3 >/dev/null 2>&1; then
        _OC_RAW_JSON=$(openclaw cron list --json 2>/dev/null) || _OC_RAW_JSON=""
        if [ -n "$_OC_RAW_JSON" ] && \
           OC_CRON_JSON="$_OC_RAW_JSON" python3 - <<'PYEOF' 2>/dev/null
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
          _CRON_HAS_OLD_WIRING=true
        fi
      fi
      if [ "$_CRON_HAS_OLD_WIRING" = "true" ]; then
        echo "  ↻ Existing weekly-onboarding-update cron has old auto-announce delivery — deleting for silent-form recreate"
        openclaw cron delete --name "weekly-onboarding-update" >/dev/null 2>&1 || true
        # Fall through to creation block below (cron is now absent)
      else
        echo "  ✓ Sunday weekly update-check cron already installed (SILENT — no client auto-announce)"
      fi
    fi
    # Create cron only when it is absent (never existed, or just deleted above)
    if ! oc_cron_present "weekly-onboarding-update"; then
      # ── SILENT-OPERATOR-CRON RULE (chore/silent-operator-crons) ───────────
      # weekly-onboarding-update is a MAINTENANCE/update-check cron, NOT an
      # owner-facing announcement. The old form registered it
      # `--session isolated --announce --channel telegram --to <owner-chat>`,
      # so the scheduler AUTO-DELIVERED the raw update-check prompt into the
      # CLIENT chat every Sunday — internal operator traffic the owner was never
      # meant to see (the leak OPERATOR-MAINTENANCE.md forbids). NOTE: the old
      # `isolated + --announce + --channel` shape is ALSO rejected by the gateway
      # on some builds (confirmed live; see 35-social-media-planner/INSTRUCTIONS.md).
      #
      # FIX: register a SILENT main-session agent-message cron — `--agent main
      # --session-target main --light-context` with NO --channel/--to/--announce.
      # The update-check runs in the agent's OWN context (log-only); the agent
      # then decides, via its own deliberate `openclaw message send`, whether to
      # surface an owner-facing "an update is available, may I apply it?" question.
      # Nothing is auto-pushed to the client. No owner target needed, so the old
      # operator-ID resolver/guard is removed entirely. Mirrors install.sh Step 12.
      PROMPT_TMP="/tmp/openclaw-cron-prompt-$$.txt"
      REPO_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"
      # Unified repo: same URL for both Mac and VPS platforms
      if curl -fsSL --max-time 15 "${REPO_URL}/cron-prompt.txt" -o "$PROMPT_TMP" 2>/dev/null && [ -s "$PROMPT_TMP" ]; then
        PROMPT_CONTENT=$(cat "$PROMPT_TMP")
        # fix/cron-flag-skew: define the runtime-compatible cron helper on the
        # guaranteed path to the create below (the resume-cron lib that also
        # defines it is sourced inside a conditional block above, so we re-guard
        # it here — its definition wins if already present). Emits the flags the
        # INSTALLED runtime accepts: 2026.6.11+ needs `--session main
        # --system-event`; older CLIs `--session-target main --message`.
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
        # Runtime-compatible SILENT main-session cron (fix/cron-flag-skew). The
        # 2026.6.11 runtime rejects `--session-target` and requires
        # `--session main --system-event` for main-session jobs; the old two-branch
        # form only ever emitted `--session-target main --message`, so a rolled box
        # silently installed NO weekly cron. _oc_cron_silent_main probes the CLI,
        # emits the accepted form, and degrades gracefully (never hard-fails).
        _WEEKLY_DESC="Sunday 3am ET -- SILENT update-check: look for OpenClaw onboarding + command-center updates; ask the owner permission (via your own message send) before applying anything."
        if _oc_cron_silent_main "weekly-onboarding-update" "main" "0 3 * * 0" "America/New_York" "$PROMPT_CONTENT" \
             --description "$_WEEKLY_DESC" --exact --light-context --thinking high --timeout-seconds 7200; then
          echo "  ✓ Sunday weekly update-check cron installed (Sundays 3am ET, SILENT main-session — no client auto-announce)"
        else
          echo "  ⚠ Cron install failed -- agent can retry manually (SILENT main-session form)"
        fi
        rm -f "$PROMPT_TMP"
      else
        echo "  ⚠ Could not fetch cron-prompt.txt -- agent can install cron manually later"
      fi
    fi
  fi

  # ----------------------------------------------------------
  # v12.34.0 (ZHC-EXPERIENCE fix BREAK #1): (RE)INSTALL THE PIPELINE TRIGGER CRONS.
  # The fleet HOT-PATCH path used to register ONLY weekly-onboarding-update — so a
  # box patched only via update-skills.sh got the new Skill 37 files but NO
  # closeout trigger, and silently depended on a prior full install.sh run. This
  # call backfills ALL pipeline trigger crons (workforce-build-resume,
  # interview-nudge, closeout-readiness-watchdog, closeout-resume) idempotently,
  # so files AND triggers now land together on the hot-patch path. Shared
  # registrar — the SAME script install.sh runs at end of run.
  # ----------------------------------------------------------
  echo ""
  echo "  Ensuring pipeline trigger crons (closeout experience triggers — hot-patch parity with install.sh)..."
  # BUG-FIX v13.0.1: this block runs AFTER the "# Cleanup" rm -rf "$TEMP_EXTRACT"
  # that wipes the freshly-pulled clone ($ONBOARDING_DIR/$EXTRACTED_DIR). On the
  # SUCCESS path $ONBOARDING_DIR no longer exists here, so resolve the persistent
  # copy first (stashed to ~/.openclaw/scripts during the install phase, before
  # cleanup). Fall back to the clone path / legacy path for older bundles.
  _PERSIST_SCRIPTS="${OC_PERSISTENT_SCRIPTS_DIR:-}"
  if [ -z "$_PERSIST_SCRIPTS" ]; then
    _PERSIST_SCRIPTS="$HOME/.openclaw/scripts"
    [ -d "/data/.openclaw" ] && _PERSIST_SCRIPTS="/data/.openclaw/scripts"
  fi
  ENSURE_CRONS="$_PERSIST_SCRIPTS/ensure-pipeline-crons.sh"
  [ -f "$ENSURE_CRONS" ] || ENSURE_CRONS="$ONBOARDING_DIR/scripts/ensure-pipeline-crons.sh"
  [ -f "$ENSURE_CRONS" ] || ENSURE_CRONS="$SKILLS_DIR/../onboarding/scripts/ensure-pipeline-crons.sh"
  if [ -f "$ENSURE_CRONS" ]; then
    if bash "$ENSURE_CRONS" >> "$LOG_FILE" 2>&1; then
      echo "  ✓ Pipeline trigger crons asserted (closeout has at least one live trigger)"
    else
      echo "  ⚠ ensure-pipeline-crons.sh returned non-zero — one or more pipeline crons not registered (see $LOG_FILE). Re-run to backfill."
    fi
  else
    echo "  ⚠ ensure-pipeline-crons.sh not found — pipeline cron backfill skipped (older bundle?). Closeout trigger may be absent on this box."
  fi

  # ----------------------------------------------------------
  # Fleet standards: ensure sub-agents fully permitted + Telegram media 50MB
  # (idempotent -- applied on every update, no-op if already canonical)
  # ----------------------------------------------------------
  # Capture openclaw.json hash BEFORE any config mutations so the conditional
  # gateway-restart gate at the end of this section can tell whether anything
  # actually changed (avoids a disruptive restart on a no-op update).
  _OC_CONFIG_HASH_BEFORE=""
  if [ -f "$OC_JSON" ]; then
    _OC_CONFIG_HASH_BEFORE=$(python3 -c "import hashlib; print(hashlib.md5(open('$OC_JSON','rb').read()).hexdigest())" 2>/dev/null || true)
  fi
  echo ""
  echo "  Applying fleet standards (sub-agents fully permitted, Telegram media 50MB)..."
  # BUG-FIX v13.0.1: prefer the persistent copy — $ONBOARDING_DIR (the clone) was
  # already removed by the "# Cleanup" rm -rf above on the success path, which is
  # why this previously printed "Fleet standards script not found" on EVERY
  # successful update. Fall back to the clone path for older/edge bundles.
  FLEET_STD="$_PERSIST_SCRIPTS/apply-fleet-standards.sh"
  [ -f "$FLEET_STD" ] || FLEET_STD="$ONBOARDING_DIR/scripts/apply-fleet-standards.sh"
  if [ -f "$FLEET_STD" ]; then
    bash "$FLEET_STD" >/dev/null 2>&1 && echo "  ✓ Fleet standards applied" || echo "  ⚠ Fleet standards application reported errors (update continues)"
  else
    echo "  ⚠ Fleet standards script not found"
  fi

  # ----------------------------------------------------------
  # v14.24.0: Operator Telegram channel separation (mirrors install.sh:7113-7124).
  # configure-operator-telegram.sh is idempotent; it emits a machine-readable
  # STATUS: operator-telegram=<state> line for honest reporting.
  # ----------------------------------------------------------
  echo ""
  echo "  Configuring operator Telegram channel separation..."
  _OPTG="$_PERSIST_SCRIPTS/configure-operator-telegram.sh"
  [ -f "$_OPTG" ] || _OPTG="$ONBOARDING_DIR/scripts/configure-operator-telegram.sh"
  if [ -f "$_OPTG" ]; then
    _OPTG_OUT="$(bash "$_OPTG" 2>&1)" || true
    _OPTG_STATUS="$(printf '%s\n' "$_OPTG_OUT" | grep -E '^STATUS:' | tail -1 || true)"
    case "$_OPTG_STATUS" in
      *=CONFIGURED*)                  echo "  ✓ Operator Telegram separation live (${_OPTG_STATUS})" ;;
      *STRUCTURE_ONLY_NEEDS_TOKEN*)   echo "  ⚠ Operator Telegram structure written; bot token still needed (${_OPTG_STATUS})" ;;
      *VALIDATE_FAILED*)              echo "  ⚠ Operator Telegram merge failed validation + rolled back (${_OPTG_STATUS})" ;;
      *)                              echo "  ℹ Operator Telegram config ran (${_OPTG_STATUS:-(no STATUS line)})" ;;
    esac
  else
    echo "  ⚠ configure-operator-telegram.sh not found — skipping"
  fi

  # ----------------------------------------------------------
  # v14.24.0: Install hardening (mirrors install.sh:6770-6776).
  # Idempotent + non-blocking: hooks.token auto-gen, brew check, media tools.
  # ----------------------------------------------------------
  echo ""
  echo "  Running install hardening (hooks.token, brew check, media tools)..."
  _HARDENING="$_PERSIST_SCRIPTS/install-hardening.sh"
  [ -f "$_HARDENING" ] || _HARDENING="$ONBOARDING_DIR/scripts/install-hardening.sh"
  if [ -f "$_HARDENING" ]; then
    bash "$_HARDENING" 2>&1 | tail -5 || true
    echo "  ✓ Install hardening complete"
  else
    echo "  ℹ install-hardening.sh not in bundle — skipping (older bundle, harmless)"
  fi

  # ----------------------------------------------------------
  # v14.24.0: Sane heartbeat defaults (mirrors install.sh Fix D / Fix D2).
  # CONDITIONAL: only sets when unset or below 6h threshold.
  # ----------------------------------------------------------
  echo ""
  echo "  Ensuring heartbeat defaults (6h min, main-only, capped tokens)..."
  _ENSURE_HB="$_PERSIST_SCRIPTS/ensure-heartbeat-defaults.sh"
  [ -f "$_ENSURE_HB" ] || _ENSURE_HB="$ONBOARDING_DIR/scripts/ensure-heartbeat-defaults.sh"
  if [ -f "$_ENSURE_HB" ]; then
    bash "$_ENSURE_HB" 2>&1 || true
  else
    echo "  ℹ ensure-heartbeat-defaults.sh not in bundle — skipping"
  fi

  # ----------------------------------------------------------
  # Loop / furnace protection activation (Skill 60 EWS + Skill 61 Loop
  # Protection). Post-sync hook — the SAME shared helper install.sh calls, so the
  # roll/update path activates identically (no copy-paste drift). Client-box
  # activation is GATED HELD by default (61-loop-protection-system/config/
  # rollout.json; env OPENCLAW_LOOP_PROTECTION_ROLLOUT overrides); it installs the
  # 60-then-61 watchdogs (ews-tick + loop-tick crons + ledgers) in DRY_RUN
  # observe-only ONLY when the fleet rollout gate is enabled, and NEVER arms.
  # See GRAPHICS-FURNACE-CONTEXT-RESCUE-SPEC Topic 2 §2.3 item 2. Best-effort.
  # ----------------------------------------------------------
  echo ""
  echo "  Loop/furnace protection (Skill 60 + 61): activation gate (HELD by default; DRY_RUN, never arms)..."
  _ACT_LOOP="$_PERSIST_SCRIPTS/activate-loop-protection.sh"
  [ -f "$_ACT_LOOP" ] || _ACT_LOOP="$ONBOARDING_DIR/scripts/activate-loop-protection.sh"
  if [ -f "$_ACT_LOOP" ]; then
    bash "$_ACT_LOOP" --role client --skills-dir "$SKILLS_DIR" 2>&1 | tail -6 || true
  else
    echo "  ℹ activate-loop-protection.sh not in bundle — loop protection wiring skipped (older bundle)"
  fi

  # ----------------------------------------------------------
  # Routing-defect permanent fix (4-layer: doctrine path, pptx deny, symlink
  # unblock, dept workspace seeding). Mirror of install.sh — idempotent on every
  # update, no-op when already applied. tools.sessions.visibility + agentToAgent
  # require a gateway reload to take effect; that reload is gated below.
  # apply-routing-fix.sh is persisted to $_PERSIST_SCRIPTS at the persistent-copy
  # loop above so it survives the temp-clone cleanup, same as apply-fleet-standards.sh.
  # ----------------------------------------------------------
  echo ""
  echo "  Applying routing-defect permanent fix (4-layer: doctrine, pptx deny, symlink unblock, dept seeding)..."
  ROUTING_FIX="$_PERSIST_SCRIPTS/apply-routing-fix.sh"
  [ -f "$ROUTING_FIX" ] || ROUTING_FIX="$ONBOARDING_DIR/scripts/apply-routing-fix.sh"
  if [ -f "$ROUTING_FIX" ]; then
    bash "$ROUTING_FIX" >/dev/null 2>&1 && echo "  ✓ Routing fix applied" || echo "  ⚠ Routing fix reported errors (update continues — re-run apply-routing-fix.sh)"
  else
    echo "  ⚠ apply-routing-fix.sh not found (skipping routing fix)"
  fi

  # ----------------------------------------------------------
  # CEO PreToolUse intent-gate — WIRE THE RUNTIME BRAKE (v16.2.19).
  # apply-routing-fix.sh (above) stamps the presentation reflex + the SIGNED
  # route-presentation.sh helper, but that reflex is only ENFORCED at runtime by
  # the PreToolUse intent-gate hook (hooks/ceo-intent-gate.sh): the hook denies a
  # raw `python3 build_deck.py` on the router/CEO and redirects it to route. The
  # hook + its installer shipped but were NEVER invoked, so the brake stayed OFF
  # on every box. Wire it here, mirroring the apply-routing-fix.sh pattern: prefer
  # the persistent copy (survives the temp-clone cleanup); the installer reads its
  # hook+lib source from the persisted ~/.openclaw/hooks/ library staged above.
  # Idempotent (self-skips when already wired), self-skips on PA-default boxes,
  # box-user (never root), non-fatal (a wiring error is a loud warning, NOT an
  # update abort — same convention as the other verify/stamp steps here).
  # ----------------------------------------------------------
  echo ""
  echo "  Wiring CEO PreToolUse intent-gate (runtime brake for the presentation reflex)..."
  INTENT_GATE_INSTALLER="$_PERSIST_SCRIPTS/install-ceo-intent-gate.sh"
  [ -f "$INTENT_GATE_INSTALLER" ] || INTENT_GATE_INSTALLER="$ONBOARDING_DIR/scripts/install-ceo-intent-gate.sh"
  if [ -f "$INTENT_GATE_INSTALLER" ]; then
    if bash "$INTENT_GATE_INSTALLER" 2>&1; then
      echo "  ✓ CEO intent-gate wired (or already wired / PA-box skip)"
    else
      echo "  ⚠ install-ceo-intent-gate.sh reported errors (update continues — re-run install-ceo-intent-gate.sh)"
    fi
  else
    echo "  ⚠ install-ceo-intent-gate.sh not found (skipping intent-gate wire)"
  fi

  # ----------------------------------------------------------
  # Post-stamp verification: verify-routing.sh static gates G1–G8 (v16.2.19).
  # The updater applied the 4-layer routing fix + wired the intent-gate above but
  # never VERIFIED them, so a box that silently failed a layer went unflagged. Run
  # the gate now and surface per-gate PASS/FAIL. LOUD WARNING on failure — NOT a
  # hard update abort (matches the non-fatal convention of the other steps here;
  # the gate is read-only/static G1–G8, no --probe).
  # ----------------------------------------------------------
  VERIFY_ROUTING="$_PERSIST_SCRIPTS/verify-routing.sh"
  [ -f "$VERIFY_ROUTING" ] || VERIFY_ROUTING="$ONBOARDING_DIR/scripts/verify-routing.sh"
  if [ -f "$VERIFY_ROUTING" ]; then
    echo ""
    echo "  Verifying routing wiring (verify-routing.sh static gates G1–G8)..."
    if bash "$VERIFY_ROUTING" 2>&1; then
      echo "  ✓ verify-routing: all static gates PASS"
    else
      echo "  ⚠ verify-routing: one or more gates FAILED — routing/intent-gate wiring incomplete on this box."
      echo "  ⚠ Update continues; re-run apply-routing-fix.sh + install-ceo-intent-gate.sh, then 'bash scripts/verify-routing.sh' to see which gate."
    fi
  else
    echo "  ⚠ verify-routing.sh not found (skipping post-stamp routing verification)"
  fi

  # ----------------------------------------------------------
  # Dept-agent registration: turn built workspace folders into REAL agents in
  # openclaw.json. Runs after apply-routing-fix.sh so the routing config
  # (tools.sessions.visibility / agentToAgent) is set before agents are registered.
  # Idempotent: re-running adds 0 duplicates; updates stale entries in place.
  # Skipped silently when Skill 32 is not yet installed on this box.
  # ----------------------------------------------------------
  _MATERIALIZE="$SKILLS_DIR/32-command-center-setup/scripts/materialize-dept-agents.sh"
  if [ -f "$_MATERIALIZE" ]; then
    echo ""
    echo "  Registering dept agents in openclaw.json (materialize-dept-agents)..."
    if bash "$_MATERIALIZE" >/dev/null 2>&1; then
      # WIRING-ASSERT (v14.26.0): mirrors run-full-install.sh Phase 4 hard gate.
      # Verifies agents.list[] >=2 after materialize so a zero-dept scan, a path
      # miss, or a silent empty run is surfaced loudly — NOT swallowed with a
      # soft "update continues" message.  Skips gracefully when openclaw.json is
      # absent (Skill 32 not yet built on this box).
      _AGENT_COUNT=0
      if [ -f "$OC_JSON" ]; then
        _AGENT_COUNT=$(python3 -c "import json,sys; d=json.load(open('$OC_JSON')); sys.stdout.write(str(len(d.get('agents',{}).get('list',[]))))" 2>/dev/null || echo "0")
      fi
      if [ -z "$_AGENT_COUNT" ] || [ "$_AGENT_COUNT" -lt 2 ]; then
        echo "  ⚠ WIRING-ASSERT FAIL: agents.list[] has only ${_AGENT_COUNT:-0} entries after materialize"
        echo "  ⚠ Dept agents NOT live — re-run update after build-workforce.py completes or check Skill 32 path"
      else
        echo "  ✓ Dept agents registered (${_AGENT_COUNT} agents in agents.list[])"
      fi

      # DEPARTMENT-RUNTIME-PARITY GUARD (belt-and-suspenders on update runs): the
      # WIRING-ASSERT above only floors the TOTAL agents.list[] count — it never
      # verifies EACH INDIVIDUAL department board row (a mission-control.db
      # `workspaces` row) has ITS OWN matching runtime entry (the
      # no_specialist_runtime failure class). Cross-checks every seeded
      # department against agents.list[] using the same slug variants
      # blackceo-command-center's resolveSpecialistSessionKey() tries. Non-fatal
      # here (matches this block's own WARN-and-continue convention above) —
      # the SAME check is a HARD, install-blocking gate in run-full-install.sh
      # Phase 6e2, which this update run also invokes moments later via
      # --update-only below, so a real mismatch is never silently swallowed.
      _DEPT_PARITY_GUARD="$SKILLS_DIR/32-command-center-setup/scripts/guard-department-runtime-parity.py"
      if [ -f "$_DEPT_PARITY_GUARD" ]; then
        if _DEPT_PARITY_OUT="$(python3 "$_DEPT_PARITY_GUARD" --config "$OC_JSON" 2>&1)"; then
          echo "  ✓ ${_DEPT_PARITY_OUT##*] }"
        else
          echo "  ⚠ DEPARTMENT-RUNTIME-PARITY FAIL — one or more seeded departments have no matching OpenClaw runtime:"
          printf '%s\n' "$_DEPT_PARITY_OUT" | while IFS= read -r _line; do echo "  ⚠   $_line"; done
          echo "  ⚠ Update continues; this is also a hard install-blocking gate in run-full-install.sh (Phase 6e2)"
        fi
      fi
    else
      echo "  ⚠ WIRING-ASSERT FAIL: materialize-dept-agents.sh exited non-zero — dept agents NOT registered"
      echo "  ⚠ Check that Skill 32 is installed and build-workforce.py has produced department folders"
    fi

  # ----------------------------------------------------------
  # D5 — Command Center web-app refresh (v14.27.0):
  # git pull --ff-only + npm install + db:push + sync-departments + pm2 restart.
  # Closes the CC #108/#109/#112 delivery gap on EXISTING boxes.
  #
  # install.sh delivers CC v4.54.0 via the Skill-37 closeout agent (run-full-install.sh
  # Phase 6). update-skills.sh previously copied Skill-32 scripts but never INVOKED
  # run-full-install.sh, so existing boxes kept the stale dashboard + the #109
  # demo-department regression until an owner manually approved the weekly cron.
  #
  # Guarded: verify-remote guard — only fires when ~/projects/command-center is a git
  # checkout of blackceo-command-center. Does NOT re-embed the persona index (honors
  # "never rebuild a live correct index" and "client uses own keys").
  # ----------------------------------------------------------
  _CC_DIR="$HOME/projects/command-center"
  _CC_RUN_INSTALL="$SKILLS_DIR/32-command-center-setup/scripts/run-full-install.sh"
  # Resolve client identity from build-state once (used by BOTH the refresh and
  # the F10 bootstrap branch). An interview-completed box has these populated.
  _STATE_FILE="$OC_WORKSPACE_DEFAULT/.workforce-build-state.json"
  _CC_SLUG=""
  _CC_COMPANY=""
  _CC_EMAIL=""
  if [ -f "$_STATE_FILE" ]; then
    # P1-3: build-workforce.py now writes the slug as `companySlug` (canonical) and
    # `clientSlug` (transition alias). Read companySlug first, fall back to clientSlug,
    # so both build-state generations resolve. jq fallback chain (was: clientSlug-only).
    _CC_SLUG=$(jq -r '.companySlug // .clientSlug // ""' "$_STATE_FILE" 2>/dev/null || echo "")
    _CC_COMPANY=$(python3 -c "import json; d=json.load(open('$_STATE_FILE')); print(d.get('companyName',''))" 2>/dev/null || echo "")
    _CC_EMAIL=$(python3 -c "import json; d=json.load(open('$_STATE_FILE')); print(d.get('contactEmail',''))" 2>/dev/null || echo "")
  fi
  # ----------------------------------------------------------
  # D5-PRE (stale-checkout guard): both D5 branches below run the ON-BOX Skill-32
  # installer ($SKILLS_DIR/32-command-center-setup/scripts/run-full-install.sh).
  # But the copy loop only refreshes Skill 32 when it is in THIS run's copy set —
  # an `--only <not-32>` run (or a resume/closeout path) leaves a STALE on-box
  # installer, yet D5 invokes it unconditionally. A stale installer silently
  # lacks cc_mirror_api_auth_to_agent_secrets (Skill-32 v12.9.31), so it writes
  # the token to CC .env.local but never mirrors it to $OC_ROOT/secrets/.env —
  # the server is half-provisioned and dept-agent write-backs 401 (root cause of
  # boxes that "provisioned" but stayed dispatch-dead). Fix: bring the on-box
  # Skill-32 folder CURRENT from the freshly-cloned source BEFORE running it, so
  # the installer that runs always carries the latest provisioning logic. Version-
  # gated (skill-version.txt compare) so it is a no-op when already current; best-
  # effort and never fatal.
  if [ -n "${ONBOARDING_DIR:-}" ] \
     && [ -f "$ONBOARDING_DIR/32-command-center-setup/scripts/run-full-install.sh" ]; then
    _CC_SRC_VER=$(tr -d '[:space:]' < "$ONBOARDING_DIR/32-command-center-setup/skill-version.txt" 2>/dev/null || echo "")
    _CC_DST_VER=$(tr -d '[:space:]' < "$SKILLS_DIR/32-command-center-setup/skill-version.txt" 2>/dev/null || echo "")
    if [ -n "$_CC_SRC_VER" ] && [ "$_CC_SRC_VER" != "$_CC_DST_VER" ]; then
      echo "  [D5-PRE] Refreshing on-box Skill 32 (${_CC_DST_VER:-none} -> ${_CC_SRC_VER}) before running the CC installer (stale-checkout guard)..."
      rm -rf "$SKILLS_DIR/32-command-center-setup"
      cp -r "$ONBOARDING_DIR/32-command-center-setup" "$SKILLS_DIR/"
      command -v obs_set_status >/dev/null 2>&1 && obs_set_status "32-command-center-setup" "downloaded"
    fi
  fi
  if [ -d "$_CC_DIR/.git" ] && [ -f "$_CC_RUN_INSTALL" ]; then
    _CC_REMOTE=$(git -C "$_CC_DIR" remote get-url origin 2>/dev/null || echo "")
    if echo "$_CC_REMOTE" | grep -q 'blackceo-command-center'; then
      echo ""
      echo "  Refreshing Command Center web app (CC #108/#109/#112 — git pull + db:push + workspace seed + sync-departments)..."
      if bash "$_CC_RUN_INSTALL" --update-only "${_CC_SLUG:-}" "${_CC_COMPANY:-}" "${_CC_EMAIL:-}" >>"$LOG_FILE" 2>&1; then
        echo "  ✓ Command Center app refreshed (git pull + npm install + db:push + workspace seed + sync-departments + pm2 restart)"
      else
        echo "  ⚠ Command Center refresh reported errors — check $OC_WORKSPACE_DEFAULT/.command-center-install.log"
      fi
    fi
  elif [ ! -d "$_CC_DIR/.git" ] && [ -f "$_CC_RUN_INSTALL" ] \
       && [ -n "$_CC_SLUG" ] && [ -n "$_CC_COMPANY" ] && [ -n "$_CC_EMAIL" ]; then
    # F10 — CC bootstrap on update. Previously the refresh block above was the
    # ONLY CC path on update and it was gated on $_CC_DIR/.git existing, so an
    # interview-completed box that never cloned the dashboard got neither the
    # seeder nor the board on update — it stayed without a Command Center
    # forever. Run run-full-install.sh in FULL mode (clone + npm install +
    # db:push + Phase 6b workspace seed + sync-departments + pm2 start) so the
    # update path truly converges to the install path. Gated on a REAL interview
    # (build-state slug+company+email present) so a pre-interview/in-flight box
    # is never bootstrapped. run-full-install.sh is itself state-gated/idempotent
    # and runs as the box user (never root).
    echo ""
    echo "  Command Center not yet provisioned on this box (no checkout) — bootstrapping full install (clone + db:push + workspace seed + sync)..."
    if bash "$_CC_RUN_INSTALL" "$_CC_SLUG" "$_CC_COMPANY" "$_CC_EMAIL" >>"$LOG_FILE" 2>&1; then
      echo "  ✓ Command Center bootstrapped (clone + npm install + db:push + workspace seed + sync-departments + pm2 start)"
    else
      echo "  ⚠ Command Center bootstrap reported errors — check $OC_WORKSPACE_DEFAULT/.command-center-install.log"
    fi
  elif [ ! -d "$_CC_DIR/.git" ] && [ -f "$_CC_RUN_INSTALL" ] && [ -n "$_CC_SLUG" ]; then
    echo ""
    echo "  ℹ Command Center not provisioned and build-state is missing company/email — bootstrap deferred (needs slug+company+email)."
  fi

  fi

  # ----------------------------------------------------------
  # Conditional gateway restart: only restart when openclaw.json was actually
  # mutated by fleet-standards, routing-fix, or materialize this run.
  # This ensures tools.sessions.visibility and agentToAgent are live immediately
  # without restarting the gateway on every no-op update.
  # Platform dispatch: openclaw CLI first (works on Mac + VPS); falls back to
  # launchctl kickstart (Mac) or docker restart (VPS) when CLI is not on PATH.
  # ----------------------------------------------------------
  _OC_CONFIG_HASH_AFTER=""
  if [ -f "$OC_JSON" ]; then
    _OC_CONFIG_HASH_AFTER=$(python3 -c "import hashlib; print(hashlib.md5(open('$OC_JSON','rb').read()).hexdigest())" 2>/dev/null || true)
  fi
  if [ -n "$_OC_CONFIG_HASH_BEFORE" ] && [ -n "$_OC_CONFIG_HASH_AFTER" ]       && [ "$_OC_CONFIG_HASH_BEFORE" != "$_OC_CONFIG_HASH_AFTER" ]; then
    echo ""
    echo "  openclaw.json changed — restarting gateway to activate routing config..."
    if command -v openclaw >/dev/null 2>&1; then
      openclaw gateway restart >/dev/null 2>&1         && echo "  ✓ Gateway restarted (routing config now live)"         || echo "  ⚠ Gateway restart failed — restart manually: openclaw gateway restart"
    elif [ "$OC_PLATFORM" = "vps" ]; then
      docker restart openclaw >/dev/null 2>&1         && echo "  ✓ Gateway restarted via docker (routing config now live)"         || echo "  ⚠ docker restart failed — restart manually: openclaw gateway restart"
    else
      # v16.2.13: `awk '...exit'` closes the pipe on the first match → `launchctl
      # list` (hundreds of lines) dies with SIGPIPE (rc 141) → `pipefail` promotes
      # it → the plain assignment would abort the updater under `set -e` (same
      # SIGPIPE class as the persona-index reconcile bug). `|| true` neutralizes it;
      # the empty fallback on the next line already supplies the default label.
      GW_LABEL="$(launchctl list 2>/dev/null | awk '/openclaw.*gateway/{print $3; exit}' || true)"
      [ -z "$GW_LABEL" ] && GW_LABEL="ai.openclaw.gateway"
      launchctl kickstart -k "gui/$(id -u)/$GW_LABEL" >/dev/null 2>&1 \
        && echo "  ✓ Gateway restarted via launchctl (routing config now live)" \
        || echo "  ⚠ launchctl restart failed — restart manually: openclaw gateway restart"
    fi
  else
    echo "  ℹ Routing config unchanged — no gateway restart needed"
  fi

  # ----------------------------------------------------------
  # FIX-PRES-02: PRESENTATION DEPS CONVERGE (idempotent, fail-soft). A Mac box that
  # predates install.sh Step 6.5 never receives the four presentation-pipeline
  # runtime deps (soffice, pdftoppm, reportlab, python-pptx) from update-skills.sh,
  # so it would forever refuse every deck build at GATE 1 even after pulling the
  # latest skills. Converge them here exactly like install.sh Step 6.5's Mac branch
  # (VPS is handled by the reassert script the same step writes), then hard-WARN if
  # any dep is still missing. It never blocks the update; the following
  # qc-completeness gate re-checks the same four deps.
  # ----------------------------------------------------------
  converge_presentation_deps() {
    echo ""
    echo "  Converging presentation-pipeline runtime deps (soffice, pdftoppm, reportlab, python-pptx)..."
    if [ "${OPENCLAW_PLATFORM:-}" = "vps" ]; then
      local _reassert="/data/.openclaw/scripts/reassert-presentation-deps.sh"
      if [ -x "$_reassert" ]; then
        echo "    VPS: running the idempotent reassert script ($_reassert)..."
        bash "$_reassert" >/dev/null 2>&1 || echo "    ⚠ reassert script reported an issue (non-fatal)"
      else
        echo "    VPS: reassert script not present yet ($_reassert) — run install.sh Step 6.5 once to create it."
      fi
    else
      # Mac: brew formula for poppler, NONINTERACTIVE cask for LibreOffice (loud
      # warn on failure — a cask can need an admin password), pip --user for the
      # two Python modules. NONINTERACTIVE + no `read` so a silent roll never hangs.
      if command -v pdftoppm >/dev/null 2>&1; then
        echo "    pdftoppm (poppler) already present"
      elif command -v brew >/dev/null 2>&1; then
        brew install poppler >/dev/null 2>&1 && echo "    poppler (pdftoppm) installed" \
          || echo "    ⚠ brew install poppler failed — pdftoppm unavailable (Phase-6 QC PNG extraction will fail)"
      else
        echo "    ⚠ Homebrew not found — cannot install poppler (pdftoppm)"
      fi
      if command -v soffice >/dev/null 2>&1 || [ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
        echo "    soffice (LibreOffice) already present"
      elif command -v brew >/dev/null 2>&1; then
        echo "    Installing LibreOffice (soffice) via NONINTERACTIVE Homebrew cask..."
        NONINTERACTIVE=1 brew install --cask libreoffice >/dev/null 2>&1 \
          && echo "    LibreOffice cask install completed" \
          || echo "    ⚠ NONINTERACTIVE LibreOffice cask install failed (may need an admin password). Run once interactively: brew install --cask libreoffice"
      else
        echo "    ⚠ Homebrew not found — cannot install LibreOffice (soffice)"
      fi
      if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import reportlab, pptx" >/dev/null 2>&1; then
          echo "    reportlab + python-pptx already importable"
        else
          echo "    Installing reportlab + python-pptx (pip --user --break-system-packages)..."
          python3 -m pip install --user --break-system-packages reportlab python-pptx >/dev/null 2>&1 \
            && echo "    reportlab + python-pptx installed" \
            || echo "    ⚠ pip install reportlab/python-pptx failed — deck assembly + presenter PDF will fail"
        fi
      fi
    fi
    # Hard end-of-converge WARNING when any of the four deps is STILL missing.
    local _pres_missing=""
    command -v soffice  >/dev/null 2>&1 || _pres_missing="${_pres_missing} soffice"
    command -v pdftoppm >/dev/null 2>&1 || _pres_missing="${_pres_missing} pdftoppm"
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "import reportlab, pptx" >/dev/null 2>&1 || _pres_missing="${_pres_missing} python(reportlab+python-pptx)"
    fi
    if [ -n "$_pres_missing" ]; then
      echo "  ⚠⚠ PRESENTATION_DEPS_MISSING after converge:${_pres_missing}. The Skill 23 presentation pipeline will refuse every deck build at GATE 1 until these resolve. Mac: brew install poppler; brew install --cask libreoffice; python3 -m pip install --user --break-system-packages reportlab python-pptx. VPS: bash /data/.openclaw/scripts/reassert-presentation-deps.sh"
    else
      echo "  ✓ presentation deps converged: soffice + pdftoppm + reportlab + python-pptx all present"
    fi
  }
  converge_presentation_deps

  # ----------------------------------------------------------
  # v10.15.4: Post-pull qc-completeness check. Read-only. Runs against the live
  # workforce after every successful skill pull.
  #
  # SILENT-MAINTENANCE (v17.0.18): a fleet roll / skill update is inherently
  # MAINTENANCE, so this embedded QC call MUST run with OPENCLAW_MAINTENANCE=1.
  # That forces qc-completeness.sh into quiet mode and SUPPRESSES its Telegram
  # alert entirely (log-only) — the embedded QC step can NEVER message a client
  # during a roll. The operator still gets the workforce QC STATUS folded into the
  # OPERATOR-ROUTED update note below (send_telegram_progress), so no visibility is
  # lost — only the client-facing alert is suppressed.
  #
  # v20.0.9 (SECURITY/PRIVACY): belt-and-suspenders — this call ALSO passes --quiet
  # (log-only path) AND inherits the roll-wide OPENCLAW_MAINTENANCE_SILENT=1 exported
  # at the top of main(). Any ONE of the three (OPENCLAW_MAINTENANCE=1, --quiet,
  # OPENCLAW_MAINTENANCE_SILENT=1) fully suppresses the send, and qc-completeness now
  # routes only to the OPERATOR (never the client owner / allowFrom[0]) in any case.
  # ----------------------------------------------------------
  QC_COMPLETENESS_SCRIPT="$SKILLS_DIR/23-ai-workforce-blueprint/scripts/qc-completeness.sh"
  QC_STATUS_LINE=""
  QC_COMPLETENESS_RC=0   # FIX 1: HONOR this exit code (was ignored). 0=PASS, 2=PARTIAL, 3=FAIL, 4=NO_WORKFORCE
  if [ -x "$QC_COMPLETENESS_SCRIPT" ]; then
    echo ""
    echo "  Running qc-completeness.sh against live workforce (maintenance mode — client alert suppressed)..."
    QC_OUTPUT="$(OPENCLAW_MAINTENANCE=1 bash "$QC_COMPLETENESS_SCRIPT" --quiet 2>&1)" || QC_COMPLETENESS_RC=$?
    QC_STATUS_LINE="$(printf '%s\n' "$QC_OUTPUT" | grep -E '^STATUS:' | tail -1 || true)"
    echo "  ${QC_STATUS_LINE:-qc-completeness ran (no STATUS line captured)} (exit $QC_COMPLETENESS_RC)"
  fi

  # ----------------------------------------------------------
  # Post-update: write UPDATE PENDING flag + Telegram + backup block
  # ----------------------------------------------------------
  echo ""
  echo "  Writing UPDATE PENDING flag for agent activation..."
  write_update_pending_flag "$ONBOARDING_VERSION" "$NEW_SKILLS_CSV"

  # ----------------------------------------------------------
  # v17.0.21: make roll-time activation SELF-HEALING. When this roll left work
  # for the agent (new numbered skills copied, OR the verification gate did NOT
  # pass), install the SAME SILENT, bounded, self-removing onboarding-resume cron
  # that install.sh installs — so the activation flag we just wrote is actually
  # driven to qc-passed autonomously instead of waiting on a human. CONDITIONAL:
  # if there is NO pending activation (gate green AND no new skills) we install
  # NOTHING. IDEMPOTENT: install_onboarding_resume_cron() leaves any existing
  # cron in place. SILENT: the cron carries no --channel/--to/--announce (it is a
  # main-session self-ping); it can never push to a client chat.
  _RESUME_NEEDED="no"
  [ "${ONBOARDING_GATE_OK:-unknown}" = "no" ] && _RESUME_NEEDED="yes"   # gate proved unverified skills remain
  [ -n "${NEW_SKILLS_CSV:-}" ] && _RESUME_NEEDED="yes"                  # new numbered skills need activation
  if [ "$_RESUME_NEEDED" = "yes" ]; then
    echo "  Pending activation detected — ensuring the SILENT onboarding-resume cron (idempotent)..."
    if command -v install_onboarding_resume_cron >/dev/null 2>&1; then
      install_onboarding_resume_cron || echo "  ⚠ onboarding-resume cron install reported an issue (non-fatal; agent still has the flag)"
    else
      echo "  ⚠ install_onboarding_resume_cron unavailable (resume-cron lib not sourced) — skipping cron (agent still has the AGENTS.md flag)"
    fi
  else
    echo "  ✓ No pending activation (gate green, no new skills) — onboarding-resume cron NOT installed (nothing to self-heal)."
  fi

  echo "  Sending Telegram notification..."
  # ----------------------------------------------------------
  # FIX 1: HONEST REPORTING CONTRACT. The headline is CONDITIONAL on the
  # verification gate (ONBOARDING_GATE_OK) AND the workforce qc-completeness
  # exit code (QC_COMPLETENESS_RC, previously ignored). We NEVER say
  # "complete/installed/onboarded" unless BOTH gates pass. Otherwise we report
  # the truth: how many skills are verified vs. not, and that resume will retry.
  # ----------------------------------------------------------
  _TG_HEADLINE=""
  if [ "$ONBOARDING_GATE_OK" = "yes" ] && { [ "${QC_COMPLETENESS_RC:-0}" -eq 0 ] || [ "${QC_COMPLETENESS_RC:-0}" -eq 4 ]; }; then
    # Gate passed (qc=PASS, or NO_WORKFORCE which is not an install failure).
    _TG_HEADLINE="✅ OpenClaw skill update ${ONBOARDING_VERSION} verified-installed.

${ONBOARDING_GATE_SUMMARY:-all skills verified}."
  else
    # Honest partial. NEVER claim done.
    _TG_HEADLINE="⏳ OpenClaw skill update ${ONBOARDING_VERSION}: files synced, NOT all verified yet.

${ONBOARDING_GATE_SUMMARY:-verification gate did not produce a summary}.

The onboarding-resume cron will keep re-firing wiring + QC until every skill passes (it does NOT stop on a self-declared 'done')."
  fi

  send_telegram_progress "${_TG_HEADLINE}

New skills (need activation): ${NEW_SKILLS_CSV:-none -- updates only}.

Workforce QC: ${QC_STATUS_LINE:-not run} (exit ${QC_COMPLETENESS_RC:-?})

Persona-index provisioning: ${_PIDX_SKIP_WARNINGS:+⚠️ SKIPPED — }${_PIDX_SKIP_WARNINGS:-OK (no skip warnings)}

Paste this to your agent:

▶ \"I just ran update-skills.sh. There is an UPDATE PENDING flag at the top of my AGENTS.md describing what changed. Check .onboarding-state.json and run the verification gate (scripts/onboarding-state.sh). Activate + QC every skill that is not yet qc-passed. Do NOT report done until the gate passes. Send me a summary when the gate is green.\"

(If you didn't get THIS Telegram note, the same instructions are also printed in your Terminal.)"

  case "$TELEGRAM_LAST_RESULT" in
    sent-operator:*)        echo "  ✓ Update-result note sent to OPERATOR chat ${TELEGRAM_LAST_RESULT#sent-operator:} (not the client)" ;;
    logged-no-operator-chat) echo "  ℹ Update-result note LOG-ONLY (no operator escalation chat configured) — agent picks up the AGENTS.md UPDATE PENDING flag; client is NOT auto-notified" ;;
    no-openclaw-cli)        echo "  ⚠ Update-result note skipped -- openclaw CLI not on PATH (Terminal backup block below)" ;;
    failed-operator:*)      echo "  ⚠ Update-result operator send FAILED -- see $LOG_FILE (NOT routed to client; Terminal backup block below)" ;;
  esac

  # Always print the backup block so client is never stranded
  cat <<'BACKUP_BLOCK'

╔════════════════════════════════════════════════════════════════════╗
║   BACKUP -- IF YOU DID NOT GET A TELEGRAM NOTE                      ║
╠════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║   Open whatever you use to talk to your OpenClaw agent (Telegram,  ║
║   web UI, terminal chat -- whatever you have set up).               ║
║                                                                    ║
║   Paste this EXACT message to your agent (copy between the         ║
║   >>> and <<< markers):                                            ║
║                                                                    ║
║   >>>                                                              ║
║   I just ran update-skills.sh. There is an UPDATE PENDING flag     ║
║   at the top of my AGENTS.md describing what changed. Please       ║
║   follow the activation steps for any new skills listed in the     ║
║   flag. Run QC after each one. Send me a summary when complete.    ║
║   <<<                                                              ║
║                                                                    ║
║   Your agent will read the flag and walk through the activation    ║
║   for you. You don't need to type any other commands.              ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝

BACKUP_BLOCK
}

main "$@"
