#!/usr/bin/env bash
# scaffold-agent-files.sh — write per-agent core files for a single top-level agent.
#
# Trevor's agent-file architecture (locked 2026-05-24):
#   - SHARED files (one copy at workspace root, every agent symlinks to them):
#       USER.md, AGENTS.md, TOOLS.md
#   - PER-AGENT files (one copy per agent, in its workspace folder):
#       IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md
#   - Sub-agents (the role folders inside a dept) are EXCLUDED — they inherit
#     from their parent dept-head agent and have their own separate scaffolder
#     in 23-ai-workforce-blueprint/scripts/post-build-role-workspaces.py.
#
# What this script does for ONE agent:
#   1. Create the agent's workspace folder if it doesn't exist
#   2. Write IDENTITY.md, SOUL.md, MEMORY.md, HEARTBEAT.md as lightweight stubs
#      if they don't already exist (idempotent — never overwrites curated content)
#   3. Create/refresh symlinks for USER.md, AGENTS.md, TOOLS.md pointing at the
#      shared workspace root. If a file (not a symlink) already exists with the
#      same name, leave it alone and log a warning — operator decides whether
#      to convert it.
#   4. Verify the shared files exist at the workspace root. Warn loudly if not.
#
# This script is meant to be invoked from:
#   - materialize-dept-agents.sh   (after openclaw.json agents.list[] is updated)
#   - seed-dashboard-content.py    (after a dept-head row is inserted)
#   - add-department.sh            (after a new dept is added live)
#   - 23-ai-workforce-blueprint/scripts/build-workforce.py
#     (currently writes SOUL/MEMORY/HEARTBEAT directly; this fills the IDENTITY gap)
#
# Usage:
#   bash scaffold-agent-files.sh --agent-slug sales \
#                                --agent-name "Chief Revenue Officer" \
#                                --department sales
#   bash scaffold-agent-files.sh --agent-slug sales --agent-name "..." \
#                                --department sales \
#                                --workspace-dir /data/.openclaw/workspace/departments/sales
#
# Flags:
#   --agent-slug      required — the agent's slug (used in agent-id `dept-<slug>`)
#   --agent-name      required — friendly role title (e.g. "Chief Revenue Officer")
#   --department      optional — department slug (defaults to agent-slug); used
#                                in templates and to compute workspace path
#   --workspace-dir   optional — absolute path to the agent's workspace folder.
#                                If omitted, defaults to
#                                $OC_ROOT/workspace/departments/<department>
#   --shared-root     optional — absolute path to the shared workspace root that
#                                holds USER.md / AGENTS.md / TOOLS.md.
#                                Defaults to $OC_ROOT/workspace
#   --force           optional — re-write per-agent files even if they exist
#                                (NEVER use during install — operator-only)
#
# Exit codes:
#   0 — success (created or already exists)
#   1 — fatal (missing args, can't reach OC_ROOT, etc.)
#
# Idempotency contract:
#   - Re-running with the same args is a no-op (prints "= already exists")
#   - Never overwrites a per-agent file that has content the operator/agent
#     may have edited
#   - Symlinks: if the symlink already points at the right target, no change.
#     If a regular file exists with that name, leave it and warn.

set -euo pipefail

# ─── Arg parsing ─────────────────────────────────────────────────────────────
AGENT_SLUG=""
AGENT_NAME=""
DEPARTMENT=""
WORKSPACE_DIR=""
SHARED_ROOT=""
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-slug)    AGENT_SLUG="${2:-}";    shift 2 ;;
    --agent-name)    AGENT_NAME="${2:-}";    shift 2 ;;
    --department)    DEPARTMENT="${2:-}";    shift 2 ;;
    --workspace-dir) WORKSPACE_DIR="${2:-}"; shift 2 ;;
    --shared-root)   SHARED_ROOT="${2:-}";   shift 2 ;;
    --force)         FORCE=1;                shift ;;
    -h|--help)
      sed -n '2,60p' "$0"
      exit 0
      ;;
    *)
      echo "[scaffold-agent-files] FATAL: unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$AGENT_SLUG" || -z "$AGENT_NAME" ]]; then
  echo "[scaffold-agent-files] FATAL: --agent-slug and --agent-name are required" >&2
  echo "Usage: bash scaffold-agent-files.sh --agent-slug X --agent-name \"Y\" [--department Z]" >&2
  exit 1
fi

# Default department to agent-slug
[[ -z "$DEPARTMENT" ]] && DEPARTMENT="$AGENT_SLUG"

# ─── Platform detection ──────────────────────────────────────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT="/data/.openclaw"
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[scaffold-agent-files] FATAL: no OpenClaw root found at /data/.openclaw or \$HOME/.openclaw" >&2
  exit 1
fi

# Default workspace dir
[[ -z "$WORKSPACE_DIR" ]] && WORKSPACE_DIR="$OC_ROOT/workspace/departments/$DEPARTMENT"
# Default shared root
[[ -z "$SHARED_ROOT" ]] && SHARED_ROOT="$OC_ROOT/workspace"

NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "[scaffold-agent-files] OC_ROOT=$OC_ROOT"
echo "[scaffold-agent-files] agent=$AGENT_SLUG  name=\"$AGENT_NAME\"  dept=$DEPARTMENT"
echo "[scaffold-agent-files] workspace=$WORKSPACE_DIR"
echo "[scaffold-agent-files] shared-root=$SHARED_ROOT"

# ─── Ensure workspace dir exists ─────────────────────────────────────────────
if [[ ! -d "$WORKSPACE_DIR" ]]; then
  mkdir -p "$WORKSPACE_DIR"
  echo "  + created workspace dir: $WORKSPACE_DIR"
fi

# ─── Verify shared root exists ───────────────────────────────────────────────
if [[ ! -d "$SHARED_ROOT" ]]; then
  echo "[scaffold-agent-files] WARN: shared root $SHARED_ROOT does not exist" >&2
  echo "[scaffold-agent-files] WARN: USER.md / AGENTS.md / TOOLS.md symlinks will dangle" >&2
fi

# ─── Helper: write a file only if it doesn't exist (or --force) ─────────────
write_if_missing() {
  local path="$1"
  local content="$2"
  if [[ -f "$path" && $FORCE -eq 0 ]]; then
    echo "  = already exists: $(basename "$path")"
    return 0
  fi
  printf '%s' "$content" > "$path"
  echo "  + wrote: $(basename "$path")"
}

# ─── Per-agent file templates ────────────────────────────────────────────────
IDENTITY_CONTENT="# IDENTITY.md — ${AGENT_NAME}

**Department:** ${DEPARTMENT}
**Agent slug:** ${AGENT_SLUG}
**Generated:** ${NOW_ISO}

## Who I Am

- **Name:** (assign during first conversation — capture the persona/name the owner gives this agent)
- **Role:** ${AGENT_NAME}
- **Department:** ${DEPARTMENT}
- **Reports to:** Master Orchestrator (CEO Agent)

## What This Role Owns

The ${DEPARTMENT} department's performance and outputs. See SOUL.md for the
department mission, KPIs, and standards. See HEARTBEAT.md for the cadence.

## Operating Discipline

- I back up \`/data/.openclaw/openclaw.json\` before any config change.
- I follow the Teach Yourself Protocol (TYP) for substantial new knowledge.
- I investigate root cause before fixing. I never claim done without verifying.
- I use the symlinked TOOLS.md to know what tools are available.
- I use the symlinked AGENTS.md to know how to behave and who to escalate to.
- I use the symlinked USER.md to know who I work for and how they communicate.

## Persona Governance

When the owner assigns me a persona, I adopt its voice and style while still
honoring the mission in SOUL.md and the values in USER.md. If a persona's
instructions conflict with company values, I surface the conflict before acting.

---

This file is unique to this agent. Subagents under this department inherit
from this IDENTITY but write their own role-specific IDENTITY.md.
"

MEMORY_CONTENT="# MEMORY.md — ${AGENT_NAME}

> Long-term state, decisions, and metrics for the ${DEPARTMENT} department head.
> Updated by this agent after each meaningful work session.

## ${NOW_ISO%T*} — Agent Scaffolded

- Agent slug: ${AGENT_SLUG}
- Per-agent files created via scaffold-agent-files.sh
- Awaiting first task assignment

## Long-term facts

- (Updated as the role accumulates work)

## Decisions

- (Logged at the time they're made)

## What I've learned about the owner / customers

- (Captured from feedback over time)
"

# Pull SOUL/HEARTBEAT defaults — only used if those files don't already exist.
# In practice, the dept's SOUL.md + HEARTBEAT.md are written by build-workforce.py
# from the interview answers, so these stubs almost never get written. They're
# here for the case where the scaffolder runs without a prior Skill 23 build
# (e.g. add-department.sh on a live install).
SOUL_CONTENT="# SOUL.md — ${AGENT_NAME}

## Mission

Serve the ${DEPARTMENT} department by executing this role's responsibilities at
a standard high enough to deserve the trust of the human owner.

## Voice

Mirror the owner's communication style (see symlinked USER.md > Behavioral
Identity Profile). Plain, direct, no jargon unless the task domain requires it.

## Values

- Output quality beats output speed
- Honor the persona when assigned; honor the mission always
- Surface uncertainty rather than guess
- Document what you learn in MEMORY.md

## Department Mission

(Populate from the interview answers in
\`/data/.openclaw/workspace/zero-human-company/<slug>/workforce-interview-answers.md\`.
If this stub is still showing, Skill 23's build-workforce.py did not run for
this department — invoke it or fill this manually.)
"

HEARTBEAT_CONTENT="# HEARTBEAT.md — ${AGENT_NAME}

Cadence: every 30 minutes (default).
Owner: ${AGENT_SLUG}
Dept: ${DEPARTMENT}

## On startup

1. Read SOUL.md for the department mission
2. Read inherited AGENTS.md, TOOLS.md, USER.md (via symlinks)
3. Check for assigned persona (if any)
4. Read latest entries in MEMORY.md

## Scheduled tasks

(Empty — populated by the dept's daily/weekly cadence in SOUL.md / how-to.md.)
"

# ─── Write per-agent files ──────────────────────────────────────────────────
write_if_missing "$WORKSPACE_DIR/IDENTITY.md"  "$IDENTITY_CONTENT"
write_if_missing "$WORKSPACE_DIR/SOUL.md"      "$SOUL_CONTENT"
write_if_missing "$WORKSPACE_DIR/MEMORY.md"    "$MEMORY_CONTENT"
write_if_missing "$WORKSPACE_DIR/HEARTBEAT.md" "$HEARTBEAT_CONTENT"

# ─── Symlink shared files ───────────────────────────────────────────────────
# We compute the relative path from the agent's workspace to the shared root so
# symlinks remain valid if the install is mounted at a different prefix.
relpath() {
  python3 -c "import os, sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$1" "$2"
}

for shared in USER.md AGENTS.md TOOLS.md; do
  link_path="$WORKSPACE_DIR/$shared"
  target_path="$SHARED_ROOT/$shared"

  # Verify the target exists (warn if not — symlinks would dangle but we still create them
  # so the architecture is in place when the shared file lands)
  if [[ ! -f "$target_path" ]]; then
    echo "  ! WARN: shared $shared not found at $target_path — symlink will dangle until shared file is created"
  fi

  rel_target=$(relpath "$target_path" "$(dirname "$link_path")")

  if [[ -L "$link_path" ]]; then
    # Already a symlink — check it points where we want
    current_target=$(readlink "$link_path")
    if [[ "$current_target" == "$rel_target" || "$current_target" == "$target_path" ]]; then
      echo "  = symlink already correct: $shared → $current_target"
      continue
    fi
    # Stale symlink — replace
    rm "$link_path"
    ln -s "$rel_target" "$link_path"
    echo "  ~ replaced stale symlink: $shared → $rel_target"
    continue
  fi

  if [[ -e "$link_path" ]]; then
    # Regular file with this name — DON'T overwrite. Operator decides.
    echo "  ! WARN: $shared exists as a regular file (not symlink) at $link_path — leaving as-is" >&2
    echo "  !       to convert: rm '$link_path' && ln -s '$rel_target' '$link_path'" >&2
    continue
  fi

  ln -s "$rel_target" "$link_path"
  echo "  + symlinked: $shared → $rel_target"
done

echo "[scaffold-agent-files] done: $AGENT_SLUG"
exit 0
